"""LocRes v3/LocMeta v1 serialization; no third-party source is vendored.

Key fingerprints use the external MIT-licensed cityhash package. Binary field
layout is documented in references/formats.md; this is not an asset writer.
"""
from collections import Counter, defaultdict
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
