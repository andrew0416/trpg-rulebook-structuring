"""Actual paid hits choose one Iterative Evolution branch after other effects."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_class_passive_combat_bulk as F
import class_passive_combat as C,combat_damage as DAMAGE,type_ace as TA


class IterativeEvolutionEffectivenessTests(unittest.TestCase):
 setUpClass=classmethod(F.ClassPassiveCombatBulkTests.setUpClass.__func__)
 fixture=F.ClassPassiveCombatBulkTests.fixture
 activate=F.ClassPassiveCombatBulkTests.activate

 def paid_hit(self,types,*,tinted=False,move_name='은빛바람',actual_type=None):
  e,t,p,q=self.fixture(feats=[C.ADAPTIVE],pokemon_types=['노말'],enemy_types=types,pokemon_moves=[move_name])
  if tinted:e.gm.set_ability(p,'색안경',reason='actual acquired Tinted Lens before the hit')
  e.gm.observe_loyalty(p,6,reason='observed native Move command obedience')
  self.activate(e,t,p,C.ADAPTIVE);sustain=p.spec[C.STATE]['sustains'][C.ADAPTIVE]
  self.assertEqual((sustain['acquisition_source'],sustain['clause_id']),(C.ADAPTIVE,C.CLAUSE_BY_RULE[C.ADAPTIVE]))
  self.assertEqual(t.spec['ap_bound'][sustain['instance']],2);self.assertEqual(t.budget['standard'],0)
  self.assertIs(C._active(e,p,C.ADAPTIVE)[0],t)
  e.end_of_turn(t);e.start_of_turn(p,initiative_count=19)
  move=e.r.move('move/'+move_name);printed=move['type'];damage_type=actual_type or printed
  if actual_type is not None:p.type_override_next=actual_type
  db=e.damage_base(p,move,target=q,_actual_damage_type=damage_type)
  dice=e.r.mech('combat/damage-chart')['by_damage_base'][str(db)]['set']['mid']
  attack=p.staged('spa' if move['class']=='특수' else 'atk')
  defense=q.staged('spd' if move['class']=='특수' else 'def')
  bonuses=[];accuracies=[];native_bonus=C.damage_roll_modifier;native_accuracy=C.accuracy_bonus
  def bonus(*args):
   value=native_bonus(*args);bonuses.append((args[3]['type'],args[4],value));return value
  def accuracy(*args):
   value=native_accuracy(*args);accuracies.append(value);return value
  hp=q.hp
  with patch.object(e,'d20',return_value=10),patch.object(C,'damage_roll_modifier',side_effect=bonus),patch.object(C,'accuracy_bonus',side_effect=accuracy),patch.object(TA,'damage_bonus',wraps=TA.damage_bonus) as ace:
   dealt=e.use_move(p,q,move['id'],set_damage=True)
  self.assertEqual(len(bonuses),1);self.assertEqual(len(accuracies),1);self.assertEqual(len(ace.call_args_list),1)
  self.assertEqual(q.hp,hp-dealt);self.assertGreater(dealt,0)
  self.assertEqual((p.budget['standard'],p.move_uses[move['id']]),(0,1))
  self.assertEqual(t.spec['ap_bound'][sustain['instance']],2)
  self.assertEqual(e.r.move(move['id'])['type'],printed);self.assertIsNone(p.type_override_next)
  self.assertTrue(e.validate_state()['valid'])
  return dealt,dice,attack,defense,bonuses[0],accuracies[0],ace.call_args.args[-1]

 def check_hit(self,types,before,after,bonus,accuracy,**options):
  dealt,dice,attack,defense,observed,actual_accuracy,ace_multiplier=self.paid_hit(types,**options)
  self.assertEqual(observed,(options.get('actual_type','벌레'),before,bonus))
  self.assertEqual(actual_accuracy,accuracy);self.assertEqual(ace_multiplier,after)
  defended=DAMAGE.defend(dice=dice,attack=attack,modifiers=bonus,defense=defense,reduction=0)
  self.assertEqual(dealt,DAMAGE.scale(after_defense=defended['after_defense'],type_multiplier=after))

 def test_paid_damage_selects_one_branch_after_actual_tinted_lens_before_own_relief(self):
  for types,tinted,before,after,bonus,accuracy in (
      (['노말'],False,1,1,4,0),
      (['풀'],False,1.5,1.5,0,2),
      (['불꽃'],False,0.5,1,0,0),
      (['불꽃','비행'],False,0.25,0.5,0,0),
      (['불꽃'],True,1,1,4,0),
      (['불꽃','비행'],True,0.5,1,0,0)):
   with self.subTest(types=types,tinted=tinted):self.check_hit(types,before,after,bonus,accuracy,tinted=tinted)

 def test_paid_damage_relief_uses_consumed_actual_type_in_both_directions(self):
  self.check_hit(['불꽃'],0.5,1,0,0,move_name='화염방사',actual_type='벌레')
  self.check_hit(['불꽃'],0.5,0.5,0,0,move_name='은빛바람',actual_type='불꽃')


if __name__=='__main__':unittest.main()
