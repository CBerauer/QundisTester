import logging
import time
from .hci import Parser, encode, telegram

MODES = {'ct':3, 'c':5, 't':2, 's':1, 'custom-ct':7}

def ports():
    from serial.tools import list_ports
    return [dict(port=p.device, description=p.description, manufacturer=p.manufacturer,
                 vid=p.vid, pid=p.pid, serial_number=p.serial_number) for p in list_ports.comports()]

def candidates():
    return [p['port'] for p in ports() if any(x in str(p).lower() for x in ('imst','iu891','im891'))
            or (p['vid'], p['pid']) == (0x04b4,0x0003) and str(p['serial_number']).startswith('IMS')]

class HCIReceiver:
    def __init__(self, port, ingest, status):
        import serial
        self.serial = serial.Serial(port, 115200, timeout=.2, write_timeout=2)
        self.parser = Parser()
        self.ingest, self.status = ingest, status

    def close(self):
        self.serial.close()

    def receive(self):
        frames = self.parser.feed(self.serial.read(4096))
        self.status(crc_errors=self.parser.errors)
        for sap,msg,payload,raw in frames:
            if sap == 9 and msg == 0x20:
                try:
                    self.ingest(telegram(payload, raw))
                except ValueError:
                    logging.exception('Invalid RX indication')
            elif sap == 9 and msg == 0x24:
                self.status(scan_notification_hex=payload.hex())
            elif sap == 1 and msg == 0x10:
                raise ConnectionError('Dongle restarted; reconnecting and restoring active configuration')
        return frames

    def request(self, sap, msg, payload=b''):
        self.serial.write(encode(sap,msg,payload))
        end = time.monotonic()+3
        while time.monotonic() < end:
            for endpoint, response, body, _ in self.receive():
                if endpoint == sap and response == msg+1:
                    if not body or body[0] != 0:
                        raise ValueError(f'HCI {sap:02x}/{msg:02x} rejected: {body.hex()}')
                    return body[1:]
        raise TimeoutError(f'HCI {sap:02x}/{msg:02x} response timed out')

    def identify(self):
        info = self.request(1,3)
        if not info or info[0] != 0x6e:
            raise ValueError(f'Not an iU891A-XL: {info.hex()}')
        firmware = self.request(1,5)
        self.status(hardware_hex=info.hex(), firmware_hex=firmware.hex(),
                    firmware=f'{firmware[1]}.{firmware[0]} ' + firmware[4:].decode('ascii','replace') if len(firmware)>=4 else firmware.hex())

    def configure(self, mode):
        config = bytearray(self.request(9,1))
        if len(config) != 11:
            raise ValueError(f'Unsupported config length {len(config)}; refusing guessed layout')
        self.status(original_config_hex=config.hex())
        # Disable header-only scan mode first. RAM settings only; never NVM/restart.
        self.request(9,0x21,b'\x00\x00\x00')
        config[0] = MODES[mode]
        options = (int.from_bytes(config[1:3],'little') & ~1) | 2
        config[1:3] = options.to_bytes(2,'little')
        self.request(9,3,bytes(config))
        actual = self.request(9,1)
        if actual != config:
            raise ValueError('Active configuration readback differs')
        self.status(active_config_hex=actual.hex(), mode=mode)

def run_radio(stop, port, mode, ingest, status):
    while not stop.is_set():
        receiver = None
        try:
            choices = [port] if port else candidates()
            if not choices:
                raise RuntimeError('No identifiable IMST port. Run --ports; use --port COM3 if confirmed.')
            if len(choices)>1:
                raise RuntimeError('Multiple candidate ports; select --port explicitly')
            receiver = HCIReceiver(choices[0], ingest, status)
            status(state='identifying', port=choices[0])
            receiver.identify()
            receiver.configure(mode)
            status(state='listening', error=None)
            while not stop.is_set():
                receiver.receive()
        except Exception as error:
            logging.exception('Receiver unavailable')
            status(state='disconnected', error=str(error))
        finally:
            if receiver:
                receiver.close()
        stop.wait(3)

def run_simulation(stop, ingest, status):
    status(state='simulation', port='synthetic', firmware='simulation — no hardware')
    n=0
    while not stop.is_set():
        # Synthetic QDS standard volume record, not a captured Q water fixture.
        for manufacturer, identity, typ in ((0x4493,12345678,7),(0x0421,87654321,0xff)):
            body = b'\x44'+manufacturer.to_bytes(2,'little')+bytes.fromhex(str(identity))[::-1]+bytes([0x1a,typ,0x7a,0,0,0,0,4,0x13])+(123456+n).to_bytes(4,'little')
            raw = bytes([len(body)])+body
            ingest(dict(raw_hex=raw.hex(),hci_hex='',rssi=-54-n%10,mode='C',format='A',encryption_mode=0,decryption_status=0,dongle_timestamp=None,simulated=True))
        n+=1
        stop.wait(2)
