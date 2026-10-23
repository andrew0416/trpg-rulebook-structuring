"""Native capability investments, actual consumers and prerequisite refunds."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon,build_trainer
from grid import Grid
import pokemon_capability_edges as E,movement_actions as M,capability_actions as C,jump_actions as J
import pokemon_party as PARTY,state_fields as F,downtime as D,state_grants as G

class CapabilityEdgeStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.add(build_pokemon(self.r,'근육몬',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':12}))
  self.raw={'land':4,'sky':5,'swim':3,'burrow':2,'levitate':2,'teleport':4,'power':3,'high_jump':1,'long_jump':3}
  self.e.gm.set_movement_capabilities(self.p,self.raw,basis='base',reason='GM established actual pre-bonus capabilities')
 def teach(self,choice,source=E.TRAINING,**kw):return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=source,capability=choice,**kw,safe=True)
 def test_power_high_and_long_jump_are_three_separate_one_point_investments(self):
  for choice in ('power','high_jump','long_jump'):self.teach(choice)
  self.assertEqual((C.power(self.p),J.limits(self.p)),(4,{'high_jump':2,'long_jump':4}))
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(9,10800));self.assertEqual(self.p.spec['movement'],self.raw)
  for choice in ('Power','High Jump','Long Jump','Jump'):
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(choice)
   self.assertEqual(before,self.snap())
 def test_native_capability_reader_uses_common_composition_with_source_evidence(self):
  self.teach('land',E.MOBILITY);self.teach('power')
  before=self.snap()
  with patch.object(E.LIMITS.COMPOSITION,'derive',wraps=E.LIMITS.COMPOSITION.derive) as derive:
   self.assertEqual(M.capabilities(self.e,self.p)['land'],6)
   self.assertTrue(any(call.args[0]==4 and call.args[1][0]['source']==E.MOBILITY
                       for call in derive.call_args_list))
  evidence=E.projection(self.r,self.p.spec,self.raw)
  self.assertEqual((evidence['land']['base'],evidence['land']['value']),(4,6))
  self.assertEqual(evidence['land']['steps'][0]['law'],'add')
  self.assertFalse(evidence['land']['consumed'])
  self.assertEqual(self.snap(),before)
 def test_fractional_observed_jump_bases_survive_composition_and_restore(self):
  raw={**self.raw,'high_jump':0.5,'long_jump':2.25}
  self.e.gm.set_movement_capabilities(self.p,raw,basis='base',reason='actual fractional jump measurement')
  self.teach('high_jump');self.teach('long_jump')
  self.assertEqual(J.limits(self.p),{'high_jump':1.5,'long_jump':3.25})
  self.assertEqual(self.p.spec['movement'],raw)
  loaded=self.restored();c=next(x for x in loaded.gm.everyone if x.entity_id==self.p.entity_id)
  self.assertEqual(J.limits(c),{'high_jump':1.5,'long_jump':3.25})
 def test_shared_composition_failure_does_not_partially_acquire_an_edge(self):
  before=self.snap()
  with patch.object(E.LIMITS.COMPOSITION,'derive',side_effect=ValueError('shared composition failed')):
   with self.assertRaisesRegex(ValueError,'shared composition failed'):self.teach('land',E.MOBILITY)
  self.assertEqual(self.snap(),before)
 def test_each_existing_movement_mode_receives_two_once_and_no_fabricated_new_mode(self):
  for choice in ('land','sky','swim','burrow','levitate','teleport'):
   self.teach(choice,E.MOBILITY);self.assertEqual(M.capabilities(self.e,self.p)[choice],self.raw[choice]+2)
   self.assertEqual(self.e.move_profile(self.p,movement_mode=choice)[0],self.raw[choice]+2)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(6,21600));self.assertEqual(self.p.spec['movement'],self.raw)
  before=self.snap()
  with self.assertRaises(ValueError):self.teach('Overland',E.MOBILITY)
  self.assertEqual(before,self.snap())
  other=self.add(build_pokemon(self.r,'근육몬',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_edge',target=other,edge=E.MOBILITY,capability='teleport',safe=True)
 def test_native_carrying_threshold_changes_and_both_jump_directions_use_selected_bonus(self):
  objects=[{'id':'edge-load','weight_kg':23}]
  self.e.gm.set_carried_objects(self.p,objects,'observed23kg');self.assertEqual(C.load(self.p)['band'],'staggering')
  self.teach('power');self.assertEqual(C.load(self.p)['band'],'heavy')
  self.e.gm.set_carried_objects(self.p,[],'released load')
  self.teach('long_jump');self.assertEqual(J.limits(self.p)['high_jump'],1)
  self.e.grid=Grid(20,20);self.p.pos=(0,0);self.e.start_round([self.p]);self.e.start_of_turn(self.p)
  out=self.e.jump(self.p,(4,0),jump_id='edge-jump',difficult=False,clear_path=True,reason_text='ordinary observed clear jump')
  self.assertTrue(out['landed']);self.assertEqual(self.p.pos,(4,0));self.assertEqual(self.p.budget['shift'],0)
 def test_native_land_travel_consumes_increased_shift_and_does_not_change_base(self):
  self.teach('land',E.MOBILITY);self.e.grid=Grid(30,20);self.p.pos=(0,0);self.a.pos=(15,0)
  self.e.start_round([self.p]);self.e.start_of_turn(self.p);self.e.approach(self.p,self.a,1,movement_mode='land')
  self.assertEqual(self.p.pos,(6,0));self.assertEqual(self.p.budget['shift'],0);self.assertEqual(self.p.spec['movement']['land'],4)
 def test_level_prerequisite_loss_removes_only_derived_bonuses_and_refunds_once(self):
  self.teach('power');self.teach('land',E.MOBILITY);self.teach('long_jump');self.assertEqual(self.p.spec['tutor_points'],9)
  self.e.gm.set_level(self.p,19,reason='actual permanent level correction')
  self.assertEqual((C.power(self.p),J.limits(self.p)['long_jump'],self.e.move_profile(self.p,movement_mode='land')[0]),(3,3,4))
  self.assertEqual(self.p.spec['tutor_points'],12);self.assertTrue(all(r['status']=='refunded' for r in E.records(self.p.spec)))
  self.e.gm.set_level(self.p,18,reason='further level correction');self.assertEqual(self.p.spec['tutor_points'],12)
  self.e.gm.set_level(self.p,20,reason='later actual level correction');self.assertEqual(E.amounts(self.r,self.p.spec),{})
  self.teach('land',E.MOBILITY);self.assertEqual((self.p.spec['tutor_points'],M.capabilities(self.e,self.p)['land']),(11,6))
 def test_current_capability_observation_decomposes_known_contributions_without_double_add(self):
  self.teach('power');self.teach('land',E.MOBILITY);self.teach('high_jump')
  observed=M.capabilities(self.e,self.p);self.assertEqual((observed['power'],observed['land'],observed['high_jump']),(4,6,2))
  self.e.gm.set_movement_capabilities(self.p,observed,basis='current',reason='GM copied actual current totals')
  self.assertEqual(M.capabilities(self.e,self.p),observed);self.assertEqual(self.p.spec['movement'],self.raw)
  self.e.gm.set_level(self.p,19,reason='prerequisite ended');self.assertEqual(M.capabilities(self.e,self.p),self.raw)
 def test_independent_move_and_numeric_sources_survive_only_edge_refund(self):
  self.e.gm.set_move(self.p,'move/구멍파기',True,reason='actual learned Dig')
  self.teach('burrow',E.MOBILITY);self.teach('land',E.MOBILITY)
  key='gm:independent-land';G._source(self.p,key,'gm',owner_id=None,lifetime='permanent',rule_id='gm/observed-movement',tutor_points=0);G.numeric(self.p,'movement',1,key)
  self.assertEqual((M.capabilities(self.e,self.p)['burrow'],M.capabilities(self.e,self.p)['land']),(7,7))
  self.e.gm.set_level(self.p,19,reason='only Poke Edge prerequisites ended')
  self.assertEqual((M.capabilities(self.e,self.p)['burrow'],M.capabilities(self.e,self.p)['land']),(5,5));self.assertIn('move/구멍파기',self.p.moves)
  G.revoke(self.p,key,engine=self.e);self.assertEqual(M.capabilities(self.e,self.p)['land'],4)
 def test_no_points_bad_choices_low_level_and_unknown_refund_balance_are_atomic(self):
  self.e.gm.set_level(self.p,19,reason='low level');before=self.snap()
  with self.assertRaises(ValueError):self.teach('power')
  self.assertEqual(before,self.snap());self.e.gm.set_level(self.p,20,reason='eligible level')
  for choice,source in (('jump',E.TRAINING),('power',E.MOBILITY),('sky',E.TRAINING)):
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(choice,source)
   self.assertEqual(before,self.snap())
  self.teach('power');self.p.spec.pop('tutor_points');before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.set_level(self.p,19,reason='cannot invent refund balance')
  self.assertEqual(before,self.snap())
 def test_transfer_evolution_and_both_restores_retain_independent_permanent_investment(self):
  self.teach('long_jump');self.teach('land',E.MOBILITY)
  other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(F.STATS,10)))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='actual party',roster=[self.p]);PARTY.configure(self.e,other,mode='unlimited',reason='actual party',roster=[])
  PARTY.transfer(self.e,self.a,target=self.p,new_owner=other,reason='actual transfer',request_id='cap-edge-transfer')
  self.assertEqual(self.p.spec['tutor_points'],10);self.e.gm.set_level(self.p,35,reason='observed later growth')
  self.assertTrue(D.evolve_combatant(self.e,self.p,'괴력몬')['evolved'])
  self.assertEqual(J.limits(self.p)['long_jump'],self.p.spec['movement']['long_jump']+1)
  self.assertEqual(M.capabilities(self.e,self.p)['land'],self.p.movement+2)
  expected=deepcopy(self.p.spec);snapshot=self.e.gm.snapshot();self.e.gm.set_level(self.p,19,reason='temporary observation');self.e.gm.restore(snapshot)
  current=next(x for x in self.e.gm.everyone if x.entity_id==self.p.entity_id);self.assertEqual(current.spec,expected)
  loaded=self.restored();current=next(x for x in loaded.gm.everyone if x.entity_id==self.p.entity_id)
  self.assertEqual(current.spec,expected);loaded.gm.set_level(current,19,reason='actual prerequisite loss after load');self.assertEqual(current.spec['tutor_points'],12)
 def test_grooming_credit_applies_distinct_capability_investments_in_one_completed_hour(self):
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True);self.teach('power',from_grooming=True);self.teach('high_jump',from_grooming=True)
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.p.spec['tutor_points'],10)
 def test_power_above_chart_is_retained_without_inventing_lifting_limits(self):
  values={**self.raw,'power':16};self.e.gm.set_movement_capabilities(self.p,values,basis='base',reason='GM established extreme Power')
  self.teach('power');self.assertEqual(C.power(self.p),17)
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
  with self.assertRaisesRegex(ValueError,'published weight limits'):C.limits(self.p)
 def test_tampered_derived_choice_or_prerequisite_receipt_rejects_save(self):
  self.teach('power');row=E.records(self.p.spec)[0];row['effect_storage']='already included'
  self.assertFalse(self.e.validate_state()['valid']);row['effect_storage']='derived'
  self.e.gm.set_level(self.p,19,reason='actual refund');row=E.records(self.p.spec)[0];row['refund']['points']=True
  self.assertFalse(self.e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
