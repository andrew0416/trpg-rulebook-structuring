"""TK Mastery through actual native source, roll, object, attack and maneuver owners."""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
import test_category2_move_edge_state as _fixture_test_category2_move_edge_state
import tk_mastery as M,telekinetic_combat as TK,telekinetic_load as LOAD
import struggle_capabilities as STRUGGLE,skill_modifiers as S,state_grants as G
import state_fields as F,state_codec as CODEC,world_entities as W
import maneuver_opposed as OP,forced_movement as FORCED,turn as TURN
from grid import Grid


class TKMasteryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_category2_move_edge_state.MoveEdgeStateTests.setUpClass()
 def setUp(self):
  self.f=_fixture_test_category2_move_edge_state.MoveEdgeStateTests();self.f.setUp();self.e=self.f.e;self.r=self.f.r;self.p=self.f.p;self.t=self.f.t;self.owner=self.f.a
  G.replace_baseline(self.e,self.p,'capabilities',['염력'])
  self.e.gm.set_skill(self.p,'집중',3,reason='actual Focus rank observed')
 def snap(self):return CODEC.dump_engine(self.e)
 def teach(self,**options):return self.e.pokemon_activity(self.owner,'teach_edge',target=self.p,edge=options.pop('edge',M.SOURCE),safe=True,**options)
 def round(self,target=None,distance=8):
  target=target or self.t;self.e.grid=Grid(20,4);self.p.pos=(0,0);target.pos=(distance,0)
  self.e.start_round([self.p,target]);self.e.start_of_turn(self.p)
 def choice(self,special=False,policy=None):
  result={'capability':'염력','special':special}
  if special:
   pending=self.e.telekinetic_struggle_policy()
   result['damage_policy']={'value':policy or 'capability_physical','reason':'GM selects the stated PTK passage for this attack','scope':pending['decision_scope']}
  return result
 def prepared(self,**options):return STRUGGLE.prepare(self.e,self.p,self.r.move('struggle'),self.choice(**options))
 def options(self,skill='전투',**changes):
  result={'defender_skill':skill,'fixed_accuracy':10,
   'challenger_options':{'fixed':[3]*(S.rank(self.r,self.p,'집중')[2]+M.bonus(self.p))},
   'defender_options':{'fixed':[1]*S.rank(self.r,self.t,skill)[2]}}
  result.update(changes);return result
 def test_real_csv_acquisition_hour_tp_receipt_and_duplicate_refusal(self):
  out=self.teach(edge='C2CSV/input/db/poke-edges.csv:R56:main')
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds,M.focus(self.p)),(7,3600,5))
  self.assertEqual(out['definition_origin']['record'],56)
  receipt=M.records(self.p)[0]
  self.assertEqual((receipt['definition_origin']['record'],receipt['trainer_id'],receipt['point_cost']),(56,self.owner.entity_id,1))
  before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_missing_prerequisite_tp_or_actual_owner_refuses_without_cost(self):
  for change in ('level','capability','balance','owner'):
   self.setUp()
   if change=='level':self.e.gm.set_level(self.p,19,reason='actual level correction')
   if change=='capability':G.replace_baseline(self.e,self.p,'capabilities',[])
   if change=='balance':self.p.spec['tutor_points']=0
   if change=='owner':self.p.spec['trainer_id']=self.t.entity_id
   before=deepcopy((self.p.spec,self.e.elapsed_seconds,self.e.rng.getstate()))
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual((self.p.spec,self.e.elapsed_seconds,self.e.rng.getstate()),before)
 def test_actual_struggle_reach_changes_three_to_five_without_global_focus_bonus(self):
  self.assertEqual(self.prepared()['_struggle_range']['origin'],3)
  self.teach();self.round(distance=5)
  with patch.object(M.COMPOSITION,'derive',wraps=M.COMPOSITION.derive) as common:
   prepared=self.prepared()
  self.assertTrue(any(any(row['source']==M.SOURCE for row in call.args[1]) for call in common.call_args_list))
  self.assertEqual(prepared['_struggle_range']['origin'],5)
  self.assertEqual(self.e.skill_roll(self.p,'집중',fixed=[3]*3).total,9)
  before=self.t.hp
  with patch.object(self.e.rng,'randint',return_value=10):self.e.use_move(self.p,self.t,'struggle',set_damage=True,struggle_choice=self.choice())
  self.assertLess(self.t.hp,before);self.assertEqual(self.p.budget['standard'],0)
 def test_outside_scoped_struggle_range_cannot_spend_action_or_rng(self):
  self.teach();self.round(distance=6);before=self.snap()
  self.assertEqual(self.e.use_move(self.p,self.t,'struggle',struggle_choice=self.choice()),0)
  self.assertEqual(self.snap(),before)
 def test_conflicting_damage_class_has_no_silent_special_attack_default(self):
  self.teach();self.round(distance=5);pending=self.e.telekinetic_struggle_policy()
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  self.assertEqual(pending['obligations'][0]['decision_kind'],'source_conflict')
  for decision in (None,{'value':'capability_physical','reason':'missing scope'},dict(self.choice(True)['damage_policy'],scope={})):
   bad={'capability':'염력','special':True}
   if decision is not None:bad['damage_policy']=decision
   before=self.snap()
   with self.assertRaises(ValueError):self.e.use_move(self.p,self.t,'struggle',struggle_choice=bad)
   self.assertEqual(self.snap(),before)
 def test_both_explicit_sources_keep_attack_stat_and_damage_class_independent(self):
  self.teach()
  F.base_patch(self.p,{'stats':dict(hp=20,atk=10,**{'def':10},spa=40,spd=10,spe=1)},reason='actual observed attack stats')
  F.base_patch(self.t,{'stats':dict(hp=20,atk=10,**{'def':1},spa=10,spd=21,spe=1)},reason='actual distinct defenses')
  normal=self.prepared()
  physical=self.prepared(special=True,policy='capability_physical')
  special=self.prepared(special=True,policy='combat_table_special')
  self.assertEqual((physical['class'],special['class'],physical['type'],special['type']),('물리','특수','노말','노말'))
  self.assertEqual(physical[TK.STRUGGLE_MARKER]['attack_stat'],'spa')
  a=self.e.roll_damage(self.p,self.t,normal,set_damage=True)
  b=self.e.roll_damage(self.p,self.t,physical,set_damage=True)
  c=self.e.roll_damage(self.p,self.t,special,set_damage=True)
  self.assertEqual(b-a,30);self.assertEqual(b-c,20)
  self.assertEqual(self.r.move('struggle')['class'],'물리')
 def test_source_decision_is_observed_by_native_trace_and_survives_restore(self):
  import event_trace as TRACE
  self.teach();self.round(distance=5);TRACE.enable(self.e,True)
  with patch.object(self.e.rng,'randint',return_value=10):self.e.use_move(self.p,self.t,'struggle',set_damage=True,struggle_choice=self.choice(True))
  traces=TRACE.records(self.e);self.assertIn('capability_physical',json.dumps(traces,ensure_ascii=False))
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
  self.assertEqual(TRACE.records(loaded),traces)
 def test_actual_focus_lifting_chart_and_five_dice_carry_check_keep_eight_metre_limit(self):
  old=LOAD.table(self.p)['heavy'][1];self.teach();self.assertGreater(LOAD.table(self.p)['heavy'][1],old)
  self.round();weight=LOAD.table(self.p)['staggering']-1
  W.register_object(self.e,'tk-load',location={'kind':'grid','cell':(8,0)},weight_kg=weight,reason='actual remote weighed object')
  self.e.telekinetic_lift(self.p,['tk-load'],action_cost='shift',reason='GM declares actual Shift lifting')
  out=self.e.carry_check(self.p,fixed=[3]*5);self.assertTrue(out.passed)
  self.e.release_telekinetic_load(self.p,reason='actual release')
  W.register_object(self.e,'tk-load',location={'kind':'grid','cell':(9,0)},weight_kg=1,reason='actual object nine metres away')
  TURN.reset_budget(self.e,self.p);before=self.snap()
  with self.assertRaisesRegex(ValueError,'eight'):self.e.telekinetic_lift(self.p,['tk-load'],action_cost='shift',reason='GM actual cost')
  self.assertEqual(self.snap(),before)
 def test_remote_trip_uses_shared_opposed_owner_and_five_focus_dice(self):
  self.teach();self.round()
  with patch.object(OP,'_run',wraps=OP._run) as common:
   out=self.e.telekinetic_maneuver(self.p,self.t,'trip',**self.options())
  self.assertTrue(out);self.assertEqual(common.call_count,1);self.assertIn('넘어짐',self.t.conditions)
  self.assertEqual(self.p.budget,{'standard':0,'shift':1,'swift':1})
 def test_remote_push_is_one_focus_half_displacement_without_follow(self):
  for trained,distance in ((False,1),(True,2)):
   self.setUp()
   if trained:self.teach()
   self.round();self.t.spec['weight_kg']=1
   with patch.object(FORCED,'displace',wraps=FORCED.displace) as common:
    out=self.e.telekinetic_maneuver(self.p,self.t,'push',**self.options())
   self.assertEqual((out['requested'],out['moved'],self.t.pos,self.p.pos),(distance,distance,(8+distance,0),(0,0)))
   self.assertEqual(common.call_count,1);self.assertEqual((out['follow_metres'],self.p.budget['shift']),(0,1))
 def test_remote_maneuver_range_weight_and_repeat_refuse_before_cost(self):
  self.teach();self.round(distance=9);before=self.snap()
  with self.assertRaises(ValueError):self.e.telekinetic_maneuver(self.p,self.t,'trip',**self.options())
  self.assertEqual(self.snap(),before)
  self.t.pos=(8,0);self.t.spec['weight_kg']=LOAD.table(self.p)['heavy'][1]+.1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'Heavy'):self.e.telekinetic_maneuver(self.p,self.t,'push',**self.options())
  self.assertEqual(self.snap(),before)
  self.t.spec['weight_kg']=1;before=self.snap()
  with self.assertRaisesRegex(ValueError,'repeat'):self.e.telekinetic_maneuver(self.p,self.t,'push',follow_steps=1,**self.options())
  self.assertEqual(self.snap(),before)
 def test_miss_and_defending_tie_spend_one_action_but_no_result(self):
  self.teach();self.round();rng=self.e.rng.getstate()
  self.assertFalse(self.e.telekinetic_maneuver(self.p,self.t,'trip',**self.options(fixed_accuracy=1)))
  self.assertEqual((self.p.budget['standard'],self.e.rng.getstate()),(0,rng));self.assertNotIn('넘어짐',self.t.conditions)
  TURN.reset_budget(self.e,self.p)
  # Defender total ties15; ordinary status quo wins without a second attack.
  rank=S.rank(self.r,self.t,'전투')[2]
  self.assertFalse(self.e.telekinetic_maneuver(self.p,self.t,'trip',**self.options(defender_options={'fixed':[3]*rank,'mods':15-3*rank})))
  self.assertNotIn('넘어짐',self.t.conditions);self.assertEqual(self.p.budget['standard'],0)
 def test_late_forced_result_failure_rolls_back_action_rng_and_world(self):
  self.teach();self.round();self.t.spec['weight_kg']=1;before=self.snap()
  with patch.object(FORCED,'displace',side_effect=ValueError('late forced result failure')):
   with self.assertRaisesRegex(ValueError,'late forced'):self.e.telekinetic_maneuver(self.p,self.t,'push',**self.options())
  self.assertEqual(self.snap(),before)
 def test_remote_disarm_reuses_actual_equipment_selection_and_drop(self):
  self.teach();target=self.owner;self.round(target)
  key=TURN.equip_weapon(self.e,target,{'name':'실제 검','kind':'소형 근접무기','grade':'조잡'})
  rank=S.rank(self.r,target,'전투')[2]
  with patch.object(TURN,'disarm_equipment',wraps=TURN.disarm_equipment) as common:
   out=self.e.telekinetic_maneuver(self.p,target,'disarm',defender_skill='전투',fixed_accuracy=10,
    challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*rank})
  self.assertTrue(out);self.assertEqual(common.call_count,1);self.assertNotIn(key,target.custom_conditions.get('equipped_weapons',{}))
  self.assertEqual((self.p.budget['standard'],target.pos),(0,(8,0)))
 def test_prerequisite_loss_refunds_once_and_restore_reactivates_saved_consumer(self):
  self.teach();self.e.gm.snapshot('tk-active');saved=self.snap()
  G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual((self.p.spec['tutor_points'],M.records(self.p)[0]['status']),(8,'refunded'))
  G.replace_baseline(self.e,self.p,'capabilities',['염력'])
  self.assertEqual((M.focus(self.p),self.p.spec['tutor_points']),(3,8))
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)))
  p=next(x for x in loaded.everyone if x.entity_id==self.p.entity_id)
  self.assertEqual(M.focus(p),5)
  self.e.gm.restore('tk-active');self.assertEqual(M.focus(self.p),5)
  self.e.gm.set_level(self.p,19,reason='actual level loss');self.assertEqual(self.p.spec['tutor_points'],8)
  self.e.gm.set_level(self.p,18,reason='second level correction');self.assertEqual(self.p.spec['tutor_points'],8)
 def test_changed_csv_origin_cannot_be_saved(self):
  self.teach();M.records(self.p)[0]['definition_origin']['record']=55
  with self.assertRaises(ValueError):self.snap()

 def test_maneuver_context_cannot_name_another_skill_or_missing_target(self):
  self.teach();self.round()
  context={'purpose':TK.PURPOSE,'maneuver':OP.TRIP,'target_id':self.t.entity_id,'reason':'actual native counterpart'}
  for skill,change in [('집중',{'target_id':'missing'}),('전투',{}),('집중',{'extra':1})]:
   before=self.snap()
   with self.assertRaises(ValueError):self.e.skill_roll(self.p,skill,skill_context=dict(context,**change))
   self.assertEqual(self.snap(),before)

 def test_prepared_struggle_rechecks_loss_and_rejects_injected_attack_stat(self):
  self.teach();prepared=self.prepared();tampered=deepcopy(prepared)
  tampered[TK.STRUGGLE_MARKER]['attack_stat']='spa';before=self.snap()
  with self.assertRaises(ValueError):self.e.roll_damage(self.p,self.t,tampered,set_damage=True)
  self.assertEqual(self.snap(),before)
  self.e.gm.set_level(self.p,19,reason='actual prerequisite loss')
  self.assertEqual(STRUGGLE.prepare(self.e,self.p,prepared)['_struggle_range']['origin'],3)
  G.replace_baseline(self.e,self.p,'capabilities',[]);before=self.snap()
  with self.assertRaises(ValueError):self.e.roll_damage(self.p,self.t,prepared,set_damage=True)
  self.assertEqual(self.snap(),before)

 def test_grooming_completed_hour_is_reused_without_second_hour(self):
  self.owner.spec['edges']=['미용사'];self.owner.spec['items']['미용사 킷']=1
  self.owner.spec['skills']['포켓몬학']=3
  self.e.pokemon_activity(self.owner,'groom',targets=[self.p],safe=True)
  self.teach(from_grooming=True)
  self.assertEqual((self.e.elapsed_seconds,self.p.spec['tutor_points']),(3600,7))
  self.assertIn(M.SOURCE,self.p.spec['training_credit']['applications'])

 def test_trainer_telekinetic_struggle_uses_same_native_attack_without_pokemon_edge(self):
  G.grant(self.owner,'capabilities','Telekinetic','fixture:trainer-telekinetic','actual acquired capability')
  self.e.gm.set_skill(self.owner,'집중',4,reason='actual trainer Focus')
  self.e.grid=Grid(12,4);self.owner.pos=(0,0);self.t.pos=(4,0)
  self.e.start_round([self.owner,self.t]);self.e.start_of_turn(self.owner)
  before=self.t.hp
  with patch.object(self.e.rng,'randint',return_value=10):self.e.use_move(self.owner,self.t,'struggle',set_damage=True,struggle_choice=self.choice())
  self.assertLess(self.t.hp,before);self.assertEqual(self.owner.budget['standard'],0)

 def test_excluded_csv_definition_refuses_acquisition_before_time_or_tp(self):
  old=self.r.selection.excluded.get(M.SOURCE);self.r.selection.excluded[M.SOURCE]='exclude_units'
  try:
   before=deepcopy((self.p.spec,self.e.elapsed_seconds,self.e.rng.getstate()))
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual((self.p.spec,self.e.elapsed_seconds,self.e.rng.getstate()),before)
  finally:
   if old is None:self.r.selection.excluded.pop(M.SOURCE,None)
   else:self.r.selection.excluded[M.SOURCE]=old


if __name__=='__main__':unittest.main()

