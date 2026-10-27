import arithmetic_policy as M
"""PTK movement capabilities on native movement, actor state, and turn costs.

A stored sheet may already include learned bonuses. GM observations explicitly
mark it current or base; only base records derive those bonuses. Learning is
possession, never a Move-use or daily-frequency check.
"""
from copy import copy,deepcopy
import common_checks as C
import turn as TURN
import action_lifecycle as ACTION
import capability_actions as LOAD
from grid import cheb
MODES=('land','sky','levitate','swim','burrow','teleport')

def reason(value):
 if not isinstance(value,str) or not value.strip():raise ValueError('explicit GM world observation reason required')
 return value

def capabilities(e,c,*,environment=True):
 result=dict(c.spec.get('movement') or {});result['land']=c.movement
 for key in MODES+('free_float',):
  if key in result:C.integer(result[key],key+' movement',0)
 basis=c.spec.get('movement_basis','current')
 if basis not in ('base','current','trainer_base'):raise ValueError('movement basis must be base, current, or trainer_base')
 if basis=='trainer_base':
  import trainer_capabilities as TRAINER
  if TRAINER.DERIVED.intersection(c.spec.get('movement') or {}):raise ValueError('derived trainer fields must not also be supplied as current values')
  result.update(TRAINER.values(c))
  result["land"]=c.movement
  result["swim"]=TRAINER.swimming(c,result["land"])
 if basis=='base' and c.kind=='trainer':
  import trainer_capabilities as TRAINER
  if 'swim' in result:result['swim']=TRAINER.swimming(c,result['land'],base_swim=result['swim'])
  result=TRAINER.jump_bonuses(c,result)
 if basis in ('base','trainer_base'):
  import move_capabilities as MOVE_CAPABILITIES
  result=MOVE_CAPABILITIES.numeric_values(c,result,MODES+('free_float','high_jump','long_jump'))
 else:
  import move_capabilities as MOVE_CAPABILITIES
  result=MOVE_CAPABILITIES.current_values(c,result,MODES+('free_float','high_jump','long_jump'))
 if basis=='base' and c.kind=='pokemon':
  if '부유' in c.abilities or 'Levitate' in c.abilities:
   if c.abilities_suppressed:raise ValueError('suppressed Levitate capability duration needs an explicit current sheet ruling')
   if e.r._selected_rule('ability/부유')!='ability/부유':raise ValueError('selected Levitate variant needs its own capability policy')
   result['levitate']=result.get('levitate',0)+(2 if result.get('levitate',0)>0 else 4)
 import pokemon_capability_edges as CAP_EDGES
 result=CAP_EDGES.apply(c,result)
 result=__import__('combat_move_reactions').movement(e,c,result)
 import training_features as TRAINING
 result=TRAINING.movement(c,result)
 import survivalist_features as SURVIVALIST
 result=SURVIVALIST.movement(e,c,result)
 import optional_physical_equipment as OPTIONAL_EQUIPMENT
 result=OPTIONAL_EQUIPMENT.movement(c,result)
 import stat_ace as STAT
 bonus=STAT.stratagem_bonus(e,c,'movement')
 for key in MODES+('free_float',):
  if result.get(key,0)>0:result[key]+=bonus
 import csv_item_form_contracts as CSV_FORMS
 result=CSV_FORMS.movement_projection(e,c,result)
 if c.kind=='pokemon':
  import baby_templates as BABY
  result=BABY.capability_values(c,result,MODES+('free_float','high_jump','long_jump'))
 import combat_timing as TIMING
 result=__import__('telekinetic').movement(e,c,result)
 result=__import__('warper').movement(e,c,result)
 bonus=__import__('berserker').frenzy_bonus(c)
 for mode in MODES:
  if result.get(mode,0)>0:result[mode]+=bonus
 bonus=__import__('commander_orders').movement_bonus(e,c)
 for mode in MODES:
  if result.get(mode,0)>0:result[mode]+=bonus
 import environment_derive as ED
 result=ED.movement(e,c,result) if environment else result
 for mode in TIMING.blocked_movement_modes(c):result[mode]=0
 return result

def set_capabilities(e,c,values,*,basis,reason_text):
 reason(reason_text)
 if not isinstance(values,dict):raise ValueError('movement capability mapping required')
 if basis=='current':
  import pokemon_capability_edges as CAP_EDGES
  values=CAP_EDGES.decompose_current(c,values)
 # Validate raw input before arithmetic can coerce booleans into integers.
 for key in MODES+('free_float',):
  if key in values:C.integer(values[key],key+' movement',0)
 probe=copy(c);probe.spec=dict(c.spec,movement=deepcopy(values),movement_basis=basis)
 probe.__dict__.pop('movement',None)
 import state_grants as GRANTS
 delta=sum(c.spec.get(GRANTS.KEY,{}).get('numbers',{}).get('movement',{}).get('sources',{}).values())
 if basis=='trainer_base':probe._movement_delta=delta
 else:probe._movement_value=values.get('land',4)+delta
 import move_capabilities as MOVE_CAPABILITIES
 probe.spec[MOVE_CAPABILITIES.TOTALS_KEY]=MOVE_CAPABILITIES.observe_totals(probe)
 result=capabilities(e,probe,environment=False)
 import environment_derive as ED
 result=ED.movement(e,c,result)
 before={'movement':deepcopy(c.spec.get('movement')),'basis':c.spec.get('movement_basis','current')}
 c.spec['movement']=deepcopy(values);c.spec['movement_basis']=basis
 c.spec[MOVE_CAPABILITIES.TOTALS_KEY]=probe.spec[MOVE_CAPABILITIES.TOTALS_KEY]
 c.__dict__.pop('movement',None)
 if basis=='trainer_base':c._movement_delta=delta
 else:c._movement_value=values.get('land',4)+delta
 row=c.spec.get(GRANTS.KEY,{}).get('numbers',{}).get('movement')
 if row is not None:
  row['base']=c.movement-delta;row['visible']=c.movement
 e.gm._rec('이동 재능 원천',before,{'movement':values,'basis':basis},reason_text,c)
 return result

def boundary(e,name):
 import passive_events as P
 import league_runtime as L
 import heavy_injury_adapter as H
 P.ensure_clear(e);L.check_boundary(e,name);H.ensure_clear(e);ACTION.ensure_resolutions_clear(e)

