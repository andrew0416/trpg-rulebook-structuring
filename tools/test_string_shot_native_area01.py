"""String Shot uses exact selected effects and each actual native cone hit once."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import effects as FX
import move_completion as MC
import state_codec as CODEC
import world_entities as WORLD
from native_scenario_fixture import prepare_scene, assert_rejected_unchanged

MOVE = 'move/실뿜기'


class StringShotNativeAreaTests(unittest.TestCase):
    def scene(self):
        placements = [('a', (2, 2), 'party'), ('b', (3, 2), 'foe'),
                      ('c', (4, 2), 'foe'), ('outside', (2, 4), 'foe')]
        rows = [
            dict(key=key, kind='trainer',
                 sheet=dict(name=key, level=20,
                            stats=dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
                            moves=[MOVE] if key == 'a' else ['move/몸통박치기'],
                            abilities=[], pos=position, side=side),
                 body=dict(size='중형', offsets=[(0, 0)], reason='actual String Shot cone participant'))
            for key, position, side in placements]
        self.e, actors = prepare_scene(ROOT, ruleset='core', seed=31,
            grid={'width': 9, 'height': 9}, actors=rows)
        for name, actor in actors.items():
            setattr(self, name, actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a)

    def native(self, face=10, everyone=None):
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(self.a, self.b, MOVE,
                self.e.everyone if everyone is None else everyone, aim=(3, 2))

    def completion(self):
        rows = [row for row in self.e._move_completions.values()
                if row['actor'] is self.a and row['move_id'] == MOVE]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['phase'], 'complete')
        return rows[0]

    def valid(self):
        report = self.e.validate_state()
        self.assertTrue(report['valid'], report['issues'])

    def test_actual_cone_hits_each_recipient_once_and_preserves_outside_target(self):
        self.scene()
        self.e.change_stage(self.outside, 'spe', -6)
        self.native()
        row = self.completion()
        self.assertEqual({actor.entity_id for actor in MC.actual_recipients(row)},
                         {self.b.entity_id, self.c.entity_id})
        self.assertTrue(all(MC.recipient_result(row, actor)['hit'] for actor in (self.b, self.c)))
        self.assertEqual([self.a.stages['spe'], self.b.stages['spe'], self.c.stages['spe'],
                          self.outside.stages['spe']], [0, -1, -1, -6])
        self.assertFalse(any('구속' in actor.conditions for actor in (self.a, self.b, self.c, self.outside)))
        stages = [entry for entry in self.e._effect_dispatch_receipts.values()
                  if entry['source_id'] == MOVE and entry['effect'].get('type') == 'stage_change']
        self.assertEqual(len(stages), 2)
        self.assertTrue(all(entry['status'] == 'completed' for entry in stages))
        self.assertEqual(self.a.move_uses[MOVE], 1)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertEqual(self.e.effect_stats['held'], 0)
        self.valid()

    def test_speed_reaches_or_already_equals_minus_six_traps_only_actual_hits_and_survives_load(self):
        self.scene()
        self.e.change_stage(self.b, 'spe', -5)
        self.e.change_stage(self.c, 'spe', -6)
        self.e.change_stage(self.outside, 'spe', -6)
        self.native()
        self.assertEqual([self.b.stages['spe'], self.c.stages['spe']], [-6, -6])
        self.assertTrue(all('구속' in actor.conditions for actor in (self.b, self.c)))
        self.assertNotIn('구속', self.outside.conditions)
        ids = [self.b.entity_id, self.c.entity_id, self.outside.entity_id, self.a.entity_id]
        loaded = CODEC.load_engine(self.e.r, self.e.export_state())
        actors = WORLD.actor_index(loaded)
        self.assertTrue(all('구속' in actors[identity].conditions for identity in ids[:2]))
        self.assertNotIn('구속', actors[ids[2]].conditions)
        self.assertEqual(actors[ids[3]].move_uses[MOVE], 1)
        report = loaded.validate_state()
        self.assertTrue(report['valid'], report['issues'])

    def test_native_miss_does_not_lower_speed_or_trap_even_at_minus_six(self):
        self.scene()
        self.e.change_stage(self.b, 'spe', -6)
        self.e.change_stage(self.c, 'spe', -5)
        self.native(face=1)
        row = self.completion()
        self.assertFalse(any(MC.recipient_result(row, actor)['hit'] for actor in (self.b, self.c)))
        self.assertEqual([self.b.stages['spe'], self.c.stages['spe']], [-6, -5])
        self.assertFalse(any('구속' in actor.conditions for actor in self.e.everyone))
        self.assertEqual(self.a.move_uses[MOVE], 1)
        self.assertEqual(self.a.budget['standard'], 0)
        self.valid()

    def test_direct_single_target_and_omitted_cone_recipient_are_rejected_before_payment(self):
        self.scene()
        assert_rejected_unchanged(self.e,
            lambda: self.e.use_move(self.a, self.b, MOVE, aim=(3, 2)),
            reason_pattern='complete native target activation')
        assert_rejected_unchanged(self.e,
            lambda: self.native(everyone=[self.a, self.b, self.outside]),
            reason_pattern='omitted')
        self.assertNotIn(MOVE, self.a.move_uses)

    def test_changed_selected_area_effect_is_rejected_before_native_payment(self):
        self.scene()
        original = self.e.r.move_mech
        def changed(mid):
            mechanics, confidence = original(mid)
            mechanics = deepcopy(mechanics)
            if mid == MOVE:
                mechanics['effects_exec'][0]['delta'] = -2
            return mechanics, confidence
        def changed_activation():
            with patch.object(self.e.r, 'move_mech', side_effect=changed):
                return self.native()
        assert_rejected_unchanged(self.e, changed_activation,
            reason_pattern='unchanged reviewed selected source')
        self.assertEqual([self.b.stages['spe'], self.c.stages['spe']], [0, 0])
        self.assertNotIn(MOVE, self.a.move_uses)

    def test_naked_hit_flag_cannot_apply_area_effect_without_its_native_recipient(self):
        self.scene()
        effect = self.e.r.move_mech(MOVE)[0]['effects_exec'][0]
        result = FX.run_effects(self.e, self.a, self.b, [effect],
            dict(engine=self.e, attacker=self.a, target=self.b, hit=True, nat=10,
                 move=self.e.r.move(MOVE)), MOVE)
        self.assertEqual(result[1], 1)
        self.assertEqual([self.b.stages['spe'], self.c.stages['spe']], [0, 0])
        self.assertTrue(any(entry['status'] == 'execution_failed'
                            for entry in self.e._effect_dispatch_receipts.values()))
        self.assertNotIn(MOVE, self.a.move_uses)


if __name__ == '__main__':
    unittest.main()