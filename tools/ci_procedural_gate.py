"""Run one original procedural script in a fresh audited CI child, without collection."""
from __future__ import annotations
import base64, contextlib, copy, hashlib, io, json, math, os, re, sys, tempfile, time, traceback, types
from pathlib import Path, PurePosixPath
from fnmatch import fnmatchcase
_RAW_OPEN = io.open
KIND = 'procedural_runner'
INVENTORY_SHA256 = '46c04e8eb8efa90c96a5ca21864b44e0112a7b0b9d78f77c31aad5bafe36caf5'
CONTRACTS = {'script:engine/test_builder.py': {'original_contract_sha256': 'e3d77188349b73970f6d36f0f531954dee866138e7948788b9d3062d268daf49', 'runner': {'source_path': 'engine/test_builder.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_builder.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/builder-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': ['output/encounter-lakeside.md', 'output/encounter-cave.md'], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_contest.py': {'original_contract_sha256': '2643fc488e4d75eb8b8ae602dfbb53a8fb827577546416aebc98fd23ce0fd9f7', 'runner': {'source_path': 'engine/test_contest.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_contest.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/contest-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_downtime.py': {'original_contract_sha256': '8567f29733dffb421374a7fd02841657261bee248b6dffc44c742cfe4b7a1121', 'runner': {'source_path': 'engine/test_downtime.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_downtime.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/downtime-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_effects.py': {'original_contract_sha256': '765b953a94ea3cd8db43da8d344d7b7839936f79b1cf10a5f2bcd9b67ff9a8b4', 'runner': {'source_path': 'engine/test_effects.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_effects.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/effect-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_gm_state.py': {'original_contract_sha256': '6d26de94a987d9473b304e478b07f77866756719b89aa4d8f7cb5e85c82a6f70', 'runner': {'source_path': 'engine/test_gm_state.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_gm_state.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/gm-state-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_grid.py': {'original_contract_sha256': '32f97821226602bb9793304e200b8ab38747509bc74481704cee074778c22797', 'runner': {'source_path': 'engine/test_grid.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_grid.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/grid-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_items.py': {'original_contract_sha256': 'aebde1628a4a43c42d344b645c857a9c42daee7d4589aebec1cc79a834d51074', 'runner': {'source_path': 'engine/test_items.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_items.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/item-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_rules.py': {'original_contract_sha256': '897c201c260f1f2987b390fdffd754a5db8c1a64aafbd2a774004d252ac2f31f', 'runner': {'source_path': 'engine/test_rules.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_rules.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/rule-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'results', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_ruleset.py': {'original_contract_sha256': 'a2b7d49eddf6df34019f29adbfb633e8a4e6ba14b1870c8a0d3501033a3dbc08', 'runner': {'source_path': 'engine/test_ruleset.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_ruleset.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/ruleset-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': ['output/ruleunits.core.jsonl', 'output/ruleset-core.md'], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_rulings.py': {'original_contract_sha256': '724c7317ed000d0bfca8ca0e590752fa02b498524c7b6df86667d9015729ccca', 'runner': {'source_path': 'engine/test_rulings.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_rulings.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/rulings-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:engine/test_turn.py': {'original_contract_sha256': 'ef3d2f70cba9723b945187a201f8fdffacdbacf8a723f179ddba42cc41478160', 'runner': {'source_path': 'engine/test_turn.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/engine/test_turn.py', '{stage}'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/turn-tests.md', 'kind': 'markdown_result_table'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'res', 'entry_function': 'run', 'sort_results_by_id': False}}, 'script:tools/test_common_check_engine_independent.py': {'original_contract_sha256': 'b6684fb25484da6294e2788e9972d2befa16a57299cbb9d7c67ecd2006f0613a', 'runner': {'source_path': 'tools/test_common_check_engine_independent.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_common_check_engine_independent.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp', 'PTK_NATIVE_RULE_ROOT': '{stage}'}, 'report': {'path': 'output/common-check-engine-independent-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': ['tools/common_check_synthetic_evidence.txt'], 'generated_retained': ['tools/native-profile-test-*.json']}, 'result_buffer': 'RESULTS', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_admission_independent.py': {'original_contract_sha256': '5902ed9e2e561f281041de5a4425721342b7002e3d1f77d9d736cc9cd540144b', 'runner': {'source_path': 'tools/test_root_admission_independent.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_admission_independent.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/admission-independent-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': ['tools/root_admission_synthetic_evidence.txt'], 'generated_retained': []}, 'result_buffer': 'results', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_child_bridge_independent.py': {'original_contract_sha256': '71db64cb1af09824673a51bc25276924c4aa5468d0bda4f61fedfac6a6e7a61c', 'runner': {'source_path': 'tools/test_root_child_bridge_independent.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_child_bridge_independent.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-child-bridge-independent-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': ['tools/certificate-parent.json'], 'generated_retained': ['tools/certificate-parent.json', 'tools/certificate-child.json', 'tools/certificate-grand.json']}, 'result_buffer': 'RESULTS', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_children_author.py': {'original_contract_sha256': 'b5b377b5206210a36dc12f14c0b74282bba9ad0e30996a2088d212a394bfc2a2', 'runner': {'source_path': 'tools/test_root_children_author.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_children_author.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-children-author-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'rows', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_common_checks_author.py': {'original_contract_sha256': '6ad65ebee1de6cf93cc64bcddc942ec5dcd44cbbe32a2be94baedf58cd397572', 'runner': {'source_path': 'tools/test_root_common_checks_author.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_common_checks_author.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-common-check-author-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'results', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_frontier_independent.py': {'original_contract_sha256': '04044fc0fdd31a6ffff7394dbfd5787648a7f5babb15c8f93f33eefc7457343d', 'runner': {'source_path': 'tools/test_root_frontier_independent.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_frontier_independent.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-frontier-independent-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'RESULTS', 'entry_function': None, 'sort_results_by_id': True}}, 'script:tools/test_root_inputs_author.py': {'original_contract_sha256': '810154d42450d8c546de087fcda36896d0242b71ae87b252dba2be0bb8c68c21', 'runner': {'source_path': 'tools/test_root_inputs_author.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_inputs_author.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-inputs-author-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'results', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_machine_independent.py': {'original_contract_sha256': 'fdda17687309f0092a7f7553e39045301baa99ade36f263e5f95ee7f2199a23e', 'runner': {'source_path': 'tools/test_root_machine_independent.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_machine_independent.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-machine-independent-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'results', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_resolution.py': {'original_contract_sha256': '3b17f1cfd8582a46bc66484edbd3735ae0930089eef85eeed414490425653642', 'runner': {'source_path': 'tools/test_root_resolution.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_resolution.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-resolution-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'RESULTS', 'entry_function': None, 'sort_results_by_id': False}}, 'script:tools/test_root_runtime_io_independent.py': {'original_contract_sha256': '605a69d30ab8e0bfff62fbbc61e51bacf961d9781b276d378f5907a25a106432', 'runner': {'source_path': 'tools/test_root_runtime_io_independent.py', 'argv': ['python', '-B', '-X', 'utf8', '-I', '{stage}/tools/test_root_runtime_io_independent.py'], 'cwd': '{stage}', 'environment': {'TEMP': '{stage}/.tmp', 'TMP': '{stage}/.tmp'}, 'report': {'path': 'output/root-runtime-io-independent-tests.json', 'kind': 'json_results_array'}, 'additional_outputs': [], 'mutations': {'temporarily_modified_restored': [], 'generated_retained': []}, 'result_buffer': 'results', 'entry_function': None, 'sort_results_by_id': False}}}

# Separate new metadata entry; the historical 21-runner inventory stays unchanged.
ADDITIONAL_INVENTORY_SHA256 = '644d8b97633d5f09fe8bbce02e0e7e132a499757ef4d9509bad25f90f3edf5a8'
ADDITIONAL_CONTRACTS = {'script:tools/audit_common_activation_matrix.py': {'original_contract_sha256': 'f61cf414d4a37d60ab67031bb7155700b59646aff654a49f4a715de181279fd9',
                                                    'runner': {'additional_outputs': [],
                                                               'argv': ['python',
                                                                        '-B',
                                                                        '-X',
                                                                        'utf8',
                                                                        '-I',
                                                                        '{stage}/tools/audit_common_activation_matrix.py'],
                                                               'cwd': '{stage}',
                                                               'entry_function': None,
                                                               'environment': {'TEMP': '{stage}/.tmp',
                                                                               'TMP': '{stage}/.tmp'},
                                                               'mutations': {'generated_retained': [],
                                                                             'temporarily_modified_restored': []},
                                                               'report': {'kind': 'json_results_array',
                                                                          'path': 'output/common-activation-matrix-audit.json'},
                                                               'result_buffer': 'results',
                                                               'sort_results_by_id': False,
                                                               'source_path': 'tools/audit_common_activation_matrix.py'},
                                                    'source_sha256': 'd03b8b616b0d89701ec5aa86fe9487bf9f2a5fc327844bf8ca5958cd2e83f5ca'}}

def _bytes(path):
    with _RAW_OPEN(path,'rb') as stream:return stream.read()

def _sha(path):return hashlib.sha256(_bytes(path)).hexdigest()

def _write_json(path,value):
    with _RAW_OPEN(path,'x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')

def packet(value):
    if type(value) is not dict or value.get('schema_version')!=1 or value.get('execution_kind')!=KIND:
        raise ValueError('unknown procedural packet schema')
    unit=value.get('unit_id')
    if not isinstance(unit,str) or unit not in CONTRACTS and unit not in ADDITIONAL_CONTRACTS:
        raise ValueError('unknown explicitly allowed procedural runner')
    additional=unit in ADDITIONAL_CONTRACTS
    expected=ADDITIONAL_CONTRACTS[unit] if additional else CONTRACTS[unit]
    inventory=ADDITIONAL_INVENTORY_SHA256 if additional else INVENTORY_SHA256
    if value.get('inventory_sha256')!=inventory or value.get('unit_kind')!='procedural_script_runner':
        raise ValueError('unknown original or additional runner inventory')
    if value.get('required_runner_ids')!=[unit] or value.get('completed')!={}:
        raise ValueError('one explicitly allowed runner and no ordinary method IDs required')
    runner=value.get('runner',{});spec=dict(runner);digest=spec.pop('source_sha256',None)
    if spec!=expected['runner'] or value.get('original_contract_sha256')!=expected['original_contract_sha256']:
        raise ValueError('original procedural execution contract changed')
    if not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None:
        raise ValueError('exact captured script SHA required')
    if additional and digest!=expected['source_sha256']:
        raise ValueError('additional metadata runner source differs from its reviewed source')
    return copy.deepcopy(value)


def prepare_stage(stage,declaration,hashes,destination):
    """Record exact stale declared outputs before removing only their fresh-stage copies."""
    packet(declaration)
    stage=Path(stage).resolve();destination=Path(destination).resolve()
    if destination.is_relative_to(stage):raise ValueError('preparation evidence must be outside the stage')
    runner=declaration['runner'];source=stage/runner['source_path']
    if hashes.get(runner['source_path'])!=runner['source_sha256'] or _sha(source)!=runner['source_sha256']:
        raise ValueError('preparation source differs from the frozen runner')
    rows=[]
    for rel in [runner['report']['path'],*runner['additional_outputs']]:
        if (not isinstance(rel,str) or '\\' in rel or ':' in rel
                or any(p in ('','..','.') for p in rel.split('/'))):
            raise ValueError('unsafe exact procedural output path')
        path=stage/rel
        if path.is_symlink() or not path.resolve().is_relative_to(stage):
            raise ValueError('procedural output leaves its fresh stage')
        if not path.exists():continue
        if not path.is_file():raise ValueError('procedural output is not a regular file')
        body=_bytes(path);digest=hashlib.sha256(body).hexdigest()
        if hashes.get(rel)!=digest:raise ValueError('stale output has no authenticated preimage')
        rows.append({'path':rel,'sha256':digest,'preimage_base64':base64.b64encode(body).decode('ascii')})
    record={'schema_version':1,'action':'remove_exact_declared_output_stage_copy_before_pre_capture',
        'execution_stage':str(stage),'unit_id':declaration['unit_id'],
        'source_path':runner['source_path'],'source_sha256':runner['source_sha256'],
        'original_contract_sha256':declaration['original_contract_sha256'],
        'inventory_sha256':declaration['inventory_sha256'],'preimages':rows}
    _write_json(destination,record)
    for row in rows:
        path=stage/row['path']
        if _sha(path)!=row['sha256']:raise ValueError('stale output changed after preimage recording')
        path.unlink()
        del hashes[row['path']]
    return record

def capture_generated_bytes(path,digest,physical,directory):
    body=_bytes(path)
    if hashlib.sha256(body).hexdigest()!=digest:raise ValueError('generated first-read bytes changed')
    dest=Path(physical)/directory/(digest+'.bin');dest.parent.mkdir(exist_ok=True)
    if not dest.exists():
        with _RAW_OPEN(dest,'xb') as stream:stream.write(body)
    elif _bytes(dest)!=body:raise ValueError('generated evidence hash collision')
    return 'physical/'+directory+'/'+digest+'.bin'


class Capture:
    """Only the contract's new artifacts may become dynamically read inputs."""
    def __init__(self,stage,declaration,before,physical,event):
        self.stage=Path(stage).resolve();self.physical=Path(physical).resolve();self.event=event
        self.before={str(Path(p).resolve()):h for p,h in before.items()};self.runner=declaration['runner']
        self.generated=self.runner['mutations']['generated_retained']
        self.restored=set(self.runner['mutations']['temporarily_modified_restored'])
        self.outputs={self.runner['report']['path'],*self.runner['additional_outputs']}
        self.active=False;self.writes=set();self.generated_reads={};self.write_events=[]
        for pattern in self.generated:
            if list(self.stage.glob(pattern)):raise ValueError('generated contract path already exists')
        self.initial_files={p.relative_to(self.stage).as_posix() for p in self.stage.rglob('*') if p.is_file()}
    def relative(self,path):
        path=Path(path).resolve()
        return path.relative_to(self.stage).as_posix() if path.is_relative_to(self.stage) else None
    def allowed_generated(self,rel):
        return rel in self.outputs or any(len(PurePosixPath(rel).parts)==len(PurePosixPath(p).parts)
            and all(fnmatchcase(a,b) for a,b in zip(PurePosixPath(rel).parts,PurePosixPath(p).parts)) for p in self.generated)
    def observe_open(self,file,mode):
        if not self.active or isinstance(file,int) or not isinstance(mode,str) or not any(c in mode for c in 'wax+'):return
        path=Path(file).resolve();rel=self.relative(path)
        if rel is None:raise ValueError('procedural write leaves its dedicated stage')
        if str(path) in self.before:
            if rel not in self.restored:raise ValueError('procedural write overwrites an immutable input')
        elif not self.allowed_generated(rel) and not rel.startswith('.tmp/'):
            raise ValueError('procedural write has no original output/mutation contract')
        elif path.exists() and str(path) not in self.writes:
            raise ValueError('procedural output would overwrite an existing unregistered file')
        first_write=str(path) not in self.writes;existed_before_write=path.exists()
        self.write_events.append({'path':rel,'mode':mode,'first_write':first_write,'existed_before_write':existed_before_write})
        self.event('procedural_write',path=str(path),mode=mode,first_write=first_write,existed_before_write=existed_before_write)
        self.writes.add(str(path))
    def generated_read(self,path,digest):
        path=Path(path).resolve();rel=self.relative(path)
        if not self.active or rel is None or str(path) not in self.writes or str(path) in self.before or not self.allowed_generated(rel):return False
        member=capture_generated_bytes(path,digest,self.physical,'procedural-generated')
        self.generated_reads[str(path)]={'path':rel,'sha256':digest,'archive_member':member}
        self.event('procedural_generated_first_read',path=str(path),sha256=digest,archive_member=member)
        return True
    def finish(self):
        for rel in self.restored:
            path=self.stage/rel;expected=self.before.get(str(path.resolve()))
            if expected is None:expected=self.generated_reads.get(str(path.resolve()),{}).get('sha256')
            if expected is None or not path.is_file() or _sha(path)!=expected:
                raise ValueError('declared temporary mutation was not restored')
        for path in self.stage.rglob('*'):
            if not path.is_file():continue
            rel=path.relative_to(self.stage).as_posix()
            if rel not in self.initial_files and not self.allowed_generated(rel) and not rel.startswith('.tmp/'):
                raise ValueError('undeclared generated stage file')
        final=[]
        for key in sorted(self.writes):
            path=Path(key);rel=self.relative(path)
            if key in self.before or rel in self.outputs or not self.allowed_generated(rel) or not path.is_file():continue
            body=_bytes(path);sha=hashlib.sha256(body).hexdigest();dest=self.physical/'procedural-generated'/(sha+'.bin')
            dest.parent.mkdir(exist_ok=True)
            if not dest.exists():
                with _RAW_OPEN(dest,'xb') as stream:stream.write(body)
            final.append({'path':rel,'sha256':sha,'archive_member':'physical/procedural-generated/'+sha+'.bin'})
        return {'writes':self.write_events,'generated_first_reads':list(self.generated_reads.values()),'generated_final_artifacts':final,'temporary_inputs_restored':True}

def _invoke(source,argv,buffer_name,entry_function,stdout,stderr):
    """Execute unchanged __main__ code; retain the actual result buffer for completeness."""
    main=types.ModuleType('__main__');main.__file__=str(source);main.__package__=None;main.__spec__=None
    namespace=main.__dict__;old_main=sys.modules.get('__main__');old_argv=sys.argv;old_path=list(sys.path);old_trace=sys.gettrace()
    observed={};exit_code=None;exception=None
    def trace(frame,event,arg):
        if frame.f_code.co_filename!=str(source) or frame.f_code.co_name!=entry_function:return None
        if event=='return':
            rows=frame.f_locals.get(buffer_name)
            observed['rows']=[(r[0],r[1],None) for r in rows] if isinstance(rows,list) and all(isinstance(r,(tuple,list)) and len(r)==3 for r in rows) else None
            observed['completed']=type(arg) is bool
        return trace
    try:
        sys.modules['__main__']=main;sys.argv=list(argv)
        if entry_function:sys.settrace(trace)
        with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            try:exec(compile(source.read_bytes(),str(source),'exec'),namespace)
            except SystemExit as done:
                exit_code=0 if done.code is None else int(done.code) if type(done.code) in (int,bool) else 1
            except BaseException:
                exception=traceback.format_exc();stderr.write(exception);exit_code=1
        if entry_function is None:
            observed['rows']=copy.deepcopy(namespace.get(buffer_name));observed['report']=copy.deepcopy(namespace.get('report'))
            observed['completed']=exit_code is not None and type(observed['report']) is dict
    finally:
        sys.settrace(old_trace);sys.argv=old_argv;sys.path[:]=old_path
        if old_main is None:sys.modules.pop('__main__',None)
        else:sys.modules['__main__']=old_main
    return exit_code,observed,exception

def validate_report(body,kind,observed,sort_results_by_id=False):
    if not observed.get('completed') or not isinstance(observed.get('rows'),list) or not observed['rows']:
        raise ValueError('original runner did not complete a nonempty result buffer')
    rows=observed['rows'];passed=failed=unknown=0
    if kind=='markdown_result_table':
        text=body.decode('utf-8-sig');summaries=re.findall(r'(?m)^\*{0,2}(\d+)/(\d+) 통과\*{0,2}.*$',text)
        table=[line for line in text.splitlines() if re.match(r'^\|\s*\d+\s*\|',line)]
        if len(summaries)!=1 or len(table)!=len(rows):raise ValueError('partial or unknown Markdown result table')
        for i,(line,row) in enumerate(zip(table,rows),1):
            if not isinstance(row,(list,tuple)) or len(row)!=3 or type(row[1]) is not bool:raise ValueError('unknown original Markdown result row')
            name,ok,_=row;status='PASS' if ok else 'FAIL'
            if not line.startswith(f'| {i} | {name} | {status} |') or not line.endswith('|'):raise ValueError('Markdown row differs from actual original result')
            passed+=int(ok);failed+=int(not ok)
        if tuple(map(int,summaries[0]))!=(passed,len(rows)):raise ValueError('Markdown summary is partial or inconsistent')
    elif kind=='json_results_array':
        report=json.loads(body.decode('utf-8-sig'));native=json.loads(json.dumps(observed.get('report'),ensure_ascii=False,allow_nan=False))
        expected=sorted(rows,key=lambda r:r['id']) if sort_results_by_id else rows
        expected=json.loads(json.dumps(expected,ensure_ascii=False,allow_nan=False))
        if type(report) is not dict or report!=native or report.get('results')!=expected:raise ValueError('JSON report omits or changes actual original result rows')
        for row in report['results']:
            if type(row) is not dict or type(row.get('id')) is not str or not row['id']:raise ValueError('unknown JSON result identity')
            status=row.get('status');passed+=int(status in ('pass','passed'));failed+=int(status in ('fail','failed'));unknown+=int(status not in ('pass','passed','fail','failed'))
        if 'passed' in report and (type(report['passed']) is not int or report['passed']!=passed):raise ValueError('JSON passed count mismatch')
        if 'failed' in report and (type(report['failed']) is not int or report['failed']!=failed):raise ValueError('JSON failed count mismatch')
    else:raise ValueError('unknown original report kind')
    return {'result_count':len(rows),'passed_count':passed,'failed_count':failed,'unknown_count':unknown,'complete':unknown==0}

def execute(stage,declaration,destination,before_mode,*,capture):
    stage=Path(stage).resolve();destination=Path(destination);runner=declaration['runner'];unit=declaration['unit_id'];started=time.perf_counter()
    report={'schema_version':1,'execution_kind':'procedural_runner_gate','unit_id':unit,'declared_runner_ids':[unit],'actual_runner_ids':[],'verified_runner_ids':[],
            'status':'not_executed','script_exit_code':None,'source_path':runner['source_path'],'source_sha256':runner['source_sha256'],
            'original_contract_sha256':declaration['original_contract_sha256'],'inventory_sha256':declaration['inventory_sha256'],
            'declared_argv':runner['argv'],'physical_wrapper_argv':list(sys.argv),'errors':[],'original_report':{},'ordinary_test_pass_credit':0,'clause_credit':0}
    old_env={k:os.environ.get(k) for k in runner['environment']};old_cwd=Path.cwd();old_temp=tempfile.tempdir
    try:
        packet(declaration)
        if os.environ.get('GITHUB_ACTIONS')!='true' or not sys.flags.isolated:raise ValueError('procedural execution requires isolated authorized CI child')
        source=stage/runner['source_path'];original=stage/runner['report']['path']
        if capture.before.get(str(source.resolve()))!=runner['source_sha256'] or _sha(source)!=runner['source_sha256']:raise ValueError('captured procedural source changed')
        if original.exists():
            if str(original.resolve()) in capture.before:raise ValueError('stale report is a captured input')
            original.unlink()
        (stage/'output').mkdir(exist_ok=True);(stage/'.tmp').mkdir(exist_ok=True)
        for key,value in runner['environment'].items():os.environ[key]=value.replace('{stage}',str(stage))
        tempfile.tempdir=str(stage/'.tmp');os.chdir(stage)
        argv=[sys.executable]+[v.replace('{stage}',str(stage)) for v in runner['argv'][1:]]
        report['resolved_argv']=argv;report['executed_argv']=argv[5:]
        before_mode(unit);capture.active=True;report['actual_runner_ids']=[unit];capture.event('procedural_start',unit_id=unit,argv=argv[5:])
        with _RAW_OPEN(destination.parent/'procedural.stdout.log','x',encoding='utf8') as stdout,_RAW_OPEN(destination.parent/'procedural.stderr.log','x',encoding='utf8') as stderr:
            code,observed,exception=_invoke(source,argv[5:],runner['result_buffer'],runner['entry_function'],stdout,stderr)
        capture.active=False;report['script_exit_code']=code
        if not original.is_file():raise ValueError('original procedural report missing after '+('exception' if exception else 'return'))
        body=_bytes(original);ext='.md' if runner['report']['kind']=='markdown_result_table' else '.json';copy_path=destination.parent/('procedural-original-report'+ext)
        with _RAW_OPEN(copy_path,'xb') as stream:stream.write(body)
        result={'path':str(original),'archive_member':'physical/'+copy_path.name,'sha256':hashlib.sha256(body).hexdigest(),'kind':runner['report']['kind'],'newly_created':str(original.resolve()) in capture.writes}
        report['original_report']=result
        if exception:raise ValueError('original procedural script raised an uncaught exception; raw report retained')
        result.update(validate_report(body,runner['report']['kind'],observed,runner['sort_results_by_id']))
        if not result['newly_created']:raise ValueError('report was not written during this original execution')
        if result['unknown_count']:raise ValueError('unknown original result status')
        report['additional_outputs']=[]
        for rel in runner['additional_outputs']:
            extra=stage/rel
            if not extra.is_file() or str(extra.resolve()) not in capture.writes:raise ValueError('declared additional output missing or stale')
            content=_bytes(extra);member='physical/procedural-additional/'+rel;copied=destination.parent/'procedural-additional'/rel
            copied.parent.mkdir(parents=True,exist_ok=True)
            with _RAW_OPEN(copied,'xb') as stream:stream.write(content)
            report['additional_outputs'].append({'path':str(extra),'archive_member':member,'sha256':hashlib.sha256(content).hexdigest()})
        report['mutation_evidence']=capture.finish()
        successful=code==0 and result['complete'] and result['failed_count']==0 and result['passed_count']==result['result_count']
        report['status']='passed' if successful else 'failed';report['verified_runner_ids']=[unit] if successful else []
    except BaseException as error:
        report['errors'].append({'type':type(error).__name__,'message':str(error)});report['status']='error' if report['actual_runner_ids'] else 'not_executed';report['verified_runner_ids']=[]
    finally:
        capture.active=False;os.chdir(old_cwd);tempfile.tempdir=old_temp
        for key,value in old_env.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value
        report['elapsed_seconds']=time.perf_counter()-started;report['successful']=report['status']=='passed'
        _write_json(destination,report);capture.event('procedural_finished',unit_id=unit,status=report['status'])
    return (0 if report['successful'] else 1),report

def public_summary(path,outcome):
    try:raw=json.loads(_bytes(path).decode('utf8'))
    except (OSError,ValueError):raw={}
    result=raw.get('original_report',{});success=raw.get('status')=='passed' and raw.get('successful') is True and outcome.get('exit_code')==0
    def count(value):return value if type(value) is int and value>=0 else 0
    return {'schema_version':1,'kind':'procedural_runner_gate','successful':success,'status':'passed' if success else 'failed_or_incomplete',
            'declared_runner_count':len(raw.get('declared_runner_ids',[])),'actual_runner_count':len(raw.get('actual_runner_ids',[])),
            'verified_runner_count':len(raw.get('verified_runner_ids',[])) if success else 0,
            'result_row_count':count(result.get('result_count')),'failed_row_count':count(result.get('failed_count')),'unknown_row_count':count(result.get('unknown_count')),
            'ordinary_test_pass_credit':0,'clause_credit':0,'private_trace_location':'encrypted physical/procedural-runner.json'}
