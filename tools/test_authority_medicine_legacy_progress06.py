"""Native legacy medicine progress and restorative-trigger source controls.

Existing native STOCK originals remain unchanged. Old-format events are obtained
by removing only the new linkage field from actual saved events.
"""
from copy import deepcopy
import json
import unittest
import test_authority_medicine_receipt_binding as BASE
from engine import Engine
import class_actor_state_actions as C
import consumption_execution as STOCK
import action_points as AP
import state_codec as CODEC


class MedicineLegacyProgress06(unittest.TestCase):
    setUpClass=classmethod(BASE.MedicineReceiptBinding.setUpClass.__func__)
    engine=BASE.MedicineReceiptBinding.engine
    trainer=BASE.MedicineReceiptBinding.trainer
    medical_fixture=BASE.MedicineReceiptBinding.medical_fixture
    restored=BASE.MedicineReceiptBinding.restored
    event_node=BASE.MedicineReceiptBinding.event_node
    payload_node=BASE.MedicineReceiptBinding.payload_node
    old_format=BASE.MedicineReceiptBinding.old_format

    def event(self,owner,identity):
        return next(row for row in owner.spec[C.STATE]['events'] if row['id']==identity)

    def legacy(self,*,closed=None):
        e,a,p,q,event_id,saved=self.medical_fixture()
        if closed is not None:
            e.resolve_class_actor_state_action(a,event_id,use=closed)
            saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        self.old_format(saved,event_id)
        e,a,p,q=self.restored(e.r,saved,a,p,q)
        original=deepcopy(e.export_state())
        self.assertNotIn('payment_id',self.event(a,event_id)['payload'])
        self.assertTrue(C.validate(a))
        self.assertEqual(e.export_state(),original,'validation/export cannot pin or mutate old links')
        return e,a,p,q,event_id

    def next_medicine(self,e,a,p,q,event_id):
        first=deepcopy(self.event(a,event_id))
        old_receipts=deepcopy(STOCK.validate(a))
        original=next(iter(old_receipts))
        e.end_encounter()
        a.spec['items']['상처약']=1  # Explicit actual stock observation, matching existing fixture.
        before=(p.hp,q.hp,AP.available(a))
        self.assertEqual(e.use_item(a,'상처약',q),(1,0))
        events=[x for x in a.spec[C.STATE]['events'] if x['source']==C.MEDICAL_TECHNIQUE]
        self.assertEqual(len(events),2)
        self.assertEqual(events[0]['at'],events[1]['at'])
        self.assertEqual(events[0]['payload']['native_result'],events[1]['payload']['native_result'])
        self.assertEqual(events[0]['payload']['payment_id'],original)
        self.assertEqual(events[0]['target_id'],p.entity_id)
        self.assertEqual(events[0]['status'],first['status'])
        self.assertEqual(events[0]['result'],first['result'])
        self.assertNotEqual(events[1]['payload']['payment_id'],original)
        self.assertEqual(events[1]['target_id'],q.entity_id)
        self.assertEqual(a.spec['items']['상처약'],0)
        self.assertEqual((p.hp,AP.available(a)),(before[0],before[2]))
        self.assertGreater(q.hp,before[1])
        self.assertEqual(STOCK.validate(a)[original],old_receipts[original],
                         'retaining the old derived link cannot rewrite original native payment')
        saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        e,a,p,q=self.restored(e.r,saved,a,p,q)
        self.assertEqual(len(STOCK.validate(a)),2)
        second=self.event(a,events[1]['id'])
        before=(p.hp,q.hp,AP.available(a))
        self.assertTrue(e.resolve_class_actor_state_action(a,second['id'],use=True)['used'])
        self.assertEqual(p.hp,before[0]);self.assertGreater(q.hp,before[1])
        self.assertEqual(AP.available(a),before[2]-1)
        e.export_state()

    def test_unique_pending_legacy_pins_only_at_actual_accept_or_decline_and_allows_next_use(self):
        for use in (False,True):
            with self.subTest(use=use):
                e,a,p,q,event_id=self.legacy()
                native=deepcopy(STOCK.validate(a))
                e.resolve_class_actor_state_action(a,event_id,use=use)
                self.assertEqual(self.event(a,event_id)['payload']['payment_id'],next(iter(native)))
                self.assertEqual(STOCK.validate(a),native)
                self.next_medicine(e,a,p,q,event_id)

    def test_already_closed_unique_legacy_is_preserved_before_later_same_time_payment(self):
        for used in (False,True):
            with self.subTest(originally_used=used):
                e,a,p,q,event_id=self.legacy(closed=used)
                self.next_medicine(e,a,p,q,event_id)

    def test_failed_next_action_does_not_pin_legacy_or_consume_stock(self):
        e,a,p,q,event_id=self.legacy(closed=False)
        self.assertEqual(a.budget['standard'],0,'first actual medicine already spent the Standard')
        a.spec['items']['상처약']=1
        before=deepcopy((a.spec,p.hp,q.hp,a._action_history,STOCK.validate(a)))
        self.assertEqual(e.use_item(a,'상처약',q),(0,0))
        self.assertNotIn('payment_id',self.event(a,event_id)['payload'])
        self.assertEqual((a.spec,p.hp,q.hp,a._action_history,STOCK.validate(a)),before)

    def test_real_x_item_remains_native_but_cannot_become_medical_trigger_by_payload_rebind(self):
        e,a,p,q,first,_=self.medical_fixture()
        e.resolve_class_actor_state_action(a,first,use=False)
        e.end_encounter()
        a.spec['items']['플러스파워']=1
        self.assertEqual(e.use_item(a,'플러스파워',p),(1,0))
        x=[r for r in STOCK.validate(a).values() if r['item_stock']['item_id']=='item/플러스파워']
        self.assertEqual(len(x),1);x=x[0]
        self.assertEqual(len(a.spec[C.STATE]['events']),1,'native X use creates no Medical Technique trigger')
        self.assertEqual(a.spec['items']['플러스파워'],0)
        e.export_state()  # Genuine X behavior/receipt must stay exportable.
        a.spec['items']['상처약']=1
        e.use_item(a,'상처약',p)
        event=next(row for row in a.spec[C.STATE]['events'] if row['status']=='pending')
        self.assertEqual(event['at'],x['at'])
        self.assertEqual(event['target_id'],x['target_id'])
        baseline=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        for legacy in (False,True):
            with self.subTest(legacy=legacy):
                saved=deepcopy(baseline)
                payload=self.payload_node(saved,event['id'])
                values={'item_id':x['item_stock']['item_id'],'item_name':'플러스파워',
                        'payment_id':x['receipt_id']}
                for pair in payload['items']:
                    if pair[0] in values:pair[1]=values[pair[0]]
                    elif pair[0]=='native_result':
                        result=saved['nodes'][pair[1]['$ref']]
                        result['items']=[x['native_immediate_result']['done'],x['native_immediate_result']['held']]
                if legacy:self.old_format(saved,event['id'])
                # Only the derivative payload changes; native X stock, payer,
                # target, applied result, and event time remain genuine.
                with self.assertRaises(CODEC.StateCodecError):Engine.import_state(e.r,saved)
                self.assertEqual(json.loads(json.dumps(e.export_state(),ensure_ascii=False)),baseline)
        before=(p.hp,q.hp,AP.available(a))
        self.assertTrue(e.resolve_class_actor_state_action(a,event['id'],use=True)['used'])
        self.assertGreater(p.hp,before[0]);self.assertEqual(q.hp,before[1])
        self.assertEqual(AP.available(a),before[2]-1)


if __name__=='__main__':unittest.main()
