"""One data-only operation contract boundary for externally authored policies.

Bindings name existing public Engine consumers. This registry is code-owned;
declarations cannot supply modules, callables, private arguments or grants.
"""
from copy import deepcopy
from importlib import import_module
from inspect import Parameter,signature
import re
import root_resolution as R

# operation -> (original foundation ID, public Engine method, expanded native signature)
BINDINGS={
 'objects.identity':('object_lifecycle.identity','entity_identity',None),
 'objects.use_item':('object_lifecycle.lifecycle','use_item',None),
 'resources.actions':('resources.actions','execute_source_policy_action',None),
 'resources.frequency':('resources.frequency','execute_source_policy_action',None),
 'events.subscribe':('events.dispatch','subscribe_source_policy',None),
 'events.trace':('events.trace','execution_traces',None),
 'acquisition.qualify':('acquisition.qualification','evaluate_source_policy_qualification',None),
 'acquisition.grant':('acquisition.receipt','execute_source_policy_grants',None),
 'acquisition.receipts':('acquisition.receipt','acquisition_receipts',None),
 'acquisition.withdraw':('acquisition.withdrawal','refund_grant_sources','grant_payments.refund'),
 'composition.derive':('composition.derive','evaluate_source_policy_composition',None),
 'composition.reconcile':('composition.reconcile','bind_grant_reconciliation',None),
 'roll.plan':('roll_context.plan','plan_rank_context',None),
 'roll.resolve':('roll_context.resolve','resolve_roll_context',None),
 'growth.stats':('growth.stats','allocate_trainer_growth_stats',None),
 'growth.nature':('growth.stats','commit_growth_nature','growth_stats.commit_nature'),
 'growth.forms':('growth.stats','configure_growth_forms',None),
 'growth.project':('growth.stats','growth_stat_projection',None),
 'growth.milestones':('growth.milestones','execute_source_policy_progression',None),
 'learning.grant':('learning.grant','execute_source_policy_teaching',None),
 'learning.slots':('learning.slots','acquire_grant_group','grant_payments.acquire'),
 'movement.permission':('movement.permission','move_profile',None),
 'movement.path':('movement.path','approach',None),
 'movement.teleport':('movement.path','teleport','movement_actions.teleport'),
 'movement.burrow':('movement.path','burrow_move','movement_actions.burrow_move'),
 'combat.hit':('combat.hit','use_move',None),
 'combat.ground_flight_option':('combat.hit','configure_ground_flight_option',None),
 'combat.damage':('combat.damage','use_move',None),
 'unown.adopt':('acquisition.receipt','adopt_unown_imbuement',None),
 'unown.hidden_power':('combat.hit','use_unown_hidden_power',None),
 'unown.accuracy':('combat.hit','boost_unown_attack',None),
 'unown.detect_watch':('events.dispatch','watch_unown_detect',None),
 'combat.capture':('combat.capture','throw_ball',None),
 'effects.end':('effects.lifetime','end_effects',None),
 'effects.heal':('effects.recovery','heal',None),
 'effects.revive':('effects.recovery','revive',None),
 'effects.injury':('effects.recovery','recover_injury','injury_recovery.recover_naturally'),
 'initiative.derive':('initiative.derive','initiative_value',None),
 'initiative.schedule':('initiative.schedule','prepare_initiative_schedule','initiative_schedule.prepare'),
 'initiative.replace':('initiative.schedule','replace_scheduled_participant',None),
 'activity.clock':('activity.clock','advance_time',None),
 'activity.start':('activity.job','start_activity_job','activity_jobs.start'),
 'activity.advance':('activity.job','advance_activity_job','activity_jobs.advance'),
 'activity.attempt':('activity.job','attempt_activity_job','activity_jobs.attempt'),
 'activity.interrupt':('activity.job','interrupt_activity_job','activity_jobs.interrupt'),
 'activity.resume':('activity.job','resume_activity_job','activity_jobs.resume'),
 'activity.credit':('activity.job','apply_activity_credit','activity_jobs.apply_credit'),
 'crafting.recipe':('crafting.recipe','craft_recipe','crafting_recipes.craft'),
 'crafting.product':('crafting.product','craft_recipe','crafting_recipes.craft'),
 'cultivation.plant':('cultivation.growth','plant_growth','cultivation_growth.plant'),
 'cultivation.fertilize':('cultivation.growth','fertilize_growth','cultivation_growth.fertilize'),
 'cultivation.harvest':('cultivation.harvest','harvest_growth','cultivation_harvest.harvest'),
 'training.eligibility':('training.eligibility','plan_training_eligibility','training_eligibility.prepare'),
 'training.rewards':('training.rewards','apply_training_rewards',None),
 'creation.egg':('creation.egg','create_declared_egg','creation_egg.create'),
 'creation.hatch':('creation.egg','hatch_declared_egg','creation_egg.hatch'),
 'creation.fossil':('creation.fossil','restore_declared_fossil','creation_fossil.restore'),
 'perception.observe':('perception.observe','observe_target','perception_observe.observe'),
 'perception.communicate':('perception.communicate','communicate','perception_communicate.send'),
 'control.mount':('control.mount','board_mount','control_mount.board'),
 'control.dismount':('control.mount','dismount','control_mount.dismount'),
 'control.vehicle':('control.vehicle','operate_machine','control_vehicle.operate'),
 'control.remote':('control.remote','connect_remote_control','control_remote.connect'),
 'network.enter':('network.connection','enter_network','network_connection.enter'),
 'network.exit':('network.connection','exit_network','network_connection.exit'),
 'network.integrity':('network.integrity','digital_operation','network_integrity.execute'),
 'repair.restore':('repair.restore','restore_object','repair_restore.execute'),
 'repair.damage':('repair.breach','damage_vehicle','repair_breach.damage'),
 'environment.observe':('environment.derive','observe_environment','environment_derive.observe_region'),
 'environment.bind':('environment.derive','bind_environment','environment_derive.bind'),
 'environment.change':('environment.change','change_environment','environment_change.change'),
 'environment.terrain':('environment.change','shape_ground',None),
 'maneuvers.opposed':('maneuvers.opposed','opposed_maneuver','maneuver_opposed.execute'),
 'maneuvers.grapple':('maneuvers.grapple','grapple','grapple_state.initiate'),
 'maneuvers.grapple_action':('maneuvers.grapple','grapple_action','grapple_state.action'),
}
SPECIAL={
 'effects.apply':('effects.apply',{'actor':'actor','target':'actor','effects':'array'}),
 'movement.forced':('movement.forced',{'actor':'actor','target':'actor','direction':'array','distance':'integer','source':'string'}),
}
ACTORS={'a','b','c','user','actor','attacker','target','trainer','owner','rider','mount','operator','participant','observer','sender','recipient','pokemon','provider'}
ACTOR_LISTS={'participants','combatants','targets','parents'}
INTEGERS={'amount','seconds','delta','priority','count','points','hp','reach','distance','rarity','fixed_accuracy','fixed_capture','fixed_reroll','fixed_roll','situational','dealt','nat','ap_cost','birth_level','tutor_points','duration_seconds','round_offset_seconds'}
STRINGS={'id','identity','kind','skill','purpose','source','source_id','source_ref','reason','reason_text','request_id','event_id','occurrence','group_id','region_id','network_id','avatar_id','target_id','machine_id','job_id','plant_id','egg_entity_id','fossil_entity_id','move_id','ball_name','text','mode','movement_mode','active','operation','nature','slot','source_kind','procedure'}
OBJECTS={'declaration','facts','recipe','document','investment','stats','declarations','binding','intent','context','decisions','observed_choices','challenger_options','defender_options','escape','product_policy','blindness_options'}
ARRAYS={'path','effects','requests','sources','contributors','grants','direction','destination'}
RESERVED={'_activation','_shared_accuracy','_action_grant','free_action','count_use','_grant'}
CACHE={}


