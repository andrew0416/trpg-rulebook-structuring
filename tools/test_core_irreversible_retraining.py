"""Actual permanent teachers and actual trainer selection withdrawal, C02-163."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Combatant, Engine, Rules
from builder import build_trainer
import acquisition_withdrawal as WITHDRAWAL
import trainer_retraining as RETRAINING
import trainer_feature_acquisition as FEATURES
import pokemon_teaching as TEACHING
import state_codec as CODEC
import state_grants as GRANTS
import test_category2_mentor_move_state as MOVE_FIXTURE
import test_category2_mentor_csv as CSV_FIXTURE
import test_category2_feature_ability_lessons as ABILITY_FIXTURE
import test_category2_type_sync as TYPE_FIXTURE
import test_category2_signature_moves as SIGNATURE_FIXTURE


class IrreversibleRetrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')
        MOVE_FIXTURE.MentorMoveStateTests.setUpClass()
        CSV_FIXTURE.MentorCSVTests.setUpClass()
        ABILITY_FIXTURE.FeatureAbilityLessonTests.setUpClass()
        TYPE_FIXTURE.TypeSyncTests.setUpClass()
        SIGNATURE_FIXTURE.SignatureMoveTests.setUpClass()

    def simple(self, feats=(), edges=(), skills=None, moves=()):
        e = Engine(self.rules, seed=163)
        a = Combatant(self.rules, build_trainer(self.rules, 'actual trainer', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            moves=list(moves), abilities=[], extra={'feats': list(feats), 'edges': list(edges),
                'skills': skills or {}, 'exp_bank': 10}))
        e.gm.add_combatant(a, reason='actual retraining participant')
        return e, a

    def sources(self, e, a):
        return {uid: RETRAINING.owned_source(e, a, uid) for uid in RETRAINING._owned(a)}

    def decisions(self, e, a, uid, *, request='retrain/one', dependencies=None):
        sources = self.sources(e, a)
        retained = {source: list(a.spec['state_grants']['sources'][source].get('withdrawal_dependencies', []))
                    for owned, source in sources.items() if owned != uid}
        for child, parents in RETRAINING._native_dependencies(e, a, RETRAINING._owned(a)).items():
            if child != uid:
                retained[sources[child]] = [sources[parent] for parent in parents]
        return dict(request_id=request, reason='actual trainer chooses retraining',
                    gm_decision={'allowed': True, 'reason': 'GM reviewed prerequisites and narrative'},
                    retained_dependencies=retained if dependencies is None else dependencies)

    def snapshot(self, e):
        return deepcopy((CODEC.dump_engine(e), e.rng.getstate(), e.log_lines))

    def restored(self, e):
        return CODEC.load_engine(e.r, json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))

    def test_unused_actual_feature_removes_selection_effect_and_spends_existing_xp_once(self):
        e, a = self.simple([TEACHING.MOVE_TUTOR], skills={'매력': 5, '포켓몬학': 3})
        a.spec['feats'].insert(0, TEACHING.MENTOR)
        TEACHING.select_mentor_skills(e, a, ['매력', '포켓몬학'], reason='actual class choices')
        e.register_abilities(a)
        decision = self.decisions(e, a, TEACHING.MOVE_TUTOR)
        source = self.sources(e, a)[TEACHING.MOVE_TUTOR]
        self.assertTrue(any(row.get(GRANTS.TAG, '').startswith(source) for row in a.registry))
        result = e.retrain_trainer_source(a, TEACHING.MOVE_TUTOR, **decision)
        self.assertNotIn(TEACHING.MOVE_TUTOR, a.spec['feats'])
        self.assertNotIn(source, a.spec['state_grants']['sources'])
        self.assertFalse(any(row.get(GRANTS.TAG, '').startswith(source) for row in a.registry))
        self.assertEqual((a.spec['exp_bank'], a.level, result['xp_paid']), (8, 20, 2))
        self.assertEqual(a.spec['trainer_xp_payments']['retrain/one']['used'], 'retraining:retrain/one')
        loaded = self.restored(e); b = loaded.everyone[0]; before = self.snapshot(loaded)
        self.assertEqual(loaded.retrain_trainer_source(b, TEACHING.MOVE_TUTOR, **decision), result)
        self.assertEqual(self.snapshot(loaded), before)
        with self.assertRaisesRegex(ValueError, 'changed'):
            loaded.retrain_trainer_source(b, TEACHING.MOVE_TUTOR, **dict(decision, reason='changed'))
        with self.assertRaisesRegex(ValueError, 'not refundable'):
            loaded.refund_trainer_xp_payment(b, 'retrain/one', reason='already consumed')
        self.assertEqual(self.snapshot(loaded), before)

    def test_move_mentor_and_egg_producers_block_their_actual_teacher_after_forgetting_and_restore(self):
        for feature, move, level in ((TEACHING.MENTOR, '화염방사', 32),
                                     (TEACHING.MOVE_TUTOR, '열풍', 30),
                                     (TEACHING.EGG_TUTOR, '두번차기', 5)):
            with self.subTest(feature=feature):
                f = MOVE_FIXTURE.MentorMoveStateTests(); f.setUp(); p = f.pokemon(level)
                f.a.spec['exp_bank'] = 10
                f.teach(p, move, feature)
                source = self.sources(f.e, f.a)[feature]
                self.assertTrue(f.a.spec['state_grants']['sources'][source]['irreversible_uses'])
                f.e.gm.set_move(p, f.r.move_id(move), add=False, reason='actual later forgetting')
                e = self.restored(f.e); a = next(x for x in e.everyone if x.entity_id == f.a.entity_id)
                decision = self.decisions(e, a, feature); before = self.snapshot(e)
                with self.assertRaisesRegex(ValueError, 'irreversible|retained grant depends'):
                    e.retrain_trainer_source(a, feature, **decision)
                with self.assertRaisesRegex(ValueError, 'irreversible'):
                    GRANTS.revoke(a, source, engine=e)
                self.assertEqual(self.snapshot(e), before)
                # Ownership removal must also fail through the normal import validator.
                a.spec['feats'].remove(feature)
                with self.assertRaises(ValueError):
                    CODEC.dump_engine(e)

    def test_failed_move_teaching_does_not_publish_teacher_use_and_real_retry_does(self):
        f = MOVE_FIXTURE.MentorMoveStateTests(); f.setUp(); p = f.pokemon(30)
        before = self.snapshot(f.e)
        import trainer_retraining
        actual_irreversible = trainer_retraining.irreversible
        def fail_after_actual_use(e, actor, uid, **effect):
            actual_irreversible(e, actor, uid, **effect)
            source = 'feature:' + actor.entity_id + ':' + uid
            self.assertIn(effect['event_id'], actor.spec['state_grants']['sources'][source]['irreversible_uses'])
            self.assertTrue(actor.spec['state_grants']['sources'][source]['irreversible_trainer_feature'])
            raise ValueError('late actual use failure')
        with patch.object(trainer_retraining, 'irreversible', side_effect=fail_after_actual_use):
            with self.assertRaisesRegex(ValueError, 'late actual use'):
                f.teach(p, '열풍', TEACHING.MOVE_TUTOR)
        self.assertEqual(self.snapshot(f.e), before)
        f.teach(p, '열풍', TEACHING.MOVE_TUTOR)
        source = self.sources(f.e, f.a)[TEACHING.MOVE_TUTOR]
        self.assertEqual(len(f.a.spec['state_grants']['sources'][source]['irreversible_uses']), 1)

    def test_csv_mentor_uses_real_acquisition_receipt_and_actual_teacher_source(self):
        f = CSV_FIXTURE.MentorCSVTests(); f.setUp(); acquisition = f.acquire(); p = f.pupil()
        f.a.spec['exp_bank'] = 10
        f.teach(p, '돌진')
        source = self.sources(f.e, f.a)[TEACHING.MENTOR]
        self.assertTrue(f.a.spec['state_grants']['sources'][source]['irreversible_uses'])
        self.assertEqual(p.spec['move_learning'][f.rules.move_id('돌진')]['mentor_acquisition_receipt'], acquisition)
        decision = self.decisions(f.e, f.a, TEACHING.MENTOR); before = self.snapshot(f.e)
        with self.assertRaisesRegex(ValueError, 'irreversible'):
            f.e.retrain_trainer_source(f.a, TEACHING.MENTOR, **decision)
        self.assertEqual(self.snapshot(f.e), before)

    def test_all_existing_permanent_ability_lesson_features_record_the_actual_teacher(self):
        for feature, (_, abilities) in ABILITY_FIXTURE.CASES.items():
            for ability in abilities:
                with self.subTest(feature=feature, ability=ability):
                    f = ABILITY_FIXTURE.FeatureAbilityLessonTests(); f.fixture(feature)
                    if feature=='feat/효과적인-방법':
                        import training_features as TRAINING
                        f.teacher.spec.setdefault('feats',[]).append(TRAINING.FOCUSED)
                    f.teacher.spec['exp_bank'] = 10
                    result = f.teach(ability)
                    source = self.sources(f.engine, f.teacher)[feature]
                    uses = f.teacher.spec['state_grants']['sources'][source]['irreversible_uses']
                    self.assertIn(result['job_id'], uses)
                    self.assertIn(ability, __import__('ability_transitions').known(f.pupil))
                    decision = self.decisions(f.engine, f.teacher, feature); before = self.snapshot(f.engine)
                    with self.assertRaisesRegex(ValueError, 'irreversible'):
                        f.engine.retrain_trainer_source(f.teacher, feature, **decision)
                    self.assertEqual(self.snapshot(f.engine), before)

    def test_native_and_explicit_skill_provider_dependencies_cannot_be_omitted_or_withdrawn(self):
        f = MOVE_FIXTURE.MentorMoveStateTests(); f.setUp(); f.a.spec['exp_bank'] = 10
        decision = self.decisions(f.e, f.a, TEACHING.MOVE_TUTOR)
        source = self.sources(f.e, f.a)[TEACHING.EGG_TUTOR]
        omitted = deepcopy(decision); omitted['retained_dependencies'][source] = []
        before = self.snapshot(f.e)
        with self.assertRaisesRegex(ValueError, 'cannot be omitted'):
            f.e.retrain_trainer_source(f.a, TEACHING.MOVE_TUTOR, **omitted)
        with self.assertRaisesRegex(ValueError, 'retained grant depends'):
            f.e.retrain_trainer_source(f.a, TEACHING.MOVE_TUTOR, **decision)
        self.assertEqual(self.snapshot(f.e), before)
        e, a = self.simple([FEATURES.PERSONAL_TUTOR], ['edge/기본-스킬'], skills={'일반 지식': 3})
        sources = self.sources(e, a)
        e.bind_grant_dependencies(a, sources[FEATURES.PERSONAL_TUTOR], [sources['edge/기본-스킬']])
        decision = self.decisions(e, a, 'edge/기본-스킬'); before = self.snapshot(e)
        with self.assertRaisesRegex(ValueError, 'retained grant depends'):
            e.retrain_trainer_source(a, 'edge/기본-스킬', **decision)
        self.assertEqual(self.snapshot(e), before)
        e, a = self.simple(edges=[FEATURES.MARTIAL_PREREQUISITE], skills={'전투': 3})
        FEATURES.acquire_martial_artist(e, a, acquisition_request_id='actual/martial', selected_ability='ability/근성',
            lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_WHILE_OWNED))
        e.register_abilities(a)
        decision = self.decisions(e, a, FEATURES.MARTIAL_PREREQUISITE)
        omitted = deepcopy(decision)
        omitted['retained_dependencies'][self.sources(e, a)[FEATURES.MARTIAL_ARTIST]] = []
        before = self.snapshot(e)
        with self.assertRaisesRegex(ValueError, 'cannot be omitted'):
            e.retrain_trainer_source(a, FEATURES.MARTIAL_PREREQUISITE, **omitted)
        with self.assertRaisesRegex(ValueError, 'retained grant depends'):
            e.retrain_trainer_source(a, FEATURES.MARTIAL_PREREQUISITE, **decision)
        self.assertEqual(self.snapshot(e), before)

    def test_real_selection_receipt_is_preserved_as_withdrawn_and_not_current_choices(self):
        moves = list(self.rules.moves)[:3]
        e, a = self.simple(edges=[FEATURES.MARTIAL_PREREQUISITE],
            skills={'일반 지식': 3, '전투': 3}, moves=moves)
        receipt = FEATURES.acquire_personal_tutor(e, a, acquisition_request_id='actual/personal',
            selected_values=moves, source_clause_id='C03-127',
            lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_UNRESOLVED))
        decision = self.decisions(e, a, FEATURES.PERSONAL_TUTOR)
        e.retrain_trainer_source(a, FEATURES.PERSONAL_TUTOR, **decision)
        self.assertEqual(a.spec[FEATURES.LEDGER_KEY]['actual/personal'], receipt)
        self.assertEqual(FEATURES.projection(a, FEATURES.PERSONAL_TUTOR), {})
        e = self.restored(e); a = e.everyone[0]
        self.assertIn(dict(receipt, state='withdrawn'), e.acquisition_receipts(a))
        with self.assertRaisesRegex(ValueError, 'committed selection'):
            FEATURES.selected_values(a, FEATURES.PERSONAL_TUTOR, 'feat/개인-지도:1')
        FEATURES.acquire_martial_artist(e, a, acquisition_request_id='later/martial', selected_ability='ability/근성',
            lifecycle_policy=deepcopy(FEATURES.LIFECYCLE_WHILE_OWNED))
        self.assertTrue(FEATURES.projection(a, FEATURES.MARTIAL_ARTIST))
        self.assertEqual(FEATURES.projection(a, FEATURES.PERSONAL_TUTOR), {})
        self.assertEqual(a.spec[FEATURES.LEDGER_KEY]['actual/personal'], receipt)
        f = CSV_FIXTURE.MentorCSVTests(); f.setUp(); f.acquire(); f.a.spec['exp_bank'] = 10
        decision = self.decisions(f.e, f.a, TEACHING.MENTOR)
        f.e.retrain_trainer_source(f.a, TEACHING.MENTOR, **decision)
        self.assertFalse(CSV_FIXTURE.CSV.has_receipt(f.a))
        self.assertEqual(FEATURES.projection(f.a, TEACHING.MENTOR), {})
        with self.assertRaisesRegex(ValueError, 'actual committed'):
            CSV_FIXTURE.CSV.receipt(f.a)
        f = SIGNATURE_FIXTURE.SignatureMoveTests(); f.setUp(); receipt = f.acquire()
        f.actor.spec['exp_bank'] = 10
        native = SIGNATURE_FIXTURE.SIGNATURE
        base = tuple(receipt['selection']['acquisition_snapshot']['base_frequency'])
        mid = receipt['selection']['values'][0]
        self.assertNotEqual(native.frequency(f.actor, mid, base), base)
        decision = self.decisions(f.engine, f.actor, native.FEATURE)
        f.engine.retrain_trainer_source(f.actor, native.FEATURE, **decision)
        self.assertEqual(native.frequency(f.actor, mid, base), base)
        self.assertEqual(f.actor.stats['atk'], 10)

    def test_gm_consultation_complete_dependencies_and_late_failure_are_atomic(self):
        e, a = self.simple([FEATURES.PERSONAL_TUTOR])
        decision = self.decisions(e, a, FEATURES.PERSONAL_TUTOR); before = self.snapshot(e)
        for gm in ({'allowed': False, 'reason': 'too prominent'},
                   {'allowed': None, 'reason': 'not yet consulted'}, {'allowed': True, 'reason': ''}):
            with self.subTest(gm=gm), self.assertRaises(ValueError):
                e.retrain_trainer_source(a, FEATURES.PERSONAL_TUTOR, **dict(decision, gm_decision=gm))
            self.assertEqual(self.snapshot(e), before)
        with patch.object(RETRAINING, 'sha256') as digest:
            digest.return_value.hexdigest.return_value = 'changed-original'
            with self.assertRaisesRegex(ValueError, 'source changed'):
                e.retrain_trainer_source(a, FEATURES.PERSONAL_TUTOR, **decision)
        self.assertEqual(self.snapshot(e), before)
        other, owner = self.simple([FEATURES.PERSONAL_TUTOR], ['edge/기본-스킬'])
        incomplete = self.decisions(other, owner, FEATURES.PERSONAL_TUTOR)
        incomplete['retained_dependencies'] = {}
        other_before = self.snapshot(other)
        with self.assertRaisesRegex(ValueError, 'cover every'):
            other.retrain_trainer_source(owner, FEATURES.PERSONAL_TUTOR, **incomplete)
        self.assertEqual(self.snapshot(other), other_before)
        import trainer_xp_payments as XP
        before = self.snapshot(e)
        with patch.object(XP, 'mark_used', side_effect=ValueError('late retraining failure')):
            with self.assertRaisesRegex(ValueError, 'late retraining'):
                e.retrain_trainer_source(a, FEATURES.PERSONAL_TUTOR, **decision)
        self.assertEqual(self.snapshot(e), before)
        e.retrain_trainer_source(a, FEATURES.PERSONAL_TUTOR, **decision)

    def test_same_named_independent_source_is_not_the_actual_feature_use(self):
        e, a = self.simple([FEATURES.PERSONAL_TUTOR])
        sources = self.sources(e, a)
        GRANTS.grant(a, 'capabilities', 'independent/witness', 'custom/permanent', 'custom',
                     rule_id=FEATURES.PERSONAL_TUTOR, owner_id=a.entity_id, lifetime='while_owned')
        e.record_irreversible_grant_use(a, 'custom/permanent', event_id='custom/effect/1', reason='actual custom permanent effect')
        decision = self.decisions(e, a, FEATURES.PERSONAL_TUTOR)
        e.retrain_trainer_source(a, FEATURES.PERSONAL_TUTOR, **decision)
        self.assertIn('independent/witness', GRANTS.effective(a, 'capabilities'))
        self.assertNotIn(sources[FEATURES.PERSONAL_TUTOR], a.spec['state_grants']['sources'])
        with self.assertRaisesRegex(ValueError, 'irreversible'):
            GRANTS.revoke(a, 'custom/permanent', engine=e)

    def test_gm_type_sync_observation_does_not_invent_a_feature_teacher(self):
        f = TYPE_FIXTURE.TypeSyncTests(); f.setUp()
        before = deepcopy(f.a.spec)
        f.sync()
        self.assertNotEqual(f.p.spec['types'], ['풀', '독'])
        self.assertEqual(f.a.spec, before)


if __name__ == '__main__':
    unittest.main()
