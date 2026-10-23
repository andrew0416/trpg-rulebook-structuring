"""Independent tests for source-labelled feature action dispatch (not leaf semantics)."""
import copy, hashlib, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from synthetic_rule_fixture import register_synthetic
from mechanize_feats import parse_frequency
import items as I, effects as FX, action_metadata as M, frequency as F

class Independent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='all')
        register_synthetic(cls.rules,'feat/independent-action',name='isolated action dispatch fixture')
    def fixture(self,header,automatic=False,effects=None):
        r=self.rules; rid='feat/independent-action'
        payload=effects if effects is not None else [{'type':'injury','value':1,'target':'target'}]
        if automatic: payload=[{'type':'trigger','text':'사용자가 기술을 사용할 때'}]+payload
        r.feats_mech[rid]={'name':rid,'coverage':'full','header':copy.deepcopy(header),'effects':copy.deepcopy(payload)}
        e=Engine(r,seed=31)
        def actor(n):return Combatant(r,{'name':n,'kind':'trainer','level':10,'stats':{s:30 for s in ['hp','atk','def','spa','spd','spe']},'types':[],'abilities':[],'moves':[]})
        a,b=actor('a'),actor('b');e.everyone=e.gm.everyone=[a,b];a.spec['feats']=[rid]
        I.register_feats(e,a)
        if automatic and not a.ability_triggers:
            # Exercise dispatch's own guard as well as the separate registration guard.
            # This is a saved activation record, not a Python callback alteration.
            a.registry=[]
            r.feats_mech[rid]['header']={'frequency':parse_frequency('2 AP - 자유 행동')}
            I.register_feats(e,a)
            self.assertEqual(len(a.ability_triggers),1)
            a.ability_triggers[0]['activation_header']=copy.deepcopy(header)
            freq=header.get('frequency',{})
            a.ability_triggers[0]['frequency']=freq.get('raw','') if isinstance(freq,dict) else freq
        e.start_round([a,b]);e.start_of_turn(a)
        a.budget={'standard':0,'shift':0,'swift':0}
        return e,a,b,rid
    @staticmethod
    def snapshot(e,a,b):
        return copy.deepcopy({'aspec':a.spec,'bspec':b.spec,'ahp':a.hp,'bhp':b.hp,'ai':a.injuries,'bi':b.injuries,'budget':a.budget,'history':getattr(a,'_action_history',[]),'standard':a.took_standard,'counters':a.counters,'bcounters':b.counters,'rng':e.rng.getstate(),'clock':e.elapsed_seconds,'round':e.round_no,'mods':a.modifiers,'bmods':b.modifiers,'moves':a.moves})
    @staticmethod
    def fire(e,a,b,rid,auto):
        if auto:FX.fire_event(e,a,{'event':'on_move_use','move':{'name':'fixture'}},b)
        else:I.manual_feat(e,a,rid,b)
    def test_actual_parser_placeholder_and_compound_do_not_supply_authority(self):
        # Known conjunction is now supported; missing labels and timing keywords remain pending.
        for raw in ('','장면','임의 - 기본 행동 + 우선','임의 - 자유 행동 + 방해'):
            with self.subTest(raw=raw): self.assertIsNone(M.resolve_feature_action({'frequency':parse_frequency(raw)})[0])
        self.assertEqual(M.resolve_feature_action({'frequency':parse_frequency('임의 - 기본 행동 + 신속 행동')})[0].components,('standard','swift'))
    def test_scoped_crafting_default_and_explicit_override(self):
        for raw in ('','2 AP'):
            self.assertEqual(M.resolve_feature_action({'feature_kind':'crafting','frequency':parse_frequency(raw)})[0],'extended')
        self.assertEqual(M.resolve_feature_action({'feature_kind':'crafting','frequency':parse_frequency('항상')})[0],'static')
        self.assertEqual(M.resolve_feature_action({'feature_kind':'crafting','frequency':parse_frequency('임의 - 자유 행동')})[0],'free')
        self.assertIsNone(M.resolve_feature_action({'ingredients':['ore'],'name':'제작'})[0])
    def test_real_saved_compound_header_is_not_single_standard(self):
        effects,header=self.rules.feat_effects('feat/집중-명령')
        self.assertIn('신속',header['frequency']['raw'])
        self.assertEqual(header['frequency']['action'],'standard')
        # Complete raw restores both costs instead of authorizing just the lossy first component.
        self.assertEqual(M.resolve_feature_action(header)[0].components,('standard','swift'))
    def test_saved_static_and_edge_effects_register_without_action_not_full_source_conformance(self):
        e,a,b,rid=self.fixture({'frequency':{'raw':'2 AP - 자유 행동','ap':2,'action':'free'}})
        a.registry=[];a.spec['feats']=['feat/달맞이산-블루스'];a.spec['edges']=['edge/기본-무술','edge/호감인']
        before=copy.deepcopy(a._action_history)
        I.register_feats(e,a)
        for move in ['초음파','바위깨기','초롱초롱눈동자']:self.assertIn(self.rules.move_id(move),a.moves)
        self.assertEqual(a._action_history,before)
        self.assertFalse(any(x.get('type')=='feat_manual' for x in a.registry))
    def test_standard_actual_budget_is_consumed_in_both_callers(self):
        for auto in (False,True):
            e,a,b,rid=self.fixture({'frequency':parse_frequency('2 AP - 기본 행동')},auto)
            a.budget['standard']=1
            self.fire(e,a,b,rid,auto)
            self.assertEqual(b.injuries,1);self.assertEqual(a.spec.get('ap_spent'),2)
            self.assertEqual(a.budget['standard'],0);self.assertEqual(a._action_history,['standard'])
    def test_unknown_and_active_registration_cannot_apply_passives(self):
        for raw in ('','임의 - 기본 행동','임의 - 자유 행동','임의 - 기본 행동 + 신속 행동'):
            with self.subTest(raw=raw):
                e,a,b,rid=self.fixture({'frequency':parse_frequency(raw)},effects=[{'type':'save_mod','value':5}])
                self.assertEqual(a.save_mod,0)
                self.assertTrue(any(x.get('type')=='feat_manual' for x in a.registry))
    def test_static_manual_does_not_create_free_activation(self):
        e,a,b,rid=self.fixture({'frequency':parse_frequency('항상')},effects=[{'type':'gm','choice':'independent static acknowledgement'}])
        e.rule_answer('independent static acknowledgement',{'effects':[{'type':'injury','value':1,'target':'target'}]},'independent')
        before=self.snapshot(e,a,b)
        self.fire(e,a,b,rid,False)
        self.assertEqual(self.snapshot(e,a,b),before)

