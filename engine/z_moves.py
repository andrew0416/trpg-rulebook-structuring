"""Printed Z crystals: physical source choices over native Technique consumers."""
from copy import deepcopy
import state_grants as G
import world_entities as W
import frequency as F

FEATURE = 'feat/전력포즈'
CLAUSE = 'input/ch03-skills-edges-feats.md:674-677'
BOOK_SHA = 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
SOURCE = {'file':'input/hb-zmoves.md','sha256':'da78fc14141b928e225be5f5bf34c352db066b60cb4ebffbc1054feba360c513'}
RING = 'item/hb-zring'
POWER_RING = 'item/hb-zpower-ring'
CRYSTAL = 'item/hb-zcrystal'
CHOICE = 'z_crystal_choice'
HISTORY = 'z_crystal_uses'
QUOTA = {'kind':'scene','uses':1}
MARKER = '_z_crystal_technique'
ITEMS = {RING:('Z링 (수정형)','장신구',[7,7],'hb-zmoves-1'),
         POWER_RING:('Z파워링 (수정형)','장신구',[8,8],'hb-zmoves-1'),
         CRYSTAL:('Z크리스탈 (수정형)',None,[15,15],'hb-zmoves/지니는-도구')}


def _sign(row):
    row['sha256']=__import__('resolution_transaction').request_fingerprint({k:v for k,v in row.items() if k!='sha256'})
    return row


def _signed(row):
    if type(row) is not dict or row.get('sha256')!=_sign(deepcopy(row))['sha256']:
        raise ValueError('actual immutable Z crystal source choice required')


def source(rules,item_id=CRYSTAL):
    from source_context import verified_source
    verified_source(rules,SOURCE,label='Z crystal modifier source')
    if rules._selected_rule(item_id)!=item_id:raise ValueError('selected actual hb Z equipment source required')
    return deepcopy(SOURCE)


def install(rules):
    """Derived identities preserve source/profile admission and CSV separation."""
    from source_context import verified_source
    from ruleset import ExcludedRuleSelection
    if not any(s in rules.ruleset.sources for s in ('*','hb-zmoves')):return
    verified_source(rules,SOURCE,label='printed Z equipment')
    for uid,(name,slot,span,parent) in ITEMS.items():
        unit={'id':uid,'name':name,'kind':'entity:item','source':{
            'file':'hb-zmoves.md','lines':span,'sha256':SOURCE['sha256']}}
        try:rules.selection.register_derived(unit,(parent,))
        except ExcludedRuleSelection:continue
        header={'name':name,'category':'장신구' if slot else '지니는 도구'}
        if slot:header['trainer_slot']=slot
        rules.items_mech[uid]={'name':name,'coverage':'full','header':header,'effects':[],
            'desc':'Actual hb-zmoves.md source; not the typed daily CSV variant.'}


def acquired(trainer):
    import trainer_feature_acquisition as T, acquired_features as A
    if not A.owned_rule_count(trainer,FEATURE):return None
    T.validate_actor(trainer)
    rows=[r['static_acquisition'] for _,r,live in T._static_records(trainer)
          if live and r['static_acquisition']['feature_id']==FEATURE]
    if trainer.kind!='trainer' or len(rows)!=1 or A.owned_rule_count(trainer,FEATURE)!=1:
        raise ValueError('one real Full-Force Pose acquisition required')
    return rows[0]


def _object(engine,uid,rule=None):
    obj=getattr(engine,'_physical_objects',{}).get(uid)
    if type(obj) is not dict or obj.get('kind')!='item_instance' or rule and obj.get('item_rule_id')!=rule:
        raise ValueError('actual physical Z equipment instance required')
    W.require_physical_access(obj)
    return obj


def _equipped(engine,actor,uid,rules,*,held=False):
    import items as I
    rows=[r for r in I.equipment_options(actor,('held',) if held else ('장신구',))
          if r.get('instance_id')==uid and r.get('item_id') in rules
          and r.get('registration_key') in getattr(actor,'_item_reg',{})
          and (r.get('held') if held else '장신구' in r.get('slots',[]))]
    if len(rows)!=1:raise ValueError('actual held crystal or worn Trainer ring required')
    source(engine.r,rows[0]['item_id'])
    obj=_object(engine,uid,rows[0]['item_id'])
    if obj.get('equipped_by')!=actor.entity_id:raise ValueError('Z equipment requires its actual equipped holder')
    if not I.equipment_benefit_active(actor,actor._item_reg[rows[0]['registration_key']]):
        raise ValueError('suppressed Z equipment cannot supply a modifier')
    return obj


