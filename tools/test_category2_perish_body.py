"""R0141: native completed hit, explicit Reaction, independent volatile counts."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
import action_resources as RESOURCES
import condition_instances as CONDITIONS
import custom_condition_effects as CUSTOM
import linked_move_conditions as LINKED
import perish_body as PB
import state_grants as G


class PerishBodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 530)
        self.e.grid = Grid(20, 20)
        self.a = self.actor('attacker', [], (2, 2), 'opponent')
        self.t = self.actor('body owner', ['멸망의바디'], (3, 2), 'party')
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def actor(self, name, abilities, pos, side):
        moves = ['move/몸통박치기', 'move/물대포', 'move/멸망의노래', 'move/칼춤']
        actor = Combatant(self.r, build_pokemon(self.r, '이상해씨', 30,
            name=name, moves=moves, extra={'abilities': abilities, 'pos': pos,
                                          'side': side, 'size': '중형'}))
        self.e.gm.add_combatant(actor)
        return actor

    def watch(self, owner=None):
        return self.e.watch_ability_reaction(owner or self.t, PB.SOURCE,
            reason='owner requests an explicit completed-hit Reaction choice')

    def offer(self, move='move/몸통박치기', *, owner=None):
        owner = owner or self.t
        self.watch(owner)
        hp = owner.hp
        self.e.use_move(self.a, owner, move, set_damage=True)
        self.assertLess(owner.hp, hp)
        self.assertIsNone(self.e._passive_pending)
        pending = self.e.pending_ability_reactions()
        own = [r for r in pending if r['owner_id'] == owner.entity_id and r['source'] == PB.SOURCE]
        self.assertEqual(len(own), 1)
        self.assertNotIn(PB.NAME, owner.conditions)
        self.assertNotIn(PB.NAME, self.a.conditions)
        return own[0]['event_id']

    def choose(self, event_id, *, owner=None, use=True):
        return self.e.choose_ability_reaction(event_id, owner or self.t, use=use,
            reason='actual owner chooses the post-return source Reaction')

    def activate(self):
        event = self.offer()
        self.choose(event)
        return event

    def count(self, actor):
        records = CONDITIONS.records(actor, PB.NAME)
        self.assertEqual(len(records), 1)
        return records[0]

    def turn(self, actor, *, new_round=True):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        if new_round:
            self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=20)

    def fresh(self):
        saved = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        identities = self.a.entity_id, self.t.entity_id
        self.e = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        index = {a.entity_id: a for a in self.e.everyone}
        self.a, self.t = (index[i] for i in identities)
        return saved

    def test_actual_completed_melee_hit_creates_exact_ability_pair_after_acceptance(self):
        event = self.offer()
        owner_turn = self.t.custom_conditions.get('combat_turn_serial', 0)
        self.choose(event)
        for holder in (self.a, self.t):
            record = self.count(holder)
            self.assertEqual(record['source'], PB.SOURCE)
            self.assertNotEqual(record['source'], LINKED.PERISH)
            self.assertEqual(record['effect']['operation'], 'perish_count')
            self.assertEqual(record['applications'], [])
            self.assertEqual(record['effect_instance']['applied_by_actor_id'], self.t.entity_id)
            self.assertEqual(record[PB.TAG]['event_id'], event)
        self.assertEqual(self.t.custom_conditions.get('combat_turn_serial', 0), owner_turn)
        self.assertIs(self.e._active_turn_actor, self.a)
        self.assertEqual(self.t.spec['frequency_state']['activations'][PB.SOURCE]['used'], 1)
        self.assertEqual(self.a.move_uses['move/몸통박치기'], 1)

    def test_decline_leaves_count_action_debt_and_daily_use_unchanged(self):
        event = self.offer()
        before = deepcopy((self.a.budget, getattr(self.t,'budget',None), RESOURCES.pending(self.t),
                           self.t.spec.get('frequency_state'), self.a.hp, self.t.hp))
        self.choose(event, use=False)
        self.assertEqual((self.a.budget, getattr(self.t,'budget',None), RESOURCES.pending(self.t),
                          self.t.spec.get('frequency_state'), self.a.hp, self.t.hp), before)
        self.assertNotIn(PB.NAME, self.a.conditions)
        self.assertNotIn(PB.NAME, self.t.conditions)
        self.assertNotIn(PB.KEY, self.t.spec)

    def test_holder_starts_are_independent_and_third_sets_only_that_hp_without_damage(self):
        self.activate()
        attacker_hp = self.a.hp
        self.turn(self.t)
        self.assertEqual(self.count(self.t)['applications'][-1]['remaining'], 2)
        self.assertEqual(self.count(self.a)['applications'], [])
        self.turn(self.t)
        self.assertEqual(self.count(self.t)['applications'][-1]['remaining'], 1)
        self.e.enable_execution_trace()
        with patch.object(self.e, 'take_damage', side_effect=AssertionError('Perish must not deal damage')):
            self.turn(self.t)
        self.assertEqual(self.t.hp, 0)
        self.assertEqual(self.a.hp, attacker_hp)
        self.assertNotIn(PB.NAME, self.t.conditions)
        self.assertEqual(self.count(self.a)['applications'], [])
        losses = [r for r in self.e.execution_traces() if r['kind'] == 'non_attack_hp_loss'
                  and r['inputs']['source'] == PB.SOURCE]
        self.assertEqual(len(losses), 1)
        self.assertEqual(losses[0]['inputs']['loss_kind'], 'hp_setting')
        self.assertTrue(losses[0]['inputs']['unpreventable'])
        closed = [r for r in self.t.spec['effect_instance_history'] if r['source'] == PB.SOURCE]
        self.assertEqual(closed[0]['applications'][-1]['remaining'], 0)
        self.fresh()

    def test_recall_breather_and_faint_clear_only_the_affected_holder(self):
        for ending in ('recall', 'breather', 'faint'):
            with self.subTest(ending=ending):
                self.setUp()
                self.activate()
                if ending == 'recall':
                    self.e.gm.recall(self.a, reason='actual count holder recalled')
                elif ending == 'breather':
                    self.turn(self.a)
                    result = self.e.take_breather(self.a, request_id='body-clear-breather',
                        path=[(2, 2), (1, 2)], retreat_reason='safe retreat confirmed',
                        save_dc=1, save_reason='GM DC', save_cost='full', fixed_save=20)
                    self.assertTrue(result['completed'])
                else:
                    self.e.lose_hp(self.a, self.a.hp, source='gm/observed-loss',
                                   unpreventable=True, loss_kind='hp_setting')
                self.assertNotIn(PB.NAME, self.a.conditions)
                self.assertEqual(self.count(self.t)['applications'], [])
                self.fresh()

    def test_miss_ranged_and_fatal_hit_do_not_offer_or_consume_ability(self):
        for variant in ('miss', 'ranged', 'faint'):
            with self.subTest(variant=variant):
                self.setUp()
                self.watch()
                if variant == 'miss':
                    self.e.rng.seed(31)
                if variant == 'faint':
                    self.t.hp = 1
                self.e.use_move(self.a, self.t,
                    'move/물대포' if variant == 'ranged' else 'move/몸통박치기', set_damage=True)
                self.assertEqual(self.e.pending_ability_reactions(), [])
                self.assertNotIn(PB.NAME, self.a.conditions)
                self.assertNotIn(PB.NAME, self.t.conditions)
                self.assertNotIn(PB.SOURCE, self.t.spec.get('frequency_state', {}).get('activations', {}))
                self.assertEqual(RESOURCES.pending(self.t), {})

    def test_existing_perish_song_blocks_whole_pair_before_ability_cost(self):
        self.e.use_move_on(self.a, self.t, LINKED.PERISH, self.e.everyone)
        self.turn(self.a)
        self.watch()
        self.e.use_move(self.a, self.t, 'move/몸통박치기', set_damage=True)
        event = self.e.pending_ability_reactions()[0]['event_id']
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, 'overlapping linked'):
            self.choose(event)
        self.assertEqual(self.e.export_state(), before)
        self.assertEqual(self.count(self.a)['source'], LINKED.PERISH)
        self.assertEqual(self.count(self.t)['source'], LINKED.PERISH)

    def test_other_ability_issuer_blocks_pair_without_adding_count_to_new_owner(self):
        self.activate()
        other = self.actor('second Body owner', ['멸망의바디'], (3, 3), 'party')
        self.turn(self.a)
        self.watch(other)
        self.e.use_move(self.a, other, 'move/몸통박치기', set_damage=True)
        event = self.e.pending_ability_reactions()[0]['event_id']
        before = self.e.export_state()
        with self.assertRaisesRegex(ValueError, 'overlapping linked'):
            self.choose(event, owner=other)
        self.assertEqual(self.e.export_state(), before)
        self.assertNotIn(PB.NAME, other.conditions)
        self.assertEqual(self.count(self.a)['effect_instance']['applied_by_actor_id'], self.t.entity_id)

    def test_direct_ability_condition_grant_and_fabricated_event_are_rejected(self):
        row = PB.condition_definition(self.r)
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            CUSTOM.grant(self.e, self.t, self.a, row['raw'], PB.SOURCE)
        with self.assertRaises(ValueError):
            PB.prepare(self.e, self.t, 'fabricated-hit')
        self.assertEqual(self.e.export_state(), before)

    def test_same_source_issuer_preflight_retains_existing_identity_and_progress(self):
        self.activate()
        self.turn(self.a)
        existing = deepcopy(self.count(self.a))
        row = PB.condition_definition(self.r)
        LINKED.prepare(self.e, self.t, self.a, row['raw'], PB.SOURCE, row)
        self.assertFalse(LINKED.grant(self.e, self.t, self.a, row['raw'], PB.SOURCE, row))
        self.assertEqual(self.count(self.a), existing)
        self.assertEqual(existing['applications'][-1]['remaining'], 2)

    def test_cold_offer_acceptance_and_live_counts_keep_daily_use_and_native_identity(self):
        event = self.offer()
        self.fresh()
        self.choose(event)
        ids = self.count(self.a)['id'], self.count(self.t)['id']
        debt = deepcopy(RESOURCES.pending(self.t))
        self.fresh()
        self.assertEqual((self.count(self.a)['id'], self.count(self.t)['id']), ids)
        self.assertEqual(RESOURCES.pending(self.t), debt)
        self.assertEqual(self.t.spec['frequency_state']['activations'][PB.SOURCE]['used'], 1)
        with self.assertRaises(ValueError):
            self.watch()
        self.assertEqual(self.a.move_uses['move/몸통박치기'], 1)

    def test_deleted_source_receipt_and_changed_condition_origin_are_rejected(self):
        self.activate()
        receipts = deepcopy(self.t.spec[PB.KEY])
        self.t.spec[PB.KEY] = {}
        with self.assertRaises(ValueError):
            PB.validate_world(self.e)
        self.t.spec[PB.KEY] = receipts
        self.count(self.a)[PB.TAG]['owner_id'] = self.a.entity_id
        with self.assertRaises(ValueError):
            self.e.export_state()


if __name__ == '__main__':
    unittest.main()