def sprint(e,c,*,source_policy=None):
 boundary(e,'sprint');e.r._selected_rule('maneuver/질주')
 if source_policy is None:return C.PendingDecision('Sprint source choice: ch06 one movement vs ch07 rest of turn')
 if source_policy not in ('ch06_once','ch07_turn'):raise ValueError('unknown Sprint source policy')
 if '질주' in c.custom_conditions:raise ValueError('one pending Sprint movement already exists')
 if not TURN.spend(e,c,'standard','질주'):return False
 c.custom_conditions['질주']={'round':e.round_no,'source_policy':source_policy}
 import athlete as ATHLETE
 ATHLETE.coach_sprint(e,c)
 e.log('  '+c.name+': 질주 '+('x2 (코칭)' if ATHLETE.sprint_rate(e,c)=='1' else '+50%')+', '+source_policy,'maneuver/질주')
 return True

def distance_budget(e,c,mode,*,as_slowed=False):
 M.validate_source(e.r)
 value,_=e.move_profile(c,movement_mode=mode,as_slowed=as_slowed)
 if mode!='teleport' and '질주' in c.custom_conditions:value=M.increase(value,__import__('athlete').sprint_rate(e,c),quantity='movement',base_id='current_capability',stage='sprint',source='maneuver/질주')
 return LOAD.movement_limit(c,value)

def _point(value):
 if not isinstance(value,(tuple,list)) or len(value)!=2 or any(type(v)is not int for v in value):raise ValueError('integer two-dimensional mapped coordinate required')
 return tuple(value)

def step_cost(origin,destination,diagonals):
 if cheb(origin,destination)>1:raise ValueError('continuous mapped movement step required')
 if origin==destination:return 0,diagonals
 diagonal=origin[0]!=destination[0] and origin[1]!=destination[1]
 return (2 if diagonal and diagonals%2 else 1),diagonals+int(diagonal)

def observed_path(e,c,path,*,ignore_actors=()):
 """Read an ordered observed 3D path through the existing body/LOS geometry."""
 from physical_limits import number
 if not isinstance(path,(list,tuple)) or len(path)<2:raise ValueError('observed path includes actual origin and destination')
 points=[]
 for index,node in enumerate(path):
  if type(node) is not dict or set(node) not in ({'position','altitude'},{'position','altitude','gm_distance'}):raise ValueError('exact observed position, altitude and optional measured distance required')
  position=_point(node['position']);altitude=number(node['altitude'],'observed path altitude',minimum=0)
  points.append(dict(node,position=position,altitude=altitude))
 if points[0]['position']!=c.pos or points[0]['altitude']!=c.spec.get('_movement_altitude',0) or 'gm_distance' in points[0]:raise ValueError('observed path must start at actual current position and altitude')
 probe=copy(c);probe.spec=dict(c.spec);distance=0;diagonals=getattr(c,'_diagonal_steps',0);points[0]['diagonals']=diagonals
 for node in points[1:]:
  old=probe.spec.get('_movement_altitude',0);rise=abs(node['altitude']-old)
  if rise>1:raise ValueError('observed path needs continuous altitude steps')
  horizontal,next_diagonals=step_cost(probe.pos,node['position'],diagonals)
  measured=node.get('gm_distance')
  if measured is not None and number(measured,'GM path segment distance',minimum=0)<max(horizontal,rise):raise ValueError('measured segment shorter than actual path displacement')
  if measured is None and not rise:measured=horizontal
  _,cost=_travel_geometry(e,probe,node['position'],node['altitude'],measured,ignore_actors=ignore_actors)
  distance+=cost;diagonals=next_diagonals;node['diagonals']=diagonals
  probe.pos=node['position'];probe.spec['_movement_altitude']=node['altitude']
 return {'path':points,'distance':distance,'diagonals':diagonals}

def burrow_plan(e,c,path,*,diggable,reason_text,surface=False,maximum_distance=None,ignore_actors=()):
 reason(reason_text)
 if type(surface)is not bool:raise ValueError('surface choice must be boolean')
 if diggable is not True:return C.PendingDecision('GM establishes that this actual path can be burrowed')
 if not isinstance(path,(list,tuple)) or len(path)<2:raise ValueError('burrow path includes origin and destination')
 path=tuple(_point(q) for q in path)
 if e.grid is None or path[0]!=c.pos or any(not e.grid.inside(q) for q in path):raise ValueError('actual mapped burrow path required')
 if any(cheb(a,b)!=1 for a,b in zip(path,path[1:])):raise ValueError('burrow path must be continuous')
 size=c.spec.get('size')
 if not isinstance(size,(str,int)) or isinstance(size,bool) or size=='':raise ValueError('actual body size needed to preserve tunnel size')
 value=distance_budget(e,c,'burrow');cost=0;diagonals=getattr(c,'_diagonal_steps',0)
 if maximum_distance is not None:value=min(value,C.integer(maximum_distance,'actual paid burrow allowance',0))
 for a,b in zip(path,path[1:]):
  step,diagonals=step_cost(a,b,diagonals);cost+=step
 if cost>value:raise ValueError('burrow path exceeds available movement')
 import body_state as BODY
 if any(not e.grid.inside(cell) for point in path for cell in BODY.at_position(c,point)):
  raise ValueError('burrow body extends outside mapped path')
 import map_terrain as TERRAIN
 for index,point in enumerate(path[1:],1):
  if not TERRAIN.can_travel(e,c,point,'burrow',altitude=0,underground=not(surface and index==len(path)-1)):
   raise ValueError('burrow path conflicts with actual base terrain and destination')
 if surface and not BODY.can_place(e,c,path[-1],origin=path[-2],altitude=0,underground=False,ignore_actors=ignore_actors):
  raise ValueError('surface destination is blocked or occupied')
 return {'mode':'burrow','path':path,'distance':cost,'budget':value,'diagonals':diagonals,
         'origin_altitude':c.spec.get('_movement_altitude',0),'origin_underground':bool(c.spec.get('_burrow',{}).get('underground')),
         'parameters':{'diggable':diggable,'surface':surface,'reason_text':reason_text}}


def burrow_move(e,c,path,*,diggable,reason_text,surface=False):
 import state_grants as G
 return G.transition(e,c,lambda se,sa:_burrow_move(se,sa,path,diggable=diggable,reason_text=reason_text,surface=surface))