def _public(value):
    if type(value) is dict:
        if any(not isinstance(key,str) or key.startswith('_') for key in value):raise ValueError('external operations cannot set private runtime metadata')
        for child in value.values():_public(child)
    elif type(value) in (list,tuple):
        for child in value:_public(child)


def _parameters(operation):
    if operation in CACHE:return deepcopy(CACHE[operation])
    from engine import Engine
    foundation,method,native=BINDINGS[operation]
    parameters=list(signature(getattr(Engine,method)).parameters.values())[1:]
    public=[p for p in parameters if p.kind not in (Parameter.VAR_KEYWORD,Parameter.VAR_POSITIONAL)]
    if native is not None and any(p.kind==Parameter.VAR_KEYWORD for p in parameters):
        module,name=native.rsplit('.',1)
        expanded=list(signature(getattr(import_module(module),name)).parameters.values())
        public_pos=[p for p in public if p.kind in (Parameter.POSITIONAL_ONLY,Parameter.POSITIONAL_OR_KEYWORD)]
        # The native adapter's leading engine/participants already have public names.
        expanded=expanded[1+len(public_pos):]
        known={p.name for p in public}
        public.extend(p for p in expanded if p.name not in known and p.kind not in (Parameter.VAR_KEYWORD,Parameter.VAR_POSITIONAL))
    result={}
    for p in public:
        if p.name.startswith('_') or p.name in RESERVED:continue
        required=p.default is Parameter.empty
        if p.name in ACTORS:kind='actor'
        elif p.name in ACTOR_LISTS:kind='actors'
        elif type(p.default) is bool:kind='boolean'
        elif p.name in INTEGERS or type(p.default) is int:kind='integer'
        elif p.name in STRINGS or type(p.default) is str:kind='string'
        elif p.name in OBJECTS:kind='object'
        elif p.name in ARRAYS or type(p.default) in (list,tuple):kind='array'
        else:kind='data'
        result[p.name]=dict(type=kind,required=required,nullable=p.default is None)
    # Some public arguments accept a documented structured alternative.
    if operation in ('roll.resolve','initiative.derive'):result['procedure']['type']='object'
    if operation=='growth.stats':result['stats']['type']='object'
    if operation=='environment.change':result['changes']['type']='object'
    if operation=='environment.terrain':result['changes']['type']='array'
    CACHE[operation]=deepcopy(result)
    return result


