"""Independent ranked-tag authority and existing state projection boundaries."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import state_grants as G
import static_feature_state_grants as STATIC
import test_category2_class_move_grants as FIXTURE
CID='input/ch04-trainer-classes.md:2247-2253'
UID='feat/육상-기술'

class RankedStatProjectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 setUp=FIXTURE.ClassMoveTests.setUp
 ranked=FIXTURE.ClassMoveTests.ranked
 def select(self,rank=1):
  pairs=[['조이기','블록'],['누르기','돌진'],['메가톤킥','객기']]
  self.ranked(UID,'class/운동선수',pairs[:rank])
 def state(self):return deepcopy((self.c.spec,self.c.stats,self.c.moves,self.c.hp,self.e.rng.getstate()))
 def test_exact_general_tag_source_and_rank_count_require_actual_ownership(self):
  policy=STATIC._policy(self.rules)
  self.assertEqual(policy['stat_tag_authority']['excerpt_sha256'],
                   'a8b515650d18f8762ede090eb4f40c771ed7a328adf952faa8218bd3bef00316')
  import trainer_feature_acquisition as ACQUISITION
  self.assertEqual(ACQUISITION._martial_source(self.rules,'C04-098')['clause_id'],'C04-098')
  for rank in (1,2,3):
   self.select(rank);before=self.state()
   self.assertEqual(STATIC.plan(self.c)[CID],{'stat':'hp','count':rank})
   self.assertEqual(self.state(),before)
  self.c.spec['feat_ranks'][UID]=4
  before=self.state()
  with self.assertRaises(ValueError):STATIC.plan(self.c)
  self.assertEqual(self.state(),before)
  self.c.spec['feats']=[]
  self.assertNotIn(CID,STATIC.plan(self.c))
 def test_rank_projection_reuses_source_operation_and_preserves_independent_hp(self):
  self.select();G.stat(self.c,'hp',2,'equipment:independent-hp')
  base=self.c.spec['stats']['hp'];before_hp=self.c.hp
  STATIC.register_all(self.e,self.c)
  source=STATIC._source(self.c,CID)
  self.assertEqual(self.c.stats['hp'],base+3)
  self.assertEqual(self.c.spec['stats']['hp'],base)
  self.assertEqual(self.c.hp,before_hp)
  row=self.c.spec[G.KEY]['stat_sources']['hp']['sources'][source]
  self.assertEqual(row,{'feature_count':{'delta':1,'minimum':None}})
  old=self.state();STATIC.register_all(self.e,self.c);self.assertEqual(self.state(),old)
  self.select(3);STATIC.register_all(self.e,self.c)
  self.assertEqual(self.c.stats['hp'],base+5)
  self.assertEqual(len(self.c.spec[G.KEY]['stat_sources']['hp']['sources'][source]),1)
  self.c.spec['feats']=[];STATIC.register_all(self.e,self.c)
  self.assertEqual(self.c.stats['hp'],base+2)
  self.assertNotIn(source,self.c.spec[G.KEY]['sources'])
 def test_exact_source_or_tag_corruption_is_rejected_without_actor_mutation(self):
  self.select();before=self.state();policy=deepcopy(STATIC._policy(self.rules))
  original=Path.read_text
  for defect in ('authority','tag'):
   with self.subTest(defect=defect):
    value=deepcopy(policy)
    if defect=='authority':value['stat_tag_authority']['excerpt_sha256']='0'*64
    else:value['rules'][CID]['tag']='+공격'
    self.rules.__dict__.pop('_static_feature_state_policy',None)
    def read(path,*args,**kwargs):
     if path.as_posix().endswith(STATIC.POLICY_PATH):return json.dumps(value,ensure_ascii=False)
     return original(path,*args,**kwargs)
    with patch.object(Path,'read_text',read):
     with self.assertRaises(ValueError):STATIC.plan(self.c)
    self.assertEqual(self.state(),before)
  self.rules.__dict__.pop('_static_feature_state_policy',None)

if __name__=='__main__':unittest.main()
