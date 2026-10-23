"""Owned fossil restoration with declared materials, work and native birth."""
from copy import deepcopy
import common_checks as C,crafting_recipes as Q,world_entities as W,resolution_transaction as TX

SOURCE='edge/고생물학자'
CONTRACT='fossil_creation_contract'
BIRTH='fossil_birth_policy'
RECORDS='fossil_creation_records'


def birth_policy(value):
    Q._fields(value,('level','tutor_points','seconds'))
    C.integer(value['level'],'fossil birth level',1,100);C.integer(value['tutor_points'],'fossil initial Tutor Points',0)
    if value['seconds'] is not None:C.integer(value['seconds'],'fossil hatch waiting seconds',0)
    return deepcopy(value)


def declaration(value):
    Q._fields(value,('id','source','requirements','machine','materials','seconds','species','hatch'))
    Q._text(value['id']);Q._text(value['source']);C.integer(value['seconds'],'fossil restoration seconds',0)
    if type(value['requirements']) is not list or not value['requirements']:raise ValueError('explicit fossil restoration permission required')
    identities=set()
    for row in value['requirements']:
        Q._fields(row,('id','condition','reason'));Q._text(row['id']);Q._text(row['reason']);Q._condition(row['condition'])
        if row['id'] in identities:raise ValueError('distinct fossil permission identities required')
        identities.add(row['id'])
    machine=value['machine']
    if type(machine) is dict and machine.get('kind')=='native_restoration_machine':
        Q._fields(machine,('kind',))
        if value['source']!=SOURCE:raise ValueError('native machine family belongs to Paleontologist only')
    else:
        Q._condition(machine)
        if machine['kind']!='tool':raise ValueError('actual selected restoration tool required')
    Q.material_groups(value['materials']);Q._fields(value['species'],('allowed','allow_gm_other'))
    if type(value['species']['allowed']) is not list or type(value['species']['allow_gm_other']) is not bool:raise ValueError('explicit fossil species authority required')
    for uid in value['species']['allowed']:Q._text(uid)
    birth_policy(value['hatch'])
    return deepcopy(value)


def native():
    import pokemon_entities as P
    return {'id':'native-fossil-restoration','source':SOURCE,'requirements':[
        {'id':'acquired','condition':{'kind':'owned','fields':['edges'],'names':[SOURCE,'고생물학자','Paleontologist']},'reason':'acquired Paleontologist required'},
        {'id':'rank','condition':{'kind':'any','conditions':[{'kind':'skill','skill':s,'rank':3,'effective':False} for s in ('포켓몬학','생존')]},'reason':'actual Paleontologist prerequisite required'}],
        'machine':{'kind':'native_restoration_machine'},'materials':[],'seconds':0,
        'species':{'allowed':['pokemon/'+name for name in P.STANDARD_FOSSIL_SPECIES],'allow_gm_other':True},
        'hatch':{'level':10,'tutor_points':1,'seconds':None}}


def _machine(engine,owner,node,sources):
    if node['kind']!='native_restoration_machine':
        if not Q._observe(engine,owner,node,sources):raise ValueError('actual permitted restoration machine is not accessible')
        return {'policy':deepcopy(node),'observed_access':True}
    # ch05:748 explicitly permits both named machines. The portable name has
    # no separate extracted item definition; never invent a catalog identity.
    Q._selected(engine,'item/복원기');sources.add('item/복원기')
    names=('복원기','휴대용 복원기','Reanimation Machine','Portable Reanimation Machine')
    for name in names:
        if name in owner.spec.get('damaged_items',[]):continue
        if C.integer(owner.spec.get('items',{}).get(name,0),'actual restoration machine count',0):
            return {'name':name,'access':'inventory','authority':SOURCE}
        if name in owner.spec.get('accessible_equipment',[]):return {'name':name,'access':'accessible_equipment','authority':SOURCE}
    raise ValueError('actual permitted restoration machine is not accessible')


def prepare(engine,owner,fossil_entity_id,value,*,inputs=None,gm_species_approved=None,reason):
    import pokemon_entities as P,pokemon_activities as A
    W.require_actors(engine,owner);A._trainer(owner);A._outside(engine);Q._text(reason)
    value=declaration(value);Q._selected(engine,value['source']);entry=P.fossil_index(engine).get(fossil_entity_id)
    if entry is None or entry[0] is not owner or entry[1]['status']!='fossil':raise ValueError('actual unconsumed owned fossil required')
    fossil=entry[1];sources={value['source']}
    for row in value['requirements']:
        if not Q._observe(engine,owner,row['condition'],sources):raise ValueError(row['reason'])
    machine=_machine(engine,owner,value['machine'],sources)
    from builder import species_lookup
    allowed=[species_lookup(engine.r,uid)['id'] for uid in value['species']['allowed']]
    if fossil['species'] not in allowed:
        if not value['species']['allow_gm_other'] or type(gm_species_approved) is not bool or not gm_species_approved:
            raise ValueError('explicit GM-approved nonstandard fossil species required')
    material_plan=Q.prepare_materials(engine,owner,value['materials'],inputs=inputs);sources.update(material_plan['sources'])
    return {'declaration':value,'provider_id':owner.entity_id,'fossil_entity_id':fossil_entity_id,'species':fossil['species'],
        'species_basis':fossil['species_basis'],'machine':machine,'payments':material_plan['payments'],'sources':sorted(sources)}


