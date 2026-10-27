"""Source-selected permanent Move modifications; independent of learning rights."""
from copy import deepcopy
import state_fields as F
import composition_derive as COMPOSITION

ACCURACY='poke_edge/정확도-훈련'
ALIASES={ACCURACY:ACCURACY,'정확도 훈련':ACCURACY,'Accuracy Training':ACCURACY}
MARKER='_pokemon_accuracy_training'


def records(spec):
    rows=spec.get('learned_poke_edges',[])
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Poke Edge investments must be records')
    return [r for r in rows if r.get('source')==ACCURACY]


def validate(rules,spec,*,allow_lost_prerequisite=False):
    active=set()
    for row in records(spec):
        import poke_edge_variants as VARIANTS
        VARIANTS.validate_receipt(rules,row,history=True,minimum_level=20)
        if spec.get('kind')!='pokemon':raise ValueError('Accuracy Training requires an actual Pokemon')
        if rules._selected_rule(ACCURACY)!=ACCURACY:raise ValueError('selected Accuracy Training needs its own source policy')
        mid=row.get('move_id')
        if not isinstance(mid,str) or rules.move_id(mid)!=mid or mid in getattr(rules,'excluded_moves',{}):raise ValueError('canonical actual Move selection required')
        if rules._selected_rule(mid)!=mid:raise ValueError('selected Move variant requires its own accuracy policy')
        F.integer(rules.move(mid).get('ac'),'Accuracy Training original Move AC',3)
        F.integer(row.get('point_cost'),'Accuracy Training point cost',1,1)
        if row.get('effect_storage')!='derived':raise ValueError('Accuracy Training must use a derived Move overlay')
        if row.get('status')=='active':
            if mid in active:raise ValueError('Accuracy Training must select distinct Moves')
            active.add(mid)
            if spec['level']<20 and not allow_lost_prerequisite:raise ValueError('lost level20 prerequisite needs Accuracy Training refund')
        elif row.get('status')=='refunded':
            refund=row.get('refund')
            if not isinstance(refund,dict) or refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('Accuracy Training refund receipt required')
            F.integer(refund.get('points'),'Accuracy Training refunded points',1,1)
        else:raise ValueError('explicit Accuracy Training lifetime required')
    if len(active)>3:raise ValueError('Accuracy Training permits at most three active selections')


def reconcile_spec(rules,spec,*,reason):
    reconcile_mixed_spec(rules,spec,reason=reason)
    validate(rules,spec,allow_lost_prerequisite=True)
    ending=[r for r in records(spec) if r['status']=='active' and spec['level']<20]
    import acquisition_withdrawal as WITHDRAWAL
    WITHDRAWAL.refund_native_investments(spec,ending,source='input/ch05-pokemon.md:274',
        reason=reason,lost_prerequisite={'minimum_level':20,'actual_level':spec['level']})
    validate(rules,spec)
    return [{'source':r['source'],'move_id':r['move_id'],'points':1} for r in ending]


def prepare(engine,actor,move):
    """Idempotent actor projection; later conditional AC replacement still wins."""
    import struggle_capabilities as STRUGGLE
    move=STRUGGLE.prepare(engine,actor,move)
    import move_type_sync as MOVE_SYNC
    move=MOVE_SYNC.prepare(engine,actor,move)
    import unown_imbuement as UNOWN
    move=UNOWN.prepare(engine,actor,move)
    move=__import__('type_ace').prepare(engine,actor,move)
    move=__import__('rune_master').prepare(engine,actor,move)
    move=__import__('ace_trainer').prepare(engine,actor,move)
    validate(engine.r,actor.spec)
    amount=int(any(r['status']=='active' and r['move_id']==move['id'] for r in records(actor.spec)))
    previous=move.get(MARKER)
    if not amount and previous is None:return move
    out=deepcopy(move)
    if previous is not None:
        if not isinstance(previous,dict) or previous.get('source')!=ACCURACY:raise ValueError('invalid prepared Move accuracy provenance')
        F.integer(previous.get('amount'),'prepared accuracy contribution',1,1)
        out['ac']+=previous['amount'];out.pop(MARKER)
    if amount:
        F.integer(out.get('ac'),'actual Move AC before Accuracy Training',1)
        out['ac']=COMPOSITION.derive(out['ac'],[{'id':ACCURACY,'source':ACCURACY,'value':-1}],
            [{'law':'add','contributors':[ACCURACY]}])['value']
        out[MARKER]={'source':ACCURACY,'actor_id':actor.entity_id,'amount':1}
    return out


