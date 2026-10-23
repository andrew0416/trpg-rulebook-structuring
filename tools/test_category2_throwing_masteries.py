"""Throwing Masteries through native inventory, capture and equipped weapon actions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
import test_category3_capabilities as FIX
import test_category3_pokemon_activities as CAPTURE_FIX
import throwing_masteries as T,capability_actions as CAP,weapon_actions as W,turn as TURN
import state_grants as G,state_codec as CODEC,state_fields as F
import acquisition_qualification as Q,acquired_features as A,physical_limits as LIMITS

ROOT=Path(__file__).resolve().parents[1]

class ThrowingMasteriesTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.f=FIX.Tests('runTest');self.f.rules=self.r;self.f.setUp()
  self.e,self.a,self.b=self.f.e,self.f.a,self.f.b
  self.a.spec['skills'].update({'곡예':4,'전투':4})
 def own(self,alias=T.SOURCE):return G.transition(self.e,self.a,lambda e,c:c.spec.setdefault('edges',[]).append(alias))
 def turn(self):self.f.turn()
 def snap(self):return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,vars(self.a),vars(self.b),self.e.log_lines),{id(self.r):self.r})
 def throw(self,distance,**options):
  kw=dict(item='돌',destination=(self.a.pos[0]+distance,self.a.pos[1]),small_object=True,action_cost='standard',reason='actual observed small stone throw')
  kw.update(options);return self.e.throw_small_object(self.a,**kw)
 def equip(self,kind='단거리 사격무기',moves=None):
  return TURN.equip_weapon(self.e,self.a,{'name':'actual '+kind,'kind':kind,'grade':'간단','moves':moves or []})
 def capture(self,owned=True,distance=10):
  f=CAPTURE_FIX.PokemonActivityTests('runTest');f.rules=self.r;f.setUp()
  f.a.spec['items']['몬스터볼']=1;f.p.pos=(distance,0)
  if owned:G.transition(f.e,f.a,lambda e,c:c.spec['edges'].append(T.SOURCE))
  return f
 def test_native_throw_calls_common_ownership_qualification_and_source_composition(self):
  self.own();self.turn()
  with patch.object(A,'owned_rule_count',wraps=A.owned_rule_count) as acquired,patch.object(Q,'require',wraps=Q.require) as qualified,patch.object(LIMITS.COMPOSITION,'derive',wraps=LIMITS.COMPOSITION.derive) as composed:
   result=self.throw(8)
  self.assertEqual(result['distance'],8);self.assertIsNone(result['hit'])
  self.assertGreater(acquired.call_count,0);self.assertGreater(qualified.call_count,0)
  self.assertTrue(any(any(row['source']==T.SOURCE for row in c.args[1]) for c in composed.call_args_list))
  self.assertEqual((self.a.spec['items']['돌'],self.a.budget['standard']),(1,0))
 def test_unowned_actor_keeps_original_range_and_outside_refusal(self):
  self.assertEqual(CAP.throwing_range(self.e,self.a),6);self.turn();before=self.snap()
  with self.assertRaises(ValueError):self.throw(7)
  self.assertEqual(self.snap(),before)
 def test_source_range_is_passive_once_without_extra_state_or_roll(self):
  self.own();before=self.snap()
  for category in ('poke_ball','small_object'):
   for _ in range(3):self.assertEqual(CAP.throwing_range(self.e,self.a,category=category),8)
  self.assertEqual(self.snap(),before)
 def test_generic_throw_above_bonus_limit_and_blocked_path_are_atomic(self):
  self.own();self.turn();before=self.snap()
  with self.assertRaises(ValueError):self.throw(9)
  self.assertEqual(self.snap(),before)
  with patch.object(self.e.grid,'blocked',return_value=True):
   with self.assertRaises(ValueError):self.throw(8)
  self.assertEqual(self.snap(),before)
 def test_bonus_never_establishes_small_object_or_inventory_authority(self):
  self.own();self.turn();before=self.snap()
  self.assertEqual(type(self.throw(8,small_object=False)).__name__,'PendingDecision')
  with self.assertRaises(ValueError):self.throw(8,item='unowned')
  self.assertEqual(self.snap(),before)
 def test_effective_athletics_is_added_before_bonus_but_ordinary_acrobatics_qualifies(self):
  self.own()
  self.a.spec['skills']['육상']=6;self.a.spec['edges'].append('거장');self.a.spec['edge_choices']={'거장':['육상']}
  self.assertEqual(CAP.throwing_range(self.e,self.a),14)
  self.a.spec['skills']['곡예']=3
  with patch.object(CAP.S,'effective_rank',return_value=8):
   with self.assertRaisesRegex(ValueError,'Adept Acrobatics'):CAP.throwing_range(self.e,self.a)
 def test_native_poke_ball_at_extended_boundary_captures_and_consumes_once(self):
  f=self.capture()
  with patch.object(T,'extend',wraps=T.extend) as extension:out=f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20)
  self.assertTrue(out);self.assertTrue(f.p.captured)
  self.assertTrue(any(c.args[2]=='poke_ball' for c in extension.call_args_list))
  self.assertEqual(f.a.spec['items']['몬스터볼'],0);self.assertEqual(len(f.a.spec['capture_attempts']),1)
 def test_extended_poke_ball_miss_keeps_actual_recoverable_ball_and_no_free_capture(self):
  f=self.capture();self.assertFalse(f.e.throw_ball(f.a,f.p,fixed_accuracy=1,fixed_capture=20))
  self.assertFalse(f.p.captured);self.assertEqual(f.a.spec['items']['몬스터볼'],0)
  self.assertEqual(f.a.spec['capture_attempts']['capture-1']['status'],'recoverable_on_ground')
 def test_poke_ball_beyond_limit_and_unowned_bonus_do_not_pay_or_roll(self):
  for owned,distance in ((True,11),(False,10)):
   f=self.capture(owned,distance);before=f.state()
   self.assertFalse(f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20))
   self.assertEqual(f.state(),before);self.assertNotIn('capture_attempts',f.a.spec)
 def test_short_range_weapon_native_attack_reaches_six_metres(self):
  self.own();mid=self.equip();self.b.pos=(7,2);self.turn();before=self.b.hp
  with patch.object(self.e.rng,'randint',return_value=20):self.assertGreater(self.e.use_move(self.a,self.b,mid,set_damage=True),0)
  self.assertLess(self.b.hp,before);self.assertEqual(self.a.budget['standard'],0)
 def test_long_range_weapon_native_attack_reaches_fourteen_metres(self):
  self.own();mid=self.equip('장거리 사격무기');self.b.pos=(15,2);self.turn();before=self.b.hp
  with patch.object(self.e.rng,'randint',return_value=20):self.assertGreater(self.e.use_move(self.a,self.b,mid,set_damage=True),0)
  self.assertLess(self.b.hp,before)
 def test_long_range_minimum_and_extended_maximum_still_refuse_before_cost(self):
  self.own();mid=self.equip('장거리 사격무기');self.turn();move=W.prepare(self.e,self.a,self.r.move(mid))
  self.assertEqual((move['_weapon_attack']['minimum_distance'],W.range_spec(self.e,move)['origin']),(5,14))
  for distance in (4,15):
   self.b.pos=(1+distance,2);before=self.snap()
   with self.assertRaises(ValueError):self.e.use_move(self.a,self.b,mid)
   self.assertEqual(self.snap(),before)
 def test_wr_granted_move_native_grid_attack_preserves_frequency_and_shift(self):
  self.own();mid=self.equip(moves=['강타']);self.b.pos=(7,2);self.turn();self.e.at_initiative_count(20)
  with patch.object(self.e.rng,'randint',return_value=20):self.assertGreater(self.e.use_move_on(self.a,self.b,'move/강타',[self.a,self.b],weapon_id=mid),0)
  self.assertEqual(self.a.move_uses['move/강타'],1);self.assertEqual(self.a.budget['shift'],1)
  self.assertNotIn(mid,self.a.move_uses)
 def test_melee_and_independently_known_pokemon_move_ranges_are_unchanged(self):
  self.own();mid=self.equip('소형 근접무기')
  self.assertEqual(W.range_spec(self.e,W.prepare(self.e,self.a,self.r.move(mid)))['origin'],'melee')
  original=deepcopy(self.r.move('move/화염방사'));before=deepcopy(W.range_spec(self.e,original))
  self.assertEqual(W.range_spec(self.e,W.prepare(self.e,self.a,original)),before)
 def test_weapon_preparation_never_changes_catalog_or_double_adds_bonus(self):
  self.own();mid=self.equip();original=deepcopy((self.r.moves[mid],self.r.moves_mech[mid]))
  move=W.prepare(self.e,self.a,self.r.move(mid));self.assertEqual(W.range_spec(self.e,move)['origin'],6)
  self.assertEqual(W.range_spec(self.e,W.prepare(self.e,self.a,move))['origin'],6)
  self.assertEqual((self.r.moves[mid],self.r.moves_mech[mid]),original)
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].clear())
  self.assertEqual(W.range_spec(self.e,W.prepare(self.e,self.a,self.r.move(mid)))['origin'],4)
 def test_all_actual_aliases_work_and_duplicate_acquisition_is_rejected_atomically(self):
  for alias in T.NAMES:
   G.transition(self.e,self.a,lambda e,c:c.spec.__setitem__('edges',[alias]))
   self.assertEqual(CAP.throwing_range(self.e,self.a),8)
  before=self.snap()
  with self.assertRaises(ValueError):self.own()
  self.assertEqual(self.snap(),before)
 def test_owned_prerequisite_loss_by_actual_gm_edit_is_atomic(self):
  self.own();before=self.snap()
  with self.assertRaisesRegex(ValueError,'Adept Acrobatics'):self.e.gm.set_skill(self.a,'곡예',3,reason='actual permanent skill edit')
  self.assertEqual(self.snap(),before)
 def test_staged_invalid_acquisition_and_removal_then_skill_loss(self):
  self.e.gm.set_skill(self.a,'곡예',3,reason='ordinary Novice');before=self.snap()
  with self.assertRaisesRegex(ValueError,'Adept Acrobatics'):self.own()
  self.assertEqual(self.snap(),before)
  self.e.gm.set_skill(self.a,'곡예',4,reason='ordinary Adept');self.own()
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].clear())
  self.e.gm.set_skill(self.a,'곡예',3,reason='removed source');self.assertEqual(CAP.throwing_range(self.e,self.a),6)
 def test_invalid_actor_import_and_pokemon_cannot_claim_trainer_edge(self):
  spec=deepcopy(self.a.spec);spec['edges']=[T.SOURCE];spec['skills']['곡예']=3
  spec['id']='invalid imported trainer'
  with self.assertRaisesRegex(ValueError,'Adept Acrobatics'):self.e.gm.add_combatant(Combatant(self.r,spec),pos=(3,3),side='party')
  spec['skills']['곡예']=4;spec['kind']='pokemon'
  with self.assertRaises(ValueError):self.e.gm.add_combatant(Combatant(self.r,spec),pos=(3,3),side='party')
 def test_json_and_gm_restore_keep_bonus_once_and_actual_weapon_owner(self):
  self.own();mid=self.equip();saved=self.e.gm.snapshot()
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  actor=next(a for a in loaded.everyone if a.entity_id==self.a.entity_id)
  self.assertEqual(CAP.throwing_range(loaded,actor),8)
  self.assertEqual(W.range_spec(loaded,W.prepare(loaded,actor,self.r.move(mid)))['origin'],6)
  G.transition(self.e,self.a,lambda e,c:c.spec['edges'].clear());self.e.gm.restore(saved)
  self.assertEqual(CAP.throwing_range(self.e,self.a),8)
  self.assertEqual(W.range_spec(self.e,W.prepare(self.e,self.a,self.r.move(mid)))['origin'],6)
 def test_selected_literal_change_fails_before_native_throw_cost(self):
  self.own();self.turn();before=self.snap();selected=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**kw:uid+'/changed' if uid==T.SOURCE else selected(uid,**kw)):
   with self.assertRaises(ValueError):self.throw(8)
  self.assertEqual(self.snap(),before)
 def test_changed_chapter_or_csv_source_bytes_cannot_supply_bonus(self):
  self.own();original=Path.read_bytes
  for filename in ('input/ch03-skills-edges-feats.md','input/db/edges.csv'):
   def altered(path,*args,**kw):
    raw=original(path,*args,**kw)
    return raw+b'changed' if path.resolve()==(ROOT/filename).resolve() else raw
   before=self.snap()
   with patch.object(Path,'read_bytes',altered):
    with self.assertRaises(ValueError):CAP.throwing_range(self.e,self.a)
   self.assertEqual(self.snap(),before)
 def test_exact_duplicate_csv_is_one_source_and_one_range_contribution(self):
  self.own();value=T.policy(self.r)
  self.assertEqual((value['lines'],value['minimum_rank'],value['csv_duplicate']),([486,488],4,'C2CSV/input/db/edges.csv:R49:main'))
  self.assertEqual(CAP.throwing_range(self.e,self.a),8)

if __name__=='__main__':unittest.main()

