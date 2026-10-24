"""PTK timing policy for source-owned runtime effects, separate from dispatch.

Only explicit recognized boundaries are executable. Scalar contributions remain
separate records and are read by native consumers; expiry never reverses a
clamped or independently overwritten aggregate value.
"""
import re
import combat_timing as TIMING
import common_checks as C
import effect_lifetime_policy as POLICY

FIELDS={'skill_check_mod':'skill_modifier','accuracy_mod':'accuracy_modifier','evasion_mod':'evasion_modifier','damage_reduction':'damage_reduction','save_mod':'save_modifier'}
KINDS=set(FIELDS)|{'oracle_mark','channel_imprint','apply_status','initiative','initiative_multiplier','type_change','size_change','forbid','swap_stats','move_lock','damage_roll_mod','type_override_moves'}
class TimingUnsupported(ValueError):pass
class TimingAmbiguous(ValueError):pass

def declared(effect):return any(k in effect for k in ('duration','until','while','repeat'))

def prepare(engine,actor,target,effect,source):
 if source=='move/페어리록':return __import__('native_path_area_moves').fairy_prepare(engine,actor,target,effect,source)
 structured=any(type(effect.get(k)) is dict for k in ('duration','until','while','repeat'))
 if 'while' in effect and type(effect['while']) is not dict:raise TimingUnsupported('continuous predicate needs an explicit state declaration: '+str(effect['while']))
 if 'repeat' in effect and type(effect['repeat']) is not dict:raise TimingUnsupported('repeat needs an explicit event declaration: '+str(effect['repeat']))
 if not declared(effect):return None
 if effect['type']=='oracle_mark':
  if effect.get('until')!='target_ends':raise TimingUnsupported('Mark ends through its actual target consent boundary')
  return {'source':source,'manual_end':True,'effect_contract':True,'oracle_mark':__import__('oracle').mark_payload(engine,actor,target,effect,source)}
 if effect.get('type')=='pledge' and 'rainbow_observed' in effect:
  import pledge_state as PLEDGE
  return PLEDGE.prepare(engine,actor,target,effect,source)
 if effect.get('type')=='create_terrain':
  import field_effects as FIELD
  if FIELD.handles_local_snow(engine,source,effect):
   FIELD.prepare_local_snow(engine,actor,target,effect,source)
   return {'source':source,'local_weather_owned':True}
 if effect['type']=='custom_condition':
  # Reviewed custom conditions own their lifetime in the condition instance.
  # The generic dispatcher still routes every declared lifetime through this
  # module, so acknowledge that ownership without installing a second timer.
  import custom_condition_effects as CUSTOM
  CUSTOM.prepare(engine,actor,target,effect,source)
  return {'source':source,'custom_condition_owned':True}
 if effect['type']=='swap_stats':
  import stat_exchange_state as STAT_EXCHANGE
  return STAT_EXCHANGE.prepare(engine,actor,target,effect,source)
 if effect['type']=='move_lock':
  import catalog_move_states as CATALOG
  return CATALOG.prepare_move_lock(engine,actor,target,effect,source)
 if 'repeat' in effect:return POLICY.prepare(engine,actor,target,effect,source)
 if effect['type'] not in KINDS:raise TimingUnsupported('no source-owned lifetime consumer for '+effect['type'])
 if effect['type']=='forbid' and effect.get('actions')!=['attack_of_opportunity']:
  raise TimingUnsupported('timed prohibition requires a reviewed native action consumer')
 if effect['type'] in FIELDS:C.integer(effect.get('value'),'timed numeric modifier')
 if effect['type']=='damage_roll_mod':
  C.integer(effect.get('value'),'timed damage modifier')
  if set(effect)-{'type','value','move_type','target','until','duration','while','note','confidence'} or ('move_type' in effect and type(effect['move_type'])is not str):
   raise TimingUnsupported('timed damage modifier needs an exact supported passive payload')
 if effect['type']=='type_override_moves':
  if (source!='move/송전' or effect.get('moves')!='water moves and melee attacks'
      or effect.get('as_type')!='전기' or effect.get('until')!="end of user's next turn"
      or set(effect)-{'type','moves','as_type','target','until','note','confidence'}):
   raise TimingUnsupported('timed move-type override needs the reviewed Electrify payload')
 if effect['type']=='apply_status' and not isinstance(effect.get('status'),str):raise TimingUnsupported('one sourced status required for timed application')
 if 'duration' in effect and 'until' in effect:raise TimingAmbiguous('multiple lifetime declarations require an explicit composition rule')
 raw=effect.get('until',effect.get('duration'))
 if structured:
  record=POLICY.prepare(engine,actor,target,effect,source)
 elif not isinstance(raw,str):raise TimingUnsupported('typed timing adapter required for non-text lifetime')
 else:record={'source':source,'effect_contract':True,'timing_text':raw}
 if structured:pass
 elif raw=='source_ended':record['manual_end']=True
 elif raw in ('encounter_end','encounter','인카운터 끝까지'):
  if not engine.encounter_active:raise TimingAmbiguous('encounter lifetime requires an actual encounter')
  record['encounter_end']=True
 elif raw in ('scene_end','scene','장면'):
  record['scene_end']=True
 elif re.fullmatch(r'([1-9][0-9]*)라운드(?: 동안)?',raw) or re.fullmatch(r'([1-9][0-9]*) rounds?',raw):
  if not engine.encounter_active:raise TimingAmbiguous('round lifetime requires an actual encounter')
  count=TIMING.current(engine);n=int(re.match(r'[0-9]+',raw).group());record['count_deadline']=(engine.round_no+n,count);record['encounter_end']=True
 elif raw in ("end of user's next turn","start of user's next turn","end of target's next turn","start of target's next turn"):
  if not engine.encounter_active:raise TimingAmbiguous('turn lifetime requires an actual encounter')
  owner=actor if "user's" in raw else target
  key='turn_start_deadline' if raw.startswith('start') else 'turn_deadline'
  record.update(turn_owner=owner,encounter_end=True);record[key]=owner.custom_conditions.get('combat_turn_serial',0)+1
 elif raw in ('this round','이번 라운드'):
  if not engine.encounter_active:raise TimingAmbiguous('current-round lifetime requires an actual encounter')
  record.update(round_end_deadline=engine.round_no,encounter_end=True)
 elif 'next turn' in raw or '다음 턴' in raw:
  raise TimingAmbiguous('lifetime must identify whose turn and start or end: '+raw)
 else:raise TimingUnsupported('unimplemented explicit lifetime: '+raw)
 if effect['type']=='channel_imprint':record['channel_imprint']=__import__('channeler').imprint_payload(engine,actor,target,effect,source)
 elif effect['type']=='damage_roll_mod':pass
 elif effect['type']=='type_override_moves':record['move_type_override']={key:effect[key] for key in ('type','moves','as_type')}
 elif effect['type']=='size_change':
  import body_state as BODY,body_modes as MODES
  if source!='move/작아지기' or effect.get('to')!='Small' or raw not in ('encounter_end','encounter','인카운터 끝까지'):
   raise TimingUnsupported('timed size source requires reviewed native Minimize contract')
  if MODES.validate(target):raise TimingUnsupported('Minimize while a capability body mode is active needs a composition contract')
  BODY.cells(target,require_complete=True)
  record['size_value']='Small'
 elif effect['type']=='type_change':
  # Shared storage does not certify an area Move's whole-activation timing.
  if source in engine.r.moves and not engine.r.moves_reviewed.get(source,{}).get('type_lifetime_ready'):
   raise TimingUnsupported('native type-change source needs reviewed activation timing: '+source)
  record['type_operation']=type_operation(engine.r,effect,source=source)
  import type_state as TYPES
  TYPES.validate_actor(target)
 elif effect['type'] in ('initiative','initiative_multiplier'):
  import initiative_derivation as INITIATIVE
  record['initiative_operation']=INITIATIVE.operation(effect)
  if record['initiative_operation']=={'operation':'replace','value':0,'priority':0}:record['initiative_zero']=True
 elif effect['type']=='apply_status':record['statuses']=[effect['status']]
 elif effect['type']=='forbid':record['forbidden_actions']=list(effect['actions'])
 else:record[FIELDS[effect['type']]]=effect['value']
 return record

