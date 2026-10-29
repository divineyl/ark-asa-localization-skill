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


if __name__ == '__main__': unittest.main()
