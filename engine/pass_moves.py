"""Source-bound mapped Pass activation, composed from existing paid owners.

The path determines all recipients; callers adjudicate only physical-object
hits/pre-DR damage. Creature accuracy, damage and completion stay native.
Printed Pass uses reviewed Move contracts; Conqueror's actual Order converts its
five eligible printed range families without changing their native effects.
Native recipient waits preserve the paid ordered path in the activation owner.
"""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
import json
import body_state as BODY
import world_entities as WORLD
import physical_object_attacks as OBJECTS
import movement_actions as MOVEMENT
import action_lifecycle as ACTION
import move_activation as ACTIVATION
import state_grants as GRANTS
import turn as TURN
import frequency as FREQ

KEY='_pass_moves'
SOURCE='input/ch10-index-reference.md:347'


def is_pass(move):
    """Pass is an independent printed range keyword; Groundsource is distinct."""
    return any(token.strip()=='통과' for token in move.get('range','').split(','))


def _require_owner(e,actor,scope):
    if (getattr(e,'_pass_move_scope',None) is not scope or scope['actor'] is not actor
            or e._active_turn_actor is not actor or scope['round']!=e.round_no):
        raise ValueError('Pass requires its live actual path producer')


def require_scope(e,actor,scope):
    _require_owner(e,actor,scope)
    if scope.get('conversion') is not None:
        if scope['conversion'].get('source')=='feat/열광':
            __import__('tumbler').validate_pass(e,actor.entity_id,scope['conversion'],scope['round'])
        elif scope['conversion'].get('source')=='feat/스탯-메뉴버':
            import stat_ace as STAT
            STAT.conversion_proof(e,actor.entity_id,scope['conversion'],scope['round'])
        else:
            import conquerors_march as MARCH
            MARCH.require_conversion(e,actor,scope['conversion'])
    return scope


def converted_scope(e,actor,mid):
    scope=getattr(e,'_pass_move_scope',None)
    return scope if scope is not None and scope['actor'] is actor and scope['move_id']==mid and scope.get('conversion') is not None else None


def range_spec(e,actor,move):
    scope=converted_scope(e,actor,move['id'])
    if scope is None:return None
    require_scope(e,actor,scope)
    return {'raw':'근접, 통과','origin':'melee','targets':1,'parsed':True}


def bind(e,actor,move):
    scope=converted_scope(e,actor,move['id'])
    if scope is None:return move
    require_scope(e,actor,scope)
    return dict(move,_tumbler_no_critical=scope['conversion'].get('source')=='feat/열광',range='근접, 통과',keywords=[k for k in move.get('keywords',[]) if k!='대시']+['통과'],
                _effect_area_cells=set().union(*(BODY.at_position(actor,q) for q in scope['path'])))


def converted_policy(e,mid,conversion=None):
    import conquerors_march as MARCH
    move=e.r.move(mid);mm=e.r.move_mech(mid)[0]
    if conversion and conversion.get('source')=='feat/열광':
        if mid!=__import__('tumbler').ACE:raise ValueError('Flip Out Pass only converts Aerial Ace')
    elif conversion and conversion.get('source')=='feat/스탯-메뉴버':
        import stat_ace as STAT,weapon_actions as WEAPONS
        original=WEAPONS.range_spec(e,move)
        if move.get('class')!='물리' or original.get('origin')!='melee' or original.get('targets')!=1 or original.get('shape'):
            raise ValueError('Stat Maneuver Pass needs Physical Melee 1-Target')
    elif not MARCH.eligible(move):raise ValueError('converted Pass lost its selected eligible Move')
    return {'definition':move,'mechanics':mm,'sharp':'베기' in move.get('keywords',[]),
            'source':conversion.get('source',MARCH.FEATURE) if conversion else MARCH.FEATURE,'object_scope':'GM observed hit and pre-DR damage; native creature effects remain native'}


def receipt_policy(e,row):
    if row.get('conversion') is not None:
        _validate_conversion(e,row['intent']['actor_id'],row['conversion'],row['round'])
        return converted_policy(e,row['move_id'],row['conversion'])
    return json.loads((Path(e.r.root)/OBJECTS.POLICY).read_text(encoding='utf-8'))['moves'].get(row['move_id'])


