"""Source-derived range diagrams and shared accuracy checks (PTU 1.05 pp338,343-345)."""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import test_frequencies as _fixture_test_frequencies
from grid import Grid
from engine import Combatant

class RangeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):_fixture_test_frequencies.FrequencyTests.setUpClass()
    def offset(self,cells):return {(x+5,y+5) for x,y in cells}
    def test_original_cardinal_cone2_diagram(self):
        self.assertEqual(Grid(20,20).cone((5,5),(1,0),2),self.offset([(1,0),(2,-1),(2,0),(2,1)]))
    def test_original_diagonal_cone2_diagram_four_rotations(self):
        for dx,dy in [(1,1),(1,-1),(-1,1),(-1,-1)]:
            expected=self.offset([(dx,dy),(2*dx,dy),(dx,2*dy)])
            self.assertEqual(Grid(20,20).cone((5,5),(dx,dy),2),expected)
    def test_cardinal_cone3_keeps_three_meter_rows(self):
        expected=self.offset([(1,0),(2,-1),(2,0),(2,1),(3,-1),(3,0),(3,1)])
        self.assertEqual(Grid(20,20).cone((5,5),(1,0),3),expected)
    def test_original_diagonal_line4_diagram(self):
        for dx,dy in [(1,1),(1,-1),(-1,1),(-1,-1)]:
            self.assertEqual(Grid(20,20).line((5,5),(dx,dy),4),self.offset([(dx,dy),(2*dx,2*dy),(3*dx,3*dy)]))
    def test_diagonal_line2_cannot_pay_second_diagonal(self):
        self.assertEqual(Grid(20,20).line((5,5),(1,1),2),{(6,6)})
    def test_original_cardinal_line4_diagram(self):
        self.assertEqual(Grid(20,20).line((5,5),(1,0),4),{(6,5),(7,5),(8,5),(9,5)})
    def area(self):
        e,a,b,m=_fixture_test_frequencies.FrequencyTests().fixture()
        c=Combatant(e.r,dict({k:v for k,v in a.spec.items() if k!='id'},name='second'))
        e.r.moves[m].update(range='원뿔 2',ac=2)
        e.r.moves_mech[m]['header']['range']={'shape':'cone','size':2}
        # Mapped movement/snapshot cases require known body geometry and legal
        # native stats. Speed1 still has zero speed evasion for these assertions.
        for actor in (a,b,c):actor.spec['size']='Medium'
        b.stats['spe']=c.stats['spe']=1
        b.evasion_mod=0;c.evasion_mod=1
        e.targets_in_range=lambda *args:[b,c]
        e.everyone=e.gm.everyone=[a,b,c]
        return e,a,b,c,m
    def test_area_uses_one_natural_roll_with_per_target_evasion(self):
        e,a,b,c,m=self.area();rolls=[]
        def roll():rolls.append(1);return 2 if len(rolls)==1 else 20
        e.d20=roll;e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual(len(rolls),1);self.assertEqual((b.injuries,c.injuries),(1,0))
    def test_area_natural_one_misses_all(self):
        e,a,b,c,m=self.area();rolls=[]
        def roll():rolls.append(1);return 1 if len(rolls)==1 else 20
        e.d20=roll;e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual((b.injuries,c.injuries),(0,0));self.assertEqual(len(rolls),1)
    def test_area_no_roll_when_action_rejected(self):
        e,a,b,c,m=self.area();e.start_round([a,b,c]);e.start_of_turn(a);a.budget={'standard':0}
        e.d20=lambda:(_ for _ in ()).throw(AssertionError('rejected activation must not roll'))
        e.use_move_on(a,b,m,[a,b,c]);self.assertEqual((b.injuries,c.injuries),(0,0))
    def test_original_wall_cone_only_upper_target_hit(self):
        g=Grid(10,10,walls=[((1,1),(2,1)),((1,2),(2,2))])
        self.assertEqual(g.cone((0,1),(1,0),2),{(1,1),(2,0)})
    def test_original_two_walls_block_burst_diagonal(self):
        g=Grid(10,10,walls=[((5,5),(6,5)),((5,5),(5,6))])
        self.assertNotIn((6,6),g.burst((5,5),1))
    def test_one_wall_does_not_block_burst_diagonal(self):
        g=Grid(10,10,walls=[((5,5),(6,5))])
        self.assertIn((6,6),g.burst((5,5),1))
        self.assertNotIn((6,5),g.burst((5,5),1))
    def test_line_stops_at_wall_between_cells(self):
        g=Grid(10,10,walls=[((1,1),(2,1))])
        self.assertEqual(g.line((0,1),(1,0),4),{(1,1)})
    def test_wall_state_restored_by_gm_rewind(self):
        e,a,b,c,m=self.area();e.grid=Grid(10,10,walls=[((1,1),(2,1))])
        e.gm.snapshot();e.grid.walls.clear();e.gm.restore()
        self.assertTrue(e.grid.blocked((0,1),(3,1)))

    def test_area_single_use_accuracy_bonus_applies_to_every_target(self):
        e,a,b,c,m=self.area();c.evasion_mod=0
        e.rule_situational('accuracy',1,who=a.name,uses=1)
        e.d20=lambda:2
        e.r.moves[m]['ac']=3
        e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual((b.injuries,c.injuries),(1,1))
    def test_runtime_movement_respects_diagonal_meter_cost(self):
        e,a,b,c,m=self.area();e.grid=Grid(12,12);e.everyone=[a,b]
        a.pos=(1,1);b.pos=(9,9);a.movement=4
        e.approach(a,b)
        dx,dy=a.pos[0]-1,a.pos[1]-1
        self.assertLessEqual(max(dx,dy)+min(dx,dy)//2,4)
        self.assertNotEqual(a.pos,(1,1))
    def test_runtime_movement_cannot_cross_full_edge_wall(self):
        e,a,b,c,m=self.area();e.grid=Grid(10,1,walls=[((1,0),(2,0))]);e.everyone=[a,b]
        a.pos=(0,0);b.pos=(5,0)
        e.approach(a,b)
        self.assertLess(a.pos[0],2)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='RANGE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='RANGE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='RANGE-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(RangeSourceTests))
    paths=[p for folder,pat in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pat)]
    paths += [ROOT/'tools/synthetic_rule_fixture.py',Path(__file__),ROOT/'tools/test_frequencies.py',ROOT/'input/ch10-index-reference.md',ROOT/'output/source-audit/2026-10-10/ptu-core-1.05.pdf']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Original diagrams pp343-345, cardinal cone rows, line distance, shared AoE natural accuracy; not complete range semantics.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/range-source-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
