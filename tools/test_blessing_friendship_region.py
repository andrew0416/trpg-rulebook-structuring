"""Public Friends/Poffin path accepts the shared independent region field."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import contest_features as F
import native_scenario_fixture as NATIVE
import tools.test_category3_contest_skill_features as BASE

REGION='gift/마이너-기프트-벌컨의-직감'


class FriendshipRegionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')

 fixture=BASE.Tests.fixture
 friends=BASE.Tests.friends
 used=BASE.Tests.used

 def setUp(self):self.fixture('귀여움',F.FRIENDS)

 def assert_friends(self,context):
  original=deepcopy(context)
  result=self.friends(skill_context=context)
  self.assertEqual(result['check'].total,13) # Five Poffin dice of2 + actual unstaged Speed bonus3.
  self.assertTrue(result['check'].passed)
  self.assertEqual(self.w.spec['dispositions'],{'pokemon:pokemon/p':'우호적'})
  self.assertEqual(self.t._action_history,['free'])
  self.assertEqual(self.used(F.FRIENDS),1)
  self.assertEqual(context,original)

 def test_region_only_keeps_granted_poffin_pool_and_real_friendship_result(self):
  for kind in ('mountain','volcanic','other'):
   with self.subTest(kind=kind):
    self.setUp()
    self.assert_friends({'region':{'kind':kind,'reason':'GM observed actual region'}})

 def test_permitted_purpose_and_region_coexist_on_public_friends_path(self):
  for purpose in ('singing','dancing'):
   with self.subTest(purpose=purpose):
    self.setUp()
    self.assert_friends({'purpose':purpose,'reason':'actual friendly performance',
     'region':{'kind':'volcanic','reason':'GM observed actual volcanic district'}})

 def test_malformed_regions_and_unknown_purpose_reject_without_state_or_rng_changes(self):
  regions=(None,{}, {'kind':[],'reason':'invalid kind'}, {'kind':'unknown','reason':'unobserved'},
   {'kind':'volcanic','reason':''}, {'kind':'mountain','reason':'observed','extra':True})
  for region in regions:
   with self.subTest(region=region):
    self.setUp()
    NATIVE.assert_rejected_unchanged(self.e,lambda:self.friends(fixed=None,skill_context={'region':region}),
     reason_pattern='region|reason')
  self.setUp()
  context={'purpose':'invented_purpose','reason':'unsupported check purpose',
   'region':{'kind':'mountain','reason':'GM observed actual mountain'}}
  NATIVE.assert_rejected_unchanged(self.e,lambda:self.friends(fixed=None,skill_context=context),
   reason_pattern='known GM skill purpose')

 def test_r104_does_not_add_three_to_charm_or_transfer_from_trainer_to_performer(self):
  self.t.spec['gifts']=[REGION];self.t.spec['gift_patrons']={REGION:'히드런'}
  self.e.confirm_blessing_gift(self.t,REGION,reason='GM confirms exact already acquired Heatran Gift')
  context={'purpose':'singing','reason':'actual friendly performance',
   'region':{'kind':'volcanic','reason':'GM observed actual volcanic district'}}
  self.assertEqual(self.e.skill_roll(self.t,'매력',fixed=[2]*3,skill_context=context).modifier,0)
  self.assert_friends(context)


if __name__=='__main__':unittest.main()
