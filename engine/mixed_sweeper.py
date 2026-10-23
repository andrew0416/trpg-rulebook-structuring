"""Ranked chapter Mixed Sweeper; the conflicting CSV is a different definition."""
from copy import deepcopy
import state_fields as F
import growth_stats as GS
SOURCE='C05-067'
ALIASES=(SOURCE,'Mixed Sweeper','쌍두 스위퍼','input/ch05-pokemon.md:295-304')


def definition(rules):
    import json
    from pathlib import Path
    from source_context import verified_source
    data=json.loads((Path(rules.root)/'data/mixed-sweeper-policy.json').read_text(encoding='utf-8'))
    parent=data['selected_parent']
    if rules._selected_rule(parent)!=parent:raise ValueError('selected chapter Mixed Sweeper source required')
    verified_source(rules,data['source'],label='chapter Mixed Sweeper')
    locator=rules.selection.units[parent]['source']
    low,high=data['source']['lines']
    if locator['file']!='ch05-pokemon.md' or not locator['lines'][0]<=low<=high<=locator['lines'][1]:
        raise ValueError('chapter Mixed Sweeper locator changed')
    if data['clause_id']!=SOURCE or data['csv_equivalent'] is not False:raise ValueError('distinct chapter Mixed Sweeper declaration required')
    return data


def records(spec):
    rows=spec.get('learned_poke_edges',[])
    if type(rows)is not list or any(type(row)is not dict for row in rows):raise ValueError('actual Poke Edge records required')
    return [row for row in rows if row.get('source')==SOURCE]


def choice(value,config):
    import underdog_edges as U
    chosen=U.growth_choice(value)
    rows=[chosen] if set(chosen)==set(F.STATS) else chosen.values()
    for row in rows:
        for stat,number in row.items():F.integer(number,'Mixed Sweeper bonus investment',0)
        if sum(row.values())!=config['bonus_points'] or any(row[stat] for stat in set(F.STATS)-set(config['allowed_stats'])):
            raise ValueError('distribute exactly the declared Mixed Sweeper bonus among HP, Defense, Special Defense and Speed')
    return chosen


def source_rows(rules,spec):
    rows=records(spec)
    if not rows:return []
    config=definition(rules);active=[]
    if spec.get('kind')!='pokemon':raise ValueError('Mixed Sweeper requires an actual Pokemon')
    for row in rows:
        rank=F.integer(row.get('rank'),'Mixed Sweeper rank',1,len(config['ranks']))
        if row.get('definition_origin')!={'clause_id':SOURCE,'rule_id':config['selected_parent'],'lines':config['source']['lines']}:
            raise ValueError('chapter Mixed Sweeper acquisition source required')
        F.integer(row.get('point_cost'),'Mixed Sweeper paid TP',config['tutor_cost'],config['tutor_cost'])
        F.integer(row.get('acquired_level'),'Mixed Sweeper acquisition level',config['ranks'][rank-1]['level'],100)
        if type(row.get('trainer_id'))is not str or not row['trainer_id']:raise ValueError('actual Mixed Sweeper trainer identity required')
        values=row.get('bonus_investments');choice(values,config)
        if set(values)==set(F.STATS):raise ValueError('form-owned Mixed Sweeper investments required')
        proof=row.get('acquired_investment')
        if type(proof)is not dict or set(proof)!=set(values):raise ValueError('actual acquisition investment proof for each form required')
        for investment in proof.values():
            if type(investment)is not dict or set(investment)!=set(config['prerequisite_stats']):raise ValueError('both actual attack investments required')
            for number in investment.values():F.integer(number,'Mixed Sweeper acquired ordinary investment',config['ranks'][rank-1]['investment'])
        if row.get('status')=='active':active.append(row)
        elif row.get('status')=='refunded':
            refund=row.get('refund',{})
            if refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('actual Mixed Sweeper refund cause required')
            F.integer(refund.get('points'),'Mixed Sweeper refunded TP',row['point_cost'],row['point_cost'])
        else:raise ValueError('explicit Mixed Sweeper investment lifetime required')
    if sorted(row['rank'] for row in active)!=list(range(1,len(active)+1)):raise ValueError('distinct contiguous acquired Mixed Sweeper ranks required')
    return active


def point_sources(rules,spec,*,form='base'):
    result=[]
    for row in source_rows(rules,spec):
        values=row['bonus_investments'].get(form,row['bonus_investments'].get('base'))
        if values is None:raise ValueError('Mixed Sweeper investment for every actual form required')
        result.append({'source':f"{SOURCE}:rank:{row['rank']}",'values':deepcopy(values)})
    return result


def ordinary_plans(spec,current):
    return spec.get('form_growth_allocations',{}).get('plans',{'base':current})


def qualified(level,plans,rank,config):
    threshold=config['ranks'][rank-1]
    return level>=threshold['level'] and all(
        plan['investment'][stat]>=threshold['investment'] for plan in plans.values() for stat in config['prerequisite_stats'])


def validate(actor,*,allow_lost=False):
    active=source_rows(actor.r,actor.spec)
    if not active or allow_lost:return
    current=GS.source_permanent(actor);config=definition(actor.r)
    for row in active:
        if not qualified(actor.level,ordinary_plans(actor.spec,current),row['rank'],config):
            raise ValueError('lost Mixed Sweeper level or ordinary investment prerequisite requires refund')


