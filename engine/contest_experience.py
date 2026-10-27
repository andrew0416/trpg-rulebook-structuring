"""S-002: quote completed Contest outcomes; explicitly pay through native growth."""
from copy import deepcopy

import arithmetic as A
import arithmetic_policy as M
import contest_halls as HALLS
import downtime as DT
import resolution_transaction as TX
import state_fields as F
import state_grants as GRANTS

SOURCE = 'ch08-contests/포켓몬-콘테스트-플레이/콘테스트-경험치'
KEY = 'contest_xp_awards'


def _defeated(host, state, contestant):
    if host._festival_run is not None:
        # Use finalized elimination/advancement and scoped winner adjudication.
        # Equal raw scores do not undo a native decision that settled the placing.
        eliminated = state['eliminated']
        if contestant in eliminated:
            return tuple(eliminated[:eliminated.index(contestant)])
        scores = state['history'][-1]['scores']
        winner = state['winner']
        return tuple(eliminated) + tuple(c for c in state['result'] if c is not contestant
            and (contestant is winner or (c is not winner and scores[c] < scores[contestant])))
    rotation = state.get('rotation')
    anchors = state['contract'][0]
    if rotation is not None:
        scores = HALLS.terminal_scores(host, state)
        team = next(i for i, members in enumerate(rotation['teams']) if contestant in members)
        score = scores[anchors[team]]
        return tuple(c for i, members in enumerate(rotation['teams'])
                     if scores[anchors[i]] < score
                     for c in members)
    scores = HALLS.terminal_scores(host, state)
    return tuple(c for c in anchors if scores[c] < scores[contestant])


def _quote(host, contestant, significance):
    policy = host.r.mech('contest/experience')
    result = HALLS._contest_result(host)
    if result is None or result[2]['phase'] != 'complete':
        raise ValueError('completed native Contest or whole Festival result required')
    engine, identity, state, _ = result
    for reader in (host.r, engine.r):
        M.validate_source(reader)
        if reader._selected_rule(SOURCE) != SOURCE:
            raise ValueError('selected Contest experience source required')
    if (policy['decision'] != 'S-002' or policy['defeated'] != 'strict_lower_final_outcome'
            or policy['rounding'] != 'ceil_half_count_then_final_floor'):
        raise ValueError('selected S-002 Contest experience policy required')
    participants = state['contract'][0]
    if state.get('rotation') is not None:
        participants = tuple(c for team in state['rotation']['teams'] for c in team)
    if contestant not in participants:
        raise ValueError('actual Pokemon participant in this completed event required')
    pokemon = host._native_intro_bindings[contestant][1]
    level = F.integer(pokemon.level, 'Contest XP recipient level', 1, 100)
    factor = A.exact(policy['default_significance'] if significance is None else significance)
    if factor <= 0:
        raise ValueError('positive finite Contest significance required')
    beaten = _defeated(host, state, contestant)
    half = M.ceil_ratio(len(beaten), 2)
    quote = {'source': SOURCE, 'decision': 'S-002', 'event': deepcopy(identity),
             'recipient_id': pokemon.entity_id, 'level': level,
             'defeated_ids': sorted(host._native_intro_bindings[c][1].entity_id for c in beaten),
             'half_count': half, 'significance': str(factor),
             'amount': M.product(level, half, factor)}
    return engine, pokemon, quote


def quote(host, contestant, *, significance=None):
    """Read-only base XP, before existing sourced recipient XP modifiers."""
    return _quote(host, contestant, significance)[2]


def award(host, contestant, *, significance=None, stat_choices=None):
    """One explicit award per occurrence/roster/recipient, including a zero award.

    Growth and its choices remain downtime's responsibility. No receipt survives
    failed growth or native candidate validation; snapshots/codecs keep it in spec.
    """
    engine, pokemon, proposal = _quote(host, contestant, significance)
    # Recreating presentation Contestants must not reset an actual event's receipt.
    occurrence = {k: proposal['event'][k] for k in ('format', 'contest_id', 'entrants')}
    receipt_id = 'contest-xp/'+TX.json_fingerprint({**occurrence, 'recipient_id': pokemon.entity_id})
    def apply(staged, recipient):
        receipts = recipient.spec.get(KEY, {})
        if type(receipts) is not dict:
            raise ValueError('invalid actual Contest XP receipts')
        prior = [row for row in receipts.values() if type(row) is dict
                 and row.get('recipient_id') == recipient.entity_id
                 and type(row.get('event')) is dict
                 and all(row['event'].get(k) == occurrence[k] for k in ('format', 'contest_id'))]
        if receipt_id in receipts or prior:
            raise ValueError('Contest experience already awarded to this Pokemon')
        if recipient.level != proposal['level']:
            raise ValueError('Contest XP recipient changed since quote')
        before = recipient.spec.get('exp')
        logs = []
        if proposal['amount']:
            logs = DT._gain_exp_combatant(staged, recipient, proposal['amount'],
                                         stat_choices=stat_choices)
        receipt = {**deepcopy(proposal), 'id': receipt_id,
                   'exp_before': before, 'exp_after': recipient.spec.get('exp'),
                   'growth_log': list(logs)}
        recipient.spec.setdefault(KEY, {})[receipt_id] = receipt
        staged.gm._rec('Contest experience '+recipient.name, before, receipt['exp_after'],
                       'S-002 completed Contest experience')
        return deepcopy(receipt)
    return GRANTS.transition(engine, pokemon, apply)
