"""Durable native maneuver costs around observed optional skill decisions.

The ordinary maneuver owns Standard, AoO, accuracy and final world effects.
Only its existing opposed skill phase resumes after a feature-choice error.
"""
from copy import deepcopy
import common_checks as C
import skill_feature_actions as SF

RECEIPTS='_skill_maneuver_receipts'
ACTIVE='_skill_maneuver_active'

def identity(source,plans):
 return source+':'+str(plans[0][2].get('roll_id'))

def resuming(actor,source,options):
 return actor.custom_conditions.get(ACTIVE)==source+':'+str(options.get('roll_id'))

def prepare(e,actor,target,source,basis,plans,*,observe=False):
 import body_modes as BODY_MODES
 BODY_MODES.require_targetable(target,engine=e)
 import skill_targets as TARGETS
 for c,skill,options in plans:
  bound=TARGETS.bind(e,options,target if c is actor else actor)
  options.update(bound)
 # An armed Athlete Coaching declares its bonus die before any pool is sized; its cost is paid after the maneuver's own action.
 import athlete as ATHLETE
 ATHLETE.coaching_prepare(e,actor,source,plans)
 featured=observe or any(options.get('feature') is not None for _,_,options in plans)
 key=identity(source,plans) if featured else None
 active=actor.custom_conditions.get(ACTIVE)
 if active is not None and active!=key:raise ValueError('finish the actually observed maneuver before changing its declaration')
 if not featured:
  for c,skill,options in plans:
   prepared=e._prepare_skill_roll(c,skill,**options)
   if prepared[3] is not None:options['fixed']=prepared[3]
   if prepared[4] is not None:options['fixed_penalties']=prepared[4]
  return None
 ids=[options.get('roll_id') for _,_,options in plans]
 if any(not isinstance(v,str) or not v.strip() for v in ids) or len(set(ids))!=len(ids):raise ValueError('maneuver observation boundary requires distinct actual opposed roll identities')
 if any(not isinstance(c.spec.get('id'),str) or not c.spec['id'] for c in (actor,target)):raise ValueError('actual maneuver participant identities required')
 basis=dict(basis,turn_owner=getattr(getattr(e,'_active_turn_actor',None),'spec',{}).get('id'),scene=actor.spec.get('frequency_state',{}).get('scene',0),source=source,actor=actor.spec['id'],target=target.spec['id'],round=e.round_no,elapsed_seconds=e.elapsed_seconds,actor_position=tuple(actor.pos),target_position=tuple(target.pos))
 record=actor.custom_conditions.get(RECEIPTS,{}).get(key)
 if record is not None:
  if record['stage']=='closed':raise ValueError('actual maneuver already finalized')
  if record['basis']!=basis:raise ValueError('cannot change an observed maneuver declaration')
 elif any(SF.event(e,c,options['roll_id']) is not None for c,skill,options in plans):raise ValueError('opposed roll already belongs to another observed action')
 for c,skill,options in plans:
  prepared=SF.prepared_for_sequence(e,c,skill,options)
  if prepared[3] is not None:options['fixed']=prepared[3]
  if prepared[4] is not None:options['fixed_penalties']=prepared[4]
 requests=tuple((c,SF._request(e,c,skill,options),options.get('feature'),options['roll_id']) for c,skill,options in plans)
 if record is not None and record['requests']!=requests:raise ValueError('cannot change an observed maneuver declaration')
 return {'key':key,'basis':basis,'requests':requests,'record':record,'plans':plans}

def _run(e,actor,prepared,*,spend,aoo,can_continue,accuracy,outcome,opposed=None,resolve_rolls=None):
 import athlete as ATHLETE
 if prepared is None:
  if not callable(opposed):raise ValueError('ordinary maneuver requires an explicit opposed stage')
  try:
   if not spend():return False
   ATHLETE.coaching_commit(e,actor)
   aoo()
   if not can_continue() or not accuracy():return False
   return outcome(opposed())
  finally:ATHLETE.coaching_end(actor)
 key=prepared['key'];record=prepared['record']
 if record is None:
  record={'basis':deepcopy(prepared['basis']),'requests':prepared['requests'],'stage':'prepared'}
  actor.custom_conditions.setdefault(RECEIPTS,{})[key]=record
  actor.custom_conditions[ACTIVE]=key
 def close(value):
  record['stage']='closed';record['result']=value
  actor.custom_conditions.pop(ACTIVE,None)
  ATHLETE.coaching_end(actor)
  return value
 if record['stage']=='prepared':
  record['stage']='spending'
  if not spend():return close(False)
  ATHLETE.coaching_commit(e,actor)
  record['stage']='aoo_started'
  aoo()
  record['stage']='after_aoo'
 if record['stage']=='after_aoo':
  if not can_continue():return close(False)
  record['stage']='accuracy_started'
  record['accuracy']=accuracy()
  record['stage']='skill'
 if record['stage']!='skill':
  # An unrelated native exception can have already changed the world. It must
  # not acquire a fresh Standard/AoO/accuracy through this skill retry API.
  return C.PendingDecision('GM continuation of interrupted native maneuver '+record['stage'],basis=deepcopy(record['basis']))
 if not record['accuracy']:return close(False)
 def finish(rolls):
  resolved=C.opposed(*rolls)=='challenger' if resolve_rolls is None else resolve_rolls(rolls)
  record['stage']='outcome_started'
  result=outcome(resolved)
  return close(result)
 return SF.sequence(e,'maneuver:'+key,record['basis'],prepared['plans'],finish)



