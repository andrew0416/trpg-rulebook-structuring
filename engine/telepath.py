"""Core Telepath adapters over acquired sources, communication and native attacks."""
from copy import deepcopy
from functools import wraps
from pathlib import Path
from hashlib import sha256
import json
import common_checks as C, state_grants as G, world_entities as W
import effect_instances as E, combat_timing as TIME, skill_modifiers as SK

CLASS='class/텔레파시능력자';HONED='feat/연마된-정신';AWARE='feat/텔레파시-인식'
DETECT='feat/사고-탐지';WARNING='feat/텔레파시-경고';ASSAULT='feat/정신공격';SUGGEST='feat/암시'
READER='move/마음의눈';PSYSHOCK='move/사이코쇼크'
GENTLE='ability/다정한분위기';CORE='ability/텔레파시-core';FEB='ability/텔레파시-feb2016'
EXTRACT='data/verification/telepath-core-source-excerpts.txt'
EXTRACT_SHA='8be4a75b58e9a91cecc6c4ee8acfa23b6563dc745b214744e2a9d2aaf450625a'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
FEATURES={CLASS:(3194,3196),HONED:(3198,3202),AWARE:(3204,3208),DETECT:(3210,3214),WARNING:(3216,3221),ASSAULT:(3223,3227),SUGGEST:(3229,3234)}
PARENTS={CLASS:(),HONED:(CLASS,),AWARE:(CLASS,),DETECT:(AWARE,),WARNING:(AWARE,),ASSAULT:(CLASS,),SUGGEST:(HONED,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[3182,3182] if u==CLASS else list(s),'parents':list(PARENTS[u]),'minimum_rank':3 if u==CLASS else 5 if u in (WARNING,ASSAULT) else 6 if u==SUGGEST else 0,'stat_tags':['spd'],'choices':[GENTLE,CORE,FEB] if u==AWARE else [],'clause_id':{DETECT:'C04-117',SUGGEST:'C04-118'}.get(u,'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1]))} for u,s in FEATURES.items()}
LABELS={GENTLE:'다정한분위기',CORE:'텔레파시 [Core p332]',FEB:'텔레파시 [Official Feb2016]'}
CONTRACTS={CORE:{'type':'telepathy_interrupt','action':'shift','damaging_only':False},FEB:{'type':'telepathy_disengage','action':'free','damaging_only':True,'evasion':1}}

def records(a,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(a, FEATURES, feature, active=active)]

def acquired(a,feature=CLASS):
 rows=records(a,feature,True)
 return rows[-1] if rows else None

def acquisition_snapshot(e,a,u,rank,selection):
 if rank is not None:raise ValueError('Telepath Features are not Ranked')
 if u==AWARE:
  if selection not in LABELS:raise ValueError('choose exactly one sourced Gentle Vibe or Telepathy Ability')
  e.r._selected_rule(selection)
 elif selection is not None:raise ValueError('this Telepath Feature has no selection')
 elemental=__import__('elemental_connection').choices(e,a) if u==CLASS else ()
 iron=__import__('perception_communicate')._owns(a,'edges',('edge/강철의-정신','강철의 정신','Iron Mind'))
 return {'intuition':SK.rank(e.r,a,'직감')[2],'focus':SK.rank(e.r,a,'집중')[2],'parents':[r['request_id'] for r in records(a,active=True) if r['feature_id'] in PARENTS[u]],'psychic_connection':'에스퍼' in elemental,'iron_mind':iron,'selection':selection}

def qualification(a,u,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'intuition','focus','parents','psychic_connection','iron_mind','selection'}:raise ValueError('actual Telepath acquisition observations required')
 for k in ('intuition','focus'):SK.validate_rank_value(a.r,snapshot[k],label='Telepath skill rank')
 known={r['request_id']:r['feature_id'] for r in records(a) if r['feature_id'] in PARENTS[u]}
 if type(snapshot['parents'])is not list or not set(snapshot['parents'])<=set(known):raise ValueError('actual Telepath parent receipts required')
 passed=set(PARENTS[u])<={known[x] for x in snapshot['parents']}
 rank=snapshot['intuition'] if u==CLASS else max(snapshot['intuition'],snapshot['focus'])
 return Q.require(u,'native','acquire',[Q.check('trainer','prerequisite',a.kind=='trainer','actual Trainer required'),Q.check('parent','prerequisite',passed,'actual Telepath parent required'),Q.check('rank','prerequisite',rank>=DEFINITIONS[u]['minimum_rank'],'printed Focus or Intuition rank required'),Q.check('edges','prerequisite',u!=CLASS or snapshot['psychic_connection'] and snapshot['iron_mind'],'Psychic Elemental Connection and Iron Mind required'),Q.check('selection','selection',snapshot['selection'] in LABELS if u==AWARE else snapshot['selection'] is None,'one immutable Awareness choice required')])

def after_acquire(e,a,u,sid):
 # Honed Mind's old CSV projection owns its tag. Mental Assault's Core pair
 # is deliberately separate from CSV507, so its acquired Core source owns it.
 if u!=HONED:G.stat(a,'spd',1,sid,operation_id='acquisition_stat_tag')
 if u in (HONED,ASSAULT):
  __import__('static_feature_state_grants').register_all(e,a);__import__('class_move_grants').register_all(e,a)
 if u==AWARE:
  selected=acquired(a,u)['snapshot']['selection'];a.spec.setdefault('feature_choices',{})[u]=[selected]
  G.grant(a,'abilities',LABELS[selected],sid,'feature',rule_id=u,owner_id=a.entity_id,lifetime='while_owned');G.ensure_ability(e,a,LABELS[selected])

def validate_acquisition(a,r,sid,active):
 if not active:return
 u=r['feature_id']
 if u==AWARE and a.spec.get('feature_choices',{}).get(u)!=[r['snapshot']['selection']]:raise ValueError('Awareness selection changed')
 if u!=HONED and a.spec.get(G.KEY,{}).get('stat_sources',{}).get('spd',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Telepath SpDef tag required')

def require(e,a,u,capability=False):
 W.require_actors(e,a)
 if e.r._selected_rule(u)!=u:raise ValueError('selected exact Telepath source required')
 if not acquired(a,u):raise ValueError('actual acquired Telepath Feature required: '+u)
 if a.dead or a.fainted or not a.on_field or a.captured:raise ValueError('available Telepath actor required')
 if capability and not __import__('telepathy').owns(a):raise ValueError('current Telepathy Capability required')

def pay(e,a,u,action,ap=0,quota=None,triggered=False):
 import action_points as AP,turn as T,frequency as F
 if AP.available(a)<ap:raise ValueError('available Telepath AP required')
 if quota and not F.activation_allowed(a,u,quota,engine=e):raise ValueError('Telepath frequency exhausted')
 if triggered:__import__('action_lifecycle').triggered_free_action(e,a,u)
 elif not T.spend(e,a,action,u):raise ValueError('Telepath requires '+action+' action')
 if ap:AP.charge(a,ap)
 if quota:F.consume_activation(a,u,quota,engine=e)

def activate(e,a):
 require(e,a,CLASS)
 def apply(se,c):
  pay(se,c,CLASS,'swift',2)
  sid='telepath-scene:'+c.entity_id+':'+str(__import__('frequency').state(c)['scene'])
  G.grant(c,'capabilities','Telepathy',sid,'feature',rule_id=CLASS,owner_id=c.entity_id,lifetime='scene')
  c.spec['telepath_scene_capability']={'source_id':sid,'acquisition':acquired(c)['request_id']}
  return deepcopy(c.spec['telepath_scene_capability'])
 return G.transition(e,a,apply)

def end_capability(e,a):
 row=a.spec.pop('telepath_scene_capability',None)
 if row:G.revoke(a,row['source_id'],engine=e)

def before_revoke(e,a,sources):
 if any(a.spec.get(G.KEY,{}).get('sources',{}).get(s,{}).get('rule_id')==CLASS and not s.startswith('telepath-scene:') for s in sources):end_capability(e,a)

def detection(e,a):
 require(e,a,DETECT,True)
 maximum=3*SK.effective_rank(e.r,a,'집중');count=0
 for target in W.actor_index(e).values():
  if target.kind not in ('trainer','pokemon') or target.dead:continue
  distance=W.distance_known(a,target)
  if distance is None:
   origin=W.location_of(a);other=W.location_of(target)
   if origin.get('map_id') is not None and other.get('map_id') is not None and origin['map_id']!=other['map_id']:continue
   raise ValueError('Thought Detection needs actual distance and living facts; unknown is not zero')
  if distance<=maximum and not __import__('mindlock').block(e,target):count+=1
 def apply(se,c):
  pay(se,c,DETECT,'standard',quota={'kind':'scene','uses':1})
  result={'source':DETECT,'observer_id':c.entity_id,'count':count,'at':se.elapsed_seconds}
  c.spec.setdefault('thought_detection_observations',[]).append(result)
  return deepcopy(result)
 return G.transition(e,a,apply)

def live(a,kind=None):return [r for r in TIME.records(a) if r.get(E.KEY,{}).get('kind')=='telepath' and (kind is None or r['effect']['operation']==kind)]

def effect(e,a,target,source,operation,payload,lifetime):
 row=E.create(e,target,kind='telepath',source=source,payload={'kind':'telepath','operation':operation,'caster_id':a.entity_id,**deepcopy(payload)},capacity={'bucket':operation,'source':source},lifetime=lifetime,applied_by=a)
 row['manual_end']=True;TIME.install(e,target,row);return row

def residue(e,a,target,source,trigger):
 # Its expiry is unspecified. This discoverable instance is ended only by an
 # explicit world observation; no invented scene or clock expiry is attached.
 row=effect(e,a,target,source,'psychic_residue',{'trigger':trigger,'discoverable':True},{'boundary':'unspecified'})
 __import__('psionic_sight').witness_created(e,a,target,row)
 return row

def suggest(e,a,target,thought):
 require(e,a,SUGGEST,True);W.require_actors(e,target);E.text(thought,'actual suggested thought')
 if target.kind not in ('trainer','pokemon'):raise ValueError('Suggestion targets an actual Trainer or Pokemon')
 def apply(se,c,t):
  pay(se,c,SUGGEST,'standard')
  row=effect(se,c,t,SUGGEST,'suggestion',{'thought':thought,'compels_action':False,'creates_memories':False,'acquisition':acquired(c,SUGGEST)['request_id']},{'boundary':'bound_ap'})
  c.ap_account.charge(1,mode='bind',instance_id=row['id'])
  residue(se,c,t,SUGGEST,row['id']);return deepcopy(row)
 return G.transition(e,a,apply,participants=(target,))

def release(e,a,instance_id):
 W.require_actors(e,a);rows=[(t,r) for t in W.actor_index(e).values() for r in live(t,'suggestion') if r['id']==instance_id and r['effect']['caster_id']==a.entity_id]
 if len(rows)!=1:raise ValueError('exact live Suggestion instance owned by caster required')
 t,row=rows[0]
 def apply(se,c,target):
  if se._active_turn_actor is not c or se._ordinary_turn_rounds.get(c)!=se.round_no:raise ValueError('own open turn required for Bound AP release')
  row=next(r for r in live(target,'suggestion') if r['id']==instance_id)
  if c.ap_account.identified_bindings().get(instance_id)!=1:raise ValueError('exact live Suggestion AP reservation required')
  pay(se,c,SUGGEST,'free');c.ap_account.release_binding(instance_id,expected_amount=1)
  TIME.expire(se,target,row,event={'kind':'manual_bound_ap_release','caster_id':c.entity_id})
  return instance_id
 return G.transition(e,a,apply,participants=(t,))

def validate_effect(a,row,terminal=False):
 E.validate(row,actor=a,terminal=terminal);p=row['effect'];m=row[E.KEY]
 if p.get('kind')!='telepath' or p.get('operation') not in ('suggestion','read','psychic_residue') or p.get('caster_id')!=m.get('applied_by_actor_id') or not row.get('manual_end'):raise ValueError('actual sourced Telepath instance required')
 if p['operation']=='suggestion':
  if row['source']!=SUGGEST or p.get('compels_action')is not False or p.get('creates_memories')is not False or m['lifetime']!={'boundary':'bound_ap'}:raise ValueError('Suggestion cannot invent compulsion or memories')
  E.text(p.get('thought'),'suggested thought');E.text(p.get('acquisition'),'Suggestion acquisition')
 if p['operation']=='read':
  if row['source']!=READER or p.get('contract') not in ('core_1.05','korean_csv') or row.get('turn_deadline')!=m['lifetime'].get('turn'):raise ValueError('exact Read policy and next-user-turn ending required')
 if p['operation']=='psychic_residue' and (p.get('discoverable')is not True or m['lifetime']!={'boundary':'unspecified'}):raise ValueError('discoverable residue with unspecified expiry required')

def validate_world(e,index):
 for a in index.values():
  cap=a.spec.get('telepath_scene_capability')
  if cap and (not acquired(a) or cap['source_id'] not in a.spec.get(G.KEY,{}).get('sources',{})):raise ValueError('scene Telepathy lacks its actual acquired source')
  for r in live(a):
   validate_effect(a,r);p=r['effect'];caster=index.get(p['caster_id'])
   if caster is None:raise ValueError('actual Telepath caster required')
   if p['operation']=='suggestion' and caster.ap_account.identified_bindings().get(r['id'])!=1:raise ValueError('Suggestion lacks its exact AP binding')
   if p['operation']=='read' and r.get('turn_owner')is not caster:raise ValueError('Read must expire at the actual caster turn')
 __import__('psionic_sight').validate_world(e,index)
 return True

def mechanics(r,mid,mm):
 if mid==READER:return {'effects_exec':[]}
 if mid==PSYSHOCK:return {'effects_exec':[{'type':'damage_formula_override','defense_stat':'def','evasion_class':'특수'}]}
 return mm

def after_hit(e,a,t,move,completion):
 if move['id']!=READER:return
 contract=a.spec.get('mind_reader_contract','core_1.05')
 if contract not in ('core_1.05','korean_csv'):raise ValueError('explicit printed Mind Reader source contract required')
 row=effect(e,a,t,READER,'read',{'completion':completion,'contract':contract},{'boundary':'user_next_turn_end','turn':a.custom_conditions.get('combat_turn_serial',0)+1})
 row['turn_owner']=a;row['turn_deadline']=a.custom_conditions.get('combat_turn_serial',0)+1

def cast_reader(e,a,t,*,source_policy='core_1.05'):
 if source_policy not in ('core_1.05','korean_csv'):raise ValueError('explicit Mind Reader source contract required')
 def apply(se,c,target):
  c.spec['mind_reader_contract']=source_policy
  try:return se.use_move(c,target,READER)
  finally:c.spec.pop('mind_reader_contract',None)
 return G.transition(e,a,apply,participants=(t,))

def read_information(e,a,t):
 W.require_actors(e,a,t)
 if not __import__('telepathy').owns(a):raise ValueError('current Telepathy Capability required for Read thoughts')
 if not any(r['effect']['caster_id']==a.entity_id for r in live(t,'read')):raise ValueError('actual current Read target required')
 if __import__('mindlock').block(e,t):raise ValueError('Mindlock blocks actual thought reading')
 fact=__import__('perception_observe').current_thought(t)
 return {'source':READER,'target_id':t.entity_id,'surface_thought':None if fact is None else fact['text'],'thought_revision':None if fact is None else fact['revision'],'status':'unknown' if fact is None else 'observed'}

def read_accuracy(e,a,t,move):
 import environ_moves as ENV
 mm,_=ENV.read(e,move,a)
 for holder in W.actor_index(e).values():
  for r in list(live(holder,'read')):
   caster=W.actor_index(e)[r['effect']['caster_id']]
   outgoing=a is caster and t is (caster if r['effect']['contract']=='core_1.05' else holder)
   incoming=a is holder and t is caster
   if not outgoing and not incoming:continue
   if incoming and (mm.get('never_miss') or move.get('ac') is None):continue
   if e.rulings.decide({'type':'mind_reader_consume','source':READER,'instance_id':r['id'],'caster_id':caster.entity_id,'attacker_id':a.entity_id,'target_id':t.entity_id,'branch':'hit' if outgoing else 'miss'}) is not True:continue
   TIME.expire(e,holder,r,ending='consumed',event={'kind':'mind_reader_attack','move_id':move['id'],'attacker_id':a.entity_id,'target_id':t.entity_id})
   return outgoing
 return None

def validate_core_ability(rules,row):
 uid=row.get('id')
 if uid not in CONTRACTS or row.get('name')!=LABELS[uid] or row.get('native_contract')!=CONTRACTS[uid]:raise ValueError('exact Telepathy Ability source contract required')
 if sha256((Path(rules.root)/EXTRACT).read_bytes()).hexdigest()!=EXTRACT_SHA:raise ValueError('reviewed Telepath source changed')
 return row

def registration(rules,name):
 uid=next((u for u in LABELS if name in (u,LABELS[u]) or u==GENTLE and name=='Gentle Vibe'),None)
 if uid is None:return None
 if uid in CONTRACTS:validate_core_ability(rules,rules.core_abilities[uid])
 if rules._selected_rule(uid)!=uid:raise ValueError('selected exact Telepath Ability required')
 return {'name':LABELS[uid],'source_id':uid,'equivalent_source_ids':[uid]}

def gentle(e,a,ability,target):
 reg=registration(e.r,ability);W.require_actors(e,a,target)
 if not reg or reg['source_id']!=GENTLE or not __import__('ability_transitions').active(a,GENTLE) or a.fainted or not a.on_field:raise ValueError('actual unsuppressed Gentle Vibe owner required')
 if e.grid is None:raise ValueError('Gentle Vibe needs actual Burst geometry')
 targets=[c for c in W.actor_index(e).values() if W.distance_known(a,c) is not None and W.distance_known(a,c)<=2 and c.on_field]
 def apply(se,c,*actual):
  pay(se,c,GENTLE,'standard',quota={'kind':'scene','uses':1});out=[]
  for t in actual:
   immune=__import__('mindlock').block(se,t)
   if not immune:
    __import__('combat_state_lifecycle').reset_actor(se,t)
    for cond in list(t.conditions):
     if se.r.condition_class(cond)=='volatile':se.cure_status(t,cond)
   out.append({'target_id':t.entity_id,'status':'immune' if immune else 'calmed','immunity_source':immune})
  return {'source':GENTLE,'actor_id':c.entity_id,'targets':out}
 return G.transition(e,a,apply,participants=tuple(targets),include_rulings=True)

def evasion(a):
 return int(not a.abilities_suppressed and FEB in __import__('ability_transitions').project_components(a))

def arm(e,a,source,*,paths):
 W.require_actors(e,a);e.r._selected_rule(source)
 if source==WARNING:require(e,a,WARNING,True)
 elif source not in CONTRACTS or not __import__('ability_transitions').active(a,source):raise ValueError('actual active Telepathy Ability required')
 if type(paths)is not dict or not paths:raise ValueError('explicit optional recipient paths required')
 for uid,path in paths.items():
  t=W.actor_index(e).get(uid);W.require_actors(e,t)
  if getattr(t,'side',None)!=getattr(a,'side',None) or not getattr(a,'side',None) or source!=WARNING and t is not a:raise ValueError('actual affected ally choice required')
  if path is not None and (type(path)is not list or not path):raise ValueError('explicit nonempty physical path or decline required')
 return G.transition(e,a,lambda se,c:c.spec.setdefault('telepath_reaction_choices',{}).update({source:deepcopy(paths)}))

def reaction(e,attacker,target,move,hit,completion):
 if not hit:return hit
 import initiative_interrupts as I,turn as T
 rng=__import__('weapon_actions').range_spec(e,move,attacker);area=rng.get('shape')
 if not area and move.get('id')!='struggle':
  # Warning is an Attack feature, not limited to area Moves.
  pass
 for owner in list(W.actor_index(e).values()):
  if not owner.spec.get('telepath_reaction_choices'):continue
  owner_side=getattr(owner,'side',None)
  if not owner_side or owner_side!=getattr(attacker,'side',None):continue
  for source,paths in list(owner.spec.get('telepath_reaction_choices',{}).items()):
   if target.entity_id not in paths:continue
   if source==WARNING:
    require(e,owner,WARNING,True)
    if __import__('mindlock').block(e,attacker):continue
   elif not area or source==FEB and move.get('class') not in ('물리','특수') or not __import__('ability_transitions').active(owner,source):continue
   if not getattr(target,'side',None) or target.side!=owner_side:continue
   path=paths[target.entity_id]
   # Declining does not pay, consume an action or create a residue.
   if path is None:continue
   native=e._move_completions.get(completion)
   if not native or native['actor']is not attacker or native['phase']=='complete':raise ValueError('actual pending Attack completion required')
   if source==WARNING:
    paid=owner.spec.setdefault('telepath_warning_paid',[])
    if completion not in paid:pay(e,owner,WARNING,'free',1,triggered=True);paid.append(completion)
   uid='telepath:'+completion+':'+source+':'+target.entity_id
   parent=e._active_turn_actor
   trigger={'kind':'turn','actor_id':parent.entity_id,'serial':parent.custom_conditions['combat_turn_serial'],'round':e.round_no}
   origin=target.pos
   if source==FEB:
    e._telepath_disengage_boundary={'actor_id':target.entity_id,'source':source,'completion':completion}
    try:
     if len(path)!=1 or not T.disengage(e,target,path[0],_telepathy_source=source):raise ValueError('actual Free Disengage failed')
    finally:del e._telepath_disengage_boundary
   else:
    request={'id':uid,'actor_id':target.entity_id,'source':source,'priority':0,'mode':'reaction','payment':'next','budget':{'shift':1},'clock':'none'}
    queued=I.queue(e,[request],trigger=trigger);I.begin(e,queued['window_id'],uid)
    distance,mode=e.move_profile(target)
    if not T.spend(e,target,'shift',source,movement=True):raise ValueError('actual Shift Interrupt unavailable')
    canonical={'육상':'land','공중/부유':'sky','수영':'swim','땅속':'burrow'}.get(mode,mode)
    __import__('movement_actions').follow_paid_path(e,target,path,mode=canonical,maximum_distance=distance)
    I.finish(e)
   if target.pos==origin:raise ValueError('actual reaction path did not move')
   if source==WARNING:residue(e,owner,target,source,completion)
   owner.spec['telepath_reaction_choices'][source].pop(target.entity_id)
   # The actual immutable area stays at its original aim. Single-target
   # attacks use the same actual range owner after movement.
   if area:
    bound=getattr(e,'_telepath_area_cells',None)
    if bound is None:raise ValueError('area reaction needs its immutable actual native aim')
    return bool(__import__('body_state').cells(target,require_complete=True).intersection({tuple(x) for x in bound}))
   reach=rng.get('origin')
   reach=1 if reach=='melee' or not isinstance(reach,int) else reach
   return __import__('body_state').in_range(e,attacker,target,reach)
 return hit

def native_move(fn):
 @wraps(fn)
 def run(e,a,t,mid,*args,**kwargs):
  interested=mid in (READER,PSYSHOCK) or any(live(x,'read') or x.spec.get('telepath_reaction_choices') for x in W.actor_index(e).values())
  if not interested or getattr(e,'_reactive_move_transaction',False):return fn(e,a,t,mid,*args,**kwargs)
  def apply(se,c,target):
   payload=G._stage_transition_payload(e,se,{'args':args,'kwargs':kwargs})
   old=getattr(se,'_telepath_area_cells',None)
   try:return fn(se,c,target,mid,*payload['args'],**payload['kwargs'])
   finally:
    if old is None:se.__dict__.pop('_telepath_area_cells',None)
    else:se._telepath_area_cells=old
  return __import__('reactive_ability_events').atomic_move(e,a,t,apply)
 return run

def area_cells(e,a,t,move,aim=None):
 if e.grid is None:return None
 rng=__import__('weapon_actions').range_spec(e,move,a);shape=rng.get('shape');size=rng.get('size')
 if not shape:return None
 # Reuse the existing geometry owner, retaining the declaration-time aim for
 # each recipient even after an interrupt changes that recipient's body.
 bound=dict(move,_area_aim=a.pos if shape=='burst' else t.pos if aim is None else aim)
 return list(__import__('area_targets').cells(e,a,bound))

def capture_area(e,a,t,move):
 import combat_move_reactions as REACTIONS,warper as WARPER
 if getattr(e,'_telepath_area_cells',None) is None and any(x.spec.get('telepath_reaction_choices') or WARPER.TELEPORT in x.spec.get(REACTIONS.CHOICES,{}) for x in W.actor_index(e).values()):
  e._telepath_area_cells=area_cells(e,a,t,move,aim=move.get('_area_aim'))
