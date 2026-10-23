"""One actual CSV intake/activation sharing D16's accepted native close boundary."""
from copy import copy, deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest

import combat_timing as TIMING
import effect_contracts as CONTRACTS
import food_effects as FOOD
import frequency as FREQ
import state_codec as CODEC
import world_entities as WORLD
from rulings import Rulings
import test_csv_food_common_intake as _fixture_test_csv_food_common_intake
import test_historical_csv_food_boundaries as _fixture_test_historical_csv_food_boundaries
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts

SOURCE = 'authored/audit/csv-sweet-expiry'
ROOT = Path(__file__).resolve().parents[1]
if not (ROOT/'data').is_dir() or not (ROOT/'output').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')


class CsvSweetPendingTurnEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass()

    fixture = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.fixture
    intake = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.intake
    buff = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.buff
    restored = _fixture_test_csv_food_common_intake.CsvFoodCommonIntake.restored

    def test_public_sweet_expiry_waits_for_pending_close_then_gm_json_resolves_once(self):
        e, actor, other = self.fixture('item/단맛-과자')
        # Isolate the explicitly authored trigger registration from ordinary rules.
        r = copy(e.r); r.ruleset = deepcopy(e.r.ruleset); r.selection = copy(e.r.selection)
        r.selection.filter = r.ruleset; r.rulings = Rulings()
        e.r = r; e.rulings = r.rulings
        for participant in WORLD.actor_index(e).values():participant.r = r
        actor.spec['nature'] = _fixture_test_historical_csv_food_boundaries.HistoricalCsvFoodBoundaries().nature_for('liked')
        self.intake(e, actor, 'item/단맛-과자')
        buff = self.buff(actor, 'item/단맛-과자')
        e.start_round([actor, other]); e.start_of_turn(actor, initiative_count=20)
        e.consume_food_buff(actor, buff_id=buff['id'])
        self.assertEqual((FOOD.slots(actor), len(actor.spec['food_consumption_receipts'])), (0, 1))
        self.assertEqual(TIMING.records(actor)[0]['evasion_modifier'], 2)
        e.end_of_turn(actor); e.end_round()
        e.start_round([actor, other]); e.start_of_turn(actor, initiative_count=20)
        reference = {'file':'input/ch07-combat.md',
                     'sha256':sha256((ROOT/'input/ch07-combat.md').read_bytes()).hexdigest()}
        r.register_source_policy_definitions([dict(id=SOURCE, title='Authored Sweet expiry boundary diagnostic',
            source=reference, locator={'lines':[1,1]}, tags=[],
            rationale='Application-authored admitted trigger diagnostic; no native rule clause is asserted')])
        frequency = dict(raw='장면 - 자유 행동', kind='scene', uses=1, action='free')
        declaration = dict(name='Authored accepted condition at CSV Sweet expiry',
            spec={'event':'turn_end'}, frequency=frequency, usage_key=SOURCE,
            effects=[dict(type='stage_change', stat='def', delta=1, target='self',
                          **{'if':'target was asleep'})],
            _feat=True, activation_header={'id':SOURCE,'frequency':frequency})
        actor.active_effects.register_definition_row(e, 'external-row:'+SOURCE, 'ability_triggers', declaration)
        self.assertEqual(e.end_of_turn(actor)['status'], 'awaiting_input')
        token, pending = next((t,row) for t,row in e._effect_dispatch_receipts.items()
                              if row['status']=='condition_unknown')
        self.assertEqual(pending['condition_request']['boundary'], CONTRACTS.boundary(e,actor,actor))
        self.assertEqual(len(e._turn_closures), 1)
        self.assertEqual(len(TIMING.records(actor)), 1)
        self.assertEqual(actor.spec['items']['item/단맛-과자'], 1)
        e.gm.snapshot('csv-sweet-pending-expiry')
        e.resolve_effect_condition(actor, token, target_was_asleep=True,
                                  reason='actual accepted historical condition observation')
        self.assertFalse(TIMING.records(actor))
        self.assertEqual(len(e._turn_closures), 2)
        e.gm.restore('csv-sweet-pending-expiry', reason='restore the original pending Sweet expiry')
        e = self.restored(e); actor = WORLD.actor_index(e)[actor.entity_id]
        token=next(t for t,row in e._effect_dispatch_receipts.items() if row['status']=='condition_unknown')
        self.assertEqual(len(TIMING.records(actor)), 1)
        self.assertEqual(len(e._turn_closures), 1)
        e.resolve_effect_condition(actor, token, target_was_asleep=True,
                                  reason='actual accepted historical condition observation')
        self.assertFalse(TIMING.records(actor))
        self.assertIsNone(e._active_turn_actor)
        self.assertEqual((len(e._turn_closures), FOOD.slots(actor), actor.stages['def']), (2,0,1))
        self.assertEqual(actor.spec['items']['item/단맛-과자'], 1)
        self.assertEqual(len(actor.spec['food_consumption_receipts']), 1)
        self.assertEqual(FREQ.state(actor)['activations'][SOURCE]['used'], 1)
        before = CODEC.dump_engine(e)
        e.resolve_effect_condition(actor, token, target_was_asleep=True,
                                  reason='actual accepted historical condition observation')
        self.assertEqual(CODEC.dump_engine(e), before)
        self.restored(e)

