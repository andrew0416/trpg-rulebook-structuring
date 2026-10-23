"""Source-specific chain choices inside the existing native Move activation.

Only a live activation authorizes a new recipient or its two-metre movement.
The completion owner persists waits; this adapter has no separate ledger.
"""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import hashlib,json
import move_activation as ACTIVATION
import move_completion as COMPLETE
import action_lifecycle as ACTION
import world_entities as WORLD
import movement_actions as MOVEMENT
import body_state as BODY
import turn as TURN

POLICY='data/dynamic-chain-policy.json'


def declared(mm):
    return any(effect.get('type')=='multi_target_chain' for effect in mm.get('effects_exec',()))


def _document(rules):
    document=json.loads((Path(rules.root)/POLICY).read_text(encoding='utf-8'))
    if hashlib.sha256((Path(rules.root)/document['source_file']).read_bytes()).hexdigest()!=document['source_sha256']:
        raise ValueError('dynamic chain source changed')
    return document


def mechanics(rules,mid,mm):
    row=_document(rules)['moves'].get(mid)
    if row is None:return mm
    import declarative_move_contracts as DMC
    expected=DMC.prepare_mechanics(rules,mid,row['mechanics'])
    if mm!=expected:raise ValueError('selected dynamic chain mechanics changed')
    # The exact Technician sentence is consumed by this source adapter.
    return dict(mm,effects_exec=[e for e in mm['effects_exec'] if e.get('type')!='rule'])


def policy(rules,mid):
    row=_document(rules)['moves'].get(mid)
    if row is None:raise ValueError('selected dynamic chain needs its source-specific producer policy')
    import declarative_move_contracts as DMC
    expected=mechanics(rules,mid,DMC.prepare_mechanics(rules,mid,row['mechanics']))
    if rules.move(mid)!=row['definition'] or rules.move_mech(mid)[0]!=expected:
        raise ValueError('selected dynamic chain definition or mechanics changed')
    return row


def _step(e,actor,value,seen,*,first=False):
    if type(value) is not dict or set(value) not in ({'target','path','forgo_remaining'},{'target','path','forgo_remaining','movement_mode'}):
        raise ValueError('chain step requires actual target, path and before-roll forgo_remaining')
    target=value['target'];WORLD.require_actors(e,actor,target)
    if target is actor or target.entity_id in seen:raise ValueError('chain requires distinct actual recipients')
    if type(value['forgo_remaining']) is not bool:raise ValueError('chain forgo_remaining must be boolean')
    if not isinstance(value['path'],(list,tuple)):raise ValueError('chain actual path required')
    mode=value.get('movement_mode','land')
    if mode not in ('land','swim','sky','levitate'):raise ValueError('chain movement mode needs its sourced path adapter')
    if mode in ('sky','levitate'):
        path=[]
        for node in value['path']:
            if type(node) is not dict or set(node) not in ({'position','altitude'},{'position','altitude','gm_distance'}):
                raise ValueError('chain aerial path requires actual position, altitude and optional measured distance')
            path.append(dict(node,position=MOVEMENT._point(node['position'])))
    else:path=[MOVEMENT._point(q) for q in value['path']]
    if first and path:raise ValueError('first chain target uses the ordinary initial position')
    if len(path)>2:raise ValueError('chain movement exceeds source two-metre allowance')
    return dict(target=target,path=path,forgo_remaining=value['forgo_remaining'],movement_mode=mode)


def steps(e,actor,values,previous=(),*,first=False):
    if not isinstance(values,(list,tuple)) or not values:raise ValueError('explicit chain steps required')
    if len(previous)+len(values)>3:raise ValueError('chain exceeds three attacks')
    seen={target.entity_id for target in previous};result=[]
    for i,value in enumerate(values):
        step=_step(e,actor,value,seen,first=first and i==0)
        if step['forgo_remaining'] and i!=len(values)-1:raise ValueError('forgone chain attacks cannot have later steps')
        seen.add(step['target'].entity_id);result.append(step)
    return result


def _scope(e,actor,mid):
    return next((s for s in reversed(getattr(e,'_move_activation_scopes',()))
                 if s['actor'] is actor and s['move_id']==mid and 'chain' in s),None)


def require_target(e,actor,target,mid):
    scope=_scope(e,actor,mid)
    if scope is None or scope['chain'].get('target') is not target:
        raise ValueError('multi-target chain requires the actual use_move_on producer')
    if scope['profile']!=ACTIVATION._profile(e) or scope['lifetime']!=ACTIVATION._lifetime(e):
        raise ValueError('dynamic chain producer boundary changed')
    policy(e.r,mid)
    return scope


