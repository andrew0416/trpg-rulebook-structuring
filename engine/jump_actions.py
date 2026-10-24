"""PTK High/Long Jump on actual positions, whole-Shift cost and GM context.

ch06:133-135; ch07:130 allows the whole Shift alternative. The shared travel
budget alternative and run-up bonuses are separate capabilities, not invented.
A failed check stores its result for a GM world response, never rerolls it.
"""
from copy import deepcopy
import common_checks as C
import common_action_checks as COMMON
import movement_actions as M
import turn as TURN
import trainer_capabilities as TRAINER
from physical_limits import number

def limits(c):
 mv=TRAINER.values(c) if c.spec.get('movement_basis')=='trainer_base' else c.spec.get('movement') or {}
 if c.kind=='trainer' and c.spec.get('movement_basis')=='base':mv=TRAINER.jump_bonuses(c,mv)
 if c.spec.get('movement_basis') in ('base','trainer_base'):
  import move_capabilities as MOVE_CAPABILITIES
  mv=MOVE_CAPABILITIES.numeric_values(c,mv,('high_jump','long_jump'))
 else:
  import move_capabilities as MOVE_CAPABILITIES
  mv=MOVE_CAPABILITIES.current_values(c,mv,('high_jump','long_jump'))
 import pokemon_capability_edges as CAP_EDGES
 mv=CAP_EDGES.apply(c,mv)
 import csv_item_capability_contracts as CSV_CAPABILITIES
 bonuses=CSV_CAPABILITIES.muscle_jump_bonus(c)
 survival=__import__('survivalist_class').jump_bonus(c)
 mv={key:(mv.get(key) or 0)+bonuses[key]+survival[key] for key in ('high_jump','long_jump')}
 import csv_item_form_contracts as CSV_FORMS
 mv=CSV_FORMS.jump_projection(c,mv)
 if c.kind=='pokemon':
  import baby_templates as BABY
  mv=BABY.capability_values(c,mv,('high_jump','long_jump'))
 bonus=__import__('jump_move_actions').bonus(c)
 return {key:number(mv.get(key),key,minimum=0)+bonus for key in ('high_jump','long_jump')}

def _fall_options(options):
 if type(options) is not dict:raise ValueError('explicit native falling options required for lower landing')
 if set(options)&{'action_id','meters','intentional','same_jump_id','reason'}:raise ValueError('actual jump owns fall identity, height and intentionality')

def _landing_fall(e,c,record,jump_id,options):
 _fall_options(options)
 drop=record['launch_altitude']+record['apex_height']-record['landing_altitude']
 C.integer(drop,'actual jump descent metres',0)
 identity='jump-fall:'+jump_id;record['fall_pending']=True
 outcome=e.falling_damage(c,action_id=identity,meters=drop,intentional=True,same_jump_id=jump_id,reason=record['reason'],**options)
 actual=c.spec.get('_fall_events',{}).get(identity)
 if actual is not None:record['falling']=deepcopy(actual);record.pop('fall_pending',None)
 if isinstance(outcome,C.PendingDecision):return outcome
 record.pop('fall_pending',None)
 return record

def _landing_intent(destination,apex_height,landing_altitude,difficult,difficulty_skill,difficulty_dc,boost,reason_text,gm_distance,clear_path,running_start,running_reason,running_bonus_included,wall_run):
 return dict(destination=tuple(destination),apex_height=apex_height,landing_altitude=landing_altitude,
  difficult=difficult,difficulty_skill=difficulty_skill,difficulty_dc=difficulty_dc,boost=boost,
  reason=reason_text,gm_distance=gm_distance,clear_path=clear_path,running_start=running_start,
  running_reason=running_reason,running_bonus_included=running_bonus_included,wall_run=deepcopy(wall_run))


