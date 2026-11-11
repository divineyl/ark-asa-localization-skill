import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class PipelineTests(unittest.TestCase):
    def test_external_tool_hash_is_checked_before_execution(self):
        self.assertIsNotNone(importlib.util.find_spec('asa_localize'), 'Pipeline implementation missing')
        import asa_localize
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / 'not-a-tool.exe'
            exe.write_bytes(b'not executable')
            with self.assertRaises(ValueError):
                asa_localize.checked_tools({'repak':{'path':str(exe), 'sha256':'0'*64}})

    @unittest.skipUnless(os.environ.get('ASA_TEST_TOOLS'), 'Set ASA_TEST_TOOLS to your external tools manifest')
    def test_build_independent_export_pack_roundtrip_package_and_bat_install(self):
        self.assertIsNotNone(importlib.util.find_spec('asa_localize'), 'Pipeline implementation missing')
        import asa_core
        import asa_localize
        import asa_resources
        from test_installer import PS
        with tempfile.TemporaryDirectory(prefix='asa-pipeline-') as d:
            work = Path(d)
            source = work / '原始 [source]'
            source.mkdir()
            text = b'\0'*17 + struct.pack('<I', 8) + b'\0' + struct.pack('<i', 0)
            text += struct.pack('<i', 33) + b'A'*32 + b'\0' + struct.pack('<i', 5) + b'Help\0'
            (source / 'HUD.uasset').write_bytes(text)
            original = hashlib.sha256(text).hexdigest()
            plan = asa_core.inventory(source)
            row = next(r for r in plan['entries'] if r['kind'] == 'ftext-base')
            row.update(display=True, translation='帮助', review_note='Fixture HUD label')
            tools = asa_core.read_json(os.environ['ASA_TEST_TOOLS'])
            report = asa_localize.build_target(source, plan, 'example123', work / 'build', tools)
            self.assertFalse(report['runtime_tested'])
            self.assertEqual(report['identity_count'], 1)
            zh = work / 'build/stage/ShooterGame/Content/Localization/example123/zh/example123.locres'
            self.assertEqual(asa_resources.decode_locres(zh.read_bytes())[('', 'A'*32)]['text'], '帮助')
            self.assertEqual(hashlib.sha256((source / 'HUD.uasset').read_bytes()).hexdigest(), original)
            package = work / '中文 package [1]'
            asa_localize.package_build(work / 'build', package, tools, 123456, 'fixture-v1', 'Demo mod')
            self.assertEqual((package / 'LICENSE.txt').read_bytes(), (ROOT / 'LICENSE').read_bytes())
            game = work / '飞升游戏'
            (game / 'ShooterGame/Binaries/Win64').mkdir(parents=True)
            (game / 'ShooterGame/Binaries/Win64/ArkAscended.exe').touch()
            (game / 'ShooterGame/Content/Paks').mkdir(parents=True)
            mod = game / 'ShooterGame/Binaries/Win64/ShooterGame/Mods/83374/123456_fixture/Demo'
            mod.mkdir(parents=True)
            (mod / 'Demo.uplugin').write_text(json.dumps({'Description':'cf_ugcID=123456', 'VersionName':'fixture-v1'}))
            for action in ('detect', 'install', 'uninstall'):
                command = f'cmd.exe /d /c ""{package / (action + ".bat")}" "{game}""'
                r = subprocess.run(command, input=b'\n', capture_output=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                exists = (game / 'ShooterGame/Content/Paks' / report['pak_name']).exists()
                self.assertEqual(exists, action == 'install')
            self.assertTrue(package.with_suffix('.zip').exists())
            # A report edited independently of resources cannot preserve evidence counts.
            verification_path = work / 'build/verification.json'
            verification = json.loads(verification_path.read_text(encoding='utf-8'))
            original_counts = verification['evidence_counts']
            verification['evidence_counts'] = {'observed-key':999}
            verification_path.write_text(json.dumps(verification), encoding='utf-8')
            with self.assertRaises(ValueError):
                asa_localize.package_build(work / 'build', work / 'wrong-counts', tools, 123456, 'fixture-v1', 'Demo')
            verification['evidence_counts'] = original_counts
            verification_path.write_text(json.dumps(verification), encoding='utf-8')
            # Offline verification cannot attest a later-mutated build.
            pak = work / 'build' / report['pak_name']
            pak.write_bytes(b'changed after validation')
            with self.assertRaises(ValueError):
                asa_localize.package_build(work / 'build', work / 'wrong', tools, 123456, 'fixture-v1', 'Demo')


class PatchApplySafetyTests(unittest.TestCase):
    def setUp(self):
        import asa_localize
        import asa_resources
        self.localize = asa_localize
        self.resources = asa_resources
        self.tmp = tempfile.TemporaryDirectory(prefix='asa-patch-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def _locres(self, source, translation, key):
        return self.resources.encode_locres([
            dict(namespace='UI', key=key, source=source, translation=translation, evidence='observed-key')])

    def test_unreadable_export_and_apply_write_nothing(self):
        source = self.work / 'patch'
        source.mkdir()
        (source / 'old.locres').write_bytes(b'truncated-after-a-game-update')
        dest = self.work / 'dest'
        dest.mkdir()
        kept = self._locres('Help', '旧', 'HelpKey')
        (dest / 'old.locres').write_bytes(kept)
        with self.assertRaisesRegex(self.resources.PatchStaleError, 'No files were written'):
            self.localize.apply_patch(source, dest, self.work / 'backups')
        self.assertEqual((dest / 'old.locres').read_bytes(), kept)
        self.assertFalse((self.work / 'backups').exists())
        exported = self.work / 'export.csv'
        with self.assertRaisesRegex(self.resources.PatchStaleError, 'Game update likely invalidated'):
            self.localize.export_patch(source / 'old.locres', exported)
        self.assertFalse(exported.exists())
        script = ROOT / 'scripts' / 'asa_localize.py'
        result = subprocess.run([sys.executable, '-B', str(script), 'preflight', '--input', str(source / 'old.locres')],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Game update likely invalidated', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIn('Offline checks do not show', result.stderr)

    def test_apply_backs_up_and_failed_write_rolls_back(self):
        source = self.work / 'patch'
        nested = source / 'nested'
        nested.mkdir(parents=True)
        new_a = self._locres('Help', '帮助', 'HelpKey')
        new_b = self._locres('Open', '打开', 'OpenKey')
        (source / 'a.locres').write_bytes(new_a)
        (nested / 'b.locres').write_bytes(new_b)
        dest = self.work / 'dest'
        dest.mkdir()
        old_a = self._locres('Help', '旧帮助', 'HelpKey')
        (dest / 'a.locres').write_bytes(old_a)
        (dest / 'nested').write_bytes(b'not-a-directory')
        with self.assertRaisesRegex(self.resources.PatchStaleError, 'Previous files were restored') as caught:
            self.localize.apply_patch(source, dest, self.work / 'backups')
        self.assertIn('Backup kept at', str(caught.exception))
        self.assertIn('do not show that ASA loads', str(caught.exception))
        self.assertEqual((dest / 'a.locres').read_bytes(), old_a)
        self.assertEqual((dest / 'nested').read_bytes(), b'not-a-directory')
        self.assertFalse((dest / 'nested' / 'b.locres').exists())
        self.assertEqual(len(list((self.work / 'backups').iterdir())), 1)

    def test_dry_run_partial_stale_apply_and_explicit_rollback(self):
        source = self.work / 'patch'
        source.mkdir()
        combined = self.resources.encode_locres([
            dict(namespace='UI', key='HelpKey', source='Help', translation='帮助', evidence='observed-key'),
            dict(namespace='UI', key='OpenKey', source='Open', translation='打开', evidence='observed-key'),
        ])
        (source / 'ui.locres').write_bytes(combined)
        (self.work / 'current.json').write_text(json.dumps({'sources': ['Help']}), encoding='utf-8')
        dest = self.work / 'dest'
        dest.mkdir()
        previous = self._locres('Help', '以前', 'HelpKey')
        (dest / 'ui.locres').write_bytes(previous)
        preview = self.localize.apply_patch(source, dest, dry_run=True, current=self.work / 'current.json')
        self.assertTrue(preview['dry_run'])
        self.assertFalse(preview['runtime_tested'])
        self.assertTrue(preview['partially_stale'])
        self.assertIsNone(preview['backup'])
        self.assertEqual((dest / 'ui.locres').read_bytes(), previous)
        self.assertFalse((self.work / 'backups').exists())
        applied = self.localize.apply_patch(source, dest, self.work / 'backups', current=self.work / 'current.json')
        self.assertFalse(applied['runtime_tested'])
        self.assertEqual((dest / 'ui.locres').read_bytes(), combined)
        self.assertIn('not evidence', applied['note'])
        (dest / 'ui.locres').write_bytes(b'user-edit-after-apply')
        restored = self.localize.rollback_patch(applied['backup'], dest)
        self.assertEqual(restored['restored'], ['ui.locres'])
        self.assertFalse(restored['runtime_tested'])
        self.assertIn('does not show that ASA loads', restored['note'])
        self.assertEqual((dest / 'ui.locres').read_bytes(), previous)
        saved = Path(applied['backup']) / 'files' / 'ui.locres'
        saved.unlink()
        (dest / 'ui.locres').write_bytes(combined)
        with self.assertRaisesRegex(self.resources.PatchStaleError, 'Rollback incomplete') as caught:
            self.localize.rollback_patch(applied['backup'], dest)
        self.assertIn(str(applied['backup']), str(caught.exception))
        self.assertEqual((dest / 'ui.locres').read_bytes(), combined)


if __name__ == '__main__': unittest.main()
