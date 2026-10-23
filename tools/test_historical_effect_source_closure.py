"""Historical source-gap checks at existing public executable-row boundaries.

These are explicitly application-authored declarations. They do not implement
or reinterpret any native feat whose generic trigger path remains incomplete.
"""
from copy import copy, deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Rules, Engine, Combatant
from builder import build_trainer
from rulings import Rulings
from state_codec import dump_engine, load_engine
import combat_timing as TIME
import effect_contracts as CONTRACTS
import effect_lifetimes as LIFE
import effects as FX
import frequency as FREQ
import test_category2_move_optional_slots as AUGMENT_FIXTURE

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'data').is_dir() or not (ROOT / 'output').is_dir():ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
SOURCE_A = 'authored/audit/accepted-trigger-a'
SOURCE_B = 'authored/audit/accepted-trigger-b'


class AcceptedTriggerSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.r = copy(self.base)
        self.r.ruleset = deepcopy(self.base.ruleset)
        self.r.selection = copy(self.base.selection)
        self.r.selection.filter = self.r.ruleset
        self.r.rulings = Rulings()
        self.e = Engine(self.r, 547)
        self.a = Combatant(self.r, build_trainer(
            self.r, 'Authored declaration owner', 20,
            dict(hp=10, atk=10, **{'def': 10}, spa=10, spd=10, spe=10),
            abilities=[]))
        self.e.gm.add_combatant(self.a, pos=(0, 0), side='party', reason='actual declaration owner')
        self.e.start_round([self.a])
        self.e.start_of_turn(self.a, initiative_count=20)
        source_file = self.r.selection.units['combat/struggle']['source']['file']
        self.reference = dict(file='input/' + source_file,
                              sha256=sha256((ROOT / 'input' / source_file).read_bytes()).hexdigest())
        definitions = [dict(id=uid, title='Explicit authored trigger ' + uid[-1],
                            source=self.reference, locator={'lines': [1, 1]}, tags=[],
                            rationale='Application-authored executable-row diagnostic; the reference '
                                      'proves source bytes only and does not assert native feat semantics')
                       for uid in (SOURCE_A, SOURCE_B)]
        self.r.register_source_policy_definitions(definitions)

    def register(self, uid=SOURCE_A, effects=None, *, is_feat=True, name=None):
        frequency = dict(raw='장면 - 자유 행동', kind='scene', uses=1, action='free')
        value = dict(name=name or 'External declared end-turn effect ' + uid[-1],
                     spec={'event': 'turn_end'}, frequency=frequency,
                     effects=effects or [dict(type='damage_reduction', value=5, target='self',
                                             duration={'seconds': 5})],
                     usage_key=uid)
        if is_feat:
            value.update(_feat=True, activation_header={'id': uid, 'frequency': frequency})
        registration = 'external-row:' + uid
        self.assertTrue(self.a.active_effects.register_definition_row(
            self.e, registration, 'ability_triggers', value))
        self.assertFalse(self.a.active_effects.register_definition_row(
            self.e, registration, 'ability_triggers', value))
        return registration, value

    def test_eown_source_01_public_end_turn_preserves_key_receipt_timer_and_raw_source(self):
        self.register()
        raw_reads = []
        original = Path.read_bytes
        def observed(path):
            value = original(path)
            if path.resolve() == (ROOT / self.reference['file']).resolve():
                raw_reads.append(dict(file=str(path.resolve()), sha256=sha256(value).hexdigest()))
            return value
        with patch.object(Path, 'read_bytes', observed):
            self.e.end_of_turn(self.a)
            self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 5)
        rows = list(self.e._effect_dispatch_receipts.values())
        print('ACCEPTED_TRIGGER_SOURCE', json.dumps(dict(
            usage_key=SOURCE_A, receipt_sources=[row['source_id'] for row in rows],
            timer_sources=[row['source'] for row in TIME.records(self.a)],
            frequency=FREQ.state(self.a), raw_source_reads=raw_reads), ensure_ascii=False, default=str))
        self.assertEqual([row['source_id'] for row in rows], [SOURCE_A])
        self.assertEqual([row['source'] for row in TIME.records(self.a)], [SOURCE_A])
        self.assertEqual(FREQ.state(self.a)['activations'][SOURCE_A]['used'], 1)
        self.assertTrue(raw_reads)
        self.assertTrue(all(row['sha256'] == self.reference['sha256'] for row in raw_reads))
        restored = load_engine(self.r, json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False)))
        actor = restored.everyone[0]
        self.assertEqual(LIFE.numeric(actor, 'damage_reduction'), 5)
        self.assertEqual([row['source_id'] for row in restored._effect_dispatch_receipts.values()], [SOURCE_A])
        restored.advance_time(5, [actor])
        self.assertEqual(LIFE.numeric(actor, 'damage_reduction'), 0)

    def test_eown_source_02_same_display_name_keeps_independent_sources_and_removal(self):
        first, _ = self.register(name='Shared authored display')
        self.register(SOURCE_B, [dict(type='damage_reduction', value=3, target='self',
                                   duration={'seconds': 9})], name='Shared authored display')
        self.e.end_of_turn(self.a)
        self.assertEqual({row['source_id'] for row in self.e._effect_dispatch_receipts.values()},
                         {SOURCE_A, SOURCE_B})
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 8)
        self.assertTrue(self.a.active_effects.remove(self.e, first))
        self.assertEqual(len(self.a.ability_triggers), 1)
        self.e.advance_time(5, [self.a])
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 3)
        self.e.advance_time(4, [self.a])
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 0)

    def test_eown_source_03_suspended_condition_and_suffix_keep_original_source(self):
        self.register(effects=[dict(type='damage_reduction', value=2, target='self',
                                    duration={'seconds': 7}, **{'if': 'target was asleep'}),
                               dict(type='stage_change', stat='def', delta=1, target='self')])
        # fire_event is the existing public dispatcher. end_of_turn necessarily
        # advances the continuation boundary after the callback; pause at the
        # dispatcher boundary when exercising its explicit resume operation.
        FX.fire_event(self.e, self.a, {'event': 'turn_end'})
        rows = self.e._effect_dispatch_receipts
        token, pending = next((token, row) for token, row in rows.items()
                              if row['status'] == 'condition_unknown')
        print('SUSPENDED_TRIGGER_SOURCE', json.dumps(dict(
            usage_key=SOURCE_A, sources=[row['source_id'] for row in rows.values()],
            status=[row['status'] for row in rows.values()]), ensure_ascii=False))
        self.assertTrue(all(row['source_id'] == SOURCE_A for row in rows.values()))
        self.assertEqual(pending['condition_request']['profile'], CONTRACTS.source_profile(self.e, SOURCE_A))
        result = FX.resolve_condition(self.e, self.a, token, target_was_asleep=True,
                                      reason='explicit actual historical observation')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.a.stages['def'], 1)
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 2)
        self.assertTrue(all(row['source_id'] == SOURCE_A for row in self.e._effect_dispatch_receipts.values()))
        self.assertTrue(all(row['status'] == 'completed' for row in self.e._effect_dispatch_receipts.values()))

    def test_eown_source_04_non_feat_explicit_key_and_legacy_fallback(self):
        self.register(is_feat=False)
        self.e.end_of_turn(self.a)
        self.assertEqual({row['source_id'] for row in self.e._effect_dispatch_receipts.values()}, {SOURCE_A})
        self.assertEqual(FREQ.state(self.a)['activations'][SOURCE_A]['used'], 1)
        self.setUp()
        _, row = self.register(is_feat=False, name='Declared legacy ability')
        self.a.ability_triggers[0].pop('usage_key')
        self.e.end_of_turn(self.a)
        self.assertEqual({row['source_id'] for row in self.e._effect_dispatch_receipts.values()},
                         {'ability/Declared legacy ability'})

    def changed_source(self):
        original = Path.read_bytes
        def changed(path):
            content = original(path)
            return content + b'\nchanged authored reference\n' if path.resolve() == (ROOT / self.reference['file']).resolve() else content
        return patch.object(Path, 'read_bytes', changed)

    def test_eown_source_05_live_numeric_rechecks_current_registered_source_bytes(self):
        self.register()
        self.e.end_of_turn(self.a)
        before = dump_engine(self.e)
        with self.changed_source():
            with self.assertRaisesRegex(ValueError, 'source changed'):
                LIFE.numeric(self.a, 'damage_reduction')
        self.assertEqual(dump_engine(self.e), before)
        self.assertEqual(LIFE.numeric(self.a, 'damage_reduction'), 5)

    def test_eown_source_06_condition_resume_rechecks_original_source_without_prefix_replay(self):
        self.register(effects=[dict(type='stage_change', stat='atk', delta=1, target='self'),
                               dict(type='stage_change', stat='def', delta=1, target='self',
                                    **{'if': 'target was asleep'}),
                               dict(type='stage_change', stat='spe', delta=1, target='self')])
        FX.fire_event(self.e, self.a, {'event': 'turn_end'})
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 0, 0))
        token = next(token for token, row in self.e._effect_dispatch_receipts.items()
                     if row['status'] == 'condition_unknown')
        before = dump_engine(self.e)
        with self.changed_source():
            with self.assertRaisesRegex(ValueError, 'source changed'):
                FX.resolve_condition(self.e, self.a, token, target_was_asleep=True,
                                     reason='actual historical observation after source changed')
        self.assertEqual(dump_engine(self.e), before)
        FX.resolve_condition(self.e, self.a, token, target_was_asleep=True,
                             reason='actual historical observation after original source restored')
        self.assertEqual((self.a.stages['atk'], self.a.stages['def'], self.a.stages['spe']), (1, 1, 1))
        self.assertTrue(all(row['source_id'] == SOURCE_A for row in self.e._effect_dispatch_receipts.values()))
        self.assertEqual(FREQ.state(self.a)['activations'][SOURCE_A]['used'], 1)


class LiveAugmentationHistoryBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        AUGMENT_FIXTURE.SmartVisionMoveSlotTests.setUpClass()

    def fixture(self):
        f = AUGMENT_FIXTURE.SmartVisionMoveSlotTests()
        f.r = copy(f.r)
        f.r.rulings = Rulings()
        f.setUp()
        f.upgrade('application1')
        return f

    def test_augmentation_history_01_native_stable_projection_and_first_error_order(self):
        import augmentation_moves as AUG
        import world_entities as W
        f = self.fixture()
        current = f.e._physical_objects[f.row['id']]
        row = deepcopy(current)
        grants = AUG.projection(f.e, row, W.actor_index(f.e), f.e._physical_objects)
        self.assertEqual(len(grants), 1)
        erased = deepcopy(row)
        erased['experimental_designs'] = []
        with patch.object(f.r, '_selected_rule', side_effect=AssertionError('first error order lost')):
            with self.assertRaisesRegex(ValueError, 'history cannot be erased'):
                AUG.projection(f.e, erased, W.actor_index(f.e), f.e._physical_objects)

    def test_augmentation_history_02_custom_source_reader_live_change_requires_second_read(self):
        import augmentation_moves as AUG
        import world_entities as W
        f = self.fixture()
        row = deepcopy(f.e._physical_objects[f.row['id']])
        prior = f.r._selected_rule
        calls = []
        def custom_reader(uid, *args, **kwargs):
            selected = prior(uid, *args, **kwargs)
            if uid == AUG.SOURCE:
                calls.append(uid)
                changed = deepcopy(f.e._physical_objects[f.row['id']])
                changed['experimental_designs'][0]['reason'] = 'changed during custom source read'
                f.e._physical_objects[f.row['id']] = changed
            return selected
        with patch.object(f.r, '_selected_rule', side_effect=custom_reader):
            with self.assertRaisesRegex(ValueError, 'history cannot be erased or rewritten'):
                AUG.projection(f.e, row, W.actor_index(f.e), f.e._physical_objects)
        self.assertEqual(calls, [AUG.SOURCE])
        print('AUGMENTATION_LIVE_BOUNDARY', json.dumps(dict(
            source_calls=calls, first_prefix_accepted=True, selected_source_returned=True,
            live_registry_replacement_rejected=True,
            native_row_id=row['id'], native_application_id=row['experimental_designs'][0]['id']), ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
