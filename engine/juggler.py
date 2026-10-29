"""Juggler source adapters. Party, physical balls and native Interrupts own transitions."""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import json
import common_checks as C, state_grants as G, world_entities as W

CLASS='class/저글러';BOUNCE='feat/바운스-샷';SHOW='feat/저글링-쇼'
ROUND='feat/왕복-여행';TAG='feat/태그-인';EMERGENCY='feat/긴급-방출';FIRST='feat/퍼스트-블러드'
QUICK='feat/퀵-스위치';LOCK='move/록온';KEY='juggler_native'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(843,845),BOUNCE:(847,852),SHOW:(854,858),ROUND:(860,865),TAG:(867,872),EMERGENCY:(874,878),FIRST:(880,885)}
PARENTS={CLASS:(QUICK,),BOUNCE:(CLASS,),SHOW:(CLASS,),ROUND:(CLASS,),TAG:(ROUND,),EMERGENCY:(CLASS,),FIRST:(TAG,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[831,831] if u==CLASS else list(s),
 'clause_id':'C04-038' if u==FIRST else 'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1]),
 'parents':list(PARENTS[u]),'minimum_rank':{CLASS:3,ROUND:4,TAG:5,EMERGENCY:5,FIRST:6}.get(u,0),
 'stat_tags':['spe'],'ranked':False,'branch':False} for u,s in FEATURES.items()}
DEFINITIONS[QUICK]={'span':[649,653],'catalog_span':[649,653],'clause_id':'input/ch03-skills-edges-feats.md:649-653','parents':[],'minimum_rank':3,'stat_tags':[],
 'source':{'file':'input/ch03-skills-edges-feats.md','sha256':'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'}}

def state(a):return a.spec.setdefault(KEY,{'events':[],'uses':{},'lock_on':[]})
def records(a,u=None,active=False):
 if a is None:return []
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(a, FEATURES, u, active=active)]
def acquired(a,u=CLASS):
 rows=records(a,u,True)
 return rows[-1] if rows else None

def source(rules,u,edition='core'):
 from source_context import verified_source
 if edition not in ('core','local_translation','local_csv'):raise ValueError('explicit Core or local Juggler source required')
 if u not in (*FEATURES,QUICK):raise ValueError('reviewed Juggler or Quick Switch source required')
 path='input/ch03-skills-edges-feats.md' if u==QUICK else 'input/ch04-trainer-classes.md'
 digest=SOURCE_SHA256
 if u==QUICK:digest=contract(rules)['source_files'][path]
 verified_source(rules,{'file':path,'sha256':digest},label='Juggler source')
 if rules._selected_rule(u)!=u:raise ValueError('selected Juggler source needs its reviewed adapter')
 row={'edition':edition,'file':path,'sha256':digest,'span':[649,653] if u==QUICK else list(FEATURES[u])}
 if edition=='core':
  original=contract(rules)['core']
  if sha256((Path(rules.root)/original['file']).read_bytes()).hexdigest()!=original['sha256']:raise ValueError('reviewed original Core Juggler source changed')
  row['interpretation']={'file':original['file'],'sha256':original['sha256'],'pages':[59] if u==QUICK else [100,101]}
 if edition=='local_csv':
  file='input/db/feats.csv';digest=contract(rules)['source_files'][file]
  verified_source(rules,{'file':file,'sha256':digest},label='local Juggler CSV')
  row.update(file=file,sha256=digest,record=contract(rules)['csv_records'].get(u,{}).get('record'),span=None)
 return row

def contract(rules):
 row=getattr(rules,'_juggler_contract',None)
 if row is None:
  row=json.loads((Path(rules.root)/'data/juggler-source-contract.json').read_text(encoding='utf8'))
  for file,digest in row['source_files'].items():
   if sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('Juggler source changed: '+file)
  rules._juggler_contract=row
 return row

def acquisition_snapshot(e,a,u,rank,selection):
 import skill_modifiers as SK,acquired_features as A
 if rank is not None:raise ValueError('Juggler Features are not Ranked')
 if selection is not None and (type(selection)is not dict or set(selection)!={'edition'}):raise ValueError('one immutable Juggler source selection required')
 edition='core' if selection is None else selection['edition'];selected=source(e.r,u,edition)
 return {'skills':{s:SK.rank(e.r,a,s)[2] for s in ('곡예','교활')},
  'parents':{p:A.owned_rule_count(a,p) for p in PARENTS.get(u,())},'selection':deepcopy(selection),'edition':edition,'source':selected}

