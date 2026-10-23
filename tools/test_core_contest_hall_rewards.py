"""C08-001/002: new Hall entry and native winner-to-Trainer Ribbon boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path.insert(0, str(STAGE/'engine'))
sys.path.insert(1, str(ROOT/'engine'))
sys.path.insert(2, str(ROOT/'tools'))

# Load the selected staged owners before fixture modules prepend their own path.
import battle_contest as BATTLE
import contest_halls as HALLS
import state_codec as CODEC
import world_entities as WORLD
import pokemon_party as PARTY
import state_grants as GRANTS
from contest import ContestEngine
from gm_state import GMState
from native_rule_policy import PolicyPending
import test_category2_state_codec as codec_fixture
import test_category2_battle_contest as battle_fixture
import test_contest_modes19_edges as modes_fixture


class Pause(Exception):
    pass


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        codec_fixture.ContestStateCodecTests.setUpClass()
        cls.nr = cls.rules = codec_fixture.ContestStateCodecTests.nr
        cls.cr = cls.contest_rules = codec_fixture.ContestStateCodecTests.cr
        safe = []
        cls.reliable = None
        for move_id in cls.cr._moves:
            try:
                _, effect = cls.cr.move_contest(move_id)
            except (ValueError, KeyError):
                continue
            if effect == '안전한 선택':
                safe.append(move_id)
            if effect == '신뢰' and cls.reliable is None:
                cls.reliable = move_id
        assert cls.reliable is not None and len(safe) >= 2
        cls.safe = tuple(safe[:2])
        cls.topic = cls.cr.move_contest(cls.reliable)[0]

    def prepare(self, host, participants):
        # Change only fixture inputs; the real owner still performs every turn.
        for c in participants:
            _, pokemon, trainer, _, _ = host._native_intro_bindings[c]
            for actual in (pokemon, trainer):
                actual.moves = [self.reliable, *self.safe]
                actual.spec['moves'] = list(actual.moves)
            c.moves = list(pokemon.moves)
            c.stat_dice.update(dict.fromkeys(self.cr.mech('contest/type-match')['ring'], 24))
            partner = host._trainer_partners.get(c)
            if partner is not None:
                partner.moves = list(trainer.moves)

    def fixture(self, paired=False):
        result = codec_fixture.ContestStateCodecTests.fixture(self, paired=paired)
        self.prepare(result[0], result[1])
        return result

    def rotation(self, mode='team'):
        result = modes_fixture.RotationNativeBoundaryTests.fixture(self, mode=mode)
        self.prepare(result[1], [c for team in result[2] for c in team])
        return result

    def hall(self, host, native, types=None, identity='hall/actual'):
        WORLD.register_object(native, identity, location={'kind': 'unknown'},
                              reason='actual observed city Contest Hall')
        HALLS.observe_hall(host, native, identity,
                           self.cr.mech('contest/type-match')['ring'] if types is None else types,
                           reason='actual offered Contest types')
        return identity

    def chooser(self, host, winner, *, tied=False):
        winner_pair = {winner, host._trainer_partners.get(winner)}
        def choose(actor, round_number, adjacent, center):
            return ((self.safe[1 if actor.last_move == self.safe[0] else 0], 0) if tied else
                    (self.reliable, 2 if actor in winner_pair else 0))
        return choose

    def play(self, host, participants, *, variant='standard', mode=None, tied=False,
             hall_id=None, occurrence='reward/actual'):
        options = {'variant': variant, 'contest_id': occurrence}
        if hall_id is not None:
            options['hall_id'] = hall_id
        if mode is not None:
            options.update(trainer_model=mode, trainer_order=lambda c, t, rnd:
                           [c, t] if mode == 'simultaneous' else [c if rnd % 2 else t])
        with patch.object(ContestEngine, 'd6', lambda host, n: [1 if tied else 5]*n):
            return host.run(participants, None if variant == 'super' else self.topic,
                            self.chooser(host, participants[0], tied=tied), **options)

    def ribbons(self, native):
        return {uid: deepcopy(actor.spec[HALLS.KEY])
                for uid, actor in WORLD.actor_index(native).items()
                if actor.kind == 'trainer' and actor.spec.get(HALLS.KEY)}

    def assert_recipients(self, native, expected):
        awarded = self.ribbons(native)
        self.assertEqual(set(awarded), set(expected))
        self.assertTrue(all(len(records) == 1 for records in awarded.values()))
        if awarded:
            records = [next(iter(rows.values())) for rows in awarded.values()]
            self.assertTrue(all(row == records[0] for row in records))
            self.assertEqual(records[0]['winner_trainer_ids'], sorted(expected))
            self.assertEqual(records[0]['source'], HALLS.SOURCE)
        return awarded

    def assert_cold_contest_replay(self, host, participants, native):
        expected = self.ribbons(native)
        loaded, parts = CODEC.load_contest(self.cr,
            json.loads(json.dumps(CODEC.dump_contest(host, participants))), native_rules=self.nr)
        actual = loaded._native_intro_bindings[parts[0]][0]
        before = (list(actual.log_lines), list(loaded.log_lines), loaded.rng.getstate())
        HALLS.award_contest(loaded)
        HALLS.award_contest(loaded)
        self.assertEqual(before, (actual.log_lines, loaded.log_lines, loaded.rng.getstate()))
        self.assertEqual(self.ribbons(actual), expected)
        return actual

    @staticmethod
    def pause(*args):
        raise Pause()

    def test_all_five_observed_hall_types_start_the_actual_native_owner(self):
        for topic in self.cr.mech('contest/type-match')['ring']:
            with self.subTest(topic=topic):
                host, cs, native, _, _ = self.fixture()
                hall_id = self.hall(host, native)
                with self.assertRaises(Pause):
                    host.run(cs, topic, self.pause, hall_id=hall_id, contest_id='hall/'+topic)
                self.assertEqual(host._standard_run['contract'][1], topic)
                self.assertEqual(host._standard_run['hall']['id'], hall_id)
                self.assertTrue(all(c.intro_completed for c in cs))
                self.assertEqual(host._standard_run['phase'], 'perform')
                self.assertEqual(self.ribbons(native), {})

    def test_specialized_hall_rejects_other_type_before_intro_and_keeps_original_resume(self):
        host, cs, native, _, _ = self.fixture()
        ring = self.cr.mech('contest/type-match')['ring']
        hall_id = self.hall(host, native, ring[:2])
        before = (host.rng.getstate(), deepcopy([vars(c) for c in cs]))
        with self.assertRaises(ValueError):
            host.run(cs, ring[2], self.pause, hall_id=hall_id)
        self.assertIsNone(host._standard_run)
        self.assertEqual(before, (host.rng.getstate(), [vars(c) for c in cs]))
        with self.assertRaises(Pause):
            host.run(cs, ring[0], self.pause, hall_id=hall_id)
        other = self.hall(host, native, identity='hall/other')
        before = (host.rng.getstate(), len(host.log_lines))
        with self.assertRaises(ValueError):
            host.run(cs, ring[0], self.pause, hall_id=other)
        self.assertEqual(before, (host.rng.getstate(), len(host.log_lines)))

    def test_hall_observation_rejects_unknown_venue_empty_duplicate_and_non_source_types(self):
        host, _, native, _, _ = self.fixture()
        with self.assertRaises(ValueError):
            HALLS.observe_hall(host, native, 'hall/missing', [self.topic], reason='test')
        hall_id = self.hall(host, native)
        before = deepcopy(native._physical_objects[hall_id])
        for invalid in ([], [self.topic, self.topic], ['unknown'], '근사함', [True]):
            with self.subTest(types=invalid), self.assertRaises(ValueError):
                HALLS.observe_hall(host, native, hall_id, invalid, reason='invalid observation')
            self.assertEqual(native._physical_objects[hall_id], before)

    def test_hall_and_native_reward_source_gates_precede_observation_and_introduction(self):
        host, cs, native, _, _ = self.fixture()
        hall_id = self.hall(host, native)
        before = (deepcopy(native._physical_objects), host.rng.getstate())
        selected = native.r._selected_rule
        def replaced(uid, *args, **kw):
            return 'unsupported/circuit' if uid == HALLS.SOURCE else selected(uid, *args, **kw)
        with patch.object(native.r, '_selected_rule', replaced):
            with self.assertRaises(ValueError):
                HALLS.observe_hall(host, native, hall_id, [self.topic], reason='test')
            with self.assertRaises(ValueError):
                host.run(cs, self.topic, self.pause, hall_id=hall_id)
        self.assertIsNone(host._standard_run)
        self.assertEqual(before, (native._physical_objects, host.rng.getstate()))

    def test_standard_and_super_native_end_award_the_actual_winner_trainer(self):
        for variant in ('standard', 'super'):
            with self.subTest(variant=variant):
                host, cs, native, trainers, _ = self.fixture()
                with patch.object(host, 'perform', wraps=host.perform) as performed:
                    result = self.play(host, cs, variant=variant)
                self.assertEqual(performed.call_count, len(cs)*len(host._standard_run['table']['rounds']))
                self.assertIs(result[0], cs[0])
                self.assertEqual(host._standard_run['phase'], 'complete')
                self.assert_recipients(native, [trainers[0].entity_id])
                if variant == 'super':
                    self.assert_cold_contest_replay(host, cs, native)

    def test_both_native_trainer_participation_models_pay_the_pair_owner(self):
        for mode in ('simultaneous', 'alternating'):
            with self.subTest(mode=mode):
                host, cs, native, trainers, _ = self.fixture(paired=True)
                result = self.play(host, cs, mode=mode)
                self.assertIs(result[0], cs[0])
                self.assert_recipients(native, [trainers[0].entity_id])
                self.assertEqual(host._paired_run['phase'], 'complete')
                self.assert_cold_contest_replay(host, cs, native)

    def test_rotation_winning_team_pays_each_actual_trainer_once_and_solo_owner_once(self):
        for mode in ('solo', 'team'):
            with self.subTest(mode=mode):
                native, host, teams, reps = self.rotation(mode)
                winning = set(teams[0])
                with patch.object(ContestEngine, 'd6', lambda host, n: [5]*n):
                    result = host.run_rotation(teams, self.topic,
                        lambda c, rnd, adjacent, center: (self.reliable, 2 if c in winning else 0),
                        representatives=reps, orders=teams, contest_id='rotation/'+mode)
                self.assertIs(result[0], reps[0])
                owners = {host._native_intro_bindings[c][2].entity_id for c in winning}
                self.assertEqual(len(owners), 1 if mode == 'solo' else 3)
                self.assert_recipients(native, owners)
                self.assert_cold_contest_replay(host, [c for team in teams for c in team], native)

    def test_festival_child_never_pays_and_actual_final_winner_needs_no_five_ribbon_gate(self):
        native, host, teams, _ = self.rotation()
        cs = (teams[0][0], teams[0][1], teams[1][0], teams[2][0])
        self.assertEqual(self.ribbons(native), {})
        policy = dict(scope='festival/reward', reason='explicit test table resource interpretation',
                      introduction='repeat', stat_dice='reset', excitement='reset', last_move='reset')
        chooser = self.chooser(host, cs[0])
        observed_children = []
        actual_award = HALLS.award_contest
        def observe_award(actual_host):
            receipt = actual_award(actual_host)
            if actual_host is host and actual_host._festival_run['phase'] != 'complete':
                self.assertEqual(actual_host._standard_run['phase'], 'complete')
                self.assertIsNone(receipt)
                self.assertEqual(self.ribbons(native), {})
                observed_children.append(actual_host._standard_run['id'])
            return receipt
        with patch.object(ContestEngine, 'd6', lambda host, n: [5]*n), \
                patch.object(HALLS, 'award_contest', observe_award):
            result = host.run(cs, self.topic, chooser, variant='festival', contest_id='festival/reward',
                              festival_policy=policy)
        self.assertTrue(observed_children)
        self.assertIs(result[0], cs[0])
        winner = host._native_intro_bindings[cs[0]][2]
        self.assert_recipients(native, [winner.entity_id])
        self.assertEqual(host._festival_run['phase'], 'complete')
        self.assert_cold_contest_replay(host, cs, native)

    def test_festival_final_tie_waits_for_actual_scoped_GM_winner_and_replay_pays_once(self):
        host, cs, native, trainers, _ = self.fixture()
        policy = dict(scope='festival/tie', reason='explicit test table resource interpretation',
                      introduction='repeat', stat_dice='reset', excitement='reset', last_move='reset')
        with patch.object(ContestEngine, 'd6', lambda host, n: [1]*n):
            with self.assertRaises(PolicyPending) as pending:
                host.run(cs, self.topic, self.chooser(host, cs[0], tied=True), variant='festival',
                         contest_id='festival/tie', festival_policy=policy)
        self.assertEqual(self.ribbons(native), {})
        ask = pending.exception.obligations[0]
        self.assertEqual(ask['key'], '1:winner')
        decision = dict(value=cs[-1].entity_id, reason='actual final GM winner', scope=ask['scope'])
        before = len(host._performance_observations)
        options = dict(variant='festival', contest_id='festival/tie', festival_policy=policy,
                       festival_decisions={ask['key']: decision})
        result = host.run(cs, self.topic, self.pause, **options)
        self.assertIs(result[0], cs[-1])
        self.assertEqual(before, len(host._performance_observations))
        self.assert_recipients(native, [trainers[-1].entity_id])
        paid = self.ribbons(native)
        host.run(cs, self.topic, self.pause, **options)
        self.assertEqual(self.ribbons(native), paid)

    def test_unresolved_ties_in_standard_super_paired_and_rotation_never_pay(self):
        for variant, mode in (('standard', None), ('super', None),
                              ('standard', 'simultaneous'), ('standard', 'alternating')):
            with self.subTest(variant=variant, mode=mode):
                host, cs, native, _, _ = self.fixture(paired=mode is not None)
                self.play(host, cs, variant=variant, mode=mode, tied=True)
                self.assertIsNone(HALLS.award_contest(host))
                self.assertEqual(self.ribbons(native), {})
        native, host, teams, reps = self.rotation()
        with patch.object(ContestEngine, 'd6', lambda host, n: [1]*n):
            host.run_rotation(teams, self.topic,
                lambda c, rnd, adjacent, center: (self.safe[(rnd-1) % 2], 0),
                representatives=reps, orders=teams, contest_id='rotation/tie')
        self.assertIsNone(HALLS.award_contest(host))
        self.assertEqual(self.ribbons(native), {})

    def test_incomplete_native_states_never_pay_any_format(self):
        for mode in (None, 'simultaneous', 'alternating'):
            host, cs, native, _, _ = self.fixture(paired=mode is not None)
            options = {} if mode is None else dict(trainer_model=mode, trainer_order=lambda c, t, rnd:
                        [c, t] if mode == 'simultaneous' else [c if rnd % 2 else t])
            with self.assertRaises(Pause):
                host.run(cs, self.topic, self.pause, **options)
            self.assertIsNone(HALLS.award_contest(host))
            self.assertEqual(self.ribbons(native), {})
        native, host, teams, reps = self.rotation()
        with self.assertRaises(Pause):
            host.run_rotation(teams, self.topic, self.pause, representatives=reps, orders=teams)
        self.assertIsNone(HALLS.award_contest(host))
        self.assertEqual(self.ribbons(native), {})
        engine, _, _, _, cid = battle_fixture.BattleContestTests.fixture(self)
        self.assertIsNone(HALLS.award_battle(engine, cid))
        self.assertEqual(self.ribbons(engine), {})

    def test_cold_contest_and_engine_json_restore_preserve_one_ribbon_and_replay_has_no_log(self):
        host, cs, native, trainers, _ = self.fixture()
        hall_id = self.hall(host, native)
        self.play(host, cs, hall_id=hall_id)
        expected = self.assert_recipients(native, [trainers[0].entity_id])
        actual = self.assert_cold_contest_replay(host, cs, native)
        restored = CODEC.load_engine(self.nr, json.loads(json.dumps(CODEC.dump_engine(actual))))
        self.assertEqual(self.ribbons(restored), expected)
        host._standard_run['hall']['source'] = 'unsupported/Hall'
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_contest(host, cs)

    def test_gm_checkpoint_restores_native_cursor_hall_and_ribbon_together(self):
        host, cs, native, trainers, _ = self.fixture()
        hall_id = self.hall(host, native)
        with self.assertRaises(Pause):
            host.run(cs, self.topic, self.pause, hall_id=hall_id, contest_id='checkpoint/award')
        host.snapshot('before-award')
        self.play(host, cs, hall_id=hall_id, occurrence='checkpoint/award')
        self.assert_recipients(native, [trainers[0].entity_id])
        host.restore('before-award', reason='actual GM checkpoint rollback')
        self.assertEqual(self.ribbons(native), {})
        self.assertEqual(host._standard_run['phase'], 'perform')
        self.assertEqual(host._standard_run['hall']['id'], hall_id)
        self.play(host, cs, hall_id=hall_id, occurrence='checkpoint/award')
        self.assert_recipients(native, [trainers[0].entity_id])

    def test_in_progress_changed_owner_forged_actor_and_wrong_trainer_receipt_are_rejected(self):
        host, cs, native, trainers, pokemon = self.fixture()
        with self.assertRaises(Pause):
            host.run(cs, self.topic, self.pause, contest_id='reward/actual')
        pokemon[0].spec['trainer_id'] = trainers[1].entity_id
        with self.assertRaises(ValueError):
            HALLS.award_contest(host)
        pokemon[0].spec['trainer_id'] = trainers[0].entity_id
        clone = deepcopy(trainers[0], {id(self.nr): self.nr})
        native.everyone.append(clone)
        with self.assertRaises(ValueError):
            HALLS.award_contest(host)
        native.everyone.remove(clone)
        self.play(host, cs)
        trainers[1].spec[HALLS.KEY] = trainers[0].spec.pop(HALLS.KEY)
        with self.assertRaises(ValueError):
            HALLS.award_contest(host)
        with self.assertRaises(CODEC.StateCodecError):
            CODEC.dump_contest(host, cs)

    def test_late_gm_failure_keeps_native_completion_and_retry_only_pays_the_reward(self):
        host, cs, native, trainers, _ = self.fixture()
        original = GMState._rec
        def fail(gm, what, *args, **kw):
            result = original(gm, what, *args, **kw)
            if what.startswith('Contest Ribbon '):
                raise RuntimeError('late Ribbon record failure')
            return result
        with patch.object(GMState, '_rec', fail), self.assertRaises(RuntimeError):
            self.play(host, cs)
        self.assertEqual(host._standard_run['phase'], 'complete')
        self.assertEqual(self.ribbons(native), {})
        self.assertFalse(any('Contest Ribbon ' in line for line in native.log_lines))
        before = (len(host._performance_observations), host.rng.getstate(), list(host.log_lines))
        HALLS.award_contest(host)
        self.assertEqual(before, (len(host._performance_observations), host.rng.getstate(), host.log_lines))
        self.assert_recipients(native, [trainers[0].entity_id])

    def test_rotation_team_reward_failure_is_atomic_across_all_winning_trainers(self):
        native, host, teams, reps = self.rotation()
        original = GMState._rec
        def fail(gm, what, *args, **kw):
            result = original(gm, what, *args, **kw)
            if what.startswith('Contest Ribbon '):
                raise RuntimeError('late team award failure')
            return result
        with patch.object(GMState, '_rec', fail), patch.object(ContestEngine, 'd6', lambda host, n: [5]*n):
            with self.assertRaises(RuntimeError):
                host.run_rotation(teams, self.topic,
                    lambda c, rnd, adjacent, center: (self.reliable, 2 if c in teams[0] else 0),
                    representatives=reps, orders=teams, contest_id='rotation/atomic')
        self.assertEqual(host._standard_run['phase'], 'complete')
        self.assertEqual(self.ribbons(native), {})
        HALLS.award_contest(host)
        self.assert_recipients(native, {host._native_intro_bindings[c][2].entity_id for c in teams[0]})

    def battle_leader(self, engine, host, teams, cid):
        BATTLE.begin_round(engine, cid)
        scorer, target = teams[1][0], teams[0][0]
        engine.start_of_turn(scorer)
        BATTLE.perform_move(engine, host, cid, scorer, target, 'move/보복',
                            fixed_rolls=[6]*6, combat_options={'set_damage': True})
        BATTLE.finish_turn(engine, cid, scorer)
        self.assertGreater(BATTLE.result(engine, cid)['scores'][1], BATTLE.result(engine, cid)['scores'][0])
        return scorer, target

    def test_battle_round_limit_pays_actual_winner_and_cold_restore_does_not_pay_twice(self):
        engine, host, trainers, teams, cid = battle_fixture.BattleContestTests.fixture(self)
        self.battle_leader(engine, host, teams, cid)
        result = BATTLE.finish_round(engine, cid)
        while result['status'] != 'complete':
            BATTLE.begin_round(engine, cid)
            result = BATTLE.finish_round(engine, cid)
        self.assertEqual(result['completion_reason'], 'round_limit')
        expected = self.assert_recipients(engine, [trainers[1].entity_id])
        restored = CODEC.load_engine(self.nr, json.loads(json.dumps(CODEC.dump_engine(engine))))
        before = list(restored.log_lines)
        HALLS.award_battle(restored, cid)
        self.assertEqual(self.ribbons(restored), expected)
        self.assertEqual(restored.log_lines, before)

    def test_battle_attack_terminal_uses_native_appeal_winner_even_when_its_roster_faints(self):
        engine, host, trainers, teams, cid = battle_fixture.BattleContestTests.fixture(self)
        scorer, opponent = self.battle_leader(engine, host, teams, cid)
        for reserve in teams[1][1:]:
            engine.lose_hp(reserve, reserve.hp, source='prior actual native combat damage')
        scorer.hp = 1
        scorer.stats['def'] = 1
        engine.start_of_turn(opponent)
        result = BATTLE.perform_move(engine, host, cid, opponent, scorer, 'struggle',
                                    combat_options={'situational': 100, 'set_damage': True})
        self.assertEqual(result['result']['completion_reason'], 'all_pokemon_fainted')
        self.assertTrue(all(p.fainted for p in teams[1]))
        self.assert_recipients(engine, [trainers[1].entity_id])

    def test_battle_dot_terminal_and_unresolved_tie_follow_native_winner_identity(self):
        engine, host, trainers, teams, cid = battle_fixture.BattleContestTests.fixture(self)
        scorer, _ = self.battle_leader(engine, host, teams, cid)
        BATTLE.finish_round(engine, cid)
        BATTLE.begin_round(engine, cid)
        for reserve in teams[1][1:]:
            engine.lose_hp(reserve, reserve.hp, source='prior actual native combat damage')
        scorer.hp = 1
        scorer.conditions.add('독')
        engine.start_of_turn(scorer)
        scorer.took_standard = True
        result = BATTLE.finish_turn(engine, cid, scorer)
        self.assertEqual(result['result']['completion_reason'], 'all_pokemon_fainted')
        self.assert_recipients(engine, [trainers[1].entity_id])
        engine, _, _, _, cid = battle_fixture.BattleContestTests.fixture(self, contest_id='battle/tie')
        state = BATTLE.validate(engine, cid)[1]
        # The two actual identical skill introductions supply equal starting Appeal.
        self.assertEqual(BATTLE.result(engine, cid)['scores'][0], BATTLE.result(engine, cid)['scores'][1])
        for _ in range(state['max_rounds']):
            BATTLE.begin_round(engine, cid)
            BATTLE.finish_round(engine, cid)
        self.assertIsNone(BATTLE.result(engine, cid)['winner_trainer_id'])
        self.assertIsNone(HALLS.award_battle(engine, cid))
        self.assertEqual(self.ribbons(engine), {})

    def test_hall_observation_late_gm_failure_rolls_back_same_physical_venue_and_gm_log(self):
        host, _, native, _, _ = self.fixture()
        hall_id = self.hall(host, native)
        actual = native._physical_objects[hall_id]
        before = (deepcopy(actual), list(native.log_lines))
        original = GMState._rec
        def fail(gm, what, *args, **kw):
            original(gm, what, *args, **kw)
            if what.startswith('Contest Hall '):
                raise RuntimeError('late Hall observation failure')
        with patch.object(GMState, '_rec', fail), self.assertRaises(RuntimeError):
            HALLS.observe_hall(host, native, hall_id, [self.topic], reason='new actual observation')
        self.assertIs(native._physical_objects[hall_id], actual)
        self.assertEqual(before, (actual, native.log_lines))

    def test_new_native_contestants_with_same_actual_pokemon_and_label_earn_another_ribbon(self):
        for mode, label in ((None, None), ('simultaneous', None), ('alternating', None),
                            (None, 'same/explicit-label')):
            with self.subTest(mode=mode, label=label):
                host, cs, native, trainers, _ = self.fixture(paired=mode is not None)
                self.play(host, cs, mode=mode, occurrence=label)
                first_state = host._paired_run if mode else host._standard_run
                first_id = next(iter(trainers[0].spec[HALLS.KEY]))
                first_uuids = {c.entity_id for c in cs}
                fresh = ContestEngine(self.cr, seed=130)
                actual_new = []
                for old in cs:
                    engine, pokemon, trainer, skill, choices = host._native_intro_bindings[old]
                    c = fresh.contestant_from_combatants(engine, pokemon, trainer, skill,
                        dict.fromkeys(self.cr.mech('contest/type-match')['ring'], 24),
                        bonus_stats=choices)
                    if mode is not None:
                        fresh.trainer_participant(c)
                    actual_new.append(c)
                self.prepare(fresh, actual_new)
                self.assertTrue(first_uuids.isdisjoint(c.entity_id for c in actual_new))
                self.play(fresh, actual_new, mode=mode, occurrence=label)
                new_state = fresh._paired_run if mode else fresh._standard_run
                self.assertEqual(first_state['id'], new_state['id'])
                records = trainers[0].spec[HALLS.KEY]
                self.assertEqual(len(records), 2)
                self.assertIn(first_id, records)
                self.assertEqual({tuple(row['entrants']) for row in records.values()},
                                 {tuple(sorted(host._native_intro_bindings[c][1].entity_id for c in cs))})
                self.assertEqual(len({tuple(row['native_participants']) for row in records.values()}), 2)
                self.assert_cold_contest_replay(fresh, actual_new, native)

    def test_completed_original_trainer_ribbon_survives_actual_transfer_hall_correction_and_demolition(self):
        for variant in ('standard', 'rotation', 'festival', 'battle'):
            with self.subTest(variant=variant):
                hall_id = None
                if variant == 'standard':
                    host, cs, native, trainers, pokemon = self.fixture()
                    hall_id = self.hall(host, native)
                    self.play(host, cs, hall_id=hall_id)
                    original_hall = deepcopy(host._standard_run['hall'])
                    transferred, former, new_owner = pokemon[0], trainers[0], trainers[1]
                elif variant == 'festival':
                    host, cs, native, trainers, pokemon = self.fixture()
                    policy = dict(scope='festival/historical', reason='explicit fixture resource interpretation',
                                  introduction='repeat', stat_dice='reset', excitement='reset', last_move='reset')
                    with patch.object(ContestEngine, 'd6', lambda host, n: [5]*n):
                        host.run(cs, self.topic, self.chooser(host, cs[0]), variant='festival',
                            contest_id='festival/historical', festival_policy=policy)
                    transferred, former, new_owner = pokemon[0], trainers[0], trainers[1]
                elif variant == 'rotation':
                    native, host, teams, reps = self.rotation()
                    cs = [c for team in teams for c in team]
                    with patch.object(ContestEngine, 'd6', lambda host, n: [5]*n):
                        host.run_rotation(teams, self.topic,
                            lambda c, rnd, adjacent, center: (self.reliable, 2 if c in teams[0] else 0),
                            representatives=reps, orders=teams, contest_id='rotation/historical')
                    _, transferred, former, _, _ = host._native_intro_bindings[teams[0][0]]
                    new_owner = host._native_intro_bindings[teams[1][0]][2]
                else:
                    native, host, trainers, teams, cid = battle_fixture.BattleContestTests.fixture(self)
                    transferred, _ = self.battle_leader(native, host, teams, cid)
                    result = BATTLE.finish_round(native, cid)
                    while result['status'] != 'complete':
                        BATTLE.begin_round(native, cid)
                        result = BATTLE.finish_round(native, cid)
                    former, new_owner = trainers[1], trainers[0]
                expected = self.ribbons(native)
                self.assertIn(former.entity_id, expected)
                if native.encounter_active:
                    native.end_encounter()
                actors = WORLD.actor_index(native)
                for trainer in (a for a in actors.values() if a.kind == 'trainer'):
                    PARTY.configure(native, trainer, mode='unlimited',
                        reason='explicit fixture carrying policy for observed post-contest transfer',
                        roster=[p for p in actors.values() if p.kind == 'pokemon'
                                and p.spec.get('trainer_id') == trainer.entity_id])
                WORLD.transfer_owner(native, transferred, former, new_owner,
                    reason='actual post-contest ownership transfer', request_id='transfer/'+variant)
                self.assertEqual(transferred.spec['trainer_id'], new_owner.entity_id)
                if hall_id is not None:
                    other = next(t for t in self.cr.mech('contest/type-match')['ring'] if t != self.topic)
                    HALLS.observe_hall(host, native, hall_id, [other], reason='new actual offered-type observation')
                    GRANTS.transition(native, None, lambda staged, _: WORLD.finish_physical_use(
                        staged, staged._physical_objects[hall_id], 'destroyed',
                        {'source': 'gm/observed demolition', 'by_actor_id': new_owner.entity_id,
                         'at': staged.elapsed_seconds}))
                    self.assertEqual(host._standard_run['hall'], original_hall)
                before = list(native.log_lines)
                if variant == 'battle':
                    HALLS.award_battle(native, cid)
                    restored = CODEC.load_engine(self.nr, json.loads(json.dumps(CODEC.dump_engine(native))))
                    HALLS.award_battle(restored, cid)
                    self.assertEqual(self.ribbons(restored), expected)
                else:
                    HALLS.award_contest(host)
                    if variant == 'festival':
                        self.assertIs(host.run(cs, self.topic, self.pause, variant='festival',
                            contest_id='festival/historical', festival_policy=policy)[0], cs[0])
                    self.assert_cold_contest_replay(host, cs, native)
                self.assertEqual(native.log_lines, before)
                self.assertEqual(self.ribbons(native), expected)


if __name__ == '__main__':
    unittest.main()
