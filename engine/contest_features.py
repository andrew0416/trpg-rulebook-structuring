"""PTK contest-feature ownership and prerequisites; no inferred feature acquisition.

Branch choices use trainer.spec['feature_choices'][source_id] as distinct stat
names, and Ranked features reuse spec['feat_ranks']. Poffins are the native
Pokemon's recorded consumed Poffins, not a caller-supplied dice bonus.
"""
import arithmetic_policy as M
import action_points as AP
import common_checks as C
import roll_pools as POOLS
import skill_modifiers as SKILL

STATS=('아름다움','근사함','귀여움','슬기로움','강인함')
SKILLS=('매력','명령','교활','협박','직감')
STYLE='class/스타일-전문가'
FLOURISH='feat/스타일-플로리시'
JUGGLING_SHOW='feat/저글링-쇼'
INTRODUCTION_SKILL_BONUSES={JUGGLING_SHOW:('곡예',2)}
RANKED={
 '아름다움':('feat/아름다운-발레','직감',('feat/굉장함-최대','feat/유혹되는-아름다움')),
 '근사함':('feat/근사한-행위','명령',('feat/근사함의-규칙','feat/액션-히어로-스턴트')),
 '귀여움':('feat/귀여운-포옹','매력',('feat/신나는-발걸음','feat/우리-친구-하자')),
 '슬기로움':('feat/슬기로운-계획','교활',('feat/계산된-공격','feat/실수로부터-배운다')),
 '강인함':('feat/강인한-텀블링','협박',('feat/마초-돌진','feat/인내력')),
}

def conscious_trainer(trainer):
 if trainer.kind!='trainer' or trainer.dead or trainer.fainted or trainer.hp<=0:
  raise ValueError('conscious trainer required')
 if not isinstance(trainer.spec.get('id'),str) or not trainer.spec['id']:
  raise ValueError('actual trainer identity required')

def owner(trainer,pokemon):
 conscious_trainer(trainer)
 if pokemon.kind!='pokemon' or pokemon.spec.get('trainer_id')!=trainer.spec['id']:
  raise ValueError('target must be the actual trainer-owned Pokemon')

def owned(trainer,uid):
 fields=('edges',) if uid.startswith('edge/') else ('classes','feats')
 names=[]
 for field in fields:
  values=trainer.spec.get(field,[])
  if not isinstance(values,(list,tuple)):raise ValueError('acquired features/classes/edges must be lists')
  names.extend(values)
  aliases={'class/코디네이터':('Coordinator',),'edge/우아함':('Grace',),'class/스타일-전문가':('Style Expert',),JUGGLING_SHOW:('Juggling Show',)}
 return uid in names or uid.split('/')[-1].replace('-',' ') in names or any(name in names for name in aliases.get(uid,()))

def require(e,trainer,uid):
 import acquired_features as ACQUIRED
 ACQUIRED.validate_class_slots(trainer)
 if not owned(trainer,uid):raise ValueError('acquired source required: '+uid)
 if e.r._selected_rule(uid)!=uid:raise ValueError('selected feature variant requires a sourced adapter')

def coordinator(e,trainer):
 __import__('coordinator').require(e,trainer,'class/코디네이터')
 conscious_trainer(trainer);require(e,trainer,'class/코디네이터');require(e,trainer,'edge/우아함')
 if max(SKILL.rank(e.r,trainer,s)[2] for s in SKILLS)<3:
  raise ValueError('Coordinator requires a Novice contest skill')

def introduction_bonus_dice(engine,trainer,pokemon,source):
 owner(trainer,pokemon)
 require(engine,trainer,source)
 if source not in INTRODUCTION_SKILL_BONUSES:
  raise ValueError('supported acquired introduction bonus required')
 skill,divisor=INTRODUCTION_SKILL_BONUSES[source]
 return M.ratio(SKILL.effective_rank(engine.r,trainer,skill),divisor)

def branch_choices(trainer,uid):
 choices=trainer.spec.get('feature_choices',{}).get(uid)
 if not isinstance(choices,(list,tuple)) or not choices or any(s not in STATS for s in choices) or len(set(choices))!=len(choices):
  raise ValueError('distinct acquired contest-stat branch choices required: '+uid)
 return tuple(choices)