def completed_attack_event(e,actor,attack):
 """Read the existing actual accuracy hit in SM.run's completed native maneuver tail."""
 frame=getattr(e,'_native_action_stack',[])
 if not frame or frame[-1]['actor'] is not actor or frame[-1]['source']!=attack['id'] or frame[-1]['kind']!='maneuver':return None
 event=next((row for row in e._precision_events if row['id']==frame[-1].get('precision_event_id')
             and row['kind']=='attack' and row.get('actor') is actor and row['source']==attack['id']
             and row.get('producer')=='combat_maneuver'),None)
 return event if event is not None and event['round']==e.round_no and event['result']=='accuracy_hit' else None


def run(e,actor,prepared,*,spend,aoo,can_continue,accuracy,outcome,opposed=None,attack=None,resolve_rolls=None):
 import action_lifecycle as ACTION,confusion_attacks as CONFUSION
 options=dict(spend=spend,aoo=aoo,can_continue=can_continue,accuracy=accuracy,outcome=outcome,opposed=opposed,resolve_rolls=resolve_rolls)
 if attack is None:return _run(e,actor,prepared,**options)
 CONFUSION.preflight(e,actor,attack)
 def observed_accuracy():
  identity=CONFUSION.observe_action(e,actor,attack)
  if prepared is not None and identity is not None:
   actor.custom_conditions[RECEIPTS][prepared['key']]['confusion_action']=identity
  hit=accuracy()
  if prepared is not None:
   actor.custom_conditions[RECEIPTS][prepared['key']]['precision_event_id']=e._native_action_stack[-1].get('precision_event_id')
  return hit
 options['accuracy']=observed_accuracy
 with ACTION.resolution(e,actor,attack['id'],kind='maneuver') as frame:
  if prepared is not None and prepared['record'] is not None:
   frame['precision_event_id']=prepared['record'].get('precision_event_id')
  result=_run(e,actor,prepared,**options)
  if not isinstance(result,C.PendingDecision) and (prepared is None or actor.custom_conditions[RECEIPTS][prepared['key']]['stage']=='closed'):
   event=completed_attack_event(e,actor,attack)
   if event is not None:
    # Accuracy hit is independent of the opposed effect. Consume existing ranges
    # before Roughneck can install Menace from this very Terrorize.
    __import__('combat_modifiers').incoming_status_hit(e,actor,event['target'],attack,{},event.get('natural'))
    __import__('martial_artist')._retain_tag_hit(actor,event['target'])
   pending=__import__('roughneck').after_maneuver(e,actor,attack)
   if isinstance(pending,C.PendingDecision):result=pending
  if prepared is not None:
   record=actor.custom_conditions.get(RECEIPTS,{}).get(prepared['key'])
   if record is not None and record['stage']!='closed':frame['deferred']=True
  return result


def resume_entry(actor_parameter,source=None,*,source_parameter=None,options_parameter='challenger_options',prepared_parameter=None):
 """Authorize only the existing paid maneuver's own observed continuation."""
 from functools import wraps
 from inspect import signature
 def decorate(fn):
  sig=signature(fn)
  @wraps(fn)
  def call(engine,*args,**kwargs):
   values=sig.bind(engine,*args,**kwargs).arguments
   actor=values[actor_parameter];actual_source=values[source_parameter] if source_parameter else source
   if prepared_parameter:
    prepared=values.get(prepared_parameter);key=prepared['key'] if prepared else None
   else:key=actual_source+':'+str((values.get(options_parameter) or {}).get('roll_id'))
   record=actor.custom_conditions.get(RECEIPTS,{}).get(key)
   identity=record.get('confusion_action') if record and actor.custom_conditions.get(ACTIVE)==key else None
   if identity is None:return fn(engine,*args,**kwargs)
   row=getattr(engine,'_native_action_resolutions',{}).get(identity)
   if (row is None or row['actor'] is not actor or row['source']!=actual_source or row['kind']!='maneuver'
       or row['phase']!='interrupted' or record['stage']!='skill'):
    raise ValueError('actual interrupted maneuver skill continuation required')
   prior=getattr(engine,'_confusion_resuming_action',None)
   engine._confusion_resuming_action=identity
   try:return fn(engine,*args,**kwargs)
   finally:
    if prior is None:del engine._confusion_resuming_action
    else:engine._confusion_resuming_action=prior
  return call
 return decorate
