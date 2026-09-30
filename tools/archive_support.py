"""Extract a PS2 Secret Agent Clank ISO and checksum-verify HIG/TJZIP archives.
Uses electrogecko's reviewed TJZIP token decoder (tools/upstream/tjzip_dump.py).
"""
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).parent / 'upstream'))
import tjzip_dump as tj


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def iso_files(stream, iso_size):
    stream.seek(16 * 2048)
    pvd = stream.read(2048)
    if pvd[:7] != b'\x01CD001\x01':
        raise ValueError('Expected ISO9660 primary volume descriptor')
    seen = set()
    def walk(record, parent):
        offset, size = u32(record, 2) * 2048, u32(record, 10)
        if offset + size > iso_size or offset in seen:
            raise ValueError('Invalid/cyclic ISO directory')
        seen.add(offset)
        stream.seek(offset)
        data = stream.read(size)
        pos = 0
        while pos < len(data):
            n = data[pos]
            if not n:
                pos = (pos // 2048 + 1) * 2048
                continue
            record = data[pos:pos+n]
            pos += n
            if len(record) < 34:
                raise ValueError('Truncated directory record')
            raw = record[33:33+record[32]]
            if raw in (b'\0', b'\1'):
                continue
            name = raw.decode('ascii').split(';')[0]
            if name in ('', '.', '..') or any(c in name for c in '/\\:'):
                raise ValueError('Unsafe ISO filename')
            path = parent / name
            if record[25] & 2:
                yield from walk(record, path)
            else:
                off, length = u32(record, 2) * 2048, u32(record, 10)
                if off + length > iso_size or record[25] & 0x80:
                    raise ValueError('Out of bounds or multi-extent file')
                yield path, off, length
    return list(walk(pvd[156:156+pvd[156]], Path()))


def decompress(blob):
    if len(blob) < 0xc0 or blob[:4] != b'HIG!':
        raise ValueError('Not a HIG archive')
    expected, packed = u32(blob, 0x40), u32(blob, 0x44)
    if packed != len(blob)-0xc0 or expected > 512*1024*1024:
        raise ValueError('Invalid archive sizes')
    comp = blob[0xc0:]
    out = bytearray(expected)
    ip, op, crc = tj.tjzip_parse_raw(comp, 0, out, 0, crc=0, crc_table=None)
    while ip < len(comp):
        ip, op, crc, post = tj.tjzip_parse_dict(comp, ip, out, op, crc=0, crc_table=None)
        if ip == len(comp) and op == expected:
            break
        if post == 0:
            ip, op, crc = tj.tjzip_parse_raw(comp, ip, out, op, crc=0, crc_table=None)
        elif post in (1, 2):
            if ip+post > len(comp) or op+post > expected:
                raise ValueError('Literal overrun')
            out[op:op+post] = comp[ip:ip+post]
            ip += post
            op += post
    if ip != len(comp) or op != expected:
        raise ValueError(f'Length mismatch: input {ip}/{len(comp)}, output {op}/{expected}')
    actual = zlib.crc32(out, 0xffffffff)
    if actual != u32(blob, 0x38):
        raise ValueError(f'CRC mismatch: {actual:08x} != {u32(blob, 0x38):08x}')
    return bytes(out), actual


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == data:
            return
        raise FileExistsError(f'Refusing to replace different file: {path}')
    with path.open('xb') as f:
        f.write(data)