def consumed_poffins(pokemon,trainer=None,*,engine=None):
 import poffin_state as POFFINS
 return list(POFFINS.available(pokemon,trainer,engine=engine))

def style_expert(e,trainer):
 conscious_trainer(trainer);require(e,trainer,STYLE)
 choices=branch_choices(trainer,STYLE)
 import style_expert as STYLE_OWNER
 if all(STYLE_OWNER.acquired(trainer,STYLE,stat) for stat in choices):
  for stat in choices:STYLE_OWNER.local_csv(trainer,STYLE,stat)
  return choices
 roster=[*getattr(e,'everyone',[]),*getattr(e,'_time_actors',[]),*getattr(getattr(e,'gm',None),'everyone',[])]
 roster=list({id(p):p for p in roster if p.kind=='pokemon' and p.spec.get('trainer_id')==trainer.spec['id']}.values())
 ids=[p.spec.get('id') for p in roster]
 if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
  raise ValueError('distinct owned Pokemon identities required for Style Expert')
 for stat in choices:
  eligible=[p for p in roster if consumed_poffins(p,trainer,engine=e).count(stat)>=3]
  if len(eligible)<3:
   coordinator(e,trainer)
   if not eligible:raise ValueError('Style Expert requires actual owned Poffin-trained Pokemon')
 return choices

def style_feature_count(e,trainer,choices,exclude=()):
 # ch03:576/607/609: base Class, each Rank and each acquired branch count.
 # Shared Flourish/Entrainment cannot establish their own acquisition prerequisite.
 count=len(choices)
 for stat,(uid,skill,children) in RANKED.items():
  has_rank=owned(trainer,uid)
  acquired_children=[child for child in children if owned(trainer,child)]
  if not has_rank:
   if acquired_children:raise ValueError('Style feature requires its Ranked prerequisite')
   continue
  require(e,trainer,uid)
  if stat not in choices:raise ValueError('Ranked style feature requires its corresponding branch')
  import acquired_features as ACQUIRED
  rank=ACQUIRED.feature_rank(trainer,uid)
  C.integer(rank,'acquired style feature rank',1,2)
  if SKILL.rank(e.r,trainer,skill)[2]<(5 if rank==2 else 3):
   raise ValueError('Ranked style feature skill prerequisite not met')
  count+=rank
  for child in acquired_children:require(e,trainer,child);count+=1
 import acquired_features as ACQUIRED
 return ACQUIRED.count_for_class(trainer,STYLE,exclude=exclude)

def flourish(e,trainer,pokemon,stat):
 owner(trainer,pokemon);require(e,trainer,FLOURISH)
 choices=style_expert(e,trainer)
 selected=branch_choices(trainer,FLOURISH)
 if any(s not in choices for s in selected):raise ValueError('Flourish branch requires acquired Style Expert branch')
 if stat not in selected:raise ValueError('Move contest type must match an acquired Flourish branch')
 if style_feature_count(e,trainer,choices,exclude=(FLOURISH,))<3:raise ValueError('Flourish requires three prior Style Expert features')
 if AP.available(trainer)<1:raise ValueError('Style Flourish requires 1 available AP')
 return (FLOURISH,stat)

# Native skill-feature producers. The caller supplies an explicit GM context;
# neither failed checks nor Poffin-derived values are accepted as naked numbers.
from copy import copy,deepcopy
from dataclasses import dataclass
import action_lifecycle as ACTION
import ap_roll_bonus as AP_ROLL
import frequency as FREQ
import turn as TURN
import heavy_injury_adapter as HEAVY

STUNT='feat/액션-히어로-스턴트'
FRIENDS='feat/우리-친구-하자'
MISTAKES='feat/실수로부터-배운다'
RELIABLE='feat/신뢰의-공연'
NUANCED='feat/뉘앙스-공연'

@dataclass(frozen=True)
class ContentSkillRoll:
 source: str
 rank: int
 faces: tuple
 base: int
 modifier: int
 helper_rank: int=0
 penalties: tuple=()
 helper_bonus: object=None
 @property
 def total(self):
  return self.base+self.modifier+(M.ratio(self.helper_rank,2) if self.helper_bonus is None else self.helper_bonus)-sum(self.penalties)

