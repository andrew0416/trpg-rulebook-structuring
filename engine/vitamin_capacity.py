"""Dietician changes new-dose eligibility; consumed Vitamins remain permanent.

Current owner contributions and historical application evidence are separate.
An old seven-slot entitlement never authorizes a new application after it ends.
"""
from copy import deepcopy
DIETICIAN='feat/영양사'
CHEF='class/요리사'
HISTORY='vitamin_capacity_history'
ALIASES=(DIETICIAN,'영양사','Dietician')


def current(rules,spec):
    sources=[]
    for key,row in spec.get('state_grants',{}).get('sources',{}).items():
        policy=row.get('vitamin_capacity_policy')
        if policy is None:continue
        if policy!={'rule_id':DIETICIAN,'maximum':7} or type(policy.get('maximum'))is not int or row.get('kind')!='feature' or row.get('rule_id')!=DIETICIAN or row.get('lifetime')!='your_pokemon' or rules._selected_rule(DIETICIAN)!=DIETICIAN:
            raise ValueError('actual selected Dietician capacity source required')
        if not spec.get('trainer_id') or row.get('owner_id')!=spec['trainer_id'] or key!='feature:'+row['owner_id']+':'+DIETICIAN:
            raise ValueError('Dietician capacity requires the current actual owner')
        sources.append({'source_id':key,'rule_id':DIETICIAN,'owner_id':row['owner_id']})
    if len(sources)>1:raise ValueError('duplicate Dietician registrations do not stack')
    return {'capacity':7 if sources else 5,'capacity_sources':sources}


def historical_limit(rules,spec):
    rows=spec.get(HISTORY,[])
    if not isinstance(rows,list):raise ValueError('Vitamin eligibility history must be a list')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('rule_id')!=DIETICIAN or row.get('maximum')!=7 or type(row.get('maximum'))is not int or row.get('pokemon_id')!=spec.get('id') or rules._selected_rule(DIETICIAN)!=DIETICIAN:
            raise ValueError('historical Vitamin eligibility must preserve the actual recipient and source')
        if not isinstance(row.get('owner_id'),str) or not row['owner_id'] or row.get('source_id')!='feature:'+row['owner_id']+':'+DIETICIAN:
            raise ValueError('historical Dietician owner identity required')
        kind=row.get('kind');identity=row.get('application_id')
        if kind=='vitamin':
            if type(identity)is not int or not 1<=identity<=len(spec.get('vitamins',[])) or row.get('item')!=spec['vitamins'][identity-1]:
                raise ValueError('historical eligibility must identify a retained actual Vitamin dose')
        elif kind=='vm':
            if not isinstance(identity,str) or not identity or not any(x.get('method')=='vm' and x.get('application_id')==identity and x.get('move_id')==row.get('move_id') for x in spec.get('move_learning_log',[]) if isinstance(x,dict)):
                raise ValueError('historical eligibility must identify the actual VM application')
        else:raise ValueError('unknown Vitamin eligibility application')
        key=(kind,identity)
        if key in seen:raise ValueError('duplicate Vitamin eligibility application')
        seen.add(key)
    return 7 if rows else 5


def record(rules,spec,kind,identity,**details):
    state=current(rules,spec)
    if not state['capacity_sources']:return
    row={**state['capacity_sources'][0],'maximum':7,'pokemon_id':spec['id'],'kind':kind,'application_id':identity,**details}
    rows=spec.setdefault(HISTORY,[])
    existing=next((x for x in rows if (x.get('kind'),x.get('application_id'))==(kind,identity)),None)
    if existing is not None:
        if existing!=row:raise ValueError('Vitamin application cannot change its original capacity source')
        return
    rows.append(row)


