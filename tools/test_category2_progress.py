"""Reference inputs cannot silently expand or weaken the frozen clause scope."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import report_category2_progress as P


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.freeze_path=P.ROOT/'data/verification/category2-scope-freeze.json'
        self.freeze=json.loads(self.freeze_path.read_text(encoding='utf-8'))

    def changed_freeze(self,change):
        document=deepcopy(self.freeze);change(document)
        read_text=Path.read_text
        def read(path,*args,**kwargs):
            return json.dumps(document) if path==self.freeze_path else read_text(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):return P.collect()

    def test_declared_reference_inputs_keep_original_clause_ids_and_denominator(self):
        result=P.collect()
        self.assertTrue(result['denominator_frozen']);self.assertEqual(result['validation_errors'],[])
        self.assertEqual(result['denominator'],2352)
        self.assertEqual(result['included_clause_ids'],self.freeze['included_clause_ids'])
        self.assertFalse(any(r['counts_for_category2'] for r in self.freeze['reference_only_sources']))

    def test_undeclared_additional_input_still_invalidates_inventory(self):
        result=self.changed_freeze(lambda d:d.pop('reference_only_sources'))
        self.assertIn('Saved input file inventory changed',result['validation_errors'])
        self.assertIsNone(result['completed_clause_count'])

    def test_reference_bytes_are_checked_instead_of_ignored(self):
        result=self.changed_freeze(lambda d:d['reference_only_sources'][0].update(sha256='0'*64))
        self.assertIn('Frozen input changed: '+self.freeze['reference_only_sources'][0]['file'],result['validation_errors'])
        self.assertIsNone(result['denominator'])

    def test_reference_classification_is_explicit(self):
        result=self.changed_freeze(lambda d:d['reference_only_sources'][0].update(counts_for_category2=True))
        self.assertIn('Unclassified reference-only input: '+self.freeze['reference_only_sources'][0]['file'],result['validation_errors'])

    def test_original_source_bytes_are_still_checked(self):
        result=self.changed_freeze(lambda d:d['source_manifest'][0].update(sha256='0'*64))
        self.assertIn('Frozen input changed: '+self.freeze['source_manifest'][0]['file'],result['validation_errors'])
        self.assertIsNone(result['completed_clause_count'])


class EdgeReuseProgressTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((P.ROOT/'data/verification/category2-edge-work-plan.json').read_text(encoding='utf-8'))
        self.audit=self.plan['post_foundation_reuse']['itemized_audit']

    def result(self):
        return P.collect_edge_reuse(plan=self.plan)

    def test_inspection_uses_original_item_ids_and_is_separate_from_implementation(self):
        result=self.result()
        self.assertEqual(len(self.audit['baseline_clause_ids']),95)
        self.assertEqual(result['validation_errors'],[])
        self.assertEqual(result['completed']+result['remaining'],result['denominator'])
        self.assertEqual(result['category2_completion_credit'],0)
        self.assertEqual(P.collect()['denominator'],2352)

    def test_missing_or_duplicate_record_never_shrinks_or_inflates_fixed_denominator(self):
        before=self.result();row=self.audit['items'].pop()
        missing=self.result()
        self.assertEqual(missing['denominator'],before['denominator'])
        self.assertEqual(missing['completed'],before['completed']-1)
        self.assertTrue(missing['validation_errors'])
        self.audit['items'].extend([row,deepcopy(row)])
        repeated=self.result()
        self.assertEqual(repeated['denominator'],before['denominator'])
        self.assertEqual(repeated['completed'],before['completed']-1)
        self.assertTrue(any('Duplicate inspection row' in x for x in repeated['validation_errors']))

    def test_path_presence_and_pending_status_cannot_earn_review_credit(self):
        before=self.result();row=self.audit['items'][0]
        row['entrypoint_reviewed']=False
        self.assertEqual(self.result()['completed'],before['completed']-1)
        row['entrypoint_reviewed']=True;row['status']='verification_needed'
        pending=self.result()
        self.assertEqual(pending['completed'],before['completed']-1)
        self.assertEqual(pending['denominator'],before['denominator'])
        self.assertIn(row['id'],pending['pending_clause_ids'])

    def test_changed_verification_log_cannot_certify_its_consumers(self):
        before=self.result();key=self.audit['items'][0]['route']
        affected=sum(x['route']==key for x in self.audit['items'])
        self.audit['routes'][key]['evidence'][0]['sha256']='0'*64
        changed=self.result()
        self.assertEqual(changed['denominator'],before['denominator'])
        self.assertEqual(changed['completed'],before['completed']-affected)
        self.assertTrue(changed['validation_errors'])

    def test_explicit_success_cases_require_actual_unittest_evidence_and_modules(self):
        from hashlib import sha256
        from tempfile import TemporaryDirectory
        good='test_category2_selected.Tests.test_good'
        bad='test_category2_failed.Tests.test_bad'
        spoof='test_category2_traceback.Tests.test_spoof'
        headers=f'test_good ({good}) ... ok\ntest_bad ({bad}) ... FAIL\n'
        diagnostic='\n'+'='*70+'\nFAIL: '+bad+'\nTraceback (most recent call last):\n'+f'test_spoof ({spoof}) ... ok\n'
        summary='\n'+'-'*70+'\nRan 2 tests in 0.001s\n\nFAILED (failures=1)\n'
        mixed=headers+diagnostic+summary
        subheaders=f'test_good ({good}) ... ok\ntest_bad ({bad}) ... \n'
        subheaders+=''.join(f'  test_bad ({bad}) (value={value}) ... ERROR\n' for value in (1,2))
        submixed=subheaders+diagnostic+summary.replace('failures=1','errors=2')
        repeated=subheaders+f'test_bad ({bad}) ... ERROR\n'+diagnostic+summary.replace('failures=1','errors=3')
        noncontiguous=subheaders+f'test_spoof ({spoof}) ... ok\ntest_bad ({bad}) ... ERROR\n'+diagnostic+summary.replace('Ran 2','Ran 3').replace('failures=1','errors=3')
        legacy=f'test_good ({good}) ... ok\n\n'+('-'*70)+'\nRan 1 test in 0.001s\n\nOK\n'
        footer='UTC end 2026-10-20T00:01:02.123456+00:00\n'
        table=[
            ('mixed success',mixed,[good],'test_category2_selected',True),
            ('failed subcases other success',submixed,[good],'test_category2_selected',True),
            ('failed subcase parent',submixed,[bad],'test_category2_failed',False),
            ('subcase then parent error keeps other success',repeated,[good],'test_category2_selected',True),
            ('subcase then parent error cannot pass parent',repeated,[bad],'test_category2_failed',False),
            ('subcase parent error count preserved',repeated.replace('errors=3','errors=2'),[good],'test_category2_selected',False),
            ('subcase parent forged whole success',repeated.replace('FAILED (errors=3)','OK'),[good],'test_category2_selected',False),
            ('noncontiguous repeated parent',noncontiguous,[good],'test_category2_selected',False),
            ('repeated ordinary error',mixed.replace(headers,headers+f'test_bad ({bad}) ... ERROR\n').replace('Ran 2','Ran 3').replace('failures=1','failures=1, errors=1'),[good],'test_category2_selected',False),
            ('forged subcase error count',submixed.replace('errors=2','errors=1'),[good],'test_category2_selected',False),
            ('foreign subcase parent',submixed.replace(f'  test_bad ({bad})',f'  test_spoof ({spoof})'),[good],'test_category2_selected',False),
            ('normalized full ID',mixed,['tools.'+good],'tools.test_category2_selected',True),
            ('valid UTC mixed',mixed+footer,[good],'test_category2_selected',True),
            ('legacy whole OK',legacy,None,'test_category2_selected',True),
            ('legacy repeated successful invocation',legacy.replace(f'test_good ({good}) ... ok\n',f'test_good ({good}) ... ok\ntest_good ({good}) ... ok\n').replace('Ran 1','Ran 2'),None,'test_category2_selected',True),
            ('legacy UTC OK',legacy+footer,None,'test_category2_selected',True),
            ('no scope keeps whole OK',mixed,None,'test_category2_selected',False),
            ('failed case',mixed,[bad],'test_category2_failed',False),
            ('failed module text',mixed,[good],'test_category2_failed',False),
            ('traceback header',mixed,[spoof],'test_category2_traceback',False),
            ('traceback module',mixed,[good],'test_category2_traceback',False),
            ('missing ID',mixed,[good+'x'],'test_category2_selected',False),
            ('duplicate requested ID',mixed,[good,good],'test_category2_selected',False),
            ('normalized duplicate ID',mixed,[good,'tools.'+good],'test_category2_selected',False),
            ('empty cases',mixed,[],'test_category2_selected',False),
            ('wrong case container',mixed,good,'test_category2_selected',False),
            ('duplicate actual header',mixed.replace(headers,headers+headers.splitlines(True)[0]).replace('Ran 2','Ran 3'),[good],'test_category2_selected',False),
            ('wrong Ran count',mixed.replace('Ran 2','Ran 3'),[good],'test_category2_selected',False),
            ('wrong final outcomes',mixed.replace('failures=1','errors=1'),[good],'test_category2_selected',False),
            ('forged whole success',mixed.replace('FAILED (failures=1)','OK'),[good],'test_category2_selected',False),
            ('mismatched header method',mixed.replace('test_good (','test_other ('),[good],'test_category2_selected',False),
            ('unscoped successful module',legacy.replace('Ran 1','Ran 2').replace('\n\n'+'-'*70,f'\ntest_spoof ({spoof}) ... ok\n\n'+('-'*70)),[good],'test_category2_traceback',False),
            ('changed raw hash',mixed,[good],'test_category2_selected',False),
            ('arbitrary tail',mixed+'arbitrary tail\n',[good],'test_category2_selected',False),
            ('non UTC offset',mixed+footer.replace('+00:00','+09:00'),[good],'test_category2_selected',False),
            ('invalid UTC date',mixed+footer.replace('-10-20T','-99-20T'),[good],'test_category2_selected',False),
            ('duplicate UTC footer',mixed+footer+footer,[good],'test_category2_selected',False),
        ]
        with TemporaryDirectory() as directory:
            root=Path(directory);log=root/'evidence.log'
            for label,body,cases,module,accepted in table:
                with self.subTest(label=label):
                    raw=body.encode();log.write_bytes(raw)
                    proof={'log':'evidence.log','sha256':sha256(raw).hexdigest()}
                    if cases is not None:proof['cases']=cases
                    if label=='changed raw hash':proof['sha256']='0'*64
                    audit={'baseline_clause_ids':['original-clause'],'added_clause_ids':[],
                           'baseline_sha256':sha256(b'original-clause').hexdigest(),'scope':'fixture',
                           'items':[{'id':'original-clause','route':'native','status':'verified','entrypoint_reviewed':True}],
                           'routes':{'native':{'native_paths':['actual consumer'],'foundation_ids':['owner'],'required_test_modules':[module],'evidence':[proof]}}}
                    plan={'post_foundation_reuse':{'itemized_audit':audit},'foundation_discovery':{'foundation_execution_plan':{'units':[{'id':'owner'}]}}}
                    result=P.collect_edge_reuse(root,plan)
                    self.assertEqual(result['completed'],int(accepted))
                    self.assertEqual(bool(result['validation_errors']),not accepted)


if __name__=='__main__':unittest.main()