def install(engine,actor,target,effect,source,receipt,occurrence):
 record=prepare(engine,actor,target,effect,source)
 if record is None:return False
 if record.get('local_weather_owned'):
  import field_effects as FIELD
  FIELD.install_local_snow(engine,actor,target,effect,source,receipt,occurrence)
  return True
 if record.get('custom_condition_owned'):
  import custom_condition_effects as CUSTOM
  CUSTOM.grant(engine,actor,target,effect,source)
  return True
 record.update(effect_occurrence=occurrence,effect_receipt=receipt)
 if POLICY.KEY in record and not POLICY.holds(engine,record):return True
 if effect['type']=='damage_roll_mod':
  import state_grants as GRANTS
  import effects as FX
  grant=GRANTS.effect_source(target,{'source_id':source,'effect_occurrence':occurrence},'timed-damage')
  GRANTS._source(target,grant,'effect',owner_id=actor.entity_id,rule_id=source,lifetime=record['timing_text'])
  passive={k:effect[k] for k in ('type','value','move_type') if k in effect}
  GRANTS.apply_owned(engine,target,grant,lambda:FX.apply_passives(engine,target,[passive]),effects=[passive])
  record['grant_source']=grant
 if 'move_type_override' in record:
  import state_grants as GRANTS
  grant=GRANTS.effect_source(target,{'source_id':source,'effect_occurrence':occurrence},'timed-move-type')
  GRANTS._source(target,grant,'effect',owner_id=actor.entity_id,rule_id=source,lifetime=record['timing_text'])
  passive=record['move_type_override']
  GRANTS.apply_owned(engine,target,grant,lambda:target.registry.append(passive),effects=[passive])
  record['grant_source']=grant
 if 'size_value' in record:
  import state_grants as GRANTS
  grant=GRANTS.effect_source(target,{'source_id':source,'effect_occurrence':occurrence},'timed-size')
  GRANTS._source(target,grant,'effect',owner_id=actor.entity_id,rule_id=source,lifetime=record['timing_text'])
  GRANTS.scalar(target,'spec.size',record['size_value'],grant)
  GRANTS.scalar(target,'spec.footprint',None,grant)
  record['grant_source']=grant
 if 'type_operation' in record:
  import homebrew_state as HOME
  if HOME.type_change_blocked(target):return True
  import state_grants as GRANTS
  grant=GRANTS.effect_source(target,{'source_id':source,'effect_occurrence':occurrence},'timed-type')
  operation=record['type_operation']
  GRANTS._source(target,grant,'effect',owner_id=actor.entity_id,rule_id=source,
                 lifetime=record['timing_text'],timed_type_contract={
                  'operation':dict(operation),'boundary':type_boundary(record),
                  'occurrence':occurrence})
  import personal_type_settings as PERSONAL
  if PERSONAL.neutral_burn_up(engine.r,source,operation['mode'],operation['values']):
   GRANTS.state(target)['sources'][grant]['personal_type_setting']={
    'source':PERSONAL.NEUTRAL_SOURCE,'identity':PERSONAL.TYPELESS,'fallback':None}
  GRANTS.type_operation(target,operation['mode'],operation['values'],grant,fallback=operation['fallback'])
  record['grant_source']=grant
 if POLICY.KEY in record:
  from copy import deepcopy
  row=engine._effect_dispatch_receipts[receipt]
  contribution={k:deepcopy(record[k]) for k in (*FIELDS.values(),'statuses','initiative_zero','initiative_operation','type_operation','forbidden_actions','pledge_rainbow') if k in record}
  row.setdefault('lifetime_contracts',{})[target.entity_id]={'policy':deepcopy(record[POLICY.KEY]),'contribution':contribution}
 stat_plan=None
 if 'stat_exchange' in record:
  import stat_exchange_state as STAT_EXCHANGE
  stat_plan=STAT_EXCHANGE.prepare_install(target,record)
 TIMING.install(engine,target,record)
 if source=='move/페어리록' and not any(status in target.conditions for status in record['statuses']):
  TIMING.expire(engine,target,record)
 if stat_plan is not None:STAT_EXCHANGE.commit_install(target,stat_plan)
 return True

