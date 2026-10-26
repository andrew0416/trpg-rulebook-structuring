"""Selected-ability transitions with shared ownership and actual end events."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import common_checks as C
import state_grants as G
import combat_timing as TIME

CHOICES='ability_transition_choices'
TAG='ability_transition'

def install(rules):
 data=json.loads((Path(rules.root)/'data/ability-transition-policy.json').read_text(encoding='utf-8'))
 if data.get('schema_version')!=1:raise ValueError('reviewed ability-transition policy required')
 for file,digest in data['source_files'].items():
  if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('ability-transition source changed: '+file)
 rules.ability_transition_policy=data

def definition(rules,source):
 row=rules.ability_transition_policy['sources'].get(source)
 if row is not None and rules._selected_rule(source)!=source:raise ValueError('ability-transition source is not selected')
 return row

def registration(rules,name):
 reg=__import__('ability_exchange_contracts').registration(rules,name)
 if reg is not None:return reg
 sources=getattr(rules,'ability_transition_policy',{}).get('sources',{})
 for uid,row in sources.items():
  if row['manual'] and name in row['aliases']:
   source=name if name in sources else uid
   definition(rules,source)
   equivalent=[x for x,y in sources.items() if y['manual'] and y['manual']['name']==row['manual']['name']]
   return {'name':row['manual']['name'],'source_id':source,'equivalent_source_ids':equivalent}
 return None

def ability_id(rules,name):
 import move_state as M
 reg=M.ability_registration(rules,name)
 if reg:
  # Only registrars declaring reviewed equivalence collapse multiple source IDs.
  # Native single-source registrations already carry their canonical source_id.
  return reg['equivalent_source_ids'][0] if 'equivalent_source_ids' in reg else reg['source_id']
 if name.startswith('ability/') and name in rules.selection.units:return rules._selected_rule(name)
 return rules.selection.resolve_name(name.split('/',1)[1] if name.startswith('ability/') else name,('ability/',))

def label(rules,uid):
 import move_state as M
 reg=M.ability_registration(rules,uid)
 return reg['name'] if reg else uid.split('/',1)[1]

def component_definitions(rules,uid):
 row=rules.ability_transition_policy.get('innate_components',{}).get(uid)
 if row is None:return ({'id':'main','innate':False},)
 if rules._selected_rule(uid)!=uid:raise ValueError('selected Innate ability requires its own component policy')
 components=row.get('components')
 if not isinstance(components,list) or not components:raise ValueError('reviewed ability component definitions required')
 ids=[x.get('id') for x in components if isinstance(x,dict)]
 if len(ids)!=len(components) or any(not isinstance(value,str) or not value.strip() for value in ids) or len(set(ids))!=len(ids):
  raise ValueError('reviewed distinct ability component definitions required')
 if any(type(x.get('innate'))is not bool or not isinstance(x.get('source_text'),str) or not x['source_text'].strip() for x in components):
  raise ValueError('reviewed component Innate flags and source text required')
 return tuple({'id':x['id'],'innate':x['innate']} for x in components)


def component_ids(rules,uid,*,innate=None):
 rows=component_definitions(rules,uid)
 return tuple(row['id'] for row in rows if innate is None or row['innate'] is innate)


def wholly_innate(rules,uid):
 row=rules.ability_transition_policy.get('innate_components',{}).get(uid)
 if row is None:return False
 return all(x['innate'] for x in component_definitions(rules,uid))


def partially_innate(rules,uid):
 flags={row['innate'] for row in component_definitions(rules,uid)}
 return flags=={False,True}


def protected(rules,uid):
 return uid in rules.ability_transition_policy['protected_abilities'] or wholly_innate(rules,uid)


def registration_only(rules,uid):
 row=rules.ability_transition_policy.get('innate_components',{}).get(uid)
 return bool(row and row.get('registration_only') and wholly_innate(rules,uid))


def native_passive(rules,uid):
 if __import__('ability_exchange_contracts').handled(rules,uid):return True
 if uid in __import__('telepath').CONTRACTS:return __import__('telepath').registration(rules,uid) is not None
 if uid==__import__('sage').TOUCH:return __import__('sage').registration(rules,uid) is not None
 if uid in __import__('oracle').CORE_CONTRACTS:return __import__('oracle').registration(rules,uid) is not None
 if uid=='ability/틈새포착':
  if rules._selected_rule(uid)!=uid or rules.ability_effects.get('틈새포착')!=[{'type':'skill_mod','skill':'은신','value':2},{'type':'ignore_effects','no_hazard_trigger':True,'no_blessing_reactions':True,'ignore_substitute':True}]:raise ValueError('reviewed Core Infiltrator declaration changed')
  return True
 # These effects are dynamic consumers of the actual active ability list.
 return uid in ('ability/도주','ability/도주-playtest','ability/불면','ability/단순','ability/멀티타입','ability/흡반') or registration(rules,uid) is not None

def _raw_abilities(actor):
 st=actor.spec.get(G.KEY,{})
 result=list(actor.spec.get('abilities',[]))+list(st.get('legacy',{}).get('abilities',[]))
 for row in st.get('sources',{}).values():result.extend(row.get('grants',{}).get('abilities',[]))
 overlays=[row['abilities'] for row in st.get('overlays',{}).values() if 'abilities' in row]
 if overlays:result=overlays[-1]
 return list(dict.fromkeys(result))


def _component_projection(actor,values,*,include_suppressed=False,ignored_sources=(),check_producer=True):
 rules=actor.r;result={};labels={}
 for value in values:
  uid=ability_id(rules,value);labels.setdefault(uid,value);result.setdefault(uid,set()).update(component_ids(rules,uid))
 operations=[(r['ability_operation'],r.get('rule_id')) for key,r in actor.spec.get(G.KEY,{}).get('sources',{}).items() if key not in ignored_sources and 'ability_operation' in r]
 for op,source in operations:
  if not isinstance(op,dict) or set(op)!={'kind','remove','add'} or op['kind'] not in ('copy','replace','suppress') or not all(isinstance(op[k],list) and all(isinstance(x,str) for x in op[k]) for k in ('remove','add')):raise ValueError('invalid source-owned ability operation')
  if include_suppressed and op['kind']=='suppress':continue
  source_row=rules.ability_transition_policy.get('sources',{}).get(source)
  if source_row is None:
   import reactive_ability_events as REACTIVE
   mode=REACTIVE.operation_mode(rules,source)
   if mode is None:
    import duelist as DUELIST
    mode='replace' if not check_producer and source==DUELIST.MANUAL else DUELIST.operation_mode(actor,source)
   if mode is None:mode=__import__('ability_exchange_contracts').operation_mode(rules,source)
   if mode is None:raise ValueError('ability operation requires its reviewed producer')
  else:mode=source_row['mode']
  for uid in op['remove']:
   result.setdefault(uid,set()).difference_update(component_ids(rules,uid,innate=False))
  for uid in op['add']:
   labels.setdefault(uid,label(rules,uid));available=component_ids(rules,uid) if mode=='replace' else component_ids(rules,uid,innate=False)
   result.setdefault(uid,set()).update(available)
 ordered={}
 for uid,active_ids in result.items():
  if not active_ids:continue
  declared=component_ids(rules,uid);ordered[uid]=tuple(value for value in declared if value in active_ids)
 return ordered,labels


def project_components(actor,values=None,*,include_suppressed=False,ignored_sources=()):
 projected,_=_component_projection(actor,_raw_abilities(actor) if values is None else values,
  include_suppressed=include_suppressed,ignored_sources=ignored_sources)
 return projected


def project(actor,values,*,include_suppressed=False,ignored_sources=()):
 projected,labels=_component_projection(actor,values,include_suppressed=include_suppressed,ignored_sources=ignored_sources)
 return [labels[uid] for uid in projected]


def owned_from_spec(rules,spec):
 """Read possession for slot/receipt checks; live producers validate their own receipts."""
 from types import SimpleNamespace
 import move_state as M
 actor=SimpleNamespace(r=rules,spec=spec)
 projected,labels=_component_projection(actor,M.effective_list(spec,'abilities'),include_suppressed=True,check_producer=False)
 return [labels[uid] for uid in projected]


def active(actor,uid,component=None):
 if actor.abilities_suppressed:return False
 canonical=ability_id(actor.r,uid);active_ids=project_components(actor).get(canonical,())
 if component is None:return bool(active_ids)
 if not isinstance(component,str) or not component:raise ValueError('ability component identity required')
 if component not in component_ids(actor.r,canonical):raise ValueError('unknown ability component')
 return component in active_ids


def effect_active(actor,effect):
 """Native passive ownership follows its selected source, not a display label."""
 if actor.abilities_suppressed:return False
 source=effect.get('_rule_id')
 if isinstance(source,str) and source.startswith('ability/'):
  return active(actor,source)
 name=effect.get('_ability')
 return isinstance(name,str) and active(actor,name)


def component_snapshot(rules,chosen,copied):
 def one(uid):
  return {'all':list(component_ids(rules,uid)),'innate':list(component_ids(rules,uid,innate=True)),
   'transferable':list(component_ids(rules,uid,innate=False))}
 return {'chosen':one(chosen),'copied':one(copied)}

def known(actor):
 return list(dict.fromkeys(ability_id(actor.r,x) for x in G.effective(actor,'abilities',include_suppressed=True)))

def key(source,target):
 return source+'@'+target.entity_id

def select(engine,actor,target,source,*,ability=None,allies=(),reason,edition=None):
 import ability_exchange_contracts as X
 if X.source(engine.r,source) is not None:
  return X.select(engine,actor,target,source,ability=ability,allies=allies,reason=reason,edition=edition)
 if edition is not None:raise ValueError('edition belongs only to its reviewed exchange source')
 row=definition(engine.r,source)
 if row is None:raise ValueError('reviewed ability-transition source required')
 if not isinstance(reason,str) or not reason.strip():raise ValueError('actual choice reason required')
 import world_entities as W
 index=W.actor_index(engine)
 if index.get(actor.entity_id) is not actor or index.get(target.entity_id) is not target:raise ValueError('actual chooser and target required')
 if row['choice'] is None and ability is not None:raise ValueError('random selection cannot be replaced by a chosen ability')
 uid=ability_id(engine.r,ability) if ability is not None else None
 owner=actor if row['choice']=='user' else target
 if uid is not None and uid not in known(owner):raise ValueError('chosen ability is not known by the actual selection owner')
 if row['mode']!='copy_allies' and allies:raise ValueError('this source does not share with allies')
 ally_ids=[]
 for ally in allies:
  if index.get(ally.entity_id) is not ally or ally is actor or ally is target or not actor.side or ally.side!=actor.side:raise ValueError('explicit other actual allies required')
  if ally.entity_id in ally_ids:raise ValueError('an ally may be selected only once')
  ally_ids.append(ally.entity_id)
 record={'source':source,'target_id':target.entity_id,'ability_id':uid,'allies':ally_ids,'reason':reason}
 actor.spec.setdefault(CHOICES,{})[key(source,target)]=record
 return deepcopy(record)

def choice(engine,actor,target,source,row):
 owner=actor if row['choice']=='user' else target
 pool=known(owner)
 if not pool:
  if row['mode'] in ('suppress','replace'):return None,{}
  raise ValueError('ability transition requires an actual known ability')
 selected=actor.spec.get(CHOICES,{}).get(key(source,target),{})
 uid=selected.get('ability_id')
 if row['choice']:
  if uid is None:
   if len(pool)!=1:raise ValueError('choose the actual ability before activating this source')
   uid=pool[0]
  if uid not in pool:raise ValueError('selected ability changed before activation')
 return uid,selected

def preflight(engine,actor,target,effect,source):
 row=definition(engine.r,source)
 if row is None or effect!={'type':'ability_transition','contract':source}:raise ValueError('exact reviewed ability-transition effect required')
 if not engine.encounter_active:raise ValueError('ability lifetime requires an actual encounter')
 import world_entities as W,partial_entities as PARTIAL
 index=W.actor_index(engine)
 for c in (actor,target):
  PARTIAL.require_complete(c,'ability transition')
  if index.get(c.entity_id) is not c:raise ValueError('ability transition needs actual registered actors')
 if row['mode']=='swap' and actor is target:raise ValueError('Skill Swap needs distinct participants')
 uid,selected=choice(engine,actor,target,source,row)
 if row['mode'] in ('copy_random','swap') and not known(target):raise ValueError('random donor has no ability')
 # Validate every participating component policy without initializing a legacy
 # state-grant ledger during a read-only preflight.
 candidates=list(dict.fromkeys([*project_components(actor,include_suppressed=True),
  *project_components(target,include_suppressed=True)]))
 if row.get('replacement') is not None:candidates.append(row['replacement'])
 for candidate in candidates:component_definitions(engine.r,candidate)
 allies=[]
 for aid in selected.get('allies',[]):
  ally=index.get(aid)
  if row['mode']!='copy_allies' or ally is None or ally is actor or ally is target or ally.side!=actor.side:raise ValueError('selected sharing ally changed')
  import body_state as BODY
  if not BODY.in_range(engine,actor,ally,6):raise ValueError('Doodle ally must be within6 meters')
  allies.append(ally)
 if row['manual']:
  if target.kind not in ('trainer','pokemon'):raise ValueError('copying ability targets a Trainer or Pokemon')
  import body_state as BODY
  if not BODY.in_range(engine,actor,target,row['manual']['range']):raise ValueError('copying target is outside actual10-meter range')
 return row,uid,allies

def apply(engine,actor,target,effect,ctx):
 source=ctx['source_id'];row,_,allies=preflight(engine,actor,target,effect,source)
 def staged(e,a,t,*friends):
  spec,uid,_=preflight(e,a,t,effect,source)
  donor_pool=known(t);random_index=None
  if uid is None and spec['mode'] in ('suppress','replace'):return {'applied':False,'reason':'target has no ability'}
  if spec['mode'] in ('copy_random','swap'):
   random_index=e.rng.randrange(len(donor_pool));copied=donor_pool[random_index]
  else:copied=uid
  blocked=(protected(e.r,copied) or (spec['mode']=='swap' and protected(e.r,uid)))
  if blocked:return {'applied':False,'reason':'ability cannot be copied or disabled','selected':copied,'random_index':random_index,'pool':donor_pool}
  component_contract=component_snapshot(e.r,uid,copied)
  mode=spec['mode']
  if mode=='suppress':changes=[(t,{'kind':'suppress','remove':[uid],'add':[]})]
  elif mode=='replace':changes=[(t,{'kind':'replace','remove':[uid],'add':[spec['replacement']]})]
  elif mode=='swap':changes=[(a,{'kind':'replace','remove':[uid],'add':[copied]}),(t,{'kind':'replace','remove':[copied],'add':[uid]})]
  else:changes=[(c,{'kind':'copy','remove':[],'add':[copied]}) for c in [a,*friends]]
  results=[]
  for holder,operation in changes:
   grant=G.effect_source(holder,ctx,'ability-transition')
   record={'source':source,'effect_contract':True,'encounter_end':True,'grant_source':grant,
    'effect_receipt':ctx['effect_receipt'],'effect_occurrence':ctx['effect_occurrence'],
    TAG:deepcopy(operation),'ability_origin':t,'ability_producer':a,'ends':list(spec['ends']),
    'selection':{'chosen':uid,'copied':copied,'random_index':random_index,'pool':donor_pool,
     'component_contract':deepcopy(component_contract)},
    'recipient_id':holder.entity_id}
   G._source(holder,grant,'effect',owner_id=a.entity_id,rule_id=source,lifetime='ability_transition',
     ability_operation=deepcopy(operation),ability_ends=list(spec['ends']))
   G.materialize(holder,'abilities');G.reconcile(e,holder)
   TIME.install(e,holder,record);results.append(holder.entity_id)
   if holder.fainted and 'faint' in spec['ends']:TIME.expire(e,holder,record)
  e.time_actors([a,t,*friends]);a.spec.get(CHOICES,{}).pop(key(source,t),None)
  return {'applied':True,'recipients':results,'selected':copied,'random_index':random_index,'pool':donor_pool,
   'component_contract':component_contract}
 return G.transition(engine,actor,staged,participants=(target,*allies))

def activate(engine,actor,name,target):
 import ability_exchange_contracts as X
 if X.registration(engine.r,name) is not None:return X.activate(engine,actor,name,target)
 if not X.admit_trigger(engine,actor,name):raise ValueError('Neutralizing Gas prohibits this triggered ability')
 reg=registration(engine.r,name)
 if reg is None:raise ValueError('reviewed manual copy source required')
 source=reg['source_id'];row=definition(engine.r,source)
 if actor.fainted or actor.abilities_suppressed or not any((registration(engine.r,x) or {}).get('name')==reg['name'] for x in actor.abilities):raise ValueError('actual active copying ability required')
 effect={'type':'ability_transition','contract':source};preflight(engine,actor,target,effect,source)
 def staged(e,a,t):
  import frequency as F,turn as TURN,effects as FX
  usage='ability:'+reg['name'];frequency=row['manual']['frequency']
  if not F.activation_allowed(a,usage,frequency,engine=e,action_actor=a):raise ValueError('copying ability Scene frequency exhausted')
  if not TURN.spend(e,a,row['manual']['action'],reg['name']):raise ValueError('copying ability action unavailable')
  F.consume_activation(a,usage,frequency,engine=e,action_actor=a)
  result=FX.run_effects(e,a,t,[effect],{'hit':True,'nat':None},source)
  if result.pending:raise ValueError('copying ability effect did not complete')
  return result
 return G.transition(engine,actor,staged,participants=(target,))

def end(engine,actor,event):
 # Transform explicitly restores the prior Move List at these native boundaries.
 if event in ('recall','faint','encounter'):
  for sid,row in list(actor.spec.get(G.KEY,{}).get('sources',{}).items()):
   if row.get('rule_id')=='move/변신' and sid in actor.spec.get(G.KEY,{}).get('overlays',{}):
    G.revoke(actor,sid,engine=engine)
 for record in list(TIME.records(actor)):
  if TAG in record and event in record['ends']:TIME.expire(engine,actor,record)
 import reactive_ability_events as REACTIVE
 REACTIVE.end(engine,actor,event)
 __import__('ability_exchange_contracts').end(engine,actor,event)

def validate_world(engine,index):
 for actor in index.values():
  expected={k for k,v in actor.spec.get(G.KEY,{}).get('sources',{}).items() if 'ability_operation' in v and 'reactive_ability' not in v and 'duelist_manual' not in v and 'ability_exchange' not in v};seen=set()
  for record in TIME.records(actor):
   if TAG not in record:continue
   source=record['source'];definition_row=definition(engine.r,source)
   if definition_row is None or record['ends']!=definition_row['ends'] or record.get('encounter_end') is not True:raise ValueError('ability-transition lifetime differs from source')
   grant=record.get('grant_source');owner=actor.spec[G.KEY]['sources'].get(grant)
   if grant not in expected or grant in seen or owner.get('ability_operation')!=record[TAG]:raise ValueError('ability transition and owned contribution disagree')
   seen.add(grant)
   if record['recipient_id']!=actor.entity_id or owner.get('rule_id')!=source or owner.get('ability_ends')!=record['ends']:raise ValueError('ability transition identity mismatch')
   allowed={'source','effect_contract','encounter_end','grant_source','effect_receipt','effect_occurrence',TAG,'ability_origin','ability_producer','ends','selection','recipient_id','owned_statuses','installing'}
   if set(record)!=allowed or record.get('effect_contract') is not True or record.get('owned_statuses') or record.get('installing') is not False:raise ValueError('ability transition has unreviewed extra effects or timing')
   selection=record['selection'];pool=selection.get('pool');chosen=selection.get('chosen');copied=selection.get('copied');random_index=selection.get('random_index')
   if not isinstance(pool,list) or not pool or len(pool)!=len(set(pool)):raise ValueError('actual unique donor ability snapshot required')
   for uid in pool:
    if ability_id(engine.r,uid)!=uid:raise ValueError('donor snapshot needs canonical abilities')
   mode=definition_row['mode']
   if mode in ('copy_random','swap'):
    if type(random_index)is not int or not 0<=random_index<len(pool) or copied!=pool[random_index]:raise ValueError('random selection differs from recorded donor snapshot')
   elif random_index is not None or copied!=chosen or chosen not in pool:raise ValueError('chosen selection differs from donor snapshot')
   expected_components=component_snapshot(engine.r,chosen,copied)
   if selection.get('component_contract')!=expected_components:raise ValueError('ability component provenance differs from the reviewed policy')
   if protected(engine.r,copied) or (mode=='swap' and protected(engine.r,chosen)):raise ValueError('protected ability cannot have a transition')
   producer=record['ability_producer'];origin=record['ability_origin']
   if index.get(producer.entity_id) is not producer or index.get(origin.entity_id) is not origin:raise ValueError('ability origin or producer identity is missing')
   if mode=='suppress':expected_operation={'kind':'suppress','remove':[chosen],'add':[]};recipients=[origin]
   elif mode=='replace':expected_operation={'kind':'replace','remove':[chosen],'add':[definition_row['replacement']]};recipients=[origin]
   elif mode=='swap':
    recipients=[producer,origin]
    expected_operation={'kind':'replace','remove':[chosen if actor is producer else copied],'add':[copied if actor is producer else chosen]}
   else:
    recipients=[producer] if mode!='copy_allies' else [actor]
    expected_operation={'kind':'copy','remove':[],'add':[copied]}
   if actor not in recipients or record[TAG]!=expected_operation:raise ValueError('ability operation differs from the actual source contract')
   op=record[TAG]
   if op['kind'] not in ('copy','replace','suppress') or not isinstance(op['remove'],list) or not isinstance(op['add'],list):raise ValueError('invalid selected-ability operation')
   for uid in op['remove']+op['add']:
    if ability_id(engine.r,uid)!=uid:raise ValueError('ability operation needs canonical identities')
   receipt=getattr(engine,'_effect_dispatch_receipts',{}).get(record['effect_receipt'])
   if not receipt or receipt.get('status')!='completed':raise ValueError('ability transition needs completed native receipt')
   import effect_contracts as CONTRACTS
   CONTRACTS.validate_receipt(engine,record['effect_receipt'],source,record['effect_occurrence'],receipt['actor'],receipt['target'],receipt['effect'])
   if receipt['effect']!={'type':'ability_transition','contract':source}:raise ValueError('ability receipt has another effect')
   if record['ability_producer'] is not receipt['actor'] or record['ability_origin'] is not receipt['target'] or owner['owner_id']!=receipt['actor'].entity_id:raise ValueError('ability provenance differs from actual actors')
   if not receipt.get('result') or actor.entity_id not in receipt['result'].get('recipients',[]):raise ValueError('native receipt did not grant this recipient')
   result=receipt['result']
   if result.get('applied') is not True or result.get('selected')!=copied or result.get('pool')!=pool or result.get('random_index')!=random_index or result.get('component_contract')!=expected_components:raise ValueError('ability choice differs from completed native result')
  if expected!=seen:raise ValueError('ability contribution lacks its end-event record')
  if expected and actor.abilities!=G.effective(actor,'abilities'):raise ValueError('ability projection differs from source-owned state')
 return __import__('ability_exchange_contracts').validate_world(engine,index)
