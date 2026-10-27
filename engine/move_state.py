"""Known-move state and retained natural-learning opportunities.

A source list establishes the classification of an already known move. It never
learns a move, spends points, or certifies an acquisition procedure. Historical
opportunities remain attached to the individual when its species changes.
"""
from copy import deepcopy
import re

SOURCE='ch05-pokemon/포켓몬-관리하기/기술'
HISTORY='move_natural_history'
VM_SOURCE='supp-polygon/영혼-스프레이'
VITAMIN_SOURCE='ch09-equipment/포켓몬-도구/영양제'


def _source(rules):
 if rules._selected_rule(SOURCE)!=SOURCE:
  raise ValueError('selected natural-move source needs its own state policy')


def known(rules,spec):
 result=[]
 for raw in spec.get('moves',[]):
  if raw=='struggle':continue
  mid=rules.move_id(raw)
  if mid is None or mid in result:raise ValueError('distinct selected known moves required')
  result.append(mid)
 return result


def current_natural_evidence(rules,spec):
 """Current species/level evidence, without asserting how the move was learned."""
 _source(rules)
 if spec.get('species') is None:return {}  # Imported unknown species is not invented.
 from builder import species_lookup
 sp=species_lookup(rules,spec['species']);level=spec['level']
 if type(level)is not int or not 1<=level<=100:raise ValueError('actual Pokemon level required')
 result={}
 def add(mid,kind,required_level=None):
  if mid and mid in rules.moves:
   import example_species as EXAMPLES
   if not EXAMPLES.learning_allowed(rules,sp,mid):return
   result.setdefault(mid,[]).append({'source':SOURCE,'species_id':sp['id'],'kind':kind,'required_level':required_level})
 import type_sync as TYPE_SYNC
 sync=TYPE_SYNC.active(rules,spec)
 if sync is None:
  for row in rules.learnset_links.get(sp['name'],{}).get('moves',[]):
   if row.get('source')=='level_up' and row.get('level',0)<=level:
    add(row.get('to'),'level_up',row.get('level',0))
 else:
  for row in sync['level_up']:
   if row['level']<=level:
    import example_species as EXAMPLES
    if not EXAMPLES.learning_allowed(rules,sp,row['move_id']):continue
    result.setdefault(row['move_id'],[]).append({'source':TYPE_SYNC.SOURCE,'species_id':sp['id'],
      'kind':'level_up','required_level':row['level'],'type_sync_id':sync['id']})
 ls=rules.learnsets.get(sp['name'],{})
 if 'mentor_egg_list' in spec:
  import mentor as MENTOR_FULL
  for mid in MENTOR_FULL.individual_egg_list(rules,spec):
   if mid in {rules.move_id(name) for name in ls.get('egg',[])}:add(mid,'egg')
   else:
    event=MENTOR_FULL.individual_egg_evidence(rules,spec,mid)
    result.setdefault(mid,[]).append({'source':MENTOR_FULL.CSV[MENTOR_FULL.EGG_TUTOR],
      'species_id':sp['id'],'kind':'egg','required_level':None,'egg_list_request_id':event['request_id']})
 else:
  for name in ls.get('egg',[]):add(rules.move_id(name),'egg')
 for name in ls.get('tutor',[]):
  if re.search(r'\(N\)',str(name),re.I):
   add(rules.move_id(re.sub(r'\s*\(N\)','',name,flags=re.I)),'n_tutor')
 return result


def validate_history(rules,spec):
 from builder import species_lookup
 def species_identity(raw):
  try:return species_lookup(rules,raw)['id']
  except (KeyError,TypeError):raise ValueError('natural opportunity requires an actual historical species') from None
 history=spec.get(HISTORY,{})
 if not isinstance(history,dict):raise ValueError('natural opportunity history must be a mapping')
 for mid,events in history.items():
  if rules.move_id(mid)!=mid or not isinstance(events,list) or not events:
   raise ValueError('natural opportunity history needs a canonical move and events')
  seen=set()
  for event in events:
   import type_sync as TYPE_SYNC
   if not isinstance(event,dict) or event.get('source') not in (SOURCE,TYPE_SYNC.SOURCE,__import__('mentor').CSV[__import__('mentor').EGG_TUTOR]) or not isinstance(event.get('reason'),str) or not event['reason'].strip():
    raise ValueError('natural opportunity requires its actual source and observation reason')
   kind=event.get('kind');level=event.get('at_level');species=event.get('species_id')
   if kind not in ('level_up','egg','n_tutor') or type(level)is not int or not 1<=level<=100:
    raise ValueError('invalid natural opportunity kind or observed level')
   if event['source']==__import__('mentor').CSV[__import__('mentor').EGG_TUTOR]:
    __import__('mentor').validate_individual_egg_event(rules,spec,mid,event)
    continue
   evidence=({mid:TYPE_SYNC.historical_evidence(rules,spec,event.get('type_sync_id'),mid,level)}
             if event['source']==TYPE_SYNC.SOURCE else current_natural_evidence(rules,{'species':species,'level':level}))
   key=(species_identity(species),kind,event.get('required_level'),event['source'],event.get('type_sync_id'))
   if key in seen:raise ValueError('duplicate natural opportunity event')
   seen.add(key)
   if not any(row['kind']==kind and row['required_level']==event.get('required_level') and species_identity(row['species_id'])==species_identity(species) and row.get('type_sync_id')==event.get('type_sync_id') for row in evidence.get(mid,[])):
    raise ValueError('natural opportunity does not match its historical species and level')
 return True


