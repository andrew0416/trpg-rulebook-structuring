"""Small, derived navigation over the existing contracts; never a completion ledger."""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re

PLAN = Path('data/verification/category2-edge-work-plan.json')
CONTRACTS = Path('data/verification/template-reuse-contracts.json')
INDEX = Path('vaults/구현찾기.md')
START = '\n<!-- reuse-navigation:start -->\n'
END = '<!-- reuse-navigation:end -->\n'
START_BOUNDARY = re.compile(r'\r?\n<!-- reuse-navigation:start -->\r?\n')
END_BOUNDARY = re.compile(r'<!-- reuse-navigation:end -->\r?\n')
INDEX_MARKER = '<!-- derived reuse navigation; not implementation evidence -->'
LEGACY_ROUTE_FOOTER = ('같은 경로라도 각 원조항의 고유 조건·예외는 유지한다. '
                       '미완료 엣지를 이 행들에 자동 합류시키거나 완료로 간주하지 않는다.')


def without_links(text):
    """Remove only our bounded block, preserving every byte outside it."""
    starts, ends = list(START_BOUNDARY.finditer(text)), list(END_BOUNDARY.finditer(text))
    if not starts and not ends:
        return text
    if len(starts) != 1 or len(ends) != 1 or ends[0].start() < starts[0].end():
        raise ValueError('Malformed navigation block; preserve the note for inspection.')
    return text[:starts[0].start()] + text[ends[0].end():]


def has_legacy_generated_body(relative, text):
    """Identify the old full-render shape without claiming ownership of custom notes."""
    clean = without_links(text)
    if relative.parent.name == '공통기반':
        return '\n정본 상세: ' in clean
    if relative.parent.name == '재사용':
        return LEGACY_ROUTE_FOOTER in clean
    return False


def inside(root, relative, resolved_root=None):
    path = Path(root) / relative
    if not path.resolve().is_relative_to(resolved_root if resolved_root is not None else Path(root).resolve()):
        raise ValueError(f'Navigation path leaves the project: {relative}')
    return path


def read_note(root, relative, resolved_root=None):
    return inside(root, relative, resolved_root).read_bytes().decode('utf-8')


