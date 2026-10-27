"""Only the two explicit CSV deltas; all common class obligations keep the Book owners."""
from copy import deepcopy
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

import test_book_chronicler_acquisition as fixture
import test_book_chronicler_actions as actions
import test_category2_type_sync as type_fixture
from engine import Engine, Rules
import action_points as AP
import activity_jobs as JOBS
import chronicler as CH
import move_state as M
import pokemon_teaching as TEACH
import state_codec as CODEC
import state_grants as G
import world_entities as WORLD


class ChroniclerCSVTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    setUp = fixture.ChroniclerAcquisitionTests.setUp
    setup = fixture.ChroniclerAcquisitionTests.setup
    add = fixture.ChroniclerAcquisitionTests.add
    acquire = fixture.ChroniclerAcquisitionTests.acquire
    whole = fixture.ChroniclerAcquisitionTests.whole
    rejected = fixture.ChroniclerAcquisitionTests.rejected
    valid = fixture.ChroniclerAcquisitionTests.valid
    restore = fixture.ChroniclerAcquisitionTests.restore
    combat = fixture.ChroniclerAcquisitionTests.combat
    next_turn = fixture.ChroniclerAcquisitionTests.next_turn
    use = fixture.ChroniclerAcquisitionTests.use
    witness = fixture.ChroniclerAcquisitionTests.witness
    record = fixture.ChroniclerAcquisitionTests.record
    archive_subject = fixture.ChroniclerAcquisitionTests.archive_subject
    archive_move = fixture.ChroniclerAcquisitionTests.archive_move
    archive_place = fixture.ChroniclerAcquisitionTests.archive_place
    new_day = fixture.ChroniclerAcquisitionTests.new_day
    other_owner = actions.ChroniclerActionTests.other_owner
    tutor = actions.ChroniclerActionTests.tutor

    def csv_record(self, target=None, **extra):
        options = dict(kind='pokemon', reason='actual CSV observed subject', request_id='csv-record', edition=CH.CSV_RECORD)
        options.update(extra)
        return CH.record(self.e, self.t, self.b if target is None else target, **options)

    def cold(self):
        identities = {name:getattr(self, name).entity_id for name in ('t', 'p', 'b', 'u', 'v', 'c') if hasattr(self, name)}
        self.e = CODEC.load_engine(Rules(fixture.ROOT, ruleset='core'), json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])

    def machine_pool(self, pokemon):
        # Actual inventory units, species compatibility, one-hour use and paid native receipts.
        for code in ('TM24', 'TM72', 'TM94'):
            self.t.spec.setdefault('items', {})[code] = 1
            TEACH.register_machine(self.e, self.t, instance_id='csv-prior-' + code, code=code)
            TEACH.teach_machine(self.e, self.t, target=pokemon, instance_id='csv-prior-' + code)
        self.assertEqual(M.describe(self.e.r, pokemon.spec)['taught_count'], 3)

    def test_csv_record_zero_ap_keeps_native_swift_and_separate_extended_archive(self):
        self.whole()
        AP.spend(self.t, AP.available(self.t))
        self.combat(self.t)
        self.rejected(lambda:self.record(self.b, 'pokemon', 'book-no-ap'), 'one available AP')
        row = self.csv_record()
        self.assertEqual((AP.available(self.t), self.t.budget['swift'], row['status']), (0, 0, 'provisional'))
        self.assertEqual(row['edition'], CH.CSV_RECORD)
        self.assertEqual(self.csv_record(), row)
        self.rejected(lambda:self.csv_record(edition=None), 'replay cannot change')
        self.rejected(lambda:CH.archive(self.e, self.t, row['id'], seconds=600, reason='combat archival'), 'encounter')
        self.csv_record(self.p, request_id='csv-second')
        self.assertEqual(self.t.budget['standard'], 0)
        self.rejected(lambda:self.csv_record(self.p, request_id='csv-third'), 'Swift action unavailable')
        self.e.end_of_turn(self.t)
        self.e.end_round()
        self.e.end_scene()
        before = self.e.elapsed_seconds
        CH.archive(self.e, self.t, row['id'], seconds=600, reason='actual separate Extended archival')
        self.assertEqual(self.e.elapsed_seconds, before + 600)
        self.assertEqual(CH.archived(self.t, 'profile'), {self.b.entity_id})
        self.cold()
        self.assertEqual(self.csv_record(), self.t.spec[CH.KEY]['records'][row['id']])
        self.valid()

    def test_csv_interrupt_zero_ap_still_borrows_the_native_next_swift(self):
        self.whole()
        AP.spend(self.t, AP.available(self.t))
        self.combat(self.b, count=20)
        trigger = {'kind':'turn', 'actor_id':self.b.entity_id, 'serial':self.b.custom_conditions['combat_turn_serial'], 'round':self.e.round_no}
        row = CH.record_interrupt(self.e, self.t, self.b, kind='pokemon', reason='actual CSV interruption', request_id='csv-interrupt',
            trigger=trigger, edition=CH.CSV_RECORD)
        self.assertEqual((row['status'], AP.available(self.t), self.e.initiative_reaction_status()['frames']), ('provisional', 0, 0))
        self.cold()
        self.e.end_of_turn(self.b)
        self.e.end_round()
        self.combat(self.t)
        self.assertEqual(self.t.budget, {'standard':1, 'shift':1, 'swift':0})
        self.valid()

    def test_exact_csv_sources_drift_replay_and_late_record_failure_are_atomic(self):
        self.whole()
        self.rejected(lambda:self.csv_record(edition=CH.CSV_TUTOR), 'exact reviewed')
        with patch.object(CH, 'CSV_SHA', '0' * 64):
            self.rejected(self.csv_record, 'source changed')
            self.rejected(lambda:self.tutor(self.p, 'move/전기자석파', edition=CH.CSV_TUTOR), 'source changed')
        native = Engine.log
        def fail(engine, *args, **kwargs):
            native(engine, *args, **kwargs)
            raise ValueError('injected late CSV record failure')
        with patch.object(Engine, 'log', fail):
            self.rejected(self.csv_record, 'injected late')
        self.assertIsNone(CH.state(self.t))
        self.csv_record()
        self.rejected(lambda:self.csv_record(self.p), 'replay cannot change')
        self.valid()

    def test_own_csv_lesson_exempts_only_the_paid_move_quota_and_survives_cold_restore(self):
        self.whole()
        self.machine_pool(self.p)
        self.archive_move('move/차지빔')
        self.rejected(lambda:self.tutor(self.p, 'move/차지빔'), 'combined TM/Tutor')
        balance, elapsed = self.p.spec['tutor_points'], self.e.elapsed_seconds
        result = self.tutor(self.p, 'move/차지빔', edition=CH.CSV_TUTOR)
        self.assertEqual((result['classification'], result['point_cost']), ('taught', 2))
        self.assertEqual((self.p.spec['tutor_points'], self.e.elapsed_seconds), (balance - 2, elapsed + 3600))
        limits = M.describe(self.e.r, self.p.spec)
        self.assertEqual((limits['taught_count'], limits['slot_count'], limits['total']), (3, 6, 6))
        proof = self.p.spec['move_learning']['move/차지빔']['archive_tutor_edition']
        self.assertEqual(proof, {'source':CH.CSV_TUTOR, 'teacher_id':self.t.entity_id, 'pokemon_id':self.p.entity_id, 'owner_id':self.t.entity_id})
        self.rejected(lambda:self.e.gm.set_move(self.p, 'move/전기쇼크', reason='explicit seventh Move observation'), 'capacity')
        self.new_day()
        self.rejected(lambda:self.tutor(self.p, 'move/전기자석파', edition=CH.CSV_TUTOR), 'archived Technique')
        self.archive_move('move/전기자석파')
        self.rejected(lambda:self.tutor(self.p, 'move/전기자석파', edition=CH.CSV_TUTOR), 'only once')
        self.rejected(lambda:self.tutor(self.p, 'move/전기자석파'), 'only once')
        self.cold()
        self.assertEqual(M.describe(self.e.r, self.p.spec)['taught_count'], 3)
        self.assertTrue(CH.tutor_pool_exempt(self.e.r, self.p.spec, 'move/차지빔'))
        self.e.gm.set_move(self.p, 'move/차지빔', add=False, reason='actual explicit forgetting of the CSV lesson')
        self.assertFalse(CH.tutor_pool_exempt(self.e.r, self.p.spec, 'move/차지빔'))
        self.rejected(lambda:G.grant(self.p, 'moves', 'move/차지빔', 'independent-paid-lesson', 'feature',
            tutor_points=2, rule_id='feat/기술-가르침'), 'combined TM/Tutor')
        self.rejected(lambda:self.tutor(self.p, 'move/전기자석파'), 'only once')
        self.valid()

    def test_book_history_blocks_later_csv_and_other_owner_csv_keeps_the_quota(self):
        self.whole()
        self.other_owner()
        self.archive_move('move/전기자석파')
        self.tutor(self.p, 'move/전기자석파')
        self.new_day()
        self.archive_move('move/10만볼트')
        self.rejected(lambda:self.tutor(self.p, 'move/10만볼트', edition=CH.CSV_TUTOR), 'only once')
        result = self.tutor(self.v, 'move/10만볼트', edition=CH.CSV_TUTOR)
        self.assertEqual(result['classification'], 'taught')
        self.assertFalse(CH.tutor_pool_exempt(self.e.r, self.v.spec, 'move/10만볼트'))
        self.assertEqual(M.describe(self.e.r, self.v.spec)['taught_count'], 1)
        self.new_day()
        self.rejected(lambda:self.tutor(self.v, 'move/전기자석파'), 'only once')
        self.rejected(lambda:self.tutor(self.v, 'move/전기자석파', edition=CH.CSV_TUTOR), 'only once')
        self.cold()
        self.valid()

    def test_csv_daily_cost_and_late_teaching_failure_keep_every_native_resource_atomic(self):
        self.whole()
        self.other_owner()
        self.archive_move('move/10만볼트')
        self.p.spec['tutor_points'] = 1
        self.rejected(lambda:self.tutor(self.p, 'move/10만볼트', edition=CH.CSV_TUTOR), 'two actual Tutor Points')
        self.p.spec['tutor_points'] = 8
        native = JOBS.run_fixed
        def fail(*args, **kwargs):
            native(*args, **kwargs)
            raise ValueError('injected late CSV teaching failure')
        with patch.object(JOBS, 'run_fixed', fail):
            self.rejected(lambda:self.tutor(self.p, 'move/10만볼트', edition=CH.CSV_TUTOR), 'injected late')
        self.tutor(self.p, 'move/10만볼트', edition=CH.CSV_TUTOR)
        self.rejected(lambda:self.tutor(self.v, 'move/10만볼트', edition=CH.CSV_TUTOR), 'daily frequency')
        self.assertEqual(len(self.t.spec[CH.KEY]['tutoring']), 1)
        self.cold()
        self.valid()

    def test_csv_pool_provenance_and_once_history_cannot_be_forged_on_restore(self):
        self.whole()
        self.archive_move('move/10만볼트')
        self.tutor(self.p, 'move/10만볼트', edition=CH.CSV_TUTOR)
        saved = self.e.export_state()
        record = self.p.spec['move_learning']['move/10만볼트']
        bad = deepcopy(record)
        bad['archive_tutor_edition']['source'] = CH.CSV_RECORD
        spec = deepcopy(self.p.spec)
        spec['move_learning']['move/10만볼트'] = bad
        with self.assertRaisesRegex(ValueError, 'exact reviewed'):
            M.validate_spec(self.e.r, spec)
        bad = deepcopy(record)
        bad['archive_tutor_edition']['teacher_id'] = None
        spec['move_learning']['move/10만볼트'] = bad
        with self.assertRaisesRegex(ValueError, 'permanent learning provenance'):
            M.validate_spec(self.e.r, spec)
        self.t.spec[CH.KEY]['tutoring'].append(deepcopy(self.t.spec[CH.KEY]['tutoring'][0]))
        with self.assertRaisesRegex(ValueError, 'only once'):
            CH.validate(self.e)
        self.e = CODEC.load_engine(self.e.r, saved)
        self.assertTrue(self.e.validate_state()['valid'])

    def type_sync(self, **extra):
        options = type_fixture.TypeSyncTests.args(SimpleNamespace(p=self.p), self.p, replace_type='전기', **extra)
        return self.e.gm.observe_type_sync(self.p, **options)

    def test_type_sync_false_filters_only_machine_tutor_routes_for_both_consumers(self):
        self.whole()
        for mid in ('move/10만볼트', 'move/아이언테일', 'move/물대포'):
            self.archive_move(mid)
        exceptions = {mid:{'allowed':False, 'reason':'actual GM Type Sync learning prohibition'}
            for mid in ('move/10만볼트', 'move/아이언테일', 'move/물대포')}
        self.type_sync(level_up=[{'level':1, 'move_id':'move/전광석화'}, {'level':11, 'move_id':'move/물대포'}],
            learning={'exceptions':exceptions})
        self.assertEqual(self.p.spec['species'], '피카츄')  # supported alias remains in the original receipt
        self.assertEqual(CH.learning_routes(self.e, self.p, 'move/물대포'), ['level_up'])
        for mid in ('move/10만볼트', 'move/아이언테일'):
            self.assertEqual(CH.learning_routes(self.e, self.p, mid), [])
            self.rejected(lambda mid=mid:self.tutor(self.p, mid, edition=CH.CSV_TUTOR), 'Level Up, TM or Tutor')
        self.combat(self.p, count=20)
        for mid in ('move/10만볼트', 'move/아이언테일'):
            self.rejected(lambda mid=mid:CH.recreation(self.e, self.t, self.p, mid), 'Level Up, TM or Tutor')
        CH.recreation(self.e, self.t, self.p, 'move/물대포')
        self.use(self.p, self.b, 'move/물대포', face=1)
        self.e.end_of_turn(self.p)
        self.e.end_round()
        self.e.end_scene()
        self.assertNotIn('move/물대포', self.p.moves)
        self.tutor(self.p, 'move/물대포', edition=CH.CSV_TUTOR)
        self.assertIn('move/물대포', self.p.moves)
        for species in ('pokemon/이상해씨', 'unregistered species'):
            bad = deepcopy(self.p.spec)
            bad[M.HISTORY]['move/물대포'][-1]['species_id'] = species
            with self.assertRaisesRegex(ValueError, 'natural opportunity'):
                M.validate_history(self.e.r, bad)
        bad = deepcopy(self.p.spec)
        duplicate = deepcopy(bad[M.HISTORY]['move/물대포'][-1])
        duplicate['species_id'] = '피카츄'
        bad[M.HISTORY]['move/물대포'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'duplicate natural opportunity'):
            M.validate_history(self.e.r, bad)
        self.cold()
        self.valid()

    def test_type_sync_true_needs_actual_machine_and_both_consumers_keep_permanent_history(self):
        self.whole()
        for mid in ('move/열탕', 'move/물의파동', 'move/아쿠아커터'):
            self.archive_move(mid)
        self.type_sync()
        self.assertIn('tm', CH.learning_routes(self.e, self.p, 'move/열탕'))
        self.assertIn('tutor', CH.learning_routes(self.e, self.p, 'move/물의파동'))
        self.assertEqual(CH.learning_routes(self.e, self.p, 'move/아쿠아커터'), [])
        self.rejected(lambda:self.tutor(self.p, 'move/아쿠아커터'), 'Level Up, TM or Tutor')
        self.combat(self.p, count=20)
        self.rejected(lambda:CH.recreation(self.e, self.t, self.p, 'move/아쿠아커터'), 'Level Up, TM or Tutor')
        CH.recreation(self.e, self.t, self.p, 'move/물의파동')
        self.use(self.p, self.b, 'move/물의파동', face=1)
        self.e.end_of_turn(self.p)
        self.e.end_round()
        self.e.end_scene()
        self.assertNotIn('move/물의파동', self.p.moves)
        result = self.tutor(self.p, 'move/열탕')
        self.assertEqual((result['classification'], result['point_cost']), ('taught', 2))
        receipt = deepcopy(self.p.spec['move_learning']['move/열탕'])
        options = type_fixture.TypeSyncTests.args(SimpleNamespace(p=self.p), self.p,
            application_id='later-fire-sync', chosen_type='불꽃', replace_type='물',
            learning={'exceptions':{'move/열탕':{'allowed':False, 'reason':'later learning prohibition does not erase completed permanent history'}}})
        self.e.gm.observe_type_sync(self.p, **options)
        self.cold()
        self.assertEqual(self.p.spec['move_learning']['move/열탕'], receipt)
        self.assertIn('move/열탕', self.p.moves)
        self.valid()


if __name__ == '__main__':
    unittest.main()
