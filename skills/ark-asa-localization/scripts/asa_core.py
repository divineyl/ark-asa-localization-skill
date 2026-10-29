"""ASA read-only inspection and reviewed text plans. Python 3.10+, standard library."""
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    if path.exists(): raise FileExistsError('Output already exists; choose a new path: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def safe_relative(name):
    normalized = name.replace('\\', '/')
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ':' in normalized or any(c in normalized for c in '\0\r\n'):
        raise ValueError(f'Unsafe relative path: {name!r}')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) or
           re.match(r'(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', p) or
           any(c in p for c in '<>"|?*') for p in normalized.rstrip('/').split('/')):
        raise ValueError(f'Unsafe Windows path: {name!r}')
    return path


def inspect_zip(archive, extract=None, max_unpacked=4 * 1024**3):
    archive = Path(archive)
    if extract is not None and Path(extract).exists(): raise FileExistsError('Extraction directory already exists; choose a new path: ' + str(extract))
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > max_unpacked: raise ValueError('ZIP exceeds unpacked size limit')
        seen = set()
        for info in z.infolist():
            relative = safe_relative(info.filename)
            key = str(relative).casefold()
            if key in seen: raise ValueError(f'Case-insensitive ZIP collision: {info.filename}')
            seen.add(key)
            if stat.S_ISLNK(info.external_attr >> 16): raise ValueError('ZIP symlink refused')
            if info.flag_bits & 1: raise ValueError('Encrypted ZIP unsupported')
        failure = z.testzip()
        if failure: raise ValueError(f'ZIP CRC failed: {failure}')
        plugins, files = [], []
        for info in z.infolist():
            relative = safe_relative(info.filename)
            if info.is_dir(): continue
            data = z.read(info)
            files.append(dict(path=relative.as_posix(), size=len(data), sha256=hashlib.sha256(data).hexdigest()))
            if relative.suffix.lower() == '.uplugin':
                meta = json.loads(data.decode('utf-8-sig'))
                match = re.search(r'cf_ugcID=(\d+)(?=[&#\s]|$)', str(meta.get('Description', '')))
                plugins.append(dict(path=relative.as_posix(), mod_id=int(match[1]) if match else None,
                                    name=meta.get('FriendlyName'), version=meta.get('VersionName'), sdk=meta.get('SDKVersion')))
        if extract is not None:
            dest = Path(extract)
            # A fresh root avoids overwriting user files and following pre-existing junctions.
            dest.mkdir(parents=True, exist_ok=False)
            for info in z.infolist():
                path = dest.joinpath(*safe_relative(info.filename).parts)
                if not path.resolve().is_relative_to(dest.resolve()): raise ValueError('Extract path escaped root')
                if info.is_dir(): path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('xb') as stream: stream.write(z.read(info))
    extensions = Counter(PurePosixPath(f['path']).suffix.lower() for f in files)
    return dict(schema=1, input_name=archive.name, input_sha256=sha256(archive), files=files, plugins=plugins,
                extensions=dict(extensions), has_iostore=bool(extensions['.utoc'] and extensions['.ucas']),
                asa_identity_observed=any(p['mod_id'] and p['sdk'] for p in plugins), runtime_tested=False)


def fstring(data, offset, limit=20000):
    if offset < 0 or offset + 4 > len(data): raise ValueError('FString bounds')
    n = struct.unpack_from('<i', data, offset)[0]
    if abs(n) > limit: raise ValueError('FString length')
    start = offset + 4
    size = n if n >= 0 else -n * 2
    end = start + size
    if end > len(data): raise ValueError('Truncated FString')
    if not n: return '', end
    raw = data[start:end]
    if n > 0:
        if raw[-1:] != b'\0': raise ValueError('FString terminator')
        value = raw[:-1].decode('utf-8')
    else:
        if raw[-2:] != b'\0\0': raise ValueError('Wide FString terminator')
        value = raw[:-2].decode('utf-16-le')
    if '\0' in value or any(ord(c) < 32 and c not in '\r\n\t' for c in value): raise ValueError('Non-text FString')
    return value, end


def scan_bytes(data, relative):
    rows = []
    digest = hashlib.sha256(data).hexdigest()

    def add(kind, offset, end, source, **extra):
        if source and any(c.isalpha() for c in source):
            rows.append(dict(path=relative, source_sha256=digest, offset=offset, end=end, kind=kind,
                             source=source, display=False, **extra))

    # Lookahead is intentional: non-overlapping matches miss structures inside zero runs.
    for match in re.finditer(rb'(?=([\x00-\x1f]\x00\x00\x00\x00))', data):
        p = match.start()
        try:
            ns, q = fstring(data, p + 5, 1024)
            key, q = fstring(data, q, 128)
            source, end = fstring(data, q)
            if re.fullmatch(r'[\w ./:-]*', ns) and key and re.fullmatch(r'[\w./-]+', key):
                add('ftext-base', p, end, source, namespace=ns, key=key)
        except (ValueError, UnicodeError, struct.error): pass
    text_const = rb'\x29\x01\x1f([\x09\x0a\x0d\x20-\x7e]{0,20000})\x00\x1f([\x20-\x7e]{0,1024})\x00\x1f([\x20-\x7e]{0,1024})\x00'
    for m in re.finditer(text_const, data):
        source, key, ns = [v.decode('ascii') for v in m.groups()]
        add('textconst', m.start(), m.end(), source, namespace=ns, key=key)
    for m in re.finditer(rb'\x1f([\x09\x0a\x0d\x20-\x7e]{2,20000})\x00', data):
        add('stringconst', m.start(), m.end(), m[1].decode('ascii'))
    for m in re.finditer(rb'[\x09\x0a\x0d\x20-\x7e]{3,20000}\x00', data):
        p = m.start() - 4
        if p >= 0 and struct.unpack_from('<i', data, p)[0] == len(m[0]):
            add('fstring', p, m.end(), m[0][:-1].decode('ascii'))
    return sorted(rows, key=lambda r: (r['offset'], r['kind']))


