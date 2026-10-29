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


class CsvBookComparisonTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        (self.root/'input/db').mkdir(parents=True)
        self.registry=self.root/'registry.json'

    def fixture(self,cells,book,*,columns=None,rows=None,cached=None):
        import csv
        path=self.root/'input/db/class-data.csv'
        rows=rows or [cells];columns=columns or list(range(1,len(cells)+1))
        with path.open('w',encoding='utf-8',newline='') as stream:csv.writer(stream).writerows(rows)
        (self.root/'input/book.md').write_text(book,encoding='utf-8')
        row=dict(id='csv:2',name=cells[0],file='input/db/class-data.csv',csv_record=len(rows),columns=columns,cells=cells,
                 file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),status='incomplete',include_category2=True,dedupe_target=None,
                 potential_md_blocks=cached or [])
        self.registry.write_text(json.dumps({'rows':[row]},ensure_ascii=False),encoding='utf-8')
        return row

    def compare(self):
        from source_locations import compare_csv_book
        return compare_csv_book(self.root,self.registry)

    def test_multiline_logical_rows_parallel_columns_and_independent_filter(self):
        cells=['Alpha','2 AP\nSwift','may not use A/B']
        row=self.fixture(cells,'**Alpha**\n2 AP – Swift\nmay not use A/B\n',
                         rows=[['header','multiline\ntext'],['unrelated','wrong',*cells]],columns=[3,4,5],cached=['input/book.md:1-3'])
        skipped=[dict(row,id='deduped',dedupe_target={'block_id':'input/book.md:1-3'}),dict(row,id='out-of-scope',include_category2=False),dict(row,id='done',status='implemented')]
        self.registry.write_text(json.dumps({'rows':[row,*skipped]}),encoding='utf-8')
        result=self.compare()
        self.assertEqual(result['pending_count'],1)
        # Dash is meaningful: the cells must contain the same action separator.
        self.assertEqual(result['rows'][0]['classification'],'manual_difference_or_unmapped')
        row['cells'][1]='2 AP – Swift'
        self.fixture(row['cells'],'**Alpha**\n2 AP - Swift\nmay not use A/B\n',columns=[3,4,5],rows=[['header','a\nb'],['unrelated','wrong',*row['cells']]],cached=['input/book.md:1-3'])
        self.assertEqual(self.compare()['rows'][0]['classification'],'all_cells_format_match')

    def test_source_sha_saved_cells_and_column_coordinates_fail_closed(self):
        base=self.fixture(['Alpha','2 AP'],'**Alpha**\n2 AP\n',cached=['input/book.md:1-2'])
        for change in ({'file_sha256':'0'*64},{'cells':['Alpha','3 AP']},{'columns':[1,8]},{'csv_record':0}):
            with self.subTest(change=change):
                self.registry.write_text(json.dumps({'rows':[dict(base,**change)]}),encoding='utf-8')
                with self.assertRaises(ValueError):self.compare()

    def test_normalizer_keeps_numbers_signs_negation_conditions_and_or_slash(self):
        from source_locations import normalize_source_text as norm
        import unicodedata
        self.assertEqual(norm('**가**\n» “2 AP” – <span>신속</span>'),norm(unicodedata.normalize('NFD','가 2AP-신속')))
        for left,right in [('2 AP','12 AP'),('2 AP','3 AP'),('2 AP','-2 AP'),('−2','+2'),('-2','2'),('may not use','may use'),('A/B','AB'),('A or B','A and B'),('if owned','if not owned')]:
            with self.subTest(left=left,right=right):
                self.assertNotEqual(norm(left),norm(right))
                self.fixture(['Alpha',left],'**Alpha**\n'+right+'\n',cached=['input/book.md:1-2'])
                self.assertEqual(self.compare()['rows'][0]['classification'],'manual_difference_or_unmapped')

    def test_cached_span_cannot_cross_adjacent_feature_or_parent_heading(self):
        for book,needed in [('**Alpha**\n2 AP\n**Beta**\nextra bonus\n','extra bonus'),
                            ('# Parent\nrequires training\n**Alpha**\n2 AP\n','requires training')]:
            with self.subTest(book=book):
                self.fixture(['Alpha','2 AP',needed],book,cached=['input/book.md:1-4'])
                result=self.compare()['rows'][0]
                self.assertEqual(result['classification'],'manual_difference_or_unmapped')
                self.assertEqual(result['matched_blocks'],[])

    def test_heading_fallback_is_bounded_and_miss_is_not_a_proven_variant(self):
        self.fixture(['Alpha','2 AP'],'# Parent\n**Alpha**\n2 AP\n**Beta**\n3 AP\n')
        result=self.compare()
        self.assertEqual(result['rows'][0]['classification'],'all_cells_named_heading_match')
        self.assertEqual(result['rows'][0]['matched_blocks'],['input/book.md:2-3'])
        self.fixture(['Alpha','2 AP'],'**Alpha**\n'+('unchanged\n'*161)+'2 AP\n')
        result=self.compare()
        self.assertEqual(result['rows'][0]['classification'],'manual_difference_or_unmapped')
        self.assertNotIn('actual_variant',json.dumps(result))

    def test_import_and_stdout_cli_do_not_write_or_adjudicate_completion(self):
        import contextlib,io,runpy
        from unittest.mock import patch
        import source_locations
        self.fixture(['Alpha','2 AP'],'**Alpha**\n2 AP\n')
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        path=Path(source_locations.__file__);code=compile(path.read_bytes(),str(path),'exec')
        with patch('builtins.open',side_effect=AssertionError('import I/O')),patch.object(Path,'read_bytes',side_effect=AssertionError('import I/O')):
            exec(code,{'__name__':'_source_locations_import_probe','__file__':str(path)})
        output=io.StringIO()
        with patch.object(sys,'argv',[str(path),'--compare-csv-book','--root',str(self.root),'--registry',str(self.registry)]),contextlib.redirect_stdout(output):
            runpy.run_path(str(path),run_name='__main__')
        result=json.loads(output.getvalue())
        self.assertEqual(result['kind'],'read_only_csv_book_comparison_not_completion_ledger')
        self.assertNotIn('completed',result)
        with patch.object(sys,'argv',[str(path),'--compare-csv-book','--root',str(self.root),'--registry',str(self.registry),'--output',str(self.root/'input/forbidden.json')]),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):runpy.run_path(str(path),run_name='__main__')
        self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)


if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='PROV-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='PROV-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='PROV-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    paths=[ROOT/x for x in ['tools/test_source_locations.py','tools/source_locations.py','tools/ptk_structure.py','tools/parse_sheets_extra.py','tools/export_ruleunits.py','data/source-location-overrides.json','output/ruleunits.jsonl','output/source-audit/2026-10-10/xlsx-cells.json']]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),results=r.rows,units_path=str(UNIT_PATH),input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/provenance-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
