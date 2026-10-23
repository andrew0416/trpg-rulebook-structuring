"""Exact CSV reactive type/handoff contracts through native Move producers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import ability_transitions as A
import state_grants as G


class ReactiveAbilityEventsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 530)
        self.e.grid = Grid(30, 30)
        self.a = self.actor('attacker', [], (2, 2), 'party')
        self.t = self.actor('holder', [], (3, 2), 'opponent')
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def actor(self, name, abilities, pos, side, *, trainer=False):
        moves = ['move/몸통박치기', 'move/물대포', 'move/칼춤']
        extra = {'abilities': abilities, 'size': '중형', 'pos': pos,
                 'side': side, 'moves': moves}
        if trainer:
            spec = build_trainer(self.r, name, 10,
                dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10), extra=extra)
        else:
            spec = build_pokemon(self.r, '이상해씨', 10, name=name, moves=moves, extra=extra)
        actor = Combatant(self.r, spec)
        self.e.gm.add_combatant(actor)
        return actor

    def give(self, actor, abilities):
        G.replace_baseline(self.e, actor, 'abilities', abilities)

    def fresh(self):
        saved = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        new = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        index = {c.entity_id: c for c in new.everyone}
        return new, index[self.a.entity_id], index[self.t.entity_id]

    def world(self):
        return deepcopy((self.a.spec, self.a.budget, self.t.spec,
                         getattr(self.t, 'budget', None), self.e.rng.getstate()))

    def choose(self, actor, source, ability=None):
        return self.e.choose_reactive_ability(actor, source, ability=ability,
            reason='actual owner authorizes this source on its next native trigger')

    def test_accuracy_suspension_restores_native_hit_without_repayment(self):
        import test_foundation_event_subscriptions as SUBSCRIPTIONS
        import passive_events as PASSIVE
        SUBSCRIPTIONS.Subscriptions.setUpClass()
        fixture = SUBSCRIPTIONS.Subscriptions()
        e, a, target, doc, _ = fixture.fixture()
        G.replace_baseline(e, target, 'abilities', ['변색'])
        target.spec['types'] = ['물']; target._types = ['물']
        target.damage_cap = {'value': 1}
        e.choose_reactive_ability(target, 'ability/변색', reason='owner chooses next native hit')
        pending = deepcopy(doc); pending['id'] = 'event/reactive-accuracy-wait'
        pending['variants'][0]['inputs']['choice'] = {
            'type': 'boolean', 'authority': 'gm', 'question': 'Reaction choice'}
        pending['variants'][0]['values']['effects'][0]['delta'] = 0
        key = e.subscribe_source_policy(a, 'reactive-wait', pending,
            event='accuracy_resolved', inputs={'hit': 'hit'})
        hp = target.hp
        with self.assertRaises(PASSIVE.PassiveEventPending):
            e.use_move(a, target, 'struggle', set_damage=True)
        event = e._passive_pending
        self.assertIsNotNone(event)
        self.assertEqual(target.hp, hp)
        self.assertEqual(target.types, ['물'])
        self.assertEqual(a.move_uses['struggle'], 1)
        rng = e.rng.getstate()
        new = Engine.import_state(Rules(ROOT, ruleset='core'),
            json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        actor, holder = new.everyone
        new.choose_passive_event(event, actor, key,
            {'decisions': {'choice': {'value': True, 'reason': 'actual reaction decision'}}})
        self.assertEqual(holder.types, ['노말'])
        self.assertLess(holder.hp, hp)
        self.assertEqual(actor.move_uses['struggle'], 1)
        self.assertEqual(actor._action_history, ['standard'])
        self.assertEqual(new.rng.getstate(), rng)
        before = new.export_state()
        self.assertEqual(new.deliver_passive_event(event), 'already_delivered')
        self.assertEqual(new.export_state(), before)

    def test_color_change_native_hit_updates_only_after_damage_and_preserves_baseline(self):
        self.give(self.t, ['변색'])
        baseline = list(self.t.spec['types'])
        budget = deepcopy(getattr(self.t, 'budget', None))
        self.choose(self.t, 'ability/변색')
        dealt = self.e.use_move(self.a, self.t, 'move/물대포', set_damage=True)
        self.assertGreater(dealt, 0)
        self.assertEqual(self.t.types, ['물'])
        self.assertEqual(self.t.spec['types'], baseline)
        self.assertEqual(getattr(self.t, 'budget', None), budget)
        new, _, target = self.fresh()
        self.assertEqual(target.types, ['물'])
        new.end_encounter(new.everyone)
        self.assertEqual(target.types, ['물'])

    def test_aroma_daily_use_survives_encounter_end_and_cold_restore(self):
        self.give(self.t, ['가시지않는향기']); self.give(self.a, ['인분'])
        self.choose(self.t, 'ability/가시지않는향기')
        self.e.use_move(self.a, self.t, 'move/몸통박치기')
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(self.a.abilities, ['인분'])
        new, _, holder = self.fresh()
        before = new.export_state()
        with self.assertRaisesRegex(ValueError, 'frequency exhausted'):
            new.choose_reactive_ability(holder, 'ability/가시지않는향기', reason='same day next encounter')
        self.assertEqual(new.export_state(), before)

    def test_spirit_scene_use_not_replenished_by_source_withdrawal_and_return(self):
        self.give(self.t, ['떠도는영혼']); self.give(self.a, ['인분'])
        self.choose(self.t, 'ability/떠도는영혼')
        self.e.use_move(self.a, self.t, 'move/몸통박치기')
        self.e.gm.recall(self.t, reason='participant recalls after its scene reaction')
        self.assertEqual(self.t.abilities, ['떠도는영혼'])
        before = self.world()
        with self.assertRaisesRegex(ValueError, 'frequency exhausted'):
            self.choose(self.t, 'ability/떠도는영혼')
        self.assertEqual(self.world(), before)

    def test_color_change_actual_immune_hit_changes_type_and_miss_does_not(self):
        self.give(self.t, ['변색'])
        self.t.spec['types'] = ['고스트']; self.t._types = ['고스트']
        self.choose(self.t, 'ability/변색')
        self.assertEqual(self.e.use_move(self.a, self.t, 'move/몸통박치기'), 0)
        self.assertEqual(self.t.types, ['노말'])
        self.setUp(); self.give(self.t, ['변색'])
        original = list(self.t.types)
        self.choose(self.t, 'ability/변색')
        self.e.rng.seed(31)
        self.e.use_move(self.a, self.t, 'move/물대포')
        self.assertEqual(self.t.types, original)

    def test_native_cannot_hit_prevention_is_distinct_from_an_immune_hit(self):
        from unittest.mock import patch
        import effects_ext as EXT
        self.give(self.t, ['변색', '불가사의부적'])
        before = list(self.t.types)
        self.choose(self.t, 'ability/변색')
        blocked = []; original = EXT.blocks_hit
        def observe(*args, **kwargs):
            result = original(*args, **kwargs)
            blocked.append(result)
            return result
        with patch.object(EXT, 'blocks_hit', side_effect=observe):
            self.assertEqual(self.e.use_move(self.a, self.t, 'move/물대포', set_damage=True), 0)
        self.assertIn('ability/불가사의부적', blocked)
        self.assertEqual(self.t.types, before)
        # This actual cannot-hit predicate prevents accuracy itself; unlike an
        # immune hit it therefore records a miss before native damage resolution.
        self.assertEqual(self.e._precision_events[-1]['result'], 'miss')
        self.assertIn('ability/변색', self.t.spec['reactive_ability_choices'])

    def test_protean_native_use_changes_before_same_move_stab_and_spends_swift(self):
        # Both attacks have identical native dice, target and initial user types.
        ordinary = self.e.use_move(self.a, self.t, 'move/물대포', set_damage=True)
        self.setUp(); self.give(self.a, ['변환자재'])
        self.choose(self.a, 'ability/변환자재')
        changed = self.e.use_move(self.a, self.t, 'move/물대포', set_damage=True)
        self.assertEqual(self.a.types, ['물'])
        self.assertGreater(changed, ordinary)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertEqual(self.a.budget['swift'], 0)
        self.assertEqual(self.a.move_uses['move/물대포'], 1)

    def test_protean_decline_and_combined_cost_failure_leave_types_and_usage_intact(self):
        self.give(self.a, ['변환자재'])
        original = list(self.a.types)
        self.e.use_move(self.a, self.t, 'move/물대포')
        self.assertEqual(self.a.types, original)
        self.setUp(); self.give(self.a, ['변환자재'])
        self.choose(self.a, 'ability/변환자재')
        self.a.budget['swift'] = 0
        before = self.world()
        with self.assertRaises(ValueError):
            self.e.use_move(self.a, self.t, 'move/물대포')
        self.assertEqual(self.world(), before)

    def test_wandering_spirit_native_melee_swaps_only_self_source_with_random_opponent(self):
        self.give(self.t, ['떠도는영혼', '인분'])
        self.give(self.a, ['불굴의방패', '불요의검'])
        self.choose(self.t, 'ability/떠도는영혼')
        self.e.use_move(self.a, self.t, 'move/몸통박치기')
        self.assertIn('인분', self.t.abilities)
        self.assertNotIn('떠도는영혼', self.t.abilities)
        self.assertIn('떠도는영혼', self.a.abilities)
        copied = set(self.t.abilities) - {'인분'}
        self.assertEqual(len(copied), 1)
        self.assertTrue(copied <= {'불굴의방패', '불요의검'})
        self.assertEqual(set(self.a.abilities), {'떠도는영혼'} | ({'불굴의방패', '불요의검'} - copied))
        new, attacker, target = self.fresh()
        new.end_encounter(new.everyone)
        self.assertEqual(set(attacker.abilities), {'불굴의방패', '불요의검'})
        self.assertEqual(set(target.abilities), {'떠도는영혼', '인분'})

    def test_wandering_spirit_rejects_caller_random_choice_and_non_pokemon_attacker(self):
        self.give(self.t, ['떠도는영혼'])
        with self.assertRaises(ValueError):
            self.choose(self.t, 'ability/떠도는영혼', ability='불굴의방패')
        trainer = self.actor('trainer attacker', ['불굴의방패'], (3, 3), 'party', trainer=True)
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(trainer, initiative_count=19)
        self.choose(self.t, 'ability/떠도는영혼')
        self.e.use_move(trainer, self.t, 'move/몸통박치기')
        self.assertEqual(self.t.abilities, ['떠도는영혼'])
        self.assertEqual(trainer.abilities, ['불굴의방패'])

    def test_lingering_aroma_replaces_all_attacker_abilities_and_restores_at_encounter_end(self):
        self.give(self.t, ['가시지않는향기'])
        self.give(self.a, ['불굴의방패', '불요의검'])
        self.choose(self.t, 'ability/가시지않는향기')
        self.e.use_move(self.a, self.t, 'move/몸통박치기')
        self.assertEqual(self.a.abilities, ['가시지않는향기'])
        self.assertEqual(self.a.stages['def'], 0)
        self.assertEqual(self.a.stages['atk'], 0)
        new, attacker, _ = self.fresh()
        new.end_encounter(new.everyone)
        self.assertEqual(set(attacker.abilities), {'불굴의방패', '불요의검'})

    def test_melee_reactions_ignore_ranged_and_missed_native_attacks(self):
        for source in ('ability/떠도는영혼', 'ability/가시지않는향기'):
            for miss in (False, True):
                with self.subTest(source=source, miss=miss):
                    self.setUp(); self.give(self.t, [source.split('/', 1)[1]]); self.give(self.a, ['인분'])
                    self.choose(self.t, source)
                    if miss: self.e.rng.seed(31)
                    self.e.use_move(self.a, self.t,
                        'move/몸통박치기' if miss else 'move/물대포')
                    self.assertEqual(self.t.abilities, [source.split('/', 1)[1]])
                    self.assertEqual(self.a.abilities, ['인분'])

    def test_both_type_reactions_consume_actual_individual_move_type_not_catalog_type(self):
        import move_type_sync as SYNC
        self.give(self.a, ['변환자재']); self.give(self.t, ['변색'])
        SYNC.observe(self.e, self.a, application_id='reactive-native-electric-water-gun',
            move_id='move/물대포', chosen_type='전기', new_name='전기대포',
            effect_decision={'mode': 'preserve', 'reason': 'keep exact authored effects', 'effects_exec': None},
            feasibility_review='GM accepts the completed individual type sync',
            power_review='GM confirms unchanged base damage', reason='actual completed adaptation')
        self.choose(self.a, 'ability/변환자재'); self.choose(self.t, 'ability/변색')
        self.e.use_move(self.a, self.t, 'move/물대포')
        self.assertEqual(self.a.types, ['전기'])
        self.assertEqual(self.t.types, ['전기'])
        self.assertEqual(self.r.move('move/물대포')['type'], '물')

    def test_untrusted_hit_or_use_assertions_and_direct_damage_never_activate_intents(self):
        import reactive_ability_events as R
        self.give(self.a, ['변환자재'])
        self.give(self.t, ['변색'])
        self.choose(self.a, 'ability/변환자재')
        self.choose(self.t, 'ability/변색')
        original = list(self.t.types)
        move = self.r.move('move/물대포')
        before = self.world()
        with self.assertRaises(ValueError):
            R.begin_move(self.e, self.a, self.t, move, 'fabricated-completion')
        with self.assertRaises(ValueError):
            R.resolved_hit(self.e, self.a, self.t, move, 'fabricated-completion')
        self.assertEqual(self.world(), before)
        self.e.resolve_attack_damage(self.a, self.t, move, set_damage=True)
        self.assertEqual(self.t.types, original)

    def test_lingering_aroma_preserves_innate_identity_while_replacing_transferable_components(self):
        self.give(self.t, ['가시지않는향기'])
        self.give(self.a, ['멀티타입', '불굴의방패', '불요의검'])
        self.choose(self.t, 'ability/가시지않는향기')
        self.e.use_move(self.a, self.t, 'move/몸통박치기')
        self.assertEqual(set(self.a.abilities), {'멀티타입', '가시지않는향기'})
        self.assertTrue(A.active(self.a, 'ability/멀티타입'))
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(set(self.a.abilities), {'멀티타입', '불굴의방패', '불요의검'})

    def test_type_source_withdrawal_preserves_independent_type_contribution(self):
        self.give(self.t, ['변색'])
        original = list(self.t.types)
        G.type_operation(self.t, 'add', ['드래곤'], 'independent:dragon')
        self.choose(self.t, 'ability/변색')
        self.e.use_move(self.a, self.t, 'move/물대포')
        self.assertEqual(self.t.types, ['물'])
        self.give(self.t, ['인분'])
        self.assertEqual(self.t.types, list(dict.fromkeys([*original, '드래곤'])))
        self.assertIn('independent:dragon', self.t.spec[G.KEY]['type_sources']['sources'])


if __name__ == '__main__':
    unittest.main()
