"""An owned Connection Ability exempts its actual known linked Move slots."""
import state_fields as F,ability_transitions as A

SOURCE='poke_edge/고급-연결'
ALIASES={SOURCE:SOURCE,'고급 연결':SOURCE,'Advanced Connection':SOURCE}

def records(spec):
 return [row for row in spec.get('learned_poke_edges',[]) if row.get('source')==SOURCE]

def linked_moves(rules,ability):
 import ability_mastery as AM
 uid=AM.choice(rules,ability);name=A.label(rules,uid)
 linked={rules.move_id(fx['move']) for fx in rules.ability_effects.get(name,[])
         if isinstance(fx,dict) and fx.get('type')=='connection' and fx.get('move')}
 if not linked or None in linked:raise ValueError('Advanced Connection requires an actual Connection Ability with linked Moves')
 for mid in linked:rules._selected_rule(mid)
 return linked

def owned(rules,spec,ability,abilities=None):
 import move_state as M
 return any(A.ability_id(rules,name)==ability for name in M.owned_list(spec,'abilities',abilities))

def checked(rules,spec,*,allow_lost=False):
 import poke_edge_variants as V
 active=0
 for row in records(spec):
  V.validate_receipt(rules,row)
  if spec.get('kind')!='pokemon' or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('actual selected Pokemon Advanced Connection required')
  linked_moves(rules,row.get('ability'));F.integer(row.get('point_cost'),'Advanced Connection Tutor Point cost',1,1)
  if row.get('status')=='active':
   active+=1
   if not allow_lost and not owned(rules,spec,row['ability']):raise ValueError('lost Connection Ability requires actual refund')
  elif row.get('status')=='refunded':
   refund=row.get('refund',{})
   if refund.get('source')!='input/ch05-pokemon.md:274' or refund.get('points')!=1 or not refund.get('reason'):raise ValueError('actual Advanced Connection refund required')
  else:raise ValueError('explicit Advanced Connection lifetime required')
 if active>1:raise ValueError('Advanced Connection permits one actual selected Ability')
 return records(spec)

def validate(actor):checked(actor.r,actor.spec)

def exemptions(rules,spec,abilities=None):
 import move_state as M
 out={};known=set(M.known(rules,{'moves':M.owned_list(spec,'moves')}))
 for row in records(spec):
  if row['status']=='active' and owned(rules,spec,row['ability'],abilities):
   for mid in linked_moves(rules,row['ability'])&known:out[mid]=SOURCE+':'+row['ability']
 return out

def reconcile(actor,*,reason):
 rows=checked(actor.r,actor.spec,allow_lost=True)
 ending=[row for row in rows if row['status']=='active' and not owned(actor.r,actor.spec,row['ability'])]
 import acquisition_withdrawal as W
 for row in ending:
  W.refund_native_investments(actor.spec,[row],source='input/ch05-pokemon.md:274',
   reason=reason,lost_prerequisite={'ability':row['ability'],'owned':False})
 validate(actor)

def teach(engine,owner,target,definition,ability,*,from_grooming=False,from_training=False,safe=None):
 import pokemon_teaching as T
 T._pokemon(engine,owner,target);T.source(engine.r,SOURCE,T.POINTS);validate(target)
 linked_moves(engine.r,ability)
 if not owned(engine.r,target.spec,ability):raise ValueError('selected Connection Ability must actually be owned')
 if any(row['status']=='active' for row in records(target.spec)):raise ValueError('Advanced Connection already acquired')
 if T._balance(target.spec)<1:raise ValueError('Advanced Connection costs one Tutor Point')
 if T.credit_mode(from_grooming,from_training):T.training_credit(engine,owner,target,SOURCE,from_training=from_training)
 else:T.edge_training_hour(engine,owner,target,SOURCE,SOURCE,safe=safe)
 if not owned(engine.r,target.spec,ability):raise ValueError('actual Connection Ability must survive completed training')
 target.spec.setdefault('learned_poke_edges',[]).append({'source':SOURCE,'status':'active','ability':ability,'point_cost':1,
  'trainer_id':owner.entity_id,'acquired_level':target.level,'completed_at':engine.elapsed_seconds,
  'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274',
  'definition_origin':{k:definition[k] for k in ('clause_id','rule_id','record')}})
 T._debit_points(target.spec,1)
 if T.credit_mode(from_grooming,from_training):T.consume_credit(target,SOURCE,from_training=from_training)
 validate(target)
 return {'activity':'teach_edge','edge':SOURCE,'ability':ability,'point_cost':1,'seconds':0 if (from_grooming or from_training) else 3600}
