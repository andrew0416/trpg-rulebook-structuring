"""Source-only Natural Fighter acceptance candidates; not locally executed.

Use the existing real Survivalist fixture/acquisition and public native actions.
No Move handler is stubbed; deterministic accuracy patches only the dice source.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import action_points as AP
import book_survivalist_fixture as FIX
import coat_effects as COAT
import combat_timing as TIME
import natural_fighter as NF
import state_codec as CODEC
import survivalist_class as SC


class NaturalFighterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def scene(self, role='trainer', terrain='tundra', **options):
        world = FIX.scene(self.rules, **options)
        self.e, self.t, self.p, self.foe = [world[k] for k in ('engine', 'trainer', 'partner', 'foe')]
        self.actor = world[role]
        self.e.gm.observe_loyalty(self.p, 6, reason='actual willing owned Pokemon')
        self.e.gm.set_position(self.foe, (3, 3), reason='actual target in native range')
        FIX.env(self.e, self.actor, terrain)
        FIX.battle(self.e, self.actor)
        return world

    def cast(self, terrain, *, target=None, subject=None):
        return self.e.survivalist_activity(self.t, 'natural_fighter',
            subject=subject or self.actor, terrain_name=terrain, target=target, set_damage=True)

    def next_round(self):
        self.e.end_of_turn(self.actor)
        FIX.battle(self.e, self.actor)

    def snap(self):
        return deepcopy((CODEC.dump_engine(self.e), self.e.rng.getstate(),
                         self.e.log_lines, self.e.gm_prompts))

    def reject_unchanged(self, pattern, call):
        before = self.snap()
        with self.assertRaisesRegex(ValueError, pattern):
            call()
        self.assertEqual(before, self.snap())

    def test_six_complete_routes_use_native_effects_and_one_standard_one_ap(self):
        for terrain in ('grassland', 'forest', 'wetland', 'ocean', 'tundra', 'mountain'):
            with self.subTest(terrain=terrain):
                self.scene(terrain=terrain)
                ap = AP.available(self.t)
                learned = deepcopy(self.t.spec.get('moves', []))
                if terrain == 'tundra':
                    self.e.change_stage(self.t, 'atk', 2)
                    self.e.change_stage(self.p, 'spe', 2)
                    self.e.change_stage(self.foe, 'def', -2)
                before_hp = self.foe.hp
                target = None if terrain in NF.SELF_ANCHORS else self.foe
                with patch.object(Engine, 'd20', return_value=18):
                    result = self.cast(terrain, target=target)
                self.assertEqual(result['move_id'], NF.MOVES[terrain])
                self.assertEqual(AP.available(self.t), ap - 1)
                self.assertEqual(self.t.budget['standard'], 0)
                self.assertEqual(self.t.spec.get('moves', []), learned)
                self.assertNotIn(NF.MOVES[terrain], self.t.moves)
                row = self.e._move_completions[result['completion_id']]
                self.assertEqual(row['phase'], 'complete')
                self.assertTrue(row['sealed'])
                if terrain == 'grassland':
                    self.assertEqual(self.p.stages['spe'], -2)
                    self.assertEqual(self.foe.stages['spe'], -2)
                elif terrain == 'forest':
                    self.assertIn('잠듦', self.foe.conditions)
                elif terrain == 'wetland':
                    self.assertLess(self.foe.hp, before_hp)
                    self.assertEqual(self.foe.accuracy_stage, -1)
                elif terrain == 'ocean':
                    self.assertEqual([r['source'] for r in COAT.live(self.t)], ['move/아쿠아링'])
                elif terrain == 'tundra':
                    self.assertEqual((self.t.stages['atk'], self.p.stages['spe'], self.foe.stages['def']), (0, 0, 0))
                elif terrain == 'mountain':
                    self.assertLess(self.foe.hp, before_hp)
                    records = [r for r in TIME.records(self.foe) if r.get('catalog_grounding')]
                    self.assertEqual(len(records), 1)
                    self.assertEqual(records[0]['catalog_grounding']['turns'], 3)

    def test_owned_pokemon_uses_its_terrain_and_pays_only_owner_ap(self):
        self.scene('partner', 'tundra')
        FIX.env(self.e, self.t, 'urban')
        ap = AP.available(self.t)
        owner_budget = deepcopy(getattr(self.t, 'budget', None))
        self.cast('tundra')
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(getattr(self.t, 'budget', None), owner_budget)
        self.assertEqual(self.p.budget['standard'], 0)
        self.assertEqual(self.p.move_uses['move/흑안개'], 1)
        self.assertNotIn('move/흑안개', self.p.moves)
        self.assertNotIn('move/흑안개', self.t.move_uses)

    def test_aqua_ring_heals_future_own_turn_after_codec_restore(self):
        self.scene('partner', 'ocean')
        self.p.hp = 1
        self.cast('ocean')
        self.assertEqual(self.p.hp, 1)
        loaded, index = FIX.restore(self.rules, self.e)
        pokemon = index[self.p.entity_id]
        loaded.end_of_turn(pokemon)
        loaded.start_of_turn(index[self.foe.entity_id], initiative_count=19)
        self.assertEqual(pokemon.hp, 1)
        loaded.end_of_turn(index[self.foe.entity_id])
        FIX.battle(loaded, pokemon)
        self.assertEqual(pokemon.hp, 1 + loaded.tick(pokemon))
        self.assertEqual(pokemon.move_uses['move/아쿠아링'], 1)
        self.assertNotIn('move/아쿠아링', pokemon.moves)

    def test_learned_and_natural_haze_share_scene_frequency_through_restore(self):
        self.scene()
        self.e.gm.set_move(self.t, 'move/흑안개', reason='actual previously learned trainer Move')
        self.e.use_move_on(self.t, self.t, 'move/흑안개', self.e.everyone)
        self.next_round()
        self.next_round()  # a Scene Move may not repeat on consecutive turns (frequency rule); the shared count is what is tested
        self.cast('tundra')
        self.assertEqual(self.t.move_uses['move/흑안개'], 2)
        self.assertIn('move/흑안개', self.t.moves)
        self.e, index = FIX.restore(self.rules, self.e)
        self.t, self.p, self.foe = [index[a.entity_id] for a in (self.t, self.p, self.foe)]
        self.actor = self.t
        self.next_round()
        self.reject_unchanged('.', lambda: self.cast('tundra'))
        self.assertEqual(self.t.move_uses['move/흑안개'], 2)

    def test_eot_cotton_spore_cannot_be_regranted_on_the_next_turn(self):
        self.scene(terrain='grassland')
        with patch.object(Engine, 'd20', return_value=18):
            self.cast('grassland')
        self.next_round()
        self.reject_unchanged('.', lambda: self.cast('grassland'))

    def test_completed_miss_still_pays_one_ap_standard_and_move_use(self):
        self.scene(terrain='forest')
        ap, hp = AP.available(self.t), self.foe.hp
        with patch.object(Engine, 'd20', return_value=1):
            self.cast('forest', target=self.foe)
        self.assertEqual(AP.available(self.t), ap - 1)
        self.assertEqual(self.t.budget['standard'], 0)
        self.assertEqual(self.t.move_uses['move/풀피리'], 1)
        self.assertEqual(self.foe.hp, hp)
        self.assertNotIn('잠듦', self.foe.conditions)

    def test_urban_without_actual_projectile_choice_rejects_before_all_costs_and_rng(self):
        self.scene(terrain='urban')
        self.reject_unchanged('explicit actual Fling projectile choice', lambda: self.cast('urban', target=self.foe))

    def test_unobserved_arena_and_wrong_current_terrain_reject_unchanged(self):
        self.scene(terrain='urban')
        self.reject_unchanged('observed current terrain', lambda: self.cast('tundra'))
        FIX.env(self.e, self.t)
        self.reject_unchanged('observed current terrain', lambda: self.cast('tundra'))

    def test_foreign_pokemon_and_other_trainer_cannot_use_owner_feature(self):
        world = self.scene(ally=True)
        self.reject_unchanged('trainer-owned Pokemon', lambda: self.cast('tundra', subject=self.foe))
        self.reject_unchanged('trainer-owned Pokemon', lambda: self.cast('tundra', subject=world['ally']))

    def test_feature_receipt_and_actual_subject_turn_are_required(self):
        self.scene(feats=(SC.CLASS,))
        self.reject_unchanged('acquired source', lambda: self.cast('tundra'))
        self.scene()
        FIX.env(self.e, self.p, 'tundra')
        self.reject_unchanged('actual encounter turn', lambda: self.cast('tundra', subject=self.p))

    def test_ap_and_standard_exhaustion_reject_without_frequency_or_rng_change(self):
        self.scene()
        AP.spend(self.t, AP.available(self.t))
        self.reject_unchanged('1 available trainer AP', lambda: self.cast('tundra'))
        self.scene()
        self.cast('tundra')
        self.reject_unchanged('available Standard', lambda: self.cast('tundra'))

    def test_native_recalled_target_rejection_rolls_back_inner_ap_and_permission(self):
        self.scene(terrain='forest')
        self.e.gm.recall(self.foe, reason='actual recalled target before declaration')
        self.reject_unchanged('.', lambda: self.cast('forest', target=self.foe))
    def test_self_and_field_moves_reject_foreign_anchor_before_payment(self):
        for terrain in ('grassland', 'ocean', 'tundra'):
            with self.subTest(terrain=terrain):
                self.scene(terrain=terrain)
                self.reject_unchanged('user anchor', lambda: self.cast(terrain, target=self.foe))


if __name__ == '__main__':
    unittest.main()


