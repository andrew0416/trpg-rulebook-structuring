"""Declared initiative operations over actual, source-owned contributions."""
from copy import deepcopy
from fractions import Fraction
from math import isfinite
import composition_derive as COMPOSITION


class InitiativePending(ValueError):
    pass


class InitiativeStateError(ValueError):
    pass


def _native(reader, *args):
    try:
        return reader(*args)
    except ValueError as exc:
        raise InitiativeStateError(str(exc)) from exc


def operation(effect):
    """Normalize an external/native effect without choosing its composition."""
    kind = effect.get('type')
    keys = [k for k in ('delta', 'multiplier', 'set_to') if k in effect]
    if kind == 'initiative_multiplier':
        if keys or 'value' not in effect:
            raise ValueError('one initiative multiplier value required')
        key, amount = 'multiplier', effect['value']
    elif kind == 'initiative' and len(keys) == 1:
        key, amount = keys[0], effect[keys[0]]
    else:
        raise ValueError('one additive, multiplier or fixed initiative operation required')
    if key == 'multiplier':
        if type(amount) is float:
            if not isfinite(amount):
                raise ValueError('finite initiative multiplier required')
            ratio = Fraction(str(amount))
            amount = {'numerator': ratio.numerator, 'denominator': ratio.denominator}
        exact = COMPOSITION.R._number(amount)
        if exact < 0:
            raise ValueError('nonnegative initiative multiplier required')
    elif type(amount) is not int:
        raise ValueError('integer initiative delta or fixed value required')
    result = {'operation': {'delta': 'add', 'multiplier': 'multiply', 'set_to': 'replace'}[key],
              'value': deepcopy(amount)}
    if 'priority' in effect:
        if key != 'set_to' or type(effect['priority']) is not int:
            raise ValueError('integer priority belongs only to fixed initiative')
        result['priority'] = effect['priority']
    elif key == 'set_to':
        result['priority'] = 0
    return result


def selected(rules, source):
    if type(source) is not str or not source.strip():
        raise ValueError('initiative source identity required')
    if source in rules.selection.units and rules._selected_rule(source) != source:
        raise ValueError('initiative source selection changed')
    return source


def derive(speed, contributions, procedure=None):
    """Apply declared phases; unspecified competing phases remain pending."""
    if type(speed) is not int or type(contributions) is not list:
        raise ValueError('actual integer staged speed and contributions required')
    rows = []
    phases = {}
    for original in contributions:
        if type(original) is not dict or not {'id','source','value','operation'} <= set(original) or set(original)-{'id','source','value','operation','priority','active'}:
            raise ValueError('exact initiative contribution fields required')
        row = deepcopy(original)
        phase = row.pop('operation')
        if phase not in ('add', 'flinch', 'multiply', 'replace'):
            raise ValueError('known initiative phase required')
        if phase in ('add', 'flinch', 'replace') and type(row['value']) is not int:
            raise ValueError('integer additive or fixed initiative contribution required')
        if phase == 'multiply' and COMPOSITION.R._number(row['value']) < 0:
            raise ValueError('nonnegative initiative multiplier required')
        if phase == 'replace':
            row.setdefault('priority', 0)
        phases.setdefault(phase, []).append(row['id'])
        rows.append(row)
    if procedure is None:
        if set(phases) <= {'add', 'flinch'}:
            order = [p for p in ('add', 'flinch') if p in phases]
        elif len(phases) == 1 and len(rows) == 1:
            order = list(phases)
        else:
            raise InitiativePending('initiative composition requires explicit phase order')
        rounding = 'floor'
    else:
        if type(procedure) is not dict or set(procedure)-{'source','order','rounding','speed_subject','contribution_subject'} or not {'source','order','rounding'} <= set(procedure):
            raise ValueError('explicit initiative procedure source, order and rounding required')
        if type(procedure['source']) is not str or not procedure['source'].strip():
            raise ValueError('initiative procedure source identity required')
        order, rounding = procedure['order'], procedure['rounding']
        if (type(order) is not list or any(type(p) is not str or p not in ('add','flinch','multiply','replace') for p in order)
                or len(order) != len(set(order)) or not set(phases) <= set(order)):
            raise ValueError('initiative procedure must account for every phase exactly once')
        if rounding not in ('floor','ceil','trunc'):
            raise ValueError('explicit integer initiative rounding required')
    steps = [{'law': 'add' if phase == 'flinch' else phase, 'contributors': phases[phase]}
             for phase in order if phase in phases]
    try:
        result = COMPOSITION.derive(speed, rows, steps, rounding=rounding)
    except COMPOSITION.CompositionPending as exc:
        raise InitiativePending(str(exc)) from exc
    result['initiative_contributions'] = deepcopy(contributions)
    result['procedure'] = deepcopy(procedure)
    return result