def mentor_natural_moves(rules,spec):
 result=set()
 for mid,record in spec.get('move_learning',{}).items():
  if isinstance(record,dict) and 'mentor_acquisition_evidence' in record:__import__('mentor').validate_teaching_evidence(rules,record)
  if isinstance(record,dict) and record.get('method')=='mentor_csv':
   import mentor_csv as MENTOR_CSV
   MENTOR_CSV.validate_learning(rules,spec,mid,record)
   result.add(mid)
   continue
  if not isinstance(record,dict) or record.get('method')!='mentor':continue
  if record.get('source')!='class/멘토' or rules._selected_rule('class/멘토')!='class/멘토':raise ValueError('Mentor natural exception requires its selected exact source')
  import pokemon_teaching as TEACHING
  ranks=TEACHING.validate_mentor_ranks(rules,record);level=record.get('learned_at_level')
  if type(level)is not int or not 1<=level<=100 or not isinstance(record.get('teacher_id'),str) or not record['teacher_id'] or record.get('paid_tp')!=1:raise ValueError('Mentor natural exception requires its completed teaching provenance')
  import type_sync as TYPE_SYNC
  options=(TYPE_SYNC.historical_evidence(rules,spec,record['type_sync_id'],mid,min(100,level+sum(ranks))) if record.get('type_sync_id') else current_natural_evidence(rules,{'species':record.get('species_id'),'level':min(100,level+sum(ranks))}).get(mid,[]))
  if not any(row['kind'] in ('level_up','n_tutor') for row in options):raise ValueError('Mentor move outside its historical species and both-skill level allowance')
  result.add(mid)
 return result


def natural_moves(rules,spec):
 current=current_natural_evidence(rules,spec)
 validate_history(rules,spec)
 import underdog_lessons as LESSONS
 import growth_milestones as MILESTONES
 return set(current)|set(spec.get(HISTORY,{}))|mentor_natural_moves(rules,spec)|LESSONS.natural_moves(rules,spec)|MILESTONES.inheritance_natural_moves(rules,spec)


def _opportunity_candidates(rules,spec):
 # Learned ownership survives an overlay hiding the permanent moves. An
 # overlay-only displayed identity does not establish prior TM/Tutor learning.
 result={mid:[{'authority':'permanent_baseline'}] for mid in known(rules,spec)}
 st=spec.get('state_grants',{})
 for source_id,row in st.get('sources',{}).items():
  paid=row.get('tutor_points',0)
  group=st.get('payments',{}).get(row.get('payment_id'))
  if group is not None and row.get('learning_route')=='taught' and source_id in group['children'] and type(group.get('paid')) is int and group['paid']>0:
   provenance={'authority':'paid_group_source_grant','source_id':source_id,'rule_id':row.get('rule_id'),
               'payment_id':row['payment_id'],'group_paid_tp':group['paid']}
  elif type(paid)is int and paid>0:
   provenance={'authority':'paid_source_grant','source_id':source_id,'rule_id':row.get('rule_id'),'paid_tp':paid}
  else:continue
  for mid in known(rules,{'moves':row.get('grants',{}).get('moves',[])}):
   result.setdefault(mid,[]).append(dict(provenance))
 learning=spec.get('move_learning',{})
 if not isinstance(learning,dict):raise ValueError('move learning provenance must be a mapping')
 for mid in known(rules,{'moves':st.get('legacy',{}).get('moves',[])}):
  record=learning.get(mid)
  if isinstance(record,dict) and record.get('source') and (record.get('method') in ('tm','hm','tutor') or (record.get('method')=='feature' and type(record.get('paid_tp'))is int and record['paid_tp']>0)):
   result.setdefault(mid,[]).append({'authority':'observed_legacy_learning','method':record['method'],'source':record['source']})
 return result


def record_natural_opportunities(rules,spec,*,reason):
 """Persist only evidenced opportunities for moves already present in the sheet."""
 if spec.get('kind','pokemon')!='pokemon':return []
 if not isinstance(reason,str) or not reason.strip():raise ValueError('natural opportunity observation reason required')
 learning=spec.get('move_learning',{})
 if not isinstance(learning,dict):raise ValueError('move learning provenance must be a mapping')
 if any(not isinstance(record,dict) for record in learning.values()):raise ValueError('move learning provenance must be a record')
 validate_history(rules,spec)
 current=current_natural_evidence(rules,spec);history=deepcopy(spec.get(HISTORY,{}));added=[]
 for mid,provenance in _opportunity_candidates(rules,spec).items():
  for row in current.get(mid,[]):
   events=history.setdefault(mid,[])
   if any(all(event.get(k)==row.get(k) for k in ('source','species_id','kind','required_level','type_sync_id')) for event in events):continue
   event=dict(row,at_level=spec['level'],reason=reason,observation_provenance=deepcopy(provenance))
   events.append(event);added.append({'move_id':mid,**event})
 import underdog_lessons as LESSONS
 import growth_milestones as MILESTONES
 natural=set(current)|set(history)|mentor_natural_moves(rules,spec)|LESSONS.natural_moves(rules,spec)|MILESTONES.inheritance_natural_moves(rules,spec)
 updates=[]
 for mid,record in learning.items():
  updates.append((record,mid in natural))
 # Every input has passed before mutation; preserve existing record identities.
 if history:spec[HISTORY]=history
 for record,is_natural in updates:record['natural']=is_natural
 return added


GUIDANCE='feat/지침'
LIFELONG='feat/평생학습'
FOILING='feat/나뭇잎-포장'
SLOT_FEATURES=(GUIDANCE,LIFELONG,FOILING)
CSV_SLOT_FEATURES={
 'C2CSV/input/db/feats.csv:R107:main':GUIDANCE,
 'C2CSV/input/db/feats.csv:R110:main':LIFELONG,
 'C2CSV/input/db/feats.csv:R265:main':FOILING,
}
SLOT_POLICIES={**{uid:uid for uid in SLOT_FEATURES},**CSV_SLOT_FEATURES}


def effective_list(spec,field,live=None):
 st=spec.get('state_grants',{})
 base=list(spec.get(field,[]))
 legacy=st.get('legacy',{}).get(field,[]) if st else [v for v in live or [] if v not in base]
 result=base+list(legacy)
 for row in st.get('sources',{}).values():
  if not source_active(spec,row):continue
  result.extend(row.get('grants',{}).get(field,[]))
 overlays=[row[field] for row in st.get('overlays',{}).values() if field in row]
 return list(dict.fromkeys(overlays[-1] if overlays else result))


