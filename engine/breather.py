"""Native Take a Breather producer; unprinted table decisions remain explicit.

The selected prose gives no universal saving DC or failed-save cost. Those are
table adjudications, not invented rule constants. Mapped retreat uses an observed
route: its maximality is a GM world observation, not an attack flag.
"""
from copy import copy,deepcopy
from contextlib import contextmanager
import common_checks as C
import skill_modifiers as SKILL_RANKS
import action_lifecycle as ACTION
import movement_actions as MOVEMENT
import observed_resolution as OBS
import turn as TURN
import world_entities as W

SOURCE='ch07-combat/전투의-다른-행동/숨돌리기'
SOURCE_REF={'file':'input/ch07-combat.md','sha256':'57abb79c4f70c64246cd7927bffe2377e951bdc32dfa4c9a5c14b4ad97618c18'}
FIELD='_breather_attempts'
STAYING='feat/지구력'
CLASS='class/불굴의-투지'
SHRUG='feat/떨쳐버리기'
VIM='feat/생기활발'
NOT_YET='feat/아직이야'
FEATURES=(STAYING,SHRUG,VIM,NOT_YET,CLASS)
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'

def feature_source(rules,feature,edition):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('core','local_csv'):
        raise ValueError('reviewed Enduring Soul feature source required')
    if edition=='core':
        import trainer_feature_acquisition as T
        return dict(T._static_source(rules,feature),edition=edition)
    record={CLASS:125,STAYING:126,SHRUG:127,VIM:131,NOT_YET:130}[feature]
    source={'file':'input/db/feats.csv','sha256':CSV_SHA,'record_span':[record,record]}
    verified_source(rules,source,label='Enduring Soul CSV')
    clause='C2CSV/input/db/feats.csv:R'+str(record)+':main'
    rules.ruleset.require({'id':clause,'source':{'file':'db/feats.csv','record_span':[record,record]}})
    return dict(source,clause_id=clause,edition=edition)

def feature_snapshot(engine,actor,feature,selection):
    import acquired_features as A,trainer_feature_acquisition as T
    if selection is not None and (type(selection)is not dict or set(selection)!={'edition'}):
        raise ValueError('one immutable Enduring Soul feature source selection required')
    if feature==CLASS:
        import skill_modifiers as S
        return {'selection':deepcopy(selection),'source':feature_source(engine.r,feature,'core' if selection is None else selection['edition']),
            'class_ranks':[S.effective_rank(engine.r,actor,skill) for skill in ('육상','집중')]}
    if feature==STAYING and selection is None:
        return {'enduring_soul':bool(A.owned_rule_count(actor,'class/불굴의-투지'))}
    parent=SHRUG if feature==VIM else STAYING if feature==SHRUG else None
    parents=[r for _,r in T.static_acquisitions(actor,parent,active=True)] if parent is not None else []
    result={'selection':deepcopy(selection),'source':feature_source(engine.r,feature,'core' if selection is None else selection['edition']),
        'enduring_soul':bool(A.owned_rule_count(actor,'class/불굴의-투지')),
        'parent_request':parents[0]['request_id'] if len(parents)==1 else None}
    if feature in (VIM,NOT_YET):
        import skill_modifiers as S
        result['class_ranks']=[S.effective_rank(engine.r,actor,skill) for skill in ('육상','집중')]
    return result

