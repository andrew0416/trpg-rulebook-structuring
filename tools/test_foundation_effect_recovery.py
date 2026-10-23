"""Reusable recovery parameters and actual native Integrity repair."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys, json, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_special_entities as _fixture_test_category2_special_entities
from engine import Engine
import special_entities as SPECIAL
import recovery_resolution as RECOVERY
import temporary_hp as TEMP
import injury_recovery as INJURY
import effects_ext as EXT


class EffectRecoveryTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_test_category2_special_entities.SpecialTests.setUpClass.__func__)
    setUp=_fixture_test_category2_special_entities.SpecialTests.setUp
    trainer=_fixture_test_category2_special_entities.SpecialTests.trainer
    object=_fixture_test_category2_special_entities.SpecialTests.object
    digital=_fixture_test_category2_special_entities.SpecialTests.digital

    def avatar(self, *, integrity=1, status='connected'):
        row=self.digital();row.update(integrity=integrity,status=status)
        SPECIAL.observe(self.e,row,reason='actual digital resource observation')
        return self.e._physical_objects['avatar']

    def repair(self, amount, **options):
        return self.e.repair_integrity('avatar',amount,source=options.pop('source','gm/declared-repair'),
            eligible=options.pop('eligible',True),reason='explicit repair procedure permission',**options)

    def test_data_operations_keep_resource_caps_and_allowance_distinct(self):
        cases=[
            (dict(current=10,requested=5,resource='hp',ceiling=8),10,0),
            (dict(current=-5,requested=9,resource='hp',ceiling=20),4,9),
            (dict(current=8,requested=5,resource='temp_hp',mode='at_least'),8,0),
            (dict(current=3,requested=12,resource='integrity',ceiling=10),10,7),
            (dict(current=5,requested=5,resource='injuries',mode='remove',floor=2,allowance=1),4,1),
        ]
        for data,after,applied in cases:
            with self.subTest(data=data):
                result=RECOVERY.resolve(**data)
                self.assertEqual((result['after'],result['applied']),(after,applied))

    def test_native_hp_temp_hp_and_injury_consumers_preserve_their_policies(self):
        self.a.injuries=2;self.a.hp=self.a.base_max_hp;before=self.a.hp
        self.assertEqual(self.e.heal(self.a,20),0);self.assertEqual(self.a.hp,before)
        self.assertEqual(TEMP.grant(self.e,self.a,8),8)
        self.assertEqual(TEMP.grant(self.e,self.a,5),0)
        self.assertEqual(TEMP.grant(self.e,self.a,12),4)
        self.a.injuries=5
        self.assertEqual(INJURY.heal(self.e,self.a,2,source='gm/ordinary-recovery'),2)
        self.assertEqual(INJURY.heal(self.e,self.a,8,source='gm/ordinary-recovery'),1)
        self.assertEqual(self.a.injuries,2)

    def test_actual_integrity_repair_caps_without_changing_real_hp_or_location(self):
        row=self.avatar();before=(self.a.hp,deepcopy(self.a.location),row['temp_integrity'])
        result=self.repair(1000)
        self.assertEqual(result['resource'],'integrity')
        self.assertEqual((result['before'],result['after'],result['applied']),(1,row['max_integrity'],row['max_integrity']-1))
        self.assertEqual((self.a.hp,self.a.location,row['temp_integrity']),before)
        self.assertEqual(self.repair(1)['applied'],0)

    def test_positive_integrity_does_not_reconnect_ejected_entity(self):
        row=self.avatar(integrity=0,status='ejected')
        self.repair(10)
        self.assertEqual((row['integrity'],row['status']),(10,'ejected'))

    def test_actual_node_repairs_its_integrity_without_changing_data_or_connection(self):
        self.object('network')
        node=dict(id='core',kind='digital_node',location={'kind':'abstract','place_id':'network'},
                  node_type='server_core',network_id='network',integrity=0,max_integrity=90,
                  status='disabled',anchor_id=None,controller_id=self.a.entity_id,
                  defense=8,evasion=2,data_state='corrupted',bot_id=None)
        SPECIAL.observe(self.e,node,reason='actual disabled server core')
        result=self.e.repair_integrity('core',100,source='gm/declared-node-repair',
                                       eligible=True,reason='explicit repair permission')
        actual=self.e._physical_objects['core']
        self.assertEqual((result['applied'],actual['integrity']),(90,90))
        self.assertEqual((actual['status'],actual['data_state']),('disabled','corrupted'))

    def test_declared_ineligibility_does_not_change_resource(self):
        row=self.avatar();before=deepcopy(row)
        result=self.repair(10,eligible=False)
        self.assertFalse(result['eligible']);self.assertEqual(result['applied'],0)
        self.assertEqual(row,before)

    def test_invalid_recovery_values_and_changed_source_reject_before_resource_change(self):
        row=self.avatar();before=deepcopy(row)
        for amount in (-1,True,1.5):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):self.repair(amount)
                self.assertEqual(row,before)
        with self.assertRaises(ValueError):self.repair(1,eligible='maybe')
        source=row['source_ids'][0];original=self.e.r._selected_rule
        with patch.object(self.e.r,'_selected_rule',side_effect=lambda uid:uid+'/changed' if uid==source else original(uid)):
            with self.assertRaises(ValueError):self.repair(1,source=source)
        self.assertEqual(row,before)

    def test_late_native_integrity_validation_failure_rolls_back_resource(self):
        row=self.avatar();before=deepcopy(row);original=SPECIAL.validate_record
        def reject(staged,record,*args,**kwargs):
            if record.get('id')=='avatar' and record['integrity']==record['max_integrity']:
                raise ValueError('late repair state rejection')
            return original(staged,record,*args,**kwargs)
        with patch.object(SPECIAL,'validate_record',side_effect=reject):
            with self.assertRaisesRegex(ValueError,'late repair'):self.repair(1000)
        self.assertEqual(row,before)

    def test_repaired_integrity_roundtrip_keeps_separate_resource_identity(self):
        row=self.avatar();self.repair(10)
        restored=Engine.import_state(self.e.r,json.loads(json.dumps(self.e.export_state())))
        self.assertEqual(restored._physical_objects['avatar']['integrity'],11)
        self.assertEqual(restored._physical_objects['avatar']['actor_id'],self.a.entity_id)
        self.assertEqual(restored._physical_objects['avatar']['max_integrity'],row['max_integrity'])

    def test_invalid_healing_does_not_register_actor_in_shared_clock(self):
        self.assertNotIn(self.a,self.e._time_actors)
        for amount,source in [(True,'move'),(1,'invented-source-kind')]:
            with self.assertRaises(ValueError):self.e.heal(self.a,amount,source_kind=source)
            self.assertNotIn(self.a,self.e._time_actors)

    def test_general_removal_save_preserves_modifiers_without_inventing_a_condition(self):
        self.a.save_mod=2
        self.assertEqual(EXT.save_dc(self.e,self.a,None,15),13)
        with self.assertRaises(ValueError):EXT.save_dc(self.e,self.a,'unresolved-affliction',15)


if __name__=='__main__':unittest.main()
