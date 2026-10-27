"""Common accuracy/evasion state, source qualifiers, timed totals and reset."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_condition_recovery as FIX
import combat_modifiers as M,effects as FX,state_grants as G,effect_lifetimes as L,combat_timing as T
from synthetic_rule_fixture import register_synthetic
SOURCE='test/category2-bounded-modifier'

class BoundedModifierTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  FIX.ConditionRecoveryTests.setUpClass.__func__(cls)
  register_synthetic(cls.r,SOURCE,name='bounded modifier component',kind='entity:move')
 setUp=FIX.ConditionRecoveryTests.setUp
 add=FIX.ConditionRecoveryTests.add
 restored=FIX.ConditionRecoveryTests.restored
 snap=FIX.ConditionRecoveryTests.snap
 def timed(self,c,kind,value):
  return L.install(self.e,c,c,{'type':kind,'value':value,'duration':'scene'},SOURCE,'test-timing',len(T.records(c)))
 def reset(self,c):FX.h_reset_stages(self.e,c,c,{'target':'self'},{})
 def active(self,c):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  if self.e.round_start_seconds is not None:self.e.end_round()
  self.e.start_round(self.actors);self.e.start_of_turn(c)
 def test_actual_coil_adds_accuracy_directly_without_multiplying_stats(self):
  for c in self.actors:
   self.e.gm.set_move(c,'move/똬리틀기',True,reason='observed learned source');self.active(c)
   self.e.use_move(c,c,'move/똬리틀기')
   self.assertEqual(c.accuracy_stage,1);self.assertEqual(c.stages['atk'],1);self.assertEqual(c.stages['def'],1)
   before=c.accuracy_stage;FX.h_accuracy_mod(self.e,c,c,{'value':20,'target':'self'},{});self.assertEqual(c.accuracy_stage,6)
   FX.h_accuracy_mod(self.e,c,c,{'value':-20,'target':'self'},{});self.assertEqual(c.accuracy_stage,-6)
 def test_actual_shelter_extra_evasion_applies_all_categories_and_ends_on_recall(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.a if kind=='trainer' else self.p;before=[c.evasion(k) for k in ('물리','특수','변화')]
   self.e.gm.set_move(c,'move/농성',True,reason='observed learned source');self.active(c)
   self.e.use_move(c,c,'move/농성');self.assertEqual(c.evasion_mod,2)
   raised=[max(min(6,c.stats[s]*6//5//5),min(6,c.stats['spe']//5)) for s in ('def','spd')]+[min(6,c.stats['spe']//5)]
   self.assertEqual([c.evasion(k) for k in ('물리','특수','변화')],[min(9,b+2) for b in raised])
   self.e.gm.recall(c);self.assertEqual(c.evasion_mod,0);self.assertEqual([c.evasion(k) for k in ('물리','특수','변화')],before)
 def test_combined_extra_evasion_is_bounded_before_the_total_nine_cap(self):
  for c in self.actors:
   base=[c.evasion(k) for k in ('물리','특수','변화')]
   self.e.gm.set_stage(c,'eva',value=5);self.timed(c,'evasion_mod',4)
   self.assertEqual([c.evasion(k,conditional_bonus=2) for k in ('물리','특수','변화')],[min(9,b+6) for b in base])
   self.reset(c);self.e.gm.set_stage(c,'eva',value=-5);self.timed(c,'evasion_mod',-4)
   self.assertEqual([c.evasion(k,conditional_bonus=-2) for k in ('물리','특수','변화')],[max(0,b-6) for b in base])
 def test_negative_extra_cannot_improve_attacker_accuracy_below_zero_evasion(self):
  # Separate real bodies so occupied rough terrain cannot add its independent -2.
  self.a.pos=(1,1);self.p.pos=(1,3)
  move=self.r.move('move/메가톤펀치')
  for c in self.actors:
   self.e.gm.set_stage(c,'eva',value=-6)
   self.assertEqual(c.evasion('물리'),0)
   self.assertFalse(self.e.accuracy_check(self.target,c,move,fixed_roll=move['ac']-1)[0])
   self.assertTrue(self.e.accuracy_check(self.target,c,move,fixed_roll=move['ac'])[0])
 def test_timed_accuracy_is_bounded_with_ordinary_stage_at_actual_roll(self):
  self.e.gm.add_condition(self.target,'취약',force=True,reason='zero target evasion')
  move=self.r.move('move/메가톤펀치')
  for c in self.actors:
   self.e.gm.set_stage(c,'acc',value=-5);self.timed(c,'accuracy_mod',-4)
   self.assertEqual(M.accuracy_stage(c),-6)
   self.assertTrue(self.e.accuracy_check(c,self.target,move,fixed_roll=move['ac']+6)[0])
   self.assertFalse(self.e.accuracy_check(c,self.target,move,fixed_roll=move['ac']+5)[0])
   self.reset(c);self.e.gm.set_stage(c,'acc',value=5);self.timed(c,'accuracy_mod',4);self.assertEqual(M.accuracy_stage(c),6)
 def test_stage_reset_removes_timed_stage_records_but_not_physical_roll_penalty(self):
  for c in self.actors:
   self.e.gm.set_stage(c,'acc',value=4);self.e.gm.set_stage(c,'eva',value=4)
   self.timed(c,'accuracy_mod',4);self.timed(c,'evasion_mod',4)
   physical={'source':'item/그물','manual_end':True,'accuracy_modifier':-3}
   T.install(self.e,c,physical);self.e.apply_status(c,'실명')
   self.reset(c)
   self.assertEqual((c.accuracy_stage,c.evasion_mod,M.accuracy_stage(c)),(0,0,0))
   self.assertEqual(T.accuracy_modifier(c,include_effect_contract=False),-3);self.assertIn('실명',c.conditions)
   self.assertEqual(len(T.records(c)),1)
 def test_stage_reset_keeps_owned_always_active_passive_and_removal_cleans_it(self):
  for c in self.actors:
   self.e.gm.set_ability(c,'복안',True,reason='actual static accuracy')
   self.e.gm.set_ability(c,'본능',True,reason='actual static evasion')
   self.assertEqual((c.accuracy_stage,c.evasion_mod),(3,2))
   FX.h_accuracy_mod(self.e,c,c,{'value':-5,'target':'self'},{});FX.h_evasion_mod(self.e,c,c,{'value':4,'target':'self'},{});self.reset(c)
   self.assertEqual((c.accuracy_stage,c.evasion_mod),(3,2))
   self.e.gm.set_ability(c,'복안',False,reason='source removed');self.e.gm.set_ability(c,'본능',False,reason='source removed')
   self.assertEqual((c.accuracy_stage,c.evasion_mod),(0,0))
 def test_scoped_passives_preserve_qualifiers_without_false_self_stage_grant(self):
  qualifiers=({'moves':['몸통박치기'],'on_activation':True},{'target':'target'},{'target':'enemies within 3m'},{'if_weather_hail':2},{'if':'familiar terrain'},{'vs':'status moves'},{'duration':'1라운드'},{'until':'encounter_end'})
  for c in self.actors:
   for i,q in enumerate(qualifiers):
    for kind in ('accuracy_mod','evasion_mod'):
     effect={'type':kind,'value':2,**q};before=(c.accuracy_stage,c.evasion_mod)
     self.assertIsNone(M.passive_field(effect));self.assertEqual(G._declared([effect]),({},{}))
     source=f'test-scoped:{i}:{kind}'
     G.apply_owned(self.e,c,source,lambda:FX.apply_passives(self.e,c,[effect]),effects=[effect])
     self.assertEqual((c.accuracy_stage,c.evasion_mod),before);self.assertTrue(any(all(x.get(k)==v for k,v in effect.items()) for x in c.modifiers))
     G.remove_owned(self.e,c,source)
 def test_actual_activation_only_ability_holds_without_granting_global_accuracy(self):
  for c in self.actors:
   before=self.snap()
   with self.assertRaisesRegex(ValueError,'unresolved source input'):
    self.e.gm.set_ability(c,'등껍질로켓포',True,reason='native source with activation requirement')
   self.assertEqual(c.accuracy_stage,0);self.assertEqual(self.snap(),before)
 def test_gm_and_durable_restore_replay_bounded_read_and_reset_for_both_kinds(self):
  for c in self.actors:
   self.e.gm.set_stage(c,'acc',value=5);self.e.gm.set_stage(c,'eva',value=5);self.timed(c,'accuracy_mod',3);self.timed(c,'evasion_mod',3)
  expected={c.entity_id:[c.evasion(k) for k in ('물리','특수','변화')] for c in self.actors}
  self.e.gm.snapshot('bounded');loaded=self.restored()
  for original in self.actors:
   c=next(x for x in loaded.gm.everyone if x.entity_id==original.entity_id)
   self.assertEqual(M.accuracy_stage(c),6);self.assertEqual([c.evasion(k) for k in ('물리','특수','변화')],expected[c.entity_id])
   FX.h_reset_stages(loaded,c,c,{'target':'self'},{});self.assertEqual(M.accuracy_stage(c),0);self.assertFalse(T.records(c))
   self.reset(original)
  self.e.gm.restore('bounded')
  for c in self.actors:self.assertEqual(M.accuracy_stage(c),6);self.reset(c);self.assertEqual(M.accuracy_stage(c),0)
 def test_unrelated_timed_damage_reduction_survives_stage_reset(self):
  self.timed(self.a,'damage_reduction',4);self.timed(self.a,'evasion_mod',4);self.reset(self.a)
  self.assertEqual(L.numeric(self.a,'damage_reduction'),4);self.assertEqual(L.numeric(self.a,'evasion_modifier'),0)

 def test_actual_sweet_scent_reduces_shared_extra_evasion_on_both_kinds(self):
  for kind in ('trainer','pokemon'):
   self.setUp();c=self.a if kind=='trainer' else self.p;c.pos=(1,1);self.target.pos=(2,1)
   self.target.side='foe';c.side='party'
   self.e.gm.set_stage(c,'eva',value=5);before=[c.evasion(k) for k in ('물리','특수','변화')]
   self.e.gm.set_move(self.target,'move/달콤한향기',True,reason='observed source move')
   self.e.start_round([self.target,c]);self.e.start_of_turn(self.target);self.e.rng.seed(6)
   self.e.use_move(self.target,c,'move/달콤한향기');self.assertEqual(c.evasion_mod,3)
   self.assertEqual(self.target.move_uses['move/달콤한향기'],1)
   self.assertEqual([c.evasion(k) for k in ('물리','특수','변화')],[v-2 for v in before])
 def test_blindness_roll_penalty_stays_separate_beyond_the_stage_lower_bound(self):
  self.e.gm.add_condition(self.target,'취약',force=True,reason='zero evasion')
  move=self.r.move('move/메가톤펀치')
  for c in self.actors:
   self.e.gm.set_stage(c,'acc',value=-6);self.e.apply_status(c,'실명')
   self.assertEqual(M.accuracy_stage(c),-6)
   self.assertTrue(self.e.accuracy_check(c,self.target,move,fixed_roll=move['ac']+12)[0])
   self.assertFalse(self.e.accuracy_check(c,self.target,move,fixed_roll=move['ac']+11)[0])

if __name__=='__main__':unittest.main()
