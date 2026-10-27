"""Source-backed GM-selected ordinary check contexts; no prose classifier.

A context selects real native skill rolls and preserves both sides. The GM
still supplies world outcomes. PTK selection examples live in data; common
roll arithmetic and transactional staging remain ruleset-neutral.
"""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import json
import common_checks as C
import common_action_checks as COMMON
import skill_modifiers as S

def policy(e):
 return json.loads((Path(e.r.root)/'data/context-check-policy.json').read_text(encoding='utf-8'))

def perform(e,actor,skill,dc,options,adjudication):
 options=dict(options);case=options.pop('case',None);context=options.pop('context',None)
 config=policy(e)['contexts'].get(case)
 if config is None:return C.PendingDecision('GM selects a supported ordinary action context')
 if not isinstance(context,dict) or not isinstance(context.get('purpose'),str) or not context['purpose'].strip():return C.PendingDecision('GM concrete purpose and context')
 if config.get('required_context') and context.get(config['required_context']) is not True:return C.PendingDecision('GM establishes '+config['required_context'])
 selected=config['skill'] if skill is None else skill
 if selected is None:return C.PendingDecision('GM selects one of the sourced situation skills: '+str(config.get('allowed_skills',[])))
 allowed=config.get('allowed_skills',[config['skill']])
 if S.skill_id(e.r.skill_policy,selected,required=True) not in {S.skill_id(e.r.skill_policy,v,required=True) for v in allowed}:raise ValueError('selected case does not use this acting skill; choose another context or explicit ordinary GM check')
 if e.r._selected_rule(config['source_id'])!=config['source_id']:raise ValueError('selected context variant needs its own procedure adapter')
 basis={'case':case,'context':deepcopy(context),'source':policy(e)['source'],'lines':config['lines'],'actor':actor.spec.get('id',actor.name),'skill':selected,'world_note':config.get('world_note','GM world response required')}
 changes=options.pop('environment_modifiers',[])
 if not isinstance(changes,(list,tuple)):raise ValueError('environment modifiers must be explicit GM records')
 for change in changes:
  if not isinstance(change,dict) or set(change)!={'side','amount','reason'} or change['side'] not in ('actor','defender'):raise ValueError('environment modifier needs actor/defender side, amount, reason')
  C.integer(change['amount'],'environment modifier')
  if not isinstance(change['reason'],str) or not change['reason'].strip():raise ValueError('GM reason for environment modifier required')
 basis['environment_modifiers']=deepcopy(changes)
 if config['mode']=='skill':
  if config.get('examples'):basis['source_dc_examples']=config['examples']
  interpretation=options.pop('source_policy',policy(e)['interpretations'].get(config.get('interpretation'),{}).get('default'))
  if config.get('interpretation')=='rare_survival':
   if interpretation not in ('ptk_literal','ptu_margin'):return C.PendingDecision('GM selects ptk_literal rare DC4 or ptu_margin base DC+margin4; source conflict is not silently corrected',basis=basis)
   basis['source_policy']=interpretation
   if interpretation=='ptk_literal':
    if dc not in (None,4):raise ValueError('literal PTK rare-signs check has DC4')
    dc=4
  elif interpretation is not None:raise ValueError('source_policy is not used for this context')
  if dc is None:return C.PendingDecision('GM ordinary task DC; examples are guidance and do not create an automatic opposed check',basis=basis)
  if any(x['side']!='actor' for x in changes):raise ValueError('ordinary check has no defending roll')
  if changes:options['mods']=C.integer(options.get('mods',0),'ordinary modifier')+sum(x['amount'] for x in changes)
  if any(k in options for k in ['target','defender_skill','defender_options','defender_role']):raise ValueError('ordinary context uses a task DC, not an invented resisting skill')
  options['roll_purpose']=context['purpose']
  result=e.common_action(actor,selected,dc,mode='skill',**adjudication,**options)
  if result.basis and 'roll_plan' in result.basis:basis['roll_plan']=result.basis['roll_plan']
  if config.get('interpretation')=='rare_survival':
   basis['rare_information_eligible']=bool(result.check and result.check.passed and (interpretation=='ptk_literal' or result.check.margin>=4))
  return replace(result,basis=basis)
 if dc is not None:raise ValueError('opposed context uses actual opposing skill, not a task DC')
 target=options.pop('target',None);defending=options.pop('defender_skill',config['defender_skill']);role=options.pop('defender_role',None)
 other=dict(options.pop('defender_options',{}) or {});acting=dict(options.pop('challenger_options',{}) or {})
 subject=options.pop('subject',None)
 if subject is not None and case!='third_party_persuasion':raise ValueError('explicit third-party subject is exclusive to third-party persuasion')
 if options:raise ValueError('unknown context procedure options: '+str(sorted(options)))
 if target is None or target is actor:return C.PendingDecision('distinct live opposed target')
 if role!='status_quo':return C.PendingDecision('GM identifies the defender maintaining the status quo; symmetric tie needs its own ruling')
 import skill_targets as TARGETS
 if case=='third_party_persuasion':
  if subject is actor or subject is target:raise ValueError('third-party evaluator must differ from both persuaders')
  acting=TARGETS.bind(e,acting,subject);other=TARGETS.bind(e,other,subject)
 else:acting=TARGETS.bind(e,acting,target);other=TARGETS.bind(e,other,actor)
 if target.dead or target.fainted:return C.PendingDecision('source for unconscious resisting participant')
 if defending is None:return C.PendingDecision('GM relevant manipulation skill of the actual device or magical restraint creator')
 if config['defender_skill'] is not None:
  if S.skill_id(e.r.skill_policy,defending,required=True)!=S.skill_id(e.r.skill_policy,config['defender_skill'],required=True):raise ValueError('case has a different opposed skill; general alternate procedure needs an explicit GM selection')
 elif defending not in config['suggested_defender_skills']:
  if not isinstance(context.get('relevance_reason'),str) or not context['relevance_reason'].strip():return C.PendingDecision('GM explains the other relevant creator skill; listed skills are examples')
 for opts,side in [(acting,'actor'),(other,'defender')]:
  additions=[x['amount'] for x in changes if x['side']==side]
  if additions:opts['mods']=C.integer(opts.get('mods',0),'opposed modifier')+sum(additions)
 if acting.get('roll_id') is not None and acting.get('roll_id')==other.get('roll_id'):raise ValueError('distinct opposed roll identities required')
 import skill_feature_actions as SF
 featured=any(o.get('feature') is not None for o in (acting,other))
 plans=[]
 for c,s,opts in [(actor,selected,acting),(target,defending,other)]:
  if featured:
   prepared=SF.prepared_for_sequence(e,c,s,opts)
   if prepared[3] is not None:opts['fixed']=prepared[3]
   if prepared[4] is not None:opts['fixed_penalties']=prepared[4]
  else:
   plan_options=dict(opts);roll_target=plan_options.pop('skill_target',c)
   plan=e.plan_skill_check(c,s,purpose=context['purpose'],target=roll_target,**plan_options)
   opts['fixed']=plan['fixed_faces'];opts['fixed_penalties']=plan['fixed_penalties'];plans.append(plan)
 if plans:basis['roll_plans']=plans
 def resolve(staged,observed=None):
  if observed is None:a=staged.skill_roll(actor,selected,**acting);b=staged.skill_roll(target,defending,**other)
  else:a,b=observed
  SF.finish(staged,actor,acting.get('roll_id'));SF.finish(staged,target,other.get('roll_id'))
  winner,(a,b)=SF.resolve_opposed(staged,[(actor,selected,acting),(target,defending,other)],[a,b])
  check=C.CheckResult(a.total,b.total,a.total-b.total,winner=='challenger')
  resolved=dict(basis,defender=target.spec.get('id',target.name),defender_skill=defending,defender_role=role,challenger_roll=a,defender_roll=b)
  return replace(C.adjudicate(check,**adjudication),basis=resolved)
 if featured:
  key=acting.get('roll_id')
  if not isinstance(key,str) or not key.strip():raise ValueError('context opposed feature requires acting roll ID')
  return SF.sequence(e,'context:'+key,dict(basis,defender_role=role),[(actor,selected,acting),(target,defending,other)],lambda rolls:resolve(e,rolls))
 return COMMON._staged_rolls(e,resolve,actors=(actor,target))
