"""CSV8 teaching uses the native learning, occupancy and historical owners."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'input').is_dir() else Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_book_personal_tutoring as book
import test_category2_type_sync as sync_fixture
import native_scenario_fixture as NATIVE
import personal_tutoring as P
import move_state as M
import pokemon_teaching as T
import state_codec as CODEC
import trainer_feature_acquisition as A
import vitamin_moves as V
from encounter import usable_moves
from engine import Combatant, Engine, Rules


class CsvPersonalTutoringTests(unittest.TestCase):
    add = book.BookPersonalTutoringTests.add
    start = book.BookPersonalTutoringTests.start
    pokemon = book.BookPersonalTutoringTests.pokemon
    snapshot = book.BookPersonalTutoringTests.snapshot
    record = book.BookPersonalTutoringTests.record
    transfer = book.BookPersonalTutoringTests.transfer
    sync_move = book.BookPersonalTutoringTests.sync_move

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.start(('파도타기', '열풍', '두번차기'), source=P.CSV_SOURCE)

    def teach(self, pokemon, move='파도타기', **options):
        return self.e.teach_personal_tutor(self.t, target=pokemon, move_id=move,
            seconds=60, reason='GM observed completed CSV Extended teaching',
            source_clause_id=P.CSV_SOURCE, **options)

    def reject(self, action, reason):
        NATIVE.assert_rejected_unchanged(self.e, action, reason_pattern=reason)

    def dose(self, pupil, count):
        self.t.spec['items']['타우린'] = count
        for _ in range(count):
            self.e.use_item(self.t, '타우린', pupil)

    def test_public_csv_ignores_species_compatibility_but_pays_supplemented_two_tp(self):
        pupil = self.pokemon()
        result = self.teach(pupil)
        self.assertEqual((result['source_clause_id'], result['point_cost']), (P.CSV_SOURCE, 2))
        self.assertEqual((pupil.spec['tutor_points'], self.e.elapsed_seconds), (10, 60))
        self.assertIn('move/파도타기', usable_moves(self.e, pupil))
        row = self.record(pupil, '파도타기')
        self.assertNotIn('personal_tutor_legality', row)
        self.assertEqual(row['personal_tutor_cost_source'], P.CSV_COST_SOURCE)
        self.assertEqual(row['personal_tutor_acquisition_receipt'], self.acquisition)
        state = M.describe(self.rules, pupil.spec)
        self.assertEqual((state['slot_count'], state['taught_count'], state['vm_moves']), (2, 1, []))
        self.assertEqual(state['personal_tutor_moves'], ['move/파도타기'])
        self.assertEqual((state['vitamin_state']['reserved'], state['vitamin_state']['occupied']), (1, 1))

    def test_source_receipt_cannot_be_cherry_picked_and_acquisition_is_not_forged_projection(self):
        for mode in ('book', 'raw', 'missing', 'nonselected', 'instance', 'unknown'):
            with self.subTest(mode=mode):
                self.start(('파도타기', '열풍', '두번차기'),
                    source=P.SOURCE if mode == 'book' else P.CSV_SOURCE,
                    acquire=mode not in ('raw', 'missing'))
                pupil = self.pokemon()
                if mode == 'raw':
                    self.t.spec['feats'].append(P.FEATURE)
                    self.t.spec['feature_choices'] = {P.FEATURE: ['move/파도타기', 'move/열풍', 'move/두번차기']}
                if mode == 'unknown':
                    self.reject(lambda: self.e.teach_personal_tutor(self.t, target=pupil,
                        move_id='파도타기', seconds=60, reason='unknown exact source',
                        source_clause_id='unreviewed/PersonalTutor'), 'reviewed exact source')
                else:
                    self.reject(lambda: self.teach(pupil, '방어' if mode == 'nonselected' else '파도타기',
                        **({'feature_instance_id': 'forged:2'} if mode == 'instance' else {})),
                        'acquired|selection|selected')
        self.setUp(); pupil = self.pokemon()
        self.reject(lambda: self.e.teach_personal_tutor(self.t, target=pupil,
            move_id='열풍', seconds=60, reason='CSV receipt cannot enter book route'), 'book|selection')

    def test_one_current_move_is_not_one_ever_and_replacement_releases_reservation(self):
        pupil = self.pokemon()
        self.teach(pupil)
        self.reject(lambda: self.teach(pupil, '열풍'), 'one.*Personal Tutor|one.*personal')
        self.sync_move(self.e, pupil, '파도타기')
        self.teach(pupil, '열풍', replace='파도타기')
        self.assertEqual(pupil.spec['move_type_sync']['history'][-1]['status'], 'forgotten')
        self.assertNotIn('move/파도타기', usable_moves(self.e, pupil))
        self.assertEqual(M.vitamin_state(self.rules, pupil.spec)['reserved'], 1)
        self.e.gm.set_move(pupil, '열풍', add=False, reason='actual forgetting releases current reservations')
        self.assertEqual(M.vitamin_state(self.rules, pupil.spec)['reserved'], 0)
        self.teach(pupil, '두번차기')
        state = M.describe(self.rules, pupil.spec)
        self.assertEqual((state['slot_count'], state['taught_count']), (2, 0))
        self.assertEqual(len(pupil.spec['move_learning_log']), 3)

    def test_weighted_total_preserves_five_actual_moves_and_regular_taught_quota(self):
        self.start(('파도타기', '열풍', '두번차기'), source=P.CSV_SOURCE)
        natural = ['몸통박치기', '울음소리', '덩굴채찍', '씨뿌리기', '성장']
        pupil = self.pokemon('이상해씨', 50, moves=natural)
        self.reject(lambda: self.teach(pupil), 'capacity')
        self.teach(pupil, replace='울음소리')
        state = M.describe(self.rules, pupil.spec)
        self.assertEqual((len(state['known']), state['slot_count']), (5, 6))
        self.setUp(); pupil = self.pokemon()
        for move in ('열풍', '누르기', '잠꼬대'):
            M.observe_learning(self.e, pupil, move, method='tutor', source=T.MOVE_TUTOR,
                paid_tp=2, reason='actual three occupied taught slots')
        self.reject(lambda: self.teach(pupil), 'TM/Tutor')
        self.teach(pupil, replace='누르기')
        self.assertEqual(M.describe(self.rules, pupil.spec)['taught_count'], 3)

    def test_actual_vitamins_and_vm_compete_without_conflating_move_routes(self):
        pupil = self.pokemon(); self.dose(pupil, 4); self.teach(pupil)
        self.t.spec['items'][V.HEART] = 2
        points = pupil.spec['tutor_points']
        self.e.use_item(self.t, V.HEART, pupil)
        self.assertEqual((len(pupil.spec['vitamins']), pupil.spec['tutor_points']), (4, points))
        self.e.gm.set_move(pupil, '파도타기', add=False, reason='actual forgetting releases one Vitamin slot')
        self.e.use_item(self.t, V.HEART, pupil)
        self.assertEqual((len(pupil.spec['vitamins']), pupil.spec['tutor_points']), (5, points + 2))
        self.reject(lambda: self.teach(pupil, '열풍'), 'Vitamin.*capacity|Vitamin slot')
        previous = self.rules
        self.rules = Rules(ROOT, ruleset='all')
        self.addCleanup(setattr, self, 'rules', previous)
        self.setUp(); pupil = self.pokemon(); self.dose(pupil, 3)
        M.observe_vm_learning(self.e, pupil, '냉동빔', application_id='csv-shared-vm',
            reason='actual separately completed VM')
        self.teach(pupil)
        state = M.describe(self.rules, pupil.spec)
        self.assertEqual((state['slot_count'], state['vm_moves'], state['personal_tutor_moves']),
            (4, ['move/냉동빔'], ['move/파도타기']))
        self.assertEqual(state['vitamin_state']['reserved'], 2)

    def test_general_errata_level_and_points_and_native_actor_boundaries_precede_cost(self):
        pupil = self.pokemon(level=19)
        self.reject(lambda: self.teach(pupil, '열풍'), 'tutoring restriction')
        self.e.gm.set_level(pupil, 30, reason='actual eligibility')
        self.teach(pupil)
        self.e.gm.set_level(pupil, 19, reason='historical teaching does not repeat')
        self.assertEqual(self.record(pupil, '파도타기')['learned_at_level'], 30)
        for mode in ('points', 'private', 'foreign', 'known', 'replacement'):
            with self.subTest(mode=mode):
                self.setUp(); pupil = self.pokemon(points=1 if mode == 'points' else 12)
                if mode == 'private': pupil = Combatant(self.rules, deepcopy(pupil.spec))
                if mode == 'foreign': self.transfer(pupil)
                if mode == 'known': self.e.gm.set_move(pupil, '파도타기', reason='actual existing Move')
                self.reject(lambda: self.teach(pupil,
                    **({'replace': '熱風'} if mode == 'replacement' else {})),
                    'Tutor Points|registered|actual|different trainer|already|replacement|distinct actors share identity')

    def test_csv_compatibility_waiver_keeps_independent_type_sync_exception(self):
        pupil = self.pokemon('이상해씨')
        args = sync_fixture.TypeSyncTests.args(SimpleNamespace(p=pupil), pupil,
            learning={'exceptions': {'move/파도타기': {'allowed': False,
                'reason': 'actual independent GM learning exception'}}})
        self.e.gm.observe_type_sync(pupil, **args)
        # The CSV explicitly overrides compatibility, not global recipient restrictions.
        self.reject(lambda: self.teach(pupil), 'Type Sync|learning exception|forbids')

    def test_sourced_unlimited_taught_quota_does_not_waive_csv_one_move_or_vitamin_limit(self):
        previous = self.rules
        self.rules = Rules(ROOT, ruleset='all')
        self.addCleanup(setattr, self, 'rules', previous)
        self.setUp(); pupil = self.pokemon()
        self.e.gm.set_ability(pupil, 'ability/기부자', reason='actual original CSV40 acquired Ability')
        self.teach(pupil)
        state = M.describe(self.rules, pupil.spec)
        self.assertIsNone(state['taught'])
        self.assertEqual((state['slot_count'], state['vitamin_state']['reserved']), (2, 1))
        self.reject(lambda: self.teach(pupil, '열풍'), 'one.*Personal Tutor|one.*personal')

    def test_native_actual_move_use_and_later_natural_opportunity_keep_csv_slot_reservation(self):
        from builder import build_pokemon
        from grid import Grid
        import pokemon_entities as ENTITIES
        self.start(('화염방사', '열풍', '두번차기'), source=P.CSV_SOURCE)
        pupil = self.pokemon(); self.teach(pupil, '화염방사')
        self.e.gm.set_level(pupil, 40, reason='later actual natural opportunity')
        state = M.describe(self.rules, pupil.spec)
        self.assertEqual((state['slot_count'], state['taught_count']), (2, 0))
        self.e.grid = Grid(8, 8)
        self.e.gm.set_position(pupil, (1, 1), reason='actual native battle position')
        foe = Combatant(self.rules, build_pokemon(self.rules, '이브이', 30,
            name='CSV native target', moves=['몸통박치기'], abilities=[]))
        self.e.gm.add_combatant(foe, pos=(2, 1), side='enemy', reason='actual opposing target')
        for actor in (pupil, foe):
            NATIVE.prepare_body(self.e, actor, size=actor.spec['size'], offsets=[(0, 0)],
                reason='actual native combatant body')
        ENTITIES.observe_loyalty(self.e, pupil, 3, reason='GM observed willing battle partner')
        self.e.start_round([pupil, foe])
        self.e.start_of_turn(pupil, initiative_count=20)
        hp = foe.hp
        with patch.object(Engine, 'd20', return_value=18):
            dealt = self.e.use_move_on(pupil, foe, 'move/화염방사', [foe], set_damage=True)
        self.assertIsInstance(dealt, int)
        self.assertGreater(dealt, 0, self.e.log_lines)
        self.assertLess(foe.hp, hp, self.e.log_lines)
        self.assertEqual(M.describe(self.rules, pupil.spec)['slot_count'], 2)

    def test_dietician_history_retains_old_reservation_but_cannot_authorize_new_learning(self):
        import book_chef_fixture as CHEF_FIX
        import chef_cooking as CHEF
        import items as ITEMS
        import vitamin_capacity as CAPACITY
        self.t = self.add(CHEF_FIX.trainer_spec(self.rules, 'CSV actual Dietician', intuition=5))
        self.e.gm.set_skill(self.t, '일반 지식', 3, reason='actual Novice prerequisite')
        for move in ('파도타기', '열풍', '두번차기'):
            self.e.gm.set_move(self.t, move, reason='actual permanently known acquisition choices')
        A.acquire_personal_tutor(self.e, self.t, acquisition_request_id='csv-dietician-tutor',
            selected_values=['파도타기', '열풍', '두번차기'], source_clause_id=P.CSV_SOURCE,
            lifecycle_policy=deepcopy(A.LIFECYCLE_UNRESOLVED))
        for uid in (CHEF.CLASS, CHEF.DIETICIAN): CHEF_FIX.acquire(self.e, self.t, uid)
        ITEMS.register_feats(self.e, self.t)
        pupil = self.pokemon(); self.dose(pupil, 6); self.teach(pupil)
        history = deepcopy(pupil.spec[CAPACITY.HISTORY])
        self.assertEqual(history[-1]['kind'], 'personal_tutor')
        self.t = self.transfer(pupil)
        state = M.vitamin_state(self.rules, pupil.spec)
        self.assertEqual((state['capacity'], state['historical_capacity'], state['occupied']), (5, 7, 7))
        self.assertEqual(pupil.spec[CAPACITY.HISTORY], history)
        self.e.gm.set_skill(self.t, '일반 지식', 3, reason='actual new owner prerequisite')
        for move in ('파도타기', '열풍', '두번차기'):
            self.e.gm.set_move(self.t, move, reason='actual new owner known selection')
        A.acquire_personal_tutor(self.e, self.t, acquisition_request_id='csv-new-owner-tutor',
            selected_values=['파도타기', '열풍', '두번차기'], source_clause_id=P.CSV_SOURCE,
            lifecycle_policy=deepcopy(A.LIFECYCLE_UNRESOLVED))
        self.e.gm.set_move(pupil, '파도타기', add=False, reason='actual old reservation released')
        self.reject(lambda: self.teach(pupil, '열풍'), 'current Vitamin slot')
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        restored = next(a for a in loaded.everyone if a.entity_id == pupil.entity_id)
        self.assertEqual(restored.spec[CAPACITY.HISTORY], history)
        self.assertEqual(M.vitamin_state(self.rules, restored.spec)['occupied'], 6)

    def test_historical_acquisition_survives_teacher_forgetting_transfer_and_two_restores(self):
        pupil = self.pokemon()
        self.e.gm.set_move(self.t, '파도타기', add=False, reason='mastery uses original known selection')
        self.teach(pupil)
        record = deepcopy(self.record(pupil, '파도타기'))
        self.e.gm.snapshot('csv learned')
        self.e.gm.set_move(pupil, '파도타기', add=False, reason='later forget')
        self.e.gm.restore('csv learned')
        actors = {a.entity_id: a for a in self.e.everyone}
        self.t = actors[self.t.entity_id]; pupil = actors[pupil.entity_id]
        self.transfer(pupil)
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        actors = {a.entity_id: a for a in self.e.everyone}
        self.t = actors[self.t.entity_id]; pupil = actors[pupil.entity_id]
        self.assertEqual(self.record(pupil, '파도타기'), record)
        self.assertIn('move/파도타기', usable_moves(self.e, pupil))
        self.assertEqual(M.vitamin_state(self.rules, pupil.spec)['reserved'], 1)
        self.reject(lambda: self.teach(pupil, '열풍'), 'different trainer')

    def test_completed_learning_blocks_retraining_even_after_forgotten_and_owner_transfer(self):
        pupil = self.pokemon()
        self.e.retrain_trainer_source(self.t, P.FEATURE,
            request_id='csv-tutor/unused-withdrawal', reason='actual unused source withdrawal',
            gm_decision={'allowed': True, 'reason': 'actual GM consultation'}, retained_dependencies={})
        self.reject(lambda: self.teach(pupil), 'acquired|selection')
        self.setUp()
        pupil = self.pokemon(); self.teach(pupil); self.transfer(pupil)
        self.e.gm.set_move(pupil, '파도타기', add=False, reason='actual later forgetting')
        self.reject(lambda: self.e.retrain_trainer_source(self.t, P.FEATURE,
            request_id='csv-tutor/retrain', reason='attempts withdrawal after permanent teaching',
            gm_decision={'allowed': True, 'reason': 'actual GM review'}, retained_dependencies={}),
            'irreversible|permanent')

    def test_explicit_replacement_uses_actual_signature_forgetting_and_refund_once(self):
        import test_book_ace_trainer_full as ACE_FIX
        helper = ACE_FIX.AceTrainerFullTests()
        helper.rules = self.rules
        helper.setUp(); self.addCleanup(helper.doCleanups)
        for mid in list(helper.p.spec['moves']):
            if mid != 'struggle':
                helper.e.gm.set_move(helper.p, mid, add=False,
                    reason='remove unrelated imported unknown-route fixture Moves')
        helper.teach('alternative_energy', 'move/막치기')
        self.e, self.t, pupil = helper.e, helper.t, helper.p
        self.e.gm.set_level(pupil, 30, reason='actual general tutoring level before CSV teaching')
        self.e.gm.set_skill(self.t, '일반 지식', 3, reason='actual General Education prerequisite')
        for move in ('파도타기', '열풍', '두번차기'):
            self.e.gm.set_move(self.t, move, reason='actual immutable acquisition selection')
        A.acquire_personal_tutor(self.e, self.t, acquisition_request_id='csv-signature-tutor',
            selected_values=['파도타기', '열풍', '두번차기'], source_clause_id=P.CSV_SOURCE,
            lifecycle_policy=deepcopy(A.LIFECYCLE_UNRESOLVED))
        points = pupil.spec['tutor_points']
        self.teach(pupil, replace='막치기')
        self.assertEqual(pupil.spec['tutor_points'], points - 2 + 1)
        self.assertEqual(pupil.spec['signature_techniques'][-1]['status'], 'forgotten')
        self.e.gm.set_move(pupil, '파도타기', add=False, reason='later independent forgetting')
        self.assertEqual(pupil.spec['tutor_points'], points - 2 + 1)

    def test_unknown_versions_and_corrupt_historical_source_cost_and_receipt_are_rejected(self):
        pupil = self.pokemon()
        before = self.snapshot()
        with patch.dict(self.rules.ruleset.unit_versions, {P.CSV_SOURCE: 99}):
            from ruleset import RuleSelection
            rebuilt = RuleSelection(self.rules.ruleset, list(self.rules.selection.units.values()))
            with patch.object(self.rules, 'selection', rebuilt):
                with self.assertRaisesRegex(ValueError, 'version'):
                    self.teach(pupil)
        self.assertEqual(self.snapshot(), before)
        original_read = Path.read_bytes
        def changed_source(path):
            return b'changed English cost source' if str(path).replace('\\', '/').endswith(P.CSV_COST_SOURCE['file']) else original_read(path)
        with patch.object(Path, 'read_bytes', changed_source):
            self.reject(lambda: self.teach(pupil), 'English cost supplement changed')
        for mode in ('source', 'cost', 'cost_source', 'teacher', 'recipient', 'selection', 'admission', 'log'):
            with self.subTest(mode=mode):
                self.setUp(); pupil = self.pokemon(); self.teach(pupil)
                row = self.record(pupil, '파도타기')
                if mode == 'source': row[P.MARKER] = P.SOURCE
                elif mode == 'cost': row['paid_tp'] = 0
                elif mode == 'cost_source': row['personal_tutor_cost_source']['point_cost'] = 0
                elif mode == 'teacher': row['teacher_id'] = 'trainer/forged'
                elif mode == 'recipient': row['personal_tutor_recipient_id'] = 'pokemon/forged'
                elif mode == 'selection': row['personal_tutor_acquisition_receipt']['selection']['values'][0] = 'move/방어'
                elif mode == 'admission': row['tutoring_admission']['damage_base'] = 0
                else:
                    self.e.gm.set_move(pupil, '파도타기', add=False, reason='validate forgotten historical learning')
                    pupil.spec['move_learning_log'][-1]['personal_tutor_cost_source']['point_cost'] = 0
                with self.assertRaises(Exception): CODEC.dump_engine(self.e)

    def test_action_and_late_job_and_late_payment_failure_leave_world_rng_and_reservations_unchanged(self):
        import activity_jobs as JOBS
        import turn as TURN
        pupil = self.pokemon(); before = self.snapshot()
        with patch.object(TURN, 'spend', return_value=False):
            self.reject(lambda: self.teach(pupil), 'Extended action')
        original = JOBS.run_fixed
        def fail_after_job(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('late CSV job failure')
        with patch.object(JOBS, 'run_fixed', side_effect=fail_after_job):
            with self.assertRaisesRegex(RuntimeError, 'late CSV job'): self.teach(pupil)
        self.assertEqual(self.snapshot(), before)
        original_debit = T._debit_points
        def fail_after_debit(*args, **kwargs):
            original_debit(*args, **kwargs)
            raise RuntimeError('late CSV debit failure')
        with patch.object(T, '_debit_points', side_effect=fail_after_debit):
            with self.assertRaisesRegex(RuntimeError, 'late CSV debit'): self.teach(pupil)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__': unittest.main(verbosity=2)
