"""Core Telekinetic source adapters over acquisition, equipment and combat owners."""
from copy import deepcopy
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
import json
import common_checks as C, state_grants as G, world_entities as W
import combat_timing as TIME, skill_modifiers as SK

CLASS='class/염동력자';ALPHA='feat/pk-알파';OMEGA='feat/pk-오메가'
POWER='feat/정신의-힘';COMBAT='feat/pk-전투';BURST='feat/텔레키네틱-버스트';OVERLOAD='feat/초능력-과부하'
KINESIS='move/숟가락휘기';BARRIER='move/배리어';PSYCHIC='move/사이코키네시스';LIFT='move/텔레키네시스'
PSYSHOCK='move/사이코쇼크'
INTERFERENCE='ability/간섭-core';PLAYTEST='ability/간섭-playtest';LEVITATE='ability/부유'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
EXTRACT='data/verification/telekinetic-core-source-excerpts.txt'
EXTRACT_SHA='2c2dbce323a1c5ed21a3a41d1379490a64757695691f1ffefe08c46e240e37f2'
FEATURES={CLASS:(3136,3138),ALPHA:(3140,3144),OMEGA:(3146,3150),POWER:(3152,3156),COMBAT:(3158,3162),BURST:(3164,3168),OVERLOAD:(3170,3179)}
PARENTS={CLASS:(),ALPHA:(CLASS,),OMEGA:(ALPHA,),POWER:(CLASS,),COMBAT:(CLASS,),BURST:(COMBAT,),OVERLOAD:(OMEGA,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[3124,3124] if u==CLASS else list(s),'parents':list(PARENTS[u]),
 'clause_id':'C04-116' if u==COMBAT else 'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1]),
 'minimum_rank':{CLASS:3,COMBAT:4,OMEGA:5,BURST:5,OVERLOAD:6}.get(u,0),'stat_tags':['spa'],
 'choices':[INTERFERENCE,PLAYTEST,LEVITATE] if u==POWER else [],'tags':['Weapon'] if u==COMBAT else []} for u,s in FEATURES.items()}
CSV_VARIANTS={CLASS:495,ALPHA:496,COMBAT:499,BURST:500,OVERLOAD:501}
CSV_SHA256='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'

def csv_source(rules,u):
 from source_context import verified_source
 if u not in CSV_VARIANTS:raise ValueError('reviewed Telekinetic CSV difference required')
 n=CSV_VARIANTS[u];uid='C2CSV/input/db/feats.csv:R'+str(n)+':main'
 rules.ruleset.require({'id':uid,'source':{'file':'db/feats.csv','record_span':[n,n]}})
 source={'file':'input/db/feats.csv','sha256':CSV_SHA256}
 verified_source(rules,source,label='Telekinetic CSV')
 return dict(source,edition='local_csv',record=n,clause_id=uid)

def local_csv(a,u):
 row=acquired(a,u)
 if row is None or row['snapshot'].get('selection') is None or u==POWER:return False
 if row['snapshot']['selection']!={'edition':'local_csv'} or row['snapshot'].get('source')!=csv_source(a.r,u):raise ValueError('immutable actual Telekinetic CSV source required')
 return True

def prerequisite_parents(a,u):
 return () if u==COMBAT and local_csv(a,u) else PARENTS[u]

def overload_ap(a):return 1 if local_csv(a,OVERLOAD) else 2

def records(a,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(a, FEATURES, feature, active=active)]

def acquired(a,feature=CLASS):
 rows=records(a,feature,True)
 return rows[-1] if rows else None

def acquisition_snapshot(e,a,u,rank,selection):
 if rank is not None:raise ValueError('Telekinetic Features are not Ranked')
 if u==POWER:
  if selection not in (INTERFERENCE,PLAYTEST,LEVITATE):raise ValueError('choose exactly one sourced Interference or Levitate Ability')
  e.r._selected_rule(selection)
 elif selection is not None:
  if selection!={'edition':'local_csv'}:raise ValueError('exact Telekinetic CSV edition selection required')
  csv_source(e.r,u)
 elemental=__import__('elemental_connection').choices(e,a) if u==CLASS else ()
 iron=any(SK.key(x) in {SK.key(v) for v in ('edge/강철의-정신','강철의 정신','Iron Mind')} for x in a.spec.get('edges',[]))
 parents=() if u==COMBAT and selection is not None else PARENTS[u]
 result={'rank':SK.rank(e.r,a,'집중')[2],'parents':[r['request_id'] for r in records(a,active=True) if r['feature_id'] in parents],'psychic_connection':'에스퍼' in elemental,'iron_mind':iron,'selection':deepcopy(selection)}
 if u!=POWER and selection is not None:
  result['source']=csv_source(e.r,u)
  if u==COMBAT:result['telekinetic']=bool({SK.key(x) for x in G.effective_capabilities(a)}&{SK.key(x) for x in ('염력','Telekinetic','capability/염력')})
 return result

