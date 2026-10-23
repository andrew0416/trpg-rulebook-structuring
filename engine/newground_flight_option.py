"""Explicit campaign adoption of ch11's Ground/Flying optional paragraph.

Only the campaign choice is owned here. Native movement owns actual airborne
state; the catalog and field owners retain grounding and Ground-immunity
exceptions. The ordinary type chart remains unchanged.
"""
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path

import root_resolution as ROOT

SOURCE = 'ch11-running-the-game/선택적인-룰/땅-공격-비행-타입들'
KEY = '_ground_flight_option'
REFERENCE = {'file': 'input/ch11-running-the-game.md',
             'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}


def _source(engine):
    policy = json.loads((Path(engine.r.root) / 'data/ground-flight-option-policy.json').read_text(encoding='utf-8'))
    if (policy['source_id'] != SOURCE or policy['source'] != REFERENCE
            or policy['groundsource_keyword'] != '지면통과'
            or policy['flying_ground_component'] != .5):
        raise ValueError('selected Ground/Flying policy needs its own adapter')
    chosen = engine.r.select_source_definition(SOURCE, source=REFERENCE)
    if (chosen['selected_id'] != SOURCE or engine.rulings.mech.get(SOURCE)
            or engine.rulings.effects.get(SOURCE)):
        raise ValueError('selected Ground/Flying variant needs its own adapter')
    return policy


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + ' required')


def validate(engine):
    """Validate the one campaign observation at native and restore boundaries."""
    if not hasattr(engine, KEY):
        return None
    row = getattr(engine, KEY)
    _source(engine)
    if (type(row) is not dict or set(row) != {
            'source', 'reference', 'enabled', 'gm_id', 'reason', 'fingerprint'}
            or row['source'] != SOURCE or row['reference'] != REFERENCE
            or type(row['enabled']) is not bool
            or row['fingerprint'] != ROOT.fingerprint({k: v for k, v in row.items() if k != 'fingerprint'})):
        raise ValueError('actual Ground/Flying campaign adoption changed')
    _text(row['gm_id'], 'GM identity')
    _text(row['reason'], 'GM adoption reason')
    return row


def configure(engine, *, enabled, gm_id, reason):
    """Record an explicit GM choice; source admission alone never adopts it."""
    _source(engine)
    if type(enabled) is not bool:
        raise ValueError('explicit Ground/Flying adoption boolean required')
    _text(gm_id, 'GM identity')
    _text(reason, 'GM adoption reason')
    row = dict(source=SOURCE, reference=deepcopy(REFERENCE), enabled=enabled,
               gm_id=gm_id.strip(), reason=reason.strip())
    row['fingerprint'] = ROOT.fingerprint(row)
    setattr(engine, KEY, row)
    return deepcopy(row)


def defense_component(engine, attack, defense, target, ordinary):
    """Replace only the existing Ground/Flying component before composition.

    Engine calls this only in its ordinary component loop. A source-owned final
    defense chart therefore retains its existing authority and bypasses this.
    """
    row = validate(engine)
    if (row is not None and row['enabled'] and target.kind == 'pokemon'
            and attack == '땅' and defense == '비행'):
        return .5
    return ordinary


def _groundsource(engine, actor, move):
    import effects_ext as EXT
    import weapon_actions as WEAPONS
    keywords = set(EXT.keywords_for(actor, move))
    actual_range = WEAPONS.range_spec(engine, move, actor)
    keywords.update(str(actual_range.get('raw', '')).split(','))
    return bool({str(value).strip().casefold() for value in keywords}
                & {'지면통과', 'groundsource'})


def block_reason(engine, actor, target, move, mechanics):
    """Prevent this target being affected, including attacks with no AC roll."""
    row = validate(engine)
    if row is None or not row['enabled'] or target.kind != 'pokemon':
        return None
    if not _groundsource(engine, actor, move):
        return None
    import catalog_move_states as CATALOG
    if CATALOG.grounded(target):
        return None
    airborne = getattr(target, 'airborne', False)
    height = target.spec.get('_movement_altitude', 0)
    if (type(airborne) is not bool or type(height) not in (int, float)
            or not isfinite(height) or height < 0):
        raise ValueError('actual airborne state and nonnegative altitude required')
    if not airborne:
        return None  # An elevated supported surface is not flight.
    import effects_ext as EXT
    actual_type = EXT.effective_type(engine, actor, target, move, mechanics, consume=False)
    if actual_type == '땅':
        import field_effects as FIELD
        # Ask the existing owner whether this actor has ordinary live Levitate
        # immunity. Ignoring that Ability on one Move does not remove position.
        source = {'_ability': '부유'} if CATALOG.levitate_blocks(
            engine, target, dict(move, type=actual_type), {}) else None
        if FIELD.suppresses_ground_immunity(engine, target, source):
            return None
    return SOURCE
