"""The CSV Edge reuses real installed augmentation and native digital damage."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Rules
from ruleset import RuleFilter
import test_foundation_network_integrity as _fixture_test_foundation_network_integrity
from state_codec import load_engine
import network_integrity as I,special_entities as S,world_entities as W

ROOT=Path(__file__).resolve().parents[1]

class DefensiveHackingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.poly=Rules(ROOT,ruleset='all')
 trainer=_fixture_test_foundation_network_integrity.IntegrityTests.trainer
 policy=_fixture_test_foundation_network_integrity.IntegrityTests.policy
 snap=_fixture_test_foundation_network_integrity.IntegrityTests.snap
 next_turn=_fixture_test_foundation_network_integrity.IntegrityTests.next_turn
 run_effect=_fixture_test_foundation_network_integrity.IntegrityTests.run_effect
 def setUp(self):
  _fixture_test_foundation_network_integrity.IntegrityTests.setUp(self);self.t.spec['edges']=[I.DEFENSIVE_HACKING]
  W.register_object(self.e,'datajack/target',location={'kind':'unknown'},reason='actual installed Datajack instance')
  S.observe(self.e,dict(id='augmentation/target',kind='augmentation_set',location={'kind':'unknown'},actor_id=self.t.entity_id,
   body_slots=[],installations=[{'instance_id':'datajack/target','augmentation_id':'datajack'}],allow_added_parts=False,essence_enabled=False),reason='actual target Datajack installation')
 def test_native_technology_attack_automatically_uses_actual_focus_once(self):
  physical_hp=self.t.hp
  out=self.run_effect();self.assertEqual((out['requested'],out['derivation']['defense'],out['derivation']['reduction']),(21,0,3))
  self.assertEqual((self.target['integrity'],self.t.hp),(19,physical_hp))
  self.next_turn();value=self.policy();value['id']+='-declared-feature';value['effect']['defensive_feature']={'source':I.DEFENSIVE_HACKING,'names':[I.DEFENSIVE_HACKING],'skill':'집중'}
  out=self.run_effect(value,request='repeat-with-declaration');self.assertEqual(out['derivation']['reduction'],3)
 def test_virtuoso_focus_uses_eight_reduction_while_ordinary_rank_stays_six(self):
  import skill_modifiers as SKILL,state_grants as GRANTS,supplemental_state as SUPPLEMENTAL
  self.e.gm.set_level(self.t,30,reason='actual level30 Defensive Hacking owner')
  self.e.gm.set_skill(self.t,'집중',6,reason='actual Master Focus before Virtuoso')
  GRANTS.transition(self.e,self.t,lambda e,a:a.spec.update(
   edges=[*a.spec['edges'],'edge/거장'],edge_choices={'edge/거장':['집중']}))
  self.assertEqual(SKILL.rank(self.e.r,self.t,'기술학')[2],4)
  self.assertEqual((SKILL.rank(self.e.r,self.t,'집중')[2],SKILL.effective_rank(self.e.r,self.t,'집중')),(6,8))
  maximum=SUPPLEMENTAL.avatar_maximum(self.e,self.t)
  S.observe(self.e,dict(self.target,integrity=maximum,max_integrity=maximum),reason='actual level30 target avatar maximum')
  physical_hp=self.t.hp
  out=self.run_effect()
  self.assertEqual((out['requested'],out['derivation']['defense'],out['derivation']['reduction']),(16,0,8))
  self.assertEqual((self.target['integrity'],self.t.hp),(maximum-16,physical_hp))
  self.next_turn()
  out=self.run_effect(self.policy(1),request='ordinary-virtuoso')
  self.assertEqual((out['derivation']['defense'],out['derivation']['reduction']),(10,10))
  self.assertEqual((out['requested'],self.target['integrity'],self.t.hp),(1,maximum-17,physical_hp))
  self.next_turn()
  value=self.policy();value['id']+='-virtuoso-declared-feature'
  value['effect']['defensive_feature']={'source':I.DEFENSIVE_HACKING,'names':[I.DEFENSIVE_HACKING],'skill':'집중'}
  out=self.run_effect(value,request='declared-virtuoso')
  self.assertEqual((out['requested'],out['derivation']['reduction']),(16,8))
  self.assertEqual((self.target['integrity'],self.t.hp),(maximum-33,physical_hp))
  self.assertEqual(SKILL.rank(self.e.r,self.t,'집중')[2],6)
 def test_ordinary_digital_damage_keeps_existing_defense_and_adds_focus(self):
  out=self.run_effect(self.policy(1));self.assertEqual(out['requested'],5);self.assertEqual(self.target['integrity'],35)
  self.assertEqual(out['derivation']['reduction'],5)
 def test_unowned_edge_and_real_source_removal_do_not_gain_reduction(self):
  import state_grants as G
  G.transition(self.e,self.t,lambda e,c:c.spec.update(edges=[]))
  out=self.run_effect();self.assertEqual((out['requested'],out['derivation']['reduction']),(24,0))
 def test_missing_datajack_low_skill_and_duplicate_ownership_refuse_atomically(self):
  for field,value in (('기술학',3),('집중',2)):
   original=self.t.spec['skills'][field];self.t.spec['skills'][field]=value
   before=deepcopy((self.t.spec,self.e._physical_objects,self.a.budget,self.e.rng.getstate()))
   with self.assertRaises(ValueError):I._defensive_hacking(self.e,self.t)
   with self.assertRaises(ValueError):self.run_effect()
   self.assertEqual(before,(self.t.spec,self.e._physical_objects,self.a.budget,self.e.rng.getstate()));self.t.spec['skills'][field]=original
  self.t.spec['edges'].append(I.DEFENSIVE_HACKING);before=self.snap()
  with self.assertRaises(ValueError):self.run_effect()
  self.assertEqual(before,self.snap());self.t.spec['edges'].pop()
  row=dict(self.e._physical_objects['augmentation/target'],installations=[]);S.observe(self.e,row,reason='actual Datajack removal');before=self.snap()
  with self.assertRaisesRegex(ValueError,'installed Datajack'):self.run_effect()
  self.assertEqual(before,self.snap())
 def test_selected_source_exclusion_and_changed_csv_refuse_atomically(self):
  old=self.poly.ruleset;self.poly.ruleset=RuleFilter({'sources':['core','polygon'],'exclude_units':[I.DEFENSIVE_HACKING]});self.poly._apply_ruleset()
  try:
   before=self.snap()
   with self.assertRaises(ValueError):self.run_effect()
   self.assertEqual(before,self.snap())
  finally:self.poly.ruleset=old;self.poly._apply_ruleset()
  original=Path.read_bytes
  def changed(path):
   raw=original(path);return raw+b'changed' if path.name=='edges.csv' else raw
  before=self.snap()
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaises(ValueError):self.run_effect()
  self.assertEqual(before,self.snap())
 def test_json_restore_keeps_actual_edge_installation_and_digital_damage(self):
  restored=load_engine(self.poly,json.loads(json.dumps(self.snap())))
  self.e=restored;self.a=W.actor_index(restored)[self.a.entity_id];self.t=W.actor_index(restored)[self.t.entity_id]
  self.target=restored._physical_objects['target-avatar']
  out=self.run_effect();self.assertEqual((out['requested'],self.target['integrity']),(21,19))

if __name__=='__main__':unittest.main()
