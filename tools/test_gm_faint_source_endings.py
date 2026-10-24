"""GM actual zero-HP observation commits or rolls back native faint source endings."""
from unittest.mock import patch
import unittest
from tools import test_weapon_union_crowned_source_revision as FIXTURE
import csv_item_form_contracts as UNION
import state_codec as CODEC


class GMFaintSourceEndingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):FIXTURE.WeaponUnionCrownedSourceRevisionTests.setUpClass()

    def test_late_native_form_end_failure_restores_hp_form_source_and_full_world(self):
        for species in ('자시안','자마젠타'):
            with self.subTest(species=species):
                fixture=FIXTURE.WeaponUnionCrownedSourceRevisionTests()
                e,actor,_,_,item,_=fixture.scene(species)
                fixture.enter(e,actor,item)
                before=CODEC.dump_engine(e);native=UNION._end_weapon_union
                def fail(*args,**kwargs):
                    native(*args,**kwargs)
                    raise ValueError('actual faint form receiver failed')
                with patch.object(UNION,'_end_weapon_union',side_effect=fail):
                    with self.assertRaisesRegex(ValueError,'actual faint form receiver failed'):
                        e.gm.set_hp(actor,value=0,reason='actual observed knockout')
                self.assertEqual(CODEC.dump_engine(e),before)
                self.assertFalse(actor.fainted)
                self.assertIn('weapon_union',actor.spec[UNION.STATE])


if __name__=='__main__':unittest.main()
