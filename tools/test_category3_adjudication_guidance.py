"""Native GM guidance and ordinary/specific Pokemon knowledge source audit."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import common_checks as C
import skill_feature_actions as SF
from ruleset import RuleFilter,ExcludedRuleSelection
CLAUSES=['C3-CORE-014','C3-CORE-064','C3-CORE-065','C3-CORE-066','C3-CORE-075','C3-CORE-076']
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=829)
  self.a=Combatant(self.r,{'id':'trainer/a','name':'A','kind':'trainer','level':20,'stats':{'hp':20,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'skills':{'포켓몬학':'미숙','교활':'숙련','곡예':'초보'},'items':{}})
  self.p=Combatant(self.r,{'id':'pokemon/p','name':'P','kind':'pokemon','species':'pokemon/포푸니라','level':20,'types':['얼음','악'],'stats':{'hp':20,'atk':10,'def':10,'spa':10,'spd':10,'spe':10}})
  self.e.everyone=self.e.gm.everyone=[self.a,self.p]
 def knowledge(self,topic='type',**kw):return self.e.pokemon_knowledge(self.a,self.p,topic,**kw)
 def test_source_scopes_and_printed_rank_values_unchanged(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text('utf-8'))['entries']
  for row in rows:
   if row['id'] not in CLAUSES:continue
   s=row['source_snapshot']['source'];actual='\n'.join((ROOT/s['file']).read_text('utf-8-sig').splitlines()[s['start']-1:s['end']])
   self.assertEqual(actual,s['excerpt']);self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(),s['excerpt_sha256'])
  p=self.e.difficulty_guidance()
  self.assertEqual(p['rank_dc_guide'],{'미숙':7,'초보':10,'숙련':13,'전문':17,'달인':21})
  self.assertIn('4d6 mathematical mean is14',p['average_wording'])
 def test_guide_is_not_auto_dc_or_prerequisite(self):
  state=self.e.rng.getstate()
  out=self.e.common_action(self.a,'교활',mode='skill',difficulty_context={'reference_rank':'숙련','reason':'GM considering a moderately difficult task'})
  self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check);self.assertEqual(self.e.rng.getstate(),state)
  self.assertEqual(out.basis['difficulty_guidance']['reference_dc'],13)
  self.assertIsNone(out.basis['difficulty_guidance']['selected_dc'])
  out=self.e.common_action(self.a,'교활',17,mode='skill',fixed=[4,4,4,5],difficulty_context={'reference_rank':'달인','reason':'low rank may attempt this task'})
  self.assertTrue(out.check.passed);self.assertEqual(out.check.dc,17)
 def test_context_examples_are_optional_not_a_prose_classifier(self):
  for dc,tone,passed in [(12,'anime',True),(14,'anime',False),(20,'realistic',False),(1,'custom campaign',True)]:
   out=self.e.common_action(self.a,'곡예',dc,mode='skill',fixed=[4,4,4],declaration={'action':'지나가는 비행선에 뛴다'},difficulty_context={'tone':tone,'realism':'GM world assumptions','task_context':'same described jump','reason':'GM selected this difficulty'})
   self.assertEqual(out.check.passed,passed);self.assertEqual(out.check.dc,dc)
   self.assertEqual(out.basis['difficulty_guidance']['selected_dc'],dc)
  self.assertEqual(self.a.pos,(0,0)) # Checking this ordinary example does not execute a jump.
 def test_modifier_changes_roll_once_not_guide_or_dc(self):
  out=self.e.common_action(self.a,'교활',17,mode='skill',fixed=[3,4,3,4],mods=3,difficulty_context={'reference_rank':'숙련','reason':'rare model problem and actual research modifier'})
  self.assertEqual((out.check.total,out.check.dc,out.check.margin),(17,17,0));self.assertTrue(out.check.passed)
  self.assertEqual(out.basis['difficulty_guidance']['reference_dc'],13)
 def test_disagreement_preserves_gm_selection_without_pause_or_reroll(self):
  disagreement={'player_reason':'군중 속에 숨으니 은신을 제안','gm_reason':'동행인 척하므로 교활'}
  out=self.e.common_action(self.a,'교활',10,mode='skill',fixed=[2,2,3,3],declaration={'action':'상대를 뒤따른다','proposed_skill':'은신'},disagreement=disagreement)
  self.assertTrue(out.check.passed);self.assertEqual(out.check.total,10)
  self.assertEqual(out.declaration['proposed_skill'],'은신')
  self.assertEqual(out.basis['disagreement']['current_gm_selection'],{'mode':'skill','skill':'교활','dc':10})
  self.assertEqual(out.basis['disagreement']['guidance']['review_timing'],'after_session_recommended')
  self.assertFalse(out.basis['disagreement']['guidance']['force_pause'])
  disagreement['player_reason']='changed';self.assertNotEqual(out.basis['disagreement']['player_reason'],'changed')
 def test_advice_keeps_existing_context_basis_and_extended_result(self):
  out=self.e.common_action(self.a,mode='context',case='general_knowledge',context={'purpose':'옛 역사의 일반 지식 확인'},disagreement={'player_reason':'다른 스킬 제안','gm_reason':'교활 사용'})
  # Context still awaits the actual GM DC; advice cannot convert it into success.
  self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  self.assertIn('disagreement',out.basis);self.assertEqual(out.basis['case'],'general_knowledge')
  out=self.e.common_action(self.a,'교활',5,mode='extended',task_id='research',interval_id='one',interval={'amount':1,'unit':'hour'},interval_completed=True,complexity=2,limited=True,fixed=[3]*4,difficulty_context={'reason':'GM extended research DC'})
  self.assertTrue(out.outcome.check.passed);self.assertIn('difficulty_guidance',out.outcome.basis)
 def test_invalid_advice_before_any_rng(self):
  before=self.e.rng.getstate()
  for kw in [{'difficulty_context':{}},{'difficulty_context':{'reason':'x','reference_rank':'불능'}},{'difficulty_context':{'reason':'x','automatic_dc':10}},{'disagreement':{'player_reason':'x'}}]:
   with self.assertRaises(ValueError):self.e.common_action(self.a,'교활',10,mode='skill',**kw)
  self.assertEqual(self.e.rng.getstate(),before)
 def test_basic_known_species_untrained_rank_no_roll_with_explicit_information(self):
  state=self.e.rng.getstate()
  for topic in ('type','type_interaction','battle_role'):
   out=self.knowledge(topic,species_known=True,responses={'success':'GM이 공개한 해당 종 기본 상식'})
   self.assertIsInstance(out,C.ActionOutcome);self.assertIsNone(out.check);self.assertEqual(out.basis['knowledge']['education_rank'],2)
  self.assertEqual(self.e.rng.getstate(),state);self.assertFalse(getattr(self.a,'_action_history',[]))
 def test_no_automatic_private_information_even_when_basic_access_is_allowed(self):
  self.p.spec.update(hidden_item='비밀 장비',hidden_trait='비밀 변종');out=self.knowledge(species_known=True)
  self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  self.assertNotIn('비밀',repr(out));self.assertNotIn('types',repr(out.basis));self.assertNotIn('moves',repr(out.basis))
 def test_incapable_unknown_undiscovered_species_need_actual_gm_agreement(self):
  state=self.e.rng.getstate()
  for rank,familiar in [('불능',True),('미숙',False),('미숙',None)]:
   self.a.spec['skills']['포켓몬학']=rank;out=self.knowledge(species_known=familiar,responses={'success':'not automatically accepted'})
   self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  self.assertEqual(self.e.rng.getstate(),state)
  out=self.knowledge(species_known=False,method='known',reason='GM: 이 개체를 이전에 관찰해 타입을 배웠다',responses={'success':'관찰했던 타입을 기억한다'})
  self.assertIsInstance(out,C.ActionOutcome)
 def test_behavior_biology_need_selected_method_and_dc(self):
  state=self.e.rng.getstate()
  for topic in ('behavior','biology'):
   out=self.knowledge(topic,species_known=True);self.assertIsInstance(out,C.PendingDecision)
   out=self.knowledge(topic,species_known=True,method='skill',reason='GM asks for additional knowledge')
   self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  self.assertEqual(self.e.rng.getstate(),state)
 def test_actual_education_check_equality_and_failure_information(self):
  for faces,expected in [([3,4],True),([3,3],False)]:
   out=self.knowledge('biology',species_known=True,method='skill',reason='GM biology question',dc=7,fixed=faces,responses={'success':'물가에서 생활한다','failure':'이 행동의 생물학적 원인은 알아내지 못했다'})
   self.assertEqual(out.check.passed,expected)
   self.assertEqual(out.description,'물가에서 생활한다' if expected else '이 행동의 생물학적 원인은 알아내지 못했다')
 def test_failed_check_without_gm_consequence_preserves_observation_and_waits(self):
  out=self.knowledge('behavior',method='skill',reason='GM behavior question',dc=7,fixed=[1,1],responses={'success':'secret successful answer'})
  self.assertIsInstance(out,C.PendingDecision);self.assertFalse(out.check.passed);self.assertNotIn('secret',repr(out))
  self.assertEqual(self.a.hp,self.a.max_hp)
 def test_specific_knowledge_requires_explicit_high_rank_threshold_or_pokedex(self):
  self.a.spec['skills']['포켓몬학']='전문';state=self.e.rng.getstate()
  for topic in ('learnset','growth_abilities'):
   out=self.knowledge(topic,method='skill',reason='GM precise knowledge',dc=17)
   self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
   out=self.knowledge(topic,method='skill',reason='GM chooses Master for this obscure information',high_rank_requirement=6,dc=17)
   self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  self.assertEqual(self.e.rng.getstate(),state)
  out=self.knowledge('learnset',method='skill',reason='GM chooses Expert for this information',high_rank_requirement=5,dc=17,fixed=[3,3,3,4,4],responses={'success':'GM이 확인한 학습 목록'})
  self.assertTrue(out.check.passed)
 def test_known_specific_information_cannot_bypass_the_high_rank_gate(self):
  state=self.e.rng.getstate()
  out=self.knowledge('learnset',method='known',reason='request alone does not establish high knowledge',responses={'success':'not authorized automatically'})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.e.rng.getstate(),state)
  self.a.spec['skills']['포켓몬학']='전문'
  out=self.knowledge('learnset',method='known',reason='GM recognizes prior learning',high_rank_requirement=5,responses={'success':'이전에 익힌 학습 목록'})
  self.assertIsInstance(out,C.ActionOutcome)
 def test_actual_pokedex_ownership_existing_entry_no_implicit_scan(self):
  before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.knowledge('learnset',method='pokedex',reason='read existing entry',pokedex_has_entry=True)
  self.a.spec['items']['포켓몬 도감']=1
  for available in (None,False):
   out=self.knowledge('learnset',method='pokedex',reason='read existing entry',pokedex_has_entry=available)
   self.assertIsInstance(out,C.PendingDecision)
  out=self.knowledge('learnset',method='pokedex',reason='GM confirms existing downloaded entry',pokedex_has_entry=True,responses={'success':'도감의 기존 학습 정보'})
  self.assertIsNone(out.check);self.assertIsInstance(out,C.ActionOutcome)
  self.assertEqual(self.e.rng.getstate(),before);self.assertFalse(getattr(self.a,'_action_history',[]))
  self.assertEqual(self.a.spec['items']['포켓몬 도감'],1)
 def test_excluded_pokedex_and_duplicate_inventory_aliases_reject(self):
  r=Rules(str(ROOT),ruleset='core');r.ruleset=RuleFilter({'sources':['core'],'exclude_units':['item/포켓몬-도감']});r._apply_ruleset()
  self.e.r=self.a.r=self.p.r=r;self.a.spec['items']['포켓몬 도감']=1
  with self.assertRaises(ExcludedRuleSelection):self.knowledge('learnset',method='pokedex',reason='read',pokedex_has_entry=True)
  self.setUp();self.a.spec['items']={'포켓몬 도감':1,'포켓몬도감':1}
  with self.assertRaises(ValueError):self.knowledge('learnset',method='pokedex',reason='read',pokedex_has_entry=True)
 def test_actual_variant_types_survive_expected_species_knowledge_and_combat(self):
  self.e.gm.set_types(self.p,['얼음','불꽃'],reason='GM selected regional variant source for this individual')
  out=self.knowledge(species_known=True,responses={'success':'통상 포푸니라는 얼음/악 타입이다'})
  self.assertIn('얼음/악',out.description);self.assertEqual(self.p.types,['얼음','불꽃'])
  self.assertEqual(self.e.type_multiplier('물',self.p)[0],1.5)
  out=self.knowledge(species_known=True,method='known',reason='GM reveals observed variant type',responses={'success':'이 개체는 얼음/불꽃 타입이다'})
  self.assertIn('얼음/불꽃',out.description);self.assertEqual(out.basis['knowledge']['subject_id'],self.p.spec['id'])
 def test_rank_alias_conflicts_invalid_face_and_unconscious_before_rng(self):
  state=self.e.rng.getstate();self.a.spec['skills']['Pokemon Education']='전문'
  with self.assertRaises(ValueError):self.knowledge(species_known=True)
  self.a.spec['skills'].pop('Pokemon Education')
  with self.assertRaises(ValueError):self.knowledge('biology',method='skill',reason='GM check',dc=7,fixed=[7,1])
  self.a.hp=0;out=self.knowledge(species_known=True,responses={'success':'cannot act'})
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.e.rng.getstate(),state)
 def test_native_skill_monkey_and_difficulty_guidance_in_knowledge(self):
  self.a.spec.update(skills={'포켓몬학':'숙련','곡예':'숙련','육상':'숙련'},feats=[SF.MONKEY])
  out=self.knowledge('biology',method='skill',reason='GM studies actual biology',dc=13,fixed=[1]*4,roll_id='biology-reroll',feature=SF.MONKEY,feature_options={'decision':lambda first:True,'reroll_faces':[3]*4},difficulty_context={'reference_rank':'숙련','reason':'explicit actual DC'},responses={'success':'생물학적 요구를 알아낸다'})
  self.assertTrue(out.check.passed);self.assertEqual(out.check.total,14)
  self.assertIn('difficulty_guidance',out.basis);self.assertIn('knowledge',out.basis)
  self.assertEqual(self.a.spec['frequency_state']['activations'][SF.MONKEY]['used'],1)
 def test_no_roll_knowledge_cannot_consume_dice_or_grant_ap_and_effects(self):
  before=deepcopy((self.a.spec,self.a.hp,self.p.spec,self.e.rng.getstate()))
  with self.assertRaises(ValueError):self.knowledge(species_known=True,fixed=[6,6])
  self.assertEqual(before,(self.a.spec,self.a.hp,self.p.spec,self.e.rng.getstate()))
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/cultivation-policy.json','engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/engine.py','engine/common_action_checks.py','engine/common_checks.py','engine/context_actions.py','data/context-check-policy.json','engine/skill_modifiers.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/ap_roll_bonus.py','engine/action_points.py','engine/turn.py','engine/action_lifecycle.py','engine/contest_features.py','engine/frequency.py','engine/food_effects.py','engine/skill_maneuver_actions.py','engine/ruleset.py','engine/gm_state.py','data/core-rules.json','data/skill-check-policy.json','data/rulesets.json','data/items-mech.json','input/ch06-gameplay.md','input/ch11-running-the-game.md','input/ch09-equipment.md','tools/test_category3_adjudication_guidance.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':CLAUSES,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'boundaries':['Advice is not a forced pause, automatic DC, task list, or new rule display UI.','Knowledge answers are explicit GM information, not automatic access to secret individual sheets.','Pokedex path reads GM-confirmed existing entries on owned devices; scanning/acquisition is an independent item procedure.','Very specific knowledge threshold and check DC remain explicit GM choices because the source does not fix them.']}
 (ROOT/'output/category3-adjudication-guidance-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