def teach(engine,owner,target,*,growth,from_grooming=False,from_training=False,safe=None):
    import state_grants as G
    def apply(e,t,o):
        import pokemon_teaching as T,acquisition_qualification as Q
        T._pokemon(e,o,t);config=definition(e.r);T.source(e.r,T.POINTS);validate(t)
        active=source_rows(e.r,t.spec);rank=len(active)+1
        Q.require(SOURCE,t.entity_id,'acquire',[Q.check('rank','repeat',rank<=len(config['ranks']),'Mixed Sweeper has only its declared ranks')])
        current=GS.source_permanent(t);plans=ordinary_plans(t.spec,current)
        Q.require(SOURCE,t.entity_id,'acquire',[Q.check('level_and_investment','prerequisite',qualified(t.level,plans,rank,config),'Mixed Sweeper requires its rank level and actual ordinary Attack AND Special Attack investments in every form')])
        chosen=choice(growth,config);names=set(plans)
        allocations={name:deepcopy(chosen) for name in names} if set(chosen)==set(F.STATS) else chosen
        if set(allocations)!=names:raise ValueError('Mixed Sweeper bonus for each current form required')
        cost=config['tutor_cost']
        if T._balance(t.spec)<cost:raise ValueError('Mixed Sweeper requires its actual Tutor Point cost')
        row={'source':SOURCE,'rank':rank,'status':'active','point_cost':cost,'trainer_id':o.entity_id,'acquired_level':t.level,
             'definition_origin':{'clause_id':SOURCE,'rule_id':config['selected_parent'],'lines':config['source']['lines']},
             'bonus_investments':deepcopy(allocations),
             'acquired_investment':{name:{st:plan['investment'][st] for st in config['prerequisite_stats']} for name,plan in plans.items()}}
        proposed=deepcopy(t.spec);proposed.setdefault('learned_poke_edges',[]).append(row);GS.source_plans(e.r,proposed,current)
        application=f'{SOURCE}:rank:{rank}'
        if T.credit_mode(from_grooming,from_training):T.training_credit(e,o,t,application,from_training=from_training)
        else:T.edge_training_hour(e,o,t,config['selected_parent'],application,safe=safe)
        current=GS.source_permanent(t)
        row.update(completed_at=e.elapsed_seconds,training_source='edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274')
        t.spec.setdefault('learned_poke_edges',[]).append(row);T._debit_points(t.spec,cost)
        GS.migrate_sources(t,current,source=SOURCE,reason='actual taught chapter Mixed Sweeper rank',kind='poke_edge_points')
        if T.credit_mode(from_grooming,from_training):T.consume_credit(t,application,from_training=from_training)
        validate(t)
        return {'activity':'teach_edge','edge':SOURCE,'rank':rank,'point_cost':cost,'bonus_points':config['bonus_points'],
                'definition_origin':deepcopy(row['definition_origin']),'seconds':0 if (from_grooming or from_training) else 3600}
    return G.transition(engine,target,apply,participants=(owner,))


def refund(spec,ending,reason,*,plans,config):
    if not ending:return
    import acquisition_withdrawal as W
    for row in ending:
        threshold=config['ranks'][row['rank']-1];lost={}
        if spec['level']<threshold['level']:lost.update(minimum_level=threshold['level'],actual_level=spec['level'])
        investments={name:{stat:plan['investment'][stat] for stat in config['prerequisite_stats']
            if plan['investment'][stat]<threshold['investment']} for name,plan in plans.items()}
        investments={name:values for name,values in investments.items() if values}
        if investments:lost.update(minimum_investment=threshold['investment'],actual_investments=investments)
        W.refund_native_investments(spec,[row],source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite=lost)


def reconcile(engine,actor,*,reason):
    active=source_rows(actor.r,actor.spec)
    if not active:return
    current=GS.source_permanent(actor);config=definition(actor.r);plans=ordinary_plans(actor.spec,current)
    ending=[row for row in active if not qualified(actor.level,plans,row['rank'],config)]
    if ending:
        refund(actor.spec,ending,reason,plans=plans,config=config)
        GS.migrate_sources(actor,current,source=SOURCE,reason=reason,kind='poke_edge_points')
    validate(actor)


def evolution_plans(rules,spec,plans):
    active=source_rows(rules,spec)
    if not active:return plans
    config=definition(rules)
    ending=[row for row in active if not qualified(spec['level'],plans,row['rank'],config)]
    removed={f"{SOURCE}:rank:{row['rank']}" for row in ending};result={}
    for name,plan in plans.items():
        result[name]=GS.compose(plan['species_base'],plan['investment'],points=plan['points'],nature=spec.get('nature'),rules=rules,
            excluded=plan['excluded'],relation_exempt=plan['relation_exempt'],strategy=plan['strategy'],relation_bounds=plan.get('relation_bounds',()),
            base_sources=plan.get('base_sources',()),point_sources=[row for row in plan.get('point_sources',()) if row['source'] not in removed])
    refund(spec,ending,'actual evolved ordinary allocation no longer meets chapter rank prerequisites',plans=plans,config=config)
    return result