def describe(operation):
    if operation in SPECIAL:
        foundation,kinds=SPECIAL[operation]
        args={key:dict(type=kind,required=True,nullable=False) for key,kind in kinds.items()}
    elif operation in BINDINGS:foundation=BINDINGS[operation][0];args=_parameters(operation)
    else:raise ValueError('unsupported foundation operation: '+str(operation))
    return dict(id='operation/'+operation,operation=operation,version=1,foundation_id=foundation,
                arguments=args,source_binding='actual selected policy variant',
                lifetime_contract='native source-owned lifetime consumer; no generic invented expiry',
                execution_certified=False)


def catalog():return [describe(name) for name in sorted(set(BINDINGS)|set(SPECIAL))]


def _reference(value,inputs,prior):
    if type(value) is not dict:return None
    if '$input' in value:
        if set(value)!={'$input'} or value['$input'] not in inputs:raise ValueError('unknown operation input reference')
        return inputs[value['$input']]['type']
    if '$source' in value:
        if value!={'$source':True}:raise ValueError('selected source reference requires true')
        return 'string'
    if '$actor' in value:
        if set(value)!={'$actor'} or type(value['$actor']) is not str or not value['$actor']:raise ValueError('explicit actual actor reference required')
        return 'actor'
    if '$result' in value:
        if set(value)-{'$result','path'} or value['$result'] not in prior:raise ValueError('operation result must refer to an earlier actual step')
        if 'path' in value and (type(value['path']) is not list or any(type(key) not in (str,int) or isinstance(key,str) and key.startswith('_') for key in value['path'])):raise ValueError('public result path required')
        return 'result'
    if any(key.startswith('$') for key in value):raise ValueError('unknown operation reference')
    return None


def _value(value,kind,inputs,prior,nullable=False):
    ref=_reference(value,inputs,prior)
    if ref=='result':return
    if ref is not None:
        if kind!='data' and ref!=kind:raise ValueError('operation input/reference type does not match '+kind)
        return
    if value is None and nullable:return
    if kind=='actor':raise ValueError('actor arguments require an explicit actual $actor reference')
    if kind=='actors':
        if type(value) is not list:raise ValueError('actual actor reference list required')
        for child in value:_value(child,'actor',inputs,prior)
        return
    expected={'integer':int,'boolean':bool,'string':str,'object':dict,'array':list}
    if kind in expected and type(value) is not expected[kind]:raise ValueError('operation argument requires exact '+kind)
    if type(value) is dict:
        for child in value.values():_value(child,'data',inputs,prior)
    elif type(value) is list:
        for child in value:_value(child,'data',inputs,prior)


def _has_reference(value):
    if type(value) is dict:return any(key.startswith('$') for key in value) or any(_has_reference(v) for v in value.values())
    if type(value) is list:return any(_has_reference(v) for v in value)
    return False


