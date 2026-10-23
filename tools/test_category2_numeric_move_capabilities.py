"""Source-specific numeric learning on actual movement, jump, load and saves."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon,species_lookup
from grid import Grid
import move_capabilities as CAP,state_grants as G,movement_actions as M,jump_actions as J,capability_actions as P,state_codec as CODEC

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_progression_state.ProgressionStateTests.setUp
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 pokemon=_fixture_test_category2_progression_state.ProgressionStateTests.pokemon
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def base(self,c):
  c.spec['power_basis']='base'
  self.e.gm.set_movement_capabilities(c,{'land':6,'power':4,'high_jump':2,'long_jump':3},basis='base',reason='actual pre-learning base capabilities')
 def choose(self,c,choice='move_entry'):
  return self.e.gm.choose_learned_capability_policy(c,'move/공중날기',choice,reason='GM resolves contradictory original source entries')
 def learn(self,c,name):self.e.gm.set_move(c,'move/'+name,reason='observed actual learning')
 def forget(self,c,name):self.e.gm.set_move(c,'move/'+name,add=False,reason='observed actual forgetting')
 def test_all_eight_sources_both_actor_kinds_and_reversible_numeric_consumers(self):
  expected={'달려들기':{'land':1,'long_jump':1},'뛰어오르기':{'high_jump':1},'튀어오르기':{'long_jump':1},'괴력':{'power':1},'구멍파기':{'burrow':3},'공중날기':{'sky':3},'다이빙':{'swim':3},'순간이동':{'teleport':4}}
  for c in (self.a,self.pokemon()):
   self.base(c);self.choose(c);baseline=M.capabilities(self.e,c)
   for name,bonuses in expected.items():
    with self.subTest(kind=c.kind,move=name):
     self.learn(c,name)
     for field,value in bonuses.items():
      actual=P.power(c) if field=='power' else J.limits(c)[field] if field.endswith('jump') else M.capabilities(self.e,c)[field]
      self.assertEqual(actual,baseline.get(field,0)+value)
     self.forget(c,name);self.assertEqual(M.capabilities(self.e,c),baseline);self.assertEqual(P.power(c),4)
 def test_fly_source_choice_is_required_atomic_and_both_alternatives_are_retained(self):
  c=self.pokemon();self.base(c);self.learn(c,'공중날기');before=deepcopy(c.spec)
  with self.assertRaisesRegex(ValueError,'source choice'):M.capabilities(self.e,c)
  with self.assertRaises(ValueError):self.choose(c,'invented')
  self.assertEqual(c.spec,before)
  self.choose(c);self.assertEqual(M.capabilities(self.e,c)['sky'],3)
  self.choose(c,'capability_entry');self.assertEqual(M.capabilities(self.e,c)['sky'],4)
  self.e.gm.set_movement_capabilities(c,{'land':6,'sky':2},basis='base',reason='preexisting species flight')
  self.assertEqual(M.capabilities(self.e,c)['sky'],6)
  self.forget(c,'공중날기');self.assertEqual(M.capabilities(self.e,c)['sky'],2)
 def test_permissions_overlays_duplicate_sources_and_independent_base(self):
  c=self.pokemon();self.base(c)
  G.grant_moves(c,['move/괴력'],'permission','temporary',mode='permission');self.assertEqual(P.power(c),4)
  for sid in ('one','two'):G.grant_moves(c,['move/괴력'],sid,'feature',lifetime='while_owned')
  self.assertEqual(P.power(c),5);G.overlay(c,'display',moves=[]);self.assertEqual(P.power(c),5)
  G.revoke(c,'one');self.assertEqual(P.power(c),5);G.revoke(c,'two');self.assertEqual(P.power(c),4)
 def test_native_jump_uses_only_learned_splash_not_its_active_temporary_bonus(self):
  c=self.pokemon();self.base(c);self.e.grid=Grid(20,10);c.pos=(1,1)
  self.e.start_round([c]);self.e.start_of_turn(c);before=self.e.rng.getstate()
  args=dict(jump_id='learned',difficult=False,clear_path=True,reason_text='actual clear jump path')
  with self.assertRaises(ValueError):self.e.jump(c,(5,1),**args)
  self.learn(c,'튀어오르기');out=self.e.jump(c,(5,1),**args)
  self.assertEqual(out['effective_limits'],{'high_jump':2,'long_jump':4})
  self.assertEqual(c.pos,(5,1));self.assertEqual(c.budget['shift'],0);self.assertEqual(self.e.rng.getstate(),before);self.assertFalse(c.move_uses)
 def test_native_shift_and_load_threshold_use_learned_numeric_grants(self):
  c=self.pokemon();self.base(c);self.e.grid=Grid(30,10);c.pos=(1,1);self.a.pos=(25,1)
  self.learn(c,'달려들기');self.e.start_round([c]);self.e.start_of_turn(c)
  self.e.approach(c,self.a,movement_mode='land');self.assertEqual(c.pos[0],8);self.assertLessEqual(abs(c.pos[1]-1),7);self.assertEqual(c.budget['shift'],0)
  old=P.limits(c);self.learn(c,'괴력');new=P.limits(c);self.assertGreater(new['heavy'][0],old['heavy'][0])
  weight=(old['heavy'][0]+new['heavy'][0])/2
  self.e.gm.set_carried_objects(c,[{'id':'crate','weight_kg':weight}],'GM weighed actual crate')
  self.assertEqual(P.load(c)['band'],'normal');self.forget(c,'괴력');self.assertNotEqual(P.load(c)['band'],'normal')
 def test_current_observed_totals_are_not_added_twice_and_derived_trainer_gains(self):
  c=self.a;before_power=P.power(c);before_jump=J.limits(c);before=M.capabilities(self.e,c)
  self.learn(c,'괴력');self.learn(c,'튀어오르기');self.learn(c,'달려들기')
  self.assertEqual(P.power(c),before_power+1);self.assertEqual(J.limits(c)['long_jump'],before_jump['long_jump']+2)
  self.assertEqual(M.capabilities(self.e,c)['land'],before['land']+1)
  c=self.pokemon();self.choose(c);self.learn(c,'공중날기');self.learn(c,'괴력');c.spec['power_basis']='current'
  self.e.gm.set_movement_capabilities(c,{'land':6,'sky':7,'power':8},basis='current',reason='observed totals include currently known Moves')
  self.assertEqual(M.capabilities(self.e,c)['sky'],7);self.assertEqual(P.power(c),8)
 def test_trainer_learns_an_absent_or_zero_movement_mode_and_uses_actual_flight(self):
  for present in (False,True):
   for choice,amount in (('move_entry',3),('capability_entry',4)):
    with self.subTest(present=present,choice=choice):
     self.setUp();c=self.a;self.e.grid=Grid(12,12);c.pos=(1,1)
     if present:
      self.e.gm.set_movement_capabilities(c,{'land':6,'sky':0},basis='base',reason='observed zero flight before acquisition')
     self.assertEqual(M.capabilities(self.e,c).get('sky',0),0)
     self.e.start_round([c]);self.e.start_of_turn(c)
     before=deepcopy((c.spec,c.pos,c.budget,self.e.rng.getstate()))
     with self.assertRaisesRegex(ValueError,'not possessed'):
      self.e.aerial_move(c,(2,1),mode='sky',altitude=1,reason_text='actual attempted flight without its capability')
     self.assertEqual((c.spec,c.pos,c.budget,self.e.rng.getstate()),before)
     self.choose(c,choice);self.learn(c,'공중날기')
     self.assertEqual(M.capabilities(self.e,c)['sky'],amount)
     rng=self.e.rng.getstate();out=self.e.aerial_move(c,(2,1),mode='sky',altitude=1,gm_distance=2,reason_text='actual newly acquired trainer flight with measured mixed distance')
     self.assertEqual((out['mode'],c.pos,c.airborne,c.budget['shift'],c.budget['standard']),('sky',(2,1),True,0,1))
     self.assertEqual(self.e.rng.getstate(),rng);self.assertFalse(c.move_uses)
     self.assertTrue(self.e.validate_state()['valid'])
 def test_new_trainer_movement_permission_learning_withdrawal_and_both_restore_paths(self):
  c=self.a;self.e.grid=Grid(12,12);c.pos=(1,1);self.choose(c)
  G.grant_moves(c,['move/공중날기'],'temporary-use','temporary',mode='permission')
  self.assertNotIn('sky',M.capabilities(self.e,c));G.revoke(c,'temporary-use')
  self.learn(c,'공중날기');self.e.start_round([c]);self.e.start_of_turn(c)
  snapshot=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(snapshot)
  for e in (self.e,loaded):
   q=next(a for a in e.gm.everyone if a.entity_id==c.entity_id)
   self.assertEqual(M.capabilities(e,q)['sky'],3)
   e.gm.set_move(q,'move/공중날기',add=False,reason='actual withdrawal of the learned movement source')
   self.assertNotIn('sky',M.capabilities(e,q));before=deepcopy((q.spec,q.pos,q.budget,e.rng.getstate()))
   with self.assertRaisesRegex(ValueError,'not possessed'):
    e.aerial_move(q,(2,1),mode='sky',altitude=1,reason_text='withdrawn flight cannot authorize movement')
   self.assertEqual((q.spec,q.pos,q.budget,e.rng.getstate()),before)
   e.gm.set_move(q,'move/공중날기',reason='actual reacquisition after restoration')
   self.assertEqual(M.capabilities(e,q)['sky'],3)
   e.aerial_move(q,(2,1),mode='sky',altitude=1,gm_distance=2,reason_text='actual flight after restored reacquisition with measured mixed distance')
   self.assertEqual((q.pos,q.budget['shift'],q.budget['standard']),((2,1),0,1));self.assertFalse(q.move_uses)
   self.assertTrue(e.validate_state()['valid'])
 def test_choices_and_learned_state_survive_both_restore_paths_and_corruption_rejects(self):
  c=self.pokemon();self.base(c);self.choose(c);self.learn(c,'공중날기');self.learn(c,'괴력');uid=c.entity_id
  self.e.gm.snapshot('numeric');self.choose(c,'capability_entry');self.e.gm.restore('numeric')
  restored=self.restored();c=next(a for a in restored.gm.everyone if a.entity_id==uid)
  self.assertEqual(M.capabilities(restored,c)['sky'],3);self.assertEqual(P.power(c),5)
  restored.gm.set_move(c,'move/공중날기',add=False,reason='actual forgetting after restore');self.assertNotIn('sky',M.capabilities(restored,c))
  c.spec[CAP.CHOICES_KEY]['move/공중날기']['authority']='fabricated'
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(restored)

 def test_fresh_species_bases_apply_initial_known_moves_and_forget_without_skill_derivation(self):
  source=species_lookup(self.r,'잉어킹');base=self.pokemon(20)
  self.assertEqual(base.spec['movement'],source['movement'])
  self.assertEqual(G.effective_capabilities(base),source['capabilities'])
  baseline=M.capabilities(self.e,base);power=P.power(base);jumps=J.limits(base)
  expected={'달려들기':{'land':1,'long_jump':1},'뛰어오르기':{'high_jump':1},'튀어오르기':{'long_jump':1},'괴력':{'power':1},'구멍파기':{'burrow':3},'공중날기':{'sky':3},'다이빙':{'swim':3},'순간이동':{'teleport':4}}
  for name,bonuses in expected.items():
   with self.subTest(move=name):
    c=self.add(build_pokemon(self.r,'잉어킹',20,moves=['move/'+name],abilities=[],extra={'trainer_id':self.a.entity_id}))
    if name=='공중날기':self.choose(c)
    raw=deepcopy(c.spec['movement'])
    for skill in ('육상','곡예','생존'):c.spec['skills'][skill]='8d6'
    for field,amount in bonuses.items():
     actual=P.power(c) if field=='power' else J.limits(c)[field] if field.endswith('jump') else M.capabilities(self.e,c)[field]
     original=power if field=='power' else jumps[field] if field.endswith('jump') else baseline.get(field,0)
     self.assertEqual(actual,original+amount)
    self.forget(c,name)
    self.assertEqual(M.capabilities(self.e,c),baseline);self.assertEqual(P.power(c),power)
    self.assertEqual(c.spec['movement'],raw);self.assertFalse(c.move_uses)

 def test_fresh_and_explicit_current_species_values_survive_restore_without_double_addition(self):
  fresh=self.add(build_pokemon(self.r,'잉어킹',20,moves=['move/괴력','move/튀어오르기'],abilities=[],extra={'trainer_id':self.a.entity_id}))
  current=self.add(build_pokemon(self.r,'잉어킹',20,moves=['move/괴력','move/튀어오르기'],abilities=[],extra={'trainer_id':self.a.entity_id,'movement':{'land':7,'power':6,'high_jump':3,'long_jump':5}}))
  self.assertEqual((P.power(fresh),J.limits(fresh)['long_jump']),(2,4))
  self.assertEqual((P.power(current),J.limits(current)['long_jump']),(6,5))
  self.e.gm.snapshot('species-bases');self.forget(fresh,'괴력');self.e.gm.restore('species-bases')
  restored=self.restored()
  for original,expected in ((fresh,(1,3)),(current,(5,4))):
   c=next(a for a in restored.gm.everyone if a.entity_id==original.entity_id)
   for name in ('괴력','튀어오르기'):restored.gm.set_move(c,'move/'+name,add=False,reason='actual forgetting after both restores')
   self.assertEqual((P.power(c),J.limits(c)['long_jump']),expected)

if __name__=='__main__':unittest.main()
