"""Tumbler consumes the published ordinary/effect-rank and retraining contracts."""
from pathlib import Path
from copy import copy,deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from rulings import Rulings
from tumbler_fixture import TumblerScene
import tumbler as T,skill_modifiers as SK,passive_events as P,trainer_retraining as RT

class TumblerAuditIntegrationTests(TumblerScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.rules=copy(self.base);self.rules.rulings=Rulings();self.setup()
 def declared(self,rank):
  self.rules=copy(self.base);self.rules.rulings=Rulings()
  self.rules.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.Mythic',{'rank':rank,'dice':'7d6','eng':'Mythic'},reason='Explicit campaign ordinary rank and separate seven-die pool',scope='campaign',rules=self.rules)
  self.setup(rank=rank)
 def incoming(self,expected):
  self.begin(self.t,40);hp=self.a.hp;baseline=self.e.roll_damage(self.t,self.a,self.rules.move('move/몸통박치기'),set_damage=True)
  self.e.watch_move_defense(self.a,[{'actor_id':self.a.entity_id,'source':T.SPLASH}],reason='actual acquired Flip Out damage-rank consumption')
  with self.assertRaises(P.PassiveEventPending):self.use(self.t,self.a,'move/몸통박치기')
  event_id=self.e._passive_pending
  self.e.choose_move_defense(event_id,self.a,use=True,options={'jump':None},reason='use actual Splash and selected effective rank')
  event=self.e._passive_events[event_id];state=self.e._move_completions[event['completion_id']]['defense'][self.a.entity_id]
  self.assertEqual(state['attempts'][0]['splash']['damage_reduction'],expected)
  self.assertEqual(hp-self.a.hp,max(1,baseline-expected));self.valid();self.restore();self.valid()
 def test_declared_seven_and_ten_acquire_complete_family_and_restore_actual_seven_dice(self):
  for rank in (7,10):
   with self.subTest(rank=rank):
    self.declared(rank);self.family(T.BURST)
    self.assertEqual(T.acquired(self.a,T.BURST)['snapshot']['rank'],rank)
    self.assertEqual(set(r['feature_id'] for r in T.records(self.a,active=True)),set(T.FEATURES))
    roll=self.e.skill_roll(self.a,'곡예',fixed=[2]*7)
    self.assertEqual((roll.rank,len(roll.faces),roll.total),(rank,7,14));self.valid();self.restore();self.valid()
    self.assertEqual(SK.rank(self.e.r,self.a,'곡예')[2],rank)
    self.assertEqual(len(self.e.skill_roll(self.a,'곡예',fixed=[1]*7).faces),7)
 def test_declared_rank_and_virtuoso_splash_use_effect_rank_not_dice_or_acquisition_rank(self):
  for rank,virtuoso,expected in ((10,False,20),(6,True,16)):
   with self.subTest(rank=rank,virtuoso=virtuoso):
    if virtuoso:
     self.rules=copy(self.base);self.rules.rulings=Rulings();self.setup(extra_edges=['edge/거장'],edge_choices={'edge/거장':['곡예']})
    else:self.declared(rank)
    self.family(T.FLIP)
    self.assertEqual(T.acquired(self.a,T.FLIP)['snapshot']['rank'],rank)
    self.assertEqual(SK.effective_rank(self.rules,self.a,'곡예'),expected//2)
    self.assertEqual(len(self.e.skill_roll(self.a,'곡예',fixed=[1]*(6 if virtuoso else 7)).faces),6 if virtuoso else 7)
    self.incoming(expected)
 def test_native_virtuoso_retraining_cleans_live_choice_preserves_tumbler_receipts_and_restores(self):
  self.setup(extra_edges=['edge/거장'],edge_choices={'edge/거장':['곡예']});self.family(T.FLIP)
  receipts=deepcopy(T.records(self.a));moves=list(self.a.moves);speed=self.a.stats['spe']
  owned=RT._owned(self.a);sources={uid:RT.owned_source(self.e,self.a,uid) for uid in owned}
  retained={sid:list(self.a.spec['state_grants']['sources'][sid].get('withdrawal_dependencies',[])) for uid,sid in sources.items() if uid!='edge/거장'}
  for child,parents in RT._native_dependencies(self.e,self.a,owned).items():
   if child!='edge/거장':retained[sources[child]]=[sources[parent] for parent in parents]
  decision=dict(request_id='tumbler-retire-virtuoso',reason='actual source withdrawal',gm_decision={'allowed':True,'reason':'GM reviewed retained Tumbler prerequisites'},retained_dependencies=retained)
  result=self.e.retrain_trainer_source(self.a,'edge/거장',**decision)
  self.assertNotIn('edge/거장',self.a.spec['edge_choices']);self.assertEqual(T.records(self.a),receipts)
  self.assertEqual((self.a.moves,self.a.stats['spe']),(moves,speed));self.assertEqual(SK.effective_rank(self.rules,self.a,'곡예'),6)
  self.valid();self.restore();self.valid();before=self.e.export_state();self.assertEqual(self.e.retrain_trainer_source(self.a,'edge/거장',**decision),result);self.assertEqual(self.e.export_state(),before)
  self.incoming(12)