CASES={
 'missing':{},
 'placeholder':{'frequency':parse_frequency('')},
 'unknown':{'frequency':{'raw':'2 AP - 미해석','ap':2}},
 'conflict':{'frequency':{'raw':'2 AP - 기본 행동','ap':2,'action':'free'}},
 'priority':{'frequency':parse_frequency('2 AP - 기본 행동 + 우선')},
 'compound_cost':{'frequency':parse_frequency('2 AP - 기본 행동 + 신속 행동')},
 'crafting_extended':{'feature_kind':'crafting','frequency':parse_frequency('2 AP')},
 'free':{'frequency':parse_frequency('2 AP - 자유 행동')},
 'standard':{'frequency':parse_frequency('2 AP - 기본 행동')},
 'static':{'frequency':parse_frequency('항상')},
}
for automatic in (False,True):
    for label,header in CASES.items():
        def check(self,automatic=automatic,label=label,header=header):
            e,a,b,rid=self.fixture(header,automatic)
            if label=='standard':F.state(a)  # Existing lazy usage-state materialization is not an activation.
            before=self.snapshot(e,a,b)
            self.fire(e,a,b,rid,automatic)
            if label=='free':
                self.assertEqual(a.spec.get('ap_spent'),2);self.assertEqual(b.injuries,1)
                self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':0});self.assertEqual(a._action_history,['free'])
            else:self.assertEqual(self.snapshot(e,a,b),before)
        setattr(Independent,'test_'+('trigger_' if automatic else 'manual_')+label,check)

if __name__=='__main__':
    class Results(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'ACTION-INDEPENDENT-'+t._testMethodName,'status':'pass'})
        def addFailure(self,t,x):super().addFailure(t,x);self.rows.append({'id':'ACTION-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(x,t)})
        def addError(self,t,x):super().addError(t,x);self.rows.append({'id':'ACTION-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(x,t)})
    r=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
    files=[Path(__file__),ROOT/'tools/mechanize_feats.py',ROOT/'tools/synthetic_rule_fixture.py']+list((ROOT/'engine').glob('*.py'))+list((ROOT/'data').glob('*.json'))+list((ROOT/'output/entities').glob('*.json'))+[ROOT/'output/ruleunits.jsonl',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']+[ROOT/'input'/x for x in ('ch03-skills-edges-feats.md','ch04-trainer-classes.md','ch07-combat.md','supp-errata.md')]
    out={'results':r.rows,'input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'scope':'Independent active-encounter dispatch/registration controls only; fixtures isolate action choice, not actual leaf effects.','semantic_closure':False,'whole_rulebook_complete':False}
    (ROOT/'output/action-metadata-independent-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not r.wasSuccessful())
