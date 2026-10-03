import collections
import datetime
import hashlib
import json
import logging
import threading
from pathlib import Path
from .decoder import decode

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

class Store:
    def __init__(self, directory, external=None):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.telegrams=collections.deque(maxlen=100)
        self.meters={}; self.status={'state':'starting'}; self.count=0
        self.external=external
        self.readings={}
        self.settings_path=self.directory/'settings.json'
        self.settings=json.loads(self.settings_path.read_text('utf-8')) if self.settings_path.exists() else {'manufacturers':[]}
        self.validate_settings(self.settings)
        self.alias_path=self.directory/'aliases.json'
        self.aliases=json.loads(self.alias_path.read_text('utf-8')) if self.alias_path.exists() else {}
        if not isinstance(self.aliases,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in self.aliases.items()):
            raise ValueError('aliases.json must contain a string-to-string object')

    def update_status(self, **values):
        with self.lock:
            self.status.update(values)

    def ingest(self, event, timestamp=None):
        event=dict(event, timestamp=timestamp or now())
        try:
            event['decoded']=decode(event['raw_hex'])
        except Exception as error:
            event['decoded']={'decode_status':str(error),'meter_id':None}
        d=event['decoded']
        unsupported = event.get('decryption_status',0)>1 or event.get('encryption_mode',0) and event.get('decryption_status')!=1
        validated_plain = d.get('validated_plain_walkby') and event.get('encryption_mode',0) in (0,255)
        if unsupported and not validated_plain:
            d['reading']=None; d['decode_status']='dongle reports unsupported/undecrypted payload'
        elif unsupported:
            event['gateway_note']='Gateway does not recognize this format; plain water payload passed structural validation'
        if self.external and d.get('meter_id'):
            try:
                event['external_decoded']=self.external.decode(event['raw_hex'],d['meter_id'])
            except Exception as error:
                event['external_decoder_error']=str(error)
        key=f"{d.get('manufacturer','?')}:{d.get('meter_id')}:{d.get('version')}:{d.get('type_code')}" if d.get('meter_id') else 'unknown:'+hashlib.sha256(bytes.fromhex(event['raw_hex'])).hexdigest()[:16]
        event['device_key']=key
        with self.lock:
            reading=d.get('reading')
            external=event.get('external_decoded',{})
            if not reading and isinstance(external.get('total_m3'),(int,float)):
                reading={'value':external['total_m3'],'unit':'m³','source':'wmbusmeters (unverified)'}
            if reading:
                self.readings[key]=dict(reading, timestamp=event['timestamp'])
            self.count+=1; event['sequence']=self.count
            self.telegrams.append(event)
            # Bound the discovery cache too, retaining latest devices.
            self.meters.pop(key,None); self.meters[key]=event
            if len(self.meters)>1000:
                expired=next(iter(self.meters));del self.meters[expired];self.readings.pop(expired,None)
        logging.info('telegram %s',json.dumps(event,ensure_ascii=False))

    def alias(self,key,value):
        if not isinstance(key,str) or not isinstance(value,str) or len(value)>100 or len(key)>200:
            raise ValueError('Invalid alias')
        with self.lock:
            aliases=dict(self.aliases); aliases[key]=value
            temp=self.alias_path.with_suffix('.tmp')
            temp.write_text(json.dumps(aliases,ensure_ascii=False,indent=2),'utf-8')
            temp.replace(self.alias_path); self.aliases=aliases

    def snapshot(self):
        with self.lock:
            return dict(status=dict(self.status),count=self.count,aliases=dict(self.aliases),
                        settings={'manufacturers':list(self.settings['manufacturers'])},
                        meters=[dict(e,last_reading=dict(self.readings[e['device_key']]) if e['device_key'] in self.readings else None) for e in self.meters.values()],telegrams=list(reversed(self.telegrams)))

    @staticmethod
    def validate_settings(value):
        if not isinstance(value,dict) or set(value)!={'manufacturers'} or not isinstance(value['manufacturers'],list) or len(value['manufacturers'])>100:
            raise ValueError('Invalid settings')
        if any(not isinstance(code,str) or not (code=='Unknown' or len(code)==3 and code.isascii() and code.isalpha() and code.isupper()) for code in value['manufacturers']):
            raise ValueError('Invalid manufacturer code')

    def save_settings(self,value):
        self.validate_settings(value)
        settings={'manufacturers':sorted(set(value['manufacturers']))}
        with self.lock:
            temp=self.settings_path.with_suffix('.tmp')
            temp.write_text(json.dumps(settings,indent=2),'utf-8');temp.replace(self.settings_path)
            self.settings=settings
