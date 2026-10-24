"""Observed manual/scheduled boundaries and explicit established Order signals."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import action_points as AP
import perception_communicate as COMM
import priority_limited as PRIORITY
import state_codec as CODEC
import world_entities as WORLD


class OrderTimingSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=Rules(ROOT,ruleset='core')
        cls.all=Rules(ROOT,ruleset='all')

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def restore(self,e):
        loaded=CODEC.load_engine(e.r,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)))
        self.valid(loaded);return loaded,WORLD.actor_index(loaded)

    def reject(self,e,fn,pattern):
        return assert_rejected_unchanged(e,fn,reason_pattern=pattern)

    def signal(self,e,a,p,source):
        import moment_of_action as MOMENT
        signal_source=MOMENT.TRAINING
        self.assertNotEqual(signal_source,source)
        e.gm.observe_sensory_environment(a,p,paths={'auditory':False,'visual':True},present=True,
                                       reason='actual established visual signals; speech blocked')
        request='signals:'+source+':'+a.entity_id+':'+p.entity_id
        policy={'id':request,'source':signal_source,'capabilities':[],'requirements':[],
                'mode':'visual','range':None,'path':'visual','medium':[],'consent':{'kind':'none'},
                'blockers':[],'connection':None,'frequency':{'kind':'at_will','uses':1},
                'retry':None,'distance_exceptions':[]}
        result=COMM.send(e,a,p,policy,'actual established Order signals',request_id=request)
        self.assertEqual(result['status'],'delivered')
        return request

    def training(self):
        import test_category2_training_orders_csv as FIX
        f=FIX.TrainingOrdersCSVTests();f.r=self.core
        return f,f.fixture()

    def test_manual_order_needs_observed_count_or_real_current_round_closure(self):
        import training_features as TRAIN
        for boundary in ('fresh','count','closure'):
            with self.subTest(boundary=boundary):
                f,(e,a,p,foe)=self.training();e.begin_encounter(e.everyone);f.audible(e,a,p)
                self.assertIsNone(getattr(e,'_initiative_schedule',None))
                self.reject(e,lambda:e.manual_feat(a,TRAIN.FOCUSED,p),'open combat round')
                e.start_round(e.everyone)
                if boundary=='count':e.at_initiative_count(30)
                elif boundary=='closure':e.start_of_turn(foe);e.end_of_turn(foe)
                e.manual_feat(a,TRAIN.FOCUSED,p)
                self.assertEqual(a.pending_action_loss,{'standard':1});self.valid(e)

    def test_prepared_schedule_admits_only_actual_current_unacted_slot(self):
        import training_features as TRAIN
        f,(e,a,p,foe)=self.training();f.audible(e,a,p)
        prepared=e.prepare_initiative_schedule(e.everyone,source='gm/order-review',
            order_groups=[[c.entity_id] for c in e.everyone])
        self.assertEqual(prepared['status'],'prepared');e.start_round(e.everyone)
        e.manual_feat(a,TRAIN.FOCUSED,p)
        self.assertEqual(a.pending_action_loss,{'standard':1});self.valid(e)
        loaded,index=self.restore(e);owner=index[a.entity_id]
        loaded.start_of_turn(owner)
        self.assertEqual(owner.budget,{'standard':0,'shift':1,'swift':1})
        self.assertEqual(PRIORITY.records(owner)[-1]['payment']['phase'],'paid')
        loaded.end_of_turn(owner)
        self.reject(loaded,lambda:loaded.manual_feat(owner,TRAIN.BRUTAL,index[p.entity_id]),'already taken')

    def test_training_signal_requires_actual_current_endpoints_and_routes_then_restores(self):
        import training_features as TRAIN
        f,(e,a,p,foe)=self.training();e.start_round(e.everyone);e.at_initiative_count(30)
        request=self.signal(e,a,p,TRAIN.FOCUSED)
        signal_source=COMM._state(e)['requests'][request]['result']['source']
        self.assertNotEqual(signal_source,TRAIN.FOCUSED)
        self.assertEqual(COMM._state(e)['policies'][signal_source]['declaration']['mode'],'visual')
        use=lambda chosen:e.manual_feat(a,TRAIN.FOCUSED,p,communication=chosen)
        self.reject(e,lambda:use('invented'),'established communication')
        wrong=self.signal(e,a,foe,TRAIN.FOCUSED)
        self.reject(e,lambda:use(wrong),'communication')
        e.gm.observe_sensory_environment(a,p,paths={'auditory':False,'visual':False},present=True,reason='signals now obstructed')
        self.reject(e,lambda:use(request),'communication')
        e.gm.observe_sensory_environment(a,p,paths={'auditory':False,'visual':True},present=True,reason='signals now visible')
        self.reject(e,lambda:e.manual_feat(a,TRAIN.FOCUSED,p),'not delivered')
        before=set(COMM._state(e)['requests']);out=use(request)
        created=set(COMM._state(e)['requests'])-before;self.assertEqual(len(created),1)
        actual=COMM._state(e)['requests'][next(iter(created))]['result']
        self.assertEqual(actual,out['communication']);self.assertEqual(actual['recipient_id'],p.entity_id)
        self.valid(e);self.restore(e)
        COMM._state(e)['requests'][next(iter(created))]['result']['message']='tampered delivery'
        with self.assertRaises(ValueError):COMM.validate_world(e,WORLD.actor_index(e))
        f,(e,a,p,_)=self.training()
        old=self.signal(e,a,p,TRAIN.FOCUSED);e.advance_time(1)
        e.start_round(e.everyone);e.at_initiative_count(30)
        self.reject(e,lambda:e.manual_feat(a,TRAIN.FOCUSED,p,communication=old),'communication')

    def test_type_ace_celerity_both_routes_signal_cheer_bound_ap_and_restore(self):
        import test_book_type_ace_actions as FIX,type_ace as TYPE
        import moment_of_action as MOMENT,trainer_feature_acquisition as ACQUIRE,cheerleader as CHEER
        for own in (False,True):
            with self.subTest(own_turn=own):
                f=FIX.TypeAceActionsTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
                f.branch('비행','Celerity');e,a,p=f.e,f.t,f.p
                for feature in (MOMENT.TRAINING,MOMENT.CLASS):
                    ACQUIRE.acquire_static(e,a,feature,acquisition_request_id='celerity/'+feature)
                f.answer('cheerleader','Cheered');e.start_round(e.everyone);e.at_initiative_count(30)
                if own:e.start_of_turn(a,initiative_count=30)
                feature=TYPE.uid('Celerity');request=self.signal(e,a,p,feature);before=AP.available(a)
                self.reject(e,lambda:TYPE.activate(e,a,p,feature),'communication')
                row=TYPE.activate(e,a,p,feature,communication=request)
                self.assertEqual(AP.available(a),before-2);self.assertEqual(a.spec['ap_bound'][row['instance']],2)
                self.assertEqual(len(CHEER.live(p,'Cheered')),1)
                self.assertEqual(CHEER._uses(a)[-1]['origin']['source'],feature)
                if own:self.assertEqual(a.budget['standard'],0);self.assertFalse(PRIORITY.records(a))
                else:self.assertEqual(a.pending_action_loss,{'standard':1})
                self.valid(e);self.restore(e)

    def test_type_ace_adopted_free_stratagem_keeps_actual_free_cost(self):
        import test_book_type_ace_actions as FIX,type_ace as TYPE
        for name in ('Unconquerable','Fey Trance','Desert Heart'):
            with self.subTest(feature=name):
                feature=TYPE.uid(name);definition=TYPE.DEFINITIONS[feature]
                f=FIX.TypeAceActionsTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
                f.branch(definition['branch'],definition['parent'],feature);e,a,p=f.e,f.t,f.p
                self.assertEqual(definition['action'],'free')
                e.start_round(e.everyone);e.start_of_turn(f.b,initiative_count=30)
                request=self.signal(e,a,p,feature);before=AP.available(a)
                TYPE.activate(e,a,p,feature,communication=request)
                self.assertEqual(AP.available(a),before-2);self.assertFalse(PRIORITY.records(a))
                self.assertEqual(a._action_history[-1],'free');self.assertIs(e._active_turn_actor,f.b)
                self.valid(e)

    def test_type_refresh_between_turns_has_actual_source_and_cheer_consumer(self):
        import test_book_type_ace_acquisition as FIX,type_ace as TYPE
        import moment_of_action as MOMENT,trainer_feature_acquisition as ACQUIRE,cheerleader as CHEER
        f=FIX.TypeAceAcquisitionTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.acquire();f.acquire(TYPE.REFRESH);e,a,p=f.e,f.t,f.p
        for feature in (MOMENT.TRAINING,MOMENT.CLASS):
            ACQUIRE.acquire_static(e,a,feature,acquisition_request_id='refresh/'+feature)
        e.rulings.add_answer('cheerleader','Motivated',reason='actual choice',scope='permanent')
        e.gm.set_move(p,'move/불대문자',reason='actual selected Scene Move')
        f.combat(p);f.use('move/불대문자');e.end_of_turn(p)
        self.assertGreater(p.move_uses['move/불대문자'],0)
        request=self.signal(e,a,p,TYPE.REFRESH);before=AP.available(a)
        self.assertTrue(TYPE.refresh(e,a,p,'불꽃','move/불대문자',communication=request))
        self.assertEqual((p.move_uses['move/불대문자'],AP.available(a)),(0,before-2))
        self.assertEqual(a.pending_action_loss,{'standard':1});self.assertEqual(len(CHEER.live(p,'Motivated')),1)
        self.valid(e);self.restore(e)

    def test_class_stratagem_and_pinpoint_public_facades_pass_established_signal(self):
        import test_category2_class_passive_combat_bulk as CLASS_FIX,class_passive_combat as CLASS
        import test_category3_combat_precision as PIN_FIX,combat_precision_features as PIN
        f=CLASS_FIX.ClassPassiveCombatBulkTests();f.rules=self.all
        e,a,p,_=f.fixture(feats=[CLASS.CAPRICIOUS]);e.start_round(e.everyone);e.at_initiative_count(30)
        request=self.signal(e,a,p,CLASS.CAPRICIOUS)
        self.assertEqual(e.activate_class_passive(a,p,CLASS.CAPRICIOUS,communication=request),(1,0));self.valid(e)
        f=PIN_FIX.CombatPrecisionTests();f.r=self.all;f.setUp();e,a,p=f.e,f.a,f.p
        for c in e.everyone:c.moves=c.moves[:6];c.spec['moves']=c.moves[:]
        e.start_round(e.everyone);e.at_initiative_count(30);request=self.signal(e,a,p,PIN.PINPOINT)
        self.assertEqual(e.manual_feat(a,PIN.PINPOINT,p,communication=request),(1,0));self.valid(e)

    def test_director_public_facade_and_stat_stratagem_pass_established_signal(self):
        import test_category2_directive_features as DIRECT_FIX,directive_features as DIRECT
        import test_book_stat_ace_full as STAT_FIX,stat_ace as STAT
        f=DIRECT_FIX.DirectiveFeatureTests();f.r=self.core;f.setUp();e,a,p=f.e,f.a,f.b
        request=self.signal(e,a,p,DIRECT.FEATURE)
        self.assertEqual(e.use_decisive_director(a,p,adjustment='increase',communication=request)['delta'],6);self.valid(e)
        f=STAT_FIX.StatAceTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.family('atk',stratagem=True);e,a,p=f.e,f.a,f.p;e.start_round(e.everyone);e.at_initiative_count(30)
        request=self.signal(e,a,p,STAT.STRATAGEM)
        self.assertEqual(STAT.activate(e,a,p,'atk',communication=request),(1,0));self.valid(e)

    def test_chronicler_and_dress_native_adapters_pass_established_signal(self):
        import test_book_chronicler_actions as CH_FIX,chronicler as CH
        import test_book_fashionista_wardrobe as FA_FIX,fashionista as FA
        f=CH_FIX.ChroniclerActionTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.whole();e,a,p=f.e,f.t,f.p;e.start_round(e.everyone);e.at_initiative_count(30)
        request=self.signal(e,a,p,CH.PROFILING);CH.profile_order(e,a,p,communication=request);self.valid(e)
        f=FA_FIX.FashionistaWardrobeTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.stocked();e,a,p=f.e,f.t,f.p;e.start_round(e.everyone);e.at_initiative_count(30)
        request=self.signal(e,a,p,FA.DRESS);FA.dress_to_impress(e,a,p,communication=request);self.valid(e)

    def test_guide_and_errata_cheer_group_requests_are_explicit_and_target_exact(self):
        import book_survivalist_fixture as GUIDE_FIX,survivalist_class as GUIDE
        import test_category2_optional_state_effect_eight as ERRATA_FIX
        world=GUIDE_FIX.scene(self.core,ally=True);e,a,p,b=world['engine'],world['trainer'],world['partner'],world['ally']
        GUIDE_FIX.env(e,a,'forest');e.start_round(e.everyone);e.at_initiative_count(30)
        requests={target.entity_id:self.signal(e,a,target,GUIDE.GUIDE) for target in (p,b)}
        use=lambda mapping:e.survivalist_activity(a,'wilderness_guide',terrain_name='forest',reason='observed terrain',communication=mapping)
        self.reject(e,lambda:use({}),'per-ally');use(requests);self.valid(e)
        f=ERRATA_FIX.OptionalStateEffectEightTests();f.rules=self.all;e,a,p,b,_=f.fixture('feat/응원-문구-1')
        requests={target.entity_id:self.signal(e,a,target,'feat/응원-문구-1') for target in (p,b)}
        e.activate_optional_state_effect(a,'ERRATA-056',choice='temp_hp',communication=requests)
        self.assertEqual((p.temp_hp,b.temp_hp),(4,4));self.valid(e);self.restore(e)

    def test_duelist_both_native_order_adapters_pass_established_signal(self):
        import test_book_duelist_momentum as FIX,duelist as DUELIST
        for feature in (DUELIST.EXPEND,DUELIST.MANUAL):
            with self.subTest(feature=feature):
                f=FIX.DuelistMomentumTests();f.rules=self.all;f.setup();f.rounds(3)
                e,a,p=f.e,f.a,f.p;e.at_initiative_count(30)
                request=self.signal(e,a,p,feature)
                options={'amount':2} if feature==DUELIST.EXPEND else {'mode':2}
                row=e.manual_feat(a,feature,p,adjustment=options,communication=request)
                self.assertEqual(row['communication']['result']['status'],'delivered')
                self.assertEqual(a.pending_action_loss,{'standard':1});self.valid(e);self.restore(e)

    def test_book_cheer_own_turn_keeps_compound_cost_with_established_group_signals(self):
        import test_book_go_fight_win as FIX,go_fight_win as GO
        f=FIX.GoFightWinTests();f.rules=self.core;f.setup();e,a=f.e,f.a
        e.start_of_turn(a,initiative_count=20)
        requests={target.entity_id:self.signal(e,a,target,GO.FEATURE) for target in (f.b,f.c)}
        row=f.use('temp_hp',communication=requests)
        self.assertEqual(row['payment'],{'kind':'compound','components':['standard','swift']})
        self.assertEqual(a.budget,{'standard':0,'shift':1,'swift':0});self.assertFalse(PRIORITY.records(a))
        self.valid(e);self.restore(e)

    def unavailable(self,e,p,state):
        if state=='fainted':e.gm.set_hp(p,value=0,reason='actual current recipient fainting')
        elif state=='off_field':e.gm.recall(p,reason='actual current recipient withdrawal')
        elif state=='captured':
            # Native current-state fixture, as in test_category2_priority_independent.
            p.captured=True
        elif state!='outside_encounter':raise AssertionError(state)

    def test_chronicler_established_signal_rechecks_current_recipient_eligibility(self):
        import test_book_chronicler_actions as FIX,chronicler as CH
        for state in ('fainted','captured','off_field','outside_encounter'):
            with self.subTest(state=state):
                f=FIX.ChroniclerActionTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
                f.whole();e,a,p=f.e,f.t,f.p
                if state!='outside_encounter':e.start_round(e.everyone);e.at_initiative_count(30)
                request=self.signal(e,a,p,CH.PROFILING)
                self.unavailable(e,p,state)
                self.reject(e,lambda:CH.profile_order(e,a,p,communication=request),'available actual Order recipient')
                self.assertIsNone(CH.profiling_record(p));self.assertFalse(PRIORITY.records(a))

    def test_type_refresh_established_signal_rechecks_current_recipient_eligibility(self):
        import test_book_type_ace_acquisition as FIX,type_ace as TYPE,frequency as FREQUENCY
        for state in ('fainted','captured','off_field','outside_encounter'):
            with self.subTest(state=state):
                f=FIX.TypeAceAcquisitionTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
                f.acquire();f.acquire(TYPE.REFRESH);e,a,p=f.e,f.t,f.p
                e.gm.set_move(p,'move/불대문자',reason='actual known matching Scene Move')
                if state!='outside_encounter':e.start_round(e.everyone);e.at_initiative_count(30)
                request=self.signal(e,a,p,TYPE.REFRESH)
                self.unavailable(e,p,state)
                self.reject(e,lambda:TYPE.refresh(e,a,p,'불꽃','move/불대문자',communication=request),'available actual Order recipient')
                self.assertFalse(PRIORITY.records(a))
                self.assertTrue(FREQUENCY.activation_allowed(p,TYPE.REFRESH,{'kind':'scene','uses':1},engine=e))


if __name__=='__main__':unittest.main()
