import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def fs(s):
    b = (s + '\0').encode('utf-16-le' if not s.isascii() else 'ascii')
    return struct.pack('<i', -len(b)//2 if not s.isascii() else len(b)) + b


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('asa_core'), 'Core implementation missing')
        import asa_core
        self.core = asa_core
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def test_zip_traversal_case_collision_symlink_and_crc_are_rejected(self):
        for index, entries in enumerate([
                [('A/../../outside', b'bad')], [('C:/outside', b'bad')], [('A\\..\\outside', b'bad')],
                [('A/file', b'x'), ('a/FILE', b'y')], [('CON.txt', b'bad')]]):
            archive = self.work / f'bad{index}.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                for name, data in entries: z.writestr(name, data)
            with self.assertRaises(ValueError): self.core.inspect_zip(archive)
        archive = self.work / 'link.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            info = zipfile.ZipInfo('link')
            info.external_attr = 0o120777 << 16
            z.writestr(info, '/outside')
        with self.assertRaises(ValueError): self.core.inspect_zip(archive)
        archive = self.work / 'crc.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as z: z.writestr('item', b'unique_marker')
        data = archive.read_bytes().replace(b'unique_marker', b'broken_marker')
        archive.write_bytes(data)
        with self.assertRaises((ValueError, zipfile.BadZipFile)): self.core.inspect_zip(archive)
        self.assertFalse((self.work / 'outside').exists())

    def test_zip_identifies_plugin_and_preserves_source(self):
        archive = self.work / 'mod.zip'
        import json
        plugin = json.dumps({'Description':'Example &cf_ugcID=123456', 'FriendlyName':'Example', 'VersionName':'v1', 'SDKVersion':1}).encode()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('Example/Example.uplugin', plugin)
            z.writestr('Example/Content/Paks/Windows/mod.utoc', b'-==--==--==--==-')
        original = archive.read_bytes()
        report = self.core.inspect_zip(archive, self.work / 'extracted')
        self.assertEqual(report['plugins'][0]['mod_id'], 123456)
        self.assertEqual(report['plugins'][0]['version'], 'v1')
        self.assertEqual((self.work / 'extracted/Example/Example.uplugin').read_bytes(), plugin)
        self.assertEqual(archive.read_bytes(), original)
        with self.assertRaises(FileExistsError): self.core.inspect_zip(archive, self.work / 'extracted')

    def test_overlapping_ftext_scan_preserves_guid_namespace_unicode_and_offsets(self):
        prefix = b'\0' * 17
        text = struct.pack('<I', 8) + b'\0' + fs('') + fs('A' * 32) + fs('Toggle Cannon Stance')
        unicode_text = struct.pack('<I', 0) + b'\0' + fs('UI') + fs('B' * 32) + fs('中文提示')
        records = self.core.scan_bytes(prefix + text + unicode_text, 'HUD.uasset')
        keyed = [r for r in records if r['kind'] == 'ftext-base']
        self.assertTrue(any(r['offset'] == 17 and r['key'] == 'A' * 32 and r['namespace'] == '' for r in keyed))
        self.assertTrue(any(r['source'] == '中文提示' for r in keyed))
        self.assertTrue(all(not r['display'] for r in records))

    def test_translation_guards_numbers_percent_printf_tags_and_newlines(self):
        validate = self.core.translation_errors
        self.assertEqual(validate('Adds +10% damage reduction.', '获得 +10% 伤害减免。'), [])
        for source, translated in [
            ('+10% damage', '+20% 伤害'), ('Hello %s', '你好'),
            ('{Fire} + {Targeting}', '{Fire}'), ('<RichColor Color="1,0,0">Hi</>', '你好'),
            ('Line1\r\n\r\nLine2', '行1\n行2')]:
            self.assertTrue(validate(source, translated), source)

    def test_only_reviewed_entries_are_selected_and_source_changes_rejected(self):
        data = b'\x1fRotateAttack\0' + struct.pack('<I', 0) + b'\0' + fs('') + fs('A'*32) + fs('Help')
        src = self.work / 'original'
        src.mkdir()
        (src / 'HUD.uasset').write_bytes(data)
        records = self.core.inventory(src)['entries']
        help_row = next(r for r in records if r['kind'] == 'ftext-base' and r['source'] == 'Help')
        help_row.update(display=True, translation='帮助', review_note='Visible HUD label')
        plan = {'schema':1, 'entries':records}
        selected = self.core.reviewed_records(src, plan)
        self.assertEqual({r['source'] for r in selected}, {'Help'})
        self.assertEqual(selected[0]['key'], 'A'*32)
        (src / 'HUD.uasset').write_bytes(data + b'changed')
        with self.assertRaises(ValueError): self.core.reviewed_records(src, plan)

    def test_jsonc_comment_parser_preserves_quoted_delimiters_and_rejects_malformed(self):
        self.assertEqual(self.core.parse_jsonc('{"x":"keep,] and ,} // /*",/*note*/"y":[1,],}'),
                         {'x':'keep,] and ,} // /*', 'y':[1]})
        with self.assertRaises(ValueError): self.core.parse_jsonc('{"x":1/*x*/2}')
        with self.assertRaises(ValueError): self.core.parse_jsonc('{"x":1/*missing end')


if __name__ == '__main__': unittest.main()
