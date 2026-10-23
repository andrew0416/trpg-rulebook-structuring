from copy import deepcopy
import json
import unittest

from engine import Engine
import csv_item_capability_contracts as CAP
import downtime as DOWNTIME
import world_entities as WORLD
import state_grants as GRANTS
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts


class EggHatcherClock(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.pokemon
    trainer=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.trainer
    fixture=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.fixture
    egg=_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.egg

    def actual(self):
        actor=self.pokemon('homebrew-hatcher',capabilities=('알부화기',))
        owner=self.trainer('actual-egg-owner')
        e=self.fixture(actor,owner)
        return e,actor,owner,self.egg(e,owner,remaining=259200)

    def test_one_then_twenty_four_hour_boundary_and_two_reduce_actual_egg(self):
        e,actor,owner,egg=self.actual()
        before=egg['hatch_remaining_seconds']
        first=CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=1)
        self.assertEqual(first['reduced_seconds'],0)
        self.assertEqual(egg['hatch_remaining_seconds'],before)
        e.advance_time(86399,[actor,owner])
        before=deepcopy(e.export_state())
        with self.assertRaisesRegex(ValueError,'24-hour'):
            CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=2)
        self.assertEqual(e.export_state(),before)
        e.advance_time(1,[actor,owner])
        before=egg['hatch_remaining_seconds']
        result=CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=2)
        self.assertEqual(result['reduced_seconds'],86400)
        self.assertEqual(egg['hatch_remaining_seconds'],max(0,before-86400))

    def test_new_day_cannot_reset_rolling_lifetime_and_json_preserves_it(self):
        e,actor,owner,egg=self.actual()
        CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=1)
        DOWNTIME.new_day(actor)
        restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        index=WORLD.actor_index(restored)
        actual=index[actor.entity_id]
        before=deepcopy(restored.export_state())
        with self.assertRaisesRegex(ValueError,'24-hour'):
            CAP.heat_egg(restored,actual,egg['entity_id'],fixed_d2=2)
        self.assertEqual(restored.export_state(),before)
        restored.advance_time(86400,list(index.values()))
        self.assertEqual(CAP.heat_egg(restored,actual,egg['entity_id'],fixed_d2=2)['reduced_seconds'],86400)

    def test_invalid_die_and_unknown_egg_are_atomic_before_source_receipt(self):
        e,actor,owner,egg=self.actual()
        for value in (False,True,0,3,1.0):
            with self.subTest(value=value):
                before=deepcopy(e.export_state())
                with self.assertRaises(ValueError):
                    CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=value)
                self.assertEqual(e.export_state(),before)
        with self.assertRaises(ValueError):
            CAP.heat_egg(e,actor,'egg/not-registered',fixed_d2=2)
        self.assertNotIn(CAP.STATE,actor.spec)

    def test_pokemon_live_source_and_legacy_clock_authority(self):
        e,actor,owner,egg=self.actual()
        trainer=self.trainer('not-an-egg-hatcher-pokemon',capabilities=('알부화기',))
        e.gm.add_combatant(trainer)
        before=deepcopy(e.export_state())
        with self.assertRaisesRegex(ValueError,'requires a Pokemon'):
            CAP.heat_egg(e,trainer,egg['entity_id'],fixed_d2=2)
        self.assertEqual(e.export_state(),before)
        actor.spec['capabilities']=[]
        GRANTS.grant(actor,'capabilities','알부화기','test/egg-source','capability')
        CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=1)
        GRANTS.revoke(actor,'test/egg-source',engine=e)
        e.advance_time(86400,[actor,owner,trainer])
        before=deepcopy(e.export_state())
        with self.assertRaisesRegex(ValueError,'actual capability required'):
            CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=2)
        self.assertEqual(e.export_state(),before)
        GRANTS.grant(actor,'capabilities','알부화기','test/egg-source','capability')
        self.assertEqual(CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=2)['reduced_seconds'],86400)
        actor.spec[CAP.STATE]['receipts']=[]
        before=deepcopy(e.export_state())
        with self.assertRaisesRegex(ValueError,'actual 24-hour receipt'):
            CAP.heat_egg(e,actor,egg['entity_id'],fixed_d2=2)
        self.assertEqual(e.export_state(),before)