def _selected(e,c,move_id,range_source):
    if range_source is None:
        requested,move,mm,policy=OBJECTS._move(e,c,move_id)
        if not is_pass(move):raise ValueError('actual selected Pass Move required')
        return requested,move,mm,policy,None
    import conquerors_march as MARCH
    import move_state as MOVES
    if range_source not in (MARCH.FEATURE,'feat/스탯-메뉴버','feat/열광'):raise ValueError('reviewed actual range conversion source required')
    requested=e.r.move_id(move_id)
    if requested is None or requested not in MOVES.known(e.r,{'moves':MOVES.owned_list(c.spec,'moves',c.moves)}):
        raise ValueError('actual learned or granted Move required for Conqueror Pass')
    mid=e._ruleset_move(c,requested)
    if mid is None:raise ValueError('selected Conqueror Move unavailable')
    if range_source=='feat/열광':
        proof=__import__('tumbler').pass_proof(e,c);policy=converted_policy(e,mid,proof)
    elif range_source=='feat/스탯-메뉴버':
        import stat_ace as STAT
        scope=STAT.scope(e,c,e.r.move(mid))
        if scope is None or scope['proof']['branch']!='atk':raise ValueError('actual paid Stat Maneuver Pass scope required')
        proof=scope['proof'];policy=converted_policy(e,mid,proof)
    else:
        policy=converted_policy(e,mid);proof=MARCH.conversion(e,c,policy['definition'])
    return requested,policy['definition'],policy['mechanics'],policy,proof


def _validate_conversion(e,actor_id,proof,round_no):
    if proof.get('source')=='feat/열광':return __import__('tumbler').validate_pass(e,actor_id,proof,round_no)
    if proof.get('source')=='feat/스탯-메뉴버':
        import stat_ace as STAT
        return STAT.conversion_proof(e,actor_id,proof,round_no)
    import conquerors_march as MARCH
    return MARCH.validate_conversion(e,actor_id,proof,round_no)


def movement_authority(e,actor,scope,path,mode):
    require_scope(e,actor,scope)
    if (not scope.get('paid') or mode!='land' or list(path)!=[scope.get('next_cell')]):
        raise ValueError('Pass movement must follow its paid actual next cell')
    return tuple(c for c in e.everyone if c is not actor and c.side!=actor.side)


def activation_authority(e,actor,move_id,targets,scope):
    require_scope(e,actor,scope)
    if not scope.get('paid') or scope['move_id']!=move_id or tuple(targets)!=scope['creatures']:
        raise ValueError('Pass activation target set or paid Move changed')


def require_native_target(e,actor,target,move_id):
    if not is_pass(e.r.move(move_id)) and not converted_scope(e,actor,move_id):return
    scope=getattr(e,'_pass_move_scope',None)
    if scope is None:raise ValueError('Pass Move requires use_pass_move and an actual complete path')
    require_scope(e,actor,scope)
    if not scope.get('paid') or scope['move_id']!=move_id or scope.get('current_target') is not target:
        raise ValueError('Pass native target is not the actual traversed recipient')


def native_transaction(e,actor,target):
    """Only the current paid recipient belongs to the enclosing Pass transaction."""
    scope=getattr(e,'_pass_move_scope',None)
    if scope is None or scope['actor'] is not actor:return False
    require_scope(e,actor,scope)
    if not scope.get('paid') or scope.get('current_target') is not target or target not in scope['creatures']:
        raise ValueError('native reaction is not the current paid Pass recipient')
    return True


def prepaid_move(e,actor,target,move_id):
    """The enclosing transaction pays only its selected Move, not another one."""
    scope=getattr(e,'_pass_move_scope',None)
    if scope is None or scope['move_id']!=move_id:return False
    return native_transaction(e,actor,target)


def transient_overlap(e,left,right):
    """Known co-location only at the current paid Pass recipient's actual cell."""
    scope=getattr(e,'_pass_move_scope',None)
    if scope is None or scope.get('current_target') not in (left,right):return False
    actor=scope['actor'];target=scope['current_target']
    import control_mount as MOUNT
    other=right if left is target else left
    if other not in MOUNT.travel_group(e,actor):return False
    native_transaction(e,actor,target)
    if actor.pos!=scope.get('next_cell') or actor.pos not in scope['path']:
        raise ValueError('Pass overlap requires its actual current traversed cell')
    return True


