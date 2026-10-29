"""Build a deterministic source-only skill ZIP. No network access or game writes."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

SKILL_NAME = 'ark-asa-localization'
TEXT_SUFFIXES = {'.md', '.py', '.ps1', '.json', '.yaml', '.yml', '.txt'}
DENIED_PARTS = {'__pycache__', '.git', '.venv', 'node_modules'}


def release_files(root):
    root = Path(root).resolve()
    skill = root / 'skills' / SKILL_NAME
    if not (skill / 'SKILL.md').is_file():
        raise ValueError('Missing skill entrypoint')
    files = {}
    for path in sorted(skill.rglob('*')):
        relative = path.relative_to(skill)
        if path.is_symlink():
            raise ValueError('Release symlinks are not allowed: ' + str(relative))
        if any(part in DENIED_PARTS for part in relative.parts):
            raise ValueError('Release contains cache/vendor directory: ' + str(relative))
        if not path.is_file():
            continue
        if path.name != 'LICENSE' and path.suffix.lower() not in TEXT_SUFFIXES:
            raise ValueError('Release contains unapproved asset: ' + str(relative))
        data = path.read_bytes()
        data.decode('utf-8-sig')
        if b'\x00' in data or data.startswith(b'MZ'):
            raise ValueError('Release contains binary data: ' + str(relative))
        files[SKILL_NAME + '/' + relative.as_posix()] = data
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing regular root license document: ' + name)
        data = path.read_bytes()
        data.decode('utf-8-sig')
        member = SKILL_NAME + '/' + name
        if member in files and files[member] != data:
            raise ValueError('Root and skill license documents disagree: ' + name)
        files[member] = data
    return files


def build_release(root, output):
    output = Path(output).resolve()
    checksum = output.with_suffix(output.suffix + '.sha256')
    if output.exists() or checksum.exists():
        raise FileExistsError('Release output or checksum already exists: ' + str(output))
    files = release_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stored ZIP avoids zlib-version differences; these are small source files.
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or archive.namelist() != sorted(files):
            raise ValueError('Release ZIP integrity verification failed')
        for name, expected in files.items():
            if archive.read(name) != expected:
                raise ValueError('Release ZIP content mismatch: ' + name)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with checksum.open('x', encoding='ascii', newline='\n') as stream:
        stream.write(digest + '  ' + output.name + '\n')
    return {'file': str(output), 'sha256': digest, 'members': len(files), 'bytes': output.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1], help='Repository root')
    parser.add_argument('--output', type=Path, required=True, help='New ZIP path; never overwrites')
    args = parser.parse_args()
    try:
        print(json.dumps(build_release(args.root, args.output), ensure_ascii=True, indent=2))
        return 0
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile) as error:
        print('Release failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
