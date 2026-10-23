"""Read-only, source-selected catalog records for rule-authoring scripts.

Cell text stays textual: prices/formulas/effects are not executable policies.
Positional columns preserve duplicate headings and source omissions verbatim.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from source_context import verified_source


def _document(rules):
    root = Path(rules.root).resolve()
    document = (root / 'data/source-catalog.json').read_bytes()
    identity = (str(root), sha256(document).hexdigest())
    cached = getattr(rules, '_source_catalog', None)
    if cached is not None:
        if getattr(rules, '_source_catalog_identity', None) != identity:
            raise ValueError('catalog definition or root changed; review required')
        return cached
    doc = json.loads(document.decode('utf-8'))
    if doc.get('schema') != 'source-catalog-v1':
        raise ValueError('unsupported source catalog schema')
    entries, sources = {}, {}
    for entry in doc['entries']:
        if entry['id'] in entries:
            raise ValueError('duplicate catalog identity')
        path = (root / entry['source_file']).resolve()
        if not path.is_relative_to((root / 'input').resolve()):
            raise ValueError('catalog source must be inside input')
        if path not in sources:
            data = verified_source(rules, {'file':entry['source_file'],'sha256':entry['source_sha256']}, label='catalog')
            sources[path] = (sha256(data).hexdigest(), data.decode('utf-8').splitlines())
        digest, lines = sources[path]
        if digest != entry['source_sha256']:
            raise ValueError('catalog source changed; review required')
        first, last = entry['lines']
        if not (type(first) is int and type(last) is int and 1 <= first <= last <= len(lines)):
            raise ValueError('invalid catalog source range')
        entries[entry['id']] = (entry, lines[first-1:last])
    rules._source_catalog_identity = identity
    rules._source_catalog = entries
    return entries


def definition(rules, identity):
    if isinstance(identity,str) and identity.startswith('operation/'):
        import foundation_operations as OPERATIONS
        return OPERATIONS.describe(identity.removeprefix('operation/'))
    entry, lines = _document(rules)[identity]
    # A cached parse is not a current source certificate. Revalidate the
    # requested source, including path containment, before exposing its rows.
    root = Path(rules.root).resolve()
    path = (root / entry['source_file']).resolve()
    if not path.is_relative_to((root / 'input').resolve()):
        raise ValueError('catalog source must be inside input')
    selection=rules.select_source_definition(entry['rule_id'],source={'file':entry['source_file'],'sha256':entry['source_sha256']})
    uid=selection['selected_id']
    if uid != entry['rule_id']:
        raise ValueError('catalog replacement needs its own reviewed definition')
    source=selection['source']
    bounds = source.get('lines')
    if not bounds or bounds[0] > entry['lines'][0] or bounds[1] < entry['lines'][1]:
        raise ValueError('catalog source range not covered by selected rule')
    records, tables, current = [], [], None
    for number, raw in enumerate(lines, entry['lines'][0]):
        stripped = raw.strip()
        record = {'id': identity + ':L' + str(number), 'line': number, 'text': raw}
        records.append(record)
        if stripped == '<table>':
            current = {'id': identity + ':T' + str(len(tables)+1), 'columns': [], 'rows': []}
            tables.append(current)
        elif stripped == '</table>':
            current = None
        elif stripped.startswith('|') and stripped.endswith('|'):
            if current is None:
                raise ValueError('table row outside table')
            cells = [x.strip() for x in re.split(r'(?<!\\)\|', stripped[1:-1])]
            if all(re.fullmatch(r':?-{3,}:?', c) for c in cells):
                continue
            if not current['columns'] and entry['has_table_header']:
                current['columns'] = [{'index': i, 'label': c} for i,c in enumerate(cells)]
                current['header_line'] = number
            else:
                if current['columns'] and len(cells) != len(current['columns']):
                    raise ValueError('ragged source catalog table')
                current['rows'].append({'id': record['id'], 'line': number, 'cells': cells})
    return deepcopy({'id': identity, 'title': entry['title'], 'rule_id': uid,
        'source': {'file': entry['source_file'], 'sha256': entry['source_sha256'], 'lines': entry['lines']},
        'records': records, 'tables': tables, 'effect_execution_certified': False})
