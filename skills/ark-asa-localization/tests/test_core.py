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
        # Percent prose is not a printf specifier, with or without a space before the word.
        self.assertEqual(validate('10% damage', '10% 伤害'), [])
        self.assertEqual(validate('100%damage', '100%伤害'), [])
        self.assertEqual(validate('100%faster', '快 100%'), [])
        self.assertEqual(validate('Save 100%%', '保存 100%%'), [])
        self.assertEqual(validate('+10 armor', '+10 护甲'), [])
        self.assertEqual(validate('Use {{Item}} and {Item}', '使用 {{Item}} 和 {Item}'), [])
        self.assertEqual(validate('Deal %d damage to %s', '对 %s 造成 %d 伤害'), [])
        self.assertEqual(validate('%1$s %.2f', '%1$s %.2f'), [])
        self.assertEqual(validate('<A>1</A><B>2</B>', '<A>1</A><B>2</B>'), [])
        self.assertEqual(validate('Help', '帮助'), [])
        for source, translated in [
            ('+10% damage', '+20% 伤害'), ('+10 armor', '10 护甲'), ('-5 health', '5 生命'),
            ('10% damage', '10％伤害'), ('10% and 10%', '10%'),
            ('Hello %s', '你好'), ('player1%s', '玩家1'), ('Deal %d damage', '造成伤害'),
            ('{Fire} + {Targeting}', '{Fire}'), ('Use {Item}', '使用 Item'),
            ('<RichColor Color="1,0,0">Hi</>', '你好'), ('<A>1</A><B>2</B>', '<B>2</B><A>1</A>'),
            ('Line1\r\n\r\nLine2', '行1\n行2'), ('Help', '  '), ('Help', '')]:
            self.assertTrue(validate(source, translated), source)
        self.assertEqual(validate('Help', '   '), ['empty translation'])

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
        self.assertEqual(self.core.parse_jsonc('{\r\n"a":"quote \\" // not comment", // tail\r\n"b":1,\r\n}'),
                         {'a':'quote " // not comment', 'b':1})
        with self.assertRaises(ValueError): self.core.parse_jsonc('{"x":1/*x*/2}')
        with self.assertRaises(ValueError): self.core.parse_jsonc('{"x":1/*missing end')
        with self.assertRaises(ValueError): self.core.parse_jsonc('{"x":1 /* "unterminated}')

    def test_text_candidates_cover_keyed_constants_and_reject_non_display_paths(self):
        import json
        import asa_resources
        src = self.work / 'cooked'
        src.mkdir()
        keyed = struct.pack('<I', 0) + b'\0' + fs('UI') + fs('B' * 32) + fs('中文提示')
        path_text = struct.pack('<I', 8) + b'\0' + fs('') + fs('C' * 32) + fs('/Game/PrimalEarth/UI/HUD')
        help_text = struct.pack('<I', 8) + b'\0' + fs('') + fs('A' * 32) + fs('Help')
        (src / 'HUD.uasset').write_bytes(b'\0' * 17 + keyed + path_text + help_text)
        textconst = b'\x29\x01\x1fToggle Cannon Stance\x00\x1f' + b'D' * 32 + b'\x00\x1fUI\x00'
        (src / 'BP.uasset').write_bytes(textconst)
        (src / 'Legacy.uasset').write_bytes(bytes.fromhex('c1832a9e') + b'rest')
        wide = struct.pack('<i', -4) + '中文'.encode('utf-16-le') + b'\0\0'
        (src / 'Wide.uasset').write_bytes(wide)
        report = self.core.inventory(src)
        layouts = {item['path']: item['layout'] for item in report['files']}
        self.assertEqual(layouts['Legacy.uasset'], 'legacy-unreal-header')
        self.assertEqual(layouts['HUD.uasset'], 'unclassified-cooked-chunk')
        self.assertFalse(any(row['source'] == '中文' and row['kind'] in ('fstring', 'stringconst') for row in report['entries']))
        constant = next(row for row in report['entries'] if row['kind'] == 'textconst')
        self.assertEqual((constant['source'], constant['key'], constant['namespace']), ('Toggle Cannon Stance', 'D' * 32, 'UI'))
        rows = [row for row in report['entries'] if row['path'] == 'HUD.uasset']
        chinese = next(row for row in rows if row['kind'] == 'ftext-base' and row['source'] == '中文提示')
        chinese = dict(chinese, display=True, translation='提示', review_note='Unicode HUD label')
        with self.assertRaises(ValueError):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [chinese]})
        chinese['source_hash'] = 0x12345678
        with self.assertRaises(ValueError):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [chinese]})
        chinese['source_hash_origin'] = 'synthetic observed locres hash'
        selected = self.core.reviewed_records(src, {'schema': 1, 'entries': [chinese]})
        self.assertEqual(selected[0]['source_hash'], 0x12345678)
        self.assertEqual(asa_resources.fingerprint(selected[0]), 0x12345678)
        game = next(row for row in rows if row['kind'] == 'ftext-base' and row['source'].startswith('/Game/'))
        game = dict(game, display=True, translation='界面', review_note='not display text')
        with self.assertRaisesRegex(ValueError, 'Resource path'):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [game]})
        nested = next(row for row in rows if row['kind'] == 'fstring' and row['source'] == 'Help')
        nested = dict(nested, display=True, translation='帮助', review_note='nested bytes')
        with self.assertRaisesRegex(ValueError, 'nested string'):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [nested]})
        nested_const = next(row for row in report['entries'] if row['path'] == 'BP.uasset' and row['kind'] == 'stringconst' and row['source'] == 'Toggle Cannon Stance')
        nested_const = dict(nested_const, display=True, translation='切换火炮姿态', review_note='nested constant')
        with self.assertRaisesRegex(ValueError, 'nested string'):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [nested_const]})
        help_row = next(row for row in rows if row['kind'] == 'ftext-base' and row['source'] == 'Help')
        unfinished = dict(help_row, display=True)
        with self.assertRaisesRegex(ValueError, 'require a translation'):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [unfinished]})
        mismatched = dict(help_row, display=True, translation='帮助', review_note='HUD label', source_hash=1, source_hash_origin='hand filled')
        with self.assertRaisesRegex(ValueError, 'case-verified CRC32'):
            self.core.reviewed_records(src, {'schema': 1, 'entries': [mismatched]})
        matched = dict(help_row, display=True, translation='帮助', review_note='HUD label',
                       source_hash=asa_resources.source_hash('Help'), source_hash_origin='recomputed ASCII CRC')
        self.assertEqual(self.core.reviewed_records(src, {'schema': 1, 'entries': [matched]})[0]['source'], 'Help')
        archive = self.work / 'mod.zip'
        plugin = json.dumps({'Description': 'cf_ugcID=123456&next=1', 'FriendlyName': 'Example', 'VersionName': 'v1', 'SDKVersion': 1}).encode()
        no_sdk = json.dumps({'Description': 'cf_ugcID=44', 'FriendlyName': 'Partial'}).encode()
        longer = json.dumps({'Description': 'cf_ugcID=123456789', 'FriendlyName': 'Longer', 'SDKVersion': 2, 'VersionName': 'v2'}).encode()
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('Example/Example.uplugin', plugin)
            zipped.writestr('Example/Partial.uplugin', no_sdk)
            zipped.writestr('Example/Longer.uplugin', longer)
            zipped.writestr('Example/Content/Paks/Windows/mod.utoc', b'utoc')
            zipped.writestr('Example/Content/Paks/Windows/mod.ucas', b'ucas')
        inspected = self.core.inspect_zip(archive)
        by_path = {item['path']: item for item in inspected['plugins']}
        self.assertEqual(by_path['Example/Example.uplugin']['mod_id'], 123456)
        partial = by_path['Example/Partial.uplugin']
        self.assertEqual((partial['mod_id'], partial['sdk']), (44, None))
        self.assertEqual(by_path['Example/Longer.uplugin']['mod_id'], 123456789)
        self.assertTrue(inspected['has_iostore'])
        self.assertTrue(inspected['asa_identity_observed'])
        self.assertFalse(inspected['runtime_tested'])
        with self.assertRaisesRegex(ValueError, 'unpacked size'):
            self.core.inspect_zip(archive, max_unpacked=4)
        encrypted = self.work / 'encrypted.zip'
        with zipfile.ZipFile(encrypted, 'w') as zipped:
            zipped.writestr('item.txt', b'hello')
        blob = bytearray(encrypted.read_bytes())
        blob[6] |= 0x1
        central = blob.find(b'PK\x01\x02')
        blob[central + 8] |= 0x1
        encrypted.write_bytes(blob)
        with self.assertRaisesRegex(ValueError, 'Encrypted'):
            self.core.inspect_zip(encrypted)


if __name__ == '__main__': unittest.main()