def observe_crystal(engine,instance_id,*,modification,reason,source_contract='core_1.05'):
    """GM observes the single immutable modifier carried by an actual reward."""
    import ace_trainer as A
    source(engine.r);G._text(reason,'observed crystal reward reason')
    if modification not in A.MODIFICATIONS:raise ValueError('one actual printed Signature Technique modifier required')
    A.source(engine.r,source_contract)
    obj=_object(engine,instance_id,CRYSTAL)
    row=_sign({'instance_id':instance_id,'modification':modification,'source_contract':source_contract,
               'source':deepcopy(SOURCE),'reason':reason})
    if 'z_crystal' in obj:
        if obj['z_crystal']!=row:raise ValueError('one physical crystal cannot change its contained modifier')
        return deepcopy(row)
    obj['z_crystal']=row
    return deepcopy(row)


def _current(engine,pokemon,row):
    import ace_trainer as A
    _signed(row);source(engine.r)
    index=W.actor_index(engine);trainer=index.get(row['trainer_id'])
    if trainer is None:raise ValueError('actual Z Trainer required')
    W.require_actors(engine,trainer,pokemon)
    A._own(engine,trainer,pokemon)
    acquisition=acquired(trainer)
    if acquisition is None or acquisition['request_id']!=row['feature_acquisition']:
        raise ValueError('actual Full-Force Pose source permission required')
    _equipped(engine,trainer,row['ring_id'],(RING,POWER_RING))
    obj=_equipped(engine,pokemon,row['crystal_id'],(CRYSTAL,),held=True)
    crystal=obj.get('z_crystal');_signed(crystal)
    if crystal!=row['crystal'] or row['actor_id']!=pokemon.entity_id:
        raise ValueError('Z choice differs from its actual held crystal source')
    if (row['modification'],row['source_contract'])!=(crystal['modification'],crystal['source_contract']):
        raise ValueError('Z choice must use its contained modifier contract')
    if row['move_id'] not in A._known(engine.r,pokemon.spec):raise ValueError('Z crystal modifies an actually known Move')
    A._eligible(engine.r,row['move_id'],row['modification'],row['source_contract'])
    permanent=A.active(engine.r,pokemon.spec,row['move_id'])
    conflict=(permanent is not None and permanent['modification']==row['modification']
              and permanent['source_contract']!=row['source_contract'])
    selected=row.get('same_modifier_source')
    if conflict and selected not in ('signature','crystal'):
        raise ValueError('explicit same_modifier_source selection required for different modifier contracts')
    if not conflict and selected is not None:
        raise ValueError('same_modifier_source selection requires actual conflicting modifier contracts')
    return row


def arm(engine,trainer,pokemon,*,move_id,crystal_id,ring_id,request_id,same_modifier_source=None):
    """Choose as part of the next actual Move; native begin_move pays the quota."""
    import ace_trainer as A
    W.require_actors(engine,trainer,pokemon);G._text(request_id,'Z Move choice request')
    source(engine.r);acquisition=acquired(trainer)
    if acquisition is None:raise ValueError('actual Full-Force Pose source permission required')
    crystal=_object(engine,crystal_id,CRYSTAL).get('z_crystal');_signed(crystal)
    row=_sign({'id':request_id,'actor_id':pokemon.entity_id,'trainer_id':trainer.entity_id,
        'move_id':engine.r.move_id(move_id),'crystal_id':crystal_id,'ring_id':ring_id,
        'feature_acquisition':acquisition['request_id'],'crystal':deepcopy(crystal),
        'modification':crystal['modification'],'source_contract':crystal['source_contract'],
        'same_modifier_source':same_modifier_source})
    for old in pokemon.spec.get(HISTORY,[]):
        if old['choice']['id']==request_id:
            if old['choice']!=row:raise ValueError('Z request replay intent changed')
            return deepcopy(old)
    _current(engine,pokemon,row)
    old=pokemon.spec.get(CHOICE)
    if old and old.get('status')=='resolving':raise ValueError('finish the actual pending Z Move before replacing its choice')
    if not F.activation_allowed(pokemon,CRYSTAL,QUOTA,engine=engine):raise ValueError('Z crystal already used this scene')
    def apply(e,p):
        p.spec[CHOICE]={'status':'armed','choice':deepcopy(row)}
        return deepcopy(p.spec[CHOICE])
    return G.transition(engine,pokemon,apply)


