"""Native Threaded: current capability, relative mass, ordinary hit and shared displacement."""
from pathlib import Path
from copy import deepcopy
import json
import state_grants as G,world_entities as W,body_state as B,common_checks as C
import precise_threadings as P
import action_lifecycle as ACTION,confusion_attacks as CONFUSION
from physical_limits import number
from source_context import verified_source

SOURCE=P.CAPABILITY


def policy(rules):
    value=json.loads((Path(rules.root)/'data/threaded-policy.json').read_text(encoding='utf-8'))
    verified_source(rules,value['source'],label='Threaded')
    if value.get('rule_id')!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Threaded source required')
    return value


def parameters(actor):
    value=policy(actor.r)
    return dict({key:value[key] for key in ('range','accuracy','action_cost')},**P.parameters(actor))


def require(engine,actor,target):
    W.require_actors(engine,actor)
    if not P.owned(actor):raise ValueError('current actual Threaded capability required')
    policy(engine.r)
    if actor.fainted or not actor.on_field or actor.captured:raise ValueError('available actual Threaded user required')
    if type(target)is dict:
        if getattr(engine,'_physical_objects',{}).get(target.get('id'))is not target:raise ValueError('actual registered Threaded target object required')
        W.require_usable_object(target)
        if any(target.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):raise ValueError('Threaded is not an implicit Disarm or load release')
        uid=target['id'];mass=number(target.get('weight_kg'),'actual Threaded object weight',minimum=0)
    else:
        W.require_actors(engine,target)
        if target is actor or not target.on_field or target.captured:raise ValueError('distinct available actual Threaded target required')
        if target.spec.get('_movement_altitude',0) or target.spec.get('_burrow',{}).get('underground'):raise ValueError('Threaded requires observed same-plane geometry')
        uid=target.entity_id;mass=number(B.weight_kg(target),'actual Threaded target weight',minimum=0)
    own=number(B.weight_kg(actor),'actual Threaded user weight',minimum=0)
    if engine.grid is None or actor.spec.get('_movement_altitude',0) or actor.spec.get('_burrow',{}).get('underground'):raise ValueError('Threaded requires actual mapped same-plane geometry')
    left,right=W.location_of(actor),W.location_of(target)
    if left['kind']!='grid' or right['kind']!='grid' or left.get('map_id')!=right.get('map_id'):raise ValueError('known same-map Threaded positions required')
    import body_modes as MODES
    reach=parameters(actor)['range'];cells={tuple(right['cell'])} if type(target)is dict else B.cells(target,require_complete=True)
    if not any(max(abs(a[i]-b[i]) for i in (0,1))<=reach and not engine.grid.blocked(a,b)
               and not MODES.blocks_line(engine,a,b,ignored=(actor,target)) for a in B.cells(actor,require_complete=True) for b in cells):
        raise ValueError('Threaded target outside actual clear range')
    return {'actor_id':actor.entity_id,'target_id':uid,'actor_weight':own,'target_weight':mass,
            'actor_position':left,'target_position':right}


def equal_weight_policy(engine,actor,target,decision=None):
    binding=require(engine,actor,target)
    if binding['actor_weight']!=binding['target_weight']:raise ValueError('equal-weight interpretation belongs only to actual tied weights')
    if decision is not None and (type(decision)is not dict or 'scope' not in decision):
        raise ValueError('equal Threaded weights require a scoped explicit local decision')
    document=deepcopy(policy(engine.r)['equal_weight'])
    document['variants'][0]['values']['binding']=binding
    return engine.r.resolve_source_policy(document,decisions={} if decision is None else {'mover':decision})


