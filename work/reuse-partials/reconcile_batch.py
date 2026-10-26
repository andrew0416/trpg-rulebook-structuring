"""Stage existing canonical ledgers from one reviewed batch specification.

Does not mutate production or decide whether source obligations are complete.
Use the existing hash-guarded publish.ps1 after reviewing the staged manifest.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from unittest.mock import patch
from acceptance_evidence import identity, log_results, verify_acceptance_evidence
import json, re, sys

R=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
PLAN='data/verification/category2-edge-work-plan.json'
CP='data/verification/category2-work-checkpoint.json'
PROGRESS='data/verification/category2-progress.json'
REGISTRIES={'core':('category2-core-clause-status.json','clause_mappings','clause_id'),
            'csv':('category2-csv-abilities-moves-status.json','rows','row_id'),
            'csv_moves':('category2-csv-abilities-moves-status.json','rows','row_id'),
            'csv_abilities':('category2-csv-abilities-moves-status.json','rows','row_id'),
            'csv-items':('category2-item-table-status.json','new_clauses','clause_id'),
            'csv-core':('category2-tabular-core-status.json','entries','id'),
            'class_csv':('category2-class-csv-clause-status.json','rows','id'),
            'optional':('category2-optional-clause-status.json','rows','clause_id'),
            'optional-additional':('category2-optional-additional-clause-status.json','rows','clause_id'),
            'class':('category2-class-clause-status.json','entries','source_clause_id')}

def digest(raw):return sha256(raw).hexdigest()
def object_hash(value):return digest(json.dumps(value,ensure_ascii=False,sort_keys=True).encode())
def read(name):return json.loads((R/name).read_text(encoding='utf-8-sig'))

def eligible_run_proofs(runs):
    """Cite actual PASS cases only from acceptance-eligible physical executions."""
    proofs=[]
    for run in runs:
        if run.get('acceptance_eligible') is False:continue
        passed_cases=run['cases'] if run['result']=='PASS' else [case for case,result in run['case_results'].items() if result=='ok']
        if not passed_cases:continue
        proof={key:run[key] for key in ('log','sha256','tests','seconds')}
        if run['result']!='PASS':proof['cases']=passed_cases
        proofs.append(proof)
    return proofs

def registry_included(row, registry):
    if registry == 'csv-core':
        return row['include_category2'] is True and row['denominator_contribution'] == 1
    if registry == 'class_csv':
        return row['include_category2'] is True and row.get('dedupe_target') is None
    if registry == 'class':
        return row['include_category2'] is True
    if registry in ('optional','optional-additional','csv-items'):
        return row['category2_in_scope'] is True
    return row['category2_included'] is True

def registry_status(row, registry):
    return row['status'] if registry in ('optional','optional-additional','class','csv-items','csv-core','class_csv') else row['category2_status']

def candidate_source_identity(details):
    """Keep preflight, reconciliation and references on one declared digest."""
    for field in ('source_sha256','source_row_sha256','cell_sha256','source_statement_sha256'):
        if details.get(field):
            return field,details[field]
    return None,None

def registry_source_digests(row, registry):
    if registry == 'csv-core':
        return {digest(row['statement'].encode('utf-8'))}
    if registry == 'class_csv':
        return {row['cell_sha256']}
    if registry == 'class':
        anchors=row['anchors']
        assert anchors,('missing class source anchor',row.get('source_clause_id'))
        return {anchor['sha256'] for anchor in anchors}
    if registry in ('optional','optional-additional'):
        sources=row['source']
        assert sources,('missing optional source',row.get('clause_id'))
        return {source['excerpt_sha256'] for source in sources}
    if registry == 'csv-items':
        sources=row['source']
        assert sources,('missing csv item source',row.get('clause_id'))
        return {source['raw_cells_sha256'] for source in sources}
    return {row['statement_sha256' if registry=='core' else 'source_row_sha256']}

def registry_source_reference(uid, row, registry, expected_digest):
    if registry == 'csv-core':
        numbers=[row['row']] if 'row' in row else [source['row'] for source in row['source_occurrences']]
        columns=row['columns']
        return dict(id=uid,file=row['source_file'],sha256=expected_digest,
                    blocks=[f"{row['source_file']}:R{number}:{columns[0]}-{columns[-1]}" for number in numbers],
                    columns=deepcopy(columns),source_file_sha256=row['source_sha256'])
    if registry == 'class_csv':
        return dict(id=uid,file=row['file'],sha256=row['cell_sha256'],
                    blocks=[f"{row['file']}:R{row['csv_record']}"],
                    source_file_sha256=row['file_sha256'],columns=deepcopy(row.get('columns',[])))
    if registry == 'class':
        anchor=next(anchor for anchor in row['anchors'] if anchor['sha256']==expected_digest)
        return dict(id=uid,file=anchor['file'],sha256=anchor['sha256'],
                    blocks=[f"{anchor['file']}:{anchor['start']}-{anchor['end']}"],
                    sources=deepcopy(row['anchors']),source_file_sha256=row['source_sha256'])
    if registry in ('optional','optional-additional'):
        source=next(source for source in row['source'] if source['excerpt_sha256']==expected_digest)
        return dict(id=uid,file=source['file'],sha256=source['excerpt_sha256'],
                    blocks=[f"{source['file']}:{source['start']}-{source['end']}"],
                    sources=deepcopy(row['source']))
    if registry == 'csv-items':
        source=next(source for source in row['source'] if source['raw_cells_sha256']==expected_digest)
        columns=source.get('columns',[])
        block=f"{source['file']}:{source['row']}"
        if columns:
            block+=f":{columns[0]}-{columns[-1]}"
        return dict(id=uid,file=source['file'],sha256=source['raw_cells_sha256'],
                    blocks=[block],sources=deepcopy(row['source']),
                    source_file_sha256=source.get('file_sha256'))
    return dict(id=uid,file=row['source_file'],sha256=row['source_sha256'],blocks=row.get('block_ids',[]))

def complete_registry_row(row, registry, details, ref, verification, at, clause_id=None):
    if verification.get('method') == 'existing_proof_only':
        # Current execution and retained coverage have different identities.
        row['reused_test_ids']=deepcopy(details['reused_test_ids'])
        row['retained_verification']=dict(record=ref,proof=deepcopy(verification['retained_proof']),
            new_game_test_count=0,new_game_execution_attempts=0,
            historical_named_pass_count=len(details['reused_test_ids']),
            obligation_mapping=deepcopy(verification['obligation_mapping'][clause_id]))
    if registry == 'class_csv':
        row.update(status='implemented',verified_at=at,
                   implementation_evidence=list(dict.fromkeys([*row.get('implementation_evidence',[]),ref])),
                   tests=deepcopy(details['tests']),
                   validation_result=details.get('validation_result') or
                                     (f"{verification['unique_tests']} unique direct tests passed; actual producer, consumer, lifetime and restoration paths reviewed."))
        for child in row.get('children',[]):
            child.update(status='implemented',
                         evidence=list(dict.fromkeys([*child.get('evidence',[]),ref])))
        return
    if registry == 'csv-items':
        row.update(status='implemented',producer=deepcopy(details['producers']),
                   consumer=deepcopy(details['consumers']),tests=deepcopy(details['tests']),
                   remaining=[],field_authority_evidence=deepcopy(details['field_authority']),
                   canonical_state_references=deepcopy(details['canonical_state_references']),
                   implementation_evidence=list(dict.fromkeys([*row.get('implementation_evidence',[]),ref])))
        for child in row.get('children',[]):
            child.update(status='implemented',
                         evidence=list(dict.fromkeys([*child.get('evidence',[]),ref])))
        return
    if registry == 'optional-additional':
        row.update(status='implemented',evidence_scope=ref,remaining=[],
                   producer=deepcopy(details['producers']),
                   consumer=deepcopy(details['consumers']),
                   tests=deepcopy(details['tests']),
                   field_authority_evidence=deepcopy(details['field_authority']),
                   canonical_state_references=deepcopy(details['canonical_state_references']))
        row['completion_evidence']={
            'fields':deepcopy(details['canonical_state_references']),
            'producer':deepcopy(details['producers']),
            'consumer':deepcopy(details['consumers']),
            'verification':{
                'record':ref,
                'tests':deepcopy(details['tests']),
                'logs':[run['log'] for run in verification['runs']],
            },
            'scope':details['obligation'],
        }
        evidence=list(dict.fromkeys([*details['tests'],ref]))
        for child in row.get('children',[]):
            child.update(implementation_verified=True,status='implemented',
                         evidence=list(dict.fromkeys([*child.get('evidence',[]),*evidence])))
        return
    common={k:deepcopy(details[k]) for k in
            ('field_authority','producers','consumers','tests','canonical_state_references')}
    row.update(common)
    if registry == 'class':
        obligations=list(row.get('category2_obligations',[]))
        for obligation in [details['obligation'],*details.get('category2_obligations',[])]:
            if obligation not in obligations:
                obligations.append(obligation)
        implementation=[*details['producers'],*details['consumers'],*details['canonical_state_references'],
                        *details.get('implementation_evidence',[]),ref]
        row.update(status='implemented',evidence_scope=ref,completion_evidence=ref,
                   verified_at=at,category2_obligations=obligations,
                   implementation_evidence=list(dict.fromkeys([*row.get('implementation_evidence',[]),*implementation])),
                   test_evidence=list(dict.fromkeys([*row.get('test_evidence',[]),*details['tests']])),
                   validation_result=details.get('validation_result') or
                                     (f"{verification['unique_tests']} unique direct and related tests passed; "
                                      "actual producer, consumer, lifetime and restoration paths reviewed."))
        for child in row.get('children',[]):
            child.update(status='implemented',
                         evidence=list(dict.fromkeys([*child.get('evidence',[]),ref])))
        return
    if registry in ('optional','csv-core'):
        row.update(status='implemented',evidence_scope=ref,remaining=[])
        if registry == 'csv-core':
            row.update(completion_credit=True,verified_at=at)
        row['completion_evidence']={
            'fields':deepcopy(details['canonical_state_references']),
            'producer':deepcopy(details['producers']),
            'consumer':deepcopy(details['consumers']),
            'verification':{
                'record':ref,
                'tests':deepcopy(details['tests']),
                'logs':[run['log'] for run in verification['runs']],
            },
            'scope':details['obligation'],
        }
        return
    row.update(category2_status='implemented',evidence_scope=ref)
    if registry=='core':row['category2_implemented']=True

def selected_name(row):
    return row.get('source_statement') or row.get('statement') or row.get('name')

def reviewed_file_name(reference):
    """Keep the locator in provenance, but fingerprint its containing file."""
    name=re.sub(r':[LR]?\d+(?:-[LR]?\d+)?$','',reference.split('#',1)[0])
    return candidate_file_path(name,'reviewed_files').as_posix()

def candidate_file_path(name, field, root=None):
    if not isinstance(name,str) or not name.strip():
        raise RuntimeError(f'candidate {field} path must be a non-empty string')
    path=PureWindowsPath(name)
    if (not path.parts or path.drive or path.root or '..' in path.parts
            or re.search(r'[\x00-\x1f<>:"|?*]',name)
            or any(part!=part.rstrip(' .') or PureWindowsPath(part).is_reserved() for part in path.parts)):
        raise RuntimeError(f'unsafe candidate {field} path: {name}')
    relative=Path(*path.parts)
    if root is not None and not (Path(root)/relative).resolve().is_relative_to(Path(root).resolve()):
        raise RuntimeError(f'candidate {field} path escapes root: {name}')
    return relative

def validate_notes(spec, repo_root=R):
    """Reject malformed note writes before staging any reconciliation output."""
    notes=spec.get('notes',{})
    if not isinstance(notes,dict):
        raise RuntimeError('candidate notes must be an object')
    for name,value in notes.items():
        path=candidate_file_path(name,'note',repo_root)
        if not isinstance(value,dict):
            raise RuntimeError(f'candidate note entry must be an object: {name}')
        mode=value.get('mode')
        if mode not in ('append','create'):
            raise RuntimeError(f'candidate note has invalid mode for {name}: {mode!r}')
        body=value.get('body')
        if not isinstance(body,str) or not body.strip():
            raise RuntimeError(f'candidate note has no non-empty body: {name}')
        target=Path(repo_root)/path
        if mode=='append' and not target.is_file():
            raise RuntimeError(f'candidate append note target does not exist: {name}')
        if mode=='create' and target.exists():
            raise RuntimeError(f'candidate create note target already exists: {name}')

def validate_candidate_shape(spec):
    repair=spec.get('repair_only',False)
    if type(repair) is not bool:
        raise RuntimeError('repair_only must be an explicit boolean')
    credit=spec.get('implementation_credit',0)
    if type(credit) is not int or credit not in (0,1):
        raise RuntimeError('implementation_credit must be integer 0 or 1')
    if credit and not spec.get('runtime_changes'):
        raise RuntimeError('implementation credit requires explicit runtime changes')
    if not isinstance(spec.get('id'),str) or not spec['id'].strip():
        raise RuntimeError('candidate has no non-empty id')
    retained=spec.get('existing_proof_only',False)
    if type(retained) is not bool:
        raise RuntimeError('existing_proof_only must be an explicit boolean')
    for field in ('native_paths','foundation_ids','changes','reviewed_files','logs','required_test_modules'):
        values=spec.get(field)
        empty_allowed=(repair and field=='native_paths') or (retained and field in ('logs','required_test_modules'))
        if not isinstance(values,list) or (not values and not empty_allowed) or any(not isinstance(value,str) or not value.strip() for value in values):
            raise RuntimeError(f'candidate has no non-empty string list: {field}')
    for field in ('runtime_changes','test_changes','source_corrections','staged_artifacts'):
        if not isinstance(spec.get(field),list):
            raise RuntimeError(f'candidate field must be a list: {field}')
    for field in ('selection','completed','deferred'):
        if not isinstance(spec.get(field),dict):
            raise RuntimeError(f'candidate {field} must be an object')
    for uid,details in spec['completed'].items():
        if not isinstance(details,dict) or details.get('registry') not in REGISTRIES:
            raise RuntimeError(f'candidate completed clause has unknown registry: {uid}')
        if not isinstance(details.get('obligation'),str) or not details['obligation'].strip():
            raise RuntimeError(f'candidate completed clause requires obligation: {uid}')
        fields=('tests',) if details['registry']=='class_csv' else (
            'field_authority','producers','consumers','tests','canonical_state_references')
        for field in fields:
            values=details.get(field)
            if (not isinstance(values,list) or (not values and not (retained and field=='tests'))
                    or any(not isinstance(value,str) or not value.strip() for value in values)):
                raise RuntimeError(f'candidate completed clause requires {field} string list: {uid}')
    queried=spec['selection'].get('queried_clause_ids')
    if (not isinstance(queried,list) or any(not isinstance(uid,str) or not uid.strip() for uid in queried)
            or len(queried)!=len(set(queried)) or not set(spec['completed'])<=set(queried)):
        raise RuntimeError('candidate selection.queried_clause_ids must uniquely include completed clause IDs')
    if any(module.endswith('.py') or re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*',module) is None
           for module in spec['required_test_modules']):
        raise RuntimeError('required_test_modules must contain module names, not file paths (for example tools.test_owner)')
    withdrawn=spec.get('withdrawn_test_assumptions',{})
    if not isinstance(withdrawn,dict):
        raise RuntimeError('candidate withdrawn_test_assumptions must be an object')
    if withdrawn:
        required={identity(case) for details in spec['completed'].values() for case in details.get('tests',[])}
        explicit_repair=repair and 'required_test_ids' in spec
        if explicit_repair:
            values=spec['required_test_ids']
            if not isinstance(values,list) or not values or any(not isinstance(case,str) or not case.strip() for case in values):
                raise RuntimeError('withdrawn tests require a non-empty repair required_test_ids string list')
            required.update(identity(case) for case in values)
        for case,decision in withdrawn.items():
            if not isinstance(case,str) or not case.strip():
                raise RuntimeError('withdrawn test ID must be a non-empty string')
            if not isinstance(decision,dict):
                raise RuntimeError('withdrawn test decision must be an object: '+case)
            for field in ('replacement','reason'):
                if not isinstance(decision.get(field),str) or not decision[field].strip():
                    raise RuntimeError('withdrawn test requires a non-empty string '+field+': '+case)
            replacement=identity(decision['replacement'])
            if identity(case)==replacement:
                raise RuntimeError('withdrawn test cannot replace itself: '+case)
            if identity(case) in required:
                raise RuntimeError('withdrawn test is still required: '+case)
            if explicit_repair and replacement not in required:
                raise RuntimeError('withdrawn test replacement must be required by the repair: '+case)
    validate_new_shared_features(spec)

    if repair:
        if spec['completed'] or spec['deferred'] or spec.get('traversal') != []:
            raise RuntimeError('repair_only requires empty completed, deferred and traversal')
        if spec['selection'].get('queried_clause_ids') != [] or spec['selection'].get('admitted_clause_ids') != []:
            raise RuntimeError('repair_only cannot claim queried or admitted original clauses')
        if spec.get('shared_feature_credit',0) != 0:
            raise RuntimeError('repair_only cannot create a shared-feature credit')
    elif not spec['completed']:
        raise RuntimeError('empty completion requires explicit repair_only=true')
    proposed=spec.get('proposed_delta',{})
    if not isinstance(proposed,dict):
        raise RuntimeError('candidate proposed_delta must be an object')
    for field in ('clauses','completion'):
        if field in proposed and (type(proposed[field]) is not int or proposed[field]!=len(spec['completed'])):
            raise RuntimeError(f'proposed_delta.{field} must equal the completed candidate count (zero for repair_only)')
    reporting=spec['selection'].get('reporting',{})
    if not isinstance(reporting,dict):
        raise RuntimeError('candidate reporting must be an object')
    if reporting:
        registries={details.get('registry') for details in spec['completed'].values()}
        section=next(iter(registries)) if len(registries)==1 else reporting.get('section')
        if section in ('core','class'):
            if registries and registries!={section}:
                raise RuntimeError('ordered reporting requires one core or class registry')
            initial=118 if section=='core' else 221
            for field,expected in (('section',section),('section_initial',initial),('section_initial_remaining',initial),('overall_total',2352)):
                if field in reporting and (type(reporting[field]) is not type(expected) or reporting[field]!=expected):
                    raise RuntimeError(f'incorrect reporting scope: {field} must be {expected!r}')
    if spec.get('status')=='prepared_unexecuted':
        for field in ('game_runs','test_executions','completion_credit','implementation_credit','shared_feature_credit','latest_valid_pass_count'):
            if field in spec and (type(spec[field]) is not int or spec[field]!=0):
                raise RuntimeError(f'prepared_unexecuted requires {field}=0')
        actual=spec.get('actual_credit',{})
        if not isinstance(actual,dict) or any(type(value) is not int or value!=0 for value in actual.values()):
            raise RuntimeError('prepared_unexecuted requires zero actual_credit')
        if spec.get('execution_history'):
            raise RuntimeError('prepared_unexecuted cannot have execution_history')
        required_lists={}
        for field in ('required_test_ids','first_run_required_test_ids'):
            values=spec.get(field)
            if not isinstance(values,list) or not values or any(not isinstance(value,str) or not value.strip() for value in values):
                raise RuntimeError(f'prepared_unexecuted requires a non-empty test ID list: {field}')
            ids=[identity(value) for value in values]
            if len(ids)!=len(set(ids)):
                raise RuntimeError(f'prepared_unexecuted has duplicate test IDs: {field}')
            required_lists[field]=set(ids)
        required=required_lists['required_test_ids']
        # After execution, first-run requirements are history and may differ from the final set.
        if required_lists['first_run_required_test_ids']!=required:
            raise RuntimeError('prepared_unexecuted first-run test IDs must match required_test_ids')
        if not {identity(case) for detail in spec['completed'].values() for case in detail.get('tests',[])}<=required:
            raise RuntimeError('prepared_unexecuted required_test_ids omit completed candidate tests')
        if 'mandatory_unique_ids' in spec and (type(spec['mandatory_unique_ids']) is not int or spec['mandatory_unique_ids']!=len(required)):
            raise RuntimeError('prepared_unexecuted mandatory_unique_ids differs from required_test_ids')
    if retained:
        if repair or any(spec[field] for field in ('runtime_changes','test_changes','source_corrections','logs')):
            raise RuntimeError('existing_proof_only requires no repair, runtime, test, source changes or current logs')
        if any(spec.get(field,0)!=0 for field in ('implementation_credit','shared_feature_credit')):
            raise RuntimeError('existing_proof_only cannot earn implementation or shared-feature credit')
        if spec.get('withdrawn_test_assumptions') or spec.get('retained_failure_logs'):
            raise RuntimeError('existing_proof_only cannot alter current-run failure history')
        if any(not name.startswith('vaults/') for name in spec.get('notes',{})):
            raise RuntimeError('existing_proof_only note writes are restricted to vault notes')
        for name in spec['staged_artifacts']:
            if (not isinstance(name,str) or Path(name).drive or '..' in Path(name).parts
                    or not name.startswith(('data/verification/','vaults/'))):
                raise RuntimeError('existing_proof_only stages verification records or vault notes only')
        for details in spec['completed'].values():
            if details.get('tests')!=[] or not details.get('reused_test_ids'):
                raise RuntimeError('existing_proof_only requires empty current tests and explicit reused_test_ids')
            if details.get('remaining_implementation_obligations') or details.get('mandatory_unanswered_questions'):
                raise RuntimeError('existing_proof_only has unresolved completion obligations')


def validate_candidate_metadata(spec, *, repo_root=R, stage=None):
    """Read-only gate; an explicit stage also checks every declared input file."""
    validate_candidate_shape(spec)
    plan=json.loads((Path(repo_root)/PLAN).read_text(encoding='utf-8-sig'))
    sweep_ids={row['id'] for row in plan.get('latest_reassessment',{}).get('ready_sweep',{}).get('rows',[])}
    for uid,decision in spec['deferred'].items():
        if uid in sweep_ids:
            for field in ('observed','prerequisite','resume_when'):
                if not isinstance(decision.get(field),str) or not decision[field].strip():
                    raise RuntimeError('deferred legacy sweep clause requires non-empty '+field+': '+uid)
    foundations=set(plan['foundation_discovery']['foundation_freeze']['unit_ids'])
    unknown=set(spec['foundation_ids'])-foundations
    if unknown:
        raise RuntimeError('Unknown original foundation: '+', '.join(sorted(unknown)))
    validate_notes(spec,repo_root)
    if stage is not None:
        for name in spec.get('notes',{}):candidate_file_path(name,'note',stage)
        baseline_path=Path(stage)/'baseline.json'
        if not baseline_path.is_file():
            raise RuntimeError('candidate stage requires baseline.json dictionary')
        baseline=json.loads(baseline_path.read_text(encoding='utf-8-sig'))
        if not isinstance(baseline,dict) or any(
                not isinstance(name,str) or (value is not None and
                (not isinstance(value,str) or re.fullmatch(r'[a-f0-9]{64}',value) is None))
                for name,value in baseline.items()):
            raise RuntimeError('candidate baseline.json must map file paths to SHA256 or null')
        for name in baseline:candidate_file_path(name,'baseline',repo_root)
    for field in ('runtime_changes','test_changes','source_corrections','staged_artifacts'):
        for name in spec[field]:
            path=candidate_file_path(name,field,repo_root)
            if stage is not None:
                candidate_file_path(name,field,stage)
                if not (Path(stage)/path).is_file():
                    raise RuntimeError(f'candidate {field} missing staged input file: {name}')
    if stage is not None and spec.get('execution_history'):
        recorded={row.get('metadata') for row in spec['execution_history']}
        for name in spec['staged_artifacts']:
            if not name.endswith('.json'):continue
            value=json.loads((Path(stage)/name).read_text(encoding='utf-8-sig'))
            if (isinstance(value,dict) and any(key in value for key in
                    ('runtime_test_data_sha256_before','frozen_inputs')) and name not in recorded):
                raise RuntimeError('candidate physical metadata missing from execution_history: '+name+
                                   '; keep collection-only metadata as separate support evidence')
    generated={PLAN,CP,PROGRESS}
    generated.update('data/verification/'+REGISTRIES[details['registry']][0] for details in spec['completed'].values())
    staged_names={name for field in ('runtime_changes','test_changes','source_corrections','staged_artifacts')
                  for name in spec[field]}
    for reference in spec['reviewed_files']:
        name=reviewed_file_name(reference)
        if name in generated:
            raise RuntimeError('candidate reviewed_files must omit generated reconciliation files: '+reference)
        root=stage if stage is not None and name in staged_names else repo_root
        if (stage is not None or name not in staged_names) and not (Path(root)/name).is_file():
            raise RuntimeError('candidate reviewed_files missing containing file: '+reference)
    if spec.get('repair_only',False):return
    documents={}
    for uid,details in spec['completed'].items():
        registry=details['registry'];filename,key,identity=REGISTRIES[registry]
        if filename not in documents:
            document=json.loads((Path(repo_root)/'data/verification'/filename).read_text(encoding='utf-8-sig'))
            documents[filename]={row[identity]:row for row in document[key]}
        row=documents[filename].get(uid)
        label={'csv-core':'CSV core'}.get(registry,registry)
        if row is None or not registry_included(row,registry):
            raise RuntimeError(f'candidate completed clause must name an included {label} registry ID: {uid!r}')
        source_field,source_digest=candidate_source_identity(details)
        if source_digest not in registry_source_digests(row,registry):
            raise RuntimeError(f'candidate {label} source digest does not match the registry source: '
                               f'{uid!r}; selected {source_field}={source_digest!r}')
    registries={details.get('registry') for details in spec['completed'].values()}
    section=next(iter(registries)) if len(registries)==1 else spec['selection'].get('reporting',{}).get('section')
    cursors={field:spec[field] for field in ('next_clause_id','next_cursor') if spec.get(field) is not None}
    if section!='class':return
    filename,key,identity=REGISTRIES['class']
    document=json.loads((Path(repo_root)/'data/verification'/filename).read_text(encoding='utf-8-sig'))
    rows={row[identity]:row for row in document[key]}
    for field,uid in cursors.items():
        row=rows.get(uid) if isinstance(uid,str) else None
        if (row is None or uid in spec['completed'] or not registry_included(row,'class')
                or registry_status(row,'class') not in ('incomplete','known-rule-choice')):
            raise RuntimeError(f'candidate {field} must name an unfinished included class registry ID: {uid!r}')
    if len(set(cursors.values()))>1:
        raise RuntimeError('candidate next_cursor must match next_clause_id')


def validate_new_shared_features(spec):
    records=spec.get('new_shared_features',[]);credit=spec.get('shared_feature_credit',0)
    if not isinstance(records,list) or type(credit) is not int or credit!=len(records):
        raise RuntimeError('shared_feature_credit must equal the explicit new shared-feature record count')
    if records and (spec.get('repair_only') or spec.get('existing_proof_only') or spec.get('implementation_credit')!=1):
        raise RuntimeError('new shared features require a current implementation; repairs and retained proof cannot earn credit')
    fields={'id','contract','runtime_paths','actual_consumers','completed_consumers','waiting_consumers','source_references','tests','vault_note'}
    ids=set()
    for record in records:
        if not isinstance(record,dict) or set(record)!=fields:
            raise RuntimeError('new shared-feature record requires contract, runtime, source consumers, tests and vault note')
        for field in ('id','contract','vault_note'):
            if not isinstance(record[field],str) or not record[field].strip():
                raise RuntimeError('empty shared-feature field: '+field)
        if record['id'] in ids or record['id'] in spec.get('extends_shared_feature_ids',[]):
            raise RuntimeError('duplicate or already extended shared-feature id: '+record['id'])
        ids.add(record['id'])
        for field in ('runtime_paths','actual_consumers','completed_consumers','waiting_consumers','tests'):
            values=record[field]
            if (not isinstance(values,list) or (not values and field not in ('completed_consumers','waiting_consumers'))
                    or any(not isinstance(value,str) or not value.strip() for value in values) or len(values)!=len(set(values))):
                raise RuntimeError('invalid shared-feature string list: '+field)
        done=set(record['completed_consumers']);waiting=set(record['waiting_consumers'])
        if not done|waiting or done & waiting or not done<=spec['completed'].keys() or not waiting<=spec['deferred'].keys():
            raise RuntimeError('shared-feature source consumers must match completed or deferred originals')
        refs=record['source_references']
        if (not isinstance(refs,list) or any(not isinstance(ref,dict) or set(ref)!={'id','sha256'}
                or not isinstance(ref['id'],str) or not isinstance(ref['sha256'],str)
                or not re.fullmatch('[0-9a-f]{64}',ref['sha256']) for ref in refs)
                or len(refs)!=len(done|waiting) or {ref['id'] for ref in refs}!=done|waiting):
            raise RuntimeError('shared-feature source references must pin every consumer exactly once')
        for name in [*record['runtime_paths'],record['vault_note']]:
            if Path(name).is_absolute() or Path(name).drive or '..' in Path(name).parts or '\\' in name:
                raise RuntimeError('unsafe shared-feature path: '+name)
        if not record['vault_note'].startswith('vaults/') or not set(record['runtime_paths'])<=set(spec['runtime_changes']):
            raise RuntimeError('shared-feature owner must change and its contract must have a vault note')
        required={identity(case) for details in spec['completed'].values() for case in details['tests']}
        if not {identity(case) for case in record['tests']}<=required:
            raise RuntimeError('shared-feature tests must be included in the required completed-clause checks')


def shared_feature_count(registry):
    features=registry['features'];ids=[record['id'] for record in features]
    assert all(isinstance(uid,str) and uid.strip() for uid in ids) and len(ids)==len(set(ids)), 'duplicate shared-feature registry id'
    assert type(registry['count']) is int and registry['count']==len(features), 'shared-feature registry count mismatch'
    return len(features)


def resolve_shared_feature_consumers(features,completed,reference):
    """Close only previously waiting consumers accepted in this batch."""
    result=deepcopy(features);completed=set(completed)
    for record in result:
        waiting=record.get('waiting_consumers',[])
        resolved=[uid for uid in waiting if uid in completed]
        if not resolved:continue
        record['waiting_consumers']=[uid for uid in waiting if uid not in completed]
        record['completed_consumers']=list(dict.fromkeys([*record.get('completed_consumers',[]),*resolved]))
        record['latest_consumer_resolution']=reference
    return result


def new_shared_feature_records(spec,batch,rows,registry,read):
    """Bind reviewed contracts to the existing source and actual-run evidence."""
    validate_new_shared_features(spec)
    reviewed={re.sub(r':R?\d+$','',name.split('#',1)[0]) for name in batch['current_file_hashes']}
    latest={identity(case):run.get('case_results',{}).get(case,'ok' if run['result']=='PASS' else 'FAILED')
            for run in batch['verification']['runs'] for case in run['cases']}
    records=[]
    for value in spec.get('new_shared_features',[]):
        record=deepcopy(value);sources=[]
        for reference in record['source_references']:
            uid=reference['id'];row=rows[uid]
            assert registry_included(row,registry), ('excluded shared-feature consumer',uid)
            assert reference['sha256'] in registry_source_digests(row,registry), ('shared-feature source mismatch',uid)
            if uid in record['waiting_consumers']:
                assert registry_status(row,registry) in ('incomplete','known-rule-choice'), ('completed waiting consumer',uid)
            sources.append(registry_source_reference(uid,row,registry,reference['sha256']))
        for name in [*record['runtime_paths'],record['vault_note'],*(ref['file'] for ref in sources)]:
            assert name in reviewed and read(name).strip(), ('shared-feature file must exist and be reviewed',name)
        assert all(latest.get(identity(case))=='ok' for case in record['tests']), 'shared-feature tests require actual latest passing evidence'
        record.update(source_references=sources,status='implemented_and_verified',at=batch['at'],
                      canonical_reference=PLAN+'#latest_reassessment.'+spec['id']+'_completion',checks=deepcopy(batch['verification']))
        records.append(record)
    return records


def case_identity(case):
    return 'tools.'+case if case.startswith('test_category2_') else case


def verify_retained_proof(spec, stage, root):
    """Admit reviewed historical case proofs, without executing or relabeling them.

    The hashed review owns the semantic impact decision. This guard checks its
    exact current/archived inputs, real named outcomes and obligation mapping.
    """
    if not spec.get('existing_proof_only'):
        return None
    def require(condition,message):
        if not condition:raise RuntimeError(message)
    def relative(name):
        require(isinstance(name,str) and bool(name) and not Path(name).is_absolute()
                and not Path(name).drive and '..' not in Path(name).parts,'unsafe retained proof path')
        return name
    def checked(path,expected):
        require(isinstance(expected,str) and re.fullmatch('[a-f0-9]{64}',expected),'missing retained input SHA256')
        raw=path.read_bytes()
        require(digest(raw)==expected,'retained input SHA256 mismatch: '+str(path))
        return raw
    reference=spec.get('retained_proof',{})
    proof_path=relative(reference.get('path'))
    require(proof_path.startswith('data/verification/') and proof_path in spec['staged_artifacts'],
            'retained proof must be an explicit staged verification record')
    proof=json.loads(checked(Path(stage)/proof_path,reference.get('sha256')).decode('utf-8-sig'))
    inputs=proof.get('runtime_test_source_sha256')
    require(isinstance(inputs,dict) and bool(inputs),'retained proof has no current input fingerprints')
    for name,expected in inputs.items():checked(Path(root)/relative(name),expected)
    protected=deepcopy(inputs)
    impact=reference.get('impact_review',{})
    require(isinstance(impact.get('basis'),str) and bool(impact['basis'].strip())
            and bool(impact.get('historical_inputs')),'retained proof has no change-impact basis')
    for item in impact['historical_inputs']:
        checked(Path(item['path']),item.get('sha256'))
    require(proof.get('stable_read_only_inputs') is True and proof.get('new_game_test_count')==0
            and proof.get('new_game_test_ids')==[],'retained proof is not existing-evidence-only')
    require(not proof.get('remaining_implementation_obligations') and not proof.get('mandatory_unanswered_questions'),
            'retained proof has unresolved completion obligations')
    # Use the canonical reporter's existing parser. It validates all original
    # outcomes/counts, including failures, before selecting the named successes.
    from importlib.util import module_from_spec,spec_from_file_location
    module_spec=spec_from_file_location('_retained_proof_reporter',Path(root)/'tools/report_category2_progress.py')
    reporter=module_from_spec(module_spec);module_spec.loader.exec_module(reporter)
    runs=[];passed=set()
    for item in proof.get('reused_evidence',[]):
        log=relative(item.get('log'));raw=checked(Path(root)/log,item.get('raw_sha256'))
        protected[log]=item['raw_sha256']
        body=raw.decode('utf-8-sig');lines=body.splitlines();selected=[]
        for named in item.get('named_pass',[]):
            line=named.get('line');text=named.get('text')
            require(type(line) is int and 0<line<=len(lines) and lines[line-1]==text,
                    'retained named PASS line mismatch: '+log)
            match=re.fullmatch(r'(test_\w+) \((\w+(?:\.\w+){2,})\) \.\.\. ok',text)
            require(match is not None and match[1]==match[2].rsplit('.',1)[-1],
                    'retained line is not an actual named PASS: '+log)
            selected.append(case_identity(match[2]))
        require(bool(selected) and len(set(selected))==len(selected),'duplicate or empty retained case scope')
        require(reporter._verified_test_ids(body,selected)==set(selected),'invalid historical run or named PASS scope: '+log)
        require(not passed.intersection(selected),'duplicate retained test identity across logs')
        passed.update(selected)
        summary=re.search(r'Ran (\d+) tests? in ([\d.]+)s',body)
        terminal=re.search(r'\n(OK|FAILED)(?: \(([^\r\n]+)\))?\s*(?:UTC end [^\r\n]+\s*)?\Z',body)
        run=dict(log=log,sha256=item['raw_sha256'],tests=int(summary[1]),seconds=float(summary[2]),
                 result='PASS' if terminal[1]=='OK' else 'FAILED',cases=selected,
                 named_pass=deepcopy(item['named_pass']),historical=True)
        if 'historical_run_summary' in item:
            historical=item['historical_run_summary'];counts=dict(re.findall(r'(failures|errors)=(\d+)',terminal[2] or ''))
            require(historical.get('tests')==run['tests'] and historical.get('success') is (run['result']=='PASS')
                    and all(historical.get(key,0)==int(counts.get(key,0)) for key in ('failures','errors')),
                    'historical whole-run summary contradicts raw outcomes: '+log)
            run['historical_run_summary']=deepcopy(historical)
        if item.get('manifest'):
            manifest=relative(item['manifest']);checked(Path(root)/manifest,item.get('manifest_sha256'))
            protected[manifest]=item['manifest_sha256']
            run.update(manifest=manifest,manifest_sha256=item['manifest_sha256'])
        runs.append(run)
    required=set();mapping=reference.get('obligation_mapping',{})
    require(set(mapping)==set(spec['completed']),'retained obligation map differs from completed clauses')
    for uid,details in spec['completed'].items():
        ids=[case_identity(case) for case in details['reused_test_ids']]
        require(len(set(ids))==len(ids) and set(ids)<=passed,'missing or duplicate retained named PASS: '+uid)
        required.update(ids)
        entry=mapping[uid];requirements=entry.get('requirements',[])
        require(entry.get('source_obligation')==details['obligation'] and bool(requirements),
                'missing retained source obligation mapping: '+uid)
        mapped=set()
        for requirement in requirements:
            require(bool(requirement.get('obligation')) and bool(requirement.get('test_ids')),
                    'empty retained mandatory obligation mapping: '+uid)
            mapped.update(case_identity(case) for case in requirement['test_ids'])
        require(mapped==set(ids),'retained mandatory obligation coverage mismatch: '+uid)
        paths=[value.split('#',1)[0] for field in ('producers','consumers') for value in details[field]]
        paths += ['tools/'+case.removeprefix('tools.').rsplit('.',2)[0]+'.py' for case in ids]
        paths.append(re.sub(r':\d+(?:-\d+)?$','',details['source']))
        require(all(name in inputs for name in paths),'retained consumer/source/test missing current SHA: '+uid)
    require(required==passed,'retained proof contains unassigned named coverage')
    def destination_key(name):return str((Path(root)/name).resolve()).casefold()
    protected={destination_key(name):expected for name,expected in protected.items()}
    for name in spec['staged_artifacts']:
        if destination_key(name) in protected:checked(Path(stage)/name,protected[destination_key(name)])
    require(not {destination_key(name) for name in spec.get('notes',{})}.intersection(protected),
            'retained evidence inputs cannot be replaced by candidate notes')
    return dict(method='existing_proof_only',retained_proof=dict(path=proof_path,sha256=reference['sha256']),
                new_game_test_count=0,new_game_execution_attempts=0,historical_named_pass_count=len(passed),
                retained_runs=runs,current_input_sha256=deepcopy(inputs),impact_review=deepcopy(impact),
                current_input_scope='Canonical pre-publication inputs checked at admission; historical inputs remain separately pinned.',
                obligation_mapping=deepcopy(mapping))


def main(stage, candidate, *, repo_root=R, evidence_repo_root=None):
    """Reconcile a candidate path or object into an explicit staging directory."""
    S=Path(stage).resolve();R=Path(repo_root).resolve()
    spec=deepcopy(candidate) if isinstance(candidate,dict) else json.loads(Path(candidate).read_text(encoding='utf-8-sig'))
    repair=spec.get('repair_only',False)
    validate_candidate_metadata(spec,repo_root=R,stage=S)
    retained=verify_retained_proof(spec,S,R)
    references=[row['metadata'] for row in spec.get('execution_history',[]) if row.get('metadata')]
    references += [name for name in spec.get('staged_artifacts',[]) if name.endswith('.json')]
    references += [str(Path(name).with_suffix('.json')) for name in spec['logs']
                   if (S/Path(name).with_suffix('.json')).is_file()]
    physical=False
    for name in dict.fromkeys(references):
        meta=json.loads((S/name).read_text(encoding='utf-8-sig'))
        physical |= isinstance(meta,dict) and any(key in meta for key in ('runtime_test_data_sha256_before','frozen_inputs'))
    physical_root=(R if evidence_repo_root is None else Path(evidence_repo_root).resolve()) if physical else None
    evidence=verify_acceptance_evidence(S,spec,physical_root) if physical else None
    physical_runs={run['raw_log']:run for run in evidence['runs']} if evidence else {}
    case_key=identity if physical else case_identity
    def read(name):return json.loads((R/name).read_text(encoding='utf-8-sig'))
    base=json.loads((S/'baseline.json').read_text(encoding='utf-8-sig'));names=[]
    def stage(name,raw):
        name=Path(name).as_posix();dest=R/name
        assert not Path(name).is_absolute() and '..' not in Path(name).parts,name
        current=digest(dest.read_bytes()) if dest.is_file() else None
        assert base.get(name,current)==current,('concurrent change',name)
        base[name]=current;target=S/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
        if name not in names:names.append(name)
    def save(name,value):stage(name,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    staged_inputs=[]
    for name in [*spec.get('runtime_changes',[]),*spec.get('test_changes',[]),
                 *spec.get('source_corrections',[]),*spec.get('staged_artifacts',[])]:
        name=Path(name).as_posix()
        if name in staged_inputs:continue
        source=S/name
        assert source.is_file(),('missing staged input',name)
        stage(name,source.read_bytes());staged_inputs.append(name)
    def read_overlay(name):
        name=Path(name).as_posix();path=S/name if name in names else R/name
        return json.loads(path.read_text(encoding='utf-8-sig'))
    p,c=read(PLAN),read(CP);v=p['latest_reassessment'];sweep=v['ready_sweep']
    before=spec['completed_before'];assert p['overall_completed']==c['completed']==before
    assert c['architecture_review']['controller']['suspension']['paused']
    protected={'architecture_review':object_hash(c['architecture_review']),
               'foundation_discovery':object_hash(p['foundation_discovery']),
               'reuse40':object_hash(v['whole_rule_template_audit']['reuse_elements_progress']),
               'baseline95':p['post_foundation_reuse']['itemized_audit']['baseline_sha256'],
               'entrypoint':digest((R/'엔트리포인트.md').read_bytes()),
               'instructions':digest((R/'vaults/작업지시.md').read_bytes())}
    at=datetime.now(timezone.utc).isoformat();key=spec['id'];ref=PLAN+'#latest_reassessment.'+key+'_completion'
    assert key+'_completion' not in v,'batch already recorded'
    runs=[];latest={}
    for name in physical_runs if physical else spec['logs']:
        raw=(S/name).read_bytes();body=raw.decode('utf-8-sig')
        match=re.search(r'Ran (\d+) tests? in ([\d.]+)s',body);assert match,name
        if physical:
            proof=physical_runs[name]
            assert digest(raw)==proof['raw_log_sha256'],('physical log changed after validation',name)
            case_results,passed,failures,errors=log_results(body)
            cases=list(case_results)
            assert passed==(not failures and not errors),name
        else:
            # unittest may emit ResourceWarning blocks between a case header and its
            # trailing ``ok``.  The final runner status and Ran-count remain the
            # authority; collect case identities from their stable header instead.
            headers=list(re.finditer(r'^test_\w+ \(([-\w.]+)\) \.\.\.',body,re.M))
            cases=[];case_results={};subtest_parent_results=set()
            for index,header in enumerate(headers):
                case=header[1]
                case='tools.'+case if case.startswith('test_category2_') else case
                end=headers[index+1].start() if index+1<len(headers) else len(body)
                segment=body[header.end():end].split('\n'+'='*70,1)[0]
                result=re.search(r'^[ \t]*(ok|FAIL|ERROR)[ \t]*\r?$',segment,re.M)
                # A failing unittest subTest prints each failing parameterized
                # occurrence instead of a final parent ERROR/FAIL line.
                subresults=re.findall(r'^[ \t]+'+re.escape(header[1].rsplit('.',1)[-1])+r' \('+re.escape(header[1])+r'\) \([^\r\n]*\) \.\.\. (FAIL|ERROR)[ \t]*\r?$',segment,re.M)
                status=('ERROR' if 'ERROR' in subresults else 'FAIL') if subresults else result[1] if result else None
                assert status,('missing actual case result',name,case)
                if case in case_results:
                    # unittest repeats the parent header when a later parent error
                    # follows failing subTests. It is still one invocation (Ran).
                    assert cases[-1]==case and case in subtest_parent_results and not subresults and status in ('FAIL','ERROR'),('duplicate case in one run',name,case)
                    case_results[case]='ERROR' if 'ERROR' in (case_results[case],status) else 'FAIL'
                    subtest_parent_results.remove(case)
                else:
                    cases.append(case);case_results[case]=status
                    if subresults:subtest_parent_results.add(case)
            assert len(cases)==int(match[1]),name
            status_body=body.rstrip()
            # Timed runners append one explicit UTC footer after unittest's status.
            # Keep the original bytes as evidence and remove only that validated
            # footer for status detection; arbitrary trailing output stays invalid.
            footer=re.search(r'\r?\nUTC end ([^\r\n]+)\Z',status_body)
            if footer:
                ended_at=datetime.fromisoformat(footer[1])
                assert ended_at.utcoffset() is not None and ended_at.utcoffset().total_seconds()==0,('non-UTC runner footer',name)
                status_body=status_body[:footer.start()].rstrip()
            passed=bool(re.search(r'(?:^|\n)OK\Z',status_body))
            assert passed or re.search(r'\nFAILED \([^\n]*\)\Z',status_body),name
            assert passed==all(value=='ok' for value in case_results.values()),name
        log_path=name if name.startswith('data/verification/') else 'data/verification/'+name
        run=dict(log=log_path,sha256=digest(raw),tests=int(match[1]),seconds=float(match[2]),result='PASS' if passed else 'FAILED',cases=cases)
        if not passed:run['case_results']=case_results
        runs.append(run)
        if physical:
            run.update(actual_original_test_calls=proof['actual_original_test_calls'],
                       loader_error_count=proof['loader_error_count'],loader_errors=proof['loader_errors'],
                       unexecuted_requested_ids=proof['unexecuted_requested_ids'],
                       acceptance_eligible=proof['acceptance_eligible'])
            latest.update({case_key(case):status for case,status in case_results.items()
                           if case not in proof['loader_errors']})
            latest.update({case_key(case):'unexecuted' for case in proof['unexecuted_requested_ids']})
            if not proof['acceptance_eligible']:
                for case in [*case_results,*proof['unexecuted_requested_ids']]:
                    if case not in proof['loader_errors']:latest[case_key(case)]='ineligible'
        else:
            latest.update(case_results)
        stage(runs[-1]['log'],raw)
    # Preserve failed original runs, but accept only an actually observed final
    # pass for every case. A narrow repair rerun must not require rerunning the
    # unaffected passes or manufacturing an all-OK replacement log.
    # An explicitly disproven test assumption may be withdrawn after a real
    # replacement passes. Preserve its failed original, count every invocation,
    # and never use that withdrawn case to support an original clause.
    observed_unique_tests=len(latest)
    withdrawn=[]
    required_cases={case_key(case)
                    for details in spec['completed'].values() for case in details['tests']}
    explicit_repair=repair and physical and 'required_test_ids' in spec
    if explicit_repair:
        required_cases.update(case_key(case) for case in spec['required_test_ids'])
    for case,decision in spec.get('withdrawn_test_assumptions',{}).items():
        case=case_key(case);replacement=case_key(decision['replacement'])
        # A reviewed wrong PASS can be retired only from an explicit physical repair set.
        assert latest.get(case) in (('FAIL','ERROR','ok') if explicit_repair else ('FAIL','ERROR')) and latest.get(replacement)=='ok'
        assert not explicit_repair or replacement in required_cases
        assert case not in required_cases and decision.get('reason')
        withdrawn.append(dict(case=case,result=latest.pop(case),**decision))
    assert (latest or retained) and all(value=='ok' for value in latest.values()),('unresolved test failures',latest)
    for name in spec.get('retained_failure_logs',[]):
        log_path=name if name.startswith('data/verification/') else 'data/verification/'+name
        stage(log_path,(S/name).read_bytes())
    verification=dict(unique_tests=len(latest),latest_passed=len(latest),latest_failed=0,
                      test_invocations=sum(x['tests'] for x in runs),runs=runs,
                      retained_failure_logs=spec.get('retained_failure_logs',[]))
    if physical:
        verification.update(evidence_repo_root=str(physical_root),publication_repo_root=str(R))
    if retained:verification.update(retained)
    if withdrawn:
        verification.update(observed_unique_tests=observed_unique_tests,
                            withdrawn_test_assumptions=withdrawn)
    selected={};documents={}
    for uid,details in spec['completed'].items():
        registry=details['registry'];filename,rows_key,id_key=REGISTRIES[registry]
        path='data/verification/'+filename
        if path not in documents:documents[path]=read_overlay(path)
        doc=documents[path];row=next(x for x in doc[rows_key] if x[id_key]==uid)
        assert registry_included(row,registry) and registry_status(row,registry) in (('incomplete','known-rule-choice') if registry=='class' else ('incomplete',)),uid
        assert (retained and details['tests']==[] and details['reused_test_ids']) or (details['tests'] and all(case_key(case) in latest for case in details['tests'])),uid
        _,source_digest=candidate_source_identity(details)
        assert source_digest in registry_source_digests(row,registry),uid
        complete_registry_row(row,registry,details,ref,verification,at,uid)
        selected[uid]=row
    for path,doc in documents.items():
        if path.endswith('core-clause-status.json'):doc['implementation_counts']=dict(Counter(x['category2_status'] for x in doc['clause_mappings']))
        if path.endswith('class-clause-status.json'):
            doc['counts']['status']=dict(Counter(x['status'] for x in doc['entries']))
            doc['latest_native_edge_completion']=ref
        if path.endswith(('category2-optional-clause-status.json','category2-optional-additional-clause-status.json')):
            doc['status_counts']=dict(Counter(x['status'] for x in doc['rows']))
            doc['completion_revision']=int(doc.get('completion_revision',0))+1
        if path.endswith('item-table-status.json'):
            doc['runtime_implementation_counts']=dict(Counter(x['status'] for x in doc['new_clauses']))
        if path.endswith('class-csv-clause-status.json'):
            status_counts=Counter(x['status'] for x in doc['rows'])
            doc['counts'].update(status_counts)
        save(path,doc)
    inventory_path='data/verification/template-audit-inventory.json'
    optional_paths=('data/verification/category2-optional-clause-status.json',
                    'data/verification/category2-optional-additional-clause-status.json')
    changed_optional_paths=[path for path in optional_paths if path in documents]
    if inventory_path in names and changed_optional_paths:
        inventory=read_overlay(inventory_path)
        for optional_path in changed_optional_paths:
            optional_sha=digest((S/optional_path).read_bytes())
            matches=[row for row in inventory['registries'] if row.get('path')==optional_path]
            assert len(matches)==1
            matches[0]['sha256']=optional_sha
        stage(inventory_path,(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    completed=list(selected);after=before+len(completed);remaining=2352-after
    reviewed_hashes={}
    for reference in spec['reviewed_files']:
        # Keep the exact line/record/fragment locator in provenance, while
        # fingerprinting its containing file rather than a fictitious filename.
        name=reviewed_file_name(reference)
        reviewed_hashes[reference]=digest(((S/name) if name in names else (R/name)).read_bytes())
    batch={k:deepcopy(spec[k]) for k in ('id','runtime_changes','test_changes','native_paths','foundation_ids','changes')}
    batch.update(at=at,status='repair_verified' if repair else 'implemented_and_verified',repair_only=repair,clause_ids=completed,completion_delta=len(completed),
                 completed_before=before,completed_after=after,denominator=2352,remaining=remaining,
                 source_obligations={uid:spec['completed'][uid]['obligation'] for uid in completed},
                 source_references=[registry_source_reference(uid,row,spec['completed'][uid]['registry'],
                                                              candidate_source_identity(spec['completed'][uid])[1])
                                    for uid,row in selected.items()],
                 selection=deepcopy(spec['selection']),verification=verification,
                 not_completed=list(spec['deferred']),preserved_sha256=protected,
                 current_file_hashes=reviewed_hashes)
    v[key+'_completion']=batch
    v['last_repair_at' if repair else 'last_native_completion_at']=at;p['overall_completed']=after
    v['verified_overall']=dict(completed=after,denominator=2352,remaining=remaining,percent=round(after/2352*100,8))
    by_id={x['id']:x for x in sweep['rows']};deps=v['dependency_order']['deferred_consumers']
    for uid,decision in spec['deferred'].items():
        row=dict(consumer=uid,waiting_consumer=uid,status='deferred_unverified_complete_consumer',
                 verified_absent=False,completion_credit=0,latest_review=ref)
        row.update(decision)
        old=next((x for x in deps if x.get('consumer')==uid),None)
        if old is None:deps.append(row)
        else:old.update(row)
        # Some denominator registries (CSV abilities/moves, class CSV, item
        # tables) were frozen after the legacy 1,790-row ready sweep.  Their
        # deferred consumers still belong in dependency_order, but there is no
        # legacy sweep row to mutate.  This mirrors the completed-row handling
        # immediately below instead of rejecting a valid registry clause.
        if uid in by_id:
            by_id[uid].update(
                admit_now=False,
                decision=row['status'],
                reason=row['observed'],
                prerequisite=row['prerequisite'],
                resume_when=row['resume_when'],
                latest_review=ref,
            )
    for uid in completed:
        # Later frozen registries (for example class CSV and item-table rows)
        # contribute to the 2,352 denominator but were added after the legacy
        # 1,790-row ready sweep was frozen.  Reconcile their native registry and
        # global ledgers without inventing a legacy sweep row.
        if uid in by_id:
            by_id[uid].update(admit_now=False,decision='completed_verified',reason=spec['completed'][uid]['obligation'],completion_credit=1,evidence=ref,completion_evidence=ref)
        if uid not in sweep['completed_clause_ids']:sweep['completed_clause_ids'].append(uid)
        for row in deps:
            if row.get('consumer')==uid:row.update(status='implemented_and_verified',completion_credit=1,completion_evidence=ref,resolved_at=at)
    sweep.update(counts=dict(Counter(x['decision'] for x in sweep['rows'])),completed_after_batches=after,remaining_now=remaining)
    assert sum(sweep['counts'].values())==sweep['coverage']['expected']==1790
    sweep['ready_clause_ids']=[x for x in sweep['ready_clause_ids'] if x not in completed]
    if not repair:
        sweep['consumer_review_batches'].append(dict(id=key,at=at,queried_clause_ids=spec['selection']['queried_clause_ids'],selected_clause_ids=completed,completed_clause_ids=completed,deferred_clause_ids=list(spec['deferred']),completion_delta=len(completed),evidence=ref))
        sweep['batch_queue'].append(dict(id=key,clause_ids=completed,stage='implemented_and_verified',native_path=spec['native_paths'][0],completion_credit=len(completed),completion_evidence=ref))
    audit=p['post_foundation_reuse']['itemized_audit'];old_count=len(audit['items'])
    for uid,row in selected.items():
        assert uid not in audit['baseline_clause_ids']+audit['added_clause_ids']
        audit['added_clause_ids'].append(uid)
        audit['items'].append(dict(id=uid,name=selected_name(row),category2_counted=True,route=key,status='verified',entrypoint_reviewed=True,reviewed_at=at,review_basis=ref))
    # Preserve successful individual cases from mixed runs without relabeling
    # the entire run as successful. The reporter verifies these explicit case
    # IDs against the hashed original bytes; latest results above must all pass.
    if not repair:
        proofs=eligible_run_proofs(runs)
        if retained:
            proofs.extend({k:deepcopy(run[k]) for k in ('log','sha256','tests','seconds','cases')}
                          for run in retained['retained_runs'])
        audit['routes'][key]=dict(target_clause_ids=completed,native_paths=spec['native_paths'],foundation_ids=spec['foundation_ids'],required_test_modules=spec['required_test_modules'],behavior='; '.join(batch['source_obligations'].values()),evidence_refs=[ref],evidence=proofs)
        audit['scope_additions'].append(dict(at=at,clause_ids=completed,**{'from':old_count,'to':len(audit['items'])},reason=spec['changes'][0],evidence=ref))
        audit['scope']=f"최초 원조항95개와 실제 구현·검증 후 추가한{len(audit['added_clause_ids'])}개를 포함한다. 현재 점검 분모는 원조항 ID{len(audit['items'])}개다. 재사용 점검 자체에 대분류2 완료 점수를 부여하지 않는다."
    save(PLAN,p)
    route_note=f'vaults/재사용/{key}.md'
    if not repair and not (R/route_note).is_file() and route_note not in names:
        sys.path.insert(0,str(R/'tools'))
        import build_reuse_vault as BUILD_VAULT
        generated=BUILD_VAULT.render_route(
            key,audit['routes'][key],(row for row in audit['items'] if row['route']==key),
            p['foundation_discovery']['foundation_freeze']['unit_ids'])
        stage(route_note,generated.encode('utf-8'))
    original_text,original_bytes,original_file=Path.read_text,Path.read_bytes,Path.is_file
    def overlay(path):
        try:name=path.relative_to(R).as_posix()
        except ValueError:return path
        return S/name if name in names else path
    def text(path,*args,**kwargs):return original_text(overlay(path),*args,**kwargs)
    def raw(path):return original_bytes(overlay(path))
    def is_file(path):return original_file(overlay(path))
    sys.path.insert(0,str(R/'tools'))
    report_path='tools/report_category2_progress.py'
    if report_path in names:
        from importlib.util import module_from_spec,spec_from_file_location
        report_spec=spec_from_file_location('_staged_category2_progress',S/report_path)
        REPORT=module_from_spec(report_spec);report_spec.loader.exec_module(REPORT)
    else:
        import report_category2_progress as REPORT
    with patch.object(Path,'read_text',text),patch.object(Path,'read_bytes',raw),patch.object(Path,'is_file',is_file):inspection=REPORT.collect_edge_reuse(R,p)
    if not (inspection['completed']==inspection['denominator']==len(audit['items']) and not inspection['validation_errors']):
        print(json.dumps({'reuse_inspection_failure':inspection},ensure_ascii=False,indent=2))
        raise AssertionError('reuse inspection failed')
    p['post_foundation_reuse']['itemized_summary']=inspection;save(PLAN,p)
    c.update(completed=after,percent=round(after/2352*100,8),reuse_inspection=inspection,last_goal_turn_classification='progress')
    c['current_work'].update(completed_now=after,completed=after,remaining=remaining,stage='repair_verified' if repair else 'cached_native_consumer_implemented_and_verified',completion_credit=len(completed),latest_batch=ref,reuse_inspection=inspection,completed_this_work_turn=completed,work_completed_this_turn=completed)
    if repair:c['current_work']['latest_repair']=ref
    else:c['current_work'].update(latest_completion=ref,latest_selection_review=ref,current_clause=None)
    c['current_work']['verified_batch_refs'].append(ref)
    if spec['selection'].get('execution_method'):
        c['current_work']['execution_method']=spec['selection']['execution_method']
    c['last_goal_turn']=dict(at=at,classification='progress',previous_turn_classification='progress',previous_turn_evidence=spec['previous_completion'],work=[ref],clause_delta=len(completed),from_completed=before,to_completed=after,completed_clause_ids=completed,inspection=inspection,verification=verification,user_steering='한 번 조회한 후보를 재사용하고 기존 경로로 완결 가능한 소비자를 묶는다. 계수기·교정 주기는 중지 유지.')
    assert object_hash(c['architecture_review'])==protected['architecture_review'];save(CP,c)
    assert object_hash(p['foundation_discovery'])==protected['foundation_discovery']
    assert object_hash(v['whole_rule_template_audit']['reuse_elements_progress'])==protected['reuse40']
    assert audit['baseline_sha256']==protected['baseline95']
    checks=read('data/verification/template-reuse-checks.json');checks['implementation_batches'].append(batch)
    checks['current_implementation_result']=dict(id=key,at=at,evidence=ref,status='PASS',completion_delta=len(completed),completed=after,denominator=2352,**verification)
    save('data/verification/template-reuse-checks.json',checks)
    contracts=read('data/verification/template-reuse-contracts.json')
    if repair:contracts['latest_repair']=ref
    else:contracts.update(latest_consumer_completion=ref,latest_consumer_review=ref)
    save('data/verification/template-reuse-contracts.json',contracts)
    with patch.object(Path,'read_text',text),patch.object(Path,'read_bytes',raw),patch.object(Path,'is_file',is_file):progress=REPORT.collect(R)
    if not (progress['completed_clause_count']==after and progress['denominator']==2352 and not progress['validation_errors']):
        print(json.dumps({'progress_reconciliation_failure': {
            'expected_completed': after,
            'completed_clause_count': progress.get('completed_clause_count'),
            'denominator': progress.get('denominator'),
            'validation_errors': progress.get('validation_errors'),
        }},ensure_ascii=False,indent=2))
        raise AssertionError('progress reconciliation failed')
    assert progress['edge_reuse_inspection']==inspection;save(PROGRESS,progress)
    for name,value in spec.get('notes',{}).items():
        body=value['body']
        if value['mode']=='append':body=(R/name).read_text(encoding='utf-8-sig').rstrip()+'\n\n'+body
        else:assert value['mode']=='create' and not (R/name).exists()
        stage(name,(body.rstrip()+'\n').encode('utf-8'))
    (S/'baseline.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf-8')
    (S/(key+'-artifacts.json')).write_text(json.dumps(names,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(completed=after,remaining=remaining,unique_tests=len(latest),retained_named_passes=retained['historical_named_pass_count'] if retained else 0,reuse=f"{inspection['completed']}/{inspection['denominator']}",artifacts=len(names)),ensure_ascii=False))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate',type=Path)
    parser.add_argument('--stage',type=Path,help='defaults to the candidate directory (legacy CLI compatible)')
    parser.add_argument('--repo-root',type=Path,default=R)
    parser.add_argument('--evidence-repo-root',type=Path,help='actual root used by physical executions; does not change the publication root')
    parser.add_argument('--preflight-only',action='store_true',help='validate metadata, note targets and staged input files without evidence, writes or game imports')
    args=parser.parse_args()
    if args.preflight_only:
        validate_candidate_metadata(json.loads(args.candidate.read_text(encoding='utf-8-sig')),
                                    repo_root=args.repo_root,stage=args.stage or args.candidate.resolve().parent)
        print('Candidate metadata preflight PASS')
    else:
        main(args.stage or args.candidate.resolve().parent,args.candidate,repo_root=args.repo_root,evidence_repo_root=args.evidence_repo_root)