def source_active(spec,row):
 """A conditional permission requires an independently owned capability.

 Conditional sources cannot establish their own prerequisite or form a cycle.
 This predicate reads the existing ownership ledger without writing a shadow.
 """
 required=row.get('required_capability')
 if required is None:return True
 if not isinstance(required,str) or not required:raise ValueError('conditional source needs a capability identity')
 st=spec.get('state_grants',{})
 caps=list(spec.get('capabilities',[]))+list(st.get('legacy',{}).get('capabilities',[]))
 for candidate in st.get('sources',{}).values():
  if candidate.get('required_capability') is None:caps.extend(candidate.get('grants',{}).get('capabilities',[]))
 overlays=[r['capabilities'] for r in st.get('overlays',{}).values() if 'capabilities' in r]
 return required in (overlays[-1] if overlays else caps)


def owned_list(spec,field,live=None):
 st=spec.get('state_grants',{})
 result=list(spec.get(field,[]))+list(st.get('legacy',{}).get(field,[]))
 for row in st.get('sources',{}).values():
  if field=='moves' and row.get('move_mode')=='permission':continue
  if not source_active(spec,row):continue
  result.extend(row.get('grants',{}).get(field,[]))
 # Raw imported current values remain explicit unknown ownership; values
 # explained by a display overlay or permission never become learned moves.
 if live is not None:
  explained=effective_list(spec,field)
  # Inactive permissions still explain stale materialized display values;
  # losing their prerequisite cannot turn that cache into unknown learning.
  for row in st.get('sources',{}).values():explained.extend(row.get('grants',{}).get(field,[]))
  result.extend(v for v in live if v not in explained)
 return list(dict.fromkeys(result))


GIVER_IDS=('ability/기부자','ability/기부자-2')


def ability_registration(rules,name):
 vigor=__import__('endure').registration(rules,name)
 if vigor is not None:return vigor
 cap=__import__('hp_setting_moves').registration(rules,name)
 if cap:return cap
 typed=__import__('typed_defensive_bypass').registration(rules,name)
 if typed:return typed
 core_suction=__import__('core_suction_cups').registration(rules,name)
 if core_suction is not None:return core_suction
 # One CSV row shares the two defenses, but species acquisition keeps its member.
 armor_id='ability/조가비갑옷-전투무장'
 armor_names={'조가비갑옷':'조가비갑옷','Shell Armor':'조가비갑옷',
              '전투무장':'전투무장','Battle Armor':'전투무장'}
 if name in (*armor_names,armor_id,'조가비갑옷/전투무장','Shell Armor/Battle Armor'):
  if rules._selected_rule(armor_id)!=armor_id:raise ValueError('selected Armor source needs its own registration')
  unit=rules.selection.units[armor_id];source=unit['source']
  if unit['title']!='조가비갑옷/전투무장' or source.get('file')!='db/abilities.csv' or source.get('record_span')!=[366,366]:
   raise ValueError('reviewed paired Armor source changed')
  return {'name':'조가비갑옷/전투무장','source_id':armor_id,
          'acquisition_identity':armor_names.get(name)}
 # As One's two stock mounts have duplicated identical CSV definitions. Keep
 # both source IDs; equality of these exact rows authorizes only this family.
 for literal,ids,records in (
  ('백의울음',('ability/백의울음','ability/백의울음-2'),(179,615)),
  ('흑의울음',('ability/흑의울음','ability/흑의울음-2'),(481,618))):
  if name not in (literal,*ids):continue
  import csv,json,hashlib
  from pathlib import Path
  root=Path(rules.root)
  if hashlib.sha256((root/'input/db/abilities.csv').read_bytes()).hexdigest()!='87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae':
   raise ValueError('As One basic ability reviewed CSV source changed; review required')
  with (root/'input/db/abilities.csv').open(encoding='utf-8-sig',newline='') as handle:raw=list(csv.reader(handle))
  cells=[raw[number-1] for number in records]
  if cells[0]!=cells[1] or len(cells[0])!=8 or cells[0][0]!=literal:
   raise ValueError('As One basic ability duplicate source changed; review required')
  rows={row['id']:row for row in json.loads((root/'output/entities/abilities.json').read_text(encoding='utf-8')) if row.get('id') in ids}
  if set(rows)!=set(ids):raise ValueError('As One basic ability exact source definitions missing')
  definitions=[{k:v for k,v in rows[uid].items() if k not in ('id','_source')} for uid in ids]
  if definitions[0]!=definitions[1]:raise ValueError('As One basic ability definitions no longer equivalent')
  for uid,number in zip(ids,records):
   source=rows[uid].get('_source',{})
   if source.get('file')!='db/abilities.csv' or source.get('record_span')!=[number,number]:
    raise ValueError('As One basic ability source identity changed')
   expected={'name':cells[0][0],'frequency':cells[0][1],'effect':cells[0][2],
             'trigger':cells[0][3] or None,'target':cells[0][4] or None,
             'keyword':cells[0][5] or None,'effect2':cells[0][6],'eng':cells[0][7].strip()}
   if any(rows[uid].get(key)!=value for key,value in expected.items()):
    raise ValueError('As One basic ability differs from its actual CSV source')
  uid=name if name in ids else ids[0]
  if rules._selected_rule(uid)!=uid:raise ValueError('selected As One mount ability needs its own policy')
  return {'name':literal,'source_id':uid,'equivalent_source_ids':list(ids),
          'equivalence_records':list(records)}
 # Two actual CSV rows have identical full rule text, frequency and keyword.
 # Certify only this reviewed equivalence; never normalize arbitrary same names.
 if name not in ('기부자','Giver',*GIVER_IDS):
  import move_permissions as PERMISSIONS,held_equipment as HELD,manual_effects as MANUAL,base_stage_abilities as BASE_ABILITIES
  import ability_transitions as ABILITY_TRANSITIONS,capacity_abilities as CAPACITY_ABILITIES
  import acquired_feature_projections as ACQUIRED_PROJECTIONS
  import ability_state_projection as ABILITY_STATE_PROJECTION
  import reactive_ability_events as REACTIVE
  import tera_shell as TERA_SHELL
  import perish_body as PERISH_BODY
  return __import__('oracle').registration(rules,name) or BASE_ABILITIES.registration(rules,name) or PERMISSIONS.registration(rules,name) or HELD.registration(rules,name) or MANUAL.registration(rules,name) or ABILITY_TRANSITIONS.registration(rules,name) or ABILITY_STATE_PROJECTION.ability_registration(rules,name) or CAPACITY_ABILITIES.registration(rules,name) or ACQUIRED_PROJECTIONS.registration(rules,name) or REACTIVE.registration(rules,name) or TERA_SHELL.registration(rules,name) or PERISH_BODY.registration(rules,name)
 import json
 from pathlib import Path
 rows={x['id']:x for x in json.loads((Path(rules.root)/'output/entities/abilities.json').read_text(encoding='utf8')) if x.get('id') in GIVER_IDS}
 if set(rows)!=set(GIVER_IDS):raise ValueError('Giver exact source definitions missing')
 keys=('name','eng','frequency','effect','keyword')
 if any(rows[GIVER_IDS[0]].get(k)!=rows[GIVER_IDS[1]].get(k) for k in keys) or rows[GIVER_IDS[0]].get('keyword')!='2-16 Playtest':
  raise ValueError('Giver duplicate source equivalence changed; review required')
 uid=name if name in GIVER_IDS else GIVER_IDS[0]
 if rules._selected_rule(uid)!=uid:raise ValueError('selected Giver variant needs its own policy')
 return {'name':'기부자','source_id':uid,'equivalent_source_ids':list(GIVER_IDS)}


