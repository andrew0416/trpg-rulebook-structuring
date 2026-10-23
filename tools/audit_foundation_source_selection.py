"""Exercise source identity lookup for every frozen selection reference.

This records connection evidence, not completion or gameplay certification.
Run with --write to replace only this audit in the existing canonical ledger.
"""
import json,re,sys
from collections import Counter
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules
from ruleset import ExcludedRuleSelection,UnresolvedRuleSelection


def audit():
    path=ROOT/'data/verification/category2-edge-work-plan.json';raw=path.read_bytes()
    document=json.loads(raw);foundation=document['foundation_discovery']
    unit=next(u for u in foundation['foundation_freeze']['units'] if u['id']=='source_policy.selection')
    profiles={name:Rules(str(ROOT),ruleset=name) for name in ('core','all')}
    rules=profiles['core'];rows=[];hashes={}
    previous=foundation.get('foundation_completion_audits',{}).get('source_policy.selection',{})
    annotations={json.dumps(row['reference'],sort_keys=True):{key:row[key] for key in ('required_selection_scope','source_disposition','consumer_evidence','selection_acceptance') if key in row} for row in previous.get('references',[])}
    for reference in unit['mandatory_acceptance_refs']:
        row={'reference':reference,'scope_status':'not_certified'}
        row.update(annotations.get(json.dumps(reference,sort_keys=True),{}))
        if 'requirement_ref' in reference:
            match=re.search(r'(input/[^:]+):([LR])(\d+)',reference['requirement_ref'])
            if not match:
                row['connection_status']='non_location_obligation';rows.append(row);continue
            file,kind,number=match.group(1),match.group(2),int(match.group(3))
        else:
            records=foundation
            for key in reference['collection'].split('.'):records=records[key]
            record=records[reference['index']];file=record['file'];kind='R' if 'record' in record else 'L'
            number=record.get('record',record.get('line',record.get('start')))
        if file not in hashes:hashes[file]=sha256((ROOT/file).read_bytes()).hexdigest()
        row['location']={'file':file,'kind':kind,'number':number};row['candidates']=[]
        for uid,entry in rules.selection.units.items():
            source=entry['source']
            if source.get('file')!=file.removeprefix('input/'):continue
            bounds=(source.get('record_span') or ([source['record']]*2 if 'record' in source else None)) if kind=='R' else source.get('lines')
            if not bounds or not bounds[0]<=number<=bounds[1]:continue
            candidate={'id':uid,'profile_results':{}}
            for profile,reader in profiles.items():
                try:
                    selected=reader.select_source_definition(uid,source={'file':file,'sha256':hashes[file]},supports_versions=True)
                    if reader.validate_source_selection(selected)!=selected:raise AssertionError('selection roundtrip changed')
                    outcome={'status':'selection_read_exercised','selected_id':selected['selected_id'],'version':selected['version'],'record_revalidated':True}
                except (ExcludedRuleSelection,UnresolvedRuleSelection) as exc:
                    outcome={'status':'explicit_selection_rejection','error_type':type(exc).__name__,'reason':str(exc)}
                candidate['profile_results'][profile]=outcome
            candidate.update(candidate['profile_results']['core'])
            row['candidates'].append(candidate)
        row['connection_status']='located_native_candidates' if row['candidates'] else 'no_located_native_identity'
        rows.append(row)
    result={'at':datetime.now(timezone.utc).isoformat(),'status':'connection_inventory_not_completion',
            'contract_sha256':foundation['foundation_freeze']['unit_contract_sha256'],
            'reference_count':len(rows),'references':rows,'current_source_sha256':hashes,
            'connection_counts':dict(Counter(r['connection_status'] for r in rows)),
            'profile_counts':{name:dict(Counter(c['profile_results'][name]['status'] for r in rows for c in r.get('candidates',[]))) for name in profiles},
            'acceptance_partition':previous.get('acceptance_partition',{}),
            'scenario_evidence':previous.get('scenario_evidence',{}),
            'limits':['Covering source locations identify candidates, not semantic equivalence or complete consumer coverage.',
                      'Current hashes exercise provenance checks; they do not certify source interpretation.',
                      'Missing native identity may use explicit authored registration; no automatic registration or name merging occurs.']}
    if '--write' in sys.argv:
        foundation.setdefault('foundation_completion_audits',{})['source_policy.selection']=result
        assert path.read_bytes()==raw
        path.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'connections':result['connection_counts'],'profiles':result['profile_counts']},sort_keys=True))

if __name__=='__main__':audit()
