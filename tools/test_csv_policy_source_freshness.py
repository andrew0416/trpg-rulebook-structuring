"""Public CSV reads must not reuse an earlier source-admission decision."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import csv_item_contract_policy as POLICY
import csv_item_food_contracts as FOOD
import csv_item_physical_contracts as PHYSICAL
import source_context
from engine import Rules, Combatant, Engine
from builder import build_trainer
import world_entities as WORLD
from ruleset import ExcludedRuleSelection

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = Path(tempfile.gettempdir())
STATUS = 'data/verification/category2-item-table-status.json'
MANUAL = 'item/타입-공부-메뉴얼-1'
MANUAL_CLAUSE = 'C2CSV/inventory:70:1'


class CsvPolicySourceFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Rules(str(ROOT), ruleset='core')
        cls.document = json.loads((ROOT / 'data' / POLICY.POLICY_FILE).read_text(encoding='utf-8'))

    def setUp(self):
        TEMP_ROOT.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='csv-source-', dir=TEMP_ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / 'input', self.root / 'input')
        for relative in (STATUS, 'data/' + POLICY.POLICY_FILE):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.rules = deepcopy(self.original)
        self.rules.root = str(self.root)
        for key, relative in (('inventory_file_sha256', 'input/db/inventory.csv'),
                              ('item_data_file_sha256', 'input/db/item-data.csv')):
            self.assertEqual(sha256((self.root / relative).read_bytes()).hexdigest(), self.document[key])

    def changed_bytes(self, relative):
        path = self.root / relative
        old = path.read_bytes()
        stamp = path.stat()
        path.write_bytes(bytes([old[0] ^ 1]) + old[1:])
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(path.stat().st_size, len(old))
        self.assertEqual(path.stat().st_mtime_ns, stamp.st_mtime_ns)

    def test_inventory_changed_after_cached_definition_is_rejected(self):
        self.assertEqual(POLICY.definition(self.rules, item_id=MANUAL)['item_id'], MANUAL)
        self.changed_bytes('input/db/inventory.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            POLICY.definition(self.rules, item_id=MANUAL)

    def test_item_data_changed_after_cached_clauses_is_rejected(self):
        self.assertEqual(len(POLICY.clauses(self.rules)), 34)
        self.changed_bytes('input/db/item-data.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            POLICY.clauses(self.rules)

    def test_current_registered_row_is_rechecked_after_cache(self):
        POLICY.definition(self.rules, clause_id=MANUAL_CLAUSE)
        path = self.root / STATUS
        status = json.loads(path.read_text(encoding='utf-8'))
        registered = next(row for row in status['new_clauses'] if row['clause_id'] == MANUAL_CLAUSE)
        registered['source'][0]['raw_cells_sha256'] = '0' * 64
        path.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source provenance changed'):
            POLICY.definition(self.rules, clause_id=MANUAL_CLAUSE)

    def test_missing_source_after_cache_is_rejected(self):
        POLICY.policy(self.rules)
        (self.root / 'input/db/item-data.csv').unlink()
        with self.assertRaises(OSError):
            POLICY.policy(self.rules)

    def test_public_policy_result_cannot_rewrite_next_definition(self):
        returned = POLICY.policy(self.rules)
        expected = deepcopy(returned['rows'][MANUAL_CLAUSE])
        returned['rows'][MANUAL_CLAUSE]['kind'] = 'injected_kind'
        returned['rows'][MANUAL_CLAUSE]['source_columns'].append(999)
        self.assertEqual(POLICY.definition(self.rules, clause_id=MANUAL_CLAUSE), expected)

    def test_public_definition_result_remains_detached(self):
        row = POLICY.definition(self.rules, item_id=MANUAL)
        row['source_columns'].append(999)
        self.assertEqual(POLICY.definition(self.rules, item_id=MANUAL), self.document['rows'][MANUAL_CLAUSE])

    def test_explicit_csv_choice_does_not_change_core_automatic_admission(self):
        for item_id in (MANUAL, 'item/다이버섯', 'item/회복허브'):
            with self.subTest(item_id=item_id):
                with self.assertRaises(ExcludedRuleSelection):
                    self.rules.select_source_definition(item_id)
                row = POLICY.definition(self.rules, item_id=item_id)
                self.assertEqual(row['item_id'], item_id)
                self.assertEqual(POLICY.definition(self.rules, item_id=item_id), row)
                with self.assertRaises(ExcludedRuleSelection):
                    self.rules.select_source_definition(item_id)

    def test_actual_physical_consumer_rejects_change_before_item_state(self):
        # Construct real native actors/objects against the read-only corpus,
        # then run this consumer against the copied input with the same bytes.
        self.rules.root = str(ROOT)
        spec = build_trainer(self.rules, 'csv-source-owner', 30,
            {'hp': 80, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20},
            extra={'moves': ['move/몸통박치기'], 'movement': {'land': 6},
                   'skills': {'은신': 3, '지각': 3, '집중': 3}})
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=1)
        engine.gm.add_combatant(actor)
        WORLD.register_object(engine, 'csv/source-manual', kind='item_instance',
            location={'kind': 'unknown'}, reason='source freshness fixture',
            item_rule_id=MANUAL, owner_id=actor.entity_id)
        self.rules.root = str(self.root)
        accepted = PHYSICAL.prepare_register(engine, actor, MANUAL, 'csv/source-manual')
        self.assertEqual(accepted['item_id'], MANUAL)
        before = deepcopy((actor.spec, engine._physical_objects))
        self.changed_bytes('input/db/inventory.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            PHYSICAL.prepare_register(engine, actor, MANUAL, 'csv/source-manual')
        self.assertEqual((actor.spec, engine._physical_objects), before)

    def test_food_definition_rechecks_item_data_before_returning_playtest_row(self):
        item_id = 'item/회복허브'
        self.assertEqual(FOOD.definition(self.rules, item_id)['kind'], 'recovery_herb_playtest')
        self.changed_bytes('input/db/item-data.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            FOOD.definition(self.rules, item_id)

    def test_every_public_call_uses_existing_current_bytes_owner(self):
        with patch.object(source_context, 'verified_source', wraps=source_context.verified_source) as verify:
            POLICY.policy(self.rules)
            self.assertEqual(verify.call_count, 2)
            POLICY.definition(self.rules, item_id=MANUAL)
            self.assertEqual(verify.call_count, 4)
            POLICY.clauses(self.rules)
            self.assertEqual(verify.call_count, 6)
        self.assertEqual({row['domain'] for row in POLICY.policy(self.rules)['rows'].values()},
                         {'physical', 'food', 'form', 'capability', 'environment'})


if __name__ == '__main__':
    unittest.main()
