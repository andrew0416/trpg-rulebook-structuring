"""Exact native sources over the existing class-passive combat consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_class_passive_combat_bulk as fixtures
import class_passive_combat as C,combat_precision_features as CPF,state_grants as G
import state_codec as CODEC,world_entities as W,ruleset


class NativeClassPassiveTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ClassPassiveCombatBulkTests.setUpClass.__func__)
 fixture=fixtures.ClassPassiveCombatBulkTests.fixture
 activate=fixtures.ClassPassiveCombatBulkTests.activate
 def test_native_sources_keep_actual_acquisition_and_csv_behavior_distinct(self):
  for uid,clause in C.NATIVE_CLAUSE_BY_RULE.items():
   with self.subTest(source=uid):
    e,t,p,q=self.fixture(feats=[uid]);sid=C._source_id(t,p,uid)
    row=G.state(p)['sources'][sid]
    self.assertEqual((row['acquisition_source'],row['native_clause_id'],row['clause_id']),
                     (uid,clause,C.CLAUSE_BY_RULE[uid]))
    self.assertIs(C._declaration(e,p,uid)[0],t)
    # A behavior clause is evidence, not an acquired Rules source identity.
    with self.assertRaisesRegex(ruleset.UnresolvedRuleSelection,'missing_source_identity'):
     self.fixture(feats=[C.CLAUSE_BY_RULE[uid]])
 def test_trick_shot_penalizes_actual_accuracy_and_keeps_critical_and_no_ac_exception(self):
  e,t,p,q=self.fixture(feats=[C.TRICK_SHOT],pokemon_moves=['화염방사'])
  move=self.rules.move('move/화염방사')
  self.assertTrue(e._accuracy_check_native(p,q,move,waive=True,fixed_roll=3)[0])
  self.activate(e,t,p,C.TRICK_SHOT)
  self.assertFalse(e._accuracy_check_native(p,q,move,waive=True,fixed_roll=3)[0])
  hit,natural,critical=e._accuracy_check_native(p,q,move,waive=True,fixed_roll=17)
  self.assertEqual((hit,natural,critical),(True,17,True))
  no_ac=dict(move,ac=None)
  self.assertEqual(C.accuracy_target(e,p,no_ac,0),0);self.assertEqual(C.critical_bonus(e,p,no_ac),0)
  self.assertEqual(C.accuracy_target(e,p,dict(move,ac=0),0),2)
  melee=self.rules.move('move/몸통박치기')
  self.assertEqual(C.accuracy_target(e,p,melee,melee['ac']),melee['ac'])
 def test_capricious_whirl_uses_actual_evasion_damage_and_encounter_binding_lifetime(self):
  e,t,p,q=self.fixture(feats=[C.CAPRICIOUS],pokemon_moves=['몸통박치기'])
  move=self.rules.move('move/몸통박치기')
  self.activate(e,t,p,C.CAPRICIOUS)
  row=p.spec[C.STATE]['sustains'][C.CAPRICIOUS]
  self.assertEqual(row['native_clause_id'],C.NATIVE_CLAUSE_BY_RULE[C.CAPRICIOUS])
  self.assertEqual(t.spec['ap_bound'][row['instance']],2)
  self.assertFalse(e._accuracy_check_native(q,p,move,fixed_roll=5)[0])
  self.assertEqual(C.damage_roll_modifier(e,p,q,move,1.0),-5)
  e.end_of_turn(t);e.end_encounter(e.everyone)
  self.assertFalse(p.spec[C.STATE]['sustains']);self.assertFalse(t.spec['ap_bound'])
  self.assertEqual(C.evasion_bonus(e,p),0);self.assertEqual(C.damage_roll_modifier(e,p,q,move,1.0),0)
 def test_shining_flame_uses_actual_burn_range_owner_and_source_removal(self):
  e,t,p,q=self.fixture(feats=[C.SHINING_FLAME],pokemon_moves=['니트로차지','불꽃세례'])
  fire=self.rules.move('move/니트로차지');mm=self.rules.move_mech(fire['id'])[0]
  C.after_move(e,p,q,fire,mm,17,5);self.assertNotIn('화상',q.conditions)
  C.after_move(e,p,q,fire,mm,18,5);self.assertIn('화상',q.conditions)
  self.assertEqual(C.damage_roll_modifier(e,p,q,fire,1.0),4)
  ember=self.rules.move('move/불꽃세례')
  self.assertEqual(CPF.effect_natural(e,p,ember,15),18)
  status=self.rules.move('move/도깨비불')
  self.assertEqual(CPF.effect_natural(e,p,status,15),15)
  self.assertEqual(C.damage_roll_modifier(e,t,q,fire,1.0),0)
  t.spec['feats']=[];e.register_abilities(p);q.conditions.discard('화상')
  C.after_move(e,p,q,fire,mm,20,5);self.assertNotIn('화상',q.conditions)
  self.assertEqual(CPF.effect_natural(e,p,ember,15),15)
 def test_native_sustain_and_static_sources_survive_json_gm_and_reject_changed_provenance(self):
  e,t,p,q=self.fixture(feats=[C.TRICK_SHOT,C.SHINING_FLAME],pokemon_moves=['화염방사'])
  self.activate(e,t,p,C.TRICK_SHOT);payload=CODEC.dump_engine(e);e.gm.snapshot('native')
  e.release_class_passive(t,p,C.TRICK_SHOT);e.gm.restore('native',reason='restore exact source and AP binding')
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(payload,ensure_ascii=False)))
  for world in (e,loaded):
   index=W.actor_index(world);lp=index[p.entity_id];lt=index[t.entity_id]
   row=lp.spec[C.STATE]['sustains'][C.TRICK_SHOT]
   self.assertEqual(lt.spec['ap_bound'][row['instance']],2)
   self.assertEqual(row['native_clause_id'],'C03-132')
   self.assertIs(C._active(world,lp,C.TRICK_SHOT)[0],lt)
   self.assertIs(C._declaration(world,lp,C.SHINING_FLAME)[0],lt)
  row=G.state(p)['sources'][C._source_id(t,p,C.SHINING_FLAME)]
  row['native_clause_id']='C03-132'
  self.assertFalse(W.validate_world(e)['valid'])
  with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(e)
 def test_late_source_failure_rolls_back_native_sustain_cost_and_rng(self):
  e,t,p,q=self.fixture(feats=[C.TRICK_SHOT]);e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(t)
  before=CODEC.dump_engine(e);original=G._source
  def fail_sustain(*args,**kwargs):
   if kwargs.get('sustain'):raise RuntimeError('late native sustain source')
   return original(*args,**kwargs)
  with patch.object(G,'_source',side_effect=fail_sustain):
   with self.assertRaisesRegex(RuntimeError,'late native'):e.activate_class_passive(t,p,C.TRICK_SHOT)
  self.assertEqual(before,CODEC.dump_engine(e))


if __name__=='__main__':unittest.main()
