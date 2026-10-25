"""Source-bound Priority declarations over the native between-turn loan path.

The printed header grants ordinary Priority. Conditional body keywords do not.
Shocking Speed is one explicit, paid producer of Advanced entitlement.
"""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
import re

import action_lifecycle as ACTION
import frequency as FREQUENCY
import initiative_interrupts as INTERRUPTS
import move_state as MOVES
import state_grants as GRANTS
import world_entities as WORLD

POLICY = 'data/priority-actions-policy.json'
SHOCKING = 'feat/쇼킹-스피드'


def definition(rules):
    # Do not add a redundant warm Rules cache to the durable rules fingerprint.
    policy = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf8'))
    if policy.get('schema_version') != 1 or policy['shocking_speed'] != {
            'source': SHOCKING, 'prerequisite': 'feat/락다운',
            'frequency': {'kind': 'scene', 'uses': 2}, 'action': 'free',
            'type': '전기', 'minimum_type_link_rank': 5}:
        raise ValueError('reviewed Priority source policy required')
    for row in policy['authority'].values():
        lines = (Path(rules.root) / row['file']).read_text(encoding='utf8').splitlines()
        actual = '\n'.join(lines[row['start'] - 1:row['end']])
        if actual != row['excerpt'] or hashlib.sha256(actual.encode()).hexdigest() != row['excerpt_sha256']:
            raise ValueError('Priority source excerpt changed')
    return policy


def _move(rules, move_id):
    if type(move_id) is not str or move_id not in rules.moves:
        raise ValueError('actual selected Move identity required')
    move = rules.move(move_id)
    if move['id'] != move_id or move.get('class') == '항상':
        raise ValueError('exact selected active Move required')
    source = move.get('_source', {})
    span = source.get('record_span')
    if source.get('file') != 'db/moves.csv' or not isinstance(span, list) or len(span) != 2 or span[0] != span[1]:
        raise ValueError('actual selected CSV Move source required')
    policy = definition(rules)
    path = Path(rules.root) / 'input/db/moves.csv'
    if hashlib.sha256(path.read_bytes()).hexdigest() != policy['moves_csv_sha256']:
        raise ValueError('Priority Move source corpus changed')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    if type(span[0]) is not int or not 1 <= span[0] <= len(rows):
        raise ValueError('actual selected Move source row required')
    row = rows[span[0] - 1]
    if (len(row) < 23 or (move.get('name'), move.get('range'), move.get('frequency'),
                         move.get('class'), move.get('type'), move.get('eng')) !=
            (row[0], row[6], row[4], row[9], row[10], row[22])):
        raise ValueError('selected Move header differs from actual printed source')
    return deepcopy(move)


def classify(rules, move_id):
    """Inspect only a source-authenticated header; never scan narrative keywords."""
    move = _move(rules, move_id)
    tokens = [token.strip() for token in move['range'].split(',')]
    priority = [token for token in tokens if token.startswith('우선')]
    if not priority:
        return None
    if len(priority) != 1:
        return {'variant': 'unknown', 'move_id': move_id}
    token = re.sub(r'\s+', '', priority[0])
    variant = {'우선': 'plain', '우선(제한)': 'limited', '우선(고급)': 'advanced'}.get(token, 'unknown')
    return {'variant': variant, 'move_id': move_id}


def _owned_move(engine, actor, move_id):
    owned = MOVES.owned_list(actor.spec, 'moves', actor.moves)
    if move_id not in [engine.r.resolve_move(uid) for uid in owned]:
        raise ValueError('Priority requires the actual learned selected Move')
    return _move(engine.r, move_id)


def _feature(owner, source, aliases):
    feats = owner.spec.get('feats', [])
    if not isinstance(feats, list) or sum(value in (source, *aliases) for value in feats) != 1:
        raise ValueError('one actual acquired ' + source + ' required')
    if owner.r._selected_rule(source) != source:
        raise ValueError('selected Priority feature variant required')