def _positive(value,inputs):
    _value(value,'integer',inputs,set())
    if not _has_reference(value) and value<1:raise ValueError('positive lifetime count required')
    if type(value) is dict and '$input' in value:
        minimum=inputs[value['$input']].get('minimum')
        if minimum is not None and minimum<1:raise ValueError('lifetime input minimum must be positive')


def _event(value,inputs,repeating=False):
    allowed={'event','owner','times'} if repeating else {'event','owner','after'}
    if type(value) is not dict or set(value)-allowed or value.get('event') not in ('turn_start','turn_end','round_end','scene_end','encounter_end'):raise ValueError('unsupported lifetime event')
    if value['event'] in ('turn_start','turn_end'):
        if value.get('owner') not in ('user','target'):raise ValueError('turn lifetime requires its actual owner')
    elif 'owner' in value:raise ValueError('world lifetime cannot declare a turn owner')
    key='times' if repeating else 'after'
    if key in value:_positive(value[key],inputs)
    if value['event'] in ('scene_end','encounter_end') and (repeating or value.get('after',1)!=1):raise ValueError('unsupported scene/encounter repetition')


def validate_effects(effects,inputs=None,prior=None):
    import effects as FX,effect_lifetimes as LIFE,effect_lifetime_policy as POLICY
    inputs=inputs or {}
    if type(effects) is not list or not effects:raise ValueError('nonempty native effects required')
    for effect in effects:
        if type(effect) is not dict or effect.get('type') not in FX.HANDLERS or effect['type'] in FX.JUDGEMENT_TYPES|FX.ENGINE_TYPES:raise ValueError('unsupported executable effect operation')
        _public(effect);_value(effect,'object',inputs,prior or set())
        controls={key:effect[key] for key in ('duration','until','while','repeat') if key in effect}
        if not controls:continue
        if 'duration' in controls and 'until' in controls:raise ValueError('multiple effect lifetimes require explicit composition')
        if 'repeat' in controls:
            if effect['type'] not in POLICY.REPEAT_KINDS:raise ValueError('effect has no native repeat consumer')
        elif effect['type'] not in LIFE.KINDS:raise ValueError('effect has no native lifetime consumer')
        for key,value in controls.items():
            if key=='duration' and type(value) is dict:
                if set(value)!={'seconds'}:raise ValueError('duration requires seconds')
                _positive(value['seconds'],inputs)
            elif key=='until' and type(value) is dict:_event(value,inputs)
            elif key=='while':
                if type(value) is not dict or value.get('owner') not in ('user','target') or set(value) not in ({'owner','condition'},{'owner','cells','membership'}):raise ValueError('unsupported continuous lifetime predicate')
                if 'membership' in value and value['membership'] not in ('any','all'):raise ValueError('explicit body membership required')
            elif key=='repeat':
                if type(value) is dict and set(value)=={'seconds','times'}:
                    _positive(value['seconds'],inputs);_positive(value['times'],inputs)
                else:_event(value,inputs,True)
            elif type(value) is str:
                known={'encounter_end','encounter','인카운터 끝까지','scene_end','scene','장면','this round','이번 라운드',"end of user's next turn","start of user's next turn","end of target's next turn","start of target's next turn"}
                if value not in known and not re.fullmatch(r'([1-9][0-9]*)라운드(?: 동안)?|([1-9][0-9]*) rounds?',value):raise ValueError('unsupported textual lifetime')
            else:raise ValueError('unsupported lifetime declaration')


def validate(values,inputs=None):
    inputs=inputs or {}
    if type(values) is not dict or set(values)!={'operations'} or type(values['operations']) is not list or not values['operations']:raise ValueError('sole nonempty operations list required')
    R.freeze(values);_public(values);seen=set()
    for step in values['operations']:
        if type(step) is not dict or set(step)!={'id','operation','arguments'} or type(step['id']) is not str or not step['id'] or step['id'] in seen:raise ValueError('distinct operation step IDs and exact fields required')
        contract=describe(step['operation']);args=step['arguments'];specs=contract['arguments']
        if type(args) is not dict or set(args)-set(specs) or any(spec['required'] and key not in args for key,spec in specs.items()):raise ValueError('operation arguments do not match '+step['operation'])
        for key,value in args.items():_value(value,specs[key]['type'],inputs,seen,specs[key]['nullable'])
        op=step['operation']
        if op=='effects.apply':validate_effects(args['effects'],inputs,seen)
        validator=None;value=args.get('declaration',args.get('recipe'))
        if op=='maneuvers.opposed':
            from maneuver_opposed import declaration as validator
        elif op=='maneuvers.grapple' and value is not None:
            from grapple_state import policy as validator
        elif op=='environment.bind':
            from environment_derive import declaration as validator
        elif op in ('crafting.recipe','crafting.product'):
            from crafting_recipes import declaration as validator
        if validator is not None and not _has_reference(value):validator(value)
        seen.add(step['id'])
    return deepcopy(values['operations'])