def acquisition_evidence(engine,owner):
    from acquired_features import _names,_resolve
    names=_names(owner,'feat/')
    if owner.kind!='trainer' or DIETICIAN not in {_resolve(owner,v,'feat/',names) for v in owner.spec.get('feats',[]) if v in names}:
        raise ValueError('actual acquired Dietician required')
    if engine.r._selected_rule(DIETICIAN)!=DIETICIAN:raise ValueError('selected Dietician source required')
    acquisition=owner.spec.get('dietician_acquisition')
    if acquisition is None:
        from pokemon_teaching import _acquired_feature
        if not _acquired_feature(owner,CHEF):
            raise ValueError('Dietician requires acquired Chef')
        import skill_modifiers as SKILLS
        rank=SKILLS.effective_rank(engine.r,owner,'직감')
        if rank<5:raise ValueError('Dietician requires Expert Intuition at acquisition')
        acquisition={'source':DIETICIAN,'trainer_id':owner.entity_id,'class_source':CHEF,'intuition_rank':rank}
    elif not isinstance(acquisition,dict) or acquisition.get('source')!=DIETICIAN or acquisition.get('trainer_id')!=owner.entity_id or acquisition.get('class_source')!=CHEF or type(acquisition.get('intuition_rank'))is not int or not 5<=acquisition['intuition_rank']<=6:
        raise ValueError('invalid Dietician acquisition evidence')
    return deepcopy(acquisition)


def register(engine,owner,name,targets=None):
    if name not in ALIASES:return False
    acquisition=acquisition_evidence(engine,owner)
    import world_entities as WORLD,state_grants as G
    actors=WORLD.actor_index(engine,[owner])
    if actors.get(owner.entity_id)is not owner:raise ValueError('actual registered Dietician required')
    targets=[c for c in actors.values() if c.kind=='pokemon' and c.spec.get('trainer_id')==owner.entity_id] if targets is None else list(targets)
    if len({id(c) for c in targets})!=len(targets):raise ValueError('Dietician targets must be distinct')
    if any(actors.get(c.entity_id)is not c or c.kind!='pokemon' or c.spec.get('trainer_id')!=owner.entity_id for c in targets):
        raise ValueError('Dietician targets must be your actual Pokemon')
    def apply(e,trainer,*pokemon):
        trainer.spec['dietician_acquisition']=deepcopy(acquisition)
        key='feature:'+trainer.entity_id+':'+DIETICIAN
        for c in pokemon:
            row=G._source(c,key,'feature',owner_id=trainer.entity_id,lifetime='your_pokemon',rule_id=DIETICIAN,tutor_points=0)
            row['vitamin_capacity_policy']={'rule_id':DIETICIAN,'maximum':7}
            current(e.r,c.spec)
    G.transition(engine,owner,apply,participants=tuple(targets))
    return True


def owns(owner):
    return owner.kind=='trainer' and any(name in ALIASES for name in owner.spec.get('feats',[]))


def sync_source_end(engine,owner):
    if owns(owner):return
    import world_entities as WORLD,state_grants as G
    key='feature:'+owner.entity_id+':'+DIETICIAN
    targets=[c for c in WORLD.actors(engine) if key in c.spec.get(G.KEY,{}).get('sources',{})]
    if not targets:return
    def apply(e,trainer,*pokemon):
        for c in pokemon:G.revoke(c,key,engine=e)
    G.transition(engine,owner,apply,participants=tuple(targets))


def prepare_transfer(engine,target,new_owner):
    # Pure preflight: an invalid new owner's acquisition cannot half-transfer.
    return acquisition_evidence(engine,new_owner) if owns(new_owner) else None


def commit_transfer(engine,target,new_owner,acquisition):
    if acquisition is None:return
    import state_grants as G
    new_owner.spec['dietician_acquisition']=deepcopy(acquisition)
    key='feature:'+new_owner.entity_id+':'+DIETICIAN
    row=G._source(target,key,'feature',owner_id=new_owner.entity_id,lifetime='your_pokemon',rule_id=DIETICIAN,tutor_points=0)
    row['vitamin_capacity_policy']={'rule_id':DIETICIAN,'maximum':7}


def register_current_owner(engine,target):
    if target.kind!='pokemon':return
    import world_entities as WORLD
    owner=WORLD.actor_index(engine,[target]).get(target.spec.get('trainer_id'))
    if owner is not None and owns(owner):
        commit_transfer(engine,target,owner,acquisition_evidence(engine,owner))


def validate_world(engine,actors):
    for target in actors.values():
        if target.kind!='pokemon':continue
        for source in current(engine.r,target.spec)['capacity_sources']:
            owner=actors.get(source['owner_id'])
            if owner is None or not owns(owner):raise ValueError('current Dietician source lacks its actual acquired owner')
            acquisition_evidence(engine,owner)