def technique(engine,pokemon,move_id):
    state=pokemon.spec.get(CHOICE)
    if not state or state['status'] not in ('armed','resolving') or state['choice']['move_id']!=move_id:return None
    row=state['choice'];_signed(row)
    if state['status']=='armed':_current(engine,pokemon,row)
    if state['status']=='armed' and not F.activation_allowed(pokemon,CRYSTAL,QUOTA,engine=engine):
        raise ValueError('Z crystal already used this scene')
    if state['status']=='resolving':
        completion=getattr(engine,'_move_completions',{}).get(state['completion_id'])
        if completion is None or completion['actor'] is not pokemon or completion['move_id']!=move_id or completion['phase']=='complete':
            raise ValueError('Z modifier belongs only to its actual unfinished Move')
        # Once admitted, the actual Move owns its projection even if a hit
        # transfers equipment. Rechecking possession would undo that hit.
        if not any(r['choice']==row and r['completion_id']==completion['id'] for r in pokemon.spec.get(HISTORY,[])):
            raise ValueError('actual paid Z Move completion receipt required')
    return dict(deepcopy(row),z_crystal=True)


def interested(actor):
    state=getattr(actor,'spec',{}).get(CHOICE)
    return bool(state and state.get('status') in ('armed','resolving'))


def mega_ring(rules,item_id):
    if item_id!=POWER_RING:return False
    source(rules,POWER_RING)
    return rules._selected_rule(POWER_RING)==POWER_RING


def begin(engine,completion):
    marker=completion['move'].get(MARKER)
    if marker is None:return
    p=completion['actor'];state=p.spec.get(CHOICE)
    if not state or state['choice']['id']!=marker['investment_id']:raise ValueError('actual armed Z Move choice required')
    if state['status']=='resolving':
        if state['completion_id']!=completion['id']:raise ValueError('one Z choice cannot pay a second actual Move')
        return
    _current(engine,p,state['choice'])
    if not F.activation_allowed(p,CRYSTAL,QUOTA,engine=engine):raise ValueError('Z crystal already used this scene')
    F.consume_activation(p,CRYSTAL,QUOTA,engine=engine)
    state.update(status='resolving',completion_id=completion['id'])
    p.spec.setdefault(HISTORY,[]).append(_sign({'choice':deepcopy(state['choice']),
        'completion_id':completion['id'],'scene':F.state(p)['scene']}))


def finish(engine,completion):
    state=completion['actor'].spec.get(CHOICE)
    if state and state.get('completion_id')==completion['id']:state['status']='spent'


def historical(engine,pokemon,marker,move_id):
    rows=[r for r in pokemon.spec.get(HISTORY,[]) if r['choice']['id']==marker.get('investment_id')]
    if len(rows)!=1:
        row=technique(engine,pokemon,move_id)
        if row and row['id']==marker.get('investment_id'):return row
        raise ValueError('actual source-owned Z Move completion required')
    receipt=rows[0];_signed(receipt);row=receipt['choice'];_signed(row)
    if row['move_id']!=move_id:raise ValueError('Z completion Move source changed')
    return dict(deepcopy(row),z_crystal=True)


