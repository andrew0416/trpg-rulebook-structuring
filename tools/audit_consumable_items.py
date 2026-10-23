"""Inventory every saved item definition and locate item/resource-loss consumers.
Read-only with respect to runtime and completion credit. Labels are investigation
routing, not executable permission or source-completion certification.
"""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import ast,csv,hashlib,json,re,sys,html
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
import food_effects as FOOD,restorative_items as REST,vitamin_moves as V,items as ITEMS

def load(path):return json.loads((ROOT/path).read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def normalize(name):return re.sub(r'[\s_-]+','',re.sub(r'\[.*?\]|\(.*?\)','',str(name))).lower()
REVIEW=load('data/verification/category2-consumable-review.json')
OVERRIDES={uid:{k:v for k,v in entry.items() if k!='ids'} for entry in REVIEW['overrides'] for uid in entry['ids']}
RELATED=re.compile(r'소모품|소비품|소모성|일회용|1회용|만복|음식 ?버프|열매|한약|붕대|파스|영양제|주얼|기술머신|비전머신|회복 ?도구|약물포|캡슐|오물탄|부적|미끼|스프레이|식재료|요리 재료|재활용|리사이클|수확|먹보|먹이|파편|내던지기|진화의 ?돌|재료|탄창|탄약|카트리지')
TOKEN=re.compile(r'소모|소비|일회용|1회용|비소모품|충전|탄약|탄창|리필|파괴|파손|분실|만복|버프|먹[으는을고인]|섭취|비료|재료')
FAMILIES={
 'medicine':('회복약·한약·X도구','물품 한 단위 소비; 한약 횟수와 X 대상/지속 규칙은 별도','engine/items.py; engine/restorative_items.py; engine/food_effects.py'),
 'food':('음식·음료·열매·식사·포핀','섭취 때 물품 소비, 이후 만복 버프를 별도로 소비; 식재료로도 쓰일 수 있음','engine/food_effects.py; engine/contest_features.py; engine/crafting_activities.py'),
 'vitamin_growth':('영양제·성장 도구·억제제','복용/적용 물품과 평생 또는 개체별 적용 한도를 구분','engine/vitamin_moves.py; engine/items.py; engine/move_state.py'),
 'bandage':('붕대·파스','여러 단위를 한 번에 적용하고 지속효과/부상치유 한도를 별도 추적','engine/bandages.py'),
 'capture_ball':('포획용 볼','던져 재고를 떠남; 빗나감·포획실패·성공 후 상태를 구분','engine/engine.py:throw_ball; engine/encounter.py'),
 'loaded_container':('볼 케이스·부착장치·발사기','본체/내용물/장전 상태를 분리; 재사용 본체를 매번 소비하면 안 됨','engine/net_capsule.py; other source-specific adapters require review'),
 'wild_field':('미끼·스프레이·비료','배치/살포/분사 후 물품과 필드 또는 유인 상태를 구분','engine/wild_equipment.py; engine/pokemon_activities.py; engine/crafting_activities.py'),
 'gem':('타입주얼','자유 행동으로 물품 소비 후 다음 해당 타입 기술에 남는 효과를 추적','engine/crafting_activities.py:craft_gem; activation adapter not identified'),
 'tactical':('전투 소모 도구·부적·군수품','준비/투척/명중/소각/결계 파괴 등 각 출처의 소비 시점을 유지','engine/items.py generic path; full source-specific adapters require review'),
 'ammunition':('탄약·캡슐·장전 수','탄약 단위, 장전고와 발사기를 분리; 발사 시 소비','engine/net_capsule.py; engine/crafting_activities.py'),
 'crafting_material':('제작 재료·파편·잔여 재료','종류/개수/가치로 소비; 제작 본체 도구와 돈/AP는 구분','engine/crafting_activities.py; engine/pokemon_teaching.py'),
 'reusable_charge':('재사용·충전·횟수 제한 장비','물품은 유지하고 사용 횟수, 잔량, 시간 또는 내구도만 변화','source-specific lifetime and frequency adapters'),
 'trigger_consumable':('피격·상태 변화 시 소비 도구','트리거 성립과 자동/선택 소비 및 교체를 구분','source-specific native producer not identified'),
 'destruction':('피격 시 파괴 도구','자발적 소비가 아니라 물리 객체 파괴','engine/items.py:destroy_equipment; automatic source adapter not identified'),
 'evolution_catalyst':('진화용 도구·연금 촉매','사용 가능과 소멸을 구분; 원문 확인 없이 소비 확정 금지','engine/pokemon_progression.py; source-specific application review'),
 'related_tool':('생산·투여·획득 보조 도구','본체는 유지하고 입력 재료/아이템을 처리','engine/crafting_activities.py; engine/pokemon_activities.py'),
 'rule_modifier':('소비·제작 규칙을 바꾸는 책','책 자체는 소비하지 않고 자격에 따른 규칙을 합성','source-specific policy dependency'),
 'source_heading':('아이템 총칙·분류 표제','추출된 ID이지만 개별 판매 물품으로 세지 않음','source rules only'),
 'other_candidate':('추가 소비·상태 변화 후보','자동 후보 판정만 있음; 원문 단위 검토 없이 소비 권한을 부여하지 않음','not individually certified'),
 'not_flagged':('현재 소비 후보 아님','장비/설명/행동 비용만 있는 항목도 원문과 함께 보존','not a proof of non-consumption')}

def classify(uid,name,desc,header,source):
 n=normalize(name);raw=desc;use=header.get('use');category=header.get('category');path=str(source.get('path',''))
 if uid in OVERRIDES:return OVERRIDES[uid]['family']
 if '메가' not in raw and ('진화시킬수' in raw or '진화시킬 수' in raw):return 'evolution_catalyst'
 if uid.startswith('crafted_item/'):return 'related_tool'
 if uid in REST.HELD_CONSUMABLES or uid in FOOD.HERBS:return 'medicine'
 if uid in V.ALL_ITEMS or any(x in n for x in ('영양제','이상한사탕','억제제','진화의돌')):return 'vitamin_growth'
 if n in ('붕대','파스'):return 'bandage'
 if '주얼' in n:return 'gem'
 if any(x in n for x in ('케이스','부착장치','약물포','캡슐캐논','카메라키트','추적칩','알람장치')):return 'loaded_container'
 if any(x in n for x in ('마법피리','호흡기','루어','분리중갑','반사연결')) and use!='ball':return 'reusable_charge'
 if any(x in n for x in ('미끼','벌레회피스프레이','실버스프레이','골드스프레이','비료')):return 'wild_field'
 if any(x in n for x in ('캡슐','탄창','탄약','카트리지')):return 'ammunition'
 if any(x in n for x in ('마름쇠','꿈안개','부적','오물탄','연막탄','수류탄','그레네이드','플래시뱅','제압블라','제압블래','잽블래','인페르노캐논')) or '1회용 군수품' in path:return 'tactical'
 if category=='몬스터볼' or use=='ball':return 'capture_ball'
 if any(x in n for x in ('하트비늘','조각','파편','규토리')) and not any(x in n for x in ('기력의조각','규토리볼')):return 'crafting_material'
 if category=='음식' or uid in FOOD.DRINKS or uid in FOOD.SNACKS or '열매' in n or '포핀' in n or '식사' in n or '허브' in n or '버섯' in n:return 'food'
 if category=='약':return 'medicine'
 if re.search(r'재충전|리필|매.{0,8}복구|(?:하루|장면|전투|콘테스트).{0,10}(?:한|[123]) ?(?:번|회)|하루당',raw):return 'reusable_charge'
 if use=='consumable' or re.search(r'(도구|아이템|물품|부적|재료).{0,18}(소모|소비|사라|파괴)|일회용|1회용|자동 소비|행동으로 소비',raw):return 'other_candidate'
 return 'not_flagged'

rows=[json.loads(line) for line in (ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
entities={r['id']:r for r in rows if r['id'].startswith(('item/','crafted_item/','augment/'))}
mechanized=load('data/items-mech.json');tables=load('data/verification/category2-item-table-status.json')['rows']
shared=set(REST.HELD_CONSUMABLES)|V.ALL_ITEMS|{'item/붕대','item/파스','item/이유식'}|set(FOOD.DRINKS)|set(FOOD.SNACKS)|set(FOOD.BERRY_HEALS)|set(FOOD.BERRY_CURES)|set(FOOD.BERRY_TYPES)
by_name=defaultdict(list)
for row in tables:by_name[normalize(row['name'])].append(row)
records=[]
for uid in sorted(set(entities)|set(mechanized)):
 unit=entities.get(uid,{});draft=mechanized.get(uid,{})
 name=unit.get('title',draft.get('name',uid));text=unit.get('text',{})
 body=text.get('body','') if isinstance(text,dict) else str(text)
 desc=draft.get('desc','');header=draft.get('header',{});source=unit.get('source',{})
 family=classify(uid,name,body+'\n'+desc,header,source)
 matches=by_name.get(normalize(name),[])
 status='shared_stock_native_adapter' if uid in shared else 'dedicated_capture_path_requires_source_review' if family=='capture_ball' and name in ITEMS.BALL_RULES else 'reusable_resource_not_unit_consumption' if family=='reusable_charge' else 'requires_source_adapter_review' if family!='not_flagged' else 'not_flagged_by_current_inventory'
 records.append({'id':uid,'name':name,'family':family,'family_name':FAMILIES[family][0],'candidate':family!='not_flagged','runtime_status':status,'draft_use':header.get('use'),'draft_category':header.get('category'),'source':source,'source_body':body,'catalog_description':desc,'source_variants_not_merged':True,'table_rows':[r['id'] for r in matches],'related_clause_ids':sorted({r['parent_clause_id'] for r in matches if r.get('parent_clause_id')}),'implementation_complete':False,'classification_review':OVERRIDES.get(uid,{'reason':'분류/본문/명칭 기반 검색 분류. 물품의 전체 효과를 개별 인증한 기록이 아님.'}),'consumption_contract':REVIEW['contracts'].get(family,{'when':'개별 검토 미확정','quantity':'미확정','failure':'미확정','state':'소비 권한을 추론하지 않음','shared':'해당 없음'}),'contract_status':'family routing; individual qualifiers and source variants retained','relation':'source_heading' if family=='source_heading' else 'not_flagged' if family=='not_flagged' else 'related_nonconsuming_or_transform_tool' if family in ('related_tool','rule_modifier','loaded_container','reusable_charge') else 'consumption_unresolved' if family=='evolution_catalyst' else 'resource_or_lifecycle_candidate'})

source_hits=[];source_files=[]
for path in sorted((ROOT/'input').rglob('*')):
 if not path.is_file():continue
 rel=path.relative_to(ROOT).as_posix();source_files.append({'file':rel,'sha256':digest(path)})
 if path.suffix=='.md':
  for line,text in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
   if TOKEN.search(text):source_hits.append({'file':rel,'line':line,'text':text,'classification':'lexical_candidate_not_individual_rule_confirmation'})
 elif path.suffix=='.csv':
  with path.open(encoding='utf-8-sig',newline='') as handle:
   for rownum,cells in enumerate(csv.reader(handle),1):
    for col,text in enumerate(cells,1):
     if TOKEN.search(text):source_hits.append({'file':rel,'csv_row':rownum,'column':col,'text':text,'classification':'lexical_candidate_not_individual_rule_confirmation'})

runtime_sites=[];parse_errors=[];scanned_runtime=[]
RESOURCE=re.compile(r'items|inventory|\binv\b|stock|ammo|charge|material|scrap|shard|capsule|batch',re.I)
class Visitor(ast.NodeVisitor):
 def __init__(self,path,lines):self.path=path;self.lines=lines;self.function=[]
 def visit_FunctionDef(self,node):
  self.function.append(node.name);self.generic_visit(node);self.function.pop()
 visit_AsyncFunctionDef=visit_FunctionDef
 def record(self,node,kind):
  semantic=REVIEW['runtime_semantics'].get(self.path+':'+'.'.join(self.function),{'operation':'requires_semantic_review','meaning':'AST candidate only'})
  runtime_sites.append({'semantic_review':semantic,'file':self.path,'line':node.lineno,'function':'.'.join(self.function),'kind':kind,'code':' '.join(self.lines[node.lineno-1:min(node.end_lineno,node.lineno+3)]).strip(),'whole_rule_verified':False})
 def visit_AugAssign(self,node):
  if isinstance(node.op,ast.Sub) and RESOURCE.search(ast.unparse(node.target)):self.record(node,'direct_resource_decrement')
  self.generic_visit(node)
 def visit_Assign(self,node):
  if RESOURCE.search(' '.join(ast.unparse(t) for t in node.targets)) and isinstance(node.value,ast.BinOp) and isinstance(node.value.op,ast.Sub):self.record(node,'direct_subtraction_assignment')
  self.generic_visit(node)
 def visit_Call(self,node):
  fn=ast.unparse(node.func)
  if fn.endswith('STOCK.debit'):self.record(node,'shared_stock_debit_call')
  elif isinstance(node.func,ast.Attribute) and node.func.attr in ('pop','remove','clear') and RESOURCE.search(ast.unparse(node.func.value)):self.record(node,'resource_removal_candidate')
  self.generic_visit(node)
for path in sorted((ROOT/'engine').glob('*.py')):
 if path.name.startswith('test'):continue
 rel=path.relative_to(ROOT).as_posix();scanned_runtime.append({'file':rel,'sha256':digest(path)})
 text=path.read_text(encoding='utf-8-sig')
 try:Visitor(rel,text.splitlines()).visit(ast.parse(text))
 except SyntaxError as exc:parse_errors.append({'file':rel,'error':str(exc)})

machines=load('data/pokemon-machines.json')['machines']
machine_sources={}
with (ROOT/'input/db/tm.csv').open(encoding='utf-8-sig',newline='') as handle:
 for rownum,cells in enumerate(csv.reader(handle),1):
  match=re.match(r'^(TM|HM)([0-9]+):(.+)',cells[0] if cells else '')
  if match:
   kind,number,name=match.groups();code=kind+number
   machine_sources[code]={'code':code,'kind':kind,'number':int(number),'move_name':name,'price':int(re.sub(r'[^0-9]','',cells[1]) or 0),'source':{'file':'input/db/tm.csv','csv_row':rownum,'columns':[1,2,3]},'source_category':cells[2]}
machine_records=[]
for code in sorted(set(machines)|set(machine_sources),key=lambda c:(c[:2],int(c[2:]))):
 raw=machine_sources.get(code);runtime=machines.get(code);row=raw or runtime
 differences={k:{'source':raw[k],'runtime_catalog':runtime[k]} for k in ('move_name','price') if raw and runtime and raw[k]!=runtime[k]}
 machine_records.append({'code':code,'kind':row['kind'],'move_name':row['move_name'],'source_record':raw,'runtime_record':runtime,'differences':differences,'runtime_status':'catalog_entry_present_not_source_certification' if runtime else 'missing_from_runtime_catalog','stock_contract':'one unit consumed after actual teaching' if row['kind']=='TM' else 'reusable item; one use per day','runtime':'engine/pokemon_teaching.py:teach_machine','shared_stock':False})
table_groups=Counter(r['family'] for r in records)
result={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'purpose':'All saved consumable and limited-use tool investigation; original clause denominator unchanged.','completion_credit':0,'scope':{'item_definitions':len(records),'mechanized_catalog_entries':len(mechanized),'source_files':len(source_files),'raw_table_panels':len(tables),'source_machine_codes':len(machine_records),'runtime_machine_definitions':len(machines),'missing_runtime_machine_codes':[r['code'] for r in machine_records if r['runtime_record'] is None],'runtime_files':len(scanned_runtime),'candidate_item_definitions':sum(r['candidate'] for r in records),'lexical_source_hits':len(source_hits),'runtime_sites':len(runtime_sites),'runtime_parse_errors':parse_errors,'shared_stock_native_ids':len(shared),'relation_counts':dict(Counter(r['relation'] for r in records)),'related_rule_index_entries':sum(not r['id'].startswith(('item/','crafted_item/','augment/')) and bool(TOKEN.search(str(r.get('text',{}))) or RELATED.search(str(r.get('text',{})))) for r in rows),'unmatched_nonstructural_table_panels':sum(t['disposition']!='structural' and not any(t['id'] in r['table_rows'] for r in records) for t in tables)},'counting_notes':['Definition IDs are counted separately, including variants and aliases. These are not distinct semantic item types or completed clauses.','The 175 consumable header labels in the draft catalog are hints. Gems/tactical items occur outside them, and ingredient/reusable rows can be mislabeled.','All item definitions remain in this artifact, including not_flagged rows, to make candidate omissions reviewable.','Source hits are a broad retrieval index, not individually verified item rules. Other resource-only hits are retained for review.','No runtime coverage or completion is inferred merely from a header label or shared stock connection.','All 729 definition IDs are partitioned, but individual effect semantics are not all certified. Source headings, aliases and variants are counted separately.','AST loss search is a static index, not a proof that all indirect resource mutations were found.','The raw 1146 table panels also contain capabilities and Pokebot data; they are coverage material, not 1146 items.'],
 'families':[{'id':key,'name':value[0],'stock_contract':value[1],'runtime_paths':value[2],'definition_count':table_groups[key]} for key,value in FAMILIES.items()],
 'items':records,'machines':machine_records,
 'raw_table_panels':tables,'source_files':source_files,'source_hits':source_hits,'runtime_files':scanned_runtime,'runtime_sites':runtime_sites,'related_rules':[{'id':r['id'],'kind':r.get('kind'),'title':r.get('title'),'source':r.get('source'),'text':r.get('text',{}),'review_status':'dependency retrieval index; not individually certified'} for r in rows if not r['id'].startswith(('item/','crafted_item/','augment/')) and (TOKEN.search(str(r.get('text',{}))) or RELATED.search(str(r.get('text',{}))))],
 'findings':REVIEW['findings'],'source_only_resources':REVIEW['source_only_resources'],'implementation_order':REVIEW['implementation_order'],'unresolved_policy':REVIEW['unresolved_policy'],'progress':REVIEW['progress'],'review_file':'data/verification/category2-consumable-review.json'}
output=ROOT/'data/verification/category2-consumable-inventory-audit.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'output':str(output),'scope':result['scope'],'families':dict(table_groups),'unmapped_runtime_sites':[x for x in runtime_sites if x['semantic_review']['operation']=='requires_semantic_review']},ensure_ascii=False,indent=2))
