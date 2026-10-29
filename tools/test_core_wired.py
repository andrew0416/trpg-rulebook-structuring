"""Core Wired's actual electronic route and GM-device native Move consumer."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Rules, Engine, Combatant
from builder import build_pokemon
import control_remote as REMOTE
import wired_capability as WIRED
import state_grants as GRANTS
import move_state as MOVES
import frequency as FREQ
import world_entities as WORLD
import state_codec as CODEC

ROOT = Path(__file__).resolve().parents[1]


class CoreWiredTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, seed=5)
        self.p = self.pokemon('operator', '로토무', (0, 0))
        self.target = self.pokemon('target', '잠만보', (0, 1))
        self.target.side = self.target.spec['side'] = 'opponent'
        self.e.everyone = self.e.gm.everyone = [self.p, self.target]
        self.e.begin_encounter(self.e.everyone)
        self.e.start_round(self.e.everyone); self.e.start_of_turn(self.p)
        self.device('device/A'); self.device('device/B')

    def pokemon(self, uid, species, pos):
        p = Combatant(self.r, build_pokemon(self.r, species, 50, moves=['struggle'],
            abilities=[], wild=True, side='independent', pos=pos, extra={'id':'pokemon/'+uid}))
        GRANTS.set_baseline(p, 'capabilities', ['접속'])
        return p

    def device(self, uid):
        WORLD.register_object(self.e, uid, location={'kind':'unknown'}, reason='actual electronic appliance')
        WORLD.register_object(self.e, uid+'/cord', location={'kind':'unknown'}, reason='actual physical cord')
        WIRED.observe_device(self.e, uid, electronic=True, reason='GM observes actual electronic device')

    def connect(self, device='device/A', route='route/A', *, actor=None, cord=True):
        actor = actor or self.p
        if cord:WIRED.observe_cord(self.e, actor, device, device+'/cord', connected=True, reason='actual plugged cord')
        links = dict(devices=[device+'/cord'], avatar_id=None, node_id=None,
            recipient_id=None, communication_source=None, component_id=None)
        return self.e.connect_remote_control(actor, device, WIRED.native(), links,
            route_id=route, connected=True, reason='observed actual electronic connection')

    def allow(self, moves, device='device/A'):
        return WIRED.allow_moves(self.e, device, moves, reason='explicit GM Moves for this actual device')

    def turn(self):
        self.e.end_of_turn(self.p); self.e.start_round(self.e.everyone); self.e.start_of_turn(self.p)

    def test_actual_nonvehicle_connection_requires_current_cord_and_grants_no_machine_commands_or_cost(self):
        self.p.spec['species'] = '폴리곤'
        before = CODEC.dump_engine(self.e)
        with self.assertRaisesRegex(ValueError, 'cord'):self.connect(cord=False)
        self.assertEqual(before, CODEC.dump_engine(self.e))
        budget = deepcopy(self.p.budget)
        self.connect(); self.connect('device/B', 'route/B')
        self.assertEqual(self.p.budget, budget)
        self.assertEqual([r['status'] for r in self.e.remote_control_routes(self.p).values()], ['live', 'live'])
        self.assertEqual(REMOTE.permission(self.e, self.p, 'device/A', 'route/A'),
            {'body':False, 'pilot_requirements':False, 'weapons':False})
        for command in ('move', 'fire'):
            with self.assertRaisesRegex(ValueError, 'command exceeds'):
                REMOTE.permission(self.e, self.p, 'device/A', 'route/A', command)
        self.allow(['파괴광선'])
        self.assertNotIn('move/파괴광선', self.p.moves)
        self.assertNotIn('owner_id', self.e._physical_objects['device/A'])

    def test_rotom_device_specific_exact_gm_moves_use_native_action_and_never_learn_slots(self):
        self.connect(); self.connect('device/B', 'route/B')
        self.assertNotIn('move/파괴광선', self.p.moves)
        self.allow([]); self.assertNotIn('move/파괴광선', self.p.moves)
        self.allow(['파괴광선']); self.allow(['냉동빔'], 'device/B')
        self.assertIn('move/파괴광선', self.p.moves)
        self.assertNotIn('move/파괴광선', MOVES.owned_list(self.p.spec, 'moves', self.p.moves,rules=self.p.r))
        with self.assertRaisesRegex(ValueError, 'permission'):
            WIRED.use_move(self.e, self.p, self.target, 'move/화염방사', route_id='route/A')
        with self.assertRaisesRegex(ValueError, 'permission'):
            WIRED.use_move(self.e, self.p, self.target, 'move/파괴광선', route_id='route/B')
        WIRED.use_move(self.e, self.p, self.target, 'move/파괴광선', route_id='route/A')
        self.assertEqual(self.p.move_uses['move/파괴광선'], 1)
        self.assertEqual(self.p.budget['standard'], 0)
        self.e.disconnect_remote_control(self.p, 'route/B', reason='actual B cord disconnect')
        self.assertNotIn('move/냉동빔', self.p.moves)
        self.assertIn('move/파괴광선', self.p.moves)
        before = CODEC.dump_engine(self.e)
        for values in (['missing move'], ['파괴광선', '파괴광선'], ['struggle']):
            with self.assertRaises(ValueError):self.allow(values)
            self.assertEqual(before, CODEC.dump_engine(self.e))

    def test_current_species_capability_device_and_cord_losses_revoke_only_dependent_permissions(self):
        self.connect(); self.allow(['파괴광선', '냉동빔'])
        self.e.gm.set_move(self.p, 'move/냉동빔', reason='independent learned Move')
        def changed(e, p):p.spec['species'] = '폴리곤'
        GRANTS.transition(self.e, self.p, changed)
        self.assertNotIn('move/파괴광선', self.p.moves)
        self.assertIn('move/냉동빔', self.p.moves)
        self.assertEqual(self.e.remote_control_routes(self.p)['route/A']['status'], 'live')
        GRANTS.transition(self.e, self.p, lambda e, p:p.spec.update(species='로토무'))
        self.assertIn('move/파괴광선', self.p.moves)
        GRANTS.transition(self.e, self.p, lambda e, p:GRANTS.set_baseline(p, 'capabilities', []))
        self.assertNotIn('move/파괴광선', self.p.moves)
        self.assertIn('move/냉동빔', self.p.moves)
        self.assertEqual(self.e.remote_control_routes(self.p)['route/A']['status'], 'closed')
        GRANTS.transition(self.e, self.p, lambda e, p:GRANTS.set_baseline(p, 'capabilities', ['접속']))
        self.connect(route='route/new')
        WIRED.observe_cord(self.e, self.p, 'device/A', 'device/A/cord', connected=False, reason='actual unplugged cord')
        self.assertEqual(self.e.remote_control_routes(self.p)['route/new']['status'], 'closed')
        self.connect(route='route/final')
        self.e._physical_objects['device/A']['disabled'] = True
        self.assertEqual(self.e.remote_control_routes(self.p)['route/final']['status'], 'closed')
        # Free/non-counting calls must still reach the new native admission.
        with self.assertRaisesRegex(ValueError, 'permission'):
            self.e.use_move(self.p, self.target, 'move/파괴광선', count_use=False, free_action=True)
        with self.assertRaisesRegex(ValueError, 'permission'):
            self.e.use_move(self.p, self.target, 'move/파괴광선', count_use=False, free_action=True)
        self.assertNotIn('move/파괴광선', self.p.moves)
        self.assertIn('move/냉동빔', self.p.moves)
        self.assertEqual(self.e.remote_control_routes(self.p)['route/final']['status'], 'closed')
        self.e.use_move(self.p, self.target, 'move/냉동빔')
        self.assertEqual(self.p.move_uses['move/냉동빔'], 1)
        # A different native child Move was never borrowed from Wired. Existing
        # non-counting admission remains unchanged after all Wired routes close.
        self.e.use_move(self.p, self.target, 'move/전기쇼크', count_use=False, free_action=True)
        # An independently granted permission for the exact old borrowed ID
        # remains valid and is never removed along with the Wired source.
        GRANTS.grant_moves(self.p, ['파괴광선'], 'fixture:independent-native', 'effect', mode='permission')
        self.e.use_move(self.p, self.target, 'move/파괴광선', count_use=False, free_action=True)
        self.assertIn('fixture:independent-native', self.p.spec['state_grants']['sources'])

    def test_route_and_gm_list_changes_preserve_native_usage_and_independent_sources(self):
        self.connect(); self.allow(['파괴광선'])
        self.e.use_move(self.p, self.target, 'move/파괴광선')
        use_state = deepcopy((self.p.move_uses, self.p.spec['frequency_state']))
        self.e.disconnect_remote_control(self.p, 'route/A', reason='actual cable temporarily unplugged')
        self.connect(route='route/reconnected')
        self.allow([]); self.allow(['파괴광선'])
        self.assertEqual((self.p.move_uses, self.p.spec['frequency_state']), use_state)
        self.assertFalse(FREQ.move_allowed(self.e, self.p, 'move/파괴광선')[0])
        self.turn(); before = (deepcopy(self.p.budget), self.e.rng.getstate())
        self.e.use_move(self.p, self.target, 'move/파괴광선')
        self.assertEqual((self.p.budget, self.e.rng.getstate()), before)
        self.assertEqual(self.p.move_uses['move/파괴광선'], 1)
        # A different physical device and route share the actor's Move pool.
        self.allow(['파괴광선'], 'device/B'); self.connect('device/B', 'route/B')
        self.assertFalse(FREQ.move_allowed(self.e, self.p, 'move/파괴광선')[0])

    def test_cord_endpoint_change_identity_false_connection_and_policy_tampering_fail_closed(self):
        self.connect(); self.allow(['파괴광선'])
        WIRED.observe_cord(self.e, self.p, 'device/B', 'device/A/cord', connected=True, reason='same actual cord moved to B')
        self.assertEqual(self.e.remote_control_routes(self.p)['route/A']['status'], 'closed')
        self.assertNotIn('move/파괴광선', self.p.moves)
        before = CODEC.dump_engine(self.e)
        with self.assertRaises(ValueError):self.connect(actor=copy(self.p))
        self.assertEqual(before, CODEC.dump_engine(self.e))
        value = WIRED.native(); value['maximum'] = 1
        with self.assertRaisesRegex(ValueError, 'exact source'):REMOTE.declaration(value)
        value = WIRED.native(); value['commands'] = ['move']
        with self.assertRaisesRegex(ValueError, 'exact source'):REMOTE.declaration(value)
        WIRED.observe_device(self.e, 'device/A', electronic=False, reason='GM identifies non-electronic object')
        with self.assertRaisesRegex(ValueError, 'electronic'):self.connect(route='route/not-electronic')

    def test_json_and_gm_restore_preserve_typed_route_permissions_usage_and_reject_corruption(self):
        self.connect(); self.allow(['파괴광선']); self.e.use_move(self.p, self.target, 'move/파괴광선')
        encoded = CODEC.dump_engine(self.e)
        restored = CODEC.load_engine(self.r, json.loads(json.dumps(encoded, ensure_ascii=False)))
        p = WORLD.actor_index(restored)[self.p.entity_id]
        self.assertEqual(restored.remote_control_routes(p)['route/A']['machine_id'], 'device/A')
        self.assertIn('move/파괴광선', p.moves)
        self.assertNotIn('move/파괴광선', MOVES.owned_list(p.spec, 'moves', p.moves,rules=p.r))
        self.assertFalse(FREQ.move_allowed(restored, p, 'move/파괴광선')[0])
        self.e.gm.snapshot('wired')
        WIRED.observe_cord(self.e, self.p, 'device/A', 'device/A/cord', connected=False, reason='actual later disconnection')
        self.e.gm.restore('wired', reason='restore actual saved world')
        self.assertEqual(self.e.remote_control_routes(self.p)['route/A']['status'], 'live')
        self.assertEqual(self.p.move_uses['move/파괴광선'], 1)
        self.e._remote_control['wired']['cords']['device/A/cord']['device_id'] = 'device/B'
        with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)

    def test_actual_copy_repeat_preflight_stays_unsupported_and_never_bypasses_stale_wired_permission(self):
        mid = 'move/전기쇼크'
        for source in ('move/따라하기', 'move/지휘'):
            with self.subTest(source=source):
                self.setUp(); self.connect(); self.allow([mid])
                self.e.end_scene(self.e.everyone)
                self.assertFalse(self.e.encounter_active)
                self.e.gm.set_move(self.target, mid, reason='independent target Move')
                with patch.object(self.e, 'accuracy_check', return_value=(True, 20, False)):
                    self.e.use_move(self.p, self.target, mid)
                    self.e.use_move(self.target, self.p, mid)
                self.e.disconnect_remote_control(self.p, 'route/A', reason='actual Wired source ends')
                self.assertNotIn(mid, self.p.moves)
                owner, target = (self.p, self.target) if source == 'move/따라하기' else (self.target, self.p)
                self.e.gm.set_move(owner, source, reason='independently learned native copy/repeat Move')
                before = deepcopy((owner.moves, owner.move_uses, getattr(owner, 'budget', None),
                    owner.spec['state_grants'], self.e.rng.getstate()))
                from effect_contracts import EffectContractError
                with self.assertRaisesRegex(EffectContractError, 'unsupported_execution.*native source-bound execution consumer'):
                    self.e.use_move(owner, target, source)
                self.assertEqual(before, (owner.moves, owner.move_uses, getattr(owner, 'budget', None),
                    owner.spec['state_grants'], self.e.rng.getstate()))
                self.assertNotIn(mid, self.p.moves)
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, 'permission'):
                        self.e.use_move(self.p, self.target, mid, count_use=False)
                self.assertNotIn(mid, self.p.moves)


if __name__ == '__main__':unittest.main()
