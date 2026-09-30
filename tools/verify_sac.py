"""Verify saved disc, ZIP entries, WAD payloads, and section slices."""
import hashlib
import json
import sys
import zipfile
import zlib
from pathlib import Path
from archive_support import u32


def main():
    root = Path(sys.argv[1])
    report = json.loads((root / 'manifest.json').read_text())
    assert not report['errors'], report['errors']
    with Path(report['iso']).open('rb') as iso:
        for item in report['files']:
            iso.seek(item['iso_offset'])
            digest = hashlib.sha256()
            remaining = item['size']
            with (root / 'disc' / item['path']).open('rb') as saved:
                while remaining:
                    block = iso.read(min(1024*1024, remaining))
                    assert block and saved.read(len(block)) == block, item['path']
                    digest.update(block)
                    remaining -= len(block)
                assert not saved.read(1)
            assert digest.hexdigest() == item['sha256']
    with zipfile.ZipFile(root / 'disc/IMAGE.ZIP') as archive:
        for item in report['zip_entries']:
            data = (root / 'image' / item['path']).read_bytes()
            assert data == archive.read(item['path'])
            assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256']
    sections = 0
    for item in report['archives']:
        dest = root / 'unpacked' / item['path']
        original = (root / 'image' / item['path']).read_bytes()
        header = (dest / 'header.bin').read_bytes()
        payload = (dest / 'payload.bin').read_bytes()
        assert header == original[:0xc0]
        assert len(payload) == u32(header, 0x40) == item['payload_size']
        assert zlib.crc32(payload, 0xffffffff) == u32(header, 0x38) == int(item['crc32'], 16)
        assert hashlib.sha256(payload).hexdigest() == item['payload_sha256']
        full = header + payload
        for section in item['sections']:
            data = (dest / section['file']).read_bytes()
            assert data == full[section['offset']:section['offset']+section['size']]
            assert hashlib.sha256(data).hexdigest() == section['sha256']
            sections += 1
    result = dict(disc_files=len(report['files']), zip_entries=len(report['zip_entries']), wads=len(report['archives']), sections=sections, errors=0)
    (root / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
