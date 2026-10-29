"""Actual R663 hit/Swift producer and optional native Tera Blast consumers."""
from copy import deepcopy
from pathlib import Path
import json
import math
import random
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from builder import build_pokemon
from engine import Combatant, Engine, Rules
import combat_move_reactions as CMR
import effects_ext as EXT
import homebrew_state as HOME
import frequency as FREQUENCY
import passive_events as PE
import stellar_tera_blast as STELLAR
import world_entities as WORLD
from tools import test_category2_csv_stellar_tera_blast as BASE
from tools import test_actual_damage_type_revision as DAMAGE


class StellarR663OptionalSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='homebrew')

    def world(self, *, radiate=True, tera=None):
        fixture = BASE.StellarTeraBlastTests()
        fixture.rules = self.rules
        fixture.setUp()
        e, actor, target = fixture.engine, fixture.owner, fixture.foe
        # Repeated actual damage must not silently turn later uses into the
        # separate nonpositive-HP admission path. Defense/type stay unchanged.
        e.gm.set_stat(target,'hp',value=300,reason='multi-activation fixture HP headroom')
        e.gm.set_hp(target,value=target.base_max_hp,reason='multi-activation fixture starts healthy')
        if tera is not None:
            HOME.observe_type(e, actor, tera, reason='actual established ordinary Tera choice')
            HOME.observe_active(e, actor, True, reason='actual source-owned ordinary Terastal state')
        if radiate:
            fixture.radiate('불꽃')
        e.rng = random.Random(663)
        self.next_turn(e, actor)
        return e, actor, target

    def next_turn(self, e, actor):
        e.end_of_turn(actor)
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=20)

    def hit(self, e, actor, target, move_id, *, face=12, **options):
        with patch.object(Engine, 'd20', return_value=face):
            return e.use_move(actor, target, move_id, set_damage=True,
                              situational=100, **options)

    def last(self, e):
        return list(e._move_completions.values())[-1]

    def test_paid_native_accept_decline_and_main_variant_stab_use_one_frozen_type(self):
        for move_id, tera, choice, stab in (
                ('move/테라버스트', '물', True, True),
                ('move/테라버스트', None, None, False),
                ('move/테라버스트-물리', '풀', True, True),
                ('move/테라버스트-물리', '물', False, False),
                ('move/테라버스트-특수', None, True, False),
                ('move/테라버스트-특수', '물', None, False)):
            with self.subTest(move=move_id, tera=tera, choice=choice):
                e, actor, target = self.world(tera=tera)
                types = list(actor.types)
                history = deepcopy(actor.spec[STELLAR.STATE]['history'])
                before = (actor.budget['swift'], actor.move_uses.get(move_id, 0))
                move = STELLAR.prepare(e, actor, self.rules.move(move_id), choice)
                selected = 'atk' if move_id == 'move/테라버스트' else None
                move = EXT.prepare_versatile_move(e, move, selected)
                actual = '불꽃' if choice else tera or '노말'
                self.assertEqual(EXT.effective_type(e, actor, target, move,
                    self.rules.move_mech(move_id)[0], consume=False), actual)
                db = 8 + (math.floor(e.formula('stab')) if stab else 0)
                self.assertEqual(e.damage_base(actor, move, target=target), db)
                expected = DAMAGE.ActualDamageTypeRevisionTests().expected(
                    e, actor, target, move_id, db, bonus=10 if actual == '불꽃' else 0,
                    selected=selected)
                if tera == actual:
                    expected += 10
                expected = math.floor(expected * e.type_multiplier(actual, target)[0])
                options = {'versatile_stat': selected}
                if choice is not None:
                    options['use_radiated_type'] = choice
                self.assertEqual(self.hit(e, actor, target, move_id, **options), expected)
                receipt = self.last(e)['move'][STELLAR.CHOICE]
                self.assertEqual(receipt, move[STELLAR.CHOICE])
                self.assertEqual(receipt['use_radiated_type'], bool(choice))
                self.assertEqual((actor.budget['standard'], actor.budget['swift'],
                    actor.move_uses[move_id]), (0, before[0], before[1] + 1))
                self.assertEqual(actor.types, types)
                self.assertEqual(actor.spec[STELLAR.STATE]['history'], history)

    def test_actual_group_option_and_next_default_miss_pay_once_without_reusing_choice(self):
        e, actor, target = self.world()
        move_id = 'move/테라버스트-물리'
        history = deepcopy(actor.spec[STELLAR.STATE]['history'])
        uses = actor.move_uses.get(move_id, 0)
        swift = actor.budget['swift']
        with patch.object(Engine, 'd20', return_value=12):
            self.assertGreater(e.use_move_on(actor, target, move_id, e.everyone,
                set_damage=True, use_radiated_type=True), 0)
        first = self.last(e)
        self.assertTrue(first['move'][STELLAR.CHOICE]['use_radiated_type'])
        self.assertEqual(first['started'], [target.entity_id])
        self.assertEqual((actor.budget['standard'], actor.budget['swift'],
            actor.move_uses[move_id]), (0, swift, uses + 1))
        self.next_turn(e, actor)
        self.assertFalse(FREQUENCY.move_allowed(e, actor, move_id, outside_combat=False)[0])
        self.next_turn(e, actor)
        self.assertTrue(FREQUENCY.move_allowed(e, actor, move_id, outside_combat=False)[0])
        self.assertEqual(self.hit(e, actor, target, move_id, face=1), 0)
        second = self.last(e)
        self.assertFalse(second['move'][STELLAR.CHOICE]['use_radiated_type'])
        self.assertFalse(second['results'][target.entity_id]['hit'])
        self.assertEqual(actor.move_uses[move_id], uses + 2)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(actor.spec[STELLAR.STATE]['history'], history)

    def test_dormant_stellar_choice_has_no_bonus_but_actual_radiation_form_bonus_survives_decline(self):
        e, actor, target = self.world(radiate=False)
        HOME.observe_type(e, actor, '스텔라', reason='actual ability-backed permanent imitation choice')
        HOME.observe_type(e, target, '물', reason='actual target ordinary Tera choice')
        HOME.observe_active(e, target, True, reason='actual target transformed state')
        move_id = 'move/테라버스트-물리'
        expected = DAMAGE.ActualDamageTypeRevisionTests().expected(e, actor, target, move_id, 8)
        self.assertFalse(HOME.tera_active(actor))
        self.assertEqual(self.hit(e, actor, target, move_id), expected)
        self.assertIs(self.last(e)['move'][STELLAR.CHOICE], False)
        opportunity = actor.spec[STELLAR.STATE]['opportunities'][-1]
        e.gm.activate_stellar_blast(actor, opportunity['id'], '물', reason='actual hit chosen type')
        self.next_turn(e, actor)
        self.assertEqual(self.hit(e, actor, target, move_id, use_radiated_type=False),
                         math.floor(expected * 1.5))
        self.assertFalse(self.last(e)['move'][STELLAR.CHOICE]['use_radiated_type'])
        self.assertEqual(actor.types, ['풀', '독'])
        move = STELLAR.prepare(e, actor, self.rules.move(move_id), False)
        self.assertEqual(EXT.effectiveness_hook(e, actor, target, move,
            self.rules.move_mech(move_id)[0], 2.0, {}), 2.0)
        e.end_encounter(e.everyone)
        self.assertIsNone(STELLAR.active_radiation(e, actor))
        self.assertEqual(EXT.effectiveness_hook(e, actor, target, self.rules.move(move_id),
            self.rules.move_mech(move_id)[0], 1.0, {}), 1.0)

    def test_invalid_or_inapplicable_native_choices_refuse_before_rng_and_payment(self):
        for radiate, move_id, option in (
                (False, 'move/테라버스트-물리', True),
                (False, 'move/테라버스트-물리', False),
                (True, 'move/테라버스트-물리', 'yes'),
                (True, 'move/테라버스트-물리', 1),
                (True, 'move/몸통박치기', True)):
            with self.subTest(radiate=radiate, move=move_id, option=option):
                e, actor, target = self.world(radiate=radiate)
                before = deepcopy((actor.spec, actor.budget, actor.move_uses,
                    target.spec, target.hp, e.rng.getstate()))
                with self.assertRaises(ValueError):
                    e.use_move_on(actor, target, move_id, e.everyone,
                                  set_damage=True, use_radiated_type=option)
                self.assertEqual((actor.spec, actor.budget, actor.move_uses,
                    target.spec, target.hp, e.rng.getstate()), before)
        e, actor, target = self.world()
        actor.moves.remove('move/테라버스트-물리')
        before = deepcopy((actor.spec, actor.budget, actor.move_uses, e.rng.getstate()))
        with self.assertRaises(ValueError):
            self.hit(e, actor, target, 'move/테라버스트-물리', use_radiated_type=True)
        self.assertEqual((actor.spec, actor.budget, actor.move_uses, e.rng.getstate()), before)
        e, actor, target = self.world()
        e.end_encounter(e.everyone)
        before = deepcopy((actor.spec, actor.budget, e.rng.getstate()))
        with self.assertRaises(ValueError):
            e.use_move(actor, target, 'move/테라버스트-물리', use_radiated_type=True)
        self.assertEqual((actor.spec, actor.budget, e.rng.getstate()), before)

    def test_actual_paid_choice_history_and_new_default_survive_gm_and_fresh_rules_json(self):
        e, actor, target = self.world()
        move_id = 'move/테라버스트-특수'
        self.assertGreater(self.hit(e, actor, target, move_id, use_radiated_type=True), 0)
        completed = self.last(e)
        first_id = completed['id']
        recorded = deepcopy((completed['move'][STELLAR.CHOICE], completed['results']))
        radiation = deepcopy(actor.spec[STELLAR.STATE]['history'])
        self.next_turn(e, actor)
        e.gm.snapshot('optional Stellar use')
        e.gm.restore('optional Stellar use', reason='restore actual paid source history')
        actor_id, target_id = actor.entity_id, target.entity_id
        fresh = Rules(str(ROOT), ruleset='homebrew')
        e = Engine.import_state(fresh, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        actor, target = (WORLD.actor_index(e)[uid] for uid in (actor_id, target_id))
        self.assertEqual((e._move_completions[first_id]['move'][STELLAR.CHOICE],
            e._move_completions[first_id]['results']), recorded)
        self.assertEqual(actor.spec[STELLAR.STATE]['history'], radiation)
        self.assertGreater(target.hp, 0)
        self.assertFalse(target.fainted or target.captured or not target.on_field)
        self.assertIs(e._active_turn_actor, actor)
        self.assertEqual(FREQUENCY.move_frequency(e, move_id, actor)[0], 'every_other_turn')
        state = FREQUENCY.state(actor)
        previous_turn = state['moves'][move_id]['turn']
        self.assertEqual(state['turn'] - previous_turn, 1)
        allowed, reason = FREQUENCY.move_allowed(e, actor, move_id, outside_combat=False)
        self.assertFalse(allowed)
        self.assertIn('재사용 대기', reason)
        before = (target.hp, deepcopy(actor.budget), dict(actor.move_uses),
                  e.rng.getstate(), tuple(e._move_completions))
        self.assertEqual(self.hit(e, actor, target, move_id), 0)
        self.assertEqual((target.hp, actor.budget, actor.move_uses,
                          e.rng.getstate(), tuple(e._move_completions)), before)
        # The intervening owner turn must pass before this source permits reuse.
        self.next_turn(e, actor)
        self.assertEqual(FREQUENCY.state(actor)['turn'] - previous_turn, 2)
        self.assertTrue(FREQUENCY.move_allowed(e, actor, move_id, outside_combat=False)[0])
        self.assertGreater(target.hp, 0)
        self.assertGreater(self.hit(e, actor, target, move_id), 0)
        self.assertFalse(self.last(e)['move'][STELLAR.CHOICE]['use_radiated_type'])
        self.assertEqual((e._move_completions[first_id]['move'][STELLAR.CHOICE],
            e._move_completions[first_id]['results']), recorded)
        self.assertEqual(actor.spec[STELLAR.STATE]['history'], radiation)
        self.assertTrue(e.validate_state()['valid'], e.validate_state())

    def test_real_legacy_paid_accuracy_continuation_keeps_forced_projection_without_repayment(self):
        e, actor, target = self.world()
        move_id = 'move/테라버스트-물리'
        responder = Combatant(e.r, build_pokemon(e.r, '꼬렛', 20,
            name='actual known Quick Guard responder', side='party', pos=(9, 2),
            abilities=[], moves=[CMR.GUARD]))
        e.gm.add_combatant(responder)
        CMR.arm(e, responder, CMR.GUARD)
        # A real armed source enters resolved_move's normal native frame path.
        # It protects this responder, not the attacked foe, so no response fires.
        # Application test checkpoint only: choosing False executes no effect.
        # It creates a genuine paid accuracy boundary, not an R663 rule or receipt.
        key = PE.subscribe_policy(e, actor, 'legacy-r663-checkpoint', {
            'schema': 1, 'id': 'test-only-legacy-r663-checkpoint', 'variants': [{
                'rule_id': 'ability/스텔라버스트',
                'source': {'file': 'input/db/abilities.csv', 'sha256':
                    '87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},
                'values': {'effects': []}, 'when': {'$input': 'apply_test_effect'},
                'inputs': {'apply_test_effect': {'type': 'boolean', 'authority': 'gm',
                    'question': 'Test-only transport checkpoint; decline the effect'}}
            }]}, event='accuracy_resolved')
        uses = actor.move_uses.get(move_id, 0)
        hp = target.hp
        history = deepcopy(actor.spec[STELLAR.STATE]['history'])
        # Reproduce only the former unmarked catalog-preparation seam. Real
        # Engine payment, accuracy, native frame and continuation all run normally.
        with patch.object(STELLAR, 'prepare', side_effect=lambda e, a, m, *args, **kw: m):
            with self.assertRaises(PE.PassiveEventPending):
                self.hit(e, actor, target, move_id)
        event_id = e._passive_pending
        event = e._passive_events[event_id]
        row = self.last(e)
        completion_id = row['id']
        self.assertEqual(event['phase'], 'accuracy_boundary')
        self.assertEqual(row['started'], [target.entity_id])
        self.assertIs(row['native_action_frame']['actor'], actor)
        self.assertNotIn(STELLAR.CHOICE, row['move'])
        self.assertNotIn(STELLAR.CHOICE, event['continuation']['args']['move'])
        self.assertEqual((actor.budget['standard'], actor.move_uses[move_id], target.hp),
                         (0, uses + 1, hp))
        ordinary = self.rules.move(move_id)
        self.assertEqual(EXT.effective_type(e, actor, target, ordinary,
            self.rules.move_mech(move_id)[0], consume=False), '노말')
        original_move = deepcopy(row['move'], {id(c): c.entity_id for c in WORLD.actor_index(e).values()})
        rng = e.rng.getstate()
        e.gm.snapshot('actual legacy paid accuracy')
        e.gm.restore('actual legacy paid accuracy', reason='retain actual interrupted paid producer')
        actor_id, target_id = actor.entity_id, target.entity_id
        e = Engine.import_state(Rules(str(ROOT), ruleset='homebrew'),
            json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        actor, target = (WORLD.actor_index(e)[uid] for uid in (actor_id, target_id))
        expected = math.floor(DAMAGE.ActualDamageTypeRevisionTests().expected(
            e, actor, target, move_id, 8, bonus=10) * e.type_multiplier('불꽃', target)[0])
        PE.choose(e, event_id, actor, key, {'decisions': {'apply_test_effect': {
            'value': False, 'reason': 'complete only the test transport checkpoint'}}})
        row = e._move_completions[completion_id]
        self.assertEqual(row['results'][target.entity_id]['dealt'], expected)
        self.assertEqual(target.hp, hp - expected)
        self.assertEqual((actor.budget['standard'], actor.move_uses[move_id]), (0, uses + 1))
        self.assertEqual(e.rng.getstate(), rng)
        self.assertEqual(deepcopy(row['move'], {id(c): c.entity_id for c in WORLD.actor_index(e).values()}), original_move)
        self.assertEqual(actor.spec[STELLAR.STATE]['history'], history)
        self.assertIsNone(e._passive_pending)
        self.assertTrue(e.validate_state()['valid'], e.validate_state())


if __name__ == '__main__':
    unittest.main()