def object_authority(e,actor,uid,move_id,scope):
    require_scope(e,actor,scope)
    if not scope.get('paid') or scope['move_id']!=move_id or scope.get('current_object')!=uid:
        raise ValueError('Pass object is not the actual traversed recipient')


def _path(grid,origin,destination):
    destination=MOVEMENT._point(destination)
    dx=destination[0]-origin[0];dy=destination[1]-origin[1]
    if (dx==dy==0 or (dx and dy and abs(dx)!=abs(dy))):
        raise ValueError('Pass requires a nonempty cardinal or diagonal straight path')
    direction=((dx>0)-(dx<0),(dy>0)-(dy<0))
    return [(origin[0]+i*direction[0],origin[1]+i*direction[1])
            for i in range(1,max(abs(dx),abs(dy))+1)]


def _plan(e,c,destination,adjudications):
    import map_terrain as TERRAIN
    if e.grid is None:raise ValueError('Pass requires actual mapped cells')
    if c.spec.get('_movement_altitude',0) or c.spec.get('_burrow',{}).get('underground'):
        raise ValueError('Pass altitude/tunnel composition needs its actual movement adapter')
    path=_path(e.grid,c.pos,destination)
    if len(path)>4:raise ValueError('Pass exceeds four metres')
    # Endpoint occupancy is checked without the transient enemy overlap grant.
    if not BODY.can_place(e,c,path[-1]):raise ValueError('Pass must end in an empty cell')
    ignored=[a for a in e.everyone if a is not c and a.side!=c.side]
    import control_mount as MOUNT
    context=MOUNT.shared_movement(e,c)[2] if MOUNT.manages(e,c) else None
    origin=c.pos;diagonals=context['diagonals'] if context is not None else getattr(c,'_diagonal_steps',0);distance=0
    cells=[]
    for q in path:
        if not TERRAIN.can_travel(e,c,q,'land') or not BODY.can_place(e,c,q,origin=origin,ignore_actors=ignored):
            raise ValueError('Pass straight path is blocked')
        step,diagonals=MOVEMENT.step_cost(origin,q,diagonals)
        distance+=step+MOVEMENT.slow_terrain_penalty(e,c,q,'land',step=step)
        cells.append(BODY.at_position(c,q));origin=q
    if distance>min(4,context['remaining'] if context is not None else MOVEMENT.distance_budget(e,c,'land')):
        raise ValueError('Pass exceeds four metres or actual movement allowance')
    steps=[[] for _ in path];seen=set()
    for a in e.everyone:
        if a in MOUNT.travel_group(e,c) or a.fainted or a.captured or not a.on_field:continue
        if a.spec.get('_movement_altitude',0) or a.spec.get('_burrow',{}).get('underground'):continue
        for i,swept in enumerate(cells):
            if BODY.at_position(a).intersection(swept):
                if a.entity_id not in seen:steps[i].append(('creature',a.entity_id));seen.add(a.entity_id)
                break
    object_ids=[]
    actor_location=WORLD.location_of(c)
    for uid,obj in getattr(e,'_physical_objects',{}).items():
        if WORLD.physical_lifecycle(obj)['destroyed'] or WORLD.physical_lifecycle(obj)['consumed']:continue
        loc=WORLD.effective_location(e,obj)
        if loc['kind']!='grid' or loc.get('map_id')!=actor_location.get('map_id'):continue
        for i,swept in enumerate(cells):
            if tuple(loc['cell']) in swept:
                OBJECTS._object(e,uid);WORLD.require_usable_object(obj)
                if OBJECTS.FIELD not in obj:raise ValueError('every traversed object needs actual durability facts')
                if any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):
                    raise ValueError('Pass held object requires its holder/exposure adapter')
                steps[i].append(('object',uid));object_ids.append(uid);break
    if type(adjudications) is not dict or set(adjudications)!=set(object_ids):
        raise ValueError('adjudicate every actual traversed object exactly once; no omitted or extra targets')
    for row in adjudications.values():
        if type(row) is not dict or set(row)!={'hit','damage_before_dr'}:
            raise ValueError('physical Pass adjudication requires hit and pre-DR damage')
        OBJECTS._integer(row['damage_before_dr'],'adjudicated pre-DR damage')
        if type(row['hit']) is not bool or not row['hit'] and row['damage_before_dr']:
            raise ValueError('a physical Pass miss must have zero damage')
    # A dropped object also occupies the endpoint for this actual activation.
    if any(kind=='object' for kind,uid in steps[-1]):raise ValueError('Pass must end in an empty cell')
    index=WORLD.actor_index(e)
    creatures=tuple(index[uid] for step in steps for kind,uid in step if kind=='creature')
    return dict(path=path,distance=distance,steps=steps,creatures=creatures,mount_context=context)


