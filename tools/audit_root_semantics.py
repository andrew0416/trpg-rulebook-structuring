"""Integrity checks for the partial root specification, not semantic proof."""
import hashlib,json

REQUIRED_CRITERIA={'source_scope','typed_state','transition_totality','exception_composition','proof_and_conformance'}

def closure_blockers(spec):
    blocks=[]
    inventory=spec.get('source_inventory',{})
    if inventory.get('status')!='complete' or inventory.get('reviewed_complete') is not True or inventory.get('common_clause_total')!=len(spec.get('clauses',[])):
        blocks.append('common_source_inventory_not_closed')
    criteria=spec.get('completion_criteria',[])
    if {c['id'] for c in criteria}!=REQUIRED_CRITERIA:blocks.append('completion_criteria_missing')
    for c in criteria:
        if c.get('status')!='complete' or not c.get('evidence'):blocks.append('criterion_pending:'+c['id'])
    for c in spec.get('clauses',[]):
        if c.get('status')!='reviewed' or c.get('remaining') or not c.get('evidence'):blocks.append('clause_pending:'+c['id'])
    for finding in spec.get('open_findings',[]):
        if finding.get('status')!='resolved':blocks.append('root_finding_unresolved:'+finding['id'])
    if not spec.get('clauses'):blocks.append('root_clauses_missing')
    return blocks

