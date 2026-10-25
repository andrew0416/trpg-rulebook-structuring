"""Source-preserving query refactor checks, not rule-completion evidence."""
import ast
from copy import deepcopy
import importlib
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / 'engine'), str(STAGE / 'tools')]
import trainer_feature_acquisition as TFA
OMITTED = object()


class StaticAcquisitionQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queries = json.loads((STAGE / 'tools/fixtures/static-acquisition-queries.json').read_text())['queries']
        cls.functions = []
        for row in cls.queries:
            module = importlib.import_module(row['module'])
            namespace = dict(vars(module))
            exec(compile(row['source'], '<frozen-original-query>', 'exec'), namespace)
            cls.functions.append((row, module, namespace[row['function']], getattr(module, row['function'])))

    def actor(self, features):
        receipts = [{'feature_id': value, 'snapshot': {'rank_number': index}}
                    for index, value in enumerate(features)]
        sources = {'unrelated': {'grants': {}}}
        for index, receipt in enumerate(receipts):
            sources['live/' + str(index)] = {'static_acquisition': receipt}
        return SimpleNamespace(spec={'state_grants': {
            'sources': sources,
            'ended_sources': [{'source_id': 'ended/' + str(index),
                               'record': {'static_acquisition': receipt}}
                              for index, receipt in reversed(list(enumerate(receipts)))]}})

    def feature_values(self, row, module):
        if row['family']:
            return list(eval(row['family'], vars(module)))
        if row['feature'] in inspect.signature(getattr(module, row['function'])).parameters:
            return ['feat/example', None, '', False]
        return [eval(row['feature'], vars(module))]

    def call(self, function, row, actor, feature=OMITTED, active=OMITTED):
        parameters = inspect.signature(function).parameters
        args = [actor]
        options = {} if active is OMITTED else {'active': active}
        if row['feature'] in parameters and feature is not OMITTED:
            if parameters[row['feature']].kind is inspect.Parameter.KEYWORD_ONLY:
                options[row['feature']] = feature
            else:
                args.append(feature)
        try:
            return function(*args, **options), None
        except Exception as error:
            return None, (type(error), str(error))

    def compare(self, row, old, current, actor, feature=OMITTED, active=OMITTED):
        before = deepcopy(actor.spec) if actor is not None else None
        expected, old_error = self.call(old, row, actor, feature, active)
        actual, new_error = self.call(current, row, actor, feature, active)
        self.assertEqual(new_error, old_error)
        self.assertEqual(actual, expected)
        if actual is not None:
            for old_row, new_row in zip(expected, actual):
                if row['pairs']:
                    self.assertEqual(old_row[0], new_row[0])
                    self.assertIs(old_row[1], new_row[1])
                else:
                    self.assertIs(old_row, new_row)
        if actor is not None:
            self.assertEqual(actor.spec, before)

    def test_all_consumers_preserve_signature_and_nonquery_ast(self):
        self.assertEqual(len(self.functions), 38)
        for row, module, old, current in self.functions:
            with self.subTest(module=row['module']):
                self.assertEqual(inspect.signature(current), inspect.signature(old))
                # Pin only the query declaration, never unrelated class implementation.
                declarations = [ast.parse(inspect.getsource(current)).body[0],
                                ast.parse(row['source']).body[0]]
                for declaration in declarations:
                    declaration.body = [ast.Pass()]
                self.assertEqual(ast.dump(declarations[0], include_attributes=False),
                                 ast.dump(declarations[1], include_attributes=False))

    def test_all_features_live_archived_order_and_identity_match_original_queries(self):
        for row, module, old, current in self.functions:
            values = self.feature_values(row, module)
            actor = self.actor([*values, 'feat/outside-family', *values[:1]])
            for feature in [None, *values, 'feat/unknown', '', False, 0, [], {}]:
                for active in (False, True, None, 0, 1, ''):
                    with self.subTest(module=row['module'], feature=feature, active=active):
                        self.compare(row, old, current, actor, feature, active)

    def test_actual_public_defaults_match_without_explicit_active_or_feature(self):
        for row, module, old, current in self.functions:
            values = self.feature_values(row, module)
            actor = self.actor([*values, 'feat/outside-family'])
            with self.subTest(module=row['module']):
                self.compare(row, old, current, actor, values[0])
                parameter = inspect.signature(current).parameters.get(row['feature'])
                if parameter is None or parameter.default is not inspect.Parameter.empty:
                    self.compare(row, old, current, actor)

    def test_empty_missing_and_malformed_state_match_original_errors(self):
        states = [{}, {'state_grants': {}}, {'state_grants': None},
                  {'state_grants': {'sources': None}},
                  {'state_grants': {'ended_sources': [None]}},
                  {'state_grants': {'ended_sources': [{}]}},
                  {'state_grants': {'sources': {'bad': None}}},
                  *({'state_grants': {'sources': {'bad': {'static_acquisition': value}}}}
                    for value in (None, [], {}, {'feature_id': []}, {'feature_id': {}},
                                  {'feature_id': None}, {'feature_id': 0})),
                  *({'state_grants': {'ended_sources': [
                      {'source_id': 'ended/bad', 'record': {'static_acquisition': value}}]}}
                    for value in (None, [], {}, {'feature_id': []}, {'feature_id': {}},
                                  {'feature_id': None}, {'feature_id': 0}))]
        for row, module, old, current in self.functions:
            feature = self.feature_values(row, module)[0]
            for state in states:
                for active in (False, True):
                    with self.subTest(module=row['module'], state=state, active=active):
                        self.compare(row, old, current, SimpleNamespace(spec=deepcopy(state)), feature, active)
            self.compare(row, old, current, None, feature, False)

    def test_current_state_is_requeried_and_returned_receipts_stay_live_objects(self):
        for row, module, old, current in self.functions:
            feature = self.feature_values(row, module)[0]
            actor = self.actor([feature])
            first, error = self.call(current, row, actor, feature, True)
            self.assertIsNone(error)
            if not first:
                continue
            receipt = first[0][1] if row['pairs'] else first[0]
            receipt['query_identity_probe'] = {'value': 1}
            self.assertIs(actor.spec['state_grants']['sources']['live/0']['static_acquisition'], receipt)
            actor.spec['state_grants']['sources'].clear()
            self.compare(row, old, current, actor, feature, True)
            second, error = self.call(current, row, actor, feature, True)
            self.assertEqual(second, [])
            self.assertIsNone(error)
            self.assertTrue(self.call(current, row, actor, feature, False)[0])

    def test_no_pure_consumer_reintroduces_an_inline_static_record_scan(self):
        for path in (STAGE / 'engine').glob('*.py'):
            if path.name == 'trainer_feature_acquisition.py':
                continue
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef):
                    continue
                for statement in node.body:
                    if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.ListComp):
                        continue
                    scans = [child for child in ast.walk(statement)
                             if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                             and child.func.attr == '_static_records']
                    self.assertFalse(scans, str(path) + ':' + node.name)


if __name__ == '__main__':
    unittest.main()
