"""Real native multi-hit attacks retain optional weather charges and costs."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
import test_category2_native_setup_state as NATIVE
import blessing_effects as B
import weather_blessings as WEATHER
import world_entities as WORLD

FIVE = 'move/물수리검'
DOUBLE = 'move/뼈다귀부메랑'
CHAIN = 'move/트리플다이브'


class WeatherChargeMultihitSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='all')
        cls.base_rulings = deepcopy(cls.r.rulings)

    def scene(self, weather='비바라기', role='trainer'):
        self.r.rulings = deepcopy(self.base_rulings)
        case = NATIVE.NativeSetupStateTests()
        case.r = self.r
        case.fixture(role)
        e, a, b = case.e, case.a, case.b
        mid = 'move/' + weather
        e.gm.set_move(a, mid, reason='actual learned selected homebrew weather Move')
        e.use_move(a, a, mid)
        e.end_of_turn(a)
        return e, a, b

    def pool(self, actor, *, historical=False):
        rows = actor.spec.get(B.HISTORY, []) if historical else B.live(actor)
        return next(row for row in rows if WEATHER.is_weather(row))

    def choose(self, e, answer):
        prompts = []
        def decide(prompt):
            if prompt.get('type') == 'weather_blessing':
                prompts.append(deepcopy(prompt))
                return answer
            return None
        e.rulings.provider = decide
        return prompts

    def turn(self, e, actor):
        if e._active_turn_actor is not None:
            e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=20)

    def restored(self, e, *actors):
        loaded = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        index = WORLD.actor_index(loaded)
        return loaded, *(index[actor.entity_id] for actor in actors)

    def test_actual_five_strike_combined_damage_keeps_trainer_pokemon_and_optional_charge(self):
        for role in ('trainer', 'pokemon'):
            for selected in (True, False):
                with self.subTest(role=role, selected=selected):
                    e, a, b = self.scene(role=role)
                    e.gm.set_move(a, FIVE, reason='actual learned printed Five Strike Move')
                    self.turn(e, a)
                    prompts = self.choose(e, selected)
                    hp, rng = b.hp, e.rng.getstate()
                    with patch.object(Engine, 'd20', return_value=18) as accuracy, \
                         patch.object(Engine, 'roll_expr', return_value=(7, [7])) as dice:
                        damage = e.use_move_on(a, b, FIVE, e.everyone, set_damage=True)
                    self.assertGreater(damage, 0)
                    self.assertEqual((accuracy.call_count, dice.call_count), (1, 1))
                    self.assertEqual(a.spec['five_strike_history'][-1]['hits'], 4)
                    self.assertEqual((b.hp, a.budget['standard'], a.move_uses[FIVE]), (hp - damage, 0, 1))
                    self.assertEqual(e.rng.getstate(), rng)
                    pool = self.pool(a)
                    self.assertEqual((len(prompts), len(pool['decisions']), B.remaining(pool)),
                                     (1, 1, 1 if selected else 2))
                    decision = pool['decisions'][0]
                    self.assertEqual((decision['selected'], decision['direction'], decision['target_id']),
                                     (selected, 'offense', b.entity_id))
                    self.assertEqual((decision['multiplier_before'], decision['multiplier_after']),
                                     (1, 1.5 if selected else 1))
                    self.assertEqual(decision['damage_after'], damage)
                    self.restored(e)

    def test_actual_wild_water_shuriken_in_sunny_weather_may_use_or_decline_defense(self):
        for selected, face in ((True, 18), (False, 18), (True, 1)):
            with self.subTest(selected=selected, face=face):
                e, a, _ = self.scene('쾌청')
                wild = Combatant(self.r, build_pokemon(
                    self.r, 'Greninja', 30, moves=[FIVE], abilities=[], wild=True,
                    pos=(3, 2), extra={'side': 'wild'}))
                e.gm.add_combatant(wild)
                self.turn(e, wild)
                prompts = self.choose(e, selected)
                hp = a.hp
                with patch.object(Engine, 'd20', return_value=face), \
                     patch.object(Engine, 'roll_expr', return_value=(7, [7])) as dice:
                    damage = e.use_move_on(wild, a, FIVE, e.everyone, set_damage=True)
                self.assertEqual(dice.call_count, 1)
                self.assertEqual((wild.spec['five_strike_history'][-1]['hits'],
                                  wild.budget['standard'], wild.move_uses[FIVE]), (4, 0, 1))
                pool = self.pool(a)
                if face == 1:
                    self.assertEqual((damage, a.hp, prompts, pool['decisions'], B.remaining(pool)),
                                     (0, hp, [], [], 2))
                else:
                    self.assertGreater(damage, 0)
                    self.assertEqual(a.hp, hp - damage)
                    self.assertEqual((len(prompts), len(pool['decisions']), B.remaining(pool)),
                                     (1, 1, 1 if selected else 2))
                    decision = pool['decisions'][0]
                    self.assertEqual((decision['direction'], decision['attacker_id'], decision['target_id']),
                                     ('defense', wild.entity_id, a.entity_id))
                    self.assertEqual((decision['multiplier_before'], decision['multiplier_after']),
                                     (1, 0.5 if selected else 1))
                    self.assertEqual(decision['damage_after'], damage)
                self.restored(e)

    def test_actual_double_strike_rolls_combine_before_one_optional_charge(self):
        for faces in ((18, 18), (18, 1), (1, 1)):
            for selected in (True, False):
                with self.subTest(faces=faces, selected=selected):
                    e, a, b = self.scene('모래바람')
                    e.gm.set_move(a, DOUBLE, reason='actual learned printed Double Strike Move')
                    self.turn(e, a)
                    prompts = self.choose(e, selected)
                    hp = b.hp
                    with patch.object(Engine, 'd20', side_effect=faces) as accuracy:
                        damage = e.use_move_on(a, b, DOUBLE, e.everyone, set_damage=True)
                    self.assertEqual(accuracy.call_count, 2)
                    rolls = a.spec['multi_strike_history'][-1]['rolls']
                    self.assertEqual([row[1] for row in rolls], list(faces))
                    self.assertEqual(sum(row[0] for row in rolls), faces.count(18))
                    self.assertEqual((a.move_uses[DOUBLE], a.budget['standard']), (1, 0))
                    pool = self.pool(a)
                    if faces == (1, 1):
                        self.assertEqual((damage, b.hp, prompts, pool['decisions'], B.remaining(pool)),
                                         (0, hp, [], [], 2))
                    else:
                        self.assertGreater(damage, 0)
                        self.assertEqual(b.hp, hp - damage)
                        self.assertEqual((len(prompts), len(pool['decisions']), B.remaining(pool)),
                                         (1, 1, 1 if selected else 2))
                        self.assertEqual(pool['decisions'][0]['damage_after'], damage)
                    self.restored(e)

    def test_actual_multihit_charge_decision_survives_both_restores_and_exhausts_once(self):
        for restoration in ('gm', 'json'):
            with self.subTest(restoration=restoration):
                e, a, b = self.scene()
                e.gm.set_move(a, FIVE, reason='actual learned printed Five Strike Move')
                self.turn(e, a)
                self.choose(e, True)
                with patch.object(Engine, 'd20', return_value=18), \
                     patch.object(Engine, 'roll_expr', return_value=(7, [7])):
                    e.use_move_on(a, b, FIVE, e.everyone, set_damage=True)
                identity = self.pool(a)['id']
                first = deepcopy(self.pool(a)['decisions'])
                hp = b.hp
                if restoration == 'gm':
                    e.gm.snapshot('one actual multi-hit charge')
                    e.gm.set_weather(None, reason='actual intervening weather removal')
                    e.gm.restore('one actual multi-hit charge')
                else:
                    e, a, b = self.restored(e, a, b)
                self.assertEqual((self.pool(a)['decisions'], B.remaining(self.pool(a)), b.hp),
                                 (first, 1, hp))
                # Every-other-turn frequency remains owned by actual turns.
                self.turn(e, a)
                self.turn(e, a)
                self.choose(e, True)
                with patch.object(Engine, 'd20', return_value=18), \
                     patch.object(Engine, 'roll_expr', return_value=(7, [7])):
                    e.use_move_on(a, b, FIVE, e.everyone, set_damage=True)
                self.assertFalse(any(row['id'] == identity for row in B.live(a)))
                closed = self.pool(a, historical=True)
                self.assertEqual((closed['id'], B.remaining(closed), len(closed['decisions'])),
                                 (identity, 0, 2))
                self.assertEqual(closed['decisions'][:1], first)
                self.assertNotEqual(closed['decisions'][0]['activation_id'], closed['decisions'][1]['activation_id'])
                self.assertEqual((a.move_uses[FIVE], len(a.spec['five_strike_history'])), (2, 2))
                self.assertEqual(e.weather, 'rain')
                self.restored(e)

    def test_native_multihit_final_hook_and_actual_chain_rollback_keep_charge_capacity(self):
        e, a, b = self.scene()
        e.gm.set_move(a, FIVE, reason='actual learned printed Five Strike Move')
        self.turn(e, a)
        prompts = self.choose(e, True)
        hp = b.hp
        with patch.dict(e.rulings.hooks, {'before_damage': []}):
            e.rulings.add_hook('before_damage', lambda value, context: 0,
                               reason='actual final damage nullification')
            with patch.object(Engine, 'd20', return_value=18), \
                 patch.object(Engine, 'roll_expr', return_value=(7, [7])):
                self.assertEqual(e.use_move_on(a, b, FIVE, e.everyone, set_damage=True), 0)
        self.assertEqual((b.hp, len(prompts), self.pool(a)['decisions'], B.remaining(self.pool(a))),
                         (hp, 1, [], 2))
        self.assertEqual((a.move_uses[FIVE], a.budget['standard']), (1, 0))
        self.restored(e)

        # This printed chain owns its existing atomic native activation. One
        # observed recipient avoids changing the separate area-cardinality rule.
        e, a, b = self.scene()
        e.gm.set_move(a, CHAIN, reason='actual learned printed chain Move')
        self.turn(e, a)
        prompts = self.choose(e, True)
        options = {'chain_steps': [{'target': b, 'path': [], 'forgo_remaining': True}],
                   'set_damage': True}
        def reject_after_weather(value, context):
            raise ValueError('actual late weather damage rejection')
        with patch.dict(e.rulings.hooks, {'before_damage': []}):
            e.rulings.add_hook('before_damage', reject_after_weather,
                               reason='actual final damage observer rejects this resolution')
            with patch.object(Engine, 'd20', return_value=18):
                assert_rejected_unchanged(
                    e, lambda: e.use_move_on(a, b, CHAIN, e.everyone, **options),
                    reason_pattern='actual late weather damage rejection')
        self.assertEqual((len(prompts), self.pool(a)['decisions'], B.remaining(self.pool(a))), (1, [], 2))
        with patch.object(Engine, 'd20', return_value=18):
            self.assertGreater(e.use_move_on(a, b, CHAIN, e.everyone, **options), 0)
        self.assertEqual((a.move_uses[CHAIN], len(self.pool(a)['decisions']), B.remaining(self.pool(a))),
                         (1, 1, 1))
        self.restored(e)


if __name__ == '__main__':
    unittest.main()