def qualification(a,u,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'skills','parents','selection','edition','source'}:raise ValueError('actual Juggler qualification observations required')
 if snapshot['source']!=source(a.r,u,snapshot['edition']):raise ValueError('immutable actual Juggler source required')
 if set(snapshot['skills'])!={'곡예','교활'} or set(snapshot['parents'])!=set(PARENTS.get(u,())):raise ValueError('exact Juggler parents and both skills required')
 for v in snapshot['skills'].values():C.integer(v,'Juggler skill rank',1)
 for v in snapshot['parents'].values():C.integer(v,'actual acquired Juggler parent count',0)
 enough=min(snapshot['skills'].values())>=3 if u==CLASS else max(snapshot['skills'].values())>=DEFINITIONS[u]['minimum_rank']
 return Q.require(u,'native','acquire',[Q.check('trainer','prerequisite',a.kind=='trainer','actual Trainer required'),
  Q.check('parents','prerequisite',all(v==1 for v in snapshot['parents'].values()),'actual Juggler parent and Quick Switch required'),
  Q.check('skills','prerequisite',enough,'printed Juggler skill rank required')])

def after_acquire(e,a,u,sid):
 if u!=QUICK:G.stat(a,'spe',1,sid,operation_id='acquisition_stat_tag')
def validate_acquisition(a,r,sid,active):
 if active and r['feature_id']!=QUICK and a.spec.get(G.KEY,{}).get('stat_sources',{}).get('spe',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Juggler Speed tag required')
def require(e,a,u):
 W.require_actors(e,a);source(e.r,u,edition(a,u))
 if not acquired(a,u) or a.kind!='trainer' or a.fainted or a.captured or not a.on_field:raise ValueError('actual available acquired Juggler Feature required: '+u)
def edition(a,u):
 r=acquired(a,u)
 return r['snapshot']['edition'] if r else 'core'
def boundary(e):
 import initiative_interrupts as I
 a=I.suspended_owner(e) or e._active_turn_actor
 return {'round':e.round_no,'at':e.elapsed_seconds,'actor_id':None if a is None else a.entity_id,
  'turn':None if a is None else a.custom_conditions.get('combat_turn_serial',0),
  'actions':[] if a is None else list(getattr(a,'_action_history',[]))}
def event(e,kind,p,*,trainer=None,request_id=None,source_id=None):
 if not e.encounter_active or e.round_start_seconds is None:return
 for a in W.actors(e):
  if a.kind!='trainer' or not (acquired(a) or __import__('acquired_features').owned_rule_count(a,QUICK)):continue
  rows=state(a)['events'];uid=a.entity_id+':juggler-event:'+str(len(rows)+1)
  rows.append({'id':uid,'kind':kind,'pokemon_id':p.entity_id,'trainer_id':None if trainer is None else trainer.entity_id,
   'request_id':request_id,'source':source_id,'boundary':boundary(e)})
def trigger(e,a,event_id,kind=None):
 rows=[r for r in a.spec.get(KEY,{}).get('events',[]) if r['id']==event_id]
 if len(rows)!=1 or rows[0]['boundary']!=boundary(e) or kind is not None and rows[0]['kind']!=kind:raise ValueError('actual immediate Juggler producer occurrence required')
 return rows[0]

def pay(e,a,u,kind,ap):
 import turn as T,action_points as AP
 if AP.available(a)<ap:raise ValueError('available Juggler AP required')
 if not T.spend(e,a,kind,u,_triggered_source=u):raise ValueError('actual Juggler '+kind+' action required')
 if ap:AP.spend(a,ap)

def party_plan(e,a,recall,send,feature):
 """Authenticate source exceptions before ordinary party payment or mutation."""
 import acquired_features as A
 if type(feature)is not dict or set(feature)-{'source','event_id','completion_id','tag_in'}:raise ValueError('exact Juggler party source context required')
 u=feature.get('source');tag=feature.get('tag_in',False)
 if type(tag)is not bool:raise ValueError('explicit Tag In selection required')
 if tag:
  require(e,a,TAG)
  if len(recall)!=1 or a.spec.get(KEY,{}).get('pending_tag'):raise ValueError('one actual recall and unoccupied next-release Tag In required')
 if u==QUICK:
  source(e.r,QUICK)
  if A.owned_rule_count(a,QUICK)!=1:raise ValueError('actual acquired Quick Switch required')
  if len(recall)!=1 or len(send)!=1:raise ValueError('Quick Switch requires one actual complete switch')
  if e._active_turn_actor is not a:
   r=trigger(e,a,feature.get('event_id'));p=W.actor_index(e)[r['pokemon_id']]
   if r['source']==QUICK or not (r['kind']=='faint' and p is recall[0] or r['kind']=='release' and p.side!=a.side):raise ValueError('Quick Switch needs own faint or opposing release; recursive Quick Switch is forbidden')
  ap=1 if acquired(a) else 2;kind='free'
 elif u==ROUND:
  require(e,a,ROUND)
  if len(recall)!=1 or len(send)!=1:raise ValueError('Round Trip switches exactly the actual Move user')
  row=getattr(e,'_move_completions',{}).get(feature.get('completion_id'))
  if row is None or row['phase']!='complete' or row['actor'] is not recall[0] or row['actor'].spec.get('trainer_id')!=a.entity_id or a.spec.get(KEY,{}).get('move_window')!={'id':row['id'],'boundary':boundary(e)}:raise ValueError('Round Trip needs the just completed whole owned Pokemon Move')
  ap=1;kind='free'
 elif u==EMERGENCY:
  require(e,a,EMERGENCY)
  if recall or len(send)!=1:raise ValueError('Emergency Release permits exactly one actual release')
  ap=1 if edition(a,u)=='local_csv' else 2;kind='free' if ap==1 else 'shift'
 elif u is None and tag:ap=0;kind=None
 else:raise ValueError('reviewed Juggler party source required')
 result={'source':u,'action':kind,'ap':ap,'tag_in':tag,'ignore_trapped':u==ROUND,'preserve_turn':u in (QUICK,ROUND)}
 if u==ROUND:result['completion_id']=row['id']
 return result

def party_payment(e,a,plan):
 import frequency as F
 u=plan['source']
 if u:
  frequency=None
  if u==EMERGENCY and edition(a,u)=='local_csv':frequency=__import__('capture_specialist')._quota(e,a,u,'turn')
  pay(e,a,u,plan['action'],plan['ap'])
  if frequency:F.consume_activation(a,u,frequency,engine=e)
 if plan['tag_in']:
  if e._active_turn_actor is a:pay(e,a,TAG,'free',1)
  else:
   if __import__('action_points').available(a)<1:raise ValueError('available Tag In AP required')
   __import__('action_lifecycle').triggered_free_action(e,a,TAG);__import__('action_points').spend(a,1)

def act(e,a,*,recall=(),send=(),request_id,reason,source_id=None,event_id=None,completion_id=None,tag_in=False,release_throw=None):
 """Native party API with a source-bound action frame when reacting off-turn."""
 import party_actions as P,initiative_interrupts as I
 feature={'source':source_id,'tag_in':tag_in}
 if event_id is not None:feature['event_id']=event_id
 if completion_id is not None:feature['completion_id']=completion_id
 participants=tuple(dict.fromkeys([*recall,*(p for p,_ in send)]))
 waiting=[]
 def apply(se,owner,*subjects):
  index=W.actor_index(se);recalled=[index[p.entity_id] for p in recall];sent=[(index[p.entity_id],pos) for p,pos in send]
  if request_id in owner.spec.get(P.KEY,{}):
   return P.act(se,owner,recall=recalled,send=sent,request_id=request_id,reason=reason,release_throw=release_throw,feature=feature)
  plan=party_plan(se,owner,recalled,sent,feature)
  own=se._active_turn_actor is owner
  current=I.frame(se)
  if not own and current and current['actor'] is owner:own=True
  window=None
  if not own and source_id is not None:
   parent=se._active_turn_actor
   if parent is None:raise ValueError('Juggler Interrupt requires an actual suspended turn')
   raw={'kind':'turn','actor_id':parent.entity_id,'serial':parent.custom_conditions.get('combat_turn_serial',0),'round':se.round_no}
   budget={} if plan['action']=='free' else {plan['action']:1}
   state(owner)['executing']={'source':source_id or TAG,'request_id':request_id}
   payment='current' if getattr(owner,'budget',None)is not None else 'next'
   declaration={'id':request_id,'actor_id':owner.entity_id,'source':source_id or TAG,'priority':0,'mode':'reaction','payment':payment,'budget':budget,'clock':'none'}
   window=I.queue(se,[declaration],trigger=raw)['window_id'];I.begin(se,window,request_id)
  try:result=P.act(se,owner,recall=recalled,send=sent,request_id=request_id,reason=reason,release_throw=release_throw,feature=feature)
  except __import__('passive_events').PassiveEventPending as pending:
   if se._passive_pending!=pending.event_id:raise
   waiting.append(pending.event_id);return None
  if window:finish_party_reaction(se,owner,request_id)
  return result
 def scoped(se,owner,*subjects):
  parent=getattr(se,'_move_completions',{}).get(completion_id) if source_id==ROUND else None
  receipt=owner.spec.get(P.KEY,{}).get(request_id)
  with __import__('action_lifecycle').completion_reaction(se,owner,source_id,parent,receipt=receipt,
      _child=(owner,'escape',P.SOURCE)):
   return apply(se,owner,*subjects)
 result=G.transition(e,a,scoped,participants=participants,include_rulings=True,include_grid=e.grid is not None)
 if waiting:raise __import__('passive_events').PassiveEventPending(waiting[0])
 return result

def finish_party_reaction(e,a,request_id):
 import initiative_interrupts as I
 proof=state(a).get('executing');frame=I.frame(e)
 if proof and proof['request_id']==request_id:
  if frame is None or frame['actor'] is not a or frame['request_id']!=request_id:raise ValueError('actual retained Juggler party Interrupt required')
  I.finish(e);state(a).pop('executing',None)

def free_reaction(e,a,row):
 r=state(a).get('executing')
 if not r or r!={'source':row['source'],'request_id':row['id']} or row['source'] not in (QUICK,ROUND,EMERGENCY,TAG):raise ValueError('actual Juggler source-owned reaction required')
 if row['source']!=QUICK:require(e,a,row['source'])

def validate_party_replacement(e,p,source_id,request_id):
 import party_actions as P
 a=P.owner(e,p);record=None if a is None else a.spec.get(P.KEY,{}).get(request_id)
 if record is None and source_id in ('move/배턴터치',ROUND):
  return __import__('native_switch_transfer').validate_replacement(e,p,source_id,request_id)
 if record is None or p.entity_id not in record['result']['sent'] or source_id!=(record['result'].get('feature_plan',{}).get('source') or P.SOURCE):
  raise ValueError('actual source-paid party replacement receipt required')
 return record['result']

def before_recall(e,a,p,party,*,baton_source=None):
 if party.get('feature_plan',{}).get('tag_in'):
  require(e,a,TAG)
  __import__('native_switch_transfer').select_tag_in(e,a,p,reason='actual paid Juggler party recall',_prepaid_request=party['request_id'])
 if baton_source=='move/배턴터치':
  return capture_transfer(e,p,source=baton_source,request_id=party.get('request_id'))

def capture_transfer(e,p,*,source,request_id,native_recall_id=None):
  import combat_stage_sources as CS,coat_effects as COATS,class_passive_combat as P,combat_precision_features as PRECISION,commander_orders as O
  CS.validate(p);COATS.validate_actor(p)
  payload={'source':source,'request_id':request_id,'pokemon_id':p.entity_id,'stages':dict(p.stages),
   'coats':[r['id'] for r in COATS.live(p)],'sustains':deepcopy(P._state(p)['sustains']) if P._state(p) else {},
   'pinpoint':p.custom_conditions.get(PRECISION.KEY,{}).get('instance'),
   'brace':[r['id'] for r in O.live(e,p,O.BRACE)],'at':e.elapsed_seconds,
   'locks':[{'owner_id':actor.entity_id,'completion_id':row['completion_id'],'field':field,'from':p.entity_id}
    for actor in W.actors(e) for row in actor.spec.get(KEY,{}).get('lock_on',[]) if row.get('consumed_by') is None
    for field in ('user_id','target_id') if row[field]==p.entity_id]}
  if native_recall_id is not None:payload['native_recall_id']=native_recall_id
  payload['integrity']=tag_seal(payload)
  return payload

def tag_seal(payload):
 import resolution_transaction as TX
 return TX.request_fingerprint({k:v for k,v in payload.items() if k not in ('integrity','recipient_id','consumed_at')})

def finish_native_transfer(e,old,new,snapshot,event):
 """The common switch owner already moved stages, Coats and selected Orders."""
 import native_order_transfer as TRANSFER
 if snapshot.get('integrity')!=tag_seal(snapshot) or snapshot.get('native_recall_id')!=event['recall_id'] or snapshot['pokemon_id']!=old.entity_id:
  raise ValueError('actual native pre-recall snapshot required')
 TRANSFER.require_switch_proof(e,event,snapshot['integrity'],kind='juggler')
 owner=W.actor_index(e).get(event['trainer_id'])
 if owner is None:raise ValueError('native switch Trainer required')
 if snapshot['source']==TAG and state(owner).get('pending_tag') is not snapshot:
  raise ValueError('Tag In view must alias the actual pending native snapshot')
 if old is not new:
  for captured in snapshot['locks']:
   actor=W.actor_index(e)[captured['owner_id']]
   for row in actor.spec.get(KEY,{}).get('lock_on',[]):
    field=captured['field']
    if row['completion_id']==captured['completion_id'] and row.get('consumed_by') is None and row[field]==old.entity_id:
     row.setdefault('transfers',[]).append({'source':snapshot['source'],'field':field,'from':old.entity_id,'to':new.entity_id,
      'at':e.elapsed_seconds,'snapshot':snapshot['integrity']});row[field]=new.entity_id
 snapshot.update(recipient_id=new.entity_id,consumed_at=e.elapsed_seconds)
 if snapshot['source']==TAG:
  state(owner).setdefault('tag_history',[]).append(state(owner).pop('pending_tag'))
 else:state(owner).setdefault('baton_history',[]).append(snapshot)

def receive_tag(e,a,p,*,pending=None,old=None,transfer_coats=True):
 tagged=pending is None
 pending=state(a).get('pending_tag') if tagged else pending
 if pending is None:return
 if 'native_recall_id' in pending:raise ValueError('native Tag In must finish at the actual send boundary')
 if pending.get('integrity')!=tag_seal(pending):raise ValueError('actual pre-recall Tag In snapshot changed')
 old=W.actor_index(e).get(pending['pokemon_id']) if old is None else old
 if old is None or old is p and not tagged or old is not p and old.on_field:raise ValueError('Tag In next-release requires its actual recalled source')
 import coat_effects as COATS,combat_stage_sources as CS,class_passive_combat as P,combat_precision_features as PRECISION,commander_orders as O
 if old is p:
  # Core Tag In says next release, not another Pokemon. A later legal release
  # of the same holder keeps live instance identities; it is not a self-transfer
  # and must not resurrect an ended Coat or sustained Stratagem.
  CS.assign_combat(p,pending['stages'])
  pending.update(recipient_id=p.entity_id,consumed_at=e.elapsed_seconds)
  state(a).setdefault('tag_history',[]).append(state(a).pop('pending_tag'))
  return
 if transfer_coats:COATS.transfer_tag(e,old,p,pending)
 live_sustains={} if P._state(old) is None else P._state(old)['sustains']
 transferable={uid:snapshot for uid,snapshot in pending['sustains'].items() if live_sustains.get(uid,{}).get('instance')==snapshot['instance']}
 binding=PRECISION.binding(e,old) if pending['pinpoint'] else None
 brace=[r['id'] for r in O.live(e,old,O.BRACE) if r['id'] in pending['brace']]
 if transferable or binding and binding['instance']==pending['pinpoint'] or brace:P._require_stratagem_slot(p)
 for uid,snapshot in transferable.items():
  live=P._state(old)['sustains'].get(uid)
  if live!=snapshot:raise ValueError('Tag In actual sustained Stratagem changed before release')
  P._active(e,old,uid)
  sid=live['instance'];grant=old.spec[G.KEY]['sources'].pop(sid)
  G.state(p)['sources'][sid]=grant
  live['target_id']=p.entity_id;P._state(p,create=True)['sustains'][uid]=P._state(old)['sustains'].pop(uid)
 if binding and binding['instance']==pending['pinpoint']:
  binding['target']=p;p.custom_conditions[PRECISION.KEY]=old.custom_conditions.pop(PRECISION.KEY)
 O.transfer_baton(e,old,p,brace,source=pending['source'])
 CS.assign_combat(p,pending['stages'])
 for captured in pending['locks']:
  actor=W.actor_index(e)[captured['owner_id']]
  for row in actor.spec.get(KEY,{}).get('lock_on',[]):
   field=captured['field']
   if row['completion_id']==captured['completion_id'] and row.get('consumed_by') is None and row[field]==old.entity_id:
    row.setdefault('transfers',[]).append({'source':pending['source'],'field':field,'from':old.entity_id,'to':p.entity_id,'at':e.elapsed_seconds,'snapshot':pending['integrity']});row[field]=p.entity_id
 pending.update(recipient_id=p.entity_id,consumed_at=e.elapsed_seconds)
 if tagged:state(a).setdefault('tag_history',[]).append(state(a).pop('pending_tag'))
 else:state(a).setdefault('baton_history',[]).append(pending)

def released(e,a,p,*,request_id,source_id=None):
 receive_tag(e,a,p)
 if acquired(a) and e.encounter_active:
  import combat_timing as TIME
  if not any(r.get('juggler_release') and r.get('round_end_deadline')==e.round_no for r in TIME.records(p)):
   import effect_contracts as CONTRACTS,initiative_derivation as INITIATIVE
   effect={'type':'initiative','delta':10,'until':'this round'}
   # This hook runs after the actual paid party/GM release, not an attack.
   # Use the native producer receipt API rather than inventing a hit predicate.
   CONTRACTS.require(e,a,p,[effect],CLASS)
   occurrence,receipt=CONTRACTS.issue_receipt(e,CLASS,a,p,effect,0)
   INITIATIVE.install_temporary(e,a,p,effect,CLASS,receipt,occurrence)
   CONTRACTS.finish(e,receipt,'completed',{'release_request_id':request_id,'pokemon_id':p.entity_id})
   record=TIME.records(p)[-1]
   record['juggler_release']={'trainer_id':a.entity_id,'request_id':request_id}
  schedule=getattr(e,'_initiative_schedule',None)
  if schedule:
   slot=next((key for key,row in schedule['slots'].items() if row['actor'] is p),None)
   if slot is not None:__import__('initiative_schedule').reorder_party(e,slot,request_id)
 event(e,'release',p,trainer=a,request_id=request_id,source_id=source_id)

def lock_definition(rules):
 contract(rules)
 if rules._selected_rule(LOCK)!=LOCK:raise ValueError('selected Core Lock-On source required')
 return {'raw':{'type':'custom_condition','name':'록온','on':'target','passable_by':'배턴터치'},
  'payload':{'kind':'lock_on','operation':'next_attack_never_misses','both_endpoints_passable':True}}

def prepare_lock(e,a,t,effect):
 W.require_actors(e,a,t);row=lock_definition(e.r)
 if {k:v for k,v in effect.items() if not k.startswith('_')}!=row['raw']:raise ValueError('reviewed Lock-On extraction changed')
 return row

def after_move(e,row):
 if row['phase']!='complete':return
 p=row['actor'];a=__import__('party_actions').owner(e,p)
 if a is not None and acquired(a,ROUND):state(a)['move_window']={'id':row['id'],'boundary':boundary(e)}
 for actor in W.actors(e):
  for lock in actor.spec.get(KEY,{}).get('lock_on',[]):
   if lock['user_id']==p.entity_id and lock.get('consumed_by') is None and row['id']!=lock['completion_id'] and row.get('juggler_accuracy_required',{}).get(lock['target_id'],False):lock['consumed_by']=row['id']
 if row['move_id']==LOCK:
  for t in row['targets']:
   result=__import__('move_completion').recipient_result(row,t)
   if result and result['hit'] and not result.get('cancelled'):
    state(p)['lock_on'].append({'source':LOCK,'completion_id':row['id'],'original_target_id':t.entity_id,'user_id':p.entity_id,'target_id':t.entity_id,'consumed_by':None,'transfers':[]})

def lock_on(e,a,t):
 return any(r['user_id']==a.entity_id and r['target_id']==t.entity_id and r.get('consumed_by') is None for actor in W.actors(e) for r in actor.spec.get(KEY,{}).get('lock_on',[]))

def first_location(e,p):
 import party_actions as P,initiative_interrupts as I
 a=P.owner(e,p)
 if a is None:raise ValueError('First Blood requires the released Pokemon owner')
 require(e,a,FIRST)
 proof=state(a).get('first_request',{});event_id=proof.get('event_id')
 rows=[r for r in state(a)['events'] if r['id']==event_id and r['kind']=='release']
 if len(rows)!=1 or proof.get('reaction_boundary')!=boundary(e):raise ValueError('First Blood requires its immediate actual release boundary')
 r=rows[0]
 if r['pokemon_id']!=p.entity_id or r['trainer_id']!=a.entity_id:raise ValueError('First Blood requires this actual containing-ball release')
 s=getattr(e,'_initiative_schedule',None)
 if not s or s['status']!='active':raise ValueError('First Blood requires the actual stable Pokemon turn slot')
 slot=next((k for k,v in s['slots'].items() if v['actor'] is p),None)
 if slot is None or s['open_slot']==slot:raise ValueError('released Pokemon needs an unopened or consumed actual turn slot')
 loans=I._state(e)['loans'].values();epoch=P.scope(e)[0]
 current_available=(s['slots'][slot]['turn']=='ready' and P.switch_lock(e,p)is None
  and sum(tuple(x['scope'])==P.scope(e) for x in a.spec.get('party_command_turns',[]))+I.command_debts(e,a)<P.command_limit(e,a))
 due=e.round_no if current_available else e.round_no+1
 if any(l['status']=='owed' and l['due_round']==due and (l['slot']==slot or l.get('trainer_id')==a.entity_id and l['actor'] is p) for l in loans):raise ValueError('First Blood actual Pokemon turn already borrowed')
 if sum(l.get('mode')=='switch_interrupt' and l['status']=='owed' and l['due_round']==due and l.get('trainer_id')==a.entity_id for l in loans)>=P.command_limit(e,a):raise ValueError('First Blood has no actual unconsumed Pokemon command turn')
 return {'slot':slot,'role':s['slots'][slot]['role'],'due_round':due,'trainer_id':a.entity_id,'encounter_epoch':epoch,'switch_request_id':r['request_id']}

def first_request(e,p,row,*,historical=False):
 a=__import__('party_actions').owner(e,p)
 if a is None:raise ValueError('actual First Blood owner required')
 proof=state(a).get('first_requests',{}).get(row['id'])
 if proof is None or proof['pokemon_id']!=p.entity_id or proof['move_id']!=row['move_id'] or row['source']!=FIRST:raise ValueError('source-authenticated First Blood selected Move required')
 if not historical:
  require(e,a,FIRST)
  if not p.on_field or p.fainted or p.captured:raise ValueError('actual released First Blood Pokemon required')
 return proof

def validate_first_loan(e,index,loan):
 import party_actions as P
 a=index.get(loan['trainer_id']);records={} if a is None else state(a).get('first_requests',{})
 proof=records.get(loan['request_id'])
 releases=[] if a is None else [r for r in state(a)['events'] if r['id']==proof.get('event_id') and r['kind']=='release'] if proof else []
 if (proof is None or len(releases)!=1 or proof['pokemon_id']!=loan['actor'].entity_id or proof['move_id']!=loan['move_id']
  or proof['release_request_id']!=loan['switch_request_id'] or releases[0]['request_id']!=loan['switch_request_id']
  or releases[0]['pokemon_id']!=loan['actor'].entity_id or releases[0]['boundary']['round']!=loan['borrow_round']):raise ValueError('First Blood lost its actual source release and selected native Move')

def first_blood(e,a,p,t,mid,*,event_id,request_id,**options):
 """One native Move Interrupt spends the current/next whole Pokemon turn."""
 import initiative_interrupts as I,frequency as F
 W.require_actors(e,a,p,t);require(e,a,FIRST);r=trigger(e,a,event_id,'release')
 if p.spec.get('trainer_id')!=a.entity_id or r['pokemon_id']!=p.entity_id:raise ValueError('First Blood requires the actual owned release')
 if mid not in p.moves and mid!='struggle':raise ValueError('First Blood requires an actually known Move')
 waiting=[]
 def apply(se,owner,pokemon,target):
  frequency=__import__('capture_specialist')._quota(se,owner,FIRST,'scene')
  parent=se._active_turn_actor
  if parent is None:raise ValueError('First Blood requires its actual suspended release turn')
  proof={'event_id':event_id,'pokemon_id':pokemon.entity_id,'move_id':mid,'target_id':target.entity_id,'release_request_id':r['request_id']}
  data=state(owner);data['first_request']=proof;data.setdefault('first_requests',{})[request_id]=proof
  pay(se,owner,FIRST,'free',0) if parent is owner else __import__('action_lifecycle').triggered_free_action(se,owner,FIRST)
  # The Free action belongs to the release trigger; keep that occurrence's signature.
  proof['reaction_boundary']=boundary(se)
  raw={'kind':'turn','actor_id':parent.entity_id,'serial':parent.custom_conditions.get('combat_turn_serial',0),'round':se.round_no}
  declaration={'id':request_id,'actor_id':pokemon.entity_id,'source':FIRST,'priority':0,'mode':'switch_interrupt','payment':'future_turn','budget':{'standard':1},'clock':'none','move_id':mid}
  window=I.queue(se,[declaration],trigger=raw)['window_id'];I.begin(se,window,request_id)
  F.consume_activation(owner,FIRST,frequency,engine=se)
  try:result=se.use_move(pokemon,target,mid,**options)
  except __import__('passive_events').PassiveEventPending as pending:
   if se._passive_pending!=pending.event_id:raise
   waiting.append(pending.event_id);return None
  I.finish(se);data.pop('first_request',None)
  return result
 result=G.transition(e,a,apply,participants=(p,t),include_rulings=True,include_grid=e.grid is not None)
 if waiting:raise __import__('passive_events').PassiveEventPending(waiting[0])
 return result

def validate_world(e,index):
 for a in index.values():
  data=a.spec.get(KEY)
  if data is None:continue
  for row in data.get('events',[]):
   if row['pokemon_id'] not in index or row['kind'] not in ('release','faint'):raise ValueError('actual Juggler native event required')
  pending=data.get('pending_tag')
  for snapshot in [*data.get('tag_history',[]),*data.get('baton_history',[])]+([pending] if pending else []):
   if snapshot.get('integrity')!=tag_seal(snapshot) or snapshot['pokemon_id'] not in index:raise ValueError('actual pre-recall Tag In snapshot changed')
   if 'native_recall_id' in snapshot:
    __import__('native_switch_transfer').validate_juggler_snapshot(e,a,snapshot)
   elif snapshot['source']==TAG:
    receipt=a.spec.get(__import__('party_actions').KEY,{}).get(snapshot['request_id'])
    if receipt is None or receipt['result'].get('tag_snapshot_integrity')!=snapshot['integrity']:raise ValueError('Tag In requires its actual paid recall snapshot')
  for r in data.get('lock_on',[]):
   row=getattr(e,'_move_completions',{}).get(r['completion_id'])
   if row is None or row['move_id']!=LOCK or row['phase']!='complete' or not {r['user_id'],r['target_id']}<=index.keys():raise ValueError('Lock-On requires its actual completed source and two world endpoints')
   endpoints={'user_id':row['actor'].entity_id,'target_id':r['original_target_id']}
   if endpoints['target_id'] not in [t.entity_id for t in row['targets']]:raise ValueError('Lock-On original recipient changed')
   for change in r['transfers']:
    histories=[s for owner in index.values() for s in owner.spec.get(KEY,{}).get('tag_history',[])+owner.spec.get(KEY,{}).get('baton_history',[]) if s['integrity']==change['snapshot']]
    if (endpoints.get(change['field'])!=change['from'] or len(histories)!=1 or histories[0].get('recipient_id')!=change['to']
     or histories[0]['source']!=change['source'] or not any(s['completion_id']==r['completion_id'] and s['field']==change['field'] and s['from']==change['from'] for s in histories[0]['locks'])):raise ValueError('Lock-On requires its actual captured endpoint transfer chain')
    endpoints[change['field']]=change['to']
   if any(r[field]!=value for field,value in endpoints.items()):raise ValueError('Lock-On endpoints differ from their actual transfer history')
 return True

def bounce_plan(e,a,target,choice,*,function='capture'):
 """An explicit observed first landing is distinct from the function target."""
 require(e,a,BOUNCE)
 if type(choice)is not dict or set(choice)!={'landing','direction','timing','reason'}:raise ValueError('Bounce Shot needs explicit first landing, direction, function timing and observation reason')
 W._text(choice['reason'],'actual Bounce Shot landing reason')
 landing=tuple(choice['landing']);direction=tuple(choice['direction'])
 if len(landing)!=2 or any(type(v)is not int for v in landing) or len(direction)!=2 or any(type(v)is not int or v not in (-1,0,1) for v in direction) or not any(direction):raise ValueError('actual grid landing and one three-metre bounce direction required')
 if choice['timing'] not in ('before','after'):raise ValueError('choose the ball function before or after the bounce')
 end=tuple(landing[i]+3*direction[i] for i in (0,1))
 import map_terrain as TERRAIN,capability_actions as CAP
 if e.grid is None or not e.grid.inside(landing) or not e.grid.inside(end):raise ValueError('actual Bounce Shot landing and endpoint must be on the map')
 terrain=getattr(e.grid,'terrain_observations',{}).get(TERRAIN.key(landing),{}).get('map_terrain')
 if not terrain:raise ValueError('actual first landing terrain must be observed before Bounce Shot')
 TERRAIN.validate(e.grid)
 from grid import cheb
 if cheb(a.pos,landing)>CAP.throwing_range(e,a,category='poke_ball'):raise ValueError('actual first ball landing exceeds throwing range')
 function_cell=landing if choice['timing']=='before' else end
 if function=='capture' and tuple(target.pos)!=function_cell:raise ValueError('capture target must occupy the actual before/after bounce function position')
 return {'source':BOUNCE,'edition':edition(a,BOUNCE),'landing':list(landing),'endpoint':list(end),'direction':list(direction),'timing':choice['timing'],'function':function,'reason':choice['reason'],'terrain':deepcopy(terrain)}

def bounce_physical(e,a,obj,plan,record):
 if record.get('bounce_done') and plan['edition']=='local_csv':raise ValueError('the same physical ball cannot bounce repeatedly on one CSV throw')
 if obj['id']!=record['physical_instance_id'] or tuple(W.location_of(obj).get('cell',()))!=tuple(plan['landing']):raise ValueError('Bounce Shot must move the same actual ball from its observed landing')
 W._set_object_location(obj,{'kind':'grid','cell':plan['endpoint']})
 record['bounce_done']=True;record['bounce']=deepcopy(plan)
 record.setdefault('function_order',[]).append('bounce')
 return obj

def capture_launch(e,a,target,record,obj,plan):
 if plan is None:return
 pay(e,a,BOUNCE,'free',0)
 record['bounce_plan']=deepcopy(plan);record['function_order']=['throw','landing']
 record['first_landing']={'kind':'grid','cell':tuple(plan['landing'])}
 W._set_object_location(obj,{'kind':'grid','cell':plan['landing']})
 if plan['timing']=='after':bounce_physical(e,a,obj,plan,record)

def capture_function(e,a,record,obj,*,hit):
 plan=record.get('bounce_plan')
 if plan is None:return
 record['function_order'].append('capture' if hit else 'capture_miss')
 if plan['timing']=='before' and hit:bounce_physical(e,a,obj,plan,record)

def bounce_missed(e,a,*,attempt_id):
 import missed_ball_body as B
 require(e,a,BOUNCE)
 record=a.spec.get('capture_attempts',{}).get(attempt_id)
 if record is None or record.get('hit') or record.get('landing',{}).get('status')!='observed' or 'bounce_plan' not in record:raise ValueError('actual missed-ball ground observation and original Bounce Shot required')
 if record.get('bounce_done') and edition(a,BOUNCE)=='local_csv':raise ValueError('same ball already bounced during this CSV throw')
 def apply(se,owner):
  row=owner.spec['capture_attempts'][attempt_id];plan=deepcopy(row['bounce_plan']);landing=row['landing']['cell']
  plan['landing']=list(landing);plan['endpoint']=[landing[i]+3*plan['direction'][i] for i in (0,1)]
  if se.grid is None or not se.grid.inside(tuple(plan['endpoint'])):raise ValueError('actual missed-ball bounce endpoint is outside the map')
  bounce_physical(se,owner,B.attempt_ball(se,owner,row),plan,row)
  row['landing']['cell']=list(plan['endpoint']);return deepcopy(row['bounce'])
 return G.transition(e,a,apply,include_grid=e.grid is not None)


def completion_reaction_origin(e,actor,source,row,receipt):
 if source!=ROUND:return False
 require(e,actor,ROUND)
 if row['actor'].spec.get('trainer_id')!=actor.entity_id:raise ValueError('actual owned Round Trip completion required')
 if receipt is not None:
  import party_actions as P
  if not any(saved is receipt for saved in actor.spec.get(P.KEY,{}).values()):raise ValueError('actual retained party receipt required')
  feature=receipt.get('intent',{}).get('feature',{})
  if feature.get('source')!=ROUND or feature.get('completion_id')!=row['id']:raise ValueError('retained Round Trip origin changed')
 elif actor.spec.get(KEY,{}).get('move_window')!={'id':row['id'],'boundary':boundary(e)}:
  raise ValueError('actual current Round Trip completion required')
 return True