def native_transaction(e,actor,target):
    scope=next((s for s in reversed(getattr(e,'_move_activation_scopes',()))
                if s['actor'] is actor and 'chain' in s),None)
    if scope is None:return False
    require_target(e,actor,target,scope['move_id'])
    return True


def prepare(e,actor,target,move):
    scope=require_target(e,actor,target,move['id'])
    choice=scope['chain'];index=scope['index']-1
    step=choice['steps'][index];forgone=2-index if step['forgo_remaining'] else 0
    row=policy(e.r,move['id'])
    return dict(move,_chain_bonus={'accuracy':forgone*row['accuracy_per_forgone'],
        'db':forgone*row['db_per_forgone'],'damage':forgone*row['damage_per_forgone'],
        'technician':row['technician']})


def bonus(move,kind):
    return move.get('_chain_bonus',{}).get(kind,0)


def technician(actor,move):
    if not bonus(move,'technician') or actor.abilities_suppressed:return 0
    return 2 if any(value in actor.abilities for value in ('테크니션','ability/테크니션')) else 0


def movement_authority(e,actor,scope,path,mode):
    if _scope(e,actor,scope['move_id']) is not scope or not scope['activation'].get('started'):
        raise ValueError('chain movement needs its live paid source producer')
    chain=scope['chain'];step=chain['steps'][scope['index']]
    if mode is not None and (mode!=step['movement_mode'] or list(path)!=step['path']):
        raise ValueError('chain movement differs from the actual selected path')
    row=policy(e.r,scope['move_id'])
    return None if row['aoo_exemption']=='all' else chain['steps'][scope['index']-1]['target']


def _eligible(e,actor):
    return not (actor.fainted or actor.dead or actor.captured) and actor.on_field and TURN.can_act(e,actor)


def _move(e,scope,step):
    actor=scope['actor'];path=step['path'];mode=step['movement_mode']
    if path:
        if e.grid is None:raise ValueError('chain movement needs actual mapped cells')
        import control_mount as MOUNT
        if MOUNT.manages(e,actor) or actor.spec.get('_burrow',{}).get('underground') or (actor.spec.get('_movement_altitude',0) and mode not in ('sky','levitate')):
            raise ValueError('chain special movement composition needs its sourced adapter')
        if MOVEMENT.distance_budget(e,actor,mode)<=0 or not TURN.movement_permission(e,actor):
            raise ValueError('chain requires an available movement capability')
        progress={}
        moved=MOVEMENT.follow_paid_path(e,actor,path,mode=mode,maximum_distance=2,progress=progress,chain_scope=scope)
        if not _eligible(e,actor):return False
        if moved['steps']!=len(path) or progress['phase']!='complete':
            raise ValueError('chain movement interrupted; actual selected path cannot complete')
    import weapon_actions as WEAPON
    move=scope['chain']['move'];reach=WEAPON.range_spec(e,move,actor)['origin']
    if reach=='melee':reach=BODY.melee_reach(actor)
    if e.grid is not None and not BODY.in_range(e,actor,step['target'],reach,move=move):
        raise ValueError('chain target is outside actual source reach after selected movement')
    return True


def _waiting(e,scope):
    row=e._move_completions[scope['completion_id']]
    scope['chain']['awaiting_choice']=True
    frame=ACTION.move_frame(e,row)
    if frame is not None:frame['deferred']=True
    memo={id(actor):actor for actor in WORLD.actor_index(e).values()}
    saved=deepcopy(scope,memo)
    row['activation_continuation']={'scope':saved,'event_id':None,'choice':True,
        'fingerprint':ACTIVATION.R.fingerprint(ACTIVATION._continuation_facts(saved,None))}
    return {'status':'awaiting_chain_choice','completion_id':row['id'],'total':scope['total']}


def advance(e,scope):
    chain=scope['chain'];actor=scope['actor']
    if not _eligible(e,actor):scope['interrupted']=True
    while scope['index']<len(chain['steps']):
        if not _eligible(e,actor):scope['interrupted']=True;break
        i=scope['index'];step=chain['steps'][i]
        row=getattr(e,'_move_completions',{}).get(scope.get('completion_id'),{})
        if step['target'].entity_id in row.get('received',{}):
            raise ValueError('chain recipient was already targeted by the actual routed attack')
        if i and not _move(e,scope,step):scope['interrupted']=True;break
        chain['target']=step['target']
        context=(ACTION.move_grant(e,actor,step['target'],scope['move_id'],source='same_move_activation') if i else nullcontext(None))
        with context as grant:
            dealt=e.use_move(actor,step['target'],scope['move_id'],count_use=i==0,
                _activation=scope['activation'],_action_grant=grant,**scope['options'])
        if not scope['activation'].get('started'):return scope['total']
        current=getattr(e,'_move_completions',{}).get(scope.get('completion_id'),{})
        if scope['index']==i or step['target'].entity_id not in current.get('started',()):
            scope['interrupted']=True;break
        scope['total']+=dealt
        if not _eligible(e,actor):scope['interrupted']=True;break
    if not scope.get('interrupted') and scope['index']<3 and not chain['steps'][-1]['forgo_remaining']:
        return _waiting(e,scope)
    COMPLETE.seal(e,scope,interrupted=bool(scope.get('interrupted')))
    return scope['total']


