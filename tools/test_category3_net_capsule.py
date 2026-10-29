"""Native Net Cap acquisition, firing, effects, manual lifetime and removal."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from grid import Grid
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
import items as ITEMS
import net_capsule as NET
import combat_timing as TIMING
import movement_actions as MOVEMENT
import wild_equipment as WILD
class NetTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core+errata')
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 act=_fixture_test_category3_pokemon_activities.PokemonActivityTests.act
 state=_fixture_test_category3_pokemon_activities.PokemonActivityTests.state
 def setUp(self):
  _fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self);self.e.grid=Grid(20,20);self.a.pos=(0,0);self.p.pos=(3,0);self.q.pos=(12,0)
  self.p.spec.update(size='Medium',movement={'power':5,'land':6,'sky':6,'levitate':4});self.a.spec['items'].update({'캡슐캐논':1,'네트캡슐':5})
  ITEMS.register_item(self.e,self.a,'캡슐캐논')
  for actor in (self.a,self.q):self.e.gm.set_footprint(actor,[(0,0)],reason='observed one-cell Net Cap fixture body')
 def fire(self,face=20,**kw):return self.act('net_capsule',target=self.p,fixed_accuracy=face,**kw)
 def test_actual_cannon_equipment_uses_both_hands_and_ammunition(self):
  self.assertEqual(self.a._item_reg['캡슐캐논']['slots'],['주요손','반대손'])
  self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.a)
  r=self.fire();self.assertTrue(r['hit']);self.assertEqual(self.a.spec['items']['네트캡슐'],4);self.assertEqual(self.a.budget['standard'],0);self.assertIsNotNone(NET.active(self.p))
 def test_unowned_unequipped_or_single_hand_cannon_cannot_fire(self):
  for mutation in ('unowned','unequipped','one_hand','overlap'):
   self.setUp()
   if mutation=='unowned':self.a.spec['items']['캡슐캐논']=0
   elif mutation=='unequipped':self.a._item_reg.clear()
   elif mutation=='one_hand':self.a._item_reg['캡슐캐논']['slots']=['주요손']
   else:self.a.custom_conditions['equipped_weapons']={'actual_other_weapon':{'slots':['반대손']}}
   before=self.state()
   with self.assertRaises(ValueError):self.fire()
   self.assertEqual(before,self.state());self.assertIsNone(NET.active(self.p))
 def test_real_slot_occupancy_blocks_cannon_registration(self):
  ITEMS.unregister_item(self.e,self.a,'캡슐캐논');self.a.custom_conditions['equipped_weapons']={'actual_other_weapon':{'slots':['반대손']}}
  ITEMS.register_item(self.e,self.a,'캡슐캐논');self.assertFalse(self.a._item_reg)
 def test_technology_rank_and_target_evasion_use_native_accuracy_natural_boundaries(self):
  for face,expected in [(1,False),(6,False),(7,True),(20,True)]:
   self.setUp();r=self.fire(face);self.assertEqual(r['ac'],6);self.assertEqual(r['hit'],expected);self.assertEqual(self.a.spec['items']['네트캡슐'],4)
  self.setUp();self.a.spec['skills']['기술학']='달인';self.a.spec['edges']=['edge/거장'];self.a.spec['edge_choices']={'거장':['기술학']};self.assertEqual(self.fire(3)['ac'],2)
 def test_named_ap_accuracy_is_spent_once_and_wrong_actor_cannot_spend_ammo(self):
  self.q.spec['trainer_id']=self.a.entity_id  # Declared starting ownership of this other registered beneficiary.
  self.e.boost_roll(self.a,self.a,roll_id='net-shot',kind='accuracy');self.assertEqual(self.a.spec['ap_spent'],1)
  r=self.fire(6,accuracy_roll_id='net-shot');self.assertTrue(r['hit']);self.assertEqual(self.e._ap_rolls['net-shot']['state'],'resolved')
  self.e.remove_net(self.p,fixed=10);before=self.state()
  with self.assertRaises(ValueError):self.fire(20,accuracy_roll_id='net-shot')
  self.assertEqual(before,self.state());self.e.boost_roll(self.a,self.q,roll_id='wrong-target',kind='accuracy');before=self.state()
  self.assertIs(self.e._ap_rolls['wrong-target']['beneficiary'],self.q)
  with self.assertRaisesRegex(ValueError,'another actor'):self.fire(20,accuracy_roll_id='wrong-target')
  self.assertEqual(before,self.state())
 def test_excluded_errata_source_cannot_equip_cannon(self):
  original=self.rules
  try:
   self.rules=Rules(str(ROOT),ruleset='core');_fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self);self.a.spec['items']['캡슐캐논']=1
   with self.assertRaises(ValueError):ITEMS.register_item(self.e,self.a,'캡슐캐논')
   self.assertFalse(getattr(self.a,'_item_reg',{}))
  finally:self.rules=original
 def test_miss_consumes_actual_standard_and_capsule_without_state(self):
  self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.a)
  r=self.fire(1);self.assertEqual(r['status'],'missed');self.assertIsNone(NET.active(self.p));self.assertEqual(self.a.budget['standard'],0);self.assertFalse(self.p.conditions)
 def test_outside_combat_shot_and_removal_ignore_stale_turn_budgets(self):
  self.assertFalse(self.e.encounter_active)
  self.a.budget={'standard':0,'shift':0,'swift':0};self.p.budget={'standard':0,'shift':0,'swift':0}
  result=self.fire();self.assertTrue(result['hit']);self.assertEqual(self.a.spec['items']['네트캡슐'],4)
  self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':0})
  self.assertEqual(self.a._action_history.count('standard'),1)
  self.assertTrue(self.e.remove_net(self.p,fixed=10)['removed'])
  self.assertEqual(self.p.budget,{'standard':0,'shift':0,'swift':0})
  self.assertEqual(self.p._action_history.count('standard'),1);self.assertIsNone(NET.active(self.p))
 def test_invalid_face_size_range_los_and_ammo_do_not_spend(self):
  for mutation in ('face','size','range','los','ammo'):
   self.setUp();options={}
   if mutation=='face':options['fixed_accuracy']=21
   elif mutation=='size':self.p.spec.pop('size')
   elif mutation=='range':self.p.pos=(7,0)
   elif mutation=='los':self.e.grid.blocking.add((1,0))
   else:self.a.spec['items']['네트캡슐']=0
   before=self.state()
   with self.assertRaises(ValueError):self.act('net_capsule',target=self.p,**options)
   self.assertEqual(before,self.state())
 def test_native_phasing_target_refusal_preserves_shot_action_ammo_ap_rng_and_history(self):
  import state_grants as G
  self.e.gm.set_footprint(self.p,[(0,0)],reason='actual unchanged Phasing body')
  G.grant(self.p,'capabilities','Phasing','fixture:net-phasing','fixture')
  self.e.change_body_mode(self.p,'phasing',reason='actual target enters native Phasing')
  self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.a)
  self.e.apply_status(self.a,'혼란')
  self.e.boost_roll(self.a,self.a,roll_id='rejected-net',kind='accuracy')
  def observed():
   return deepcopy((self.state(),self.a._action_history,self.a.hp,self.a.conditions,self.p.hp,self.p.conditions,self.p.custom_conditions,self.e._ap_rolls,self.e.log_lines),{id(c):c for c in self.e.gm.everyone})
  before=observed()
  for fixed in (None,20):
   with self.assertRaisesRegex(ValueError,'Phasing'):
    self.act('net_capsule',target=self.p,fixed_accuracy=fixed,accuracy_roll_id='rejected-net')
   self.assertEqual(observed(),before)
   self.assertFalse(getattr(self.e,'_native_action_resolutions',{}))
   self.assertFalse(getattr(self.e,'_native_action_stack',()))
   self.assertIsNone(NET.active(self.p))
 def test_paid_hit_and_miss_keep_one_native_action_and_ap_roll(self):
  for face in (1,20):
   self.setUp();self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.a)
   self.e.boost_roll(self.a,self.a,roll_id='paid-net',kind='accuracy')
   result=self.fire(face,accuracy_roll_id='paid-net')
   self.assertEqual((result['hit'],result['status']),(face==20,'attached' if face==20 else 'missed'))
   self.assertEqual((self.a.budget['standard'],self.a._action_history.count('standard')),(0,1))
   self.assertEqual((self.a.spec['items']['네트캡슐'],self.a.spec['net_capsule_serial'],len(self.a.spec['net_capsule_attempts'])),(4,1,1))
   self.assertEqual((self.a.spec['ap_spent'],self.e._ap_rolls['paid-net']['state']),(1,'resolved'))

 def test_native_grounding_commits_actual_entry_effect_with_one_shot(self):
  self.p.spec['_movement_altitude']=3;self.p.airborne=True
  self.e.gm.place_hazard(self.p.pos,'observed landing trap',effects=[{'type':'stage_change','stat':'spe','delta':-1}],reason='actual ground trap at target landing')
  before_hp=self.p.hp
  result=self.fire(gm_distance=5)
  self.assertTrue(result['hit']);self.assertEqual(self.a.spec['items']['네트캡슐'],4)
  self.assertEqual((self.p.spec['_movement_altitude'],self.p.airborne,self.p.hp,self.p.stages['spe']),(0,False,before_hp,-1))
  self.assertIsNotNone(NET.active(self.p))
  self.assertNotIn(self.p.pos,self.e.hazards)

 def test_size_boundaries_preserve_literal_large_or_smaller_minus_three(self):
  for size,penalty,statuses in [('Small',-3,True),('Medium',-3,True),('Large',-3,False),('Huge',0,False)]:
   self.setUp();self.p.spec['size']=size;self.fire();self.assertEqual(NET.active(self.p)['size_policy'],'ptk-literal-large-or-smaller');self.assertEqual(TIMING.accuracy_modifier(self.p),penalty);self.assertEqual({'둔화','취약'}<=self.p.conditions,statuses)
   move={'id':'ball','name':'plain attack','class':'변화','type':'노말','ac':6}
   hit,_,_=self.e.accuracy_check(self.p,self.q,move,fixed_roll=9);self.assertEqual(hit,penalty==0)
 def test_standard_save_power_dc15_equality_and_failed_cost_retained(self):
  self.fire();self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
  r=self.e.remove_net(self.p,fixed=9);self.assertFalse(r['removed']);self.assertEqual(r['check']['total'],14);self.assertEqual(self.p.budget['standard'],0);self.assertEqual(len(NET.active(self.p)['removal_checks']),1)
  self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
  r=self.e.remove_net(self.p,fixed=10);self.assertTrue(r['removed']);self.assertEqual(r['check']['dc'],15);self.assertIsNone(NET.active(self.p));self.assertFalse(self.p.conditions)
 def test_save_modifier_adds_to_power_and_no_natural_twenty_special_rule(self):
  self.fire();self.p.save_mod=2;r=self.e.remove_net(self.p,fixed=8);self.assertEqual((r['check']['total'],r['removed']),(15,True))
  self.setUp();self.fire();self.p.save_mod=-20;r=self.e.remove_net(self.p,fixed=20);self.assertFalse(r['removed']);self.assertIsNotNone(NET.active(self.p))
 def test_only_actual_target_can_remove_not_helper(self):
  self.fire();before=self.state()
  with self.assertRaises(ValueError):self.e.remove_net(self.a,fixed=20)
  self.assertEqual(before,self.state())
 def test_unavailable_standard_sleep_faint_and_invalid_save_preserve_source_and_rng(self):
  self.fire();self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
  self.assertFalse(self.e.remove_net(self.p,fixed=9)['removed'])  # The real failed removal spends this turn's Standard.
  rng=self.e.rng.getstate();self.assertIs(self.e.remove_net(self.p),False);self.assertEqual(self.e.rng.getstate(),rng)
  self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
  rng=self.e.rng.getstate()
  for status in ('잠듦','얼음'):
   self.p.conditions.add(status);self.assertIs(self.e.remove_net(self.p),False);self.p.conditions.remove(status);self.assertEqual(self.p.budget['standard'],1)
  self.p.hp=0;self.assertIs(self.e.remove_net(self.p),False);self.assertIsNotNone(NET.active(self.p));self.p.hp=10
  with self.assertRaises(ValueError):self.e.remove_net(self.p,fixed=21)
  self.assertEqual(self.e.rng.getstate(),rng)
 def test_actual_encounter_native_turn_fire_then_self_removal(self):
  self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.a);self.fire();self.e.end_of_turn(self.a);self.e.start_of_turn(self.p)
  result=self.e.remove_net(self.p,fixed=10);self.assertTrue(result['removed']);self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p._action_history.count('standard'),1)
 def test_extended_automatic_removal_requires_explicit_actual_time_and_survives_scene(self):
  self.fire();self.e.end_scene([self.a,self.p,self.q]);self.assertIsNotNone(NET.active(self.p));self.assertIn('둔화',self.p.conditions);rng=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.remove_net(self.p,method='extended')
  r=self.e.remove_net(self.p,method='extended',minutes=3,reason='GM actual untangling duration');self.assertTrue(r['removed']);self.assertEqual(self.e.elapsed_seconds,180);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.p._action_history[-1],'extended')
 def test_extended_removal_cannot_roll_or_bypass_sleep_or_encounter(self):
  self.fire()
  with self.assertRaises(ValueError):self.e.remove_net(self.p,method='extended',minutes=1,reason='invalid',fixed=20)
  self.p.conditions.add('잠듦');self.assertIs(self.e.remove_net(self.p,method='extended',minutes=1,reason='asleep'),False);self.p.conditions.remove('잠듦');self.assertEqual(self.e.elapsed_seconds,0)
  self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.p)
  with self.assertRaises(ValueError):self.e.remove_net(self.p,method='extended',minutes=1,reason='combat')
 def test_preexisting_and_reapplied_external_status_survive_physical_removal(self):
  self.e.apply_status(self.p,'둔화');self.fire();self.e.apply_status(self.p,'취약');self.e.remove_net(self.p,fixed=10);self.assertEqual(self.p.conditions,{'둔화','취약'})
 def test_generic_condition_recovery_and_recall_preserve_attached_physical_net(self):
  import common_checks as C
  for actor in (self.a,self.q):
   self.e.gm.set_footprint(actor,[(0,0)],reason='GM observed one-cell body for actual Net Cap recovery case')
  self.fire();self.e.end_scene([self.a,self.p,self.q]);before=self.state();when=self.e.elapsed_seconds
  result=self.e.recover_condition(self.p,'둔화',duration_minutes=3,reason='generic recovery cannot detach this net')
  self.assertIsInstance(result,C.PendingDecision);self.assertEqual(self.state(),before);self.assertEqual(self.e.elapsed_seconds,when)
  self.e.gm.recall(self.p,reason='actual recall with attached net');self.assertIn('둔화',self.p.conditions);self.assertIsNotNone(NET.active(self.p))
  self.e.gm.send_out(self.p);result=self.e.remove_net(self.p,method='extended',minutes=3,reason='actual source-specific physical removal')
  self.assertTrue(result['removed']);self.assertNotIn('둔화',self.p.conditions)
 def test_ordinary_cure_cannot_remove_physical_source_but_cures_external_ownership(self):
  self.e.apply_status(self.p,'둔화');self.fire();self.assertIs(self.e.cure_status(self.p,'둔화'),False);self.assertIn('둔화',self.p.conditions);self.e.remove_net(self.p,fixed=10);self.assertFalse(self.p.conditions)
 def test_overlapping_timed_source_transfers_ownership_both_orders(self):
  for net_first in (False,True):
   self.setUp()
   if net_first:self.fire()
   other=TIMING.install(self.e,self.p,{'source':'test/timed_effect','statuses':['둔화']})
   if not net_first:self.fire()
   self.e.remove_net(self.p,fixed=10);self.assertIn('둔화',self.p.conditions);TIMING.expire(self.e,self.p,other);self.assertFalse(self.p.conditions)
 def test_forced_grounding_changes_actual_altitude_without_hp_loss_then_blocks_both_modes(self):
  self.p.spec['_movement_altitude']=3;self.p.airborne=True;hp=self.p.hp;position=self.p.pos;r=self.fire(gm_distance=5)
  self.assertTrue(r['hit']);self.assertEqual(self.p.hp,hp);self.assertEqual(self.p.pos,position);self.assertEqual(self.p.spec['_movement_altitude'],0);self.assertFalse(self.p.airborne)
  for mode in ('sky','levitate'):
   self.assertEqual(MOVEMENT.capabilities(self.e,self.p)[mode],0)
   with self.assertRaises(ValueError):self.e.aerial_move(self.p,self.p.pos,mode=mode,altitude=1,reason_text='attempt netted flight')
  self.e.remove_net(self.p,fixed=10);self.assertEqual(MOVEMENT.capabilities(self.e,self.p)['sky'],6);self.e.aerial_move(self.p,self.p.pos,mode='sky',altitude=1,reason_text='actual flight after net removed');self.assertEqual(self.p.spec['_movement_altitude'],1)
 def test_airborne_unknown_altitude_mixed_distance_or_occupied_ground_preflight_no_cost(self):
  for mode in ('unknown','mixed','occupied'):
   self.setUp();self.p.airborne=True;options={}
   if mode!='unknown':self.p.spec['_movement_altitude']=3
   if mode=='occupied':self.q.pos=self.p.pos;options['gm_distance']=5
   before=self.state()
   with self.assertRaises(ValueError):self.fire(**options)
   self.assertEqual(before,self.state())
 def test_modern_capture_real_net_adds_four_and_actual_snare_adds_two_more(self):
  for snare in (False,True):
   self.setUp();self.fire();self.a.spec['items']['몬스터볼']=1;self.p.spec['evolutions_remaining']=0
   if snare:self.a.spec.update(classes=['class/포획전문가'],capture_techniques=['덫'])
   self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=3 if snare else 5));r=self.a.spec['capture_attempts']['capture-1'];self.assertEqual(r['net_bonus'],4);self.assertEqual(r['snare_bonus'],2 if snare else 0);self.assertEqual(r['capture_total'],12)
 def test_removed_or_owned_target_has_no_net_capture_bonus(self):
  self.fire();self.p.spec['trainer_id']='someone';self.assertEqual(NET.capture_bonus(self.e,self.p),0);self.p.spec.pop('trainer_id');self.e.remove_net(self.p,fixed=10);self.assertEqual(NET.capture_bonus(self.e,self.p),0)
 def test_selected_source_replacement_and_duplicate_nets_fail_before_cost(self):
  original=self.e.r._selected_rule
  try:
   self.e.r._selected_rule=lambda uid:uid+'/unreviewed' if uid==NET.SOURCE else original(uid);before=self.state()
   with self.assertRaises(ValueError):self.fire()
   self.assertEqual(before,self.state())
  finally:self.e.r._selected_rule=original
  self.fire();before=self.state()
  with self.assertRaises(ValueError):self.fire()
  self.assertEqual(before,self.state())
 def test_nonmove_heavy_standard_remains_explicitly_pending_before_cost(self):
  self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a);self.a.injuries=5;before=self.state()
  with self.assertRaises(ValueError):self.fire()
  self.assertEqual(before,self.state());self.a.injuries=0;self.fire();self.e.end_of_turn(self.a);self.e.start_of_turn(self.p);self.p.injuries=5;budget=dict(self.p.budget)
  with self.assertRaises(ValueError):self.e.remove_net(self.p,fixed=10)
  self.assertEqual(self.p.budget,budget);self.assertIsNotNone(NET.active(self.p))
 def test_fixed_source_scope_unchanged(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8-sig'))['entries'];row=next(x for x in rows if x['id']=='C3-EX-118')
  for a in row['source_snapshot']['source_anchors']:
   text='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']]);self.assertEqual(text,a['excerpt'])
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(NetTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/injury_recovery.py','engine/downtime.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/net_capsule.py','engine/combat_timing.py','engine/engine.py','engine/movement_actions.py','engine/effects_ext.py','engine/items.py','engine/turn.py','engine/action_lifecycle.py','engine/wild_equipment.py','engine/pokemon_activities.py','engine/crafting_activities.py','engine/capability_actions.py','engine/skill_modifiers.py','engine/ap_roll_bonus.py','data/rulesets.json','data/core-rules.json','data/items-mech.json','data/items-reviewed.json','data/conditions.json','output/ruleunits.jsonl','input/supp-errata.md','tools/test_category3_net_capsule.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-118'],'completion':'fixed-scope candidate; global non-Move Standard heavy-injury composition is external pending dependency','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-net-capsule-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