@contextmanager
def _scope(e,c,mid,event_id,plan,conversion):
    if hasattr(e,'_pass_move_scope'):raise ValueError('nested Pass activation needs a source policy')
    scope=dict(actor=c,move_id=mid,event_id=event_id,round=e.round_no,creatures=plan['creatures'],path=plan['path'],paid=False,conversion=conversion)
    e._pass_move_scope=scope
    try:yield scope
    finally:del e._pass_move_scope


def use(e,c,move_id,destination,*,event_id,object_adjudications,source,reason,range_source=None):
    WORLD.require_actors(e,c)
    OBJECTS._text(event_id,'Pass event identity');OBJECTS._text(source,'Pass adjudication source');OBJECTS._text(reason,'Pass reason')
    destination=MOVEMENT._point(destination)
    intent=dict(actor_id=c.entity_id,requested_move_id=move_id,destination=list(destination),
                object_adjudications=deepcopy(object_adjudications),source=source,reason=reason)
    if range_source is not None:intent['range_source']=range_source
    OBJECTS.validate_world(e);validate_world(e)
    old=getattr(e,KEY,{}).get(event_id)
    if old is not None:
        if old['intent']!=intent:raise ValueError('Pass event identity conflicts with its previous intent')
        if old.get('phase')=='pending':
            import passive_events as PASSIVE
            raise PASSIVE.PassiveEventPending(e._passive_pending)
        return deepcopy(old)
    requested,move,mm,policy,conversion=_selected(e,c,move_id,range_source)
    __import__('native_path_area_moves').roller_preflight(e,move['id'])
    plan=_plan(e,c,destination,object_adjudications)
    import forced_move_lock as FORCED
    if FORCED.current(e,c)==move['id'] and not plan['creatures']:
        FORCED.clear(e,c,move['id'],reason='no_target')
        return 0
    if not FORCED.preflight_choice(e,c,move['id'],plan['creatures'],ordinary=True):return 0
    MOVEMENT.boundary(e,'Pass')

    def apply(staged,actor):
        plan=_plan(staged,actor,destination,object_adjudications)
        import control_mount as MOUNT
        mount_policy=None
        if plan['mount_context'] is not None:
            donor,mount_policy,context=MOUNT.shared_movement(staged,actor)
            if donor is not actor:raise ValueError('Pass requires its actual mounted movement donor')
            actor._diagonal_steps=context['diagonals']
        origin=actor.pos;before_diagonals=getattr(actor,'_diagonal_steps',0)
        with _scope(staged,actor,move['id'],event_id,plan,conversion) as scope:
            physical=[uid for step in plan['steps'] for target_kind,uid in step if target_kind=='object']
            if physical:
                kind=OBJECTS._permission(staged,actor,OBJECTS._object(staged,physical[0]),move,mm,pass_scope=scope)
            else:
                target=plan['creatures'][0] if plan['creatures'] else None
                kind=ACTIVATION.paid_move_permission(staged,actor,target,move,mm)
            if not TURN.movement_permission(staged,actor):raise ValueError('Pass movement unavailable')
            if not TURN.spend(staged,actor,kind,move['name'],_native_move=move):raise ValueError('Pass Move action unavailable')
            if not TURN.spend(staged,actor,'shift','통과 이동',movement=True):raise ValueError('Pass movement action unavailable')
            FREQ.consume_move(staged,actor,move['id'],outside_combat=False)
            actor.last_move=move['id'];actor.last_target=None;scope['paid']=True
            import conditional_damage_base as CONDITIONAL
            CONDITIONAL.begin_pass(staged,actor,move,scope)
            import confusion_attacks as CONFUSION
            scope['confusion']=CONFUSION.begin_native(staged,actor,move,producer='pass',event_id=event_id)
            row=dict(event_id=event_id,intent=intent,move_id=move['id'],definition_hash=OBJECTS._hash(policy),
                     origin=origin,path=plan['path'],distance=plan['distance'],diagonals_before=before_diagonals,
                     targets=[list(pair) for step in plan['steps'] for pair in step],results=[],
                     round=staged.round_no,at=staged.elapsed_seconds,source=SOURCE,completion_id=None)
            if conversion is not None:row['conversion']=deepcopy(conversion)
            scope.update(receipt=row,steps=plan['steps'],cell_index=0,target_index=0,
                         entered=False,travelled=0,diagonals=before_diagonals,
                         kind=kind,mount_policy=mount_policy)
            creatures=plan['creatures']
            context=(ACTIVATION.open_scope(staged,actor,move['id'],creatures,shared=False,
                         primary=creatures[0],_prepaid=scope) if creatures else nullcontext((None,None)))
            import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
            try:
                with ACTION.resolution(staged,actor,move['id'],kind='move'):
                    with context as (activation,accuracy):
                        interrupted=_advance(staged,scope,activation,accuracy)
                        if creatures:
                            live=next(s for s in staged._move_activation_scopes if s['activation'] is activation)
                            row['completion_id']=live.get('completion_id')
                            if interrupted:live['interrupted']=True
                return _finish(staged,scope,interrupted=interrupted)
            except PASSIVE.PassiveEventPending as pending:
                saved=_saved(staged,event_id)
                if saved is None or staged._passive_pending!=pending.event_id:
                    raise ValueError('Pass pending lacks an executable native recipient continuation; the entire activation was rolled back') from None
                return ('pass_pending',pending.event_id)
            except HEAVY.HeavyPending:
                raise ValueError('Pass Heavy continuation is not executable; activation boundary rolled back') from None
    result=GRANTS.transition(e,c,apply,include_grid=True,include_rulings=True)
    if type(result) is tuple and result[0]=='pass_pending':
        import passive_events as PASSIVE
        raise PASSIVE.PassiveEventPending(result[1])
    return result