def plan(prepared,*,event_id):
    """Pure ordered-program plan; source_ready stays false until native admission."""
    steps=validate(prepared['values'])
    ids=tuple(prepared['policy_id']+'/'+step['id'] for step in steps)
    request=R.ResolutionRequest(event_id=event_id,event_kind='authored_foundation_operations',
        profile_hash=prepared['profile_hash'],catalog_hash=R.fingerprint(catalog()),
        context_hash=R.fingerprint(dict(definition=prepared['definition_hash'],inputs=prepared['inputs_hash'])),
        clauses=tuple(R.Clause(id=identity,aspect='foundation.operations',value=step,
                         source_refs=(prepared['selected_id'],)) for identity,step in zip(ids,steps)),
        laws=(R.CompositionLaw(aspect='foundation.operations',kind='sequence',
            witness_ref='foundation_operations/ordered-program-v1',contributor_order=ids,
            observation_policy='ordered'),),candidate_closure=R.TRUE)
    result=R.resolve(request)
    if result.tag!='ModelReady':raise ValueError('foundation operation model is unresolved')
    return R.plain(R.plan_payload(result))


# Execution uses the same registry as loading; only native results, never document
# supplied Python names, can flow between steps.
def _bind(value,engine,actor,target,source,results):
    import world_entities as W
    from collections.abc import Mapping
    from dataclasses import fields,is_dataclass
    if type(value) is dict:
        if '$source' in value:return source
        if '$actor' in value:
            identity=value['$actor']
            subject=actor if identity=='actor' else target if identity=='target' else W.actor_index(engine).get(identity)
            W.require_actors(engine,subject)
            return subject
        if '$result' in value:
            result=results[value['$result']]
            for key in value.get('path',[]):
                if isinstance(result,Mapping):result=result[key]
                elif type(result) in (list,tuple) and type(key) is int:result=result[key]
                elif is_dataclass(result) and key in {f.name for f in fields(result)}:result=getattr(result,key)
                else:raise ValueError('result path does not identify public native data')
            return result
        return {key:_bind(child,engine,actor,target,source,results) for key,child in value.items()}
    if type(value) is list:return [_bind(child,engine,actor,target,source,results) for child in value]
    return value


def evidence(value,engine):
    """Detached observations: no grants, native tokens, callbacks or actor copies."""
    from collections.abc import Mapping
    from dataclasses import fields,is_dataclass
    from enum import Enum
    from fractions import Fraction
    import math,world_entities as W
    if hasattr(value,'entity_id') and hasattr(value,'spec'):
        W.require_actors(engine,value)
        return {'entity_id':value.entity_id}
    if value is None or type(value) in (str,int,bool):return value
    if isinstance(value,Enum):return evidence(value.value,engine)
    if isinstance(value,Fraction):return {'numerator':value.numerator,'denominator':value.denominator}
    if type(value) is float:
        if not math.isfinite(value):raise ValueError('nonfinite native observation')
        return {'native_decimal':repr(value)}
    if is_dataclass(value):return {f.name:evidence(getattr(value,f.name),engine) for f in fields(value) if not f.name.startswith('_')}
    if isinstance(value,Mapping):
        if all(type(key) is str for key in value):return {key:evidence(child,engine) for key,child in value.items() if not key.startswith('_')}
        return {'entries':[[evidence(k,engine),evidence(v,engine)] for k,v in value.items()]}
    if type(value) in (list,tuple):return [evidence(child,engine) for child in value]
    if type(value) in (set,frozenset):return sorted((evidence(child,engine) for child in value),key=R.canonical)
    return {'runtime_type':type(value).__name__}


