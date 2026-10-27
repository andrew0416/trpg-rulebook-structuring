"""Non-Smite printed self drops finish once after the actual native Move."""
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules
import test_book_conquerors_march as PASS
import test_post_damage_self_stage as FIX
import move_completion as MC
import world_entities as WORLD
import substitute as SUB

CHANGES={'move/인파이트':{'def':-1,'spd':-1},'move/엄청난힘':{'atk':-1,'def':-1},'move/스케일노이즈':{'def':-1}}
class NonSmiteSelfCostTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')
 def self_rows(self,e,a,mid):return [r for r in getattr(e,'_effect_dispatch_receipts',{}).values() if r['actor'] is a and r['source_id']==mid and r['effect'].get('type')=='stage_change' and r['effect'].get('target')=='self']
 def once(self,e,a,mid,row):
  self.assertEqual(row['phase'],'complete')
  self.assertEqual({stat:a.stages[stat] for stat in CHANGES[mid]},CHANGES[mid])
  receipts=self.self_rows(e,a,mid);self.assertEqual(sorted(r['effect']['stat'] for r in receipts),sorted(CHANGES[mid]));self.assertTrue(all(r['status']=='completed' for r in receipts))
  before=e.export_state();MC.refresh(e,row['id']);self.assertEqual(e.export_state(),before)
  loaded=Engine.import_state(self.rules,json.loads(json.dumps(before,ensure_ascii=False)))
  actor=WORLD.actor_index(loaded)[a.entity_id];before=loaded.export_state();MC.refresh(loaded,row['id']);self.assertEqual(loaded.export_state(),before)
  self.assertEqual({stat:actor.stages[stat] for stat in CHANGES[mid]},CHANGES[mid])
 def world(self,mid):
  f=FIX.PostDamageSelfStageTests();f.rules=self.rules
  return f.world(mid)
 def test_actual_mounted_dash_pass_applies_one_cost_after_both_recipients(self):
  for mid in ('move/인파이트','move/엄청난힘'):
   with self.subTest(move=mid):
    f=PASS.ConquerorsMarchTests();f.rules=self.rules;f.setup(moves=[mid])
    for t in (f.enemy,f.other):
     f.e.gm.set_stat(t,'hp',value=400,reason='actual durable recipient before the complete Pass')
     f.e.gm.set_hp(t,value=t.base_max_hp,reason='initial healthy native target')
    f.start();f.order();f.close(f.a);f.e.start_of_turn(f.p)
    stages=[];original=Engine.roll_damage;fields=tuple(CHANGES[mid]);before=[t.hp for t in (f.enemy,f.other)]
    def damage(e,a,t,move,*args,**kw):
     if a.entity_id==f.p.entity_id and move['id']==mid:stages.append(tuple(a.stages[x] for x in fields))
     return original(e,a,t,move,*args,**kw)
    with patch.object(Engine,'d20',return_value=19),patch.object(Engine,'roll_damage',damage):result=f.pass_move(mid)
    row=f.e._move_completions[result['completion_id']]
    self.assertEqual(stages,[tuple(0 for _ in fields)]*2);self.assertEqual(len(row['results']),2)
    self.assertTrue(all(t.hp<before[i] for i,t in enumerate((f.enemy,f.other))))
    self.assertEqual(f.p.move_uses[mid],1);self.assertEqual(f.p.budget['standard'],0)
    self.once(f.e,f.p,mid,row)
 def test_clanging_scales_burst_uses_original_defense_then_one_drop(self):
  mid='move/스케일노이즈';e,a,targets=self.world(mid)
  for t,pos in zip(targets,((3,2),(2,3))):e.gm.set_position(t,pos,reason='two actual Burst1 recipients')
  stages=[];original=Engine.roll_damage;before=[t.hp for t in targets]
  def damage(engine,actor,target,move,*args,**kw):
   if actor is a and move['id']==mid:stages.append(a.stages['def'])
   return original(engine,actor,target,move,*args,**kw)
  with patch.object(Engine,'d20',return_value=19),patch.object(Engine,'roll_damage',damage):e.use_move_on(a,targets[0],mid,e.everyone,aim=a.pos,set_damage=True)
  row=next(r for r in e._move_completions.values() if r['actor'] is a and r['move_id']==mid)
  self.assertEqual(stages,[0,0]);self.assertEqual(len(row['results']),2);self.assertTrue(all(t.hp<before[i] for i,t in enumerate(targets)))
  self.once(e,a,mid,row)
 def test_nonsmite_misses_do_not_gain_after_use_exception_but_substitute_hit_keeps_user_cost(self):
  for mid in CHANGES:
   with self.subTest(move=mid,case='ordinary miss'):
    e,a,targets=self.world(mid);target=targets[0];e.gm.set_position(a,(4,5),reason='actual source range')
    before=target.hp
    with patch.object(Engine,'d20',return_value=1):e.use_move(a,target,mid,set_damage=True)
    row=next(r for r in e._move_completions.values() if r['actor'] is a and r['move_id']==mid)
    self.assertEqual(row['phase'],'complete');self.assertFalse(row['results'][target.entity_id]['hit']);self.assertEqual(target.hp,before)
    self.assertEqual({stat:a.stages[stat] for stat in CHANGES[mid]},{stat:0 for stat in CHANGES[mid]});self.assertEqual(self.self_rows(e,a,mid),[])
  mid='move/엄청난힘';e,a,targets=self.world(mid);target=targets[0]
  e.gm.set_position(a,(4,5),reason='actual melee attack into real Substitute')
  e.gm.set_move(target,'move/대타출동',reason='actual known Substitute')
  e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.start_of_turn(target,initiative_count=30)
  e.use_move(target,target,'move/대타출동');e.end_of_turn(target);e.start_of_turn(a,initiative_count=20)
  self.assertTrue(SUB.live(target));holder_hp=target.hp
  with patch.object(Engine,'d20',return_value=19):e.use_move(a,target,mid,set_damage=True)
  row=next(r for r in e._move_completions.values() if r['actor'] is a and r['move_id']==mid);actual=MC.recipient_result(row,target)
  self.assertFalse(actual['hit']);self.assertTrue(actual['hit_prevented']);self.assertIn('substitute_damage',actual);self.assertEqual(target.hp,holder_hp)
  self.once(e,a,mid,row)
if __name__=='__main__':unittest.main()