def feature_qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q,trainer_feature_acquisition as T
    if prerequisite_source is not None:raise ValueError('actual Enduring Soul feature prerequisite required')
    if feature==CLASS:
        if type(snapshot)is not dict or set(snapshot)!={'selection','source','class_ranks'}:
            raise ValueError('actual Enduring Soul class source and skill observations required')
        choice=snapshot['selection'];ranks=snapshot['class_ranks']
        if choice is not None and (type(choice)is not dict or set(choice)!={'edition'}):raise ValueError('one immutable class source required')
        if snapshot['source']!=feature_source(actor.r,feature,'core' if choice is None else choice['edition']):raise ValueError('Enduring Soul class source changed')
        if type(ranks)is not list or len(ranks)!=2:raise ValueError('actual class skill ranks required')
        for value in ranks:SKILL_RANKS.validate_rank_value(actor.r,value,kind='effective',label='class skill rank')
        return Q.require(feature,'native','acquire',[
            Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
            Q.check('skills','prerequisite',min(ranks)>=3,'Novice Athletics and Focus required')])
    if feature==STAYING and type(snapshot)is dict and set(snapshot)=={'enduring_soul'}:
        qualified=snapshot=={'enduring_soul':True}
    else:
        if type(snapshot)is not dict or set(snapshot)!=({'selection','source','enduring_soul','parent_request'}|({'class_ranks'} if feature in (VIM,NOT_YET) else set())):
            raise ValueError('immutable Enduring Soul feature acquisition observations required')
        choice=snapshot['selection']
        if choice is not None and (type(choice)is not dict or set(choice)!={'edition'}):
            raise ValueError('one immutable Enduring Soul feature source selection required')
        if snapshot['source']!=feature_source(actor.r,feature,'core' if choice is None else choice['edition']):
            raise ValueError('Enduring Soul feature acquisition source changed')
        if type(snapshot['enduring_soul'])is not bool:raise ValueError('actual Enduring Soul prerequisite observation required')
        qualified=snapshot['enduring_soul']
        if feature in (SHRUG,VIM):
            parent=SHRUG if feature==VIM else STAYING
            qualified=qualified and len([r for _,r in T.static_acquisitions(actor,parent)
                if r['request_id']==snapshot['parent_request']])==1
        elif snapshot['parent_request'] is not None:raise ValueError('Staying Power has no Staying Power parent')
    checks=[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('parent','prerequisite',qualified,'actual Enduring Soul / Staying Power prerequisite required')]
    if feature in (VIM,NOT_YET):
        ranks=snapshot['class_ranks'];minimum=6 if feature==VIM else 5
        if type(ranks)is not list or len(ranks)!=2:
            raise ValueError('actual acquisition-time class skill ranks required')
        for value in ranks:SKILL_RANKS.validate_rank_value(actor.r,value,kind='effective',label='acquisition-time class skill rank')
        checks.append(Q.check('skill','prerequisite',max(ranks)>=minimum,('Master' if feature==VIM else 'Expert')+' Athletics or Focus required'))
    return Q.require(feature,'native','acquire',checks)

def feature_receipt(engine,owner,feature):
    import trainer_feature_acquisition as T
    T.validate_actor(owner)
    rows=[r for _,r in T.static_acquisitions(owner,feature,active=True)]
    if owner.kind!='trainer' or len(rows)!=1:raise ValueError('actual acquired '+feature+' receipt required')
    source=rows[0]['snapshot'].get('source')
    if source is not None and source!=feature_source(engine.r,feature,source['edition']):
        raise ValueError('Enduring Soul feature current source changed')
    return rows[0]

def feature_edition(engine,owner,feature):
    return feature_receipt(engine,owner,feature)['snapshot'].get('source',{}).get('edition','core')


def class_edition(owner):
    """Legacy class instances keep their accepted CSV contribution, never infer a Book choice."""
    import trainer_feature_acquisition as T
    rows=T.static_acquisitions(owner,CLASS,active=True)
    return rows[0][1]['snapshot']['source']['edition'] if len(rows)==1 else 'local_csv'

def staying_owner(engine,actor,choice):
    if type(choice)is not dict or set(choice) not in ({'trainer_id','reset_stages'},{'trainer_id','reset_stages','clear_temp_hp'}) or type(choice['reset_stages'])is not bool:
        raise ValueError('Staying Power needs actual owner and explicit combat-stage reset choice')
    owner=W.actor_index(engine).get(choice['trainer_id'])
    if actor.kind!='pokemon' or owner is None or actor.spec.get('trainer_id')!=owner.entity_id:
        raise ValueError('Staying Power affects only the actual owner Pokemon taking a Breather')
    feature_receipt(engine,owner,STAYING)
    csv=feature_edition(engine,owner,STAYING)=='local_csv'
    if ('clear_temp_hp' in choice)!=csv or (csv and type(choice['clear_temp_hp'])is not bool):
        raise ValueError('CSV Staying Power requires an explicit temporary-HP clear choice; Book has no such choice')
    return owner

def staying_permission(engine,actor,kind):
    scope=getattr(engine,'_breather_staying_scope',None)
    return bool(kind in ('full','swift') and scope is not None and scope['actor'] is actor and staying_owner(engine,actor,scope['choice']))

def shrug_owner(engine,actor,choice):
    if type(choice)is not dict or set(choice)!={'trainer_id','heal_injury'} or type(choice['heal_injury'])is not bool:
        raise ValueError('Shrug Off needs actual owner and explicit Injury-heal choice')
    owner=W.actor_index(engine).get(choice['trainer_id'])
    if actor.kind!='pokemon' or owner is None or actor.spec.get('trainer_id')!=owner.entity_id:
        raise ValueError('Shrug Off affects only the actual owner Pokemon')
    feature_receipt(engine,owner,SHRUG)
    if feature_edition(engine,owner,SHRUG)=='core' and not choice['heal_injury']:
        raise ValueError('Book Shrug Off activates to remove an Injury')
    return owner

