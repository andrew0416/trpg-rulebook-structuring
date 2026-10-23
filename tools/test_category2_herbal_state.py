"""Native shared herbal histories, save benefits and rest boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import random,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_condition_recovery as FIX
import test_category2_temporary_hp_state as _fixture_test_category2_temporary_hp_state
import food_effects as FOOD,downtime as D,temporary_hp as TEMP,combat_stage_sources as STAGES,state_codec as CODEC

class HerbalStateTests(unittest.TestCase):
 setUpClass=classmethod(FIX.ConditionRecoveryTests.setUpClass.__func__)
 setUp=FIX.ConditionRecoveryTests.setUp
 add=FIX.ConditionRecoveryTests.add
 restored=FIX.ConditionRecoveryTests.restored
 native_grant=_fixture_test_category2_temporary_hp_state.TemporaryHPStateTests.native_grant
 def herb(self,actor,name='힘의가루',*,user=None,accepted=True):
  user=user or actor;user.spec.setdefault('items',{})[name]=user.spec.get('items',{}).get(name,0)+1
  return self.e.use_item(user,name,actor,accepted=accepted)
 def faces(self,*faces):
  for seed in range(100000):
   rng=random.Random(seed)
   if [rng.randint(1,6) for _ in faces]==list(faces):self.e.rng.seed(seed);return
  self.fail('deterministic d6 fixture missing')
 def snap(self):
  return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone]),{id(self.r):self.r})
 def test_actual_counts_are_recipient_scoped_and_all_herbs_share_one_history(self):
  self.herb(self.a);self.herb(self.p,user=self.a);self.herb(self.p,'힘의뿌리',user=self.a)
  self.assertEqual(FOOD.herbal_state(self.a)['count'],1);self.assertEqual(FOOD.herbal_state(self.p)['count'],2)
  self.e.apply_status(self.p,'독');self.faces(1);self.herb(self.p,'만능가루',user=self.a);self.assertNotIn('독',self.p.conditions)
  self.p.hp=0;self.e.check_fainted(self.p);self.faces(2);self.herb(self.p,'부활초',user=self.a)
  state=FOOD.validate_herbal(self.p)
  self.assertEqual(state['count'],4);self.assertEqual({r['item'] for r in state['uses']},FOOD.HERBS-{'item/파스'})
  self.assertFalse(self.p.fainted);self.assertEqual(self.p.hp,self.p.base_max_hp//2)
  self.assertEqual(FOOD.herbal_state(self.a)['count'],1)
 def test_first_buff_changes_actual_save_once_for_both_kinds_after_restore(self):
  for kind in ('trainer','pokemon'):
   self.setUp();actor=self.a if kind=='trainer' else self.p
   self.herb(actor);buff=actor.buffs[0];self.e.apply_status(actor,'마비')
   self.e.consume_food_buff(actor,buff_id=buff['id'],save_condition='마비')
   for seed in range(1000):
    if random.Random(seed).randint(1,20)==9:self.e.rng.seed(seed);break
   snapshot=self.e.gm.snapshot();loaded=self.restored();copy=next(c for c in loaded.gm.everyone if c.entity_id==actor.entity_id)
   for e,c in ((self.e,actor),(loaded,copy)):
    e.start_round([c]);e.start_of_turn(c)
    self.assertIsNone(c._turn_action_limit);self.assertFalse(c.buffs);self.assertEqual(c._action_history,[])
    self.assertEqual(c.spec['food_consumption_receipts'][-1]['benefit'],{'save_condition':'마비','bonus':2})
    self.assertEqual(FOOD.herbal_state(c)['count'],1)
   self.e.gm.restore(snapshot);self.assertEqual(actor.buffs[0]['id'],buff['id'])
 def test_second_use_blocks_native_new_gains_but_preserves_old_resources_and_normal_potions(self):
  for kind in ('trainer','pokemon'):
   self.setUp();actor=self.a if kind=='trainer' else self.p;self.herb(actor);buff=actor.buffs[0]['id'];TEMP.grant(self.e,actor,1);self.herb(actor)
   self.assertEqual(actor.temp_hp,1);self.assertEqual(actor.buffs[0]['id'],buff)
   actor.spec['items']['꿀']=1;before=self.snap()
   with self.assertRaises(ValueError):self.e.use_item(actor,'꿀',duration_minutes=1,duration_reason='actual intake request')
   self.assertEqual(self.snap(),before)
   actor.spec['items']['상처약']=5
   for _ in range(5):
    actor.hp=1;self.e.use_item(actor,'상처약');self.assertEqual(actor.hp,21)
   self.assertEqual(actor.spec['items']['상처약'],0);self.assertEqual(FOOD.herbal_state(actor)['count'],2)
   TEMP.grant(self.e,actor,10);self.assertEqual(actor.temp_hp,1)
   # Bug Bite also transfers food. The same herbal restriction rejects that
   # source before it can trigger Honey Thief's secondary temporary HP grant.
   from effect_contracts import EffectContractError
   with self.assertRaisesRegex(EffectContractError,'recipient cannot acquire transferred food effect'):self.native_grant(actor)
   self.assertEqual(actor.move_uses.get('move/벌레먹기',0),0);self.assertEqual(actor.temp_hp,1)
   self.e.end_of_turn(actor);self.e.end_round()
   self.assertEqual(actor.buffs[0]['id'],buff)
 def test_all_five_random_branches_rerolls_and_unbounded_repeated_herbs_reach_base_state(self):
  for actor in self.actors:
   self.herb(actor);self.herb(actor)
   for face,stat in enumerate(('atk','def','spa','spd','spe'),1):
    self.faces(6,6,face);self.herb(actor);last=FOOD.herbal_state(actor)['uses'][-1]
    self.assertEqual(last['faces'],[6,6,face]);self.assertEqual(last['stat'],stat);self.assertEqual(actor.stages[stat],-1)
   self.faces(4);self.herb(actor);self.assertEqual(actor.stages['spd'],-2)
   self.assertEqual(FOOD.validate_herbal(actor)['count'],8)
 def test_only_actual_extended_rest_resets_that_recipient_and_resumes_after_save(self):
  for actor in self.actors:
   self.herb(actor);self.herb(actor);self.faces(1);self.herb(actor)
  self.e.end_encounter(self.actors);self.e.end_scene(self.actors)
  for actor in self.actors:D.new_day(actor);self.assertEqual(FOOD.herbal_state(actor)['count'],3)
  D.rest(self.e,self.a,239,rest_id='trainer-rest');self.assertEqual(FOOD.herbal_state(self.a)['count'],3)
  snap=self.e.gm.snapshot();loaded=self.restored();copy=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
  for e,c in ((self.e,self.a),(loaded,copy)):
   D.rest(e,c,1,rest_id='trainer-rest');self.assertEqual(FOOD.herbal_state(c)['count'],0);self.assertEqual(c.stages['atk'],0)
   self.assertTrue(FOOD.temp_hp_allowed(c));self.assertNotIn('herbal_restoratives',c.spec)
  self.assertEqual(FOOD.herbal_state(self.p)['count'],3);self.assertEqual(self.p.stages['atk'],-1)
  self.e.gm.restore(snap);self.assertEqual(FOOD.herbal_state(self.a)['count'],3)
  D.rest(self.e,self.a,1,rest_id='trainer-rest');D.extended_rest(self.e,self.p,4)
  self.assertEqual(FOOD.herbal_state(self.p)['count'],0)
 def test_rest_removes_exact_penalty_at_clamp_without_erasing_independent_stage(self):
  for actor in self.actors:
   self.e.change_stage(actor,'atk',-6);self.herb(actor);self.herb(actor);self.faces(1);self.herb(actor)
   self.assertEqual(actor.stages['atk'],-6)
  D.rest_many(self.e,self.actors,240,rest_id='shared-rest')
  for actor in self.actors:self.assertEqual(actor.stages['atk'],-6);self.assertEqual(FOOD.herbal_state(actor)['count'],0)
 def test_bad_count_faces_source_or_base_penalty_fail_before_stock_rng_time_or_export(self):
  self.herb(self.p);self.herb(self.p);self.faces(1);self.herb(self.p)
  baseline=deepcopy(self.p.spec);self.p.spec.setdefault('items',{})['힘의가루']=1;baseline=deepcopy(self.p.spec)
  mutations=[lambda s:s.update(count=True),lambda s:s.update(count=2),lambda s:s['uses'][2].update(faces=[1,2]),lambda s:s['uses'][2].update(faces=[6]),lambda s:s['uses'][2].update(stat='spe'),lambda s:s['uses'][2].update(base_stage_delta=-2),lambda s:s['uses'][0].update(item='item/상처약')]
  for mutate in mutations:
   self.p.spec.clear();self.p.spec.update(deepcopy(baseline));mutate(self.p.spec['herbal_restoratives']);before=self.snap()
   for action in (lambda:self.e.use_item(self.p,'힘의가루'),lambda:D.extended_rest(self.e,self.p,4),self.e.export_state):
    with self.assertRaises(ValueError):action()
    self.assertEqual(self.snap(),before)
  self.p.spec.clear();self.p.spec.update(deepcopy(baseline));state=STAGES.prepared(self.p);state['base']['herbal_restoratives']['deltas']['atk']=-2;STAGES.write(self.p,state);before=self.snap()
  with self.assertRaises(ValueError):self.e.use_item(self.p,'힘의가루')
  self.assertEqual(self.snap(),before)
 def test_malformed_saved_history_is_rejected_on_actual_durable_load(self):
  self.herb(self.p);self.p.spec['herbal_restoratives']['count']=2
  with patch.object(FOOD,'validate_herbal',return_value=None):payload=CODEC.dump_engine(self.e)
  before=self.snap()
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  self.assertEqual(self.snap(),before)

if __name__=='__main__':unittest.main()
