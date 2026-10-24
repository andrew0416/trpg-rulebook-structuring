"""Real cooked type-berry consumers: pre-RNG refusal and one actual hit plan."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import test_temporary_hp_composition as BASE
import book_chef_fixture as FIX
import chef_cooking as CHEF
import coat_effects as COATS
import custom_condition_effects as CUSTOM
import food_effects as FOOD
import frequency as FREQUENCY
import roll_effects as ROLLS
import temporary_hp as TEMP
import trainer_feature_acquisition as ACQUIRE
import type_ace as TA


class TemporaryHPBerryPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    setUp = BASE.TemporaryHPCompositionTests.setUp
    world = BASE.TemporaryHPCompositionTests.world
    choice = BASE.TemporaryHPCompositionTests.choice
    buy = BASE.TemporaryHPCompositionTests.buy
    salty = BASE.TemporaryHPCompositionTests.salty
    rows = BASE.TemporaryHPCompositionTests.rows
    unset_lifetime_default = BASE.TemporaryHPCompositionTests.unset_lifetime_default

    def ready_berry(self, *, composite=False, origin='item/카리열매', incoming=False):
        engine, chef, actor, foe = self.world(feats=FIX.ALL_FEATURES, stored_foods=True)
        batch = FIX.cook(engine, chef, recipe='preserves', origin=origin, taste='짠맛')
        if composite:
            batch = FIX.cook(engine, chef, recipe='dumplings',
                ingredient_1={'batch_id': batch['batch_id']},
                ingredient_2={'item': 'item/먹다남은음식'}, taste='짠맛')
        if incoming:
            food = FIX.cook(engine, chef, recipe='tasty_snack', snack='짠맛 서프라이즈')
        berry = FIX.serve(engine, chef, batch['batch_id'], actor)['buff_id']
        if incoming:
            food = FIX.serve(engine, chef, food['batch_id'], actor)['buff_id']
        # Cook and serve before granting the source; no fabricated receipts or buffs.
        original = self.salty(engine, chef, actor, foe, cooked=False)
        self.assertEqual(actor.temp_hp, 10)
        FIX.decline_all(engine, chef)
        engine.consume_food_buff(actor, buff_id=berry)
        if incoming:
            engine.consume_food_buff(actor, buff_id=food)
        engine.advance_time(40)
        return engine, chef, actor, foe, berry, original

    def reject(self, engine, actor, foe, move, pattern):
        with patch.object(Engine, 'roll_expr', autospec=True, side_effect=Engine.roll_expr) as dice, \
                patch.object(TEMP, 'food_source', side_effect=AssertionError('preflight minted source rights')):
            assert_rejected_unchanged(engine,
                lambda: engine.roll_damage(foe, actor, move), reason_pattern=pattern)
        dice.assert_not_called()

    def acquire_true_steel(self, engine, chef, actor, foe):
        skill = TA.SKILLS['강철'][0]
        chef.spec.setdefault('type_link_skills', {})['강철'] = skill
        engine.gm.set_skill(chef, skill, 6, reason='observed Master Steel type-link skill')
        engine.gm.set_types(actor, ['강철', '물'], reason='actual dual-type owned defender')
        second = Combatant(self.rules, FIX.pokemon_spec(self.rules, chef, 'second Steel partner'))
        engine.gm.add_combatant(second, pos=(1, 1), side='party', reason='distinct actual owned Steel partner')
        engine.gm.set_types(second, ['강철'], reason='actual qualifying second Steel Pokemon')
        ACQUIRE.acquire_static(engine, chef, TA.CLASS, branch='강철',
            acquisition_request_id='berry/steel-class/' + chef.entity_id)
        for feature in ('Polished Shine', 'True Steel'):
            FIX.acquire(engine, chef, TA.uid(feature))
        engine.gm.set_move(foe, 'move/불꽃세례', reason='actual known attack for the Steel-only matchup')
        FIX.battle(engine, foe)

    def provider(self, engine, selected):
        calls = []
        original=type(engine.rulings).decide
        def decide(current,prompt):
            if prompt.get('type') == 'type_ace_choice' and prompt.get('feature') == TA.uid('True Steel'):
                calls.append(deepcopy(prompt))
                return selected
            return original(current,prompt)
        self.enterContext(patch.object(type(engine.rulings),'decide',decide))
        return calls

    def test_real_preserves_and_dumplings_missing_invalid_policy_reject_before_rng_and_receipt(self):
        self.unset_lifetime_default()
        for composite in (False, True):
            for mode in (None, 'invalid'):
                with self.subTest(composite=composite, mode=mode):
                    engine, chef, actor, foe, berry, original = self.ready_berry(composite=composite)
                    engine.rulings.answers = [r for r in engine.rulings.answers if r['key'] != 'temporary_hp_additive_lifetime']
                    if mode is not None:
                        self.choice(engine, 'additive_lifetime', mode)
                    self.reject(engine, actor, foe, self.rules.move('move/몸통박치기'),
                        'temporary HP additive_lifetime')
                    self.assertEqual(actor.spec['food_hit_choice']['buff_id'], berry)
                    self.assertEqual(FIX.receipt(actor), original)

    def test_actual_uncertain_outside_clock_rejects_before_rng_even_when_healing_is_blocked(self):
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                engine, chef, actor, foe, berry, original = self.ready_berry()
                engine.start_round([chef])
                engine.end_encounter()
                engine.advance_time(250)
                self.assertEqual([actor.custom_conditions[TEMP.STATE][key]
                    for key in ('minimum_seconds', 'maximum_seconds')], [0, 10])
                if blocked:
                    row = CUSTOM.definition(self.rules, 'move/회복봉인')
                    engine.apply_effect(foe, actor, row['raw'], nat=10, hit=True, dealt=0, src='move/회복봉인')
                    self.assertEqual(TEMP.blocked_reason(actor), 'healing_block')
                self.reject(engine, actor, foe, self.rules.move('move/몸통박치기'),
                    'temporary HP expiry needs the unresolved grant/elapsed timestamp')

    def test_nonmatching_type_and_not_super_effective_hit_keep_berry_armed_without_policy(self):
        self.unset_lifetime_default()
        for origin in ('item/카리열매', 'item/오카열매'):
            with self.subTest(origin=origin):
                engine, chef, actor, foe, berry, original = self.ready_berry(origin=origin)
                before = deepcopy(actor.custom_conditions[TEMP.STATE])
                move = self.rules.move('move/불꽃세례')
                engine.gm.set_move(foe, move['id'], reason='actual known Fire attack')
                engine.roll_damage(foe, actor, move, set_damage=True)
                self.assertEqual(actor.spec['food_hit_choice']['buff_id'], berry)
                self.assertEqual(FIX.receipt(actor), original)
                self.assertEqual(actor.custom_conditions[TEMP.STATE], before)
                self.assertTrue(engine.validate_state()['valid'])

    def test_berry_then_food_taste_uses_actual_receipts_and_both_explicit_lifetimes_after_restore(self):
        for mode, expected in ((None, 10), ('per_grant', 10), ('refresh_pool', 20)):
            with self.subTest(mode=mode):
                engine, chef, actor, foe, berry, original = self.ready_berry(incoming=True)
                if mode is not None:
                    self.choice(engine, 'additive_lifetime', mode)
                engine.roll_damage(foe, actor, self.rules.move('move/몸통박치기'), set_damage=True)
                first, second = actor.spec['food_consumption_receipts'][-2:]
                self.assertEqual((first['buff_id'], first['producer'], second['producer']),
                    (berry, 'actual_hit', 'actual_attack'))
                self.assertEqual(actor.temp_hp, 20)
                self.assertEqual([(row['source']['kind'], row['source']['receipt_sequence']) for row in self.rows(actor)],
                    [('food', original['sequence']), ('chef_taste', first['sequence']), ('chef_taste', second['sequence'])])
                FIX.decline_all(engine, chef)
                loaded, actors = FIX.restore(self.rules, engine)
                for current, target in ((engine, actor), (loaded, actors[actor.entity_id])):
                    current.advance_time(260)
                    self.assertEqual(target.temp_hp, expected)
                    self.assertTrue(current.validate_state()['valid'])

    def test_true_steel_enables_berry_and_null_policy_refuses_before_rng_without_payment(self):
        self.unset_lifetime_default()
        engine, chef, actor, foe, berry, original = self.ready_berry(origin='item/오카열매')
        self.acquire_true_steel(engine, chef, actor, foe)
        calls = self.provider(engine, True)
        move = self.rules.move('move/불꽃세례')
        self.assertEqual(engine.type_multiplier(move['type'], actor)[0], 1)
        self.reject(engine, actor, foe, move, 'temporary HP additive_lifetime')
        self.assertEqual(len(calls), 1)
        self.assertEqual(actor.spec['food_hit_choice']['buff_id'], berry)

    def test_true_steel_decision_is_used_once_for_declined_and_accepted_berry_hits(self):
        self.unset_lifetime_default()
        for selected in (False, True):
            with self.subTest(selected=selected):
                engine, chef, actor, foe, berry, original = self.ready_berry(origin='item/오카열매')
                self.acquire_true_steel(engine, chef, actor, foe)
                if selected:
                    self.choice(engine, 'additive_lifetime', 'per_grant')
                calls = self.provider(engine, selected)
                feature = TA.uid('True Steel')
                before = FREQUENCY.state(chef)['activations'].get(feature, {}).get('used', 0)
                engine.roll_damage(foe, actor, self.rules.move('move/불꽃세례'), set_damage=True)
                self.assertEqual(len(calls), 1)
                self.assertEqual(FREQUENCY.state(chef)['activations'].get(feature, {}).get('used', 0),
                    before + int(selected))
                self.assertEqual(actor.temp_hp, 15 if selected else 10)
                self.assertEqual(any(buff['id'] == berry for buff in actor.buffs), not selected)
                self.assertTrue(engine.validate_state()['valid'])

    def test_native_coat_and_helping_hand_keep_single_consumption_on_the_composed_hit(self):
        engine, chef, actor, foe, berry, original = self.ready_berry(origin='item/오카열매')
        self.choice(engine, 'additive_lifetime', 'per_grant')
        FIX.battle(engine, foe)
        coat = COATS.definition(self.rules, 'move/타르샷')['raw']
        engine.apply_effect(foe, actor, coat, nat=10, hit=True, dealt=0, src='move/타르샷')
        coat_id = COATS.live(actor)[0]['id']
        roll = ROLLS.definition(self.rules, 'move/도우미')['raw']
        engine.apply_effect(chef, foe, roll, nat=10, hit=True, dealt=0, src='move/도우미')
        roll_id = ROLLS.live(foe)[0]['id']
        move_id = 'move/타오르는분노'
        engine.gm.set_move(foe, move_id, reason='actual known alternate-type attack against Tar Shot')
        engine.gm.choose_alternate_move_type(foe, move_id, '불꽃', reason='actual selected Fire mode')
        with patch.object(Engine, 'd20', return_value=10):
            engine.use_move_on(foe, actor, move_id, engine.everyone, set_damage=True)
        history = [row for row in actor.spec[COATS.HISTORY] if row['id'] == coat_id]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['effect_instance']['end_event']['move_type'], '불꽃')
        used = [row for row in ROLLS.closed(foe) if row['id'] == roll_id]
        self.assertEqual(len(used), 1)
        self.assertEqual([event['component'] for event in used[0]['applications']], ['accuracy', 'damage'])
        receipts = [row for row in actor.spec['food_consumption_receipts'] if row['buff_id'] == berry]
        self.assertEqual(len(receipts), 1)
        self.assertEqual((receipts[0]['producer'], receipts[0]['taste_bonus']['gained']), ('actual_hit', 5))
        self.assertEqual(receipts[0]['benefit']['move_type'], '불꽃')
        self.assertEqual(self.rules.move(move_id)['type'], '악')
        self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
