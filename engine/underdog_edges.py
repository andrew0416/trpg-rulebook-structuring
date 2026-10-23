"""Underdog sources separate species bases, ordinary investment and bonus points."""
from copy import deepcopy
from types import SimpleNamespace
import state_fields as F
import state_grants as G
import skill_modifiers as S
STRENGTH='poke_edge/약골의-힘'
POTENTIAL='poke_edge/잠재력-발견'
HOMEBREW='poke_edge/잠재력-발견-1'
SOURCES=(STRENGTH,POTENTIAL,HOMEBREW)
ALIASES={'Underdog’s Strength':STRENGTH,"Underdog's Strength":STRENGTH,'Realized Potential':POTENTIAL,'Realized Potential [Homebrew]':HOMEBREW}


def records(spec):
    rows=spec.get('learned_poke_edges',[])
    if not isinstance(rows,list) or any(type(r) is not dict for r in rows):raise ValueError('Poke Edge records required')
    return [r for r in rows if r.get('source') in SOURCES]


def owned(actor):
    return bool({S.key(x) for x in ('약골','Underdog','capability/약골')} & {S.key(x) for x in G.effective_capabilities(actor,only=('약골','Underdog'))})


def definition(rules,source):
    import poke_edge_variants as V
    row=V.resolve(rules,source)
    if row is None or row.get('policy') not in SOURCES or row.get('underdog_kind') not in ('base','points'):
        raise ValueError('actual selected Underdog source declaration required')
    F.integer(row.get('minimum_level'),'Underdog minimum level',1,100)
    F.integer(row.get('tutor_cost'),'Underdog declared TP',1)
    if row['policy']==STRENGTH and row.get('base_bonus')!=1:raise ValueError('reviewed Underdog Strength base contribution required')
    return row


def growth_choice(value):
    if type(value) is not dict or not value:raise ValueError('explicit complete bonus investment required')
    def checked(row):
        if type(row) is not dict or set(row)!=set(F.STATS):raise ValueError('complete bonus investment per stat required')
        for number in row.values():F.integer(number,'bonus point investment')
        return deepcopy(row)
    if set(value)==set(F.STATS):return checked(value)
    if any(type(key) is not str or not key for key in value):raise ValueError('named bonus investments required')
    return {name:checked(row) for name,row in value.items()}


def species_points(rules,species):
    from builder import species_lookup
    return 45-sum(species_lookup(rules,species)['base_stats'].values())


def check_bonus_budget(values,budget):
    growth_choice(values)
    if sum(values.values())!=budget:raise ValueError('source bonus investment budget mismatch')
    if any(value<0 if budget>=0 else value>0 for value in values.values()):
        raise ValueError('bonus investment cannot redistribute ordinary growth points')


def bonus_policy(rules,spec,source,decision=None,*,species=None):
    import json
    from pathlib import Path
    from builder import species_lookup
    config=definition(rules,source);source=config['policy']
    if config['underdog_kind']!='points':raise ValueError('actual Realized Potential source required')
    document=json.loads((Path(rules.root)/'data/underdog-negative-bonus-policy.json').read_text(encoding='utf-8'))
    variant=document['variants'][0];variant['rule_id']=source
    chosen=species_lookup(rules,species or spec['species'])['id']
    variant['values']['binding']={'actor_id':spec['id'],'species':chosen,'raw_points':species_points(rules,chosen)}
    return rules.resolve_source_policy(document,decisions={} if decision is None else {'negative_policy':decision})


def resolved_budget(rules,spec,source,decision=None,*,species=None):
    raw=species_points(rules,species or spec['species'])
    if raw>=0:
        if decision is not None:raise ValueError('negative-bonus interpretation applies only to an actual negative formula')
        return raw,None
    result=bonus_policy(rules,spec,source,decision,species=species)
    if result['status']!='PolicyValuesReady':raise ValueError('negative Underdog bonus requires the explicit scoped decision from underdog_bonus_policy()')
    selected=result['values']['selected']
    if selected=='unavailable':raise ValueError('selected negative-bonus interpretation does not permit this Edge')
    return (raw if selected=='signed_points' else 0),result


