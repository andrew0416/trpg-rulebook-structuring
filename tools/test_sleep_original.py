"""Sleep's actual ally action and native loss consumers; shared checks reused."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
from engine import Rules,Engine,Combatant
from grid import Grid
import turn as TURN,temporary_hp as TEMP,world_entities as W
import equipment_actions as EQUIPMENT
from state_codec import load_engine

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def world(self,kind='trainer'):
  e=Engine(self.r,6);e.everyone=e.gm.everyone=[];e.grid=Grid(12,12)
  def actor(name,pos):
   c=Combatant(self.r,dict(name=name,kind=kind,level=20,size='medium',
       stats={s:30 for s in ('hp','atk','def','spa','spd','spe')},types=['노말'],
       moves=['move/스피드스타'],abilities=[],movement={'land':4},pos=pos))
   c.side='party';e.everyone.append(c);e.gm.set_footprint(c,[(0,0)],reason='actual occupied body');return c
  a,b=actor('helper',(1,1)),actor('sleeper',(2,1))
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
  e.apply_status(b,'잠듦');e.apply_status(b,'악몽');return e,a,b
 def state(self,e,a,b):
  return deepcopy((a.budget,a.hp,b.hp,b.temp_hp,a.conditions,b.conditions,b.custom_conditions,e.rng.getstate()))
 def test_actual_trainer_and_pokemon_wake_ally_pay_one_standard_and_preserve_other_state(self):
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    e,a,b=self.world(kind);e.apply_status(b,'독');TEMP.grant(e,b,12);hp=b.hp;rng=e.rng.getstate()
    self.assertTrue(e.wake_ally(a,b));self.assertEqual(a.budget,{'standard':0,'shift':1,'swift':1})
    self.assertNotIn('잠듦',b.conditions);self.assertNotIn('악몽',b.conditions);self.assertIn('독',b.conditions)
    self.assertEqual((b.hp,b.temp_hp,e.rng.getstate()),(hp,12,rng))
    saved=e.gm.snapshot();loaded=load_engine(self.r,json.loads(json.dumps(e.export_state())))
    bb=W.actor_index(loaded)[b.entity_id];self.assertEqual(bb.conditions,b.conditions)
    e.apply_status(b,'잠듦');e.gm.restore(saved);self.assertNotIn('잠듦',b.conditions)
    with self.assertRaisesRegex(ValueError,'asleep ally'):e.wake_ally(a,b)
 def test_invalid_contact_identity_and_side_refuse_before_cost(self):
  for case in ('enemy','self','far','off_field','unregistered','blocked'):
   with self.subTest(case=case):
    e,a,b=self.world()
    if case=='enemy':b.side='foes'
    elif case=='self':b=a;e.apply_status(a,'잠듦')
    elif case=='far':b.pos=(5,5)
    elif case=='off_field':b.on_field=False
    elif case=='unregistered':b=deepcopy(b) # copied identity is not the registered actual actor
    elif case=='blocked':e.grid.blocking.add(b.pos)
    before=self.state(e,a,b)
    with self.assertRaises(ValueError):e.wake_ally(a,b)
    self.assertEqual(self.state(e,a,b),before)
 def test_action_unavailable_sleep_or_other_turn_cannot_wake(self):
  for case in ('budget','sleep','other_turn'):
   with self.subTest(case=case):
    e,a,b=self.world()
    if case=='budget':a.budget['standard']=0
    elif case=='sleep':e.apply_status(a,'잠듦')
    else:e.end_of_turn(a);e.start_of_turn(b,initiative_count=10)
    before=self.state(e,a,b)
    self.assertFalse(e.wake_ally(a,b));self.assertEqual(self.state(e,a,b),before)
 def test_late_cure_failure_rolls_back_ally_cost_and_damage(self):
  original=Engine.cure_status
  def fail(e,c,condition):
   result=original(e,c,condition)
   if condition=='잠듦':raise ValueError('late Sleep cure')
   return result
  for operation in ('ally','damage'):
   with self.subTest(operation=operation):
    e,a,b=self.world();TEMP.grant(e,b,7);before=self.state(e,a,b)
    with patch.object(Engine,'cure_status',fail):
     with self.assertRaisesRegex(ValueError,'late Sleep cure'):
      e.wake_ally(a,b) if operation=='ally' else e.take_damage(b,3)
    self.assertEqual(self.state(e,a,b),before)
 def test_native_damage_zero_or_shield_loss_and_neutral_passive_loss(self):
  e,a,b=self.world();TEMP.grant(e,b,20);hp=b.hp
  e.lose_hp(b,3,source='독');self.assertIn('잠듦',b.conditions)
  e.take_damage(b,0);self.assertIn('잠듦',b.conditions)
  e.take_damage(b,4);self.assertNotIn('잠듦',b.conditions);self.assertEqual((b.hp,b.temp_hp),(hp,13))
 def test_actual_delayed_attack_wakes_after_failed_sleep_save_and_restore(self):
  from test_category2_delayed_attacks import DelayedAttackTests
  f=DelayedAttackTests();f.rules=self.r;e,a,b=f.world('move/미래예지')
  e.use_move_on(a,b,'move/미래예지',e.everyone);e.apply_status(b,'잠듦')
  loaded=load_engine(self.r,json.loads(json.dumps(e.export_state())))
  a,b=(W.actor_index(loaded)[x.entity_id] for x in (a,b));loaded.rng.seed(31)
  f.finish_target_turn(loaded,a,b);self.assertNotIn('잠듦',b.conditions)
  self.assertFalse(hasattr(loaded,'_sleep_damage_sources'));self.assertTrue(loaded.validate_state()['valid'])
 def test_actual_pending_incineration_loss_wakes_once_after_gm_and_json_restore(self):
  from test_category2_csv_item_transfers import Tests as Fixture
  Fixture.setUpClass();f=Fixture();e,a,b,mid=f.fixture('불태우기',held=(None,'선제공격손톱'))
  e.apply_status(b,'잠듦');e.apply_status(b,'악몽')
  with patch.object(Engine,'roll_damage',return_value=0),patch.object(Engine,'accuracy_check',return_value=(True,20,False)):
   e.use_move(a,b,mid)
  row=EQUIPMENT.pending(e)[0];self.assertIn('잠듦',b.conditions);token=row['id']
  e.gm.snapshot('pending-sleep');e.gm.restore('pending-sleep')
  loaded=load_engine(e.r,json.loads(json.dumps(e.export_state())));bb=W.actor_index(loaded)[b.entity_id]
  before=bb.hp;result=EQUIPMENT.resolve(loaded,bb,token,choice='hp_loss')
  self.assertNotIn('잠듦',bb.conditions);self.assertNotIn('악몽',bb.conditions)
  self.assertEqual(before-bb.hp,loaded.tick(bb));self.assertEqual(result['applications'],1)
  EQUIPMENT.resolve(loaded,bb,token,choice='hp_loss');self.assertEqual(before-bb.hp,loaded.tick(bb))
  self.assertTrue(loaded.validate_state()['valid'])
 def test_actual_steelheart_zero_damage_followup_wakes(self):
  from test_category2_optional_weapon_framework import OptionalWeaponFrameworkTests as WeaponTests
  import optional_weapon_framework as FW
  WeaponTests.setUpClass();f=WeaponTests();e,a,b,_=f.fixture(family='steelheart',athletics=4,focus=5,combat=2)
  uid=f.weapon(e,a,'steel/sleep',arcane=False,metal=True,moves=['move/강타']);key=FW.equip(e,a,uid);f.start(e,a)
  with patch.object(Engine,'accuracy_check',return_value=(True,18,False)),patch.object(Engine,'roll_damage',return_value=0):
   e.use_move(a,b,'move/몸통박치기',set_damage=True)
   e.apply_status(b,'잠듦');hp=b.hp;TURN.reset_budget(e,a)
   e.use_move(a,b,key,weapon_id=uid,set_damage=True)
  self.assertNotIn('잠듦',b.conditions);self.assertEqual(hp-b.hp,e.tick(b))
 def test_actual_machine_weapon_damage_and_hp_loss_wake(self):
  from test_foundation_control_vehicle import VehicleTests
  VehicleTests.setUpClass()
  for kind in ('attack_damage','hp_loss'):
   with self.subTest(kind=kind):
    f=VehicleTests();f.setUp();value=f.policy();value['weapons'][0]['damage']['kind']=kind
    f.e.apply_status(f.t,'잠듦');hp=f.t.hp;result=f.fire(value=value)
    self.assertTrue(result['passed']);self.assertLess(f.t.hp,hp);self.assertNotIn('잠듦',f.t.conditions)
 def test_observed_mapless_contact_and_vertical_contact_use_existing_reach(self):
  from test_mapless_space import MaplessTests
  import common_checks as C
  f=MaplessTests();f.r=self.r;f.setUp();e,a,b=f.e,f.a,f.b;b.side=a.side
  f.configure(contacts=[[a.entity_id,b.entity_id]]);e.apply_status(b,'잠듦')
  self.assertTrue(e.wake_ally(a,b));self.assertNotIn('잠듦',b.conditions)
  e,a,b=self.world();b.spec['_movement_altitude']=1;before=self.state(e,a,b)
  self.assertIsInstance(e.wake_ally(a,b),C.PendingDecision);self.assertEqual(self.state(e,a,b),before)
  self.assertTrue(e.wake_ally(a,b,contact={'reach_distance':1,'reach_reason':'observed adjacent raised body'}))
 def test_actual_execute_attack_wakes_after_hp_setting(self):
  import effects_ext as EXT
  e,a,b=self.world();b.side='foes';a.moves.append('move/절대영도')
  with patch.object(Engine,'accuracy_check',return_value=(True,20,False)),patch.object(EXT.POOLS,'die',return_value=1):
   e.use_move(a,b,'move/절대영도')
  self.assertLessEqual(b.hp,0);self.assertNotIn('잠듦',b.conditions)
 def test_actual_reflected_attack_loss_wakes_after_sleep_arrives_before_reaction(self):
  import effects_ext as EXT
  e,a,b=self.world();e.cure_status(b,'잠듦');b.side='foes';b.moves.append('move/미러코트')
  mechanics,_=e.r.move_mech('move/미러코트')
  effect=next(x for x in mechanics['effects_exec'] if x['type']=='reaction_reflect')
  EXT.h_reaction_ext(e,b,b,effect,{'move':e.r.move('move/미러코트')})
  self.assertIsNotNone(b.reflect)
  original=EXT.after_move;hp=a.hp
  def after(engine,actor,target,move,mechanics,ctx):
   engine.apply_status(actor,'잠듦') # actual condition arriving before the already earned reaction
   return original(engine,actor,target,move,mechanics,ctx)
  with patch.object(EXT,'after_move',after):e.use_move(a,b,'move/스피드스타')
  self.assertLess(a.hp,hp);self.assertNotIn('잠듦',a.conditions);self.assertIsNone(b.reflect)
 def test_actual_hp_redistribution_target_wakes_and_late_cure_rolls_back(self):
  original=Engine.cure_status
  def fail(engine,actor,condition):
   original(engine,actor,condition)
   if condition=='잠듦':raise ValueError('late redistribution wake')
  for broken in (False,True):
   with self.subTest(broken=broken):
    e,a,b=self.world();a.moves.append('move/아픔나누기');b.side='foes';e.lose_hp(a,20);hp=(a.hp,b.hp)
    if broken:
     with patch.object(Engine,'cure_status',fail):e.use_move(a,b,'move/아픔나누기')
     self.assertEqual((a.hp,b.hp),hp);self.assertIn('잠듦',b.conditions)
    else:
     e.use_move(a,b,'move/아픔나누기');self.assertNotIn('잠듦',b.conditions);self.assertLess(b.hp,hp[1])
 def test_sleep_suppresses_all_evasions_and_all_three_condition_saves(self):
  e,a,b=self.world()
  self.assertEqual([b.evasion(k) for k in ('물리','특수','변화')],[0,0,0])
  self.assertTrue(e.wake_ally(a,b));self.assertTrue(all(b.evasion(k)>0 for k in ('물리','특수','변화')))
  for cond in ('난동','혼란','헤롱헤롱'):e.apply_status(a,cond,applied_by=b)
  e.apply_status(a,'잠듦')
  with patch.object(Engine,'d20',return_value=15) as die:e.end_of_turn(a)
  self.assertEqual(die.call_count,1)
  self.assertTrue({'잠듦','난동','혼란','헤롱헤롱'}<=a.conditions)

if __name__=='__main__':unittest.main()