def prepare(engine,actor,target,*,willing,path,reason,equal_decision=None,fixed_accuracy=None):
    binding=require(engine,actor,target)
    if type(willing)is not bool or type(reason)is not str or not reason.strip():raise ValueError('actual willingness and pull path observation reason required')
    if type(target)is dict and not willing:raise ValueError('unwilling attack requires an actual opposing actor')
    if fixed_accuracy is not None:C.integer(fixed_accuracy,'Threaded accuracy d20',1,20)
    if willing and fixed_accuracy is not None:raise ValueError('willing Threaded target has no accuracy roll')
    selected=None
    if binding['actor_weight']==binding['target_weight']:
        selected=equal_weight_policy(engine,actor,target,equal_decision)
        if selected['status']!='PolicyValuesReady':raise ValueError('equal Threaded weights require explicit scoped mover decision')
        mover=selected['values']['mover']
    else:
        if equal_decision is not None:raise ValueError('equal-weight decision cannot override actual unequal weights')
        mover='actor' if binding['actor_weight']<binding['target_weight'] else 'target'
    subject=actor if mover=='actor' else target
    if not isinstance(path,(list,tuple)) or not path or any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(x)is not int for x in p) for p in path):raise ValueError('explicit actual Threaded pull path required')
    points=[tuple(p) for p in path]
    if points[0]!=W.grid_cell(subject):raise ValueError('pull path must start at the actual lighter participant')
    if mover=='none':
        if len(points)!=1:raise ValueError('no-movement interpretation requires no displacement path')
    else:
        if len(points)<2:raise ValueError('explicit nonempty pull path required')
        anchor=target if mover=='actor' else actor
        anchors={W.grid_cell(anchor)} if type(anchor)is dict else B.cells(anchor,require_complete=True)
        def gap(point):
            occupied={point} if type(subject)is dict else B.at_position(subject,point)
            return min(max(abs(a[i]-b[i]) for i in (0,1)) for a in occupied for b in anchors)
        for a,b in zip(points,points[1:]):
            if max(abs(b[i]-a[i]) for i in (0,1))!=1 or gap(b)>=gap(a):raise ValueError('each Threaded step must pull continuously toward the heavier participant')
            if not engine.grid.inside(b):raise ValueError('mapped Threaded pull path required')
    value=parameters(actor)
    move={'id':SOURCE,'name':'실 날리기','type':'노말','class':'변화','ac':value['accuracy'],'range':str(value['range'])+', 대상 1','keywords':[]}
    if not willing:engine._prepare_accuracy_context(actor,target,move,fixed_roll=fixed_accuracy)
    return {'binding':binding,'mover':mover,'points':points,'parameters':value,'move':move,'equal_weight_policy':selected}


def use(engine,actor,target,*,willing,path,reason,equal_decision=None,fixed_accuracy=None):
    options=dict(willing=willing,path=path,reason=reason,equal_decision=equal_decision,fixed_accuracy=fixed_accuracy)
    # Bind physical objects by their actual identity in the staged world.
    if type(target)is dict:
        require(engine,actor,target);uid=target['id']
        return G.transition(engine,actor,lambda e,a:_use(e,a,e._physical_objects[uid],**options))
    W.require_actors(engine,actor,target)
    return G.transition(engine,actor,lambda e,a,t:_use(e,a,t,**options),participants=(target,))


@ACTION.resolved_native("actor",SOURCE,"threaded")
def _use(engine,actor,target,**options):
    plan=prepare(engine,actor,target,**options)
    if not options['willing']:CONFUSION.preflight(engine,actor,plan['move'])
    import turn as TURN,forced_movement as FORCED,precise_actions as PRECISE
    if not TURN.spend(engine,actor,plan['parameters']['action_cost'],'실 날리기'):raise ValueError('cannot pay actual Threaded Shift action')
    hit=True;natural=None;interrupted=False
    if not options['willing']:
        if not engine.adjacent(actor,target):TURN.trigger_aoo(engine,actor,'인접하지 않은 대상에게 원거리 공격')
        interrupted=not TURN.can_act(engine,actor)
        if interrupted:hit=False
        else:
            CONFUSION.observe_action(engine,actor,plan['move'])
            event=PRECISE.attacked(engine,actor,target,plan['move'],producer='Engine.threaded')
            hit,natural,_=engine.accuracy_check(actor,target,plan['move'],fixed_roll=options['fixed_accuracy'])
            PRECISE.accuracy(event,hit)
    movement=None
    if hit and plan['mover']!='none':
        if require(engine,actor,target)!=plan['binding']:raise ValueError('actual Threaded geometry or weight changed during resolution')
        subject=actor if plan['mover']=='actor' else target
        movement=FORCED.along_path(engine,actor,subject,points=plan['points'],source=SOURCE,
                                  allow_fainted=type(subject)is not dict and subject.fainted)
    result={'source':SOURCE,'actor_id':actor.entity_id,'target_id':plan['binding']['target_id'],
            'hit':hit,'natural':natural,'interrupted':interrupted,'mover':plan['mover'],'range':plan['parameters']['range'],'accuracy':plan['parameters']['accuracy'],
            'action_cost':plan['parameters']['action_cost'],'movement':movement,'equal_weight_policy':plan['equal_weight_policy'],'reason':options['reason']}
    engine.gm._rec('Threaded action',None,result,options['reason'],actor)
    return result
