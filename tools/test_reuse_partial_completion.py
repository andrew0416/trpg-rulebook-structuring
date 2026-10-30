"""Native group completion and bounded, independently owned counter stages."""
from pathlib import Path
import sys,json,unittest
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
import move_completion as COMPLETE
import combat_stage_sources as STAGES
import counter_effects as COUNTERS
from state_codec import dump_engine,load_engine,StateCodecError

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,41)
  def actor(name,moves,types):
   return Combatant(self.r,build_trainer(self.r,name,20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=moves,extra={'types':types}))
  self.a=actor('user',['move/비축하기','move/꿀꺽','move/불사르기','move/마지막수단'],['불꽃'])
  self.b=actor('one',[],[]);self.c=actor('two',[],[])
  self.e.everyone=self.e.gm.everyone=[self.a,self.b,self.c]
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def test_stockpile_cap_and_clear_preserve_other_sources(self):
  STAGES.add_base(self.a,'independent','def',2,source='actual/other',ends='scene_end')
  for _ in range(4):
   result=self.e.apply_effect(self.a,self.a,{'type':'counter','name':'stockpile','delta':1,'max':3},nat=None,hit=True,dealt=0,src='move/비축하기')
   self.assertEqual(result,(1,0))
  self.assertEqual((self.a.counters['stockpile'],self.a.stages['def'],self.a.stages['spd']),(3,5,3))
  self.e.apply_effect(self.a,self.a,{'type':'counter','name':'stockpile','set':0,'requires':'stockpile > 0'},nat=None,hit=True,dealt=0,src='move/꿀꺽')
  self.assertEqual((self.a.counters['stockpile'],self.a.stages['def'],self.a.stages['spd']),(0,2,0))
  COUNTERS.validate(self.a)
 def test_linked_stage_handler_does_not_double_count(self):
  self.e.use_move(self.a,self.a,'move/비축하기')
  self.assertEqual((self.a.counters['stockpile'],self.a.stages['def'],self.a.stages['spd']),(1,1,1))
 def test_source_offsets_survive_visible_stage_cap(self):
  self.e.change_stage(self.a,'def',6)
  for _ in range(3):COUNTERS.change(self.e,self.a,{'name':'stockpile','delta':1,'max':3},'move/비축하기')
  COUNTERS.change(self.e,self.a,{'name':'stockpile','set':0},'move/꿀꺽')
  self.assertEqual((self.a.stages['def'],self.a.stages['spd']),(6,0))
 def test_after_all_targets_keeps_user_type_during_each_damage(self):
  self.e.targets_in_range=lambda *args:[self.b,self.c]
  observations=[]
  def damage(a,t,*args,**kw):observations.append((t.entity_id,list(a.types)));return 1
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'resolve_attack_damage',side_effect=damage):
   self.e.use_move_on(self.a,self.b,'move/불사르기',self.e.everyone)
  self.assertEqual(observations,[(self.b.entity_id,['불꽃']),(self.c.entity_id,['불꽃'])])
  self.assertEqual(self.a.types,['노말'])
  row=list(self.e._move_completions.values())[-1]
  self.assertEqual((row['phase'],len(row['results'])),('complete',2))
  del self.e.targets_in_range
  before=dump_engine(self.e);COMPLETE.refresh(self.e,row['id']);self.assertEqual(dump_engine(self.e),before)
 def test_after_use_counter_advances_once_even_when_all_miss(self):
  self.e.targets_in_range=lambda *args:[self.b,self.c]
  seen=[]
  def accuracy(*args,**kw):seen.append(self.a.counters.get('last_resort',0));return False,1,False
  with patch.object(self.e,'accuracy_check',side_effect=accuracy):
   self.e.use_move_on(self.a,self.b,'move/마지막수단',self.e.everyone)
  self.assertEqual(seen,[0,0]);self.assertEqual(self.a.counters['last_resort'],1)
 def test_interrupted_group_never_claims_completion(self):
  self.e.targets_in_range=lambda *args:[self.b,self.c]
  with patch.object(self.e,'accuracy_check',side_effect=ValueError('actual interruption')):
   with self.assertRaises(ValueError):self.e.use_move_on(self.a,self.b,'move/불사르기',self.e.everyone)
  self.assertEqual(self.a.types,['불꽃'])
  self.assertEqual(list(self.e._move_completions.values())[-1]['phase'],'interrupted')
 def test_json_restores_counter_ownership_and_completion(self):
  self.e.use_move(self.a,self.a,'move/비축하기')
  e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))));a=e.everyone[0]
  COUNTERS.validate(a);self.assertEqual(a.counters['stockpile'],1)
  COMPLETE.refresh(e);self.assertEqual(len(e._move_completions),1)
 def test_corrupt_counter_projection_rejected(self):
  COUNTERS.change(self.e,self.a,{'name':'stockpile','delta':1,'max':3},'move/비축하기')
  self.a.counters['stockpile']=2
  with self.assertRaises(StateCodecError):dump_engine(self.e)
 def test_native_damage_formula_uses_old_count_for_every_target(self):
  self.e.targets_in_range=lambda *args:[self.b,self.c]
  seen=[]
  def damage(a,t,move,*args,**kwargs):seen.append(self.e.damage_base(a,move,target=t));return 1
  for expected in (6,8):
   if expected==8:
    before=(self.a.budget.copy(),self.a.move_uses.copy(),self.a.counters.copy(),self.e.rng.getstate())
    self.assertEqual(self.e.use_move_on(self.a,self.b,'move/마지막수단',self.e.everyone),0)
    self.assertEqual(before,(self.a.budget,self.a.move_uses,self.a.counters,self.e.rng.getstate()))
    self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
   with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',side_effect=damage):
    self.e.use_move_on(self.a,self.b,'move/마지막수단',self.e.everyone)
   self.assertEqual(seen[-2:],[expected,expected])
   self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  self.assertEqual(self.a.counters['last_resort'],2)
 def test_native_pending_child_finishes_completion_only_after_actual_resolution(self):
  import maneuver_grants as GRANTS
  self.a.moves.append('move/괴력')
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)),patch.object(self.e,'roll_damage',return_value=1):
   self.e.use_move(self.a,self.b,'move/괴력')
  row=list(self.e._move_completions.values())[-1]
  self.assertNotEqual(row['phase'],'complete')
  e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  actual=next(x for x in e._effect_dispatch_receipts.values() if x.get('status')=='awaiting_input')
  grant_id=actual['result'].grant_id
  before=(e.everyone[0].budget.copy(),e.everyone[0].move_uses.copy(),e.everyone[1].hp,e.rng.getstate())
  GRANTS.resolve(e,e.everyone[0],grant_id,accept=False)
  self.assertEqual(list(e._move_completions.values())[-1]['phase'],'complete')
  COMPLETE.refresh(e)
  self.assertEqual(before,(e.everyone[0].budget,e.everyone[0].move_uses,e.everyone[1].hp,e.rng.getstate()))
 def test_swallow_without_a_count_is_a_paid_no_op_not_a_prerequisite_refusal(self):
  # r598 / core en11923: 'If the user has no Stockpiled count, Swallow does nothing' — paid, not refused (composed 2026-10-30).
  self.e.lose_hp(self.a,10,source='gm/fixture-injury');hp=self.a.hp;budget=deepcopy(self.a.budget)
  self.e.use_move(self.a,self.a,'move/꿀꺽')
  self.assertEqual((self.a.hp,self.a.move_uses['move/꿀꺽']),(hp,1));self.assertNotEqual(self.a.budget,budget);COUNTERS.validate(self.a)
 def test_uncapped_counter_is_not_silently_capped_at_arbitrary_99(self):
  self.a.counters['last_resort']=99
  COUNTERS.change(self.e,self.a,{'name':'last_resort','delta':1},'move/마지막수단')
  self.assertEqual(self.a.counters['last_resort'],100)

if __name__=='__main__':unittest.main()