def qualification(a,u,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 fields={'rank','parents','psychic_connection','iron_mind','selection'}
 csv=type(snapshot)is dict and u!=POWER and snapshot.get('selection') is not None
 if csv:
  fields|={'source'}|({'telekinetic'} if u==COMBAT else set())
  if snapshot['selection']!={'edition':'local_csv'} or snapshot.get('source')!=csv_source(a.r,u):raise ValueError('immutable actual Telekinetic CSV source required')
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!=fields:raise ValueError('actual Telekinetic acquisition observations required')
 C.integer(snapshot['rank'],'Focus rank',1)
 if snapshot['rank'] not in {row['rank'] for row in SK._declared_ranks(a.r)[0].values()}:raise ValueError('declared ordinary Focus rank required')
 known={r['request_id']:r['feature_id'] for r in records(a) if r['feature_id'] in PARENTS[u]}
 if type(snapshot['parents'])is not list or not set(snapshot['parents'])<=set(known):raise ValueError('actual Telekinetic parent receipts required')
 parent=(snapshot['telekinetic'] is True and snapshot['parents']==[]) if csv and u==COMBAT else set(PARENTS[u])<={known[x] for x in snapshot['parents']}
 choice=snapshot['selection'] in (INTERFERENCE,PLAYTEST,LEVITATE) if u==POWER else csv or snapshot['selection'] is None
 return Q.require(u,'native','acquire',[Q.check('trainer','prerequisite',a.kind=='trainer','actual Trainer required'),Q.check('parent','prerequisite',parent,'actual Telekinetic parent required'),Q.check('rank','prerequisite',snapshot['rank']>=DEFINITIONS[u]['minimum_rank'],'printed Focus rank required'),Q.check('edges','prerequisite',u!=CLASS or snapshot['psychic_connection'] and snapshot['iron_mind'],'Psychic Elemental Connection and Iron Mind required'),Q.check('selection','selection',choice,'one immutable Power of the Mind selection required')])

def after_acquire(e,a,u,sid):
 # Existing static producers already own the base class and Alpha/Omega grants.
 if u not in (CLASS,OMEGA):G.stat(a,'spa',1,sid,operation_id='acquisition_stat_tag')
 if u in (CLASS,ALPHA,OMEGA):
  __import__('static_feature_state_grants').register_all(e,a);__import__('class_move_grants').register_all(e,a)
 if u==CLASS and local_csv(a,u):G.grant_moves(a,[KINESIS],sid,'feature',owner_id=a.entity_id,lifetime='while_owned',rule_id=u)
 if u==POWER:
  selected=acquired(a,u)['snapshot']['selection'];a.spec.setdefault('feature_choices',{})[u]=[selected]
  name={INTERFERENCE:'간섭 [Core p321]',PLAYTEST:'간섭 [Playtest]',LEVITATE:'부유'}[selected]
  G.grant(a,'abilities',name,sid,'feature',rule_id=u,owner_id=a.entity_id,lifetime='while_owned');G.ensure_ability(e,a,name)

def validate_acquisition(a,r,sid,active):
 if not active:return
 u=r['feature_id']
 if u==POWER and a.spec.get('feature_choices',{}).get(u)!=[r['snapshot']['selection']]:raise ValueError('Power of the Mind selection changed')
 if u not in (CLASS,OMEGA) and a.spec.get(G.KEY,{}).get('stat_sources',{}).get('spa',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Telekinetic SpA tag required')

def require(e,a,u):
 W.require_actors(e,a)
 if e.r._selected_rule(u)!=u or not acquired(a,u):raise ValueError('actual acquired Telekinetic Feature required: '+u)
 if a.fainted or not a.on_field or a.captured:raise ValueError('available Telekinetic actor required')

def pay(e,a,u,kind,ap=0):
 import turn as T, action_points as AP
 if AP.available(a)<ap:raise ValueError('available Telekinetic AP required')
 if not T.spend(e,a,kind,u):raise ValueError('Telekinetic requires '+kind+' action')
 if ap:AP.charge(a,ap)

def active_combat(a):
 return next((v for v in getattr(a,'_ap_bound_effects',{}).values() if v.get('state')=='active' and v.get('source_ref')==COMBAT),None)

def activate_combat(e,a,*,instance_id):
 require(e,a,COMBAT);__import__('telekinetic_load').require(e,a)
 if active_combat(a):raise ValueError('PK Combat is already bound')
 def apply(se,c):
  pay(se,c,COMBAT,'standard')
  return __import__('bound_ap').activate_modifier(se,c,instance_id,amount=1,modifier={'type':'damage_roll_mod','value':0},ending_method='none_specified',source_ref=COMBAT)
 return G.transition(e,a,apply)

def remote(e,a,obj):
 require(e,a,COMBAT)
 if not active_combat(a):raise ValueError('active bound PK Combat required')
 import telekinetic_load as LOAD,capability_actions as CARRY
 LOAD.require(e,a);LOAD.validate_world(e,W.actor_index(e));LOAD.range_check(e,a,obj);CARRY.load(a)
 if obj.get('telekinetic_holder_id')!=a.entity_id:raise ValueError('actual telekinetically held object required')
 if a.spec['_carried_load'].get('failure_pending'):raise ValueError('resolve current Focus carrying check first')
 return obj

def remote_weapon(e,a,weapon):
 uid=weapon.get('framework_instance') or weapon.get('instance_id')
 obj=getattr(e,'_physical_objects',{}).get(uid,{})
 if not weapon.get('telekinetic') and obj.get('telekinetic_holder_id')!=a.entity_id:return False
 remote(e,a,obj);return True

def equip_weapon(e,a,uid,*,slot='주요손'):
 import optional_weapon_framework as F,turn as T
 obj,row=F.object_profile(e,uid);remote(e,a,obj)
 return G.transition(e,a,lambda se,c:T.equip_weapon(se,c,{k:deepcopy(row[k]) for k in ('name','kind','grade','moves')}|{'framework_instance':uid,'instance_id':uid,'slot':slot,'telekinetic':True}),include_rulings=True)

def prepare_weapon(e,a,move):
 attack=move.get('_weapon_attack',{});entry=a.custom_conditions.get('equipped_weapons',{}).get(attack.get('key'))
 if not entry or not entry['weapon'].get('telekinetic'):return move
 remote_weapon(e,a,entry['weapon']);out=deepcopy(move)
 if out['class']!='물리':raise ValueError('PK Combat retains Physical weapon attacks')
 if a.spec.get('pk_combat_use_spa',False):out['_pk_combat_spa']=True
 else:out.pop('_pk_combat_spa',None)
 if '근접' in entry['weapon']['kind']:
  out['_weapon_attack']['range'].update(origin=8,raw='8, 대상 1',parsed=True);out['range']='8, 대상 1'
 return out

def weapon_attack(e,a,t,mid,key,*,use_spa=False,**options):
 if type(use_spa)is not bool:raise ValueError('explicit physical weapon damage-stat choice required')
 entry=a.custom_conditions.get('equipped_weapons',{}).get(key)
 if entry is None or not entry['weapon'].get('telekinetic'):raise ValueError('actual equipped remote weapon required')
 remote_weapon(e,a,entry['weapon'])
 if entry['weapon']['kind'] in ('소형 근접무기','대형 근접무기') and (W.distance_known(a,t) is None or W.distance_known(a,t)>8):raise ValueError('remote melee target outside eight metres')
 def apply(se,c,target):
  c.spec['pk_combat_use_spa']=use_spa
  try:return se.use_move(c,target,mid,weapon_id=key,**options)
  finally:c.spec.pop('pk_combat_use_spa',None)
 return G.transition(e,a,apply,participants=(t,),include_grid=e.grid is not None)

def item_target(e,a,uid,t):
 obj=getattr(e,'_physical_objects',{}).get(uid,{})
 remote(e,a,obj);W.require_actors(e,t)
 distance=W.distance_known(a,t)
 if distance is None or distance>8:raise ValueError('remote item target must be within eight metres')
 entries=a.custom_conditions.get('equipped_weapons',{}).values()
 used=len({slot for x in entries for slot in x['slots']}|{s for x in getattr(a,'_item_reg',{}).values() for s in x.get('slots',[]) if s in ('주요손','반대손')})
 if used>=2:raise ValueError('remote item respects the normal held-item count')
 return obj

def use_item(e,a,uid,t=None,**options):
 t=t or a;obj=item_target(e,a,uid,t)
 if obj.get('kind')!='item_instance':raise ValueError('actual registered remote item required')
 if 'held_selection' in options:raise ValueError('one exact remote item selection required')
 return e.use_item(a,obj['item_rule_id'],t,held_selection=uid,**options)

def before_revoke(e,a,sources):
 if not any(a.spec.get(G.KEY,{}).get('sources',{}).get(s,{}).get('rule_id') in (CLASS,COMBAT) for s in sources):return
 end_combat(e,a,source_loss=True)

def end_combat(e,a,*,instance_id=None,event_id=None,source_loss=False):
 r=active_combat(a)
 if r is None:
  if source_loss:return
  raise ValueError('active PK Combat binding required')
 uid=next(k for k,v in a._ap_bound_effects.items() if v is r)
 if instance_id not in (None,uid):raise ValueError('exact PK Combat binding required')
 if not source_loss:
  result=__import__('bound_ap').release(e,a,uid,event_id=event_id)
  if result.status!='released':raise ValueError(result.reason)
 else:
  a.modifiers[:]=[m for m in a.modifiers if m is not r['modifier']];a.ap_account.release_binding(uid,expected_amount=1)
  r.update(state='ended',end_event={'id':'source-loss:'+uid,'kind':'source_loss'});r.pop('owner');r.pop('modifier')
 for key,entry in list(a.custom_conditions.get('equipped_weapons',{}).items()):
  if entry['weapon'].get('telekinetic'):__import__('turn').unequip_weapon(e,a,key)
 return uid

def burst(e,a,t,kind,**options):
 require(e,a,BURST)
 def apply(se,c,target):
  pay(se,c,BURST,'swift',2 if local_csv(c,BURST) else 1)
  return __import__('telekinetic_combat')._native(se,c,target,kind,action_cost='included',**dict(defender_skill=options.pop('defender_skill'),fixed_accuracy=options.pop('fixed_accuracy',None),challenger_options=options.pop('challenger_options',None),defender_options=options.pop('defender_options',None),item_name=options.pop('item_name',None),prevent_with_ap=options.pop('prevent_with_ap',None),follow_steps=options.pop('follow_steps',0)))
 if kind not in ('trip','push','disarm'):raise ValueError('one printed Telekinetic Burst maneuver required')
 return G.transition(e,a,apply,participants=(t,))

def evasion_policy(e,decision=None,*,adjudication=False):
 path='data/telekinesis-evasion-policy.json' if decision is not None or adjudication else 'data/telekinesis-core-policy.json'
 document=json.loads((Path(e.r.root)/path).read_text(encoding='utf8'))
 return e.r.resolve_source_policy(document,decisions={} if decision is None else {'evasion_owner':decision})

def cast(e,a,t,mid,*,segments=None,overload=False,evasion_owner=None,push_direction=None,aim=None):
 if mid not in (BARRIER,KINESIS,PSYCHIC,LIFT,PSYSHOCK):raise ValueError('one exact Telekinetic Move required')
 if type(overload)is not bool:raise ValueError('explicit Overload choice required')
 if mid==PSYSHOCK and (not overload or not local_csv(a,OVERLOAD)):raise ValueError('Psyshock Overload requires its actual CSV acquisition')
 if mid==PSYSHOCK and any(value is not None for value in (segments,evasion_owner,push_direction)):raise ValueError('Psyshock Overload does not use other Telekinetic Move choices')
 if mid!=PSYSHOCK and aim is not None:raise ValueError('Telekinetic aim belongs to the CSV Psyshock area')
 choice={'segments':segments,'overload':overload,'evasion_owner':evasion_owner,'push_direction':push_direction}
 waiting=[]
 def apply(se,c,target):
  if 'telekinetic_move_choice' in c.spec:raise ValueError('one actual Telekinetic Move at a time')
  c.spec['telekinetic_move_choice']=deepcopy(choice)
  try:
   if mid!=PSYSHOCK:return se.use_move(c,target,mid)
   return se.use_move_on(c,target,mid,se.everyone,aim=aim)
  except Exception as error:
   if G.record_native_pending(se,error,waiting):return None
   raise
  finally:c.spec.pop('telekinetic_move_choice',None)
 result=G.transition(e,a,apply,participants=(t,),include_grid=e.grid is not None,include_rulings=True)
 if waiting:
  exception,event_id=waiting[0];raise exception(event_id)
 return result

def project_move(e,a,move):
 if move['id']!=PSYSHOCK or not a.spec.get('telekinetic_move_choice',{}).get('overload'):return move
 require(e,a,OVERLOAD)
 if not local_csv(a,OVERLOAD):raise ValueError('Psyshock Overload requires its actual CSV acquisition')
 out=deepcopy(move);out['range']='4, 폭발 2'
 out['_class_move_range']={'raw':out['range'],'origin':4,'shape':'blast','size':2,'parsed':True}
 return out

def begin_move(e,a,target,move,completion_id):
 choice=a.spec.get('telekinetic_move_choice')
 if choice is None or move['id'] not in (BARRIER,KINESIS,PSYCHIC,LIFT,PSYSHOCK):return
 import move_activation as ACTIVATION
 ACTIVATION._require_started_event_use(e,a,target,move['id'],scope_error='Telekinetic choice needs its actual native Move')
 row=e._move_completions[completion_id]
 if row['actor'] is not a or row['move_id']!=move['id'] or target not in row['targets'] or target.entity_id not in row['started'] or row['phase']!='targets':
  raise ValueError('actual started Telekinetic completion recipient required')
 if 'telekinetic_overload' in row:
  value=_overload_binding(e,row,current=True)
  if value['choice']!=choice:raise ValueError('Telekinetic continuation choice changed')
  return
 if type(choice)is not dict or set(choice)!={'segments','overload','evasion_owner','push_direction'} or type(choice['overload'])is not bool:
  raise ValueError('exact native Telekinetic choice required')
 acquisition=None;payment=None
 if choice['overload']:
  require(e,a,OVERLOAD);acquisition=acquired(a,OVERLOAD)['request_id']
 if move['id']==PSYSHOCK:
  if not choice['overload'] or not local_csv(a,OVERLOAD):raise ValueError('actual CSV Psyshock Overload acquisition required')
  if any(choice[key] is not None for key in ('segments','evasion_owner','push_direction')):raise ValueError('exact Psyshock Overload choice required')
  pay(e,a,OVERLOAD,'swift',overload_ap(a))
  payment={'action':'swift','ap':1,'action_index':len(a._action_history)-1}
 row['telekinetic_overload']={'move_id':move['id'],'move_source':deepcopy(row['move'].get('_source')),
  'acquisition':acquisition,'choice':deepcopy(choice),'payment':payment}
 _overload_binding(e,row,current=True)

def _overload_binding(e,row,*,current=False):
 """Validate native cast selection; Book costs remain in their existing owner."""
 value=row.get('telekinetic_overload')
 if value is None:return None
 a=row['actor'];mid=row['move_id']
 if (type(value)is not dict or set(value)!={'move_id','move_source','acquisition','choice','payment'} or
     mid not in (BARRIER,KINESIS,PSYCHIC,LIFT,PSYSHOCK) or value['move_id']!=mid or row['move']['id']!=mid or
     type(value['move_source'])is not dict or value['move_source']!=row['move'].get('_source') or
     value['move_source']!=e.r.move(mid).get('_source') or type(value['choice'])is not dict or
     set(value['choice'])!={'segments','overload','evasion_owner','push_direction'} or type(value['choice']['overload'])is not bool):
  raise ValueError('Telekinetic native source choice changed')
 choice=value['choice'];record=None
 if choice['overload']:
  matches=[item for item in records(a,OVERLOAD) if item['request_id']==value['acquisition']]
  if len(matches)!=1:raise ValueError('Telekinetic choice lost its actual Overload acquisition')
  record=matches[0]
 elif value['acquisition'] is not None:raise ValueError('ordinary Telekinetic choice cannot invent Overload acquisition')
 waiting=getattr(e,'_passive_events',{}).get(getattr(e,'_passive_pending',None))
 active=current or row['phase'] not in ('complete','interrupted') or waiting is not None and waiting.get('completion_id')==row['id']
 if active and row['turn_serial']!=a.custom_conditions.get('combat_turn_serial',0):
  raise ValueError('Telekinetic pending choice left its actual turn')
 if mid==PSYSHOCK:
  if (record is None or record['snapshot'].get('selection')!={'edition':'local_csv'} or
      record['snapshot'].get('source')!=csv_source(e.r,OVERLOAD) or
      any(choice[key] is not None for key in ('segments','evasion_owner','push_direction')) or
      row['move'].get('_class_move_range')!={'raw':'4, 폭발 2','origin':4,'shape':'blast','size':2,'parsed':True}):
   raise ValueError('Psyshock Overload acquisition or range changed')
  payment=value['payment']
  if type(payment)is not dict or set(payment)!={'action','ap','action_index'} or payment['action']!='swift' or type(payment['ap'])is not int or payment['ap']!=1:
   raise ValueError('Psyshock Overload native payment changed')
  index=C.integer(payment['action_index'],'Psyshock native Swift history index',0)
  if active and (index>=len(a._action_history) or a._action_history[index]!='swift'):
   raise ValueError('Psyshock Overload lost its native Swift payment')
 elif value['payment'] is not None:raise ValueError('Book Telekinetic cost belongs to its native effect owner')
 if current and choice['overload']:
  if not (a.fainted or a.dead):require(e,a,OVERLOAD)
  current_record=acquired(a,OVERLOAD)
  if e.r._selected_rule(OVERLOAD)!=OVERLOAD or current_record is None or current_record['request_id']!=value['acquisition']:
   raise ValueError('Telekinetic current Overload acquisition changed')
 return value

def continuation_choice(e,event):
 row=getattr(e,'_move_completions',{}).get(event.get('completion_id'))
 return None if row is None else _overload_binding(e,row)

@contextmanager
def restored_scope(e,event):
 row=getattr(e,'_move_completions',{}).get(event.get('completion_id'))
 value=None if row is None else _overload_binding(e,row)
 if value is None:
  yield
  return
 if row['phase'] in ('complete','interrupted') and not event.get('continuation') and not row.get('activation_continuation'):
  yield
  return
 _overload_binding(e,row,current=True)
 a=row['actor'];previous=a.spec.get('telekinetic_move_choice')
 if previous is not None and previous!=value['choice']:raise ValueError('Telekinetic continuation source choice differs')
 a.spec['telekinetic_move_choice']=deepcopy(value['choice'])
 try:yield
 finally:
  if previous is None:a.spec.pop('telekinetic_move_choice',None)
  else:a.spec['telekinetic_move_choice']=previous

def pending(e,a,mid):
 if mid not in (BARRIER,LIFT,PSYCHIC):return None
 choice=a.spec.get('telekinetic_move_choice')
 if mid==LIFT and choice is None:return None
 if choice is None:return C.PendingDecision('Telekinetic Move requires explicit placement, Psychic push direction or scoped Evasion adjudication',basis={'source':mid,'policy':evasion_policy(e) if mid==LIFT else 'push_direction' if mid==PSYCHIC else 'segments'})
 if mid==LIFT:
  p=evasion_policy(e,choice['evasion_owner'])
  if p['status']!='PolicyValuesReady':return C.PendingDecision('Telekinesis optional GM override requires explicit source_policy.adjudication',basis=p)
 return None

def mechanics(r,mid,mm):
 if mid not in (BARRIER,LIFT,PSYCHIC):return mm
 __import__('priority_actions')._move(r,mid)
 if mid==BARRIER:return {'effects_exec':[]}
 if mid==LIFT:return {'effects_exec':[deepcopy(x) for x in mm.get('effects_exec',[]) if x.get('type')=='grant_capability']}
 result=deepcopy(mm)
 result['effects_exec']=[x for x in result.get('effects_exec',[]) if x.get('type')!='push']
 return result

def harm_semantics(r,mid):
 """Reviewed active effects that this owner executes outside effects_exec."""
 if mid not in (BARRIER,LIFT):return None
 __import__('priority_actions')._move(r,mid)
 # Lift impairs the target's movement even under the literal caster Evasion
 # policy. Barrier creates protective walls, not an effect harming its target.
 return mid==LIFT

def preflight_move(e,a,t,move):
 mid=move['id'];choice=a.spec.get('telekinetic_move_choice',{})
 if mid==KINESIS and __import__('combat_move_reactions').current(e,a,mid) is None:raise ValueError('Kinesis requires the actual about-to-hit attack Interrupt')
 if mid==BARRIER:segment_plan(e,a,choice.get('segments'),choice.get('overload',False))
 if mid==PSYCHIC:
  d=choice.get('push_direction')
  if not isinstance(d,(tuple,list)) or len(d)!=2 or any(type(x)is not int or x not in (-1,0,1) for x in d) or tuple(d)==(0,0):raise ValueError('Psychic requires its explicit one-metre push direction')
 if choice.get('overload'):
  require(e,a,OVERLOAD)
  if mid==KINESIS:raise ValueError('choose Kinesis Overload on its actual armed reaction; Swift is paid after the Interrupt returns')
  if __import__('initiative_interrupts').frame(e) is not None or e._active_turn_actor is not a:raise ValueError('Psionic Overload Swift requires its own ordinary turn')
  if mid not in (KINESIS,BARRIER,PSYCHIC,LIFT) and not(mid==PSYSHOCK and local_csv(a,OVERLOAD)):raise ValueError('Overload requires the named Psychic or another Telekinetic Move')

def segment_plan(e,a,segments,overload):
 from grid import cheb
 if e.grid is None or not isinstance(segments,(list,tuple)) or not 1<=len(segments)<= (6 if overload else 4):raise ValueError('one to four Barrier segments, or six with Overload, required')
 edges=[];endpoints=[]
 for raw in segments:
  if not isinstance(raw,(list,tuple)) or len(raw)!=2:raise ValueError('Barrier uses actual cell-edge walls')
  x,y=(tuple(__import__('movement_actions')._point(p)) for p in raw)
  if abs(x[0]-y[0])+abs(x[1]-y[1])!=1 or not e.grid.inside(x) or not e.grid.inside(y):raise ValueError('Barrier segment must separate adjacent mapped cells')
  edge=tuple(sorted((x,y)))
  if edge in edges or edge in e.grid.walls:raise ValueError('Barrier cannot replace an existing wall')
  edges.append(edge)
  axis=0 if x[0]!=y[0] else 1;other=1-axis
  center=[x[i]+y[i] for i in range(2)]
  ends=[]
  for offset in (-1,1):
   point=center.copy();point[other]+=offset;ends.append(tuple(point))
  endpoints.append(set(ends))
  if overload and min(cheb(a.pos,p) for p in edge)>6:raise ValueError('Overloaded Barrier outside six metres')
 if not overload:
  if not any(a.pos in edge for edge in edges):raise ValueError('one Barrier segment must touch its user')
  seen={0}
  while True:
   add={j for j in range(len(edges)) if any(endpoints[j]&endpoints[i] for i in seen)}-seen
   if not add:break
   seen|=add
  if len(seen)!=len(edges):raise ValueError('normal Barrier segments must form one continuous wall')
 return edges

def after_hit(e,a,t,move,completion):
 mid=move['id'];choice=a.spec.get('telekinetic_move_choice',{});over=choice.get('overload',False)
 if mid not in (KINESIS,BARRIER,PSYCHIC,LIFT):return
 if over:pay(e,a,OVERLOAD,'swift',overload_ap(a))
 if mid==BARRIER:
  edges=segment_plan(e,a,choice.get('segments'),over)
  ids=[]
  for i,edge in enumerate(edges):
   uid=completion+':barrier:'+str(i+1);W.register_object(e,uid,location=dict(W.location_of(a),cell=edge[0]),reason='Core Barrier native Move segment',owner_id=a.entity_id,source=BARRIER)
   obj=e._physical_objects[uid];obj['telekinetic_barrier']={'completion':completion,'creator_id':a.entity_id,'edge':edge,'type':'에스퍼','height_m':2,'width_m':1,'thickness_cm':2,'overload':over}
   __import__('physical_object_attacks').configure(e,a,uid,max_hp=20,reduction=15,minimum_damage=0,source=BARRIER,reason='Core p418 Barrier')
   e.grid.walls.add(edge);ids.append(uid)
  TIME.install(e,a,{'source':BARRIER,'barrier_segments':ids,'encounter_end':True})
 elif mid==LIFT:
  policy=evasion_policy(e,choice.get('evasion_owner'))
  if policy['status']!='PolicyValuesReady':raise ValueError('explicit Telekinesis Evasion owner adjudication required')
  sid='lifted:'+completion+':'+t.entity_id
  G.grant(t,'abilities','부유',sid,'move',rule_id=LIFT,owner_id=a.entity_id,lifetime='effect');G.ensure_ability(e,t,'부유')
  row={'source':LIFT,'lifted':{'id':sid,'caster_id':a.entity_id,'completion':completion,'overload':over,'evasion_policy':policy,'ticks':[]},'statuses':['둔화'],'grant_source':sid,'encounter_end':True}
  owner=t if policy['values']['evasion_owner']=='lifted_target' else a
  if owner is t:row['evasion_zero']=True
  else:TIME.install(e,a,{'source':LIFT,'lifted_evasion':sid,'evasion_zero':True,'encounter_end':True})
  TIME.install(e,t,row)
 elif mid==PSYCHIC:
  __import__('forced_movement').displace(e,a,t,direction=choice['push_direction'],distance=1,source=PSYCHIC)
  if over:TIME.install(e,t,{'source':OVERLOAD,'telekinetic_psychic':completion,'statuses':['취약'],'count_deadline':(e.round_no+1,TIME.current(e))})

def kinesis_overload(e,a,event):
 import combat_move_reactions as REACTIONS,initiative_interrupts as I
 require(e,a,OVERLOAD);REACTIONS.validate_event(e,a,event)
 if event['source']!=KINESIS or event['status']!='complete' or event.get('overload_spent') or not event.get('overload') or event['turn_owner_id']!=a.entity_id or e._active_turn_actor is not a or I.frame(e) is not None or e._ordinary_turn_rounds.get(a)!=e.round_no:raise ValueError('Kinesis Overload requires its completed actual reaction during its own ordinary turn')
 pay(e,a,OVERLOAD,'swift',overload_ap(a))
 e.apply_status(W.actor_index(e)[event['attacker_id']],'혼란',source=OVERLOAD,applied_by=a)
 event['overload_spent']=True;REACTIONS._seal(event)

def lifted(a):return [r for r in TIME.records(a) if 'lifted' in r]

def movement(e,a,result):
 if lifted(a):return dict(result,**{m:4 if m=='levitate' else 0 for m in __import__('movement_actions').MODES})
 import ability_transitions as ABILITIES
 if a.kind=='trainer' and not a.abilities_suppressed and any(ABILITIES.ability_id(e.r,value)==LEVITATE for value in a.abilities):
  result=dict(result);result['levitate']=result.get('levitate',0)+(2 if result.get('levitate',0)>0 else 4)
 return result

def escape(e,a):
 W.require_actors(e,a)
 if not lifted(a):raise ValueError('actual Lifted target required')
 def apply(se,c):
  pay(se,c,LIFT,'shift');face=se.d20()
  if face>=16:
   for r in list(lifted(c)):TIME.expire(se,c,r,ending='expired',event={'kind':'lifted_escape','natural':face})
  return {'natural':face,'escaped':face>=16}
 return G.transition(e,a,apply)

def ending(e,a,row):
 if 'lifted' in row:
  sid=row['lifted']['id']
  for actor in W.actor_index(e).values():
   for other in list(TIME.records(actor)):
    if other.get('lifted_evasion')==sid:TIME.expire(e,actor,other)
 if 'barrier_segments' in row:
  for uid in row['barrier_segments']:
   obj=e._physical_objects[uid];obj['telekinetic_barrier']['ended']=True;sync_barrier(e,obj)

def end_encounter(e):
 for actor in W.actor_index(e).values():
  for row in list(TIME.records(actor)):
   if row.get('source') in (BARRIER,LIFT) and row.get('encounter_end') and row in TIME.records(actor):TIME.expire(e,actor,row)

def end_turn(e,a):
 for row in lifted(a):
  state=row['lifted'];token=[e.round_no,a.custom_conditions.get('combat_turn_serial')]
  if state['overload'] and token not in state['ticks']:
   state['ticks'].append(token);e.lose_tick_hp(a,1,source=OVERLOAD)

def sync_barrier(e,obj):
 row=obj.get('telekinetic_barrier')
 if row and (row.get('ended') or obj.get('destroyed')) and e.grid is not None:e.grid.walls.discard(tuple(tuple(x) for x in row['edge']))

def barrier_multiplier(e,obj,move):
 if not obj.get('telekinetic_barrier'):return 1
 import type_state as TYPES
 value=TYPES.matchup(e.r,move['type'],'에스퍼')
 if value==0:return 0
 return e.r.mech('combat/type-effectiveness')['multiplier_by_net_steps'][str(1 if value>1 else -1 if value<1 else 0)]

def ability_registration(rules,name):
 if name not in (INTERFERENCE,PLAYTEST,'간섭 [Core p321]','간섭 [Playtest]'):return None
 uid=INTERFERENCE if name in (INTERFERENCE,'간섭 [Core p321]') else PLAYTEST
 if rules._selected_rule(uid)!=uid:raise ValueError('exact Interference source required')
 return {'name':'간섭 [Core p321]' if uid==INTERFERENCE else '간섭 [Playtest]','source_id':uid,'equivalent_source_ids':[uid]}

def validate_core_ability(rules,row):
 expected={'type':'core_interference','frequency':{'kind':'at_will'},'action':'standard','range':3,'accuracy_modifier':-2,'duration':'end_of_user_next_turn'}
 if row.get('id')!=INTERFERENCE or row.get('name')!='간섭 [Core p321]' or row.get('native_contract')!=expected:raise ValueError('exact Core Interference contract required')
 source=row['official_source']
 if source!={'document':'Pokemon Tabletop United Core 1.05','pages':[321],'extract':EXTRACT,'sha256':EXTRACT_SHA}:raise ValueError('Core Interference official source identity changed')
 from hashlib import sha256
 if sha256((Path(rules.root)/source['extract']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Core Interference source changed')

def activate_interference(e,a,ability,target=None):
 reg=ability_registration(e.r,ability)
 if reg is None or not __import__('ability_transitions').active(a,reg['source_id']):raise ValueError('actual unsuppressed Interference Ability required')
 def apply(se,c):
  source=reg['source_id'];play=source==PLAYTEST;quota={'kind':'scene','uses':1}
  if play and not __import__('frequency').activation_allowed(c,source,quota,engine=se):raise ValueError('Interference Scene frequency exhausted')
  count=TIME.current(se) if play else None
  pay(se,c,source,'swift' if play else 'standard')
  if play:__import__('frequency').consume_activation(c,source,quota,engine=se)
  targets=[]
  for foe in W.actor_index(se).values():
   if not foe.on_field or foe.side==c.side or foe.captured:continue
   if W.distance_known(c,foe) is None or W.distance_known(c,foe)>3:continue
   row={'source':source,'accuracy_modifier':-2,'telekinetic_interference':{'caster_id':c.entity_id,'version':'official_feb2016' if play else 'core_1.05'},'encounter_end':True}
   if play:row['count_deadline']=(se.round_no+1,count)
   else:row.update(turn_owner=c,turn_deadline=c.custom_conditions['combat_turn_serial']+1)
   TIME.install(se,foe,row);targets.append(foe.entity_id)
  return {'source':source,'targets':targets}
 return G.transition(e,a,apply)

def native_move(fn):
 @wraps(fn)
 def run(e,a,t,mid,*args,**kwargs):
  pending_result=pending(e,a,mid)
  if pending_result is not None:return pending_result
  interested=mid in (BARRIER,LIFT,PSYCHIC,KINESIS) or any(KINESIS in x.spec.get(__import__('combat_move_reactions').CHOICES,{}) for x in e.everyone) or any(v['weapon'].get('telekinetic') for v in a.custom_conditions.get('equipped_weapons',{}).values())
  if not interested or getattr(e,'_reactive_move_transaction',False):return fn(e,a,t,mid,*args,**kwargs)
  def apply(se,c,target):
   payload=G._stage_transition_payload(e,se,{'args':args,'kwargs':kwargs})
   return fn(se,c,target,mid,*payload['args'],**payload['kwargs'])
  return __import__('reactive_ability_events').atomic_move(e,a,t,apply)
 return run

def validate_world(e,index):
 for row in getattr(e,'_move_completions',{}).values():_overload_binding(e,row)
 for a in index.values():
  for row in TIME.records(a):
   if 'lifted' in row:
    state=row['lifted'];completion=getattr(e,'_move_completions',{}).get(state['completion'])
    if not completion or completion['move_id']!=LIFT or completion['actor'].entity_id!=state['caster_id']:raise ValueError('Lifted lost its actual native Move')
    p=state['evasion_policy'];selected=evasion_policy(e,{'value':p['input_values']['evasion_owner'],'reason':p['decision_evidence'][0]['reason'],'scope':p['decision_scope']}) if p['input_values'] else evasion_policy(e)
    if selected!=p or row.get('statuses')!=['둔화'] or row.get('grant_source')!=state['id']:raise ValueError('Lifted source policy or owned state changed')
  for uid,obj in getattr(e,'_physical_objects',{}).items():
   b=obj.get('telekinetic_barrier')
   if not b:continue
   completion=getattr(e,'_move_completions',{}).get(b['completion']);edge=tuple(tuple(x) for x in b['edge'])
   if not completion or completion['move_id']!=BARRIER or completion['actor'].entity_id!=b['creator_id'] or (b['height_m'],b['width_m'],b['thickness_cm'],b['type'])!=(2,1,2,'에스퍼'):raise ValueError('Barrier actual native source or dimensions changed')
   if e.grid is not None and (edge in e.grid.walls)==bool(b.get('ended') or obj.get('destroyed')):raise ValueError('Barrier live physical wall and destruction disagree')
 return True
