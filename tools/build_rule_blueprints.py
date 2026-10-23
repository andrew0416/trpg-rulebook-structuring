"""Project classified clauses into one authoring format, without certification."""
from pathlib import Path
import argparse, collections, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
import rule_blueprints as B

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build(analysis,output):
    if output.exists():
        raise FileExistsError('Choose a fresh --output; existing authoring decisions must not be overwritten')
    remaining=read(analysis/'remaining-work-plan.json')
    completed=read(analysis/'completed-work-classification.json')
    assert remaining['ledger_hashes']==completed['ledger_hashes']
    for fn,digest in remaining['ledger_hashes'].items():
        assert hashlib.sha256((ROOT/'data/verification'/fn).read_bytes()).hexdigest()==digest, fn
    rows=[]
    for status,collection in [('remaining',remaining['rows']),('implemented',completed['rows'])]:
        for x in collection:
            evidence=x.get('routing_evidence',{})
            reason=x.get('qualitative_reason') or (evidence.get('reason') if isinstance(evidence,dict) else None)
            reason=reason or ('기존 묶음의 포함 상태 의무: '+str(x.get('state_scope')))
            uid=x['id'];key=uid+'::contract_binding'
            requirements={key:{'kind':'contract_review',
                'question':'기록된 상태 의무와 차이를 각 계약 축 및 기존 소비 경로에 어떻게 연결하는가? '+reason,
                'resume_when':'해당 조항의 실제 원문과 포함 상태 범위에 맞는 선언 및 소비 경로를 확인하고 축별 값/해당 없음의 근거를 기록'}}
            contract={axis:{'state':'deferred','requires':[key]} for axis in B.AXES}
            question=x.get('qualitative_open_question') or x.get('specific_open_question')
            blockers=x.get('known_blockers') or []
            if question or blockers:
                source_key=uid+'::source_decision'
                requirements[source_key]={'kind':'source_decision','question':str(question or blockers),
                    'resume_when':'채택 판본 또는 명시적 GM 정책과 근거가 결정됨; 상충하는 원문은 그대로 보존'}
                contract['source_policy']['requires'].append(source_key)
            row={'schema':'rule-blueprint-v1','id':uid,'family':x['primary_family'],
                'source_text':x['source_text'],'qualitative_reason':reason,
                'source':x['source'],'registry':x['registry'],'ledger_status':status,
                'state_scope':x.get('scope') or x.get('state_scope'),
                'contract':contract,'requirements':requirements,
                'existing_native_evidence':x.get('recorded_implementation_evidence') or {
                    'runtime_refs':x.get('existing_runtime_refs',[]),
                    'static_references':x.get('static_code_references',[]),
                    'source_units':x.get('source_unit_candidates',[])},
                'binding_status':'authoring_contract_not_bound',
                'completion_credit':0}
            B.validate(row);rows.append(row)
    index=B.dependency_index(rows)
    assert len(rows)==2352 and len({x['id'] for x in rows})==2352
    families=[]
    for f in remaining['families']:
        for module in f['modules']:assert (ROOT/module).exists(),module
        families.append({'id':f['id'],'title':f['title'],'outcome':f['outcome'],
            'split_on':f['split_on'],'candidate_native_modules':f['modules'],
            'native_adapter_verified':False,
            'clause_ids':[x['id'] for x in rows if x['family']==f['id']]})
    result={'schema':'rule-blueprint-catalog-v1','scope':'Authoring slots, not normalized mechanics or new completion evidence',
        'baseline':remaining['baseline'],'ledger_hashes':remaining['ledger_hashes'],
        'architecture':{'definition':'Existing Rules and rule selection retain source authority',
          'acquisition':'acquired_features and state_grants retain source-owned actor state',
          'execution':'effect_contracts/effects retain native validation and dispatch',
          'instance':'effect_instances retains identity on authoritative family records',
          'lifetime':'effect_lifetimes and family event consumers retain expiry',
          'authoring':'rule_blueprints holds explicit unresolved contracts; never eval source prose'},
        'families':families,'rows':rows,'dependencies':index,
        'validation':{'unique_clauses':len(rows),'families':len(families),
          'ledger_implemented':sum(x['ledger_status']=='implemented' for x in rows),
          'authoring_bound':0,'completion_credit':0,
          'source_decisions':sum(v['requirement']['kind']=='source_decision' for v in index.values()),
          'source_ledger_unchanged':True}}
    write(output,result)
    print(json.dumps(result['validation'],ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('analysis',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'data/rule-blueprints.json')
    args=parser.parse_args();build(args.analysis,args.output)