def validate_root(spec,graph,root):
    errors=[];nodes={n['id'] for n in graph['nodes']}
    from audit_common_source_inventory import validate as validate_inventory
    inventory_path=spec.get('source_inventory',{}).get('physical_inventory')
    if inventory_path!='data/verification/common-source-inventory.json' or not (root/inventory_path).is_file():
        errors.append('physical_source_inventory_missing')
    else:
        inventory=json.loads((root/inventory_path).read_text(encoding='utf-8'))
        errors += ['source_inventory:'+e for e in validate_inventory(inventory,root)]
    from audit_common_scope_inventory import audit as audit_scope
    if spec.get('source_inventory',{}).get('semantic_scope_reviews')!='data/verification/common-source-reviews':
        errors.append('semantic_scope_reviews_missing')
    else:
        errors += ['semantic_scope:'+e for e in audit_scope(root)['errors']]
    from audit_root_authority_atoms import validate as validate_authority_atoms
    authority_path='data/verification/root-authority-atoms.json'
    if spec.get('source_inventory',{}).get('authority_atom_draft')!=authority_path or not (root/authority_path).is_file():
        errors.append('authority_atom_draft_missing')
    else:
        errors += ['authority_atoms:'+e for e in validate_authority_atoms(json.loads((root/authority_path).read_text(encoding='utf-8')),root)]
    from audit_root_authority_scope import validate as validate_authority_scope
    scope_path='data/verification/root-authority-scope-review.json'
    if spec.get('source_inventory',{}).get('authority_scope_review')!=scope_path or not (root/scope_path).is_file():
        errors.append('authority_scope_review_missing')
    else:
        errors += ['authority_scope:'+e for e in validate_authority_scope(json.loads((root/scope_path).read_text(encoding='utf-8')),root)]
    from audit_root_authority_scope_inventory import validate as validate_scope_inventory, SPEC_NAMES
    inventory_paths=['data/verification/'+name for name in SPEC_NAMES]
    if spec.get('source_inventory',{}).get('authority_scope_inventory_reviews')!=inventory_paths or any(not (root/p).is_file() for p in inventory_paths):
        errors.append('authority_scope_inventory_reviews_missing')
    else:
        combined=[json.loads((root/p).read_text(encoding='utf-8')) for p in inventory_paths]
        errors += ['authority_scope_inventory:'+e for e in validate_scope_inventory(combined,root)[0]]
    from audit_root_mixed_decomposition import validate as validate_mixed, SPECS as MIXED_SPECS
    mixed_paths=list(MIXED_SPECS)
    if spec.get('source_inventory',{}).get('mixed_decomposition_reviews')!=mixed_paths or any(not (root/p).is_file() for p in mixed_paths):
        errors.append('mixed_decomposition_reviews_missing')
    else:
        errors += ['mixed_decomposition:'+e for e in validate_mixed([json.loads((root/p).read_text(encoding='utf-8')) for p in mixed_paths],root)]
    from audit_common_numeric_semantics import validate as validate_numeric
    from audit_world_state_semantics import validate as validate_state
    from audit_precedence_semantics import source_errors as validate_precedence_sources
    for section, expected, validator in [
        ('arithmetic', 'data/verification/common-numeric-semantics.json', validate_numeric),
        ('state_model', 'data/verification/world-state-semantics.json', validate_state),
        ('specificity', 'data/verification/precedence-semantics.json', validate_precedence_sources),
    ]:
        if spec.get(section, {}).get('specification') != expected or not (root/expected).is_file():
            errors.append('root_supporting_spec_missing:'+section)
            continue
        try:
            supporting=json.loads((root/expected).read_text(encoding='utf-8'))
            errors += [section+':'+e for e in validator(supporting, root)]
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append('root_supporting_spec_invalid:'+section+':'+type(exc).__name__)
    from audit_common_action_lifecycle import validate as validate_action_lifecycle
    from audit_action_cost_semantics import validate as validate_action_costs
    from audit_common_checks import validate as validate_checks
    from test_common_precedence_edges import validate as validate_edges
    for section, key, expected, validator in [
        ('transition_model','action_lifecycle','data/verification/common-action-lifecycle-semantics.json',validate_action_lifecycle),
        ('transition_model','action_costs','data/verification/action-cost-semantics.json',validate_action_costs),
        ('transition_model','common_checks','data/verification/common-check-semantics.json',validate_checks),
        ('specificity','source_edge_inventory','data/verification/common-precedence-edges.json',validate_edges),
    ]:
        if spec.get(section,{}).get(key)!=expected or not (root/expected).is_file():
            errors.append('root_supporting_spec_missing:'+key);continue
        supporting=json.loads((root/expected).read_text(encoding='utf-8'))
        errors += [key+':'+e for e in validator(supporting,root)]
    from audit_life_state import validate as validate_life
    path='data/verification/life-state-semantics.json'
    if spec.get('state_model',{}).get('life_transitions')!=path or not (root/path).is_file():
        errors.append('life_state_spec_missing')
    else:
        errors += ['life_state:'+e for e in validate_life(json.loads((root/path).read_text(encoding='utf-8')),root)]
    from audit_time_boundaries import validate as validate_time
    time_path='data/verification/time-boundary-semantics.json'
    if spec.get('state_model',{}).get('time_boundaries')!=time_path or not (root/time_path).is_file():
        errors.append('time_boundary_spec_missing')
    else:
        errors += ['time_boundary:'+e for e in validate_time(json.loads((root/time_path).read_text(encoding='utf-8')),root)]
    from audit_recovery_semantics import validate as validate_recovery
    recovery_path='data/verification/recovery-semantics.json'
    if spec.get('state_model',{}).get('recovery')!=recovery_path or not (root/recovery_path).is_file():
        errors.append('recovery_spec_missing')
    else:
        errors += ['recovery:'+e for e in validate_recovery(json.loads((root/recovery_path).read_text(encoding='utf-8')),root)]
    clauses=spec.get('clauses',[])
    ids=[c['id'] for c in clauses]
    if len(ids)!=len(set(ids)):errors.append('duplicate_root_clause')
    if not ids:errors.append('root_clauses_missing')
    if spec.get('source_inventory',{}).get('enumerated_root_clauses')!=len(ids):errors.append('root_inventory_count_mismatch')
    for c in clauses:
        if c.get('symbol') not in nodes:errors.append('unknown_root_symbol:'+c['id'])
        s=c.get('source',{});path=root/s.get('file','')
        if not isinstance(s.get('start'),int) or not isinstance(s.get('end'),int) or s['start']<1 or s['end']<s['start'] or not path.is_file():
            errors.append('invalid_root_source:'+c['id']);continue
        lines=path.read_text(encoding='utf-8').splitlines()
        excerpt='\n'.join(lines[s['start']-1:s['end']])
        if s['end']>len(lines) or excerpt!=s.get('excerpt') or hashlib.sha256(excerpt.encode()).hexdigest()!=s.get('excerpt_sha256'):errors.append('stale_root_source:'+c['id'])
        if not c.get('formal') or not c.get('proof_obligations'):errors.append('root_obligations_missing:'+c['id'])
    if spec.get('closure',{}).get('current') or spec.get('status') in ('complete','reviewed'):
        if closure_blockers(spec):errors.append('unsupported_root_completion_claim')
    return errors