def load(root):
    """Use explicit ledger relations. Shared foundations yield candidates, not proof."""
    root = Path(root)
    resolved_root = root.resolve()
    plan = json.loads((root / PLAN).read_text(encoding='utf-8-sig'))
    contracts = json.loads((root / CONTRACTS).read_text(encoding='utf-8-sig'))
    foundation = plan['foundation_discovery']
    scopes = {row['id']: row for row in foundation['foundation_execution_plan']['units']}
    drafts = {row['id']: row for row in foundation['foundation_unit_drafts']['units']}
    frozen = {row['id']: row for row in foundation['foundation_freeze']['units']}
    audit = plan['post_foundation_reuse']['itemized_audit']
    clauses_by_route = {}
    for row in audit['items']:
        clauses_by_route.setdefault(row['route'], []).append(row)
    notes = {}

    def add(uid, kind, title, document, contract, native=(), clauses=(), tests=(), checks=(), reference=None):
        if uid in notes:
            raise ValueError(f'Duplicate navigation ID: {uid}')
        if not inside(root, document, resolved_root).is_file():
            raise ValueError(f'Missing implementation note: {document}')
        notes[uid] = dict(id=uid, kind=kind, title=title, document=str(document),
                          contract=contract, native=list(native), clauses=list(clauses), relations=[],
                          tests=list(tests), checks=list(checks), canonical_reference=reference)

    ids = foundation['foundation_freeze']['unit_ids']
    if len(ids) != 57 or len(set(ids)) != 57:
        raise ValueError('Keep the original 57 foundation IDs.')
    for uid in ids:
        scope = scopes[uid]
        contract = {key: scope.get(key) for key in (
            'shared_runtime_work', 'declaration_and_validation_scope', 'dependency_ids')}
        contract.update(outcome=frozen[uid]['observable_outcome'],
                        exceptions=frozen[uid].get('negative_acceptance'))
        add(uid, 'foundation', drafts[uid].get('title', uid), f'vaults/공통기반/{uid}.md',
            contract, scope.get('reuse_and_integration_targets', []),
            checks=foundation['common_foundation_progress']['units'][uid].get('checks', []),
            reference=f'{PLAN.as_posix()}#foundation_discovery.common_foundation_progress.units.{uid}')
    for group in contracts['groups']:
        contract = {key: group.get(key) for key in (
            'reusable_operations', 'conceptual_parameters', 'composition_guidance',
            'output_contract', 'state_owner', 'semantic_boundaries')}
        status = plan['latest_reassessment']['whole_rule_template_audit']['reuse_elements_progress']['groups'][group['id']]
        contract['common_implementation_status'] = status['status']
        contract['common_implementation_scope'] = status.get('reason')
        contract['dependency_records'] = [
            {'id': row['id'], 'state': row.get('state', 'not_recorded'),
             'recorded_requirement': row.get('needed'), 'clauses': row.get('clauses', []),
             'canonical_references': row.get('canonical_dependency_references', [])}
            for row in group.get('pending_dependencies', [])]
        add(group['id'], 'operation', group['title'], group['document'], contract,
            [contracts['native_elements'][key] for key in group['native_elements']],
            tests=group.get('existing_test_discovery', []), checks=status.get('reused_common_checks', []),
            reference=group['implementation_progress_ref'])
    for uid, route in audit['routes'].items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', uid):
            raise ValueError(f'Unsafe route ID: {uid}')
        add(uid, 'route', uid, f'vaults/재사용/{uid}.md',
            {key: route.get(key) for key in ('behavior', 'native_paths', 'required_test_modules')},
            clauses=clauses_by_route.get(uid, []), checks=route.get('evidence', []),
            reference=f'{PLAN.as_posix()}#post_foundation_reuse.itemized_audit.routes.{uid}')

    def relate(source, target, relation, reverse):
        if source not in notes or target not in notes:
            raise ValueError(f'Unknown relation: {source} -> {target}')
        notes[source]['relations'].append({'relation': relation, 'id': target})
        notes[target]['relations'].append({'relation': reverse, 'id': source})

    for uid in ids:
        for dep in scopes[uid].get('dependency_ids', []):
            relate(uid, dep, 'requires', 'required_by')
    for group in contracts['groups']:
        for uid in group['foundation_ids']:
            relate(group['id'], uid, 'uses_foundation', 'operation_using_foundation')
    for name, route in audit['routes'].items():
        for uid in route.get('foundation_ids', []):
            relate(name, uid, 'uses_foundation', 'verified_route_using_foundation')
        for group in contracts['groups']:
            if set(route.get('foundation_ids', [])) & set(group['foundation_ids']):
                relate(group['id'], name, 'shared_foundation_candidate', 'related_operation_candidate')
    for note in notes.values():
        note['relations'].sort(key=lambda row: (row['relation'], row['id']))
    return notes


def visible_lines(text):
    """Keep real source line numbers while excluding our derived backlinks."""
    without_links(text)  # Validate the markers before using line coordinates.
    hidden = False
    for number, value in enumerate(text.splitlines(), 1):
        if value == START.strip():
            hidden = True
        elif value == END.strip():
            hidden = False
        elif not hidden:
            yield number, value


