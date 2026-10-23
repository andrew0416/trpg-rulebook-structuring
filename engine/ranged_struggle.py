"""Basic Ranged Attacks: per-capability TP investments and live range."""
import state_fields as F
import struggle_capabilities as S
SOURCE='poke_edge/기본-원거리-공격'
ALIASES=(SOURCE,'기본 원거리 공격','Basic Ranged Attacks')


def records(actor):
 rows=actor.spec.get('learned_poke_edges',[])
 if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Poke Edge investment records required')
 return [r for r in rows if r.get('source')==SOURCE]


def validate(actor,*,allow_lost=False):
 rows=records(actor);seen=set()
 if not rows:return
 if actor.kind!='pokemon' or actor.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Pokemon ranged Struggle source required')
 for row in rows:
  import poke_edge_variants as V
  V.validate_receipt(actor.r,row)
  name=row.get('choice')
  if name not in S.DEFINITIONS or row.get('effect_storage')!='derived':raise ValueError('explicit ranged Struggle capability required')
  F.integer(row.get('point_cost'),'ranged Struggle investment',1,1)
  if row.get('status')=='active':
   if name in seen:raise ValueError('distinct active ranged Struggle choices required')
   seen.add(name)
   if not allow_lost and (actor.spec['level']<20 or not S.owned(actor,name)):raise ValueError('lost ranged Struggle prerequisite requires refund')
  elif row.get('status')=='refunded':
   refund=row.get('refund',{})
   if refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('ranged Struggle refund receipt required')
   F.integer(refund.get('points'),'ranged Struggle refund',1,1)
  else:raise ValueError('explicit ranged Struggle lifetime required')


def reconcile(actor,*,reason):
 validate(actor,allow_lost=True)
 ending=[r for r in records(actor) if r['status']=='active' and (actor.spec['level']<20 or not S.owned(actor,r['choice']))]
 import acquisition_withdrawal as W
 for row in ending:
  lost={}
  if actor.spec['level']<20:lost.update(minimum_level=20,actual_level=actor.spec['level'])
  if not S.owned(actor,row['choice']):lost.update(capability=row['choice'],owned=False)
  W.refund_native_investments(actor.spec,[row],source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite=lost)
 validate(actor)
 return len(ending)


def range_for(actor,capability):
 validate(actor)
 return 6 if any(r['status']=='active' and r['choice']==capability for r in records(actor)) else None


def teach(e,owner,*,target,capability,from_grooming=False,from_training=False,safe=None):
 import state_grants as G
 return G.transition(e,target,lambda se,st,so:_teach(se,so,st,capability,from_grooming,from_training,safe),participants=(owner,))


def _teach(e,owner,target,capability,from_grooming=False,from_training=False,safe=None):
 import pokemon_teaching as T
 T._pokemon(e,owner,target);T.source(e.r,SOURCE,T.POINTS);validate(target)
 name=S.canonical(capability)
 if target.level<20 or not S.owned(target,name):raise ValueError('ranged Struggle requires level20 and selected actual capability')
 if any(r['status']=='active' and r['choice']==name for r in records(target)):raise ValueError('capability already has ranged Struggle')
 if T._balance(target.spec)<1:raise ValueError('ranged Struggle costs one Tutor Point')
 application=SOURCE+':'+name
 if T.credit_mode(from_grooming,from_training):T.training_credit(e,owner,target,application,from_training=from_training)
 else:T.edge_training_hour(e,owner,target,SOURCE,application,safe=safe)
 T._debit_points(target.spec,1)
 target.spec.setdefault('learned_poke_edges',[]).append({'source':SOURCE,'status':'active','choice':name,'point_cost':1,'effect_storage':'derived','trainer_id':owner.entity_id,'acquired_level':target.level,'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274','completed_at':e.elapsed_seconds})
 if T.credit_mode(from_grooming,from_training):T.consume_credit(target,application,from_training=from_training)
 validate(target)
 return {'activity':'teach_edge','edge':SOURCE,'capability':name,'range':6,'point_cost':1,'seconds':0 if (from_grooming or from_training) else 3600}
