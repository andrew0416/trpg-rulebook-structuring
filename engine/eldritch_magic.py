"""C11-142's explicit actor adoption on the selected native Confusion family.

Only an admitted native attack's legal recipient can produce Dementia. Its
extra state is one ordinary condition instance, so native Confusion attacks,
Sleep exceptions, volatile expiry and cures keep their existing ownership.
The default low Save band uses the modified end-turn result. An explicit GM
adoption may instead capture the natural Save face for that actor's instances.
"""
from copy import deepcopy
from pathlib import Path
import json
import common_checks as C
import condition_instances as CI
import effect_instances as E
import resolution_transaction as F

CLAUSE = 'C11-142'
ADOPTION = 'eldritch_magic_adoption'
FIELD = 'eldritch_magic'
SOURCE = {'file': 'input/ch11-running-the-game.md',
          'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
PAYLOAD = {'kind': 'eldritch_dementia', 'condition': '혼란'}
CAPACITY = {'bucket': 'condition:혼란', 'source': 'condition/혼란'}
LIFETIME = {'boundary': 'condition_cure_or_volatile_end'}
SAVE_BASES = ('modified_save', 'natural_save')


def policy(rules):
    from source_context import verified_source
    import combat_stage_sources as STAGES
    row = json.loads((Path(rules.root) / 'data/core-eldritch-magic-policy.json').read_text(encoding='utf-8'))
    expected = {'schema_version': 1, 'clause_id': CLAUSE, 'source': SOURCE,
                'lines': [2389, 2392], 'owner_kinds': ['pokemon', 'trainer'],
                'attack_classes': ['물리', '특수'], 'effect_range_minimum': 16,
                'payload': PAYLOAD, 'save_modifier': -2,
                'save_timing': 'selected_confusion_end_of_turn',
                'low_range': {'basis': 'modified_save', 'maximum': 8},
                'stat_pool': list(STAGES.STATS),
                'reapplication': 'native_curse'}
    if row != expected:
        raise ValueError('reviewed Eldritch Magic policy changed')
    verified_source(rules, SOURCE, label='Eldritch Magic')
    return row


def _adoption(row, actor_id):
    fields = {'actor_id', 'clause_id', 'source', 'reason', 'active'}
    if (not isinstance(row, dict) or set(row) not in (fields, fields | {'save_band_basis'})
            or row['actor_id'] != actor_id or row['clause_id'] != CLAUSE
            or row['source'] != SOURCE or type(row['active']) is not bool):
        raise ValueError('actual actor-owned Eldritch Magic adoption required')
    if row.get('save_band_basis', 'modified_save') not in SAVE_BASES:
        raise ValueError('explicit supported Dementia save_band_basis required')
    E.text(row['reason'], 'Eldritch Magic adoption reason')
    return row


def adoption(actor):
    row = actor.spec.get(ADOPTION)
    if row is None:
        return None
    policy(actor.r)
    import confusion_attacks as CONFUSION
    CONFUSION.policy(actor)
    _adoption(row, actor.entity_id)
    if actor.kind not in ('pokemon', 'trainer'):
        raise ValueError('Eldritch Magic requires an actual Pokemon or Trainer')
    return row


def adopt(engine, actor, *, reason, save_band_basis='modified_save'):
    """Explicit sample adoption on an actual actor, never a species-name rule."""
    import world_entities as W
    import state_grants as G
    W.require_actors(engine, actor)
    policy(engine.r)
    import confusion_attacks as CONFUSION
    CONFUSION.policy(engine)
    E.text(reason, 'Eldritch Magic adoption reason')
    if save_band_basis not in SAVE_BASES:
        raise ValueError('explicit supported Dementia save_band_basis required')
    if actor.kind not in ('pokemon', 'trainer'):
        raise ValueError('Eldritch Magic requires an actual Pokemon or Trainer')
    if adoption(actor) is not None:
        raise ValueError('Eldritch Magic adoption already recorded')
    def apply(staged, actual):
        actual.spec[ADOPTION] = {'actor_id': actual.entity_id, 'clause_id': CLAUSE,
                                'source': deepcopy(SOURCE), 'reason': reason, 'active': True,
                                'save_band_basis': save_band_basis}
        staged.log('    ' + actual.name + ': Eldritch Magic adopted', CLAUSE)
        return deepcopy(actual.spec[ADOPTION])
    return G.transition(engine, actor, apply)


def withdraw(engine, actor, *, reason):
    """Future attacks stop afflicting; existing Confusion retains its source."""
    import world_entities as W
    import state_grants as G
    W.require_actors(engine, actor)
    E.text(reason, 'Eldritch Magic withdrawal reason')
    row = adoption(actor)
    if row is None or not row['active']:
        return False
    def apply(staged, actual):
        actual.spec[ADOPTION]['active'] = False
        staged.log('    ' + actual.name + ': Eldritch Magic withdrawn: ' + reason, CLAUSE)
        return True
    return G.transition(engine, actor, apply)


def owns(row):
    return row.get('effect', {}).get('kind') == PAYLOAD['kind']


def active(actor):
    rows = [row for row in CI.records(actor, '혼란') if owns(row)]
    if len(rows) > 1:
        raise ValueError('one actual Dementia instance required')
    return rows[0] if rows else None


def save_modifier(actor):
    row = active(actor)
    if row is None:
        return 0
    validate_record(actor, row)
    return -2


def _source(rules, move_id):
    # Native Struggle has an explicit selected mechanic rather than a Move unit.
    if move_id == 'struggle':
        payload = rules.mech('combat/struggle')
    else:
        if rules._selected_rule(move_id) != move_id:
            raise ValueError('actual selected Eldritch attack source required')
        payload = {'unit': rules.selection.units[move_id], 'mechanics': rules.move_mech(move_id)[0]}
    return F.json_fingerprint(payload, sort_keys=True, compact=True, allow_nan=True)


def preflight(engine, actor, move):
    chosen = adoption(actor)
    if chosen is None or not chosen['active']:
        return False
    if move.get('class') not in ('물리', '특수'):
        return False
    _source(engine.r, move['id'])
    return True


def _producer(engine, actor, target, move, *, completion_id, defense_token, effect_receipt):
    """Join existing native completion/admission evidence, never a GM hit flag."""
    if completion_id is not None:
        row = getattr(engine, '_move_completions', {}).get(completion_id)
        if (row is None or row['actor'] is not actor or row['move_id'] != move['id']
                or row['move'].get('class') != move['class']):
            raise ValueError('actual native Move source required for Dementia')
        if target.entity_id in row.get(FIELD, {}):
            return row, {'kind': 'move', 'id': completion_id}
        if (row['phase'] != 'targets' or target.entity_id in row.get('results', {})
                or target.entity_id in row.get('received', {})):
            raise ValueError('actual unresolved native Move recipient required for Dementia')
        if defense_token is not None:
            import move_defense_reactions as DEFENSE
            DEFENSE.require_recipient(engine, defense_token, actor, target, move, completion_id)
        elif (not any(candidate is target for candidate in row['targets'])
              or target.entity_id not in row['started']):
            raise ValueError('Dementia recipient differs from actual started Move target')
        else:
            import move_activation as ACTIVATION
            ACTIVATION._require_started_event_use(engine, actor, target, move['id'],
                scope_error='Dementia needs its live native Move producer', move_id_required=True)
        return row, {'kind': 'move', 'id': completion_id}
    stack = getattr(engine, '_native_action_stack', [])
    frame = stack[-1] if stack else None
    receipt = getattr(engine, '_effect_dispatch_receipts', {}).get(effect_receipt)
    if (frame is None or frame['actor'] is not actor or frame['source'] != move['id']
            or frame['kind'] != 'ability_attack' or receipt is None
            or receipt.get('status') != 'dispatching' or receipt['actor'] is not actor
            or receipt['target'] is not target or receipt['effect'].get('type') != 'attack'
            or move['id'] != 'derived/ability-attack/' + engine.r.selection.require_supported_version(
                receipt['effect'].get('_rule_id', ''))
            or receipt['effect'].get('class', '변화') != move['class']):
        raise ValueError('Dementia needs its actual dispatched native Ability attack')
    import action_lifecycle as ACTION
    if frame['id'] is None:
        row = ACTION.observe_resolution(engine, actor, CLAUSE, {'event': 'eldritch_attack'})
        next(t for t in row['triggers'] if t['source'] == CLAUSE)['status'] = 'completed'
    else:
        row = engine._native_action_resolutions[frame['id']]
    return row, {'kind': 'ability_attack', 'id': row['id'], 'effect_receipt': effect_receipt}


def _witness(event):
    # The existing native receipt owns opaque tokens; only immutable scalar
    # facts enter this source-specific integrity check.
    facts = {key: event[key] for key in ('actor_id', 'target_id', 'attack', 'natural',
                                        'effect_face', 'source_fingerprint', 'adoption')}
    facts['origin'] = {key: event['origin'][key] for key in ('kind', 'id')}
    return F.json_fingerprint(facts, sort_keys=True, compact=True, allow_nan=True)


def after_hit(engine, actor, target, move, natural, *, completion_id=None,
              defense_token=None, effect_receipt=None):
    """Called only at native legal-hit production, once per attack/recipient.

    A damaging attack is identified by its admitted native class/source. Zero
    HP loss retains native status-hit semantics; Status attacks and absent
    accuracy faces cannot invent an effect-range roll.
    """
    if not preflight(engine, actor, move) or natural is None:
        return None
    import world_entities as W
    W.require_actors(engine, actor, target)
    C.integer(natural, 'actual Eldritch accuracy face', 1, 20)
    producer, origin = _producer(engine, actor, target, move, completion_id=completion_id,
                                 defense_token=defense_token, effect_receipt=effect_receipt)
    applications = producer.setdefault(FIELD, {})
    if target.entity_id in applications:
        return applications[target.entity_id]
    import combat_precision_features as CPF
    face = CPF.effect_natural(engine, actor, move, natural)
    observation = {'origin': origin, 'actor_id': actor.entity_id, 'target_id': target.entity_id,
                   'attack': {'id': move['id'], 'class': move['class']},
                   'natural': natural, 'effect_face': face,
                   'source_fingerprint': _source(engine.r, move['id']),
                   'adoption': deepcopy(adoption(actor))}
    observation['fingerprint'] = _witness(observation)
    # This bounded recipient slot belongs to the native completion, including
    # a multihit Move. Its later hit cannot turn the first application to Curse.
    applications[target.entity_id] = observation
    if face < 16:
        observation.update(outcome='outside_range', instance_id=None)
        return observation
    if engine.immune_to(target, '혼란'):
        observation.update(outcome='immune', instance_id=None)
        return observation
    existing = active(target)
    if existing is not None:
        validate_record(target, existing)
        applied = engine.apply_status(target, '저주', source=move['id'], applied_by=actor)
        observation.update(outcome='native_curse', instance_id=existing['id'], applied=bool(applied))
        return observation
    if '혼란' not in target.conditions:
        import field_effects as FIELD_EFFECTS
        marker = {key: origin[key] for key in ('kind', 'id')}
        engine.apply_status(target, '혼란', source=move['id'], applied_by=actor,
                            parameters={FIELD: marker})
        pending = next((row for row in FIELD_EFFECTS._pending(target)
                        if row['condition'] == '혼란'), None)
        if pending is not None:
            parameters = pending.get('parameters') or {}
            if not isinstance(parameters, dict):
                raise ValueError('native deferred Confusion parameters must be a mapping')
            previous = parameters.get(FIELD)
            if previous is None:
                # Add the subtype to an already deferred ordinary Confusion;
                # its original first-turn delay and applying source stay native.
                pending['parameters'] = dict(parameters, **{FIELD: marker})
            observation.update(outcome='deferred' if previous in (None, marker)
                               else 'already_deferred', instance_id=None)
            return observation
    if '혼란' not in target.conditions:
        observation.update(outcome='blocked', instance_id=None)
        return observation
    return _grant(engine, actor, target, observation)


def _grant(engine, actor, target, observation):
    row = E.create(engine, target, kind='condition', source=observation['attack']['id'], payload=PAYLOAD,
                   capacity=CAPACITY, lifetime=LIFETIME, applied_by=actor)
    row.update(adoption=deepcopy(observation['adoption']), attack=deepcopy(observation['attack']),
               source_fingerprint=observation['source_fingerprint'],
               origin=dict(observation['origin']), infliction_fingerprint=observation['fingerprint'], saves=[])
    target.custom_conditions.setdefault(CI.KEY, []).append(row)
    engine.time_actors([actor, target])
    observation.update(outcome='dementia', instance_id=row['id'])
    validate_record(target, row)
    return observation


def _deferred_event(engine, actor, pending):
    parameters = pending.get('parameters') or {}
    if not isinstance(parameters, dict) or FIELD not in parameters:
        return None
    marker = parameters[FIELD]
    if (pending.get('condition') != '혼란' or not isinstance(marker, dict)
            or set(marker) != {'kind', 'id'} or marker['kind'] not in ('move', 'ability_attack')):
        raise ValueError('Dementia requires its native deferred Confusion marker')
    producers = getattr(engine, '_move_completions' if marker['kind'] == 'move'
                        else '_native_action_resolutions', {})
    producer = producers.get(marker['id'])
    event = producer.get(FIELD, {}).get(actor.entity_id) if producer is not None else None
    if (event is None or event.get('outcome') != 'deferred'
            or event.get('target_id') != actor.entity_id
            or {key: event['origin'][key] for key in ('kind', 'id')} != marker
            or event.get('fingerprint') != _witness(event)):
        raise ValueError('Dementia lost its actual deferred native attack')
    return producer, event


def resume_deferred(engine, actor, pending):
    """Called after the existing Misty owner reapplies its due native status."""
    observed = _deferred_event(engine, actor, pending)
    if observed is None:
        return
    producer, event = observed
    if actor.turns_taken < pending['activate_after_turn']:
        raise ValueError('Dementia cannot skip its native first-turn delay')
    if '혼란' not in actor.conditions:
        event.update(outcome='blocked', instance_id=None)
        return
    if active(actor) is not None:
        raise ValueError('deferred Dementia cannot replace a live subtype')
    _grant(engine, producer['actor'], actor, event)


def cancel_deferred(engine, actor, pending):
    """A native cure cancels only the subtype attached to that deferred row."""
    observed = _deferred_event(engine, actor, pending)
    if observed is not None:
        observed[1].update(outcome='deferred_cured', instance_id=None)


def after_confusion_save(engine, actor, check):
    """Consume the selected native end-turn save, never another roll or clock."""
    row = active(actor)
    if row is None:
        return
    validate_record(actor, row)
    if getattr(engine, '_active_turn_actor', None) is not actor or '잠듦' in actor.conditions:
        raise ValueError('Dementia rider requires its actual awake holder end-turn save')
    turn = C.integer(actor.custom_conditions.get('combat_turn_serial'), 'Dementia holder turn', 1)
    if row['saves'] and row['saves'][-1]['turn'] == turn:
        if row['saves'][-1]['check'] != check:
            raise ValueError('Dementia cannot replace its actual end-turn save')
        return row['saves'][-1]
    effective = check['natural'] + check['base_dc'] - check['dc']
    event = {'turn': turn, 'at': engine.elapsed_seconds, 'check': dict(check),
             'effective': effective, 'stat': None, 'before': None, 'after': None,
             'stage_receipt': None, 'save_band_version': 2}
    natural_band = row['adoption'].get('save_band_basis', 'modified_save') == 'natural_save'
    if natural_band:
        event.update(save_band_version=3, save_band_basis='natural_save')
    if 1 <= (check['natural'] if natural_band else effective) <= 8:
        import combat_stage_sources as STAGES
        import world_entities as W
        import effects as FX
        stat = engine.rng.choice(STAGES.STATS)
        before = actor.stages[stat]
        issuer = W.actor_index(engine)[row[E.KEY]['applied_by_actor_id']]
        result = FX.run_effects(engine, issuer, actor,
                               [{'type': 'stage_change', 'stat': stat, 'delta': -1}],
                               {'hit': True}, row['source'])
        if result.pending or result != (1, 0) or result.outcomes[0].status != 'completed':
            raise ValueError('Dementia native stage contribution did not complete')
        event.update(stat=stat, before=before, after=actor.stages[stat],
                     stage_receipt=result.outcomes[0].receipt)
    row['saves'].append(event)
    return event


def archive(engine, actor, row, event):
    """Preserve the actual dispatcher capability through common history copy."""
    closed = E.archive(engine, actor, row, state='expired', event=event)
    if 'effect_receipt' in row['origin']:
        closed['origin']['effect_receipt'] = row['origin']['effect_receipt']
    for original, saved in zip(row['saves'], closed['saves']):
        saved['stage_receipt'] = original['stage_receipt']
    return closed


def validate_record(actor, row, *, terminal=False):
    E.validate(row, actor=actor, terminal=terminal)
    policy(actor.r)
    import confusion_attacks as CONFUSION
    CONFUSION.policy(actor)
    meta = row[E.KEY]
    if (row['effect'] != PAYLOAD or meta['kind'] != 'condition'
            or meta['capacity'] != CAPACITY or meta['lifetime'] != LIFETIME):
        raise ValueError('Dementia condition authority changed')
    chosen = _adoption(row.get('adoption'), meta.get('applied_by_actor_id'))
    if not chosen['active']:
        raise ValueError('Dementia needs the inflictor adoption at application')
    attack = row.get('attack')
    if (not isinstance(attack, dict) or set(attack) != {'id', 'class'}
            or attack['id'] != row['source'] or attack['class'] not in ('물리', '특수')
            or row.get('source_fingerprint') != _source(actor.r, row['source'])):
        raise ValueError('Dementia needs its actual selected damaging attack source')
    origin = row.get('origin')
    if (not isinstance(origin, dict) or origin.get('kind') not in ('move', 'ability_attack')
            or set(origin) != ({'kind', 'id'} if origin['kind'] == 'move'
                              else {'kind', 'id', 'effect_receipt'})):
        raise ValueError('Dementia needs its original native attack receipt')
    E.text(origin['id'], 'Dementia native attack identity')
    E.text(row.get('infliction_fingerprint'), 'Dementia original native observation')
    import combat_stage_sources as STAGES
    if not isinstance(row.get('saves'), list):
        raise ValueError('Dementia actual end-turn saves required')
    previous, when = 0, row['at']
    printed_band_seen = False
    natural_band = chosen.get('save_band_basis', 'modified_save') == 'natural_save'
    for event in row['saves']:
        fields = {'turn', 'at', 'check', 'effective', 'stat', 'before', 'after', 'stage_receipt'}
        legacy = 'save_band_version' not in event
        natural_event = event.get('save_band_version') == 3
        expected = fields if legacy else fields | {'save_band_version'}
        if natural_event:
            expected |= {'save_band_basis'}
        if (set(event) != expected
                or (not legacy and (type(event['save_band_version']) is not int
                                    or event['save_band_version'] != (3 if natural_band else 2)))
                or (natural_band and legacy)
                or (natural_event and event.get('save_band_basis') != 'natural_save')
                or (legacy and printed_band_seen)):
            raise ValueError('Dementia actual end-turn save record required')
        printed_band_seen = printed_band_seen or not legacy
        previous = C.integer(event['turn'], 'Dementia actual holder turn', previous + 1,
                             actor.custom_conditions.get('combat_turn_serial', 0))
        when = C.integer(event['at'], 'Dementia actual save time', when)
        check = event['check']
        if not isinstance(check, dict):
            raise ValueError('Dementia requires its native save result')
        C.integer(check.get('natural'), 'Dementia actual save face', 1, 20)
        C.integer(check.get('dc'), 'Dementia adjusted save DC')
        C.integer(event['effective'], 'Dementia modified save result')
        if (check.get('base_dc') != 16 or type(check.get('passed')) is not bool
                or check['passed'] != (check['natural'] >= check['dc'])
                or event['effective'] != check['natural'] + check['base_dc'] - check['dc']):
            raise ValueError('Dementia requires the selected modified Confusion save')
        # Unversioned historical saves retain their already-applied <=8 effects.
        band_result = check['natural'] if natural_event else event['effective']
        if (band_result <= 8 if legacy else 1 <= band_result <= 8):
            if event['stat'] not in STAGES.STATS or event['stage_receipt'] is None:
                raise ValueError('Dementia low save requires one native non-HP stage request')
            for key in ('before', 'after'):
                C.integer(event[key], 'Dementia actual stage', -6, 6)
        elif any(event[key] is not None for key in ('stat', 'before', 'after', 'stage_receipt')):
            raise ValueError('Dementia stage request requires its modified low Save band')
    if not terminal and ('혼란' not in actor.conditions or active(actor) is not row):
        raise ValueError('Dementia needs its single live native Confusion presence')
    if terminal and meta['end_event'] != {'kind': 'condition_cure', 'condition': '혼란'}:
        raise ValueError('Dementia ends with its actual native Confusion cure')
    return True


def validate_world(engine, index):
    import move_completion as COMPLETE
    import field_effects as FIELD_EFFECTS
    instances = {}
    deferred = set()
    for actor in index.values():
        adoption(actor)
        for pending in FIELD_EFFECTS._pending(actor):
            observed = _deferred_event(engine, actor, pending)
            if observed is not None:
                event = observed[1]
                deferred.add((event['origin']['kind'], event['origin']['id'], actor.entity_id))
        for row, phase in E.records(actor):
            if not owns(row):
                continue
            validate_record(actor, row, terminal=phase == 'terminal')
            instances[row['id']] = row
            issuer = index.get(row[E.KEY].get('applied_by_actor_id'))
            chosen = adoption(issuer) if issuer is not None else None
            if chosen is None or {k: v for k, v in chosen.items() if k != 'active'} != {
                    k: v for k, v in row['adoption'].items() if k != 'active'}:
                raise ValueError('Dementia issuer adoption is missing or changed')
            origin = row['origin']
            producers = getattr(engine, '_move_completions' if origin['kind'] == 'move'
                                else '_native_action_resolutions', {})
            producer = producers.get(origin['id'])
            event = producer.get(FIELD, {}).get(actor.entity_id) if producer else None
            if (event is None or event.get('outcome') != 'dementia' or event.get('instance_id') != row['id']
                    or event['origin'] != origin or event['actor_id'] != issuer.entity_id
                    or event['attack'] != row['attack'] or event['adoption'] != row['adoption']
                    or event['source_fingerprint'] != row['source_fingerprint']
                    or event['fingerprint'] != row['infliction_fingerprint']):
                raise ValueError('Dementia lost its actual native infliction producer')
            for save in row['saves']:
                if save['stage_receipt'] is None:
                    continue
                stage = getattr(engine, '_effect_dispatch_receipts', {}).get(save['stage_receipt'])
                if (stage is None or stage.get('status') != 'completed' or stage['actor'] is not issuer
                        or stage['target'] is not actor or stage['source_id'] != row['source']
                        or stage['effect'] != {'type': 'stage_change', 'stat': save['stat'], 'delta': -1}):
                    raise ValueError('Dementia lost its actual native stage producer')
    for kind, rows in [('move', getattr(engine, '_move_completions', {})),
                       ('ability_attack', getattr(engine, '_native_action_resolutions', {}))]:
        for identity, producer in rows.items():
            applications = producer.get(FIELD, {})
            if not isinstance(applications, dict):
                raise ValueError('native Eldritch recipient mapping required')
            for target_id, event in applications.items():
                target = index.get(target_id)
                issuer = producer['actor']
                if (target is None or event['target_id'] != target_id or event['actor_id'] != issuer.entity_id
                        or event['origin']['kind'] != kind or event['origin']['id'] != identity
                        or event['attack']['id'] != producer.get('move_id', producer.get('source'))
                        or event['source_fingerprint'] != _source(engine.r, event['attack']['id'])
                        or event.get('fingerprint') != _witness(event)
                        or event['adoption']['active'] is not True):
                    raise ValueError('native Eldritch recipient/source facts changed')
                _adoption(event['adoption'], issuer.entity_id)
                chosen = adoption(issuer)
                if chosen is None or {k: v for k, v in chosen.items() if k != 'active'} != {
                        k: v for k, v in event['adoption'].items() if k != 'active'}:
                    raise ValueError('native Eldritch inflictor adoption changed')
                C.integer(event['natural'], 'actual Eldritch accuracy face', 1, 20)
                C.integer(event['effect_face'], 'actual Eldritch effect range')
                if kind == 'move':
                    result = COMPLETE.recipient_result(producer, target)
                    # During the native leaf the started recipient has not yet
                    # returned. A complete producer must retain its legal hit.
                    if result is None and producer['phase'] not in ('targets', 'interrupted'):
                        raise ValueError('Eldritch Move lost its actual recipient return')
                    if result is not None and not result['hit']:
                        raise ValueError('missed native Move cannot inflict Dementia')
                    if event['attack']['class'] != producer['move'].get('class'):
                        raise ValueError('Eldritch attack class differs from its native Move')
                else:
                    receipt = getattr(engine, '_effect_dispatch_receipts', {}).get(event['origin']['effect_receipt'])
                    if (producer['kind'] != 'ability_attack' or receipt is None or receipt['actor'] is not issuer
                            or receipt['target'] is not target or receipt['effect'].get('type') != 'attack'
                            or receipt['effect'].get('class', '변화') != event['attack']['class']
                            or event['attack']['id'] != 'derived/ability-attack/' +
                            engine.r.selection.require_supported_version(receipt['effect'].get('_rule_id', ''))):
                        raise ValueError('Eldritch Ability lost its actual dispatched attack')
                outcome = event.get('outcome')
                if outcome == 'outside_range':
                    if event['effect_face'] >= 16 or event.get('instance_id') is not None:
                        raise ValueError('out-of-range native attack cannot inflict Dementia')
                elif event['effect_face'] < 16:
                    raise ValueError('Dementia requires its actual native effect range')
                elif outcome == 'immune':
                    if event.get('instance_id') is not None:
                        raise ValueError('immune recipient cannot own a Dementia application')
                elif outcome in ('deferred', 'deferred_cured', 'already_deferred', 'blocked'):
                    if event.get('instance_id') is not None:
                        raise ValueError('unafflicted native recipient cannot own a Dementia instance')
                    if outcome == 'deferred' and (kind, identity, target_id) not in deferred:
                        raise ValueError('Dementia lost its actual native first-turn delay')
                elif outcome in ('dementia', 'native_curse'):
                    if event.get('instance_id') not in instances:
                        raise ValueError('Eldritch consequence lost its actual condition instance')
                    if outcome == 'native_curse' and type(event.get('applied')) is not bool:
                        raise ValueError('native Curse result required for repeat Dementia')
                else:
                    raise ValueError('native Eldritch consequence required')
    return True