def _burrow_move(e,c,path,*,diggable,reason_text,surface=False):
 import environment_change as EC
 if EC.managed(e,c):return EC.run(e,c,lambda s,a:burrow_move(s,a,path,diggable=diggable,reason_text=reason_text,surface=surface))
 boundary(e,'burrow_move')
 plan=burrow_plan(e,c,path,diggable=diggable,reason_text=reason_text,surface=surface)
 if isinstance(plan,C.PendingDecision):return plan
 if not c.on_field or c.captured or not TURN.spend(e,c,'shift','지중 이동',movement=True):return False
 result=follow_paid_transfer(e,c,plan)
 return {k:v for k,v in result.items() if k not in ('steps','mode')} if result['steps'] else False

def reset_preflight(c):
 import action_resources as RESOURCES
 RESOURCES.pending(c)

def reset_budget(e,c):
 state=c.spec.get('_burrow',{})
 if state.get('standard_debt'):
  import action_resources as RESOURCES
  c.budget=RESOURCES.subtract(c.budget,{'standard':1})
  state['standard_debt']=False;state['debt_paid_round']=e.round_no
  e.log('  '+c.name+': 지난 지하 체류로 다음 기본 행동 상실','capability/burrow')

def finish_turn(e,c):
 import initiative_interrupts as INTERRUPTS
 state=c.spec.get('_burrow',{})
 if state.get('underground') and state.get('upkeep_round')!=e.round_no:
  if not e.encounter_active:return C.PendingDecision('noncombat underground timing needs GM round intervals')
  if not TURN.can_act(e,c):raise ValueError('unconscious underground actor needs a GM world response')
  if c.budget is None:raise ValueError('underground upkeep requires current action ledger')
  if c.budget.get('standard',0)>0:
   if not TURN.spend(e,c,'standard','지하 체류'):raise ValueError('cannot pay underground Standard upkeep; world response required')
  # ch07:63 Full consumes the Standard as well as Shift. Preserve the actual
  # action kind instead of globally pretending a Full was a Standard action.
  elif c.took_standard or 'full' in getattr(c,'_action_history',()) or state.get('debt_paid_round')==e.round_no or INTERRUPTS.paid_standard(e,c):
   state['standard_debt']=True
   e.log('  '+c.name+': 기본 행동을 이미 소모하여 다음 기본 행동 상실 예약','capability/burrow')
  else:raise ValueError('unknown Standard loss conjunction for underground upkeep')
  state['upkeep_round']=e.round_no
 import nicolette_gym as NICOLETTE
 NICOLETTE.end_turn(e,c)
 c.custom_conditions.pop('질주',None)


def finish_round(e):
 for c in getattr(e,'_time_actors',[]):
  state=c.spec.get('_burrow',{})
  if state.get('underground') and state.get('upkeep_round')!=e.round_no:
   raise ValueError('underground actor cannot skip this round upkeep by omitting its turn')

def _travel_geometry(e,c,destination,altitude,gm_distance,*,require_los=True,ignore_actors=()):
 from physical_limits import number
 destination=_point(destination);number(altitude,'destination altitude',minimum=0)
 if e.grid is None or not e.grid.inside(destination):raise ValueError('mapped destination required')
 if require_los and e.grid.blocked(c.pos,destination):raise ValueError('destination is outside clear mapped line of sight')
 old=c.spec.get('_movement_altitude',0);number(old,'current altitude',minimum=0)
 dx,dy=abs(destination[0]-c.pos[0]),abs(destination[1]-c.pos[1]);horizontal=max(dx,dy)+min(dx,dy)//2
 if gm_distance is None:
  if old!=altitude and horizontal:raise ValueError('mixed vertical/horizontal distance needs an explicit GM measurement')
  distance=abs(altitude-old) if old!=altitude else horizontal
 else:
  distance=number(gm_distance,'GM measured travel distance',minimum=0)
  if distance<max(horizontal,abs(altitude-old)):raise ValueError('GM distance cannot be shorter than mapped displacement')
 if distance<=0:raise ValueError('movement must change actual position or altitude')
 import body_state as BODY
 if not BODY.can_place(e,c,destination,origin=c.pos if require_los else None,altitude=altitude,ignore_actors=ignore_actors):
  raise ValueError('destination body is blocked, outside map or occupied at this altitude')
 return destination,distance

def free_float_destination(e,c,destination,mode,*,origin=None,distance=None,sprint_rate=None):
 if mode not in ('sky','공중/부유'):return True
 ordinary=capabilities(e,c,environment=False)
 if ordinary.pop('free_float',0)<=0:return True
 import environment_derive as ED
 # Conditional Sky can fund only the actually observed zero-gravity segment.
 origin=c.pos if origin is None else origin
 points=[origin,destination] if e.grid is None else [origin,*e.grid.line_cells(origin,destination),destination]
 if all(ED.zero_gravity(e,c,position=point) for point in points):return True
 ordinary=ED.movement(e,c,ordinary)
 sky=ordinary.get('sky',0)
 lev=ordinary.get('levitate',0) if mode=='공중/부유' and c.spec.get('_movement_altitude',0)<=ordinary.get('levitate',0)/2 else 0
 if max(sky,lev)<=0:return False
 if distance is None:return True
 from physical_limits import number
 number(distance,'actual Free Floating boundary distance',minimum=0)
 # Reuse the chosen native mode's ordinary stage/Slowed/Sprint/load consumers;
 # two sources of Sky do not invent a mixed-capability averaging decision.
 import effects_ext as EXT
 native_mode='levitate' if lev>sky else 'sky'
 limit,_=EXT.movement_profile(e,c,ordinary.get('land',c.movement),max(sky,lev),movement_mode=native_mode,capabilities=ordinary)
 limit=LOAD.movement_limit(c,limit)
 if sprint_rate is None:sprint_rate=__import__('athlete').sprint_rate(e,c) if '질주' in c.custom_conditions else False
 if sprint_rate is not False:
  if type(sprint_rate)is not str or sprint_rate not in ('0.5','1'):raise ValueError('actual paid Free Floating Sprint rate required')
  limit=M.increase(limit,sprint_rate,quantity='movement',base_id='current_capability',stage='sprint',source='maneuver/질주')
 return distance<=LOAD.movement_limit(c,limit)


