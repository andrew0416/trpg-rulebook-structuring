"""Build a reviewable candidate graph, never freeze or certify foundations."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'data/verification/category2-edge-work-plan.json'
# Explicit semantic grouping. Unknown operations fail instead of falling into a catch-all.
GROUPS = {
'acquisition': 'repeat_acquisition distinct_choices distinct_repeat bounded_distinct_repeat ranked_acquisition choice_record category_choice type_choice weapon_choice stat_choice ability_choice move_choice capability_choice movement_choice generation_choice allocated_stat_prerequisite creation_phase_predicate owner_feature_predicate acquisition_prerequisite_substitution conditional_refund retained_investment one_time_resource_grant per_rank_resource_spend gift_grant patron_relation',
'roll_context': 'purpose_match dice_pool_adjustment roll_total_addition effective_rank_override skill_substitution substitution_prohibition purpose_skill_substitution target_skill_substitution training_skill_substitution derived_skill_substitution contest_skill_substitution purpose_bonus skill_bonus skill_set_bonus purpose_skill_bonus purpose_roll_bonus scoped_effective_rank roll_bonus_from_max_rank timed_dice_bonus opposed_roll_bonus opposed_skill_substitution skill_roll skill_dc automatic_success helper_formula_override resource_bonus_replacement',
'composition': 'nonstacking_by_target capability_value_addition capability_grant capability_grant_or_increment conditional_skill_grant skill_rank_addition skill_rank_transition',
'crafting': 'recipe_permission inventory_transaction material_spend resource_cost_substitution craft_or_apply regional_service component_substitution',
'cultivation': 'cultivation_permission world_site growth_time',
'object_lifecycle': 'object_damage_state repair_or_destroy spawn_entity body_size_predicate body_eligibility equipped_predicate target_predicate keyword_predicate condition_category_query species_rank_comparison species_stat_sum',
'activity': 'activity_time timed_activity activity_credit extended_check',
'growth': 'level_transition evolution_prohibition allocated_bonus_points restricted_bonus_allocation base_stat_addition base_relation_exemption evolution_recalculation level_one_points_provenance skill_background_change evolution_branch_choice',
'learning': 'move_grant natural_ability_choice ability_grant linked_move_query slot_exemption slot_reservation alternate_learnset move_learning natural_route learning_provenance',
'combat': 'critical_range_addition critical_event status_move_critical hit_event keyword_evasion damage_cause_predicate context_damage_reduction accuracy_override attack_range_override action_range_override action_accuracy_override range_modifier',
'effects': 'condition_apply condition_remove timed_save_modifier condition_save_modifier duration_override temporary_hp shock_immunity item_heal_bonus',
'events': 'attempt_event post_action_event relation_event_delivery training_event',
'resources': 'conditional_resource_spend action_cost action_cost_override equipment_action_cost recipient_action_cost_exception success_gated_frequency shared_turn_budget',
'movement': 'movement_distance_override movement_bonus movement_path_permission rank_based_distance rank_based_breath_limit',
'maneuvers': 'grapple_outcome_choice',
'training': 'obedience training_limit owner_dependent_limit multi_target_training training_xp_formula xp_bonus',
'creation': 'breeding_eligibility identification',
'perception': 'information_delivery range_addition_from_rank',
'control': 'control_eligibility vehicle_control machine_permission',
'network': 'digital_participation network_participation',
'repair': 'vehicle_hp_repair breach_patch',
'environment': 'interval_capability_grant interval_allocation home_environment_baseline',
'initiative': 'rank_derived_initiative',
}
# Input -> observable output; checks describe behavior, not helper implementation.
SPECS = {
'source_policy': ('선택한 원문·판본·정정·GM 위임 범위', '상충 정책의 명시적 선택과 추적 가능한 판정 근거', ['Mixed Sweeper 세 판본의 비용·효과를 섞지 않는다', '미확정 수식을 임의 기본값으로 실행하지 않는다'], [], ['source_catalog','source_context','native_rule_policy']),
'object_lifecycle': ('실제 개체 ID·종류·소유·통제·실물 구성', '참조가 유효한 생성·변경·파괴와 속성 질의', ['가상 ID나 다른 객체의 부품으로 자격을 얻지 못한다', '파괴와 사용불능·일시 억제를 구분한다'], ['source_policy'], ['world_entities','special_entities','pokemon_entities']),
'atomic_transition': ('복수 객체·자원·이벤트의 한 작업 변경안', '검증 후 일괄 반영 또는 전체 원상 유지', ['비용 검증 후 대상 변경 실패 시 비용도 보존한다', '동일 사건 재전달이 이중 지급·환불을 만들지 않는다'], ['object_lifecycle'], ['state_grants','resolution_transaction']),
'acquisition': ('취득자·제공자·선택·전제·실제 지불·면제·영구/임시 출처', '취득 영수증·의존성·회수 및 실제 비용 기준 환불', ['무료·묶음 취득을 개별 유료 취득처럼 환불하지 않는다', '재훈련이 남은 전제나 되돌릴 수 없는 사용을 훼손하면 거절한다', 'Dilettante 면제가 해당 출처의 지정 전제에만 적용된다'], ['source_policy','atomic_transition'], ['acquired_features','pokemon_teaching','state_grants']),
'composition': ('기준값과 출처별 기여·중첩 정책·적용 대상', '파생 값과 남아 있는 유효 출처', ['임시 부여 만료가 같은 능력의 영구 소유를 지우지 않는다', '랭크 증가와 유효 랭크 대체가 실제 주사위 수를 임의로 혼동하지 않는다'], ['acquisition'], ['state_grants','skill_modifiers','capability_traits']),
'roll_context': ('판정 목적·대상·제공자·대항자·원래 스킬과 주사위', '해당 목적에 한정한 주사위·상수·대체·재굴림 결과', ['일반 판정 보너스가 능력 파생 공식에 자동 적용되지 않는다', 'Dowsing 특수 Skill Stunt가 일반 -1d6/+6 처리와 섞이지 않는다'], ['composition','source_policy'], ['skill_modifiers','common_checks','skill_stunts','engine']),
'resources': ('시도/성공/종료 시점·행동권·AP·횟수·대상별 키', '정확한 시점의 소비·예약·반환', ['성공 시 소비와 시도 시 소비를 실패 사례에서 구분한다', '차량과 조종자가 공유하는 행동권을 두 번 쓸 수 없다'], ['atomic_transition','source_policy'], ['frequency','action_points','turn','action_lifecycle']),
'events': ('원인·실행 단계·시전자·대상·결과·사건 ID', '조건에 맞는 후속 효과와 근거 기록', ['명중·치명타·행동 완료·시도를 서로 대신 발행하지 않는다', 'Breather 후속 효과는 전체 행동 성공 후 정확히 한 번 발생한다'], ['atomic_transition','source_policy'], ['passive_events','event_effects','action_lifecycle']),
'activity': ('참여자·기간·일/시간 슬롯·누적 판정·중단 조건', '시간 지출과 중첩 가능한 훈련 활동 및 누적 진행', ['동일 훈련 시간의 가르치기·경험치 기여를 별도 한 시간씩 중복 청구하지 않는다', 'Dream Machine 누적 판정 간 하루 제한과 8시간 세션을 보존한다'], ['resources','events'], ['downtime','pokemon_activities','rest_intervals']),
'growth': ('종족·성격·레벨·실제 배분·진화 분기·투자 내역', '제약을 만족하는 재계산과 일회성 성장 지급', ['진화 후에도 유효한 기여와 회수 대상 기여를 분리한다', '레벨1 배분과 추가 투자 포인트를 구분해 전제를 검사한다'], ['composition','atomic_transition'], ['pokemon_progression','pokemon_stat_edges','nature_state']),
'learning': ('기술·특성·학습 경로·레벨·종족·슬롯 출처', '실제 사용 가능한 기술/특성과 경로별 슬롯 계산', ['동일 기술의 자연 학습 전환이 잘못된 빈 슬롯이나 중복 기술을 만들지 않는다', '독립적인 두 부여 출처 중 하나 회수 후 남은 기술은 유지된다'], ['composition','growth'], ['move_state','ability_transitions','pokemon_move_edges']),
'combat': ('공격 유형·피해 분류·공격 수치 선택·사거리·방어·조건', '명중/피해와 적용된 보정 내역', ['염력 Struggle은 특수공격 수치를 쓰더라도 Normal 물리 피해를 유지한다', 'Status 기술의 치명타 가능 여부를 일반 피해 치명타와 구별한다'], ['roll_context','resources','events'], ['engine','combat_modifiers','struggle_capabilities','move_accuracy']),
'effects': ('효과 원인·출처·분류·대상·지속·중첩·해제 조건', '조건·면역·임시 HP·회복의 실제 상태 변화', ['한 출처 제거로 독립 출처의 같은 조건까지 제거하지 않는다', '식품 버프 획득 시점과 발동·소모 시점을 구별한다'], ['composition','events','resources'], ['condition_instances','effect_instances','effect_lifetimes','temporary_hp','food_effects']),
'movement': ('실제 위치·맵·경로·이동 방식·하중·허용/금지', '검증된 위치 변화와 이동 예산 소비', ['같은 수치의 사거리 증가가 이동력까지 증가시키지 않는다', '기승자는 탈것 이동량을 자기 차례에 다시 초기화하지 못한다'], ['object_lifecycle','resources','composition'], ['movement_actions','grid','physical_limits','telekinetic_load']),
'maneuvers': ('실제 참가자·행동 종류·명중·대항·거리·선택', '밀기·넘어뜨리기·무장해제·붙잡기 관계의 변화', ['염력 밀기는 Focus/2 거리이며 일반 반복 밀기 절차를 물려받지 않는다', '붙잡기 탈출 보너스가 모든 붙잡기 공격에 적용되지 않는다'], ['combat','movement','effects'], ['combat_maneuvers','maneuver_edges','physics_maneuvers']),
'crafting': ('레시피·권한·실물 재료·금액·도구·지역', '원자적인 소비와 결과물 생성/적용', ['속성 조각과 제작용 고철은 서로 대체되지 않는다', '제작 실패가 재료를 소모하거나 결과물을 중복 생성하지 않는다'], ['activity','object_lifecycle','atomic_transition'], ['crafting_activities','crafting_resources','items']),
'cultivation': ('실제 식재·토양·비료·성숙 시간·수확 주기', '성장 상태와 원문 수확 주사위/수량', ['하루 두 번 수확하거나 실물 없는 비료를 적용하지 못한다', '0 이하 수확을 음수 재고로 만들지 않는다'], ['crafting','roll_context'], ['cultivation_state','item_maturation']),
'training': ('훈련자·대상들·안전·소유·시간·날짜·적용 판본', '허용 대상 수·복종·경험치와 활동 크레딧', ['훈련 대상 수 계산과 경험치 계산의 스킬 대체를 분리한다', 'Pokemon 하루 한 번 XP 제한을 다른 훈련자로 우회하지 않는다'], ['activity','growth','roll_context'], ['training_features','pokemon_activities','pokemon_understanding']),
'creation': ('부모/화석·종족·도구·자격·상속 가능한 기술·선택', '출처가 보존된 새로운 알/개체', ['화석 부활에 일반 교배 부모와 레벨1을 강요하지 않는다', '부모가 배우지 않은 기술을 단순 종족 목록만 보고 상속하지 않는다'], ['growth','learning','crafting'], ['pokemon_entities','pokemon_requests','species_metadata']),
'perception': ('실제 위치·범위·조건·감지 방식·허용 공개 정보', '감지 결과 또는 전달 가능한 정보와 실패 이력', ['존재 감지가 정체·정확한 좌표를 추가 공개하지 않는다', 'Telepathy의 실패 페널티는 같은 대상과 24시간 범위만 적용한다'], ['roll_context','resources','object_lifecycle'], ['capability_traits','context_actions','blessing_effects']),
'control': ('실제 조종자·몸체 자격·장비·동의·관계', '제어 권한과 공유 행동/명령 경로', ['Wired의 단일 실물 제어와 일반 Vehicle Training을 구분한다', '보유 능력 플래그만으로 장비 없는 머신을 사용하지 못한다'], ['object_lifecycle','resources','movement'], ['special_entities','context_actions']),
'network': ('접속 근거·실제 네트워크·앵커·Integrity·프로그램', '진입·공격·복구·퇴출 및 종속 연결 해제', ['앵커 퇴출은 연결 대상의 별도 Integrity를 감소시킨다', '물리 HP와 Integrity 및 물리 장비와 프로그램을 섞지 않는다'], ['control','combat','effects'], ['supplemental_state']),
'repair': ('손상 객체·원인·HP·파공·패치·비용·기술 판정', '대상 종류에 맞는 수리와 기능/보호 상태', ['패치된 파공도 파공 용량에는 계속 포함된다', '유기체 회복으로 차량을 고치거나 영구 수리와 임시 패치를 혼동하지 않는다'], ['crafting','roll_context','effects'], ['special_entities','pokebot_state']),
'environment': ('실제 환경·지역·고향 중력·허용 구간·장비 설정', '해당 조건의 능력/보정과 환경 변화 반영', ['개체 허용 구간과 환경 자체의 중력 단계를 혼동하지 않는다', '원문 없는 중력 효과 수식을 만들어 실행하지 않는다'], ['composition','activity','movement'], ['environmental_effects','terrain_actions','weather_state']),
'initiative': ('속도/랭크·조종 관계·일시 순서 변경', '실제 차례 순서와 만료 후 복원', ['일시 initiative 0이 원래 속도 수치를 파괴하지 않는다', '차량 차례가 조종자 속도에서 파생되는 적용 범위를 지킨다'], ['composition','events','control'], ['initiative','combat_timing']),
'scripting': ('외부 작성 규칙의 타입화된 선언·선택·허용 실행 연산', '원문 식별·검증·바인딩·실행·결과 추적', ['엔진 코드를 고치지 않고 외부 선언 두 개를 같은 기반에 연결하여 실행한다', '미지원 연산/미결 필수 정책은 상태 변경 전에 거절한다'], ['source_policy','atomic_transition'], ['rule_blueprints','effect_contracts','root_resolution']),
}
GIFT = {
'action_permission':'resources','action_prohibition':'resources','component_substitution':'crafting','condition_immunity':'effects','dice_reroll':'roll_context','edge_grant':'acquisition','entity_detection':'perception','environment_modifier':'environment','equipment_modifier':'composition','forced_movement':'movement','identification':'perception','injury_provenance':'effects','move_grant':'learning','move_immunity':'effects','opponent_modifier':'roll_context','opposed_bonus':'roll_context','purpose_modifier':'roll_context','recovery_rate':'effects','regional_recovery':'effects','relation_channel':'perception','resource_bonus_replacement':'roll_context','scene_detection':'perception','target_modifier':'roll_context','terrain_override':'environment','world_information':'perception'}
CONSUMERS = {
'alluring':'perception resources roll_context','stealth':'perception combat movement','telekinetic':'movement combat maneuvers roll_context','telepathy':'perception roll_context resources','threaded':'movement combat resources','tracker':'perception roll_context resources','tremorsense':'perception','underdog_identity':'object_lifecycle acquisition',
'augmentation_shock':'effects combat composition','vehicle_permission':'control','network':'network','dream_machine':'activity control growth roll_context resources','disarm':'maneuvers','dirty_trick':'maneuvers effects resources','manipulate':'maneuvers effects resources','push':'maneuvers movement','trip':'maneuvers effects','grapple':'maneuvers movement effects','breather':'resources movement effects events roll_context','pokemon_stats':'growth','pokemon_learning':'learning','pokemon_progression_evolution':'growth learning acquisition','training':'training','mount':'control movement roll_context','digestion':'effects crafting','cultivation':'cultivation','craft_resources':'crafting','dowsing':'crafting roll_context activity','poffin_contest':'composition resources roll_context growth','poffin_recipe':'crafting','breeding':'creation','fossil':'creation','bait':'perception resources activity roll_context','pokebot_base':'object_lifecycle control repair growth combat effects environment','vehicle_base':'object_lifecycle repair control combat effects','vehicle_operation':'control repair roll_context resources','shock_trigger':'combat effects','trainer_entitlements':'acquisition growth','trainer_retraining':'acquisition','gravity_interval':'environment'}

def build():
 data=json.loads(PLAN.read_text(encoding='utf-8')); d=data['foundation_discovery']
 assert d['denominator'] is None, 'Frozen inventory must not be regenerated silently'
 opmap={}
 for group, ops in GROUPS.items():
  for op in ops.split():
   assert op not in opmap, op
   opmap[op]=group
 contracts={k:{'id':k,'input':v[0],'observable_output':v[1],'acceptance_scenarios':v[2],'depends_on':v[3],'runtime_candidates':v[4],'requirement_refs':[],'status':'candidate; unit boundaries and implementation acceptance not frozen'} for k,v in SPECS.items()}
 for k,c in contracts.items():
  assert set(c['depends_on'])<=contracts.keys(),k
  assert all((ROOT/'engine'/(n+'.py')).exists() for n in c['runtime_candidates']),k
 visiting=set();visited=set()
 def walk(k):
  assert k not in visiting, 'dependency cycle: '+k
  if k in visited:return
  visiting.add(k)
  for child in contracts[k]['depends_on']:walk(child)
  visiting.remove(k);visited.add(k)
 for k in contracts:walk(k)
 requirements=[]
 def add(ref, text, groups, source):
  assert groups and set(groups)<=contracts.keys(),ref
  requirements.append({'ref':ref,'requirement':text,'candidate_contracts':sorted(set(groups)),'source':source,'status':'candidate mapping; consumer-path acceptance audit pending'})
  for group in set(groups):contracts[group]['requirement_refs'].append(ref)
 def definition(ref,row,ops):
  for i,op in enumerate(ops):
   assert op in opmap, 'Unmapped operation: '+op
   add(ref+'/operation/'+str(i),op,[opmap[op]],{k:row[k] for k in ['file','record','start','end'] if k in row})
  add(ref+'/acquisition','Source-selected acquisition, permission, provider, removal and script binding',['source_policy','acquisition','scripting'],{k:row[k] for k in ['file','record','start','end'] if k in row})
 for row in d['csv_records']:
  if row['kind']=='definition':definition(row['file']+':R'+str(row['record']),row,row['obligation_review']['operations'])
 for key in ['main_body_definition_review','supplement_definitions_reviewed']:
  for row in d[key]:definition(row['file']+':L'+str(row['start']),row,row['operation_candidates'])
 for row in d['minor_gift_candidates']:
  ref=row['file']+':L'+str(row['start'])
  add(ref+'/gift-outcome',row['requirements'],[GIFT[f] for f in row['requirements']['family_candidates']],{'file':row['file'],'start':row['start'],'end':row['end']})
  add(ref+'/acquisition','Actual patron, GM permission and independent grant lifetime',['source_policy','acquisition','scripting'],{'file':row['file'],'start':row['start'],'end':row['end']})
 for row in d['consumer_dependency_reviews']:
  groups=row['candidate_contracts'] if 'candidate_contracts' in row else CONSUMERS[row['id']].split()
  # Each retained obligation is linked; multi-contract section assignments still require finer audit.
  for i,behavior in enumerate(row['required_behaviors']):
   add('consumer/'+row['id']+'/'+str(i),behavior,groups,{'file':row['file'],'start':row['start'],'end':row['end']})
 for row in d.get('original_source_dependency_reviews', []):
  for i, behavior in enumerate(row['required_behaviors']):
   add('original/'+row['id']+'/'+str(i), behavior, row['candidate_contracts'], {'file':row['file'], 'pages':row['pages'], 'source_sha256':row['source_sha256']})
 name_search=json.loads((ROOT/'data/verification/edge-name-search-candidates.json').read_text(encoding='utf-8'))
 for row in name_search['rows']:
  mapping=row.get('contract_mapping')
  if mapping:
   add('named/'+row['file']+':L'+str(row['line']), mapping['semantic_obligation'], mapping['candidate_contracts'], {'file':row['file'],'start':row['line'],'end':row['line']})
 for row in d.get('english_alias_search', {}).get('rows', []):
  if row.get('candidate_contracts'):
   add('alias/'+row['file']+':L'+str(row['line']), row['reason'], row['candidate_contracts'], {'file':row['file'],'start':row['line'],'end':row['line']})
 for row in d['discovered_requirements']:
  add(row['id'],row['requirement'],['acquisition','composition','source_policy'],row['sources'])
 assert len({r['ref'] for r in requirements})==len(requirements)
 for c in contracts.values():
  c['direct_requirement_count']=len(c['requirement_refs'])
  c['required_by_contracts']=[k for k,v in contracts.items() if c['id'] in v['depends_on']]
  assert c['requirement_refs'] or c['required_by_contracts'],c['id']
 d['candidate_contract_graph']={
  'status':'unfrozen candidate graph, not the foundation denominator',
  'contracts':list(contracts.values()),'requirements':requirements,
  'validation':{'requirements':len(requirements),'unique_refs':True,'unmapped_extracted_operations':0,'dangling_contract_refs':0,'dependency_cycles':0,'runtime_paths_exist':True,'runtime_acceptance_verified':False},
  'coverage_limits':['Covers extracted CSV/body/supplement/gift operations and reviewed consumer sections (including original PDF dependencies); this does not certify unextracted source coverage.', 'Consumer section assignment is conservative and multi-contract; each behavior needs precise execution-owner review.', 'Candidate contracts may need independent acceptance units before freezing; their count is not progress denominator.', 'Remaining source questions and original-source adjudications must be closed or validly delegated, never replaced by an invented default.']}
 audit=[]
 for name,findings in [
 ('pokebot_state',[('project', 'Component state projection exists; module docstring excludes crafting/actions. wired_projection explicitly leaves interface permission unchecked. Full execution is not certified.')]),
 ('special_entities',[('validate_pokebot','Source-specific object invariants and immunity correction SPOL-028 exist; control_permission_checked and component_acquisition_certified remain false.'),('validate_vehicle','State validation exists, not a repair/damage executor.'),('vehicle_view','Patched breach protection vs capacity is represented; combat_adapter_available is explicitly false.')]),
 ('supplemental_state',[('avatar','Avatar invariants and anchor capacity exist. Returned ejection data is not proof that ejection events execute; Original PDF p71 supports replacing HP multiplier 3 with Technology rank/2; arithmetic rounding and actual action integration still need verification.')]),
 ('rule_blueprints',[('validate','Authoring schema validates unresolved obligations; not executable scripting.'),('resolved_contract','Returns a contract only; docstring explicitly excludes execution authorization.')]),
 ('pokemon_capability_edges',[('validate','Requires point_cost exactly 1 and level >=20 without provider-specific waivers. Cannot represent Empowered Development grants faithfully.'),('reconcile_spec','Refund is hard-coded +1 per ended edge; grouped or free acquisitions need payment provenance and scoped prerequisite lifetime before this can be reused.')]),
 ('pokemon_teaching',[('_teach_edge','Ordinary Skill Improvement charges exactly 1TP and checks species baseline; no provider-scoped prerequisite waiver or shared acquisition payment.')]),
 ('pokemon_skill_edges',[('refund_excess','Permanent skill overflow refunds exactly 1TP, tied to fixed-cost receipt. Does not certify grouped/free-acquisition refund behavior.')])]:
  f=ROOT/'engine'/(name+'.py'); text=f.read_text(encoding='utf-8-sig'); tree=ast.parse(text); funcs={x.name:x for x in tree.body if isinstance(x,ast.FunctionDef)}
  for symbol,finding in findings:
   node=funcs[symbol];audit.append({'file':f.relative_to(ROOT).as_posix(),'symbol':symbol,'start':node.lineno,'end':node.end_lineno,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'finding':finding,'evidence_level':'source implementation inspected; no new runtime certification','completion_credit':0})
 d['runtime_contract_audit']=audit
 # Discovery next actions are maintained in the authoritative plan; graph regeneration must preserve them.
 PLAN.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(d['candidate_contract_graph']['validation'],ensure_ascii=False))
 print('candidate_contracts',len(contracts),'runtime_findings',len(audit),'foundation_denominator',d['denominator'])

if __name__=='__main__':build()
