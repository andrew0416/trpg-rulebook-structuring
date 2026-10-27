"""Fortress fixtures use real acquisition, physical items and native turn budgets."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import trainer_feature_acquisition as T,state_codec as CODEC,world_entities as W
import fortress as F,state_grants as G

ROOT=Path(__file__).resolve().parents[1]


class FortressFixture:
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(ROOT,ruleset='fantasy');cls.base_rulings=deepcopy(cls.rules.rulings)

 def actor(self,name,pos,side='party',*,combat=5,focus=5):
  actor=Combatant(self.rules,build_trainer(self.rules,name,40,
   {'hp':200,'atk':25,'def':5,'spa':25,'spd':5,'spe':20},moves=['move/물대포'],
   skills={'전투':combat,'집중':focus,'육상':5,'곡예':5,'은신':5,'오컬트학':5,'직감':5,'통찰':5},pos=pos,side=side,
   extra={'exp_bank':100,'chronicler_archive_choices':{'class/기록자':'profile'},
    'movement':{'land':6,'swim':3,'sky':0,'levitate':0,'burrow':0,'teleport':0,'power':4},'movement_basis':'current','power_basis':'current'}))
  self.e.gm.add_combatant(actor)
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete Fortress scene body')
  return actor

 def scene(self,*,features=(),edition='supplement',combat=5,focus=5):
  self.rules.rulings=deepcopy(self.base_rulings);self.e=Engine(self.rules,seed=102657);self.e.grid=Grid(16,16)
  self.edition=edition;self.a=self.actor('actual Fortress',(1,1),combat=combat,focus=focus)
  self.b=self.actor('actual marked foe',(2,1),'foe')
  self.ally=self.actor('actual protected ally',(1,2));self.other=self.actor('actual other foe',(5,5),'foe')
  self.initial_def=self.a.stats['def']
  for feature in features:self.acquire(feature)

 def acquire(self,feature=F.CLASS,*,edition=None,ability='애널라이즈',request=None,mark_scope='korean_own_mark'):
  for parent in F.PARENTS[feature]:
   if F.acquired(self.a,parent)is None:self.acquire(parent,edition=edition)
  choice={'edition':edition or self.edition}
  if feature==F.SLOW:choice['ability']=ability
  if feature==F.GUARDIAN:choice['mark_scope']=mark_scope
  return T.acquire_static(self.e,self.a,feature,acquisition_request_id=request or 'fortress/acquire/'+feature,selection=choice)

 def combat(self,actor=None):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=20)

 def next_turn(self,actor=None):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=20)

 def attack(self,*,actor=None,target=None,weapon=None,roll=10,guardian=False,skill='집중'):
  actor=actor or self.a;target=target or self.b
  mid='struggle' if weapon is None else actor.custom_conditions['equipped_weapons'][weapon]['struggle_id']
  with patch.object(Engine,'d20',return_value=roll):
   if guardian:result=self.e.guardian_weapon_attack(actor,target,mid,weapon_id=weapon,skill=skill)
   else:result=self.e.use_move_on(actor,target,mid,self.e.everyone,weapon_id=weapon)
  self.completion=next(reversed(self.e._move_completions))
  return result

 def mark(self,*,weapon=None,roll=10):
  self.attack(weapon=weapon,roll=roll)
  self.e.end_of_turn(self.a,fortress_mark=self.completion)

 def weapon(self):
  import turn
  return turn.equip_weapon(self.e,self.a,{'name':'observed Fortress blade','kind':'소형 근접무기','grade':'간단','moves':[]})

 def shield(self,heavy=False):
  import capability_actions as CAP,items
  uid='physical/fortress-heavy-shield' if heavy else 'physical/fortress-light-shield'
  rule='item/중방패' if heavy else 'item/경방패'
  W.register_object(self.e,uid,location={'kind':'unknown'},reason='observed exact printed shield',
   kind='item_instance',item_rule_id=rule,owner_id=self.a.entity_id,weight_kg=2)
  CAP.set_carried(self.e,self.a,[{'id':uid,'weight_kg':2}],'observed actual shield possession')
  # Component setup is not a simulated manual paid equip action.
  items.register_item(self.e,self.a,rule,source_instance_id=uid)
  return uid

 def follow_scene(self,*,mode='land',ally_mode='land',normal=6,ally_normal=6):
  self.scene(features=(F.SHIELD,));uid=self.shield()
  for actor,selected,limit in ((self.a,mode,normal),(self.ally,ally_mode,ally_normal)):
   if selected=='teleport':self.e.gm.set_move(actor,'move/순간이동',reason='actual learned Teleport capability source')
   values=deepcopy(actor.spec['movement']);values[selected]=limit
   self.e.gm.set_movement_capabilities(actor,values,basis='current',reason='observed current native follow movement capability')
  self.combat();self.e.ready_fortress_shield(self.a,uid,ally=self.ally,request_id='follow-ready')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.ally,initiative_count=10)

 def restore(self):
  ids=[a.entity_id for a in (self.a,self.b,self.ally,self.other)]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=W.actor_index(self.e);self.a,self.b,self.ally,self.other=[index[uid] for uid in ids]

 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])

 def rejected(self,fn,pattern='.'):
  return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)

 def withdraw(self,feature):
  sid=next(sid for sid,row in G.state(self.a)['sources'].items() if row.get('static_acquisition',{}).get('feature_id')==feature)
  def apply(e,a):
   G.revoke(a,sid,engine=e);a.spec['feats'].remove(feature)
  return G.transition(self.e,self.a,apply)
