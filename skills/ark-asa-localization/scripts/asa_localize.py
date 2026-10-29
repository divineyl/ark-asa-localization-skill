"""Portable ASA localization CLI. Never installs into a game automatically."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

import asa_core as core
import asa_resources as resources


def checked_tools(manifest):
    result = {}
    for name in ('repak', 'unreal_locres'):
        record = manifest.get(name)
        if not isinstance(record, dict): raise ValueError('Missing tool record: ' + name)
        path = Path(record['path']).resolve()
        if not re.fullmatch(r'[a-fA-F0-9]{64}', record.get('sha256', '')) or core.sha256(path) != record['sha256'].lower():
            raise ValueError('Tool hash mismatch: ' + name)
        if not record.get('version') or not record.get('source_url', '').startswith('https://'):
            raise ValueError('Tool version and HTTPS upstream URL required: ' + name)
        result[name] = path
    return result


def run(exe, *args):
    result = subprocess.run([str(exe), *map(str, args)], capture_output=True, text=True, encoding='utf-8', errors='strict', check=True)
    return result.stdout.strip()


def expected_files(target):
    prefix = f'ShooterGame/Content/Localization/{target}/'
    return sorted([prefix + target + '.locmeta'] + [prefix + c + '/' + target + '.locres' for c in ('en', 'zh', 'zh-Hans')])


def verify_build(folder, report, tools):
    folder = Path(folder)
    paths = checked_tools(tools)
    target = resources.target_name(report['target'])
    expected = expected_files(target)
    if report['files'] != expected: raise ValueError('Unexpected resource scope')
    pak_name = report['pak_name']
    if Path(pak_name).name != pak_name or pak_name != f'ShooterGame-Windows_{target}_P.pak': raise ValueError('Invalid PAK name')
    pak = folder / pak_name
    if core.sha256(pak) != report['pak_sha256']: raise ValueError('PAK changed after verification')
    if sorted(run(paths['repak'], 'list', pak).splitlines()) != expected: raise ValueError('PAK entry paths differ')
    stage = folder / 'stage'
    with tempfile.TemporaryDirectory(prefix='asa-verify-', dir=folder) as temp:
        temp = Path(temp)
        run(paths['repak'], 'unpack', pak, '--output', temp / 'unpacked')
        for name in expected:
            a, b = stage / name, temp / 'unpacked' / name
            if core.sha256(a) != report['resource_sha256'][name] or a.read_bytes() != b.read_bytes():
                raise ValueError('Resource roundtrip changed: ' + name)
        meta_path = stage / f'ShooterGame/Content/Localization/{target}/{target}.locmeta'
        meta = resources.decode_metadata(meta_path.read_bytes())
        if meta != {'native':'en', 'resource':f'en/{target}.locres', 'cultures':['en','zh','zh-Hans']}:
            raise ValueError('Metadata target/culture mismatch')
        identities = core.read_json(folder / 'identities.json')
        if (len(identities) != report['identity_count'] or
            len({(r['namespace'],r['key']) for r in identities}) != len(identities) or
            len({r['source'] for r in identities}) != report['unique_sources'] or
            dict(Counter(r['evidence'] for r in identities)) != report['evidence_counts']):
            raise ValueError('Identity/evidence counts differ from the report')
        for culture in ('en', 'zh', 'zh-Hans'):
            loc = stage / f'ShooterGame/Content/Localization/{target}/{culture}/{target}.locres'
            parsed = resources.decode_locres(loc.read_bytes())
            expected_text = {(r['namespace'],r['key']):r['source' if culture == 'en' else 'translation'] for r in identities}
            if {k:v['text'] for k,v in parsed.items()} != expected_text: raise ValueError('Resource translations differ')
            for row in identities:
                value = parsed[(row['namespace'], row['key'])]
                if value['source_hash'] != resources.fingerprint(row): raise ValueError('Source fingerprint changed')
                if value['namespace_hash'] != resources.key_hash(row['namespace']) or value['key_hash'] != resources.key_hash(row['key']):
                    raise ValueError('Identity fingerprint changed')
            output = temp / (culture + '.csv')
            run(paths['unreal_locres'], 'export', loc, '-o', output)
            with output.open(encoding='utf-8-sig', newline='') as stream:
                independent = Counter((r['key'], r['source']) for r in csv.DictReader(stream))
            # Namespace/key may themselves contain '/'. Preserve every exported row
            # instead of silently merging different identities with the same label.
            if independent != Counter((ns + '/' + key, text) for (ns,key),text in expected_text.items()):
                raise ValueError('Independent UnrealLocres export differs')
    return True


def build_target(source, plan, target, output, tools, crc_candidates=False, aliases=False):
    resources.target_name(target)
    output = Path(output)
    if output.exists(): raise FileExistsError('Build directory already exists; choose a new path: ' + str(output))
    checked_tools(tools)
    reviewed = core.reviewed_records(source, plan)
    identities = resources.make_identities(reviewed, crc_candidates=crc_candidates, aliases=aliases)
    source = Path(source)
    before = {r['path']:core.sha256(source / r['path']) for r in reviewed}
    stage = output / 'stage'
    for culture in ('en', 'zh', 'zh-Hans'):
        path = stage / f'ShooterGame/Content/Localization/{target}/{culture}/{target}.locres'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resources.encode_locres(identities, native=culture == 'en'))
    (stage / f'ShooterGame/Content/Localization/{target}/{target}.locmeta').write_bytes(resources.encode_metadata(target))
    core.write_json(output / 'identities.json', identities)
    pak_name = f'ShooterGame-Windows_{target}_P.pak'
    run(checked_tools(tools)['repak'], 'pack', '--version', 'V11', '--mount-point', '../../../', stage, output / pak_name)
    files = expected_files(target)
    report = dict(schema=1, target=target, pak_name=pak_name, pak_sha256=core.sha256(output / pak_name),
                  files=files, resource_sha256={name:core.sha256(stage / name) for name in files},
                  identity_count=len(identities), unique_sources=len({r['source'] for r in identities}),
                  evidence_counts=dict(Counter(r['evidence'] for r in identities)),
                  source_files=before, runtime_tested=False, requires_v99=False,
                  tools={name:{k:v for k,v in record.items() if k != 'path'} for name,record in tools.items()})
    verify_build(output, report, tools)
    if any(core.sha256(source / name) != digest for name,digest in before.items()): raise ValueError('Source changed during build')
    report['offline_checks'] = {'source_unchanged':True, 'independent_export':True, 'pak_roundtrip':True, 'metadata_consistent':True}
    core.write_json(output / 'verification.json', report)
    return report


def package_build(build, output, tools, mod_id, mod_version, mod_name):
    build, output = Path(build), Path(output)
    if output.exists() or output.with_suffix('.zip').exists(): raise FileExistsError('Package directory or ZIP already exists; choose a new path: ' + str(output))
    if type(mod_id) is not int or not 0 < mod_id < 10**12 or not mod_version: raise ValueError('mod_id/mod_version required')
    report = core.read_json(build / 'verification.json')
    if report.get('runtime_tested') is not False or not all(report.get('offline_checks', {}).get(k) is True for k in ('source_unchanged','independent_export','pak_roundtrip','metadata_consistent')):
        raise ValueError('Completed offline verification required; runtime cannot be inferred or auto-promoted')
    verify_build(build, report, tools)
    output.mkdir(parents=True)
    shutil.copyfile(build / report['pak_name'], output / report['pak_name'])
    shutil.copyfile(Path(__file__).with_name('install.ps1'), output / 'install.ps1')
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'LICENSE', output / 'LICENSE.txt')
    manifest = dict(schema=1, mod_id=mod_id, mod_version=mod_version, mod_name=mod_name, target=report['target'],
                    pak_name=report['pak_name'], pak_sha256=report['pak_sha256'], runtime_tested=False)
    core.write_json(output / 'manifest.json', manifest)
    for action in ('Install', 'Uninstall', 'Detect'):
        batch = rf'''@echo off
setlocal
if "%~1"=="" (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Action {action}
) else (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Action {action} -GamePath "%~1"
)
set "installerExit=%errorlevel%"
echo.
pause
exit /b %installerExit%
'''
        (output / (action.lower() + '.bat')).write_text(batch, encoding='ascii', newline='\r\n')
    identities = core.read_json(build / 'identities.json')
    with (output / 'translations.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['namespace','key','source','translation','evidence'])
        writer.writerows((r[k] for k in ('namespace','key','source','translation','evidence')) for r in identities)
    note = f'''{mod_name} ({mod_id}) 中文独立小包 · 研究测试版
模组版本：{mod_version}
完整解压后，退出飞升，双击 install.bat。detect.bat 仅检测，uninstall.bat 卸载。
需先在 Windows Steam 飞升客户端内下载并启用原模组。找到多个客户端时请选择。
查找失败时粘贴飞升目录，或把该目录拖到 BAT 上。
安装会备份配置，向 Content/Paks 添加 PAK，在 Saved/Config/Windows/Game.ini 登记 {report['target']}。
备份位于 ShooterGame/Saved/LocalizationBackups/{report['target']}；请保留安装记录与备份。
仅修改本工具拥有的文件/配置块；卸载保留个人设置和其他汉化。
不含完整模组、V9.9 底包、字体或 DLL，不修改原模组资产。检测已下载不等于存档已启用。
原文 {report['unique_sources']} 条，身份 {report['identity_count']} 个；候选数不等于命中数。
离线资源回读、独立导出与封包校验通过；ASA 目标加载和译文命中尚未游戏实测。
CRC/命名空间别名属于候选。不要把安装校验通过当成游戏内生效。
使用简体中文测试名称、描述、菜单、Buff、占位符与重启持久性，并记录版本及实际结果。
旧覆盖包可能影响测试，请自行备份核对冲突，不删除官方 pakchunk 文件。
安装器不自动提权；如目录拒绝写入，可在确认目录正确后以管理员身份运行 BAT。
'''
    (output / '说明.txt').write_text(note, encoding='utf-8-sig', newline='\r\n')
    core.write_json(output / 'verification.json', report)
    checksums = {p.name:core.sha256(p) for p in sorted(output.iterdir()) if p.is_file()}
    core.write_json(output / 'sha256.json', checksums)
    with zipfile.ZipFile(output.with_suffix('.zip'), 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(output.iterdir()): z.write(path, path.name)
    with zipfile.ZipFile(output.with_suffix('.zip')) as z:
        if z.testzip() is not None: raise ValueError('Delivery ZIP CRC failed')
        import hashlib
        if any(hashlib.sha256(z.read(name)).hexdigest() != digest for name,digest in checksums.items()):
            raise ValueError('Delivery ZIP bytes differ')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('inspect-zip')
    p.add_argument('--input', required=True); p.add_argument('--output', required=True); p.add_argument('--extract')
    p = sub.add_parser('inventory')
    p.add_argument('--input', required=True); p.add_argument('--output', required=True)
    p = sub.add_parser('validate-plan')
    p.add_argument('--source', required=True); p.add_argument('--plan', required=True)
    p = sub.add_parser('build')
    for arg in ('source','plan','target','output','tools'): p.add_argument('--' + arg, required=True)
    p.add_argument('--crc-candidates', action='store_true'); p.add_argument('--namespace-aliases', action='store_true')
    p = sub.add_parser('package')
    for arg in ('build','output','tools','mod-version','mod-name'): p.add_argument('--' + arg, required=True)
    p.add_argument('--mod-id', required=True, type=int)
    args = parser.parse_args(argv)
    if args.command == 'inspect-zip': core.write_json(args.output, core.inspect_zip(args.input, args.extract))
    elif args.command == 'inventory': core.write_json(args.output, core.inventory(args.input))
    elif args.command == 'validate-plan': print(json.dumps({'reviewed':len(core.reviewed_records(args.source, core.read_json(args.plan))) }))
    elif args.command == 'build': print(json.dumps(build_target(args.source, core.read_json(args.plan), args.target, args.output, core.read_json(args.tools), args.crc_candidates, args.namespace_aliases), ensure_ascii=False, indent=2))
    elif args.command == 'package': print(json.dumps(package_build(args.build, args.output, core.read_json(args.tools), args.mod_id, args.mod_version, args.mod_name), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit('Error: ' + str(exc))