def find(root, notes, query, limit=5, kind=None, _documents=None):
    """All query terms must match; an unknown query never becomes a ready task."""
    terms = query.casefold().split()
    if not terms or not 1 <= limit <= 20 or kind not in (None, 'operation', 'foundation', 'route'):
        raise ValueError('Use a nonempty query, limit 1~20 and a known note kind.')
    query = query.casefold().strip()
    resolved_root = Path(root).resolve()
    results = []
    for note in notes.values():
        if kind is not None and note['kind'] != kind:
            continue
        symbols = [row['symbol'].casefold() for row in note['native']]
        clauses = [row['id'].casefold() for row in note['clauses']]
        title = (note['id'] + ' ' + note['title']).casefold()
        fields = json.dumps(note['contract'], ensure_ascii=False).casefold()
        if _documents is None:
            original = read_note(root, note['document'], resolved_root)
        else:
            original = _documents.get(note['document'])
            if original is None:
                original = _documents[note['document']] = read_note(root, note['document'], resolved_root)
        body = without_links(original)
        searchable = '\n'.join([title, fields, *symbols, *clauses, body.casefold()])
        if not all(term in searchable for term in terms):
            continue
        exact = query in [note['id'].casefold(), *symbols, *clauses]
        score = 1000 * exact + sum(20 * (term in title) + 8 * (term in fields)
                                  + 30 * any(term in symbol for symbol in symbols) for term in terms)
        line = next(((i, value.strip()) for i, value in visible_lines(original)
                     if all(term in value.casefold() for term in terms)), None)
        results.append((score, {'id': note['id'], 'kind': note['kind'], 'title': note['title'],
                               'document': note['document'], 'exact': exact,
                               'show': f'--show {note["id"]}',
                               'match': None if line is None else {'line': line[0], 'text': line[1][:220]}}))
    order = {'operation': 0, 'foundation': 1, 'route': 2}
    results.sort(key=lambda pair: (-pair[0], order[pair[1]['kind']], pair[1]['id']))
    return [row for _, row in results[:limit]]


def current_symbols(root, targets):
    """Resolve current signatures from source, without importing the engine."""
    parsed = {}
    results = []
    for target in targets:
        relative, symbol = target['file'], target['symbol']
        path = inside(root, relative)
        item = {'file': relative, 'symbol': symbol}
        if not path.is_file():
            results.append(dict(item, status='missing_file'))
            continue
        if relative not in parsed:
            raw = path.read_bytes()
            try:
                tree = ast.parse(raw.decode('utf-8-sig'))
            except SyntaxError:
                tree = None
            parsed[relative] = (tree, hashlib.sha256(raw).hexdigest())
        node, sha = parsed[relative]
        if node is None:
            results.append(dict(item, status='invalid_source'))
            continue
        names = symbol.split('.')
        if names[0] == path.stem:
            names = names[1:]
        for name in names:
            found = [child for child in getattr(node, 'body', [])
                     if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                     and child.name == name]
            if len(found) != 1:
                node = None
                break
            node = found[0]
        if node is None:
            results.append(dict(item, status='missing_symbol'))
            continue
        item.update(status='current_source', line=node.lineno, sha256=sha)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            item['signature'] = node.name + '(' + ast.unparse(node.args) + ')'
        if target.get('source_sha256'):
            item['contract_file_hash_matches'] = sha == target['source_sha256']
        results.append(item)
    return results


def resolve(notes, query):
    """Accept exact IDs only; never silently choose among ambiguous symbols."""
    query = query.strip().casefold()
    ids = [uid for uid in notes if uid.casefold() == query]
    if ids:
        return ids[0], 'note'
    matches = [(uid, kind) for uid, note in notes.items()
               for kind, values in [('symbol', [v['symbol'] for v in note['native']]),
                                    ('clause', [v['id'] for v in note['clauses']])]
               if query in [value.casefold() for value in values]]
    if len(matches) != 1:
        options = ', '.join(sorted({uid for uid, _ in matches}))
        raise ValueError(f'Ambiguous exact ID: {options}; use a note ID.' if matches
                         else f'Unknown exact ID: {query}; use --find for text.')
    return matches[0]


def note_sections(root, document):
    text = read_note(root, document)
    lines = list(visible_lines(text))
    starts = [(line, value.lstrip('#').strip(), len(value) - len(value.lstrip('#')))
              for line, value in lines if re.match(r'#{2,6} ', value)]
    return [dict(title=title, line=line, end_line=next(
        (other - 1 for other, _, depth in starts if other > line and depth <= level),
        len(text.splitlines()))) for line, title, level in starts]


