"""Direct contracts for the eleven-row Blessing observation fanout."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv,hashlib,json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon,build_trainer
from engine import Rules,Engine,Combatant
from grid import Grid
import action_points as AP
import blessing_observations as B
import frequency as F
import perception_observe as OBSERVE
import state_codec as CODEC


class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def add(self,spec,pos=(0,0)):
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c,pos=pos,side='party',reason='actual state');return c
 def setUp(self):
  self.e=Engine(self.r,seed=1105);self.e.grid=Grid(40,20)
  gifts=['gift/고대의-지혜','gift/마이너-기프트-조심스런-수면',
   'gift/마이너-기프트-드림-마스터리','gift/마이너-기프트-사보타지-직감']+list(B.RULES)
  choices={
   'gift/위대한-존재의-통찰력':{'role':'메시아'},
   'gift/마이너-기프트-엘리멘탈-소울':{'patron':'프리져'},
   'gift/메이저-기프트-꿈의-전조':{'patron':'크레세리아'},
  }
  patrons={'gift/위대한-존재의-통찰력':'뮤','gift/고대의-지혜':'뮤',
   'gift/마이너-기프트-엘리멘탈-소울':'프리져','gift/마이너-기프트-재앙-탐지':'세레비',
   'gift/마이너-기프트-조심스런-수면':'지라치','gift/메이저-기프트-진실의-눈':'지라치',
   'gift/마이너-기프트-완벽한-타이밍':'디아루가','gift/마이너-기프트-공간인식':'펄기아',
   'gift/마이너-기프트-데스-센스':'기라티나','gift/마이너-기프트-드림-마스터리':'크레세리아',
   'gift/메이저-기프트-꿈의-전조':'크레세리아','gift/마이너-기프트-세계뱀의-포옹':'지가르데',
   'gift/마이너-기프트-이단자-탐지':'미싱노 (타락한 창조주)',
   'gift/마이너-기프트-사보타지-직감':'미싱노 (네트워크 보안의 새로운 신)',
   'gift/메이저-기프트-접속-시각화':'미싱노 (네트워크 보안의 새로운 신)'}
  spec=build_trainer(self.r,'observer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'직감':4},extra={'feats':['feat/나의-이름으로'],'gifts':[],'gift_choices':choices,'gift_patrons':patrons})
  self.a=self.add(spec,(2,2))
  self.t=self.add(build_pokemon(self.r,'잉어킹',10,moves=[],abilities=[],extra={'size':'Medium','height_m':0.9}),(5,6))
  self.a.spec['gifts']=gifts
  for gift in gifts:
   configuration={'role':'messiah'} if gift=='gift/고대의-지혜' else None
   self.e.confirm_blessing_gift(self.a,gift,reason='GM approved exact acquired Gift and actual patron',configuration=configuration)
  import items
  items.register_feats(self.e,self.a)
 def begin(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def fact(self,gift,value,target=None):
  return OBSERVE.record_blessing_fact(self.e,self.a,gift,value,reason='GM established actual campaign fact',target=target)
 def observe(self,gift,target=None,selection=None):
  return OBSERVE.observe_blessing(self.e,self.a,gift,target=target,selection=selection)

 def test_policy_exactly_pins_eleven_incomplete_source_rows(self):
  registry=json.loads((ROOT/'data/verification/category2-class-csv-clause-status.json').read_text(encoding='utf-8'))
  rows={row['id']:row for row in registry['rows']};self.assertEqual(len(B.catalog()),11)
  self.assertEqual(hashlib.sha256((ROOT/'input/db/class-data.csv').read_bytes()).hexdigest(),B._POLICY['source_sha256'])
  for policy in B.catalog():
   row=rows[policy['clause_id']]
   self.assertEqual(row['status'],'implemented');self.assertEqual(row['csv_record'],policy['record'])
   self.assertEqual((row['cell_sha256'],row['source_text'],row['name']),(policy['cell_sha256'],policy['source_text'],policy['name']))
   self.assertEqual(self.r._selected_rule(policy['gift']),policy['gift'])

 def test_four_passive_native_providers_reveal_only_finite_information(self):
  ice=self.add(build_pokemon(self.r,'꾸꾸리',10,moves=[],abilities=[]),(8,2))
  self.assertEqual(self.observe('gift/마이너-기프트-엘리멘탈-소울')['values'],{'presence':True})
  ice.pos=(20,2);self.assertEqual(self.observe('gift/마이너-기프트-엘리멘탈-소울')['values'],{'presence':False})
  self.e.advance_time(73)
  self.assertEqual(self.observe('gift/마이너-기프트-완벽한-타이밍',selection={'started_at':13})['values'],{'world_seconds':73,'stopwatch_seconds':60})
  self.t.pos=(5,6);spatial=self.observe('gift/마이너-기프트-공간인식',target=self.t)['values']
  self.assertEqual(spatial,{'distance_cm':500,'size':'Medium','dimensions_cm':{'height':90}})
  actual='gift/마이너-기프트-진실된-영웅'
  holder=self.add(build_trainer(self.r,'actual gifted trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'gifts':[actual],'gift_patrons':{actual:'레시라무'}}),(10,2))
  self.e.confirm_blessing_gift(holder,actual,reason='actual acquired non-MissingNo Gift')
  self.fact('gift/마이너-기프트-이단자-탐지',{'range_cm':1500,'basis':'actual current native GM sensing criterion'},holder)
  self.assertEqual(self.observe('gift/마이너-기프트-이단자-탐지')['values'],{'presence':True})
  missing='gift/마이너-기프트-외계인-얼굴'
  holder.spec.update(gifts=[missing],gift_patrons={missing:'미싱노 (코즈믹 호러)'})
  self.e.confirm_blessing_gift(holder,missing,reason='actual acquired MissingNo-only Gift')
  self.assertEqual(self.observe('gift/마이너-기프트-이단자-탐지')['values'],{'presence':False})

 def test_recorded_world_and_corpse_facts_keep_signature_window_and_ownership(self):
  disaster='gift/마이너-기프트-재앙-탐지';self.fact(disaster,{'disaster_kind':'홍수','when_seconds':3600})
  self.assertEqual(self.observe(disaster)['values'],{'disaster_kind':'홍수','when_seconds':3600})
  death='gift/마이너-기프트-데스-센스';self.t.spec['dead']=True;self.e.advance_time(7200)
  self.fact(death,{'died_at':0},self.t);self.assertEqual(self.observe(death,self.t)['values'],{'hours_since_death':2})
  self.e.advance_time(604801)
  with self.assertRaisesRegex(ValueError,'one-week'):self.observe(death,self.t)
  self.a.spec['gifts'].remove(disaster)
  with self.assertRaisesRegex(ValueError,'acquired'):self.observe(disaster)

 def test_active_target_knowledge_preserves_role_redaction_actions_ap_and_scene_quota(self):
  insight='gift/위대한-존재의-통찰력';truth='gift/메이저-기프트-진실의-눈'
  values={'allegiance':'청색단','weaknesses':['소금','빛'],'goals':'문 열기','motives':'구조','harms_patron_followers':False}
  self.fact(insight,values,self.t);self.begin();out=self.observe(insight,self.t)
  self.assertEqual(out['values'],values);self.assertEqual(self.a.budget['swift'],0)
  before=deepcopy((self.a.spec,self.a.budget))
  with self.assertRaisesRegex(ValueError,'frequency'):self.observe(insight,self.t)
  self.assertEqual((self.a.spec,self.a.budget),before)
  self.setUp();self.a.spec['gift_choices'][insight]={'role':'계약자'};self.fact(insight,values,self.t);self.begin()
  redacted=self.observe(insight,self.t,{'weakness':'빛'})['values']
  self.assertEqual(redacted,{'weakness':'빛','aligned':True,'harms_patron_followers':False});self.assertNotIn('allegiance',redacted)
  self.setUp();self.fact(truth,{'desire_altruistic':True},self.t);self.begin();ap=AP.available(self.a)
  self.assertEqual(self.observe(truth,self.t)['values'],{'desire_altruistic':True});self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(self.a.budget['standard'],0)

 def test_dream_serpent_and_network_share_atomic_lifecycle_contract(self):
  dream='gift/메이저-기프트-꿈의-전조';serpent='gift/마이너-기프트-세계뱀의-포옹';network='gift/메이저-기프트-접속-시각화'
  self.fact(dream,{'tone':'유리함','hint':'새벽의 빈 길'});ap=AP.available(self.a);out=self.observe(dream)
  self.assertEqual(out['values']['hint'],'새벽의 빈 길');self.assertEqual(AP.available(self.a),ap-2);self.assertIn('잠듦',self.a.conditions)
  self.setUp();self.fact(serpent,{'legendary_presence':True,'approximate_locations':['아래 동굴','북쪽 능선']})
  out=self.observe(serpent);self.assertNotIn('route',out['values'])
  with self.assertRaisesRegex(ValueError,'frequency'):self.observe(serpent)
  self.setUp();links=[{'from_id':'device/a','to_id':'device/b'}];self.fact(network,{'communication_links':links});self.begin()
  first=self.observe(network);self.assertEqual(first['lifetime']['expires_at'],300);self.assertEqual(self.a.budget['standard'],0)
  again=self.observe(network);self.assertEqual(again['status'],'active');self.assertEqual(again['values']['communication_links'],links)
  self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
  self.e.advance_time(300)
  with self.assertRaisesRegex(ValueError,'frequency'):self.observe(network)

 def test_failures_are_atomic_and_signed_state_round_trips(self):
  truth='gift/메이저-기프트-진실의-눈';self.fact(truth,{'desire_altruistic':True},self.t);self.begin()
  AP.charge(self.a,AP.available(self.a),mode='spend');before=deepcopy((self.a.spec,self.a.budget,self.a.conditions))
  with self.assertRaisesRegex(ValueError,'AP unavailable'):self.observe(truth,self.t)
  self.assertEqual((self.a.spec,self.a.budget,self.a.conditions),before)
  disaster='gift/마이너-기프트-재앙-탐지';self.fact(disaster,{'disaster_kind':'산사태','when_seconds':90})
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  owner=next(x for x in loaded.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(B.observe(loaded,owner,disaster)['values']['disaster_kind'],'산사태')
  owner.spec[B.FACTS][disaster]['value']['when_seconds']=91
  with self.assertRaisesRegex(ValueError,'signature'):B.observe(loaded,owner,disaster)

 def test_world_serpent_native_extended_action_scene_quota_and_authority_are_atomic(self):
  import turn as TURN
  gift='gift/마이너-기프트-세계뱀의-포옹'
  self.assertEqual((B.RULES[gift]['action'],B.RULES[gift]['frequency']),('extended','장면'))
  self.fact(gift,{'legendary_presence':True,'approximate_locations':['아래 동굴']})
  self.begin()
  before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'action unavailable'):self.observe(gift)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
  budget=dict(self.a.budget);ap=AP.available(self.a);history=list(getattr(self.a,'_action_history',[]))
  with patch.object(TURN,'spend',wraps=TURN.spend) as spend:
   out=self.observe(gift)
  self.assertEqual([call.args[2] for call in spend.call_args_list],['extended'])
  self.assertEqual(out['values'],{'legendary_presence':True,'approximate_locations':['아래 동굴']})
  self.assertEqual((self.a.budget,AP.available(self.a)),(budget,ap))
  self.assertEqual(self.a._action_history,history+['extended'])
  before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'frequency'):self.observe(gift)
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.a.spec['gifts'].remove(gift)
  before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'acquired'):self.observe(gift)
  self.assertEqual(CODEC.dump_engine(self.e),before)


if __name__=='__main__':unittest.main()

