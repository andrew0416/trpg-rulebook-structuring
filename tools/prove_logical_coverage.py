"""Exhaustive certificates for small Boolean models.
Proves the declared Boolean domain only, never natural-language completeness or all runtime states.
"""
import hashlib,itertools,json
from pathlib import Path

def evaluate(expr,values):
    if type(expr) is bool:return expr
    if not isinstance(expr,dict):raise ValueError('non-Boolean expression')
    if set(expr)=={'var'}:
        value=values[expr['var']]
        if type(value) is not bool:raise ValueError('non-Boolean variable')
        return value
    op=expr.get('op');args=expr.get('args',[])
    if op=='not' and len(args)==1:return not evaluate(args[0],values)
    if op in ('and','or') and len(args)>=2:
        vals=[evaluate(arg,values) for arg in args]
        return all(vals) if op=='and' else any(vals)
    raise ValueError('unsupported Boolean operator/arity')

def expand(expr,bindings):
    if not isinstance(expr,dict):return expr
    if set(expr)=={'var'}:return bindings[expr['var']]
    return dict(op=expr['op'],args=[expand(arg,bindings) for arg in expr['args']])

def prove(model,results,witnesses):
    variables=model['variables'];names=list(variables)
    if not names or len(names)>16 or any(v!='boolean' for v in variables.values()):
        raise ValueError('requires 1..16 Boolean variables')
    points=[dict(zip(names,values)) for values in itertools.product([False,True],repeat=len(names))]
    def key(v):return tuple(v[name] for name in names)
    oracles={key(row['inputs']):row['expected'] for row in model['independent_truth_table']}
    errors=[]
    if len(oracles)!=len(model['independent_truth_table']):errors.append('duplicate_oracle_rows')
    if set(oracles)!={key(v) for v in points}:errors.append('incomplete_independent_truth_table')
    if any(type(x) is not bool for x in oracles.values()):errors.append('non_boolean_oracle')
    rows=[];counterexamples=[];covered=set()
    for p in points:
        answer=evaluate(model['expression'],p);expected=oracles.get(key(p))
        if answer!=expected:counterexamples.append(dict(inputs=p,model=answer,expected=expected))
        testids=[tid for tid,w in witnesses.items() if w.get('model_id')==model['id'] and w.get('inputs')==p and results.get(tid,{}).get('status')=='pass']
        if testids:covered.add(key(p))
        rows.append(dict(inputs=p,result=answer,test_ids=testids))
    independence=[]
    for name in names:
        pairs=[]
        for left,right in itertools.combinations(rows,2):
            changed=[n for n in names if left['inputs'][n]!=right['inputs'][n]]
            if changed==[name] and left['result']!=right['result'] and left['test_ids'] and right['test_ids']:
                pairs.append(dict(left=left['inputs'],right=right['inputs'],left_test=left['test_ids'][0],right_test=right['test_ids'][0]))
        independence.append(dict(condition=name,covered=bool(pairs),witness=pairs[0] if pairs else None))
    complete=not errors and not counterexamples and len(covered)==len(points) and all(x['covered'] for x in independence)
    return dict(model_id=model['id'],proof_status='proved_for_declared_boolean_model' if complete else 'incomplete',valuation_count=len(points),covered_valuations=len(covered),coverage_percent=100*len(covered)/len(points),truth_table=rows,independent_condition_effects=independence,errors=errors,counterexamples=counterexamples,whole_rule_certified=False,scope=model['scope'],assumptions=model['assumptions'],excluded_obligations=model['excluded_obligations'])

def main(root):
    models=json.loads((root/'data/verification/logical-models.json').read_text(encoding='utf-8'))['models']
    contracts={c['id']:c for c in json.loads((root/'data/verification/rule-contracts.json').read_text(encoding='utf-8'))['contracts']}
    report=json.loads((root/'output/mettle-tests.json').read_text(encoding='utf-8'))
    results={r['id']:r for r in report['results']};witnesses=report.get('logical_witnesses',{})
    freshness=[]
    for file,expected in report['input_hashes'].items():
        if hashlib.sha256((root/file).read_bytes()).hexdigest()!=expected:freshness.append('stale_execution_evidence:'+file)
    proofs=[]
    for model in models:
        proof=prove(model,results,witnesses)
        clause=next(c for c in contracts[model['contract_id']]['clauses'] if c['id']==model['clause_id'])
        if expand(model['expression'],model['abstraction_bindings'])!=clause['when']:proof['errors'].append('model_contract_mismatch')
        proof['errors']+=freshness
        if proof['errors']:proof['proof_status']='incomplete'
        proofs.append(proof)
    paths=[root/'data/verification/logical-models.json',root/'data/verification/rule-contracts.json',root/'output/mettle-tests.json',Path(__file__)]
    result=dict(proofs=proofs,all_declared_models_proved=all(p['proof_status']=='proved_for_declared_boolean_model' for p in proofs),whole_rulebook_certified=False,input_hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},meaning='Finite Boolean coverage and matching test witnesses, conditional on declared abstraction. No proof of source completeness, numeric predicate derivation, state-transition coverage, or whole-program equivalence.')
    (root/'output/whole-rulebook-audit/logical-coverage-proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([dict(model=p['model_id'],status=p['proof_status'],covered=p['covered_valuations'],total=p['valuation_count'],errors=p['errors']) for p in proofs],ensure_ascii=False))
    return 0 if result['all_declared_models_proved'] else 1
if __name__=='__main__':raise SystemExit(main(Path(__file__).resolve().parents[1]))