def import_bindings(nodes, relative):
    bindings = {}
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            parts = Path(relative).with_suffix('').parts
            base = '.'.join(parts[:-node.level]) if node.level else ''
            base = '.'.join(part for part in (base, node.module) if part)
            for name in node.names:
                bindings[name.asname or name.name] = '.'.join(part for part in (base, name.name) if part)
        elif isinstance(node, ast.Import):
            for name in node.names:
                bindings[name.asname or name.name.split('.')[0]] = name.name if name.asname else name.name.split('.')[0]
    return bindings


def scope_nodes(scope):
    """Do not confuse a nested function's imports/calls with its parent."""
    for child in ast.iter_child_nodes(scope):
        if not isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            yield child
            yield from scope_nodes(child)


def current_calls(root, target, limit, *, _parsed=None):
    """Re-find recorded call expressions only; not a call graph or runtime proof."""
    records = target.get('module_qualified_call_sites', [])
    rows = []
    parsed = {} if _parsed is None else _parsed
    for record in records[:limit]:
        item = {'file': record['file'], 'enclosing': record['enclosing'],
                'recorded_line': record['line'], 'meaning': 'static_recorded_call_not_runtime_trace'}
        if record['file'] not in parsed:
            path = inside(root, record['file'])
            if not path.is_file():
                parsed[record['file']] = 'missing_file'
            else:
                try:
                    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                except SyntaxError:
                    parsed[record['file']] = 'invalid_source'
                else:
                    nodes = list(ast.walk(tree))
                    parsed[record['file']] = (
                        import_bindings(tree.body, record['file']),
                        {child: node for node in nodes for child in ast.iter_child_nodes(node)},
                        [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))],
                        {},  # Local import bindings, keyed by the current AST scope.
                    )
        source = parsed[record['file']]
        if isinstance(source, str):
            rows.append(dict(item, status=source))
            continue
        # Require the recorded expression AND its import binding; line drift is harmless.
        imports, parents, functions, scope_imports = source
        expected = ast.unparse(ast.parse(record['call'], mode='eval').body)
        symbol = target['symbol'].removeprefix(Path(target['file']).stem + '.')
        module = Path(target['file']).with_suffix('')
        # This engine supports both package imports and top-level engine-module imports.
        wanted = {module.as_posix().replace('/', '.') + '.' + symbol, module.stem + '.' + symbol}
        scopes = [node for node in functions if node.name == record['enclosing'].split('.')[-1]]
        found = {}
        for scope in scopes:
            for node in ast.walk(scope):
                if not isinstance(node, ast.Call) or ast.unparse(node) != expected:
                    continue
                ancestors = []
                parent = parents.get(node)
                while parent is not None:
                    if isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        ancestors.append(parent)
                    parent = parents.get(parent)
                ancestors.reverse()
                names = ['.'.join(v.name for v in ancestors[:i + 1]) for i in range(len(ancestors))]
                if not any(name == record['enclosing'] or name.endswith('.' + record['enclosing']) for name in names):
                    continue
                local = dict(imports)
                for ancestor in ancestors:
                    if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if ancestor not in scope_imports:
                            scope_imports[ancestor] = import_bindings(scope_nodes(ancestor), record['file'])
                        local.update(scope_imports[ancestor])
                called = ast.unparse(node.func).split('.')
                binding = '.'.join([local.get(called[0], ''), *called[1:]])
                if binding in wanted:
                    found[node] = '.'.join(v.name for v in ancestors)
        if len(found) == 1:
            node, enclosing = next(iter(found.items()))
            item.update(status='current_recorded_call', line=node.lineno,
                        current_enclosing=enclosing, call=ast.unparse(node))
        else:
            item.update(status='changed_or_missing_recorded_call')
        rows.append(item)
    return rows


def current_tests(root, discoveries, checks, limit):
    """Locate a bounded sample of declared test methods, without running tests."""
    targets = []
    for check in checks:
        for case in check.get('cases', []):
            parts = case.rsplit('.', 2)
            if len(parts) == 3 and parts[0].startswith(('tools.', 'engine.')):
                targets.append(dict(file=parts[0].replace('.', '/') + '.py', symbol='.'.join(parts[1:])))
    for discovery in discoveries:
        for case in discovery.get('tests', []):
            targets.append(dict(file=discovery['file'], symbol=case, source_sha256=discovery.get('sha256')))
    unique = {(row['file'], row['symbol']): row for row in targets}
    return {'meaning': 'Current method locations; discovery and historical runs are separate. Not a test run or automatic suite selection.',
            'recorded_method_count': len(unique), 'shown': current_symbols(root, list(unique.values())[:limit]),
            'discovery_files': [row['file'] for row in discoveries]}


