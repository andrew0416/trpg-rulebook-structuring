"""Render the audited inventory as a searchable offline report; no runtime edits."""
from pathlib import Path
from collections import Counter
import html,json
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/verification/category2-consumable-inventory-audit.json'
a=json.loads(DATA.read_text(encoding='utf-8'))
progress=json.loads((ROOT/'data/verification/category2-progress.json').read_text(encoding='utf-8'))
progress_text=f"{progress['completed_clause_count']:,} / {progress['denominator']:,} = {progress['completion_percent']:.8f}%"
remaining=progress['denominator']-progress['completed_clause_count']
def h(v):return html.escape(str(v),quote=True)
def j(v):return h(json.dumps(v,ensure_ascii=False,indent=2))
def source(s):
 if not s:return '추출 출처 없음'
 if isinstance(s,str):return h(s)
 if 'source' in s:return h(s.get('rule_id',''))+' '+source(s['source'])
 file=s.get('file','');location=''
 if s.get('csv_row'):location=' CSV 행 '+str(s['csv_row'])
 elif s.get('csv_rows'):location=' CSV 행 '+str(s['csv_rows'])
 elif s.get('record_span'):location=' 추출 record_span '+str(s['record_span'])
 elif s.get('lines'):location=' 줄 '+str(s['lines'])
 return h(file+location)
parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>소비 도구 전체 조사</title>',
'<style>\n:root{color-scheme:light;--ink:#172a35;--accent:#126966;--line:#dce4e6}*{box-sizing:border-box}body{margin:0;background:#f5f8f8;color:var(--ink);font:15px/1.65 "Malgun Gothic",system-ui,sans-serif}main{max-width:1480px;margin:auto;padding:32px}h1{font-size:32px;margin:0 0 10px}h2{margin:30px 0 10px;font-size:23px}h3{font-size:18px;margin:12px 0}p{margin:8px 0 14px}a{color:var(--accent)}.lead{max-width:1080px}.muted{color:#52636d;font-size:13px}.cards{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}.card{background:white;border:1px solid var(--line);padding:14px 20px;border-radius:8px;min-width:150px}.card b{font-size:26px;display:block;color:var(--accent)}.box,details.issue{background:white;border:1px solid var(--line);border-radius:8px;padding:16px;margin:10px 0}summary{cursor:pointer;font-weight:650}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;background:white;table-layout:fixed}th,td{padding:11px 12px;border:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#e9f0f0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.5}code{font-size:12px}.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:16px 0;padding:12px;background:#e9f0f0;position:sticky;top:0;z-index:2}input[type=search]{min-width:250px;flex:1}input,select{font:inherit;padding:7px;border:1px solid #b9c8cd;border-radius:5px}label{white-space:nowrap}.badge{font-size:12px;display:inline-block;border-radius:4px;padding:2px 7px;background:#e2f4ed;color:#176347}.warn{background:#fff1dd;color:#784d12}.catalog td:nth-child(1){width:18%}.catalog td:nth-child(2){width:27%}.catalog td:nth-child(3){width:23%}.catalog td:nth-child(4){width:32%}[hidden]{display:none!important}.toc{display:flex;flex-wrap:wrap;gap:16px}@media(max-width:800px){main{padding:16px}table{min-width:950px}h1{font-size:26px}}\n</style>', '<main><h1>소비 도구 전체 조사</h1>',
 '<p class="lead">현재 저장된 룰북·보충자료·정오표·DB를 기준으로 품목과 실제 소비 경로를 대조했습니다. 아래 개수는 <b>별칭·변형·총칙을 포함한 정의 ID 수</b>입니다. 개별 효과의 구현 완료 수 또는 의미상 고유 품목 수가 아닙니다.</p>',
 '<nav class="toc"><a href="#scope">범위</a><a href="#hierarchy">공통 구조</a><a href="#followup">후속 검증</a><a href="#findings">발견 사항</a><a href="#catalog">전체 품목</a><a href="#machines">TM·HM</a><a href="#generated">발생형·별도 자원</a><a href="#runtime">코드 경로</a><a href="#dependencies">관련 규칙</a></nav>']
