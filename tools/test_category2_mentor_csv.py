"""Exact CSV Mentor acquisition and real native teaching, not injected grants."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from encounter import usable_moves
from builder import build_trainer, build_pokemon
import mentor_csv as CSV
import pokemon_teaching as T
import trainer_feature_acquisition as A
import move_state as M
import state_codec as C
import frequency as F
import activity_jobs as JOBS


class MentorCSVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.rules, seed=104)
        self.a = self.add(build_trainer(self.rules, 'actual CSV Mentor', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            abilities=[], extra={'classes': [], 'feats': [], 'skills': {'매력': 5, '포켓몬학': 3,
                '직감': 3, '협박': 3}, 'movement_basis': 'current', 'power_basis': 'current'}))

    def add(self, spec):
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, pos=(0, 0), side='party', reason='actual registered source participant')
        return actor

    def acquire(self, **kwargs):
        return CSV.acquire(self.e, self.a, acquisition_request_id=kwargs.pop('request', 'mentor/104'),
            skills=kwargs.pop('skills', ['매력', '포켓몬학']),
            lifecycle_policy=deepcopy(A.LIFECYCLE_UNRESOLVED), **kwargs)

    def pupil(self, species='이상해씨', level=30, tp=5):
        return self.add(build_pokemon(self.rules, species, level, moves=[], abilities=[],
            extra={'tutor_points': tp}))

    def teach(self, pupil, move, **kwargs):
        return CSV.teach(self.e, self.a, target=pupil, move_id=move, seconds=60,
            reason='GM observes actual one-minute Extended instruction', **kwargs)

    def state(self):
        return deepcopy((self.e.elapsed_seconds, self.e.rng.getstate(),
                         [vars(a) for a in self.e.everyone], self.e.log_lines),
                         {id(self.rules): self.rules})

    def test_acquisition_two_novice_skills_immutable_replay_and_current_projection(self):
        row = self.acquire()
        self.assertEqual(row['selection']['values'], ['매력', '포켓몬학'])
        self.assertEqual(row['selection']['acquisition_snapshot']['ranks'], [5, 3])
        self.assertIn(T.MENTOR, self.a.spec['classes'])
        before = self.state()
        self.assertEqual(self.acquire(), row)
        self.assertEqual(self.state(), before)
        for kwargs in ({'skills': ['직감', '협박']}, {'request': 'new-request'}):
            with self.assertRaises(ValueError):
                self.acquire(**kwargs)
            self.assertEqual(self.state(), before)
        T.select_mentor_skills(self.e, self.a, ['매력', '포켓몬학'], reason='same committed choice')
        self.assertEqual(self.a.spec['mentor_skill_selection']['source'], CSV.SOURCE)
        with self.assertRaises(ValueError):
            T.select_mentor_skills(self.e, self.a, ['직감', '협박'], reason='forbidden replacement')
        self.assertEqual(self.state(), before)

    def test_acquisition_bad_choices_skill_rank_source_and_capacity_are_atomic(self):
        before = self.state()
        for values in ([], ['매력'], ['매력', '매력'], ['육상', '포켓몬학'], ['매력', '포켓몬학', '직감']):
            with self.assertRaises(ValueError):
                self.acquire(skills=values)
            self.assertEqual(self.state(), before)
        self.a.spec['skills']['직감'] = 2
        before = self.state()
        with self.assertRaises(ValueError):
            self.acquire(skills=['직감', '협박'])
        self.assertEqual(self.state(), before)
        with self.assertRaises(ValueError):
            self.acquire(source_clause_id='C04-not-exact')
        self.assertEqual(self.state(), before)
        with patch.object(CSV, 'CSV_SHA', '0' * 64):
            with self.assertRaises(ValueError):
                self.acquire()
        self.assertEqual(self.state(), before)

    def test_both_actual_ranks_level_boundary_nonowned_target_and_paid_natural(self):
        self.acquire()
        pupil = self.pupil('브케인', 31)
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'allowance'):
            self.teach(pupil, '화염방사')
        self.assertEqual(self.state(), before)
        self.e.gm.set_level(pupil, 32, reason='actual next level makes level40 within ranks5+3')
        result = self.teach(pupil, '화염방사')
        self.assertEqual((result['point_cost'], result['classification']), (1, 'natural'))
        self.assertEqual((pupil.spec['tutor_points'], self.e.elapsed_seconds), (4, 60))
        self.assertEqual(pupil.spec['move_learning']['move/화염방사']['mentor_skill_ranks'], [5, 3])
        self.assertEqual(M.describe(self.rules, pupil.spec)['taught_count'], 0)
        self.assertIn('move/화염방사', usable_moves(self.e, pupil))

    def test_actual_level_up_is_free_but_zero_tp_target_still_rejected(self):
        self.acquire()
        zero = self.pupil('이상해씨', 10, tp=0)
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'Tutor Points'):
            self.teach(zero, '덩굴채찍')
        self.assertEqual(self.state(), before)
        pupil = self.pupil('이상해씨', 10, tp=1)
        result = self.teach(pupil, '덩굴채찍')
        self.assertEqual((result['point_cost'], result['classification'], pupil.spec['tutor_points']), (0, 'natural', 1))
        proof = pupil.spec['move_learning']['move/덩굴채찍']['mentor_csv_proof']
        self.assertLessEqual(proof['membership']['required_level'], 10)
        self.assertEqual(self.e.elapsed_seconds, 60)

    def test_current_n_tutor_without_required_level_is_paid(self):
        self.acquire()
        pupil = self.pupil('리자몽', 30, tp=1)
        result = self.teach(pupil, '에어슬래시')
        self.assertEqual((result['point_cost'], pupil.spec['tutor_points']), (1, 0))
        proof = pupil.spec['move_learning']['move/에어슬래시']['mentor_csv_proof']
        self.assertEqual(proof['membership']['kind'], 'n_tutor')
        self.assertIsNone(proof['membership']['required_level'])

    def test_initially_evolved_true_predecessor_lost_move_no_evolution_history_required(self):
        self.acquire()
        pupil = self.pupil('뷰티플라이', 10, tp=1)
        self.assertFalse(pupil.spec.get('allocation_migrations'))
        result = self.teach(pupil, '단단해지기', ancestor='실쿤')
        self.assertEqual((result['classification'], result['point_cost'], pupil.spec['tutor_points']), ('natural', 0, 1))
        row = pupil.spec['move_learning']['move/단단해지기']
        proof = row['mentor_csv_proof']
        self.assertEqual((proof['route'], proof['ancestor'], proof['membership']['required_level']), ('pre_evolution_n', '실쿤', 5))
        self.assertEqual([v[1] for v in proof['lineage']], ['개무소', '실쿤', '뷰티플라이'])
        self.assertEqual(M.describe(self.rules, pupil.spec)['taught_count'], 0)

    def test_branch_sibling_and_currently_available_future_move_cannot_be_lost_n(self):
        self.acquire()
        pupil = self.pupil('뷰티플라이', 10)
        before = self.state()
        with self.assertRaises(ValueError):
            self.teach(pupil, '단단해지기', ancestor='카스쿤')
        self.assertEqual(self.state(), before)
        raichu = self.pupil('라이츄', 5)
        before = self.state()
        with self.assertRaises(ValueError):
            self.teach(raichu, '10만볼트', ancestor='피카츄')
        self.assertEqual(self.state(), before)

    def test_native_daily_three_includes_free_and_legacy_entry_no_second_pool(self):
        self.acquire()
        pupil = self.pupil('이상해씨', 30, tp=1)
        for i, name in enumerate(['덩굴채찍', '잎날가르기', '성장']):
            result = self.teach(pupil, name) if i != 1 else T.teach_feature(self.e, self.a,
                target=pupil, move_id=name, feature=T.MENTOR, seconds=60, reason='legacy public entry dispatches exact source')
            self.assertEqual(result['point_cost'], 0)
        self.assertEqual((pupil.spec['tutor_points'], self.e.elapsed_seconds), (1, 180))
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'daily frequency'):
            self.teach(pupil, '수면가루')
        self.assertEqual(self.state(), before)
        F.new_day(self.a); F.new_day(pupil)
        self.assertEqual(self.teach(pupil, '수면가루')['classification'], 'natural')

    def test_late_failure_after_native_job_and_frequency_rolls_back_all_participants(self):
        self.acquire()
        pupil = self.pupil('이상해씨', 10, tp=1)
        before = self.state(); original = F.consume_activation
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise ValueError('injected after actual time and frequency')
        with patch.object(F, 'consume_activation', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'injected'):
                self.teach(pupil, '덩굴채찍')
        self.assertEqual(self.state(), before)
        self.assertEqual(self.teach(pupil, '덩굴채찍')['point_cost'], 0)
        self.assertEqual(self.e.elapsed_seconds, 60)

    def test_gm_and_fresh_rules_restore_source_choice_natural_proof_and_native_use(self):
        self.acquire()
        pupil = self.pupil('뷰티플라이', 10, tp=1)
        self.teach(pupil, '단단해지기')
        self.e.gm.snapshot('csv-mentor')
        self.e.gm.set_move(pupil, '단단해지기', add=False, reason='actual forgetting after snapshot')
        self.e.gm.restore('csv-mentor')
        self.assertIn('move/단단해지기', M.describe(self.rules, pupil.spec)['classifications'])
        payload = json.loads(json.dumps(C.dump_engine(self.e), ensure_ascii=False))
        fresh = Rules(str(ROOT), ruleset='core')
        loaded = C.load_engine(fresh, payload)
        actors = {a.entity_id: a for a in loaded.everyone}; restored = actors[pupil.entity_id]
        self.assertEqual(CSV.receipt(actors[self.a.entity_id])['selection']['values'], ['매력', '포켓몬학'])
        self.assertEqual((restored.spec['tutor_points'], M.describe(fresh, restored.spec)['classifications']['move/단단해지기']), (1, 'natural'))
        loaded.start_round(loaded.everyone); loaded.start_of_turn(restored)
        old = restored.stages['def']
        loaded.use_move(restored, restored, 'move/단단해지기')
        self.assertGreater(restored.stages['def'], old)
        self.assertEqual(restored.budget['standard'], 0)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_historical_natural_proof_does_not_recompute_later_level_or_teacher_rank(self):
        self.acquire()
        pupil = self.pupil('브케인', 32)
        self.teach(pupil, '화염방사')
        row = deepcopy(pupil.spec['move_learning']['move/화염방사'])
        self.e.gm.set_level(pupil, 20, reason='actual later lower current level')
        self.a.spec['skills']['매력'] = 3
        self.assertTrue(M.validate_actor(pupil))
        self.assertEqual(pupil.spec['move_learning']['move/화염방사'], row)
        self.assertEqual(M.describe(self.rules, pupil.spec)['classifications']['move/화염방사'], 'natural')
        C.dump_engine(self.e)

    def test_receipt_and_historical_species_lineage_payment_forgery_rejected(self):
        self.acquire()
        pupil = self.pupil('뷰티플라이', 10, tp=1)
        self.teach(pupil, '단단해지기')
        original = deepcopy(pupil.spec)
        for change in ('ancestor', 'payment', 'ranks', 'row_hash', 'acquisition'):
            pupil.spec.clear(); pupil.spec.update(deepcopy(original))
            row = pupil.spec['move_learning']['move/단단해지기']
            if change == 'ancestor': row['mentor_csv_proof']['ancestor'] = '카스쿤'
            elif change == 'payment': row['paid_tp'] = 1
            elif change == 'ranks': row['mentor_skill_ranks'] = [6, 6]
            elif change == 'row_hash': row['mentor_csv_proof']['ancestor_source']['row_sha256'] = '0' * 64
            else: row['mentor_acquisition_receipt']['qualification']['checks'][1]['observed']['ranks'] = [6, 6]
            # Keep the ordinary log mirror coherent, so source validation is
            # challenged rather than merely an unrelated missing log link.
            pupil.spec['move_learning_log'][-1] = {'move_id': 'move/단단해지기', 'replaced': None, **deepcopy(row)}
            with self.assertRaises(ValueError):
                M.validate_actor(pupil)
            with self.assertRaises(ValueError):
                C.dump_engine(self.e)
        pupil.spec.clear(); pupil.spec.update(original)
        self.assertTrue(M.validate_actor(pupil))


if __name__ == '__main__':
    unittest.main()
