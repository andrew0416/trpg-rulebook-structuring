"""Integrity of common check source links and executable evidence; not closure."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC='data/verification/common-check-semantics.json'

def validate(spec,root):
    errors=[]
    root_spec=json.loads((root/'data/verification/root-semantics.json').read_text(encoding='utf-8'))
    parents={c['id'] for c in root_spec['clauses']}
    tree=ast.parse((root/'tools/test_common_checks.py').read_text(encoding='utf-8-sig'))
    tests={'CHECK-'+n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    ids=[c['id'] for c in spec.get('clauses',[])]
    if not ids or len(ids)!=len(set(ids)):errors.append('invalid_clause_inventory')
    if spec.get('whole_rule_certified') is not False or not spec.get('remaining'):errors.append('unsupported_completion_claim')
    for c in spec.get('clauses',[]):
        if c.get('parent_clause') not in parents:errors.append('unknown_parent:'+c['id'])
        if not c.get('tests') or not set(c['tests'])<=tests:errors.append('missing_test:'+c['id'])
        s=c.get('source',{});path=root/s.get('file','')
        if not path.is_file() or not path.resolve().is_relative_to((root/'input').resolve()):errors.append('invalid_source:'+c['id']);continue
        lines=path.read_text(encoding='utf-8').splitlines()
        if type(s.get('start')) is not int or type(s.get('end')) is not int or not 1<=s['start']<=s['end']<=len(lines):errors.append('invalid_range:'+c['id']);continue
        excerpt='\n'.join(lines[s['start']-1:s['end']])
        if excerpt!=s.get('excerpt') or hashlib.sha256(excerpt.encode()).hexdigest()!=s.get('excerpt_sha256'):errors.append('stale_source:'+c['id'])
    return errors

if __name__=='__main__':
    spec=json.loads((ROOT/SPEC).read_text(encoding='utf-8'));errors=validate(spec,ROOT)
    paths=[SPEC,'tools/audit_common_checks.py','tools/test_common_checks.py','engine/common_checks.py','engine/engine.py','data/core-rules.json','data/verification/root-semantics.json']+sorted({c['source']['file'] for c in spec['clauses']})
    result=dict(status='integrity_pass_semantics_partial' if not errors else 'invalid',errors=errors,clause_groups=len(spec['clauses']),whole_rule_certified=False,remaining=spec['remaining'],input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/whole-rulebook-audit/common-check-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_hashes','remaining')},ensure_ascii=False));raise SystemExit(bool(errors))
