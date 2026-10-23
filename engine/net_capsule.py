"""Source-selected Net Cap, actual two-handed cannon/ammunition and manual removal.
Errata:191-243; modern capture conversion:765-769. No automatic scene expiry.
"""
from copy import deepcopy
import common_checks as C
import action_lifecycle as ACTION,confusion_attacks as CONFUSION
import combat_timing as TIMING
import turn as TURN
import movement_actions as MOVEMENT
import skill_modifiers as SKILL

SOURCE='supp-errata/캡슐-캐논'
NET='item/네트캡슐'
CANNON='item/캡슐캐논'
SIZES={'극소형':0,'소형':1,'중형':2,'대형':3,'초대형':4,'거대형':5,'Tiny':0,'Small':1,'Medium':2,'Large':3,'Huge':4,'Gigantic':5,'Gargantuan':5}

def _selected(e):
 for uid in (SOURCE,NET,CANNON):
  if e.r._selected_rule(uid)!=uid:raise ValueError('selected capsule source needs its own execution policy')

def cannon_slots(e):
 _selected(e)
 return [['주요손','반대손']]

def active(c):
 return next((x for x in TIMING.records(c) if x.get('source')==SOURCE and x.get('item')==NET and x.get('manual_end') and x.get('target_id')==c.spec.get('id')),None)

def _known(e,c):
 if c is None or c.kind not in ('trainer','pokemon') or not isinstance(c.spec.get('id'),str):raise ValueError('identified actual actor required')
 if c.r is not e.r:raise ValueError('actor belongs to another selected rule context')
 if c not in list(e.everyone or [])+list(e.gm.everyone or []):raise ValueError('actual encountered actor required')

def _size(e,c):
 value=c.spec.get('size')
 if value not in SIZES:raise ValueError('actual canonical body size required for net effects')
 return SIZES[value]

def _equipped(e,actor):
 from crafting_activities import _inventory
 _inventory(actor,'캡슐캐논',1)
 reg=getattr(actor,'_item_reg',{})
 cannon=next((x for x in reg.values() if x.get('item_id')==CANNON),None)
 if cannon is None or set(cannon.get('slots',[]))!={'주요손','반대손'}:raise ValueError('actual cannon equipped in both hand slots required')
 other={slot for x in reg.values() if x is not cannon for slot in x.get('slots',[])}
 other.update(slot for x in actor.custom_conditions.get('equipped_weapons',{}).values() for slot in x.get('slots',[]))
 if other.intersection(cannon['slots']):raise ValueError('cannon hands are also occupied by another item')

def _geometry(e,actor,target,gm_distance):
 from physical_limits import number
 if e.grid is None or not e.grid.inside(actor.pos) or not e.grid.inside(target.pos):raise ValueError('actual mapped cannon origin and target required')
 if e.grid.blocked(actor.pos,target.pos):raise ValueError('capsule line of sight blocked')
 dx,dy=abs(actor.pos[0]-target.pos[0]),abs(actor.pos[1]-target.pos[1]);horizontal=max(dx,dy)+min(dx,dy)//2
 a=number(actor.spec.get('_movement_altitude',0),'cannon altitude',minimum=0);t=number(target.spec.get('_movement_altitude',0),'target altitude',minimum=0)
 if getattr(target,'airborne',False) and not t:raise ValueError('actual airborne target altitude must be observed')
 if gm_distance is None:
  if a!=t and horizontal:raise ValueError('mixed horizontal and vertical shot needs an explicit GM measured distance')
  distance=max(horizontal,abs(a-t))
 else:
  distance=number(gm_distance,'GM shot distance',minimum=0)
  if distance<max(horizontal,abs(a-t)):raise ValueError('shot distance shorter than mapped displacement')
 if distance>6:raise ValueError('net capsule range is six metres')
 if target.pos in e.grid.blocking:raise ValueError('net grounding location is blocked; GM world response required')
 if t:
  for other in list(e.everyone or [])+list(e.gm.everyone or []):
   if other is not target and other.on_field and not other.captured and not other.fainted and other.pos==target.pos and other.spec.get('_movement_altitude',0)==0:raise ValueError('net grounding location occupied; GM world response required')
 return distance,t