def _prepare(engine, actor, target, move_id, trainer, stat_trainer=None, chronicler=None, ambush=None, weapon_id=None, signature_technique=False):
    WORLD.require_actors(engine, actor, target)
    if engine.r._selected_rule('action_type/우선-행동') != 'action_type/우선-행동':
        raise ValueError('selected Priority action source required')
    INTERRUPTS.between_trigger(engine)
    import vision_impairment as VISION
    if VISION.accuracy_level(engine, actor) == 'total':
        raise ValueError('Total Blindness prohibits declared Priority Moves')
    import effect_lifetimes as LIFETIMES
    if LIFETIMES.forbids(actor, 'priority'):
        raise ValueError('current effect prohibits Priority actions')
    if any(x.dead or x.fainted or not x.on_field or x.captured for x in (actor, target)):
        raise ValueError('actual eligible Priority participants required')
    move = _owned_move(engine, actor, move_id)
    policy = definition(engine.r)
    if signature_technique:
        import ace_trainer as ACE
        authority=ACE.bloodied_authority(engine,actor,move_id)
        if authority is None:
            raise ValueError('actual Bloodied Speed investment required')
        return move,authority['source']
    if chronicler is not None:
        # Situational Awareness: the ally's next action is Priority (Advanced);
        # an acted ally forgoes its next-round turn through the ordinary loan location.
        import chronicler as CHRONICLER
        token=CHRONICLER.consume_priority(engine,actor,chronicler)
        return move,CHRONICLER.CINEMATIC
    if stat_trainer is not None:
        import stat_ace as STAT
        WORLD.require_actors(engine,stat_trainer)
        if STAT.owner(engine,actor,STAT.MANEUVER,'spe') is not stat_trainer:raise ValueError('actual Speed Stat Maneuver owner required')
        found=classify(engine.r,move_id)
        if found is None:
            _,_,due=INTERRUPTS._loan_location(engine,actor)
            if due!=engine.round_no:raise ValueError('ordinary Stat Maneuver Priority requires this-round unacted right')
        elif found['variant']!='plain':raise ValueError('Stat Maneuver upgrades only ordinary or plain Priority Moves')
        return move,STAT.MANEUVER
    if ambush is not None:
        prepared=__import__('weapon_actions').prepare(engine,actor,move,weapon_id)
        return prepared,__import__('rogue').prepare_ambush(engine,actor,prepared,ambush)
    if trainer is None:
        found = classify(engine.r, move_id)
        if found is None or found['variant'] != 'plain':
            raise ValueError('actual unconditional plain Priority header required; source producer needed for variants')
        # A closed actual schedule slot, not an old budget or a caller flag,
        # determines whether this round's ordinary right has already been used.
        _, _, due = INTERRUPTS._loan_location(engine, actor)
        if due != engine.round_no:
            raise ValueError('ordinary Priority requires this round unacted turn right')
        return move, move_id
    WORLD.require_actors(engine, trainer)
    if trainer.kind != 'trainer':
        raise ValueError('Shocking Speed requires its actual trainer feature owner')
    if WORLD.identity_field(engine, actor, 'owner_id') != trainer.entity_id:
        raise ValueError('Shocking Speed requires the feature owner\'s actual owned Pokemon')
    _feature(trainer, SHOCKING, ('쇼킹 스피드', 'Shocking Speed'))
    _feature(trainer, 'feat/락다운', ('락다운', 'Lockdown'))
    import class_passive_combat as CLASSES
    if CLASSES.type_link_rank(engine, trainer, '전기') < policy['shocking_speed']['minimum_type_link_rank']:
        raise ValueError('Shocking Speed requires Expert electric Type Link skill')
    import effects_ext as EFFECTS
    mm = engine.r.move_mech(move_id)[0]
    effective = EFFECTS.effective_type(engine, actor, target, move, mm, consume=False)
    if actor.kind != 'pokemon' or '전기' not in actor.types or effective != '전기':
        raise ValueError('Shocking Speed requires Electric Pokemon using an actual Electric Move')
    if FREQUENCY.move_frequency(engine, move_id, actor)[0] != 'at_will':
        raise ValueError('Shocking Speed requires actual at-will Move frequency')
    if not FREQUENCY.activation_allowed(trainer, SHOCKING, policy['shocking_speed']['frequency'], engine=engine):
        raise ValueError('Shocking Speed scene frequency exhausted')
    return move, SHOCKING


