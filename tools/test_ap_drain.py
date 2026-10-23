"""Drain AP resource lifecycle, source ch03:588 / ch06:82 / ch07:750."""
import json,hashlib,sys,unittest,copy
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import test_action_points as _fixture_test_action_points
import test_frequencies as _fixture_test_frequencies
import action_points as AP
import downtime as DT
import items as ITEMS
from engine import Combatant
class DrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):_fixture_test_action_points.ActionPointTests.setUpClass()
    def fixture(self,automatic=False):
        return _fixture_test_action_points.ActionPointTests().fixture(amount=2,mode='제거',automatic=automatic)
    def fire(self,e,a,b,rid,automatic=False):_fixture_test_action_points.ActionPointTests().fire(e,a,b,rid,automatic)
    def test_manual_drain_removes_resource(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_removed'),2);self.assertEqual(a.spec.get('ap_spent',0),0)
    def test_automatic_drain_removes_resource(self):
        e,a,b,rid=self.fixture(True);self.fire(e,a,b,rid,True)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_removed'),2)
    def test_scene_and_new_day_do_not_restore_drained_resource(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid);e.end_scene([a,b]);DT.new_day(a)
        self.assertEqual(a.spec.get('ap_removed'),2);self.assertEqual(AP.available(a),5)
    def test_rest_under_four_hours_does_not_restore(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid);DT.extended_rest(e,a,3.99)
        self.assertEqual(a.spec.get('ap_removed'),2)
    def test_four_hour_rest_restores_drained_ap(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid)
        self.assertEqual(AP.available(a),5);DT.extended_rest(e,a,4);self.assertEqual(AP.available(a),7)
    def test_ordinary_and_drained_costs_share_capacity(self):
        e,a,b,rid=self.fixture();a.spec['ap_spent']=4
        self.fire(e,a,b,rid);self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(AP.available(a),1)
    def test_insufficient_drain_does_not_change_effect_or_action(self):
        e,a,b,rid=self.fixture();a.spec['ap_removed']=6;a.budget={'standard':1,'shift':1,'swift':1}
        before=copy.deepcopy(a.budget);self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,0);self.assertEqual(a.spec['ap_removed'],6);self.assertEqual(a.budget,before)
    def test_unresolved_effect_does_not_drain(self):
        e,a,b,rid=self.fixture()
        for rec in a.registry:
            if rec.get('type')=='feat_manual':rec['effects']=[{'type':'gm','choice':'drain decision pending'}]
        self.fire(e,a,b,rid);self.assertEqual(a.spec.get('ap_removed',0),0)
    def test_save_preserves_drain(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid);z=Combatant(e.r,json.loads(json.dumps(a.spec)))
        self.assertEqual(AP.available(z),5)
    def test_rewind_restores_drain_and_effect(self):
        e,a,b,rid=self.fixture();e.gm.snapshot();self.fire(e,a,b,rid)
        self.assertEqual(a.spec.get('ap_removed'),2);e.gm.restore()
        self.assertEqual(AP.available(a),7);self.assertEqual(b.injuries,0)
    def test_original_drain_features_parse_annotated_cost(self):
        e,a,b,rid=self.fixture()
        for name,amount in [('feat/미래의-챔피언',1),('feat/간호사',2)]:
            effects,header=e.r.feat_effects(name)
            self.assertIn('제거',header['frequency']['raw'])
            self.assertEqual(AP.quote(header,effects),(amount,''))
    def test_bind_still_requires_effect_lifetime(self):
        e,a,b,rid=_fixture_test_action_points.ActionPointTests().fixture(mode='지속')
        self.fire(e,a,b,rid);self.assertEqual(b.injuries,0)
        self.assertTrue(any('[보류]' in line for line in e.log_lines))
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='DRAIN-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='DRAIN-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='DRAIN-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(DrainTests))
    paths=[p for folder,pat in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pat)]
    paths += [Path(__file__),ROOT/'tools/test_action_points.py',ROOT/'tools/test_frequencies.py',ROOT/'tools/synthetic_rule_fixture.py']+[ROOT/('input/'+n) for n in ['ch03-skills-edges-feats.md','ch06-gameplay.md','ch07-combat.md']]
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Drain AP resource lifetime only; complete feat semantics and bound effect lifetimes remain unverified.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/ap-drain-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
