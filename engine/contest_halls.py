"""Actual hall type observations and native completed-contest Ribbon rewards.

Progress, scores and winner decisions stay with the existing format owners.
The physical hall and Trainer.spec.ribbons are the only new persisted state.
"""
from copy import deepcopy

import resolution_transaction as TX
import state_grants as GRANTS
import world_entities as WORLD

SOURCE = 'ch08-contests/콘테스트를-소개합니다/콘테스트-서킷'
KEY = 'ribbons'


def _source(*readers):
    for reader in readers:
        if reader._selected_rule(SOURCE) != SOURCE:
            raise ValueError('selected Contest Circuit source required')


def _hall(engine, hall_id):
    hall_id = WORLD._text(hall_id, 'actual Contest Hall identity')
    row = getattr(engine, '_physical_objects', {}).get(hall_id)
    if (WORLD.entity_index(engine).get(hall_id) is not row or not isinstance(row, dict)
            or row.get('kind') != 'physical_object'):
        raise ValueError('actual registered physical Contest Hall required')
    WORLD.require_usable_object(row)
    return row


def observe_hall(host, engine, hall_id, contest_types, *, reason):
    """Attach the GM-observed offered types to an existing physical venue."""
    _source(host.r, engine.r)
    WORLD._text(reason, 'Contest Hall observation reason')
    _hall(engine, hall_id)
    ring = host.r.mech('contest/type-match')['ring']
    if (type(contest_types) not in (list, tuple) or not contest_types
            or any(type(value) is not str or value not in ring for value in contest_types)
            or len(set(contest_types)) != len(contest_types)):
        raise ValueError('a nonempty distinct subset of the five Contest types required')
    fact = {'source': SOURCE, 'types': tuple(contest_types), 'reason': reason}
    def apply(staged, _):
        hall = _hall(staged, hall_id)
        before = deepcopy(hall.get('contest_hall'))
        hall['contest_hall'] = deepcopy(fact)
        staged.gm._rec('Contest Hall '+hall_id, before, fact, reason)
        return deepcopy(fact)
    return GRANTS.transition(engine, None, apply, include_rulings=True)


def native_context(host, participants, *, historical=False):
    """Validate real bindings; a wholly standalone contest has no Trainer payee."""
    participants = tuple(participants)
    bindings = host._native_intro_bindings
    if not any(c in bindings for c in participants):
        return None
    if any(c not in bindings for c in participants):
        raise ValueError('every native competitor needs its original Pokemon/Trainer binding')
    engines = {bindings[c][0] for c in participants}
    if len(engines) != 1:
        raise ValueError('one actual native contest world required')
    engine = next(iter(engines))
    _source(host.r, engine.r)
    seen = set()
    for contestant in participants:
        _, pokemon, trainer, _, _ = bindings[contestant]
        WORLD.require_actors(engine, pokemon, trainer)
        # A completed occurrence retains its original Trainer after a transfer.
        if (pokemon.kind != 'pokemon' or trainer.kind != 'trainer'
                or (not historical and pokemon.spec.get('trainer_id') != trainer.entity_id)
                or pokemon.entity_id in seen):
            raise ValueError('distinct actual Pokemon and their original Trainer owners required')
        seen.add(pokemon.entity_id)
    return engine


def _offers(host, fact, contest_type):
    ring = host.r.mech('contest/type-match')['ring']
    if (type(fact) is not dict or fact.get('source') != SOURCE
            or type(fact.get('types')) not in (list, tuple) or not fact['types']
            or any(type(value) is not str or value not in ring for value in fact['types'])
            or len(set(fact['types'])) != len(fact['types'])
            or contest_type not in fact['types']):
        raise ValueError('the actual observed Contest Hall must offer this type')


def admit_hall(host, participants, contest_type, hall_id):
    engine = native_context(host, participants)
    if engine is None:
        raise ValueError('a Contest Hall starts an actual native contest')
    fact = _hall(engine, hall_id).get('contest_hall')
    _offers(host, fact, contest_type)
    return {'id': hall_id, 'source': SOURCE, 'types': tuple(fact['types'])}


def validate_hall(host, state):
    if 'hall' not in state:
        return
    hall = state['hall']
    if type(hall) is not dict or set(hall) != {'id', 'source', 'types'}:
        raise ValueError('invalid original Contest Hall binding')
    if state['contract'][2] != 'standard' or 'rotation' in state:
        raise ValueError('fixed-type standard Hall entry required')
    if state['phase'] == 'complete':
        # The occurrence owns its original observation, even after a venue closes.
        WORLD._text(hall['id'], 'original Contest Hall identity')
        _offers(host, hall, state['contract'][1])
        return
    expected = admit_hall(host, state['contract'][0], state['contract'][1], hall['id'])
    if hall != expected:
        raise ValueError('original Contest Hall observation changed')


