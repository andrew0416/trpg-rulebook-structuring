"""Ability Mastery delegates effect ownership and withdrawal to state_grants."""
import state_fields as F,state_grants as G
import ability_transitions as A
from builder import species_lookup

SOURCE='poke_edge/특성-숙달'
ALIASES={SOURCE:SOURCE,'특성 숙달':SOURCE,'Ability Mastery':SOURCE}


def choice(rules,value):
    if type(value)is not str or not value:raise ValueError('explicit actual Ability choice required')
    uid=A.ability_id(rules,value)
    if type(uid)is not str or rules._selected_rule(uid)!=uid:raise ValueError('selected actual Ability source required')
    rules.selection.require_supported_version(uid)
    return uid


def candidates(rules,spec):
    import growth_milestones as M
    from ruleset import UnresolvedRuleSelection
    result=[]
    for name in M.natural_abilities(rules,spec):
        try:uid=choice(rules,name)
        except (UnresolvedRuleSelection,KeyError):continue
        if uid not in result:result.append(uid)
    return result


def records(spec):
    rows=spec.get('learned_poke_edges',[])
    if type(rows)is not list or any(type(row)is not dict for row in rows):raise ValueError('actual Poke Edge receipts required')
    return [row for row in rows if row.get('source')==SOURCE]


def checked(rules,spec,*,allow_lost=False):
    rows=records(spec)
    if not rows:
        if any(row.get('rule_id')==SOURCE for row in spec.get(G.KEY,{}).get('sources',{}).values()):
            raise ValueError('Ability Mastery grant requires its actual acquisition receipt')
        return []
    import poke_edge_variants as V,downtime as D
    definition=V.resolve(rules,SOURCE)
    if spec.get('kind')!='pokemon' or definition is None or definition['field']!='ability':raise ValueError('selected Pokemon Ability Mastery source required')
    ids=set();active=0
    sources=spec.get(G.KEY,{}).get('sources',{})
    for row in rows:
        V.validate_receipt(rules,row)
        if row.get('definition_origin')!={k:definition[k] for k in ('clause_id','rule_id','record')}:raise ValueError('actual Ability Mastery definition receipt required')
        F.integer(row.get('point_cost'),'Ability Mastery TP',3,3)
        F.integer(row.get('acquired_level'),'historical Ability Mastery level',60,100)
        if type(row.get('trainer_id'))is not str or not row['trainer_id']:raise ValueError('actual historical Ability Mastery teacher required')
        uid=choice(rules,row.get('ability'));species=species_lookup(rules,row.get('origin_species'))['id']
        if uid!=row['ability'] or uid not in candidates(rules,dict(spec,species=species,abilities=[])):raise ValueError('actual naturally acquirable historical Ability required')
        key=row.get('grant_source')
        if type(key)is not str or not key.startswith(SOURCE+':') or key in ids:raise ValueError('distinct Ability Mastery grant identity required')
        ids.add(key)
        history=row.get('ability_evolutions')
        if type(history)is not list:raise ValueError('explicit Ability evolution history required')
        for step in history:
            if type(step)is not dict or set(step)!={'from_species','to_species','from_ability','to_ability'} or step['from_species']!=species or step['from_ability']!=uid:raise ValueError('Ability evolution provenance mismatch')
            next_species=species_lookup(rules,step['to_species'])['id']
            expected=D.evolved_abilities(rules,[A.label(rules,uid)],species_lookup(rules,species),species_lookup(rules,next_species),[])[0]
            uid=choice(rules,expected);species=next_species
            if step['to_ability']!=uid:raise ValueError('Ability evolution must use native slot mapping')
        if row.get('current_ability')!=uid:raise ValueError('current Ability Mastery identity mismatch')
        grant=sources.get(key)
        if row.get('status')=='active':
            active+=1
            if species!=spec['species']:raise ValueError('native Ability Mastery evolution update required')
            if not allow_lost and spec['level']<60:raise ValueError('lost level60 prerequisite requires Ability Mastery refund')
            expected={'kind':'poke_edge','owner_id':spec['id'],'lifetime':'while_prerequisites','rule_id':SOURCE,'tutor_points':3,'grants':{'abilities':[A.label(rules,uid)]}}
            if grant!=expected:raise ValueError('actual source-owned Ability Mastery grant required')
        elif row.get('status')=='refunded':
            refund=row.get('refund',{})
            if grant is not None or refund.get('source')!='input/ch05-pokemon.md:274' or refund.get('points')!=3 or not refund.get('reason'):raise ValueError('actual one-time Ability Mastery refund required')
        else:raise ValueError('explicit Ability Mastery lifetime required')
    if active>1:raise ValueError('one active Ability Mastery acquisition permitted')
    if any(row.get('rule_id')==SOURCE and key not in ids for key,row in sources.items()):raise ValueError('Ability Mastery grant requires its actual acquisition receipt')
    return rows


