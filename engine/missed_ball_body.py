"""C05-157: one thrown body, observed ground, and existing recovery owners."""
from copy import deepcopy
from functools import wraps
import common_checks as C
import state_grants as G
import world_entities as W
import item_stock as STOCK
import items as I
import map_terrain as TERRAIN
import action_lifecycle as ACTION

SOURCE='ch05-pokemon/포켓몬-포획'
REFERENCE={'file':'input/ch05-pokemon.md','sha256':'bdfb5d39fec8fede32cac615a7788301336aaceefc46079c8ed7014ea76d174b'}


def source(rules):
    selected=rules.select_source_definition(SOURCE,source=REFERENCE)
    bounds=selected['source'].get('lines',())
    if selected['selected_id']!=SOURCE or len(bounds)!=2 or not bounds[0]<=690<=bounds[1]:
        raise ValueError('selected missed-ball source needs its own physical policy')
    return selected


def atomic_throw(fn):
    @wraps(fn)
    def run(e,trainer,target,*args,**options):
        # Action frames and staged participants are not world registration.
        W.require_actors(e,trainer,target)
        with ACTION.resolution(e,trainer,'pokemon/capture-rate',kind='capture'):
            return G.transition(e,trainer,lambda se,sa,st:fn(se,sa,st,*args,**options),
                                participants=(target,),include_rulings=True,include_grid=e.grid is not None)
    return run


def physical(e,actor,uid):
    import csv_item_physical_contracts as CSV
    obj=getattr(e,'_physical_objects',{}).get(uid)
    if not isinstance(obj,dict):raise ValueError('actual possessed ball instance required')
    CSV._object(e,actor,uid,obj.get('item_rule_id'))
    if obj.get('disabled') or obj.get('ball_integrity',{}).get('intact') is False:
        raise ValueError('broken physical ball must be repaired before use')
    for owner in W.actor_index(e).values():
        for attempt in owner.spec.get('capture_attempts',{}).values():
            identity=attempt.get('physical_instance_id',attempt.get('cannon',{}).get('ball_instance_id'))
            if identity==uid and attempt.get('status') not in ('recovered_intact','repaired'):
                raise ValueError('thrown ball must be actually recovered before reuse')
    return obj


def ball_rule(e,name):
    candidates=[uid for uid,row in e.r.items_mech.items()
                if row.get('name')==name and row.get('header',{}).get('use')=='ball']
    if len(candidates)!=1:raise ValueError('one actual capture-ball product definition required')
    return candidates[0]


def prepare(e,actor,name,inventory_key,physical_instance_id,cannon):
    selection=source(e.r)
    if physical_instance_id is not None and cannon is not None:
        raise ValueError('select the hand ball or the loaded Cannon ball once')
    uid=cannon['ball_instance_id'] if cannon is not None else physical_instance_id
    if uid is not None:
        obj=physical(e,actor,uid)
        header=e.r.item_effects(obj['item_rule_id'])[1]
        definition=e.r.items_mech.get(header['id'],{})
        if I.ball_name(definition.get('name',''))!=name or header.get('use')!='ball':
            raise ValueError('selected physical projectile must be this ball kind')
        if cannon is None:
            if any(row.get('csv_remaining_item_state',{}).get('loaded_ball_instance_id')==uid
                   for row in getattr(e,'_physical_objects',{}).values()):
                raise ValueError('loaded Cannon projectile cannot also be thrown by hand')
            if obj.get('equipped_by'):
                STOCK.inspect_held(e,actor,obj['item_rule_id'],uid)
            elif W.distance_known(obj,actor)!=0:
                raise ValueError('hand throw needs the actual recovered ball at the actor')
            if obj.get('carrier_id'):
                raise ValueError('release carried load before selecting a hand projectile')
        return {'kind':'physical','instance_id':uid,'item_id':obj['item_rule_id'],'selection':selection}
    header=e.r.item_effects(ball_rule(e,name))[1]
    # shortcut: native legacy Basic Ball keys predate exact product IDs; retain their existing count debit.
    if inventory_key in I.BALL_ALIASES or (name=='몬스터볼' and inventory_key in ('몬스터볼','item/몬스터볼')):
        C.integer(actor.spec['items'].get(inventory_key),'actual legacy ball count',1)
        stock={'kind':'legacy_ball_alias','item_id':header['id'],'key':inventory_key}
    else:stock=STOCK.prepare(e,actor,header['id'],quantity_key=inventory_key)
    return {'kind':'quantity','stock':stock,'item_id':header['id'],'selection':selection}


