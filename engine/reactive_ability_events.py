"""Optional ability intents consumed by actual native move completions.

The move completion owns the event evidence. Grants reuse state_grants and
combat_timing; an intent cannot supply hit, range, type, or a random result.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

import ability_transitions as ABILITIES
import combat_timing as TIME
import frequency as FREQUENCY
import state_grants as GRANTS
import move_defense_reactions as DEFENSE

POLICY = 'data/reactive-ability-policy.json'
CHOICES = 'reactive_ability_choices'
TAG = 'reactive_ability'
PROTEAN = 'ability/변환자재'
COLOR = 'ability/변색'
SPIRIT = 'ability/떠도는영혼'
AROMA = 'ability/가시지않는향기'
SOURCES = (PROTEAN, COLOR, SPIRIT, AROMA)


def install(rules):
    data = json.loads((Path(rules.root) / POLICY).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or set(data.get('sources', {})) != set(SOURCES):
        raise ValueError('reviewed reactive ability policy required')
    for path, digest in data['source_files'].items():
        if hashlib.sha256((Path(rules.root) / path).read_bytes()).hexdigest() != digest:
            raise ValueError('reactive ability source changed: ' + path)
    rules.reactive_ability_policy = data


def definition(rules, source):
    row = getattr(rules, 'reactive_ability_policy', {}).get('sources', {}).get(source)
    if row is not None and rules._selected_rule(source) != source:
        raise ValueError('reactive ability source is not selected')
    return row


def handled(rules, selected_id):
    return selected_id.startswith('ability/') and definition(rules, selected_id) is not None


def registration(rules, name):
    for source in (PROTEAN, COLOR, SPIRIT, AROMA):
        label = source.split('/', 1)[1]
        if name in (source, label) and definition(rules, source) is not None:
            return {'name': label, 'source_id': source, 'equivalent_source_ids': [source]}
    return None


def operation_mode(rules, source):
    if definition(rules, source) is None:
        return None
    return {SPIRIT: 'swap', AROMA: 'replace'}.get(source)


def _eligible(owner, source):
    return not owner.fainted and ABILITIES.active(owner, source)


def _choice(owner, source):
    return owner.spec.get(CHOICES, {}).get(source)


def choose(engine, owner, source, *, ability=None, reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('actual choice reason required')
    if source not in SOURCES:
        source = 'ability/' + source
    row = definition(engine.r, source)
    if row is None:
        raise ValueError('reviewed reactive source required')
    import world_entities as WORLD
    if WORLD.actor_index(engine).get(owner.entity_id) is not owner:
        raise ValueError('actual registered reactive owner required')
    if not _eligible(owner, source):
        raise ValueError('active owned reactive ability required')
    if ability is not None:
        raise ValueError('reactive event does not accept an ability or random-result override')
    request = {'source': source, 'ability': None, 'reason': reason}
    def apply(e, actor):
        if not FREQUENCY.activation_allowed(
                actor, source, row['frequency'], engine=e):
            raise ValueError('reactive ability frequency exhausted')
        actor.spec.setdefault(CHOICES, {})[source] = deepcopy(request)
        return deepcopy(request)
    return GRANTS.transition(engine, owner, apply)


def interested(engine, actor, target):
    subjects = [actor, target, *getattr(engine, 'everyone', ())]
    return any(subject is not None and subject.spec.get(CHOICES) for subject in subjects)


def atomic_move(engine, actor, target, callback):
    import pass_moves as PASS
    import dynamic_chain_moves as CHAIN
    if PASS.native_transaction(engine,actor,target) or CHAIN.native_transaction(engine,actor,target):
        # These actual producers already stage their movement, costs and hits.
        engine._reactive_move_transaction = True
        try:
            return callback(engine,actor,target)
        finally:
            del engine._reactive_move_transaction
    pending = []
    def apply(e, a, t):
        e._reactive_move_transaction = True
        try:
            return callback(e, a, t)
        except Exception as error:
            if GRANTS.record_native_pending(e, error, pending):
                return None
            raise
        finally:
            del e._reactive_move_transaction
    result = GRANTS.transition(engine, actor, apply, participants=(target,),
                               include_rulings=True, include_grid=engine.grid is not None)
    if pending:
        exception, event_id = pending[0]
        raise exception(event_id)
    return result


def preflight_move(engine, actor, target, move, mm, *, ordinary_action='standard'):
    request = _choice(actor, PROTEAN)
    if request is not None:
        if not _eligible(actor, PROTEAN):
            raise ValueError('stale pre-use ability choice')
        import action_resources as ACTIONS
        import pass_moves as PASS
        prepaid = PASS.prepaid_move(engine,actor,target,move['id'])
        costs = ([ordinary_action] if not prepaid and ordinary_action in ACTIONS.KINDS else []) + ['swift']
        if ACTIONS.plan_cost(actor.budget, costs) is None:
            raise ValueError('reactive ability requires the move and Swift action costs')
    return mm


def _completion(engine, actor, target, move, token):
    row = getattr(engine, '_move_completions', {}).get(token)
    empty = row is not None and row.get('activation') == 'empty_area_field'
    received = row is not None and row.get('received',{}).get(target.entity_id,{}).get('actor') is target
    if (row is None or row['actor'] is not actor or row['move_id'] != move['id'] or
            row['move'].get('type') != move.get('type') or
            (not empty and not received and (target not in row['targets'] or target.entity_id not in row['started']))):
        raise ValueError('actual native move completion required')
    return row


def _pay(engine, owner, source):
    import turn as TURN
    row = definition(engine.r, source)
    if not FREQUENCY.activation_allowed(owner, source, row['frequency'], engine=engine,action_actor=owner if row['action'] is not None else None):
        raise ValueError('reactive ability frequency exhausted')
    if row['action'] == 'free':
        import action_lifecycle as ACTION
        if not _reaction_allowed(engine, owner):
            raise ValueError('reactive ability action unavailable')
        # The completed native hit supplies this off-turn permission.
        ACTION.record_action(engine, owner, 'free')
    elif not TURN.spend(engine, owner, row['action'], source):
        raise ValueError('reactive ability action unavailable')
    FREQUENCY.consume_activation(owner, source, row['frequency'], engine=engine,action_actor=owner if row['action'] is not None else None)


def _reaction_allowed(engine, owner):
    import action_lifecycle as ACTION
    import body_modes as BODY
    import boss_transitions as BOSS
    import turn as TURN
    return (TURN.can_act(engine, owner) and BOSS.action_permission(owner) and
            BODY.permits(owner, 'free') and ACTION.status_permission(engine, owner, 'free'))


def _new_application(row, source, owner, donor, target):
    evidence = row.setdefault(TAG, {'begun': False, 'hits': {}, 'applications': []})
    number = len(evidence['applications']) + 1
    application = {'id': row['id'] + ':reactive:' + str(number), 'source': source,
                   'owner': owner, 'donor': donor, 'target': target, 'grants': []}
    evidence['applications'].append(application)
    return application


def _grant(engine, row, application, recipient, *, operation=None, type_value=None):
    source = application['source']
    key = application['id'] + ':' + recipient.entity_id
    payload = {'recipient': recipient, 'key': key}
    metadata = {TAG: application['id'], 'completion_id': row['id'],
                'owner_id': application['owner'].entity_id, 'rule_id': source,
                'lifetime': 'reactive_move'}
    if operation is not None:
        metadata['ability_operation'] = deepcopy(operation)
        GRANTS._source(recipient, key, 'effect', **metadata)
        payload['operation'] = deepcopy(operation)
        policy = definition(engine.r, source)
        timing = {'source': source, 'grant_source': key, TAG: application['id'],
                  'effect_contract': True, 'encounter_end': True}
        timing['ends'] = list(policy['ends'])
        payload['timing'] = {k: v for k, v in timing.items() if k not in ('turn_owner',)}
        TIME.install(engine, recipient, timing)
    else:
        state = GRANTS.state(recipient)
        old = [k for k, value in state['sources'].items()
               if TAG in value and value.get('rule_id') == source]
        for previous in old:
            GRANTS.revoke(recipient, previous, engine=engine)
        GRANTS._source(recipient, key, 'effect', **metadata)
        GRANTS.type_operation(recipient, 'set', [type_value], key)
        parent_key = state['ability_receipts'].get(ABILITIES.label(engine.r, source))
        if parent_key not in state['effects']:
            raise ValueError('reactive type requires its actual ability ownership receipt')
        state['sources'][key]['parent_source'] = parent_key
        payload['parent_source'] = parent_key
        payload['type_operation'] = {'mode': 'set', 'values': [type_value], 'fallback': None}
    application['grants'].append(payload)


def _type(engine, row, source, owner, target):
    import homebrew_state as HOME
    if HOME.type_change_blocked(owner):
        return
    import cheerleader as CHEER
    cheer_snapshot=CHEER.support_snapshot(engine,owner)
    application = _new_application(row, source, owner, row['actor'], target)
    _pay(engine, owner, source)
    _grant(engine, row, application, owner, type_value=row['move']['type'])
    owner.spec[CHOICES].pop(source, None)
    CHEER.support(engine,cheer_snapshot,[owner],{'kind':'reactive_ability','source':source,'completion_id':row['id'],'application_id':application['id']})


def begin_move(engine, actor, target, move, completion_id):
    if not _choice(actor, PROTEAN):
        return
    row = _completion(engine, actor, target, move, completion_id)
    if row.get(TAG, {}).get('begun'):
        return
    if not getattr(engine, '_reactive_move_transaction', False):
        raise ValueError('native reactive move transaction required')
    evidence = row.setdefault(TAG, {'begun': False, 'hits': {}, 'applications': []})
    evidence['begun'] = True
    if _choice(actor, PROTEAN) and _eligible(actor, PROTEAN):
        _type(engine, row, PROTEAN, actor, target)


def _melee(move):
    value = str(move.get('range', '')).casefold()
    return '근접' in value or 'melee' in value


def native_contact(engine, actor, move):
    """Snapshot this actual recipient's contact before its hit effects."""
    import equipment_variant_contracts as EQUIPMENT
    return _melee(move) and not EQUIPMENT.suppresses_melee_hit_reactions(engine, actor, move)


