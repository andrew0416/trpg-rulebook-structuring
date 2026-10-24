"""C07-183 denominator repairs through native actions; historical receipts stay observations."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
import test_category2_native_move_batches as MOVES
import test_book_type_ace_passives as PASSIVES
import test_category2_coat_effects as COAT_FIX
from engine import Engine, Combatant
from builder import build_pokemon
from native_scenario_fixture import prepare_body
import coat_effects as COATS
import condition_instances as CONDITIONS
import effect_instances as INSTANCES
import effects as FX
import field_effects as FIELD
import frequency as FREQ
import movement_actions as MOVEMENT
import optional_move_modes as OPTIONAL
import turn as TURN
import type_ace as ACE


class NativeRealMaximumTests(unittest.TestCase):
    initial_moves = ['move/꽃가루경단', 'move/그래스필드', 'move/씨뿌리기', 'move/압정뿌리기']
    setUpClass = classmethod(MOVES.NativeMoveBatchTests.setUpClass.__func__)
    setUp = MOVES.NativeMoveBatchTests.setUp
    turn = MOVES.NativeMoveBatchTests.turn
    restore = MOVES.NativeMoveBatchTests.restore

    def hundred(self, actor, hp=10, injuries=3):
        self.e.gm.set_level(actor, 30, reason='actual level for real maximum 100')
        self.e.gm.set_stat(actor, 'hp', value=20, reason='actual HP Stat for real maximum 100')
        self.e.gm.set_injuries(actor, injuries, reason='observed prior injuries')
        self.e.gm.set_hp(actor, value=hp, reason='observed current real HP')
        self.assertEqual((actor.base_max_hp, actor.max_hp), (100, 100-injuries*10))

    def roundtrip(self):
        ids = self.p.entity_id, self.t.entity_id
        self.e.__dict__.pop('d20', None)
        self.e.gm.snapshot('real-max')
        self.e.gm.restore('real-max', reason='restore distinct real maximum and healing ceiling')
        self.e = self.restore()
        self.p, self.t = [next(a for a in self.e.everyone if a.entity_id == uid) for uid in ids]
        self.assertTrue(self.e.validate_state()['valid'])

    def ally(self):
        actor = Combatant(self.r, build_pokemon(self.r, '꼬부기', 30,
            moves=['move/몸통박치기'], abilities=[], side=self.p.side))
        self.e.gm.add_combatant(actor, pos=(10, 11), reason='actual allied healing recipient')
        return actor

    def test_pollen_native_half_request_caps_at_injury_ceiling_and_keeps_choice_receipt(self):
        for hp, expected in ((10, 60), (60, 70), (85, 85)):
            with self.subTest(hp=hp):
                self.setUp()
                ally = self.ally()
                self.hundred(ally, hp)
                self.e.gm.choose_optional_move_effect(self.p, 'move/꽃가루경단', reason='actual allied healing choice')
                self.assertEqual(self.e.use_move_on(self.p, ally, 'move/꽃가루경단', self.e.everyone), 0)
                self.assertEqual(ally.hp, expected)
                receipt = deepcopy(OPTIONAL.history(self.p))
                self.assertEqual(receipt[0]['use']['boundary'], 'activation')
                self.assertEqual(receipt[0]['use']['target_ids'], [ally.entity_id])
                self.assertEqual(self.p.budget['standard'], 0)
                loaded = self.restore()
                holder = next(a for a in loaded.everyone if a.entity_id == self.p.entity_id)
                self.assertEqual(OPTIONAL.history(holder), receipt)
                self.assertTrue(loaded.validate_state()['valid'])

    def test_pending_pollen_choice_survives_both_restores_and_generic_ceiling_expression_is_unchanged(self):
        ally = self.ally()
        self.hundred(ally)
        self.e.gm.choose_optional_move_effect(self.p, 'move/꽃가루경단', reason='pending old-compatible choice')
        receipt = deepcopy(OPTIONAL.history(self.p))
        uid = ally.entity_id
        self.roundtrip()
        ally = next(a for a in self.e.everyone if a.entity_id == uid)
        self.assertEqual(OPTIONAL.history(self.p), receipt)
        context = {'attacker': self.p}
        self.assertEqual(FX._amount('current_max_hp/2', ally, self.e, context), 35)
        self.assertEqual(FX._amount('current_hp/2', ally, self.e, context), 5)
        with patch.object(Engine, 'd20', return_value=17):
            self.e.use_move_on(self.p, ally, 'move/꽃가루경단', self.e.everyone)
        self.assertEqual(ally.hp, 60)

    def test_native_grass_turn_requests_real_tick_ground_contact_and_heal_cap(self):
        self.hundred(self.t, 10)
        self.e.use_move_on(self.p, self.p, 'move/그래스필드', self.e.everyone)
        self.assertEqual(self.e.field['source_id'], 'move/그래스필드')
        self.roundtrip()
        self.turn(self.t)
        self.assertEqual(self.t.hp, 20)
        self.e.gm.set_hp(self.t, value=65, reason='below injured recovery ceiling')
        self.turn(self.t, new_round=True)
        self.assertEqual(self.t.hp, 70)
        self.t.airborne = True
        self.e.gm.set_hp(self.t, value=10, reason='airborne recipient below ceiling')
        self.turn(self.t, new_round=True)
        self.assertEqual(self.t.hp, 10)

    def test_seed_real_tick_preserves_temp_hp_net_loss_caster_cap_and_receipts(self):
        for temporary, hp_lost, caster_hp in ((0, 10, 70), (6, 4, 69), (20, 0, 65)):
            with self.subTest(temporary=temporary):
                self.setUp()
                self.hundred(self.p, 65)
                self.hundred(self.t, 60)
                self.e.use_move_on(self.p, self.t, 'move/씨뿌리기', self.e.everyone)
                if temporary:
                    self.e.gm.set_temp_hp(self.t, temporary, reason='actual sourced temporary HP', duration_seconds=300)
                self.roundtrip()
                self.turn(self.t)
                event = CONDITIONS.records(self.t, '씨뿌리기')[0]['applications'][-1]
                self.assertEqual((event['maximum_hp'], event['requested'], event['lost']), (100, 10, hp_lost))
                self.assertEqual((self.t.hp, self.t.temp_hp, self.p.hp),
                                 (60-hp_lost, max(0, temporary-10), caster_hp))
                self.roundtrip()
                self.assertEqual(CONDITIONS.records(self.t, '씨뿌리기')[0]['applications'][-1], event)

    def test_seed_legacy_application_is_preserved_then_future_turn_uses_actual_maximum(self):
        self.hundred(self.p, 10)
        self.hundred(self.t, 60)
        self.e.use_move_on(self.p, self.t, 'move/씨뿌리기', self.e.everyone)
        self.turn(self.t)
        record = CONDITIONS.records(self.t, '씨뿌리기')[0]
        # A valid pre-repair observation is evidence of past arithmetic, not a current-stat formula.
        record['applications'][0].update(maximum_hp=70, requested=7, lost=7)
        old = deepcopy(record['applications'][0])
        self.roundtrip()
        self.turn(self.t, new_round=True)
        apps = CONDITIONS.records(self.t, '씨뿌리기')[0]['applications']
        self.assertEqual(apps[0], old)
        self.assertEqual((apps[1]['maximum_hp'], apps[1]['requested']), (100, 10))
        self.e.gm.recall(self.t, reason='actual target returned to its ball')
        closed = self.t.spec['effect_instance_history'][-1]
        self.assertEqual(closed['applications'][0], old)
        self.assertTrue(self.restore().validate_state()['valid'])

    def test_native_spikes_paid_ground_entry_real_tick_and_temporary_hp(self):
        cells = [(12, 10), (12, 11), (12, 12), (13, 10), (13, 11), (13, 12), (14, 10), (14, 11)]
        self.hundred(self.t, 60)
        for actor in (self.p, self.t):
            prepare_body(self.e, actor, size=actor.spec['size'], offsets=[(0, 0)], reason='observed body for actual path entry')
        self.e.use_move_on(self.p, self.p, 'move/압정뿌리기', self.e.everyone, aim=cells)
        self.assertEqual(self.p.budget['standard'], 0)
        self.e.gm.set_temp_hp(self.t, 6, reason='actual entry buffer', duration_seconds=300)
        self.roundtrip()
        self.turn(self.t)
        self.assertTrue(TURN.spend(self.e, self.t, 'shift', 'actual ground entry', movement=True))
        MOVEMENT.follow_paid_path(self.e, self.t, [(11, 10), (12, 10)], mode='land',
                                 maximum_distance=MOVEMENT.distance_budget(self.e, self.t, 'land'))
        self.assertEqual((self.t.pos, self.t.hp, self.t.temp_hp), ((12, 10), 56, 0))
        self.assertIn('둔화', self.t.conditions)
        self.assertTrue(self.restore().validate_state()['valid'])


    def test_native_local_grass_uses_same_real_tick_without_changing_local_lifetime(self):
        self.hundred(self.t, 10)
        for actor in (self.p, self.t):
            prepare_body(self.e, actor, size=actor.spec['size'], offsets=[(0, 0)], reason='actual mapped local field bodies')
        self.e.gm.set_ability(self.p, '곰팡이군주', True, reason='actual local Grass producer')
        row = self.e.activate_ability(self.p, FIELD.LOCAL_SOURCE, self.p, request_id='real-max/local-grass')
        self.assertEqual((row['source_id'], row['creator_id']), (FIELD.LOCAL_SOURCE, self.p.entity_id))
        self.assertEqual(self.p.budget['shift'], 0)
        self.assertIsNone(self.e.field)
        self.roundtrip()
        self.turn(self.t)
        self.assertEqual(self.t.hp, 20)
        self.assertEqual(FIELD.terrain_for(self.e, self.t)['source_id'], FIELD.LOCAL_SOURCE)
        self.e.end_encounter(round_elapsed_seconds=0)
        self.assertIsNotNone(FIELD.terrain_for(self.e, self.t))
        self.e.end_scene()
        self.assertIsNone(FIELD.terrain_for(self.e, self.t))


class TypeAceRealMaximumTests(unittest.TestCase):
    setUpClass = classmethod(PASSIVES.TypeAcePassiveTests.setUpClass.__func__)
    setUp = PASSIVES.TypeAcePassiveTests.setUp
    setup = PASSIVES.TypeAcePassiveTests.setup
    add = PASSIVES.TypeAcePassiveTests.add
    acquire = PASSIVES.TypeAcePassiveTests.acquire
    teach = PASSIVES.TypeAcePassiveTests.teach
    combat = PASSIVES.TypeAcePassiveTests.combat
    next_turn = PASSIVES.TypeAcePassiveTests.next_turn
    communication = PASSIVES.TypeAcePassiveTests.communication
    rejected = PASSIVES.TypeAcePassiveTests.rejected
    restore = PASSIVES.TypeAcePassiveTests.restore
    valid = PASSIVES.TypeAcePassiveTests.valid
    family = PASSIVES.TypeAcePassiveTests.family
    damage = PASSIVES.TypeAcePassiveTests.damage
    attack = PASSIVES.TypeAcePassiveTests.attack
    suppress = PASSIVES.TypeAcePassiveTests.suppress

    def third_hp(self, *, below):
        PASSIVES.TypeAcePassiveTests.third_hp(self, below=below)
        self.e.gm.set_injuries(self.p, 3, reason='same real threshold despite three injuries')
        self.e.gm.set_temp_hp(self.p, 2000, reason='temporary HP is excluded from HP fractions', duration_seconds=300)
        self.assertEqual(self.p.hp, self.p.base_max_hp//3-int(below))

    def test_injured_last_chance_exact_third_below_and_native_source_suppression(self):
        PASSIVES.TypeAcePassiveTests.test_last_chance_native_formula_uses_five_at_exact_third_ten_below_and_actual_suppression(self)

    def test_injured_strategist_exact_third_below_source_suppression_and_restore(self):
        PASSIVES.TypeAcePassiveTests.test_strategist_actual_typed_move_uses_hp_boundary_and_suppression_removes_live_dr(self)

    def test_blackout_native_hit_injury_order_inclusive_quarter_and_scene_cost(self):
        for prior, offset, fainted in ((0, 0, True), (1, 0, True), (1, -1, True), (1, 1, False), (2, 1, True)):
            with self.subTest(prior_injuries=prior, quarter_offset=offset):
                self.setup()
                self.family('악', 'Clever Ruse', 'Black-Out Strike')
                self.e.gm.set_position(self.p, (3, 2), reason='actual adjacent Dark attack')
                self.e.gm.set_move(self.p, 'move/물기', reason='actual known Dark attack')
                self.e.gm.set_injuries(self.b, prior, reason='observed prior injury count')
                self.combat(self.p)
                self.attack(self.p, self.b, 'move/물기')
                self.assertEqual(self.b.base_max_hp % 4, 0)
                self.e.gm.set_hp(self.b, value=self.b.base_max_hp//4+offset,
                                 reason='actual HP at reaction boundary after the native hit')
                self.e.gm.set_temp_hp(self.b, 2000, reason='temporary HP cannot change the quarter threshold', duration_seconds=300)
                completion = next(row for row in reversed(list(self.e._move_completions.values()))
                                  if row['actor'] is self.p and row['phase'] == 'complete')
                feature = ACE.uid('Black-Out Strike')
                ACE.react(self.e, self.t, self.p, feature, completion['id'])
                self.assertEqual(self.b.injuries, prior+1)
                self.assertEqual(self.b.fainted, fainted)
                if not fainted:
                    self.assertIn('잠듦', self.b.conditions)
                self.assertFalse(FREQ.activation_allowed(self.t, feature+':scene', {'kind':'scene', 'uses':1}, engine=self.e))
                self.assertTrue(FREQ.activation_allowed(self.t, feature, {'kind':'daily', 'uses':3}, engine=self.e))
                self.assertFalse(FREQ.activation_allowed(self.t, feature, {'kind':'daily', 'uses':1}, engine=self.e))
                self.restore()
                self.valid()


class IngrainLegacyMaximumTests(unittest.TestCase):
    setUpClass = classmethod(COAT_FIX.CoatEffectTests.setUpClass.__func__)
    setUp = COAT_FIX.CoatEffectTests.setUp
    known = COAT_FIX.CoatEffectTests.known
    restored = COAT_FIX.CoatEffectTests.restored
    add = COAT_FIX.CoatEffectTests.add
    snap = COAT_FIX.CoatEffectTests.snap
    valid = COAT_FIX.CoatEffectTests.valid
    begin = COAT_FIX.CoatEffectTests.begin
    next_turn = COAT_FIX.CoatEffectTests.next_turn
    cast = COAT_FIX.CoatEffectTests.cast

    def test_legacy_ingrain_payload_and_past_heals_restore_then_use_real_tick(self):
        self.known(self.p, '뿌리박기')
        self.begin(self.p)
        self.cast(self.p, '뿌리박기')
        self.e.gm.set_level(self.p, 30, reason='actual real maximum fixture')
        self.e.gm.set_stat(self.p, 'hp', value=20, reason='actual real maximum fixture')
        self.e.gm.set_injuries(self.p, 3, reason='three prior injuries')
        self.e.gm.set_hp(self.p, value=10, reason='low real HP')
        self.next_turn(self.p)
        record = COATS.live(self.p)[0]
        self.assertEqual((record['applications'][0]['basis'], record['applications'][0]['requested']), (100, 10))
        record['effect']['healing_basis'] = 'current_max_hp'
        record['applications'][0].update(basis=70, requested=7, hp_before=10, hp_after=17, healed=7)
        old = deepcopy(record)
        self.e.gm.snapshot('legacy-coat')
        self.e.gm.restore('legacy-coat', reason='load genuine pre-repair payload shape')
        self.assertEqual(COATS.live(self.p)[0], old)
        self.e = self.restored()
        self.p = next(a for a in self.e.everyone if a.entity_id == self.p.entity_id)
        self.assertEqual(COATS.live(self.p)[0], old)
        before = self.p.hp
        self.next_turn(self.p)
        record = COATS.live(self.p)[0]
        self.assertEqual(record['effect'], old['effect'])
        self.assertEqual(record['applications'][0], old['applications'][0])
        self.assertEqual((record['applications'][1]['basis'], record['applications'][1]['requested']), (100, 10))
        self.assertEqual(self.p.hp, before+10)
        self.assertTrue(COATS.blocks_displacement(self.e, self.p))
        self.valid()
        self.known(self.p, '안개제거')
        self.e.use_move(self.p, self.p, 'move/안개제거')
        history = next(r for r in self.p.spec[COATS.HISTORY] if r['id'] == old['id'])
        self.assertEqual(history['effect'], old['effect'])
        self.assertEqual(history['applications'][0], old['applications'][0])
        self.assertTrue(self.restored().validate_state()['valid'])

    def test_legacy_acceptance_is_specific_and_does_not_accept_other_payload_tampering(self):
        self.known(self.p, '아쿠아링', '뿌리박기')
        self.begin(self.p)
        self.cast(self.p, '아쿠아링')
        self.next_turn(self.p)
        self.cast(self.p, '뿌리박기')
        for source, field, value in (('move/아쿠아링', 'healing_basis', 'current_max_hp'),
                                     ('move/뿌리박기', 'denominator', 5),
                                     ('move/뿌리박기', 'blocks_push_pull', False)):
            record = next(r for r in COATS.live(self.p) if r['source'] == source)
            payload = deepcopy(record['effect'])
            record['effect'][field] = value
            before = self.snap()
            with self.assertRaisesRegex(ValueError, 'payload'):
                self.e.start_of_turn(self.p, initiative_count=20)
            self.assertEqual(self.snap(), before)
            record['effect'] = payload
        self.valid()
    def test_legacy_ingrain_baton_pass_preserves_identity_and_uses_receiving_holder_real_maximum(self):
        self.known(self.p, '뿌리박기', '배턴터치')
        self.begin(self.p)
        self.cast(self.p, '뿌리박기')
        record = COATS.live(self.p)[0]
        record['effect']['healing_basis'] = 'current_max_hp'
        uid = record['id']
        self.other.on_field = False
        COATS.select_transfer(self.e, self.p, self.other, reason='actual selected reserve under the same trainer')
        self.next_turn(self.p)
        self.e.use_move(self.p, self.p, COATS.BATON)
        self.assertFalse(COATS.live(self.p))
        moved = COATS.live(self.other)[0]
        self.assertEqual(moved['id'], uid)
        self.assertEqual(moved['effect']['healing_basis'], 'current_max_hp')
        self.assertEqual(moved[INSTANCES.KEY]['ownership'][-1]['source'], COATS.BATON)
        self.e.gm.set_injuries(self.other, 3, reason='actual injured replacement')
        self.e.gm.set_hp(self.other, value=1, reason='actual low replacement HP')
        self.e.end_of_turn(self.p)
        self.begin(self.other)
        self.assertEqual(self.other.hp, min(self.other.max_hp, 1+self.other.base_max_hp//10))
        self.assertEqual(moved['applications'][-1]['basis'], self.other.base_max_hp)
        self.assertTrue(self.restored().validate_state()['valid'])
