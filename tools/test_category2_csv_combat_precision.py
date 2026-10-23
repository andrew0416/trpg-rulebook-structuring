"""Exact CSV sources reuse the native Pinpoint and Blur consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from state_codec import dump_engine,load_engine
import combat_precision_features as P
import items as I
import test_category3_combat_precision as FIX

PINPOINT='C2CSV/input/db/feats.csv:R33:main'
BLUR='C2CSV/input/db/feats.csv:R36:main'


class CsvCombatPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')

    def setUp(self):
        self.f=FIX.CombatPrecisionTests();self.f.r=self.r;self.f.setUp()
        self.e,self.a,self.p,self.t=self.f.e,self.f.a,self.f.p,self.f.t
        for actor in self.e.everyone:
            actor.moves=actor.moves[:6];actor.spec['moves']=actor.moves[:]

    def bind(self):
        self.a.spec['feats'].append(PINPOINT)
        I.register_feats(self.e,self.a)
        self.f.begin()
        self.assertEqual(self.e.manual_feat(self.a,PINPOINT,self.p),(1,0))
        row=P.binding(self.e,self.p)
        self.assertEqual(row['source'],PINPOINT)
        self.assertTrue(row['instance'].startswith(PINPOINT+':'))
        self.assertEqual(self.a.spec['ap_bound'][row['instance']],2)
        return row

    def blur(self,mode='apply',base=9):
        self.t.stats['spe']=self.t.spec['stats']['spe']=base+int(mode=='included')
        self.t.spec['feats']=[BLUR]
        self.t.spec['feature_stat_imports']={BLUR:{'mode':mode,'base_stat':base}}
        I.register_feats(self.e,self.t)

    def restore(self):
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
        self.a,self.p,self.t=self.e.everyone
        self.f.e,self.f.a,self.f.p,self.f.t=self.e,self.a,self.p,self.t

    def test_csv_pinpoint_native_damage_accuracy_and_secondary_threshold_share_original_binding(self):
        self.bind();self.assertEqual(self.a.budget['standard'],0)
        move=self.r.move('move/불꽃세례')
        reduced=self.e.roll_damage(self.p,self.t,move,set_damage=True)
        self.assertTrue(self.f.accuracy(self.p,self.t,move['id'],3)[0])
        self.assertFalse(self.f.accuracy(self.p,self.t,move['id'],1)[0])
        self.assertFalse(self.f.accuracy(self.p,self.t,move['id'],18)[2])
        self.assertFalse(self.f.accuracy(self.p,self.t,'move/째려보기',2)[0])
        self.f.pokemon_turn();before=self.t.hp
        self.f.move(self.p,self.t,move['id'],16)
        self.assertEqual(before-self.t.hp,reduced)
        self.assertIn('화상',self.t.conditions)
        self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(sum(self.a.spec['ap_bound'].values()),2)
        P._unbind(self.e,self.p,P.binding(self.e,self.p))
        self.assertEqual(self.e.roll_damage(self.p,self.t,move,set_damage=True)-reduced,5)

    def test_csv_pinpoint_gm_and_json_keep_actual_owners_and_release_only_matching_two_ap(self):
        original=self.bind()['instance'];self.a.spec['ap_bound']['independent']=1
        self.e.gm.snapshot('csv-pinpoint')
        self.e.release_pinpoint_strike(self.a,self.p)
        self.e.gm.restore('csv-pinpoint');self.restore()
        row=P.binding(self.e,self.p)
        self.assertIs(row['owner'],self.a);self.assertIs(row['target'],self.p)
        self.assertEqual((row['source'],row['instance']),(PINPOINT,original))
        self.assertEqual(self.e.release_pinpoint_strike(self.a,self.p),(1,0))
        self.assertEqual(self.a.spec['ap_bound'],{'independent':1})
        self.assertNotIn(P.KEY,self.p.custom_conditions)
        with self.assertRaises(ValueError):self.e.release_pinpoint_strike(self.a,self.p)

    def test_csv_pinpoint_missing_duplicate_changed_acquisition_and_selection_refuse_before_cost(self):
        self.f.begin();before=self.f.state()
        with self.assertRaises(ValueError):self.e.manual_feat(self.a,PINPOINT,self.p)
        self.assertEqual(before,self.f.state())
        self.a.spec['feats'] += [PINPOINT,P.PINPOINT];before=self.f.state()
        with self.assertRaises(ValueError):self.e.manual_feat(self.a,PINPOINT,self.p)
        self.assertEqual(before,self.f.state())
        self.setUp();self.bind();self.f.pokemon_turn()
        selected=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**kw: uid+'-other' if uid==PINPOINT else selected(uid,**kw)):
            before=self.f.state()
            with self.assertRaises(ValueError):self.e.use_move(self.p,self.t,'move/불꽃세례')
            self.assertEqual(before,self.f.state())
        self.a.spec['feats'].remove(PINPOINT);self.a.spec['feats'].append(P.PINPOINT)
        before=self.f.state()
        with self.assertRaises(ValueError):self.e.use_move(self.p,self.t,'move/불꽃세례')
        self.assertEqual(before,self.f.state())

    def test_csv_blur_one_speed_receipt_special_accuracy_and_both_restores(self):
        self.blur();I.register_feats(self.e,self.t)
        self.assertEqual((self.t.stats['spe'],self.t.spec['stats']['spe']),(10,10))
        receipt=deepcopy(self.t.custom_conditions['_feature_stat_receipts'][BLUR])
        self.assertEqual((receipt['source'],receipt['before'],receipt['after']),(BLUR,9,10))
        self.assertNotIn(P.BLUR,self.t.custom_conditions['_feature_stat_receipts'])
        self.t.stats['spd']=30;self.t.evasion_mod=3
        self.assertFalse(self.f.accuracy(self.p,self.t,'move/스피드스타',5)[0])
        self.assertTrue(self.f.accuracy(self.p,self.t,'move/스피드스타',6)[0])
        self.assertFalse(self.f.accuracy(self.p,self.t,'move/불꽃세례',10)[0])
        self.e.gm.snapshot('csv-blur');self.t.stats['spe']=77
        self.e.gm.restore('csv-blur');self.restore();I.register_feats(self.e,self.t)
        self.assertEqual(self.t.stats['spe'],10)
        self.assertEqual(self.t.custom_conditions['_feature_stat_receipts'][BLUR],receipt)
        self.f.begin(self.p);before=self.t.hp
        self.f.move(self.p,self.t,'move/스피드스타',6)
        self.assertLess(self.t.hp,before)
        self.assertEqual(self.p.budget['standard'],0)

    def test_csv_blur_included_import_and_source_switch_never_double_add_speed(self):
        self.blur('included');I.register_feats(self.e,self.t)
        self.assertEqual(self.t.stats['spe'],10)
        self.t.spec['feats']=[P.BLUR]
        self.t.spec['feature_stat_imports'][P.BLUR]={'mode':'apply','base_stat':10}
        before=deepcopy((self.t.spec,self.t.stats,self.t.custom_conditions))
        with self.assertRaises(ValueError):I.register_feats(self.e,self.t)
        self.assertEqual((self.t.spec,self.t.stats,self.t.custom_conditions),before)
        self.setUp();self.t.spec['feats']=[BLUR]
        self.t.spec['feature_stat_imports']={P.BLUR:{'mode':'apply','base_stat':5}}
        with self.assertRaises(ValueError):I.register_feats(self.e,self.t)
        self.assertEqual(self.t.stats['spe'],5)

    def test_csv_blur_duplicate_and_changed_selection_fail_before_native_attack_cost(self):
        self.blur();self.f.begin(self.p)
        selected=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid,**kw: uid+'-other' if uid==BLUR else selected(uid,**kw)):
            before=(dict(self.p.budget),dict(self.p.move_uses),self.e.rng.getstate())
            with self.assertRaises(ValueError):self.e.use_move(self.p,self.t,'move/스피드스타')
            self.assertEqual(before,(dict(self.p.budget),dict(self.p.move_uses),self.e.rng.getstate()))
        self.t.spec['feats'].append(P.BLUR)
        before=(dict(self.p.budget),self.e.rng.getstate(),self.t.stats['spe'])
        with self.assertRaises(ValueError):self.e.use_move(self.p,self.t,'move/스피드스타')
        self.assertEqual(before,(dict(self.p.budget),self.e.rng.getstate(),self.t.stats['spe']))


if __name__=='__main__':unittest.main()
