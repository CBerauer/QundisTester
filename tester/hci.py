"""IMST HCI 2.4: SLIP framing and CRC-16/IBM-SDLC."""
import struct

def crc(data):
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x8408 if value & 1 else 0)
    return value ^ 0xffff

def encode(sap, msg, payload=b''):
    data = bytes([sap, msg]) + payload
    data += struct.pack('<H', crc(data))
    return b'\xc0' + data.replace(b'\xdb', b'\xdb\xdd').replace(b'\xc0', b'\xdb\xdc') + b'\xc0'

class Parser:
    def __init__(self):
        self.buffer = bytearray()
        self.errors = 0
        self.overflow = False

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == 0xc0:
                if self.buffer and not self.overflow:
                    raw = bytes(self.buffer)
                    out = bytearray()
                    i = 0
                    try:
                        while i < len(raw):
                            b = raw[i]
                            if b == 0xdb:
                                i += 1
                                b = {0xdc: 0xc0, 0xdd: 0xdb}[raw[i]]
                            out.append(b)
                            i += 1
                        if len(out) < 4 or crc(out[:-2]) != int.from_bytes(out[-2:], 'little'):
                            raise ValueError('CRC')
                        frames.append((out[0], out[1], bytes(out[2:-2]), bytes(out)))
                    except (KeyError, IndexError, ValueError):
                        self.errors += 1
                self.buffer.clear()
                self.overflow = False
            elif not self.overflow:
                self.buffer.append(byte)
                if len(self.buffer) > 1024:
                    self.buffer.clear()
                    self.overflow = True
                    self.errors += 1
        return frames

PACKETS = {1: ('S', 'A'), 2: ('T', 'A'), 4: ('C 50k', 'A'), 5: ('C', 'A'),
           6: ('Enhanced T', 'A'), 7: ('Custom T', 'A'), 8: ('Custom C', 'A'),
           20: ('C 50k', 'B'), 21: ('C', 'B'), 24: ('Custom C', 'B')}

def telegram(payload, raw):
    if len(payload) < 8:
        raise ValueError('Short RX indication')
    mode, fmt = PACKETS.get(payload[6], ('unknown', 'unknown'))
    return dict(raw_hex=payload[8:].hex(), hci_hex=raw.hex(),
                dongle_timestamp=int.from_bytes(payload[:4], 'little'),
                decryption_status=payload[4], encryption_mode=payload[5],
                packet_info=payload[6], rssi=struct.unpack('b', payload[7:8])[0],
                mode=mode, format=fmt)
