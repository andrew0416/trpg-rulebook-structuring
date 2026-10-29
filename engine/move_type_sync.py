"""Permanent, individual-owned Move Sync state for C11-053..055.

The source changes one learned Move on one Pokemon.  The shared Move catalog is
never mutated.  A completed GM decision records the new type and name and either
preserves the printed effects or replaces their payloads while keeping the same
executable effect kinds.  Acquisition cost and Type Ace prerequisites belong to
the separate feature activation contract.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json

import type_state as TYPES
import resolution_transaction as _FINGERPRINTS

SOURCE='ch11-running-the-game/타입-변경/기술-타입-변경'
KEY='move_type_sync'
MARKER='_move_type_sync'
POLICY='data/move-type-sync-policy.json'


def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
 return value.strip()


def _policy_path(rules):
 staged=Path(__file__).resolve().parents[1]/POLICY
 return staged if staged.exists() else Path(rules.root)/POLICY


def policy(rules):
 data=json.loads(_policy_path(rules).read_text(encoding='utf-8'))
 if data.get('schema_version')!=1 or data.get('source')!=SOURCE:raise ValueError('Move Sync policy identity changed')
 if rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Move Sync rule required')
 for file,digest in data.get('source_files',{}).items():
  if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('Move Sync source anchor changed')
 if data.get('clauses')!=['C11-053','C11-054','C11-055']:raise ValueError('Move Sync clause boundary changed')
 return data


def _digest(value):
 return _FINGERPRINTS.json_fingerprint(value, sort_keys=True, compact=True, allow_nan=True)


def _base(rules,move_id):
 mid=rules.move_id(move_id) if isinstance(move_id,str) else None
 if mid is None or mid not in rules.moves or rules._selected_rule(mid)!=mid:raise ValueError('selected canonical Move required')
 move=rules.move(mid);mechanics=rules.move_mech(mid)[0]
 return mid,move,mechanics,deepcopy(mechanics.get('effects_exec',[]))


def _effects(decision,base_effects,mechanics):
 if not isinstance(decision,dict) or set(decision)!={'mode','reason','effects_exec'}:
  raise ValueError('explicit Move Sync effect decision required')
 mode=decision['mode'];reason=_text(decision['reason'],'GM effect decision reason')
 if mode=='preserve':
  if decision['effects_exec'] is not None:raise ValueError('preserved Move effects cannot include replacements')
  return {'mode':mode,'reason':reason,'effects_exec':None}
 if mode!='replace':raise ValueError('Move Sync effects must be explicitly preserved or replaced')
 rows=decision['effects_exec']
 if not isinstance(rows,list) or not rows or len(rows)!=len(base_effects):
  raise ValueError('replacement must preserve the executable effect count')
 if set(mechanics)-{'effects_exec','header'}:
  raise ValueError('this Move has executable mechanics outside effects_exec; preserve them or add a reviewed adapter')
 out=[]
 for old,new in zip(base_effects,rows):
  if not isinstance(old,dict) or not isinstance(new,dict) or not isinstance(new.get('type'),str):
   raise ValueError('complete executable effect records required')
  if old.get('type')!=new.get('type'):
   raise ValueError('Move Sync replacement must preserve each executable effect kind')
  if any(str(key).startswith('_') for key in new):raise ValueError('effect provenance is source-owned')
  out.append(deepcopy(new))
 stripped=[{k:v for k,v in row.items() if not str(k).startswith('_')} for row in base_effects]
 if out==stripped:raise ValueError('replace decision must actually change an effect payload')
 return {'mode':mode,'reason':reason,'effects_exec':out}


def _owned(rules,spec):
 import move_state as MOVES
 return set(MOVES.known(rules,{'moves':MOVES.owned_list(spec,'moves',rules=rules)}))


def rows(spec):
 state=spec.get(KEY)
 return [] if state is None else state.get('history',[])


def active(rules,spec,move_id=None):
 validate_spec(rules,spec)
 found=[row for row in rows(spec) if row['status']=='active' and (move_id is None or row['move_id']==move_id)]
 if len(found)>1:raise ValueError('only one active Move Sync is permitted')
 return found[0] if found else None


def validate_spec(rules,spec):
 state=spec.get(KEY)
 if state is None:return True
 p=policy(rules)
 if spec.get('kind')!='pokemon' or not isinstance(state,dict) or set(state)!={'version','history'} or state['version']!=1:
  raise ValueError('invalid Pokemon Move Sync state')
 history=state['history']
 if not isinstance(history,list) or not history:raise ValueError('Move Sync history required')
 applications=set();active_rows=[];owned=_owned(rules,spec)
 required={'id','source','source_files','actor_id','move_id','base_type','synced_type','base_name','synced_name',
           'base_effects_sha256','effect_decision','feasibility_review','power_review','reason','at','status'}
 for row in history:
  if not isinstance(row,dict) or not required<=set(row):raise ValueError('complete Move Sync record required')
  uid=_text(row['id'],'Move Sync application identity')
  if uid in applications:raise ValueError('Move Sync application replay')
  applications.add(uid)
  if row['source']!=SOURCE or row['source_files']!=p['source_files'] or row['actor_id']!=spec.get('id'):
   raise ValueError('Move Sync source or individual identity changed')
  mid,base,mechanics,base_effects=_base(rules,row['move_id'])
  TYPES.validate_types(rules,[row['synced_type']],label='Move Sync selected type')
  if (mid!=row['move_id'] or row['base_type']!=base['type'] or row['base_name']!=base['name']
      or row['synced_type']==row['base_type'] or row['synced_name']==row['base_name']):
   raise ValueError('Move Sync permanent projection changed')
  _text(row['synced_name'],'renamed Move');_text(row['feasibility_review'],'Move feasibility review')
  _text(row['power_review'],'Move power review');_text(row['reason'],'Move Sync observation reason')
  if type(row['at']) is not int or row['at']<0:raise ValueError('Move Sync observed time required')
  if row['base_effects_sha256']!=_digest(base_effects):raise ValueError('Move Sync base effects changed')
  if _effects(row['effect_decision'],base_effects,mechanics)!=row['effect_decision']:
   raise ValueError('Move Sync effect decision changed')
  if row['status']=='active':
   if set(row)!=required:raise ValueError('active Move Sync record has invalid lifetime fields')
   if mid not in owned:raise ValueError('active Move Sync requires the actual learned Move')
   active_rows.append(row)
  elif row['status']=='forgotten':
   if set(row)!=required|{'forgotten_at','forgotten_reason'}:raise ValueError('forgotten Move Sync receipt incomplete')
   if type(row['forgotten_at']) is not int or row['forgotten_at']<row['at']:
    raise ValueError('Move Sync forgetting time precedes its application')
   _text(row['forgotten_reason'],'Move Sync forgetting reason')
  else:raise ValueError('explicit Move Sync lifetime required')
 if len(active_rows)>1:raise ValueError('a Pokemon can know only one Move-Synced Move at a time')
 return True


def observe(engine,actor,*,application_id,move_id,chosen_type,new_name,effect_decision,
            feasibility_review,power_review,reason):
 """Observe one completed Move Sync without inventing its feature payment."""
 if actor.kind!='pokemon':raise ValueError('Move Sync requires an actual Pokemon')
 validate_spec(engine.r,actor.spec)
 _text(application_id,'Move Sync application identity');_text(reason,'Move Sync observation reason')
 if any(row['id']==application_id for row in rows(actor.spec)):raise ValueError('Move Sync application already observed')
 if active(engine.r,actor.spec) is not None:raise ValueError('forget the active Move-Synced Move before selecting another')
 mid,base,mechanics,base_effects=_base(engine.r,move_id)
 import move_state as MOVES
 learned=set(MOVES.known(engine.r,{'moves':MOVES.owned_list(actor.spec,'moves',actor.moves,rules=actor.r)}))
 if mid not in learned:raise ValueError('Move Sync must select one actually learned Move')
 TYPES.validate_types(engine.r,[chosen_type],label='Move Sync selected type')
 if chosen_type==base['type']:raise ValueError('Move Sync must change the Move type')
 name=_text(new_name,'renamed Move')
 if name==base['name']:raise ValueError('a Move-Synced Move must be renamed')
 decision=_effects(effect_decision,base_effects,mechanics);p=policy(engine.r)
 feasibility=_text(feasibility_review,'Move feasibility review');power=_text(power_review,'Move power review')
 import state_grants as GRANTS
 def apply(e,c):
  validate_spec(e.r,c.spec)
  row={'id':application_id,'source':SOURCE,'source_files':deepcopy(p['source_files']),
       'actor_id':c.entity_id,'move_id':mid,'base_type':base['type'],'synced_type':chosen_type,
       'base_name':base['name'],'synced_name':name,'base_effects_sha256':_digest(base_effects),
       'effect_decision':deepcopy(decision),'feasibility_review':feasibility,'power_review':power,
       'reason':reason,'at':e.elapsed_seconds,'status':'active'}
  c.spec.setdefault(KEY,{'version':1,'history':[]})['history'].append(row)
  validate_spec(e.r,c.spec);e.log('    '+c.name+': permanent Move Sync '+base['name']+' → '+name,SOURCE)
  return deepcopy(row)
 return GRANTS.transition(engine,actor,apply)


def forget_spec(rules,spec,move_id,*,at,reason):
 """Close the permanent projection when its actual learned Move is forgotten."""
 validate_spec(rules,spec)
 row=next((entry for entry in rows(spec) if entry['status']=='active' and entry['move_id']==move_id),None)
 if row is None:return None
 row['status']='forgotten';row['forgotten_at']=at;row['forgotten_reason']=_text(reason,'Move Sync forgetting reason')
 validate_spec(rules,spec)
 return deepcopy(row)


def prepare(engine,actor,move):
 """Project the active individual type and renamed display value idempotently."""
 validate_spec(engine.r,actor.spec)
 record=active(engine.r,actor.spec,move.get('id'))
 marker=move.get(MARKER)
 if record is None:
  if marker is not None:raise ValueError('stale Move Sync projection')
  return move
 expected={'source':SOURCE,'application_id':record['id'],'actor_id':actor.entity_id,'move_id':record['move_id']}
 if marker is not None:
  if marker!=expected or move.get('type')!=record['synced_type'] or move.get('name')!=record['synced_name']:
   raise ValueError('Move Sync projection provenance changed')
  return move
 if move.get('type')!=record['base_type'] or move.get('name')!=record['base_name']:
  raise ValueError('Move Sync requires the selected catalog baseline')
 out=deepcopy(move);out['type']=record['synced_type'];out['name']=record['synced_name'];out[MARKER]=expected
 return out


def prepare_mechanics(engine,actor,move,mechanics):
 """Apply the GM's recorded effect decision to the actual actor's execution."""
 projected=prepare(engine,actor,move);marker=projected.get(MARKER)
 if marker is None:return projected,mechanics
 record=active(engine.r,actor.spec,projected['id']);out=deepcopy(mechanics)
 existing=out.get(MARKER)
 if existing is not None:
  if existing!=marker:raise ValueError('Move Sync mechanics provenance changed')
  return projected,out
 if record['effect_decision']['mode']=='replace':
  out['effects_exec']=deepcopy(record['effect_decision']['effects_exec'])
 out[MARKER]=deepcopy(marker)
 return projected,out
