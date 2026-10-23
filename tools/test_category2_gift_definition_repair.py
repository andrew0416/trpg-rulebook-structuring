"""Reviewed acquired Gift identities reuse native grants and actual consumers.
These tests do not approve acquisition or certify every Barrier terrain effect.
"""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import items,state_grants as G,state_codec as CODEC,encounter
GROUND='feat/그란돈의-메이저-기프트-어스셰이커'
DREAM='feat/메이저-기프트-해몽'
BARRIER='feat/메이저-기프트-베리어'
CASES=((GROUND,'capabilities','지형변화'),(DREAM,'capabilities','꿈읽기'),(BARRIER,'moves','move/배리어'))
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def fixture(self,uid):
  e=Engine(self.r,37);e.grid=Grid(8,8)
  def actor(identity,pos,feats):
   return Combatant(self.r,dict(id=identity,name=identity,kind='trainer',level=30,size='Medium',stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),types=[],abilities=[],capabilities=[],moves=[],feats=feats,pos=pos))
  c=actor('gift-holder',(1,1),[uid]);target=actor('dream-target',(4,4),[])
  e.everyone=e.gm.everyone=[c,target]
  return e,c,target
 def source(self,c,uid):return 'feature:'+c.entity_id+':'+uid
 def begin(self,e,c):
  if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
  e.start_round(e.everyone);e.start_of_turn(c,initiative_count=20)
 def observe_dream(self,e,t):
  e.gm.add_condition(t,'잠듦',reason='observed sleeping subject',force=True)
  e.gm.observe_dream(t,'a blue mountain',reason='current observed dream')
 def consume(self,e,c,t,uid):
  if uid==GROUND:
   self.begin(e,c);return e.shape_ground(c,[{'cell':[2,1],'terrain':'rough'}],reason='actual adjacent ground')['source']
  if uid==DREAM:return e.read_dream(c,t)['content']
  return 'move/배리어' in encounter.usable_moves(e,c)
 def test_all_definitions_register_once_restore_and_revoke_without_activation(self):
  for uid,field,value in CASES:
   with self.subTest(source=uid):
    e,c,t=self.fixture(uid);self.assertEqual(items.register_feats(e,c),1)
    self.assertIn(value,G.effective(c,field));self.assertFalse(any(str(v).startswith('당신은') for v in G.effective(c,field)))
    self.assertFalse(e.grid.rough);self.assertNotIn('groundshaper_history',c.spec)
    self.assertEqual(c.move_uses,{})
    before=deepcopy(c.spec);items.register_feats(e,c);self.assertEqual(c.spec,before)
    e.end_encounter(e.everyone);self.assertIn(value,G.effective(c,field))
    e.gm.snapshot('gift');loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(e))))
    a=loaded.everyone[0];self.assertIn(value,G.effective(a,field))
    G.revoke(a,self.source(a,uid),engine=loaded);self.assertNotIn(value,G.effective(a,field))
    G.revoke(c,self.source(c,uid),engine=e);self.assertNotIn(value,G.effective(c,field))
    e.gm.restore('gift');self.assertIn(value,G.effective(c,field))
 def test_native_capability_use_after_both_restores_and_revoke(self):
  for uid,expected in ((GROUND,'capability/지형변화'),(DREAM,'a blue mountain')):
   with self.subTest(source=uid):
    e,c,t=self.fixture(uid);items.register_feats(e,c)
    if uid==DREAM:self.observe_dream(e,t)
    self.assertEqual(self.consume(e,c,t,uid),expected);e.gm.snapshot('used')
    loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(e))))
    self.assertEqual(self.consume(loaded,*loaded.everyone,uid),expected)
    e.gm.restore('used');self.assertEqual(self.consume(e,c,t,uid),expected)
    G.revoke(c,self.source(c,uid),engine=e)
    with self.assertRaises(ValueError):self.consume(e,c,t,uid)
 def test_absent_sources_and_independent_baselines_are_preserved(self):
  for uid,field,value in CASES:
   with self.subTest(source=uid):
    e,c,t=self.fixture(uid);c.spec['feats']=[];self.assertEqual(items.register_feats(e,c),0);self.assertNotIn(value,G.effective(c,field))
    G.set_baseline(c,field,[value]);c.spec['feats']=[uid];items.register_feats(e,c)
    G.grant(c,field,value,'independent-source','fixture');G.revoke(c,self.source(c,uid),engine=e)
    self.assertIn(value,G.effective(c,field));G.revoke(c,'independent-source',engine=e);self.assertIn(value,G.effective(c,field))
 def test_dream_gift_does_not_bypass_mindlock_or_share_without_mist(self):
  e,c,t=self.fixture(DREAM);items.register_feats(e,c);self.observe_dream(e,t)
  with self.assertRaises(ValueError):e.read_dream(c,t,share=True)
  G.grant(t,'capabilities','Mindlock','mindlock-source','fixture')
  with self.assertRaises(ValueError):e.read_dream(c,t)
  G.revoke(t,'mindlock-source',engine=e);self.assertEqual(e.read_dream(c,t)['content'],'a blue mountain')
 def test_barrier_is_available_but_grant_does_not_consume_move_usage(self):
  e,c,t=self.fixture(BARRIER);items.register_feats(e,c)
  self.assertIn('move/배리어',encounter.usable_moves(e,c));self.assertEqual(c.move_uses,{})
  G.revoke(c,self.source(c,BARRIER),engine=e);self.assertNotIn('move/배리어',encounter.usable_moves(e,c))
if __name__=='__main__':unittest.main()
