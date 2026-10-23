"""C07-192 through the actual Full-action attack and current native target."""
from copy import deepcopy
from pathlib import Path
import sys, unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_team_blessings as fixture
import test_category2_move_defense_reactions as defense_fixture
import blessing_effects as B
import combat_damage as DAMAGE
import attack_damage_history as HISTORY
import coup_de_grace as COUP
import turn as TURN
import world_entities as WORLD
from grid import Grid


class CoupDeGraceTests(unittest.TestCase):
    setUpClass = classmethod(fixture.TeamBlessingTests.setUpClass.__func__)
    add = fixture.TeamBlessingTests.add
    known = fixture.TeamBlessingTests.known
    begin = fixture.TeamBlessingTests.begin
    snap = fixture.TeamBlessingTests.snap
    valid = fixture.TeamBlessingTests.valid
    restored = fixture.TeamBlessingTests.restored

    def setUp(self):
        fixture.TeamBlessingTests.setUp(self)
        self.known(self.a, '물대포')

    def bound(self, target=None, *, properly_bound=True, completely_helpless=True):
        return self.e.gm.observe_coup_de_grace_target(
            target or self.p, properly_bound=properly_bound,
            completely_helpless=completely_helpless,
            source='gm/current-rope-binding', reason='GM checked the current physical restraints')

    def attack(self, *, actor=None, target=None, roll=18):
        with patch.object(self.e, 'd20', return_value=roll):
            return self.e.coup_de_grace(actor or self.other, target or self.p,
                                       'move/물대포', set_damage=True)

    def test_sleep_paralysis_and_other_conditions_alone_never_authorize_the_attack(self):
        for condition in ('잠듦', '마비', '풀죽음', '넘어짐'):
            with self.subTest(condition=condition):
                self.setUp()
                self.begin(self.other)
                self.e.gm.add_condition(self.p, condition, reason='actual condition only')
                before = self.snap()
                with self.assertRaisesRegex(ValueError, 'fainted or properly bound'):
                    self.attack()
                self.assertEqual(self.snap(), before)

    def test_native_faint_including_positive_hp_waiting_for_recovery_is_eligible(self):
        self.e.gm.set_hp(self.p, value=0, reason='actual knockout')
        self.e.heal(self.p, 10, source_kind='ordinary_item')
        self.assertGreater(self.p.hp, 0)
        self.assertTrue(self.p.fainted)
        self.begin(self.other)
        hp = self.p.hp
        damage = self.attack()
        self.assertGreater(damage, 0)
        self.assertLess(self.p.hp, hp)
        self.assertEqual(self.other.budget['standard'], 0)
        self.assertEqual(self.other.budget['shift'], 0)
        self.valid()

    def test_actual_revive_removes_fainted_eligibility_before_any_cost(self):
        self.e.gm.set_hp(self.p, value=0, reason='actual knockout')
        self.assertTrue(self.e.revive(self.p, 20))
        self.assertFalse(self.p.fainted)
        self.begin(self.other)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'fainted or properly bound'):
            self.attack()
        self.assertEqual(self.snap(), before)

    def test_bound_and_completely_helpless_are_both_required_and_release_is_live(self):
        for bound, helpless in ((False, False), (True, False), (False, True)):
            with self.subTest(bound=bound, helpless=helpless):
                self.setUp()
                self.bound(properly_bound=bound, completely_helpless=helpless)
                self.begin(self.other)
                before = self.snap()
                with self.assertRaisesRegex(ValueError, 'fainted or properly bound'):
                    self.attack()
                self.assertEqual(self.snap(), before)
        self.setUp()
        self.bound()
        self.assertFalse(TURN.can_act(self.e, self.p))
        self.bound(properly_bound=False, completely_helpless=False)
        self.assertTrue(TURN.can_act(self.e, self.p))
        self.begin(self.other)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'fainted or properly bound'):
            self.attack()
        self.assertEqual(self.snap(), before)

    def test_actual_bound_target_cannot_take_an_attack_or_opportunity_attack(self):
        self.known(self.p, '물대포')
        self.bound()
        self.begin(self.p)
        budget = deepcopy(self.p.budget)
        hp = self.other.hp
        self.assertEqual(self.e.use_move(self.p, self.other, 'move/물대포'), 0)
        self.assertEqual(self.p.budget, budget)
        self.assertEqual(self.other.hp, hp)
        self.assertFalse(TURN.can_aoo(self.e, self.p))

    def test_both_actor_kinds_pay_full_and_one_frequency_for_a_real_critical_plus_ten(self):
        for name in ('a', 'other'):
            with self.subTest(actor=name):
                self.setUp()
                actor = getattr(self, name)
                self.bound()
                expected = self.e.roll_damage(actor, self.p, self.r.move('move/물대포'),
                                              crit=True, set_damage=True) + 10
                self.begin(actor)
                hp = self.p.hp
                history_before = len(HISTORY.records(self.p))
                completion_ids = set(getattr(self.e, '_move_completions', {}))
                damage = self.attack(actor=actor)
                self.assertEqual(damage, expected)
                receipts = HISTORY.records(self.p)[history_before:]
                self.assertEqual(len(receipts), 1)
                receipt = receipts[0]['receipt']
                self.assertEqual((receipt['requested'], receipt['net_hp_loss']), (damage, damage))
                completions = [row for token, row in self.e._move_completions.items()
                               if token not in completion_ids]
                self.assertEqual(len(completions), 1)
                row = completions[0]
                self.assertIs(row['actor'], actor)
                self.assertEqual((row['targets'], row['phase']), ([self.p], 'complete'))
                self.assertEqual(row['results'], {self.p.entity_id: dict(hit=True, dealt=damage, cancelled=False)})
                self.assertEqual(self.p.hp, hp - damage)
                self.assertEqual((actor.budget['standard'], actor.budget['shift']), (0, 0))
                self.assertEqual(actor.move_uses['move/물대포'], 1)
                self.valid()

    def test_full_action_without_shift_does_not_spend_standard_frequency_or_damage(self):
        self.bound()
        self.begin(self.other)
        self.other.budget['shift'] = 0
        before = (deepcopy(self.other.budget), deepcopy(self.other.move_uses), self.p.hp,
                  self.e.rng.getstate())
        self.assertEqual(self.attack(), 0)
        self.assertEqual((self.other.budget, self.other.move_uses, self.p.hp,
                          self.e.rng.getstate()), before)

    def test_miss_pays_full_and_frequency_without_automatic_hit_or_damage(self):
        self.bound()
        self.begin(self.other)
        hp = self.p.hp
        with patch.object(DAMAGE, 'application', wraps=DAMAGE.application) as applied:
            self.assertEqual(self.attack(roll=1), 0)
        self.assertEqual(applied.call_count, 0)
        self.assertEqual(self.p.hp, hp)
        self.assertEqual((self.other.budget['standard'], self.other.budget['shift']), (0, 0))
        self.assertEqual(self.other.move_uses['move/물대포'], 1)

    def test_actual_lucky_chant_cannot_cancel_or_be_spent_by_the_forced_critical(self):
        self.known(self.p, '주술')
        self.begin(self.p)
        self.e.use_move(self.p, self.p, 'move/주술')
        guard = next(row for row in B.live(self.p) if row['source'] == 'move/주술')
        remaining = B.remaining(guard)
        self.e.rulings.add_answer('team_blessing', True, reason='beneficiary would use the guard')
        self.bound()
        expected = self.e.roll_damage(self.other, self.p, self.r.move('move/물대포'),
                                     crit=True, set_damage=True) + 10
        self.begin(self.other)
        self.assertEqual(self.attack(), expected)
        self.assertEqual(B.remaining(guard), remaining)
        self.assertFalse(guard['decisions'])
        self.valid()

    def test_ordinary_attack_retains_standard_cost_and_normal_critical_rules(self):
        self.bound()
        expected = self.e.roll_damage(self.other, self.p, self.r.move('move/물대포'),
                                     crit=False, set_damage=True)
        self.begin(self.other)
        with patch.object(self.e, 'd20', return_value=18):
            damage = self.e.use_move(self.other, self.p, 'move/물대포', set_damage=True)
        self.assertEqual(damage, expected)
        self.assertEqual((self.other.budget['standard'], self.other.budget['shift']), (0, 1))

    def test_no_cost_bypass_or_composite_target_list_can_enter_coup_de_grace(self):
        self.bound()
        self.begin(self.other)
        for options in ({'count_use': False}, {'free_action': True},
                        {'_shared_accuracy': {'targets': (self.p, self.a)}},
                        {'coup_de_grace': 'yes'}):
            with self.subTest(options=options):
                before = self.snap()
                arguments = dict(coup_de_grace=True, **{k: v for k, v in options.items()
                                                        if k != 'coup_de_grace'})
                if 'coup_de_grace' in options:
                    arguments['coup_de_grace'] = options['coup_de_grace']
                with self.assertRaises(ValueError):
                    self.e.use_move(self.other, self.p, 'move/물대포', **arguments)
                self.assertEqual(self.snap(), before)

    def test_unsupported_area_status_and_deferred_attacks_are_explicit_before_cost(self):
        self.known(self.other, '지진', '칼춤', '솔라빔')
        self.bound()
        self.begin(self.other)
        for name in ('지진', '칼춤', '솔라빔'):
            with self.subTest(move=name):
                before = self.snap()
                error = ('self move requires the user target' if name == '칼춤'
                         else 'direct single-target damaging Standard')
                with self.assertRaisesRegex(ValueError, error):
                    self.e.coup_de_grace(self.other, self.p, 'move/' + name)
                self.assertEqual(self.snap(), before)

    def test_native_range_and_actual_registered_target_remain_required(self):
        self.bound()
        self.begin(self.other)
        outsider = deepcopy(self.p)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'distinct actors share identity'):
            self.e.coup_de_grace(self.other, outsider, 'move/물대포')
        self.assertEqual(self.snap(), before)
        with self.assertRaisesRegex(ValueError, 'actual registered'):
            self.bound(outsider)
        self.assertEqual(self.snap(), before)
        self.known(self.other, '몸통박치기')
        self.e.grid = Grid(20, 20)
        self.p.pos = (10, 10)
        hp = self.p.hp
        budget = deepcopy(self.other.budget)
        self.assertEqual(self.e.coup_de_grace(self.other, self.p, 'move/몸통박치기'), 0)
        self.assertEqual((self.other.budget, self.p.hp), (budget, hp))

    def test_invalid_current_gm_observation_or_wrong_actor_binding_never_authorizes(self):
        for options in ({'source': ''}, {'reason': ''}, {'properly_bound': 1},
                        {'completely_helpless': None}):
            with self.subTest(options=options):
                observation = dict(source='gm/rope', reason='current restraint',
                                   properly_bound=True, completely_helpless=True)
                observation.update(options)
                before = self.snap()
                with self.assertRaises(ValueError):
                    self.e.gm.observe_coup_de_grace_target(self.p, **observation)
                self.assertEqual(self.snap(), before)
        self.bound()
        self.a.custom_conditions[COUP.BINDING] = deepcopy(self.p.custom_conditions[COUP.BINDING])
        self.begin(self.other)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.attack(target=self.a)
        self.assertEqual(self.snap(), before)

    def test_actual_late_damage_failure_rolls_back_hp_action_frequency_rng_and_log(self):
        self.bound()
        self.begin(self.other)
        before = self.snap()
        target_state = self.p.custom_conditions
        with patch.object(DAMAGE, 'application', side_effect=ValueError('late damage receipt failure')):
            with self.assertRaisesRegex(ValueError, 'late damage receipt'):
                self.attack()
        self.assertEqual(self.snap(), before)
        self.assertIs(self.p.custom_conditions, target_state)

    def test_crafted_or_completed_marker_cannot_replace_the_native_producer(self):
        self.bound()
        self.begin(self.other)
        move = dict(self.r.move('move/물대포'), **{COUP.MARKER: dict(
            source=COUP.SOURCE, actor_id=self.other.entity_id,
            target_id=self.p.entity_id, move_id='move/물대포')})
        for completed in (False, True):
            with self.subTest(completed=completed):
                if completed:
                    self.attack()
                before = self.snap()
                with self.assertRaisesRegex(ValueError, 'actual started native'):
                    self.e.roll_damage(self.other, self.p, move, crit=True, set_damage=True)
                self.assertEqual(self.snap(), before)

    def test_actual_intercept_receives_the_original_attack_after_pending_cold_restore(self):
        f = defense_fixture.MoveDefenseReactionsTests()
        f.rules = self.r
        f.setUp()
        f.e.gm.observe_coup_de_grace_target(f.t, properly_bound=True,
            completely_helpless=True, source='gm/current-rope-binding', reason='actual original target binding')
        f.watch()
        before = f.e.export_state()
        with self.assertRaisesRegex(ValueError, 'actual available defense owner'):
            f.e.watch_move_defense(f.t, [{'actor_id': f.t.entity_id, 'source': 'move/판별'}],
                                  reason='bound target cannot take its own Detect reaction')
        self.assertEqual(f.e.export_state(), before)
        f.e.gm.observe_coup_de_grace_target(f.r, properly_bound=True,
            completely_helpless=True, source='gm/reactor-rope-binding', reason='actual reactor cannot act')
        before = f.e.export_state()
        with self.assertRaisesRegex(ValueError, 'actual available defense owner'):
            f.watch()
        self.assertEqual(f.e.export_state(), before)
        f.e.gm.observe_coup_de_grace_target(f.r, properly_bound=False,
            completely_helpless=False, source='gm/reactor-released', reason='reactor can now defend its ally')
        released_binding = deepcopy(f.r.custom_conditions[COUP.BINDING])
        hp = (f.t.hp, f.r.hp)
        expected = f.e.roll_damage(f.a, f.r, f.rules.move('move/막치기'),
                                  crit=True, set_damage=True) + 10
        with patch.object(f.e, 'd20', return_value=18):
            with self.assertRaises(defense_fixture.PASSIVE.PassiveEventPending):
                f.e.coup_de_grace(f.a, f.t, 'move/막치기', set_damage=True)
        event = f.e._passive_pending
        f.fresh()
        f.choose(event, options=f.melee())
        self.assertEqual((f.t.hp, f.r.hp), (hp[0], hp[1] - expected))
        self.assertEqual(f.a._action_history, ['full'])
        self.assertEqual(f.a.move_uses['move/막치기'], 1)
        self.assertEqual(f.r._action_history, ['full'])
        self.assertEqual(defense_fixture.RESOURCES.pending(f.r), {'standard': 1, 'shift': 1})
        row = f.completion()
        self.assertEqual(row['targets'], [f.t])
        self.assertEqual(row['move'][COUP.MARKER]['target_id'], f.t.entity_id)
        self.assertEqual(set(row['received']), {f.r.entity_id})
        self.assertTrue(row['received'][f.r.entity_id]['intercepted'])
        self.assertEqual(f.r.custom_conditions[COUP.BINDING], released_binding)
        self.assertFalse(COUP.bound(f.e, f.r))
        self.assertTrue(f.e.validate_state()['valid'])

    def test_json_restore_rebinds_current_target_and_consumes_the_same_native_path(self):
        self.bound()
        restored = self.restored()
        index = WORLD.actor_index(restored)
        attacker, target = index[self.other.entity_id], index[self.p.entity_id]
        self.assertEqual(target.custom_conditions[COUP.BINDING]['actor_id'], target.entity_id)
        restored.start_round(restored.gm.everyone)
        restored.start_of_turn(attacker, initiative_count=20)
        hp = target.hp
        with patch.object(restored, 'd20', return_value=18):
            damage = restored.coup_de_grace(attacker, target, 'move/물대포', set_damage=True)
        self.assertEqual(target.hp, hp - damage)
        self.assertEqual((attacker.budget['standard'], attacker.budget['shift']), (0, 0))
        self.assertTrue(restored.validate_state()['valid'])
        released = self.restored()
        index = WORLD.actor_index(released)
        attacker, target = index[self.other.entity_id], index[self.p.entity_id]
        released.gm.observe_coup_de_grace_target(target, properly_bound=False,
            completely_helpless=False, source='gm/restraints-removed', reason='actual release after reload')
        released.start_round(released.gm.everyone)
        released.start_of_turn(attacker, initiative_count=20)
        before = fixture.CODEC.dump_engine(released)
        with self.assertRaisesRegex(ValueError, 'fainted or properly bound'):
            released.coup_de_grace(attacker, target, 'move/물대포', set_damage=True)
        self.assertEqual(fixture.CODEC.dump_engine(released), before)

    def test_unreviewed_sniper_state_is_not_silently_given_the_core_bonus_policy(self):
        self.other.abilities.append('스나이퍼 [Playtest]')
        self.bound()
        self.begin(self.other)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'Sniper'):
            self.attack()
        self.assertEqual(self.snap(), before)


if __name__ == '__main__':
    unittest.main()