def _aerial_height(e,c,mode,altitude,*,destination=None,capability_actor=None):
 if mode not in ('sky','levitate'):raise ValueError('Sky or Levitate mode required')
 if c.spec.get('_burrow',{}).get('underground'):raise ValueError('must establish a surface exit before ordinary aerial movement')
 actual=c if capability_actor is None else capability_actor
 cap=capabilities(e,actual)
 if cap.get(mode,0)<=0:raise ValueError('selected movement capability is not possessed')
 if destination is not None and not free_float_destination(e,actual,destination,mode,origin=c.pos):
  raise ValueError('Free Floating destination requires observed zero gravity')
 from physical_limits import number
 number(altitude,'destination altitude',minimum=0)
 import field_effects as FIELD
 FIELD.validate_aerial_height(e,c,altitude)
 if mode=='levitate' and altitude>cap.get('levitate',0)/2:raise ValueError('Levitate altitude exceeds half its capability')


def aerial_move(e,c,destination,*,mode,altitude,reason_text,gm_distance=None):
 import environment_change as EC
 if EC.managed(e,c):return EC.run(e,c,lambda s,a:aerial_move(s,a,destination,mode=mode,altitude=altitude,reason_text=reason_text,gm_distance=gm_distance))
 boundary(e,'aerial_move');reason(reason_text)
 _aerial_height(e,c,mode,altitude,destination=destination)
 destination,distance=_travel_geometry(e,c,destination,altitude,gm_distance)
 if not free_float_destination(e,c,destination,mode,origin=c.pos,distance=distance):
  raise ValueError('Free Floating boundary exceeds independent native Sky allowance')
 allowance=distance_budget(e,c,mode)
 if distance>allowance:raise ValueError('aerial destination exceeds movement allowance')
 if not c.on_field or c.captured or not TURN.spend(e,c,'shift','공중/부유 이동',movement=True):return False
 movement=follow_paid_path(e,c,[{'position':destination,'altitude':altitude,'gm_distance':distance}],
                           mode=mode,maximum_distance=allowance)
 if movement['steps']!=1:return False
 e.log('  '+c.name+': '+mode+' '+str(distance)+'m → '+str(destination)+' 고도 '+str(altitude),'capability/'+mode)
 return {'distance':distance,'position':destination,'altitude':altitude,'mode':mode}

def teleport_plan(e,c,destination,*,surface_contact,altitude=0,reason_text,gm_distance=None,sky_air_policy=None,maximum_distance=None,ignore_actors=()):
 reason(reason_text)
 passenger=getattr(e,'_teleport_passenger',None)
 passenger=passenger if passenger and passenger['actor_id']==c.entity_id else None
 if c.kind!='pokemon' and not passenger and __import__('warper').TELEPORT not in __import__('move_capabilities').learned_ids(c):return C.PendingDecision('source for trainer Teleporter capability')
 if type(surface_contact)is not bool:raise ValueError('actual destination surface contact must be specified')
 if c.spec.get('_burrow',{}).get('underground'):raise ValueError('underground line of sight to destination needs a separate world ruling')
 if sky_air_policy not in (None,'sky_unlimited','levitate_limit'):raise ValueError('unknown Sky/Levitate parenthetical interpretation')
 if e.encounter_active and e.round_start_seconds is None:raise ValueError('combat teleport requires an open round')
 state=c.spec.get('_teleport',{})
 if not passenger and e.encounter_active and state.get('used_round')==e.round_no:raise ValueError('Teleporter may be used only once per combat round')
 cap=capabilities(e,c);allowance=passenger['plan']['budget'] if passenger else distance_budget(e,c,'teleport')
 if maximum_distance is not None:allowance=min(allowance,C.integer(maximum_distance,'actual paid Teleport allowance',0))
 destination,distance=_travel_geometry(e,c,destination,altitude,gm_distance,ignore_actors=ignore_actors)
 if distance>allowance:raise ValueError('Teleport destination exceeds capability; Sprint cannot extend it')
 if not surface_contact:
  sky,lev=cap.get('sky',0),cap.get('levitate',0)
  if not sky and not lev:raise ValueError('aerial teleport requires Sky or Levitate')
  if sky and (not lev or altitude>lev/2):
   if sky_air_policy is None:return C.PendingDecision('explicit Sky vs Levitate-height parenthetical interpretation')
   if sky_air_policy=='levitate_limit' and (not lev or altitude>lev/2):raise ValueError('selected Teleporter interpretation requires Levitate height limit')
  elif not sky and altitude>lev/2:raise ValueError('aerial teleport exceeds Levitate height limit')
 return {'mode':'teleport','path':(c.pos,destination),'distance':distance,'budget':allowance,
         'origin_altitude':c.spec.get('_movement_altitude',0),'origin_underground':False,
         'parameters':{'surface_contact':surface_contact,'altitude':altitude,'reason_text':reason_text,
                       'gm_distance':gm_distance,'sky_air_policy':sky_air_policy}}


def teleport(e,c,destination,*,surface_contact,altitude=0,reason_text,gm_distance=None,sky_air_policy=None):
 import environment_change as EC
 if EC.managed(e,c):return EC.run(e,c,lambda s,a:teleport(s,a,destination,surface_contact=surface_contact,altitude=altitude,reason_text=reason_text,gm_distance=gm_distance,sky_air_policy=sky_air_policy))
 boundary(e,'teleport')
 plan=teleport_plan(e,c,destination,surface_contact=surface_contact,altitude=altitude,reason_text=reason_text,gm_distance=gm_distance,sky_air_policy=sky_air_policy)
 if isinstance(plan,C.PendingDecision):return plan
 if not c.on_field or c.captured or not TURN.spend(e,c,'shift','순간이동',movement=True):return False
 result=follow_paid_transfer(e,c,plan)
 return {k:v for k,v in result.items() if k not in ('steps','mode')} if result['steps'] else False


def _paid_progress(c,path,progress):
 if progress is None:return
 if not progress:
  progress.update(path=deepcopy(path),next=0,distance=0,position=c.pos,effects=[],
                  altitude=c.spec.get('_movement_altitude',0),diagonals=getattr(c,'_diagonal_steps',0),phase='ready')
 if progress.get('path')!=path:raise ValueError('cannot replace an actual paid movement path')
 if progress.get('phase') in ('entry_pending','reaction_pending'):
  raise ValueError('actual movement pending receipts require engine validation')
 if progress.get('phase') not in ('ready','complete'):
  raise ValueError('actual movement entry/departure effects interrupted; resolve their actual producer before continuation')
 if (progress['position']!=c.pos or progress['altitude']!=c.spec.get('_movement_altitude',0)
     or progress['diagonals']!=getattr(c,'_diagonal_steps',0)):
  raise ValueError('actual movement prefix no longer matches current position, altitude or diagonals')
 C.integer(progress['next'],'actual movement prefix',0,len(path))


