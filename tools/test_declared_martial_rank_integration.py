"""Composition of declared ordinary ranks with the separately owned Martial repair."""
from copy import copy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
from engine import Rules
from rulings import Rulings
from declared_skill_ranks import configure
import test_book_martial_artist as TB
import martial_artist as MA
import skill_modifiers as S

class DeclaredMartialRankIntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=Rules(ROOT,ruleset='core')
 def fixture(self,rank,style):
  rules=copy(self.base);rules.rulings=Rulings();configure(rules)
  f=TB.MartialArtistTests();f.rules=rules;f.setup(style,combat=rank)
  return f
 def test_declared_seven_and_ten_pummeling_native_cap_and_restore(self):
  for rank in (7,10):
   with self.subTest(rank=rank):
    f=self.fixture(rank,'철주먹');f.acquire(training=1);f.start()
    MA.arm(f.e,f.a,'pummeling_momentum',target=f.t)
    seen=[]
    for i in range(rank+1):
     if i:f.next()
     f.use('마하펀치');seen.append(MA.bonus(f.a,f.t))
    self.assertEqual(seen,list(range(1,rank+1))+[rank])
    self.assertEqual(MA.records(f.a,MA.TRAINING,True)[0]['snapshot']['combat'],rank)
    f.restore();f.valid();self.assertEqual(MA.bonus(f.a,f.t),rank)
    count=7
    self.assertEqual((S.rank(f.e.r,f.a,'전투')[2],len(f.e.skill_roll(f.a,'전투',fixed=[1]*count).faces)),(rank,count))
 def test_declared_seven_and_ten_soft_landing_uses_rank_not_dice(self):
  for rank,reduction in ((7,3),(10,5)):
   with self.subTest(rank=rank):
    f=self.fixture(rank,'이판사판');f.acquire();f.start()
    result=MA.soft_landing_fall(f.e,f.a,action_id='declared-fall',meters=7,intentional=False,
     reason='Actual fall',natural_sky=False,natural_sky_reason='Trainer has no natural flight')
    self.assertEqual(result['damage_distance'],7-reduction)
    f.restore();f.valid()

if __name__=='__main__':unittest.main()
