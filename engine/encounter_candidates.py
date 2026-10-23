"""Explicit regional species pools; selection never invents an encountered actor."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from builder import species_lookup

FISHING = 'ch05-pokemon/낚시'
CLAUSE = 'C05-180'
SOURCE_FILE = 'input/ch05-pokemon.md'
SOURCE_SHA256 = 'bdfb5d39fec8fede32cac615a7788301336aaceefc46079c8ed7014ea76d174b'
DEFAULTS = {
    'fresh': ('발챙이', '셀러', '콘치', '잉어킹', '샤프니아', '미꾸리', '가재군', '형광어', '동챙이', '배쓰나이'),
    'salt': ('왕눈해', '셀러', '크랩', '쏘드라', '별가사리', '잉어킹', '총어', '샤프니아', '빈티나', '사랑동이', '깝질무', '형광어', '탱그릴', '수레기', '완철포'),
}
EQUIPMENT_SOURCE = {'file': 'input/ch09-equipment.md',
                    'sha256': 'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}


def admit_wild(engine, wearer, candidates, *, nearby, reason):
    """Actual GM-local actors enter native combat only after live Repel admission."""
    import repels
    return repels.admit(engine,wearer,candidates,nearby=nearby,reason=reason)


def equipment(rules, attachment):
    if attachment not in ('미끼', '루어'):
        raise ValueError('bait or reusable lure required')
    uid = 'item/' + attachment
    selected = rules.select_source_definition(uid, source=EQUIPMENT_SOURCE)
    if selected['selected_id'] != uid:
        raise ValueError('selected bait/lure source requires its own policy')
    return {'source': uid, 'price': 250 if attachment == '미끼' else 1500}


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + ' required')
    return value


def _source(rules):
    if rules._selected_rule(FISHING) != FISHING:
        raise ValueError('selected fishing source requires its own candidate policy')
    if FISHING in rules.ruleset.unit_versions or CLAUSE in rules.ruleset.unit_versions:
        raise ValueError('selected fishing source version requires review')
    rules.ruleset.require({'id': CLAUSE, 'source': {'file': 'ch05-pokemon.md', 'lines': [769, 771]}})
    # Exact saved source, including the printed optional lists and GM discretion.
    data = (Path(rules.root) / SOURCE_FILE).read_bytes()
    if sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('fishing candidate source changed')
    text = data.decode('utf-8-sig').splitlines()
    excerpt = '\n'.join(text[768:771])
    for label, names in DEFAULTS.items():
        expected = ', '.join(names)
        if expected not in excerpt:
            raise ValueError('fishing candidate source changed: ' + label)
    return {'clause_id': CLAUSE, 'file': SOURCE_FILE, 'lines': [769, 771],
            'excerpt_sha256': sha256(excerpt.encode('utf-8')).hexdigest()}


def _species(rules, values):
    if type(values) not in (list, tuple):
        raise ValueError('explicit species list required')
    ids = []
    for value in values:
        _text(value, 'actual selected species')
        try:
            identity = species_lookup(rules, value)['id']
        except KeyError as exc:
            raise ValueError('unknown encounter species: ' + value) from exc
        if identity in ids:
            raise ValueError('duplicate encounter species')
        ids.append(identity)
    return ids


def fishing_pool(rules, declaration):
    """A GM observation of one region/water, with explicit local deviations."""
    if type(declaration) is not dict or set(declaration) != {'region', 'water', 'add', 'remove', 'reason'}:
        raise ValueError('region, water, add, remove and GM reason required')
    _text(declaration['region'], 'observed fishing region')
    _text(declaration['reason'], 'GM regional candidate reason')
    water = declaration['water']
    if type(water) is not str or water not in DEFAULTS:
        raise ValueError('fresh or salt water required')
    source = _source(rules)
    base = _species(rules, DEFAULTS[water])
    added = _species(rules, declaration['add'])
    removed = _species(rules, declaration['remove'])
    if set(added) & set(removed) or not set(removed) <= set(base):
        raise ValueError('regional removal must name a base candidate, distinct from additions')
    candidates = [uid for uid in base if uid not in removed]
    candidates += [uid for uid in added if uid not in candidates]
    if not candidates:
        raise ValueError('regional species pool cannot be empty')
    return {'source': source, 'declaration': deepcopy(declaration), 'candidates': candidates}


def bait_pool(rules, declaration):
    """The GM supplies the actual local species; no ecology or weights are invented."""
    equipment(rules, '미끼')
    if type(declaration) is not dict or set(declaration) != {'region', 'species', 'reason'}:
        raise ValueError('region, species and GM reason required for placed bait')
    _text(declaration['region'], 'observed bait region')
    _text(declaration['reason'], 'GM regional candidate reason')
    candidates = _species(rules, declaration['species'])
    if not candidates:
        raise ValueError('regional species pool cannot be empty')
    return {'source': {'clause_id': 'C09-006', 'file': EQUIPMENT_SOURCE['file'], 'lines': [70, 71]},
            'declaration': deepcopy(declaration), 'candidates': candidates}


def validate_pool(rules, pool):
    source = pool.get('source') if type(pool) is dict else None
    reader = bait_pool if type(source) is dict and source.get('clause_id') == 'C09-006' else fishing_pool
    if type(pool) is not dict or reader(rules, pool.get('declaration')) != pool:
        raise ValueError('regional fishing pool differs from its source and GM declaration')
    return pool


def select(engine, pool, *, choice=None, random_choice=False, previous=None):
    """GM choice or host-RNG draw, once per actual attracted occurrence."""
    validate_pool(engine.r, pool)
    if type(random_choice) is not bool or (choice is None) == (not random_choice):
        raise ValueError('select either one explicit species or random_choice=True')
    selected = _species(engine.r, [choice])[0] if choice is not None else None
    if selected is not None and selected not in pool['candidates']:
        raise ValueError('selected species is outside the regional candidates')
    mode = 'random' if random_choice else 'gm'
    if previous is not None:
        if (type(previous) is not dict or previous.get('mode') != mode
                or previous.get('species_id') not in pool['candidates']
                or set(previous) != {'mode', 'species_id'}
                or (selected is not None and previous['species_id'] != selected)):
            raise ValueError('cannot replace the species already selected for this occurrence')
        return deepcopy(previous)
    return {'mode': mode, 'species_id': engine.rng.choice(pool['candidates']) if random_choice else selected}


def require_target(rules, pool, selected, target):
    validate_pool(rules, pool)
    if (type(selected) is not dict or selected.get('species_id') not in pool['candidates']
            or selected.get('mode') not in ('gm', 'random') or set(selected) != {'mode', 'species_id'}):
        raise ValueError('regional encounter species must be selected before reeling')
    if target is None or species_lookup(rules, target.spec.get('species'))['id'] != selected['species_id']:
        raise ValueError('actual hooked Pokemon differs from the selected regional species')