s=a['scope'];counts=s['relation_counts']
parts.append('<div class="cards">'+''.join('<div class="card">'+h(label)+'<b>'+h(value)+'</b></div>' for label,value in [('아이템 정의',s['item_definitions']),('소비·관련 정의 / 표제 제외',s['candidate_item_definitions']-counts['source_heading']),('원본 TM·HM',s['source_machine_codes']),('공통 stock 연결 ID',s['shared_stock_native_ids']),('원본 조사 완료 증가',0)])+'</div>')
parts.append('<div class="box" id="scope"><h2>조사 범위와 한계</h2><p>729개 정의 = 소비·이동·파괴 검토군 292 + 진화 도구 소비 여부 미확정 22 + 관련 본체·횟수 장비·제작 도구·책 130 + 총칙 표제 4 + 현재 소비 후보 아님 281.</p><p>입력 파일 38개(본문 20, CSV 17, 원본 메타데이터 1), 기존 표 패널 1,146개, 실행 모듈 137개를 색인했습니다. 표 패널에는 재능·포켓봇 데이터도 포함됩니다. 키워드 원문 '+str(s['lexical_source_hits'])+'곳과 관련 규칙 '+str(s['related_rule_index_entries'])+'개는 <b>검색 색인</b>이며 모두 개별 조항 검증을 마쳤다는 뜻이 아닙니다.</p><p>AST 차감 지점 23곳을 의미별로 분류했습니다. 간접 상태 변경을 전부 증명하는 분석은 아니며, 물리 파괴·만복 버프·화석 변환 등은 발견 사항에 별도로 기록했습니다.</p><p><b>현재 구현 진행도: '+h(progress_text)+'</b> · 남은 조항 '+format(remaining,',')+'. 원본 조사 묶음(consumable-audit-19)은 +0이며 당시 275 / 2,352였습니다. 아래 원본 조사 목록과 코드 위치는 그 시점의 기록이며 후속 수정은 별도 표시합니다.</p><p class="muted">상세 근거: <a href="category2-consumable-inventory-audit.json">전체 JSON</a> · <a href="category2-consumable-review.json">검토 판단 JSON</a> · 생성 시각 '+h(a['created_at'])+'</p></div>')
plan_path=ROOT/'data/verification/category2-consumable-family-plan.json'
if plan_path.exists():
 plan=json.loads(plan_path.read_text(encoding='utf-8'))
 parts.append('<section class="box" id="hierarchy"><h2>후속 구현: 상위 분류와 공통 인터페이스</h2><p><code>UseAdapter[RequestT]</code> 프로토콜로 실제 사용 경로를 연결했습니다. <code>ItemUse</code>는 공통 검사 후 준비·실행을 공유하고, <code>TransformationUse</code>는 원문 자격 확인·시간·재료 차감·산출·출처 기록을 함께 확정합니다. 수량/물리 인스턴스 저장은 <code>item_stock</code>에서 공유합니다.</p><p><b>즉시 소비형·효과 보관형·부착형의 기존 지원 품목과 변환형의 제작·분해·주얼·포핀 경로를 연결했습니다.</b> 장전형은 계약 정의 단계입니다. 변환형의 TM/HM·화석·연금술 등 별도 경로와 다른 미지원 품목은 아직 남았습니다. 기존 미분류 경로는 <code>UnclassifiedUse</code>로 남겨 검토된 분류인 것처럼 취급하지 않습니다.</p><div class="scroll"><table><thead><tr><th>상위 분류</th><th>정의 수</th><th>공유 흐름</th><th>실제 연결 상태</th></tr></thead><tbody>')
 for family in plan['families']:
  parts.append('<tr><td>'+h(family['name'])+'</td><td>'+str(family['definition_count'])+'</td><td>'+h(family['flow'])+'</td><td>'+h(family['status'])+'</td></tr>')
 parts.append('</tbody></table></div><p>동일 물품도 사용법에 따라 여러 처리를 조합합니다. 열매는 섭취 시 효과 보관형, 심을 때 설치형, 포핀 재료로 쓸 때 변환형입니다. 위 수량은 기본 분류를 하나씩 배정한 값이며, 복수 사용 모드는 별도 목록으로 보존합니다.</p><p><a href="category2-consumable-family-plan.json">444개 정의의 상위 분류 및 복수 사용 모드</a> · <a href="../../engine/consumable_use.py">공통 인터페이스 코드</a></p></section>')
