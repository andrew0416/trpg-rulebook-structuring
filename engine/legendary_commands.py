"""C03-129 observations and physical control applications, never ownership grants.

Unobserved legacy actors remain unevaluated. Explicit scope is species-bound;
unknown classification is not an ordinary Pokemon. A GM tool ruling only has
the effect and lifetime it explicitly declares, independently of move receipts.
"""
from copy import deepcopy
import common_checks as C
import state_grants as G
import world_entities as W
import resolution_transaction as TX
import effect_lifetime_policy as L

KEY = 'legendary_command_observations'
FEATURE = 'feat/전설의-트레이너'
KINDS = ('unknown', 'ordinary', 'worldly_legendary', 'other_legendary')
FACT_FIELDS = {'pokemon_id','species_id','source','reason'}
CONTROL_FIELDS = FACT_FIELDS | {'user_id','instance_id','application_id','target_id','move_id',
    'instance_kind','item_rule_id','object_owner_id','applied','ruling'}


def _signed(row):return dict(row, sha256=TX.request_fingerprint(row))


def _verify(row):
    if type(row) is not dict or row.get('sha256') != TX.request_fingerprint({k:v for k,v in row.items() if k != 'sha256'}):
        raise ValueError('legendary observation evidence changed')


def _actual(engine, pokemon):
    W.require_actors(engine, pokemon)
    if pokemon.kind != 'pokemon':raise ValueError('actual Pokemon required for legendary observation')
    W._text(pokemon.spec.get('species'), 'actual observed species')
    return pokemon.spec['species']


def _source(engine):
    import trainer_feature_acquisition as FEATURES
    FEATURES._static_source(engine.r, FEATURE)


def _state(pokemon):
    return pokemon.spec.get(KEY, {'classification':None, 'recognitions':{}, 'controls':{}})


def _scope(engine, pokemon, *, source, reason):
    species = _actual(engine, pokemon)
    W._text(source, 'GM observation source');W._text(reason, 'GM observation reason')
    _source(engine)
    state = pokemon.spec.setdefault(KEY, {'classification':None, 'recognitions':{}, 'controls':{}})
    if state['classification'] is None:
        state['classification'] = _signed({'pokemon_id':pokemon.entity_id, 'species_id':species,
            'kind':'unknown', 'source':source, 'reason':reason})
    return state


def observe_classification(engine, pokemon, kind, *, source, reason):
    if kind not in KINDS:raise ValueError('explicit legendary classification required')
    def apply(e, p):
        state = _scope(e,p,source=source,reason=reason)
        state['classification'] = _signed({'pokemon_id':p.entity_id, 'species_id':p.spec['species'],
            'kind':kind, 'source':source, 'reason':reason})
        return deepcopy(state['classification'])
    return G.transition(engine,pokemon,apply)


def classification(engine, pokemon):
    row = _state(pokemon)['classification']
    if row is None:return 'not_evaluated'
    _actual(engine,pokemon);_source(engine);validate_actor(pokemon)
    return row['kind'] if row['species_id'] == pokemon.spec['species'] else 'unknown'


def qualification(engine, pokemon, trainer=None):
    kind = classification(engine,pokemon)
    if kind == 'not_evaluated':return {'status':'not_evaluated'}
    if kind == 'ordinary':return {'status':'not_applicable'}
    if kind in ('unknown','other_legendary'):
        return C.PendingDecision('GM legendary classification required' if kind == 'unknown'
            else 'other legendary Pokemon requires its own authority; C03-129 does not grant it')
    if trainer is None:trainer = W.actor_index(engine).get(pokemon.spec.get('trainer_id'))
    W.require_actors(engine,trainer,pokemon)
    if trainer.kind != 'trainer':raise ValueError('actual Trainer required for legendary qualification')
    import acquired_features as ACQUIRED
    recognition = _state(pokemon)['recognitions'].get(trainer.entity_id,{})
    return {'status':'applicable', 'trainer_id':trainer.entity_id,
        'qualified':ACQUIRED.owned_rule_count(trainer,FEATURE) > 0,
        'recognized':recognition.get('recognized') if recognition.get('species_id') == pokemon.spec['species'] else None,
        'grants_ownership':False}


