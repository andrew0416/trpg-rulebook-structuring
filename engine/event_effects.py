"""Source-owned next-hit effects and future own-turn damage windows.

Instances share identity/history with food effects and use the existing combat
turn lifecycle. Eligibility belongs to the future event, never the cast-time
predicate. Source definitions remain data, with exact native admission.
"""
from copy import deepcopy
from pathlib import Path
import json,hashlib
import common_checks as C
import effect_instances as E
import combat_timing as T

KIND='event_effect'
HISTORY='effect_instance_history'
LASER='move/예민해지기'
LASER_CHOICE='laser_focus_source'

def policy(rules):
 data=getattr(rules,'_event_effect_policy',None)
 if data is None:
  data=json.loads((Path(rules.root)/'data/event-effect-policy.json').read_text(encoding='utf-8'))
  if hashlib.sha256((Path(rules.root)/data['source_file']).read_bytes()).hexdigest()!=data['source_sha256']:raise ValueError('future-effect source anchor changed')
  for path,digest in data.get('source_files',{}).items():
   if hashlib.sha256((Path(rules.root)/path).read_bytes()).hexdigest()!=digest:raise ValueError('event-effect source anchor changed: '+path)
  rules._event_effect_policy=data
 return data

def definition(rules,source):
 if source is None:return None
 row=policy(rules)['sources'].get(source)
 if row is not None and rules._selected_rule(source)!=source:raise ValueError('selected future-effect source changed')
 return row

def _laser_definitions(rules):
 from source_context import verified_source
 row=definition(rules,LASER);definitions={}
 for name,variant in row['source_variants'].items():
  source=variant['source']
  verified_source(rules,source,source_root='source-audit' if source['file'].startswith('source-audit/') else 'input',label='Laser Focus')
  definitions[name]=dict(deepcopy(variant),payload=deepcopy(row['payload']),selector=deepcopy(row['selector']))
 return definitions

def _laser_document(rules):
 definitions=_laser_definitions(rules)
 return {'schema':1,'id':'native/laser-focus-source','variants':[{
  'rule_id':LASER,'source':definitions['korean_next_attack']['source'],
  'values':{'variant':{'$input':'source_text'},'definitions':definitions},
  'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
   'choices':list(definitions),'question':'Laser Focus: Korean consumes the next damaging attack, even if it misses; English waits for the next successful damaging attack. Which complete source definition applies?'}}}]}

def laser_focus_source_choices(rules):
 return __import__('source_policy').resolve(rules,_laser_document(rules))

def _laser_choice(rules,binding,*,current=False):
 """Retain an actual producing choice, independently of later table choices."""
 import source_selection as SELECTION,root_resolution as ROOT
 if type(binding)is not dict or set(binding)!={'choice','resolution'}:raise ValueError('explicit complete Laser Focus source choice required')
 choice=binding['choice'];resolved=binding['resolution'];document=_laser_document(rules)
 if type(choice)is not dict or set(choice)!={'value','reason','scope'} or type(resolved)is not dict:raise ValueError('scoped Laser Focus source decision required')
 E.text(choice['reason'],'Laser Focus source reason')
 values=SELECTION.policy_values(resolved['source_policy_binding'],document['variants'])
 selected=choice['value']
 if (selected not in values['definitions'] or resolved['status']!='PolicyValuesReady'
     or resolved['values']!={'variant':selected,'definitions':values['definitions']}
     or resolved['selected_id']!=LASER or resolved['definition_hash']!=ROOT.fingerprint(document)
     or resolved['decision_scope']!=choice['scope']
     or resolved['inputs_hash']!=ROOT.fingerprint({'context':{},'decisions':{'source_text':choice},'state':{}})
     or resolved['decision_evidence']!=[{'input':'source_text','reason':choice['reason'],'decision_kind':'source_conflict','scope':choice['scope']}]):
  raise ValueError('retained Laser Focus source decision changed')
 if current and resolved!=__import__('source_policy').resolve(rules,document,decisions={'source_text':choice}):raise ValueError('current Laser Focus source scope changed; review required')
 return deepcopy(values['definitions'][selected])