def _perform(engine,owner,fossil_entity_id,value,*,request_id,inputs=None,gm_species_approved=None,reason,hatch_details=None):
    import pokemon_entities as P,activity_jobs as J
    value=declaration(value);Q._text(request_id);Q._text(reason);Q._selected(engine,value['source'])
    if hatch_details is not None and type(hatch_details) is not dict:raise ValueError('GM hatch details must be a mapping')
    request={'request_id':request_id,'provider_id':owner.entity_id,'fossil_entity_id':fossil_entity_id,'declaration':value,
        'inputs':deepcopy(inputs),'gm_species_approved':gm_species_approved,'reason':reason,'hatch_details':deepcopy(hatch_details)}
    intent=TX.request_fingerprint(request);records=owner.spec.get(RECORDS,{})
    if request_id in records:
        prior=records[request_id]
        if prior['intent']!=intent:raise ValueError('cannot replace a completed fossil restoration request')
        entry=P.egg_index(engine).get(prior['egg_entity_id'])
        if entry is None:raise ValueError('actual original restored egg required for replay')
        return {'activity':'fossil','phase':'restore','egg':deepcopy(entry[1]),'replayed':True}
    plan=prepare(engine,owner,fossil_entity_id,value,inputs=inputs,gm_species_approved=gm_species_approved,reason=reason)
    fossil=P.fossil_index(engine)[fossil_entity_id][1];job_id=None
    if value['seconds']:
        job_id=J.run_fixed(engine,owner,(),seconds=value['seconds'],source=value['source'],
            job_id='fossil-restoration:'+owner.entity_id+':'+request_id,context={'fossil_entity_id':fossil_entity_id,'reason':reason})['job_id']
    confirmed=prepare(engine,owner,fossil_entity_id,value,inputs=inputs,gm_species_approved=gm_species_approved,reason=reason)
    if confirmed!=plan:raise ValueError('actual restoration qualification or material plan changed during work')
    paid=Q.pay_materials(engine,owner,plan['payments'])
    egg=P.prepare_egg(engine,owner,{'id':'fossil/'+fossil['id'],'fossil_id':fossil['id'],'fossil_entity_id':fossil_entity_id,
        'restored_by':owner.entity_id,'species':fossil['species'],'source':value['source'],'hatched':False,'hatch_level':value['hatch']['level'],
        'produced_at':engine.elapsed_seconds,'gm_hatch_details':deepcopy(hatch_details),'special_appearance':'GM decision pending',BIRTH:deepcopy(value['hatch'])})
    receipt={'request':request,'intent':intent,'plan':plan,'plan_sha256':TX.request_fingerprint(plan),'payments':paid,
        'payments_sha256':TX.request_fingerprint(paid),'job_id':job_id,'produced_at':engine.elapsed_seconds}
    fossil.update(status='restored_to_egg',egg_entity_id=egg['entity_id'],restored_by=owner.entity_id)
    fossil[CONTRACT]=receipt;owner.spec.setdefault('eggs',[]).append(egg)
    owner.spec.setdefault(RECORDS,{})[request_id]={'intent':intent,'egg_entity_id':egg['entity_id'],'fossil_entity_id':fossil_entity_id}
    return {'activity':'fossil','phase':'restore','egg':deepcopy(egg),'replayed':False}


def restore(engine,owner,fossil_entity_id,value,**options):
    import state_grants as G
    W.require_actors(engine,owner)
    return G.transition(engine,owner,lambda e,a:_perform(e,a,fossil_entity_id,value,**options))


def restore_native(engine,owner,*,fossil_id,hatch_details=None,**roll):
    import state_grants as G,pokemon_entities as P,pokemon_activities as A
    if roll:raise ValueError('restoration has no sourced skill roll')
    def apply(e,a):
        A._feature(e,a,'paleontologist');record=a.spec.get('fossils',{}).get(fossil_id)
        if not record or record.get('status')!='fossil':raise ValueError('unconsumed owned fossil instance required')
        planned=P.prepare_fossil(e,a,fossil_id,record);record.clear();record.update(planned)
        import researcher_fields as RESEARCH
        value=RESEARCH.fossil_restoration_declaration(e,a,fossil_id,native())
        result=_perform(e,a,record['entity_id'],value,request_id='native:'+record['entity_id'],
            gm_species_approved=record['species_basis']=='GM_nonstandard_fossil',reason='existing GM-observed fossil restoration',hatch_details=hatch_details)
        RESEARCH.fossil_restoration_mark(e,a,fossil_id,P.egg_index(e)[result['egg']['entity_id']][1])
        return result
    return G.transition(engine,owner,apply)