def _continue_landing(e,c,record,jump_id,fall_options):
 """Resume the already-paid jump, observing existing native receipt owners."""
 path=[dict(position=record['destination'],altitude=record['landing_altitude'])]
 progress=record.setdefault('movement',{})
 M._paid_receipts(e,progress);M._paid_progress(c,path,progress)
 if not progress['next']:
  def validate():
   return M._travel_geometry(e,c,record['destination'],record['landing_altitude'],record['movement_intent']['gm_distance'],require_los=False)
  validate()
  if not M._paid_departure(e,c,record['destination'],record['landing_altitude'],progress):
   if progress['phase']=='reaction_pending':return C.PendingDecision('actual jump departure action must finish before landing')
   for key in ('movement_pending','movement','movement_intent'):record.pop(key,None)
   return False
  validate()
  c.pos=record['destination'];c.spec['_movement_altitude']=record['landing_altitude'];c.airborne=False;record['landed']=True
  progress.update(next=1,position=c.pos,altitude=c.spec.get('_movement_altitude',0),diagonals=getattr(c,'_diagonal_steps',0),phase='entering')
  e.log('  '+c.name+': 점프 → '+str(c.pos)+' 고도 '+str(record['landing_altitude']),'capability/jump')
  if not M._paid_entry(e,c,progress,surface=True):return C.PendingDecision('actual jump landing effects must finish')
 progress['phase']='complete'
 for key in ('movement_pending','movement','movement_intent'):record.pop(key,None)
 __import__('tumbler').quick_shift(e,c,record.get('quick_gymnastics'))
 if 'launch_altitude' in record:return _landing_fall(e,c,record,jump_id,fall_options)
 return record


