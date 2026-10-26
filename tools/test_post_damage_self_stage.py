"""Printed Draco Meteor/Overheat self-cost follows all native recipient damage."""
import json
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules
import test_book_type_ace_acquisition as FIX
import move_completion as MC
import effects as FX
import world_entities as WORLD

class PostDamageSelfStageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def world(self,mid):
  f=FIX.TypeAceAcquisitionTests();f.rules=self.rules;f.setup();e,a=f.e,f.p
  for actor,pos in ((f.t,(0,0)),(a,(2,2)),(f.q,(5,5)),(f.b,(6,5))):e.gm.set_position(actor,pos,reason='actual printed blast recipient geometry')
  for target in (f.q,f.b):e.gm.set_types(target,['노말'],reason='same neutral native targets')
  e.gm.set_move(a,mid,reason='actual learned source Move')
  e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  return e,a,(f.q,f.b)
 def attack(self,e,a,targets,mid,face,*,zero=False):
  observations=[];post_hits=[];damage=Engine.roll_damage;effects=FX.run_effects
  def observe(engine,attacker,target,move,*args,**kw):
   if attacker is a and move['id']==mid:observations.append(a.stages['spa'])
   value=damage(engine,attacker,target,move,*args,**kw)
   return 0 if zero else value
  def dispatch(engine,actor,target,effect_list,context,*args,**kw):
   if actor is a and context.get('after_all_targets') and any(x.get('type')=='stage_change' and x.get('target')=='self' for x in effect_list):post_hits.append(context['hit'])
   return effects(engine,actor,target,effect_list,context,*args,**kw)
  with patch.object(Engine,'d20',return_value=face),patch.object(Engine,'roll_damage',observe),patch.object(FX,'run_effects',dispatch):
   e.use_move_on(a,targets[0],mid,e.everyone,aim=(5,5),set_damage=True)
  row=next(r for r in e._move_completions.values() if r['actor'] is a and r['move_id']==mid)
  self.assertEqual(row['phase'],'complete');self.assertEqual(len(row['results']),2)
  return row,observations,post_hits
 def test_both_printed_blasts_calculate_all_damage_before_one_self_drop_and_do_not_replay(self):
  for mid in ('move/용성군','move/오버히트'):
   with self.subTest(move=mid):
    e,a,targets=self.world(mid);before=[t.hp for t in targets]
    import effect_contracts as CONTRACTS
    effect=e.r.move_mech(mid)[0]['effects_exec'][0]
    forged={'engine':e,'attacker':a,'target':targets[0],'move':e.r.move(mid),'hit':False,'after_all_targets':True,'move_completion':'missing'}
    self.assertIs(CONTRACTS.condition(e,effect,forged,source=mid).truth,CONTRACTS.ROOT.Truth.UNKNOWN)
    self.assertEqual(a.stages['spa'],0)
    row,stages,hits=self.attack(e,a,targets,mid,19)
    self.assertEqual(stages,[0,0]);self.assertEqual(a.stages['spa'],-2);self.assertEqual(hits,[True])
    self.assertTrue(all(before[i]>t.hp for i,t in enumerate(targets)))
    self.assertTrue(all(r['hit'] for r in row['results'].values()))
    receipts=[r for r in e._effect_dispatch_receipts.values() if r['source_id']==mid and r['effect'].get('type')=='stage_change']
    self.assertEqual(len(receipts),1);self.assertEqual(receipts[0]['status'],'completed')
    context=dict(forged,move_completion=row['id'])
    self.assertFalse(MC.authorized_after_damage_self_stage(e,context,effect,mid))
    with patch.dict(row,{'phase':'applying'}):
     self.assertFalse(MC.authorized_after_damage_self_stage(e,dict(context,attacker=targets[0]),effect,mid))
     self.assertFalse(MC.authorized_after_damage_self_stage(e,dict(context,target=a),effect,mid))
     self.assertFalse(MC.authorized_after_damage_self_stage(e,context,effect,'move/니트로차지'))
     with patch.dict(row,{'sealed':False}):self.assertFalse(MC.authorized_after_damage_self_stage(e,context,effect,mid))
     for flag in ('cancelled','hit_prevented'):
      with patch.dict(row,{'results':{key:dict(value,**{flag:True}) for key,value in row['results'].items()}}):
       self.assertFalse(MC.authorized_after_damage_self_stage(e,context,effect,mid))
    MC.refresh(e,row['id']);self.assertEqual(a.stages['spa'],-2)
    loaded=Engine.import_state(self.rules,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
    actor=WORLD.actor_index(loaded)[a.entity_id];MC.refresh(loaded,row['id']);self.assertEqual(actor.stages['spa'],-2)
 def test_both_smite_misses_pay_one_self_drop_with_honest_miss_context(self):
  for mid in ('move/용성군','move/오버히트'):
   with self.subTest(move=mid):
    e,a,targets=self.world(mid);before=[t.hp for t in targets]
    row,stages,hits=self.attack(e,a,targets,mid,1)
    self.assertEqual(stages,[0,0]);self.assertEqual(a.stages['spa'],-2);self.assertEqual(hits,[False])
    self.assertTrue(all(not r['hit'] and r['dealt']>0 for r in row['results'].values()))
    self.assertTrue(all(before[i]>t.hp for i,t in enumerate(targets)))
    self.assertEqual(len([r for r in e._effect_dispatch_receipts.values() if r['source_id']==mid and r['effect'].get('type')=='stage_change']),1)
 def test_zero_net_smite_still_has_printed_cost_and_unrelated_normal_miss_has_no_self_boost(self):
  e,a,targets=self.world('move/오버히트');before=[t.hp for t in targets]
  row,stages,hits=self.attack(e,a,targets,'move/오버히트',1,zero=True)
  self.assertEqual(stages,[0,0]);self.assertEqual([t.hp for t in targets],before)
  self.assertEqual(a.stages['spa'],-2);self.assertEqual(hits,[False]);self.assertTrue(all(not r['hit'] and r['dealt']==0 for r in row['results'].values()))
  for face,stage in ((1,0),(19,1)):
   e,a,targets=self.world('move/니트로차지')
   e.gm.set_position(a,(4,5),reason='actual melee source range')
   with patch.object(Engine,'d20',return_value=face):e.use_move(a,targets[0],'move/니트로차지',set_damage=True)
   self.assertEqual(a.stages['spe'],stage)
 def test_additional_area_smite_sources_drop_once_after_all_hit_or_miss_damage(self):
  for mid in ('move/리프스톰','move/플뢰르캐논','move/사이코부스트'):
   for face in (19,1):
    with self.subTest(move=mid,natural=face):
     e,a,targets=self.world(mid)
     if mid=='move/플뢰르캐논':
      e.gm.set_position(targets[0],(3,3),reason='actual first line recipient')
      e.gm.set_position(targets[1],(4,4),reason='actual second line recipient')
     before=[t.hp for t in targets]
     row,stages,hits=self.attack(e,a,targets,mid,face)
     self.assertEqual(stages,[0,0]);self.assertEqual(a.stages['spa'],-2);self.assertEqual(hits,[face!=1])
     self.assertTrue(all(r['hit']==(face!=1) and r['dealt']>0 for r in row['results'].values()))
     self.assertTrue(all(t.hp<before[i] for i,t in enumerate(targets)))
     receipts=[r for r in e._effect_dispatch_receipts.values() if r['source_id']==mid and r['effect'].get('type')=='stage_change']
     self.assertEqual(len(receipts),1);self.assertEqual(receipts[0]['status'],'completed')
     MC.refresh(e,row['id']);self.assertEqual(a.stages['spa'],-2)
 def test_v_create_pays_each_printed_user_drop_once_after_hit_or_smite_miss(self):
  mid='move/v제너레이트';fields=('def','spd','spe')
  for face in (19,1):
   with self.subTest(natural=face):
    e,a,targets=self.world(mid);target=targets[0];e.gm.set_position(a,(4,5),reason='actual one-target melee range')
    before=target.hp;observed=[];contexts=[];damage=Engine.roll_damage;effects=FX.run_effects
    def observe(engine,actor,recipient,move,*args,**kw):
     if actor is a and move['id']==mid:observed.append(tuple(a.stages[field] for field in fields))
     return damage(engine,actor,recipient,move,*args,**kw)
    def dispatch(engine,actor,recipient,effect_list,context,*args,**kw):
     if actor is a and context.get('after_all_targets') and any(x.get('type')=='stage_change' for x in effect_list):contexts.append(context['hit'])
     return effects(engine,actor,recipient,effect_list,context,*args,**kw)
    with patch.object(Engine,'d20',return_value=face),patch.object(Engine,'roll_damage',observe),patch.object(FX,'run_effects',dispatch):e.use_move(a,target,mid,set_damage=True)
    row=next(r for r in e._move_completions.values() if r['actor'] is a and r['move_id']==mid)
    self.assertEqual(row['phase'],'complete');self.assertEqual(contexts,[face!=1]);self.assertEqual(observed,[(0,0,0)])
    self.assertLess(target.hp,before);self.assertEqual(row['results'][target.entity_id]['hit'],face!=1)
    self.assertEqual(tuple(a.stages[field] for field in fields),(-1,-1,-1))
    receipts=[r for r in e._effect_dispatch_receipts.values() if r['source_id']==mid and r['effect'].get('type')=='stage_change']
    self.assertEqual(sorted(r['effect']['stat'] for r in receipts),sorted(fields));self.assertTrue(all(r['status']=='completed' for r in receipts))
    MC.refresh(e,row['id']);self.assertEqual(tuple(a.stages[field] for field in fields),(-1,-1,-1))
    loaded=Engine.import_state(self.rules,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
    restored=WORLD.actor_index(loaded)[a.entity_id];MC.refresh(loaded,row['id'])
    self.assertEqual(tuple(restored.stages[field] for field in fields),(-1,-1,-1))
if __name__=='__main__':unittest.main()
