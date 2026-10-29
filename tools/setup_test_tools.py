"""Explicitly download two pinned Windows test tools from upstream, never execute them.

This helper is optional. Ordinary verification/build/package commands never download
tools. The executables are external dependencies, excluded from skill releases.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_EXECUTABLE = 32 * 1024 * 1024
PINNED = {
    'repak': {
        'version': '0.2.3',
        'source_url': 'https://github.com/trumank/repak/releases/tag/v0.2.3',
        'download_url': 'https://github.com/trumank/repak/releases/download/v0.2.3/repak_cli-x86_64-pc-windows-msvc.zip',
        'archive_sha256': '6720d602144d75df477a99d5bedb6ea780997546afc335901d4937cafeaa73fa',
        'sha256': 'fcd538e5994b9bb833622d425ae346f4e0692f02d4b0025114a559f9b6286022',
        'filename': 'repak.exe',
    },
    'unreal_locres': {
        'version': 'release-1.1.1',
        'source_url': 'https://github.com/akintos/UnrealLocres/releases/tag/1.1.1',
        'download_url': 'https://github.com/akintos/UnrealLocres/releases/download/1.1.1/UnrealLocres.exe',
        'sha256': 'b961927f92a8bca928d378a8430e5ea36fed300500b228b184b8d6b61ebb22a1',
        'filename': 'UnrealLocres.exe',
    },
}


def checked_digest(data, expected, label):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(label + ' SHA-256 mismatch: expected ' + expected + ', got ' + actual)
    return data


def extract_payload(data, filename):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        candidates = [info for info in archive.infolist() if PurePosixPath(info.filename.replace('\\', '/')).name == filename]
        if len(candidates) != 1 or candidates[0].file_size > MAX_EXECUTABLE:
            raise ValueError('Expected one bounded executable member: ' + filename)
        # Read one member into memory, never extract archive paths to disk.
        return archive.read(candidates[0])


def download(url):
    request = Request(url, headers={'User-Agent': 'ark-asa-localization-source-tests'})
    with urlopen(request, timeout=60) as response:
        if urlsplit(response.geturl()).scheme != 'https':
            raise ValueError('Download redirected away from HTTPS')
        data = response.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError('Tool download exceeds size limit')
        return data


def setup(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Output must not exist: ' + str(output))
    skill = Path(__file__).resolve().parents[1] / 'skills'
    if output.is_relative_to(skill):
        raise ValueError('External tools must not be placed inside skills/')
    payloads = {}
    for name, record in PINNED.items():
        data = download(record['download_url'])
        if 'archive_sha256' in record:
            checked_digest(data, record['archive_sha256'], name + ' archive')
            data = extract_payload(data, record['filename'])
        payloads[name] = checked_digest(data, record['sha256'], name)
    # No destination writes until both downloads are verified. Never run tools here.
    output.mkdir(parents=True)
    manifest = {}
    for name, record in PINNED.items():
        path = output / record['filename']
        with path.open('xb') as stream:
            stream.write(payloads[name])
        manifest[name] = {key: record[key] for key in ('version', 'source_url', 'sha256')}
        manifest[name]['path'] = str(path)
    manifest_path = output / 'tools.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New external tools directory; never overwrites')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('These pinned executables are for Windows x64')
    try:
        manifest = setup(args.output)
        print(json.dumps({'tools_manifest': str(manifest), 'executed': False}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print('Tool setup failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
