"""Actual Phasing and Shadow Meld on the existing body, action and movement owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

import test_category2_body_modes as fixture
from engine import Rules
from builder import build_pokemon
import body_modes as MODES, body_state as BODY, state_grants as G, turn as TURN
import state_codec as CODEC, world_entities as WORLD, invisibility_state as INV
import skill_modifiers as SKILLS, effects_ext as EXT, forced_movement as FORCED
import mapless_space as SPACE

R=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')


class SpiritBodyModesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(R),ruleset='core')

    setUp=fixture.Tests.setUp
    add=fixture.Tests.add
    pokemon=fixture.Tests.pokemon
    restored=fixture.Tests.restored
    begin=fixture.Tests.begin
    known=fixture.Tests.known

    def own(self,c,name):G.grant(c,'capabilities',name,'fixture:'+name,'fixture')

    def phase(self,c=None,**options):
        c=self.p if c is None else c
        self.own(c,'Phasing')
        values=dict(reason='actual capability holder becomes wholly intangible')
        values.update(options)
        return self.e.change_body_mode(c,'phasing',**values)

    def gengar(self):
        c=self.add(build_pokemon(self.r,'팬텀',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
        c.pos=(5,5);self.e.gm.observe_loyalty(c,6,reason='known obedience')
        self.e.gm.set_movement_capabilities(c,{'land':6},basis='base',reason='observed native land movement')
        self.own(c,'Shadow Meld')
        return c

    def meld(self,c,**options):
        return self.e.change_body_mode(c,'shadow',reason='GM observes the actual Gengar flattened into this surface shadow',**options)

    def normal(self,c):return self.e.change_body_mode(c,'normal',reason='actual Shift return to the original body')

    def fixed_hit(self):
        native=self.e.accuracy_check
        return patch.object(self.e,'accuracy_check',side_effect=lambda *a,**kw:native(*a,**dict(kw,fixed_roll=20)))

    def resources(self,c):
        return deepcopy((getattr(c,'budget',None),c.move_uses,getattr(c,'_action_history',None),self.e.rng.getstate()))

    def test_phasing_actual_entry_standard_lock_round_loss_once_and_shift_release(self):
        original=BODY.cells(self.p);hp=self.p.hp;loss=self.e.tick_loss(self.p)
        self.begin(self.p);out=self.phase()
        self.assertEqual((out['body_mode']['mode'],BODY.cells(self.p),self.p.budget['standard']),('phasing',original,0))
        self.e.end_of_turn(self.p);self.e.end_round()
        self.assertEqual(self.p.hp,hp-loss)
        snapshot=self.e.export_state()
        with self.assertRaisesRegex(ValueError,'no open round'):self.e.end_round()
        self.assertEqual(self.e.export_state(),snapshot)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)
        before=self.resources(self.p)
        for cost in ('standard','full'):
            self.assertFalse(TURN.spend(self.e,self.p,cost,'prohibited Phasing basic action'))
        self.assertTrue(TURN.spend(self.e,self.p,'swift','actual Swift'))
        self.assertFalse(TURN.spend(self.e,self.p,'swift','forbidden Standard downgrade'))
        self.assertEqual(self.p.budget['standard'],before[0]['standard'])
        G.revoke(self.p,'fixture:Phasing',engine=self.e)
        self.normal(self.p)
        self.assertEqual(self.p.budget['shift'],0);self.assertNotIn(MODES.KEY,self.p.spec)
        hp=self.p.hp;self.e.end_of_turn(self.p);self.e.end_round();self.assertEqual(self.p.hp,hp)

    def test_phasing_rejects_actual_moves_self_item_capture_and_automatic_maneuver_before_payment(self):
        self.known(self.a,'물대포');self.begin(self.p);self.phase();self.begin(self.a)
        before=self.resources(self.a);target=deepcopy((self.p.hp,self.p.conditions,self.p.stages))
        for run in (lambda:self.e.use_move(self.a,self.p,'move/물대포'),
                    lambda:self.e.use_move_on(self.a,self.p,'move/물대포',self.e.everyone),
                    lambda:self.e.throw_ball(self.a,self.p),
                    lambda:self.e.accuracy_check(self.a,self.p,{'id':'ball','name':'ball','class':'변화','ac':6,'type':'노말'},fixed_roll=20)):
            with self.assertRaisesRegex(ValueError,'Phasing'):run()
            self.assertEqual(self.resources(self.a),before)
            self.assertEqual((self.p.hp,self.p.conditions,self.p.stages),target)
        import item_attacks as ITEMS
        from types import SimpleNamespace
        with self.assertRaisesRegex(ValueError,'Phasing'):ITEMS.prepare(self.e,SimpleNamespace(target=self.p,source_id=ITEMS.DREAM_SOURCES[0]))
        import maneuver_opposed as OP
        with self.assertRaisesRegex(ValueError,'Phasing'):
            OP._prepare(self.e,self.a,self.p,'maneuver/밀기',(),None,None,None,None,None,{},config={'action_cost':'shift','accuracy':'automatic','opposed':'waived','success':'automatic'})
        self.assertEqual(self.resources(self.a),before)
        self.known(self.p,'웅크리기');self.begin(self.p);before=self.resources(self.p)
        with self.assertRaisesRegex(ValueError,'Phasing'):self.e.use_move(self.p,self.p,'move/웅크리기')
        self.assertEqual(self.resources(self.p),before)
        # The actual-recipient leaf also refuses the current mode, independent
        # of an earlier accuracy witness or automatic hit.
        self.assertEqual(EXT.blocks_hit(self.e,self.a,self.p,self.r.move('move/물대포'),{}),'capability/페이징')

    def test_phasing_grid_area_and_mapless_selectors_consume_current_body_state(self):
        self.begin(self.p);self.phase();self.known(self.a,'스피드스타');self.begin(self.a)
        self.a.pos=(4,3);self.p.pos=(5,3);self.t.pos=(5,4)
        move=self.r.move('move/스피드스타')
        targets=self.e.targets_in_range(self.a,move,self.e.everyone,self.t)
        self.assertNotIn(self.p,targets);self.assertIn(self.t,targets)
        hp=self.p.hp;other=self.t.hp
        with self.fixed_hit():self.e.use_move_on(self.a,self.t,move['id'],self.e.everyone)
        self.assertEqual(self.p.hp,hp);self.assertLess(self.t.hp,other)
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_encounter(self.e.everyone)
        self.e.gm.set_hp(self.t,value=self.t.max_hp,reason='actual live mapless target after the area hit')
        self.e.grid=None
        self.e.gm.observe_mapless_scene(scene_id='spirit-room',places={'near':'same observed room'},placements={c.entity_id:'near' for c in self.e.everyone},contacts=[],reason='actual abstract room')
        self.e.gm.observe_mapless_targets(self.a,event_id='actual-area',move_id=move['id'],landmark_id='near',target_ids=[self.p.entity_id,self.t.entity_id],reason='actual area includes both bodies before their target eligibility is read')
        self.assertEqual(self.e.targets_in_range(self.a,move,self.e.everyone,self.t),[self.t])
        with self.assertRaisesRegex(ValueError,'Phasing'):self.e.use_move(self.a,self.p,move['id'])

    def test_shadow_species_standard_lock_stealth_evasion_and_invisibility_are_distinct(self):
        self.begin(self.p)
        with self.assertRaisesRegex(ValueError,'actual body capability'):self.meld(self.p)
        c=self.gengar();base_evasion=c.evasion('물리')
        base=SKILLS.modifiers(self.r,c,'은신',0)['modifier'];self.begin(c);self.meld(c)
        self.assertEqual(SKILLS.modifiers(self.r,c,'은신',0)['modifier'],base+4)
        self.assertEqual(SKILLS.modifiers(self.r,c,'육상',0)['modifier'],0)
        self.assertEqual(c.evasion('물리'),min(9,base_evasion+1))
        self.assertEqual(INV.accuracy_penalty(self.e,c),4)
        self.assertTrue(MODES.target_visible(self.e,self.a,c));INV.require_move(self.e,c)
        self.known(c,'물대포');self.begin(c);before=self.resources(c);hp=self.t.hp
        self.e.use_move(c,self.t,'move/물대포')
        self.assertEqual(self.resources(c),before);self.assertEqual(self.t.hp,hp)
        self.assertTrue(TURN.spend(self.e,c,'shift','actual Shadow Meld Shift'))
        with self.assertRaisesRegex(ValueError,'action unavailable'):self.normal(c)
        self.assertIn(MODES.KEY,c.spec)
        self.begin(c);self.normal(c)
        self.assertEqual(c.budget['shift'],0);self.assertEqual(SKILLS.modifiers(self.r,c,'은신',0)['modifier'],base)
        self.assertEqual(INV.accuracy_penalty(self.e,c),0)

    def test_shadow_actual_target_stays_attackable_with_native_accuracy_penalty(self):
        c=self.gengar();c.pos=(5,3);self.known(self.a,'물대포')
        move=self.r.move('move/물대포')
        before=self.e._prepare_accuracy_context(self.a,c,move,fixed_roll=10)
        self.begin(c);self.meld(c);self.begin(self.a)
        after=self.e._prepare_accuracy_context(self.a,c,move,fixed_roll=10)
        self.assertEqual(after['invisibility_penalty'],before['invisibility_penalty']+4)
        hp=c.hp
        with self.fixed_hit():self.e.use_move(self.a,c,move['id'],set_damage=True)
        self.assertLess(c.hp,hp)
        self.assertEqual(MODES.validate(c)['mode'],'shadow')

    def test_shadow_surface_uses_real_continuous_path_shift_distance_and_original_body_release(self):
        c=self.gengar();c.pos=(5,5);self.begin(c);self.meld(c)
        WORLD.register_object(self.e,'wall-surface',location={'kind':'grid','cell':[5,5]},reason='actual stationary wall whose face follows the observed path')
        path=[{'position':(5,5),'altitude':0},{'position':(5,5),'altitude':1},{'position':(6,5),'altitude':1}]
        MODES.observe_shadow_surface(self.e,'wall-surface',path,reason='GM observes these connected actual wall face contact points')
        # Entry used Standard; the actual Shift remains and consumes no flight.
        out=self.e.move_shadow(c,path,movement_id='flat-wall',surfaces=['wall-surface']*3,reason='GM observes continuous contact along this actual wall face')
        self.assertEqual((out['steps'],out['distance'],c.pos,c.spec['_movement_altitude']),(2,2,(6,5),1))
        self.assertFalse(c.airborne);self.assertEqual(c.budget['shift'],0)
        self.assertEqual(self.e.move_shadow(c,path,movement_id='flat-wall',surfaces=['wall-surface']*3,reason='GM observes continuous contact along this actual wall face'),out)
        saved=self.restored();copy_c=next(x for x in saved.everyone if x.entity_id==c.entity_id)
        self.assertEqual(BODY.projection(copy_c)['body_mode'],BODY.projection(c)['body_mode'])
        self.begin(c);before=deepcopy((c.spec,c.budget,c.location,self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError,'ground contact'):
            self.e.move_shadow(c,[{'position':(6,5),'altitude':1},{'position':(6,5),'altitude':2}],movement_id='fake-air',surfaces=['ground']*2,reason='not an observed surface')
        self.assertEqual((c.spec,c.budget,c.location,self.e.rng.getstate()),before)
        self.normal(c);self.assertNotIn(MODES.KEY,c.spec);self.assertEqual(c.budget['shift'],0)

    def test_shadow_surface_rejects_distant_contact_and_forged_paid_route(self):
        c=self.gengar();c.pos=(5,5);self.begin(c);self.meld(c)
        WORLD.register_object(self.e,'far-wall',location={'kind':'grid','cell':[15,5]},reason='actual distant stationary wall')
        MODES.observe_shadow_surface(self.e,'far-wall',[{'position':(15,5),'altitude':0},{'position':(15,5),'altitude':1}],reason='actual far wall contact geometry')
        path=[{'position':(5,5),'altitude':0},{'position':(5,5),'altitude':1}]
        before=deepcopy((c.spec,c.budget,c.location,self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError,'no observed contact'):
            self.e.move_shadow(c,path,movement_id='distant-wall',surfaces=['far-wall']*2,reason='cannot cite a distant wall to fly')
        self.assertEqual((c.spec,c.budget,c.location,self.e.rng.getstate()),before)
        WORLD.register_object(self.e,'near-wall',location={'kind':'grid','cell':[5,5]},reason='actual nearby wall')
        MODES.observe_shadow_surface(self.e,'near-wall',path,reason='observed actual continuous wall contacts')
        self.e.move_shadow(c,path,movement_id='near-wall-move',surfaces=['near-wall']*2,reason='actual surface movement')
        original=deepcopy(c.spec[MODES.KEY]['motion']);motion=c.spec[MODES.KEY]['motion']
        motion['plan']['path'][-1]['position']=(6,5)
        motion['progress']['path'][-1]['position']=(6,5)
        with self.assertRaisesRegex(CODEC.StateCodecError,'observed declaration'):self.e.export_state()
        c.spec[MODES.KEY]['motion']=original
        self.begin(c)
        contacts=path+[{'position':(5,5),'altitude':2}]
        MODES.observe_shadow_surface(self.e,'near-wall',contacts,reason='actual wall contact continues upward')
        import movement_actions as MOVE
        def moved_surface(e,current,q,height,**kw):
            WORLD.observe_location(e,e._physical_objects['near-wall'],{'kind':'grid','cell':[15,5]},reason='actual departure reaction moves the surface away')
            return True
        with patch.object(MOVE,'departure',side_effect=moved_surface):
            out=self.e.move_shadow(c,contacts[1:],movement_id='lost-contact',surfaces=['near-wall']*2,reason='actual paid wall traversal meets departure reaction')
        self.assertEqual((out['steps'],out['distance'],c.pos,c.spec['_movement_altitude']),(0,0,(5,5),1))
        self.assertEqual(c.budget['shift'],0)
        self.assertTrue(out['stopped'])
        self.assertEqual(c.spec[MODES.KEY]['motion']['progress']['phase'],'stopped')
        self.begin(c);self.normal(c);self.assertNotIn(MODES.KEY,c.spec)

    def test_actual_shadow_host_follows_native_forced_gm_and_abstract_location_without_mount_grants(self):
        c=self.gengar();c.pos=self.t.pos
        self.begin(c);self.meld(c,shadow_host=self.t)
        self.assertNotIn('mount_id',c.spec);budget=deepcopy(c.budget)
        self.begin(self.t);self.e.approach(self.t,self.a,movement_mode='land')
        self.assertEqual(c.pos,self.t.pos);self.assertNotEqual(c.pos,(7,3));self.assertEqual(c.budget,budget)
        FORCED.displace(self.e,self.a,self.t,direction=(0,1),distance=1,source='move/밀쳐내기')
        self.assertEqual(c.pos,self.t.pos)
        self.e.gm.set_position(self.t,(8,6),reason='GM observes host actual movement');self.assertEqual(c.pos,(8,6))
        saved=self.restored();copy_c=next(x for x in saved.everyone if x.entity_id==c.entity_id)
        self.assertEqual(copy_c.spec[MODES.KEY]['host']['actor_id'],self.t.entity_id)
        WORLD.observe_location(self.e,self.t,{'kind':'abstract','place_id':'same moving host'},reason='actual host entered observed abstract place')
        self.assertEqual(WORLD.location_of(c),WORLD.location_of(self.t))
        self.assertFalse(TURN.movement_permission(self.e,c));self.assertNotIn('mount_id',c.spec)
        # Returning removes the relation; later actual host movement stays separate.
        self.e.grid=None;self.begin(c);self.normal(c)
        WORLD.observe_location(self.e,self.t,{'kind':'abstract','place_id':'elsewhere'},reason='host leaves after Gengar emerged')
        self.assertNotEqual(WORLD.location_of(c),WORLD.location_of(self.t))

    def test_new_mode_observations_source_selection_and_actor_binding_are_validated(self):
        self.begin(self.p)
        for bad in (0,1,True,-1):
            before=deepcopy((self.p.spec,self.p.budget))
            with self.assertRaises(ValueError):self.phase(round_loss=bad)
            # The capability fixture is installed before the rejected operation.
            self.assertNotIn(MODES.KEY,self.p.spec);self.assertEqual(self.p.budget,before[1])
        self.phase();state=deepcopy(self.p.spec[MODES.KEY]);self.p.spec[MODES.KEY]['actor_id']=self.t.entity_id
        with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
        self.p.spec[MODES.KEY]=state
        selected=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid,*a,**kw:'custom/phasing' if uid=='capability/페이징' else selected(uid,*a,**kw)):
            with self.assertRaisesRegex(ValueError,'source mismatch'):MODES.validate(self.p)


if __name__=='__main__':unittest.main()
