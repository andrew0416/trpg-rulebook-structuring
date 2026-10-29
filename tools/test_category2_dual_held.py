"""Safe stopping unit: two-held identity/choices, not full clause certification."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'engine'))
from tools import test_category2_equipment_protection as FIX
from tools import test_category2_csv_item_transfers as LEGACY
from engine import Engine
import held_equipment as H,equipment_actions as E,items as I,world_entities as W,state_grants as G,common_checks as C

class DualHeldTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):FIX.ProtectionTests.setUpClass();cls.f=FIX.ProtectionTests();LEGACY.Tests.r=cls.f.r;cls.legacy=LEGACY.Tests()
 def add(self,e,c,name='예리한손톱',uid='second'):
  W.register_object(e,uid,location={'kind':'unknown'},reason='observed distinct physical held item',kind='item_instance',item_rule_id='item/'+name,owner_id=c.entity_id)
  return I.equip_held(e,c,name,source_instance_id=uid)
 def fixture(self,move='도둑질',ability='배달부'):
  e,a,b,mid=self.f.fixture(move,held=(None,'선제공격손톱'),abilities=((),(ability,)))
  self.add(e,b);return e,a,b,mid
 def valid(self,e):self.assertTrue(e.validate_state()['valid'],e.validate_state()['issues'])
 def roundtrip(self,e):return Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
 def test_disarmed_physical_instance_and_ground_name_survive_both_restore_paths(self):
  import skill_modifiers as SKILL
  e,a,b,mid=self.f.fixture(held=(None,'선제공격손톱'),abilities=((),()))
  e.start_round([a,b]);e.start_of_turn(a)
  self.assertTrue(e.disarm(a,b,attacker_skill='전투',defender_skill='전투',fixed_accuracy=20,
   challenger_options={'fixed':[6]*SKILL.rank(e.r,a,'전투')[2]},defender_options={'fixed':[1]*SKILL.rank(e.r,b,'전투')[2]}))
  expected=deepcopy(e.ground_items[-1]);self.assertEqual((expected['item'],expected['instance_id']),('선제공격손톱','object/1'))
  snapshot=e.gm.snapshot();e.ground_items[-1]['item']='incorrect';e.gm.restore(snapshot)
  self.assertEqual(e.ground_items[-1],expected);loaded=self.roundtrip(e)
  self.assertEqual(loaded.ground_items[-1],expected)
  obj=loaded._physical_objects['object/1'];self.assertIsNone(obj.get('equipped_by'))
  self.assertEqual(obj['location'],W.location_of(loaded.gm.everyone[1]));self.valid(loaded)
 def test_both_exact_sources_zero_one_two_and_capacity_refusal(self):
  for ability in ('배달부','배달새','ability/배달부','ability/배달부-2','ability/배달새'):
   e,a,b,mid=self.f.fixture(held=(None,None),abilities=((),(ability,)))
   self.assertIsNone(b.item);self.add(e,b,'선제공격손톱','first');self.assertEqual(b.item,'선제공격손톱');self.add(e,b)
   self.assertEqual(H.capacity(b)['maximum'],2);self.assertEqual(H.capacity(b)['sources'],[ability if ability.startswith('ability/') else 'ability/'+ability]);self.assertEqual(b.initiative_bonus,10);self.assertEqual(len(H.entries(b)),2)
   with self.assertRaises(ValueError):_=b.item
   with self.assertRaises(ValueError):b.item=None
   self.assertNotIn('item',b.spec);before=deepcopy(b.spec)
   with self.assertRaises(ValueError):I.equip_held(e,b,'예리한이빨')
   self.assertEqual(b.spec,before);self.valid(e)
 def test_reregister_unique_held_item_is_idempotent_but_duplicate_names_need_selection(self):
  e,a,b,mid=self.fixture();before=deepcopy(b.spec);bonus=b.initiative_bonus
  self.assertEqual(I.register_item(e,b,'선제공격손톱'),0)
  self.assertEqual(I.register_item(e,b,'예리한손톱'),0)
  self.assertEqual((b.spec,b.initiative_bonus),(before,bonus));self.valid(e)
  e,a,b,mid=self.f.fixture(held=(None,None),abilities=((),('배달부',)))
  self.add(e,b,'선제공격손톱','copy-one');self.add(e,b,'선제공격손톱','copy-two');before=deepcopy(b.spec)
  with self.assertRaisesRegex(ValueError,'ambiguous'):I.register_item(e,b,'선제공격손톱')
  self.assertEqual(b.spec,before)
  self.assertEqual(I.register_item(e,b,'선제공격손톱',source_instance_id='copy-one'),0)
 def test_native_theft_drop_and_pluck_holder_selects_not_attacker(self):
  for move in ('도둑질','탐내기','쪼아대기','탁쳐서떨구기'):
   e,a,b,mid=self.fixture(move);obj=e._physical_objects['second'];e.use_move(a,b,mid);row=E.pending(e)[0]
   self.assertIs(row['chooser'],b);self.assertEqual(len(H.entries(b)),2)
   with self.assertRaises(ValueError):E.resolve(e,a,row['id'],selection='second')
   E.resolve(e,b,row['id'],selection='second');self.assertEqual(b.item,'선제공격손톱');self.assertIs(e._physical_objects['second'],obj)
   self.assertEqual(obj['owner_id'],b.entity_id);self.assertEqual(a.item,None if move=='탁쳐서떨구기' else '예리한손톱');self.valid(e)
 def test_knockoff_attacker_selects_held_category_or_worn_then_holder_instance(self):
  e,a,b,mid=self.legacy.fixture('탁쳐서떨구기',held=(None,'선제공격손톱'));G.replace_baseline(e,b,'abilities',['배달부']);self.add(e,b)
  W.register_object(e,'worn',location={'kind':'unknown'},reason='observed accessory',kind='item_instance',item_rule_id='item/달인의띠',owner_id=b.entity_id);I.register_item(e,b,'달인의띠',source_instance_id='worn')
  e.use_move(a,b,mid);row=E.pending(e)[0];self.assertIs(row['chooser'],a)
  with self.assertRaises(ValueError):E.resolve(e,a,row['id'],selection='second')
  E.resolve(e,a,row['id'],selection='held-group');self.assertIs(row['chooser'],b);E.resolve(e,b,row['id'],selection='second');self.assertIn('달인의띠',b._item_reg);self.assertEqual(b.item,'선제공격손톱');self.valid(e)
 def test_switcheroo_and_trick_each_holder_selects_one_and_keeps_other(self):
  for move in ('바꿔치기','트릭'):
   e,a,b,mid=self.fixture(move);G.replace_baseline(e,a,'abilities',['배달새']);self.add(e,a,'선제공격손톱','a-first');self.add(e,a,'예리한이빨','a-second')
   if move=='트릭':e.use_move_on(a,b,mid,e.everyone,equipment_options={'targets':[a,b]})
   else:e.use_move(a,b,mid)
   row=E.pending(e)[0];self.assertIs(row['chooser'],a);E.resolve(e,a,row['id'],selection='a-second');self.assertIs(row['chooser'],b)
   E.resolve(e,b,row['id'],selection='second');self.assertEqual({x['instance_id'] for x in H.entries(a)},{'a-first','second'});self.assertEqual({x['instance_id'] for x in H.entries(b)},{'object/1','a-second'});self.assertEqual(a.move_uses[mid],1);self.valid(e)
 def test_bestow_selects_giver_item_but_spare_target_slot_is_not_empty(self):
  e,a,b,mid=self.fixture('기프트패스');G.replace_baseline(e,a,'abilities',['배달새']);self.add(e,a,'예리한이빨','a-first')
  e.use_move(a,b,mid);self.assertFalse(E.pending(e));self.assertEqual(len(H.entries(b)),2);self.assertEqual(a.item,'예리한이빨')
  e,a,b,mid=self.f.fixture('기프트패스',held=('선제공격손톱',None),abilities=(('배달부',),()));self.add(e,a)
  e.use_move(a,b,mid);row=E.pending(e)[0];self.assertIs(row['chooser'],a);E.resolve(e,a,row['id'],selection='second');self.assertEqual(a.item,'선제공격손톱');self.assertEqual(b.item,'예리한손톱');self.valid(e)
 def test_magician_accept_then_actual_affected_holder_selects_before_free_cost(self):
  e,a,b,mid=self.fixture('몸통박치기');G.replace_baseline(e,a,'abilities',['매지션']);e.use_move(a,b,mid);row=E.pending(e)[0];before=deepcopy(a._action_history)
  E.resolve(e,a,row['id'],accept=True);self.assertIs(row['chooser'],b);self.assertEqual(a._action_history,before)
  E.resolve(e,b,row['id'],selection='second');self.assertEqual(a.item,'예리한손톱');self.assertEqual(b.item,'선제공격손톱');self.assertEqual(len(a._action_history),len(before)+1);self.valid(e)
 def test_incinerate_one_hp_alternative_or_selected_held_drop(self):
  for choice in ('hp_loss','drop'):
   e,a,b,mid=self.fixture('불태우기');e.use_move(a,b,mid);row=E.pending(e)[0];hp=b.hp
   result=E.resolve(e,b,row['id'],choice=choice)
   if choice=='drop':self.assertIsInstance(result,C.PendingDecision);E.resolve(e,b,row['id'],selection='second');self.assertEqual(b.hp,hp);self.assertEqual(b.item,'선제공격손톱')
   else:self.assertEqual(hp-b.hp,e.tick(b));self.assertEqual(len(H.entries(b)),2)
   self.valid(e)
 def test_pending_and_completed_graph_survive_gm_and_codec(self):
  e,a,b,mid=self.fixture();e.use_move(a,b,mid);row=E.pending(e)[0];e.gm.snapshot('dual');E.resolve(e,b,row['id'],selection='second');e.gm.restore('dual',reason='actual held choice rewind')
  loaded=self.roundtrip(e);idx=W.actor_index(loaded);saved=E.pending(loaded)[0];self.assertIs(saved['chooser'],idx[b.entity_id]);E.resolve(loaded,idx[b.entity_id],saved['id'],selection='second');self.valid(loaded)
  again=self.roundtrip(loaded);self.assertEqual(W.actor_index(again)[a.entity_id].item,'예리한손톱');self.valid(again)
 def test_capacity_loss_and_identical_effects_preserve_objects_as_explicit_pending(self):
  e,a,b,mid=self.fixture();G.replace_baseline(e,b,'abilities',[]);before=deepcopy(e._physical_objects);self.assertEqual(H.pending(b)[0]['kind'],'capacity_lost')
  with self.assertRaises(ValueError):e.use_move(a,b,mid)
  self.assertEqual(e._physical_objects,before);self.assertFalse(a.move_uses)
  e.gm.set_item(b,None,reason='observed disposition of selected extra slot',selection='second');self.assertEqual(b.item,'선제공격손톱');self.assertFalse(H.pending(b));self.valid(e)
  e,a,b,mid=self.f.fixture(held=(None,'선제공격손톱'),abilities=((),('배달부',)));self.add(e,b,'선제공격손톱','duplicate')
  self.assertEqual(len(H.entries(b)),2);self.assertEqual(b.initiative_bonus,10);self.assertEqual(H.pending(b)[0]['kind'],'identical_effect_stacking')
  e.gm.set_item(b,None,reason='observed first copy removed',selection='object/1');self.assertEqual(b.item,'선제공격손톱');self.assertEqual(b.initiative_bonus,10);self.assertFalse(H.pending(b));self.valid(e)
 def test_other_actor_turns_snapshot_and_ordinary_damage_do_not_read_ambiguous_item(self):
  e,a,b,mid=self.fixture('몸통박치기');e.start_round(e.everyone);e.start_of_turn(a);damage=e.use_move(a,b,mid);self.assertGreater(damage,0);e.end_of_turn(a)
  import root_common_engine as ROOT_CHECK
  context=ROOT_CHECK.host_context(e,{'attacker':a,'holder':b});self.assertEqual(len(context['actors']['holder']['held_equipment']),2)
  # The root adapter admits explicit rank names; this fixture supplies that input.
  b.spec['skills']={'감지':next(name for name,row in e.r.mech('gameplay/skill-rank-dice')['by_rank_name'].items() if row.get('dice')=='2d6')}
  projected=ROOT_CHECK.actor_projection(e,{'holder':b},{});self.assertIn('item',projected['holder']['modifier_sources'])
  result=e.skill_check(b,'감지',5);self.assertIsInstance(result,tuple);self.assertEqual(len(result),2)
  e.gm.snapshot('ordinary');e.gm.restore('ordinary',reason='dual world ordinary action');loaded=self.roundtrip(e);self.assertEqual(len(H.entries(W.actor_index(loaded)[b.entity_id])),2);self.valid(loaded)
 def test_held_food_waits_for_actual_intake_duration_without_cost(self):
  e,a,b,mid=self.f.fixture(held=(None,None),abilities=((),('배달부',)));self.add(e,b,'오랭열매','berry');self.add(e,b)
  before=deepcopy((b.spec,e._physical_objects));rng=e.rng.getstate();result=e.use_item(b,'오랭열매',held_selection='berry')
  self.assertIsInstance(result,C.PendingDecision);self.assertEqual((b.spec,e._physical_objects),before);self.assertEqual(e.rng.getstate(),rng);self.assertFalse(getattr(b,'_action_history',[]))

if __name__=='__main__':unittest.main(verbosity=2)