def _paid_receipts(e,progress):
 if progress is not None and progress.get('phase') in ('entry_pending','reaction_pending'):
  for event_id in progress.get('marksman_events',[]):
   __import__('move_completion').require_returned_event(e,event_id)
  for identity in progress.get('native_actions',[]):
   row=getattr(e,'_native_action_resolutions',{}).get(identity)
   if row is None:raise ValueError('paid movement lost its actual nested action receipt')
   if row['phase']!='producer_returned' or any(t['status']!='completed' for t in row['triggers']):
    raise ValueError('paid movement waits for its actual nested action and Stamina choice')
  if ACTION.pending_resolution_effects(e,{'effects':progress['effects']}):
   raise ValueError('actual movement entry effects interrupted; resolve their actual receipts before continuation')
  progress['phase']='ready'


def _paid_departure(e,c,q,height,progress,*,pass_scope=None,chain_scope=None,disengage_scope=None):
 origin=c.pos;altitude=c.spec.get('_movement_altitude',0)
 permitted=observe_paid_departure(e,c,progress,lambda:departure(e,c,q,height,pass_scope=pass_scope,chain_scope=chain_scope,
  **({'disengage_scope':disengage_scope} if disengage_scope is not None else {})))
 return permitted and c.pos==origin and c.spec.get('_movement_altitude',0)==altitude


def observe_paid_departure(e,c,progress,resolve):
 """Observe real departure effects independently of mapped/abstract geometry."""
 receipts=set(getattr(e,'_effect_dispatch_receipts',{}))
 native_before=set(getattr(e,'_native_action_resolutions',{}))
 if progress is not None:progress['phase']='departing'
 permitted=resolve()
 if progress is not None:progress['phase']='ready'
 if not permitted:return False
 observed=[key for key in getattr(e,'_effect_dispatch_receipts',{}) if key not in receipts]
 if progress is not None:progress['effects'].extend(observed)
 if ACTION.pending_resolution_effects(e,{'effects':observed}):
  if progress is not None:progress['phase']='reaction_pending'
  return False
 if progress is not None:
  outstanding=[identity for identity,row in getattr(e,'_native_action_resolutions',{}).items()
               if identity not in native_before and row['phase']!='resolving'
               and any(t['status']!='completed' for t in row['triggers'])]
  if outstanding:
   progress.setdefault('native_actions',[]).extend(outstanding)
   progress['phase']='reaction_pending'
   return False
 ACTION.ensure_resolutions_clear(e)
 return True


def _paid_entry(e,c,progress,*,surface,reconcile=False,previous_position=None):
 position=c.pos;altitude=c.spec.get('_movement_altitude',0)
 import survivalist_features as SURVIVAL
 SURVIVAL.position_changed(e,c,event='native movement entry')
 import body_modes as BODY_MODES
 BODY_MODES.sync_shadows(e)
 import marsupial_state as MARSUPIAL
 MARSUPIAL.sync(e)
 receipts=set(getattr(e,'_effect_dispatch_receipts',{}))
 if reconcile:
  import effect_lifetime_policy as LIFETIMES
  LIFETIMES.reconcile(e)
 __import__('ability_exchange_contracts').refresh(e)
 __import__('ability_control_contracts').refresh(e)
 pending=None
 if surface and c.pos==position and c.spec.get('_movement_altitude',0)==altitude:
  import effects_ext as EXT
  pending=EXT.on_enter_cell(e,c,c.pos,previous_position=previous_position)
 elif c.pos==position and c.spec.get('_movement_altitude',0)==altitude:
  pending=__import__('marksman').moved(e,c)
 observed=[key for key in getattr(e,'_effect_dispatch_receipts',{}) if key not in receipts]
 if progress is not None:
  progress['effects'].extend(observed);progress['phase']='ready'
 if isinstance(pending,C.PendingDecision):
  if progress is not None:
   progress['phase']='entry_pending'
   if getattr(e,'_marksman_attack',None) and getattr(e,'_passive_pending',None):
    progress.setdefault('marksman_events',[]).append(e._passive_pending)
  return False
 if ACTION.pending_resolution_effects(e,{'effects':observed}):
  if progress is not None:progress['phase']='entry_pending'
  return False
 return c.pos==position and c.spec.get('_movement_altitude',0)==altitude and TURN.can_act(e,c) and TURN.movement_permission(e,c)


