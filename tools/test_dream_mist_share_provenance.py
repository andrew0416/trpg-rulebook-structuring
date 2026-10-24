"""C10-019 audit repair: Dream Reader shares only a sleep caused by an actual Dream Mist use.

ch10:35 lets Dream Reader briefly show others a dream only when the current sleep came from
Dream Mist. The proof is the native Engine.use_item -> item_attacks._consume occurrence: its
paid stock receipt (consumption_execution) is finished as applied to the exact sleep episode
it created. A bare source label (apply_status, GM state, legacy save) stays private-only.
"""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
import test_category2_dream_mist as _fixture_test_category2_dream_mist
import consumption_execution as EXECUTION,dream_state as D,state_codec as CODEC,state_grants as G


class DreamMistShareProvenanceTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_dream_mist.Tests.setUpClass.__func__)
    setUp=_fixture_test_category2_dream_mist.Tests.setUp
    add=_fixture_test_category2_dream_mist.Tests.add
    pokemon=_fixture_test_category2_dream_mist.Tests.pokemon
    restored=_fixture_test_category2_dream_mist.Tests.restored
    begin=_fixture_test_category2_dream_mist.Tests.begin
    prepare=_fixture_test_category2_dream_mist.Tests.prepare
    use=_fixture_test_category2_dream_mist.Tests.use

    def observe(self):return self.e.gm.observe_dream(self.t,'a lantern under the sea',reason='GM observed current dream')
    def receipts(self):return list(EXECUTION.validate(self.a).values())
    def active(self):return self.t.spec[D.KEY]['active']

    def test_source_label_alone_never_unlocks_sharing(self):
        G.grant(self.p,'capabilities','Dream Reader','fixture:dream','fixture')
        self.assertFalse(self.a.spec.get('items'));self.assertIsNone(self.e._active_turn_actor)
        before=deepcopy(self.a.spec.get(EXECUTION.KEY,{}))
        self.assertTrue(self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1'))
        self.observe()
        self.assertEqual(self.a.spec.get(EXECUTION.KEY,{}),before);self.assertNotIn('mist',self.active())
        private=self.e.read_dream(self.p,self.t)
        self.assertEqual((private['mode'],private['sleep_source']),('private_dream_reading','item/꿈안개-1'))
        with self.assertRaisesRegex(ValueError,'originate from Dream Mist'):self.e.read_dream(self.p,self.t,share=True)

    def test_actual_paid_hit_links_applied_payment_to_episode_and_both_restores_keep_it(self):
        self.prepare();out=self.use()
        self.assertTrue(out['status_applied'])
        receipt=self.receipts()[-1];active=self.active()
        self.assertEqual(active['mist'],{'payer_id':self.a.entity_id,'stock_receipt_id':receipt['receipt_id']})
        self.assertEqual((receipt['outcome'],receipt['target_id'],receipt['results']),
                         ('applied',self.t.entity_id,[{'kind':'dream_sleep_episode','id':active['episode_id']}]))
        self.observe();view=self.e.read_dream(self.p,self.t,share=True)
        self.assertEqual(view['mode'],'brief_moving_image')
        self.e.gm.snapshot('mist');e=self.restored();index={c.entity_id:c for c in e.everyone}
        self.assertEqual(e.read_dream(index[self.p.entity_id],index[self.t.entity_id],share=True),view)
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index={c.entity_id:c for c in loaded.everyone}
        self.assertEqual(loaded.read_dream(index[self.p.entity_id],index[self.t.entity_id],share=True),view)
        self.e.cure_status(self.t,'잠듦');self.e.gm.restore('mist')
        self.assertEqual(self.e.read_dream(self.p,self.t,share=True),view)

    def test_miss_and_immunity_spend_but_create_no_shareable_episode(self):
        self.prepare();out=self.use(1)
        self.assertFalse(out['hit']);self.assertEqual(self.receipts()[-1]['outcome'],'paid')
        self.e.gm.set_ability(self.t,'불면',reason='actual acquired sleep immunity');self.begin(self.a)
        out=self.use();self.assertTrue(out['hit']);self.assertFalse(out['status_applied'])
        self.assertEqual([r['outcome'] for r in self.receipts()],['paid','paid'])
        self.assertNotIn('잠듦',self.t.conditions)

    def test_wake_then_other_sleep_or_copied_proof_cannot_share(self):
        self.prepare();self.use();self.observe();proof=deepcopy(self.active()['mist'])
        self.assertEqual(self.e.read_dream(self.p,self.t,share=True)['sleep_serial'],1)
        self.e.cure_status(self.t,'잠듦')
        self.e.apply_status(self.t,'잠듦',source='move/최면술');self.observe()
        with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)
        self.e.cure_status(self.t,'잠듦')
        # A later bare item-labelled sleep that copies the old proof names another episode.
        self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1');self.active()['mist']=proof;self.observe()
        self.assertEqual(self.e.read_dream(self.p,self.t)['sleep_serial'],3)
        with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)

    def test_forged_or_malformed_proof_and_legacy_label_restore(self):
        self.prepare();self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1');self.observe()
        self.active()['mist']={'payer_id':self.a.entity_id,'stock_receipt_id':self.a.entity_id+':stock:9'}
        with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)
        self.active()['mist']={'payer_id':self.a.entity_id,'stock_receipt_id':'x','extra':True}
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        del self.active()['mist']
        # A legacy save that only names the item source restores as a private reading.
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index={c.entity_id:c for c in loaded.everyone}
        reader,target=index[self.p.entity_id],index[self.t.entity_id]
        self.assertEqual(loaded.read_dream(reader,target)['sleep_source'],'item/꿈안개-1')
        with self.assertRaises(ValueError):loaded.read_dream(reader,target,share=True)

    def test_binding_failure_is_atomic(self):
        self.prepare();self.use();self.e.cure_status(self.t,'잠듦');self.begin(self.a)
        serial=self.t.spec[D.KEY]['serial']
        with patch.object(EXECUTION,'finish',side_effect=ValueError('late binding failure')):
            with self.assertRaisesRegex(ValueError,'late binding failure'):self.use()
        self.assertEqual(self.t.spec[D.KEY]['serial'],serial+1);self.assertNotIn('mist',self.active())
        self.assertEqual(self.receipts()[-1]['outcome'],'paid')
        self.observe()
        with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)


    def queued(self):
        import field_effects as FIELD
        self.prepare()
        FIELD.install(self.e,self.a,self.r.move_mech('move/미스트필드')[0]['effects_exec'][0],'move/미스트필드')
        out=self.use()
        self.assertTrue(out['hit']);self.assertTrue(out['status_applied'])
        self.assertNotIn('잠듦',self.t.conditions)
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.a.spec['items']['item/꿈안개-1'],3)
        self.assertEqual(self.receipts()[-1]['outcome'],'deferred')
        return deepcopy(FIELD._pending(self.t)[0])

    def due(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_of_turn(self.t,initiative_count=10)
        self.assertNotIn('잠듦',self.t.conditions)
        self.e.end_of_turn(self.t)

    def test_paid_misty_delay_is_private_until_actual_sleep_and_both_restores_preserve_cause(self):
        import field_effects as FIELD,world_entities as W
        self.queued()
        with self.assertRaisesRegex(ValueError,'sleeping'):self.e.read_dream(self.p,self.t,share=True)
        self.e.gm.snapshot('queued');self.e.gm.restore('queued')
        original_ids=[c.entity_id for c in (self.a,self.p,self.t)]
        self.e=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        self.a,self.p,self.t=(W.actor_index(self.e)[uid] for uid in original_ids)
        self.due();self.observe()
        view=self.e.read_dream(self.p,self.t,share=True)
        self.assertEqual(view['mode'],'brief_moving_image')
        self.assertEqual(self.receipts()[-1]['results'],[{'kind':'dream_sleep_episode','id':self.active()['episode_id']}])
        before=deepcopy((self.active(),self.receipts()))
        self.assertEqual(FIELD.end_turn(self.e,self.t),[])
        self.assertEqual((self.active(),self.receipts()),before)
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=W.actor_index(loaded)
        self.assertEqual(loaded.read_dream(index[self.p.entity_id],index[self.t.entity_id],share=True),view)

    def test_delayed_cure_and_later_immunity_close_payment_without_share_authority(self):
        import field_effects as FIELD
        for cause in ('cure','immunity'):
            with self.subTest(cause=cause):
                self.setUp();pending=self.queued()
                if cause=='cure':self.e.cure_status(self.t,'잠듦')
                else:self.e.gm.set_ability(self.t,'불면',reason='immunity acquired before actual delayed sleep')
                self.due()
                self.assertNotIn('잠듦',self.t.conditions);self.assertFalse(FIELD._pending(self.t))
                self.assertEqual(self.receipts()[-1]['outcome'],'no_effect')
                self.assertEqual(self.receipts()[-1]['results'],[])
                self.assertEqual(self.a.spec['items']['item/꿈안개-1'],3)
                with self.assertRaisesRegex(ValueError,'actual paid hit'):D.validate_deferred(self.e,self.t,pending)
                with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)

    def test_bare_label_delay_and_existing_pending_status_do_not_borrow_paid_hit(self):
        import field_effects as FIELD
        self.prepare()
        FIELD.install(self.e,self.a,self.r.move_mech('move/미스트필드')[0]['effects_exec'][0],'move/미스트필드')
        self.assertTrue(self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1',applied_by=self.a))
        original=deepcopy(FIELD._pending(self.t)[0])
        out=self.use();self.assertTrue(out['hit']);self.assertFalse(out['status_applied'])
        self.assertEqual(FIELD._pending(self.t)[0],original)
        self.assertEqual(self.receipts()[-1]['outcome'],'paid')
        self.due();self.observe()
        self.assertEqual(self.e.read_dream(self.p,self.t)['mode'],'private_dream_reading')
        with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)

    def test_delayed_queue_tampering_or_other_target_cannot_reuse_payment(self):
        import field_effects as FIELD
        pending=self.queued()
        bad=deepcopy(pending);bad['activate_after_turn']+=1
        with self.assertRaisesRegex(ValueError,'actual paid hit'):D.validate_deferred(self.e,self.t,bad)
        with self.assertRaisesRegex(ValueError,'actual paid hit'):D.validate_deferred(self.e,self.p,pending)
        receipt=self.receipts()[-1];before=deepcopy(receipt)
        with self.assertRaisesRegex(ValueError,'original target'):
            EXECUTION.finish(self.a,receipt['item_stock'],target_id=self.p.entity_id,outcome='applied',results=[{'kind':'dream_sleep_episode','id':'forged'}])
        self.assertEqual(receipt,before)
        FIELD._pending(self.t)[0]['source']='item/꿈안개'
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

    def test_delayed_orphan_duplicate_and_corrupt_reference_reject_save(self):
        import field_effects as FIELD
        for corruption in ('orphan','duplicate','payer','receipt'):
            with self.subTest(corruption=corruption):
                self.setUp();self.queued()
                rows=FIELD._pending(self.t)
                if corruption=='orphan':self.t.custom_conditions.pop(FIELD.DEFERRED)
                elif corruption=='duplicate':rows.append(deepcopy(rows[0]))
                elif corruption=='payer':rows[0]['dream_mist']['payer_id']=[]
                else:rows[0]['dream_mist']['stock_receipt_id']=[]
                with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

    def test_delayed_episode_proof_does_not_survive_cure_and_resleep(self):
        self.queued();self.due();self.observe();proof=deepcopy(self.active()['mist'])
        self.assertEqual(self.e.read_dream(self.p,self.t,share=True)['mode'],'brief_moving_image')
        self.e.cure_status(self.t,'잠듦')
        self.e.apply_status(self.t,'잠듦',source='item/꿈안개-1',force=True)
        self.active()['mist']=proof;self.observe()
        with self.assertRaises(ValueError):self.e.read_dream(self.p,self.t,share=True)

    def test_completed_or_cancelled_payment_cannot_be_deferred_again(self):
        for cancelled in (False,True):
            with self.subTest(cancelled=cancelled):
                self.setUp();self.queued()
                if cancelled:self.e.cure_status(self.t,'잠듦')
                else:self.due()
                receipt=self.receipts()[-1];before=deepcopy(receipt)
                with self.assertRaisesRegex(ValueError,'unused stock payment'):
                    EXECUTION.defer(self.a,receipt['item_stock'],target_id=self.t.entity_id,results=[{'kind':'dream_deferred_sleep','id':'reopen'}])
                self.assertEqual(receipt,before)


if __name__=='__main__':unittest.main()
