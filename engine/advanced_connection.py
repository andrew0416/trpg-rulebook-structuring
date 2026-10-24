"""An owned Connection Ability exempts its actual known linked Move slots.

The Connection keyword itself also lives here: gaining the Ability learns its Move and the
learned Move cannot be forgotten, including after Ability loss. Transform alone restores
its explicitly previous Move List when that form ends.
"""
from copy import deepcopy
from math import isfinite
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

def ability_values(rules,spec):
 return A.owned_from_spec(rules,spec)


def owned(rules,spec,ability,abilities=None):
 return any(A.ability_id(rules,name)==ability for name in ability_values(rules,spec))


def checked(rules,spec,*,allow_lost=False):
 import poke_edge_variants as V
 active=0
 for row in records(spec):
  V.validate_receipt(rules,row,history=True,minimum_level=1)
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

def validate(actor):
 checked(actor.r,actor.spec);validate_protection(actor.r,actor.spec)

def exemptions(rules,spec,abilities=None):
 import move_state as M
 out={};known=set(M.known(rules,{'moves':M.owned_list(spec,'moves')}))
 for row in records(spec):
  if row['status']=='active' and owned(rules,spec,row['ability'],abilities):
   for mid in linked_moves(rules,row['ability'])&known:out[mid]=SOURCE+':'+row['ability']
 return out

# Connection keyword (official PTU 1.05 Core p.310; the Korean ch10:178 keeps only the static
# relation): upon gaining the Ability the user learns the Move, forgetting another Move if
# necessary; the Move cannot be forgotten; with 1 Tutor Point the user may immediately take
# Advanced Connection instead of forgetting.
KEYWORD='keyword/연결'
PROMPT='connection_keyword'


def _linked_by_name(rules,name):
 try:
  uid=A.ability_id(rules,name);key=A.label(rules,uid)
 except ValueError:
  uid=None;key=name.split('/',1)[1] if name.startswith('ability/') else name
 linked={rules.move_id(fx['move']) for fx in rules.ability_effects.get(key,[])
         if isinstance(fx,dict) and fx.get('type')=='connection' and fx.get('move')}
 linked.discard(None)
 return uid or name,linked


PROTECTION='connection_moves'


def validate_protection(rules,spec):
 import move_state as M
 rows=spec.get(PROTECTION,{})
 if type(rows)is not dict:raise ValueError('Connection protection requires actual acquisition records')
 known=set(M.known(rules,{'moves':M.owned_list(spec,'moves')}))
 for mid,row in rows.items():
  if (type(row)is not dict or set(row)!={'ability','actor_id','source','acquired_at','reason','acquisitions'}
      or row['actor_id']!=spec.get('id') or row['source']!=KEYWORD
      or type(row['acquired_at']) not in (int,float) or not isfinite(row['acquired_at']) or row['acquired_at']<0
      or type(row['acquisitions'])is not int or row['acquisitions']<1
      or type(row['reason'])is not str or not row['reason']
      or mid not in linked_moves(rules,row['ability'])):
   raise ValueError('actual Connection learning protection provenance required')
  if mid not in known:raise ValueError('a Connection Move cannot be forgotten through any means: '+mid)
 # Old native learning receipts also retain protection; imports gain no receipt.
 for row in spec.get('move_learning_log',[]):
  if row.get('source')==KEYWORD and row.get('learning_contract')==1:
   if row.get('paid_tp')!=0 or row.get('move_id') not in linked_moves(rules,row.get('connection_ability')):
    raise ValueError('actual free Connection learning receipt required')
   if row['move_id'] not in known:raise ValueError('a Connection Move cannot be forgotten through any means: '+row['move_id'])
 for sid,source in spec.get('state_grants',{}).get('sources',{}).items():
  if 'connection_moves' not in source:continue
  overlay=spec['state_grants'].get('overlays',{}).get(sid,{})
  if source.get('rule_id')!='move/변신' or 'moves' not in overlay:raise ValueError('Transform Connection needs its actual form Move List')
  if type(source['connection_moves'])is not dict:raise ValueError('Transform Connection needs a source-owned Move mapping')
  for mid,ability in source['connection_moves'].items():
   if mid not in linked_moves(rules,ability) or mid not in M.known(rules,overlay):
    raise ValueError('a transformed Connection Move cannot be forgotten before form restoration')


def bound_moves(rules,spec,abilities=None):
 import move_state as M
 known=set(M.known(rules,{'moves':M.owned_list(spec,'moves')}))
 out={mid:row['ability'] for mid,row in spec.get(PROTECTION,{}).items()}
 for row in spec.get('move_learning_log',[]):
  if row.get('source')==KEYWORD and row.get('learning_contract')==1:out[row['move_id']]=row['connection_ability']
 for name in ability_values(rules,spec):
  ability,linked=_linked_by_name(rules,name)
  for mid in sorted(linked&known):out.setdefault(mid,ability)
 return out


