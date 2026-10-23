"""The native upper Move entry carries the existing Set Damage selection."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import test_category2_csv_item_transfers as FIX
from engine import Engine, Rules
from grid import Grid
import world_entities as WORLD


class NativeSetDamageTests(unittest.TestCase):
    setUpClass = classmethod(FIX.Tests.setUpClass.__func__)

    def world(self, name, positions):
        fixture = FIX.Tests()
        fixture.r = self.r
        e, a, *rest = fixture.fixture(name, held=(None,) * (len(positions) + 1), seed=241)
        mid, targets = rest[-1], rest[:-1]
        e.grid = Grid(20, 20)
        a.pos, a.side = (2, 2), 'party'
        for target, position in zip(targets, positions):
            target.pos, target.side = position, 'foes'
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        for target in targets:
            target.aoo_used = True
        return e, a, targets, mid

    def observed_damage(self, calls):
        original = Engine.roll_damage
        def observe(e, a, target, move, crit=False, set_damage=False, *args, **kwargs):
            calls.append((target.entity_id, set_damage))
            return original(e, a, target, move, crit, set_damage, *args, **kwargs)
        return observe

    def valid(self, e):
        state = e.validate_state()
        self.assertTrue(state['valid'], state['issues'])

    def test_single_shared_area_and_uninterrupted_chain_use_set_without_damage_dice(self):
        for name, positions in (('몸통박치기', [(3, 2)]),
                                ('불태우기', [(3, 2), (4, 2)]),
                                # Adjacent explicitly selected recipients isolate Set Damage delivery.
                                ('트리플다이브', [(3, 2), (2, 3), (1, 2)])):
            with self.subTest(native_move=name):
                e, a, targets, mid = self.world(name, positions)
                before = {target.entity_id: target.hp for target in targets}
                calls = []
                with patch.object(Engine, 'd20', return_value=16), patch.object(
                        Engine, 'roll_expr', side_effect=AssertionError('Set Damage must not roll damage dice')), patch.object(
                        Engine, 'roll_damage', self.observed_damage(calls)):
                    options=({'chain_steps':[dict(target=t,path=[],forgo_remaining=False) for t in targets]}
                             if name=='트리플다이브' else {})
                    e.use_move_on(a, targets[0], mid, e.everyone, set_damage=True, **options)
                self.assertEqual(calls, [(target.entity_id, True) for target in targets])
                self.assertTrue(all(target.hp < before[target.entity_id] for target in targets))
                self.assertEqual(a.move_uses[mid], 1)
                self.assertEqual(a.budget['standard'], 0)
                self.valid(e)

    def test_area_reactive_wait_and_json_resume_preserve_set_for_each_real_recipient(self):
        import test_category2_move_defense_reactions as DEFENSE
        import passive_events as PASSIVE
        f = DEFENSE.MoveDefenseReactionsTests()
        f.rules = self.r
        f.setUp()
        f.r.pos = (3, 4)
        f.watch()
        hp = {actor.entity_id: actor.hp for actor in (f.t, f.r)}
        with patch.object(Engine, 'd20', return_value=16), patch.object(
                Engine, 'roll_expr', side_effect=AssertionError('Set Damage must not roll damage dice')):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_move_on(f.a, f.t, 'move/지진', f.e.everyone, set_damage=True)
        event = f.e._passive_pending
        completion = f.completion()
        self.assertIs(completion['activation_continuation']['scope']['options']['set_damage'], True)
        self.assertIs(f.e._passive_events[event]['continuation']['args']['set_damage'], True)
        before_rng = f.e.rng.getstate()
        f.fresh()
        calls = []
        with patch.object(Engine, 'd20', side_effect=AssertionError('native shared accuracy must not reroll')), patch.object(
                Engine, 'roll_expr', side_effect=AssertionError('resumed Set Damage must not roll dice')), patch.object(
                Engine, 'roll_damage', self.observed_damage(calls)):
            f.choose(event, use=False)
        self.assertEqual(calls, [(f.t.entity_id, True), (f.r.entity_id, True)])
        self.assertTrue(all(actor.hp < hp[actor.entity_id] for actor in (f.t, f.r)))
        self.assertEqual(f.e.rng.getstate(), before_rng)
        self.assertEqual(f.completion()['phase'], 'complete')
        self.assertEqual((f.a.move_uses['move/지진'], f.a._action_history), (1, ['standard']))
        self.valid(f.e)

    def test_public_setup_resolution_reuses_set_choice_after_native_preparation_restore(self):
        import test_category2_setup_move_state as SETUP_FIX
        import setup_move_state as SETUP
        f = SETUP_FIX.SetupMoveStateTests()
        f.r = Rules(self.r.root, ruleset='all')
        f.setUp()
        self.assertEqual(f.e.use_setup_move_on(f.a, f.b, SETUP_FIX.FLY, f.e.everyone,
                                               setup_options={}, set_damage=True), 0)
        saved = json.loads(json.dumps(f.e.export_state()))
        f.e = Engine.import_state(f.r, saved)
        f.a, f.b = (WORLD.actor_index(f.e)[actor.entity_id] for actor in (f.a, f.b))
        f.next_turn()
        calls = []
        path = [{'position': (3, 2), 'altitude': 25}, {'position': (4, 2), 'altitude': 25}]
        hp = f.b.hp
        with patch.object(Engine, 'd20', return_value=16), patch.object(
                Engine, 'roll_expr', side_effect=AssertionError('Set Damage must not roll damage dice')), patch.object(
                Engine, 'roll_damage', self.observed_damage(calls)):
            f.e.use_setup_move_on(f.a, f.b, SETUP_FIX.FLY, f.e.everyone,
                                  setup_options={'path': path}, set_damage=True)
        self.assertEqual(calls, [(f.b.entity_id, True)])
        self.assertLess(f.b.hp, hp)
        self.assertIsNone(SETUP.pending(f.a))
        self.assertEqual(f.a.move_uses[SETUP_FIX.FLY], 1)
        self.valid(f.e)

    def test_invalid_bool_and_target_free_damage_declaration_refuse_before_cost_or_rng(self):
        e, a, targets, mid = self.world('몸통박치기', [(3, 2)])
        for entry in ('use_move_on', 'use_move', 'use_setup_move_on'):
            for value in (None, 0, 1, 'set'):
                with self.subTest(entry=entry, value=value):
                    before = deepcopy((a.budget, a.move_uses, e.rng.getstate(), a.hp, targets[0].hp))
                    args = (a, targets[0], mid) + (() if entry == 'use_move' else (e.everyone,))
                    with self.assertRaisesRegex(ValueError, 'boolean Set Damage'):
                        getattr(e, entry)(*args, set_damage=value)
                    self.assertEqual((a.budget, a.move_uses, e.rng.getstate(), a.hp, targets[0].hp), before)
        import test_category2_hazard_state as HAZARD_FIX
        hazard = HAZARD_FIX.HazardStateTests()
        hazard.r = self.r
        e, a, target = hazard.world()
        before = deepcopy((a.budget, a.move_uses, e.rng.getstate(), e.hazards))
        with self.assertRaisesRegex(ValueError, 'no accuracy or damage declaration'):
            e.use_move_on(a, a, 'move/압정뿌리기', [a, target], aim=HAZARD_FIX.CELLS8, set_damage=True)
        self.assertEqual((a.budget, a.move_uses, e.rng.getstate(), e.hazards), before)
        e, a, targets, mid = self.world('날려버리기', [(15, 15)])
        before = deepcopy((a.budget, a.move_uses, e.rng.getstate()))
        with self.assertRaisesRegex(ValueError, 'no accuracy or damage declaration'):
            e.use_move_on(a, targets[0], mid, e.everyone, aim=(2, 8), set_damage=True)
        self.assertEqual((a.budget, a.move_uses, e.rng.getstate()), before)
        with patch.object(Engine, 'd20', side_effect=AssertionError('empty area has no accuracy')), patch.object(
                Engine, 'roll_damage', side_effect=AssertionError('empty area has no damage')):
            e.use_move_on(a, targets[0], mid, e.everyone, aim=(2, 8), set_damage=False)
        self.assertEqual(a.move_uses[mid], 1)
        self.assertEqual(a.budget['standard'], 0)
        self.valid(e)


if __name__ == '__main__':
    unittest.main()
