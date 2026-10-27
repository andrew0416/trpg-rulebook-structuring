"""Actual acquisition, observed bodies/communication and public turn fixture."""
from copy import deepcopy
from pathlib import Path
import json
from unittest.mock import patch
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import commander as C,commander_orders as O,trainer_feature_acquisition as T
import state_codec as CODEC,world_entities as W,state_fields as SF

ROOT=Path(__file__).resolve().parents[1]


class CommanderFixture:
    def scene(self,*,bundle='feat/유린-지시',command=6,acquire=True,seed=24081,ruleset='core',initial_edges=None):
        self.ruleset_name=ruleset;self.r=Rules(ROOT,ruleset=ruleset);self.e=Engine(self.r,seed=seed);self.e.grid=Grid(24,12)
        common=dict(level=40,stats={'hp':100,'atk':10,'def':5,'spa':10,'spd':5,'spe':20},
            moves=['move/막치기','move/물대포','move/성장','move/파도타기','move/전광석화'],
            abilities=[],movement={'land':6,'swim':0,'sky':0},size='중형')
        self.a=Combatant(self.r,dict(deepcopy(common),name='actual Commander',kind='trainer',
            skills={'명령':command,'협박':6,'통찰':6,'교활':6,'매력':6,'육상':3,'곡예':3},
            feats=[],classes=[],exp_bank=100,**({'edges':list(initial_edges)} if initial_edges is not None else {})))
        self.e.gm.add_combatant(self.a,pos=(1,1),side='party',reason='actual issuing Trainer')
        self.p=Combatant(self.r,dict(deepcopy(common),name='own partner',kind='pokemon',
            trainer_id=self.a.entity_id,trainer=self.a.name,skills={'육상':'3d6','곡예':'3d6'}))
        self.q=Combatant(self.r,dict(deepcopy(common),name='allied Trainer',kind='trainer',
            skills={'육상':3,'곡예':3},feats=[],classes=[]))
        self.s=Combatant(self.r,dict(deepcopy(common),name='second allied Trainer',kind='trainer',
            skills={'육상':3,'곡예':3},feats=[],classes=[]))
        self.b=Combatant(self.r,dict(deepcopy(common),name='actual foe',kind='trainer',skills={'육상':3}))
        self.z=Combatant(self.r,dict(deepcopy(common),name='second actual foe',kind='trainer',skills={'육상':3}))
        for actor,pos,side in ((self.p,(2,2),'party'),(self.q,(3,3),'party'),(self.s,(4,4),'party'),
                (self.b,(5,2),'foe'),(self.z,(6,3),'foe')):
            self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native participant')
        for actor in self.e.everyone:
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete medium body')
        self.e.gm.observe_loyalty(self.p,6,reason='observed willing partner')
        for actor in (self.p,self.q,self.s):self.hears(actor)
        if acquire:self.acquire(C.CLASS,branch=bundle)
        return self.e

    def hears(self,target,allowed=True):
        self.e.gm.observe_sensory_environment(self.a,target,paths={'auditory':allowed},present=True,
            reason='observed Order auditory path')

    def acquire(self,feature,**options):
        return T.acquire_static(self.e,self.a,feature,
            acquisition_request_id='commander/acquire/'+feature,**options)

    def leaders(self,*,battle=False,tip=False,scheme=False,complex_orders=False):
        self.acquire(C.LEADERSHIP)
        if battle:self.acquire(C.BATTLE)
        if tip:self.acquire(C.TIP)
        if scheme:self.acquire(C.SCHEME)
        if complex_orders:self.acquire(C.COMPLEX,selection={'prerequisite_source':'local_translation'})

    def combat(self,actor=None):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a if actor is None else actor,initiative_count=20)

    def next_turn(self,actor):
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.start_of_turn(actor,initiative_count=10)

    def next_round(self,actor=None):
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.end_round();self.combat(self.a if actor is None else actor)

    def attack(self,actor=None,target=None,move='move/물대포',natural=10):
        with patch.object(Engine,'d20',return_value=natural):
            return self.e.use_move_on(self.p if actor is None else actor,self.b if target is None else target,
                move,self.e.everyone,set_damage=True)

    def restore(self):
        ids=[c.entity_id for c in (self.a,self.p,self.q,self.s,self.b,self.z)]
        self.r=Rules(ROOT,ruleset=self.ruleset_name)
        self.e=CODEC.load_engine(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index=W.actor_index(self.e);self.a,self.p,self.q,self.s,self.b,self.z=[index[uid] for uid in ids]

    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])

    def rejected(self,operation,pattern):
        return assert_rejected_unchanged(self.e,operation,reason_pattern=pattern)

    def choice(self,key,value):
        self.e.rulings.add_answer(key,value,reason='actual declared player choice',scope='permanent')

    def imported_payload_rejected(self,old,new,pattern):
        payload=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False).replace(old,new))
        with self.assertRaisesRegex(ValueError,pattern):CODEC.load_engine(Rules(ROOT,ruleset='core'),payload)
