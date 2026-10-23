"""CSV/body-equivalent Smooth and Swimmer through existing native readers."""
from pathlib import Path
import sys,unittest,csv
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import trainer_capabilities as T
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(ROOT,ruleset='core')
  with (ROOT/'input/db/edges.csv').open(encoding='utf-8-sig',newline='') as f:cls.rows=list(csv.reader(f))
 def actor(self,ath=3,sur=2):
  e=Engine(self.r,43);c=Combatant(self.r,{'id':'swimmer','name':'swimmer','kind':'trainer','level':20,'stats':dict(hp=30,atk=5,**{'def':5},spa=5,spd=5,spe=5),'skills':{'육상':ath,'생존':sur,'곡예':2},'edges':[self.rows[64][0]],'movement':{'land':6,'swim':3},'movement_basis':'base'})
  e.everyone=e.gm.everyone=[c];return e,c
 def test_either_prerequisite_adds_two_swim_and_uses_higher_rank_for_water_only(self):
  for ath,sur in [(3,2),(2,3),(4,6),(6,4)]:
   e,c=self.actor(ath,sur)
   self.assertEqual(e.move_profile(c,movement_mode='swim')[0],5)
   self.assertEqual(T.breath_grace(c,'water'),60*max(ath,sur))
   self.assertEqual(T.breath_grace(c,'airless'),60)
   c.spec['edges']=[];self.assertEqual(e.move_profile(c,movement_mode='swim')[0],3)
 def test_missing_acquisition_prerequisite_rejects_before_clock_or_state_changes(self):
  e,c=self.actor(2,2);before=deepcopy(c.spec);clock=e.elapsed_seconds
  with self.assertRaisesRegex(ValueError,'Novice'):e.move_profile(c,movement_mode='swim')
  with self.assertRaisesRegex(ValueError,'Novice'):e.observe_breathing(c,air_available=False,medium='water',reason='actual immersion',timing_policy='grace_boundary')
  self.assertEqual(c.spec,before);self.assertEqual(e.elapsed_seconds,clock)
 def test_actual_water_clock_uses_extended_grace(self):
  e,c=self.actor(3,4)
  e.observe_breathing(c,air_available=False,medium='water',reason='actual immersion',timing_policy='grace_boundary')
  e.advance_time(239);self.assertEqual(c.injuries,0)
  e.advance_time(1);self.assertEqual(c.injuries,1)
if __name__=='__main__':unittest.main()
