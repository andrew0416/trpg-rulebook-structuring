"""Actual acquired gift state: availability, source identity, persistence and cleanup.
Acquisition/prerequisite legality and full ability procedures remain category6/5.
"""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import items,state_grants as G
from state_codec import dump_engine,load_engine
CASES=[
 ('feat/프리저의-메이저-기프트-겨울의입맞춤','겨울의입맞춤',597),
 ('feat/라이코의-메이저-기프트-축전','축전',617),
 ('feat/스이쿤의-메이저-기프트-저수','저수',622),
 ('feat/메이저-기프트-확률제어', '확률제어', 633),
 ('feat/메이저-기프트-클리어바디', '클리어바디', 655),
 ('feat/메이저-기프트-용기', '용기', 778),
 ('feat/메이저-기프트-부유', '부유', 789),
 ('feat/메이저-기프트-방음', '방음', 807),
 ('feat/메이저-기프트-매직미러', '매직미러', 823),
 ('feat/메이저-기프트-다정한분위기', '다정한분위기', 846),
 ('feat/레쿠쟈의-메이저-기프트-에어록', '에어록', 961),
 ('feat/디아루가의-메이저-기프트-확률제어', '확률제어', 995),
 ('feat/메이저-기프트-승리의-별', '승리의별', 1164),
 ('feat/큐레무의-메이저-기프트-겨울의-입맞춤', '겨울의입맞춤', 1235),
 ('feat/제나르에스-메이저-기프트-페어리-오라', '페어리오라', 1274),
 ('feat/이벨타르의-메이저-기프트-다크-오라', '다크오라', 1295),
]
class BlessingGrantTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')
 def fixture(self,uid,ability=None):
  r=self.rules;e=Engine(r,37)
  c=Combatant(r,dict(id='gift-holder',name='gift-holder',kind='trainer',level=30,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),feats=[uid],abilities=[] if ability is None else [ability],moves=[],pos=(0,0)))
  e.everyone=e.gm.everyone=[c]
  if ability:e.register_abilities_one(c,ability)
  return e,c
 def test_all_whole_named_gifts_register_once_and_survive_native_codec(self):
  for uid,ability,line in CASES:
   with self.subTest(source=uid):
    e,c=self.fixture(uid);self.assertEqual(items.register_feats(e,c),1)
    source='feature:'+c.entity_id+':'+uid
    self.assertEqual(c.abilities,[ability]);self.assertEqual(c.spec[G.KEY]['sources'][source]['grants']['abilities'],[ability])
    self.assertEqual(c.spec[G.KEY]['sources'][source]['rule_id'],uid)
    e.end_encounter();self.assertIn(ability,c.abilities)
    before=deepcopy(c.spec[G.KEY]);items.register_feats(e,c);self.assertEqual(c.spec[G.KEY],before);self.assertEqual(c.abilities,[ability])
    n=load_engine(self.rules,json.loads(json.dumps(dump_engine(e),ensure_ascii=False)));a=n.everyone[0]
    self.assertEqual(a.abilities,[ability]);self.assertEqual(a.spec[G.KEY],c.spec[G.KEY]);self.assertIs(a,n.gm.everyone[0])
    G.revoke(a,source,engine=n);self.assertNotIn(ability,a.abilities)
    self.assertFalse(any(x.get('_ability')==ability for x in a.modifiers+a.registry))
 def test_all_gifts_snapshot_restore_and_independent_baseline_survives_revoke(self):
  for uid,ability,line in CASES:
   with self.subTest(source=uid):
    e,c=self.fixture(uid,ability);items.register_feats(e,c);source='feature:'+c.entity_id+':'+uid
    e.gm.snapshot('gift');G.revoke(c,source,engine=e);self.assertIn(ability,c.abilities)
    e.gm.restore('gift',reason='restore actual acquired gift')
    self.assertIn(source,c.spec[G.KEY]['sources']);self.assertIn(ability,c.abilities)
    G.revoke(c,source,engine=e);self.assertEqual(c.abilities,[ability]);self.assertNotIn(source,c.spec[G.KEY]['sources'])
 def test_absent_gift_never_invents_its_source(self):
  for uid,ability,line in CASES:
   with self.subTest(source=uid):
    e,c=self.fixture(uid);c.spec['feats']=[]
    self.assertEqual(items.register_feats(e,c),0)
    self.assertNotIn(ability,c.abilities)
    self.assertNotIn('feature:'+c.entity_id+':'+uid,c.spec.get(G.KEY,{}).get('sources',{}))
 def test_independent_gifts_of_same_ability_only_cleanup_after_last_source(self):
  for first,second in [(CASES[0],CASES[13]),(CASES[3],CASES[11])]:
   with self.subTest(first=first[0],second=second[0]):
    uid,ability,_=first;e,c=self.fixture(uid);c.spec['feats'].append(second[0])
    self.assertEqual(items.register_feats(e,c),2);self.assertEqual(c.abilities,[ability])
    source1='feature:'+c.entity_id+':'+uid;source2='feature:'+c.entity_id+':'+second[0]
    self.assertIn(source1,c.spec[G.KEY]['sources']);self.assertIn(source2,c.spec[G.KEY]['sources'])
    G.revoke(c,source1,engine=e);self.assertEqual(c.abilities,[ability]);self.assertIn(source2,c.spec[G.KEY]['sources'])
    G.revoke(c,source2,engine=e);self.assertNotIn(ability,c.abilities)
    self.assertFalse(any(x.get('_ability')==ability for x in c.modifiers+c.registry))
 def test_native_immunity_consumers_follow_gift_source_and_cleanup(self):
  for (uid,ability,line),move_name in [(CASES[1],'전기쇼크'),(CASES[2],'물대포')]:
   with self.subTest(source=uid):
    e,c=self.fixture(uid);items.register_feats(e,c);move=e.r.move(e.r.move_id(move_name))
    self.assertEqual(e.roll_damage(c,c,move,set_damage=True),0)
    c.abilities_suppressed=True;self.assertGreater(e.roll_damage(c,c,move,set_damage=True),0);c.abilities_suppressed=False
    G.revoke(c,'feature:'+c.entity_id+':'+uid,engine=e)
    self.assertGreater(e.roll_damage(c,c,move,set_damage=True),0)
if __name__=='__main__':unittest.main()
