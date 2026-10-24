"""Current navigation and exact evidence rendering, without engine completion credit."""
from copy import deepcopy
from pathlib import Path
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_reuse_vault import (MARKER, PLAN, REUSE_INDEX, build, link, plain,
                               refresh_reuse_index, render)
import reuse_navigation as navigation

GRAPPLE = Path('vaults/공통기반/maneuvers.grapple.md')


class VaultNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / PLAN).read_bytes()
        cls.plan = json.loads(cls.raw.decode('utf-8-sig'))

    def test_links_keep_relative_and_absolute_target_semantics(self):
        note = Path('vaults/재사용/example.md')
        expected = '[source](<../../engine/engine.py#Engine>)'
        self.assertEqual(link('source', 'engine/engine.py#Engine', note), expected)
        self.assertEqual(link('source', 'engine\\engine.py#Engine', note), expected)
        self.assertEqual(link('source', str(ROOT / 'engine/engine.py') + '#Engine', note), expected)

    def test_current_grapple_links_resolve_to_actual_symbols_without_mutating_authority(self):
        before = deepcopy(self.plan)
        note = render(self.plan)[GRAPPLE]
        entry = note.split('## 기존 실행 진입점', 1)[1].split('\n## ', 1)[0]
        self.assertIn('`Engine.grapple`', entry)
        self.assertIn('`initiate`', entry)
        self.assertIn('engine/grapple_state.py', entry)
        self.assertNotIn('missing-runtime', entry)
        scope = next(row for row in self.plan['foundation_discovery']['foundation_execution_plan']['units'] if row['id'] == 'maneuvers.grapple')
        for target in scope['reuse_and_integration_targets']:
            self.assertIn('`' + target['symbol'] + '`', entry)
            node = ast.parse((ROOT / target['file']).read_text(encoding='utf-8-sig'))
            for name in target['symbol'].split('.'):
                matches = [child for child in node.body if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == name]
                self.assertEqual(len(matches), 1, target)
                node = matches[0]
        self.assertEqual(before, self.plan)
        self.assertEqual(self.raw, (ROOT / PLAN).read_bytes())

    def test_mixed_missing_and_zero_results_never_gain_an_unrecorded_pass(self):
        plan = deepcopy(self.plan)
        unit = plan['foundation_discovery']['common_foundation_progress']['units']['maneuvers.grapple']
        mixed = next(check for check in unit['checks'] if 'not a full pass' in check.get('result', ''))
        unit['checks'] = [mixed, {'suite': 'missing', 'log': mixed['log']}, {'suite': 'zero', 'passed': 0, 'log': mixed['log']}]
        note = render(plan)[GRAPPLE]
        self.assertIn(mixed['result'], note)
        self.assertNotIn('기록 참조 통과', note)
        missing = next(line for line in note.splitlines() if line.startswith('- `missing`'))
        self.assertIn('결과 미기록', missing)
        self.assertNotIn('통과', missing)
        zero = next(line for line in note.splitlines() if line.startswith('- `zero`'))
        self.assertIn('통과 기록: 0', zero)

    def test_actual_rebuild_is_idempotent_and_preserves_authority_and_handwritten_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / PLAN
            source.parent.mkdir(parents=True)
            source.write_bytes(self.raw)
            manual = {'엔트리포인트.md': 'manual entry\n', 'vaults/작업지시.md': 'manual instructions\n'}
            for relative, value in manual.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding='utf-8')
            first = build(root)
            self.assertEqual(first['documents'], len(render(self.plan)))
            self.assertGreater(first['changed'], 57)
            self.assertEqual(build(root)['changed'], 0)
            self.assertEqual(source.read_bytes(), self.raw)
            self.assertIn('`initiate`', (root / GRAPPLE).read_text(encoding='utf-8'))
            for relative, value in manual.items():
                self.assertEqual((root / relative).read_text(encoding='utf-8'), value)

    def test_unverified_handwritten_route_keeps_full_foundation_link(self):
        route = self.plan['post_foundation_reuse']['itemized_audit']['routes']['tk_mastery']
        foundation = Path(f'vaults/공통기반/{route["foundation_ids"][0]}.md')
        route_note = Path('vaults/재사용/tk_mastery.md')
        index = Path('vaults/재사용/인덱스.md')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manual = root / route_note
            manual.parent.mkdir(parents=True)
            manual.write_text('# tk_mastery\n\n수기 범위는 장부의 전체 동작과 다르다.\n', encoding='utf-8')
            manual_docs = render(self.plan, root=root)
            note = manual_docs[foundation]
            self.assertIn('tk_mastery: ', note)
            self.assertNotIn('tk_mastery — 고유 조건·예외', note)
            manual_row = next(line for line in manual_docs[index].splitlines()
                              if line.startswith('| [tk_mastery]('))
            self.assertIn(plain(route['behavior']), manual_row)
            self.assertIn('수기 범위', manual.read_text(encoding='utf-8'))
            manual.unlink()
            generated_docs = render(self.plan, root=root)
            generated_row = next(line for line in generated_docs[index].splitlines()
                                 if line.startswith('| [tk_mastery]('))
            self.assertIn('[고유 조건·예외](<tk_mastery.md#tk_mastery>)', generated_row)
            self.assertIn(plain(route['behavior']), generated_docs[route_note])

    def test_scoped_index_refresh_preserves_manual_boundaries_and_rejects_unknown_rows(self):
        route = self.plan['post_foundation_reuse']['itemized_audit']['routes']['tk_mastery']
        generated = render(self.plan)[REUSE_INDEX]
        compact = '[고유 조건·예외](<tk_mastery.md#tk_mastery>)'
        self.assertIn(compact, generated)
        old = generated.replace(compact, plain(route['behavior']), 1)
        old = old.replace(MARKER, '수동 구현 템플릿 링크\n\n' + MARKER, 1)
        old += '\n수동 진행 기록\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / PLAN
            source.parent.mkdir(parents=True)
            source.write_bytes(self.raw)
            route_note = root / 'vaults/재사용/tk_mastery.md'
            route_note.parent.mkdir(parents=True)
            route_note.write_text('# tk_mastery\n\n' + plain(route['behavior']) + '\n', encoding='utf-8')
            path = root / REUSE_INDEX
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(old, encoding='utf-8')
            self.assertEqual(refresh_reuse_index(root)['changed'], 1)
            updated = path.read_text(encoding='utf-8')
            self.assertIn('수동 구현 템플릿 링크', updated)
            self.assertTrue(updated.endswith('\n수동 진행 기록\n'))
            self.assertIn(compact, updated)
            self.assertEqual(refresh_reuse_index(root)['changed'], 0)
            self.assertEqual(source.read_bytes(), self.raw)
            self.assertGreater(build(root)['changed'], 0)
            updated = path.read_text(encoding='utf-8')
            self.assertIn('수동 구현 템플릿 링크', updated)
            self.assertTrue(updated.endswith('\n수동 진행 기록\n'))
            self.assertEqual(build(root)['changed'], 0)
            corrupt = updated.replace('| C03-093 |', '| UNKNOWN |', 1)
            path.write_text(corrupt, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'unrecognized reuse index row'):
                refresh_reuse_index(root)
            self.assertEqual(path.read_text(encoding='utf-8'), corrupt)
            corrupt_route = updated.replace('| [tk_mastery](<tk_mastery.md>) |',
                                            '| [unknown](<unknown.md>) |', 1)
            path.write_text(corrupt_route, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'unrecognized reuse route row'):
                refresh_reuse_index(root)
            self.assertEqual(path.read_text(encoding='utf-8'), corrupt_route)

    def test_scoped_index_does_not_shorten_stale_or_missing_route_body(self):
        route = self.plan['post_foundation_reuse']['itemized_audit']['routes']['tk_mastery']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            missing = render(self.plan, root=root, update_routes=False)[REUSE_INDEX]
            row = next(line for line in missing.splitlines() if line.startswith('| [tk_mastery]('))
            self.assertIn(plain(route['behavior']), row)
            self.assertNotIn('[고유 조건·예외]', row)
            note = root / 'vaults/재사용/tk_mastery.md'
            note.parent.mkdir(parents=True)
            note.write_text('# tk_mastery\n\n낡은 범위\n', encoding='utf-8')
            stale = render(self.plan, root=root, update_routes=False)[REUSE_INDEX]
            row = next(line for line in stale.splitlines() if line.startswith('| [tk_mastery]('))
            self.assertIn(plain(route['behavior']), row)

    def test_index_only_matches_full_render_without_generating_other_notes(self):
        for update_routes in (False, True):
            with self.subTest(update_routes=update_routes):
                scoped = render(self.plan, update_routes=update_routes, index_only=True)
                self.assertEqual(list(scoped), [REUSE_INDEX])
                self.assertEqual(scoped[REUSE_INDEX],
                                 render(self.plan, update_routes=update_routes)[REUSE_INDEX])


class ZettelkastenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notes = navigation.load(ROOT)
        cls.sources = {relative: (ROOT / relative).read_bytes()
                       for relative in (navigation.PLAN, navigation.CONTRACTS)}

    def copy_fixture(self, root):
        for relative, raw in self.sources.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        for note in self.notes.values():
            relative = Path(note['document'])
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / relative).read_bytes())

    def test_behavior_symbol_foundation_and_clause_find_the_existing_contract(self):
        for query, expected in [
            ('기술 부여', 'T10'), ('state_grants.grant_moves', 'T10'),
            ('learning.grant', 'learning.grant'), ('SB-125', 'named_static_gift_grants'),
        ]:
            with self.subTest(query=query):
                result = navigation.find(ROOT, self.notes, query)
                self.assertEqual(result[0]['id'], expected)
                self.assertTrue((ROOT / result[0]['document']).is_file())
        self.assertTrue({'T19', 'T27', 'csv_smoke_regions_completion'} <=
                        {row['id'] for row in navigation.find(ROOT, self.notes, '연막')})
        self.assertEqual(navigation.find(ROOT, self.notes, 'zzzz-no-native-implementation'), [])
        with self.assertRaises(ValueError):
            navigation.find(ROOT, self.notes, ' ')
        with self.assertRaises(ValueError):
            navigation.find(ROOT, self.notes, '기술', 21)
        for relative, raw in self.sources.items():
            self.assertEqual((ROOT / relative).read_bytes(), raw)

    def test_real_backlinks_distinguish_ledger_reuse_from_shared_foundation_candidates(self):
        foundation = self.notes['learning.grant']['relations']
        self.assertIn({'relation': 'operation_using_foundation', 'id': 'T10'}, foundation)
        self.assertIn({'relation': 'verified_route_using_foundation', 'id': 'named_static_gift_grants'}, foundation)
        template = self.notes['T10']['relations']
        self.assertIn({'relation': 'uses_foundation', 'id': 'learning.grant'}, template)
        self.assertIn({'relation': 'shared_foundation_candidate', 'id': 'named_static_gift_grants'}, template)
        self.assertNotIn({'relation': 'verified_route_using_foundation', 'id': 'named_static_gift_grants'}, template)
        for note in self.notes.values():
            for relation in note['relations']:
                self.assertIn(relation['id'], self.notes)
                self.assertTrue(any(row['id'] == note['id'] for row in self.notes[relation['id']]['relations']))

    def test_route_clauses_keep_the_ledger_order(self):
        plan = json.loads(self.sources[navigation.PLAN].decode('utf-8-sig'))
        audit = plan['post_foundation_reuse']['itemized_audit']
        for uid in audit['routes']:
            self.assertEqual(self.notes[uid]['clauses'],
                             [row for row in audit['items'] if row['route'] == uid])

    def test_details_use_current_signatures_and_report_missing_symbols_without_stale_fallback(self):
        detail = navigation.describe(ROOT, self.notes, 'T10')
        self.assertEqual(detail['contract']['common_implementation_status'], 'complete')
        self.assertNotIn('pending_dependencies', detail['contract'])
        grant = next(row for row in detail['native'] if row['symbol'] == 'state_grants.grant_moves')
        self.assertEqual(grant['status'], 'current_source')
        self.assertIn('source_id', grant['signature'])
        self.assertEqual((ROOT / grant['file']).read_text(encoding='utf-8').splitlines()[grant['line'] - 1].split('(')[0].strip(), 'def grant_moves')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'engine').mkdir()
            (root / 'engine/sample.py').write_text('\n\ndef grant(actor, *, current_source):\n    return actor\n', encoding='utf-8')
            targets = [dict(file='engine/sample.py', symbol='sample.grant', signature='old_signature()', source_sha256='old'),
                       dict(file='engine/sample.py', symbol='sample.removed', signature='removed(old)')]
            rows = navigation.current_symbols(root, targets)
            self.assertEqual(rows[0]['line'], 3)
            self.assertEqual(rows[0]['signature'], 'grant(actor, *, current_source)')
            self.assertFalse(rows[0]['contract_file_hash_matches'])
            self.assertEqual(rows[1]['status'], 'missing_symbol')
            self.assertNotIn('signature', rows[1])

    def test_link_refresh_preserves_all_note_bodies_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_fixture(root)
            pending = root / self.notes['T19']['document']
            with pending.open('a', encoding='utf-8') as stream:
                stream.write('\n사용자가 보완한 미완료: 빈 영역 활성화는 보류한다.\n')
            bodies = {uid: navigation.without_links(navigation.read_note(root, note['document']))
                      for uid, note in self.notes.items()}
            manual = root / '엔트리포인트.md'
            manual.write_text('계수기 종료. 문서 주입 유지.\n', encoding='utf-8')
            first = navigation.refresh(root)
            self.assertEqual(first['implementation_credit'], 0)
            self.assertEqual(first['documents'], len(self.notes) + 1)
            self.assertEqual(navigation.refresh(root)['changed'], 0)
            for uid, note in self.notes.items():
                self.assertEqual(navigation.without_links(navigation.read_note(root, note['document'])), bodies[uid], uid)
            self.assertEqual(manual.read_text(encoding='utf-8'), '계수기 종료. 문서 주입 유지.\n')
            for relative, raw in self.sources.items():
                self.assertEqual((root / relative).read_bytes(), raw)

    def test_legacy_full_rebuild_keeps_links_and_handwritten_deferred_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_fixture(root)
            navigation.refresh(root)
            manual_route = Path(self.notes['core_native_self_range']['document'])
            manual_body = navigation.without_links(navigation.read_note(root, manual_route))
            suffix = '\n## 수기 보완\n다른 계약의 선행 기능은 보류한다.\n'
            targets = [GRAPPLE, Path(self.notes['named_static_gift_grants']['document'])]
            written_suffixes = {}
            for relative in targets:
                previous = navigation.read_note(root, relative)
                with (root / relative).open('a', encoding='utf-8') as stream:
                    stream.write(suffix)
                written_suffixes[relative] = navigation.read_note(root, relative)[len(previous):]
            first = build(root)
            self.assertIn(manual_route.as_posix(), first['preserved_route_bodies'])
            self.assertEqual(navigation.without_links(navigation.read_note(root, manual_route)), manual_body)
            for relative in targets:
                text = navigation.read_note(root, relative)
                self.assertTrue(text.endswith(written_suffixes[relative]), relative)
                self.assertEqual(text.count(navigation.START), 1)
            second = build(root)
            self.assertEqual(second['changed'], 0)
            self.assertEqual(second['navigation']['changed'], 0)

    def test_legacy_full_rebuild_preserves_direct_manual_and_compatibility_route_bodies(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_fixture(root)
            routes = [Path(self.notes[uid]['document'])
                      for uid in ('core_native_self_range', 'core_feature_ability_choices')]
            bodies = {relative: navigation.without_links(navigation.read_note(root, relative))
                      for relative in routes}
            result = build(root)
            self.assertTrue({relative.as_posix() for relative in routes}
                            <= set(result['preserved_route_bodies']))
            for relative, body in bodies.items():
                current = navigation.read_note(root, relative)
                self.assertEqual(navigation.without_links(current), body)
                self.assertEqual(current.count(navigation.START), 1)

    def test_legacy_full_rebuild_rejects_malformed_handwritten_route_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_fixture(root)
            manual_route = Path(self.notes['core_native_self_range']['document'])
            (root / manual_route).write_text('제목 경계가 없는 수기 문서', encoding='utf-8')
            generated = root / GRAPPLE
            before = generated.read_bytes()
            with self.assertRaisesRegex(ValueError, 'handwritten route.*heading boundary'):
                build(root)
            self.assertEqual(generated.read_bytes(), before)

    def test_rendered_links_resolve_and_invalid_boundaries_fail_before_writes(self):
        docs = navigation.render(ROOT, self.notes)
        import re
        for relative, text in docs.items():
            block = text if relative == navigation.INDEX else text.split(navigation.START, 1)[1].split(navigation.END, 1)[0]
            for target in re.findall(r'\]\(<([^>]+)>\)', block):
                destination = (ROOT / relative.parent / target).resolve()
                self.assertTrue(destination.is_relative_to(ROOT))
                self.assertTrue(destination.is_file() or destination == ROOT / navigation.INDEX, target)
        with self.assertRaises(ValueError):
            navigation.without_links('broken' + navigation.START)
        with self.assertRaises(ValueError):
            navigation.inside(ROOT, '../outside.md')
        with self.assertRaises(ValueError):
            navigation.inside(ROOT, '../outside.md', ROOT.resolve())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.copy_fixture(root)
            index = root / navigation.INDEX
            index.write_text('수기 문서이므로 덮어쓰지 않는다.\n', encoding='utf-8')
            original = (root / GRAPPLE).read_bytes()
            with self.assertRaisesRegex(ValueError, 'handwritten'):
                navigation.refresh(root)
            self.assertEqual((root / GRAPPLE).read_bytes(), original)

    def test_actual_cli_is_read_only_and_search_lines_point_to_current_notes(self):
        protected = [navigation.PLAN, navigation.CONTRACTS,
                     Path('data/verification/category2-work-checkpoint.json'),
                     Path('data/verification/category2-progress.json')]
        before = {relative: (ROOT / relative).read_bytes() for relative in protected}
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/build_reuse_vault.py'),
                                 '--find', 'SB-125'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads(result.stdout)[0]
        self.assertEqual(row['id'], 'named_static_gift_grants')
        self.assertTrue(row['exact'])
        line = navigation.read_note(ROOT, row['document']).splitlines()[row['match']['line'] - 1].strip()
        self.assertEqual(row['match']['text'], line[:220])
        self.assertTrue(all((ROOT / relative).read_bytes() == raw for relative, raw in before.items()))

    def test_repeated_find_matches_individual_queries_with_one_document_read(self):
        queries = ('기술 부여', '연막', 'SB-125')
        documents = {}
        with patch.object(navigation, 'read_note', wraps=navigation.read_note) as read:
            expected = [navigation.find(ROOT, self.notes, query, 3, _documents=documents)
                        for query in queries]
        self.assertEqual(read.call_count, len({note['document'] for note in self.notes.values()}))
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/build_reuse_vault.py'),
                                 '--find', queries[0], '--find', queries[1], '--find', queries[2], '--limit', '3'],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         [{'query': query, 'results': rows} for query, rows in zip(queries, expected)])

    def test_exact_symbol_and_clause_lookup_keep_scope_and_do_not_guess_ambiguous_owners(self):
        symbol = navigation.describe(ROOT, self.notes, 'state_grants.grant_moves', 2)
        self.assertEqual(symbol['focus'], 'symbol')
        self.assertEqual([row['symbol'] for row in symbol['native']], ['state_grants.grant_moves'])
        self.assertEqual(len(symbol['native'][0]['call_sites']), 2)
        self.assertTrue(all(row['status'] == 'current_recorded_call' for row in symbol['native'][0]['call_sites']))
        self.assertEqual(symbol['native'][0]['call_sites'][1]['current_enclosing'], 'register_all.apply')
        clause = navigation.describe(ROOT, self.notes, 'sb-125')
        self.assertEqual(clause['focus'], 'clause')
        self.assertEqual(clause['clause_ids'], ['SB-125'])
        self.assertEqual(clause['recorded_check_count'], 1)
        self.assertEqual(clause['recorded_checks'][0]['record'], clause['focused_clause']['review_basis'])
        self.assertEqual(clause['tests']['recorded_method_count'], 2)
        self.assertTrue(all('psystrike' in row['symbol'] for row in clause['tests']['shown']))
        self.assertTrue(all(row['status'] == 'current_source' for row in clause['tests']['shown']))
        ambiguous = deepcopy(self.notes)
        ambiguous['T09']['native'].append(ambiguous['T10']['native'][-1])
        with self.assertRaisesRegex(ValueError, 'Ambiguous.*T09, T10'):
            navigation.describe(ROOT, ambiguous, 'state_grants.grant_moves')
        with self.assertRaisesRegex(ValueError, 'Unknown exact ID'):
            navigation.describe(ROOT, self.notes, '기술 부여')
        without_own_evidence = deepcopy(self.notes)
        without_own_evidence['named_static_gift_grants']['checks'] = []
        self.assertEqual(navigation.describe(ROOT, without_own_evidence, 'SB-125')['recorded_checks'], [])

    def test_kind_filter_and_managed_links_do_not_supply_a_search_excerpt(self):
        rows = navigation.find(ROOT, self.notes, '특성 부여', kind='route')
        self.assertTrue(rows)
        self.assertTrue(all(row['kind'] == 'route' for row in rows))
        self.assertIn('named_static_gift_grants',
                      [row['id'] for row in navigation.find(ROOT, self.notes, '특성 부여', 20, 'route')])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            note = deepcopy(self.notes['T10'])
            path = root / note['document']
            path.parent.mkdir(parents=True)
            path.write_bytes(('# T10\n' + navigation.START + '특성 부여 hidden-only\n' + navigation.END
                              + '\n## 실제 내용\n특성 부여 native.\n').encode('utf-8'))
            row = navigation.find(root, {'T10': note}, '특성 부여')[0]
            self.assertEqual(row['match']['text'], '특성 부여 native.')
            self.assertEqual(path.read_text(encoding='utf-8').splitlines()[row['match']['line'] - 1], '특성 부여 native.')
            self.assertEqual(navigation.find(root, {'T10': note}, 'hidden-only'), [])
        with self.assertRaises(ValueError):
            navigation.find(ROOT, self.notes, '기술', kind='invented')

    def test_current_recorded_call_follows_line_drift_but_not_changed_import_or_removed_call(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'engine/caller.py'
            path.parent.mkdir()
            target = dict(file='engine/shared.py', symbol='shared.grant', module_qualified_call_sites=[
                dict(file='engine/caller.py', enclosing='apply', line=3, call='G.grant(actor)')])
            sources = [
                ('\n\ndef apply(actor):\n    from . import shared as G\n    G.grant(actor)\n', 'current_recorded_call', 5),
                ('import shared as G\n\ndef apply(actor):\n    def nested():\n        import wrong as G\n    G.grant(actor)\n', 'current_recorded_call', 6),
                ('import wrong as G\n\ndef apply(actor):\n    G.grant(actor)\n', 'changed_or_missing_recorded_call', None),
                ('import shared as G\n\ndef apply(actor):\n    G.grant(other)\n', 'changed_or_missing_recorded_call', None),
                ('import shared as G\n\ndef apply(actor):\n    return actor\n', 'changed_or_missing_recorded_call', None),
                ('def broken(\n', 'invalid_source', None),
            ]
            for source, status, line in sources:
                with self.subTest(status=status, source=source):
                    path.write_text(source, encoding='utf-8')
                    row = navigation.current_calls(root, target, 1)[0]
                    self.assertEqual(row['status'], status)
                    self.assertEqual(row.get('line'), line)
                    if status != 'current_recorded_call':
                        self.assertNotIn('call', row)
            target['module_qualified_call_sites'][0]['file'] = 'engine/missing.py'
            self.assertEqual(navigation.current_calls(root, target, 1)[0]['status'], 'missing_file')

    def test_recorded_calls_share_one_file_read_but_refresh_on_next_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'engine/caller.py'
            path.parent.mkdir()
            path.write_text('import shared as G\n\ndef apply(actor):\n    G.grant(actor)\n', encoding='utf-8')
            target = dict(file='engine/shared.py', symbol='shared.grant', module_qualified_call_sites=[
                dict(file='engine/caller.py', enclosing='apply', line=1, call='G.grant(actor)'),
                dict(file='engine/caller.py', enclosing='apply', line=2, call='G.grant(other)'),
            ])
            original = Path.read_text
            reads = []

            def recorded(file, *args, **kwargs):
                if file == path:
                    reads.append(file)
                return original(file, *args, **kwargs)

            with patch.object(Path, 'read_text', recorded):
                rows = navigation.current_calls(root, target, 2)
            self.assertEqual(len(reads), 1)
            self.assertEqual([row['status'] for row in rows],
                             ['current_recorded_call', 'changed_or_missing_recorded_call'])
            path.write_text('import wrong as G\n\ndef apply(actor):\n    G.grant(actor)\n', encoding='utf-8')
            self.assertEqual(navigation.current_calls(root, target, 2)[0]['status'],
                             'changed_or_missing_recorded_call')

    def test_describe_shares_call_sources_and_import_scopes_only_within_one_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'engine/caller.py'
            path.parent.mkdir()
            (root / 'engine/shared.py').write_text(
                'def grant(actor): pass\ndef revoke(actor): pass\n', encoding='utf-8')
            (root / 'note.md').write_text('# fixture\n', encoding='utf-8')
            native = [dict(file='engine/shared.py', symbol='shared.' + name,
                           module_qualified_call_sites=[dict(file='engine/caller.py',
                               enclosing='apply', line=1, call='G.' + name + '(actor)')])
                      for name in ('grant', 'revoke')]
            note = dict(id='fixture', kind='operation', title='fixture', document='note.md',
                        contract={}, native=native, clauses=[], tests=[], checks=[], relations=[],
                        canonical_reference=None)
            notes = {'fixture': note}
            body = '\n\ndef apply(actor):\n    G.grant(actor)\n    G.revoke(actor)\n'
            local_body = '\n    G.grant(actor)\n    G.revoke(actor)\n'
            original = Path.read_text
            for source, expected in (
                ('import shared as G' + body, 'current_recorded_call'),
                ('import wrong as G' + body, 'changed_or_missing_recorded_call'),
                ('def apply(actor):\n    from . import shared as G' + local_body, 'current_recorded_call'),
                ('def apply(actor):\n    from . import wrong as G' + local_body, 'changed_or_missing_recorded_call'),
                ('def broken(\n', 'invalid_source'),
                (None, 'missing_file'),
                ('import shared as G' + body, 'current_recorded_call'),
            ):
                with self.subTest(expected=expected):
                    if source is None:
                        path.unlink()
                    else:
                        path.write_text(source, encoding='utf-8')
                    reads = []

                    def recorded(file, *args, **kwargs):
                        if file == path:
                            reads.append(file)
                        return original(file, *args, **kwargs)

                    with patch.object(Path, 'read_text', recorded), \
                         patch.object(navigation.ast, 'parse', wraps=ast.parse) as parsed, \
                         patch.object(navigation, 'import_bindings', wraps=navigation.import_bindings) as bindings:
                        result = navigation.describe(root, notes, 'fixture')
                    self.assertEqual([row['call_sites'][0]['status'] for row in result['native']],
                                     [expected, expected])
                    self.assertEqual(len(reads), 0 if source is None else 1)
                    if source is not None:
                        self.assertEqual(sum(call.args[0] == source for call in parsed.call_args_list), 1)
                    if expected in ('current_recorded_call', 'changed_or_missing_recorded_call'):
                        self.assertEqual(bindings.call_count, 2, 'module imports and one shared function scope')

    def test_test_locations_are_bounded_and_missing_methods_never_gain_current_or_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'tools/test_shared.py'
            path.parent.mkdir()
            path.write_text('class Checks:\n    def test_actual(self):\n        pass\n', encoding='utf-8')
            discovery = [dict(file='tools/test_shared.py', sha256='old', tests=['Checks.test_actual', 'Checks.test_removed'])]
            shown = navigation.current_tests(root, discovery, [], 1)
            self.assertEqual(shown['recorded_method_count'], 2)
            self.assertEqual(len(shown['shown']), 1)
            self.assertEqual(shown['shown'][0]['line'], 2)
            self.assertFalse(shown['shown'][0]['contract_file_hash_matches'])
            missing = navigation.current_tests(root, discovery, [], 2)['shown'][1]
            self.assertEqual(missing['status'], 'missing_symbol')
            self.assertNotIn('line', missing)
            self.assertNotIn('signature', missing)
            self.assertNotIn('passed', shown)
            path.write_text('class Checks(\n', encoding='utf-8')
            self.assertEqual(navigation.current_tests(root, discovery, [], 1)['shown'][0]['status'], 'invalid_source')

    def test_exact_section_reads_current_manual_deferred_content_with_subsections(self):
        title = '연막 실제 소비자 보완 (2026-10-16)'
        detail = navigation.describe(ROOT, self.notes, 'T19', section=title)
        self.assertIn('native_empty_area_field_activation', detail['text'])
        self.assertIn('연막 원조항은 미완료', detail['text'])
        self.assertIn('### 지도 없는 연막의 개체 정체성 교정', detail['text'])
        original = navigation.read_note(ROOT, detail['document']).splitlines()
        row = detail['section']
        self.assertEqual(detail['text'], '\n'.join(original[row['line'] - 1:row['end_line']]))
        self.assertNotIn('native', detail)
        common = navigation.describe(ROOT, self.notes, 'T19', 1)
        self.assertEqual(common['contract']['common_implementation_status'], 'complete')
        self.assertIn(title, [row['title'] for row in common['note_sections']])
        self.assertTrue(common['contract']['dependency_records'][0]['canonical_references'][0]['resume_when'])
        with self.assertRaisesRegex(ValueError, 'exact, unique'):
            navigation.describe(ROOT, self.notes, 'T19', section='연막')

    def test_cli_scoped_reads_are_read_only_and_invalid_modifiers_never_trigger_build(self):
        protected = {relative: (ROOT / relative).read_bytes() for relative in (
            navigation.PLAN, navigation.CONTRACTS, navigation.INDEX,
            Path('data/verification/category2-work-checkpoint.json'), Path('data/verification/category2-progress.json'))}
        examples = [
            (['--show', 'SB-125', '--limit', '2'], lambda value: self.assertEqual(value['tests']['recorded_method_count'], 2)),
            (['--show', 'state_grants.grant_moves', '--limit', '1'], lambda value: self.assertEqual(len(value['native']), 1)),
            (['--find', '특성 부여', '--kind', 'route'], lambda value: self.assertTrue(all(row['kind'] == 'route' for row in value))),
            (['--show', 'T19', '--section', '연막 실제 소비자 보완 (2026-10-16)'], lambda value: self.assertIn('보류', value['text'])),
        ]
        for arguments, verify in examples:
            result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/build_reuse_vault.py'), *arguments],
                                    cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            verify(json.loads(result.stdout))
        for arguments in (['--kind', 'route'], ['--section', 'anything'], ['--find', '연막', '--section', 'anything']):
            result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/build_reuse_vault.py'), *arguments],
                                    cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(all((ROOT / relative).read_bytes() == raw for relative, raw in protected.items()))


class VaultPreservationTests(unittest.TestCase):
    """Scoped document preservation; no engine imports or full-vault builds."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.root = Path(temporary.name)
        self.assertTrue(self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(temporary.cleanup)
        for relative in (navigation.PLAN, navigation.CONTRACTS):
            self.write(relative, '{}\n')

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode('utf-8'))

    def note(self, kind='operation'):
        return dict(id='sample', kind=kind, title='한글 동작',
                    document='vaults/재사용/sample.md', relations=[], native=[])

    def test_actual_martial_suffix_survives_without_navigation(self):
        from build_reuse_vault import render_route
        relative = Path('vaults/재사용/book_martial_artist_full.md')
        current = navigation.without_links((ROOT / relative).read_bytes().decode('utf-8'))
        current = current.replace('\r\n', '\n')
        suffix = current[current.index('\n## 가속 연타의 획득 상한과 보유 수명'):]
        generated = render_route(relative.stem, {'behavior': '갱신한 생성 본문'}, [], [])
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                original = current.replace('\n', newline)
                result = navigation.preserve_additions(relative, original, generated)
                self.assertTrue(result.endswith(suffix.replace('\n', newline)))
                self.assertIn('갱신한 생성 본문', result)
                self.assertEqual(result, navigation.preserve_additions(relative, result, generated))
                self.assertNotIn('\r', result.replace('\r\n', ''))
                if newline == '\r\n':
                    self.assertNotIn('\n', result.replace('\r\n', ''))

    def test_existing_navigation_and_foundation_footer_remain_intact(self):
        block = navigation.START + '기존 연결\n' + navigation.END
        for relative, footer in (
            (Path('vaults/재사용/example.md'), navigation.LEGACY_ROUTE_FOOTER),
            (GRAPPLE, '정본 상세: [기록](../../data/verification/category2-edge-work-plan.json)'),
        ):
            for newline in ('\n', '\r\n'):
                with self.subTest(relative=str(relative), newline=repr(newline)):
                    generated = '# example\n\n새 본문\n\n' + footer + '\n'
                    suffix = '\n## 고유 한계\n한글·출처 보존 — 끝 줄바꿈 없음'
                    current = ('# example\n' + block + '\n옛 본문\n\n' + footer + '\n' + suffix).replace('\n', newline)
                    result = navigation.preserve_additions(relative, current, generated)
                    self.assertEqual(navigation.without_links(result), (generated + suffix).replace('\n', newline))
                    self.assertEqual(result.count(navigation.START.strip()), 1)
                    self.assertEqual(result, navigation.preserve_additions(relative, result, generated))
        relative = Path('vaults/공통기반/인덱스.md')
        self.assertEqual(navigation.preserve_additions(relative, '# index\n', '# updated\n'), '# updated\n')

    def test_legacy_missing_duplicate_and_mixed_boundaries_are_refused(self):
        relative = Path('vaults/재사용/example.md')
        generated = '# example\n\n' + navigation.LEGACY_ROUTE_FOOTER + '\n'
        invalid = [
            '# example\n수기 본문만 존재\n',
            generated + navigation.LEGACY_ROUTE_FOOTER + '\n',
            generated + navigation.START,
            generated + navigation.START + navigation.END + navigation.START + navigation.END,
            generated.replace('\n', '\r\n', 1),
        ]
        for current in invalid:
            with self.subTest(current=current[-100:]):
                with self.assertRaises(ValueError):
                    navigation.preserve_additions(relative, current, generated)
        with self.assertRaises(ValueError):
            navigation.preserve_additions(relative, generated, generated + navigation.LEGACY_ROUTE_FOOTER + '\n')

    def test_actual_index_keeps_preface_interior_and_tail_when_table_grows(self):
        current = (ROOT / navigation.INDEX).read_bytes().decode('utf-8')
        contracts = json.loads((ROOT / navigation.CONTRACTS).read_text(encoding='utf-8-sig'))
        notes = {row['id']: dict(id=row['id'], kind='operation', title=row['title'],
                 document=row['document'], relations=[],
                 native=[contracts['native_elements'][key] for key in row['native_elements']])
                 for row in contracts['groups']}
        self.write(navigation.INDEX, current)
        read_note = navigation.read_note
        def read(root, relative, resolved_root=None):
            if Path(relative) == navigation.INDEX:
                return read_note(root, relative, resolved_root)
            return '# 범위 한정 연산 표 fixture\n'
        with patch.object(navigation, 'read_note', side_effect=read):
            self.assertEqual(navigation.render(self.root, notes)[navigation.INDEX], current)
            notes['fixture-extra'] = dict(id='fixture-extra', kind='operation', title='추가 한글 행',
                document='vaults/재사용/fixture-extra.md', relations=[], native=[])
            result = navigation.render(self.root, notes)[navigation.INDEX]
            newline = '\r\n' if '\r\n' in current else '\n'
            extra = '| 추가 한글 행 | [fixture-extra](<재사용/fixture-extra.md>) | 노트 참조 |' + newline
            self.assertEqual(result.replace(extra, ''), current)
            self.assertIn('## 스루 검사에서 추가한 공유 계약', result)
            self.write(navigation.INDEX, result)
            self.assertEqual(navigation.render(self.root, notes)[navigation.INDEX], result)

    def test_scoped_refresh_is_idempotent_with_unicode_and_line_endings(self):
        note = self.note()
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                (self.root / navigation.INDEX).unlink(missing_ok=True)
                self.write(note['document'], '# 한글 노트' + newline + newline + '수기 계약 — 보존' + newline)
                with patch.object(navigation, 'load', return_value={'sample': note}):
                    navigation.refresh(self.root)
                    index = (self.root / navigation.INDEX).read_bytes().decode('utf-8').replace('\r\n', '\n')
                    index = index.replace(navigation.INDEX_MARKER, '> 수기 서문\n\n' + navigation.INDEX_MARKER)
                    index = index.replace('## 이름·함수·ID로 바로 찾기', '## 수기 중간 절\n한글 조건\n\n## 이름·함수·ID로 바로 찾기')
                    index = ('\ufeff' + index + '\n수기 꼬리 — 끝 줄바꿈 없음').replace('\n', newline)
                    self.write(navigation.INDEX, index)
                    before = {Path(note['document']): (self.root / note['document']).read_bytes(),
                              navigation.INDEX: (self.root / navigation.INDEX).read_bytes()}
                    self.assertEqual(navigation.refresh(self.root)['changed'], 0)
                    self.assertEqual(navigation.refresh(self.root)['changed'], 0)
                    for relative, raw in before.items():
                        self.assertEqual((self.root / relative).read_bytes(), raw)
                        if newline == '\r\n':
                            self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))

    def test_index_ambiguous_boundaries_and_unknown_rows_refuse_before_writes(self):
        index = navigation.render(self.root, {})[navigation.INDEX]
        footer = index.splitlines()[-1]
        table = '| 동작 | 공통 연산 노트 | 실제 함수 예시 |\n|---|---|---|\n'
        invalid = [
            index.replace(navigation.INDEX_MARKER, ''),
            index + navigation.INDEX_MARKER + '\n',
            index.replace(footer, '없어진 정본 footer'),
            index + footer + '\n',
            index + '\n## 동작에서 출발하기\n\n' + table,
            index.replace('## 연결의 의미', '## 연결의 의미\n\n## 연결의 의미'),
            index.replace(table, table + '| 수기 추가 | 출처 미확인 | 지우면 안 됨 |\n'),
            index.replace(table, table + '| 한글 동작 | [sample](<재사용/sample.md>) | 노트 참조 |\n' * 2),
            index.replace('\n', '\r\n', 1),
        ]
        note = self.note()
        self.write(note['document'], '# 원본\n수기 내용\n')
        note_before = (self.root / note['document']).read_bytes()
        with patch.object(navigation, 'load', return_value={'sample': note}):
            for current in invalid:
                with self.subTest(current=current[-100:]):
                    self.write(navigation.INDEX, current)
                    with self.assertRaises(ValueError):
                        navigation.refresh(self.root)
                    self.assertEqual((self.root / navigation.INDEX).read_bytes(), current.encode('utf-8'))
                    self.assertEqual((self.root / note['document']).read_bytes(), note_before)

    def test_single_route_generation_navigation_roundtrip_preserves_actual_suffix(self):
        from build_reuse_vault import render_route
        relative = Path('vaults/재사용/book_martial_artist_full.md')
        original = (ROOT / relative).read_bytes().decode('utf-8').replace('\r\n', '\n')
        generated = render_route(relative.stem, {'behavior': '현재 생성 본문'}, [], [])
        note = dict(id=relative.stem, kind='route', title=relative.stem,
                    document=relative.as_posix(), relations=[], native=[])
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                body = navigation.preserve_additions(relative, original.replace('\n', newline), generated)
                self.write(relative, body)
                with patch.object(navigation, 'load', return_value={note['id']: note}):
                    navigation.refresh(self.root)
                    before = (self.root / relative).read_bytes().decode('utf-8')
                    self.assertEqual(navigation.preserve_additions(relative, before, generated), before)
                    self.assertEqual(navigation.refresh(self.root)['changed'], 0)
                    self.assertIn('## 가속 연타의 획득 상한과 보유 수명', before)


if __name__ == '__main__':
    unittest.main()
