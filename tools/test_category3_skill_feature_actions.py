"""Actual source-bound Skill Monkey paths, including observed partial attempts."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,ExcludedRuleSelection
import skill_feature_actions as F
import common_checks as C
import action_points as AP
import downtime as DOWNTIME
import turn as TURN
class Sequence:
 def __init__(self,faces):self.faces=list(faces)
 def randint(self,a,b):return self.faces.pop(0)

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def fixture(self,r=None):
  self.e=Engine(r or self.r,seed=3)
  self.t=self.actor('t');self.b=self.actor('b');self.e.everyone=[self.t,self.b]
 def actor(self,name):
  return Combatant(self.e.r,dict(id='trainer/'+name,name=name,kind='trainer',level=20,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'육상':4,'곡예':4,'통찰':4},feats=[F.MONKEY]))
 def setUp(self):self.fixture()
 def opts(self,roll_id='r',**kw):
  result=dict(roll_id=roll_id,fixed=[1]*4,feature=F.MONKEY,feature_options={'decision':lambda first:True,'reroll_faces':[2]*4});result.update(kw);return result
 def used(self,actor=None):return (actor or self.t).spec.get('frequency_state',{}).get('activations',{}).get(F.MONKEY,{}).get('used',0)
 def roll(self,**kw):return self.e.skill_roll(self.t,'육상',**self.opts(**kw))
 def team(self,opts=None,**kw):
  arguments=dict(mode='team',participants=[self.t,self.b],required_people=2,equal_contribution=True,no_main_actor=True,action_id='team1',participant_options=opts or [self.opts('a'),self.opts('b')]);arguments.update(kw)
  return self.e.common_action(skill='육상',dc=9,**arguments)
 def extended(self,interval='i1',**kw):
  options=dict(mode='extended',task_id='task1',interval_id=interval,interval={'amount':1,'unit':'minute'},interval_completed=True,complexity=2,limited=True,**self.opts('extended-'+interval));options.update(kw)
  return self.e.common_action(self.t,'육상',dc=8,**options)
 def test_native_observed_first_optional_choice_new_dice_plus_two(self):
  seen=[];out=self.roll(feature_options={'decision':lambda first:seen.append(first) or True,'reroll_faces':[3]*4})
  self.assertEqual(seen,[C.SkillRoll(4,(1,1,1,1))]);self.assertEqual(out.total,14);self.assertEqual(self.used(),1)
  self.assertEqual(self.t._action_history,['free']);self.assertIs(F.event(self.e,self.t,'r').final,out)
 def test_decline_success_and_failed_checks_are_all_legal_choices(self):
  for initial in (1,6):
   self.fixture();out=self.roll(fixed=[initial]*4,feature_options={'decision':lambda first:False})
   self.assertEqual(out.total,initial*4);self.assertEqual(self.used(),0)
   self.assertFalse(getattr(self.t,'_action_history',[]))
  self.fixture();out=self.roll(fixed=[6]*4);self.assertEqual(out.total,10) # new result is mandatory, even worse
 def test_actual_prerequisites_identity_ownership_profile_and_aliases(self):
  mutations=[lambda:self.t.spec.update(feats=[]),lambda:self.t.spec.update(skills={'육상':4,'Athletics':4,'통찰':4}),lambda:self.t.spec.update(skills={'육상':4,'곡예':3,'통찰':4}),lambda:self.t.spec.update(id=''),lambda:setattr(self.t,'kind','pokemon')]
  for mutation in mutations:
   self.fixture();mutation();state=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.roll(fixed=None)
   self.assertEqual(self.e.rng.getstate(),state);self.assertFalse(self.e._ap_rolls);self.assertEqual(self.used(),0)
  r=Rules(ROOT);r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[F.MONKEY]});r._apply_ruleset();self.fixture(r)
  with self.assertRaises(ExcludedRuleSelection):self.roll()
 def test_invalid_declared_faces_and_missing_explicit_choice_are_before_first_roll(self):
  for options in ({'decision':True},{'decision':lambda first:True,'reroll_faces':[7]*4},{'decision':lambda first:True,'extra':1}):
   with self.assertRaises(ValueError):self.roll(feature_options=options,fixed=None)
   self.assertFalse(self.e._ap_rolls)
  with self.assertRaises(ValueError):self.roll(roll_id=None)
 def test_observed_choice_error_preserves_first_and_retry_cannot_change_it(self):
  self.e.rng=Sequence([1]*4+[6]*4)
  with self.assertRaises(ValueError):self.roll(fixed=None,feature_options={'decision':lambda first:'yes'})
  first=F.event(self.e,self.t,'r').first;self.assertEqual(first.faces,(1,1,1,1));self.assertEqual(self.e.rng.faces,[6]*4)
  with self.assertRaises(ValueError):self.roll(fixed=[6]*4)
  out=self.roll(fixed=None);self.assertEqual(out.total,10);self.assertEqual(self.e.rng.faces,[6]*4)
  self.assertIs(F.event(self.e,self.t,'r').first,first)
 def test_late_reroll_rng_error_keeps_first_but_rolls_back_new_cost(self):
  self.e.rng=Sequence([1]*4+[0,2,2,2])
  with self.assertRaises(ValueError):self.roll(fixed=None,feature_options={'decision':lambda first:True})
  self.assertEqual(F.event(self.e,self.t,'r').first.total,4);self.assertEqual(self.e.rng.faces,[0,2,2,2])
  self.assertEqual(self.used(),0);self.assertFalse(getattr(self.t,'_action_history',[]))
  self.roll(fixed=None);self.assertEqual(self.used(),1)
 def test_resolved_identity_cannot_reactivate_change_actor_or_recreate_initial_roll(self):
  self.roll();state=self.e.rng.getstate()
  for action in (lambda:self.roll(),lambda:self.e.skill_roll(self.t,'육상',roll_id='r'),lambda:self.e.skill_roll(self.b,'육상',**self.opts())):
   with self.assertRaises(ValueError):action()
  self.assertEqual(self.e.rng.getstate(),state);self.assertEqual(self.used(),1)
 def test_daily_three_in_one_scene_and_source_new_day_refresh(self):
  for i in range(3):self.roll(roll_id=str(i))
  with self.assertRaises(ValueError):self.roll(roll_id='fourth')
  self.assertNotIn('fourth',self.e._ap_rolls);DOWNTIME.new_day(self.t);self.roll(roll_id='nextday');self.assertEqual(self.used(),1)
 def test_real_ap_assistance_owned_edge_timing_and_penalty_carry_once(self):
  self.t.spec['edges']=['edge/스킬-향상'];self.t.spec['edge_choices']={'edge/스킬-향상':[['육상','곡예']]}
  self.e.boost_roll(self.t,self.t,roll_id='r',kind='skill');available=AP.available(self.t)
  out=self.roll(mods=1,helper_rank=4,helper_bonus=4,penalty_count=1,fixed_penalties=[3],feature_options={'decision':lambda first:True,'reroll_faces':[2]*4,'reroll_penalties':[1]})
  self.assertEqual(F.event(self.e,self.t,'r').first.total,9);self.assertEqual(out.total,17)
  self.assertEqual(AP.available(self.t),available)
 def test_common_action_actual_check_and_outcome_use_final_observed_roll(self):
  out=self.e.common_action(self.t,'육상',9,mode='skill',outcome='success',description='문을 연다',**self.opts())
  self.assertIsInstance(out,C.ActionOutcome);self.assertEqual(out.check,C.CheckResult(10,9,1,True))
  with self.assertRaises(ValueError):self.e.common_action(self.t,'육상',9,mode='skill',**self.opts())
 def test_common_assistance_derives_actual_helper_and_instruction(self):
  out=self.e.common_action(self.t,'육상',11,mode='skill',helper=self.b,**self.opts())
  self.assertEqual(out.check.total,12);self.assertTrue(out.check.passed)
 def test_native_check_closes_raw_observation_against_post_result_feature(self):
  self.e.skill_check(self.t,'육상',9,fixed=[1]*4,roll_id='r')
  with self.assertRaises(ValueError):self.roll()
 def test_triggered_free_outside_turn_and_status_permission_without_general_grant(self):
  self.e.start_round([self.t,self.b]);self.e.start_of_turn(self.b)
  self.assertFalse(TURN.spend(self.e,self.t,'free','ordinary'));self.roll()
  self.assertEqual(self.t._action_history,['free']);self.assertFalse(TURN.spend(self.e,self.t,'free','ordinary'))
  for condition in ('잠듦','얼음'):
   self.fixture();self.t.conditions.add(condition)
   with self.assertRaises(ValueError):self.roll()
   self.assertFalse(self.e._ap_rolls)
 def test_team_checks_use_final_rolls_and_cannot_consume_again(self):
  out=self.team();self.assertEqual(out.check.total,20);self.assertTrue(out.check.passed)
  self.assertEqual([self.used(self.t),self.used(self.b)],[1,1])
  with self.assertRaises(ValueError):self.team()
 def test_team_later_bad_choice_resumes_prior_final_without_new_dice_or_cost(self):
  options=[self.opts('a'),self.opts('b',feature_options={'decision':lambda first:'bad'})]
  with self.assertRaises(ValueError):self.team(options)
  self.assertEqual([self.used(self.t),self.used(self.b)],[1,0])
  first_a=F.event(self.e,self.t,'a').first;first_b=F.event(self.e,self.b,'b').first
  with self.assertRaises(ValueError):self.team([self.opts('a',fixed=[6]*4),self.opts('b')])
  out=self.team();self.assertEqual(out.check.total,20)
  self.assertIs(F.event(self.e,self.t,'a').first,first_a);self.assertIs(F.event(self.e,self.b,'b').first,first_b)
  self.assertEqual([self.used(self.t),self.used(self.b)],[1,1])
 def test_team_fully_validates_before_first_roll_and_rejects_reusing_elsewhere(self):
  self.b.spec['feats']=[]
  with self.assertRaises(ValueError):self.team()
  self.assertFalse(self.e._ap_rolls)
  self.fixture();self.roll(roll_id='a')
  with self.assertRaises(ValueError):self.team()
  self.assertEqual(self.used(),1)
 def test_extended_final_rolls_intervals_daily_cost_and_terminal_guard(self):
  first=self.extended();self.assertEqual(first.result.total,10);self.assertEqual(first.result.status,'in_progress')
  last=self.extended('i2');self.assertEqual(last.result.total,20);self.assertEqual(last.result.status,'complete');self.assertEqual(self.used(),2)
  with self.assertRaises(ValueError):self.extended('i3')
 def test_extended_choice_error_resumes_same_interval_without_new_first(self):
  with self.assertRaises(ValueError):self.extended(feature_options={'decision':lambda first:'invalid'})
  observed=F.event(self.e,self.t,'extended-i1').first
  out=self.extended();self.assertEqual(out.result.total,10);self.assertIs(F.event(self.e,self.t,'extended-i1').first,observed)
  with self.assertRaises(ValueError):self.extended()

 def test_source_full_scope_and_excerpt_hash(self):
  register=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
  row=next(x for x in register['entries'] if x['id']=='C3-EX-045')
  self.assertEqual(row['scope_sha256'],'b0acfc0122232e355a042e367fd7f0c0db27e04387d9b71b90d21f71a12f84cc')
  for anchor in row['source_snapshot']['source_anchors']:
   excerpt='\n'.join((ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines()[anchor['start_line']-1:anchor['end_line']])
   self.assertEqual(hashlib.sha256(excerpt.encode('utf-8')).hexdigest(),anchor['excerpt_sha256'])
 def test_native_opposed_tie_and_late_resume_keep_both_actual_rolls(self):
  a=self.opts('a');b=self.opts('b',feature_options={'decision':lambda first:'invalid'})
  with self.assertRaises(ValueError):self.e.opposed_check(self.t,'육상',self.b,'육상',challenger_options=a,defender_options=b)
  first=F.event(self.e,self.t,'a').first
  self.assertFalse(self.e.opposed_check(self.t,'육상',self.b,'육상',challenger_options=a,defender_options=self.opts('b')))
  self.assertIs(F.event(self.e,self.t,'a').first,first);self.assertEqual([self.used(self.t),self.used(self.b)],[1,1])
  with self.assertRaises(ValueError):self.e.opposed_check(self.t,'육상',self.b,'육상',challenger_options=a,defender_options=self.opts('b'))
 def test_source_opposed_context_resumes_and_preserves_selected_world_basis(self):
  self.t.spec['skills']['은신']=4
  options=dict(mode='context',case='stealth_detection',context={'purpose':'숨은 경비를 피한다'},target=self.b,defender_role='status_quo',challenger_options=self.opts('a'),defender_options=self.opts('b',feature_options={'decision':lambda first:'bad'}))
  with self.assertRaises(ValueError):self.e.common_action(self.t,**options)
  options['defender_options']=self.opts('b')
  out=self.e.common_action(self.t,**options);self.assertFalse(out.check.passed)
  self.assertEqual(out.basis['challenger_roll'].total,10);self.assertEqual(out.basis['defender_roll'].total,10)
  self.assertEqual(out.basis['case'],'stealth_detection');self.assertEqual([self.used(self.t),self.used(self.b)],[1,1])
  with self.assertRaises(ValueError):self.e.common_action(self.t,**options)
 def test_precise_actual_task_and_focus_feature_resume_no_repeat_cost(self):
  import precise_actions as PRECISE
  self.t.spec['skills']['집중']=4
  self.e.start_round([self.t,self.b]);self.e.start_of_turn(self.t)
  PRECISE.attacked(self.e,self.b,self.t,self.r.move('move/몸통박치기'))
  options=dict(mode='precise',context={'delicate':True,'activity':'ordinary_task','purpose':'도구를 세밀히 조정'},task_options=self.opts('task'),focus_options=self.opts('focus',feature_options={'decision':lambda first:'bad'}))
  with self.assertRaises(ValueError):self.e.common_action(self.t,'육상',8,**options)
  self.assertEqual(self.used(),1);first=F.event(self.e,self.t,'task').first
  options['focus_options']=self.opts('focus',feature_options={'decision':lambda first:True,'reroll_faces':[4]*4})
  out=self.e.common_action(self.t,'육상',8,**options)
  self.assertEqual(out.basis['ordinary_roll'].total,10);self.assertEqual(out.basis['focus_roll'].total,18)
  self.assertEqual(out.basis['focus_penalty'],0);self.assertTrue(out.check.passed);self.assertEqual(self.used(),2)
  self.assertIs(F.event(self.e,self.t,'task').first,first)
  with self.assertRaises(ValueError):self.e.common_action(self.t,'육상',8,**options)
 def test_weighted_team_mixed_ordinary_member_observation_survives_late_error(self):
  options=[{'roll_id':'a','fixed':[3]*4},self.opts('b',feature_options={'decision':lambda first:'bad'})]
  with self.assertRaises(ValueError):self.team(options,equal_contribution=False,contribution_weights=[2,1],weighting_reason='GM role weight')
  first=F.event(self.e,self.t,'a').first
  options[1]=self.opts('b')
  out=self.team(options,equal_contribution=False,contribution_weights=[2,1],weighting_reason='GM role weight')
  self.assertEqual(out.check.total,34);self.assertEqual(self.used(),0);self.assertIs(F.event(self.e,self.t,'a').first,first)

 def jump_fixture(self):
  from grid import Grid
  self.t.spec['size']='Medium';self.b.spec['size']='Medium'
  self.t.spec['movement']={'land':6,'power':6,'high_jump':2,'long_jump':3}
  self.t.pos=(1,1);self.b.pos=(10,8);self.e.grid=Grid(20,10)
  self.e.gm.everyone=self.e.everyone;self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t)
 def test_actual_jump_keeps_shift_and_feature_free_history_after_later_choice_error(self):
  self.jump_fixture()
  options=dict(jump_id='jump1',boost='long_jump',boost_options=self.opts('boost',feature_options={'decision':lambda first:True,'reroll_faces':[4]*4}),difficult=True,difficulty_skill='곡예',difficulty_dc=9,difficulty_options=self.opts('landing',feature_options={'decision':lambda first:'bad'}),clear_path=True,reason_text='GM actual arc and landing')
  with self.assertRaises(ValueError):self.e.jump(self.t,(5,1),**options)
  self.assertEqual(self.t.pos,(1,1));self.assertEqual(self.t.budget['shift'],0);self.assertEqual(self.used(),1)
  self.assertEqual(self.t._action_history,['shift','free']);self.assertIn('_jump_inflight',self.t.spec)
  self.assertIsInstance(self.e.jump(self.t,(5,1),**dict(options,jump_id='new')),C.PendingDecision)
  options['difficulty_options']=self.opts('landing')
  out=self.e.jump(self.t,(5,1),**options)
  self.assertTrue(out['landed']);self.assertEqual(self.t.pos,(5,1));self.assertEqual(self.t.budget['standard'],1)
  self.assertEqual(self.used(),2);self.assertEqual(self.t._action_history,['shift','free','free']);self.assertNotIn('_jump_inflight',self.t.spec)
  with self.assertRaises(ValueError):self.e.jump(self.t,(5,1),**options)
 def test_actual_jump_failed_boost_does_not_create_later_skill_roll_or_cost(self):
  self.jump_fixture()
  out=self.e.jump(self.t,(5,1),jump_id='jump2',boost='long_jump',boost_options=self.opts('boost'),difficult=True,difficulty_skill='곡예',difficulty_dc=9,difficulty_options=self.opts('landing'),clear_path=True,reason_text='GM actual arc and landing')
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(out.check.total,10)
  self.assertNotIn('landing',self.e._ap_rolls);self.assertEqual(self.used(),1);self.assertEqual(self.t.budget['shift'],0)
  self.assertEqual(self.t._action_history,['shift','free']);self.assertEqual(self.t.pos,(1,1))

 def test_actual_observed_sequence_snapshot_restores_pending_cost_and_same_rolls(self):
  self.e.gm.everyone=self.e.everyone;self.e.gm.snapshot('before')
  options=[self.opts('a'),self.opts('b',feature_options={'decision':lambda first:'bad'})]
  with self.assertRaises(ValueError):self.team(options)
  self.e.gm.snapshot('pending');self.assertEqual(self.used(),1)
  first=F.event(self.e,self.t,'a').first
  options[1]=self.opts('b');self.assertTrue(self.team(options).check.passed)
  self.e.gm.restore('pending')
  self.assertEqual(self.used(),1);self.assertEqual(self.used(self.b),0)
  self.assertEqual(F.event(self.e,self.t,'a').first,first)
  self.assertTrue(self.team(options).check.passed);self.assertEqual(self.used(),1);self.assertEqual(self.used(self.b),1)
  self.e.gm.restore('before');self.assertFalse(hasattr(self.e,'_skill_sequences'));self.assertFalse(self.e._ap_rolls)
  self.assertTrue(self.team(options).check.passed);self.assertEqual(self.used(),1)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/skill_feature_actions.py','engine/engine.py','engine/common_action_checks.py','engine/contest_features.py','engine/skill_modifiers.py','engine/common_checks.py','engine/resolution_transaction.py','engine/ap_roll_bonus.py','engine/frequency.py','engine/action_lifecycle.py','engine/turn.py','data/skill-check-policy.json','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','tools/test_category3_skill_feature_actions.py']
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 paths+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py') if str(p.relative_to(ROOT)).replace('\\','/') not in paths)
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-045'],'completion_scopes':['C3-EX-045'],'partial_scopes':[],'source_scope_sha256':'b0acfc0122232e355a042e367fd7f0c0db27e04387d9b71b90d21f71a12f84cc','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-skill-feature-actions-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())