parts.append('<section class="box" id="followup"><h2>후속 검증 결과 · consumable-family-20</h2><p>A02의 포획 도구 중복 차감을 수정하고, 기존 poke_ball 재고명도 실제 투척 경로에서 인식하도록 연결했습니다. 빗나간 공의 회수 가능 상태는 유지합니다. 음료의 수신자별 시간 제한 및 5종 회복량·가격·저장복원을 검증하여 C09-030, C09-103 두 조항을 완료했습니다.</p><p>검사 123개 통과: 신규 8개 + 기존 115개. 상위 분류나 연결 품목 수 자체는 완료 조항으로 환산하지 않았습니다. 다른 조사 발견 사항은 각각의 후속 검증이 필요합니다.</p><p><a href="category2-consumable-family-completion.json">후속 완료 근거와 실행 검사 기록</a></p></section>')
bandage_path=ROOT/'data/verification/category2-bandage-state-completion.json'
if bandage_path.exists():
 parts.append('<section class="box" id="bandage-followup"><h2>후속 검증 · 붕대 부착 상태</h2><p>공통 부착 기록 검사를 실제 사용, 시간 경과, 휴식, 저장복원에 연결했습니다. 트레이너와 포켓몬이 같은 6시간 수명·피해 시 해제·복수 붕대 수량·일일 부상 치유 한도를 공유합니다. C09-025, C09-027의 대분류2 상태 항목을 완료했습니다.</p><p>검사 31개 통과: 신규 4개 + 기존 27개, 20.403초. 파스 친밀도 문구 충돌, 전투 중 연장행동 스케줄링과 일부 휴식 구간의 치유 계산은 별도 미완료입니다.</p><p><a href="category2-bandage-state-completion.json">부착 상태 완료 근거</a></p></section>')
transform_path=ROOT/'data/verification/category2-crafting-resource-completion.json'
if transform_path.exists():
 parts.append('<section class="box" id="transform-followup"><h2>후속 검증 · 변환형과 제작 재료 상태</h2><p>제작·분해·주얼·포핀의 네 실행 경로를 같은 변환 인터페이스로 연결했습니다. 수량과 재료 가치는 서로 다른 단위로 기록하며, 원문 종류가 맞는 재료만 제작 비용으로 사용합니다. 약 파편으로 스프레이를 만들던 처리를 수정했습니다.</p><p>6색 조각의 18개 타입 변환, 종류별 재료 가치와 실제 결제, 실패 복구 및 저장복원을 확인해 C09-048, C09-049, C09-051을 완료했습니다. 검사 47개 통과: 신규 6개 + 기존 41개, 27.272초. 기존 검사 중 2개는 원문에 맞게 기대값·분류 근거를 고쳤습니다.</p><p>파편 종류의 목록은 열려 있습니다. 분류가 명시되지 않은 재료는 관련 종류와 GM 판단 근거를 저장합니다. 패셔니스타 전체 산출물의 분류 근거(C09-052), 장전형, 독립적인 TM/HM·화석·연금술 연결은 이번 완료에 포함하지 않습니다.</p><p><a href="category2-crafting-resource-completion.json">제작 재료 완료 근거</a> · <a href="../../engine/transformation_use.py">변환 인터페이스</a> · <a href="../../engine/crafting_resources.py">공통 재료 상태</a></p></section>')
