"""Native food inventory, Extended intake, recipient and source constraints."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
import food_effects as FOOD
import common_checks as C
class FoodTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core');cls.playtest=Rules(str(ROOT),ruleset='playtest')
 setUp=_fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp
 actor=_fixture_test_category3_pokemon_activities.PokemonActivityTests.actor
 def state(self):
  return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,[(c.spec,c.hp,c.temp_hp,c.stages,c.buffs,c.conditions,c.custom_conditions,getattr(c,'budget',None),getattr(c,'_action_history',None),getattr(c,'pending_action_loss',None),c.modifiers,c.registry) for c in (self.a,self.p,self.q)]))
 def drink(self,name='맛있는물',minutes=1):return self.e.use_item(self.a,name,self.p,duration_minutes=minutes,duration_reason='GM actual drinking time')
 def test_all_five_drinks_heal_actual_recipient_by_source_amount_after_extended_time(self):
  for uid,amount in FOOD.DRINKS.items():
   self.setUp();self.a.spec['items'][uid]=1;self.p.hp=1;before=self.a.hp;r=self.drink(uid)
   self.assertEqual(r['healed'],min(amount,self.p.max_hp-1));self.assertEqual(self.a.hp,before);self.assertEqual(self.a.spec['items'][uid],0);self.assertEqual(self.e.elapsed_seconds,60);self.assertEqual(self.p._action_history,['extended'])
 def test_one_per_hour_exact_completed_intake_boundary_and_no_day_reset_bypass(self):
  self.a.spec['items']['맛있는물']=3;self.p.hp=1;self.drink();before=self.state()
  with self.assertRaises(ValueError):self.drink()
  self.assertEqual(before,self.state());self.p.spec.setdefault('frequency_state',{})['day']=1
  with self.assertRaises(ValueError):self.drink()
  self.e.advance_time(3539,[self.p]);before=self.state()
  with self.assertRaises(ValueError):self.drink()
  self.assertEqual(before,self.state());self.e.advance_time(1,[self.p]);self.drink();self.assertEqual(self.e.elapsed_seconds,3660)
 def test_missing_duration_declined_and_missing_inventory_never_heal_or_spend(self):
  self.a.spec['items']['맛있는물']=1;self.p.hp=1;before=self.state();r=self.e.use_item(self.a,'맛있는물',self.p);self.assertIsInstance(r,C.PendingDecision);self.assertEqual(before,self.state())
  self.e.use_item(self.a,'맛있는물',self.p,accepted=False);self.assertEqual(before,self.state());self.a.spec['items']['맛있는물']=0;before=self.state()
  with self.assertRaises(ValueError):self.drink()
  self.assertEqual(before,self.state())
 def test_drinks_cannot_be_consumed_in_combat_or_by_unconscious_sleeping_consumer(self):
  self.a.spec['items']['맛있는물']=3
  for status in ('잠듦','얼음'):
   self.p.conditions.add(status);before=self.state();self.assertIs(self.drink(),False);self.assertEqual(before,self.state());self.p.conditions.remove(status)
  self.p.hp=0
  with self.assertRaises(ValueError):self.drink()
  self.p.hp=20;self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a);before=self.state()
  with self.assertRaises(ValueError):self.drink()
  self.assertEqual(before,self.state())
 def test_unknown_elapsed_does_not_assert_hour_limit_reset(self):
  self.a.spec['items']['맛있는물']=2;self.drink();self.e.unresolved_time_intervals.append({'round':0,'reason':'unknown'});before=self.state();r=self.drink();self.assertIsInstance(r,C.PendingDecision);self.assertEqual(before,self.state())
  self.e.advance_time(3600,[self.p]);self.assertEqual(self.drink()['status'],'consumed')
 def test_selected_playtest_gluttony_allows_two_drinks_per_thirty_minutes(self):
  self.rules=self.playtest;self.setUp();self.p.abilities=['먹보 [Playtest]'];self.a.spec['items']['맛있는물']=4
  self.drink();self.drink();before=self.state()
  with self.assertRaises(ValueError):self.drink()
  self.assertEqual(before,self.state());self.e.advance_time(1680,[self.p]);self.drink();self.assertEqual(self.a.spec['items']['맛있는물'],1)
 def test_suppressed_gluttony_uses_ordinary_limit_and_unselected_version_cannot_grant_exception(self):
  self.rules=self.playtest;self.setUp();self.p.abilities=['먹보 [Playtest]'];self.p.abilities_suppressed=True;self.a.spec['items']['맛있는물']=2;self.drink()
  with self.assertRaises(ValueError):self.drink()
  self.rules=Rules(str(ROOT),ruleset='core');self.setUp();self.p.abilities=['먹보 [Playtest]'];self.a.spec['items']['맛있는물']=1;before=self.state()
  with self.assertRaises(ValueError):self.drink()
  self.assertEqual(before,self.state())
 def test_replaced_food_source_and_multiple_serving_request_reject_before_cost(self):
  self.a.spec['items']['맛있는물']=2;original=self.e.r._selected_rule
  try:
   self.e.r._selected_rule=lambda uid, *args, **kwargs: uid + '/unsupported' if uid == FOOD.DRINK_SOURCE else original(uid, *args, **kwargs);before=self.state()
   with self.assertRaises(ValueError):self.drink()
   self.assertEqual(before,self.state())
  finally:self.e.r._selected_rule=original
  before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'맛있는물',self.p,count=2,duration_minutes=1,duration_reason='invalid combined servings')
  self.assertEqual(before,self.state())
 def snack(self,name='초코바',target=None):
  self.a.spec['items'][name]=self.a.spec['items'].get(name,0)+1
  return self.e.use_item(self.a,name,target or self.p,duration_minutes=1,duration_reason='GM actual snack intake')
 def herb(self,name='힘의가루',target=None):
  self.a.spec['items'][name]=self.a.spec['items'].get(name,0)+1
  return self.e.use_item(self.a,name,target or self.p)
 def seed_for_faces(self,*faces):
  import random
  for seed in range(200000):
   rng=random.Random(seed)
   if tuple(rng.randint(1,6) for _ in faces)==faces:self.e.rng.seed(seed);return
  self.fail('test dice sequence not found')
 def test_snack_eating_grants_actual_buff_without_healing_then_explicit_action_consumes_once(self):
  self.p.hp=1;r=self.snack();self.assertEqual(self.p.hp,1);self.assertEqual(self.a.spec['items']['초코바'],0)
  self.assertEqual(self.p.buffs[0]['id'],r['buff_id']);before=self.state();hp=self.p.hp
  self.assertIsInstance(self.e.consume_food_buff(self.p,buff_id=r['buff_id']),C.PendingDecision);self.assertEqual(self.state(),before);self.assertEqual(self.p.hp,hp)
  used=self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='GM declared buff consumption timing');self.assertEqual(used['healed'],5);self.assertFalse(self.p.buffs)
  with self.assertRaises(ValueError):self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='retry')
 def test_snack_capacity_is_recipient_scoped_and_consumption_frees_it(self):
  r=self.snack();self.a.spec['items']['꿀']=1;before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'꿀',self.p,duration_minutes=1,duration_reason='full recipient')
  self.assertEqual(before,self.state());self.snack('초코바',self.q);self.assertEqual((len(self.p.buffs),len(self.q.buffs)),(1,1))
  self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='GM timing');self.snack('꿀');self.assertEqual(len(self.p.buffs),1)
 def test_black_sludge_requires_poison_pokemon_and_never_heals_on_possession(self):
  self.a.spec['items']['검은오물']=1;self.p.hp=1;before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'검은오물',self.p,duration_minutes=1,duration_reason='wrong type')
  self.assertEqual(before,self.state());self.p.types=['독'];r=self.snack('검은오물');self.assertEqual(self.p.hp,1)
  self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20);self.assertEqual(self.p.hp,1)
  self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='GM buff timing');self.e.end_of_turn(self.p);self.assertEqual(self.p.hp,1)
  self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20);self.assertEqual(self.p.hp,1+self.p.base_max_hp//8)
 def test_leftovers_uses_base_max_hp_at_turn_start_only_and_ends_with_encounter(self):
  self.p.hp=1;self.p.injuries=1;r=self.snack('먹다남은음식');self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20)
  self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='GM buff timing');self.e.end_of_turn(self.p)
  self.assertEqual(self.p.hp,1);self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20);self.assertEqual(self.p.hp,1+self.p.base_max_hp//16)
  self.e.end_encounter([self.p]);self.assertNotIn('food_turn_healing',self.p.spec);before=self.p.hp
  self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20);self.assertEqual(self.p.hp,before)
 def test_gluttony_three_buff_capacity_and_three_consumptions_per_scene(self):
  self.rules=self.playtest;self.setUp();self.p.abilities=['먹보 [Playtest]']
  for _ in range(3):self.snack()
  with self.assertRaises(ValueError):self.snack()
  for b in list(self.p.buffs):self.e.consume_food_buff(self.p,buff_id=b['id'],action_kind='free',action_reason='GM timing')
  r=self.snack();before=self.state()
  with self.assertRaises(ValueError):self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='scene fourth use')
  self.assertEqual(before,self.state());self.e.end_encounter([self.p])
  with self.assertRaises(ValueError):self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='same scene')
  self.e.end_scene([self.p]);self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='new scene')
 def test_first_herb_heals_and_grants_optional_save_buff_with_no_extra_action(self):
  self.p.hp=1;self.herb();self.assertEqual(self.p.hp,26);self.assertEqual(self.p.spec['herbal_restoratives']['count'],1)
  buff=self.p.buffs[0];self.assertEqual(buff['effect'],{'kind':'save_bonus','amount':2});self.e.apply_status(self.p,'마비')
  self.e.consume_food_buff(self.p,buff_id=buff['id'],save_condition='마비');self.assertEqual(len(self.p.buffs),1)
  import random
  for seed in range(100):
   if random.Random(seed).randint(1,20)==9:self.e.rng.seed(seed);break
  self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20)
  self.assertIn('마비',self.p.conditions);self.assertIsNone(self.p._turn_action_limit);self.assertFalse(self.p.buffs);self.assertNotIn('food_save_choice',self.p.spec);self.assertEqual(self.p._action_history,[])
 def test_prepared_herbal_buff_is_only_spent_on_the_selected_actual_save(self):
  self.herb();buff=self.p.buffs[0]
  from native_scenario_fixture import assert_rejected_unchanged
  assert_rejected_unchanged(self.e,
   lambda:self.e.consume_food_buff(self.p,buff_id=buff['id'],save_condition='혼란'),
   reason_pattern='native saving-check consumer required')
  self.e.consume_food_buff(self.p,buff_id=buff['id'],save_condition='얼음')
  self.e.apply_status(self.p,'마비');self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20);self.assertEqual(len(self.p.buffs),1)
  self.e.apply_status(self.p,'얼음');self.e.end_of_turn(self.p);self.assertFalse(self.p.buffs)
 def test_second_herb_blocks_new_food_and_temp_hp_but_keeps_existing_buff_and_temp_hp(self):
  import temporary_hp as TEMP
  self.herb();buff=self.p.buffs[0]['id'];TEMP.grant(self.e,self.p,7);self.herb();self.assertEqual(self.p.temp_hp,7);self.assertEqual(TEMP.grant(self.e,self.p,20),0)
  self.assertEqual(self.p.buffs[0]['id'],buff);self.assertEqual(self.p.spec['herbal_restoratives']['count'],2)
  self.a.spec['items']['꿀']=1;before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'꿀',self.p,duration_minutes=1,duration_reason='blocked after two herbs')
  self.assertEqual(before,self.state());self.p.hp=1;self.a.spec['items']['맛있는물']=1;self.drink();self.assertEqual(self.p.hp,21)
 def test_third_and_later_herbs_roll_actual_d6_with_six_reroll_and_cumulative_base_penalty(self):
  self.herb();self.herb();self.seed_for_faces(6,6,4);self.herb();state=self.p.spec['herbal_restoratives'];self.assertEqual(state['uses'][-1]['faces'],[6,6,4]);self.assertEqual(self.p.stages['spd'],-1)
  self.seed_for_faces(4);self.herb();self.assertEqual(self.p.stages['spd'],-2);self.assertEqual(self.p.stages['atk'],0)
 def test_herbal_base_penalty_survives_encounter_and_short_rest_then_real_extended_rest_resets(self):
  import downtime as DT
  self.herb();self.herb();self.seed_for_faces(1);self.herb();self.e.change_stage(self.p,'atk',2);self.assertEqual(self.p.stages['atk'],1)
  self.e.end_encounter([self.p]);self.assertEqual(self.p.stages['atk'],-1);DT.new_day(self.p);self.assertEqual(self.p.spec['herbal_restoratives']['count'],3)
  DT.rest(self.e,self.p,60);self.assertEqual(self.p.stages['atk'],-1);self.assertEqual(self.p.spec['herbal_restoratives']['count'],3)
  DT.extended_rest(self.e,self.p,4);self.assertEqual(self.p.stages['atk'],0);self.assertNotIn('herbal_restoratives',self.p.spec)
 def test_clamped_herbal_penalty_does_not_erase_preexisting_combat_stage_on_rest(self):
  import downtime as DT
  self.e.change_stage(self.p,'atk',-6);self.herb();self.herb();self.seed_for_faces(1);self.herb();self.assertEqual(self.p.stages['atk'],-6)
  DT.extended_rest(self.e,self.p,4);self.assertEqual(self.p.stages['atk'],-6)
 def test_untracked_stage_writer_is_held_before_new_herb_or_rest_cost(self):
  import downtime as DT
  self.herb();self.herb();self.seed_for_faces(1);self.herb();self.p.stages['atk']=3;self.a.spec['items']['힘의가루']=1;before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'힘의가루',self.p)
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):DT.extended_rest(self.e,self.p,4)
  self.assertEqual(before,self.state())
 def test_herbal_revive_and_cure_use_native_effects_then_same_consumption_counter(self):
  self.e.apply_status(self.p,'독');self.herb('만능가루');self.assertNotIn('독',self.p.conditions);self.assertEqual(self.p.spec['herbal_restoratives']['count'],1)
  self.p.hp=0;self.e.check_fainted(self.p);result=self.herb('부활초');self.assertEqual(result,(1,0));self.assertFalse(self.p.fainted);self.assertEqual(self.p.hp,self.p.base_max_hp//2);self.assertEqual(self.p.spec['herbal_restoratives']['count'],2)
 def test_declined_herb_never_counts_or_rolls_or_consumes(self):
  self.a.spec['items']['힘의가루']=1;before=self.state();self.e.use_item(self.a,'힘의가루',self.p,accepted=False);self.assertEqual(before,self.state());self.assertNotIn('herbal_restoratives',self.p.spec)
 def test_conflicting_baby_food_stays_held_before_cost(self):
  self.a.spec['items']['이유식']=1;before=self.state();r=self.e.use_item(self.a,'이유식',self.p,duration_minutes=1,duration_reason='source policy required');self.assertIsInstance(r,C.PendingDecision);self.assertEqual(before,self.state())
 def built_pokemon(self,level=15):
  from builder import build_pokemon
  from engine import Combatant
  spec=build_pokemon(self.rules,'이상해씨',level,strategy='special',extra={'id':'pokemon/baby','trainer_id':self.a.spec['id'],'items':{}})
  self.p=Combatant(self.rules,spec);self.e.gm.everyone=[self.a,self.p,self.q];return self.p
 def baby(self,policy,level=15):
  self.built_pokemon(level);self.a.spec['items']['이유식']=1
  return self.e.use_item(self.a,'이유식',self.p,duration_minutes=1,duration_reason='actual BabyFood intake',food_policy=policy)
 def test_berry_half_hp_boundary_uses_true_maximum_and_requires_actual_buff(self):
  r=self.snack('오랭열매');self.p.injuries=1;self.p.hp=self.p.base_max_hp//2+1;before=self.state()
  with self.assertRaises(ValueError):self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='GM timing')
  self.assertEqual(before,self.state());self.p.hp=self.p.base_max_hp//2;result=self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='GM timing');self.assertEqual(result['healed'],5)
 def test_status_berry_can_cure_its_actual_status_above_half_hp(self):
  r=self.snack('버치열매');self.e.apply_status(self.p,'마비');self.assertGreater(self.p.hp,self.p.base_max_hp//2)
  result=self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='GM chosen buff timing');self.assertTrue(result['cured']);self.assertNotIn('마비',self.p.conditions)
 def test_sleep_berry_explicit_self_cure_swift_is_permitted_but_unrelated_food_is_not(self):
  r=self.snack('유루열매');self.e.apply_status(self.p,'잠듦');result=self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='GM self-cure timing');self.assertTrue(result['cured'])
  r=self.snack('초코바');self.e.apply_status(self.p,'잠듦');before=self.state();self.assertIs(self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='not sleep cure'),False);self.assertEqual(before,self.state())
 def test_type_berry_changes_actual_damage_one_resistance_step_only_once(self):
  self.p.types=['풀'];move=self.e.r.move('move/불꽃세례');baseline=self.e.roll_damage(self.q,self.p,move,set_damage=True)
  r=self.snack('오카열매');self.e.consume_food_buff(self.p,buff_id=r['buff_id']);self.assertEqual(len(self.p.buffs),1)
  first=self.e.roll_damage(self.q,self.p,move,set_damage=True);self.assertLess(first,baseline);self.assertFalse(self.p.buffs);self.assertEqual(self.e.roll_damage(self.q,self.p,move,set_damage=True),baseline)
 def test_type_berry_waits_for_matching_super_effective_type_and_does_not_consume_on_miss(self):
  self.p.types=['노말'];r=self.snack('오카열매');self.e.consume_food_buff(self.p,buff_id=r['buff_id']);self.e.roll_damage(self.q,self.p,self.e.r.move('move/불꽃세례'),set_damage=True);self.assertEqual(len(self.p.buffs),1)
  self.p.types=['풀'];self.e.roll_damage(self.q,self.p,self.e.r.move('struggle'),set_damage=True);self.assertEqual(len(self.p.buffs),1)
  self.assertFalse(self.e.accuracy_check(self.q,self.p,self.e.r.move('move/불꽃세례'),fixed_roll=1)[0]);self.assertEqual(len(self.p.buffs),1)
 def test_normal_type_berry_has_no_super_effective_requirement_and_suppression_does_not_disable_food(self):
  self.p.types=['노말'];move=self.e.r.move('struggle');baseline=self.e.roll_damage(self.q,self.p,move,set_damage=True);r=self.snack('카리열매');self.e.consume_food_buff(self.p,buff_id=r['buff_id']);self.p.abilities_suppressed=True
  self.assertLess(self.e.roll_damage(self.q,self.p,move,set_damage=True),baseline);self.assertFalse(self.p.buffs)
 def test_wonder_guard_preview_does_not_consume_berry_or_retroactively_block_weakness_hit(self):
  self.p.types=['풀'];self.p.abilities=['불가사의부적'];r=self.snack('오카열매');self.e.consume_food_buff(self.p,buff_id=r['buff_id']);move=self.e.r.move('move/불꽃세례')
  hit=self.e.accuracy_check(self.q,self.p,move,fixed_roll=20)[0];self.assertTrue(hit);self.assertEqual(len(self.p.buffs),1)
  damage=self.e.roll_damage(self.q,self.p,move,set_damage=True);self.assertGreater(damage,0);self.assertFalse(self.p.buffs)
 def test_unsupported_berry_never_uses_legacy_immediate_effect_without_digestion(self):
  self.a.spec['items']['스타열매']=1;before=self.state();result=self.e.use_item(self.a,'스타열매',self.p,duration_minutes=1,duration_reason='individual berry adapter pending');self.assertIsInstance(result,C.PendingDecision);self.assertEqual(before,self.state())
 def test_book_baby_food_adds_twenty_percent_exact_floor_to_actual_xp_at_level15(self):
  import downtime as DT
  self.baby('book_xp20_level15',15);before=self.p.spec.get('exp',DT.exp_for_level(self.rules,15));DT.gain_exp_combatant(self.e,self.p,9);self.assertEqual(self.p.spec['exp']-before,10)
  self.assertFalse(self.p.buffs);self.assertNotIn('drink_history',self.p.spec)
 def test_book_baby_food_level16_and_new_day_do_not_grant_xp_bonus(self):
  import downtime as DT
  for level,newday in ((16,False),(15,True)):
   self.setUp();self.baby('book_xp20_level15',level)
   if newday:DT.new_day(self.p)
   before=self.p.spec.get('exp',DT.exp_for_level(self.rules,level));DT.gain_exp_combatant(self.e,self.p,10);self.assertEqual(self.p.spec['exp']-before,10)
 def test_book_baby_food_does_not_amplify_direct_next_level_grants(self):
  import downtime as DT
  self.baby('book_xp20_level15',15);DT.gain_exp_combatant(self.e,self.p,'to next level');self.assertEqual(self.p.level,16);self.assertEqual(self.p.spec['exp'],DT.exp_for_level(self.rules,16))
 def test_book_baby_food_actual_training_and_day_expiry_survive_gm_and_json_restore(self):
  import state_codec as CODEC,downtime as DT
  self.baby('book_xp20_level15',15);record=deepcopy(self.p.spec['baby_food'])
  self.assertEqual(record['source'],'item/이유식');self.assertEqual(record['level_when_fed'],15)
  self.assertTrue(record['eligible_when_fed']);self.assertEqual(self.a.spec['items']['이유식'],0)
  self.assertEqual(self.e.elapsed_seconds,60);self.assertEqual(self.p._action_history,['extended'])
  self.assertFalse(self.p.buffs);self.assertNotIn('drink_history',self.p.spec)
  self.a.spec['items']['이유식']=1;before=self.state()
  pending=self.e.use_item(self.a,'이유식',self.p,duration_minutes=1,duration_reason='duplicate book intake',food_policy='book_xp20_level15')
  self.assertIsInstance(pending,C.PendingDecision);self.assertEqual(before,self.state())
  initial_xp=self.p.spec['exp'];snapshot=self.e.gm.snapshot()
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  DT.gain_exp_combatant(self.e,self.p,9);self.e.gm.restore(snapshot)
  for e in (self.e,loaded):
   actor=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   target=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
   self.assertEqual(target.spec['baby_food'],record);self.assertEqual(target.spec['exp'],initial_xp)
   e.pokemon_activity(actor,'experience_training',targets=[target],safe=True)
   award=target.spec['experience_training_history'][-1]['base_award']
   self.assertGreater(award,0);self.assertEqual(target.spec['exp']-initial_xp,award*6//5)
   self.assertEqual(target.level,15);self.assertEqual(e.elapsed_seconds,3660)
   self.assertEqual(target.spec['baby_food'],record);self.assertEqual(actor.spec['items']['이유식'],1)
   before_xp=target.spec['exp'];DT.gain_exp_combatant(e,target,9)
   self.assertEqual(target.spec['exp']-before_xp,10)
   resumed=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)))
   owner=next(c for c in resumed.gm.everyone if c.entity_id==actor.entity_id)
   pokemon=next(c for c in resumed.gm.everyone if c.entity_id==target.entity_id)
   DT.new_day(owner);DT.new_day(pokemon);before_xp=pokemon.spec['exp']
   DT.gain_exp_combatant(resumed,pokemon,10)
   self.assertEqual(pokemon.spec['exp']-before_xp,10);self.assertEqual(pokemon.spec['baby_food'],record)
 def test_raw_baby_food_actual_training_adds_one_level_at_feed_level20_only(self):
  for level,expected in ((20,21),(21,21)):
   self.setUp();self.baby('raw_training_level20',level)
   if level==20:
    before=self.state()
    with self.assertRaisesRegex(ValueError,'sourced capacity'):self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],safe=True)
    self.assertEqual(before,self.state())
    # This fixture already knows six moves. The native growth path requires
    # the player's explicit forgotten-move choice before learning at level21.
    self.e.gm.set_move(self.p,next(m for m in self.p.moves if m!='struggle'),False,reason='player chose a slot for actual level-up move')
   result=self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],safe=True);self.assertEqual(self.p.level,expected);self.assertEqual(self.e.elapsed_seconds,3660)
   self.assertEqual(self.p.spec['baby_food']['consumed'],level==20)
 def test_raw_baby_food_is_not_an_xp_percentage_or_daily_repeating_level_bonus(self):
  import downtime as DT
  self.baby('raw_training_level20',15);before=self.p.spec.get('exp',DT.exp_for_level(self.rules,15));DT.gain_exp_combatant(self.e,self.p,10);self.assertEqual(self.p.spec['exp']-before,10)
  self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],safe=True);self.assertEqual(self.p.level,16);DT.new_day(self.a);DT.new_day(self.p);self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],safe=True);self.assertEqual(self.p.level,16)
 def test_baby_food_requires_pokemon_and_explicit_supported_source_policy_before_cost(self):
  self.a.spec['items']['이유식']=1;before=self.state()
  with self.assertRaises(ValueError):self.e.use_item(self.a,'이유식',self.a,duration_minutes=1,duration_reason='trainer target',food_policy='book_xp20_level15')
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.e.use_item(self.a,'이유식',self.p,duration_minutes=1,duration_reason='unknown policy',food_policy='guess')
  self.assertEqual(before,self.state())
 def test_raw_baby_food_pending_intake_and_consumed_training_survive_gm_and_json_restore(self):
  import state_codec as CODEC,downtime as DT
  self.baby('raw_training_level20',15)
  record=deepcopy(self.p.spec['baby_food'])
  self.a.spec['items']['이유식']=1;before=self.state()
  pending=self.e.use_item(self.a,'이유식',self.p,duration_minutes=1,duration_reason='duplicate actual intake',food_policy='raw_training_level20')
  self.assertIsInstance(pending,C.PendingDecision);self.assertEqual(before,self.state())
  snapshot=self.e.gm.snapshot()
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  self.e.gm.restore(snapshot)
  for e in (self.e,loaded):
   actor=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id)
   target=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
   self.assertEqual(target.spec['baby_food'],record)
   self.assertEqual(actor.spec['items']['이유식'],1)
   e.pokemon_activity(actor,'experience_training',targets=[target],safe=True)
   self.assertEqual(target.level,16);self.assertTrue(target.spec['baby_food']['consumed'])
   resumed=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)))
   owner=next(c for c in resumed.gm.everyone if c.entity_id==actor.entity_id)
   pokemon=next(c for c in resumed.gm.everyone if c.entity_id==target.entity_id)
   DT.new_day(owner);DT.new_day(pokemon)
   resumed.pokemon_activity(owner,'experience_training',targets=[pokemon],safe=True)
   self.assertEqual(pokemon.level,16);self.assertTrue(pokemon.spec['baby_food']['consumed'])
 def test_type_berry_actual_use_move_commits_reduced_hp_damage_and_miss_preserves_buff(self):
  import random
  damage=[]
  for with_buff,natural in ((False,10),(True,10),(True,1)):
   self.setUp();self.p.types=['풀'];self.q.moves=['move/불꽃세례']
   if with_buff:
    buff=self.snack('오카열매');self.e.consume_food_buff(self.p,buff_id=buff['buff_id'])
   self.e.start_round([self.q,self.p]);self.e.start_of_turn(self.q)
   for seed in range(500):
    if random.Random(seed).randint(1,20)==natural:self.e.rng.seed(seed);break
   before=self.p.hp;self.e.use_move(self.q,self.p,'move/불꽃세례',set_damage=True);damage.append(before-self.p.hp)
   self.assertEqual(len(self.p.buffs),1 if with_buff and natural==1 else 0);self.assertEqual(self.q.budget['standard'],0)
  self.assertGreater(damage[0],damage[1]);self.assertGreater(damage[1],0);self.assertEqual(damage[2],0)
 def test_extended_snack_in_combat_is_timing_pending_not_a_drink_prohibition(self):
  self.a.spec['items']['초코바']=1;self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a);before=self.state()
  # ch09:202 requires Extended intake; ch07:61 prohibits Extended Actions in combat.
  with self.assertRaisesRegex(ValueError,'active encounter'):
   self.e.use_item(self.a,'초코바',self.p,duration_minutes=1,duration_reason='spans native turns')
  self.assertEqual(before,self.state())
 def cheeks_turn(self):
  self.p.moves=['move/볼가득넣기'];self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20)
 def test_actual_stuff_cheeks_without_buff_has_no_defense_reward_and_no_invented_refund(self):
  self.cheeks_turn();self.e.use_move(self.p,self.p,'move/볼가득넣기');self.assertEqual(self.p.stages['def'],0);self.assertEqual(self.p.budget['standard'],0);self.assertNotIn('food_consumption_receipts',self.p.spec)
 def test_actual_stuff_cheeks_applies_same_buff_benefit_and_single_scene_receipt(self):
  r=self.snack();self.p.hp=1;self.cheeks_turn();self.e.use_move(self.p,self.p,'move/볼가득넣기');self.assertEqual(self.p.hp,6);self.assertEqual(self.p.stages['def'],2);self.assertFalse(self.p.buffs)
  self.assertEqual(self.p.counters['food_buff_consumed'],1);self.assertEqual(self.p.counters['lim:food_buff_consumed'],1);receipts=self.p.spec['food_consumption_receipts'];self.assertEqual(len(receipts),1);self.assertEqual(receipts[0]['buff_id'],r['buff_id']);self.assertEqual(receipts[0]['producer'],'move/볼가득넣기');self.assertEqual(receipts[0]['benefit']['healed'],5);self.assertEqual(self.p._action_history,['standard'])
 def test_stuff_cheeks_waives_berry_trigger_only_not_buff_ownership_or_effect(self):
  r=self.snack('오랭열매');self.p.hp=self.p.base_max_hp-4;before=self.state()
  with self.assertRaises(ValueError):self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='ordinary berry above half')
  self.assertEqual(before,self.state());self.cheeks_turn();self.e.use_move(self.p,self.p,'move/볼가득넣기');self.assertEqual(self.p.hp,self.p.base_max_hp);self.assertFalse(self.p.buffs);self.assertEqual(self.p.counters['lim:food_buff_consumed'],1)
 def test_stuff_cheeks_multiple_buffs_require_actual_choice_before_move_cost(self):
  self.rules=self.playtest;self.setUp();self.p.abilities=['먹보 [Playtest]'];first=self.snack();second=self.snack('꿀');self.p.hp=1;self.cheeks_turn();before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertEqual(before,self.state());self.e.consume_food_buff(self.p,buff_id=second['buff_id'],move_id='move/볼가득넣기');self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertEqual([b['id'] for b in self.p.buffs],[first['buff_id']]);self.assertEqual(self.p.hp,6);self.assertNotIn('food_move_choice',self.p.spec);self.assertEqual(self.p.spec['food_consumption_receipts'][0]['buff_id'],second['buff_id'])
 def test_stuff_cheeks_cannot_bypass_gluttony_scene_cap_or_replay_consumed_buff(self):
  self.rules=self.playtest;self.setUp();self.p.abilities=['먹보 [Playtest]']
  for _ in range(3):
   r=self.snack();self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='native scene use')
  r=self.snack();self.cheeks_turn();before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertEqual(before,self.state());self.assertEqual(len(self.p.spec['food_consumption_receipts']),3)
 def test_stuff_cheeks_unresolved_save_benefit_and_stale_stage_hold_before_move_cost(self):
  self.herb();self.cheeks_turn();before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertEqual(before,self.state())
  self.setUp();self.snack();self.cheeks_turn();import combat_stage_sources as STAGES
  STAGES.add_base(self.p,'herbal_restoratives','def',-1,source=FOOD.MEDICINE,ends='extended_rest');self.p.stages['def']=3;before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertEqual(before,self.state())
 def test_common_consumption_receipt_preserves_turn_heal_until_actual_encounter_end(self):
  self.snack('먹다남은음식');self.p.hp=1;self.cheeks_turn();self.e.use_move(self.p,self.p,'move/볼가득넣기');self.assertEqual(self.p.hp,1);self.assertEqual(self.p.spec['food_consumption_receipts'][0]['benefit']['until'],'encounter_end')
  self.e.end_of_turn(self.p);self.e.start_round([self.p]);self.e.start_of_turn(self.p,initiative_count=20);self.assertEqual(self.p.hp,1+self.p.base_max_hp//16);self.e.end_encounter([self.p]);self.assertNotIn('food_turn_healing',self.p.spec)
 def test_completed_consumption_receipt_rejects_reinserted_buff_before_new_move_or_action_cost(self):
  r=self.snack();saved=deepcopy(self.p.buffs[0]);self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='free',action_reason='one actual exchange');self.p.buffs.append(saved);self.cheeks_turn();before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,'move/볼가득넣기')
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.e.consume_food_buff(self.p,buff_id=r['buff_id'],action_kind='swift',action_reason='invalid replay')
  self.assertEqual(before,self.state());self.assertEqual(len(self.p.spec['food_consumption_receipts']),1)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(FoodTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/food_effects.py','engine/restorative_items.py','engine/combat_stage_sources.py','engine/net_capsule.py','engine/effects.py','engine/effects_ext.py','engine/combat_timing.py','engine/items.py','engine/engine.py','engine/downtime.py','engine/pokemon_activities.py','engine/builder.py','engine/temporary_hp.py','engine/action_lifecycle.py','engine/life.py','data/rulesets.json','data/items-mech.json','data/items-reviewed.json','output/ruleunits.jsonl','input/ch09-equipment.md','input/db/abilities.csv','input/db/inventory.csv','tools/test_category3_food_effects.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-069 herbal native mechanics','DOMAIN-071 fixed scope'],'completion':'native food/digestion/conditional berry producer and selected BabyFood source policies; individual unsupported berry/ability catalog records remain separate adapters','results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-food-effects-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