def follow_paid_transfer(e,c,plan,*,progress=None):
 """Actual native tunnel/Teleport transfer, after its real producer paid."""
 import field_effects as FIELD
 import living_weapon as LIVING
 cursor={} if progress is None else progress
 _paid_receipts(e,cursor);_paid_progress(c,plan['path'],cursor)
 steps=len(plan['path'])-1
 if cursor['next'] not in (0,steps):raise ValueError('actual native transfer cannot contain a fabricated partial path')
 if not steps:
  cursor['phase']='complete'
  return {'distance':0,'steps':0,'position':c.pos,'mode':plan['mode']}
 if cursor['next']==steps:
  cursor['phase']='complete';return cursor['result']
 if plan['path'][0]!=c.pos or plan.get('origin_altitude',c.spec.get('_movement_altitude',0))!=c.spec.get('_movement_altitude',0):
  raise ValueError('actual native transfer origin changed after observation')
 mode=plan['mode'];parameters=plan['parameters']
 def validate():
  if mode=='burrow':return burrow_plan(e,c,plan['path'],maximum_distance=plan['budget'],**parameters)
  if mode=='teleport':return teleport_plan(e,c,plan['path'][-1],maximum_distance=plan['budget'],**parameters)
  raise ValueError('actual Burrow or Teleport plan required')
 actual=validate()
 if isinstance(actual,C.PendingDecision):raise ValueError(str(actual))
 if not LIVING.can_shift(e,c,actual['distance'],movement_mode=mode):
  return {'distance':0,'steps':0,'position':c.pos,'mode':mode}
 height=parameters.get('altitude',0);destination=plan['path'][-1]
 # Adopted Dataninja FAQ p18: instantaneous Teleport does not provoke.
 # Other transfers and ordinary Shifting still use the existing AoO owner.
 if mode!='teleport' and not _paid_departure(e,c,destination,height,cursor):
  return {'distance':0,'steps':0,'position':c.pos,'mode':mode}
 actual=validate()
 if isinstance(actual,C.PendingDecision):raise ValueError(str(actual))
 if not LIVING.can_shift(e,c,actual['distance'],movement_mode=mode):
  return {'distance':0,'steps':0,'position':c.pos,'mode':mode}
 origin=c.pos;origin_altitude=c.spec.get('_movement_altitude',0);origin_contact=FIELD.touches_ground(c);c.pos=destination
 if mode=='burrow':
  c._diagonal_steps=actual['diagonals'];c.airborne=False;consume_sprint(c)
  size=c.spec['size'];surface=parameters['surface'];path=actual['path']
  c.spec.setdefault('_burrow',{}).update(underground=not surface,last_path=path,body_size=size,reason=parameters['reason_text'])
  import burrow_tunnels as TUNNELS
  TUNNELS.record(e,c,actual,surface=surface)
  location='' if getattr(e,'_relative_mover',None)==c.entity_id else ' → '+str(c.pos)
  e.log('  '+c.name+': 지중 이동 '+str(actual['distance'])+'m'+location,'capability/burrow')
  result={'distance':actual['distance'],'position':c.pos,'underground':not surface,'tunnel_size':size}
 else:
  surface=parameters['surface_contact'];c.spec['_movement_altitude']=height;c.airborne=not surface
  if not getattr(e,'_teleport_passenger',None):c.spec['_teleport']={'used_round':e.round_no if e.encounter_active else None,'surface_contact':surface,
      'reason':parameters['reason_text'],'sky_air_policy':parameters['sky_air_policy']}
  location='' if getattr(e,'_relative_mover',None)==c.entity_id else ' → '+str(c.pos)
  e.log('  '+c.name+': 순간이동 '+str(actual['distance'])+'m'+location,'capability/teleporter')
  result={'distance':actual['distance'],'position':c.pos,'altitude':height,'surface_contact':surface}
 result.update(steps=steps,mode=mode)
 LIVING.shifted(e,c,actual['distance'])
 cursor.update(next=steps,distance=actual['distance'],position=c.pos,altitude=c.spec.get('_movement_altitude',0),
               diagonals=getattr(c,'_diagonal_steps',0),phase='entering',result=result)
 if _paid_entry(e,c,cursor,surface=surface,reconcile=mode=='teleport',previous_position=origin if origin_altitude==height and origin_contact==FIELD.touches_ground(c) else None):cursor['phase']='complete'
 return result


def exchange_positions(e,first,second,*,source):
 """Actual instantaneous two-body exchange; both placements are checked first."""
 import body_state as BODY,world_entities as W
 W.require_actors(e,first,second)
 if source!=__import__('warper').SWITCH or first is second:raise ValueError('actual Ally Switch pair required')
 origins=(first.pos,second.pos);heights=[c.spec.get('_movement_altitude',0) for c in (first,second)]
 for actor,destination,height in ((first,origins[1],heights[1]),(second,origins[0],heights[0])):
  if not BODY.can_place(e,actor,destination,origin=actor.pos,ignore_actors=(first,second),altitude=height):raise ValueError('Ally Switch actual exchanged body placement blocked')
 first.pos,second.pos=origins[1],origins[0]
 for actor,height in zip((first,second),reversed(heights)):
  actor.spec['_movement_altitude']=height;actor.airborne=height>0
  __import__('living_weapon').sync(e,actor)
  _paid_entry(e,actor,None,surface=height==0,reconcile=True)
 return {'source':source,'first':first.pos,'second':second.pos}


def consume_sprint(c):
 state=c.custom_conditions.get('질주')
 if not isinstance(state,dict) or state.get('source_policy')!='ch07_turn':c.custom_conditions.pop('질주',None)

def entry_mode(c,mode,*,altitude=None):
 """Commit the actual destination plane before any cell-entry consumer."""
 if altitude is None:c.airborne=mode=='공중/부유'
 else:
  c.spec['_movement_altitude']=altitude
  c.airborne=altitude>0 and mode!='shadow_surface'


