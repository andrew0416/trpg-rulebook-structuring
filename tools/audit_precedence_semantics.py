"""Finite reference semantics for ROOT-05, not a game-engine completion claim."""
import csv, hashlib, itertools, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def model_errors(model):
    errors = []
    contexts = set(model.get('contexts', []))
    aspects = model.get('aspects', {})
    rules = model.get('rules', [])
    by_id = {r['id']: r for r in rules}
    if len(by_id) != len(rules):
        errors.append('duplicate_rule_id')
    if not contexts:
        errors.append('empty_context_domain')
    for aspect, algebra in aspects.items():
        if algebra not in ('exclusive', 'additive'):
            errors.append('unknown_composition:' + aspect)
    for rule in rules:
        rid = rule['id']
        if rule.get('aspect') not in aspects:
            errors.append('unknown_aspect:' + rid)
        if not set(rule.get('scope', [])) <= contexts:
            errors.append('unknown_scope:' + rid)
        if type(rule.get('selected')) is not bool and rule.get('selected') is not None:
            errors.append('invalid_selection:' + rid)
        if type(rule.get('value')) is not int:
            errors.append('invalid_value:' + rid)
    relation = set()
    for edge in model.get('overrides', []):
        general, specific = edge['general'], edge['specific']
        if general not in by_id or specific not in by_id:
            errors.append('unknown_edge_endpoint')
            continue
        if general == specific:
            errors.append('reflexive_edge')
        if by_id[general]['aspect'] != by_id[specific]['aspect']:
            errors.append('cross_aspect_override')
        if not set(by_id[specific]['scope']) <= set(by_id[general]['scope']):
            errors.append('exception_outside_general_scope')
        evidence = edge.get('evidence', {})
        if not evidence.get('anchor') or not evidence.get('mapping') or evidence.get('kind') not in ('source_review', 'synthetic_fixture'):
            errors.append('unsupported_override')
        relation.add((general, specific))
    closure = set(relation)
    for middle in by_id:
        closure |= {(a, b) for a, k in tuple(closure) for k2, b in tuple(closure) if k == middle == k2}
    if any((rid, rid) in closure for rid in by_id):
        errors.append('cyclic_specificity')
    return sorted(set(errors))

def resolve(model, context):
    errors = model_errors(model)
    if errors:
        raise ValueError(';'.join(errors))
    if context not in model['contexts']:
        raise ValueError('unknown_context')
    rules = model['rules']
    ids = [r['id'] for r in rules]
    relation = {(e['general'], e['specific']) for e in model.get('overrides', [])}
    # Floyd-Warshall reachability; independent oracle enumerates simple paths.
    for middle in ids:
        relation |= {(a, b) for a, k in tuple(relation) for k2, b in tuple(relation) if k == middle == k2}
    output = {}
    for aspect, algebra in model['aspects'].items():
        relevant = [r for r in rules if r['aspect'] == aspect and context in r['scope']]
        unknown = sorted(r['id'] for r in relevant if r['selected'] is None)
        active = [r for r in relevant if r['selected'] is True]
        maxima = sorted(r['id'] for r in active if not any((r['id'], q['id']) in relation for q in active))
        values = [r['value'] for r in active if r['id'] in maxima]
        if unknown:
            status, value = 'unresolved', None
        elif not maxima:
            status, value = 'not_applicable', None
        elif algebra == 'additive':
            status, value = 'resolved', sum(values)
        elif len(set(values)) == 1:
            status, value = 'resolved', values[0]
        else:
            status, value = 'unresolved', None
        output[aspect] = dict(status=status, value=value, contributors=maxima, unknown=unknown)
    return output

def independent_maxima(rules, edges, context):
    active = {r['id'] for r in rules if r['selected'] is True and context in r['scope']}
    universe = [r['id'] for r in rules]
    direct = {(e['general'], e['specific']) for e in edges}
    def path_exists(a, b):
        rest = [r for r in universe if r not in (a, b)]
        for length in range(len(rest) + 1):
            for middle in itertools.permutations(rest, length):
                path = (a,) + middle + (b,)
                if all(pair in direct for pair in zip(path, path[1:])):
                    return True
        return False
    return sorted(a for a in active if not any(a != b and path_exists(a, b) for b in active))

def fixture_edge(a, b):
    return dict(general=a, specific=b, evidence=dict(kind='synthetic_fixture', anchor='finite-domain', mapping='declared same-aspect override'))

