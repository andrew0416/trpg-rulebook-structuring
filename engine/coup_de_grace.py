"""Current C07-192 target facts consumed by the native Full-action attack.

Physical binding is a current GM observation, separate from condition names,
grappling and Necrozma's willingness input. Ordinary attack owners stay native.
"""
from copy import deepcopy
import resolution_transaction as TX
import state_grants as GRANTS
import world_entities as WORLD

SOURCE = 'combat/coup-de-grace'
BINDING = 'coup_de_grace_binding'
MARKER = '_coup_de_grace'
SOURCE_REF = {
    'file': 'input/ch07-combat.md',
    'sha256': '57abb79c4f70c64246cd7927bffe2377e951bdc32dfa4c9a5c14b4ad97618c18',
}


def selected(rules):
    from source_context import verified_source
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected core Coup de Grace source required')
    verified_source(rules, SOURCE_REF, label='Coup de Grace')
    rule = rules.mech(SOURCE)
    if (rule.get('action') != 'full' or rule.get('auto_crit') is not True
            or rule.get('bonus_damage') != 5 or rule.get('bonus_doubled_by_crit') is not True):
        raise ValueError('native Coup de Grace needs its reviewed core action and damage policy')


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError('current Coup de Grace ' + label + ' required')


def bound(engine, actor):
    record = actor.custom_conditions.get(BINDING)
    if record is None:
        return False
    WORLD.require_actors(engine, actor)
    expected = {'rule', 'actor_id', 'properly_bound', 'completely_helpless', 'source', 'reason', 'sha256'}
    if (type(record) is not dict or set(record) != expected
            or record['rule'] != SOURCE or record['actor_id'] != actor.entity_id
            or type(record['properly_bound']) is not bool
            or type(record['completely_helpless']) is not bool
            or record['sha256'] != TX.request_fingerprint({k: v for k, v in record.items() if k != 'sha256'})):
        raise ValueError('current Coup de Grace binding changed or belongs to a different actor')
    _text(record['source'], 'binding source')
    _text(record['reason'], 'binding reason')
    return record['properly_bound'] and record['completely_helpless']


def observe(engine, actor, *, properly_bound, completely_helpless, source, reason):
    WORLD.require_actors(engine, actor)
    selected(engine.r)
    for value in (properly_bound, completely_helpless):
        if type(value) is not bool:
            raise ValueError('explicit boolean binding and helplessness observations required')
    _text(source, 'binding source')
    _text(reason, 'binding reason')

    def apply(staged, target):
        before = deepcopy(target.custom_conditions.get(BINDING))
        record = dict(rule=SOURCE, actor_id=target.entity_id, properly_bound=properly_bound,
                      completely_helpless=completely_helpless, source=source, reason=reason)
        record['sha256'] = TX.request_fingerprint(record)
        target.custom_conditions[BINDING] = record
        bound(staged, target)
        staged.gm._rec('최후의 일격 현재 결박·완전무력', before, deepcopy(record), reason, target)
        return deepcopy(record)

    return GRANTS.transition(engine, actor, apply, include_rulings=True)


def require_target(engine, actor, target):
    WORLD.require_actors(engine, actor, target)
    if actor.kind not in ('trainer', 'pokemon'):
        raise ValueError('Coup de Grace requires an actual Trainer or Pokemon')
    if target.dead or target.captured or not target.on_field:
        raise ValueError('Coup de Grace requires a present living target')
    physical = bound(engine, target)
    if not target.fainted and not physical:
        raise ValueError('Coup de Grace target must be fainted or properly bound and completely helpless')


def _require_sniper_contract(actor):
    if actor.abilities_suppressed:
        return
    # The selected corpus currently has only Playtest +3d10, not a native core
    # Sniper multiplier. This new attack mode must not silently merge them.
    names = {actor.r.ability_alias.get(name, name) for name in actor.abilities}
    if any('스나이퍼' in name or 'sniper' in name.casefold() for name in names):
        raise ValueError('Sniper Coup de Grace interaction needs a selected native source contract')


def prepare(engine, actor, target, move, mechanics):
    import effects_ext as EXT
    import turn as TURN
    import weapon_actions as WEAPONS
    selected(engine.r)
    require_target(engine, actor, target)
    _require_sniper_contract(actor)
    if (move.get('class') not in ('물리', '특수')
            or TURN.action_kind_of_move(engine, actor, move, mechanics) != 'standard'
            or WEAPONS.range_spec(engine, move, actor).get('shape')
            or move.get('_actual_targets') != (target,)
            or mechanics.get('zone') is not None
            or EXT.delayed_attack_spec(mechanics) is not None
            or any(effect.get('type') in ('set_up_move', 'multi_target_chain')
                   for effect in mechanics.get('effects_exec', ()))):
        raise ValueError('Coup de Grace currently needs a direct single-target damaging Standard attack')
    return dict(move, **{MARKER: dict(source=SOURCE, actor_id=actor.entity_id,
                                    target_id=target.entity_id, move_id=move['id'])})


def active(engine, actor, target, move):
    marker = move.get(MARKER)
    if marker is None:
        return False
    WORLD.require_actors(engine, actor, target)
    original = WORLD.actor_index(engine).get(marker.get('target_id')) if type(marker) is dict else None
    if original is None or marker != dict(source=SOURCE, actor_id=actor.entity_id,
                                         target_id=original.entity_id, move_id=move['id']):
        raise ValueError('Coup de Grace binding belongs to another declared attack')
    rows = [row for row in getattr(engine, '_move_completions', {}).values()
            if row.get('actor') is actor and row.get('move_id') == move['id']
            and row.get('move', {}).get(MARKER) == marker
            and row.get('targets') == [original] and row.get('started') == [original.entity_id]
            and original.entity_id not in row.get('results', {}) and row.get('phase') == 'targets'
            and row.get('round') == engine.round_no and row.get('seconds') == engine.elapsed_seconds]
    if len(rows) != 1:
        raise ValueError('actual started native Coup de Grace producer required')
    require_target(engine, actor, original)
    if target is not original:
        import move_defense_reactions as DEFENSE
        token = getattr(engine, '_defense_recipient_scope', None)
        if DEFENSE.require_recipient(engine, token, actor, target, move, rows[0]['id']) is not True:
            raise ValueError('actual Intercept recipient required for the declared Coup de Grace')
    return True


def damage_bonus(engine, actor, target, move, critical):
    if not active(engine, actor, target, move):
        return 0
    _require_sniper_contract(actor)
    if critical is not True:
        raise ValueError('actual Coup de Grace hit must remain a critical')
    return 10
