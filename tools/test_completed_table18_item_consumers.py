"""Actual producer/consumer counterexamples for the eight frozen CSV items."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import test_category2_csv_remaining_item_contracts as FIX
import csv_item_physical_contracts as P
import csv_item_capability_contracts as CAP
import items as ITEMS
import special_entities as SPECIAL
import world_entities as WORLD
import state_codec as CODEC


class Table18ItemConsumers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):FIX.RemainingCsvItemContractTests.setUpClass()
    def setUp(self):self.f=FIX.RemainingCsvItemContractTests();self.r=self.f.r

    def test_booster_native_weather_damage_terrain_and_scene_lifetime(self):
        a=self.f.trainer('booster-native');t=self.f.pokemon('booster-target')
        e=self.f.fixture(a,t);move=self.r.move('move/화염방사')
        base=e.roll_damage(a,t,move,set_damage=True)
        self.f.equip(e,a,'table18/booster','item/부스트에너지',held=False)
        P.activate_booster(e,a,'쾌청')
        self.assertEqual(e.roll_damage(a,t,move,set_damage=True),base+5)
        self.assertIsNone(e.weather)
        before=deepcopy(a.spec)
        with self.assertRaisesRegex(ValueError,'spent'):P.activate_booster(e,a,'비')
        self.assertEqual(a.spec,before)

    def test_umbrella_native_weather_damage_and_removal(self):
        a=self.f.trainer('umbrella-native');t=self.f.pokemon('umbrella-target')
        e=self.f.fixture(a,t);move=self.r.move('move/화염방사')
        base=e.roll_damage(a,t,move,set_damage=True)
        e.gm.set_weather('sunny',rounds=None,reason='actual Sunny world')
        self.assertEqual(e.roll_damage(a,t,move,set_damage=True),base+5)
        self.f.equip(e,a,'table18/umbrella','item/만능우산',held=False)
        self.assertEqual(e.roll_damage(a,t,move,set_damage=True),base)
        ITEMS.unregister_item(e,a,'item/만능우산')
        self.assertEqual(e.roll_damage(a,t,move,set_damage=True),base+5)

    def test_eject_pack_real_stage_loss_opens_native_reaction(self):
        owner=self.f.trainer('pack-owner');a=self.f.pokemon('pack-native');b=self.f.pokemon('pack-reserve')
        a.spec['trainer_id']=b.spec['trainer_id']=owner.entity_id
        e=self.f.fixture(owner,a,b);a.on_field=True;b.on_field=False
        self.f.equip(e,a,'table18/pack','item/탈출팩')
        e.change_stage(a,'atk',-1)
        self.assertIn('eject_pack',a.spec.get(P.PENDING,{}))
        P.resolve_pending(e,a,'eject_pack',send=b)
        self.assertFalse(a.on_field);self.assertTrue(b.on_field)
        self.assertIn('consumed',e._physical_objects['table18/pack'])

    def test_red_card_actual_hit_selects_only_actual_same_controller_reserve(self):
        owner=self.f.trainer('red-owner');a=self.f.pokemon('red-attacker');b=self.f.pokemon('red-reserve')
        holder=self.f.pokemon('red-holder');a.spec['trainer_id']=b.spec['trainer_id']=owner.entity_id
        a.spec['loyalty']=2
        e=self.f.fixture(owner,a,b,holder);a.on_field=holder.on_field=True;b.on_field=False
        a.pos=(0,0);holder.pos=(1,0);b.pos=(5,0)
        self.f.equip(e,holder,'table18/red','item/레드카드')
        e.start_round([a,holder]);e.start_of_turn(a,initiative_count=20)
        with patch.object(e,'d20',return_value=18):e.use_move(a,holder,'move/몸통박치기',set_damage=True)
        self.assertIn('consumed',e._physical_objects['table18/red'])
        self.assertFalse(a.on_field);self.assertTrue(b.on_field)

    def test_band_native_form_entry_requires_actual_owner_accessory(self):
        owner=self.f.trainer('band-owner')
        a=self.f.pokemon('band-partner',species='Venusaur');a.spec['trainer_id']=owner.entity_id
        e=self.f.fixture(owner,a);e.start_round([owner,a]);e.start_of_turn(a,initiative_count=20)
        with self.assertRaisesRegex(ValueError,'Band|band|벤드'):e.enter_gigantamax(a,source_id='item/다이맥스벤드',reason='actual Band form permission')
        self.f.equip(e,owner,'table18/band','item/다이맥스벤드',held=False)
        self.assertEqual(e.enter_gigantamax(a,source_id='item/다이맥스벤드',reason='actual Band form permission')['producer_source'],'item/다이맥스벤드')

    def test_cannon_query_preserves_actual_ammo_and_native_throw_admits_range(self):
        a=self.f.trainer('cannon-owner');t=self.f.pokemon('cannon-target')
        e=self.f.fixture(a,t);a.pos=(0,0);t.pos=(12,0)
        t.side='wild';t.spec['side']='wild';t.spec['wild']=True
        self.f.equip(e,a,'table18/cannon','item/몬스터볼-캐논',held=False)
        self.f.physical(e,a,'table18/ammo','item/몬스터볼-2')
        e.start_round([a,t]);e.start_of_turn(a,initiative_count=20)
        self.assertTrue(P.load_cannon(e,a,'table18/cannon','table18/ammo')['loaded'])
        P.cannon_profile(e,a,'table18/cannon',projectile='ball')
        self.assertEqual(e._physical_objects['table18/cannon'][P.OBJECT_STATE]['loaded_ball_instance_id'],'table18/ammo')
        e.throw_ball(a,t,'몬스터볼',cannon_instance_id='table18/cannon',fixed_accuracy=18,fixed_capture=1)
        self.assertIsNone(e._physical_objects['table18/cannon'][P.OBJECT_STATE]['loaded_ball_instance_id'])
        self.assertEqual(next(iter(a.spec['capture_attempts'].values()))['cannon']['range_m'],15)

    def test_type_manual_native_training_owns_one_exclusive_growth_reward(self):
        a=self.f.trainer('manual-native');a.spec['skills']['명령']=4
        a.spec['skills']['포켓몬학']=5
        t=self.f.pokemon('manual-partner',level=10,types=('불꽃',));t.spec['trainer_id']=a.entity_id
        e=self.f.fixture(a,t);self.f.physical(e,a,'table18/manual','item/타입-공부-메뉴얼-1')
        P.configure_type_manual(e,a,'table18/manual','불꽃',2)
        before=t.level
        e.pokemon_activity(a,'experience_training',targets=[t],safe=True,type_manual={'instance_id':'table18/manual','target_id':t.entity_id})
        self.assertEqual(t.level,before+1)
        receipt=t.spec['experience_training_history'][-1]['extra_level_source']
        self.assertEqual(receipt['source'],'C2CSV/inventory:70:1')

    def test_essence_actual_selected_augmentation_reaches_hp_permissions_and_restore(self):
        r=Rules('D:/trpg-rulebook-structuring/ptk-structure-experiment',ruleset='polygon')
        a=Combatant(r,build_pokemon(r,'이브이',20,moves=['move/섀도볼'],abilities=[]))
        e=Engine(r,seed=18100);e.gm.add_combatant(a)
        WORLD.register_object(e,'table18/implant',location={'kind':'unknown'},reason='actual installed augmentation')
        WORLD.register_object(e,'table18/plating',location={'kind':'unknown'},reason='actual installed augmentation')
        row={'id':'table18/augmentation','kind':'augmentation_set','location':{'kind':'unknown'},
             'actor_id':a.entity_id,'body_slots':['eyes','limbs','body','skin'],
             'installations':[{'instance_id':'table18/implant','augmentation_id':'smart_vision'},
                              {'instance_id':'table18/plating','augmentation_id':'dermal_plating'}],
             'allow_added_parts':False,'essence_enabled':True,'essence_profile':'C2CSV/inventory:100:17'}
        base=a.max_hp
        SPECIAL.observe(e,row,reason='explicit CSV essence injury profile')
        self.assertLess(a.max_hp,base)
        restored=CODEC.load_engine(r,json.loads(json.dumps(CODEC.dump_engine(e))))
        self.assertEqual(restored.gm.everyone[0].max_hp,a.max_hp)


if __name__=='__main__':unittest.main(verbosity=2)
