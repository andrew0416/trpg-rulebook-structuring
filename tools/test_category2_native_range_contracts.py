"""Actual move definitions, body range and one scoped accuracy roll per area."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
import body_state as BODY
import weapon_actions as WEAPONS
import effects as FX

MELEE = 'move/몸통박치기'
# Each native AC plus evasion puts this face between the two target thresholds.
AREAS = (('move/거품', 'burst', 5), ('move/잎날가르기', 'cone', 7),
         ('move/눈싸라기', 'line', 5))


class NativeRangeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')

    def add(self, spec):
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def fixture(self, role='trainer', shape='burst', distance=1):
        self.e = Engine(self.r, seed=209)
        self.e.grid = Grid(12, 12)
        moves = [MELEE] + [row[0] for row in AREAS]
        owner = self.add(build_trainer(
            self.r, 'native owner', 10,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            extra={'moves': moves, 'side': 'party',
                   'pos': (4, 4) if role == 'trainer' else (0, 0)}))
        self.a = owner
        if role == 'pokemon':
            self.a = self.add(build_pokemon(
                self.r, '이브이', 10, moves=moves, abilities=[],
                extra={'trainer_id': owner.entity_id, 'side': 'party', 'pos': (4, 4)}))
            self.e.gm.observe_loyalty(self.a, 6, reason='actual current owner')
        self.targets = []
        for name, speed, pos in (
                ('low evasion', 1, (4 + distance, 4)),
                ('high evasion', 20, (5, 5) if shape == 'burst' else (6, 4))):
            stats = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10)
            stats['spe'] = speed
            self.targets.append(self.add(build_trainer(
                self.r, name, 10, stats,
                extra={'moves': [], 'side': 'opponent', 'pos': pos})))
        self.b, self.c = self.targets
        self.far = self.add(build_pokemon(
            self.r, '잉어킹', 10, moves=[], abilities=[],
            extra={'trainer_id': self.b.entity_id, 'side': 'opponent', 'pos': (9, 9)}))
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def state(self):
        return deepcopy((self.a.budget, self.a.move_uses, self.a.pos,
                         [(c.hp, c.injuries, c.conditions, c.stages) for c in self.e.everyone],
                         self.e.rng.getstate()))

    def test_hp_loss_move_class_remains_independent_in_accuracy_and_trigger_matching(self):
        # C10-205 class identity only; Counter/Mirror Coat damage procedures
        # are separate obligations and are not certified by this test.
        cases = (('move/분노의앞니', '물리'), ('move/용의분노', '특수'),
                 ('move/소닉붐', '특수'), ('move/자연의분노', '특수'))
        for role in ('trainer', 'pokemon'):
            for uid, category in cases:
                for restored in (False, True):
                    with self.subTest(role=role, move=uid, restored=restored):
                        self.fixture(role=role)
                        self.e.gm.set_move(self.a, uid, reason='observed native HP-loss move')
                        target = self.add(build_trainer(
                            self.r, 'independent defenses', 10,
                            {'hp': 10, 'atk': 10, 'def': 30, 'spa': 10, 'spd': 5, 'spe': 10},
                            extra={'side': 'opponent', 'pos': (5, 4), 'moves': []}))
                        actor = self.a
                        engine = self.e
                        if restored:
                            self.e.gm.snapshot('hp-loss-class')
                            self.e.gm.set_move(actor, uid, add=False,
                                               reason='temporary actual withdrawal')
                            self.e.gm.restore('hp-loss-class')
                            self.assertIn(uid, {self.r.move_id(x) for x in actor.moves})
                            engine = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
                            index = {c.entity_id: c for c in engine.everyone}
                            actor, target = index[actor.entity_id], index[target.entity_id]
                        move = engine.r.move(uid)
                        self.assertEqual(move['class'], category)
                        self.assertEqual(move['damage_base'], 'variable')
                        effects = engine.r.move_mech(uid)[0]['effects_exec']
                        self.assertTrue(any(e['type'] == 'hp_loss' for e in effects))
                        before = (deepcopy(actor.budget), deepcopy(actor.move_uses),
                                  actor.hp, target.hp, engine.rng.getstate())
                        # This face distinguishes the classes even with the
                        # native -2 accuracy penalty for ranged use in melee.
                        self.assertEqual((target.evasion('물리'), target.evasion('특수')), (6, 2))
                        face = move['ac'] + 5
                        hit, natural, critical = engine.accuracy_check(actor, target, move, fixed_roll=face)
                        self.assertEqual((hit, natural, critical), (category == '특수', face, False))
                        event = {'event': 'on_hit_received', 'move': move}
                        for reaction, expected in (('move/카운터', '물리'), ('move/미러코트', '특수')):
                            trigger = FX.parse_trigger(engine.r.move(reaction)['effect'].split('.', 1)[0])
                            self.assertEqual(trigger['move_class'], expected)
                            self.assertNotIn('move', trigger)
                            self.assertEqual(FX.event_matches(trigger, event), category == expected)
                        self.assertEqual((actor.budget, actor.move_uses, actor.hp, target.hp,
                                          engine.rng.getstate()), before)

    def test_named_move_trigger_particles_keep_exact_identity_without_action_words(self):
        for uid, particle in (('move/몸통박치기', '를'), ('move/용의분노', '로'),
                              ('move/악의파동', '으로')):
            with self.subTest(move=uid, particle=particle):
                move = self.r.move(uid)
                text = '사용자가 ' + move['name'] + particle + ' 사용해 적에게 명중했을 때'
                trigger = FX.parse_trigger(text)
                self.assertEqual(trigger['move'], move['name'])
                event = {'event': trigger['event'], 'move': move}
                self.assertTrue(FX.event_matches(trigger, event))
                self.assertFalse(FX.event_matches(trigger, dict(event, move=self.r.move('move/물대포'))))
        examples = (
            ('hit by damaging move', {'event': 'on_hit_received'}),
            ('when user hits with a Fire-type move', {'event': 'on_hit_dealt', 'move_type': '불꽃'}),
            ('물타입 기술로 명중시켰을 때', {'event': 'on_hit_dealt', 'move_type': '물'}),
            ('사용자가 근접공격을 당했을 경우', {'event': 'on_hit_received', 'melee': True}),
            ('자신의 공격으로 인해 적이 기절했을 때', {'event': 'enemy_faint_by_user'}))
        for text, expected in examples:
            with self.subTest(text=text):
                self.assertEqual(FX.parse_trigger(text), expected)

    def test_actual_self_moves_select_and_affect_only_the_user_with_or_without_grid(self):
        for role in ('trainer', 'pokemon'):
            for grid in (True, False):
                for uid, stat, delta in (('move/칼춤', 'atk', 2),
                                         ('move/단단해지기', 'def', 1),
                                         ('move/고속이동', 'spe', 2)):
                    with self.subTest(role=role, grid=grid, move=uid):
                        self.fixture(role=role)
                        self.e.gm.set_move(self.a, uid, reason='native self move consumer')
                        if not grid:
                            self.e.grid = None
                        self.assertEqual(self.e.targets_in_range(
                            self.a, self.r.move(uid), [self.b, self.c, self.far], self.far),
                            [self.a])
                        others = [(c.hp, deepcopy(c.stages), c.pos)
                                  for c in self.e.everyone if c is not self.a]
                        stages = dict(self.a.stages)
                        shift, pos = self.a.budget['shift'], self.a.pos
                        with patch.object(self.e, 'd20') as roll:
                            self.e.use_move_on(self.a, self.a, uid, self.e.everyone)
                        stages[stat] += delta
                        self.assertEqual(self.a.stages, stages)
                        self.assertEqual([(c.hp, c.stages, c.pos)
                                          for c in self.e.everyone if c is not self.a], others)
                        self.assertEqual(self.a.move_uses[uid], 1)
                        self.assertEqual(self.a.budget['standard'], 0)
                        self.assertEqual((self.a.budget['shift'], self.a.pos), (shift, pos))
                        roll.assert_not_called()

    def test_actual_self_move_rejects_another_target_before_cost_movement_or_rng(self):
        uid = 'move/칼춤'
        for role in ('trainer', 'pokemon'):
            for grid in (True, False):
                for entry in ('use_move', 'use_move_on'):
                    with self.subTest(role=role, grid=grid, entry=entry):
                        self.fixture(role=role)
                        self.e.gm.set_move(self.a, uid, reason='native self target boundary')
                        if not grid:
                            self.e.grid = None
                        before = self.state()
                        with patch.object(self.e, 'd20') as roll:
                            with self.assertRaisesRegex(ValueError, 'self.*user'):
                                if entry == 'use_move':
                                    self.e.use_move(self.a, self.far, uid)
                                else:
                                    self.e.use_move_on(self.a, self.far, uid, self.e.everyone)
                        roll.assert_not_called()
                        self.assertEqual(self.state(), before)

    def test_self_only_range_preserves_source_choices_and_self_centered_areas(self):
        self.fixture()
        self.assertTrue(WEAPONS.is_self_only(WEAPONS.range_spec(
            self.e, self.r.move('move/칼춤'))))
        self.assertFalse(WEAPONS.is_self_only(WEAPONS.range_spec(
            self.e, self.r.move('move/하바네로엑기스'))))
        for uid, _, _ in AREAS:
            self.assertFalse(WEAPONS.is_self_only(WEAPONS.range_spec(self.e, self.r.move(uid))))
        self.assertFalse(WEAPONS.is_self_only({'origin': 'self', 'shape': 'burst', 'size': 1}))

    def test_actual_melee_default_is_one_meter_and_direct_two_meter_attempt_is_atomic(self):
        for role in ('trainer', 'pokemon'):
            for distance in (1, 2):
                with self.subTest(role=role, distance=distance):
                    self.fixture(role=role, distance=distance)
                    move = self.r.move(MELEE)
                    self.assertEqual(WEAPONS.range_spec(self.e, move)['origin'], 'melee')
                    self.assertEqual(BODY.melee_reach(self.a), 1)
                    self.assertEqual(self.b in self.e.targets_in_range(
                        self.a, move, self.e.everyone, self.b), distance == 1)
                    before = self.state()
                    hp = self.b.hp
                    with patch.object(self.e, 'd20', return_value=10) as roll:
                        result = self.e.use_move(self.a, self.b, MELEE)
                    if distance == 1:
                        self.assertGreater(result, 0)
                        self.assertLess(self.b.hp, hp)
                        self.assertEqual(roll.call_count, 1)
                    else:
                        self.assertEqual(result, 0)
                        self.assertEqual(roll.call_count, 0)
                        self.assertEqual(self.state(), before)

    def test_actual_burst_cone_line_share_one_face_with_different_target_evasion(self):
        for role in ('trainer', 'pokemon'):
            for uid, shape, face in AREAS:
                with self.subTest(role=role, move=uid):
                    self.fixture(role=role, shape=shape)
                    move = self.r.move(uid)
                    self.assertEqual(WEAPONS.range_spec(self.e, move)['shape'], shape)
                    self.assertEqual(self.e.targets_in_range(
                        self.a, move, self.e.everyone, self.b), [self.b, self.c])
                    hp = (self.a.hp, self.b.hp, self.c.hp, self.far.hp)
                    shift = self.a.budget['shift']
                    with patch.object(self.e, 'd20', return_value=face) as roll:
                        self.assertGreater(self.e.use_move_on(
                            self.a, self.b, uid, self.e.everyone), 0)
                    self.assertEqual(roll.call_count, 1)
                    self.assertLess(self.b.hp, hp[1])
                    self.assertEqual((self.a.hp, self.c.hp, self.far.hp), (hp[0], hp[2], hp[3]))
                    self.assertEqual(self.a.move_uses[uid], 1)
                    self.assertEqual(self.a.budget['standard'], 0)
                    self.assertEqual(self.a.budget['shift'], shift)
                    self.assertEqual(getattr(self.e, '_move_activation_scopes', []), [])

    def test_actual_natural_one_misses_every_target_but_pays_only_once(self):
        for uid, shape, _ in AREAS:
            with self.subTest(move=uid):
                self.fixture(shape=shape)
                hp = [(c.hp, c.injuries, dict(c.stages)) for c in self.e.everyone]
                with patch.object(self.e, 'd20', return_value=1) as roll:
                    self.assertEqual(self.e.use_move_on(
                        self.a, self.b, uid, self.e.everyone), 0)
                self.assertEqual(roll.call_count, 1)
                self.assertEqual([(c.hp, c.injuries, c.stages) for c in self.e.everyone], hp)
                self.assertEqual(self.a.move_uses[uid], 1)
                self.assertEqual(self.a.budget['standard'], 0)

    def test_actual_shared_face_controls_secondary_effects_on_every_hit(self):
        for role in ('trainer', 'pokemon'):
            with self.subTest(role=role):
                self.fixture(role=role)
                before = [c.stages['spe'] for c in (self.a, self.b, self.c, self.far)]
                with patch.object(self.e, 'd20', return_value=16) as roll:
                    self.e.use_move_on(self.a, self.b, 'move/거품', self.e.everyone)
                self.assertEqual(roll.call_count, 1)
                self.assertEqual([c.stages['spe'] for c in (self.a, self.b, self.c, self.far)],
                                 [before[0], before[1] - 1, before[2] - 1, before[3]])

    def test_actual_area_rejection_does_not_roll_or_change_targets(self):
        for uid, shape, _ in AREAS:
            with self.subTest(move=uid):
                self.fixture(shape=shape)
                self.a.budget['standard'] = 0
                before = self.state()
                with patch.object(self.e, 'd20', return_value=20) as roll:
                    self.assertEqual(self.e.use_move_on(
                        self.a, self.b, uid, self.e.everyone), 0)
                self.assertEqual(roll.call_count, 0)
                self.assertEqual(self.state(), before)


if __name__ == '__main__':
    unittest.main()
