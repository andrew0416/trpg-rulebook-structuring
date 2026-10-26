from copy import deepcopy
from pathlib import Path
import json,unittest
from unittest.mock import patch
import test_category2_battle_contest as FIX
import test_battle_contest_pending as PENDING
from engine import Engine
import battle_contest as BATTLE,substitute as SUB,move_completion as MC,state_codec as CODEC,world_entities as WORLD

class SubstituteDamageConsumerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  FIX.BattleContestTests.setUpClass()
  cls.rules=FIX.BattleContestTests.rules;cls.contest_rules=FIX.BattleContestTests.contest_rules
 def test_coat_damage_recoil_and_self_stage_keep_creature_prevention_and_restore(self):
  for move,destroy in [('move/이판사판태클',False),('move/이판사판태클',True),('move/용성군',False)]:
   with self.subTest(move=move,destroy=destroy):
    f=FIX.BattleContestTests();e,contest,trainers,teams,cid=f.fixture(moves=['move/대타출동',move])
    a,t=teams[0][0],teams[1][0]
    a.stats['atk']=30 if destroy else 5;t.stats['def']=11 if destroy else 29
    a.stats['spa']=5;t.stats['spd']=29
    BATTLE.begin_round(e,cid);BATTLE.start_turn(e,cid,t)
    BATTLE.perform_move(e,contest,cid,t,t,'move/대타출동')
    BATTLE.finish_turn(e,cid,t);BATTLE.start_turn(e,cid,a)
    coat=SUB.live(t)[0];before=coat['hp'];hp=a.hp;holder=t.hp
    with patch.object(Engine,'d20',return_value=12):
     out=BATTLE.perform_move(e,contest,cid,a,t,move,combat_options={'set_damage':True,'situational':100})
    row=e._move_completions[out['completion_id']];result=MC.recipient_result(row,t)
    receipt=result['substitute_damage'];damage=receipt['application']['damage']
    self.assertGreater(damage,0);self.assertEqual(result['dealt'],0);self.assertTrue(result['hit_prevented'])
    self.assertFalse(result['hit']);self.assertEqual(t.hp,holder)
    if destroy:self.assertEqual(SUB.live(t),[]);self.assertGreater(damage,before)
    else:self.assertLess(damage,before);self.assertEqual(coat['hp'],before-damage)
    if move=='move/용성군':self.assertEqual(a.stages['spa'],-2);self.assertEqual(a.hp,hp)
    else:self.assertEqual(a.hp,hp-damage//3)
    saved=CODEC.dump_engine(e);cold=CODEC.load_engine(self.rules,json.loads(json.dumps(saved)))
    old=cold.export_state();MC.refresh(cold,out['completion_id']);self.assertEqual(cold.export_state(),old)
    actual=deepcopy(receipt)
    for kind in ('foreign_event','amount','index','removed'):
     with self.subTest(tamper=kind):
      bad=deepcopy(actual)
      if kind=='foreign_event':bad['event_id']='foreign:153'
      elif kind=='amount':bad['application']['damage']+=1
      elif kind=='index':bad['application_index']+=10
      try:
       if kind=='removed':result.pop('substitute_damage')
       else:result['substitute_damage']=bad
       with self.assertRaisesRegex(ValueError,'Substitute'):
        MC.validate_world(e,WORLD.actor_index(e))
      finally:result['substitute_damage']=deepcopy(actual)
    MC.validate_world(e,WORLD.actor_index(e))

 def test_intercept_coat_damage_pending_cold_resume_counts_actual_recipient_once(self):
  PENDING.BattleContestPendingTests.rules=self.rules
  PENDING.BattleContestPendingTests.contest_rules=self.contest_rules
  with patch.dict(PENDING.__dict__,MOVE='move/이판사판태클'):
   f=PENDING.BattleContestPendingTests();original=PENDING.build_pokemon
   def learned(*args,**kwargs):
    kwargs['moves']=[*kwargs['moves'],'move/대타출동'];return original(*args,**kwargs)
   with patch.object(PENDING,'build_pokemon',side_effect=learned):f.fixture()
   self.addCleanup(f.doCleanups)
   BATTLE.finish_turn(f.e,f.cid,f.a)
   BATTLE.start_turn(f.e,f.cid,f.r)
   BATTLE.perform_move(f.e,f.c,f.cid,f.r,f.r,'move/대타출동')
   BATTLE.finish_turn(f.e,f.cid,f.r);BATTLE.finish_round(f.e,f.cid)
   BATTLE.begin_round(f.e,f.cid);BATTLE.start_turn(f.e,f.cid,f.a)
   f.a.stats['atk']=5;f.r.stats['def']=29
   hp,original_hp,holder_hp=f.a.hp,f.t.hp,f.r.hp
   with patch.object(Engine,'d20',return_value=12):event,token,plan=f.pending()
   self.assertEqual(f.a.hp,hp)
   ids=[f.a.entity_id,f.t.entity_id,f.r.entity_id]
   f.e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(f.e))))
   actors=WORLD.actor_index(f.e);f.a,f.t,f.r=[actors[uid] for uid in ids]
   with patch.object(Engine,'d20',return_value=12):f.choose(event)
   row=f.e._move_completions[token];received=MC.recipient_result(row,f.r)
   damage=received['substitute_damage']['application']['damage']
   self.assertEqual(damage,6);self.assertEqual(f.a.hp,hp-2)
   self.assertEqual((f.t.hp,f.r.hp),(original_hp,holder_hp));self.assertTrue(received['hit_prevented'])
   self.assertEqual(received['dealt'],0);self.assertEqual(f.a.move_uses[PENDING.MOVE],1)
   before=f.e.export_state();MC.refresh(f.e,token);self.assertEqual(f.e.export_state(),before)
   cold=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(f.e))))
   before=cold.export_state();MC.refresh(cold,token);self.assertEqual(cold.export_state(),before)
