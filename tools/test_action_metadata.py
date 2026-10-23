"""Common missing-action regressions. Synthetic effects isolate cost dispatch.
Crafting classification is explicit input evidence, not inferred from a name.
"""
import copy, hashlib, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'engine')]
import test_action_points as _fixture_test_action_points
import action_metadata as META

class ActionMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): _fixture_test_action_points.ActionPointTests.setUpClass()

    def fixture(self, automatic, case):
        helper=_fixture_test_action_points.ActionPointTests()
        e,a,b,rid=helper.fixture(amount=2,automatic=automatic,action='free')
        rec=next(x for x in (a.ability_triggers if automatic else a.registry)
                 if x.get('_feat') or x.get('type')=='feat_manual')
        if case=='missing_header':
            rec.pop('activation_header');rec['frequency']='2 AP'
        elif case=='unknown_raw':
            rec['frequency']='2 AP - <unparsed action>'
            rec['activation_header']={'frequency':{'raw':rec['frequency'],'ap':2}}
        elif case=='null_action':
            rec['activation_header']['frequency']['action']=None
        elif case=='crafting':
            rec['frequency']='2 AP'
            rec['activation_header']={'feature_kind':'crafting','frequency':{'raw':'2 AP','ap':2}}
        elif case=='raw_free':
            rec['frequency']='2 AP - 자유 행동'
            rec['activation_header']={'frequency':{'raw':rec['frequency'],'ap':2}}
        elif case=='static_activation':
            rec['activation_header']={'frequency':{'raw':'항상','action':'static','kind':'static'}}
            rec['cost_effects']=[]
        elif case=='raw_conflict':
            rec['activation_header']['frequency'].update(action='free',raw='2 AP - 기본 행동')
        elif case in ('compound_priority','compound_cost','static_activation'):
            raw='2 AP - 기본 행동 + '+('우선' if case=='compound_priority' else '신속 행동')
            rec['activation_header']['frequency'].update(action='standard',raw=raw)
            if case=='compound_cost':
                import frequency as FREQ
                FREQ.state(a)  # Now supported metadata reaches the resource preflight.
        elif case=='standard':
            rec['activation_header']['frequency'].update(action='standard',raw='2 AP - 기본 행동')
            # Known actions reach the existing frequency reader, which lazily initializes state.
            # Materialize it before this resource-insufficiency control; unknown cases stay pristine.
            import frequency as FREQ
            FREQ.state(a)
        a.budget={'standard':0,'shift':0,'swift':0}
        return helper,e,a,b,rid

    @staticmethod
    def state(e,a,b):
        return copy.deepcopy((a.spec,b.spec,a.budget,a.counters,b.counters,
             getattr(a,'_action_history',[]),a.took_standard,e.round_no,
             e.elapsed_seconds,e.rng.getstate()))

    def check_case(self,automatic,case):
        helper,e,a,b,rid=self.fixture(automatic,case);before=self.state(e,a,b)
        helper.fire(e,a,b,rid,automatic)
        if case in ('explicit_free','raw_free'):
            self.assertEqual(a.spec.get('ap_spent'),2);self.assertEqual(b.injuries,1)
            self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':0})
            self.assertEqual(a._action_history,['free'])
        else:
            self.assertEqual(self.state(e,a,b),before)
            self.assertTrue(any('보류' in line or '남지 않음' in line for line in e.log_lines))

    def test_crafting_default_is_extended_only_when_explicitly_classified(self):
        self.assertEqual(META.resolve_feature_action({'feature_kind':'crafting'}),('extended',''))
        self.assertIsNone(META.resolve_feature_action({})[0])
        self.assertIsNone(META.resolve_feature_action({'cost':1,'ingredient':'ore','name':'crafting'})[0])

    def test_crafting_explicit_action_overrides_scoped_default(self):
        self.assertEqual(META.resolve_feature_action({'feature_kind':'crafting','frequency':{'action':'free'}}),('free',''))
        self.assertIsNone(META.resolve_feature_action({'feature_kind':'crafting','frequency':{'raw':'2 AP - unknown'}})[0])

    def test_trigger_is_not_a_universal_free_default(self):
        self.assertIsNone(META.resolve_feature_action({'trigger':'when something happens','frequency':'2 AP'})[0])

    def test_old_extractor_missing_action_static_is_not_free_evidence(self):
        self.assertIsNone(META.resolve_feature_action({'frequency':{'action':'static','kind':'at_will','raw':'2 AP'}})[0])
        self.assertIsNone(META.resolve_feature_action({'frequency':{'action':'static','kind':'static','raw':''}})[0])
        self.assertEqual(META.resolve_feature_action({'frequency':{'action':'static','raw':'항상'}}),('static',''))

    def test_unknown_compound_and_malformed_remain_unknown(self):
        for header in (None,{'frequency':3},{'frequency':{'raw':None}},
                       {'frequency':{'action':['free']}},{'frequency':'2 AP - 자유 행동 + 우선'}):
            with self.subTest(header=header): self.assertIsNone(META.resolve_feature_action(header)[0])

    def test_real_extractor_recovers_complete_cost_but_holds_priority(self):
        from mechanize_feats import parse_frequency
        for raw in ('임의 - 기본 행동 + 신속 행동','임의 - 기본 행동+신속 행동','임의 - 기본 행동 + 우선'):
            extracted=parse_frequency(raw)
            self.assertEqual(extracted['action'],'standard')
            parsed=META.resolve_feature_action({'frequency':extracted})[0]
            if '우선' in raw:self.assertIsNone(parsed)
            else:self.assertEqual(parsed,META.ActionCost(('standard','swift')))

    def test_crafting_default_handles_unanchored_extractor_placeholder(self):
        from mechanize_feats import parse_frequency
        for raw in ('','2 AP'):
            self.assertEqual(META.resolve_feature_action({'feature_kind':'crafting','frequency':parse_frequency(raw)}),('extended',''))
        self.assertEqual(META.resolve_feature_action({'feature_kind':'crafting','frequency':parse_frequency('항상')}),('static',''))

    def test_feature_registration_never_executes_unknown_or_active_actions(self):
        import items as ITEMS
        for frequency in ({}, {'raw':'임의 - 기본 행동+신속 행동','action':'standard'},
                          {'raw':'임의 - 기본 행동','action':'free'},
                          {'raw':'임의 - 자유 행동','action':'free'},
                          {'raw':'임의 - 기본 행동','action':'standard'}):
            with self.subTest(frequency=frequency):
                helper,e,a,b,rid=self.fixture(False,'explicit_free')
                import state_grants as GRANTS
                GRANTS.revoke(a,'feature:'+a.entity_id+':'+rid,engine=e)
                e.r.feats_mech[rid]={'name':'registration fixture','coverage':'full',
                    'header':{'frequency':frequency},'effects':[{'type':'grant_move','moves':['초음파']} ]}
                moves=list(a.moves);ITEMS.register_feats(e,a)
                self.assertEqual(a.moves,moves)
                self.assertTrue(any(x.get('type')=='feat_manual' for x in a.registry))
                self.assertEqual(a.spec.get('ap_spent',0),0)

    def test_real_nonstatic_feature_is_not_an_automatic_passive(self):
        import items as ITEMS
        helper,e,a,b,rid=self.fixture(False,'explicit_free');a.registry=[]
        a.spec['feats']=['feat/집중성-훈련'];a.spec['edges']=[];a.spec.setdefault('skills',{})['명령']=3
        before=a.accuracy_stage
        ITEMS.register_feats(e,a)
        self.assertEqual(a.accuracy_stage,before)
        import common_checks as CHECKS
        self.assertIsInstance(e.manual_feat(a,'feat/집중성-훈련',b),CHECKS.PendingDecision)
        self.assertFalse(any(x.get('type')=='training_regime' for x in a.registry))

    def test_real_static_registration_and_edge_acquisition_remain_distinct(self):
        import items as ITEMS
        helper,e,a,b,rid=self.fixture(False,'explicit_free');a.registry=[]
        a.spec['feats']=['feat/달맞이산-블루스'];a.spec['edges']=['edge/기본-무술','edge/호감인']
        ITEMS.register_feats(e,a)
        self.assertIn(e.r.move_id('초음파'),a.moves)
        self.assertIn(e.r.move_id('바위깨기'),a.moves)
        self.assertIn(e.r.move_id('초롱초롱눈동자'),a.moves)
        self.assertFalse(any(x.get('type')=='feat_manual' for x in a.registry))

    def test_exact_raw_action_labels(self):
        for text,expected in [('At-Will - Free Action','free'),('2 AP – 기본 행동','standard'),
                              ('Drain 2 AP — Extended Action','extended')]:
            self.assertEqual(META.resolve_feature_action({'frequency':text}),(expected,''))