def capacities(rules,spec,*,abilities=None):
 if spec.get('kind')=='trainer':return {'total':None,'taught':None,'exempt':{},'sources':[]}
 _source(rules);total=6;taught=3;exempt={};sources=[];seen=set()
 import special_entities as SPECIAL
 snapshot=spec.get(SPECIAL.PRIME_KEY)
 if snapshot and SPECIAL.prime_definition(rules,snapshot)['hidden_powers']=='all_additional':
  current=set(effective_list(spec,'moves'))
  for mid in SPECIAL.prime_moves(rules,snapshot):
   if mid in current:exempt[mid]=SPECIAL.PRIME_PREFIX+snapshot['id']
  sources.append({'rule_id':SPECIAL.PRIME_SOURCE,'record_id':snapshot['id']})
 for key,row in spec.get('state_grants',{}).get('sources',{}).items():
  policy=row.get('move_slot_policy')
  if policy is None:continue
  if not isinstance(policy,dict):raise ValueError('move slot policy must be a source record')
  uid=policy.get('rule_id')
  if uid=='feat/프로토-디자인':
   if row.get('rule_id')!=uid or rules._selected_rule(uid)!=uid or row.get('lifetime')!='installed_augmentation' or policy.get('selected_move')!=rules.move_id('페인트') or not isinstance(policy.get('instance_id'),str):raise ValueError('Smart Vision slot exemption requires its actual installed source')
   exempt[policy['selected_move']]=key;sources.append({'source_id':key,'rule_id':uid,'instance_id':policy['instance_id']});continue
  if uid not in SLOT_POLICIES or row.get('rule_id')!=uid or rules._selected_rule(uid)!=uid:
   raise ValueError('unsupported selected move slot source')
  if row.get('lifetime')!='your_pokemon' or not spec.get('trainer_id') or row.get('owner_id')!=spec['trainer_id']:
   raise ValueError('move slot feature requires the actual current owner')
  policy_id=SLOT_POLICIES[uid]
  if policy_id in seen:raise ValueError('duplicate acquired move slot feature')
  seen.add(policy_id);sources.append({'source_id':key,'rule_id':uid,'owner_id':row['owner_id']})
  if policy_id==GUIDANCE:total+=1
  elif policy_id==LIFELONG:taught=max(taught,4)
  else:
   mid=policy.get('selected_move')
   if rules.move_id(mid)!=mid:raise ValueError('Foiling Foliage requires one canonical selected move')
   move=rules.move(mid)
   if move.get('type')!='풀' or move.get('class')!='변화':raise ValueError('Foiling Foliage selection must be a Grass Status move')
   exempt[mid]=key
 # This exact Playtest source only removes the taught quota, not the six total.
 abilities=owned_list(spec,'abilities',abilities)
 import capacity_abilities as CAPACITY_ABILITIES
 for uid,row in CAPACITY_ABILITIES.sources(rules,abilities,'move_capacity').items():
  total+=row['total_bonus'];sources.append({'rule_id':uid,'ability':row['name']})
 giver=[ability_registration(rules,name) for name in abilities if name in ('기부자','Giver',*GIVER_IDS)]
 if giver:
  taught=None;sources.append({'rule_id':giver[0]['source_id'],'ability':'기부자','equivalent_source_ids':giver[0]['equivalent_source_ids']})
 import advanced_connection as CONNECTION
 for mid,source in CONNECTION.exemptions(rules,spec,abilities).items():
  exempt[mid]=source;sources.append({'source_id':source,'rule_id':CONNECTION.SOURCE,'selected_move':mid})
 return {'total':total,'taught':taught,'exempt':exempt,'sources':sources}


def vm_moves(rules,spec):
 """A current learned VM occupies two move slots; old receipts are history."""
 learning=spec.get('move_learning',{})
 if not isinstance(learning,dict):raise ValueError('move learning provenance must be a mapping')
 result=[]
 for mid in known(rules,{'moves':list(dict.fromkeys(list(spec.get('moves',[]))+list(spec.get('state_grants',{}).get('legacy',{}).get('moves',[]))))}):
  record=learning.get(mid)
  if not isinstance(record,dict) or record.get('method')!='vm':continue
  if record.get('source')!=VM_SOURCE or rules._selected_rule(VM_SOURCE)!=VM_SOURCE:
   raise ValueError('VM requires its selected exact source')
  if not isinstance(record.get('application_id'),str) or not record['application_id'].strip() or not isinstance(record.get('reason'),str) or not record['reason'].strip():
   raise ValueError('VM requires an observed completed application identity and reason')
  result.append(mid)
 if len(result)>1:raise ValueError('a Pokemon may have only one VM move, regardless of slot exceptions')
 return result


