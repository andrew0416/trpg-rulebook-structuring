"""Default Wonder Guard is distinct from temporary live ability projection."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import test_category2_body_modes as _fixture_test_category2_body_modes
from builder import build_pokemon
from engine import Combatant
import actor_templates as T,state_grants as G,state_codec as CODEC
class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 setUp=_fixture_test_category2_body_modes.Tests.setUp
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 restored=_fixture_test_category2_body_modes.Tests.restored
 def shedinja(self):return self.add(build_pokemon(self.r,'껍질몬',10,moves=[]))
 def test_native_default_hp_and_invalid_creation_import_are_rejected(self):
  c=self.shedinja();self.assertIn('불가사의부적',c.spec['abilities']);self.assertEqual((c.hp,c.max_hp),(1,1))
  for abilities in ([],['불면']):
   with self.assertRaises(ValueError):build_pokemon(self.r,'껍질몬',10,moves=[],abilities=abilities)
   spec=deepcopy(c.spec);spec['abilities']=abilities
   with self.assertRaises(ValueError):Combatant(self.r,spec)
  with self.assertRaises(ValueError):build_pokemon(self.r,'껍질몬',10,extra={'abilities':[]})
 def test_permanent_removal_atomic_temporary_overlay_does_not_rewrite_default(self):
  c=self.shedinja();before=deepcopy(c.spec)
  with self.assertRaises(ValueError):self.e.gm.set_ability(c,'불가사의부적',add=False,reason='invalid permanent removal')
  self.assertEqual(c.spec,before)
  G.overlay(c,'fixture:temporary',abilities=['불면'])
  self.assertEqual(c.abilities,['불면']);self.assertEqual(c.spec['abilities'],['불가사의부적']);T.validate(c)
  c.abilities_suppressed=True;T.validate(c)
  self.assertEqual(c.max_hp,1)
 def test_both_restores_preserve_default_and_distinct_live_projection(self):
  c=self.shedinja();G.overlay(c,'fixture:temporary',abilities=['불면'])
  self.e.gm.snapshot('soulless');loaded=self.restored();p=next(x for x in loaded.everyone if x.entity_id==c.entity_id)
  self.assertEqual((p.spec['abilities'],p.abilities,p.max_hp),(['불가사의부적'],['불면'],1))
  c.hp=-10;self.e.gm.restore('soulless');self.assertEqual((c.hp,c.abilities),(1,['불면']))
  c.spec['abilities']=[]
  with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.gm.snapshot('invalid')
  with patch.object(T,'validate_soulless_default',return_value=True):
   saved=CODEC.dump_engine(self.e);self.e.gm.snapshot('invalid')
  c.spec['abilities']=['불가사의부적'];before=deepcopy(c.spec)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,saved)
  with self.assertRaises(ValueError):self.e.gm.restore('invalid')
  self.assertEqual(c.spec,before)
 def test_selected_soulless_variant_is_not_assumed_equivalent(self):
  selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**kw:uid+'/variant' if uid==T.SOULLESS else selected(uid,**kw)):
   with self.assertRaises(ValueError):build_pokemon(self.r,'껍질몬',10,moves=[])
if __name__=='__main__':unittest.main()
