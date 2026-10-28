"""Whole printed Telekinetic class over actual native producers and state."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import telekinetic as TK,trainer_feature_acquisition as ACQ,state_grants as G
import world_entities as W,state_codec as CODEC,combat_timing as TIME,action_points as AP
import optional_weapon_framework as FW,weapon_actions as WA,combat_move_reactions as REACTIONS
import move_completion as MC,movement_actions as MOVEMENT,ability_transitions as AB

class TelekineticTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old);self.setup()
 def setup(self,rank=6):
  self.e=Engine(self.rules,seed=31243181);self.e.grid=Grid(32,24)
  self.a=self.add('Telekinetic',(2,2),rank=rank);self.b=self.add('foe',(6,2),side='foes');self.c=self.add('ally',(3,3))
 def add(self,name,pos,*,side='party',rank=6):
  spec=dict(name=name,kind='trainer',level=30,size='중형',stats={'hp':70,'atk':12,'def':15,'spa':40,'spd':15,'spe':30},moves=['move/몸통박치기','move/물대포','move/지진'],types=['노말'],abilities=[],classes=[],feats=[],edges=['edge/원소-교감','edge/강철의-정신'],edge_choices={'edge/원소-교감':'에스퍼'},skills={'집중':rank,'전투':2,'육상':3,'곡예':3,'은신':3,'오컬트학':3,'직감':3},movement={'land':8,'swim':4,'sky':6,'levitate':0,'power':4},movement_basis='current',weight_kg=30,exp_bank=100,items={})
  a=Combatant(self.rules,spec);self.e.gm.add_combatant(a,pos=pos,side=side,reason='actual Telekinetic scene participant');prepare_body(self.e,a,size='중형',offsets=[(0,0)],reason='observed body');return a
 def acquire(self,u=TK.CLASS,*,actor=None,selection=None,request=None):
  a=actor or self.a
  return ACQ.acquire_static(self.e,a,u,selection=selection,acquisition_request_id=request or a.entity_id+'/'+u)
 def family(self,u,*,selection=TK.LEVITATE,actor=None):
  a=actor or self.a
  for p in TK.PARENTS[u]:
   if not TK.acquired(a,p):self.family(p,selection=selection,actor=a)
  if not TK.acquired(a,u):self.acquire(u,actor=a,selection=selection if u==TK.POWER else None)
 def close(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
 def begin(self,a=None,count=60):self.close();self.e.start_round(self.e.everyone);self.e.start_of_turn(a or self.a,initiative_count=count)
 def turn(self,a,count=50):self.close();self.e.start_of_turn(a,initiative_count=count)
 def reject(self,fn,reason=None):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[a.entity_id for a in (self.a,self.b,self.c)];self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)));self.a,self.b,self.c=[W.actor_index(self.e)[u] for u in ids]
 def completion(self,a,mid):return [r for r in self.e._move_completions.values() if r['actor'] is a and r['move_id']==mid][-1]
 def decision(self,value):
  return {'value':value,'reason':'explicit optional table override of literal Core caster rule; not an official edition','scope':self.e.telekinesis_evasion_policy(adjudication=True)['decision_scope']}
 def cast(self,mid=TK.LIFT,*,target=None,overload=False,owner='lifted_target',segments=None,face=18):
  self.family(TK.OVERLOAD if overload else TK.OMEGA if mid in (TK.LIFT,TK.PSYCHIC) else TK.ALPHA);self.begin()
  with patch.object(Engine,'d20',return_value=face):
   self.e.use_telekinetic_move(self.a,target or (self.a if mid==TK.BARRIER else self.b),mid,overload=overload,evasion_owner=self.decision(owner) if mid==TK.LIFT else None,segments=segments,push_direction=(0,1) if mid==TK.PSYCHIC else None)
  row=self.completion(self.a,mid);self.assertEqual(row['phase'],'complete');return row
 def object(self,uid,*,cell=(7,2),weight=1,item=None):
  W.register_object(self.e,uid,location={'kind':'grid','cell':cell},weight_kg=weight,reason='actual weighed remote body',kind='item_instance' if item else 'physical_object',item_rule_id=item,owner_id=self.a.entity_id)
  return uid
 def combat(self):
  self.family(TK.COMBAT);self.begin();self.e.activate_pk_combat(self.a,instance_id='actual-pk-binding')
 def lift_objects(self,ids):return self.e.telekinetic_lift(self.a,ids,action_cost='shift',reason='GM chooses actual lifting activity Shift')
 def weapon(self,kind='소형 근접무기',*,moves=(),weight=1):
  uid=self.object('remote:'+str(len(self.e._physical_objects)),weight=weight);self.lift_objects([uid]);FW.observe_weapon(self.e,self.a,uid,name=uid,kind=kind,grade='좋음',arcane=False,metal=False,moves=list(moves),reason='observed actual remote weapon');key=self.e.equip_telekinetic_weapon(self.a,uid)
  return uid,key

 def test_seven_independent_acquisitions_spa_no_auto_siblings_and_restore(self):
  before=self.a.stats['spa'];self.acquire();self.assertEqual(len(TK.records(self.a,active=True)),1);self.assertEqual(self.a.stats['spa'],before+1);self.assertFalse(TK.acquired(self.a,TK.ALPHA));self.assertNotIn(TK.KINESIS,self.a.moves)
  for u in TK.FEATURES:self.family(u)
  self.assertEqual(len(TK.records(self.a,active=True)),7);self.assertEqual(self.a.stats['spa'],before+7);self.assertTrue({TK.KINESIS,TK.BARRIER,TK.PSYCHIC,TK.LIFT}<=set(self.a.moves));self.assertTrue(AB.active(self.a,TK.LEVITATE))
  __import__('items').register_feats(self.e,self.a);self.assertEqual(self.a.stats['spa'],before+7);self.restore();self.valid()

 def test_prerequisites_edges_parents_exact_rank_and_no_ranked_acquisition(self):
  with self.assertRaisesRegex(ValueError,'Iron Mind requires Novice Focus'):self.setup(rank=2)
  self.setup(rank=3);self.a.spec['edge_choices']={'edge/원소-교감':'불꽃'};self.reject(lambda:self.acquire(),'Connection|Iron Mind')
  self.setup(rank=3);self.reject(lambda:self.acquire(TK.ALPHA),'parent');self.family(TK.ALPHA);self.reject(lambda:self.acquire(TK.COMBAT),'rank');self.reject(lambda:self.acquire(TK.OMEGA),'rank')
  self.setup(rank=4);self.family(TK.COMBAT);self.reject(lambda:self.acquire(TK.BURST),'rank');self.setup(rank=5);self.family(TK.OMEGA);self.reject(lambda:self.acquire(TK.OVERLOAD),'rank')
  self.reject(lambda:ACQ.acquire_static(self.e,self.a,TK.CLASS,rank=1,acquisition_request_id='invented-rank'),'Ranked|rank')

 def test_power_exact_one_immutable_ability_choice_and_three_actual_identities(self):
  for choice in (TK.INTERFERENCE,TK.PLAYTEST,TK.LEVITATE):
   with self.subTest(choice=choice):
    if choice==TK.PLAYTEST:self.rules=Rules(ROOT,ruleset='all')
    self.setup();self.acquire();self.reject(lambda:self.acquire(TK.POWER),'choose');self.acquire(TK.POWER,selection=choice);self.assertTrue(AB.active(self.a,choice));self.assertEqual(self.a.spec['feature_choices'][TK.POWER],[choice]);self.reject(lambda:self.acquire(TK.POWER,selection=TK.LEVITATE if choice!=TK.LEVITATE else TK.INTERFERENCE),'selection|intent');self.restore();self.valid()

 def test_pk_combat_actual_bind_standard_exact_release_and_remote_membership(self):
  self.combat();self.assertEqual(self.a.budget['standard'],0);self.assertEqual(AP.available(self.a),AP.maximum(self.a)-1);uid,key=self.weapon();self.assertEqual(self.a.custom_conditions['equipped_weapons'][key]['instance_id'],uid);self.assertNotIn('equipped_by',self.e._physical_objects[uid]);self.assertEqual(self.e._physical_objects[uid]['telekinetic_holder_id'],self.a.entity_id)
  self.begin();self.e.end_pk_combat(self.a,instance_id='actual-pk-binding',event_id='release-exact');self.assertFalse(TK.active_combat(self.a));self.assertNotIn(key,self.a.custom_conditions.get('equipped_weapons',{}));self.assertEqual(AP.available(self.a),AP.maximum(self.a));self.restore();self.valid()

 def test_pk_combat_focus_qualification_and_normal_two_hands_limit(self):
  self.combat();uid,key=self.weapon(moves=['move/비열한-습격']);entry=self.a.custom_conditions['equipped_weapons'][key];self.assertEqual(FW.skill_rank(self.e,self.a,entry['weapon']),6);self.assertIn('move/비열한-습격',entry['available_moves']);self.assertEqual(self.a.spec['skills']['전투'],2)
  self.begin()
  # An occupied main hand cannot be replaced by another independently held weapon.
  self.reject(lambda:self.e.equip_telekinetic_weapon(self.a,uid),'occupied|already');self.restore();self.valid()

 def test_pk_combat_melee_eight_metres_optional_spa_still_physical(self):
  self.combat();uid,key=self.weapon();self.begin();self.e.gm.set_position(self.b,(10,2),reason='eight metres from user');prepared=WA.prepare(self.e,self.a,self.rules.move(key),key);self.assertEqual(WA.range_spec(self.e,prepared,self.a)['origin'],8)
  observed=[];original=Engine.roll_damage
  def damage(e,a,t,move,*args,**kw):observed.append((move['class'],move.get('_pk_combat_spa',False),t.staged('def')));return original(e,a,t,move,*args,**kw)
  with patch.object(Engine,'d20',return_value=18),patch.object(Engine,'roll_damage',damage):self.e.use_telekinetic_weapon(self.a,self.b,key,key,use_spa=True,set_damage=True)
  self.assertTrue(observed);self.assertEqual(observed[-1][:2],('물리',True));self.assertLess(self.b.hp,self.b.max_hp);self.assertEqual(self.completion(self.a,key)['move']['class'],'물리');self.valid()

 def test_pk_combat_preserves_long_ranged_twelve_and_refuses_melee_nine(self):
  self.combat();uid,key=self.weapon('장거리 사격무기');self.begin();self.e.gm.set_position(self.b,(14,2),reason='ordinary twelve-metre ranged target');self.assertEqual(WA.range_spec(self.e,WA.prepare(self.e,self.a,self.rules.move(key),key),self.a)['origin'],12)
  with patch.object(Engine,'d20',return_value=18):self.e.use_telekinetic_weapon(self.a,self.b,key,key,set_damage=True)
  self.assertTrue(MC.recipient_result(self.completion(self.a,key),self.b)['hit']);self.valid()
  self.setup();self.combat();uid,key=self.weapon();self.begin();self.e.gm.set_position(self.b,(11,2),reason='nine metres cannot be remote melee');self.reject(lambda:self.e.use_telekinetic_weapon(self.a,self.b,key,key,set_damage=True),'range|접근|outside')

 def test_pk_combat_combined_focus_weight_range_and_unbound_refusal(self):
  self.family(TK.COMBAT);self.begin();uid=self.object('unbound');FW.observe_weapon(self.e,self.a,uid,name='unbound',kind='소형 근접무기',grade='조잡',arcane=False,metal=False,moves=[],reason='actual weapon');self.lift_objects([uid]);self.reject(lambda:self.e.equip_telekinetic_weapon(self.a,uid),'bound')
  self.setup(rank=4);self.combat();self.object('weight1',weight=1000);self.object('weight2',cell=(7,3),weight=1000);self.reject(lambda:self.lift_objects(['weight1','weight2']),'weight|Lifting|무게|capacity|over|exceeds')
  self.object('outside',cell=(11,2));self.reject(lambda:self.lift_objects(['outside']),'eight|8|range')

 def test_pk_combat_real_remote_item_stock_target_eight_and_consumption(self):
  self.combat();uid=self.object('remote-potion',item='item/상처약');self.lift_objects([uid]);self.begin();self.e.gm.set_hp(self.b,self.b.max_hp-50,reason='actual wounded recipient');before=self.b.hp
  self.e.use_telekinetic_item(self.a,uid,self.b);self.assertGreater(self.b.hp,before);self.assertTrue(self.e._physical_objects[uid]['consumed']);self.assertEqual(self.a.budget['standard'],0);self.assertNotIn(uid,[x['id'] for x in self.a.spec['_carried_load']['objects']]);self.restore();self.valid()
  self.setup();self.combat();uid=self.object('remote-potion',item='item/상처약');self.lift_objects([uid]);self.begin();self.e.gm.set_position(self.b,(11,2),reason='recipient outside eight metres');self.reject(lambda:self.e.use_telekinetic_item(self.a,uid,self.b),'eight')

 def test_burst_actual_swift_one_ap_trip_and_push_no_standard_doublepay(self):
  for kind in ('trip','push'):
   with self.subTest(kind=kind):
    self.setup();self.family(TK.BURST);self.begin();ap=AP.available(self.a)
    result=self.e.telekinetic_burst(self.a,self.b,kind,defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*2})
    self.assertTrue(result);self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.a.budget['swift'],0);self.assertEqual(AP.available(self.a),ap-1)
    if kind=='trip':self.assertIn('넘어짐',self.b.conditions)
    else:self.assertEqual(self.b.pos,(9,2));self.assertEqual(result['follow_metres'],0)
    self.restore();self.valid()

 def test_burst_real_disarm_and_opposed_failure_miss_no_effect(self):
  self.family(TK.BURST);key=__import__('turn').equip_weapon(self.e,self.b,{'name':'actual-knife','kind':'소형 근접무기','grade':'조잡','moves':[]});self.begin();self.assertTrue(self.e.telekinetic_burst(self.a,self.b,'disarm',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*2},item_name=key));self.assertNotIn(key,self.b.custom_conditions.get('equipped_weapons',{}));self.valid()
  self.setup();self.family(TK.BURST);self.begin();self.assertFalse(self.e.telekinetic_burst(self.a,self.b,'trip',defender_skill='전투',fixed_accuracy=1,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*2}));self.assertNotIn('넘어짐',self.b.conditions)

 def test_burst_unowned_range_follow_and_late_failure_rollback(self):
  self.begin();self.reject(lambda:self.e.telekinetic_burst(self.a,self.b,'trip',defender_skill='전투'),'acquired');self.family(TK.BURST);self.reject(lambda:self.e.telekinetic_burst(self.a,self.b,'push',defender_skill='전투',follow_steps=1),'repeat|follow')
  with patch.object(__import__('telekinetic_combat'),'_native',side_effect=ValueError('late native Burst failure')):self.reject(lambda:self.e.telekinetic_burst(self.a,self.b,'trip',defender_skill='전투'),'late native')

 def test_barrier_four_real_segments_individual_twenty_hp_fifteen_dr_and_restore(self):
  edges=[((2,y),(3,y)) for y in range(2,6)];row=self.cast(TK.BARRIER,segments=edges);objects=[o for o in self.e._physical_objects.values() if o.get('telekinetic_barrier')];self.assertEqual(len(objects),4)
  for obj in objects:self.assertEqual((obj['physical_attack_integrity']['hp'],obj['physical_attack_integrity']['profile']['reduction']),(20,15));self.assertIn(tuple(sorted(tuple(p) for p in obj['telekinetic_barrier']['edge'])),self.e.grid.walls)
  self.restore();self.valid();self.close();self.e.end_encounter(round_elapsed_seconds=10);self.assertFalse(self.e.grid.walls);self.valid();self.e.end_scene();self.assertFalse(self.e.grid.walls)

 def test_barrier_normal_contiguity_touch_and_overload_six_nonadjacent_within_six(self):
  self.family(TK.ALPHA);self.begin();self.reject(lambda:self.e.use_telekinetic_move(self.a,self.a,TK.BARRIER,segments=[((5,5),(6,5))]),'touch');self.reject(lambda:self.e.use_telekinetic_move(self.a,self.a,TK.BARRIER,segments=[((2,2),(3,2)),((5,5),(6,5))]),'continuous')
  edges=[((3+i,5),(3+i,6)) for i in range(6)];ap=AP.available(self.a);self.cast(TK.BARRIER,segments=edges,overload=True);self.assertEqual(len(self.e.grid.walls),6);self.assertEqual(self.a.budget['swift'],0);self.assertEqual(AP.available(self.a),ap-2);self.valid()

 def test_barrier_real_physical_damage_destroyed_segment_removes_only_its_wall(self):
  self.cast(TK.BARRIER,segments=[((2,2),(3,2)),((2,3),(3,3))]);uid=next(u for u,o in self.e._physical_objects.items() if o.get('telekinetic_barrier'));self.e.gm.set_position(self.b,(3,2),reason='actual adjacent barrier attacker');self.turn(self.b)
  self.e.gm.set_move(self.b,'move/엄청난힘',reason='actual learned reviewed physical-object attack')
  row=self.e.attack_physical_object(self.b,uid,'move/엄청난힘',event_id='actual-wall-strike',hit=True,damage_before_dr=70,source='explicit-gm-hit-damage',reason='measured pre-DR actual strike');self.assertEqual(row['applied_damage'],20);self.assertTrue(self.e._physical_objects[uid]['destroyed']);self.assertEqual(len(self.e.grid.walls),1);self.restore();self.valid()

 def test_kinesis_actual_interrupt_original_accuracy_minus_four_can_miss(self):
  self.family(TK.ALPHA);REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=self.c);self.begin(self.b);self.e.gm.set_position(self.b,(4,3),reason='actual adjacent attacker');self.e.gm.set_stat(self.c,'def',value=40,reason='actual target Evasion8 makes natural11 hit before Kinesis and miss after minus4');hp=self.c.hp
  with patch.object(Engine,'d20',return_value=11) as die:self.e.use_move(self.b,self.c,'move/몸통박치기',set_damage=True)
  original=self.completion(self.b,'move/몸통박치기');self.assertFalse(MC.recipient_result(original,self.c)['hit']);self.assertEqual(self.c.hp,hp);self.assertEqual(self.completion(self.a,TK.KINESIS)['phase'],'complete');self.assertEqual(die.call_count,1);self.assertIsNone(__import__('initiative_interrupts').frame(self.e));self.restore();self.valid()

 def test_kinesis_self_without_side_or_distance_and_live_ally_observation_boundaries(self):
  import action_resources as RES
  cases=(('absent','absent'),(None,None),(None,'party'),('party',None),('party','party'),('party','foes'))
  for self_target in (False,True):
   for sides in (cases if not self_target else cases[:2]):
    with self.subTest(self_target=self_target,sides=sides):
     self.setup();self.family(TK.ALPHA);target=self.a if self_target else self.c
     REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=target)
     for actor,side in zip((self.a,target),sides):
      actor.spec.pop('side',None)
      if side=='absent':vars(actor).pop('side',None)
      else:actor.side=side
     allowed=self_target or sides==('party','party')
     if self_target:
      location=deepcopy(self.a.location);self.a.location={'kind':'unknown'}
      REACTIONS.arm(self.e,self.a,TK.KINESIS)
      self.a.location=location
     elif allowed:REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=target)
     else:self.reject(lambda:REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=target),'observed ally within six metres')
     if self_target:self.e.gm.set_position(self.c,(3,2),reason='actual third participant adjacent to attacker; no independent flanking pair')
     self.begin(self.b);self.e.gm.set_position(self.b,(target.pos[0],target.pos[1]-1),reason='actual adjacent attacker with no independent flanking pair')
     self.e.gm.set_stat(target,'def',value=40,reason='actual Evasion8 makes natural11 miss after Kinesis')
     self.restore();target=self.a if self_target else self.c;hp=target.hp
     choice=deepcopy(self.a.spec[REACTIONS.CHOICES][TK.KINESIS])
     with patch.object(Engine,'d20',return_value=11):self.e.use_move(self.b,target,'move/몸통박치기',set_damage=True)
     result=MC.recipient_result(self.completion(self.b,'move/몸통박치기'),target)
     if allowed:
      self.assertFalse(result['hit']);self.assertEqual(target.hp,hp)
      self.assertEqual(self.a.move_uses[TK.KINESIS],1);self.assertEqual(RES.pending(self.a),{'standard':1})
      self.assertNotIn(TK.KINESIS,self.a.spec[REACTIONS.CHOICES])
     else:
      self.assertTrue(result['hit']);self.assertLess(target.hp,hp)
      self.assertNotIn(TK.KINESIS,self.a.move_uses);self.assertEqual(RES.pending(self.a),{})
      self.assertEqual(self.a.spec[REACTIONS.CHOICES][TK.KINESIS],choice)
     self.restore();self.valid()

 def test_kinesis_rechecks_actual_six_metre_range_before_consuming_choice(self):
  import action_resources as RES
  self.family(TK.ALPHA);REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=self.c)
  self.e.gm.set_position(self.c,(9,2),reason='ally moved seven metres from reactor')
  self.e.gm.set_position(self.b,(10,2),reason='actual adjacent attacker')
  self.reject(lambda:REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=self.c),'six metres')
  self.begin(self.b);hp=self.c.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.c,'move/몸통박치기',set_damage=True)
  self.assertLess(self.c.hp,hp);self.assertNotIn(TK.KINESIS,self.a.move_uses)
  self.assertIn(TK.KINESIS,self.a.spec[REACTIONS.CHOICES]);self.assertEqual(RES.pending(self.a),{})
  self.restore();self.valid()

 def test_kinesis_overload_completed_real_reaction_own_ordinary_swift_original_attacker(self):
  self.family(TK.OVERLOAD);REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=self.c,overload=True);self.begin();ap=AP.available(self.a)
  # Friendly fire is an actual permitted attack during the Telekinetic own turn.
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.c,'move/물대포',set_damage=True)
  event=next(r for r in self.a.spec[REACTIONS.EVENTS].values() if r['source']==TK.KINESIS);self.assertTrue(event['overload_spent']);self.assertEqual(event['attacker_id'],self.a.entity_id);self.assertIn('혼란',self.a.conditions);self.assertNotIn('혼란',self.c.conditions);self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.a.budget['swift'],0);self.assertIsNone(__import__('initiative_interrupts').frame(self.e));self.restore();self.valid()

 def test_kinesis_offturn_overload_and_manual_untriggered_cast_are_atomic_refusals(self):
  self.family(TK.OVERLOAD);self.begin();self.reject(lambda:self.e.use_telekinetic_move(self.a,self.c,TK.KINESIS),'actual');REACTIONS.arm(self.e,self.a,TK.KINESIS,protect=self.c,overload=True);self.turn(self.b);self.e.gm.set_position(self.b,(4,3),reason='actual adjacent opponent')
  with patch.object(Engine,'d20',return_value=18):self.reject(lambda:self.e.use_move(self.b,self.c,'move/몸통박치기',set_damage=True),'ordinary turn')

 def test_psychic_actual_named_hit_direction_spdef_and_full_round_vulnerable(self):
  origin=self.b.pos;self.cast(TK.PSYCHIC,overload=True,face=18);self.assertEqual(self.b.pos,(origin[0],origin[1]+1));self.assertEqual(self.b.stages['spd'],-1);self.assertIn('취약',self.b.conditions);self.assertLess(self.b.hp,self.b.max_hp)
  self.close();self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(61);self.assertIn('취약',self.b.conditions);self.e.at_initiative_count(60);self.assertNotIn('취약',self.b.conditions);self.restore();self.valid()

 def test_psychic_miss_no_overload_ap_or_vulnerability_and_other_move_no_trigger(self):
  self.family(TK.OVERLOAD);self.begin();ap=AP.available(self.a)
  with patch.object(Engine,'d20',return_value=1):self.e.use_telekinetic_move(self.a,self.b,TK.PSYCHIC,overload=True,push_direction=(0,1))
  self.assertEqual(AP.available(self.a),ap);self.assertEqual(self.a.budget['swift'],1);self.assertNotIn('취약',self.b.conditions);self.valid()

 def test_telekinesis_printed_user_caster_default_native_use_and_optional_scoped_override(self):
  self.family(TK.OMEGA);self.begin();policy=self.e.telekinesis_evasion_policy();self.assertEqual(policy['status'],'PolicyValuesReady');self.assertEqual(policy['values']['evasion_owner'],'printed_user_caster');self.assertEqual(policy['decision_evidence'],[])
  self.e.use_move(self.a,self.b,TK.LIFT);self.assertEqual(self.completion(self.a,TK.LIFT)['phase'],'complete');self.assertEqual(self.a.evasion('물리'),0);self.assertGreater(self.b.evasion('물리'),0);self.restore();self.valid()
  self.begin(self.b)
  with patch.object(Engine,'d20',return_value=16):self.assertTrue(self.e.escape_lifted(self.b)['escaped'])
  self.assertGreater(self.a.evasion('물리'),0);self.restore();self.valid()
  self.begin();bad=self.decision('lifted_target');bad['scope']={};self.reject(lambda:self.e.use_telekinetic_move(self.a,self.b,TK.LIFT,evasion_owner=bad),'scope')

 def test_telekinesis_both_adjudication_consumers_lifted_movement_levitate_and_restore(self):
  for owner in ('printed_user_caster','lifted_target'):
   with self.subTest(owner=owner):
    self.setup();self.cast(owner=owner);self.assertTrue(TK.lifted(self.b));self.assertTrue(AB.active(self.b,TK.LEVITATE));self.assertEqual(MOVEMENT.capabilities(self.e,self.b)['land'],0);self.assertEqual(self.e.move_profile(self.b,movement_mode='levitate')[0],2)
    zero=self.a if owner=='printed_user_caster' else self.b;other=self.b if owner=='printed_user_caster' else self.a;self.assertEqual(zero.evasion('물리'),0);self.assertGreater(other.evasion('물리'),0);self.restore();self.valid()

 def test_telekinesis_shift_escape_sixteen_and_preserves_independent_owned_state(self):
  self.e.gm.set_ability(self.b,'부유',reason='independently owned Levitate');self.e.apply_status(self.b,'둔화');self.cast();self.turn(self.b)
  with patch.object(Engine,'d20',return_value=15):self.assertFalse(self.e.escape_lifted(self.b)['escaped'])
  self.begin(self.b)
  with patch.object(Engine,'d20',return_value=16):self.assertTrue(self.e.escape_lifted(self.b)['escaped'])
  self.assertFalse(TK.lifted(self.b));self.assertIn('둔화',self.b.conditions);self.assertTrue(AB.active(self.b,TK.LEVITATE));self.assertGreater(MOVEMENT.capabilities(self.e,self.b)['land'],0);self.restore();self.valid()

 def test_overload_lifted_actual_target_end_turn_one_tick_not_round_or_caster(self):
  self.cast(overload=True);hp=self.b.hp;self.close();self.assertEqual(self.b.hp,hp);self.turn(self.b);self.close();self.assertEqual(self.b.hp,hp-self.e.tick(self.b));self.e.end_round();self.assertEqual(self.b.hp,hp-self.e.tick(self.b));self.restore();self.valid()

 def test_power_trainer_levitate_actual_ground_immunity_four_and_existing_plus_two(self):
  self.family(TK.POWER);self.assertEqual(MOVEMENT.capabilities(self.e,self.a)['levitate'],4)
  self.e.gm.set_ability(self.a,TK.LEVITATE,reason='same independently owned Levitate by exact source');self.assertIn(TK.LEVITATE,self.a.abilities);self.assertNotIn('부유',self.a.abilities)
  self.assertEqual(MOVEMENT.capabilities(self.e,self.a)['levitate'],4)
  self.e.gm.set_movement_capabilities(self.a,dict(self.a.spec['movement'],levitate=5),basis='current',reason='independent positive Levitate capability');self.assertEqual(MOVEMENT.capabilities(self.e,self.a)['levitate'],7)
  self.begin(self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,'move/지진',set_damage=True)
  self.assertEqual(self.a.hp,hp);self.restore();self.valid()

 def test_interference_core_standard_atwill_next_personal_turn_and_playtest_scene_swift_round(self):
  for choice in (TK.INTERFERENCE,TK.PLAYTEST):
   with self.subTest(choice=choice):
    if choice==TK.PLAYTEST:self.rules=Rules(ROOT,ruleset='all')
    self.setup();self.family(TK.POWER,selection=choice);self.e.gm.set_position(self.b,(5,2),reason='actual foe at three metres');self.begin();self.e.activate_ability(self.a,choice,self.a);self.assertEqual(TIME.accuracy_modifier(self.b),-2);self.assertEqual(TIME.accuracy_modifier(self.c),0)
    self.assertEqual(self.a.budget['swift' if choice==TK.PLAYTEST else 'standard'],0);self.restore();self.valid();self.close();self.e.end_round();self.e.start_round(self.e.everyone)
    if choice==TK.PLAYTEST:
     self.e.at_initiative_count(60);self.assertEqual(TIME.accuracy_modifier(self.b),0);self.e.start_of_turn(self.a,initiative_count=60);self.reject(lambda:self.e.activate_ability(self.a,choice,self.a),'Scene')
    else:
     self.assertEqual(TIME.accuracy_modifier(self.b),-2);self.e.start_of_turn(self.a,initiative_count=60);self.close();self.assertEqual(TIME.accuracy_modifier(self.b),0)

 def test_late_native_move_failure_rolls_back_placement_actions_ap_rng(self):
  self.family(TK.OVERLOAD);self.begin();original=TK.after_hit
  def fail(*args):original(*args);raise ValueError('late actual Telekinetic consumer failure')
  with patch.object(TK,'after_hit',fail):self.reject(lambda:self.e.use_telekinetic_move(self.a,self.a,TK.BARRIER,segments=[((2,2),(3,2))],overload=True),'late actual')

 def test_native_acquisition_retraining_dependency_pk_binding_and_owned_spa_cleanup(self):
  self.combat();self.weapon();self.begin();import trainer_retraining as RETRAIN
  owned=RETRAIN._owned(self.a);sources={u:RETRAIN.owned_source(self.e,self.a,u) for u in owned};required=RETRAIN._native_dependencies(self.e,self.a,owned);deps={sid:[sources[p] for p in required.get(u,[])] for u,sid in sources.items() if u!=TK.COMBAT}
  self.e.retrain_trainer_source(self.a,TK.COMBAT,request_id='retire:actual-pk-combat',reason='actual retraining consultation',gm_decision={'allowed':True,'reason':'approved'},retained_dependencies=deps);self.assertFalse(TK.active_combat(self.a));self.assertFalse(self.a.custom_conditions.get('equipped_weapons'));self.assertTrue(TK.acquired(self.a,TK.CLASS));self.restore();self.valid()