@ACTION.resolved_native("actor",NET,"net_capsule")
def fire(e,actor,*,target,fixed_accuracy=None,accuracy_roll_id=None,gm_distance=None):
 import pokemon_activities as P
 import ap_roll_bonus as AP
 import effects_ext as EXT
 P._trainer(actor);MOVEMENT.boundary(e,'net_capsule');_selected(e);_known(e,actor);_known(e,target)
 if actor is target:raise ValueError('self-targeted cannon requires an explicit source policy')
 if not target.on_field or target.captured or target.dead:raise ValueError('actual uncaptured target on the field required')
 if active(target):raise ValueError('multiple physical nets need an explicit source stacking policy')
 _equipped(e,actor);size=_size(e,target);distance,altitude=_geometry(e,actor,target,gm_distance)
 if fixed_accuracy is not None:C.integer(fixed_accuracy,'capsule accuracy d20',1,20)
 AP.bonus(e,actor,accuracy_roll_id,'accuracy');EXT.validate_combat_edges(e,actor)
 rank=SKILL.effective_rank(e.r,actor,'기술학')
 from crafting_activities import _inventory
 key=_inventory(actor,'네트캡슐',1)
 if e.encounter_active and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)):raise ValueError('cannon Standard needs reviewed heavy-injury item adapter')
 move={'id':NET,'name':'네트 캡슐','class':'변화','type':'노말','ac':10-rank}
 CONFUSION.preflight(e,actor,move)
 if not TURN.spend(e,actor,'standard','네트 캡슐 발사'):return False
 actor.spec['items'][key]-=1
 serial=actor.spec.get('net_capsule_serial',0)+1;actor.spec['net_capsule_serial']=serial
 attempt={'id':actor.spec['id']+'/net-'+str(serial),'source':SOURCE,'item':NET,'actor_id':actor.spec['id'],'target_id':target.spec['id'],'ac':10-rank,'distance':distance,'status':'fired','at':e.elapsed_seconds}
 actor.spec.setdefault('net_capsule_attempts',[]).append(attempt)
 CONFUSION.observe_action(e,actor,move)
 hit,natural,_=e.accuracy_check(actor,target,move,fixed_roll=fixed_accuracy,roll_id=accuracy_roll_id)
 attempt.update(hit=hit,natural=natural,status='attached' if hit else 'missed')
 if hit:
  record=dict(attempt,size_policy='ptk-literal-large-or-smaller',observed_size=target.spec['size'],manual_end=True,statuses=['둔화','취약'] if size<=2 else [],accuracy_modifier=-3 if size<=3 else 0,blocked_movement_modes=['sky','levitate'],removal_checks=[],grounding={'from_altitude':altitude,'position':tuple(target.pos),'fall_damage':0})
  TIMING.install(e,target,record)
  target.spec['_movement_altitude']=0;target.airborne=False
  if altitude:EXT.on_enter_cell(e,target,target.pos)
  e.log('    '+target.name+': 네트 부착, 공중/부유 금지 및 낙하 피해 없는 착지',SOURCE)
 return deepcopy(attempt)

def remove(e,actor,*,method='standard',fixed=None,minutes=None,reason=None):
 choice=actor.spec.get('food_save_choice')
 if method=='standard' and ((isinstance(choice,dict) and choice.get('condition')=='네트') or 'fashion_next_save' in actor.spec):
  import state_grants as GRANTS
  return GRANTS.transition(e,actor,
   lambda staged,subject:_remove(staged,subject,method=method,fixed=fixed,minutes=minutes,reason=reason),
   include_rulings=True)
 return _remove(e,actor,method=method,fixed=fixed,minutes=minutes,reason=reason)

