"""Mechanical integrity of draft authority clauses, never semantic certification."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = 'data/verification/root-authority-atoms.json'
REVIEWS = 'data/verification/common-source-reviews'
GRAPH = 'data/verification/rule-symbol-graph.json'
TARGETS = {'source.authority', 'rules.applicability', 'rules.precedence'}
DISPOSITIONS = {'indexed_pending_atomic_review', 'partially_atomized_draft', 'excluded_from_root_scope'}
MODALITIES = {'normative', 'source_note', 'guidance'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value, allow_empty=True):
    return isinstance(value, list) and (allow_empty or bool(value)) and all(nonempty(x) for x in value)


def safe_path(root, relative):
    if not nonempty(relative):
        return None
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        return None
    path = (root / path).resolve()
    return path if path.is_relative_to(root.resolve()) and path.is_file() else None


def source_inventory(root):
    """Read the live review union instead of hard-coding the current 578 count."""
    expected, all_candidates, reviews, errors = {}, {}, {}, []
    paths = sorted((root / REVIEWS).glob('*.json'))
    if not paths:
        errors.append('missing_authority_reviews')
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            review = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as exc:
            errors.append('unreadable_authority_review:' + relative)
            continue
        if not isinstance(review, dict) or not isinstance(review.get('clauses'), list):
            errors.append('invalid_authority_review:' + relative)
            continue
        source = review.get('file')
        reviews[relative] = {'source_file': source, 'candidate_count': 0}
        source_path = safe_path(root, source)
        if source_path is None:
            errors.append('invalid_review_source:' + relative)
        elif review.get('source_sha256') != digest(source_path):
            errors.append('stale_review_source:' + relative)
        for clause in review['clauses']:
            if not isinstance(clause, dict) or not nonempty(clause.get('id')) or not strings(clause.get('symbol_refs')):
                errors.append('invalid_review_candidate:' + relative)
                continue
            cid = clause['id']
            if cid in all_candidates:
                errors.append('duplicate_review_candidate:' + cid)
            record = {'review_file': relative, 'source_file': source, 'clause': clause}
            all_candidates[cid] = record
            matched = TARGETS.intersection(clause['symbol_refs'])
            if matched:
                expected[cid] = dict(record, matched_symbols=matched)
                reviews[relative]['candidate_count'] += 1
    return expected, all_candidates, reviews, errors


def validate(spec, root):
    root = Path(root).resolve()
    expected, all_candidates, reviews, errors = source_inventory(root)
    if not isinstance(spec, dict):
        return errors + ['invalid_authority_spec']
    if spec.get('completion') is not False:
        errors.append('unsupported_authority_completion')
    if not strings(spec.get('remaining'), allow_empty=False):
        errors.append('missing_authority_remaining')
    def reject_certification(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'whole_rule_certified', 'semantic_completeness_proved', 'whole_source_complete', 'semantic_complete'} and item is not False:
                    errors.append('unsupported_authority_certification:' + key)
                reject_certification(item)
        elif isinstance(value, list):
            for item in value:
                reject_certification(item)
    reject_certification(spec)
    scope = spec.get('scope', {})
    if not isinstance(scope, dict):
        scope = {}
        errors.append('invalid_authority_scope')
    symbols = scope.get('symbols')
    if not strings(symbols) or set(symbols) != TARGETS or len(symbols) != len(TARGETS):
        errors.append('invalid_authority_target_symbols')
    for field, count in [('indexed_candidate_count', len(expected)), ('review_file_count', len(reviews))]:
        if type(scope.get(field)) is not int or scope.get(field) != count:
            errors.append('wrong_authority_count:' + field)
    snapshots = scope.get('snapshots')
    if not isinstance(snapshots, list):
        snapshots = []
        errors.append('invalid_authority_snapshots')
    snapshot_ids = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            errors.append('invalid_authority_snapshot')
            continue
        relative = snapshot.get('review_file')
        if not nonempty(relative):
            errors.append('invalid_authority_snapshot')
            continue
        snapshot_ids.append(relative)
        if relative not in reviews:
            errors.append('unknown_authority_snapshot:' + relative)
            continue
        live = reviews[relative]
        if snapshot.get('source_file') != live['source_file']:
            errors.append('wrong_snapshot_source:' + relative)
        if snapshot.get('candidate_count') != live['candidate_count']:
            errors.append('wrong_snapshot_candidate_count:' + relative)
        for path_key, hash_key in [('review_file', 'review_sha256'), ('source_file', 'source_sha256')]:
            path = safe_path(root, snapshot.get(path_key))
            if path is None or snapshot.get(hash_key) != digest(path):
                errors.append('stale_authority_snapshot:' + relative + ':' + path_key)
    if len(snapshot_ids) != len(set(snapshot_ids)):
        errors.append('duplicate_authority_snapshot')
    if set(snapshot_ids) != set(reviews):
        errors.append('authority_snapshot_set_mismatch')
    try:
        graph = json.loads((root / GRAPH).read_text(encoding='utf-8-sig'))
        graph_symbols = {node['id'] for node in graph['nodes'] if node.get('kind') == 'symbol'}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        graph_symbols = set()
        errors.append('invalid_authority_symbol_graph')
    if not TARGETS.issubset(graph_symbols):
        errors.append('missing_authority_graph_symbols')
    rows = spec.get('candidate_dispositions')
    if not isinstance(rows, list):
        rows = []
        errors.append('invalid_authority_dispositions')
    dispositions = {}
    for row in rows:
        if not isinstance(row, dict) or not nonempty(row.get('candidate_id')):
            errors.append('invalid_authority_disposition')
            continue
        cid = row['candidate_id']
        if cid in dispositions:
            errors.append('duplicate_authority_disposition:' + cid)
        dispositions[cid] = row
        live = expected.get(cid)
        if live is None:
            errors.append('unknown_authority_candidate:' + cid)
        else:
            for field in ['review_file', 'source_file']:
                if row.get(field) != live[field]:
                    errors.append('wrong_disposition_' + field + ':' + cid)
            if row.get('source_block_ids') != live['clause'].get('block_ids'):
                errors.append('wrong_disposition_blocks:' + cid)
            if row.get('statement_index') != live['clause'].get('statement'):
                errors.append('stale_disposition_statement:' + cid)
            matched = row.get('matched_symbols')
            if not strings(matched) or set(matched) != live['matched_symbols'] or len(matched) != len(set(matched)):
                errors.append('wrong_disposition_symbols:' + cid)
        if not isinstance(row.get('disposition'), str) or row.get('disposition') not in DISPOSITIONS:
            errors.append('invalid_disposition_status:' + cid)
        if not nonempty(row.get('reason')):
            errors.append('missing_disposition_reason:' + cid)
        links = row.get('atom_ids')
        if not strings(links) or len(links) != len(set(links)):
            errors.append('invalid_disposition_atom_ids:' + cid)
            links = []
        if row.get('disposition') == 'partially_atomized_draft' and not links:
            errors.append('empty_partial_disposition:' + cid)
        if isinstance(row.get('disposition'), str) and row.get('disposition') in {'indexed_pending_atomic_review', 'excluded_from_root_scope'} and links:
            errors.append('unexpected_disposition_links:' + cid)
    if set(dispositions) != set(expected):
        errors.append('authority_candidate_set_mismatch')
    records = spec.get('atoms')
    if not isinstance(records, list) or not records:
        records = []
        errors.append('missing_authority_atoms')
    atoms = {}
    line_cache = {}
    for atom in records:
        if not isinstance(atom, dict) or not nonempty(atom.get('id')):
            errors.append('invalid_authority_atom')
            continue
        aid = atom['id']
        if aid in atoms:
            errors.append('duplicate_authority_atom:' + aid)
        atoms[aid] = atom
        if not isinstance(atom.get('symbol'), str) or atom.get('symbol') not in TARGETS or atom.get('symbol') not in graph_symbols:
            errors.append('invalid_authority_atom_symbol:' + aid)
        if atom.get('status') != 'draft':
            errors.append('unsupported_authority_atom_status:' + aid)
        if not isinstance(atom.get('modality'), str) or atom.get('modality') not in MODALITIES:
            errors.append('invalid_authority_modality:' + aid)
        for field in ['statement', 'formal_relation', 'positive_case', 'negative_or_boundary_case']:
            if not nonempty(atom.get(field)):
                errors.append('missing_authority_atom_field:' + aid + ':' + field)
        for field in ['conditions', 'exceptions', 'remaining']:
            if not strings(atom.get(field), allow_empty=(field != 'conditions')):
                errors.append('invalid_authority_atom_list:' + aid + ':' + field)
        parents = atom.get('parent_candidate_ids')
        if not strings(parents, allow_empty=False) or len(parents) != len(set(parents)):
            errors.append('invalid_authority_parents:' + aid)
            parents = []
        source = atom.get('source')
        if not isinstance(source, dict):
            errors.append('invalid_authority_source:' + aid)
            source = {}
        for cid in parents:
            if cid not in dispositions:
                errors.append('unknown_authority_parent:' + aid + ':' + cid)
            elif not isinstance(dispositions[cid].get('atom_ids'), list) or aid not in dispositions[cid]['atom_ids']:
                errors.append('missing_reverse_authority_link:' + aid + ':' + cid)
            if cid in expected and source.get('file') != expected[cid]['source_file']:
                errors.append('wrong_authority_parent_source:' + aid + ':' + cid)
            if cid in expected and type(source.get('start')) is int and type(source.get('end')) is int:
                overlaps = False
                for block_id in expected[cid]['clause'].get('block_ids', []):
                    try:
                        block_file, span = block_id.rsplit(':', 1)
                        block_start, block_end = map(int, span.split('-', 1))
                    except (AttributeError, TypeError, ValueError):
                        continue
                    if (block_file == source.get('file') and block_start <= block_end
                            and max(block_start, source['start']) <= min(block_end, source['end'])):
                        overlaps = True
                if not overlaps:
                    errors.append('unrelated_authority_parent_span:' + aid + ':' + cid)
        path = safe_path(root, source.get('file'))
        start, end = source.get('start'), source.get('end')
        if path is None or type(start) is not int or type(end) is not int:
            errors.append('invalid_authority_source:' + aid)
            continue
        if path not in line_cache:
            line_cache[path] = path.read_text(encoding='utf-8-sig').splitlines()
        lines = line_cache[path]
        if not 1 <= start <= end <= len(lines):
            errors.append('invalid_authority_source_range:' + aid)
            continue
        excerpt = '\n'.join(lines[start-1:end])
        if source.get('excerpt') != excerpt:
            errors.append('stale_authority_excerpt:' + aid)
        if source.get('excerpt_sha256') != hashlib.sha256(excerpt.encode('utf-8')).hexdigest():
            errors.append('stale_authority_excerpt_hash:' + aid)
    for cid, row in dispositions.items():
        for aid in row.get('atom_ids', []) if strings(row.get('atom_ids')) else []:
            if aid not in atoms:
                errors.append('unknown_disposition_atom:' + cid + ':' + aid)
            elif not strings(atoms[aid].get('parent_candidate_ids')) or cid not in atoms[aid]['parent_candidate_ids']:
                errors.append('missing_forward_authority_link:' + cid + ':' + aid)
    gaps = spec.get('index_gaps', [])
    if not isinstance(gaps, list):
        errors.append('invalid_authority_index_gaps')
    else:
        seen_gaps = set()
        for gap in gaps:
            if not isinstance(gap, dict) or not nonempty(gap.get('candidate_id')):
                errors.append('invalid_authority_index_gap')
                continue
            cid = gap['candidate_id']
            if cid in seen_gaps or cid in expected or cid not in all_candidates:
                errors.append('invalid_authority_gap_candidate:' + cid)
            seen_gaps.add(cid)
            if not nonempty(gap.get('reason')):
                errors.append('missing_authority_gap_reason:' + cid)
    return sorted(set(errors))


def input_hashes(spec, root, spec_path=None, extra_tools=()):
    """Canonical labels permit staging validation; hashes record actual bytes read."""
    root = Path(root)
    paths = {SPEC: Path(spec_path) if spec_path else root / SPEC,
             GRAPH: root / GRAPH,
             'tools/audit_root_authority_atoms.py': Path(__file__)}
    for path in sorted((root / REVIEWS).glob('*.json')):
        paths[path.relative_to(root).as_posix()] = path
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        source = safe_path(root.resolve(), data.get('file'))
        if source:
            paths[data['file']] = source
    for atom in spec.get('atoms', []):
        source = atom.get('source', {}).get('file')
        path = safe_path(root.resolve(), source)
        if path:
            paths[source] = path
    for label, path in extra_tools:
        paths[label] = Path(path)
    return {label: digest(path) for label, path in sorted(paths.items()) if path.is_file()}


def build_report(spec, root, spec_path=None):
    errors = validate(spec, root)
    expected, _, reviews, _ = source_inventory(Path(root).resolve())
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),
                status='draft_integrity_pass' if not errors else 'invalid',
                errors=errors, indexed_candidates=len(expected), review_files=len(reviews),
                draft_records=len(spec.get('atoms', [])),
                disposition_counts=dict(Counter(row.get('disposition') for row in spec.get('candidate_dispositions', []))),
                whole_rule_certified=False, semantic_completeness_proved=False,
                coverage_percent=None,
                limitation='Only source/index/link integrity is checked. Draft record counts and cases are not proven logical atoms, executed rule tests, or semantic coverage.',
                remaining=spec.get('remaining', []),
                input_hashes=input_hashes(spec, root, spec_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    spec_path = args.spec.resolve() if args.spec else root / SPEC
    spec = json.loads(spec_path.read_text(encoding='utf-8-sig'))
    report = build_report(spec, root, spec_path)
    output = args.output or root / 'output/whole-rulebook-audit/root-authority-atoms-audit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['status', 'errors', 'indexed_candidates', 'draft_records', 'whole_rule_certified']}, ensure_ascii=False))
    return bool(report['errors'])


if __name__ == '__main__':
    raise SystemExit(main())
