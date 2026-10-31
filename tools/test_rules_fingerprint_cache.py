"""The cached rules fingerprint is byte-identical to the full recomputation and honors reassignment and touch()."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
import state_codec as CODEC


class RulesFingerprintCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def full(self, rules):
        with mock.patch.dict(os.environ, {'PTK_FINGERPRINT_FULL': '1'}):
            return CODEC.rules_fingerprint(rules)

    def test_cached_digest_equals_full_recomputation_cold_and_warm(self):
        r = self.rules
        r.touch()
        cold = CODEC.rules_fingerprint(r)          # fills the cache
        self.assertEqual(cold, self.full(r))
        warm = CODEC.rules_fingerprint(r)          # served from the cache
        self.assertEqual(warm, cold)
        self.assertNotIn('_fingerprint_cache', vars(r))   # the cache lives beside the object, not in its rule state
        self.assertGreater(len(CODEC.piece_cache(r)), 10)
        engine = Engine(r, seed=11)
        saved = CODEC.dump_engine(engine)
        self.assertEqual(saved['rules'], self.full(r))
        restored = CODEC.load_engine(r, saved)
        self.assertEqual(CODEC.dump_engine(restored)['rules'], saved['rules'])

    def test_selected_digest_equals_the_whole_document_hash(self):
        import hashlib, json
        r = self.rules
        manifest = [('input/a.md', 'a' * 64), ('data/b.json', 'b' * 64)]
        big = {'rows': {str(i): {'name': 'row ' + str(i), 'tags': ['x', 'y', i]} for i in range(3000)}}
        policy = {'small': {'k': [1, 2.5, None, True]}, 'big': big, 'z': 'text',
                  'selection': {'units': {'u1': {'source': {'file': 'input/a.md'}}}, 'filter': 'f'}}
        document = json.dumps(CODEC._plain({'files': manifest, 'selected': policy}), **CODEC._FINGERPRINT_JSON)
        expected = hashlib.sha256(document.encode()).hexdigest()
        r.touch()
        for _ in range(2):   # cold (fills the piece cache) and warm (served from it)
            self.assertEqual(CODEC._selected_digest(r, manifest, policy), expected)
        self.assertIn('big', CODEC.piece_cache(r))
        self.assertIn('selection', CODEC.piece_cache(r))
        self.assertNotIn('small', CODEC.piece_cache(r))
        with mock.patch.dict(os.environ, {'PTK_FINGERPRINT_FULL': '1'}):
            self.assertEqual(CODEC._selected_digest(r, manifest, policy), expected)
        r.touch()

    def test_reassigned_attribute_is_detected_without_declaration(self):
        r = self.rules
        before = CODEC.rules_fingerprint(r)
        original = r.skill_policy
        try:
            r.skill_policy = dict(original, fingerprint_cache_probe=True)
            changed = CODEC.rules_fingerprint(r)
            self.assertNotEqual(changed, before)
            self.assertEqual(changed, self.full(r))
        finally:
            r.skill_policy = original
        self.assertEqual(CODEC.rules_fingerprint(r), before)

    def test_in_place_edit_is_detected_after_touch(self):
        r = self.rules
        before = CODEC.rules_fingerprint(r)
        key = next(iter(r.units))
        unit = r.units[key]
        unit['fingerprint_cache_probe'] = 1
        try:
            r.touch('units')
            changed = CODEC.rules_fingerprint(r)
            self.assertNotEqual(changed, before)
            self.assertEqual(changed, self.full(r))
        finally:
            del unit['fingerprint_cache_probe']
            r.touch('units')
        self.assertEqual(CODEC.rules_fingerprint(r), before)

    def test_touch_without_names_drops_every_piece_and_cache_is_not_hashed(self):
        r = self.rules
        CODEC.rules_fingerprint(r)
        r.touch()
        self.assertEqual(CODEC.piece_cache(r), {})
        digest = CODEC.rules_fingerprint(r)
        clone = deepcopy(r)
        self.assertEqual(CODEC.rules_fingerprint(clone), digest)


if __name__ == '__main__':
    unittest.main()