def _saved(e,event_id):
    return next((row['activation_continuation'] for row in getattr(e,'_move_completions',{}).values()
        if row.get('activation_continuation',{}).get('scope',{}).get('prepaid_pass',{}).get('event_id')==event_id),None)


def _store(e,scope,phase):
    row=scope['receipt'];row['phase']=phase
    row['travelled']=scope['travelled'];row['position']=scope['actor'].pos
    row['diagonals_after']=scope['diagonals']
    row['receipt_hash']=OBJECTS._hash({k:v for k,v in row.items() if k!='receipt_hash'})
    if not hasattr(e,KEY):setattr(e,KEY,{})
    getattr(e,KEY)[scope['event_id']]=row


def suspend(e,activation):
    scope=activation['prepaid_pass']
    scope['receipt']['completion_id']=activation['completion_id']
    if scope['confusion'] is not None:scope['receipt']['confusion']=scope['confusion']
    _store(e,scope,'pending')


def _record_creature(e,scope,target,dealt,*,cancelled=False):
    if type(dealt) is not int or dealt<0:raise ValueError('Pass recipient needs an actual native return')
    result=dict(kind='creature',id=target.entity_id,dealt=dealt)
    if cancelled:result['cancelled']=True
    scope['receipt']['results'].append(result)
    scope.pop('current_target',None);scope['target_index']+=1


