"""Conservative standard records decoder; proprietary data stays visible."""
import json
import subprocess

TYPES = {2:'Electricity', 4:'Heat', 6:'Warm water', 7:'Water', 8:'Heat cost allocator', 0x37:'Radio converter'}

def qundis_walkby(b, result):
    """Recognize the specific plain water WalkByDataSet, never search arbitrary bytes."""
    pos = 11
    if b[9] == 0x37:
        if len(b) < 21 or b[11:13] != b'\x07\x79' or b[13:17] != b[4:8] or b[17:19] != b[2:4] or b[19] != b[8] or b[20] not in (6,7):
            return False
        result['device_type'] = TYPES[b[20]] + ' (radio converter)'
        result['model'] = 'Qundis water / Q module (water payload)'
        pos = 21
    if len(b) < pos+4 or b[pos:pos+4] != b'\x0d\xff\x5f\x35':
        return False
    start = pos+4
    block = b[start:start+53]
    if len(block)!=53 or any(block[i]!=v for i,v in {0:0,1:0x82,3:0,4:0,7:7,8:0xc1,9:0x13}.items()):
        return False
    # Require the expected trailing filler and meter datetime record as a second
    # structural check. Reject encrypted or different proprietary layouts.
    if b[start+53:start+55] != b'\x04\x6d' or len(b)!=start+59 or block[52]!=0x2f:
        return False
    value_bytes = block[12:16]
    if any(x & 15 > 9 or x >> 4 > 9 for x in value_bytes):
        return False
    litres = sum(((x >> 4)*10+(x & 15))*100**i for i,x in enumerate(value_bytes))
    result.update(reading={'value':litres/1000,'unit':'m³','source':'Qundis plain water WalkByDataSet'},
                  decode_status='Qundis plain water WalkByDataSet', validated_plain_walkby=True)
    result['fields'] = [dict(name='current_volume',raw_hex=value_bytes.hex(),value=litres/1000,unit='m³',storage=0)]
    return True

def decode(raw_hex):
    b = bytes.fromhex(raw_hex)
    result = dict(meter_id=None, manufacturer='Unknown', device_type='Unknown',
                  model='Unknown', reading=None, fields=[], decode_status='unsupported')
    if len(b) < 10:
        result['decode_status'] = 'truncated header'
        return result
    m = int.from_bytes(b[2:4], 'little')
    manufacturer = ''.join(chr(64 + ((m >> shift) & 31)) for shift in (10,5,0))
    if any(not 'A' <= c <= 'Z' for c in manufacturer):
        manufacturer='Unknown'
    result.update(meter_id=b[4:8][::-1].hex(), manufacturer=manufacturer,
                  version=b[8], type_code=b[9], device_type=TYPES.get(b[9], f'Unknown ({b[9]:02x})'))
    if manufacturer == 'QDS':
        result['model'] = 'Qundis water candidate' if b[9] in (6,7) else 'Qundis (model unverified)'
    if len(b) < 11:
        return result
    ci = b[10]
    if manufacturer == 'QDS' and ci == 0x78 and b[9] in (6,7,0x37) and qundis_walkby(b, result):
        return result
    if ci == 0x78:
        pos = 11
    elif ci == 0x7a and len(b) >= 15:
        if (int.from_bytes(b[13:15], 'little') >> 8) & 31:
            result['decode_status'] = 'encrypted transport'
            return result
        pos = 15
    elif ci == 0x72 and len(b) >= 23:
        if manufacturer=='QDS' and b[18] in (6,7) and b[15:17]==b[2:4]:
            result['device_type']=TYPES[b[18]]+' (radio converter)' if b[9]==0x37 else TYPES[b[18]]
            result['model']='Qundis water / Q module (water payload)'
        if (int.from_bytes(b[21:23], 'little') >> 8) & 31:
            result['decode_status'] = 'encrypted transport'
            return result
        pos = 23
    else:
        return result
    try:
        while pos < len(b):
            dif = b[pos]; pos += 1
            if dif == 0x2f:
                continue
            if dif & 15 == 15:
                break
            storage = (dif >> 6) & 1
            extension = dif
            shift = 1
            tariff = subunit = 0
            while extension & 128:
                extension = b[pos]; pos += 1
                storage |= (extension & 15) << shift
                shift += 4
                tariff |= extension & 0x30
                subunit |= extension & 0x40
            vif = b[pos]; pos += 1
            extension = vif
            has_vife = bool(vif & 128)
            while extension & 128:
                extension = b[pos]; pos += 1
            kind = dif & 15
            size = {0:0,1:1,2:2,3:3,4:4,5:4,6:6,7:8,9:1,10:2,11:3,12:4,14:6}.get(kind)
            if size is None or pos + size > len(b):
                raise ValueError('Unsupported/truncated record')
            data = b[pos:pos+size]; pos += size
            value = None
            if kind in (1,2,3,4,6,7):
                value = int.from_bytes(data, 'little', signed=True)
            elif kind in (9,10,11,12,14) and all((x & 15) < 10 and x >> 4 < 10 for x in data):
                value = sum(((x >> 4)*10+(x & 15))*100**i for i,x in enumerate(data))
            field = dict(dif=dif, vif=vif, storage=storage, raw_hex=data.hex(), value=value)
            if not has_vife and 0x10 <= vif <= 0x17 and value is not None:
                field.update(value=value * 10**((vif & 7)-6), unit='m³')
                if not storage and not tariff and not subunit and not (dif & 0x30):
                    result['reading'] = {'value':field['value'], 'unit':'m³', 'source':'standard DIF/VIF'}
            result['fields'].append(field)
        result['decode_status'] = 'standard records' if result['fields'] else 'proprietary/unsupported records'
    except (IndexError, ValueError):
        result['reading'] = None
        result['decode_status'] = 'partial/unsupported records'
    return result

class ExternalDecoder:
    def __init__(self, executable):
        self.executable = executable

    def decode(self, raw_hex, meter_id):
        # External executable, no shell; failures never suppress a received packet.
        run = subprocess.run([self.executable, '--format=json', raw_hex,
                              'tester', 'auto', meter_id, 'NOKEY'], capture_output=True,
                             text=True, timeout=5)
        for line in run.stdout.splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
        raise ValueError(f'wmbusmeters returned no JSON (exit {run.returncode})')
