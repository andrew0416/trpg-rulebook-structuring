"""Real paid object-target attacks, with explicit GM adjudication provenance."""
import json,unittest
from copy import deepcopy
import test_category2_csv_item_transfers as FIXTURE
from engine import Engine,Combatant
from builder import build_pokemon
import world_entities as WORLD
import physical_object_attacks as OBJECTS
import capability_actions as CAP


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.Tests.setUpClass();cls.f=FIXTURE.Tests()

    def fixture(self, name='화염방사', hp=20, dr=5):
        e,a,b,mid=self.f.fixture(name,held=(None,None))
        uid='door'
        WORLD.register_object(e,uid,location={'kind':'grid','cell':(1,0)},reason='actual unheld door')
        e.configure_object_durability(a,uid,max_hp=hp,reduction=dr,minimum_damage=0,
            source='gm/wooden-door-profile',reason='GM established this particular door')
        e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        return e,a,b,mid,uid

    def attack(self,e,a,mid,uid,event='attack/1',damage=12,hit=True):
        return e.attack_physical_object(a,uid,mid,event_id=event,hit=hit,damage_before_dr=damage,
            source='gm/actual-attack-resolution',reason='GM resolves actual hit and damage before object DR')

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def test_real_paid_attack_applies_dr_to_same_physical_instance(self):
        e,a,b,mid,uid=self.fixture();obj=e._physical_objects[uid]
        receipt=self.attack(e,a,mid,uid)
        self.assertEqual(receipt['applied_damage'],7)
        self.assertEqual(obj[OBJECTS.FIELD]['hp'],13)
        self.assertEqual(a.budget['standard'],0);self.assertEqual(a.move_uses[mid],1)
        self.assertIs(e._physical_objects[uid],obj)
        self.assertFalse(WORLD.physical_lifecycle(obj)['destroyed']);self.valid(e)

    def test_miss_and_zero_damage_pay_actual_move_but_do_not_damage(self):
        for hit in (False,True):
            e,a,b,mid,uid=self.fixture()
            receipt=self.attack(e,a,mid,uid,damage=0,hit=hit)
            self.assertEqual(receipt['applied_damage'],0)
            self.assertEqual(e._physical_objects[uid][OBJECTS.FIELD]['hp'],20)
            self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.budget['standard'],0)
            self.valid(e)

    def test_destroyed_instance_replay_is_idempotent_and_conflicting_event_is_rejected(self):
        e,a,b,mid,uid=self.fixture(hp=5);obj=e._physical_objects[uid]
        receipt=self.attack(e,a,mid,uid);before=e.export_state()
        self.assertTrue(WORLD.physical_lifecycle(obj)['destroyed'])
        self.assertEqual(obj['destroyed']['by_actor_id'],a.entity_id)
        self.assertEqual(self.attack(e,a,mid,uid),receipt)
        self.assertEqual(e.export_state(),before)
        for event,damage in (('attack/1',13),('attack/2',12)):
            with self.assertRaises(ValueError):self.attack(e,a,mid,uid,event,damage)
            self.assertEqual(e.export_state(),before)
        self.valid(e)

    def test_frequency_uses_same_pool_as_native_living_attack(self):
        e,a,b,mid,uid=self.fixture();self.attack(e,a,mid,uid)
        e.end_of_turn(a);e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        hp=b.hp
        self.assertEqual(e.use_move(a,b,mid),0)
        self.assertEqual(b.hp,hp);self.assertEqual(a.move_uses[mid],1)
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'재사용'):self.attack(e,a,mid,uid,'attack/2')
        self.assertEqual(e.export_state(),before)
        e.end_of_turn(a);e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        self.attack(e,a,mid,uid,'attack/3')
        self.assertEqual(a.move_uses[mid],2);self.valid(e)

    def test_actual_range_cost_conditions_and_unlearned_move_reject_without_partial_state(self):
        for failure in ('range','cost','sleep','unknown','own-turn','held','reactive'):
            e,a,b,mid,uid=self.fixture();obj=e._physical_objects[uid]
            if failure=='range':WORLD.observe_location(e,obj,{'kind':'grid','cell':(9,0)},reason='actual distant door')
            if failure=='cost':a.budget['standard']=0
            if failure=='sleep':a.conditions.add('잠듦')
            if failure=='unknown':mid=e.r.move_id('전기쇼크')
            if failure=='own-turn':a=b
            if failure=='held':
                a.spec['movement']['power']=4;a.spec['power_basis']='current'
                CAP.set_carried(e,a,[{'id':uid,'weight_kg':1}],'actual held object')
            if failure=='reactive':a.registry.append({'type':'on_move_use','effect':{}})
            before=e.export_state()
            with self.assertRaises(ValueError,msg=failure):self.attack(e,a,mid,uid)
            self.assertEqual(e.export_state(),before,failure)
            self.assertIs(e._physical_objects[uid],obj)

    def test_three_source_example_move_profiles_and_superpower_self_stage(self):
        for name in ('불꽃세례','화염방사','전기쇼크','엄청난힘'):
            e,a,b,mid,uid=self.fixture(name)
            self.attack(e,a,mid,uid)
            self.assertEqual(e._physical_objects[uid][OBJECTS.FIELD]['hp'],13)
            self.assertNotIn('conditions',e._physical_objects[uid])
            if name=='엄청난힘':self.assertEqual((a.stages['atk'],a.stages['def']),(-1,-1))
            self.valid(e)

    def test_actual_owned_pokemon_obedience_is_not_replaced_by_gm_damage_fact(self):
        for loyalty in (None,1,2):
            e,trainer,b,mid,uid=self.fixture('불꽃세례')
            e.end_of_turn(trainer);e.end_encounter()
            extra={'trainer_id':trainer.entity_id}
            if loyalty is not None:extra['loyalty']=loyalty
            pokemon=Combatant(e.r,build_pokemon(e.r,'파이리',20,moves=[mid],abilities=[],extra=extra))
            e.everyone=e.gm.everyone=[trainer,b,pokemon]
            e.start_round([trainer,b,pokemon]);e.start_of_turn(pokemon,initiative_count=20)
            before=e.export_state()
            if loyalty==2:
                self.assertEqual(self.attack(e,pokemon,mid,uid)['applied_damage'],7)
                self.assertEqual(pokemon.move_uses[mid],1);self.valid(e)
            else:
                with self.assertRaisesRegex(ValueError,'obedience'):self.attack(e,pokemon,mid,uid)
                self.assertEqual(e.export_state(),before)

    def test_gm_snapshot_and_json_roundtrip_preserve_damage_history_and_identity(self):
        e,a,b,mid,uid=self.fixture('전기쇼크');self.attack(e,a,mid,uid)
        obj=e._physical_objects[uid];e.gm.snapshot('damaged-door')
        e.end_of_turn(a);e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        self.attack(e,a,mid,uid,'attack/2')
        e.gm.restore('damaged-door',reason='restore observed attack and same door')
        obj=e._physical_objects[uid]
        self.assertEqual(obj['id'],uid);self.assertEqual(obj[OBJECTS.FIELD]['hp'],13)
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        aa=WORLD.actor_index(loaded)[a.entity_id]
        first=deepcopy(loaded.export_state())
        self.assertEqual(self.attack(loaded,aa,mid,uid)['hp_after'],13)
        self.assertEqual(loaded.export_state(),first);self.valid(loaded)

    def test_validation_detects_receipt_profile_and_hp_corruption(self):
        for failure in ('hp','profile','receipt','terminal'):
            e,a,b,mid,uid=self.fixture(hp=5);self.attack(e,a,mid,uid)
            obj=e._physical_objects[uid];state=obj[OBJECTS.FIELD]
            if failure=='hp':state['hp']=1
            if failure=='profile':state['profile']['reduction']=99
            if failure=='receipt':state['attacks'][0]['hp_after']=1
            if failure=='terminal':obj['destroyed'].pop('event_id')
            self.assertFalse(e.validate_state()['valid'],failure)
            with self.assertRaises(ValueError):Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))

    def test_no_default_stats_or_reset_or_specialized_owner_or_unsupported_move(self):
        e,a,b,mid,uid=self.fixture();before=e.export_state()
        with self.assertRaisesRegex(ValueError,'cannot reset'):
            e.configure_object_durability(a,uid,max_hp=999,reduction=0,minimum_damage=0,source='gm/x',reason='reset')
        self.assertEqual(e.export_state(),before)
        WORLD.register_object(e,'other',location={'kind':'grid','cell':(1,0)},reason='unprofiled object')
        with self.assertRaisesRegex(ValueError,'durability profile'):self.attack(e,a,mid,'other')
        e._physical_objects['other']['hp']=20
        with self.assertRaisesRegex(ValueError,'separate damage owner'):
            e.configure_object_durability(a,'other',max_hp=20,reduction=0,minimum_damage=0,source='gm/x',reason='no duplication')
        e,a,b,mid,uid=self.fixture('풀베기');before=e.export_state()
        with self.assertRaisesRegex(ValueError,'Pass Move'):self.attack(e,a,mid,uid)
        self.assertEqual(e.export_state(),before)


    def test_actual_rope_cannot_bypass_pending_material_and_cut_contract(self):
        e,a,b,mid,uid=self.fixture('엄청난힘')
        WORLD.register_object(e,'real-rope',location={'kind':'grid','cell':(1,0)},reason='actual utility rope',
            kind='item_instance',item_rule_id='item/다용도-밧줄')
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'rope requires'):
            e.configure_object_durability(a,'real-rope',max_hp=20,reduction=10,minimum_damage=0,
                source='input/ch09-equipment.md:87',reason='cannot omit source-only sharp/fire gate')
        with self.assertRaisesRegex(ValueError,'rope requires'):self.attack(e,a,mid,'real-rope')
        self.assertEqual(e.export_state(),before)


if __name__=='__main__':unittest.main()
