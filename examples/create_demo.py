"""Create a synthetic text fixture and reviewed translation plan, not a real mod."""
import argparse
import json
from pathlib import Path
import struct
import sys
import zipfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/ark-asa-localization/scripts'))
import asa_core


def create_demo(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Output must not exist: ' + str(output))
    source = output / 'source'
    source.mkdir(parents=True)
    text = b'\0' * 17 + struct.pack('<I', 8) + b'\0' + struct.pack('<i', 0)
    text += struct.pack('<i', 33) + b'A' * 32 + b'\0' + struct.pack('<i', 5) + b'Help\0'
    (source / 'HUD.uasset').write_bytes(text)
    # An identification fixture only; it is not a valid cooked or playable mod.
    plugin = {'FileVersion': 3, 'VersionName': 'synthetic-v1', 'FriendlyName': 'Synthetic Demo', 'Description': 'Synthetic test fixture &cf_ugcID=123456'}
    (source / 'Demo.uplugin').write_text(json.dumps(plugin, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(output / 'source.zip', 'x', compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(source.iterdir()):
            archive.writestr(path.name, path.read_bytes())
    plan = asa_core.inventory(source)
    row = next(row for row in plan['entries'] if row['kind'] == 'ftext-base')
    row.update(display=True, translation='帮助', review_note='Synthetic Help label explicitly created for this demo; observed namespace/key only')
    (output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = asa_core.inspect_zip(output / 'source.zip')
    (output / 'inspection.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'synthetic_only': True, 'asa_runtime_tested': False}, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New demo work directory; never overwrites')
    args = parser.parse_args()
    try:
        create_demo(args.output)
        return 0
    except (OSError, ValueError) as error:
        print('Demo failed: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
