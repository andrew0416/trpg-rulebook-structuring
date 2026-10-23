"""Borrowed mount moves share the actual donor's frequency ledger."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import move_permissions as P,move_state as M,frequency as F,pokemon_activities as A,state_grants as G,state_codec as C

class RiderPermissionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def setUp(self):
  self.e=Engine(self.r,seed=733)
  self.a=Combatant(self.r,build_trainer(self.r,'Actual rider',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=['찬란한라이더'],extra={'skills':{'곡예':3,'육상':3},'edges':['edge/탑승-기량']}))
  self.mount=Combatant(self.r,build_pokemon(self.r,'보만다',50,moves=['move/파괴광선','move/하이퍼보이스'],abilities=[]))
  self.target=Combatant(self.r,build_pokemon(self.r,'잠만보',50,moves=[],abilities=[]))
  for c,pos,side in [(self.a,(0,0),'party'),(self.mount,(0,0),'party'),(self.target,(0,2),'enemy')]:self.e.gm.add_combatant(c,pos=pos,side=side,reason='actual actors')
  result=A.mounting(self.e,self.a,target=self.mount,phase='mount',gm_mountable=True);self.assertTrue(result['passed'])
  self.e.begin_encounter([self.a,self.mount,self.target]);self.e.start_round([self.a,self.mount,self.target]);self.e.start_of_turn(self.a)
 def before(self):return deepcopy((self.a.spec,self.mount.spec,self.a.moves,self.a.budget,self.e.rng.getstate()))
 def test_actual_use_is_rider_action_but_donor_daily_pool_and_end_turn_restore(self):
  # Rider's Swift activation leaves no Swift for an Exhaust Move (ch10:317).
  # A real non-Exhaust daily Move isolates the intended donor-pool contract.
  mid='move/에어로블라스트';self.e.gm.set_move(self.mount,mid,reason='actual independent non-Exhaust daily donor Move')
  P.activate_rider(self.e,self.a,mid)
  self.assertIn(mid,self.a.moves);self.assertNotIn(mid,M.owned_list(self.a.spec,'moves'))
  self.e.use_move(self.a,self.target,mid)
  self.assertEqual(self.mount.move_uses.get(mid),1);self.assertEqual(self.a.move_uses.get(mid,0),0)
  self.assertFalse(F.move_allowed(self.e,self.mount,mid)[0]);self.assertEqual(self.a.budget['standard'],0)
  e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)));a=next(c for c in e.everyone if c.entity_id==self.a.entity_id);donor=next(c for c in e.everyone if c.entity_id==self.mount.entity_id)
  self.assertIs(P.frequency_owner(e,a,mid),donor)
  e.end_of_turn(a);self.assertNotIn(mid,a.moves);self.assertEqual(donor.move_uses[mid],1)
 def test_donor_exhaustion_and_independent_permission_overlap_cannot_reset_pool(self):
  mid='move/파괴광선';self.mount.move_uses[mid]=2;self.mount.spec['move_uses']={mid:2}
  P.activate_rider(self.e,self.a,mid);G.grant_moves(self.a,[mid],'another-permission','effect',mode='permission')
  self.assertFalse(F.move_allowed(self.e,self.a,mid)[0]);self.assertIs(P.frequency_owner(self.e,self.a,mid),self.mount)
  self.e.end_of_turn(self.a);self.assertIn(mid,self.a.moves);self.assertIs(P.frequency_owner(self.e,self.a,mid),self.a)
  G.revoke(self.a,'another-permission',engine=self.e);self.assertNotIn(mid,self.a.moves)
 def test_borrowed_pool_preserves_donor_pp_up_frequency_upgrade(self):
  import items as I,vitamin_moves as V
  mid='move/파괴광선';self.a.spec['items']={V.PP:1}
  I.use_item(self.e,self.a,V.PP,self.mount,selected_move=mid)
  P.activate_rider(self.e,self.a,mid)
  self.assertEqual(F.move_frequency(self.e,mid,self.a),('daily',3))
  self.assertEqual(F.move_frequency(self.e,mid,self.mount),('daily',3))
  self.assertNotIn('vitamin_special_uses',self.a.spec)
 def test_known_or_missing_mount_selection_rejects_before_cost_and_source(self):
  self.e.gm.set_move(self.a,'move/파괴광선',reason='actual independent learned move');before=self.before()
  with self.assertRaisesRegex(ValueError,'not learned'):P.activate_rider(self.e,self.a,'파괴광선')
  self.assertEqual(self.before(),before)
  with self.assertRaisesRegex(ValueError,'actual mount'):P.activate_rider(self.e,self.a,'냉동빔')
  self.assertEqual(self.before(),before)
 def test_scene_twice_and_no_permission_after_ability_source_ends(self):
  mid='move/하이퍼보이스';P.activate_rider(self.e,self.a,mid);self.e.end_of_turn(self.a)
  self.e.start_round([self.a,self.mount,self.target]);self.e.start_of_turn(self.a);P.activate_rider(self.e,self.a,mid);self.e.end_of_turn(self.a)
  self.e.start_round([self.a,self.mount,self.target]);self.e.start_of_turn(self.a);before=self.before()
  with self.assertRaisesRegex(ValueError,'frequency'):P.activate_rider(self.e,self.a,mid)
  self.assertEqual(self.before(),before)
  self.e.end_of_turn(self.a);self.e.end_scene([self.a,self.mount,self.target]);self.e.begin_encounter([self.a,self.mount,self.target]);self.e.start_round([self.a,self.mount,self.target]);self.e.start_of_turn(self.a)
  P.activate_rider(self.e,self.a,mid);self.e.gm.set_ability(self.a,'찬란한라이더',add=False,reason='actual ability source ends')
  self.assertNotIn(mid,self.a.moves)

if __name__=='__main__':unittest.main()