def use(e,actor,primary,mid,values,options,*,move):
    policy(e.r,mid)
    selected=steps(e,actor,values,first=True)
    if selected[0]['target'] is not primary:raise ValueError('first chain recipient must be the actual primary')
    with ACTIVATION.open_scope(e,actor,mid,[step['target'] for step in selected],shared=False,primary=primary,options=options) as (activation,accuracy):
        scope=next(s for s in e._move_activation_scopes if s['activation'] is activation)
        scope['chain']={'steps':selected,'target':primary,'awaiting_choice':False,'move':move}
        return advance(e,scope)


def validate_choice(e,row,saved,index):
    scope=saved['scope'];chain=scope.get('chain')
    if (not chain or not chain.get('awaiting_choice') or saved.get('event_id') is not None or
            row['sealed'] or row['phase']!='targets' or scope['completion_id']!=row['id'] or
            scope['actor'] is not row['actor'] or list(scope['targets'])!=row['targets'] or
            scope['index']!=len(scope['targets']) or not 0<scope['index']<3 or
            set(row['results'])!={t.entity_id for t in scope['targets']} or
            saved['fingerprint']!=ACTIVATION.R.fingerprint(ACTIVATION._continuation_facts(scope,None))):
        raise ValueError('chain choice lost its authenticated completed prefix')
    if any(index.get(t.entity_id) is not t for t in scope['targets']):raise ValueError('chain lost an actual recipient')
    policy(e.r,scope['move_id'])
    return scope


def continue_move(e,completion_id,*,chain_steps=None,stop=False):
    if type(stop) is not bool or (stop and chain_steps is not None):raise ValueError('select next chain steps or stop after the completed attack')
    row=getattr(e,'_move_completions',{}).get(completion_id)
    saved=None if row is None else row.get('activation_continuation')
    if saved is None or not saved.get('choice'):raise ValueError('actual pending chain choice required')
    scope=validate_choice(e,row,saved,WORLD.actor_index(e))
    if scope['lifetime'][1:]!=ACTIVATION._lifetime(e)[1:] or scope['profile']!=ACTIVATION._profile(e):
        raise ValueError('dynamic chain choice boundary changed')
    previous=list({t.entity_id:t for t in [*scope['targets'],*COMPLETE.actual_recipients(row)]}.values())
    selected=[] if stop else steps(e,scope['actor'],chain_steps,scope['targets'])
    if any(step['target'] in previous for step in selected):
        raise ValueError('chain recipient was already targeted by the actual routed attack')
    import state_grants as GRANTS
    def apply(staged,actor):
        native=staged._move_completions[completion_id];scope=native.pop('activation_continuation')['scope']
        scope['lifetime']=ACTIVATION._lifetime(staged);scope['chain']['awaiting_choice']=False
        mapped=GRANTS._stage_transition_payload(e,staged,selected)
        scope['chain']['steps'].extend(mapped);scope['targets']=tuple([*scope['targets'],*[s['target'] for s in mapped]])
        native['targets']=list(scope['targets'])
        frame=ACTION.move_frame(staged,native)
        if frame is not None:frame.pop('deferred',None)
        context=ACTION.resolution(staged,actor,frame['source'],kind='move',_move_completion=completion_id) if frame else nullcontext()
        previous=getattr(staged,'_move_activation_scopes',None);staged._move_activation_scopes=[scope]
        try:
            with context:
                if stop:
                    COMPLETE.seal(staged,scope,interrupted=not _eligible(staged,actor));return scope['total']
                return advance(staged,scope)
        except BaseException as error:
            if ACTIVATION.suspend(staged,scope,error):return ('chain_native_pending',error.event_id)
            raise
        finally:
            if previous is None:del staged._move_activation_scopes
            else:staged._move_activation_scopes=previous
    result=GRANTS.transition(e,scope['actor'],apply,include_grid=True,include_rulings=True)
    if type(result) is tuple and result[0]=='chain_native_pending':
        import passive_events as EVENTS
        raise EVENTS.PassiveEventPending(result[1])
    return result


def ensure_clear(e):
    if any(row.get('activation_continuation',{}).get('choice') for row in getattr(e,'_move_completions',{}).values()):
        raise ValueError('unfinished chain requires its actual next choice or stop')
