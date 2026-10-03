import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
from tester.hci import Parser, crc, encode, telegram
from tester.decoder import decode, ExternalDecoder
from tester.store import Store
from tester.web import server
from tester.receiver import run_simulation, HCIReceiver

RAW='18449344785634121a077a00000000041340e20100'

class Tests(unittest.TestCase):
    def test_actual_com3_capture(self):
        event=json.loads((Path(__file__).parent/'fixtures/com3-qds.json').read_text())
        frames=Parser().feed(b'\xc0'+bytes.fromhex(event['hci_hex'])+b'\xc0')
        self.assertEqual(len(frames),1)
        decoded=telegram(frames[0][2],frames[0][3])
        self.assertEqual(decoded,event)
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);store.ingest(event)
            result=store.snapshot()['meters'][0]
            self.assertEqual(result['decoded']['meter_id'],'12345678')
            self.assertAlmostEqual(result['decoded']['reading']['value'],0.511)

    def test_live_qundis_amr_and_walkby(self):
        events=json.loads((Path(__file__).parent/'fixtures/qundis-water-live.json').read_text())
        expected={'12345678':0.529,'12345679':0.229,'12345680':0.361}
        matched=set()
        for event in events:
            d=decode(event['raw_hex'])
            self.assertIsNotNone(d['reading'])
            if bytes.fromhex(event['raw_hex'])[10]==0x72:
                self.assertEqual(d['device_type'],'Water (radio converter)')
                self.assertEqual(d['model'],'Qundis water / Q module (water payload)')
                self.assertAlmostEqual(d['reading']['value'],expected[d['meter_id']])
                matched.add(d['meter_id'])
            if d['meter_id']=='12345680':
                self.assertAlmostEqual(d['reading']['value'],0.361)
        self.assertEqual(matched,set(expected))

    def test_walkby_rejects_wrong_layout_and_bcd(self):
        event=json.loads((Path(__file__).parent/'fixtures/com3-qds.json').read_text())
        raw=bytes.fromhex(event['raw_hex'])
        # All defining bytes, duplicated identity, block length, trailing datetime.
        for position in (13,17,19,20,21,22,23,24,25,26,28,29,32,33,34,37,77,78,79):
            broken=bytearray(raw);broken[position]^=0xff
            self.assertIsNone(decode(broken.hex())['reading'],position)
        for size in range(len(raw)):
            self.assertIsNone(decode(raw[:size].hex())['reading'],size)

    def test_latest_reading_survives_undecodable_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            first='2026-10-03T11:00:00+00:00'
            second='2026-10-03T11:05:00+00:00'
            store.ingest(dict(raw_hex=RAW),timestamp=first)
            # Same header identity, unsupported application payload.
            unknown=bytes.fromhex(RAW)[:10]+b'\x79\x00'
            store.ingest(dict(raw_hex=unknown.hex()),timestamp=second)
            snapshot=store.snapshot();meter=snapshot['meters'][0]
            self.assertIsNone(meter['decoded']['reading'])
            self.assertEqual(meter['last_reading']['timestamp'],first)
            self.assertEqual(meter['timestamp'],second)
            self.assertEqual(meter['last_reading']['value'],123.456)
            self.assertNotIn('last_reading',snapshot['telegrams'][0])

    def test_actual_encryption_never_bypassed(self):
        event=json.loads((Path(__file__).parent/'fixtures/com3-qds.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            store.ingest(dict(event,encryption_mode=5,decryption_status=2))
            self.assertIsNone(store.snapshot()['meters'][0]['decoded']['reading'])
            self.assertIsNone(store.snapshot()['meters'][0]['last_reading'])

    def test_settings_persistence_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            store.save_settings({'manufacturers':['QDS','HAG','QDS']})
            self.assertEqual(Store(directory).snapshot()['settings'],{'manufacturers':['HAG','QDS']})
            for invalid in ({},{'manufacturers':'QDS'},{'manufacturers':[123]},{'manufacturers':['<script>']},{'manufacturers':['qds']},{'manufacturers':[],'extra':True}):
                with self.assertRaises(ValueError):store.save_settings(invalid)
            store.save_settings({'manufacturers':[]})
            self.assertEqual(Store(directory).settings,{'manufacturers':[]})

    def test_crc_and_reference_ping(self):
        self.assertEqual(crc(b'123456789'),0x906e)
        self.assertEqual(encode(1,1).hex(),'c001011607c0')

    def test_fragmentation_escape_and_recovery(self):
        encoded=encode(9,32,b'\xc0\xdb')
        p=Parser(); self.assertEqual(p.feed(encoded[:4]),[])
        frames=p.feed(encoded[4:]); self.assertEqual(frames[0][2],b'\xc0\xdb')
        self.assertEqual(len(p.feed(b'\xc0bad\xc0'+encode(1,1))),1)
        self.assertEqual(p.errors,1)
        p.feed(b'x'*2000); self.assertLessEqual(len(p.buffer),1024)
        self.assertEqual(len(p.feed(b'\xc0'+encode(1,1))),1)

    def test_rx_metadata(self):
        e=telegram(bytes.fromhex('00000000000018c4')+bytes.fromhex(RAW),b'raw')
        self.assertEqual((e['rssi'],e['mode'],e['format']),(-60,'Custom C','B'))
        self.assertEqual(e['raw_hex'],RAW)

    def test_decode_current_and_historical(self):
        d=decode(RAW); self.assertEqual(d['manufacturer'],'QDS')
        self.assertEqual(d['meter_id'],'12345678')
        self.assertAlmostEqual(d['reading']['value'],123.456)
        historical=RAW.replace('041340','441340')
        self.assertIsNone(decode(historical)['reading'])
        self.assertIsNone(decode(RAW[:-2])['reading'])
        self.assertIsNone(decode(RAW.replace('7a00000000','7a00000005'))['reading'])

    def test_unknown_and_limit_alias_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            for i in range(110): store.ingest(dict(raw_hex='ff',rssi=-50,mode='?',format='?'))
            self.assertEqual(len(store.snapshot()['telegrams']),100)
            self.assertEqual(len(store.snapshot()['meters']),1)
            store.alias('unknown','Keller <script>')
            self.assertEqual(Store(directory).aliases['unknown'],'Keller <script>')

    def test_simulation_http_csv_and_write(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory); stop=threading.Event()
            worker=threading.Thread(target=run_simulation,args=(stop,store.ingest,store.update_status));worker.start()
            http=server(store,'127.0.0.1',0)
            thread=threading.Thread(target=http.serve_forever);thread.start()
            base=f'http://127.0.0.1:{http.server_port}'
            try:
                with urllib.request.urlopen(base+'/api/state') as r: state=json.load(r)
                self.assertEqual(state['status']['state'],'simulation')
                self.assertEqual(len(state['meters']),2)
                key=state['meters'][0]['device_key']
                request=urllib.request.Request(base+'/api/alias',json.dumps({'key':key,'alias':'=evil'}).encode(),{'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as r: self.assertEqual(r.status,200)
                with urllib.request.urlopen(base+'/api/export.csv') as r: self.assertIn("'=evil",r.read().decode('utf-8-sig'))
                request=urllib.request.Request(base+'/api/settings',json.dumps({'manufacturers':['QDS']}).encode(),{'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as r:self.assertEqual(r.status,200)
                with urllib.request.urlopen(base+'/api/export.csv?filtered=1') as r:
                    text=r.read().decode('utf-8-sig');self.assertIn('QDS',text);self.assertNotIn('87654321',text)
                self.assertEqual(len(store.snapshot()['meters']),2)
                self.assertEqual(store.snapshot()['settings'],{'manufacturers':['QDS']})
                self.assertEqual(Store(directory).settings,{'manufacturers':['QDS']})
                with urllib.request.urlopen(base) as r: self.assertIn(b'textContent',r.read())
            finally:
                stop.set(); worker.join();http.shutdown();http.server_close();thread.join()

    def test_config_ram_scan_and_readback(self):
        receiver=object.__new__(HCIReceiver);receiver.status=lambda **k:None
        config=bytes.fromhex('030b0000003200e8030000')
        expected=bytes.fromhex('070a0000003200e8030000')
        with patch.object(receiver,'request',side_effect=[config,b'',b'',expected]) as request:
            receiver.configure('custom-ct')
            self.assertEqual(request.call_args_list[1].args,(9,0x21,b'\x00\x00\x00'))
            self.assertEqual(request.call_args_list[2].args,(9,3,expected))

    def test_external_failure_keeps_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            external=ExternalDecoder('missing-executable')
            store=Store(directory,external)
            store.ingest(dict(raw_hex=RAW))
            self.assertIn('external_decoder_error',store.snapshot()['telegrams'][0])

if __name__=='__main__': unittest.main()