def inventory(root):
    root = Path(root).resolve()
    entries, files = [], []
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError(f'Source symlink refused: {path}')
        if not path.is_file() or path.suffix.lower() not in ('.uasset', '.umap'): continue
        if not path.resolve().is_relative_to(root): raise ValueError('Source escaped root')
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        files.append(dict(path=relative, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                          layout='legacy-unreal-header' if data[:4] == bytes.fromhex('c1832a9e') else 'unclassified-cooked-chunk'))
        entries.extend(scan_bytes(data, relative))
    return dict(schema=1, files=files, entries=entries, runtime_tested=False,
                note='Heuristic candidates only. Explicit display review and source revalidation required; not a package parser.')


def translation_errors(source, translated):
    if not isinstance(translated, str) or not translated.strip(): return ['empty translation']
    errors = []
    patterns = {
        'placeholders': r'(?<!\{)\{[^{}]+\}(?!\})',
        'printf': r'%(?:\d+\$)?[-+#0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?(?:hh|ll|[hlLjzt])?[diuoxXfFeEgGaAcspn]',
        'numbers': r'[+-]?\d+(?:\.\d+)?%?',
    }
    for label, pattern in patterns.items():
        if Counter(re.findall(pattern, source)) != Counter(re.findall(pattern, translated)): errors.append(label)
    if source.count('%') != translated.count('%'): errors.append('percent signs')
    if re.findall(r'\r\n|\r|\n', source) != re.findall(r'\r\n|\r|\n', translated): errors.append('newlines')
    tag = r'<(?:/|/?[A-Za-z][^<>\r\n]*)>'
    if re.findall(tag, source) != re.findall(tag, translated): errors.append('rich-text tags')
    return errors


def reviewed_records(root, plan):
    if plan.get('schema') != 1: raise ValueError('Plan schema must be 1')
    root = Path(root).resolve()
    caches, result = {}, []
    for row in plan['entries']:
        if row.get('display') is not True or 'translation' not in row: continue
        if not str(row.get('review_note', '')).strip(): raise ValueError('Display review_note required')
        if 'source_hash' in row and not str(row.get('source_hash_origin', '')).strip():
            raise ValueError('An externally observed source_hash requires source_hash_origin')
        relative = safe_relative(row['path'])
        path = root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(root): raise ValueError('Plan path escaped source')
        if row['path'] not in caches:
            data = path.read_bytes()
            caches[row['path']] = (hashlib.sha256(data).hexdigest(), scan_bytes(data, row['path']))
        digest, observed = caches[row['path']]
        if digest != row['source_sha256']: raise ValueError('Source hash changed: ' + row['path'])
        matches = [r for r in observed if (r['kind'], r['offset']) == (row['kind'], row['offset'])]
        if len(matches) != 1: raise ValueError('Source locator not observed')
        actual = matches[0]
        if any(row.get(k) != actual.get(k) for k in ('source', 'namespace', 'key')): raise ValueError('Source identity changed')
        if row['source'].startswith(('/Game/', '/Script/')): raise ValueError('Resource path is not display text')
        errors = translation_errors(row['source'], row['translation'])
        if errors: raise ValueError(f'Translation validation failed: {errors}: {row["source"]!r}')
        if row['kind'] in ('fstring', 'stringconst') and any(
            r.get('key') and r['offset'] <= row['offset'] < r['end'] for r in observed):
            raise ValueError('Select enclosing keyed text, not its nested string')
        result.append(row)
    if not result: raise ValueError('No reviewed display translations')
    return result


def parse_jsonc(text):
    chars = list(text)
    i, quoted = 0, False
    while i < len(chars):
        if quoted:
            if chars[i] == '\\': i += 2; continue
            if chars[i] == '"': quoted = False
        elif chars[i] == '"': quoted = True
        elif text.startswith('//', i):
            while i < len(chars) and chars[i] not in '\r\n': chars[i] = ' '; i += 1
            continue
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0: raise ValueError('Unterminated JSONC block comment')
            while i < end + 2:
                if chars[i] not in '\r\n': chars[i] = ' '
                i += 1
            continue
        i += 1
    i, quoted = 0, False
    while i < len(chars):
        if quoted:
            if chars[i] == '\\': i += 2; continue
            if chars[i] == '"': quoted = False
        elif chars[i] == '"': quoted = True
        elif chars[i] == ',':
            j = i + 1
            while j < len(chars) and chars[j].isspace(): j += 1
            if j < len(chars) and chars[j] in ']}': chars[i] = ' '
        i += 1
    return json.loads(''.join(chars))
