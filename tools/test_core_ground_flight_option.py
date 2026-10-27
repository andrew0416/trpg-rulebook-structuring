"""C11-152: adopted Groundsource immunity reads actual native airborne state."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from engine import Combatant, Engine, Rules
from builder import build_pokemon, build_trainer
from grid import Grid
import body_state as BODY
import catalog_move_states as CATALOG
import field_effects as FIELD
import newground_flight_option as OPTION
import state_codec as CODEC

EARTH = 'move/대지의힘'
MUD = 'move/진흙폭탄'
VOLTAGE = 'move/라이징볼트'
ARROWS = 'move/사우전드애로'
SMACK = 'move/떨어뜨리기'


class GroundFlightOptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=11152)
        self.e.grid = Grid(10, 10)
        self.actor = Combatant(self.r, build_trainer(self.r, 'ground option attacker', 10,
            dict(hp=10, atk=5, **{'def': 5}, spa=5, spd=5, spe=5),
            pos=(1, 1), moves=[EARTH, MUD, VOLTAGE, ARROWS, SMACK], abilities=[],
            extra={'movement': {'land': 6}}))
        self.target = Combatant(self.r, build_pokemon(self.r, '브케인', 30,
            name='actual airborne target', wild=True, moves=[], abilities=[], pos=(2, 1),
            extra={'movement': {'land': 6, 'sky': 6, 'levitate': 6}, 'movement_basis': 'current'}))
        for actor in (self.actor, self.target):
            self.e.gm.add_combatant(actor)
            BODY.observe(self.e, actor, [(0, 0)], reason='observed actual one-cell body')

    def adopt(self, enabled=True):
        return self.e.configure_ground_flight_option(dict(enabled=enabled, gm_id='actual-gm',
            reason='GM explicitly selects the entire printed optional paragraph'))

    def flight(self, mode='sky'):
        self.e.start_round([self.target, self.actor])
        self.e.start_of_turn(self.target)
        result = self.e.aerial_move(self.target, self.target.pos, mode=mode, altitude=1,
            gm_distance=1, reason_text='GM observes one metre of actual vertical flight')
        self.assertEqual((result['altitude'], self.target.budget['shift']), (1, 0))
        self.assertTrue(self.target.airborne)
        self.e.end_of_turn(self.target)
        self.e.start_of_turn(self.actor)

    def reason(self, uid):
        return OPTION.block_reason(self.e, self.actor, self.target,
            self.r.move(uid), self.r.move_mech(uid)[0])

    def test_explicit_adoption_is_atomic_and_type_component_preserves_composition(self):
        source_chart = deepcopy(self.r.mech('combat/type-chart'))
        self.e.gm.set_types(self.target, ['비행'], reason='actual single Flying type')
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], 0)
        self.assertIsNone(OPTION.validate(self.e))
        for values in ({'enabled': 1, 'gm_id': 'gm', 'reason': 'invalid boolean'},
                       {'enabled': True, 'gm_id': '', 'reason': 'missing GM'},
                       {'enabled': True, 'gm_id': 'gm', 'reason': ''}):
            with self.assertRaises(ValueError):
                OPTION.configure(self.e, **values)
            self.assertFalse(hasattr(self.e, OPTION.KEY))
        chosen = self.adopt()
        chosen['enabled'] = False
        self.assertTrue(OPTION.validate(self.e)['enabled'])
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], .5)
        self.e.gm.set_types(self.target, ['독', '비행'], reason='actual dual-type composition')
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], 1)
        self.e.gm.set_types(self.target, ['풀', '비행'], reason='both actual components resist Ground')
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], .25)
        self.e.gm.set_types(self.target, ['유리', '땅'], reason='existing source-owned final defense chart')
        selected_chart = self.e.type_multiplier('물', self.target)
        self.adopt(False)
        self.assertEqual(self.e.type_multiplier('물', self.target), selected_chart)
        self.assertEqual(self.r.mech('combat/type-chart'), source_chart)

    def test_external_json_dispatch_requires_gm_adoption_and_changes_native_consumers(self):
        self.flight()
        self.e.gm.set_types(self.target, ['비행'], reason='actual Flying type for scripted companion')
        document = json.loads((ROOT / 'data/examples/ground-flight-option.json').read_text(encoding='utf-8'))
        pending = self.e.execute_source_policy_operations(self.actor, self.target, document,
            request_id='ground-flight/pending')
        self.assertEqual(pending['status'], 'PolicyInputsRequired')
        self.assertFalse(hasattr(self.e, OPTION.KEY))
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], 0)
        decisions = {key: {'value': value, 'reason': 'explicit GM campaign choice'}
            for key, value in dict(enabled=True, gm_id='actual-gm',
                reason='GM adopts both sentences of the printed optional paragraph').items()}
        completed = self.e.execute_source_policy_operations(self.actor, self.target, document,
            decisions=decisions, request_id='ground-flight/adopt')
        self.assertEqual(completed['status'], 'PolicyOperationsCompleted')
        self.assertEqual(completed['selected_id'], OPTION.SOURCE)
        step = completed['operation_results'][0]
        self.assertEqual((step['operation'], step['foundation_id']),
                         ('combat.ground_flight_option', 'combat.hit'))
        self.assertTrue(step['result']['enabled'])
        self.assertTrue(OPTION.validate(self.e)['enabled'])
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], .5)
        self.assertEqual(self.reason(EARTH), OPTION.SOURCE)
        self.assertFalse(self.e.accuracy_check(self.actor, self.target,
            self.r.move(EARTH), fixed_roll=20)[0])

    def test_native_paid_sky_and_levitate_prevent_hit_damage_and_target_effects(self):
        for mode in ('sky', 'levitate'):
            with self.subTest(mode=mode):
                self.setUp(); self.flight(mode)
                self.assertIsNone(self.reason(EARTH))
                self.assertTrue(self.e.accuracy_check(self.actor, self.target,
                    self.r.move(EARTH), fixed_roll=20)[0])
                self.adopt()
                before = (self.target.hp, dict(self.target.stages), set(self.target.conditions))
                self.assertEqual(self.reason(EARTH), OPTION.SOURCE)
                self.assertFalse(self.e.accuracy_check(self.actor, self.target,
                    self.r.move(EARTH), fixed_roll=20)[0])
                with patch.object(Engine, 'd20', return_value=20):
                    self.e.use_move(self.actor, self.target, EARTH)
                self.assertEqual((self.target.hp, self.target.stages, self.target.conditions), before)
                self.assertEqual(self.actor.budget['standard'], 0)
                self.assertTrue(self.e.accuracy_check(self.actor, self.target,
                    self.r.move(MUD), fixed_roll=20)[0])
                self.assertIsNone(self.reason(MUD))

    def test_ground_capability_and_supported_height_do_not_invent_current_flight(self):
        self.adopt()
        self.assertGreater(self.target.spec['movement']['sky'], 0)
        self.assertIsNone(self.reason(EARTH))
        self.target.spec['_movement_altitude'] = 1  # Observed elevated support, not flight.
        self.target.airborne = False
        self.assertIsNone(self.reason(EARTH))
        self.e.start_round([self.actor, self.target]); self.e.start_of_turn(self.actor)
        before = self.target.hp
        with patch.object(Engine, 'd20', return_value=20):
            self.e.use_move(self.actor, self.target, EARTH)
        self.assertLess(self.target.hp, before)
        self.e.gm.set_movement_capabilities(self.actor, {'land': 6, 'sky': 6},
            basis='current', reason='observed actual trainer flight capability')
        self.e.aerial_move(self.actor, self.actor.pos, mode='sky', altitude=1,
            gm_distance=1, reason_text='trainer is actually in flight')
        self.assertTrue(self.actor.airborne)
        self.e.gm.set_types(self.actor, ['비행'], reason='actual trainer Flying type')
        self.assertEqual(self.e.type_multiplier('땅', self.actor)[0], 0)
        self.assertIsNone(OPTION.block_reason(self.e, self.target, self.actor,
            self.r.move(EARTH), self.r.move_mech(EARTH)[0]))

    def test_actual_groundsource_keywords_include_non_ground_and_preserve_pass_moves(self):
        self.adopt(); self.flight()
        expected = {'move/구멍파기', EARTH, 'move/지진', 'move/땅가르기',
                    'move/매그니튜드', 'move/그라운드포스', 'move/사우전드웨이브', VOLTAGE}
        # This is a declaration inventory in the test, never a runtime whitelist.
        declared = {uid for uid, row in self.r.moves_mech.items()
                    if '지면통과' in row.get('header', {}).get('range', {}).get('raw', '')}
        self.assertEqual(declared, expected)
        for uid in declared:
            self.assertEqual(self.reason(uid), OPTION.SOURCE, uid)
        self.assertEqual(self.r.move(VOLTAGE)['type'], '전기')
        self.assertFalse(self.e.accuracy_check(self.actor, self.target,
            self.r.move(VOLTAGE), fixed_roll=20)[0])
        self.assertIsNone(self.reason(ARROWS))
        self.e.gm.set_types(self.target, ['비행'], reason='actual Flying type')
        self.e.gm.set_ability(self.target, '부유', reason='actual owned Levitate Ability')
        self.assertTrue(self.e.accuracy_check(self.actor, self.target,
            self.r.move(ARROWS), fixed_roll=20)[0])
        self.actor.registry.append({'type': 'gain_keyword', 'keyword': '지면통과'})
        self.assertEqual(self.reason(MUD), OPTION.SOURCE)
        self.actor.registry.pop()
        self.assertIsNone(self.reason(MUD))

    def test_native_grounding_and_gravity_retain_existing_exception_scope(self):
        self.adopt(); self.flight()
        self.e.gm.set_types(self.target, ['비행'], reason='actual Flying target')
        gravity = next(effect for effect in self.r.move_mech('move/중력')[0]['effects_exec']
                       if effect.get('type') == 'field_effect')
        FIELD.install(self.e, self.actor, gravity, 'move/중력')
        self.assertTrue(FIELD.suppresses_ground_immunity(self.e, self.target))
        self.assertIsNone(self.reason(EARTH))
        self.assertEqual(self.e.type_multiplier('땅', self.target)[0], .5)
        self.assertEqual(self.reason(VOLTAGE), OPTION.SOURCE)  # Gravity is Ground-scoped.
        self.e.gm.set_types(self.target, ['불꽃'], reason='actual non-Flying sky-capable target')
        self.assertEqual(self.reason(EARTH), OPTION.SOURCE)
        self.e.gm.set_ability(self.target, '부유', reason='actual Gravity-suppressed immunity')
        self.assertIsNone(self.reason(EARTH))
        FIELD.clear(self.e)
        with patch.object(Engine, 'd20', return_value=20):
            self.e.use_move(self.actor, self.target, SMACK)
        self.assertTrue(CATALOG.grounded(self.target))
        self.assertEqual((self.target.airborne, self.target.spec['_movement_altitude']), (False, 0))
        self.assertIsNone(self.reason(EARTH))
        self.assertGreater(self.e.resolve_attack_damage(self.actor, self.target,
            self.r.move(EARTH), set_damage=True), 0)
        self.adopt(False)
        self.e.gm.set_hp(self.target, self.target.base_max_hp,
            reason='restore actual target after the preceding resolved hit')
        self.assertTrue(CATALOG.grounded(self.target))
        self.assertGreater(self.e.resolve_attack_damage(self.actor, self.target,
            self.r.move(EARTH), set_damage=True), 0)
        self.e.gm.set_ability(self.target, '파리덫',
            reason='actual distinct Ground/Bug damage immunity is not Levitate')
        self.assertEqual(self.e.roll_damage(self.actor, self.target,
            self.r.move(EARTH), set_damage=True), 0)

    def test_direct_damage_reuses_hit_gate_before_rng_or_target_changes(self):
        self.adopt(); self.flight()
        before = (self.target.hp, deepcopy(self.target.stages), set(self.target.conditions), self.e.rng.getstate())
        self.assertEqual(self.e.resolve_attack_damage(self.actor, self.target,
            self.r.move(EARTH)), 0)
        self.assertEqual((self.target.hp, self.target.stages, self.target.conditions, self.e.rng.getstate()), before)
        self.assertEqual(self.actor.budget['standard'], 1)
        self.assertTrue(self.target.airborne)

    def test_choice_and_actual_position_survive_both_restore_paths_and_reject_tampering(self):
        self.adopt(); self.flight()
        self.e.gm.snapshot('adopted flight')
        self.adopt(False)
        self.assertIsNone(self.reason(EARTH))
        self.e.gm.restore('adopted flight')
        self.assertEqual(self.reason(EARTH), OPTION.SOURCE)
        payload = json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False))
        restored = CODEC.load_engine(self.r, payload)
        actors = {actor.entity_id: actor for actor in restored.everyone}
        self.assertTrue(actors[self.target.entity_id].airborne)
        self.assertEqual(OPTION.block_reason(restored, actors[self.actor.entity_id],
            actors[self.target.entity_id], self.r.move(EARTH), self.r.move_mech(EARTH)[0]), OPTION.SOURCE)
        getattr(restored, OPTION.KEY)['enabled'] = False
        with self.assertRaisesRegex(CODEC.StateCodecError, 'adoption changed'):
            CODEC.dump_engine(restored)


if __name__ == '__main__':
    unittest.main()
