"""C10-097: actual wild authority, authored alternatives and paid native moves."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

import native_scenario_fixture as NATIVE
import pack_mon as PACK
import state_codec as CODEC
import world_entities as WORLD

ROOT = Path(__file__).resolve().parents[1]


class PackMonWildSourceRevisionTests(unittest.TestCase):
    def world(self, *, follower='나옹', follower_level=80, wild=True,
              owned=False, active=True, leader='페르시온'):
        def body():
            return {'size': '중형', 'offsets': [(0, 0)],
                    'reason': 'GM observed one-cell body in this command scene'}
        def pokemon(key, species, level, pos, *, is_wild=True, extra=None):
            return {'key': key, 'kind': 'pokemon', 'sheet': {
                'species': species, 'level': level, 'name': key,
                'moves': ['struggle'], 'abilities': [], 'pos': pos,
                'wild': is_wild, 'side': 'independent' if key != 'target' else 'opponent',
                'extra': {'id': 'pokemon/' + key, **(extra or {})}}, 'body': body()}
        owner = {'key': 'owner', 'kind': 'trainer', 'sheet': {
            'name': 'actual other trainer', 'level': 30,
            'stats': dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20),
            'moves': ['struggle'], 'abilities': [], 'pos': (0, 3),
            'skills': {'명령': '숙련'}, 'extra': {'id': 'trainer/actual-owner'}},
            'body': body()}
        relation = {'trainer_id': 'trainer/actual-owner'} if owned else {}
        self.e, actors = NATIVE.prepare_scene(ROOT, ruleset='core', seed=5,
            grid={'width': 8, 'height': 8}, actors=[owner,
                pokemon('leader', leader, 30, (0, 1)),
                pokemon('follower', follower, follower_level, (1, 1),
                        is_wild=wild, extra=relation),
                pokemon('target', '꼬부기', 100, (2, 1))])
        self.owner, self.leader, self.p, self.target = (
            actors[key] for key in ('owner', 'leader', 'follower', 'target'))
        if owned:
            self.e.pokemon_activity(self.owner, 'party_policy', mode='standard',
                roster=[self.p], storage={'kind': 'center', 'id': 'actual-center'},
                reason='complete native roster of the other trainer')
            self.e.gm.observe_loyalty(self.p, 0,
                reason='observed current trainer relationship', request_id='initial-loyalty')
        if active:self.turn()

    def turn(self):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p)

    def choice(self, variant):
        pending = PACK.source_choices(self.e)
        self.assertEqual(pending['status'], 'PolicyInputsRequired')
        return {'value': variant, 'reason': 'GM explicitly selected this complete text',
                'scope': pending['decision_scope']}

    def command(self, choice=None, *, actor=None):
        return self.e.pokemon_activity(self.leader if actor is None else actor,
            'command_move', pokemon=self.p, target=self.target, move_id='struggle',
            set_damage=True, pack_mon_source_choice=choice)

    def relationship(self):
        return deepcopy({key: self.p.spec[key] for key in (
            'trainer_id', 'trainer', 'wild', 'loyalty', 'loyalty_relations',
            'loyalty_observations', 'party_location') if key in self.p.spec})

    def test_native_owned_pokemon_refuses_pack_authority_but_its_trainer_can_command(self):
        self.world(owned=True, wild=False)
        relation = self.relationship()
        registry = deepcopy(self.owner.spec['pokemon_registry'])
        for variant in ('korean_same_species', 'english_lower_level'):
            choice = self.choice(variant)
            NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(choice),
                reason_pattern='unowned wild Pokemon')
        self.assertEqual(self.relationship(), relation)
        self.assertEqual(self.owner.spec['pokemon_registry'], registry)
        self.assertEqual(self.e.use_move(self.p, self.target, 'struggle'), 0)
        # The owner's real GM-observed affection, rather than Pack Mon, admits it.
        self.e.gm.observe_loyalty(self.p, 2, reason='GM observed willing cooperation',
                                 request_id='willing-loyalty')
        willing = self.relationship()
        out = self.command(actor=self.owner)
        self.assertEqual(out['status'], 'submitted')
        self.assertEqual((self.p.move_uses['struggle'], self.p.budget['standard']), (1, 0))
        self.assertEqual(self.relationship(), willing)
        self.assertEqual(self.owner.spec['pokemon_registry'], registry)

    def test_actual_wild_pre_evolution_obeys_at_higher_level_and_pays_once(self):
        self.world()
        relation = self.relationship()
        hp = self.target.hp
        leader = deepcopy((self.leader.spec, self.leader.move_uses,
                           hasattr(self.leader, 'budget')))
        with patch.object(PACK, 'authorize', wraps=PACK.authorize) as authorize:
            out = self.command()
        self.assertEqual(authorize.call_count, 2)
        self.assertEqual(out['obedience']['relation'], 'pre_evolution')
        self.assertEqual(out['obedience']['source_variant'], 'korean_same_species')
        self.assertLess(self.target.hp, hp)
        self.assertEqual((self.p.move_uses['struggle'], self.p.budget['standard']), (1, 0))
        self.assertEqual(self.relationship(), relation)
        self.assertEqual((self.leader.spec, self.leader.move_uses,
                          hasattr(self.leader, 'budget')), leader)
        self.assertNotIn('_obedience_receipts', self.e.__dict__)
        NATIVE.assert_logged_refusal_unchanged(self.e,lambda:self.command()['move_result'],
            expected_result=0,expected_logs=[
                f'    {self.p.name}: 기본 행동이 남지 않음 → 발버둥 불가  => [combat/action-economy]'])

    def test_lower_unrelated_owned_pokemon_is_not_forced_by_english_text(self):
        self.world(owned=True, wild=False, follower='꼬부기', follower_level=20)
        choice = self.choice('english_lower_level')
        relation = self.relationship()
        NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(choice),
            reason_pattern='unowned wild Pokemon')
        self.assertEqual(self.relationship(), relation)
        self.assertEqual(self.p.move_uses, {})
        self.assertEqual(self.p.budget['standard'], 1)

    def test_complete_korean_and_english_variants_differ_for_unrelated_lower_wild(self):
        for variant in ('korean_same_species', 'english_lower_level'):
            with self.subTest(variant=variant):
                self.world(follower='꼬부기', follower_level=20)
                choice = self.choice(variant)
                if variant == 'korean_same_species':
                    NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(choice),
                        reason_pattern='species/level')
                else:
                    hp = self.target.hp
                    out = self.command(choice)
                    self.assertEqual(out['obedience']['relation'], 'lower_level')
                    self.assertEqual(out['obedience']['source_choice'], choice)
                    self.assertEqual(out['obedience']['definition']['lower_level_species'], 'any_species')
                    self.assertEqual((self.p.move_uses['struggle'], self.p.budget['standard']), (1, 0))
                    self.assertLess(self.target.hp, hp)
                    self.assertNotIn('trainer_id', self.p.spec)
                    self.assertNotIn('loyalty', self.p.spec)

    def test_both_variants_keep_same_species_ten_level_boundary_and_no_reverse_authority(self):
        for variant, difference in ((v, d) for v in ('korean_same_species', 'english_lower_level')
                                    for d in (9, 10, -10)):
            with self.subTest(variant=variant, difference=difference):
                self.world(follower='페르시온', follower_level=30 - difference)
                choice = self.choice(variant)
                if difference == 10:
                    out = self.command(choice)
                    self.assertEqual(out['obedience']['relation'], 'same_species')
                    self.assertEqual((self.p.move_uses['struggle'], self.p.budget['standard']), (1, 0))
                else:
                    NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(choice),
                        reason_pattern='species/level')

    def test_nonwild_unowned_refuses_before_a_turn_or_budget_exists(self):
        self.world(wild=False, active=False)
        self.assertFalse(hasattr(self.p, 'budget'))
        for variant in ('korean_same_species', 'english_lower_level'):
            choice = self.choice(variant)
            NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(choice),
                reason_pattern='unowned wild Pokemon')
        self.assertFalse(hasattr(self.p, 'budget'))
        self.assertNotIn('_obedience_receipts', self.e.__dict__)

    def test_actual_registration_and_capability_are_required_without_synthetic_grants(self):
        self.world(leader='꼬부기')
        NATIVE.assert_rejected_unchanged(self.e, self.command,
            reason_pattern='current Pack Mon capability')
        self.world()
        detached = copy(self.leader)
        NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(actor=detached),
            reason_pattern='actual registered')

    def test_source_decision_scope_and_retained_choice_guard_the_actual_move_gate(self):
        self.world(follower='꼬부기', follower_level=20)
        choice = self.choice('english_lower_level')
        for bad in ({'value': choice['value'], 'reason': choice['reason']},
                    dict(choice, value='mixed_species'),
                    dict(choice, scope={**choice['scope'], 'profile_hash': 'foreign-profile'})):
            NATIVE.assert_rejected_unchanged(self.e, lambda: self.command(bad),
                reason_pattern='source conflict decision|invalid policy input|decision scope changed')
        real_use = self.e.use_move
        def mutate_caller_choice(*args, **options):
            choice['value'] = 'korean_same_species'
            return real_use(*args, **options)
        with patch.object(self.e, 'use_move', side_effect=mutate_caller_choice):
            out = self.command(choice)
        self.assertEqual(out['obedience']['source_variant'], 'english_lower_level')
        self.assertEqual(out['obedience']['source_choice']['value'], 'english_lower_level')
        self.assertEqual((self.p.move_uses['struggle'], self.p.budget['standard']), (1, 0))
        self.assertNotIn('_obedience_receipts', self.e.__dict__)

    def test_paid_english_command_survives_gm_and_json_restore_without_current_reselection(self):
        self.world(follower='꼬부기', follower_level=20)
        out = self.command(self.choice('english_lower_level'))
        paid = deepcopy((self.target.hp, self.p.move_uses, self.p.budget, self.relationship()))
        self.e.gm.snapshot('after-paid-pack-command')
        self.turn()
        NATIVE.assert_rejected_unchanged(self.e,
            lambda: self.command(self.choice('korean_same_species')), reason_pattern='species/level')
        self.e.gm.restore('after-paid-pack-command', reason='restore actual paid command observation')
        self.assertEqual((self.target.hp, self.p.move_uses, self.p.budget, self.relationship()), paid)
        self.e = CODEC.load_engine(self.e.r, json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index = WORLD.actor_index(self.e)
        self.owner, self.leader, self.p, self.target = (
            index[actor.entity_id] for actor in (self.owner, self.leader, self.p, self.target))
        self.assertEqual((self.target.hp, self.p.move_uses, self.p.budget, self.relationship()), paid)
        self.assertEqual(out['obedience']['source_variant'], 'english_lower_level')
        self.assertNotIn('_obedience_receipts', self.e.__dict__)


if __name__ == '__main__':
    unittest.main()
