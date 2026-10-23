"""Category 3 contest regressions; not a whole-contest certificate."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from contest import ContestEngine, ContestRules, Contestant, demo_contestants

class Ones:
    def randint(self, low, high):
        assert (low, high) == (1, 6)
        return 1

class Category3ContestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = ContestRules(ROOT)

    def setUp(self):
        self.engine = ContestEngine(self.rules, seed=73)
        self.actors = demo_contestants()

    def snapshot(self):
        return deepcopy([vars(c) for c in self.actors]), self.engine.rng.getstate(), list(self.engine.log_lines)

    def reject(self, **kwargs):
        before = self.snapshot()
        defaults = dict(c=self.actors[0], move_name='헤롱헤롱', contest_type='귀여움',
                        adjacent=self.actors[1:], center=True)
        defaults.update(kwargs)
        with self.assertRaises(ValueError):
            self.engine.perform(**defaults)
        self.assertEqual(self.snapshot(), before, 'Rejected turn changed actors, RNG or logs')

    def test_negative_spend_is_rejected_without_creating_resources(self):
        self.reject(spend_stat_dice=-1)

    def test_non_integer_spend_is_rejected(self):
        for value in (True, 1.0, 0.5, '1', None):
            with self.subTest(value=value):
                self.reject(spend_stat_dice=value)

    def test_spend_above_performance_cap_is_rejected(self):
        self.actors[0].stat_dice['귀여움'] = 9
        self.reject(spend_stat_dice=4)

    def test_spend_above_remaining_balance_is_rejected(self):
        self.reject(spend_stat_dice=3)

    def test_spend_is_not_reusable_and_adds_exactly_that_many_dice(self):
        c = self.actors[0]
        c.moves = ['연속자르기']
        c.stat_dice = {'근사함': 4}
        self.engine.perform(c, '연속자르기', '근사함', [], False,
                            spend_stat_dice=3, fixed_rolls=[2] * 7)
        self.assertEqual((c.stat_dice['근사함'], c.appeal), (1, 7))
        self.reject(move_name='연속자르기', contest_type='근사함', adjacent=[],
                    center=False, spend_stat_dice=2)
        self.engine.perform(c, 'move/연속자르기', '근사함', [], False,
                            spend_stat_dice=1, fixed_rolls=[2] * 6)
        self.assertEqual((c.stat_dice['근사함'], c.appeal), (0, 13))

    def test_unlearned_move_is_rejected_by_name_and_id(self):
        for name in ('유턴', 'move/유턴'):
            with self.subTest(name=name):
                self.reject(move_name=name)

    def test_learned_ids_and_names_are_equivalent(self):
        self.actors[0].moves = ['move/헤롱헤롱']
        self.engine.perform(self.actors[0], '헤롱헤롱', '귀여움', [], True,
                            fixed_rolls=[3, 2, 6, 1])
        self.assertEqual((self.actors[0].appeal, self.actors[0].fumble), (4, 1))

    def test_consecutive_move_is_rejected_across_name_and_id(self):
        self.engine.perform(self.actors[0], '헤롱헤롱', '귀여움', [], True,
                            fixed_rolls=[3, 2, 6, 1])
        self.reject(move_name='move/헤롱헤롱')
        self.reject(move_name='헤롱헤롱')

    def test_saved_last_move_name_cannot_bypass_repeat_restriction(self):
        self.actors[0].last_move = '헤롱헤롱'
        self.reject(move_name='move/헤롱헤롱')

    def test_reliable_exception_adds_one_die_and_excitement(self):
        c = self.actors[0]
        c.moves = ['연속자르기']
        self.engine.perform(c, '연속자르기', '근사함', [], False, fixed_rolls=[2] * 4)
        self.assertEqual((c.appeal, c.excitement), (4, 0))
        self.engine.perform(c, 'move/연속자르기', '근사함', [], False, fixed_rolls=[2] * 5)
        self.assertEqual((c.appeal, c.excitement), (9, 1))

    def test_fixed_dice_must_match_calculated_count(self):
        for rolls in ([], [6], [6] * 3, [6] * 5):
            with self.subTest(rolls=rolls):
                self.reject(fixed_rolls=rolls)

    def test_invalid_d6_faces_are_rejected_without_partial_mutation(self):
        for face in (0, 7, -1, 1.0, True, '6', None):
            with self.subTest(face=face):
                self.reject(fixed_rolls=[2, 3, 4, face])

    def test_score_checks_d6_faces_when_called_directly(self):
        for face in (0, 7, True, 1.0, '6'):
            with self.subTest(face=face), self.assertRaises(ValueError):
                self.engine.score([face], False)

    def test_late_validation_cannot_change_neighbors_or_consume_next_bonus(self):
        c = self.actors[0]
        c.moves = ['보복']
        c.double_next = True
        self.actors[1].excitement = 4
        self.reject(move_name='보복', contest_type='근사함', fixed_rolls=[6])
        self.engine.perform(c, '보복', '근사함', self.actors[1:], False, fixed_rolls=[2] * 11)
        self.assertEqual([a.excitement for a in self.actors[1:]], [5, 1])
        self.assertFalse(c.double_next)
        self.assertEqual(c.appeal, 11)

    def test_zero_dice_opposing_type_fumble_accepts_only_empty_fixed_rolls(self):
        c = self.actors[0]
        c.moves = ['회복지령']
        self.reject(move_name='회복지령', contest_type='근사함', fixed_rolls=[6])
        self.engine.perform(c, '회복지령', '근사함', [], False, fixed_rolls=[])
        self.assertEqual((c.appeal, c.fumble), (0, 1))

    def test_all_normal_and_center_faces_follow_source_table(self):
        normal = [(0, 0), (1, 0), (1, 0), (1, 0), (1, 0), (2, 0)]
        center = [(0, 1), (0, 0), (1, 0), (2, 0), (2, 0), (3, 0)]
        for face in range(1, 7):
            with self.subTest(face=face):
                self.assertEqual(self.engine.score([face], False), normal[face - 1])
                self.assertEqual(self.engine.score([face], True), center[face - 1])
        self.assertEqual(self.engine.score([1, 2, 3, 4, 5, 6], False), (6, 0))
        self.assertEqual(self.engine.score([1, 2, 3, 4, 5, 6], True), (8, 1))

    def test_actual_run_gives_each_actor_one_center_turn(self):
        for size in (3, 4, 5):
            with self.subTest(size=size):
                actors = [Contestant(str(i), {}, ['연속자르기'], '매력', 1, '귀여움') for i in range(size)]
                centers = {c.name: 0 for c in actors}
                turns = {c.name: 0 for c in actors}
                def chooser(c, rnd, adjacent, center):
                    centers[c.name] += int(center)
                    turns[c.name] += 1
                    return '연속자르기', 0
                self.engine.run(actors, '근사함', chooser)
                self.assertEqual(list(centers.values()), [1] * size)
                self.assertEqual(list(turns.values()), [size] * size)

    def test_actual_run_ranks_appeal_minus_fumble(self):
        actors = [Contestant(name, {}, ['연속자르기'], '매력', 1, '귀여움') for name in ('A', 'B', 'C')]
        actors[0].appeal, actors[0].fumble = 100, 90
        actors[1].appeal = 30
        self.engine.rng = Ones()
        result = self.engine.run(actors, '강인함', lambda *args: ('연속자르기', 0))
        self.assertEqual([c.name for c in result], ['B', 'A', 'C'])
        self.assertEqual([c.appeal - c.fumble for c in result], [26, 7, -5])
        self.assertIn('우승: B', self.engine.log_lines[-1])

    def test_final_tie_does_not_invent_a_winner_or_reuse_intro_tiebreak(self):
        actors = [Contestant(name, {}, ['연속자르기'], '매력', 1, '귀여움') for name in ('A', 'B', 'C')]
        for actor, points in zip(actors, (3, 4, 5)):
            actor.appeal = points
        self.engine.rng = Ones()
        result = self.engine.run(actors, '강인함', lambda *args: ('연속자르기', 0))
        self.assertEqual([c.appeal - c.fumble for c in result], [0, 0, 0])
        self.assertIn('최고점 동률: A, B, C', self.engine.log_lines[-1])
        self.assertIn('단독 우승 판정 미확정', self.engine.log_lines[-1])
        self.assertNotIn('우승:', self.engine.log_lines[-1])

    def test_actual_run_chooser_cannot_use_unlearned_move(self):
        snapshots = []
        def chooser(c, rnd, adjacent, center):
            snapshots.append(self.snapshot())
            return '연속자르기', 0
        with self.assertRaises(ValueError):
            self.engine.run(self.actors, '귀여움', chooser)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(self.snapshot(), snapshots[-1])

    def test_actual_run_chooser_cannot_repeat_forbidden_move(self):
        snapshots = []
        def chooser(c, rnd, adjacent, center):
            snapshots.append((rnd, self.snapshot()))
            return c.moves[0], 0
        with self.assertRaises(ValueError):
            self.engine.run(self.actors, '귀여움', chooser)
        self.assertEqual([r for r, _ in snapshots], [1, 1, 1, 2])
        self.assertEqual(self.snapshot(), snapshots[-1][1])

if __name__ == '__main__':
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.rows = []
        def addSuccess(self, t):
            super().addSuccess(t)
            self.rows.append({'id': t._testMethodName, 'status': 'pass'})
        def addFailure(self, t, err):
            super().addFailure(t, err)
            self.rows.append({'id': t._testMethodName, 'status': 'fail'})
        def addError(self, t, err):
            super().addError(t, err)
            self.rows.append({'id': t._testMethodName, 'status': 'error'})
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Category3ContestTests))
    paths = [ROOT / 'engine/adjudication_guidance.py',ROOT / 'data/adjudication-guidance.json',ROOT / 'engine/skill_maneuver_actions.py',ROOT / 'engine/food_effects.py',ROOT / 'engine/combat_social_edges.py',ROOT / 'engine/net_capsule.py',ROOT / 'engine/trainer_capabilities.py',ROOT / 'engine/skill_feature_actions.py',ROOT / 'engine/researcher_features.py',ROOT / 'engine/precise_actions.py',ROOT / 'engine/environmental_effects.py',ROOT / 'engine/wild_equipment.py',ROOT / 'engine/injury_recovery.py',ROOT / 'engine/downtime.py',ROOT / 'engine/items.py',ROOT / 'engine/skill_modifiers.py',ROOT / 'engine/common_action_checks.py',ROOT / 'engine/gm_state.py',ROOT / 'engine/heavy_injury_adapter.py',ROOT / 'engine/jump_actions.py',ROOT / 'engine/context_actions.py',ROOT / 'engine/pokemon_requests.py',ROOT / 'engine/combat_timing.py',ROOT / 'engine/combat_maneuvers.py',ROOT / 'data/context-check-policy.json',ROOT / 'data/cultivation-policy.json',ROOT / 'engine/movement_actions.py',ROOT / 'engine/weapon_actions.py',ROOT / 'data/weapon-policy.json',ROOT / 'engine/bandages.py',ROOT / 'engine/crafting_activities.py',ROOT / 'data/planter-policy.json',ROOT / 'engine/capability_actions.py',ROOT / 'engine/physical_limits.py',ROOT / 'data/capability-policy.json',ROOT / 'engine/temporary_hp.py',ROOT / 'engine/contest_features.py',ROOT / 'engine/action_points.py',ROOT / 'engine/turn.py',ROOT / 'engine/action_lifecycle.py',Path(__file__), ROOT / 'engine/contest.py', ROOT / 'engine/ruleset.py', ROOT / 'engine/common_checks.py', ROOT / 'engine/resolution_transaction.py',
             ROOT / 'data/rulesets.json', ROOT / 'data/contest-rules.json',
             ROOT / 'output/entities/moves.json', ROOT / 'output/ruleunits.jsonl',
             ROOT / 'input/ch08-contests.md']
    paths += [ROOT / v for v in ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']]
    paths += [ROOT / v for v in ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']]
    paths += [ROOT / v for v in ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']]

    paths += [ROOT / v for v in ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']]

    paths += [ROOT / v for v in ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']]
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'DOMAIN-040 scoring; partial DOMAIN-037/041 admission/resource fixes. Not all contest rules.',
              'successful': result.wasSuccessful(), 'results': result.rows,
              'input_hashes': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (ROOT / 'output/category3-contest-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)

