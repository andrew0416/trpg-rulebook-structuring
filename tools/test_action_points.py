"""AP activation cost regressions against ch02:113 / ch03:586-588 / ch06:78-85."""
import json,hashlib,sys,unittest,copy
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import test_frequencies as _fixture_test_frequencies
from synthetic_rule_fixture import register_synthetic
import items as ITEMS
import effects as FX
import action_points as AP
from engine import Combatant

class ActionPointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_frequencies.FrequencyTests.setUpClass()
        register_synthetic(_fixture_test_frequencies.FrequencyTests.rules,'feat/ap-audit',name='Synthetic AP state fixture',kind='test_fixture')
    def fixture(self,amount=2,mode='',automatic=False,action='free',frequency=None):
        e,a,b,_=_fixture_test_frequencies.FrequencyTests().fixture()
        e.rulings=copy.deepcopy(e.rulings)  # GM answers belong to this test, never a shared Rules fixture.
        action_label={'free':'자유 행동','standard':'기본 행동','shift':'이동 행동','swift':'신속 행동','full':'완전 행동','extended':'연장 행동'}.get(action,action)
        raw=f'{amount} AP {mode} - {action_label}'
        header={'frequency':{'raw':raw,'kind':'at_will','ap':amount,'action':action}}
        if frequency is not None:header['frequency']=copy.deepcopy(frequency)
        effects=[{'type':'cost','ap':amount},{'type':'injury','value':1,'target':'target'}]
        if automatic:effects.insert(0,{'type':'trigger','text':'사용자가 기술을 사용할 때'})
        rid='feat/ap-audit'
        e.r.feats_mech[rid]={'name':'ap-audit','coverage':'full','header':header,'effects':effects}
        a.spec['feats']=[rid]
        ITEMS.register_feats(e,a)
        return e,a,b,rid
    def fire(self,e,a,b,rid,automatic=False):
        if automatic:FX.fire_event(e,a,{'event':'on_move_use','move':{'name':'audit'}},b)
        else:ITEMS.manual_feat(e,a,rid,b)
    def test_common_charge_separates_reservations_drain_and_scene_spend(self):
        e,a,b,rid=self.fixture();maximum=AP.available(a)
        AP.charge(a,1,mode='spend');AP.charge(a,1,mode='drain')
        AP.charge(a,1,mode='bind',instance_id='effect/a')
        AP.charge(a,1,mode='bind',instance_id='effect/b')
        self.assertEqual(AP.available(a),maximum-4)
        AP.end_scene(a);self.assertEqual(AP.available(a),maximum-3)
        AP.release_binding(a,'effect/a',expected_amount=1)
        self.assertEqual(a.spec['ap_bound'],{'effect/b':1})
        self.assertEqual(AP.available(a),maximum-2)
        AP.extended_rest(a);self.assertEqual(AP.available(a),maximum-1)

    def test_common_reservation_rejects_duplicate_wrong_refund_and_overdraft(self):
        e,a,b,rid=self.fixture();AP.charge(a,1,mode='bind',instance_id='effect/a')
        before=copy.deepcopy(a.spec)
        for operation in [lambda:AP.charge(a,1,mode='bind',instance_id='effect/a'),
                          lambda:AP.release_binding(a,'effect/a',expected_amount=2),
                          lambda:AP.charge(a,AP.maximum(a),mode='bind',instance_id='effect/b'),
                          lambda:AP.charge(a,True,mode='spend')]:
            with self.assertRaises(ValueError):operation()
            self.assertEqual(a.spec,before)
        AP.release_binding(a,'effect/a',expected_amount=1)
        with self.assertRaises(ValueError):AP.release_binding(a,'effect/a',expected_amount=1)

    def test_registration_does_not_activate_costed_effect(self):
        e,a,b,rid=self.fixture()
        self.assertEqual(a.injuries,0)
        self.assertTrue(any(x.get('type')=='feat_manual' for x in a.registry))
    def test_manual_cost_spent_once(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_spent'),2)
    def test_auto_cost_spent_once(self):
        e,a,b,rid=self.fixture(automatic=True);self.fire(e,a,b,rid,True)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_spent'),2)
    def test_scene_restores_spent_ap(self):
        e,a,b,rid=self.fixture();a.spec['ap_spent']=7
        e.end_scene([a,b]);self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_spent'),2)
    def test_scene_does_not_restore_drained_ap(self):
        e,a,b,rid=self.fixture();a.spec['ap_removed']=6
        e.end_scene([a,b]);self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,0);self.assertEqual(a.spec['ap_removed'],6)
    def test_insufficient_action_does_not_charge_ap(self):
        e,a,b,rid=self.fixture(action='standard');a.budget={'standard':0,'shift':1,'swift':1}
        self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,0);self.assertEqual(a.spec.get('ap_spent',0),0)
    def test_action_cost_and_ap_both_spent(self):
        e,a,b,rid=self.fixture(action='standard');a.budget={'standard':1,'shift':1,'swift':1}
        self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(a.budget['standard'],0);self.assertEqual(a.spec.get('ap_spent'),2)
    def test_no_effect_resolved_does_not_charge(self):
        e,a,b,rid=self.fixture()
        for rec in a.registry:
            if rec.get('type')=='feat_manual':rec['effects']=[{'type':'unresolved_audit_effect'}]
        self.fire(e,a,b,rid);self.assertEqual(a.spec.get('ap_spent',0),0)
    def test_gm_rewind_restores_spent_ap(self):
        e,a,b,rid=self.fixture();e.gm.snapshot()
        self.fire(e,a,b,rid);self.assertEqual(a.spec.get('ap_spent'),2)
        e.gm.restore();self.assertEqual(a.spec.get('ap_spent',0),0)
    def test_unanswered_gm_prompt_is_pending_not_executed(self):
        e,a,b,rid=self.fixture()
        done,held=FX.run_effects(e,a,b,[{'type':'gm','choice':'audit GM choice'}],{'attacker':a,'target':b,'hit':True},'audit')
        self.assertEqual((done,held),(0,1));self.assertEqual(len(e.gm_prompts),1)
    def test_pending_gm_choice_does_not_spend_ap_or_action(self):
        e,a,b,rid=self.fixture(action='standard');a.budget={'standard':1,'shift':1,'swift':1}
        for rec in a.registry:
            if rec.get('type')=='feat_manual':rec['effects']=[{'type':'gm','choice':'audit GM choice'}]
        self.fire(e,a,b,rid)
        self.assertEqual(a.spec.get('ap_spent',0),0);self.assertEqual(a.budget['standard'],1)
        self.assertEqual(len(e.gm_prompts),1)
    def test_answered_gm_choice_spends_ap_and_applies_effect(self):
        e,a,b,rid=self.fixture()
        for rec in a.registry:
            if rec.get('type')=='feat_manual':rec['effects']=[{'type':'gm','choice':'audit GM choice'}]
        e.rule_answer('audit GM choice',{'effects':[{'type':'injury','value':1,'target':'target'}]},'audit')
        self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_spent'),2)
    def test_optional_cost_requires_explicit_choice(self):
        amount,reason=AP.quote({},[{'type':'cost','ap':1,'optional':True}])
        self.assertIsNone(amount);self.assertTrue(reason)
    def test_header_and_effect_cost_are_not_double_charged(self):
        self.assertEqual(AP.quote({'frequency':{'ap':2}},[{'type':'cost','ap':2}]),(2,''))
    def test_disagreeing_header_and_effect_cost_is_held(self):
        amount,reason=AP.quote({'frequency':{'ap':1}},[{'type':'cost','ap':2}])
        self.assertIsNone(amount);self.assertTrue(reason)
    def test_bound_ap_is_not_available_for_ordinary_spend(self):
        e,a,b,rid=self.fixture();a.spec['ap_bound']={'other-effect':6}
        self.fire(e,a,b,rid);self.assertEqual(b.injuries,0)
    def test_save_reload_preserves_expenditure(self):
        e,a,b,rid=self.fixture();self.fire(e,a,b,rid)
        restored=Combatant(e.r,json.loads(json.dumps(a.spec)));ITEMS.register_feats(e,restored)
        self.assertEqual(restored.spec.get('ap_spent'),2)
        restored.spec['ap_removed']=4;self.fire(e,restored,b,rid)
        self.assertEqual(b.injuries,1)

