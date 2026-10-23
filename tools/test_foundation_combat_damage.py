from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import combat_damage as D
import test_category2_move_accuracy_admission as F

class DamageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.MoveAccuracyAdmissionTests.setUpClass()
 def test_defense_floor_precedes_exact_multipliers(self):
  r=D.defend(dice=5,attack=4,modifiers=-2,defense=20,reduction=3)
  self.assertEqual(r,{'total':7,'after_defense':1})
  self.assertEqual(D.scale(after_defense=r['after_defense'],type_multiplier=.5),0)
  self.assertEqual(D.scale(after_defense=7,type_multiplier=.5,other_multiplier=1.5),5)
  self.assertEqual(D.scale(after_defense=10,type_multiplier=0),0)
  self.assertEqual(D.scale(after_defense=7,type_multiplier=.5,adjustment=-10),0)
 def test_reject_invalid_numeric_data(self):
  for value in (True,float('nan'),float('inf'),-1):
   with self.subTest(value=value),self.assertRaises(ValueError):D.scale(after_defense=4,type_multiplier=value)
  with self.assertRaises(ValueError):D.scale(after_defense=4,type_multiplier=1,adjustment=.5)
 def test_native_calculation_uses_common_stages(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp()
  with patch.object(D,'defend',wraps=D.defend) as defend,patch.object(D,'scale',wraps=D.scale) as scale:
   value=f.e.roll_damage(f.other,f.p,f.r.move('move/물대포'),set_damage=True)
  self.assertGreater(value,0);self.assertEqual(defend.call_count,1);self.assertGreaterEqual(scale.call_count,1)
 def test_core_move_classes_select_separate_defenses_through_native_damage(self):
  for mid,stat in [('move/몸통박치기','def'),('move/물대포','spd')]:
   with self.subTest(mid=mid):
    from engine import Rules
    f=F.MoveAccuracyAdmissionTests();f.r=Rules(str(ROOT),ruleset='core');f.setUp();f.p.stats.update({'def':3,'spd':19})
    move=f.r.move(mid);receipt={}
    with patch.object(D,'defend',wraps=D.defend) as defend:
     f.e.resolve_attack_damage(f.other,f.p,move,set_damage=True,_damage_observation=receipt)
    self.assertEqual(defend.call_args.kwargs['defense'],f.p.staged(stat))
    self.assertEqual(receipt['damage_class'],move['class']);self.assertGreater(receipt['requested'],0);f.valid()
  self.assertEqual(f.r.move('move/카운터')['class'],'물리')
  self.assertNotIsInstance(f.r.move('move/카운터')['damage_base'],int)
 def test_core_status_move_runs_its_effect_without_physical_or_special_damage(self):
  import blessing_effects as B
  f=F.MoveAccuracyAdmissionTests();f.setUp();f.known(f.other,'빛의장막');hp=f.other.hp;f.begin(f.other)
  self.assertEqual(f.r.move('move/빛의장막')['class'],'변화')
  with patch.object(f.e,'roll_damage',side_effect=AssertionError('status has no damage class')),patch.object(D,'defend',side_effect=AssertionError('status has no defense mapping')):
   f.e.use_move(f.other,f.other,'move/빛의장막')
  self.assertEqual(f.other.hp,hp);self.assertEqual(len(B.live(f.other)),1)
  self.assertEqual(B.live(f.other)[0]['source'],'move/빛의장막')
  self.assertEqual(f.other.move_uses['move/빛의장막'],1);self.assertEqual(f.other.budget['standard'],0);f.valid()
 def test_native_receipt_separates_request_and_temporary_hp(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp()
  import effects as FX
  FX.run_effects(f.e,f.p,f.p,[{'type':'temp_hp','value':100}],{'hit':True,'attacker':f.p,'target':f.p,'engine':f.e},'fixture grant')
  receipt={};before=f.p.hp
  damage=f.e.resolve_attack_damage(f.other,f.p,f.r.move('move/물대포'),set_damage=True,_damage_observation=receipt)
  self.assertEqual(receipt['requested'],damage);self.assertGreater(damage,0)
  self.assertEqual(receipt['net_hp_loss'],0);self.assertEqual(f.p.hp,before)
  self.assertEqual(receipt['net_temporary_hp_loss'],damage)
  self.assertEqual(receipt['damage_class'],'특수')
 def test_attack_stat_override_does_not_change_damage_class(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp()
  f.e.rule_effect('move/물대포','add',{'type':'damage_formula_override','attack_stat':'target.atk','defense_stat':'def'},reason='explicit stat source')
  f.p.stats['atk']=47
  with patch.object(D,'defend',wraps=D.defend) as defend:
   f.e.roll_damage(f.other,f.p,f.r.move('move/물대포'),set_damage=True)
  self.assertEqual(defend.call_args.kwargs['attack'],f.p.staged('atk'))
  self.assertEqual(f.r.move('move/물대포')['class'],'특수')
 def test_native_cap_receipt_keeps_requested_and_actual_distinct(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp();f.p.damage_cap={'value':2}
  receipt={};hp=f.p.hp
  requested=f.e.resolve_attack_damage(f.other,f.p,f.r.move('move/물대포'),set_damage=True,_damage_observation=receipt)
  self.assertGreater(requested,2);self.assertEqual(receipt['requested'],requested)
  self.assertEqual(receipt['net_hp_loss'],2);self.assertEqual(f.p.hp,hp-2)
  self.assertEqual(receipt['net_temporary_hp_loss'],0)
 def test_application_trace_is_serializable_and_detached(self):
  f=F.MoveAccuracyAdmissionTests();f.setUp()
  import event_trace as T,json
  T.enable(f.e)
  f.e.resolve_attack_damage(f.other,f.p,f.r.move('move/물대포'),set_damage=True)
  records=T.records(f.e);json.dumps(records)
  receipts=[c['damage_application'] for row in records for c in row['calculations'] if 'damage_application' in c]
  self.assertEqual(len(receipts),1);self.assertGreater(receipts[0]['requested'],0)
  receipts[0]['before']['hp']=-999
  self.assertNotIn('-999',json.dumps(T.records(f.e)))
if __name__=='__main__':unittest.main()