vitamin_path=ROOT/'data/verification/category2-vitamin-limit-completion.json'
if vitamin_path.exists():
 parts.append('<section class="box" id="vitamin-followup"><h2>후속 검증 · 영양제 사용 한도와 PP업</h2><p>8종 영양제의 평생 공통 한도와 PP업의 선택 기술·빈도 상태를 검증했습니다. 임의 빈도 기술에 PP업 사용을 선택하면 효과는 없고, 실제 소모 및 포켓몬당 한 번의 기록은 남습니다. 영양사의 현재·과거 한도와 VM 점유도 같은 상태를 사용합니다.</p><p>C09-071, C09-072 완료. 실제 턴·장면·일일 기술 사용과 저장복원 검사 35개 통과: 신규 4개 + 기존 31개, 39.411초. 근거 없이 한도를 넘긴 저장 기록은 거절하고, 적법한 과거 영양사 사용 기록은 유지합니다.</p><p>장전형 SPOL-010은 미완료입니다. 의료 케이스의 약품 목록 차이, 볼-케이스 실물 관계, 회수/명중 시 내용물 적용, 적용 후 포획률 계산이 함께 해결되어야 합니다.</p><p><a href="category2-vitamin-limit-completion.json">영양제 완료 근거</a> · <a href="category2-loaded-case-deferred.json">장전형의 남은 의존성</a></p></section>')
parts.append('<h2>분류별 목록 규모</h2><div class="scroll"><table><thead><tr><th>분류</th><th>정의 수</th><th>공통 stock 연결</th><th>핵심 처리</th></tr></thead><tbody>')
for f in a['families']:
 if not f['definition_count']:continue
 shared=sum(x['family']==f['id'] and x['runtime_status']=='shared_stock_native_adapter' for x in a['items'])
 parts.append('<tr><td>'+h(f['name'])+'</td><td>'+str(f['definition_count'])+'</td><td>'+str(shared)+'</td><td>'+h(f['stock_contract'])+'</td></tr>')
parts.append('</tbody></table></div><h2 id="findings">원본 조사 발견 사항 · 이후 해결 여부는 후속 검증 참조</h2>')
for f in a['findings']:
 opened=' open' if f['id'] in ('A02','A05') else ''
 parts.append('<details class="issue"'+opened+'><summary>'+h(f['id']+' · '+f['title'])+'</summary><p>'+h(f['impact'])+'</p><p><b>후속 작업:</b> '+h(f['next_action'])+'</p><p class="muted">'+ '<br>'.join(source(x) for x in f['references'])+'</p></details>')
parts.append('<h2>묶음 구현 순서</h2><ol>'+''.join('<li>'+h(x)+'</li>' for x in a['implementation_order'])+'</ol><p>'+h(a['unresolved_policy'])+'</p>')
parts.append('<h2 id="catalog">전체 품목 · 이름/ID/원문 검색</h2><p>각 행의 소비 계약은 해당 분류를 위한 구현 기준입니다. 원문에 남아 있는 품목별 조건·예외·변형을 대체하지 않습니다. 원문을 열면 실제 추출 문구와 분류 근거를 볼 수 있습니다.</p><div class="toolbar"><input id="q" type="search" aria-label="품목 검색" placeholder="예: 열매, 리보플라빈, 소비, 카트리지"><select id="family" aria-label="분류"><option value="">모든 분류</option>')
for f in a['families']:
 if f['definition_count']:parts.append('<option value="'+h(f['id'])+'">'+h(f['name'])+'</option>')
parts.append('</select><label><input id="related" type="checkbox" checked> 소비·관련 정의만</label><span id="visible"></span></div><div class="scroll"><table class="catalog"><colgroup><col style="width:18%"><col style="width:27%"><col style="width:23%"><col style="width:32%"></colgroup><thead><tr><th>이름·분류</th><th>시점·수량</th><th>실패·상태</th><th>연결·원문</th></tr></thead><tbody id="rows">')
for x in a['items']:
 c=x['consumption_contract'];linked=x['runtime_status']=='shared_stock_native_adapter';related=x['relation'] not in ('not_flagged','source_heading')
 searchable=' '.join([x['id'],x['name'],x['family_name'],x['source_body'],x['catalog_description']]).lower()
 parts.append('<tr data-family="'+h(x['family'])+'" data-related="'+str(int(related))+'" data-search="'+h(searchable)+'"><td><b>'+h(x['name'])+'</b><br><code>'+h(x['id'])+'</code><br>'+h(x['family_name'])+'</td><td><b>시점:</b> '+h(c['when'])+'<br><b>수량:</b> '+h(c['quantity'])+'</td><td><b>실패:</b> '+h(c['failure'])+'<br><b>상태:</b> '+h(c['state'])+'</td><td><span class="badge'+('' if linked else ' warn')+'">'+('공통 stock 연결' if linked else '개별 연결/정책 검토')+'</span><br>'+h(c['shared'])+'<details><summary>원문·분류 근거</summary><p class="muted">'+source(x['source'])+'</p><pre>'+h(x['source_body'] or x['catalog_description'])+'</pre><p>'+h(x['classification_review']['reason'])+'</p><pre>'+j({'table_rows':x['table_rows'],'related_clause_ids':x['related_clause_ids'],'runtime_status':x['runtime_status']})+'</pre></details></td></tr>')