def jump(e,c,destination,*,jump_id,apex_height=0,landing_altitude=0,difficult=None,difficulty_skill=None,difficulty_dc=None,difficulty_options=None,boost=None,boost_options=None,reason_text,gm_distance=None,clear_path=None,running_start=False,running_reason=None,running_bonus_included=None,wall_run=None,fall_options=None,_wall_staged=False,_prepaid_move=None):
 if (wall_run is not None or fall_options is not None) and not _wall_staged:
  options={key:value for key,value in locals().items() if key not in ('e','c','destination','_wall_staged')}
  import wallrunner as WALL
  return WALL.run_jump(e,c,destination,options)
 M.boundary(e,'jump');M.reason(reason_text);M.reason(jump_id)
 prepaid=__import__('jump_move_actions').prepaid(e,c,_prepaid_move)
 if c.spec.get('_jump_pending'):return C.PendingDecision('GM consequence of the preceding jump check')
 attempts=c.spec.get('_jump_attempts',{})
 if any(uid!=jump_id and record.get('movement_pending') for uid,record in attempts.items()):
  return C.PendingDecision('finish the already paid jump before starting another attempt')
 previous=attempts.get(jump_id)
 if previous and previous.get('movement_pending'):
  intent=_landing_intent(destination,apex_height,landing_altitude,difficult,difficulty_skill,difficulty_dc,boost,reason_text,gm_distance,clear_path,running_start,running_reason,running_bonus_included,wall_run)
  if intent!=previous['movement_intent']:raise ValueError('cannot change an already paid jump declaration')
  return _continue_landing(e,c,previous,jump_id,fall_options)
 if previous and previous.get('fall_pending'):
  if tuple(destination)!=previous['destination'] or landing_altitude!=previous['landing_altitude'] or apex_height!=previous['apex_height'] or boost!=previous['boost'] or wall_run!=previous.get('wall_run',{}).get('declaration') or c.pos!=previous['destination'] or c.spec.get('_movement_altitude',0)!=landing_altitude:raise ValueError('resume the same actually landed jump and fall')
  return _landing_fall(e,c,previous,jump_id,fall_options)
 if jump_id in attempts:raise ValueError('jump attempt identity already resolved; cannot reroll or stack boost')
 inflight=c.spec.get('_jump_inflight')
 if inflight and inflight['jump_id']!=jump_id:return C.PendingDecision('finish the observed jump before starting another attempt')
 if type(difficult)is not bool:return C.PendingDecision('GM decision whether the jump is unusually difficult')
 if boost not in (None,'high_jump','long_jump'):raise ValueError('choose only one jump capability to increase')
 if c.spec.get('_burrow',{}).get('underground'):raise ValueError('jump requires a surfaced origin')
 if clear_path is not True:return C.PendingDecision('GM confirmation of actual jump arc and landing surface clearance')
 wall=None;origin=c
 if wall_run is not None:
  import wallrunner as WALL
  wall=WALL.prepare(e,c,wall_run,inflight)
  if isinstance(wall,C.PendingDecision):return wall
  origin=WALL.launch(c,wall)
 cap=TRAINER.for_jump(c,limits(c),running_start=running_start,running_reason=running_reason,running_bonus_included=running_bonus_included);number(apex_height,'apex rise above origin',minimum=0);number(landing_altitude,'landing altitude',minimum=0)
 old_altitude=origin.spec.get('_movement_altitude',0)
 descending=landing_altitude<old_altitude
 if descending and fall_options is None:return C.PendingDecision('lower landing needs explicit native falling options')
 if fall_options is not None and (not descending or type(fall_options) is not dict):raise ValueError('native falling options require an actual lower landing')
 if descending:
  _fall_options(fall_options)
  C.integer(old_altitude+apex_height-landing_altitude,'actual jump descent metres',0)
 destination,total=M._travel_geometry(e,origin,destination,landing_altitude,gm_distance,require_los=False)
 intent=_landing_intent(destination,apex_height,landing_altitude,difficult,difficulty_skill,difficulty_dc,boost,reason_text,gm_distance,clear_path,running_start,running_reason,running_bonus_included,wall_run)
 dx,dy=abs(origin.pos[0]-destination[0]),abs(origin.pos[1]-destination[1]);long_distance=max(dx,dy)+min(dx,dy)//2
 if apex_height<max(0,landing_altitude-old_altitude):raise ValueError('apex cannot lie below the landing surface')
 if gm_distance is not None:long_distance=max(long_distance,number(gm_distance,'GM jump distance',minimum=0)) if landing_altitude==old_altitude else long_distance
 requested={'high_jump':apex_height,'long_jump':long_distance}
 if any(requested[key]>cap[key]+int(boost==key) and not (key=='high_jump' and TRAINER.short_high_jump(c,requested[key],cap[key])) for key in cap):raise ValueError('requested jump exceeds capability even with the one allowed increase')
 boost_options=dict(boost_options or {});difficulty_options=dict(difficulty_options or {})
 if boost is None and boost_options:raise ValueError('boost roll options require a declared increase attempt')
 if not difficult and (difficulty_skill is not None or difficulty_dc is not None or difficulty_options):raise ValueError('ordinary within-capability jump has no task roll')
 plans=[]
 if boost:plans.append(('boost','곡예',16,boost_options))
 if difficult:
  if difficulty_skill is None or difficulty_dc is None:return C.PendingDecision('GM skill and DC for the difficult jump')
  C.integer(difficulty_dc,'difficult jump DC');plans.append(('difficulty',difficulty_skill,difficulty_dc,difficulty_options))
 ids=[opts.get('roll_id') for _,_,_,opts in plans if opts.get('roll_id') is not None]
 if len(ids)!=len(set(ids)):raise ValueError('increase check and difficult jump check need distinct roll identities')
 import skill_feature_actions as SF
 featured=any(opts.get('feature') is not None for _,_,_,opts in plans)
 for _,skill,dc,opts in plans:
  prepared=SF.prepared_for_sequence(e,c,skill,opts) if featured else e._prepare_skill_roll(c,skill,**opts)
  if prepared[3] is not None:opts['fixed']=prepared[3]
  if prepared[4] is not None:opts['fixed_penalties']=prepared[4]
 basis={'jump_id':jump_id,'destination':destination,'origin':origin.pos,'round':e.round_no,'landing_altitude':landing_altitude,'apex_height':apex_height,'capabilities':cap,'requested':requested,'boost':boost,'checks':[(key,skill,dc) for key,skill,dc,_ in plans],'reason':reason_text,'running_start':running_start,'running_reason':running_reason,'running_bonus_included':running_bonus_included}
 if wall is not None:basis['wall_run']=deepcopy(wall)
 if descending:basis['launch_altitude']=old_altitude
 if inflight and ((not featured and 'wall_progress' not in inflight) or inflight['basis']!=basis):raise ValueError('cannot change an already observed jump attempt')
 history_count=len(getattr(c,'_action_history',[]))
 # The dry-run actor must be the same actor throughout its staged world.
 import state_grants as G
 staged,probe=deepcopy((e,c),{id(e.r):e.r,**G._transition_token_anchors(e)})
 probe.budget=getattr(probe,'budget',None)
 staged.log_lines=[]
 if not inflight and (not c.on_field or c.captured or not prepaid and not TURN.spend(staged,probe,'shift','점프',movement=True)):return False
 def resolve(roll_engine,observed=None):
  checks={};effective=dict(cap)
  for index,(key,skill,dc,opts) in enumerate(plans):
   roll=observed[index] if observed is not None else roll_engine.skill_roll(c,skill,**opts)
   SF.finish(roll_engine,c,opts.get('roll_id'))
   check=C.against_dc(roll,dc);checks[key]=check
   if key=='boost' and check.passed:effective[boost]+=1
   if not check.passed:return checks,effective,key
  return checks,effective,None
 shift_committed=bool(inflight)
 def commit_shift():
  nonlocal shift_committed
  if shift_committed:return
  shift_committed=True
  c.budget=probe.budget
  # Free actions from actual rerolls happened inside the Shift action. Keep both.
  c._action_history=probe._action_history+getattr(c,'_action_history',[])[history_count:]
  c._restricted_action_taken=getattr(probe,'_restricted_action_taken',False)
  c._regular_shift_movement_used=getattr(probe,'_regular_shift_movement_used',False)
  e.log_lines.extend(staged.log_lines)
  if featured:c.spec['_jump_inflight']={'jump_id':jump_id,'basis':deepcopy(basis)}
 if wall is not None and (not inflight or 'wall_progress' in inflight):
  commit_shift()
  current=c.spec.setdefault('_jump_inflight',{'jump_id':jump_id,'basis':deepcopy(basis)})
  progress=current.setdefault('wall_progress',{})
  if not WALL.traverse(e,c,wall,progress=progress):
   if progress['phase'] in ('reaction_pending','entry_pending'):
    return C.PendingDecision('actual Wallrunner movement action or entry effects must finish')
   c.spec.pop('_jump_inflight',None)
   c.spec.setdefault('_jump_attempts',{})[jump_id]={'destination':destination,'landing_altitude':landing_altitude,'wall_run':deepcopy(wall),'failed':'wall_run_interrupted','whole_shift':True}
   return False
 if featured:
  try:
   checks,effective,failed=SF.sequence(e,'jump:'+c.spec['id']+':'+jump_id,basis,[(c,skill,opts) for _,skill,_,opts in plans],lambda rolls:resolve(e,rolls),stop_after=lambda index,roll:not C.against_dc(roll,plans[index][2]).passed)
  finally:
   if 'jump:'+c.spec['id']+':'+jump_id in getattr(e,'_skill_sequences',{}) and any(opts.get('roll_id') in e._ap_rolls and e._ap_rolls[opts['roll_id']].get('skill_event') is not None for _,_,_,opts in plans):commit_shift()
 else:
  checks,effective,failed=COMMON._staged_rolls(e,resolve);commit_shift()
 c.spec.pop('_jump_inflight',None)
 record={'destination':destination,'landing_altitude':landing_altitude,'apex_height':apex_height,'base_limits':cap,'effective_limits':effective,'requested':requested,'boost':boost,'checks':checks,'reason':reason_text,'failed':failed,'whole_shift':True,'running_start':running_start,'running_reason':running_reason,'running_bonus_included':running_bonus_included}
 if wall is not None:record['wall_run']=deepcopy(wall)
 if descending:record['launch_altitude']=old_altitude
 c.spec.setdefault('_jump_attempts',{})[jump_id]=record
 record['quick_gymnastics']=__import__('tumbler').quick_offer(e,c,{'kind':'jump','jump_id':jump_id})
 if failed:
  c.spec['_jump_pending']=jump_id
  return C.PendingDecision('GM jump failure consequence; no automatic falling or damage',checks[failed],basis=deepcopy(record))
 record.update(movement_pending=True,movement_intent=intent)
 return _continue_landing(e,c,record,jump_id,fall_options)

def resolve_failure(e,c,*,decision,reason_text):
 M.reason(reason_text)
 pending=c.spec.get('_jump_pending')
 if not pending:raise ValueError('no unresolved jump failure')
 if decision not in ('abort','land'):raise ValueError('explicit GM abort or landing required')
 record=c.spec['_jump_attempts'][pending]
 if decision=='land':
  # Explicit GM world ruling, not an ordinary check success or free action grant.
  c.pos=tuple(record['destination']);c.spec['_movement_altitude']=record['landing_altitude'];c.airborne=False
 record['gm_consequence']={'decision':decision,'reason':reason_text}
 c.spec.pop('_jump_pending')
 __import__('tumbler').quick_shift(e,c,record.get('quick_gymnastics'))
 e.gm._rec('점프 실패 결과',pending,decision,reason_text,c)
 return deepcopy(record)
