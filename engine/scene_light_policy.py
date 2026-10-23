"""Selected ordinary light sources and the printed cave-light radii.

The scene owner observes whether a source is emitting and where it is. This
module derives current source eligibility/radius; it owns no scene state.
"""
from pathlib import Path
import hashlib
import json

import ability_transitions as ABILITIES
import state_grants as GRANTS
import world_entities as WORLD

POLICY = 'data/scene-light-policy.json'
GLOW = 'capability/반짝임'
ILLUMINATE = 'ability/발광'
SIZES = {'소형': 'small', 'small': 'small', '중형': 'medium', 'medium': 'medium',
         '대형': 'large', 'large': 'large', '거대': 'huge', '거대형': 'huge', 'huge': 'huge'}
BASE = {'small': 2, 'medium': 2, 'large': 3, 'huge': 4}


def definition(rules):
    # No redundant Rules-instance cache or alternate durable source registry.
    data = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf8'))
    if data.get('schema_version') != 1 or data.get('radii') != {
            'lantern': 2, 'glow': BASE, 'strong_artificial': 3,
            'illuminate_bonus': 1} or data.get('sources') != {
            'glow': GLOW, 'illuminate': ILLUMINATE}:
        raise ValueError('reviewed ordinary light source policy required')
    anchors = {'cave_light': ('input/ch11-running-the-game.md', 1780, 1788),
               'glow': ('input/ch10-index-reference.md', 51, 51)}
    if set(data.get('authority', {})) != set(anchors) or set(data.get('source_files', {})) != {'input/db/abilities.csv'} or data.get('illuminate_csv_record') != 168:
        raise ValueError('exact ordinary light source anchors required')
    for name, (file, start, end) in anchors.items():
        if tuple(data['authority'][name].get(key) for key in ('file', 'start', 'end')) != (file, start, end):
            raise ValueError('ordinary light source span changed')
    for row in data['authority'].values():
        actual = '\n'.join((Path(rules.root) / row['file']).read_text(
            encoding='utf8').splitlines()[row['start']-1:row['end']])
        if actual != row['excerpt'] or hashlib.sha256(actual.encode()).hexdigest() != row['excerpt_sha256']:
            raise ValueError('ordinary light source text changed')
    for relative, expected in data['source_files'].items():
        if hashlib.sha256((Path(rules.root) / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('ordinary light selected source changed: ' + relative)
    return data


def _glow(owner):
    if owner.r._selected_rule(GLOW) != GLOW:
        raise ValueError('selected Glow capability needs an exact source policy')
    # Effective capabilities includes source-owned learning contributions, but
    # excludes display-only and Move-use permission masquerading as learning.
    names = GRANTS.effective_capabilities(owner)
    return any(value in (GLOW, '반짝임', 'Glow') for value in names)


def radius(engine, *, kind, owner=None, size=None, radiant=False):
    """Return seven JSON-safe facts from actual current ownership.

    ``radiant`` preserves the observation API's legacy label. The scene owner
    treats True as an observation-time assertion, never an entitlement. Actual
    Illuminate automatically adds one; suppression/removal removes that bonus.
    An observed Glow source whose capability is withdrawn becomes ineligible.
    """
    definition(engine.r)
    if kind not in ('lantern', 'glow', 'strong_artificial') or type(radiant) is not bool:
        raise ValueError('supported ordinary light kind and boolean assertion required')
    if owner is not None:
        WORLD.require_actors(engine, owner)
    if radiant and owner is None:
        raise ValueError('Illuminate assertion requires an actual source owner')
    capability = None
    eligible = True
    if kind == 'glow':
        if owner is None or owner.kind != 'pokemon':
            raise ValueError('Glow light requires its actual Pokemon source')
        actual_size = SIZES.get(owner.spec.get('size'))
        if actual_size is None:
            raise ValueError('Glow light requires a supported observed Pokemon size')
        if size is not None and (type(size) is not str or SIZES.get(size) is None or SIZES[size] != actual_size):
            raise ValueError('Glow size declaration differs from actual observed size')
        size = actual_size
        base = BASE[size]
        eligible = _glow(owner)
        capability = GLOW if eligible else None
    else:
        if size is not None:
            raise ValueError('only Glow light uses a Pokemon size input')
        base = 2 if kind == 'lantern' else 3
    ability = None
    if owner is not None:
        if engine.r._selected_rule(ILLUMINATE) != ILLUMINATE:
            raise ValueError('selected Illuminate Ability needs an exact source policy')
        if ABILITIES.active(owner, ILLUMINATE):
            ability = ILLUMINATE
    return {'kind': kind, 'size': size, 'base_radius': base,
            'radius': base + int(ability is not None) if eligible else None,
            'capability_source': capability, 'ability_source': ability,
            'eligible': eligible}