def forbid_forgetting(actor,values):
 rules=actor.r;kept={rules.move_id(value) for value in values}
 for value in actor.spec.get('moves',[]):
  mid=rules.move_id(value)
  if mid not in kept and mid in bound_moves(rules,actor.spec):
   raise ValueError('a Connection Move cannot be forgotten through any means: '+mid)


def _all_abilities(rules,spec):
 import move_state as M
 return {_linked_by_name(rules,name)[0] for name in [*M.owned_list(spec,'abilities'),*ability_values(rules,spec)]}


def gained(engine,actor,before,*,reason):
 """Compare actual acquisition against prior ownership, never registration/import alone."""
 import acquired_features as ACQUIRED,move_state as M
 previous=_all_abilities(actor.r,before.spec);results=[]
 for ability in sorted(_all_abilities(actor.r,actor.spec)-previous):
  _,linked=_linked_by_name(actor.r,ability)
  if not linked:continue
  if any(row['ability']==ability and before.spec.get(PROTECTION,{}).get(mid)!=row for mid,row in actor.spec.get(PROTECTION,{}).items()):continue
  sources=actor.spec.get('state_grants',{}).get('sources',{})
  overlays=actor.spec.get('state_grants',{}).get('overlays',{})
  transform=next((sid for sid,row in reversed(list(overlays.items())) if sources.get(sid,{}).get('rule_id')=='move/변신'
                 and ability in {_linked_by_name(actor.r,x)[0] for x in row.get('abilities',[])}),None)
  if transform is not None and ability not in {_linked_by_name(actor.r,x)[0] for x in M.owned_list(actor.spec,'abilities')}:
   if ability not in sources[transform].get('connection_moves',{}).values():
    results.append(_learn(engine,actor,ability,linked,reason=reason,transform=transform))
   continue
  grants=[row for row in sources.values() if ability in {_linked_by_name(actor.r,x)[0] for x in row.get('grants',{}).get('abilities',[])}]
  # A fixed grant projected from an already-owned imported Feature is registration.
  if (ability not in {_linked_by_name(actor.r,x)[0] for x in actor.spec.get('abilities',[])} and grants
      and all((row.get('source_contract')=='acquired_static_feature_state_projection' or 'projection_ability_ids' in row or 'effect_sources' in row)
              and row.get('owner_id')==actor.entity_id and (row.get('rule_id') or '').startswith(('feat/','class/'))
              and ACQUIRED.owned_rule_count(before,row['rule_id']) for row in grants)):continue
  results.append(_learn(engine,actor,ability,linked,reason=reason))
 return results


def birth(engine,actor,egg,*,reason):
 """The native birth owner calls once after final traits and owner projection."""
 import creation_egg as E,pokemon_entities as P,world_entities as W
 W.require_actors(engine,actor)
 entry=P.egg_index(engine).get(actor.spec.get('egg_entity_id'))
 if entry is None or entry[1] is not egg or egg.get('pokemon_id')!=actor.entity_id or not egg.get('hatched'):
  raise ValueError('actual registered native birth origin required for Connection gain')
 E.lineage(engine,actor)
 if E.CONTRACT in egg:E.validate_binding(engine,egg)
 results=[]
 for ability in sorted(_all_abilities(actor.r,actor.spec)):
  _,linked=_linked_by_name(actor.r,ability)
  if not linked:continue
  # An owner projection may already have acquired this same Ability natively.
  if all(actor.spec.get(PROTECTION,{}).get(mid,{}).get('ability')==ability for mid in linked):continue
  results.append(_learn(engine,actor,ability,linked,reason='native birth '+egg['entity_id']+': '+reason))
 return results


