"""Observed Pledge Rainbow state over the existing effect/lifetime owners.

The observation certifies activation as a supplied world fact. It does not
execute, pay for, or infer the separately scoped combined-Move procedure.
One creator-held timer supplies the actual beneficiary team's contribution.
"""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json

import common_checks as C
import combat_timing as TIME
import effect_lifetime_policy as POLICY
import world_entities as WORLD


KEY = 'pledge_rainbow'
SOURCES = frozenset(('move/불꽃의맹세', 'move/물의맹세'))
UNTIL = {'event': 'round_end', 'after': 5}


def policy(rules):
    path = Path(__file__).resolve().parents[1] / 'data/pledge-state-policy.json'
    if not path.exists():
        path = Path(rules.root) / 'data/pledge-state-policy.json'
    result = json.loads(path.read_text(encoding='utf-8'))
    if (result.get('schema_version') != 1 or result.get('clause_id') != 'C10-348'
            or result.get('bonus') != 3 or result.get('rounds') != 5
            or set(result.get('sources', {})) != SOURCES):
        raise ValueError('Pledge Rainbow state contract changed')
    for relative, digest in result['source_files'].items():
        source = Path(rules.root) / relative
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError('Pledge Rainbow reviewed source changed: ' + relative)
    with (Path(rules.root) / 'input/db/moves.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    for source, anchor in result['sources'].items():
        cells = rows[anchor['record'] - 1]
        digest = hashlib.sha256(json.dumps(cells, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        if (cells[0] != source.split('/', 1)[1] or digest != anchor['row_sha256']
                or '5라운드 동안 지속되는 무지개' not in cells[7]):
            raise ValueError('Pledge Rainbow exact CSV producer changed')
    return result


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' required')
    return value


def _effect(effect, source, rules):
    data = policy(rules)
    if source not in SOURCES or rules._selected_rule(source) != source:
        raise ValueError('reviewed selected Rainbow-producing Pledge source required')
    expected = {'type', 'rainbow_observed', 'request_id', 'reason', 'beneficiary_side', 'target', 'until'}
    if (not isinstance(effect, dict) or set(effect) != expected or effect.get('type') != 'pledge'
            or effect.get('rainbow_observed') is not True or effect.get('target') != 'self'
            or effect.get('until') != UNTIL):
        raise ValueError('exact observed Rainbow payload and five-round lifetime required')
    for key in ('request_id', 'reason', 'beneficiary_side'):
        _text(effect[key], 'actual Rainbow ' + key)
    return {'clause_id': data['clause_id'], 'value': data['bonus'], 'side': effect['beneficiary_side']}


def live(actor):
    return [record for record in TIME.records(actor) if KEY in record]


def prepare(engine, actor, target, effect, source):
    payload = _effect(effect, source, engine.r)
    WORLD.require_actors(engine, actor, target)
    if target is not actor or payload['side'] != actor.side:
        raise ValueError('Rainbow observation needs its actual creator and current team')
    import move_state as MOVES
    if source not in MOVES.known(engine.r, {'moves': actor.moves}):
        raise ValueError('Rainbow observation needs an actual known producer Move')
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('Rainbow observation requires an actual open combat round')
    for owner in WORLD.actor_index(engine).values():
        if any(row[KEY]['side'] == payload['side'] for row in live(owner)):
            raise ValueError('overlapping team Rainbow composition requires an explicit ruling')
    record = POLICY.prepare(engine, actor, target, effect, source)
    record.update(pledge_rainbow=payload, encounter_end=True)
    return record


def _observations(engine, actor, request_id):
    return [row for row in getattr(engine, '_effect_dispatch_receipts', {}).values()
            if row.get('actor') is actor and isinstance(row.get('effect'), dict)
            and row['effect'].get('rainbow_observed') is True
            and row['effect'].get('request_id') == request_id]


def _result(row):
    return {'source_id': row['source_id'], 'occurrence': row['occurrence'],
            'side': row['effect']['beneficiary_side'], 'request_id': row['effect']['request_id']}


def observe(engine, actor, *, source_id, request_id, reason):
    """Explicitly observe activation; action payment belongs to its procedure."""
    import state_grants as GRANTS
    import effects as FX
    _text(request_id, 'actual Rainbow request'); _text(reason, 'actual Rainbow activation reason')
    WORLD.require_actors(engine, actor)

    def apply(staged, owner):
        prior = _observations(staged, owner, request_id)
        if prior:
            if (len(prior) != 1 or prior[0].get('status') != 'completed'
                    or prior[0]['source_id'] != source_id or prior[0]['effect']['reason'] != reason):
                raise ValueError('Rainbow request already belongs to a different observation')
            _effect(prior[0]['effect'], source_id, staged.r)
            return _result(prior[0])
        effect = {'type': 'pledge', 'rainbow_observed': True, 'target': 'self',
                  'request_id': request_id, 'reason': reason, 'beneficiary_side': owner.side,
                  'until': deepcopy(UNTIL)}
        prepare(staged, owner, owner, effect, source_id)
        result = FX.run_effects(staged, owner, owner, [effect], {'hit': True}, source_id)
        if result != (1, 0) or result.pending:
            raise ValueError('observed Rainbow could not install its actual lifetime')
        row = _observations(staged, owner, request_id)[0]
        staged.log('    무지개 발동 관측: 동료 특수효과 발동범위 +3, 5라운드 — ' + reason, source_id)
        return _result(row)
    return GRANTS.transition(engine, actor, apply)


def validate_world(engine, index):
    sides = set()
    for owner in index.values():
        requests = set()
        for row in getattr(engine, '_effect_dispatch_receipts', {}).values():
            effect = row.get('effect', {})
            if row.get('actor') is not owner or not isinstance(effect, dict) or effect.get('rainbow_observed') is not True:
                continue
            payload = _effect(effect, row.get('source_id'), engine.r)
            if row.get('target') is not owner or effect['request_id'] in requests:
                raise ValueError('Rainbow observation has a different actual owner or duplicate request')
            requests.add(effect['request_id'])
            if row.get('status') != 'completed':
                continue
            contract = row.get('lifetime_contracts', {}).get(owner.entity_id)
            if not contract or contract.get('contribution') != {KEY: payload}:
                raise ValueError('Rainbow observation lost its actual team contribution')
            plan = contract['policy']
            if plan.get('declaration') != {'until': UNTIL} or plan.get('until') != UNTIL:
                raise ValueError('Rainbow lifetime differs from its five-round state')
            C.integer(plan.get('started_round'), 'actual Rainbow activation round', 1, engine.round_no)
        for record in live(owner):
            if POLICY.KEY not in record or record.get('encounter_end') is not True:
                raise ValueError('Rainbow must use the shared combat lifetime')
            row = getattr(engine, '_effect_dispatch_receipts', {}).get(record.get('effect_receipt'))
            if not row or row.get('actor') is not owner:
                raise ValueError('Rainbow has no actual observed producer')
            payload = _effect(row['effect'], record['source'], engine.r)
            if record[KEY] != payload or payload['side'] in sides:
                raise ValueError('Rainbow team contribution changed or overlaps')
            sides.add(payload['side'])
            started = record[POLICY.KEY]['started_round']
            if engine.round_no > started + 4:
                raise ValueError('Rainbow survived its fifth round boundary')
    return True


def effect_range_bonus(engine, actor, move):
    """Read live team state only; accuracy, criticals and die faces stay intact."""
    if not move:
        return 0
    index = WORLD.actor_index(engine)
    if not any(live(owner) for owner in index.values()):
        return 0
    WORLD.require_actors(engine, actor)
    validate_world(engine, index)
    return sum(record[KEY]['value'] for owner in index.values() for record in live(owner)
               if record[KEY]['side'] == actor.side)
