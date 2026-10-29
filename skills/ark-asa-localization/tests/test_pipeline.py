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


if __name__ == '__main__': unittest.main()
