"""Emit a native save with the exact pre-repair Cannon registration shape."""
import json
import sys
from pathlib import Path

ROOT = Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
from test_category2_csv_remaining_item_contracts import RemainingCsvItemContractTests
import items
import turn
import csv_item_physical_contracts as csv
from unittest.mock import patch

RemainingCsvItemContractTests.setUpClass()
f = RemainingCsvItemContractTests()
actor = f.trainer('legacy-cannon-owner')
engine = f.fixture(actor)
f.physical(engine, actor, 'legacy-cannon-object', 'item/몬스터볼-캐논')
items.register_item(engine, actor, 'item/몬스터볼-캐논', source_instance_id='legacy-cannon-object')
registration = next(v for v in actor._item_reg.values() if v['instance_id'] == 'legacy-cannon-object')
key = registration.pop('cannon_weapon_key')
turn.unequip_weapon(engine, actor, key)
engine.r.moves.pop(key)
engine.r.moves_mech.pop(key)
with patch.object(csv, 'validate_world', return_value=True):
    print(json.dumps(engine.export_state(), ensure_ascii=False))