def choose_laser_focus_source(engine,actor,decision,*,legacy_effects=()):
 """Choose future uses, optionally adopting exact currently live legacy effects."""
 import state_grants as G
 if not isinstance(legacy_effects,(list,tuple)) or len(set(legacy_effects))!=len(legacy_effects):raise ValueError('distinct actual legacy effect identities required')
 for uid in legacy_effects:E.text(uid,'legacy Laser Focus effect identity')
 resolved=__import__('source_policy').resolve(engine.r,_laser_document(engine.r),decisions={'source_text':decision})
 binding={'choice':deepcopy(decision),'resolution':resolved}
 _laser_choice(engine.r,binding,current=True)
 for record in live(actor):validate_record(actor,record)
 for record in actor.spec.get(HISTORY,[]):
  if record.get(E.KEY,{}).get('kind')==KIND:validate_record(actor,record,terminal=True)
 rows={r['id']:r for r in live(actor) if r['source']==LASER and LASER_CHOICE not in r}
 if any(uid not in rows for uid in legacy_effects):raise ValueError('adoption requires an actual live unbound Laser Focus effect')
 def commit(e,c):
  before=deepcopy(c.spec.get(LASER_CHOICE))
  c.spec[LASER_CHOICE]=deepcopy(binding)
  for record in live(c):
   if record['id'] in legacy_effects:
    record[LASER_CHOICE]=deepcopy(binding)
    record['laser_focus_adoption']={'at':e.elapsed_seconds,'kind':'gm_current_adoption'}
  e.gm._rec('예민해지기 출처 선택',before,{'choice':deepcopy(decision),'adopted_effect_ids':list(legacy_effects)},decision['reason'],who=c)
  return deepcopy(binding)
 return G.transition(engine,actor,commit,include_rulings=True)

def _record_definition(actor,record):
 row=definition(actor.r,record['source'])
 if record['source']==LASER and LASER_CHOICE in record:
  row=dict(row,**_laser_choice(actor.r,record[LASER_CHOICE]))
 elif LASER_CHOICE in record or 'laser_focus_adoption' in record:raise ValueError('Laser Focus choice belongs to its exact source')
 # Unbound old records retain their actual successful-hit contract. They do not
 # acquire a fictional past source choice; native use requires current adoption.
 return row

def semantic(effect):return {k:v for k,v in effect.items() if not k.startswith('_')}

def same_payload(left,right):return json.dumps(left,sort_keys=True,ensure_ascii=False)==json.dumps(right,sort_keys=True,ensure_ascii=False)

def future_predicate(rules,source,effect):
 row=definition(rules,source)
 return row is not None and row['window']=='owner_next_turn' and same_payload(semantic(effect),row['raw'])

def until_event(row):return row['window'] in ('until_successful_damaging_hit','until_matching_move_use','until_damaging_move_use')

def serial(actor):return C.integer(actor.custom_conditions.get('combat_turn_serial',0),'actual combat turn serial',0)

def live(actor):
 rows=T.records(actor)
 if not isinstance(rows,list):raise ValueError('timed effect records must be a list')
 for row in rows:
  if isinstance(row,dict) and E.KEY in row and not isinstance(row[E.KEY],dict):raise ValueError('typed timed effect metadata required')
 return [r for r in rows if isinstance(r,dict) and r.get(E.KEY,{}).get('kind')==KIND]

