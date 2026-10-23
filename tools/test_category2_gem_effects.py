"""Real Gem stock, source-owned next-Move effects, activation and restoration."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
import test_category2_event_effects as _fixture_test_category2_event_effects
from builder import build_pokemon
import event_effects as N,effect_instances as E,gem_effects as GEM
import items as I,world_entities as W,held_equipment as H,state_codec as CODEC

class GemEffectTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 known=_fixture_test_category2_event_effects.EventEffectTests.known
 begin=_fixture_test_category2_event_effects.EventEffectTests.begin
 next_turn=_fixture_test_category2_event_effects.EventEffectTests.next_turn
 snap=_fixture_test_category2_event_effects.EventEffectTests.snap
 valid=_fixture_test_category2_event_effects.EventEffectTests.valid
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
  self.p=self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'items':{}}))
  self.other=self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.e.gm.observe_loyalty(self.p,6,reason='actual Move obedience');self.other.pos=(1,0)
 def gem(self,actor=None,ty='불꽃',**options):
  actor=actor or self.p;name=ty+'주얼';actor.spec.setdefault('items',{}).setdefault(name,1)
  return self.e.use_item(actor,name,**options)
 def physical(self,actor,name,uid):
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual identified Gem',kind='item_instance',item_rule_id='item/'+name,owner_id=actor.entity_id)
  if actor.kind=='pokemon':I.equip_held(self.e,actor,name,source_instance_id=uid)
  else:I.register_item(self.e,actor,name,source_instance_id=uid)
 def attack(self,name='화염방사',*,roll=18):
  with patch.object(self.e,'d20',return_value=roll):return self.e.use_move(self.p,self.other,'move/'+name,set_damage=True)
 def test_all_eighteen_parameterized_definitions_use_actual_stock_and_shared_instances(self):
  for ty in I.TYPES:
   out=self.gem(self.a,ty);record=N.live(self.a)[-1]
   self.assertEqual(out['effect_id'],record['id']);self.assertEqual(self.a.spec['items'][ty+'주얼'],0)
   self.assertEqual(record['selector']['type'],ty);self.assertEqual(record['effect'],{'kind':'damage_base_bonus','amount':3})
  self.assertEqual(len(N.live(self.a)),18);self.assertEqual(len({r['id'] for r in N.live(self.a)}),18)
  self.assertIsNone(self.a.next_attack);self.valid();self.assertTrue(self.restored().validate_state()['valid'])
 def test_actual_held_and_both_trainer_slots_consume_only_selected_physical_object(self):
  self.physical(self.p,'불꽃주얼','p-gem');self.assertFalse(N.live(self.p));self.assertFalse(self.p.registry)
  self.begin(self.p);before=dict(self.p.budget);self.gem(held_selection='p-gem')
  self.assertEqual(self.p.budget,before);self.assertEqual(self.p.spec['items']['불꽃주얼'],1);self.assertFalse(H.entries(self.p))
  self.assertIn('consumed',self.e._physical_objects['p-gem'])
  self.e.end_of_turn(self.p)
  for name,uid in [('불꽃주얼','t-fire'),('물주얼','t-water')]:self.physical(self.a,name,uid)
  rows=I.equipment_options(self.a,('반대손','장신구'));self.assertEqual({tuple(x['slots']) for x in rows},{('반대손',),('장신구',)})
  self.e.start_of_turn(self.a,initiative_count=19)
  self.e.use_item(self.a,'물주얼',held_selection='t-water');self.assertNotIn('consumed',self.e._physical_objects['t-fire']);self.assertIn('consumed',self.e._physical_objects['t-water'])
  self.assertEqual(I.equipment_options(self.a,('반대손','장신구'))[0]['instance_id'],'t-fire');self.valid()
 def test_refusal_wrong_target_and_post_payment_failure_are_atomic(self):
  self.p.spec['items']={'불꽃주얼':1};before=self.snap()
  with self.assertRaises(ValueError):self.e.use_item(self.p,'불꽃주얼',self.other)
  self.assertEqual(before,self.snap())
  with patch.object(N,'grant',side_effect=ValueError('injected later effect failure')):
   with self.assertRaises(ValueError):self.e.use_item(self.p,'불꽃주얼')
  self.assertEqual(before,self.snap());self.assertFalse(N.live(self.p))
  self.physical(self.p,'불꽃주얼','gem');before=self.snap()
  with self.assertRaises(ValueError):self.e.use_item(self.p,'물주얼',held_selection='gem')
  self.assertEqual(before,self.snap())
 def test_off_type_attempt_preserves_but_matching_miss_consumes_once(self):
  self.known(self.p,'화염방사','전기쇼크');self.begin(self.p);self.gem();uid=N.live(self.p)[0]['id']
  self.attack('전기쇼크',roll=1);self.assertEqual(N.live(self.p)[0]['id'],uid)
  self.next_turn(self.p);self.attack(roll=1);self.assertFalse(N.live(self.p))
  end=self.p.spec[N.HISTORY][-1];self.assertEqual(end['id'],uid);self.assertEqual(end[E.KEY]['end_event']['kind'],'matching_move_use')
  self.assertEqual(self.other.hp,self.other.max_hp);self.valid();self.assertFalse(hasattr(self.e,'_event_use_scopes'))
 def test_actual_damage_chart_receives_three_db_not_three_flat_damage_or_preview(self):
  self.known(self.p,'화염방사');move=self.r.move('move/화염방사');base=self.e.damage_base(self.p,move)
  self.begin(self.p);self.gem();self.assertEqual(self.e.damage_base(self.p,move),base);self.assertEqual(len(N.live(self.p)),1)
  actual=self.e.damage_base;seen=[]
  def observe(a,m,**kw):
   value=actual(a,m,**kw);seen.append(value);return value
  with patch.object(self.e,'damage_base',side_effect=observe):self.attack()
  self.assertEqual(seen,[base+3]);self.assertEqual(self.e.damage_base(self.p,move),base);self.assertFalse(N.live(self.p));self.valid()
 def test_actual_type_override_matches_without_premature_consumption_and_other_sources_survive(self):
  self.known(self.p,'화염방사');self.begin(self.p);self.gem(ty='전기');self.gem(ty='불꽃');self.p.type_override_next='전기'
  self.attack();self.assertIsNone(self.p.type_override_next)
  self.assertEqual([r['source'] for r in N.live(self.p)],['item/불꽃주얼']);self.assertEqual(self.p.spec[N.HISTORY][-1]['source'],'item/전기주얼');self.valid()
 def test_native_multi_target_activation_gets_one_contribution_for_all_targets_without_replay(self):
  from grid import Grid
  self.e.grid=Grid(8,8);self.a.pos=(2,0);self.known(self.p,'스피드스타');self.begin(self.p);self.gem(ty='노말')
  move=self.r.move('move/스피드스타');base=self.e.damage_base(self.p,move);actual=self.e.damage_base;seen=[]
  def observe(a,m,**kw):
   value=actual(a,m,**kw);seen.append(value);return value
  with patch.object(self.e,'d20',return_value=18),patch.object(self.e,'damage_base',side_effect=observe):self.e.use_move_on(self.p,self.other,'move/스피드스타',[self.p,self.other,self.a])
  self.assertEqual(len(seen),2);self.assertEqual(seen,[base+3,base+3]);self.assertEqual(len(self.p.spec[N.HISTORY]),1)
  self.assertFalse(N.live(self.p));self.assertEqual(self.e.damage_base(self.p,move),base);self.assertFalse(hasattr(self.e,'_event_use_scopes'));self.valid()
 def test_matching_status_move_uses_effect_and_no_invented_turn_or_scene_expiry(self):
  self.known(self.p,'울음소리');self.begin(self.p);self.gem(ty='노말');self.gem(ty='물');self.next_turn(self.p)
  self.assertEqual(len(N.live(self.p)),2);self.attack('울음소리')
  self.assertEqual([r['source'] for r in N.live(self.p)],['item/물주얼']);self.assertEqual(self.other.hp,self.other.max_hp)
  self.e.end_of_turn(self.p);self.e.end_encounter();self.assertEqual(len(N.live(self.p)),1);self.valid()
 def test_unused_and_consumed_physical_effect_resume_after_gm_and_durable_restoration(self):
  self.physical(self.p,'불꽃주얼','gem');self.known(self.p,'화염방사');self.begin(self.p);self.gem(held_selection='gem')
  uid=N.live(self.p)[0]['id'];snapshot=self.e.gm.snapshot();self.attack(roll=1);self.e.gm.restore(snapshot)
  self.assertEqual(N.live(self.p)[0]['id'],uid);loaded=self.restored();p=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id);target=next(a for a in loaded.gm.everyone if a.entity_id==self.other.entity_id)
  with patch.object(loaded,'d20',return_value=18):loaded.use_move(p,target,'move/화염방사',set_damage=True)
  self.assertFalse(N.live(p));self.assertEqual(p.spec[N.HISTORY][-1]['id'],uid);self.assertTrue(loaded.validate_state()['valid'])
  self.attack(roll=1);self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
  with self.assertRaises(ValueError):self.e.use_item(self.p,'불꽃주얼',held_selection='gem')
 def test_invalid_source_stock_and_payload_reject_before_restore_or_live_action_cost(self):
  self.gem();self.known(self.p,'화염방사');self.begin(self.p);row=N.live(self.p)[0];good=deepcopy(row)
  for field,value in [('item_stock',{'kind':'quantity','item_id':'item/물주얼','count':1}),('effect',{'kind':'damage_base_bonus','amount':True})]:
   row.clear();row.update(deepcopy(good));row[field]=value
   with self.assertRaises(ValueError):self.e.gm.snapshot()
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with patch.object(E,'validate_actor',return_value=True),patch.object(E,'validate_world',return_value=True):bad=self.e.gm.snapshot();payload=CODEC.dump_engine(self.e)
  row.clear();row.update(good);before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.restore(bad)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  self.assertEqual(before,self.snap());row['item_stock']['count']=True;before=self.snap()
  with self.assertRaises(ValueError):self.attack()
  self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