def forbids(actor,action):
 """Read independently expiring source contributions in the shared timer."""
 return any(action in record.get('forbidden_actions',[]) for record in TIMING.records(actor))

def numeric_derivation(actor,key):
 import composition_derive as COMPOSITION
 contributions=[]
 for index,record in enumerate(TIMING.records(actor)):
  if record.get('effect_contract') and key in record:
   source=record['source']
   if source in actor.r.selection.units and actor.r._selected_rule(source)!=source:raise ValueError('active effect source selection changed')
   C.integer(record[key],'timed numeric modifier')
   contributions.append({'id':'timed:'+str(index),'source':source,'value':record[key]})
 steps=[{'law':'add','contributors':[row['id'] for row in contributions]}] if contributions else []
 return COMPOSITION.derive(0,contributions,steps,rounding='exact')


def numeric(actor,key):
 return numeric_derivation(actor,key)['value']

def end_encounter(engine,actors):
 actors=list(actors)
 import stat_exchange_state as STAT_EXCHANGE
 STAT_EXCHANGE.preflight_actors(actors,'encounter_end')
 POLICY.boundary(engine,'encounter_end')
 import healing_blocks as HEALING_BLOCKS
 HEALING_BLOCKS.boundary(engine,actors,'encounter_end')
 for actor in actors:
  for record in list(TIMING.records(actor)):
   if record.get('effect_contract') and record.get('encounter_end'):
    TIMING.expire(engine,actor,record,
                  event={'kind':'encounter_end'} if 'stat_exchange' in record else None)
  import ability_transitions as ABILITIES
  ABILITIES.end(engine,actor,'encounter')
 import ability_native_actions as NATIVE
 NATIVE.end_encounter(engine,actors)


