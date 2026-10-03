import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
import signal
from pathlib import Path
from .decoder import ExternalDecoder
from .receiver import ports, run_radio, run_simulation, MODES, HCIReceiver
from .store import Store
from .web import server

def main():
    parser=argparse.ArgumentParser(description='Local iU891A-XL tester')
    parser.add_argument('--simulate',action='store_true')
    parser.add_argument('--ports',action='store_true')
    parser.add_argument('--diagnose',action='store_true',help='Read identity and active config; no configuration changes')
    parser.add_argument('--port')
    parser.add_argument('--mode',choices=list(MODES),default='ct')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--http-port',type=int,default=8080)
    parser.add_argument('--data',default='data')
    parser.add_argument('--wmbusmeters',help='Optional executable path for raw telegram decoding')
    parser.add_argument('--restore-state',help='Restore a previously saved API snapshot before receiving')
    args=parser.parse_args()
    if args.ports:
        print(json.dumps(ports(),indent=2)); return
    if args.diagnose:
        if not args.port:
            parser.error('--diagnose requires --port')
        receiver=HCIReceiver(args.port,lambda e: print(json.dumps(e)),lambda **s: print(json.dumps(s)))
        try:
            receiver.identify(); print('active_config_hex='+receiver.request(9,1).hex())
        finally:
            receiver.close()
        return
    Path(args.data).mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(Path(args.data)/'tester.log',maxBytes=2_000_000,backupCount=4,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    store=Store(args.data,ExternalDecoder(args.wmbusmeters) if args.wmbusmeters else None)
    if args.restore_state:
        snapshot=json.loads(Path(args.restore_state).read_text('utf-8-sig'))
        restored={e['sequence']:e for e in snapshot.get('meters',[])+snapshot.get('telegrams',[])}
        for event in sorted(restored.values(),key=lambda e:e['sequence']):
            store.ingest({k:v for k,v in event.items() if k not in ('decoded','external_decoded','sequence','device_key','last_reading')},timestamp=event['timestamp'])
    http=server(store,args.host,args.http_port)
    stop=threading.Event()
    target=run_simulation if args.simulate else run_radio
    arguments=(stop,store.ingest,store.update_status) if args.simulate else (stop,args.port,args.mode,store.ingest,store.update_status)
    worker=threading.Thread(target=target,args=arguments,daemon=True);worker.start()
    print(f'Open http://{args.host}:{args.http_port} â€” Ctrl+C to stop',flush=True)
    def terminate(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set(); http.server_close();worker.join(timeout=6)

if __name__=='__main__':
    main()
