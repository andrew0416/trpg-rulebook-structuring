"""Selected CSV status contracts on the existing native condition owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv,json,unittest
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import test_book_hex_maniac_full as HEX
import test_category2_dream_mist as MIST
import test_foundation_maneuvers_opposed as OPPOSED
import test_category3_pokemon_activities as CAPTURE
import test_category2_precise_threadings as THREAD
import condition_instances as CI,frequency as F,turn as TURN,state_codec as CODEC
import initiative as INIT,combat_maneuvers as MANEUVERS

ROOT=Path(__file__).resolve().parents[1]


class CsvConditionEditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv=Rules(ROOT,ruleset='core-csv-status-1.05')
        cls.default=Rules(ROOT,ruleset='core')

    def setUp(self):
        HEX.HexManiacTests.setup(self,self.csv)
        self.p=Combatant(self.r,build_pokemon(self.r,'이브이',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
        self.e.gm.add_combatant(self.p,pos=(4,2),side='party',reason='actual condition recipient')
        prepare_body(self.e,self.p,size='소형',offsets=[(0,0)],reason='actual Eevee condition body')
        self.e.gm.observe_loyalty(self.p,6,reason='actual trained participant')

    def teach(self,actor,mid):
        self.e.gm.set_move(actor,mid,True,reason='actual observed learned Move')

    def begin(self,actor,face=20,count=20):
        self.e.start_round(self.e.gm.everyone)
        with patch.object(Engine,'d20',return_value=face) as roller:
            self.e.start_of_turn(actor,initiative_count=count)
        return roller.call_count

    def restored(self):
        return CODEC.load_engine(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))

    def next_turn(self,actor,face=20):
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        if self.e.round_start_seconds is not None:self.e.end_round()
        self.begin(actor,face)

    def test_exact_logical_csv_rows_and_frozen_category2_scope(self):
        with (ROOT/'input/db/tm.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
        status=json.loads((ROOT/'data/verification/category2-tabular-core-status.json').read_text(encoding='utf8'))
        for number,name in ((73,'마비'),(78,'혼란'),(83,'풀죽음'),(85,'헤롱헤롱'),(88,'억압')):
            row=next(row for row in status['entries'] if row['id']==f'C2TAB/tm/r{number:03}c4-5')
            self.assertEqual((rows[number-1][3],rows[number-1][4]),(name,row['statement']))
            self.assertIs(row['include_category2'],True);self.assertEqual(row['denominator_contribution'],1)
            self.assertEqual(row['deduplication_status'],'independent-state-source-contract')

    def test_selected_versions_do_not_replace_current_default_effects(self):
        for name in CI.CSV_REVIEWED:
            self.assertTrue(CI.csv_edition(self.csv,name))
            self.assertFalse(CI.csv_edition(self.default,name))
        self.assertEqual(self.default.mech('condition/혼란')['_version'],'core-1.05')
        self.assertEqual(self.csv.mech('condition/혼란')['_version'],'core-1.05')
        self.assertEqual(self.default.condition_effects('마비')[0]['multiplier'],0.5)
        self.assertEqual(self.default.condition_effects('헤롱헤롱')[-1]['timing'],'end_of_turn')

    def test_actual_thunder_wave_stage_save_costs_and_exact_cure_both_kinds(self):
        for role in ('a','p'):
            with self.subTest(role=role):
                self.setUp();actor=getattr(self,role)
                self.e.gm.set_stage(actor,'spe',value=3)
                self.teach(self.b,'move/전기자석파');self.begin(self.b,count=30)
                with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.b,actor,'move/전기자석파')
                self.assertIn('마비',actor.conditions);self.assertEqual(actor.stages['spe'],-1)
                self.assertEqual(INIT.value(self.r,actor,engine=self.e).value,actor.staged('spe'))
                self.e.end_of_turn(self.b)
                with patch.object(Engine,'d20',return_value=4):self.e.start_of_turn(actor,initiative_count=20)
                before=deepcopy((actor.budget,self.e.rng.getstate()))
                for kind in ('standard','shift','swift','full'):self.assertFalse(TURN.spend(self.e,actor,kind))
                self.assertEqual((actor.budget,self.e.rng.getstate()),before)
                self.assertTrue(TURN.spend(self.e,actor,'free'));self.assertTrue(TURN.spend(self.e,actor,'free'))
                loaded=self.restored();clone=next(c for c in loaded.gm.everyone if c.entity_id==actor.entity_id)
                self.assertFalse(TURN.spend(loaded,clone,'standard'))
                self.e.cure_status(actor,'마비');self.assertEqual(actor.stages['spe'],3)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_paralysis_dc5_success_is_not_cure_and_electric_immunity_is_pokemon(self):
        self.e.gm.set_types(self.p,['전기'],reason='actual Electric Pokemon')
        self.assertFalse(self.e.apply_status(self.p,'마비'))
        self.e.gm.set_types(self.a,['전기'],reason='actual typed Trainer')
        self.assertTrue(self.e.apply_status(self.a,'마비'));self.assertEqual(self.begin(self.a,5),1)
        self.assertTrue(TURN.spend(self.e,self.a,'standard'));self.assertTrue(TURN.spend(self.e,self.a,'shift'))
        with patch.object(Engine,'d20',return_value=20) as roller:self.e.end_of_turn(self.a)
        self.assertEqual(roller.call_count,0);self.assertIn('마비',self.a.conditions)

    def test_csv_action_loss_still_produces_existing_burn_tick(self):
        self.e.apply_status(self.a,'마비');self.e.apply_status(self.a,'화상');self.begin(self.a,4)
        hp=self.a.hp;self.e.end_of_turn(self.a)
        self.assertEqual(hp-self.a.hp,self.e.tick_loss(self.a))

    def test_actual_headbutt_blocks_next_turn_only_without_modern_derivatives(self):
        self.teach(self.a,'move/박치기');self.begin(self.a,count=30)
        before=INIT.value(self.r,self.b,engine=self.e).value
        with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.b,'move/박치기',set_damage=True)
        self.assertTrue(CI.records(self.b,'풀죽음'));self.assertNotIn('취약',self.b.conditions)
        self.assertEqual(INIT.value(self.r,self.b,engine=self.e).value,before)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=20)
        for kind in ('standard','shift','swift','full','free'):self.assertFalse(TURN.spend(self.e,self.b,kind))
        self.e.gm.snapshot('csv-flinch')
        loaded=self.restored();clone=next(c for c in loaded.gm.everyone if c.entity_id==self.b.entity_id)
        self.assertFalse(TURN.spend(loaded,clone,'free'));loaded.end_of_turn(clone)
        self.assertFalse(CI.flinch_blocks(clone));loaded.end_round();self.assertNotIn('풀죽음',clone.conditions)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_flinch_applied_after_own_turn_start_does_not_steal_current_or_next_round(self):
        self.begin(self.a);self.e.apply_status(self.a,'풀죽음',source='move/박치기',applied_by=self.b)
        self.assertTrue(TURN.spend(self.e,self.a,'standard'))
        self.e.end_of_turn(self.a);self.e.end_round();self.assertNotIn('풀죽음',self.a.conditions)
        self.begin(self.a);self.assertTrue(TURN.spend(self.e,self.a,'standard'))

    def test_historical_default_noncombat_flinch_hash_and_codec_remain_valid(self):
        HEX.HexManiacTests.setup(self,self.default)
        self.e.apply_status(self.a,'풀죽음',source='move/박치기',applied_by=self.b)
        row=CI.records(self.a,'풀죽음')[0]
        self.assertEqual(row['noncombat_flinch']['definition_sha256'],'de51fdd98ee786516e07d1062fa2bbce9bd2d3ba34b658c7b9ab6ca01b1d7925')
        self.assertIn('취약',self.a.conditions);self.assertTrue(self.e.validate_state()['valid'])
        self.assertTrue(self.restored().validate_state()['valid'])

    def test_infatuation_all_bands_actual_source_target_and_unrelated_move_both_kinds(self):
        for role in ('a','p'):
            for face in (1,10,11,18,19,20):
                with self.subTest(role=role,face=face):
                    self.setUp();actor=getattr(self,role);self.teach(actor,'move/염동력')
                    self.e.apply_status(actor,'헤롱헤롱',source='move/헤롱헤롱',applied_by=self.b)
                    self.assertEqual(self.begin(actor,face),1)
                    self.assertEqual('헤롱헤롱' in actor.conditions,face<19)
                    if face<=10:
                        assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,self.b,'move/염동력'),reason_pattern='CSV Infatuation')
                        target=self.c
                    else:target=self.b
                    with patch.object(Engine,'d20',return_value=20):self.e.use_move(actor,target,'move/염동력',set_damage=True)
                    self.assertEqual(actor.budget['standard'],0)
                    self.assertEqual(MANEUVERS.infatuation_damage(actor,target,{'_actual_targets':(target,)},actor,30),(30,0))
                    with patch.object(Engine,'d20',return_value=20) as roller:self.e.end_of_turn(actor)
                    self.assertEqual(roller.call_count,0)

    def test_infatuation_save_adjustment_sleep_and_both_restores_preserve_actual_relation(self):
        self.e.apply_status(self.a,'헤롱헤롱',applied_by=self.b);self.a.save_mod=1
        self.begin(self.a,10)
        self.assertEqual(CI.records(self.a,'헤롱헤롱')[0]['csv_start_save']['value'],11)
        self.e.gm.snapshot('csv-infatuation');loaded=self.restored()
        index={c.entity_id:c for c in loaded.gm.everyone}
        row=CI.records(index[self.a.entity_id],'헤롱헤롱')[0]
        self.assertIs(row['beloved'],index[self.b.entity_id]);self.assertTrue(loaded.validate_state()['valid'])
        self.e.end_of_turn(self.a);self.e.end_round();self.e.apply_status(self.a,'잠듦');self.assertEqual(self.begin(self.a,1),0)
        self.e.cure_status(self.a,'잠듦');self.e.cure_status(self.a,'헤롱헤롱');self.e.gm.restore('csv-infatuation')
        self.assertEqual(CI.records(self.a,'헤롱헤롱')[0]['csv_start_save']['value'],11)

    def test_infatuation_actual_item_attack_rejects_before_stock_or_cost(self):
        f=MIST.Tests();f.r=self.csv;f.setUp()
        f.e.apply_status(f.a,'헤롱헤롱',applied_by=f.t)
        with patch.object(Engine,'d20',return_value=1):f.prepare()
        assert_rejected_unchanged(f.e,lambda:f.use(accepted=False),reason_pattern='CSV Infatuation')

    def test_infatuation_actual_automatic_maneuver_rejects_before_cost_and_skill(self):
        f=OPPOSED.OpposedTests();f.r=self.csv;f.setUp();f.grant()
        f.e.apply_status(f.a,'헤롱헤롱',applied_by=f.b);f.e.end_of_turn(f.a);f.e.end_round();f.e.start_round(f.e.everyone)
        with patch.object(Engine,'d20',return_value=1):f.e.start_of_turn(f.a,initiative_count=20)
        assert_rejected_unchanged(f.e,lambda:f.run_maneuver(f.policy(1)),reason_pattern='CSV Infatuation')

    def test_infatuation_actual_capture_rejects_before_ball_and_roll(self):
        f=CAPTURE.PokemonActivityTests();f.rules=self.csv;f.setUp();f.e.everyone=f.e.gm.everyone
        f.a.spec['items']['몬스터볼']=2;f.e.apply_status(f.a,'헤롱헤롱',applied_by=f.p)
        f.e.start_round(f.e.everyone)
        with patch.object(Engine,'d20',return_value=1):f.e.start_of_turn(f.a,initiative_count=20)
        assert_rejected_unchanged(f.e,lambda:f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20),reason_pattern='CSV Infatuation')

    def test_infatuation_threaded_attack_is_blocked_but_willing_movement_is_not(self):
        f=THREAD.PreciseThreadingsTests();f.r=self.csv;f.setUp();f.e.apply_status(f.p,'헤롱헤롱',applied_by=f.t)
        with patch.object(Engine,'d20',return_value=1):f.round()
        assert_rejected_unchanged(f.e,lambda:f.use(willing=False,fixed_accuracy=20),reason_pattern='CSV Infatuation')
        self.assertTrue(f.use(willing=True)['hit'])

    def test_suppression_actual_pp_up_is_suspended_not_erased_and_frequency_bands(self):
        for role in ('a','p'):
            with self.subTest(role=role):
                self.setUp();actor=getattr(self,role)
                self.teach(actor,'move/화염방사')
                if role=='p':
                    self.a.spec.setdefault('items',{})['item/pp업']=1
                    self.assertEqual(self.e.use_item(self.a,'item/pp업',actor,selected_move='move/화염방사'),(1,0))
                original=deepcopy(actor.spec.get('vitamin_special_uses',{}))
                baseline=('at_will',1) if role=='p' else ('every_other_turn',1)
                self.assertEqual(F.move_frequency(self.e,'move/화염방사',actor),baseline)
                self.e.apply_status(actor,'억압',applied_by=self.b)
                for mid,expected in (('move/몸통박치기',('every_other_turn',1)),('move/화염방사',('scene',1)),('move/하이퍼보이스',('scene',1)),('move/코튼가드',('scene',1)),('move/파괴광선',('daily',2))):
                    self.assertEqual(F.move_frequency(self.e,mid,actor),expected)
                self.assertEqual(actor.spec.get('vitamin_special_uses',{}),original)
                self.e.cure_status(actor,'억압');self.assertEqual(F.move_frequency(self.e,'move/화염방사',actor),baseline)

    def test_suppression_native_usage_intervals_scene_limit_codec_and_volatile_end(self):
        for mid in ('move/몸통박치기','move/방어지령','move/나비춤'):
            with self.subTest(mid=mid):
                self.setUp();self.teach(self.a,mid);self.e.apply_status(self.a,'억압',applied_by=self.b);self.begin(self.a)
                target=self.b if mid=='move/몸통박치기' else self.a
                with patch.object(Engine,'d20',return_value=20):self.e.use_move(self.a,target,mid,set_damage=True)
                self.assertEqual(self.a.move_uses[mid],1)
                self.next_turn(self.a);before=deepcopy((self.a.budget,self.a.move_uses,self.e.rng.getstate()))
                self.e.use_move(self.a,target,mid);self.assertEqual((self.a.budget,self.a.move_uses,self.e.rng.getstate()),before)
                loaded=self.restored();clone=next(c for c in loaded.gm.everyone if c.entity_id==self.a.entity_id)
                self.assertIn('억압',clone.conditions);self.assertFalse(F.move_allowed(loaded,clone,mid)[0])
                self.next_turn(self.a)
                if mid=='move/몸통박치기':self.assertTrue(F.move_allowed(self.e,self.a,mid)[0])
                else:self.assertFalse(F.move_allowed(self.e,self.a,mid)[0])
                self.e.end_of_turn(self.a);self.e.end_encounter();self.assertNotIn('억압',self.a.conditions)
                self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
