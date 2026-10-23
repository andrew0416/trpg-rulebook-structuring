from pathlib import Path
import sys, unittest, json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import rule_blueprints as B

class Tests(unittest.TestCase):
    def sample(self):
        return {'schema':'rule-blueprint-v1','id':'example','family':'grant',
                'source_text':'example source','qualitative_reason':'source-owned grant',
                'contract':{a:{'state':'deferred','requires':['review']} for a in B.AXES},
                'requirements':{'review':{'kind':'contract_review','question':'Which contract?',
                                         'resume_when':'Source and native consumer agree'}}}
    def test_deferred_roundtrip_does_not_become_resolved(self):
        value=json.loads(json.dumps(self.sample()))
        self.assertEqual(len(B.pending(value)),1)
        with self.assertRaises(ValueError):B.resolved_contract(value)
    def test_resolve_is_atomic_and_does_not_change_original(self):
        value=self.sample()
        with self.assertRaises(ValueError):B.resolve(value,'review',{'effect':{'state':'bound','value':0,'evidence':'source'}})
        self.assertEqual(len(B.pending(value)),1)
        fixed=B.resolve(value,'review',{a:{'state':'bound','value':False if a=='exception' else 0,'evidence':'explicit source'} for a in B.AXES})
        self.assertFalse(B.pending(fixed));self.assertEqual(len(B.pending(value)),1)
        result=B.resolved_contract(fixed);result['effect']['value']=5
        self.assertEqual(fixed['contract']['effect']['value'],0)
    def test_unknown_is_not_not_applicable(self):
        value=self.sample();value['contract']['effect']={'state':'not_applicable'}
        with self.assertRaises(ValueError):B.validate(value)
    def test_dangling_and_unused_dependencies_rejected(self):
        value=self.sample();value['contract']['effect']['requires']=['missing']
        with self.assertRaises(ValueError):B.validate(value)
        value=self.sample();value['requirements']['unused']=dict(value['requirements']['review'])
        with self.assertRaises(ValueError):B.validate(value)
    def test_shared_dependency_index_and_conflict(self):
        a=self.sample();b=self.sample();b['id']='other'
        self.assertEqual(B.dependency_index([a,b])['review']['clauses'],['example','other'])
        b['requirements']['review']['question']='different'
        with self.assertRaises(ValueError):B.dependency_index([a,b])
        with self.assertRaises(ValueError):B.dependency_index([a,a])
    def test_resolving_contract_cannot_erase_source_conflict(self):
        a=self.sample()
        a['requirements']['source']={'kind':'source_decision','question':'Which edition?', 'resume_when':'Explicit edition choice'}
        a['contract']['source_policy']['requires'].append('source')
        replacements={axis:{'state':'not_applicable','evidence':'scope checked'} for axis in B.AXES}
        with self.assertRaises(ValueError):B.resolve(a,'review',replacements)
        replacements['source_policy']={'state':'deferred','requires':['source']}
        b=B.resolve(a,'review',replacements)
        self.assertEqual(set(B.pending(b)),{'source'})
        with self.assertRaises(ValueError):B.resolved_contract(b)
    def test_none_and_nonfinite_are_not_concrete(self):
        for v in (None,float('nan')):
            a=self.sample();a['contract']['effect']={'state':'bound','value':v,'evidence':'source'}
            with self.assertRaises(ValueError):B.validate(a)

if __name__=='__main__':unittest.main()
