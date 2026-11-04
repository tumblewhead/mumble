"""Extract literal data from the pinned user artifact without executing pickle.

This intentionally imports ONE reviewed byte stream, not general Python pickles.
`pickletools.genops` parses bytes; no global lookup, REDUCE or BUILD is executed.
The array payloads are decoded with struct only after whole-artifact hash/shape
checks. Changing the accepted artifact requires a new review and new hash.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import pickletools
import struct

BINARY_SHA256 = '2ccdc212edc1af5406ff7b6a8872ed2179bf6fcb1c7d39a1319aa41af04bc41e'
HERE = Path(__file__).resolve().parent


def decode_hex(text):
    blob = bytes.fromhex(text)
    if len(blob) != 3400 or hashlib.sha256(blob).hexdigest() != BINARY_SHA256:
        raise ValueError('not the pinned user-supplied n13e artifact')
    operations = list(pickletools.genops(blob))
    by_offset = {position: (op.name, arg) for op, arg, position in operations}
    expected = {
        0: ('PROTO', 4), 2: ('FRAME', 3389),
        14: ('SHORT_BINUNICODE', 'uj'),
        19: ('SHORT_BINUNICODE', 'numpy._core.multiarray'),
        44: ('SHORT_BINUNICODE', '_reconstruct'),
        69: ('SHORT_BINUNICODE', 'ndarray'),
        96: ('BININT1', 13), 112: ('SHORT_BINUNICODE', 'f8'),
        126: ('SHORT_BINUNICODE', '<'), 148: ('NEWFALSE', None),
        259: ('SHORT_BINUNICODE', 'um'), 281: ('BININT1', 27),
        287: ('NEWFALSE', None), 510: ('SHORT_BINUNICODE', 'hu'),
        524: ('SHORT_BINUNICODE', 'A'),
        545: ('BININT1', 13), 547: ('BININT1', 27),
        553: ('NEWFALSE', None),
        3371: ('SHORT_BINUNICODE', 'h'), 3384: ('SHORT_BINUNICODE', 'N'),
        3388: ('BININT1', 13), 3390: ('SHORT_BINUNICODE', 'ext'),
        3396: ('BININT1', 2), 3398: ('SETITEMS', None), 3399: ('STOP', None),
    }
    if len(operations) != 128 or any(by_offset.get(k) != v for k,v in expected.items()):
        raise ValueError('unexpected data-only artifact layout')
    arrays = {}
    for name, position, size in [('uj',149,13),('um',288,27),('A',554,351)]:
        opcode, payload = by_offset[position]
        if opcode not in ('BINBYTES','SHORT_BINBYTES') or len(payload) != 8*size:
            raise ValueError('unexpected binary64 array payload')
        values = list(struct.unpack('<'+'d'*size,payload))
        if not all(math.isfinite(x) for x in values):
            raise ValueError('nonfinite array coefficient')
        arrays[name] = values
    arrays['A'] = [arrays['A'][27*j:27*(j+1)] for j in range(13)]
    if arrays['uj'] != [-1.5+j*.25 for j in range(13)]:
        raise ValueError('unexpected pole nodes')
    if not all(a<b for a,b in zip(arrays['um'],arrays['um'][1:])):
        raise ValueError('unordered spline centres')
    for name,offset in [('hu',515),('h',3375)]:
        opcode,value=by_offset[offset]
        if opcode!='BINFLOAT' or not math.isfinite(value) or value<=0:
            raise ValueError('invalid spacing')
        arrays[name]=value
    arrays.update(N=13,ext=2)
    arrays['schema']='mumble_distinct_pole_map_v1'
    arrays['domain']=[-1.,1.]
    arrays['provenance']={
        'source':'User-pasted map_n13e.pkl hexadecimal payload, manually transcribed verbatim',
        'source_hex_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'pickle_sha256':BINARY_SHA256,'pickle_bytes':len(blob),
        'method':'pinned bytes + pickletools parse + struct literal extraction; no pickle execution',
        'dtype':'little-endian binary64','array_order':'C',
        'certificate_status':'unverified_user_checkpoint_not_a_runtime_physical_certificate',
        'rounding_policy':'Preserve exact stored binary64 A, uj, um, hu; do not replace hu by 1/12 or normalize columns',
    }
    return arrays


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--hex',type=Path,default=HERE/'map_n13e.hex')
    p.add_argument('--out',type=Path,default=HERE/'map_n13e.json')
    args=p.parse_args()
    text=args.hex.read_text(); data=decode_hex(text)
    encoded=json.dumps(data,indent=2,allow_nan=False)+'\n'
    if args.out.exists() and args.out.read_text()!=encoded:
        raise ValueError('refusing to replace different existing map')
    args.out.write_text(encoded)
    # These are finite data checks, not a physical or approximation certificate.
    print(json.dumps({'N':data['N'],'columns':len(data['um']),
        'hu':data['hu'],'binary_sha256':BINARY_SHA256,
        'json_sha256':hashlib.sha256(encoded.encode()).hexdigest(),
        'max_column_sum_deviation':max(abs(sum(row[j] for row in data['A'])-1) for j in range(27))},indent=2))


if __name__=='__main__':main()
