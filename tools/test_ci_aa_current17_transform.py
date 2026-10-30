"""Synthetic current17 adapter checks, source-only and not executed here.

No artifact retrieval, decryption, game execution, acceptance or publication.
Run remotely with the sibling public/tools overlay and unchanged ci_aa_recovery.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'public'/'tools'),
                str(Path(__file__).resolve().parents[1]/'tools')]
import ci_aa_acceptance as A


class Current17TransformTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ['RUNNER_TEMP']).resolve()
        if scratch.drive.upper() != 'D:':
            raise RuntimeError('D-only remote synthetic validation requires RUNNER_TEMP on D:')
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'tools').mkdir()
        (self.root/'records').mkdir()
        (self.root/A.REVIEWED_SOURCE_PATCH).write_text('reviewed\n', encoding='utf-8')
        self.old50 = ['tools.old.OldTests.test_case_'+str(i) for i in range(50)]
        self.old8 = [A.GAS_CASE] + ['tools.current.CurrentTests.test_case_'+str(i) for i in range(7)]
        self.exact17 = [A.GAS_CASE, *A.ENTRAINMENT_CASES] + [
            'tools.other.OtherTests.test_case_'+str(i) for i in range(13)]
        self.digest = hashlib.sha256(json.dumps(sorted(self.exact17)).encode()).hexdigest()
        self.suite = dict(required_unique_count=17, completed={'synthetic':dict(tests=self.exact17)})
        ledger = 'data/verification/category2-csv-abilities-moves-status.json'
        self.pins = {'engine/engine.py':'a'*64, ledger:'a'*64}
        self.candidate = dict(
            completed={'C2CSV-MOVE-R0479':dict(reused_test_ids=self.old50+self.old8)},
            required_test_ids=self.old8[:], required_test_modules=['tools.current'],
            reviewed_files=[], retained_proof=dict(
                runtime_test_source_sha256=self.pins.copy(), historical_related_case_ids=self.old50+self.old8,
                impact_review={}, obligation_mapping={'C2CSV-MOVE-R0479':dict(requirements=[
                    dict(obligation='Native source header remains Scene, AC2, range4 one target',
                         test_ids=self.old50+self.old8, current_boundary_pending=self.old8[:])])}))
        self.histories = {}
        for label, ids in (('original',self.old50), ('current',self.old8), ('current17',self.exact17)):
            stage = 'D:/synthetic/'+label
            log = self.root/(label+'.log')
            log.write_text(''.join(case.rsplit('.',1)[-1]+' ('+case+') ... ok\n' for case in ids), encoding='utf-8')
            self.histories[label] = dict(log=log, meta=dict(execution_stage=stage, test_ids=ids[:]),
                provenance=dict(original_h_summary=dict(required_ids_sha256=self.digest)))
        self.histories['current']['meta']['runtime_test_data_sha256_before'] = {
            str(PureWindowsPath('D:/synthetic/current')/'engine/engine.py'):'a'*64}
        paths = set(self.pins) | set(A.CHANGED_EXISTING_SOURCES) | {
            'engine/frequency.py','engine/body_state.py','engine/weapon_actions.py',
            'engine/custom_species.py','engine/fast_combat.py',
            'tools/test_entrainment_header_boundaries.py','tools/test_blinded_living_weapon_movement.py',
            '.ci/suites/changed_revisions.json'}
        self.histories['current17']['meta']['runtime_test_data_sha256_before'] = {
            str(PureWindowsPath('D:/synthetic/current17')/name):'a'*64 for name in paths}
        self.changed = set(A.REPAIR_SOURCE_PATHS)
        self.records = {}

    def fake_git(self, root, *args):
        if args[0] == 'show':
            return json.dumps(self.suite).encode()
        if args[:2] == ('diff','--name-only'):
            return '\n'.join(sorted(self.changed)).encode()
        if args[:2] == ('diff','--full-index'):
            return b'reviewed\n'
        raise AssertionError(args)

    def transform(self):
        bound = dict(A.ARTIFACTS['current17'], required_ids_sha256=self.digest)
        with patch.dict(A.ARTIFACTS, current17=bound), patch.object(A,'git',side_effect=self.fake_git), \
             patch.object(A.ci,'file_hash',return_value='a'*64), \
             patch.object(A,'write',side_effect=lambda path,value:self.records.update({str(path):deepcopy(value)})):
            return A.current17_transform(self.root,self.root,self.root,self.candidate,
                dict(retained_valid_case_ids=self.old50),
                dict(historical_evidence=dict(current8_actual_ids=self.old8)),
                self.histories,self.pins,lambda value:value)

    def test_replaces_only_gas_evidence_and_adds_three_unique_header_witnesses(self):
        pins, selections, count = self.transform()
        groups = dict(selections)
        self.assertEqual(count, 61)  # Synthetic set cardinality only, not real acceptance.
        self.assertEqual(groups['original'], self.old50)
        self.assertEqual(groups['current'], self.old8[1:])
        self.assertEqual(groups['current17'], [A.GAS_CASE,*A.ENTRAINMENT_CASES])
        self.assertEqual(self.histories['current']['meta']['test_ids'],self.old8)
        requirements = self.candidate['retained_proof']['obligation_mapping']['C2CSV-MOVE-R0479']['requirements']
        self.assertEqual([row['test_ids'] for row in requirements[-3:]],[[case] for case in A.ENTRAINMENT_CASES])
        self.assertTrue(self.records[str(self.root/'records/current17-transform.json')]['publication']['rebase_required'])

    def test_generated_ledger_remains_pinned_without_becoming_reviewed_input(self):
        ledger = 'data/verification/category2-csv-abilities-moves-status.json'
        reviewed = 'input/db/moves.csv#source-header'
        self.candidate['reviewed_files'] = [reviewed]
        pins, _, _ = self.transform()
        self.assertEqual(pins[ledger], self.pins[ledger])
        self.assertEqual(self.candidate['retained_proof']['runtime_test_source_sha256'], pins)
        self.assertEqual(set(self.candidate['reviewed_files']), (set(pins)-{ledger}) | {reviewed})

    def test_same_count_different_current17_selection_is_rejected(self):
        self.histories['current17']['meta']['test_ids'][-1] = 'tools.forged.ForgedTests.test_other'
        with self.assertRaisesRegex(ValueError,'AA_CURRENT17_EXACT_SELECTION_DIFFERS'):
            self.transform()

    def test_wrong_required_id_h_digest_is_rejected(self):
        self.histories['current17']['provenance']['original_h_summary']['required_ids_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError,'AA_CURRENT17_REQUIRED_ID_BINDING_DIFFERS'):
            self.transform()

    def test_unreviewed_runtime_change_is_rejected(self):
        self.changed.add('engine/ability_transitions.py')
        with self.assertRaisesRegex(ValueError,'AA_CURRENT8_TO_17_CHANGED_PATHS_DIFFER'):
            self.transform()

    def test_missing_current17_frozen_source_pin_is_rejected(self):
        self.histories['current17']['meta']['runtime_test_data_sha256_before'].pop(
            str(PureWindowsPath('D:/synthetic/current17')/'engine/frequency.py'))
        with self.assertRaisesRegex(ValueError,'AA_CURRENT17_FROZEN_SOURCE_PIN_MISSING'):
            self.transform()

    def test_old8_identity_mismatch_is_rejected_without_relabeling_old_pass(self):
        self.histories['current']['meta']['test_ids'][0] = 'tools.wrong.WrongTests.test_old'
        with self.assertRaisesRegex(ValueError,'AA_HISTORICAL_SELECTED_ID_BINDING_DIFFERS'):
            self.transform()

    def test_unknown_manifest_shape_records_diagnostic_and_fails_closed(self):
        with patch.object(A,'write',side_effect=lambda path,value:self.records.update({str(path):value})):
            with self.assertRaisesRegex(ValueError,'AA_PACKAGE_MANIFEST_SCHEMA_UNCONFIRMED'):
                A.check_package_manifest_shape({'schema_version':1,'entries':[]},self.root)
        self.assertIn(str(self.root/'records/package-manifest-shape.json'),self.records)


if __name__ == '__main__':
    unittest.main()