def observe_recognition(engine,pokemon,trainer,recognized,*,source,reason):
    W.require_actors(engine,trainer,pokemon)
    if trainer.kind != 'trainer' or type(recognized) is not bool:
        raise ValueError('actual trainer and explicit recognition fact required')
    def apply(e,p,t):
        state = _scope(e,p,source=source,reason=reason)
        row = _signed({'pokemon_id':p.entity_id,'species_id':p.spec['species'],
            'trainer_id':t.entity_id,'recognized':recognized,'source':source,'reason':reason})
        state['recognitions'][t.entity_id] = row
        return deepcopy(row)
    return G.transition(engine,pokemon,apply,participants=(trainer,))


def pending(engine,pokemon):
    result = qualification(engine,pokemon)
    return result if isinstance(result,C.PendingDecision) else None


def uncontrolled(engine,pokemon):
    result = qualification(engine,pokemon)
    return not isinstance(result,C.PendingDecision) and result['status'] == 'applicable' and not result['qualified']


def _ruling(value):
    if value is None:return C.PendingDecision('actual control-tool effect, cost, scope and lifetime ruling required')
    if type(value) is not dict:raise ValueError('explicit control-tool ruling required')
    fields = {'authority','source','reason','effect','use','cost','lifetime'}
    if set(value) != fields:return C.PendingDecision('complete control-tool effect, cost, scope and lifetime ruling required')
    for key in ('source','reason'):W._text(value[key],'control ruling '+key)
    if value['authority'] != 'gm_ruling' or value['effect'] != 'waive_c129_penalty':
        return C.PendingDecision('this control effect requires its own source adapter or explicit supported GM ruling')
    if value['use'] not in ('carried_by_user','equipped_by_user','equipped_by_pokemon'):
        return C.PendingDecision('control-tool application requires a supported actual physical use')
    if value['cost'] not in ('none','standard','shift','swift'):
        return C.PendingDecision('control-tool activation cost requires its native cost adapter')
    lifetime = value['lifetime']
    if type(lifetime) is not dict or set(lifetime)-{'commands','duration','until','while'}:
        return C.PendingDecision('control-tool lifetime requires existing non-repeating lifetime controls')
    if 'commands' not in lifetime or not any(k in lifetime for k in ('duration','until','while')) and lifetime['commands'] is None:
        return C.PendingDecision('explicit control-tool command limit or ending required')
    if lifetime['commands'] is not None:C.integer(lifetime['commands'],'declared control command limit',1)
    return deepcopy(value)


def _physical(engine,pokemon,user,row):
    obj = getattr(engine,'_physical_objects',{}).get(row['instance_id'])
    if obj is None:raise ValueError('actual registered control-tool instance required')
    if (obj.get('kind'),obj.get('item_rule_id')) != (row['instance_kind'],row['item_rule_id']):
        raise ValueError('control-tool physical source identity changed')
    import environmental_item_state as ENV
    ENV.require_usable(engine,obj)
    if any(W.physical_lifecycle(obj)[key] for key in ('disabled','suppressed')):
        raise ValueError('actual control-tool disabled or suppressed')
    use = row['ruling']['use']
    holder = pokemon if use == 'equipped_by_pokemon' else user
    if obj.get('owner_id') != row['object_owner_id']:raise ValueError('control-tool ownership changed')
    if use == 'carried_by_user':
        if obj.get('carrier_id') != user.entity_id:raise ValueError('control-tool is not carried by its actual user')
    else:
        import items as ITEMS
        records = [r for r in getattr(holder,'_item_reg',{}).values() if r.get('instance_id') == obj['id']]
        if obj.get('equipped_by') != holder.entity_id or len(records) != 1 or not ITEMS.equipment_benefit_active(holder,records[0]):
            raise ValueError('control-tool requires its actual active equipment benefit')
    return obj


def _record(engine,pokemon,row):
    return {L.KEY:row['lifetime'],'lifetime_actor':W.actor_index(engine)[row['user_id']], 'lifetime_target':pokemon}


def _close(engine,row,reason):
    row.pop('sha256',None);row.update(status='closed',ending=reason,ended_at=engine.elapsed_seconds)
    row['sha256'] = TX.request_fingerprint(row)


def _failure(engine,pokemon,row,event='reconcile',actor=None):
    user = W.actor_index(engine).get(row['user_id'])
    if user is None or user.entity_id != pokemon.spec.get('trainer_id'):return 'current trainer relationship changed'
    if row['species_id'] != pokemon.spec.get('species'):return 'actual species changed'
    try:_physical(engine,pokemon,user,row)
    except ValueError as exc:return str(exc)
    record = _record(engine,pokemon,row)
    if not L.holds(engine,record):return 'control lifetime condition ended'
    if L._ended(engine,record,event,actor):return 'control lifetime '+event
    return None


