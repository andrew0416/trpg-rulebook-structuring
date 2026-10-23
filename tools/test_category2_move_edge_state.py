"""Accuracy Training: native attacks, selection lifetime and source isolation."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon,build_trainer
import pokemon_move_edges as E,pokemon_capability_edges as CAP,pokemon_party as PARTY,state_fields as F

class MoveEdgeStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'근육몬',20,moves=['메가톤펀치'],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':8}))
  self.e.gm.observe_loyalty(self.p,3,reason='GM established current trainer relationship')
  self.t=self.add(build_pokemon(self.r,'잉어킹',20,moves=[],abilities=[]));self.t.side='wild';self.t.pos=(1,0)
  F.base_patch(self.t,{'stats':dict.fromkeys(F.STATS,1)},reason='explicit zero stat evasion observation')
 def teach(self,move='메가톤펀치',**kw):return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=E.ACCURACY,move_id=move,**kw,safe=True)
 def test_selected_move_base_ac_changes_without_dice_bonus_or_global_mutation(self):
  m=self.r.move('move/메가톤펀치');original=deepcopy(m)
  self.assertFalse(self.e.accuracy_check(self.p,self.t,m,fixed_roll=3)[0]);self.teach()
  self.assertTrue(self.e.accuracy_check(self.p,self.t,m,fixed_roll=3)[0]);self.assertEqual(m,original)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds,self.p.accuracy_stage),(7,3600,0))
  self.assertFalse(self.e.accuracy_check(self.t,self.p,m,fixed_roll=3,waive=True)[0])
  prepared=E.prepare(self.e,self.p,m);self.assertEqual(E.prepare(self.e,self.p,prepared)['ac'],3)
  self.assertEqual(E.prepare(self.e,self.t,prepared)['ac'],4)
 def test_three_distinct_moves_and_all_rejections_are_atomic(self):
  for mid in ('메가톤펀치','폭발펀치','암석봉인'):self.teach(mid)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(5,10800))
  for mid in ('move/메가톤펀치','돌떨구기','몸통박치기','unknown'):
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(mid)
   self.assertEqual(self.snap(),before)
 def test_no_invented_learning_permission_or_learning_prerequisite(self):
  self.teach('암석봉인');self.assertNotIn('move/암석봉인',self.p.moves)
  self.e.gm.set_move(self.p,'move/암석봉인',True,reason='actual subsequent learning')
  self.assertEqual(E.prepare(self.e,self.p,self.r.move('move/암석봉인'))['ac'],4)
  self.e.gm.set_move(self.p,'move/암석봉인',False,reason='actual forgetting');self.assertEqual(self.p.spec['tutor_points'],7)
  self.e.gm.set_move(self.p,'move/암석봉인',True,reason='actual relearning');self.assertEqual(E.prepare(self.e,self.p,self.r.move('move/암석봉인'))['ac'],4)
 def test_actual_single_target_attack_hits_lower_threshold_and_spends_real_resources(self):
  self.teach();self.e.start_round([self.p,self.t]);self.e.start_of_turn(self.p);before=self.t.hp
  with patch.object(E.COMPOSITION,'derive',wraps=E.COMPOSITION.derive) as shared:
   with patch.object(self.e.rng,'randint',return_value=3):self.e.use_move(self.p,self.t,'move/메가톤펀치',set_damage=True)
  self.assertTrue(any(any(row['source']==E.ACCURACY for row in call.args[1]) for call in shared.call_args_list))
  self.assertLess(self.t.hp,before);self.assertEqual(self.p.budget['standard'],0)
  self.assertTrue(any('AC 3+' in line for line in self.e.log_lines))
 def test_actual_target_dispatch_reuses_one_overlay(self):
  self.teach();self.e.start_round([self.p,self.t]);self.e.start_of_turn(self.p);before=self.t.hp
  with patch.object(self.e.rng,'randint',return_value=3):self.e.use_move_on(self.p,self.t,'move/메가톤펀치',[self.p,self.t])
  self.assertLess(self.t.hp,before);self.assertTrue(any('AC 3+' in line for line in self.e.log_lines))
  self.assertFalse(any('AC 2+' in line for line in self.e.log_lines))
 def test_natural_boundaries_and_independent_accuracy_evasion_remain_separate(self):
  self.teach();m=self.r.move('move/메가톤펀치')
  self.assertFalse(self.e.accuracy_check(self.p,self.t,m,fixed_roll=1,situational=100)[0])
  self.assertTrue(self.e.accuracy_check(self.p,self.t,m,fixed_roll=20,situational=-100)[0])
  self.t.evasion_mod=2
  self.assertFalse(self.e.accuracy_check(self.p,self.t,m,fixed_roll=4)[0])
  self.assertTrue(self.e.accuracy_check(self.p,self.t,m,fixed_roll=4,situational=1)[0])
 def test_component_conditional_ac_replacement_is_separate_from_permanent_base_change(self):
  # This isolates precedence only. Actual Thunder conditional admission still
  # has an independent pre-existing unresolved predicate, recorded in evidence.
  import effects_ext as EXT
  self.teach();move=self.r.move('move/메가톤펀치')
  with patch.object(EXT,'accuracy_hook',return_value=(11,False,0,False)):
   self.assertFalse(self.e.accuracy_check(self.p,self.t,move,fixed_roll=10)[0])
   self.assertTrue(self.e.accuracy_check(self.p,self.t,move,fixed_roll=11)[0])
  with patch.object(EXT,'accuracy_hook',return_value=(11,False,0,True)):
   self.assertTrue(self.e.accuracy_check(self.p,self.t,move,fixed_roll=1)[0])
 def test_actual_evolution_preserves_actor_specific_move_overlay(self):
  import downtime as D
  self.teach();self.e.gm.set_level(self.p,35,reason='actual later level')
  self.assertTrue(D.evolve_combatant(self.e,self.p,'괴력몬')['evolved'])
  self.assertEqual((self.p.spec['tutor_points'],E.prepare(self.e,self.p,self.r.move('move/메가톤펀치'))['ac']),(7,3))
 def test_losing_prerequisite_refunds_only_each_actual_investment_once(self):
  self.teach();self.teach('번개');self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=CAP.TRAINING,capability='power',safe=True)
  self.e.gm.set_level(self.p,19,reason='actual minimum prerequisite ended')
  self.assertEqual(self.p.spec['tutor_points'],8);self.assertEqual(E.prepare(self.e,self.p,self.r.move('move/메가톤펀치'))['ac'],4)
  self.e.gm.set_level(self.p,18,reason='further level correction');self.assertEqual(self.p.spec['tutor_points'],8)
  self.e.gm.set_level(self.p,20,reason='eligibility regained');self.teach();self.assertEqual(self.p.spec['tutor_points'],7)
 def test_low_level_missing_points_and_unknown_refund_balance_are_atomic(self):
  self.e.gm.set_level(self.p,19,reason='actual low level');before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(before,self.snap());self.e.gm.set_level(self.p,20,reason='actual eligible level')
  self.p.spec['tutor_points']=0;before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(before,self.snap());self.p.spec['tutor_points']=8;self.teach();self.p.spec.pop('tutor_points');before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.set_level(self.p,19,reason='cannot invent current balance')
  self.assertEqual(before,self.snap())
 def test_transfer_and_both_restore_paths_keep_selection_payment_and_effect(self):
  self.teach();other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(F.STATS,10)))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='actual party',roster=[self.p]);PARTY.configure(self.e,other,mode='unlimited',reason='actual party',roster=[])
  PARTY.transfer(self.e,self.a,target=self.p,new_owner=other,reason='actual trade',request_id='accuracy-trade')
  original=deepcopy(self.p.spec);snapshot=self.e.gm.snapshot();self.e.gm.set_level(self.p,19,reason='temporary correction');self.e.gm.restore(snapshot)
  current=next(x for x in self.e.gm.everyone if x.entity_id==self.p.entity_id);self.assertEqual(current.spec,original)
  loaded=self.restored();current=next(x for x in loaded.gm.everyone if x.entity_id==self.p.entity_id);self.assertEqual(current.spec,original)
  self.assertEqual(E.prepare(loaded,current,self.r.move('move/메가톤펀치'))['ac'],3)
  loaded.gm.set_level(current,19,reason='actual later prerequisite loss');self.assertEqual(current.spec['tutor_points'],8)
 def test_groomer_can_apply_distinct_move_choices_in_actual_completed_hour(self):
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True);self.teach(from_grooming=True);self.teach('번개',from_grooming=True)
  self.assertEqual((self.e.elapsed_seconds,self.p.spec['tutor_points']),(3600,6))
 def test_invalid_saved_choice_and_boolean_refund_rejected(self):
  self.teach();row=E.records(self.p.spec)[0];row['move_id']='메가톤펀치';self.assertFalse(self.e.validate_state()['valid']);row['move_id']='move/메가톤펀치'
  self.e.gm.set_level(self.p,19,reason='actual refund');row=E.records(self.p.spec)[0];row['refund']['points']=True
  self.assertFalse(self.e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