def _shrug_quota(engine,actor):
    import frequency as F
    if not F.activation_allowed(actor,SHRUG,{'kind':'daily','uses':1},engine=engine):
        raise ValueError('Shrug Off daily use exhausted for this Pokemon')

def _shrug_heal(engine,actor,choice,*,consume=True):
    import frequency as F,injury_recovery as I
    shrug_owner(engine,actor,choice)
    if consume:
        _shrug_quota(engine,actor)
        F.consume_activation(actor,SHRUG,{'kind':'daily','uses':1},engine=engine)
    return I.heal(engine,actor,1,source=SHRUG) if choice['heal_injury'] else 0

def shrug_off(engine,actor,*,request_id,trainer_id):
    """Book's independent Shift action; CSV replaces a Breather instead."""
    import state_grants as G
    W.require_actors(engine,actor);_text(request_id,'Shrug Off request identity')
    choice={'trainer_id':trainer_id,'heal_injury':True}
    declaration={'actor':actor,'shrug_off':choice}
    records=getattr(engine,FIELD,{})
    if request_id in records:
        old=records[request_id][OBS.KEY];OBS.verify(old,declaration)
        return old['result']
    owner=shrug_owner(engine,actor,choice)
    if feature_edition(engine,owner,SHRUG)!='core':raise ValueError('CSV Shrug Off is a Swift Breather, not a Shift injury heal')
    if not actor.on_field or actor.captured:raise ValueError('actual participating Pokemon required for a Shift action')
    def apply(e,a):
        _shrug_quota(e,a)
        with ACTION.resolution(e,a,SHRUG,kind='feature'):
            if not TURN.spend(e,a,'shift',SHRUG):raise ValueError('actual Shift action unavailable')
            if not hasattr(e,FIELD):setattr(e,FIELD,{})
            record=OBS.begin(getattr(e,FIELD),request_id,'shrug_off',(a,),dict(declaration,actor=a),{})
            removed=_shrug_heal(e,a,choice)
            return OBS.complete(record,{'completed':True,'source':SHRUG,'removed_injuries':removed})
    return G.transition(engine,actor,apply,include_rulings=True)

@contextmanager
def _staying_scope(engine,actor,choice):
    old=getattr(engine,'_breather_staying_scope',None)
    if choice is not None:
        staying_owner(engine,actor,choice)
        engine._breather_staying_scope={'actor':actor,'choice':deepcopy(choice)}
    try:yield
    finally:
        if old is None:vars(engine).pop('_breather_staying_scope',None)
        else:engine._breather_staying_scope=old

def selected(rules):
    from source_context import verified_source
    if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Take a Breather source required')
    verified_source(rules,SOURCE_REF,label='Take a Breather')
    if rules.selection.units[SOURCE]['source']['lines']!=[550,559]:raise ValueError('Take a Breather literal source changed')

def ensure_clear(engine,*,resume=None):
    if any(frame['source']==SOURCE for frame in getattr(engine,'_native_action_stack',())):return
    if any(row[OBS.KEY]['state']!='complete' and row[OBS.KEY] is not resume for row in getattr(engine,FIELD,{}).values()):
        raise ValueError('unfinished actual Take a Breather producer must resolve before another action')

def validate_continuation(engine,actor,source,kind,record):
    if type(record) is not dict:raise ValueError('actual interrupted Breather observation required')
    actual=any(row[OBS.KEY] is record for row in getattr(engine,FIELD,{}).values())
    participants=record.get('participants',())
    expected=participants[0] if kind=='breather' and len(participants)==1 else participants[-1] if kind=='assisted_breather' and len(participants)==2 else None
    observed=record.get('observation',{})
    family='take_a_breather' if kind=='breather' else 'assisted_breather'
    if (not actual or record.get('state')!='pending' or record.get('family')!=family or source!=SOURCE or actor is not expected
            or observed.get('phase')!='retreat' or observed.get('turn')!=_turn(engine,actor)):
        raise ValueError('actual interrupted Breather continuation requires the same producer and owner turn')

def _turn(engine,actor):
    return (actor,engine.round_no,actor.custom_conditions.get('combat_turn_serial'),engine._active_turn_actor)

