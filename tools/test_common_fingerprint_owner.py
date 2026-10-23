"""Persisted-encoding compatibility and exact consumer migration checks."""
import ast
import hashlib
import json
from pathlib import Path
import unittest
import resolution_transaction as TX

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE/'data/skill-check-policy.json').is_file() else Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
ARCHIVE = STAGE if (STAGE/'fingerprint-sites.json').is_file() else ROOT/'work/common-owner-integration-1255'
BASELINE = STAGE/'baseline' if (STAGE/'baseline/engine').is_dir() else ARCHIVE/'baseline'
AUDIT = json.loads((ARCHIVE/'fingerprint-sites.json').read_text(encoding='utf-8'))
SITES = AUDIT['sites']
FIXTURES = [
    {'z': ['부적', {'β': 2, 'a': -0.0}], 'a': {'two': True, 'one': None}, 'empty': []},
    {'second': {'y': [1, 2], 'x': '\n"\\'}, 'first': 'é😀'},
    [None, False, 0, 1.5, {'z': '끝', 'a': ['순서', 3]}],
]


def encoded_expression(expression, payload, helper=False):
    tree = ast.parse(expression, mode='eval')
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == ('json_fingerprint' if helper else 'dumps'):
                node.args[0] = ast.Name(id='payload', ctx=ast.Load())
    ast.fix_missing_locations(tree)
    return eval(compile(tree, '<original-encoding>' if not helper else '<owner-call>', 'eval'),
                {'json': json, 'hashlib': hashlib, 'sha256': hashlib.sha256,
                 '_FINGERPRINTS': TX, 'payload': payload})


class FingerprintOwnerTests(unittest.TestCase):
    def test_policy_flags_require_actual_booleans(self):
        for flag in ('compact', 'sort_keys', 'allow_nan'):
            for bad in (0, 1, None, 'false'):
                with self.subTest(flag=flag, bad=bad), self.assertRaises(ValueError):
                    TX.json_fingerprint({}, **{flag: bad})

    def test_request_normalization_retains_original_contract(self):
        import importlib.util
        source = BASELINE/'engine/resolution_transaction.py'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), AUDIT['owner_raw_sha256'])
        spec = importlib.util.spec_from_file_location('original_resolution_transaction', source)
        original = importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
        for payload in [{'z': ['부적', {'β': 2, 'a': 0}], 'a': {'two': True, 'one': None}},
                        FIXTURES[1], {'tuple': (1, {'b': 2, 'a': 1})}]:
            self.assertEqual(original.request_fingerprint(payload), TX.request_fingerprint(payload))
        for owner in (original, TX):
            with self.assertRaises(TypeError):owner.request_fingerprint(FIXTURES[0])
        receipt = {'request': {'intent': {'b': 2, 'a': [1]}, 'value': [3]}}
        replay = TX.replay_result(receipt, 'request', {'a': [1], 'b': 2})
        replay['value'].append(4)
        self.assertEqual(receipt['request']['value'], [3])
        with self.assertRaises(ValueError):TX.replay_result(receipt, 'request', {'a': [2], 'b': 2})

    def test_owner_is_only_json_sha_body_in_migrated_modules(self):
        for file in sorted({site['file'] for site in SITES}):
            tree = ast.parse((STAGE/file).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'hexdigest':
                    self.assertFalse(any(isinstance(child, ast.Attribute) and child.attr == 'dumps'
                                         for child in ast.walk(node)), file)

    def test_frozen_utf8_order_whitespace_golden_digests(self):
        golden = {
            (False, False): 'd6a76c77a18c732961cec5d9438f6abfe5cf1ca6a4e0b775db6120ef1668bfab',
            (False, True): '031f4eabd98cf8d17723cebee5f41f4a8d3fc0fd66f86e443026276694391aa4',
            (True, False): '448a481ea2ee72d847ac598379e8da170e10fd3d7ebe5efcbcb2c0c7cf403085',
            (True, True): 'd6b69e1a6a6e57c2e155d2e902439c8ee38607789ff53831761e1ce8dbb6ab9f',
        }
        for (sort_keys, compact), digest in golden.items():
            self.assertEqual(digest, TX.json_fingerprint(FIXTURES[0], sort_keys=sort_keys, compact=compact))

    def test_native_child_prefix_and_host_plain_normalization_are_preserved(self):
        import root_children as CHILDREN
        import root_common_engine as HOST
        self.assertEqual(CHILDREN.child_id('부모', 'node', 'key'), 'child:' +
                         hashlib.sha256(json.dumps(('부모', 'node', 'key'), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest())
        payload = {3: {'values': {3, 1}, 'float': 0.5}, 'ordered': ('부적', True)}
        expected = hashlib.sha256(json.dumps(HOST._plain(payload), sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(HOST._digest(payload), expected)

    def test_stdlib_only_consumers_keep_clean_package_and_top_level_imports(self):
        import subprocess
        import sys
        names = ('root_children', 'directive_features', 'field_effects', 'state_codec', 'state_fields')
        for package in (False, True):
            imports = ';'.join('import '+('engine.' if package else '')+name for name in names)
            location = STAGE if package else STAGE/'engine'
            code = 'import sys;sys.dont_write_bytecode=True;sys.path.insert(0,'+repr(str(location))+');'+imports
            result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


def site_case(site):
    def check(self):
        original = BASELINE/site['file']; staged = STAGE/site['file']
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), site['raw_sha256'])
        desired = ast.dump(ast.parse(site['helper'], mode='eval').body, include_attributes=False)
        tree = ast.parse(staged.read_text(encoding='utf-8'))
        self.assertTrue(any(isinstance(node, ast.Call) and ast.dump(node, include_attributes=False) == desired
                            for node in ast.walk(tree)), site['helper'])
        # Exact original input expression (including _plain/ordered row shape) is in desired.
        for payload in FIXTURES:
            self.assertEqual(encoded_expression(site['expression'], payload),
                             encoded_expression(site['helper'], payload, True))
        nonfinite = {'z': float('nan'), 'a': float('inf')}
        if site['preserved']['allow_nan']:
            self.assertEqual(encoded_expression(site['expression'], nonfinite),
                             encoded_expression(site['helper'], nonfinite, True))
        else:
            for helper in (False, True):
                with self.assertRaises(ValueError):
                    encoded_expression(site['helper'] if helper else site['expression'], nonfinite, helper)
    return check


for site in SITES:
    name = 'test_site_' + Path(site['file']).stem + '_' + site['function'] + '_' + str(site['line'])
    setattr(FingerprintOwnerTests, name, site_case(site))


def policy_case(sort_keys, compact, allow_nan):
    def check(self):
        for payload in FIXTURES:
            options = dict(ensure_ascii=False, sort_keys=sort_keys, allow_nan=allow_nan)
            if compact:options['separators'] = (',', ':')
            expected = hashlib.sha256(json.dumps(payload, **options).encode('utf-8')).hexdigest()
            self.assertEqual(expected, TX.json_fingerprint(payload, sort_keys=sort_keys,
                                                           compact=compact, allow_nan=allow_nan))
    return check


for sort_keys in (False, True):
    for compact in (False, True):
        for allow_nan in (False, True):
            name = 'test_owner_encoding_sort_%s_compact_%s_nan_%s' % (sort_keys, compact, allow_nan)
            setattr(FingerprintOwnerTests, name, policy_case(sort_keys, compact, allow_nan))
