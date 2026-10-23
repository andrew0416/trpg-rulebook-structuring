"""Independent checks of occupied body cells and paid field history."""
from copy import deepcopy
from pathlib import Path
import json
import unittest

from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
import body_state as BODY
import field_effects as FIELD
import state_codec as CODEC

ROOT = Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')


class LocalGrassIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        self.engine = Engine(self.rules, seed=63691)
        self.engine.grid = Grid(14, 14)
        self.creator = self.add('이상해씨', '곰팡이군주', (5, 5), [[0, 0]])
        # The anchor is outside burst2; the leftmost occupied cell is inside.
        self.recipient = self.add('피카츄', '정전기', (8, 5), [[0, 0], [-1, 0]])
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.creator, initiative_count=20)

    def add(self, species, ability, pos, offsets):
        spec = build_pokemon(self.rules, species, 30,
                             moves=['move/덩굴채찍'], abilities=[ability])
        spec['footprint'] = {'kind': 'observed_cells', 'offsets': offsets,
                             'reason': 'independently observed full body cells'}
        actor = Combatant(self.rules, spec)
        self.engine.gm.add_combatant(actor, pos=pos, side='party',
                                     reason='mapped independent field participant')
        return actor

    def activate(self):
        return self.engine.activate_ability(self.creator, FIELD.LOCAL_SOURCE,
                                            self.creator, request_id='independent/grass')

    def test_body_intersection_and_paid_field_survives_source_loss_and_recall(self):
        receipt = self.activate()
        self.assertNotIn(list(self.recipient.pos), receipt['cells'])
        self.assertTrue(BODY.cells(self.recipient).intersection(map(tuple, receipt['cells'])))
        self.assertEqual(FIELD.terrain_for(self.engine, self.recipient)['request_id'],
                         'independent/grass')
        self.engine.gm.set_position(self.creator, (11, 11), reason='fixed field creator moves')
        self.engine.gm.set_ability(self.creator, '곰팡이군주', add=False,
                                   reason='remove current creator ability after paid activation')
        self.engine.gm.faint(self.creator, reason='field survives creator fainting')
        self.engine.gm.recall(self.creator, reason='field survives creator recall')
        self.assertFalse(self.creator.on_field)
        self.assertEqual(FIELD.validate_local(self.engine)[0], receipt)
        move = self.rules.move('move/덩굴채찍')
        self.assertEqual(FIELD.damage_roll_modifier(self.engine, self.recipient,
                                                    self.creator, move, '풀'), 10)
        payload = json.loads(json.dumps(self.engine.export_state()))
        loaded = Engine.import_state(Rules(str(ROOT), ruleset='core'), payload)
        recipient = next(a for a in loaded.everyone if a.entity_id == self.recipient.entity_id)
        self.assertEqual(FIELD.terrain_for(loaded, recipient)['request_id'], 'independent/grass')
        self.engine.end_scene(round_elapsed_seconds=0)
        self.assertIsNone(FIELD.terrain_for(self.engine, self.recipient))
        self.engine.gm.send_out(self.creator, pos=(5, 5), reason='new scene return')
        self.engine.gm.set_ability(self.creator, '곰팡이군주', reason='restore original ability')
        self.engine.gm.set_hp(self.creator, value=self.creator.max_hp, reason='recover for new scene')
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.creator, initiative_count=20)
        next_receipt = self.engine.activate_ability(self.creator, FIELD.LOCAL_SOURCE,
                                                   self.creator, request_id='independent/next-scene')
        self.assertGreater(next_receipt['scene'], receipt['scene'])
        self.assertEqual(len(FIELD.validate_local(self.engine)), 1)

    def test_valid_actor_with_no_source_payment_cannot_claim_resealed_receipt(self):
        self.activate()
        self.engine.gm.snapshot('paid-field')
        before = CODEC.dump_engine(self.engine)
        snapshot = self.engine.gm.snapshots['paid-field']['engine'][FIELD.LOCAL_KEY]
        original = deepcopy(snapshot)
        row = snapshot['receipts']['independent/grass']
        row['creator_id'] = self.recipient.entity_id
        row['seal'] = FIELD._local_seal(row)
        with self.assertRaisesRegex(ValueError, 'Scene payment'):
            self.engine.gm.restore('paid-field')
        self.assertEqual(CODEC.dump_engine(self.engine), before)
        snapshot.clear()
        snapshot.update(original)
        saved = deepcopy(getattr(self.engine, FIELD.LOCAL_KEY))
        # Retain the codec's actual envelope, replacing only encoded live nodes.
        payload = deepcopy(self.engine.export_state())
        row = getattr(self.engine, FIELD.LOCAL_KEY)['receipts']['independent/grass']
        row['creator_id'] = self.recipient.entity_id
        row['seal'] = FIELD._local_seal(row)
        encoder = CODEC._Encoder(self.engine)
        payload['root'] = encoder.value(self.engine)
        payload['nodes'] = encoder.nodes
        setattr(self.engine, FIELD.LOCAL_KEY, saved)
        with self.assertRaises(ValueError):
            Engine.import_state(Rules(str(ROOT), ruleset='core'), payload)
        self.assertEqual(CODEC.dump_engine(self.engine), before)


if __name__ == '__main__':
    unittest.main()
