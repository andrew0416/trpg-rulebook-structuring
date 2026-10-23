"""Source-owned Coat records on the actual holder, sharing effect identity/history.

These first adapters cover periodic self coats and native removal. Source-bound
transfer, overlapping same-source composition and other coat contracts remain
separate obligations; no invented duration or silent legacy conversion.
"""
from pathlib import Path
from copy import deepcopy
import hashlib,json
import common_checks as C
import effect_instances as E
import arithmetic_policy as M

KIND='coat'
HISTORY='effect_instance_history'
REMOVERS={'move/클리어스모그','move/안개제거'}
BATON='move/배턴터치'
TRANSFER_CHOICES='coat_transfer_choices'


def policy(rules):
 data=getattr(rules,'_coat_effect_policy',None)
 if data is None:
  data=json.loads((Path(rules.root)/'data/coat-effect-policy.json').read_text(encoding='utf-8'))
  for file,digest in data['source_files'].items():
   if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('coat source anchor changed: '+file)
  rules._coat_effect_policy=data
 return data


def definition(rules,source):
 import double_team as DOUBLE
 if source==DOUBLE.SOURCE:return DOUBLE.definition(rules,source)
 row=policy(rules)['sources'].get(source)
 if row is not None and rules._selected_rule(source)!=source:raise ValueError('selected coat source changed')
 return row


def same(a,b):return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)
def serial(actor):return C.integer(actor.custom_conditions.get('combat_turn_serial',0),'actual coat holder turn',0)


def _transfer_events(record):
 return record[E.KEY]['ownership'][1:]


def _validate_transfer_history(record):
 for event in _transfer_events(record):
  if event.get('source')!=BATON:raise ValueError('Coat ownership can transfer only through Baton Pass')


def live(actor):
 if not isinstance(actor.coats,list):raise ValueError('coat storage must be a list')
 result=[]
 for r in actor.coats:
  if isinstance(r,dict) and E.KEY in r:
   E.stored_family(r,KIND);result.append(r)
 return result


def validate_record(actor,record,*,terminal=False):
 if record.get('source')=='move/그림자분신':
  import double_team as DOUBLE
  return DOUBLE.validate(actor,record,terminal)
 if record.get('effect',{}).get('kind')=='damage_coat':
  import damage_coats as DAMAGE_COATS
  return DAMAGE_COATS.validate_record(actor,record,terminal=terminal)
 E.validate(record,actor=actor,terminal=terminal)
 row=definition(actor.r,record['source'])
 if row is None or not same(record['effect'],row['payload']):raise ValueError('coat payload differs from its selected source')
 meta=record[E.KEY]
 if meta['kind']!=KIND or meta['capacity']!={'bucket':'source_coat','source':record['source']}:raise ValueError('coat capacity authority changed')
 if meta['lifetime']!={'boundary':row['lifetime']}:raise ValueError('coat cannot invent a turn or Scene expiry')
 if meta.get('applied_by_actor_id')!=meta['origin_actor_id']:raise ValueError('self Coat must retain its original applying actor')
 _validate_transfer_history(record)
 born=C.integer(record.get('issued_turn'),'coat creation turn',0,serial(actor))
 apps=record.get('applications')
 if not isinstance(apps,list):raise ValueError('coat applications must be actual observations')
 turns={};at=record['at'];holders={x['holder_id'] for x in meta['ownership']}
 for event in apps:
  if not isinstance(event,dict) or event.get('kind')!='holder_turn_healing':raise ValueError('actual coat turn event required')
  holder=event.get('holder_id')
  if holder not in holders:raise ValueError('coat healed outside its ownership history')
  turn=C.integer(event.get('turn'),'coat application turn',turns.get(holder,-1)+1);turns[holder]=turn
  at=C.integer(event.get('at'),'coat application time',at)
  basis=C.integer(event.get('basis'),'observed healing maximum',1)
  requested=C.integer(event.get('requested'),'source healing request',0)
  if requested!=M.ratio(basis,row['payload']['denominator']):raise ValueError('coat healing formula changed')
  before=C.integer(event.get('hp_before'),'observed pre-heal HP');after=C.integer(event.get('hp_after'),'observed post-heal HP')
  healed=C.integer(event.get('healed'),'observed gained HP',0,requested)
  if after-before!=healed:raise ValueError('coat healing observation disagrees with HP change')
 if terminal:
  end=meta['end_event']
  if meta['state']!='expired' or end.get('kind')!='coat_removed' or end.get('source') not in REMOVERS:raise ValueError('actual source Coat removal required')
  if actor.r._selected_rule(end['source'])!=end['source']:raise ValueError('selected Coat remover changed')
  E.text(end.get('actor_id'),'actual Coat removal actor')
  if apps and apps[-1]['at']>meta['ended_at']:raise ValueError('coat healing occurs after removal')
 return True


