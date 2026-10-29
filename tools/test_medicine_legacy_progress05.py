"""Medicine repair review: real legacy progress and actual nonrestorative receipt."""
from copy import deepcopy
from pathlib import Path
import os
import sys
import json
import unittest
ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine
import action_points as AP
import class_actor_state_actions as C
import consumption_execution as STOCK
import restorative_items as RESTORATIVE
import test_authority_medicine_receipt_binding as FIX


class MedicineLegacyProgress05(unittest.TestCase):
    setUpClass=classmethod(FIX.MedicineReceiptBinding.setUpClass.__func__)
    engine=FIX.MedicineReceiptBinding.engine
    trainer=FIX.MedicineReceiptBinding.trainer
    medical_fixture=FIX.MedicineReceiptBinding.medical_fixture
    restored=FIX.MedicineReceiptBinding.restored
    event_node=FIX.MedicineReceiptBinding.event_node
    payload_node=FIX.MedicineReceiptBinding.payload_node
    old_format=FIX.MedicineReceiptBinding.old_format

    def test_closed_legacy_event_remains_valid_after_second_same_time_native_medicine(self):
        for use in (False,True):
            for already_closed in (False,True):
                with self.subTest(use=use,already_closed=already_closed):
                    e,a,p,q,first,saved=self.medical_fixture()
                    if already_closed:
                        e.resolve_class_actor_state_action(a,first,use=use)
                        saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
                    self.old_format(saved,first)
                    e,a,p,q=self.restored(e.r,saved,a,p,q)
                    if not already_closed:
                        e.resolve_class_actor_state_action(a,first,use=use)
                    old_event=next(x for x in a.spec[C.STATE]['events'] if x['id']==first)
                    status=old_event['status'];result=deepcopy(old_event['result'])
                    payments=STOCK.validate(a)
                    old_id=next(iter(payments))
                    immutable={key:deepcopy(payments[old_id][key]) for key in
                        ('receipt_id','user_id','item_stock','target_id','outcome','results','native_immediate_result','at')}
                    e.end_encounter()
                    a.spec['items']['상처약']=1
                    before_hp=(p.hp,q.hp);before_actions=list(a._action_history);before_ap=AP.available(a)
                    e.use_item(a,'상처약',q)
                    self.assertEqual(p.hp,before_hp[0]);self.assertGreater(q.hp,before_hp[1])
                    self.assertEqual(len(a._action_history),len(before_actions)+1)
                    self.assertEqual(a._action_history[:len(before_actions)],before_actions)
                    self.assertEqual(AP.available(a),before_ap)
                    now=STOCK.validate(a)
                    self.assertEqual(len(now),2)
                    self.assertEqual({key:now[old_id][key] for key in immutable},immutable)
                    events=[x for x in a.spec[C.STATE]['events'] if x['source']==C.MEDICAL_TECHNIQUE]
                    self.assertEqual(len(events),2)
                    self.assertEqual((events[0]['status'],events[0]['result']),(status,result))
                    self.assertEqual(events[0]['at'],events[1]['at'])
                    self.assertEqual(events[0]['payload']['native_result'],events[1]['payload']['native_result'])
                    second_id=events[1]['payload']['payment_id']
                    self.assertNotEqual(second_id,old_id)
                    self.assertEqual(now[second_id]['target_id'],q.entity_id)
                    self.assertEqual(events[1]['target_id'],q.entity_id)
                    restored,aa,pp,qq=self.restored(e.r,json.loads(json.dumps(e.export_state())),a,p,q)
                    self.assertTrue(restored.resolve_class_actor_state_action(aa,events[1]['id'],use=True)['used'])
                    self.assertEqual(pp.hp,p.hp)
                    self.assertEqual(aa.spec['items']['상처약'],0)

    def test_genuine_x_item_application_cannot_be_rebound_as_medical_technique(self):
        e,a,p,q,event_id,_=self.medical_fixture()
        e.resolve_class_actor_state_action(a,event_id,use=False)
        first_event_id=event_id
        e.end_encounter()
        a.spec['items']['플러스파워']=1
        previous=set(STOCK.validate(a))
        e.use_item(a,'플러스파워',p)
        paid_id=(set(STOCK.validate(a))-previous).pop()
        payment=STOCK.validate(a)[paid_id]
        self.assertIn(payment['item_stock']['item_id'],RESTORATIVE.X_ITEMS)
        events=[x for x in a.spec[C.STATE]['events'] if x['source']==C.MEDICAL_TECHNIQUE]
        self.assertEqual(len(events),1,'the native X-item producer must not emit Medical Technique')
        self.assertEqual((events[0]['id'],events[0]['status']),(first_event_id,'declined'))
        # The earlier optional event is closed before another ordinary action.
        # Corrupt a fresh real restorative trigger, preserving the X receipt.
        a.spec['items']['상처약']=1
        e.use_item(a,'상처약',p)
        events=[x for x in a.spec[C.STATE]['events'] if x['source']==C.MEDICAL_TECHNIQUE]
        self.assertEqual(len(events),2)
        event=next(x for x in events if x['status']=='pending')
        event_id=event['id']
        self.assertNotEqual(event_id,first_event_id)
        self.assertEqual(event['at'],payment['at'])
        self.assertEqual(event['target_id'],payment['target_id'])
        # Establish that the untouched native applications and fresh event save normally.
        e.export_state()
        event['payload'].update(payment_id=paid_id,item_id=payment['item_stock']['item_id'],
            item_name='플러스파워',native_result=[payment['native_immediate_result']['done'],
                                                payment['native_immediate_result']['held']])
        before=deepcopy((a.spec,p.hp,q.hp,a._action_history,e.rng.getstate()))
        try:
            payload=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
            loaded,aa,pp,qq=self.restored(e.r,payload,a,p,q)
            result=loaded.resolve_class_actor_state_action(aa,event_id,use=True)
        except ValueError:
            self.assertEqual((a.spec,p.hp,q.hp,a._action_history,e.rng.getstate()),before)
            return
        self.fail('native nonrestorative X-item receipt authorized Medical Technique: '+repr(result))


if __name__=='__main__':
    unittest.main()
