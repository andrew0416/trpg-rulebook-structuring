"""TK Mastery: scoped Focus rank, with the existing Poke Edge lifecycle."""
import state_fields as F
import state_grants as G
import skill_modifiers as S
import composition_derive as COMPOSITION
SOURCE='poke_edge/tk-마스터리'
ALIASES=(SOURCE,'TK 마스터리','TK Mastery','C2CSV/input/db/poke-edges.csv:R56:main')
CONTEXT='telekinetic_carry'

def owned(c):
 return bool({S.key(x) for x in ('염력','Telekinetic','capability/염력')}.intersection(S.key(x) for x in G.effective_capabilities(c)))

def records(c):
 rows=c.spec.get('learned_poke_edges',[])
 if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Poke Edge records required')
 return [r for r in rows if r.get('source')==SOURCE]

def eligible(c):return c.spec['level']>=20 and owned(c)

def validate(c,*,allow_lost=False):
 rows=records(c)
 if not rows:return
 if c.kind!='pokemon' or c.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Pokemon TK Mastery source required')
 active=0
 for r in rows:
  import poke_edge_variants as V
  V.validate_receipt(c.r,r)
  F.integer(r.get('point_cost'),'TK Mastery TP',1,1)
  if r.get('status')=='active':
   active+=1
   if not allow_lost and not eligible(c):raise ValueError('lost TK Mastery prerequisite requires refund')
  elif r.get('status')=='refunded':
   refund=r.get('refund',{})
   if refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('TK Mastery refund receipt required')
   F.integer(refund.get('points'),'TK Mastery refunded TP',1,1)
  else:raise ValueError('explicit TK Mastery lifetime required')
 if active>1:raise ValueError('one active TK Mastery investment permitted')

def bonus(c):
 validate(c)
 return 2 if any(r['status']=='active' for r in records(c)) else 0

def focus(c):
 value=bonus(c)
 rows=[{'id':SOURCE,'source':SOURCE,'value':value}] if value else []
 return COMPOSITION.derive(S.effective_rank(c.r,c,'집중'),rows,
  [{'law':'add','contributors':[SOURCE]}] if rows else [])['value']

def carry_bonus(e,c,skill,context):
 import telekinetic_combat as COMBAT
 if isinstance(context,dict) and context.get('purpose')==COMBAT.PURPOSE:return COMBAT.roll_bonus(e,c,skill,context)
 if not isinstance(context,dict) or context.get('purpose')!=CONTEXT:return 0
 import telekinetic_load as TK
 TK.require(e,c)
 if S.skill_id(e.r.skill_policy,skill)!=S.skill_id(e.r.skill_policy,'집중') or c.spec.get('_carried_load',{}).get('mode')!='telekinetic':raise ValueError('actual telekinetic Focus carrying check required')
 return bonus(c)

def reconcile(c,*,reason):
 validate(c,allow_lost=True)
 ending=[r for r in records(c) if r['status']=='active' and not eligible(c)]
 import acquisition_withdrawal as W
 if ending:
  lost={}
  if c.spec['level']<20:lost.update(minimum_level=20,actual_level=c.spec['level'])
  if not owned(c):lost.update(capability='capability/염력',owned=False)
  W.refund_native_investments(c.spec,ending,source='input/ch05-pokemon.md:274',reason=reason,lost_prerequisite=lost)
 validate(c)

def teach(e,owner,*,target,from_grooming=False,from_training=False,safe=None):
 def apply(se,t,o):
  import pokemon_teaching as T
  T._pokemon(se,o,t);T.source(se.r,SOURCE,T.POINTS);validate(t)
  if not eligible(t):raise ValueError('TK Mastery requires level20 and Telekinetic')
  if any(r['status']=='active' for r in records(t)):raise ValueError('TK Mastery already acquired')
  if T._balance(t.spec)<1:raise ValueError('TK Mastery costs one TP')
  if T.credit_mode(from_grooming,from_training):T.training_credit(se,o,t,SOURCE,from_training=from_training)
  else:T.edge_training_hour(se,o,t,SOURCE,SOURCE,safe=safe)
  T._debit_points(t.spec,1)
  t.spec.setdefault('learned_poke_edges',[]).append({'source':SOURCE,'status':'active','point_cost':1,'trainer_id':o.entity_id,'acquired_level':t.level,'completed_at':se.elapsed_seconds,'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274'})
  if T.credit_mode(from_grooming,from_training):T.consume_credit(t,SOURCE,from_training=from_training)
  validate(t)
  return {'activity':'teach_edge','edge':SOURCE,'point_cost':1,'focus_rank_bonus':2,'seconds':0 if (from_grooming or from_training) else 3600}
 return G.transition(e,target,apply,participants=(owner,))
