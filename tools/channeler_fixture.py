"""Actual Channeler acquisition, body, relation, action and native Move fixtures."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged,assert_rejections_unchanged
import channeler as C,trainer_feature_acquisition as T,world_entities as W,state_codec as CODEC
import frequency as F,action_points as AP,perception_communicate as COMM

class ChannelerScene:
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old);self.setup()
 def setup(self,rank=6,mystic=True):
  self.e=Engine(self.rules,seed=1709);self.e.grid=Grid(60,40)
  self.a=self.add('channeler','trainer',(2,2),skills={'직감':rank,'집중':6,'명령':6,'매력':6},edges=['edge/신비한-감각'] if mystic else [])
  __import__('items').register_feats(self.e,self.a)
  self.p=self.add('first channel','pokemon',(3,2));self.q=self.add('second channel','pokemon',(3,3));self.r=self.add('third channel','pokemon',(2,3))
  self.b=self.add('foe','pokemon',(4,2),side='foes');self.z=self.add('other foe','pokemon',(4,3),side='foes')
 def add(self,name,kind,pos,*,side='party',skills=None,edges=(),disposition='중립',owner=None,features=()):
  spec={'name':name,'kind':kind,'level':30,'size':'중형','stats':{'hp':80,'atk':20,'def':12,'spa':20,'spd':12,'spe':20},'types':['노말'],
   'moves':['move/몸통박치기','move/물대포','move/진흙뿌리기','move/아쿠아링','move/칼춤'], 'abilities':[], 'classes':[], 'feats':list(features), 'edges':list(edges),
   'skills':dict({'육상':4,'곡예':4,'전투':4},**(skills or {})),'movement':{'land':8,'power':4},'movement_basis':'base','weight_kg':30,'exp_bank':100}
  if kind=='pokemon':spec.update(species='피카츄',disposition=disposition)
  if owner is not None:spec['trainer_id']=owner.entity_id
  actor=Combatant(self.rules,spec);self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual registered Channeler participant')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete body');return actor
 def acquire(self,uid=C.CLASS):return T.acquire_static(self.e,self.a,uid,acquisition_request_id='channeler:'+uid)
 def family(self,uid):
  parent=C.DEFINITIONS[uid]['parent']
  if parent and C.acquired(self.a,parent) is None:self.family(parent)
  if C.acquired(self.a,uid) is None:self.acquire(uid)
 def begin(self,actor=None,count=50):self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=count)
 def turn(self,actor,count=30):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_of_turn(actor,initiative_count=count)
 def next_round(self,actor=None):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.begin(actor)
 def channel(self,*pokemon):
  self.family(C.CLASS)
  for p in pokemon:
   if not self.e.encounter_active:self.begin()
   else:self.next_round()
   self.e.channel_pokemon(self.a,p)
 def decision(self,kind,value):
  self.e.rulings.answers=[row for row in self.e.rulings.answers if row['key']!=kind]
  self.e.rulings.add_answer(kind,value,reason='actual player selected native choice',scope='permanent')
 def use(self,actor,target,move='move/몸통박치기',face=15):
  with patch.object(Engine,'d20',return_value=face):return self.e.use_move(actor,target,move,set_damage=True)
 def hit(self,actor=None,target=None,move='move/몸통박치기',face=15):
  actor=actor or self.b;target=target or self.p;self.next_round(actor);return self.use(actor,target,move,face)
 def damage(self,actor=None,target=None,move='move/몸통박치기',face=15):
  rows=[];original=Engine.roll_damage
  def observe(e,a,t,m,*args,**kwargs):
   value=original(e,a,t,m,*args,**kwargs);rows.append((a.entity_id,t.entity_id,m['id'],value,deepcopy(kwargs.get('_reaction_event',{}),{id(e.r):e.r,id(e):e})));return value
  with patch.object(Engine,'roll_damage',observe):result=self.hit(actor,target,move,face)
  return result,rows
 def reject(self,fn,reason=None):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  names=('a','p','q','r','b','z');ids={n:getattr(self,n).entity_id for n in names}
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=W.actor_index(self.e)
  for n,uid in ids.items():setattr(self,n,index[uid])
 def ready_pain(self,selected=None):
  self.family(C.PAIN);self.channel(self.p,self.q,self.r)
  self.e.gm.set_hp(self.p,value=1,reason='actual pre-hit positive HP')
  self.decision('pain_dampening',selected if selected is not None else [self.p.entity_id,self.q.entity_id])
 def latest(self):return list(self.e._move_completions.values())[-1]