def validate_record(actor,record,*,terminal=False):
 E.validate(record,actor=actor,terminal=terminal)
 row=_record_definition(actor,record)
 if row is None:raise ValueError('native event effect needs its exact selected source')
 if not same_payload(record['effect'],row['payload']) or not same_payload(record.get('selector'),row['selector']):raise ValueError('future effect payload or selector changed from selected source')
 if record[E.KEY]['kind']!=KIND or record[E.KEY]['capacity']!={'bucket':'independent','source':record['source']}:raise ValueError('future-effect ownership policy changed')
 if len(record[E.KEY]['ownership'])!=1:raise ValueError('this event-effect source defines no transfer')
 if 'laser_focus_adoption' in record:
  adoption=record['laser_focus_adoption']
  if type(adoption)is not dict or set(adoption)!={'kind','at'} or adoption['kind']!='gm_current_adoption':raise ValueError('actual current Laser Focus adoption required')
  C.integer(adoption['at'],'Laser Focus adoption time',record['at'],record[E.KEY].get('ended_at'))
 born=C.integer(record.get('issued_turn'),'effect issuing turn',0)
 if born>serial(actor):raise ValueError('effect was created in a future owner turn')
 life={'boundary':'qualifying_event'} if until_event(row) else {'boundary':'owner_next_turn_end','owner_id':actor.entity_id,'turn':born+1}
 if not same_payload(record[E.KEY]['lifetime'],life) or record.get('manual_end') is not True:raise ValueError('event effect lifetime differs from its source')
 if row['window']=='owner_next_turn':
  C.integer(record.get('turn_deadline'),'future owner turn deadline',born+1,born+1)
  if record.get('turn_owner') is not actor or record.get('turn_deadline')!=born+1:raise ValueError('future effect and actual timing owner/deadline disagree')
  if not terminal and serial(actor)>born+1:raise ValueError('future turn window passed without native expiry')
 elif any(k in record for k in ('turn_owner','turn_deadline')):raise ValueError('until-hit effect has no invented turn expiry')
 observations=record.get('applications')
 if not isinstance(observations,list):raise ValueError('actual effect application history required')
 for event in observations:
  if row['payload']['kind']=='bonus_damage_dice':
   if not terminal:raise ValueError('unspent next-attack effect has no damage roll yet')
   validate_bonus_observation(actor,record,event)
   continue
  if not isinstance(event,dict) or event.get('kind')!='damage_roll':raise ValueError('actual damage roll observation required')
  C.integer(event.get('at'),'effect application time',record['at']);C.integer(event.get('turn'),'effect application turn',born+1,born+1)
  C.integer(event.get('extra_rolls'),'extra damage rolls',1,1);C.integer(event.get('damage_base'),'actual damage base',1)
  E.text(event.get('move_id'),'actual effect consumer Move');E.text(event.get('target_id'),'actual damage target')
 if until_event(row) and observations and row['payload']['kind']!='bonus_damage_dice':raise ValueError('one-use effect cannot contain repeated turn-window applications')
 if row.get('item_stock_required'):
  import gem_effects as GEMS
  GEMS.validate_receipt(record)
 elif 'item_stock' in record:raise ValueError('Move effect cannot invent item payment')
 if row.get('manual_activation'):
  import manual_effects as MANUAL
  MANUAL.validate_effect(actor,record)
 elif 'activation' in record or record[E.KEY].get('applied_by_actor_id',actor.entity_id)!=actor.entity_id:raise ValueError('this source has no foreign manual activation')
 if terminal:
  end=record[E.KEY]['end_event']
  if row['window']=='until_matching_move_use':
   if record[E.KEY]['state']!='consumed' or end.get('kind')!='matching_move_use':raise ValueError('Gem effect needs actual Move-use consumption')
   E.text(end.get('move_id'),'actual consuming Move')
   if end.get('activation')=='empty_area_field':
    if end.get('target_id') is not None:raise ValueError('target-free Move use cannot invent an actual target')
   else:
    if 'activation' in end:raise ValueError('unknown Move-use activation evidence')
    E.text(end.get('target_id'),'actual Move target')
   if 'type' in row['selector'] and end.get('move_type')!=row['selector']['type']:raise ValueError('effect used by a different actual Move type')
   if row.get('manual_activation') and end.get('move_class') not in row['selector']['classes']:raise ValueError('effect used by a different Move class')
  elif row['window']=='until_damaging_move_use':
   if record[E.KEY]['state']!='consumed' or end.get('kind') not in ('damaging_move_use','damaging_accuracy_attempt'):raise ValueError('Korean Laser Focus needs actual damaging attack consumption')
   E.text(end.get('move_id'),'actual consuming damaging Move')
   if end.get('move_class') not in row['selector']['classes']:raise ValueError('Laser Focus needs a damaging Move')
   if end['kind']=='damaging_accuracy_attempt' and any(k in end for k in ('activation','activation_targets')):raise ValueError('direct accuracy attempt cannot invent a native Move-use activation')
   if end.get('activation')=='empty_area_field':
    if end.get('target_id') is not None:raise ValueError('empty damaging area cannot invent a target')
   else:
    if 'activation' in end:raise ValueError('unknown damaging Move-use activation evidence')
    E.text(end.get('target_id'),'actual damaging Move target')
   if 'activation_targets' in end:
    targets=end['activation_targets']
    if not isinstance(targets,list) or not targets or any(not isinstance(x,str) or not x for x in targets) or len(targets)!=len(set(targets)) or end['target_id'] not in targets:raise ValueError('actual native damaging activation targets required')
  elif row['window']=='until_successful_damaging_hit':
   if record[E.KEY]['state']!='consumed' or end.get('kind')!='successful_damaging_hit':raise ValueError('automatic critical needs its actual successful-hit consumption')
   E.text(end.get('move_id'),'successful Move');E.text(end.get('target_id'),'successful hit target')
   if 'activation_targets' in end:
    targets=end['activation_targets']
    if not isinstance(targets,list) or not targets or any(not isinstance(x,str) or not x for x in targets) or len(targets)!=len(set(targets)) or end['target_id'] not in targets:raise ValueError('actual native activation target identities required')
  else:
   C.integer(end.get('turn'),'actual ending owner turn',born+1,born+1)
   if record[E.KEY]['state']!='expired' or end.get('kind')!='owner_turn_end':raise ValueError('future-turn effect needs its actual end-of-turn expiry')
 return True