def has_controls(engine):
    return any(row['status'] == 'live' for p in W.actor_index(engine).values() for row in _state(p)['controls'].values())


def next_interval(engine,end_at):
    deadlines = [row['lifetime']['end_at'] for p in W.actor_index(engine).values()
        for row in _state(p)['controls'].values() if row['status'] == 'live' and
        row['lifetime'].get('end_at') is not None and engine.elapsed_seconds < row['lifetime']['end_at'] < end_at]
    return min([end_at,*deadlines])-engine.elapsed_seconds


def boundary(engine,event,actor=None):
    for pokemon in W.actor_index(engine).values():
        for row in _state(pokemon)['controls'].values():
            if row['status'] == 'live':
                reason = _failure(engine,pokemon,row,event,actor)
                if reason is not None:_close(engine,row,reason)


def observe_control(engine,pokemon,*,user,instance_id,application_id,target,move_id,applied,source,reason,ruling=None):
    """A specific observed application, with explicit GM mechanics, never an item-name inference."""
    W.require_actors(engine,user,pokemon,target)
    if user.kind != 'trainer' or pokemon.spec.get('trainer_id') != user.entity_id:
        raise ValueError('control application needs the actual current trainer')
    for value,label in ((instance_id,'control instance'),(application_id,'control application')):W._text(value,label)
    obj = getattr(engine,'_physical_objects',{}).get(instance_id)
    if obj is None or obj.get('kind') not in ('physical_object','item_instance'):
        raise ValueError('actual registered control-tool instance required')
    if type(applied) is not bool:raise ValueError('explicit actual tool application observation required')
    resolved = engine._ruleset_move(pokemon,move_id)
    if resolved is None:return C.PendingDecision('selected control command move unavailable')
    policy = _ruling(ruling)
    intent = {'pokemon_id':pokemon.entity_id,'species_id':_actual(engine,pokemon),'user_id':user.entity_id,
        'instance_id':instance_id,'application_id':application_id,'target_id':target.entity_id,
        'instance_kind':obj['kind'],'item_rule_id':obj.get('item_rule_id'),
        'object_owner_id':obj.get('owner_id'),
        'move_id':resolved,'applied':applied,'source':source,'reason':reason,'ruling':deepcopy(ruling)}
    def apply(e,p,u,t):
        state = _scope(e,p,source=source,reason=reason)
        old = state['controls'].get(application_id)
        if old is not None:
            if old['intent'] != intent:raise ValueError('control application identity cannot change; observe a new application')
            return deepcopy(old)
        row = dict(intent,intent=deepcopy(intent),status='pending',uses=0,lifetime=None,ending=None,ended_at=None)
        if applied and not isinstance(policy,C.PendingDecision):
            _physical(e,p,u,row)
            lifetime = {k:v for k,v in policy['lifetime'].items() if k != 'commands'}
            row['lifetime'] = L.prepare(e,u,p,lifetime,policy['source'])[L.KEY]
            if policy['cost'] != 'none':
                import turn as TURN
                if not TURN.spend(e,u,policy['cost'],'explicit GM control-tool application'):
                    return C.PendingDecision('control-tool native activation action unavailable')
            row['status'] = 'live'
        state['controls'][application_id] = _signed(row)
        return deepcopy(state['controls'][application_id])
    return G.transition(engine,pokemon,apply,participants=(user,target))


def end_control(engine,pokemon,application_id,*,reason):
    W._text(reason,'actual control effect ending')
    def apply(e,p):
        row = _state(p)['controls'].get(application_id)
        if row is None:raise ValueError('actual control application required')
        if row['status'] != 'closed':_close(e,row,reason)
        return deepcopy(row)
    return G.transition(engine,pokemon,apply)


def control_permission(engine,user,pokemon,target,move_id,application_id):
    result = qualification(engine,pokemon)
    if isinstance(result,C.PendingDecision):return result
    if result['status'] != 'applicable':raise ValueError('C03-129 control effect requires an observed worldly legendary')
    row = _state(pokemon)['controls'].get(application_id)
    if row is None:raise ValueError('actual observed control application required')
    _verify(row)
    if (row['user_id'],row['target_id'],row['move_id']) != (user.entity_id,target.entity_id,move_id):
        raise ValueError('control application belongs to a different user or exact command')
    if row['status'] == 'pending':return C.PendingDecision('actual applied control-tool effect and complete supported ruling required')
    if row['status'] != 'live':raise ValueError('control application already ended or consumed')
    failure = _failure(engine,pokemon,row)
    if failure is not None:raise ValueError(failure)
    return row