def style_training(e,trainer,stat):
 choices=style_expert(e,trainer)
 if stat not in choices:raise ValueError('feature requires the corresponding Style Expert branch')
 uid,skill,_=RANKED[stat];require(e,trainer,uid)
 rank=trainer.spec.get('feat_ranks',{}).get(uid);C.integer(rank,'style prerequisite rank',1,2)
 if SKILL.rank(e.r,trainer,skill)[2]<(5 if rank==2 else 3):raise ValueError('style feature prerequisite skill not established')
 return choices

def poffin_dice(e,trainer,pokemon,stat,choices):
 # Style Expert's +2 explicitly counts as coming from Poffins (ch04:1180).
 return consumed_poffins(pokemon,trainer,engine=e).count(stat)+(2 if stat in choices else 0)

def style_stat_dice(e,trainer,pokemon):
 # These are virtual Poffin dice, never extra consumed physical Poffins. Keep
 # the source bonus outside consumed_poffins so acquisition does not bootstrap
 # its own printed three-Poffin prerequisite.
 owner(trainer,pokemon)
 if not owned(trainer,STYLE):return {}
 return {stat:2 for stat in style_expert(e,trainer)}

def require_trigger_free_action(e,trainer):
 """Check existing triggered-Free eligibility without recording an action."""
 HEAVY.ensure_clear(e);conscious_trainer(trainer)
 e.r.mech('combat/action-economy')
 if not TURN.can_act(e,trainer) or not ACTION.status_permission(e,trainer,'free'):
  raise ValueError('triggered Free Action unavailable')
 __import__('initiative_interrupts').require_recorded_action(e,trainer,'free')


def trigger_free_action(e,trainer,source):
 # ch07:57 / PTU p227: this producer has already verified its actual trigger.
 # Ordinary turn ownership is not a prerequisite for a triggered Free Action.
 require_trigger_free_action(e,trainer)
 ACTION.record_action(e,trainer,'free',_triggered_source=source)
 e.log('  '+trainer.name+': 발동조건 충족, 자유 행동 '+source,source)

def _feature_transaction(e,trainer,operation,action_actor=None,*,payload=()):
 """Use the native graph commit guard for private feature calculations."""
 import state_grants as G
 participants=() if action_actor is None else (action_actor,)
 def apply(staged,actor,*subjects):
  inputs=G._stage_transition_payload(e,staged,payload)
  return operation(staged,actor,*subjects,*inputs)
 return G.transition(e,trainer,apply,participants=participants,
                     include_rulings=True,include_grid=e.grid is not None)

def _friendship_pool(e,trainer,pokemon,options,count):
 """The source grants its own pool; it never borrows an ordinary Charm rank.

 Reuse concrete modifier/AP/condition validation without weakening the ordinary
 Pokemon intelligence gate. Only the acquired Friends producer calls this path.
 """
 import environmental_effects as ENVIRONMENT
 import blessing_skill_features as BLESSINGS
 import survivalist_features as SURVIVALIST
 import elemental_connection as ELEMENTAL
 import skill_stunts as STUNTS
 import combat_timing as TIMING
 import researcher_features as RF
 owner(trainer,pokemon);require(e,trainer,FRIENDS)
 allowed={'mods','helper_rank','penalty_count','fixed_penalties','roll_id','helper_bonus','feature','feature_options','skill_context','skill_stunt','skill_target','helper_source'}
 if set(options)-allowed:raise ValueError('unsupported friendship roll options')
 if options.get('feature') is not None or options.get('feature_options') is not None:raise ValueError('ordinary selected skill features do not replace the granted friendship pool')
 M.validate_source(e.r);ENVIRONMENT.ensure_clear(e)
 if pokemon.dead or pokemon.fainted:raise ValueError('conscious Pokemon performer required')
 skill='매력';context=options.get('skill_context')
 shared_skill_context=BLESSINGS.ADVANCED.shared_context(context)
 BLESSINGS.validate_sleep_check(e,pokemon,skill,context)
 e.r.mech('gameplay/skill-check');AP_ROLL.bonus(e,pokemon,options.get('roll_id'),'skill')
 mods=options.get('mods',0);helper=options.get('helper_rank',0);penalty_count=options.get('penalty_count',0)
 SKILL.validate_helper(e,pokemon,helper,options.get('helper_bonus'),options.get('helper_source'))
 C.validate_resolved_request(mods,helper,penalty_count,options.get('helper_bonus'))
 resolved=SKILL.modifiers(e.r,pokemon,skill,mods)
 for additions in (SURVIVALIST.modifier(e,pokemon,skill,shared_skill_context),ELEMENTAL.modifier(e,pokemon,skill,options.get('skill_target')),BLESSINGS.modifiers(e,pokemon,skill,context)):
  resolved['modifier']+=sum(row[1] for row in additions);resolved['sources']+=additions
 base_count=count
 # Skill Trainer modifies the final replacement pool, not an unused ordinary
 # skill rank or the discarded species dice expression's fixed modifier.
 pushed=pokemon.spec.get('pushed_skill')
 if pushed is not None:
  if not isinstance(pushed,dict) or pushed.get('source')!=RF.SOURCE or pushed.get('feature')!=RF.SKILL_TRAINER:raise ValueError('pushed skill requires its actual training source')
  if SKILL.skill_id(e.r.skill_policy,pushed.get('skill'),required=True)=='charm':
   RF.source(e)
   if count<6:count+=1
   else:resolved['modifier']+=3
 resolved['dice_count']=count
 STUNTS.apply(e,pokemon,skill,resolved,options.get('skill_stunt'))
 resolved['modifier']+=TIMING.skill_modifier(pokemon)
 penalties=C.dice(options['fixed_penalties'],penalty_count) if options.get('fixed_penalties') is not None else None
 return ('포핀 귀여움',str(count)+'d6',base_count,None,penalties,resolved),count


