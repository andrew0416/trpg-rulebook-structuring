"""Actual scene sources, native pairwise consumers and world restoration."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine')]
from engine import Engine,Rules,Combatant
from grid import Grid
from state_codec import dump_engine,load_engine
import scene_lighting as LIGHT
import survivalist_features as SURVIVAL
import vision_impairment as VISION


class SceneLightingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,719)
        self.e.grid=Grid(12,10)
        stats={'hp':30,'atk':10,'def':10,'spa':10,'spd':10,'spe':10}
        self.a=Combatant(self.r,dict(name='observer',kind='trainer',level=20,stats=stats,
            size='중형',skills={'통찰':3,'직감':3},moves=['move/몸통박치기'],pos=(1,4)))
        self.t=Combatant(self.r,dict(name='target',kind='pokemon',level=20,stats=stats,
            size='중형',types=['노말'],moves=['move/몸통박치기'],pos=(5,4)))
        self.e.gm.add_combatant(self.a);self.e.gm.add_combatant(self.t)
        self.e.configure_scene_lighting(darkness=True,reason='observed ordinary dark cave')

    def lantern(self):
        return self.e.observe_scene_light('lantern',kind='lantern',owner=self.a,reason='held lit lantern')

    def projection(self):return self.e.scene_light_projection(self.a,self.t)

    def fresh(self):
        ids=(self.a.entity_id,self.t.entity_id)
        self.e=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        index={a.entity_id:a for a in self.e.everyone};self.a,self.t=(index[x] for x in ids)

    def test_printed_distance_examples_and_union_use_one_native_accuracy_and_skill_penalty(self):
        self.lantern()
        SURVIVAL.observe_environment(self.e,self.a,terrains=['cave'],light='complete_darkness',reason='same cave darkness')
        move=self.r.move('move/몸통박치기')
        self.assertEqual(self.projection()['penalty'],-4)
        self.assertEqual(VISION.accuracy_penalty(self.e,self.a,self.t),-4)
        self.assertFalse(self.e.accuracy_check(self.a,self.t,move,fixed_roll=7)[0])
        self.assertEqual(self.e.skill_check(self.a,'통찰',6,fixed=[3,3,3],skill_target=self.t),(False,5))
        self.assertEqual(self.e.skill_roll(self.a,'통찰',fixed=[3,3,3]).total,9)
        self.assertEqual(self.e.skill_roll(self.a,'직감',fixed=[3,3,3],skill_target=self.t).total,9)
        self.t.pos=(3,4)
        self.assertEqual(self.projection()['penalty'],0)
        self.assertTrue(self.e.accuracy_check(self.a,self.t,move,fixed_roll=7)[0])
        self.assertEqual(self.e.skill_roll(self.a,'통찰',fixed=[3,3,3],skill_target=self.t).total,9)
        self.t.pos=(5,4)
        self.e.observe_scene_light('far',kind='lantern',origin=(7,4),reason='second ordinary source')
        self.assertEqual(self.projection()['unlit_cells'],((4,4),))
        self.assertEqual(self.projection()['penalty'],-2)
        self.e.observe_scene_light('overlap',kind='lantern',origin=(1,4),reason='overlapping source')
        self.assertEqual(self.projection()['penalty'],-2)
        self.e.remove_scene_light('far',reason='removed lantern')
        self.assertEqual(self.projection()['penalty'],-4)

    def test_live_origin_gm_and_cold_restore_and_scene_only_expiry(self):
        self.lantern();self.e.gm.snapshot('lit')
        self.a.pos=(2,4)
        self.assertEqual(self.projection()['penalty'],-2)
        self.e.remove_scene_light('lantern',reason='put away')
        self.assertEqual(self.projection()['penalty'],-6)
        self.e.gm.restore('lit')
        self.assertEqual(self.projection()['penalty'],-4)
        self.fresh();self.assertEqual(self.projection()['penalty'],-4)
        self.e.start_round(self.e.everyone)
        self.e.end_encounter(self.e.everyone,round_elapsed_seconds=0)
        self.assertEqual(self.projection()['penalty'],-4)
        self.e.end_scene()
        self.assertIsNone(self.projection())
        dump_engine(self.e)

    def test_invalid_observation_and_saved_mutation_refuse_atomically(self):
        self.lantern()
        for options in ({'kind':'unsupported','origin':(1,1)},
                        {'kind':'lantern','origin':(-1,0)},
                        {'kind':'lantern','owner':self.a,'radiant':True},
                        {'kind':'glow','owner':self.t}):
            before=dump_engine(self.e)
            with self.assertRaises(ValueError):self.e.observe_scene_light('bad',reason='invalid',**options)
            self.assertEqual(before,dump_engine(self.e))
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):self.lantern()
        self.assertEqual(before,dump_engine(self.e))
        row=self.e._scene_lighting['sources']['lantern'];row['kind']='strong_artificial'
        with self.assertRaises(ValueError):dump_engine(self.e)
        row['kind']='lantern';dump_engine(self.e)

    def test_live_glow_size_illuminate_suppression_withdrawal_and_restoration(self):
        self.t.spec['capabilities']=['반짝임']
        self.e.gm.set_ability(self.t,'발광',reason='actual Illuminate source')
        self.e.observe_scene_light('glow',kind='glow',owner=self.t,radiant=True,reason='actual glowing Pokemon')
        for size,radius in (('소형',3),('중형',3),('대형',4),('거대',5)):
            self.t.spec['size']=size
            cells,sources=LIGHT.illuminated(self.e)
            self.assertEqual(sources[0]['radius'],radius)
            self.assertIn((5+radius,4),cells)
            self.assertNotIn((5+radius+1,4),cells)
        self.t.spec['size']='중형'
        self.e.gm.snapshot('glow')
        self.t.abilities_suppressed=True
        self.assertEqual(LIGHT.illuminated(self.e)[1][0]['radius'],2)
        self.fresh()
        self.assertEqual(LIGHT.illuminated(self.e)[1][0]['radius'],2)
        self.t.abilities_suppressed=False
        self.assertEqual(LIGHT.illuminated(self.e)[1][0]['radius'],3)
        self.t.spec['capabilities']=[]
        self.assertEqual(LIGHT.illuminated(self.e),(set(),[]))
        self.fresh()
        self.assertEqual(LIGHT.illuminated(self.e),(set(),[]))
        self.t.spec['capabilities']=['반짝임'];self.t.on_field=False
        self.assertEqual(LIGHT.illuminated(self.e),(set(),[]))
        self.t.on_field=True
        self.assertEqual(LIGHT.illuminated(self.e)[1][0]['radius'],3)

    def test_explicit_blindness_precedence_and_distinct_sensory_exemptions(self):
        self.lantern()
        self.e.apply_status(self.a,'실명',parameters={'cause':'external'})
        self.assertEqual(VISION.accuracy_penalty(self.e,self.a,self.t),-6)
        self.e.cure_status(self.a,'실명')
        self.e.apply_status(self.a,'완전 실명',parameters={'cause':'external'})
        self.assertEqual(VISION.accuracy_penalty(self.e,self.a,self.t),-10)
        with self.assertRaises(ValueError):VISION.require_move(self.e,self.a,self.r.move('move/전광석화'))
        self.e.cure_status(self.a,'완전 실명')
        self.a.spec['capabilities']=['Darkvision']
        self.assertEqual(VISION.accuracy_penalty(self.e,self.a,self.t),0)
        self.assertEqual(self.e.skill_roll(self.a,'통찰',fixed=[3,3,3],skill_target=self.t).total,9)
        self.e.apply_status(self.a,'실명',parameters={'cause':'external'})
        self.assertEqual(VISION.accuracy_penalty(self.e,self.a,self.t),-6)
        self.a.spec['capabilities']=['Blindsense']
        self.assertEqual(VISION.accuracy_penalty(self.e,self.a,self.t),0)


if __name__=='__main__':unittest.main()
