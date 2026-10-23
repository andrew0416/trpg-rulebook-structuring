"""Source-owned roll components: one instance, independent consumption events.

Stored in the existing timed-effect container. Remaining benefits are derived
from the component definitions and application history, never mirrored flags.
"""
from pathlib import Path
from copy import deepcopy
import hashlib,json
import common_checks as C, effect_instances as E, combat_timing as T

KIND='roll_components'
HISTORY='effect_instance_history'

def policy(rules):
 data=getattr(rules,'_roll_effect_policy',None)
 if data is None:
  data=json.loads((Path(rules.root)/'data/roll-effect-policy.json').read_text(encoding='utf-8'))
  for file,digest in data['source_files'].items():
   if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('roll-buff source changed: '+file)
  C.integer(data.get('schema_version'),'roll-effect policy version',1,1)
  for source,row in data['sources'].items():
   E.text(source,'roll-effect source')
   if row.get('window')!='current_round_end' or row.get('payload',{}).get('kind')!='independent_roll_components':raise ValueError('unsupported roll-component lifetime or payload kind')
   components=row['payload'].get('components')
   if not isinstance(components,dict) or not components or set(components)-{'accuracy','damage'}:raise ValueError('unsupported roll-component consumers')
   for key,spec in components.items():
    if not isinstance(spec,dict) or set(spec)!={'event','amount'} or spec['event']!=key+'_roll':raise ValueError('unsupported roll-component selector')
    C.integer(spec['amount'],'sourced roll contribution')
  rules._roll_effect_policy=data
 return data

def definition(rules,source):
 row=policy(rules)['sources'].get(source)
 if row is not None and rules._selected_rule(source)!=source:raise ValueError('selected roll-buff source changed')
 return row

def same(a,b):return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)
def semantic(effect):return {k:v for k,v in effect.items() if not k.startswith('_')}
def live(actor):return [r for r in T.records(actor) if isinstance(r,dict) and isinstance(r.get(E.KEY),dict) and r[E.KEY].get('kind')==KIND]
def closed(actor):return [r for r in actor.spec.get(HISTORY,[]) if isinstance(r,dict) and isinstance(r.get(E.KEY),dict) and r[E.KEY].get('kind')==KIND]
def remaining(record):return set(record['effect']['components'])-{a['component'] for a in record['applications']}

def validate_record(actor,record,*,terminal=False):
 E.validate(record,actor=actor,terminal=terminal)
 row=definition(actor.r,record['source']);meta=record[E.KEY]
 if row is None or not same(record['effect'],row['payload']):raise ValueError('roll components differ from selected source')
 if meta['kind']!=KIND or meta['capacity']!={'bucket':'one_active_source_per_holder','source':record['source']}:raise ValueError('roll-component capacity changed')
 if len(meta['ownership'])!=1 or not meta.get('applied_by_actor_id'):raise ValueError('roll buff requires its actual issuer and defines no transfer')
 born=C.integer(record.get('issued_round'),'roll-buff issuing round',1)
 if meta['lifetime']!={'boundary':'current_round_end','round':born} or record.get('round_end_deadline')!=born or type(record.get('round_end_deadline')) is not int or record.get('manual_end') is not True:raise ValueError('roll-buff round lifetime changed')
 if any(k in record for k in ('turn_owner','turn_deadline','turn_start_deadline','count_deadline')):raise ValueError('roll buff cannot inherit a different clock')
 applications=record.get('applications');seen=set()
 if not isinstance(applications,list):raise ValueError('roll-component applications must be a list')
 for event in applications:
  if not isinstance(event,dict):raise ValueError('typed roll observation required')
  component=event.get('component');spec=row['payload']['components'].get(component)
  if spec is None or component in seen or event.get('kind')!=spec['event'] or type(event.get('amount')) is not int or event['amount']!=spec['amount']:raise ValueError('roll component consumed twice or changed')
  seen.add(component);C.integer(event.get('at'),'roll observation time',record['at']);C.integer(event.get('round'),'roll observation round',born,born)
  E.text(event.get('move_id'),'actual roll Move')
  targets=event.get('target_ids')
  if not isinstance(targets,list) or not targets or any(not isinstance(x,str) or not x for x in targets) or len(set(targets))!=len(targets):raise ValueError('distinct actual roll targets required')
  if component=='accuracy':C.integer(event.get('natural'),'actual accuracy die',1,20)
  else:
   C.integer(event.get('damage_base'),'actual damage base',1,28);C.integer(event.get('roll_value'),'actual base damage roll',0)
   if event.get('mode') not in ('random','set','fixed_dice'):raise ValueError('actual damage-roll mode required')
 if terminal:
  end=meta['end_event'];C.integer(end.get('round'),'roll-buff ending round',born,born)
  if meta['state']=='consumed':
   if remaining(record) or end.get('kind')!='components_spent':raise ValueError('all components must actually be spent before consumption')
  elif end.get('kind') not in ('round_end','encounter_end'):raise ValueError('roll buff needs an actual round/encounter ending')
 return True

def validate_actor(actor):
 seen=set()
 for record in live(actor):
  validate_record(actor,record)
  if not remaining(record):raise ValueError('spent roll buff must be archived')
  if record['source'] in seen:raise ValueError('same-source roll buff composition needs an explicit ruling')
  seen.add(record['source'])
 for record in closed(actor):validate_record(actor,record,terminal=True)
 return True

