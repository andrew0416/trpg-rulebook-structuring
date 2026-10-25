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
 active=actor.custom_conditions.get(ACTIVE);row=actor.custom_conditions.get(RECEIPTS,{}).get(active,{})
 return active==source+':'+str(options.get('roll_id')) or bool(active and row.get('native_reaction') and row['basis']['source']==source and options.get('roll_id') is None)

def prepare(e,actor,target,source,basis,plans,*,observe=False,challenger=None):
 import body_modes as BODY_MODES
 BODY_MODES.require_targetable(target,engine=e)
 import skill_targets as TARGETS
 for c,skill,options in plans:
  bound=TARGETS.bind(e,options,target if c is actor or c is challenger else challenger or actor)
  options.update(bound)
 # An armed Athlete Coaching declares its bonus die before any pool is sized; its cost is paid after the maneuver's own action.
 import athlete as ATHLETE
 ATHLETE.resist_maneuver(e,target,source,plans)
 ATHLETE.coaching_prepare(e,actor,source,plans)
 active=actor.custom_conditions.get(ACTIVE);old=actor.custom_conditions.get(RECEIPTS,{}).get(active,{})
 native_reaction=bool(old.get('native_reaction') and old['basis']['source']==source) or __import__('move_defense_reactions').native_attack_interested(e,target) or __import__('tumbler').acquired(actor,__import__('tumbler').QUICK) is not None
 if native_reaction:
  active=actor.custom_conditions.get(ACTIVE);old=actor.custom_conditions.get(RECEIPTS,{}).get(active,{})
  serial=old.get('native_serial') or len(actor.custom_conditions.get(RECEIPTS,{}))+1
  for index,(_,_,options) in enumerate(plans):options.setdefault('roll_id','native-maneuver:'+actor.entity_id+':'+source+':'+str(serial)+':'+str(index))
 featured=observe or native_reaction or any(options.get('feature') is not None for _,_,options in plans)
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
  if native_reaction_resume(e,actor,target,source):
   basis=dict(basis,actor_position=record['basis']['actor_position'],target_position=record['basis']['target_position'])
  if record['basis']!=basis:raise ValueError('cannot change an observed maneuver declaration')
 elif any(SF.event(e,c,options['roll_id']) is not None for c,skill,options in plans):raise ValueError('opposed roll already belongs to another observed action')
 for c,skill,options in plans:
  prepared=SF.prepared_for_sequence(e,c,skill,options)
  if prepared[3] is not None:options['fixed']=prepared[3]
  if prepared[4] is not None:options['fixed_penalties']=prepared[4]
 requests=tuple((c,SF._request(e,c,skill,options),options.get('feature'),options['roll_id']) for c,skill,options in plans)
 if record is not None and record['requests']!=requests:raise ValueError('cannot change an observed maneuver declaration')
 return {'key':key,'basis':basis,'requests':requests,'record':record,'plans':plans,'native_reaction':native_reaction,'native_serial':serial if native_reaction else None}