def _move(engine,actor,plan,progress,reason):
    if not progress:
        first=plan['path'][0];position=first['position'] if type(first)is dict else first
        if (actor.pos!=position or actor.spec.get('_movement_altitude',0)!=plan.get('origin_altitude',actor.spec.get('_movement_altitude',0))
                or bool(actor.spec.get('_burrow',{}).get('underground'))!=plan.get('origin_underground',bool(actor.spec.get('_burrow',{}).get('underground')))):
            raise ValueError('actual Breather movement origin changed after observation')
        engine.gm._rec('숨돌리기 실제 최장 후퇴 경로',actor.pos,plan['path'],reason,actor)
    if plan.get('mode') in ('burrow','teleport'):
        result=MOVEMENT.follow_paid_transfer(engine,actor,plan,progress=progress)
    else:
        result=MOVEMENT.follow_paid_path(engine,actor,plan['path'][1:],mode=plan.get('mode','육상'),
                                        maximum_distance=plan['budget'],progress=progress)
    if result['steps']:actor._regular_shift_movement_used=True
    return result

def _finish(engine,actor,request_id,origin,*,helper=None,movement=None):
    import state_grants as G
    import effect_contracts as EFFECTS
    EFFECTS.ensure_clear(engine)
    observed=getattr(engine,FIELD)[request_id][OBS.KEY]['observation']
    cursors=[observed['progress']] if helper is None else observed['progress'].values()
    if any(ACTION.pending_resolution_effects(engine,{'effects':cursor.get('effects',[])}) for cursor in cursors):
        raise ValueError('actual retreat effects must resolve before Breather recovery')
    def recover(staged,target,*assistants):
        staged_origin=None if origin is None else W.actor_index(staged)[origin.entity_id]
        shrug=observed.get('shrug_off')
        shrug_csv=False
        if shrug is not None:
            owner=shrug_owner(staged,target,shrug)
            shrug_csv=feature_edition(staged,owner,SHRUG)=='local_csv'
            if not shrug_csv:ACTION.triggered_free_action(staged,target,SHRUG)
        _recover(staged,target,staged_origin,staying_power=observed.get('staying_power'))
        staying=observed.get('staying_power')
        if staying is not None:
            owner=staying_owner(staged,target,staying)
            if feature_edition(staged,owner,STAYING)=='local_csv':
                import skill_modifiers as SKILLS,temporary_hp as TEMP
                value=sum(SKILLS.effective_rank(staged.r,owner,skill) for skill in ('육상','집중'))
                TEMP.grant(staged,target,value,provenance={'source':feature_source(staged.r,STAYING,'local_csv')['clause_id'],
                    'owner_id':owner.entity_id,'request_id':request_id})
        removed=None
        if shrug is not None:
            removed=_shrug_heal(staged,target,shrug,consume=not shrug_csv)
        if assistants:_disadvantage(staged,assistants[0],assisting=True)
        import stamina as STAMINA
        STAMINA.observe(staged,target,'take_a_breather',request_id=request_id,
                        **({} if not assistants else {'helper':assistants[0].entity_id}))
        record=getattr(staged,FIELD)[request_id][OBS.KEY]
        result={'completed':True,'movement':movement,'source':SOURCE}
        if removed is not None:result['removed_injuries']=removed
        if assistants:result.update(command=record['observation']['command'],helper=assistants[0].entity_id)
        else:result['save']=record['observation']['check']
        staged.log('  '+target.name+': 숨돌리기 해결',SOURCE)
        return OBS.complete(record,result)
    return G.transition(engine,actor,recover,participants=() if helper is None else (helper,),include_rulings=True)

def _continue(engine,actor,request_id,record):
    validate_continuation(engine,actor,SOURCE,'breather',record)
    with ACTION.resolution(engine,actor,SOURCE,kind='breather',_breather_attempt=record):
        MOVEMENT.boundary(engine,'take_breather_continuation')
        observed=record['observation']
        movement=_move(engine,actor,observed['retreat'],observed['progress'],observed['retreat']['reason'])
        record=getattr(engine,FIELD)[request_id][OBS.KEY]
        if not TURN.can_act(engine,actor):
            return OBS.complete(record,{'completed':False,'save':record['observation']['check'],'movement':movement,'reason':'incapacitated_during_retreat'})
        if movement['steps']!=len(record['observation']['retreat']['path'])-1:
            ACTION.ensure_resolutions_clear(engine,_breather_attempt=record)
            raise ValueError('actual Breather path interrupted; continue the same paid and observed producer')
        return _finish(engine,actor,request_id,record['observation']['origin'],movement=movement)

def _text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError('explicit '+label+' required')
    return value

