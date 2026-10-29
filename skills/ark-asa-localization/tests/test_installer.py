"""Manifest-driven installer integration tests; all client files are temporary fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PS = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


@unittest.skipUnless(os.name == 'nt' and PS.exists(), 'Windows PowerShell 5.1 integration tests')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'scripts/install.ps1').exists(), 'Generic installer missing')
        self.tmp = tempfile.TemporaryDirectory(prefix='asa-skill-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.package = self.work / '小包 [package]'
        self.package.mkdir()
        shutil.copyfile(ROOT / 'scripts/install.ps1', self.package / 'install.ps1')
        self.target = 'Demo123456'
        self.payload = b'fixture payload; tests installer effects, not PAK loading'
        self.name = 'ShooterGame-Windows_Demo123456_P.pak'
        (self.package / self.name).write_bytes(self.payload)
        self.manifest = dict(schema=1, mod_id=123456, mod_name='Demo', mod_version='fixture-v1', target=self.target,
                             pak_name=self.name, pak_sha256=hashlib.sha256(self.payload).hexdigest(), runtime_tested=False)
        self.save_manifest()
        self.game = self.work / 'SteamLibrary/steamapps/common/飞升 [client]'
        (self.game / 'ShooterGame/Binaries/Win64').mkdir(parents=True)
        (self.game / 'ShooterGame/Binaries/Win64/ArkAscended.exe').touch()
        (self.game / 'ShooterGame/Content/Paks').mkdir(parents=True)
        self.mod = self.game / 'ShooterGame/Binaries/Win64/ShooterGame/Mods/83374/123456_fixture/Demo'
        self.mod.mkdir(parents=True)
        (self.mod / 'Demo.uplugin').write_text(json.dumps({'Description':'Demo &cf_ugcID=123456', 'VersionName':'fixture-v1'}), encoding='utf-8')
        self.ini = self.game / 'ShooterGame/Saved/Config/Windows/Game.ini'
        self.ini.parent.mkdir(parents=True)
        self.pak = self.game / 'ShooterGame/Content/Paks' / self.name
        self.line = 'LocalizationPaths=../../../ShooterGame/Content/Localization/Demo123456'

    def save_manifest(self):
        (self.package / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def run_installer(self, action='Install', extra=(), game=True, ok=True, input=None):
        args = [str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.package / 'install.ps1'), '-Action', action]
        if input is None: args += ['-NonInteractive']
        if game: args += ['-GamePath', str(self.game)]
        r = subprocess.run(args + list(extra), input=input, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r

    def test_install_noop_backup_uninstall_keeps_later_edits_and_other_mod(self):
        old = '; 用户配置\r\n[Internationalization]\r\nLocalizationPaths=../../../OtherMod\r\n'
        self.ini.write_bytes(b'\xef\xbb\xbf' + old.encode())
        self.run_installer()
        installed = self.ini.read_bytes()
        self.assertIn(self.line, installed.decode('utf-8-sig'))
        self.assertEqual(self.pak.read_bytes(), self.payload)
        self.run_installer()
        self.assertEqual(self.ini.read_bytes(), installed)
        backups = list((self.game / 'ShooterGame/Saved/LocalizationBackups/Demo123456').glob('*/Game.ini'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'\xef\xbb\xbf' + old.encode())
        self.ini.write_bytes(installed + '\r\n[Later]\r\nValue=新设置\r\n'.encode())
        self.run_installer('Uninstall')
        text = self.ini.read_text(encoding='utf-8-sig')
        self.assertIn('OtherMod', text)
        self.assertIn('Value=新设置', text)
        self.assertNotIn(self.line, text)
        self.assertFalse(self.pak.exists())

    def test_detection_steam_library_and_manual_mod_path_make_no_writes(self):
        steam = self.work / 'Steam'
        (steam / 'steamapps').mkdir(parents=True)
        lib = self.work / 'SteamLibrary'
        (steam / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" {"0" {"path" "' + str(lib).replace('\\','\\\\') + '"}}', encoding='utf-8')
        (lib / 'steamapps/appmanifest_2399830.acf').write_text('"installdir" "飞升 [client]"', encoding='utf-8')
        r = self.run_installer('Detect', ['-SteamPath', str(steam)], game=False)
        self.assertIn('123456_fixture', r.stdout)
        self.run_installer('Detect', ['-GamePath', str(self.mod)], game=False)
        self.assertFalse(self.pak.exists())
        self.assertFalse(self.ini.exists())

    def test_wrong_game_missing_mod_hash_mismatch_and_traversal_fail_without_changes(self):
        exe = self.game / 'ShooterGame/Binaries/Win64/ArkAscended.exe'
        exe.unlink()
        (exe.parent / 'ShooterGame.exe').touch()
        self.run_installer(ok=False)
        exe.touch()
        plugin = self.mod / 'Demo.uplugin'
        plugin.rename(self.mod / 'Demo.disabled')
        self.run_installer(ok=False)
        (self.mod / 'Demo.disabled').rename(plugin)
        (self.package / self.name).write_bytes(b'corrupt')
        self.run_installer(ok=False)
        (self.package / self.name).write_bytes(self.payload)
        self.manifest['pak_name'] = '../outside.pak'
        self.save_manifest()
        self.run_installer(ok=False)
        self.assertFalse(self.pak.exists())
        self.assertFalse(self.ini.exists())

    def test_existing_same_files_are_not_owned_and_changed_files_not_deleted(self):
        self.ini.write_text('[Internationalization]\r\n' + self.line + '\r\n', encoding='utf-8', newline='')
        self.pak.write_bytes(self.payload)
        original = self.ini.read_bytes()
        self.run_installer()
        self.run_installer('Uninstall')
        self.assertTrue(self.pak.exists())
        self.assertEqual(self.ini.read_bytes(), original)
        self.pak.unlink()
        self.ini.unlink()
        self.run_installer()
        original = self.ini.read_bytes()
        self.pak.write_bytes(b'user replaced patch')
        self.run_installer('Uninstall', ok=False)
        self.assertEqual(self.ini.read_bytes(), original)
        self.assertEqual(self.pak.read_bytes(), b'user replaced patch')

    def test_utf16_new_ini_and_ambiguous_config(self):
        self.run_installer()
        self.assertIn('/Localization/ShooterGame', self.ini.read_text(encoding='utf-8-sig'))
        self.run_installer('Uninstall')
        self.ini.write_bytes(b'\xff\xfe' + '[Other]\r\nName=中文\r\n'.encode('utf-16-le'))
        self.run_installer()
        self.assertTrue(self.ini.read_bytes().startswith(b'\xff\xfe'))
        self.run_installer('Uninstall')
        for config in ['[Internationalization]\r\n+LocalizationPaths=Other\r\n', '[Internationalization]\r\n[Internationalization]\r\n']:
            self.ini.write_bytes(config.encode())
            self.run_installer(ok=False)
            self.assertEqual(self.ini.read_bytes(), config.encode())
            self.assertFalse(self.pak.exists())

    def test_preexisting_managed_markers_do_not_grant_ownership(self):
        original = ('[Internationalization]\r\n'
                    '; Demo123456 BEGIN - managed by installer\r\n' + self.line + '\r\n'
                    '; Demo123456 END - managed by installer\r\n').encode('utf-8')
        self.ini.write_bytes(original)
        self.pak.write_bytes(self.payload)
        self.run_installer()
        self.run_installer('Uninstall')
        self.assertEqual(self.ini.read_bytes(), original)
        self.assertEqual(self.pak.read_bytes(), self.payload)

    def test_recreated_missing_pak_becomes_owned(self):
        self.pak.write_bytes(self.payload)
        self.run_installer()
        self.pak.unlink()
        self.run_installer()
        self.assertEqual(self.pak.read_bytes(), self.payload)
        self.run_installer('Uninstall')
        self.assertFalse(self.pak.exists())

    def test_failed_write_rolls_back_and_retains_backup(self):
        self.ini.write_bytes(b'[Other]\r\nValue=keep\r\n')
        wrapper = self.work / 'locked.ps1'
        wrapper.write_text('''param($Ini,$Installer,$Game)
$lock=[IO.File]::Open($Ini,'Open','Read','Read')
try { & $Installer -GamePath $Game -Action Install -NonInteractive }
finally { $lock.Dispose() }
if ($LASTEXITCODE) {exit $LASTEXITCODE}
''', encoding='utf-8-sig')
        r = subprocess.run([str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper), '-Ini', str(self.ini), '-Installer', str(self.package / 'install.ps1'), '-Game', str(self.game)], capture_output=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.ini.read_bytes(), b'[Other]\r\nValue=keep\r\n')
        self.assertFalse(self.pak.exists())
        self.assertEqual(len(list((self.game / 'ShooterGame/Saved/LocalizationBackups/Demo123456').glob('*/Game.ini'))), 1)

    def test_multiple_clients_need_choice_and_interactive_selection_works(self):
        steam = self.work / 'Steam'
        (steam / 'steamapps').mkdir(parents=True)
        second = self.work / 'OtherLibrary/steamapps/common/ARK Survival Ascended'
        shutil.copytree(self.game, second)
        lib = self.work / 'SteamLibrary'
        (lib / 'steamapps/appmanifest_2399830.acf').write_text('"installdir" "飞升 [client]"', encoding='utf-8')
        (steam / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" {' + ''.join(
            '"%s" {"path" "%s"}' % (i, str(p).replace('\\','\\\\')) for i,p in enumerate([lib, self.work / 'OtherLibrary'])) + '}', encoding='utf-8')
        self.run_installer(extra=['-SteamPath', str(steam)], game=False, ok=False)
        self.run_installer('Detect', ['-SteamPath', str(steam)], game=False, input='1\n')
        self.assertFalse(self.pak.exists())

    def test_two_manifest_targets_coexist(self):
        self.run_installer()
        first_ini = self.ini.read_bytes()
        second_name = 'ShooterGame-Windows_Other654321_P.pak'
        (self.package / second_name).write_bytes(self.payload)
        self.manifest.update(target='Other654321', pak_name=second_name)
        self.save_manifest()
        self.run_installer()
        self.assertIn('/Other654321', self.ini.read_text(encoding='utf-8-sig'))
        self.run_installer('Uninstall')
        self.assertIn(self.line, self.ini.read_text(encoding='utf-8-sig'))
        self.assertEqual(self.pak.read_bytes(), self.payload)


if __name__ == '__main__': unittest.main()