def collect(rules, actor, *, engine=None):
    """Read native producers; do not register actors or mutate numeric ledgers."""
    import state_grants as GRANTS
    import training_features as TRAINING
    import taskmaster as TASK
    import trainer_capabilities as TRAINER
    import condition_instances as CONDITIONS
    import combat_timing as TIME
    rows = []
    def add(identity, source, op):
        rows.append(dict(id=identity, source=selected(actor.r, source), **op))
    hardened=_native(TASK.bonus,actor,'initiative')
    if hardened:add('taskmaster:hardened',TASK.CLASS,dict(operation='add',value=hardened))
    if engine is not None:
        import channeler as CHANNEL
        channel_bonus=CHANNEL.spirit_bonus(engine,actor,'initiative')
        if channel_bonus:add('channeler:spirit',CHANNEL.SPIRIT,dict(operation='add',value=channel_bonus))
        import type_ace as TA
        ace=TA.initiative(engine,actor)
        if ace:add('type_ace:celerity',TA.uid('Celerity'),dict(operation='add',value=ace))
    import chef_cooking as CHEF
    tasted=_native(CHEF.initiative_bonus,actor)
    if tasted:add('chef:accentuated_taste',CHEF.ACCENTUATED,dict(operation='add',value=tasted))
    bonus = actor.initiative_bonus
    override = actor.initiative_override
    if type(bonus) is not int or (override is not None and type(override) is not int):
        raise ValueError('initiative inputs must be integers')
    state = actor.spec.get(GRANTS.KEY, {})
    channel = state.get('numbers', {}).get('initiative_bonus', {})
    owned = channel.get('sources', {})
    independent = bonus - sum(owned.values())
    if independent:
        add('bonus:baseline', 'state/initiative_bonus', dict(operation='add', value=independent))
    for token, amount in owned.items():
        owner = state.get('sources', {}).get(token)
        if owner is None:
            # Registered feature effects own their numeric child token through
            # the parent's explicit effect_sources receipt, not another source.
            parents = [row for row in state.get('sources', {}).values()
                       if token in row.get('effect_sources', ())]
            if len(parents) != 1:
                raise ValueError('initiative contribution requires its live source receipt')
            owner = parents[0]
        add('bonus:'+token, owner.get('rule_id', token), dict(operation='add', value=amount))
    amount = _native(TRAINER.initiative_bonus, actor)
    if amount:
        add('trainer:initiative', 'edge/패기', dict(operation='add', value=amount))
    for index, record in enumerate(_native(TRAINING.active, actor)):
        amount = TRAINING.bonuses(record).get('initiative', 0)
        if record['rule_id']==TRAINING.AGILITY:
            import control_mount as MOUNT
            amount*=_native(MOUNT.agility_multiplier,actor)
        if amount:
            add('training:'+str(index), record['rule_id'], dict(operation='add', value=amount))
    if engine is not None:
        import blessing_effects as BLESSINGS
        for index, record in enumerate(_native(BLESSINGS.initiative_contributions, engine, actor)):
            add('team:'+str(index), record['source'], dict(operation='add', value=record['amount']))
    flinch = _native(CONDITIONS.flinch_penalty, actor)
    for record in CONDITIONS.records(actor, '풀죽음') if flinch else ():
        add('flinch:'+record['id'], record['source'], dict(operation='flinch', value=-5))
    for condition in sorted(actor.conditions):
        for index, effect in enumerate(rules.condition_effects(condition)):
            if effect.get('type') not in ('initiative','initiative_multiplier') or (condition == '풀죽음' and flinch):
                continue
            unknown = {k for k in effect if not k.startswith('_')}-{'type','delta','multiplier','set_to','value','priority'}
            if unknown:
                raise InitiativePending('condition initiative operation has unresolved qualifiers')
            add('condition:'+condition+':'+str(index), 'condition/'+condition, operation(effect))
    timed = TIME.records(actor)
    # Legacy zero projection is kept for compatibility, but counted only once.
    baseline = actor.custom_conditions.get('timed_initiative_baseline')
    if baseline is not None:
        override = baseline['value']
    if override is not None:
        fixed = actor.custom_conditions.get('initiative_fixed')
        if fixed is not None and fixed['operation']['value'] != override:
            raise ValueError('fixed initiative differs from its declared producer')
        add('fixed:baseline', fixed['source'] if fixed else 'state/initiative_override',
            fixed['operation'] if fixed else dict(operation='replace', value=override, priority=0))
    for index, record in enumerate(timed):
        op = record.get('initiative_operation')
        if op is None and record.get('initiative_zero'):
            op = dict(operation='replace', value=0, priority=0)
        if op is not None:
            add('timed:'+str(index), record['source'], op)
    for field in ('registry', 'modifiers'):
        for index, effect in enumerate(getattr(actor, field, ())):
            if effect.get('type') not in ('initiative','initiative_multiplier'):
                continue
            weather={'ability/엽록소-playtest':'sunny',
                     'ability/쓱쓱-playtest':'rain','ability/쓱쓱-playtest-2':'rain',
                     'ability/모래헤치기-playtest':'sandstorm',
                     'ability/눈치우기':'hail','ability/눈치우기-2':'hail'}.get(effect.get('_rule_id'))
            if (weather is not None and effect.get('type')=='initiative_multiplier'
                    and effect.get('value')==2 and effect.get('if')==weather+' or hp < half'):
                import ability_transitions as ABILITIES
                source=effect['_rule_id']
                if not ABILITIES.active(actor,source):continue
                if actor.hp*2>=actor.base_max_hp:
                    if engine is None:raise InitiativePending('weather initiative Ability needs actual weather')
                    import effects as FX
                    if not FX.weather_matches(engine,weather,actor) or __import__('survivalist_class').weather_ability_suppressed(engine,actor,source):continue
                effect={key:value for key,value in effect.items() if key!='if'}
            unknown = {k for k in effect if not k.startswith('_')}-{'type','delta','multiplier','set_to','value','priority','source'}
            if unknown:
                raise InitiativePending('registered initiative extension has unresolved qualifiers')
            token = effect.get(GRANTS.TAG)
            if token is not None:
                owner = state.get('sources', {}).get(token)
                if owner is None:
                    raise ValueError('registered initiative requires its live source receipt')
                source = owner.get('rule_id', token)
            else:
                source = effect.get('_initiative_source', effect.get('source'))
            if source is None:
                raise InitiativePending('registered initiative extension requires an explicit source')
            if '_initiative_receipt' in effect:
                import effect_contracts as CONTRACTS
                if engine is None:
                    raise InitiativePending('initiative effect receipt needs actual engine')
                receipt = effect['_initiative_receipt']
                producer = engine._effect_dispatch_receipts.get(receipt)
                if not producer or producer['status'] != 'completed':
                    raise ValueError('initiative needs a completed producer receipt')
                CONTRACTS.validate_receipt(engine, receipt, source, effect['_initiative_occurrence'],
                                          producer['actor'], producer['target'], producer['effect'])
                if actor not in CONTRACTS.recipients(producer['actor'], producer['target'], producer['effect']):
                    raise ValueError('initiative recipient differs from its producer')
                if operation(producer['effect']) != operation(effect):
                    raise ValueError('initiative operation differs from its producer')
            add(field+':'+str(index), source, operation(effect))
    return rows