def validate(actor,*,allow_lost=False):
    checked(actor.r,actor.spec,allow_lost=allow_lost)


def reconcile(engine,actor,*,reason):
    rows=checked(actor.r,actor.spec,allow_lost=True)
    if actor.spec['level']>=60:return
    ending=[row for row in rows if row['status']=='active']
    if ending:F.integer(actor.spec.get('tutor_points'),'actual Ability Mastery refund balance',0)
    for row in ending:
        G.revoke(actor,row['grant_source'],engine=engine)
    if ending:
        import acquisition_withdrawal as W
        W.refund_native_investments(actor.spec,ending,source='input/ch05-pokemon.md:274',reason=reason,
            lost_prerequisite={'minimum_level':60,'actual_level':actor.spec['level']})
    validate(actor)


def evolve_spec(rules,spec,old_species,new_species,log):
    rows=checked(rules,dict(spec,species=old_species['id']))
    import downtime as D
    for row in rows:
        if row['status']!='active':continue
        before=row['current_ability']
        after=D.evolved_abilities(rules,[A.label(rules,before)],old_species,new_species,log)[0]
        uid=choice(rules,after)
        row['ability_evolutions'].append({'from_species':old_species['id'],'to_species':new_species['id'],'from_ability':before,'to_ability':uid})
        row['current_ability']=uid
        spec[G.KEY]['sources'][row['grant_source']]['grants']['abilities']=[A.label(rules,uid)]
    checked(rules,spec)


def teach(engine,owner,target,definition,selected,*,from_grooming=False,from_training=False,safe=None):
    import pokemon_teaching as T
    T._pokemon(engine,owner,target);T.source(engine.r,SOURCE,T.POINTS);validate(target)
    if target.level<60:raise ValueError('Ability Mastery requires actual level60')
    rows=records(target.spec)
    if any(row['status']=='active' for row in rows):raise ValueError('Ability Mastery already acquired')
    uid=choice(engine.r,selected)
    if uid not in candidates(engine.r,target.spec):raise ValueError('Ability Mastery must choose a naturally acquirable Ability')
    if any(A.ability_id(engine.r,name)==uid for name in G.effective(target,'abilities',include_suppressed=True)):raise ValueError('chosen Ability already owned')
    if T._balance(target.spec)<3:raise ValueError('Ability Mastery costs three actual Tutor Points')
    if T.credit_mode(from_grooming,from_training):T.training_credit(engine,owner,target,SOURCE,from_training=from_training)
    else:T.edge_training_hour(engine,owner,target,SOURCE,SOURCE,safe=safe)
    if target.level<60 or uid not in candidates(engine.r,target.spec):raise ValueError('actual qualification must survive the completed Ability Mastery hour')
    if any(A.ability_id(engine.r,name)==uid for name in G.effective(target,'abilities',include_suppressed=True)):raise ValueError('chosen Ability became owned during the teaching hour')
    key=SOURCE+':'+str(len(rows)+1)
    target.spec.setdefault('learned_poke_edges',[]).append({'source':SOURCE,'status':'active','ability':uid,'current_ability':uid,
        'origin_species':target.spec['species'],'ability_evolutions':[],'grant_source':key,
        'point_cost':3,'trainer_id':owner.entity_id,'acquired_level':target.level,'completed_at':engine.elapsed_seconds,
        'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274',
        'definition_origin':{k:definition[k] for k in ('clause_id','rule_id','record')}})
    G.grant(target,'abilities',A.label(engine.r,uid),key,'poke_edge',owner_id=target.entity_id,lifetime='while_prerequisites',rule_id=SOURCE,tutor_points=3)
    G.reconcile(engine,target)
    T._debit_points(target.spec,3)
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,SOURCE,from_training=from_training)
    validate(target)
    return {'activity':'teach_edge','edge':SOURCE,'ability':uid,'point_cost':3,'seconds':0 if (from_grooming or from_training) else 3600}