def finite_check(resolver=resolve):
    ids = ['a', 'b', 'c']
    directed = [(a, b) for a in ids for b in ids if a != b]
    cases, relations, failures = 0, 0, []
    for flags in itertools.product([False, True], repeat=6):
        edges = [fixture_edge(a, b) for (a, b), take in zip(directed, flags) if take]
        seed = dict(contexts=['x'], aspects={'value': 'exclusive'}, rules=[
            dict(id=a, aspect='value', scope=['x'], selected=True, value=0) for a in ids], overrides=edges)
        if model_errors(seed):
            continue
        relations += 1
        for active in itertools.product([False, True], repeat=3):
            for values in itertools.product([0, 1], repeat=3):
                model = dict(seed, rules=[dict(r, selected=s, value=v) for r, s, v in zip(seed['rules'], active, values)])
                maxima = independent_maxima(model['rules'], edges, 'x')
                wanted_values = {r['value'] for r in model['rules'] if r['id'] in maxima}
                status = 'not_applicable' if not maxima else 'resolved' if len(wanted_values) == 1 else 'unresolved'
                value = next(iter(wanted_values)) if status == 'resolved' else None
                expected = dict(status=status, value=value, contributors=maxima, unknown=[])
                actual = resolver(model, 'x')['value']
                cases += 1
                if actual != expected:
                    if len(failures) < 10:
                        failures.append(dict(model=model, expected=expected, actual=actual))
    return dict(node_count=3, accepted_directed_acyclic_graphs=relations, cases=cases,
                counterexamples=failures, status='pass' if not failures else 'fail',
                limitation='Exhaustive for this declared 3-node, Boolean-selection, binary-value exclusive-composition domain only. No source-fidelity or runtime-conformance proof.')

def source_errors(spec, root):
    errors = []
    for anchor in spec['source_grounding']:
        s = anchor['source']
        lines = (root / s['file']).read_text(encoding='utf-8').splitlines()
        excerpt = '\n'.join(lines[s['start']-1:s['end']])
        if excerpt != s['excerpt'] or hashlib.sha256(excerpt.encode()).hexdigest() != s['excerpt_sha256']:
            errors.append('stale_source:' + anchor['id'])
    return errors

def duplicate_evidence(root):
    with (root / 'input/db/abilities.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    candidates = [(i + 2, row) for i, row in enumerate(rows) if row['이름'] == '옹골참 [홈브류]']
    if len(candidates) != 2:
        return dict(status='changed_inventory', candidate_count=len(candidates))
    fields = list(candidates[0][1])
    differences = {key: [row[key] for _, row in candidates] for key in fields
                   if candidates[0][1][key] != candidates[1][1][key]}
    return dict(status='not_equivalent_in_saved_source' if differences else 'same_saved_cells_identity_not_proven',
        candidates=[dict(record_number=num, cells=row,
            cells_sha256=hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()) for num, row in candidates],
        same_primary_effect=candidates[0][1]['효과'] == candidates[1][1]['효과'],
        differing_fields=differences,
        conclusion='Same title/effect body does not imply semantic identity: trigger and edition metadata differ. Preserve unresolved replacement and both source records.',
        live_source_review='not_performed')

def audit(root=ROOT):
    spec = json.loads((root / 'data/verification/precedence-semantics.json').read_text(encoding='utf-8'))
    errors = source_errors(spec, root)
    finite = finite_check()
    if finite['counterexamples']:
        errors.append('finite_model_counterexample')
    paths = ['tools/audit_precedence_semantics.py','data/verification/precedence-semantics.json',
             'input/ch01-intro.md','input/ch06-gameplay.md','input/db/abilities.csv']
    return dict(status='model_checked_source_mapping_pending' if not errors else 'invalid',
        errors=errors, formal_model=finite, duplicate_candidate_review=duplicate_evidence(root),
        runtime_conformance='not_implemented_by_this_model', whole_rule_certified=False,
        remaining=spec['remaining'], input_hashes={p:sha(root/p) for p in paths})

if __name__ == '__main__':
    result = audit()
    path = ROOT/'output/whole-rulebook-audit/precedence-semantics-audit.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], errors=result['errors'], finite_cases=result['formal_model']['cases'],
                         duplicate_status=result['duplicate_candidate_review']['status']), ensure_ascii=False))
    raise SystemExit(1 if result['errors'] else 0)
