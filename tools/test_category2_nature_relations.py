"""Nature source fidelity and strict relation state through actual producers."""
from pathlib import Path
from copy import deepcopy
import random, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine")]
from engine import Engine, Combatant, Rules
import builder as B, nature_state as N


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset="core")
        cls.base = {"hp": 4, "atk": 5, "def": 4, "spa": 6, "spd": 5, "spe": 7}

    def assert_relations(self, base, stats):
        for hi in N.STATS:
            for lo in N.STATS:
                if base[hi] > base[lo]:
                    self.assertGreater(stats[hi], stats[lo], (hi, lo, base, stats))

    def test_all_36_md_cells_and_catalog_spellings_resolve_their_exact_pair(self):
        grid = ["평안 귀여운 산만 위풍당당 과감 끈기", "절박 노력 외로움 고집 개구쟁이 용감",
                "냉혹 대담 온순 장난꾸러기 촐랑 무사태평", "호기심 조심 의젓 수줍음 덜렁 냉정",
                "낭만적 차분 얌전 신중 변덕 건방", "활발 겁쟁이 성급 명랑 천진난만 성실"]
        for up, names in enumerate(grid):
            for down, name in enumerate(names.split()):
                with self.subTest(name=name):
                    record = N.describe(self.r, name)
                    self.assertEqual((record["up_stat"], record["down_stat"]), (N.STATS[up], N.STATS[down]))
                    self.assertEqual(record["neutral"], up == down)
                    self.assertEqual(record["name"], name)
        self.assertEqual(N.describe(self.r, "절박")["catalog_name"], "무모")
        self.assertIsNone(N.describe(self.r, None))
        with self.assertRaises(ValueError):
            B.build_pokemon(self.r, "파이리", 5, nature="unrecognized")

    def test_nature_deltas_minimum_and_neutral_before_allocation(self):
        stats = B.nature_base(self.base, "위풍당당", self.r)
        self.assertEqual(stats, dict(self.base, hp=5, spa=4))
        self.assertEqual(B.nature_base(self.base, "절박", self.r), dict(self.base, atk=7, hp=3))
        for name in ("평안", "노력", "온순", "수줍음", "변덕", "성실"):
            self.assertEqual(B.nature_base(self.base, name, self.r), self.base)
        low = dict(self.base, hp=1, spa=1)
        self.assertEqual(B.nature_base(low, "절박", self.r)["hp"], 1)
        self.assertEqual(B.nature_base(low, "위풍당당", self.r)["spa"], 1)
        for name in self.r.mech("pokemon/natures")["by_name"]:
            adjusted = B.nature_base(self.base, name, self.r)
            for strategy in B.STRATEGY:
                stats = B.allocate_stats(self.base, 15, strategy, name, self.r)
                self.assert_relations(adjusted, stats)
                self.assertEqual(sum(stats.values()) - sum(adjusted.values()), 15)
                self.assertTrue(all(stats[k] >= adjusted[k] for k in N.STATS))

    def test_optional_dice_and_fixed_die_preserve_actual_rng(self):
        rng = random.Random(99)
        before = rng.getstate()
        self.assertEqual(N.from_dice(self.r, rng, raise_die=2, lower_die=4), "고집")
        self.assertEqual(rng.getstate(), before)
        control = random.Random(99)
        expected_down = control.randint(1, 6)
        chosen = N.from_dice(self.r, rng, raise_die=1)
        self.assertEqual(N.describe(self.r, chosen)["down_stat"], N.STATS[expected_down - 1])
        self.assertEqual(rng.getstate(), control.getstate())
        before = rng.getstate()
        for bad in (0, 7, True, 1.5):
            with self.assertRaises(ValueError):
                N.from_dice(self.r, rng, lower_die=bad)
            self.assertEqual(rng.getstate(), before)

    def test_actual_actor_nature_state_consumers_and_roundtrips(self):
        e = Engine(self.r)
        c = Combatant(self.r, B.build_pokemon(self.r, "파이리", 5, nature="절박", abilities=["맹화"]))
        e.gm.add_combatant(c, reason="GM imports nature-adjusted Pokemon")
        self.assert_relations(c.spec["stat_history"][-1]["base"], c.stats)
        self.assertEqual(c.staged("atk"), c.stats["atk"])
        self.assertEqual(c.max_hp, 5 + 3 * c.stats["hp"] + 10)
        view = e.gm.describe_actor(c)["nature_state"]
        self.assertEqual((view["name"], view["up_stat"], view["down_stat"]), ("절박", "atk", "hp"))
        self.assertEqual((view["likes"].replace(" ", ""), view["dislikes"].replace(" ", "")), ("매운맛", "짠맛"))
        e.gm.snapshot("nature")
        c.name = "renamed"
        e.gm.restore("nature")
        self.assertEqual(e.gm.describe_actor(c)["nature_state"], view)
        loaded = Engine.import_state(self.r, e.export_state())
        restored = next(a for a in loaded.everyone if a.entity_id == c.entity_id)
        self.assertEqual(loaded.gm.describe_actor(restored)["nature_state"], view)
        self.assertEqual(restored.spec["stat_history"], c.spec["stat_history"])
        self.assert_relations(restored.spec["stat_history"][-1]["base"], restored.stats)

    def test_flavors_follow_source_stat_pairs_and_neutral_has_none(self):
        flavors = {"hp": "짠맛", "atk": "매운맛", "def": "신맛", "spa": "떫은맛", "spd": "쓴맛", "spe": "단맛"}
        for name in self.r.mech("pokemon/natures")["by_name"]:
            view = N.describe(self.r, name)
            if view["neutral"]:
                self.assertIsNone(view["likes"])
                self.assertIsNone(view["dislikes"])
            else:
                self.assertEqual(view["likes"].replace(" ", ""), flavors[view["up_stat"]])
                self.assertEqual(view["dislikes"].replace(" ", ""), flavors[view["down_stat"]])

    def test_ties_may_split_but_later_point_cannot_equal_higher_group(self):
        spec = B.build_pokemon(self.r, "파이리", 5, nature="노력", abilities=["맹화"])
        # Both original examples satisfy every strict relation; equal bases split.
        for stats in ({"hp": 6, "atk": 8, "def": 6, "spa": 9, "spd": 7, "spe": 10},
                      {"hp": 4, "atk": 5, "def": 4, "spa": 13, "spd": 5, "spe": 15}):
            self.assert_relations(self.base, stats)
            self.assertEqual(sum(stats.values()) - sum(self.base.values()), 15)
        spec["stats"] = {"hp": 6, "atk": 8, "def": 6, "spa": 9, "spd": 7, "spe": 10}
        before = deepcopy(spec)
        with self.assertRaisesRegex(ValueError, "violates base relations"):
            B.add_stat_points(self.r, spec, 1, choice="atk")
        self.assertEqual(spec, before)
        stats = B.add_stat_points(self.r, spec, 1, choice="spe")
        self.assert_relations(self.base, stats)
        self.assertEqual(stats["spe"], 11)

    def test_soulless_exception_remains_zero_under_nature_and_allocation(self):
        spec = B.build_pokemon(self.r, "껍질몬", 5, nature="귀여운")
        c = Combatant(self.r, spec)
        self.assertEqual((c.stats["hp"], c.max_hp, spec["stat_history"][-1]["base"]["hp"]), (0, 1, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
