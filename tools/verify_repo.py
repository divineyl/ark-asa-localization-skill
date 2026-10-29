"""Check source/skill format and links; optionally run real behavior tests."""
import argparse
import ast
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
from build_release import release_files, build_release

# Only repository-root work areas are omitted. A similarly named directory
# inside the distributable skill is still inspected and release-checked.
IGNORE_ROOT_DIRS = {'.git', '.venv', 'venv', 'dist', '.test-tools', '.pytest_cache', 'work', 'local-tools', 'test-output'}
IGNORE_ROOT_FILES = {'tools.json', 'tools.local.json'}
TEXT_SUFFIXES = {'.md', '.py', '.ps1', '.json', '.yaml', '.yml', '.txt', '.toml'}
PERSONAL_PATH = re.compile(r'(?i)\b[a-z]:[/\\](?:Users|UserData|方舟)[/\\]')


def source_files(root):
    for entry in root.iterdir():
        if entry.name in IGNORE_ROOT_DIRS or entry.name in IGNORE_ROOT_FILES:
            continue
        if entry.is_file() or entry.is_symlink():
            yield entry
        elif entry.is_dir():
            yield from (path for path in entry.rglob('*') if path.is_file() or path.is_symlink())


def static_checks(root):
    root = Path(root).resolve()
    errors = []
    try:
        release_files(root)
    except (OSError, ValueError, UnicodeError) as error:
        errors.append(str(error))
    entry = root / 'skills/ark-asa-localization/SKILL.md'
    try:
        text = entry.read_text(encoding='utf-8-sig')
        block = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
        if not block:
            raise ValueError('missing YAML frontmatter delimiters')
        name = re.findall(r'^name:\s*(.+)$', block[1], re.M)
        description = re.findall(r'^description:\s*(.+)$', block[1], re.M)
        if name != ['ark-asa-localization'] or len(description) != 1:
            raise ValueError('name must match directory and one description is required')
        desc = description[0].strip()
        if desc.startswith('"'):
            desc = json.loads(desc)
        elif desc.startswith("'") and desc.endswith("'"):
            desc = desc[1:-1].replace("''", "'")
        if not isinstance(desc, str) or not 10 <= len(desc) <= 1024 or '<' in desc or '>' in desc:
            raise ValueError('description must be a concise scalar string without angle brackets')
    except (OSError, ValueError, UnicodeError) as error:
        errors.append('SKILL.md frontmatter: ' + str(error))
    for path in source_files(root):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append(relative + ': symlink is not permitted')
            continue
        if '__pycache__' in path.parts or path.suffix.lower() in {'.pyc', '.exe', '.dll', '.pak', '.ucas', '.utoc', '.uasset', '.zip'}:
            errors.append(relative + ': cache or binary asset must not be committed')
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != 'LICENSE':
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
            if PERSONAL_PATH.search(text):
                errors.append(relative + ': personal absolute path found')
            if path.suffix == '.py':
                ast.parse(text, filename=relative)
            if path.suffix == '.json':
                json.loads(text)
            if path.suffix == '.md':
                # Match links outside fenced examples; web links are not fetched.
                markdown = re.sub(r'^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text, flags=re.M | re.S)
                for match in re.finditer(r'!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\)', markdown):
                    href = match[1].strip('<>')
                    parsed = urlsplit(href)
                    if not parsed.path or parsed.scheme or parsed.netloc:
                        continue
                    target = (path.parent / unquote(parsed.path)).resolve()
                    if not target.is_relative_to(root):
                        errors.append(relative + ': link outside repository: ' + href)
                    elif not target.exists():
                        errors.append(relative + ': missing local link: ' + href)
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            errors.append(relative + ': ' + str(error))
    return errors


def run_tests(root, require_no_skips):
    suite = unittest.TestSuite()
    for folder in (root / 'skills/ark-asa-localization/tests', root / 'tests'):
        if folder.is_dir():
            suite.addTests(unittest.TestLoader().discover(str(folder), pattern='test_*.py'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.testsRun == 0:
        return False, {'run': 0, 'error': 'No tests discovered'}
    return result.wasSuccessful() and (not require_no_skips or not result.skipped), {
        'run': result.testsRun,
        'failures': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--full', action='store_true', help='Also run skill + repository tests and two reproducible release builds')
    parser.add_argument('--require-no-skips', action='store_true', help='Fail if Windows/external-tool tests are skipped; requires --full')
    args = parser.parse_args()
    if args.require_no_skips and not args.full:
        parser.error('--require-no-skips requires --full')
    root = args.root.resolve()
    errors = static_checks(root)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    report = {'static_checks': 'passed', 'asa_runtime_tested': False}
    if args.full:
        success, report['tests'] = run_tests(root, args.require_no_skips)
        if not success:
            print(json.dumps(report, indent=2))
            return 1
        with tempfile.TemporaryDirectory(prefix='asa-release-verify-') as d:
            temp = Path(d)
            first = build_release(root, temp / 'one.zip')
            second = build_release(root, temp / 'two.zip')
            if first['sha256'] != second['sha256']:
                print('Release reproducibility failed', file=sys.stderr)
                return 1
            report['release_reproducibility'] = 'passed'
            report['release_sha256'] = first['sha256']
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
