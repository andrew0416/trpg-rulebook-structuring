"""Native source connections for S-c11a-1/2 and S-c11b-1..8. Prepared, not run."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import os
import sys
import unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT',str(STAGE)))
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(STAGE/'tools'),str(ROOT/'tools')]
from engine import Engine,Combatant
import actor_templates as T
import boss_transitions as B
import builder
import condition_instances as CONDITIONS
import frequency as F
import growth_milestones as MILESTONES
import growth_stats as GROWTH
import nicolette_gym as N
import native_scenario_fixture as NATIVE
import swarm_transitions as S
import turn as TURN
import body_state as BODY
from grid import Grid
import test_category2_swarm_transitions as SWARM
import test_category2_boss_transitions as BOSS
import test_category2_core_g041_g045_g050 as TERRAIN
import test_category2_linked_move_conditions as LINKED


class SwarmSourceRepairTests(unittest.TestCase):
    setUpClass=classmethod(SWARM.SwarmTransitionTests.setUpClass.__func__)
    setUp=SWARM.SwarmTransitionTests.setUp
    configure=SWARM.SwarmTransitionTests.configure
    open_turn=SWARM.SwarmTransitionTests.open_turn
    spend_move=SWARM.SwarmTransitionTests.spend_move

    def test_native_schedule_interleaves_enemy_and_never_refills_the_swarm_turn(self):
        self.configure(3)
        self.e.gm.set_initiative(self.p,20,reason='observed swarm initiative')
        self.e.gm.set_initiative(self.t,17,reason='observed enemy initiative')
        self.e.gm.set_temp_hp(self.t,500,reason='actual barrier keeps the interleaved observer present',duration_seconds=300)
        self.e.prepare_initiative_schedule(self.e.everyone,source='combat/initiative')
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p,initiative_count=20)
        first_turn=F.state(self.p)['turn']
        serial=self.p.custom_conditions['combat_turn_serial']
        history=deepcopy(self.p.spec['stage_change_history'])
        self.assertTrue(TURN.spend(self.e,self.p,'shift','actual first-window Shift',movement=True))
        shift=self.p.budget['shift']
        with patch.object(Engine,'d20',return_value=20):
            self.e.use_move(self.p,self.t,'move/몸통박치기',situational=100,set_damage=True)
        self.assertEqual(self.e.use_move(self.p,self.t,'move/몸통박치기',set_damage=True),0)
        self.assertEqual(self.e.end_of_turn(self.p)['initiative'],15)
        self.assertEqual(self.e._turn_closures,[])
        schedule=getattr(self.e,'_initiative_schedule')
        self.assertEqual(schedule['records'][-1]['outcome'],'swarm_action_closed')
        self.assertNotIn('closure_sequence',schedule['records'][-1])
        self.assertEqual(self.p.spec['stage_change_history'],history)
        self.assertEqual(self.e.initiative_schedule_status()['next']['actor_id'],self.t.entity_id)
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:self.e.start_of_turn(self.p,initiative_count=15),
            reason_pattern='next unconsumed schedule turn')
        self.e.start_of_turn(self.t,initiative_count=17);self.e.end_of_turn(self.t)
        for count in (15,10,5):
            self.assertEqual(self.e.initiative_schedule_status()['next']['initiative'],count)
            self.e.start_of_turn(self.p,initiative_count=count)
            self.assertEqual((F.state(self.p)['turn'],self.p.custom_conditions['combat_turn_serial'],
                              self.p.budget['shift']),(first_turn,serial,shift))
            self.assertEqual(self.p.spec['stage_change_history'],history)
            with patch.object(Engine,'d20',return_value=20):
                self.e.use_move(self.p,self.t,'move/몸통박치기',situational=100,set_damage=True)
            self.e.end_of_turn(self.p)
        row=S.state(self.p)
        actions=row['round_trigger_receipts'][row['own_turn_key']]['actions']
        self.assertEqual([a['initiative'] for a in actions],[20,15,10,5])
        self.assertEqual(row['swarm_points'],0)
        self.assertEqual(self.p.move_uses['move/몸통박치기'],4)
        self.assertEqual(sum(row['actor'] is self.p for row in self.e._turn_closures),1)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_incapacitation_replaces_denial_for_all_remaining_windows_and_zero_points(self):
        for condition in ('잠듦','얼음'):
            with self.subTest(condition=condition):
                self.setUp();self.open_turn(3,condition)
                for index,count in enumerate((20,15,10)):
                    if index:self.e.start_of_turn(self.p,initiative_count=count)
                    self.assertTrue(TURN.spend(self.e,self.p,'standard','actual surviving swarm action'))
                    self.e.end_of_turn(self.p)
                self.assertEqual(S.state(self.p)['swarm_points'],0)
                self.assertEqual(len(S.state(self.p)['round_trigger_receipts'][S.state(self.p)['own_turn_key']]['actions']),3)
        self.setUp();self.open_turn(1,'잠듦')
        self.assertEqual(S.state(self.p)['swarm_points'],0)
        self.assertTrue(TURN.spend(self.e,self.p,'standard','minimum one actual action'))
        self.assertIsNone(self.e.end_of_turn(self.p))

    def test_swift_window_does_not_reopen_when_its_standard_is_spent(self):
        self.open_turn(3)
        quick=self.r.move(SWARM.AT_WILL_SWIFT)
        self.p.registry.append({'type':'action_type_change','moves':quick['name'],'to':'swift'})
        self.assertTrue(self.spend_move(SWARM.AT_WILL_SWIFT)[0])
        self.assertTrue(self.spend_move(SWARM.AT_WILL)[0])
        self.assertFalse(self.spend_move(SWARM.AT_WILL_SWIFT)[0])
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.p,initiative_count=15)
        self.assertTrue(self.spend_move(SWARM.AT_WILL_SWIFT)[0])

    def test_closed_or_past_round_incapacitation_receipt_grants_no_permission(self):
        import action_lifecycle as ACTION
        self.open_turn(3,'잠듦')
        self.assertTrue(ACTION.status_permission(self.e,self.p,'standard'))
        self.e.end_of_turn(self.p,swarm_continue=False)
        self.assertFalse(ACTION.status_permission(self.e,self.p,'standard'))
        self.assertTrue(ACTION.unable_standard(self.p,engine=self.e))
        self.e.start_round(self.e.everyone)
        self.assertFalse(ACTION.status_permission(self.e,self.p,'standard'))

    def test_daily_swift_uses_the_swarm_scene_quota(self):
        self.open_turn(3)
        mid=SWARM.DAILY
        self.p.registry.append({'type':'action_type_change','moves':self.r.move(mid)['name'],'to':'swift'})
        for used in (1,2,3):
            self.assertTrue(F.move_allowed(self.e,self.p,mid)[0])
            self.e.use_move(self.p,self.p,mid)
            self.assertEqual(self.p.move_uses[mid],used)
        self.assertFalse(F.move_allowed(self.e,self.p,mid)[0])


class NicoletteSourceRepairTests(unittest.TestCase):
    setUpClass=classmethod(TERRAIN.NicoletteTerrainTests.setUpClass.__func__)
    setUp=TERRAIN.NicoletteTerrainTests.setUp

    def scene(self,trained):
        self.e.grid=Grid(12,12)
        N.configure(self.e,heights={(1,1):0,(1,2):3,(9,9):3,(3,1):0,(3,2):6},
            ladder_links=[((3,1),(3,2))],snow_cells=[(10,10)],brush_cells=[(10,11)],ice_cells=[(11,10)],
            pc_deploy_cells=[(10,9)],gym_deploy_cells=[(1,9)],nicolette_cell=(2,9),
            reason='GM adopts the cliff, linked ladder and remote snow, brush and ice cells')
        actor=self.ps[0]
        actor.pos=(1,1)
        for other in self.e.everyone:
            if other is not actor:other.on_field=False
        BODY.observe(self.e,actor,[(0,0)],reason='actual mapped one-cell climber')
        self.e.gm.set_movement_capabilities(actor,{'land':5},basis='current',reason='observed five metre land movement')
        if trained:N.train_team(self.e,self.t,[actor])
        self.e.start_round([actor]);self.e.start_of_turn(actor)
        return actor

    def test_nonadjacent_observed_cliff_rejects_before_any_action_cost(self):
        actor=self.scene(False)
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:N.climb(self.e,actor,(9,9),climb_id='far',route='cliff',skill='육상',
                fixed=[6,6],reason='distant but observed endpoints'),
            reason_pattern='adjacent horizontal endpoints')

    def test_wallclimber_keeps_the_standard_dc12_choice_with_five_metre_allowance(self):
        actor=self.scene(True)
        result=N.climb(self.e,actor,(1,2),climb_id='checked-with-capability',route='cliff',
            skill='육상',fixed=[6,6],reason='GM chooses the printed direct skill climb')
        self.assertEqual((result['passed'],result['cost'],result['dc']),(True,3,12))
        self.assertEqual((actor.pos,actor.budget['standard'],actor.budget['shift']),((1,2),0,1))


class BossSourceRepairTests(unittest.TestCase):
    setUpClass=classmethod(BOSS.BossTransitionTests.setUpClass.__func__)
    setUp=BOSS.BossTransitionTests.setUp
    configure=BOSS.BossTransitionTests.configure

    def test_native_haze_resets_to_selected_default_and_final_bar_default(self):
        for final in (False,True):
            with self.subTest(final=final):
                self.setUp()
                self.configure(count=2,effects=[{'when':'final_bar','kind':'set_attack_stage_6'}] if final else [])
                if final:self.e.lose_hp(self.p,self.p.hp,loss_kind='hp_setting')
                self.e.gm.set_move(self.a,'move/흑안개',True,reason='actual learned Haze')
                self.e.gm.set_stage(self.p,'atk',value=-2,reason='ordinary temporary stage change')
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=30)
                self.e.use_move_on(self.a,self.p,'move/흑안개',self.e.everyone)
                self.assertEqual(self.p.stages['atk'],6 if final else 2)

    def test_vortex_ticks_once_at_round_start_and_cannot_overflow_the_bar(self):
        self.configure(count=4)
        self.e.apply_status(self.p,'조이기',source='keyword/조이기')
        self.e.gm.set_hp(self.p,value=1,reason='current bar about to deplete')
        self.e.start_round(self.e.everyone)
        self.assertEqual((T.projection(self.p)['remaining_bars'],self.p.hp),(3,self.p.max_hp))
        for count in (20,15,10,5):
            with patch.object(Engine,'d20',return_value=1):
                self.e.start_of_turn(self.p,initiative_count=count);self.e.end_of_turn(self.p)
            self.assertEqual(self.p.hp,self.p.max_hp)
        self.e.start_round(self.e.everyone)
        self.assertEqual(self.p.hp,self.p.max_hp-self.e.tick_loss(self.p,1))

    def test_stagger_restores_exactly_one_of_two_actual_scene_uses(self):
        mid='move/나비춤'
        self.e.gm.set_move(self.p,mid,True,reason='actual possessed Scene x2 Move')
        self.configure(count=4,effects=[{'when':'bar_lost','kind':'refresh_scene_move','move_id':mid}])
        self.e.start_round(self.e.everyone)
        for count in (20,15,10):
            self.e.start_of_turn(self.p,initiative_count=count)
            if count != 15:self.e.use_move(self.p,self.p,mid)
            self.e.end_of_turn(self.p)
        self.assertEqual(self.p.move_uses[mid],2)
        self.e.lose_hp(self.p,self.p.hp,loss_kind='hp_setting')
        self.assertEqual(self.p.move_uses[mid],1)
        self.e.start_of_turn(self.p,initiative_count=5);self.e.use_move(self.p,self.p,mid)
        self.assertEqual(self.p.move_uses[mid],2)

    def test_stagger_and_ordinary_flinch_share_one_lost_slot_per_round(self):
        for ordinary_first in (False,True):
            with self.subTest(ordinary_first=ordinary_first):
                self.setUp();self.configure(effects=[{'when':'bar_lost','kind':'skip_next_turn'}])
                self.e.start_round(self.e.everyone);self.e.at_initiative_count(21)
                if ordinary_first:self.assertTrue(self.e.apply_status(self.p,'풀죽음',source='test/native-flinch'))
                self.e.lose_hp(self.p,self.p.hp,loss_kind='hp_setting')
                self.e.start_of_turn(self.p,initiative_count=20)
                self.assertFalse(TURN.spend(self.e,self.p,'standard','one skipped slot'))
                self.e.end_of_turn(self.p)
                self.assertFalse(self.e.apply_status(self.p,'풀죽음',source='test/same-round-second-flinch'))
                self.e.start_of_turn(self.p,initiative_count=15)
                self.assertTrue(TURN.spend(self.e,self.p,'standard','later slot remains'))


class BossLinkedTickRepairTests(unittest.TestCase):
    initial_moves=['move/몸통박치기','move/씨뿌리기','move/소금절이']
    setUpClass=classmethod(LINKED.LinkedMoveConditionTests.setUpClass.__func__)
    setUp=LINKED.LinkedMoveConditionTests.setUp

    def test_native_seed_and_salt_loss_share_round_boundary(self):
        for move_id in ('move/씨뿌리기','move/소금절이'):
            with self.subTest(move=move_id):
                self.setUp()
                self.e.gm.set_encounter_template(self.t,kind='boss',total_bars=4,
                    action_slots=[{'id':str(i),'initiative':count} for i,count in enumerate((20,15,10,5))],
                    reason='actual target is a four-action boss')
                self.e.use_move(self.p,self.t,move_id,situational=100,set_damage=True)
                self.e.end_of_turn(self.p)
                self.e.gm.set_hp(self.t,value=1,reason='current bar tests percentage overflow')
                self.e.start_round(self.e.everyone)
                self.assertEqual((T.projection(self.t)['remaining_bars'],self.t.hp),(3,self.t.max_hp))
                rows=CONDITIONS.records(self.t)
                record=next(r for r in rows if r['source']==move_id)
                self.assertEqual(len(record['applications']),1)
                for count in (20,15,10,5):
                    self.e.start_of_turn(self.t,initiative_count=count);self.e.end_of_turn(self.t)
                self.assertEqual(len(next(r for r in CONDITIONS.records(self.t) if r['source']==move_id)['applications']),1)
                self.assertEqual(self.t.hp,self.t.max_hp)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_ordinary_holder_cannot_copy_the_boss_round_tick_exception(self):
        import custom_condition_effects as CUSTOM
        self.e.use_move(self.p,self.t,'move/소금절이',situational=100,set_damage=True)
        record=next(r for r in CONDITIONS.records(self.t) if r['source']=='move/소금절이')
        damaged=deepcopy(record)
        damaged['applications']=[{'kind':'holder_round_tick','holder_id':self.t.entity_id,
            'turn':self.t.custom_conditions.get('combat_turn_serial',0),'at':self.e.elapsed_seconds,
            'types':list(self.t.types),'ticks':1,'tick':self.e.tick(self.t),
            'requested':self.e.tick(self.t),'round':self.e.round_no,'source_id':'C11-129'}]
        with self.assertRaisesRegex(ValueError,'actual boss round-start receipt'):
            CUSTOM.validate_record(self.t,damaged)


class BossCaptureRepairTests(unittest.TestCase):
    setUpClass=classmethod(BOSS.BossTransitionTests.setUpClass.__func__)

    def test_actual_capture_applies_gm_selected_lower_form_and_rejects_missing_choices(self):
        e=Engine(self.r,seed=1136)
        trainer=Combatant(self.r,builder.build_trainer(self.r,'actual captor',30,dict.fromkeys(builder.STATS,10)))
        draft=builder.build_pokemon(self.r,'꼬렛',70,abilities=[])
        high=[]
        # Milestone list order does not choose an admitted Ability source.
        for milestone,ability in (('creation','도주'),(20,'근성'),(40,'픽업')):
            self.assertIn(ability,MILESTONES.ability_options(self.r,dict(draft,abilities=high),milestone))
            self.assertEqual(self.r.selection.resolve_name(ability,('ability/',)),'ability/'+ability)
            self.r.selection.require_supported_version('ability/'+ability)
            high.append(ability)
        p=Combatant(self.r,builder.build_pokemon(self.r,'꼬렛',70,abilities=high,side='wild',pos=(1,0)))
        e.gm.add_combatant(trainer);e.gm.add_combatant(p)
        config=dict(kind='boss',total_bars=2,action_slots=[{'id':'first','initiative':20},{'id':'second','initiative':15}],
                    capture_level=30,reason='GM selects a level 30 normal catch')
        NATIVE.assert_rejected_unchanged(e,lambda:e.gm.set_encounter_template(p,**config),
                                       reason_pattern='explicit GM capture_choices')
        low=builder.build_pokemon(self.r,'꼬렛',30,abilities=[])
        choices={'strategy':'balanced','moves':low['moves'],'abilities':high[:2]}
        e.gm.set_encounter_template(p,**config,capture_choices=choices)
        identity=p.entity_id
        trainer.spec['items']={'몬스터볼':1}
        e.lose_hp(p,p.hp,loss_kind='hp_setting');e.gm.set_hp(p,value=1,reason='visible weakened final bar')
        e.start_round(e.everyone);e.start_of_turn(trainer,initiative_count=30)
        self.assertTrue(e.throw_ball(trainer,p,fixed_accuracy=20,fixed_capture=20))
        self.assertEqual((p.entity_id,p.level,p.abilities),(identity,30,high[:2]))
        self.assertEqual(p.moves,low['moves'])
        self.assertEqual(sum(GROWTH.project(self.r,p.spec)['investment'].values()),40)
        self.assertIsNone(T.active(p))
        self.assertIn('capture_reallocation_previous',p.spec['retired_encounter_templates'][-1]['state'])
        self.assertTrue(e.validate_state()['valid'])
