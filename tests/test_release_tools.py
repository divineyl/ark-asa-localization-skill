"""Exercise public release helpers with disposable files, never real game assets."""
import importlib
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


class ReleaseToolTests(unittest.TestCase):
    def module(self, name):
        self.assertIsNotNone(importlib.util.find_spec(name), name + ' is not implemented')
        return importlib.import_module(name)

    def fixture(self, root):
        skill = root / 'skills/ark-asa-localization'
        (skill / 'references').mkdir(parents=True)
        (skill / 'scripts').mkdir()
        (skill / 'SKILL.md').write_text('---\nname: ark-asa-localization\ndescription: "Use when testing ASA localization."\n---\n\n# Test\n\n[Guide](references/guide.md)\n', encoding='utf-8')
        (skill / 'references/guide.md').write_text('# Guide\n', encoding='utf-8')
        (skill / 'scripts/helper.py').write_text('print("Hello")\n', encoding='utf-8')
        (root / 'LICENSE').write_text('MIT fixture license\n', encoding='utf-8')
        (root / 'THIRD_PARTY_NOTICES.md').write_text('[License](LICENSE)\n', encoding='utf-8')
        return skill

    def test_release_is_deterministic_and_has_only_owned_sources_and_licenses(self):
        release = self.module('build_release')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = self.fixture(root)
            (skill / 'LICENSE').write_bytes((root / 'LICENSE').read_bytes())
            a, b = root / 'one.zip', root / 'two.zip'
            first = release.build_release(root, a)
            second = release.build_release(root, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(first['sha256'], second['sha256'])
            with zipfile.ZipFile(a) as archive:
                self.assertEqual(archive.testzip(), None)
                self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
                self.assertEqual(archive.read('ark-asa-localization/LICENSE'), (root / 'LICENSE').read_bytes())
                self.assertEqual(len(archive.namelist()), 5)
                self.assertTrue(all(name.startswith('ark-asa-localization/') for name in archive.namelist()))
            self.assertIn(first['sha256'], a.with_suffix('.zip.sha256').read_text())

    def test_release_rejects_cache_binary_and_cannot_overwrite(self):
        release = self.module('build_release')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = self.fixture(root)
            for name, payload in [('scripts/foreign.dll', b'MZforeign'), ('scripts/cache.pyc', b'cache')]:
                bad = skill / name
                bad.write_bytes(payload)
                with self.assertRaises(ValueError): release.build_release(root, root / 'forbidden.zip')
                self.assertFalse((root / 'forbidden.zip').exists())
                bad.unlink()
            output = root / 'exists.zip'
            output.write_bytes(b'keep me')
            with self.assertRaises(FileExistsError): release.build_release(root, output)
            self.assertEqual(output.read_bytes(), b'keep me')

    def test_static_checks_find_broken_links_bad_frontmatter_and_source_syntax(self):
        verify = self.module('verify_repo')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = self.fixture(root)
            self.assertEqual(verify.static_checks(root), [])
            (skill / 'references/guide.md').write_text('[Missing](missing.md)\n', encoding='utf-8')
            self.assertTrue(any('missing.md' in message for message in verify.static_checks(root)))
            (skill / 'references/guide.md').write_text('# Guide\n', encoding='utf-8')
            (skill / 'scripts/helper.py').write_text('def broken(:\n', encoding='utf-8')
            self.assertTrue(any('helper.py' in message for message in verify.static_checks(root)))
            (skill / 'scripts/helper.py').write_text('pass\n', encoding='utf-8')
            entry = skill / 'SKILL.md'
            entry.write_text(entry.read_text().replace('name: ark-asa-localization', 'name: wrong'), encoding='utf-8')
            self.assertTrue(any('frontmatter' in message for message in verify.static_checks(root)))

    def test_static_checks_reject_local_path_leaks_and_links_outside_repo(self):
        verify = self.module('verify_repo')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            (root / 'README.md').write_text('[Escape](../private.md)\n', encoding='utf-8')
            self.assertTrue(any('outside' in message for message in verify.static_checks(root)))
            # Construct a fake personal path without embedding a real user's location.
            (root / 'README.md').write_text('C:' + '/Users/' + 'private-user/work\n', encoding='utf-8')
            self.assertTrue(any('personal' in message for message in verify.static_checks(root)))

    def test_static_checks_allow_root_work_dirs_but_never_hide_skill_assets(self):
        verify = self.module('verify_repo')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skill = self.fixture(root)
            for name in ('work', 'local-tools', 'test-output'):
                folder = root / name
                folder.mkdir()
                (folder / 'external.exe').write_bytes(b'MZfixture')
                (folder / 'private.json').write_text(json.dumps({'path': 'C:' + '/Users/private/tool.exe'}), encoding='utf-8')
            (root / 'tools.json').write_text(json.dumps({'path': 'C:' + '/Users/private/tool.exe'}), encoding='utf-8')
            self.assertEqual(verify.static_checks(root), [])
            (skill / 'work').mkdir()
            (skill / 'work/hidden.dll').write_bytes(b'MZfixture')
            self.assertTrue(any('hidden.dll' in message for message in verify.static_checks(root)))

    def test_demo_cli_generates_only_synthetic_observed_key_plan(self):
        script = ROOT / 'examples/create_demo.py'
        self.assertTrue(script.is_file(), 'Synthetic demo generator is not implemented')
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / '中文 demo [1]'
            result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(script), '--output', str(output)], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            plan = json.loads((output / 'plan.json').read_text(encoding='utf-8'))
            rows = [row for row in plan['entries'] if row['display']]
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['source'], rows[0]['translation'], rows[0]['namespace'], rows[0]['key']), ('Help', '帮助', '', 'A'*32))
            inspection = json.loads((output / 'inspection.json').read_text(encoding='utf-8'))
            self.assertEqual(inspection['plugins'][0]['mod_id'], 123456)
            self.assertEqual(inspection['plugins'][0]['version'], 'synthetic-v1')
            with zipfile.ZipFile(output / 'source.zip') as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist(): self.assertEqual(archive.read(name), (output / 'source' / name).read_bytes())
            repeat = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(script), '--output', str(output)], capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(repeat.returncode, 0)

    def test_setup_checks_executable_hash_and_unique_zip_payload(self):
        setup = self.module('setup_test_tools')
        data = b'synthetic executable bytes; never executed'
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(setup.checked_digest(data, digest, 'fixture'), data)
        with self.assertRaises(ValueError): setup.checked_digest(data, '0' * 64, 'fixture')
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('nested/repak.exe', data)
            z.writestr('README.md', 'not executable')
        self.assertEqual(setup.extract_payload(archive.getvalue(), 'repak.exe'), data)
        ambiguous = io.BytesIO()
        with zipfile.ZipFile(ambiguous, 'w') as z:
            z.writestr('one/repak.exe', data)
            z.writestr('two/repak.exe', data)
        with self.assertRaises(ValueError): setup.extract_payload(ambiguous.getvalue(), 'repak.exe')


if __name__ == '__main__':
    unittest.main()
