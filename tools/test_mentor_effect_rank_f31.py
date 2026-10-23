"""F31: native Mentor effects use rank eight without inventing historical rank effects."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'input').is_dir():
    ROOT = Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_mentor_csv as csv_fixture
import test_category2_mentor_move_state as book_fixture
from engine import Rules
from encounter import usable_moves
import mentor_csv as CSV
import pokemon_teaching as T
import move_state as M
import state_codec as C
import skill_modifiers as S
import trainer_feature_acquisition as A

MID = 'move/화염방사'


class MentorEffectRankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def fixture(self, route, *, choice='매력', charm=6):
        if route == 'csv':
            f = csv_fixture.MentorCSVTests('runTest'); f.rules = self.rules
        else:
            f = book_fixture.MentorMoveStateTests('runTest'); f.r = self.rules
        f.setUp()
        f.a.spec['skills']['매력'] = charm
        if choice is not None:
            f.a.spec['skills'][choice] = 6 if choice != '매력' else charm
            f.a.spec.setdefault('edges', []).append('edge/거장')
            f.a.spec.setdefault('edge_choices', {})['edge/거장'] = [choice]
        if route == 'csv':
            f.acquire()
        return f

    def pupil(self, f, route, level=29):
        return f.pupil('브케인', level, tp=8) if route == 'csv' else f.pokemon(level)

    def state(self, f):
        return deepcopy((f.e.elapsed_seconds, f.e.rng.getstate(),
                         [vars(a) for a in f.e.everyone], f.e.log_lines),
                        {id(self.rules): self.rules})

    def assert_effect_teaching(self, route):
        f = self.fixture(route); p = self.pupil(f, route)
        self.assertEqual(S.rank(self.rules, f.a, '매력')[2], 6)
        self.assertEqual(S.effective_rank(self.rules, f.a, '매력'), 8)
        roll = f.e.skill_roll(f.a, '매력', fixed=[1] * 6)
        self.assertEqual((roll.rank, len(roll.faces)), (6, 6))
        if route == 'csv':
            self.assertEqual(CSV.receipt(f.a)['selection']['acquisition_snapshot']['ranks'], [6, 3])
        result = f.teach(p, MID)
        self.assertEqual((result['classification'], result['point_cost']), ('natural', 1))
        self.assertEqual((p.spec['tutor_points'], f.e.elapsed_seconds), (7, 60))
        row = p.spec['move_learning'][MID]
        self.assertEqual(row['mentor_skill_ranks'], [8, 3])
        self.assertEqual(row['mentor_rank_evidence']['teacher_id'], f.a.entity_id)
        self.assertEqual(M.describe(self.rules, p.spec)['taught_count'], 0)
        self.assertIn(MID, usable_moves(f.e, p))
        self.assertTrue(M.validate_actor(p))

    def test_book_effect_eight_plus_three_teaches_level_forty_at_twenty_nine(self):
        self.assert_effect_teaching('book')

    def test_csv_effect_eight_keeps_ordinary_six_acquisition_and_native_learning(self):
        self.assert_effect_teaching('csv')

    def test_effect_boundary_other_choice_and_invalid_master_remain_atomic(self):
        for route in ('book', 'csv'):
            for choice, charm, level in (('매력', 6, 28), (None, 6, 29), ('직감', 6, 29), ('매력', 5, 29)):
                with self.subTest(route=route, choice=choice, charm=charm, level=level):
                    f = self.fixture(route, choice=choice, charm=charm)
                    p = self.pupil(f, route, level); before = self.state(f)
                    with self.assertRaises(ValueError):
                        f.teach(p, MID)
                    self.assertEqual(self.state(f), before)

    def test_effect_teaching_keeps_native_daily_three_and_time_payment_atomicity(self):
        for route in ('book', 'csv'):
            with self.subTest(route=route):
                f = self.fixture(route)
                for _ in range(3):
                    p = self.pupil(f, route)
                    self.assertEqual(f.teach(p, MID)['point_cost'], 1)
                    self.assertEqual(p.spec['tutor_points'], 7)
                fourth = self.pupil(f, route); before = self.state(f)
                with self.assertRaisesRegex(ValueError, 'daily frequency'):
                    f.teach(fourth, MID)
                self.assertEqual(self.state(f), before)
                self.assertEqual(f.e.elapsed_seconds, 180)

    def test_historical_effect_survives_teacher_change_gm_and_fresh_codec_restore(self):
        for route in ('book', 'csv'):
            with self.subTest(route=route):
                f = self.fixture(route); p = self.pupil(f, route); f.teach(p, MID)
                original = deepcopy(p.spec['move_learning'][MID])
                f.e.gm.snapshot('effect-eight')
                f.e.gm.set_move(p, MID, add=False, reason='explicit later forgetting')
                f.e.gm.restore('effect-eight')
                self.assertEqual(p.spec['move_learning'][MID], original)
                f.a.spec['skills']['매력'] = 3
                f.a.spec['edges'] = []; f.a.spec['edge_choices'] = {}
                f.e.gm.set_level(p, 20, reason='later actual level is below old teaching allowance')
                self.assertEqual(M.describe(self.rules, p.spec)['classifications'][MID], 'natural')
                payload = json.loads(json.dumps(C.dump_engine(f.e), ensure_ascii=False))
                fresh = Rules(str(ROOT), ruleset='core')
                loaded = C.load_engine(fresh, payload)
                actors = {a.entity_id: a for a in loaded.everyone}
                self.assertEqual(S.effective_rank(fresh, actors[f.a.entity_id], '매력'), 3)
                restored = actors[p.entity_id]
                self.assertEqual(restored.spec['move_learning'][MID], original)
                self.assertEqual(M.describe(fresh, restored.spec)['classifications'][MID], 'natural')
                self.assertIn(MID, usable_moves(loaded, restored))
                self.assertTrue(loaded.validate_state()['valid'])

    def test_unwitnessed_seven_and_coherent_rank_effect_forgery_rejected_by_restores(self):
        for route in ('book', 'csv'):
            with self.subTest(route=route):
                f = self.fixture(route); p = self.pupil(f, route); f.teach(p, MID)
                original = deepcopy(p.spec)
                valid_payload = C.dump_engine(f.e)
                f.e.gm.snapshot('rank-proof')
                for mutation in ('missing', 'seven', 'changed', 'no_owner', 'wrong_choice', 'non_master', 'teacher'):
                    with self.subTest(mutation=mutation):
                        def corrupt(spec):
                            row = spec['move_learning'][MID]
                            witness = row['mentor_rank_evidence']
                            if mutation == 'missing':
                                row.pop('mentor_rank_evidence')
                            elif mutation == 'seven':
                                row['mentor_skill_ranks'][0] = 7
                                if route == 'csv': row['mentor_csv_proof']['ranks'][0] = 7
                            elif mutation == 'changed':
                                witness['level'] = 19
                            else:
                                if mutation == 'no_owner': witness['edges'] = []; witness['edge_choices'] = {}
                                elif mutation == 'wrong_choice': witness['edge_choices']['edge/거장'] = ['직감']; witness['skills']['직감'] = 6
                                elif mutation == 'non_master': witness['skills']['매력'] = 5
                                else: witness['teacher_id'] = 'another-teacher'
                                payload = {k: v for k, v in witness.items() if k != 'integrity_id'}
                                witness['integrity_id'] = A._digest('mentor/rank-observation/v1', payload)
                            for i, logged in enumerate(spec['move_learning_log']):
                                if logged.get('move_id') == MID:
                                    spec['move_learning_log'][i] = dict(deepcopy(row), move_id=MID, replaced=logged.get('replaced'))
                        p.spec.clear(); p.spec.update(deepcopy(original)); corrupt(p.spec)
                        with self.assertRaises(ValueError): M.validate_actor(p)
                        with self.assertRaises(ValueError): C.dump_engine(f.e)
                        if mutation == 'missing':
                            encoder = C._Encoder(f.e); bad = deepcopy(valid_payload)
                            bad['root'] = encoder.value(f.e); bad['nodes'] = encoder.nodes
                        p.spec.clear(); p.spec.update(deepcopy(original))
                        attrs = f.e.gm.snapshots['rank-proof']['combatants'][id(p)]
                        prior = deepcopy(attrs['spec']); corrupt(attrs['spec'])
                        with self.assertRaises(ValueError): f.e.gm.restore('rank-proof')
                        attrs['spec'] = prior
                with self.assertRaises(ValueError): C.load_engine(self.rules, bad)
                self.assertTrue(M.validate_actor(p))


if __name__ == '__main__':
    unittest.main()
