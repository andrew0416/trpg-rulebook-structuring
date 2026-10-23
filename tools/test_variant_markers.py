"""Variant admission uses structured source markers; this is not effect certification."""
import copy,csv,hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from ruleset import RuleFilter,RuleSelection,classify,source_unit,ExcludedRuleSelection,UnresolvedRuleSelection
from engine import Rules,Engine,Combatant

class VariantMarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records=json.loads((ROOT/'output/entities/abilities.json').read_text(encoding='utf-8'))
        cls.units={u['id']:u for u in map(json.loads,(ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines())}
        with (ROOT/'input/db/abilities.csv').open(encoding='utf-8',newline='') as f:cls.csv=list(csv.reader(f))
    def unit(self,**kw):return dict(id='ability/audit',name='plain name',_source={'file':'db/abilities.csv'},**kw)
    def test_dated_keyword_is_not_core(self):
        for keyword in ['2-16 Playtest','9-15 Playtest','Playtest','플레이테스트']:
            with self.subTest(keyword=keyword):
                u=self.unit(keyword=keyword)
                self.assertEqual(classify(u),('core','playtest'))
                self.assertEqual(RuleFilter({'variants':[]}).decision(u),{'status':'excluded','reason':'variant:playtest'})
    def test_mechanized_header_retains_marker(self):
        u=self.unit(mech={'data':{'header':{'keyword':'2-16 Playtest'}}})
        self.assertEqual(classify(source_unit(source_unit(u))),('core','playtest'))
    def test_direct_header_retains_marker(self):
        self.assertEqual(classify(self.unit(header={'keyword':'썬문(SuMo)'})),('core','썬문'))
    def test_normalization_is_idempotent(self):
        u=self.unit(keyword='2-16 Playtest')
        self.assertEqual(source_unit(u),source_unit(source_unit(u)))
    def test_rule_text_and_english_name_do_not_invent_variant(self):
        u=self.unit(effect='Discuss Playtest rules',eng='Sturdy [Playtest]',keyword='면역')
        self.assertEqual(classify(u),('core',None))
    def test_unrelated_keyword_is_not_variant(self):
        for keyword in [None,'마지막기회','면역','not Playtest','']:self.assertEqual(classify(self.unit(keyword=keyword)),('core',None))
    def test_known_keyword_variants(self):
        for keyword,expected in [('홈브류','홈브류'),('썬문(SuMo)','썬문'),('소실(SwSh)','소실')]:
            self.assertEqual(classify(self.unit(keyword=keyword)),('core',expected))
    def test_conflicting_markers_are_unresolved_even_under_all(self):
        u=self.unit(keyword='2-16 Playtest');u['name']='mixed [홈브류]'
        self.assertEqual(RuleFilter({}).decision(u)['status'],'unresolved')
        with self.assertRaises(UnresolvedRuleSelection):RuleSelection(RuleFilter({}),[u]).resolve(u['id'])
    def test_matching_markers_do_not_duplicate_variant(self):
        u=self.unit(keyword='2-16 Playtest');u['name']='plain [Playtest]'
        self.assertEqual(classify(u),('core','playtest'))
    def test_explicit_exclusion_precedes_marker_conflict(self):
        u=self.unit(keyword='2-16 Playtest');u['name']='mixed [홈브류]'
        self.assertEqual(RuleFilter({'exclude_units':[u['id']]}).decision(u)['reason'],'exclude_units')
    def test_all_saved_keyword_rows_match_csv_and_ruleunit_admission(self):
        count=0
        for record in self.records:
            start,end=record['_source']['record_span'];row=self.csv[start-1]
            self.assertEqual(start,end)
            self.assertEqual(row[0],record['name'])
            keyword=row[5]
            if keyword not in ['2-16 Playtest','9-15 Playtest']:continue
            count+=1
            with self.subTest(uid=record['id']):
                self.assertEqual(classify(record)[1],'playtest')
                self.assertEqual(classify(self.units[record['id']])[1],'playtest')
                self.assertEqual(RuleFilter({'variants':[]}).decision(record)['status'],'excluded')
                self.assertEqual(RuleFilter({'variants':['playtest']}).decision(record)['status'],'allowed')
        self.assertEqual(count,208)
    def test_runtime_core_cannot_admit_unnamed_playtest(self):
        r=Rules(str(ROOT),ruleset='core')
        for uid in ['ability/가시','ability/햇살베일','ability/타입오라']:
            with self.subTest(uid=uid):
                with self.assertRaises(ExcludedRuleSelection):r.selection.require_supported_version(uid)
    def test_runtime_playtest_allows_explicit_unnamed_identity(self):
        r=Rules(str(ROOT),ruleset='playtest')
        self.assertEqual(r.selection.resolve('ability/햇살베일'),'ability/햇살베일')
        with self.assertRaises(UnresolvedRuleSelection):r.selection.resolve_name('햇살베일',('ability/',))
    def test_core_registration_cannot_apply_excluded_keyword_effect(self):
        r=Rules(str(ROOT),ruleset='core');e=Engine(r)
        c=Combatant(r,dict(name='audit',kind='trainer',level=1,stats={x:10 for x in ['hp','atk','def','spa','spd','spe']},types=[],moves=[],abilities=[]))
        before=(c.evasion_mod,copy.deepcopy(c.registry))
        e.register_abilities_one(c,'햇살베일')
        self.assertEqual((c.evasion_mod,c.registry),before)

    def source_records(self, filename):
        return json.loads((ROOT/'output/entities'/filename).read_text(encoding='utf-8'))
    def test_actual_feat_sheet_date_tags_are_preserved(self):
        records=self.source_records('feat_sheet.json')
        selected=[x for x in records if x['_source']['record_span'][0] in [328,361]]
        self.assertEqual(len(selected),2)
        with (ROOT/'input/db/feats.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.reader(f))
        for record in selected:
            self.assertEqual(record['tags'],rows[record['_source']['record_span'][0]-1][1])
            self.assertEqual(classify(source_unit(source_unit(record)))[1],'playtest')
            self.assertEqual(RuleFilter({'variants':[]}).decision(record)['status'],'excluded')
    def test_actual_homebrew_playtest_tags_remain_unresolved(self):
        selected=[x for x in self.source_records('feat_sheet.json') if x['_source']['record_span'][0] in [738,740,741,742,743]]
        self.assertEqual(len(selected),5)
        for record in selected:
            self.assertEqual(RuleFilter({}).decision(record)['status'],'unresolved')
    def test_ruleunit_source_tags_are_not_hidden_by_layer_tags(self):
        unit=self.unit(tags=['feat','C'],mech={'data':{'tags':'[9-15 Playtest]'}})
        self.assertEqual(classify(unit)[1],'playtest')
        self.assertEqual(source_unit(unit),source_unit(source_unit(unit)))
    def test_actual_dated_edge_name_is_not_core(self):
        selected=[x for x in self.source_records('edge_sheet.json') if x['_source']['record_span'][0]==83]
        self.assertEqual(len(selected),1)
        with (ROOT/'input/db/edges.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.reader(f))
        self.assertEqual(selected[0]['name'],rows[82][0])
        self.assertEqual(classify(selected[0])[1],'playtest')
        self.assertEqual(RuleFilter({'variants':[]}).decision(selected[0])['status'],'excluded')
    def test_mixed_source_group_is_preserved_and_unresolved(self):
        records=self.source_records('poke_edge.json')
        with (ROOT/'input/db/poke-edges.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.reader(f))
        self.assertEqual(rows[62][1],'기타/홈브류')
        for record in records:
            if record['_source']['record_span'][0] not in [64,65]:continue
            for unit in [record,self.units[record['id']]]:
                self.assertEqual(source_unit(unit)['source_group'],'기타/홈브류')
                self.assertEqual(source_unit(unit),source_unit(source_unit(unit)))
                self.assertEqual(RuleFilter({}).decision(unit),{'status':'unresolved','reason':'unknown_variant_lineage:기타/홈브류'})
    def test_runtime_mixed_group_is_held_even_when_all_variants_allowed(self):
        for profile in ['core','all']:
            rules=Rules(str(ROOT),ruleset=profile)
            for uid in ['poke_edge/시야-넓히기','poke_edge/쌍두스위퍼']:
                with self.assertRaises(UnresolvedRuleSelection):rules.selection.resolve(uid)
    def test_actual_locale_conflict_is_not_silently_accepted(self):
        record=next(x for x in self.records if x['id']=='ability/옹골참-홈브류-2')
        row=self.csv[491]
        self.assertEqual((record['name'],record['keyword'],record['eng']),(row[0],row[5],row[7]))
        self.assertEqual(record['eng'],'Sturdy [Playtest]')
        self.assertEqual(source_unit(record)['eng'],record['eng'])
        self.assertEqual(RuleFilter({}).decision(record)['status'],'unresolved')
        with self.assertRaises(UnresolvedRuleSelection):Rules(str(ROOT),ruleset='all').selection.resolve(record['id'])
    def test_nonconflicting_locale_markers_do_not_change_admission(self):
        for uid in ['ability/터보블레이즈-playtest','ability/질풍날개-썬문','ability/마이너스-소실']:
            record=next(x for x in self.records if x['id']==uid)
            self.assertEqual(RuleFilter({}).decision(record)['status'],'allowed')
    def test_raw_sheet_identity_is_not_conflated_with_errata_feat(self):
        rules=Rules(str(ROOT),ruleset='core')
        for name in ['고통-테크닉','캡슐-과학']:
            with self.assertRaises(UnresolvedRuleSelection):rules.selection.resolve('feat_sheet/'+name)
            with self.assertRaises(ExcludedRuleSelection):rules.selection.resolve('feat/'+name)
    def test_effect_prose_and_unrelated_group_do_not_classify(self):
        unit=self.unit(effect='[9-15 Playtest]',group='연구 분야')
        self.assertEqual(classify(unit),('core',None))
        self.assertEqual(RuleFilter({}).decision(unit)['status'],'allowed')

    def test_explicit_member_marker_resolves_mixed_group_category(self):
        records=self.source_records('poke_edge.json')
        with (ROOT/'input/db/poke-edges.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.reader(f))
        selected=[x for x in records if x['_source']['record_span'][0] in [67,68,69,70]]
        self.assertEqual(len(selected),4)
        rules=Rules(str(ROOT),ruleset='all')
        for record in selected:
            self.assertEqual(record['name'],rows[record['_source']['record_span'][0]-1][0])
            self.assertIn('[홈브류]',record['name'])
            self.assertEqual(record['group'],'기타/홈브류')
            self.assertEqual(RuleFilter({}).decision(record)['status'],'allowed')
            self.assertEqual(RuleFilter({'variants':[]}).decision(record)['reason'],'variant:홈브류')
            self.assertEqual(rules.selection.resolve(record['id']),record['id'])

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='VARIANT-MARKER-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='VARIANT-MARKER-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='VARIANT-MARKER-'+t._testMethodName,status='error'))
        def addSubTest(self,t,st,e):
            super().addSubTest(t,st,e)
            if e:self.rows.append(dict(id='VARIANT-MARKER-'+t._testMethodName+str(st),status='fail'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(VariantMarkerTests))
    paths=['tools/test_variant_markers.py','engine/ruleset.py','engine/engine.py','data/rulesets.json','input/db/abilities.csv','output/entities/abilities.json','output/ruleunits.jsonl']
    paths += ['input/db/feats.csv','input/db/edges.csv','input/db/poke-edges.csv','output/entities/feat_sheet.json','output/entities/edge_sheet.json','output/entities/poke_edge.json','data/verification/variant-marker-audit.json']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Explicit keyword/name/tag markers, locale conflicts, and mixed source-group admission; no whole rule certification.',whole_rule_certified=False,csv_playtest_keyword_records=208,results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/variant-marker-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
