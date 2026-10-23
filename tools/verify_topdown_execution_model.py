"""Run the root-model suites; never reports rulebook source coverage."""
from pathlib import Path
import sys,subprocess,json,hashlib
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
SUITES=(('test_root_machine_independent.py','root-machine-independent-tests.json'),
        ('test_root_resolution.py','root-resolution-tests.json'),
        ('test_root_resolution_independent.py','root-resolution-independent-tests.json'),
        ('test_root_admission_independent.py','admission-independent-tests.json'),
        ('test_root_inputs_author.py','root-inputs-author-tests.json'),
        ('test_root_inputs_independent.py','root-input-independent-tests.json'),
        ('test_root_frontier_independent.py','root-frontier-independent-tests.json'),
        ('test_root_runtime_io_independent.py','root-runtime-io-independent-tests.json'),
        ('test_root_children_author.py','root-children-author-tests.json'),
        ('test_root_children_independent.py','root-child-independent-tests.json'),
        ('test_root_child_bridge_independent.py','root-child-bridge-independent-tests.json'),
        ('test_root_common_checks_author.py','root-common-check-author-tests.json'),
        ('test_root_common_checks_independent.py','root-common-check-independent-tests.json'),
        ('test_common_check_engine_independent.py','common-check-engine-independent-tests.json'))
rows=[]
for script,output in SUITES:
 run=subprocess.run([sys.executable,'-B','-X','utf8',str(ROOT/'tools'/script)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
 row={'script':'tools/'+script,'exit_code':run.returncode,'report':'output/'+output,'errors':[]}
 if run.returncode:
  row['errors'].append(run.stdout+run.stderr)
 else:
  report=json.loads((ROOT/'output'/output).read_text(encoding='utf-8'))
  row['tests']=len(report['results'])
  if any(r['status'] not in ('pass','passed') for r in report['results']):row['errors'].append('nonpassing component result')
  for rel,expected in report['input_hashes'].items():
   if hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=expected:row['errors'].append('input mismatch: '+rel)
  for rel,expected in report.get('native_data_hashes',{}).items():
   if hashlib.sha256((Path(report['native_data_root'])/rel).read_bytes()).hexdigest()!=expected:row['errors'].append('native input mismatch: '+rel)
  row['report_sha256']=hashlib.sha256((ROOT/'output'/output).read_bytes()).hexdigest()
 row['status']='fail' if row['errors'] else 'pass';rows.append(row)
 print(script+': '+row['status'])
report={'generated_at':datetime.now(timezone.utc).isoformat(),'suites':rows,'test_count':sum(r.get('tests',0) for r in rows),'scope':'Root structural/model suites only; separate from legacy Engine/full-rulebook audit aggregate','source_registrations_certified':0,'whole_source_complete':False,'live_game_Engine_integration_proved':False,'native_opt_in_api_tested':True,'existing_gameplay_callers_migrated':0,'prior_test_count':364,'new_test_count':113,'native_integration_scope':'New opt-in Engine.open_common_checks API exercised by tests with real native objects; existing gameplay callers do not invoke it. Existing numeric implementation reused. No automatic world effects.','whole_live_engine_migrated':False}
(ROOT/'output/topdown-execution-model-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'suites':len(rows),'tests':report['test_count'],'failed':sum(r['status']!='pass' for r in rows)}))
raise SystemExit(any(r['status']!='pass' for r in rows))
