"""Underdog Lessons adapts native learning, slots and final-form compatibility."""
from copy import deepcopy
from builder import species_lookup,evolution_stages
import state_fields as F
SOURCE='poke_edge/약골의-수업'
ALIASES={'Underdog’s Lessons':SOURCE,"Underdog's Lessons":SOURCE}


def records(spec):
    rows=spec.get('learned_poke_edges',[])
    if type(rows)is not list or any(type(row)is not dict for row in rows):raise ValueError('actual Poke Edge records required')
    return [row for row in rows if row.get('source')==SOURCE]


def final_species(rules,species):
    current=species_lookup(rules,species);stages=evolution_stages(rules.learnsets.get(current['name'],{}))
    if not stages or not any(name==current['name'] for _,name,_ in stages):raise ValueError('explicit sourced evolution lineage required')
    maximum=max(stage for stage,_,_ in stages);result=[]
    for stage,name,_ in stages:
        if stage!=maximum:continue
        try:identity=species_lookup(rules,name)['id']
        except KeyError:continue
        if identity not in result:result.append(identity)
    return result


def choice(rules,value):
    if type(value)is not dict or set(value)!={'species','move_id'} or any(type(x)is not str or not x for x in value.values()):
        raise ValueError('explicit final species and level-up Move choice required')
    mid=rules.move_id(value['move_id'])
    if mid is None or mid in rules.excluded_moves:raise ValueError('available actual lesson Move required')
    return {'species':species_lookup(rules,value['species'])['id'],'move_id':mid}


def candidates(rules,species,level):
    import downtime as D
    return list(dict.fromkeys(D._learnset_moves_upto(rules,species_lookup(rules,species)['name'],level)))


def checked(rules,spec):
    rows=records(spec)
    if not rows:return []
    import poke_edge_variants as V,underdog_edges as U
    definition=V.resolve(rules,SOURCE)
    if definition is None or definition['field']!='lesson':raise ValueError('selected actual Underdog Lessons declaration required')
    ids=set();finals=set()
    for row in rows:
        V.validate_receipt(rules,row)
        selected=choice(rules,row.get('lesson'))
        if selected!=row['lesson']:raise ValueError('canonical lesson receipt required')
        level=F.integer(row.get('acquired_level'),'actual historical lesson level',1,100)
        F.integer(row.get('point_cost'),'actual lesson TP cost',1,1)
        for key in ('trainer_id','lesson_id'):
            if type(row.get(key))is not str or not row[key]:raise ValueError('actual lesson identity required')
        if row['lesson_id'] in ids:raise ValueError('distinct lesson receipts required')
        ids.add(row['lesson_id']);finals.add(selected['species'])
        if selected['species'] not in final_species(rules,row.get('origin_species')) or selected['move_id'] not in candidates(rules,selected['species'],level):
            raise ValueError('lesson must match its sourced historical final species and level-up list')
        index=F.integer(row.get('strength_receipt'),'historical Strength receipt index',0)
        all_rows=spec['learned_poke_edges']
        if index>=next(i for i,item in enumerate(all_rows) if item is row) or all_rows[index].get('source')!=U.STRENGTH:raise ValueError('actual historical Underdog Strength prerequisite receipt required')
        if row.get('status')=='refunded':
            refund=row.get('refund',{})
            if refund.get('points')!=1 or refund.get('source')!=SOURCE or not refund.get('reason'):raise ValueError('actual lesson refund required')
        elif row.get('status')!='active':raise ValueError('explicit lesson lifetime required')
    if len(finals)!=1 or sum(row['status']=='active' for row in rows)>3:raise ValueError('up to three lessons from the same final evolution required')
    return rows


def natural_moves(rules,spec):
    rows={row['lesson_id']:row for row in checked(rules,spec)};result=set()
    for mid,learned in spec.get('move_learning',{}).items():
        if not isinstance(learned,dict) or learned.get('method')!='underdog_lessons':continue
        row=rows.get(learned.get('lesson_id'))
        if row is None or learned.get('source')!=SOURCE or learned.get('paid_tp')!=1 or row['lesson']['move_id']!=mid:
            raise ValueError('natural lesson move requires its actual permanent learning receipt')
        if learned.get('teacher_id')!=row['trainer_id'] or learned.get('learned_at_level')!=row['acquired_level'] or learned.get('final_species')!=row['lesson']['species']:
            raise ValueError('historical lesson learning provenance mismatch')
        result.add(mid)
    return result


def validate(actor,*,allow_lost=False):
    rows=checked(actor.r,actor.spec)
    if not rows:return
    import underdog_edges as U
    if not allow_lost and any(row['status']=='active' for row in rows) and not U.blocks_evolution(actor.r,actor.spec):
        raise ValueError('lost actual Underdog Strength requires lesson refund')
    log=actor.spec.get('move_learning_log',[])
    for row in rows:
        if not any(item.get('method')=='underdog_lessons' and item.get('lesson_id')==row['lesson_id'] and item.get('move_id')==row['lesson']['move_id'] for item in log if isinstance(item,dict)):
            raise ValueError('completed lesson permanent learning history required')
    natural_moves(actor.r,actor.spec)