parts.append('</tbody></table></div><h2 id="machines">기술머신·비전머신 112개</h2><p>원본 TM106 + HM6. 현재 실행 카탈로그 TM99 + HM6. TM29는 본문 표에 기술명만 있고 번호가 누락되어 있으며 CSV에는 명시되어 있습니다. TM101~106은 CSV의 7세대 이후 추가 항목입니다. 동일 코드의 기술명/가격 차이도 병합하지 않았습니다.</p><div class="scroll"><table><thead><tr><th>코드·원본 기술</th><th>사용 규칙</th><th>실행 카탈로그</th><th>차이·출처</th></tr></thead><tbody>')
for x in a['machines']:
 r=x['runtime_record'];status='누락 — 자동 사용 지원 확정 불가' if r is None else r['move_name']+' / 카탈로그 존재(전체 효과 인증 아님)'
 parts.append('<tr><td>'+h(x['code']+' · '+x['move_name'])+'</td><td>'+('학습 완료 후 1개 소비' if x['kind']=='TM' else '본체 유지 · 하루 1회')+'</td><td>'+h(status)+'</td><td>'+source(x['source_record']['source'] if x['source_record'] else r['source'])+('<pre>'+j(x['differences'])+'</pre>' if x['differences'] else '')+'</td></tr>')
parts.append('</tbody></table></div><h2 id="generated">일반 ID 밖의 원문 자원·발생형 물품</h2>')
for x in a['source_only_resources']:
 parts.append('<div class="box"><b>'+h(x['name'])+'</b><p>'+h(x['lifecycle'])+'<br>'+h(x['status'])+'</p><p class="muted">'+'<br>'.join(source(r) for r in x['references'])+'</p></div>')
parts.append('<h2 id="runtime">원본 조사 시점 재고 차감·이동 코드 23곳</h2><div class="scroll"><table><thead><tr><th>위치</th><th>의미</th><th>코드</th></tr></thead><tbody>')
for x in a['runtime_sites']:
 parts.append('<tr><td>'+h(x['file']+':'+str(x['line']))+'<br><code>'+h(x['function'])+'</code></td><td>'+h(x['semantic_review']['meaning'])+'<br><code>'+h(x['semantic_review']['operation'])+'</code></td><td><pre>'+h(x['code'])+'</pre></td></tr>')
parts.append('</tbody></table></div><h2 id="dependencies">사용 조건을 바꾸는 기술·특성·재주·원문 색인</h2><p>리사이클·수확·숙성·긴장감·먹보·벌레먹기·내던지기·픽업·전통의학 참조서·포켓봇 제한 등을 개별 의존성으로 확인해야 합니다. 아래 목록은 관련 문구 검색 결과이며 예시/배경 설명도 포함합니다.</p><details class="box"><summary>관련 규칙 '+str(len(a['related_rules']))+'개 펼치기</summary><ul>')
for x in a['related_rules']:
 parts.append('<li><code>'+h(x['id'])+'</code> · '+source(x['source'])+'</li>')