def _advance(e,scope,activation,accuracy):
    actor=scope['actor'];move=e.r.move(scope['move_id']);row=scope['receipt']
    policy=receipt_policy(e,row);intent=row['intent']
    import control_mount as MOUNT
    while scope['cell_index']<len(scope['path']):
        q=scope['path'][scope['cell_index']];scope['next_cell']=q
        if not scope['entered']:
            progress={}
            travelled=MOVEMENT.follow_paid_path(e,actor,[q],mode='land',
                maximum_distance=4-scope['travelled'],progress=progress,pass_scope=scope)
            if travelled['steps']!=1 or progress['phase']!='complete':
                raise ValueError('Pass movement interrupted; actual movement continuation required')
            scope['travelled']+=travelled['distance'];scope['diagonals']=actor._diagonal_steps
            if scope['mount_policy'] is not None:
                MOUNT.record_movement(e,actor,scope['mount_policy'],distance=travelled['distance'],diagonals=actor._diagonal_steps)
            scope['entered']=True
        targets=scope['steps'][scope['cell_index']]
        while scope['target_index']<len(targets):
            target_kind,uid=targets[scope['target_index']]
            if target_kind=='object':
                scope['current_object']=uid
                obj_intent=dict(actor_id=actor.entity_id,object_id=uid,requested_move_id=intent['requested_move_id'],
                    **intent['object_adjudications'][uid],source=intent['source'],reason=intent['reason'])
                child_id=scope['event_id']+'/object/'+uid
                if any(r['event_id']==child_id for o in getattr(e,'_physical_objects',{}).values()
                       for r in o.get(OBJECTS.FIELD,{}).get('attacks',[])):
                    raise ValueError('Pass physical child event identity already used')
                receipt=OBJECTS.pass_recipient(e,actor,uid,move,policy,scope=scope,
                    event_id=child_id,intent=obj_intent,kind=scope['kind'])
                scope.pop('current_object')
                row['results'].append(dict(kind='object',id=uid,event_id=child_id,dealt=receipt['applied_damage']))
                scope['target_index']+=1
            else:
                target=WORLD.actor_index(e)[uid];scope['current_target']=target
                with ACTION.move_grant(e,actor,target,move['id'],source='same_move_activation') as grant:
                    dealt=e.use_move(actor,target,move['id'],count_use=False,
                        _activation=activation,_shared_accuracy=accuracy,_action_grant=grant)
                ACTIVATION.note_result(e,activation,dealt)
                _record_creature(e,scope,target,dealt)
                if actor.fainted or actor.dead:return True
        scope['cell_index']+=1;scope['target_index']=0;scope['entered']=False
    return False


def _finish(e,scope,*,interrupted=False):
    actor=scope['actor'];row=scope['receipt'];move=e.r.move(scope['move_id'])
    if not interrupted:
        if not BODY.can_place(e,actor,tuple(row['intent']['destination'])):raise ValueError('Pass endpoint no longer empty')
        if actor.pos!=tuple(row['intent']['destination']):raise ValueError('Pass must stop at its actual destination')
        if scope['creatures']:
            import conditional_damage_base as CONDITIONAL
            CONDITIONAL.finish_pass(e,actor,move,scope,row['completion_id'])
    else:
        row['interruption']='native_attacker_ineligible'
        row['actor_at_interruption']={'fainted':actor.fainted,'dead':actor.dead}
        import forced_move_lock as FORCED
        FORCED.clear(e,actor,move['id'],reason='incapacitated')
    MOVEMENT.consume_sprint(actor)
    if scope['confusion'] is not None:
        import confusion_attacks as CONFUSION
        row['confusion']=CONFUSION.finish_native(e,actor,move,scope['confusion'],
            producer='pass',event_id=scope['event_id'],
            cancelled=interrupted and not any(not result.get('cancelled') for result in row['results']))
    _store(e,scope,'interrupted' if interrupted else 'complete')
    OBJECTS.validate_world(e);validate_world(e)
    return deepcopy(row)


def resume(e,activation,event,result):
    scope=activation['prepaid_pass'];_require_owner(e,scope['actor'],scope)
    completion=e._move_completions[activation['completion_id']]
    cancelled=completion['results'][event['target'].entity_id]['cancelled']
    _record_creature(e,scope,event['target'],result,cancelled=cancelled)
    import move_completion as COMPLETE
    if cancelled or scope['actor'].fainted or scope['actor'].dead:
        COMPLETE.seal(e,activation,interrupted=True)
        return _finish(e,scope,interrupted=True)
    require_scope(e,scope['actor'],scope)
    interrupted=_advance(e,scope,activation['activation'],activation['accuracy'])
    COMPLETE.seal(e,activation,interrupted=interrupted)
    return _finish(e,scope,interrupted=interrupted)