def vitamin_state(rules,spec):
 if rules._selected_rule(VITAMIN_SOURCE)!=VITAMIN_SOURCE:
  raise ValueError('selected Vitamin variant needs its own capacity policy')
 history=spec.get('vitamins',[])
 if not isinstance(history,list) or any(not isinstance(v,str) or not v.strip() for v in history):
  raise ValueError('Vitamin consumption history must preserve actual named doses')
 import vitamin_moves as VITAMINS
 VITAMINS._history_ids(rules,spec)
 vms=vm_moves(rules,spec)
 personals=__import__('personal_tutoring').current_moves(rules,spec)
 import vitamin_capacity as CAPACITY
 state=CAPACITY.current(rules,spec)
 historical=CAPACITY.historical_limit(rules,spec)
 import learning_slots as SLOTS
 occupancy=SLOTS.occupancy({'vitamin':max(state['capacity'],historical)},
  [{'id':str(i),'source':VITAMIN_SOURCE,'weights':{'vitamin':1}} for i in range(len(history))]+[{'id':'researcher:'+str(i),'source':__import__('researcher_fields').SOURCE,'weights':{'vitamin':1}} for i in range(__import__('researcher_fields').vitamin_equivalents(spec))],
  reservations=[{'id':mid,'source':VM_SOURCE,'weights':{'vitamin':1}} for mid in vms]+
   [{'id':mid,'source':__import__('personal_tutoring').CSV_SOURCE,'weights':{'vitamin':1}} for mid in personals])
 occupied=occupancy['used']['vitamin']
 if occupied>max(state['capacity'],historical):raise ValueError('Vitamin use exceeds its actual current or historical source capacity')
 return {**state,'historical_capacity':historical,'consumed':len(history),'reserved':len(vms)+len(personals),'occupied':occupied,'source':VITAMIN_SOURCE,'vm_moves':vms,'personal_tutor_moves':personals}


def classifications(rules,spec,*,require_routes=True):
 if spec.get('kind')=='trainer':return {mid:'trainer' for mid in known(rules,spec)}
 natural=natural_moves(rules,spec);history=spec.get('move_learning',{});vms=set(vm_moves(rules,spec))
 if not isinstance(history,dict):raise ValueError('move learning provenance must be a mapping')
 result={}
 for mid in known(rules,spec):
  if mid in vms:result[mid]='vm';continue
  if mid in natural:result[mid]='natural';continue
  record=history.get(mid)
  if isinstance(record,dict) and record.get('source') and (record.get('method') in ('tm','hm','tutor') or (record.get('method')=='feature' and type(record.get('paid_tp'))is int and record['paid_tp']>0)):
   result[mid]='taught'
  elif isinstance(record,dict) and record.get('method')=='feature' and record.get('source') and record.get('paid_tp')==0:result[mid]='granted'
  elif require_routes:raise ValueError('known non-natural move needs actual learning provenance: '+mid)
  else:result[mid]='unknown'
 return result


def describe(rules,spec,*,moves=None,abilities=None,require_routes=False):
 caps=capacities(rules,spec,abilities=abilities)
 baseline=classifications(rules,spec,require_routes=require_routes)
 current=effective_list(spec,'moves') if moves is None else moves
 selected=known(rules,{'moves':owned_list(spec,'moves',moves)})
 classes={};natural=natural_moves(rules,spec) if spec.get('kind')!='trainer' else set();active_vms=set(vm_moves(rules,spec))
 for mid in selected:
  if mid in baseline:classes[mid]=baseline[mid]
  elif spec.get('kind')=='trainer':classes[mid]='trainer'
  elif mid in active_vms:classes[mid]='vm'
  elif mid in natural:classes[mid]='natural'
  else:
   st=spec.get('state_grants',{})
   rows=[row for row in st.get('sources',{}).values() if mid in row.get('grants',{}).get('moves',[])]
   # Historical learning alone is not current ownership. Only a move still
   # present in the observed legacy list may use that acquisition receipt;
   # a current free grant must not inherit a forgotten move's old paid route.
   record=spec.get('move_learning',{}).get(mid)
   legacy_owned=mid in st.get('legacy',{}).get('moves',[])
   legacy_taught=legacy_owned and isinstance(record,dict) and record.get('source') and (record.get('method') in ('tm','hm','tutor') or (record.get('method')=='feature' and type(record.get('paid_tp'))is int and record['paid_tp']>0))
   classes[mid]='taught' if legacy_taught or any(row.get('tutor_points',0)>0 or (row.get('payment_id') and row.get('learning_route')=='taught') for row in rows) else 'granted' if rows else 'unknown'
 for mid in caps['exempt']:
  if mid not in selected:raise ValueError('selected slot exemption must name a currently known move')
 vms=vm_moves(rules,spec)
 personals=__import__('personal_tutoring').current_moves(rules,spec)
 counted=[mid for mid in selected if mid not in caps['exempt']]
 # A selected move that does not count toward the total list has zero total
 # weight, even if VM ordinarily weighs two. Taught/Vitamin channels stay intact.
 import learning_slots as SLOTS
 occupancy=SLOTS.occupancy({'total':caps['total'],'taught':caps['taught']},
  [{'id':mid,'source':'observed move ownership','weights':{'total':2 if mid in vms or mid in personals else 1,
    'taught':2 if classes[mid]=='vm' else 0 if (__import__('researcher_fields').pool_exempt(spec,mid) or __import__('chronicler').tutor_pool_exempt(rules,spec,mid)) else 1 if classes[mid]=='taught' else 0}} for mid in selected],
  exemptions={'total':caps['exempt']})
 slot_count=occupancy['used']['total']
 vitamins=vitamin_state(rules,spec) if vms or personals else None
 if vitamins and vitamins['occupied']>max(vitamins['capacity'],vitamins['historical_capacity']):raise ValueError('VM requires an available Vitamin slot')
 unknown=[mid for mid,value in classes.items() if value=='unknown']
 if require_routes and unknown:raise ValueError('known non-natural move needs actual learning provenance: '+unknown[0])
 return {**caps,'known':selected,'effective_moves':known(rules,{'moves':current}),'effective_classifications':{mid:classes.get(mid,'permission') for mid in known(rules,{'moves':current})},'counted':counted,'classifications':classes,'slot_count':slot_count,'vm_moves':vms,'personal_tutor_moves':personals,'vitamin_state':vitamins,'taught_count':occupancy['used']['taught'],'unknown_routes':unknown,'route_complete':not unknown}


