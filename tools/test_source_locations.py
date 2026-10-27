"""Coordinates must resolve to original workbook records, including duplicate names."""
import copy,json,hashlib,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
from source_locations import validate_record,SHEETS
UNIT_PATH=Path(sys.argv[1]) if __name__=='__main__' and len(sys.argv)>1 else ROOT/'output/ruleunits.jsonl'
class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache={}
        cls.units=[json.loads(l) for l in UNIT_PATH.read_text(encoding='utf-8').splitlines()]
        cls.book=json.loads((ROOT/'output/source-audit/2026-10-10/xlsx-cells.json').read_text(encoding='utf-8'))
    def test_all_sheet_entity_records_have_original_coordinates(self):
        failures=[];checked=0
        for u in self.units:
            src=u['source']
            if src['file'].startswith('db/') or src['file']=='.md':
                if u['kind'] not in ['entity:move','entity:ability','entity:species','entity:item','entity:recipe','entity:technique','entity:feat','entity:poke_edge','definition:field','table']:continue
                checked+=1
                errors=validate_record(ROOT,src,u['title'],self.cache)
                if errors:failures.append((u['id'],errors));continue
                row=self.book[src['sheet']]['rows'][src['record_span'][0]-1]
                if 'name' in src['columns'] and str(row[src['columns']['name']-1]).strip()!=u['title'].strip():
                    failures.append((u['id'],'original_name_mismatch'))
        self.assertGreaterEqual(checked,4030)
        self.assertEqual(failures,[])
    def test_no_unresolvable_or_zero_markdown_locations(self):
        errors=[]
        for u in self.units:
            refs=[u['source']]+u['source'].get('related',[])
            for src in refs:
                file=src['file']
                if file.startswith('db/'):
                    if validate_record(ROOT,src,cache=self.cache):errors.append((u['id'],file))
                elif file.endswith('.md'):
                    p=ROOT/'input'/file;span=src.get('lines',[])
                    if not p.is_file() or len(span)!=2 or not 1<=span[0]<=span[1]<=len(p.read_text(encoding='utf-8').splitlines()):errors.append((u['id'],file))
                elif not (ROOT/file).is_file():errors.append((u['id'],file))
        self.assertEqual(errors,[])
    def test_shifted_row_wrong_sheet_and_invalid_columns_rejected(self):
        source=next(u['source'] for u in self.units if u['id']=='item/용의플레이트')
        self.assertEqual(validate_record(ROOT,source,'용의플레이트'),[])
        for change in [dict(record_span=[160,160]),dict(sheet='특성 데이터'),dict(columns={'name':999}),dict(record_span=[0,0])]:
            wrong=dict(source,**change);self.assertTrue(validate_record(ROOT,wrong,'용의플레이트'),change)
    def test_logical_record_is_not_multiline_csv_physical_line(self):
        source=next(u['source'] for u in self.units if u['id']=='move/저주')
        self.assertEqual(source['columns']['effect'],8)
        row=source['record_span'][0]
        cells=self.book['기술 목록']['cells']
        self.assertEqual(cells[f'A{row}'].strip(),'저주')
        self.assertIn('고스트',cells[f'H{row}'])
    def test_same_name_poke_edges_retain_distinct_rows(self):
        found=[u for u in self.units if u['id'].startswith('poke_edge/스킬-향상')]
        self.assertEqual(len(found),18)
        self.assertEqual(len({tuple(u['source']['record_span']) for u in found}),18)
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='PROV-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='PROV-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='PROV-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProvenanceTests))
    paths=[ROOT/x for x in ['tools/test_source_locations.py','tools/source_locations.py','tools/ptk_structure.py','tools/parse_sheets_extra.py','tools/export_ruleunits.py','data/source-location-overrides.json','output/ruleunits.jsonl','output/source-audit/2026-10-10/xlsx-cells.json']]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),results=r.rows,units_path=str(UNIT_PATH),input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/provenance-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
