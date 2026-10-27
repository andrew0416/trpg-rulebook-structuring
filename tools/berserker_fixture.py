"""Actual Berserker acquisitions and native scenes, without granted turn budgets."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json

from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import trainer_feature_acquisition as T
import state_codec as CODEC,world_entities as W,state_fields as SF
import berserker as B

ROOT=Path(__file__).resolve().parents[1]


class BerserkerFixture:
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='fantasy')
        cls.base_rulings=deepcopy(cls.rules.rulings)

    def scene(self,*,features=(),edition='supplement',combat_rank=5,intimidate=5):
        self.rules.rulings=deepcopy(self.base_rulings)
        self.e=Engine(self.rules,seed=102649);self.e.grid=Grid(12,12)
        self.edition=edition
        stats={'hp':100,'atk':25,'def':5,'spa':25,'spd':5,'spe':20}
        skills={'전투':combat_rank,'협박':intimidate,'육상':5,'곡예':5,'은신':5,'오컬트학':5,'직감':5,'통찰':5}
        self.a=Combatant(self.rules,build_trainer(self.rules,'actual Berserker',40,stats,
            moves=['move/물대포','move/마구할퀴기'],skills=skills,pos=(1,1),
            extra={'exp_bank':100,'chronicler_archive_choices':{'class/기록자':'profile'},
                   'movement':{'land':6,'swim':3,'sky':0,'levitate':0,'burrow':0,'teleport':0},'movement_basis':'current'}))
        foe_stats=dict(stats,hp=200,atk=20,spe=10)
        self.b=Combatant(self.rules,build_trainer(self.rules,'actual recipient',40,foe_stats,
            moves=['move/물대포'],skills={'전투':5,'협박':5},pos=(2,1),side='foe',
            extra={'movement':{'land':6},'movement_basis':'current'}))
        for actor in (self.a,self.b):
            self.e.gm.add_combatant(actor)
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete medium body')
        self.initial_max=self.a.base_max_hp
        for feature in features:self.acquire(feature)

    def acquire(self,feature=B.CLASS,*,edition=None,ability='화이트플레임'):
        for parent in B.PARENTS[feature]:
            if B.acquired(self.a,parent)is None:self.acquire(parent,edition=edition)
        selection={'edition':edition or self.edition}
        if feature==B.POWER:selection['ability']=ability
        return T.acquire_static(self.e,self.a,feature,acquisition_request_id='berserker/acquire/'+feature,selection=selection)

    def answer(self,key,value):
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!=key]
        self.e.rulings.add_answer(key,value,reason='explicit actual player choice',scope='permanent')

    def injury(self,count,actor=None):
        self.e.gm.set_injuries(actor or self.a,value=count,reason='observed actual current injuries')

    def hp(self,value,actor=None):
        self.e.gm.set_hp(actor or self.a,value=value,reason='observed actual current HP')

    def rage(self,actor=None):self.e.apply_status(actor or self.a,'난동')

    def combat(self,actor=None,*,scheduled=False):
        if scheduled:self.e.prepare_initiative_schedule(self.e.everyone,source='gm/actual-berserker-schedule')
        self.e.start_round(self.e.everyone)
        if actor is not False:self.e.start_of_turn(actor or self.a,initiative_count=20)

    def attack(self,move='move/분노',*,actor=None,target=None,weapon_id=None,roll=10):
        with patch.object(Engine,'d20',return_value=roll):
            return self.e.use_move_on(actor or self.a,target or self.b,move,self.e.everyone,
                weapon_id=weapon_id,set_damage=True)

    def equip(self,kind='소형 근접무기'):
        import turn
        return turn.equip_weapon(self.e,self.a,{'name':'observed Berserker blade','kind':kind,'grade':'간단','moves':[]})

    def restore(self):
        ids=[a.entity_id for a in (self.a,self.b)]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        actors=W.actor_index(self.e);self.a,self.b=[actors[uid] for uid in ids]

    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def rejected(self,fn,pattern='.'):
        return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)

    def withdraw(self,feature):
        import state_grants as G
        sid=next(sid for sid,row in G.state(self.a)['sources'].items()
                 if row.get('static_acquisition',{}).get('feature_id')==feature)
        def apply(e,a):
            G.revoke(a,sid,engine=e)
            a.spec['feats'].remove(feature)
        return G.transition(self.e,self.a,apply)