@contextmanager
def restored_scope(e,event):
    while event.get('defense_parent'):event=e._passive_events[event['defense_parent']]
    completion=getattr(e,'_move_completions',{}).get(event.get('completion_id'),{})
    saved=completion.get('activation_continuation')
    scope=None if saved is None else saved['scope'].get('prepaid_pass')
    if scope is None or getattr(e,'_pass_move_scope',None) is scope:
        yield;return
    if hasattr(e,'_pass_move_scope'):raise ValueError('nested Pass continuation requires its actual parent')
    if saved['fingerprint']!=ACTIVATION.R.fingerprint(ACTIVATION._continuation_facts(saved['scope'],saved['event_id'])):
        raise ValueError('native target group changed during wait')
    actor=scope['actor']
    if actor.pos!=tuple(scope['receipt']['position']) or getattr(actor,'_diagonal_steps',0)!=scope['diagonals']:
        raise ValueError('Pass current position or diagonal boundary changed during wait')
    e._pass_move_scope=scope
    try:
        if actor.fainted or actor.dead:
            _require_owner(e,actor,scope)
            if scope.get('conversion') is not None:
                _validate_conversion(e,actor.entity_id,scope['conversion'],scope['round'])
        else:require_scope(e,actor,scope)
        yield
    except Exception as error:
        import heavy_injury_adapter as HEAVY,passive_events as PASSIVE
        if type(error) is PASSIVE.PassiveEventPending:
            pending=e._passive_events.get(error.event_id)
            while pending is not None and pending.get('defense_parent'):pending=e._passive_events[pending['defense_parent']]
            if pending is None or not pending.get('continuation'):
                raise ValueError('Pass pending lacks an executable native recipient continuation; resumed boundary rolled back') from None
        if type(error) is HEAVY.HeavyPending:
            raise ValueError('Pass Heavy continuation is not executable; resumed boundary rolled back') from None
        raise
    finally:del e._pass_move_scope



def validate_object_receipt(e,uid,receipt):
    row=getattr(e,KEY,{}).get(receipt.get('pass_event'))
    if (row is None or receipt['intent']['actor_id']!=row['intent']['actor_id'] or receipt['move_id']!=row['move_id']
            or not any(r['kind']=='object' and r['id']==uid and r['event_id']==receipt['event_id']
                       and r['dealt']==receipt['applied_damage'] for r in row['results'])):
        raise ValueError('Pass physical recipient lost its complete paid path receipt')
    intent=receipt['intent'];parent=row['intent']
    expected=dict(actor_id=parent['actor_id'],object_id=uid,requested_move_id=parent['requested_move_id'],
                  **parent['object_adjudications'][uid],source=parent['source'],reason=parent['reason'])
    if intent!=expected:raise ValueError('Pass physical adjudication changed from its actual declaration')


