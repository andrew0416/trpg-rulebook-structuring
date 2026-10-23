"""Reproduce the independent movement token oracle already used in source review.

This checks the native-first ordinary budget abstraction, not all movement or source semantics.
No implementation or source files are modified; only the requested JSON result is written.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
COUNTS = {}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_fixture(root):
    sys.path.insert(0, str(root / 'engine'))
    spec = importlib.util.spec_from_file_location('source_movement_fixture', root / 'tools/test_movement_action_budget.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MovementActionTests.setUpClass()
    return module.MovementActionTests()

class IndependentMovementTests(unittest.TestCase):
    """Fixture construction is shared; expected transitions never call implementation."""
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture(ROOT)
        import turn
        cls.turn = turn

    def check_sequences(self, kind):
        # Declarative costs, in the explicit native-first interface order.
        actions = ('standard', 'swift', 'shift_effect', 'shift_move', 'full', 'free')
        payments = {
            'standard': (('standard',),),
            'swift': (('swift',), ('standard',)),
            'shift_effect': (('shift',), ('standard',)),
            'shift_move': (('shift',), ('standard',)),
            'full': (('standard', 'shift'),),
            'free': ((),),
        }
        engine, actor, _ = self.fixture.pair(kind)
        sequences = transitions = 0
        for length in range(1, 5):
            for sequence in itertools.product(actions, repeat=length):
                sequences += 1
                self.turn.reset_budget(engine, actor)
                tokens = {'standard', 'shift', 'swift'}
                moved = False
                for action in sequence:
                    permitted_payments = [
                        cost for cost in payments[action]
                        if set(cost) <= tokens
                        and not (action == 'shift_move' and cost == ('standard',)
                                 and (kind != 'trainer' or moved))
                    ]
                    allowed = bool(permitted_payments)
                    if allowed:
                        cost = permitted_payments[0]
                        tokens -= set(cost)
                        if action == 'shift_move' and cost == ('shift',):
                            moved = True
                    actual = self.turn.spend(
                        engine, actor,
                        'shift' if action.startswith('shift_') else action,
                        'independent token oracle', movement=(action == 'shift_move'))
                    observed = (actual, actor.budget['standard'], actor.budget['shift'],
                                actor.budget['swift'], actor._regular_shift_movement_used)
                    expected = (allowed, int('standard' in tokens), int('shift' in tokens),
                                int('swift' in tokens), moved)
                    transitions += 1
                    self.assertEqual(observed, expected, (kind, sequence, action))
        COUNTS[kind] = {'sequences': sequences, 'transitions': transitions}
        self.assertEqual(1554, sequences)
        self.assertEqual(5910, transitions)

    def test_trainer_sequences(self):
        self.check_sequences('trainer')

    def test_pokemon_sequences(self):
        self.check_sequences('pokemon')

    def check_nonmovement_snapshot(self, kind):
        engine, actor, target = self.fixture.pair(kind)
        self.assertTrue(self.turn.spend(engine, actor, 'shift', 'nonmovement'))
        engine.gm.snapshot('nonmovement')
        engine.approach(actor, target)
        engine.gm.restore('nonmovement')
        engine.approach(actor, target)
        self.assertEqual((2, 0) if kind == 'trainer' else (0, 0), actor.pos)
        self.assertIs(False, actor._regular_shift_movement_used)

    def test_trainer_nonmovement_snapshot(self):
        self.check_nonmovement_snapshot('trainer')

    def test_pokemon_nonmovement_snapshot(self):
        self.check_nonmovement_snapshot('pokemon')

    def check_positive_hp_fainted(self, kind):
        engine, actor, target = self.fixture.pair(kind)
        actor.conditions.add('기절')
        before = (dict(actor.budget), actor.pos, actor._regular_shift_movement_used)
        engine.approach(actor, target)
        self.assertEqual(before, (actor.budget, actor.pos, actor._regular_shift_movement_used))

    def test_trainer_positive_hp_fainted(self):
        self.check_positive_hp_fainted('trainer')

    def test_pokemon_positive_hp_fainted(self):
        self.check_positive_hp_fainted('pokemon')

class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'id': 'MOVE-INDEPENDENT-' + test._testMethodName, 'status': 'pass'})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.records.append({'id': 'MOVE-INDEPENDENT-' + test._testMethodName, 'status': 'fail'})

    def addError(self, test, error):
        super().addError(test, error)
        self.records.append({'id': 'MOVE-INDEPENDENT-' + test._testMethodName, 'status': 'error'})

def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    COUNTS.clear()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(IndependentMovementTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    dependencies = ['engine/turn.py', 'engine/engine.py', 'engine/gm_state.py',
                    'tools/test_movement_action_budget.py', 'input/ch07-combat.md',
                    'data/verification/action-cost-semantics.json']
    hashes = {name: digest(ROOT / name) for name in dependencies}
    hashes['tools/test_movement_action_budget_independent.py'] = digest(__file__)
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': 'pass' if result.wasSuccessful() else 'fail',
        'results': result.records, 'tests_run': result.testsRun,
        'input_hashes': hashes, 'finite_sequences': dict(COUNTS),
        'total_sequences': sum(x['sequences'] for x in COUNTS.values()),
        'total_transitions': sum(x['transitions'] for x in COUNTS.values()),
        'scope': 'Native-first ordinary conscious trainer/Pokemon budget, action sequences of lengths 1..4, plus existing snapshot/fainted boundaries.',
        'limitations': [
            'Shared fixture construction is not an independent source interpretation.',
            'The expected token relation is independent code but adopts the declared native-first abstraction.',
            'Budgetless calls, free trigger eligibility, extra actions, off-turn movement, pathfinding, split movement, reverse cost selection, zero-displacement cost and held-item dropping are not certified.',
            'This reproduces prior review evidence and does not add new game mechanics or resolve source ambiguities.'
        ],
        'whole_rule_certified': False, 'semantic_completeness_proved': False,
        'coverage_percent': None,
    }
    output = args.output or ROOT / 'output/movement-action-budget-independent-tests.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return not result.wasSuccessful()

if __name__ == '__main__':
    raise SystemExit(main())

