"""Native medicine receipt joins, independent legacy witnesses and atomic refusal."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_authority_candidate01_probes as PROBE
from engine import Rules,Engine
import class_actor_state_actions as C
import consumption_execution as STOCK
import action_points as AP
import state_codec as CODEC


class MedicineReceiptBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.all_rules=Rules(ROOT,ruleset='all')
    engine=PROBE.Candidate01Probes.engine
    trainer=PROBE.Candidate01Probes.trainer
    medical_fixture=PROBE.Candidate01Probes.medical_fixture
    restored=PROBE.Candidate01Probes.restored

    def event_node(self,saved,event_id):
        nodes=[n for n in saved['nodes'].values() if n['kind']=='dict'
               and ['id',event_id] in n['items'] and ['source',C.MEDICAL_TECHNIQUE] in n['items']]
        self.assertEqual(len(nodes),1)
        return nodes[0]

    def payload_node(self,saved,event_id):
        ref=next(v for k,v in self.event_node(saved,event_id)['items'] if k=='payload')
        return saved['nodes'][ref['$ref']]

    def old_format(self,saved,event_id):
        payload=self.payload_node(saved,event_id)
        self.assertEqual(sum(k=='payment_id' for k,v in payload['items']),1)
        payload['items']=[pair for pair in payload['items'] if pair[0]!='payment_id']

    def test_legacy_unique_independent_witness_restores_without_mutation_or_retarget(self):
        e,owner,patient,other,event_id,saved=self.medical_fixture()
        self.old_format(saved,event_id)
        restored,a,p,q=self.restored(e.r,saved,owner,patient,other)
        event=next(x for x in a.spec[C.STATE]['events'] if x['id']==event_id)
        self.assertNotIn('payment_id',event['payload'],'legacy validation is read-only')
        before=(p.hp,q.hp,AP.available(a))
        self.assertTrue(restored.resolve_class_actor_state_action(a,event_id,use=True)['used'])
        self.assertGreater(p.hp,before[0]);self.assertEqual(q.hp,before[1])
        self.assertEqual(AP.available(a),before[2]-1)
        altered=deepcopy(saved)
        next(pair for pair in self.event_node(altered,event_id)['items'] if pair[0]=='target_id')[1]=other.entity_id
        with self.assertRaises(CODEC.StateCodecError):Engine.import_state(e.r,altered)

    def two_payments(self):
        e,a,p,q,first,_=self.medical_fixture()
        e.resolve_class_actor_state_action(a,first,use=False)
        e.end_encounter()
        a.spec['items']['상처약']=1
        e.use_item(a,'상처약',q)
        events=[x for x in a.spec[C.STATE]['events'] if x['source']==C.MEDICAL_TECHNIQUE]
        self.assertEqual(len(events),2)
        self.assertEqual(events[0]['at'],events[1]['at'],'native immediate uses retain the same known clock')
        self.assertEqual(events[0]['payload']['native_result'],events[1]['payload']['native_result'])
        self.assertEqual([x['target_id'] for x in events],[p.entity_id,q.entity_id])
        self.assertNotEqual(events[0]['payload']['payment_id'],events[1]['payload']['payment_id'])
        return e,a,p,q,first,events[1]['id'],json.loads(json.dumps(e.export_state(),ensure_ascii=False))

    def test_two_actual_payments_bind_distinct_patients_and_ambiguous_legacy_is_held(self):
        e,a,p,q,first,second,saved=self.two_payments()
        payments=STOCK.validate(a)
        for event in a.spec[C.STATE]['events']:
            self.assertEqual(payments[event['payload']['payment_id']]['target_id'],event['target_id'])
        restored,aa,pp,qq=self.restored(e.r,saved,a,p,q)
        before=(pp.hp,qq.hp,AP.available(aa))
        self.assertTrue(restored.resolve_class_actor_state_action(aa,second,use=True)['used'])
        self.assertEqual(pp.hp,before[0]);self.assertGreater(qq.hp,before[1])
        self.assertEqual(AP.available(aa),before[2]-1)
        # Another genuine matching payment must not let a changed target choose
        # a new witness for the original trigger, even for declined history.
        altered=deepcopy(saved)
        next(pair for pair in self.event_node(altered,first)['items'] if pair[0]=='target_id')[1]=q.entity_id
        with self.assertRaises(CODEC.StateCodecError):Engine.import_state(e.r,altered)
        ambiguous=deepcopy(saved);self.old_format(ambiguous,first)
        with self.assertRaises(CODEC.StateCodecError):Engine.import_state(e.r,ambiguous)

    def test_invalid_live_target_rejects_before_accept_or_decline_and_preserves_payment(self):
        for use in (False,True):
            with self.subTest(use=use):
                e,a,p,q,event_id,_=self.medical_fixture()
                event=next(x for x in a.spec[C.STATE]['events'] if x['id']==event_id)
                event['target_id']=q.entity_id  # Deliberate invalid derived-state mutation.
                def state():
                    return deepcopy((a.spec,p.hp,q.hp,a._action_history,e.rng.getstate(),e.log_lines))
                before=state()
                with self.assertRaisesRegex(ValueError,'original medicine'):
                    e.resolve_class_actor_state_action(a,event_id,use=use)
                self.assertEqual(state(),before)
                self.assertEqual(a.spec['items']['상처약'],0)
                self.assertEqual(next(iter(STOCK.validate(a).values()))['target_id'],p.entity_id)

if __name__=='__main__':unittest.main()