def _poffin_plan(e,trainer,pokemon,skill,stat,options):
 owner(trainer,pokemon);choices=style_training(e,trainer,stat)
 options=dict(options);faces=options.pop('fixed',None)
 count=poffin_dice(e,trainer,pokemon,stat,choices)
 if stat=='귀여움':
  if SKILL.skill_id(e.r.skill_policy,skill,required=True)!='charm':raise ValueError('Friends replacement belongs only to its named Charm attempt')
  prepared,count=_friendship_pool(e,trainer,pokemon,options,count)
 else:
  prepared=e._prepare_skill_roll(pokemon,skill,**options)
  native=prepared[5].get('pokemon_plan')
  if native and native.get('pushed'):
   # Skill Trainer applies to the final replacement pool; it never adds twice.
   prepared[5]['modifier']-=(3 if native['rank']>=6 else 0)
   if count<6:count+=1
   else:prepared[5]['modifier']+=3
 faces=C.dice(faces,count) if faces is not None else None
 combat_stat={'근사함':'atk','귀여움':'spe'}[stat]
 value=C.integer(pokemon.stats.get(combat_stat),'unstaged contest combat stat',0)
 bonus=min(3,M.ratio(value,10))
 return options,prepared,count,faces,bonus


def _poffin_roll(e,pokemon,skill,source,plan):
 options,prepared,count,faces,stat_bonus=plan
 rank=prepared[2];faces=C.dice(POOLS.pool(e.rng,count)['faces'],count) if faces is None else faces
 penalties=prepared[4]
 if penalties is None:penalties=C.dice(POOLS.pool(e.rng,options.get('penalty_count',0))['faces'])
 modifier=prepared[5]['modifier']+stat_bonus+AP_ROLL.bonus(e,pokemon,options.get('roll_id'),'skill')
 result=ContentSkillRoll(source,rank,faces,sum(faces),modifier,options.get('helper_rank',0),penalties,options.get('helper_bonus'))
 AP_ROLL.complete(e,pokemon,options.get('roll_id'),'skill')
 e.log(f'  {pokemon.name}: {source}, 포핀 {count}d6 {faces}, 스탯 +{stat_bonus}, 총합 {result.total}',source)
 return result

