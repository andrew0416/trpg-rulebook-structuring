"""Optional source exceptions retain their own occupancy and application history."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import move_state as M
import state_grants as G
import state_codec as C
import items as I

class OptionalMoveSlotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def setUp(self):self.e=Engine(self.r,seed=823)
 def add(self,**kw):
  c=Combatant(self.r,build_pokemon(self.r,'브케인',5,moves=[],**kw));self.e.gm.add_combatant(c,pos=(0,0),side='party',reason='actual current Pokemon');return c
 def vm(self,c,name='냉동빔',application_id='actual-vm-1',**kw):
  return M.observe_vm_learning(self.e,c,name,application_id=application_id,reason='GM observes completed facility application',**kw)
 def test_vm_two_slots_and_only_one_other_taught_default(self):
  c=self.add();self.vm(c)
  view=M.describe(self.r,c.spec);self.assertEqual((view['slot_count'],view['taught_count'],view['vitamin_state']['reserved']),(2,2,1))
  M.observe_learning(self.e,c,'10만볼트',method='tutor',source='feat/기술-가르침',paid_tp=2,reason='observed actual tutoring')
  before=deepcopy(c.spec)
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):M.observe_learning(self.e,c,'열풍',method='tutor',source='feat/기술-가르침',paid_tp=2,reason='observed actual tutoring')
  self.assertEqual(c.spec,before)
  with self.assertRaisesRegex(ValueError,'only one VM'):self.vm(c,'화염방사',application_id='actual-vm-2')
  self.assertEqual(c.spec,before)
 def test_vm_default_five_known_and_current_source_exceptions(self):
  c=self.add(abilities=['기부자']);self.vm(c)
  for mid in ('화염방사','열풍','10만볼트','사이코키네시스'):M.observe_learning(self.e,c,mid,method='tutor',source='feat/기술-가르침',paid_tp=2,reason='observed actual tutoring')
  self.assertEqual((len(M.describe(self.r,c.spec)['known']),M.describe(self.r,c.spec)['slot_count']),(5,6))
  before=deepcopy(c.spec)
  with self.assertRaisesRegex(ValueError,'capacity'):M.observe_learning(self.e,c,'물의파동',method='tutor',source='feat/기술-가르침',paid_tp=2,reason='observed actual tutoring')
  self.assertEqual(c.spec,before)
  with self.assertRaisesRegex(ValueError,'only one VM'):self.vm(c,'물의파동',application_id='actual-vm-2')
 def test_vm_reservation_dose_history_forgetting_independent_source_and_restore(self):
  c=self.add();c.spec['vitamins']=['타우린']*4;self.vm(c)
  self.assertEqual(M.vitamin_state(self.r,c.spec)['occupied'],5)
  G.grant_moves(c,['냉동빔'],'independent-free','feature')
  self.e.gm.set_move(c,'move/냉동빔',add=False,reason='actual explicit VM move forgotten')
  self.assertIn('move/냉동빔',c.moves);self.assertEqual(M.vitamin_state(self.r,c.spec)['occupied'],4)
  self.assertEqual(M.describe(self.r,c.spec)['classifications']['move/냉동빔'],'granted')
  with self.assertRaisesRegex(ValueError,'already been observed'):self.vm(c,application_id='actual-vm-1')
  self.vm(c,application_id='actual-vm-2')
  restored=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False))).everyone[0]
  self.assertEqual(M.describe(self.r,restored.spec)['slot_count'],2)
  self.assertEqual(restored.spec['vitamins'],['타우린']*4)
  self.assertEqual(M.vitamin_state(self.r,restored.spec)['occupied'],5)
 def test_vm_foiling_changes_only_total_channel_and_lifelong_adds_one_taught_slot(self):
  trainer=Combatant(self.r,build_trainer(self.r,'Actual Grass Mentor',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},extra={'feats':[M.FOILING,M.LIFELONG]}));self.e.gm.add_combatant(trainer,pos=(0,0),side='party',reason='actual selected sources')
  c=self.add(extra={'trainer_id':trainer.entity_id});self.vm(c,'버섯포자')
  M.select_foiling(self.e,trainer,c,'버섯포자',reason='known Grass Status move chosen without learning-route restriction')
  M.register_passive_feature(self.e,trainer,M.LIFELONG,targets=[c])
  view=M.describe(self.r,c.spec);self.assertEqual((view['slot_count'],view['taught_count'],view['taught'],view['vitamin_state']['reserved']),(0,2,4,1))
  for name in ('화염방사','냉동빔'):M.observe_learning(self.e,c,name,method='tutor',source='feat/기술-가르침',paid_tp=2,reason='actual learned Tutor move')
  self.assertEqual(M.describe(self.r,c.spec)['taught_count'],4)
  before=deepcopy(c.spec)
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):M.observe_learning(self.e,c,'열풍',method='tutor',source='feat/기술-가르침',paid_tp=2,reason='overfull taught channel')
  self.assertEqual(c.spec,before)
  G.revoke(c,'feature:'+trainer.entity_id+':'+M.FOILING,engine=self.e)
  self.assertEqual(M.describe(self.r,c.spec)['slot_count'],4)
 def test_vm_fifth_vitamin_prevents_application_and_native_vitamin_consumption(self):
  c=self.add();c.spec['vitamins']=['타우린']*5;before=deepcopy(c.spec)
  with self.assertRaisesRegex(ValueError,'Vitamin'):self.vm(c)
  self.assertEqual(c.spec,before)
  c.spec['vitamins'].pop();self.vm(c)
  trainer=Combatant(self.r,build_trainer(self.r,name='Actual trainer',level=1,stats={'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},extra={'items':{'타우린':1}}));self.e.gm.add_combatant(trainer,pos=(0,1),side='party',reason='item owner')
  before_attack=c.spec['stats']['atk'];I.use_item(self.e,trainer,'타우린',c)
  self.assertEqual(c.spec['stats']['atk'],before_attack);self.assertEqual(len(c.spec['vitamins']),4)

class SmartVisionMoveSlotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='polygon')
 def setUp(self):
  import special_entities as S,world_entities as W
  self.e=Engine(self.r,seed=422)
  self.a=Combatant(self.r,build_trainer(self.r,'Upgrader',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},extra={'feats':['feat/프로토-디자인']}))
  self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual source owner')
  mids=[self.r.move_id(n) for n in ('몸통박치기','울음소리','덩굴채찍','씨뿌리기','잎날가르기','성장')]
  self.p=Combatant(self.r,build_pokemon(self.r,'이상해씨',50,moves=mids,abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.e.gm.add_combatant(self.p,pos=(0,1),side='party',reason='actual augmented Pokemon')
  W.register_object(self.e,'actual-eye',location={'kind':'unknown'},reason='actual physical implant')
  self.row=dict(id='augmentation/actual',kind='augmentation_set',location={'kind':'unknown'},actor_id=self.p.entity_id,body_slots=['eyes','body','skin','limbs'],installations=[{'instance_id':'actual-eye','augmentation_id':'smart_vision'}],allow_added_parts=False,essence_enabled=False)
  S.observe(self.e,self.row,reason='actual installed Smart Vision')
 def upgrade(self,identity):
  import augmentation_moves as A
  return A.observe_upgrade(self.e,self.a,self.p,augmentation_set_id=self.row['id'],instance_id='actual-eye',application_id=identity,active=True,reason='observed completed Experimental Designs choice')
 def test_smart_vision_seventh_without_slot_disable_restore_and_lifetime_cap(self):
  import special_entities as S
  from encounter import usable_moves
  self.upgrade('application1');self.assertEqual(M.describe(self.r,self.p.spec)['slot_count'],6)
  self.assertIn('move/페인트',usable_moves(self.e,self.p));self.assertEqual(len(M.describe(self.r,self.p.spec)['known']),7)
  self.upgrade('application2');self.assertEqual(self.p.moves.count('move/페인트'),1)
  before=deepcopy((self.e._physical_objects,self.p.spec,self.p.moves))
  with self.assertRaisesRegex(ValueError,'at most twice'):self.upgrade('application3')
  self.assertEqual((self.e._physical_objects,self.p.spec,self.p.moves),before)
  e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)));q=next(c for c in e.everyone if c.entity_id==self.p.entity_id)
  row=deepcopy(e._physical_objects[self.row['id']]);row['augmentation_active']=False;S.observe(e,row,reason='observed Augmentation Shock disables implant')
  self.assertNotIn('move/페인트',q.moves);self.assertEqual(len(row['experimental_designs']),2)
  row['augmentation_active']=True;S.observe(e,row,reason='observed shock expiry restores implant');self.assertIn('move/페인트',q.moves)
  row['installations']=[];S.observe(e,row,reason='actual implant removed');self.assertNotIn('move/페인트',q.moves)
  row['experimental_designs']=[]
  with self.assertRaisesRegex(ValueError,'history'):S.observe(e,row,reason='cannot erase consumed target applications')
 def test_smart_vision_independently_learned_feint_survives_source_end(self):
  import special_entities as S
  self.e.gm.set_move(self.p,'move/성장',add=False,reason='actual chosen forgetting leaves a learned slot')
  self.upgrade('application1');M.observe_learning(self.e,self.p,'페인트',method='feature',source='feat/프로토-디자인',paid_tp=0,reason='independent observed learned source')
  row=deepcopy(self.e._physical_objects[self.row['id']]);row['installations']=[];S.observe(self.e,row,reason='actual implant removed')
  self.assertIn('move/페인트',self.p.moves);self.assertEqual(M.describe(self.r,self.p.spec)['slot_count'],6)

if __name__=='__main__':unittest.main()

