"""Bounded native-read checks for the existing equipment source contract."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import equipment_variant_contracts as VARIANTS
import items as ITEMS
import source_context
import world_entities as WORLD
from builder import build_trainer
from engine import Combatant, Engine, Rules
from ruleset import ExcludedRuleSelection, UnresolvedRuleSelection


ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
WORKSPACE = Path(r'C:\Users\admin\Documents\ChatGPT\trpg-rulebook-structuring')
TEMP_ROOT = WORKSPACE / 'tmp'
STATUS = 'data/verification/category2-item-table-status.json'
ARMOR = 'item/분리중갑'
GLOVE = 'item/펀치글러브'


class EquipmentPolicySourceFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Rules(str(ROOT), ruleset='core')
        cls.document = json.loads((ROOT / 'data' / VARIANTS.POLICY_FILE).read_text(encoding='utf-8'))

    def setUp(self):
        TEMP_ROOT.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='equipment-source-', dir=TEMP_ROOT)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / 'input', self.root / 'input')
        for relative in (STATUS, 'data/' + VARIANTS.POLICY_FILE):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
            self.assertEqual(target.read_bytes(), (ROOT / relative).read_bytes())
        self.rules = deepcopy(self.original)
        self.rules.root = str(self.root)
        for relative, expected in (
                ('input/db/inventory.csv', self.document['inventory_file_sha256']),
                ('input/db/moves.csv', self.document['punch_classifier']['source_file_sha256'])):
            self.assertEqual(sha256((self.root / relative).read_bytes()).hexdigest(), expected)

    def changed_bytes(self, relative):
        path = self.root / relative
        old = path.read_bytes()
        stamp = path.stat()
        path.write_bytes(bytes([old[0] ^ 1]) + old[1:])
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(path.stat().st_size, len(old))
        self.assertEqual(path.stat().st_mtime_ns, stamp.st_mtime_ns)

    def actual_fixture(self, item_id):
        self.rules.root = str(ROOT)
        spec = build_trainer(self.rules, 'equipment-source-owner', 30,
            {'hp': 80, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20},
            extra={'moves': ['move/암해머'], 'movement': {'land': 6, 'power': 7},
                   'power_basis': 'current', 'skills': {'은신': 3}})
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=65108)
        engine.gm.add_combatant(actor)
        uid = 'equipment/source-instance'
        WORLD.register_object(engine, uid, kind='item_instance',
            location={'kind': 'unknown'}, reason='source freshness fixture',
            item_rule_id=item_id, owner_id=actor.entity_id)
        self.rules.root = str(self.root)
        return engine, actor, uid

    def test_inventory_changed_after_cached_definition_is_rejected(self):
        self.assertEqual(VARIANTS.definition(self.rules, ARMOR)['item_id'], ARMOR)
        self.changed_bytes('input/db/inventory.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            VARIANTS.definition(self.rules, ARMOR)

    def test_classifier_changed_after_cached_definition_is_rejected(self):
        self.assertEqual(VARIANTS.definition(self.rules, GLOVE)['item_id'], GLOVE)
        self.changed_bytes('input/db/moves.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            VARIANTS.definition(self.rules, GLOVE)

    def test_current_registered_source_pin_is_rechecked_after_cache(self):
        row = VARIANTS.definition(self.rules, ARMOR)
        path = self.root / STATUS
        status = json.loads(path.read_text(encoding='utf-8'))
        registered = next(value for value in status['new_clauses'] if value['clause_id'] == row['clause_id'])
        registered['source'][0]['raw_cells_sha256'] = '0' * 64
        path.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source provenance changed'):
            VARIANTS.definition(self.rules, ARMOR)

    def test_missing_inventory_after_cache_is_rejected(self):
        VARIANTS.policy(self.rules)
        (self.root / 'input/db/inventory.csv').unlink()
        with self.assertRaises(OSError):
            VARIANTS.definition(self.rules, ARMOR)

    def test_changed_selection_profile_is_rechecked_after_cache(self):
        VARIANTS.definition(self.rules, ARMOR)
        self.rules.ruleset.exclude_units.add(ARMOR)
        with self.assertRaises(UnresolvedRuleSelection):
            VARIANTS.definition(self.rules, ARMOR)

    def test_public_policy_result_cannot_rewrite_later_definition(self):
        returned = VARIANTS.policy(self.rules)
        expected = deepcopy(returned['rows'][ARMOR])
        returned['rows'][ARMOR]['maximum_dr'] = 999
        returned['rows'][ARMOR]['source_columns'].append(999)
        self.assertEqual(VARIANTS.definition(self.rules, ARMOR), expected)

    def test_public_definition_result_remains_detached(self):
        returned = VARIANTS.definition(self.rules, ARMOR)
        returned['source_columns'].append(999)
        returned['maximum_dr'] = 999
        self.assertEqual(VARIANTS.definition(self.rules, ARMOR), self.document['rows'][ARMOR])

    def test_actual_register_consumer_rejects_before_physical_state_change(self):
        engine, actor, uid = self.actual_fixture(ARMOR)
        self.assertEqual(VARIANTS.prepare_register(engine, actor, ARMOR, uid)['item_id'], ARMOR)
        before = deepcopy((actor.spec, engine._physical_objects))
        self.changed_bytes('input/db/inventory.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            VARIANTS.prepare_register(engine, actor, ARMOR, uid)
        self.assertEqual((actor.spec, engine._physical_objects), before)

    def test_native_damage_consumer_rejects_changed_source_with_both_caches_warm(self):
        engine, actor, uid = self.actual_fixture(GLOVE)
        # Full item installation reads unrelated native policy documents. Build
        # that valid native state at R, then verify the exact copied input here.
        self.rules.root = str(ROOT)
        ITEMS.register_item(engine, actor, GLOVE, source_instance_id=uid)
        move = self.rules.move('move/암해머')
        self.rules.root = str(self.root)
        self.assertEqual(VARIANTS.damage_roll_bonus(engine, actor, move), 5)
        self.assertIsNotNone(getattr(self.rules, '_equipment_variant_punch_moves', None))
        before = deepcopy((actor.spec, engine._physical_objects))
        self.changed_bytes('input/db/moves.csv')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            VARIANTS.damage_roll_bonus(engine, actor, move)
        self.assertEqual((actor.spec, engine._physical_objects), before)

    def test_each_policy_read_reuses_shared_current_byte_verifier(self):
        with patch.object(source_context, 'verified_source', wraps=source_context.verified_source) as verify:
            VARIANTS.policy(self.rules)
            first = [call for call in verify.call_args_list if call.kwargs.get('label') in
                     {'equipment variant', 'Punching Glove move classifier'}]
            self.assertEqual(len(first), 2)
            VARIANTS.definition(self.rules, ARMOR)
            second = [call for call in verify.call_args_list if call.kwargs.get('label') in
                      {'equipment variant', 'Punching Glove move classifier'}]
            self.assertEqual(len(second), 4)

    def test_exact_native_variant_selection_preserves_excluded_csv_choices(self):
        for item_id in self.document['rows']:
            self.assertEqual(self.rules._selected_rule(item_id), item_id)
            self.assertEqual(VARIANTS.definition(self.rules, item_id), self.document['rows'][item_id])
        for item_id in ('item/타입-공부-메뉴얼-1', 'item/다이버섯', 'item/회복허브'):
            with self.subTest(item_id=item_id):
                with self.assertRaises(ExcludedRuleSelection):
                    self.rules.select_source_definition(item_id)
                VARIANTS.policy(self.rules)
                with self.assertRaises(ExcludedRuleSelection):
                    self.rules.select_source_definition(item_id)


if __name__ == '__main__':
    unittest.main()