def subject(engine, participant, procedure):
    """Bind a declared speed basis to the actual current controller relation."""
    import world_entities as WORLD
    basis = (procedure or {}).get('speed_subject', 'self')
    if type(participant) is dict:
        import special_entities as SPECIAL
        uid = participant.get('id')
        if engine is None or getattr(engine, '_physical_objects', {}).get(uid) is not participant:
            raise ValueError('actual initiative object required')
        SPECIAL.validate_record(engine, participant)
        if participant['kind'] != 'vehicle' or basis != 'driver':
            raise InitiativePending('vehicle initiative needs explicit driver speed basis')
        identity = participant.get('driver_id')
        index = WORLD.actor_index(engine)
        if identity is None:
            raise InitiativePending('actual vehicle driver is unresolved')
        actor = index.get(identity)
        if actor is None:
            raise ValueError('vehicle driver must resolve to an actual actor')
    else:
        actor = participant
        if engine is not None:
            WORLD.actor_index(engine, extra=(actor,))
        if basis == 'controller':
            if engine is None:
                raise ValueError('actual engine required for controller speed')
            kind = WORLD.identity_field(engine, actor, 'controller_kind')
            identity = WORLD.identity_field(engine, actor, 'controller_id')
            if kind != 'actor' or identity is None:
                raise InitiativePending('initiative controller needs an actual actor relation')
            actor = WORLD.actor_index(engine)[identity]
        elif basis != 'self':
            raise ValueError('explicit self, controller or vehicle driver speed basis required')
    return actor


