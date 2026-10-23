"""Generic resolution boundary examples without PTU state or terminology."""
from copy import deepcopy
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
from resolution_transaction import resolve_transaction

class ResolutionTransactionTests(unittest.TestCase):
    def test_rejected_resolution_preserves_all_subjects_and_rng(self):
        actor = SimpleNamespace(resources={'effort': 3}, conditions=[])
        other = SimpleNamespace(resources={'effort': 1}, conditions=[])
        rng = random.Random(7)
        before = deepcopy([vars(actor), vars(other)]), rng.getstate()
        def reject(subjects, staged_rng):
            subjects[0].resources['effort'] -= 2
            subjects[1].conditions.append('distracted')
            staged_rng.randint(1, 20)
            raise ValueError('invalid declaration')
        with self.assertRaises(ValueError):
            resolve_transaction([actor, other], rng, reject)
        self.assertEqual((deepcopy([vars(actor), vars(other)]), rng.getstate()), before)

    def test_valid_failed_check_commits_cost_rng_and_returned_events(self):
        actor = SimpleNamespace(resources={'effort': 3}, conditions=[])
        rng = random.Random(7)
        reference = random.Random(7)
        roll = reference.randint(1, 20)
        original_resources = actor.resources
        def resolve(subjects, staged_rng):
            subjects[0].resources['effort'] -= 1
            result = staged_rng.randint(1, 20)
            return {'success': False, 'roll': result, 'events': ['effort spent']}
        result = resolve_transaction([actor], rng, resolve)
        self.assertEqual(result, {'success': False, 'roll': roll, 'events': ['effort spent']})
        self.assertEqual(actor.resources['effort'], 2)
        self.assertIs(actor.resources, original_resources)
        self.assertEqual(rng.getstate(), reference.getstate())

    def test_shared_subject_identity_is_preserved_in_staging(self):
        actor = SimpleNamespace(value=1)
        def resolve(subjects, rng):
            self.assertIs(subjects[0], subjects[1])
            subjects[0].value += 1
        resolve_transaction([actor, actor], random.Random(7), resolve)
        self.assertEqual(actor.value, 2)

    def test_commit_preserves_nested_aliases_cycles_and_returned_subjects(self):
        shared={'ledger':[1]};shared['self']=shared
        first=SimpleNamespace(shared=shared)
        second=SimpleNamespace(shared=shared,peer=first)
        first.peer=second
        ledger=shared['ledger']
        def apply(subjects,rng):
            a,b=subjects
            self.assertIs(a.peer,b);self.assertIs(b.peer,a)
            a.shared['ledger'].append(2)
            return {'actor':a,'other':b,'shared':a.shared,'ledger':a.shared['ledger']}
        result=resolve_transaction([first,second],random.Random(3),apply)
        self.assertIs(first.peer,second);self.assertIs(second.peer,first)
        self.assertIs(first.shared,shared);self.assertIs(second.shared,shared)
        self.assertIs(shared['self'],shared);self.assertIs(shared['ledger'],ledger)
        self.assertEqual(ledger,[1,2])
        self.assertIs(result['actor'],first);self.assertIs(result['other'],second)
        self.assertIs(result['shared'],shared);self.assertIs(result['ledger'],ledger)

    def test_failed_resolution_keeps_nested_shared_graph_untouched(self):
        shared={'ledger':[1]};first=SimpleNamespace(shared=shared);second=SimpleNamespace(shared=shared)
        rng=random.Random(4);state=rng.getstate()
        def reject(subjects,staged_rng):
            subjects[0].shared['ledger'].append(2)
            subjects[1].new_field='partial'
            staged_rng.random()
            raise ValueError('unresolved')
        with self.assertRaises(ValueError):resolve_transaction([first,second],rng,reject)
        self.assertIs(first.shared,second.shared);self.assertIs(first.shared,shared)
        self.assertEqual(shared,{'ledger':[1]});self.assertFalse(hasattr(second,'new_field'))
        self.assertEqual(rng.getstate(),state)

    def test_replacing_one_shared_field_splits_without_overwriting_survivor(self):
        for reverse in (False,True):
            with self.subTest(reverse=reverse):
                shared={'value':1};a=SimpleNamespace(shared=shared);b=SimpleNamespace(shared=shared)
                def apply(subjects,rng):
                    first,second=subjects[::-1] if reverse else subjects
                    first.shared={'value':2};second.shared['value']=3
                    return first.shared,second.shared
                result=resolve_transaction([b,a] if reverse else [a,b],random.Random(3),apply)
                self.assertEqual(a.shared,{'value':2});self.assertEqual(b.shared,{'value':3})
                self.assertIs(b.shared,shared);self.assertIsNot(a.shared,shared)
                self.assertIs(result[0],a.shared);self.assertIs(result[1],b.shared)

    def test_merging_replacement_and_deleting_alias_preserves_intended_graph(self):
        a=SimpleNamespace(shared={'value':1},obsolete=[1]);b=SimpleNamespace(shared={'value':2})
        original=a.shared
        def apply(subjects,rng):
            first,second=subjects
            first.shared={'value':4};second.shared=first.shared
            del first.obsolete
            return first.shared
        result=resolve_transaction([a,b],random.Random(3),apply)
        self.assertIs(a.shared,b.shared);self.assertIs(result,a.shared)
        self.assertIs(a.shared,original);self.assertFalse(hasattr(a,'obsolete'))
        self.assertEqual(a.shared,{'value':4})

    def test_rng_only_resolution_preserves_borrowed_live_references(self):
        actor=SimpleNamespace(name='live observer')
        event={'actor':actor}
        rng=random.Random(3)
        def resolve(subjects,staged_rng):
            staged_rng.random()
            return event
        result=resolve_transaction([],rng,resolve)
        self.assertIs(result,event)
        self.assertIs(result['actor'],actor)

    def test_rng_only_custom_rng_preserves_borrowed_live_references(self):
        actor=SimpleNamespace(name='live observer')
        event={'actor':actor};rng=SimpleNamespace(faces=[3,4]);faces=rng.faces
        def resolve(subjects,staged_rng):
            self.assertEqual(staged_rng.faces.pop(0),3)
            return event
        result=resolve_transaction([],rng,resolve)
        self.assertIs(result,event);self.assertIs(result['actor'],actor)
        self.assertIs(rng.faces,faces);self.assertEqual(faces,[4])

class RequestIntentTests(unittest.TestCase):
    def test_pending_and_completed_record_share_canonical_intent(self):
        from resolution_transaction import bind_request_intent
        record={'status':'pending','completed_steps':['cost']}
        first=bind_request_intent(record,{'target':'entity/a','amount':2})
        record['status']='completed';record['completed_steps'].append('effect')
        self.assertEqual(bind_request_intent(record,{'amount':2,'target':'entity/a'}),first)
        before=deepcopy(record)
        with self.assertRaisesRegex(ValueError,'changed input'):
            bind_request_intent(record,{'amount':3,'target':'entity/a'})
        self.assertEqual(record,before)

    def test_invalid_intent_cannot_partially_bind_a_record(self):
        from resolution_transaction import bind_request_intent
        record={'status':'pending'}
        with self.assertRaises((ValueError,TypeError)):
            bind_request_intent(record,{'callback':lambda:None})
        self.assertEqual(record,{'status':'pending'})

if __name__ == '__main__':
    unittest.main(verbosity=2)