def validate_world(e,index=None):
    index=WORLD.actor_index(e) if index is None else index
    for key,row in getattr(e,KEY,{}).items():
        if row.get('receipt_hash')!=OBJECTS._hash({k:v for k,v in row.items() if k!='receipt_hash'}):
            raise ValueError('Pass receipt changed')
        if row['event_id']!=key or row['intent']['actor_id'] not in index or row['source']!=SOURCE:
            raise ValueError('Pass producer identity/source changed')
        phase=row.get('phase','complete')
        if phase not in ('pending','complete','interrupted'):raise ValueError('unknown Pass lifecycle phase')
        __import__('native_path_area_moves').validate_roller(e,row)
        policy=receipt_policy(e,row)
        if (policy is None or e.r.move(row['move_id'])!=policy['definition']
                or e.r.move_mech(row['move_id'])[0]!=policy['mechanics']
                or OBJECTS._hash(policy)!=row['definition_hash']):
            raise ValueError('Pass selected definition changed')
        if 'confusion' in row:
            import confusion_attacks as CONFUSION
            if phase=='pending':
                context=CONFUSION._native_context(index[row['intent']['actor_id']],policy['definition'],'pass',key)
                context[CONFUSION.FIELD]=row['confusion'];CONFUSION._validate_observation(context)
                if row['confusion']['result'] is not None:raise ValueError('pending Pass cannot finish Confusion')
            else:
                CONFUSION.validate_native(index[row['intent']['actor_id']],policy['definition'],row['confusion'],
                    producer='pass',event_id=key)
        path=_path(e.grid,tuple(row['origin']),tuple(row['intent']['destination']))
        if path!=[tuple(q) for q in row['path']] or len(path)>4:raise ValueError('Pass actual straight path changed')
        if not 0<row['distance']<=4:raise ValueError('Pass actual distance changed')
        actual=[[r['kind'],r['id']] for r in row['results']]
        expected=row['targets'] if phase=='complete' else row['targets'][:len(actual)]
        if expected!=actual or len({tuple(t) for t in row['targets']})!=len(row['targets']):
            raise ValueError('Pass recipients must be ordered and distinct')
        for result in row['results']:
            if result['kind']=='object':
                obj=getattr(e,'_physical_objects',{}).get(result['id'])
                attacks=[] if obj is None else obj.get(OBJECTS.FIELD,{}).get('attacks',[])
                matches=[r for r in attacks if r['event_id']==result['event_id']]
                if len(matches)!=1:raise ValueError('Pass actual physical recipient missing')
                validate_object_receipt(e,result['id'],matches[0])
            elif result['kind']!='creature' or result['id'] not in index:raise ValueError('Pass actual creature missing')
        creatures=[uid for kind,uid in row['targets'] if kind=='creature']
        if set(row['intent']['object_adjudications'])!={uid for kind,uid in row['targets'] if kind=='object'}:
            raise ValueError('Pass physical adjudications lost actual recipients')
        completion=getattr(e,'_move_completions',{}).get(row['completion_id'])
        if creatures:
            if 'confusion' in row and (completion is None or 'confusion' in completion
                    or completion.get('confusion_parent')!={'producer':'pass','event_id':key}):
                raise ValueError('Pass native targets require their one parent Confusion observation')
            if (completion is None or completion['phase']!=('targets' if phase=='pending' else phase) or completion['move_id']!=row['move_id']
                    or completion['actor'] is not index[row['intent']['actor_id']]
                    or [t.entity_id for t in completion['targets']]!=creatures):
                raise ValueError('Pass requires the actual complete native creature activation')
            for result in row['results']:
                if result['kind']=='creature' and (result['id'] not in completion['started']
                        or completion['results'][result['id']]['cancelled']!=result.get('cancelled',False)
                        or result['dealt']!=completion['results'][result['id']]['dealt']):
                    raise ValueError('Pass requires each actual native creature attack return')
        elif row['completion_id'] is not None:raise ValueError('Pass completion without creature recipients')
        if phase=='pending':
            saved=None if completion is None else completion.get('activation_continuation')
            scope=None if saved is None else saved['scope'].get('prepaid_pass')
            if (scope is None or scope.get('receipt') is not row or scope['event_id']!=key
                    or scope['actor'] is not completion['actor'] or scope['move_id']!=row['move_id']
                    or scope['path']!=row['path'] or not scope['entered']
                    or not 0<=scope['cell_index']<len(scope['path'])
                    or saved['fingerprint']!=ACTIVATION.R.fingerprint(ACTIVATION._continuation_facts(saved['scope'],saved['event_id']))):
                raise ValueError('pending Pass lacks its authenticated actual path continuation')
            ordered=[list(pair) for step in scope['steps'] for pair in step]
            prefix=[list(pair) for step in scope['steps'][:scope['cell_index']] for pair in step]
            prefix.extend(list(pair) for pair in scope['steps'][scope['cell_index']][:scope['target_index']])
            current=scope['steps'][scope['cell_index']][scope['target_index']]
            if (ordered!=row['targets'] or prefix!=actual or current!=('creature',scope['current_target'].entity_id)
                    or scope['current_target'] is not e._passive_events[saved['event_id']]['target']
                    or tuple(row['position'])!=tuple(scope['path'][scope['cell_index']])
                    or scope['travelled']!=row['travelled'] or scope['diagonals']!=row['diagonals_after']):
                raise ValueError('pending Pass lost its actual ordered path prefix')
        elif phase=='interrupted':
            if (row.get('interruption')!='native_attacker_ineligible' or completion is None
                    or not completion['sealed'] or completion.get('activation_continuation')
                    or not row['results'] or not any(row.get('actor_at_interruption',{}).values())):
                raise ValueError('interrupted Pass requires its native cancelled recipient')

    # A surviving native child must also point back to its actual whole Pass.
    # Otherwise deleting the parent could silently discard the only draw.
    for completion in getattr(e,'_move_completions',{}).values():
        link=completion.get('confusion_parent')
        if link is None:continue
        parent=getattr(e,KEY,{}).get(link.get('event_id')) if type(link) is dict else None
        if not parent or link!={'producer':'pass','event_id':parent['event_id']}:
            raise ValueError('native Confusion child lost its actual Pass parent')
        if 'confusion' not in parent or parent['completion_id']!=completion['id'] or 'confusion' in completion:
            raise ValueError('native Confusion child must use the one parent draw')
    return True
