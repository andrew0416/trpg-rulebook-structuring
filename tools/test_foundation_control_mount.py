"""Actual boarding, physical load, native shared paths and retention triggers."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_body_modes as _fixture_test_category2_body_modes
from engine import Combatant
from builder import build_trainer,build_pokemon
from state_codec import dump_engine,load_engine,StateCodecError
import control_mount as M,state_grants as G,capability_actions as LOAD,world_entities as W,roll_context as R,forced_movement as FORCE,turn as TURN


class MountTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_body_modes.Tests.setUpClass.__func__)
 add=_fixture_test_category2_body_modes.Tests.add
 pokemon=_fixture_test_category2_body_modes.Tests.pokemon
 begin=_fixture_test_category2_body_modes.Tests.begin
 def setUp(self):
  _fixture_test_category2_body_modes.Tests.setUp(self);self.a.spec['skills'].update({'곡예':3,'육상':3});self.a.spec['weight_kg']=20
  self.p.pos=(2,3);self.t.pos=(14,3);self.p.spec['movement']['power']=3;self.p.movement=6
 def policy(self,index=0):return json.loads((ROOT/'data/examples/control-mount.json').read_text(encoding='utf8'))[index]
 def board(self,value=None,rider=None,mount=None):
  value=value or self.policy();rider=rider or self.a;mount=mount or self.p
  count=R.plan(self.e,rider,value['boarding']['skill'],purpose='declared mounting',target=mount)['dice_count']
  return self.e.board_mount(rider,mount,value,gm_mountable=True,roll_options={'fixed':[6]*count})
 def snap(self):return dump_engine(self.e)
 def auto(self):self.a.spec['edges'].append('edge/탑승-기량')
 def native(self):self.auto();return self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True)
 def test_native_gm_admission_does_not_require_mountable_and_denial_is_atomic(self):
  self.assertFalse(any(name.startswith(('탑승','Mountable')) for name in G.effective_capabilities(self.p)))
  self.auto()
  for decision in (False,None,'yes'):
   before=self.snap()
   with self.assertRaisesRegex(ValueError,'GM must establish'):
    self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=decision)
   self.assertEqual(before,self.snap())
  out=self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True)
  self.assertTrue(out['passed']);self.assertTrue(out['automatic'])
  self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
  self.assertIs(getattr(self.p,M.RIDERS)[0],self.a)
 def test_data_boarding_uses_actual_weight_native_action_and_body_relation(self):
  self.begin(self.a);out=self.board();self.assertTrue(out['passed']);self.assertFalse(out['automatic'])
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.pos,self.p.pos)
  self.assertIs(getattr(self.p,M.RIDERS)[0],self.a);self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
  self.assertEqual((LOAD.load(self.p)['weight_kg'],LOAD.load(self.p)['band']),(20,'heavy'))
 def test_native_mount_suitability_uses_observed_individual_not_a_species_or_level_ban(self):
  import body_state as BODY
  cases=(('포니타',20,1.0,True),('포니타',25,1.0,True),
         ('포니타',1,0.4,False),('롱스톤',1,0.8,False),
         ('롱스톤',1,4.0,True))
  for species,level,height,admitted in cases:
   with self.subTest(species=species,level=level,height=height):
    self.setUp();self.auto();self.a.spec['weight_kg']=60
    mount=self.add(build_pokemon(self.r,species,level,extra={'trainer_id':self.a.entity_id,'height_m':height}))
    mount.pos=(8,6)
    self.assertEqual(BODY.projection(mount)['height_m'],height)
    before=self.snap()
    if not admitted:
     with self.assertRaisesRegex(ValueError,'GM must establish'):
      self.e.pokemon_activity(self.a,'mounting',target=mount,phase='mount',gm_mountable=False)
     self.assertEqual(before,self.snap());continue
    result=self.e.pokemon_activity(self.a,'mounting',target=mount,phase='mount',gm_mountable=True)
    self.assertTrue(result['passed']);self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),mount)
    self.assertEqual(self.a.pos,mount.pos)
    # These are GM observations of the individual, not universal size/age cutoffs.
    self.assertEqual(self.a.spec[M.CONTRACT]['policy']['load'],{'kind':'gm'})
    loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
    index=W.actor_index(loaded);actual=index[mount.entity_id]
    self.assertEqual(BODY.projection(actual)['height_m'],height)
    self.assertIs(W.mount_relation(index,index[self.a.entity_id]),actual)
 def test_large_low_power_mount_cannot_carry_a_known_heavy_rider(self):
  import body_state as BODY
  for power in (1,2):
   with self.subTest(power=power):
    self.setUp();self.p.spec.update(size='Large',height_m=4.0)
    self.p.spec['movement']['power']=power;self.a.spec['weight_kg']=60
    self.assertEqual(len(BODY.cells(self.p)),4);self.assertEqual(LOAD.power(self.p),power)
    self.assertLess(LOAD.limits(self.p)['staggering'],self.a.spec['weight_kg'])
    before=self.snap()
    with self.assertRaisesRegex(ValueError,'Power limit'):self.board()
    self.assertEqual(before,self.snap());self.assertNotIn('mount_id',self.a.spec)
    # Size does not erase actual mass, and Power 1/2 is not an absolute species ban.
    self.a.spec['weight_kg']=1
    self.assertTrue(self.board()['passed']);self.assertEqual(LOAD.load(self.p)['weight_kg'],1)
    self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
 def test_rider_moves_mount_then_commands_a_different_actual_pokemon_in_same_round(self):
  import party_actions as PARTY
  companion=self.add(build_pokemon(self.r,'꼬부기',20,moves=['move/물대포'],extra={'trainer_id':self.a.entity_id}))
  companion.pos=(12,5);self.e.gm.observe_loyalty(companion,6,reason='actual companion obeys rider')
  PARTY.configure(self.e,self.a,battle_mode='full_contact',reason='mounted trainer commands another Pokemon')
  self.native();self.begin(self.a);result=self.e.approach(self.a,self.t)
  self.assertGreater(result['distance'],0);used=getattr(self.p,M.POOL)['used']
  position=self.p.pos;mount_actions=deepcopy(getattr(self.p,'budget',None));trainer_actions=deepcopy(self.a.budget)
  round_no=self.e.round_no;target_hp=self.t.hp
  self.e.end_of_turn(self.a);self.e.start_of_turn(companion,initiative_count=10)
  with patch.object(self.e,'d20',return_value=18):
   command=self.e.pokemon_activity(self.a,'command_move',pokemon=companion,target=self.t,move_id='move/물대포',set_damage=True)
  self.assertEqual(command['status'],'submitted');self.assertEqual(companion.move_uses['move/물대포'],1)
  self.assertGreater(command['move_result'],0);self.assertLess(self.t.hp,target_hp);self.assertEqual(self.e.round_no,round_no)
  self.assertEqual(companion.budget['standard'],0)
  self.assertEqual((self.p.pos,self.a.pos),(position,position));self.assertEqual(getattr(self.p,M.POOL)['used'],used)
  self.assertEqual(getattr(self.p,'budget',None),mount_actions);self.assertEqual(self.a.budget,trainer_actions)
  self.assertEqual(self.a.spec['party_command_turns'][-1]['pokemon_id'],companion.entity_id)
  self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
 def test_unmet_ownership_skill_adjacency_mass_and_foreign_inputs_do_not_consume(self):
  before=self.snap()
  for bad in (copy(self.p),self.a):
   with self.assertRaises(ValueError):self.board(mount=bad)
   self.assertEqual(before,self.snap())
  for mutate in (lambda:self.p.spec.pop('trainer_id',None),lambda:self.a.spec['skills'].update({'곡예':1}),lambda:setattr(self.p,'pos',(7,3)),lambda:self.a.spec.update(weight_kg=1000)):
   self.setUp();mutate();before=self.snap()
   with self.assertRaises(ValueError):self.board()
   self.assertEqual(before,self.snap())
 def test_native_automatic_boarding_still_rolls_retention_and_failure_releases_load(self):
  self.native();self.assertEqual(self.a.pos,self.p.pos);before=self.a.pos
  out=self.e.retain_mount(self.a,roll_options={'fixed':[1]*3});self.assertFalse(out['passed']);self.assertEqual(out['bonus'],3)
  self.assertNotIn('mount_id',self.a.spec);self.assertEqual(getattr(self.p,M.RIDERS),[]);self.assertEqual(self.a.pos,before)
 def test_rider_then_mount_share_actual_remaining_movement_without_reset_on_turn(self):
  self.native();self.begin(self.a);out=self.e.approach(self.a,self.t)
  self.assertEqual(out['distance'],6);self.assertEqual(out['remaining'],0);self.assertEqual(self.a.pos,self.p.pos)
  position=self.p.pos;self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=10);out=self.e.approach(self.p,self.t)
  self.assertEqual(out['distance'],0);self.assertEqual(self.p.pos,position);self.assertEqual(self.p.budget['standard'],1)
 def test_partial_rider_path_leaves_remaining_for_mount_and_preserves_diagonal_clock(self):
  self.native();self.begin(self.a);self.t.pos=(5,3);out=self.e.approach(self.a,self.t)
  self.assertEqual((out['distance'],out['remaining']),(2,4));position=self.p.pos
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=10);self.t.pos=(14,3)
  out=self.e.approach(self.p,self.t);self.assertEqual(out['distance'],4);self.assertEqual(out['remaining'],0);self.assertEqual(self.a.pos,self.p.pos)
  self.assertGreater(self.p.pos[0],position[0]);self.assertEqual(self.p.budget['standard'],1)
 def test_new_actual_round_refreshes_pool_and_dismount_cannot_refund_used_distance(self):
  self.native();self.begin(self.a);self.e.approach(self.a,self.t);self.e.dismount(self.a,reason='actual voluntary dismount')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=10);out=self.e.approach(self.p,self.t);self.assertEqual(out['remaining'],0)
  self.begin(self.p);out=self.e.approach(self.p,self.t);self.assertGreater(out['distance'],0)
 def test_actual_damage_threshold_triggers_retention_for_rider_or_mount(self):
  self.native();self.e.take_damage(self.p,1);self.assertNotIn('mount_retention_history',self.a.custom_conditions)
  amount=(self.a.base_max_hp+3)//4
  self.e.take_damage(self.a,amount)
  history=self.a.custom_conditions['mount_retention_history'];self.assertEqual(history[-1]['event'],'damage');self.assertEqual(history[-1]['mount_id'],self.p.entity_id)
  self.assertIsNotNone(history[-1]['check'])
 def test_actual_forced_displacement_syncs_rider_and_creates_retention(self):
  self.native();self.p.hp=self.p.base_max_hp
  out=FORCE.displace(self.e,self.t,self.p,direction=(1,0),distance=1,source='gm/actual push')
  self.assertEqual(out['moved'],1);self.assertEqual(self.a.pos,self.p.pos)
  self.assertEqual(self.a.custom_conditions['mount_retention_history'][-1]['event'],'forced_move')
 def test_known_average_rider_exception_is_removed_by_heavier_mass_or_ordinary_load(self):
  self.auto();value=self.policy(1);G.grant(self.p,'capabilities','Mountable 2','fixture:mountable','fixture');self.a.spec['weight_kg']=60
  self.e.board_mount(self.a,self.p,value,gm_mountable=True);self.assertEqual(LOAD.load(self.p)['weight_kg'],0)
  self.a.spec['weight_kg']=71
  with self.assertRaises(ValueError):LOAD.load(self.p)
  self.a.spec['weight_kg']=20;LOAD.set_carried(self.e,self.p,[{'id':'object/bag','weight_kg':1}],'actual additional bag')
  self.assertEqual(LOAD.load(self.p)['weight_kg'],21)
 def test_live_capability_loss_cannot_keep_average_weight_exemption(self):
  self.auto();value=self.policy(1);G.grant(self.p,'capabilities','Mountable 2','fixture:mountable','fixture');self.a.spec['weight_kg']=60
  self.e.board_mount(self.a,self.p,value,gm_mountable=True);G.revoke(self.p,'fixture:mountable')
  with self.assertRaises(ValueError):LOAD.load(self.p)
 def test_native_mountable_two_carries_real_riders_and_restores_shared_movement(self):
  self.p.pos=(0,8)
  self.p=self.add(build_pokemon(self.r,'날쌩마',5,extra={'trainer_id':self.a.entity_id}));self.p.pos=(2,3)
  self.e.gm.observe_loyalty(self.p,6,reason='actual native mount obedience');self.auto();self.a.spec['weight_kg']=60
  value=self.policy(1)
  self.assertIn('탑승 2',self.p.spec['capabilities']);self.assertEqual(value['source'],'capability/탑승-x')
  self.assertLess(LOAD.limits(self.p)['staggering'],120)
  self.assertTrue(self.e.board_mount(self.a,self.p,value,gm_mountable=True)['passed'])
  def rider(name,pos):
   c=self.add(build_trainer(self.r,name,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'곡예':3},extra={'edges':['edge/탑승-기량'],'weight_kg':60}));c.pos=pos;return c
  second=rider('native second rider',(1,4));self.e.board_mount(second,self.p,value,gm_mountable=True)
  self.assertEqual(LOAD.load(self.p),{'band':'normal','weight_kg':0,'penalty':0})
  third=rider('native third rider',(4,3));before=self.snap()
  with self.assertRaisesRegex(ValueError,'seat capacity'):self.e.board_mount(third,self.p,value,gm_mountable=True)
  self.assertEqual(before,self.snap())
  # The numeric average is an explicit GM observation, not a rulebook constant.
  self.a.spec['weight_kg']=value['load']['average_exception']['average_weight_kg']+1
  with self.assertRaisesRegex(ValueError,'Power limit'):LOAD.load(self.p)
  self.a.spec['weight_kg']=60
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'Power limit'):LOAD.set_carried(self.e,self.p,[{'id':'object/native-extra-bag','weight_kg':1}],'actual additional load')
  self.assertEqual(before,self.snap())
  third.pos=(0,0);self.begin(self.a);self.t.pos=(6,3);out=self.e.approach(self.a,self.t)
  self.assertEqual((out['distance'],out['remaining']),(2,6));self.assertEqual(self.a.pos,self.p.pos);self.assertEqual(second.pos,self.p.pos)
  saved=self.snap();loaded=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));index=W.actor_index(loaded)
  mount=index[self.p.entity_id];first=index[self.a.entity_id];other=index[second.entity_id]
  self.assertIs(getattr(mount,M.RIDERS)[0],first);self.assertIs(getattr(mount,M.RIDERS)[1],other)
  self.assertEqual(first.spec[M.CONTRACT]['policy']['source'],'capability/탑승-x')
  loaded.end_of_turn(first);loaded.start_of_turn(mount,initiative_count=10);index[self.t.entity_id].pos=(16,3)
  out=loaded.approach(mount,index[self.t.entity_id]);self.assertEqual((out['distance'],out['remaining']),(6,0))
  self.assertEqual(first.pos,mount.pos);self.assertEqual(other.pos,mount.pos)
  snapshot=self.e.gm.snapshot();self.e.dismount(self.a,reason='native mounted relation before restore');self.e.gm.restore(snapshot)
  self.assertIs(getattr(self.p,M.RIDERS)[0],self.a);self.assertIs(getattr(self.p,M.RIDERS)[1],second)
  self.assertEqual(getattr(self.p,M.POOL)['used'],2);self.assertEqual(LOAD.load(self.p)['weight_kg'],0)
 def test_declared_seat_capacity_uses_actual_other_riders(self):
  value=self.policy(1);self.auto();G.grant(self.p,'capabilities','Mountable 2','fixture:mountable','fixture')
  self.e.board_mount(self.a,self.p,value,gm_mountable=True)
  def other(name,pos):
   c=self.add(build_trainer(self.r,name,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'곡예':3},extra={'edges':['edge/탑승-기량'],'weight_kg':60}));c.pos=pos;return c
  b=other('second rider',(2,4));self.e.board_mount(b,self.p,value,gm_mountable=True);c=other('third rider',(3,3));before=self.snap()
  with self.assertRaisesRegex(ValueError,'seat capacity'):self.e.board_mount(c,self.p,value,gm_mountable=True)
  self.assertEqual(before,self.snap());self.assertEqual(len(getattr(self.p,M.RIDERS)),2)
 def test_json_and_gm_restore_keep_actual_rider_aliases_load_and_spent_pool(self):
  self.native();self.begin(self.a);self.e.approach(self.a,self.t);saved=self.snap()
  loaded=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));index=W.actor_index(loaded);mount=index[self.p.entity_id];rider=index[self.a.entity_id]
  self.assertIs(getattr(mount,M.RIDERS)[0],rider);self.assertEqual(rider.pos,mount.pos)
  loaded.end_of_turn(rider);loaded.start_of_turn(mount,initiative_count=10)
  self.assertEqual(loaded.approach(mount,index[self.t.entity_id])['remaining'],0)
  snapshot=self.e.gm.snapshot();self.e.dismount(self.a,reason='changed relation');self.e.gm.restore(snapshot)
  self.assertIs(getattr(self.p,M.RIDERS)[0],self.a);self.assertEqual(self.a.pos,self.p.pos)
 def test_late_boarding_or_movement_failure_rolls_back_aliases_rng_and_actions(self):
  self.begin(self.a);before=self.snap()
  with patch.object(M,'_attach',side_effect=ValueError('late boarding')):
   with self.assertRaisesRegex(ValueError,'late boarding'):self.board()
  self.assertEqual(before,self.snap());self.native();before=self.snap()
  with patch.object(M,'sync',side_effect=ValueError('late movement')):
   with self.assertRaisesRegex(ValueError,'late movement'):self.e.approach(self.a,self.t)
  self.assertEqual(before,self.snap())
 def test_dismount_keeps_current_actual_positions_and_drops_only_rider_load(self):
  self.board();origin=self.p.pos;LOAD.set_carried(self.e,self.p,[{'id':'object/small-bag','weight_kg':1}],'actual nonrider load')
  self.e.dismount(self.a,destination=(3,3),reason='actual dismount destination')
  self.assertEqual(self.p.pos,origin);self.assertEqual(self.a.pos,(3,3));self.assertEqual(LOAD.load(self.p)['weight_kg'],1)
 def test_dangling_managed_reference_and_tampered_policy_cannot_be_saved(self):
  self.native();self.a.spec[M.CONTRACT]['policy']['movement']['maximum_distance']=999
  self.assertFalse(self.e.validate_state()['valid'])
  with self.assertRaises(StateCodecError):self.e.export_state()
 def test_saved_used_movement_cannot_be_reset_to_zero(self):
  self.native();self.begin(self.a);self.e.approach(self.a,self.t);getattr(self.p,M.POOL)['used']=0
  self.assertFalse(self.e.validate_state()['valid'])
  with self.assertRaises(StateCodecError):self.e.export_state()
 def test_confusion_actual_self_hit_uses_loss_and_retention_even_below_damage_threshold(self):
  self.native();before=self.snap()
  with self.assertRaisesRegex(ValueError,'current confusion'):self.e.confusion_self_hit(self.p,1)
  self.assertEqual(before,self.snap());self.e.gm.add_condition(self.p,'혼란',reason='actual confused mount')
  before=self.p.hp;out=self.e.confusion_self_hit(self.p,1);self.assertEqual(self.p.hp,before-1)
  self.assertEqual(out['retention'][0]['event'],'confusion');self.assertIsNotNone(out['retention'][0]['check'])
 def test_damage_and_forced_retention_late_failure_roll_back_entire_native_event(self):
  self.native();before=self.snap()
  for produce in (lambda:self.e.take_damage(self.a,(self.a.base_max_hp+3)//4),lambda:FORCE.displace(self.e,self.t,self.p,direction=(1,0),distance=1,source='gm/actual push')):
   with patch.object(M,'retain',side_effect=ValueError('late retention')):
    with self.assertRaisesRegex(ValueError,'late retention'):produce()
   self.assertEqual(before,self.snap())
 def test_physical_rider_weight_cannot_use_remote_telekinetic_load_table(self):
  self.board();self.p.spec['_carried_load']={'mode':'telekinetic','objects':[{'id':'remote/bag','weight_kg':1}]}
  with self.assertRaisesRegex(ValueError,'separate load policy'):LOAD.load(self.p)


if __name__=='__main__':unittest.main()
