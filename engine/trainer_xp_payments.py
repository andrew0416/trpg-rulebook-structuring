"""Actual trainer XP-bank payments; levels are never a spendable reserve."""
from copy import deepcopy
import common_checks as C
import resolution_transaction as TX

KEY = 'trainer_xp_payments'
SOURCE = 'trainer/experience'


def validate(actor):
    rows = actor.spec.get(KEY, {})
    if type(rows) is not dict:
        raise ValueError('trainer XP payment ledger must be a mapping')
    if not rows:
        return
    if actor.kind != 'trainer':
        raise ValueError('trainer XP payments require an actual trainer')
    C.integer(actor.spec.get('exp_bank', 0), 'actual trainer XP bank', 0)
    for request, row in rows.items():
        if type(request) is not str or not request.strip() or type(row) is not dict:
            raise ValueError('identified trainer XP payment required')
        intent, result = row.get('intent'), row.get('result')
        if type(intent) is not dict or type(result) is not dict:
            raise ValueError('trainer XP payment intent and result required')
        amount = C.integer(intent.get('amount'), 'paid trainer XP', 1)
        before = C.integer(result.get('bank_before'), 'pre-payment bank', amount)
        after = C.integer(result.get('bank_after'), 'post-payment bank', 0)
        if before - after != amount or result.get('amount') != amount or result.get('entity_id') != actor.entity_id:
            raise ValueError('trainer XP payment disagrees with actual debit')
        if result.get('level_before') != result.get('level_after'):
            raise ValueError('trainer XP payment cannot change a level')
        if intent.get('refund_policy') not in ('none', 'before_use'):
            raise ValueError('explicit trainer XP refund policy required')
        if row.get('used') is not None and (type(row['used']) is not str or not row['used'].strip()):
            raise ValueError('actual irreversible trainer XP use event required')
        refund = row.get('refund')
        if refund is not None:
            if intent['refund_policy'] != 'before_use' or row.get('used') is not None:
                raise ValueError('used or nonrefundable trainer XP cannot be refunded')
            if type(refund) is not dict or refund.get('amount') != amount:
                raise ValueError('trainer XP refund differs from actual payment')
            if refund.get('bank_after', -1) - refund.get('bank_before', 0) != amount:
                raise ValueError('trainer XP refund bank evidence mismatch')


def _actor(engine, actor):
    import world_entities as W
    W.require_actors(engine, actor)
    if actor.kind != 'trainer':
        raise ValueError('actual trainer XP bank required')
    validate(actor)


def spend(engine, actor, amount, *, source, reason, request_id, refund_policy):
    """Host-declared payment, with the policy recorded before the actual debit."""
    import state_grants as G
    _actor(engine, actor)
    C.integer(amount, 'trainer XP payment', 1)
    if any(type(v) is not str or not v.strip() for v in (source, reason)):
        raise ValueError('selected XP payment source and reason required')
    if source not in engine.r.units or engine.r._selected_rule(source) != source:
        raise ValueError('selected XP payment source changed')
    if refund_policy not in ('none', 'before_use'):
        raise ValueError('explicit XP payment refund policy required')
    intent = {'amount': amount, 'source': source, 'reason': reason,
              'entity_id': actor.entity_id, 'refund_policy': refund_policy,
              'selected_policy': deepcopy(engine.r.mech(source))}
    prior = TX.replay_result(actor.spec.get(KEY, {}), request_id, intent)
    if prior is not None:
        return prior['result']
    balance = C.integer(actor.spec.get('exp_bank', 0), 'actual trainer XP bank', 0)
    if balance < amount:
        raise ValueError('insufficient banked trainer XP; levels cannot pay the difference')

    def apply(e, c):
        before = c.spec.get('exp_bank', 0)
        c.spec['exp_bank'] = before - amount
        result = {'request_id': request_id, 'entity_id': c.entity_id, 'amount': amount,
                  'bank_before': before, 'bank_after': c.spec['exp_bank'],
                  'level_before': c.level, 'level_after': c.level, 'source': source}
        c.spec.setdefault(KEY, {})[request_id] = {'intent': deepcopy(intent),
            'result': deepcopy(result), 'used': None, 'refund': None}
        validate(c)
        e.log('    ' + c.name + ': trainer XP -' + str(amount), source)
        return deepcopy(result)
    return G.transition(engine, actor, apply)


def mark_used(engine, actor, payment_id, *, event_id):
    """The real retraining consumer commits irreversible use, once."""
    import state_grants as G
    _actor(engine, actor)
    if type(event_id) is not str or not event_id.strip():
        raise ValueError('actual retraining use event required')
    row = actor.spec.get(KEY, {}).get(payment_id)
    if row is None or row['refund'] is not None:
        raise ValueError('active XP payment required')
    if row['used'] not in (None, event_id):
        raise ValueError('XP payment already used by a different retraining event')
    def apply(e, c):
        c.spec[KEY][payment_id]['used'] = event_id
        validate(c)
        return deepcopy(c.spec[KEY][payment_id]['result'])
    return G.transition(engine, actor, apply)


def refund(engine, actor, payment_id, *, reason):
    import state_grants as G
    _actor(engine, actor)
    if type(reason) is not str or not reason.strip():
        raise ValueError('explicit XP refund reason required')
    row = actor.spec.get(KEY, {}).get(payment_id)
    if row is None:
        raise ValueError('actual XP payment required')
    if row['refund'] is not None:
        if row['refund']['reason'] != reason:
            raise ValueError('XP refund input changed')
        return deepcopy(row['refund'])
    if row['intent']['refund_policy'] != 'before_use' or row['used'] is not None:
        raise ValueError('trainer XP payment is not refundable')
    def apply(e, c):
        paid = c.spec[KEY][payment_id]
        amount = paid['intent']['amount']
        before = C.integer(c.spec.get('exp_bank', 0), 'actual trainer XP bank', 0)
        c.spec['exp_bank'] = before + amount
        result = {'payment_id': payment_id, 'amount': amount, 'reason': reason,
                  'bank_before': before, 'bank_after': c.spec['exp_bank']}
        paid['refund'] = deepcopy(result)
        validate(c)
        return result
    return G.transition(engine, actor, apply)


def retraining(engine, actor, kind, *, request_id, reason, refund_policy):
    """Native C02-159 bank consumer; choice replacement remains its caller's job."""
    kinds = {'edge': 'edge', 'feature': 'feat', 'stat_point': 'stat_point'}
    if kind not in kinds:
        raise ValueError('explicit edge or feature retraining required')
    cost = engine.r.mech(SOURCE).get('retrain_cost', {}).get(kinds[kind])
    C.integer(cost, 'selected retraining XP cost', 1)
    return spend(engine, actor, cost, source=SOURCE, reason=reason,
                 request_id=request_id, refund_policy=refund_policy)