def _abilities(engine, row, source, owner, donor, target):
    pool = ABILITIES.known(donor)
    for uid in pool:
        ABILITIES.component_definitions(engine.r, uid)
    if not pool:
        return
    random_index = None
    if source == SPIRIT:
        if donor.kind != 'pokemon':
            return
        random_index = engine.rng.randrange(len(pool))
        selected = pool[random_index]
    elif source == AROMA:
        selected = source
    else:
        raise ValueError('reviewed reactive ability handoff required')
    if source != AROMA and ABILITIES.protected(engine.r, selected):
        return
    import cheerleader as CHEER
    cheer_snapshot=CHEER.support_snapshot(engine,owner)
    application = _new_application(row, source, owner, donor, target)
    application.update(pool=pool, selected=selected, random_index=random_index,
                       components={uid: list(ABILITIES.component_definitions(engine.r, uid))
                                   for uid in dict.fromkeys([*pool, selected, source])})
    _pay(engine, owner, source)
    if source == SPIRIT:
        operations = [(owner, {'kind': 'replace', 'remove': [source], 'add': [selected]}),
                      (donor, {'kind': 'replace', 'remove': [selected], 'add': [source]})]
    elif source == AROMA:
        operations = [(donor, {'kind': 'replace',
                              'remove': [uid for uid in pool if not ABILITIES.protected(engine.r, uid)],
                              'add': [source]})]
    for recipient, operation in operations:
        _grant(engine, row, application, recipient, operation=operation)
    for recipient, _ in operations:
        GRANTS.materialize(recipient, 'abilities')
    for recipient, _ in operations:
        GRANTS.reconcile(engine, recipient)
    owner.spec.get(CHOICES, {}).pop(source, None)
    CHEER.support(engine,cheer_snapshot,[recipient for recipient,_ in operations],{'kind':'reactive_ability','source':source,'completion_id':row['id'],'application_id':application['id']})
    for recipient, _ in operations:
        if recipient.fainted:
            end(engine, recipient, 'faint')


