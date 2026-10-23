"""Reproducible all-input/all-runtime buff state inventory, not certification."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
import ast,csv,hashlib,html,json,re
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/verification'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
taxonomy=read(ROOT/'data/buff-state-taxonomy.json')
by_type={}
for row in taxonomy['families']:
 for kind in row['raw_effect_types']:
  if kind in by_type:raise ValueError('type belongs to two default families: '+kind)
  by_type[kind]=row['id']
# Every frozen original input is visited, including all CSV rows. A non-match
# is an unreviewed row, never evidence that it cannot contain an effect.
patterns={
 'named_buff':r'버프|디버프|buff|digestion|만복',
 'protection':r'코트|축복|보호막|방어막|장벽|shield|coat|blessing',
 'numeric':r'보정|증가|감소|전투.?단계|추가.*(?:주사위|피해)|명중|회피|스탯',
 'lifetime':r'동안|까지|매.?턴|매.?라운드|다음.?턴|장면|지속|해제|소모|소비|중첩|누적',
 'permissions':r'면역|저항|무시|억제|금지|불가|할.?수.?없|강제|이동력|행동권',
 'state':r'상태이상|상태.?변|변신|폼|타입.*변|능력.*(?:얻|부여)|훈련|명령',
 'area':r'날씨|지형|필드|결계|범위|지역',
}
rx={k:re.compile(v,re.I) for k,v in patterns.items()}
source_files=[];source_rows=[];source_hits=[]
freeze=read(OUT/'category2-scope-freeze.json')
for old in freeze['source_manifest']:
 p=ROOT/old['file'];actual=sha(p)
 if actual!=old['sha256']:raise ValueError('frozen source changed: '+str(p))
 count=0;matches=0
 if p.suffix=='.md':
  entries=((i,line) for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1) if line.strip())
 elif p.suffix=='.csv':
  with p.open(encoding='utf-8-sig',newline='') as f:entries=list((i,' | '.join(row)) for i,row in enumerate(csv.reader(f),1) if any(x.strip() for x in row))
 else:entries=[(1,p.read_text(encoding='utf-8'))]
 for n,text in entries:
  count+=1;tags=[k for k,r in rx.items() if r.search(text)]
  row={'id':old['file']+':'+str(n),'file':old['file'],'position':n,'position_kind':'csv_record' if p.suffix=='.csv' else 'line','text_sha256':hashlib.sha256(text.encode()).hexdigest(),'candidate_tags':tags,'semantic_review':'unreviewed','preview':text[:650]}
  source_rows.append(row)
  if tags:source_hits.append(row['id']);matches+=1
 source_files.append({**old,'scanned_records':count,'candidate_records':matches})
# Keep all typed declarations and their versions; never count duplicate data
# layers as distinct rules or treat an effect handler as full source support.
typed=[];data_files=[]
name_ids=defaultdict(set)
for p in (ROOT/'output/entities').glob('*.json'):
 try:catalog=read(p)
 except (ValueError,UnicodeError):continue
 if isinstance(catalog,list):
  for row in catalog:
   if isinstance(row,dict) and isinstance(row.get('id'),str) and isinstance(row.get('name'),str):name_ids[row['name']].add(row['id'])
def walk(v,path,file,source=None):
 if isinstance(v,dict):
  source=v.get('id',source) if isinstance(v.get('id',source),str) else source
  kind=v.get('type')
  if isinstance(kind,str):
   typed.append({'file':file,'pointer':path,'source_id':source,'type':kind,'family':by_type.get(kind,'UNCLASSIFIED'),'payload':v,'semantic_review':'requires_source_comparison'})
  for k,x in v.items():
   next_source=k if '/' in k and not k.startswith('$') else source
   if path in ('/moves','/abilities','/items','/feats','/edges') and k in name_ids:
    prefix=path[1:-1]+'/' if path!='/abilities' else 'ability/'
    candidates=sorted(uid for uid in name_ids[k] if uid.startswith(prefix))
    if len(candidates)==1:next_source=candidates[0]
   walk(x,path+'/'+str(k).replace('~','~0').replace('/','~1'),file,next_source)
 elif isinstance(v,list):
  for i,x in enumerate(v):walk(x,path+'/'+str(i),file,source)
for p in sorted((ROOT/'data').glob('*.json')):
 if any(p.stem.startswith(x) for x in ('moves-','abilities-','items-','feats-','edges-')) or p.name in ('conditions.json','core-rules.json','progression-rules.json'):
  data_files.append({'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)})
  walk(read(p),'',data_files[-1]['file'])
# AST inventory covers every production module; unresolved aliases and dynamic
# keys are retained in the full mutation index, not dropped as non-buffs.
runtime_files=[];mutations=[];storage=defaultdict(list)
containers={'buffs','coats','blessings','modifiers','registry','ability_triggers','custom_conditions','counters','spec','conditions','stage_loss_immune','status_immune','weather_immune','move_immune','keyword_immune'}
mutators={'append','extend','insert','remove','pop','popitem','clear','update','setdefault','add','discard','difference_update'}
def expr(node):
 try:return ast.unparse(node)
 except Exception:return '<dynamic>'
class Scan(ast.NodeVisitor):
 def __init__(self,file,lines):self.file=file;self.lines=lines;self.context=[]
 def visit_FunctionDef(self,node):
  self.context.append(node.name);self.generic_visit(node);self.context.pop()
 visit_AsyncFunctionDef=visit_FunctionDef
 def visit_ClassDef(self,node):
  self.context.append(node.name);self.generic_visit(node);self.context.pop()
 def record(self,node,kind,target):
  text=expr(target);roots=sorted({n.attr for n in ast.walk(target) if isinstance(n,ast.Attribute) and n.attr in containers})
  row={'file':self.file,'line':node.lineno,'function':'.'.join(self.context),'operation':kind,'target':text,'known_storage_roots':roots,'code':self.lines[node.lineno-1].strip()[:550],'semantic_review':'unreviewed'}
  mutations.append(row)
  for root in roots:storage[root].append(len(mutations)-1)
 def visit_Attribute(self,node):
  if isinstance(node.ctx,(ast.Store,ast.Del)):self.record(node,'attribute_write' if isinstance(node.ctx,ast.Store) else 'attribute_delete',node)
  self.generic_visit(node)
 def visit_Subscript(self,node):
  if isinstance(node.ctx,(ast.Store,ast.Del)):self.record(node,'mapping_write' if isinstance(node.ctx,ast.Store) else 'mapping_delete',node)
  self.generic_visit(node)
 def visit_Call(self,node):
  if isinstance(node.func,ast.Attribute) and node.func.attr in mutators:self.record(node,'mutation_call:'+node.func.attr,node.func.value)
  elif isinstance(node.func,ast.Name) and node.func.id in ('setattr','delattr'):
   self.record(node,'dynamic_'+node.func.id,node)
  self.generic_visit(node)
for p in sorted((ROOT/'engine').rglob('*.py')):
 if p.name.startswith('test') or '__pycache__' in p.parts:continue
 file=p.relative_to(ROOT).as_posix();s=p.read_text(encoding='utf-8-sig')
 tree=ast.parse(s,filename=file);runtime_files.append({'file':file,'sha256':sha(p),'lines':len(s.splitlines())})
 Scan(file,s.splitlines()).visit(tree)
counts=Counter(row['type'] for row in typed)
vocab=read(ROOT/'data/effect-vocabulary.json')['effects']
all_kinds=sorted(set(counts)|set(vocab))
types=[{'type':kind,'family':by_type.get(kind,'UNCLASSIFIED'),'declarations':counts[kind],'vocabulary_status':vocab.get(kind,{}).get('status'),'distinct_source_ids':len({r['source_id'] for r in typed if r['type']==kind and r['source_id']}),'examples':[{'file':r['file'],'pointer':r['pointer'],'source_id':r['source_id']} for r in typed if r['type']==kind][:5]} for kind in all_kinds]
report={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'purpose':'All frozen source rows, structured effect declarations and production runtime mutations inventoried for full buff-state review. Semantic review and unification remain active.','completion_credit':0,'coverage':{'source_files':len(source_files),'source_records':len(source_rows),'candidate_source_records':len(source_hits),'structured_data_files':len(data_files),'typed_declarations':len(typed),'distinct_type_labels':len(types),'unclassified_type_labels':[r['type'] for r in types if r['family']=='UNCLASSIFIED'],'production_runtime_files':len(runtime_files),'runtime_mutation_sites':len(mutations),'known_storage_mutation_sites':sum(bool(x['known_storage_roots']) for x in mutations),'semantic_review_complete':False},'boundaries':['All saved inputs visited; future/external source completeness not asserted.','No keyword hit, type count, handler name, state flag or AST write is an implementation/completion unit.','Non-matching original rows remain unreviewed to prevent keyword-only completeness claims.','AST aliases/dynamic field operations remain in the full index and need semantic owner/consumer/expiry tracing.','Raw structured alternatives are retained separately; runtime ruleset/errata source selection must be checked before merging.'],'families':taxonomy['families'],'types':types,'source_files':source_files,'source_rows':source_rows,'candidate_source_row_ids':source_hits,'data_files':data_files,'typed_declarations':typed,'runtime_files':runtime_files,'runtime_mutations':mutations,'storage_indexes':dict(storage)}
food_review_path=OUT/'category2-food-buff-source-contracts.json'
food_review=read(food_review_path) if food_review_path.exists() else None
if food_review:
 report['semantic_review_documents']=[{'file':food_review_path.relative_to(ROOT).as_posix(),'sha256':sha(food_review_path),'contract_groups':len(food_review['contracts']),'whole_food_review_complete':food_review['whole_food_review_complete']}]
 for source_row in source_rows:
  matches=[]
  for contract in food_review['contracts']:
   for anchor in contract['sources']:
    if anchor['file']!=source_row['file']:continue
    position=source_row['position']
    if ('position' in anchor and position==anchor['position']) or ('start' in anchor and anchor['start']<=position<=anchor['end']):matches.append(contract['id'])
  if matches:source_row['contract_review_references']=sorted(set(matches))
event_review_path=OUT/'category2-next-event-source-contracts.json'
if event_review_path.exists():
 event_review=read(event_review_path)
 report.setdefault('semantic_review_documents',[]).append({'file':event_review_path.relative_to(ROOT).as_posix(),'sha256':sha(event_review_path),'contract_groups':len(event_review['contracts']),'whole_buff_review_complete':False})
 for source_row in source_rows:
  matches=[]
  for contract in event_review['contracts']:
   for anchor in contract['sources']:
    if anchor['file']!=source_row['file']:continue
    position=source_row['position']
    if ('position' in anchor and position==anchor['position']) or ('start' in anchor and anchor['start']<=position<=anchor['end']):matches.append(contract['id'])
  if matches:source_row['event_contract_review_references']=sorted(set(matches))
gem_review_path=OUT/'category2-gem-source-contract.json'
if gem_review_path.exists():
 report.setdefault('semantic_review_documents',[]).append({'file':gem_review_path.relative_to(ROOT).as_posix(),'sha256':sha(gem_review_path),'contract_groups':1,'whole_buff_review_complete':False})
manual_review_path=OUT/'category2-manual-effect-source-contract.json'
if manual_review_path.exists():
 report.setdefault('semantic_review_documents',[]).append({'file':manual_review_path.relative_to(ROOT).as_posix(),'sha256':sha(manual_review_path),'contract_groups':1,'whole_buff_review_complete':False})

coat_review_path=OUT/'category2-coat-blessing-source-contracts.json'
coat_review=read(coat_review_path) if coat_review_path.exists() else None
if coat_review:
 report.setdefault('semantic_review_documents',[]).append({'file':coat_review_path.relative_to(ROOT).as_posix(),'sha256':sha(coat_review_path),'contract_groups':len(coat_review['contracts']),'whole_buff_review_complete':False})
 for source_row in source_rows:
  matches=[]
  for contract in coat_review['contracts']:
   for anchor in contract['sources']:
    if anchor['file']!=source_row['file']:continue
    position=source_row['position']
    if ('position' in anchor and position==anchor['position']) or ('start' in anchor and anchor['start']<=position<=anchor['end']):matches.append(contract['id'])
  if matches:source_row['coat_blessing_review_references']=sorted(set(matches))

periodic_review_path=OUT/'category2-periodic-coat-source-review.json'
if periodic_review_path.exists():
 report.setdefault('semantic_review_documents',[]).append({'file':periodic_review_path.relative_to(ROOT).as_posix(),'sha256':sha(periodic_review_path),'contract_groups':2,'whole_buff_review_complete':False})
team_review_path=OUT/'category2-team-blessing-source-review.json'
if team_review_path.exists():
 report.setdefault('semantic_review_documents',[]).append({'file':team_review_path.relative_to(ROOT).as_posix(),'sha256':sha(team_review_path),'contract_groups':3,'whole_buff_review_complete':False})
accuracy_review_path=OUT/'category2-move-accuracy-source-review.json'
if accuracy_review_path.exists():
 report.setdefault('semantic_review_documents',[]).append({'file':accuracy_review_path.relative_to(ROOT).as_posix(),'sha256':sha(accuracy_review_path),'contract_groups':1,'whole_buff_review_complete':False})
 accuracy_policy=read(ROOT/'data/move-accuracy-policy.json')
 accuracy_by_record={r['source_record']:{'source_id':sid,'classification':r['accuracy_requirement'],'review_file':accuracy_review_path.relative_to(ROOT).as_posix()} for sid,r in (accuracy_policy['sources']|accuracy_policy['unresolved']).items()}
 for source_row in report['source_rows']:
  if source_row['file']=='input/db/moves.csv' and source_row['position'] in accuracy_by_record:source_row['accuracy_admission_review']=accuracy_by_record[source_row['position']]
 report['runtime_admission_policy_files']=[{'file':'data/move-accuracy-policy.json','sha256':sha(ROOT/'data/move-accuracy-policy.json')}]
 report['coverage']['runtime_admission_policy_files']=len(report['runtime_admission_policy_files'])
temp_review_path=OUT/'category2-temporary-hp-lifetime-source-review.json'
if temp_review_path.exists():
 report.setdefault('semantic_review_documents',[]).append({'file':temp_review_path.relative_to(ROOT).as_posix(),'sha256':sha(temp_review_path),'contract_groups':1,'whole_buff_review_complete':False})
 report['runtime_resource_policy_files']=[{'file':'data/temporary-hp-policy.json','sha256':sha(ROOT/'data/temporary-hp-policy.json')}]
 report['coverage']['runtime_resource_policy_files']=len(report['runtime_resource_policy_files'])
 report['supporting_review_documents']=[{'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in [OUT/'category2-temporary-hp-source-inventory.json',OUT/'category2-move-accuracy-column-correction.json'] if p.exists()]
helping_review_path=OUT/'category2-helping-hand-source-review.json'
helping_review=read(helping_review_path) if helping_review_path.exists() else None
if helping_review:
 report['semantic_review_documents'].append({'file':helping_review_path.relative_to(ROOT).as_posix(),'sha256':sha(helping_review_path),'contract_groups':1,'whole_buff_review_complete':False})
roll_review_path=OUT/'category2-roll-buff-source-contracts.json'
roll_review=read(roll_review_path) if roll_review_path.exists() else None
if roll_review:
 report['semantic_review_documents'].append({'file':roll_review_path.relative_to(ROOT).as_posix(),'sha256':sha(roll_review_path),'contract_groups':len(roll_review['contracts']),'whole_buff_review_complete':False})
 contracts={c['source_id']:c for c in roll_review['contracts']}
 for declaration in report['typed_declarations']:
  if declaration['type']=='next_roll_bonus' and declaration['source_id'] in contracts:
   declaration['source_contract_review']=roll_review_path.relative_to(ROOT).as_posix()
   declaration['reviewed_semantic_family']=contracts[declaration['source_id']]['semantic_family']
   declaration['native_migration_complete']=False
tailwind_review_path=OUT/'category2-tailwind-source-review.json'
if tailwind_review_path.exists():
 report['semantic_review_documents'].append({'file':tailwind_review_path.relative_to(ROOT).as_posix(),'sha256':sha(tailwind_review_path),'contract_groups':1,'whole_buff_review_complete':False})
 for declaration in report['typed_declarations']:
  if declaration['source_id']=='move/순풍':declaration['source_review']='data/verification/category2-tailwind-source-review.json'
status_review_path=OUT/'category2-status-family-source-review.json'
if status_review_path.exists():
 report['semantic_review_documents'].append({'file':status_review_path.relative_to(ROOT).as_posix(),'sha256':sha(status_review_path),'contract_groups':5,'whole_buff_review_complete':False})
parameter_review_path=OUT/'category2-parameterized-condition-source-review.json'
if parameter_review_path.exists():
 report['semantic_review_documents'].append({'file':parameter_review_path.relative_to(ROOT).as_posix(),'sha256':sha(parameter_review_path),'contract_groups':4,'whole_buff_review_complete':False})
persistent_review_path=OUT/'category2-persistent-condition-source-review.json'
if persistent_review_path.exists():
 report['semantic_review_documents'].append({'file':persistent_review_path.relative_to(ROOT).as_posix(),'sha256':sha(persistent_review_path),'contract_groups':3,'whole_buff_review_complete':False})
recovery_review_path=OUT/'category2-recovery-family-source-review.json'
if recovery_review_path.exists():
 report['semantic_review_documents'].append({'file':recovery_review_path.relative_to(ROOT).as_posix(),'sha256':sha(recovery_review_path),'contract_groups':2,'whole_buff_review_complete':False})
rest_recovery_review_path=OUT/'category2-rest-recovery-source-review.json'
if rest_recovery_review_path.exists():
 report['semantic_review_documents'].append({'file':rest_recovery_review_path.relative_to(ROOT).as_posix(),'sha256':sha(rest_recovery_review_path),'contract_groups':4,'whole_buff_review_complete':False})
injury_recovery_review_path=OUT/'category2-injury-recovery-source-review.json'
if injury_recovery_review_path.exists():
 report['semantic_review_documents'].append({'file':injury_recovery_review_path.relative_to(ROOT).as_posix(),'sha256':sha(injury_recovery_review_path),'contract_groups':3,'whole_buff_review_complete':False})
spatial_body_review_path=OUT/'category2-spatial-body-source-review.json'
if spatial_body_review_path.exists():
 report['semantic_review_documents'].append({'file':spatial_body_review_path.relative_to(ROOT).as_posix(),'sha256':sha(spatial_body_review_path),'contract_groups':4,'whole_buff_review_complete':False})
base_stage_abilities_review_path=OUT/'category2-base-stage-abilities-source-review.json'
if base_stage_abilities_review_path.exists():
 report['semantic_review_documents'].append({'file':base_stage_abilities_review_path.relative_to(ROOT).as_posix(),'sha256':sha(base_stage_abilities_review_path),'contract_groups':3,'whole_buff_review_complete':False})
timed_type_state_review_path=OUT/'category2-timed-type-state-source-review.json'
if timed_type_state_review_path.exists():
 report['semantic_review_documents'].append({'file':timed_type_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(timed_type_state_review_path),'contract_groups':1,'whole_buff_review_complete':False})
permanent_type_sync_review_path=OUT/'category2-permanent-type-sync-source-review.json'
if permanent_type_sync_review_path.exists():
 report['semantic_review_documents'].append({'file':permanent_type_sync_review_path.relative_to(ROOT).as_posix(),'sha256':sha(permanent_type_sync_review_path),'contract_groups':7,'whole_buff_review_complete':False})
source_derived_example_species_review_path=OUT/'category2-source-derived-example-species-source-review.json'
if source_derived_example_species_review_path.exists():
 report['semantic_review_documents'].append({'file':source_derived_example_species_review_path.relative_to(ROOT).as_posix(),'sha256':sha(source_derived_example_species_review_path),'contract_groups':3,'whole_buff_review_complete':False})
selected_ability_transitions_review_path=OUT/'category2-selected-ability-transitions-source-review.json'
if selected_ability_transitions_review_path.exists():
 report['semantic_review_documents'].append({'file':selected_ability_transitions_review_path.relative_to(ROOT).as_posix(),'sha256':sha(selected_ability_transitions_review_path),'contract_groups':9,'whole_buff_review_complete':False})
food_capacity_abilities_review_path=OUT/'category2-food-capacity-abilities-source-review.json'
if food_capacity_abilities_review_path.exists():
 report['semantic_review_documents'].append({'file':food_capacity_abilities_review_path.relative_to(ROOT).as_posix(),'sha256':sha(food_capacity_abilities_review_path),'contract_groups':3,'whole_buff_review_complete':False})
mega_forms_review_path=OUT/'category2-mega-forms-source-review.json'
if mega_forms_review_path.exists():
 report['semantic_review_documents'].append({'file':mega_forms_review_path.relative_to(ROOT).as_posix(),'sha256':sha(mega_forms_review_path),'contract_groups':6,'whole_buff_review_complete':False})
contest_common_state_review_path=OUT/'category2-contest-common-state-source-review.json'
if contest_common_state_review_path.exists():
 report['semantic_review_documents'].append({'file':contest_common_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(contest_common_state_review_path),'contract_groups':29,'whole_buff_review_complete':False})
paired_contest_state_review_path=OUT/'category2-paired-contest-state-source-review.json'
if paired_contest_state_review_path.exists():
 report['semantic_review_documents'].append({'file':paired_contest_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(paired_contest_state_review_path),'contract_groups':4,'whole_buff_review_complete':False})
weather_shared_state_review_path=OUT/'category2-weather-shared-state-source-review.json'
if weather_shared_state_review_path.exists():
 report['semantic_review_documents'].append({'file':weather_shared_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(weather_shared_state_review_path),'contract_groups':6,'whole_buff_review_complete':False})
supplemental_move_grants_review_path=OUT/'category2-supplemental-move-grants-source-review.json'
if supplemental_move_grants_review_path.exists():
 report['semantic_review_documents'].append({'file':supplemental_move_grants_review_path.relative_to(ROOT).as_posix(),'sha256':sha(supplemental_move_grants_review_path),'contract_groups':2,'whole_buff_review_complete':False})
learned_capabilities_review_path=OUT/'category2-learned-capabilities-source-review.json'
if learned_capabilities_review_path.exists():
 report['semantic_review_documents'].append({'file':learned_capabilities_review_path.relative_to(ROOT).as_posix(),'sha256':sha(learned_capabilities_review_path),'contract_groups':0,'reviewed_named_moves':35,'whole_buff_review_complete':False})
numeric_move_capabilities_review_path=OUT/'category2-numeric-move-capabilities-source-review.json'
if numeric_move_capabilities_review_path.exists():
 report['semantic_review_documents'].append({'file':numeric_move_capabilities_review_path.relative_to(ROOT).as_posix(),'sha256':sha(numeric_move_capabilities_review_path),'contract_groups':0,'reviewed_numeric_moves':8,'whole_buff_review_complete':False})
move_capability_lifetimes_review_path=OUT/'category2-move-capability-lifetimes-source-review.json'
if move_capability_lifetimes_review_path.exists():
 report['semantic_review_documents'].append({'file':move_capability_lifetimes_review_path.relative_to(ROOT).as_posix(),'sha256':sha(move_capability_lifetimes_review_path),'contract_groups':2,'whole_buff_review_complete':False})
whole_innate_protection_review_path=OUT/'category2-whole-innate-protection-source-review.json'
if whole_innate_protection_review_path.exists():
 report['semantic_review_documents'].append({'file':whole_innate_protection_review_path.relative_to(ROOT).as_posix(),'sha256':sha(whole_innate_protection_review_path),'contract_groups':1,'whole_buff_review_complete':False})
body_size_modes_review_path=OUT/'category2-body-size-modes-source-review.json'
if body_size_modes_review_path.exists():
 report['semantic_review_documents'].append({'file':body_size_modes_review_path.relative_to(ROOT).as_posix(),'sha256':sha(body_size_modes_review_path),'contract_groups':4,'whole_buff_review_complete':False})
flinch_core_state_review_path=OUT/'category2-flinch-core-state-source-review.json'
if flinch_core_state_review_path.exists():
 report['semantic_review_documents'].append({'file':flinch_core_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(flinch_core_state_review_path),'contract_groups':1,'whole_buff_review_complete':False})
flinch_errata_state_review_path=OUT/'category2-flinch-errata-state-source-review.json'
if flinch_errata_state_review_path.exists():
 report['semantic_review_documents'].append({'file':flinch_errata_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(flinch_errata_state_review_path),'contract_groups':1,'whole_buff_review_complete':False})
weather_template_state_review_path=OUT/'category2-weather-template-state-source-review.json'
if weather_template_state_review_path.exists():
 report['semantic_review_documents'].append({'file':weather_template_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(weather_template_state_review_path),'contract_groups':2,'whole_buff_review_complete':False})
weather_state_certification_review_path=OUT/'category2-weather-state-certification-source-review.json'
if weather_state_certification_review_path.exists():
 report['semantic_review_documents'].append({'file':weather_state_certification_review_path.relative_to(ROOT).as_posix(),'sha256':sha(weather_state_certification_review_path),'contract_groups':5,'whole_buff_review_complete':False})
melee_reach_review_path=OUT/'category2-melee-reach-source-review.json'
if melee_reach_review_path.exists():
 report['semantic_review_documents'].append({'file':melee_reach_review_path.relative_to(ROOT).as_posix(),'sha256':sha(melee_reach_review_path),'contract_groups':2,'whole_buff_review_complete':False})
capability_traits_review_path=OUT/'category2-capability-traits-source-review.json'
if capability_traits_review_path.exists():
 report['semantic_review_documents'].append({'file':capability_traits_review_path.relative_to(ROOT).as_posix(),'sha256':sha(capability_traits_review_path),'contract_groups':4,'whole_buff_review_complete':False})
environment_capabilities_review_path=OUT/'category2-environment-capabilities-source-review.json'
if environment_capabilities_review_path.exists():
 report['semantic_review_documents'].append({'file':environment_capabilities_review_path.relative_to(ROOT).as_posix(),'sha256':sha(environment_capabilities_review_path),'contract_groups':3,'whole_buff_review_complete':False})
naturewalk_state_review_path=OUT/'category2-naturewalk-state-source-review.json'
if naturewalk_state_review_path.exists():
 report['semantic_review_documents'].append({'file':naturewalk_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(naturewalk_state_review_path),'contract_groups':1,'whole_buff_review_complete':False})
voluntary_silence_review_path=OUT/'category2-voluntary-silence-source-review.json'
if voluntary_silence_review_path.exists():
 report['semantic_review_documents'].append({'file':voluntary_silence_review_path.relative_to(ROOT).as_posix(),'sha256':sha(voluntary_silence_review_path),'contract_groups':1,'whole_buff_review_complete':False})
invisibility_lifecycle_review_path=OUT/'category2-invisibility-lifecycle-source-review.json'
if invisibility_lifecycle_review_path.exists():
 report['semantic_review_documents'].append({'file':invisibility_lifecycle_review_path.relative_to(ROOT).as_posix(),'sha256':sha(invisibility_lifecycle_review_path),'contract_groups':3,'whole_buff_review_complete':False})
invisibility_readiness_amendment_path=OUT/'category2-invisibility-readiness-amendment.json'
if invisibility_readiness_amendment_path.exists():
 report['semantic_review_documents'].append({'file':invisibility_readiness_amendment_path.relative_to(ROOT).as_posix(),'sha256':sha(invisibility_readiness_amendment_path),'contract_groups':1,'whole_buff_review_complete':False})
mount_relation_evidence_path=OUT/'category2-mount-relation-evidence.json'
if mount_relation_evidence_path.exists():
 report['supporting_review_documents'].append({'file':mount_relation_evidence_path.relative_to(ROOT).as_posix(),'sha256':sha(mount_relation_evidence_path),'whole_buff_review_complete':False})
bloom_appearance_review_path=OUT/'category2-bloom-appearance-source-review.json'
if bloom_appearance_review_path.exists():
 report['semantic_review_documents'].append({'file':bloom_appearance_review_path.relative_to(ROOT).as_posix(),'sha256':sha(bloom_appearance_review_path),'contract_groups':1,'whole_buff_review_complete':False})
blender_state_evidence_path=OUT/'category2-blender-state-evidence.json'
if blender_state_evidence_path.exists():
 report['supporting_review_documents'].append({'file':blender_state_evidence_path.relative_to(ROOT).as_posix(),'sha256':sha(blender_state_evidence_path),'whole_buff_review_complete':False})
mulch_soil_state_review_path=OUT/'category2-mulch-soil-state-source-review.json'
if mulch_soil_state_review_path.exists():
 report['semantic_review_documents'].append({'file':mulch_soil_state_review_path.relative_to(ROOT).as_posix(),'sha256':sha(mulch_soil_state_review_path),'contract_groups':1,'whole_buff_review_complete':False})
weathershape_appearance_review_path=OUT/'category2-weathershape-appearance-source-review.json'
if weathershape_appearance_review_path.exists():
 report['semantic_review_documents'].append({'file':weathershape_appearance_review_path.relative_to(ROOT).as_posix(),'sha256':sha(weathershape_appearance_review_path),'contract_groups':1,'whole_buff_review_complete':False})
aura_observation_review_path=OUT/'category2-aura-observation-source-review.json'
if aura_observation_review_path.exists():
 report['semantic_review_documents'].append({'file':aura_observation_review_path.relative_to(ROOT).as_posix(),'sha256':sha(aura_observation_review_path),'contract_groups':2,'whole_buff_review_complete':False})
aura_pulse_consent_review_path=OUT/'category2-aura-pulse-consent-source-review.json'
if aura_pulse_consent_review_path.exists():
 report['semantic_review_documents'].append({'file':aura_pulse_consent_review_path.relative_to(ROOT).as_posix(),'sha256':sha(aura_pulse_consent_review_path),'contract_groups':1,'whole_buff_review_complete':False})
dream_mist_sharing_review_path=OUT/'category2-dream-mist-sharing-source-review.json'
if dream_mist_sharing_review_path.exists():
 report['semantic_review_documents'].append({'file':dream_mist_sharing_review_path.relative_to(ROOT).as_posix(),'sha256':sha(dream_mist_sharing_review_path),'contract_groups':1,'whole_buff_review_complete':False})
capability_products_review_path=OUT/'category2-capability-products-source-review.json'
if capability_products_review_path.exists():
 report['semantic_review_documents'].append({'file':capability_products_review_path.relative_to(ROOT).as_posix(),'sha256':sha(capability_products_review_path),'contract_groups':1,'whole_buff_review_complete':False})
keystone_links_review_path=OUT/'category2-keystone-links-source-review.json'
if keystone_links_review_path.exists():
 report['semantic_review_documents'].append({'file':keystone_links_review_path.relative_to(ROOT).as_posix(),'sha256':sha(keystone_links_review_path),'contract_groups':1,'whole_buff_review_complete':False})
soulless_default_review_path=OUT/'category2-soulless-default-source-review.json'
if soulless_default_review_path.exists():
 report['semantic_review_documents'].append({'file':soulless_default_review_path.relative_to(ROOT).as_posix(),'sha256':sha(soulless_default_review_path),'contract_groups':1,'whole_buff_review_complete':False})
shapeshift_appearance_review_path=OUT/'category2-shapeshift-appearance-source-review.json'
if shapeshift_appearance_review_path.exists():
 report['semantic_review_documents'].append({'file':shapeshift_appearance_review_path.relative_to(ROOT).as_posix(),'sha256':sha(shapeshift_appearance_review_path),'contract_groups':1,'whole_buff_review_complete':False})
minimize_distinction_review_path=OUT/'category2-minimize-distinction-source-review.json'
if minimize_distinction_review_path.exists():
 report['semantic_review_documents'].append({'file':minimize_distinction_review_path.relative_to(ROOT).as_posix(),'sha256':sha(minimize_distinction_review_path),'contract_groups':1,'whole_buff_review_complete':False})
report['runtime_capability_policy_files']=[{'file':'data/move-capability-policy.json','sha256':sha(ROOT/'data/move-capability-policy.json')}]
report['coverage']['runtime_capability_policy_files']=len(report['runtime_capability_policy_files'])
report['runtime_policy_files']=[{'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for p in sorted((ROOT/'data').glob('*effect-policy.json'))]+[{'file':name,'sha256':sha(ROOT/name)} for name in ['data/food-buff-policy.json','data/base-stage-abilities.json','data/type-sync-policy.json','data/example-species-policy.json','data/ability-transition-policy.json','data/ability-capacity-policy.json','data/mega-form-policy.json']]
report['coverage']['runtime_policy_files']=len(report['runtime_policy_files'])

dump(OUT/'category2-buff-state-audit.json',report)
# A compact searchable review surface; JSON retains every row, declaration,
# non-matching source row, dynamic write and full payload.
h=html.escape
rows=''.join('<tr><td>'+h(r['type'])+'</td><td>'+h(r['family'])+'</td><td>'+str(r['declarations'])+'</td><td>'+str(r['distinct_source_ids'])+'</td><td>'+h(str(r['vocabulary_status']))+'</td></tr>' for r in types)
family_rows=''.join('<tr><td>'+h(r['id'])+'</td><td>'+h(r['name'])+'</td><td>'+h(r['contract'])+'</td></tr>' for r in taxonomy['families'])
summary=h(json.dumps(report['coverage'],ensure_ascii=False,indent=2))
page="""<!doctype html><html lang="ko"><meta charset="utf-8"><title>버프·지속효과 전수 조사</title><style>body{font:15px system-ui;margin:32px auto;max-width:1200px;padding:0 20px;color:#202832}h1{font-size:26px}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #d7dfe8;padding:8px;text-align:left}th{background:#edf3f8}input{padding:12px;width:90%}pre{background:#f4f7fa;padding:18px;white-space:pre-wrap}.note{background:#fff3da;padding:18px}</style><h1>버프·지속효과 전수 조사</h1><p class="note">전수 색인 이후 개별 원문 검토와 공통 구조 이관을 진행 중입니다. 전체 버프 검토·구현 완료를 뜻하지 않습니다. 색인·분류 자체의 완료 가산은 0이며, 검증된 구현 조항은 별도 완료 장부에 기록합니다.</p><p><a href="category2-buff-state-audit.json">전체 원문/데이터/코드 색인</a> · <a href="../buff-state-direction.json">통일 방향과 단계별 검증</a></p><h2>범위</h2><pre>"""+summary+'</pre><h2>상위 분류</h2><table><tr><th>ID</th><th>종류</th><th>보존할 차이</th></tr>'+family_rows+'</table><h2>형식에 나타난 효과 종류</h2><p>중복 데이터층과 비버프 type 필드를 포함한 라벨 목록입니다. 이름이 같다고 의미가 같은 효과로 합치지 않습니다.</p><input id="search" placeholder="효과명 또는 분류 검색"><table id="types"><thead><tr><th>type</th><th>분류</th><th>선언 수</th><th>원본 ID 수</th><th>기존 어휘 상태(완료 증명 아님)</th></tr></thead><tbody>'+rows+'</tbody></table><script>document.getElementById("search").addEventListener("input",e=>{const q=e.target.value.toLowerCase();document.querySelectorAll("#types tbody tr").forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q))})</script></html>'
direction=read(ROOT/'data/buff-state-direction.json')
findings=''.join('<li><b>'+h(row['id'])+'</b> '+h(row['finding'])+'<br><small>'+h(row['status'])+'</small></li>' for row in direction['findings'])
steps=''.join('<li><b>'+h(row['family'])+'</b> '+h(row['work'])+'</li>' for row in direction['review_order'])
page=page.replace('<h2>형식에 나타난 효과 종류</h2>','<h2>통일 방향</h2><p>'+h(direction['decision'])+'</p><h2>확인한 문제와 미해결 지점</h2><ul>'+findings+'</ul><h2>이관 순서</h2><ol>'+steps+'</ol><h2>형식에 나타난 효과 종류</h2>')
migration=direction.get('first_native_migration')
if migration:
 details='<h2>첫 통일 묶음: 음식 효과</h2><p>공통 인스턴스에 원래 출처·현재 보유자·효과 정의·한도·수명·소비 이력을 보존합니다. 전체 버프 이관은 계속 진행 중입니다.</p><p><a href="'+h(Path(migration['evidence']).name)+'">실제 실행 및 저장 복원 검증 결과</a> · <a href="'+h(Path(migration['contract_review']).name)+'">음식 계열 원문 계약 검토</a></p>'
 if food_review:
  details+='<table><tr><th>계약 그룹</th><th>보존할 차이</th><th>현재 범위</th></tr>'+''.join('<tr><td>'+h(x['id'])+'</td><td>'+h(x['contract'])+'</td><td>'+h(x['status'])+'</td></tr>' for x in food_review['contracts'])+'</table>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
event_migration=direction.get('event_native_migration')
if event_migration:
 details='<h2>다음 적중·다음 자기 턴 효과 이관</h2><p>충전·승리의춤·예민해지기·정조준을 같은 효과 인스턴스와 기존 턴 타이밍에 연결했습니다. 다음 성공 적중에서 소비되는 효과와 다음 자기 턴 동안 적용되고 종료되는 효과를 구분합니다. 한 기술의 여러 대상에도 실제 활성화 단위의 치명타 결정을 유지합니다.</p><p><a href="'+h(Path(event_migration['evidence']).name)+'">4조항 실행·복원 검증</a> · <a href="'+h(Path(event_migration['source_review']).name)+'">다음 사건 원문 대조와 남은 충돌</a></p><p class="note">도우미의 턴/라운드 차이는 후속 원문 검토에서 번역 오류로 정정했습니다. 독립 소비 이관은 아래에 정리하며, 중복 부여 규칙 등은 미완료입니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
gem_migration=direction.get('gem_native_migration')
if gem_migration:
 details='<h2>타입주얼 18종 공통 이관</h2><p>실제 주얼을 자유 행동으로 소비하면 출처와 실물 소비 기록을 가진 공통 효과가 생깁니다. 다음 해당 타입 기술 사용 시 소비하며, 빗나감과 여러 대상의 한 기술 사용도 구분합니다. +3은 고정 피해가 아니라 기본 피해량(DB)에 적용합니다. 트레이너의 반대손·장신구 슬롯 및 GM·파일 복원을 검증했습니다.</p><p><a href="'+h(Path(gem_migration['evidence']).name)+'">실행·복원 검증과 남은 검사 실패</a> · <a href="'+h(Path(gem_migration['source_review']).name)+'">주얼 원문 계약</a></p><p class="note">18종은 원래 37종 도구 표 조항의 일부입니다. 이 묶음의 원조항 완료 가산은 0입니다. 기존 상위 검증 장부의 정합성 검사 2개는 미해결이며, 전체 프로젝트 검사 통과를 주장하지 않습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
manual_migration=direction.get('manual_native_migration')
if manual_migration:
 details='<h2>배터리: 다른 아군에게 주는 효과</h2><p>부여자와 보유자를 구분하고 실제 신속 행동·장면 사용 횟수와 연결했습니다. 다음 특수 기술 사용에서 한 번 소비하며, 실제 전기 타입이면 추가 피해식을 교체합니다. 빗나감, 치명타, 여러 대상, 부여자 특성 상실 및 저장·복원을 검증했습니다.</p><p><a href="'+h(Path(manual_migration['evidence']).name)+'">404개 관련 검사와 완료 증거</a> · <a href="'+h(Path(manual_migration['source_review']).name)+'">배터리 원문 계약</a></p><p>중복 원문을 제외한 원조항 1개를 완료로 집계했습니다. 전체 버프 통일은 진행 중입니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if coat_review:
 details='<h2>코트·축복 원문 대조: 40개 계약 그룹</h2><p>9개 코트 관련 기술, 9개 축복 관련 기술, 4개 특성, 4개 날씨와 개인 파동 축복, 전달·변환·제거 규칙을 구분했습니다. 이관 전 34차 묶음의 22개 실제 호출 진단 중 6개가 반환하고 16개가 거절됐습니다. 반환한 경로도 전체 효과 구현을 증명하지 않습니다.</p><p><a href="category2-coat-blessing-source-contracts.json">원문·계약·구현 순서</a> · <a href="category2-coat-blessing-native-probes.json">실제 호출 결과</a></p><p class="note">코트는 보유자별 인스턴스, 일반 소비형 축복은 아군 공유 풀, 순풍은 비중첩 시간 효과, 파동 축복은 개인 한도입니다. 이 조사 묶음의 완료 가산은 0입니다.</p>'
 details+='<table><tr><th>원문 효과·연산</th><th>분류</th><th>보존할 규칙</th></tr>'+''.join('<tr><td>'+h(x['name'])+'</td><td>'+h(x['family'])+'</td><td>'+h(x['contract'])+'</td></tr>' for x in coat_review['contracts'])+'</table>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
periodic_migration=direction.get('periodic_coat_migration')
if periodic_migration:
 details='<h2>아쿠아링·뿌리박기: 반복 코트 부분 이관</h2><p>두 코트의 실제 생성, 보유자 턴 시작 회복, 밀기 방지, 클리어스모그·안개제거의 종료 이력을 공통 효과 인스턴스에 연결했습니다. 턴 시계는 특정 효과 목록의 존재와 무관하게 증가합니다. 신규 검사 11개가 통과했습니다.</p><p><a href="'+h(Path(periodic_migration['evidence']).name)+'">통합·후속 검사와 부분 구현 범위</a> · <a href="'+h(Path(periodic_migration['source_review']).name)+'">한국어·영문 차이 및 남은 상태 규칙</a> · <a href="category2-gift-reregistration-gap.json">기프트 재등록 진단과 수정 결과</a></p><p class="note">실제 교체 대상에게 전달, 동일 출처 중첩, 뿌리박기의 원문 차이가 남아 완료 가산은 0입니다. 새 효과 객체가 있다는 사실을 원조항 완료로 세지 않습니다. 기존 검증 장부 정합성 실패도 별도 미해결입니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
restore=direction.get('feature_registration_restore')
if restore:
 details='<h2>재주 실행 목록 복원 수정</h2><p>시트만 복원한 뒤 재주를 재등록할 때 실행 목록이 비어 있던 문제를 수정했습니다. 남은 사용 횟수를 보존하고 반복 등록·출처 제거·전체 저장 복원을 확인했습니다. 신규 4개와 기존 226개 검사가 통과했으며 완료 조항 가산은 0입니다.</p><p><a href="'+h(Path(restore['evidence']).name)+'">수정 범위와 검사 결과</a></p><p class="note">이 변경은 실행 항목 복원에 한정됩니다. 모든 버프의 시트 단독 복원을 의미하지 않습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
team=direction.get('team_blessing_partial_migration')
if team:
 details='<h2>빛의장막·리플렉터·오로라베일: 팀 공유 축복 부분 이관</h2><p>트레이너와 포켓몬이 단일 사용량을 공유하고, 실제 피해 사건에서 선택한 경우에만 소비합니다. 생성자 기절·교체 뒤에도 남으며, 원래 피해 주사위를 다시 굴리지 않고 저항 단계를 적용합니다. 양측 제거·소속 교환·저장 복원과 실제 범위 공격도 검증했습니다. 최종 영향범위 검사는 신규 14개와 기존 181개가 통과했습니다.</p><p><a href="'+h(Path(team['evidence']).name)+'">검증 결과와 부분 구현 범위</a> · <a href="'+h(Path(team['source_review']).name)+'">원문 계약과 남은 시전·중첩 검토</a></p><p class="note">동일 축복 재시전·중첩 등 독립 계약은 미완료입니다. AC 없음 시전은 아래 공통 처리로 보완했으며 조항 완료 가산은 0입니다. 원장에 제외된 빛의장막·리플렉터를 분모에 임의 추가하지 않았습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
accuracy_migration=direction.get('common_move_accuracy_admission')
if accuracy_migration:
 details='<h2>버프 생성 공통 절차: 명중 판정 없음과 AC 0 분리</h2><p>원문 AC가 --인 변화기 203개를 공통 무판정 경로에 연결했습니다. 자연의힘의 효과 확인 표기는 별도로 남깁니다. 따라하기의 효과 확인은 위력 열이며 AC는 --입니다. 흐릿함·조건부 AC 지정은 판정을 도입하며, 필중 공격의 치명타 굴림은 유지합니다.</p><p><a href="'+h(Path(accuracy_migration['evidence']).name)+'">검증 결과와 적용 범위</a> · <a href="'+h(Path(accuracy_migration['source_review']).name)+'">원문 대조 및 분류 정정</a></p><p class="note">203개는 저장된 무판정 정의 수이며 버프 수나 완료 조항 수가 아닙니다. 버프 전체 의미 대조와 이관은 계속 진행 중입니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
temporary_hp=direction.get('temporary_hp_lifetime')
if temporary_hp is None and (OUT/'category2-temporary-hp-lifetime-completion.json').exists():
 temporary_hp={'evidence':'data/verification/category2-temporary-hp-lifetime-completion.json','source_review':'data/verification/category2-temporary-hp-lifetime-source-review.json'}
if temporary_hp:
 details='<h2>임시 체력: 공통 잔량과 전투 밖 만료 시계</h2><p>영문 원본과 대조해 전투 밖에서 누적 5분 후 만료하도록 바로잡았습니다. 실제 전투 참가자의 시계만 멈추며 비참가자는 계속 흐릅니다. 낮거나 같은 값의 부여는 남은 시간을 갱신하지 않습니다. 상태 치료·실제 볼 복귀·GM 및 파일 저장 복원도 확인합니다. 꿀도둑은 실제 음식 버프 탈취가 끝난 뒤에만 임시 체력을 부여합니다.</p><p><a href="'+h(Path(temporary_hp['evidence']).name)+'">C07-157 검증 범위와 결과</a> · <a href="'+h(Path(temporary_hp['source_review']).name)+'">번역 충돌 판단과 원문</a> · <a href="category2-temporary-hp-source-inventory.json">임시 체력 관련 원문 후보94곳</a></p><p class="note">음식·도시락통의 합산 예외와 변신별 획득 제한은 별도 미완료입니다. 예전 저장본에 시계 근거가 없으면 잔량을 보존하고 명시적 시간 확인 전까지 사용을 보류합니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if roll_review:
 details='<h2>같은 이름의 굴림 버프 4종: 소비 단위 분리</h2><p>next_roll_bonus라는 같은 추출 형식이 독립적인 다음 굴림, 시간 동안 모든 굴림, 한 공격에 묶인 보너스를 섞고 있었습니다. 공통 인스턴스 안에서 적용 사건·소비 묶음·종료 조건을 따로 정의해야 합니다.</p><table><tr><th>효과</th><th>검토한 실제 계약</th><th>이관 상태</th></tr>'+''.join('<tr><td>'+h(c['name'])+'</td><td>'+h(c['semantic_family'])+'</td><td>원문 형태 대조 완료 · 실제 실행 이관 미완료</td></tr>' for c in roll_review['contracts'])+'</table><p><a href="category2-roll-buff-source-contracts.json">원문 8곳과 보존할 차이</a></p><p class="note">도우미의 수명은 원본의 이번 라운드로 정정했습니다. 같은 출처의 중복 부여와 더블 샷의 두 번째 공격 연장 예외는 별도 해결이 필요합니다. 이 추가 조사에 대한 완료 조항 가산은 0입니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if helping_review and (OUT/'category2-roll-components-partial-evidence.json').exists():
 details='<h2>도우미: 명중·피해 보너스 독립 소비</h2><p>기존 next_attack 스칼라를 공유 효과 인스턴스의 성분별 사용 이력으로 옮겼습니다. 명중은 빗나가도 사용되고, 남은 피해 보너스는 따로 유지됩니다. 무판정 기술은 소비하지 않으며, 실제 볼 투척과 범위 공격의 공유 명중굴림도 같은 소비 경로를 사용합니다. 이번 라운드 종료 시 남은 성분이 만료되고 GM·파일 복원이 이를 보존합니다.</p><p><a href="category2-roll-components-partial-evidence.json">실제 실행·복원 검증과 남은 범위</a> · <a href="category2-helping-hand-source-review.json">원문 대조와 번역 판단</a></p><p class="note">같은 출처를 중복 부여할 때의 합성 규칙과 남은 굴림 소비자 대조가 완료되지 않았습니다. 조항 가산은 0입니다. 현재 형식에서 출처 없는 기존 스칼라는 보존하되 해석 전 실행을 거절하며, 다른 규칙 지문의 과거 저장본을 자동 이관하지는 않습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-tailwind-completion.json').exists():
 details='<h2>순풍: 팀 지속 보너스와 습득 재능</h2><p>시전자별 원본 효과를 보존하며 모든 아군 트레이너·포켓몬의 이니셔티브에 +5를 한 번만 더합니다. 재시전을 금지하지 않고 중복 보너스만 막습니다. 전투 종료·안개제거·코트체인지와 실제 행동 순서, 저장 복원을 연결했습니다. 기술 습득에 따른 세찬바람 재능은 기술 보유에서 산출하며 잊었을 때 해당 출처의 기여만 사라집니다.</p><p><a href="category2-tailwind-completion.json">검증 결과와 조항 집계</a> · <a href="category2-tailwind-source-review.json">원문·수명·합성 근거</a></p><p class="note">마비·고정 이니셔티브와의 일반 합성 순서, 세찬바람 자체의 행동 규칙, 다른 기술의 습득 재능과 나머지 버프 전체 구현을 의미하지 않습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-status-family-completion.json').exists():
 details='<h2>상태 공통 처리: 원조항 5개 묶음</h2><p>같은 상태 집합에서 지속·휘발·별도 상태를 구분하고 트레이너·포켓몬의 치료, 기절, 복귀, 전투 종료를 함께 처리합니다. 악몽의 잠듦 의존성과 실제 내성 체크 손실, 저주의 실제 기본행동 조건, 난동의 행동 제한을 연결했습니다. 임시HP는 별도 자원으로 유지합니다.</p><p><a href="category2-status-family-completion.json">묶음 검증과 조항 집계</a> · <a href="category2-status-family-source-review.json">23개 상태 분류와 원문 대조</a></p><p class="note">억압의 1라운드 지속, 봉인의 기술별 인자와 나머지 개별 상태 조항은 미완료입니다. 분류표에 있다는 이유로 완료 처리하지 않습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-parameterized-condition-completion.json').exists():
 details='<h2>추가 정보를 가진 상태: 공통 인스턴스</h2><p>사슬묶기의 기술별 금지, 헤롱헤롱의 실제 상대 참조, 억압의 적용·종료 시점을 공통 효과 기록으로 저장합니다. 실제 기술 사용과 피해 계산, 정확한 한 라운드 종료, 치료 및 저장 복원을 연결했습니다. Other의 일반 치료 제외 조항도 함께 검증했습니다.</p><p><a href="category2-parameterized-condition-completion.json">원조항 4개와 실행 검증</a> · <a href="category2-parameterized-condition-source-review.json">원문·개정판·예외 구분</a></p><p class="note">풀죽음 수치, 특수 억압의 종료 예외, 여러 다른 헤롱헤롱 출처의 합성 및 개별 재주·특성 생산자는 별도 미완료입니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-persistent-condition-completion.json').exists():
 details='<h2>지속 상태: 화상·얼음·독</h2><p>화상·독의 행동 조건부 손실을 공유하며, 맹독은 공통 상태 인스턴스에 출처와 실제 완료 라운드 이력을 보존합니다. 얼음의 불꽃 타입 내성 DC, 날씨 보정, 특정 타입 공격 명중에 따른 해제를 실제 실행 경로에 연결했습니다.</p><p><a href="category2-persistent-condition-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-persistent-condition-source-review.json">영문 원본과 개정 규칙 대조</a></p><p class="note">전체 마비·풀죽음 및 잠듦의 공격·인접 동료 회복 경로는 별도 미완료입니다. 자연 회복과 전투 후 해동은 아래 회복 묶음에서 검증했습니다.</p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-recovery-family-completion.json').exists():
 details='<h2>회복 경로: 공통 시간·해제 처리</h2><p>자연 수면 회복과 전투 후 해동은 명시된 시간·근거와 공통 회복 기록을 사용합니다. 일반 회복약을 반복 사용해도 기절 회복 기한을 유지하며, 다시 쓰러진 뒤의 새 회복은 새 10분을 적용합니다.</p><p><a href="category2-recovery-family-completion.json">원조항 2개와 실행 검증</a> · <a href="category2-recovery-family-source-review.json">원문·회복 수단·시점 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-rest-recovery-completion.json').exists():
 details='<h2>휴식·회복: 공통 시간과 일일 한도</h2><p>GM이 휴식 여부와 근거를 기록하면 트레이너·포켓몬이 한 시간 구간을 공유합니다. 연속 30분·하루 8시간·연장 휴식 4시간·일일 일반 부상 치료 3개의 상태를 기존 공통 로직으로 처리하고 저장·복원을 검증했습니다. 새 부상 없는 24시간 판정과 트레이너의 AP 부상 치료는 별도 미완료입니다.</p><p><a href="category2-rest-recovery-completion.json">원조항 4개와 실행 검증</a> · <a href="category2-rest-recovery-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-injury-recovery-completion.json').exists():
 details='<h2>부상·질식·회복: 공통 출처와 실제 경과 시간</h2><p>질식 부상은 호흡 출처를 유지하며 일반 치료와 구별합니다. 실제 최대 HP와 부상 회복 상한을 분리하고 전체 부상 비율 적용 후 내립니다. 트레이너·포켓몬은 공통 새 부상 없는24시간 기록을 사용하며, 트레이너의 연장 행동·2AP 제거 치료도 같은 일일 한도를 씁니다. 저장·복원과199개 실행 검증을 통과했습니다.</p><p><a href="category2-injury-recovery-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-injury-recovery-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-spatial-body-completion.json').exists():
 details='<h2>몸체·인접·포위: 하나의 점유 칸 정보</h2><p>크기와 관측된 비정사각 몸체를 공통 점유 칸으로 사용합니다. 인접·매우 인접, 큰 몸체의 가장자리 사거리와 이동 공간, 포위 인원·접촉 칸 가중치·최소 두 전투원을 함께 검증했습니다. 원문 그림5개와 크기별 경계, 실제 명중·저장복원을 포함한131개 고유 테스트를 통과했습니다. 대각선 이동 이력 조항은 별도 미완료입니다.</p><p><a href="category2-spatial-body-completion.json">원조항 4개와 실행 검증</a> · <a href="category2-spatial-body-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-base-stage-abilities-completion.json').exists():
 details='<h2>기본 전투단계: 특성 출처와 장비 조건 공유</h2><p>불굴의방패·불요의검·곡예 Playtest를 출처별 기본 단계로 통일했습니다. 획득·억제·기절·상실, 장비 유무, 상한·초기화·저장복원이 같은 저장소를 사용합니다. 두 도구를 지녀도 곡예의 조건부 감소는 한 번만 적용합니다. 고유 테스트130개의 통과 근거를 확보했습니다.</p><p><a href="category2-base-stage-abilities-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-base-stage-abilities-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-timed-type-state-completion.json').exists():
 details='<h2>타입 효과 공통 수명: 추가·제거·교체 / 날개쉬기</h2><p>타입 추가·제거·교체는 동일한 출처별 상태와 수명 처리로 통합했다. 실제 날개쉬기의 회복·조건부 비행타입 제거·사용자 다음 턴 시작 복귀·중첩 보존·두 저장복원 경로를 검증했다. 원문 단위 완료는1개이며, 5턴의 기준 및 범위공격 전체 종료 의존성은 미완료로 보존한다.56개 검사가 동일 실행코드/자료에서 통과했다.</p><p><a href="category2-timed-type-state-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-timed-type-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-permanent-type-sync-completion.json').exists():
 details='<h2>영구 타입 변경 7개 조항: 타입·학습·재능·특성·레벨업 목록</h2><p>하나의 개체별 Type Sync 전환으로7개 원문 조항을 통합했다. 타입 조합은 자동 검증하고 GM의 네 결정 영역을 명시적으로 보존한다. 실제 TM/가르침 학습, HM 학습 결과 기록, 레벨업·멘토 학습, 개별 출처 중첩과 저장복원을 검증했다.44개 고유 검사가 통과했으며 일반 타입 변화·기술 상태의 기존 검사를 포함한다.</p><p><a href="category2-permanent-type-sync-completion.json">원조항 7개와 실행 검증</a> · <a href="category2-permanent-type-sync-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-source-derived-example-species-completion.json').exists():
 details='<h2>원문 변형 포켓몬 3종: 하나의 선언형 종 정의와 공통 실행</h2><p>근육진 다부니·라이코 부모 썬더볼트·거대 캐터피를 공통 선언형 정의로 묶었다. 실제 생성·기술머신 학습·레벨업·진화 금지·새 엔진의 저장복원을 검증했다. 마지막 변경의14개 검사가 통과했으며, 앞선77개 검사 중 발견된 저장 오류 유형1건의 수정·재검증 내역도 보존한다.</p><p><a href="category2-source-derived-example-species-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-source-derived-example-species-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-selected-ability-transitions-completion.json').exists():
 details='<h2>특성 복사·교환·교체·무효화 9조항: 하나의 출처 관리와 개별 종료</h2><p>선택한 특성의 원본·현재 효과·기여 출처를 공통으로 관리한다. 일반 기술과 특성 발동 경로에서 적용하며 스킬스왑의 양쪽 종료는 독립적으로 처리한다. 모든9개 출처의 실제 적용·새 엔진 저장복원·실제 종료를 포함한107개 고유 검사가 통과했다.</p><p><a href="category2-selected-ability-transitions-completion.json">원조항 9개와 실행 검증</a> · <a href="category2-selected-ability-transitions-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-food-capacity-abilities-completion.json').exists():
 details='<h2>음식 특성3조항: 선택한 출처와 한도 단위의 공통 처리</h2><p>꿀파기 원본·Playtest 및 먹보 Playtest를 공통 특성 등록과 음식 처리에 연결했다. 실제 섭취·일반 슬롯과 예외 슬롯·장면 소비·정확한30분 경계·특성 제거 후 획득 버프 유지·새 Rules 저장복원을 함께 검증한다. 최종80개 검사가 모두 통과했다.</p><p><a href="category2-food-capacity-abilities-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-food-capacity-abilities-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-mega-forms-completion.json').exists():
 details='<h2>메가진화 공통 상태6조항</h2><p>폼 정의·물리적 링/스톤·스탯/타입/특성 출처를 공통 상태로 연결하고 장면 종료 때 해당 출처만 회수한다. 재배분은 HP 유지 예외와 나머지 기본관계를 구별한다.</p><p><a href="category2-mega-forms-completion.json">원조항 6개와 실행 검증</a> · <a href="category2-mega-forms-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-contest-common-state-completion.json').exists():
 details='<h2>기본·슈퍼 콘테스트 상태 29조항</h2><p>공통 자원·소개·위치·점수 상태를 대조하고 중심 역할 기록과 라운드 종료 수명을 보완했다. 새 검증6개와 기존137개를 중복 없이 확인했다. 페스티벌을 포함하는 C08-014는 미완료로 유지한다.</p><p><a href="category2-contest-common-state-completion.json">원조항 29개와 실행 검증</a> · <a href="category2-contest-common-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-paired-contest-state-completion.json').exists():
 details='<h2>트레이너 참가 공통 상태 4조항</h2><p>동시·교대 참가의 실제 배우, 공유 주사위 풀, 분리·공유 흥분도, 순서와 재주 사용을 검증했다. 저장 데이터도 동일한 모델 제약을 지킨다.</p><p><a href="category2-paired-contest-state-completion.json">원조항 4개와 실행 검증</a> · <a href="category2-paired-contest-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-weather-shared-state-completion.json').exists():
 details='<h2>기본 날씨 공통 상태 6조항</h2><p>날씨 설정·교체·해제·만료를 한 경로로 모으고 자연 관찰과 GM의 효과 인정을 분리했다. 실제 기술 출처, 다섯 라운드 경계, 조건부 특성, 저장·복원을 검증했다.</p><p><a href="category2-weather-shared-state-completion.json">원조항 6개와 실행 검증</a> · <a href="category2-weather-shared-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-supplemental-move-grants-completion.json').exists():
 details='<h2>추가 재주 기술 부여 2조항</h2><p>겨울의 예고와 바위 파편을 기존 기술 부여 경로에 통합했다. 랭크·기술 선택·스킬 조건·제거·저장 복원을 검증했으며, 선행 카탈로그·특성 처리가 막힌8조항은 미완료로 남겼다.</p><p><a href="category2-supplemental-move-grants-completion.json">원조항 2개와 실행 검증</a> · <a href="category2-supplemental-move-grants-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-move-capability-lifetimes-completion.json').exists():
 details='<h2>습득 재능 공통 수명: 원조항2개</h2><p>이름형35개 기술과 수치형8개 기술의 습득·망각을 공통 처리합니다. 현재 총합의 포함 보너스, 독립 출처, 원문 선택과 저장복원을 검증했습니다.</p><p><a href="category2-move-capability-lifetimes-completion.json">원조항 2개와 실행 검증</a> · <a href="category2-move-capability-lifetimes-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-whole-innate-protection-completion.json').exists():
 details='<h2>전체 선천적 특성의 교환 실패: 원조항1개</h2><p>명시적 선천적 특성5개에 같은 교환·복사·억제 보호를 적용했습니다. 일부만 선천적인 구성요소 분리는 별도 미완료로 유지합니다.</p><p><a href="category2-whole-innate-protection-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-whole-innate-protection-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-body-size-modes-completion.json').exists():
 details='<h2>팽창·수축 공통 상태: 원조항4개</h2><p>크기·무게·회피·행동 비용·현재 몸을 통한 표적 차단을 한 상태로 처리하고 실제 행동 및 저장복원을 검증했습니다. 재능 본문에서 발견한 기술 연결3개도 공통 정책에 보완했습니다.</p><p><a href="category2-body-size-modes-completion.json">원조항 4개와 실행 검증</a> · <a href="category2-body-size-modes-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-flinch-core-state-completion.json').exists():
 details='<h2>풀죽음의 중첩·수명·해제: 원조항1개</h2><p>풀죽음 중첩과 한 라운드 취약을 서로 다른 수명으로 처리하고 출처·실제 행동·저장복원을 검증했습니다.</p><p><a href="category2-flinch-core-state-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-flinch-core-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-flinch-errata-state-completion.json').exists():
 details='<h2>풀죽음 에라타 상태: 원조항1개</h2><p>풀죽음 중첩과 한 라운드 취약을 서로 다른 수명으로 처리하고 출처·실제 행동·저장복원을 검증했습니다.</p><p><a href="category2-flinch-errata-state-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-flinch-errata-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-weather-template-state-completion.json').exists():
 details='<h2>날씨 샘플9종과 맞춤 정의 객체</h2><p>원문 예시를 타입 조합 템플릿으로 표현하고 명시적 맞춤 정의와 저장·복원을 검증합니다.</p><p><a href="category2-weather-template-state-completion.json">원조항 2개와 실행 검증</a> · <a href="category2-weather-template-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-weather-state-certification-completion.json').exists():
 details='<h2>선택 날씨: 고유 피해 제거 및 생성·지속 4종</h2><p>실제 선택 원문과 대조해 고유 날씨 피해 제거, 조건부 기술 유지, 네 날씨의 실제 생성·종료·복원을 검증합니다. 충전 소비와 눈 치환의 별도 미완성 조항은 포함하지 않습니다.</p><p><a href="category2-weather-state-certification-completion.json">원조항 5개와 실행 검증</a> · <a href="category2-weather-state-certification-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-melee-reach-completion.json').exists():
 details='<h2>도달: 근접 사거리와 관측 예외</h2><p>C10-107/108: 크기별2m/3m 및 GM이 관측한 큰 몸·긴 팔 예외. 발버둥·기술·무기·접근·복원51개 검증 통과.</p><p><a href="category2-melee-reach-completion.json">원조항 2개와 실행 검증</a> · <a href="category2-melee-reach-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-capability-traits-completion.json').exists():
 details='<h2>감각 면역과 서술형 온도 재능</h2><p>C10-010/013/014/047: 실제 보유 출처를 공통 조회하여 실명 면역·어둠 이동·차가움/따뜻함을 적용.60개 관련 검증 통과.</p><p><a href="category2-capability-traits-completion.json">원조항 4개와 실행 검증</a> · <a href="category2-capability-traits-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-environment-capabilities-completion.json').exists():
 details='<h2>지형변화·아가미 환경 상태</h2><p>C10-037/040/042: 칸별 지형 선택을 하나의 기본 행동으로 반영하고 실제 명중·이동·저장복원을 검증. 아가미는 장시간 수중 호흡과 출처 회수 경계를 검증.22개 통과.</p><p><a href="category2-environment-capabilities-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-environment-capabilities-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-naturewalk-state-completion.json').exists():
 details='<h2>자연걸음의 실제 지형 소비</h2><p>C10-096: 명시 지형·기존 종족 지형·별도 부여 출처를 보존하여 실제 이동·명중에 적용. 영문 grassland/wetland 분리 오류 수정.15개 관련 검증 통과.</p><p><a href="category2-naturewalk-state-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-naturewalk-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-voluntary-silence-completion.json').exists():
 details='<h2>무음 선택과 행동의 소리 상태</h2><p>C10-015: 숨소리·심장소리를 포함한 자발적 무음. 종족/부여 출처, 실제 이동·공격, 저장복원 검증9개 통과. C10-126 복합 행동 예외 미완료.</p><p><a href="category2-voluntary-silence-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-voluntary-silence-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-invisibility-lifecycle-completion.json').exists():
 details='<h2>투명 활성화·종료·재사용 대기</h2><p>C10-059/061/062: 공유 투명 상태, 실제 기술 제한·명중+4 요구, 240초 만료와 유지시간+120초 재사용 대기, 시간 불확실성·저장복원 검증18개 통과.</p><p><a href="category2-invisibility-lifecycle-completion.json">원조항 3개와 실행 검증</a> · <a href="category2-invisibility-lifecycle-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-bloom-appearance-completion.json').exists():
 details='<h2>만개의 실제 날씨 반응</h2><p>C10-011: 쾌청 시 분홍 꽃, 그 외 보라색 봉오리. 실제 쾌청 기술·날씨 교체와 만료·종족 및 부여 출처·두 저장복원·시야 소비자 검증10개 통과.</p><p><a href="category2-bloom-appearance-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-bloom-appearance-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-mulch-soil-state-completion.json').exists():
 details='<h2>비료의 실제 토양·수확 상태</h2><p>C09-035: 실제 비료1개 소비, 토양 품질+1및 최종+2상한, 기존 토양·플랜터와 합성. 일일 만료·과거 수확·저장복원 포함11개 검증 통과.</p><p><a href="category2-mulch-soil-state-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-mulch-soil-state-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-weathershape-appearance-completion.json').exists():
 details='<h2>공통 날씨 외형: 캐스퐁과 만개</h2><p>C10-150: 쾌청·비·우박·모래바람의 네 외형을 실제 날씨 기술과 연결. 만개와 공통 날씨 출처를 사용하며 두 저장복원과 부여 해제 검증.</p><p><a href="category2-weathershape-appearance-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-weathershape-appearance-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-aura-observation-completion.json').exists():
 details='<h2>파동 색과 밝기의 공통 관측·읽기</h2><p>C10-004/005: 파동 색의 인격·가치관과 밝기의 기분·의도 정보를 공통 관측으로 관리. 실제 종족 및 부여 재능·생존 대상·정보 갱신·두 저장복원 검증.</p><p><a href="category2-aura-observation-completion.json">원조항 2개와 실행 검증</a> · <a href="category2-aura-observation-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-aura-pulse-consent-completion.json').exists():
 details='<h2>파동술: 상대별 동의와 표면 생각</h2><p>C10-007: 특정 상대에게 자발적으로 마음을 연 관계와 현재 표면 생각을 보존. 생각 전달만으로 읽기 권한을 얻지 않으며 철회·재능 상실·두 저장복원·관계 무결성을 검증.</p><p><a href="category2-aura-pulse-consent-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-aura-pulse-consent-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-dream-mist-sharing-completion.json').exists():
 details='<h2>꿈안개 실제 사용에서 꿈 공유까지</h2><p>C10-019: 근접 AC6·기본 행동·재고 소모에서 수면 출처와 꿈 공유까지 연결. 자연1/20·회피·면역·물리 아이템·정신봉인·수면 종료·두 저장복원 검증.</p><p><a href="category2-dream-mist-sharing-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-dream-mist-sharing-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-capability-products-completion.json').exists():
 details='<h2>공통 재능 생산: 꿈안개·우유·꿀</h2><p>레벨·환경 조건별 일일 연장 생산을 공통 빈병 내용물로 연결. 실제 꿈안개 공격·우유 회복·일일 횟수·병 재사용·두 저장복원 검증18개 통과. C09-081만 신규 완료.</p><p><a href="category2-capability-products-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-capability-products-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-keystone-links-completion.json').exists():
 details='<h2>쐐기돌의 실제 연결 상태</h2><p>수집한 실제 돌과 화강돌별 연결·2포인트 소비·중복 방지·원자성·두 저장복원 및 실제 이동 소비자를 검증. C10-066만 완료.</p><p><a href="category2-keystone-links-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-keystone-links-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-soulless-default-completion.json').exists():
 details='<h2>영혼없음 기본 특성과 HP</h2><p>불가사의부적 기본 보유와 최대HP1을 생성·영구 변경·저장복원에서 검증. 일시 특성 투영과 기본값 구분.30개 검증 통과, C10-118완료.</p><p><a href="category2-soulless-default-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-soulless-default-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-shapeshift-appearance-completion.json').exists():
 details='<h2>형상변환 외형·기능 구분</h2><p>복잡한 기계는 단순화된 외형만 표시하고 포켓몬의 기계적 성질을 복사하지 않음. 실제 메타몽과 두 저장복원 포함19검증 통과. C10-112완료, 질량·부피 충돌 C10-111은 보류.</p><p><a href="category2-shapeshift-appearance-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-shapeshift-appearance-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
if (OUT/'category2-minimize-distinction-completion.json').exists():
 details='<h2>작아지기와 수축 재능 구분</h2><p>습득은 재능 보유만, 기술 사용은 인카운터 소형·회피+4, 재능 사용은 별도 신체 상태와 기본 행동 제약. 두 저장복원 및 독립 종료 포함19검증 통과. C10-117완료.</p><p><a href="category2-minimize-distinction-completion.json">원조항 1개와 실행 검증</a> · <a href="category2-minimize-distinction-source-review.json">원문·조건·예외 대조</a></p>'
 page=page.replace('<h2>형식에 나타난 효과 종류</h2>',details+'<h2>형식에 나타난 효과 종류</h2>')
(OUT/'category2-buff-state-audit.html').write_text(page,encoding='utf-8')
print(json.dumps(report['coverage'],ensure_ascii=False))
