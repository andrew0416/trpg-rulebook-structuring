"""S-b_next1-1: rank effects use Virtuoso 8, acquired prerequisites stay Master 6."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import test_book_martial_artist as TB
import martial_artist as MA
import skill_modifiers as S

class MartialArtistEffectRankTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
 def fixture(self,style='철주먹',virtuoso=True,choice='전투'):
  f=TB.MartialArtistTests();f.rules=self.rules
  actual=TB.Combatant
  def actor(rules,spec):
   if spec['id']=='trainer/martial' and virtuoso:
    spec['edges'].append('edge/거장');spec['edge_choices']={'edge/거장':[choice]}
   return actual(rules,spec)
  with patch.object(TB,'Combatant',side_effect=actor):f.setup(style,combat=6)
  self.assertEqual(S.rank(self.rules,f.a,'전투')[2],6)
  self.assertEqual(S.effective_rank(self.rules,f.a,'전투'),8 if virtuoso and choice=='전투' else 6)
  return f
 def tag(self,f,count):
  f.acquire(training=1);f.start();MA.arm(f.e,f.a,'pummeling_momentum',target=f.t)
  seen=[]
  for i in range(count):
   if i:f.next()
   f.use('마하펀치');seen.append(MA.bonus(f.a,f.t))
  return seen
 def test_virtuoso_soft_landing_reduces_four_and_restores(self):
  f=self.fixture('이판사판');f.acquire();f.start()
  result=MA.soft_landing_fall(f.e,f.a,action_id='fall/rank8',meters=7,intentional=False,reason='actual fall',natural_sky=False,natural_sky_reason='Trainer has no natural flight')
  self.assertEqual((result['meters'],result['damage_distance'],result['height_injuries']),(7,3,0))
  f.restore();f.valid()
 def test_virtuoso_pummeling_reaches_eight_caps_and_restores_seven_and_eight(self):
  f=self.fixture();self.assertEqual(self.tag(f,7),[1,2,3,4,5,6,7])
  f.restore();f.valid();self.assertEqual(MA.bonus(f.a,f.t),7)
  f.next();f.use('마하펀치');self.assertEqual(MA.bonus(f.a,f.t),8)
  f.restore();f.valid();self.assertEqual(MA.bonus(f.a,f.t),8)
  f.next();f.use('마하펀치');self.assertEqual(MA.bonus(f.a,f.t),8)
  tag=deepcopy(f.a.spec[MA.TAG]);f.a.spec[MA.TAG]['bonus']=9;MA._seal_tag(f.a.spec[MA.TAG])
  with self.assertRaisesRegex(ValueError,'Pummeling Momentum bonus'):MA.validate(f.e)
  f.a.spec[MA.TAG]=tag;f.valid()
 def test_master_pummeling_caps_six_and_rejects_saved_seven(self):
  f=self.fixture(virtuoso=False);self.assertEqual(self.tag(f,7),[1,2,3,4,5,6,6])
  f.restore();f.valid()
  tag=deepcopy(f.a.spec[MA.TAG]);f.a.spec[MA.TAG]['bonus']=7;MA._seal_tag(f.a.spec[MA.TAG])
  with self.assertRaisesRegex(ValueError,'Pummeling Momentum bonus'):MA.validate(f.e)
  f.a.spec[MA.TAG]=tag;f.valid()
 def test_virtuoso_training_snapshot_and_skill_dice_remain_ordinary_master(self):
  f=self.fixture();f.acquire(training=3)
  self.assertEqual([row['snapshot']['combat'] for row in MA.records(f.a,MA.TRAINING,True)],[6,6,6])
  self.assertEqual(len(f.e.skill_roll(f.a,'전투',fixed=[1]*6).faces),6)
  f.restore();f.valid()
 def test_virtuoso_other_skill_does_not_raise_combat_effect_cap(self):
  f=self.fixture(choice='육상')
  self.assertEqual(S.effective_rank(self.rules,f.a,'육상'),8)
  self.assertEqual(self.tag(f,7),[1,2,3,4,5,6,6])
  f.restore();f.valid()

if __name__=='__main__':unittest.main()