def resolved_hit(engine, actor, target, move, completion_id, *, hit_prevented=False, contact=None):
    row = _completion(engine, actor, target, move, completion_id)
    relevant = row.get(TAG) or any(_choice(target, source) for source in (COLOR, SPIRIT, AROMA))
    if not relevant:
        return
    evidence = row.setdefault(TAG, {'begun': False, 'hits': {}, 'applications': []})
    if target.entity_id in evidence['hits']:
        return
    if not getattr(engine, '_reactive_move_transaction', False):
        raise ValueError('native reactive move transaction required')
    result = DEFENSE.received_result(row, target)
    if result is None or type(hit_prevented) is not bool:
        raise ValueError('completed native target result required')
    # Older already-produced return frames have no contact observation field.
    contact = _melee(move) if contact is None else contact
    if type(contact) is not bool or (contact and not _melee(move)):
        raise ValueError('reactive contact must belong to its actual melee hit')
    evidence['hits'][target.entity_id] = {'hit_prevented': hit_prevented}
    if not result['hit'] or result['cancelled'] or hit_prevented:
        return
    for source in (COLOR, SPIRIT, AROMA):
        if not _choice(target, source) or not _eligible(target, source) or not _reaction_allowed(engine, target):
            continue
        if source != COLOR and not contact:
            continue
        if not FREQUENCY.activation_allowed(target, source, definition(engine.r, source)['frequency'], engine=engine):
            continue
        if source == COLOR:
            _type(engine, row, source, target, target)
        else:
            _abilities(engine, row, source, target, actor, target)


