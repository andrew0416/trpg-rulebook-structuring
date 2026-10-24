"""Prepared, unexecuted actual-producer regressions for native switch handoff."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import state_codec as CODEC
import native_switch_transfer as SWITCH
import native_order_transfer as TRANSFER
import training_features as TRAINING
import combat_timing as TIME
import coat_effects as COATS
import combat_precision_features as PRECISION
import directive_features as DIRECTOR
import turn as TURN
import native_switch_policy as SWITCH_POLICY
from grid import Grid
from native_scenario_fixture import assert_rejected_unchanged


class NativeSwitchTransferRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

    def setUp(self):self.setup()

    def setup(self,*,juggler=False,precision=False,director=False):
        from builder import build_trainer
        import items as ITEMS
        self.e=Engine(self.r,seed=814)
        stats={'hp':60,'atk':20,'def':15,'spa':20,'spd':15,'spe':10}
        classes=([SWITCH.CLASS] if juggler else [])+([DIRECTOR.CLASS] if director else [])
        feats=[*TRAINING.RULES]
        if juggler:feats.extend(('feat/퀵-스위치',SWITCH.ROUND_TRIP,SWITCH.TAG_IN))
        if precision:feats.append(PRECISION.PRECISION)
        if director:feats.append(DIRECTOR.FEATURE)
        self.t=Combatant(self.r,build_trainer(self.r,'trainer',20,stats,moves=[],
            skills={'육상':3,'명령':5 if precision else 3,'협박':3,'매력':3,'곡예':5 if juggler else 3},
            extra={'classes':classes,'feats':feats,'movement':{'land':6,'swim':3,'sky':0}}))
        common=dict(level=20,stats=stats,skills={'육상':'2d6+1'},movement={'land':6,'swim':3,'sky':0})
        self.p=Combatant(self.r,dict(common,name='partner',kind='pokemon',trainer_id=self.t.entity_id,
            trainer=self.t.name,moves=['move/불꽃세례']))
        self.foe=Combatant(self.r,dict(common,name='foe',kind='pokemon',moves=[]))
        for actor,pos,side in ((self.t,(0,0),'party'),(self.p,(1,0),'party'),(self.foe,(2,0),'enemy')):
            self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual initially declared source ownership')
        ITEMS.register_feats(self.e,self.t)
        self.q=Combatant(self.r,dict(id='native-transfer-reserve',name='reserve',kind='pokemon',
            level=20,stats=deepcopy(self.p.spec['stats']),skills={},moves=[],movement={'land':6},
            trainer_id=self.t.entity_id,trainer=self.t.name,pos=(3,0)))
        self.q.side=self.p.side;self.q.on_field=False
        self.e.everyone.append(self.q);self.e.time_actors([self.q])
        self.e.gm.observe_loyalty(self.p,6,reason='actual transfer Move obedience')
        self.e.gm.observe_loyalty(self.q,6,reason='actual reserve Move obedience')
        self.e.gm.set_move(self.p,SWITCH.BATON,reason='actual learned Baton Pass')
        self.e.gm.set_move(self.p,'move/칼춤',reason='actual preceding self Move')
        self.e.gm.observe_sensory_environment(self.t,self.p,paths={'auditory':True},present=True,reason='actual Order delivery')

    def open(self,actor=None):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor or self.p,initiative_count=20)

    def mapped(self):
        for actor in self.e.everyone:
            self.e.gm.set_footprint(actor,[(0,0)],reason='actual one-cell fixture body')
        self.e.grid=Grid(8,8)

    def baton(self):
        SWITCH.select(self.e,self.p,self.q,source=SWITCH.BATON,reason='actual reserve selection')
        self.e.use_move(self.p,self.p,SWITCH.BATON)
        records=[row for row in self.e._effect_dispatch_receipts.values()
                 if row['source_id']==SWITCH.BATON and row.get('native_switch')]
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['status'],'completed')
        return records[0]

    def test_baton_without_coats_transfers_stages_and_records_real_replacement(self):
        self.open();self.e.change_stage(self.p,'atk',2);self.e.change_stage(self.p,'def',-1)
        self.e.apply_status(self.p,'수렁')
        result=self.baton()['native_switch']
        self.assertEqual((self.q.stages['atk'],self.q.stages['def']),(2,-1))
        self.assertEqual((self.p.stages['atk'],self.p.on_field,self.q.on_field),(0,False,True))
        self.assertEqual((result['outgoing_id'],result['incoming_id'],result['recalled'],result['sent']),
                         (self.p.entity_id,self.q.entity_id,True,True))
        self.assertEqual(self.p.budget['standard'],0)
        self.assertNotIn('passed',vars(self.p))

    def test_missing_replacement_fails_before_move_payment_or_rng(self):
        self.open()
        assert_rejected_unchanged(self.e,lambda:self.e.use_move(self.p,self.p,SWITCH.BATON),reason_pattern='selected replacement')

    def test_four_actual_training_orders_keep_payment_and_issuer_deadline(self):
        for source in TRAINING.RULES:
            with self.subTest(source=source):
                self.setUp();self.open(self.t)
                self.e.manual_feat(self.t,source,self.p)
                row=next(row for row in TRAINING.records(self.p) if row['mode']=='orders')
                source_id=row['_state_source'];deadline=TIME.records(self.p)[0]['turn_start_deadline']
                self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=19)
                self.baton()
                moved=next(row for row in TRAINING.records(self.q) if row['mode']=='orders')
                self.assertEqual(moved['_state_source'],source_id)
                self.assertEqual(TRANSFER.origin_id(moved,self.q),self.p.entity_id)
                self.assertIs(TIME.records(self.q)[0]['turn_owner'],self.t)
                self.assertEqual(TIME.records(self.q)[0]['turn_start_deadline'],deadline)
                self.assertFalse(TRAINING.records(self.p))
                self.e.end_of_turn(self.p);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=20)
                self.assertFalse([row for row in TRAINING.records(self.q) if row['mode']=='orders'])

    def test_pinpoint_same_bound_ap_instance_moves_and_releases_once(self):
        self.setup(precision=True)
        self.open(self.t);self.e.manual_feat(self.t,PRECISION.PINPOINT,self.p)
        before=deepcopy(self.t.ap_account.identified_bindings())
        original=PRECISION.binding(self.e,self.p)['instance']
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=19);self.baton()
        self.assertIsNone(PRECISION.binding(self.e,self.p))
        self.assertEqual(PRECISION.binding(self.e,self.q)['instance'],original)
        self.assertEqual(self.t.ap_account.identified_bindings(),before)
        self.e.end_of_turn(self.p);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=20)
        PRECISION.release(self.e,self.t,self.q)
        self.assertNotIn(original,self.t.ap_account.identified_bindings())

    def test_director_keeps_original_paid_target_and_remaining_holder_turn(self):
        self.setup(director=True)
        self.open(self.t)
        result=self.e.manual_feat(self.t,DIRECTOR.FEATURE,self.p,adjustment='increase')
        original_plan=deepcopy(self.e._effect_dispatch_receipts[result['receipt']][DIRECTOR.KEY])
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=19);self.baton()
        row=self.e._effect_dispatch_receipts[result['receipt']]
        self.assertIs(row['target'],self.p);self.assertEqual(row[DIRECTOR.KEY],original_plan)
        moved=next(row for row in TIME.records(self.q) if row.get('effect_receipt') is result['receipt'])
        self.assertIs(moved['lifetime_target'],self.p)
        self.assertEqual(TRANSFER.original_policy(moved),row['lifetime_contracts'][self.p.entity_id]['policy'])
        self.e.end_of_turn(self.p)
        self.assertFalse([r for r in TIME.records(self.q) if r.get('effect_receipt') is result['receipt']])
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.q,initiative_count=20)
        self.e.end_of_turn(self.q)
        self.assertFalse([r for r in TIME.records(self.q) if r.get('effect_receipt') is result['receipt']])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_round_trip_actual_move_recipient_and_one_ap_not_trainer_recall(self):
        self.setup(juggler=True);self.open();self.e.use_move(self.p,self.p,'move/칼춤')
        SWITCH.select(self.e,self.p,self.q,source=SWITCH.ROUND_TRIP,reason='actual Round Trip choice')
        before=self.t.ap_account.available()
        result=self.e.manual_feat(self.t,SWITCH.ROUND_TRIP,self.p)
        self.assertTrue(self.t.on_field);self.assertFalse(self.p.on_field);self.assertTrue(self.q.on_field)
        self.assertEqual(self.t.ap_account.available(),before-1)
        self.assertEqual(self.e._effect_dispatch_receipts[result['receipt']]['status'],'completed')
        self.assertEqual(self.q.stages['atk'],0)

    def test_round_trip_same_time_intervening_action_and_replay_reject(self):
        self.setup(juggler=True);self.open();self.e.use_move(self.p,self.p,'move/칼춤')
        SWITCH.select(self.e,self.p,self.q,source=SWITCH.ROUND_TRIP,reason='actual choice')
        self.assertTrue(TURN.spend(self.e,self.p,'shift','actual later action'))
        assert_rejected_unchanged(self.e,lambda:self.e.manual_feat(self.t,SWITCH.ROUND_TRIP,self.p),reason_pattern='immediate native action boundary')
        self.setup(juggler=True);self.open();self.e.use_move(self.p,self.p,'move/칼춤')
        SWITCH.round_trip(self.e,self.t,self.p,self.q)
        assert_rejected_unchanged(self.e,lambda:self.e.manual_feat(self.t,SWITCH.ROUND_TRIP,self.p),reason_pattern='already consumed')

    def test_tag_in_real_paid_party_recall_then_next_send_survives_json_and_gm(self):
        self.setup(juggler=True)
        self.e.configure_party_combat(self.t,battle_mode='league',reason='actual party action')
        self.open(self.t);self.e.change_stage(self.p,'atk',3)
        self.e.act_on_party(self.t,recall=[self.p],request_id='actual-recall',reason='actual recall trigger')
        before=self.t.ap_account.available()
        self.e.manual_feat(self.t,SWITCH.TAG_IN,self.p)
        self.assertEqual(self.t.ap_account.available(),before-1)
        saved=CODEC.dump_engine(self.e);loaded=CODEC.load_engine(self.r,json.loads(json.dumps(saved)))
        trainer=next(a for a in loaded.everyone if a.entity_id==self.t.entity_id)
        reserve=next(a for a in loaded.everyone if a.entity_id==self.q.entity_id)
        snapshot=loaded.gm.snapshot();loaded.gm.send_out(reserve,reason='actual next send-out')
        self.assertEqual(reserve.stages['atk'],3);self.assertNotIn(SWITCH.TAG,trainer.spec)
        loaded.gm.restore(snapshot);loaded.gm.send_out(reserve,reason='restored same actual send-out')
        self.assertEqual(reserve.stages['atk'],3)
        self.assertEqual(len([r for r in trainer.spec[SWITCH.USES] if r.get('incoming_id')==reserve.entity_id]),1)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_actual_standard_party_switch_selects_tag_in_and_replay_does_not_repay(self):
        self.setup(juggler=True);self.mapped()
        self.e.configure_party_combat(self.t,battle_mode='league',reason='actual Standard switch')
        self.open(self.t);self.e.change_stage(self.p,'atk',2)
        before=self.t.ap_account.available()
        options=dict(recall=[self.p],send=[(self.q,self.p.pos)],request_id='paired-tag',reason='selected actual Tag In',tag_in=True)
        result=self.e.act_on_party(self.t,**options)
        self.assertEqual(result['payment']['funded'],{'standard':1})
        self.assertEqual(self.t.budget,{'standard':0,'shift':1,'swift':1})
        self.assertEqual(self.t.ap_account.available(),before-1)
        self.assertEqual(self.q.stages['atk'],2)
        self.assertFalse(self.p.on_field);self.assertTrue(self.q.on_field)
        self.assertNotIn(SWITCH.TAG,self.t.spec)
        saved=CODEC.dump_engine(self.e)
        self.assertEqual(self.e.act_on_party(self.t,**options),result)
        self.assertEqual(CODEC.dump_engine(self.e),saved)

    def test_handoff_clock_or_recipient_cannot_borrow_an_unrelated_recall(self):
        self.open(self.t);self.e.manual_feat(self.t,TRAINING.FOCUSED,self.p)
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=19);self.baton()
        row=next(r for r in TRAINING.records(self.q) if r['mode']=='orders')
        original=deepcopy(row[TRANSFER.KEY])
        for field,value in (('to_turn',99),('source',SWITCH.TAG_IN),('recall_id','unrelated-recall')):
            with self.subTest(field=field):
                row[TRANSFER.KEY]=deepcopy(original);row[TRANSFER.KEY]['events'][0][field]=value
                with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        row[TRANSFER.KEY]=original
        self.assertTrue(self.e.validate_state()['valid'])

    def test_english_source_choice_excludes_training_but_keeps_actual_stratagem(self):
        for feature in (TRAINING.FOCUSED,PRECISION.PINPOINT):
            with self.subTest(feature=feature):
                self.setup(precision=feature==PRECISION.PINPOINT)
                pending=SWITCH_POLICY.choices(self.e)
                SWITCH_POLICY.choose(self.e,self.p,'english_1_05_stratagems',
                    reason='explicit table selection of English Baton entry',decision_scope=pending['decision_scope'])
                self.open(self.t);self.e.manual_feat(self.t,feature,self.p)
                self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=19)
                proof=self.baton()['native_switch']
                self.assertEqual(proof['contract']['scope'],'stratagems')
                if feature==TRAINING.FOCUSED:
                    self.assertFalse(TRAINING.records(self.q));self.assertTrue(TRAINING.records(self.p))
                    self.assertFalse(proof['transfer']['orders'])
                else:self.assertIsNotNone(PRECISION.binding(self.e,self.q))

    def test_tag_in_locks_chosen_baton_scope_before_next_send(self):
        self.setup(juggler=True);self.mapped()
        self.e.configure_party_combat(self.t,battle_mode='league',reason='actual source-selected switch')
        pending=SWITCH_POLICY.choices(self.e)
        SWITCH_POLICY.choose(self.e,self.p,'english_1_05_stratagems',reason='actual English source decision',decision_scope=pending['decision_scope'])
        self.open(self.t);self.e.manual_feat(self.t,TRAINING.FOCUSED,self.p)
        self.e.end_of_turn(self.t);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p,initiative_count=30)
        self.e.act_on_party(self.t,recall=[self.p],send=[(self.q,self.p.pos)],tag_in=True,
            request_id='english-tag',reason='actual Tag In source inheritance')
        use=next(row for row in self.t.spec[SWITCH.USES] if row.get('source')==SWITCH.TAG_IN)
        self.assertEqual(use['contract']['scope'],'stratagems')
        self.assertFalse(TRAINING.records(self.q));self.assertTrue(TRAINING.records(self.p))
        self.assertTrue(self.e.validate_state()['valid'])

    def test_unstarted_target_turn_moves_to_reserve_next_actual_turn_without_granting_one(self):
        self.setup(juggler=True,director=True);self.mapped()
        self.e.configure_party_combat(self.t,battle_mode='league',reason='actual pending-turn transfer')
        self.open(self.t);use=self.e.manual_feat(self.t,DIRECTOR.FEATURE,self.p,adjustment='increase')
        self.e.end_of_turn(self.t);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.t,initiative_count=20)
        self.e.act_on_party(self.t,recall=[self.p],send=[(self.q,self.p.pos)],tag_in=True,
            request_id='pending-director',reason='actual pending target turn')
        record=next(row for row in TIME.records(self.q) if row.get('effect_receipt') is use['receipt'])
        self.assertIs(record['lifetime_target'],self.q)
        self.assertNotIn('turn_anchor',record[TRANSFER.KEY])
        self.assertEqual(self.q.custom_conditions.get('combat_turn_serial',0),0)
        self.assertIs(self.e._active_turn_actor,self.t)
        self.e.end_of_turn(self.t);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.q,initiative_count=20)
        self.assertIn(record,TIME.records(self.q));self.e.end_of_turn(self.q)
        self.assertFalse([row for row in TIME.records(self.q) if row.get('effect_receipt') is use['receipt']])

    def test_repeated_actual_tag_recall_keeps_one_original_open_turn_anchor(self):
        self.setup(juggler=True,director=True)
        third=Combatant(self.r,dict(id='native-transfer-third',name='third reserve',kind='pokemon',
            level=20,stats=deepcopy(self.p.spec['stats']),skills={},moves=[],movement={'land':6},
            trainer_id=self.t.entity_id,trainer=self.t.name,pos=(4,0)))
        third.side=self.p.side;third.on_field=False
        self.e.everyone.append(third);self.e.time_actors([third])
        self.open(self.t);use=self.e.manual_feat(self.t,DIRECTOR.FEATURE,self.p,adjustment='increase')
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=19);self.baton()
        first=next(row for row in TIME.records(self.q) if row.get('effect_receipt') is use['receipt'])
        anchor=deepcopy(first[TRANSFER.KEY]['turn_anchor'])
        SWITCH.select_tag_in(self.e,self.t,self.q,reason='actual GM-observed second recall')
        self.e.gm.recall(self.q,reason='actual second recall while original turn stays open')
        self.e.gm.send_out(third,reason='actual next send-out')
        moved=next(row for row in TIME.records(third) if row.get('effect_receipt') is use['receipt'])
        self.assertEqual(moved[TRANSFER.KEY]['turn_anchor'],anchor)
        self.assertIs(moved['lifetime_target'],self.p);self.assertIs(self.e._active_turn_actor,self.p)
        self.e.end_of_turn(self.p)
        self.assertFalse([row for row in TIME.records(third) if row.get('effect_receipt') is use['receipt']])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_delayed_tag_stages_expire_on_actual_encounter_reset_without_erasing_receiver_base(self):
        self.setup(juggler=True);self.mapped()
        self.e.configure_party_combat(self.t,battle_mode='league',reason='actual delayed Tag source')
        self.open(self.t);self.e.change_stage(self.p,'atk',3)
        self.e.act_on_party(self.t,recall=[self.p],request_id='delayed-recall',reason='actual recall')
        self.e.manual_feat(self.t,SWITCH.TAG_IN,self.p)
        original=deepcopy(self.p.spec[SWITCH.RECALLS][-1])
        paid=self.t.spec['ap_spent']
        self.e.end_of_turn(self.t);self.e.end_encounter(self.e.everyone)
        self.e.apply_status(self.q,'화상')
        baseline=dict(self.q.stages)
        self.assertEqual(self.p.spec[SWITCH.RECALLS][-1],original)
        self.assertEqual(self.t.spec[SWITCH.TAG]['stage_reset']['source'],'combat_state_lifecycle.reset_actor')
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        trainer=next(a for a in loaded.everyone if a.entity_id==self.t.entity_id)
        reserve=next(a for a in loaded.everyone if a.entity_id==self.q.entity_id)
        loaded.gm.send_out(reserve,reason='actual later send after source reset')
        self.assertEqual(reserve.stages,baseline);self.assertEqual(trainer.spec['ap_spent'],paid)
        use=next(row for row in trainer.spec[SWITCH.USES] if row['source']==SWITCH.TAG_IN)
        self.assertIsNone(use['transfer']['stages']);self.assertNotIn(SWITCH.TAG,trainer.spec)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_fainted_tag_stage_exception_requires_selected_qna_source(self):
        for profile,expected in (('core',3),('all',0)):
            with self.subTest(profile=profile):
                self.r=Rules(str(ROOT),ruleset=profile);self.setup(juggler=True);self.mapped()
                self.e.configure_party_combat(self.t,battle_mode='league',reason='actual fainted recall source')
                self.open(self.t);self.e.change_stage(self.p,'atk',3)
                self.e.gm.faint(self.p,reason='actual faint before recall')
                self.e.act_on_party(self.t,recall=[self.p],send=[(self.q,self.p.pos)],tag_in=True,
                    request_id='fainted-tag',reason='actual selected Tag In on fainted recall')
                use=next(row for row in self.t.spec[SWITCH.USES] if row['source']==SWITCH.TAG_IN)
                self.assertEqual(self.q.stages['atk'],expected)
                self.assertEqual(use['fainted_stage_rule'] is None,profile=='core')
                if profile=='all':
                    self.assertEqual(use['stage_reset']['source'],'hb-finance:36')
                    self.assertEqual(use['fainted_stage_rule']['line_sha256'],SWITCH_POLICY.QNA_LINE_SHA)
                self.assertTrue(self.e.validate_state()['valid'])

    def encoded_dict(self,payload,**fields):
        matches=[]
        for uid,node in payload['nodes'].items():
            if node['kind']!='dict':continue
            values={key:value for key,value in node['items'] if type(key)is str}
            if all(values.get(key)==value for key,value in fields.items()):matches.append((uid,node))
        self.assertEqual(len(matches),1)
        return matches[0]

    def test_tag_in_coat_without_native_recall_or_paid_occurrence_rejects_before_mutation(self):
        self.setup(juggler=True);self.e.gm.set_move(self.p,'move/아쿠아링',reason='actual learned Coat Move')
        self.open();self.e.use_move(self.p,self.p,'move/아쿠아링')
        assert_rejected_unchanged(self.e,lambda:COATS.transfer_to(self.e,self.p,self.q,source=SWITCH.TAG_IN),
            reason_pattern='actual Tag In recall')
        self.e.gm.recall(self.p,reason='actual recall without selecting or paying Tag In')
        recall=self.p.spec[SWITCH.RECALLS][-1]['id']
        assert_rejected_unchanged(self.e,lambda:COATS.transfer_to(self.e,self.p,self.q,source=SWITCH.TAG_IN,recall_id=recall),
            reason_pattern='actual native switch occurrence')

    def test_paid_tag_in_coat_missing_each_native_proof_field_rejects_json_and_gm(self):
        self.setup(juggler=True);self.mapped()
        self.e.configure_party_combat(self.t,battle_mode='league',reason='actual paid Coat switch')
        self.e.gm.set_move(self.p,'move/아쿠아링',reason='actual learned Coat Move')
        self.open();self.e.use_move(self.p,self.p,'move/아쿠아링')
        coat_id=COATS.live(self.p)[0]['id']
        self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.t,initiative_count=20)
        paid=self.t.ap_account.available()
        self.e.act_on_party(self.t,recall=[self.p],send=[(self.q,self.p.pos)],tag_in=True,
            request_id='proved-coat-tag',reason='actual selected Coat handoff')
        self.assertEqual(self.t.ap_account.available(),paid-1)
        self.assertEqual(COATS.live(self.q)[0]['id'],coat_id)
        proof=deepcopy(self.t.spec[SWITCH.USES][-1])
        saved=json.loads(json.dumps(CODEC.dump_engine(self.e)))
        loaded=CODEC.load_engine(self.r,deepcopy(saved))
        self.assertTrue(loaded.validate_state()['valid'])
        fields=('recall_id','trainer_id','from_turn','to_turn')
        for missing in [(field,) for field in fields]+[fields]:
            with self.subTest(missing=missing):
                payload=deepcopy(saved)
                _,event=self.encoded_dict(payload,source=SWITCH.TAG_IN,
                    from_holder_id=self.p.entity_id,holder_id=self.q.entity_id)
                event['items']=[pair for pair in event['items'] if pair[0] not in missing]
                with self.assertRaisesRegex(ValueError,'native recall proof'):CODEC.load_engine(self.r,payload)
                self.e.gm.snapshot('coat-proof')
                snapshot=self.e.gm.snapshots['coat-proof']
                history=snapshot['combatants'][id(self.q)]['coats'][0][COATS.E.KEY]['ownership']
                for field in missing:history[-1].pop(field)
                self.assertEqual(snapshot['combatants'][id(self.t)]['spec'][SWITCH.USES][-1],proof)
                assert_rejected_unchanged(self.e,lambda:self.e.gm.restore('coat-proof'),reason_pattern='native recall proof')
        self.assertEqual(self.t.spec[SWITCH.USES][-1],proof)

    def test_active_anchor_cannot_substitute_same_serial_borrowed_turn_in_json_or_gm(self):
        self.setup(juggler=True,director=True)
        participants=[self.t,self.p,self.foe]
        self.e.prepare_initiative_schedule(participants,source='gm/test-schedule',
            order_groups=[[actor.entity_id] for actor in participants])
        self.e.start_round(participants);self.e.start_of_turn(self.t)
        use=self.e.manual_feat(self.t,DIRECTOR.FEATURE,self.p,adjustment='increase')
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p)
        request=dict(id='native-anchor-borrow',actor_id=self.foe.entity_id,source='homebrew/whole-turn',priority=10,
            mode='borrow_turn',payment='future_turn',budget=None,clock='owner_turn',settlement_clock='none')
        window=self.e.queue_initiative_reactions([request],trigger=dict(kind='turn',actor_id=self.p.entity_id,
            serial=self.p.custom_conditions['combat_turn_serial'],round=self.e.round_no))
        self.e.begin_initiative_reaction(window['window_id'],request['id'])
        SWITCH.select_tag_in(self.e,self.t,self.p,reason='actual transfer during suspended eligible turn')
        self.e.gm.recall(self.p,reason='actual original holder recall inside borrowed turn')
        self.e.gm.send_out(self.q,reason='actual beneficiary sent inside borrowed turn')
        record=next(row for row in TIME.records(self.q) if row.get('effect_receipt') is use['receipt'])
        original=deepcopy(record[TRANSFER.KEY]);borrowed=TRANSFER._open_turn(self.e,self.foe)
        self.assertEqual(original['turn_anchor']['turn_serial'],borrowed['turn_serial'])
        self.assertNotEqual(original['turn_anchor']['loan_id'],borrowed['loan_id'])
        self.assertIs(record['lifetime_target'],self.p)
        proof=deepcopy(self.t.spec[SWITCH.USES][-1])
        saved=json.loads(json.dumps(CODEC.dump_engine(self.e)))
        restored=CODEC.load_engine(self.r,deepcopy(saved))
        self.assertTrue(restored.validate_state()['valid'])
        payload=deepcopy(saved)
        history_id,history=self.encoded_dict(payload,instance_id=original['instance_id'],origin_id=self.p.entity_id)
        anchor_ref=dict(history['items'])['turn_anchor']
        payload['nodes'][anchor_ref['$ref']]['items']=[[key,value] for key,value in borrowed.items()]
        _,timer=self.encoded_dict(payload,**{TRANSFER.KEY:{'$ref':history_id}})
        foe_ref=next({'$ref':uid} for uid,node in payload['nodes'].items() if node['kind']=='actor'
            and dict(payload['nodes'][dict(payload['nodes'][node['attrs']['$ref']]['items'])['spec']['$ref']]['items']).get('id')==self.foe.entity_id)
        timer['items']=[[key,foe_ref if key=='lifetime_target' else value] for key,value in timer['items']]
        with self.assertRaisesRegex(ValueError,'turn anchor'):CODEC.load_engine(self.r,payload)
        self.e.gm.snapshot('anchor-proof')
        snapshot=self.e.gm.snapshots['anchor-proof']
        moved=next(row for row in snapshot['combatants'][id(self.q)]['custom_conditions'][TIME.KEY]
            if row.get(TRANSFER.KEY,{}).get('instance_id')==original['instance_id'])
        moved[TRANSFER.KEY]['turn_anchor']=deepcopy(borrowed);moved['lifetime_target']=self.foe
        self.assertEqual(moved[TRANSFER.KEY]['events'],original['events'])
        self.assertEqual(snapshot['combatants'][id(self.t)]['spec'][SWITCH.USES][-1],proof)
        assert_rejected_unchanged(self.e,lambda:self.e.gm.restore('anchor-proof'),reason_pattern='turn anchor')
        self.assertEqual(record[TRANSFER.KEY],original);self.assertEqual(self.t.spec[SWITCH.USES][-1],proof)
        self.e.finish_initiative_reaction();self.assertIs(self.e._active_turn_actor,self.p)
        self.e.end_of_turn(self.p)
        self.assertFalse([row for row in TIME.records(self.q) if row.get(TRANSFER.KEY,{}).get('instance_id')==original['instance_id']])

    def test_pending_and_independent_histories_reject_an_added_turn_anchor(self):
        for phase in ('pending','independent'):
            with self.subTest(phase=phase):
                self.setup(juggler=True,director=phase=='pending')
                self.open(self.t)
                if phase=='pending':
                    use=self.e.manual_feat(self.t,DIRECTOR.FEATURE,self.p,adjustment='increase')
                else:self.e.manual_feat(self.t,TRAINING.FOCUSED,self.p)
                SWITCH.select_tag_in(self.e,self.t,self.p,reason='actual handoff before the recipient turn')
                self.e.gm.recall(self.p,reason='actual selected recall');self.e.gm.send_out(self.q,reason='actual next send')
                record=(next(row for row in TIME.records(self.q) if row.get('effect_receipt') is use['receipt'])
                    if phase=='pending' else next(row for row in TRAINING.records(self.q) if row['mode']=='orders'))
                history=record[TRANSFER.KEY]
                self.assertEqual(history['events'][-1]['clock']['phase'],phase)
                self.assertNotIn('turn_anchor',history)
                payload=json.loads(json.dumps(CODEC.dump_engine(self.e)))
                _,encoded=self.encoded_dict(payload,instance_id=history['instance_id'],origin_id=self.p.entity_id)
                encoded['items'].append(['turn_anchor',None])
                with self.assertRaisesRegex(ValueError,'turn anchor'):CODEC.load_engine(self.r,payload)


class NativeDuelistHandoffRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')

    def fixture(self,mode):
        import test_book_duelist_momentum as FIX
        import duelist as DUELIST
        h=FIX.DuelistMomentumTests();h.rules=self.rules
        h.setup(ability='강내성');h.rounds(3)
        q=h.extra_partner();h.e.gm.set_ability(q,'강내성',reason='actual reserve baseline Ability')
        h.e.gm.recall(q,reason='actual off-field reserve')
        h.e.gm.observe_loyalty(q,6,reason='actual reserve obedience')
        h.e.gm.set_move(h.p,'move/잠자기',add=False,reason='actual Move replacement')
        h.e.gm.set_move(h.p,SWITCH.BATON,reason='actual Baton Pass learning')
        if mode==1:h.manual(mode,ability=DUELIST.EXPLOIT)
        else:h.manual(mode)
        h.start(h.p)
        SWITCH.select(h.e,h.p,q,reason='actual passed Manual recipient')
        h.e.use_move(h.p,h.p,SWITCH.BATON)
        return h,q

    def test_manual1_source_and_timer_move_together_then_original_turn_closes_after_json(self):
        import duelist as DUELIST,ability_transitions as AB
        h,q=self.fixture(1)
        record=next(row for row in TIME.records(q) if row.get('duelist_mode')==1)
        self.assertTrue(AB.active(q,DUELIST.EXPLOIT));self.assertFalse(AB.active(q,DUELIST.TOLERANCE))
        self.assertIs(record['turn_owner'],h.p)
        self.assertEqual(DUELIST.method_multiplier(q),2)
        loaded=CODEC.load_engine(h.e.r,json.loads(json.dumps(CODEC.dump_engine(h.e))))
        old=next(a for a in loaded.everyone if a.entity_id==h.p.entity_id)
        holder=next(a for a in loaded.everyone if a.entity_id==q.entity_id)
        self.assertTrue(AB.active(holder,DUELIST.EXPLOIT))
        loaded.end_of_turn(old)
        self.assertFalse([row for row in TIME.records(holder) if row.get('duelist_mode')==1])
        self.assertTrue(AB.active(holder,DUELIST.TOLERANCE));self.assertFalse(AB.active(holder,DUELIST.EXPLOIT))
        self.assertTrue(loaded.validate_state()['valid'])

    def test_manual2_next_attack_is_consumed_once_and_cannot_return_on_second_baton(self):
        h,q=self.fixture(2)
        original=next(row['duelist_use'] for row in TIME.records(q) if row.get('duelist_mode')==2)
        h.e.gm.set_move(q,'move/불태우기',reason='actual known qualifying area attack')
        h.e.gm.set_move(q,SWITCH.BATON,reason='actual known next Baton Pass')
        h.start(q);h.attack(actor=q,move='move/불태우기',area=True)
        self.assertFalse([row for row in TIME.records(q) if row.get('duelist_use')==original])
        h.start(q);SWITCH.select(h.e,q,h.p,reason='actual second Baton recipient')
        h.e.use_move(q,q,SWITCH.BATON)
        self.assertFalse([row for row in TIME.records(h.p) if row.get('duelist_use')==original])
        self.assertTrue(h.e.validate_state()['valid'])


class NativeGuideTagHandoffRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')

    def test_actual_standard_tag_switch_preserves_urban_guide_until_original_count(self):
        import test_book_survivalist_guide as GUIDE_TEST
        import book_survivalist_fixture as FIX
        import survivalist_class as GUIDE
        from builder import build_pokemon
        h=GUIDE_TEST.SurvivalistGuideTests();h.rules=self.rules;h.setUp();self.addCleanup(h.doCleanups)
        e=Engine(self.rules,seed=11);e.grid=Grid(12,8)
        trainer=Combatant(self.rules,FIX.trainer_spec(self.rules,'survivalist juggler',
            classes=[SWITCH.CLASS],feats=['feat/퀵-스위치',SWITCH.ROUND_TRIP,SWITCH.TAG_IN],skills={'곡예':5}))
        e.gm.add_combatant(trainer,pos=(2,2),side='party',reason='actual initial Juggler source declaration')
        outgoing=Combatant(self.rules,FIX.pokemon_spec(self.rules,trainer,'partner'))
        e.gm.add_combatant(outgoing,pos=(3,2),side='party',reason='actual owned Guide recipient')
        for source in FIX.CORE_FEATURES:FIX.acquire(e,trainer,source)
        for actor in (trainer,outgoing):FIX.env(e,actor,'urban')
        reserve=Combatant(self.rules,build_pokemon(self.rules,'이브이',20,name='actual Guide reserve',moves=[],abilities=[],
            extra={'trainer_id':trainer.entity_id,'trainer':trainer.name}))
        e.gm.add_combatant(reserve,pos=(6,6),side='party',reason='actual reserve participant')
        e.gm.recall(reserve,reason='actual reserve before encounter')
        e.configure_party_combat(trainer,battle_mode='league',reason='actual Standard party switch')
        FIX.battle(e,trainer);h.guide(e,trainer,'urban')
        original=next(row for row in TIME.records(outgoing) if row.get('source')==GUIDE.GUIDE)
        deadline=tuple(original['count_deadline'])
        e.end_of_turn(trainer);e.end_round();e.start_round(e.everyone);e.start_of_turn(outgoing,initiative_count=30)
        result=e.act_on_party(trainer,recall=[outgoing],send=[(reserve,outgoing.pos)],tag_in=True,
            request_id='guide-tag-switch',reason='actual selected Tag In before recall cleanup')
        moved=next(row for row in TIME.records(reserve) if row.get('source')==GUIDE.GUIDE)
        self.assertEqual(result['payment']['funded'],{'standard':1})
        self.assertEqual((moved['evasion_modifier'],tuple(moved['count_deadline'])),(1,deadline))
        self.assertFalse([row for row in TIME.records(outgoing) if row.get('source')==GUIDE.GUIDE])
        e.end_of_turn(outgoing);e.at_initiative_count(20)
        self.assertFalse([row for row in TIME.records(reserve) if row.get('source')==GUIDE.GUIDE])
        self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