def describe(root, notes, uid, limit=5, section=None):
    if not 1 <= limit <= 20:
        raise ValueError('Use a limit between 1 and 20.')
    requested = uid
    uid, focus = resolve(notes, uid)
    note = notes[uid]
    sections = note_sections(root, note['document'])
    if section is not None:
        selected = [row for row in sections if row['title'] == section]
        if len(selected) != 1:
            raise ValueError('Section must match one exact, unique heading; use --show to list headings.')
        row = selected[0]
        text = read_note(root, note['document']).splitlines()
        return dict(id=uid, document=note['document'], section=row,
                    text='\n'.join(text[row['line'] - 1:row['end_line']]),
                    meaning='Current note excerpt, not new implementation evidence.')
    native = [row for row in note['native'] if focus != 'symbol' or row['symbol'].casefold() == requested.strip().casefold()]
    clauses = [row for row in note['clauses'] if focus != 'clause' or row['id'].casefold() == requested.strip().casefold()]
    checks = note['checks']
    if focus == 'clause':
        basis = clauses[0].get('review_basis')
        checks = [row for row in checks if basis is not None and row.get('record') == basis]
    symbols = current_symbols(root, native)
    call_sources = {}  # Share only this lookup; the next request reads current files again.
    for item, target in zip(symbols, native):
        item['recorded_call_site_count'] = len(target.get('module_qualified_call_sites', []))
        item['call_sites'] = current_calls(root, target, min(limit, 2) if focus != 'symbol' else limit,
                                          _parsed=call_sources)
    relations = note['relations']
    groups = sorted({row['relation'] for row in relations})
    return {
        'id': uid, 'kind': note['kind'], 'title': note['title'], 'document': note['document'],
        'requested': requested, 'focus': focus, 'canonical_reference': note['canonical_reference'],
        'contract': note['contract'], 'native': symbols, 'note_sections': sections,
        'tests': current_tests(root, note['tests'], checks, limit),
        'recorded_checks': checks[:limit], 'recorded_check_count': len(checks),
        'focused_clause': clauses[0] if focus == 'clause' else None,
        'relations': {kind: [dict(row, document=notes[row['id']]['document'])
                            for row in relations if row['relation'] == kind][:limit] for kind in groups},
        'relation_counts': dict(Counter(row['relation'] for row in relations)),
        'clause_ids': [row['id'] for row in clauses],
        'evidence': '기존 장부 근거. current_source와 current_recorded_call은 현재 소스의 정적 확인이며 실행 검증이나 새 조항 완료가 아니다. recorded_checks는 과거 기록이다. shared_foundation_candidate는 같은 기반을 공유하는 후보일 뿐 실제 재사용 인증이 아니다. 공통 구현 상태는 개별 소비자 완료를 뜻하지 않는다. 수기 보완·보류는 note_sections의 해당 절에서 확인한다.',
    }


def md_link(label, target, note):
    relative = os.path.relpath(target, Path(note).parent).replace('\\', '/')
    return f'[{label}](<{relative}>)'


LABELS = {
    'requires': '선행 기반', 'required_by': '이 기반에 의존',
    'uses_foundation': '사용하는 기반', 'operation_using_foundation': '이 기반의 공통 연산',
    'verified_route_using_foundation': '기존 장부에서 이 기반을 재사용한 사례',
    'shared_foundation_candidate': '같은 기반의 사례 후보',
    'related_operation_candidate': '같은 기반의 공통 연산 후보',
}