def _allowance(engine,actor,movement_mode=None,*,highest=True):
    mode='land' if movement_mode is None else movement_mode
    if mode not in MOVEMENT.MODES:raise ValueError('unknown Breather movement capability')
    caps=MOVEMENT.capabilities(engine,actor)
    available={key:engine.move_profile(actor,movement_mode=key)[0] for key in MOVEMENT.MODES if caps.get(key,0)>0}
    if not available.get(mode,0) or (highest and available[mode]<max(available.values())):
        return C.PendingDecision('Breather must use its actual highest available movement capability')
    if any(key in actor.spec for key in ('mount_id','vehicle_id')) or (actor.spec.get('_burrow',{}).get('underground') and mode!='burrow'):
        return C.PendingDecision('Breather mounted/vehicle/underground retreat composition')
    if mode in ('land','swim','burrow') and actor.spec.get('_movement_altitude',0)!=0:
        return C.PendingDecision('actual aerial retreat needs Sky or Levitate and observed altitudes')
    return available[mode],mode

def _land_allowance(engine,actor):
    result=_allowance(engine,actor,'land')
    return result if isinstance(result,C.PendingDecision) else result[0]

def _retreat(engine,actor,path,reason,*,start=None,maximum_distance=None,ignore_actors=(),diagonals=None,
             movement_mode=None,movement_options=None,start_altitude=None,start_underground=None,require_highest=True):
    _text(reason,'GM maximal retreat route observation')
    if not isinstance(path,(list,tuple)) or not path:raise ValueError('actual observed retreat path required')
    probe=copy(actor);probe.spec=dict(actor.spec);probe.pos=actor.pos if start is None else start
    if start_altitude is not None:probe.spec['_movement_altitude']=start_altitude
    if start_underground is not None:probe.spec['_burrow']=dict(actor.spec.get('_burrow',{}),underground=start_underground)
    if diagonals is not None:probe._diagonal_steps=diagonals
    allowance=_allowance(engine,probe,movement_mode,highest=require_highest)
    if isinstance(allowance,C.PendingDecision):return allowance
    budget,capability=allowance
    if maximum_distance is not None:budget=min(budget,C.integer(maximum_distance,'joint retreat allowance',0))
    if capability in ('burrow','teleport'):
        points=tuple(MOVEMENT._point(p) for p in path)
        if points[0]!=probe.pos:raise ValueError('retreat path must start at the actual actor position')
        if movement_options is not None and type(movement_options)is not dict:raise ValueError('actual movement observation options required')
        options={} if movement_options is None else movement_options
        if len(points)==1:
            if options:raise ValueError('stationary Breather does not perform a native transfer')
            return {'mode':capability,'path':points,'distance':0,'budget':budget,'reason':reason,'parameters':{},
                    'origin_altitude':probe.spec.get('_movement_altitude',0),'origin_underground':bool(probe.spec.get('_burrow',{}).get('underground'))}
        if not TURN.movement_permission(engine,actor):raise ValueError('actual condition prevents the declared retreat path')
        if capability=='burrow':
            if set(options)-{'diggable','surface'}:raise ValueError('unknown actual Burrow observation')
            plan=MOVEMENT.burrow_plan(engine,probe,points,maximum_distance=budget,reason_text=reason,
                diggable=options.get('diggable'),surface=options.get('surface',False),ignore_actors=ignore_actors)
        else:
            if len(points)!=2:raise ValueError('Teleport retreat is one actual origin and destination, not a walking path')
            if set(options)-{'surface_contact','altitude','gm_distance','sky_air_policy'}:raise ValueError('unknown actual Teleport observation')
            if 'surface_contact' not in options:return C.PendingDecision('actual Teleport destination surface contact required')
            plan=MOVEMENT.teleport_plan(engine,probe,points[-1],maximum_distance=budget,reason_text=reason,ignore_actors=ignore_actors,**options)
        if isinstance(plan,C.PendingDecision):return plan
        return dict(plan,reason=reason)
    if movement_options is not None:raise ValueError('movement options belong to actual Burrow or Teleport observations')
    aerial=capability in ('sky','levitate')
    if aerial:
        if any(type(node)is not dict or set(node) not in ({'position','altitude'},{'position','altitude','gm_distance'}) for node in path):
            raise ValueError('aerial retreat requires actual position, altitude and optional measured distance')
        points=[dict(node,position=MOVEMENT._point(node['position'])) for node in path]
        if points[0]['altitude']!=probe.spec.get('_movement_altitude',0) or 'gm_distance' in points[0]:
            raise ValueError('aerial retreat must start at actual current altitude')
        for node in points:MOVEMENT._aerial_height(engine,probe,capability,node['altitude'])
        positions=[node['position'] for node in points]
        mode=capability
    else:
        points=[MOVEMENT._point(p) for p in path];positions=points
        mode=engine.move_profile(actor,movement_mode=capability)[1]
    if positions[0]!=(actor.pos if start is None else start):raise ValueError('retreat path must start at the actual actor position')
    if len(points)>1:
        if not TURN.movement_permission(engine,actor):raise ValueError('actual condition prevents the declared retreat path')
        nodes=points if aerial else [{'position':p,'altitude':0} for p in points]
        observed=MOVEMENT.observed_path(engine,probe,nodes,ignore_actors=ignore_actors)
        import map_terrain as TERRAIN
        if any(not TERRAIN.can_travel(engine,actor,p,mode,altitude=(node['altitude'] if aerial else 0)) for p,node in zip(positions[1:],nodes[1:])):raise ValueError('retreat lacks the actual base-terrain movement capability')
        diagonals=getattr(actor,'_diagonal_steps',0);penalty=0
        for start_point,end_point in zip(positions,positions[1:]):
            step,diagonals=MOVEMENT.step_cost(start_point,end_point,diagonals)
            penalty+=MOVEMENT.slow_terrain_penalty(engine,actor,end_point,mode,step=step)
        distance=observed['distance']+penalty
        if distance>budget:raise ValueError('retreat exceeds actual highest movement allowance')
    else:distance=0
    return {'path':points,'distance':distance,'budget':budget,'reason':reason,'mode':mode,
            'origin_altitude':probe.spec.get('_movement_altitude',0),'origin_underground':bool(probe.spec.get('_burrow',{}).get('underground'))}

