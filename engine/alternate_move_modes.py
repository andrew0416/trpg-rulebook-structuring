"""Explicit scene-limited alternate-type modes for reviewed Moves.

The printed Move remains the default.  A player/GM choice is recorded on the
actual Pokemon, then the ordinary Move activation consumes that choice before
accuracy is resolved.  The receipt therefore survives misses, snapshots and
JSON state restore without borrowing the Move's normal frequency counter.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json

KEY='alternate_move_modes'
POLICY='data/alternate-move-mode-policy.json'


def _text(value,label):
 if not isinstance(value,str) or not value.strip():raise ValueError(label+' required')
 return value.strip()


def _policy_path(rules):
 staged=Path(__file__).resolve().parents[1]/POLICY
 return staged if staged.exists() else Path(rules.root)/POLICY


def policy(rules):
 data=json.loads(_policy_path(rules).read_text(encoding='utf-8'))
 if data.get('schema_version')!=1 or data.get('contract')!='explicit_scene_alternate_move_type':
  raise ValueError('alternate Move mode policy identity changed')
 for path,digest in data.get('source_files',{}).items():
  if hashlib.sha256((Path(rules.root)/path).read_bytes()).hexdigest()!=digest:
   raise ValueError('alternate Move mode source anchor changed: '+path)
 if set(data.get('moves',{}))!={'move/타오르는분노','move/천둥차기','move/얼어붙는시선'}:
  raise ValueError('alternate Move mode source boundary changed')
 return data


def definition(rules,move_id):
 row=policy(rules)['moves'].get(move_id)
 if row is None:return None
 if rules._selected_rule(move_id)!=move_id:raise ValueError('selected alternate-type Move source changed')
 move=rules.move(move_id);mechanics=rules.move_mech(move_id)[0]
 expected=[row['secondary_effect'],{'type':'alternate_type','move_type':row['alternate_type'],'limit':'scene x1'}]
 actual=[{key:value for key,value in effect.items() if not key.startswith('_')} for effect in mechanics.get('effects_exec',[])]
 if move.get('type')!=row['base_type'] or actual!=expected:
  raise ValueError('alternate-type Move definition changed from reviewed source')
 return row


def owns(rules,move,effect):
 mid=move.get('id') if isinstance(move,dict) else None
 row=definition(rules,mid) if mid in policy(rules)['moves'] else None
 return bool(row and effect=={'type':'alternate_type','move_type':row['alternate_type'],'limit':'scene x1'})


def _scene(actor):
 import frequency as FREQ
 return FREQ.state(actor)['scene']


def history(actor):
 state=actor.spec.get(KEY)
 return [] if state is None else state.get('history',[])


def _usage_status(actor,record):
 if record.get('use') is not None:return 'used'
 return 'pending' if record['scene']==_scene(actor) else 'expired'


def validate_actor(actor):
 state=actor.spec.get(KEY)
 if state is None:return True
 if actor.spec.get('kind')!='pokemon' or not isinstance(state,dict) or set(state)!={'version','history'} or state['version']!=1:
  raise ValueError('alternate Move mode state requires a Pokemon-owned versioned history')
 rows=state['history']
 if not isinstance(rows,list):raise ValueError('alternate Move mode history must be a list')
 seen=set()
 for record in rows:
  if not isinstance(record,dict):raise ValueError('alternate Move mode record required')
  required={'id','actor_id','move_id','clause_id','source_row_sha256','base_type','alternate_type','scene','selected_at','reason','lifetime','use'}
  if set(record)!=required:raise ValueError('alternate Move mode record shape changed')
  row=definition(actor.r,record.get('move_id'))
  if row is None:raise ValueError('alternate Move mode needs its exact reviewed Move')
  if record['actor_id']!=actor.entity_id or record['clause_id']!=row['clause_id'] or record['source_row_sha256']!=row['source_row_sha256']:
   raise ValueError('alternate Move mode ownership or provenance changed')
  if record['base_type']!=row['base_type'] or record['alternate_type']!=row['alternate_type']:
   raise ValueError('alternate Move mode type projection changed')
  if type(record['scene']) is not int or record['scene']<0 or record['scene']>_scene(actor):
   raise ValueError('alternate Move mode scene is invalid')
  if record['lifetime']!={'boundary':'scene','scene':record['scene']}:
   raise ValueError('alternate Move mode lifetime changed')
  _text(record['id'],'alternate Move mode id');_text(record['reason'],'alternate Move mode reason')
  if type(record['selected_at']) is not int or record['selected_at']<0:raise ValueError('alternate Move mode selection time invalid')
  identity=(record['move_id'],record['scene'])
  if identity in seen:raise ValueError('alternate Move type can be selected only once per Move per scene')
  seen.add(identity)
  use=record['use']
  if use is not None:
   if not isinstance(use,dict) or set(use)!={'move_id','scene','at','target_id','targetless','actual_type'}:
    raise ValueError('alternate Move mode use receipt shape changed')
   if use['move_id']!=record['move_id'] or use['scene']!=record['scene'] or use['actual_type']!=record['alternate_type']:
    raise ValueError('alternate Move mode was consumed by a different activation')
   if type(use['at']) is not int or use['at']<record['selected_at'] or type(use['targetless']) is not bool:
    raise ValueError('alternate Move mode activation evidence invalid')
   if use['targetless'] is (use['target_id'] is not None):
    raise ValueError('alternate Move mode target evidence invalid')
   if use['target_id'] is not None:_text(use['target_id'],'alternate Move target identity')
 return True


def validate_world(engine,index):
 for actor in index.values():
  validate_actor(actor)
  for record in history(actor):
   use=record['use']
   if use is not None and use['target_id'] is not None and use['target_id'] not in index:
    raise ValueError('alternate Move mode use references a missing target')
   if record['selected_at']>engine.elapsed_seconds or (use is not None and use['at']>engine.elapsed_seconds):
    raise ValueError('alternate Move mode record references future time')
 return True


def choose(engine,actor,move_id,alternate_type,*,reason):
 import world_entities as WORLD
 WORLD.require_actors(engine,actor);validate_actor(actor)
 mid=engine.r.move_id(move_id)
 row=definition(engine.r,mid)
 if row is None:raise ValueError('Move has no reviewed alternate-type mode')
 if actor.spec.get('kind')!='pokemon':raise ValueError('alternate Move mode requires an actual Pokemon')
 if mid not in actor.moves:raise ValueError('Pokemon must currently know the selected Move')
 if alternate_type!=row['alternate_type']:raise ValueError('selected alternate type differs from the source')
 scene=_scene(actor)
 if any(record['move_id']==mid and record['scene']==scene for record in history(actor)):
  raise ValueError('alternate Move type already selected or used this scene')
 if actor.type_override_next is not None:
  raise ValueError('resolve the pending next-Move type override before selecting this mode')
 record={'id':f'alternate:{actor.entity_id}:{mid}:{scene}','actor_id':actor.entity_id,
  'move_id':mid,'clause_id':row['clause_id'],'source_row_sha256':row['source_row_sha256'],
  'base_type':row['base_type'],'alternate_type':row['alternate_type'],'scene':scene,
  'selected_at':engine.elapsed_seconds,'reason':_text(reason,'selection reason'),
  'lifetime':{'boundary':'scene','scene':scene},'use':None}
 state=deepcopy(actor.spec.get(KEY,{'version':1,'history':[]}));state['history'].append(record)
 before=deepcopy(actor.spec.get(KEY));actor.spec[KEY]=state
 try:validate_actor(actor)
 except BaseException:
  if before is None:actor.spec.pop(KEY,None)
  else:actor.spec[KEY]=before
  raise
 engine.log(f'    {actor.name}: {engine.r.move(mid)["name"]}을(를) {alternate_type}타입으로 선택 (장면당 1회)',mid)
 return deepcopy(record)


def begin_move_use(engine,actor,target,move,mechanics,*,targetless=False):
 """Consume one explicit choice at the authenticated native activation."""
 validate_actor(actor)
 row=definition(engine.r,move.get('id')) if move.get('id') in policy(engine.r)['moves'] else None
 if row is None:return None
 current=__import__('move_activation')._require_started_event_use(engine,actor,target,move['id'],
  scope_error='alternate Move mode requires an actual native Move activation')
 group=__import__('move_activation').current_scope(engine,actor,target,move['id'])
 cached=group.get('alternate_move_mode') if group is not None else None
 if cached is not None:
  current['alternate_move_mode']=cached
  return cached['actual_type']
 pending=next((record for record in history(actor) if record['move_id']==move['id'] and record['scene']==_scene(actor) and record['use'] is None),None)
 if pending is None:
  current['alternate_move_mode']={'actual_type':row['base_type'],'receipt_id':None}
  if group is not None:group['alternate_move_mode']=current['alternate_move_mode']
  return row['base_type']
 if actor.type_override_next is not None:
  raise ValueError('alternate Move mode cannot consume beside a pending next-Move type override')
 use={'move_id':move['id'],'scene':_scene(actor),'at':engine.elapsed_seconds,
      'target_id':None if targetless else target.entity_id,'targetless':targetless,
      'actual_type':row['alternate_type']}
 pending['use']=use;validate_actor(actor)
 current['alternate_move_mode']={'actual_type':row['alternate_type'],'receipt_id':pending['id']}
 if group is not None:group['alternate_move_mode']=current['alternate_move_mode']
 engine.log(f'    타입 선택 사용: {row["base_type"]} → {row["alternate_type"]} (장면당 1회)',move['id'])
 return row['alternate_type']


def effective_type(engine,actor,target,move):
 if move.get('id') not in policy(engine.r)['moves']:return None
 scopes=getattr(engine,'_event_use_scopes',())
 if not scopes:return None
 current=scopes[-1]
 if current.get('actor') is not actor or current.get('target') is not target or current.get('move_id')!=move['id']:
  return None
 mode=current.get('alternate_move_mode')
 return None if mode is None else mode['actual_type']


def status(actor,move_id):
 validate_actor(actor)
 return [dict(deepcopy(record),status=_usage_status(actor,record)) for record in history(actor) if record['move_id']==move_id]
