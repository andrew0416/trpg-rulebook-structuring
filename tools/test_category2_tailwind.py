"""Native team initiative and learned capability lifetimes, without flag copies."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
from builder import build_pokemon
import blessing_effects as B,effect_instances as E,state_codec as CODEC
import state_grants as G,move_capabilities as CAP,initiative as INIT

class TailwindTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known
 snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap
 valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid
 restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add
 begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin
 cast=_fixture_test_category2_team_blessings.TeamBlessingTests.cast
 answer=_fixture_test_category2_team_blessings.TeamBlessingTests.answer
 attack=_fixture_test_category2_team_blessings.TeamBlessingTests.attack
 setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 def bonus(self,actor,engine=None):
  engine=engine or self.e
  return sum(row['amount'] for row in B.initiative_contributions(engine,actor))
 def test_actual_cast_changes_native_order_and_recasts_do_not_stack(self):
  first=self.cast('순풍',self.a);second=self.cast('순풍',self.p)
  self.assertNotEqual(first['id'],second['id'])
  self.assertEqual(self.bonus(self.a),5);self.assertEqual(self.bonus(self.p),5);self.assertEqual(self.bonus(self.other),0)
  self.assertEqual(self.e.initiative([self.other,self.a,self.p]),[self.p,self.a,self.other])
  for actor in (self.a,self.p):
   self.assertEqual(actor.initiative_bonus,0);self.assertEqual(len(B.live(actor)),1)
   self.assertEqual(actor.move_uses['move/순풍'],1);self.assertEqual(actor.budget['standard'],0)
  later=self.add(build_pokemon(self.r,'이브이',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.assertEqual(self.bonus(later),5);self.assertFalse(later.blessings)
  before=self.snap();self.bonus(later);self.assertEqual(before,self.snap());self.valid()
 def test_learning_forgetting_and_independent_baseline_capability(self):
  for actor in (self.a,self.p):
   self.known(actor,'순풍');self.assertIn('세찬바람',G.effective_capabilities(actor))
   self.assertEqual(CAP.contributions(actor)[0]['source'],'move/순풍');self.assertFalse(actor.blessings)
   self.e.gm.set_move(actor,'move/순풍',add=False,reason='observed forgotten Move')
   self.assertNotIn('세찬바람',G.effective_capabilities(actor))
  self.p.spec['capabilities']=list(self.p.spec.get('capabilities',[]))+['세찬바람']
  self.cast('순풍',self.p);self.e.gm.set_move(self.p,'move/순풍',add=False,reason='forget independently of active team Blessing')
  self.assertIn('세찬바람',G.effective_capabilities(self.p));self.assertEqual(self.bonus(self.a),5)
  self.e.end_encounter();self.assertEqual(self.bonus(self.a),0);self.assertIn('세찬바람',G.effective_capabilities(self.p));self.valid()
 def test_creator_recall_faint_and_encounter_end_are_distinct_boundaries(self):
  r=self.cast('순풍',self.p);self.e.end_of_turn(self.p)
  self.e.gm.recall(self.p,reason='actual creator recall');self.e.gm.faint(self.p,reason='actual creator faint')
  self.assertEqual(self.bonus(self.a),5);self.assertEqual(B.remaining(r),None)
  self.e.end_encounter([]);self.assertFalse(B.live(self.p));closed=self.p.spec[B.HISTORY][-1]
  self.assertEqual(closed['id'],r['id']);self.assertEqual(closed[E.KEY]['end_event'],{'kind':'encounter_end'})
  self.assertIn('세찬바람',G.effective_capabilities(self.p));self.e.end_encounter([])
  self.assertEqual(sum(x['id']==r['id'] for x in self.p.spec[B.HISTORY]),1);self.valid()
 def test_native_side_exchange_and_defog_preserve_sources(self):
  r=self.cast('순풍');uid=r['id'];self.begin(self.other)
  self.e.use_move(self.other,self.a,'move/코트체인지')
  self.assertEqual(self.bonus(self.a),0);self.assertEqual(self.bonus(self.other),5)
  self.assertEqual(B.live(self.a)[0]['id'],uid);self.assertEqual(B.side(r),'wild')
  self.known(self.a,'안개제거');self.begin(self.a);self.e.use_move(self.a,self.a,'move/안개제거')
  self.assertEqual(self.bonus(self.other),0);self.assertFalse(B.live(self.a))
  self.assertEqual(self.a.spec[B.HISTORY][-1][E.KEY]['end_event']['source'],'move/안개제거');self.valid()
 def test_both_restore_paths_keep_nonstacking_identity_and_forgetting_projection(self):
  first=self.cast('순풍');second=self.cast('순풍',self.p)
  self.e.gm.snapshot('two-origins');self.e.end_encounter();self.e.gm.restore('two-origins')
  self.assertEqual({r['id'] for c in self.e.gm.everyone for r in B.live(c)},{first['id'],second['id']})
  restored=self.restored();actors={c.entity_id:c for c in restored.gm.everyone};a=actors[self.a.entity_id];p=actors[self.p.entity_id]
  self.assertEqual(self.bonus(a,restored),5);self.assertEqual(len(B.initiative_contributions(restored,a)[0]['instances']),2)
  restored.gm.set_move(p,'move/순풍',add=False,reason='forget after durable restore')
  self.assertNotIn('세찬바람',G.effective_capabilities(p));self.assertEqual(self.bonus(a,restored),5)
  restored.end_encounter();self.assertEqual(self.bonus(a,restored),0);self.assertTrue(restored.validate_state()['valid'])
  self.assertEqual(self.bonus(self.a),5)
 def test_continuous_bonus_and_consumable_defense_share_scope_but_not_uses(self):
  r=self.cast('순풍');screen=self.cast('빛의장막');self.answer(True);self.attack(self.p)
  self.assertEqual(B.remaining(screen),1);self.assertIsNone(B.remaining(r));self.assertFalse(r['decisions'])
  self.assertEqual(self.bonus(self.a),5);self.e.end_encounter()
  self.assertEqual([r['source'] for r in B.live(self.a)],['move/빛의장막']);self.valid()
 def test_corrupt_continuous_payload_capacity_history_and_stale_encounter_reject(self):
  for key in ('payload','capacity','decisions','duplicate','encounter'):
   with self.subTest(key=key):
    self.setUp();r=self.cast('순풍')
    if key=='payload':r['effect']['amount']=10
    elif key=='capacity':r[E.KEY]['capacity']['limit']=2
    elif key=='decisions':r['decisions'].append({'selected':True})
    elif key=='duplicate':self.p.blessings.append(deepcopy(r))
    else:self.e.encounter_active=False
    with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
    before=self.snap()
    with self.assertRaises(ValueError):self.e.initiative([self.a,self.other])
    self.assertEqual(before,self.snap())
 def test_no_encounter_and_modified_effect_reject_before_move_cost(self):
  self.known(self.a,'순풍');before=self.snap()
  with self.assertRaisesRegex(ValueError,'encounter'):self.e.use_move(self.a,self.a,'move/순풍')
  self.assertEqual(before,self.snap());self.begin(self.a)
  import effect_contracts as CONTRACT
  raw=deepcopy(B.definition(self.r,'move/순풍')['raw']);raw['no_stack']=False
  before=self.snap();issue=CONTRACT.inspect(self.e,self.a,self.a,raw,'move/순풍')
  self.assertIsNotNone(issue);self.assertEqual(before,self.snap())
  self.cast('순풍');self.a.initiative_override=1
  self.assertTrue(INIT.value(self.r,self.a,engine=self.e).unresolved)

if __name__=='__main__':unittest.main()