def _run(e,actor,prepared,*,spend,aoo,can_continue,accuracy,outcome,opposed=None,resolve_rolls=None,attack_boundary=None):
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
  record={'basis':deepcopy(prepared['basis']),'requests':prepared['requests'],'stage':'prepared','native_serial':prepared.get('native_serial')}
  if prepared.get('native_reaction'):record['native_reaction']=True
  actor.custom_conditions.setdefault(RECEIPTS,{})[key]=record
  actor.custom_conditions[ACTIVE]=key
 def close(value):
  record['stage']='closed';record['result']=value
  if record.get('native_action'):
   for trigger in e._native_action_resolutions[record['native_action']]['triggers']:
    if trigger['source']==record['basis']['source'] and trigger['actor'] is actor:trigger['status']='completed'
  actor.custom_conditions.pop(ACTIVE,None)
  ATHLETE.coaching_end(actor)
  return value
 if record['stage']=='prepared':
  record['stage']='spending'
  if not spend():return close(False)
  ATHLETE.coaching_commit(e,actor)
  record['stage']='aoo_started'
  record['deferred_aoo']=bool(__import__('tumbler').acquired(actor,__import__('tumbler').QUICK))
  if not record['deferred_aoo']:aoo()
  record['stage']='after_aoo'
 if record['stage']=='after_aoo':
  if not can_continue():return close(False)
  record['stage']='accuracy_started'
  record['accuracy']=accuracy()
  record['stage']='attack_boundary' if record.get('native_reaction') else 'skill'
 if record['stage']=='attack_boundary':
  result=attack_boundary(record,aoo,can_continue)
  record=actor.custom_conditions[RECEIPTS][key]
  if isinstance(result,C.PendingDecision):return result
  if result is False:return close(False)
  record['stage']='skill'
 if record['stage']!='skill':
  # An unrelated native exception can have already changed the world. It must
  # not acquire a fresh Standard/AoO/accuracy through this skill retry API.
  return C.PendingDecision('GM continuation of interrupted native maneuver '+record['stage'],basis=deepcopy(record['basis']))
 if not record['accuracy']:return close(False)
 def finish(rolls):
  if resolve_rolls is None:
   winner,rolls=SF.resolve_opposed(e,prepared['plans'],rolls);resolved=winner=='challenger'
  else:resolved=resolve_rolls(rolls)
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
 original_accuracy=accuracy
 def native_accuracy():
  # Included maneuvers have no child action frame. The short-lived actual
  # callback scope plus its native attack event cannot survive an exception.
  previous=getattr(e,'_athlete_maneuver_accuracy',None)
  e._athlete_maneuver_accuracy=actor
  try:return original_accuracy()
  finally:
   if previous is None:vars(e).pop('_athlete_maneuver_accuracy',None)
   else:e._athlete_maneuver_accuracy=previous
 accuracy=native_accuracy
 options=dict(spend=spend,aoo=aoo,can_continue=can_continue,accuracy=accuracy,outcome=outcome,opposed=opposed,resolve_rolls=resolve_rolls)
 included=attack is None
 if included and not (prepared and prepared.get('native_reaction')):return _run(e,actor,prepared,**options)
 if included:attack={'id':prepared['basis']['source'],'class':'변화'}
 if not included:CONFUSION.preflight(e,actor,attack)
 def observed_accuracy():
  identity=None if included else CONFUSION.observe_action(e,actor,attack)
  if prepared is not None and identity is not None:
   actor.custom_conditions[RECEIPTS][prepared['key']]['confusion_action']=identity
  hit=accuracy()
  if prepared is not None:
   actor.custom_conditions[RECEIPTS][prepared['key']]['precision_event_id']=e._native_action_stack[-1].get('precision_event_id')
  return hit
 options['accuracy']=observed_accuracy
 options['attack_boundary']=lambda record,aoo,can_continue:__import__('move_defense_reactions').maneuver_accuracy_boundary(e,actor,attack,prepared,record,aoo,can_continue)
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
   pending=__import__('tumbler').after_maneuver(e,actor,attack)
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
   active=actor.custom_conditions.get(ACTIVE)
   if not actor.custom_conditions.get(RECEIPTS,{}).get(key) and active and actor.custom_conditions[RECEIPTS][active].get('native_reaction') and actor.custom_conditions[RECEIPTS][active]['basis']['source']==actual_source:key=active
   record=actor.custom_conditions.get(RECEIPTS,{}).get(key)
   if record and record.get('native_action') and record['stage']!='closed':
    prior=getattr(engine,'_native_maneuver_resume',None);engine._native_maneuver_resume=(actor,key,actual_source)
    try:return fn(engine,*args,**kwargs)
    finally:
     if prior is None:vars(engine).pop('_native_maneuver_resume',None)
     else:engine._native_maneuver_resume=prior
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




def native_resume_frame(e,actor,source):
 context=getattr(e,'_native_maneuver_resume',None)
 if context is None or context[0] is not actor or context[2]!=source:return None
 record=actor.custom_conditions.get(RECEIPTS,{}).get(context[1])
 if record is None or record.get('native_action') is None or record['stage']=='closed' or record['basis']['source']!=source:raise ValueError('actual paid maneuver continuation required')
 frame=record['native_frame'];row=e._native_action_resolutions.get(record['native_action'])
 if row is None or row['actor'] is not actor or row['source']!=source or row['kind']!='maneuver' or frame['id']!=row['id']:raise ValueError('native maneuver frame provenance changed')
 return frame


def native_reaction_resume(e,actor,target,source):
 context=getattr(e,'_native_maneuver_resume',None)
 if context is None or context[0] is not actor or context[2]!=source:return False
 record=actor.custom_conditions.get(RECEIPTS,{}).get(context[1])
 if record is None or record['stage']!='attack_boundary' or record['basis']['target']!=target.entity_id:return False
 import move_defense_reactions as D
 event=D.native_event(e,record['precision_id']);state=event.get(D.NATIVE_DEFENSE,{})
 if state.get('phase')!='complete':return False
 if (state['facts']['origin']!={'kind':'maneuver','receipt':context[1]} or event['actor'] is not actor or event['target'] is not target or event['source']!=source or tuple(actor.pos)!=tuple(state['actor_position']) or tuple(target.pos)!=tuple(state['target_position'])):raise ValueError('paid maneuver reaction continuation changed')
 D.validate_native_attacks(e,__import__('world_entities').actor_index(e))
 return True