def contributions_for(rules, participant, speed_actor, procedure, engine):
    basis = (procedure or {}).get('contribution_subject', 'participant')
    if type(participant) is dict:
        if basis not in ('none', 'speed_actor'):
            raise InitiativePending('vehicle contribution subject needs explicit none or speed_actor')
        return [] if basis == 'none' else collect(rules, speed_actor, engine=engine)
    if basis not in ('participant', 'speed_actor'):
        raise ValueError('explicit participant or speed_actor contribution subject required')
    return collect(rules, participant if basis == 'participant' else speed_actor, engine=engine)


def validate_world(engine, index):
    """Producer-bound operations must survive saving with their actual identity."""
    import combat_timing as TIME
    import effect_contracts as CONTRACTS
    for actor in index.values():
        entries = [(r, r.get('initiative_operation'), r.get('effect_receipt'),
                    r.get('source'), r.get('effect_occurrence'))
                   for r in TIME.records(actor) if 'initiative_operation' in r]
        entries += [(r, operation(r), r['_initiative_receipt'], r.get('_initiative_source'),
                     r.get('_initiative_occurrence'))
                    for r in actor.registry if '_initiative_receipt' in r]
        fixed = actor.custom_conditions.get('initiative_fixed')
        if fixed is not None:
            projected = actor.custom_conditions.get('timed_initiative_baseline',{}).get('value',actor.initiative_override)
            if projected != fixed['operation']['value']:
                raise ValueError('fixed initiative projection differs from its producer')
            entries.append((fixed,fixed['operation'],fixed['receipt'],fixed['source'],fixed['occurrence']))
        for record, op, receipt, source, occurrence in entries:
            selected(engine.r, source)
            producer = engine._effect_dispatch_receipts.get(receipt)
            if not producer or producer['status'] != 'completed':
                raise ValueError('initiative requires its actual completed producer')
            CONTRACTS.validate_receipt(engine, receipt, source, occurrence,
                                      producer['actor'], producer['target'], producer['effect'])
            import native_order_transfer as TRANSFER
            if TRANSFER.origin(engine,actor,record) not in CONTRACTS.recipients(producer['actor'], producer['target'], producer['effect']):
                raise ValueError('initiative recipient differs from its producer')
            if op != operation(producer['effect']):
                raise ValueError('initiative operation differs from its actual producer')
            if record.get('initiative_zero') and op != {'operation':'replace','value':0,'priority':0}:
                raise ValueError('initiative zero projection differs from its actual operation')
    return True


def install_temporary(engine, actor, target, effect, source, receipt, occurrence):
    """Use the existing graph transaction for the complete temporary grant."""
    import state_grants as GRANTS
    import effect_contracts as CONTRACTS
    import effect_lifetimes as LIFE
    def apply(staged, owner, recipient):
        for subject in CONTRACTS.recipients(owner, recipient, effect):
            LIFE.install(staged, owner, subject, effect, source, receipt, occurrence)
    return GRANTS.transition(engine, actor, apply, participants=(target,))
