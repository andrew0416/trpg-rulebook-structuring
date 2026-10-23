"""Native Manipulate and Expert Maneuver edges, fixed DOMAIN021/EX023."""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import combat_maneuvers as M
import combat_timing as TIMING
import action_points as AP
import temporary_hp as TEMP
import turn as TURN
import skill_feature_actions as SF
import items as ITEMS
class FixedRng:
 def __init__(self,values):self.values=list(values)
 def randint(self,a,b):
  n=self.values.pop(0);assert a<=n<=b;return n
class ManipulateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT))
 def actor(self,name,kind='trainer'):
  return Combatant(self.r,{'id':name,'name':name,'kind':kind,'size':'medium','level':30,'stats':{'hp':60,'atk':21,'def':10,'spa':21,'spd':10,'spe':5},'skills':{x:'숙련' for x in ('교활','매력','집중','협박','은신','육상','곡예')},'moves':['move/칼춤','move/화염방사','move/째려보기'],'movement':{'land':6}})
 def setUp(self):
  self.e=Engine(self.r,seed=341);self.a=self.actor('A');self.t=self.actor('T')
  self.a.side='party';self.t.side='wild';self.a.pos=(1,1);self.t.pos=(5,1)
  self.e.grid=Grid(12,5);self.e.everyone=[self.a,self.t];self.e.gm.everyone=[self.a,self.t]
 def begin(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def options(self,**changes):
  out={'defender_skill':'집중','fixed_accuracy':15,'challenger_options':{'fixed':[4]*4},'defender_options':{'fixed':[3]*4}}
  out.update(changes);return out
 def perform(self,kind='bon_mot',**changes):return self.e.manipulate(self.a,self.t,kind,**self.options(**changes))
 def finish_round(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.e.start_round(self.e.everyone)
 def test_original_scopes_immutable(self):
  ledger=json.loads((ROOT/'data/verification/category3-register.json').read_text('utf-8'))
  for entry in ledger['entries']:
   if entry['id'] not in ('DOMAIN-021','C3-EX-023'):continue
   for a in entry['source_snapshot'].get('anchors',entry['source_snapshot'].get('source_anchors',[])):
    lines=(ROOT/a['file']).read_text('utf-8-sig').splitlines();start=a.get('start',a.get('start_line'));end=a.get('end',a.get('end_line'))
    self.assertEqual('\n'.join(lines[start-1:end]),a['excerpt'])
 def test_bon_mot_actual_standard_opposed_rage_and_ap_forbidden(self):
  self.begin();self.assertTrue(self.perform());self.assertEqual(self.a.budget['standard'],0)
  self.assertIn('난동',self.t.conditions);self.assertEqual(AP.available(self.t),0)
  with self.assertRaises(ValueError):AP.spend(self.t,1)
  with self.assertRaises(ValueError):self.e.boost_roll(self.t,self.t,roll_id='cannotpay',kind='skill')
  self.assertNotIn('ap_spent',self.t.spec);self.assertNotIn('cannotpay',self.e._ap_rolls)
 def test_bon_mot_save_not_rolled_and_next_same_count_restores_ap(self):
  self.begin();self.perform();self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
  self.e.rng=FixedRng([]);self.e.end_of_turn(self.t);self.assertIn('난동',self.t.conditions)
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(21);self.assertEqual(AP.available(self.t),0)
  self.e.at_initiative_count(20);self.assertNotIn('난동',self.t.conditions);self.assertEqual(AP.available(self.t),11)
 def test_bon_mot_forces_native_damage_attack_without_paying_for_rejected_status_move(self):
  self.t.pos=(2,1)  # Actual melee target for the forced Struggle below.
  self.begin();self.perform();self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
  self.assertFalse(TURN.spend(self.e,self.t,'standard','nonattack'))
  self.assertEqual(self.e.use_move(self.t,self.t,'move/칼춤'),0);self.assertEqual(self.t.budget['standard'],1)
  self.e.rng=FixedRng([15]);self.e.use_move(self.t,self.a,'struggle',set_damage=True)
  self.assertEqual(self.t.budget['standard'],0);self.assertLess(self.a.hp,self.a.max_hp)
 def test_bon_mot_does_not_delete_independent_rage_at_expiry(self):
  self.e.apply_status(self.t,'난동');self.begin();self.perform();self.finish_round();self.e.at_initiative_count(20)
  self.assertIn('난동',self.t.conditions);self.assertEqual(AP.available(self.t),11)
 def test_flirt_infatuated_with_actor_and_no_save_roll(self):
  self.begin();self.assertTrue(self.perform('flirt'));record=TIMING.records(self.t)[0]
  self.assertIs(record['infatuation_source'],self.a);self.assertIn('헤롱헤롱',self.t.conditions)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10);self.e.rng=FixedRng([]);self.e.end_of_turn(self.t)
  self.assertIn('헤롱헤롱',self.t.conditions)
 def test_flirt_native_damage_halves_own_attack_against_source_and_minus_five_others(self):
  other=self.actor('other');other.pos=(7,1);self.e.everyone.append(other)
  move=self.r.move('struggle');baseline=self.e.roll_damage(self.t,self.a,move,set_damage=True)
  self.begin();self.perform('flirt')
  self.assertEqual(self.e.roll_damage(self.t,self.a,move,set_damage=True),baseline-11)
  self.assertEqual(self.e.roll_damage(self.t,other,move,set_damage=True),baseline-5)
 def test_flirt_area_damage_uses_included_source_for_all_targets(self):
  other=self.actor('other');move=dict(self.r.move('struggle'),_actual_targets=(self.a,other))
  baseline=self.e.roll_damage(self.t,other,move,set_damage=True);self.begin();self.perform('flirt')
  self.assertEqual(self.e.roll_damage(self.t,other,move,set_damage=True),baseline-11)
 def test_flirt_immunity_has_no_effect_and_expert_does_not_consume(self):
  self.a.spec['edges']=['전문적인 조종자'];self.t.status_immune={'헤롱헤롱'};self.begin()
  self.assertFalse(self.perform('flirt'));self.assertFalse(TIMING.records(self.t));self.assertFalse(self.a.custom_conditions.get('manipulate_uses'))
 def test_terrorize_clears_real_temporary_hp_and_restricts_native_frequency(self):
  TEMP.grant(self.e,self.t,20);self.begin();self.assertTrue(self.perform('terrorize'))
  self.assertEqual(self.t.temp_hp,0);self.assertNotIn(TEMP.STATE,self.t.custom_conditions)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
  before=(self.t.hp,self.e.rng.getstate(),dict(self.t.move_uses))
  self.assertEqual(self.e.use_move(self.t,self.a,'move/화염방사'),0)
  self.assertEqual(before,(self.t.hp,self.e.rng.getstate(),dict(self.t.move_uses)));self.assertEqual(self.t.budget['standard'],1)
  self.e.rng=FixedRng([15]);self.e.use_move(self.t,self.a,'move/째려보기');self.assertEqual(self.t.budget['standard'],0)
 def test_terrorize_does_not_invent_prohibition_on_new_temporary_hp(self):
  self.begin();self.perform('terrorize');TEMP.grant(self.e,self.t,9,round_offset_seconds=0);self.assertEqual(self.t.temp_hp,9)
 def test_manipulation_tie_is_defender_win_and_base_miss_consumes_scene_use(self):
  self.begin();self.assertFalse(self.perform(challenger_options={'fixed':[3]*4}))
  self.assertEqual(self.a.custom_conditions['manipulate_uses'],[('bon_mot',self.t)])
  self.finish_round();self.e.start_of_turn(self.a,initiative_count=20)
  with self.assertRaisesRegex(ValueError,'already been used'):self.perform()
  self.setUp();self.begin();self.assertFalse(self.perform(fixed_accuracy=1));self.assertEqual(self.a.custom_conditions['manipulate_uses'],[('bon_mot',self.t)])
 def test_expert_manipulator_bonus_can_change_outcome_and_miss_does_not_consume(self):
  self.a.spec['edges']=['전문적인 조종자'];ITEMS.register_feats(self.e,self.a);self.begin()
  self.assertTrue(self.perform(challenger_options={'fixed':[3]*4}));self.assertEqual(self.a.custom_conditions['manipulate_uses'],[('bon_mot',self.t)])
  self.setUp();self.a.spec['edges']=['Expert Manipulator'];self.begin();self.assertFalse(self.perform(fixed_accuracy=1))
  self.assertFalse(self.a.custom_conditions.get('manipulate_uses'))
 def test_expert_bonus_applies_to_defender_and_is_not_a_general_skill_bonus(self):
  self.t.spec['edges']=['전문적인 조종자'];self.begin()
  self.assertFalse(self.perform(challenger_options={'fixed':[3,3,3,4]},defender_options={'fixed':[3]*4}))
  self.assertEqual(self.e.skill_roll(self.t,'집중',fixed=[3]*4).total,12)
 def test_each_kind_target_scene_is_independent_and_scene_end_restores(self):
  self.begin();self.perform();self.finish_round();self.e.start_of_turn(self.a,initiative_count=20)
  self.assertTrue(self.perform('terrorize'));self.finish_round();self.e.end_round();self.e.end_scene()
  self.assertFalse(self.a.custom_conditions.get('manipulate_uses'))
 def test_invalid_actor_range_defender_skill_and_prerequisite_reject_before_cost(self):
  self.begin();before=(dict(self.a.budget),self.e.rng.getstate())
  with self.assertRaises(ValueError):self.perform(defender_skill='육상')
  self.t.pos=(8,1)
  with self.assertRaises(ValueError):self.perform()
  self.t.pos=(5,1);self.a.kind='pokemon'
  with self.assertRaises(ValueError):self.perform()
  self.a.kind='trainer';self.a.spec['edges']=['전문적인 조종자'];self.a.spec['skills']['교활']='초보'
  with self.assertRaises(ValueError):self.perform()
  self.assertEqual(before,(dict(self.a.budget),self.e.rng.getstate()))
 def test_accuracy_two_plus_speed_evasion_boundary(self):
  self.begin();self.assertFalse(self.perform(fixed_accuracy=2));self.setUp();self.begin();self.assertTrue(self.perform(fixed_accuracy=3))
 def test_dirty_trick_expert_bonus_and_success_only_scene_usage(self):
  self.t.pos=(2,1);self.a.spec['edges']=['전문 트릭스터'];self.begin()
  self.assertTrue(self.e.dirty_trick(self.a,self.t,'blind',fixed_accuracy=15,challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4}))
  self.assertIn('실명',self.t.conditions);self.assertEqual(self.a.custom_conditions['dirty_trick_uses'],[('blind',self.t)])
  self.setUp();self.t.pos=(2,1);self.a.spec['edges']=['전문 트릭스터'];self.begin()
  self.assertFalse(self.e.dirty_trick(self.a,self.t,'blind',fixed_accuracy=1,challenger_options={'fixed':[3]*4},defender_options={'fixed':[3]*4}))
  self.assertFalse(self.a.custom_conditions.get('dirty_trick_uses'))
 def test_dirty_trick_immune_no_success_charge_and_defender_bonus(self):
  self.t.pos=(2,1);self.a.spec['edges']=['전문 트릭스터'];self.t.status_immune={'실명'};self.begin()
  self.assertFalse(self.e.dirty_trick(self.a,self.t,'blind',fixed_accuracy=15,challenger_options={'fixed':[4]*4},defender_options={'fixed':[3]*4}))
  self.assertFalse(self.a.custom_conditions.get('dirty_trick_uses'))
  self.setUp();self.t.pos=(2,1);self.t.spec['edges']=['전문 트릭스터'];self.begin()
  self.assertFalse(self.e.dirty_trick(self.a,self.t,'blind',fixed_accuracy=15,challenger_options={'fixed':[3,3,3,4]},defender_options={'fixed':[3]*4}))
 def test_expert_requires_enemy_identity_and_does_not_charge_friendly_success(self):
  self.a.spec['edges']=['전문적인 조종자'];self.t.side=None;self.begin()
  with self.assertRaisesRegex(ValueError,'side'):self.perform()
  self.t.side='party';self.assertTrue(self.perform());self.assertFalse(self.a.custom_conditions.get('manipulate_uses'))
 def test_observed_reroll_error_resumes_without_repaying_standard_or_accuracy(self):
  self.a.spec['feats']=[SF.MONKEY];self.begin();seen=[]
  def bad(roll):seen.append(roll);return 'bad'
  options=self.options(challenger_options={'fixed':[2]*4,'roll_id':'maneuver-a','feature':SF.MONKEY,'feature_options':{'decision':bad}},defender_options={'fixed':[3]*4,'roll_id':'maneuver-b'})
  with self.assertRaisesRegex(ValueError,'boolean'):self.e.manipulate(self.a,self.t,'bon_mot',**options)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(SF.event(self.e,self.a,'maneuver-a').first.total,8)
  self.e.rng=FixedRng([]);options['challenger_options']['feature_options']={'decision':lambda roll:True,'reroll_faces':[4]*4}
  self.assertTrue(self.e.manipulate(self.a,self.t,'bon_mot',**options));self.assertEqual(self.a._action_history.count('standard'),1)
  self.assertEqual(len(seen),1);self.assertFalse(self.e.rng.values)
  with self.assertRaises(ValueError):self.e.manipulate(self.a,self.t,'bon_mot',**options)
 def test_external_status_cure_removes_only_its_linked_restrictions(self):
  self.begin();self.perform();self.e.cure_status(self.t,'난동')
  self.assertEqual(AP.available(self.t),0);self.assertFalse(M.force_attack(self.t));self.assertIsNone(M.save_disposition(self.t,'난동'))
  self.e.apply_status(self.t,'난동');self.assertIsNone(M.save_disposition(self.t,'난동'))
  self.setUp();self.begin();self.perform('flirt');self.e.cure_status(self.t,'헤롱헤롱');self.e.apply_status(self.t,'헤롱헤롱',applied_by=self.a)
  self.assertIsNone(M.save_disposition(self.t,'헤롱헤롱'));self.assertNotIn('infatuation_source',TIMING.records(self.t)[0])
 def test_flirt_actual_area_producer_shares_source_membership_across_targets(self):
  other=self.actor('other');other.side='party';other.pos=(4,2);self.a.pos=(5,1);self.t.pos=(4,1)
  self.e.everyone.append(other);self.t.moves.append('move/꽃보라');self.begin();self.perform('flirt')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
  self.e.rng=FixedRng([15]+[4]*30);self.e.use_move_on(self.t,self.a,'move/꽃보라',self.e.everyone)
  self.assertLess(self.a.hp,self.a.max_hp);self.assertEqual(self.a.max_hp-self.a.hp,other.max_hp-other.hp)
 def test_edge_variant_and_duplicate_acquisition_rejected(self):
  self.a.spec['edges']=['전문적인 조종자','Expert Manipulator'];self.begin()
  with self.assertRaises(ValueError):self.perform()
  self.assertEqual(self.a.budget['standard'],1)
  self.a.spec['edges']=['전문적인 조종자'];original=self.r._selected_rule
  self.r._selected_rule=lambda uid,*a,**kw:uid+'-variant' if uid=='edge/전문적인-조종자' else original(uid,*a,**kw)
  try:
   with self.assertRaisesRegex(ValueError,'variant'):self.perform()
  finally:self.r._selected_rule=original
  self.assertEqual(self.a.budget['standard'],1)
 def test_snapshot_preserves_sources_usage_and_actual_participant_references(self):
  self.begin();self.perform('flirt');self.e.gm.snapshot('flirt');self.finish_round();self.e.at_initiative_count(20)
  self.assertNotIn('헤롱헤롱',self.t.conditions);self.e.gm.restore('flirt')
  self.assertIs(TIMING.records(self.t)[0]['infatuation_source'],self.a)
  self.assertIs(self.a.custom_conditions['manipulate_uses'][0][1],self.t)
 def test_native_dirty_and_manipulate_json_keep_actual_target_source_and_spent_attempt(self):
  from state_codec import dump_engine,load_engine
  for family,kind,status in (('dirty','low_blow','취약'),('manipulate','flirt','헤롱헤롱')):
   with self.subTest(family=family):
    self.setUp();self.t.pos=(2,1);self.begin()
    options=self.options();options.pop('defender_skill')
    if family=='dirty':result=self.e.dirty_trick(self.a,self.t,kind,**options)
    else:result=self.perform(kind)
    self.assertTrue(result)
    saved=dump_engine(self.e);loaded=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)))
    actors={c.entity_id:c for c in loaded.everyone};a=actors[self.a.entity_id];t=actors[self.t.entity_id]
    key='dirty_trick_uses' if family=='dirty' else 'manipulate_uses'
    self.assertIs(a.custom_conditions[key][0][1],t);self.assertIsNot(a,self.a);self.assertIsNot(t,self.t)
    self.assertIn(status,t.conditions);self.assertEqual(a.budget['standard'],0)
    if family=='manipulate':self.assertIs(TIMING.records(t)[0]['infatuation_source'],a)
    before=dump_engine(loaded)
    with self.assertRaisesRegex(ValueError,'already been used'):
     if family=='dirty':loaded.dirty_trick(a,t,kind,**options)
     else:loaded.manipulate(a,t,kind,**self.options())
    self.assertEqual(before,dump_engine(loaded))
    loaded.end_of_turn(a);loaded.end_round();loaded.start_round(loaded.everyone)
    if family=='dirty':loaded.start_of_turn(a,initiative_count=20);loaded.end_of_turn(a)
    else:loaded.at_initiative_count(20)
    self.assertNotIn(status,t.conditions)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ManipulateTests))
 files=['engine/combat_maneuvers.py','engine/maneuver_edges.py','engine/skill_maneuver_actions.py','engine/engine.py','engine/turn.py','engine/action_lifecycle.py','engine/action_points.py','engine/frequency.py','engine/combat_timing.py','engine/items.py','engine/skill_feature_actions.py','engine/skill_modifiers.py','engine/temporary_hp.py','engine/combat_social_edges.py','engine/effects.py','engine/effects_ext.py','engine/ap_roll_bonus.py','engine/gm_state.py','input/ch03-skills-edges-feats.md','input/ch07-combat.md','tools/test_category3_manipulate.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-021','C3-EX-023'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-manipulate-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
