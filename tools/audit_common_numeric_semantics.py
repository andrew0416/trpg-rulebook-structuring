"""Integrity of a supporting arithmetic source specification, not runtime conformance."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ANCHOR_IDS = {'K-default','K-evasion-conflict','K-evasion-combat','K-stage','K-hp','K-damage','K-damage-example','K-contest','K-local-ceil','K-xp','P-default','P-evasion','P-stage','P-movement','P-contest','K-xp-significance','P-xp-significance'}
RELATION_STATUS = {'N01':'resolved','N02':'resolved','N03':'resolved','N04':'provisional','N05':'resolved','N06':'unresolved','N07':'provisional','N08':'unresolved','N09':'unresolved','N10':'resolved','N11':'resolved','N12':'unresolved','N13':'resolved','N14':'provisional'}
ORACLE_KINDS = {'resolved_operator','resolved_composition','conditional_named_boundary','resolved_operator_operand_pending','provisional_translation_oracle','resolved_multiplier_path','unresolved_sentence_equivalence','provisional_local_signed_operator','unresolved_alternatives','resolved_source_example','source_expectation_cases','documented_composition_boundary'}
TOP_FIELDS = {'schema_version','kind','status','root_contract','symbol_refs','whole_semantic_complete','implementation_conformance_proved','semantic_coverage_proved','claim_scope','source_anchors','typed_semantics','boundary_oracles','source_authority','remaining'}
HEX = set('0123456789abcdef')

def sha(data):
    return hashlib.sha256(data).hexdigest()


def _relative_file(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('source path must be relative')
    p = (root / name).resolve()
    if not p.is_relative_to(root):
        raise ValueError('source path escapes root')
    return p


@lru_cache(maxsize=4)
def _pdf_reader(absolute_path, actual_sha256):
    from pypdf import PdfReader
    return PdfReader(absolute_path)


@lru_cache(maxsize=32)
def _pdf_text(absolute_path, actual_sha256, page_index):
    # Caller hashes the current file before every lookup. A same-path mutation
    # never reuses old text under a new digest. No mtime-only trust is used.
    reader = _pdf_reader(absolute_path, actual_sha256)
    return reader.pages[page_index].extract_text() or ''


def validate(spec, root):
    """Return integrity errors; an empty list makes no semantic completion claim."""
    errors = []
    root = Path(root).resolve()
    if not isinstance(spec, dict):
        return ['spec must be an object']
    if set(spec) != TOP_FIELDS:
        errors.append('unexpected or missing top-level fields: ' + str(sorted(set(spec) ^ TOP_FIELDS)))
    for key in ('whole_semantic_complete','implementation_conformance_proved','semantic_coverage_proved'):
        if spec.get(key) is not False:
            errors.append(key + ' must remain false')
    for key, value in [('schema_version',1),('kind','source_grounded_supporting_spec'),('status','draft_local_contexts'),('root_contract','math.root')]:
        if spec.get(key) != value:
            errors.append(key + ' has unsupported value')
    if not isinstance(spec.get('claim_scope'), str) or not spec.get('claim_scope'):
        errors.append('claim_scope missing')
    def texts(value, label, nonempty=True):
        if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(x,str) or not x.strip() for x in value):
            errors.append(label + ' must be a list of nonempty strings')
            return []
        if len(set(value)) != len(value):
            errors.append(label + ' contains duplicates')
        return value
    def records(value, label, expected):
        if not isinstance(value, list):
            errors.append(label + ' must be a list')
            return {}
        result = {}
        for row in value:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                errors.append(label + ' contains invalid record')
                continue
            uid = row['id']
            if uid in result:
                errors.append(label + ' duplicate id ' + uid)
            result[uid] = row
        if set(result) != expected:
            errors.append(label + ' missing/unknown ids ' + str(sorted(set(result) ^ expected)))
        return result
    texts(spec.get('remaining'), 'remaining')
    authority = spec.get('source_authority')
    if not isinstance(authority, dict):
        errors.append('source_authority must be an object')
    else:
        for key in ('ptk','ptu','decision'):
            if not isinstance(authority.get(key), str) or not authority.get(key):
                errors.append('source_authority.' + key + ' missing')
        if authority.get('resolved_scope') != 'local_source_backed_only':
            errors.append('resolved scope must be local source-backed only')
        for key in ('ptu_automatically_overrides_ptk','resolved_means_whole_rule'):
            if authority.get(key) is not False:
                errors.append(key + ' must remain false')
    try:
        graph = json.loads((root/'data/verification/rule-symbol-graph.json').read_text(encoding='utf-8'))
        symbols = {x['id'] for x in graph['nodes']}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append('symbol graph unreadable: ' + str(exc)); symbols = set()
    refs = texts(spec.get('symbol_refs'), 'symbol_refs')
    if set(refs) != {'math.rounding','math.percent_addition'} or set(refs) - symbols:
        errors.append('unknown/missing supporting math symbols')
    anchors = records(spec.get('source_anchors'), 'anchors', ANCHOR_IDS)
    files = {}
    for uid, a in anchors.items():
        kind = a.get('kind')
        if not isinstance(kind,str) or kind not in ('markdown','pdf'):
            errors.append(uid + ': unknown anchor kind'); continue
        for key in ('file_sha256','excerpt_sha256') + (('page_text_sha256',) if kind == 'pdf' else ()):
            value = a.get(key)
            if not isinstance(value,str) or len(value)!=64 or not set(value)<=HEX:
                errors.append(uid + ': invalid ' + key)
        excerpt = a.get('excerpt')
        if not isinstance(excerpt,str) or not excerpt:
            errors.append(uid + ': missing excerpt'); continue
        if sha(excerpt.encode('utf-8')) != a.get('excerpt_sha256'):
            errors.append(uid + ': excerpt hash mismatch')
        try:
            path = _relative_file(root, a.get('file'))
            if path not in files:
                blob = path.read_bytes(); files[path] = (blob, sha(blob))
            blob, digest = files[path]
            if digest != a.get('file_sha256'):
                errors.append(uid + ': actual source hash mismatch'); continue
            if kind == 'markdown':
                start, end = a.get('line_start'), a.get('line_end')
                lines = blob.decode('utf-8').splitlines()
                if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
                    errors.append(uid + ': invalid line range'); continue
                if a.get('normalization') != 'UTF-8 lines joined with LF, no trailing LF':
                    errors.append(uid + ': unknown Markdown normalization')
                if '\n'.join(lines[start-1:end]) != excerpt:
                    errors.append(uid + ': actual line excerpt mismatch')
            else:
                page = a.get('page_index')
                if type(page) is not int or page < 0:
                    errors.append(uid + ': invalid PDF page index'); continue
                if type(a.get('printed_page')) is not int or a['printed_page'] != page + 1:
                    errors.append(uid + ': inconsistent printed page locator')
                if a.get('normalization') not in ('exact substring of pypdf extract_text(); line breaks preserved','exact pypdf extract_text substring'):
                    errors.append(uid + ': unknown PDF normalization')
                page_text = _pdf_text(str(path), digest, page)
                if sha(page_text.encode('utf-8')) != a.get('page_text_sha256'):
                    errors.append(uid + ': actual PDF page text hash mismatch')
                if excerpt not in page_text:
                    errors.append(uid + ': PDF excerpt not found on page')
        except (OSError, ValueError, UnicodeError, IndexError, ImportError) as exc:
            errors.append(uid + ': cannot read source: ' + str(exc))
    if Counter(a.get('kind') if isinstance(a.get('kind'),str) else '<invalid>' for a in anchors.values()) != {'markdown':11,'pdf':6}:
        errors.append('anchor kind inventory must be 11 markdown and 6 pdf')
    typed = spec.get('typed_semantics')
    if not isinstance(typed,dict):
        errors.append('typed_semantics must be an object'); typed = {}
    texts(typed.get('types'), 'typed_semantics.types')
    texts(typed.get('modeling_conventions'), 'typed_semantics.modeling_conventions')
    relations = records(typed.get('relations'), 'relations', set(RELATION_STATUS))
    oracles = records(spec.get('boundary_oracles'), 'oracles', {'O%02d'%i for i in range(1,15)})
    used_anchors = set()
    oracle_users = {}
    for uid, row in relations.items():
        if row.get('status') != RELATION_STATUS.get(uid):
            errors.append(uid + ': reviewed local status changed or unknown')
        if row.get('resolution_scope') != 'local_only':
            errors.append(uid + ': scope must remain local_only')
        if not isinstance(row.get('symbol'),str) or row.get('symbol') not in symbols:
            errors.append(uid + ': unknown symbol')
        for key in ('statement','formal'):
            if not isinstance(row.get(key),str) or not row.get(key):
                errors.append(uid + ': missing ' + key)
        for key in ('conditions','remaining'):
            texts(row.get(key), uid + '.' + key)
        texts(row.get('exceptions'), uid + '.exceptions', nonempty=False)
        sources = texts(row.get('sources'), uid + '.sources')
        used_anchors.update(sources)
        if set(sources) - set(anchors):
            errors.append(uid + ': unknown source reference')
        refs = texts(row.get('oracle_refs'), uid + '.oracle_refs', nonempty=False)
        if row.get('oracle_status') != ('bounded_cases_only' if refs else 'interpretation_only_no_case'):
            errors.append(uid + ': invalid oracle scope')
        if not refs and row.get('status') != 'unresolved':
            errors.append(uid + ': resolved/provisional relation lacks a case')
        for ref in refs:
            oracle_users.setdefault(ref,[]).append(uid)
            if ref not in oracles or oracles[ref].get('condition') != uid:
                errors.append(uid + ': invalid oracle backreference ' + ref)
    if used_anchors != set(anchors):
        errors.append('unused or unknown source anchors')
    for uid, row in oracles.items():
        condition = row.get('condition')
        if not isinstance(condition,str) or condition not in relations:
            errors.append(uid + ': unknown condition'); continue
        if oracle_users.get(uid) != [condition]:
            errors.append(uid + ': missing/ambiguous condition backreference')
        if not isinstance(row.get('kind'),str) or row.get('kind') not in ORACLE_KINDS:
            errors.append(uid + ': unknown oracle kind')
        sources = texts(row.get('source_anchors'), uid + '.source_anchors')
        if set(sources) - set(relations[condition].get('sources', [])):
            errors.append(uid + ': case source not grounded in condition')
        if relations[condition].get('status') == 'unresolved' and row.get('gate_pass_allowed') is not False:
            errors.append(uid + ': unresolved case must prohibit gate pass')
        if row.get('gate_pass_allowed') is True:
            errors.append(uid + ': case cannot claim global gate pass')
        if uid == 'O13' and (row.get('kind') != 'source_expectation_cases' or row.get('runtime_conformance') != 'not_evaluated'):
            errors.append('O13 must retain expectations without runtime conformance')
        if uid == 'O03' and row.get('does_not_set_global_boundary') is not True:
            errors.append('O03 cannot establish a global boundary')
        if uid == 'O04' and row.get('contest_input_count_unresolved') is not True:
            errors.append('O04 operand uncertainty must remain')
        if uid == 'O14' and row.get('outside_range_oracle', 'missing') is not None:
            errors.append('O14 outside-range oracle must remain null')
    payload_fields = {
        'O01':('inputs','expected'), 'O02':('base','rates','exact_result','rejected_compounding'),
        'O03':('base','rates','exact_result','final_floor_if_integer_quantity','rejected_component_floor'),
        'O04':('n','ceil_half'), 'O05':('stats','floor_evasion','nearest_alternative_at8'),
        'O06':('base','stages','expected'), 'O07':('base','stage','table','shortcut'),
        'O08':('stages','floor_half','symmetric_magnitude_alternative'),
        'O09':('real_max_hp','signed_then_floor','magnitude_then_negate'),
        'O10':('real_max_hp','injuries','per_injury_floor','combined_fraction_floor'),
        'O11':('exact_result','expected'), 'O12':('total','recipients','expected_each'),
        'O13':('cases',), 'O14':('cases',)}
    for uid, fields in payload_fields.items():
        if uid in oracles and any(key not in oracles[uid] for key in fields):
            errors.append(uid + ': missing boundary case payload')
    for uid, keys in [('O13',{'input','expected_per_player'}),('O14',{'base','S','C','expected'})]:
        cases = oracles.get(uid,{}).get('cases')
        if not isinstance(cases,list) or not cases or any(not isinstance(case,dict) or not keys <= set(case) for case in cases):
            errors.append(uid + ': invalid source expectation cases')
    def no_runtime(value):
        if isinstance(value,dict):
            for key, child in value.items():
                if key in ('runtime_review','input_hashes','actual_per_player','actual_effective','observations','current_conformance'):
                    errors.append('historical/runtime evidence forbidden in supporting spec: ' + key)
                no_runtime(child)
        elif isinstance(value,list):
            for child in value: no_runtime(child)
    no_runtime(spec)
    return errors


def input_hashes(spec, root, paths=()):
    root = Path(root).resolve()
    candidates = {Path(p).resolve() for p in paths}
    candidates.add(root/'data/verification/rule-symbol-graph.json')
    for a in spec.get('source_anchors', []):
        try: candidates.add(_relative_file(root,a.get('file')))
        except (ValueError,TypeError,AttributeError): continue
    result = {}
    for p in sorted(candidates):
        if p.is_file():
            key = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
            result[key] = sha(p.read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = args.spec or args.root/'data/verification/common-numeric-semantics.json'
    spec = json.loads(path.read_text(encoding='utf-8'))
    errors = validate(spec,args.root)
    report = {'generated_at':datetime.now(timezone.utc).isoformat(),'scope':'supporting spec integrity only; no implementation equivalence or whole semantic completion','errors':errors,'results':[{'id':'MATH-SPEC-integrity','status':'fail' if errors else 'pass'}],'input_hashes':input_hashes(spec,args.root,[path,Path(__file__)]),'local_status_counts':dict(Counter(r['status'] for r in spec.get('typed_semantics',{}).get('relations',[]))),'whole_semantic_complete':False}
    output = args.output or args.root/'output/common-numeric-semantics-audit.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'errors':errors,'anchors':len(spec.get('source_anchors',[])),'local_status_counts':report['local_status_counts']},ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