def _curse_retreat(actor,origin,plan):
    if origin is not None and not origin.fainted:
        height=(plan['path'][-1]['altitude'] if plan['mode'] in ('sky','levitate') else
                plan.get('parameters',{}).get('altitude',plan.get('origin_altitude',actor.spec.get('_movement_altitude',0))))
        underground=(plan['mode']=='burrow' and not plan['parameters'].get('surface',not plan.get('origin_underground',False)))
        if height!=0 or underground or origin.spec.get('_burrow',{}).get('underground'):
            return C.PendingDecision('Breather Curse distance requires actual 3D/underground measurement')
    return origin

def _curse(engine,actor,origin,reason):
    known=actor.custom_conditions.get('curse_origin')
    if known is not None and origin is not None and known is not origin:raise ValueError('cannot replace the actual Curse origin')
    origin=known if known is not None else origin
    if '저주' not in actor.conditions:
        if origin is not None or reason is not None:raise ValueError('Curse observation requires an actual cursed actor')
        return None
    if origin is None:return C.PendingDecision('actual Curse origin required for Breather cure exception')
    W.require_actors(engine,origin)
    if known is None:_text(reason,'GM observation of actual Curse origin')
    if origin.spec.get('_movement_altitude',0)!=0:return C.PendingDecision('Breather Curse distance requires actual 3D measurement')
    return origin

def _recover(engine,actor,origin,*,staying_power=None,no_shift_trip=False):
    import status_sets as STATUSES,combat_state_lifecycle as STATE,temporary_hp as TEMP
    import body_state as BODY
    from grid import cheb
    for condition in STATUSES.afflictions(actor,'volatile'):
        if condition=='저주':
            if not origin.fainted:
                if (actor.spec.get('_movement_altitude',0)!=origin.spec.get('_movement_altitude',0)
                        or any(c.spec.get('_burrow',{}).get('underground') for c in (actor,origin))):
                    raise ValueError('actual Breather Curse distance requires 3D or underground observation')
                distance=min(cheb(a,b) for a in BODY.cells(actor,require_complete=True) for b in BODY.cells(origin,require_complete=True))
                if distance<=12:continue
        engine.cure_status(actor,condition)
    import healing_blocks as HEALING_BLOCKS
    HEALING_BLOCKS.boundary(engine,(actor,),'breather')
    __import__('defense_curl').boundary(engine,(actor,),'breather')
    import linked_move_conditions as LINKED
    LINKED.boundary(engine,actor,'breather')
    for condition in ('둔화','구속'):engine.cure_status(actor,condition)
    if staying_power is None or staying_power['reset_stages']:STATE.reset_actor(engine,actor)
    if staying_power is None or staying_power.get('clear_temp_hp',True):TEMP.clear(engine,actor,'숨돌리기')
    _disadvantage(engine,actor,staying_power=staying_power,no_shift_trip=no_shift_trip)

def _disadvantage(engine,actor,*,assisting=False,staying_power=None,no_shift_trip=False):
    import effect_lifetimes as LIFETIMES,combat_timing as TIMING
    if staying_power is not None:
        owner=staying_owner(engine,actor,staying_power)
        if feature_edition(engine,owner,STAYING)=='local_csv':return
    record=LIFETIMES.prepare(engine,actor,actor,
        {'type':'apply_status','status':'넘어짐','until':"end of user's next turn"},SOURCE)
    record['statuses']=['넘어짐'] if assisting else ['넘어짐','취약']
    if no_shift_trip:record['statuses']=['취약']
    if staying_power is not None:
        record['statuses']=['취약']
    if assisting:record['evasion_zero']=True
    TIMING.install(engine,actor,record)

