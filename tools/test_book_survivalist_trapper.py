"""Trapper (ch04:2156-2164): daily consumable tools, same-day deployment, eight adjacent Hazard metres,
foe collision effects by creation terrain, Naturewalk immunity, destruction after resolution and restores."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import common_checks as C
import frequency as FREQ
import hazard_state as H
import state_grants as G
import survivalist_class as SC

WALL = tuple((5, y) for y in range(8))


class SurvivalistTrapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        SC.definitions(self.rules)

    def rejected(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def create(self, engine, trainer, tool_id, terrain, **changes):
        options = dict(tool_id=tool_id, terrain_name=terrain, minutes=30, reason='GM observed the actual crafting time')
        options.update(changes)
        return engine.survivalist_activity(trainer, 'create_trap_tool', **options)

    def deploy(self, engine, trainer, tool_id, cells=WALL, **changes):
        options = dict(tool_id=tool_id, cells=list(cells), reason='actual deployment in front of the foe')
        options.update(changes)
        return engine.survivalist_activity(trainer, 'deploy_trap_tool', **options)

    def instances(self, engine):
        return [row for envelope in engine.hazards.values() for row in envelope['instances']]

    def test_tool_creation_is_a_daily_twice_extended_action_bound_to_the_actual_terrain(self):
        world = FIX.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        self.rejected(engine, lambda: self.create(engine, trainer, 'dust-1', 'grassland'), 'GM current environment|actual current terrain')
        FIX.env(engine, trainer, 'grassland', 'forest')
        self.rejected(engine, lambda: self.create(engine, trainer, 'slick-1', 'ocean'), 'actual current terrain')
        self.rejected(engine, lambda: self.create(engine, trainer, 'dust-1', 'grassland', minutes=0), 'minutes')
        before = engine.elapsed_seconds
        first = self.create(engine, trainer, 'dust-1', 'grassland')
        self.assertEqual((first['kind'], first['terrain'], first['status'], first['used'], first['created_day']), ('dust', 'grassland', 'ready', None, FREQ.state(trainer)['day']))
        self.assertEqual(engine.elapsed_seconds - before, 1800)
        self.assertEqual(trainer._action_history, ['extended'])
        self.assertEqual(first['frequency'], {'kind': 'daily', 'period': FREQ.state(trainer)['day'], 'used': 1})
        self.rejected(engine, lambda: self.create(engine, trainer, 'dust-1', 'forest'), 'duplicate Trapper tool identity')
        second = self.create(engine, trainer, 'tangle-1', 'forest')
        self.assertEqual((second['kind'], second['frequency']['used']), ('tangle', 2))
        self.rejected(engine, lambda: self.create(engine, trainer, 'dust-2', 'grassland'), 'daily frequency exhausted')
        self.assertEqual([row['id'] for row in trainer.spec[SC.TOOLS]], ['dust-1', 'tangle-1'])
        engine.gm.set_skill(trainer, '생존', 3, reason='actual lost Adept Survival')
        self.rejected(engine, lambda: self.create(engine, trainer, 'dust-3', 'grassland'), 'prerequisite not met')
        engine.gm.set_skill(trainer, '생존', 6, reason='actual Master Survival')
        FREQ.new_day(trainer)
        third = self.create(engine, trainer, 'dust-3', 'grassland')
        self.assertEqual(third['frequency']['used'], 1)
        self.assertTrue(engine.validate_state()['valid'])
        other = world['partner']
        self.rejected(engine, lambda: self.create(engine, other, 'p-1', 'grassland'), 'conscious trainer|acquired source')

    def test_deployment_needs_the_gm_action_ruling_same_day_encounter_and_eight_adjacent_metres_within_six(self):
        world = FIX.scene(self.rules)
        engine, trainer, foe = world['engine'], world['trainer'], world['foe']
        FIX.env(engine, trainer, 'grassland')
        self.create(engine, trainer, 'dust-1', 'grassland')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1'), 'actual encounter')
        FIX.battle(engine, trainer)
        pending = self.deploy(engine, trainer, 'dust-1')
        self.assertIsInstance(pending, C.PendingDecision)
        self.assertIn(SC.DEPLOY_RULING, pending.required)
        self.assertEqual((trainer.budget['standard'], engine.hazards), (1, {}))
        FIX.ruling(engine, SC.DEPLOY_RULING, 'shift')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1'), 'standard, swift, free')
        FIX.ruling(engine, SC.DEPLOY_RULING, 'standard')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'missing'), 'actual owned Trapper tool')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1', cells=WALL[:7]), 'exactly 8 distinct metres')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1', cells=WALL[:7] + ((5, 0),)), 'exactly 8 distinct metres')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1', cells=WALL[:7] + ((9, 7),)), 'outside 6 metres')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1', cells=WALL[:6] + ((7, 0), (7, 7))), 'adjacent to another')
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1', cells=WALL[:7] + ((5, 9),)), 'outside the map')
        used = self.deploy(engine, trainer, 'dust-1')
        self.assertEqual((used['status'], used['used']['action'], used['used']['round'], used['used']['ruling']), ('used', 'standard', engine.round_no, SC.DEPLOY_RULING))
        self.assertEqual(trainer.budget['standard'], 0)
        rows = self.instances(engine)
        self.assertEqual(len(rows), 8)
        self.assertEqual({(row['kind'], row['name'], row['source_id'], row['owner_side'], row['region_id'], row['clause_id']) for row in rows},
                         {(SC.TRAP_KIND, '더스트 트랩', SC.TRAPPER + '#dust#grassland', 'party', used['used']['region_id'], 'input/ch04-trainer-classes.md:2156-2164')})
        self.assertEqual(sorted(tuple(c) for c in used['used']['cells']), sorted(WALL))
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-1'), 'already used')
        self.assertTrue(engine.validate_state()['valid'])
        FIX.next_turn(engine, trainer, foe, count=10)
        engine.end_of_turn(foe)
        engine.end_round()
        engine.end_encounter()
        self.assertEqual(engine.hazards, {})
        self.create(engine, trainer, 'dust-2', 'grassland')
        FREQ.new_day(trainer)
        FIX.battle(engine, trainer)
        self.rejected(engine, lambda: self.deploy(engine, trainer, 'dust-2'), 'lost all effect')
        self.assertTrue(engine.validate_state()['valid'])

    def test_foe_collision_slows_until_its_next_turn_adds_the_terrain_effect_and_destroys_that_metre(self):
        expectations = {
            'grassland': ('dust', {'둔화', '실명'}, {}),
            'forest': ('tangle', {'구속'}, {}),
            'ocean': ('slick', {'둔화', '취약'}, {}),
            'cave': ('abrasion', {'둔화'}, {'def': -1, 'spd': -1}),
        }
        for terrain, (kind, statuses, stages) in expectations.items():
            with self.subTest(terrain=terrain):
                world = FIX.scene(self.rules)
                engine, trainer, foe = world['engine'], world['trainer'], world['foe']
                FIX.env(engine, trainer, terrain)
                self.create(engine, trainer, 'tool', terrain)
                FIX.ruling(engine, SC.DEPLOY_RULING, 'standard')
                FIX.battle(engine, trainer)
                self.deploy(engine, trainer, 'tool')
                self.assertEqual(self.instances(engine)[0]['name'], SC.TRAPS[kind]['korean'])
                FIX.next_turn(engine, trainer, foe, count=10)
                before = {stat: foe.stages[stat] for stat in ('def', 'spd')}
                engine.approach(foe, trainer)
                self.assertTrue(statuses <= foe.conditions, foe.conditions)
                if kind == 'tangle':
                    self.assertNotIn('둔화', foe.conditions)
                    self.assertEqual(foe.pos[0], 5)
                else:
                    self.assertLess(foe.pos[0], 5)
                for stat, delta in stages.items():
                    self.assertEqual(foe.stages[stat], before[stat] + delta)
                remaining = self.instances(engine)
                self.assertEqual(len(remaining), 7)
                self.assertTrue({row['cell'] for row in remaining} < set(WALL))
                if kind == 'tangle':
                    self.assertNotIn(foe.pos, [row['cell'] for row in remaining])
                self.assertTrue(any(SC.TRAPS[kind]['korean'] + ' 발동 후 파괴' in line for line in engine.log_lines))
                engine.end_of_turn(foe)
                self.assertTrue(statuses <= foe.conditions)
                engine.end_round()
                engine.start_round(engine.everyone)
                engine.start_of_turn(trainer, initiative_count=20)
                FIX.next_turn(engine, trainer, foe, count=10)
                engine.end_of_turn(foe)
                self.assertFalse(statuses & foe.conditions, foe.conditions)
                self.assertTrue(engine.validate_state()['valid'])

    def test_naturewalk_for_the_creation_terrain_is_immune_and_allies_never_trigger(self):
        world = FIX.scene(self.rules)
        engine, trainer, partner, foe = world['engine'], world['trainer'], world['partner'], world['foe']
        FIX.env(engine, trainer, 'grassland')
        self.create(engine, trainer, 'tool', 'grassland')
        FIX.ruling(engine, SC.DEPLOY_RULING, 'standard')
        FIX.battle(engine, trainer)
        self.deploy(engine, trainer, 'tool')
        G.grant(foe, 'capabilities', 'Naturewalk(초원)', 'fixture:naturewalk', 'fixture')
        FIX.next_turn(engine, trainer, foe, count=15)
        engine.approach(foe, trainer)
        self.assertLess(foe.pos[0], 5)
        self.assertFalse({'둔화', '실명'} & foe.conditions)
        self.assertEqual(len(self.instances(engine)), 8)
        self.assertTrue(any('자연걸음으로 더스트 트랩 효과 면역' in line for line in engine.log_lines))
        G.revoke(foe, 'fixture:naturewalk')
        G.grant(foe, 'capabilities', 'Naturewalk(사막)', 'fixture:naturewalk', 'fixture')
        engine.gm.set_position(foe, (8, 4), reason='GM repositions the foe east of the wall')
        FIX.next_turn(engine, foe, partner, count=10)
        engine.gm.set_position(partner, (7, 6), reason='own Pokemon starts east of the wall')
        engine.approach(partner, trainer)
        self.assertLess(partner.pos[0], 5)
        self.assertFalse({'둔화', '실명'} & partner.conditions)
        self.assertEqual(len(self.instances(engine)), 8)
        engine.end_of_turn(partner)
        engine.end_round()
        engine.start_round(engine.everyone)
        engine.start_of_turn(foe, initiative_count=10)
        engine.approach(foe, trainer)
        self.assertTrue({'둔화', '실명'} <= foe.conditions)
        self.assertEqual(len(self.instances(engine)), 7)
        self.assertTrue(engine.validate_state()['valid'])

    def test_json_and_gm_restores_keep_tools_hazards_and_receipts_and_tampering_is_rejected(self):
        world = FIX.scene(self.rules)
        engine, trainer, foe = world['engine'], world['trainer'], world['foe']
        FIX.env(engine, trainer, 'ocean')
        self.create(engine, trainer, 'slick-1', 'ocean')
        self.create(engine, trainer, 'slick-2', 'ocean')
        FIX.ruling(engine, SC.DEPLOY_RULING, 'swift')
        FIX.battle(engine, trainer)
        used = self.deploy(engine, trainer, 'slick-1')
        self.assertEqual((trainer.budget['swift'], trainer.budget['standard']), (0, 1))
        tools = deepcopy(trainer.spec[SC.TOOLS])
        engine.gm.snapshot('deployed')
        loaded, index = FIX.restore(self.rules, engine)
        again = index[trainer.entity_id]
        self.assertEqual(again.spec[SC.TOOLS], tools)
        self.assertEqual(len([row for envelope in loaded.hazards.values() for row in envelope['instances']]), 8)
        self.assertEqual({row['source_id'] for envelope in loaded.hazards.values() for row in envelope['instances']}, {SC.TRAPPER + '#slick#ocean'})
        self.assertTrue(loaded.validate_state()['valid'])
        self.rejected(loaded, lambda: loaded.survivalist_activity(again, 'deploy_trap_tool', tool_id='slick-1', cells=list(WALL), reason='again'), 'already used')
        trainer.spec[SC.TOOLS][0]['kind'] = 'dust'
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('deployed')
        self.assertEqual(trainer.spec[SC.TOOLS], tools)
        self.assertTrue(engine.validate_state()['valid'])
        trainer.spec[SC.TOOLS][1]['status'] = 'used'
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('deployed')
        self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
