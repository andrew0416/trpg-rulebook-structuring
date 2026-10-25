"""Explicit native exclusions retain core refusal before feature/source readers."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from ruleset import RuleFilter, UnresolvedRuleSelection
from source_selection import SourceChangedError
from native_scenario_fixture import assert_logged_refusal_unchanged
import test_book_taskmaster_hardened as TASKMASTER
import test_book_duelist_momentum as DUELIST
import telekinetic as TELEKINETIC
import duelist


class NativeMoveExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def fixture(self, *, rules=None, hardened=False):
        case = TASKMASTER.TaskmasterTests()
        case.rules = self.rules if rules is None else rules
        case.setup(acquire=hardened)
        if hardened:
            case.train()
        case.combat(case.p)
        return case

    def operation(self, case, entry, move_id):
        if entry == 'use_move':
            return lambda: case.e.use_move(case.p, case.b, move_id)
        return lambda: case.e.use_move_on(case.p, case.b, move_id, case.e.everyone)

    def refusal(self, case, entry, move_id):
        rules = case.rules
        message = (f"  {case.p.name} {rules.moves[move_id]['name']}: "
                   f"룰셋 '{rules.ruleset.name}' 에서 제외된 기술"
                   f"({rules.excluded_moves[move_id]}) → 사용 불가  => [ruleset/exclude]")
        return assert_logged_refusal_unchanged(
            case.e, self.operation(case, entry, move_id),
            expected_result=0, expected_logs=[message])

    def test_public_explicit_exclusion_logs_once_without_PP_budget_HP_or_RNG_change(self):
        for entry in ('use_move', 'use_move_on'):
            for hardened in (False, True):
                with self.subTest(entry=entry, hardened=hardened):
                    case = self.fixture(hardened=hardened)
                    self.assertIn('move/폴리곤-쇼크', case.rules.excluded_moves)
                    self.refusal(case, entry, 'move/폴리곤-쇼크')
                    self.assertEqual(case.p.budget['standard'], 1)
                    self.assertEqual(case.p.move_uses.get('move/폴리곤-쇼크', 0), 0)

    def test_excluded_Telekinetic_moves_do_not_create_placement_or_push_pending(self):
        rules = Rules(ROOT, ruleset='core')
        profile = deepcopy(rules.ruleset.profile)
        profile['exclude_units'] = list(profile.get('exclude_units', [])) + [
            TELEKINETIC.BARRIER, TELEKINETIC.PSYCHIC, TELEKINETIC.LIFT]
        rules.ruleset = RuleFilter(profile, 'explicit-native-exclusions')
        rules._apply_ruleset()
        for entry in ('use_move', 'use_move_on'):
            for move_id in (TELEKINETIC.BARRIER, TELEKINETIC.PSYCHIC, TELEKINETIC.LIFT):
                with self.subTest(entry=entry, move_id=move_id):
                    self.refusal(self.fixture(rules=rules), entry, move_id)

    def test_explicit_excluded_nonpositive_HP_move_keeps_core_refusal(self):
        rules = Rules(ROOT, ruleset='no-ohko')
        for entry in ('use_move', 'use_move_on'):
            with self.subTest(entry=entry):
                case = self.fixture(rules=rules)
                case.hp(case.p, 0)
                self.assertTrue(case.p.fainted)
                self.refusal(case, entry, 'move/대폭발')

    def test_unresolved_and_stale_selection_are_not_normalized_to_exclusion(self):
        for entry in ('use_move', 'use_move_on'):
            for failure in ('unresolved', 'stale'):
                with self.subTest(entry=entry, failure=failure):
                    rules = Rules(ROOT, ruleset='core')
                    case = self.fixture(rules=rules)
                    before = case.e.export_state()
                    move_id = 'move/폴리곤-쇼크'
                    if failure == 'unresolved':
                        rules.unresolved_moves[move_id] = ['move/a', 'move/b']
                    else:
                        rules.ruleset.exclude_units.add('move/물대포')
                    try:
                        with self.assertRaises(UnresolvedRuleSelection) as raised:
                            self.operation(case, entry, move_id)()
                        if failure == 'unresolved':
                            self.assertEqual(raised.exception.candidates, ('move/a', 'move/b'))
                        else:
                            self.assertIn('selection_profile_changed', str(raised.exception))
                    finally:
                        if failure == 'unresolved':
                            del rules.unresolved_moves[move_id]
                        else:
                            rules.ruleset.exclude_units.remove('move/물대포')
                    self.assertEqual(case.e.export_state(), before)

    def test_selected_source_corruption_keeps_real_error_and_unchanged_world(self):
        for entry in ('use_move', 'use_move_on'):
            with self.subTest(entry=entry):
                rules = Rules(ROOT, ruleset='core')
                case = self.fixture(rules=rules)
                before = case.e.export_state()
                origin = rules.selection.units['move/물대포']['source']
                original = deepcopy(origin)
                origin['sha256'] = '0' * 64
                try:
                    with self.assertRaises(SourceChangedError):
                        self.operation(case, entry, 'move/물대포')()
                finally:
                    origin.clear()
                    origin.update(original)
                self.assertEqual(case.e.export_state(), before)

    def test_selected_Taskmaster_and_Duelist_keep_actual_native_move_consumers(self):
        case = self.fixture(hardened=True)
        case.injury(case.p, 5)
        hp = case.p.hp
        self.assertGreater(case.attack(case.p, case.b), 0)
        self.assertEqual(case.p.hp, hp)
        self.assertEqual(case.p.budget['standard'], 0)
        self.assertEqual(case.p.move_uses['move/물대포'], 1)
        case.valid()

        case = DUELIST.DuelistMomentumTests()
        case.rules = Rules(ROOT, ruleset='all')
        case.setup()
        case.start(case.p)
        self.assertGreater(case.attack(), 0)
        self.assertEqual(duelist.momentum(case.p), 1)
        self.assertEqual(case.p.budget['standard'], 0)
        self.assertEqual(case.p.move_uses['move/몸통박치기'], 1)
        case.valid()


if __name__ == '__main__':
    unittest.main()
