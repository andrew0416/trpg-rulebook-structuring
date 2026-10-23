from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_grant_payments as F
import state_grants as G,form_allocations as FORMS,effects_ext as EXT
from state_codec import dump_engine,load_engine

class FormTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.GrantPaymentTests.setUpClass()
 def setUp(self):
  self.f=F.GrantPaymentTests();self.f.setUp();f=self.f
  self.forms={'normal':deepcopy(f.c.spec['stats']),'alternate':dict(f.c.spec['stats'],atk=20,def_=5)}
  self.forms['alternate'].pop('def_');self.forms['alternate']['def']=5
  f.e.configure_form_allocations(f.c,self.forms,active='normal',source='combat/struggle')
 def test_shared_source_updates_inactive_projection_without_copying_effective_base(self):
  f=self.f;G._source(f.c,'boost','feature',rule_id='combat/struggle');G.stat(f.c,'atk',3,'boost')
  before=dump_engine(f.e);out=f.e.form_allocation_projection(f.c)
  self.assertEqual((out['normal']['effective']['atk'],out['alternate']['effective']['atk']),(13,23))
  self.assertEqual(out['alternate']['base']['atk'],20);self.assertEqual(dump_engine(f.e),before)
  hp=f.c.hp
  for form,expected in [('alternate',23),('normal',13),('alternate',23)]:
   EXT.h_form_change(f.e,f.c,f.c,{'form':form},{})
   self.assertEqual(f.c.stats['atk'],expected);self.assertEqual(f.c.hp,hp)
  G.transition(f.e,f.c,lambda e,c:G.revoke(c,'boost',engine=e))
  self.assertEqual(f.c.stats['atk'],20);self.assertEqual(f.e.form_allocation_projection(f.c)['normal']['effective']['atk'],10)
 def test_restore_keeps_every_form_base_and_no_duplicate_modifier(self):
  f=self.f;G._source(f.c,'boost','feature',rule_id='combat/struggle');G.stat(f.c,'atk',3,'boost')
  e=load_engine(f.rules,dump_engine(f.e));c=e.everyone[2]
  FORMS.switch(e,c,'alternate');self.assertEqual(c.stats['atk'],23)
  FORMS.switch(e,c,'normal');self.assertEqual(c.stats['atk'],13)
  self.assertEqual(c.spec[FORMS.KEY]['forms'],self.forms)
 def test_unknown_form_and_mismatched_hp_reject_without_partial_state(self):
  f=self.f;before=dump_engine(f.e)
  with self.assertRaises(ValueError):FORMS.switch(f.e,f.c,'unknown')
  with self.assertRaises(ValueError):EXT.h_form_change(f.e,f.c,f.c,{'forms':['unknown'],'at':'turn start'},{})
  bad=deepcopy(self.forms);bad['alternate']['hp']+=1
  with self.assertRaisesRegex(ValueError,'shared HP'):f.e.configure_form_allocations(f.c,bad,active='normal',source='combat/struggle')
  self.assertEqual(dump_engine(f.e),before)
 def test_shared_modifier_invalid_in_inactive_form_rolls_back(self):
  f=self.f;before=dump_engine(f.e)
  def apply(e,c):
   G._source(c,'penalty','feature',rule_id='combat/struggle');G.stat(c,'def',-6,'penalty')
  with self.assertRaisesRegex(ValueError,'effective statistics invalid'):G.transition(f.e,f.c,apply)
  self.assertEqual(dump_engine(f.e),before)

if __name__=='__main__':unittest.main()