def source_rows(rules,spec):
    rows=records(spec)
    if not rows:return []
    import poke_edge_variants as V
    if spec.get('kind')!='pokemon':raise ValueError('actual Pokemon Underdog investment required')
    active=[]
    for row in rows:
        config=definition(rules,row['source']);V.validate_receipt(rules,row)
        origin=row.get('definition_origin')
        if type(origin) is not dict or origin.get('clause_id')!=config['clause_id']:raise ValueError('actual selected Underdog source receipt required')
        F.integer(row.get('point_cost'),'Underdog TP',config['tutor_cost'],config['tutor_cost'])
        F.integer(row.get('acquired_level'),'Underdog acquisition level',config['minimum_level'],100)
        if not isinstance(row.get('trainer_id'),str) or not row['trainer_id']:raise ValueError('Underdog trainer identity required')
        if config['underdog_kind']=='points':
            budget=F.integer(row.get('species_points'),'recorded source bonus budget')
            allocations=row.get('bonus_investments')
            if type(allocations) is not dict or not allocations:raise ValueError('source-owned bonus investments required')
            for values in allocations.values():
                check_bonus_budget(values,budget)
            if row.get('status')=='active':
                expected,policy=resolved_budget(rules,spec,row['source'],row.get('negative_decision'))
                if budget!=expected or row.get('negative_policy')!=policy:raise ValueError('evolution requires actual source bonus migration')
        if row.get('status')=='active':active.append(row)
        elif row.get('status')=='refunded':
            refund=row.get('refund',{})
            if refund.get('source') not in ('input/ch05-pokemon.md:274',row['source']) or not refund.get('reason'):raise ValueError('Underdog refund receipt required')
            F.integer(refund.get('points'),'Underdog refunded TP',config['tutor_cost'],config['tutor_cost'])
        else:raise ValueError('explicit Underdog investment lifetime required')
    if sum(row['source']==STRENGTH for row in active)>1:raise ValueError('one active Underdog Strength permitted')
    if sum(row['source'] in (POTENTIAL,HOMEBREW) for row in active)>1:raise ValueError('choose one Realized Potential source variant')
    return active


def validate(actor,*,allow_lost=False):
    active=source_rows(actor.r,actor.spec)
    if not allow_lost:
        for row in active:
            if actor.level<definition(actor.r,row['source'])['minimum_level'] or not owned(actor):raise ValueError('lost Underdog prerequisite requires source refund')
        if records(actor.spec):permanent(actor)


def base_sources(rules,spec):
    return [{'source':STRENGTH,'values':dict.fromkeys(F.STATS,1)}] if any(row['source']==STRENGTH for row in source_rows(rules,spec)) else []


def point_sources(rules,spec,*,form='base'):
    result=[]
    for row in source_rows(rules,spec):
        if row['source'] not in (POTENTIAL,HOMEBREW):continue
        investments=row['bonus_investments'];values=investments.get(form,investments.get('base'))
        if values is None:raise ValueError('explicit source bonus investment for every configured form required')
        result.append({'source':row['source'],'values':deepcopy(values)})
    return result


def blocks_evolution(rules,spec):return any(row['source']==STRENGTH for row in source_rows(rules,spec))


def permanent(actor):
    import growth_stats as GS
    return GS.source_permanent(actor)


def plans(rules,spec,current):
    import growth_stats as GS
    return GS.source_plans(rules,spec,current)


def migrate(actor,current,*,source,reason):
    import growth_stats as GS
    return GS.migrate_sources(actor,current,source=source,reason=reason,kind='underdog')


def reconcile(engine,actor,*,reason):
    if not records(actor.spec):return
    validate(actor,allow_lost=True)
    ending=[row for row in source_rows(actor.r,actor.spec) if actor.level<definition(actor.r,row['source'])['minimum_level'] or not owned(actor)]
    if not ending:return
    current=permanent(actor)
    import acquisition_withdrawal as W
    for row in ending:
        config=definition(actor.r,row['source']);lost={}
        if actor.level<config['minimum_level']:lost.update(minimum_level=config['minimum_level'],actual_level=actor.level)
        if not owned(actor):lost.update(capability='capability/약골',owned=False)
        W.refund_native_investments(actor.spec,[row],source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite=lost)
    migrate(actor,current,source=ending[0]['source'],reason=reason);validate(actor)