def render(root, notes=None):
    """Replace bounded links only. Handwritten contracts and deferred notes survive."""
    root = Path(root)
    resolved_root = root.resolve()
    notes = load(root) if notes is None else notes
    docs = {}
    for note in notes.values():
        document = note['document']
        original = read_note(root, document, resolved_root)
        clean = without_links(original)
        if '\n' not in clean:
            raise ValueError(f'Note has no heading boundary: {document}')
        lines = [f'**구현 찾기:** {md_link("동작별 입구", INDEX, document)} · `{note["id"]}`']
        for relation, label in LABELS.items():
            related = [row['id'] for row in note['relations'] if row['relation'] == relation]
            if related:
                links = ' · '.join(md_link(uid, notes[uid]['document'], document) for uid in related[:4])
                rest = '' if len(related) <= 4 else f' · 나머지 {len(related) - 4}개는 `--show {note["id"]}`'
                lines.append(f'- {label}: {links}{rest}')
        lines.append('기반 공유 후보는 실제 재사용 인증이 아니다. 사용 조건·상태 소유·소비·예외는 아래 본문과 실제 소비자에서 확인한다.')
        block = START + '\n'.join(lines) + '\n' + END
        heading, rest = clean.split('\n', 1)
        docs[Path(document)] = heading + '\n' + block + rest

    lines = ['# 공통 구현 찾기', '', INDEX_MARKER, '',
             '동작 → 공통 연산 노트 → 실제 함수와 사용 조건 → 기존 소비자와 직접 검사 순서로 읽는다. 필요한 노트만 열고 연관 링크를 따라간다.', '',
             '## 이름·함수·ID로 바로 찾기', '', '프로젝트 루트에서 실행한다. 검색·상세 조회는 파일을 변경하지 않는다.', '',
             '```powershell', 'python -B -X utf8 tools/build_reuse_vault.py --find "기술 부여"',
             'python -B -X utf8 tools/build_reuse_vault.py --find "state_grants.grant_moves"',
             'python -B -X utf8 tools/build_reuse_vault.py --find "SB-125"',
             'python -B -X utf8 tools/build_reuse_vault.py --find "특성 부여" --kind route',
             'python -B -X utf8 tools/build_reuse_vault.py --show state_grants.grant_moves',
             'python -B -X utf8 tools/build_reuse_vault.py --show SB-125',
             'python -B -X utf8 tools/build_reuse_vault.py --show T19 --section "연막 실제 소비자 보완 (2026-10-16)"', '```', '',
             '`--find`는 모든 검색어를 포함한 노트만 최대5개 반환한다. 정확한 기반 ID·함수·원조항 ID를 우선한다. '
             '`--kind operation|foundation|route`로 공통 연산·원래 기반·소비 사례 중에서 찾고, `--limit 1~20`으로 조회량을 정한다. 관리 표식의 역링크는 검색 근거나 발췌 행으로 사용하지 않는다.', '',
             '`--show`는 노트 ID뿐 아니라 유일한 정확한 함수·원조항 ID를 직접 받는다. 중복이면 선택할 노트 ID를 알려주며 임의로 결정하지 않는다. '
             '함수 조회는 해당 함수만, 원조항 조회는 해당 조항의 검토 근거에 직접 연결된 검사 기록만 좁혀 보여준다.', '',
             '상세 결과에서 현재 함수 위치·인자, 기록된 호출 표현식의 현재 위치, 검사 메서드 위치, 상태 소유·조합·예외와 관련 노트를 확인한다. '
             '변경·삭제된 호출은 과거 행 번호로 현재 연결을 주장하지 않는다. 호출·검사 위치 확인은 정적 조회이며 실행 검사나 전용 검사 묶음 선정이 아니다.', '',
             '긴 수기 보완·보류는 `note_sections`의 제목·행을 확인한 뒤 `--section "정확한 절 제목"`으로 그 절만 읽는다. '
             '하위 절은 함께 포함하며 공통 구현 완료를 개별 소비자 완료로 간주하지 않는다. 더 넓은 경로와 검사 전체가 필요할 때만 기존 노트·정본으로 이동한다.', '',
             '## 동작에서 출발하기', '', '| 동작 | 공통 연산 노트 | 실제 함수 예시 |', '|---|---|---|']
    for note in notes.values():
        if note['kind'] == 'operation':
            example = note['native'][0] if note['native'] else None
            native = md_link(example['symbol'], example['file'], INDEX) if example else '노트 참조'
            lines.append(f'| {note["title"]} | {md_link(note["id"], note["document"], INDEX)} | {native} |')
    lines += ['', '## 연결의 의미', '',
              '- 원래57개 기반 노트: 선행/의존 기반, 해당 공통 연산, 장부에 기록된 실제 재사용 사례로 양방향 연결한다.',
              '- T01~T40 노트: 입력·조합·상태 소유·소비·예외와 현재 함수를 찾는 입구다. 같은 기반의 사례는 비교 후보이며 자동으로 같은 계약이 되지 않는다.',
              '- 재사용 경로 노트: 실제 소비자·관련 검사·연결된 원조항을 확인한다. 과거 검사나 함수 존재만으로 현재 원조항 전체를 완료하지 않는다.',
              '- 검색 결과가 없거나 새 의존성이 보이면 구현 목록에 넣지 않는다. 기존 정본의 선행 기능·대기 소비자·재개 조건으로 돌아간다.', '',
              '## 갱신', '', '`python -B -X utf8 tools/build_reuse_vault.py --navigation`은 기존 노트의 관리 표식 안 연결과 이 입구만 갱신한다. '
              '기존 본문·수기 보완·부분 구현·보류 기록을 보존한다. 관계는 기존 두 정본에서 다시 계산하며 별도 상태 장부를 만들지 않는다.', '',
              f'정본: {md_link("기반·실제 재사용 장부", PLAN, INDEX)} · {md_link("공통 연산 계약", CONTRACTS, INDEX)}. '
              '노트 연결 수·검색 적중은 구현 완료 점수가 아니다. 계수기 종료와 문서 주입 설정을 바꾸지 않는다.']
    docs[INDEX] = '\n'.join(lines) + '\n'
    if (root / INDEX).exists() and INDEX_MARKER not in read_note(root, INDEX, resolved_root):
        raise ValueError('Refusing to replace a handwritten implementation index.')
    return docs


