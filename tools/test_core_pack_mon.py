"""C10-097's real commands; trainer/party, action and codec owners are reused."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json, unittest

from engine import Rules, Engine, Combatant
from builder import build_pokemon
import test_category3_pokemon_activities as fixture
import common_checks as C
import downtime as GROWTH
import pack_mon as PACK
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD

ROOT = Path(__file__).resolve().parents[1]


class CorePackMonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r = cls.rules = Rules(ROOT, ruleset='core')

    actor = fixture.PokemonActivityTests.actor

    def setUp(self):self.world()

    def world(self, leader='페르시온', follower='나옹', leader_level=30, follower_level=80, *, owned=False):
        self.e = Engine(self.r, seed=5)
        self.owner = self.actor('actual-owner', 'trainer')
        self.leader = self.pokemon('leader', leader, leader_level, (0, 1))
        self.p = self.pokemon('follower', follower, follower_level, (0, 0))
        self.target = self.pokemon('target', '꼬부기', 100, (1, 0))
        self.target.side = self.target.spec['side'] = 'opponent'
        if owned:self.p.spec.update(trainer_id=self.owner.entity_id, wild=False, loyalty=0)
        self.e.everyone = self.e.gm.everyone = [self.owner, self.leader, self.p, self.target]
        self.e.begin_encounter(self.e.everyone)
        self.turn()

    def pokemon(self, uid, species, level, pos):
        return Combatant(self.r, build_pokemon(self.r, species, level, moves=['struggle'],
            abilities=[], wild=True, side='independent', pos=pos, extra={'id':'pokemon/'+uid}))

    def turn(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p)

    def command(self, **options):
        return self.e.pokemon_activity(self.leader, 'command_move', pokemon=self.p,
            target=self.target, move_id='struggle', set_damage=True, **options)

    def state(self):
        return deepcopy((self.e.rng.getstate(), self.e.elapsed_seconds,
            [(a.entity_id, a.spec, a.hp, a.move_uses, getattr(a,'budget',None)) for a in self.e.everyone]))

    def grant(self):GRANTS.grant(self.leader, 'capabilities', 'Pack Mon', 'fixture:pack', 'fixture')

    def test_pre_evolution_obeys_above_leader_level_without_changing_owner_or_loyalty(self):
        # A real stock Pack Mon, with its actual sourced predecessor, not type equality.
        self.assertNotIn('loyalty', self.p.spec)
        relation = deepcopy({k:self.p.spec.get(k) for k in ('trainer_id','wild','loyalty','party_location')})
        leader_state = deepcopy((self.leader.spec, self.leader.move_uses, getattr(self.leader,'budget',None)))
        hp = self.target.hp
        with patch.object(PACK, 'authorize', wraps=PACK.authorize) as authorize:
            out = self.command()
        self.assertEqual(authorize.call_count, 2)  # declaration and the real use_move gate
        self.assertEqual(out['status'], 'submitted')
        self.assertEqual(out['obedience']['relation'], 'pre_evolution')
        self.assertEqual((out['obedience']['commander_level'],out['obedience']['pokemon_level']), (30,80))
        self.assertLess(self.target.hp, hp)
        self.assertEqual((self.p.move_uses['struggle'], self.p.budget['standard']), (1,0))
        self.assertEqual((self.leader.spec, self.leader.move_uses, getattr(self.leader,'budget',None)), leader_state)
        self.assertEqual({k:self.p.spec.get(k) for k in relation}, relation)
        self.assertEqual(getattr(self.e,'_obedience_receipts',[]), [])
        self.assertEqual(self.e.use_move(self.p,self.target,'struggle'), 0)
        with self.assertRaises(ValueError):
            self.e.pokemon_activity(self.leader,'command_loyalty',target=self.p)
        with self.assertRaises(ValueError):
            self.e.pokemon_activity(self.owner,'command_move',pokemon=self.leader,target=self.target,move_id='struggle')

    def test_same_species_requires_ten_levels_and_keeps_normal_move_action_cost(self):
        for difference in (9,10,11,-10):
            with self.subTest(difference=difference):
                self.world(follower='페르시온', leader_level=30, follower_level=30-difference, owned=False)
                if difference < 10:
                    before = self.state()
                    with self.assertRaisesRegex(ValueError,'species/level'):self.command()
                    self.assertEqual(self.state(), before)
                    continue
                out = self.command()
                self.assertEqual(out['obedience']['relation'], 'same_species')
                self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']), (1,0))
                self.assertNotIn('trainer_id', self.p.spec)
                self.assertNotIn('loyalty', self.p.spec)
                before = self.state()
                self.command()  # obedience cannot create another Standard action
                self.assertEqual(self.state(), before)

    def test_actual_lineage_rejects_other_families_siblings_and_wrong_branch(self):
        cases = [('리자몽','파이리',True), ('리자몽','꼬부기',False),
                 ('뷰티플라이','실쿤',True), ('뷰티플라이','카스쿤',False),
                 ('샤미드','부스터',False), ('실쿤','뷰티플라이',False)]
        for leader,follower,obeys in cases:
            with self.subTest(leader=leader,follower=follower):
                self.world(leader,follower,leader_level=30,follower_level=40)
                self.grant()
                if obeys:
                    out=self.command();self.assertEqual(out['obedience']['relation'],'pre_evolution')
                    self.assertEqual(self.p.move_uses['struggle'],1)
                else:
                    before=self.state()
                    with self.assertRaisesRegex(ValueError,'species/level'):self.command()
                    self.assertEqual(self.state(),before)

    def test_native_evolution_and_restored_current_levels_change_command_eligibility(self):
        self.world(follower_level=40)
        self.assertEqual(self.command()['obedience']['relation'],'pre_evolution')
        self.e.end_of_turn(self.p)
        result=GROWTH.evolve_combatant(self.e,self.p,'페르시온')
        self.assertTrue(result['evolved'])
        self.assertEqual(self.p.spec['species'],'pokemon/페르시온')
        self.e=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=WORLD.actor_index(self.e)
        self.owner,self.leader,self.p,self.target=[index[a.entity_id] for a in (self.owner,self.leader,self.p,self.target)]
        self.turn();before=self.state()
        with self.assertRaisesRegex(ValueError,'species/level'):self.command()
        self.assertEqual(self.state(),before)
        self.leader.level=50  # the current actor level is the existing spec-backed property
        self.assertEqual(self.command()['obedience']['relation'],'same_species')
        self.assertNotIn('trainer_id', self.p.spec)
        self.assertNotIn('loyalty', self.p.spec)

    def test_live_source_identity_and_transient_authority_are_rechecked_without_leaks(self):
        self.world('리자몽','파이리');self.grant()
        before=self.state();detached=copy(self.leader)
        with self.assertRaisesRegex(ValueError,'actual registered'):
            self.e.pokemon_activity(detached,'command_move',pokemon=self.p,target=self.target,move_id='struggle')
        self.assertEqual(self.state(),before)
        selected=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid,*a,**k:'foreign/pack' if uid==PACK.SOURCE else selected(uid,*a,**k)):
            with self.assertRaisesRegex(ValueError,'selected recipe'):self.command()
        self.assertEqual(self.state(),before)
        with self.assertRaisesRegex(ValueError,'loyalty or control-tool options'):
            self.command(obedience_options={'dc_override':0})
        self.assertEqual(self.state(),before)
        real_use=self.e.use_move
        hp=self.target.hp;rng=self.e.rng.getstate();budget=deepcopy(self.p.budget)
        def lose_capability(*args,**options):
            GRANTS.revoke(self.leader,'fixture:pack')
            return real_use(*args,**options)
        with patch.object(self.e,'use_move',side_effect=lose_capability):
            with self.assertRaisesRegex(ValueError,'current Pack Mon'):self.command()
        self.assertEqual((self.target.hp,self.e.rng.getstate(),self.p.budget),(hp,rng,budget))
        self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[])
        self.grant()
        with patch.object(self.e,'use_move',side_effect=RuntimeError('actual downstream failure')):
            with self.assertRaisesRegex(RuntimeError,'downstream'):self.command()
        self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[])
        self.assertEqual((self.target.hp,self.e.rng.getstate(),self.p.budget),(hp,rng,budget))
        # A wild Pokemon may act autonomously after a failed command; no receipt
        # is needed, and the ordinary move still spends its real Standard action.
        self.e.use_move(self.p,self.target,'struggle',set_damage=True)
        self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
