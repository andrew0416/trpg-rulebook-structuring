"""Native handoff, next-turn prohibition and exact equipment consumers."""
import unittest,json
from copy import deepcopy
import test_manual_equipment as MANUAL
from engine import Engine,Combatant
from builder import build_pokemon
import world_entities as W,capability_actions as CAP,items as I,held_equipment as H
import action_resources as RES,turn as TURN,state_grants as G


class EquipmentOriginalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        MANUAL.Tests.setUpClass()
        cls.f=MANUAL.Tests()
    valid=MANUAL.Tests.valid

    def fixture(self):
        e,a,b,uid=self.f.fixture()
        p=Combatant(e.r,build_pokemon(e.r,'이브이',20,moves=[],abilities=[],pos=(0,1),
            extra={'trainer_id':a.entity_id,'movement':{'land':6,'power':4},'power_basis':'current'}))
        e.gm.add_combatant(p)
        return e,a,b,p,uid

    def physical(self,e,actor,name,uid,*,equip=True):
        W.register_object(e,uid,location={'kind':'unknown'},reason='actual selected test equipment',
            kind='item_instance',item_rule_id=e.r.item_effects(name)[1]['id'],
            owner_id=actor.entity_id,weight_kg=1)
        CAP.set_carried(e,actor,[*actor.spec.get('_carried_load',{}).get('objects',[]),{'id':uid,'weight_kg':1}],'actual measured item')
        if equip:I.register_item(e,actor,name,source_instance_id=uid,as_held=actor.kind=='pokemon')

    def test_handoff_equips_actual_pokemon_then_blocks_whole_next_turn_once(self):
        e,a,b,p,uid=self.fixture();obj=e._physical_objects[uid]
        out=e.give_equipment(a,p,uid)
        self.assertTrue(out['equipped']);self.assertIs(e._physical_objects[uid],obj)
        self.assertEqual((obj['carrier_id'],obj['equipped_by'],obj['owner_id']),(p.entity_id,p.entity_id,a.entity_id))
        self.assertEqual(H.entries(p)[0]['instance_id'],uid);self.assertFalse(RES.action_locked(p))
        e.end_of_turn(a);e.start_of_turn(b,initiative_count=19);e.end_of_turn(b)
        self.assertEqual(RES.turn_lock(p)['phase'],'pending')
        e.start_of_turn(p,initiative_count=18);before=deepcopy(p.budget)
        for kind in ('free','swift','shift','standard','full'):
            self.assertFalse(TURN.spend(e,p,kind,'actual prohibited action'))
        self.assertFalse(TURN.can_aoo(e,p));self.assertFalse(p._action_history)
        self.assertEqual(p.budget,before)
        hp=b.hp;used=dict(p.move_uses)
        e.use_move(p,b,'struggle')
        self.assertEqual(b.hp,hp);self.assertEqual(p.move_uses,used)
        with self.assertRaises(ValueError):e.drop_held_equipment(p,uid)
        e.end_of_turn(p);self.assertIsNone(RES.turn_lock(p))
        e.end_round();e.start_round([a,b,p]);e.start_of_turn(p,initiative_count=18)
        self.assertTrue(e.drop_held_equipment(p,uid)['changed'])
        self.assertEqual(e._physical_objects[uid]['location'],W.location_of(p));self.valid(e)

    def test_pending_and_active_lock_survive_gm_and_json_and_bad_boundary_is_rejected(self):
        e,a,b,p,uid=self.fixture();e.give_equipment(a,p,uid);e.gm.snapshot('pending-lock')
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        ix=W.actor_index(loaded);aa=ix[a.entity_id];pp=ix[p.entity_id]
        loaded.end_of_turn(aa);loaded.start_of_turn(pp,initiative_count=18)
        self.assertTrue(RES.action_locked(pp));loaded.gm.snapshot('active-lock')
        again=Engine.import_state(e.r,json.loads(json.dumps(loaded.export_state())))
        restored=W.actor_index(again)[pp.entity_id]
        self.assertFalse(TURN.spend(again,restored,'free','blocked after restore'))
        again.end_of_turn(restored);self.assertIsNone(RES.turn_lock(restored));self.valid(again)
        loaded.end_of_turn(pp);loaded.gm.restore('active-lock',reason='restore actual locked owner turn')
        self.assertTrue(RES.action_locked(pp));loaded.end_of_turn(pp)
        e.gm.restore('pending-lock',reason='restore actual handoff')
        self.assertEqual(RES.turn_lock(p)['phase'],'pending')
        RES.turn_lock(p).update(phase='active',active_round=e.round_no)
        self.assertFalse(e.validate_state()['valid'])

    def test_pokemon_replacement_and_full_capacity_are_atomic_and_old_item_stays_carried(self):
        e,a,b,p,uid=self.fixture();self.physical(e,p,'예리한손톱','old')
        before=e.export_state()
        with self.assertRaises(ValueError):e.give_equipment(a,p,uid)
        self.assertEqual(e.export_state(),before)
        e.give_equipment(a,p,uid,replace_selection='old')
        self.assertEqual(H.entries(p)[0]['instance_id'],uid)
        self.assertEqual(e._physical_objects['old']['carrier_id'],p.entity_id)
        self.assertIsNone(e._physical_objects['old'].get('equipped_by'));self.valid(e)

    def test_observed_weapons_pay_for_equip_give_and_recipient_equip_and_keep_grants(self):
        import optional_weapon_framework as FW
        for form in ('소형 근접무기','대형 근접무기','단거리 사격무기','장거리 사격무기'):
            with self.subTest(form=form):
                e,a,b,uid=self.f.fixture()
                a.spec['skills']={'전투':4};b.spec['skills']={'전투':4}
                wid='weapon/'+form
                W.register_object(e,wid,location={'kind':'unknown'},reason='actual physical weapon',owner_id=a.entity_id,weight_kg=1)
                CAP.set_carried(e,a,[{'id':wid,'weight_kg':1}],'actual weapon possession')
                FW.observe_weapon(e,a,wid,name=form,kind=form,grade='간단',arcane=False,metal=True,moves=(),reason='actual shape/material')
                self.assertEqual(e.equip_equipment(a,wid)['equipped'],wid)
                first=next(iter(a.custom_conditions['equipped_weapons'].values()))
                mid=first['struggle_id'];self.assertIn(mid,a.moves);self.assertEqual(a.budget['standard'],0)
                e.end_of_turn(a);e.end_round();e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
                e.give_equipment(a,b,wid);self.assertNotIn(mid,a.moves)
                self.assertFalse(b.custom_conditions.get('equipped_weapons'))
                e.end_of_turn(a);e.start_of_turn(b,initiative_count=19);e.equip_equipment(b,wid)
                self.assertIn(mid,b.moves);self.assertEqual(b.budget['standard'],0)
                self.assertEqual(e._physical_objects[wid]['owner_id'],a.entity_id);self.valid(e)

    def test_printed_standard_drop_overrides_apply_to_both_actual_wearer_kinds(self):
        for name in ('화염구슬','검은철구','맹독구슬','느림보 도구(공격)'):
            for kind in ('pokemon','trainer') if '느림보' not in name else ('pokemon',):
                with self.subTest(name=name,kind=kind):
                    e,a,b,p,_=self.fixture();holder=p if kind=='pokemon' else a
                    self.physical(e,holder,name,'cost-item')
                    if holder is p:e.end_of_turn(a);e.start_of_turn(p,initiative_count=18)
                    before=e.export_state();holder.budget['standard']=0
                    spent=e.export_state()
                    with self.assertRaisesRegex(ValueError,'action unavailable'):e.drop_held_equipment(holder,'cost-item')
                    self.assertEqual(e.export_state(),spent)
                    holder.budget['standard']=1
                    e.drop_held_equipment(holder,'cost-item')
                    self.assertEqual(holder.budget['standard'],0);self.assertEqual(holder._action_history[-1],'standard')
                    self.assertEqual(e._physical_objects['cost-item']['location'],W.location_of(holder));self.valid(e)

    def test_handyman_gem_herb_and_snack_consume_only_one_selected_actual_slot(self):
        for name,options in (('불꽃주얼',{}),('힘의가루',{}),('초코바',{'duration_minutes':1,'duration_reason':'actual held snack intake'}),('오랭열매',{'duration_minutes':1,'duration_reason':'actual held berry intake'})):
            with self.subTest(name=name):
                e,a,b,p,_=self.fixture();G.replace_baseline(e,p,'abilities',['배달부'])
                self.physical(e,p,name,'selected');self.physical(e,p,'예리한손톱','retained')
                if options:e.end_encounter()
                else:e.end_of_turn(a);e.start_of_turn(p,initiative_count=18)
                p.hp-=10
                out=e.use_item(p,name,held_selection='selected',**options)
                self.assertIn('consumed',e._physical_objects['selected'])
                self.assertEqual(H.entries(p)[0]['instance_id'],'retained')
                self.assertNotIn('consumed',e._physical_objects['retained'])
                self.assertEqual(p._action_history[0],'free' if name=='불꽃주얼' else 'full' if name=='힘의가루' else 'extended')
                if options:
                    e.start_round([a,b,p]);e.start_of_turn(p,initiative_count=18)
                    p.hp=p.base_max_hp//2
                    e.consume_food_buff(p,buff_id=out['buff_id'],action_kind='free',action_reason='explicit GM exchange timing')
                    self.assertEqual(p._action_history[-1],'free')
                self.valid(e)

    def test_extended_intake_is_source_forbidden_in_combat_without_cost(self):
        for name in ('초코바','오랭열매'):
            for resumable in (False,True):
                with self.subTest(name=name,resumable=resumable):
                    e,a,b,p,_=self.fixture();self.physical(e,p,name,'snack')
                    e.end_of_turn(a);e.start_of_turn(p,initiative_count=18)
                    before=e.export_state()
                    opts={'resumable':True,'request_id':'forbidden-intake'} if resumable else {}
                    with self.assertRaisesRegex(ValueError,'active encounter'):
                        e.use_item(p,name,held_selection='snack',duration_minutes=1,
                                   duration_reason='actual proposed combat intake',**opts)
                    self.assertEqual(e.export_state(),before)
                    self.valid(e)

    def test_completed_held_berry_intake_replays_after_restore_and_combat_buff_exchange(self):
        e,a,b,p,_=self.fixture();self.physical(e,p,'오랭열매','berry')
        e.end_encounter()
        options=dict(held_selection='berry',duration_minutes=1,
                     duration_reason='actual precombat berry intake',resumable=True,request_id='berry-intake')
        result=e.use_item(p,'오랭열매',**options)
        self.assertEqual(e.elapsed_seconds,60)
        self.assertIn('consumed',e._physical_objects['berry']);self.assertFalse(H.entries(p))
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        actors=W.actor_index(loaded);pp=actors[p.entity_id]
        loaded.start_round(list(actors.values()));loaded.start_of_turn(pp,initiative_count=18)
        pp.hp=pp.base_max_hp//2
        hp=pp.hp
        loaded.consume_food_buff(pp,buff_id=result['buff_id'],action_kind='free',action_reason='explicit GM exchange timing')
        self.assertEqual(pp.hp,hp+5);self.assertFalse(pp.buffs)
        before=loaded.export_state()
        self.assertEqual(loaded.use_item(pp,'오랭열매',**options),result)
        self.assertEqual(loaded.export_state(),before);self.valid(loaded)

    def test_heavy_boundary_preserves_paid_equipment_and_restorable_pending_event(self):
        import heavy_injury_adapter as HEAVY
        e,a,b,uid=self.f.fixture();a.injuries=5;a.hp=1
        with self.assertRaises(HEAVY.HeavyPending) as caught:e.equip_equipment(a,uid)
        event=e._heavy_events[caught.exception.event_id]
        self.assertEqual(event['status'],'pending');self.assertEqual(a.hp,1)
        self.assertEqual(a.budget['standard'],0)
        self.assertEqual(e._physical_objects[uid]['equipped_by'],a.entity_id)
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        self.assertEqual(loaded._heavy_pending,caught.exception.event_id);self.valid(loaded)
        with self.assertRaises(HEAVY.HeavyPending):e.equip_equipment(a,uid)
        self.assertEqual(len(e._heavy_events),1)

    def test_heavy_stable_equip_consumes_shared_temporary_hp_once_and_failure_creates_no_event(self):
        e,a,b,uid=self.f.fixture();a.injuries=5;__import__('temporary_hp').grant(e,a,8)
        hp=a.hp
        e.equip_equipment(a,uid)
        self.assertEqual((a.hp,a.temp_hp),(hp,3));self.assertEqual(len(e._heavy_events),1)
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'action unavailable'):e.give_equipment(a,b,uid)
        self.assertEqual(e.export_state(),before)

    def test_encounter_end_releases_pending_handoff_lock(self):
        e,a,b,p,uid=self.fixture();e.give_equipment(a,p,uid)
        e.end_encounter();self.assertIsNone(RES.turn_lock(p));self.valid(e)


if __name__=='__main__':unittest.main()