def launch(e,actor,target,attempt,plan):
    if e.grid is not None and not hasattr(e.grid,'_tunnel_map_id'):
        from uuid import uuid4
        e.grid._tunnel_map_id=str(uuid4())
    uid=plan.get('instance_id')
    if plan['kind']=='quantity':
        uid=actor.entity_id+'/ball/'+attempt['id']
        if uid in W.entity_index(e):raise ValueError('new projectile identity already exists')
        if plan['stock']['kind']=='legacy_ball_alias':
            key=plan['stock']['key'];C.integer(actor.spec['items'].get(key),'actual legacy ball count',1)
            actor.spec['items'][key]-=1
        else:STOCK.debit(e,actor,plan['stock'])
        W.register_object(e,uid,location={'kind':'unknown'},reason='actual quantity ball thrown once',
                          kind='item_instance',item_rule_id=plan['item_id'],owner_id=actor.entity_id,source=SOURCE)
    obj=e._physical_objects[uid]
    for key,row in list(getattr(actor,'_item_reg',{}).items()):
        if row.get('instance_id')==uid:I.unregister_item(e,actor,registration_key=key)
    obj.pop('carrier_id',None)
    W._set_object_location(obj,{'kind':'unknown'})
    attempt.update(physical_instance_id=uid,physical_item=plan['item_id'],physical_source=plan['selection'],
                   throw_origin=W.location_of(actor),throw_target=W.location_of(target),
                   throw_map_id=getattr(e.grid,'_tunnel_map_id',None) if e.grid is not None else None)
    obj['ball_integrity']={'intact':True,'source':SOURCE,'basis':'undamaged before throw'}
    return obj


def miss(e,actor,attempt):
    obj=attempt_ball(e,actor,attempt)
    W._set_object_location(obj,{'kind':'unknown'})
    obj['ball_integrity']={'intact':True,'source':SOURCE,'basis':'usual intact missed landing'}
    attempt['landing']={'status':'pending','reason':'GM must observe actual behind-target ground and integrity'}


def attempt_ball(e,actor,attempt):
    uid=attempt.get('physical_instance_id')
    if uid is None:return None
    obj=getattr(e,'_physical_objects',{}).get(uid)
    if (not isinstance(obj,dict) or obj.get('kind')!='item_instance'
            or obj.get('owner_id')!=actor.entity_id or obj.get('item_rule_id')!=attempt.get('physical_item',attempt.get('item'))):
        raise ValueError('same actual thrown ball identity required')
    if attempt.get('status')!='captured':W.require_present_object(obj)
    return obj