def add(name,fn):setattr(ActionPointTests,'test_'+name,fn)
for automatic in (False,True):
    for spent in (5,6,7):
        def boundary(self,automatic=automatic,spent=spent):
            e,a,b,rid=self.fixture(automatic=automatic);a.spec['ap_spent']=spent
            self.fire(e,a,b,rid,automatic)
            self.assertEqual(b.injuries,1 if spent==5 else 0)
            self.assertEqual(a.spec['ap_spent'],7 if spent==5 else spent)
        add(('auto' if automatic else 'manual')+'_remaining_'+str(7-spent),boundary)
    def faint(self,automatic=automatic):
        e,a,b,rid=self.fixture(automatic=automatic);a.hp=0
        self.fire(e,a,b,rid,automatic)
        self.assertEqual(b.injuries,0);self.assertEqual(a.spec.get('ap_spent',0),0)
    add(('auto' if automatic else 'manual')+'_fainted_cannot_activate_feat',faint)
for mode in ['지속']:
    def unresolved(self,mode=mode):
        e,a,b,rid=self.fixture(mode=mode);self.fire(e,a,b,rid)
        # Until binding effect lifetimes are implemented, do not grant free effects.
        self.assertEqual(b.injuries,0);self.assertEqual(a.spec.get('ap_spent',0),0)
        self.assertTrue(any('[보류]' in line for line in e.log_lines))
    add('unimplemented_lifetime_is_held_'+mode,unresolved)
for level,maximum in [(1,5),(4,5),(5,6),(9,6),(10,7),(15,8)]:
    def level_boundary(self,level=level,maximum=maximum):
        e,a,b,rid=self.fixture(amount=1);a.level=level;a.spec['level']=level;a.spec['ap_spent']=maximum-1
        self.fire(e,a,b,rid);self.fire(e,a,b,rid)
        self.assertEqual(b.injuries,1);self.assertEqual(a.spec['ap_spent'],maximum)
    add('level_'+str(level),level_boundary)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='AP-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='AP-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='AP-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActionPointTests))
    paths=[p for folder,pat in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pat)]
    paths += [Path(__file__),ROOT/'tools/test_frequencies.py',ROOT/'tools/synthetic_rule_fixture.py']+[ROOT/('input/'+n) for n in ['ch02-character-creation.md','ch03-skills-edges-feats.md','ch06-gameplay.md','ch07-combat.md']]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Ordinary mandatory integer AP cost, actor/action guards, persistence; unsupported bind/choice must be held, not counted as implemented.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/action-point-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
