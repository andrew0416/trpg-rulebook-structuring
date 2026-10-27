"""Direct producer/consumer boundaries for the selected G045 and G050 rows."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
CANON = STAGE if (STAGE / "input").exists() else Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(STAGE / "engine"), str(CANON / "engine"), str(CANON / "tools")]

from engine import Combatant, Engine, Rules
from grid import Grid
from builder import build_pokemon, build_trainer
# Keep the staged import path without replacing owners already held by other fixtures.
sys.path.insert(0, str(STAGE / "engine"))
import campaign_rewards as CAMPAIGN
import encounter_settlement as SETTLEMENT
import environmental_effects as ENVIRONMENT
import movement_actions as MOVEMENT
import nicolette_gym as NICOLETTE
import training_features as TRAINING
import turn as TURN
import body_state as BODY
import test_category2_training_state as training_fixture


STATS = dict(hp=30, atk=10, **{"def": 10}, spa=10, spd=10, spe=10)


def trainer(rules, name, money=0):
    return Combatant(rules, build_trainer(
        rules, name, 20, STATS, moves=[],
        extra={"money": money, "items": {}, "skills": {"육상": 3, "곡예": 3}}))


def pokemon(rules, owner, name, *, pos=(0, 0), weight=2, types=None, movement=6):
    spec = build_pokemon(
        rules, "브케인", 10, name=name, moves=[], abilities=[], pos=pos,
        extra={"trainer_id": owner.entity_id, "trainer": owner.name,
               "weight_class": weight, "types": list(types or ()),
               "movement": {"land": movement}, "movement_basis": "current",
               "skills": {"육상": "2d6+1", "곡예": "2d6+1"}})
    return Combatant(rules, spec)


class EncounterSettlementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(CANON), ruleset="core")

    def setUp(self):
        self.e = Engine(self.r, 313)
        self.a = trainer(self.r, "rewarded-a", 500)
        self.b = trainer(self.r, "rewarded-b", 500)
        self.p = pokemon(self.r, self.a, "participant-a1")
        self.fainted = pokemon(self.r, self.a, "participant-a2")
        self.q = pokemon(self.r, self.b, "participant-b1")
        self.reserve = pokemon(self.r, self.a, "unused-reserve")
        self.fainted.hp = 0
        self.fainted.conditions.add("기절")
        self.e.everyone = self.e.gm.everyone = [
            self.a, self.b, self.p, self.fainted, self.q, self.reserve]

    def observe(self, identity="ordinary-battle"):
        return SETTLEMENT.observe(
            self.e, encounter_id=identity,
            rewarded_trainers=[self.a, self.b],
            participating_pokemon={
                self.a.entity_id: [self.p, self.fainted],
                self.b.entity_id: [self.q]},
            winner=self.b, defeated_levels=[10, 10], significance=2,
            challenge=1, reason="actual completed ordinary battle")

    def test_player_count_share_then_any_ratio_actual_participants_including_fainted(self):
        row = self.observe()
        self.assertEqual((row["xp_detail"]["players"], row["xp_share"]), (2, 20))
        before = deepcopy((self.p.spec, self.fainted.spec, self.reserve.spec))
        with self.assertRaises(ValueError):
            SETTLEMENT.allocate_pokemon_xp(
                self.e, encounter_id="ordinary-battle", trainer=self.a,
                allocations={self.reserve.entity_id: 20})
        self.assertEqual(before, (self.p.spec, self.fainted.spec, self.reserve.spec))
        old = self.fainted.spec["exp"]
        receipt = SETTLEMENT.allocate_pokemon_xp(
            self.e, encounter_id="ordinary-battle", trainer=self.a,
            allocations={self.fainted.entity_id: 20})
        self.assertEqual(receipt["allocations"], {self.fainted.entity_id: 20})
        self.assertEqual(self.fainted.spec["exp"], old + 20)
        self.assertTrue(self.fainted.fainted)
        with self.assertRaises(ValueError):
            SETTLEMENT.allocate_pokemon_xp(
                self.e, encounter_id="ordinary-battle", trainer=self.a,
                allocations={self.p.entity_id: 20})

    def test_same_observed_winner_consumes_both_preexisting_wager_stakes(self):
        CAMPAIGN.wager(
            self.e, self.a, event_id="ordinary-wager", opponent=self.b,
            stakes={self.a.entity_id: 100, self.b.entity_id: 150},
            consents={self.a.entity_id: True, self.b.entity_id: True},
            reason="both actual trainers agree before battle")
        self.assertEqual((self.a.spec["money"], self.b.spec["money"]), (400, 350))
        self.observe()
        result = SETTLEMENT.settle_wager(
            self.e, encounter_id="ordinary-battle", wager_id="ordinary-wager", actor=self.a)
        self.assertEqual(result, {"status": "paid", "winner": self.b.entity_id, "payout": 250})
        self.assertEqual((self.a.spec["money"], self.b.spec["money"]), (400, 600))
        with self.assertRaises(ValueError):
            SETTLEMENT.settle_wager(
                self.e, encounter_id="ordinary-battle", wager_id="ordinary-wager", actor=self.a)


class NicoletteTerrainTests(unittest.TestCase):
    setUpClass = classmethod(training_fixture.TrainingStateTests.setUpClass.__func__)
    setUp = training_fixture.TrainingStateTests.setUp

    def configure(self):
        self.e.grid = Grid(12, 12)
        return NICOLETTE.configure(
            self.e,
            heights={(1, 1): 0, (1, 2): 3,
                     (2, 1): 0, (2, 2): 3,
                     (3, 1): 0, (3, 2): 6},
            ladder_links=[((3, 1), (3, 2))],
            snow_cells=[(4, 1)], brush_cells=[(5, 1)], ice_cells=[(6, 1), (6, 2)],
            pc_deploy_cells=[(10, 9), (10, 10)], gym_deploy_cells=[(1, 9), (1, 10)],
            nicolette_cell=(2, 9), reason="GM adopts the printed Nicolette sample map")

    def test_height_routes_and_special_training_use_native_movement_consumers(self):
        self.configure()
        # The ordinary Training Feature is an independent live source and must
        # still contribute after the scenario-specific terrain training.
        self.e.train_pokemon(
            self.t, [(self.ps[0], [TRAINING.AGILITY])], minutes=30,
            reason="actual agility training", request_id="nicolette-agility", safe=True)
        NICOLETTE.train_team(self.e, self.t, [self.ps[0]])
        self.assertTrue(MOVEMENT.ordinary_terrain(self.e, self.ps[0], (4, 1)))
        self.assertTrue(MOVEMENT.ordinary_terrain(self.e, self.ps[0], (6, 1)))
        self.assertFalse(MOVEMENT.ordinary_terrain(self.e, self.ps[0], (5, 1)))
        self.assertEqual(MOVEMENT.capabilities(self.e, self.ps[0])["land"], 7)
        self.ps[0].pos, self.ps[1].pos, self.ps[2].pos = (1, 1), (2, 1), (3, 1)
        for actor in (self.t, self.ps[3], self.enemy):
            actor.on_field = False
        for actor in self.ps[:3]:
            BODY.observe(self.e, actor, [(0, 0)], reason="actual one-cell mapped body")
        self.e.start_round([self.ps[0], self.ps[1], self.ps[2]])
        self.e.start_of_turn(self.ps[0])
        wall = NICOLETTE.climb(
            self.e, self.ps[0], (1, 2), climb_id="wall-trained",
            route="cliff", reason="trained sample-team wall climb")
        self.assertTrue(wall["passed"])
        self.assertEqual(wall["cost"], 6)
        self.e.end_of_turn(self.ps[0])
        self.e.start_of_turn(self.ps[1])
        checked = NICOLETTE.climb(
            self.e, self.ps[1], (2, 2), climb_id="direct-dc12",
            route="cliff", skill="육상", fixed=[6, 6],
            reason="direct three metre cliff attempt")
        self.assertEqual((checked["dc"], checked["passed"]), (12, True))
        self.e.end_of_turn(self.ps[1])
        self.e.start_of_turn(self.ps[2])
        ladder = NICOLETTE.climb(
            self.e, self.ps[2], (3, 2), climb_id="land-ladder",
            route="ladder", reason="observed ladder counts as land movement")
        self.assertEqual((ladder["rise"], ladder["cost"], ladder["skill"]), (6, 6, None))

    def _ice_engine(self, *, weight, position, identity, types=()):
        e = Engine(self.r, 700 + weight)
        owner = trainer(self.r, "ice-owner-" + identity)
        actor = pokemon(self.r, owner, identity, pos=position, weight=weight, types=types)
        e.everyone = e.gm.everyone = [owner, actor]
        e.grid = Grid(10, 10)
        NICOLETTE.configure(
            e, heights={(0, 1): 0, (1, 1): 0, (1, 2): 0},
            ladder_links=[], snow_cells=[(3, 1)], brush_cells=[(4, 1)],
            ice_cells=[(1, 1), (1, 2)], pc_deploy_cells=[(8, 8)],
            gym_deploy_cells=[(1, 8)], nicolette_cell=(2, 8),
            reason="GM adopts frozen-river boundary fixture")
        return e, actor

    def test_ice_break_thresholds_and_cold_water_turn_end_are_connected(self):
        e, actor = self._ice_engine(weight=5, position=(0, 1), identity="walker")
        e.start_round([actor])
        e.start_of_turn(actor)
        self.assertTrue(TURN.spend(e, actor, "shift", "walk onto frozen river", movement=True))
        moved = MOVEMENT.follow_paid_path(e, actor, [(1, 1)], mode="land", maximum_distance=6)
        self.assertEqual((moved["steps"], actor.pos), (1, (1, 1)))
        self.assertIn([1, 1], NICOLETTE.state(e, required=True)["broken_ice"])
        before = actor.stages["spe"]
        e.end_of_turn(actor)
        self.assertEqual(actor.stages["spe"], before - 1)

        e2, faller = self._ice_engine(weight=3, position=(1, 2), identity="faller")
        e2.falling_damage(
            faller, action_id="ice-fall", meters=1, intentional=False,
            reason="actual fall onto frozen river", fixed_damage=[1])
        self.assertIn([1, 2], NICOLETTE.state(e2, required=True)["broken_ice"])

        e3, light = self._ice_engine(weight=2, position=(1, 2), identity="light-faller")
        e3.falling_damage(
            light, action_id="light-ice-fall", meters=1, intentional=False,
            reason="actual light fall onto frozen river", fixed_damage=[1])
        self.assertNotIn([1, 2], NICOLETTE.state(e3, required=True)["broken_ice"])

    def test_deployment_zones_exclude_nicolette_from_actual_combat_participants(self):
        self.configure()
        pc = self.ps[0]
        gym = self.ps[1]
        gym.spec["trainer_id"] = self.t.entity_id
        result = NICOLETTE.deploy(
            self.e, pcs=[pc], gym_pokemon=[gym], nicolette=self.t,
            pc_positions=[(10, 9)], gym_positions=[(1, 9)],
            reason="actual right-sign and left-bridge deployment")
        self.assertEqual(set(result["participant_ids"]), {pc.entity_id, gym.entity_id})
        self.assertNotIn(self.t.entity_id, result["participant_ids"])
        self.assertFalse(self.t.on_field)
        self.assertTrue(self.e.encounter_active)
        self.assertEqual((pc.pos, gym.pos, self.t.pos), ((10, 9), (1, 9), (2, 9)))


if __name__ == "__main__":
    unittest.main()
