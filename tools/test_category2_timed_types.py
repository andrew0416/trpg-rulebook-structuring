"""Actual Roost plus shared source-owned type operations and real boundaries."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from state_codec import StateCodecError
import state_grants as G
import combat_timing as TIME
import effect_contracts as CONTRACTS
import effect_lifetimes as LIFE
import homebrew_state as HOME

class TimedTypeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core');cls.home=Rules(ROOT,ruleset='homebrew')
 def world(self,types=('노말','비행'),kind='trainer',rules=None):
  r=rules or self.rules;e=Engine(r,503)
  if kind=='pokemon':spec=build_pokemon(r,'피죤',30,moves=['move/날개쉬기'],abilities=[],pos=(1,1))
  else:spec=build_trainer(r,'Roost user',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=['move/날개쉬기'],pos=(1,1))
  spec['types']=list(types);a=Combatant(r,spec)
  b=Combatant(r,build_trainer(r,'other',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),pos=(2,1),side='wild'))
  e.gm.add_combatant(a);e.gm.add_combatant(b);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  return e,a,b
 def next_start(self,e,a,b):
  e.end_of_turn(a);e.start_of_turn(b,initiative_count=10);e.end_of_turn(b);e.end_round()
  e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
 def apply(self,e,a,recipient=None,source='gm/type-effect',**effect):
  return e.apply_effect(a,recipient or a,dict(type='type_change',**effect),nat=None,hit=True,dealt=0,src=source)
 def roundtrip(self,e,a):
  n=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  return n,next(c for c in n.everyone if c.entity_id==a.entity_id)
 def test_native_roost_heals_and_only_actual_users_next_start_ends_removal(self):
  for kind in ('trainer','pokemon'):
   for types,after in [(('노말','비행'),['노말']),(('비행',),[]),(('물',),['물'])]:
    with self.subTest(kind=kind,types=types):
     e,a,b=self.world(types,kind);a.hp=1
     e.use_move(a,a,'move/날개쉬기')
     self.assertEqual(a.hp,1+a.base_max_hp//2);self.assertEqual(a.types,after)
     self.assertEqual(a.move_uses['move/날개쉬기'],1);self.assertEqual(a.budget['standard'],0)
     self.assertEqual(len(TIME.records(a)),int('비행' in types))
     if '비행' in types:self.assertNotEqual(e.type_multiplier('땅',a)[0],0)
     e.end_of_turn(a);self.assertEqual(a.types,after)
     e.start_of_turn(b,initiative_count=10);e.end_of_turn(b);self.assertEqual(a.types,after)
     e.end_round();self.assertEqual(a.types,after)
     e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
     self.assertEqual(a.types,list(types));self.assertFalse(TIME.records(a))
     if '비행' in types:self.assertEqual(e.type_multiplier('땅',a)[0],0)
 def test_native_roost_full_hp_fraction_and_injury_ceiling_are_distinct(self):
  e,a,b=self.world();e.gm.set_injuries(a,2,reason='observed two ordinary injuries');a.hp=1
  e.use_move(a,a,'move/날개쉬기')
  self.assertEqual(a.hp,min(a.max_hp,1+a.base_max_hp//2))
  self.assertEqual(a.types,['노말'])
  e.end_encounter(e.everyone);self.assertEqual(a.types,['노말','비행'])
 def test_shared_add_remove_replace_fallback_and_independent_expirations(self):
  e,a,b=self.world(('불꽃',))
  self.assertEqual(self.apply(e,a,lose_type='불꽃',fallback='노말',until='encounter_end'),(1,0))
  self.assertEqual(a.types,['노말'])
  self.apply(e,a,add_type='고스트',until='scene_end')
  self.assertEqual(a.types,['노말','고스트'])
  self.apply(e,a,set_type='물',single_type=True,until="start of user's next turn")
  self.assertEqual(a.types,['물'])
  self.next_start(e,a,b);self.assertEqual(a.types,['노말','고스트'])
  e.end_encounter(e.everyone);self.assertEqual(a.types,['불꽃','고스트'])
  TIME.end_scene(e);self.assertEqual(a.types,['불꽃'])
  self.assertFalse(any('timed_type_contract' in x for x in G.state(a)['sources'].values()))
 def test_same_source_reapplications_keep_independent_owner_boundaries(self):
  e,a,b=self.world(('불꽃',))
  self.apply(e,a,b,add_type='고스트',target='target',until="start of user's next turn")
  self.apply(e,b,b,add_type='고스트',target='target',until="start of user's next turn")
  self.assertEqual(b.types,['고스트']);self.assertEqual(len(TIME.records(b)),2)
  e.end_of_turn(a);e.start_of_turn(b,initiative_count=10)
  self.assertEqual(b.types,['고스트']);self.assertEqual(len(TIME.records(b)),1)
  e.end_of_turn(b);e.end_round();e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  self.assertEqual(b.types,[]);self.assertFalse(TIME.records(b))
 def test_native_removal_preserves_later_permanent_and_independent_source_edits(self):
  e,a,b=self.world();e.use_move(a,a,'move/날개쉬기')
  G.type_operation(a,'add',['물'],'separate/water')
  e.gm.set_types(a,['풀','비행'],reason='independent observed base type change')
  self.assertEqual(a.types,['풀','물'])
  self.next_start(e,a,b);self.assertEqual(a.types,['풀','비행','물'])
  G.remove_owned(e,a,'separate/water');self.assertEqual(a.types,['풀','비행'])
 def test_gm_and_durable_restore_preserve_owner_receipt_and_exact_expiration(self):
  e,a,b=self.world();e.use_move(a,a,'move/날개쉬기');e.gm.snapshot('live roost')
  self.next_start(e,a,b);self.assertEqual(a.types,['노말','비행'])
  e.gm.restore('live roost');self.assertEqual(a.types,['노말'])
  self.assertIs(TIME.records(a)[0]['turn_owner'],a)
  n,c=self.roundtrip(e,a);other=next(x for x in n.everyone if x.entity_id==b.entity_id)
  self.assertIs(TIME.records(c)[0]['turn_owner'],c)
  self.next_start(n,c,other);self.assertEqual(c.types,['노말','비행'])
  self.next_start(e,a,b);self.assertEqual(a.types,['노말','비행'])
 def test_forged_lifetime_source_receipt_or_orphan_cannot_save_or_restore(self):
  for mode in ('deadline','source','receipt','orphan'):
   e,a,b=self.world();e.use_move(a,a,'move/날개쉬기');record=TIME.records(a)[0]
   if mode=='deadline':record['turn_start_deadline']+=1
   elif mode=='source':record['grant_source']='not-an-issued-source'
   elif mode=='receipt':record['effect_receipt']=object()
   else:a.custom_conditions.pop(TIME.KEY)
   with self.subTest(mode=mode):
    with self.assertRaises(StateCodecError):e.export_state()
    with self.assertRaises(ValueError):e.gm.snapshot('invalid')
  e,a,b=self.world();e.use_move(a,a,'move/날개쉬기');e.gm.snapshot('stored')
  snap=e.gm.snapshots['stored'];snap['combatants'][id(a)]['custom_conditions'][TIME.KEY][0]['turn_start_deadline']+=1
  before=(a.types[:],e.round_no,a.hp)
  with self.assertRaises(ValueError):e.gm.restore('stored')
  self.assertEqual(before,(a.types,e.round_no,a.hp))
 def test_unreviewed_native_lifetimes_and_invalid_contracts_fail_before_cost(self):
  e,a,b=self.world()
  # Burn Up/Double Shock now use the actual all-target completion consumer.
  for name in ('핼러윈','숲의저주','마법가루','물붓기'):
   a.moves.append('move/'+name)
   before=(a.budget.copy(),a.move_uses.copy(),a.types[:],a.hp,b.hp,e.rng.getstate())
   with self.subTest(move=name):
    with self.assertRaises(CONTRACTS.EffectContractError):e.use_move(a,b,'move/'+name)
    self.assertEqual(before,(a.budget,a.move_uses,a.types,a.hp,b.hp,e.rng.getstate()))
  for payload in ({'add_type':'물','lose_type':'불꽃'},{'add_type':'물','fallback':'노말'},{'set_type':'unresolved option'},{'add_type':'물','unknown_semantics':True}):
   with self.subTest(payload=payload):
    with self.assertRaises(CONTRACTS.EffectContractError):self.apply(e,a,until='scene_end',**payload)
 def test_type_lock_prevents_grant_without_breaking_healing_or_other_sources(self):
  e,a,b=self.world(kind='pokemon',rules=self.home)
  HOME.observe_type(e,a,'물',reason='observed Tera type');HOME.observe_active(e,a,True,reason='actual active Tera')
  before=deepcopy(a.spec);a.hp=1;e.use_move(a,a,'move/날개쉬기')
  self.assertEqual(a.types,['물']);self.assertEqual(a.hp,1+a.base_max_hp//2)
  self.assertFalse(TIME.records(a))
  self.apply(e,a,add_type='고스트',until='scene_end')
  self.assertEqual(a.types,['물']);self.assertFalse(TIME.records(a))
  self.assertFalse(any('timed_type_contract' in row for row in a.spec.get(G.KEY,{}).get('sources',{}).values()))

if __name__=='__main__':unittest.main()