def validate_actor(actor):
 for r in live(actor):validate_record(actor,r)
 history=actor.spec.get(HISTORY,[])
 if not isinstance(history,list):raise ValueError('typed effect history list required')
 for r in history:
  if not isinstance(r,dict) or not isinstance(r.get(E.KEY),dict):raise ValueError('typed ended effect required')
  if r[E.KEY].get('kind')==KIND:validate_record(actor,r,terminal=True)
 return True

def preflight(engine,actor,effect,source):
 row=definition(engine.r,source)
 if row is None:return False
 if source==LASER:row=dict(row,**_laser_choice(engine.r,actor.spec.get(LASER_CHOICE),current=True))
 if not same_payload(semantic(effect),row['raw']):raise ValueError('selected future-effect payload needs its own reviewed policy')
 validate_actor(actor)
 if row['window']=='owner_next_turn' and (not engine.encounter_active or engine._active_turn_actor is not actor):raise ValueError('next-own-turn effect requires the actual current owner turn')
 return True

def grant(engine,actor,effect,source,*,item_stock=None,applied_by=None,activation=None):
 if not preflight(engine,actor,effect,source):return False
 row=definition(engine.r,source);born=serial(actor)
 if source==LASER:row=dict(row,**_laser_choice(engine.r,actor.spec.get(LASER_CHOICE),current=True))
 if row.get('item_stock_required') and item_stock is None:raise ValueError('Gem requires actual item consumption')
 if row.get('manual_activation') and (applied_by is None or not isinstance(activation,dict)):raise ValueError('manual ability requires its actual paid activation')
 life={'boundary':'qualifying_event'} if until_event(row) else {'boundary':'owner_next_turn_end','owner_id':actor.entity_id,'turn':born+1}
 record=E.create(engine,actor,kind=KIND,source=source,payload=row['payload'],capacity={'bucket':'independent','source':source},lifetime=life,applied_by=applied_by)
 record.update(selector=deepcopy(row['selector']),issued_turn=born,applications=[],manual_end=True)
 if source==LASER:record[LASER_CHOICE]=deepcopy(actor.spec[LASER_CHOICE])
 if item_stock is not None:record['item_stock']=deepcopy(item_stock)
 if activation is not None:record['activation']=deepcopy(activation)
 if row['window']=='owner_next_turn':record.update(turn_owner=actor,turn_deadline=born+1)
 T.install(engine,actor,record);validate_record(actor,record)
 engine.log(f'    {actor.name}: sourced future effect {record["id"]}',source)
 return True

def matches(engine,actor,record,move,*,actual_type=None):
 if move.get('class') not in record['selector']['classes']:return False
 selector=record['selector']
 if 'type' in selector and (actual_type or move.get('type'))!=selector['type']:return False
 if selector.get('weapon_move'):
  import weapon_actions as WEAPONS
  if not isinstance(move.get('_weapon_attack'),dict) or move['id'] not in WEAPONS.policy(engine)['moves']:return False
 if record[E.KEY]['lifetime']['boundary']=='owner_next_turn_end':
  return engine.encounter_active and engine._active_turn_actor is actor and serial(actor)==record[E.KEY]['lifetime']['turn']
 return True