def use(engine, actor, target, move_id, *, shocking_speed=None, stat_maneuver=None, situational_awareness=None, ambush=None, weapon_id=None, signature_technique=False):
    """Use the declared Move now and keep its whole native turn open.

    Remaining actions and ending the turn use the existing Engine APIs. Native
    passive/Heavy waits preserve their paid prefix; arbitrary errors roll back.
    """
    WORLD.require_actors(engine, actor, target)
    producers=[x for x in (shocking_speed,stat_maneuver,situational_awareness) if x is not None]
    if type(signature_technique)is not bool:raise ValueError('actual Signature Technique choice required')
    if len(producers)+int(ambush is not None)+int(signature_technique)>1:raise ValueError('one actual Priority producer required')
    if weapon_id is not None and ambush is None:raise ValueError('weapon choice requires its actual Ambush producer')
    if shocking_speed is not None:
        WORLD.require_actors(engine, shocking_speed)
    if situational_awareness is not None:
        WORLD.require_actors(engine, situational_awareness)
    pending = []
    extra = () if not producers else (producers[0],)
    def apply(e, a, t, *owners):
        trainer = owners[0] if owners and shocking_speed is not None else None
        stat_trainer=owners[0] if owners and stat_maneuver is not None else None
        chronicler=owners[0] if owners and situational_awareness is not None else None
        move, source = _prepare(e, a, t, move_id, trainer,stat_trainer,chronicler,ambush,weapon_id,signature_technique)
        if stat_trainer is not None:
            import stat_ace as STAT
            STAT._consume(e,stat_trainer,a,'spe',move_id)
        if trainer is not None:
            ACTION.triggered_free_action(e, trainer, SHOCKING)
            FREQUENCY.consume_activation(trainer, SHOCKING, definition(e.r)['shocking_speed']['frequency'], engine=e)
        request = {'id': 'priority-move', 'actor_id': a.entity_id, 'source': source,
                   'priority': 0, 'mode': 'borrow_turn', 'payment': 'future_turn',
                   'budget': None, 'clock': 'owner_turn', 'settlement_clock': 'none'}
        queued = INTERRUPTS.queue(e, [request], trigger=INTERRUPTS.between_trigger(e))
        INTERRUPTS.begin(e, queued['window_id'], request['id'])
        if ambush is not None:
            ACTION.triggered_free_action(e,a,ambush)
            FREQUENCY.consume_activation(a,ambush,{'kind':'scene','uses':1},engine=e)
        before = set(getattr(e, '_move_completions', {}))
        try:
            if ambush is not None:e._rogue_ambush={'actor':a,'move_id':move_id,'ability':ambush}
            try:result = e.use_move_on(a, t, move_id, e.everyone,weapon_id=weapon_id)
            finally:
                if hasattr(e,'_rogue_ambush'):del e._rogue_ambush
        except Exception as error:
            if GRANTS.record_native_pending(e, error, pending):
                return None
            raise
        completions = [row for key, row in e._move_completions.items() if key not in before
                       and row['actor'] is a and row['move_id'] == move_id]
        if not completions:
            raise ValueError('native Priority Move did not activate')
        return {'window_id': queued['window_id'], 'request_id': request['id'],
                'move_id': move_id, 'source': source, 'result': result}
    result = GRANTS.transition(engine, actor, apply, participants=(target, *extra),
                               include_rulings=True, include_grid=engine.grid is not None)
    if pending:
        exception, event_id = pending[0]
        raise exception(event_id)
    return result