def validate_spec(rules,spec,*,moves=None,abilities=None,require_routes=False):
 for row in spec.get('state_grants',{}).get('sources',{}).values():
  linked=row.get('ability_lesson',{}).get('connection_move')
  if linked is not None and linked not in known(rules,spec):raise ValueError('Connection Move cannot be forgotten')
 for row in spec.get('move_learning_log',[]):
  if row.get('connection_ability') in ('ability/생기','ability/생기-홈브류'):
   if row.get('source')!=row['connection_ability'] or row.get('move_id') not in ('move/버티기','move/버티기-홈브류'):
    raise ValueError('actual Vigor Connection learning provenance required')
   if row['move_id'] not in known(rules,spec):raise ValueError('Connection Move cannot be forgotten even after the Ability ends')
 __import__('growth_milestones').validate_inheritance(rules,spec)
 for mid,record in spec.get('move_learning',{}).items():
  if isinstance(record,dict) and 'archive_tutor_admission' in record:
   import pokemon_teaching as T,chronicler as CH
   admission=record['archive_tutor_admission']
   if record.get('source')!=CH.TUTOR or admission!=T.tutor_admission(rules,mid,record.get('learned_at_level'),policy=admission.get('policy')):
    raise ValueError('Archive Tutor admission differs from actual source and historical level')
  if isinstance(record,dict) and 'archive_tutor_edition' in record:
   import chronicler as CH
   CH.tutor_pool_exempt(rules,spec,mid)
 __import__('coordinator').validate_spec(rules,spec)
 import advanced_connection as CONNECTION
 CONNECTION.validate_protection(rules,spec)
 import example_species as EXAMPLES
 EXAMPLES.validate_spec(rules,spec,moves=owned_list(spec,'moves',moves))
 import special_entities as SPECIAL
 SPECIAL.validate_prime_spec(rules,spec,moves=moves or ())
 # New native tutoring receipts retain the admission at the learning level,
 # rather than reinterpreting a later level change as a new acquisition.
 for mid,record in spec.get('move_learning',{}).items():
  if isinstance(record,dict) and 'tutoring_admission' in record:
   import pokemon_teaching as T
   if record.get('source') not in (T.MENTOR,T.MOVE_TUTOR,T.EGG_TUTOR,'feat/개인-지도'):
    raise ValueError('tutoring admission requires its actual teaching source')
   T.source(rules,record['source'])
   if record['tutoring_admission']!=T.tutor_admission(rules,mid,record.get('learned_at_level'),policy=record['tutoring_admission'].get('policy')):
    raise ValueError('tutoring admission differs from selected source and historical level')
 import personal_tutoring as PERSONAL_TUTOR
 PERSONAL_TUTOR.validate_spec(rules,spec)
 import move_type_sync as MOVE_SYNC
 MOVE_SYNC.validate_spec(rules,spec)
 __import__('ace_trainer').validate_spec(rules,spec)
 out=describe(rules,spec,moves=moves,abilities=abilities,require_routes=require_routes)
 import learning_grant as LEARNING
 LEARNING.validate(rules,spec)
 if out['total'] is not None and out['slot_count']>out['total']:
  raise ValueError('known Pokemon moves exceed sourced capacity; explicit forgotten-move choice required')
 if out['taught'] is not None and out['taught_count']>out['taught']:
  raise ValueError('combined TM/Tutor moves exceed sourced capacity')
 return out


def validate_actor(actor):
 if actor.kind!='pokemon':return True
 import vitamin_moves as VITAMINS
 VITAMINS.validate(actor)
 vitamin_state(actor.r,actor.spec)
 validate_history(actor.r,actor.spec)
 validate_spec(actor.r,actor.spec,moves=actor.moves,abilities=actor.abilities)
 return True


def preflight_baseline(actor,field,values):
 if field=='moves':
  import advanced_connection as CONNECTION
  CONNECTION.forbid_forgetting(actor,values)
 import csv_item_capability_contracts as CSV_CAP
 if field=='moves' and 'csv_essence_projection' in actor.spec:
  added=[mid for mid in values if mid not in actor.spec.get('moves',[])]
  if any(not CSV_CAP.essence_move_allowed(actor,actor.r.move(mid)) for mid in added):
   raise ValueError('CSV Essence forbids learning Ghost/Aura Moves at Essence four or below')
 if actor.kind!='pokemon' or field not in ('moves','abilities'):return
 spec=deepcopy(actor.spec);st=spec.setdefault('state_grants',{})
 if not st:st['legacy']={f:[v for v in getattr(actor,f,[]) if v not in actor.spec.get(f,[])] for f in ('moves','abilities')}
 if st:
  old=spec.get(field,[])
  st.setdefault('legacy',{})[field]=[v for v in st.get('legacy',{}).get(field,[]) if v not in values and v not in old]
 spec[field]=list(dict.fromkeys(values))
 validate_spec(actor.r,spec,moves=effective_list(spec,'moves',actor.moves),abilities=effective_list(spec,'abilities',actor.abilities))


