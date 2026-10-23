"""Observed native checks and optional Skill Monkey rerolls (ch03:909-913).

Once observed, the first roll survives later choice failures. Only reroll dice
and the source's action/frequency cost form a new transaction.
"""
from copy import copy, deepcopy
from dataclasses import dataclass, replace
import common_checks as C
import roll_pools as POOLS
import skill_modifiers as S
import contest_features as FEATURES
import frequency as FREQ

MONKEY='feat/팔방미인'
MONKEY_CSV='C2CSV/input/db/feats.csv:R51:main'
FREQUENCY={'kind':'daily','uses':3}

@dataclass(frozen=True)
class SkillEvent:
 actor: object
 skill: str
 request: tuple
 prepared: tuple
 first: C.SkillRoll
 final: object=None
 feature: object=None
 state: str='observed'

def _request(e,actor,skill,options):
 return (S.skill_id(e.r.skill_policy,skill),options.get('mods',0),
         options.get('helper_rank',0),None if options.get('fixed') is None else tuple(options['fixed']),
         options.get('penalty_count',0),None if options.get('fixed_penalties') is None else tuple(options['fixed_penalties']),
         options.get('helper_bonus'),deepcopy(options.get('skill_context')),deepcopy(options.get('skill_stunt')),options.get('skill_target'))

def event(e,actor,roll_id):
 if not isinstance(roll_id,str) or not roll_id.strip():raise ValueError('explicit actual skill roll ID required')
 result=e._ap_rolls.get(roll_id,{}).get('skill_event')
 if result is not None and result.actor is not actor:raise ValueError('skill event belongs to another actor')
 return result

def _store(e,roll_id,value):
 e._ap_rolls[roll_id]={**e._ap_rolls[roll_id],'skill_event':value}

def observe(e,actor,skill,result,prepared,options):
 roll_id=options.get('roll_id')
 if roll_id is None:return
 if event(e,actor,roll_id) is not None:raise ValueError('skill result was already observed')
 _store(e,roll_id,SkillEvent(actor,S.skill_id(e.r.skill_policy,skill),_request(e,actor,skill,options),prepared,result))

def _source(e,actor,feature):
 if feature not in (MONKEY,MONKEY_CSV):raise ValueError('unsupported selected skill feature')
 if feature==MONKEY_CSV:
  acquired=actor.spec.get('feats',[])
  if not isinstance(acquired,(list,tuple)) or sum(x in (MONKEY_CSV,MONKEY,'팔방미인') for x in acquired)!=1:
   raise ValueError('one unambiguous acquired Skill Monkey source required')
 FEATURES.conscious_trainer(actor)
 if actor.r is not e.r:raise ValueError('skill feature actor belongs to another rule context')
 FEATURES.require(e,actor,feature)
 identities={S.skill_id(e.r.skill_policy,s,required=True):s for s in actor.spec.get('skills',{})}
 if sum(S.rank(e.r,actor,s)[2]>=4 for s in identities.values())<3:
  raise ValueError('Skill Monkey requires three distinct Adept skills')

def _feature_options(options,rank,penalty_count):
 if not isinstance(options,dict):raise ValueError('explicit feature options required')
 if set(options)-{'decision','reroll_faces','reroll_penalties'}:raise ValueError('unsupported skill feature options')
 if not callable(options.get('decision')):raise ValueError('choice must observe the actual first SkillRoll')
 faces=C.dice(options['reroll_faces'],rank) if options.get('reroll_faces') is not None else None
 penalties=C.dice(options['reroll_penalties'],penalty_count) if options.get('reroll_penalties') is not None else None
 return faces,penalties

def _preflight_cost(e,actor,feature):
 staged=copy(e);staged.log_lines=[];staged._time_actors=list(getattr(e,'_time_actors',[]))
 shadow=copy(actor);shadow.spec=deepcopy(actor.spec);shadow._action_history=list(getattr(actor,'_action_history',[]))
 if not FREQ.activation_allowed(shadow,feature,FREQUENCY,engine=staged):raise ValueError('Skill Monkey daily uses exhausted')
 FEATURES.trigger_free_action(staged,shadow,feature)

def prepare(e,actor,skill,feature,feature_options,options):
 _source(e,actor,feature)
 old=event(e,actor,options.get('roll_id'))
 if old is not None:
  if old.state not in ('observed','pending') or old.feature not in (None,feature):raise ValueError('skill roll feature decision already finalized')
  if old.request!=_request(e,actor,skill,options):raise ValueError('cannot change an observed skill declaration')
  prepared=old.prepared
 else:prepared=e._prepare_skill_roll(actor,skill,**options)
 _feature_options(feature_options,prepared[5]['dice_count'],options.get('penalty_count',0))
 _preflight_cost(e,actor,feature)
 return prepared

