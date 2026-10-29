"""Battery's actual payer/holder, Scene/Swift costs and next Special Move."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,call
import sys,re,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_gem_effects as _fixture_test_category2_gem_effects
import event_effects as N,effect_instances as E,manual_effects as A
import state_grants as G,state_codec as CODEC,move_state as M

class ManualEffectTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_gem_effects.GemEffectTests.setUpClass.__func__)
 add=_fixture_test_category2_gem_effects.GemEffectTests.add
 restored=_fixture_test_category2_gem_effects.GemEffectTests.restored
 known=_fixture_test_category2_gem_effects.GemEffectTests.known
 snap=_fixture_test_category2_gem_effects.GemEffectTests.snap
 valid=_fixture_test_category2_gem_effects.GemEffectTests.valid
 def setUp(self):
  _fixture_test_category2_gem_effects.GemEffectTests.setUp(self);self.a.pos=(0,0);self.p.pos=(1,0);self.other.pos=(2,0)
  G.replace_baseline(self.e,self.a,'abilities',['배터리'])
 def start(self,actor):self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(actor,initiative_count=20)
 def give(self,*,giver=None,target=None,ability='배터리'):return self.e.activate_ability(giver or self.a,ability,target or self.p)
 def receiver_turn(self):self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=19)
 def dice(self,expr,times=1):
  m=re.fullmatch(r'(\d+)d(\d+)(?:\+(\d+))?',expr);faces=[1]*(int(m[1])*times)
  return sum(faces)+int(m[3] or 0)*times,faces
 def attack(self,move='화염방사',roll=18):
  with patch.object(self.e,'d20',return_value=roll):return self.e.use_move(self.p,self.other,'move/'+move,set_damage=True)
 def test_registration_exact_duplicates_and_both_actor_roles(self):
  self.assertFalse(self.e.gm_prompts);self.assertFalse(N.live(self.a));self.assertFalse(N.live(self.p))
  self.assertEqual(M.ability_registration(self.r,'배터리')['source_id'],'ability/배터리')
  for value in ['ability/배터리','ability/배터리-2']:
   self.setUp();G.replace_baseline(self.e,self.p,'abilities',[value]);self.start(self.p)
   result=self.give(giver=self.p,target=self.a,ability=value);effect=N.live(self.a)[0]
   self.assertEqual(effect[E.KEY]['applied_by_actor_id'],self.p.entity_id);self.assertEqual(result['effect_id'],effect['id'])
   self.assertFalse(N.live(self.p));self.assertEqual(effect['source'],value);self.valid()
 def test_swift_and_scene_two_aliases_share_one_paid_pool(self):
  self.start(self.a)
  rng=self.e.rng.getstate()
  first=self.give();self.assertEqual((self.a.budget['swift'],self.a.budget['standard']),(0,1))
  second=self.give(ability='ability/배터리-2');self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(self.e.rng.getstate(),rng)
  self.assertNotEqual(first['effect_id'],second['effect_id']);self.assertEqual([x['used'] for x in self.a.spec[A.HISTORY]],[1,2])
  before=self.snap()
  with self.assertRaises(ValueError):self.give()
  self.assertEqual(before,self.snap());self.valid()
 def test_invalid_source_target_and_action_reject_before_payment(self):
  self.start(self.a)
  for case in ['unowned','suppressed','enemy','self','distant','action']:
   snapshot=self.e.gm.snapshot()
   if case=='unowned':G.replace_baseline(self.e,self.a,'abilities',[])
   if case=='suppressed':self.a.abilities_suppressed=True
   if case=='enemy':self.p.side='enemy'
   if case=='distant':self.p.pos=(5,5)
   if case=='action':self.a.budget={'swift':0,'standard':0}
   before=self.snap()
   with self.assertRaises(ValueError):self.give(target=self.a if case=='self' else self.p)
   self.assertEqual(before,self.snap());self.e.gm.restore(snapshot)
 def test_failure_after_payment_is_atomic_for_both_actors(self):
  self.start(self.a);before=self.snap()
  with patch.object(N,'grant',side_effect=ValueError('later grant failure')):
   with self.assertRaises(ValueError):self.give()
  self.assertEqual(before,self.snap());self.assertFalse(self.a.spec.get(A.HISTORY));self.assertFalse(N.live(self.p))
 def test_physical_and_status_preserve_next_special_miss_consumes(self):
  self.known(self.p,'몸통박치기','울음소리','화염방사');self.start(self.a);self.give();self.receiver_turn();uid=N.live(self.p)[0]['id']
  self.attack('몸통박치기',roll=1);self.assertEqual(N.live(self.p)[0]['id'],uid)
  self.e.end_of_turn(self.p);self.start(self.p);self.attack('울음소리',roll=1);self.assertEqual(len(N.live(self.p)),1)
  self.e.end_of_turn(self.p);self.start(self.p)
  with patch.object(self.e,'roll_expr',side_effect=AssertionError('no damage on miss')):self.attack(roll=1)
  self.assertFalse(N.live(self.p));self.assertFalse(self.p.spec[N.HISTORY][-1]['applications']);self.valid()
 def test_normal_electric_and_critical_use_one_source_bonus_roll(self):
  for electric,crit in [(False,False),(True,False),(False,True),(True,True)]:
   self.setUp();self.known(self.p,'화염방사');self.start(self.a);self.give();self.receiver_turn()
   if electric:self.p.type_override_next='전기'
   expr='3d6+6' if electric else '2d6+4'
   baseline=self.e.roll_damage(self.p,self.other,self.r.move('move/화염방사'),crit=crit,set_damage=True)
   if electric:self.p.type_override_next='전기'
   hp=self.other.hp
   with patch.object(self.e,'roll_expr',side_effect=self.dice) as rolls:self.attack(roll=20 if crit else 18)
   self.assertEqual(hp-self.other.hp,baseline+(9 if electric else 6))
   self.assertEqual(rolls.call_args_list,[call(expr)]);observation=self.p.spec[N.HISTORY][-1]['applications'][0]
   self.assertEqual(observation['total'],9 if electric else 6);self.assertEqual(len(observation['faces']),3 if electric else 2)
   self.assertFalse(N.live(self.p));self.assertIsNone(self.p.type_override_next);self.valid();self.assertTrue(self.restored().validate_state()['valid'])
 def test_native_multi_target_attack_reuses_bonus_roll_and_records_all_targets(self):
  from grid import Grid
  self.e.grid=Grid(8,8);self.a.pos=(1,0);self.p.pos=(0,0);self.other.pos=(2,0)
  self.known(self.p,'스피드스타');self.start(self.a);self.give();self.receiver_turn();self.a.pos=(2,0);self.other.pos=(1,0)
  with patch.object(self.e,'roll_expr',side_effect=self.dice) as rolls,patch.object(self.e,'d20',return_value=18):self.e.use_move_on(self.p,self.other,'move/스피드스타',[self.p,self.a,self.other])
  self.assertEqual(sum(c.args[0]=='2d6+4' for c in rolls.call_args_list),1)
  record=self.p.spec[N.HISTORY][-1];self.assertEqual(len(record['applications']),1);self.assertEqual(set(record['applications'][0]['target_ids']),{self.a.entity_id,self.other.entity_id})
  self.assertFalse(hasattr(self.e,'_event_use_scopes'));self.valid()
 def test_scene_reset_and_loss_of_ability_keep_independent_effects(self):
  self.known(self.p,'화염방사');self.start(self.a);self.give();self.give();self.e.end_of_turn(self.a);self.e.end_encounter()
  with self.assertRaises(ValueError):self.give()
  self.e.end_scene(self.e.gm.everyone);self.start(self.a)
  receipt=self.give();self.assertEqual(receipt['used'],1);self.assertEqual(len(N.live(self.p)),3)
  G.replace_baseline(self.e,self.a,'abilities',[]);self.receiver_turn()
  with patch.object(self.e,'roll_expr',side_effect=self.dice) as rolls:self.attack()
  self.assertEqual(len(rolls.call_args_list),3);self.assertFalse(N.live(self.p));self.assertEqual(len(self.p.spec[N.HISTORY]),3);self.valid()
 def test_gm_and_durable_restore_foreign_source_and_frequency(self):
  self.known(self.p,'화염방사');self.start(self.a);receipt=self.give();snapshot=self.e.gm.snapshot();self.receiver_turn();self.attack(roll=1);self.e.gm.restore(snapshot)
  self.assertEqual(N.live(self.p)[0]['activation'],receipt);loaded=self.restored();giver=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id);holder=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id);target=next(c for c in loaded.gm.everyone if c.entity_id==self.other.entity_id)
  loaded.end_of_turn(giver);loaded.start_of_turn(holder,initiative_count=19)
  with patch.object(loaded,'d20',return_value=18):loaded.use_move(holder,target,'move/화염방사',set_damage=True)
  self.assertEqual(holder.spec[N.HISTORY][-1]['activation']['giver_id'],giver.entity_id);self.assertTrue(loaded.validate_state()['valid'])
  self.receiver_turn();self.attack(roll=1);self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
 def test_missing_payer_and_forged_bonus_reject_restore_and_live_cost(self):
  self.known(self.p,'화염방사');self.start(self.a);self.give();self.receiver_turn();receipt=self.a.spec[A.HISTORY][0];good=deepcopy(receipt);receipt['effect_id']='invented'
  with patch.object(E,'validate_world',return_value=True):bad=self.e.gm.snapshot();payload=CODEC.dump_engine(self.e)
  before=self.snap()
  with self.assertRaises(ValueError):self.attack()
  self.assertEqual(before,self.snap());receipt.clear();receipt.update(good);before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.restore(bad)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  self.assertEqual(before,self.snap())
  with patch.object(self.e,'roll_expr',side_effect=self.dice):self.attack()
  record=self.p.spec[N.HISTORY][-1];record['applications'][0]['faces'][0]=True
  with self.assertRaises(ValueError):self.e.gm.snapshot()
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

if __name__=='__main__':unittest.main()
