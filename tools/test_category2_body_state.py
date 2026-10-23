"""Body footprints are state, distinct from a single map token."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"engine")]
from engine import Rules,Engine,Combatant
from grid import Grid
import body_state as B,state_fields as F,builder

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset="core")
    def setUp(self):
        self.e=Engine(self.r,100);self.e.grid=Grid(14,14)
        self.a=Combatant(self.r,builder.build_trainer(self.r,"a",5,{s:5 for s in F.STATS},pos=(2,2)))
        self.p=Combatant(self.r,builder.build_pokemon(self.r,"강철톤",25,pos=(4,2)))
        self.e.everyone=self.e.gm.everyone=[self.a,self.p]
    def test_catalog_size_and_non_square_observed_body(self):
        self.assertEqual(len(B.cells(self.p,require_complete=True)),16)
        shape=[(x,y) for x in range(8) for y in range(2)]
        view=self.e.gm.set_footprint(self.p,shape,reason="GM observes the coiled 8 by 2 body")
        self.assertTrue(view["geometry_complete"])
        self.assertEqual(len(self.e.occupied(self.a)),16)
        self.assertIn((11,3),self.e.occupied(self.a))
        before=deepcopy(self.p.spec)
        with self.assertRaises(ValueError):self.e.gm.set_footprint(self.p,[(0,0),(99,0)],reason="outside map")
        self.assertEqual(self.p.spec,before)
        loaded=Engine.import_state(self.r,self.e.export_state())
        restored=next(x for x in loaded.everyone if x.entity_id==self.p.entity_id)
        self.assertEqual(B.projection(restored),B.projection(self.p))
    def test_native_area_includes_edge_once_even_if_anchor_outside(self):
        self.e.gm.set_footprint(self.p,[(0,0),(-1,0),(-1,1)],reason="GM observed three body cells")
        move_id=next(uid for uid,m in sorted(self.r.moves_mech.items()) if m.get("header",{}).get("range",{}).get("shape")=="burst" and m["header"]["range"].get("size")==1)
        selected=self.e.targets_in_range(self.a,self.r.move(move_id),[self.a,self.p],self.p)
        self.assertEqual(selected,[self.p])
    def test_unknown_size_is_partial_geometry_not_a_verified_one_cell_body(self):
        self.a.spec["size"]=None  # Explicit unknown import, separate from trainer default.
        view=B.projection(self.a)
        self.assertFalse(view["geometry_complete"])
        self.assertEqual(view["cells"],{(2,2)})
        with self.assertRaises(ValueError):B.cells(self.a,require_complete=True)
        self.e.gm.set_footprint(self.a,[(0,0)],reason="GM confirms ordinary medium body")
        self.assertTrue(B.projection(self.a)["geometry_complete"])

if __name__=="__main__":unittest.main(verbosity=2)
