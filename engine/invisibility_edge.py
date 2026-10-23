"""Extended Invisibility investment and historical session retirement."""
import state_fields as F
import state_grants as G
import skill_modifiers as S
SOURCE='poke_edge/투명-연장'
ALIASES=(SOURCE,'투명 연장','Extended Invisibility','C2CSV/input/db/poke-edges.csv:R52:main')

def records(c):
 rows=c.spec.get('learned_poke_edges',[])
 if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('Poke Edge records required')
 return [r for r in rows if r.get('source')==SOURCE]

def eligible(c):
 return c.spec['level']>=20 and bool({S.key('투명'),S.key('Invisibility')}.intersection(S.key(x) for x in G.effective(c,'capabilities',include_suppressed=True)))

def validate(c,*,allow_lost=False):
 rows=records(c)
 if not rows:return
 if c.kind!='pokemon' or c.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Pokemon Extended Invisibility source required')
 active=0
 for r in rows:
  F.integer(r.get('point_cost'),'Extended Invisibility TP',1,1)
  if r.get('status')=='active':
   active+=1
   if not allow_lost and not eligible(c):raise ValueError('lost Extended Invisibility prerequisite requires refund')
  elif r.get('status')=='refunded':
   refund=r.get('refund',{})
   if refund.get('source')!='input/ch05-pokemon.md:274' or not refund.get('reason'):raise ValueError('Extended Invisibility refund receipt required')
   F.integer(refund.get('points'),'Extended Invisibility refunded TP',1,1)
  else:raise ValueError('explicit Extended Invisibility lifetime required')
 if active>1:raise ValueError('one active Extended Invisibility investment permitted')

def duration(c):
 validate(c)
 return 480 if any(r['status']=='active' for r in records(c)) else 240

def reconcile(e,c):
 validate(c,allow_lost=True)
 ending=[r for r in records(c) if r['status']=='active' and not eligible(c)]
 if not ending:return
 F.integer(c.spec.get('tutor_points'),'Extended Invisibility refund balance',0)
 import invisibility_state as V
 row=c.spec.get(V.KEY)
 if row and row.get('duration_seconds',240)==480 and row['ended_elapsed'] is None:
  low,high=V.elapsed_bounds(e,c)
  if low<480:
   has_base=bool({S.key('투명'),S.key('Invisibility')}.intersection(S.key(x) for x in G.effective(c,'capabilities',include_suppressed=True)))
   if has_base and high<=240:row['duration_seconds']=240
   else:
    if low!=high:raise ValueError('observe invisibility elapsed time before prerequisite loss')
    row.update(clock_anchor=e.elapsed_seconds,unknown_index=len(e.unresolved_time_intervals),elapsed_base=low,ended_elapsed=low,reason='Extended Invisibility prerequisite ended')
 lost={}
 if c.spec['level']<20:lost.update(minimum_level=20,actual_level=c.spec['level'])
 if not {S.key('투명'),S.key('Invisibility')}.intersection(S.key(x) for x in G.effective(c,'capabilities',include_suppressed=True)):
  lost.update(capability='capability/투명',owned=False)
 import acquisition_withdrawal as W
 W.refund_native_investments(c.spec,ending,source='input/ch05-pokemon.md:274',
  reason='Extended Invisibility prerequisite ended',lost_prerequisite=lost)
 validate(c)

def teach(e,owner,*,target,from_grooming=False,from_training=False,safe=None):
 def apply(se,t,o):
  import pokemon_teaching as T
  T._pokemon(se,o,t);T.source(se.r,SOURCE,T.POINTS);validate(t)
  if not eligible(t):raise ValueError('Extended Invisibility requires level20 and Invisibility')
  if any(r['status']=='active' for r in records(t)):raise ValueError('Extended Invisibility already acquired')
  if T._balance(t.spec)<1:raise ValueError('Extended Invisibility costs one TP')
  if T.credit_mode(from_grooming,from_training):T.training_credit(se,o,t,SOURCE,from_training=from_training)
  else:T.edge_training_hour(se,o,t,SOURCE,SOURCE,safe=safe)
  T._debit_points(t.spec,1)
  t.spec.setdefault('learned_poke_edges',[]).append({'source':SOURCE,'status':'active','point_cost':1,'trainer_id':o.entity_id,'acquired_level':t.level,'completed_at':se.elapsed_seconds,'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274'})
  import invisibility_state as V
  view=V.projection(se,t)
  if view['active'] is None:raise ValueError('observe invisibility elapsed time before extending current session')
  if view['active']:t.spec[V.KEY]['duration_seconds']=480
  if T.credit_mode(from_grooming,from_training):T.consume_credit(t,SOURCE,from_training=from_training)
  validate(t)
  return {'activity':'teach_edge','edge':SOURCE,'point_cost':1,'duration_seconds':480,'seconds':0 if (from_grooming or from_training) else 3600}
 return G.transition(e,target,apply,participants=(owner,))
