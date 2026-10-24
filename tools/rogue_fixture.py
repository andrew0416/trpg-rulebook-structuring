"""Helpers only: actual native Rogue acquisitions, actors and completed Moves."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import rogue as R
import trainer_feature_acquisition as T
import turn as TURN
import state_codec as CODEC
import world_entities as W

class RogueScene:
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.setup()
 def setup(self,skills=None,extra_feats=(),target_kind='pokemon',target_edges=None):
  self.e=Engine(self.rules,seed=2595);self.e.grid=Grid(14,12)
  self.common=dict(level=30,size='중형',stats={'hp':70,'atk':20,'def':10,'spa':20,'spd':10,'spe':20},
   moves=['move/몸통박치기','move/째려보기','move/전기쇼크','move/더블어택'],abilities=[],types=['노말'],
   movement={'land':6,'swim':2,'sky':0,'power':4},movement_basis='current',weight_kg=30,
   skills=skills or {'곡예':5,'육상':5,'은신':5,'집중':3,'전투':2})
  self.a=self.add('rogue','trainer',(2,2),feats=list(extra_feats),classes=[],edges=[],exp_bank=100,items={'item/벌레회피스프레이':1})
  self.t=self.add('foe',target_kind,(3,2),side='foes',speed=15,feats=list(extra_feats),**({'edges':list(target_edges)} if target_edges is not None else {}),**({'species':'피카츄','wild':True} if target_kind=='pokemon' else {}))
  self.b=self.add('ally','trainer',(2,3),feats=[],classes=[],edges=[],speed=18)
  self.u=self.add('other foe','pokemon',(3,3),side='foes',species='피카츄',speed=14)
 def add(self,name,kind,pos,speed=None,**extra):
  spec=dict(deepcopy(self.common),name=name,kind=kind)
  if speed is not None:spec['stats']=dict(spec['stats'],spe=speed)
  spec.update(extra);actor=Combatant(self.e.r,spec)
  self.e.gm.add_combatant(actor,pos=pos,side=extra.get('side','party'),reason='actual Rogue scene participant')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed full body')
  return actor
 def acquire(self,uid,*,actor=None,ability=R.AMBUSH,request=None):
  actor=actor or self.a
  return T.acquire_static(self.e,actor,uid,acquisition_request_id=request or actor.entity_id+'/'+uid,branch=ability if uid==R.UNDERHAND else None)
 def family(self,uid,ability=R.AMBUSH):
  for parent in R.DEFINITIONS[uid]['parents']:
   if not R.acquired(self.a,parent):self.family(parent,ability)
  if not R.acquired(self.a,uid):self.acquire(uid,ability=ability)
 def whole(self,ability=R.AMBUSH):
  for uid in R.FEATURES:self.acquire(uid,ability=ability)
 def weapon(self,kind='소형 근접무기',actor=None,name='knife',moves=(),slot='주요손',grade='조잡'):
  actor=actor or self.a
  return TURN.equip_weapon(self.e,actor,{'name':name,'kind':kind,'grade':grade,'moves':list(moves),'slot':slot})
 def begin(self,actor=None,count=30):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=count)
 def turn(self,actor,count=20):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_of_turn(actor,initiative_count=count)
 def next_round(self,actor=None,count=30):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.begin(actor,count)
 def use(self,actor,target,mid,face=15,**options):
  with patch.object(Engine,'d20',return_value=face):self.e.use_move(actor,target,mid,set_damage=True,**options)
  rows=[row for row in getattr(self.e,'_move_completions',{}).values() if row['actor'] is actor and row['move_id']==mid]
  self.assertTrue(rows,'native Move did not start: '+mid+' '+str(self.e.log_lines[-6:]))
  self.assertEqual(rows[-1]['phase'],'complete',str({'last_log':self.e.log_lines[-15:],'completion':{k:v for k,v in rows[-1].items() if k in ('phase','sealed','started','results')},'effects':[{k:receipt.get(k) for k in ('source_id','effect','status','reason','result')} for receipt in getattr(self.e,'_effect_dispatch_receipts',{}).values()]}));return rows[-1]
 def hit(self,mid='move/속여때리기',weapon_id=None,target=None):return self.use(self.a,target or self.t,mid,weapon_id=weapon_id)['id']
 def reject(self,fn,reason):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids={key:getattr(self,key).entity_id for key in ('a','t','b','u')}
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=W.actor_index(self.e)
  for key,uid in ids.items():setattr(self,key,index[uid])
