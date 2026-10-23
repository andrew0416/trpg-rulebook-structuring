"""Observable actual mechanical repair, native resources, periods and providers."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_special_entities as _fixture_test_category2_special_entities
from engine import Engine,Rules
from state_codec import dump_engine,load_engine,StateCodecError
import special_entities as S,world_entities as W,repair_restore as REPAIR,crafting_recipes as Q

class RepairTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.poly=Rules(str(ROOT),ruleset='polygon')
 trainer=_fixture_test_category2_special_entities.SpecialTests.trainer
 bot=_fixture_test_category2_special_entities.SpecialTests.bot
 vehicle=_fixture_test_category2_special_entities.SpecialTests.vehicle
 def setUp(self):
  self.e=Engine(self.poly,27);self.a=self.trainer(self.poly);self.a.spec.update(money=500,crafting_scrap={'기계':40,'차량':40});self.a.spec['skills']['기술학']=4;self.e.everyone=self.e.gm.everyone=[self.a]
  row=self.bot();row.update(hp=20,injuries=4);S.observe(self.e,row,reason='actual damaged machine');self.target=self.e._physical_objects['bot']
 def policy(self,index=0):return json.loads((ROOT/'data/examples/repair-restore.json').read_text(encoding='utf8'))[index]
 def snap(self):return dump_engine(self.e)
 def restore(self,value=None,target='bot',request='repair/1',**options):
  return self.e.restore_object(self.a,target,value or self.policy(),request_id=request,reason='actual reviewed repair procedure',**options)
 def vehicle_ready(self):
  row=self.vehicle();row.update(hp=30,breaches=0,patched_breaches=0);S.observe(self.e,row,reason='actual damaged vehicle');return self.e._physical_objects['vehicle']
 def part(self,module='repair_nanites',uid='nanites',choice=None):
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual installed repair provider')
  row=deepcopy(self.target);row['components'].append({'instance_id':uid,'complexity':2,'source':'feat/엔지니어','module_id':module,'choice':choice});row['complexity']+=2;S.observe(self.e,row,reason='actual installed module');return uid
 def module_event(self,uid='event/1',event='breather'):
  return self.e.observe_machine_recovery(self.a,'bot','ability/재생력',event,event_id=uid,reason='GM observed this actual machine taking a breather')
 def regenerate(self,event_id='event/1',request='regenerate/1',**options):
  return self.e.regenerate_machine(self.a,'bot',component_id='nanites',event='breather',event_id=event_id,request_id=request,reason='actual sourced module recovery',**options)
 def test_actual_repair_consumes_cost_and_completed_period_with_native_injury_cap(self):
  physical=self.a.hp;out=self.restore(inputs={'parts':{'option':0,'scrap_value':10}})
  self.assertEqual((self.target['hp'],self.target['injuries']),(30,3));self.assertEqual(self.a.spec['money'],490);self.assertEqual(self.a.spec['crafting_scrap']['기계'],30);self.assertEqual(self.e.elapsed_seconds,60);self.assertEqual(self.a.hp,physical);self.assertEqual(self.e.activity_job_status(out['job_id'])['status'],'complete')
  self.assertEqual([x['applied'] for x in out['restored']],[10,1]);before=self.snap();self.assertEqual(self.restore(inputs={'parts':{'option':0,'scrap_value':10}}),out);self.assertEqual(before,self.snap())
 def test_actual_center_period_removes_at_most_three_and_honors_smaller_declared_limit(self):
  self.a.spec['crafting_location']={'region':'pokemon_center','source':'gm/observed-service','reason':'actual center repair service'};value=self.policy();out=self.restore(value);self.assertEqual(out['restored'][1]['applied'],3);self.assertEqual(self.target['injuries'],1)
  self.target['injuries']=5;value['effects'][1]['maximum']=2;out=self.restore(value,request='repair/2');self.assertEqual(out['restored'][1]['applied'],2);self.assertEqual(self.target['injuries'],3)
 def test_native_vehicle_cost_formula_uses_actual_money_and_typed_scrap(self):
  vehicle=self.vehicle_ready();out=self.e.repair_vehicle(self.a,'vehicle',cost=10,seconds=90,request_id='vehicle/1',accessible=True,reason='actual 90 second repair observation',inputs={'repair':{'option':0,'scrap_value':4}})
  self.assertEqual(vehicle['hp'],50);self.assertEqual(self.e.elapsed_seconds,90);self.assertEqual(self.a.spec['money'],494);self.assertEqual(self.a.spec['crafting_scrap']['차량'],36);self.assertEqual(out['restored'][0]['requested'],20)
  out=self.e.repair_vehicle(self.a,'vehicle',cost=9,seconds=30,request_id='vehicle/2',accessible=True,reason='actual later repair');self.assertEqual(vehicle['hp'],60);self.assertEqual(out['restored'][0]['applied'],10);self.assertEqual(self.a.spec['money'],485)
 def test_actual_skill_formula_uses_native_roll_action_and_failed_check_restores_nothing(self):
  vehicle=self.vehicle_ready();self.e.begin_encounter([self.a]);self.e.start_round([self.a]);self.e.start_of_turn(self.a);value=self.policy(2);out=self.restore(value,target='vehicle',roll_options={'fixed':[4]*4});self.assertEqual(out['check']['total'],16);self.assertEqual(vehicle['hp'],46);self.assertEqual(self.a.budget['standard'],0)
  self.e.end_of_turn(self.a);self.e.start_round([self.a]);self.e.start_of_turn(self.a);out=self.restore(value,target='vehicle',request='failed',roll_options={'fixed':[1]*4});self.assertFalse(out['passed']);self.assertEqual(vehicle['hp'],46);self.assertEqual(self.a.budget['standard'],0)
 def test_missing_money_tool_skill_or_damage_rejects_without_work_or_payment(self):
  self.a.spec['money']=0;self.a.spec['crafting_scrap']['기계']=0;before=self.snap()
  with self.assertRaisesRegex(ValueError,'insufficient'):self.restore()
  self.assertEqual(before,self.snap());self.a.spec['money']=500;self.a.spec['skills']['기술학']=1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'qualification'):self.restore()
  self.assertEqual(before,self.snap());self.a.spec['skills']['기술학']=4;self.target.update(hp=40,injuries=0);before=self.snap()
  with self.assertRaisesRegex(ValueError,'actual damage'):self.restore()
  self.assertEqual(before,self.snap())
 def test_actual_disabled_tool_cannot_satisfy_repair_requirement(self):
  tool='item/몬스터볼-공구함';W.register_object(self.e,'tool',kind='item_instance',item_rule_id=tool,owner_id=self.a.entity_id,location={'kind':'unknown'},reason='actual tool');self.a.spec['accessible_equipment']=['tool'];self.e._physical_objects['tool']['disabled']=True
  value=self.policy();value['requirements'].append({'kind':'tool','item_id':tool,'names':['몬스터볼 공구함'],'instance_id':'tool'});before=self.snap()
  with self.assertRaisesRegex(ValueError,'qualification'):self.restore(value)
  self.assertEqual(before,self.snap());self.e._physical_objects['tool']['disabled']=False;self.assertTrue(self.restore(value)['passed'])
 def test_wrong_identity_owner_kind_or_destroyed_machine_does_not_resurrect(self):
  before=self.snap()
  with self.assertRaises(ValueError):self.e.restore_object(copy(self.a),'bot',self.policy(),request_id='copy',reason='copied actor')
  with self.assertRaisesRegex(ValueError,'kind'):self.restore(self.policy(1))
  self.assertEqual(before,self.snap());self.target['owner_id']=None;before=self.snap()
  with self.assertRaisesRegex(ValueError,'owner'):self.restore()
  self.assertEqual(before,self.snap());self.target['owner_id']=self.a.entity_id;self.target['destroyed']=True;before=self.snap()
  with self.assertRaisesRegex(ValueError,'destroyed'):self.restore()
  self.assertEqual(before,self.snap())
 def test_organic_healing_requires_actual_current_dubious_disc_provider(self):
  value=self.policy();value.update(method='organic',materials=[],action='free',seconds=0);value['effects']=value['effects'][:1];before=self.snap()
  with self.assertRaisesRegex(ValueError,'organic'):self.restore(value)
  self.assertEqual(before,self.snap());self.part('sympathetic_drive','disc',{'item':'dubious_disc','mode':'trait'});self.assertTrue(self.restore(value)['passed']);self.assertEqual(self.target['hp'],30)
  row=deepcopy(self.target);row.update(components=[],complexity=0);S.observe(self.e,row,reason='actual healing provider removed')
  with self.assertRaisesRegex(ValueError,'organic'):self.restore(value,request='after-removal')
 def test_module_fraction_uses_actual_installed_provider_trigger_and_daily_target_quota(self):
  self.part();self.target['hp']=10;before=self.snap()
  with self.assertRaisesRegex(ValueError,'trigger'):self.regenerate()
  self.assertEqual(before,self.snap());self.module_event();out=self.regenerate();self.assertEqual(self.target['hp'],23);self.assertEqual(out['restored'][0]['requested'],13);before=self.snap();self.assertEqual(self.regenerate(),out);self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'trigger'):self.regenerate(request='same-event-again')
  self.target['hp']=5;self.module_event('event/2');self.regenerate('event/2',request='regenerate/2');self.assertEqual(self.target['hp'],18);self.module_event('event/3');before=self.snap()
  with self.assertRaisesRegex(ValueError,'quota'):self.regenerate('event/3',request='regenerate/3')
  self.assertEqual(before,self.snap())
 def test_module_removal_disabled_provider_or_false_event_blocks_regeneration(self):
  self.part();self.module_event();self.e._physical_objects['nanites']['disabled']=True;before=self.snap()
  with self.assertRaisesRegex(ValueError,'disabled'):self.regenerate()
  self.assertEqual(before,self.snap());self.e._physical_objects['nanites']['disabled']=False;self.e.advance_time(1);before=self.snap()
  with self.assertRaisesRegex(ValueError,'trigger'):self.regenerate()
  self.assertEqual(before,self.snap());row=deepcopy(self.target);row.update(components=[],complexity=0);S.observe(self.e,row,reason='actual module removed')
  with self.assertRaisesRegex(ValueError,'installed'):self.regenerate()
 def test_declaration_renaming_cannot_increase_actual_module_daily_limit(self):
  self.part();self.module_event();self.regenerate();self.module_event('event/2');value=REPAIR.regeneration_policy('nanites','breather');value.update(id='new-name',daily_limit=3);before=self.snap()
  with self.assertRaisesRegex(ValueError,'quota cannot change'):self.restore(value,event_id='event/2',request='renamed')
  self.assertEqual(before,self.snap())
 def test_actual_disabled_item_repairs_same_identity_without_new_inventory(self):
  rule=next(iter(self.poly.items_mech));W.register_object(self.e,'item',kind='item_instance',item_rule_id=rule,owner_id=self.a.entity_id,location={'kind':'unknown'},reason='actual damaged item');target=self.e._physical_objects['item'];target['disabled']=True;old=(target['id'],target['item_rule_id'],target['owner_id']);out=self.restore(self.policy(1),target='item')
  self.assertEqual(old,(target['id'],target['item_rule_id'],target['owner_id']));self.assertFalse(target['disabled']);self.assertEqual(out['restored'][0]['applied'],1);self.assertEqual(self.a.spec.get('items',{}),{})
 def test_repair_period_and_actual_targets_survive_json_and_gm_restore(self):
  out=self.restore();saved=self.snap();loaded=load_engine(self.poly,json.loads(json.dumps(saved,ensure_ascii=False)));self.assertEqual(loaded._physical_objects['bot']['hp'],30);self.assertEqual(loaded.activity_job_status(out['job_id'])['progress_seconds'],60)
  self.e.gm.snapshot('repair');self.restore(request='repair/2');self.e.gm.restore('repair',reason='restore actual repair and its cost/time');self.assertEqual(self.e._physical_objects['bot']['hp'],30);self.assertEqual(self.e.elapsed_seconds,60);self.assertEqual(self.a.spec['money'],480)
 def test_late_time_payment_or_restoration_failure_rolls_back_work_money_rng_and_object(self):
  before=self.snap()
  with patch.object(Q,'pay_materials',side_effect=RuntimeError('late payment')):
   with self.assertRaises(RuntimeError):self.restore()
  self.assertEqual(before,self.snap())
  with patch.object(S,'validate_record',side_effect=lambda *args,**kw: (_ for _ in ()).throw(RuntimeError('late restored state')) if args[1].get('hp')==30 else self.original_validate(*args,**kw)):
   with self.assertRaises(RuntimeError):self.restore()
  self.assertEqual(before,self.snap())
 def test_tampered_completed_repair_evidence_rejects_world_json_and_gm(self):
  self.restore();getattr(self.e,REPAIR.FIELD)['requests']['repair/1']['result']['seconds']=0;self.assertFalse(W.validate_world(self.e)['valid'])
  with self.assertRaises(StateCodecError):self.snap()
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad')
 original_validate=staticmethod(S.validate_record)

if __name__=='__main__':unittest.main()
