"""C10-074/079: committed shared movement and complete No Guard alternatives."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

import combat_hit as HIT
import effects_ext as EXT
import living_weapon as L
import movement_actions as MOVE
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import state_grants as G
import turn as TURN
import world_entities as W

ROOT=Path(__file__).resolve().parents[1]
NO_GUARD='노가드 [Playtest]'


class LivingWeaponMovementNoGuardSourceRevisionTests(unittest.TestCase):
    def world(self,*,holder='pokemon',modes=()):
        def actor(key,kind,species,pos,side,speed):
            movement={'land':speed,'power':3,**dict.fromkeys(modes,speed)}
            sheet={'name':key,'level':40,'moves':['move/몸통박치기'],'abilities':[],
                   'pos':pos,'side':side,'extra':{'skills':{'전투':6,'집중':6},
                       'movement':movement,'movement_basis':'current'}}
            if kind=='pokemon':sheet.update(species=species,wild=True)
            else:sheet['stats']=dict.fromkeys(('hp','atk','def','spa','spd','spe'),30)
            return {'key':key,'kind':kind,'sheet':sheet,
                    'body':{'size':'소형' if kind=='pokemon' else '중형','offsets':[(0,0)],
                            'reason':'actual observed Living Weapon movement participant body'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=74079,
            grid={'width':25,'height':12},actors=[
                actor('holder',holder,'파오리',(2,2),'party',6),
                actor('weapon','pokemon','단칼빙',(3,2),'party',2),
                actor('target','pokemon','파오리',(20,2),'opponent',2)])
        self.a,self.p,self.t=(actors[key] for key in ('holder','weapon','target'))

    def choice(self,variant):
        pending=L.no_guard_choices(self.e)
        self.assertEqual(pending['status'],'PolicyInputsRequired')
        self.assertEqual(pending['obligations'][0]['decision_kind'],'source_conflict')
        return {'value':variant,'reason':'campaign explicitly chooses the complete No Guard source definition',
                'scope':pending['decision_scope']}

    def equip(self,variant=None,**options):
        choice=None if variant is None else self.choice(variant)
        self.e.equip_living_weapon(self.a,self.p,consent=True,no_guard_choice=choice,**options)
        return choice

    def turn(self,actor,*,new_round=False):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        if new_round or not self.e.encounter_active:self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=20)

    def restore(self):
        identities=[c.entity_id for c in (self.a,self.p,self.t)]
        self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=W.actor_index(self.e)
        self.a,self.p,self.t=(index[key] for key in identities)

    def modifiers(self,pairs):
        observed=[];resolve=HIT.resolve
        def capture(**options):observed.append(options['modifier']);return resolve(**options)
        with patch.object(HIT,'resolve',capture):
            for attacker,target in pairs:
                self.e.accuracy_check(attacker,target,self.e.r.move('move/몸통박치기'),fixed_roll=10)
        return observed

    def test_shared_pool_uses_trainer_or_pokemon_holder_speed_across_turns_restore_and_rounds(self):
        for holder in ('trainer','pokemon'):
            with self.subTest(holder=holder):
                self.world(holder=holder);self.equip();self.turn(self.a)
                self.e.gm.set_position(self.t,(6,2),reason='actual first goal is three metres away')
                self.assertEqual(self.e.approach(self.a,self.t)['distance'],3)
                self.assertEqual((self.a.pos,self.p.pos),((5,2),(5,2)))
                self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],3)
                self.e.gm.snapshot('shared-three');self.e.gm.restore('shared-three');self.restore()
                self.e.gm.set_position(self.t,(20,2),reason='actual second goal leaves more than the remaining pool')
                self.turn(self.p)
                self.assertEqual(self.e.move_profile(self.p,movement_mode='land')[0],6)
                self.assertEqual(self.e.approach(self.p,self.t)['distance'],3)
                self.assertEqual((self.a.pos,self.p.pos),((8,2),(8,2)))
                self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],6)
                self.assertEqual((self.a.budget['shift'],self.p.budget['shift']),(0,0))
                self.assertEqual(self.p.spec['movement']['land'],2)
                self.restore();self.assertEqual(L.movement_remaining(self.e,self.p),0)
                self.turn(self.a,new_round=True)
                self.assertEqual(self.e.approach(self.a,self.t)['distance'],6)
                self.assertEqual(self.p.spec[L.MOVEMENT]['round'],self.e.round_no)
                self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],6)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_partial_paid_path_rejected_step_and_resumed_prefix_debit_only_committed_cost(self):
        self.world();self.equip();self.turn(self.a)
        self.assertTrue(TURN.spend(self.e,self.a,'shift','actual declared native path',movement=True))
        path=[(x,2) for x in range(3,9)];progress={}
        self.e.grid.blocking.add((5,2));rng=self.e.rng.getstate()
        result=MOVE.follow_paid_path(self.e,self.a,path,mode='land',maximum_distance=6,progress=progress)
        self.assertEqual((result['distance'],progress['next'],self.p.spec[L.MOVEMENT]['distance']),(2,2,2))
        self.assertEqual((self.a.pos,self.p.pos),((4,2),(4,2)))
        self.assertEqual(self.e.rng.getstate(),rng)
        self.e.grid.blocking.remove((5,2))
        result=MOVE.follow_paid_path(self.e,self.a,path,mode='land',maximum_distance=6,progress=progress)
        self.assertEqual((result['distance'],progress['next'],self.p.spec[L.MOVEMENT]['distance']),(6,6,6))
        again=MOVE.follow_paid_path(self.e,self.a,path,mode='land',maximum_distance=6,progress=progress)
        self.assertEqual(again,result);self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],6)
        self.turn(self.p);budget=deepcopy(self.p.budget)
        self.assertEqual(self.e.approach(self.p,self.t)['distance'],0)
        self.assertEqual(self.p.budget,budget);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_native_entry_failure_rolls_back_joint_position_pool_action_and_rng(self):
        self.world();self.equip();self.turn(self.a)
        with patch.object(EXT,'on_enter_cell',side_effect=ValueError('actual entry consumer failed')):
            NATIVE.assert_rejected_unchanged(self.e,lambda:self.e.approach(self.a,self.t),
                                             reason_pattern='actual entry consumer failed')
        self.assertNotIn(L.MOVEMENT,self.p.spec)
        self.assertEqual((self.a.pos,self.p.pos),((2,2),(2,2)))
        self.assertEqual(self.a.budget['shift'],1)

    def test_sprint_and_detach_reattach_do_not_refill_the_same_round(self):
        self.world();self.equip();self.turn(self.a)
        self.assertTrue(self.e.sprint(self.a,source_policy='ch06_once'))
        self.assertEqual(self.e.approach(self.a,self.t)['distance'],6)
        self.assertEqual(self.a.budget['standard'],0)
        self.world();self.equip();self.turn(self.a)
        self.e.gm.set_position(self.t,(5,2),reason='actual two metre first route')
        self.assertEqual(self.e.approach(self.a,self.t)['distance'],2)
        self.e.separate_living_weapon(self.a,destination=(4,3))
        self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],2)
        # Both Standards remain available after that Shift and Swift. The
        # actual cooperative re-engagement does not create another allowance.
        self.e.equip_living_weapon(self.a,self.p,consent=True)
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(L.movement_remaining(self.e,self.a),4)
        self.restore();self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],2)
        self.assertIn(L.HISTORY,self.p.spec)
        self.e.gm.set_position(self.t,(20,3),reason='actual distant goal after re-engagement')
        self.turn(self.p)
        self.assertEqual(self.e.approach(self.p,self.t)['distance'],4)
        self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],6)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_aerial_burrow_and_teleport_commit_to_the_same_pool_without_replacing_permissions(self):
        for mode in ('sky','burrow','teleport'):
            for requested in (3,4):
                with self.subTest(mode=mode,requested=requested):
                    self.world(modes=(mode,));self.equip();self.turn(self.a)
                    if mode=='sky':
                        first=self.e.aerial_move(self.a,(5,2),mode='sky',altitude=0,reason_text='actual clear aerial route')
                    elif mode=='burrow':
                        first=self.e.burrow_move(self.a,[(2,2),(3,2),(4,2),(5,2)],diggable=True,
                                                reason_text='actual diggable route with surface exit',surface=True)
                    else:
                        first=self.e.teleport(self.a,(5,2),surface_contact=True,reason_text='actual visible surface')
                    self.assertEqual(first['distance'],3);self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],3)
                    self.turn(self.p);destination=(5+requested,2);rng=self.e.rng.getstate()
                    if mode=='sky':
                        second=self.e.aerial_move(self.p,destination,mode='sky',altitude=0,reason_text='actual clear aerial route')
                    elif mode=='burrow':
                        second=self.e.burrow_move(self.p,[(x,2) for x in range(5,6+requested)],diggable=True,
                                                 reason_text='actual diggable route with surface exit',surface=True)
                    else:
                        second=self.e.teleport(self.p,destination,surface_contact=True,reason_text='actual visible surface')
                    if requested==3:
                        self.assertEqual(second['distance'],3);used=6;position=(8,2)
                    else:
                        self.assertFalse(second);used=3;position=(5,2)
                        self.assertNotEqual(self.p.spec.get('_teleport',{}).get('used_round'),self.e.round_no)
                    self.assertEqual((self.a.pos,self.p.pos),(position,position))
                    self.assertEqual(self.p.spec[L.MOVEMENT]['distance'],used)
                    self.assertEqual(L.movement_remaining(self.e,self.p,movement_mode=mode),6-used)
                    self.assertEqual(self.e.rng.getstate(),rng)
                    self.assertEqual(self.p.budget['shift'],0)
                    self.assertTrue(self.e.validate_state()['valid'])

    def test_complete_no_guard_definitions_default_scope_restore_and_all_accuracy_endpoints(self):
        for variant,expected in ((None,[0,3,0,3]),('korean_unaffected',[0,3,0,3]),
                                 ('english_no_own_benefit',[0,3,3,3])):
            with self.subTest(variant=variant):
                self.world();choice=self.equip(variant);self.turn(self.a)
                pairs=((self.p,self.t),(self.a,self.t),(self.t,self.p),(self.t,self.a))
                baseline=self.modifiers(pairs)
                for actor in (self.a,self.p):
                    self.e.gm.set_ability(actor,NO_GUARD,reason='actual native No Guard ability')
                self.e.gm.snapshot('no-guard-source');self.e.gm.restore('no-guard-source');self.restore()
                self.assertEqual(self.p.spec[L.KEY].get('no_guard_choice'),choice)
                pairs=((self.p,self.t),(self.a,self.t),(self.t,self.p),(self.t,self.a))
                self.assertEqual([new-old for new,old in zip(self.modifiers(pairs),baseline)],expected)
                # Enemy No Guard still benefits/harms both ends in the English
                # alternative; the Korean alternative excludes it on the weapon.
                self.e.gm.set_ability(self.t,NO_GUARD,reason='actual opponent native No Guard')
                added=self.modifiers(pairs)
                extra=[3,3,3,3] if variant=='english_no_own_benefit' else [0,3,0,3]
                self.assertEqual([new-old for new,old in zip(added,baseline)],
                                 [x+y for x,y in zip(expected,extra)])
                self.assertTrue(self.e.validate_state()['valid'])

    def test_english_preserves_other_owners_negative_own_sources_and_bounded_unrelated_accuracy(self):
        for variant,expected in (('korean_unaffected',5),('english_no_own_benefit',6)):
            with self.subTest(variant=variant):
                self.world();self.equip(variant);self.turn(self.p)
                self.e.gm.set_ability(self.p,NO_GUARD,reason='actual own native No Guard')
                for sid,value,owner,rule in (('fixture:other',5,self.p.entity_id,'fixture/accuracy'),
                        ('fixture:third-party-no-guard',2,self.a.entity_id,'ability/노가드-playtest'),
                        ('fixture:negative-own-no-guard',-1,self.p.entity_id,'ability/노가드-playtest')):
                    G._source(self.p,sid,'fixture',owner_id=owner,rule_id=rule)
                    G.numeric(self.p,'accuracy_stage',value,sid,bounds=(-6,6))
                self.assertEqual(self.p.accuracy_stage,6)
                self.assertEqual(self.modifiers(((self.p,self.t),)),[expected])
                self.restore();self.assertEqual(self.modifiers(((self.p,self.t),)),[expected])
                self.e.separate_living_weapon(self.p,destination=(2,3))
                self.assertEqual(self.modifiers(((self.p,self.t),)),[6])
                self.assertIn(NO_GUARD,self.p.abilities)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_no_guard_and_borrowing_scopes_are_independent_and_stale_choices_reject_atomically(self):
        self.world();choice=self.choice('english_no_own_benefit');bad=deepcopy(choice)
        bad['scope']['definition_hash']='stale'
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:self.e.equip_living_weapon(self.a,self.p,consent=True,no_guard_choice=bad),
            reason_pattern='GM decision scope changed')
        borrowing=L.borrowing_choices(self.e)
        source={'value':'english_own_living_weapon','reason':'independent complete borrowing source',
                'scope':borrowing['decision_scope']}
        self.equip('english_no_own_benefit',source_choice=source);self.restore()
        self.assertEqual(self.p.spec[L.KEY]['source_choice'],source)
        self.assertEqual(self.p.spec[L.KEY]['no_guard_choice'],choice)
        self.p.spec[L.KEY]['no_guard_choice']['scope']['profile_hash']='stale'
        self.assertFalse(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