def validate_actor(actor):
 seen=set()
 for record in live(actor):
  validate_record(actor,record)
  if record['source'] in seen:raise ValueError('overlapping same-source Coat composition is not reviewed')
  seen.add(record['source'])
 for record in actor.spec.get(HISTORY,[]):
  if isinstance(record,dict) and isinstance(record.get(E.KEY),dict) and record[E.KEY].get('kind')==KIND:validate_record(actor,record,terminal=True)


def _choice(actor):
 choices=actor.spec.get(TRANSFER_CHOICES,{})
 if not isinstance(choices,dict):raise ValueError('Coat transfer choices must be a mapping')
 return choices.get(BATON)


def select_transfer(engine,actor,replacement,*,reason):
 """Record the actual owned replacement before Baton Pass pays or mutates."""
 import world_entities as W
 index=W.actor_index(engine)
 if index.get(actor.entity_id) is not actor or index.get(replacement.entity_id) is not replacement:raise ValueError('actual Baton Pass participants required')
 if engine.r._selected_rule(BATON)!=BATON:raise ValueError('selected Baton Pass source changed')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('actual replacement selection reason required')
 owner=actor.spec.get('trainer_id')
 if actor is replacement or actor.kind!='pokemon' or replacement.kind!='pokemon' or not owner or replacement.spec.get('trainer_id')!=owner or actor.side!=replacement.side:raise ValueError('Baton Pass requires a distinct Pokemon owned by the same Trainer')
 if not actor.on_field or actor.fainted or actor.captured:raise ValueError('Baton Pass source must be an active usable Pokemon')
 if replacement.on_field or replacement.fainted or replacement.captured or replacement.dead:raise ValueError('Baton Pass replacement must be an available off-field Pokemon')
 record={'source':BATON,'actor_id':actor.entity_id,'replacement_id':replacement.entity_id,'selected_at':engine.elapsed_seconds,'reason':reason}
 actor.spec.setdefault(TRANSFER_CHOICES,{})[BATON]=record
 return deepcopy(record)


def preflight_transfer(engine,actor,source):
 import world_entities as W
 if source!=BATON or engine.r._selected_rule(source)!=source:raise ValueError('reviewed Baton Pass source required')
 index=W.actor_index(engine);record=_choice(actor)
 if not isinstance(record,dict) or set(record)!={'source','actor_id','replacement_id','selected_at','reason'}:raise ValueError('actual selected replacement required')
 if record['source']!=source or record['actor_id']!=actor.entity_id or not isinstance(record['reason'],str) or not record['reason'].strip():raise ValueError('Baton Pass selection identity changed')
 C.integer(record['selected_at'],'Baton Pass selection time',0,engine.elapsed_seconds)
 replacement=index.get(record['replacement_id'])
 if index.get(actor.entity_id) is not actor or replacement is None:raise ValueError('actual Baton Pass participants required')
 owner=actor.spec.get('trainer_id')
 if actor.kind!='pokemon' or replacement.kind!='pokemon' or not owner or replacement.spec.get('trainer_id')!=owner or actor.side!=replacement.side:raise ValueError('selected replacement is not the same Trainer owned Pokemon')
 if not actor.on_field or actor.fainted or actor.captured or replacement.on_field or replacement.fainted or replacement.captured or replacement.dead:raise ValueError('selected replacement is no longer available')
 if any(not isinstance(r,dict) or E.KEY not in r for r in actor.coats):raise ValueError('legacy Coat cannot transfer without source identity')
 validate_actor(actor);validate_actor(replacement)
 incoming={r['source'] for r in live(actor)};existing={r['source'] for r in live(replacement)}
 if incoming&existing:raise ValueError('Baton Pass would create unresolved same-source Coat composition')
 return replacement


def transfer(engine,actor,source):
 replacement=preflight_transfer(engine,actor,source)
 moved=list(live(actor))
 for record in moved:
  E.transfer(engine,actor,replacement,record,source=source)
  record['issued_turn']=serial(replacement)
  actor.coats.remove(record);replacement.coats.append(record)
 actor.spec[TRANSFER_CHOICES].pop(BATON,None)
 if not actor.spec[TRANSFER_CHOICES]:actor.spec.pop(TRANSFER_CHOICES,None)
 validate_actor(actor);validate_actor(replacement)
 engine.log('    '+actor.name+' -> '+replacement.name+': '+str(len(moved))+' source-owned Coats transferred',source)
 return replacement


