"""LocRes v3/LocMeta v1 serialization; no third-party source is vendored.

Key fingerprints use the external MIT-licensed cityhash package. Binary field
layout is documented in references/formats.md; this is not an asset writer.
"""
from collections import Counter, defaultdict
import hashlib
import re
import struct
import zlib

LOCRES_MAGIC = bytes.fromhex('0e147475674a03fc4a15909dc3377f1b')
META_MAGIC = struct.pack('<4I', 0xA14CEE4F, 0x83554868, 0xBD464C6C, 0x7C50DA70)


def target_name(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{2,47}', value) or value.casefold() in {'shootergame', 'engine'}:
        raise ValueError('Target must be a unique ASCII identifier, 3..48 characters, not ShooterGame/Engine')
    return value


def key_hash(value):
    if not value: return 0
    try:
        from cityhash import CityHash64
    except ImportError as exc:
        raise RuntimeError('Install the external build dependency: python -m pip install cityhash==0.4.10') from exc
    h = CityHash64(value.encode('utf-16-le'))
    return ((h & 0xffffffff) + (h >> 32) * 23) & 0xffffffff


def source_hash(value):
    if not value.isascii():
        raise ValueError('Only ASCII source CRC is case-verified. Supply an independently observed source_hash for non-ASCII source.')
    return zlib.crc32(value.encode('utf-32-le')) & 0xffffffff


def fingerprint(row):
    value = row.get('source_hash')
    if value is None: return source_hash(row['source'])
    if type(value) is not int or not 0 <= value <= 0xffffffff: raise ValueError('Invalid source_hash')
    return value


def make_identities(rows, crc_candidates=False, aliases=False):
    result = {}
    keyed_sources = {r['source'] for r in rows if r.get('key')}

    def add(namespace, key, row, evidence):
        value = dict(namespace=namespace, key=key, source=row['source'], translation=row['translation'],
                     source_hash=fingerprint(row), evidence=evidence)
        identity = (namespace, key)
        if identity in result and any(result[identity][k] != value[k] for k in ('source', 'translation', 'source_hash')):
            raise ValueError(f'Identity conflict: {identity}')
        # An alias may be encountered before the same identity in a real asset.
        # Retain observed evidence regardless of row ordering.
        if identity not in result or evidence == 'observed-key': result[identity] = value

    for row in rows:
        if row.get('key'):
            add(row.get('namespace', ''), row['key'], row, 'observed-key')
            if aliases and not row.get('namespace'): add('GraphLiteral', row['key'], row, 'namespace-alias-candidate')
        elif crc_candidates and row['source'] not in keyed_sources:
            for namespace in ('Content', 'GraphLiteral', ''):
                add(namespace, str(fingerprint(row)), row, 'source-crc-candidate')
    if not result: raise ValueError('No identities: review explicit keys or deliberately enable experimental CRC candidates')
    return [result[k] for k in sorted(result)]


def encode_string(value):
    if '\0' in value: raise ValueError('Embedded NUL')
    if not value: return struct.pack('<i', 0)
    if value.isascii():
        raw = value.encode('ascii') + b'\0'
        return struct.pack('<i', len(raw)) + raw
    raw = value.encode('utf-16-le') + b'\0\0'
    return struct.pack('<i', -len(raw)//2) + raw


class Reader:
    def __init__(self, data, pos=0): self.data, self.pos = data, pos
    def raw(self, size):
        if size < 0 or self.pos + size > len(self.data): raise ValueError('Truncated resource')
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result
    def number(self, fmt): return struct.unpack('<' + fmt, self.raw(struct.calcsize('<' + fmt)))[0]
    def count(self):
        n = self.number('I')
        if n > 1000000: raise ValueError('Resource count limit')
        return n
    def string(self):
        n = self.number('i')
        if abs(n) > 1000000: raise ValueError('Resource string limit')
        if not n: return ''
        raw = self.raw(n if n > 0 else -n * 2)
        unit = 1 if n > 0 else 2
        if raw[-unit:] != b'\0' * unit: raise ValueError('Resource string terminator')
        try: return raw[:-unit].decode('utf-8' if n > 0 else 'utf-16-le')
        except UnicodeError as exc: raise ValueError('Resource string encoding') from exc


def encode_locres(records, native=False):
    values, indexes = [], {}
    groups = defaultdict(list)
    for row in sorted(records, key=lambda r: (r['namespace'], r['key'])):
        text = row['source'] if native else row['translation']
        if text not in indexes:
            indexes[text] = len(values)
            values.append(text)
        groups[row['namespace']].append((row, indexes[text]))
    refs = Counter(index for group in groups.values() for _, index in group)
    body = bytearray(struct.pack('<I', len(groups)))
    for ns, group in groups.items():
        body += struct.pack('<I', key_hash(ns)) + encode_string(ns) + struct.pack('<I', len(group))
        for row, index in group:
            body += struct.pack('<I', key_hash(row['key'])) + encode_string(row['key'])
            body += struct.pack('<Ii', fingerprint(row), index)
    tail = bytearray(struct.pack('<i', len(values)))
    for i, text in enumerate(values): tail += encode_string(text) + struct.pack('<i', refs[i])
    header = LOCRES_MAGIC + b'\x03' + struct.pack('<QI', 29 + len(body), len(records))
    data = bytes(header + body + tail)
    if len(decode_locres(data)) != len(records): raise ValueError('Duplicate resource identities')
    return data


def decode_locres(data):
    reader = Reader(data)
    if reader.raw(16) != LOCRES_MAGIC or reader.number('B') != 3: raise ValueError('Only LocRes v3 supported')
    offset, total = reader.number('Q'), reader.count()
    if not reader.pos <= offset < len(data): raise ValueError('Invalid string table offset')
    values = Reader(data, offset)
    strings = [(values.string(), values.number('i')) for _ in range(values.count())]
    if values.pos != len(data): raise ValueError('Trailing string table bytes')
    result, refs = {}, Counter()
    for _ in range(reader.count()):
        nh, ns, count = reader.number('I'), reader.string(), reader.count()
        for _ in range(count):
            kh, key, sh, index = reader.number('I'), reader.string(), reader.number('I'), reader.number('i')
            if not 0 <= index < len(strings): raise ValueError('String table index')
            identity = (ns, key)
            if identity in result: raise ValueError('Duplicate identity')
            result[identity] = dict(namespace_hash=nh, key_hash=kh, source_hash=sh, text=strings[index][0])
            refs[index] += 1
    if reader.pos != offset or len(result) != total: raise ValueError('Resource table size mismatch')
    if any(refs[i] != count for i, (_, count) in enumerate(strings)): raise ValueError('String reference count mismatch')
    return result


def encode_metadata(target):
    target_name(target)
    data = META_MAGIC + b'\x01' + encode_string('en') + encode_string(f'en/{target}.locres') + struct.pack('<i', 3)
    return data + b''.join(encode_string(s) for s in ('en', 'zh', 'zh-Hans'))


def decode_metadata(data):
    r = Reader(data)
    if r.raw(16) != META_MAGIC or r.number('B') != 1: raise ValueError('Only LocMeta v1 supported')
    result = dict(native=r.string(), resource=r.string(), cultures=[r.string() for _ in range(r.count())])
    if r.pos != len(data): raise ValueError('Trailing metadata')
    return result


# Offline patch gate. A readable file is not evidence that ASA loads or displays it.
PAK_MAGIC = 0x5A6F12E1
PATCH_LIMIT = 32 * 1024 * 1024
# V11 footer is 221 bytes. install.ps1 Test-LocalizationPak uses these same offsets:
# encrypted +16, magic +17, version +21, index offset +25, index size +33, sha1 +41.
V11_FOOTER_SIZE = 221
_FOOTER_SPECS = (
    # size, majors, frozen byte, compression-name slots, guid, encrypted flag
    (222, frozenset({9}), True, 5, True, True),
    (221, frozenset({8, 10, 11}), False, 5, True, True),
    (189, frozenset({8}), False, 4, True, True),
    (61, frozenset({7}), False, 0, True, True),
    (45, frozenset({4, 5, 6}), False, 0, False, True),
    (44, frozenset({1, 2, 3}), False, 0, False, False),
)


class PatchStaleError(ValueError):
    """Patch input failed an offline safety check.

    The message is not a statement about any ASA client. runtime_tested stays false.
    """


def refuse_stale_patch(detail):
    raise PatchStaleError(
        'Game update likely invalidated this localization patch: ' + detail
        + '. No files were written. Offline checks do not show that ASA loads or displays the text.')


def patch_kind(name):
    if name.endswith('.locres'): return 'locres'
    if name.endswith('.locmeta'): return 'locmeta'
    if name.endswith('_P.pak'): return 'pak'
    return None


def read_locres_patch(data, label='LocRes'):
    if len(data) > PATCH_LIMIT:
        refuse_stale_patch(label + ' is not readable LocRes v3 (too large)')
    try:
        parsed = decode_locres(data)
    except PatchStaleError:
        raise
    except ValueError as exc:
        refuse_stale_patch(label + ' is not readable LocRes v3 (' + str(exc) + ')')
    if not parsed:
        refuse_stale_patch(label + ' has no localization entries')
    return parsed


def read_locmeta_patch(data, label='LocMeta'):
    if len(data) > PATCH_LIMIT:
        refuse_stale_patch(label + ' is not readable LocMeta v1 (too large)')
    try:
        return decode_metadata(data)
    except PatchStaleError:
        raise
    except ValueError as exc:
        refuse_stale_patch(label + ' is not readable LocMeta v1 (' + str(exc) + ')')


def _pak_string(value):
    if not value.isascii():
        raise ValueError('PAK path must be ASCII: ' + value)
    raw = value.encode('ascii') + b'\0'
    return struct.pack('<I', len(raw)) + raw


def _fnv64(data, seed):
    # Same offset basis and prime repak uses for V11 path hashes.
    hash_value = (0xcbf29ce484222325 + seed) & 0xffffffffffffffff
    for byte in data:
        hash_value ^= byte
        hash_value = (hash_value * 0x00000100000001b3) & 0xffffffffffffffff
    return hash_value


def _path_hash(path, seed):
    return _fnv64(path.casefold().encode('utf-16-le'), seed)


def _split_pak_child(path):
    if path in ('/', ''):
        return None
    trimmed = path[:-1] if path.endswith('/') else path
    slash = trimmed.rfind('/')
    if slash < 0:
        return '/', trimmed
    return trimmed[:slash + 1], trimmed[slash + 1:]


def _check_pak_path(path):
    parts = path.split('/')
    if not path or '\\' in path or path.startswith('/') or ':' in path or any(part in ('', '.', '..') for part in parts):
        raise ValueError('Unsafe pak entry path')
    return path


def _footer_candidates(data):
    found = []
    for size, majors, frozen, slots, guid, encrypted_flag in _FOOTER_SPECS:
        if len(data) < size:
            continue
        blob = data[-size:]
        reader = Reader(blob)
        try:
            if guid:
                reader.raw(16)
            encrypted = reader.number('B') if encrypted_flag else 0
            magic = reader.number('I')
            version = reader.number('I')
            index_offset = reader.number('Q')
            index_size = reader.number('Q')
            digest = reader.raw(20)
            if frozen:
                reader.number('B')
            for _ in range(slots):
                reader.raw(32)
        except ValueError:
            continue
        if reader.pos != size or magic != PAK_MAGIC or version not in majors or encrypted not in (0, 1):
            continue
        end = len(data) - size
        if index_size <= 0 or index_offset > end or index_size > end - index_offset:
            continue
        region = data[index_offset:index_offset + index_size]
        if hashlib.sha1(region).digest() != digest:
            continue
        found.append(dict(version=version, encrypted=bool(encrypted), index_offset=index_offset,
                          index_size=index_size, footer_size=size))
    return found


def _slice_region(data, offset, size, footer_size):
    end = len(data) - footer_size
    if size < 0 or offset < 0 or offset > end or size > end - offset:
        refuse_stale_patch('pak index region is outside the file')
    return data[offset:offset + size]


def _read_encoded_entry(blob, pos):
    reader = Reader(blob, pos)
    bits = reader.number('I')
    method = (bits >> 23) & 0x3f
    compression = None if method == 0 else method - 1
    encrypted = bool(bits & (1 << 22))
    block_count = (bits >> 6) & 0xffff
    block_size = bits & 0x3f
    if block_size == 0x3f:
        block_size = reader.number('I')
    else:
        block_size <<= 11
    if block_count > 100000:
        refuse_stale_patch('pak compression block count is not readable')

    def varint(bit):
        return reader.number('I') if bits & (1 << bit) else reader.number('Q')

    offset = varint(31)
    uncompressed = varint(30)
    compressed = uncompressed if compression is None else varint(29)
    if block_count == 1 and not encrypted:
        pass
    elif block_count:
        for _ in range(block_count):
            reader.number('I')
    return dict(offset=offset, compressed=compressed, uncompressed=uncompressed, compression=compression,
                encrypted=encrypted, block_size=block_size)


def _read_stored_payload(data, entry, index_offset):
    if entry['encrypted'] or entry['offset'] >= index_offset:
        refuse_stale_patch('pak entry is encrypted or stored past the index')
    reader = Reader(data, entry['offset'])
    reader.number('Q')
    compressed = reader.number('Q')
    uncompressed = reader.number('Q')
    method = reader.number('I')
    digest = reader.raw(20)
    compression = None if method == 0 else method - 1
    if compression is not None:
        blocks = reader.number('I')
        if blocks > 100000:
            refuse_stale_patch('pak compression block count is not readable')
        for _ in range(blocks):
            reader.number('Q')
            reader.number('Q')
    flags = reader.number('B')
    reader.number('I')
    if flags & 1 or compressed != entry['compressed'] or uncompressed != entry['uncompressed'] or compression != entry['compression']:
        refuse_stale_patch('pak entry header does not match the index')
    if reader.pos + compressed > index_offset:
        refuse_stale_patch('pak entry overlaps the index')
    payload = reader.raw(compressed)
    if hashlib.sha1(payload).digest() != digest:
        refuse_stale_patch('pak entry hash does not match its bytes')
    return payload


def inspect_pak(data):
    """Read an uncompressed V11 localization pak. Offline only; runtime_tested is false."""
    try:
        return _inspect_pak(data)
    except PatchStaleError:
        raise
    except (ValueError, struct.error) as exc:
        refuse_stale_patch('container is not a readable _P.pak (' + str(exc) + ')')


def _inspect_pak(data):
    if not isinstance(data, (bytes, bytearray)) or not 44 <= len(data) <= PATCH_LIMIT:
        refuse_stale_patch('container is not a readable _P.pak')
    data = bytes(data)
    matches = _footer_candidates(data)
    if not matches:
        refuse_stale_patch('container is not a readable _P.pak')
    footer = max(matches, key=lambda item: item['version'])
    if footer['version'] != 11:
        refuse_stale_patch('container is pak version %s, not the V11 localization patch this tool writes' % footer['version'])
    if footer['encrypted']:
        refuse_stale_patch('pak index is encrypted and was not read')
    index = Reader(_slice_region(data, footer['index_offset'], footer['index_size'], footer['footer_size']))
    mount = index.string()
    record_count = index.number('I')
    index.number('Q')
    if index.number('I') == 0:
        refuse_stale_patch('pak index has no path hash index')
    phi_offset, phi_size = index.number('Q'), index.number('Q')
    phi_hash = index.raw(20)
    phi = _slice_region(data, phi_offset, phi_size, footer['footer_size'])
    if hashlib.sha1(phi).digest() != phi_hash:
        refuse_stale_patch('pak path index hash does not match')
    if index.number('I') == 0:
        refuse_stale_patch('pak index has no directory index')
    fdi_offset, fdi_size = index.number('Q'), index.number('Q')
    fdi_hash = index.raw(20)
    fdi_bytes = _slice_region(data, fdi_offset, fdi_size, footer['footer_size'])
    if hashlib.sha1(fdi_bytes).digest() != fdi_hash:
        refuse_stale_patch('pak directory index hash does not match')
    encoded_size = index.number('I')
    if encoded_size > PATCH_LIMIT:
        refuse_stale_patch('pak encoded index is not readable')
    encoded = index.raw(encoded_size)
    non_encoded = index.number('I')
    if non_encoded:
        refuse_stale_patch('pak non-encoded entries were not read offline')
    if index.pos != footer['index_size'] or record_count > 100000:
        refuse_stale_patch('pak index size does not match its footer')
    fdi = Reader(fdi_bytes)
    paths = {}
    directory_count = fdi.number('I')
    if directory_count > 100000:
        refuse_stale_patch('pak directory index is not readable')
    for _ in range(directory_count):
        directory = fdi.string()
        prefix = directory[1:] if directory.startswith('/') else directory
        file_count = fdi.number('I')
        if file_count > 100000:
            refuse_stale_patch('pak directory index is not readable')
        for _ in range(file_count):
            name = fdi.string()
            encoded_offset = fdi.number('i')
            try:
                path = _check_pak_path(prefix + name)
            except ValueError:
                refuse_stale_patch('pak entry path is not a localization-relative path')
            if path in paths:
                refuse_stale_patch('duplicate pak entry: ' + path)
            paths[path] = encoded_offset
    if fdi.pos != len(fdi_bytes) or len(paths) != record_count:
        refuse_stale_patch('pak directory index does not match the entry count')
    entries = []
    for path in sorted(paths):
        encoded_offset = paths[path]
        if encoded_offset < 0 or encoded_offset >= len(encoded):
            refuse_stale_patch('pak entry offset is outside the encoded index')
        entry = _read_encoded_entry(encoded, encoded_offset)
        payload = _read_stored_payload(data, entry, footer['index_offset'])
        entries.append(dict(path=path, data=payload, compressed=entry['compression'] is not None, encrypted=False))
    return dict(schema=1, version=11, mount=mount, encrypted=False, entries=entries, runtime_tested=False,
                note='Pak footer and uncompressed bytes only. This does not show that ASA mounts the pak.')


def encode_v11_pak(files, mount='../../../'):
    """Build an uncompressed V11 pak. Tests and the installer fixture use this; it is not a game pak writer."""
    if not files:
        raise ValueError('PAK needs at least one file')
    if not mount.isascii() or '\\' in mount:
        raise ValueError('Unsafe PAK mount point')
    records = []
    blob = bytearray()
    for path in sorted(files):
        _check_pak_path(path)
        payload = files[path]
        if not isinstance(payload, (bytes, bytearray)):
            raise ValueError('PAK payload must be bytes')
        header = struct.pack('<QQQI', 0, len(payload), len(payload), 0) + hashlib.sha1(payload).digest() + struct.pack('<BI', 0, 0)
        records.append((path, len(blob), bytes(payload)))
        blob += header + payload
    encoded = bytearray()
    encoded_at = {}
    for path, offset, payload in records:
        encoded_at[path] = len(encoded)
        flags = (1 << 29) | (1 << 30) | (1 << 31)
        encoded += struct.pack('<III', flags, offset, len(payload))
    directories = {}
    for path, _, _ in records:
        cursor = path
        while True:
            parent = _split_pak_child(cursor)
            if parent is None:
                break
            cursor = parent[0]
            directories.setdefault(cursor, {})
        directory, filename = _split_pak_child(path)
        directories.setdefault(directory, {})[filename] = encoded_at[path]
    fdi = bytearray(struct.pack('<I', len(directories)))
    for directory in sorted(directories):
        files_in_dir = directories[directory]
        fdi += _pak_string(directory) + struct.pack('<I', len(files_in_dir))
        for filename in sorted(files_in_dir):
            fdi += _pak_string(filename) + struct.pack('<I', files_in_dir[filename])
    seed = 0
    phi = bytearray(struct.pack('<I', len(records)))
    for path, _, _ in records:
        phi += struct.pack('<QI', _path_hash(path, seed), encoded_at[path])
    phi += struct.pack('<I', 0)
    mount_bytes = _pak_string(mount)
    index_size = len(mount_bytes) + 4 + 8 + 4 + 8 + 8 + 20 + 4 + 8 + 8 + 20 + 4 + len(encoded) + 4
    index_offset = len(blob)
    phi_offset = index_offset + index_size
    fdi_offset = phi_offset + len(phi)
    index = bytearray(mount_bytes)
    index += struct.pack('<IQ', len(records), seed)
    index += struct.pack('<IQQ', 1, phi_offset, len(phi)) + hashlib.sha1(phi).digest()
    index += struct.pack('<IQQ', 1, fdi_offset, len(fdi)) + hashlib.sha1(fdi).digest()
    index += struct.pack('<I', len(encoded)) + encoded + struct.pack('<I', 0)
    if len(index) != index_size:
        raise RuntimeError('Internal PAK index size mismatch')
    footer = b'\0' * 16 + b'\0' + struct.pack('<IIQQ', PAK_MAGIC, 11, index_offset, index_size)
    footer += hashlib.sha1(index).digest() + b'\0' * (32 * 5)
    if len(footer) != V11_FOOTER_SIZE:
        raise RuntimeError('Internal PAK footer size mismatch')
    return bytes(blob + index + phi + fdi + footer)


def preflight_patch_bytes(named, current_hashes=None):
    """Dry-run a list of (relative path, bytes). Raises before any caller writes."""
    if not named:
        refuse_stale_patch('no LocRes, LocMeta, or _P.pak inputs')
    seen, inputs, fingerprints = set(), [], set()
    for name, data in named:
        folded = name.casefold()
        if folded in seen:
            refuse_stale_patch('case-insensitive patch path collision: ' + name)
        seen.add(folded)
        kind = patch_kind(name)
        if kind is None:
            refuse_stale_patch('unsupported patch input: ' + name)
        if kind == 'locres':
            parsed = read_locres_patch(data, name)
            fingerprints.update(item['source_hash'] for item in parsed.values())
            inputs.append(dict(path=name, kind=kind, entries=len(parsed)))
        elif kind == 'locmeta':
            meta = read_locmeta_patch(data, name)
            inputs.append(dict(path=name, kind=kind, cultures=list(meta['cultures'])))
        else:
            info = inspect_pak(data)
            locres_entries = [entry for entry in info['entries'] if entry['path'].endswith('.locres')]
            if not locres_entries:
                refuse_stale_patch(name + ' has no LocRes entries')
            decoded = 0
            for entry in locres_entries:
                if entry['compressed'] or entry['encrypted']:
                    refuse_stale_patch(name + ' LocRes ' + entry['path'] + ' is compressed or encrypted and was not decoded')
                parsed = read_locres_patch(entry['data'], entry['path'])
                fingerprints.update(item['source_hash'] for item in parsed.values())
                decoded += len(parsed)
            inputs.append(dict(path=name, kind=kind, version=info['version'], entries=decoded,
                               locres=[entry['path'] for entry in locres_entries]))
    unmatched = []
    if current_hashes is not None:
        if not fingerprints:
            refuse_stale_patch('patch has no source fingerprints to compare')
        current = set(current_hashes)
        unmatched = sorted(fingerprints - current)
        if len(unmatched) == len(fingerprints):
            refuse_stale_patch('none of the patch source fingerprints match the current mod text')
    return dict(schema=1, runtime_tested=False, offline_only=True, inputs=inputs,
                partially_stale=bool(unmatched), unmatched_source_hashes=unmatched,
                note='Offline preflight only. A readable patch is not evidence that ASA loads or displays it.')