def _runtime_arguments(engine,operation,args):
    import world_entities as W
    from collections.abc import Mapping
    specs=describe(operation)['arguments']
    for name,value in args.items():
        spec=specs[name];kind=spec['type']
        if value is None and spec['nullable']:continue
        if kind=='actor':W.require_actors(engine,value)
        elif kind=='actors':
            if type(value) not in (list,tuple):raise ValueError('native actor list required')
            W.require_actors(engine,*value)
        elif kind=='object':
            if not isinstance(value,Mapping):raise ValueError('native object argument required')
        elif kind=='array':
            if type(value) not in (list,tuple):raise ValueError('native array argument required')
        elif kind!='data':_value(value,kind,{},set())


def _resolved(result):
    """A native failed roll can return normally; unresolved work cannot commit."""
    from collections.abc import Mapping
    from dataclasses import fields,is_dataclass
    from source_policy import PolicyExecutionPending
    from effect_contracts import BatchResult
    blocked={'pending','unresolved','blocked','awaiting_input','unresolved_source',
             'unsupported_execution','execution_failed','deferred_suffix','PolicyInputsRequired'}
    def pending(status):
        return type(status) is str and (status in blocked or status.lower().endswith('pending') or status.endswith('InputsRequired'))
    if isinstance(result,BatchResult):
        if result.pending:raise PolicyExecutionPending('native effect batch unresolved')
        for outcome in result.outcomes:_resolved(outcome)
    elif isinstance(result,Mapping):
        if pending(result.get('status')):raise PolicyExecutionPending('native operation unresolved: '+str(result['status']))
        for value in result.values():_resolved(value)
    elif is_dataclass(result):
        if pending(getattr(result,'status',None)):raise PolicyExecutionPending('native operation unresolved: '+str(result.status))
        for field in fields(result):
            if not field.name.startswith('_'):_resolved(getattr(result,field.name))
    elif type(result) in (list,tuple):
        for child in result:_resolved(child)


def _invoke(engine,method,args):
    # Existing decorators preserve the public signature but may use a different
    # participant parameter name internally. Bind public positional parameters
    # positionally, retaining keyword-only/expanded native options by name.
    consumer=getattr(engine,method)
    positional=[p for p in signature(consumer).parameters.values() if p.kind in (Parameter.POSITIONAL_ONLY,Parameter.POSITIONAL_OR_KEYWORD)]
    last=max((i for i,p in enumerate(positional) if p.name in args),default=-1)
    keywords=dict(args);values=[]
    for p in positional[:last+1]:values.append(keywords.pop(p.name,p.default))
    return consumer(*values,**keywords)


def execute(engine,actor,target,steps,source,*,tool_use=None):
    import effects as FX,forced_movement as FORCED,world_entities as W
    from source_policy import PolicyExecutionPending
    W.require_actors(engine,actor,target)
    results={};rows=[]
    for step in steps:
        if tool_use is not None:
            import crafting_recipes as TOOLS
            if TOOLS.require_tool(engine,actor,tool_use['instance_id']) != tool_use:
                raise ValueError('physical tool identity or ownership changed during execution')
        operation=step['operation']
        args=_bind(step['arguments'],engine,actor,target,source,results)
        _runtime_arguments(engine,operation,args)
        # These public parameters name the producing source, not an arbitrary
        # authority selected independently from the admitted policy variant.
        for key in ('source','source_ref'):
            if key in args and args[key]!=source:raise ValueError('operation producing source differs from selected policy')
        if operation=='effects.apply':
            batch=FX.run_effects(engine,args['actor'],args['target'],args['effects'],{'hit':True},source)
            if any(outcome.status not in ('completed','condition_false') for outcome in batch.outcomes):
                raise PolicyExecutionPending('native effect operation unresolved')
            result=[{'source_id':outcome.source_id,'status':outcome.status,'occurrence':outcome.occurrence} for outcome in batch.outcomes]
        elif operation=='movement.forced':
            result=FORCED.displace(engine,**args)
        else:
            method=BINDINGS[operation][1]
            specs=describe(operation)['arguments']
            for key in ('source','source_ref'):
                if key in specs and key not in args:args[key]=source
            result=_invoke(engine,method,args)
        _resolved(result)
        results[step['id']]=result
        rows.append(dict(id=step['id'],operation=operation,foundation_id=describe(operation)['foundation_id'],
                         state='returned',result=evidence(result,engine)))
    return rows