for automatic in (False,True):
    for case in ('missing_header','unknown_raw','null_action','crafting','explicit_free','raw_free','standard','raw_conflict','compound_priority','compound_cost','static_activation'):
        def test(self,automatic=automatic,case=case):self.check_case(automatic,case)
        setattr(ActionMetadataTests,'test_'+('trigger_' if automatic else 'manual_')+case,test)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'ACTION-METADATA-'+t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'ACTION-METADATA-'+t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'ACTION-METADATA-'+t._testMethodName,'status':'error'})
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActionMetadataTests))
    paths=[Path(__file__),ROOT/'tools/test_action_points.py',ROOT/'tools/test_frequencies.py',ROOT/'tools/synthetic_rule_fixture.py',ROOT/'tools/mechanize_feats.py']
    paths += list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))
    paths += [ROOT/'output/ruleunits.jsonl',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']
    paths += list((ROOT/'output/entities').glob('*.json'))
    paths += [ROOT/'input/ch03-skills-edges-feats.md',ROOT/'input/ch06-gameplay.md',ROOT/'input/ch07-combat.md']
    out={'scope':'Missing/unknown action handling and explicit crafting Extended default; no AP binding, crafting execution or whole rule coverage claim.','results':r.rows,'input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'semantic_closure':False}
    (ROOT/'output/action-metadata-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not r.wasSuccessful())
