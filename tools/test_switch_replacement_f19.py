"""A native held-item switch requires an actual replacement Pokemon."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import csv_item_physical_contracts as PHYSICAL
import test_category2_csv_remaining_item_contracts as FIX
import world_entities as WORLD
from engine import Engine
from native_scenario_fixture import assert_rejected_unchanged


class SwitchReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIX.RemainingCsvItemContractTests.setUpClass()

    def setUp(self):
        self.f = FIX.RemainingCsvItemContractTests()

    def fixture(self, kind, *, reserve_count=0, decoys=False):
        owner = self.f.trainer('holder-controller')
        rival = self.f.trainer('attacker-controller')
        holder = self.f.pokemon('holder-' + kind)
        attacker = self.f.pokemon('attacker-' + kind)
        holder.spec['trainer_id'] = owner.entity_id
        attacker.spec['trainer_id'] = rival.entity_id
        holder.side, attacker.side = 'party', 'foe'
        holder.pos = (1, 0)
        attacker.spec['loyalty'] = 2
        controller = rival if kind == 'red_card' else owner
        reserves = [self.f.pokemon('reserve-' + str(i)) for i in range(reserve_count)]
        for actor in reserves:
            actor.spec['trainer_id'] = controller.entity_id
            actor.side = 'foe' if kind == 'red_card' else 'party'
        others = []
        if decoys:
            foreign = self.f.pokemon('foreign-reserve')
            foreign.spec['trainer_id'] = owner.entity_id
            foreign.side = 'party'
            exhausted = self.f.pokemon('fainted-reserve')
            exhausted.spec['trainer_id'] = rival.entity_id
            exhausted.side = 'foe'
            others = [foreign, exhausted]
        engine = self.f.fixture(owner, rival, holder, attacker, *reserves, *others)
        holder.on_field = attacker.on_field = True
        for actor in reserves + others:
            actor.on_field = False
        if decoys:
            engine.gm.set_hp(others[1], value=0, reason='actual unavailable reserve')
        uid = 'f19/' + kind
        item_id = {'eject_button': 'item/탈출버튼', 'eject_pack': 'item/탈출팩',
                   'red_card': 'item/레드카드'}[kind]
        self.f.equip(engine, holder, uid, item_id)
        engine.start_round([attacker, holder])
        engine.start_of_turn(holder, initiative_count=30)
        engine.end_of_turn(holder)
        engine.start_of_turn(attacker, initiative_count=20)
        return engine, holder, attacker, reserves, others, uid

    def restore(self, engine, holder, attacker, reserves, others):
        restored = Engine.import_state(self.f.r,
            json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(restored)
        return (restored, actors[holder.entity_id], actors[attacker.entity_id],
                [actors[a.entity_id] for a in reserves], [actors[a.entity_id] for a in others])

    def trigger(self, engine, holder, attacker, kind):
        if kind == 'eject_pack':
            before = holder.stages['atk']
            engine.change_stage(holder, 'atk', -1)
            self.assertEqual(holder.stages['atk'], before - 1)
        else:
            before = holder.hp
            with patch.object(engine, 'd20', return_value=18):
                engine.use_move(attacker, holder, 'move/몸통박치기', set_damage=True)
            self.assertLess(holder.hp, before)

    def test_optional_missing_replacement_preserves_pending_physical_frequency_actions_and_rng(self):
        for kind in ('eject_button', 'eject_pack'):
            for restored in (False, True):
                for reserve_count in (0, 1):
                    with self.subTest(kind=kind, restored=restored, reserves=reserve_count):
                        engine, holder, attacker, reserves, others, uid = self.fixture(
                            kind, reserve_count=reserve_count)
                        self.trigger(engine, holder, attacker, kind)
                        if restored:
                            engine, holder, attacker, reserves, others = self.restore(
                                engine, holder, attacker, reserves, others)
                        self.assertIn(kind, holder.spec[PHYSICAL.PENDING])
                        assert_rejected_unchanged(engine,
                            lambda: PHYSICAL.resolve_pending(engine, holder, kind, accept=True),
                            reason_pattern='replacement')
                        self.assertTrue(holder.on_field)
                        self.assertNotIn('consumed', engine._physical_objects[uid])
                        self.assertTrue(engine.validate_state()['valid'])

    def test_automatic_without_replacement_consumes_once_without_recall_or_random_choice(self):
        for restored in (False, True):
            with self.subTest(restored=restored):
                engine, holder, attacker, reserves, others, uid = self.fixture('red_card')
                if restored:
                    engine, holder, attacker, reserves, others = self.restore(
                        engine, holder, attacker, reserves, others)
                with patch.object(type(engine.rng), 'choice', autospec=True,
                                  side_effect=type(engine.rng).choice) as choose:
                    self.trigger(engine, holder, attacker, 'red_card')
                choose.assert_not_called()
                self.assertTrue(attacker.on_field)
                obj = engine._physical_objects[uid]
                self.assertIn('consumed', obj)
                self.assertNotIn('red_card', holder.spec.get(PHYSICAL.PENDING, {}))
                self.assertEqual(sum(row['event'] == 'consumed'
                                     for row in obj[PHYSICAL.OBJECT_STATE]['history']), 1)
                self.assertTrue(engine.validate_state()['valid'])

    def test_one_replacement_switches_all_items_and_preserves_optional_free_action(self):
        for kind in ('eject_button', 'eject_pack', 'red_card'):
            for restored in (False, True):
                with self.subTest(kind=kind, restored=restored):
                    engine, holder, attacker, reserves, others, uid = self.fixture(kind, reserve_count=1)
                    if kind != 'red_card':
                        self.trigger(engine, holder, attacker, kind)
                    if restored:
                        engine, holder, attacker, reserves, others = self.restore(
                            engine, holder, attacker, reserves, others)
                    if kind == 'red_card':
                        self.trigger(engine, holder, attacker, kind)
                        outgoing = attacker
                    else:
                        self.assertIn(kind, holder.spec[PHYSICAL.PENDING])
                        budgets = deepcopy((holder.budget, attacker.budget))
                        result = PHYSICAL.resolve_pending(engine, holder, kind, accept=True, send=reserves[0])
                        self.assertEqual(result['sent_id'], reserves[0].entity_id)
                        self.assertEqual((holder.budget, attacker.budget), budgets)
                        outgoing = holder
                    self.assertFalse(outgoing.on_field)
                    self.assertTrue(reserves[0].on_field)
                    self.assertIn('consumed', engine._physical_objects[uid])
                    self.assertTrue(engine.validate_state()['valid'])

    def test_random_replacement_uses_only_actual_attacker_controller_conscious_reserves(self):
        for restored in (False, True):
            with self.subTest(restored=restored):
                engine, holder, attacker, reserves, others, uid = self.fixture(
                    'red_card', reserve_count=2, decoys=True)
                if restored:
                    engine, holder, attacker, reserves, others = self.restore(
                        engine, holder, attacker, reserves, others)
                with patch.object(type(engine.rng), 'choice', autospec=True,
                                  side_effect=type(engine.rng).choice) as choose:
                    self.trigger(engine, holder, attacker, 'red_card')
                choose.assert_called_once()
                self.assertEqual({a.entity_id for a in choose.call_args.args[1]},
                                 {a.entity_id for a in reserves})
                self.assertFalse(attacker.on_field)
                self.assertEqual(sum(a.on_field for a in reserves), 1)
                self.assertFalse(any(a.on_field for a in others))
                self.assertIn('consumed', engine._physical_objects[uid])
                self.assertTrue(engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
