import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('asa_resources'), 'Resource implementation missing')
        import asa_resources
        self.r = asa_resources

    def test_key_hash_and_source_hash_match_case_golden_vectors(self):
        self.assertEqual(self.r.key_hash(''), 0)
        self.assertEqual(self.r.key_hash('Awesome Teleporter'), 248634034)
        self.assertEqual(self.r.key_hash('UI'), 1066470515)
        self.assertEqual(self.r.source_hash('Awesome Teleporter'), 1145908353)
        self.assertEqual(self.r.source_hash('Help'), 3982240912)
        # Non-ASCII source fingerprints need an observed source_hash until verified.
        with self.assertRaises(ValueError): self.r.source_hash('新文本😀')
        observed = dict(source='中文提示', source_hash=0x12345678)
        self.assertEqual(self.r.fingerprint(observed), 0x12345678)
        with self.assertRaisesRegex(ValueError, 'case-verified CRC32'):
            self.r.fingerprint(dict(source='Help', source_hash=1))
        with self.assertRaisesRegex(ValueError, 'Invalid source_hash'):
            self.r.fingerprint(dict(source='Help', source_hash=True))
        self.assertEqual(self.r.fingerprint(dict(source='Awesome Teleporter', source_hash=1145908353)), 1145908353)

    def test_locres_roundtrip_and_rejects_truncation(self):
        records = [dict(namespace='', key='A'*32, source='Hello', translation='你好😀', evidence='observed-key'),
                   dict(namespace='UI', key='B'*32, source='Hello', translation='您好', evidence='observed-key')]
        binary = self.r.encode_locres(records, native=False)
        parsed = self.r.decode_locres(binary)
        self.assertEqual(parsed[('', 'A'*32)]['text'], '你好😀')
        self.assertEqual(parsed[('UI', 'B'*32)]['text'], '您好')
        self.assertEqual(parsed[('', 'A'*32)]['source_hash'], self.r.source_hash('Hello'))
        self.assertEqual(parsed[('', 'A'*32)]['namespace_hash'], 0)
        self.assertEqual(parsed[('', 'A'*32)]['key_hash'], self.r.key_hash('A'*32))
        self.assertEqual(parsed[('UI', 'B'*32)]['namespace_hash'], self.r.key_hash('UI'))
        native = self.r.decode_locres(self.r.encode_locres(records, native=True))
        self.assertEqual({item['text'] for item in native.values()}, {'Hello'})
        unicode_row = dict(namespace='UI', key='K', source='中文提示', translation='提示',
                           source_hash=0x12345678, evidence='observed-key')
        foreign = self.r.decode_locres(self.r.encode_locres([unicode_row], native=False))
        self.assertEqual(foreign[('UI', 'K')]['text'], '提示')
        self.assertEqual(foreign[('UI', 'K')]['source_hash'], 0x12345678)
        original = self.r.decode_locres(self.r.encode_locres([unicode_row], native=True))
        self.assertEqual(original[('UI', 'K')]['text'], '中文提示')
        for end in [0, 16, 28, len(binary)-1]:
            with self.assertRaises(ValueError): self.r.decode_locres(binary[:end])
        raw = bytearray(binary)
        raw[16] = 2
        with self.assertRaisesRegex(ValueError, 'LocRes v3'):
            self.r.decode_locres(bytes(raw))
        ui_hash = __import__('struct').pack('<I', self.r.key_hash('UI'))
        tampered = bytearray(binary)
        index = tampered.find(ui_hash)
        self.assertGreaterEqual(index, 0)
        tampered[index] ^= 0xFF
        with self.assertRaisesRegex(ValueError, 'Identity fingerprint mismatch'):
            self.r.decode_locres(bytes(tampered))
        duplicate = [dict(records[1]), dict(records[1])]
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.r.encode_locres(duplicate)

    def test_explicit_identities_are_not_replaced_with_global_crc(self):
        rows = [dict(namespace='', key='A'*32, source='Settings', translation='设置', kind='ftext-base'),
                dict(source='Cannon mode', translation='火炮模式', kind='stringconst')]
        exact = self.r.make_identities(rows, crc_candidates=False, aliases=False)
        self.assertEqual(len(exact), 1)
        candidate = self.r.make_identities(rows, crc_candidates=True, aliases=True)
        self.assertEqual(len(candidate), 5)
        self.assertEqual(len([r for r in candidate if r['source'] == 'Settings']), 2)
        crc = [r for r in candidate if r['evidence'] == 'source-crc-candidate']
        self.assertEqual({r['namespace'] for r in crc}, {'Content', 'GraphLiteral', ''})
        self.assertEqual({r['key'] for r in crc}, {str(self.r.source_hash('Cannon mode'))})
        unkeyed = [dict(source='Cannon mode', translation='火炮模式', kind='stringconst')]
        with self.assertRaisesRegex(ValueError, 'No identities'):
            self.r.make_identities(unkeyed, crc_candidates=False)
        with self.assertRaisesRegex(ValueError, 'Identity conflict'):
            self.r.make_identities([
                dict(source='Open', translation='打开', kind='stringconst'),
                dict(source='Open', translation='开启', kind='stringconst'),
            ], crc_candidates=True)

    def test_conflicting_translation_for_same_identity_is_rejected(self):
        rows = [dict(namespace='UI', key='same', source='Open', translation=t, kind='ftext-base') for t in ['打开', '开放']]
        with self.assertRaises(ValueError): self.r.make_identities(rows)
        changed_source = [dict(namespace='UI', key='same', source=source, translation='打开', kind='ftext-base')
                          for source in ('Open', 'Opened')]
        with self.assertRaisesRegex(ValueError, 'Identity conflict'):
            self.r.make_identities(changed_source)
        alias_conflict = [dict(namespace='', key='same', source='Open', translation='打开', kind='ftext-base'),
                          dict(namespace='GraphLiteral', key='same', source='Open', translation='开启', kind='ftext-base')]
        with self.assertRaisesRegex(ValueError, 'Identity conflict'):
            self.r.make_identities(alias_conflict, aliases=True)

    def test_observed_identity_takes_precedence_over_an_earlier_alias(self):
        rows = [dict(namespace=ns, key='same', source='Open', translation='打开', kind='ftext-base')
                for ns in ('', 'GraphLiteral')]
        for order in (rows, list(reversed(rows))):
            result = self.r.make_identities(order, aliases=True)
            self.assertEqual({(r['namespace'], r['key']): r['evidence'] for r in result},
                             {('', 'same'): 'observed-key', ('GraphLiteral', 'same'): 'observed-key'})

    def test_metadata_uses_matching_target_and_cultures(self):
        value = self.r.decode_metadata(self.r.encode_metadata('Example123'))
        self.assertEqual(value, {'native':'en', 'resource':'en/Example123.locres', 'cultures':['en','zh','zh-Hans']})
        self.assertNotIn('zh-CN', value['cultures'])
        with self.assertRaises(ValueError): self.r.encode_metadata('../ShooterGame')
        for name in ('ShooterGame', 'shootergame', 'Engine', 'ENGINE', 'ab', '1Mod', 'A' * 49):
            with self.assertRaisesRegex(ValueError, 'Target must be'):
                self.r.target_name(name)
        encoded = self.r.encode_metadata('Example123')
        with self.assertRaisesRegex(ValueError, 'Trailing metadata'):
            self.r.decode_metadata(encoded + b'\x00')
        broken = bytearray(encoded)
        broken[16] = 2
        with self.assertRaisesRegex(ValueError, 'LocMeta v1'):
            self.r.decode_metadata(bytes(broken))


if __name__ == '__main__': unittest.main()
