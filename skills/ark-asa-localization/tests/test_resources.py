import hashlib
import importlib.util
from pathlib import Path
import struct
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
        self.assertEqual(self.r.source_hash('Awesome Teleporter'), 1145908353)
        # Non-ASCII source fingerprints need an observed source_hash until verified.
        with self.assertRaises(ValueError): self.r.source_hash('新文本😀')

    def test_locres_roundtrip_and_rejects_truncation(self):
        records = [dict(namespace='', key='A'*32, source='Hello', translation='你好😀', evidence='observed-key'),
                   dict(namespace='UI', key='B'*32, source='Hello', translation='您好', evidence='observed-key')]
        binary = self.r.encode_locres(records, native=False)
        parsed = self.r.decode_locres(binary)
        self.assertEqual(parsed[('', 'A'*32)]['text'], '你好😀')
        self.assertEqual(parsed[('UI', 'B'*32)]['text'], '您好')
        self.assertEqual(parsed[('', 'A'*32)]['source_hash'], self.r.source_hash('Hello'))
        for end in [0, 16, 28, len(binary)-1]:
            with self.assertRaises(ValueError): self.r.decode_locres(binary[:end])

    def test_explicit_identities_are_not_replaced_with_global_crc(self):
        rows = [dict(namespace='', key='A'*32, source='Settings', translation='设置', kind='ftext-base'),
                dict(source='Cannon mode', translation='火炮模式', kind='stringconst')]
        exact = self.r.make_identities(rows, crc_candidates=False, aliases=False)
        self.assertEqual(len(exact), 1)
        candidate = self.r.make_identities(rows, crc_candidates=True, aliases=True)
        self.assertEqual(len(candidate), 5)
        self.assertEqual(len([r for r in candidate if r['source'] == 'Settings']), 2)
        self.assertEqual(sum(r['evidence'] == 'source-crc-candidate' for r in candidate), 3)

    def test_conflicting_translation_for_same_identity_is_rejected(self):
        rows = [dict(namespace='UI', key='same', source='Open', translation=t, kind='ftext-base') for t in ['打开', '开放']]
        with self.assertRaises(ValueError): self.r.make_identities(rows)

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
        with self.assertRaises(ValueError): self.r.encode_metadata('../ShooterGame')

    def _locres(self, source, translation, key):
        return self.r.encode_locres([dict(namespace='UI', key=key, source=source, translation=translation, evidence='observed-key')])

    def test_v11_pak_roundtrip_and_footer_offsets_match_the_installer(self):
        first = self._locres('Help', '帮助', 'HelpKey')
        second = self._locres('Open', '打开', 'OpenKey')
        pak = self.r.encode_v11_pak({
            'ShooterGame/Content/Localization/Demo/zh/Demo.locres': first,
            'ShooterGame/Content/Localization/Demo/en/Demo.locres': second,
        })
        start = len(pak) - self.r.V11_FOOTER_SIZE
        self.assertEqual(pak[start + 16], 0)
        self.assertEqual(struct.unpack_from('<I', pak, start + 17)[0], self.r.PAK_MAGIC)
        self.assertEqual(struct.unpack_from('<I', pak, start + 21)[0], 11)
        offset, size = struct.unpack_from('<QQ', pak, start + 25)
        self.assertEqual(hashlib.sha1(pak[offset:offset + size]).digest(), pak[start + 41:start + 61])
        info = self.r.inspect_pak(pak)
        self.assertFalse(info['runtime_tested'])
        self.assertEqual(info['mount'], '../../../')
        self.assertEqual({entry['path']: entry['data'] for entry in info['entries']}, {
            'ShooterGame/Content/Localization/Demo/zh/Demo.locres': first,
            'ShooterGame/Content/Localization/Demo/en/Demo.locres': second,
        })
        self.assertIn('does not show that ASA mounts', info['note'])

    def test_stale_or_unreadable_patch_inputs_fail_before_any_caller_writes(self):
        locres = self._locres('Help', '帮助', 'HelpKey')
        broken = bytearray(locres)
        broken[16] = 4
        with self.assertRaisesRegex(self.r.PatchStaleError, 'not readable LocRes v3'):
            self.r.read_locres_patch(bytes(broken), 'old.locres')
        with self.assertRaisesRegex(self.r.PatchStaleError, 'No files were written'):
            self.r.read_locres_patch(locres[:20], 'truncated.locres')
        with self.assertRaisesRegex(self.r.PatchStaleError, 'not readable LocMeta'):
            self.r.read_locmeta_patch(b'not-metadata', 'old.locmeta')
        pak = self.r.encode_v11_pak({'ShooterGame/Content/Localization/Demo/zh/Demo.locres': locres})
        start = len(pak) - self.r.V11_FOOTER_SIZE
        index_offset = struct.unpack_from('<Q', pak, start + 25)[0]
        flipped = bytearray(pak)
        flipped[index_offset] ^= 0xff
        with self.assertRaisesRegex(self.r.PatchStaleError, 'not a readable _P.pak'):
            self.r.inspect_pak(bytes(flipped))
        payload = bytearray(pak)
        payload[60] ^= 0xff
        with self.assertRaisesRegex(self.r.PatchStaleError, 'pak entry hash does not match'):
            self.r.inspect_pak(bytes(payload))
        encrypted = bytearray(pak)
        encrypted[len(encrypted) - self.r.V11_FOOTER_SIZE + 16] = 1
        with self.assertRaisesRegex(self.r.PatchStaleError, 'encrypted'):
            self.r.inspect_pak(bytes(encrypted))
        index = b'abc'
        footer = b'\0' * 16 + b'\0' + struct.pack('<IIQQ', self.r.PAK_MAGIC, 9, 0, len(index))
        footer += hashlib.sha1(index).digest() + b'\0' + (b'\0' * 160)
        self.assertEqual(len(footer), 222)
        with self.assertRaisesRegex(self.r.PatchStaleError, 'pak version 9'):
            self.r.inspect_pak(index + footer)
        bare = self.r.encode_v11_pak({'fixture/payload.txt': b'not a localization resource'})
        with self.assertRaisesRegex(self.r.PatchStaleError, 'has no LocRes entries'):
            self.r.preflight_patch_bytes([('ShooterGame-Windows_Demo_P.pak', bare)])

    def test_source_fingerprint_mismatch_is_stale_and_partial_overlap_is_reported(self):
        help_res = self._locres('Help', '帮助', 'HelpKey')
        both = self.r.encode_locres([
            dict(namespace='UI', key='HelpKey', source='Help', translation='帮助', evidence='observed-key'),
            dict(namespace='UI', key='OpenKey', source='Open', translation='打开', evidence='observed-key'),
        ])
        with self.assertRaisesRegex(self.r.PatchStaleError, 'none of the patch source fingerprints'):
            self.r.preflight_patch_bytes([('a.locres', help_res)], {self.r.source_hash('Other')})
        report = self.r.preflight_patch_bytes(
            [('a.locres', both), ('Example123.locmeta', self.r.encode_metadata('Example123'))],
            {self.r.source_hash('Help')})
        self.assertFalse(report['runtime_tested'])
        self.assertTrue(report['offline_only'])
        self.assertTrue(report['partially_stale'])
        self.assertEqual(report['unmatched_source_hashes'], [self.r.source_hash('Open')])
        self.assertIn('not evidence that ASA loads', report['note'])
        self.assertEqual(report['inputs'][1]['cultures'], ['en', 'zh', 'zh-Hans'])


if __name__ == '__main__': unittest.main()
