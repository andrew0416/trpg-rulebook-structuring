"""Q22: real Designer producers, complete choices and retained historical facts."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools'), str(ROOT / 'examples')]

import ability_native_actions as NATIVE
import ability_state_projection as PROJECTION
import state_grants as GRANTS
import test_category2_ability_native_actions as FIXTURE
from engine import Engine, Rules

LEAFY = 'ability/잎사귀망토'
DESIGNER = 'ability/디자이너'
CHLOROPHYLL = 'ability/엽록소-playtest'
LEAF_GUARD = 'ability/리프가드-playtest'
OVERCOAT = 'ability/방진'
SOUNDPROOF = 'ability/방음'
HYBRID = 'korean_candidates_english_timing_clarification'


class LeafyCloakDesignerSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='all')

    def setUp(self):
        self.fixture = FIXTURE.AbilityNativeActionTests()
        self.fixture.r = self.r

    def user(self, name, abilities=(DESIGNER, LEAFY), pos=(2, 2), moves=()):
        return self.fixture.pokemon(name, None, pos=pos, moves=moves, extra={
            'abilities': list(abilities), 'types': ['노말']})

    def choose(self, e, user, pair, source_choice=None):
        observation = None if source_choice is None else {'source_choice': source_choice}
        return e.choose_ability_state(user, LEAFY, '+'.join(pair),
            observation=observation, reason='actual next Designer pair choice')

    def source_choice(self, user, variant):
        return {'value': variant, 'reason': 'table chooses the explicitly labelled candidate/timing interpretation',
                'scope': PROJECTION.leafy_source_choices(user)['decision_scope']}

    def design(self, e, user, types=('불꽃', '물')):
        return e.activate_ability(user, DESIGNER, (user, {'types': list(types)}))

    def unchanged_refusal(self, e, call):
        before = deepcopy(e.export_state())
        with self.assertRaises(ValueError):
            call()
        self.assertEqual(e.export_state(), before)

    def test_english_default_real_designer_grants_overcoat_and_playtest_chlorophyll_to_native_consumers(self):
        user = self.user('leafy-english')
        attacker = self.user('leafy-attacker', abilities=(), pos=(3, 2), moves=('독가루', '하이퍼보이스'))
        control = self.user('weather-control', abilities=(), pos=(4, 2))
        e = self.fixture.engine(user, attacker, control)
        self.choose(e, user, (CHLOROPHYLL, OVERCOAT))
        self.assertNotIn(OVERCOAT, user.abilities)
        receipt = self.design(e, user)
        projection = user.spec[PROJECTION.KEY][LEAFY]
        self.assertEqual(projection['leafy_producer']['receipt_id'], receipt['id'])
        self.assertEqual(projection['leafy_producer']['selection']['variant'], 'english_complete')
        self.assertEqual(set(receipt['details']['types']), {'불꽃', '물'})
        self.assertEqual(set(projection['payload']['abilities']), {CHLOROPHYLL, OVERCOAT})
        self.assertNotIn('ability/엽록소', user.abilities)
        self.assertFalse(e.accuracy_check(attacker, user, self.r.move('move/독가루'), waive=True, fixed_roll=20)[0])
        self.assertTrue(e.accuracy_check(attacker, user, self.r.move('move/하이퍼보이스'), waive=True, fixed_roll=20)[0])
        base = e.initiative_value(user).value
        e.gm.set_weather('sunny', reason='actual sunny interval')
        self.assertEqual(e.initiative_value(user).value, base * 2)
        e.gm.set_weather('hail', reason='actual damaging hail')
        before = user.hp, control.hp
        e.start_round([user, attacker, control])
        e.start_of_turn(user, initiative_count=30)
        self.assertEqual(user.hp, before[0])
        e.end_of_turn(user)
        e.start_of_turn(control, initiative_count=20)
        self.assertLess(control.hp, before[1])
        e.end_of_turn(control)
        user.abilities_suppressed = True
        suppressed_hp = user.hp
        self.fixture.turn(e, user, [user, attacker, control])
        self.assertLess(user.hp, suppressed_hp)
        user.abilities_suppressed = False
        self.fixture.valid(e)

    def test_scoped_soundproof_choice_waits_for_next_designer_and_retains_both_producing_histories(self):
        unrelated = 'ability/정신력-playtest'
        user = self.user('leafy-source-change', abilities=(DESIGNER, LEAFY, unrelated))
        attacker = self.user('leafy-source-attacker', abilities=(), pos=(3, 2), moves=('독가루', '하이퍼보이스'))
        e = self.fixture.engine(user, attacker)
        self.choose(e, user, (CHLOROPHYLL, OVERCOAT))
        first = self.design(e, user)
        original = deepcopy(user.spec[PROJECTION.KEY][LEAFY])
        choices = PROJECTION.leafy_source_choices(user)
        self.assertIn('not an intact Korean edition', choices['definitions'][HYBRID]['label'])
        selected = self.source_choice(user, HYBRID)
        self.choose(e, user, (LEAF_GUARD, SOUNDPROOF), selected)
        self.assertEqual(user.spec[PROJECTION.KEY][LEAFY], original)
        self.assertIn(OVERCOAT, user.abilities)
        second = self.design(e, user, ('풀', '전기'))
        current = user.spec[PROJECTION.KEY][LEAFY]
        self.assertEqual(current['leafy_producer']['selection']['choice'], selected)
        self.assertIn(unrelated, user.abilities)
        self.assertIn(LEAF_GUARD, user.abilities)
        self.assertNotIn(OVERCOAT, user.abilities)
        self.assertNotIn(CHLOROPHYLL, user.abilities)
        self.assertEqual(user.spec[PROJECTION.LEAFY_HISTORY][0]['projection'], original)
        self.assertEqual(user.spec[PROJECTION.LEAFY_HISTORY][0]['replaced_by'], second['id'])
        self.assertEqual(user.spec[NATIVE.HISTORY][0], first)
        self.assertEqual(user.spec[NATIVE.KEY][DESIGNER]['destroyed_garments'][0]['grant_source'], first['details']['grant_source'])
        self.assertTrue(e.accuracy_check(attacker, user, self.r.move('move/독가루'), waive=True, fixed_roll=20)[0])
        self.assertFalse(e.accuracy_check(attacker, user, self.r.move('move/하이퍼보이스'), waive=True, fixed_roll=20)[0])
        e.gm.snapshot('actual-soundproof-garment')
        self.choose(e, user, (CHLOROPHYLL, OVERCOAT))
        self.design(e, user)
        e.gm.restore('actual-soundproof-garment', reason='restore actual Designer and Leafy choices together')
        n = Engine.import_state(Rules(ROOT, ruleset='all'), json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        restored = next(c for c in n.everyone if c.entity_id == user.entity_id)
        self.assertEqual(restored.spec[PROJECTION.KEY][LEAFY], current)
        self.assertEqual(restored.spec[NATIVE.HISTORY], [first, second])
        self.fixture.valid(n)

    def test_missing_wrong_or_stale_pair_and_independent_activation_refuse_before_work_and_failed_creation_rolls_back(self):
        user = self.user('leafy-preflight')
        only_leafy = self.user('leafy-without-designer', abilities=(LEAFY,), pos=(4, 2))
        plain = self.user('designer-without-leafy', abilities=(DESIGNER,), pos=(6, 2))
        e = self.fixture.engine(user, only_leafy, plain)
        self.unchanged_refusal(e, lambda: self.design(e, user))
        self.unchanged_refusal(e, lambda: self.choose(e, only_leafy, (CHLOROPHYLL, OVERCOAT)))
        self.unchanged_refusal(e, lambda: self.choose(e, user, (CHLOROPHYLL, SOUNDPROOF)))
        stale = self.source_choice(user, HYBRID)
        stale['scope'] = dict(stale['scope'], profile_hash='not-the-actual-scope')
        self.unchanged_refusal(e, lambda: self.choose(e, user, (LEAF_GUARD, SOUNDPROOF), stale))
        self.unchanged_refusal(e, lambda: e.activate_ability_state(user, LEAFY,
            choice=CHLOROPHYLL + '+' + OVERCOAT, reason='no independent manual action permission'))
        self.design(e, plain)
        self.assertNotIn(PROJECTION.KEY, plain.spec)
        self.choose(e, user, (CHLOROPHYLL, OVERCOAT))
        with patch.object(PROJECTION, 'complete_designer', side_effect=ValueError('creation completion refuses')):
            self.unchanged_refusal(e, lambda: self.design(e, user))
        self.assertIn(LEAFY, user.spec[PROJECTION.PENDING])
        self.fixture.turn(e, user, [user, only_leafy, plain])
        self.unchanged_refusal(e, lambda: self.design(e, user))
        self.assertIn(LEAFY, user.spec[PROJECTION.PENDING])
        self.fixture.valid(e)

    def test_legacy_projection_restores_without_invented_designer_then_actual_creation_preserves_it_as_history(self):
        user = self.user('leafy-legacy')
        e = self.fixture.engine(user)
        # Reconstruct the former saved projection schema, without claiming a new activation.
        choice = 'ability/엽록소+ability/방음'
        payload = deepcopy(PROJECTION.definition(self.r, LEAFY)['choices'][choice])
        GRANTS.transition(e, user, lambda staged, actual: PROJECTION._apply(staged, actual, LEAFY,
            choice, payload, None, 'retained historical projection', lifetime='until_reactivated'))
        legacy = deepcopy(user.spec[PROJECTION.KEY][LEAFY])
        self.assertNotIn('leafy_producer', legacy)
        self.assertEqual(user.spec.get(NATIVE.HISTORY, []), [])
        n = Engine.import_state(Rules(ROOT, ruleset='all'), json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        restored = next(c for c in n.everyone if c.entity_id == user.entity_id)
        self.assertEqual(restored.spec[PROJECTION.KEY][LEAFY], legacy)
        self.assertEqual(restored.spec.get(NATIVE.HISTORY, []), [])
        n.gm.snapshot('historical-projection')
        self.choose(n, restored, (CHLOROPHYLL, LEAF_GUARD))
        actual = self.design(n, restored)
        self.assertEqual(restored.spec[PROJECTION.LEAFY_HISTORY][0]['projection'], legacy)
        self.assertEqual(restored.spec[PROJECTION.LEAFY_HISTORY][0]['replaced_by'], actual['id'])
        self.assertNotIn(SOUNDPROOF, restored.abilities)
        self.assertEqual(len(restored.spec[NATIVE.HISTORY]), 1)
        before = deepcopy(n.export_state())
        def corrupt(staged, actor):
            actor.spec[PROJECTION.KEY][LEAFY]['leafy_producer']['receipt_id'] = 'no-such-completed-Designer'
        with self.assertRaises(ValueError):
            GRANTS.transition(n, restored, corrupt)
        self.assertEqual(n.export_state(), before)
        n.gm.restore('historical-projection', reason='restore the actual unbound legacy record')
        original = next(c for c in n.everyone if c.entity_id == user.entity_id)
        self.assertEqual(original.spec[PROJECTION.KEY][LEAFY], legacy)
        self.assertEqual(original.spec.get(NATIVE.HISTORY, []), [])
        self.fixture.valid(n)

    def test_actual_playtest_leaf_guard_pays_swift_uses_scene_quota_and_sun_ignores_only_frequency(self):
        user = self.user('leafy-active-playtest-candidates')
        e = self.fixture.engine(user)
        self.choose(e, user, (CHLOROPHYLL, LEAF_GUARD))
        self.design(e, user)
        base = e.initiative_value(user).value
        e.gm.set_hp(user, value=(user.base_max_hp + 1) // 2, reason='actual HP at or above half')
        self.assertEqual(e.initiative_value(user).value, base)
        e.gm.set_hp(user, value=(user.base_max_hp - 1) // 2, reason='actual HP below half')
        self.assertEqual(e.initiative_value(user).value, base * 2)
        # This existing native flag suppresses the owned projection without rewriting its history.
        user.abilities_suppressed = True
        self.assertEqual(e.initiative_value(user).value, base)
        user.abilities_suppressed = False
        e.gm.set_hp(user, value=user.base_max_hp, reason='actual recovery before the encounter')
        e.apply_status(user, '독', source='actual affliction', force=True)
        self.fixture.turn(e, user, [user])
        first = e.activate_ability(user, LEAF_GUARD, user)
        self.assertEqual(first['details'], {'status': '독', 'ignored_scene_frequency': False})
        self.assertNotIn('독', user.conditions)
        self.assertEqual(user.budget['swift'], 0)
        self.assertEqual(user.spec['frequency_state']['activations'][LEAF_GUARD]['used'], 1)
        e.end_of_turn(user)
        e.apply_status(user, '화상', source='different actual affliction', force=True)
        self.fixture.turn(e, user, [user])
        self.unchanged_refusal(e, lambda: e.activate_ability(user, LEAF_GUARD, user))
        e.gm.set_weather('sunny', reason='actual sunny turn permits frequency exception')
        second = e.activate_ability(user, LEAF_GUARD, (user, {'status': '화상'}))
        self.assertEqual(second['details'], {'status': '화상', 'ignored_scene_frequency': True})
        self.assertNotIn('화상', user.conditions)
        self.assertEqual(user.budget['swift'], 0)
        self.assertEqual(user.spec['frequency_state']['activations'][LEAF_GUARD]['used'], 1)
        e.end_of_turn(user)
        e.gm.set_weather(None, reason='actual sunlight ended')
        e.apply_status(user, '독', source='new actual affliction after sunlight', force=True)
        self.fixture.turn(e, user, [user])
        self.unchanged_refusal(e, lambda: e.activate_ability(user, LEAF_GUARD, user))
        self.fixture.valid(e)


if __name__ == '__main__':
    unittest.main()
