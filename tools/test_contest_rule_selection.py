"""Contest admission regressions. Synthetic variants are not source authority evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from contest import ContestRules, ContestEngine, demo_contestants
from ruleset import RuleFilter, ExcludedRuleSelection, UnresolvedRuleSelection
import arithmetic_policy as M


class ContestSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.units = json.loads((ROOT / 'data/contest-rules.json').read_text(encoding='utf-8'))['units']
        moves = json.loads((ROOT / 'output/entities/moves.json').read_text(encoding='utf-8'))
        cls.attract = next(m for m in moves if m['id'] == 'move/헤롱헤롱')
        cls.arithmetic_unit = next(u for line in (ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines() if (u:=json.loads(line))['id']==M.SOURCE)

    def test_replaced_filter_requires_new_selection_before_any_read(self):
        rules=self.rules()
        uid=self.units[0]['id']
        rules.ruleset=RuleFilter({'exclude_units':[uid]})
        for read in (lambda:rules.mech(uid),lambda:rules.move('move/헤롱헤롱'),lambda:rules._selected_rule(uid)):
            with self.assertRaisesRegex(UnresolvedRuleSelection,'selection_profile_changed'):
                read()

    def rules(self, profile=None, moves=None, units=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'data').mkdir()
        (root / 'output/entities').mkdir(parents=True)
        (root / 'data/rulesets.json').write_bytes((ROOT / 'data/rulesets.json').read_bytes())
        (root / 'data/contest-rules.json').write_text(json.dumps({'units': self.units if units is None else units}, ensure_ascii=False), encoding='utf-8')
        (root / 'output/entities/moves.json').write_text(json.dumps([self.attract] if moves is None else moves, ensure_ascii=False), encoding='utf-8')
        (root/'output/ruleunits.jsonl').write_text(json.dumps(self.arithmetic_unit,ensure_ascii=False)+'\n',encoding='utf-8')
        return ContestRules(root, ruleset=profile)

    def state(self, e, cs):
        return deepcopy([vars(c) for c in cs]), e.rng.getstate(), list(e.log_lines)

    def assert_rejected(self, rules, exc, move='헤롱헤롱', **kwargs):
        e, cs = ContestEngine(rules, seed=7), demo_contestants()
        before = self.state(e, cs)
        with self.assertRaises(exc):
            e.perform(cs[0], move, '귀여움', cs[1:], True, spend_stat_dice=1, **kwargs)
        self.assertEqual(self.state(e, cs), before)

    def test_arithmetic_source_exclusion_rejects_before_mutation(self):
        self.assert_rejected(self.rules(RuleFilter({'exclude_units':[M.SOURCE]})),ExcludedRuleSelection)

    def test_default_all_and_core_preserve_fixed_appeal_example(self):
        for profile in (None, 'all', 'core'):
            with self.subTest(profile=profile):
                r = ContestRules(ROOT, ruleset=profile)
                self.assertEqual(r.ruleset.name, profile or 'all')
                e, cs = ContestEngine(r), demo_contestants()
                e.perform(cs[0], '헤롱헤롱', '귀여움', cs[1:], True, fixed_rolls=[3, 2, 6, 1])
                self.assertEqual((cs[0].appeal, cs[0].fumble, cs[0].excitement), (4, 1, 2))

    def test_actual_no_ohko_rejects_by_name_and_id(self):
        r = ContestRules(ROOT, ruleset='no-ohko')
        for move in ('절대영도', 'move/절대영도'):
            self.assert_rejected(r, ExcludedRuleSelection, move)

    def test_excluded_move_cannot_reenter_by_name_or_id(self):
        r = self.rules(RuleFilter({'exclude_units': ['move/헤롱헤롱']}))
        for move in ('헤롱헤롱', 'move/헤롱헤롱'):
            self.assert_rejected(r, ExcludedRuleSelection, move)
        self.assertNotIn('헤롱헤롱', r.moves)

    def test_each_performance_dependency_rejects_before_mutation(self):
        for suffix in ('performance-stage', 'effects', 'excitement', 'type-match', 'stat-dice', 'appeal-scoring'):
            with self.subTest(rule=suffix):
                self.assert_rejected(self.rules(RuleFilter({'exclude_units': ['contest/' + suffix]})), ExcludedRuleSelection)

    def test_run_checks_intro_and_positions_before_logs_or_rolls(self):
        for suffix in ('intro-stage', 'position-tables'):
            r = self.rules(RuleFilter({'exclude_units': ['contest/' + suffix]}))
            e, cs = ContestEngine(r), demo_contestants()
            before = self.state(e, cs)
            with self.assertRaises(ExcludedRuleSelection):
                e.run(cs, '귀여움', lambda *args: ('헤롱헤롱', 0))
            self.assertEqual(self.state(e, cs), before)

    def test_run_checks_declared_moves_before_intro(self):
        r = ContestRules(ROOT, RuleFilter({'exclude_units': ['move/유턴']}))
        e, cs = ContestEngine(r), demo_contestants()
        before = self.state(e, cs)
        with self.assertRaises(ExcludedRuleSelection):
            e.run(cs, '귀여움', lambda *args: ('헤롱헤롱', 0))
        self.assertEqual(self.state(e, cs), before)

    def test_unknown_move_provenance_is_not_filled_from_kind(self):
        for source in (None, {}, {'file': 'unregistered.md'}):
            m = deepcopy(self.attract)
            m.pop('_source', None)
            if source is not None:
                m['_source'] = source
            self.assert_rejected(self.rules(moves=[m]), UnresolvedRuleSelection)

    def test_unknown_rule_provenance_is_not_filled_from_contest_file(self):
        units = deepcopy(self.units)
        next(u for u in units if u['id'] == 'contest/appeal-scoring')['source'] = {}
        self.assert_rejected(self.rules(units=units), UnresolvedRuleSelection)

    def test_supplement_fixture_requires_selected_source_group(self):
        m = deepcopy(self.attract)
        m['_source'] = {'file': 'supp-fantasy.md', 'test_fixture': True}
        self.assert_rejected(self.rules('core', moves=[m]), ExcludedRuleSelection)
        self.assertEqual(self.rules('all', moves=[m]).move_contest(m['id']), ('귀여움', '고조'))

    def variant_moves(self):
        base = deepcopy(self.attract)
        base.update(id='move/test-base', name='선택 검사', frequency='장면 x1')
        variant = deepcopy(base)
        variant.update(id='move/test-base-playtest', name='선택 검사 [Playtest]', contest='귀여움 - 반전 어필', frequency='장면 x2')
        return base, variant

    def test_variant_alias_selects_one_record_for_all_fields(self):
        base, variant = self.variant_moves()
        r = self.rules(RuleFilter({'variant_replaces_core': True}), moves=[base, variant])
        for key in (base['id'], base['name'], variant['id'], variant['name']):
            self.assertEqual(r.move(key)['id'], variant['id'])
            self.assertEqual(r.move(key)['frequency'], '장면 x2')
            self.assertEqual(r.move_contest(key), ('귀여움', '반전 어필'))
        e, cs = ContestEngine(r), demo_contestants()
        cs[0].moves = [base['id']]
        e.perform(cs[0], base['name'], '귀여움', [], False, fixed_rolls=[6] * 6)
        self.assertEqual(cs[0].last_move, variant['id'])

    def test_competing_variants_require_explicit_choice(self):
        base, variant = self.variant_moves()
        second = dict(variant, id='move/test-base-playtest-2', name='선택 검사 [Playtest]')
        r = self.rules(RuleFilter({'variant_replaces_core': True}), moves=[base, variant, second])
        self.assert_rejected(r, UnresolvedRuleSelection, base['id'])
        chosen = self.rules(RuleFilter({'variant_replaces_core': True, 'variant_choices': {base['id']: second['id']}}), moves=[base, variant, second])
        self.assertEqual(chosen.move(base['id'])['id'], second['id'])

    def test_version_on_replaced_identity_stays_unresolved(self):
        base, variant = self.variant_moves()
        r = self.rules(RuleFilter({'variant_replaces_core': True, 'unit_versions': {base['id']: 'v2'}}), moves=[base, variant])
        self.assert_rejected(r, UnresolvedRuleSelection, base['id'])

    def test_legacy_capture_profile_accepts_out_of_domain_version(self):
        self.assertEqual(ContestRules(ROOT, 'legacy-capture').move_contest('헤롱헤롱'), ('귀여움', '고조'))

    def test_cli_isolated_mode_exposes_ruleset_option(self):
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-I', str(ROOT / 'engine/contest.py'), '--help'], text=True, encoding='utf8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--ruleset', result.stdout)

    def test_core_does_not_admit_explicit_variant(self):
        base, variant = self.variant_moves()
        r = self.rules('core', moves=[base, variant])
        self.assertEqual(r.move(base['id'])['id'], base['id'])
        self.assert_rejected(r, ExcludedRuleSelection, variant['id'])

    def test_same_name_ids_are_ambiguous_but_exact_id_works(self):
        m = deepcopy(self.attract)
        m['id'], m['contest'] = 'move/test-second', '귀여움 - 반전 어필'
        r = self.rules(moves=[self.attract, m])
        self.assert_rejected(r, UnresolvedRuleSelection)
        self.assertEqual(r.move_contest(m['id']), ('귀여움', '반전 어필'))
        self.assertNotIn('헤롱헤롱', r.moves)

    def test_missing_identity_rejects_before_mutation(self):
        self.assert_rejected(self.rules(), UnresolvedRuleSelection, 'move/not-stored')

    def test_selected_mech_version_changes_scoring(self):
        units = deepcopy(self.units)
        score = next(u for u in units if u['id'] == 'contest/appeal-scoring')['mech']['data']
        score['test_version'] = {'normal': dict(score['normal'], **{'6': {'appeal': 4}})}
        r = self.rules(RuleFilter({'unit_versions': {'contest/appeal-scoring': 'test_version'}}), units=units)
        self.assertEqual(ContestEngine(r).score([6], False), (4, 0))
        self.assertEqual(r.mech('contest/appeal-scoring')['_version'], 'test_version')

    def test_missing_mech_version_rejects_before_mutation(self):
        r = self.rules(RuleFilter({'unit_versions': {'contest/appeal-scoring': 'not-stored'}}))
        self.assert_rejected(r, ValueError)

    def test_unsupported_move_version_is_not_ignored(self):
        r = self.rules(RuleFilter({'unit_versions': {'move/헤롱헤롱': 'other'}}))
        self.assert_rejected(r, UnresolvedRuleSelection)

    def test_duplicate_identity_cannot_overwrite_record(self):
        with self.assertRaises(ValueError):
            self.rules(moves=[self.attract, self.attract])

    def test_unknown_profile_choice_is_not_ignored(self):
        with self.assertRaises(ValueError):
            self.rules(RuleFilter({'unit_versions': {'contest/missing': 'v2'}}))

    def test_public_views_and_returned_records_are_detached(self):
        r = self.rules()
        r.moves['헤롱헤롱']['contest'] = '귀여움 - 반전 어필'
        r.units['contest/excitement']['mech']['data']['max'] = 999
        r.move('헤롱헤롱')['contest'] = '귀여움 - 반전 어필'
        r.mech('contest/excitement')['max'] = 999
        self.assertEqual(r.move_contest('헤롱헤롱'), ('귀여움', '고조'))
        self.assertEqual(r.mech('contest/excitement')['max'], 5)

    def test_optional_coordinator_rule_is_admitted_before_reroll(self):
        r = ContestRules(ROOT, RuleFilter({'exclude_units': ['class/코디네이터']}))
        self.assert_rejected(r, ExcludedRuleSelection, reroll_ok=True)


if __name__ == '__main__':
    class Result(unittest.TextTestResult):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.rows = []
        def addSuccess(self, t):
            super().addSuccess(t)
            self.rows.append(dict(id='CONTEST-SELECTION-' + t._testMethodName, status='pass'))
        def addFailure(self, t, err):
            super().addFailure(t, err)
            self.rows.append(dict(id='CONTEST-SELECTION-' + t._testMethodName, status='fail'))
        def addError(self, t, err):
            super().addError(t, err)
            self.rows.append(dict(id='CONTEST-SELECTION-' + t._testMethodName, status='error'))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContestSelectionTests))
    paths = [Path(__file__), ROOT / 'engine/contest.py', ROOT / 'engine/ruleset.py', ROOT / 'engine/resolution_transaction.py', ROOT / 'engine/common_checks.py', ROOT / 'data/rulesets.json', ROOT / 'data/contest-rules.json', ROOT / 'output/entities/moves.json', ROOT / 'output/ruleunits.jsonl', ROOT / 'data/verification/rule-selection-semantics.json']
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(), scope='Contest public readers and operation admission before state/RNG/log mutation. Synthetic versions and variants do not certify source authority or all contest semantics.', results=result.rows, input_hashes={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT / 'output/contest-rule-selection-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
