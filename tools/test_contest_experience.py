"""S-002 completed-result quotes and actual native XP settlement boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Engine, Combatant
from contest import ContestEngine
from builder import build_pokemon, build_trainer
import contest_experience as XP
import downtime as DT
import state_codec as CODEC
from native_rule_policy import PolicyPending
import test_core_contest_hall_rewards as HALL_FIX


class Pause(Exception):
    pass


class ContestExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HALL_FIX.Tests.setUpClass.__func__(cls)

    def fixture(self, *, levels=(10,)*5, scores=None, paired=False):
        native, host = Engine(self.nr, seed=851), ContestEngine(self.cr, seed=852)
        cs, pokemon = [], []
        ring = self.cr.mech('contest/type-match')['ring']
        for i, level in enumerate(levels):
            trainer = Combatant(self.nr, build_trainer(self.nr, 'trainer '+str(i), 20,
                dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
                moves=list(self.safe), skills={'매력': 2}, extra={'items': {}, 'edges': []}))
            p = Combatant(self.nr, build_pokemon(self.nr, '잉어킹', level,
                name='pokemon '+str(i), moves=list(self.safe), abilities=[],
                extra={'trainer_id': trainer.entity_id}))
            for actor in (trainer, p):
                native.gm.add_combatant(actor, pos=(i, 0), side='party', reason='actual Contest entrants')
            c = host.contestant_from_combatants(native, p, trainer, '매력', dict.fromkeys(ring, 24))
            c.appeal = (len(levels)-i)*1000 if scores is None else scores[i]
            if paired:
                host.trainer_participant(c)
            cs.append(c)
            pokemon.append(p)
        return host, cs, native, pokemon

    def choose(self, actor, rnd, adjacent, center):
        return self.safe[1 if actor.last_move == self.safe[0] else 0], 0

    def play(self, host, cs, *, variant='standard', chooser=None, **kw):
        # Fixed legal faces, not a forged completed-result record. All turns run.
        with patch.object(ContestEngine, 'd6', lambda _, n: [1]*n):
            return host.run(cs, self.topic, chooser or self.choose,
                            variant=variant, contest_id='xp/actual', **kw)

    def world(self, native):
        return json.loads(json.dumps(CODEC.dump_engine(native), ensure_ascii=False))

    def test_literal_five_contestants_first40_last0_and_odd_counts(self):
        host, cs, native, pokemon = self.fixture()
        self.play(host, cs)
        before = self.world(native)
        quotes = [host.experience_quote(c) for c in cs]
        self.assertEqual([len(q['defeated_ids']) for q in quotes], [4, 3, 2, 1, 0])
        self.assertEqual([q['half_count'] for q in quotes], [2, 2, 1, 1, 0])
        self.assertEqual([q['amount'] for q in quotes], [40, 40, 20, 20, 0])
        self.assertEqual(self.world(native), before)
        for c, p, q in zip(cs, pokemon, quotes):
            self.assertEqual(q['decision'], 'S-002')
            self.assertNotIn(p.entity_id, q['defeated_ids'])
            self.assertNotIn(XP.KEY, p.spec)

    def test_equal_rank_is_not_beaten_or_a_list_order_bonus(self):
        host, cs, _, _ = self.fixture(scores=[3000, 3000, 2000, 2000, 0])
        self.play(host, cs)
        quotes = [host.experience_quote(c) for c in cs]
        self.assertEqual([len(q['defeated_ids']) for q in quotes], [3, 3, 1, 1, 0])
        self.assertEqual([q['amount'] for q in quotes], [40, 40, 20, 20, 0])

    def test_only_half_count_rounds_up_and_final_fraction_rounds_down(self):
        host, cs, _, _ = self.fixture(levels=(9, 9, 9))
        self.play(host, cs)
        q = host.experience_quote(cs[0], significance='1.5')
        self.assertEqual((len(q['defeated_ids']), q['half_count'], q['amount']), (2, 1, 13))
        self.assertEqual(host.experience_quote(cs[1], significance='1.5')['amount'], 13)

    def test_award_updates_actual_native_xp_level_stats_and_hp_through_growth_owner(self):
        host, cs, native, pokemon = self.fixture()
        self.play(host, cs)
        recipient = pokemon[0]
        expected_world = CODEC.load_engine(self.nr, self.world(native))
        expected = next(c for c in expected_world.gm.everyone if c.entity_id == recipient.entity_id)
        DT.gain_exp_combatant(expected_world, expected, 40)
        before = recipient.spec['exp']
        receipt = host.award_experience(cs[0])
        self.assertEqual(recipient.spec['exp'], before+40)
        self.assertEqual((receipt['amount'], receipt['exp_before'], receipt['exp_after']), (40, before, before+40))
        self.assertEqual((recipient.level, recipient.stats, recipient.hp), (expected.level, expected.stats, expected.hp))
        actual = deepcopy(recipient.spec)
        actual.pop(XP.KEY)
        self.assertEqual(actual, expected.spec)
        self.assertEqual(len(recipient.spec[XP.KEY]), 1)
        self.assertTrue(all(XP.KEY not in p.spec for p in pokemon[1:]))

    def test_zero_is_a_real_once_only_receipt_without_growth_or_fabricated_xp(self):
        host, cs, native, pokemon = self.fixture()
        self.play(host, cs)
        p = pokemon[-1]
        before = deepcopy((p.spec, p.stats, p.hp, p.level))
        with patch.object(DT, '_gain_exp_combatant', side_effect=AssertionError('zero must not invoke growth')):
            receipt = host.award_experience(cs[-1])
        self.assertEqual(receipt['amount'], 0)
        actual = deepcopy(p.spec)
        actual.pop(XP.KEY)
        self.assertEqual((actual, p.stats, p.hp, p.level), before)
        saved = self.world(native)
        with self.assertRaisesRegex(ValueError, 'already awarded'):
            host.award_experience(cs[-1])
        self.assertEqual(self.world(native), saved)

    def test_cold_contest_restore_keeps_actual_award_and_blocks_repeat(self):
        host, cs, _, pokemon = self.fixture()
        self.play(host, cs)
        receipt = host.award_experience(cs[0])
        payload = json.loads(json.dumps(CODEC.dump_contest(host, cs), ensure_ascii=False))
        restored, actors = CODEC.load_contest(self.cr, payload, native_rules=self.nr)
        actor = next(c for c in actors if c.entity_id == cs[0].entity_id)
        native, p, _, _, _ = restored._native_intro_bindings[actor]
        self.assertEqual(p.spec[XP.KEY][receipt['id']], receipt)
        self.assertEqual(p.spec['exp'], pokemon[0].spec['exp'])
        before = self.world(native)
        with self.assertRaisesRegex(ValueError, 'already awarded'):
            restored.award_experience(actor, significance=3)
        self.assertEqual(self.world(native), before)

    def test_actual_growth_failure_keeps_world_choices_and_receipt_atomic(self):
        host, cs, native, pokemon = self.fixture()
        self.play(host, cs)
        for choices in ({pokemon[0].level+1: 'not-a-stat'},):
            before, original = self.world(native), deepcopy(choices)
            with self.assertRaisesRegex(ValueError, 'unknown stat choice'):
                host.award_experience(cs[0], stat_choices=choices)
            self.assertEqual(self.world(native), before)
            self.assertEqual(choices, original)
        pokemon[0].spec.pop('exp')
        before = self.world(native)
        with self.assertRaisesRegex(ValueError, 'XP is unknown'):
            host.award_experience(cs[0])
        self.assertEqual(self.world(native), before)
        self.assertNotIn(XP.KEY, pokemon[0].spec)

    def test_incomplete_foreign_and_invalid_factor_refusals_do_not_pay(self):
        host, cs, native, _ = self.fixture()
        before = self.world(native)
        with self.assertRaisesRegex(ValueError, 'completed native'):
            host.award_experience(cs[0])
        self.assertEqual(self.world(native), before)
        self.play(host, cs)
        foreign = self.fixture()[1][0]
        for factor in (0, -1, True, float('nan'), float('inf')):
            before = self.world(native)
            with self.assertRaises(ValueError):
                host.award_experience(cs[0], significance=factor)
            self.assertEqual(self.world(native), before)
        with self.assertRaisesRegex(ValueError, 'actual Pokemon participant'):
            host.award_experience(foreign)

    def test_festival_uses_whole_actual_aggregate_and_not_completed_children(self):
        host, cs, native, pokemon = self.fixture()
        initial = [p.spec['exp'] for p in pokemon]
        def pause_on_second(actor, rnd, adjacent, center):
            if host._festival_run['history']:
                raise Pause()
            return self.choose(actor, rnd, adjacent, center)
        with self.assertRaises(Pause):
            self.play(host, cs, variant='festival', chooser=pause_on_second)
        self.assertEqual(len(host._festival_run['history']), 1)
        before = self.world(native)
        with self.assertRaisesRegex(ValueError, 'whole Festival'):
            host.award_experience(cs[0])
        self.assertEqual(self.world(native), before)
        self.play(host, cs, variant='festival')
        state = host._festival_run
        self.assertEqual(state['phase'], 'complete')
        self.assertEqual(len(state['history']), 3)
        self.assertEqual([p.spec['exp'] for p in pokemon], initial)
        self.assertTrue(all(XP.KEY not in p.spec for p in pokemon))
        self.assertEqual([host.experience_quote(c)['amount'] for c in cs], [40, 40, 20, 20, 0])
        receipt = host.award_experience(cs[0])
        self.assertEqual((receipt['event']['format'], receipt['event']['contest_id'], receipt['amount']),
                         ('festival', 'xp/actual', 40))
        self.assertEqual(pokemon[0].spec['exp'], initial[0]+40)
        self.assertEqual(len(pokemon[0].spec[XP.KEY]), 1)

    def test_festival_tie_pending_is_not_an_xp_result_or_implicit_choice(self):
        host, cs, native, pokemon = self.fixture(scores=[0]*5)
        with self.assertRaises(PolicyPending):
            self.play(host, cs, variant='festival')
        before = self.world(native)
        with self.assertRaisesRegex(ValueError, 'whole Festival'):
            host.award_experience(cs[0])
        self.assertEqual(self.world(native), before)
        self.assertTrue(all(XP.KEY not in p.spec for p in pokemon))

    def test_festival_scoped_tiebreak_sets_actual_placing_but_remaining_ties_stay_tied(self):
        host, cs, _, pokemon = self.fixture(levels=(10,)*4, scores=[0]*4)
        decisions = {}
        for _ in range(3):
            try:
                self.play(host, cs, variant='festival', festival_decisions=decisions)
                break
            except PolicyPending as pending:
                ask = pending.obligations[0]
                decisions[ask['key']] = {'value': ask['choices'][-1], 'scope': ask['scope'],
                                         'reason': 'actual explicit Festival tie adjudication'}
        else:
            self.fail('two native tie decisions should complete this four-person Festival')
        state = host._festival_run
        winner, eliminated = state['winner'], state['eliminated'][0]
        self.assertEqual(len(decisions), 2)
        self.assertEqual(len(set(state['history'][-1]['scores'].values())), 1)
        self.assertEqual(host.experience_quote(winner)['amount'], 40)
        self.assertEqual(host.experience_quote(eliminated)['amount'], 0)
        remaining = [c for c in state['result'] if c is not winner]
        for c in remaining:
            self.assertEqual(host.experience_quote(c)['defeated_ids'],
                             [host._native_intro_bindings[eliminated][1].entity_id])
            self.assertEqual(host.experience_quote(c)['amount'], 20)
        actual = host._native_intro_bindings[winner][1]
        before = actual.spec['exp']
        self.assertEqual(host.award_experience(winner)['amount'], 40)
        self.assertEqual(actual.spec['exp'], before+40)
        self.assertTrue(all(XP.KEY not in p.spec for p in pokemon if p is not actual))

    def test_paired_result_counts_pokemon_opponents_not_trainers(self):
        host, cs, _, _ = self.fixture(levels=(10,)*3, paired=True)
        self.play(host, cs, trainer_model='simultaneous',
                  trainer_order=lambda c, t, rnd: [c, t])
        self.assertEqual([len(host.experience_quote(c)['defeated_ids']) for c in cs], [2, 1, 0])
        self.assertEqual([host.experience_quote(c)['amount'] for c in cs], [20, 20, 0])

    def test_rotation_team_outcome_excludes_teammates_and_includes_actual_opponents(self):
        fixture = HALL_FIX.modes_fixture.RotationNativeBoundaryTests()
        fixture.rules, fixture.contest_rules = self.nr, self.cr
        native, host, teams, reps = fixture.fixture()
        HALL_FIX.Tests.prepare(self, host, [c for team in teams for c in team])
        for i, team in enumerate(teams):
            for c in team:
                c.appeal = (3-i)*1000
        with patch.object(ContestEngine, 'd6', lambda _, n: [1]*n):
            host.run_rotation(teams, self.topic, self.choose, representatives=reps,
                performer_selector=lambda rep, rnd, available: available[0], contest_id='xp/rotation')
        q = host.experience_quote(teams[0][2])
        self.assertEqual((len(q['defeated_ids']), q['amount']), (6, 180))
        own = {host._native_intro_bindings[c][1].entity_id for c in teams[0]}
        self.assertTrue(own.isdisjoint(q['defeated_ids']))
        self.assertEqual(host.experience_quote(teams[-1][0])['amount'], 0)
        self.assertTrue(all(XP.KEY not in c.spec for c in native.gm.everyone))

    def rebind(self, original, contestants):
        """A fresh public event declaration for the same actual registered actors."""
        host, actors = ContestEngine(self.cr, seed=862), []
        ring = self.cr.mech('contest/type-match')['ring']
        for i, c in enumerate(contestants):
            native, pokemon, trainer, skill, _ = original._native_intro_bindings[c]
            fresh = host.contestant_from_combatants(native, pokemon, trainer, skill,
                                                   dict.fromkeys(ring, 24))
            fresh.appeal = (len(contestants)-i)*1000
            actors.append(fresh)
        return host, actors

    def play_occurrence(self, host, cs, occurrence=None):
        options = {} if occurrence is None else {'contest_id': occurrence}
        with patch.object(ContestEngine, 'd6', lambda _, n: [1]*n):
            return host.run(cs, self.topic, self.choose, **options)

    def test_terminal_tie_partition_survives_public_practice_and_both_restores(self):
        host, cs, native, pokemon = self.fixture(levels=(10,)*3, scores=[1000, 0, 0])
        self.play(host, cs)
        self.assertEqual(host.experience_quote(cs[1])['amount'], 0)
        terminal = deepcopy(host.last_standings)
        frozen = tuple(host._standard_run['terminal_scores'])
        host.snapshot('actual terminal tie')
        # This ordinary public practice splits the live second/third-place tie
        # without changing result order or the unique winner. It remains legal.
        move = self.safe[1 if cs[1].last_move == self.safe[0] else 0]
        with patch.object(ContestEngine, 'd6', lambda _, n: [5]*n):
            host.perform(cs[1], move, self.topic, [], False, spend_stat_dice=0)
        self.assertGreater(cs[1].appeal-cs[1].fumble, cs[2].appeal-cs[2].fumble)
        self.assertEqual(host._standard_run['result'], tuple(cs))
        self.assertEqual(host.last_standings, terminal)
        self.assertEqual(host._standard_run['terminal_scores'], frozen)
        self.assertEqual(host.experience_quote(cs[1])['defeated_ids'], [])
        payload = json.loads(json.dumps(CODEC.dump_contest(host, cs), ensure_ascii=False))
        restored, actors = CODEC.load_contest(self.cr, payload, native_rules=self.nr)
        actor = next(c for c in actors if c.entity_id == cs[1].entity_id)
        p = restored._native_intro_bindings[actor][1]
        before = p.spec['exp']
        self.assertEqual(restored.experience_quote(actor)['amount'], 0)
        self.assertEqual(restored.award_experience(actor)['amount'], 0)
        self.assertEqual(p.spec['exp'], before)
        host.restore('actual terminal tie', reason='actual terminal outcome snapshot')
        self.assertEqual(host.experience_quote(cs[1])['amount'], 0)
        before = pokemon[1].spec['exp']
        self.assertEqual(host.award_experience(cs[1])['amount'], 0)
        self.assertEqual(pokemon[1].spec['exp'], before)

    def test_fresh_implicit_events_and_explicit_new_event_each_pay_same_native_roster(self):
        host, cs, native, pokemon = self.fixture(levels=(10,)*3)
        ids = []
        for occurrence in (None, None, 'xp/explicit-new'):
            self.play_occurrence(host, cs, occurrence)
            identity = host._standard_run['id']
            self.assertNotIn(identity, ids)
            ids.append(identity)
            amount = host.experience_quote(cs[0])['amount']
            before = pokemon[0].spec['exp']
            self.assertEqual(host.award_experience(cs[0])['amount'], amount)
            self.assertEqual(pokemon[0].spec['exp'], before+amount)
            host, cs = self.rebind(host, cs)
        self.assertNotEqual(ids[0], 'standard-contest:1')
        self.assertEqual(len(pokemon[0].spec[XP.KEY]), 3)
        # Complete another fresh omitted-ID event and prove its identity survives
        # real JSON restore before the single permitted payment.
        self.play_occurrence(host, cs)
        identity = host._standard_run['id']
        payload = json.loads(json.dumps(CODEC.dump_contest(host, cs), ensure_ascii=False))
        restored, actors = CODEC.load_contest(self.cr, payload, native_rules=self.nr)
        actor = next(c for c in actors if c.entity_id == cs[0].entity_id)
        self.assertEqual(restored._standard_run['id'], identity)
        amount = restored.experience_quote(actor)['amount']
        self.assertEqual(restored.award_experience(actor)['amount'], amount)
        current = restored._native_intro_bindings[actor][0]
        before = self.world(current)
        with self.assertRaisesRegex(ValueError, 'already awarded'):
            restored.award_experience(actor)
        self.assertEqual(self.world(current), before)

    def test_explicit_event_reconstruction_and_changed_roster_cannot_reset_paid_receipt(self):
        host, cs, native, pokemon = self.fixture(levels=(10,)*4)
        self.play_occurrence(host, cs[:3], 'xp/same-actual-event')
        host.award_experience(cs[0])
        for participants in (cs[:3], [cs[0], cs[1], cs[3]]):
            replay, actors = self.rebind(host, participants)
            self.play_occurrence(replay, actors, 'xp/same-actual-event')
            before = self.world(native)
            with self.assertRaisesRegex(ValueError, 'already awarded'):
                replay.award_experience(actors[0])
            self.assertEqual(self.world(native), before)
        self.assertEqual(len(pokemon[0].spec[XP.KEY]), 1)


if __name__ == '__main__':
    unittest.main()