def reconcile(actor,*,reason):
    rows=checked(actor.r,actor.spec)
    if not rows:return
    import underdog_edges as U
    if U.blocks_evolution(actor.r,actor.spec):return
    ending=[row for row in rows if row['status']=='active']
    if not ending:return
    import acquisition_withdrawal as W
    W.refund_native_investments(actor.spec,ending,source=SOURCE,reason=reason,
        lost_prerequisite={'source':U.STRENGTH,'active':False})
    validate(actor)


def active_final(rules,spec):
    rows=[row for row in checked(rules,spec) if row['status']=='active']
    return rows[0]['lesson']['species'] if rows else None


def learning_permission(rules,spec,mid,method,*,machine=None):
    final=active_final(rules,spec)
    if final is None:return False
    import re
    ls=rules.learnsets.get(species_lookup(rules,final)['name'],{})
    if method=='tutor':
        return mid in {rules.move_id(re.sub(r'\s*\(N\)','',str(name),flags=re.I)) for name in ls.get('tutor',[])}
    if method not in ('tm','hm') or type(machine)is not dict:return False
    expected=('A' if method=='hm' else '')+str(machine['number']);listed=[]
    for raw in ls.get('tm',[]):
        match=re.fullmatch(r'\s*([A-Za-z]?)([0-9]+)\s+(.+?)\s*',str(raw))
        if match and match.group(1).upper()+str(int(match.group(2)))==expected:listed.append(match.group(3))
    if not listed:return False
    mids={rules.move_id(name) for name in listed}
    if None in mids or mids!={mid}:raise ValueError('final species and machine source identity conflict')
    return True


def teach(engine,owner,target,definition,selected,*,from_grooming=False,from_training=False,safe=None):
    import pokemon_teaching as T,underdog_edges as U,learning_grant as L,move_state as M,state_grants as G
    T._pokemon(engine,owner,target);T.source(engine.r,SOURCE,T.POINTS);U.validate(target);validate(target)
    if not U.blocks_evolution(engine.r,target.spec):raise ValueError('actual acquired Underdog Strength required')
    selected=choice(engine.r,selected);rows=checked(engine.r,target.spec)
    if len([row for row in rows if row['status']=='active'])>=3:raise ValueError('at most three active Underdog Lessons')
    if rows and rows[0]['lesson']['species']!=selected['species']:raise ValueError('all lessons must use the same final evolution')
    if selected['species'] not in final_species(engine.r,target.spec['species']):raise ValueError('selected species is not an actual final evolution')
    pool=candidates(engine.r,selected['species'],target.level)
    if selected['move_id'] not in pool:raise ValueError('lesson must be a level-up Move at or below actual current level')
    if T._balance(target.spec)<1:raise ValueError('Underdog Lessons needs one actual Tutor Point')
    row={'source':SOURCE,'status':'active','point_cost':1,'trainer_id':owner.entity_id,'acquired_level':target.level,
        'lesson':selected,'origin_species':target.spec['species'],'lesson_id':SOURCE+':'+str(len(rows)+1),
        'strength_receipt':next(i for i,item in enumerate(target.spec['learned_poke_edges']) if item.get('source')==U.STRENGTH and item.get('status')=='active'),
        'definition_origin':{'clause_id':definition['clause_id'],'rule_id':definition['rule_id'],'record':definition['record']}}
    candidate=deepcopy(target.spec);candidate.setdefault('learned_poke_edges',[]).append(deepcopy(row))
    L.learn_moves(engine.r,candidate,candidates=pool,selected=[selected['move_id']],method='underdog_lessons',source=SOURCE,
        reason='actual final evolution lesson learned as a level-up Move',provider=owner.entity_id,paid_tp=1,
        details={'lesson_id':row['lesson_id'],'final_species':selected['species']})
    M.record_natural_opportunities(engine.r,candidate,reason='completed final evolution lesson')
    M.validate_spec(engine.r,candidate,require_routes=True)
    if T.credit_mode(from_grooming,from_training):T.training_credit(engine,owner,target,SOURCE,from_training=from_training)
    else:T.edge_training_hour(engine,owner,target,SOURCE,SOURCE,safe=safe)
    if not U.blocks_evolution(engine.r,target.spec):raise ValueError('actual Strength prerequisite must survive the completed lesson hour')
    row.update(completed_at=engine.elapsed_seconds,training_source='edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274')
    target.spec.setdefault('learned_poke_edges',[]).append(row)
    for field in ('move_learning','move_learning_log',M.HISTORY):
        if field in candidate:target.spec[field]=candidate[field]
    G.set_baseline(target,'moves',candidate['moves']);T._debit_points(target.spec,1)
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,SOURCE,from_training=from_training)
    validate(target);M.validate_spec(engine.r,target.spec,moves=target.moves,abilities=target.abilities,require_routes=True)
    return {'activity':'teach_edge','edge':SOURCE,'lesson':deepcopy(selected),'point_cost':1,'classification':'natural',
        'seconds':0 if (from_grooming or from_training) else 3600}

