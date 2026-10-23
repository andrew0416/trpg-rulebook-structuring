"""Validate saved source anchors and partial common time evidence; not closure."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC='data/verification/time-boundary-semantics.json'

def validate(spec,root):
    errors=[]
    if any(spec.get('certification',{}).values()):errors.append('unsupported_time_certification')
    clauses=spec.get('clauses',[])
    if not clauses or len({c['id'] for c in clauses})!=len(clauses):errors.append('invalid_time_clauses')
    for c in clauses:
        src=c.get('source',{});path=root/src.get('file','')
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            errors.append('invalid_time_source:'+c['id']);continue
        lines=path.read_text(encoding='utf-8').splitlines();a,b=src.get('start',0),src.get('end',0)
        excerpt='\n'.join(lines[a-1:b])
        if a<1 or b<a or b>len(lines) or excerpt!=src.get('excerpt') or hashlib.sha256(excerpt.encode()).hexdigest()!=src.get('excerpt_sha256'):
            errors.append('stale_time_source:'+c['id'])
        if not c.get('proof_obligations'):errors.append('missing_time_obligations:'+c['id'])
    runtime=spec.get('runtime_contract',{})
    if not runtime.get('remaining'):errors.append('unsupported_time_runtime_closure')
    supporting='data/verification/session-frequency-source-review.json'
    if runtime.get('session_frequency_review')!=supporting or not (root/supporting).is_file():
        errors.append('missing_session_frequency_review')
    else:
        session=json.loads((root/supporting).read_text(encoding='utf-8'))
        if session.get('whole_rule_certified') is not False or not session.get('remaining'):
            errors.append('unsupported_session_frequency_closure')
    tests=runtime.get('partial_tests',[])
    tree=ast.parse((root/'tools/test_time_boundaries.py').read_text(encoding='utf-8-sig'))
    ids={'TIME-'+n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    if not tests or not set(tests)<=ids:errors.append('invalid_time_test_links')
    return errors

if __name__=='__main__':
    spec=json.loads((ROOT/SPEC).read_text(encoding='utf-8'));errors=validate(spec,ROOT)
    paths=[SPEC,'data/verification/session-frequency-source-review.json','tools/audit_time_boundaries.py','tools/test_time_boundaries.py']+spec['runtime_contract']['implementation']+sorted({c['source']['file'] for c in spec['clauses']})
    report=dict(status='integrity_pass_runtime_partial' if not errors else 'invalid',errors=errors,clauses=len(spec['clauses']),proof_obligations=sum(len(c['proof_obligations']) for c in spec['clauses']),integration_obligations=len(spec['integration_obligations']),whole_rule_certified=False,remaining=spec['runtime_contract']['remaining'],input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/whole-rulebook-audit/time-boundary-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('remaining','input_hashes')},ensure_ascii=False));raise SystemExit(bool(errors))
