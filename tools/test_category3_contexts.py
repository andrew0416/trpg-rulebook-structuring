"""Actual ordinary and opposed skill contexts with explicit GM purpose."""
import sys,json,hashlib,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import common_checks as C
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=817);self.a=self.actor('a');self.b=self.actor('b')
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
 def actor(self,name):return Combatant(self.r,{'id':name,'name':name,'kind':'trainer','level':20,'stats':{'hp':20,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},'skills':{s:'숙련' for s in ['협박','은신','통찰','집중','기술학','오컬트학','생존','일반 지식','매력','명령','교활','직감','곡예']}})
 def context(self,case,**opts):
  context={'purpose':'GM specified attempted action','competing_threats':True,'precise_or_difficult_task':True,'opponent_created_device_or_magic':True};context.update(opts.pop('context',{}))
  return self.e.common_action(self.a,mode='context',case=case,context=context,**opts)
 def opposed(self,case,**opts):
  defaults={'target':self.b,'defender_role':'status_quo','challenger_options':{'fixed':[4]*4},'defender_options':{'fixed':[3]*4}};defaults.update(opts)
  return self.context(case,**defaults)
 def test_source_scoped_anchors_unchanged(self):
  ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))
  for e in ledger['entries']:
   if e['id'] not in ['C3-EX-008','C3-EX-009','C3-EX-010','C3-EX-011','C3-EX-012','C3-EX-013']:continue
   for a in e['source_snapshot']['source_anchors']:
    lines=(ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines();self.assertEqual(hashlib.sha256('\n'.join(lines[a['start_line']-1:a['end_line']]).encode()).hexdigest(),a['excerpt_sha256'])
 def test_ordinary_intimidation_uses_gm_dc_and_never_invents_resistance(self):
  result=self.context('intimidation',dc=16,fixed=[4]*4)
  self.assertEqual(result.basis['roll_plan']['purpose'],'GM specified attempted action')
  self.assertEqual(result.basis['roll_plan']['actor_id'],self.a.entity_id)
  self.assertIsInstance(result,C.PendingDecision);self.assertTrue(result.check.passed);self.assertEqual(result.basis['skill'],'협박');self.assertNotIn('defender_roll',result.basis)
  with self.assertRaises(ValueError):self.context('intimidation',dc=16,target=self.b)
 def test_intimidation_does_not_auto_control_or_improve_relationship(self):
  before=dict(self.b.spec);out=self.context('intimidation',dc=4,fixed=[6]*4)
  self.assertIsInstance(out,C.PendingDecision);self.assertEqual(self.b.spec,before);self.assertIn('not automatic control',out.basis['world_note'])
 def test_mutual_threats_use_both_real_intimidation_ranks(self):
  self.b.spec['skills']['협박']='초보'
  out=self.opposed('mutual_intimidation',defender_options={'fixed':[5]*3})
  self.assertEqual([(p['actor_id'],p['target_id']) for p in out.basis['roll_plans']],[(self.a.entity_id,self.b.entity_id),(self.b.entity_id,self.a.entity_id)])
  self.assertEqual((out.check.total,out.check.dc),(16,15));self.assertEqual(len(out.basis['defender_roll'].faces),3)
 def test_disrupting_precise_work_uses_intimidation_vs_focus(self):
  self.b.spec['skills']['집중']='달인';self.b.spec['skills']['협박']='취약'
  out=self.opposed('disrupt_concentration',defender_options={'fixed':[3]*6})
  self.assertFalse(out.check.passed);self.assertEqual((out.basis['defender_skill'],out.check.dc),('집중',18))
 def test_stealth_detection_uses_perception_not_intuition(self):
  self.b.spec['skills']['통찰']='초보';self.b.spec['skills']['직감']='달인'
  out=self.opposed('stealth_detection',defender_options={'fixed':[4]*3})
  self.assertEqual((out.basis['skill'],out.basis['defender_skill'],out.check.dc),('은신','통찰',12))
 def test_restraint_and_lock_use_gm_selected_actual_creator_skill(self):
  for skill in ['기술학','오컬트학']:
   out=self.opposed('escape_restraint',defender_skill=skill);self.assertEqual(out.basis['defender_skill'],skill);self.assertTrue(out.check.passed)
 def test_examples_do_not_forbid_another_explicitly_relevant_skill(self):
  out=self.opposed('escape_restraint',defender_skill='생존');self.assertIsInstance(out,C.PendingDecision);self.assertIsNone(out.check)
  out=self.opposed('escape_restraint',defender_skill='생존',context={'relevance_reason':'creator tied a wilderness trapping knot'})
  self.assertEqual(out.basis['defender_skill'],'생존');self.assertTrue(out.check.passed)
 def test_status_quo_tie_is_defender_win_and_symmetric_case_waits_for_ruling(self):
  out=self.opposed('stealth_detection',defender_options={'fixed':[4]*4});self.assertFalse(out.check.passed);self.assertEqual(out.check.margin,0)
  before=self.e.rng.getstate();out=self.opposed('mutual_intimidation',defender_role=None);self.assertIsNone(out.check);self.assertEqual(self.e.rng.getstate(),before)
 def test_missing_context_and_late_invalid_actor_do_not_consume_rng(self):
  before=self.e.rng.getstate();out=self.opposed('disrupt_concentration',context={'precise_or_difficult_task':False});self.assertIsNone(out.check)
  with self.assertRaises(ValueError):self.opposed('stealth_detection',challenger_options={},defender_options={'fixed':[2]})
  self.assertEqual(self.e.rng.getstate(),before)
 def test_failed_check_preserves_gm_consequence_and_declaration(self):
  out=self.context('intimidation',dc=30,fixed=[4]*4,outcome='failure',description='NPC refuses and regards the threat as hostile',declaration={'action':'threaten guard','intent':'obtain entry','activity':'ordinary'})
  self.assertEqual(out.outcome,'failure');self.assertFalse(out.check.passed);self.assertEqual(out.declaration['intent'],'obtain entry')
 def test_wilderness_dc_examples_are_guidance_and_actual_gm_dc_is_used(self):
  out=self.context('wilderness_survey',context={'wilderness_task':True})
  self.assertIsNone(out.check);self.assertEqual(out.basis['source_dc_examples'],{'savanna_or_small_forest':12,'foggy_wetland':16,'rainforest_or_arctic':'20+'})
  out=self.context('wilderness_survey',dc=14,fixed=[4]*4,context={'wilderness_task':True})
  self.assertEqual((out.check.total,out.check.dc),(16,14));self.assertTrue(out.check.passed);self.assertNotIn('items',self.a.spec)
 def test_rare_signs_consistent_default_uses_original_dc_and_preserves_conflicting_text(self):
  out=self.context('rare_wilderness_signs',dc=12,fixed=[4]*4,context={'rare_signs':True})
  self.assertEqual(out.check.dc,12);self.assertEqual(out.check.margin,4);self.assertEqual(out.basis['source_policy'],'ptu_margin');self.assertTrue(out.basis['rare_information_eligible'])
  source=json.loads((ROOT/'data/context-check-policy.json').read_text(encoding='utf-8'))['interpretations']['rare_survival']
  self.assertEqual(source['default'],'ptu_margin');self.assertIn('ptk_literal',source);self.assertEqual(len(source['basis']),3)
  before=self.e.rng.getstate();pending=self.context('rare_wilderness_signs',context={'rare_signs':True})
  self.assertIsNone(pending.check);self.assertEqual(self.e.rng.getstate(),before)
 def test_rare_signs_original_margin_four_is_inclusive_and_not_a_dc_four(self):
  for faces,eligible in [([3,3,3,3],False),([3,4,4,4],False),([4,4,4,4],True)]:
   out=self.context('rare_wilderness_signs',dc=12,fixed=faces,source_policy='ptu_margin',context={'rare_signs':True})
   self.assertTrue(out.check.passed);self.assertEqual(out.basis['rare_information_eligible'],eligible);self.assertEqual(out.check.dc,12)
 def test_rare_signs_literal_policy_is_separate_dc_four_without_auto_information(self):
  out=self.context('rare_wilderness_signs',fixed=[1]*4,source_policy='ptk_literal',context={'rare_signs':True})
  self.assertEqual((out.check.total,out.check.dc),(4,4));self.assertTrue(out.check.passed);self.assertTrue(out.basis['rare_information_eligible']);self.assertIsInstance(out,C.PendingDecision)
  with self.assertRaises(ValueError):self.context('rare_wilderness_signs',dc=12,source_policy='ptk_literal',context={'rare_signs':True})
 def test_tracking_environment_modifier_applies_to_explicit_real_side(self):
  out=self.opposed('tracking',context={'following_tracks':True},environment_modifiers=[{'side':'defender','amount':-2,'reason':'visible tracks in desert'}],defender_options={'fixed':[4]*4})
  self.assertEqual((out.check.total,out.check.dc),(16,14));self.assertTrue(out.check.passed)
  out=self.opposed('tracking',context={'following_tracks':True},environment_modifiers=[{'side':'actor','amount':-3,'reason':'dark cave obscures signs'}],defender_options={'fixed':[4]*4})
  self.assertEqual((out.check.total,out.check.dc),(13,16));self.assertFalse(out.check.passed)
 def test_tracking_never_infers_a_fixed_desert_or_darkness_modifier(self):
  out=self.opposed('tracking',context={'following_tracks':True,'environment':'desert'},defender_options={'fixed':[4]*4})
  self.assertEqual((out.check.total,out.check.dc),(16,16));self.assertEqual(out.basis['environment_modifiers'],[])
  before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.opposed('tracking',context={'following_tracks':True},environment_modifiers=[{'side':'actor','amount':-2,'reason':''}])
  self.assertEqual(before,self.e.rng.getstate())
 def test_survival_is_body_for_category_and_education_for_real_instruction(self):
  self.a.spec.update(edges=['단정적인 경향'],edge_choices={'단정적인 경향':'physical'})
  self.b.spec.update(edges=['설명']);self.b.spec['skills']['일반 지식']='초보'
  out=self.context('wilderness_survey',dc=21,fixed=[4]*4,helper=self.b,helper_skill='생존',context={'wilderness_task':True})
  self.assertEqual(out.check.total,21);self.assertTrue(out.check.passed)
 def test_ordinary_education_and_technology_do_not_invent_an_opponent(self):
  for case,skill in [('general_knowledge','일반 지식'),('occult_knowledge','오컬트학'),('technology_task','기술학')]:
   out=self.context(case,dc=16,fixed=[4]*4);self.assertEqual(out.basis['skill'],skill);self.assertTrue(out.check.passed)
   with self.assertRaises(ValueError):self.context(case,dc=16,target=self.b)
 def test_competing_occult_ritual_uses_both_actual_occult_skills(self):
  self.b.spec['skills']['오컬트학']='초보'
  out=self.opposed('ritual_control',context={'competing_for_artifact_or_ritual':True},defender_options={'fixed':[5]*3})
  self.assertEqual((out.check.total,out.check.dc),(16,15));self.assertEqual(out.basis['defender_skill'],'오컬트학')
 def test_technical_security_requires_actual_relevant_opponent_selection(self):
  out=self.opposed('technical_security',context={'opposed_technical_security':True});self.assertIsNone(out.check)
  out=self.opposed('technical_security',defender_skill='기술학',context={'opposed_technical_security':True});self.assertEqual(out.basis['skill'],'기술학');self.assertTrue(out.check.passed)
 def test_wits_lies_and_disguises_keep_distinct_actual_opposed_skills(self):
  for case,skill,fact in [('battle_of_wits','교활','competing_wits'),('detect_lie','직감','attempted_lie'),('see_through_disguise','통찰','actual_disguise')]:
   out=self.opposed(case,context={fact:True});self.assertEqual((out.basis['skill'],out.basis['defender_skill']),('교활',skill));self.assertTrue(out.check.passed)
 def test_ambush_reaction_requires_selected_perception_or_acrobatics(self):
  out=self.context('react_to_ambush',dc=16,context={'sudden_ambush':True});self.assertIsNone(out.check)
  for skill in ['통찰','곡예']:
   out=self.context('react_to_ambush',skill=skill,dc=16,fixed=[4]*4,context={'sudden_ambush':True});self.assertTrue(out.check.passed);self.assertIsInstance(out,C.PendingDecision)
  with self.assertRaises(ValueError):self.context('react_to_ambush',skill='직감',dc=16,context={'sudden_ambush':True})
 def test_charm_is_ordinary_unless_third_party_evaluates_both_arguments(self):
  out=self.context('charm_npc',dc=16,fixed=[4]*4);self.assertTrue(out.check.passed)
  out=self.opposed('third_party_persuasion');self.assertIsNone(out.check)
  out=self.opposed('third_party_persuasion',context={'third_party_evaluates_both':True});self.assertEqual(out.basis['defender_skill'],'매력')
 def test_attracting_crowd_and_crisis_leadership_use_distinct_skills(self):
  for case,skill,fact in [('attract_crowd','매력','speech_attracts_audience'),('crisis_leadership','명령','community_crisis_or_authority')]:
   out=self.context(case,dc=16,fixed=[4]*4,context={fact:True});self.assertEqual(out.basis['skill'],skill);self.assertTrue(out.check.passed)
 def test_command_resists_intimidation_and_contextual_mental_control(self):
  out=self.opposed('resist_group_panic',context={'protect_group_from_panic':True});self.assertEqual((out.basis['skill'],out.basis['defender_skill']),('명령','협박'))
  for skill in ['집중','협박']:
   out=self.opposed('rescue_mental_control',defender_skill=skill,context={'ally_under_mental_control':True});self.assertEqual(out.basis['defender_skill'],skill);self.assertIsInstance(out,C.PendingDecision)
 def test_source_variant_and_invalid_environment_do_not_roll_or_mutate(self):
  before=self.e.rng.getstate();old=self.r._selected_rule
  self.r._selected_rule=lambda uid, *args, **kwargs: uid + '-other' if uid == 'ch03-skills-edges-feats/스킬/일반-지식' else old(uid, *args, **kwargs)
  try:
   with self.assertRaises(ValueError):self.context('general_knowledge',dc=16)
  finally:self.r._selected_rule=old
  self.assertEqual(before,self.e.rng.getstate())
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/gm_state.py','engine/heavy_injury_adapter.py','output/source-audit/2026-10-10/ptu-core-1.05.pdf','engine/pokemon_activities.py','engine/jump_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/cultivation-policy.json','tools/test_category3_contexts.py','engine/context_actions.py','data/context-check-policy.json','engine/engine.py','engine/common_checks.py','engine/common_action_checks.py','engine/skill_modifiers.py','engine/ap_roll_bonus.py','engine/resolution_transaction.py','engine/ruleset.py','data/skill-check-policy.json','data/core-rules.json','data/rulesets.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-008','C3-EX-009','C3-EX-010','C3-EX-011','C3-EX-012','C3-EX-013'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-context-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
