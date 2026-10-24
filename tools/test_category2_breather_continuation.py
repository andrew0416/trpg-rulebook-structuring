"""Continue the actual paid route and observed roll, never a fresh Breather."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import unittest
from engine import Rules
import test_category2_breather as VOLUNTARY
import test_category2_breather_assistance as ASSISTED
import action_lifecycle as ACTION,action_resources as RESOURCES
import breather as B,condition_recovery as RECOVERY,effects_ext as EXT
import movement_actions as MOVEMENT,state_codec as CODEC,stamina as STAMINA
import state_grants as G,temporary_hp as TEMP
import effects as FX

ROOT=Path(__file__).resolve().parents[1]

class BreatherContinuationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def ordinary(self):
  VOLUNTARY.BreatherTests.setUp(self)
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].append(STAMINA.SOURCE))
  TEMP.grant(self.e,self.a,12)
  return self.a,VOLUNTARY.BreatherTests.options(self)
 def assisted(self):
  ASSISTED.AssistedBreatherTests.setUp(self)
  G.transition(self.e,self.t,lambda e,c:c.spec['edges'].append(STAMINA.SOURCE))
  return self.t,ASSISTED.AssistedBreatherTests.options(self)
 def blocked(self,actor,options,who,cell):
  original=MOVEMENT.departure
  def changed(e,c,q,altitude,**options):
   permitted=original(e,c,q,altitude,**options)
   if c is who and q==cell:e.grid.blocking.add(q)
   return permitted
  with patch.object(MOVEMENT,'departure',side_effect=changed):
   with self.assertRaisesRegex(ValueError,'path interrupted'):self.e.take_breather(actor,**options)
 def test_actual_ordinary_prefix_resumes_without_full_save_or_previous_cells(self):
  actor,options=self.ordinary();self.blocked(actor,options,actor,(4,2))
  self.assertEqual(actor.pos,(3,2));self.assertEqual(actor.temp_hp,12)
  rng=self.e.rng.getstate();self.e.grid.blocking.remove((4,2));entered=[]
  original=EXT.on_enter_cell
  with patch.object(RECOVERY,'saving_check',side_effect=AssertionError('cannot reroll')),patch.object(EXT,'on_enter_cell',side_effect=lambda e,c,p,**kw:(entered.append(p),original(e,c,p,**kw))[-1]):
   result=self.e.take_breather(actor,**options)
  self.assertTrue(result['completed']);self.assertEqual(entered,[(4,2),(5,2),(6,2)])
  self.assertEqual((result['movement']['distance'],result['movement']['steps']),(4,4))
  self.assertEqual((actor.temp_hp,actor.budget['standard'],actor.budget['shift']),(5,0,0))
  self.assertEqual(self.e.rng.getstate(),rng)
  self.assertEqual(len([x for x in actor._action_history if x=='full']),1)
  self.assertEqual(len([x for x in self.e._native_action_resolutions.values() if x['kind']=='breather']),1)
 def test_assisted_finished_target_and_partial_helper_continue_only_remaining_helper(self):
  actor,options=self.assisted();self.blocked(actor,options,self.h,(4,2))
  self.assertEqual((self.t.pos,self.h.pos),((7,2),(3,2)))
  self.assertIn('난동',self.t.conditions);self.assertNotIn('넘어짐',self.t.conditions)
  self.e.grid.blocking.remove((4,2));entered=[];original=EXT.on_enter_cell
  with patch.object(self.e,'skill_check',side_effect=AssertionError('cannot repeat Command')),patch.object(EXT,'on_enter_cell',side_effect=lambda e,c,p,**kw:(entered.append((c.entity_id,p)),original(e,c,p,**kw))[-1]):
   result=self.e.take_breather(actor,**options)
  self.assertTrue(result['completed'])
  self.assertEqual(entered,[(self.h.entity_id,p) for p in [(4,2),(5,2),(6,2)]])
  self.assertEqual((self.t.temp_hp,self.t.pos,self.h.pos),(5,(7,2),(6,2)))
  self.assertEqual(RESOURCES.pending(self.t),{'standard':1,'shift':1})
  self.assertEqual((self.h.budget['standard'],self.h.budget['shift']),(0,0))
 def test_actual_assisting_approach_prefix_also_resumes_once(self):
  actor,options=self.assisted();self.h.pos=(0,2)
  G.transition(self.e,self.h,lambda e,c:setattr(c,'movement',6))
  options['assistance']['approach_path']=[(0,2),(1,2),(2,2)]
  self.blocked(actor,options,self.h,(2,2));self.assertEqual(self.h.pos,(1,2))
  self.e.grid.blocking.remove((2,2))
  with patch.object(self.e,'skill_check',side_effect=AssertionError('cannot repeat Command')):
   self.assertTrue(self.e.take_breather(actor,**options)['completed'])
  self.assertEqual((self.t.pos,self.h.pos),((7,2),(6,2)))
 def test_saved_ordinary_and_assisted_prefixes_keep_real_actor_references_and_costs(self):
  for assisted in (False,True):
   with self.subTest(assisted=assisted):
    actor,options=self.assisted() if assisted else self.ordinary()
    self.blocked(actor,options,actor,(5,2) if assisted else (4,2))
    restored=CODEC.load_engine(self.r,CODEC.dump_engine(self.e))
    index={c.entity_id:c for c in restored.everyone};current=index[actor.entity_id]
    if assisted:options=dict(options,helper=index[self.h.entity_id])
    restored.grid.blocking.remove((5,2) if assisted else (4,2))
    with patch.object(RECOVERY,'saving_check',side_effect=AssertionError('cannot reroll save')),patch.object(restored,'skill_check',side_effect=AssertionError('cannot reroll Command')):
     result=restored.take_breather(current,**options)
    self.assertTrue(result['completed']);self.assertEqual(current.temp_hp,5)
    self.assertEqual(restored.take_breather(current,**options),result)
 def test_changed_declaration_foreign_continuation_and_displaced_prefix_cannot_bypass(self):
  actor,options=self.ordinary();self.blocked(actor,options,actor,(4,2));before=CODEC.dump_engine(self.e)
  changed=deepcopy(options);changed['fixed_save']=1
  with self.assertRaisesRegex(ValueError,'declaration'):self.e.take_breather(actor,**changed)
  with self.assertRaisesRegex(ValueError,'actual interrupted'):
   with ACTION.resolution(self.e,actor,B.SOURCE,kind='breather',_breather_attempt={}):pass
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.grid.blocking.remove((4,2));actor.pos=(3,3)
  with self.assertRaisesRegex(ValueError,'prefix'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.temp_hp,12)
 def test_entry_hook_exception_is_not_silently_replayed_or_skipped(self):
  actor,options=self.ordinary()
  with patch.object(EXT,'on_enter_cell',side_effect=RuntimeError('actual entry hook')):
   with self.assertRaisesRegex(RuntimeError,'entry hook'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.pos,(3,2));self.assertEqual(actor.temp_hp,12)
  with self.assertRaisesRegex(ValueError,'effects interrupted'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.temp_hp,12)
  with self.assertRaisesRegex(ValueError,'unfinished'):self.e.end_of_turn(actor)
 def test_atomic_recovery_error_preserves_route_but_does_not_partially_cure_or_reaward(self):
  actor,options=self.ordinary();self.e.apply_status(actor,'혼란')
  with patch.object(B,'_disadvantage',side_effect=RuntimeError('actual recovery hook')):
   with self.assertRaisesRegex(RuntimeError,'recovery hook'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.pos,(6,2));self.assertIn('혼란',actor.conditions);self.assertEqual(actor.temp_hp,12)
  with patch.object(RECOVERY,'saving_check',side_effect=AssertionError('cannot repeat save')):
   result=self.e.take_breather(actor,**options)
  self.assertTrue(result['completed']);self.assertNotIn('혼란',actor.conditions);self.assertEqual(actor.temp_hp,5)
 def test_actual_owner_turn_is_required_for_continuation(self):
  actor,options=self.ordinary();self.blocked(actor,options,actor,(4,2))
  self.e._active_turn_actor=self.b
  with self.assertRaisesRegex(ValueError,'same producer and owner turn'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.temp_hp,12)
 def test_actual_opportunity_attack_is_not_repeated_when_paid_route_continues(self):
  actor,options=self.ordinary();self.b.aoo_used=False
  with patch.object(self.e,'use_move',wraps=self.e.use_move) as attack:
   self.blocked(actor,options,actor,(4,2));self.assertEqual(attack.call_count,1)
   self.e.grid.blocking.remove((4,2))
   self.assertTrue(self.e.take_breather(actor,**options)['completed'])
   self.assertEqual(attack.call_count,1)
  self.assertTrue(self.b.aoo_used);self.assertEqual(actor.temp_hp,5)
 def test_diagonal_prefix_preserves_actual_parity_and_total_distance_on_resume(self):
  actor,options=self.ordinary()
  options['path']=[(2,2),(3,3),(4,4),(5,4)]
  self.blocked(actor,options,actor,(4,4));self.assertEqual(actor._diagonal_steps,1)
  self.e.grid.blocking.remove((4,4));result=self.e.take_breather(actor,**options)
  self.assertTrue(result['completed']);self.assertEqual(result['movement']['distance'],4)
  self.assertEqual(actor._diagonal_steps,2)
 def test_actual_unresolved_entry_receipt_stops_before_later_cells_and_recovery(self):
  actor,options=self.ordinary();self.e.apply_status(actor,'혼란')
  original=EXT.on_enter_cell
  def entry(e,c,p,**kw):
   original(e,c,p,**kw)
   FX.run_effects(e,c,c,[{'type':'unreviewed_actual_entry_effect'}],{'hit':True},'hazard/observed')
  with patch.object(EXT,'on_enter_cell',side_effect=entry):
   with self.assertRaisesRegex(ValueError,'path interrupted'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.pos,(3,2));self.assertEqual(actor.temp_hp,12);self.assertIn('혼란',actor.conditions)
  with self.assertRaisesRegex(ValueError,'actual receipts'):self.e.take_breather(actor,**options)
  self.assertEqual(actor.pos,(3,2));self.assertEqual(actor.temp_hp,12)
 def test_actual_opportunity_stamina_choice_finishes_before_paid_movement_continues(self):
  from random import Random
  actor,options=self.ordinary();self.b.aoo_used=False;actor.spec['skills']['전투']=6
  seed=next(n for n in range(1000) if Random(n).randint(1,20)==20)
  self.e.rng.seed(seed)
  with patch.object(self.e,'use_move',wraps=self.e.use_move) as attack:
   with self.assertRaisesRegex(ValueError,'post-action Stamina'):self.e.take_breather(actor,**options)
   self.assertEqual(attack.call_count,1);self.assertEqual(actor.pos,(2,2))
   self.assertEqual(actor.temp_hp,0)
   row=next(x for x in self.e._native_action_resolutions.values() if x['kind']=='move')
   self.e.resolve_stamina(actor,row['id'],skill='육상');self.assertEqual(actor.temp_hp,5)
   result=self.e.take_breather(actor,**options)
   self.assertTrue(result['completed']);self.assertEqual(attack.call_count,1)
  self.assertEqual(actor.pos,(6,2));self.assertEqual(actor.temp_hp,0)
  row=next(x for x in self.e._native_action_resolutions.values() if x['kind']=='breather')
  self.e.resolve_stamina(actor,row['id'],skill='전투');self.assertEqual(actor.temp_hp,6)

if __name__=='__main__':unittest.main()