def follow_paid_path(e,c,path,*,mode,maximum_distance,action_owner=None,progress=None,pass_scope=None,chain_scope=None,movement_mode=None,disengage_scope=None):
 """Shared physical movement after a producer has paid its actual action."""
 import body_state as BODY,effects_ext as EXT,control_mount as MOUNT,action_lifecycle as ACTION,field_effects as FIELD
 import living_weapon as LIVING
 action_owner=c if action_owner is None else action_owner
 C.integer(maximum_distance,'actual movement allowance',0)
 import type_ace as TA
 maximum_distance=TA.movement_allowance(c,mode,maximum_distance)
 aerial=mode in ('sky','levitate','shadow_surface')
 shared_mode=movement_mode or (mode if mode in MODES else 'land' if mode in ('육상','shadow_surface') else None)
 if mode=='shadow_surface':
  import body_modes as BODY_MODES
  if not BODY_MODES.flat(c):raise ValueError('surface path requires actual Shadow Meld')
 if aerial:
  from physical_limits import number
  points=[]
  for node in path:
   if type(node)is not dict or set(node) not in ({'position','altitude'},{'position','altitude','gm_distance'}):
    raise ValueError('actual aerial position, altitude and optional measured distance required')
   points.append(dict(node,position=_point(node['position']),
                      altitude=number(node['altitude'],'destination altitude',minimum=0)))
  path=points
 else:path=[_point(node[:2]) for node in path]
 ignored=()
 if pass_scope is not None:
  import pass_moves as PASS
  ignored=PASS.movement_authority(e,c,pass_scope,path,mode)
 if chain_scope is not None:
  import dynamic_chain_moves as CHAIN
  CHAIN.movement_authority(e,c,chain_scope,path,mode)
 def geometry(node):
  if not aerial:
   q=_point(node[:2]);step,diagonals=step_cost(c.pos,q,getattr(c,'_diagonal_steps',0))
   return q,c.spec.get('_movement_altitude',0),step+slow_terrain_penalty(e,c,q,mode,step=step),diagonals
  q=node['position'];height=node['altitude']
  if mode!='shadow_surface':_aerial_height(e,c,mode,height,destination=q)
  diagonals=getattr(c,'_diagonal_steps',0)
  dx,dy=abs(q[0]-c.pos[0]),abs(q[1]-c.pos[1])
  measured=node.get('gm_distance')
  if measured is None and height==c.spec.get('_movement_altitude',0):
   measured=max(dx,dy)+(diagonals+min(dx,dy))//2-diagonals//2
  _,cost=_travel_geometry(e,c,q,height,measured)
  return q,height,cost,diagonals+min(dx,dy)
 _paid_receipts(e,progress);_paid_progress(c,path,progress)
 # A producer may own several cell-local receipts within one paid movement.
 free_float_distance_offset=0 if progress is None else progress.get('free_float_distance_offset',0)
 C.integer(free_float_distance_offset,'actual parent movement charged prefix',0)
 free_float_sprint=None
 if (movement_mode or mode) in ('sky','공중/부유') and capabilities(e,c,environment=False).get('free_float',0)>0:
  # consume_sprint removes the one-movement flag after entry, not its paid rate.
  # Keep only that rate with this path; capabilities and gravity remain live.
  if progress is not None and 'free_float_sprint_rate' in progress:free_float_sprint=progress['free_float_sprint_rate']
  else:
   free_float_sprint=__import__('athlete').sprint_rate(e,c) if '질주' in c.custom_conditions else False
   if progress is not None:progress['free_float_sprint_rate']=free_float_sprint
 import electro_shot as ELECTRO
 active_exits={} if progress is None else ELECTRO.restore_exits(e,c,progress)
 physical_distance=0 if progress is None else progress['distance']
 spent=0 if progress is None else progress.get('charged_distance',physical_distance)
 moved=0 if progress is None else progress['next']
 for node in path[moved:]:
  q=node['position'] if aerial else _point(node[:2])
  height=node['altitude'] if aerial else c.spec.get('_movement_altitude',0)
  origin=c.pos;altitude=c.spec.get('_movement_altitude',0)
  commander_ignored=__import__('commander_orders').path_passers(e,c,path[moved:],mode=mode,remaining=maximum_distance-spent)
  actual_ignored=tuple(ignored)+tuple(x for x in commander_ignored if x not in ignored)
  import map_terrain as TERRAIN
  if mode=='shadow_surface' and not BODY_MODES.shadow_contact(e,c,node):break
  if not TERRAIN.can_travel(e,c,q,mode,altitude=height,movement_mode=movement_mode) or not BODY.can_place(e,c,q,origin=c.pos,ignore_actors=actual_ignored,**({'altitude':height} if aerial else {})):break
  origin_diagonals=getattr(c,'_diagonal_steps',0)
  q,height,cost,diagonals=geometry(node)
  physical_cost=cost
  exit_candidate=ELECTRO.exit_step(e,c,path,moved,active_exits,movement_mode=shared_mode,progress=progress)
  if exit_candidate is not None:cost=0
  if spent+cost>maximum_distance:break
  if not free_float_destination(e,c,q,movement_mode or mode,origin=origin,distance=free_float_distance_offset+spent+cost,sprint_rate=free_float_sprint):break
  if not LIVING.can_shift(e,c,cost,movement_mode=shared_mode):break
  if not _paid_departure(e,c,q,height,progress,pass_scope=pass_scope,chain_scope=chain_scope,disengage_scope=disengage_scope):break
  # Reactions can move the actor or change the destination body/terrain.
  if c.pos!=origin or c.spec.get('_movement_altitude',0)!=altitude:break
  if mode=='shadow_surface' and not BODY_MODES.shadow_contact(e,c,node):break
  if not TERRAIN.can_travel(e,c,q,mode,altitude=height,movement_mode=movement_mode) or not BODY.can_place(e,c,q,origin=origin,ignore_actors=actual_ignored,**({'altitude':height} if aerial else {})):break
  origin_diagonals=getattr(c,'_diagonal_steps',0)
  q,height,cost,diagonals=geometry(node)
  physical_cost=cost
  exit_candidate=ELECTRO.exit_step(e,c,path,moved,active_exits,movement_mode=shared_mode,progress=progress)
  if exit_candidate is not None:cost=0
  if spent+cost>maximum_distance:break
  if not free_float_destination(e,c,q,movement_mode or mode,origin=origin,distance=free_float_distance_offset+spent+cost,sprint_rate=free_float_sprint):break
  if not LIVING.can_shift(e,c,cost,movement_mode=shared_mode):break
  if action_owner is not c and action_owner.spec.get('mount_id')!=c.entity_id:break
  departure_distance=physical_cost if aerial else step_cost(origin,q,getattr(c,'_diagonal_steps',0))[0]
  origin_contact=FIELD.touches_ground(c)
  c._diagonal_steps=diagonals;c.pos=q
  if pass_scope is not None:__import__('native_path_area_moves').roller_entry(e,c,pass_scope,q)
  __import__('commander_orders').shifted(e,c,[q])
  __import__('ninja').departed(e,c,origin,distance=departure_distance)
  import burrow_tunnels as TUNNELS
  TUNNELS.enter(e,c,mode)
  entry_mode(c,mode,altitude=height if aerial else None)
  active_exits=ELECTRO.commit_step(e,progress,c,exit_candidate,moved,physical_cost,path,origin,altitude,height,origin_diagonals,diagonals)
  if aerial:
   consume_sprint(c)
  MOUNT.sync(e,c)
  LIVING.shifted(e,c,cost)
  __import__('ability_exchange_contracts').refresh(e)
  __import__('ability_control_contracts').crossing(e,c,origin,q)
  spent+=cost;physical_distance+=physical_cost;moved+=1
  TA.moved(c,cost)
  if progress is not None:
   progress.update(next=moved,distance=physical_distance,position=c.pos,altitude=c.spec.get('_movement_altitude',0),
                   diagonals=c._diagonal_steps,phase='entering')
   if spent!=physical_distance:progress['charged_distance']=spent
  if c.pos!=q or c.spec.get('_movement_altitude',0)!=height or c.fainted or not c.on_field or c.captured:break
  if not _paid_entry(e,c,progress,surface=not aerial or height==0 or mode=='shadow_surface',reconcile=aerial,previous_position=origin if altitude==height and origin_contact==FIELD.touches_ground(c) else None):break
 if progress is not None and moved==len(path) and progress['phase']=='ready':progress['phase']='complete'
 result={'distance':physical_distance,'steps':moved,'position':c.pos,'mode':mode}
 if spent!=physical_distance:result['charged_distance']=spent
 if aerial:result['altitude']=c.spec.get('_movement_altitude',0)
 return result