def validate_world(engine,index):
    for obj in getattr(engine,'_physical_objects',{}).values():
        if 'z_crystal' in obj:
            _signed(obj['z_crystal'])
            if obj.get('item_rule_id')!=CRYSTAL or obj['z_crystal']['instance_id']!=obj['id']:
                raise ValueError('Z modifier requires its exact original crystal')
            import ace_trainer as A
            source(engine.r)
            if obj['z_crystal']['source']!=SOURCE or obj['z_crystal']['modification'] not in A.MODIFICATIONS:
                raise ValueError('actual printed immutable crystal modifier source required')
            A.source(engine.r,obj['z_crystal']['source_contract'])
        if 'z_ring_combination' in obj:
            row=obj['z_ring_combination'];_signed(row);source(engine.r,POWER_RING)
            if obj.get('item_rule_id')!=POWER_RING or row['source']!=SOURCE or row['gm_decision'].get('allowed') is not True:
                raise ValueError('actual source-approved combined Z power ring required')
            parts=[getattr(engine,'_physical_objects',{}).get(uid) for uid in row['components']]
            if (len(parts)!=2 or any(p is None for p in parts) or
                    [p['item_rule_id'] for p in parts]!=[RING,'item/메가링'] or
                    any(p.get('consumed')!={'source':p['item_rule_id'],'by_actor_id':row['trainer_id'],'at':row['at']} for p in parts)):
                raise ValueError('combined ring requires its two actual archived components')
    for p in index.values():
        seen=set()
        for receipt in p.spec.get(HISTORY,[]):
            _signed(receipt);choice=receipt['choice'];_signed(choice);source(engine.r)
            if choice['actor_id']!=p.entity_id:raise ValueError('Z use belongs to its actual Pokemon')
            if choice['id'] in seen:raise ValueError('one Z choice cannot pay multiple native Moves')
            seen.add(choice['id'])
            completed=getattr(engine,'_move_completions',{}).get(receipt['completion_id'])
            if completed is None or completed['actor'] is not p or completed['move_id']!=choice['move_id']:
                raise ValueError('Z use requires its actual native Move completion')
            marker=completed['move'].get(MARKER)
            if marker!={k:choice[v] for k,v in (('investment_id','id'),('actor_id','actor_id'),('modification','modification'),('source_contract','source_contract'))}:
                raise ValueError('Z use and actual native projection authority disagree')
            trainer=index.get(choice['trainer_id'])
            import trainer_feature_acquisition as T
            if trainer is None or not any(r['static_acquisition']['feature_id']==FEATURE and
                    r['static_acquisition']['request_id']==choice['feature_acquisition'] for _,r,_ in T._static_records(trainer)):
                raise ValueError('Z use requires its actual Trainer acquisition history')
            if choice['crystal_id'] not in engine._physical_objects or choice['ring_id'] not in engine._physical_objects:
                raise ValueError('Z use requires its actual historical equipment identities')
            actual_crystal=engine._physical_objects[choice['crystal_id']]
            if (actual_crystal.get('item_rule_id')!=CRYSTAL or actual_crystal.get('z_crystal')!=choice['crystal'] or
                    (choice['modification'],choice['source_contract'])!=
                    (choice['crystal']['modification'],choice['crystal']['source_contract'])):
                raise ValueError('Z history cannot change the actual contained crystal modifier')
            if engine._physical_objects[choice['ring_id']].get('item_rule_id') not in (RING,POWER_RING):
                raise ValueError('Z history requires its actual ring rule identity')
        if CHOICE in p.spec:
            state=p.spec[CHOICE];_signed(state['choice'])
            if state['status'] not in ('armed','resolving','spent'):raise ValueError('actual Z choice lifecycle required')
            paid=[r for r in p.spec.get(HISTORY,[]) if r['choice']==state['choice']]
            if state['status']=='armed':
                if paid:raise ValueError('spent Z choice cannot be armed again')
            elif len(paid)!=1 or state.get('completion_id')!=paid[0]['completion_id']:
                raise ValueError('resolving or spent Z choice requires its actual paid completion')
    return True


def combine_rings(engine,trainer,*,zring_id,mega_ring_id,result_id,gm_decision,reason):
    """Archive both actual components; create one carried combined accessory."""
    import items as I, capability_actions as C, turn as TURN
    W.require_actors(engine,trainer);source(engine.r,POWER_RING);G._text(reason,'Z power ring combination reason')
    source(engine.r,RING)
    G._text(result_id,'new combined ring identity')
    if type(gm_decision) is not dict or set(gm_decision)!={'allowed','reason'} or gm_decision['allowed'] is not True:
        raise ValueError('actual GM approval required for Z power ring combination')
    G._text(gm_decision['reason'],'GM approval reason')
    if engine.encounter_active:raise ValueError('Z power ring combination requires an Extended Action outside combat')
    parts=[_object(engine,zring_id,RING),_object(engine,mega_ring_id,'item/메가링')]
    if result_id in W.entity_index(engine):raise ValueError('new combined ring identity already exists')
    if any(p.get('carrier_id')!=trainer.entity_id for p in parts):raise ValueError('own both actual carried ring components')
    def apply(e,t):
        if not TURN.spend(e,t,'extended',POWER_RING):raise ValueError('Z power ring Extended Action unavailable')
        for uid in (zring_id,mega_ring_id):
            for row in I.equipment_options(t,('장신구','held')):
                if row.get('instance_id')==uid:I._unregister_selected(e,t,row)
        carried=[r for r in t.spec['_carried_load']['objects'] if r['id'] not in (zring_id,mega_ring_id)]
        C.set_carried(e,t,carried,reason)
        for uid in (zring_id,mega_ring_id):
            obj=e._physical_objects[uid]
            W.finish_physical_use(e,obj,'consumed',{'source':obj['item_rule_id'],'by_actor_id':t.entity_id,'at':e.elapsed_seconds})
        weight=sum(e._physical_objects[u]['weight_kg'] for u in (zring_id,mega_ring_id))
        W.register_object(e,result_id,location={'kind':'unknown'},reason=reason,weight_kg=weight,
            kind='item_instance',item_rule_id=POWER_RING,owner_id=t.entity_id,source='input/hb-zmoves.md:8')
        result=e._physical_objects[result_id]
        result['z_ring_combination']=_sign({'components':[zring_id,mega_ring_id],'gm_decision':deepcopy(gm_decision),
            'source':deepcopy(SOURCE),'trainer_id':t.entity_id,'at':e.elapsed_seconds})
        C.set_carried(e,t,carried+[{'id':result_id,'weight_kg':weight}],reason)
        return deepcopy(result)
    return G.transition(engine,trainer,apply)
