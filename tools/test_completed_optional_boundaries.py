"""Printed optional contracts missing a complete current public-consumer check."""
from pathlib import Path
from copy import deepcopy
import json
import unittest
from builder import build_trainer
from engine import Combatant, Engine, Rules
import class_move_grants as CLASS
import encounter
import items
import state_codec as CODEC
import state_grants as GRANTS

ROOT=Path(__file__).resolve().parents[1]
FIXED={
 'FAN-100':('feat/철벽',['철벽','방어']),
 'FAN-125':('feat/선명한-그림자',['악의파동','깜짝베기']),
 'FAN-126':('feat/심연의-심장',['나이트버스트','혼내기']),
 'FAN-143':('feat/정열적인-하모니',['매지컬샤인','드레인키스']),
 'FAN-144':('feat/럭키-클로버-그랜드-피날레',['문포스','아로마미스트']),
 'FAN-185':('feat/반짝임',['트라이어택','웨더볼']),
 'FAN-186':('feat/레인보우-서지',['파괴광선','아침햇살']),
 'FAN-194':('feat/불쾌함의-부름',['녹기','오물폭탄']),
 'FAN-195':('feat/불쾌함-촉발',['오물웨이브','맹독']),
 'FAN-200':('feat/바위-파편',['스톤샤워','스텔스록']),
}

class CompletedOptionalBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')
 def actor(self,uid,**extra):
  spec=build_trainer(self.rules,'optional-native-owner',30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],abilities=[])
  spec.update(classes=[],edges=[],feats=[uid],skills={'전투':6,'육상':6,'생존':6},**extra)
  if uid in ('feat/선명한-그림자','feat/심연의-심장'):spec['static_feature_choices']={uid:'atk'}
  actor=Combatant(self.rules,spec);e=Engine(self.rules,126);e.everyone=e.gm.everyone=[actor]
  return e,actor
 def test_ten_printed_fixed_pairs_reach_usable_moves_and_independent_ownership(self):
  for clause,(uid,names) in FIXED.items():
   with self.subTest(clause=clause):
    expected=[self.rules.move_id(name) for name in names];self.assertNotIn(None,expected)
    e,c=self.actor(uid);GRANTS.set_baseline(c,'moves',[expected[0]])
    self.assertNotIn(expected[1],encounter.usable_moves(e,c));items.register_feats(e,c)
    key='feature:'+c.entity_id+':'+uid;row=c.spec[GRANTS.KEY]['sources'][key]
    self.assertEqual((row['rule_id'],row['owner_id'],row['lifetime']),(uid,c.entity_id,'while_owned'))
    self.assertCountEqual(row['grants']['moves'],expected)
    self.assertTrue(set(expected)<=set(encounter.usable_moves(e,c)))
    before=deepcopy(c.spec[GRANTS.KEY]);items.register_feats(e,c);self.assertEqual(c.spec[GRANTS.KEY],before)
    e.end_encounter();self.assertTrue(set(expected)<=set(encounter.usable_moves(e,c)))
    loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)));q=loaded.everyone[0]
    self.assertTrue(set(expected)<=set(encounter.usable_moves(loaded,q)))
    q.spec['feats']=[];items.register_feats(loaded,q)
    GRANTS.revoke(q,key,engine=loaded)
    self.assertIn(expected[0],encounter.usable_moves(loaded,q));self.assertNotIn(expected[1],encounter.usable_moves(loaded,q))
    self.assertTrue(loaded.validate_state()['valid'])
 def test_winter_herald_full_table_rank_history_real_consumer_and_invalid_future_cell(self):
  uid='feat/겨울의-예고'
  printed={1:('프리즈드라이','냉동펀치','냉동빔','고드름떨구기'),2:('눈사태','눈보라','얼음숨결','고드름침')}
  self.assertEqual(CLASS.RANKED[uid],printed)
  history=[['프리즈드라이','냉동펀치'],['눈사태','눈보라']]
  e,c=self.actor(uid,feat_ranks={uid:1},feature_choices={uid:history[:1]})
  items.register_feats(e,c)
  c.spec['feat_ranks'][uid]=2;c.spec['feature_choices'][uid]=deepcopy(history);items.register_feats(e,c)
  expected=[self.rules.move_id(name) for pair in history for name in pair]
  self.assertTrue(set(expected)<=set(encounter.usable_moves(e,c)))
  c.spec['feat_ranks'][uid]=1;c.spec['feature_choices'][uid]=[history[1]]
  before=deepcopy((c.spec,c.moves,e.rng.getstate()))
  with self.assertRaises(ValueError):items.register_feats(e,c)
  self.assertEqual((c.spec,c.moves,e.rng.getstate()),before)
  c.spec['feature_choices'][uid]=history[:1];items.register_feats(e,c)
  self.assertFalse(set(expected[2:])&set(encounter.usable_moves(e,c)))
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)));q=loaded.everyone[0]
  self.assertTrue(set(expected[:2])<=set(encounter.usable_moves(loaded,q)))
  q.spec['feats']=[];items.register_feats(loaded,q)
  self.assertFalse(set(expected)&set(encounter.usable_moves(loaded,q)))

if __name__=='__main__':unittest.main()
