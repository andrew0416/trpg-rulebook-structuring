"""Integration checks for composed AP, acquisition and active-effect owners."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

import action_points as AP
import state_grants as G
import test_foundation_grant_payments as F
from state_codec import dump_engine, load_engine


class ResponsibilityComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.GrantPaymentTests.setUpClass()

    def fixture(self):
        fixture = F.GrantPaymentTests()
        fixture.setUp()
        return fixture

    def native_effect(self, fixture):
        actor = fixture.owner
        source = "combat/struggle"
        G.grant(actor, "capabilities", "witness/native", source, "feature", rule_id=source)
        actor.active_effects.register(
            fixture.e, source,
            lambda: setattr(actor, "damage_reduction", actor.damage_reduction + 2),
        )
        return source

    def test_retained_ap_account_follows_gm_restore(self):
        f = self.fixture()
        account = f.owner.ap_account
        initial = account.available()
        f.e.gm.snapshot("component/ap")
        account.charge(1)
        self.assertEqual(account.available(), initial - 1)
        f.e.gm.restore("component/ap", reason="component restore")
        self.assertEqual(account.available(), initial)
        account.charge(1)
        self.assertEqual(AP.available(f.owner), initial - 1)
        self.assertEqual(f.other.ap_account.available(), initial)

    def test_retained_ledger_follows_partial_refund_and_gm_restore(self):
        f = self.fixture()
        ledger = f.c.acquisitions
        f.buy(allocation={"child/a": 1, "child/b": 0, "child/c": 0})
        initial = ledger.read(f.e)
        f.e.gm.snapshot("component/acquisition")
        f.refund(["child/a"])
        self.assertEqual(ledger.read(f.e)[0]["children"][0]["state"], "refunded")
        f.e.gm.restore("component/acquisition", reason="restore actual acquisition")
        self.assertEqual(ledger.read(f.e), initial)
        self.assertEqual(f.c.spec["tutor_points"], 2)
        detached = ledger.read(f.e)
        detached[0]["children"].clear()
        self.assertEqual(ledger.read(f.e), initial)

    def test_ending_one_source_preserves_sibling_and_acquisition_evidence(self):
        f = self.fixture()
        f.buy()
        paid = f.c.acquisitions.read(f.e)
        source = self.native_effect(f)
        actor = f.owner
        effects = actor.active_effects
        effects.register(
            f.e, "combat/hit-points",
            lambda: setattr(actor, "damage_reduction", actor.damage_reduction + 3),
        )
        self.assertFalse(effects.register(f.e, source, lambda: self.fail("duplicate registration")))
        self.assertEqual(actor.damage_reduction, 5)
        G.revoke(actor, source, engine=f.e)
        self.assertEqual(actor.damage_reduction, 3)
        self.assertEqual(f.c.acquisitions.read(f.e), paid)
        history = actor.acquisitions.read(f.e)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["state"], "ended")
        self.assertEqual(history[0]["grant_source_id"], source)

    def test_late_failure_restores_all_three_owners_and_rng(self):
        f = self.fixture()
        f.buy()
        source = self.native_effect(f)
        account = f.owner.ap_account
        ledger = f.owner.acquisitions
        effects = f.owner.active_effects
        before = dump_engine(f.e)
        available = account.available()
        receipts = ledger.read(f.e)

        def fail(staged, actor):
            actor.ap_account.charge(1)
            actor.active_effects.remove(staged, source)
            actor.acquisitions.end_source(source)
            staged.rng.randint(1, 20)
            raise RuntimeError("late component failure")

        with self.assertRaisesRegex(RuntimeError, "late component failure"):
            G.transition(f.e, f.owner, fail)
        self.assertEqual(dump_engine(f.e), before)
        self.assertEqual(account.available(), available)
        self.assertEqual(ledger.read(f.e), receipts)
        self.assertTrue(effects.remove(f.e, source))
        self.assertEqual(f.owner.damage_reduction, 0)

    def test_json_roundtrip_preserves_balances_history_and_independent_effects(self):
        f = self.fixture()
        f.buy(allocation={"child/a": 1, "child/b": 0, "child/c": 0})
        source = self.native_effect(f)
        f.owner.ap_account.charge(1)
        f.owner.ap_account.charge(1, mode="drain")
        saved = dump_engine(f.e)
        # Merely acquiring handles must not introduce state or saved graph nodes.
        f.owner.ap_account
        f.owner.acquisitions
        f.owner.active_effects
        self.assertEqual(dump_engine(f.e), saved)
        loaded = load_engine(f.rules, saved)
        by_id = {actor.entity_id: actor for actor in loaded.everyone}
        owner = by_id[f.owner.entity_id]
        pokemon = by_id[f.c.entity_id]
        self.assertEqual(owner.ap_account.available(), f.owner.ap_account.available())
        self.assertEqual(pokemon.acquisitions.read(loaded), f.c.acquisitions.read(f.e))
        owner.active_effects.remove(loaded, source)
        self.assertEqual(owner.damage_reduction, 0)
        self.assertEqual(f.owner.damage_reduction, 2)
        loaded.refund_grant_sources(
            pokemon, ["child/a"], request_id="component/refund", reason="restored native refund"
        )
        self.assertEqual(pokemon.spec["tutor_points"], 3)
        self.assertEqual(f.c.spec["tutor_points"], 2)
        self.assertEqual(owner.ap_account.available(), f.owner.ap_account.available())


if __name__ == "__main__":
    unittest.main()