parts.append('</ul></details><p class="muted">이 보고서는 물품 정의와 소비 구조의 조사 결과입니다. 품목 수나 검사 수를 완료 조항으로 환산하지 않습니다.</p></main>')
parts.append("<script>\nconst rows=Array.from(document.querySelectorAll('#rows tr'));\nfunction filter(){const q=document.getElementById('q').value.toLowerCase().trim();const family=document.getElementById('family').value;const related=document.getElementById('related').checked;let n=0;for(const row of rows){const show=(!q||row.dataset.search.includes(q))&&(!family||row.dataset.family===family)&&(!related||row.dataset.related==='1');row.hidden=!show;if(show)n++;}document.getElementById('visible').textContent=n+' / 729개 표시';}\nfor(const id of ['q','family','related'])document.getElementById(id).addEventListener('input',filter);\nfilter();\n</script></html>")
vitamin_family_path=ROOT/'data/verification/category2-vitamin-family-completion.json'
if vitamin_family_path.exists():
 family=json.loads(vitamin_family_path.read_text(encoding='utf-8'))
 checked=family['tests'];result=checked['final_result']
 section='<section class="box" id="vitamin-family-followup"><h2>후속 검증 · 영양제 8종 공통 사용</h2><p>UseAdapter 인터페이스와 ItemUse 추상 클래스 아래에서 8종을 VitaminUse 하나로 통합했습니다. 대상·한도·수량 또는 실제 물품·행동 비용·사용 이력을 공유하고, 능력치·가르침 포인트·선택 기술 빈도 효과를 구별합니다. 중복 능력치 영양제 코드를 제거하고, 효과 적용 중 오류가 나면 소모와 상태 변경이 함께 취소되도록 했습니다.</p><p>C09-145 원문 표 한 조항을 완료했습니다. 검사 '+h(result['tests'])+'개 통과: 신규 '+h(checked['new_methods'])+'개 + 기존 '+h(checked['existing_methods'])+'개, '+h(result['seconds'])+'초. 원문 8종의 효과·가격·한도, 실제 턴과 양쪽 저장복원, 소모 이후 오류 복구를 검증했습니다.</p><p>5개 문맥별 능력 강화 조항은 실제 사용 경로 의존성을 기록하고 미완료로 유지합니다. 장전형 등 다른 분류의 완성을 뜻하지 않습니다.</p><p><a href="category2-vitamin-family-completion.json">공통 사용 완료 근거</a> · <a href="../../engine/consumable_use.py">인터페이스와 추상 클래스</a></p></section>'
 position=next(i for i,part in enumerate(parts) if 'id="vitamin-followup"' in part)+1
 parts.insert(position,section)

cultivation_path=ROOT/'data/verification/category2-cultivation-state-completion.json'
if cultivation_path.exists():
 cultivation=json.loads(cultivation_path.read_text(encoding='utf-8'))
 checked=cultivation['tests'];result=checked['final_result']
 section='<section class="box" id="cultivation-followup"><h2>후속 검증 · 공통 식물과 수확 상태</h2><p>나무열매·규토리·허브가 같은 식물 상태와 수확 기록을 사용합니다. 심은 시각, 선택한 플랜터 규칙, 토양과 특성 보정, 실제 주사위, 하루 시도와 재고 변화를 보존합니다. 수확물이 0개여도 그날 시도는 남으며, 실제 수확한 열매를 공통 음식 경로로 소비하는 것까지 확인했습니다.</p><p>C09-033, C09-034, C09-105 세 조항 완료. 검사 '+h(result['tests'])+'개 통과: 신규 '+h(checked['new_methods'])+'개 + 기존 '+h(checked['existing_methods'])+'개, '+h(result['seconds'])+'초. 플랜터의 출처 간 수용량·성숙 차이와 비료 상한 해석은 별도 미완료입니다.</p><p>향기버섯의 수확식은 기존 식물의 명시적 GM 관측으로 검증했으며, 원문에 없는 재배 권한을 부여하지 않았습니다. 규칙을 데이터·스크립트로 작성하는 장기 구조 요구도 설계 지침으로 기록했습니다.</p><p><a href="category2-cultivation-state-completion.json">식물·수확 완료 근거</a> · <a href="../../data/rule-engine-direction.json">장기 규칙 작성 구조</a></p></section>'
 position=next(i for i,part in enumerate(parts) if 'id="vitamin-family-followup"' in part)+1
 parts.insert(position,section)