def preflight_move_grants(actor,values,source_id,kind,metadata):
 import csv_item_capability_contracts as CSV_CAP
 if 'csv_essence_projection' in actor.spec and any(not CSV_CAP.essence_move_allowed(actor,actor.r.move(mid)) for mid in values if mid not in actor.moves):
  raise ValueError('CSV Essence forbids learning Ghost/Aura Moves at Essence four or below')
 spec=deepcopy(actor.spec);st=spec.setdefault('state_grants',{})
 if st and st.get('version')!=1:raise ValueError('unsupported source ledger')
 if not st:st['legacy']={f:[v for v in getattr(actor,f,[]) if v not in spec.get(f,[])] for f in ('moves','abilities')}
 row=st.setdefault('sources',{}).get(source_id)
 if row is not None and (row.get('kind')!=kind or any(k in row and row[k]!=v for k,v in metadata.items())):raise ValueError('source identity cannot be reused with different provenance')
 row=st['sources'].setdefault(source_id,{'kind':kind,'grants':{},**deepcopy(metadata)})
 out=row['grants'].setdefault('moves',[])
 for mid in values:
  if mid not in out:out.append(mid)
 validate_spec(actor.r,spec)


def preflight_grant(actor,field,value,source_id,*,tutor_points=0):
 if actor.kind!='pokemon' or field not in ('moves','abilities'):return
 spec=deepcopy(actor.spec);st=spec.setdefault('state_grants',{})
 if not st:
  st['legacy']={f:[v for v in getattr(actor,f,[]) if v not in spec.get(f,[])] for f in ('moves','abilities')}
 row=st.setdefault('sources',{}).setdefault(source_id,{'grants':{},'tutor_points':tutor_points})
 values=row['grants'].setdefault(field,[])
 if value not in values:values.append(value)
 validate_spec(actor.r,spec)


def preflight_revoke(actor,source_ids):
 spec=deepcopy(actor.spec);st=spec.get('state_grants',{})
 for source in source_ids:
  st.get('sources',{}).pop(source,None);st.get('overlays',{}).pop(source,None)
 __import__('ace_trainer').forget_missing(actor.r,spec,at=0,reason='preflight actual learned source withdrawal')
 import advanced_connection as CONNECTION
 remaining=set(known(actor.r,{'moves':owned_list(spec,'moves')}))
 if set(CONNECTION.bound_moves(actor.r,actor.spec))-remaining:
  raise ValueError('a Connection Move cannot be forgotten through source revocation')
 CONNECTION.validate_protection(actor.r,spec)
 if actor.kind=='pokemon':validate_spec(actor.r,spec)


def _feature_id(owner,name):
 if name in CSV_SLOT_FEATURES:return name
 if name not in (*SLOT_FEATURES,'지침','평생학습','나뭇잎 포장','Guidance','Lifelong Learning','Foiling Foliage'):return None
 from acquired_features import _names,_resolve
 names=_names(owner,'feat/')
 if name not in names or not any(uid in SLOT_FEATURES for uid in names[name]):return None
 uid=_resolve(owner,name,'feat/',names)
 return uid if uid in SLOT_FEATURES else None


def _require_slot_feature(owner,uid):
 if owner.kind!='trainer':raise ValueError('trainer-owned slot feature required')
 from acquired_features import _names,_resolve
 names=_names(owner,'feat/');values=owner.spec.get('feats',[])
 if not isinstance(values,(list,tuple)):raise ValueError('actual acquired slot features must be a list')
 acquired=[v if v in CSV_SLOT_FEATURES else _resolve(owner,v,'feat/',names)
           for v in values if v in CSV_SLOT_FEATURES or v in names]
 equivalent=[v for v in acquired if SLOT_POLICIES.get(v)==SLOT_POLICIES[uid]]
 if equivalent!=[uid]:raise ValueError('one actual acquired slot feature source required')
 if owner.r._selected_rule(uid)!=uid:raise ValueError('selected slot feature variant needs its own policy')


def _project_slot_feature(owner,target,uid):
 import state_grants as G
 if target.kind!='pokemon' or target.spec.get('trainer_id')!=owner.entity_id:raise ValueError('slot feature target must be your actual Pokemon')
 key='feature:'+owner.entity_id+':'+uid
 row=G._source(target,key,'feature',owner_id=owner.entity_id,lifetime='your_pokemon',rule_id=uid,tutor_points=0)
 row['move_slot_policy']={'rule_id':uid}


def project_owner_slot_features(owner,targets):
 """Native ownership transactions project these passives before final validation."""
 targets=tuple(targets)
 for name in owner.spec.get('feats',[]):
  uid=_feature_id(owner,name)
  if SLOT_POLICIES.get(uid) not in (GUIDANCE,LIFELONG):continue
  _require_slot_feature(owner,uid)
  for target in targets:_project_slot_feature(owner,target,uid)


def register_passive_feature(engine,owner,name,targets=None):
 uid=_feature_id(owner,name)
 if SLOT_POLICIES.get(uid) not in (GUIDANCE,LIFELONG):return False
 _require_slot_feature(owner,uid)
 import world_entities as WORLD
 targets=[c for c in WORLD.actors(engine) if c.kind=='pokemon' and c.spec.get('trainer_id')==owner.entity_id] if targets is None else targets
 import state_grants as G
 targets=list(targets)
 for target in targets:
  if target.kind!='pokemon' or target.spec.get('trainer_id')!=owner.entity_id:raise ValueError('slot feature target must be your actual Pokemon')
 if len({id(c) for c in targets})!=len(targets):raise ValueError('slot feature targets must be distinct actual Pokemon')
 if not targets:return True
 def apply(e,staged_owner,*staged_targets):
  for c in staged_targets:
   _project_slot_feature(staged_owner,c,uid);validate_actor(c)
 G.transition(engine,owner,apply,participants=tuple(targets))
 return True