def departure(e,c,destination,altitude,*,pass_scope=None,chain_scope=None,disengage_scope=None):
 # Native opportunity attacks resolve while the mover is still in its old cell.
 # A Shift is not automatically the separate one-metre Disengage maneuver.
 import body_state as BODY
 old_altitude=c.spec.get('_movement_altitude',0)
 enemies=[other for other in TURN.adjacent_enemies(e,c) if abs(other.spec.get('_movement_altitude',0)-old_altitude)<=1 and (not BODY.adjacent(other,c,right_position=destination) or abs(other.spec.get('_movement_altitude',0)-altitude)>1)]
 if disengage_scope is not None:
  __import__('move_defense_reactions').perception_disengage_authority(e,c,disengage_scope,destination,altitude)
 elif getattr(e,'_type_ace_disengage',None) is c:
  __import__('type_ace').mark_departure(e,c,destination)
 elif pass_scope is not None:
  import pass_moves as PASS
  PASS.movement_authority(e,c,pass_scope,[destination],'land')
 elif chain_scope is not None:
  import dynamic_chain_moves as CHAIN
  exempt=CHAIN.movement_authority(e,c,chain_scope,[destination],None)
  enemies=[] if exempt is None else [other for other in enemies if other is not exempt]
  if enemies:TURN.trigger_aoo(e,c,'인접 칸 밖으로 이동',enemies)
 elif enemies:TURN.trigger_aoo(e,c,'인접 칸 밖으로 이동',enemies)
 permitted=TURN.can_act(e,c) and TURN.movement_permission(e,c)
 if permitted:
  import sound_state as SOUND
  SOUND.observe(e,c,'movement')
 return permitted


# These additional distinct labels occur literally in the species Naturewalk column.
# They are not aliases for Ocean, Forest or Wetland; source spelling errors are rejected.
NATUREWALK_ADDITIONAL_TERRAINS=('해변','민물','타이가')

def terrain_type(value):
 import survivalist_features as SURVIVAL
 if value in NATUREWALK_ADDITIONAL_TERRAINS:return value
 return SURVIVAL.terrain(value)


def _naturewalk_values(value):
 import re
 if value is None or value=='':return ()
 if isinstance(value,str):values=re.split(r'\s*(?:,|과|와|\band\b|/)\s*',value,flags=re.IGNORECASE)
 elif isinstance(value,(list,tuple)):values=value
 else:raise ValueError('Naturewalk requires explicit terrain labels')
 result=[]
 for part in values:
  if not isinstance(part,str):raise ValueError('Naturewalk requires explicit terrain labels')
  result.append(terrain_type(part.strip()))
 return tuple(result)


def observe_cell_terrain(e,cells,terrains,reason_text):
 """Record actual cell terrain; no terrain is inferred from artwork or names."""
 import survivalist_features as SURVIVAL
 reason(reason_text)
 if e.grid is None:raise ValueError('cell terrain observation needs an actual grid')
 if not isinstance(cells,(list,tuple)) or not cells:raise ValueError('actual observed cells required')
 points=tuple(_point(cell) for cell in cells)
 if len(set(points))!=len(points) or any(not e.grid.inside(cell) for cell in points):raise ValueError('distinct in-bounds terrain cells required')
 if not isinstance(terrains,(list,tuple)) or not terrains:raise ValueError('known actual terrain types required')
 values=tuple(terrain_type(value) for value in terrains)
 if len(set(values))!=len(values):raise ValueError('duplicate cell terrain classification')
 mapping=dict(getattr(e.grid,'terrain_types',{}));observations=dict(getattr(e.grid,'terrain_observations',{}))
 for x,y in points:
  key=str(x)+','+str(y);mapping[key]=list(values);observations[key]={'reason':reason_text,'source':'GM actual cell terrain observation'}
 e.grid.terrain_types=mapping;e.grid.terrain_observations=observations
 for actor in e.everyone:
  if actor.location['kind']=='grid' and tuple(actor.pos) in points:
   SURVIVAL.position_changed(e,actor,event='GM cell terrain observation')
 return {str(x)+','+str(y):list(values) for x,y in points}


def naturewalk_terrains(e,c):
 import csv_item_form_contracts as CSV_FORMS
 provider=CSV_FORMS.naturewalk_provider(e,c)
 if provider is not c:return naturewalk_terrains(e,provider)
 import re
 import survivalist_features as SURVIVAL
 result=set()
 import state_grants as GRANTS
 candidates=[value for value in GRANTS.effective(c,'capabilities',include_suppressed=True)
             if re.match(r'^(?:자연걸음|Naturewalk|Nature Walk)(?:\s|\(|$)',str(value).removeprefix('capability/'),re.IGNORECASE)]
 for value in GRANTS.effective_capabilities(c,only=candidates):
  value=str(value).removeprefix('capability/')
  match=re.fullmatch(r'(?:자연걸음|Naturewalk|Nature Walk)\s*\(([^)]+)\)',value,re.IGNORECASE)
  if not match and re.match(r'^(?:자연걸음|Naturewalk|Nature Walk)(?:\s|\(|$)',value,re.IGNORECASE):raise ValueError('Naturewalk requires explicit parenthesized terrain labels')
  if match:
   if e.r._selected_rule('capability/자연걸음')!='capability/자연걸음':raise ValueError('selected Naturewalk variant needs explicit source policy')
   result.update(_naturewalk_values(match.group(1)))
 raw=c.spec.get('naturewalk')
 if raw:
  if e.r._selected_rule('capability/자연걸음')!='capability/자연걸음':raise ValueError('selected Naturewalk variant needs explicit source policy')
  result.update(_naturewalk_values(raw))
 if c.kind=='trainer':
  import contest_features as FEATURES
  if FEATURES.owned(c,SURVIVAL.SURVIVALIST):
   choices=SURVIVAL.selected(e,c)
   if choices and e.r._selected_rule('capability/자연걸음')!='capability/자연걸음':raise ValueError('selected Naturewalk variant needs explicit source policy')
   result.update(choices)
 return frozenset(result)


def ordinary_terrain(e,c,cell):
 """Whether sourced Naturewalk covers an observed cell's terrain types."""
 if e.grid is None:return False
 point=_point(cell)
 if not e.grid.inside(point):raise ValueError('terrain query outside grid')
 types=getattr(e.grid,'terrain_types',{}).get(str(point[0])+','+str(point[1]))
 if types is None:return False
 types=__import__('survivalist_class').effective_cell_terrains(e,c,types)
 known=naturewalk_terrains(e,c)
 if not isinstance(types,list) or not types:raise ValueError("observed terrain requires explicit types")
 return set(types).issubset(known)


def slow_terrain_penalty(e,c,cell,mode,*,step=1):
 import map_terrain as TERRAIN
 return step*(TERRAIN.slow_multiplier(e,c,cell,mode)-1)