def validate_world(engine,index):
 for actor in index.values():
  validate_actor(actor)
  choice=_choice(actor)
  if choice is not None:
   if not isinstance(choice,dict) or choice.get('actor_id')!=actor.entity_id or choice.get('source')!=BATON or choice.get('replacement_id') not in index:raise ValueError('pending Coat transfer choice references missing actors')
   C.integer(choice.get('selected_at'),'Baton Pass selection time',0,engine.elapsed_seconds)
  for record,spent in E.records(actor):
   if record[E.KEY]['kind']!=KIND:continue
   if record[E.KEY]['applied_by_actor_id'] not in index:raise ValueError('actual coat creator missing')
   if any(v['at']>engine.elapsed_seconds or v.get('holder_id') not in index for v in record['applications']):raise ValueError('coat application references missing actors or the future')
   if spent=='terminal' and record[E.KEY]['end_event']['actor_id'] not in index:raise ValueError('actual coat removal actor missing')


def preflight(engine,actor,target,effect,source):
 row=definition(engine.r,source)
 if row is None:return False
 if {k:v for k,v in effect.items() if not k.startswith('_')}!=row['raw']:raise ValueError('coat extraction differs from reviewed source')
 if row['payload']['kind']=='damage_coat':actor=target
 validate_actor(actor)
 if any(r['source']==source for r in live(actor)) or any(isinstance(r,dict) and r.get('coat')==row['raw']['coat'] for r in actor.coats):raise ValueError('overlapping same-source Coat needs an explicit reviewed composition rule')
 return True


def grant(engine,actor,effect,source,*,target=None):
 target=target or actor
 if not preflight(engine,actor,target,effect,source):return False
 row=definition(engine.r,source)
 holder=target if row['payload']['kind']=='damage_coat' else actor
 record=E.create(engine,holder,kind=KIND,source=source,payload=row['payload'],capacity={'bucket':'source_coat','source':source},lifetime={'boundary':row['lifetime']},applied_by=actor)
 record.update(issued_turn=serial(holder),applications=[])
 holder.coats.append(record);validate_record(holder,record)
 engine.log('    '+holder.name+': sourced Coat '+record['id'],source)
 return True


def turn_start(engine,actor):
 validate_actor(actor)
 if not actor.on_field or actor.captured:return
 turn=serial(actor)
 for record in live(actor):
  if record['effect']['kind'] in ('damage_coat','double_team_coat'):continue
  own=[x['turn'] for x in record['applications'] if x['holder_id']==actor.entity_id]
  last=own[-1] if own else record['issued_turn']
  if turn<=last:continue
  payload=record['effect'];basis=actor.max_hp if payload['healing_basis']=='current_max_hp' else actor.base_max_hp
  amount=M.ratio(basis,payload['denominator']);before=actor.hp
  healed=engine.heal(actor,amount,source_kind='move')
  record['applications'].append({'kind':'holder_turn_healing','holder_id':actor.entity_id,'turn':turn,'at':engine.elapsed_seconds,'basis':basis,'requested':amount,'hp_before':before,'hp_after':actor.hp,'healed':healed})
  validate_record(actor,record)


def blocks_displacement(engine,actor):
 validate_actor(actor)
 sources=[r['source'] for r in live(actor) if r['effect']['blocks_push_pull']]
 if sources:engine.log('    '+actor.name+': Coat prevents push/pull',sources[0])
 return bool(sources)


def preflight_clear(engine,actors,*,source,applied_by):
 for actor in actors:validate_actor(actor)
 if not any(live(actor) for actor in actors):return
 if source not in REMOVERS or engine.r._selected_rule(source)!=source:raise ValueError('native Coat removal needs reviewed source')
 import world_entities as WORLD
 index=WORLD.actor_index(engine)
 if index.get(applied_by.entity_id) is not applied_by or any(index.get(a.entity_id) is not a for a in actors):raise ValueError('Coat removal requires actual actors')
 E.validate_world(engine,index)


def clear(engine,actor,*,source,applied_by):
 preflight_clear(engine,[actor],source=source,applied_by=applied_by)
 owned=live(actor)
 if owned and (source not in REMOVERS or engine.r._selected_rule(source)!=source):raise ValueError('native Coat removal needs reviewed source')
 for record in owned:E.archive(engine,actor,record,state='expired',event={'kind':'coat_removed','source':source,'actor_id':applied_by.entity_id})
 count=len(actor.coats);actor.coats.clear()
 return count
