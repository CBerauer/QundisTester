import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def server(store, host, port):
    class Handler(BaseHTTPRequestHandler):
        def respond(self,code,data,kind='application/json'):
            self.send_response(code)
            self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path=='/':
                self.respond(200,Path(__file__).with_name('index.html').read_bytes(),'text/html')
            elif self.path=='/api/state':
                self.respond(200,json.dumps(store.snapshot(),ensure_ascii=False).encode())
            elif self.path in ('/api/export.csv','/api/export.csv?filtered=1'):
                snapshot=store.snapshot(); output=io.StringIO(newline='')
                columns=['sequence','timestamp','device_key','alias','meter_id','manufacturer','device_type','reading','rssi','mode','format','raw_hex','hci_hex','dongle_timestamp','decoded','external_decoded']
                writer=csv.DictWriter(output,fieldnames=columns); writer.writeheader()
                for event in snapshot['telegrams']:
                    d=event['decoded']; row={k:event.get(k,'') for k in columns}
                    if self.path.endswith('?filtered=1') and snapshot['settings']['manufacturers'] and d.get('manufacturer','Unknown') not in snapshot['settings']['manufacturers']:
                        continue
                    row.update(alias=snapshot['aliases'].get(event['device_key'],''),
                               **{k:d.get(k,'') for k in ('meter_id','manufacturer','device_type','reading')})
                    for k in ('decoded','external_decoded','reading'):
                        row[k]=json.dumps(row[k],ensure_ascii=False)
                    # Protect spreadsheet users from formula interpretation.
                    row={k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v for k,v in row.items()}
                    writer.writerow(row)
                self.respond(200,output.getvalue().encode('utf-8-sig'),'text/csv')
            else:
                self.respond(404,b'{}')

        def do_POST(self):
            # Same-origin writes only, including when accessed through localhost.
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):
                self.respond(403,b'{}'); return
            if self.path not in ('/api/alias','/api/settings') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.respond(400,b'{}'); return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:
                    raise ValueError('Body too large')
                value=json.loads(self.rfile.read(length))
                if self.path=='/api/settings':
                    store.save_settings(value)
                else:
                    store.alias(value['key'],value['alias'])
                self.respond(200,b'{"ok":true}')
            except (ValueError,KeyError,TypeError):
                self.respond(400,b'{"error":"Invalid input"}')
            except OSError:
                self.respond(500,b'{"error":"Could not save JSON file"}')

        def log_message(self,*args):
            pass
    return ThreadingHTTPServer((host,port),Handler)