def take(engine,actor,*,staying_power=None,**options):
    def apply(e,c):
        with _staying_scope(e,c,staying_power):
            return _take(e,c,staying_power=staying_power,**options)
    if staying_power is not None or options.get('shrug_off') is not None:
        import state_grants as G
        return G.transition(engine,actor,apply,include_rulings=True,include_grid=engine.grid is not None)
    return apply(engine,actor)

def _take(engine,actor,*,request_id,path=None,retreat_reason=None,save_dc=None,save_reason=None,
         save_cost=None,fixed_save=None,curse_origin=None,curse_reason=None,helper=None,assistance=None,movement_mode=None,movement_options=None,staying_power=None,shrug_off=None):
    """Ordinary voluntary producer. Unsupported assisted/movement branches hold.

    save_cost is an explicit table decision: full on any attempt, or only after
    a successful permission save. A saved observation cannot be rerolled.
    """
    W.require_actors(engine,actor);selected(engine.r)
    _text(request_id,'Breather request identity')
    if helper is not None:
        if shrug_off is not None:raise ValueError('Shrug Off requires its own Pokemon voluntary Breather')
        if staying_power is not None:raise ValueError('Staying Power does not grant the assisting Trainer its benefits')
        if movement_mode is not None or movement_options is not None:return C.PendingDecision('assisted Breather distinct participant movement modes and reach')
        if assistance is not None and any(x is not None for x in (save_dc,save_reason,save_cost,fixed_save)):
            raise ValueError('assisted Breather uses actual Command DC12, not a voluntary saving check')
        import breather_assistance as ASSISTANCE
        return ASSISTANCE.take(engine,actor,helper,request_id=request_id,path=path,retreat_reason=retreat_reason,
            curse_origin=curse_origin,curse_reason=curse_reason,assistance=assistance)
    if assistance is not None:raise ValueError('assistance inputs require an actual assisting Trainer')
    declaration={'actor':actor,'path':deepcopy(path),'retreat_reason':retreat_reason,
        'save_dc':save_dc,'save_reason':save_reason,'save_cost':save_cost,'fixed_save':fixed_save,
        'curse_origin':curse_origin,'curse_reason':curse_reason,'helper':helper}
    if movement_mode is not None:declaration['movement_mode']=movement_mode
    if movement_options is not None:declaration['movement_options']=deepcopy(movement_options)
    if staying_power is not None:declaration['staying_power']=deepcopy(staying_power)
    if shrug_off is not None:declaration['shrug_off']=deepcopy(shrug_off)
    records=getattr(engine,FIELD,{})
    if request_id in records:
        old=records[request_id][OBS.KEY];OBS.verify(old,declaration)
        if old['state']=='complete':return old['result']
        return _continue(engine,actor,request_id,old)
    MOVEMENT.boundary(engine,'take_breather');ACTION.ensure_resolutions_clear(engine)
    shrug_owner_actor=None if shrug_off is None else shrug_owner(engine,actor,shrug_off)
    swift=shrug_owner_actor is not None and feature_edition(engine,shrug_owner_actor,SHRUG)=='local_csv'
    if shrug_off is not None:_shrug_quota(engine,actor)
    if swift and (not TURN.can_act(engine,shrug_owner_actor) or not ACTION.status_permission(engine,shrug_owner_actor,'free',new_action=True)):
        raise ValueError('CSV Shrug Off actual Trainer Free Action unavailable')
    action='swift' if swift else 'full'
    if actor.kind not in ('trainer','pokemon') or not actor.on_field or actor.captured:raise ValueError('actual participating Trainer or Pokemon required')
    if not engine.encounter_active:return C.PendingDecision('actual combat and next owner-turn boundary required')
    if not TURN.can_act(engine,actor) or not ACTION.ordinary_permission(engine,actor) or not ACTION.status_permission(engine,actor,action):return False
    import combat_maneuvers as MANEUVERS
    if MANEUVERS.force_attack(actor) and staying_power is None:return C.PendingDecision('Enraged actor requires an actual assisting Trainer')
    if not isinstance(actor.budget,dict):return False
    available=max(actor.budget.get('standard',0),actor.budget.get('swift',0)) if swift else min(actor.budget.get('standard',0),actor.budget.get('shift',0))
    if available<=0:return False
    if save_cost not in ('full','success_only') or not isinstance(save_reason,str) or not save_reason.strip():
        return C.PendingDecision('GM Breather permission-save DC and failed-save cost adjudication; prose prints no universal values')
    condition='혼란' if '혼란' in actor.conditions else None
    if save_dc is None and condition:
        effects=engine.r.condition_effects(condition)
        save_dc=next((e['dc'] for e in effects if e.get('type')=='save'),None)
        if save_dc is None and __import__('confusion_attacks').core(engine):
            save_dc=next(e['cure_min'] for e in effects if e.get('type')=='core_confusion_start_turn')
    if save_dc is None:return C.PendingDecision('explicit GM general Breather saving DC; no universal DC is printed')
    C.integer(save_dc,'Breather saving DC',1)
    if fixed_save is not None:C.integer(fixed_save,'Breather observed saving d20',1,20)
    import condition_recovery as RECOVERY,combat_state_lifecycle as STATE,temporary_hp as TEMP
    RECOVERY.save_preflight(engine,actor,condition)
    STATE.preflight(actor);TEMP.ensure_certain(engine,actor)
    if staying_power is not None:
        if any(x is not None for x in (path,retreat_reason,movement_mode,movement_options)):raise ValueError('Staying Power does not perform the ordinary mandatory retreat')
        plan={'path':[actor.pos],'distance':0,'budget':0,'reason':'actual Staying Power Breather','mode':'육상','origin_altitude':actor.spec.get('_movement_altitude',0),'origin_underground':bool(actor.spec.get('_burrow',{}).get('underground'))}
    else:plan=_retreat(engine,actor,path,retreat_reason,movement_mode=movement_mode,movement_options=movement_options)
    if isinstance(plan,C.PendingDecision):return plan
    origin=_curse(engine,actor,curse_origin,curse_reason)
    if isinstance(origin,C.PendingDecision):return origin
    origin=_curse_retreat(actor,origin,plan)
    if isinstance(origin,C.PendingDecision):return origin
    with ACTION.resolution(engine,actor,SOURCE,kind='breather'):
        if swift:ACTION.triggered_free_action(engine,shrug_owner_actor,SHRUG)
        if staying_power is not None:
            import frequency as F
            owner=staying_owner(engine,actor,staying_power);quota={'kind':'scene','uses':1}
            if not F.activation_allowed(owner,STAYING,quota,engine=engine):raise ValueError('Staying Power Scene use exhausted')
            ACTION.triggered_free_action(engine,owner,STAYING)
            F.consume_activation(owner,STAYING,quota,engine=engine)
        if not hasattr(engine,FIELD):setattr(engine,FIELD,{})
        records=getattr(engine,FIELD)
        if save_cost=='full' and not TURN.spend(engine,actor,action,'숨돌리기'):return False
        if swift and save_cost=='full':
            import frequency as F
            F.consume_activation(actor,SHRUG,{'kind':'daily','uses':1},engine=engine)
        observation=OBS.begin(records,request_id,'take_a_breather',(actor,),declaration,{},
                              references=() if origin is None else (origin,))
        check=RECOVERY.saving_check(engine,actor,condition,save_dc,fixed=fixed_save)
        observation['observation'].update(check=check,retreat=plan,table_save_adjudication=save_reason,
                                          origin=origin,progress={},turn=_turn(engine,actor))
        if staying_power is not None:observation['observation']['staying_power']=deepcopy(staying_power)
        if shrug_off is not None:observation['observation']['shrug_off']=deepcopy(shrug_off)
        if not check['passed']:
            return OBS.complete(observation,{'completed':False,'save':check,'reason':'save_failed'})
        if save_cost=='success_only' and not TURN.spend(engine,actor,action,'숨돌리기'):
            return OBS.complete(observation,{'completed':False,'save':check,'reason':'full_action_unavailable'})
        if swift and save_cost=='success_only':
            import frequency as F
            F.consume_activation(actor,SHRUG,{'kind':'daily','uses':1},engine=engine)
        observation['observation']['phase']='retreat'
        movement={'steps':0,'staying_power':True} if staying_power is not None else _move(engine,actor,plan,observation['observation']['progress'],retreat_reason)
        observation=getattr(engine,FIELD)[request_id][OBS.KEY]
        if movement['steps']:actor._regular_shift_movement_used=True
        if not TURN.can_act(engine,actor):
            return OBS.complete(observation,{'completed':False,'save':check,'movement':movement,'reason':'incapacitated_during_retreat'})
        if movement['steps']!=len(plan['path'])-1:
            ACTION.ensure_resolutions_clear(engine,_breather_attempt=observation)
            raise ValueError('actual Breather path interrupted; paid cost and observed save cannot replay')
        return _finish(engine,actor,request_id,origin,movement=movement)
