"""Wish editions on the native delayed queue and actual owner-turn clock."""
from copy import deepcopy
from contextlib import contextmanager
from functools import wraps
from inspect import Parameter, signature
import csv
import hashlib
import io
import json
from pathlib import Path
import arithmetic_policy as M
import common_checks as C
import world_entities as W

SOURCE = 'move/희망사항'
EDITIONS = ('ptu105', 'csv-row623')
RAW = {'type': 'delayed_heal', 'when': "end of target's next turn",
       'fraction_of_max': [1, 2], 'transfers_on_switch': True}
CSV_SHA = 'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'
ROW_SHA = '4d39ed9d937ead5567493b1ae84e022575964ad55b836ec8b0df74b55e129e38'
PDF_SHA = 'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'


def source(rules):
    from source_context import verified_source
    content = verified_source(rules, {'file': 'input/db/moves.csv', 'sha256': CSV_SHA}, label='Wish CSV')
    row = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))[622]
    digest = hashlib.sha256(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if digest != ROW_SHA or rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('Wish exact source row or selected Move changed')
    pdf = Path(rules.root) / 'output/source-audit/2026-10-10/ptu-core-1.05.pdf'
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != PDF_SHA:
        raise ValueError('Wish PTU 1.05 printed page 413 source changed')


def edition(engine, actor, target):
    scope = getattr(engine, '_wish_choice', None)
    if scope is None:
        return 'ptu105'
    if scope['actor_id'] != actor.entity_id:
        raise ValueError('Wish source selection belongs to another activation')
    if scope['target_id'] != target.entity_id:
        token = _recipient_token(engine, actor, target)
        if token is None or token[1] != scope['target_id']:
            raise ValueError('Wish source selection belongs to another activation')
    return scope['edition']


def continuation_choice(engine, args):
    return {'actor_id': args['attacker'].entity_id, 'target_id': args['target'].entity_id,
            'edition': edition(engine, args['attacker'], args['target'])}


@contextmanager
def resume_choice(engine, args, choice):
    if choice is None:
        yield
        return
    if (args['move_id'] != SOURCE or type(choice) is not dict or
            set(choice) != {'actor_id', 'target_id', 'edition'} or
            choice['actor_id'] != args['attacker'].entity_id or
            choice['target_id'] != args['target'].entity_id or choice['edition'] not in EDITIONS):
        raise ValueError('Wish continuation lost its actual selected source and participants')
    previous = getattr(engine, '_wish_choice', None)
    if previous is not None and previous != choice:
        raise ValueError('Wish continuation changed source selection')
    engine._wish_choice = deepcopy(choice)
    try:
        yield
    finally:
        if previous is None:del engine._wish_choice
        else:engine._wish_choice = previous


def _reflected_choice(engine, actor, target, previous):
    import warper as WARPER
    proof = getattr(engine, '_warper_reflection', None)
    if proof is None or not WARPER.move_authority(engine, actor, target, SOURCE, WARPER.COAT):
        return False
    original = engine._move_completions[proof['trigger_completion']]
    return (original['move_id'] == SOURCE and actor in original['targets'] and
            previous['actor_id'] == target.entity_id and previous['target_id'] == actor.entity_id)


def native_move(function):
    @wraps(function)
    def run(engine, actor, target, move_id, *args, **options):
        selected = options.pop('wish_edition', None)
        previous = getattr(engine, '_wish_choice', None)
        if selected is None:
            if (move_id != SOURCE or previous is None or
                    (previous['actor_id'], previous['target_id']) == (actor.entity_id, target.entity_id)):
                return function(engine, actor, target, move_id, *args, **options)
            if not _reflected_choice(engine, actor, target, previous):
                raise ValueError('nested Wish activation changed source selection')
            selected = previous['edition']
        if move_id != SOURCE or selected not in EDITIONS:
            raise ValueError('exact Wish edition required')
        W.require_actors(engine, actor, target)
        proposed = {'actor_id': actor.entity_id, 'target_id': target.entity_id, 'edition': selected}
        if previous is not None and previous != proposed:
            if selected != previous['edition'] or not _reflected_choice(engine, actor, target, previous):
                raise ValueError('nested Wish activation changed source selection')
        engine._wish_choice = proposed
        try:
            return function(engine, actor, target, move_id, *args, **options)
        finally:
            if previous is None:
                del engine._wish_choice
            else:
                engine._wish_choice = previous
    public = signature(function)
    parameters = list(public.parameters.values())
    position = next((i for i, parameter in enumerate(parameters) if parameter.kind is Parameter.VAR_KEYWORD), len(parameters))
    parameters.insert(position, Parameter('wish_edition', Parameter.KEYWORD_ONLY, default=None))
    run.__signature__ = public.replace(parameters=parameters)
    return run


def _recipient_token(engine, actor, target):
    token = getattr(engine, '_defense_recipient_scope', None)
    if token is None:return None
    import move_defense_reactions as DEFENSE, move_completion as COMPLETE
    event = engine._passive_events[token[0]]
    if event['move_id'] != SOURCE:return None
    DEFENSE.require_recipient(engine, token, actor, target, COMPLETE.event_move(engine, event), event['completion_id'])
    return tuple(token)


def preflight(engine, actor, target, effect, source_id):
    if source_id != SOURCE or {k: v for k, v in effect.items() if not k.startswith('_')} != RAW:
        raise ValueError('Wish requires its exact sourced delayed-healing payload')
    source(engine.r)
    W.require_actors(engine, actor, target)
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('Wish requires an actual open encounter and future native turn')
    selected = edition(engine, actor, target)
    if selected not in EDITIONS:
        raise ValueError('exact Wish edition required')
    validate_world(engine, W.actor_index(engine))
    return selected


def schedule(engine, actor, target, effect, context):
    selected = preflight(engine, actor, target, effect, context.get('source_id'))
    import effect_contracts as CONTRACTS
    token, occurrence = context.get('effect_receipt'), context.get('effect_occurrence')
    CONTRACTS.validate_receipt(engine, token, SOURCE, occurrence, actor, target, effect)
    completion_id = context.get('move_completion')
    completion = getattr(engine, '_move_completions', {}).get(completion_id)
    if completion is None or completion['actor'] is not actor or completion['move_id'] != SOURCE:
        raise ValueError('Wish requires its actual native Move completion')
    recipient_token = _recipient_token(engine, actor, target)
    if target not in completion['targets'] and recipient_token is None:
        raise ValueError('Wish requires its actual received native target')
    owner = actor if selected == 'ptu105' else target
    origin = C.integer(owner.custom_conditions.get('combat_turn_serial', 0), 'Wish actual turn serial', 0)
    engine.delayed.append({'kind': 'wish', 'src': SOURCE, 'who': target, 'issuer': actor,
        'original_target': target, 'turn_owner': owner,
        'turn_origin': origin, 'turn_deadline': origin + 1,
        'dispatch_receipt': token, 'occurrence': occurrence, 'completion_id': completion_id,
        'recipient_token': recipient_token,
        'edition': selected, 'effect': deepcopy(RAW), 'at': engine.elapsed_seconds,
        'encounter_epoch': engine._party_encounter_epoch, 'replacements': []})
    engine.log('    희망사항: 실제 다음 소유자 턴 종료에 회복 예약 (' + selected + ')', SOURCE)


def replaced(engine, outgoing, incoming, *, request_id):
    """Only the paid native one-for-one party replacement transfers the slot."""
    owner = __import__('party_actions').owner(engine, incoming)
    receipt = None if owner is None else owner.spec.get('party_action_receipts', {}).get(request_id)
    if receipt is None or receipt['result']['recalled'] != [outgoing.entity_id] or receipt['result']['sent'] != [incoming.entity_id]:
        raise ValueError('Wish replacement requires its actual one-for-one party receipt')
    for row in engine.delayed:
        if row.get('kind') != 'wish' or row['who'] is not outgoing:
            continue
        if row['edition'] == 'ptu105' and row['original_target'] is not row['issuer']:
            continue
        row['who'] = incoming
        if row['turn_owner'] is outgoing:
            row['turn_owner'] = incoming
            row['turn_origin'] = incoming.custom_conditions.get('combat_turn_serial', 0)
            row['turn_deadline'] = row['turn_origin'] + 1
        row['replacements'].append({'trainer_id': owner.entity_id, 'request_id': request_id,
            'outgoing_id': outgoing.entity_id, 'incoming_id': incoming.entity_id,
            'incoming_turn_serial': incoming.custom_conditions.get('combat_turn_serial', 0)})


def end_turn(engine, actor):
    validate_world(engine, W.actor_index(engine))
    serial = actor.custom_conditions.get('combat_turn_serial', 0)
    for row in list(engine.delayed):
        if row.get('kind') != 'wish' or row['turn_owner'] is not actor or serial < row['turn_deadline']:
            continue
        engine.delayed.remove(row)
        target = row['who']
        maximum = target.base_max_hp if row['edition'] == 'ptu105' else target.max_hp
        engine.heal(target, M.ratio(maximum, 2), source_kind='move')
        engine.log('    희망사항: 다음 실제 턴 종료 회복 → ' + target.name, SOURCE)


def validate_world(engine, index):
    for row in engine.delayed:
        if row.get('kind') != 'wish':
            continue
        source(engine.r)
        if row.get('src') != SOURCE or row.get('edition') not in EDITIONS or row.get('effect') != RAW:
            raise ValueError('Wish delayed source or edition changed')
        for key in ('who', 'issuer', 'original_target', 'turn_owner'):
            actor = row.get(key)
            if actor is None or index.get(actor.entity_id) is not actor:
                raise ValueError('Wish requires the actual native actor identities')
        C.integer(row.get('at'), 'Wish creation time', 0, engine.elapsed_seconds)
        C.integer(row.get('encounter_epoch'), 'Wish encounter scope', 1, engine._party_encounter_epoch)
        C.integer(row.get('turn_deadline'), 'Wish actual next-turn deadline', 1)
        origin = C.integer(row.get('turn_origin'), 'Wish native clock origin', 0,
                           row['turn_owner'].custom_conditions.get('combat_turn_serial', 0))
        if row['turn_deadline'] != origin + 1:
            raise ValueError('Wish deadline must be the next actual owner turn')
        import effect_contracts as CONTRACTS
        token = row.get('dispatch_receipt')
        receipt = getattr(engine, '_effect_dispatch_receipts', {})
        try:
            dispatch = receipt.get(token)
            completion = getattr(engine, '_move_completions', {}).get(row.get('completion_id'))
        except TypeError:
            raise ValueError('Wish requires native dispatcher and Move identities')
        if dispatch is None or completion is None:
            raise ValueError('Wish lost its actual native activation')
        CONTRACTS.validate_receipt(engine, token, SOURCE, row.get('occurrence'),
            row['issuer'], row['original_target'], dispatch['effect'])
        if (completion['actor'] is not row['issuer'] or completion['move_id'] != SOURCE or
                completion['seconds'] != row['at']):
            raise ValueError('Wish delayed effect differs from its actual Move')
        recipient_token = row.get('recipient_token')
        if recipient_token is None:
            if row['original_target'] not in completion['targets']:
                raise ValueError('Wish delayed effect differs from its actual Move target')
        else:
            _validate_recipient(engine, row, completion, recipient_token)
        if type(row.get('replacements')) is not list:
            raise ValueError('Wish native replacement history required')
        expected = row['original_target']
        for event in row['replacements']:
            trainer = index.get(event.get('trainer_id'))
            proof = {} if trainer is None else trainer.spec.get('party_action_receipts', {}).get(event.get('request_id'), {}).get('result', {})
            incoming = index.get(event.get('incoming_id'))
            if event.get('outgoing_id') != expected.entity_id or proof.get('recalled') != [expected.entity_id] or proof.get('sent') != [event.get('incoming_id')] or incoming is None:
                raise ValueError('Wish transfer lost its actual party replacement')
            if row['edition'] == 'ptu105' and row['original_target'] is not row['issuer']:
                raise ValueError('PTU Wish only transfers a self-targeted replacement')
            C.integer(event.get('incoming_turn_serial'), 'Wish replacement clock origin', 0,
                      incoming.custom_conditions.get('combat_turn_serial', 0))
            expected = incoming
        if row['who'] is not expected:
            raise ValueError('Wish beneficiary differs from its native replacement chain')
        original_owner = row['issuer'] if row['edition'] == 'ptu105' else row['original_target']
        expected_owner = expected if original_owner is row['original_target'] else original_owner
        if row['turn_owner'] is not expected_owner:
            raise ValueError('Wish clock changed from its selected source owner')
        if row['replacements'] and original_owner is row['original_target']:
            expected_origin = row['replacements'][-1]['incoming_turn_serial']
        elif row['edition'] == 'ptu105':
            expected_origin = completion['turn_serial']
        else:
            expected_origin = origin
        if origin != expected_origin:
            raise ValueError('Wish next turn lost its native clock origin')
    return True


def _validate_recipient(engine, row, completion, token):
    if type(token) not in (tuple, list) or len(token) != 3 or token[2] != row['original_target'].entity_id:
        raise ValueError('Wish lost its actual native recipient identity')
    event = engine._passive_events.get(token[0])
    state = completion.get('defense', {}).get(token[1])
    if (event is None or state is None or event['actor'] is not row['issuer'] or
            event['completion_id'] != completion['id'] or event['target'].entity_id != token[1] or
            event['target'] not in completion['targets'] or state['event_id'] != token[0] or
            not any(plan['actor_id'] == token[2] and plan['hit'] for plan in state['recipients'])):
        raise ValueError('Wish recipient lost its actual defense completion')
    # While this same producer is still dispatching, its live token is authority.
    if tuple(token) == getattr(engine, '_defense_recipient_scope', None):
        if _recipient_token(engine, row['issuer'], row['original_target']) != tuple(token):
            raise ValueError('Wish recipient producer changed')
        return
    received = completion.get('received', {}).get(token[2])
    if (received is None or received['actor'] is not row['original_target'] or
            received['event_id'] != token[0] or received['original_id'] != token[1] or
            received['child_event'] != state['children'].get(token[2]) or
            not received['hit'] or received['cancelled'] or row['dispatch_receipt'] not in received['effects']):
        raise ValueError('Wish requires its actual received effect receipt')