lifetime_path=ROOT/'data/verification/category2-lifetime-consumables-completion.json'
if lifetime_path.exists():
 section='<section class="box" id="lifetime-consumables-followup"><h2>후속 검증 · 평생 소비 한도와 성장</h2><p>이상한사탕 C09-074 완료. 두 도구 ID와 수량·실물 소비가 같은 개체의 평생5회 이력을 사용합니다. 다음 레벨까지 필요한 경험치만 지급하고, 영양제 슬롯은 차지하지 않습니다. 진화·소유자 변경·일자 변경·GM/파일 복원 후에도 한도가 유지됩니다.</p><p>실제 물품·행동·성장·이력을 함께 확정하며, 중간 오류는 모두 반영되지 않습니다. 기존 캐릭터의 과거 사용 횟수가 없으면 확인할 때까지 보류합니다. 신규6개+기존27개 검사, 총33개 통과(39.538초). 억제제의 원문/번역 차이와 범용 스크립트 실행기는 별도 미완료입니다.</p><p><a href="category2-lifetime-consumables-completion.json">완료 근거</a> · <a href="../lifetime-consumable-policy.json">데이터로 분리한 규칙 정의</a></p></section>'
 position=next(i for i,part in enumerate(parts) if 'id="cultivation-followup"' in part)+1
 parts.insert(position,section)

maturation_path=ROOT/'data/verification/category2-item-maturation-completion.json'
if maturation_path.exists():
 section='<section class="box" id="item-maturation-followup"><h2>후속 검증 · 지닌 열매와 껍질 속 생산물</h2><p>C10-063 완료: 실제 열매 개체의 지닌 시점과 미소모 상태를 추적하여24시간 뒤 껍질 속 주스로 바꿉니다. 열매 사용·내려놓기는 연속 보유를 중단하고, 서로 다른 열매의 시간은 독립적으로 유지됩니다. GM/파일 저장복원과 실제 물품 연결을 검증했습니다.</p><p>2주 후 사탕 생성과 실제 사탕 사용까지 구현했으나, 27번 묶음 당시에는 주스의 소비·병입 경로가 남아 C10-064/065를 미완료로 유지했습니다. 이후 완료 여부는 아래 후속 검증을 참조하십시오. 신규8개+기존87개, 총95개 검사 통과(43.610초). 이번 완료 집계는1조항입니다.</p><p><a href="category2-item-maturation-completion.json">시간 변환 검증과 남은 의존성</a> · <a href="category2-mulch-source-deferred.json">비료 원문 비교</a></p></section>'
 position=next(i for i,part in enumerate(parts) if 'id="lifetime-consumables-followup"' in part)+1
 parts.insert(position,section)

contents_path=ROOT/'data/verification/category2-container-contents-completion.json'
if contents_path.exists():
 section='<section class="box" id="container-contents-followup"><h2>후속 검증 · 재사용 용기와 내용물</h2><p>C10-064/065 완료: 껍질 속 주스의 실제 간식 소비, 실제 빈 병으로의 이동, 다른 포켓몬·트레이너의 음료 소비와 2주 숙성 중단을 연결했습니다. 내용물만 소비하고 병은 남으며, 같은 병을 꿀·우유에 재사용합니다. 원문과 상태 관계, GM/파일 복원, 중복 소비·누락된 실물·손상된 이력의 거부를 검증했습니다.</p><p>신규8개+기존89개, 총97개 검사 통과(47.921초). 이번 완료는2조항입니다. 임의 용량·혼합물과 약품 케이스별 발동, 전투 중 장시간 음식 섭취 절차 전체를 완료한 것으로 집계하지 않습니다.</p><p><a href="category2-container-contents-completion.json">원문 대조 및 완료 근거</a> · <a href="../item-container-policy.json">용기 정책</a></p></section>'
 position=next(i for i,part in enumerate(parts) if 'id="item-maturation-followup"' in part)+1
 parts.insert(position,section)

out=ROOT/'data/verification/category2-consumable-audit.html'
out.write_text(''.join(parts),encoding='utf-8')
print(json.dumps({'report':str(out),'bytes':out.stat().st_size,'item_rows':len(a['items']),'machine_rows':len(a['machines']),'findings':len(a['findings'])},ensure_ascii=False))
