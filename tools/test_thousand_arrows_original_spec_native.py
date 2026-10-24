"""Original-game first hit after source review, retaining PTU native grounding lifetime."""
from copy import deepcopy
import unittest

import test_grounded_effectiveness_native_pass as FIXTURE
import blessing_effects as BLESSINGS
import catalog_move_states as CATALOG
import coat_effects as COATS
import field_effects as FIELD

ARROWS, SMACK, GROUND, FIRE = FIXTURE.ARROWS, FIXTURE.SMACK, FIXTURE.GROUND, FIXTURE.FIRE


class ThousandArrowsOriginalSpecNativeTests(unittest.TestCase):
    setUpClass = classmethod(FIXTURE.GroundedEffectivenessNativeTests.setUpClass.__func__)
    setUp = FIXTURE.GroundedEffectivenessNativeTests.setUp
    begin = FIXTURE.GroundedEffectivenessNativeTests.begin
    use = FIXTURE.GroundedEffectivenessNativeTests.use
    hit = FIXTURE.GroundedEffectivenessNativeTests.hit
    restore = FIXTURE.GroundedEffectivenessNativeTests.restore
    expire = FIXTURE.GroundedEffectivenessNativeTests.expire
    equip_balloon = FIXTURE.GroundedEffectivenessNativeTests.equip_balloon
    ground = FIXTURE.GroundedEffectivenessNativeTests.ground

    def flying(self, types, *, levitate=False):
        self.e.gm.set_types(self.t, list(types), reason='actual first-hit recipient types')
        if levitate:
            self.e.gm.set_ability(self.t, '부유', reason='actual Levitate recipient')
        self.begin(self.t)
        self.e.aerial_move(self.t, self.t.pos, mode='sky', altitude=1,
            gm_distance=1, reason_text='actual airborne recipient before Thousand Arrows')
        self.assertFalse(CATALOG.grounded(self.t))

    def test_first_flying_hit_is_neutral_then_remaining_ground_components_apply(self):
        for types, later in ((('비행',), 1.0), (('강철', '비행'), 1.5),
                             (('벌레', '비행'), .5), (('풀', '비행'), .5)):
            with self.subTest(types=types):
                self.setUp()
                self.flying(types)
                source = deepcopy(self.rules.move(ARROWS))
                mechanics = deepcopy(self.rules.move_mech(ARROWS))
                self.assertEqual(self.e.type_multiplier('땅', self.t)[0], 0)
                self.hit(ARROWS, expected=1.0)
                self.assertTrue(CATALOG.grounded(self.t))
                self.assertEqual(self.t.spec['_movement_altitude'], 0)
                self.assertEqual(self.a.move_uses[ARROWS], 1)
                self.assertEqual(self.rules.moves_mech[ARROWS]['header']['frequency'],
                                 {'kind': 'scene', 'uses': 1})
                self.restore()
                self.hit(GROUND, expected=later)
                self.assertEqual(self.rules.move(ARROWS), source)
                self.assertEqual(self.rules.move_mech(ARROWS), mechanics)

    def test_native_arrows_on_already_grounded_targets_does_not_flatten_matchup(self):
        for types, expected in ((('강철', '비행'), 1.5), (('벌레', '비행'), .5),
                                (('풀', '비행'), .5)):
            with self.subTest(types=types):
                self.setUp()
                self.ground(SMACK, types)
                self.restore()
                self.hit(ARROWS, expected=expected)

    def test_non_flying_levitate_and_balloon_keep_ground_weakness_or_resistance(self):
        for immunity in ('levitate', 'balloon'):
            for types, expected in ((('강철',), 1.5), (('풀',), .5)):
                with self.subTest(immunity=immunity, types=types):
                    self.setUp()
                    self.flying(types, levitate=immunity == 'levitate')
                    if immunity == 'balloon':
                        self.equip_balloon('original-spec-balloon')
                    self.restore()
                    self.hit(ARROWS, expected=expected)
                    self.assertTrue(CATALOG.grounded(self.t))
                    if immunity == 'balloon':
                        self.assertIn('destroyed', self.e._physical_objects['original-spec-balloon'])
                    else:
                        self.assertIn('부유', self.t.abilities)

    def test_balloon_flying_first_hit_and_native_grounding_survive_cold_restore(self):
        self.flying(('강철', '비행'))
        self.equip_balloon('flying-original-balloon')
        self.restore()
        self.hit(ARROWS, expected=1.0)
        self.assertIn('destroyed', self.e._physical_objects['flying-original-balloon'])
        self.restore()
        self.hit(GROUND, expected=1.5)
        self.expire()
        before = self.t.hp
        self.assertEqual(self.use(GROUND), 0)
        self.assertEqual(self.t.hp, before)

    def test_actual_non_ground_type_uses_ordinary_matchup_and_keeps_its_own_immunity(self):
        self.flying(('풀', '비행'), levitate=True)
        self.a.type_override_next = '불꽃'
        self.restore()
        self.hit(ARROWS, expected=1.5, actual_type='불꽃')
        self.assertEqual(self.rules.move(ARROWS)['type'], '땅')
        self.assertIsNone(self.a.type_override_next)
        self.setUp()
        self.flying(('땅', '비행'))
        self.a.type_override_next = '전기'
        before = self.t.hp
        self.assertEqual(self.use(ARROWS), 0)
        self.assertEqual(self.t.hp, before)
        self.assertIsNone(self.a.type_override_next)

    def test_gravity_and_adopted_flying_resistance_prevent_the_first_neutral_override(self):
        for mode, expected in (('gravity', 1.5), ('optional_flying_resistance', 1.0)):
            with self.subTest(mode=mode):
                self.setUp()
                self.flying(('강철', '비행'))
                if mode == 'gravity':
                    self.e.gm.set_move(self.a, 'move/중력', reason='actual acquired Gravity')
                    self.use('move/중력', target=self.a)
                    self.assertTrue(FIELD.suppresses_ground_immunity(self.e, self.t))
                else:
                    self.e.configure_ground_flight_option(dict(enabled=True, gm_id='actual-gm',
                        reason='explicit Ground/Flying optional rule adoption'))
                self.restore()
                self.assertFalse(CATALOG.grounded(self.t))
                self.hit(ARROWS, expected=expected)

    def test_ground_stab_and_independent_registered_step_follow_neutral_base(self):
        self.flying(('풀', '비행'))
        self.e.gm.set_types(self.a, ['땅'], reason='actual Ground STAB attacker')
        self.a.registry.append({'type': 'type_effectiveness_override', 'steps': '+1'})
        facts = self.hit(ARROWS, expected=1.5)
        self.assertEqual(facts['damage_base'], 11)
        self.assertEqual(facts['damage_type'], '땅')
        self.assertEqual(self.rules.move(ARROWS)['damage_base'], 9)

    def test_native_reflect_and_tar_coat_preserve_independent_post_base_effects(self):
        self.flying(('벌레', '비행'))
        self.use('move/타르샷')
        coat = next(r for r in COATS.live(self.t) if r['source'] == 'move/타르샷')
        self.e.gm.set_move(self.t, 'move/리플렉터', reason='actual learned Reflect')
        self.use('move/리플렉터', actor=self.t, target=self.t)
        blessing = next(r for r in BLESSINGS.live(self.t) if r['source'] == 'move/리플렉터')
        self.rules.rulings.add_answer('team_blessing', True, reason='actual Reflect choice')
        self.hit(ARROWS, expected=1.0)
        self.assertEqual((blessing['decisions'][-1]['multiplier_before'],
                          blessing['decisions'][-1]['multiplier_after']), (1.0, .5))
        self.assertIn(coat, COATS.live(self.t))
        self.hit(FIRE, expected=2.0)
        self.assertFalse(COATS.live(self.t))

    def test_external_ice_override_is_not_suppressed_with_the_source_local_legacy_clause(self):
        self.flying(('풀', '비행'))
        self.a.registry.append({'type': 'type_effectiveness_override',
            'if_target_type': '비행', 'as_if_attack_type': '얼음'})
        self.hit(ARROWS, expected=2.0)

    def test_source_owned_final_chart_and_other_ability_immunity_are_preserved(self):
        self.e.gm.set_types(self.t, ['유리', '땅'], reason='source-owned final chart recipient')
        self.e.gm.set_ability(self.t, '부유', reason='actual unrelated Levitate projection')
        self.hit(ARROWS, expected=1.5)
        self.setUp()
        self.flying(('강철', '비행'))
        self.e.gm.set_ability(self.t, '불가사의부적', reason='actual independent Wonder Guard')
        before = self.t.hp
        self.assertEqual(self.use(ARROWS), 0)
        self.assertEqual(self.t.hp, before)
        self.assertFalse(CATALOG.grounded(self.t))


if __name__ == '__main__':
    unittest.main()
