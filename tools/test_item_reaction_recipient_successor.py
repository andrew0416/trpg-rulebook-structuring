"""Thunderous Kick uses the shared native hit recipient even through Covert Cloak."""
import unittest
from unittest.mock import patch

import effect_contracts as CONTRACTS
import equipment_variant_contracts as VARIANTS
import test_category2_equipment_variant_contracts as FIX
from grid import Grid
from engine import Engine, Combatant
from builder import build_pokemon


class ItemReactionRecipientSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.EquipmentVariantContractTests.setUpClass()

    def setUp(self):
        self.f = FIX.EquipmentVariantContractTests()

    def test_thunderous_kick_cloak_blocks_wearer_defense_drop_but_keeps_damage(self):
        for accept in (False, True):
            with self.subTest(cloak=accept):
                engine = Engine(self.f.r, seed=65108)
                attacker = Combatant(self.f.r, build_pokemon(self.f.r, 'pokemon/썬더-가라르', 50,
                    moves=['move/천둥차기'], abilities=[], wild=True))
                wearer = self.f.trainer('actual Covert Cloak recipient')
                for actor in (attacker,wearer):engine.gm.add_combatant(actor)
                engine.grid = Grid(10, 10)
                attacker.pos, wearer.pos = (1, 1), (2, 1)
                attacker.side, wearer.side = "foe", "party"
                self.f.equip(engine, wearer, "item/은밀망토", "thunderous-kick")
                engine.start_round([attacker, wearer])
                engine.start_of_turn(attacker, initiative_count=20)
                engine.gm.choose_alternate_move_type(attacker, "move/천둥차기", "전기",
                    reason="actual optional Electric mode keeps the native Defense effect")
                VARIANTS.authorize_covert_cloak(engine, wearer,
                    expected_move_id="move/천둥차기", accept=accept)
                hp, defense = wearer.hp, wearer.stages["def"]
                with patch.object(Engine, "d20", return_value=18):
                    dealt = engine.use_move_on(attacker, wearer, "move/천둥차기",
                                               engine.everyone, set_damage=True)
                self.assertGreater(dealt, 0)
                self.assertLess(wearer.hp, hp)
                self.assertEqual(wearer.stages["def"], defense if accept else defense - 1)
                self.assertTrue(engine.validate_state()["valid"])

    def test_hit_mapping_requires_exact_supported_source_and_selector(self):
        engine, attacker, target = self.f.fixture(moves=("move/천둥차기",))
        effect = dict(type="stage_change", stat="def", delta=-1, target="all_targets")
        self.assertEqual(CONTRACTS.hit_recipients(engine, attacker, target, effect, "move/천둥차기"), (target,))
        for source, candidate in (("move/몸통박치기", effect),
                                  ("move/천둥차기", dict(effect, delta=-2)),
                                  ("move/천둥차기", dict(effect, target="unbound_targets"))):
            with self.subTest(source=source, effect=candidate):
                with self.assertRaisesRegex(ValueError, "source/effect|target-set"):
                    CONTRACTS.hit_recipients(engine, attacker, target, candidate, source)


if __name__ == "__main__":
    unittest.main()
