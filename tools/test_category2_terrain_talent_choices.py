"""Terrain Talent choice provenance, rank growth and global native consumers."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from state_codec import dump_engine,load_engine
import survivalist_features as V
import test_category3_survivalist as FIX


class TerrainTalentChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.f=FIX.Tests();self.f.r=self.r;self.f.setUp()
        self.e,self.a=self.f.e,self.f.a

    def activity(self,action,**options):
        return self.e.survivalist_activity(self.a,action,**options)

    def restore(self):
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
        self.a=self.e.everyone[0];self.f.e,self.f.a=self.e,self.a

    def test_fixed_two_choices_keep_native_bonus_outside_habitat_after_both_restores(self):
        self.a.spec['feats'].append('feat/내추럴-파이터')
        self.f.master('grassland');self.f.master('mountain')
        self.a.spec['feats'].append(V.TALENT);self.a.spec['feat_ranks']={V.TALENT:1}
        self.activity('choose_talents',terrains=['초원','산'])
        chosen=deepcopy(self.a.spec['_survivalist_talents'])
        self.activity('observe_environment',terrains=['urban'],light='normal',reason='actual different habitat')
        self.e.gm.everyone=self.e.everyone;self.e.gm.snapshot('chosen-talents')
        self.a.spec['_survivalist_talents']['terrains']=('cave','forest')
        self.e.gm.restore('chosen-talents');self.restore()
        self.assertEqual(self.a.spec['_survivalist_talents'],chosen)
        self.assertEqual(V.talents(self.e,self.a),('grassland','mountain'))
        out=self.e.skill_roll(self.a,'통찰',fixed=[1]*3,skill_context=self.f.context('distant_object'))
        self.assertEqual(out.total,5)
        self.assertEqual(self.e.skill_roll(self.a,'통찰',fixed=[1]*3).total,3)
        before=dump_engine(self.e)
        for choices in (['산','초원'],['동굴','숲'],['초원','초원'],['초원','바다']):
            with self.subTest(choices=choices),self.assertRaises(ValueError):
                self.activity('choose_talents',terrains=choices)
            self.assertEqual(dump_engine(self.e),before)
        self.a.spec['feats'].remove(V.TALENT);before=dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.skill_roll(self.a,'통찰',fixed=[1]*3)
        self.assertEqual(dump_engine(self.e),before)

    def test_rank_two_requires_four_real_histories_and_extends_original_choices_once(self):
        self.f.talent('cave','grassland')
        initial=deepcopy(self.a.spec['_survivalist_talents'])
        self.a.spec['feats'].extend(['feat/트래퍼','feat/야생-가이드'])
        self.a.spec['feat_ranks'][V.TALENT]=2
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):
            self.activity('choose_talents',terrains=['cave','grassland','mountain','urban'])
        self.assertEqual(dump_engine(self.e),before)
        self.f.master('mountain');self.f.master('urban')
        before=dump_engine(self.e)
        for choices in (['cave','grassland'],['cave','grassland','mountain','ocean'],
                        ['cave','grassland','mountain','mountain']):
            with self.subTest(choices=choices),self.assertRaises(ValueError):
                self.activity('choose_talents',terrains=choices)
            self.assertEqual(dump_engine(self.e),before)
        self.activity('choose_talents',terrains=['cave','grassland','mountain','urban'])
        record=deepcopy(self.a.spec['_survivalist_talents'])
        self.assertTrue(set(initial['terrains'])<=set(record['terrains']))
        self.assertEqual((record['source'],record['rank'],len(record['terrains'])),(V.TALENT,2,4))
        self.restore()
        self.assertEqual(self.a.spec['_survivalist_talents'],record)
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):
            self.activity('choose_talents',terrains=list(reversed(record['terrains'])))
        self.assertEqual(dump_engine(self.e),before)
        for name in record['terrains']:
            actual=next(x for x in self.a.spec['_survivalist_terrains'] if x['terrain']==name)
            self.assertGreaterEqual(len(actual['nights']),3)
            self.assertTrue(set(actual['nights'])<=self.a.spec['_survivalist_nights'].keys())


if __name__=='__main__':unittest.main()
