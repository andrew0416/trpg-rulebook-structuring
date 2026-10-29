"""Fixed Skill Stunt scope through actual native consumers, not rank mutation."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from grid import Grid
from ruleset import RuleFilter,ExcludedRuleSelection
import skill_stunts as ST
import skill_feature_actions as SF
import common_checks as C
import turn as TURN
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self):
  self.e=Engine(self.r,seed=7)
  self.a=Combatant(self.r,{'id':'trainer/a','name':'A','pos':(0,0),'kind':'trainer','size':'medium','level':20,'stats':dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=10),'skills':{'기술학':3,'곡예':4,'육상':4,'생존':4,'오컬트학':3},'edges':[ST.SOURCE],'feats':[SF.MONKEY],'movement':{'land':6,'high_jump':1,'long_jump':2}})
  self.b=Combatant(self.r,{'id':'trainer/b','name':'B','kind':'trainer','size':'medium','level':20,'stats':dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=10),'skills':{'기술학':3,'곡예':4,'육상':4},'pos':(1,0)})
  self.e.everyone=[self.a,self.b]
 def approve(self,identity='repair',skill='기술학',use='고장 난 선박 엔진 배선 진단',**kw):
  options=dict(choice_id=identity,skill=skill,use=use,reason='GM sufficiently narrow and suitable use',approved=True);options.update(kw)
  return self.e.approve_skill_stunt(self.a,**options)
 def use(self,choice='repair',apply=True,matches=True):return {'choice_id':choice,'apply':apply,'matches_approved_use':matches,'reason':'GM actual task matches the approved narrow situation'}
 def test_optional_replacement_rolls_one_fewer_d6_plus_six_with_rank_preserved(self):
  self.approve();out=self.e.skill_roll(self.a,'기술학',fixed=[2,3],skill_stunt=self.use())
  self.assertIsInstance(out,C.AdjustedSkillRoll);self.assertEqual((out.rank,out.dice_count,out.faces,out.total),(3,2,(2,3),11))
  ordinary=self.e.skill_roll(self.a,'기술학',fixed=[1,2,3]);declined=self.e.skill_roll(self.a,'기술학',fixed=[1,2,3],skill_stunt=self.use(apply=False))
  self.assertEqual(ordinary,declined);self.assertIsInstance(declined,C.SkillRoll);self.assertEqual(declined.total,6)
 def test_actual_native_check_uses_replacement_for_dc_and_equality(self):
  self.approve();passed,total=self.e.skill_check(self.a,'기술학',10,fixed=[2,2],skill_stunt=self.use())
  self.assertTrue(passed);self.assertEqual(total,10)
 def test_approval_refusal_and_invalid_prerequisites_do_not_assign_choice(self):
  result=self.approve(approved=False);self.assertEqual(result['status'],'gm_rejected');self.assertNotIn('edge_choices',self.a.spec)
  self.a.spec['skills']['기술학']=2
  with self.assertRaises(ValueError):self.approve()
  self.assertNotIn('edge_choices',self.a.spec)
  self.a.spec['edges']=[]
  with self.assertRaises(ValueError):self.approve(skill='육상')
 def test_multiple_acquisitions_bind_distinct_approved_situations(self):
  self.a.spec['edges'].append(ST.SOURCE);self.approve();self.approve('escape','곡예','선박 난간에 걸린 밧줄 빠져나오기')
  self.assertEqual(len(ST.choices(self.e,self.a)),2)
  self.assertEqual(self.e.skill_roll(self.a,'곡예',fixed=[1]*3,skill_stunt=self.use('escape')).total,9)
  with self.assertRaises(ValueError):self.approve('third','생존','표류 중 소금기 없는 웅덩이 찾기')
 def test_same_situation_repeat_uses_one_choice_and_mismatch_rejects_before_rng(self):
  self.a.spec['edges'].append(ST.SOURCE);self.approve()
  self.approve('again','Technology Education','고장 난 선박 엔진 배선 진단')
  for choice in ('repair','again'):
   self.assertEqual(self.e.skill_roll(self.a,'기술학',fixed=[1,1],skill_stunt=self.use(choice)).total,8)
  state=self.e.rng.getstate()
  for skill,decl in [('육상',self.use()),('기술학',self.use('missing')),('기술학',self.use(matches=False))]:
   with self.assertRaises(ValueError):self.e.skill_roll(self.a,skill,skill_stunt=decl)
  self.assertEqual(self.e.rng.getstate(),state)
 def test_unapproved_imported_or_unowned_choice_cannot_grant_stunt(self):
  self.a.spec['edge_choices']={ST.SOURCE:[{'id':'repair','skill':'기술학','use':'진단','gm_approved':False}]}
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'기술학',skill_stunt=self.use())
  self.a.spec['edge_choices'][ST.SOURCE][0]['gm_approved']=True;self.a.spec['edges']=[]
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'기술학',skill_stunt=self.use())
 def test_legacy_choice_is_normalized_without_inventing_second_acquisition(self):
  self.a.spec['edge_choices']={'고난이도 스킬':[{'skill':'기술학','use':'선박 진단','gm_approved':True}]}
  self.assertEqual(self.e.skill_roll(self.a,'기술학',fixed=[1,1],skill_stunt=self.use('legacy:0')).total,8)
  self.a.spec['edge_choices'][ST.SOURCE]=deepcopy(self.a.spec['edge_choices']['고난이도 스킬'])
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'기술학',skill_stunt=self.use('legacy:0'))
 def test_player_declines_without_matching_situation_and_no_bonus(self):
  self.approve();out=self.e.skill_roll(self.a,'기술학',fixed=[2]*3,skill_stunt=self.use(apply=False,matches=False));self.assertEqual(out.total,6)
 def test_wrong_replacement_faces_fail_before_rng_or_observation(self):
  self.approve();state=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'기술학',fixed=[1]*3,skill_stunt=self.use(),roll_id='bad')
  self.assertEqual(self.e.rng.getstate(),state);self.assertFalse(self.e._ap_rolls)
 def test_native_assistance_penalties_and_other_modifiers_remain_once(self):
  self.approve();self.b.spec['skills']['기술학']=4
  out=self.e.common_action(self.a,'기술학',11,mode='skill',roll_purpose='고장 난 선박 엔진 배선 진단',fixed=[2,3],skill_stunt=self.use(),mods=1,helper=self.b,helper_skill='기술학',penalty_count=1,fixed_penalties=[3])
  self.assertEqual(out.check.total,11);self.assertTrue(out.check.passed)
 def test_skill_monkey_rerolls_reduced_pool_and_keeps_six_once(self):
  self.approve();out=self.e.skill_roll(self.a,'기술학',fixed=[1,1],skill_stunt=self.use(),roll_id='r',feature=SF.MONKEY,feature_options={'decision':lambda first:True,'reroll_faces':[2,3]})
  self.assertEqual(SF.event(self.e,self.a,'r').first.total,8);self.assertEqual((out.rank,out.dice_count,out.total),(3,2,13))
  self.assertEqual(self.a._action_history,['free'])
 def test_observed_stunt_choice_cannot_change_during_reroll_retry(self):
  self.approve();options=dict(fixed=[1,1],skill_stunt=self.use(),roll_id='r',feature=SF.MONKEY,feature_options={'decision':lambda first:'bad'})
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'기술학',**options)
  first=SF.event(self.e,self.a,'r').first
  options.update(skill_stunt=self.use(apply=False),feature_options={'decision':lambda first:False})
  with self.assertRaises(ValueError):self.e.skill_roll(self.a,'기술학',**options)
  options['skill_stunt']=self.use();out=self.e.skill_roll(self.a,'기술학',**options);self.assertEqual(out,first)
 def test_extended_attempt_limit_uses_base_rank_not_reduced_pool(self):
  self.a.spec['skills']['기술학']=4;self.approve();out=self.e.common_action(self.a,'기술학',10,mode='extended',task_id='repair',interval_id='one',interval={'amount':1,'unit':'minute'},interval_completed=True,complexity=5,limited=True,fixed=[1,1,1],skill_stunt=self.use())
  self.assertEqual((out.result.attempt_limit,out.result.attempts_used,out.result.total),(2,1,9))
 def test_native_team_and_opposed_consume_actual_modified_roll(self):
  self.approve();out=self.e.common_action(skill='기술학',dc=7,mode='team',participants=[self.a,self.b],required_people=2,equal_contribution=True,no_main_actor=True,participant_options=[{'fixed':[1,1],'skill_stunt':self.use()},{'fixed':[2]*3}])
  self.assertEqual(out.check.total,14);self.assertTrue(out.check.passed)
  self.assertTrue(self.e.opposed_check(self.a,'기술학',self.b,'기술학',challenger_options={'fixed':[1,1],'skill_stunt':self.use()},defender_options={'fixed':[2]*3}))
 def test_actual_jump_boost_uses_replaced_pool_without_changing_capability_rank(self):
  self.approve('jump','곡예','선박 난간에서 수평 도약');self.e.grid=Grid(6,3);self.a.pos=(0,1);self.b.pos=(5,2)
  self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a,initiative_count=20)
  out=self.e.jump(self.a,(3,1),jump_id='jump-stunt',difficult=False,boost='long_jump',boost_options={'fixed':[3,3,4],'skill_stunt':self.use('jump')},clear_path=True,reason_text='GM actual clear jump arc')
  self.assertEqual(self.a.pos,(3,1));self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a.spec['skills']['곡예'],4)
 def test_actual_trip_opposed_stunt_winner_commits_real_tripped_status(self):
  self.approve('balance','곡예','선박 갑판 상대 발걸기');self.a.side='party';self.b.side='enemy';self.e.grid=Grid(4,1);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
  won=self.e.trip(self.a,self.b,challenger_skill='곡예',defender_skill='곡예',fixed_accuracy=20,challenger_options={'fixed':[1]*3,'skill_stunt':self.use('balance')},defender_options={'fixed':[2]*4})
  self.assertTrue(won);self.assertIn('넘어짐',self.b.conditions);self.assertEqual(self.a.budget['standard'],0)
 def test_dowsing_source_exception_remains_plus_one_die_not_plus_six(self):
  self.approve('dowse','오컬트학','다우징');self.a.spec['items']={'다우징 로드':1}
  out=self.e.pokemon_activity(self.a,'dowse',outdoors=True,fixed={'0':1,'1':1,'2':1,'3':1})
  self.assertEqual(out['pool'],4);self.assertFalse(out['gained']);self.assertEqual(len(out['results']),4);self.assertEqual(self.e.elapsed_seconds,600)
 def test_repeated_approved_dowsing_choices_do_not_multiply_exception(self):
  self.a.spec['edges'].append(ST.SOURCE)
  self.approve('dowsing-one','오컬트학','다우징');self.approve('dowsing-two','오컬트학','다우징')
  self.assertTrue(ST.for_dowsing(self.e,self.a))

 def test_fixed_snapshot_source_hashes_unchanged(self):
  row=next(r for r in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if r['id']=='C3-EX-015')
  self.assertEqual(row['scope_sha256'],'ed3654eadddcec35996aa6ff254372f6254038848493b51335fb0ac964c27360')
  for a in row['source_snapshot']['source_anchors']:
   excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']]);self.assertEqual(excerpt,a['excerpt']);self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py'))+['input/ch03-skills-edges-feats.md','input/ch09-equipment.md','tools/test_category3_skill_stunts.py','data/skill-check-policy.json','data/adjudication-guidance.json']
 paths=[p for p in paths if (ROOT/p).exists()]
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-015'],'completion_scopes':['C3-EX-015'],'partial_scopes':[],'source_scope_sha256':'ed3654eadddcec35996aa6ff254372f6254038848493b51335fb0ac964c27360','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-skill-stunt-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
