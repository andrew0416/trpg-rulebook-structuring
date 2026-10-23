"""Skill Monkey in actual Disarm/Dirty Trick: costs and observed rolls survive choice errors."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import turn as TURN
import common_checks as C
import skill_feature_actions as SF
import skill_maneuver_actions as SM
import combat_timing as TIMING

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def actor(self,name,side,pos):
  return Combatant(self.r,dict(id='trainer/'+name,name=name,kind='trainer',size='Medium',side=side,pos=list(pos),level=20,stats=dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'육상':4,'곡예':4,'통찰':4,'은신':4,'전투':4},feats=[SF.MONKEY]))
 def setUp(self):
  self.e=Engine(self.r,7);self.a=self.actor('A','party',(1,1));self.b=self.actor('B','wild',(2,1));self.w=self.actor('W','wild',(1,2))
  self.e.everyone=[self.a,self.b,self.w];self.e.gm.everyone=self.e.everyone;self.e.grid=Grid(8,8)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  TURN.equip_weapon(self.e,self.b,{'name':'검','kind':'소형 근접무기','grade':'조잡'})
 def opts(self,identity,*,bad=False,faces=2,decline=False):
  return {'roll_id':identity,'fixed':[1]*4,'feature':SF.MONKEY,'feature_options':{'decision':(lambda first:'bad') if bad else (lambda first:not decline),'reroll_faces':[faces]*4}}
 def used(self,c):return c.spec.get('frequency_state',{}).get('activations',{}).get(SF.MONKEY,{}).get('used',0)
 def options(self,bad=False):return dict(fixed_accuracy=20,challenger_options=self.opts('a',faces=4),defender_options=self.opts('b',bad=bad))
 def disarm(self,options=None):return self.e.disarm(self.a,self.b,attacker_skill='전투',defender_skill='은신',**(options or self.options()))
 def dirty(self,trick='blind',options=None):
  kw={} if trick=='blind' else {'duration_policy':'combined','policy_reason':'explicit combined source scope'}
  return self.e.dirty_trick(self.a,self.b,trick,**kw,**(options or self.options()))
 def test_disarm_actual_aoo_standard_accuracy_and_earlier_roll_survive_late_choice(self):
  with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as accuracy:
   with self.assertRaises(ValueError):self.disarm(self.options(True))
   calls=accuracy.call_count;rng=self.e.rng.getstate();hp=self.a.hp;first=SF.event(self.e,self.a,'a').first
   self.assertEqual(calls,2);self.assertTrue(self.w.aoo_used);self.assertEqual(self.a.budget['standard'],0)
   self.assertEqual((self.used(self.a),self.used(self.b)),(1,0));self.assertEqual(len(self.b.custom_conditions['equipped_weapons']),1)
   self.assertTrue(self.disarm());self.assertEqual(accuracy.call_count,calls);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.a.hp,hp)
   self.assertIs(SF.event(self.e,self.a,'a').first,first);self.assertEqual((self.used(self.a),self.used(self.b)),(1,1))
   self.assertEqual(len(self.e.ground_items),1);self.assertEqual(self.b.custom_conditions.get('equipped_weapons',{}),{})
   self.assertEqual(self.a._action_history,['standard','free'])
   with self.assertRaises(ValueError):self.disarm()
   with self.assertRaises(ValueError):self.e.skill_roll(self.a,'전투',**self.opts('a'))
 def test_each_dirty_trick_applies_actual_outcome_once_after_resume(self):
  for trick,status in [('blind','실명'),('hinder','둔화'),('low_blow','취약')]:
   self.setUp()
   with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as accuracy:
    with self.assertRaises(ValueError):self.dirty(trick,self.options(True))
    calls=accuracy.call_count;self.assertNotIn(status,self.b.conditions);self.assertEqual(len(self.a.custom_conditions['dirty_trick_uses']),1)
    self.assertTrue(self.dirty(trick));self.assertEqual(accuracy.call_count,calls);self.assertIn(status,self.b.conditions)
    self.assertEqual(len(TIMING.records(self.b)),1);self.assertEqual(len(self.a.custom_conditions['dirty_trick_uses']),1)
    if trick=='hinder':self.assertEqual(TIMING.skill_modifier(self.b),-2)
    if trick=='low_blow':self.assertEqual(self.b.initiative_override,0)
 def test_real_miss_never_draws_opposed_dice_or_feature_cost_and_cannot_retry_hit(self):
  for method in (self.disarm,self.dirty):
   self.setUp();options=self.options();options['fixed_accuracy']=1
   self.assertFalse(method(options=options));self.assertEqual((self.used(self.a),self.used(self.b)),(0,0))
   self.assertIsNone(SF.event(self.e,self.a,'a'));self.assertEqual(self.a.budget['standard'],0)
   with self.assertRaises(ValueError):method(options=self.options())
 def test_defender_feature_final_result_wins_ties_or_reverses_initial_success(self):
  options=self.options();options['challenger_options']['fixed']=[6]*4;options['challenger_options']['feature_options']['decision']=lambda first:False
  options['defender_options']=self.opts('b',faces=6)
  self.assertFalse(self.disarm(options));self.assertEqual((self.used(self.a),self.used(self.b)),(0,1));self.assertFalse(getattr(self.e,'ground_items',[]))
  self.assertEqual(SF.event(self.e,self.b,'b').final.total,26)
 def test_pending_action_rejects_new_ids_changed_accuracy_skill_round_or_ordinary_bypass(self):
  with self.assertRaises(ValueError):self.disarm(self.options(True))
  state=(self.e.rng.getstate(),deepcopy(self.a.budget),self.a.hp,self.used(self.a))
  changes=[dict(self.options(),fixed_accuracy=19),dict(self.options(),challenger_options=self.opts('different')),
           dict(self.options(),challenger_options={'roll_id':'ordinary','fixed':[6]*4},defender_options={'roll_id':'other','fixed':[1]*4})]
  for options in changes:
   with self.assertRaises(ValueError):self.disarm(options)
  with self.assertRaises(ValueError):self.e.disarm(self.a,self.b,attacker_skill='은신',defender_skill='은신',**self.options())
  self.e.round_no+=1
  with self.assertRaises(ValueError):self.disarm()
  self.e.round_no-=1
  self.assertEqual((self.e.rng.getstate(),self.a.budget,self.a.hp,self.used(self.a)),state)
  self.assertTrue(self.disarm())
 def test_all_later_feature_inputs_validate_before_standard_aoo_accuracy_or_first_roll(self):
  options=self.options();options['defender_options']['feature_options']['reroll_faces']=[7]*4
  before=(self.e.rng.getstate(),deepcopy(self.a.budget),self.a.hp)
  with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as accuracy:
   with self.assertRaises(ValueError):self.disarm(options)
   self.assertEqual(accuracy.call_count,0)
  self.assertEqual((self.e.rng.getstate(),self.a.budget,self.a.hp),before);self.assertFalse(self.w.aoo_used);self.assertNotIn(SM.ACTIVE,self.a.custom_conditions)
 def test_snapshot_of_observed_maneuver_restores_same_cost_and_dropped_item_transition(self):
  with self.assertRaises(ValueError):self.disarm(self.options(True))
  self.e.gm.snapshot('pending');hp=self.a.hp
  self.assertTrue(self.disarm());self.e.gm.restore('pending')
  self.assertEqual(self.a.hp,hp);self.assertEqual((self.used(self.a),self.used(self.b)),(1,0));self.assertEqual(len(self.b.custom_conditions['equipped_weapons']),1)
  self.assertTrue(self.disarm());self.assertEqual(len(self.e.ground_items),1)
 def test_defender_only_feature_and_first_callback_failure_preserve_actual_first_faces(self):
  options=self.options(True);options['challenger_options']={'roll_id':'a','fixed':[3]*4}
  with self.assertRaises(ValueError):self.disarm(options)
  self.assertEqual(self.used(self.a),0);first=SF.event(self.e,self.a,'a').first
  options['defender_options']=self.opts('b')
  self.assertTrue(self.disarm(options));self.assertIs(SF.event(self.e,self.a,'a').first,first)
 def test_native_exception_after_aoo_or_accuracy_cannot_restart_fresh_rng(self):
  with patch.object(self.e,'accuracy_check',side_effect=RuntimeError('native interruption')) as accuracy:
   with self.assertRaises(RuntimeError):self.disarm()
  result=self.disarm();self.assertIsInstance(result,C.PendingDecision)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.used(self.a),0)

 def test_weapon_of_choice_modifier_and_conditional_ap_are_applied_once_after_resume(self):
  self.b.spec.update(edges=['선택한 무기'],edge_choices={'선택한 무기':'소형 근접무기'},classes=['닌자'])
  self.b.spec['feats'].append('독극 무기');options=dict(self.options(True),prevent_with_ap=True)
  with self.assertRaises(ValueError):self.disarm(options)
  self.assertEqual(SF.event(self.e,self.b,'b').first.modifier,2);self.assertEqual(self.b.spec.get('ap_spent',0),0)
  options=dict(self.options(),prevent_with_ap=True)
  self.assertFalse(self.disarm(options));self.assertEqual(self.b.spec['ap_spent'],1)
  self.assertEqual(len(self.b.custom_conditions['equipped_weapons']),1);self.assertFalse(getattr(self.e,'ground_items',[]))
 def test_observed_maneuver_cannot_resume_after_turn_or_scene_changes(self):
  with self.assertRaises(ValueError):self.disarm(self.options(True))
  self.e.end_of_turn(self.a)
  with self.assertRaises(ValueError):self.disarm()
 def fall_options(self,bad=False):
  self.a.spec['weight_class']=2;self.a.spec['movement']={'high_jump':1}
  return dict(action_id='fall1',meters=5,intentional=True,reason='GM actual five-metre fall',natural_sky=False,natural_sky_reason='Trainer has no natural Sky',high_jump_boost=True,boost_options=self.opts('boost',faces=4),acrobatics=True,acrobatics_options=self.opts('acro',bad=bad,faces=4),acrobatics_injury_policy='damage_only')
 def test_actual_fall_high_jump_and_acrobatics_resume_same_rolls_then_apply_hp_once(self):
  options=self.fall_options(True);before=self.a.hp
  with self.assertRaises(ValueError):self.e.falling_damage(self.a,**options)
  self.assertEqual(self.a.hp,before);self.assertEqual(self.used(self.a),1);first=SF.event(self.e,self.a,'boost').first
  with self.assertRaises(ValueError):self.e.falling_damage(self.a,**dict(options,action_id='new-fall'))
  with self.assertRaises(ValueError):self.e.falling_damage(self.a,**dict(options,meters=6))
  options=self.fall_options();out=self.e.falling_damage(self.a,**options)
  self.assertEqual((out['high_jump'],out['damage_distance'],out['height_injuries']),(2,2,0))
  self.assertEqual(self.a.hp,before-out['damage']);self.assertEqual(self.used(self.a),2)
  self.assertIs(SF.event(self.e,self.a,'boost').first,first);self.assertNotIn('_fall_skill_inflight',self.a.spec)
  with self.assertRaises(ValueError):self.e.falling_damage(self.a,**options)
 def test_fall_missing_injury_policy_preserves_observed_final_and_accepts_explicit_gm_choice(self):
  self.a.spec['weight_class']=2;self.a.spec['movement']={'high_jump':0}
  options=dict(action_id='policy',meters=4,intentional=True,reason='GM actual fall',natural_sky=False,natural_sky_reason='Trainer no wings',acrobatics=True,acrobatics_options=self.opts('acro',faces=4))
  with self.assertRaisesRegex(ValueError,'injury-distance policy'):self.e.falling_damage(self.a,**options)
  first=SF.event(self.e,self.a,'acro').first;self.assertEqual(self.used(self.a),1)
  out=self.e.falling_damage(self.a,**dict(options,acrobatics_injury_policy='damage_only'))
  self.assertEqual((out['height_injuries'],out['injury_distance']),(2,4));self.assertEqual(self.used(self.a),1)
  self.assertIs(SF.event(self.e,self.a,'acro').first,first)

 def test_featured_maneuver_normalizes_actual_face_generators_once(self):
  options=self.options();options['challenger_options']['fixed']=(1 for _ in range(4));options['defender_options']['fixed']=(1 for _ in range(4))
  self.assertTrue(self.disarm(options));self.assertEqual(SF.event(self.e,self.a,'a').first.faces,(1,)*4)
 def test_fall_late_damage_input_error_keeps_skill_observation_and_snapshot_resume(self):
  options=self.fall_options();options['fixed_damage']=[7]
  before=self.a.hp
  with self.assertRaises(ValueError):self.e.falling_damage(self.a,**options)
  first=SF.event(self.e,self.a,'boost').first;self.assertEqual((self.a.hp,self.used(self.a)),(before,2))
  self.e.gm.snapshot('fall-pending');options['fixed_damage']=[1]
  out=self.e.falling_damage(self.a,**options);self.assertEqual(self.used(self.a),2)
  self.e.gm.restore('fall-pending');again=self.e.falling_damage(self.a,**options)
  self.assertEqual((out['damage'],out['checks']),(again['damage'],again['checks']))
  self.assertEqual(SF.event(self.e,self.a,'boost').first,first);self.assertEqual(self.a.hp,before-out['damage'])

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/downtime.py','engine/items.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json',*sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')),'tools/test_category3_maneuver_features.py','input/ch03-skills-edges-feats.md','input/ch07-combat.md','data/skill-check-policy.json','data/weapon-policy.json']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-045'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
 (ROOT/'output/category3-maneuver-feature-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