def end(engine, actor, event):
    for record in list(TIME.records(actor)):
        if TAG in record and event in record.get('ends', ()):
            TIME.expire(engine, actor, record)


def withdraw_ability(engine, actor, receipt):
    """End type contributions at the existing actual passive removal boundary."""
    keys = [key for key, row in actor.spec.get(GRANTS.KEY, {}).get('sources', {}).items()
            if TAG in row and row.get('parent_source') == receipt]
    for key in keys:
        GRANTS.revoke(actor, key, engine=engine)


def validate_world(engine, index):
    expected = {}
    for token, row in getattr(engine, '_move_completions', {}).items():
        evidence = row.get(TAG)
        if evidence is None:
            continue
        if type(evidence.get('begun')) is not bool or not isinstance(evidence.get('hits'), dict):
            raise ValueError('reactive completion phase required')
        for entity_id, fact in evidence['hits'].items():
            if (entity_id not in row['results'] and entity_id not in row.get('received',{})) or set(fact) != {'hit_prevented'} or type(fact['hit_prevented']) is not bool:
                raise ValueError('reactive hit lacks native completion evidence')
        for sequence, application in enumerate(evidence['applications'], 1):
            source = application['source']; policy = definition(engine.r, source)
            if policy is None or application['id'] != token + ':reactive:' + str(sequence):
                raise ValueError('reactive application identity differs from native completion')
            owner = application['owner']; donor = application['donor']; target = application['target']
            if any(index.get(c.entity_id) is not c for c in (owner, donor, target)):
                raise ValueError('reactive application participant identity required')
            if source == PROTEAN:
                if not evidence['begun'] or owner is not row['actor']:
                    raise ValueError('pre-use projection lacks actual producer')
            else:
                result = DEFENSE.received_result(row, target)
                if (not result or not result['hit'] or result['cancelled'] or
                        evidence['hits'].get(target.entity_id, {}).get('hit_prevented') is not False):
                    raise ValueError('reactive application requires an actual unprevented hit')
                if owner is not target or donor is not row['actor']:
                    raise ValueError('reactive hit participant provenance mismatch')
                if source in (SPIRIT, AROMA) and not _melee(row['move']):
                    raise ValueError('reactive handoff requires actual melee hit')
            if source in (PROTEAN, COLOR):
                operations = [(owner, None)]
            else:
                pool = application['pool']; selected = application['selected']; roll = application['random_index']
                if not isinstance(pool, list) or not pool or len(pool) != len(set(pool)):
                    raise ValueError('actual donor ability snapshot required')
                for uid in application['components']:
                    if application['components'][uid] != list(ABILITIES.component_definitions(engine.r, uid)):
                        raise ValueError('reactive ability component contract changed')
                component_ids = set(pool + [selected, source])
                if set(application['components']) != component_ids:
                    raise ValueError('reactive ability component snapshot incomplete')
                if source == SPIRIT:
                    if donor.kind != 'pokemon' or type(roll) is not int or not 0 <= roll < len(pool) or selected != pool[roll] or ABILITIES.protected(engine.r, selected):
                        raise ValueError('actual random transferable ability required')
                    operations = [(owner, {'kind': 'replace', 'remove': [source], 'add': [selected]}),
                                  (donor, {'kind': 'replace', 'remove': [selected], 'add': [source]})]
                elif source == AROMA:
                    if selected != source or roll is not None:
                        raise ValueError('replace-all source identity mismatch')
                    operations = [(donor, {'kind': 'replace',
                                          'remove': [uid for uid in pool if not ABILITIES.protected(engine.r, uid)],
                                          'add': [source]})]
            if len(application['grants']) != len(operations):
                raise ValueError('reactive recipient count mismatch')
            for grant, (recipient, operation) in zip(application['grants'], operations):
                key = application['id'] + ':' + recipient.entity_id
                if grant['key'] != key or grant['recipient'] is not recipient:
                    raise ValueError('reactive grant identity mismatch')
                expected[(recipient.entity_id, key)] = (application, grant, token)
                if operation is None:
                    if grant.get('type_operation') != {'mode': 'set', 'values': [row['move']['type']], 'fallback': None}:
                        raise ValueError('reactive type differs from actual move type')
                elif grant.get('operation') != operation:
                    raise ValueError('reactive ability operation differs from source')
                else:
                    timing = {'source': source, 'grant_source': key, TAG: application['id'],
                              'effect_contract': True, 'encounter_end': True}
                    timing['ends'] = list(policy['ends'])
                    if grant.get('timing') != timing:
                        raise ValueError('reactive lifetime differs from source policy')
    for actor in index.values():
        for source, request in actor.spec.get(CHOICES, {}).items():
            if definition(engine.r, source) is None or request.get('source') != source or set(request) != {'source', 'ability', 'reason'}:
                raise ValueError('reactive choice contains untrusted event facts')
        sources = actor.spec.get(GRANTS.KEY, {}).get('sources', {})
        live = {key: value for key, value in sources.items() if TAG in value}
        timed = {}
        for record in TIME.records(actor):
            if TAG not in record:
                continue
            key = record['grant_source']
            if key in timed or key not in live:
                raise ValueError('reactive timing lacks unique live grant')
            timed[key] = record
        for key, value in live.items():
            item = expected.get((actor.entity_id, key))
            if item is None:
                raise ValueError('reactive grant lacks actual move provenance')
            application, grant, token = item; source = application['source']
            if (value.get(TAG) != application['id'] or value.get('completion_id') != token or
                    value.get('rule_id') != source or value.get('owner_id') != application['owner'].entity_id):
                raise ValueError('reactive grant provenance mismatch')
            if 'type_operation' in grant:
                if actor.spec[GRANTS.KEY].get('type_sources', {}).get('sources', {}).get(key) != grant['type_operation'] or key in timed:
                    raise ValueError('reactive type contribution mismatch')
                parent_key = grant.get('parent_source')
                state = actor.spec[GRANTS.KEY]
                if (value.get('parent_source') != parent_key or parent_key not in state['effects'] or
                        state['ability_receipts'].get(ABILITIES.label(engine.r, source)) != parent_key):
                    raise ValueError('reactive type lost its owning ability receipt')
            else:
                if value.get('ability_operation') != grant['operation']:
                    raise ValueError('reactive ability contribution mismatch')
                record = timed.get(key)
                if record is None:
                    raise ValueError('reactive ability lifetime missing')
                boundary = {k: v for k, v in record.items() if k not in ('turn_owner', 'owned_statuses', 'installing')}
                if boundary != grant['timing'] or record.get('owned_statuses') or record.get('installing') is not False:
                    raise ValueError('reactive ability lifetime mismatch')
        if live and actor.abilities != GRANTS.effective(actor, 'abilities'):
            raise ValueError('reactive ability projection mismatch')
    return True
