"""All eight Core Vitamins share five slots; special doses retain exact choices."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import items as I,move_state as M,vitamin_moves as V,frequency as F,state_codec as C

class VitaminMoveStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def setUp(self):
  self.e=Engine(self.r,seed=881)
  self.a=Combatant(self.r,build_trainer(self.r,'Owner',20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},extra={'items':{'타우린':8,V.HEART:2,V.PP:3}}))
  self.p=Combatant(self.r,build_pokemon(self.r,'브케인',5,moves=['move/화염방사','move/파괴광선','move/하이퍼보이스','move/몸통박치기'],abilities=[],extra={'tutor_points':5}))
  for c in (self.a,self.p):self.e.gm.add_combatant(c,pos=(0,0),side='party',reason='actual Vitamin users')
 def test_heart_booster_actual_tp_once_and_shared_five_limit(self):
  self.assertEqual(self.e.use_item(self.a,V.HEART,self.p),(1,0));self.assertEqual(self.p.spec['tutor_points'],7)
  self.e.use_item(self.a,V.HEART,self.p);self.assertEqual(self.p.spec['tutor_points'],7);self.assertEqual(len(self.p.spec['vitamins']),1)
  attack=self.p.spec['stats']['atk']
  for _ in range(5):self.e.use_item(self.a,'타우린',self.p)
  self.assertEqual(self.p.spec['stats']['atk'],attack+4);self.assertEqual(len(self.p.spec['vitamins']),5)
  self.assertEqual(M.vitamin_state(self.r,self.p.spec)['occupied'],5)
 def test_pp_up_three_frequency_kinds_and_selected_move_persists_when_forgotten(self):
  for mid,expected in [('move/화염방사',('at_will',1)),('move/파괴광선',('daily',3)),('move/하이퍼보이스',('scene',3))]:
   with self.subTest(mid=mid):
    p=Combatant(self.r,build_pokemon(self.r,'브케인',5,moves=[mid],abilities=[]));self.e.gm.add_combatant(p,pos=(1,1),side='party',reason='independent actual dose recipient')
    self.assertEqual(self.e.use_item(self.a,V.PP,p,selected_move=mid),(1,0));self.assertEqual(F.move_frequency(self.e,mid,p),expected)
    self.e.gm.set_move(p,mid,add=False,reason='actual chosen forgetting');self.assertEqual(F.move_frequency(self.e,mid,p),expected)
  e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  for p in e.everyone:
   record=p.spec.get('vitamin_special_uses',{}).get(V.PP)
   if record:self.assertEqual(F.move_frequency(e,record['move_id'],p),dict([('move/화염방사',('at_will',1)),('move/파괴광선',('daily',3)),('move/하이퍼보이스',('scene',3))])[record['move_id']])
 def test_pp_up_unlearned_choice_does_not_consume_and_second_dose_has_no_effect(self):
  before=deepcopy((self.a.spec,self.p.spec))
  with self.assertRaisesRegex(ValueError,'actually learned'):self.e.use_item(self.a,V.PP,self.p,selected_move='냉동빔')
  self.assertEqual((self.a.spec,self.p.spec),before)
  self.e.use_item(self.a,V.PP,self.p,selected_move='화염방사');self.e.use_item(self.a,V.PP,self.p,selected_move='파괴광선')
  self.assertEqual(F.move_frequency(self.e,'move/화염방사',self.p),('at_will',1));self.assertEqual(F.move_frequency(self.e,'move/파괴광선',self.p),('daily',2));self.assertEqual(len(self.p.spec['vitamins']),1)
 def test_vm_and_special_vitamin_share_last_slot_without_dose_history_loss(self):
  for mid in ('move/화염방사','move/파괴광선','move/하이퍼보이스'):self.e.gm.set_move(self.p,mid,add=False,reason='actual chosen forgetting of imported moves')
  self.p.spec['vitamins']=['타우린']*4
  M.observe_vm_learning(self.e,self.p,'냉동빔',application_id='actual-vm',reason='GM observed completed application')
  self.e.use_item(self.a,V.HEART,self.p);self.assertEqual(self.p.spec['tutor_points'],5);self.assertEqual(len(self.p.spec['vitamins']),4)
  self.e.gm.set_move(self.p,'move/냉동빔',add=False,reason='actual VM move forgotten')
  self.e.use_item(self.a,V.HEART,self.p);self.assertEqual(self.p.spec['tutor_points'],7);self.assertEqual(len(self.p.spec['vitamins']),5)

if __name__=='__main__':unittest.main()
