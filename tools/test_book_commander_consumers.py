"""Actual six Order consumers, source differences and changed native seams."""
from pathlib import Path
import sys,unittest,json
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from commander_fixture import CommanderFixture
from engine import Engine,Rules
import commander as C,commander_orders as O,class_passive_combat as P
import action_points as AP,weapon_actions as WEAPON,combat_timing as TIMING
import movement_actions as MOVE,action_lifecycle as ACTION,move_defense_reactions as DEFENSE
import action_resources as RESOURCES,passive_events as PASSIVE,blessing_effects as BLESS
import state_codec as CODEC


class CommanderConsumerTests(CommanderFixture,unittest.TestCase):
    def test_strike_again_immediate_known_atwill_attack_uses_scoped_native_grant(self):
        self.scene();self.combat();before=self.b.hp
        with patch.object(Engine,'d20',return_value=10):
            result=self.e.use_general_order(self.a,self.p,O.STRIKE,
                attack={'move':'move/물대포','target_id':self.b.entity_id})
        self.assertLess(self.b.hp,before);self.assertEqual(RESOURCES.pending(self.p),{})
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.p.move_uses['move/물대포'],1)
        self.assertEqual(result['source']['interpretation']['pages'],[60,61,62])
        self.assertEqual(self.e._action_grants,[])
        self.next_turn(self.p);self.assertEqual(self.p.budget['standard'],1)
        self.restore();self.valid()

    def test_strike_again_frequency_unknown_status_nonatwill_and_forged_grant_rejections(self):
        self.scene();self.combat()
        for move in ('move/성장','move/파도타기'):
            self.rejected(lambda move=move:self.e.use_general_order(self.a,self.p,O.STRIKE,
                attack={'move':move,'target_id':self.b.entity_id}),'damaging At-Will')
        self.rejected(lambda:self.e.use_general_order(self.a,self.p,O.STRIKE,
            attack={'move':'move/물대포','target_id':'absent/target'}),'immediate attack target')
        def forged():
            with ACTION.move_grant(self.e,self.p,self.b,'move/물대포',source=O.STRIKE,kind='free'):pass
        self.rejected(forged,'actual paid immediate Order')
        self.e.use_general_order(self.a,self.p,O.STRIKE,attack={'move':'move/물대포','target_id':self.b.entity_id})
        self.next_round()
        self.rejected(lambda:self.e.use_general_order(self.a,self.p,O.STRIKE,
            attack={'move':'move/물대포','target_id':self.b.entity_id}),'Scene frequency')

    def test_strike_again_late_actual_move_failure_rolls_back_all_actors_rng_action_and_quota(self):
        self.scene();self.combat()
        original=Engine._take_damage
        def failure(e,target,amount,*args,**kwargs):
            original(e,target,amount,*args,**kwargs)
            if target.entity_id==self.b.entity_id:raise ValueError('injected actual damage-consumer failure')
        with patch.object(Engine,'_take_damage',new=failure),patch.object(Engine,'d20',return_value=10):
            self.rejected(lambda:self.e.use_general_order(self.a,self.p,O.STRIKE,
                attack={'move':'move/물대포','target_id':self.b.entity_id}),'actual damage-consumer failure')

    def test_long_shot_doubles_origin_not_area_adds_distance_and_actual_critical_dice(self):
        self.scene(bundle='feat/명사수-지시');self.combat()
        single=self.r.move('move/물대포');area=self.r.move('move/파도타기')
        before_range=WEAPON.range_spec(self.e,single,self.p);before_area=WEAPON.range_spec(self.e,area,self.p)
        normal=self.e.roll_damage(self.p,self.b,single,set_damage=True)
        critical=self.e.roll_damage(self.p,self.b,single,crit=True,set_damage=True)
        self.e.use_general_order(self.a,self.p,O.LONG)
        after_range=WEAPON.range_spec(self.e,single,self.p);after_area=WEAPON.range_spec(self.e,area,self.p)
        self.assertEqual(after_range['origin'],2*before_range['origin'])
        if isinstance(before_area.get('origin'),(int,float)):self.assertEqual(after_area['origin'],2*before_area['origin'])
        self.assertEqual(after_area.get('size'),before_area.get('size'))
        distance=3
        self.assertEqual(self.e.roll_damage(self.p,self.b,single,set_damage=True)-normal,distance)
        self.assertGreater(self.e.roll_damage(self.p,self.b,single,crit=True,set_damage=True)-critical,distance)
        self.restore();self.valid();self.next_turn(self.p)
        self.assertTrue(O.live(self.e,self.p,O.LONG));self.e.end_of_turn(self.p)
        self.assertFalse(O.live(self.e,self.p,O.LONG))

    def test_long_shot_actual_extended_range_move_reaches_and_second_scene_use_is_retained(self):
        self.scene(bundle='feat/명사수-지시');self.e.gm.set_position(self.b,(10,2),reason='actual extended distance')
        self.combat();self.e.use_general_order(self.a,self.p,O.LONG);self.next_turn(self.p)
        before=self.b.hp;self.attack();self.assertLess(self.b.hp,before)
        self.next_round();self.e.use_general_order(self.a,self.p,O.LONG,edition='local_csv')
        self.assertEqual(O.live(self.e,self.p,O.LONG)[-1]['source']['record'],25)
        self.next_round()
        self.rejected(lambda:self.e.use_general_order(self.a,self.p,O.LONG),'Scene frequency')

    def test_dazzling_nonstat_evasion_increases_existing_movement_not_evasion(self):
        self.scene(bundle='feat/트릭스터-지시');self.p.evasion_mod=2;self.combat()
        movement=MOVE.capabilities(self.e,self.p);evasion=self.p.evasion('물리',engine=self.e)
        self.e.use_general_order(self.a,self.p,O.DAZZLING)
        self.assertEqual(MOVE.capabilities(self.e,self.p)['land'],movement['land']+2)
        self.assertEqual(MOVE.capabilities(self.e,self.p)['sky'],0)
        self.assertEqual(self.p.evasion('물리',engine=self.e),evasion)
        self.restore();self.valid()

    def test_dazzling_actual_missed_attack_still_debuffs_until_foe_next_turn_end(self):
        self.scene(bundle='feat/트릭스터-지시');self.combat();self.e.use_general_order(self.a,self.p,O.DAZZLING)
        self.next_turn(self.p);hp=self.b.hp;self.attack(natural=1)
        self.assertEqual(self.b.hp,hp)
        self.assertEqual(sum(row.get('all_roll_modifier',0) for row in TIMING.records(self.b)),-3)
        self.next_turn(self.b);self.assertEqual(sum(row.get('all_roll_modifier',0) for row in TIMING.records(self.b)),-3)
        self.e.end_of_turn(self.b);self.assertEqual(sum(row.get('all_roll_modifier',0) for row in TIMING.records(self.b)),0)
        self.restore();self.valid()

    def test_dazzling_actual_shift_crosses_enemy_occupied_square_and_does_not_end_there(self):
        self.scene(bundle='feat/트릭스터-지시')
        self.e.gm.set_position(self.p,(2,2),reason='actual moving actor')
        self.e.gm.set_position(self.b,(3,2),reason='actual occupied intermediate square')
        self.e.gm.set_position(self.z,(5,2),reason='actual destination approach target')
        for x in range(2,6):
            for y in (1,3):self.e.grid.blocking.add((x,y))
        for actor in (self.p,self.q,self.s):self.hears(actor)
        self.combat();self.e.use_general_order(self.a,self.p,O.DAZZLING);self.next_turn(self.p)
        result=self.e.approach(self.p,self.z)
        self.assertEqual(result['position'],(4,2));self.assertEqual(self.p.budget['shift'],0)
        self.assertEqual(sum(row.get('all_roll_modifier',0) for row in TIMING.records(self.b)),-3)
        self.restore();self.valid()

    def test_dazzling_core_per_foe_round_and_csv_one_foe_round_are_separate_sources(self):
        for edition,count in (('core',2),('local_csv',1)):
            with self.subTest(edition=edition):
                self.scene(bundle='feat/트릭스터-지시')
                self.e.gm.set_position(self.z,(6,2),reason='both actual foes in the Surf line')
                self.combat()
                row=self.e.use_general_order(self.a,self.p,O.DAZZLING,edition=edition)
                self.assertEqual(row['source']['edition'],edition)
                self.next_turn(self.p)
                with patch.object(Engine,'d20',return_value=10):
                    self.e.use_move_on(self.p,self.b,'move/파도타기',[self.b,self.z],set_damage=True)
                affected=sum(any(r.get('all_roll_modifier')==-3 for r in TIMING.records(c)) for c in (self.b,self.z))
                self.assertEqual(affected,count);self.restore();self.valid()

    def test_brace_actual_binding_standard_activation_round_quota_dr_and_native_release(self):
        self.scene(bundle='feat/가디언-지시');self.combat();initial=AP.available(self.a)
        self.e.use_general_order(self.a,self.p,O.BRACE)
        self.assertEqual(AP.available(self.a),initial-2);self.next_turn(self.p)
        self.assertTrue(self.e.brace_for_impact(self.p));self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(O.reduction(self.p),5);self.assertFalse(self.e.brace_for_impact(self.p))
        baseline=self.e.roll_damage(self.b,self.p,self.r.move('move/물대포'),set_damage=True)
        self.restore();self.valid();self.assertEqual(O.reduction(self.p),5)
        self.next_round();self.assertEqual(O.release(self.e,self.a,self.p),(1,0));self.assertEqual(AP.available(self.a),initial)
        self.assertEqual(self.e.roll_damage(self.b,self.p,self.r.move('move/물대포'),set_damage=True),baseline)

    def test_brace_self_status_move_optional_decline_accept_and_other_target_not_trigger(self):
        self.scene(bundle='feat/가디언-지시')
        self.e.gm.set_move(self.p,'move/단단해지기',reason='actual known self-only Status Move')
        self.combat();self.e.use_general_order(self.a,self.p,O.BRACE)
        self.choice('brace_for_impact',False);self.next_turn(self.p)
        self.e.use_move_on(self.p,self.p,'move/단단해지기',self.e.everyone,set_damage=True)
        self.assertEqual(O.reduction(self.p),0)
        self.next_round(self.p)
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='brace_for_impact']
        self.choice('brace_for_impact',True)
        self.e.use_move_on(self.p,self.p,'move/단단해지기',self.e.everyone,set_damage=True)
        self.assertEqual(O.reduction(self.p),5);self.restore();self.valid()

    def test_brace_competing_existing_stratagem_and_temporary_binding_owner_are_real(self):
        self.scene(bundle='feat/가디언-지시');self.acquire('feat/명사수-지시');self.combat()
        self.e.use_general_order(self.a,self.p,O.BRACE);self.next_round()
        self.rejected(lambda:self.e.issue_orders(self.a,P.TRICK_SHOT,self.p),'Stratagem|stratagem')
        row=O.live(self.e,self.p,O.BRACE)[0]
        import temporary_ap as TEMP
        self.assertEqual(TEMP.native_binding(self.e,self.a,row['id'],'commander_orders')[0],row)
        self.restore();self.valid();self.e.end_encounter();self.assertEqual(self.a.spec.get('ap_bound',{}),{})

    def test_sentinel_native_intercept_shift_payment_attempt_dr_and_issuer_clock(self):
        self.scene(bundle='feat/가디언-지시');self.leaders();self.combat()
        for actor,pos in ((self.a,(0,0)),(self.b,(2,2)),(self.p,(3,2)),(self.q,(3,5)),(self.s,(8,8))):
            self.e.gm.set_position(actor,pos,reason='actual native melee intercept geometry')
        for actor in (self.p,self.q,self.s):self.hears(actor)
        self.e.use_general_order(self.a,self.q,O.SENTINEL);self.next_turn(self.b)
        self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual chosen interceptor')
        with patch.object(Engine,'d20',return_value=10),self.assertRaises(PASSIVE.PassiveEventPending) as pending:
            self.e.use_move(self.b,self.p,'move/막치기',set_damage=True)
        event=pending.exception.event_id
        self.e.choose_move_defense(event,self.q,use=True,options={'path':[(3,5),(3,4),(3,3),(3,2)],
            'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6,6,6]}},reason='actual Sentinel attempt')
        self.assertEqual(RESOURCES.pending(self.q),{'shift':1})
        completion=list(self.e._move_completions.values())[-1]
        attempt=completion['defense'][self.p.entity_id]['attempts'][0]
        self.assertEqual(attempt['sentinel']['damage_reduction'],10)
        self.assertEqual(attempt['cost_profile']['action'],'shift')
        self.assertTrue(O.live(self.e,self.q,O.SENTINEL));self.next_turn(self.q)
        self.e.end_of_turn(self.q);self.assertTrue(O.live(self.e,self.q,O.SENTINEL))
        self.restore();self.valid();self.next_round(self.a);self.e.end_of_turn(self.a)
        self.assertFalse(O.live(self.e,self.q,O.SENTINEL))

    def test_perfect_aim_next_actual_damaging_attack_auto_hits_natural_one_and_consumes_once(self):
        self.scene(bundle='feat/정밀-지시');self.combat();self.e.use_general_order(self.a,self.p,O.PERFECT)
        self.next_turn(self.p);before=self.b.hp
        neutral=self.e.roll_damage(self.p,self.b,self.r.move('move/물대포'),set_damage=True)
        self.assertEqual(self.attack(natural=1),neutral);self.assertLess(self.b.hp,before)
        rows=O.records(self.p);self.assertTrue(rows[0]['ended']);self.assertIsNotNone(rows[0]['consumed_by'])
        self.restore();self.valid();self.next_round(self.p);before=self.b.hp
        self.attack(natural=1);self.assertEqual(self.b.hp,before)

    def test_perfect_aim_status_move_preserves_then_issuer_next_turn_end_expires(self):
        self.scene(bundle='feat/정밀-지시')
        self.e.gm.set_move(self.p,'move/단단해지기',reason='actual known self-only Status Move')
        self.combat();self.e.use_general_order(self.a,self.p,O.PERFECT)
        self.next_turn(self.p);self.e.use_move_on(self.p,self.p,'move/단단해지기',self.e.everyone,set_damage=True)
        self.assertTrue(O.live(self.e,self.p,O.PERFECT));self.assertIsNone(O.records(self.p)[0]['consumed_by'])
        self.next_round(self.a);self.e.end_of_turn(self.a);self.assertFalse(O.live(self.e,self.p,O.PERFECT))

    def test_perfect_aim_native_wonder_guard_bypass_keeps_ability_and_type_resistance_one_step(self):
        self.scene(bundle='feat/정밀-지시');self.e.gm.set_types(self.b,['물'],reason='actual resistant target')
        self.e.gm.set_ability(self.b,'불가사의부적',reason='actual defensive Ability');self.e.register_abilities(self.b)
        self.combat();self.e.use_general_order(self.a,self.p,O.PERFECT);self.next_turn(self.p)
        original=Engine.roll_damage;observed=[]
        def observe(e,actor,target,move,*args,**options):
            result=original(e,actor,target,move,*args,**options)
            if actor.entity_id==self.p.entity_id and target.entity_id==self.b.entity_id and options.get('_reaction_event') is not None:
                observed.append(dict(options['_reaction_event']['damage_formula']))
            return result
        before=self.b.hp
        with patch.object(Engine,'roll_damage',new=observe):self.assertGreater(self.attack(),0)
        self.assertLess(self.b.hp,before);self.assertEqual(observed[0]['multiplier'],0.25)
        self.assertIn('불가사의부적',self.b.abilities);self.assertFalse(self.b.abilities_suppressed)
        self.restore();self.valid()

    def test_perfect_aim_native_intercept_attempt_forbidden_without_spending_reactor(self):
        self.scene(bundle='feat/정밀-지시');self.combat();self.e.use_general_order(self.a,self.p,O.PERFECT)
        self.next_turn(self.p)
        self.e.watch_move_defense(self.b,[{'actor_id':self.z.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual watched interception')
        with self.assertRaises(PASSIVE.PassiveEventPending) as pending:self.attack()
        event=pending.exception.event_id;self.valid()
        self.rejected(lambda:self.e.choose_move_defense(event,self.z,use=True,options={'path':[(6,3),(6,2)],
            'skill':'육상','mode':'land','roll_options':{'fixed':[6,6,6]}},reason='attempt actual forbidden defense'),'Perfect Aim prohibits')
        self.e.choose_move_defense(event,self.z,use=False,reason='declined unavailable defense')
        self.assertEqual(RESOURCES.pending(self.z),{});self.restore();self.valid()

    def test_native_order_clock_source_acquisition_and_binding_json_tampering_rejected(self):
        for bundle,feature in (('feat/가디언-지시',O.BRACE),('feat/명사수-지시',O.LONG),('feat/정밀-지시',O.PERFECT)):
            with self.subTest(feature=feature):
                self.scene(bundle=bundle);self.combat();self.e.use_general_order(self.a,self.p,feature)
                self.restore();self.valid()
                self.imported_payload_rejected(O.records(self.p)[0]['id'],'forged/order/instance','Order|binding|source|AP|timed_type_contract')
                self.imported_payload_rejected(C.CORE_SHA,'f'*64,'Order|source|interpretation|timed_type_contract|static Feature acquisition integrity')

    def test_explicit_local_source_differences_and_ambiguous_translation_boundary(self):
        for bundle,feature,record in (('feat/명사수-지시',O.LONG,25),('feat/트릭스터-지시',O.DAZZLING,28),
                ('feat/가디언-지시',O.BRACE,30),('feat/가디언-지시',O.SENTINEL,31),('feat/정밀-지시',O.PERFECT,34)):
            with self.subTest(feature=feature):
                self.scene(bundle=bundle);self.combat();row=self.e.use_general_order(self.a,self.p,feature,edition='local_csv')
                self.assertEqual(row['source']['record'],record);self.restore();self.valid()
        self.scene(bundle='feat/트릭스터-지시');self.combat()
        self.rejected(lambda:self.e.use_general_order(self.a,self.p,O.DAZZLING,edition='local_translation'),'explicit source ruling')

    def test_perfect_aim_actual_protect_shield_is_bypassed_without_suppressing_other_abilities(self):
        self.scene(bundle='feat/정밀-지시');self.e.gm.set_move(self.b,'move/방어',reason='actual learned Protect')
        self.combat(self.b);self.e.use_move_on(self.b,self.b,'move/방어',self.e.everyone,set_damage=True)
        self.next_turn(self.a);self.e.use_general_order(self.a,self.p,O.PERFECT);self.next_turn(self.p)
        before=self.b.hp;self.assertGreater(self.attack(),0);self.assertLess(self.b.hp,before)
        self.restore();self.valid()

    def test_perfect_aim_target_blessing_forbidden_attacker_blessing_still_actual_available(self):
        self.scene(bundle='feat/정밀-지시')
        self.e.gm.set_ability(self.b,'재앙의그릇',reason='actual defensive Blessing creator')
        self.e.gm.set_ability(self.a,'재앙의구슬',reason='actual offensive Blessing creator')
        self.e.register_abilities(self.b);self.e.register_abilities(self.a)
        self.combat(self.b);self.e.activate_ability(self.b,'재앙의그릇',self.b)
        self.next_turn(self.a);self.e.activate_ability(self.a,'재앙의구슬',self.a)
        self.e.use_general_order(self.a,self.p,O.PERFECT);self.choice('team_blessing',True)
        self.next_turn(self.p);self.attack()
        defensive=BLESS.live(self.b)[0];offensive=BLESS.live(self.a)[0]
        self.assertEqual(defensive['decisions'],[]);self.assertEqual(BLESS.remaining(defensive),2)
        self.assertEqual(sum(d['selected'] for d in offensive['decisions']),1)
        self.restore();self.valid()

    def test_brace_real_temporary_moment_funding_ends_only_actual_native_binding_on_expiry(self):
        self.scene(bundle='feat/가디언-지시')
        import trainer_feature_acquisition as T,state_fields as SF,moment_of_action as MOMENT,temporary_ap as TEMP
        SF.base_patch(self.q,{'skills':{'매력':3,'명령':3}},reason='actual Moment of Action qualification')
        for uid in (MOMENT.TRAINING,MOMENT.CLASS,MOMENT.FEATURE):
            T.acquire_static(self.e,self.q,uid,acquisition_request_id='actual-second-issuer/'+uid)
        self.e.gm.observe_sensory_environment(self.q,self.a,paths={'auditory':True},present=True,reason='actual Moment delivery')
        self.combat()
        policy={'priority':'temporary_first','binding_expiry':'end_effect','reason':'actual explicit funding loss policy'}
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
        self.e.moment_of_action(self.q,[self.a],funding={self.a.entity_id:policy},
            allies={self.a.entity_id:{'allied':True,'reason':'actual observed party relationship'}})
        self.e.start_of_turn(self.a,initiative_count=20)
        self.e.use_general_order(self.a,self.p,O.BRACE)
        self.assertEqual(TEMP.bound_amount(self.a),1);self.restore();self.valid()
        self.next_round();self.e.at_initiative_count(20)
        self.assertFalse(O.live(self.e,self.p,O.BRACE));self.assertTrue(O.records(self.p)[0]['ended'])
        self.assertEqual(TEMP.bound_amount(self.a),0);self.restore();self.valid()

    def test_sentinel_brace_optional_trigger_uses_one_round_quota_and_native_attempt_evidence(self):
        self.scene(bundle='feat/가디언-지시');self.leaders();self.combat()
        self.e.use_general_order(self.a,self.q,O.BRACE);self.next_round()
        for actor,pos in ((self.a,(0,0)),(self.b,(2,2)),(self.p,(3,2)),(self.q,(3,5)),(self.s,(8,8))):
            self.e.gm.set_position(actor,pos,reason='actual native Brace/Sentinel geometry')
        for actor in (self.p,self.q,self.s):self.hears(actor)
        self.e.use_general_order(self.a,self.q,O.SENTINEL);self.choice('brace_for_impact',True)
        self.next_turn(self.b)
        self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual Sentinel attempt')
        with patch.object(Engine,'d20',return_value=10),self.assertRaises(PASSIVE.PassiveEventPending) as pending:self.e.use_move(self.b,self.p,'move/막치기',set_damage=True)
        self.e.choose_move_defense(pending.exception.event_id,self.q,use=True,options={'path':[(3,5),(3,4),(3,3),(3,2)],
            'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6,6,6]}},reason='actual source-owned attempt')
        self.assertEqual(O.reduction(self.q),5)
        self.assertEqual(len(O.live(self.e,self.q,O.BRACE)[0]['used_rounds']),1);self.restore();self.valid()

    def test_strike_actual_pending_defense_restore_completes_same_order_without_repayment(self):
        self.scene();self.combat()
        self.e.watch_move_defense(self.b,[{'actor_id':self.z.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual watched child Move')
        with patch.object(Engine,'d20',return_value=10),self.assertRaises(PASSIVE.PassiveEventPending) as pending:
            self.e.use_general_order(self.a,self.p,O.STRIKE,attack={'move':'move/물대포','target_id':self.b.entity_id})
        event=pending.exception.event_id;self.assertEqual(self.a.budget['standard'],0)
        self.restore();self.valid();self.e.choose_move_defense(event,self.z,use=False,reason='actual native decline')
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.p.move_uses['move/물대포'],1)
        self.assertEqual(self.a.spec[O.USES][0]['phase'],'complete');self.restore();self.valid()

    @patch.object(Engine,'d20',new=lambda engine:10)
    def test_scheme_strike_actual_pending_batch_resumes_each_native_child_and_cheers_once(self):
        self.scene();self.leaders(scheme=True)
        import moment_of_action as MOMENT,cheerleader as CHEER
        for uid in (MOMENT.TRAINING,MOMENT.CLASS):self.acquire(uid)
        self.choice('cheerleader','Cheered');self.combat()
        self.e.watch_move_defense(self.b,[{'actor_id':self.z.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual batch child watch')
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.issue_orders(self.a,O.STRIKE,self.p,modifier=C.SCHEME,additional_targets=[self.q,self.s],
                options={'attack':{'move':'move/물대포','target_id':self.b.entity_id}})
        self.e.gm.snapshot('pending-commander')
        self.e.gm.snapshots['pending-commander']['engine']['_commander_order_scope']['assignments'][1]['options']['attack']['move']='move/막치기'
        self.rejected(lambda:self.e.gm.restore('pending-commander',reason='actual changed stored child choice'),
            'Commander native choices|continuation|timed_type_contract')
        self.restore();self.valid();pending_count=0
        while C.scope(self.e,self.a) is not None:
            pending_count+=1;self.assertLessEqual(pending_count,3)
            try:self.e.choose_move_defense(self.e._passive_pending,self.z,use=False,reason='actual native decline for this child')
            except PASSIVE.PassiveEventPending:pass
        self.assertEqual(pending_count,1)
        self.assertEqual(len(self.a.spec[O.USES]),3);self.assertEqual(len(CHEER._uses(self.a)),1)
        completed=[row for row in self.e._move_completions.values() if row.get('commander_strike')]
        self.assertEqual(len(completed),3)
        self.assertEqual({row['actor'].entity_id for row in completed},{c.entity_id for c in (self.p,self.q,self.s)})
        self.assertTrue(all(row['phase']=='complete' for row in completed))
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0))
        for actor in (self.p,self.q,self.s):self.assertEqual(actor.move_uses['move/물대포'],1)
        self.restore();self.valid()

    def test_sentinel_failed_actual_intercept_still_pays_shift_and_retains_attempt_reduction(self):
        self.scene(bundle='feat/가디언-지시');self.leaders();self.combat()
        for actor,pos in ((self.a,(0,0)),(self.b,(2,2)),(self.p,(3,2)),(self.q,(3,5)),(self.s,(8,8))):
            self.e.gm.set_position(actor,pos,reason='actual failed native intercept geometry')
        for actor in (self.p,self.q,self.s):self.hears(actor)
        self.e.use_general_order(self.a,self.q,O.SENTINEL);self.next_turn(self.b)
        self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual failed attempt')
        with patch.object(Engine,'d20',return_value=10),self.assertRaises(PASSIVE.PassiveEventPending) as pending:self.e.use_move(self.b,self.p,'move/막치기',set_damage=True)
        hp=self.q.hp
        self.e.choose_move_defense(pending.exception.event_id,self.q,use=True,options={'path':[(3,5),(3,4),(3,3),(3,2)],
            'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[1,1,1]}},reason='actual failed skill check')
        attempt=list(self.e._move_completions.values())[-1]['defense'][self.p.entity_id]['attempts'][0]
        self.assertEqual(attempt['outcome'],'failed');self.assertEqual(attempt['sentinel']['damage_reduction'],10)
        self.assertEqual(RESOURCES.pending(self.q),{'shift':1});self.assertEqual(self.q.pos,(3,4))
        self.assertEqual(self.q.hp,hp);self.restore();self.valid()

    def test_perfect_aim_actual_natural_roll_still_supplies_critical_and_secondary_effect(self):
        self.scene(bundle='feat/정밀-지시');self.e.gm.set_move(self.p,'move/독침',reason='actual learned effect-bearing damaging Move')
        self.combat();self.e.use_general_order(self.a,self.p,O.PERFECT);self.next_turn(self.p)
        original=Engine.accuracy_check;seen=[]
        def observe(e,*args,**options):
            result=original(e,*args,**options);seen.append(result);return result
        with patch.object(Engine,'accuracy_check',new=observe):self.attack(move='move/독침',natural=20)
        self.assertEqual(seen[0],(True,20,True));self.assertIn('독',self.b.conditions)
        self.restore();self.valid()

    def test_new_order_instance_gm_snapshot_restore_preserves_binding_and_rejects_changed_saved_source(self):
        self.scene(bundle='feat/가디언-지시');self.acquire(C.MOBILIZE);self.combat()
        self.e.use_general_order(self.a,self.p,O.BRACE);C.mobilize(self.e,self.a,self.q)
        self.e.gm.snapshot('commander-contract');identifier=O.records(self.p)[0]['id']
        O.release(self.e,self.a,self.p);self.e.gm.restore('commander-contract',reason='actual source-owned binding restoration')
        self.assertEqual(O.live(self.e,self.p,O.BRACE)[0]['id'],identifier);self.valid()
        saved=self.e.gm.snapshots['commander-contract'];body=saved['combatants'][id(self.p)]
        body['spec'][O.KEY][0]['source']['sha256']='0'*64
        self.rejected(lambda:self.e.gm.restore('commander-contract',reason='actual tampered snapshot'),'Order|source|binding|timed_type_contract')

    def test_brace_core_round_and_local_turn_quota_follow_separate_actual_turns(self):
        for edition,second in (('core',False),('local_csv',True)):
            with self.subTest(edition=edition):
                import tumbler as T,trainer_feature_acquisition as TFA,state_fields as SF,items as ITEMS
                self.scene(bundle='feat/가디언-지시');self.leaders()
                self.q.spec['edges']=['edge/곡예사']
                SF.base_patch(self.q,{'skills':{'곡예':6,'육상':3,'전투':4,'집중':3},
                    'movement':dict(self.q.spec['movement'],high_jump=1,long_jump=2,power=4)},reason='actual imported Acrobat skills and complete capability totals')
                for move_id in ('move/성장','move/파도타기','move/전광석화'):
                    self.e.gm.set_move(self.q,move_id,add=False,reason='actual forgotten moves leave room for Tumbler grants')
                ITEMS.register_feats(self.e,self.q)
                for uid in T.FEATURES:TFA.acquire_static(self.e,self.q,uid,acquisition_request_id='actual-extra-turn/'+uid)
                self.combat();self.e.use_general_order(self.a,self.q,O.BRACE,edition=edition)
                self.next_turn(self.q);self.assertTrue(self.e.brace_for_impact(self.q))
                count=min(10,self.e.initiative_value(self.q).value//2)
                self.choice('burst_of_speed',count);self.e.end_of_turn(self.q)
                self.e.start_of_turn(self.q,initiative_count=count)
                self.assertEqual(self.e.brace_for_impact(self.q),second)
                self.assertEqual(len(O.live(self.e,self.q,O.BRACE)[0]['used_rounds']),2 if second else 1)
                self.restore();self.valid()


if __name__=='__main__':unittest.main()