def teach(engine,owner,target,config,*,growth=None,negative_decision=None,from_grooming=False,from_training=False,safe=None):
    import pokemon_teaching as T,poke_edge_variants as V
    uid=config['policy']
    if definition(engine.r,uid)!=config:raise ValueError('current selected Underdog declaration required')
    T._pokemon(engine,owner,target);T.source(engine.r,uid,T.POINTS);validate(target)
    if target.level<config['minimum_level'] or not owned(target):raise ValueError('Underdog Edge requires its actual source minimum level and Underdog capability')
    active=source_rows(engine.r,target.spec)
    if any(row['source']==uid or (uid in (POTENTIAL,HOMEBREW) and row['source'] in (POTENTIAL,HOMEBREW)) for row in active):raise ValueError('Underdog investment or alternate definition already acquired')
    cost=config['tutor_cost']
    if T._balance(target.spec)<cost:raise ValueError('Underdog Edge needs its source Tutor Point cost')
    V.selected(engine.r,config)
    row={'source':uid,'status':'active','point_cost':cost,'trainer_id':owner.entity_id,'acquired_level':target.level,
        'definition_origin':{'clause_id':config['clause_id'],'rule_id':config['rule_id'],'record':config['record']}}
    if config['underdog_kind']=='points':
        budget,policy=resolved_budget(engine.r,target.spec,uid,negative_decision)
        choice=growth_choice(growth);names=set(target.spec.get('form_growth_allocations',{}).get('plans',{'base':None}))
        allocations={name:deepcopy(choice) for name in names} if set(choice)==set(F.STATS) else choice
        if set(allocations)!=names:raise ValueError('bonus investment for every current form required')
        for values in allocations.values():check_bonus_budget(values,budget)
        row.update(growth=deepcopy(choice),species_points=budget,bonus_investments=deepcopy(allocations),negative_decision=deepcopy(negative_decision),negative_policy=policy)
    elif growth is not None or negative_decision is not None:raise ValueError('Underdog Strength has no bonus point choice')
    current=permanent(target);candidate=deepcopy(target.spec);candidate.setdefault('learned_poke_edges',[]).append(row);plans(engine.r,candidate,current)
    if T.credit_mode(from_grooming,from_training):T.training_credit(engine,owner,target,uid,from_training=from_training)
    else:T.edge_training_hour(engine,owner,target,uid,uid,safe=safe)
    current=permanent(target)
    row.update(completed_at=engine.elapsed_seconds,training_source='edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274')
    target.spec.setdefault('learned_poke_edges',[]).append(row);T._debit_points(target.spec,cost)
    migrate(target,current,source=uid,reason='actual taught source-owned base or bonus investment')
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,uid,from_training=from_training)
    validate(target)
    return {'activity':'teach_edge','edge':uid,'point_cost':cost,'base_bonus':dict.fromkeys(F.STATS,1 if uid==STRENGTH else 0),
        'bonus_points':row.get('species_points',0),'evolution_prohibited':uid==STRENGTH,'seconds':0 if (from_grooming or from_training) else 3600}


def evolution_points(rules,spec,new_species,decision=None):
    """Prepare source budgets without changing old allocation evidence."""
    result={'budgets':[],'ending':[],'negative_decision':None,'negative_policy':None};rows=[row for row in source_rows(rules,spec) if row['source'] in (POTENTIAL,HOMEBREW)]
    if not rows:
        if decision is not None:raise ValueError('actual Realized Potential evolution decision required')
        return result
    future=deepcopy(spec);future.update(species=new_species['id'],capabilities=list(new_species.get('capabilities') or []))
    # The evolved-sheet projection is an actual Pokemon subject (source_rows already required kind
    # pokemon) for the shared capability owner; it carries no live round-scoped combat records.
    available=owned(SimpleNamespace(r=rules,spec=future,moves=list(future.get('moves',[])),kind='pokemon',custom_conditions={}))
    for row in rows:
        config=definition(rules,row['source']);budget=45-sum(new_species['base_stats'].values());reason=None
        if not available:reason='actual Underdog capability lost at evolution'
        elif config.get('refund_on_species_total') is not None and sum(new_species['base_stats'].values())>=config['refund_on_species_total']:reason='evolved species base total reached source refund threshold'
        if reason is not None:result['ending'].append({'source':row['source'],'reason':reason});continue
        budget,policy=resolved_budget(rules,spec,row['source'],decision,species=new_species['id'])
        result.update(negative_decision=deepcopy(decision),negative_policy=policy)
        result['budgets'].append({'source':row['source'],'points':budget})
    if decision is not None and not result['budgets']:raise ValueError('refunded source has no negative-bonus interpretation to apply')
    return result


def commit_evolution(rules,spec,new_species,plan,prepared):
    endings={row['source']:row['reason'] for row in prepared['ending']};budgets={row['source']:row['points'] for row in prepared['budgets']}
    all_plans=spec.get('form_growth_allocations',{}).get('plans',{'base':plan})
    for row in records(spec):
        if row['status']!='active' or row['source'] not in (POTENTIAL,HOMEBREW):continue
        previous={'species_points':row['species_points'],'bonus_investments':deepcopy(row['bonus_investments'])}
        if row['source'] in endings:
            F.integer(spec.get('tutor_points'),'actual evolution refund balance',0)
            row.update(status='refunded',refund={'source':row['source'],'points':row['point_cost'],'reason':endings[row['source']]});spec['tutor_points']+=row['point_cost']
        else:
            row['species_points']=budgets[row['source']]
            row.update(negative_decision=deepcopy(prepared['negative_decision']),negative_policy=deepcopy(prepared['negative_policy']))
            row['bonus_investments']={name:deepcopy(next(r['values'] for r in value.get('point_sources',[]) if r['source']==row['source'])) for name,value in all_plans.items()}
        row.setdefault('evolution_history',[]).append({'species':new_species['id'],'previous':previous,'species_points':row['species_points'],'status':row['status']})
