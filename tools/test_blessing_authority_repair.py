"""Source-bound patron, confirmed role, and independent region regressions."""
from copy import deepcopy
from pathlib import Path
import csv
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon
import action_points as AP
import blessing_skill_features as B
import blessing_observations as O
import items
import native_scenario_fixture as NATIVE
import perception_observe as OBSERVE
import state_codec as CODEC
import survivalist_features as SURVIVALIST
import tools.test_csv_blessings32 as CSV_TESTS

ROYAL='gift/마이너-기프트-로얄-하트'
DREAM='gift/마이너-기프트-드림-마스터리'
REGION='gift/마이너-기프트-벌컨의-직감'
CLOUDS='gift/마이너-기프트-구름-읽기'
INSIGHT=B.INSIGHT
VALUES={'allegiance':'청색단','weaknesses':['빛','소금'],'goals':'구조','motives':'연민','harms_patron_followers':False}


class BlessingAuthorityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')

 def fixture(self):
  case=CSV_TESTS.SourceBoundaries('runTest');case.rules=self.rules;case.setUp();return case

 def pending(self,case,gift,patron=None):
  if gift in B.PREREQUISITES:
   required=B.PREREQUISITES[gift][1]
   if required not in case.a.spec['gifts']:
    case.own(required,B.GRANTING_PATRONS[required][1][0])
  case.a.spec['gifts'].append(gift)
  if patron is not None:case.a.spec['gift_patrons'][gift]=patron

 def confirm(self,case,gift,authority=None):
  configuration={'education_skills':['생존','기술학']} if gift==B.ADVANCED.FOUNT_OF_KNOWLEDGE else {}
  if authority is not None:configuration['authority']=authority
  return case.e.confirm_blessing_gift(case.a,gift,reason='GM explicitly confirms this already acquired source-bound Gift',configuration=configuration or None)

 def reject(self,case,operation,pattern):
  pending=[gift for gift in case.a.spec.get('gifts',[]) if gift in B.SOURCES
           and gift not in case.a.spec.get('_blessing_gift_approvals',{})]
  if pending:
   # An unconfirmed claim intentionally cannot be exported as valid gameplay.
   # Compare its complete mutable native prefix while testing confirmation refusal.
   import gm_state,world_entities as WORLD
   e=case.e;actors=WORLD.actor_index(e)
   memo={id(e):e,id(e.gm):e.gm,id(e.r):e.r,**{id(a):a for a in actors.values()}}
   def state():
    return deepcopy(({uid:vars(a) for uid,a in actors.items()},
      {key:getattr(e,key) for key in gm_state.ENGINE_FIELDS if hasattr(e,key)},
      e.log_lines,e.gm_prompts,vars(e.gm),e.rng.getstate(),vars(e.rulings)),memo.copy())
   before=state()
   try:
    with self.assertRaisesRegex(ValueError,pattern):operation()
   finally:self.assertEqual(state(),before)
   return
  return NATIVE.assert_rejected_unchanged(case.e,operation,reason_pattern=pattern)

 def test_exact_twenty_six_domains_match_source_and_all_allowed_patrons_confirm(self):
  self.assertEqual({row[0] for row in B.GRANTING_PATRONS.values()},
   {21,27,28,30,36,43,44,46,49,52,55,58,86,89,93,97,104,109,120,124,128,142,151,156,161,164})
  with (ROOT/'input/db/class-data.csv').open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
  for gift,(number,allowed) in B.GRANTING_PATRONS.items():
   self.assertEqual(tuple(x.strip() for x in rows[number-1][12].split(',')),allowed)
   for patron in allowed:
    with self.subTest(gift=gift,patron=patron):
     case=self.fixture();self.pending(case,gift,patron);record=self.confirm(case,gift)
     authority=record['patron_authority']
     self.assertEqual(authority['gift_source']['record_span'],[number,number])
     self.assertEqual(authority['granting_patron']['species'],patron)
     self.assertEqual(authority['qualification']['status'],'qualified')
     self.assertTrue(B.require(case.e,case.a,gift))

 def test_all_twenty_six_contradictions_reject_atomically_despite_generic_gm_permission(self):
  for gift,(_,allowed) in B.GRANTING_PATRONS.items():
   with self.subTest(gift=gift):
    case=self.fixture();self.pending(case,gift,'뮤' if '뮤' not in allowed else '라티아스')
    self.reject(case,lambda:self.confirm(case,gift),'granting patron contradicts')
    self.assertNotIn(gift,case.a.spec.get('_blessing_gift_approvals',{}))

 def test_all_twenty_six_unknown_histories_stay_explicit_without_inventing_illegality(self):
  for gift in B.GRANTING_PATRONS:
   with self.subTest(gift=gift):
    case=self.fixture();self.pending(case,gift);record=self.confirm(case,gift)
    authority=record['patron_authority']
    self.assertEqual(authority['granting_patron'],{'kind':'historical_unknown','value':None,'species':None})
    self.assertEqual(authority['qualification']['status'],'pending')
    self.assertTrue(B.require(case.e,case.a,gift))
    self.assertNotIn(gift,case.a.spec['gift_patrons'])

 def test_actual_actor_identity_uses_species_not_display_name_and_preserves_history(self):
  for species,name,valid in [('라티아스','뮤',True),('뮤','라티아스',False)]:
   with self.subTest(species=species):
    case=self.fixture();patron=Combatant(self.rules,build_pokemon(self.rules,species,30,name=name,moves=[],abilities=[]))
    case.e.gm.add_combatant(patron,pos=(10,10),side='party',reason='actual granting actor')
    self.pending(case,ROYAL,patron.entity_id)
    if not valid:self.reject(case,lambda:self.confirm(case,ROYAL),'granting patron contradicts');continue
    record=self.confirm(case,ROYAL);self.assertEqual(record['patron_authority']['granting_patron'],{'kind':'actor','value':patron.entity_id,'species':'라티아스'})
    case.a.spec['gift_patrons'][ROYAL]='뮤';patron.spec['species']='pokemon/뮤'
    self.assertTrue(B.require(case.e,case.a,ROYAL))
    self.assertEqual(case.a.spec['_blessing_gift_approvals'][ROYAL],record)

 def test_unregistered_historical_actor_id_is_unknown_not_an_illegal_species(self):
  case=self.fixture();self.pending(case,ROYAL,'pokemon/instance/past-grantor')
  record=self.confirm(case,ROYAL)
  fact=record['patron_authority']['granting_patron']
  self.assertEqual(fact,{'kind':'historical_unknown','value':'pokemon/instance/past-grantor','species':None})
  self.assertEqual(record['patron_authority']['qualification']['status'],'pending')
  self.assertTrue(B.require(case.e,case.a,ROYAL))

 def test_missingno_aspects_are_not_interchangeable(self):
  gifts=[gift for gift,(_,patrons) in B.GRANTING_PATRONS.items() if patrons[0].startswith('미싱노')]
  for gift in gifts:
   for patron in ('미싱노', '미싱노 (코즈믹 호러)', '미싱노 (타락한 창조주)', '미싱노 (네트워크 보안의 새로운 신)'):
    with self.subTest(gift=gift,patron=patron):
     case=self.fixture();self.pending(case,gift,patron)
     if patron in B.GRANTING_PATRONS[gift][1]:self.confirm(case,gift)
     else:self.reject(case,lambda:self.confirm(case,gift),'granting patron contradicts')

 def test_exact_scoped_waiver_can_override_one_patron_check_only(self):
  waiver={'source_id':ROYAL,'provider':'native','stage':'gift_confirmation','checks':['granting_patron'],'reason':'explicit alternate source-bound grant'}
  for field,value in [('source_id',DREAM),('provider','other'),('stage','acquisition'),('checks',['owned'])]:
   with self.subTest(field=field):
    case=self.fixture();self.pending(case,ROYAL,'뮤');wrong={**waiver,field:value}
    self.reject(case,lambda:self.confirm(case,ROYAL,{'waivers':[wrong]}),'granting patron contradicts|waiver may only')
  case=self.fixture();self.pending(case,ROYAL,'뮤');record=self.confirm(case,ROYAL,{'waivers':[waiver]})
  self.assertEqual(record['patron_authority']['qualification']['checks'][0]['state'],'waived')
  items.register_feats(case.e,case.a);case.e.apply_status(case.a,'헤롱헤롱',applied_by=case.t)
  self.assertNotIn('헤롱헤롱',case.a.conditions)

 def test_patron_receipt_source_and_identity_corruption_fail_before_native_immunity(self):
  for field,value in [('species','뮤'),('value','pokemon/forged'),('kind','invented')]:
   with self.subTest(field=field):
    case=self.fixture();self.pending(case,ROYAL,'라티아스');self.confirm(case,ROYAL)
    case.a.spec['_blessing_gift_approvals'][ROYAL]['patron_authority']['granting_patron'][field]=value
    self.reject(case,lambda:items.register_feats(case.e,case.a),'patron|evidence')
  case=self.fixture();self.pending(case,ROYAL,'라티아스');self.confirm(case,ROYAL)
  case.a.spec['_blessing_gift_approvals'][ROYAL]['patron_authority']['gift_source']['record_span']=[97,97]
  self.reject(case,lambda:B.require(case.e,case.a,ROYAL),'receipt or source changed')
  case.a.spec['_blessing_gift_approvals'][ROYAL]['actor_id']='trainer/another'
  self.reject(case,lambda:B.require(case.e,case.a,ROYAL),'GM permission')

 def test_royal_and_dream_immunities_survive_json_and_gm_restore(self):
  for gift,patron in [(ROYAL,'라티오스'),(DREAM,'다크라이')]:
   with self.subTest(gift=gift):
    case=self.fixture();self.pending(case,gift,patron);self.confirm(case,gift);items.register_feats(case.e,case.a)
    case.e.gm.snapshot('authority');case.a.spec['gift_patrons'].clear();case.e.gm.restore('authority',reason='restore actual authority')
    loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(case.e),ensure_ascii=False)))
    a=next(v for v in loaded.everyone if v.entity_id==case.a.entity_id);t=next(v for v in loaded.everyone if v.entity_id==case.t.entity_id)
    if gift==ROYAL:
     loaded.apply_status(a,'헤롱헤롱',applied_by=t);self.assertNotIn('헤롱헤롱',a.conditions)
    else:self.assertFalse(loaded.accuracy_check(t,a,self.rules.move('move/최면술'),fixed_roll=20)[0])

 def test_royal_and_dream_unapproved_contradictions_cannot_register_native_immunity(self):
  for gift in (ROYAL,DREAM):
   with self.subTest(gift=gift):
    case=self.fixture();self.pending(case,gift,'뮤')
    self.reject(case,lambda:self.confirm(case,gift),'granting patron contradicts')
    self.reject(case,lambda:items.register_feats(case.e,case.a),'GM permission')

 def test_legacy_patron_confirmation_preserves_old_acquisition_after_prerequisite_loss(self):
  for gift in ('gift/메이저-기프트-진실의-눈','gift/메이저-기프트-순수-호흡','gift/메이저-기프트-접속-시각화'):
   with self.subTest(gift=gift):
    case=self.fixture();self.pending(case,gift,B.GRANTING_PATRONS[gift][1][0]);self.confirm(case,gift)
    previous=case.a.spec['_blessing_gift_approvals'][gift];previous.pop('patron_authority');previous=deepcopy(previous)
    required=B.PREREQUISITES[gift][1];case.a.spec['gifts'].remove(required);case.a.spec['_blessing_gift_approvals'].pop(required)
    self.reject(case,lambda:B.require(case.e,case.a,gift),'legacy Gift')
    record=self.confirm(case,gift);self.assertEqual(record['previous_approval'],previous)
    self.assertEqual(record['acquisition'],previous['acquisition']);self.assertTrue(B.require(case.e,case.a,gift))

 def insight(self,role='계약자',values=None):
  case=self.fixture();case.own(B.ADVANCED.ANCIENT_WISDOM,'뮤',configuration={'role':'contractor'})
  case.own(INSIGHT,'뮤',{'role':role});case.fact(INSIGHT,deepcopy(VALUES if values is None else values),case.t)
  case.begin();return case

 def observe(self,case,selection=None):
  return OBSERVE.observe_blessing(case.e,case.a,INSIGHT,target=case.t,selection=selection)

 def next_turn(self,case):
  case.e.end_of_turn(case.a);case.e.end_round();case.begin()

 def test_confirmed_roles_control_redaction_swift_ap_and_second_use_scene_limit(self):
  for role in ('계약자','메시아'):
   with self.subTest(role=role):
    case=self.insight(role);ap=AP.available(case.a)
    value=self.observe(case,{'weakness':'빛'} if role=='계약자' else None)['values']
    self.assertEqual(value,{'weakness':'빛','aligned':True,'harms_patron_followers':False} if role=='계약자' else VALUES)
    self.assertEqual(AP.available(case.a),ap-(role=='계약자'));self.assertEqual(case.a.budget['swift'],0)
    self.next_turn(case);self.reject(case,lambda:self.observe(case,{'weakness':'빛'} if role=='계약자' else None),'frequency exhausted')
    case.e.end_of_turn(case.a);case.e.end_scene(case.e.everyone);case.begin()
    self.observe(case,{'weakness':'빛'} if role=='계약자' else None)

 def test_role_changes_both_directions_reject_before_revelation_or_payment(self):
  for role,other in [('계약자','메시아'),('메시아','계약자')]:
   with self.subTest(role=role):
    case=self.insight(role);case.a.spec['gift_choices'][INSIGHT]['role']=other
    self.reject(case,lambda:self.observe(case,{'weakness':'빛'}),'Insight acquisition role changed')

 def test_contractor_empty_facts_declined_selection_ap_shortage_and_action_failure_are_atomic(self):
  empty={**VALUES,'allegiance':'','weaknesses':[]}
  case=self.insight(values=empty);self.assertEqual(self.observe(case)['values'],{'weakness':None,'aligned':False,'harms_patron_followers':False})
  case=self.insight();self.reject(case,lambda:self.observe(case),'select one actual weakness')
  self.reject(case,lambda:self.observe(case,{'weakness':'invented'}),'select one actual weakness')
  AP.charge(case.a,AP.available(case.a),mode='spend')
  self.reject(case,lambda:self.observe(case,{'weakness':'빛'}),'AP unavailable')
  case=self.insight();import turn as TURN
  self.assertTrue(TURN.spend(case.e,case.a,'swift',INSIGHT));self.assertTrue(TURN.spend(case.e,case.a,'standard',INSIGHT))
  self.reject(case,lambda:self.observe(case,{'weakness':'빛'}),'action unavailable')

 def test_role_authority_source_or_configuration_corruption_rejects_before_payment(self):
  for field in ('source','configuration','cost_source','sha256'):
   with self.subTest(field=field):
    case=self.insight();record=case.a.spec['_blessing_gift_approvals'][INSIGHT]
    record['role_authority'][field]={} if field!='sha256' else 'forged'
    self.reject(case,lambda:self.observe(case,{'weakness':'빛'}),'role authority changed')

 def test_role_cost_and_scene_receipts_survive_json_gm_and_historical_prerequisite_loss(self):
  for role in ('계약자','메시아'):
   with self.subTest(role=role):
    case=self.insight(role);case.a.spec['gifts'].remove(B.ADVANCED.ANCIENT_WISDOM);case.a.spec['feats']=[]
    case.e.gm.snapshot('before');ap=AP.available(case.a);selection={'weakness':'빛'} if role=='계약자' else None
    self.observe(case,selection);case.e.gm.restore('before',reason='restore legitimate pre-use state')
    self.assertEqual(AP.available(case.a),ap);self.observe(case,selection)
    loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(case.e),ensure_ascii=False)))
    case.e=loaded;case.a=next(v for v in loaded.everyone if v.entity_id==case.a.entity_id);case.t=next(v for v in loaded.everyone if v.entity_id==case.t.entity_id)
    self.assertEqual(AP.available(case.a),ap-(role=='계약자'));self.next_turn(case)
    self.reject(case,lambda:self.observe(case,selection),'frequency exhausted')

 def test_legacy_role_requires_explicit_confirmation_without_inventing_past_costs(self):
  case=self.insight();record=case.a.spec['_blessing_gift_approvals'][INSIGHT];record.pop('role_authority');record.pop('configuration');old=deepcopy(record)
  case.a.spec['gifts'].remove(B.ADVANCED.ANCIENT_WISDOM);case.a.spec['feats']=[]
  self.reject(case,lambda:self.observe(case,{'weakness':'빛'}),'legacy confirmation')
  ap=AP.available(case.a);before=deepcopy(case.a.spec.get('frequency_state'))
  receipt=case.e.confirm_blessing_gift(case.a,INSIGHT,reason='GM explicitly declares the historical Contractor role',configuration={'role':'계약자'})
  self.assertEqual(receipt['previous_approval'],old);self.assertEqual(receipt['acquisition'],old['acquisition'])
  self.assertEqual(AP.available(case.a),ap);self.assertEqual(case.a.spec.get('frequency_state'),before)
  self.observe(case,{'weakness':'빛'});self.assertEqual(AP.available(case.a),ap-1)

 def region_case(self):
  case=self.fixture();case.own(REGION,'히드런');case.own(CLOUDS,'토네로스');return case

 def roll(self,case,skill='생존',context=None):
  return case.e.skill_roll(case.a,skill,skill_context=context)

 def test_mountain_weather_and_volcanic_perception_keep_independent_purpose(self):
  case=self.region_case();SURVIVALIST.observe_environment(case.e,case.a,terrains=['mountain'],light='normal',reason='observed actual mountain')
  result=self.roll(case,context={'purpose':'predict_weather_from_clouds','reason':'actual clouds'})
  self.assertEqual(result.modifier,6)
  for purpose in ('climb','distant_object'):
   self.assertEqual(self.roll(case,'통찰',{'purpose':purpose,'reason':'actual bounded purpose'}).modifier,3)
  # Mountain and volcanic may both hold; forest does not disprove volcanic.
  for terrains in (['mountain'],['forest']):
   SURVIVALIST.observe_environment(case.e,case.a,terrains=terrains,light='normal',reason='current observed terrain')
   self.assertEqual(self.roll(case,'통찰',{'purpose':'distant_object','reason':'far object','region':{'kind':'volcanic','reason':'actual volcanic district'}}).modifier,3)

 def test_other_unknown_and_unrelated_skills_do_not_gain_region_bonus(self):
  case=self.region_case();self.assertEqual(self.roll(case).modifier,0)
  self.assertEqual(self.roll(case,context={'purpose':'predict_weather_from_clouds','reason':'cloud observation'}).modifier,3)
  SURVIVALIST.observe_environment(case.e,case.a,terrains=['forest'],light='normal',reason='actual forest')
  self.assertEqual(self.roll(case).modifier,0)
  self.assertEqual(self.roll(case,context={'region':{'kind':'other','reason':'neither mountain nor volcanic'}}).modifier,0)
  self.assertEqual(self.roll(case,'매력',{'region':{'kind':'volcanic','reason':'actual volcanic area'}}).modifier,0)

 def test_explicit_unknown_malformed_and_contradictory_regions_reject_before_rng(self):
  case=self.region_case()
  for region in (None,{}, {'kind':[],'reason':'invalid kind'}, {'kind':'unknown','reason':'not observed'}, {'kind':'volcanic','reason':''}):
   with self.subTest(region=region):
    self.reject(case,lambda:self.roll(case,context={'region':region}),'region|reason')
  SURVIVALIST.observe_environment(case.e,case.a,terrains=['mountain'],light='normal',reason='current mountain cell')
  self.reject(case,lambda:self.roll(case,context={'region':{'kind':'other','reason':'contradiction'}}),'contradicts')

 def test_region_context_and_environment_keep_json_and_gm_restore(self):
  case=self.region_case();SURVIVALIST.observe_environment(case.e,case.a,terrains=['mountain'],light='normal',reason='real mountain')
  case.e.gm.snapshot('mountain');SURVIVALIST.observe_environment(case.e,case.a,terrains=['urban'],light='normal',reason='later city')
  case.e.gm.restore('mountain',reason='restore mountain observation')
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(case.e),ensure_ascii=False)))
  case.e=loaded;case.a=next(v for v in loaded.everyone if v.entity_id==case.a.entity_id)
  self.assertEqual(self.roll(case,context={'purpose':'predict_weather_from_clouds','reason':'weather on mountain'}).modifier,6)

 def test_region_is_stripped_for_sleep_permission_and_other_purpose_consumers(self):
  context={'purpose':'imminent_danger','reason':'approaching actual danger',
   'region':{'kind':'volcanic','reason':'observed volcanic district'}}
  self.assertEqual(B.ADVANCED.shared_context(context),{'purpose':'imminent_danger','reason':'approaching actual danger'})
  for gift in (B.SLEEP,B.ADVANCED.WATCHFUL_SLEEP):
   with self.subTest(gift=gift):
    case=self.fixture();case.a.spec['gifts'].append(gift);case.a.spec['gift_patrons'][gift]='지라치'
    case.e.confirm_blessing_gift(case.a,gift,reason='GM confirms the exact already acquired sleep permission')
    case.a.conditions.add('잠듦')
    case.e.skill_roll(case.a,'통찰',skill_context=context)
    self.assertIn('잠듦',case.a.conditions)
    self.reject(case,lambda:case.e.skill_roll(case.a,'통찰',skill_context={**context,'purpose':'climb'}),'sleep permits|Watchful Sleep permits')
  case=self.fixture();case.own(B.TRUTH,'레시라무')
  context={'purpose':'detect_lies','reason':'actual statement',
   'region':{'kind':'volcanic','reason':'observed volcanic district'}}
  self.assertEqual(self.roll(case,'직감',context).modifier,3)


if __name__=='__main__':unittest.main()
