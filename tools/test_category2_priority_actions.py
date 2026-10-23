"""Actual C07-018 consumers, with an explicit Shocking Speed producer."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from rulings import Rulings
from state_codec import dump_engine, load_engine
import initiative_interrupts as INTERRUPTS
import priority_actions as PRIORITY
import turn
import frequency as FREQ

QUICK = 'move/전광석화'
MACH = 'move/마하펀치'
THUNDER = 'move/전기쇼크'
WAVE = 'move/전격파'


class PriorityActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 871)
        self.r.rulings = self.e.rulings = Rulings()
        self.t = self.actor('trainer', 30, 'trainer', [],
                            feats=['feat/쇼킹-스피드', 'feat/락다운'],
                            skills={'집중': 5}, type_link_skills={'전기': '집중'})
        self.p = self.actor('priority user', 20, 'pokemon', ['전기'],
                            moves=[QUICK, MACH, THUNDER, WAVE,
                                   'move/힘껏펀치', 'move/리벤지'])
        self.foe = self.actor('recipient', 10, 'pokemon', ['노말'], moves=[QUICK])
        self.t.side = self.p.side = 'party'
        self.foe.side = 'enemy'
        self.e.prepare_initiative_schedule(self.e.everyone, source='gm/test-schedule')
        self.e.start_round(self.e.everyone)

    def actor(self, name, speed, kind, types, **values):
        stats = dict(hp=100, atk=30, def_=10, spa=30, spd=10, spe=speed)
        stats['def'] = stats.pop('def_')
        actor = Combatant(self.r, dict(name=name, kind=kind, level=20,
            stats=stats, types=types, movement={'land': 4}, pos=(0, 0), **values))
        self.e.gm.add_combatant(actor)
        return actor

    def close(self, actor):
        self.e.start_of_turn(actor)
        self.e.end_of_turn(actor)

    def fresh(self):
        ids = [x.entity_id for x in (self.t, self.p, self.foe)]
        state = json.loads(json.dumps(dump_engine(self.e)))
        self.e = load_engine(Rules(ROOT, ruleset='core'), state)
        index = {x.entity_id: x for x in self.e.everyone}
        self.t, self.p, self.foe = [index[uid] for uid in ids]

    def unchanged(self, callback):
        before = dump_engine(self.e)
        with self.assertRaises(ValueError):
            callback()
        self.assertEqual(before, dump_engine(self.e))

    def complete_round(self):
        self.e.finish_initiative_reaction()
        self.close(self.t)
        self.e.settle_borrowed_turn()
        self.close(self.foe)
        self.e.end_round()

    def test_exact_header_classifier_refuses_conditional_body_and_variant_promotion(self):
        for move in (QUICK, MACH, 'move/신속'):
            self.assertEqual(PRIORITY.classify(self.r, move), {'variant': 'plain', 'move_id': move})
        for move in ('move/힘껏펀치', 'move/리벤지'):
            self.assertEqual(PRIORITY.classify(self.r, move)['variant'], 'limited')
        # The conditional pledge text does not grant the base Move Priority.
        self.assertNotIn('우선', self.r.moves_mech['move/불꽃의맹세']['header']['keywords'])
        self.assertIsNone(PRIORITY.classify(self.r, 'move/불꽃의맹세'))
        self.assertIsNone(PRIORITY.classify(self.r, THUNDER))

    def test_two_actual_plain_moves_pay_standard_allow_remainder_and_consume_current_slot_once(self):
        for move in (QUICK, MACH):
            with self.subTest(move=move):
                if move != QUICK:
                    self.setUp()
                hp = self.foe.hp
                result = self.e.use_priority_move(self.p, self.foe, move)
                self.assertEqual(result['source'], move)
                self.assertLess(self.foe.hp, hp)
                self.assertEqual(self.p.move_uses[move], 1)
                self.assertEqual(self.p.budget, {'standard': 0, 'shift': 1, 'swift': 1})
                self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 1)
                self.assertTrue(turn.spend(self.e, self.p, 'shift'))
                self.assertTrue(turn.spend(self.e, self.p, 'swift'))
                self.complete_round()
                self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 1)
                self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])
                dump_engine(self.e)

    def test_nonpriority_delayed_limited_bodyonly_advanced_and_unlearned_reject_atomically(self):
        for move in (THUNDER, 'move/힘껏펀치', 'move/리벤지', 'move/불꽃의맹세', 'move/신속'):
            with self.subTest(move=move):
                self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, move))

    def test_plain_already_acted_and_during_other_turn_refuse_before_payment(self):
        self.close(self.t)
        self.close(self.p)
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, QUICK))
        self.e.start_of_turn(self.foe)
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, QUICK))

    def test_late_native_failure_rolls_back_turn_loan_free_frequency_and_rng(self):
        for trainer in (None, self.t):
            with self.subTest(advanced=trainer is not None):
                move = QUICK if trainer is None else THUNDER
                with patch.object(Engine, 'use_move_on', side_effect=ValueError('late native failure')):
                    self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, move, shocking_speed=trainer))

    def test_plain_open_turn_gm_and_fresh_rules_restore_keep_paid_move_and_remaining_actions(self):
        self.e.use_priority_move(self.p, self.foe, QUICK)
        hp = self.foe.hp
        self.e.gm.snapshot('priority')
        self.e.finish_initiative_reaction()
        self.e.gm.restore('priority')
        self.assertIs(self.e._active_turn_actor, self.p)
        self.fresh()
        self.assertEqual(self.foe.hp, hp)
        self.assertEqual(self.p.move_uses[QUICK], 1)
        self.assertTrue(turn.spend(self.e, self.p, 'shift'))
        self.complete_round()
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 1)

    def test_actual_native_accuracy_wait_keeps_priority_loan_and_restores_before_damage(self):
        import passive_events as PASSIVE
        import items
        self.foe.spec['abilities'] = ['테라셸']
        self.foe.abilities = ['테라셸']
        self.e.register_abilities(self.foe)
        self.e.watch_ability_interrupt(self.foe, 'ability/테라셸', reason='actual defensive choice')
        hp = self.foe.hp
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_priority_move(self.p, self.foe, QUICK)
        event = self.e._passive_pending
        self.assertIs(self.e._active_turn_actor, self.p)
        self.assertEqual(self.p.move_uses[QUICK], 1)
        self.assertEqual(self.foe.hp, hp)
        self.fresh()
        self.e.choose_ability_interrupt(event, self.foe, use=True,
            options={'chosen_type': '강철'}, reason='native recipient chooses')
        self.assertIsNone(self.e._passive_pending)
        self.assertLess(self.foe.hp, hp)
        self.assertEqual(self.p.move_uses[QUICK], 1)
        self.assertEqual(len(self.e.initiative_reaction_status()['owed_turns']), 1)
        self.complete_round()

    def test_shocking_speed_two_real_electric_moves_free_cost_and_current_whole_turn(self):
        for move in (THUNDER, WAVE):
            with self.subTest(move=move):
                if move != THUNDER:
                    self.setUp()
                hp = self.foe.hp
                result = self.e.use_priority_move(self.p, self.foe, move, shocking_speed=self.t)
                self.assertEqual(result['source'], PRIORITY.SHOCKING)
                self.assertEqual(self.t._action_history, ['free'])
                self.assertEqual(FREQ.state(self.t)['activations'][PRIORITY.SHOCKING]['used'], 1)
                self.assertLess(self.foe.hp, hp)
                self.assertEqual(self.p.budget, {'standard': 0, 'shift': 1, 'swift': 1})
                self.assertTrue(turn.spend(self.e, self.p, 'shift'))
                self.complete_round()
                self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 1)

    def test_advanced_after_acted_uses_next_round_turn_and_debt_survives_fresh_rules(self):
        self.close(self.t)
        self.close(self.p)
        self.e.use_priority_move(self.p, self.foe, WAVE, shocking_speed=self.t)
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'][0]['due_round'], 2)
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 2)
        self.e.finish_initiative_reaction()
        self.close(self.foe)
        self.e.end_round()
        self.fresh()
        self.e.prepare_initiative_schedule(self.e.everyone, source='gm/test-schedule')
        self.e.start_round(self.e.everyone)
        self.close(self.t)
        with self.assertRaises(ValueError):
            self.e.start_of_turn(self.p)
        self.e.settle_borrowed_turn()
        self.close(self.foe)
        self.e.end_round()
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'], 2)
        self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])

    def test_shocking_speed_exact_scene_two_uses_and_no_third_payment(self):
        for used in (1, 2):
            self.e.use_priority_move(self.p, self.foe, WAVE, shocking_speed=self.t)
            self.assertEqual(FREQ.state(self.t)['activations'][PRIORITY.SHOCKING]['used'], used)
            self.complete_round()
            self.e.prepare_initiative_schedule(self.e.everyone, source='gm/test-schedule')
            self.e.start_round(self.e.everyone)
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, WAVE, shocking_speed=self.t))

    def test_advanced_nonqualifying_type_frequency_and_feature_prerequisites_are_atomic(self):
        mutations = [
            lambda: setattr(self.p, 'types', ['노말']),
            lambda: self.t.spec.update(feats=['feat/락다운']),
            lambda: self.t.spec.update(feats=['feat/쇼킹-스피드']),
            lambda: self.t.spec.update(skills={'집중': 4}),
            lambda: self.t.spec.update(type_link_skills={'전기': '직감'}),
        ]
        for mutation in mutations:
            with self.subTest(case=mutations.index(mutation)):
                self.setUp()
                mutation()
                self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, THUNDER, shocking_speed=self.t))
        self.setUp()
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, QUICK, shocking_speed=self.t))
        self.p.spec['moves'][-1] = self.p.moves[-1] = 'move/방전'
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, 'move/방전', shocking_speed=self.t))

    def test_total_blindness_blocks_granted_advanced_before_free_or_start_cure(self):
        self.p.conditions.add('완전-실명')
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, WAVE, shocking_speed=self.t))
        self.unchanged(lambda: self.e.use_priority_move(self.p, self.foe, QUICK))

    def test_limited_actual_training_order_preserves_own_shift_swift_and_no_whole_turn_loan(self):
        import training_features as TRAINING
        import items
        import pokemon_entities as ENTITIES
        self.t.spec['feats'].append(TRAINING.FOCUSED)
        self.t.spec['skills']['명령'] = 3
        self.p.spec.update(trainer_id=self.t.entity_id, trainer=self.t.name)
        ENTITIES.observe_loyalty(self.e, self.p, 3, reason='actual willing owned recipient')
        items.register_feats(self.e, self.t)
        self.e.gm.observe_sensory_environment(self.t, self.p,
            paths={'auditory': True}, present=True, reason='actual order path')
        out = self.e.manual_feat(self.t, TRAINING.FOCUSED, self.p)
        self.assertEqual(out['status'], 'applied')
        self.assertIsNone(self.e._active_turn_actor)
        self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])
        self.e.start_of_turn(self.t)
        self.assertEqual(self.t.budget, {'standard': 0, 'shift': 1, 'swift': 1})
        self.assertTrue(turn.spend(self.e, self.t, 'shift'))
        self.assertTrue(turn.spend(self.e, self.t, 'swift'))
        self.e.end_of_turn(self.t)
        self.close(self.p)
        self.close(self.foe)
        self.e.end_round()
        dump_engine(self.e)


if __name__ == '__main__':
    unittest.main()
