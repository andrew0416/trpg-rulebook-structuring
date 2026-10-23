"""C11-140: three actual heads consume existing body and native movement owners."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import actor_templates as T, body_state as BODY, movement_actions as MOVE
import forced_movement as FORCED, turn as TURN, state_codec as CODEC


class HydreigonMultipartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 1140)
        self.e.grid = Grid(60, 50)
        self.heads = []
        for i, position in enumerate(((10, 10), (10, 22), (10, 34))):
            spec = build_pokemon(self.r, '삼삼드래', 50, abilities=[],
                moves=['move/몸통박치기'] if i == 0 else ['move/불꽃세례'], pos=position,
                extra={'id': 'pokemon/head-'+str(i), 'movement': {'land': 4, 'teleport': 10},
                       'movement_basis': 'current'})
            actor = Combatant(self.r, spec)
            self.e.gm.add_combatant(actor, side='foes', reason='actual independently imported head')
            self.heads.append(actor)
        self.target = Combatant(self.r, build_trainer(self.r, 'actual target', 20,
            dict(hp=20, atk=10, **{'def': 10}, spa=10, spd=10, spe=10), abilities=[], pos=(21, 10)))
        self.e.gm.add_combatant(self.target, side='party', reason='actual mapped opponent')
        self.horizontal = [(x, 0) for x in range(4)]
        self.footprints = {actor.entity_id: self.horizontal for actor in self.heads}

    def adopt(self, **options):
        args = dict(parent_id='hydreigon', part_ids=[a.entity_id for a in self.heads],
            spatial_profile='hydreigon', part_footprints=self.footprints,
            reason='GM adopts the printed three-head spatial sample')
        args.update(options)
        return self.e.gm.set_multipart_entity(**args)

    def next_turn(self, actor):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor)

    def relocate(self, destinations=None):
        return self.e.gm.relocate_multipart_entity(parent_id='hydreigon',
            destinations=destinations if destinations is not None else {
                a.entity_id: (30, 10+12*i) for i, a in enumerate(self.heads)},
            reason='GM observes the entire Hydreigon at these three new starting positions')

    def snapshot(self): return deepcopy(self.e.export_state())

    def test_actual_adoption_uses_three_existing_bodies_and_keeps_native_actor_state(self):
        native = [(a.entity_id, a.hp, deepcopy(a.stats), list(a.moves), list(a.abilities),
                   self.e.initiative_value(a).value) for a in self.heads]
        self.footprints[self.heads[1].entity_id] = [(0, y) for y in (-1, 0, 1, 2)]
        view = self.adopt()
        self.assertEqual(view['part_ids'], [a.entity_id for a in self.heads])
        self.assertEqual(view['location'], {'kind': 'unknown'})
        self.assertNotIn('hp', self.e._physical_objects['hydreigon'])
        for actor, part, original in zip(self.heads, view['parts'], native):
            self.assertEqual(len(part['footprint']['cells']), 4)
            self.assertEqual((actor.entity_id, actor.hp, actor.stats, actor.moves, actor.abilities,
                              self.e.initiative_value(actor).value), original)
            self.assertEqual(part['location'], actor.location)
        self.assertEqual(len(self.e.everyone), 4)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_invalid_source_admission_is_atomic_and_ordinary_multipart_has_no_region(self):
        invalid = [dict(part_ids=[a.entity_id for a in self.heads[:2]]),
            dict(part_ids=[self.heads[0].entity_id]*3),
            dict(part_ids=[self.heads[0].entity_id, self.heads[1].entity_id, self.target.entity_id]),
            dict(part_footprints={self.heads[0].entity_id: self.horizontal}),
            dict(part_footprints={a.entity_id: [(0, 0), (1, 0), (0, 1), (1, 1)] for a in self.heads}),
            dict(spatial_profile='unreviewed')]
        for options in invalid:
            with self.subTest(options=options):
                before = self.snapshot()
                with self.assertRaises(ValueError): self.adopt(**options)
                self.assertEqual(self.snapshot(), before)
        self.e.gm.set_multipart_entity(parent_id='ordinary',
            part_ids=[a.entity_id for a in self.heads], reason='ordinary independent multipart')
        self.assertTrue(BODY.can_place(self.e, self.heads[0], (40, 10)))
        self.assertNotIn('spatial_profile', self.e._physical_objects['ordinary'])

    def test_region_uses_original_grid_anchor_and_body_owner_preserves_shape_constraints(self):
        self.adopt(); head = self.heads[0]
        self.assertTrue(BODY.can_place(self.e, head, (17, 10)))
        self.assertTrue(BODY.can_place(self.e, head, (17, 17)))
        self.assertFalse(BODY.can_place(self.e, head, (18, 10)))
        self.assertFalse(BODY.can_place(self.e, head, (10, 18)))
        self.e.grid.blocking.add((20, 10))
        self.assertFalse(BODY.can_place(self.e, head, (17, 10)))
        self.e.grid.blocking.clear()
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.e.gm.set_position(head, (18, 10), reason='single-head observation cannot reset the starting region')
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ValueError):
            self.e.gm.set_footprint(head, [(0, 0)], reason='cannot erase three source head cells')
        self.assertEqual(self.snapshot(), before)

    def test_native_approach_pays_each_turn_and_cannot_refill_seven_metre_region(self):
        self.adopt(); head = self.heads[0]
        self.e.gm.set_position(self.heads[1], (17, 17), reason='another actual head remains a distinct body within both regions')
        import burrow_tunnels as TUNNELS
        probe = TUNNELS.at_origin(self.e, head, (11, 10))
        self.assertIsNot(probe, head)
        self.assertTrue(BODY.can_place(self.e, probe, (12, 10), origin=(11, 10)))
        self.assertFalse(BODY.can_place(self.e, probe, (17, 17)))
        self.e.grid.blocking.update((x, y) for x in range(60) for y in (9, 11))
        self.next_turn(head)
        result = self.e.approach(head, self.target, movement_mode='land')
        self.assertEqual((result['distance'], head.pos, head.budget['shift']), (4, (14, 10), 0))
        self.e.end_of_turn(head); self.next_turn(head)
        result = self.e.approach(head, self.target, movement_mode='land')
        self.assertEqual((result['distance'], head.pos), (3, (17, 10)))
        self.adopt()
        self.assertEqual(T.multipart_projection(self.e, 'hydreigon')['spatial_profile']['origins'][head.entity_id]['cell'], (10, 10))
        self.target.pos = (22, 10)
        self.e.end_of_turn(head); self.next_turn(head)
        self.e.approach(head, self.target, movement_mode='land')
        self.assertEqual(head.pos, (17, 10))
        self.assertEqual(head.budget['shift'], 0)

    def test_native_transfer_and_forced_movement_consume_the_same_head_region(self):
        self.adopt(); head = self.heads[0]; self.target.pos = (40, 10); self.next_turn(head)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            MOVE.teleport(self.e, head, (18, 10), surface_contact=True, reason_text='outside its stretch region')
        self.assertEqual(self.snapshot(), before)
        self.e.gm.set_position(head, (16, 10), reason='actual in-region position before displacement')
        budget = deepcopy(head.budget)
        result = FORCED.displace(self.e, self.target, head, direction=(1, 0), distance=3, source='actual forced displacement')
        self.assertEqual((result['moved'], result['stopped_by'], head.pos), (1, 'collision', (17, 10)))
        self.assertEqual(head.budget, budget)
        self.assertEqual(T.multipart_projection(self.e, 'hydreigon')['spatial_profile']['origins'][head.entity_id]['cell'], (10, 10))

    def test_native_disengage_rejects_outside_region_before_cost_and_accepts_inside(self):
        self.adopt(); head = self.heads[0]
        self.target.pos = (40, 10)
        self.e.gm.set_position(head, (17, 10), reason='actual region boundary')
        self.next_turn(head); before = self.snapshot()
        with self.assertRaises(ValueError): TURN.disengage(self.e, head, (18, 10), movement_mode='land')
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(TURN.disengage(self.e, head, (16, 10), movement_mode='land'))
        self.assertEqual((head.pos, head.budget['shift']), ((16, 10), 0))

    def test_native_disengage_checks_nonanchor_body_clearance_for_ordinary_actor(self):
        head = self.heads[0]
        self.e.gm.set_footprint(head, self.horizontal, reason='ordinary imported four-cell body')
        self.e.grid.blocking.add((14, 10))
        self.next_turn(head); before = self.snapshot()
        with self.assertRaises(ValueError): TURN.disengage(self.e, head, (11, 10), movement_mode='land')
        self.assertEqual(self.snapshot(), before)

    def test_whole_relocation_updates_all_native_locations_and_only_the_starting_origins(self):
        self.adopt(); head = self.heads[0]; self.next_turn(head)
        self.e.gm.set_position(head, (17, 10), reason='head at the old region edge')
        budgets = [(hasattr(a, 'budget'), deepcopy(getattr(a, 'budget', None))) for a in self.heads]
        native = [(a.hp, deepcopy(a.stats), list(a.moves), list(a.abilities)) for a in self.heads]
        view = self.relocate()
        for i, actor in enumerate(self.heads):
            self.assertEqual(actor.pos, (30, 10+12*i))
            self.assertEqual(view['spatial_profile']['origins'][actor.entity_id], actor.location)
            self.assertEqual((actor.hp, actor.stats, actor.moves, actor.abilities), native[i])
            self.assertEqual((hasattr(actor, 'budget'), getattr(actor, 'budget', None)), budgets[i])
            self.assertTrue(BODY.can_place(self.e, actor, (37, 10+12*i)))
            self.assertFalse(BODY.can_place(self.e, actor, (38, 10+12*i)))
        self.assertEqual(view['location'], {'kind': 'unknown'})
        self.assertEqual(len(self.e.everyone), 4)

    def test_partial_foreign_overlapping_or_blocked_whole_relocation_is_atomic(self):
        self.adopt()
        valid = {a.entity_id: (30, 10+12*i) for i, a in enumerate(self.heads)}
        variants = [{a.entity_id: valid[a.entity_id] for a in self.heads[:2]},
            dict(valid, **{self.target.entity_id: (40, 40)}),
            {uid: (30, 10) for uid in valid},
            dict(valid, **{self.heads[0].entity_id: (59, 10)}),
            dict(valid, **{self.heads[0].entity_id: (True, 10)})]
        for destinations in variants:
            with self.subTest(destinations=destinations):
                before = self.snapshot()
                with self.assertRaises(ValueError): self.relocate(destinations)
                self.assertEqual(self.snapshot(), before)
        self.e.grid.blocking.add((33, 10)); before = self.snapshot()
        with self.assertRaises(ValueError): self.relocate(valid)
        self.assertEqual(self.snapshot(), before)

    def test_new_origins_survive_gm_and_json_restore_and_reject_invalid_saved_profile(self):
        self.adopt(); self.relocate(); self.e.gm.snapshot('relocated-heads')
        expected = T.multipart_projection(self.e, 'hydreigon')
        self.relocate({a.entity_id: (45, 10+12*i) for i, a in enumerate(self.heads)})
        self.e.gm.restore('relocated-heads')
        self.assertEqual(T.multipart_projection(self.e, 'hydreigon'), expected)
        loaded = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
        self.assertEqual(T.multipart_projection(loaded, 'hydreigon'), expected)
        actor = next(a for a in loaded.everyone if a.entity_id == self.heads[0].entity_id)
        self.assertTrue(BODY.can_place(loaded, actor, (37, 10)))
        self.assertFalse(BODY.can_place(loaded, actor, (38, 10)))
        payload = loaded.export_state(); changed = 0
        for node in payload['nodes'].values():
            if node['kind'] == 'dict':
                for item in node['items']:
                    if item == ['source_id', 'C11-140']:
                        item[1] = 'C11-139'; changed += 1
        self.assertEqual(changed, 1)
        with self.assertRaises(CODEC.StateCodecError): Engine.import_state(self.r, payload)

    def test_late_whole_relocation_publication_failure_preserves_original_graph_and_rng(self):
        self.adopt(); before = self.snapshot(); original = type(self.e.gm)._rec
        objects = self.e._physical_objects; row = objects['hydreigon']; specs = [a.spec for a in self.heads]
        def fail_last(gm, action, *args, **kwargs):
            if action == 'multipart relocation': raise ValueError('injected final relocation record')
            return original(gm, action, *args, **kwargs)
        with patch.object(type(self.e.gm), '_rec', new=fail_last):
            with self.assertRaisesRegex(ValueError, 'final relocation'): self.relocate()
        self.assertEqual(self.snapshot(), before)
        self.assertIs(self.e._physical_objects, objects)
        self.assertIs(objects['hydreigon'], row)
        for actor, spec in zip(self.heads, specs): self.assertIs(actor.spec, spec)


if __name__ == '__main__': unittest.main(verbosity=2)
