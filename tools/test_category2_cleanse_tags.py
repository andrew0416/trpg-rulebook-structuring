"""Actual C09-083 manufacture; later tag effects deliberately have no claim."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
import cleanse_tags as TAG
import crafting_products as PRODUCTS
import skill_feature_actions as SKILLS
import state_codec as CODEC
import world_entities as WORLD
import items as ITEMS


class CleanseTagTests(unittest.TestCase):
    actor = _fixture_test_category3_pokemon_activities.PokemonActivityTests.actor

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def setUp(self):
        _fixture_test_category3_pokemon_activities.PokemonActivityTests.setUp(self)
        self.a.spec['edges'] = [TAG.SOURCE]
        self.a.spec['skills']['오컬트학'] = '숙련'
        self.a.spec['money'] = 0
        self.work = {'source': 'gm/observation', 'paper': True, 'prayer': True,
                     'seconds': 37, 'reason': 'GM observed prepared paper and prayer; declared this extended work interval'}

    def craft(self, n='one', engine=None, actor=None, **options):
        args = dict(event_id='make-' + n, instance_id='tag:' + n,
                    work=deepcopy(self.work), skill_options={'fixed': [1, 2, 3, 4]})
        args.update(options)
        return TAG.craft(engine or self.e, actor or self.a, **args)

    def loaded(self):
        fresh = Rules(str(ROOT), ruleset='core')
        e = Engine.import_state(fresh, json.loads(json.dumps(self.e.export_state())))
        return e, WORLD.actor_index(e)[self.a.entity_id]

    def test_actual_maker_occult_native_production_and_usable_level(self):
        result = self.craft(skill_options={'fixed': [1, 2, 3, 4], 'mods': 2})
        self.assertEqual(TAG.level(self.e, 'tag:one'), 12)
        self.assertEqual(self.e.elapsed_seconds, 37)
        self.assertEqual(self.a.spec['money'], 0)
        self.assertEqual(self.a.spec['items'][TAG.ITEM], 0)
        self.assertEqual(result['materials'], [])
        profile = result[TAG.PROFILE]
        event = SKILLS.event(self.e, self.a, profile['roll_id'])
        self.assertIs(event.actor, self.a)
        self.assertEqual((event.state, event.final.total), ('final', 12))
        row = self.a.spec[PRODUCTS.KEY][profile['production_id']]
        self.assertIs(row['transformation'], self.a.spec['resource_transformations'][0])
        self.assertEqual(row['intent']['options']['work'], self.work)
        self.assertEqual(self.e.activity_job_status(result['job_id'])['status'], 'complete')
        self.assertEqual(self.a.spec['frequency_state']['activations'][TAG.SOURCE]['used'], 1)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_rank_half_daily_quota_uses_actual_ranks_and_day_reset(self):
        for rank in (3, 4, 5, 6):
            with self.subTest(rank=rank):
                self.setUp()
                self.a.spec['skills']['오컬트학'] = rank
                for n in range(rank // 2):
                    self.craft(str(n), skill_options={'fixed': [1] * rank})
                before = self.e.export_state()
                with self.assertRaisesRegex(ValueError, 'frequency exhausted'):
                    self.craft('exhausted', skill_options={'fixed': [1] * rank})
                self.assertEqual(before, self.e.export_state())
                self.a.spec['frequency_state']['day'] += 1
                self.craft('next-day', skill_options={'fixed': [2] * rank})
                self.assertEqual(TAG.level(self.e, 'tag:next-day'), rank * 2)

    def test_invalid_qualification_material_work_and_dice_are_atomic(self):
        changes = [('edges', []), ('skills', dict(self.a.spec['skills'], 오컬트학='미숙'))]
        for field, value in changes:
            old = self.a.spec[field]
            self.a.spec[field] = value
            before = self.e.export_state()
            with self.assertRaises(ValueError):
                self.craft()
            self.assertEqual(before, self.e.export_state())
            self.a.spec[field] = old
        before = self.e.export_state()
        for args in ({'work': dict(self.work, paper=False)}, {'work': dict(self.work, seconds=0)},
                     {'work': dict(self.work, source='unproved')}, {'skill_options': {'level': 100}},
                     {'skill_options': {'fixed': [7] * 4}}):
            with self.assertRaises(ValueError):
                self.craft(**args)
            self.assertEqual(before, self.e.export_state())

    def test_selected_source_and_identity_failure_are_atomic(self):
        native = self.rules._selected_rule
        for source in (TAG.SOURCE, TAG.ITEM):
            before = self.e.export_state()
            with patch.object(self.rules, '_selected_rule', side_effect=lambda uid: 'other-version' if uid == source else native(uid)):
                with self.assertRaises(ValueError):
                    self.craft()
            self.assertEqual(before, self.e.export_state())
        self.craft()
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.craft(instance_id='tag:copy')
        self.assertEqual(before, self.e.export_state())

    def test_completed_replay_and_level_survive_edge_withdrawal_and_rank_change(self):
        first = self.craft()
        self.a.spec['edges'] = []
        self.a.spec['skills']['오컬트학'] = '미숙'
        before = self.e.export_state()
        self.assertEqual(TAG.level(self.e, 'tag:one'), 10)
        self.assertEqual(self.craft(), first)
        self.assertEqual(before, self.e.export_state())
        with self.assertRaises(ValueError):
            self.craft('new')
        self.assertEqual(before, self.e.export_state())

    def test_late_failure_keeps_observed_roll_then_native_retry_without_redraw(self):
        native = PRODUCTS.publish
        def fail_after_publish(*args, **kwargs):
            native(*args, **kwargs)
            raise RuntimeError('late tag production failure')
        with patch.object(PRODUCTS, 'publish', side_effect=fail_after_publish):
            with self.assertRaisesRegex(RuntimeError, 'late tag'):
                self.craft(skill_options={})
        self.assertNotIn('tag:one', self.e._physical_objects)
        self.assertEqual(self.e.elapsed_seconds, 0)
        self.assertNotIn('resource_transformations', self.a.spec)
        events = [row['skill_event'] for row in self.e._ap_rolls.values() if 'skill_event' in row]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].state, 'final')
        rng = self.e.rng.getstate()
        e, actor = self.loaded()
        original_total = events[0].final.total
        result = self.craft(engine=e, actor=actor, skill_options={})
        self.assertEqual(result[TAG.PROFILE]['level'], original_total)
        self.assertEqual(e.rng.getstate(), rng)
        self.assertEqual(e.elapsed_seconds, 37)
        self.assertEqual(len(actor.spec['resource_transformations']), 1)

    def test_pending_observed_roll_gm_restore_preserves_retry_intent(self):
        with patch.object(PRODUCTS, 'materialize', side_effect=RuntimeError('materialize failure')):
            with self.assertRaises(RuntimeError):
                self.craft()
        self.e.gm.snapshot('observed-tag')
        self.craft()
        self.e.gm.restore('observed-tag')
        self.assertNotIn('tag:one', self.e._physical_objects)
        before = self.e.export_state()
        with self.assertRaises(ValueError):
            self.craft(work=dict(self.work, seconds=41))
        self.assertEqual(before, self.e.export_state())
        self.assertEqual(self.craft()[TAG.PROFILE]['level'], 10)
        self.assertEqual(self.e.elapsed_seconds, 37)

    def test_finished_gm_and_fresh_rules_restore_preserve_original_level(self):
        self.craft()
        self.e.gm.snapshot('finished-tag')
        self.a.spec['skills']['오컬트학'] = '달인'
        self.e.gm.restore('finished-tag')
        self.assertEqual(TAG.level(self.e, 'tag:one'), 10)
        e, actor = self.loaded()
        actor.spec['edges'] = []
        actor.spec['skills']['오컬트학'] = '미숙'
        self.assertEqual(TAG.level(e, 'tag:one'), 10)
        self.assertEqual(self.craft(engine=e, actor=actor)[TAG.PROFILE]['level'], 10)
        self.assertTrue(e.validate_state()['valid'])

    def test_profile_level_copy_and_detached_production_are_rejected(self):
        self.craft()
        obj = self.e._physical_objects['tag:one']
        original = deepcopy(obj[TAG.PROFILE])
        obj[TAG.PROFILE]['level'] += 1
        with self.assertRaises(ValueError):
            self.e.export_state()
        with self.assertRaises(ValueError):
            TAG.level(self.e, 'tag:one')
        obj[TAG.PROFILE] = original
        copied = deepcopy(obj); copied['id'] = 'tag:fake'
        self.e._physical_objects['tag:fake'] = copied
        with self.assertRaises(ValueError):
            self.e.export_state()
        self.e._physical_objects.pop('tag:fake')
        row = next(iter(self.a.spec[PRODUCTS.KEY].values()))
        result = row['transformation']['result']
        qualified = deepcopy(result['qualification'])
        result['qualification']['checks'][0]['passed'] = False
        with self.assertRaises(ValueError):
            TAG.level(self.e, 'tag:one')
        result['qualification'] = qualified
        profile = result[TAG.PROFILE]
        profile['rank_at_creation'] += 1
        obj[TAG.PROFILE]['rank_at_creation'] += 1
        with self.assertRaises(ValueError):
            TAG.level(self.e, 'tag:one')
        profile['rank_at_creation'] -= 1
        obj[TAG.PROFILE]['rank_at_creation'] -= 1
        row['transformation'] = deepcopy(row['transformation'])
        with self.assertRaises(ValueError):
            self.e.export_state()
        with self.assertRaises(ValueError):
            TAG.level(self.e, 'tag:one')

    def test_native_negative_result_has_no_invented_dc_or_minimum_level(self):
        result = self.craft(skill_options={'fixed': [1] * 4, 'mods': -12})
        self.assertEqual(result[TAG.PROFILE]['level'], -8)
        self.assertEqual(TAG.level(self.e, 'tag:one'), -8)


if __name__ == '__main__':
    unittest.main()