def observe_ground(e,actor,*,attempt_id,cell=None,intact=None,reason):
    source(e.r);W.require_actors(e,actor)
    W._text(reason,'GM actual landing and integrity reason')
    attempt=actor.spec.get('capture_attempts',{}).get(attempt_id)
    if not isinstance(attempt,dict) or attempt.get('hit') or attempt.get('status')!='recoverable_on_ground':
        raise ValueError('actual missed throw awaiting ground required')
    if attempt.get('landing',{}).get('status')=='observed':raise ValueError('missed-ball landing already observed')
    origin=attempt.get('throw_origin',{});target=attempt.get('throw_target',{})
    if (e.grid is None or cell is None or intact is None or origin.get('kind')!='grid' or target.get('kind')!='grid'
            or origin.get('map_id')!=target.get('map_id')):
        return C.PendingDecision('GM must observe actual ground cell and integrity on the throw map')
    if type(intact) is not bool:raise ValueError('explicit observed ball integrity required')
    cell=TERRAIN.point(cell)
    if not e.grid.inside(cell):raise ValueError('actual landing is outside the current grid')
    if attempt.get('throw_map_id')!=getattr(e.grid,'_tunnel_map_id',None):
        raise ValueError('landing observation must use the original throw map')
    a,b=origin['cell'],target['cell'];direction=[b[i]-a[i] for i in (0,1)]
    if not any(direction):return C.PendingDecision('original throw direction is unknown at coincident positions')
    if sum((cell[i]-b[i])*direction[i] for i in (0,1))<=0:
        raise ValueError('observed missed-ball ground must be behind the original target')
    terrain=getattr(e.grid,'terrain_observations',{}).get(TERRAIN.key(cell),{}).get('map_terrain')
    if not terrain:return C.PendingDecision('GM must observe the actual landing terrain before resolving the missed ball')
    TERRAIN.validate(e.grid)
    if terrain.get('base')!=getattr(e.grid,'base_terrain',{}).get(TERRAIN.key(cell)):
        raise ValueError('actual landing terrain observation changed')
    def apply(se,sa):
        row=sa.spec['capture_attempts'][attempt_id];obj=attempt_ball(se,sa,row)
        before=deepcopy(row.get('landing'))
        W._set_object_location(obj,{'kind':'grid','cell':list(cell)})
        obj['ball_integrity']={'intact':intact,'source':SOURCE,'basis':'GM observed actual landing','reason':reason}
        if not intact:obj['disabled']=True
        row['landing']={'status':'observed','cell':list(cell),'intact':intact,'terrain':deepcopy(terrain),'reason':reason,'source':SOURCE}
        se.gm._rec('missed ball '+obj['id'],before,row['landing'],reason,sa)
        return deepcopy(row['landing'])
    return G.transition(e,actor,apply,include_rulings=True)


def recover(e,actor,attempt):
    obj=attempt_ball(e,actor,attempt)
    if obj is None:return False
    source(e.r)
    if not attempt.get('hit'):
        landing=attempt.get('landing',{})
        if landing.get('status')!='observed':return C.PendingDecision('actual missed-ball landing must be observed before recovery')
        if not landing.get('intact'):raise ValueError('observed broken missed ball cannot be recovered intact')
        if W.location_of(obj)!={'kind':'grid','cell':tuple(landing['cell'])}:
            raise ValueError('actual missed ball moved from its observed ground')
    obj.pop('disabled',None)
    obj['ball_integrity']={'intact':True,'source':SOURCE,'basis':'actual recovery or completed repair'}
    W._set_object_location(obj,W.location_of(actor))
    return True


def validate_world(e,index):
    selected=None
    for actor in index.values():
        active=set()
        for attempt in actor.spec.get('capture_attempts',{}).values():
            if 'physical_instance_id' not in attempt:continue
            if selected is None:selected=source(e.r)
            completed=attempt.get('status') in ('recovered_intact','repaired','permanently_broken','captured')
            if completed:
                obj=getattr(e,'_physical_objects',{}).get(attempt['physical_instance_id'])
                if (not isinstance(obj,dict) or obj.get('kind')!='item_instance'
                        or obj.get('item_rule_id')!=attempt.get('physical_item')):
                    raise ValueError('completed throw must retain its original physical identity')
            else:obj=attempt_ball(e,actor,attempt)
            if attempt.get('physical_source')!=selected:raise ValueError('saved physical ball source changed')
            cannon=attempt.get('cannon')
            if cannon and cannon.get('ball_instance_id')!=obj['id']:raise ValueError('Cannon and throw must share the same actual body')
            if completed:continue
            if obj['id'] in active:raise ValueError('same actual ball has two unresolved throws')
            active.add(obj['id'])
            if attempt.get('hit'):continue
            landing=attempt.get('landing',{})
            if landing.get('status')=='pending':
                if W.location_of(obj)!={'kind':'unknown'}:raise ValueError('pending missed landing cannot invent a ground position')
            elif landing.get('status')=='observed':
                if (W.location_of(obj)!={'kind':'grid','cell':tuple(landing.get('cell',()))}
                        or obj.get('ball_integrity',{}).get('intact') is not landing.get('intact')):
                    raise ValueError('same actual ball ground and integrity disagree')
            else:raise ValueError('actual missed ball needs pending or observed ground')
    return True