def accuracy_attempt(engine,actor,target,move):
 if move.get('class') not in ('물리','특수'):return False
 uses=getattr(engine,'_event_use_scopes',[])
 current=uses[-1] if uses else None
 if current is not None and current['actor'] is actor and current['target'] is target and current['move_id']==move['id']:
  return bool(current.get('laser_critical_sources'))
 validate_actor(actor)
 chosen=[r for r in live(actor) if r['source']==LASER and _record_definition(actor,r)['window']=='until_damaging_move_use' and matches(engine,actor,r,move)]
 event={'kind':'damaging_accuracy_attempt','move_id':move['id'],'move_class':move['class'],'target_id':target.entity_id}
 for record in chosen:T.expire(engine,actor,record,ending='consumed',event=event)
 return bool(chosen)


def critical(engine,actor,target,move,hit):
 validate_actor(actor)
 if not hit or move.get('class') not in ('물리','특수'):return False
 # One actual native Move activation can have several targets. Its authenticated
 # producer scope retains the spent source decision for the remaining targets;
 # an arbitrary shared-roll dictionary is never authority to reuse the effect.
 scope=__import__('move_activation').current_scope(engine,actor,target,move['id'])
 uses=getattr(engine,'_event_use_scopes',[])
 current=uses[-1] if uses else None
 native_critical=current is not None and current['actor'] is actor and current['target'] is target and current['move_id']==move['id'] and bool(current.get('laser_critical_sources'))
 if scope is not None and scope.get('event_critical_sources'):return True
 chosen=[r for r in live(actor) if r['effect']['kind']=='automatic_critical' and _record_definition(actor,r)['window']=='until_successful_damaging_hit' and matches(engine,actor,r,move)]
 event={'kind':'successful_damaging_hit','move_id':move['id'],'target_id':target.entity_id}
 if scope is not None:event['activation_targets']=[c.entity_id for c in scope['targets']]
 for record in chosen:T.expire(engine,actor,record,ending='consumed',event=event)
 if scope is not None and chosen:scope['event_critical_sources']=[r['id'] for r in chosen]
 return native_critical or bool(chosen)

def extra_rolls(engine,actor,move,actual_type):
 validate_actor(actor)
 chosen=[r for r in live(actor) if r['effect']['kind']=='extra_damage_roll' and matches(engine,actor,r,move,actual_type=actual_type)]
 # Each independently owned source explicitly adds one extra roll.
 return chosen

def record_damage(engine,actor,target,move,records,db):
 for row in records:
  row['applications'].append({'kind':'damage_roll','move_id':move['id'],'target_id':target.entity_id,'at':engine.elapsed_seconds,'turn':serial(actor),'extra_rolls':1,'damage_base':db})
  engine.log(f'    추가 피해 주사위 1회: {row["id"]}',row['source'])

def validate_world(engine,index):
 import move_coins as COINS
 COINS.validate_world(engine,index)
 import attack_damage_history as DAMAGE_HISTORY, move_type_choices as TYPE_CHOICES
 DAMAGE_HISTORY.validate_world(engine,index)
 TYPE_CHOICES.validate_world(engine,index)
 import five_strike as FIVE_STRIKE
 FIVE_STRIKE.validate_world(engine,index)
 import manual_effects as MANUAL
 MANUAL.validate_world(engine,index)
 import alternate_move_modes as ALTERNATE
 ALTERNATE.validate_world(engine,index)
 import optional_move_modes as OPTIONAL
 OPTIONAL.validate_world(engine,index)
 import post_resolution_stage_effects as POST_STAGE
 POST_STAGE.validate_world(engine,index)
 for actor in index.values():
  for row in live(actor)+[x for x in actor.spec.get(HISTORY,[]) if x.get(E.KEY,{}).get('kind')==KIND]:
   for event in row['applications']:
    if event['target_id'] not in index or event['at']>engine.elapsed_seconds or any(x not in index for x in event.get('target_ids',[])):raise ValueError('effect application references missing target or future time')
   if definition(engine.r,row['source']).get('item_stock_required'):
    import gem_effects as GEMS
    GEMS.validate_world_receipt(engine,actor,row,index)
   ending=row[E.KEY].get('end_event',{})
   if row.get('laser_focus_adoption',{}).get('at',0)>engine.elapsed_seconds:raise ValueError('Laser Focus adoption cannot be in the future')
   if any(uid not in index for uid in ending.get('activation_targets',[])):raise ValueError('effect activation references missing target')
   if ending.get('target_id') is not None and ending['target_id'] not in index:raise ValueError('effect consumption references missing actual target')
 return True