def type_operation(rules,effect,*,source=None):
 """Lossless data contract shared by timed addition, removal and replacement."""
 import type_state as TYPES
 keys=[key for key in ('add_type','lose_type','set_type') if key in effect]
 if len(keys)!=1:raise TimingUnsupported('exactly one explicit type operation required')
 key=keys[0];value=effect[key]
 if not isinstance(value,str):raise TimingUnsupported('one resolved type identity required')
 TYPES.validate_types(rules,[value],label='timed type operation')
 mode={'add_type':'add','lose_type':'remove','set_type':'set'}[key]
 if 'single_type' in effect and (effect['single_type'] is not True or mode!='set'):
  raise TimingUnsupported('single_type belongs only to a resolved replacement')
 fallback=effect.get('fallback')
 if fallback is not None:
  if mode!='remove':raise TimingUnsupported('fallback belongs only to type removal')
  TYPES.validate_types(rules,[fallback],label='timed type fallback')
 import personal_type_settings as PERSONAL
 if PERSONAL.neutral_burn_up(rules,source,mode,[value]):fallback=None
 return {'mode':mode,'values':[value],'fallback':fallback}


def type_boundary(record):
 value={key:record[key] for key in ('timing_text','encounter_end','scene_end',
        'count_deadline','turn_deadline','turn_start_deadline','round_end_deadline',POLICY.KEY) if key in record}
 if 'turn_owner' in record:value['turn_owner_id']=record['turn_owner'].entity_id
 return value


def validate_type_world(engine,index):
 """Bind each live type contribution to its actual lifetime and native receipt."""
 POLICY.validate_world(engine,index)
 import stat_exchange_state as STAT_EXCHANGE
 STAT_EXCHANGE.validate_world(engine,index)
 import state_grants as GRANTS
 import type_state as TYPES
 import effect_contracts as CONTRACTS
 for actor in index.values():
  TYPES.validate_actor(actor)
  state=actor.spec.get(GRANTS.KEY,{})
  sources=state.get('sources',{})
  expected={key for key,row in sources.items() if 'timed_type_contract' in row}
  seen=set()
  for record in TIMING.records(actor):
   if 'type_operation' not in record:continue
   key=record.get('grant_source')
   if key not in expected or key in seen:raise ValueError('timed type has missing or repeated grant source')
   seen.add(key);source=sources[key];contract=source['timed_type_contract']
   if record.get('effect_contract') is not True or contract!={'operation':record['type_operation'],
      'boundary':type_boundary(record),'occurrence':record.get('effect_occurrence')}:
    raise ValueError('timed type lifetime differs from its source contract')
   if state.get('type_sources',{}).get('sources',{}).get(key)!=record['type_operation']:
    raise ValueError('timed type operation differs from its live contribution')
   if source.get('rule_id')!=record.get('source') or source.get('lifetime')!=record.get('timing_text'):
    raise ValueError('timed type provenance differs from its lifetime')
   owner=record.get('turn_owner')
   if owner is not None and index.get(owner.entity_id) is not owner:
    raise ValueError('timed type turn owner does not resolve to an actual actor')
   receipt=record.get('effect_receipt')
   row=getattr(engine,'_effect_dispatch_receipts',{}).get(receipt)
   if not row or row.get('status')!='completed':raise ValueError('timed type needs a completed native effect receipt')
   CONTRACTS.validate_receipt(engine,receipt,record['source'],record['effect_occurrence'],row['actor'],row['target'],row['effect'])
   if source.get('owner_id')!=row['actor'].entity_id or not any(x is actor for x in CONTRACTS.recipients(row['actor'],row['target'],row['effect'])):
    raise ValueError('timed type recipient or producer differs from its receipt')
   if row['effect'].get('type')!='type_change' or type_operation(engine.r,row['effect'],source=row['source_id'])!=record['type_operation']:
    raise ValueError('timed type receipt carries a different operation')
  if seen!=expected:raise ValueError('timed type source has no live expiration record')
 import catalog_move_states as CATALOG
 CATALOG.validate_world(engine,index)
 return True

