"""Independent rejection boundaries for the three ranked Speed consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import class_move_grants as MOVES
import static_feature_state_grants as STATIC
import items
import test_category2_fantasy_ranked_moves as FIXTURE
SOURCES={'FAN-140':'feat/스톰-위자드','FAN-158':'feat/휘몰아치는-바람','FAN-216':'feat/해류의-부름'}

class RankedSpeedBoundaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(ROOT,ruleset='all')
  cls.tables=MOVES._ranked_tables(cls.rules)
 fixture=FIXTURE.FantasyRankedMoveTests.fixture
 fingerprint=FIXTURE.FantasyRankedMoveTests.fingerprint
 def test_each_source_excerpt_and_stat_tag_reject_corruption_atomically(self):
  policy=deepcopy(STATIC._policy(self.rules));original=Path.read_text
  try:
   for cid,uid in SOURCES.items():
    for defect in ('source','tag'):
     with self.subTest(source=cid,defect=defect):
      e,a=self.fixture(uid);before=self.fingerprint(e,a)
      changed=deepcopy(policy)
      if defect=='source':changed['rules'][cid]['excerpt_sha256']='0'*64
      else:changed['rules'][cid]['tag']='+HP'
      self.rules.__dict__.pop('_static_feature_state_policy',None)
      def read(path,*args,**kwargs):
       if path.as_posix().endswith(STATIC.POLICY_PATH):return json.dumps(changed,ensure_ascii=False)
       return original(path,*args,**kwargs)
      with patch.object(Path,'read_text',read):
       with self.assertRaises(ValueError):items.register_feats(e,a)
      self.assertEqual(self.fingerprint(e,a),before)
  finally:self.rules.__dict__.pop('_static_feature_state_policy',None)
 def test_duplicate_owner_aliases_cannot_multiply_speed_or_move_grants(self):
  for cid,uid in SOURCES.items():
   with self.subTest(source=cid):
    e,a=self.fixture(uid);items.register_feats(e,a)
    a.spec['feats'].append(self.rules.selection.units[uid]['title'])
    before=self.fingerprint(e,a)
    with self.assertRaises(ValueError):items.register_feats(e,a)
    self.assertEqual(self.fingerprint(e,a),before)

if __name__=='__main__':unittest.main()