def skill_feature(e,trainer,pokemon,feature,skill,dc,*,context=None,decision=None,reroll_faces=None,reroll_penalties=None,**roll_options):
 """Native Engine entry for Action Hero Stunt and Learn From Your Mistakes."""
 owner(trainer,pokemon);C.integer(dc,'DC');require(e,trainer,feature)
 if feature==RELIABLE:
  reliable(e,trainer,pokemon)
  if context is not None or decision is not None or reroll_faces is not None or reroll_penalties is not None:
   raise ValueError('Reliable Performance is an explicitly chosen pre-roll replacement')
  if roll_options.get('fixed') is not None:raise ValueError('average replacement does not accept fabricated die faces')
  prepared=e._prepare_skill_roll(pokemon,skill,**roll_options)
  def resolve(staged,actor,subject,prepared,options):
   _pay_reliable(staged,actor)
   penalties=prepared[4]
   if penalties is None:penalties=C.dice(POOLS.pool(staged.rng,options.get('penalty_count',0))['faces'])
   modifier=prepared[5]['modifier']+AP_ROLL.bonus(staged,subject,options.get('roll_id'),'skill')
   rolled=ContentSkillRoll(RELIABLE,prepared[2],(),M.ratio(prepared[5].get('dice_count',prepared[2])*7,2),modifier,options.get('helper_rank',0),penalties,options.get('helper_bonus'))
   AP_ROLL.complete(staged,subject,options.get('roll_id'),'skill')
   staged.log(f'  {subject.name}: 신뢰의 공연, 기본값 {rolled.base}, 총합 {rolled.total}',RELIABLE)
   return {'source':RELIABLE,'roll':rolled,'check':C.against_dc(rolled,dc),'replacement':'skill_rank_average'}
  return _feature_transaction(e,trainer,resolve,pokemon,payload=(prepared,roll_options))
 if feature==STUNT:
  if not isinstance(context,dict) or context.get('source')!='ordinary' or context.get('dramatic_risk') is not True:
   raise ValueError('Stunt requires an explicit GM dramatic-risk ordinary check; combat maneuvers, intercepts, Moves and Abilities are excluded')
  for field in ('action','risk'):
   if not isinstance(context.get(field),str) or not context[field].strip():raise ValueError('GM action and dramatic risk descriptions required')
  if decision is not None or reroll_faces is not None or reroll_penalties is not None:raise ValueError('Stunt is a pre-roll replacement, not a reroll')
  plan=_poffin_plan(e,trainer,pokemon,skill,'근사함',roll_options)
  quota=__import__('style_expert').frequency(trainer,feature)
  def resolve(staged,actor,subject,plan,context):
   if not FREQ.activation_allowed(actor,feature,quota,engine=staged):raise ValueError('Action Hero Stunt daily uses exhausted')
   trigger_free_action(staged,actor,feature)
   rolled=_poffin_roll(staged,subject,skill,feature,plan)
   check=C.against_dc(rolled,dc)
   FREQ.consume_activation(actor,feature,quota,engine=staged)
   return {'source':feature,'roll':rolled,'check':check,'context':deepcopy(context)}
  return _feature_transaction(e,trainer,resolve,pokemon,payload=(plan,context))
 if feature==MISTAKES:
  return _mistakes(e,trainer,pokemon,skill,dc,decision,reroll_faces,reroll_penalties,roll_options)
 raise ValueError('unsupported contest skill feature')