def _contest_result(host):
    festival = getattr(host, '_festival_run', None)
    paired = host._paired_run
    state = festival or paired or host._standard_run
    if state is None:
        return None
    participants = tuple(state['contract'][0])
    rotation = state.get('rotation')
    if rotation is not None:
        participants = tuple(c for team in rotation['teams'] for c in team)
    engine = native_context(host, participants, historical=state['phase'] == 'complete')
    if engine is None:
        return None
    kind = ('festival' if festival else 'trainer-'+state['model'] if paired
            else 'rotation' if rotation is not None else state['contract'][2])
    identity = {'format': kind, 'contest_id': state['id'],
                'entrants': tuple(sorted(host._native_intro_bindings[c][1].entity_id
                                         for c in participants)),
                'native_participants': tuple(sorted(c.entity_id for c in participants))}
    winners = ()
    if state['phase'] == 'complete':
        if festival:
            import contest_festival as FESTIVAL
            FESTIVAL.validate(host, set(host._native_intro_bindings))
            winners = (state['winner'],)
        else:
            anchors = state['contract'][0]
            if rotation is not None:
                import contest_rotation as ROTATION
                totals = ROTATION.scores(rotation)
                scores = {c: totals[c][0]-totals[c][1] for c in anchors}
            elif paired:
                scores = {c: c.appeal-c.fumble+state['pairs'][c].appeal-state['pairs'][c].fumble
                          for c in anchors}
            else:
                scores = {c: c.appeal-c.fumble for c in anchors}
            high = max(scores.values())
            leaders = [c for c in anchors if scores[c] == high]
            if tuple(state['result']) != tuple(sorted(anchors, key=lambda c: -scores[c])):
                raise ValueError('native completed result disagrees with its current scores')
            if len(leaders) == 1:
                winners = (tuple(rotation['teams'][anchors.index(leaders[0])])
                           if rotation is not None else (leaders[0],))
    return engine, identity, state, winners


def _receipt(identity, trainer_ids, pokemon_ids, contest_type, hall_id=None):
    return {'id': 'ribbon/'+TX.json_fingerprint(identity), 'source': SOURCE,
            **deepcopy(identity), 'winner_trainer_ids': sorted(set(trainer_ids)),
            'winner_pokemon_ids': sorted(set(pokemon_ids)),
            'contest_type': contest_type, 'hall_id': hall_id}


def _existing(engine, ribbon_id, expected):
    found = {}
    for actor in WORLD.actor_index(engine).values():
        if actor.kind != 'trainer':
            continue
        ribbons = actor.spec.get(KEY, {})
        if type(ribbons) is not dict:
            raise ValueError('actual Trainer Ribbon state must be a mapping')
        if ribbon_id in ribbons:
            found[actor.entity_id] = ribbons[ribbon_id]
    if found and (expected is None or set(found) != set(expected['winner_trainer_ids'])
                  or any(row != expected for row in found.values())):
        raise ValueError('Ribbon recipients or original native completion disagree')
    return bool(found)


def _grant(engine, record):
    if _existing(engine, record['id'], record):
        return deepcopy(record)
    index = WORLD.actor_index(engine)
    recipients = tuple(index[uid] for uid in record['winner_trainer_ids'])
    def apply(staged, _, *trainers):
        _source(staged.r)
        if _existing(staged, record['id'], record):
            return deepcopy(record)
        for trainer in trainers:
            if trainer.kind != 'trainer':
                raise ValueError('actual winning Trainer required')
            trainer.spec.setdefault(KEY, {})[record['id']] = deepcopy(record)
        staged.gm._rec('Contest Ribbon '+record['id'], None, record,
                       'native completed contest '+record['contest_id'])
        return deepcopy(record)
    return GRANTS.transition(engine, None, apply, participants=recipients, include_rulings=True)


def validate_contest(host):
    """Codec/claim boundary; validation reads the native owner and never pays."""
    state = host._standard_run
    if state is not None:
        validate_hall(host, state)
    outcome = _contest_result(host)
    if outcome is None:
        return None
    engine, identity, state, winners = outcome
    record = None
    if winners:
        bindings = [host._native_intro_bindings[c] for c in winners]
        record = _receipt(identity, [binding[2].entity_id for binding in bindings],
                          [binding[1].entity_id for binding in bindings],
                          state['contract'][1], state.get('hall', {}).get('id'))
    ribbon_id = 'ribbon/'+TX.json_fingerprint(identity)
    _existing(engine, ribbon_id, record)
    return engine, record


def award_contest(host):
    """Native end/retry adapter; incomplete and unresolved-tie states never pay."""
    outcome = validate_contest(host)
    if outcome is None or outcome[1] is None:
        return None
    return _grant(*outcome)


def award_battle(engine, contest_id):
    """Use the Battle Contest owner's actual terminal Trainer result."""
    import battle_contest as BATTLE
    _, state, index = BATTLE.validate(engine, contest_id)
    _source(engine.r)
    members = [index[uid] for side in state['sides'] for uid in side['roster']]
    trainers = [index[side['trainer_id']] for side in state['sides']]
    WORLD.require_actors(engine, *members, *trainers)
    identity = {'format': 'battle', 'contest_id': contest_id,
                'host_trainer_id': state['host_trainer_id'],
                'entrants': tuple(actor.entity_id for actor in (*trainers, *members))}
    record = None
    if state['status'] == 'complete':
        scores = [BATTLE._score(state, side) for side in (0, 1)]
        side = None if scores[0] == scores[1] else 0 if scores[0] > scores[1] else 1
        winner = None if side is None else state['sides'][side]['trainer_id']
        if state.get('winner_trainer_id') != winner or state.get('scores') != scores:
            raise ValueError('actual Battle Contest terminal winner disagrees')
        if winner is not None:
            record = _receipt(identity, [winner], state['sides'][side]['roster'],
                              state['contest_type'])
    _existing(engine, 'ribbon/'+TX.json_fingerprint(identity), record)
    return None if record is None else _grant(engine, record)