def validate_fossil(engine,row):
    if CONTRACT not in row:return
    record=row[CONTRACT];request=record['request'];plan=record['plan'];value=declaration(request['declaration'])
    if record['intent']!=TX.request_fingerprint(request) or record['plan_sha256']!=TX.request_fingerprint(plan) or record['payments_sha256']!=TX.request_fingerprint(record['payments']):
        raise ValueError('fossil restoration evidence changed')
    if row['status']=='fossil' or request['fossil_entity_id']!=row['entity_id'] or plan['fossil_entity_id']!=row['entity_id'] or plan['provider_id']!=row['restored_by'] or request['provider_id']!=row['restored_by'] or plan['species']!=row['species'] or plan['species_basis']!=row['species_basis'] or plan['declaration']!=value:
        raise ValueError('actual fossil restoration provenance changed')
    for source in plan['sources']:Q._selected(engine,source)
    C.integer(record['produced_at'],'actual fossil egg production time',0)


def validate_egg(row):
    if BIRTH not in row:return
    policy=birth_policy(row[BIRTH])
    if row.get('fossil_entity_id') is None or row['hatch_level']!=policy['level']:raise ValueError('fossil birth declaration disagrees with actual egg')


def validate_world(engine,fossils,eggs,actors):
    import activity_jobs as J
    for _,egg in eggs.values():
        if BIRTH in egg:
            entry=fossils.get(egg.get('fossil_entity_id'))
            if entry is None or CONTRACT not in entry[1]:raise ValueError('fossil birth policy requires actual declared restoration evidence')
    for uid,(_,fossil) in fossils.items():
        if CONTRACT not in fossil:continue
        validate_fossil(engine,fossil);record=fossil[CONTRACT];plan=record['plan'];value=plan['declaration']
        egg=eggs[fossil['egg_entity_id']][1];validate_egg(egg)
        if egg.get(BIRTH)!=value['hatch'] or egg['source']!=value['source'] or egg.get('produced_at')!=record['produced_at'] or egg.get('parents'):
            raise ValueError('fossil/egg source, birth policy or production time changed')
        provider=actors[plan['provider_id']];prior=provider.spec.get(RECORDS,{}).get(record['request']['request_id'])
        if prior!={'intent':record['intent'],'egg_entity_id':egg['entity_id'],'fossil_entity_id':uid}:raise ValueError('actual fossil producer replay receipt changed')
        if record['job_id'] is not None:
            job=J._row(engine,record['job_id'])
            if job['status']!='complete' or job['owner'].entity_id!=plan['provider_id'] or job['participants'] or job['progress_seconds']!=value['seconds'] or job['end_seconds']!=record['produced_at']:
                raise ValueError('actual completed fossil restoration work required')
        if fossil['status']=='hatched':
            child=actors[fossil['pokemon_id']]
            if child.spec.get('egg_entity_id')!=egg['entity_id']:raise ValueError('actual child lost fossil egg provenance')


def _hatch(engine,owner,egg,*,name,ready,reason,details):
    import pokemon_entities as P,pokemon_activities as A,creation_egg as E,pokemon_party as PARTY
    W.require_actors(engine,owner);A._trainer(owner);A._outside(engine);Q._text(reason)
    if egg['owner_id']!=owner.entity_id or egg['hatched']:raise ValueError('actual owned unhatched fossil egg required')
    fossil=P.egg_fossil(engine,egg)
    if fossil['status']!='restored_to_egg':raise ValueError('actual restored fossil producer required')
    policy=egg.get(BIRTH,{'level':10,'tutor_points':1,'seconds':None});birth_policy(policy)
    details=__import__('researcher_fields').fossil_birth_details(engine,owner,egg,details)
    if policy['seconds'] is None:
        if type(ready) is not bool or not ready:raise ValueError('GM must establish that this fossil egg is ready to hatch')
    elif E.hatch_remaining(engine,egg,policy['seconds']):raise ValueError('declared fossil hatch waiting time has not elapsed')
    pokemon,selected=E.construct(engine,owner,egg,name=name,birth_level=policy['level'],tutor_points=policy['tutor_points'],selected=details,
        extra={'fossil_egg_id':egg['id'],'fossil_egg_entity_id':egg['entity_id'],'fossil_entity_id':fossil['entity_id']})
    placement=PARTY.preflight_hatch(engine,owner,pokemon,egg)
    fossil.update(status='hatched',pokemon_id=pokemon.entity_id);E.commit_birth(engine,owner,egg,pokemon,selected,reason=reason,placement=placement)
    return {'activity':'hatch_fossil','pokemon':pokemon,'egg_id':egg['id']}


def hatch(engine,owner,egg_entity_id,*,name,ready=None,reason,details):
    import state_grants as G,pokemon_entities as P
    W.require_actors(engine,owner)
    def apply(e,a):
        entry=P.egg_index(e).get(egg_entity_id)
        if entry is None or entry[0] is not a:raise ValueError('actual owned fossil egg required')
        return _hatch(e,a,entry[1],name=name,ready=ready,reason=reason,details=details)
    return G.transition(engine,owner,apply)
