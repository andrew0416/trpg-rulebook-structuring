"""Sage adapters; acquisition, team pools, clocks and recovery keep their owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import common_checks as C
import state_grants as G
import world_entities as W
import combat_timing as TIME
import effect_instances as E
import frequency as F

CLASS='class/현자';SHIELD='feat/신성-방패';DEFENSE='feat/신비의-방어'
BENEDICTION='feat/현자의-축도';HANDS='feat/안수';PRAYERS='feat/기도자를-향한-큰-반응';WIND='feat/신성한-바람'
TOUCH='ability/축복의손길-core';HEALER='ability/치유의마음'
SOURCE_SHA256='a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4'
EXTRACT='data/verification/sage-core-source-excerpts.txt'
EXTRACT_SHA='4ec401e89c1ad3b7ba8b054e6e1f33cff65e89b6b9c8f77d0d98a2130a20c1e8'
FEATURES={CLASS:(3076,3078),SHIELD:(3080,3084),DEFENSE:(3086,3090),BENEDICTION:(3092,3101),HANDS:(3103,3107),PRAYERS:(3109,3114),WIND:(3116,3121)}
PARENTS={CLASS:(),SHIELD:(CLASS,),DEFENSE:(CLASS,),BENEDICTION:(SHIELD,DEFENSE),HANDS:(CLASS,),PRAYERS:(HANDS,),WIND:(BENEDICTION,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[3067,3067] if u==CLASS else list(s),
 'clause_id':{CLASS:'C04-113',PRAYERS:'C04-114',WIND:'C04-115'}.get(u,'input/ch04-trainer-classes.md:'+str(s[0])+'-'+str(s[1])),
 'parents':list(PARENTS[u]),'parent_mode':'any' if u==BENEDICTION else 'all',
 'minimum_rank':3 if u==CLASS else 4 if u==BENEDICTION else 5 if u==HANDS else 6 if u==WIND else 0,
 'stat_tags':['hp'],'choices':[TOUCH,HEALER] if u==HANDS else []} for u,s in FEATURES.items()}
MOVES={'move/리플렉터':SHIELD,'move/주술':SHIELD,'move/빛의장막':DEFENSE,'move/신비의부적':DEFENSE}
BONUSES={'move/리플렉터':'def','move/빛의장막':'spd','move/신비의부적':'eva','move/주술':'acc'}
CORE_CONTRACT={'type':'core_blessed_touch','frequency':{'kind':'daily','uses':2},'action':'standard','range':'adjacent','heal':'maximum_hp/4'}

def records(actor,feature=None,active=False):
 import trainer_feature_acquisition as T
 return [record for _, record in T.static_family_acquisitions(actor, FEATURES, feature, active=active)]

def acquired(actor,feature=CLASS):
 rows=records(actor,feature,True)
 return rows[-1] if rows else None

def acquisition_snapshot(e,actor,feature,rank,selection):
 import skill_modifiers as SK
 if rank is not None:raise ValueError('Sage has no Ranked Features')
 if feature==HANDS:
  selection={TOUCH:TOUCH,'축복의손길':TOUCH,HEALER:HEALER,'치유의마음':HEALER}.get(selection)
  if selection is None:raise ValueError('Lay on Hands requires exactly one Core Blessed Touch or Healer choice')
 elif selection is not None:raise ValueError('this Sage Feature has no acquisition choice')
 return {'rank':SK.rank(e.r,actor,'오컬트학')[2],'parents':[r['request_id'] for r in records(actor,active=True) if r['feature_id'] in PARENTS[feature]],'selection':selection}

def qualification(actor,feature,snapshot,prerequisite_source):
 import acquisition_qualification as Q
 if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'rank','parents','selection'}:raise ValueError('actual Sage acquisition observations required')
 C.integer(snapshot['rank'],'Occult Education rank',1,6)
 known={r['request_id']:r['feature_id'] for r in records(actor) if r['feature_id'] in PARENTS[feature]}
 if not isinstance(snapshot['parents'],list) or not set(snapshot['parents'])<=set(known):raise ValueError('actual Sage parent receipts required')
 parents={known[x] for x in snapshot['parents']}
 passed=bool(parents) if feature==BENEDICTION else set(PARENTS[feature])<=parents
 chosen=snapshot['selection'] in (TOUCH,HEALER) if feature==HANDS else snapshot['selection'] is None
 return Q.require(feature,'native','acquire',[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),Q.check('parent','prerequisite',passed,'actual Sage parent required'),Q.check('rank','prerequisite',snapshot['rank']>=DEFINITIONS[feature]['minimum_rank'],'printed Occult Education rank required'),Q.check('choice','selection',chosen,'one printed Lay on Hands choice required')])

def after_acquire(e,actor,feature,sid):
 operation='feature_count' if feature in (SHIELD,DEFENSE) else 'acquisition_stat_tag'
 G.stat(actor,'hp',1,sid,operation_id=operation)
 if feature in (SHIELD,DEFENSE):
  __import__('static_feature_state_grants').register_all(e,actor)
  __import__('class_move_grants').register_all(e,actor)
 if feature==HANDS:
  actor.spec.setdefault('feature_choices',{})[feature]=[acquired(actor,feature)['snapshot']['selection']]
  __import__('acquired_feature_projections').register_all(e,actor)

def validate_acquisition(actor,record,sid,active):
 if not active:return
 uid=record['feature_id'];operation='feature_count' if uid in (SHIELD,DEFENSE) else 'acquisition_stat_tag'
 if actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('hp',{}).get('sources',{}).get(sid,{}).get(operation)!={'delta':1,'minimum':None}:raise ValueError('actual source-owned Sage HP tag required')
 if uid==HANDS and actor.spec.get('feature_choices',{}).get(HANDS)!=[record['snapshot']['selection']]:raise ValueError('Lay on Hands acquisition choice changed')

def require(e,actor,feature):
 W.require_actors(e,actor)
 if e.r._selected_rule(feature)!=feature or not acquired(actor,feature):raise ValueError('actual acquired Sage Feature required: '+feature)
 __import__('trainer_feature_acquisition').validate_actor(actor)
 if actor.fainted or not actor.on_field:raise ValueError('available Sage actor required')

def pay(e,actor,source,action,*,ap=0,quota=None):
 import action_points as AP,turn as TURN
 if AP.available(actor)<ap:raise ValueError('available Sage AP required')
 if quota and not F.activation_allowed(actor,source,quota,engine=e):raise ValueError('Sage frequency exhausted')
 if action=='free' and source in (BENEDICTION,PRAYERS,WIND):
  if not __import__('body_modes').permits(actor,'free'):raise ValueError('Sage triggered Free body permission required')
  __import__('action_lifecycle').triggered_free_action(e,actor,source)
 elif not TURN.spend(e,actor,action,source):raise ValueError('Sage requires '+action+' action')
 if ap:AP.charge(actor,ap)
 if quota:F.consume_activation(actor,source,quota,engine=e)

def ally(e,actor,target,maximum=5):
 W.require_actors(e,actor,target)
 if not actor.side or actor.side!=target.side or target.fainted or not target.on_field:raise ValueError('actual available Sage ally required')
 if e.grid is None or actor.pos is None or target.pos is None or __import__('grid').cheb(actor.pos,target.pos)>maximum:raise ValueError('Sage ally outside printed range')

def cast(e,actor,target):
 require(e,actor,CLASS);ally(e,actor,target);TIME.current(e)
 def apply(se,a,t):
  pay(se,a,CLASS,'standard')
  return grant(se,a,t,stacking=False)
 return G.transition(e,actor,apply,participants=(target,),include_rulings=True)

def grant(e,actor,target,*,stacking,trigger=None):
 import skill_modifiers as SK
 require(e,actor,CLASS);ally(e,actor,target);count=TIME.current(e)
 rank=SK.rank(e.r,actor,'오컬트학')[2];tick=e.tick(target);amount=max(rank*2,tick)
 row=E.create(e,target,kind='sage_dr',source=PRAYERS if stacking else CLASS,payload={'kind':'sage_dr','amount':amount,'rank':rank,'tick':tick,'stacking':stacking,'caster_id':actor.entity_id,'acquisition':acquired(actor,PRAYERS if stacking else CLASS)['request_id'],'trigger':trigger},capacity={'bucket':'sage_dr','source':CLASS},lifetime={'boundary':'initiative_count','round':e.round_no+1,'count':count},applied_by=actor)
 row['count_deadline']=(e.round_no+1,count);TIME.install(e,target,row)
 validate_effect(target,row)
 return deepcopy(row)

def validate_effect(actor,row,*,terminal=False):
 E.validate(row,actor=actor,terminal=terminal);p=row['effect'];m=row[E.KEY]
 C.integer(p.get('amount'),'Sage DR',1)
 C.integer(p.get('rank'),'Sage cast Occult Education rank',1,6);C.integer(p.get('tick'),'Sage actual target Tick',1)
 if p['amount']!=max(p['rank']*2,p['tick']):raise ValueError('Sage DR must use the greater printed operand')
 if p.get('kind')!='sage_dr' or type(p.get('stacking'))is not bool or row['source']!=(PRAYERS if p['stacking'] else CLASS) or p.get('caster_id')!=m.get('applied_by_actor_id') or not isinstance(p.get('acquisition'),str):raise ValueError('sourced Sage DR instance required')
 if m['capacity']!={'bucket':'sage_dr','source':CLASS} or m['lifetime']!={'boundary':'initiative_count','round':row['count_deadline'][0],'count':row['count_deadline'][1]}:raise ValueError('Sage exact full-round deadline required')
 if p['stacking'] and not isinstance(p.get('trigger'),dict):raise ValueError('actual Prayer trigger required')

def reduction(actor):
 rows=[r['effect'] for r in TIME.records(actor) if r.get(E.KEY,{}).get('kind')=='sage_dr']
 ordinary=max([r['amount'] for r in rows if not r['stacking']]+[0])
 groups={}
 for r in rows:
  if r['stacking']:groups[r['caster_id']]=groups.get(r['caster_id'],0)+r['amount']
 return max([ordinary,*groups.values()])

def validate_core_ability(rules,row):
 if row.get('id')!=TOUCH or row.get('name')!='축복의손길 [Core p312]' or row.get('native_contract')!=CORE_CONTRACT:raise ValueError('exact Core Blessed Touch contract required')
 if sha256((Path(rules.root)/EXTRACT).read_bytes()).hexdigest()!=EXTRACT_SHA:raise ValueError('reviewed Sage English source changed')
 return row

def registration(rules,name):
 if name not in (TOUCH,'축복의손길 [Core p312]',HEALER,'치유의마음'):return None
 if name in (TOUCH,'축복의손길 [Core p312]'):
  validate_core_ability(rules,rules.core_abilities[TOUCH]);uid=TOUCH;label='축복의손길 [Core p312]'
 else:
  __import__('source_context').verified_source(rules,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='Core Healer R395')
  if sha256((Path(rules.root)/EXTRACT).read_bytes()).hexdigest()!=EXTRACT_SHA:raise ValueError('reviewed Healer source changed')
  uid=HEALER;label='치유의마음'
 if rules._selected_rule(uid)!=uid:raise ValueError('selected exact Sage Ability required')
 return {'name':label,'source_id':uid,'equivalent_source_ids':[uid]}

def activate_ability(e,actor,ability,target):
 reg=registration(e.r,ability);W.require_actors(e,actor,target)
 if reg is None or not __import__('ability_transitions').active(actor,reg['source_id']) or actor.fainted or not actor.on_field:raise ValueError('actual unsuppressed acquired healing Ability required')
 if target.kind not in ('trainer','pokemon') or not e.adjacent(actor,target):raise ValueError('actual adjacent Pokemon or Trainer required')
 def apply(se,a,t):
  source=reg['source_id'];touch=source==TOUCH
  pay(se,a,source,'standard' if touch else 'free',quota={'kind':'daily' if touch else 'scene','uses':2 if touch else 1})
  if touch:
   amount=__import__('arithmetic_policy').ratio(t.base_max_hp,4)
   changed=__import__('life').heal(se,t,amount,source_kind='feature')
  else:
   before=set(t.conditions)
   for condition in sorted(before):se.cure_status(t,condition)
   changed=len(before-set(t.conditions))
  receipt={'kind':'healing_ability','source':source,'actor_id':a.entity_id,'target_id':t.entity_id,'changed':changed,'at':se.elapsed_seconds,'sequence':len(a.spec.get('sage_healing_uses',[]))+1}
  a.spec.setdefault('sage_healing_uses',[]).append(receipt)
  if a.side and a.side==t.side:prayer(se,a,t,receipt)
  return deepcopy(receipt)
 return G.transition(e,actor,apply,participants=(target,),include_rulings=True)

def prayer(e,owner,target,trigger):
 if trigger.get('kind')=='injury':
  valid=any(r['id']==trigger.get('sequence') and r['target'] is target and r['kind']=='injury' and r['amount']==trigger.get('amount') and r['source']==trigger.get('source') for r in e._precision_events)
 else:valid=trigger in owner.spec.get('sage_healing_uses',[]) and trigger.get('target_id')==target.entity_id
 if not valid:return False
 key=(trigger['kind'],trigger['sequence'])
 used=[r for c in W.actor_index(e).values() for r in TIME.records(c)+c.spec.get('effect_instance_history',[]) if r.get(E.KEY,{}).get('kind')=='sage_dr' and r['effect']['caster_id']==owner.entity_id and r['effect']['stacking']]
 if any((r['effect']['trigger']['kind'],r['effect']['trigger']['sequence'])==key for r in used):return False
 if not acquired(owner,PRAYERS) or owner.fainted or not owner.on_field or not target.side or owner.side!=target.side or target.fainted:return False
 quota={'kind':'scene','uses':3}
 if not F.activation_allowed(owner,PRAYERS,quota,engine=e):return False
 if not e.encounter_active:return False
 if e.grid is None or owner.pos is None or target.pos is None or __import__('grid').cheb(owner.pos,target.pos)>5:return False
 TIME.current(e)
 if e.rulings.decide({'type':'sage_prayers','unit':PRAYERS,'actor_id':owner.entity_id,'target_id':target.entity_id,'trigger':deepcopy(trigger),'text':'Use Sage as Free for this actual trigger?'}) is not True:return False
 pay(e,owner,PRAYERS,'free',quota=quota)
 grant(e,owner,target,stacking=True,trigger=deepcopy(trigger));return True

def injury(e,target,amount,source):
 if amount<=0:return
 trigger={'kind':'injury','sequence':getattr(e,'_precision_sequence',0),'source':source,'amount':amount,'target_id':target.entity_id}
 for owner in list(W.actor_index(e).values()):
  if acquired(owner,PRAYERS):prayer(e,owner,target,trigger)

def blessing_selected(e,owner,target,record,event):
 if not acquired(owner,BENEDICTION) or not owner.side or owner.side!=target.side or record['source'] not in MOVES:return
 uid=event['event_id'];rows=owner.spec.setdefault('sage_benedictions',[])
 if any(r['event_id']==uid and r['instance_id']==record['id'] for r in rows):return
 import blessing_effects as B
 rows.append({'event_id':uid,'instance_id':record['id'],'target_id':target.entity_id,'move_id':B.effective_source(record),'status':'pending','acquisition':acquired(owner,BENEDICTION)['request_id'],'at':e.elapsed_seconds})

def finish_blessings(e):
 """Only native successful producer completion calls this after the entire attack."""
 import action_points as AP
 for owner in list(W.actor_index(e).values()):
  for row in owner.spec.get('sage_benedictions',[]):
   if row['status']!='pending':continue
   row['status']='declined';target=W.actor_index(e).get(row['target_id'])
   if target is None or not acquired(owner,BENEDICTION) or owner.fainted or AP.available(owner)<1:continue
   if e.rulings.decide({'type':'sage_benediction','unit':BENEDICTION,'actor_id':owner.entity_id,'target_id':target.entity_id,'event_id':row['event_id'],'move_id':row['move_id'],'text':'1 AP Free after Blessing and attack resolution?'}) is not True:continue
   pay(e,owner,BENEDICTION,'free',ap=1)
   stat=BONUSES[row['move_id']]
   if stat in ('def','spd'):e.change_stage(target,stat,1)
   else:
    field='evasion_mod' if stat=='eva' else 'accuracy_stage'
    if not G.adjust_numeric(target,field,1):setattr(target,field,max(-6,min(6,getattr(target,field)+1)))
   row['status']='applied';row['resolved_at']=e.elapsed_seconds

def wind(e,actor,move_id):
 require(e,actor,WIND)
 if move_id not in MOVES or not acquired(actor,MOVES[move_id]) or move_id not in actor.moves:raise ValueError('Divine Wind requires a Sage Blessing type you can actually generate')
 import blessing_effects as B
 B.checked(e)
 scene=F.state(actor)['scene'];history=actor.spec.get('sage_wind_choices',[])
 if any(r['scene']==scene and r['move_id']==move_id for r in history):raise ValueError('Divine Wind type already selected this Scene')
 def apply(se,a):
  pay(se,a,WIND,'free',ap=2)
  converted=B.convert_sage(se,a,move_id)
  a.spec.setdefault('sage_wind_choices',[]).append({'scene':scene,'move_id':move_id,'at':se.elapsed_seconds,'instances':converted,'acquisition':acquired(a,WIND)['request_id']})
  return tuple(converted)
 return G.transition(e,actor,apply,include_rulings=True)

def withdraw(e,actor,feature):
 if feature not in FEATURES:return
 for target in W.actor_index(e).values():
  for row in list(TIME.records(target)):
   if row.get(E.KEY,{}).get('kind')=='sage_dr' and row['effect']['caster_id']==actor.entity_id and (feature==CLASS or feature==PRAYERS and row['effect']['stacking']):TIME.expire(e,target,row,event={'kind':'source_withdrawn','source':feature})
