"""C10-348's observed team state consumes the real native secondary threshold."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import combat_precision_features as PRECISION
import combat_timing as TIME
import pledge_state as PLEDGE
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD


class PledgeStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=348)
        moves = ['불꽃의맹세', '물의맹세', '아이언헤드', '전기쇼크', '코멧펀치']
        def trainer(name):
            return Combatant(self.r, build_trainer(self.r, name, 40,
                {'hp': 100, 'atk': 20, 'def': 10, 'spa': 20, 'spd': 10, 'spe': 20},
                moves=moves, abilities=[]))
        self.a = trainer('Observed Rainbow creator')
        self.ally = trainer('Actual allied trainer')
        self.enemy = trainer('Actual opposing trainer')
        self.target = trainer('Actual threshold recipient')
        self.p = Combatant(self.r, build_pokemon(self.r, '브케인', 50,
            moves=moves, abilities=[], extra={'trainer_id': self.a.entity_id}))
        for actor, pos, side in ((self.a, (1, 1), 'party'), (self.ally, (1, 2), 'party'),
                (self.p, (2, 1), 'party'), (self.enemy, (3, 2), 'wild'),
                (self.target, (2, 2), 'wild')):
            self.e.gm.add_combatant(actor, pos=pos, side=side, reason='actual Rainbow state participant')
        self.e.gm.observe_loyalty(self.p, 6, reason='actual owned native attacker')
        self.e.start_round(self.e.gm.everyone)

    def observe(self, source='move/불꽃의맹세', request='observed-rainbow'):
        return self.e.gm.observe_pledge_rainbow(self.a, source_id=source,
            request_id=request, reason='Pledge Rainbow activation was actually observed')

    def snap(self):
        receipts = getattr(self.e, '_effect_dispatch_receipts', {})
        return deepcopy((self.e.elapsed_seconds, self.e.rng.getstate(), self.e.log_lines,
            [vars(actor) for actor in self.e.gm.everyone], receipts),
            {id(self.r): self.r, id(self.e.r): self.e.r,
             **{id(actor): actor for actor in self.e.gm.everyone},
             **{id(token): token for token in receipts}})

    def attack(self, actor, move='아이언헤드', face=14):
        self.e.start_of_turn(actor, initiative_count=20)
        before = self.target.hp
        with patch.object(self.e, 'd20', return_value=face):
            self.e.use_move(actor, self.target, 'move/' + move, set_damage=True)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(actor.move_uses['move/' + move], 1)
        self.assertGreater(before, self.target.hp)

    def test_actual_team_trainers_and_pokemon_read_one_record_and_opponent_does_not(self):
        for role, face, expected in (('ally', 13, False), ('ally', 14, True),
                ('p', 14, True), ('a', 14, True), ('enemy', 14, False), ('enemy', 17, True)):
            with self.subTest(role=role, face=face):
                self.setUp(); self.observe()
                self.assertEqual(sum(len(PLEDGE.live(owner)) for owner in self.e.gm.everyone), 1)
                self.assertEqual(PLEDGE.live(self.a)[0][PLEDGE.KEY]['side'], 'party')
                self.attack(getattr(self, role), '전기쇼크', face)
                self.assertEqual('마비' in self.target.conditions, expected)

    def test_fifth_actual_round_ends_only_rainbow_and_replay_cannot_restart_it(self):
        self.observe('move/물의맹세')
        GRANTS.apply_owned(self.e, self.ally, 'fixture:independent-effect-range',
            lambda: self.ally.modifiers.append({'type': 'effect_range_mod', 'value': 1}))
        self.assertEqual(PRECISION.effect_natural(self.e, self.ally, self.r.move('move/전기쇼크'), 14), 18)
        for round_no in range(1, 6):
            self.assertEqual(self.e.round_no, round_no)
            self.assertEqual(PLEDGE.effect_range_bonus(self.e, self.ally, self.r.move('move/전기쇼크')), 3)
            self.e.end_round()
            if round_no < 5:
                self.e.start_round(self.e.gm.everyone)
        self.assertFalse(PLEDGE.live(self.a))
        self.assertEqual(PRECISION.effect_natural(self.e, self.ally, self.r.move('move/전기쇼크'), 14), 15)
        history = self.a.custom_conditions['effect_lifetime_history'][-1]
        self.assertEqual(history['event']['kind'], 'round_end')
        before = self.snap(); self.observe('move/물의맹세'); self.assertEqual(before, self.snap())
        self.assertFalse(PLEDGE.live(self.a))

    def test_actual_scope_restore_and_new_team_member_keep_original_lifetime(self):
        receipt = self.observe(); self.e.end_round(); self.e.start_round(self.e.gm.everyone)
        snapshot = self.e.gm.snapshot(); self.e.gm.restore(snapshot)
        self.e = CODEC.load_engine(self.r, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        index = WORLD.actor_index(self.e)
        self.a, self.ally, self.p = [index[actor.entity_id] for actor in (self.a, self.ally, self.p)]
        self.assertEqual(PLEDGE.live(self.a)[0]['effect_occurrence'], receipt['occurrence'])
        self.assertEqual(PLEDGE.live(self.a)[0]['lifetime_policy']['started_round'], 1)
        before = self.snap(); self.observe(); self.assertEqual(before, self.snap())
        self.ally.side = 'wild'
        self.assertEqual(PLEDGE.effect_range_bonus(self.e, self.ally, self.r.move('move/전기쇼크')), 0)
        newcomer = Combatant(self.e.r, build_trainer(self.e.r, 'New actual ally', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20)))
        self.e.gm.add_combatant(newcomer, side='party', pos=(0, 1), reason='actual new team membership')
        self.assertEqual(PLEDGE.effect_range_bonus(self.e, newcomer, self.r.move('move/전기쇼크')), 3)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_wrong_source_changed_request_and_overlap_refuse_without_mutation(self):
        for source in ('move/풀의맹세', 'gm/fictional-rainbow'):
            with self.subTest(source=source):
                before = self.snap()
                with self.assertRaisesRegex(ValueError, 'source'):
                    self.observe(source)
                self.assertEqual(before, self.snap())
        self.observe()
        for source, request in (('move/물의맹세', 'observed-rainbow'),
                ('move/물의맹세', 'overlapping-rainbow')):
            with self.subTest(source=source, request=request):
                before = self.snap()
                with self.assertRaises(ValueError):
                    self.observe(source, request)
                self.assertEqual(before, self.snap())

    def test_expanded_secondary_threshold_does_not_change_actual_accuracy_or_critical(self):
        costs = deepcopy((getattr(self.a, 'budget', None), self.a.move_uses))
        self.observe()
        move = self.r.move('move/전기쇼크')
        self.assertEqual(PRECISION.effect_natural(self.e, self.ally, move, 17), 20)
        self.assertEqual(self.e.accuracy_check(self.ally, self.target, move, fixed_roll=17), (True, 17, False))
        self.assertEqual(self.e.accuracy_check(self.ally, self.target, move, fixed_roll=1), (False, 1, False))
        self.assertIsNone(PRECISION.effect_natural(self.e, self.ally, move, None))
        self.assertEqual((getattr(self.a, 'budget', None), self.a.move_uses), costs)


if __name__ == '__main__':
    unittest.main()
