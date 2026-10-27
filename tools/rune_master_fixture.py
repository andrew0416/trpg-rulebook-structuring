"""Actual Rune acquisitions, physical surfaces and native turns; no grants faked."""
from pathlib import Path
from copy import deepcopy
import json
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
from native_scenario_fixture import prepare_body
import trainer_feature_acquisition as T,world_entities as W,state_codec as CODEC
import rune_master as R

ROOT=Path(__file__).resolve().parents[1]


class RuneFixture:
    def scene(self,*,edition='supplement',occult=5,acquire=True,trainer_level=40):
        self.edition=edition;self.e=Engine(self.rules,seed=102673);self.e.grid=Grid(30,16)
        self.a=Combatant(self.rules,build_trainer(self.rules,'actual Rune Master',trainer_level,
            {'hp':100,'atk':35,'def':5,'spa':20,'spd':5,'spe':20},moves=[],abilities=[],
            extra={'id':'trainer/rune','classes':[],'feats':[],'skills':{'오컬트학':occult,'명령':6,'매력':3},'movement':{'land':6},'size':'중형','exp_bank':100}))
        self.b=Combatant(self.rules,build_trainer(self.rules,'actual remote target',40,
            {'hp':100,'atk':10,'def':5,'spa':10,'spd':5,'spe':10},moves=[],abilities=[],
            extra={'id':'trainer/target','movement':{'land':6},'size':'중형'}))
        self.unown=[Combatant(self.rules,build_pokemon(self.rules,'안농',20,moves=[],abilities=[],
            extra={'id':'pokemon/unown/'+str(n),'trainer_id':self.a.entity_id,'unown_letter':chr(65+n)})) for n in range(6)]
        for actor,pos,side in [(self.a,(1,1),'party'),(self.b,(20,8),'foe'),
                *[(u,(3+n,2),'party') for n,u in enumerate(self.unown)]]:
            self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual Rune scene participant')
            prepare_body(self.e,actor,size=actor.spec.get('size') or '중형',offsets=[(0,0)],reason='GM observed complete body')
        for u in self.unown:self.e.gm.observe_loyalty(u,6,reason='actual willingly owned Unown')
        W.register_object(self.e,'surface/wall',location={'kind':'grid','cell':[20,7]},reason='actual distant wall')
        if acquire:
            for uid in (R.CLASS,R.POWER,R.REWRITE,R.GLYPH,R.WORDS,R.ALARM,R.EXPLOSIVE,R.SENTRY):self.acquire(uid)
        return self.e

    def acquire(self,feature,*,edition=None,request=None):
        return T.acquire_static(self.e,self.a,feature,acquisition_request_id=request or 'rune/acquire/'+feature,
            selection={'edition':edition or self.edition,'stat':'atk'})

    def glyph(self,n=0,*,visible=False):
        previous=self.a.pos
        self.e.gm.set_position(self.a,(20,6),reason='actual creator at surface before pressing')
        self.e.gm.set_position(self.unown[n],(21,7),reason='actual selected Unown at surface before pressing')
        try:
            return R.create_glyph(self.e,self.a,self.unown[n],glyph_id='glyph/'+str(n),surface_id='surface/wall',
                visible=visible,seconds=3,flat_surface=True,contact=True,gm_id='gm/actual',reason='GM observes actual pressing against a flat wall for three seconds')
        finally:self.e.gm.set_position(self.a,previous,reason='later observed creator position away from glyph')

    def combat(self,actor=None):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=20)

    def next_round(self,actor=None):
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.end_round();self.combat(actor)

    def restore(self):
        ids=[a.entity_id for a in (self.a,self.b,*self.unown)]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        index=W.actor_index(self.e);self.a,self.b,*self.unown=[index[uid] for uid in ids]

    def rejected(self,callback):
        before=CODEC.dump_engine(self.e)
        try:callback()
        except ValueError:pass
        else:raise AssertionError('expected native rejection')
        self.assertEqual(CODEC.dump_engine(self.e),before)

    def investment(self):
        spec=build_pokemon(self.rules,'안농',self.a.level,moves=[],abilities=[])
        return deepcopy(spec['initial_allocation']['investment'])
