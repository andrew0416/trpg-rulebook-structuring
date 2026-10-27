"""Direct contracts for C07-185 and C07-194."""
from pathlib import Path
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
CANON = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / "engine"), str(CANON / "engine")]

from engine import Combatant, Engine, Rules
from builder import build_trainer
import campaign_injury_policy as CAMPAIGN
import downtime as DOWNTIME
import injury_recovery as INJURY
import precise_actions as PRECISE


STATS = dict(hp=40, atk=12, **{"def": 12}, spa=12, spd=12, spe=12)


def actor(rules, name):
    return Combatant(rules, build_trainer(rules, name, 20, STATS, moves=[]))


class CampaignInjuryPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(CANON), ruleset="core")

    def fresh(self, seed=413):
        engine = Engine(self.r, seed)
        target = actor(self.r, "injury-policy-target")
        engine.everyone = engine.gm.everyone = [target]
        return engine, target

    def test_localized_injuries_reduce_selected_stages_until_actual_healing(self):
        engine, target = self.fresh()
        CAMPAIGN.configure(
            engine, injury_mode="localized", death_enabled=False,
            center_heals_all=False, taskmaster_exempt=True,
            recovery_order="oldest_first", reason="selected gritty campaign")
        baseline = {stat: target.staged(stat) for stat in ("atk", "def", "spa", "spd", "spe")}

        engine.gm.set_injuries(target, value=2, reason="two actual combat injuries")
        active = list(target.spec[CAMPAIGN.ACTIVE])
        self.assertEqual((target.injuries, len(active)), (2, 2))
        self.assertTrue(all(row["location"] for row in active))
        affected = {row["stat"] for row in active}
        self.assertTrue(all(target.staged(stat) < baseline[stat] for stat in affected))

        target.injuries += 1
        PRECISE.injury(engine, target, 1, "feature/감독관/잔혹성-훈련")
        self.assertEqual((target.injuries, len(target.spec[CAMPAIGN.ACTIVE])), (3, 2))
        self.assertEqual(target.spec[CAMPAIGN.HISTORY][-1]["status"], "taskmaster_exempt")

        first_sequence = active[0]["sequence"]
        self.assertEqual(INJURY.heal(engine, target, 1, source="actual_treatment"), 1)
        self.assertEqual(target.injuries, 2)
        self.assertNotIn(first_sequence, {row["sequence"] for row in target.spec[CAMPAIGN.ACTIVE]})
        healed = [row for row in target.spec[CAMPAIGN.HISTORY] if row.get("status") == "healed"]
        self.assertEqual((len(healed), healed[0]["healed_by"]), (1, "actual_treatment"))

    def test_campaign_switches_suppress_injuries_and_disable_death_independently(self):
        engine, target = self.fresh()
        selected = CAMPAIGN.configure(
            engine, injury_mode="disabled", death_enabled=False,
            center_heals_all=False, taskmaster_exempt=False,
            recovery_order="oldest_first", reason="cinematic campaign")
        self.assertEqual((selected["injury_mode"], engine.death_enabled), ("disabled", False))

        engine.gm.set_injuries(target, value=3, reason="producer is suppressed by campaign")
        self.assertEqual(target.injuries, 0)
        target.injuries = 4  # A producer without the shared notifier is caught at the life boundary.
        engine.check_fainted(target)
        self.assertEqual(target.injuries, 0)
        target.hp = -target.base_max_hp
        engine.check_fainted(target)
        self.assertIn("기절", target.conditions)
        self.assertFalse(target.dead)

    def test_selected_center_variant_heals_every_admission_injury(self):
        engine, target = self.fresh()
        CAMPAIGN.configure(
            engine, injury_mode="core", death_enabled=False,
            center_heals_all=True, taskmaster_exempt=False,
            recovery_order="oldest_first", reason="heroic Pokemon Centers")
        engine.gm.set_injuries(target, value=6, reason="center admission injuries")
        DOWNTIME.pokemon_center(engine, target)
        self.assertEqual((target.injuries, target.spec["center_injuries_today"]), (0, 6))

        ordinary, other = self.fresh(seed=414)
        CAMPAIGN.configure(
            ordinary, injury_mode="core", death_enabled=False,
            center_heals_all=False, taskmaster_exempt=False,
            recovery_order="oldest_first", reason="base Center allowance")
        ordinary.gm.set_injuries(other, value=6, reason="ordinary center admission")
        DOWNTIME.pokemon_center(ordinary, other)
        self.assertEqual(other.injuries, 3)

    def test_policy_is_snapshot_owned_and_injury_model_changes_need_conversion(self):
        engine, target = self.fresh()
        CAMPAIGN.configure(
            engine, injury_mode="core", death_enabled=False,
            center_heals_all=True, taskmaster_exempt=False,
            recovery_order="oldest_first", reason="first selection")
        engine.gm.snapshot("campaign-policy")
        CAMPAIGN.configure(
            engine, injury_mode="core", death_enabled=True,
            center_heals_all=False, taskmaster_exempt=False,
            recovery_order="newest_first", reason="temporary selection")
        engine.gm.restore("campaign-policy", "test rollback")
        restored = CAMPAIGN.policy(engine)
        self.assertEqual((restored["death_enabled"], restored["center_heals_all"], engine.death_enabled),
                         (False, True, False))

        engine.gm.set_injuries(target, value=1, reason="existing injury")
        with self.assertRaisesRegex(ValueError, "conversion ruling"):
            CAMPAIGN.configure(
                engine, injury_mode="localized", death_enabled=False,
                center_heals_all=True, taskmaster_exempt=False,
                recovery_order="oldest_first", reason="invalid live conversion")


if __name__ == "__main__":
    unittest.main(verbosity=2)
