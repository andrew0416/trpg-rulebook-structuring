"""Q43: actual source choices, physical fishing results and fossil birth basis."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_category3_pokemon_activities as activities_fixture
import test_book_researcher_fields_pokemon as fossil_fixture
from engine import Rules, Engine
import pokemon_activities as ACTIVITIES
import creation_fossil as FOSSIL
import researcher_fields as RESEARCH
import pokemon_progression as PROGRESSION
import downtime as DOWNTIME
import world_entities as WORLD

ROOT = activities_fixture.ROOT
CLAUSES = ['C05-168', 'C05-172', 'C05-179', 'C04-088']


class RelationshipsFishingSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    setUp = activities_fixture.PokemonActivityTests.setUp
    actor = activities_fixture.PokemonActivityTests.actor
    act = activities_fixture.PokemonActivityTests.act

    def source_choice(self, value, **options):
        before = self.e.export_state()
        pending = self.act('befriend', target=self.p, source_query=True, **options)
        self.assertEqual(pending['status'], 'PolicyInputsRequired')
        self.assertEqual(self.e.export_state(), before)
        return {'value': value, 'reason': 'GM selects the actual current disposition source',
                'scope': pending['decision_scope']}

    def hook(self):
        self.a.spec['items'].update({'대단한낚싯대': 1, '루어': 2})
        self.act('fishing', phase='start', rod='대단한낚싯대', attachment='루어')
        self.act('fishing', phase='wait', roll_d20=15)

    def test_complete_kr_and_en_choices_use_actual_standard_and_shared_dc_relationships(self):
        for interpretation, result in [('kr_one_step', '두려움'), ('en_hostile_to_neutral', '중립')]:
            with self.subTest(interpretation=interpretation):
                self.setUp()
                self.act('disposition_ruling', target=self.p, disposition='적대적', reason='GM observed hostility')
                self.e.start_round([self.a, self.p])
                self.e.start_of_turn(self.a, initiative_count=20)
                choice = self.source_choice(interpretation)
                out = self.act('befriend', target=self.p, source_choice=choice, fixed=[3] * 4, mods=3)
                self.assertEqual((out['check'].dc, out['check'].total, out['disposition']), (15, 15, result))
                self.assertEqual(self.a.budget['standard'], 0)
                self.assertFalse(self.p.captured)
                history = self.p.spec['disposition_history'][-1]
                self.assertEqual((history['before'], history['after'], history['audience']),
                                 ('적대적', result, 'trainer:' + self.a.entity_id))
                self.assertEqual(history['source_decision']['values']['interpretation'], interpretation)
        self.setUp()
        self.p.spec['disposition'] = '적대적'
        out = self.act('befriend', target=self.p, fixed=[3] * 4, mods=3)
        self.assertEqual((out['disposition'], out['source_decision']['authority']), ('두려움', 'authored_default'))
        self.setUp()
        self.p.spec['disposition'] = '두려움'
        out = self.act('befriend', target=self.p, source_choice=self.source_choice('en_hostile_to_neutral'), fixed=[2] * 4)
        self.assertEqual((out['check'].dc, out['disposition']), (8, '중립'))

    def test_source_scope_failure_lock_and_actual_history_survive_gm_and_fresh_rules_json(self):
        self.p.spec['disposition'] = '적대적'
        choice = self.source_choice('en_hostile_to_neutral')
        wrong = deepcopy(choice)
        wrong['scope']['definition_hash'] = 'foreign'
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.act('befriend', target=self.p, source_choice=wrong, fixed=[6] * 4)
        self.assertEqual(self.e.export_state(), before)
        failed = self.act('befriend', target=self.p, source_choice=choice, fixed=[1] * 4)
        self.assertFalse(failed['check'].passed)
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.act('befriend', target=self.p, source_choice=choice, fixed=[6] * 4)
        self.assertEqual(self.e.export_state(), before)
        self.act('disposition_ruling', target=self.p, disposition='두려움', allow_retry=True,
                 reason='GM changed circumstances allow this actual trainer another attempt')
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.act('befriend', target=self.p, source_choice=choice, fixed=[2] * 4)
        self.assertEqual(self.e.export_state(), before)
        self.act('befriend', target=self.p, source_choice=self.source_choice('en_hostile_to_neutral'), fixed=[2] * 4)
        history = deepcopy(self.p.spec['disposition_history'])
        snapshot = self.e.gm.snapshot()
        self.act('disposition_ruling', target=self.p, disposition='적대적', reason='GM observed a later unrelated event')
        self.e.gm.restore(snapshot)
        self.assertEqual(self.p.spec['disposition_history'], history)
        loaded = Engine.import_state(Rules(str(ROOT), ruleset='core'), json.loads(json.dumps(self.e.export_state())))
        target = WORLD.actor_index(loaded)[self.p.entity_id]
        self.assertEqual(target.spec['disposition_history'], history)
        self.assertEqual(target.spec['dispositions']['trainer:' + self.a.entity_id], '중립')
        self.assertTrue(loaded.validate_state()['valid'])

    def test_actual_failed_reel_ten_loses_one_lure_and_eleven_retains_same_hooked_target(self):
        self.hook()
        out = self.act('fishing', phase='reel', target=self.p, fixed=[1] * 4, escape_d20=11)
        self.assertEqual((out['status'], out['escaped'], self.a.spec['items']['루어']), ('hooked', False, 2))
        self.q.spec['wild'] = True
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.act('fishing', phase='reel', target=self.q, fixed=[2] * 4)
        self.assertEqual(self.e.export_state(), before)
        out = self.act('fishing', phase='reel', target=self.p, fixed=[1] * 4, escape_d20=10)
        self.assertEqual((out['status'], out['escaped'], self.a.spec['items']['루어']), ('escaped', True, 1))
        receipt = out['lure_loss']
        self.assertEqual((receipt['escape_d20'], receipt['target_id'], receipt['stock_before'], receipt['stock_after']),
                         (10, self.p.entity_id, 2, 1))
        self.assertTrue(receipt['lost'])
        snapshot = self.e.gm.snapshot()
        self.act('fishing', phase='start', rod='대단한낚싯대', attachment='루어')
        self.e.gm.restore(snapshot)
        self.assertEqual(self.a.spec['fishing_session']['lure_loss'], receipt)
        loaded = Engine.import_state(Rules(str(ROOT), ruleset='core'), json.loads(json.dumps(self.e.export_state())))
        owner, target = (WORLD.actor_index(loaded)[x.entity_id] for x in (self.a, self.p))
        self.assertEqual((owner.spec['items']['루어'], owner.spec['fishing_session']['lure_loss']), (1, receipt))
        before = loaded.export_state()
        with self.assertRaises(ValueError):
            loaded.pokemon_activity(owner, 'fishing', phase='lure_loss', target=target, cause='escaped',
                                    lost=True, reason='the same fish cannot take a second lure')
        self.assertEqual(loaded.export_state(), before)
        self.assertFalse(target.captured)

    def test_late_loss_failure_rolls_back_and_legacy_escape_waits_for_actual_physical_observation(self):
        self.hook()
        before = self.e.export_state()
        # The actual loss has already been produced when the transaction tries
        # to return its copied result; this is a meaningful post-debit failure.
        original = ACTIVITIES.deepcopy
        def fail_after_loss(value):
            if isinstance(value, dict) and 'lure_loss' in value:
                raise RuntimeError('late physical result failure')
            return original(value)
        with patch.object(ACTIVITIES, 'deepcopy', fail_after_loss):
            with self.assertRaises(RuntimeError):
                self.act('fishing', phase='reel', target=self.p, fixed=[1] * 4, escape_d20=10)
        self.assertEqual(self.e.export_state(), before)
        self.act('fishing', phase='reel', target=self.p, fixed=[1] * 4, escape_d20=10)
        # Project the real failed check to the exact pre-Q43 producer fields:
        # escaped/actual target, no die/loss receipt, unchanged observed stock.
        # The current consumer must not infer either a past debit or retrieval.
        state = self.a.spec['fishing_session']
        state.pop('reel_failure')
        state.pop('lure_loss')
        self.a.spec['items']['루어'] = 2
        history = deepcopy(state)
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, 'historical escape'):
            self.act('fishing', phase='start', rod='대단한낚싯대', attachment='루어')
        self.assertEqual(self.e.export_state(), before)
        self.assertEqual(self.a.spec['items']['루어'], 2)
        self.assertEqual(state, history)
        self.act('fishing', phase='lure_loss', target=self.p, cause='escaped', lost=False,
                 reason='GM currently observes the actual old lure retrieved intact')
        self.assertEqual(self.a.spec['items']['루어'], 2)
        self.act('fishing', phase='start', rod='대단한낚싯대', attachment='루어')


class FossilBirthInterpretationRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    setUp = fossil_fixture.ResearcherFieldsPokemonTests.setUp
    setup = fossil_fixture.ResearcherFieldsPokemonTests.setup
    trainer = fossil_fixture.ResearcherFieldsPokemonTests.trainer
    pokemon = fossil_fixture.ResearcherFieldsPokemonTests.pokemon
    rejected = fossil_fixture.ResearcherFieldsPokemonTests.rejected
    valid = fossil_fixture.ResearcherFieldsPokemonTests.valid
    restore = fossil_fixture.ResearcherFieldsPokemonTests.restore
    fossil = fossil_fixture.ResearcherFieldsPokemonTests.fossil
    hatch = fossil_fixture.ResearcherFieldsPokemonTests.hatch

    def test_new_plain_three_and_earned_feature_one_keep_birth_basis_and_only_future_real_awards(self):
        for feature, initial in [(False, 3), (True, 1)]:
            with self.subTest(feature=feature):
                self.setUp()
                egg = self.fossil('프테라', 'actual', feature=feature)
                self.assertEqual(egg[FOSSIL.BIRTH_BASIS], FOSSIL.INITIAL_LEVEL_BASIS)
                fossil = self.t.spec['fossils']['actual']
                self.assertEqual(fossil[FOSSIL.CONTRACT]['request'][FOSSIL.BIRTH_BASIS], egg[FOSSIL.BIRTH_BASIS])
                if feature:
                    self.assertEqual(egg[RESEARCH.FOSSIL_MARK]['tutor_points'],
                                     {'native': 3, 'printed_delta': -2, 'birth': 1, 'deficit': 0})
                child = self.hatch(egg, 'actual native child')
                self.assertEqual((child.level, child.spec['tutor_points']), (10, initial))
                self.assertEqual(len(child.abilities), 2 if feature else 1)
                self.assertEqual(child.spec[FOSSIL.BIRTH_BASIS], egg[FOSSIL.BIRTH_BASIS])
                self.assertEqual(child.spec[PROGRESSION.LEVEL_STATE]['awards'], [])
                DOWNTIME.gain_exp_combatant(self.e, child, DOWNTIME.exp_for_level(self.rules, 15) - child.spec['exp'])
                self.assertEqual((child.level, child.spec['tutor_points']), (15, initial + 1))
                self.assertEqual([row['level'] for row in child.spec[PROGRESSION.LEVEL_STATE]['awards']], [15])
                self.restore('t')
                self.e = Engine.import_state(Rules(str(ROOT), ruleset='core'), json.loads(json.dumps(self.e.export_state())))
                self.t = WORLD.actor_index(self.e)[self.t.entity_id]
                restored = WORLD.actor_index(self.e)[child.entity_id]
                self.assertEqual((restored.spec['tutor_points'], restored.spec[FOSSIL.BIRTH_BASIS]), (initial + 1, FOSSIL.INITIAL_LEVEL_BASIS))
                self.valid()

    def test_real_legacy_plain_one_feature_zero_and_spent_child_balance_survive_current_rules(self):
        native = FOSSIL.native
        for feature, initial in [(False, 1), (True, 0)]:
            with self.subTest(feature=feature):
                self.setUp()
                # This executes the actual owned restoration producer with the
                # exact pre-Q43 native1 policy and absent interpretation field.
                with patch.object(FOSSIL, 'native', lambda **options: native(legacy=True)), patch.object(FOSSIL, 'INITIAL_LEVEL_BASIS', None):
                    egg = self.fossil('프테라', 'historical', feature=feature)
                self.assertNotIn(FOSSIL.BIRTH_BASIS, egg)
                self.assertEqual(egg[FOSSIL.BIRTH]['tutor_points'], initial)
                if feature:
                    self.assertEqual(egg[RESEARCH.FOSSIL_MARK]['tutor_points'],
                                     {'native': 1, 'printed_delta': -2, 'birth': 0, 'deficit': 1})
                self.restore('t')
                egg = self.t.spec['eggs'][0]
                child = self.hatch(egg, 'historical child')
                self.assertEqual(child.spec['tutor_points'], initial)
                self.assertNotIn(FOSSIL.BIRTH_BASIS, child.spec)
                if initial:
                    self.e.pokemon_activity(self.t, 'observe_tutor_points', target=child, balance=0,
                                            reason='GM verifies the actual current spent historical balance')
                before = deepcopy(child.spec[PROGRESSION.LEVEL_STATE])
                self.restore('t')
                self.e = Engine.import_state(Rules(str(ROOT), ruleset='core'), json.loads(json.dumps(self.e.export_state())))
                self.t = WORLD.actor_index(self.e)[self.t.entity_id]
                child = WORLD.actor_index(self.e)[child.entity_id]
                self.assertEqual(child.spec['tutor_points'], 0)
                self.assertEqual(child.spec[PROGRESSION.LEVEL_STATE], before)
                DOWNTIME.gain_exp_combatant(self.e, child, DOWNTIME.exp_for_level(self.rules, 15) - child.spec['exp'])
                self.assertEqual(child.spec['tutor_points'], 1)
                self.assertEqual([row['level'] for row in child.spec[PROGRESSION.LEVEL_STATE]['awards']], [15])
                self.valid()
