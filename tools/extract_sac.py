"""Dump SAC's ISO, extract IMAGE.ZIP, and checksum-verify/unpack its HIG WADs."""
import argparse
import hashlib
import json
import re
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from archive_support import iso_files, decompress, u32, write_new


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path, data):
    write_new(path, (json.dumps(data, indent=2) + '\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iso', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        parser.error('Choose a new or empty output folder; existing files will not be overwritten.')
    root.mkdir(parents=True, exist_ok=True)
    report = dict(iso=str(args.iso.resolve()), files=[], zip_entries=[], archives=[], errors=[])
    paths = []
    with args.iso.open('rb') as source:
        for rel, offset, size in iso_files(source, args.iso.stat().st_size):
            dest = root / 'disc' / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            source.seek(offset)
            digest = hashlib.sha256()
            remaining = size
            with dest.open('xb') as out:
                while remaining:
                    block = source.read(min(1024*1024, remaining))
                    if not block:
                        raise ValueError('Unexpected ISO EOF')
                    out.write(block)
                    digest.update(block)
                    remaining -= len(block)
            report['files'].append(dict(path=rel.as_posix(), iso_offset=offset, size=size, sha256=digest.hexdigest()))
            if len(report['files']) % 25 == 0:
                print(f"Dumped {len(report['files'])} disc files...", flush=True)
    print(f"Dumped {len(report['files'])} disc files", flush=True)
    with zipfile.ZipFile(root / 'disc/IMAGE.ZIP') as archive:
        for entry in archive.infolist():
            rel = PurePosixPath(entry.filename)
            if rel.is_absolute() or '..' in rel.parts or '\\' in entry.filename or ':' in entry.filename:
                raise ValueError(f'Unsafe ZIP filename: {entry.filename}')
            if entry.is_dir():
                continue
            data = archive.read(entry)  # zipfile verifies each entry's CRC.
            write_new(root / 'image' / rel, data)
            report['zip_entries'].append(dict(path=rel.as_posix(), size=len(data), compressed_size=entry.compress_size, zip_crc32=f'{entry.CRC:08x}', sha256=sha(data)))
            if rel.suffix.lower() != '.wad':
                continue
            try:
                payload, crc = decompress(data)
                full = data[:0xc0] + payload
                dest = root / 'unpacked' / rel
                write_new(dest / 'header.bin', data[:0xc0])
                write_new(dest / 'payload.bin', payload)
                pointers = [(slot, u32(data, slot)) for slot in range(4, 0x38, 4) if u32(data, slot)]
                bounds = sorted(set(value for _, value in pointers))
                if any(value < 0xc0 or value >= len(full) for value in bounds):
                    raise ValueError('Section pointer outside reconstructed WAD')
                sections = []
                for index, start in enumerate(bounds):
                    end = bounds[index+1] if index+1 < len(bounds) else len(full)
                    slots = [slot for slot, value in pointers if value == start]
                    name = f'sections/{start:08x}_slot_{slots[0]:02x}.bin'
                    section = full[start:end]
                    write_new(dest / name, section)
                    sections.append(dict(file=name, header_slots=slots, offset=start, size=len(section), sha256=sha(section)))
                info = dict(path=rel.as_posix(), compressed_size=len(data)-0xc0, payload_size=len(payload), crc32=f'{crc:08x}', crc_verified=True, payload_sha256=sha(payload), source_name=data[0x48:0xc0].split(b'\0')[0].decode('ascii', errors='replace'), sections=sections)
                save_json(dest / 'manifest.json', info)
                report['archives'].append(info)
                for match in re.finditer(rb'[A-Za-z]:\\[ -~]{5,}', payload):
                    paths.append(dict(archive=rel.as_posix(), payload_offset=match.start(), reconstructed_offset=match.start()+0xc0, source_path=match.group().decode('ascii')))
                print(f'OK {rel}: {len(payload):,} bytes, {len(sections)} sections, CRC {crc:08x}', flush=True)
            except Exception as exc:
                report['errors'].append(dict(path=rel.as_posix(), error=str(exc)))
                print(f'ERROR {rel}: {exc}', flush=True)
    save_json(root / 'manifest.json', report)
    save_json(root / 'embedded_paths.json', paths)
    print(f"Extracted {len(report['zip_entries'])} ZIP entries; verified {len(report['archives'])} WADs; {len(report['errors'])} errors", flush=True)
    return bool(report['errors'])


if __name__ == '__main__':
    raise SystemExit(main())
