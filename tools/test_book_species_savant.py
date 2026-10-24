"""Book C03-126 actual ownership, retained family and existing stat consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "input").is_dir():
    ROOT = Path(r"D:/trpg-rulebook-structuring/ptk-structure-experiment")
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
import class_passive_combat as C
import pokemon_party as PARTY
import trainer_feature_acquisition as A
import state_codec as CODEC
import state_grants as G
import world_entities as W
import downtime as D
import test_category2_class_passive_combat_bulk as legacy


STATS = ("hp", "atk", "def", "spa", "spd", "spe")


class BookSpeciesSavantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="core")

    def setUp(self):
        self.e = Engine(self.rules, seed=126)
        self.t = self.trainer("family owner")

    def add(self, spec):
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, reason="actual Species Savant participant")
        return actor

    def trainer(self, name):
        return self.add(build_trainer(self.rules, name, 20, dict.fromkeys(STATS, 10),
            abilities=[], moves=[], extra={"feats": [], "edges": [], "exp_bank": 10}))

    def pokemon(self, species="디그다", *, owner=None, level=20):
        owner = self.t if owner is None else owner
        return self.add(build_pokemon(self.rules, species, level, abilities=[], moves=[],
            extra={"trainer_id": owner.entity_id}))

    def trio(self, species="디그다"):
        return [self.pokemon(species) for _ in range(3)]

    def acquire(self, trio, selected="디그다", request="species/book"):
        return C.acquire_species_savant(self.e, self.t, acquisition_request_id=request,
            selected_species=selected, prerequisite_ids=[p.entity_id if hasattr(p, "entity_id") else p for p in trio])

    def snapshot(self):
        return deepcopy(CODEC.dump_engine(self.e))

    def assert_bonus(self, pokemon, amount=1):
        self.assertEqual(pokemon.stats, {stat: pokemon.spec["stats"][stat] + amount for stat in STATS})

    def test_same_species_three_actual_entities_receive_six_stats_once(self):
        trio = self.trio(); outsider = self.pokemon("꼬부기")
        regional = [self.pokemon(name) for name in ("디그다 알로라", "닥트리오 알로라")]
        ordinary_family = C._species_family(trio[0], "pokemon/디그다")
        regional_family = C._species_family(regional[0], "pokemon/디그다-알로라")
        self.assertEqual(ordinary_family, sorted(("pokemon/디그다", "pokemon/닥트리오")))
        self.assertEqual(regional_family, sorted(("pokemon/디그다-알로라", "pokemon/닥트리오-알로라")))
        self.assertTrue(set(ordinary_family).isdisjoint(regional_family))
        receipt = self.acquire(trio)
        self.assertEqual(receipt["source"]["clause_id"], "C03-126")
        self.assertEqual(len({row["entity_id"] for row in receipt["selection"]["acquisition_snapshot"]["prerequisites"]}), 3)
        for pokemon in trio:
            self.assert_bonus(pokemon)
            self.e.register_abilities(pokemon)
            self.assert_bonus(pokemon)
            row = G.state(pokemon)["sources"][C._source_id(self.t, pokemon, C.SPECIES_SAVANT)]
            self.assertEqual((row["source_variant"], row["acquisition_receipt_id"]), ("C03-126", receipt["receipt_id"]))
        self.assert_bonus(outsider, 0)
        for pokemon in regional:
            self.assert_bonus(pokemon, 0)
        self.assertEqual(self.t.stats, self.t.spec["stats"])

    def test_eevee_branches_share_one_choice_independent_of_prerequisite_family(self):
        trio = self.trio()
        branches = [self.pokemon(name) for name in ("이브이", "샤미드", "쥬피썬더", "부스터", "에브이", "블래키", "리피아", "글레이시아", "님피아")]
        receipt = self.acquire(trio, selected="Eevee")
        for pokemon in branches:
            self.assert_bonus(pokemon)
        for pokemon in trio:
            self.assert_bonus(pokemon, 0)
        self.t.spec["class_passive_choices"] = {C.SPECIES_SAVANT: {"evolution_group": "invented-group"}}
        self.e.register_abilities(branches[0]); self.assert_bonus(branches[0])
        self.assertEqual(self.acquire(trio, selected="샤미드"), receipt)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "cannot change"):
            self.acquire(trio, selected="디그다")
        with self.assertRaisesRegex(ValueError, "reselect"):
            self.acquire(trio, selected="디그다", request="species/reselect")
        self.assertEqual(self.snapshot(), before)

    def test_registered_storage_individuals_count_without_fabricating_sheets(self):
        pokemon = self.pokemon()
        PARTY.configure(self.e, self.t, mode="standard", reason="actual owned storage", roster=[pokemon],
            storage={"kind": "center", "id": "species-center"})
        for uid in ("reserve/digda-one", "reserve/digda-two"):
            PARTY.register_reserve(self.e, self.t, pokemon_id=uid, species="Diglett", location="storage", reason="observed actual distinct stored Pokemon")
        receipt = self.acquire([pokemon, "reserve/digda-one", "reserve/digda-two"])
        self.assertEqual([row["basis"] for row in receipt["selection"]["acquisition_snapshot"]["prerequisites"]],
            ["actual_actor", "registered_reserve", "registered_reserve"])
        self.assert_bonus(pokemon)
        self.assertNotIn("reserve/digda-one", W.actor_index(self.e))

    def test_duplicate_foreign_and_history_only_evidence_cannot_acquire(self):
        trio = self.trio(); foreign_owner = self.trainer("other owner")
        foreign = self.pokemon(owner=foreign_owner)
        self.t.spec["caught_species"] = ["pokemon/디그다"]
        for evidence in ([trio[0], trio[0], trio[0]], [trio[0], trio[1], foreign],
                         [trio[0], trio[1], "history/digda"]):
            with self.subTest(evidence=evidence):
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.acquire(evidence)
                self.assertEqual(self.snapshot(), before)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "distinct actors share identity"):
            duplicate = Combatant(self.rules, deepcopy(trio[0].spec))
            W.actor_index(self.e, extra=(duplicate,))
        self.assertEqual(self.snapshot(), before)

    def test_mixed_family_denied_and_unknown_definition_pending_change_nothing(self):
        trio = self.trio(); outsider = self.pokemon("꼬부기")
        for evidence, selected, status in (([trio[0], trio[1], outsider], "디그다", "denied"),
                                           (trio, "unestablished-family", "pending")):
            before = self.snapshot()
            result = self.acquire(evidence, selected=selected)
            self.assertEqual((result["status"], result["acquired"]), (status, False))
            self.assertEqual(self.snapshot(), before)
        with patch.dict(self.rules.learnsets, {"디그다": dict(deepcopy(self.rules.learnsets["디그다"]), evolution=["unreviewed lineage"])}):
            result = self.acquire(trio)
            self.assertEqual((result["status"], result["acquired"]), ("pending", False))

    def test_json_fresh_rules_and_gm_restore_keep_selection_and_reject_tampering(self):
        trio = self.trio(); receipt = self.acquire(trio)
        payload = json.loads(json.dumps(self.snapshot(), ensure_ascii=False))
        fresh = Rules(ROOT, ruleset="core")
        loaded = CODEC.load_engine(fresh, payload)
        for pokemon in trio:
            self.assert_bonus(W.actor_index(loaded)[pokemon.entity_id])
        self.e.gm.snapshot("species")
        self.t.spec["class_passive_choices"] = {C.SPECIES_SAVANT: {"evolution_group": "other"}}
        self.e.gm.restore("species", reason="restore actual retained family")
        owner = W.actor_index(self.e)[self.t.entity_id]
        self.assertEqual(A.receipts(owner)[0], receipt)
        saved = deepcopy(owner.spec[A.LEDGER_KEY])
        owner.spec[A.LEDGER_KEY]["species/book"]["selection"]["values"] = ["pokemon/꼬부기"]
        with self.assertRaises(ValueError):
            A.validate_actor(owner)
        owner.spec[A.LEDGER_KEY] = saved
        A.validate_actor(owner)

    def test_native_level_growth_and_evolution_preserve_the_existing_stat_source(self):
        trio = self.trio("이상해씨"); pokemon = trio[0]
        self.acquire(trio, selected="이상해씨")
        D.gain_exp_combatant(self.e, pokemon, "to next level")
        self.assertEqual(pokemon.level, 21); self.assert_bonus(pokemon)
        self.assertTrue(D.evolve_combatant(self.e, pokemon, "이상해풀")["evolved"])
        self.assertEqual(pokemon.spec["species"], "pokemon/이상해풀")
        self.assert_bonus(pokemon)
        self.e.register_abilities(pokemon); self.assert_bonus(pokemon)

    def test_native_transfer_removes_former_owner_grants_and_applies_new_owner_family(self):
        trio = self.trio(); recipient = self.trainer("recipient")
        final_owner = self.trainer("unfeatured recipient")
        others = [self.pokemon(owner=recipient) for _ in range(3)]
        PARTY.configure(self.e, self.t, mode="standard", reason="actual owner roster", roster=trio,
            storage={"kind": "center", "id": "old-center"})
        PARTY.configure(self.e, recipient, mode="standard", reason="actual recipient roster", roster=others,
            storage={"kind": "center", "id": "new-center"})
        PARTY.configure(self.e, final_owner, mode="standard", reason="actual final recipient roster", roster=[],
            storage={"kind": "center", "id": "last-center"})
        self.acquire(trio)
        C.acquire_species_savant(self.e, recipient, acquisition_request_id="recipient/species", selected_species="닥트리오",
            prerequisite_ids=[p.entity_id for p in others])
        with self.subTest(failure="late receiving-owner stat grant"):
            before = self.snapshot()
            gm_before = deepcopy(self.e.rulings.log); rng_before = self.e.rng.getstate()
            receipts_before = deepcopy(getattr(self.e, "_world_relation_receipts", {}))
            original = G.stat
            def fail(pokemon, stat, *args, **kwargs):
                if pokemon.entity_id == trio[0].entity_id and stat == "spe":
                    raise RuntimeError("late receiving-owner stat grant")
                return original(pokemon, stat, *args, **kwargs)
            with patch.object(G, "stat", side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, "late receiving-owner"):
                    self.e.pokemon_activity(self.t, "party_transfer", target=trio[0], new_owner=recipient,
                        reason="actual ownership transfer", request_id="species/transfer")
            self.assertEqual(self.snapshot(), before)
            self.assertEqual((self.e.rulings.log, self.e.rng.getstate(), getattr(self.e, "_world_relation_receipts", {})),
                (gm_before, rng_before, receipts_before))
            self.assertIs(W.actor_index(self.e)[trio[0].entity_id], trio[0])
            self.assertEqual(trio[0].spec["trainer_id"], self.t.entity_id)
        result = self.e.pokemon_activity(self.t, "party_transfer", target=trio[0], new_owner=recipient,
            reason="actual ownership transfer", request_id="species/transfer")
        self.assertEqual(result["new_owner_id"], recipient.entity_id)
        self.assert_bonus(trio[0])
        self.assertNotIn(C._source_id(self.t, trio[0], C.SPECIES_SAVANT), G.state(trio[0])["sources"])
        self.assertIn(C._source_id(recipient, trio[0], C.SPECIES_SAVANT), G.state(trio[0])["sources"])
        for pokemon in trio[1:]:
            self.assert_bonus(pokemon)
        self.assertEqual(A.receipts(self.t)[0]["qualification"]["status"], "qualified")
        self.e.pokemon_activity(recipient, "party_transfer", target=trio[0], new_owner=final_owner,
            reason="actual transfer to unfeatured owner", request_id="species/transfer-again")
        self.assert_bonus(trio[0], 0)
        self.assertEqual(A.receipts(recipient)[0]["qualification"]["status"], "qualified")

    def test_retraining_retracts_only_own_bonus_and_preserves_historical_receipt(self):
        trio = self.trio(); self.acquire(trio)
        G._source(trio[0], "independent-stat", "gm_observation", tutor_points=0)
        G.stat(trio[0], "atk", 2, "independent-stat")
        before = trio[0].stats["atk"]
        self.e.retrain_trainer_source(self.t, C.SPECIES_SAVANT, request_id="species/withdraw",
            reason="actual retraining", gm_decision={"allowed": True, "reason": "GM reviewed actual Feature removal"},
            retained_dependencies={})
        self.assertEqual(trio[0].stats["atk"], before - 1)
        self.assertEqual(trio[0].stats["hp"], trio[0].spec["stats"]["hp"])
        self.assertEqual(A.receipts(self.t)[0]["state"], "withdrawn")
        self.assertNotIn(C.SPECIES_SAVANT, self.t.spec["feats"])
        self.assertEqual(self.t.spec[A.PROJECTION_KEY], {})
        self.assertTrue(W.validate_world(self.e)["valid"])

    def test_book_late_failure_rolls_back_acquisition_and_csv_projection_stays_separate(self):
        trio = self.trio(); before = self.snapshot(); original = G.stat
        def fail(pokemon, *args, **kwargs):
            if pokemon.entity_id == trio[-1].entity_id:
                raise RuntimeError("late actual Species Savant projection")
            return original(pokemon, *args, **kwargs)
        with patch.object(G, "stat", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "late actual"):
                self.acquire(trio)
        self.assertEqual(self.snapshot(), before)
        fixture = legacy.ClassPassiveCombatBulkTests(); fixture.rules = self.rules
        e, owner, pokemon, _ = fixture.fixture(feats=[C.SPECIES_SAVANT],
            choices={C.SPECIES_SAVANT: {"evolution_group": "pokemon/이상해씨"}})
        self.assert_bonus(pokemon)
        self.assertIsNone(C._species_book_receipt(owner))
        row = G.state(pokemon)["sources"][C._source_id(owner, pokemon, C.SPECIES_SAVANT)]
        self.assertEqual(row["clause_id"], "C2CSV/input/db/feats.csv:R7:main")
        self.assertNotIn("source_variant", row)


if __name__ == "__main__":
    unittest.main(verbosity=2)
