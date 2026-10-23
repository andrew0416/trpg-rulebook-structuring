"""C03-127 actual teaching and only its new source/consumer boundaries."""
from copy import copy, deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
import unittest


STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'input').is_dir() else Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Combatant, Engine, Rules
from builder import build_pokemon, build_trainer
from encounter import usable_moves
import activity_jobs as JOBS
import move_state as M
import personal_tutoring as PERSONAL
import pokemon_party as PARTY
import pokemon_teaching as T
import state_codec as CODEC
import trainer_feature_acquisition as A
import turn as TURN
import world_entities as WORLD
import test_category2_type_sync as type_fixture
import test_category2_mentor_move_state as mentor_fixture


STATS = ('hp', 'atk', 'def', 'spa', 'spd', 'spe')
CSV_SOURCE = 'C2CSV/input/db/feats.csv:R8:main'


class BookPersonalTutoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.start()

    def add(self, spec):
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, reason='actual book Personal Tutor participant')
        return actor

    def start(self, selected=('화염방사', '열풍', '두번차기'), *, source=PERSONAL.SOURCE, acquire=True):
        self.e = Engine(self.rules, seed=127)
        known = list(dict.fromkeys(list(selected) + ['방어', '솔라빔', '파도타기']))
        self.t = self.add(build_trainer(self.rules, 'book tutor', 20, dict.fromkeys(STATS, 10),
            moves=known, abilities=[], extra={'skills': {'일반 지식': 3}, 'feats': [], 'exp_bank': 10}))
        if acquire:
            self.acquisition = A.acquire_personal_tutor(self.e, self.t,
                acquisition_request_id='book/tutor/acquisition', selected_values=list(selected),
                source_clause_id=source, lifecycle_policy=deepcopy(A.LIFECYCLE_UNRESOLVED))

    def pokemon(self, species='브케인', level=30, *, points=12, owner=None, moves=()):
        owner = self.t if owner is None else owner
        return self.add(build_pokemon(self.rules, species, level, moves=list(moves), abilities=[],
            extra={'trainer_id': owner.entity_id, 'tutor_points': points}))

    def teach(self, pokemon, move='열풍', **options):
        return self.e.teach_personal_tutor(self.t, target=pokemon, move_id=move,
            seconds=60, reason='GM observes completed one-minute Extended teaching', **options)

    def snapshot(self):
        return deepcopy((CODEC.dump_engine(self.e), self.e.rng.getstate(), self.e.log_lines))

    def record(self, pokemon, move='열풍'):
        return pokemon.spec['move_learning'][self.rules.move_id(move)]

    def sync_move(self, engine, pokemon, move):
        return engine.gm.observe_move_type_sync(pokemon, application_id='teaching-replaced-sync',
            move_id=move, chosen_type='고스트', new_name='유령의 ' + move,
            effect_decision={'mode': 'preserve', 'reason': 'The printed effect remains appropriate.', 'effects_exec': None},
            feasibility_review='Printed targeting and accuracy stay unchanged.',
            power_review='No damage or effect strength changes.', reason='GM observed completed individual Move Sync')

    def transfer(self, pokemon):
        other = self.add(build_trainer(self.rules, 'actual new owner', 20, dict.fromkeys(STATS, 10), abilities=[]))
        for owner, roster in ((self.t, [pokemon]), (other, [])):
            PARTY.configure(self.e, owner, mode='standard', roster=roster,
                storage={'kind': 'center', 'id': 'tutor-center-' + owner.entity_id},
                reason='actual registered ownership and storage')
        WORLD.transfer_owner(self.e, pokemon, self.t, other,
            reason='actual later ownership transfer', request_id='book-tutor/transfer')
        return other

    def test_public_book_route_spends_actual_points_time_and_produces_native_move(self):
        pupil = self.pokemon()
        result = self.teach(pupil)
        self.assertEqual((result['source_clause_id'], result['point_cost'], result['classification']),
                         ('C03-127', 2, 'taught'))
        self.assertEqual((pupil.spec['tutor_points'], self.e.elapsed_seconds), (10, 60))
        self.assertIn('move/열풍', usable_moves(self.e, pupil))
        row = self.record(pupil)
        self.assertEqual(row['teacher_id'], self.t.entity_id)
        self.assertEqual(row['personal_tutor_recipient_id'], pupil.entity_id)
        self.assertEqual(row['personal_tutor_acquisition_receipt'], self.acquisition)
        self.assertEqual((row['paid_tp'], row['learning_contract'], row['source']), (2, 1, PERSONAL.FEATURE))
        self.assertEqual(row['personal_tutor_legality']['learnset']['species'], '브케인')
        self.assertEqual(row['tutoring_admission'], T.tutor_admission(self.rules, 'move/열풍', 30))
        self.assertEqual(self.t.spec['feats'], [PERSONAL.FEATURE])
        self.assertNotIn('mentor_skills', self.t.spec)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_all_four_sourced_lists_include_future_level_without_false_natural_credit(self):
        for move, expected_kind, classification in (
                ('분화', 'level_up', 'taught'), ('방어', 'tm', 'taught'),
                ('두번차기', 'egg', 'natural'), ('열풍', 'tutor', 'taught')):
            with self.subTest(move=move):
                chosen = [move] + [value for value in ('분화', '방어', '두번차기', '열풍') if value != move][:2]
                self.start(chosen)
                pupil = self.pokemon()
                result = self.teach(pupil, move)
                self.assertEqual(result['classification'], classification)
                kinds = {value['kind'] for value in self.record(pupil, move)['personal_tutor_legality']['memberships']}
                self.assertIn(expected_kind, kinds)
                if move == '분화':
                    self.assertEqual(M.describe(self.rules, pupil.spec)['taught_count'], 1)
                    self.e.gm.set_level(pupil, 58, reason='actual later natural learning opportunity')
                    self.assertEqual(M.describe(self.rules, pupil.spec)['classifications']['move/분화'], 'natural')

    def test_same_day_repetition_has_no_daily_or_csv_one_move_vitamin_restriction(self):
        pupil = self.pokemon()
        for move in ('열풍', '화염방사', '두번차기'):
            self.teach(pupil, move)
        other = self.pokemon()
        self.teach(other)
        self.assertEqual((pupil.spec['tutor_points'], other.spec['tutor_points'], self.e.elapsed_seconds), (6, 10, 240))
        state = M.describe(self.rules, pupil.spec)
        self.assertEqual((state['slot_count'], state['taught_count']), (3, 2))
        self.assertFalse(state['vm_moves'])

    def test_actual_book_receipt_is_required_and_current_choices_cannot_replace_it(self):
        for mode in ('csv', 'unreceipted', 'unacquired', 'nonselected'):
            with self.subTest(mode=mode):
                self.start(source=CSV_SOURCE if mode == 'csv' else PERSONAL.SOURCE,
                           acquire=mode not in ('unreceipted', 'unacquired'))
                if mode == 'unreceipted':
                    self.t.spec['feats'].append(PERSONAL.FEATURE)
                pupil = self.pokemon()
                self.t.spec['feature_choices'] = {PERSONAL.FEATURE: ['move/방어', 'move/솔라빔', 'move/파도타기']}
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.teach(pupil, '방어' if mode == 'nonselected' else '열풍')
                self.assertEqual(self.snapshot(), before)

    def test_own_recipient_legality_points_and_existing_knowledge_reject_before_cost(self):
        for mode in ('other_owner', 'illegal', 'points', 'known', 'bad_replacement'):
            with self.subTest(mode=mode):
                self.start(('파도타기', '열풍', '두번차기'))
                pupil = self.pokemon(points=1 if mode == 'points' else 12)
                if mode == 'other_owner':
                    self.transfer(pupil)
                if mode == 'known':
                    M.observe_learning(self.e, pupil, '열풍', method='tutor', source=T.MOVE_TUTOR,
                                       paid_tp=2, reason='actual previously completed teaching')
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.teach(pupil, '파도타기' if mode == 'illegal' else '열풍',
                               **({'replace': '파도타기'} if mode == 'bad_replacement' else {}))
                self.assertEqual(self.snapshot(), before)

    def test_errata_is_connected_at_book_learning_and_uses_historical_level(self):
        pupil = self.pokemon(level=19)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'tutoring restriction'):
            self.teach(pupil)
        self.assertEqual(self.snapshot(), before)
        self.e.gm.set_level(pupil, 30, reason='actual eligible teaching level')
        self.teach(pupil)
        self.e.gm.set_level(pupil, 19, reason='later corrected level must not re-teach a Move')
        M.validate_actor(pupil)
        self.assertEqual(self.record(pupil)['learned_at_level'], 30)

    def test_ordinary_total_and_taught_slots_remain_and_explicit_replacement_works(self):
        from ruleset import ExcludedRuleSelection, RuleFilter, RuleSelection, UnresolvedRuleSelection
        for value, expected in (('몸통박치기', 'move/몸통박치기'), ('move/몸통박치기', 'move/몸통박치기'), ('struggle', 'struggle')):
            self.assertEqual(self.rules.resolve_move(value), expected)
        with patch.dict(self.rules.move_alias, {'legacy-tackle': 'move/몸통박치기'}):
            self.assertEqual(self.rules.resolve_move('legacy-tackle'), 'move/몸통박치기')
        with self.assertRaisesRegex(UnresolvedRuleSelection, 'missing_source_identity'):
            self.rules.resolve_move('unregistered tutor fixture move')
        blocked = copy(self.rules)
        blocked.ruleset = RuleFilter({'exclude_units': ['move/몸통박치기']})
        blocked.selection = RuleSelection(blocked.ruleset, [self.rules.selection.units['move/몸통박치기']])
        for value in ('몸통박치기', 'move/몸통박치기'):
            with self.assertRaises(ExcludedRuleSelection):
                blocked.resolve_move(value)
        with patch.dict(self.rules.selection.conflicts, {'move/몸통박치기': ['unresolved actual selection']}):
            for value in ('몸통박치기', 'move/몸통박치기'):
                with self.assertRaises(UnresolvedRuleSelection):
                    self.rules.resolve_move(value)
        self.start(('솔라빔', '열풍', '두번차기'))
        six = ['몸통박치기', '울음소리', '덩굴채찍', '씨뿌리기', '잎날가르기', '성장']
        pupil = self.pokemon('이상해씨', 50, moves=six)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'capacity'):
            self.teach(pupil, '솔라빔')
        self.assertEqual(self.snapshot(), before)
        self.sync_move(self.e, pupil, '울음소리')
        self.teach(pupil, '솔라빔', replace='울음소리')
        self.assertEqual(pupil.spec['move_type_sync']['history'][-1]['status'], 'forgotten')
        self.assertNotIn('move/울음소리', usable_moves(self.e, pupil))
        self.assertEqual(M.describe(self.rules, pupil.spec)['slot_count'], 6)
        self.start()
        pupil = self.pokemon()
        for move in ('열풍', '누르기', '잠꼬대'):
            M.observe_learning(self.e, pupil, move, method='tutor', source=T.MOVE_TUTOR,
                               paid_tp=2, reason='actual existing taught-slot occupancy')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'TM/Tutor'):
            self.teach(pupil, '화염방사')
        self.assertEqual(self.snapshot(), before)
        self.teach(pupil, '화염방사', replace='누르기')
        self.assertEqual(M.describe(self.rules, pupil.spec)['taught_count'], 3)

        for route in ('move_tutor', 'machine'):
            with self.subTest(replacement_route=route):
                if route == 'move_tutor':
                    helper = SimpleNamespace(r=self.rules)
                    mentor_fixture.MentorMoveStateTests.setUp(helper)
                    engine, teacher = helper.e, helper.a
                    pupil = mentor_fixture.MentorMoveStateTests.pokemon(helper, 30)
                    engine.gm.set_move(pupil, '몸통박치기', reason='actual initial natural Move')
                else:
                    self.start(); engine, teacher = self.e, self.t
                    pupil = self.pokemon(moves=['몸통박치기'])
                    teacher.spec['items']['TM35'] = 1
                    T.register_machine(engine, teacher, instance_id='replacement-tm', code='TM35')
                self.sync_move(engine, pupil, '몸통박치기')
                points = pupil.spec['tutor_points']
                if route == 'move_tutor':
                    result = T.teach_feature(engine, teacher, target=pupil, move_id='열풍',
                        feature=T.MOVE_TUTOR, seconds=60, reason='actual Extended replacement', replace='몸통박치기')
                else:
                    result = T.teach_machine(engine, teacher, target=pupil,
                        instance_id='replacement-tm', replace='몸통박치기')
                self.assertEqual(pupil.spec['move_type_sync']['history'][-1]['status'], 'forgotten')
                self.assertNotIn('move/몸통박치기', usable_moves(engine, pupil))
                self.assertIn(result['move'], usable_moves(engine, pupil))
                self.assertEqual(pupil.spec['tutor_points'], points - result['point_cost'])
                self.assertEqual(engine.elapsed_seconds, 60 if route == 'move_tutor' else 3600)
                CODEC.dump_engine(engine)

    def test_action_denial_and_late_native_activity_failure_preserve_new_route_graph(self):
        pupil = self.pokemon()
        before = self.snapshot()
        with patch.object(TURN, 'spend', return_value=False):
            with self.assertRaisesRegex(ValueError, 'Extended action'):
                self.teach(pupil)
        self.assertEqual(self.snapshot(), before)
        original = JOBS.run_fixed
        def fail_after_actual_job(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('late book consumer failure')
        with patch.object(JOBS, 'run_fixed', side_effect=fail_after_actual_job):
            with self.assertRaisesRegex(RuntimeError, 'late book consumer'):
                self.teach(pupil)
        self.assertEqual(self.snapshot(), before)

    def test_codec_gm_restore_and_teacher_forgetting_retain_actual_history_and_native_use(self):
        pupil = self.pokemon()
        self.e.gm.set_move(self.t, '열풍', add=False, reason='teacher forgets after immutable mastery acquisition')
        self.teach(pupil)
        self.e.gm.snapshot('book Tutor learned')
        self.e.gm.set_move(pupil, '열풍', add=False, reason='later pupil forgetting')
        self.e.gm.restore('book Tutor learned')
        actors = {value.entity_id: value for value in self.e.everyone}
        self.t = actors[self.t.entity_id]; pupil = actors[pupil.entity_id]
        self.assertIn('move/열풍', usable_moves(self.e, pupil))
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        actors = {value.entity_id: value for value in loaded.everyone}
        self.e = loaded; self.rules = loaded.r
        self.t = actors[self.t.entity_id]; pupil = actors[pupil.entity_id]
        self.assertEqual(self.record(pupil)['personal_tutor_acquisition_receipt'], self.acquisition)
        self.teach(self.pokemon())
        self.assertTrue(self.e.validate_state()['valid'])

    def test_corrupt_book_record_or_forgotten_log_cannot_pass_codec(self):
        for field in ('source', 'paid_tp', 'teacher', 'selection', 'legality', 'admission', 'log'):
            with self.subTest(field=field):
                self.start(); pupil = self.pokemon(); self.teach(pupil)
                row = self.record(pupil)
                if field == 'source': row[PERSONAL.MARKER] = CSV_SOURCE
                elif field == 'paid_tp': row['paid_tp'] = 0
                elif field == 'teacher': row['teacher_id'] = 'trainer/forged'
                elif field == 'selection': row['personal_tutor_acquisition_receipt']['selection']['values'][0] = 'move/파도타기'
                elif field == 'legality': row['personal_tutor_legality']['memberships'] = []
                elif field == 'admission': row['tutoring_admission']['damage_base'] = 0
                else:
                    self.e.gm.set_move(pupil, '열풍', add=False, reason='actual forgotten learned Move')
                    pupil.spec['move_learning_log'][-1]['personal_tutor_legality']['memberships'] = []
                with self.assertRaises(Exception):
                    CODEC.dump_engine(self.e)

    def test_permanent_teaching_blocks_retraining_even_after_recipient_forgets(self):
        pupil = self.pokemon(); self.teach(pupil)
        learned = deepcopy(self.record(pupil))
        self.transfer(pupil)
        self.assertEqual(self.record(pupil), learned)
        self.assertIn('move/열풍', usable_moves(self.e, pupil))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'different trainer'):
            self.teach(pupil, '두번차기')
        self.assertEqual(self.snapshot(), before)
        self.e.gm.set_move(pupil, '열풍', add=False, reason='pupil later forgets the permanent teaching')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'irreversible|permanent'):
            self.e.retrain_trainer_source(self.t, PERSONAL.FEATURE,
                request_id='book-tutor/retrain', reason='trainer attempts to remove completed permanent source',
                gm_decision={'allowed': True, 'reason': 'GM reviewed actual source'}, retained_dependencies={})
        self.assertEqual(self.snapshot(), before)

    def test_actual_type_sync_learning_sources_are_reused_and_original_proof_survives_later_sync(self):
        self.start(('열탕', '물대포', '아쿠아테일'))
        pupil = self.pokemon('이상해씨')
        helper = SimpleNamespace(p=pupil)
        args = type_fixture.TypeSyncTests.args(helper, pupil)
        self.e.gm.observe_type_sync(pupil, **args)
        for move in ('열탕', '물대포', '아쿠아테일'):
            self.teach(pupil, move)
        first = deepcopy(self.record(pupil, '열탕')['personal_tutor_legality'])
        later = type_fixture.TypeSyncTests.args(helper, pupil,
            application_id='later-electric-sync', chosen_type='전기', replace_type='독')
        self.e.gm.observe_type_sync(pupil, **later)
        self.assertEqual(self.record(pupil, '열탕')['personal_tutor_legality'], first)
        CODEC.dump_engine(self.e)
        self.start(('열탕', '물대포', '아쿠아테일')); pupil = self.pokemon('이상해씨')
        args = type_fixture.TypeSyncTests.args(SimpleNamespace(p=pupil), pupil,
            learning={'exceptions': {'move/열탕': {'allowed': False, 'reason': 'actual source-backed GM learning exception'}}})
        self.e.gm.observe_type_sync(pupil, **args)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'not legal'):
            self.teach(pupil, '열탕')
        self.assertEqual(self.snapshot(), before)

    def test_live_learning_list_mutation_cannot_authorize_incompatible_book_teaching(self):
        self.start(('파도타기', '열풍', '두번차기')); pupil = self.pokemon()
        changed = deepcopy(self.rules.learnsets['브케인'])
        changed['tutor'].append('파도타기')
        with patch.dict(self.rules.learnsets, {'브케인': changed}):
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, 'learnset/source'):
                self.teach(pupil, '파도타기')
            self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