def teach(e,owner,*,target,move_id,from_grooming=False,from_training=False,safe=None):
    import state_grants as G
    return G.transition(e,target,lambda se,st,so:_teach(se,so,st,move_id,from_grooming,from_training,safe),participants=(owner,))


def _teach(e,owner,target,move_id,from_grooming,from_training,safe=None):
    import pokemon_teaching as T
    T._pokemon(e,owner,target);T.source(e.r,ACCURACY,T.POINTS);validate(e.r,target.spec)
    if target.level<20:raise ValueError('Accuracy Training requires level20')
    mid=e.r.move_id(move_id) if isinstance(move_id,str) else None
    if mid is None or mid in getattr(e.r,'excluded_moves',{}):raise ValueError('select one actual Move')
    if e.r._selected_rule(mid)!=mid:raise ValueError('selected Move variant needs its own accuracy policy')
    F.integer(e.r.move(mid).get('ac'),'Accuracy Training original Move AC',3)
    active=[r for r in records(target.spec) if r['status']=='active']
    if len(active)>=3:raise ValueError('Accuracy Training permits at most three selections')
    if any(r['move_id']==mid for r in active):raise ValueError('Accuracy Training must select distinct Moves')
    if T._balance(target.spec)<1:raise ValueError('Accuracy Training costs one Tutor Point')
    application=ACCURACY+':'+mid
    if T.credit_mode(from_grooming,from_training):T.training_credit(e,owner,target,application,from_training=from_training)
    else:T.edge_training_hour(e,owner,target,ACCURACY,application,safe=safe)
    T._debit_points(target.spec,1)
    target.spec.setdefault('learned_poke_edges',[]).append({'source':ACCURACY,'status':'active','move_id':mid,
        'point_cost':1,'effect_storage':'derived','trainer_id':owner.entity_id,'acquired_level':target.level,
        'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,application,from_training=from_training)
    validate(e.r,target.spec)
    return {'activity':'teach_edge','edge':ACCURACY,'move_id':mid,'ac_modifier':-1,'point_cost':1,'seconds':0 if (from_grooming or from_training) else 3600}


# Adopted errata PDF14 replaces the older Mixed Sweeper ability grant. This
# uses the ordinary Poke Edge investment receipt and teaching/time/TP owners.
MIXED_POWER='poke_edge/mixed-power-errata'
MIXED_ORIGIN={'file':'source-audit/dataninja-errata-primary.pdf','sha256':'f754c539e64d40c28c933d43c86a75e2b4089d930b8f9eb0442e52c01fa7fdbb','pdf_page':14}
OFFICIAL_MIXED='poke_edge/mixed-power-september-2015'
OFFICIAL_MIXED_ORIGIN={'file':'source-audit/official-sep2015.pdf','sha256':'846c23a90f26d7deb7a86117622378bc60dc7c729a9a6b1e747ea67d4a1c6caf','pdf_page':9}
INCANDESCENCE='feat/작열'


def incandescence_source(rules):
 """Independent explicit versions; the existing user-adopted default stays put."""
 from source_context import verified_source
 version=rules.ruleset.unit_versions.get(INCANDESCENCE,'adopted-errata')
 refs={'adopted-errata':dict(MIXED_ORIGIN,pdf_page=17),
  'ptu-core-1.05':{'file':'source-audit/ptu-core-1.05.pdf','sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907','pdf_page':123},
  'september-2015':OFFICIAL_MIXED_ORIGIN}
 if version not in refs:raise ValueError('unknown Incandescence source version')
 if rules._selected_rule(INCANDESCENCE,supports_versions=True)!=INCANDESCENCE:raise ValueError('selected Incandescence required')
 verified_source(rules,refs[version],label='Incandescence '+version,source_root='source-audit')
 return dict(refs[version],version=version)


def incandescence_bound(engine,p,move):
 return bool(move['class'] in ('물리','특수') and move['type']=='불꽃'
  and __import__('type_ace').sustained(engine,p,INCANDESCENCE))


def official_incandescence_power(engine,p,move):
 """The September gained Ability effect follows the independently selected Ability."""
 if not incandescence_bound(engine,p,move) or incandescence_source(engine.r)['version']!='september-2015' or official_mixed_power(p):return False
 if engine.r._selected_rule('ability/트위스트파워')!='ability/트위스트파워':raise ValueError('conditional official Mixed Power requires its selected Twisted Power policy')
 return not p.abilities_suppressed


def official_mixed_power(actor,*,allow_lost=False):
 """The official Ability-granting receipt is never inferred from the later edge."""
 rows=[r for r in actor.spec.get('learned_poke_edges',[]) if r.get('source')==OFFICIAL_MIXED]
 if rows and actor.kind!='pokemon':raise ValueError('official Mixed Power requires an actual Pokemon')
 if len([r for r in rows if r.get('status')=='active'])>1:raise ValueError('official Mixed Power is not repeatable')
 if rows:
  from source_context import verified_source
  verified_source(actor.r,OFFICIAL_MIXED_ORIGIN,label='official Mixed Power',source_root='source-audit')
 for row in rows:
  if (row.get('point_cost')!=2 or row.get('definition_origin')!=OFFICIAL_MIXED_ORIGIN
    or type(row.get('trainer_id'))is not str or not row['trainer_id'].strip()
    or type(row.get('grant_source'))is not str or not row['grant_source'].startswith(OFFICIAL_MIXED+':')
    or type(row.get('acquired_level'))is not int or row['acquired_level']<10
    or row.get('training_source')!='input/ch05-pokemon.md:274' or type(row.get('completed_at'))is not int or row['completed_at']<3600):raise ValueError('actual official Mixed Power acquisition receipt required')
  proof=row.get('acquired_investment')
  if type(proof)is not dict or not proof or any(type(v)is not dict or set(v)!={'atk','spa'} or any(type(n)is not int or n<5 for n in v.values()) for v in proof.values()):raise ValueError('official Mixed Power actual five investments in both stats required')
  grant=actor.spec.get('state_grants',{}).get('sources',{}).get(row.get('grant_source'))
  if row.get('status')=='active':
   expected={'kind':'poke_edge','owner_id':actor.entity_id,'lifetime':'while_prerequisites','rule_id':'ability/트위스트파워','tutor_points':2,'grants':{'abilities':['트위스트파워']}}
   if grant!=expected:raise ValueError('actual official Mixed Power Twisted Power grant required')
   if not allow_lost:
    import growth_stats as GS,mixed_sweeper as MS
    plans=MS.ordinary_plans(actor.spec,GS.source_permanent(actor))
    if actor.level<10 or any(plan['investment'][s]<5 for plan in plans.values() for s in ('atk','spa')):raise ValueError('lost official Mixed Power prerequisites require refund')
  elif row.get('status')=='refunded':
   if grant is not None or row.get('refund',{}).get('source')!='input/ch05-pokemon.md:274' or row.get('refund',{}).get('points')!=2:raise ValueError('actual official Mixed Power refund required')
  else:raise ValueError('explicit official Mixed Power lifetime required')
 return any(row['status']=='active' for row in rows)


def teach_official_mixed_power(engine,owner,target,*,safe=None):
 """September2015 p9: level10 + five ordinary points in each attack; no within-five gate."""
 from source_context import verified_source
 verified_source(engine.r,OFFICIAL_MIXED_ORIGIN,label='official Mixed Power',source_root='source-audit')
 import state_grants as G
 def apply(e,p,t):
  import pokemon_teaching as T,growth_stats as GS,mixed_sweeper as MS
  T._pokemon(e,t,p);T.source(e.r,T.POINTS)
  if official_mixed_power(p):raise ValueError('official Mixed Power already acquired')
  current=GS.source_permanent(p);plans=MS.ordinary_plans(p.spec,current)
  if p.level<10 or any(plan['investment'][s]<5 for plan in plans.values() for s in ('atk','spa')):raise ValueError('official Mixed Power requires level ten and five actual ordinary investments in both attack Stats')
  if T._balance(p.spec)<2:raise ValueError('official Mixed Power costs two Tutor Points')
  T.edge_training_hour(e,t,p,T.POINTS,OFFICIAL_MIXED,safe=safe)
  sid=OFFICIAL_MIXED+':'+str(len(p.spec.get('learned_poke_edges',[]))+1)
  p.spec.setdefault('learned_poke_edges',[]).append({'source':OFFICIAL_MIXED,'status':'active','point_cost':2,'trainer_id':t.entity_id,'definition_origin':dict(OFFICIAL_MIXED_ORIGIN),
   'acquired_level':p.level,'acquired_investment':{name:{s:plan['investment'][s] for s in ('atk','spa')} for name,plan in plans.items()},'grant_source':sid,
   'training_source':'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
  G.grant(p,'abilities','트위스트파워',sid,'poke_edge',owner_id=p.entity_id,lifetime='while_prerequisites',rule_id='ability/트위스트파워',tutor_points=2)
  G.reconcile(e,p);T._debit_points(p.spec,2);official_mixed_power(p)
  return {'activity':'teach_edge','edge':OFFICIAL_MIXED,'point_cost':2,'seconds':3600}
 return G.transition(engine,target,apply,participants=(owner,))


def mixed_power(actor):
 rows=[r for r in actor.spec.get('learned_poke_edges',[]) if r.get('source')==MIXED_POWER]
 if len([r for r in rows if r.get('status')=='active'])>1:raise ValueError('Mixed Power is not repeatable')
 if rows:mixed_source()
 for r in rows:
  if r.get('status') not in ('active','refunded') or r.get('point_cost')!=2 or r.get('definition_origin')!=MIXED_ORIGIN or not r.get('trainer_id') or not isinstance(r.get('acquired_investment'),dict):raise ValueError('actual sourced Mixed Power acquisition receipt required')
  if r['status']=='refunded' and (r.get('refund',{}).get('source')!='input/ch05-pokemon.md:274' or r.get('refund',{}).get('points')!=2):raise ValueError('actual Mixed Power prerequisite refund required')
 return any(r['status']=='active' for r in rows)


def teach_mixed_power(engine,owner,target,*,safe=None):
 mixed_source()
 import state_grants as G
 def apply(e,p,t):
  import pokemon_teaching as T,growth_stats as GS,mixed_sweeper as MS
  T._pokemon(e,t,p);T.source(e.r,T.POINTS)
  if mixed_power(p):raise ValueError('Mixed Power already acquired')
  current=GS.source_permanent(p);plans=MS.ordinary_plans(p.spec,current)
  if p.level<10 or any(plan['investment']['atk']<5 or plan['investment']['spa']<5 for plan in plans.values()) or abs(p.stats['atk']-p.stats['spa'])>5:raise ValueError('Mixed Power requires level ten, five actual ordinary investments in each attack Stat and un-staged stats within five')
  if T._balance(p.spec)<2:raise ValueError('Mixed Power costs two Tutor Points')
  T.edge_training_hour(e,t,p,T.POINTS,MIXED_POWER,safe=safe);T._debit_points(p.spec,2)
  p.spec.setdefault('learned_poke_edges',[]).append({'source':MIXED_POWER,'status':'active','point_cost':2,'trainer_id':t.entity_id,'definition_origin':dict(MIXED_ORIGIN),'acquired_investment':{name:{st:plan['investment'][st] for st in ('atk','spa')} for name,plan in plans.items()},'training_source':'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
  mixed_power(p)
  return {'activity':'teach_edge','edge':MIXED_POWER,'point_cost':2,'seconds':3600}
 return G.transition(engine,target,apply,participants=(owner,))


def mixed_damage_stat(engine,p,move,current):
 if move['class'] not in ('물리','특수'):return current
 bound=incandescence_bound(engine,p,move)
 owned=mixed_power(p)
 if bound:
  version=incandescence_source(engine.r)['version']
  if version=='ptu-core-1.05':return p.staged('atk')+p.staged('spa')
  if version=='september-2015':
   if official_mixed_power(p):return p.staged('atk')+p.staged('spa')
   # The conditional Ability choice belongs to the existing native completion,
   # not an automatic damage bonus. An independent adopted direct edge stays.
   return current+__import__('arithmetic_policy').ratio(p.staged('spa' if move['class']=='물리' else 'atk'),2) if owned else current
  if owned:return p.staged('atk')+p.staged('spa')
 if bound or owned:return current+__import__('arithmetic_policy').ratio(p.staged('spa' if move['class']=='물리' else 'atk'),2)
 return current


def mixed_source():
 from pathlib import Path
 from hashlib import sha256
 raw=(Path(__file__).resolve().parents[1]/MIXED_ORIGIN['file']).read_bytes()
 if sha256(raw).hexdigest()!=MIXED_ORIGIN['sha256']:raise ValueError('adopted Mixed Power source changed; review required')


def mixed_qualified(rules,spec):
 if spec['level']<10 or abs(spec['stats']['atk']-spec['stats']['spa'])>5:return False
 import growth_stats as GS,mixed_sweeper as MS
 plans=MS.ordinary_plans(spec,GS.project(rules,spec))
 return all(plan['investment']['atk']>=5 and plan['investment']['spa']>=5 for plan in plans.values())


def reconcile_mixed_spec(rules,spec,*,reason):
 rows=[r for r in spec.get('learned_poke_edges',[]) if r.get('source')==MIXED_POWER and r.get('status')=='active']
 if not rows:return
 mixed_source()
 if not mixed_qualified(rules,spec):
  __import__('acquisition_withdrawal').refund_native_investments(spec,rows,source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite={'minimum_level':10,'minimum_each_ordinary_attack_investment':5,'maximum_unstaged_attack_difference':5,'actual_level':spec['level'],'actual_attack_difference':abs(spec['stats']['atk']-spec['stats']['spa'])})


def reconcile_mixed(engine,actor,*,reason):
 reconcile_mixed_spec(engine.r,actor.spec,reason=reason)
 mixed_power(actor)
 if official_mixed_power(actor,allow_lost=True):
  import growth_stats as GS,mixed_sweeper as MS,state_grants as G
  plans=MS.ordinary_plans(actor.spec,GS.source_permanent(actor))
  if actor.level<10 or any(plan['investment'][s]<5 for plan in plans.values() for s in ('atk','spa')):
   rows=[r for r in actor.spec['learned_poke_edges'] if r.get('source')==OFFICIAL_MIXED and r['status']=='active']
   for row in rows:G.revoke(actor,row['grant_source'],engine=engine)
   __import__('acquisition_withdrawal').refund_native_investments(actor.spec,rows,source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite={'minimum_level':10,'minimum_each_ordinary_attack_investment':5})
   official_mixed_power(actor)