def _learn(engine,c,ability,linked,*,reason,transform=None):
 import move_state as M,learning_grant as L,pokemon_teaching as T,state_grants as G,common_checks as CC
 rules=c.r
 if rules._selected_rule(KEYWORD)!=KEYWORD:raise ValueError('selected Connection keyword source required')
 destination=c.spec if transform is None else c.spec[G.KEY]['overlays'][transform]
 # Source-owned known Moves become independently learned by this new keyword gain.
 missing=sorted(linked-set(M.known(rules,destination)))
 state=M.describe(rules,c.spec)
 present=set(M.known(rules,{'moves':M.owned_list(c.spec,'moves')})) if transform is None else set(M.known(rules,destination))
 used=state['slot_count'] if transform is None else len(present-set(state['exempt']))
 full=state['total'] is not None and used+len(set(missing)-present)>state['total']
 points=c.spec.get('tutor_points',0)
 CC.integer(points,'actual remaining Tutor Points',0)
 edge=any(row.get('status')=='active' for row in records(c.spec))
 choice=None
 if full or (c.kind=='pokemon' and points>=1 and not edge):
  choice=engine.rulings.decide({'type':PROMPT,'unit':KEYWORD,'actor':c.name,'actor_id':c.entity_id,'ability':ability,
   'moves':list(missing),'move_list_full':full,'tutor_points':points,
   'text':'Connection: name one known Move to forget, or spend 1 Tutor Point on Advanced Connection.'})
 forget=None;advanced=False
 if choice is not None:
  if (type(choice) is not dict or choice.get('actor_id')!=c.entity_id or choice.get('ability')!=ability
      or set(choice) not in ({'actor_id','ability','forget'},{'actor_id','ability','advanced_connection'})):
   raise ValueError('explicit Connection choice must name this actor, Ability and one option')
  if 'forget' in choice:
   forget=rules.move_id(choice['forget']) if isinstance(choice['forget'],str) else None
   if not full:raise ValueError('Connection forgets another Move only when necessary')
   if forget is None or forget not in M.known(rules,destination) or forget in linked:
    raise ValueError('Connection forgets one actually known permanent Move')
  elif choice['advanced_connection'] is not True:raise ValueError('explicit Advanced Connection choice required')
  else:advanced=True
 if full and forget is None and not advanced:
  raise ValueError('known Moves are full: Connection needs an explicit forgotten Move or immediate Advanced Connection')
 if advanced:
  import ability_mastery as AM,poke_edge_variants as V
  if c.kind!='pokemon':raise ValueError('Advanced Connection requires a Pokemon recipient')
  if edge:raise ValueError('Advanced Connection already acquired')
  if points<1:raise ValueError('immediate Advanced Connection costs one actual Tutor Point')
  rows=[row for row in V.catalog(rules) if row['policy']==SOURCE]
  if len(rows)!=1:raise ValueError('one selected Advanced Connection definition required')
  V.selected(rules,rows[0])
  c.spec.setdefault('learned_poke_edges',[]).append({'source':SOURCE,'status':'active','ability':AM.choice(rules,ability),
   'point_cost':1,'trainer_id':c.spec.get('trainer_id'),'acquired_level':c.level,'completed_at':engine.elapsed_seconds,
   'training_source':KEYWORD,'definition_origin':{k:rows[0][k] for k in ('clause_id','rule_id','record')}})
  T._debit_points(c.spec,1)
 if transform is not None:
  if forget is not None:
   if forget in c.spec[G.KEY]['sources'][transform].get('connection_moves',{}):raise ValueError('a Connection Move cannot be forgotten through any means')
   destination['moves']=[m for m in destination['moves'] if rules.move_id(m)!=forget]
  destination['moves'].extend(mid for mid in missing if mid not in destination['moves'])
  c.spec[G.KEY]['sources'][transform].setdefault('connection_moves',{}).update({mid:ability for mid in linked})
  G.materialize(c,'moves')
 else:
  candidate=deepcopy(c.spec);candidate.setdefault('moves',[])
  if forget is not None:
   import move_type_sync as MOVE_SYNC
   forbid_forgetting(c,[m for m in candidate['moves'] if rules.move_id(m)!=forget])
   MOVE_SYNC.forget_spec(rules,candidate,forget,at=engine.elapsed_seconds,reason=reason)
   candidate['moves']=[m for m in candidate['moves'] if rules.move_id(m)!=forget]
  if missing:
   L.learn_moves(rules,candidate,candidates=list(missing),selected=list(missing),method='feature',source=KEYWORD,
    reason=reason,details={'connection_ability':ability},replaced=forget)
  for field in ('move_learning','move_learning_log',M.HISTORY,'move_type_sync'):
   if field in candidate:c.spec[field]=candidate[field]
  G.set_baseline(c,'moves',candidate['moves'])
  for mid in linked:
   previous=c.spec.setdefault(PROTECTION,{}).get(mid,{})
   c.spec[PROTECTION][mid]={'ability':ability,'actor_id':c.entity_id,'source':KEYWORD,
    'acquired_at':engine.elapsed_seconds,'reason':reason,'acquisitions':previous.get('acquisitions',0)+1}
 checked(rules,c.spec,allow_lost=True);validate_protection(rules,c.spec)
 return {'ability':ability,'learned':list(missing),'forgotten':forget,'advanced_connection':advanced}


def reconcile(actor,*,reason,engine=None,before=None):
 rows=checked(actor.r,actor.spec,allow_lost=True)
 ending=[row for row in rows if row['status']=='active' and not owned(actor.r,actor.spec,row['ability'])]
 import acquisition_withdrawal as W
 for row in ending:
  W.refund_native_investments(actor.spec,[row],source='input/ch05-pokemon.md:274',
   reason=reason,lost_prerequisite={'ability':row['ability'],'owned':False})
 if engine is not None and before is not None:
  gained(engine,actor,before,reason='Connection keyword on a newly gained Ability: '+reason)
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
