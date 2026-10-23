"""Helpers only: actual native actors, acquisition, Move uses and turn boundaries."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import provocateur as P
import trainer_feature_acquisition as T
import state_codec as CODEC
import state_fields as FIELDS
import world_entities as WORLD

class ProvocateurScene:
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.setup()
 def setup(self,skills=None,edges=None,abilities=()):
  self.e=Engine(self.rules,seed=2530);self.e.grid=Grid(14,12)
  self.common=dict(level=30,size='중형',stats={'hp':50,'atk':20,'def':10,'spa':20,'spd':10,'spe':20},
   moves=['move/몸통박치기','move/째려보기','move/비밀이야기','move/초롱초롱눈동자','move/화염방사'],abilities=[],types=['노말'],
   movement={'land':6,'swim':0,'sky':0,'power':4},weight_kg=30,
   skills=skills or {'매력':5,'교활':5,'협박':5,'집중':3,'전투':4,'육상':4,'기술학':3})
  self.a=self.add('provocateur','trainer',(2,2),edges=list(edges or ['edge/호감인']),feats=[],classes=[],exp_bank=100)
  self.t=self.add('foe','pokemon',(4,2),side='foes',species='피카츄',abilities=list(abilities),speed=15)
  self.b=self.add('ally','trainer',(5,2),feats=[],classes=[],edges=[],speed=18)
  self.u=self.add('other foe','pokemon',(4,3),side='foes',species='피카츄',speed=14)
 def add(self,name,kind,pos,speed=None,**extra):
  spec=dict(deepcopy(self.common),name=name,kind=kind)
  if speed is not None:spec['stats']=dict(spec['stats'],spe=speed)
  spec.update(extra);actor=Combatant(self.e.r,spec)
  self.e.gm.add_combatant(actor,pos=pos,side=extra.get('side','party'),reason='actual Provocateur scene participant')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed full body')
  return actor
 def acquire(self,uid,*,actor=None,selection=None,request=None):
  actor=actor or self.a
  if uid==P.PUSH and selection is None:selection={'edge':P.DEMO}
  return T.acquire_static(self.e,actor,uid,acquisition_request_id=request or actor.entity_id+'/'+uid,selection=selection)
 def whole(self):
  for uid in P.FEATURES:self.acquire(uid)
 def family(self,uid):
  parent=P.DEFINITIONS[uid]['parent']
  if parent and not P.acquired(self.a,parent):self.family(parent)
  if not P.acquired(self.a,uid):self.acquire(uid)
 def begin(self,actor=None,count=30):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=count)
 def turn(self,actor,count=20):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_of_turn(actor,initiative_count=count)
 def next_round(self,actor=None,count=30):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.begin(actor,count)
 def use(self,actor,target,mid,face=15,**options):
  if mid not in actor.moves and mid!='struggle':self.e.gm.set_move(actor,mid,reason='actually learned Move')
  with patch.object(Engine,'d20',return_value=face):
   self.e.use_move(actor,target,mid,set_damage=True,**options)
  rows=[r for r in getattr(self.e,'_move_completions',{}).values() if r['actor'] is actor and r['move_id']==mid]
  self.assertTrue(rows,'native Move did not start: '+mid+' '+str(self.e.log_lines[-5:]))
  return rows[-1]
 def trigger(self,mid,face=15):
  row=self.use(self.a,self.t,mid,face)
  self.assertEqual(row['phase'],'complete');return row['id']
 def fiddle(self,mid,**options):
  token=self.trigger(mid);return self.e.play_them_like_a_fiddle(self.a,self.t,token,**options)
 def reject(self,fn,reason):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids={key:getattr(self,key).entity_id for key in ('a','t','b','u')}
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=WORLD.actor_index(self.e)
  for key,uid in ids.items():setattr(self,key,index[uid])
 def skills(self,**values):FIELDS.base_patch(self.a,{'skills':dict(self.a.spec['skills'],**values)},reason='actual changed skill ranks')
 def policy(self,uid,skill,rank):
  import quick_npc as NPC
  source=NPC.requirement_source(self.rules,uid)
  return {'policy':{'schema':1,'id':'test/qualified-edge/'+uid,'variants':[{'rule_id':uid,'source':source['source'],
   'values':{'source_text':source['source_text'],'requirements_reviewed':True},
   'inputs':{'requirements_reviewed':{'type':'boolean','authority':'gm','question':'Complete printed prerequisite reviewed?'},
    'rank':{'type':'integer','authority':'state','question':'Actual rank','binding':{'subject':'actor','field':'skill_rank','skill':skill}}},
   'when':{'all':[{'$input':'requirements_reviewed'},{'op':'ge','left':{'$input':'rank'},'right':rank}]}}]},
   'decisions':{'requirements_reviewed':{'value':True,'reason':'Complete printed Edge prerequisite adopted'}}}
