"""Actual manual actions must distinguish possession from equipment effects."""
import json, unittest
from copy import deepcopy
import test_category2_csv_item_transfers as TRANSFERS
from engine import Engine
import items as ITEMS, world_entities as WORLD, capability_actions as CAP


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TRANSFERS.Tests.setUpClass()
        cls.f=TRANSFERS.Tests()

    def fixture(self, equipped=False):
        e,a,b,_=self.f.fixture(held=(None,None))
        for c in (a,b):
            c.spec['movement']['power']=4
            c.spec['power_basis']='current'
        uid='manual-belt'
        WORLD.register_object(e,uid,location={'kind':'unknown'},reason='observed physical belt',
                              kind='item_instance',item_rule_id='item/달인의띠',owner_id=a.entity_id,weight_kg=1)
        CAP.set_carried(e,a,[{'id':uid,'weight_kg':1}],'actual belt possession')
        if equipped:ITEMS.register_item(e,a,'달인의띠',source_instance_id=uid)
        e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        return e,a,b,uid

    def valid(self,e):
        self.assertTrue(e.validate_state()['valid'],e.validate_state()['issues'])

    def test_give_only_transfers_possession_then_recipient_pays_separate_standard(self):
        for equipped in (False,True):
            with self.subTest(equipped=equipped):
                e,a,b,uid=self.fixture(equipped)
                obj=e._physical_objects[uid]
                self.assertFalse(e.give_equipment(a,b,uid)['equipped'])
                self.assertEqual(a.budget['standard'],0)
                self.assertIsNone(getattr(b,'budget',None))
                self.assertEqual(obj['carrier_id'],b.entity_id)
                self.assertEqual(obj['owner_id'],a.entity_id)
                self.assertNotIn('equipped_by',obj)
                self.assertFalse(getattr(b,'_item_reg',{}))
                self.assertFalse(getattr(a,'_item_reg',{}))
                self.assertIs(e._physical_objects[uid],obj)
                e.end_of_turn(a);e.start_of_turn(b,initiative_count=19)
                self.assertEqual(e.equip_equipment(b,uid)['slots'],['장신구'])
                self.assertEqual(b.budget['standard'],0)
                self.assertEqual(obj['equipped_by'],b.entity_id)
                self.valid(e)

    def test_replacement_keeps_old_item_carried_and_swaps_one_paid_slot(self):
        e,a,b,uid=self.fixture(True)
        other='other-belt'
        WORLD.register_object(e,other,location={'kind':'unknown'},reason='second physical belt',
                              kind='item_instance',item_rule_id='item/기합의띠',owner_id=a.entity_id,weight_kg=1)
        CAP.set_carried(e,a,[{'id':uid,'weight_kg':1},{'id':other,'weight_kg':1}],'two belts')
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'registration did not acquire'):
            e.equip_equipment(a,other)
        self.assertEqual(e.export_state(),before)
        e.equip_equipment(a,other,replace_selection=uid)
        self.assertEqual(a.budget['standard'],0)
        self.assertNotIn('equipped_by',e._physical_objects[uid])
        self.assertEqual(e._physical_objects[uid]['carrier_id'],a.entity_id)
        self.assertEqual(e._physical_objects[other]['equipped_by'],a.entity_id)
        self.assertNotIn('달인의띠',a._item_reg)
        self.valid(e)

    def test_own_turn_and_actual_possession_not_legal_owner_are_required(self):
        e,a,b,uid=self.fixture()
        before=e.export_state()
        for call in (lambda:e.equip_equipment(b,uid),lambda:e.give_equipment(b,a,uid),
                     lambda:e.equip_equipment(a,'missing')):
            with self.assertRaises(ValueError):call()
            self.assertEqual(e.export_state(),before)
        # Remote ownership does not confer physical possession.
        CAP.set_carried(e,a,[],'put down the belt')
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'physical possession'):e.equip_equipment(a,uid)
        self.assertEqual(e.export_state(),before)

    def test_failed_cost_and_recipient_capacity_roll_back_effects_carriers_and_rng(self):
        for unavailable in ('cost','load','distance'):
            with self.subTest(unavailable=unavailable):
                e,a,b,uid=self.fixture(True)
                if unavailable=='cost':a.budget['standard']=0
                if unavailable=='load':b.spec['movement']['power']=1;e._physical_objects[uid]['weight_kg']=100;a.spec['_carried_load']['objects'][0]['weight_kg']=100
                if unavailable=='distance':b.pos=(20,0)
                before=e.export_state();obj=e._physical_objects[uid]
                with self.assertRaises(ValueError):e.give_equipment(a,b,uid)
                self.assertEqual(e.export_state(),before)
                self.assertIs(e._physical_objects[uid],obj)

    def test_free_drop_requires_own_turn_records_free_and_places_same_instance(self):
        e,a,b,uid=self.fixture()
        ITEMS.register_item(e,a,'달인의띠',source_instance_id=uid,as_held=True)
        before=deepcopy(a.budget);obj=e._physical_objects[uid]
        self.assertTrue(e.drop_held_equipment(a,uid)['changed'])
        self.assertEqual(a.budget,before)
        self.assertEqual(a._action_history,['free'])
        self.assertNotIn('equipped_by',obj);self.assertNotIn('carrier_id',obj)
        self.assertEqual(obj['location'],WORLD.location_of(a))
        self.assertFalse(a.spec['_carried_load']['objects'])
        self.valid(e)
        before=e.export_state()
        with self.assertRaises(ValueError):e.drop_held_equipment(b,uid)
        self.assertEqual(e.export_state(),before)

    def test_sleep_blocks_free_drop_without_removing_equipment(self):
        e,a,b,uid=self.fixture()
        ITEMS.register_item(e,a,'달인의띠',source_instance_id=uid,as_held=True)
        e.apply_status(a,'잠듦')
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'action unavailable'):e.drop_held_equipment(a,uid)
        self.assertEqual(e.export_state(),before)

    def test_handoff_survives_both_restores_without_automatically_equipping(self):
        e,a,b,uid=self.fixture(True)
        e.give_equipment(a,b,uid);e.gm.snapshot('given')
        e.end_of_turn(a);e.start_of_turn(b,initiative_count=19);e.equip_equipment(b,uid)
        e.gm.restore('given',reason='restore actual handoff')
        self.assertNotIn('equipped_by',e._physical_objects[uid])
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        index=WORLD.actor_index(loaded);aa=index[a.entity_id];bb=index[b.entity_id]
        self.assertEqual(loaded._physical_objects[uid]['carrier_id'],bb.entity_id)
        self.assertFalse(getattr(bb,'_item_reg',{}))
        loaded.end_of_turn(aa);loaded.start_of_turn(bb,initiative_count=19)
        loaded.equip_equipment(bb,uid)
        self.assertEqual(bb.budget['standard'],0);self.valid(loaded)

    def test_actual_heavy_standard_equipment_uses_existing_local_consequence(self):
        e,a,b,uid=self.fixture()
        a.injuries=5
        before=a.hp
        try:result=e.equip_equipment(a,uid)
        except __import__('heavy_injury_adapter').HeavyPending as err:
            self.fail(str(e._heavy_events[err.event_id]['issues']))
        self.assertEqual(a.hp,before-5)
        self.assertEqual(e._heavy_events[result['heavy_event']]['status'],'applied')
        self.assertEqual(a.budget['standard'],0)
        self.valid(e)

    def test_paid_native_equip_reuses_head_body_feet_accessory_slot_owners(self):
        for name,slot in (('고고고글','머리'),('경갑','몸통'),('러닝슈즈','발'),('달인의띠','장신구')):
            with self.subTest(item=name):
                e,a,b,_=self.fixture()
                uid='selected/'+slot
                WORLD.register_object(e,uid,location={'kind':'unknown'},reason='observed actual equipment',
                                      kind='item_instance',item_rule_id='item/'+name,owner_id=a.entity_id,weight_kg=1)
                CAP.set_carried(e,a,[{'id':uid,'weight_kg':1}],'actual selected equipment')
                self.assertEqual(e.equip_equipment(a,uid)['slots'],[slot])
                self.assertEqual(a.budget['standard'],0)
                self.assertEqual(e._physical_objects[uid]['equipped_by'],a.entity_id)
                self.valid(e)

    def test_sleep_and_spent_standard_block_equip_before_registering_effects(self):
        for restriction in ('sleep','cost'):
            with self.subTest(restriction=restriction):
                e,a,b,uid=self.fixture()
                if restriction=='sleep':e.apply_status(a,'잠듦')
                else:a.budget['standard']=0
                before=e.export_state()
                with self.assertRaisesRegex(ValueError,'action unavailable'):e.equip_equipment(a,uid)
                self.assertEqual(e.export_state(),before)
                self.assertNotIn('equipped_by',e._physical_objects[uid])
                self.assertFalse(getattr(a,'_item_reg',{}))


if __name__=='__main__':unittest.main()
