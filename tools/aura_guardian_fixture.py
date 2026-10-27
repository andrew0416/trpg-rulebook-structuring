"""Aura Guardian uses actual acquisition receipts and native body/turn helpers."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from tumbler_fixture import TumblerScene
from engine import Rules,Engine
import aura_guardian as A
import trainer_feature_acquisition as T
import state_grants as G

class AuraScene(TumblerScene):
 def setup(self,rank=5,element='격투',extra_edges=(),edge_choices=None):
  choices={'edge/원소-교감':[element]} if element else {}
  choices.update(edge_choices or {})
  TumblerScene.setup(self,rank=4,acrobat=False,extra_skills={'직감':rank},extra_edges=(['edge/원소-교감'] if element else [])+list(extra_edges),edge_choices=choices)
  self.ally=self.add('ally','trainer',(5,2),extra_skills={'직감':rank},edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':['격투']})
 def acquire(self,uid,request=None,*,stat='atk',moves=None,ability=None,rank=None,actor=None):
  actor=actor or self.a;selection={'stat':stat}
  if uid in A.MOVES:selection['moves']=list(moves or A.MOVES[uid][:2])
  if uid==A.POWER:selection['ability']=ability or A.SCRAPPY
  return T.acquire_static(self.e,actor,uid,acquisition_request_id=request or 'aura:'+uid+':'+str(rank),rank=rank,selection=selection)
 def family(self,uid,**choices):
  parent=A.DEFINITIONS[uid]['parent']
  if parent and not A.acquired(self.a,parent):self.family(parent)
  if not A.acquired(self.a,uid):return self.acquire(uid,**choices)
 def reader(self):
  self.family(A.READER);self.begin();return self.e.activate_aura_reader(self.a)
 def ambient(self):
  self.family(A.AMBIENT);self.reader();self.next_round();self.decision('ambient_aura',True)
  self.use(self.a,self.t,'move/진공파');return A.blessing(self.a)
 def restore(self):
  ally_id=self.ally.entity_id;TumblerScene.restore(self)
  self.ally=__import__('world_entities').actor_index(self.e)[ally_id]
