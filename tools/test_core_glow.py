"""C10-038: actual Glow species reactions reach target-owned native movement."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest

ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
from engine import Engine,Rules,Combatant
from grid import Grid
from state_codec import dump_engine,load_engine
import perception_observe as PERCEPTION
import scene_lighting as LIGHT
import pokemon_entities as POKEMON
import turn as TURN


class CoreGlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,seed=380);self.e.grid=Grid(20,12)
        self.source=self.actor('pokemon/source','pokemon/안농',(2,4),capabilities=['반짝임'])
        self.attracted=self.actor('pokemon/owned','pokemon/피카츄',(9,4),trainer_id='trainer/other')
        self.repelled=self.actor('pokemon/wild','pokemon/파이리',(7,8),wild=True)
        trainer=Combatant(self.r,{'id':'trainer/other','name':'actual owner','kind':'trainer',
            'level':20,'size':'중형','pos':(18,10),'moves':[],
            'stats':{'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10}})
        self.e.everyone=self.e.gm.everyone=[self.source,self.attracted,self.repelled,trainer]
        self.e.configure_scene_lighting(darkness=False,reason='GM observes this actual scene')
        self.e.observe_scene_light('body',kind='glow',owner=self.source,reason='body actually emits light')
        self.table()
        for target in (self.attracted,self.repelled):self.expose(target)

    def actor(self,uid,species,pos,**extra):
        return Combatant(self.r,dict(id=uid,name=uid,kind='pokemon',species=species,level=20,
            stats={'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},
            size='중형',types=['노말'],movement={'land':4},moves=[],pos=pos,side='same-observed-side',**extra))

    def table(self,reactions=None):
        self.e.observe_glow_reactions('body',reactions=reactions or {
            'pokemon/피카츄':'attract','pokemon/파이리':'repel','pokemon/꼬부기':'none'},
            reason='GM independently observes these species reactions')

    def expose(self,target,*,path=True,present=True):
        return PERCEPTION.observe_environment(self.e,target,self.source,
            paths={'visual':path},present=present,reason='actual target sees this source light')

    def query(self,target=None,**options):
        return self.e.glow_response('body',target or self.attracted,nearby=options.pop('nearby',True),
            reason='GM independently observes target near this light',**options)

    def respond(self,target=None,*,accept=True,movement=None,nearby=True):
        return self.e.respond_to_glow('body',target or self.attracted,nearby=nearby,
            reason='GM independently observes actual proximity',accept=accept,movement=movement)

    def turn(self,target):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(target)

    def outward(self,identity='away'):
        self.e.observe_relative_directions(self.repelled,directions={'outward':(1,0),'inward':(-1,0)},
            quickly_trip_placement='before_entry',reason='GM observes known directions')
        return {'kind':'relative','direction':'outward','distance':2,'pace':'slowly','movement_id':identity}

    def state(self):return deepcopy(dump_engine(self.e))

    def fresh(self):
        ids=[actor.entity_id for actor in (self.source,self.attracted,self.repelled)]
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
        index={actor.entity_id:actor for actor in self.e.everyone}
        self.source,self.attracted,self.repelled=[index[uid] for uid in ids]

    def test_species_attract_and_repel_consume_targets_ordinary_shifts_without_relationship_or_source_cost(self):
        # Both targets have the same type: the GM species fact determines response.
        cells,_=LIGHT.illuminated(self.e)
        self.assertNotIn(self.attracted.pos,cells)
        self.assertEqual((self.query()['response'],self.query(self.repelled)['response']),('attract','repel'))
        source_fields=('capabilities','moves','items')
        source_before=deepcopy({key:self.source.spec.get(key) for key in source_fields})
        rng=self.e.rng.getstate()
        self.turn(self.attracted)
        source_budget=deepcopy(getattr(self.source,'budget',None))
        result=self.respond(movement={'kind':'approach','reach':1})
        self.assertEqual(result['response'],'attract');self.assertEqual(self.attracted.pos[0],5)
        self.assertEqual(result['movement']['distance'],4);self.assertEqual(self.attracted.budget['shift'],0)
        self.assertEqual(getattr(self.source,'budget',None),source_budget)
        self.turn(self.repelled)
        result=self.respond(self.repelled,movement=self.outward())
        self.assertEqual(result['response'],'repel');self.assertEqual(self.repelled.pos,(9,8))
        self.assertEqual(result['movement']['distance'],2);self.assertEqual(self.repelled.budget['shift'],0)
        self.assertEqual({key:self.source.spec.get(key) for key in source_fields},source_before)
        self.assertEqual(getattr(self.source,'_action_history',[]),[])
        self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(self.attracted.spec['trainer_id'],'trainer/other')
        self.assertTrue(self.repelled.spec['wild']);self.assertNotIn('trainer_id',self.repelled.spec)
        for actor in (self.attracted,self.repelled):
            self.assertFalse(actor.captured);self.assertIsNone(POKEMON.loyalty_value(actor))
            self.assertFalse(POKEMON.disposition_projection(actor,'trainer:other')['known'])
            self.assertNotIn('fear',actor.conditions)

    def test_unknown_species_none_decline_and_exposure_never_invent_action_or_reaction(self):
        before=self.state()
        self.assertFalse(self.respond(accept=False)['accepted']);self.assertEqual(self.state(),before)
        for nearby,status,why in ((None,'unknown','nearby_unknown'),(False,'not_observable','not_nearby')):
            result=self.query(nearby=nearby);self.assertEqual((result['status'],result['observation_reason']),(status,why))
        for path,present,status,why in ((None,True,'unknown','path_unknown'),
                (False,True,'not_observable','path_blocked'),(True,False,'absent','no_detectable_presence')):
            self.expose(self.attracted,path=path,present=present)
            before=self.state();result=self.respond(movement={'kind':'approach'})
            self.assertEqual((result['status'],result['observation_reason']),(status,why))
            self.assertIsNone(result['movement']);self.assertEqual(self.state(),before)
        self.expose(self.attracted)
        for species,status,response in (('pokemon/이상해씨','unknown',None),('pokemon/꼬부기','unaffected','none')):
            self.attracted.spec['species']=species
            self.assertEqual((self.query()['status'],self.query()['response']),(status,response))
        self.e.apply_status(self.attracted,'완전 실명',parameters={'cause':'external'})
        self.assertEqual(self.query()['observation_reason'],'vision_blocked')

    def test_live_light_qualification_species_and_pair_observation_gate_new_responses(self):
        self.source.spec['capabilities']=[];self.source.spec['moves']=self.source.moves=['move/플래시']
        self.assertEqual(self.query()['status'],'ready')
        self.source.pos=(3,4)
        self.assertEqual(self.query()['observation_reason'],'path_unknown')
        self.expose(self.attracted);self.assertEqual(self.query()['status'],'ready')
        self.attracted.spec['species']='pokemon/파이리'
        self.assertEqual(self.query()['response'],'repel')
        self.source.spec['moves']=self.source.moves=[]
        before=self.state()
        with self.assertRaisesRegex(ValueError,'current present emitting'):self.query()
        self.assertEqual(self.state(),before)
        self.source.spec['capabilities']=['반짝임'];self.source.on_field=False
        with self.assertRaises(ValueError):self.query()
        self.source.on_field=True
        self.e.remove_scene_light('body',reason='body ceases emitting')
        with self.assertRaisesRegex(ValueError,'observed Glow'):self.query()
        self.e.observe_scene_light('body',kind='glow',owner=self.source,reason='new body emission')
        self.assertEqual(self.query()['observation_reason'],'species_reaction_unknown')

    def test_saved_gm_species_facts_restore_with_source_identity_and_end_with_scene(self):
        original=self.query();self.e.gm.snapshot('observed-glow')
        self.table({'pokemon/피카츄':'repel'})
        self.assertEqual(self.query()['response'],'repel')
        self.e.gm.restore('observed-glow');self.assertEqual(self.query(),original)
        self.fresh();self.assertEqual(self.query(),original)
        row=self.e._scene_lighting['sources']['body']['glow_reactions']
        row['reactions']['pokemon/피카츄']='repel'
        with self.assertRaisesRegex(ValueError,'scene_lighting'):dump_engine(self.e)
        row['reactions']['pokemon/피카츄']='attract'
        self.e.end_scene()
        with self.assertRaises(ValueError):self.query()

    def test_repel_uses_native_terrain_action_availability_and_paid_departure_interrupt(self):
        self.turn(self.repelled);movement=self.outward('blocked')
        self.e.grid.blocking.add((8,8))
        self.expose(self.repelled)
        out=self.respond(self.repelled,movement=movement)
        self.assertEqual(out['movement']['distance'],0);self.assertEqual(self.repelled.pos,(7,8))
        self.assertEqual(self.repelled.budget['shift'],0)
        self.e.grid.blocking.clear()
        self.expose(self.repelled)
        self.assertFalse(self.respond(self.repelled,movement=dict(movement,movement_id='no-extra'))['movement'])
        self.assertEqual(self.repelled.pos,(7,8))
        self.turn(self.repelled)
        enemy=self.actor('pokemon/enemy','pokemon/꼬부기',(6,8));enemy.side='opponent'
        self.e.everyone.append(enemy)
        origin=self.repelled.pos
        def stop(_engine,mover,*_args,**_kwargs):mover.hp=0
        with patch.object(TURN,'trigger_aoo',side_effect=stop) as reaction:
            out=self.respond(self.repelled,movement=dict(movement,movement_id='interrupted'))
        reaction.assert_called_once()
        self.assertEqual(self.repelled.pos,origin);self.assertEqual(out['movement']['distance'],0)
        self.assertEqual(self.repelled.budget['shift'],0)

    def test_wrong_target_light_species_or_movement_authority_reject_before_action(self):
        self.turn(self.repelled);movement=self.outward()
        invalid=dict(movement,direction='inward')
        before=self.state()
        with self.assertRaisesRegex(ValueError,'head away'):self.respond(self.repelled,movement=invalid)
        self.assertEqual(self.state(),before)
        for table in ({'노말':'attract'},{'pokemon/피카츄':'fear'},{}):
            with self.assertRaises(ValueError):
                self.e.observe_glow_reactions('body',reactions=table,reason='invalid species fact')
            self.assertEqual(self.state(),before)
        self.e.observe_scene_light('lantern',kind='lantern',origin=(1,1),reason='separate artificial light')
        before=self.state()
        with self.assertRaises(ValueError):
            self.e.observe_glow_reactions('lantern',reactions={'pokemon/피카츄':'attract'},reason='wrong light')
        with self.assertRaises(ValueError):self.query(target=self.source)
        proxy=self.actor('pokemon/proxy','pokemon/피카츄',(9,4))
        with self.assertRaises(ValueError):self.query(target=proxy)
        self.assertEqual(self.state(),before)
        original=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid: 'other/Glow' if uid==LIGHT.POLICY.GLOW else original(uid)):
            with self.assertRaisesRegex(ValueError,'exact source policy'):self.query()


if __name__=='__main__':unittest.main()