def refresh(root):
    root = Path(root)
    resolved_root = root.resolve()
    before = {name: (root / name).read_bytes() for name in (PLAN, CONTRACTS)}
    docs = render(root)
    changed = 0
    for relative, content in docs.items():
        path = inside(root, relative, resolved_root)
        raw = content.encode('utf-8')
        if not path.exists() or path.read_bytes() != raw:
            path.write_bytes(raw)
            changed += 1
    if any((root / name).read_bytes() != raw for name, raw in before.items()):
        raise RuntimeError('Authority changed while refreshing navigation.')
    return {'documents': len(docs), 'changed': changed, 'implementation_credit': 0}


def preserve_additions(relative, current, generated):
    """Full legacy rebuilds must retain the added navigation and handwritten suffix."""
    clean = without_links(current)
    if clean == current:
        return generated
    if relative.parent.name == '공통기반':
        position = clean.rfind('\n정본 상세: ')
        if position == -1:
            raise ValueError(f'Missing legacy footer; preserve {relative} for inspection.')
        boundary = clean.find('\n', position + 1)
        boundary = len(clean) if boundary == -1 else boundary + 1
    elif relative.parent.name == '재사용':
        position = clean.rfind(LEGACY_ROUTE_FOOTER)
        if position == -1:
            raise ValueError(f'Missing legacy footer; preserve {relative} for inspection.')
        boundary = position + len(LEGACY_ROUTE_FOOTER)
        if clean[boundary:boundary + 2] == '\r\n':
            boundary += 2
        elif clean[boundary:boundary + 1] == '\n':
            boundary += 1
    else:
        raise ValueError(f'Unexpected generated note with navigation: {relative}')
    suffix = clean[boundary:]
    block = current[START_BOUNDARY.search(current).start():END_BOUNDARY.search(current).end()]
    heading, rest = generated.split('\n', 1)
    return heading + '\n' + block + rest + suffix
