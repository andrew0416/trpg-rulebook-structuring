from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from learning_slots import occupancy

class LearningSlotsTests(unittest.TestCase):
 def test_data_driven_channels_keep_reservations_distinct_from_exempt_items(self):
  items=[{'id':'move/a','source':'learned/source','weights':{'total':2,'taught':2}}]
  reservations=[{'id':'move/a','source':'reservation/source','weights':{'total':1,'vitamin':1}}]
  before=deepcopy((items,reservations))
  out=occupancy({'total':1,'taught':3,'vitamin':1},items,reservations=reservations,exemptions={'total':{'move/a':'exemption/source'}})
  self.assertTrue(out['valid']);self.assertEqual(out['used'],{'total':1,'taught':2,'vitamin':1})
  self.assertEqual(out['reserved'],{'total':1,'taught':0,'vitamin':1});self.assertEqual((items,reservations),before)
  out['trace'][0]['weights']['total']=99;self.assertEqual(items[0]['weights']['total'],2)
 def test_overflow_unlimited_and_distinct_channel_exemptions(self):
  rows=[{'id':'a','source':'s','weights':{'total':3,'taught':5}}]
  out=occupancy({'total':2,'taught':None},rows)
  self.assertEqual(out['overflow'],{'total':1});self.assertFalse(out['valid'])
  out=occupancy({'total':2,'taught':None},rows,exemptions={'total':{'a':'selected rule'}})
  self.assertEqual(out['used'],{'total':0,'taught':5});self.assertTrue(out['valid'])
 def test_fake_exemptions_and_invalid_costs_rejected(self):
  for weights in [{'total':True},{'total':-1},{'invented':1}]:
   with self.assertRaises(ValueError):occupancy({'total':6},[{'id':'a','source':'s','weights':weights}])
  with self.assertRaises(ValueError):occupancy({'total':6},[],exemptions={'total':{'fake move':'s'}})
  row={'id':'a','source':'s','weights':{'total':1}}
  with self.assertRaises(ValueError):occupancy({'total':6},[row,row])

if __name__=='__main__':unittest.main()