def select_foiling(engine,owner,target,move_id,*,reason,feature=FOILING):
 """Observe the selected active outcome; does not grant/pay the extended action."""
 if not isinstance(reason,str) or not reason.strip():raise ValueError('explicit slot selection observation reason required')
 uid=_feature_id(owner,feature)
 if SLOT_POLICIES.get(uid)!=FOILING:raise ValueError('selected Foiling Foliage source required')
 _require_slot_feature(owner,uid)
 if target.kind!='pokemon' or target.spec.get('trainer_id')!=owner.entity_id:raise ValueError('Foiling Foliage requires your actual Pokemon')
 mid=engine.r.move_id(move_id)
 if mid not in known(engine.r,{'moves':owned_list(target.spec,'moves',target.moves)}):raise ValueError('selected Foiling Foliage move must be currently learned')
 import state_grants as G
 key='feature:'+owner.entity_id+':'+uid
 def apply(e,c):
  row=G._source(c,key,'feature',owner_id=owner.entity_id,lifetime='your_pokemon',rule_id=uid,tutor_points=0)
  row['move_slot_policy']={'rule_id':uid,'selected_move':mid,'reason':reason}
  validate_actor(c)
  return deepcopy(row['move_slot_policy'])
 return G.transition(engine,target,apply)



def prepare_observation(rules,before,proposed,*,reason):
 """Return a full candidate spec; the caller commits it only after all checks."""
 candidate=deepcopy(proposed)
 if before.get('kind')!='pokemon':return candidate
 historical=deepcopy(before)
 record_natural_opportunities(rules,historical,reason='before observation: '+reason)
 if HISTORY in historical:candidate[HISTORY]=deepcopy(historical[HISTORY])
 record_natural_opportunities(rules,candidate,reason='after observation: '+reason)
 validate_spec(rules,candidate)
 return candidate



def observe_learning(engine,actor,move_id,*,method,source,paid_tp=0,replace=None,reason,application_id=None):
 """Record an observed acquired result, separately from paying/performing it."""
 if actor.kind!='pokemon':raise ValueError('Pokemon learning-route observation required')
 if method not in ('tm','hm','tutor','feature','level_up','egg','n_tutor','vm'):raise ValueError('explicit learning method required')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('learning observation reason required')
 if type(paid_tp)is not int or paid_tp<0:raise ValueError('observed paid Tutor Points must be nonnegative whole points')
 if not isinstance(source,str) or source not in engine.r.selection.units or engine.r._selected_rule(source)!=source:
  raise ValueError('selected learning source identity required')
 mid=engine.r.move_id(move_id);old=engine.r.move_id(replace) if replace is not None else None
 import csv_item_capability_contracts as CSV_CAP
 if mid is not None and 'csv_essence_projection' in actor.spec and not CSV_CAP.essence_move_allowed(actor,engine.r.move(mid)):
  raise ValueError('CSV Essence forbids learning Ghost/Aura Moves at Essence four or below')
 import type_sync as TYPE_SYNC
 if mid is not None and TYPE_SYNC.learning_permission(engine.r,actor.spec,mid,method) is False:raise ValueError('GM Type Sync exception forbids this learning route')
 if mid is None:raise ValueError('selected actual move identity required')
 if method in ('level_up','egg','n_tutor') and not any(row['kind']==method for row in current_natural_evidence(engine.r,actor.spec).get(mid,[])):
  raise ValueError('observed natural learning method lacks its species/level evidence')
 if method=='vm' and (source!=VM_SOURCE or paid_tp!=0 or not isinstance(application_id,str) or not application_id.strip()):raise ValueError('VM requires its exact source and completed application identity; no Tutor Point cost is inferred')
 import state_grants as G
 def apply(e,c):
  before=known(e.r,c.spec)
  if mid in before:raise ValueError('move already has a permanent learning source')
  if replace is not None and old not in before:raise ValueError('replacement must be an actually known permanent move')
  moves=[m for m in c.spec.get('moves',[]) if e.r.move_id(m)!=old]
  moves.insert(moves.index('struggle') if 'struggle' in moves else len(moves),mid)
  record={'method':method,'source':source,'paid_tp':paid_tp,'learned_at_level':c.level,'species_id':c.spec.get('species'),'reason':reason}
  if method=='vm':
   if any(row.get('application_id')==application_id for row in c.spec.get('move_learning_log',[]) if isinstance(row,dict)):raise ValueError('VM application has already been observed')
   record['application_id']=application_id
  candidate=deepcopy(c.spec)
  if old is not None:
   import move_type_sync as MOVE_SYNC
   MOVE_SYNC.forget_spec(e.r,candidate,old,at=e.elapsed_seconds,reason=reason)
   __import__('ace_trainer').forget_spec(e.r,candidate,old,at=e.elapsed_seconds,reason=reason)
  candidate['moves']=moves;candidate.setdefault('move_learning',{})[mid]=record
  if method=='vm':
   state=vitamin_state(e.r,candidate)
   if state['occupied']>state['capacity']:raise ValueError('VM requires an available current Vitamin slot')
  record_natural_opportunities(e.r,candidate,reason=reason)
  validate_spec(e.r,candidate,require_routes=True)
  c.spec['move_learning']=candidate['move_learning']
  if HISTORY in candidate:c.spec[HISTORY]=candidate[HISTORY]
  if 'move_type_sync' in candidate:c.spec['move_type_sync']=candidate['move_type_sync']
  if 'signature_techniques' in candidate:
   c.spec['signature_techniques']=candidate['signature_techniques'];c.spec['tutor_points']=candidate['tutor_points']
  c.spec.setdefault('move_learning_log',[]).append({'move_id':mid,'replaced':old,**deepcopy(record)})
  if method=='vm':
   import vitamin_capacity as CAPACITY
   CAPACITY.record(e.r,c.spec,'vm',application_id,move_id=mid)
  G.set_baseline(c,'moves',moves)
  return deepcopy(record)
 return G.transition(engine,actor,apply)


def observe_vm_learning(engine,actor,move_id,*,application_id,replace=None,reason):
 """Observe a completed GM-timed VM application, without inventing time/cost."""
 return observe_learning(engine,actor,move_id,method='vm',source=VM_SOURCE,application_id=application_id,replace=replace,reason=reason)
