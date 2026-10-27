"""Synthetic publication workflow checks; no native execution or completion credit."""
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import ast
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import reconcile_batch as batch

HERE = Path(__file__).resolve().parent
module_spec = spec_from_file_location('publication_workflow_draft', HERE/'verify_ordered_core.py')
workflow = module_from_spec(module_spec)
module_spec.loader.exec_module(workflow)


class PublicationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='publication-unit-', dir=os.environ['TEMP'])
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root, self.stage = self.base/'canonical', self.base/'stage'
        self.root.mkdir()
        self.stage.mkdir()
        self.source_sha = sha256(b'synthetic source\n').hexdigest()
        for number in range(40):
            self.write(self.root/f'input/source-{number:02}.md', b'synthetic source\n')
        self.source = 'input/source-00.md'
        self.write(self.root/'tools/report_category2_progress.py',
                   (batch.R/'tools/report_category2_progress.py').read_bytes())
        for name in ('engine/world_entities.py', 'engine/other.py',
                     'work/reuse-partials/verify_overlay_tests.py'):
            self.write(self.root/name, b'# synthetic protected fixture\n')
        self.reporter = workflow._publication_reporter(self.root)
        self.addCleanup(patch.stopall)
        patch.object(self.reporter, 'collect_edge_reuse', return_value={
            'completed': 1, 'denominator': 1, 'validation_errors': []}).start()
        patch.object(workflow, '_publication_reporter', return_value=self.reporter).start()
        self.metadata = patch.object(workflow, 'validate_candidate_metadata').start()
        self.documents = {}
        for group, filename, key in self.reporter.SOURCES:
            count = 6072 if group == 'core' else 1
            rows = [self.row(group, number) for number in range(count)]
            self.documents[group] = (filename, key, rows)
            self.save(self.root/'data/verification'/filename, {key: rows})
        ids = [row.get('clause_id') or row.get('source_clause_id') or row.get('row_id') or row['id']
               for group, (_, _, rows) in self.documents.items()
               for number, row in enumerate(rows) if group != 'core' or number < 2344]
        self.save(self.root/workflow._PUBLICATION_FREEZE, dict(
            revision='synthetic', denominator=2352, included_clause_ids=sorted(ids),
            source_manifest=[dict(file=f'input/source-{n:02}.md', sha256=self.source_sha)
                             for n in range(40)], reference_only_sources=[]))
        self.save(self.root/workflow._PUBLICATION_PROGRESS, self.reporter.collect(self.root))
        self.core_name = 'data/verification/'+self.documents['core'][0]
        self.progress_name = workflow._PUBLICATION_PROGRESS
        self.names = [self.core_name, self.progress_name]
        self.manifest = self.stage/'artifacts.json'
        self.candidate = self.stage/'candidate.json'
        self.save(self.manifest, self.names)
        self.spec = dict(id='synthetic', completed_before=0, completed={'core-0': {'registry': 'core'}})
        self.save(self.candidate, self.spec)
        self.core = deepcopy(self.documents['core'][2])
        self.core[0].update(category2_status='implemented', tests=['synthetic_only'])
        self.refresh_stage()
        self.save(self.stage/'baseline.json', {name: self.hash(self.root/name) for name in self.names})

    @staticmethod
    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def save(self, path, value):
        self.write(path, (json.dumps(value, ensure_ascii=False)+'\n').encode('utf8'))

    @staticmethod
    def hash(path):
        return sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    def row(self, group, number):
        uid = f'{group}-{number}'
        common = dict(source_file=self.source, source_sha256=self.source_sha,
                      statement='synthetic immutable statement', children=[
                          dict(id='child', obligation='immutable child', status='incomplete')])
        if group in ('core', 'core-additional'):
            return dict(common, clause_id=uid, category2_included=group != 'core' or number < 2344,
                        category2_status='incomplete', statement_sha256='a'*64)
        if group == 'classes':
            return dict(common, source_clause_id=uid, id=uid, include_category2=True, status='incomplete')
        if group == 'csv-abilities-moves':
            return dict(common, row_id=uid, category2_included=True, denominator_contribution=1,
                        category2_status='incomplete')
        if group == 'csv-classes':
            return dict(id=uid, file=self.source, file_sha256=self.source_sha, cells=['source'],
                        include_category2=True, dedupe_target=None, status='incomplete')
        if group == 'csv-core':
            return dict(common, id=uid, include_category2=True, denominator_contribution=1, status='incomplete')
        return dict(clause_id=uid, category2_in_scope=True, status='incomplete',
                    source=[dict(file=self.source, file_sha256=self.source_sha)],
                    statement='synthetic immutable statement')

    def refresh_stage(self):
        self.save(self.stage/self.core_name, {self.documents['core'][1]: self.core})
        projected = self.base/'fixture-projection'
        if projected.exists():
            self.assertTrue(projected.resolve().is_relative_to(self.base.resolve()))
            shutil.rmtree(projected)
        shutil.copytree(self.root, projected)
        self.write(projected/self.core_name, (self.stage/self.core_name).read_bytes())
        self.save(self.stage/self.progress_name, self.reporter.collect(projected))

    def pre(self):
        return workflow.publication_check(self.stage, Path('candidate.json'), Path('artifacts.json'), self.root)

    def publish_fixture(self, pre):
        self.pre_path = self.stage/'pre.json'
        self.save(self.pre_path, pre)
        for name in self.names:
            self.write(self.root/name, (self.stage/name).read_bytes())
        self.save(self.stage/'baseline.json', dict(pre['preimages'], **pre['pins']['artifacts']))

    def post(self):
        return workflow.publication_check(self.stage, self.candidate, self.manifest,
                                          self.root, pre_record=self.pre_path.name)

    def test_pre_post_roundtrip_uses_actual_reporter_and_does_not_publish(self):
        initial = (self.root/self.core_name).read_bytes()
        pre = self.pre()
        self.assertEqual((pre['before'], pre['after'], pre['registry_rows']), (0, 1, 6080))
        self.assertEqual(pre['non_target_unchanged'], 6079)
        self.assertEqual((self.root/self.core_name).read_bytes(), initial)
        self.metadata.assert_called_once_with(self.spec, repo_root=self.root, stage=self.stage)
        self.publish_fixture(pre)
        post = self.post()
        self.assertEqual(post['status'], 'published_postgate_pass')
        self.assertEqual(post['root_new_game_runs'], 0)

    def test_stale_unlisted_stage_registry_is_not_overlaid(self):
        filename, key, rows = self.documents['csv-classes']
        stale = deepcopy(rows)
        stale[0]['include_category2'] = False
        self.save(self.stage/'data/verification'/filename, {key: stale})
        self.assertEqual(self.pre()['after'], 1)

    def test_extra_non_target_change_is_rejected(self):
        self.core[1]['tests'] = ['not targeted']
        self.refresh_stage()
        with self.assertRaisesRegex(RuntimeError, 'exact completed targets'):
            self.pre()

    def test_target_source_and_child_contracts_cannot_change(self):
        for mutation in ('statement', 'child'):
            with self.subTest(mutation=mutation):
                original = deepcopy(self.core[0])
                if mutation == 'statement':
                    self.core[0]['statement'] = 'rewritten source'
                else:
                    self.core[0]['children'][0]['obligation'] = 'rewritten child'
                self.refresh_stage()
                with self.assertRaisesRegex(RuntimeError, 'source/include/dedupe'):
                    self.pre()
                self.core[0] = original

    def test_duplicate_identity_and_6081st_row_are_rejected(self):
        for extra in (deepcopy(self.core[0]), dict(self.core[-1], clause_id='new-outside-row')):
            with self.subTest(extra=extra['clause_id']):
                self.core.append(extra)
                self.refresh_stage()
                with self.assertRaises(RuntimeError):
                    self.pre()
                self.core.pop()

    def test_flat_current_baseline_is_required(self):
        original = workflow._publication_json(self.stage/'baseline.json')
        for value in ({'context': {'sha256': 'a'*64}},
                      dict(original, **{self.core_name: 'a'*64}), {}):
            with self.subTest(value=value):
                self.save(self.stage/'baseline.json', value)
                with self.assertRaises(RuntimeError):
                    self.pre()

    def test_unsafe_duplicate_and_protected_names_are_rejected(self):
        for names in ([self.core_name, '../escape'], [self.core_name, self.core_name.upper()],
                      [*self.names, 'engine/world_entities.py']):
            with self.subTest(names=names):
                self.save(self.manifest, names)
                if 'engine/world_entities.py' in names:
                    self.write(self.stage/'engine/world_entities.py', b'# bad\n')
                with self.assertRaises(RuntimeError):
                    self.pre()

    def test_mixed_case_world_and_runner_names_cannot_bypass_fixed_protection(self):
        for name in ('Engine/World_Entities.py', 'Work/Reuse-Partials/Verify_Overlay_Tests.py'):
            with self.subTest(name=name):
                self.write(self.stage/name, b'# synthetic protected overwrite attempt\n')
                self.save(self.manifest, [*self.names, name])
                with self.assertRaisesRegex(RuntimeError, 'World and native runner'):
                    self.pre()

    def test_cli_report_is_exclusive_utf8_and_console_summary_is_small(self):
        result = dict(status='prepublication_gate_pass', before=0, after=1, registry_rows=6080,
                      protected_count=1490, protected={'원문 보존': 'a'*64})
        output = StringIO()
        options = ['verify_ordered_core.py', str(self.stage), '--publication-check', 'pre',
                   '--repo-root', str(self.root), '--artifact-manifest', str(self.manifest),
                   '--report', 'root-publication-pre.json']
        with patch.object(sys, 'argv', options), \
             patch.object(workflow, 'publication_check', return_value=result), redirect_stdout(output):
            workflow.main()
            with self.assertRaises(FileExistsError):
                workflow.main()
        path = self.stage/'root-publication-pre.json'
        self.assertEqual(json.loads(path.read_text(encoding='utf8')), result)
        self.assertIn('원문 보존'.encode('utf8'), path.read_bytes())
        summary = json.loads(output.getvalue())
        self.assertNotIn('protected', summary)
        self.assertEqual(summary['report'], str(path))

    def test_candidate_before_and_saved_report_must_match_current(self):
        self.save(self.candidate, dict(self.spec, completed_before=1))
        with self.assertRaisesRegex(RuntimeError, 'completed_before'):
            self.pre()
        self.save(self.candidate, self.spec)
        saved = workflow._publication_json(self.root/self.progress_name)
        saved['completed_clause_count'] = 99
        self.save(self.root/self.progress_name, saved)
        baseline = workflow._publication_json(self.stage/'baseline.json')
        baseline[self.progress_name] = self.hash(self.root/self.progress_name)
        self.save(self.stage/'baseline.json', baseline)
        with self.assertRaisesRegex(RuntimeError, 'saved progress'):
            self.pre()

    def test_included_id_swap_is_rejected_even_at_same_denominator(self):
        self.core[1]['category2_included'] = False
        self.core[2344]['category2_included'] = True
        self.refresh_stage()
        with self.assertRaises(RuntimeError):
            self.pre()

    def test_source_input_and_freeze_changes_are_rejected(self):
        self.names.append(self.source)
        self.write(self.stage/self.source, b'changed original input\n')
        self.save(self.manifest, self.names)
        baseline = workflow._publication_json(self.stage/'baseline.json')
        baseline[self.source] = self.hash(self.root/self.source)
        self.save(self.stage/'baseline.json', baseline)
        with self.assertRaises(RuntimeError):
            self.pre()

    def test_post_protected_inventory_change_is_rejected(self):
        pre = self.pre()
        self.publish_fixture(pre)
        self.write(self.root/'engine/new_unpublished.py', b'# concurrent addition\n')
        with self.assertRaisesRegex(RuntimeError, 'protected Python'):
            self.post()

    def test_pre_rejects_staged_artifact_mutation_during_collect(self):
        snapshot = workflow._publication_snapshot
        def mutate(*args, **kwargs):
            result = snapshot(*args, **kwargs)
            if len(args) > 2 and args[2] is not None:
                path = self.stage/self.core_name
                self.write(path, path.read_bytes()+b' ')
            return result
        with patch.object(workflow, '_publication_snapshot', side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, 'changed during pre'):
                self.pre()

    def test_post_rejects_protected_mutation_during_collect(self):
        pre = self.pre()
        self.publish_fixture(pre)
        snapshot = workflow._publication_snapshot
        def mutate(*args, **kwargs):
            result = snapshot(*args, **kwargs)
            self.write(self.root/'engine/other.py', b'# changed during check\n')
            return result
        with patch.object(workflow, '_publication_snapshot', side_effect=mutate):
            with self.assertRaisesRegex(RuntimeError, 'changed during post'):
                self.post()

    def test_post_artifact_candidate_and_manifest_pins_cannot_be_relabelled(self):
        pre = self.pre()
        self.publish_fixture(pre)
        for path in (self.stage/self.core_name, self.candidate, self.manifest):
            original = path.read_bytes()
            self.write(path, original+b' ')
            with self.subTest(path=path):
                with self.assertRaisesRegex(RuntimeError, 'pre record'):
                    self.post()
            self.write(path, original)

    def test_post_requires_exact_canonical_artifact_bytes(self):
        pre = self.pre()
        self.publish_fixture(pre)
        self.write(self.root/self.core_name, (self.root/self.core_name).read_bytes()+b' ')
        with self.assertRaisesRegex(RuntimeError, 'canonical artifact'):
            self.post()

    def test_post_rejects_legacy_summary_instead_of_inventing_preimages(self):
        self.pre_path = self.stage/'legacy-pre.json'
        self.save(self.pre_path, {'status': 'prepublication_gate_pass', 'before': 0, 'after': 1})
        with self.assertRaisesRegex(RuntimeError, 'complete publication_pre'):
            self.post()

    def test_post_baseline_cannot_add_unrelated_context(self):
        pre = self.pre()
        self.publish_fixture(pre)
        baseline = workflow._publication_json(self.stage/'baseline.json')
        baseline['context'] = None
        self.save(self.stage/'baseline.json', baseline)
        with self.assertRaisesRegex(RuntimeError, 'baseline changed'):
            self.post()

    def test_evidence_only_keeps_existing_early_return_and_never_calls_publication(self):
        output = StringIO()
        evidence = {'mode': 'synthetic_evidence_default_unchanged'}
        with patch.object(sys, 'argv', ['verify_ordered_core.py', str(self.stage), '--evidence-only',
                                        '--repo-root', str(self.root)]), \
             patch.object(workflow, 'verify_acceptance_evidence', return_value=evidence) as verify, \
             patch.object(workflow, 'publication_check') as publication, redirect_stdout(output):
            with self.assertRaises(SystemExit) as stopped:
                workflow.main()
        self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue()), evidence)
        verify.assert_called_once_with(self.stage, self.spec, self.root)
        publication.assert_not_called()

    def test_legacy_verification_tail_is_ast_identical(self):
        current = ast.parse((HERE/'verify_ordered_core.py').read_text(encoding='utf-8-sig'))
        new = next(node for node in current.body if isinstance(node, ast.FunctionDef) and node.name == 'main').body
        index = next(i for i, node in enumerate(new) if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == 'spec' for target in node.targets))
        tail = ast.dump(ast.Module(body=new[index:], type_ignores=[]), include_attributes=False)
        # Pin the original legacy AST without requiring an AF-only support/preimage tree.
        self.assertEqual(sha256(tail.encode()).hexdigest(),
                         'ce6f4f5293fad8289ee24732c9fda49025003008c4eb2ae7da9abbe954873f34')

    def test_publication_cli_requires_explicit_root_and_cannot_mix_legacy_mode(self):
        for options in (['--publication-check', 'pre', '--artifact-manifest', str(self.manifest)],
                        ['--publication-check', 'pre', '--artifact-manifest', str(self.manifest),
                         '--repo-root', str(self.root), '--evidence-only']):
            with self.subTest(options=options), patch.object(sys, 'argv',
                    ['verify_ordered_core.py', str(self.stage), *options]):
                with self.assertRaises(SystemExit) as stopped:
                    workflow.main()
                self.assertEqual(stopped.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
