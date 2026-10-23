"""Real sourced rope identity/HP, material exceptions and existing paid attacks."""
from copy import deepcopy
import json,unittest
from engine import Engine
import test_physical_object_attacks as BASE
import physical_object_attacks as ATTACKS
import physical_materials as MATERIALS
import world_entities as WORLD


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.Tests.setUpClass();cls.base=BASE.Tests()

    def fixture(self,name='화염방사',rule='item/다용도-밧줄',length=50):
        e,a,b,mid,_=self.base.fixture(name)
        uid='rope'
        WORLD.register_object(e,uid,location={'kind':'grid','cell':(1,0)},reason='observed actual rope',
            kind='item_instance',item_rule_id=rule)
        e.configure_rope(a,uid,length_feet=length,reason='actual rope kind and measured length')
        return e,a,b,mid,uid

    def test_three_actual_kinds_source_lengths_prices_hp_and_real_load_capacity(self):
        for rule,hp,dr,tension,price in [('item/기본-밧줄',5,0,35,100),('item/다용도-밧줄',20,10,80,200),('item/단단한-로프',30,20,225,400)]:
            e,a,b,mid,uid=self.fixture(rule=rule)
            obj=e._physical_objects[uid]
            for length in (25,30,50,300):
                q=e.rope_quote(rule,length_feet=length)
                self.assertEqual((q['max_hp'],q['reduction'],q['tension_kg'],q['price']),(hp,dr,tension,price*length//25))
            self.assertEqual(obj[ATTACKS.FIELD]['hp'],hp)
            WORLD.register_object(e,'load',location={'kind':'grid','cell':(1,0)},reason='real load',weight_kg=tension)
            WORLD.register_object(e,'extra',location={'kind':'grid','cell':(1,0)},reason='extra real load',weight_kg=0.1)
            self.assertTrue(e.rope_capacity(uid,load_ids=['load'])['within_capacity'])
            self.assertFalse(e.rope_capacity(uid,load_ids=['load','extra'])['within_capacity'])
            self.assertEqual(obj[ATTACKS.FIELD]['hp'],hp)
            self.base.valid(e)

    def test_paid_fire_applies_material_dr_then_uses_same_destruction_owner(self):
        e,a,b,mid,uid=self.fixture(rule='item/단단한-로프')
        obj=e._physical_objects[uid]
        result=self.base.attack(e,a,mid,uid,damage=55)
        self.assertEqual(result['applied_damage'],30)
        self.assertEqual(result['material_policy']['reduction'],20)
        self.assertEqual(result['material_policy']['tags'],['fire'])
        self.assertIs(e._physical_objects[uid],obj)
        self.assertTrue(WORLD.physical_lifecycle(obj)['destroyed'])
        self.assertEqual(a.budget['standard'],0);self.assertEqual(a.move_uses[mid],1)
        before=e.export_state();self.assertEqual(self.base.attack(e,a,mid,uid,damage=55),result)
        self.assertEqual(e.export_state(),before);self.base.valid(e)

    def test_nonsharp_nonfire_hit_pays_but_cannot_damage_or_break_rope(self):
        for name in ('엄청난힘','전기쇼크'):
            e,a,b,mid,uid=self.fixture(name)
            result=self.base.attack(e,a,mid,uid,damage=999)
            self.assertEqual(result['applied_damage'],0)
            self.assertEqual(e._physical_objects[uid][ATTACKS.FIELD]['hp'],20)
            self.assertFalse(result['material_policy']['allowed'])
            self.assertEqual(a.budget['standard'],0);self.assertEqual(a.move_uses[mid],1)
            if name=='엄청난힘':self.assertEqual((a.stages['atk'],a.stages['def']),(-1,-1))
            self.base.valid(e)

    def test_allowed_fire_uses_core_minimum_one_after_material_dr(self):
        e,a,b,mid,uid=self.fixture('불꽃세례',rule='item/단단한-로프')
        result=self.base.attack(e,a,mid,uid,damage=2)
        self.assertEqual(result['applied_damage'],1)
        self.assertEqual(e._physical_objects[uid][ATTACKS.FIELD]['hp'],29)
        self.base.valid(e)

    def test_cut_material_plan_ignores_all_twenty_dr_but_pass_activation_is_not_faked(self):
        e,a,b,mid,uid=self.fixture('풀베기',rule='item/단단한-로프')
        _,move,mm,policy=ATTACKS._move(e,a,mid)
        plan=MATERIALS.damage_policy(e,e._physical_objects[uid],move,policy)
        self.assertEqual(plan['reduction'],0);self.assertTrue(plan['ignore_all_dr'])
        result=ATTACKS._calculation(e._physical_objects[uid][ATTACKS.FIELD]['profile'],True,12,plan)
        self.assertEqual(result['after_defense'],12)
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'Pass Move'):self.base.attack(e,a,mid,uid)
        self.assertEqual(e.export_state(),before)

    def test_invalid_lengths_reset_and_definition_mutation_reject_atomically(self):
        e,a,b,mid,uid=self.fixture();before=e.export_state()
        for length in (True,24,301,25.5):
            with self.assertRaises(ValueError):e.configure_rope(a,uid,length_feet=length,reason='invalid length')
            self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'cannot reset'):
            e.configure_rope(a,uid,length_feet=75,reason='cannot reset')
        self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'cannot reset'):
            e.configure_object_durability(a,uid,max_hp=99,reduction=0,minimum_damage=0,source='fake',reason='fake')
        self.assertEqual(e.export_state(),before)
        from unittest.mock import patch
        original=e.r.item_effects
        def changed(name):
            effects,definition=deepcopy(original(name));definition['price']+=1
            return effects,definition
        with patch.object(e.r,'item_effects',changed):
            with self.assertRaisesRegex(ValueError,'changed'):e.rope_quote('item/다용도-밧줄',length_feet=25)
        self.assertEqual(e.export_state(),before)

    def test_gm_and_json_restore_material_history_and_reject_corrupt_source_projection(self):
        e,a,b,mid,uid=self.fixture('불꽃세례');self.base.attack(e,a,mid,uid,damage=12)
        e.gm.snapshot('rope')
        e.end_of_turn(a);e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        self.base.attack(e,a,mid,uid,event='second',damage=14)
        e.gm.restore('rope',reason='restore same rope and damage')
        self.assertEqual(e._physical_objects[uid][ATTACKS.FIELD]['hp'],18)
        state=json.loads(json.dumps(e.export_state()))
        loaded=Engine.import_state(e.r,state);self.base.valid(loaded)
        for corrupt in ('price','tension_kg','length_feet'):
            bad=Engine.import_state(e.r,deepcopy(state))
            bad._physical_objects[uid][MATERIALS.FIELD]['facts'][corrupt]+=1
            self.assertFalse(bad.validate_state()['valid'])
            with self.assertRaises(ValueError):Engine.import_state(e.r,json.loads(json.dumps(bad.export_state())))


if __name__=='__main__':unittest.main()
