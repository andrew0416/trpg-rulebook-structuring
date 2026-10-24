"""Complete Elemental source interpretations through actual native consumers."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
from native_scenario_fixture import assert_rejected_unchanged
import test_category3_elemental_connection as FIXTURE
import elemental_connection as ELEM
import world_entities as WORLD


class ElementalConnectionSourceChoiceRevisionTests(unittest.TestCase):
    setUpClass = classmethod(FIXTURE.ElementalTests.setUpClass.__func__)
    setUp = FIXTURE.ElementalTests.setUp
    actor = FIXTURE.ElementalTests.actor

    def acquire(self, *types):
        self.a.spec['edges'] = [ELEM.SOURCE] * len(types)
        self.a.spec['edge_choices'] = {ELEM.SOURCE: list(types)}

    def choice(self, interpretation):
        before = self.e.export_state()
        pending = ELEM.source_choices(self.e, self.a)
        self.assertEqual(pending['status'], 'PolicyInputsRequired')
        self.assertEqual(self.e.export_state(), before)
        return {'value': interpretation,
                'reason': 'GM explicitly selects current native Elemental source and overlap interpretation',
                'scope': pending['decision_scope']}

    def select(self, interpretation):
        return self.e.gm.observe_elemental_connection_source(self.a, self.choice(interpretation))

    def test_all_three_complete_interpretations_reach_five_skills_opposed_and_paid_maneuver(self):
        for interpretation in ELEM.INTERPRETATIONS:
            with self.subTest(interpretation=interpretation):
                self.setUp()
                self.acquire(*(('불꽃',) if interpretation == 'en_single_acquisition' else ('불꽃', '비행')))
                receipt_start=len(self.e.rulings.log)
                selected = self.select(interpretation)
                bonus = 4 if interpretation == ELEM.DEFAULT_INTERPRETATION else 2
                self.assertEqual(selected['policy']['values']['interpretation'], interpretation)
                receipts=[row for row in self.e.rulings.log[receipt_start:]
                          if row['kind']=='state' and row['what']==self.a.name+' 원소 교감 출처 해석']
                self.assertEqual(len(receipts),1);receipt=receipts[0]
                self.assertIsNone(receipt['before'])
                self.assertEqual(receipt['after'], self.a.spec[ELEM.SOURCE_OBSERVATION])
                for skill in ELEM.SKILLS:
                    result = self.e.skill_roll(self.a, skill, skill_target=self.p, fixed=[3] * 4)
                    self.assertEqual(result.total, 12 + bonus)
                self.assertTrue(self.e.opposed_check(
                    self.a, '교활', self.p, '직감',
                    challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [3] * 4}))
                self.e.start_round(self.e.everyone)
                self.e.start_of_turn(self.a, initiative_count=20)
                before_rng = self.e.rng.getstate()
                self.assertTrue(self.e.manipulate(
                    self.a, self.p, 'flirt', defender_skill='집중', fixed_accuracy=15,
                    challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [3] * 4}))
                self.assertEqual(self.a.budget['standard'], 0)
                self.assertEqual(self.e.rng.getstate(), before_rng)
                self.assertIn('헤롱헤롱', self.p.conditions)
                retained = deepcopy(self.a.spec[ELEM.SOURCE_OBSERVATION])
                self.p.types = ['물']
                self.assertEqual(self.e.skill_roll(self.a, '매력', skill_target=self.p, fixed=[3] * 4).total, 12)
                self.p.types = ['불꽃', '비행']
                self.assertEqual(self.e.skill_roll(self.a, '매력', skill_target=self.p, fixed=[3] * 4).total, 12 + bonus)
                self.assertEqual(self.a.spec[ELEM.SOURCE_OBSERVATION], retained)

    def test_unselected_authored_additive_default_keeps_ordinary_callers_and_creates_no_past_choice(self):
        self.assertEqual(self.e.skill_roll(self.a, '매력', skill_target=self.p, fixed=[3] * 4).total, 14)
        self.acquire('불꽃', '비행')
        before_rng = self.e.rng.getstate()
        self.assertEqual(self.e.skill_roll(self.a, '매력', skill_target=self.p, fixed=[3] * 4).total, 16)
        self.assertEqual(self.e.rng.getstate(), before_rng)
        self.assertNotIn(ELEM.SOURCE_OBSERVATION, self.a.spec)
        self.assertEqual(self.e.skill_roll(self.a, '매력', fixed=[3] * 4).total, 12)
        self.assertEqual(self.e.skill_roll(self.a, '집중', skill_target=self.p, fixed=[3] * 4).total, 12)
        self.p.types = ['불꽃']
        self.assertEqual(self.e.skill_roll(self.a, '매력', skill_target=self.p, fixed=[3] * 4).total, 14)
        self.e.gm.snapshot('unselected-native-default')
        self.e.gm.restore('unselected-native-default')
        self.assertNotIn(ELEM.SOURCE_OBSERVATION, self.a.spec)

    def test_english_repeat_rejection_and_foreign_stale_acquisition_choices_precede_payment_and_rng(self):
        self.acquire('불꽃', '비행')
        english = self.choice('en_single_acquisition')
        assert_rejected_unchanged(
            self.e, lambda: self.e.gm.observe_elemental_connection_source(self.a, english),
            reason_pattern='English Elemental Connection permits one acquired type choice')
        self.assertNotIn(ELEM.SOURCE_OBSERVATION, self.a.spec)
        own_choice = self.choice('kr_branch_once_per_check')
        other = self.actor('foreign elemental trainer')
        other.spec.update(edges=[ELEM.SOURCE, ELEM.SOURCE],
                          edge_choices={ELEM.SOURCE: ['불꽃', '비행']})
        other.pos = (7, 4)
        self.e.everyone.append(other)
        assert_rejected_unchanged(
            self.e, lambda: self.e.gm.observe_elemental_connection_source(other, own_choice),
            reason_pattern='GM decision scope changed')
        self.e.gm.observe_elemental_connection_source(self.a, own_choice)
        previous = deepcopy(self.a.spec[ELEM.SOURCE_OBSERVATION])
        self.acquire('불꽃', '물')  # An actual current acquisition observation differs.
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)
        assert_rejected_unchanged(
            self.e, lambda: self.e.skill_roll(self.a, '매력', skill_target=self.p),
            reason_pattern='GM decision scope changed')
        assert_rejected_unchanged(
            self.e, lambda: self.e.manipulate(
                self.a, self.p, 'flirt', defender_skill='집중', fixed_accuracy=15,
                challenger_options={'fixed': [3] * 4}, defender_options={'fixed': [3] * 4}),
            reason_pattern='GM decision scope changed')
        self.assertEqual(self.a.budget['standard'], 1)
        self.assertEqual(self.a.spec[ELEM.SOURCE_OBSERVATION], previous)
        receipt_start=len(self.e.rulings.log)
        self.select('kr_branch_each_matching_type')
        receipts=[row for row in self.e.rulings.log[receipt_start:]
                  if row['kind']=='state' and row['what']==self.a.name+' 원소 교감 출처 해석']
        self.assertEqual(len(receipts),1)
        self.assertEqual(receipts[0]['before'], previous)
        self.assertEqual(receipts[0]['after'],self.a.spec[ELEM.SOURCE_OBSERVATION])
        self.assertEqual(self.e.skill_roll(self.a, '매력', skill_target=self.p, fixed=[3] * 4).total, 14)

    def test_actual_gm_and_fresh_rules_json_retain_complete_choices_and_inactive_history_without_grants(self):
        for interpretation in ELEM.INTERPRETATIONS:
            with self.subTest(interpretation=interpretation):
                self.setUp()
                self.acquire(*(('불꽃',) if interpretation == 'en_single_acquisition' else ('불꽃', '비행')))
                retained = self.select(interpretation)
                self.e.gm.snapshot('elemental-source')
                alternative = ('kr_branch_once_per_check' if interpretation != 'kr_branch_once_per_check'
                               else ELEM.DEFAULT_INTERPRETATION)
                self.select(alternative)
                self.e.gm.restore('elemental-source')
                fresh = Rules(ROOT)
                loaded = Engine.import_state(fresh, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
                for world in (self.e, loaded):
                    actor = WORLD.actor_index(world)[self.a.entity_id]
                    target = WORLD.actor_index(world)[self.p.entity_id]
                    self.assertEqual(actor.spec[ELEM.SOURCE_OBSERVATION], retained)
                    self.assertEqual(world.skill_roll(actor, '매력', skill_target=target, fixed=[3] * 4).total,
                                     16 if interpretation == ELEM.DEFAULT_INTERPRETATION else 14)
                    actor.spec.update(edges=[], edge_choices={})
                    self.assertEqual(world.skill_roll(actor, '매력', skill_target=target, fixed=[3] * 4).total, 12)
                    self.assertEqual(actor.spec[ELEM.SOURCE_OBSERVATION], retained)
                    restored = Engine.import_state(Rules(ROOT), json.loads(json.dumps(world.export_state(), ensure_ascii=False)))
                    inactive = WORLD.actor_index(restored)[actor.entity_id]
                    self.assertEqual(inactive.spec['edges'], [])
                    self.assertEqual(inactive.spec[ELEM.SOURCE_OBSERVATION], retained)
                    self.assertEqual(ELEM.choices(restored, inactive), ())


if __name__ == '__main__':
    unittest.main()