def consume_control(engine,pokemon,application_id):
    row = _state(pokemon)['controls'][application_id]
    row.pop('sha256',None);row['uses'] += 1
    limit = row['ruling']['lifetime']['commands']
    if limit is not None and row['uses'] >= limit:_close(engine,row,'declared command limit consumed')
    else:row['sha256'] = TX.request_fingerprint(row)


def validate_actor(pokemon):
    if KEY not in pokemon.spec:return True
    state = pokemon.spec[KEY]
    if pokemon.kind != 'pokemon' or type(state) is not dict or set(state) != {'classification','recognitions','controls'}:
        raise ValueError('legendary observations require their actual Pokemon state')
    row = state['classification'];_verify(row)
    if set(row) != FACT_FIELDS | {'kind','sha256'} or row.get('kind') not in KINDS:raise ValueError('explicit legendary classification required')
    if type(state['recognitions']) is not dict or type(state['controls']) is not dict:
        raise ValueError('actual recognition and control identities required')
    for value in (row,*state['recognitions'].values(),*state['controls'].values()):
        _verify(value)
        if value.get('pokemon_id') != pokemon.entity_id:raise ValueError('legendary observation belongs to another Pokemon')
        for key in ('species_id','source','reason'):W._text(value.get(key),'legendary observation '+key)
    for trainer,value in state['recognitions'].items():
        if set(value) != FACT_FIELDS | {'trainer_id','recognized','sha256'} or value.get('trainer_id') != trainer or type(value.get('recognized')) is not bool:raise ValueError('actual recognition relationship required')
    for identity,value in state['controls'].items():
        if set(value) != CONTROL_FIELDS | {'intent','status','uses','lifetime','ending','ended_at','sha256'}:
            raise ValueError('exact observed control application fields required')
        if value.get('application_id') != identity or value.get('status') not in ('pending','live','closed'):
            raise ValueError('actual control application state required')
        for key in ('user_id','instance_id','application_id','target_id','move_id'):W._text(value[key],'control '+key)
        if type(value['applied']) is not bool or value['instance_kind'] not in ('physical_object','item_instance'):
            raise ValueError('actual physical control application observation required')
        C.integer(value.get('uses'),'control command uses',0)
        if type(value.get('intent')) is not dict or set(value['intent']) != CONTROL_FIELDS or any(value.get(k) != v for k,v in value['intent'].items()):
            raise ValueError('control application differs from its actual observed input')
        if value['status'] == 'live' and (not value.get('applied') or value.get('lifetime') is None):
            raise ValueError('live control requires an actual applied effect and declared lifetime')
        if value['lifetime'] is not None and isinstance(_ruling(value['ruling']),C.PendingDecision):
            raise ValueError('active control effect needs its supported declared ruling')
        if value['lifetime'] is not None:
            declaration = {k:v for k,v in value['ruling']['lifetime'].items() if k != 'commands'}
            if value['lifetime'].get('declaration') != declaration:raise ValueError('control lifetime differs from its explicit ruling')
            limit = value['ruling']['lifetime']['commands']
            if limit is not None and (value['uses'] > limit or value['uses'] == limit and value['status'] != 'closed'):
                raise ValueError('control command limit does not match its consumption')
        if value['status'] == 'closed':
            W._text(value['ending'],'actual control ending');C.integer(value['ended_at'],'actual control end time',0)
        elif value['ending'] is not None or value['ended_at'] is not None:raise ValueError('unended control cannot have an ending event')
    return True


def validate_world(engine,actors):
    for pokemon in actors.values():
        validate_actor(pokemon)
        if KEY not in pokemon.spec:continue
        for trainer in _state(pokemon)['recognitions']:
            if trainer not in actors or actors[trainer].kind != 'trainer':raise ValueError('actual recognition trainer reference required')
        for row in _state(pokemon)['controls'].values():
            if row['user_id'] not in actors or actors[row['user_id']].kind != 'trainer' or row['target_id'] not in actors:
                raise ValueError('actual control user and command target references required')
            if row['instance_id'] not in getattr(engine,'_physical_objects',{}):raise ValueError('actual control physical instance reference required')
    return True
