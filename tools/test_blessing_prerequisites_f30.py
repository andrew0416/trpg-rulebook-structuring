"""Acquisition-time prerequisites through the existing native Gift consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon
import acquired_features as ACQUIRED
import blessing_skill_features as B
import class_passive_combat as PASSIVE
import items
import perception_observe as OBSERVE
import state_codec as CODEC
import tools.test_csv_blessings32 as FIXTURES

TRUTH='gift/메이저-기프트-진실의-눈'
DREAM='gift/메이저-기프트-꿈의-전조'
INSIGHT='gift/위대한-존재의-통찰력'
NETWORK='gift/메이저-기프트-접속-시각화'
BREATH='gift/메이저-기프트-순수-호흡'
RESILIENCE=PASSIVE.BLESSED_RESILIENCE
PATRONS={TRUTH:'지라치',DREAM:'크레세리아',INSIGHT:'뮤',
 NETWORK:'미싱노 (네트워크 보안의 새로운 신)',BREATH:'쉐이미',RESILIENCE:'스이쿤'}


class BlessingPrerequisiteTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')

 def fixture(self,gift=None):
  case=FIXTURES.SourceBoundaries('runTest');case.rules=self.rules;case.setUp()
  if gift is not None:
   case.a.spec['gifts'].append(gift);case.a.spec['gift_patrons'][gift]=PATRONS[gift]
   if gift==INSIGHT:case.a.spec['gift_choices'][gift]={'role':'계약자'}
   if gift==DREAM:case.a.spec['gift_choices'][gift]={'patron':'크레세리아'}
   if gift==RESILIENCE:
    patron=Combatant(self.rules,build_pokemon(self.rules,'스이쿤',30,moves=[],abilities=[]))
    case.e.gm.add_combatant(patron,pos=(10,7),side='party',reason='actual registered Water patron')
    case.a.spec['gift_patrons'][gift]=patron.entity_id
    case.a.spec['class_passive_choices']={gift:{'role':'messiah','patron_id':patron.entity_id,
     'eligible_types':['강철','물','불꽃','얼음'],'selected_types':['불꽃','물']}}
  return case

 def snapshot(self,case):
  return (deepcopy(case.a.spec),deepcopy(getattr(case.a,'budget',None)),
   deepcopy(getattr(case.a,'_action_history',[])),case.e.rng.getstate(),list(case.e.log_lines))

 def rejected(self,case,call,pattern='prerequisite|전제|permission|rank'):
  before=self.snapshot(case)
  with self.assertRaisesRegex(ValueError,pattern):call()
  self.assertEqual(self.snapshot(case),before)

 def confirm(self,case,gift):
  record=case.e.confirm_blessing_gift(case.a,gift,reason='GM confirms this actual source-bound acquisition')
  if gift==RESILIENCE:case.e.register_abilities(case.a)
  return record

 def prerequisite(self,case,gift,*,approved=True):
  required=B.PREREQUISITES[gift][1]
  case.a.spec['gifts'].append(required)
  case.a.spec['gift_patrons'][required]=PATRONS[gift]
  if approved and required in B.SOURCES:
   configuration={'role':'contractor'} if required==B.ADVANCED.ANCIENT_WISDOM else None
   case.e.confirm_blessing_gift(case.a,required,reason='GM approves the actual prerequisite acquisition',configuration=configuration)
  return required

 def consume(self,case,gift):
  if gift==BREATH:
   items.register_feats(case.e,case.a)
   return case.e.accuracy_check(case.t,case.a,case.rules.move('move/분노가루'),fixed_roll=20)[0]
  if gift==RESILIENCE:return PASSIVE.resistance_steps(case.e,case.a,'불꽃')
  value={TRUTH:{'desire_altruistic':True},
   INSIGHT:{'allegiance':'','weaknesses':[],'goals':'구조','motives':'연민','harms_patron_followers':False},
   DREAM:{'tone':'유리함','hint':'다가올 길'},
   NETWORK:{'communication_links':[{'from_id':'device/a','to_id':'device/b'}]}}[gift]
  target=case.t if gift in (TRUTH,INSIGHT) else None
  case.fact(gift,value,target)
  if gift!=DREAM:case.begin()
  return OBSERVE.observe_blessing(case.e,case.a,gift,target=target)['values']

 def missing(self,gift):
  case=self.fixture(gift)
  self.rejected(case,lambda:self.confirm(case,gift))
  self.assertNotIn(gift,case.a.spec.get('_blessing_gift_approvals',{}))

 def test_truth_eye_without_watchful_sleep_is_not_usable(self):self.missing(TRUTH)
 def test_dream_omen_without_dream_mastery_is_not_usable(self):self.missing(DREAM)
 def test_insight_without_ancient_wisdom_is_not_usable(self):self.missing(INSIGHT)
 def test_network_without_sabotage_intuition_is_not_usable(self):self.missing(NETWORK)
 def test_pure_breathing_without_plant_intuition_does_not_grant_immunity(self):self.missing(BREATH)
 def test_blessed_resilience_without_blessed_power_does_not_grant_resistance(self):self.missing(RESILIENCE)

 def missing_rank(self,gift):
  case=self.fixture();case.a.spec['feats']=[]
  case.a.spec['gifts'].append(gift)
  configuration={'role':'messiah',**({'category':'mental'} if gift==B.ADVANCED.PARAGON else {})}
  self.rejected(case,lambda:case.e.confirm_blessing_gift(case.a,gift,reason='GM cannot replace the actual rank prerequisite',configuration=configuration))

 def test_ancient_wisdom_messiah_requires_rank_one(self):self.missing_rank(B.ADVANCED.ANCIENT_WISDOM)
 def test_paragon_messiah_requires_rank_one(self):self.missing_rank(B.ADVANCED.PARAGON)

 def test_all_six_native_consumers_keep_acquisition_facts_after_prerequisite_loss_and_codec(self):
  expected={TRUTH:{'desire_altruistic':True},INSIGHT:{'weakness':None,'aligned':False,'harms_patron_followers':False},
   DREAM:{'tone':'유리함','hint':'다가올 길'},NETWORK:{'communication_links':[{'from_id':'device/a','to_id':'device/b'}]},
   BREATH:False,RESILIENCE:1}
  for gift in B.PREREQUISITES:
   with self.subTest(gift=gift):
    case=self.fixture(gift);required=self.prerequisite(case,gift)
    record=self.confirm(case,gift)
    self.assertEqual(record['acquisition']['required'],required)
    self.assertEqual(record['acquisition']['qualification']['status'],'qualified')
    case.a.spec['gifts'].remove(required)
    case.a.spec.get('_blessing_gift_approvals',{}).pop(required,None)
    case.a.spec['feats']=[]
    if gift==BREATH:items.register_feats(case.e,case.a)
    loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(case.e),ensure_ascii=False)))
    case.e=loaded;case.a=next(x for x in loaded.everyone if x.entity_id==case.a.entity_id)
    case.t=next(x for x in loaded.everyone if x.entity_id==case.t.entity_id)
    self.assertEqual(case.a.spec['_blessing_gift_approvals'][gift],record)
    self.assertEqual(self.consume(case,gift),expected[gift])
    case.a.spec['gifts'].remove(gift)
    self.assertFalse(B.approval(case.a,gift))

 def test_supported_prerequisites_need_their_own_approval(self):
  for gift in (INSIGHT,TRUTH,DREAM,NETWORK,BREATH):
   with self.subTest(gift=gift):
    case=self.fixture(gift);self.prerequisite(case,gift,approved=False)
    self.rejected(case,lambda:self.confirm(case,gift))

 def test_blessed_power_requires_csv_gift_and_preserves_bare_alias_and_duplicate_checks(self):
  case=self.fixture(RESILIENCE)
  case.a.spec.setdefault('feats',[]).append('feat/축복받은-힘')
  self.rejected(case,lambda:self.confirm(case,RESILIENCE))
  case.a.spec['gifts'].append('축복받은 힘')
  record=self.confirm(case,RESILIENCE)
  self.assertEqual(record['acquisition']['required'],'gift/축복받은-힘')
  self.assertEqual(record['acquisition']['source']['file'],'db/class-data.csv')
  self.assertEqual(record['acquisition']['source']['record_span'],[7,7])
  self.assertEqual(PASSIVE.resistance_steps(case.e,case.a,'불꽃'),1)
  duplicate=self.fixture(RESILIENCE)
  duplicate.a.spec['gifts']+=['gift/축복받은-힘','축복받은 힘']
  self.rejected(duplicate,lambda:self.confirm(duplicate,RESILIENCE),'duplicate')

 def test_real_rank_and_signer_routes_preserve_role_and_do_not_become_live_requirements(self):
  for gift in B.RANK_ONE:
   for role in ('messiah','contractor'):
    with self.subTest(gift=gift,role=role):
     case=self.fixture();case.a.spec['gifts']=[gift]
     required=B.IN_MY_NAME if role=='messiah' else B.SIGNER
     case.a.spec['feats']=[required]
     configuration={'role':role,**({'category':'mental'} if gift==B.ADVANCED.PARAGON else {})}
     if role=='messiah':case.a.spec['feat_ranks']={required:2}
     record=case.e.confirm_blessing_gift(case.a,gift,reason='actual acquired role-specific prerequisite',configuration=configuration)
     self.assertEqual(record['acquisition']['required'],required)
     self.assertEqual(record['acquisition']['rank'],2 if role=='messiah' else None)
     case.a.spec['feats']=[]
     self.assertTrue(B.approval(case.a,gift))
     case.a.spec[B.ADVANCED.CONFIGURATION][gift]['values']['role']='contractor' if role=='messiah' else 'messiah'
     self.rejected(case,lambda:B.approval(case.a,gift),'snapshot changed|prerequisite rank')
  for rank in (0,True,5):
   with self.subTest(invalid_rank=rank):
    case=self.fixture();case.a.spec['feats']=[B.IN_MY_NAME];case.a.spec['feat_ranks']={B.IN_MY_NAME:rank}
    case.a.spec['gifts']=[B.ADVANCED.ANCIENT_WISDOM]
    self.rejected(case,lambda:case.e.confirm_blessing_gift(case.a,B.ADVANCED.ANCIENT_WISDOM,reason='invalid actual rank',configuration={'role':'messiah'}),'rank')

 def test_contractor_uses_common_selected_feature_ownership_not_role_tags(self):
  case=self.fixture();case.a.spec.update(feats=[],gifts=[B.ADVANCED.ANCIENT_WISDOM],role='contractor',tags=['계약자'])
  self.assertEqual(ACQUIRED.owned_rule_count(case.a,B.SIGNER),0)
  confirm=lambda:case.e.confirm_blessing_gift(case.a,B.ADVANCED.ANCIENT_WISDOM,reason='actual contractor feature required',configuration={'role':'contractor'})
  self.rejected(case,confirm)
  case.a.spec['feats']=[B.SIGNER,B.SIGNER]
  self.assertEqual(ACQUIRED.owned_rule_count(case.a,B.SIGNER),2)
  self.rejected(case,confirm)
  case.a.spec['feats']=[B.SIGNER]
  self.assertEqual(ACQUIRED.owned_rule_count(case.a,B.SIGNER),1)
  confirm()

 def test_snapshot_corruption_and_excluded_sources_are_rejected_without_state_change(self):
  case=self.fixture(TRUTH);required=self.prerequisite(case,TRUTH);self.confirm(case,TRUTH)
  record=case.a.spec['_blessing_gift_approvals'][TRUTH]
  original=deepcopy(record['acquisition'])
  for field,value in (('count',True),('required','feat/축복받은-힘'),('clause_id','wrong'),('source',{}),('approved',False)):
   with self.subTest(field=field):
    record['acquisition']=deepcopy(original);record['acquisition'][field]=value
    self.rejected(case,lambda:B.require(case.e,case.a,TRUTH),'snapshot changed|prerequisite')
  record['acquisition']=original
  old=self.rules.ruleset
  from ruleset import RuleFilter
  try:
   self.rules.ruleset=RuleFilter({'sources':['core','errata','fantasy','blessings'],'exclude_units':[required]})
   self.rules._apply_ruleset()
   self.rejected(case,lambda:B.require(case.e,case.a,TRUTH),'excluded|Excluded|적용|source')
  finally:self.rules.ruleset=old;self.rules._apply_ruleset()

 def test_legacy_approval_requires_explicit_current_confirmation_and_keeps_old_receipt(self):
  case=self.fixture(TRUTH);required=self.prerequisite(case,TRUTH);self.confirm(case,TRUTH)
  old=case.a.spec['_blessing_gift_approvals'][TRUTH];old.pop('acquisition');old=deepcopy(old)
  self.rejected(case,lambda:B.approval(case.a,TRUTH))
  case.a.spec['gifts'].remove(required)
  self.rejected(case,lambda:self.confirm(case,TRUTH))
  case.a.spec['gifts'].append(required)
  corrected=self.confirm(case,TRUTH)
  self.assertEqual(corrected['previous_approval'],old)
  self.assertTrue(B.approval(case.a,TRUTH))
  self.rejected(case,lambda:self.confirm(case,TRUTH),'already recorded')

 def test_legacy_rank_confirmation_does_not_reselect_permanent_configuration(self):
  case=self.fixture();gift=B.ADVANCED.PARAGON
  case.a.spec['gifts']=[gift];case.a.spec['feats']=[B.IN_MY_NAME]
  configuration={'role':'messiah','category':'mental'}
  confirm=lambda config:case.e.confirm_blessing_gift(case.a,gift,reason='explicit current acquisition qualification',configuration=config)
  confirm(configuration);case.a.spec['_blessing_gift_approvals'][gift].pop('acquisition')
  self.rejected(case,lambda:confirm({'role':'messiah','category':'spirit'}),'preserved')
  confirm(configuration)
  self.assertEqual(case.e.skill_roll(case.a,'기술학',fixed=[2,2]).modifier,2)
  with self.subTest(gift=RESILIENCE):
   case=self.fixture(RESILIENCE);self.prerequisite(case,RESILIENCE)
   self.confirm(case,RESILIENCE)
   old=case.a.spec['_blessing_gift_approvals'][RESILIENCE];old.pop('acquisition');old=deepcopy(old)
   configuration=deepcopy(old['configuration'])
   changed={**configuration,'selected_types':['강철','얼음']}
   self.rejected(case,lambda:case.e.confirm_blessing_gift(case.a,RESILIENCE,reason='legacy selection cannot be changed',configuration=changed),'preserved')
   corrected=case.e.confirm_blessing_gift(case.a,RESILIENCE,reason='preserve the existing selection',configuration=configuration)
   self.assertEqual(corrected['previous_approval'],old)
   self.assertEqual(corrected['configuration'],configuration)
   self.assertEqual(case.a.spec['class_passive_choices'][RESILIENCE],configuration)
   self.assertEqual(PASSIVE.resistance_steps(case.e,case.a,'불꽃'),1)


if __name__=='__main__':unittest.main()
