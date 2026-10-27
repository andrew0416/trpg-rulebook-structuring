"""Whole C03-131, retained CSV19, and the literal Commander Voice combination."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from commander_fixture import CommanderFixture
from native_scenario_fixture import prepare_body
import focused_command as F,commander as C,commander_orders as O
import trainer_feature_acquisition as T,world_entities as W,state_codec as CODEC
import frequency as FREQUENCY,action_points as AP,turn as TURN
import pokemon_party as PARTY,party_actions as COMMANDS,items as ITEMS,state_fields as SF
import training_features as TRAIN,priority_limited as PRIORITY,combat_timing as TIME


class FocusedCommandFullTests(CommanderFixture,unittest.TestCase):
    def world(self,*,acquire=True,voice=False,limit=1,bundle='feat/명사수-지시',ruleset='core',crafting=False):
        self.scene(acquire=False,ruleset=ruleset,**({'initial_edges':['edge/몬스터볼']} if crafting else {}))
        SF.base_patch(self.a,{'skills':{'명령':6,'집중':5,'교활':5,'협박':5,'포켓몬학':5,
                                     '통찰':6,'매력':6,'육상':3,'곡예':3}},reason='actual printed skill ranks')
        if crafting:
            SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],기술학=3)},
                reason='actual source-qualified initial maker skills')
            self.a.spec.update(items={'몬스터볼 공구함':1,'화학 세트':1},money=1000,
                crafting_scrap={'몬스터볼':200,'스프레이':200})
        for actor,speed in ((self.a,30),(self.p,20)):
            stats=dict(actor.spec['stats']);stats['spe']=speed
            SF.base_patch(actor,{'stats':stats},reason='actual distinct native initiative')
        partners=[]
        for name,pos,speed in (('second commanded Pokemon',(3,2),19),('other owned Pokemon',(4,2),18)):
            spec=deepcopy(self.p.spec)
            for key in ('id','state_grants','party_membership','loyalty_observations'):spec.pop(key,None)
            spec.update(name=name,trainer_id=self.a.entity_id,trainer=self.a.name,
                        moves=['move/막치기','move/물대포','move/성장','move/판별'],feats=[],classes=[],edges=[])
            spec['stats']['spe']=speed;actor=Combatant(self.r,spec)
            self.e.gm.add_combatant(actor,pos=pos,side='party',reason='actual owned Pokemon')
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed actual Pokemon body')
            self.e.gm.observe_loyalty(actor,6,reason='actual willing partner');self.hears(actor);partners.append(actor)
        self.p2,self.third=partners
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual owned party',roster=[self.p,self.p2,self.third])
        self.e.configure_party_combat(self.a,battle_mode='league',reason='actual League command pool',
            command_limit=limit,gm_id='gm/focused-test' if limit!=1 else None)
        if acquire:self.acquire(F.FEATURE)
        if voice:self.acquire(bundle);self.acquire(F.VOICE)

    def battle(self,*,scheduled=False):
        participants=[self.a,self.p,self.p2] if scheduled else self.e.everyone
        if scheduled:self.e.prepare_battle_initiative(participants,battle_mode='league')
        self.e.start_round(participants)
        if scheduled:self.e.declare_scheduled_action(self.a,{'kind':'actual Focused Command declaration'})
        self.e.start_of_turn(self.a,initiative_count=30)

    def close(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)

    def partner_turn(self,partner):
        self.close();self.e.start_of_turn(partner,initiative_count=partner.stats['spe'])

    def focused(self,**options):return self.e.focused_command(self.a,[self.p,self.p2],**options)
    def voice(self,feature=O.LONG,**options):return self.e.focused_command_with_voice(self.a,[self.p,self.p2],feature,**options)

    def cold(self):
        ids=[a.entity_id for a in (self.a,self.p,self.p2,self.third,self.b)]
        state=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.r=Rules(ROOT,ruleset=self.ruleset_name);self.e=CODEC.load_engine(self.r,state)
        index=W.actor_index(self.e);self.a,self.p,self.p2,self.third,self.b=[index[uid] for uid in ids]

    def test_actual_acquisition_requires_master_and_each_named_expert_alternative_without_auto_voice(self):
        self.world(acquire=False)
        SF.base_patch(self.a,{'skills':{'명령':5,**dict.fromkeys(F.SKILLS,5)}},reason='actual below-Master Command')
        self.rejected(lambda:self.acquire(F.FEATURE),'Master Command')
        SF.base_patch(self.a,{'skills':{'명령':6,**dict.fromkeys(F.SKILLS,4)}},reason='none at Expert')
        self.rejected(lambda:self.acquire(F.FEATURE),'at Expert')
        for expert in F.SKILLS:
            self.world(acquire=False)
            SF.base_patch(self.a,{'skills':{'명령':6,**dict.fromkeys(F.SKILLS,4),expert:5}},reason='one actual Expert alternative')
            receipt=self.acquire(F.FEATURE)
            self.assertEqual(receipt['snapshot']['skills'][expert],5);self.assertIsNone(F.acquired(self.a,F.VOICE))
            self.assertEqual(receipt,self.acquire(F.FEATURE))
        self.cold();self.valid()

        self.world(acquire=False)
        self.rejected(lambda:SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],명령=7)},
            reason='undeclared numeric rank is not an acquired qualification'),'unresolved ordinary numeric')
        self.r.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.천상',
            {'rank':12,'dice':'12d6','eng':'Celestial'},reason='U-001 explicitly declared extended campaign rank',rules=self.r)
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],명령=12,집중=12)},reason='actual declared extended-rank Trainer sheet')
        receipt=self.acquire(F.FEATURE);self.assertEqual(receipt['snapshot']['command'],12)
        self.acquire(TRAIN.FOCUSED);voice=self.acquire(F.VOICE);self.assertEqual(voice['snapshot']['skills']['집중'],12)
        self.cold();self.valid()
        self.assertEqual(C.receipts(self.a,F.FEATURE)[0]['snapshot']['command'],12)

    def test_voice_prerequisite_is_two_actual_orders_not_unrelated_feats_or_one_order(self):
        self.world(acquire=False);self.rejected(lambda:self.acquire(F.VOICE),'two actually acquired')
        self.acquire(F.FEATURE);self.rejected(lambda:self.acquire(F.VOICE),'two actually acquired')
        self.acquire('feat/명사수-지시');receipt=self.acquire(F.VOICE)
        self.assertIn(F.FEATURE,receipt['snapshot']['orders']);self.assertGreaterEqual(len(receipt['snapshot']['orders']),2)
        self.cold();self.valid()
        original=list(self.a.spec['feats'])
        try:
            for extra,pattern in (('feat/위험물-소지허가증','Excluded rule selection'),(F.FEATURE,'duplicate feature')):
                self.a.spec['feats']=[*original,extra]
                with self.assertRaisesRegex(ValueError,pattern):F.known_orders(self.a)
        finally:self.a.spec['feats']=original

    def test_native_schedule_two_distinct_pokemon_turns_no_budget_refresh_and_round_expiry(self):
        self.world();self.battle(scheduled=True);self.focused()
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift'],self.a.budget['shift']),(0,0,1))
        for partner in (self.p,self.p2):
            self.partner_turn(partner);self.assertGreater(self.attack(actor=partner,move='move/막치기',natural=18),0)
        self.close();self.assertEqual([r['pokemon_id'] for r in self.a.spec['party_command_turns']],[self.p.entity_id,self.p2.entity_id])
        self.rejected(lambda:self.e.start_of_turn(self.p),'ordinary turn');self.assertEqual(self.p.budget['standard'],0)
        self.e.end_round();self.assertEqual(F.damage_modifier(self.e,self.p),0)
        self.e.prepare_battle_initiative([self.a,self.p,self.p2],battle_mode='league');self.e.start_round([self.a,self.p,self.p2])
        self.e.declare_scheduled_action(self.a,{'kind':'actual ordinary command'});self.e.start_of_turn(self.a);self.close()
        self.partner_turn(self.p);self.close();self.rejected(lambda:self.e.start_of_turn(self.p2),'already used the Pokemon')

    def test_targetless_core_and_targeted_csv_keep_actual_target_separate_from_affected_pair(self):
        self.world();self.battle();self.rejected(lambda:self.focused(target=self.p),'has no targets')
        self.rejected(lambda:self.focused(edition='local_csv'),'requires an explicit actual target')
        row=self.focused(edition='local_csv',target=self.b)
        self.assertEqual(row['source']['record'],19);self.assertEqual(row['target_id'],self.b.entity_id)
        self.assertEqual(row['pokemon_ids'],[self.p.entity_id,self.p2.entity_id]);self.assertEqual(F.damage_modifier(self.e,self.b),0)
        self.cold();self.valid()

    def test_wrong_pair_ownership_availability_and_no_turn_costs_reject_atomically(self):
        self.world();self.battle();self.rejected(lambda:self.e.focused_command(self.a,[self.p,self.p]),'two distinct')
        self.rejected(lambda:self.e.focused_command(self.a,[self.p,self.q]),'Pokemon|포켓몬')
        self.e.gm.recall(self.p2,reason='actual unavailable partner');self.rejected(lambda:self.focused(),'on the field')
        self.e.gm.send_out(self.p2,(3,2),reason='actual returned partner');TURN.spend(self.e,self.a,'swift','actual previous Swift action')
        self.rejected(lambda:self.focused(),'Standard and Swift');self.assertNotIn(F.KEY,self.a.spec)

    def test_non_at_will_native_moves_reject_before_type_boss_or_swarm_exceptions_and_do_not_pay(self):
        self.world();self.battle();self.focused();self.partner_turn(self.p2)
        self.assertNotEqual(FREQUENCY.move_frequency(self.e,'move/성장',self.p2)[0],'at_will')
        before=(deepcopy(self.p2.budget),deepcopy(self.p2.move_uses),self.b.hp,self.e.rng.getstate())
        with patch('type_ace.frequency_exception',return_value=True) as exception:
            self.assertEqual(self.e.use_move_on(self.p2,self.p2,'move/성장',self.e.everyone),0);exception.assert_not_called()
        self.assertEqual(before,(self.p2.budget,self.p2.move_uses,self.b.hp,self.e.rng.getstate()))
        self.assertFalse(FREQUENCY.activation_allowed(self.p2,'actual-limited-action',{'kind':'scene','uses':1},engine=self.e,action_actor=self.p2))
        self.assertTrue(FREQUENCY.activation_allowed(self.p2,'actual-other-actors-per-target-quota',{'kind':'scene','uses':1},engine=self.e))
        self.assertTrue(FREQUENCY.move_allowed(self.e,self.p2,'move/막치기')[0]);self.assertGreater(self.attack(actor=self.p2,move='move/막치기',natural=18),0)

    def test_round_start_ap_all_four_choices_change_real_move_and_damage_consumers(self):
        self.world();self.battle();self.partner_turn(self.p);ordinary=self.attack(actor=self.p,move='move/막치기',natural=18)
        for lift,cost in ((None,0),('frequency',1),('damage',1),('both',2)):
            with self.subTest(lift=lift):
                self.world();available=AP.available(self.a)
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.assertEqual(AP.available(self.a),available);self.battle();self.assertEqual(AP.available(self.a),available-cost)
                self.focused();self.partner_turn(self.p)
                self.assertEqual(FREQUENCY.move_allowed(self.e,self.p,'move/성장')[0],lift in ('frequency','both'))
                damage=self.attack(actor=self.p,move='move/막치기',natural=18)
                self.assertEqual(ordinary-damage,0 if lift in ('damage','both') else 5)
                self.assertEqual(F.damage_modifier(self.e,self.p2),0 if lift in ('damage','both') else -5)
                self.assertEqual(F.damage_modifier(self.e,self.third),0)

    def test_ap_only_actual_round_boundary_late_choices_and_insufficient_ap_are_atomic(self):
        self.world();self.e.prepare_focused_command_ap(self.a,'both');self.cold();AP.charge(self.a,AP.available(self.a),mode='spend')
        self.rejected(lambda:self.e.start_round(self.e.everyone),'insufficient available AP')
        self.assertIn(F.PENDING,self.a.spec);self.assertNotIn(F.AP_KEY,self.a.spec)
        self.world();self.battle();self.rejected(lambda:self.e.prepare_focused_command_ap(self.a,'damage'),'before the actual beginning')
        self.focused();self.close();self.e.end_round();self.e.prepare_focused_command_ap(self.a,'frequency');available=AP.available(self.a)
        self.e.start_round(self.e.everyone);self.assertEqual(AP.available(self.a),available-1);self.assertEqual(len(self.a.spec[F.AP_KEY]),1)

    def test_prior_first_pokemon_nonatwill_and_unpenalized_damage_cannot_bypass_whole_round_conditions(self):
        cases=((None,'move/성장','prior non-At-Will'),(None,'move/막치기','prior Damage Rolls'),
               ('frequency','move/성장',None),('damage','move/막치기',None),('both','move/파도타기',None))
        for lift,move,error in cases:
            with self.subTest(lift=lift,move=move):
                self.world();self.e.configure_party_combat(self.a,battle_mode='full_contact',reason='actual Pokemon acts before its Trainer')
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=40)
                self.attack(actor=self.p,target=self.p if move=='move/성장' else self.b,move=move,natural=18)
                self.assertEqual(self.p.move_uses[move],1);self.close();self.cold();self.e.start_of_turn(self.a,initiative_count=30)
                if error:self.rejected(lambda:self.focused(),error)
                else:self.focused();self.partner_turn(self.p2)

    def test_prior_atwill_miss_remains_eligible_without_inventing_before_first_turn_timing(self):
        self.world();self.e.configure_party_combat(self.a,battle_mode='full_contact',reason='actual mixed initiative')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=40)
        self.assertEqual(self.attack(actor=self.p,move='move/막치기',natural=1),0)
        self.close();self.e.start_of_turn(self.a,initiative_count=30);self.focused();self.partner_turn(self.p2)
        self.assertEqual(F.damage_modifier(self.e,self.p2),-5);self.assertEqual(len(self.a.spec['party_command_turns']),2)

    def test_midround_acquisition_cannot_erase_actual_prior_pokemon_action_facts(self):
        self.world(acquire=False);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=40)
        self.attack(actor=self.p,move='move/막치기',natural=18);self.close();self.e.start_of_turn(self.a,initiative_count=30)
        self.acquire(F.FEATURE);self.rejected(lambda:self.focused(),'prior Damage Rolls')
        self.cold();self.rejected(lambda:self.focused(),'prior Damage Rolls');self.valid()

    def test_actual_native_ability_action_not_ledger_owner_or_noaction_controls_frequency_restriction(self):
        self.world();self.e.gm.set_ability(self.p,'위협',reason='actual acquired encounter Swift Ability')
        self.battle();self.focused();self.partner_turn(self.p)
        self.rejected(lambda:self.e.activate_ability(self.p,'위협',self.b),'only At-Will')
        self.assertNotIn('encounter_used',self.p.spec['ability_native_actions']['ability/위협']);self.assertEqual(self.p.budget['swift'],1)
        self.e.gm.set_ability(self.p,'색채이론',reason='actual source-declared No Action Ability')
        before=deepcopy(F.round_facts(self.p));self.e.activate_ability(self.p,'색채이론',(self.p,{'birth_roll':2,'reason':'actual immutable birth color'}))
        self.assertEqual(F.round_facts(self.p),before);self.valid()

    def test_pickup_actual_scene_swift_action_is_gated_without_creating_or_charging_a_copy(self):
        for lift in (None,'frequency'):
            with self.subTest(lift=lift):
                self.world();self.e.gm.set_ability(self.p,'픽업',reason='actual acquired Scene Swift Ability')
                W.register_object(self.e,'focused/original',location={'kind':'unknown'},reason='actual held original',
                    kind='item_instance',item_rule_id='item/선제공격손톱',owner_id=self.third.entity_id)
                ITEMS.register_item(self.e,self.third,'선제공격손톱',source_instance_id='focused/original',as_held=True)
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.battle();self.focused();self.partner_turn(self.p)
                operation=lambda:self.e.activate_ability(self.p,'픽업',self.third,held_selection='focused/original')
                if lift:
                    row=operation();self.assertEqual(row['original_instance_id'],'focused/original')
                    self.assertEqual(self.p.budget['swift'],0);self.assertTrue(any(r['kind']=='scene' for r in F.round_facts(self.p)))
                else:
                    self.rejected(operation,'Pickup Scene frequency exhausted');self.assertEqual(self.p.budget['swift'],1)
                    self.assertNotIn('ability:픽업',FREQUENCY.state(self.p)['activations'])
                self.cold();self.valid()

    def test_local_grass_actual_scene_shift_action_requires_waiver_and_preserves_paid_replay(self):
        import field_effects as FIELD
        for lift in (None,'frequency'):
            with self.subTest(lift=lift):
                self.world();self.e.gm.set_ability(self.p,'곰팡이군주',reason='actual acquired Scene Shift Ability')
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.battle();self.focused();self.partner_turn(self.p)
                operation=lambda:self.e.activate_ability(self.p,FIELD.LOCAL_SOURCE,self.p,request_id='focused/grass')
                if lift:
                    row=operation();self.assertEqual(self.p.budget['shift'],0)
                    before=json.dumps(self.e.export_state(),sort_keys=True);self.assertEqual(operation(),row)
                    self.assertEqual(json.dumps(self.e.export_state(),sort_keys=True),before)
                    self.assertTrue(any(r['source_id']==FIELD.LOCAL_SOURCE and r['kind']=='scene' for r in F.round_facts(self.p)))
                else:
                    self.rejected(operation,'local Grass Scene frequency exhausted');self.assertEqual(self.p.budget['shift'],1)
                    self.assertFalse(FIELD.validate_local(self.e))
                self.cold();self.valid()

    def test_mettle_actual_triggered_free_action_is_not_confused_with_automatic_item_quota(self):
        import damage_reactions as DAMAGE,roughneck as ROUGH,test_book_roughneck_full as FIX
        for lift in (None,'frequency'):
            with self.subTest(lift=lift):
                self.world();rough=FIX.RoughneckTests();rough.rules=self.r;rough.e=self.e
                rough.t=rough.add('actual acquired Roughneck',(8,4),edges=[ROUGH.PRESENCE])
                rough.roughneck(ROUGH.METTLE)
                self.assertEqual(rough.t.kind,'trainer');self.assertEqual(len(ROUGH.records(rough.t,ROUGH.METTLE)),1)
                SF.base_patch(self.b,{'stats':dict(self.b.spec['stats'],atk=200)},reason='actual incoming attack exceeds the Roughneck Mettle threshold')
                self.choice('mettle',True)
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.battle();self.focused();self.partner_turn(self.p)
                dealt=self.e.resolve_attack_damage(self.b,rough.t,self.r.move('move/막치기'),set_damage=True,intercepted=True)
                self.assertGreater(dealt,0);self.assertEqual(self.b.stages['atk'],-2)
                self.assertEqual(FREQUENCY.state(rough.t)['activations'][DAMAGE.METTLE]['used'],1)
                self.assertIn('free',rough.t._action_history)
                self.assertFalse(any(r['source_id']==DAMAGE.METTLE for r in F.round_facts(self.p)))
                self.cold();self.valid()
        self.world();W.register_object(self.e,'focused/automatic',location={'kind':'unknown'},reason='actual automatic item',
            kind='item_instance',item_rule_id='item/허탕보험',owner_id=self.p.entity_id)
        ITEMS.register_item(self.e,self.p,'허탕보험',source_instance_id='focused/automatic',as_held=True)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=40)
        self.assertEqual(self.attack(actor=self.p,move='move/막치기',natural=1),0)
        self.assertTrue(self.p.spec.get('held_item_reaction_history'));self.close();self.e.start_of_turn(self.a,initiative_count=30)
        self.focused();self.assertTrue(all(r['kind']=='at_will' for r in F.round_facts(self.p)));self.cold();self.valid()

    def test_crafted_fashion_actual_scene_free_action_keeps_maker_and_effect_ownership(self):
        import test_category2_fashion_item_contracts as FIX,effect_lifetimes as LIFETIMES
        for lift in (None,'frequency'):
            with self.subTest(lift=lift):
                self.world(ruleset='homebrew',crafting=True)
                maker=FIX.FashionItemContractTests();maker.rules=self.r;maker.e=self.e;maker.a=self.a
                recipe=maker.recipe();item='item/귀여운-패션-1';recipe['output']={'item_id':item,'key':item}
                maker.craft(recipe,product_policy={'mode':'create','instance_ids':['focused/fashion'],
                    'owner_id':self.p.entity_id,'state':'intact','attachments':[]},event_id='focused/make-fashion')
                ITEMS.register_item(self.e,self.p,item,source_instance_id='focused/fashion',as_held=True)
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.battle();self.focused();self.partner_turn(self.p)
                operation=lambda:self.e.activate_fashion_item(self.p,item)
                if lift:
                    operation();self.assertEqual(LIFETIMES.numeric(self.p,'evasion_modifier'),2)
                    self.assertTrue(any(r['source_id']=='fashion:focused/fashion' and r['kind']=='scene' for r in F.round_facts(self.p)))
                else:
                    self.rejected(operation,'Fashion scene activation is exhausted')
                    self.assertEqual(LIFETIMES.numeric(self.p,'evasion_modifier'),0)
                self.cold();self.valid()

    def test_selected_optional_native_limited_action_is_not_exempt_from_focused_round(self):
        # Retained allocation ID: actual selected optional Pokemon action, not an
        # invented grant of the Trainer-only-origin ERRATA-056 Feature to a Pokemon.
        # The optional _spend adapter retains its original actual-Trainer impact test.
        import field_effects as FIELD
        for lift in (None,'frequency'):
            with self.subTest(lift=lift):
                self.world(ruleset='all');self.e.gm.set_ability(self.p,'곰팡이군주',reason='actual optional Pokemon Scene Shift Ability')
                if lift:self.e.prepare_focused_command_ap(self.a,lift)
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=40)
                self.e.activate_ability(self.p,FIELD.LOCAL_SOURCE,self.p,request_id='focused/prior-optional-grass')
                self.assertTrue(any(r['source_id']==FIELD.LOCAL_SOURCE and r['kind']=='scene' for r in F.round_facts(self.p)))
                self.close();self.e.start_of_turn(self.a,initiative_count=30)
                if lift:
                    self.focused();self.assertFalse(F.restricted(self.e,self.p))
                else:
                    self.rejected(lambda:self.focused(),'prior non-At-Will action');self.assertNotIn(F.KEY,self.a.spec)
                self.cold();self.valid()

    def test_damage_roll_observer_excludes_fixed_hp_loss_and_includes_absorbed_actual_roll(self):
        self.world();self.e.gm.set_move(self.p,'move/용의분노',reason='actual fixed HP-loss Move')
        self.e.prepare_focused_command_ap(self.a,'frequency');self.battle();self.focused();self.partner_turn(self.p)
        before=self.b.hp;self.attack(actor=self.p,move='move/용의분노',natural=18)
        self.assertEqual(before-self.b.hp,15);self.assertFalse(any(r['kind']=='damage_roll' for r in F.round_facts(self.p)))
        before=self.b.hp;self.e.lose_hp(self.b,11,source='actual non-attack HP loss')
        self.assertEqual(before-self.b.hp,11);self.assertFalse(any(r['kind']=='damage_roll' for r in F.round_facts(self.p)))
        self.world();self.e.gm.set_ability(self.b,'저수',reason='actual absorbing defense')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=40)
        self.assertEqual(self.attack(actor=self.p,move='move/물대포',natural=18),0)
        self.assertTrue(any(r['kind']=='damage_roll' and r['penalty']==0 for r in F.round_facts(self.p)))
        self.close();self.e.start_of_turn(self.a,initiative_count=30)
        self.rejected(lambda:self.focused(),'prior Damage Rolls');self.cold();self.valid()

    def test_actual_trickster_per_pokemon_scene_quota_does_not_become_that_pokemons_action(self):
        import test_book_trickster_full as FIX,trickster as TRICK
        f=FIX.TricksterFullTests();f.rules=Rules(ROOT,ruleset='core');f.setup();f.family()
        SF.base_patch(f.t,{'skills':dict(f.t.spec['skills'],명령=6,집중=5)},reason='actual Focused Command prerequisites')
        T.acquire_static(f.e,f.t,F.FEATURE,acquisition_request_id='actual-focused-with-trickster')
        f.e.configure_party_combat(f.t,battle_mode='league',reason='actual one Pokemon pool');f.learn('move/친해지기')
        f.begin(f.t);f.e.focused_command(f.t,[f.p,f.q]);f.close();f.e.start_of_turn(f.p,initiative_count=40)
        with patch.object(Engine,'d20',return_value=18):f.e.escape_artist(f.t,f.p,f.foe,'move/친해지기',(2,3))
        facts=F.round_facts(f.p);self.assertTrue(any(r['source_id']=='move/친해지기' for r in facts))
        self.assertFalse(any(r['source_id'].startswith(TRICK.ESCAPE) for r in facts));f.restore();f.valid()

    def test_actual_rider_move_uses_donor_pool_without_claiming_donor_took_the_action(self):
        import test_category2_rider_move_permission as FIX,move_permissions as PERMISSIONS
        f=FIX.RiderPermissionTests();f.r=Rules(ROOT,ruleset='all');f.setUp();mid='move/에어로블라스트'
        f.e.gm.set_move(f.mount,mid,reason='actual non-Exhaust donor Move');PERMISSIONS.activate_rider(f.e,f.a,mid)
        f.e.use_move(f.a,f.target,mid)
        self.assertEqual(f.mount.move_uses[mid],1);self.assertFalse(F.round_facts(f.mount));self.assertEqual(f.a.budget['standard'],0)

    def test_manual_entrypoint_is_native_and_imported_name_does_not_grant_actual_ownership(self):
        self.world(acquire=False);self.battle();self.rejected(lambda:self.focused(),'actual acquired')
        self.world();self.battle();self.rejected(lambda:self.e.manual_feat(self.a,F.FEATURE,self.p),'commanded Pokemon identities')
        row=self.e.manual_feat(self.a,F.FEATURE,None,adjustment={'pokemon_ids':[self.p.entity_id,self.p2.entity_id]})
        self.assertEqual(row['pokemon_ids'],[self.p.entity_id,self.p2.entity_id]);self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0))

    def test_registration_is_not_global_minus_five_and_native_gm_three_cap_is_not_four(self):
        self.world(limit=3);ITEMS.register_feats(self.e,self.a);self.assertFalse(any(e.get('_rule_id')==F.FEATURE for e in self.a.registry))
        self.battle();self.focused();self.assertEqual(COMMANDS.command_limit(self.e,self.a),3);self.assertEqual(F.damage_modifier(self.e,self.a),0)
        for partner in (self.p,self.p2,self.third):
            self.partner_turn(partner);self.assertGreater(self.attack(actor=partner,move='move/막치기',natural=18),0)
        self.assertEqual(F.damage_modifier(self.e,self.third),0);self.assertEqual(len(self.a.spec['party_command_turns']),3)
        self.world(limit=3);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.third,initiative_count=40)
        self.attack(actor=self.third,move='move/막치기',natural=18);self.close()
        self.e.start_of_turn(self.a,initiative_count=30);self.focused()
        self.assertEqual(COMMANDS.command_limit(self.e,self.a),3);self.assertEqual(F.damage_modifier(self.e,self.third),0)

    def test_voice_other_scene_order_delivers_to_both_one_frequency_and_compound_cost(self):
        self.world(voice=True);self.battle();self.rejected(lambda:self.voice(action='swift'),'cannot use Focused Command as a Swift')
        result=self.voice();self.assertEqual(result['target_ids'],[self.p.entity_id,self.p2.entity_id])
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0))
        for partner in (self.p,self.p2):self.assertEqual([r['feature'] for r in O.records(partner)],[O.LONG])
        self.assertEqual(FREQUENCY.state(self.a)['activations'][O.LONG]['used'],1)
        self.assertEqual(self.a.spec[C.ACTIVATIONS][-1]['orders'][0],{'feature':F.FEATURE,'target_id':None});self.cold();self.valid()
        self.world(voice=True);self.hears(self.b);self.battle();result=self.voice(edition='local_csv',target=self.b)
        self.assertEqual(result['target_ids'],[self.p.entity_id,self.p2.entity_id])
        self.assertEqual(self.a.spec[C.ACTIVATIONS][-1]['orders'][0],{'feature':F.FEATURE,'target_id':self.b.entity_id})
        self.assertFalse(O.records(self.b));self.cold();self.valid()

    def test_voice_failed_second_delivery_rolls_back_first_effect_command_and_both_actions(self):
        self.world(voice=True);self.hears(self.p2,False);self.battle();self.rejected(lambda:self.voice(),'communication was not delivered')
        self.assertNotIn(F.KEY,self.a.spec);self.assertNotIn(C.ACTIVATIONS,self.a.spec)
        self.assertFalse(O.records(self.p));self.assertFalse(O.records(self.p2));self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(1,1))

    def test_voice_real_pending_strike_restores_and_resumes_both_native_children_without_repayment(self):
        import passive_events as PASSIVE
        self.world(voice=True,bundle='feat/유린-지시');self.battle();reactor_id=self.z.entity_id
        self.e.watch_move_defense(self.b,[{'actor_id':reactor_id,'source':'maneuver/원거리-가로채기'}],reason='actual Voice child native defense')
        with patch.object(Engine,'d20',return_value=10),self.assertRaises(PASSIVE.PassiveEventPending):
            self.voice(O.STRIKE,options={'attack':{'move':'move/물대포','target_id':self.b.entity_id}})
        before=self.e.export_state()
        for call in (lambda:self.e.prepare_focused_command_ap(self.a,'damage'),self.focused,self.voice,
                     lambda:self.e.manual_feat(self.a,F.FEATURE,adjustment={'pokemon_ids':[self.p.entity_id,self.p2.entity_id]})):
            with self.assertRaises(PASSIVE.PassiveEventPending):call()
            self.assertEqual(self.e.export_state(),before)
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0));self.cold();self.valid()
        reactor=W.actor_index(self.e)[reactor_id]
        with patch.object(Engine,'d20',return_value=10):
            while C.scope(self.e,self.a) is not None:
                try:self.e.choose_move_defense(self.e._passive_pending,reactor,use=False,reason='actual native child defense decline')
                except PASSIVE.PassiveEventPending:pass
        self.assertEqual([p.move_uses['move/물대포'] for p in (self.p,self.p2)],[1,1])
        self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,0));self.assertTrue(all(row['phase']=='complete' for row in self.a.spec[O.USES]));self.cold();self.valid()

    def test_actual_attached_league_driver_owns_focused_public_and_manual_boundaries(self):
        from test_category3_batch15_pokemon import Tests as LeagueFixture
        fixture=LeagueFixture();fixture.r=Rules(ROOT,ruleset='core');fixture.setUp();e=fixture.e
        self.assertEqual(e.start_league([('a',fixture.a,fixture.p),('b',fixture.b,fixture.q)],mode='league')['status'],'ready')
        before=e.export_state()
        for call in (lambda:e.prepare_focused_command_ap(fixture.a,'damage'),
                     lambda:e.focused_command(fixture.a,[fixture.p,fixture.q]),
                     lambda:e.focused_command_with_voice(fixture.a,[fixture.p,fixture.q],O.LONG),
                     lambda:e.manual_feat(fixture.a,F.FEATURE,adjustment={'pokemon_ids':[fixture.p.entity_id,fixture.q.entity_id]})):
            with self.assertRaisesRegex(ValueError,'League driver owns'):call()
            self.assertEqual(e.export_state(),before)

    def test_voice_does_not_retarget_original_allied_trainer_only_order_onto_pokemon(self):
        import moment_of_action as MOMENT
        self.world()
        for feature in (MOMENT.TRAINING,MOMENT.CLASS,MOMENT.FEATURE,F.VOICE):self.acquire(feature)
        from test_book_moment_of_action import FUNDING
        options={'funding':{p.entity_id:deepcopy(FUNDING) for p in (self.p,self.p2)},
                 'allies':{p.entity_id:{'allied':True,'reason':'actual willing allied Pokemon'} for p in (self.p,self.p2)}}
        self.battle();self.rejected(lambda:self.voice(MOMENT.FEATURE,options=options),'Trainer|trainer')
        self.assertNotIn(F.KEY,self.a.spec);self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(1,1))

    def test_voice_core_and_retained_csv_training_use_real_native_lifetime_and_payment(self):
        for edition in ('core','local_csv'):
            with self.subTest(edition=edition):
                self.world();self.acquire(TRAIN.FOCUSED);self.acquire(F.VOICE);self.battle();self.voice(TRAIN.FOCUSED,options={'edition':edition})
                self.assertEqual([TRAIN.bonus(p,'accuracy') for p in (self.p,self.p2)],[1,1]);self.assertFalse(PRIORITY.records(self.a))
                self.cold();self.valid();self.close();self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
                self.assertEqual([TRAIN.bonus(p,'accuracy') for p in (self.p,self.p2)],[0,0])

    def test_voice_critical_native_trained_two_pokemon_keeps_scene_quota_and_next_owner_turn_end(self):
        import test_book_ace_trainer_full as FIX,ace_trainer as ACE
        f=FIX.AceTrainerFullTests();f.rules=Rules(ROOT,ruleset='core');f.setup();f.family(ACE.CRITICAL);f.all_training();f.train([TRAIN.FOCUSED])
        SF.base_patch(f.t,{'skills':dict(f.t.spec['skills'],협박=5)},reason='actual Expert Focused alternative')
        for feature in (F.FEATURE,F.VOICE):f.acquire(feature)
        for partner in (f.p,f.q):f.e.gm.observe_sensory_environment(f.t,partner,paths={'auditory':True},present=True,reason='actual combined Critical delivery')
        f.e.configure_party_combat(f.t,battle_mode='league',reason='actual command pool');f.e.start_round(f.e.everyone);f.e.start_of_turn(f.t,initiative_count=60)
        result=f.e.focused_command_with_voice(f.t,[f.p,f.q],ACE.CRITICAL)
        self.assertEqual(set(result['target_ids']),{f.p.entity_id,f.q.entity_id});self.assertEqual([TRAIN.bonus(p,'accuracy') for p in (f.p,f.q)],[3,3])
        self.assertEqual((f.t.budget['standard'],f.t.budget['swift']),(0,0));self.assertFalse(PRIORITY.records(f.t))
        self.assertEqual(FREQUENCY.state(f.t)['activations'][ACE.CRITICAL]['used'],1);f.rules=Rules(ROOT,ruleset='core');f.restore();f.valid()
        self.assertTrue(C.voice_authority(f.t,f.p,ACE.CRITICAL,TIME.records(f.p)[-1]['payment_id']))
        f.close();f.e.end_round();f.e.start_round(f.e.everyone);f.e.start_of_turn(f.t,initiative_count=60)
        self.assertEqual(TRAIN.bonus(f.p,'accuracy'),3);f.close();self.assertEqual(TRAIN.bonus(f.p,'accuracy'),1)

    def test_gm_and_fresh_rules_restore_keep_round_allowance_and_reject_tampered_actual_effect(self):
        self.world();self.e.prepare_focused_command_ap(self.a,'damage');self.battle();self.focused();self.e.gm.snapshot('actual-focused-round')
        self.partner_turn(self.p);self.close();self.e.gm.restore('actual-focused-round');self.cold();self.valid()
        self.assertEqual(COMMANDS.command_limit(self.e,self.a),2);self.assertEqual(F.damage_modifier(self.e,self.p2),0)
        row=self.a.spec[F.KEY][0];old=row['pokemon_ids'];row['pokemon_ids']=[self.p.entity_id,self.third.entity_id]
        with self.assertRaisesRegex(ValueError,'evidence changed'):F.damage_modifier(self.e,self.p)
        row['pokemon_ids']=old;self.partner_turn(self.p);self.close();self.partner_turn(self.p2);self.close()

    def test_source_contract_actual_csv_row_and_official_negative_scope_are_not_invented_versions(self):
        contract=json.loads((ROOT/'data/focused-command-source-contract.json').read_text(encoding='utf8'))
        self.assertEqual(contract['primary_clause'],'C03-131');self.assertEqual(contract['dependencies_credit'],{'C03-130':0})
        with (ROOT/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
        self.assertEqual(rows[18][0],'집중 명령');self.assertIn('대상을 지정해야만',rows[18][-1])
        self.assertEqual(contract['official_playtest']['changed_named_features'],[]);self.assertEqual(set(contract['source_choices']),{'core','local_csv'})
        self.world();self.battle();original=Path.read_bytes
        def changed(path):return b'changed actual original PDF' if path.name=='ptu-core-1.05.pdf' else original(path)
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'Core Focused Command source changed'):self.focused()
        self.assertNotIn(F.KEY,self.a.spec)


if __name__=='__main__':unittest.main()