def roll(e,actor,skill,feature,feature_options,options):
 prepared=prepare(e,actor,skill,feature,feature_options,options)
 options=dict(options)
 if options.get('fixed') is not None:options['fixed']=prepared[3]
 if options.get('fixed_penalties') is not None:options['fixed_penalties']=prepared[4]
 roll_id=options['roll_id'];old=event(e,actor,roll_id)
 if old is None:
  e.skill_roll(actor,skill,**options)
  old=event(e,actor,roll_id)
 old=replace(old,state='pending',feature=feature)
 _store(e,roll_id,old)
 decision=feature_options['decision'](old.first)
 if type(decision) is not bool:raise ValueError('observed reroll choice must be boolean')
 if not decision:
  _store(e,roll_id,replace(old,state='final',final=old.first))
  return old.first
 def reroll(staged,shadow):
  _source(staged,shadow,feature)
  if not FREQ.activation_allowed(shadow,feature,FREQUENCY,engine=staged):raise ValueError('Skill Monkey daily uses exhausted')
  FEATURES.trigger_free_action(staged,shadow,feature)
  dice_count=getattr(old.first,'dice_count',old.first.rank)
  faces,penalties=_feature_options(feature_options,dice_count,len(old.first.penalties))
  if faces is None:faces=tuple(POOLS.pool(staged.rng,dice_count)['faces'])
  if penalties is None:penalties=tuple(POOLS.pool(staged.rng,len(old.first.penalties))['faces'])
  result=(C.AdjustedSkillRoll(old.first.rank,faces,old.first.modifier+2,old.first.helper_rank,penalties,old.first.helper_bonus,dice_count) if isinstance(old.first,C.AdjustedSkillRoll) else C.SkillRoll(old.first.rank,faces,old.first.modifier+2,old.first.helper_rank,penalties,old.first.helper_bonus))
  FREQ.consume_activation(shadow,feature,FREQUENCY,engine=staged)
  staged.log(f'  {shadow.name}: 팔방미인 {old.first.total} → {result.total} (새 굴림 +2)',feature)
  return result
 result=FEATURES._feature_transaction(e,actor,reroll)
 _store(e,roll_id,replace(old,state='final',final=result))
 return result

def finish(e,actor,roll_id):
 if roll_id is None:return
 old=event(e,actor,roll_id)
 if old is not None and old.state=='observed':_store(e,roll_id,replace(old,state='final',final=old.first))

def resume_roll(e,actor,skill,options):
 """Internal compound-check replay: never activate a feature twice."""
 old=event(e,actor,options['roll_id'])
 if old is not None and old.state=='final':
  if old.request!=_request(e,actor,skill,options):raise ValueError('changed completed participant declaration')
  return old.final
 result=e.skill_roll(actor,skill,**options)
 finish(e,actor,options.get('roll_id'))
 return result



def sequence(e,key,basis,plans,resolve,*,stop_after=None):
 """Resume an identified compound action after a later observed-choice error.

 Every request is prevalidated first. Thereafter observations and paid feature
 costs are durable: completed participants are replayed only inside this same
 unfinished action, and a completed action cannot be consumed again.
 """
 if not isinstance(key,str) or not key.strip():raise ValueError('explicit compound skill action identity required')
 runs=getattr(e,'_skill_sequences',{})
 requests=tuple((actor, _request(e,actor,skill,options),options.get('feature'),options.get('roll_id')) for actor,skill,options in plans)
 ids=[entry[-1] for entry in requests]
 if any(not isinstance(uid,str) or not uid.strip() for uid in ids) or len(set(ids))!=len(ids):
  raise ValueError('distinct actual participant roll IDs required')
 old=runs.get(key)
 if old is not None:
  if old['closed']:raise ValueError('compound skill action already finalized')
  if old['basis']!=basis or old['requests']!=requests:raise ValueError('cannot change an observed compound action')
 else:
  for actor,skill,options in plans:
   if event(e,actor,options['roll_id']) is not None:raise ValueError('roll already belongs to another observed action')
 # Do all remaining permission/input checks before drawing any further dice.
 for actor,skill,options in plans:
  recorded=event(e,actor,options['roll_id'])
  if recorded is None or recorded.state!='final':e._prepare_skill_roll(actor,skill,**options)
 if old is None:
  old={'basis':deepcopy(basis),'requests':requests,'closed':False}
  if not hasattr(e,'_skill_sequences'):e._skill_sequences={}
  e._skill_sequences[key]=old
 rolls=[]
 for index,(actor,skill,options) in enumerate(plans):
  rolls.append(resume_roll(e,actor,skill,options))
  if stop_after is not None and stop_after(index,rolls[-1]):break
 result=resolve(rolls)
 old['closed']=True
 return result


def prepared_for_sequence(e,actor,skill,options):
 old=event(e,actor,options['roll_id'])
 if old is not None and old.state=='final':
  if old.request!=_request(e,actor,skill,options):raise ValueError('changed completed participant declaration')
  return old.prepared
 return e._prepare_skill_roll(actor,skill,**options)


def opposed(e,a,skill_a,b,skill_b,acting,defending):
 plans=[(a,skill_a,acting),(b,skill_b,defending)]
 def resolve(rolls):
  winner=C.opposed(*rolls)
  e.log(f'  대항 체크: {a.name} {rolls[0].total} vs {b.name} {rolls[1].total} → '+('공격 측 승' if winner=='challenger' else '수비 측 승(동률 포함)'), 'gameplay/skill-check')
  return winner=='challenger'
 roll_id=acting.get('roll_id')
 if not isinstance(roll_id,str) or not roll_id.strip():raise ValueError('opposed feature resolution requires acting roll ID')
 return sequence(e,'opposed:'+roll_id,{'kind':'native_opposed'},plans,resolve)
