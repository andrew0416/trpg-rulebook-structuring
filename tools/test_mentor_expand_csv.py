"""CSV64 uses the real Mentor Expand owner, not a second permanent Poke Edge."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_mentor_full as fixture
import mentor as M,state_codec as CODEC,pokemon_party as PARTY
from builder import build_trainer
from ruleset import RuleFilter,RuleSelection,UnresolvedRuleSelection,source_unit


class ExpandCsvTests(unittest.TestCase):
    setUpClass=classmethod(fixture.MentorFullTests.setUpClass.__func__)
    setUp=fixture.MentorFullTests.setUp
    add=fixture.MentorFullTests.add
    acquire=fixture.MentorFullTests.acquire
    pupil=fixture.MentorFullTests.pupil
    reject=fixture.MentorFullTests.reject
    restore=fixture.MentorFullTests.restore

    def expand(self,p,request='csv64',**options):
        return self.e.expand_horizons(self.a,p,request_id=request,seconds=options.pop('seconds',60),
            reason=options.pop('reason','actual CSV64 instruction'),source_id=options.pop('source_id',M.EXPAND_CSV),**options)

    def ready(self):
        self.acquire();self.acquire(M.EXPAND)

    def test_positive_balance_zero_cost_actual_plus_three_and_same_native_receipt(self):
        self.ready();p=self.pupil(tp=7)
        before_edges=deepcopy(p.spec.get('learned_poke_edges',[]))
        result=self.expand(p)
        self.assertEqual((result['point_cost'],result['before'],result['after'],p.spec['tutor_points']),(0,7,10,10))
        self.assertEqual((result['source'],result['input_source']['selected_id']),(M.EXPAND,M.EXPAND_CSV))
        self.assertEqual(result['input_source']['source']['record_span'],[64,64])
        self.assertEqual(self.e.elapsed_seconds,60)
        self.assertEqual(p.spec.get('learned_poke_edges',[]),before_edges)
        self.assertEqual(len(p.spec['mentor_expansion_history']),1)
        state=CODEC.dump_engine(self.e)
        self.assertEqual(self.expand(p),result)
        self.assertEqual(CODEC.dump_engine(self.e),state)
        self.reject(lambda:self.expand(p,'again'),lambda:self.expand(p,'book',source_id=M.EXPAND))

    def test_zero_starting_points_are_allowed_without_payment(self):
        self.ready();p=self.pupil(tp=0);result=self.expand(p)
        self.assertEqual((result['points'],result['point_cost'],p.spec['tutor_points']),(3,0,3))
        self.assertFalse(p.spec.get('state_grants',{}).get('payments',{}))
        book=self.pupil(tp=2);self.expand(book,'book-first',source_id=M.EXPAND)
        self.reject(lambda:self.expand(book,'csv-after-book'))

    def test_actual_parent_and_feature_ownership_target_and_extended_time_are_required(self):
        p=self.pupil(tp=4)
        self.reject(lambda:self.expand(p))
        self.acquire();self.reject(lambda:self.expand(p))
        self.acquire(M.EXPAND);other=self.pupil(tp=4,owned=False)
        self.reject(lambda:self.expand(other),lambda:self.expand(p,seconds=0),
            lambda:self.expand(p,reason=''),lambda:self.expand(p,source_id='poke_edge/not-reviewed'))
        self.assertEqual(p.spec['tutor_points'],4)
        self.assertEqual(self.e.elapsed_seconds,0)

    def test_csv_lifetime_survives_json_and_owner_transfer_and_blocks_book_reuse(self):
        self.ready();p=self.pupil();self.expand(p)
        new=self.add(build_trainer(self.r,'CSV recipient',20,fixture.STATS,abilities=[],extra={
            'classes':[],'feats':[],'skills':dict.fromkeys(M.SKILLS,6)}))
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual roster',roster=[p])
        PARTY.configure(self.e,new,mode='unlimited',reason='actual roster',roster=[])
        PARTY.transfer(self.e,self.a,target=p,new_owner=new,reason='actual gift',request_id='gift')
        actors=self.restore(fresh_rules=True);p=actors[p.entity_id];self.a=actors[new.entity_id]
        self.acquire(request='recipient/class');self.acquire(M.EXPAND,request='recipient/expand')
        self.reject(lambda:self.expand(p,'again'),lambda:self.expand(p,'book',source_id=M.EXPAND))
        self.assertEqual(p.spec['tutor_points'],11)

    def test_each_csv_call_checks_both_real_csv_and_supplemented_book_sources(self):
        self.ready();p=self.pupil(tp=5);read=Path.read_bytes
        for file in ('poke-edges.csv','ch04-trainer-classes.md'):
            def changed(path,file=file):
                raw=read(path)
                return raw+b'\nchanged' if path.name==file else raw
            def stale_call(changed=changed):
                with patch.object(Path,'read_bytes',changed):return self.expand(p)
            with self.subTest(file=file):self.reject(stale_call,pattern='source changed')
        self.assertEqual((p.spec['tutor_points'],self.e.elapsed_seconds),(5,0))

    def test_review_is_exact_identity_not_miscellaneous_or_variant_admission(self):
        units=deepcopy(self.r.selection.units)
        units[M.EXPAND_CSV]['source']['record_span']=[65,65]
        with self.assertRaisesRegex(ValueError,'identity changed'):M.bind_expand_csv_source(self.r,units)
        unknown=source_unit({'id':'poke_edge/unknown-misc','source':{'file':'db/poke-edges.csv'},'group':'기타/홈브류'})
        selection=RuleSelection(RuleFilter({'sources':['core'],'variants':[]},'core'),[unknown])
        with self.assertRaisesRegex(UnresolvedRuleSelection,'unknown_variant_lineage'):selection.resolve(unknown['id'])
        units={key:deepcopy(self.r.selection.units[key]) for key in (M.EXPAND,M.EXPAND_CSV)}
        units[M.EXPAND_CSV]['tags'].append('homebrew')
        M.bind_expand_csv_source(self.r,units)
        selection=RuleSelection(RuleFilter({'sources':['core'],'variants':[]},'core'),units.values())
        with self.assertRaises(ValueError):selection.resolve(M.EXPAND_CSV)

    def test_csv_dependency_retains_explicit_feature_exclusion(self):
        units={key:deepcopy(self.r.selection.units[key]) for key in (M.EXPAND,M.EXPAND_CSV)}
        selection=RuleSelection(RuleFilter({'sources':['core'],'variants':[],
            'exclude_units':[M.EXPAND]},'core'),units.values())
        selection.dependencies[M.EXPAND_CSV]=(M.EXPAND,)
        with self.assertRaises(ValueError):selection.resolve(M.EXPAND_CSV)

    def test_existing_contract_link_conflicts_cannot_change_csv_identity_or_effect(self):
        path=ROOT/'data/mentor-source-contract.json';read=Path.read_text
        data=json.loads(read(path,encoding='utf-8'))
        expected={'id':M.EXPAND_CSV,'file':'db/poke-edges.csv','record_span':[64,64],
            'sha256':'8e4bbb735033db781ca011f98885c1b5fe1b900da75a196b9e6f8734ceff946d',
            'feature':M.EXPAND,'feature_file':'ch04-trainer-classes.md','feature_lines':[627,631],
            'point_cost':0,'points':3,'action':'extended'}
        for key,value in (('point_cost',1),('point_cost',False),('points',4),('action','free'),('sha256','0'*64),('record_span',[65,65])):
            with self.subTest(field=key,value=value):
                changed=deepcopy(data);changed['expand_csv']=dict(expected,**{key:value})
                units=deepcopy(self.r.selection.units);before=deepcopy(units)
                def metadata(current,*args,**kwargs):
                    return json.dumps(changed,ensure_ascii=False) if current==path else read(current,*args,**kwargs)
                with patch.object(Path,'read_text',metadata):
                    with self.assertRaisesRegex(ValueError,'identity changed'):M.bind_expand_csv_source(self.r,units)
                self.assertEqual(units,before)


if __name__=='__main__':unittest.main()