def validate_world(engine,index):
 for actor in index.values():
  validate_actor(actor)
  for record in live(actor)+closed(actor):
   if record['issued_round']>engine.round_no:raise ValueError('roll buff belongs to a future round')
   if record in live(actor) and (not engine.encounter_active or engine.round_start_seconds is None or record['issued_round']!=engine.round_no):raise ValueError('roll-buff round passed without expiry')
   for event in record['applications']:
    if event['at']>engine.elapsed_seconds or any(uid not in index for uid in event['target_ids']):raise ValueError('roll observation references missing target or future time')
 return True

def require_origin(actor,component=None):
 legacy=getattr(actor,'next_attack',None)
 keys=(component,) if component else ('accuracy','damage')
 if isinstance(legacy,dict) and any(legacy.get(k) for k in keys):raise ValueError('legacy roll bonus needs explicit source/lifetime reconciliation')

def preflight_move(engine,actor,target,move,mechanics):
 import move_accuracy as ACCURACY
 if not ACCURACY.no_status_check(engine,actor,target,move,mechanics):require_origin(actor,'accuracy')
 if move.get('class') in ('물리','특수'):require_origin(actor,'damage')

def preflight(engine,issuer,holder,effect,source):
 row=definition(engine.r,source)
 if row is None:raise ValueError('roll buff needs a reviewed source-specific component policy')
 if not same(semantic(effect),row['raw']):raise ValueError('roll-buff fields differ from selected source')
 if not engine.encounter_active or engine.round_start_seconds is None:raise ValueError('this-round roll buff requires an open actual round')
 import world_entities as W
 index=W.actor_index(engine,extra=(issuer,holder));E.validate_world(engine,index)
 require_origin(holder)
 if any(r['source']==source for r in live(holder)):raise ValueError('same-source roll buff composition needs an explicit ruling')
 return row

def grant(engine,issuer,holder,effect,source):
 row=preflight(engine,issuer,holder,effect,source)
 record=E.create(engine,holder,kind=KIND,source=source,payload=row['payload'],capacity={'bucket':'one_active_source_per_holder','source':source},lifetime={'boundary':'current_round_end','round':engine.round_no},applied_by=issuer)
 record.update(issued_round=engine.round_no,round_end_deadline=engine.round_no,manual_end=True,applications=[])
 T.install(engine,holder,record);validate_record(holder,record)
 engine.log(f'    {holder.name}: 독립 소비 굴림 효과 {record["id"]}',source)
 return record

def accuracy_scope(engine,actor,target,move,shared_roll):
 scope=__import__('move_activation').current_scope(engine,actor,target,move['id'])
 if shared_roll is None:return None,None
 if scope is None or scope['accuracy'] is not shared_roll or type(scope.get('actual_accuracy_index')) is not int:
  if any('accuracy' in remaining(r) for r in live(actor)):raise ValueError('shared roll bonus requires actual native accuracy-group authority')
  return None,None
 return scope,scope['actual_accuracy_index']

def preflight_accuracy(engine,actor,target,move,shared_roll):
 require_origin(actor,'accuracy');validate_actor(actor);accuracy_scope(engine,actor,target,move,shared_roll)

def use(engine,actor,target,move,component,facts,*,shared_roll=None):
 validate_actor(actor);require_origin(actor,component)
 scope,index=accuracy_scope(engine,actor,target,move,shared_roll) if component=='accuracy' else (None,None)
 cache=scope.setdefault('roll_component_uses',{}) if scope is not None else None
 if cache is not None and index in cache:
  total=0
  for entry in cache[index]:
   record=next(r for r in live(actor)+closed(actor) if r['id']==entry['id'])
   event=next(x for x in record['applications'] if x['component']==component)
   if event['natural']!=facts['natural'] or event['move_id']!=move['id']:raise ValueError('shared roll observation changed')
   if target.entity_id not in event['target_ids']:event['target_ids'].append(target.entity_id)
   total+=event['amount']
  return total
 chosen=[r for r in live(actor) if component in remaining(r)];total=0;used=[]
 for record in chosen:
  spec=record['effect']['components'][component]
  event=dict(component=component,kind=spec['event'],amount=spec['amount'],at=engine.elapsed_seconds,round=engine.round_no,move_id=move['id'],target_ids=[target.entity_id],**facts)
  record['applications'].append(event);total+=spec['amount'];used.append({'id':record['id']})
  if not remaining(record):T.expire(engine,actor,record,ending='consumed',event={'kind':'components_spent','round':engine.round_no})
  engine.log(f'    굴림 보너스 {component} +{spec["amount"]}: {record["id"]}',record['source'])
 if cache is not None:cache[index]=used
 import equipment_variant_contracts as EQUIPMENT_VARIANTS
 if component=='damage':total+=EQUIPMENT_VARIANTS.damage_roll_bonus(engine,actor,move)
 return total

def end_encounter(engine):
 for actor in engine.time_actors():
  for record in list(live(actor)):T.expire(engine,actor,record,event={'kind':'encounter_end','round':engine.round_no})
