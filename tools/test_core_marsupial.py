"""Native birth/pouch consumers; no inherited TestCase or synthetic offspring."""
from pathlib import Path
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

ROOT = Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
from engine import Engine, Rules, Combatant
from builder import build_pokemon, build_trainer, nature_base, STATS
from grid import Grid
import creation_egg as E
import pokemon_entities as ENT
import pokemon_party as PARTY
import party_actions as COMMAND
import growth_stats as GS
import downtime as D
import marsupial_state as M
import baby_templates as OPTIONAL
import state_grants as G
import world_entities as W
import turn as TURN
import body_modes as BODY
import setup_move_state as SETUP
import state_codec as CODEC
import move_state as MOVES
import pokemon_progression as PROGRESSION


class MarsupialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=68082)
        self.e.grid = Grid(20, 16)
        self.a = Combatant(self.r, build_trainer(self.r, 'breeder', 20,
            dict.fromkeys(STATS, 10), skills={'포켓몬학': 3, '명령': 3},
            pos=(1, 1), items={'몬스터볼': 4}, extra={'edges': ['edge/브리더']}))
        self.mother = Combatant(self.r, build_pokemon(self.r, '캥카', 35,
            moves=['move/몸통박치기'], abilities=[], pos=(3, 1),
            extra={'trainer_id': self.a.entity_id, 'gender': 'female'}))
        self.father = Combatant(self.r, build_pokemon(self.r, '메타몽', 35,
            moves=[], abilities=[], pos=(6, 1),
            extra={'trainer_id': self.a.entity_id, 'gender': 'genderless'}))
        self.enemy = Combatant(self.r, build_pokemon(self.r, '파오리', 40,
            moves=['move/몸통박치기'], abilities=[], wild=True, pos=(4, 2)))
        self.e.everyone = self.e.gm.everyone = [self.a, self.mother, self.father, self.enemy]
        PARTY.configure(self.e, self.a, mode='unlimited', reason='actual campaign roster',
                        roster=[self.mother, self.father])
        self.father.on_field = False

    def policy(self):
        # The existing external declaration boundary supplies observed Ditto
        # compatibility and an explicit empty inherited selection. It does not
        # pretend Ditto has a male biological fact or invent a mother.
        value = json.loads((ROOT / 'data/examples/egg-creation.json').read_text(encoding='utf8'))[0]
        value['requirements'] = [r for r in value['requirements'] if r['id'] != 'father-fact']
        value['species'] = {'parents': [0], 'allowed': []}
        value['inheritance'] = {'kind': 'declared', 'moves': [], 'parents': [0, 1], 'knowledge': 'any'}
        value['work_seconds'] = 0
        return value

    def egg(self, *, key='baby', policy=None):
        return self.e.create_declared_egg(self.a, [self.mother, self.father],
            self.policy() if policy is None else policy, request_id=key,
            compatible=True, species='캥카', inheritance_moves=[], reason='observed actual compatible parents')

    def hatch(self, egg, *, nature='노력', owner=None):
        return self.e.hatch_declared_egg(owner or self.a, egg['entity_id'], name='actual native baby',
            ready=True, reason='actual observed Kangaskhan birth', choices={
                'gender': 'female', 'nature': nature, 'abilities': [], 'moves': [],
                'special_appearance': False, 'inheritance_moves': []})['pokemon']

    def born(self, **kwargs):
        return self.hatch(self.egg(), **kwargs)

    def snap(self):
        return json.dumps(CODEC.dump_engine(self.e), sort_keys=True, ensure_ascii=False)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])
        M.validate_world(self.e)

    def grow(self, baby, level):
        while baby.level < level:
            # Explicitly forget actual learned Moves only when the next native
            # learning event needs room. No capacity/stat/catalog override.
            incoming = D._learnset_moves_upto(self.r, baby.spec['species'], baby.level + 1,
                                              baby.level, spec=baby.spec)
            known = MOVES.known(self.r, baby.spec)
            while len(set(known + incoming)) > 6:
                mid = next(m for m in known if m not in incoming)
                self.e.gm.set_move(baby, mid, False, reason='explicit GM-selected forgetting before actual growth')
                known.remove(mid)
            D.gain_exp_combatant(self.e, baby, 'to next level')

    def test_actual_birth_signed_floor_before_nature_and_real_parent_identity(self):
        parent_stats = deepcopy(self.mother.spec['stats'])
        baby = self.born()
        base = self.r.species['pokemon/캥카']['base_stats']
        expected = {s: max(1, base[s] - 5) for s in STATS}
        current = GS.project_actor(self.e, baby)['permanent']
        self.assertEqual(current['nature_base'], expected)
        self.assertEqual(expected['spa'], 1)
        self.assertEqual(sum(current['investment'].values()), baby.spec['initial_allocation']['points'])
        self.assertEqual(baby.spec['moves'], ['struggle'])
        self.assertEqual(baby.spec['tutor_points'], 1)
        self.assertEqual(baby.spec[PROGRESSION.LEVEL_STATE]['origin'], 'hatch')
        self.assertEqual(self.mother.spec['stats'], parent_stats)
        self.assertNotIn(OPTIONAL.KEY, baby.spec)
        self.assertEqual(M.projection(baby)['mother_id'], self.mother.entity_id)
        self.assertIs(W.actor_index(self.e)[baby.entity_id], baby)
        self.assertNotEqual(baby.entity_id, self.mother.entity_id)
        self.valid()

    def test_actual_non_neutral_birth_growth_and_native_maturity_keep_investment(self):
        # Select by actual Nature metadata rather than assuming translated labels.
        import nature_state as N
        nature = next(name for name in self.r.mech('pokemon/natures')['by_name']
                      if N.describe(self.r, name)['up_stat'] == 'spa' and not N.describe(self.r, name)['neutral'])
        baby = self.born(nature=nature)
        raw = self.r.species['pokemon/캥카']['base_stats']
        self.assertEqual(GS.project(self.r, baby.spec)['nature_base'],
                         nature_base({s: max(1, raw[s]-5) for s in STATS}, nature, self.r))
        source = deepcopy(baby.spec['initial_allocation']['base_sources'])
        self.grow(baby, 5)
        self.assertTrue(M.active(baby))
        self.assertEqual(baby.spec['initial_allocation']['base_sources'], source)
        self.assertNotIn(OPTIONAL.KEY, baby.spec)
        self.assertNotIn('allocation_migrations', baby.spec)
        self.grow(baby, 25)
        self.assertFalse(M.active(baby))
        after = GS.project(self.r, baby.spec)
        self.assertEqual(after['nature_base'], nature_base(raw, nature, self.r))
        self.assertEqual(sum(after['investment'].values()), baby.spec['initial_allocation']['points'] + 24)
        self.valid()

    def test_native_baby_actions_and_actual_attacks_refuse_before_cost(self):
        baby = self.born()
        COMMAND.configure(self.e, self.a, battle_mode='full_contact', reason='actual native commands')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'cannot participate'):
            self.e.start_round([self.a, self.mother, self.enemy, baby])
        self.assertEqual(self.snap(), before)
        self.e.start_round([self.a, self.mother, self.enemy])
        self.assertFalse(TURN.can_act(self.e, baby))
        for fn in (lambda: self.e.use_move(baby, self.enemy, 'struggle'),
                   lambda: self.e.start_of_turn(baby, initiative_count=5),
                   lambda: COMMAND.act(self.e, self.a, send=[(baby, (8, 2))],
                                       request_id='baby-send', reason='invalid independent release')):
            before = self.snap()
            with self.assertRaisesRegex(ValueError, 'cannot participate'):
                fn()
            self.assertEqual(self.snap(), before)
        self.assertFalse(BODY.targetable(baby))
        self.assertFalse(SETUP.targetable(baby))
        for fn in (lambda: self.e.use_move(self.enemy, baby, 'move/몸통박치기'),
                   lambda: self.e.throw_ball(self.a, baby, fixed_accuracy=20, fixed_capture=20)):
            before = self.snap()
            with self.assertRaisesRegex(ValueError, 'pouch'):
                fn()
            self.assertEqual(self.snap(), before)
        self.e.start_of_turn(self.enemy, initiative_count=20)
        hp = self.mother.hp
        self.e.use_move(self.enemy, self.mother, 'move/몸통박치기', situational=100, set_damage=True)
        self.assertLess(self.mother.hp, hp)
        self.valid()

    def test_actual_recall_send_share_one_ball_without_prime_party_discount(self):
        baby = self.born()
        COMMAND.configure(self.e, self.a, battle_mode='full_contact', reason='actual contact combat')
        self.assertEqual(PARTY._carried(self.a), 3)
        self.e.start_round([self.a, self.mother, self.enemy])
        self.e.start_of_turn(self.a, initiative_count=20)
        budget = self.a.budget['shift']
        COMMAND.act(self.e, self.a, recall=[self.mother], request_id='recall-mother', reason='return actual mother and pouch')
        self.assertEqual(self.a.budget['shift'], budget - 1)
        self.assertEqual(set(M.ball_view(self.e, self.mother)['occupant_ids']), {self.mother.entity_id, baby.entity_id})
        self.assertFalse(baby.on_field)
        self.e.end_of_turn(self.a)
        self.e.start_round([self.a, self.enemy])
        self.e.start_of_turn(self.a, initiative_count=20)
        COMMAND.act(self.e, self.a, send=[(self.mother, (7, 2))], request_id='send-mother', reason='release actual shared ball')
        self.assertEqual(M.ball_view(self.e, self.mother)['occupant_ids'], [])
        self.assertEqual(baby.pos, self.mother.pos)
        self.assertFalse(baby.on_field)
        self.assertEqual(PARTY._carried(self.a), 3)
        self.assertNotIn('combined_into', self.a.spec['pokemon_registry'][baby.entity_id])
        self.valid()

    def test_two_party_places_paired_storage_transfer_and_individual_refusal(self):
        baby = self.born()
        PARTY.configure(self.e, self.a, mode='custom', limit=1, storage={'kind': 'center', 'id': 'actual-center'},
                        reason='one remaining place cannot divide actual pouch pair', roster=[self.mother, baby, self.father])
        self.assertEqual(self.mother.spec['party_location']['location'], 'storage')
        self.assertEqual(baby.spec['party_location']['location'], 'storage')
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'carrying limit'):
            PARTY.place(self.e, self.a, target=self.mother, location='carried')
        self.assertEqual(self.snap(), before)
        with self.assertRaisesRegex(ValueError, 'cannot participate'):
            PARTY.place(self.e, self.a, target=baby, location='carried')
        PARTY.configure(self.e, self.a, mode='unlimited', reason='actual capacity restored',
                        roster=[self.mother, baby, self.father])
        other = Combatant(self.r, build_trainer(self.r, 'recipient', 20, dict.fromkeys(STATS, 10), pos=(1, 4)))
        self.e.everyone.append(other)
        PARTY.configure(self.e, other, mode='unlimited', reason='actual recipient roster', roster=[])
        PARTY.transfer(self.e, self.a, target=self.mother, new_owner=other, reason='actual gift of mother; baby retains own ownership', request_id='mother-gift')
        self.assertEqual([p.spec['trainer_id'] for p in (self.mother, baby)], [other.entity_id, self.a.entity_id])
        self.assertEqual(PARTY._carried(other), 1)
        self.assertIn(baby.entity_id, self.a.spec['pokemon_registry'])
        self.assertEqual(set(M.ball_view(self.e, self.mother)['occupant_ids']), {self.mother.entity_id, baby.entity_id})
        PARTY.transfer(self.e, self.a, target=baby, new_owner=other, reason='separate explicit actual baby ownership gift', request_id='baby-gift')
        self.assertEqual(PARTY._carried(other), 2)
        self.assertNotIn(baby.entity_id, self.a.spec['pokemon_registry'])
        self.assertIs(W.actor_index(self.e)[baby.entity_id], baby)
        self.valid()

    def test_actual_level25_exit_withdraws_only_native_source(self):
        baby = self.born()
        OPTIONAL.apply(self.e, baby, stat_reduction=2, permanent_stat_reduction=2,
                       reason='separate explicit optional permanent template')
        original = deepcopy(baby.spec[OPTIONAL.KEY])
        self.grow(baby, 24)
        self.assertTrue(M.active(baby))
        before = GS.project(self.r, baby.spec)
        hp_fraction = baby.hp / baby.base_max_hp
        D.gain_exp_combatant(self.e, baby, 'to next level')
        after = GS.project(self.r, baby.spec)
        self.assertEqual((baby.level, M.active(baby), M.in_pouch(baby)), (25, False, False))
        self.assertTrue(TURN.can_act(self.e, baby))
        self.assertTrue(BODY.targetable(baby))
        self.assertEqual(sum(after['investment'].values()), sum(before['investment'].values())+1)
        self.assertEqual(baby.spec[OPTIONAL.KEY]['stat_penalty_remaining'], original['stat_penalty_remaining'])
        sources = baby.spec['allocation_migrations'][-1]['plan']['base_sources']
        self.assertEqual([r['source'] for r in sources], [OPTIONAL.STAT_SOURCE])
        self.assertAlmostEqual(baby.hp / baby.base_max_hp, hp_fraction, delta=1/baby.base_max_hp)
        self.assertEqual(baby.spec[M.KEY]['ended_level'], 25)
        self.assertEqual(baby.spec['trainer_id'], self.a.entity_id)
        self.assertNotIn('capture', baby.spec[M.KEY])
        self.valid()

    def test_unknown_mother_is_not_inferred_and_cross_owner_birth_keeps_pouch_and_owners(self):
        self.mother.spec.pop('gender')
        policy = self.policy()
        policy['requirements'] = [r for r in policy['requirements'] if r['id'] != 'mother-fact']
        baby = self.hatch(self.egg(policy=policy))
        self.assertIsNone(baby.spec[M.KEY]['mother_id'])
        self.assertFalse(M.in_pouch(baby))
        self.assertFalse(TURN.can_act(self.e, baby))
        self.assertTrue(BODY.targetable(baby))
        self.valid()
        # Physical pouch custody and the egg recipient's ownership are distinct.
        self.mother.spec['gender'] = 'female'
        egg = self.egg(key='known-cross-owner')
        other = Combatant(self.r, build_trainer(self.r, 'egg recipient', 20, dict.fromkeys(STATS, 10), pos=(1, 5)))
        self.e.everyone.append(other)
        PARTY.configure(self.e, other, mode='unlimited', reason='actual recipient policy', roster=[])
        self.e.gm.transfer_egg(self.a, other, egg['entity_id'], reason='actual egg ownership gift', request_id='egg-gift')
        child = self.hatch(egg, owner=other)
        self.assertTrue(M.in_pouch(child))
        self.assertEqual((self.mother.spec['trainer_id'], child.spec['trainer_id']), (self.a.entity_id, other.entity_id))
        self.assertIn(child.entity_id, other.spec['pokemon_registry'])
        self.assertNotIn(child.entity_id, self.a.spec['pokemon_registry'])
        self.assertEqual(W.effective_location(self.e, child), W.location_of(self.mother))
        W.observe_location(self.e, self.mother, {'kind': 'grid', 'cell': [8, 3]}, reason='actual observed maternal movement')
        self.assertEqual(child.location, self.mother.location)
        self.assertEqual(M.custody(self.e, child)['baby_owner_id'], other.entity_id)
        self.valid()

    def test_actual_unowned_maternal_birth_and_one_ball_capture_keep_two_ids(self):
        actual = Combatant(self.r, build_pokemon(self.r, '캥카', 30, name='actual unowned mother',
            moves=['move/몸통박치기'], abilities=[], wild=True, pos=(3, 3), extra={'gender': 'female'}))
        self.e.everyone.append(actual)
        self.mother = actual
        policy = self.policy()
        policy['owned_parents'] = False
        baby = self.hatch(self.egg(policy=policy))
        self.assertTrue(M.in_pouch(baby))
        self.assertIsNone(actual.spec.get('trainer_id'))
        self.assertEqual(baby.spec['trainer_id'], self.a.entity_id)
        self.e.start_round([self.a, actual])
        self.e.start_of_turn(self.a, initiative_count=20)
        count = self.a.spec['items']['몬스터볼']
        self.assertTrue(self.e.throw_ball(self.a, actual, fixed_accuracy=20, fixed_capture=20))
        self.assertEqual(self.a.spec['items']['몬스터볼'], count-1)
        self.assertEqual(set(M.ball_view(self.e, actual)['occupant_ids']), {actual.entity_id, baby.entity_id})
        self.assertEqual(actual.spec['trainer_id'], baby.spec['trainer_id'])
        self.assertEqual(len({actual.entity_id, baby.entity_id}), 2)
        self.valid()

    def test_external_healing_move_reaches_baby_and_attack_block_keeps_native_source(self):
        import effects_ext as EXT
        baby = self.born()
        attack = self.r.move('move/몸통박치기')
        mm, _ = self.r.move_mech(attack['id'])
        self.assertEqual(EXT.blocks_hit(self.e, self.enemy, baby, attack, mm), M.SOURCE)
        self.e.gm.set_move(self.mother, 'move/치유파동', True, reason='observed actual known healing Move')
        ENT.observe_loyalty(self.e, self.mother, 2, reason='actual current-owner obedience observation for the healing command')
        self.e.start_round([self.mother, self.enemy])
        self.e.start_of_turn(self.mother, initiative_count=20)
        self.e.disengage(self.mother, (4, 1))
        self.assertEqual(baby.location, self.mother.location)
        before = self.snap()
        with self.assertRaisesRegex(ValueError, 'pouch'):
            W.observe_location(self.e, baby, {'kind': 'grid', 'cell': [8, 4]}, reason='invalid independent pouch placement')
        self.assertEqual(self.snap(), before)
        self.e.lose_hp(baby, 2, source='gm/observed-non-attack-loss')
        hp = baby.hp
        self.e.use_move(self.mother, baby, 'move/치유파동')
        self.assertGreater(baby.hp, hp, '\n'.join(self.e.log_lines[-24:]))
        self.e.end_of_turn(self.mother)
        self.e.gm.set_move(self.enemy, 'move/치유파동', True, reason='observed external opponent healing support')
        self.e.start_of_turn(self.enemy, initiative_count=10)
        self.e.lose_hp(baby, 2, source='gm/observed-non-attack-loss')
        hp = baby.hp
        self.e.use_move(self.enemy, baby, 'move/치유파동')
        self.assertGreater(baby.hp, hp, '\n'.join(self.e.log_lines[-24:]))
        self.assertTrue(M.in_pouch(baby))
        self.valid()

    def test_native_birth_restore_and_source_maternal_tamper_boundaries(self):
        egg = self.egg()
        before = self.snap()
        with patch.object(PARTY, 'finish_hatch', side_effect=ValueError('late actual birth placement failure')):
            with self.assertRaisesRegex(ValueError, 'late actual birth'):
                self.hatch(egg)
        self.assertEqual(self.snap(), before)
        baby = self.hatch(egg)
        restored = CODEC.load_engine(self.r, json.loads(self.snap()))
        rb = W.actor_index(restored)[baby.entity_id]
        self.assertEqual(M.projection(rb), M.projection(baby))
        self.assertEqual(M.ball_view(restored, W.actor_index(restored)[self.mother.entity_id]),
                         M.ball_view(self.e, self.mother))
        original = deepcopy(baby.spec[M.KEY])
        for patch_value in ({'mother_id': None}, {'mother_id': self.father.entity_id},
                            {'active': False, 'ended_level': 25}, {'pouch': False},
                            {'egg_id': 'egg/unknown'}, {'source': OPTIONAL.SOURCE}):
            baby.spec[M.KEY].update(patch_value)
            with self.assertRaises(ValueError):
                M.validate_world(self.e)
            self.assertFalse(self.e.validate_state()['valid'])
            baby.spec[M.KEY] = deepcopy(original)
        self.valid()


if __name__ == '__main__':
    unittest.main()