def _mistakes(e,trainer,pokemon,skill,dc,decision,reroll_faces,reroll_penalties,roll_options):
 """Commit the original check before exposing failure; stage only its reroll."""
 import observed_resolution as OBS
 import skill_feature_actions as SF
 from dataclasses import replace
 choices=style_training(e,trainer,'슬기로움')
 quota=__import__('style_expert').frequency(trainer,MISTAKES)
 if not callable(decision):raise ValueError('Learn From Your Mistakes requires a choice after actual failure')
 options=dict(roll_options)
 key,old=OBS.locate(e._ap_rolls,'contest_skill:'+MISTAKES,(trainer,pokemon),options.get('roll_id'))
 options['roll_id']=key
 # SF's request contains actual target identity and independently copied context.
 declaration={'skill':SKILL.skill_id(e.r.skill_policy,skill,required=True),'dc':dc,'request':SF._request(e,pokemon,skill,options)}
 if old is not None:
  OBS.verify(old,declaration);first=old['observation']['first'];bonus=old['observation']['poffin_bonus']
  count=getattr(first,'dice_count',first.rank)
 else:
  prepared=e._prepare_skill_roll(pokemon,skill,**options);count=prepared[5]['dice_count']
  bonus=poffin_dice(e,trainer,pokemon,'슬기로움',choices)
 if reroll_faces is not None:reroll_faces=C.dice(reroll_faces,count)
 if reroll_penalties is not None:reroll_penalties=C.dice(reroll_penalties,options.get('penalty_count',0))
 if old is None:
  # Known source/action/input errors must not expose a speculative first roll.
  staged=copy(e);staged.log_lines=[];staged._time_actors=list(getattr(e,'_time_actors',[]));shadow=copy(trainer);shadow.spec=__import__('world_entities').spec_copy(trainer);shadow._action_history=deepcopy(getattr(trainer,'_action_history',[]))
  if not FREQ.activation_allowed(shadow,MISTAKES,quota,engine=staged):raise ValueError('Learn From Your Mistakes daily uses exhausted')
  require_trigger_free_action(staged,trainer)
  # The first Mistakes result is private; nested native choices use the shared commit guard.
  first=_feature_transaction(e,trainer,lambda staged,shadow,subject,inputs:staged.skill_roll(subject,skill,**inputs),
                             pokemon,payload=(options,))
  old=OBS.begin(e._ap_rolls,key,'contest_skill:'+MISTAKES,(trainer,pokemon),declaration,{'first':first,'poffin_bonus':bonus},references=tuple(x for x in (options.get('skill_target'),) if x is not None))
 check=C.against_dc(first,dc)
 if check.passed:
  SF.finish(e,pokemon,key)
  return OBS.complete(old,{'source':MISTAKES,'first_roll':first,'roll':first,'check':check,'rerolled':False,'roll_id':key})
 chosen=OBS.decide(old,decision,check)
 if not chosen:
  SF.finish(e,pokemon,key)
  return OBS.complete(old,{'source':MISTAKES,'first_roll':first,'roll':first,'check':check,'rerolled':False,'roll_id':key})
 def reroll(staged,shadow,subject,observed):
  owner(shadow,subject);require(staged,shadow,MISTAKES)
  style_training(staged,shadow,'슬기로움')
  if __import__('style_expert').frequency(shadow,MISTAKES)!=quota:
   raise ValueError('Learn From Your Mistakes source quota changed after observation')
  if not FREQ.activation_allowed(shadow,MISTAKES,quota,engine=staged):raise ValueError('Learn From Your Mistakes daily uses exhausted')
  trigger_free_action(staged,shadow,MISTAKES)
  faces=C.dice(POOLS.pool(staged.rng,count)['faces'],count) if reroll_faces is None else reroll_faces
  penalties=C.dice(POOLS.pool(staged.rng,len(observed.penalties))['faces'],len(observed.penalties)) if reroll_penalties is None else reroll_penalties
  # Use the actual original rank/pool/modifiers; AP, helper and other bonuses
  # are not re-read or applied again after observing the failure.
  result=replace(observed,faces=faces,penalties=penalties,modifier=observed.modifier+bonus)
  FREQ.consume_activation(shadow,MISTAKES,quota,engine=staged)
  staged.log(f'  {subject.name}: 실수로부터 배운다 {observed.total} → {result.total}, 포핀 +{bonus}',MISTAKES)
  return result
 final=_feature_transaction(e,trainer,reroll,pokemon,payload=(first,))
 SF.finish(e,pokemon,key)
 return OBS.complete(old,{'source':MISTAKES,'first_roll':first,'roll':final,'check':C.against_dc(final,dc),'rerolled':True,'poffin_bonus':bonus,'roll_id':key})


def reliable(e,trainer,pokemon):
 """ch04:509-519: validate the entire acquired Coordinator feature chain."""
 owner(trainer,pokemon);coordinator(e,trainer)
 __import__('coordinator').require(e,trainer,RELIABLE)
 require(e,trainer,NUANCED);require(e,trainer,RELIABLE)
 if max(SKILL.rank(e.r,trainer,s)[2] for s in SKILLS)<6:
  raise ValueError('Reliable Performance requires a Master contest skill')
 if AP.available(trainer)<2:raise ValueError('Reliable Performance requires 2 available AP')


def _pay_reliable(e,trainer):
 trigger_free_action(e,trainer,RELIABLE);AP.spend(trainer,2)


