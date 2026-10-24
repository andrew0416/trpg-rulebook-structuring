"""Native regressions for S-move2-4/S-move3-5; prepared, not yet executed."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from builder import build_pokemon
from engine import Combatant, Engine, Rules
from grid import Grid
import field_effects as FIELD
import initiative as INIT
import items as ITEMS
import state_codec as CODEC
import world_entities as WORLD

GRAVITY, MAGIC, PSYCHIC = 'move/중력', 'move/매직룸', 'move/사이코필드'
TRICK, WONDER, GRAVITAS = 'move/트릭룸', 'move/원더룸', 'move/거다이천도'
GRASS = 'move/그래스필드'


class IndependentFieldSlotsRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')

    def world(self, moves):
        engine = Engine(self.r, seed=675695710729731)
        engine.grid = Grid(30, 30)
        actor = Combatant(self.r, build_pokemon(self.r, '피카츄', 30,
            moves=moves, abilities=[]))
        target = Combatant(self.r, build_pokemon(self.r, '구구', 80,
            moves=['move/공중날기', 'move/전광석화', 'move/점프킥'], abilities=[], side='wild'))
        actor.pos, target.pos = (4, 4), (5, 4)
        actor.stats['spe'], target.stats['spe'] = 20, 5
        for member in (actor, target):
            engine.gm.add_combatant(member)
        engine.start_round(engine.everyone)
        return engine, actor, target

    def native_field(self, engine, actor, move_id):
        engine.start_of_turn(actor, initiative_count=20)
        before = actor.budget['standard']
        engine.use_move(actor, actor, move_id)
        self.assertEqual(actor.budget['standard'], before - 1)
        self.assertGreater(actor.move_uses[move_id], 0)
        engine.end_of_turn(actor)

    def rows(self, engine):
        return {row['source_id']: row for row in FIELD.active_fields(engine)}

    def equip_claw(self, engine, actor):
        uid = 'independent-fields/claw'
        WORLD.register_object(engine, uid, kind='item_instance',
            item_rule_id='item/선제공격손톱', owner_id=actor.entity_id,
            location={'kind': 'unknown'}, reason='actual field suppression fixture')
        ITEMS.register_item(engine, actor, 'item/선제공격손톱',
            source_instance_id=uid, as_held=True)
        self.assertEqual(engine._physical_objects[uid]['equipped_by'], actor.entity_id)

    def test_native_five_fields_coexist_in_both_orders_and_expire_independently(self):
        for order in ((GRAVITY, MAGIC, PSYCHIC, TRICK, WONDER),
                      (WONDER, TRICK, PSYCHIC, MAGIC, GRAVITY)):
            with self.subTest(order=order):
                engine, actor, target = self.world(list(order))
                deadlines = {}
                for index, move_id in enumerate(order):
                    if index:
                        engine.start_round(engine.everyone)
                    self.native_field(engine, actor, move_id)
                    deadlines[move_id] = engine.round_no + 5 + int(move_id == TRICK)
                self.assertEqual(set(self.rows(engine)), set(order))
                self.assertEqual(FIELD.accuracy_modifier(engine, actor), 2)
                self.assertEqual(FIELD.defense_stat(engine, target, 'def'), 'spd')
                self.assertEqual(INIT.order(engine, [actor, target]), [target, actor])
                self.assertEqual(FIELD.damage_roll_modifier(engine, actor, target,
                    self.r.move('move/염동력'), '에스퍼'), 10)
                self.assertGreater(engine.type_multiplier('땅', target)[0], 0)
                engine.start_of_turn(target, initiative_count=10)
                before = deepcopy((target.budget, target.move_uses, engine.rng.getstate()))
                self.assertEqual(engine.use_move(target, actor, 'move/전광석화'), 0)
                self.assertEqual((target.budget, target.move_uses, engine.rng.getstate()), before)
                target.spec['_movement_altitude'] = 2
                with self.assertRaisesRegex(ValueError, 'above 1 metre'):
                    engine.end_of_turn(target)
                target.spec['_movement_altitude'] = 0
                engine.end_of_turn(target)
                while engine.round_no <= max(deadlines.values()):
                    expected = {source for source, end in deadlines.items() if engine.round_no < end}
                    self.assertEqual(set(self.rows(engine)), expected)
                    for source, row in self.rows(engine).items():
                        self.assertEqual(row['rounds'], deadlines[source] - engine.round_no)
                    engine.start_round(engine.everyone)
                self.assertFalse(self.rows(engine))

    def test_native_terrain_replacement_and_same_source_refresh_leave_other_fields(self):
        engine, actor, target = self.world([PSYCHIC, GRAVITY, GRASS])
        for index, move_id in enumerate((PSYCHIC, GRAVITY, GRASS, GRAVITY)):
            if index:
                engine.start_round(engine.everyone)
            self.native_field(engine, actor, move_id)
        self.assertEqual(engine.field['source_id'], GRASS)
        self.assertEqual(set(self.rows(engine)), {GRAVITY, GRASS})
        self.assertEqual(self.rows(engine)[GRAVITY]['rounds'], 5)
        self.assertEqual(FIELD.accuracy_modifier(engine, actor), 2)
        self.assertEqual(FIELD.damage_roll_modifier(engine, actor, target,
            self.r.move('move/염동력'), '에스퍼'), 0)
        self.assertEqual(FIELD.damage_roll_modifier(engine, actor, target,
            self.r.move('move/덩굴채찍'), '풀'), 10)

    def test_native_magic_room_survives_other_fields_snapshot_and_cold_restore_until_own_expiry(self):
        engine, actor, _ = self.world([MAGIC, WONDER, PSYCHIC])
        self.equip_claw(engine, actor)
        held = deepcopy(actor.spec['held_equipment'])
        self.assertEqual(actor.initiative_bonus, 10)
        for index, move_id in enumerate((MAGIC, WONDER, PSYCHIC)):
            if index:
                engine.start_round(engine.everyone)
            self.native_field(engine, actor, move_id)
            self.assertEqual(actor.initiative_bonus, 0)
        engine.gm.snapshot('independent-fields')
        saved = deepcopy(getattr(engine, FIELD.INDEPENDENT_KEY))
        engine.gm.set_field(None, reason='explicit GM field clear')
        self.assertFalse(self.rows(engine))
        self.assertEqual(actor.initiative_bonus, 10)
        engine.gm.restore('independent-fields')
        self.assertEqual(getattr(engine, FIELD.INDEPENDENT_KEY), saved)
        self.assertEqual(actor.initiative_bonus, 0)
        loaded = Engine.import_state(self.r, json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))
        owner = WORLD.actor_index(loaded)[actor.entity_id]
        self.assertEqual(getattr(loaded, FIELD.INDEPENDENT_KEY), saved)
        for round_no in (4, 5):
            loaded.start_round(loaded.everyone)
            self.assertEqual(loaded.round_no, round_no)
            self.assertEqual(owner.initiative_bonus, 0)
        loaded.start_round(loaded.everyone)
        self.assertEqual(set(self.rows(loaded)), {WONDER, PSYCHIC})
        self.assertEqual(owner.initiative_bonus, 10)
        self.assertEqual(owner.spec['held_equipment'], held)

    def test_native_gravity_and_gravitas_keep_distinct_sides_accuracy_and_deadlines(self):
        for gravity_first in (True, False):
            with self.subTest(gravity_first=gravity_first):
                engine, room_user, enemy = self.world([GRAVITY, 'move/점프킥'])
                gmax_user = Combatant(self.r, build_pokemon(self.r, '이올브', 50,
                    moves=['move/염동력'], abilities=[]))
                gmax_user.pos = (4, 5)
                engine.gm.add_combatant(gmax_user)
                engine.begin_encounter([room_user, enemy, gmax_user])
                for first in (True, False):
                    if not first:
                        engine.start_round(engine.everyone)
                    if first == gravity_first:
                        self.native_field(engine, room_user, GRAVITY)
                    else:
                        engine.start_of_turn(gmax_user, initiative_count=15)
                        engine.enter_gigantamax(gmax_user, source_id='test/actual-gmax',
                            reason='actual independent Gravitas producer')
                        with patch.object(engine, 'd20', return_value=17):
                            engine.use_gmax_move_on(gmax_user, enemy, 'move/염동력',
                                GRAVITAS, engine.everyone, aim=enemy.pos)
                        engine.end_of_turn(gmax_user)
                self.assertEqual(set(self.rows(engine)), {GRAVITY, GRAVITAS})
                self.assertEqual(FIELD.accuracy_modifier(engine, room_user), 2)
                self.assertEqual(FIELD.native_move_block_reason(engine, 'move/공중날기', room_user), GRAVITY)
                while engine.round_no < 6:
                    engine.start_round(engine.everyone)
                remaining = GRAVITAS if gravity_first else GRAVITY
                self.assertEqual(set(self.rows(engine)), {remaining})
                self.assertEqual(FIELD.accuracy_modifier(engine, room_user), 0 if gravity_first else 2)
                self.assertEqual(FIELD.native_move_block_reason(engine, 'move/공중날기', enemy), remaining)
                self.assertEqual(FIELD.native_move_block_reason(engine, 'move/공중날기', room_user),
                    None if gravity_first else GRAVITY)
                self.assertGreater(engine.type_multiplier('땅', enemy)[0], 0)
                engine.start_of_turn(room_user, initiative_count=20)
                before = room_user.budget['standard']
                with patch.object(engine, 'd20', return_value=20):
                    result = engine.use_move(room_user, enemy, 'move/점프킥', set_damage=True)
                self.assertEqual(room_user.budget['standard'], before - int(gravity_first))
                self.assertEqual(result > 0, gravity_first)
                engine.end_of_turn(room_user)
                engine.start_of_turn(enemy, initiative_count=10)
                before = deepcopy((enemy.budget, enemy.move_uses, engine.rng.getstate()))
                self.assertEqual(engine.use_move(enemy, room_user, 'move/점프킥'), 0)
                self.assertEqual((enemy.budget, enemy.move_uses, engine.rng.getstate()), before)
                engine.end_of_turn(enemy)
                engine.start_round(engine.everyone)
                self.assertFalse(self.rows(engine))
                self.assertEqual(engine.type_multiplier('땅', enemy)[0], 0)

    def test_historical_single_slot_migrates_on_real_terrain_move_without_losing_magic_room(self):
        engine, actor, _ = self.world([MAGIC, PSYCHIC])
        self.equip_claw(engine, actor)
        self.native_field(engine, actor, MAGIC)
        # Encode the historical representation of an actually produced field.
        engine.field = getattr(engine, FIELD.INDEPENDENT_KEY).pop(MAGIC)
        delattr(engine, FIELD.INDEPENDENT_KEY)
        loaded = Engine.import_state(self.r, json.loads(json.dumps(engine.export_state(), ensure_ascii=False)))
        owner = WORLD.actor_index(loaded)[actor.entity_id]
        loaded.start_round(loaded.everyone)
        self.native_field(loaded, owner, PSYCHIC)
        self.assertEqual(set(self.rows(loaded)), {MAGIC, PSYCHIC})
        self.assertEqual(self.rows(loaded)[MAGIC]['rounds'], 4)
        self.assertEqual(owner.initiative_bonus, 0)
        loaded.gm.set_field(None, reason='explicitly end historical and current fields')
        self.assertEqual(owner.initiative_bonus, 10)

    def test_native_steel_roller_pass_ends_terrain_without_ending_magic_room(self):
        engine, actor, _ = self.world([MAGIC, GRASS, 'move/아이언롤러'])
        self.equip_claw(engine, actor)
        self.native_field(engine, actor, MAGIC)
        engine.start_round(engine.everyone)
        self.native_field(engine, actor, GRASS)
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=20)
        with patch.object(engine, 'd20', return_value=20):
            engine.use_pass_move(actor, 'move/아이언롤러', (7, 4),
                event_id='independent-fields/steel-roller', object_adjudications={},
                source='test/native-pass', reason='actual path through global Terrain')
        self.assertEqual(actor.pos, (7, 4))
        self.assertIsNone(engine.field)
        self.assertEqual(set(self.rows(engine)), {MAGIC})
        self.assertEqual(actor.initiative_bonus, 0)
        engine.end_of_turn(actor)

    def test_malformed_independent_slots_reject_save_restore_and_native_preflight_without_spend(self):
        engine, actor, _ = self.world([GRAVITY, MAGIC])
        self.native_field(engine, actor, GRAVITY)
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=20)
        valid = deepcopy(getattr(engine, FIELD.INDEPENDENT_KEY))
        for damage in ('wrong-source', 'wrong-kind', 'empty-lifetime', 'bad-mapping', 'missing-creator'):
            with self.subTest(damage=damage):
                slots = deepcopy(valid)
                if damage == 'wrong-source':
                    slots[GRAVITY]['source_id'] = MAGIC
                elif damage == 'wrong-kind':
                    slots[GRAVITY]['kind'] = 'unreviewed'
                elif damage == 'empty-lifetime':
                    slots[GRAVITY]['rounds'] = 0
                elif damage == 'bad-mapping':
                    slots = []
                else:
                    slots[GRAVITY]['creator_id'] = 'missing-owner'
                payload = engine.export_state()
                setattr(engine, FIELD.INDEPENDENT_KEY, slots)
                before = deepcopy((actor.budget, actor.move_uses, engine.rng.getstate(), slots))
                with self.assertRaises(ValueError):
                    engine.use_move(actor, actor, MAGIC)
                self.assertEqual((actor.budget, actor.move_uses, engine.rng.getstate(),
                    getattr(engine, FIELD.INDEPENDENT_KEY)), before)
                with self.assertRaises(ValueError):
                    engine.export_state()
                encoder = CODEC._Encoder(engine)
                payload['root'] = encoder.value(engine)
                payload['nodes'] = encoder.nodes
                with self.assertRaises(ValueError):
                    Engine.import_state(self.r, json.loads(json.dumps(payload, ensure_ascii=False)))
                setattr(engine, FIELD.INDEPENDENT_KEY, deepcopy(valid))
        engine.gm.snapshot('fields')
        engine.gm.snapshots['fields']['engine'][FIELD.INDEPENDENT_KEY][GRAVITY]['source_id'] = MAGIC
        before = deepcopy(getattr(engine, FIELD.INDEPENDENT_KEY))
        with self.assertRaises(ValueError):
            engine.gm.restore('fields')
        self.assertEqual(getattr(engine, FIELD.INDEPENDENT_KEY), before)


if __name__ == '__main__':
    unittest.main()
