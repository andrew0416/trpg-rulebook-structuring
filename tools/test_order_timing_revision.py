"""Source-specific Order entry regressions; fixture classes are not re-collected."""
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
import priority_limited as PRIORITY
import state_codec as CODEC
import turn as TURN


class OrderTimingRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=Rules(ROOT,ruleset='core')
        cls.all=Rules(ROOT,ruleset='all')

    def audible(self,e,a,p,allowed=True):
        e.gm.observe_sensory_environment(a,p,paths={'auditory':allowed},present=True,
                                       reason='observed actual Order communication')

    def rejected(self,e,fn,pattern):
        return assert_rejected_unchanged(e,fn,reason_pattern=pattern)

    def valid(self,e):
        result=e.validate_state()
        self.assertTrue(result['valid'],result['issues'])

    def restored(self,e):
        return CODEC.load_engine(e.r,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)))

    def debt(self,e,a,expected):
        self.assertEqual(a.pending_action_loss,expected)
        self.assertTrue(PRIORITY.validate(a))
        e.start_of_turn(a)
        self.assertEqual(a.budget,{kind:1-expected.get(kind,0) for kind in ('standard','shift','swift')})
        self.assertEqual(PRIORITY.records(a)[-1]['payment']['phase'],'paid')

    def test_training_each_ordinary_order_spends_standard_and_keeps_own_turn_expiry(self):
        import test_category2_training_orders_csv as FIX,training_features as TRAIN
        for source in TRAIN.RULES:
            with self.subTest(source=source):
                f=FIX.TrainingOrdersCSVTests();f.r=self.core
                e,a,p,_=f.fixture();f.open(e);f.audible(e,a,p);e.start_of_turn(a)
                out=e.manual_feat(a,source,p)
                self.assertEqual(out['priority_receipt']['payment']['kind'],'ordinary')
                self.assertEqual(a.budget,{'standard':0,'shift':1,'swift':1})
                self.assertFalse(PRIORITY.records(a))
                self.assertEqual(TRAIN.active(p)[0]['rule_id'],source)
                loaded=self.restored(e);self.valid(loaded)
                e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.at_initiative_count(30);e.start_of_turn(a)
                self.assertFalse(TRAIN.records(p))

    def test_training_ordinary_cheer_survives_order_expiry_and_restore(self):
        import test_book_cheerleader_bundle as FIX,training_features as TRAIN,cheerleader as CHEER
        f=FIX.CheerleaderBundleTests();f.rules=self.core;f.setup()
        e,a,p=f.e,f.a,f.p;e.start_of_turn(a)
        e.manual_feat(a,TRAIN.INSPIRED,p)
        self.assertEqual(len(CHEER.live(p)),1)
        e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.at_initiative_count(30);e.start_of_turn(a)
        self.assertFalse(TRAIN.records(p));self.assertEqual(len(CHEER.live(p)),1)
        self.valid(e);self.valid(self.restored(e))

    def test_scene_priority_features_have_no_order_delivery_gate_on_either_route(self):
        import test_category2_scene_feature_ability_grants as FIX,scene_feature_ability_grants as SCENE
        f=FIX.SceneFeatureAbilityGrantTests();f.rules=self.all
        f.policy=json.loads((ROOT/SCENE.POLICY).read_text(encoding='utf8'))
        for kind in ('stat','style'):
            for own_turn in (False,True):
                with self.subTest(kind=kind,own_turn=own_turn):
                    if kind=='stat':
                        e,a,p=f.stat_fixture('atk',authority='book');source=SCENE.STAT_FEATURE;branch='atk';ability='오기'
                    else:
                        e,a,targets=f.style_fixture();p=targets[0];source=SCENE.STYLE_FEATURE;branch='근사함';ability='스나이퍼'
                    self.audible(e,a,p,False);e.start_round(e.everyone);e.at_initiative_count(30)
                    if own_turn:e.start_of_turn(a)
                    before=AP.available(a)
                    out=e.activate_scene_feature_ability(a,p,source,branch,ability)
                    self.assertIsNone(out['communication']);self.assertEqual(AP.available(a),before-1)
                    if own_turn:
                        self.assertIsNone(out['priority_receipt']);self.assertEqual(a.budget,{'standard':1,'shift':1,'swift':0})
                    else:
                        self.assertIsNone(out['priority_receipt']['communication']);self.debt(e,a,{'swift':1})
                    self.valid(e);self.valid(self.restored(e))

    def test_all_five_class_stratagems_require_delivery_and_reserve_only_standard(self):
        import test_category2_class_passive_combat_bulk as FIX,class_passive_combat as CLASS
        f=FIX.ClassPassiveCombatBulkTests();f.rules=self.all
        for source in sorted(CLASS.STRATAGEMS):
            with self.subTest(source=source):
                e,a,p,_=f.fixture(feats=[source]);e.start_round(e.everyone);e.at_initiative_count(30)
                self.audible(e,a,p,False)
                self.rejected(e,lambda:e.activate_class_passive(a,p,source),'not delivered')
                self.audible(e,a,p);before=AP.available(a)
                self.assertEqual(e.activate_class_passive(a,p,source),(1,0))
                self.assertEqual(AP.available(a),before-2)
                self.assertEqual(PRIORITY.records(a)[-1]['source'],source)
                self.valid(self.restored(e));self.debt(e,a,{'standard':1})
                self.assertEqual(len(p.spec[CLASS.STATE]['sustains']),1)
                self.rejected(e,lambda:e.activate_class_passive(a,p,source),'Stratagem|stratagem')

    def test_pinpoint_book_and_csv_use_real_delivery_and_standard_debt(self):
        import test_category3_combat_precision as FIX,combat_precision_features as PIN,items
        for source in (PIN.PINPOINT,'C2CSV/input/db/feats.csv:R33:main'):
            with self.subTest(source=source):
                f=FIX.CombatPrecisionTests();f.r=self.all;f.setUp()
                e,a,p=f.e,f.a,f.p
                for actor in e.everyone:actor.moves=actor.moves[:6];actor.spec['moves']=actor.moves[:]
                if source!=PIN.PINPOINT:a.spec['feats'].append(source);items.register_feats(e,a)
                e.start_round(e.everyone);e.at_initiative_count(30);self.audible(e,a,p,False)
                self.rejected(e,lambda:e.manual_feat(a,source,p),'not delivered')
                self.audible(e,a,p);self.assertEqual(e.manual_feat(a,source,p),(1,0))
                self.assertEqual(PIN.binding(e,p)['source'],source)
                self.debt(e,a,{'standard':1});self.assertEqual(sum(a.spec['ap_bound'].values()),2)

    def test_stat_stratagem_cheer_and_priority_have_the_actual_source(self):
        import test_book_stat_ace_full as FIX,stat_ace as STAT
        import moment_of_action as MOMENT,trainer_feature_acquisition as ACQUIRE,cheerleader as CHEER
        f=FIX.StatAceTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.family('atk',stratagem=True);e,a,p=f.e,f.a,f.p
        e.gm.set_skill(a,'매력',3,reason='actual Novice Charm')
        for source in (MOMENT.TRAINING,MOMENT.CLASS):ACQUIRE.acquire_static(e,a,source,acquisition_request_id='order-review/'+source)
        f.answer('cheerleader','Cheered');self.audible(e,a,p);e.start_round(e.everyone);e.at_initiative_count(30)
        self.assertEqual(STAT.activate(e,a,p,'atk'),(1,0))
        self.assertEqual(len(CHEER.live(p)),1);self.assertEqual(CHEER._uses(a)[-1]['origin']['source'],STAT.STRATAGEM)
        self.valid(e);self.valid(self.restored(e));self.debt(e,a,{'standard':1})

    def test_chronicler_profile_order_keeps_two_ap_and_target_turn_scope_between_turns(self):
        import test_book_chronicler_actions as FIX,chronicler as CH
        f=FIX.ChroniclerActionTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.whole();f.archive_subject(f.b,'pokemon','order-review-profile');f.communication()
        e,a,p=f.e,f.t,f.p;e.start_round(e.everyone);e.at_initiative_count(30);before=AP.available(a)
        row=CH.profile_order(e,a,p)
        self.assertEqual(AP.available(a),before-2);self.assertEqual(row['active_serial'],1)
        self.assertIs(CH.profiling_record(p)['turn_owner'],p)
        self.valid(self.restored(e));self.debt(e,a,{'standard':1})

    def test_dress_priority_delivery_cheer_frequency_and_round_expiry(self):
        import test_book_fashionista_wardrobe as FIX,fashionista as FA,cheerleader as CHEER
        import moment_of_action as MOMENT,trainer_feature_acquisition as ACQUIRE
        f=FIX.FashionistaWardrobeTests();f.rules=self.core;f.setUp();self.addCleanup(f.doCleanups)
        f.stocked();e,a,p=f.e,f.t,f.p
        for source in (MOMENT.TRAINING,MOMENT.CLASS):ACQUIRE.acquire_static(e,a,source,acquisition_request_id='dress-review/'+source)
        e.rulings.add_answer('cheerleader','Motivated',reason='actual choice',scope='permanent')
        e.start_round(e.everyone);e.at_initiative_count(30);e.at_initiative_count(30)
        self.audible(e,a,p,False);self.rejected(e,lambda:FA.dress_to_impress(e,a,p),'not delivered')
        self.audible(e,a,p);row=FA.dress_to_impress(e,a,p)
        self.assertEqual(len(row['items']),2);self.assertEqual(len(CHEER.live(p,'Motivated')),1)
        self.valid(e);self.valid(self.restored(e));self.debt(e,a,{'standard':1})
        e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.at_initiative_count(30);e.at_initiative_count(30)
        self.assertIsNone(FA.dress_record(p))
        self.rejected(e,lambda:FA.dress_to_impress(e,a,p),'once per Scene')

    def test_guide_group_delivery_and_cheer_are_atomic_and_keep_count_deadline(self):
        import book_survivalist_fixture as FIX,survivalist_class as GUIDE,cheerleader as CHEER
        import moment_of_action as MOMENT,trainer_feature_acquisition as ACQUIRE
        world=FIX.scene(self.core,ally=True);e,a,p,b=world['engine'],world['trainer'],world['partner'],world['ally']
        FIX.env(e,a,'forest')
        for source in (MOMENT.TRAINING,MOMENT.CLASS):ACQUIRE.acquire_static(e,a,source,acquisition_request_id='guide-review/'+source)
        e.rulings.add_answer('cheerleader','Excited',reason='actual choice',scope='permanent')
        e.start_round(e.everyone);e.at_initiative_count(30);e.at_initiative_count(25)
        use=lambda:e.survivalist_activity(a,'wilderness_guide',terrain_name='forest',reason='actual current terrain')
        self.audible(e,a,b,False);self.rejected(e,use,'not delivered')
        self.audible(e,a,b);before=AP.available(a);row=use()
        self.assertEqual(AP.available(a),before-1);self.assertEqual(row['count'],25)
        for ally in (p,b):
            self.assertEqual(len(CHEER.live(ally,'Excited')),1)
            self.assertEqual(GUIDE._guide_rows(ally)[0]['count_deadline'],(e.round_no+1,25))
        self.assertFalse(CHEER.live(a));self.valid(e);self.valid(self.restored(e));self.debt(e,a,{'standard':1})

    def test_duelist_expend_and_manual_between_turns_keep_distinct_momentum_costs(self):
        import test_book_duelist_momentum as FIX,duelist as DUELIST
        for source in (DUELIST.EXPEND,DUELIST.MANUAL):
            with self.subTest(source=source):
                f=FIX.DuelistMomentumTests();f.rules=self.all;f.setup();f.rounds(3)
                e,a,p=f.e,f.a,f.p;before=DUELIST.momentum(p);ap=AP.available(a)
                options={'amount':2} if source==DUELIST.EXPEND else {'mode':2}
                row=e.manual_feat(a,source,p,adjustment=options)
                self.assertIn('priority_receipt_id',row)
                self.assertEqual(DUELIST.momentum(p),before-2 if source==DUELIST.EXPEND else before)
                self.assertEqual(AP.available(a),ap if source==DUELIST.EXPEND else ap-2)
                self.valid(e);self.valid(self.restored(e));self.debt(e,a,{'standard':1})

    def test_director_enemy_order_between_turns_requires_delivery_and_preserves_signed_rank(self):
        import test_category2_directive_features as FIX,directive_features as DIRECT
        f=FIX.DirectiveFeatureTests();f.r=self.core;f.setUp();e,a,p=f.e,f.a,f.b
        e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.at_initiative_count(30)
        self.audible(e,a,p,False);self.rejected(e,lambda:e.use_decisive_director(a,p,adjustment='decrease'),'not delivered')
        self.audible(e,a,p);before=e.initiative_value(p).value
        out=e.use_decisive_director(a,p,adjustment='decrease')
        self.assertEqual(out['delta'],-6);self.assertEqual(e.initiative_value(p).value,before-6)
        self.valid(e);self.valid(self.restored(e));self.debt(e,a,{'standard':1})
        self.assertEqual(DIRECT._effect(7,'increase')['delta'],14)
        self.assertEqual(DIRECT._effect(9,'decrease')['delta'],-18)

    def test_moment_own_turn_after_shift_keeps_actual_standard_and_allied_ap(self):
        import test_book_moment_of_action as FIX,temporary_ap as TEMP
        f=FIX.MomentOfActionTests();f.rules=self.core;f.setup();e,a=f.e,f.a
        e.start_of_turn(a);self.assertTrue(TURN.spend(e,a,'shift','actual nonmovement Shift'))
        row=f.use();self.assertEqual(row['payment'],{'kind':'standard','action':'standard'})
        self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':1});self.assertFalse(PRIORITY.records(a))
        self.assertEqual((TEMP.available(f.b),TEMP.available(f.c)),(1,1))
        self.valid(e);self.valid(self.restored(e))

    def test_go_fight_win_own_turn_compound_cost_and_failure_are_atomic(self):
        import test_book_go_fight_win as FIX,cheerleader as CHEER
        f=FIX.GoFightWinTests();f.rules=self.core;f.setup();e,a=f.e,f.a
        e.start_of_turn(a);self.assertTrue(TURN.spend(e,a,'shift','actual nonmovement Shift'))
        row=f.use('temp_hp')
        self.assertEqual(row['payment'],{'kind':'compound','components':['standard','swift']})
        self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':0});self.assertFalse(PRIORITY.records(a))
        self.assertEqual((f.b.temp_hp,f.c.temp_hp),(5,5));self.assertEqual(len(CHEER.live(f.b,'Excited')),1)
        self.valid(e);self.valid(self.restored(e));self.rejected(e,lambda:f.use('defense'),'Standard and Swift')

    def test_errata_go_fight_win_keeps_two_ap_standard_and_has_no_book_fixed_condition(self):
        import test_category2_optional_state_effect_eight as FIX,cheerleader as CHEER
        f=FIX.OptionalStateEffectEightTests();f.rules=self.all
        e,a,p,q,_=f.fixture('feat/응원-문구-1')
        e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.at_initiative_count(30)
        use=lambda:e.activate_optional_state_effect(a,'ERRATA-056',choice='temp_hp')
        self.audible(e,a,q,False);self.rejected(e,use,'not delivered')
        self.audible(e,a,q);before=AP.available(a);out=use()
        self.assertEqual(out['clause_id'],'ERRATA-056');self.assertEqual(AP.available(a),before-2)
        self.assertEqual((p.temp_hp,q.temp_hp),(4,4));self.assertFalse(CHEER.live(p))
        self.assertEqual(PRIORITY.records(a)[-1]['source'],'feat/응원-문구-1')
        self.valid(e);self.valid(self.restored(e));self.debt(e,a,{'standard':1})


if __name__=='__main__':unittest.main()
