"""The exact TM row113 Frozen differences use the existing native owners."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import csv,json,unittest
from engine import Rules,Engine
import test_csv_condition_editions as FIX
import turn as TURN,condition_recovery as RECOVERY,world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]


class CsvFrozenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv=Rules(ROOT,ruleset='core-csv-frozen-homebrew')
        cls.default=Rules(ROOT,ruleset='core')

    def setUp(self):
        original=self.csv.rulings;self.csv.rulings=deepcopy(original)
        self.addCleanup(setattr,self.csv,'rulings',original)
        FIX.CsvConditionEditionTests.setUp(self)

    begin=FIX.CsvConditionEditionTests.begin
    teach=FIX.CsvConditionEditionTests.teach
    restored=FIX.CsvConditionEditionTests.restored

    def attack(self,move,target=None,face=18):
        target=target or self.p
        self.teach(self.b,'move/'+move);self.begin(self.b)
        with patch.object(Engine,'d20',return_value=face):
            result=self.e.use_move(self.b,target,'move/'+move,set_damage=True)
        self.assertEqual(self.b.budget['standard'],0)
        return result

    def test_exact_csv_contract_and_both_explicit_selections(self):
        source=ROOT/'input/db/tm.csv'
        self.assertEqual(sha256(source.read_bytes()).hexdigest(),'dd06395776044c0c13e698420aead38907d6969f475caf8485ec2cd1a2259f44')
        with source.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
        registry=json.loads((ROOT/'data/verification/category2-tabular-core-status.json').read_text(encoding='utf8'))
        row=next(row for row in registry['entries'] if row['id']=='C2TAB/tm/r113c4-5')
        self.assertEqual(rows[112][3:5],[row['name'],row['statement']])
        self.assertIs(row['include_category2'],True);self.assertEqual(row['denominator_contribution'],1)
        self.assertEqual(row['deduplication_status'],'independent-state-source-contract')
        for rules,dc,fire,weather in ((self.default,16,11,{'쾌청':4,'싸라기눈':-2}),(self.csv,12,8,{'쾌청':2,'싸라기눈':-4})):
            effects=rules.condition_effects('얼음')
            self.assertEqual(next(e['dc'] for e in effects if e['type']=='save'),dc)
            self.assertEqual(next(e['dc'] for e in effects if e.get('if_type')=='불꽃'),fire)
            self.assertEqual(next(e['weather'] for e in effects if 'weather' in e),weather)
        self.assertEqual(self.csv.mech('condition/얼음')['_version'],'csv-homebrew')
        self.assertNotIn('_version',self.default.mech('condition/얼음'))

    def test_end_turn_dc_type_weather_boundaries_both_kinds_and_native_save_modifier(self):
        for role,types,base in (('a',['노말'],12),('a',['불꽃'],12),('p',['노말'],12),('p',['불꽃'],8)):
            for weather,mod in ((None,0),('sunny',2),('hail',-4)):
                for face in (base-mod-1,base-mod):
                    with self.subTest(role=role,types=types,weather=weather,face=face):
                        self.setUp();actor=getattr(self,role)
                        self.e.gm.set_types(actor,types,reason='actual Frozen type boundary')
                        self.e.apply_status(actor,'얼음');self.assertEqual(self.begin(actor),0)
                        self.e.gm.set_weather(weather,rounds=None,reason='actual Frozen save weather')
                        with patch.object(Engine,'d20',return_value=face) as roller:self.e.end_of_turn(actor)
                        self.assertEqual(roller.call_count,1)
                        self.assertEqual('얼음' in actor.conditions,face<base-mod)
                        self.assertTrue(self.e.validate_state()['valid'])
        self.setUp();self.e.apply_status(self.a,'얼음');self.begin(self.a)
        self.e.rulings.add_situational('dc',-2,who=self.a.name,uses=1,reason='actual sourced situational save adjustment')
        with patch.object(Engine,'d20',return_value=10):self.e.end_of_turn(self.a)
        self.assertNotIn('얼음',self.a.conditions)
        self.assertFalse(self.e.rulings.situational)

    def test_printed_default_weather_boundaries_use_the_native_sourced_weather(self):
        self.csv=self.default
        for weather,dc in ((None,16),('sunny',12),('hail',18)):
            for face in (dc-1,dc):
                with self.subTest(weather=weather,face=face):
                    self.setUp();self.e.apply_status(self.p,'얼음');self.begin(self.p)
                    self.e.gm.set_weather(weather,rounds=None,reason='actual printed Frozen weather control')
                    with patch.object(Engine,'d20',return_value=face):self.e.end_of_turn(self.p)
                    self.assertEqual('얼음' in self.p.conditions,face<dc)
                    self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_ice_beam_cost_immunity_actions_evasion_and_both_restores(self):
        for role in ('a','p'):
            with self.subTest(role=role):
                self.setUp();actor=getattr(self,role)
                self.attack('냉동빔',actor,face=20)
                self.assertIn('얼음',actor.conditions);self.assertEqual(self.b.move_uses['move/냉동빔'],1)
                self.e.end_of_turn(self.b)
                with patch.object(Engine,'d20',return_value=20) as roller:self.e.start_of_turn(actor,initiative_count=10)
                self.assertEqual(roller.call_count,0)
                before=deepcopy(actor.budget)
                for kind in ('standard','shift','swift','full','free'):self.assertFalse(TURN.spend(self.e,actor,kind))
                self.assertEqual(actor.budget,before)
                self.assertEqual([actor.evasion(k) for k in ('물리','특수','변화')],[0,0,0])
                snapshot=self.e.gm.snapshot('csv-frozen')
                loaded=self.restored();clone=WORLD.actor_index(loaded)[actor.entity_id]
                self.assertFalse(TURN.spend(loaded,clone,'standard'))
                with patch.object(Engine,'d20',return_value=12):loaded.end_of_turn(clone)
                self.assertNotIn('얼음',clone.conditions);self.assertTrue(loaded.validate_state()['valid'])
                self.e.cure_status(actor,'얼음');self.e.gm.restore(snapshot)
                actor=WORLD.actor_index(self.e)[actor.entity_id]
                with patch.object(Engine,'d20',return_value=12):self.e.end_of_turn(actor)
                self.assertNotIn('얼음',actor.conditions);self.assertTrue(self.e.validate_state()['valid'])
        self.setUp();self.e.gm.set_types(self.p,['얼음'],reason='actual Ice Pokemon immunity')
        self.attack('냉동빔',face=20);self.assertNotIn('얼음',self.p.conditions)
        self.setUp();self.e.gm.set_types(self.a,['얼음'],reason='actual Ice typed Trainer')
        self.assertEqual(self.e.immune_to(self.a,'얼음'),'combat/type-immunities')
        self.attack('냉동빔',self.a,face=20);self.assertNotIn('얼음',self.a.conditions)

    def test_real_damage_thaws_all_four_types_but_not_preview_miss_status_or_generic_loss(self):
        for move in ('화염방사','깨트리기','파워젬','아이언헤드'):
            with self.subTest(move=move):
                self.setUp();self.e.apply_status(self.p,'얼음')
                self.assertGreater(self.e.roll_damage(self.b,self.p,self.r.move('move/'+move),set_damage=True),0)
                self.assertIn('얼음',self.p.conditions)
                self.attack(move);self.assertNotIn('얼음',self.p.conditions)
                self.assertTrue(self.e.validate_state()['valid'])
        for move,face in (('화염방사',1),('도깨비불',18),('물대포',18)):
            with self.subTest(move=move,face=face):
                self.setUp();self.e.apply_status(self.p,'얼음');self.attack(move,face=face)
                self.assertIn('얼음',self.p.conditions)
        self.setUp();self.e.apply_status(self.p,'얼음');self.e.lose_hp(self.p,1,source='화염방사')
        self.assertIn('얼음',self.p.conditions)

    def test_selected_csv_persistent_recall_and_actual_postcombat_recovery(self):
        self.e.apply_status(self.p,'얼음');self.e.gm.recall(self.p,reason='actual persistent Frozen recall')
        self.assertIn('얼음',self.p.conditions);self.e.gm.send_out(self.p,reason='actual deployment')
        self.e.begin_encounter(self.e.everyone);self.e.end_encounter()
        self.assertIn('얼음',self.p.custom_conditions[RECOVERY.KEY])
        start=self.e.elapsed_seconds
        receipt=self.e.recover_condition(self.p,'얼음',duration_minutes=2,reason='actual postcombat thaw interval')
        self.assertEqual(receipt['method'],'extended_action_after_combat')
        self.assertEqual(self.e.elapsed_seconds-start,120);self.assertEqual(self.p._action_history[-1],'extended')
        self.assertNotIn('얼음',self.p.conditions);self.assertTrue(self.e.validate_state()['valid'])