def _remove(e,actor,*,method='standard',fixed=None,minutes=None,reason=None):
 import pokemon_activities as P
 import capability_actions as CAP
 import effects_ext as EXT
 MOVEMENT.boundary(e,'remove_net');_selected(e);_known(e,actor)
 record=active(actor)
 if record is None:raise ValueError('actor must be the actual netted target; helping another target needs GM ruling')
 if method not in ('standard','extended'):raise ValueError('net removal is Standard saving check or Extended automatic')
 if method=='extended':
  P._outside(e);P._text(reason,'GM Extended removal duration reason');C.integer(minutes,'Extended removal minutes',1)
  if fixed is not None:raise ValueError('Extended removal is automatic, with no saving roll')
  if not TURN.can_act(e,actor):return False
  import action_lifecycle as ACTION
  if not ACTION.ordinary_permission(e,actor) or not ACTION.status_permission(e,actor,'extended'):return False
  e.advance_time(minutes*60,[actor]);ACTION.record_action(e,actor,'extended');record['removed_by']='extended';record['duration_reason']=reason
  TIMING.expire(e,actor,record)
  return {'removed':True,'method':'extended','seconds':minutes*60}
 if minutes is not None or reason is not None:raise ValueError('Standard removal does not consume invented Extended time')
 if fixed is not None:C.integer(fixed,'net saving d20',1,20)
 power=CAP.power(actor)
 C.integer(actor.save_mod,'saving throw modifier')
 import enduring_awareness as AWARENESS
 awareness_bonus=AWARENESS.bonus(e,actor)
 if e.encounter_active and (actor.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(actor)):raise ValueError('net removal Standard needs reviewed heavy-injury item adapter')
 import food_effects as FOOD
 import condition_recovery as RECOVERY
 RECOVERY.save_preflight(e,actor,'네트')
 if not TURN.spend(e,actor,'standard','네트 제거'):return False
 import duelist as DUELIST
 natural=11 if DUELIST.choose_eleven(e,actor,'net_escape') else fixed if fixed is not None else e.d20()
 food_bonus=FOOD.save_bonus(e,actor,'네트')
 import fashion_items as FASHION
 fashion_bonus=FASHION.consume_save_bonus(e,actor)
 all_roll_modifier=FASHION.all_roll_modifier(actor)
 # Native save modifiers and GM DC adjustments retain the normal saving path.
 dc=EXT.save_dc(e,actor,None,15)+e.rulings.consume('dc',actor.name,e)-food_bonus-fashion_bonus-all_roll_modifier
 check={'natural':natural,'power':power,'save_modifier':actor.save_mod+awareness_bonus,'food_bonus':food_bonus,
        'fashion_bonus':fashion_bonus,'all_roll_modifier':all_roll_modifier,
        'total':natural+power+actor.save_mod+awareness_bonus+food_bonus+fashion_bonus+all_roll_modifier,
        'dc':dc+actor.save_mod+awareness_bonus+food_bonus+fashion_bonus+all_roll_modifier,'passed':natural+power>=dc,'at':e.elapsed_seconds}
 record['removal_checks'].append(check)
 if check['passed']:record['removed_by']='standard';TIMING.expire(e,actor,record)
 return {'removed':check['passed'],'method':'standard','check':dict(check)}

def capture_bonus(e,target):
 if active(target) is None:return 0
 _selected(e)
 if target.kind!='pokemon' or target.captured or target.spec.get('trainer_id') or target.spec.get('trainer') or not target.spec.get('wild',target.side=='wild'):return 0
 # +20 to the former target rate eases capture: modern target DC -20/5,
 # equivalently +4 to the modern roll (not a ball's -20 roll modifier).
 if e.r._selected_rule('supp-errata/포획-메커니즘-변경')!='supp-errata/포획-메커니즘-변경':raise ValueError('selected modern capture conversion needs its own adapter')
 if e.r.mech('pokemon/capture-rate').get('_version') is not None:raise ValueError('net modern bonus requires selected d20 capture')
 return 4

ACTIVITIES={'net_capsule':fire}
