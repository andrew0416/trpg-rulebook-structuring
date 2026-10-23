"""Live trainer source permits HP growth without a global relation bypass."""
from pathlib import Path
from copy import deepcopy,copy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixtures
from builder import build_pokemon
import builder as B,downtime as D,state_fields as F

class OwnerStatTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.ProgressionStateTests.setUpClass.__func__)
 add=fixtures.ProgressionStateTests.add
 snap=fixtures.ProgressionStateTests.snap
 restored=fixtures.ProgressionStateTests.restored
 def setUp(self):
  fixtures.ProgressionStateTests.setUp(self)
  self.c=self.add(build_pokemon(self.r,'파이리',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  base=B.allocation_base(self.r,self.c.spec);stats={k:v*100 for k,v in base.items()}
  self.higher=next(k for k in base if base[k]>base['hp']);stats['hp']=stats[self.higher]-1
  F.base_patch(self.c,{'stats':stats},reason='observed allocation at HP relation boundary')
 def grow(self,stat='hp'):return D.gain_exp_combatant(self.e,self.c,'to next level',stat_choices={self.c.level+1:stat})
 def test_actual_owner_source_allows_hp_and_survives_restore_without_global_exemption(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'base relations'):self.grow()
  self.assertEqual(before,self.snap());self.a.spec['classes']=['class/불굴의-투지'];old=deepcopy(self.c.stats)
  self.grow();self.assertEqual(self.c.stats,{**old,'hp':old['hp']+1})
  record=self.c.spec['stat_history'][-1]['provider'];self.assertEqual(record['trainer_id'],self.a.entity_id)
  self.assertEqual(record['source'],'class/불굴의-투지');self.assertNotIn('stat_relation_exempt',self.c.spec)
  loaded=self.restored();c=next(a for a in loaded.gm.everyone if a.entity_id==self.c.entity_id)
  self.assertEqual(c.stats,self.c.stats);self.assertEqual(c.spec['stat_history'][-1]['provider'],record)
  self.a.spec['classes']=[];before=self.snap()
  with self.assertRaisesRegex(ValueError,'base relations'):self.grow()
  self.assertEqual(before,self.snap())
  self.grow(self.higher);self.assertEqual(self.c.stats['hp'],old['hp']+1)
 def test_unrelated_owner_does_not_authorize_and_other_stats_keep_constraints(self):
  self.a.spec['classes']=['class/불굴의-투지']
  self.c.spec.pop('trainer_id');before=self.snap()
  with self.assertRaisesRegex(ValueError,'base relations'):self.grow()
  self.assertEqual(before,self.snap());self.c.spec['trainer_id']=self.a.entity_id
  stats=deepcopy(self.c.stats);base=B.allocation_base(self.r,self.c.spec)
  lo,hi=next((lo,hi) for lo in base for hi in base if lo!='hp' and hi!='hp' and base[lo]<base[hi]);stats[lo]=stats[hi]-1
  F.base_patch(self.c,{'stats':stats},reason='second boundary')
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'base relations'):self.grow(lo)
  self.assertEqual(before,self.snap())
 def test_excluded_acquired_class_cannot_authorize_hp_growth(self):
  from ruleset import RuleSelection
  self.a.spec['classes']=['class/불굴의-투지']
  profile=deepcopy(self.r.ruleset);profile.exclude_units.add('class/불굴의-투지')
  selection=RuleSelection(profile,list(self.r.selection.units.values()))
  with patch.object(self.r,'ruleset',profile),patch.object(self.r,'selection',selection):
   before=self.snap()
   with self.assertRaises(ValueError):self.grow()
   self.assertEqual(before,self.snap())
 def test_changed_class_source_rejects_before_xp_stats_or_rng(self):
  self.a.spec['classes']=['class/불굴의-투지'];before=self.snap();native=Path.read_bytes
  def changed(path):return native(path)+(b'changed' if path.name=='ch04-trainer-classes.md' else b'')
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):self.grow()
  self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
