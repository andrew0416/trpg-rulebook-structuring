"""Whole Fighter/Command Versatility, actual native use and refusal boundaries."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import test_book_type_expertise_full as FIX
import versatility as V,frequency as F,trainer_feature_acquisition as T
import state_codec as CODEC,world_entities as W,state_grants as G,state_fields as SF
import action_points as AP,action_lifecycle as ACTION,turn as TURN,downtime as D

SCENE='move/똬리틀기'
SCENE2='move/나비춤'
ONCE='move/코튼가드'
DAILY='move/회복지령'
DAILY1='move/에어로블라스트'
ATWILL='move/몸통박치기'
MOVES=[SCENE,SCENE2,ONCE,DAILY,DAILY1,ATWILL]


class VersatilityFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def world(self,*,moves=None,rules=None):
        FIX.TypeExpertiseTests.setup(self,rules=rules,moves=MOVES if moves is None else moves)
        self.r=self.e.r
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],명령=4,교활=3,포켓몬학=3)},reason='actual named Versatility prerequisites')
        partners=[]
        for number,pos in enumerate(((2,2),(2,4))):
            spec={'id':'pokemon/versatility-'+str(number),'name':'actual exchange Pokemon '+str(number),'kind':'pokemon',
                  'level':30,'size':'중형','weight_kg':30,'weight_class':3,'stats':dict(self.a.spec['stats']),
                  'types':['노말'],'moves':list(MOVES),'abilities':[],'feats':[],'classes':[],'edges':[],
                  'skills':{'육상':3,'곡예':3},'movement':{'land':6,'sky':0},
                  'trainer_id':self.a.entity_id,'trainer':self.a.name}
            actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor,pos=pos,side='party',reason='actual own exchange Pokemon')
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual observed Pokemon body')
            self.e.gm.observe_loyalty(actor,6,reason='actual willing partner');partners.append(actor)
        self.p,self.p2=partners

    def acquire(self,feature=V.FIGHTER,*,actor=None,edition='core',stat='atk',request=None):
        selection={'edition':edition}
        if feature==V.FIGHTER:selection['stat']=stat
        return T.acquire_static(self.e,actor or self.a,feature,selection=selection,
            acquisition_request_id=request or 'versatility/'+feature+'/'+(actor or self.a).entity_id)

    def close(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)

    def turn(self,actor=None):
        self.close()
        if self.e.round_start_seconds is not None:self.e.end_round()
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=30)

    def use(self,actor,move):
        if move==DAILY:self.e.gm.set_hp(actor,value=max(1,actor.base_max_hp//3),reason='actual injured healing recipient')
        with patch.object(Engine,'d20',return_value=18):
            result=self.e.use_move(actor,self.t if move in (DAILY1,ATWILL) else actor,move,set_damage=move in (DAILY1,ATWILL))
        self.assertGreater(actor.move_uses.get(move,0),0)
        return result

    def spent(self,actor=None,move=ONCE):
        actor=actor or self.a;self.turn(actor);self.use(actor,move);self.turn(actor)

    def fighter(self,give=SCENE,restore=ONCE,**options):return self.e.fighters_versatility(self.a,give,restore,**options)
    def command(self,pokemon=None,give=SCENE,restore=ONCE,**options):
        return self.e.command_versatility(self.a,pokemon or self.p,give,restore,**options)
    def reject(self,operation,reason):return assert_rejected_unchanged(self.e,operation,reason_pattern=reason)
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])

    def cold(self):
        ids=[x.entity_id for x in (self.a,self.t,self.p,self.p2)]
        payload=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.r=Rules(ROOT,ruleset=self.r.ruleset.name);self.e=CODEC.load_engine(self.r,payload)
        self.a,self.t,self.p,self.p2=[W.actor_index(self.e)[uid] for uid in ids];self.valid()

    def test_fighter_two_actual_learned_limited_moves_not_permission_or_atwill(self):
        self.world(moves=[SCENE,ATWILL]);self.reject(self.acquire,'two actually learned')
        G.grant_moves(self.a,[ONCE],'actual/permission-only','effect',mode='permission')
        self.reject(self.acquire,'two actually learned')
        self.e.gm.set_move(self.a,DAILY,reason='actual second learned limited Move')
        row=self.acquire();self.assertEqual(set(row['snapshot']['known_moves']),{SCENE,ATWILL,DAILY})
        self.assertNotIn(ONCE,row['snapshot']['known_moves']);self.valid()

    def test_fighter_all_six_source_owned_stat_tags_replay_and_exact_choice(self):
        for stat in V.STATS:
            with self.subTest(stat=stat):
                self.world();before=self.a.stats[stat];row=self.acquire(stat=stat)
                self.assertEqual(self.a.stats[stat],before+1);self.assertEqual(self.acquire(stat=stat),row)
                self.reject(lambda:self.acquire(stat='accuracy'),'replay cannot change optional selection')
                self.assertEqual(self.a.stats[stat],before+1)
        self.cold();self.assertEqual(V.records(self.a,V.FIGHTER)[0][1]['snapshot']['selection']['stat'],'spe')

    def test_command_each_adept_alternative_and_declared_extended_rank(self):
        for skill in V.SKILLS:
            with self.subTest(skill=skill):
                self.world();SF.base_patch(self.a,{'skills':dict.fromkeys(V.SKILLS,3)},reason='actual no Adept named skill')
                self.reject(lambda:self.acquire(V.COMMAND),'Adept Command')
                SF.base_patch(self.a,{'skills':{**dict.fromkeys(V.SKILLS,3),skill:4}},reason='actual one Adept alternative')
                row=self.acquire(V.COMMAND);self.assertEqual(row['snapshot']['skills'][skill],4)
        self.world(rules=Rules(ROOT,ruleset='core'));self.r.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.천상',{'rank':12,'dice':'12d6','eng':'Celestial'},reason='U-001 declared campaign rank',rules=self.r)
        SF.base_patch(self.a,{'skills':{**dict.fromkeys(V.SKILLS,3),'명령':12}},reason='actual declared extended skill')
        self.assertEqual(self.acquire(V.COMMAND)['snapshot']['skills']['명령'],12);self.cold()

    def test_actual_scene_exchange_restores_native_reuse_without_fake_move_activation(self):
        self.world();self.acquire();self.spent();before=deepcopy(F.state(self.a)['moves']);uses=dict(self.a.move_uses)
        completions=set(self.e._move_completions);stages=dict(self.a.stages);budget=dict(self.a.budget)
        row=self.fighter();self.assertEqual((self.a.move_uses[SCENE],self.a.move_uses[ONCE]),(1,0))
        self.assertEqual(F.state(self.a)['moves'].get(SCENE),before.get(SCENE));self.assertEqual(self.a.stages,stages)
        self.assertEqual(set(self.e._move_completions),completions);self.assertEqual(self.a.budget,budget)
        self.assertEqual(row['forfeiture']['source'],V.FIGHTER);self.assertEqual(self.a._action_history,['free'])
        self.assertEqual(F.state(self.a)['restored_move_occurrences'][ONCE],before[ONCE])
        self.use(self.a,ONCE);self.assertEqual(self.a.move_uses[ONCE],uses[ONCE]);self.cold()

    def test_daily_to_scene_allowed_and_scene_to_daily_rejected_atomically(self):
        self.world();self.acquire();self.spent();self.fighter(DAILY,ONCE)
        self.assertEqual(self.a.move_uses[DAILY],1);self.assertNotIn(DAILY,F.state(self.a)['moves'])
        self.world();self.acquire();self.spent(move=DAILY)
        self.reject(lambda:self.fighter(SCENE,DAILY),'Scene to Daily');self.valid()

    def test_daily_restore_one_of_two_used_and_clears_only_recipient_scene_lock(self):
        self.world();self.acquire();self.spent(move=DAILY);self.e.end_scene()
        self.spent(move=DAILY);self.assertEqual(self.a.move_uses[DAILY],2)
        original=deepcopy(F.state(self.a)['moves'][DAILY]);self.fighter(DAILY1,DAILY)
        self.assertEqual(self.a.move_uses[DAILY],1);self.assertEqual(F.state(self.a)['restored_move_occurrences'][DAILY],original)
        self.assertNotIn(DAILY,F.state(self.a)['moves']);self.assertNotIn(DAILY1,F.state(self.a)['moves'])
        self.use(self.a,DAILY);self.assertEqual(self.a.move_uses[DAILY],2);self.cold()

    def test_scene_two_uses_restore_one_and_fighter_quota_is_once_scene(self):
        self.world();self.acquire();self.spent(move=SCENE2);self.turn();self.use(self.a,SCENE2);self.turn()
        self.assertEqual(self.a.move_uses[SCENE2],2);self.fighter(SCENE,SCENE2)
        self.assertEqual(self.a.move_uses[SCENE2],1);self.turn();self.reject(lambda:self.fighter(DAILY,SCENE2),'once per Scene')
        self.e.end_scene();self.spent();self.fighter();self.assertEqual(F.state(self.a)['activations'][V.FIGHTER]['used'],1)

    def test_fighter_real_initiative_trigger_before_after_other_turn_and_after_action(self):
        self.world();self.acquire();self.reject(self.fighter,'actual native Initiative')
        self.spent();self.close();self.e.start_of_turn(self.t,initiative_count=20)
        self.reject(self.fighter,'actual native Initiative');self.turn();self.use(self.a,ATWILL)
        self.reject(self.fighter,'trigger has already passed')
        self.turn();self.close();self.reject(self.fighter,'actual native Initiative')

    def test_simultaneous_native_free_start_action_does_not_close_trigger(self):
        self.world();self.acquire();self.spent()
        ACTION.triggered_free_action(self.e,self.a,'actual/simultaneous-free-start-effect')
        self.fighter();self.assertEqual(self.a._action_history,['free','free']);self.valid()

    def test_native_turn_start_marker_cold_restore_and_tamper_rejection(self):
        self.world();self.acquire();self.spent();self.cold();self.fighter();self.cold()
        row=self.a.spec[V.WINDOW];old=row['turn'];row['turn']=old+1
        with self.assertRaisesRegex(ValueError,'turn-start evidence'):self.e.export_state()
        row['turn']=old;self.valid()

    def test_command_actual_offturn_trainer_ap_and_pokemon_quota_no_second_command(self):
        self.world();self.acquire(V.COMMAND);self.spent(self.p);before=AP.available(self.a)
        history=list(self.p._action_history);budget=dict(self.p.budget);completions=set(self.e._move_completions)
        self.command();self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.p._action_history,history)
        self.assertEqual(self.p.budget,budget);self.assertEqual(set(self.e._move_completions),completions)
        self.assertEqual(F.state(self.p)['activations'][V.COMMAND]['used'],1)
        self.assertNotIn(V.COMMAND,F.state(self.a)['activations']);self.assertIn('free',self.a._action_history)
        self.assertNotIn('party_command_turns',self.a.spec);self.use(self.p,ONCE);self.cold()

    def test_focused_command_restricted_subject_quota_does_not_become_pokemon_action(self):
        import test_book_focused_command_full as FOCUS,focused_command as FC
        f=FOCUS.FocusedCommandFullTests();f.world()
        f.acquire(V.COMMAND,selection={'edition':'core'})
        f.e.gm.set_move(f.p,'move/막치기',add=False,reason='actual replaceable learned Move')
        for mid in (ONCE,SCENE):f.e.gm.set_move(f.p,mid,reason='actual exchange Move')
        f.battle();f.partner_turn(f.p);f.e.use_move(f.p,f.p,ONCE);f.close();f.e.end_round()
        f.battle();f.focused();f.partner_turn(f.p);before=AP.available(f.a)
        f.e.command_versatility(f.a,f.p,SCENE,ONCE)
        self.assertEqual(AP.available(f.a),before-1);self.assertEqual(f.p.move_uses[ONCE],0)
        self.assertEqual(f.p._action_history,[]);self.assertFalse(any(row['source_id'] in (V.COMMAND,SCENE) for row in FC.round_facts(f.p)))
        self.assertFalse(F.move_allowed(f.e,f.p,ONCE)[0]);self.assertEqual(FC.damage_modifier(f.e,f.p),-5);f.cold();f.valid()

    def test_command_once_per_each_pokemon_not_global_and_scene_reset(self):
        self.world();self.acquire(V.COMMAND);self.spent(self.p);self.command()
        self.spent(self.p2);self.command(self.p2);self.assertEqual(self.p2.move_uses[ONCE],0)
        self.spent(self.p);self.reject(self.command,'once per Scene')
        self.e.end_scene();self.spent(self.p);self.command();self.assertEqual(F.state(self.p)['activations'][V.COMMAND]['used'],1)

    def test_command_wrong_owner_type_no_ap_and_late_action_refuse_unchanged(self):
        self.world();self.acquire(V.COMMAND);self.spent(self.p)
        self.reject(lambda:self.e.command_versatility(self.t,self.p,SCENE,ONCE),'acquired')
        self.reject(lambda:self.e.command_versatility(self.a,self.t,SCENE,ONCE),'Pokemon')
        self.reject(lambda:self.e.command_versatility(self.a,None,SCENE,ONCE),'actual Command')
        self.e.gm.set_hp(self.a,value=0,reason='actual unconscious issuer')
        self.reject(self.command,'Free Action unavailable');self.e.gm.set_hp(self.a,value=20,reason='actual recovered issuer')
        AP.spend(self.a,AP.available(self.a));self.reject(self.command,'requires 1 AP')
        self.e.gm.set_position(self.p,(4,2),reason='actual adjacent melee target before the native late action')
        self.assertEqual(__import__('grid').cheb(self.p.pos,self.t.pos),1)
        self.turn(self.p);self.use(self.p,ATWILL);self.reject(self.command,'trigger has already passed')

    def test_exhausted_donor_unknown_atwill_same_unused_and_forgotten_recipient(self):
        self.world();self.acquire();self.spent();self.reject(lambda:self.fighter(ONCE,ONCE),'different Moves')
        self.reject(lambda:self.fighter(ATWILL,ONCE),'known Scene or Daily')
        self.reject(lambda:self.fighter(SCENE,SCENE2),'already used')
        self.e.gm.set_move(self.a,ONCE,add=False,reason='actual recipient forgotten')
        self.reject(self.fighter,'known Scene or Daily')
        self.e.gm.set_move(self.a,ONCE,reason='actual recipient relearned')
        self.use(self.a,SCENE);self.turn();self.use(self.a,SCENE2);self.turn();self.use(self.a,SCENE);self.turn()
        self.reject(self.fighter,'donor Move uses exhausted')

    def test_pure_forfeit_and_current_zero_cannot_be_promoted_to_used_capacity(self):
        self.world();self.acquire();self.acquire(V.COMMAND);self.spent(self.p)
        self.command(give=SCENE2);self.assertFalse(F.scene_move_was_used(self.p,SCENE2))
        self.turn(self.p);self.reject(lambda:self.command(give=SCENE,restore=SCENE2),'already used')
        self.spent();self.fighter(SCENE2,ONCE);self.turn()
        self.reject(lambda:F.preflight_restore_move_use(self.e,self.a,ONCE),'already used')

    def test_archived_actual_daily_use_then_native_forfeit_can_be_restored_by_both_features(self):
        for feature in (V.FIGHTER,V.COMMAND):
            with self.subTest(feature=feature):
                self.world();self.acquire(feature);subject=self.a if feature==V.FIGHTER else self.p
                exchange=(lambda give,restore:self.fighter(give,restore)) if feature==V.FIGHTER else (lambda give,restore:self.command(give=give,restore=restore))
                self.spent(subject,DAILY1);exchange(DAILY,DAILY1)
                self.assertEqual(subject.move_uses[DAILY1],0);archived=deepcopy(F.state(subject)['restored_move_occurrences'][DAILY1])
                self.e.end_scene();self.spent(subject,ONCE);exchange(DAILY1,ONCE)
                self.assertEqual(subject.move_uses[DAILY1],1);self.assertNotIn(DAILY1,F.state(subject)['moves'])
                self.e.end_scene();self.turn(subject);exchange(DAILY,DAILY1)
                self.assertEqual(subject.move_uses[DAILY1],0);self.assertEqual(F.state(subject)['restored_move_occurrences'][DAILY1],archived)
                self.reject(lambda:F.preflight_restore_move_use(self.e,subject,DAILY1),'already used');self.cold()

    def test_late_restore_failure_rolls_back_ap_quota_forfeiture_actions_and_rng(self):
        self.world();self.acquire(V.COMMAND);self.spent(self.p)
        with patch.object(F,'restore_scene_use',side_effect=ValueError('actual late native restore failure')):
            self.reject(self.command,'late native restore failure')
        self.command();self.assertEqual(self.p.move_uses[SCENE],1);self.valid()

    def test_actual_pp_up_effective_scene_cap_and_daily_cap_keep_one_forfeit(self):
        import items as I,vitamin_moves as VM
        for mid,basecap in ((SCENE,2),(DAILY,2)):
            with self.subTest(mid=mid):
                self.world();self.a.spec['items']={VM.PP:1};I.use_item(self.e,self.a,VM.PP,self.p,selected_move=mid)
                self.acquire(V.COMMAND);self.assertEqual(F.move_frequency(self.e,mid,self.p)[1],basecap+1)
                self.spent(self.p,move=mid)
                if mid==DAILY:self.e.end_scene()
                self.turn(self.p);self.use(self.p,mid);self.spent(self.p)
                self.command(give=mid);self.assertEqual(self.p.move_uses[mid],basecap+1)
                self.reject(lambda:F.preflight_forfeit_move(self.e,self.p,mid,source=V.COMMAND),'donor Move uses exhausted')
                self.assertEqual(F.move_frequency(self.e,mid,self.p)[1],basecap+1);self.cold()

    def test_native_center_and_rest_refresh_preserve_signed_forfeitures_without_subtracting_new_use(self):
        for refresh in ('center','rest','all'):
            with self.subTest(refresh=refresh):
                self.world();self.acquire();self.spent();self.fighter(DAILY,ONCE)
                original=deepcopy(F.state(self.a)['move_forfeitures']);self.close();self.e.end_encounter()
                if refresh=='center':D.pokemon_center(self.e,self.a)
                elif refresh=='rest':D.new_day(self.a);D.extended_rest(self.e,self.a,4)
                else:F.restore_all_moves(self.a)
                self.assertEqual(F.state(self.a)['move_forfeitures'],original)
                self.e.end_scene();self.spent(move=DAILY)
                owner,kind=F.preflight_restore_move_use(self.e,self.a,DAILY)
                self.assertIs(owner,self.a);self.assertEqual(kind,'daily');self.assertEqual(F.forfeited_uses(self.a,DAILY),0)
                self.fighter(DAILY1,DAILY);self.assertEqual(self.a.move_uses[DAILY],0);self.cold()

    def test_daily_forfeit_remains_spent_across_midnight_and_only_forfeit_is_not_used(self):
        self.world();self.acquire();self.spent();self.fighter(DAILY,ONCE);self.close();self.e.end_encounter()
        D.new_day(self.a);self.assertEqual(F.forfeited_uses(self.a,DAILY),1)
        self.reject(lambda:F.preflight_restore_move_use(self.e,self.a,DAILY),'already used');self.cold()

    def test_command_both_source_editions_preserve_all_three_exchange_directions(self):
        for edition in ('core','local_csv'):
            for give,restore in ((SCENE,ONCE),(DAILY,ONCE),(DAILY1,DAILY)):
                with self.subTest(edition=edition,give=give,restore=restore):
                    self.world();self.acquire(V.COMMAND,edition=edition);self.spent(self.p,move=restore)
                    self.command(give=give,restore=restore,edition=edition)
                    self.assertEqual((self.p.move_uses[give],self.p.move_uses[restore]),(1,0))
        self.world();self.acquire(V.COMMAND);self.spent(self.p,move=DAILY)
        self.reject(lambda:self.command(give=SCENE,restore=DAILY),'Scene to Daily')

    def test_fighter_retained_csv_stat_and_native_action_do_not_create_csv39_credit(self):
        self.world();self.acquire(edition='local_csv',stat='hp');self.spent()
        self.fighter(edition='local_csv');self.assertEqual(self.a.stats['hp'],101)
        self.assertEqual(V.records(self.a,V.FIGHTER)[0][1]['snapshot']['source']['record'],39);self.cold()

    def test_signed_forfeiture_sources_and_refresh_boundaries_reject_tampered_saves(self):
        self.world();self.acquire();self.spent();self.fighter(DAILY,ONCE)
        st=F.state(self.a);row=st['move_forfeitures'][0];old=row['source'];row['source']='feat/unreviewed'
        with self.assertRaisesRegex(ValueError,'reviewed Move-use forfeiture'):self.e.export_state()
        row['source']=old;self.close();self.e.end_encounter();D.pokemon_center(self.e,self.a)
        row=F.state(self.a)['move_forfeiture_refreshes'][DAILY];old=row['through'];row['through']=old+1
        with self.assertRaisesRegex(ValueError,'refresh evidence'):self.e.export_state()
        row['through']=old;self.cold()

    def test_command_native_transfer_keeps_subject_scene_quota_after_owner_changes(self):
        import pokemon_party as PARTY
        self.world();self.acquire(V.COMMAND)
        SF.base_patch(self.t,{'skills':dict(self.t.spec['skills'],명령=4)},reason='actual receiving Adept owner')
        self.acquire(V.COMMAND,actor=self.t)
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual old owner roster',roster=[self.p,self.p2])
        PARTY.configure(self.e,self.t,mode='unlimited',reason='actual receiving owner roster',roster=[])
        self.spent(self.p);self.command();self.use(self.p,ONCE);self.close();self.e.end_encounter()
        before=deepcopy(F.state(self.p)['activations'][V.COMMAND]);PARTY.transfer(self.e,self.a,target=self.p,new_owner=self.t,reason='actual ownership transfer',request_id='versatility/transfer')
        self.assertEqual(F.state(self.p)['activations'][V.COMMAND],before);self.turn(self.p)
        self.reject(lambda:self.e.command_versatility(self.t,self.p,SCENE,ONCE),'once per Scene');self.cold()

    def test_manual_entrypoints_are_native_and_imported_name_never_grants_receipt(self):
        self.world();self.turn();self.reject(lambda:self.e.manual_feat(self.a,V.FIGHTER),'two Move exchange')
        self.reject(lambda:self.fighter(),'actual acquired')
        self.acquire();self.spent();row=self.e.manual_feat(self.a,"Fighter's Versatility",adjustment={'give_move':SCENE,'restore_move':ONCE})
        self.assertEqual(row['source'],V.FIGHTER)
        self.acquire(V.COMMAND);self.spent(self.p);row=self.e.manual_feat(self.a,'융통 명령',self.p,adjustment={'give_move':DAILY,'restore_move':ONCE})
        self.assertEqual(row['source'],V.COMMAND);self.cold()

    def test_source_stat_withdrawal_keeps_spent_history_and_blocks_feature_without_receipt(self):
        self.world();self.acquire(stat='spe');self.spent();self.fighter();self.close();self.e.end_encounter()
        history=deepcopy(F.state(self.a));self.e.retrain_trainer_source(self.a,V.FIGHTER,request_id='versatility/retrain',reason='actual source withdrawal',
            gm_decision={'allowed':True,'reason':'GM reviewed this Feature'},retained_dependencies={})
        self.assertEqual(self.a.stats['spe'],30);self.assertFalse(V.records(self.a));self.assertEqual(F.state(self.a),history)
        self.turn();self.reject(self.fighter,'actual acquired');self.cold()

    def test_selected_source_catalog_and_actual_csv_records_preserve_membership(self):
        self.world()
        for feature,record in ((V.COMMAND,4),(V.FIGHTER,39)):
            with (ROOT/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
            self.assertEqual(rows[record-1][0],self.r.selection.units[feature]['title'])
            selected=V.source(self.r,feature,'local_csv');self.assertEqual(selected['record'],record)
            self.assertEqual(self.r.selection.units[feature]['source']['lines'],list(V.FEATURES[feature]))
        self.acquire(V.COMMAND,edition='local_csv');self.spent(self.p);self.command(edition='local_csv')
        def unreviewed():
            with patch.dict(self.r.ruleset.unit_versions,{V.COMMAND:'unreviewed'}):
                self.command()
        self.reject(unreviewed,'selection_profile_changed_rebuild_required')
        self.valid()

    def test_actual_rider_alias_keeps_forfeit_and_one_daily_restore_on_donor_pool(self):
        import test_category2_rider_move_permission as RIDER,move_permissions as P
        f=RIDER.RiderPermissionTests();f.r=Rules(ROOT,ruleset='all');f.setUp()
        f.e.gm.set_move(f.mount,DAILY1,reason='actual non-Exhaust borrowed Daily Move')
        P.activate_rider(f.e,f.a,DAILY1)
        with patch.object(Engine,'d20',return_value=18):f.e.use_move(f.a,f.target,DAILY1,set_damage=True)
        owner,kind=F.preflight_restore_move_use(f.e,f.a,DAILY1);self.assertIs(owner,f.mount);self.assertEqual(kind,'daily')
        F.restore_daily_use(f.e,f.a,DAILY1);self.assertEqual(f.mount.move_uses[DAILY1],0);self.assertNotIn(DAILY1,f.a.move_uses)
        F.forfeit_move(f.e,f.a,DAILY1,source=V.FIGHTER);self.assertEqual(f.mount.move_uses[DAILY1],1)
        self.assertIs(F.preflight_restore_move_use(f.e,f.a,DAILY1)[0],f.mount)
        F.restore_daily_use(f.e,f.a,DAILY1)
        assert_rejected_unchanged(f.e,lambda:F.preflight_restore_move_use(f.e,f.a,DAILY1),reason_pattern='already used')


if __name__=='__main__':unittest.main()
