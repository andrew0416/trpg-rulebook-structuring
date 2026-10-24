"""ERRATA-095: inherited Blindness disadvantages use actual current sight."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
import book_survivalist_fixture as SURVIVAL_FIXTURE
import state_codec as CODEC
import survivalist_class as SURVIVAL_CLASS
import survivalist_features as SURVIVAL
import vision_impairment as VISION

TACKLE = 'move/몸통박치기'
CHANNELS = ('물리', '특수', '변화')


class TotalBlindnessEvasionSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def scene(self, role, *, capabilities=()):
        engine = Engine(self.rules, seed=95)
        engine.grid = Grid(12, 8)
        stats = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20)
        owner = Combatant(self.rules, build_trainer(
            self.rules, 'actual defending trainer', 20, stats, abilities=[],
            extra={'moves': [], 'capabilities': list(capabilities),
                   'side': 'party', 'pos': (2, 2)}))
        engine.gm.add_combatant(owner, reason='actual native trainer enters the encounter')
        defender = owner
        if role == 'pokemon':
            owner.pos = (0, 0)
            defender = Combatant(self.rules, build_pokemon(
                self.rules, '이브이', 20, abilities=[], moves=[],
                extra={'trainer_id': owner.entity_id, 'capabilities': list(capabilities),
                       'side': 'party', 'pos': (2, 2)}))
            engine.gm.add_combatant(defender, reason='actual owned Pokemon enters the encounter')
            engine.gm.observe_loyalty(defender, 6, reason='actual current trainer relationship')
        attacker = Combatant(self.rules, build_trainer(
            self.rules, 'actual attacking trainer', 20, stats, abilities=[],
            extra={'moves': [TACKLE], 'side': 'opponent', 'pos': (3, 2)}))
        engine.gm.add_combatant(attacker, reason='actual native opposing trainer')
        for stat, value in [('hp', 40), ('def', 15), ('spd', 25), ('spe', 30)]:
            engine.gm.set_stat(defender, stat, value, reason='observed current stat for distinct evasion channels')
        engine.gm.set_hp(defender, value=defender.max_hp, reason='actual healthy defender before the attack')
        engine.gm.set_stage(defender, 'eva', 2, reason='actual independent positive evasion modifier')
        engine.start_round(engine.everyone)
        engine.start_of_turn(attacker, initiative_count=20)
        return engine, defender, attacker

    def evasion(self, engine, actor):
        return tuple(actor.evasion(channel, engine=engine) for channel in CHANNELS)

    def attack_hits(self, engine, attacker, defender):
        move = engine.r.move(TACKLE)
        return engine.accuracy_check(attacker, defender, move, fixed_roll=move['ac'] + 1)[0]

    def observe(self, engine, actor, light):
        return SURVIVAL.observe_environment(
            engine, actor, terrains=['urban'], light=light,
            reason='GM observes the actual current illumination around this defender')

    def restored(self, engine, defender, attacker):
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(
            CODEC.dump_engine(engine), ensure_ascii=False)))
        index = {actor.entity_id: actor for actor in loaded.everyone}
        return loaded, index[defender.entity_id], index[attacker.entity_id]

    def test_actual_total_blindness_aliases_remove_all_evasion_before_native_attack(self):
        for role in ('trainer', 'pokemon'):
            for condition in ('완전 실명', '완전-실명'):
                with self.subTest(role=role, condition=condition):
                    engine, defender, attacker = self.scene(role)
                    self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                    self.assertFalse(self.attack_hits(engine, attacker, defender))
                    self.assertTrue(engine.apply_status(
                        defender, condition, parameters={'cause': 'external'}))
                    self.assertIn(VISION.TOTAL, defender.conditions)
                    self.assertNotIn('취약', defender.conditions)
                    self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
                    self.assertEqual(tuple(defender.evasion(c) for c in CHANNELS), (0, 0, 0))
                    self.assertEqual(defender.evasion('물리', engine=engine,
                                     conditional_bonus=4, ignore_stats=True), 0)
                    self.assertTrue(self.attack_hits(engine, attacker, defender))
                    hp = defender.hp
                    with patch.object(engine, 'd20', return_value=engine.r.move(TACKLE)['ac'] + 1) as roll:
                        dealt = engine.use_move(attacker, defender, TACKLE, set_damage=True)
                    roll.assert_called_once()
                    self.assertGreater(dealt, 0)
                    self.assertEqual(defender.hp, hp - dealt)
                    self.assertEqual(attacker.budget['standard'], 0)
                    self.assertEqual(attacker.move_uses[TACKLE], 1)

    def test_actual_cure_and_both_restores_keep_real_evasion_sources(self):
        for role in ('trainer', 'pokemon'):
            for condition in ('실명', '완전 실명'):
                for restoration in ('gm', 'json'):
                    with self.subTest(role=role, condition=condition, restoration=restoration):
                        engine, defender, attacker = self.scene(role)
                        sources = deepcopy((defender.stats, defender.stages, defender.evasion_mod))
                        engine.apply_status(defender, condition, parameters={'cause': 'external'})
                        self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
                        self.assertTrue(self.attack_hits(engine, attacker, defender))
                        if restoration == 'gm':
                            engine.gm.snapshot('actually blinded defender')
                            engine.cure_status(defender, condition)
                            self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                            engine.gm.restore('actually blinded defender')
                        else:
                            engine, defender, attacker = self.restored(engine, defender, attacker)
                        self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
                        self.assertEqual((defender.stats, defender.stages, defender.evasion_mod), sources)
                        self.assertNotIn('취약', defender.conditions)
                        engine.cure_status(defender, condition)
                        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                        self.assertFalse(self.attack_hits(engine, attacker, defender))
                        self.assertEqual((defender.stats, defender.stages, defender.evasion_mod), sources)
                        engine.gm.add_condition(defender, '구속', reason='ordinary control blocks only Speed Evasion')
                        self.assertEqual(self.evasion(engine, defender), (5, 7, 2))
                        engine.gm.remove_condition(defender, '구속', reason='actual release restores existing sources')
                        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))

    def test_actual_observed_darkness_has_no_stored_affliction_and_recovers_in_light(self):
        for role in ('trainer', 'pokemon'):
            for light, expected in [('low_light', 'ordinary'), ('complete_darkness', 'total')]:
                for restoration in ('gm', 'json'):
                    with self.subTest(role=role, light=light, restoration=restoration):
                        engine, defender, attacker = self.scene(role)
                        conditions = set(defender.conditions)
                        self.observe(engine, defender, light)
                        self.assertEqual(VISION.accuracy_level(engine, defender), expected)
                        self.assertEqual(defender.conditions, conditions)
                        self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
                        # Without the actual Engine, environmental sight is not available.
                        self.assertEqual(tuple(defender.evasion(c) for c in CHANNELS), (8, 8, 8))
                        self.assertTrue(self.attack_hits(engine, attacker, defender))
                        if restoration == 'gm':
                            engine.gm.snapshot('observed actual darkness')
                            self.observe(engine, defender, 'normal')
                            self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                            engine.gm.restore('observed actual darkness')
                        else:
                            engine, defender, attacker = self.restored(engine, defender, attacker)
                        self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
                        self.observe(engine, defender, 'normal')
                        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                        self.assertFalse(self.attack_hits(engine, attacker, defender))
                        self.assertEqual(defender.conditions, conditions)

    def test_native_senses_preserve_darkness_and_external_affliction_distinctions(self):
        for role in ('trainer', 'pokemon'):
            for capability in ('Blindsense', 'Darkvision'):
                with self.subTest(role=role, capability=capability):
                    engine, defender, attacker = self.scene(role, capabilities=[capability])
                    self.observe(engine, defender, 'complete_darkness')
                    self.assertEqual(VISION.accuracy_level(engine, defender), 'none')
                    self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                    self.assertFalse(self.attack_hits(engine, attacker, defender))
                    self.assertFalse(engine.apply_status(
                        defender, '완전 실명', parameters={'cause': 'darkness'}))
                    applied = engine.apply_status(defender, '완전 실명', parameters={'cause': 'external'})
                    self.assertEqual(applied, capability == 'Darkvision')
                    self.assertEqual(self.evasion(engine, defender),
                                     (0, 0, 0) if applied else (8, 8, 8))
                    if applied:
                        engine.cure_status(defender, '완전 실명')
                    self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
                    self.observe(engine, defender, 'normal')
                    self.assertEqual(self.evasion(engine, defender), (8, 8, 8))

    def test_actual_cave_dweller_keeps_low_light_exemption_and_total_downgrade(self):
        SURVIVAL_CLASS.definitions(self.rules)
        world = SURVIVAL_FIXTURE.scene(self.rules)
        engine, defender = world['engine'], world['trainer']
        for terrain in ('cave', 'forest'):
            SURVIVAL_FIXTURE.master(engine, defender, terrain)
        SURVIVAL_FIXTURE.talents(engine, defender, 'cave', 'forest')
        engine.gm.set_stat(defender, 'spe', 30, reason='observed current Speed Evasion source')
        engine.gm.set_stage(defender, 'eva', 2, reason='actual independent evasion modifier')
        SURVIVAL_FIXTURE.env(engine, defender, 'urban', light='low_light')
        self.assertEqual(VISION.accuracy_level(engine, defender), 'none')
        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
        SURVIVAL_FIXTURE.env(engine, defender, 'urban', light='complete_darkness')
        self.assertEqual(SURVIVAL.vision(engine, defender), ('ordinary', True))
        self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
        engine.apply_status(defender, '완전 실명', parameters={'cause': 'external'})
        self.assertEqual(VISION.accuracy_level(engine, defender), 'total')
        self.assertEqual(self.evasion(engine, defender), (0, 0, 0))
        engine.cure_status(defender, '완전 실명')
        self.assertEqual(VISION.accuracy_level(engine, defender), 'ordinary')
        SURVIVAL_FIXTURE.env(engine, defender, 'urban', light='normal')
        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))

    def test_mapped_unlit_distance_alone_never_fabricates_blindness_or_zero_evasion(self):
        engine, defender, attacker = self.scene('trainer')
        engine.configure_scene_lighting(darkness=True, reason='actual mapped ordinary darkness')
        projection = engine.scene_light_projection(defender, attacker)
        self.assertGreater(projection['unlit_meters'], 0)
        self.assertLess(projection['penalty'], 0)
        self.assertEqual(VISION.accuracy_level(engine, defender), 'none')
        self.assertEqual(VISION.accuracy_penalty(engine, defender, attacker), projection['penalty'])
        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
        engine.observe_scene_light('held-lantern', kind='lantern', owner=defender,
                                   reason='actual held lit lantern illuminates the adjacent actor')
        self.assertEqual(engine.scene_light_projection(defender, attacker)['penalty'], 0)
        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
        engine.remove_scene_light('held-lantern', reason='actual lantern is removed')
        self.assertLess(engine.scene_light_projection(defender, attacker)['penalty'], 0)
        self.assertEqual(self.evasion(engine, defender), (8, 8, 8))
        self.assertNotIn('실명', defender.conditions)
        self.assertNotIn('완전-실명', defender.conditions)
        self.assertNotIn('취약', defender.conditions)


if __name__ == '__main__':
    unittest.main()
