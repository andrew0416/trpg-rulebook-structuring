"""ch03:272-280: extra Focus for a GM-selected complex or stressful task.

The two actual checks remain separate. The source supplies neither a universal
Focus DC nor a formula converting failure into an ordinary task penalty.
Combat precision has its own source-defined procedure and is not copied here.
"""
from copy import deepcopy
from dataclasses import replace
import common_checks as C
import common_action_checks as COMMON
import skill_feature_actions as SF

SOURCE='ch03-skills-edges-feats/스킬/집중'

def perform(e,actor,skill,dc,options,adjudication):
 options=dict(options);context=options.pop('context',None);focus_dc=options.pop('focus_dc',None)
 task=options.pop('task_options',{});focus=options.pop('focus_options',{})
 if options:raise ValueError('unknown additional Focus options: '+str(sorted(options)))
 if actor is None or skill is None or dc is None or focus_dc is None:return C.PendingDecision('GM task actor, original skill/DC and additional Focus DC')
 if not isinstance(context,dict) or context.get('kind') not in ('complex','stressful') or not isinstance(context.get('purpose'),str) or not context['purpose'].strip() or not isinstance(context.get('focus_reason'),str) or not context['focus_reason'].strip():
  return C.PendingDecision('GM concrete complex/stressful task and reason for additional Focus')
 if context.get('delicate_in_combat') is True:return C.PendingDecision('use the distinct combat precision procedure with actual recent attack evidence')
 if e.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Focus variant requires its own procedure')
 C.integer(dc,'original task DC');C.integer(focus_dc,'additional Focus DC');C.validate_adjudication(**adjudication)
 if not isinstance(task,dict) or not isinstance(focus,dict):raise ValueError('separate task and Focus roll options required')
 task=COMMON.assisted_options(e,actor,skill,task);focus=COMMON.assisted_options(e,actor,'집중',focus)
 featured=any(o.get('feature') is not None for o in (task,focus))
 ids=[o.get('roll_id') for o in (task,focus)]
 if featured and (any(not isinstance(uid,str) or not uid.strip() for uid in ids) or len(set(ids))!=2):raise ValueError('featured task and additional Focus require distinct roll IDs')
 if ids[0] is not None and ids[0]==ids[1]:raise ValueError('task and Focus cannot share one observed roll')
 for selected,opts in ((skill,task),('집중',focus)):
  prepared=SF.prepared_for_sequence(e,actor,selected,opts) if featured else e._prepare_skill_roll(actor,selected,**opts)
  if prepared[3] is not None:opts['fixed']=prepared[3]
  if prepared[4] is not None:opts['fixed_penalties']=prepared[4]
 basis={'source':SOURCE,'source_lines':[272,274],'context':deepcopy(context),'task_skill':skill,'task_dc':dc,'focus_dc':focus_dc,'combination':'separate_checks_with_explicit_GM_world_response'}
 def observe(staged,actor,task,focus):
  return [staged.skill_roll(actor,skill,**task),staged.skill_roll(actor,'집중',**focus)]
 def resolve(staged,actor,task,focus,observed=None):
  ordinary,concentration=observed if observed is not None else observe(staged,actor,task,focus)
  identities=[SF._observed(staged,actor,roll,opts)[0] if actor.entity_id in getattr(staged,'_let_me_help_offers',{}) else opts.get('roll_id') for roll,opts in ((ordinary,task),(concentration,focus))]
  task_check=SF.resolve_check(staged,actor,skill,dc,ordinary,task);focus_check=SF.resolve_check(staged,actor,'집중',focus_dc,concentration,focus)
  ordinary,concentration=[(SF.event(staged,actor,uid).final or roll) if uid is not None else roll for uid,roll in zip(identities,(ordinary,concentration))]
  record=dict(basis,task_roll=ordinary,focus_roll=concentration,task_check=task_check,focus_check=focus_check)
  SF.finish(staged,actor,task.get('roll_id'));SF.finish(staged,actor,focus.get('roll_id'))
  staged.log(f'  추가 집중: 원작업 {ordinary.total} vs DC {dc}, 집중 {concentration.total} vs DC {focus_dc}',SOURCE)
  return replace(C.adjudicate(**adjudication),basis=record)
 if featured:return SF.sequence(e,'focus_task:'+ids[0],basis,[(actor,skill,task),(actor,'집중',focus)],lambda rolls:resolve(e,actor,task,focus,rolls))
 return COMMON._rolls_before_help(e,resolve,observe,actors=(actor,),payload=(actor,task,focus))
