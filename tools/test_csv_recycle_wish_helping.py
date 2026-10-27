"""Native source-selected Wish, consumed-item Recycle, and retained Helping Hand boundary."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import pokemon_party as PARTY
import state_codec as CODEC
import wish_move as WISH
import recycle_move as RECYCLE
import consumption_execution as PAYMENTS
import native_scenario_fixture as NATIVE


class CsvReuseWishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=623)
        self.e.grid = Grid(24, 8)
        self.a = self.add(build_trainer(self.r, 'Wish owner', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            skills={'명령': 4}, extra={'items': {}, 'edges': []}), (0, 0))
        self.p = self.add(build_pokemon(self.r, '이브이', 20, moves=[], abilities=[],
            extra={'id': 'pokemon/wisher', 'trainer_id': self.a.entity_id}), (2, 0))
        self.t = self.add(build_pokemon(self.r, '이브이', 20, moves=[], abilities=[],
            extra={'id': 'pokemon/target', 'trainer_id': self.a.entity_id}), (4, 0))
        self.q = self.add(build_pokemon(self.r, '이브이', 20, moves=[], abilities=[],
            extra={'id': 'pokemon/replacement', 'trainer_id': self.a.entity_id}), (6, 0))
        self.e.gm.recall(self.q, reason='actual reserve before combat')
        PARTY.configure(self.e, self.a, mode='standard', reason='actual party',
            roster=[self.p, self.t, self.q], storage={'kind': 'center', 'id': 'native-center'})
        self.e.configure_party_combat(self.a, battle_mode='full_contact', reason='native full contact')
        for actor in (self.p, self.t, self.q):
            self.e.gm.observe_loyalty(actor, 6, reason='actual obedient partner')
            self.e.gm.set_move(actor, WISH.SOURCE, reason='actually learned Wish')

    def add(self, sheet, position):
        actor = Combatant(self.r, sheet)
        self.e.gm.add_combatant(actor, pos=position, side='party', reason='actual actor')
        self.e.gm.set_footprint(actor, [(0, 0)], reason='actual one-cell body')
        return actor

    def begin(self, actor):
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor)

    def next_round(self, actor):
        self.e.end_round()
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor)

    def cast(self, actor, target, edition='ptu105'):
        result = self.e.use_move(actor, target, WISH.SOURCE, wish_edition=edition)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(actor.move_uses[WISH.SOURCE], 1)
        row = next(r for r in self.e.delayed if r.get('kind') == 'wish')
        self.assertEqual(row['edition'], edition)
        return row

    def restored(self):
        return CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e))))

    def test_wish_exact_source_selection_rejects_forged_or_unrelated_choices_before_cost(self):
        WISH.source(self.r)
        self.begin(self.p)
        NATIVE.assert_rejections_unchanged(self.e, [
            lambda: self.e.use_move(self.p, self.t, WISH.SOURCE, wish_edition='future'),
            lambda: self.e.use_move(self.p, self.t, 'struggle', wish_edition='ptu105')],
            reason_pattern=['exact Wish edition', 'exact Wish edition'])
        before = CODEC.dump_engine(self.e)
        for grouped in (False, True):
            with self.subTest(strict_native_arguments=grouped):
                with self.assertRaises(TypeError):
                    if grouped:
                        self.e.use_move_on(self.p, self.t, WISH.SOURCE, self.e.gm.everyone,
                            wish_edition='ptu105', recycle_receipt_id=None, unreviewed_source_choice=True)
                    else:
                        self.e.use_move(self.p, self.t, WISH.SOURCE,
                            wish_edition='ptu105', recycle_receipt_id=None, unreviewed_source_choice=True)
                self.assertEqual(CODEC.dump_engine(self.e), before)
        self.e.use_move_on(self.p, self.t, WISH.SOURCE, self.e.gm.everyone,
            wish_edition='csv-row623')
        self.assertEqual(self.p.budget['standard'], 0)
        self.assertEqual(self.p.move_uses[WISH.SOURCE], 1)
        row = next(r for r in self.e.delayed if r.get('kind') == 'wish')
        self.assertIs(row['turn_owner'], self.t)
        self.assertIs(row['who'], self.t)

    def test_wish_user_next_turn_not_casting_turn_target_turn_round_or_elapsed_time(self):
        self.e.gm.set_injuries(self.t, 2, reason='actual existing injury-limited maximum')
        self.e.lose_hp(self.t, self.t.hp - 1, source='actual earlier damage')
        before = self.t.hp
        self.assertLess(before + self.t.base_max_hp // 2, self.t.max_hp)
        self.begin(self.p)
        row = self.cast(self.p, self.t)
        self.assertIs(row['turn_owner'], self.p)
        self.e.end_of_turn(self.p)
        self.assertEqual(self.t.hp, before)
        self.next_round(self.t)
        self.e.end_of_turn(self.t)
        self.assertEqual(self.t.hp, before)
        self.e.end_round()
        self.assertEqual(self.t.hp, before)
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(self.p)
        self.assertEqual(self.t.hp, before)
        self.e.end_of_turn(self.p)
        self.assertEqual(self.t.hp, min(self.t.max_hp, before + self.t.base_max_hp // 2))
        self.assertFalse(any(r.get('kind') == 'wish' for r in self.e.delayed))
        self.assertTrue(self.e.validate_state()['valid'])

    def test_wish_csv_target_next_turn_preserves_its_explicit_clock_and_current_maximum(self):
        self.e.gm.set_injuries(self.t, 2, reason='actual existing injuries')
        self.e.lose_hp(self.t, self.t.hp - 1, source='actual earlier damage')
        before = self.t.hp
        self.assertLess(before + self.t.max_hp // 2, self.t.max_hp)
        self.assertGreater(self.t.base_max_hp // 2, self.t.max_hp // 2)
        self.begin(self.p)
        self.cast(self.p, self.t, 'csv-row623')
        self.e.end_of_turn(self.p)
        self.next_round(self.t)
        self.e.end_of_turn(self.t)
        self.assertEqual(self.t.hp, min(self.t.max_hp, before + self.t.max_hp // 2))
        self.assertFalse(any(r.get('kind') == 'wish' for r in self.e.delayed))

    def test_wish_native_self_replacement_inherits_only_the_real_next_turn_and_restores(self):
        self.e.lose_hp(self.q, 30, source='actual earlier replacement damage')
        before = self.q.hp
        self.begin(self.p)
        self.cast(self.p, self.p)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.a)
        result = self.e.act_on_party(self.a, recall=[self.p], send=[(self.q, (2, 0))],
            request_id='wish-switch', reason='actual one-for-one replacement')
        self.assertTrue(result['counts_as_switch'])
        row = next(r for r in self.e.delayed if r.get('kind') == 'wish')
        self.assertIs(row['who'], self.q)
        self.assertIs(row['turn_owner'], self.q)
        saved = self.e.gm.snapshot('pending native Wish')
        restored = self.restored()
        self.e.gm.restore(saved)
        for engine in (self.e, restored):
            actors = {a.entity_id: a for a in engine.gm.everyone}
            owner, replacement = actors[self.a.entity_id], actors[self.q.entity_id]
            engine.end_of_turn(owner)
            self.assertEqual(replacement.hp, before)
            engine.end_round()
            engine.start_round(engine.gm.everyone)
            engine.start_of_turn(replacement)
            self.assertEqual(replacement.hp, before)
            engine.end_of_turn(replacement)
            self.assertEqual(replacement.hp, min(replacement.max_hp, before + replacement.base_max_hp // 2))
            self.assertTrue(engine.validate_state()['valid'])

    def test_wish_other_target_replacement_differs_by_selected_source(self):
        for selected in WISH.EDITIONS:
            with self.subTest(edition=selected):
                if selected != WISH.EDITIONS[0]:
                    self.setUp()
                self.e.lose_hp(self.q, 30, source='actual earlier damage')
                self.e.lose_hp(self.t, 25, source='actual earlier original-target damage')
                original_before, replacement_before = self.t.hp, self.q.hp
                self.begin(self.p)
                row = self.cast(self.p, self.t, selected)
                self.e.end_of_turn(self.p)
                self.e.start_of_turn(self.a)
                self.e.act_on_party(self.a, recall=[self.t], send=[(self.q, (4, 0))],
                    request_id='other-target-switch', reason='actual target replacement')
                self.assertIs(row['who'], self.t if selected == 'ptu105' else self.q)
                self.assertIs(row['turn_owner'], self.p if selected == 'ptu105' else self.q)
                self.e.end_of_turn(self.a)
                self.next_round(self.q)
                self.e.end_of_turn(self.q)
                if selected == 'ptu105':
                    self.assertEqual(self.q.hp, replacement_before)
                    self.assertEqual(self.t.hp, original_before)
                    self.next_round(self.p)
                    self.e.end_of_turn(self.p)
                    self.assertEqual(self.t.hp, min(self.t.max_hp, original_before + self.t.base_max_hp // 2))
                    self.assertEqual(self.q.hp, replacement_before)
                else:
                    self.assertEqual(self.q.hp, min(self.q.max_hp, replacement_before + self.q.max_hp // 2))
                    self.assertEqual(self.t.hp, original_before)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_wish_invalid_restored_actor_deadline_and_fainted_move_healing_use_existing_owners(self):
        self.begin(self.p)
        row = self.cast(self.p, self.t)
        good = dict(row)
        for key, bad in [('turn_deadline', False), ('turn_deadline', row['turn_deadline'] + 1),
                         ('who', self.q), ('edition', 'forged'), ('dispatch_receipt', [])]:
            row[key] = bad
            with self.assertRaises(ValueError):
                self.e.gm.snapshot()
            row.clear()
            row.update(good)
        self.e.end_of_turn(self.p)
        self.e.lose_hp(self.t, self.t.hp, source='actual faint before Wish')
        self.assertTrue(self.t.fainted)
        self.next_round(self.p)
        self.e.end_of_turn(self.p)
        self.assertGreater(self.t.hp, 0)
        self.assertFalse(self.t.fainted)
        self.assertTrue(self.e.validate_state()['valid'])

    def medicine(self, actor, *, physical=False, item='상처약'):
        actor.spec.setdefault('items', {})[item] = 1
        if physical:
            import world_entities as WORLD, items as ITEMS
            WORLD.register_object(self.e, 'original-consumable', location={'kind': 'unknown'},
                reason='actual medicinal item', kind='item_instance', item_rule_id='item/' + item,
                owner_id=actor.entity_id)
            ITEMS.equip_held(self.e, actor, item, source_instance_id='original-consumable')
        self.assertEqual(self.e.use_item(actor, item, actor,
            held_selection='original-consumable' if physical else None), (1, 0))
        row = list(PAYMENTS.validate(actor).values())[-1]
        self.assertEqual(row['outcome'], 'applied')
        return row['receipt_id']

    def test_recycle_actual_native_medicine_both_kinds_stocks_one_use_and_both_restores(self):
        for index, (role, physical) in enumerate((('pokemon', False), ('trainer', False),
                                                ('pokemon', True), ('trainer', True))):
            with self.subTest(role=role, physical=physical):
                if index:
                    self.setUp()
                actor = self.p if role == 'pokemon' else self.a
                self.e.gm.set_move(actor, RECYCLE.SOURCE, reason='actually learned Recycle')
                self.e.lose_hp(actor, 40, source='actual earlier damage')
                self.begin(actor)
                identity = self.medicine(actor, physical=physical)
                count = actor.spec['items']['상처약']
                self.e.end_of_turn(actor)
                self.next_round(actor)
                before = actor.hp
                if role == 'trainer' and physical:
                    self.e.use_move_on(actor, actor, RECYCLE.SOURCE, self.e.gm.everyone, recycle_receipt_id=identity)
                else:
                    self.e.use_move(actor, actor, RECYCLE.SOURCE, recycle_receipt_id=identity)
                self.assertEqual(actor.hp, min(actor.max_hp, before + 20))
                self.assertEqual(actor.spec['items']['상처약'], count)
                self.assertEqual(actor.budget['standard'], 0)
                self.assertEqual(actor.move_uses[RECYCLE.SOURCE], 1)
                self.assertEqual(len(PAYMENTS.validate(actor)[identity]['reuses']), 1)
                if physical:
                    self.assertIn('consumed', self.e._physical_objects['original-consumable'])
                    self.assertFalse(__import__('held_equipment').entries(actor))
                saved = self.e.gm.snapshot('completed Recycle')
                restored = self.restored()
                self.e.gm.restore(saved)
                self.assertTrue(restored.validate_state()['valid'])
                self.e.end_of_turn(actor)
                self.next_round(actor)
                before = (actor.hp, deepcopy(actor.budget), deepcopy(actor.spec['items']), self.e.rng.getstate())
                self.e.use_move(actor, actor, RECYCLE.SOURCE, recycle_receipt_id=identity)
                self.assertEqual((actor.hp, actor.budget, actor.spec['items'], self.e.rng.getstate()), before)
                self.assertEqual(len(PAYMENTS.validate(actor)[identity]['reuses']), 1)

    def test_recycle_unknown_prior_encounter_and_paid_only_receipts_reject_before_move_cost(self):
        self.e.gm.set_move(self.p, RECYCLE.SOURCE, reason='actually learned Recycle')
        self.e.lose_hp(self.p, 20, source='actual earlier damage')
        identity = self.medicine(self.p)
        self.begin(self.p)
        NATIVE.assert_rejections_unchanged(self.e, [
            lambda: self.e.use_move(self.p, self.p, RECYCLE.SOURCE, recycle_receipt_id='forged'),
            lambda: self.e.use_move(self.p, self.p, RECYCLE.SOURCE, recycle_receipt_id=identity)],
            reason_pattern=['actual original consumption', 'earlier in this encounter'])
        self.p.spec['items']['상처약'] = 1
        import items as ITEMS
        with patch.object(ITEMS, 'apply_immediate_effects', side_effect=ValueError('actual post-payment effect failure')):
            with self.assertRaisesRegex(ValueError, 'post-payment effect failure'):
                self.e.use_item(self.p, '상처약', self.p)
        unpaid_effect = list(PAYMENTS.validate(self.p).values())[-1]
        self.assertEqual(unpaid_effect['outcome'], 'paid')
        self.e.end_of_turn(self.p)
        self.next_round(self.p)
        NATIVE.assert_rejected_unchanged(self.e,
            lambda: self.e.use_move(self.p, self.p, RECYCLE.SOURCE,
                recycle_receipt_id=unpaid_effect['receipt_id']),
            reason_pattern='completed item effect, not payment alone')

    def test_recycle_actual_x_item_reuses_native_stage_effect_and_preserves_spent_identity(self):
        self.e.gm.set_move(self.p, RECYCLE.SOURCE, reason='actually learned Recycle')
        self.begin(self.p)
        identity = self.medicine(self.p, physical=True, item='플러스파워')
        self.assertEqual(self.p.stages['atk'], 2)
        self.e.end_of_turn(self.p)
        self.next_round(self.p)
        # The original native X-item recipient debt, not Recycle, owns this loss.
        self.assertEqual(self.p.budget['standard'], 0)
        self.e.end_of_turn(self.p)
        self.next_round(self.p)
        self.assertEqual(self.p.budget['standard'], 1)
        before = self.p.stages['atk']
        result = self.e.use_move(self.p, self.p, RECYCLE.SOURCE, recycle_receipt_id=identity)
        diagnostic = '\n'.join(self.e.log_lines[-18:])
        self.assertEqual(len(PAYMENTS.validate(self.p)[identity].get('reuses', [])), 1, diagnostic)
        self.assertEqual(self.p.stages['atk'], min(6, before + 2), diagnostic)
        self.assertIn('consumed', self.e._physical_objects['original-consumable'])
        self.assertEqual(len(PAYMENTS.validate(self.p)[identity]['reuses']), 1)
        self.assertTrue(self.e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