def begin_move_use(engine,actor,target,move,mechanics,*,targetless=False):
 """Commit next-use effects at actual activation, before its hit/miss outcome."""
 if type(targetless) is not bool:raise ValueError('explicit targetless Move-use observation required')
 scopes=getattr(engine,'_event_use_scopes',[])
 if not scopes or scopes[-1]['actor'] is not actor or scopes[-1]['target'] is not target:raise ValueError('actual native Move call required')
 current=scopes[-1]
 if current['move_id'] is not None:raise ValueError('one activation per native Move call')
 current['move_id']=move['id']
 group=__import__('move_activation').current_scope(engine,actor,target,move['id'])
 import alternate_move_modes as ALTERNATE
 ALTERNATE.begin_move_use(engine,actor,target,move,mechanics,targetless=targetless)
 import optional_move_modes as OPTIONAL
 OPTIONAL.begin_move_use(engine,actor,target,move,mechanics)
 import move_type_choices as TYPE_CHOICES
 TYPE_CHOICES.begin_move_use(engine,actor,target,move)
 import optional_physical_equipment as OPTIONAL_EQUIPMENT
 OPTIONAL_EQUIPMENT.begin_weapon_attack(engine,actor,target,move)
 import five_strike as FIVE_STRIKE
 FIVE_STRIKE.begin_move_use(engine,actor,target,move)
 import declarative_move_contracts as DECLARATIVE_MOVES
 DECLARATIVE_MOVES.begin_move_use(engine,actor,target,move,mechanics,targetless=targetless)
 current['laser_critical_sources']=group.setdefault('laser_critical_sources',[]) if group is not None else []
 first=group is None or not group.get('laser_focus_started')
 if group is not None:group['laser_focus_started']=True
 if first and move.get('class') in ('물리','특수'):
  chosen=[r for r in live(actor) if r['source']==LASER and _record_definition(actor,r)['window']=='until_damaging_move_use' and matches(engine,actor,r,move)]
  event={'kind':'damaging_move_use','move_id':move['id'],'move_class':move['class'],'target_id':None if targetless else target.entity_id}
  if targetless:event['activation']='empty_area_field'
  elif group is not None:event['activation_targets']=[c.entity_id for c in group['targets']]
  for record in chosen:
   T.expire(engine,actor,record,ending='consumed',event=event)
   current['laser_critical_sources'].append(record['id'])
 cached=group.setdefault('event_move_contributions',[]) if group is not None else []
 pending=[r for r in live(actor) if r['effect']['kind'] in ('damage_base_bonus','bonus_damage_dice')]
 if not pending and not cached:return
 import effects_ext as EXT
 actual_type=EXT.effective_type(engine,actor,target,move,mechanics,consume=False)
 current['move_type']=actual_type
 # Reuse only the native group decision, never a field supplied on a Move.
 chosen=[r for r in pending if matches(engine,actor,r,move,actual_type=actual_type)]
 for record in chosen:
  entry={'id':record['id'],'source':record['source'],'kind':record['effect']['kind'],'type':record['selector'].get('type'),'payload':deepcopy(record['effect']),'rolls':{}}
  event={'kind':'matching_move_use','move_id':move['id'],
         'target_id':None if targetless else target.entity_id,
         'move_type':actual_type,'move_class':move['class']}
  if targetless:event['activation']='empty_area_field'
  T.expire(engine,actor,record,ending='consumed',event=event)
  cached.append(entry)
 current['contributions']=[r for r in cached if r['type'] in (None,actual_type)]
 for entry in current['contributions']:engine.log(f'    다음 기술 효과 사용: {entry["id"]}',entry['source'])


