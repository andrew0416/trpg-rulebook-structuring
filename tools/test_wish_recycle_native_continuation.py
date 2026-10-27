"""Real paid waits, printed Warper responses, and their native receipt boundaries."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_csv_recycle_wish_helping as BASE
import test_book_warper_full as WARPER_FIXTURE
import consumption_execution as PAYMENTS
import native_scenario_fixture as NATIVE
import move_completion as COMPLETE
import passive_events as PASSIVE
import state_codec as CODEC
import wish_move as WISH
import recycle_move as RECYCLE
import warper as WARPER
import world_entities as WORLD


class NativeContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.CsvReuseWishTests.setUpClass()
        cls.r = BASE.CsvReuseWishTests.r

    setUp = BASE.CsvReuseWishTests.setUp
    add = BASE.CsvReuseWishTests.add
    begin = BASE.CsvReuseWishTests.begin
    next_round = BASE.CsvReuseWishTests.next_round
    medicine = BASE.CsvReuseWishTests.medicine

    def wait_listener(self, actor):
        # The existing external-policy fixture's selected Struggle source is a
        # no-op observation listener, not a forged Wish/Recycle implementation.
        source = self.e.r.selection.units['combat/struggle']['source']['file']
        document = {'schema': 1, 'id': 'event/native-source-choice-wait', 'variants': [{
            'rule_id': 'combat/struggle',
            'source': {'file': 'input/' + source,
                       'sha256': sha256((ROOT / 'input' / source).read_bytes()).hexdigest()},
            'inputs': {'hit': {'authority': 'context', 'type': 'boolean', 'question': 'Native hit'},
                       'decision': {'authority': 'gm', 'type': 'boolean', 'question': 'Resume?'}},
            'when': {'op': 'eq', 'left': {'$input': 'hit'}, 'right': True},
            'values': {'effects': [{'type': 'stage_change', 'stat': 'atk', 'delta': 0,
                                   'target': 'self'}]}}]}
        return self.e.subscribe_source_policy(actor, 'native-source-choice-wait', document,
            event='accuracy_resolved', inputs={'hit': 'hit'})

    def restore(self):
        ids = [actor.entity_id for actor in (self.a, self.p, self.t, self.q)]
        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e))))
        self.a, self.p, self.t, self.q = [WORLD.actor_index(self.e)[identity] for identity in ids]

    def resume(self, actor, event_id, listener):
        return self.e.choose_passive_event(event_id, actor, listener,
            {'decisions': {'decision': {'value': True, 'reason': 'actual observed reaction finished'}}})

    def test_csv_wish_paid_accuracy_wait_cold_resume_keeps_source_clock_and_heal_once(self):
        self.e.gm.set_injuries(self.t, 2, reason='actual lower current maximum')
        self.e.lose_hp(self.t, self.t.hp - 1, source='actual prior damage')
        before_hp = self.t.hp
        self.begin(self.p)
        listener = self.wait_listener(self.p)
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.p, self.t, WISH.SOURCE, wish_edition='csv-row623')
        event_id = self.e._passive_pending
        self.assertEqual(self.p.budget['standard'], 0)
        self.assertEqual(self.p.move_uses[WISH.SOURCE], 1)
        self.assertFalse(self.e.delayed)
        rng = self.e.rng.getstate()
        self.restore()
        self.resume(self.p, event_id, listener)
        self.assertEqual(self.e.rng.getstate(), rng)
        row = next(row for row in self.e.delayed if row.get('kind') == 'wish')
        self.assertEqual(row['edition'], 'csv-row623')
        self.assertIs(row['turn_owner'], self.t)
        self.assertIs(row['who'], self.t)
        self.assertEqual(self.p.budget['standard'], 0)
        self.assertEqual(self.p.move_uses[WISH.SOURCE], 1)
        before_replay = CODEC.dump_engine(self.e)
        self.assertEqual(self.e.deliver_passive_event(event_id), 'already_delivered')
        self.assertEqual(CODEC.dump_engine(self.e), before_replay)
        self.e.end_of_turn(self.p)
        self.assertEqual(self.t.hp, before_hp)
        self.next_round(self.t)
        self.e.end_of_turn(self.t)
        self.assertEqual(self.t.hp, min(self.t.max_hp, before_hp + self.t.max_hp // 2))
        self.assertFalse(any(row.get('kind') == 'wish' for row in self.e.delayed))
        self.assertTrue(self.e.validate_state()['valid'])

    def test_recycle_paid_wait_cold_resume_keeps_original_quantity_and_physical_consumption(self):
        for physical in (False, True):
            with self.subTest(physical=physical):
                if physical:self.setUp()
                self.e.gm.set_move(self.p, RECYCLE.SOURCE, reason='actually learned Recycle')
                self.e.lose_hp(self.p, 40, source='actual prior damage')
                self.begin(self.p)
                identity = self.medicine(self.p, physical=physical)
                self.e.end_of_turn(self.p)
                self.next_round(self.p)
                listener = self.wait_listener(self.p)
                before_hp = self.p.hp
                stock = deepcopy(self.p.spec['items'])
                paid = deepcopy(PAYMENTS.validate(self.p)[identity]['item_stock'])
                with self.assertRaises(PASSIVE.PassiveEventPending):
                    self.e.use_move(self.p, self.p, RECYCLE.SOURCE, recycle_receipt_id=identity)
                event_id = self.e._passive_pending
                self.assertEqual(self.p.hp, before_hp)
                self.assertEqual(self.p.budget['standard'], 0)
                self.assertEqual(self.p.move_uses[RECYCLE.SOURCE], 1)
                rng = self.e.rng.getstate()
                self.restore()
                self.resume(self.p, event_id, listener)
                receipt = PAYMENTS.validate(self.p)[identity]
                self.assertEqual(receipt['item_stock'], paid)
                self.assertEqual(self.p.spec['items'], stock)
                self.assertEqual(self.p.hp, min(self.p.max_hp, before_hp + 20))
                self.assertEqual(len(receipt['reuses']), 1)
                self.assertEqual(self.p.budget['standard'], 0)
                self.assertEqual(self.p.move_uses[RECYCLE.SOURCE], 1)
                self.assertEqual(self.e.rng.getstate(), rng)
                if physical:
                    self.assertIn('consumed', self.e._physical_objects['original-consumable'])
                    self.assertFalse(__import__('held_equipment').entries(self.p))
                before_replay = CODEC.dump_engine(self.e)
                self.assertEqual(self.e.deliver_passive_event(event_id), 'already_delivered')
                self.assertEqual(CODEC.dump_engine(self.e), before_replay)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_paid_continuation_selection_tamper_rejects_without_effect_or_another_cost(self):
        for source in (WISH.SOURCE, RECYCLE.SOURCE):
            with self.subTest(source=source):
                if source == RECYCLE.SOURCE:self.setUp()
                if source == RECYCLE.SOURCE:
                    self.e.gm.set_move(self.p, source, reason='actually learned Recycle')
                    self.e.lose_hp(self.p, 40, source='actual prior damage')
                    self.begin(self.p)
                    identity = self.medicine(self.p)
                    self.e.end_of_turn(self.p)
                    self.next_round(self.p)
                    target, options = self.p, {'recycle_receipt_id': identity}
                else:
                    self.begin(self.p)
                    target, options = self.t, {'wish_edition': 'csv-row623'}
                listener = self.wait_listener(self.p)
                with self.assertRaises(PASSIVE.PassiveEventPending):
                    self.e.use_move(self.p, target, source, **options)
                event_id = self.e._passive_pending
                self.restore()
                frame = self.e._passive_events[event_id]['continuation']
                original = deepcopy(frame['source_choices'])
                original_fingerprint = frame['fingerprint']
                completion_id = frame['args']['completion_id']
                choice = frame['source_choices']['wish' if source == WISH.SOURCE else 'recycle']
                choice['edition' if source == WISH.SOURCE else 'receipt_id'] = (
                    'ptu105' if source == WISH.SOURCE else 'replacement-receipt')
                NATIVE.assert_rejected_unchanged(self.e,
                    lambda: self.e.deliver_passive_event(event_id), reason_pattern='continuation changed')
                self.assertFalse(self.e.delayed)
                if source == RECYCLE.SOURCE:
                    self.assertFalse(PAYMENTS.validate(self.p)[identity].get('reuses'))
                from root_resolution import fingerprint
                for shape in ('legacy-missing', 'empty', 'null-selection'):
                    with self.subTest(compatibility=shape):
                        frame.pop('source_choices', None)
                        if shape == 'empty':frame['source_choices'] = {}
                        elif shape == 'null-selection':
                            frame['source_choices'] = {'wish' if source == WISH.SOURCE else 'recycle': None}
                        # Reproducing the old structural shape is not evidence
                        # of an edition or an original consumed-item selection.
                        frame['fingerprint'] = fingerprint(PASSIVE._continuation_facts(
                            self.e, self.e._passive_events[event_id], frame))
                        NATIVE.assert_rejected_unchanged(self.e,
                            lambda: self.e.deliver_passive_event(event_id),
                            reason_pattern='actual stored source choice')
                        self.assertEqual(frame['args']['completion_id'], completion_id)
                        self.assertEqual(self.p.move_uses[source], 1)
                        self.assertEqual(self.p.budget['standard'], 0)
                        self.assertFalse(self.e.delayed)
                        if source == RECYCLE.SOURCE:
                            self.assertFalse(PAYMENTS.validate(self.p)[identity].get('reuses'))
                frame['source_choices'] = original
                frame['fingerprint'] = original_fingerprint
                self.resume(self.p, event_id, listener)
                self.assertEqual(self.p.move_uses[source], 1)
                self.assertEqual(self.p.budget['standard'], 0)


class WarperWishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        WARPER_FIXTURE.WarperTests.setUpClass()
        cls.rules = WARPER_FIXTURE.WarperTests.rules

    setUp = WARPER_FIXTURE.WarperTests.setUp
    setup = WARPER_FIXTURE.WarperTests.setup
    add = WARPER_FIXTURE.WarperTests.add
    acquire = WARPER_FIXTURE.WarperTests.acquire
    family = WARPER_FIXTURE.WarperTests.family
    close = WARPER_FIXTURE.WarperTests.close
    begin = WARPER_FIXTURE.WarperTests.begin
    turn = WARPER_FIXTURE.WarperTests.turn
    restore = WARPER_FIXTURE.WarperTests.restore
    completion = WARPER_FIXTURE.WarperTests.completion
    valid = WARPER_FIXTURE.WarperTests.valid
    reject = WARPER_FIXTURE.WarperTests.reject

    def teach_wish(self):
        self.e.gm.set_move(self.b, WISH.SOURCE, reason='actually learned selected Wish')

    def test_magic_coat_actual_no_damage_wish_rebinds_both_selected_sources(self):
        for edition in WISH.EDITIONS:
            with self.subTest(edition=edition):
                if edition != WISH.EDITIONS[0]:self.setup()
                self.family(WARPER.ENERGY)
                self.teach_wish()
                self.e.gm.set_position(self.b, (4, 2), reason='both actual printed ranges')
                self.e.lose_hp(self.b, 40, source='actual earlier damage')
                self.begin()
                self.e.arm_warper_move(self.a, WARPER.COAT)
                self.turn(self.b)
                before_hp = self.b.hp
                if edition == 'csv-row623':
                    listener = NativeContinuationTests.wait_listener(self, self.b)
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        self.e.use_move(self.b, self.a, WISH.SOURCE, wish_edition=edition)
                    event_id = self.e._passive_pending
                    self.assertEqual(self.a.move_uses.get(WARPER.COAT, 0), 0)
                    self.assertFalse(self.e.delayed)
                    rng = self.e.rng.getstate()
                    self.restore()
                    actual_complete = PASSIVE.complete
                    def changed_accuracy(engine, identity, **observations):
                        if identity == event_id:observations['hit'] = False
                        return actual_complete(engine, identity, **observations)
                    with patch.object(PASSIVE, 'complete', new=changed_accuracy):
                        self.reject(lambda: NativeContinuationTests.resume(self, self.b, event_id, listener),
                            'completion disagrees with actual accuracy observation')
                    NativeContinuationTests.resume(self, self.b, event_id, listener)
                    self.assertEqual(self.e.rng.getstate(), rng)
                    accuracy = next(row['facts'] for row in PASSIVE.observations(self.e, event_id)
                                    if row['stage'] == 'accuracy')
                    self.assertIs(accuracy['hit'], True)
                    self.assertIs(self.e._passive_events[event_id]['hit'], True)
                    self.reject(lambda: COMPLETE.require_hit_return(self.e, event_id, self.a),
                                'actual successful nonprevented recipient hit required')
                    before_replay = CODEC.dump_engine(self.e)
                    self.assertEqual(self.e.deliver_passive_event(event_id), 'already_delivered')
                    self.assertEqual(CODEC.dump_engine(self.e), before_replay)
                else:
                    self.e.use_move(self.b, self.a, WISH.SOURCE, wish_edition=edition)
                self.assertEqual(self.a.move_uses[WARPER.COAT], 1)
                self.assertEqual(self.b.move_uses[WISH.SOURCE], 1)
                self.assertEqual(self.b.budget['standard'], 0)
                rows = [row for row in self.e.delayed if row.get('kind') == 'wish']
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row['edition'], edition)
                self.assertIs(row['issuer'], self.a)
                self.assertIs(row['who'], self.b)
                self.assertIs(row['turn_owner'], self.a if edition == 'ptu105' else self.b)
                parent = self.completion(self.b, WISH.SOURCE)
                self.assertFalse(parent['results'][self.a.entity_id]['hit'])
                proof = parent['warper_reflection']
                reflected = self.e._move_completions[proof['result_completion']]
                self.assertTrue(reflected['results'][self.b.entity_id]['hit'])
                self.assertEqual(row['completion_id'], proof['result_completion'])
                self.restore()
                self.valid()
                self.close()
                self.assertEqual(self.b.hp, before_hp)
                self.begin(self.a if edition == 'ptu105' else self.b)
                self.close()
                maximum = self.b.base_max_hp if edition == 'ptu105' else self.b.max_hp
                self.assertEqual(self.b.hp, min(self.b.max_hp, before_hp + maximum // 2))
                self.assertFalse(any(row.get('kind') == 'wish' for row in self.e.delayed))

    def test_actual_magic_coat_cannot_change_reflected_source_and_rolls_back_all_costs(self):
        self.family(WARPER.ENERGY)
        self.teach_wish()
        self.e.gm.set_position(self.b, (4, 2), reason='both actual printed ranges')
        self.begin()
        self.e.arm_warper_move(self.a, WARPER.COAT)
        self.turn(self.b)
        from engine import Engine
        original = Engine.use_move
        def change_child_source(engine, actor, target, move_id, *args, **options):
            if move_id == WISH.SOURCE and getattr(engine, '_warper_reflection', None) is not None:
                if boundary == 'edition':options['wish_edition'] = 'ptu105'
                else:target = WORLD.actor_index(engine)[self.c.entity_id]
            return original(engine, actor, target, move_id, *args, **options)
        for boundary in ('edition', 'uncertified-recipient'):
            with self.subTest(boundary=boundary):
                with patch.object(Engine, 'use_move', new=change_child_source):
                    self.reject(lambda: self.e.use_move(self.b, self.a, WISH.SOURCE,
                        wish_edition='csv-row623'), 'nested Wish|Magic Coat')
        self.assertEqual(self.a.move_uses.get(WARPER.COAT, 0), 0)
        self.assertEqual(self.b.move_uses.get(WISH.SOURCE, 0), 0)
        self.assertFalse(self.e.delayed)
        self.assertFalse(getattr(self.e, '_move_completions', {}))
        self.e.use_move(self.b, self.a, WISH.SOURCE, wish_edition='csv-row623')
        self.assertEqual(len([row for row in self.e.delayed if row.get('kind') == 'wish']), 1)

    def test_ally_switch_wish_binds_actual_recipient_receipt_through_restore_and_healing(self):
        for edition in WISH.EDITIONS:
            with self.subTest(edition=edition):
                if edition != WISH.EDITIONS[0]:self.setup()
                self.family(WARPER.SPACE)
                self.teach_wish()
                self.e.lose_hp(self.a, 40, source='actual earlier recipient damage')
                self.begin()
                self.e.arm_warper_move(self.a, WARPER.SWITCH, ally=self.c, willing=True)
                self.turn(self.b)
                before_hp = self.a.hp
                self.e.use_move(self.b, self.c, WISH.SOURCE, wish_edition=edition)
                row = next(row for row in self.e.delayed if row.get('kind') == 'wish')
                self.assertIs(row['original_target'], self.a)
                self.assertIs(row['who'], self.a)
                self.assertIs(row['turn_owner'], self.b if edition == 'ptu105' else self.a)
                completion = self.completion(self.b, WISH.SOURCE)
                self.assertNotIn(self.a, completion['targets'])
                received = completion['received'][self.a.entity_id]
                self.assertIn(row['dispatch_receipt'], received['effects'])
                self.assertEqual(row['recipient_token'],
                    (received['event_id'], self.c.entity_id, self.a.entity_id))
                self.restore()
                self.valid()
                self.close()
                self.assertEqual(self.a.hp, before_hp)
                self.begin(self.b if edition == 'ptu105' else self.a)
                self.close()
                maximum = self.a.base_max_hp if edition == 'ptu105' else self.a.max_hp
                self.assertEqual(self.a.hp, min(self.a.max_hp, before_hp + maximum // 2))
                self.assertFalse(any(row.get('kind') == 'wish' for row in self.e.delayed))

    def test_ally_switch_wish_recipient_or_effect_receipt_tamper_rolls_back_turn_end(self):
        self.family(WARPER.SPACE)
        self.teach_wish()
        self.begin()
        self.e.arm_warper_move(self.a, WARPER.SWITCH, ally=self.c, willing=True)
        self.turn(self.b)
        self.e.use_move(self.b, self.c, WISH.SOURCE)
        self.restore()
        row = next(row for row in self.e.delayed if row.get('kind') == 'wish')
        before = (self.a.hp, self.b.hp, deepcopy(self.b.budget), self.e.rng.getstate(),
                  self.b.custom_conditions['combat_turn_serial'], self.e._active_turn_actor)
        good = row['recipient_token']
        row['recipient_token'] = (good[0], good[1], self.c.entity_id)
        with self.assertRaises(ValueError):self.e.end_of_turn(self.b)
        self.assertEqual((self.a.hp, self.b.hp, self.b.budget, self.e.rng.getstate(),
            self.b.custom_conditions['combat_turn_serial'], self.e._active_turn_actor), before)
        with self.assertRaises(ValueError):self.e.gm.snapshot('tampered native recipient')
        row['recipient_token'] = good
        received = self.completion(self.b, WISH.SOURCE)['received'][self.a.entity_id]
        effects = received['effects']
        received['effects'] = []
        with self.assertRaises(ValueError):self.e.end_of_turn(self.b)
        self.assertEqual((self.a.hp, self.b.hp, self.b.budget, self.e.rng.getstate(),
            self.b.custom_conditions['combat_turn_serial'], self.e._active_turn_actor), before)
        with self.assertRaises(ValueError):self.e.gm.snapshot('missing actual received effects')
        received['effects'] = effects
        self.close()
        self.valid()


if __name__ == '__main__':
    unittest.main()
