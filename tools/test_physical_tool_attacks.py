"""Real equipped sharp/blunt weapon attacks share existing rope HP and costs."""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Engine
from grid import Grid
import test_physical_materials as BASE
import world_entities as WORLD
import physical_object_attacks as HP
import physical_tool_attacks as TOOLS
import optional_weapon_framework as FW
import turn as TURN


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.Tests.setUpClass();cls.base=BASE.Tests()

    def fixture(self,surface='cutting_edge',kind='소형 근접무기',rule='item/다용도-밧줄'):
        e,a,b,_,rope=self.base.fixture(rule=rule)
        e.end_of_turn(a);e.grid=Grid(16,6);a.pos=(0,0);b.pos=(15,5)
        import body_state as BODY
        for c in (a,b):BODY.observe(e,c,[(0,0)],reason='observed human body')
        uid='actual/knife'
        WORLD.register_object(e,uid,location={'kind':'unknown'},owner_id=a.entity_id,weight_kg=1,reason='actual owned tool')
        FW.observe_weapon(e,a,uid,name='서바이벌 나이프',kind=kind,grade='간단',arcane=False,metal=True,
                          moves=[],reason='GM observes actual weapon form')
        if surface is not None:e.observe_weapon_contact_surface(a,uid,contact_surface=surface,
            source='gm/actual-contact-observation',reason='observed the working edge/point or blunt striking surface')
        key=FW.equip(e,a,uid)
        e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        return e,a,b,key,rope,uid

    def attack(self,e,a,rope,uid,event='weapon/1',damage=12,hit=True):
        return e.attack_object_with_weapon(a,rope,uid,event_id=event,hit=hit,damage_before_dr=damage,
            source='gm/actual-tool-hit',reason='actual contact hit and damage before target DR')

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def test_actual_knife_uses_same_rope_dr_hp_action_and_weapon_frequency(self):
        e,a,b,key,rope,uid=self.fixture();obj=e._physical_objects[rope]
        result=self.attack(e,a,rope,uid)
        self.assertEqual(result['applied_damage'],2);self.assertEqual(obj[HP.FIELD]['hp'],18)
        self.assertEqual(result['material_policy']['tags'],['sharp']);self.assertFalse(result['material_policy']['ignore_all_dr'])
        self.assertEqual((a.budget['standard'],a.move_uses[key]),(0,1));self.assertIs(obj,e._physical_objects[rope])
        self.assertEqual(result['tool_attack']['tool_id'],uid);self.valid(e)

    def test_sharp_point_blunt_and_miss_pay_without_invented_cut_exception(self):
        for surface,hit,damage,expected in [('sharp_point',True,31,11),('cutting_edge',True,2,1),
                                           ('blunt',True,999,0),('cutting_edge',False,0,0)]:
            with self.subTest(surface=surface,hit=hit,damage=damage):
                e,a,b,key,rope,uid=self.fixture(surface,rule='item/단단한-로프')
                row=self.attack(e,a,rope,uid,hit=hit,damage=damage)
                self.assertEqual(row['applied_damage'],expected)
                self.assertEqual((a.budget['standard'],a.move_uses[key]),(0,1));self.valid(e)

    def test_sharp_breaks_basic_rope_and_replay_after_unequip_restores_no_action(self):
        e,a,b,key,rope,uid=self.fixture(rule='item/기본-밧줄')
        row=self.attack(e,a,rope,uid);self.assertTrue(WORLD.physical_lifecycle(e._physical_objects[rope])['destroyed'])
        TURN.unequip_weapon(e,a,key);before=e.export_state()
        self.assertEqual(self.attack(e,a,rope,uid),row);self.assertEqual(e.export_state(),before);self.valid(e)
        with self.assertRaisesRegex(ValueError,'conflicts'):self.attack(e,a,rope,uid,damage=13)
        self.assertEqual(e.export_state(),before)

    def test_actual_four_weapon_ranges_and_long_range_minimum(self):
        for kind,distance in [('소형 근접무기',1),('대형 근접무기',1),('단거리 사격무기',4),('장거리 사격무기',12)]:
            with self.subTest(kind=kind):
                e,a,b,key,rope,uid=self.fixture(kind=kind)
                WORLD.observe_location(e,e._physical_objects[rope],{'kind':'grid','cell':(distance,0)},reason='actual rope position')
                self.assertEqual(self.attack(e,a,rope,uid)['applied_damage'],2);self.valid(e)
        e,a,b,key,rope,uid=self.fixture(kind='장거리 사격무기');before=e.export_state()
        with self.assertRaisesRegex(ValueError,'minimum range'):self.attack(e,a,rope,uid)
        self.assertEqual(e.export_state(),before)

    def test_missing_observation_unequipped_other_holder_blocked_range_and_cost_refuse_atomically(self):
        for case in ('missing','unequipped','holder','wall','range','cost'):
            with self.subTest(case=case):
                e,a,b,key,rope,uid=self.fixture(None if case=='missing' else 'cutting_edge')
                if case=='unequipped':TURN.unequip_weapon(e,a,key)
                if case=='wall':e.grid.blocking.add((1,0))
                if case=='range':WORLD.observe_location(e,e._physical_objects[rope],{'kind':'grid','cell':(3,0)},reason='out of reach')
                if case=='cost':a.budget['standard']=0
                before=e.export_state()
                with self.assertRaises(ValueError):self.attack(e,b if case=='holder' else a,rope,uid)
                self.assertEqual(e.export_state(),before)

    def test_late_destruction_failure_rolls_back_weapon_use_and_same_hp(self):
        e,a,b,key,rope,uid=self.fixture(rule='item/기본-밧줄');obj=e._physical_objects[rope];before=e.export_state()
        with patch.object(WORLD,'finish_physical_use',side_effect=ValueError('late actual destruction failure')):
            with self.assertRaisesRegex(ValueError,'late actual'):self.attack(e,a,rope,uid)
        self.assertEqual(e.export_state(),before);self.assertIs(e._physical_objects[rope],obj);self.valid(e)

    def test_json_gm_restore_preserves_sourced_surface_and_damage_then_next_attack(self):
        e,a,b,key,rope,uid=self.fixture();first=self.attack(e,a,rope,uid)
        e.gm.snapshot('after-knife');e.gm.restore('after-knife');self.valid(e)
        restored=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        ra=WORLD.actor_index(restored)[a.entity_id];self.valid(restored)
        self.assertEqual(self.attack(restored,ra,rope,uid),first)
        restored.end_of_turn(ra);restored.start_round(restored.everyone);restored.start_of_turn(ra,initiative_count=20)
        self.assertEqual(self.attack(restored,ra,rope,uid,event='weapon/2')['hp_after'],16);self.valid(restored)

    def test_surface_cannot_be_reclassified_or_forged_and_bypassed_with_public_move(self):
        e,a,b,key,rope,uid=self.fixture();before=e.export_state()
        with self.assertRaisesRegex(ValueError,'immutable'):
            e.observe_weapon_contact_surface(a,uid,contact_surface='blunt',source='gm/change',reason='try reset')
        with self.assertRaises(ValueError):e.attack_physical_object(a,rope,key,event_id='bypass',hit=True,
            damage_before_dr=999,source='gm/free-sharp',reason='no physical producer')
        self.assertEqual(e.export_state(),before)
        self.attack(e,a,rope,uid)
        e._physical_objects[uid][TOOLS.FIELD]['facts']['contact_surface']='blunt'
        self.assertFalse(e.validate_state()['valid'])
