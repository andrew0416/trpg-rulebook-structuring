"""Whole Warper acquisition and the native consumers of all six learned Moves."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import warper as WP,trainer_feature_acquisition as ACQ,state_grants as G
import world_entities as W,state_codec as CODEC,combat_timing as TIME,action_points as AP
import frequency as F,movement_actions as MOVEMENT,move_completion as MC


class WarperTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old);self.setup()
 def setup(self,rank=6,teleport=0):
  self.e=Engine(self.rules,seed=32373295);self.e.grid=Grid(40,24)
  self.a=self.add('Warper',(2,2),rank=rank,teleport=teleport);self.b=self.add('foe',(5,2),side='foes');self.c=self.add('ally',(3,2))
 def add(self,name,pos,*,side='party',rank=6,teleport=0,kind='trainer'):
  movement={'land':8,'swim':4,'sky':0,'levitate':0,'power':4}
  if teleport:movement['teleport']=teleport
  spec=dict(name=name,kind=kind,level=30,size='중형',stats={'hp':70,'atk':15,'def':15,'spa':20,'spd':15,'spe':30},moves=['move/몸통박치기','move/물대포','move/울음소리'],types=['노말'],abilities=[],classes=[],feats=[],edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':'에스퍼'},skills={'교활':rank,'집중':3,'전투':2,'육상':3,'곡예':3,'직감':3,'오컬트학':3},movement=movement,movement_basis='base',weight_kg=30,exp_bank=100,items={})
  a=Combatant(self.rules,spec);self.e.gm.add_combatant(a,pos=pos,side=side,reason='actual Warper scene participant');prepare_body(self.e,a,size='중형',offsets=[(0,0)],reason='actual complete body');return a
 def acquire(self,u=WP.CLASS,*,actor=None,request=None):
  a=actor or self.a;return ACQ.acquire_static(self.e,a,u,acquisition_request_id=request or a.entity_id+'/'+u)
 def family(self,u,*,actor=None):
  a=actor or self.a
  for p in WP.PARENTS[u]:
   if not WP.acquired(a,p):self.family(p,actor=a)
  if not WP.acquired(a,u):self.acquire(u,actor=a)
 def close(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
 def begin(self,a=None,count=60):self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(a or self.a,initiative_count=count)
 def turn(self,a,count=50):self.close();self.e.start_of_turn(a,initiative_count=count)
 def reject(self,fn,reason=None):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[a.entity_id for a in (self.a,self.b,self.c)];self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)));self.a,self.b,self.c=[W.actor_index(self.e)[u] for u in ids]
 def used(self,a,source):return F.state(a)['activations'].get(source,{}).get('used',0)
 def teleport(self,destination,**options):return self.e.warper_teleport(self.a,destination,surface_contact=True,reason='observed actual destination',**options)
 def completion(self,a,mid):return [r for r in self.e._move_completions.values() if r['actor'] is a and r['move_id']==mid][-1]
 def needs_item(self,*args):return {'common':True,'normally_possessed':True,'needed_now':True,'reason':'actual wound and no medicine remaining'}
 def event(self,outcomes=None,kind='in_world_random'):
  return lambda e,a:{'id':'world:coin:1','kind':kind,'outcomes':outcomes or ['heads','tails'],'reason':'GM observes this actual in-world random event'}
 def retrain(self,u):
  import trainer_retraining as R
  owned=R._owned(self.a);sources={v:R.owned_source(self.e,self.a,v) for v in owned};required=R._native_dependencies(self.e,self.a,owned)
  deps={sid:[sources[p] for p in required.get(v,[])] for v,sid in sources.items() if v!=u}
  return self.e.retrain_trainer_source(self.a,u,request_id='retire:'+u,reason='actual retraining consultation',gm_decision={'allowed':True,'reason':'approved'},retained_dependencies=deps)

 def test_all_seven_actual_acquisitions_speed_pairs_no_auto_siblings_and_restore(self):
  before=self.a.stats['spe'];self.acquire();self.assertEqual(len(WP.records(self.a,active=True)),1);self.assertEqual(self.a.stats['spe'],before+1);self.assertNotIn(WP.TELEPORT,self.a.moves);self.assertIn('확률제어',self.a.abilities)
  for u in WP.FEATURES:self.family(u)
  self.assertEqual(len(WP.records(self.a,active=True)),7);self.assertEqual(self.a.stats['spe'],before+7);self.assertTrue({WP.TELEPORT,WP.SWITCH,WP.GRAVITY,WP.TRICK,WP.HEAL_BLOCK,WP.COAT}<=set(self.a.moves))
  __import__('items').register_feats(self.e,self.a);self.assertEqual(self.a.stats['spe'],before+7);self.restore();self.valid()

 def test_exact_psychic_guile_both_parents_and_not_ranked(self):
  self.setup(rank=2);self.reject(lambda:self.acquire(),'Guile|rank');self.setup(rank=3);self.a.spec['edge_choices']={'edge/원소-교감':'불꽃'};self.reject(lambda:self.acquire(),'Psychic|Connection')
  self.setup(rank=3);self.reject(lambda:self.acquire(WP.SPACE),'parent');self.family(WP.GROUND);self.reject(lambda:self.acquire(WP.ENERGY),'parent');self.family(WP.ENERGY);self.reject(lambda:self.acquire(WP.FARCAST),'rank')
  self.setup(rank=5);self.family(WP.FARCAST);self.reject(lambda:self.acquire(WP.WARPED),'rank');self.reject(lambda:ACQ.acquire_static(self.e,self.a,WP.REALITY,rank=1,acquisition_request_id='invented-ranked'),'rank|Ranked')

 def test_while_owned_pairs_speed_probability_and_independent_baseline_survive_revoke(self):
  self.family(WP.SPACE);__import__('state_grants').replace_baseline(self.e,self.a,'moves',list(self.a.spec['moves'])+[WP.TELEPORT]);before=self.a.stats['spe']
  self.retrain(WP.SPACE)
  self.assertIn(WP.TELEPORT,self.a.moves);self.assertNotIn(WP.SWITCH,self.a.moves);self.assertEqual(self.a.stats['spe'],before-1);self.restore();self.valid()
  self.setup();self.acquire();before=self.a.stats['spe'];self.retrain(WP.CLASS);self.assertNotIn('확률제어',self.a.abilities);self.assertEqual(self.a.stats['spe'],before-1);self.restore();self.valid()

 def test_trainer_learned_missing_four_and_existing_plus_four_actual_transfer(self):
  for base,expected in ((0,4),(5,9)):
   with self.subTest(base=base):
    self.setup(teleport=base);self.family(WP.SPACE);self.assertEqual(MOVEMENT.capabilities(self.e,self.a)['teleport'],expected);self.begin();result=self.teleport((2+expected,2));self.assertEqual(result['position'],(2+expected,2));self.assertEqual(self.a.budget['shift'],0);self.reject(lambda:self.teleport((2,2)),'once|round');self.restore();self.valid()

 def test_trainer_teleport_actual_los_surface_sprint_and_adopted_no_aoo(self):
  self.family(WP.SPACE);self.begin();self.reject(lambda:self.teleport((7,2)),'capability');self.reject(lambda:self.e.warper_teleport(self.a,(4,3),surface_contact=False,reason='air destination'),'Sky|Levitate')
  self.e.gm.set_position(self.b,(1,2),reason='adjacent actual foe');hp=self.a.hp;self.teleport((4,3));self.assertFalse(self.b.aoo_used);self.assertEqual(self.a.hp,hp)
  self.assertEqual(WP.teleport_aoo_policy(self.e)['authority'],'adopted_dataninja_faq_p18');self.valid()

 def test_farcast_core_triple_actual_value_one_use_and_does_not_grant_transporter(self):
  self.family(WP.FARCAST);self.assertNotIn('트랜스포터 [Playtest]',self.a.abilities);self.assertNotIn(WP.TRANSPORTER,self.a.abilities);self.begin();self.teleport((14,2),triple=True);self.assertEqual(self.a.pos,(14,2));self.assertEqual(self.used(self.a,WP.FARCAST),1);self.assertEqual(MOVEMENT.capabilities(self.e,self.a)['teleport'],4);self.restore();self.valid()

 def test_farcast_touching_willing_one_partner_one_use_two_modes_two_uses(self):
  for triple,dest,partner_dest,uses in ((False,(6,3),(6,2),1),(True,(13,3),(13,2),2)):
   with self.subTest(triple=triple):
    self.setup();self.family(WP.FARCAST);self.begin();self.teleport(dest,triple=triple,partner=self.c,willing=True,touching=True,partner_destination=partner_dest);self.assertEqual((self.a.pos,self.c.pos),(dest,partner_dest));self.assertEqual(self.used(self.a,WP.FARCAST),uses);self.restore();self.valid()

 def test_farcast_touching_consent_placement_quota_reject_atomically(self):
  self.family(WP.FARCAST);self.begin();self.reject(lambda:self.teleport((6,3),partner=self.c,willing=True,partner_destination=(6,2)),'touching');self.reject(lambda:self.teleport((6,3),partner=self.c,touching=True,partner_destination=(6,2)),'willing');self.reject(lambda:self.teleport((6,3),partner=self.c,willing=True,touching=True,partner_destination=(10,2)),'adjacent|allowance')
  self.teleport((13,3),triple=True,partner=self.c,willing=True,touching=True,partner_destination=(13,2));self.begin();self.reject(lambda:self.teleport((24,3),triple=True,partner=self.c,willing=True,touching=True,partner_destination=(24,2)),'frequency')

 def test_teleport_move_scene_standard_native_completion_and_final_position(self):
  self.family(WP.SPACE);self.begin();self.teleport((6,3),move=True);self.assertEqual(self.a.pos,(6,3));self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['shift'],1);self.assertEqual(self.completion(self.a,WP.TELEPORT)['phase'],'complete');self.assertEqual(self.a.move_uses[WP.TELEPORT],1);self.valid()

 def test_teleport_move_interrupt_single_target_miss_real_destination_and_debt(self):
  self.family(WP.SPACE);self.begin();self.e.arm_warper_move(self.a,WP.TELEPORT,destination=(2,6),surface_contact=True,reason='actual legal escape');hp=self.a.hp;self.turn(self.b)
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,'move/물대포',set_damage=True)
  self.assertEqual(self.a.pos,(2,6));self.assertEqual(self.a.hp,hp);self.assertFalse(MC.recipient_result(self.completion(self.b,'move/물대포'),self.a)['hit']);self.assertEqual(self.a.move_uses[WP.TELEPORT],1);self.restore();self.valid()

 def test_ally_switch_interrupt_willing_six_metres_and_actual_recipient_exchange(self):
  self.family(WP.SPACE);self.begin();origin=self.a.pos;ally_origin=self.c.pos;self.e.arm_warper_move(self.a,WP.SWITCH,ally=self.c,willing=True);self.turn(self.b);before=(self.a.hp,self.c.hp)
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.c,'move/물대포',set_damage=True)
  self.assertEqual((self.a.pos,self.c.pos),(ally_origin,origin));self.assertLess(self.a.hp,before[0]);self.assertEqual(self.c.hp,before[1]);row=self.completion(self.b,'move/물대포');self.assertTrue(MC.recipient_result(row,self.a)['hit']);self.assertEqual(self.a.move_uses[WP.SWITCH],1);self.restore();self.valid()

 def test_ally_switch_other_target_direction_and_own_turn_consent_range_rejection(self):
  self.family(WP.SPACE);self.begin();self.reject(lambda:self.e.arm_warper_move(self.a,WP.SWITCH,ally=self.c,willing=False),'willing');self.e.gm.set_position(self.c,(10,2),reason='outside six metres');self.reject(lambda:self.e.arm_warper_move(self.a,WP.SWITCH,ally=self.c,willing=True),'six|range')
  self.e.gm.set_position(self.c,(3,2),reason='actual nearby ally');self.e.arm_warper_move(self.a,WP.SWITCH,ally=self.c,willing=True);self.turn(self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,'move/물대포',set_damage=True)
  self.assertEqual(self.a.hp,hp);self.assertTrue(MC.recipient_result(self.completion(self.b,'move/물대포'),self.c)['hit']);self.valid()
  self.setup();self.family(WP.WARPED);self.e.gm.set_position(self.b,(4,2),reason='foe adjacent to ordinary Ally Switch final square');self.begin();ap=AP.available(self.a)
  self.reject(lambda:self.e.warper_ally_switch(self.a,self.c,willing=False,warped=True),'willing')
  self.e.warper_ally_switch(self.a,self.c,willing=True,warped=True)
  self.assertEqual((self.a.pos,self.c.pos),((3,2),(2,2)));self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['swift'],0);self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.a.move_uses[WP.SWITCH],1);self.assertEqual(WP.evasion(self.b),-3);self.assertEqual(self.completion(self.a,WP.SWITCH)['phase'],'complete');self.reject(lambda:self.e.warper_ally_switch(self.a,self.c,willing=True),'frequency|Scene|scene|move|기술');self.restore();self.valid()

 def test_magic_coat_no_damage_dice_uses_coater_as_user_original_user_as_target(self):
  self.family(WP.ENERGY);self.begin();self.e.arm_warper_move(self.a,WP.COAT);self.turn(self.b)
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,'move/울음소리')
  self.assertEqual(self.a.stages['atk'],0);self.assertEqual(self.b.stages['atk'],-1);self.assertEqual(self.a.move_uses[WP.COAT],1);row=self.completion(self.b,'move/울음소리');self.assertEqual(row['warper_reflection']['user_id'],self.a.entity_id);self.assertEqual(row['warper_reflection']['target_id'],self.b.entity_id);self.restore();self.valid()

 def test_magic_coat_cannot_reflect_damaging_move_and_preserves_daily_use(self):
  self.family(WP.ENERGY);self.begin();self.e.arm_warper_move(self.a,WP.COAT);self.turn(self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,'move/물대포',set_damage=True)
  self.assertLess(self.a.hp,hp);self.assertEqual(self.a.move_uses.get(WP.COAT,0),0);self.valid()

 def test_warped_teleporter_final_adjacent_all_foes_exact_two_ap_and_swift(self):
  self.family(WP.WARPED);other=self.add('second foe',(8,4),side='foes');self.e.gm.set_position(self.b,(6,4),reason='foe at final square');self.e.gm.set_position(self.c,(7,3),reason='adjacent ally excluded');self.begin();ap=AP.available(self.a)
  result=self.teleport((7,4),triple=True,warped=True);self.assertEqual(set(result['warped_targets']),{self.b.entity_id,other.entity_id});self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.a.budget['swift'],0);self.assertEqual(WP.evasion(self.b),-3);self.assertEqual(WP.evasion(self.c),0);self.assertEqual(WP.evasion(self.a),0);self.restore();self.valid()

 def test_warped_actual_teleport_does_not_invent_foes_from_absent_sides(self):
  for role in ('source','target'):
   with self.subTest(role=role):
    self.setup();self.family(WP.WARPED)
    self.e.gm.set_position(self.b,(6,4),reason='actual adjacent candidate after teleport')
    unknown=self.a if role=='source' else self.b
    del unknown.side;unknown.spec.pop('side',None)
    self.begin();ap=AP.available(self.a)
    result=self.teleport((6,3),triple=True,warped=True)
    self.assertEqual(result['warped_targets'],[])
    self.assertEqual(AP.available(self.a),ap-2)
    self.assertEqual(WP.evasion(self.b),0)
    self.restore();self.valid()

 def test_warped_full_round_evasion_and_next_owner_turn_end_shift_protection_differ(self):
  self.family(WP.WARPED);self.e.gm.set_position(self.b,(6,4),reason='adjacent final foe');self.begin();self.teleport((6,3),triple=True,warped=True);self.assertTrue(WP.prevents_aoo(self.b,self.a,'인접 칸 밖으로 이동'));self.assertFalse(WP.prevents_aoo(self.b,self.c,'인접 칸 밖으로 이동'));self.assertFalse(WP.prevents_aoo(self.b,self.a,'인접하지 않은 대상에게 원거리 공격'))
  self.close();self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(60);self.assertEqual(WP.evasion(self.b),0);self.assertTrue(WP.prevents_aoo(self.b,self.a,'인접 칸 밖으로 이동'));self.e.start_of_turn(self.a,initiative_count=60)
  hp=self.a.hp;self.e.approach(self.a,self.c);self.assertEqual(self.a.budget['shift'],0);self.assertFalse(self.e.adjacent(self.a,self.b));self.assertFalse(self.b.aoo_used);self.assertEqual(self.a.hp,hp)
  self.close();self.assertFalse(WP.prevents_aoo(self.b,self.a,'인접 칸 밖으로 이동'));self.restore();self.valid()

 def test_warped_requires_actual_teleporter_or_switch_own_swift_and_ap(self):
  self.family(WP.WARPED);self.begin();self.reject(lambda:self.teleport((6,3),move=True,warped=True),'Teleporter|Ally Switch');self.turn(self.b);self.reject(lambda:self.teleport((6,3),warped=True),'turn|Swift|shift');self.assertEqual(self.a.pos,(2,2))

 def test_gravity_and_heal_block_from_actual_acquired_pair_native_consumers(self):
  self.family(WP.ENERGY);self.begin();self.e.use_move(self.a,self.a,WP.GRAVITY);self.assertTrue(__import__('field_effects').active(self.e,'왜곡'));self.begin()
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.b,WP.HEAL_BLOCK)
  self.assertTrue(__import__('healing_blocks').blocked(self.b));self.assertIn(WP.GRAVITY,self.a.moves);self.assertIn(WP.HEAL_BLOCK,self.a.moves);self.valid()

 def test_probability_control_skill_final_dc_result_scene_cost_and_discoverable_residue(self):
  self.acquire();self.begin();self.e.arm_probability_control(self.a,self.c,purpose='skill',decision=lambda first:True,reroll_fixed=[6,6,6]);result=self.e.skill_check(self.c,'집중',15,fixed=[1,1,1]);self.assertTrue(result[0]);self.assertEqual(result[1],18);self.assertEqual(self.used(self.a,WP.PROBABILITY),1)
  self.assertEqual(self.e.psychic_residue(self.b,reason='GM observes unsuccessful trace search',observe=lambda *args:False),[])
  traces=self.e.psychic_residue(self.b,reason='actual Psychic trace search succeeded',observe=lambda *args:True);self.assertTrue(any(t['source']==WP.PROBABILITY and t['actor_id']==self.a.entity_id for t in traces));self.restore();self.valid()

 def test_probability_control_accuracy_and_damage_actual_final_native_results(self):
  for purpose in ('accuracy','damage'):
   with self.subTest(purpose=purpose):
    self.setup();self.acquire();self.begin();self.e.arm_probability_control(self.a,self.a,purpose=purpose,decision=lambda first:True,reroll_fixed=[20] if purpose=='accuracy' else None)
    with patch.object(Engine,'d20',return_value=1 if purpose=='accuracy' else 18):self.e.use_move(self.a,self.b,'move/물대포')
    self.assertLess(self.b.hp,self.b.max_hp);self.assertEqual(self.used(self.a,WP.PROBABILITY),1);self.valid()

 def test_probability_any_declared_native_pool_not_just_skill_or_d20_and_ally_boundary(self):
  self.acquire();self.begin();self.reject(lambda:self.e.arm_probability_control(self.a,self.b,purpose='external_pool',decision=lambda x:True),'self|ally')
  self.e.arm_probability_control(self.a,self.c,purpose='external_pool',decision=lambda x:True,reroll_fixed=[8,8]);result=self.e.resolve_native_pool(self.c,purpose='external_pool',source=WP.PROBABILITY,count=2,sides=8,fixed=[1,1]);self.assertEqual(result['faces'],[8,8]);self.assertEqual(result['total'],16);self.assertEqual(self.used(self.a,WP.PROBABILITY),1);self.restore();self.valid()

 def test_probability_decline_no_cost_no_residue_and_second_activation_denied(self):
  self.acquire();self.begin();self.e.arm_probability_control(self.a,self.a,purpose='skill',decision=lambda first:False);self.e.skill_check(self.a,'집중',10,fixed=[1,1,1]);self.assertEqual(self.used(self.a,WP.PROBABILITY),0)
  self.e.arm_probability_control(self.a,self.a,purpose='skill',decision=lambda first:True,reroll_fixed=[6,6,6]);self.e.skill_check(self.a,'집중',10,fixed=[1,1,1]);self.reject(lambda:self.e.arm_probability_control(self.a,self.a,purpose='skill',decision=lambda first:True),'frequency|Scene|scene')

 def test_reality_exact_two_gm_world_outcomes_consumed_and_gameplay_dice_excluded(self):
  self.family(WP.REALITY);self.begin()
  def apply(e,a,uid,value):
   target=W.actor_index(e)[self.c.entity_id];e.gm.set_position(target,(4,3) if value=='heads' else (4,4),reason='actual selected world outcome');return {'position':list(target.pos)}
  self.reject(lambda:self.e.reality_bender_event(self.a,choose=0,provide=self.event(kind='gameplay_dice'),apply_outcome=apply),'gameplay');self.reject(lambda:self.e.reality_bender_event(self.a,choose=0,provide=self.event(['a','b','c']),apply_outcome=apply),'exactly two')
  result=self.e.reality_bender_event(self.a,choose=1,provide=self.event(),apply_outcome=apply);self.assertEqual(result['selected'],'tails');self.assertEqual(self.c.pos,(4,4));self.assertEqual(self.used(self.a,WP.REALITY),1);self.restore();self.valid()

 def test_reality_created_needed_physical_item_immediately_consumed_cannot_store(self):
  self.family(WP.REALITY);self.begin();self.e.gm.set_hp(self.c,self.c.hp-20,reason='actual wound');hp=self.c.hp;result=self.e.reality_bender_item(self.a,'item/상처약',self.c,instance_id='reality:potion:1',provide=self.needs_item)
  self.assertGreater(self.c.hp,hp);obj=self.e._physical_objects[result['instance_id']];self.assertTrue(obj['consumed']);self.assertNotIn('equipped_by',obj);self.assertEqual(self.used(self.a,WP.REALITY),1);self.restore();self.valid()

 def test_reality_existing_item_unneeded_uncommon_price_and_native_failure_atomic(self):
  self.family(WP.REALITY);self.begin();self.a.spec['items']['item/상처약']=1;self.reject(lambda:self.e.reality_bender_item(self.a,'item/상처약',self.c,instance_id='existing',provide=self.needs_item),'none|available');self.a.spec['items'].clear()
  self.reject(lambda:self.e.reality_bender_item(self.a,'item/상처약',self.c,instance_id='unneeded',provide=lambda *args:dict(self.needs_item(),needed_now=False)),'needed');self.reject(lambda:self.e.reality_bender_item(self.a,'item/좋은상처약',self.c,instance_id='over-core-price',provide=self.needs_item),'price')
  with patch.object(Engine,'use_item',side_effect=ValueError('late actual consumption failure')):self.reject(lambda:self.e.reality_bender_item(self.a,'item/상처약',self.c,instance_id='failed',provide=self.needs_item),'late actual')

 def test_reality_local_csv515_price_and_outcome_wording_is_independent_not_official(self):
  self.family(WP.REALITY);self.begin();self.e.gm.set_hp(self.c,self.c.hp-35,reason='needs stronger actual medicine');result=self.e.reality_bender_item(self.a,'item/좋은상처약',self.c,instance_id='local:medicine',provide=self.needs_item,source='local_csv515');self.assertEqual(result['source_variant'],'local_csv515');self.assertEqual(self.used(self.a,WP.REALITY),1)
  self.setup();self.family(WP.REALITY);self.begin();result=self.e.reality_bender_event(self.a,choose=2,provide=self.event(['a','b','c']),apply_outcome=lambda e,a,u,v:{'actual':v},source='local_csv515');self.assertEqual(result['selected'],'c');self.valid()

 def test_farcast_actual_teleport_move_triples_value_with_native_move_and_feature_uses(self):
  self.family(WP.FARCAST);self.begin();self.teleport((14,3),move=True,triple=True);self.assertEqual(self.a.pos,(14,3));self.assertEqual(self.a.move_uses[WP.TELEPORT],1);self.assertEqual(self.used(self.a,WP.FARCAST),1);self.assertEqual(self.completion(self.a,WP.TELEPORT)['phase'],'complete');self.restore();self.valid()

 def test_official_transporter_ability_separate_from_core_farcast_and_local_csv_grant(self):
  self.rules=Rules(ROOT,ruleset='all');self.setup();self.family(WP.SPACE)
  self.e.gm.set_ability(self.a,WP.TRANSPORTER,reason='actually acquired official February2016 Teleport Connection Ability')
  self.begin();self.teleport((13,3),triple=True,partner=self.c,willing=True,touching=True,partner_destination=(13,2),source=WP.TRANSPORTER);self.assertEqual(self.used(self.a,WP.TRANSPORTER),2);self.assertEqual(self.used(self.a,WP.FARCAST),0);self.assertFalse(WP.acquired(self.a,WP.FARCAST));self.restore();self.valid()
  self.setup();self.a.spec['feats']=[WP.FARCAST];__import__('items').register_feats(self.e,self.a);self.assertTrue(__import__('ability_transitions').active(self.a,WP.TRANSPORTER));self.assertFalse(WP.acquired(self.a,WP.FARCAST));self.assertFalse(WP.policy(self.e)['independent_sources']['official_feb2016_transporter']['replaces_core_farcast_class_feature'])

 def test_actual_trick_exchanges_accessories_and_both_targets_must_hit(self):
  import items
  self.family(WP.GROUND)
  # Existing actual equipment owner installs the Accessory slot; the exchange
  # must preserve that slot and its source effects on the receiving Trainer.
  for actor,uid in ((self.a,'accessory:a'),(self.c,'accessory:c')):
   W.register_object(self.e,uid,location={'kind':'unknown'},reason='observed actual worn accessory',kind='item_instance',item_rule_id='item/달인의띠',owner_id=actor.entity_id);items.register_item(self.e,actor,'달인의띠',source_instance_id=uid)
  self.begin();result=self.e.use_move_on(self.a,self.a,WP.TRICK,self.e.everyone,equipment_options={'targets':[self.a,self.c],'consenting':[self.c]})
  history=self.a.custom_conditions['_equipment_trick_history'][-1];self.assertTrue(all(history['hits'].values()));self.assertTrue(history['result']['changed']);self.assertEqual(items.equipment_options(self.a,('장신구',))[0]['instance_id'],'accessory:c');self.assertEqual(items.equipment_options(self.c,('장신구',))[0]['instance_id'],'accessory:a');self.restore();self.valid()

 def test_teleport_area_uses_immutable_aim_and_actual_final_membership(self):
  self.family(WP.SPACE);self.e.gm.set_move(self.b,'move/파도타기',reason='actual learned area reference');self.e.gm.set_position(self.b,(1,2),reason='original actual line origin');self.begin();self.e.arm_warper_move(self.a,WP.TELEPORT,destination=(2,6),surface_contact=True,reason='escape actual immutable line');self.turn(self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.b,self.a,'move/파도타기',[self.a],aim=(7,2),set_damage=True)
  self.assertEqual(self.a.pos,(2,6));self.assertEqual(self.a.hp,hp);self.assertFalse(MC.recipient_result(self.completion(self.b,'move/파도타기'),self.a)['hit']);self.restore();self.valid()

 def test_warped_ally_switch_offturn_cannot_invent_an_extra_swift_action(self):
  self.family(WP.WARPED);self.begin();self.e.arm_warper_move(self.a,WP.SWITCH,ally=self.c,willing=True,warped=True);self.turn(self.b)
  with patch.object(Engine,'d20',return_value=18):self.reject(lambda:self.e.use_move(self.b,self.a,'move/물대포',set_damage=True),'swift|Swift|action|행동')

 def test_probability_save_preserves_offer_but_requires_fresh_live_observation_authentication(self):
  self.acquire();self.begin();self.e.arm_probability_control(self.a,self.c,purpose='external_pool',decision=lambda first:True,reroll_fixed=[8,8]);self.restore();self.reject(lambda:self.e.resolve_native_pool(self.c,purpose='external_pool',source=WP.PROBABILITY,count=2,sides=8,fixed=[1,1]),'authentication|live');self.e.arm_probability_control(self.a,self.c,purpose='external_pool',decision=lambda first:True,reroll_fixed=[8,8]);self.assertEqual(self.e.resolve_native_pool(self.c,purpose='external_pool',source=WP.PROBABILITY,count=2,sides=8,fixed=[1,1])['total'],16);self.valid()

 def test_ordered_multiple_targets_later_recipient_can_react_on_same_move_completion(self):
  self.family(WP.SPACE);self.e.gm.set_move(self.b,'move/스톤샤워',reason='actual learned ranged Blast');self.e.gm.set_position(self.c,(3,3),reason='first actual target within original Blast');self.begin();self.e.arm_warper_move(self.a,WP.TELEPORT,destination=(2,6),surface_contact=True,reason='later recipient actual escape');self.turn(self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.b,self.c,'move/스톤샤워',[self.c,self.a],aim=(2,2),set_damage=True)
  row=self.completion(self.b,'move/스톤샤워');self.assertEqual(len(row['results']),2);self.assertEqual(self.a.pos,(2,6));self.assertEqual(self.a.hp,hp);self.assertFalse(MC.recipient_result(row,self.a)['hit']);self.assertEqual(row['phase'],'complete');self.restore();self.valid()

 def test_no_explicit_aim_blast_retains_original_area_after_teleport(self):
  self.family(WP.SPACE);self.e.gm.set_move(self.b,'move/스톤샤워',reason='actual learned ranged Blast');self.begin();self.e.arm_warper_move(self.a,WP.TELEPORT,destination=(2,6),surface_contact=True,reason='escape original Blast');self.turn(self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.b,self.a,'move/스톤샤워',[self.a],set_damage=True)
  row=self.completion(self.b,'move/스톤샤워');self.assertEqual(self.a.pos,(2,6));self.assertEqual(self.a.hp,hp);self.assertFalse(MC.recipient_result(row,self.a)['hit']);self.restore();self.valid()

 def test_reality_metronome_world_result_and_daily_no_second_consumption(self):
  self.family(WP.REALITY);self.begin();result=self.e.reality_bender_event(self.a,choose=1,provide=self.event(['move/물대포','move/울음소리'],kind='metronome'),apply_outcome=lambda e,a,u,v:{'actual_metronome_result':v});self.assertEqual(result['selected'],'move/울음소리');self.reject(lambda:self.e.reality_bender_event(self.a,choose=0,provide=self.event(),apply_outcome=lambda *args:{'consumed':True}),'frequency');self.valid()


if __name__=='__main__':unittest.main()