def damage_base_bonus(engine,actor,move,target=None):
 scopes=getattr(engine,'_event_use_scopes',[])
 if not scopes:return 0
 scope=scopes[-1]
 if scope['actor'] is not actor or scope['move_id']!=move['id'] or (target is not None and scope['target'] is not target):return 0
 if move.get('class') not in ('물리','특수'):return 0
 return sum(r['payload']['amount'] for r in scope['contributions'] if r['kind']=='damage_base_bonus')


def validate_bonus_observation(actor,record,event):
 import re,type_state as TYPES
 if not isinstance(event,dict) or event.get('kind')!='bonus_damage':raise ValueError('actual extra damage observation required')
 TYPES.validate_types(actor.r,[event.get('move_type')],label='actual extra damage type')
 payload=record['effect'];expr=payload['by_type'].get(event['move_type'],payload['default'])
 if event.get('expression')!=expr:raise ValueError('extra damage expression changed from source')
 m=re.fullmatch(r'(\d+)d(\d+)\+(\d+)',expr);faces=event.get('faces')
 if not isinstance(faces,list) or len(faces)!=int(m[1]):raise ValueError('extra damage dice count mismatch')
 for face in faces:C.integer(face,'actual extra damage die',1,int(m[2]))
 C.integer(event.get('total'),'actual extra damage result',sum(faces)+int(m[3]),sum(faces)+int(m[3]))
 C.integer(event.get('at'),'actual extra damage time',record[E.KEY]['ended_at'])
 if event.get('move_id')!=record[E.KEY]['end_event']['move_id']:raise ValueError('extra damage belongs to another activation')
 targets=event.get('target_ids')
 if not isinstance(targets,list) or not targets or len(set(targets))!=len(targets) or event.get('target_id')!=targets[0]:raise ValueError('actual extra damage target observations required')
 for uid in targets:E.text(uid,'extra damage target identity')


def damage_roll_bonus(engine,actor,target,move,actual_type):
 scopes=getattr(engine,'_event_use_scopes',[])
 if not scopes:return 0
 scope=scopes[-1]
 if scope['actor'] is not actor or scope['target'] is not target or scope['move_id']!=move['id']:return 0
 total=0
 for entry in scope['contributions']:
  if entry['kind']!='bonus_damage_dice':continue
  payload=entry['payload'];expr=payload['by_type'].get(actual_type,payload['default'])
  record=next(r for r in actor.spec[HISTORY] if r['id']==entry['id'])
  observation=entry['rolls'].get(expr)
  if observation is None:
   value,faces=engine.roll_expr(expr)
   observation={'kind':'bonus_damage','expression':expr,'faces':list(faces),'total':value,'at':engine.elapsed_seconds,'move_id':move['id'],'move_type':actual_type,'target_id':target.entity_id,'target_ids':[target.entity_id]}
   validate_bonus_observation(actor,record,observation)
   record['applications'].append(observation);entry['rolls'][expr]=observation
  elif target.entity_id not in observation['target_ids']:observation['target_ids'].append(target.entity_id)
  total+=observation['total'];engine.log(f'    추가 피해 {expr} = {observation["total"]}: {entry["id"]}',entry['source'])
 return total


def validate_for_use(engine,actor,*,move=None):
 if move is not None and move.get('class') in ('물리','특수'):
  for record in live(actor):
   if record['source']==LASER and LASER_CHOICE not in record:raise ValueError('legacy Laser Focus needs an explicit current source adoption before native use')
 import attack_damage_history as DAMAGE_HISTORY, move_type_choices as TYPE_CHOICES
 DAMAGE_HISTORY.validate_actor(actor)
 TYPE_CHOICES.validate_actor(actor)
 E.validate_actor(actor)
 import alternate_move_modes as ALTERNATE
 ALTERNATE.validate_actor(actor)
 import optional_move_modes as OPTIONAL
 OPTIONAL.validate_actor(actor)
 import blessing_effects as BLESSINGS
 BLESSINGS.checked(engine)
 if any('activation' in r for r in live(actor)):
  import manual_effects as MANUAL,world_entities as W
  MANUAL.validate_world(engine,W.actor_index(engine))
 return True