def prepare_reliable_accuracy(e,trainer,pokemon):
 """Preflight the native source and action without spending live resources."""
 reliable(e,trainer,pokemon)
 if pokemon.dead or pokemon.fainted:
  raise ValueError('conscious Pokemon required for Reliable Performance')
 staged=copy(e);staged.log_lines=[]
 actor=copy(trainer);actor.spec=__import__('world_entities').spec_copy(trainer)
 actor._action_history=deepcopy(getattr(trainer,'_action_history',[]))
 require_trigger_free_action(staged,trainer)
 AP.spend(actor,2)
 staged.log('  '+actor.name+': 발동조건 충족, 자유 행동 '+RELIABLE,RELIABLE)
 return staged.log_lines


def reliable_accuracy_preflight(e,trainer,pokemon,move,mm,*,shared_accuracy=None,activation=None,fixed_roll=None):
 """Native use_move calls this before Standard, frequency or on_move_use.
 The setup turn only verifies eligibility; only an actual accuracy producer
 calling reliable_accuracy_check commits the feature's cost.
 """
 import effects_ext as EXT
 if shared_accuracy is not None or activation is not None or fixed_roll is not None or EXT.multi_roll_spec(mm) is not None:
  raise ValueError('Reliable Performance fixed/shared/composite accuracy requires a per-roll selection policy')
 if move['class']=='변화' and not move.get('ac') and '자신' in move.get('range',''):
  raise ValueError('this move has no accuracy check to replace')
 prepare_reliable_accuracy(e,trainer,pokemon)


def reliable_accuracy_check(e,trainer,pokemon,resolve):
 """The actual accuracy producer supplies resolve(natural), never a result.
 Stage only this feature's new cost; native accuracy preserves its existing
 shield, blessing and situational-modifier behavior. A late exception cannot
 charge this feature's AP or record its Free action.
 """
 cost_logs=prepare_reliable_accuracy(e,trainer,pokemon)
 log_index=len(e.log_lines)
 result=resolve(10)
 AP.spend(trainer,2);ACTION.record_action(e,trainer,'free')
 e.log_lines[log_index:log_index]=cost_logs
 return result


def friendship_check(e,trainer,performer,target,*,dc,roll_options):
 """Roll only; pokemon_activities owns audience, disposition and failure history."""
 owner(trainer,performer);require(e,trainer,FRIENDS);C.integer(dc,'DC')
 import pokemon_party as PARTY
 PARTY.require_participation(e,performer)
 if performer.captured or not getattr(performer,'on_field',True):raise ValueError('actual available on-field Pokemon performer required')
 roster=[*getattr(e,'everyone',[]),*getattr(e,'_time_actors',[]),*getattr(e.gm,'everyone',[])]
 for subject in (trainer,performer,target):
  matches={id(a):a for a in roster if a.spec.get('id')==subject.spec.get('id')}
  if subject.r is not e.r or not subject.spec.get('id') or len(matches)!=1 or next(iter(matches.values())) is not subject:
   raise ValueError('actual uniquely registered friendship participants required')
 if target is performer or target.kind!='pokemon' or not target.spec.get('wild',False) or target.captured:
  raise ValueError('Let Us Be Friends requires a distinct actual wild Pokemon target')
 options=dict(roll_options)
 if options.get('skill_target') not in (None,target):raise ValueError('friendship check target cannot be substituted')
 options['skill_target']=target
 plan=_poffin_plan(e,trainer,performer,'매력','귀여움',options)
 quota=__import__('style_expert').frequency(trainer,FRIENDS)
 def resolve(staged,actor,subject,plan):
  if not FREQ.activation_allowed(actor,FRIENDS,quota,engine=staged):raise ValueError('Let Us Be Friends selected frequency exhausted')
  if not TURN.spend(staged,actor,'free','우리 친구 하자!'):
   raise ValueError('trainer Free action unavailable for Let Us Be Friends')
  # ch04:1283-1287 grants this target's attempt as the Free feature's effect.
  # It names no extra Pokemon Standard cost or general out-of-turn permission.
  rolled=_poffin_roll(staged,subject,'매력',FRIENDS,plan)
  FREQ.consume_activation(actor,FRIENDS,quota,engine=staged)
  return C.against_dc(rolled,dc)
 return _feature_transaction(e,trainer,resolve,performer,payload=(plan,))
