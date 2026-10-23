"""CSV weather rocks on the native equipment and weather-lifetime paths."""
import json
import importlib.util
from copy import deepcopy
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path.insert(0, str(STAGE / "engine"))
sys.path.insert(1, str(ROOT / "engine"))


def _stage_module(name):
    spec = importlib.util.spec_from_file_location(name, STAGE / "engine" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_stage_module("weather_duration_items")
_stage_module("homebrew_weather")
WEATHER = _stage_module("weather_state")

from engine import Combatant, Engine, Rules
from state_codec import StateCodecError
import items as ITEMS
import world_entities as WORLD


CASES = (
    ("차가운바위", "싸라기눈", "hail", "C2CSV/inventory:134:10"),
    ("보송보송바위", "모래바람", "sandstorm", "C2CSV/inventory:135:10"),
    ("뜨거운바위", "쾌청", "sunny", "C2CSV/inventory:136:10"),
    ("축축한바위", "비바라기", "rain", "C2CSV/inventory:137:10"),
)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="core")

    def fixture(self, *, pokemon=False, abilities=()):
        engine = Engine(self.rules, 58)
        base = dict(
            level=25,
            stats=dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 20),
            moves=["move/" + move for _, move, _, _ in CASES],
        )
        if pokemon:
            base.update(id="weather/pokemon", name="P", kind="pokemon", abilities=list(abilities))
        else:
            base.update(id="weather/trainer", name="T", kind="trainer")
        actor = Combatant(self.rules, base)
        witness = Combatant(self.rules, dict(base, id="weather/witness", name="W", kind="pokemon", abilities=[]))
        engine.everyone = engine.gm.everyone = [actor, witness]
        return engine, actor, witness

    def equip(self, engine, actor, name, suffix="one", *, held=False):
        uid = "weather-item/" + suffix
        WORLD.register_object(
            engine, uid, kind="item_instance", item_rule_id="item/" + name,
            owner_id=actor.entity_id, location={"kind": "unknown"},
            reason="actual inspected weather-duration equipment",
        )
        ITEMS.register_item(engine, actor, name, source_instance_id=uid, as_held=held)
        return uid

    def cast(self, engine, actor, move):
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=12)
        result = engine.use_move(actor, actor, "move/" + move)
        engine.end_of_turn(actor)
        return result

    def restored(self, engine):
        return Engine.import_state(self.rules, json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))

    def test_each_actual_equipped_rock_extends_only_its_native_weather_move(self):
        for index, (item, move, weather, clause_id) in enumerate(CASES):
            with self.subTest(clause_id=clause_id):
                engine, actor, _ = self.fixture()
                uid = self.equip(engine, actor, item, str(index))
                self.cast(engine, actor, move)
                active = engine._weather_state["active"]
                self.assertEqual((engine.weather, engine.weather_rounds, active["duration"]), (weather, 7, 7))
                receipt = active["item_extension"]
                self.assertEqual((receipt["base_rounds"], receipt["added_rounds"]), (5, 2))
                self.assertEqual(receipt["sources"][0]["instance_id"], uid)
                self.assertEqual(receipt["sources"][0]["item_id"], "item/" + item)
                self.restored(engine)

    def test_mismatched_rock_and_gm_weather_do_not_receive_an_extension(self):
        engine, actor, _ = self.fixture()
        self.equip(engine, actor, "차가운바위", "cold")
        self.cast(engine, actor, "비바라기")
        self.assertEqual(engine.weather_rounds, 5)
        self.assertNotIn("item_extension", engine._weather_state["active"])
        engine.gm.set_weather("hail", rounds=5, reason="GM-created weather is not the wearer's move")
        self.assertEqual(engine.weather_rounds, 5)
        self.assertNotIn("item_extension", engine._weather_state["active"])

    def test_created_deadline_survives_unequip_snapshot_and_json_restore(self):
        engine, actor, _ = self.fixture()
        self.equip(engine, actor, "축축한바위", "rain")
        self.cast(engine, actor, "비바라기")
        expected = deepcopy(engine._weather_state["active"])
        engine.gm.snapshot("extended-rain")
        ITEMS.unregister_item(engine, actor, "축축한바위")
        self.assertEqual(engine._weather_state["active"], expected)
        loaded = self.restored(engine)
        self.assertEqual(loaded._weather_state["active"], expected)
        WEATHER.set_weather(engine, "rain", rounds=5, source_id="move/비바라기", origin="move", actor=actor)
        self.assertEqual(engine.weather_rounds, 5)
        self.assertNotIn("item_extension", engine._weather_state["active"])
        engine.gm.set_weather("sunny", reason="temporary replacement")
        engine.gm.restore("extended-rain")
        self.assertEqual(engine._weather_state["active"], expected)

    def test_two_identical_actual_sources_never_stack_more_than_once(self):
        engine, actor, _ = self.fixture(pokemon=True, abilities=("ability/배달부",))
        self.equip(engine, actor, "축축한바위", "rain-a", held=True)
        self.equip(engine, actor, "축축한바위", "rain-b", held=True)
        WEATHER.set_weather(engine, "rain", rounds=5, source_id="move/비바라기", origin="move", actor=actor)
        receipt = engine._weather_state["active"]["item_extension"]
        self.assertEqual((engine.weather_rounds, receipt["added_rounds"], len(receipt["sources"])), (7, 2, 2))

    def test_receipt_tampering_is_rejected_by_state_validation(self):
        engine, actor, _ = self.fixture()
        self.equip(engine, actor, "뜨거운바위", "sun")
        self.cast(engine, actor, "쾌청")
        original = deepcopy(engine._weather_state["active"]["item_extension"])
        mutations = (
            lambda row: row.__setitem__("base_rounds", 4),
            lambda row: row["sources"][0].__setitem__("item_id", "item/축축한바위"),
            lambda row: row.__setitem__("actor_id", "weather/other"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                engine._weather_state["active"]["item_extension"] = deepcopy(original)
                mutate(engine._weather_state["active"]["item_extension"])
                with self.assertRaises(StateCodecError):
                    engine.export_state()


if __name__ == "__main__":
    unittest.main()
