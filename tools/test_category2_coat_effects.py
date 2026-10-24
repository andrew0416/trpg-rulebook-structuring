"""Native periodic Coats, removal history, displacement and restored state."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_gem_effects as _fixture_test_category2_gem_effects
import coat_effects as C,effect_instances as E,state_codec as CODEC,effects_ext as EXT

class CoatEffectTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_gem_effects.GemEffectTests.setUpClass.__func__)
 def setUp(self):
  _fixture_test_category2_gem_effects.GemEffectTests.setUp(self);self.e.gm.observe_loyalty(self.other,6,reason="actual consumer Move obedience")
 known=_fixture_test_category2_gem_effects.GemEffectTests.known
 restored=_fixture_test_category2_gem_effects.GemEffectTests.restored
 add=_fixture_test_category2_gem_effects.GemEffectTests.add
 snap=_fixture_test_category2_gem_effects.GemEffectTests.snap
 valid=_fixture_test_category2_gem_effects.GemEffectTests.valid
 def begin(self,actor):self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(actor,initiative_count=20)
 def next_turn(self,actor):self.e.end_of_turn(actor);self.begin(actor)
 def cast(self,actor,name):
  self.e.use_move(actor,actor,'move/'+name)
  self.assertTrue(any(r['source']=='move/'+name for r in C.live(actor)),self.e.log_lines[-5:])
 def test_actual_both_actor_kinds_pay_and_heal_only_on_future_own_turn(self):
  for role in ['a','p']:
   self.setUp();actor=getattr(self,role);self.known(actor,'아쿠아링');self.begin(actor);actor.hp=1;before=actor.hp;self.cast(actor,'아쿠아링')
   record=C.live(actor)[0];self.assertEqual(actor.hp,before);self.assertEqual(actor.budget['standard'],0);self.assertEqual(actor.move_uses['move/아쿠아링'],1)
   self.assertEqual(record[E.KEY]['applied_by_actor_id'],actor.entity_id)
   self.e.end_of_turn(actor);self.e.start_of_turn(self.other,initiative_count=19);self.assertEqual(actor.hp,before)
   self.e.end_of_turn(self.other);self.begin(actor);self.assertEqual(actor.hp,before+self.e.tick(actor));self.assertEqual(len(record['applications']),1)
   EXT.start_of_turn(self.e,actor);self.assertEqual(len(record['applications']),1);self.valid()
 def test_distinct_current_max_and_tick_formulas_and_persistent_scene_lifetime(self):
  self.known(self.p,'아쿠아링','뿌리박기');self.begin(self.p);self.cast(self.p,'아쿠아링');self.next_turn(self.p);self.cast(self.p,'뿌리박기')
  self.p.injuries=3;self.p.hp=1;expected=2*(self.p.base_max_hp//10)
  self.next_turn(self.p);self.assertEqual(self.p.hp,1+expected)
  observations={r['source']:r['applications'][-1] for r in C.live(self.p)}
  self.assertEqual(observations['move/아쿠아링']['basis'],self.p.base_max_hp);self.assertEqual(observations['move/뿌리박기']['basis'],self.p.base_max_hp)
  self.e.end_of_turn(self.p);self.e.end_encounter();self.e.end_scene();self.assertEqual(len(C.live(self.p)),2);self.valid()
 def test_recast_with_unreviewed_composition_rejects_before_cost(self):
  self.known(self.p,'아쿠아링');self.begin(self.p);self.cast(self.p,'아쿠아링');self.next_turn(self.p);before=self.snap()
  with self.assertRaisesRegex(ValueError,'composition'):self.e.use_move(self.p,self.p,'move/아쿠아링')
  self.assertEqual(before,self.snap());self.assertEqual(len(C.live(self.p)),1)
 def test_actual_clear_smog_removes_all_instances_and_preserves_ending_history(self):
  self.known(self.p,'아쿠아링','뿌리박기');self.known(self.other,'클리어스모그');self.begin(self.p);self.cast(self.p,'아쿠아링');self.next_turn(self.p);self.cast(self.p,'뿌리박기');ids={r['id'] for r in C.live(self.p)}
  self.e.end_of_turn(self.p);self.e.start_of_turn(self.other,initiative_count=19)
  self.e.use_move(self.other,self.p,'move/클리어스모그',set_damage=True)
  self.assertFalse(C.live(self.p));closed=[r for r in self.p.spec[C.HISTORY] if r[E.KEY]['kind']==C.KIND]
  self.assertEqual({r['id'] for r in closed},ids);self.assertTrue(all(r[E.KEY]['end_event']['actor_id']==self.other.entity_id for r in closed))
  self.p.hp=1;self.e.end_of_turn(self.other);self.begin(self.p);self.assertEqual(self.p.hp,1);self.valid();self.assertTrue(self.restored().validate_state()['valid'])
 def test_actual_defog_removes_source_coats_on_multiple_actors(self):
  self.known(self.a,'아쿠아링','안개제거');self.known(self.p,'뿌리박기');self.begin(self.a);self.cast(self.a,'아쿠아링')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=19);self.cast(self.p,'뿌리박기');self.e.end_of_turn(self.p);self.begin(self.a)
  self.e.use_move(self.a,self.a,'move/안개제거')
  self.assertFalse(self.a.coats);self.assertFalse(self.p.coats)
  self.assertEqual(self.a.spec[C.HISTORY][-1][E.KEY]['end_event']['source'],'move/안개제거');self.assertEqual(self.p.spec[C.HISTORY][-1][E.KEY]['end_event']['source'],'move/안개제거');self.valid()
 def test_actual_push_is_prevented_by_ingrain_and_restored_after_clear(self):
  from test_category3_physics_maneuvers import Tests as P
  P.setUpClass();x=P();x.setUp();x.e.gm.set_move(x.b,'move/뿌리박기',reason='actual acquired Move');x.e.gm.set_move(x.a,'move/클리어스모그',reason='actual acquired Move')
  x.e.end_of_turn(x.a);x.e.start_of_turn(x.b,initiative_count=19);x.e.use_move(x.b,x.b,'move/뿌리박기');self.assertEqual(len(C.live(x.b)),1)
  x.e.end_of_turn(x.b);x.e.start_round(x.e.everyone);x.e.start_of_turn(x.a,initiative_count=20);origin=x.b.pos;result=x.push()
  self.assertEqual(result['pushed_metres'],0);self.assertEqual(x.b.pos,origin);self.assertEqual(x.a.budget['standard'],0)
  x.e.gm.set_move(x.a,'move/메가톤킥',reason='actual native Move with push effect')
  x.e.end_of_turn(x.a);x.e.start_round(x.e.everyone);x.e.start_of_turn(x.a,initiative_count=20)
  with patch.object(x.e,'d20',return_value=18):x.e.use_move(x.a,x.b,'move/메가톤킥',set_damage=True)
  self.assertEqual(x.b.pos,origin);self.assertEqual(len(C.live(x.b)),1)
  x.e.end_of_turn(x.a);x.e.start_round(x.e.everyone);x.e.start_of_turn(x.a,initiative_count=20);x.e.use_move(x.a,x.b,'move/클리어스모그',set_damage=True);self.assertFalse(C.live(x.b))
  x.e.end_of_turn(x.a);x.e.start_round(x.e.everyone);x.e.start_of_turn(x.a,initiative_count=20);self.assertEqual(x.push()['pushed_metres'],1)
 def test_actual_gm_and_durable_restore_continue_one_healing_per_holder_turn(self):
  self.known(self.p,'아쿠아링');self.begin(self.p);self.cast(self.p,'아쿠아링');self.p.hp=1;snapshot=self.e.gm.snapshot();self.next_turn(self.p);self.e.gm.restore(snapshot)
  self.assertEqual(self.p.hp,1);self.assertFalse(C.live(self.p)[0]['applications']);self.next_turn(self.p);self.assertEqual(len(C.live(self.p)[0]['applications']),1)
  loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id);before=p.hp
  EXT.start_of_turn(loaded,p);self.assertEqual(p.hp,before)
  loaded.end_of_turn(p);loaded.start_round(loaded.gm.everyone);loaded.start_of_turn(p,initiative_count=20)
  self.assertEqual(p.hp,min(p.max_hp,before+loaded.tick(p)));self.assertEqual(len(C.live(p)[0]['applications']),2);self.assertTrue(loaded.validate_state()['valid'])
 def test_forged_metadata_payload_observation_rejected_before_turn_and_restore(self):
  self.known(self.p,'아쿠아링');self.begin(self.p);self.cast(self.p,'아쿠아링');self.next_turn(self.p)
  for change in ['payload','holder','observed']:
   original=deepcopy(C.live(self.p)[0]);r=C.live(self.p)[0]
   if change=='payload':r['effect']['denominator']=1
   elif change=='holder':r[E.KEY]['holder_id']=self.other.entity_id
   else:r['applications'][0]['healed']=True
   before=self.snap()
   with self.assertRaises(ValueError):self.e.start_of_turn(self.p,initiative_count=20)
   self.assertEqual(before,self.snap())
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
   self.p.coats[0]=original
  self.valid()

 def test_native_baton_pass_needs_real_replacement_instead_of_shallow_copy(self):
  self.known(self.p,'아쿠아링','배턴터치');self.begin(self.p);self.cast(self.p,'아쿠아링');self.next_turn(self.p);before=self.snap()
  with self.assertRaisesRegex(ValueError,'selected replacement'):self.e.use_move(self.p,self.p,'move/배턴터치')
  self.assertEqual(before,self.snap());self.assertTrue(self.p.on_field);self.assertIsNone(self.p.passed)
 def test_defog_preflights_every_holder_before_any_field_or_actor_mutation(self):
  self.known(self.a,'아쿠아링','안개제거');self.known(self.p,'뿌리박기');self.begin(self.a);self.cast(self.a,'아쿠아링')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=19);self.cast(self.p,'뿌리박기');self.e.end_of_turn(self.p);self.begin(self.a)
  C.live(self.p)[0]['effect']['blocks_push_pull']=False;before=self.snap()
  with self.assertRaisesRegex(ValueError,'payload'):self.e.use_move(self.a,self.a,'move/안개제거')
  self.assertEqual(before,self.snap());self.assertEqual(len(C.live(self.a)),1)

 def test_restore_cannot_introduce_unreviewed_same_source_stacking(self):
  self.known(self.p,'아쿠아링');self.begin(self.p);self.cast(self.p,'아쿠아링');r=deepcopy(C.live(self.p)[0]);self.p.spec[E.SEQUENCE]+=1
  r['id']=self.p.entity_id+':effect:'+str(self.p.spec[E.SEQUENCE]);r[E.KEY]['sequence']=self.p.spec[E.SEQUENCE];self.p.coats.append(r)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'composition'):self.e.start_of_turn(self.p,initiative_count=20)
  self.assertEqual(before,self.snap())
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
