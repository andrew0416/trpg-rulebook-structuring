"""Real Tumbler acquisition, physical actors, native turn and Move helpers only."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import tumbler as T
import trainer_feature_acquisition as A
import state_codec as CODEC
import world_entities as W

class TumblerScene:
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.setup()
 def setup(self,rank=6,acrobat=True,extra_skills=None,extra_edges=(),edge_choices=None):
  self.e=Engine(self.rules,seed=2718);self.e.grid=Grid(16,12)
  self.a=self.add('tumbler','trainer',(2,2),rank=rank,edges=([T.ACROBAT] if acrobat else [])+list(extra_edges),speed=30,extra_skills=extra_skills,edge_choices=edge_choices)
  self.t=self.add('foe','pokemon',(3,2),side='foes',speed=20)
  self.u=self.add('other foe','pokemon',(1,2),side='foes',speed=10)
 def add(self,name,kind,pos,rank=6,edges=(),speed=20,side='party',extra_skills=None,edge_choices=None):
  spec={'name':name,'kind':kind,'level':30,'size':'중형','types':['노말'],'stats':{'hp':60,'atk':20,'def':10,'spa':20,'spd':10,'spe':speed},
   'moves':['move/몸통박치기','move/물대포'],'abilities':[],'classes':[],'feats':[],'edges':list(edges),'skills':{'곡예':rank,'육상':4,'전투':4,'집중':3},
   'movement':{'land':6,'high_jump':1,'long_jump':2,'power':4},'movement_basis':'base','weight_kg':30,'exp_bank':100}
  if extra_skills:spec['skills'].update(extra_skills)
  if edge_choices is not None:spec['edge_choices']=deepcopy(edge_choices)
  if kind=='pokemon':spec['species']='피카츄'
  actor=Combatant(self.rules,spec);self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual Tumbler native participant')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete body')
  return actor
 def acquire(self,uid,request=None):return A.acquire_static(self.e,self.a,uid,acquisition_request_id=request or 'tumbler:'+uid)
 def family(self,uid):
  if uid==T.BURST:
   for f in T.FEATURES:
    if f!=T.BURST and not T.acquired(self.a,f):self.family(f)
  parent=T.DEFINITIONS[uid]['parent']
  if parent in T.FEATURES and not T.acquired(self.a,parent):self.family(parent)
  if not T.acquired(self.a,uid):self.acquire(uid)
 def begin(self,actor=None,count=40):self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=count)
 def turn(self,actor,count):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_of_turn(actor,initiative_count=count)
 def next_round(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.begin()
 def decision(self,kind,value):self.rules.rulings.add_answer(kind,value,reason='actual player chooses printed option',scope='scene')
 def use(self,actor,target,mid,face=15):
  with patch.object(Engine,'d20',return_value=face):return self.e.use_move(actor,target,mid,set_damage=True)
 def jump(self,destination=(2,3),**extra):
  return self.e.jump(self.a,destination,jump_id=extra.pop('jump_id','jump-native'),difficult=False,clear_path=True,reason_text='observed clear native Jump',**extra)
 def jump_move(self,mid,target=None,*,event='jump-move',destination=(2,3),path=None,destroy=False,face=15):
  target=target or (self.a if mid==T.SPLASH else self.t)
  self.e.declare_jump_move(self.a,target,mid,event_id=event,jump={'destination':destination,'difficult':False,'clear_path':True} if path is None else None,path=path,destroy_hazards=destroy,reason='actual chosen Jump Move')
  return self.use(self.a,target,mid,face)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[c.entity_id for c in (self.a,self.t,self.u)]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=W.actor_index(self.e);self.a,self.t,self.u=[index[uid] for uid in ids]
 def reject(self,fn,reason):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)

 def hold_item(self,actor=None,name="달인의띠",as_held=True):
  actor=actor or self.a
  import items as ITEMS,world_entities as W,capability_actions as CAP
  uid='object/tumbler-held-belt'
  _,header=self.rules.item_effects(name)
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual held item',kind='item_instance',item_rule_id=header['id'],owner_id=actor.entity_id,weight_kg=1)
  CAP.set_carried(self.e,actor,[{'id':uid,'weight_kg':1}],'actual held possession')
  ITEMS.register_item(self.e,actor,name,source_instance_id=uid,as_held=as_held)
