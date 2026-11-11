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
import zipfile

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
            digest = hashlib.sha256(exe.read_bytes()).hexdigest()
            record = {'path':str(exe), 'sha256':digest, 'version':'0', 'source_url':'http://example.invalid/tool'}
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                asa_localize.checked_tools({'repak':record, 'unreal_locres':dict(record, source_url='https://example.invalid/tool')})
            with self.assertRaisesRegex(ValueError, 'version'):
                asa_localize.checked_tools({'repak':dict(record, source_url='https://example.invalid/tool', version=''),
                                            'unreal_locres':dict(record, source_url='https://example.invalid/tool')})

    def test_package_rejects_runtime_promotion_and_invalid_identity(self):
        import asa_localize
        offline = {name: True for name in ('source_unchanged', 'independent_export', 'pak_roundtrip', 'metadata_consistent')}
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            with self.assertRaisesRegex(ValueError, 'mod_id'):
                asa_localize.package_build(work / 'missing', work / 'out', {}, 0, 'v1', 'Demo')
            with self.assertRaisesRegex(ValueError, 'mod_id'):
                asa_localize.package_build(work / 'missing', work / 'out', {}, 10**12, '', 'Demo')
            build = work / 'build'
            build.mkdir()
            report = {'runtime_tested': True, 'offline_checks': offline}
            (build / 'verification.json').write_text(json.dumps(report), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'runtime cannot be inferred'):
                asa_localize.package_build(build, work / 'promoted', {}, 123456, 'v1', 'Demo')
            report['runtime_tested'] = 'false'
            (build / 'verification.json').write_text(json.dumps(report), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'runtime cannot be inferred'):
                asa_localize.package_build(build, work / 'string-false', {}, 123456, 'v1', 'Demo')
            report['runtime_tested'] = False
            report['offline_checks'] = dict(offline, pak_roundtrip=False)
            (build / 'verification.json').write_text(json.dumps(report), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'offline verification'):
                asa_localize.package_build(build, work / 'partial', {}, 123456, 'v1', 'Demo')
            self.assertFalse((work / 'promoted').exists())
            self.assertFalse((work / 'promoted.zip').exists())

    def test_cli_inspect_inventory_and_validate_plan_roundtrip_strings(self):
        script = ROOT / 'scripts' / 'asa_localize.py'
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            source = work / 'source'
            source.mkdir()
            text = b'\0' * 17 + struct.pack('<I', 8) + b'\0' + struct.pack('<i', 0)
            text += struct.pack('<i', 33) + b'A' * 32 + b'\0' + struct.pack('<i', 5) + b'Help\0'
            (source / 'HUD.uasset').write_bytes(text)
            archive = work / 'mod.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('Demo.uplugin', json.dumps({'Description': 'cf_ugcID=123456', 'FriendlyName': 'Demo', 'VersionName': 'v1', 'SDKVersion': 9}))
                zipped.writestr('HUD.uasset', text)
            def run(*args):
                result = subprocess.run([sys.executable, '-B', str(script), *args], capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result
            run('inspect-zip', '--input', str(archive), '--output', str(work / 'source.json'))
            inspected = json.loads((work / 'source.json').read_text(encoding='utf-8'))
            self.assertEqual(inspected['plugins'][0]['mod_id'], 123456)
            self.assertFalse(inspected['runtime_tested'])
            run('inventory', '--input', str(source), '--output', str(work / 'plan.json'))
            plan = json.loads((work / 'plan.json').read_text(encoding='utf-8'))
            row = next(item for item in plan['entries'] if item['kind'] == 'ftext-base')
            self.assertEqual(row['source'], 'Help')
            self.assertFalse(row['display'])
            failed = subprocess.run([sys.executable, '-B', str(script), 'validate-plan', '--source', str(source), '--plan', str(work / 'plan.json')], capture_output=True, text=True, encoding='utf-8')
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('No reviewed display translations', failed.stderr)
            row.update(display=True, translation='帮助', review_note='Synthetic HUD label')
            (work / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
            checked = run('validate-plan', '--source', str(source), '--plan', str(work / 'plan.json'))
            self.assertEqual(json.loads(checked.stdout), {'reviewed': 1})

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
            note = (package / '说明.txt').read_text(encoding='utf-8-sig')
            self.assertIn('尚未游戏实测', note)
            self.assertIn('候选数不等于命中数', note)
            self.assertIn('不要把安装校验通过当成游戏内生效', note)
            self.assertNotIn('全界面汉化成功', note)
            manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
            self.assertFalse(manifest['runtime_tested'])
            translated = (package / 'translations.csv').read_text(encoding='utf-8-sig')
            self.assertIn('帮助', translated)
            self.assertIn('observed-key', translated)
            self.assertIn('Help', translated)
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
