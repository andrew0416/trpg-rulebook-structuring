"""Full-Force Pose's real acquired permission, equipment and native modifiers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_book_ace_trainer_full as BASE
import ace_trainer as A
import z_moves as Z
import items as I
import trainer_feature_acquisition as T
import state_grants as G
import frequency as F
import world_entities as W
import capability_actions as CAP
from ruleset import RuleFilter
from native_scenario_fixture import assert_rejected_unchanged


class FullForcePoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='homebrew')
        cls.core=Rules(ROOT,ruleset='core')

    setup=BASE.AceTrainerFullTests.setup
    family=BASE.AceTrainerFullTests.family
    all_training=BASE.AceTrainerFullTests.all_training
    teach=BASE.AceTrainerFullTests.teach
    acquire=BASE.AceTrainerFullTests.acquire
    close=BASE.AceTrainerFullTests.close
    begin=BASE.AceTrainerFullTests.begin
    turn=BASE.AceTrainerFullTests.turn
    completion=BASE.AceTrainerFullTests.completion
    attack=BASE.AceTrainerFullTests.attack
    restore=BASE.AceTrainerFullTests.restore
    valid=BASE.AceTrainerFullTests.valid

    def retrain(self,feature):
        cost=self.rules.mech('trainer/experience')['retrain_cost']['feat']
        self.e.award_trainer_progression(self.t,kind='experience',
            amount=max(0,cost-self.t.spec.get('exp_bank',0)),
            request_id='actual-z-retraining-xp',reason='observed XP awarded before actual consultation')
        return BASE.AceTrainerFullTests.retrain(self,feature)

    def setUp(self):
        old=self.rules.rulings;self.rules.rulings=deepcopy(old)
        self.addCleanup(setattr,self.rules,'rulings',old)
        self.setup()

    def own(self,actor,rule,uid,*,equip=False):
        actor.spec['movement']['power']=4;actor.spec['power_basis']='current'
        W.register_object(self.e,uid,location={'kind':'unknown'},reason='observed actual Z reward',
            kind='item_instance',item_rule_id=rule,owner_id=actor.entity_id,weight_kg=0.1)
        carried=list(actor.spec.get('_carried_load',{}).get('objects',[]))
        CAP.set_carried(self.e,actor,carried+[{'id':uid,'weight_kg':0.1}],'actual carried Z reward')
        if equip:I.register_item(self.e,actor,rule,source_instance_id=uid)
        return uid

    def pose(self):
        if not Z.acquired(self.t):
            T.acquire_static(self.e,self.t,Z.FEATURE,acquisition_request_id='actual-full-force-pose')

    def crystal(self,mod,move,*,contract='core_1.05',request='z-choice',same_modifier_source=None):
        self.pose();self.own(self.t,Z.RING,'actual-zring',equip=True)
        self.own(self.p,Z.CRYSTAL,'actual-crystal',equip=True)
        self.e.observe_z_crystal('actual-crystal',modification=mod,source_contract=contract,
            reason='GM observed the actual reward contains this single modifier')
        self.e.gm.set_move(self.p,move,reason='actual learned compatible Z Move')
        return self.arm(move,request=request,same_modifier_source=same_modifier_source)

    def arm(self,move,*,crystal='actual-crystal',ring='actual-zring',request='z-choice',same_modifier_source=None):
        return self.e.arm_z_move(self.t,self.p,move_id=move,crystal_id=crystal,ring_id=ring,
            request_id=request,same_modifier_source=same_modifier_source)

    def reject(self,call,reason):
        return assert_rejected_unchanged(self.e,call,reason_pattern=reason)

    def excluded_profile(self,*excluded):
        profile=deepcopy(type(self).rules.ruleset.profile)
        profile['exclude_units']=profile.get('exclude_units',[])+list(excluded)
        selected=RuleFilter(profile,'actual-hb-explicit-exclusions')
        with patch.object(RuleFilter,'load',return_value=selected):return Rules(ROOT)

    def test_actual_level10_static_acquisition_replay_and_withdrawal(self):
        self.t.spec['level']=9
        self.reject(lambda:self.pose(),'level 10')
        self.t.spec['level']=10;self.pose();record=Z.acquired(self.t)
        self.assertEqual(record['source']['clause_id'],Z.CLAUSE)
        self.assertEqual(T.acquire_static(self.e,self.t,Z.FEATURE,acquisition_request_id='actual-full-force-pose')['request_id'],record['request_id'])
        self.assertNotIn(A.SIGNATURE,self.t.spec['feats'])
        self.retrain(Z.FEATURE);self.assertIsNone(Z.acquired(self.t));self.restore();self.valid()

    def test_hb_items_are_profile_gated_and_csv_sources_remain_distinct(self):
        for uid in Z.ITEMS:
            self.assertNotIn(uid,self.core.items_mech)
            self.assertEqual(self.rules._selected_rule(uid),uid)
            self.assertEqual(self.rules.selection.units[uid]['source']['file'],'hb-zmoves.md')
        self.assertIn('item/노말z',self.rules.items_mech)
        self.assertNotEqual(Z.CRYSTAL,'item/노말z')
        row=self.rules.selection.units[Z.FEATURE]
        self.assertEqual(row['source']['file'],'ch03-skills-edges-feats.md')
        self.assertEqual(row['source']['lines'],[674,677])
        self.assertEqual(row['source']['sha256'],Z.BOOK_SHA)
        self.assertEqual(T.STATIC_FEATURES[Z.FEATURE].get('catalog_span',T.STATIC_FEATURES[Z.FEATURE]['span']),row['source']['lines'])
        self.assertNotIn('사용x',row['title'])
        self.rules=self.excluded_profile(Z.CRYSTAL)
        self.assertNotIn(Z.CRYSTAL,self.rules.items_mech)
        self.assertIn(Z.POWER_RING,self.rules.items_mech)
        self.fused_mega();self.pose()
        self.reject(lambda:self.arm('move/막치기',ring='power-ring'),'missing_source_identity')
        self.rules=self.excluded_profile('hb-zmoves-1');self.setup();self.pose()
        self.assertNotIn(Z.RING,self.rules.items_mech);self.assertNotIn(Z.POWER_RING,self.rules.items_mech)
        self.assertIn(Z.CRYSTAL,self.rules.items_mech)
        self.own(self.p,Z.CRYSTAL,'actual-crystal',equip=True)
        self.e.observe_z_crystal('actual-crystal',modification='alternative_energy',reason='actual allowed crystal reward')
        self.own(self.t,'item/z링','actual-csv-ring',equip=True)
        self.e.gm.set_move(self.p,'move/막치기',reason='actual known Move in explicitly excluded ring profile')
        self.reject(lambda:self.arm('move/막치기',ring='actual-csv-ring'),'worn Trainer ring')

    def test_crystal_requires_one_immutable_physical_modifier(self):
        self.own(self.p,Z.CRYSTAL,'actual-crystal')
        self.reject(lambda:self.e.observe_z_crystal('missing',modification='double_down',reason='missing'),'physical')
        self.reject(lambda:self.e.observe_z_crystal('actual-crystal',modification='arbitrary',reason='unprinted'),'printed')
        row=self.e.observe_z_crystal('actual-crystal',modification='double_down',reason='single actual reward')
        self.assertEqual(self.e.observe_z_crystal('actual-crystal',modification='double_down',reason='single actual reward'),row)
        self.reject(lambda:self.e.observe_z_crystal('actual-crystal',modification='alternative_energy',reason='changed'),'cannot change')
        self.restore();self.valid()

    def test_ring_feature_ownership_and_compatible_actual_move_gates_are_atomic(self):
        self.own(self.t,Z.RING,'actual-zring',equip=True);self.own(self.p,Z.CRYSTAL,'actual-crystal',equip=True)
        self.e.observe_z_crystal('actual-crystal',modification='double_down',reason='actual small-damage reward')
        self.e.gm.set_move(self.p,'move/불꽃세례',reason='actual compatible learned Move')
        self.reject(lambda:self.arm('move/불꽃세례'),'Full-Force Pose')
        self.pose()
        self.reject(lambda:self.e.arm_z_move(self.foe,self.p,move_id='move/불꽃세례',crystal_id='actual-crystal',ring_id='actual-zring',request_id='foreign'),'Full-Force Pose|owner')
        self.reject(lambda:self.arm('move/파도타기'),'actually known')
        self.e.gm.set_move(self.p,'move/파도타기',reason='actual incompatible high-damage Move')
        self.reject(lambda:self.arm('move/파도타기'),'DB four')
        held=I.equipment_options(self.p,('held',))[0]
        I._unregister_selected(self.e,self.p,held)
        self.reject(lambda:self.arm('move/불꽃세례'),'held crystal')
        I.register_item(self.e,self.p,Z.CRYSTAL,source_instance_id='actual-crystal')
        I.unregister_item(self.e,self.t,registration_key=I.equipment_options(self.t,('장신구',))[0]['registration_key'])
        self.reject(lambda:self.arm('move/불꽃세례'),'worn Trainer ring')
        I.register_item(self.e,self.t,Z.RING,source_instance_id='actual-zring')
        self.arm('move/불꽃세례');self.retrain(Z.FEATURE);self.begin()
        self.reject(lambda:self.e.use_move_on(self.p,self.foe,'move/불꽃세례',[self.foe]),'Full-Force Pose')

    def test_native_move_consumes_one_scene_use_no_swap_bypass_and_scene_refresh(self):
        self.crystal('alternative_energy','move/막치기');tp=self.p.spec['tutor_points']
        row=self.attack('move/막치기')
        self.assertEqual(row['move']['class'],'특수');self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(self.p.spec['tutor_points'],tp);self.assertFalse(self.p.spec.get(A.KEY))
        self.assertEqual(len(self.p.spec[Z.HISTORY]),1)
        self.assertFalse(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA))
        self.reject(lambda:self.arm('move/막치기',request='second'),'used this scene')
        first=I.equipment_options(self.p,('held',))[0]
        I._unregister_selected(self.e,self.p,first)
        self.own(self.p,Z.CRYSTAL,'other-crystal',equip=True)
        self.e.observe_z_crystal('other-crystal',modification='alternative_energy',reason='other actual reward')
        self.reject(lambda:self.arm('move/막치기',crystal='other-crystal',request='swap'),'used this scene')
        self.close();self.e.end_scene();self.arm('move/막치기',crystal='other-crystal',request='new-scene')
        self.attack('move/막치기');self.assertEqual(len(self.p.spec[Z.HISTORY]),2);self.valid()
        import focused_command as FC,state_fields as SF,combat_damage as DAMAGE
        for move,allowed in (('move/막치기',True),('move/파도타기',False)):
            with self.subTest(focused_command_z_move=move):
                self.setup();self.crystal('alternative_energy',move)
                SF.base_patch(self.t,{'skills':dict(self.t.spec['skills'],명령=6,집중=5)},
                    reason='actual Focused Command acquisition prerequisites')
                acquisition=T.acquire_static(self.e,self.t,FC.FEATURE,acquisition_request_id='actual-focused-with-z')
                self.e.configure_party_combat(self.t,battle_mode='league',reason='actual two-Pokemon Focused Command pool')
                self.begin(self.t);focused=self.e.focused_command(self.t,[self.p,self.q])
                self.assertEqual(focused['acquisition'],acquisition['request_id'])
                self.assertEqual(focused['pokemon_ids'],[self.p.entity_id,self.q.entity_id])
                self.assertIsNone(focused['lift']);self.close()
                self.e.start_of_turn(self.p,initiative_count=50)
                self.assertTrue(FC.restricted(self.e,self.p));self.assertEqual(FC.damage_modifier(self.e,self.p),-5)
                self.assertEqual(F.move_frequency(self.e,move,self.p)[0]=='at_will',allowed)
                self.assertEqual(F.move_allowed(self.e,self.p,move)[0],allowed)
                if not allowed:
                    before=self.e.export_state()
                    reason=F.move_allowed(self.e,self.p,move)[1]
                    self.assertEqual(self.e.use_move_on(self.p,self.foe,move,[self.foe]),0)
                    # Native frequency rejection appends one diagnostic, not an
                    # action. Account for exactly that node; all other saved
                    # gameplay, identities, choice, budgets and RNG stay equal.
                    nodes=before['nodes'];root=nodes[before['root']['$ref']]
                    attrs=dict(nodes[root['attrs']['$ref']]['items'])
                    nodes[attrs['log_lines']['$ref']]['items'].append(
                        f'  {self.p.name}: {reason}  => [frequency/move]')
                    self.assertEqual(self.e.export_state(),before)
                    self.assertFalse(self.p.spec.get(Z.HISTORY))
                    self.assertTrue(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA,engine=self.e))
                    self.assertFalse(any(r['source_id'] in (move,Z.CRYSTAL) for r in FC.round_facts(self.p)))
                    self.valid();continue
                observed=[];native_defend=DAMAGE.defend
                def observe_damage(**facts):
                    observed.append(facts['modifiers'])
                    return native_defend(**facts)
                hp=self.foe.hp
                with patch.object(Engine,'d20',return_value=18),patch.object(DAMAGE,'defend',side_effect=observe_damage):
                    self.e.use_move_on(self.p,self.foe,move,[self.foe])
                self.assertEqual(observed,[-5]);self.assertLess(self.foe.hp,hp)
                self.assertEqual(self.completion()['move']['class'],'특수')
                self.assertEqual(self.p.budget['standard'],0);self.assertEqual(len(self.p.spec[Z.HISTORY]),1)
                self.assertEqual(F.state(self.p)['activations'][Z.CRYSTAL]['used'],1)
                self.assertFalse(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA,engine=self.e))
                facts=FC.round_facts(self.p)
                self.assertTrue(any(r['source_id']==move and r['kind']=='at_will' for r in facts))
                self.assertTrue(any(r['source_id']==move and r['kind']=='damage_roll' and r['penalty']==-5 for r in facts))
                self.assertFalse(any(r['source_id']==Z.CRYSTAL or r['kind']=='scene' for r in facts))
                self.valid()

    def test_failed_native_action_and_forged_projection_do_not_consume(self):
        self.crystal('double_down','move/불꽃세례')
        forged=dict(self.rules.move('move/불꽃세례'),**{Z.MARKER:{'investment_id':'invented'}})
        self.reject(lambda:A.prepare(self.e,self.p,forged),'projection source changed')
        self.reject(lambda:self.e.use_move(self.p,deepcopy(self.foe),'move/불꽃세례'),'distinct actors share identity:')
        self.assertFalse(self.p.spec.get(Z.HISTORY));self.assertTrue(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA))
        self.begin();before=self.e.export_state()
        with patch.object(A,'_eligible',side_effect=ValueError('injected changed source before admission')):
            with self.assertRaisesRegex(ValueError,'changed source'):self.e.use_move_on(self.p,self.foe,'move/불꽃세례',[self.foe])
        self.assertEqual(self.e.export_state(),before)
        with patch.object(Engine,'d20',return_value=18),patch.object(A,'after_target',side_effect=ValueError('injected late native failure')):
            with self.assertRaisesRegex(ValueError,'late native failure'):self.e.use_move_on(self.p,self.foe,'move/불꽃세례',[self.foe])
        self.assertEqual(self.e.export_state(),before)
        self.assertFalse(self.p.spec.get(Z.HISTORY));self.assertTrue(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA))

    def test_save_restore_preserves_crystal_choice_completed_use_and_quota(self):
        import passive_events as PASSIVE
        self.crystal('alternative_energy','move/막치기')
        G.set_baseline(self.foe,'abilities',['테라셸']);self.e.register_abilities(self.foe)
        self.e.watch_ability_interrupt(self.foe,'ability/테라셸',reason='actual Z target choice')
        self.restore()
        self.assertEqual(self.p.spec[Z.CHOICE]['status'],'armed')
        self.begin()
        with patch.object(Engine,'d20',return_value=18),self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move_on(self.p,self.foe,'move/막치기',[self.foe],set_damage=True)
        event=self.e._passive_pending;completion=self.completion()['id']
        self.assertEqual(self.p.spec[Z.CHOICE]['status'],'resolving');self.assertEqual(len(self.p.spec[Z.HISTORY]),1)
        self.assertFalse(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA));self.restore()
        with patch.object(Engine,'d20',return_value=18):
            self.e.choose_ability_interrupt(event,self.foe,use=False,options={},reason='actual target declines after restore')
        self.assertEqual(self.e._move_completions[completion]['phase'],'complete')
        self.assertEqual(len(self.p.spec[Z.HISTORY]),1);self.restore()
        self.assertEqual(self.p.spec[Z.CHOICE]['status'],'spent');self.valid()
        self.reject(lambda:self.arm('move/막치기',request='restore-must-not-refresh'),'used this scene')
        snapshot=self.e.gm.snapshot()
        for field,value in (('actor_id',self.foe.entity_id),('ring_id','actual-crystal')):
            receipt=self.p.spec[Z.HISTORY][0];receipt['choice'][field]=value
            Z._sign(receipt['choice']);Z._sign(receipt)
            with self.assertRaisesRegex(ValueError,'actual Pokemon|ring rule identity'):
                Z.validate_world(self.e,W.actor_index(self.e))
            # Native world validation groups Move-completion domain findings
            # under its established grapple_state relation code.
            with self.assertRaisesRegex(ValueError,'world reference integrity: grapple_state'):self.e.export_state()
            self.e.gm.restore(snapshot);self.valid()

    def test_scattershot_three_targets_and_adopted_two_targets(self):
        for contract,n in (('core_1.05',3),('dataninja_class_errata',2)):
            self.setup();self.crystal('scattershot','move/파도타기',contract=contract)
            projected=A.prepare(self.e,self.p,self.rules.move('move/파도타기'))
            self.assertEqual(projected['range'],'4m, 대상'+str(n))
            self.assertEqual(A.prepare(self.e,self.p,projected),projected)
            targets=[self.foe,self.q,self.ps[2]][:n]
            row=self.attack('move/파도타기',targets=targets)
            self.assertEqual(len(row['targets']),n);self.restore();self.valid()

    def test_shock_vicious_guard_and_unbalancing_native_consumers(self):
        for mod,mid in (('shock_and_awe','move/파도타기'),('vicious_storm','move/파도타기'),
                        ('guarding_strike','move/막치기'),('unbalancing_blow','move/막치기')):
            self.setup();self.crystal(mod,mid);hp=self.foe.hp
            row=self.attack(mid,face=18 if mod=='guarding_strike' else 1)
            if mod=='shock_and_awe':
                self.assertTrue(A.timed(self.foe,mod));self.assertEqual(A.save_bonus(self.foe),-2)
            elif mod=='vicious_storm':self.assertLess(self.foe.hp,hp);self.assertIn('강타',row['move']['range'])
            elif mod=='guarding_strike':self.assertEqual(A.damage_reduction(self.p,self.foe),5)
            else:self.assertEqual(self.foe.evasion('물리'),0)
            self.restore();self.valid()

    def test_reliable_native_miss_frequency_and_free_struggle(self):
        self.crystal('reliable_attack','move/불꽃세례');row=self.attack('move/불꽃세례',face=1)
        self.assertEqual(self.p.move_uses.get('move/불꽃세례',0),0)
        self.assertFalse(F.activation_allowed(self.p,Z.CRYSTAL,Z.QUOTA))
        with patch.object(Engine,'d20',return_value=18):self.e.reliable_attack_struggle(self.p,self.foe,row['id'])
        self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p._action_history[-1],'free')
        self.reject(lambda:self.e.reliable_attack_struggle(self.p,self.foe,row['id']),'opportunity')
        self.restore();self.valid()

    def test_alternative_energy_and_double_down_native_damage(self):
        for mod,mid,wanted in (('alternative_energy','move/막치기','특수'),
                               ('alternative_energy','move/불꽃세례','물리'),('double_down','move/불꽃세례','특수')):
            self.setup();self.crystal(mod,mid);before=self.foe.hp
            row=self.attack(mid)
            self.assertEqual(row['move']['class'],wanted);self.assertLess(self.foe.hp,before)
            if mod=='double_down':
                strike=self.p.spec['multi_strike_history'][-1]
                self.assertEqual(len(strike['rolls']),2);self.assertEqual(strike['technique_authority']['source'],Z.CRYSTAL)
            self.restore();self.valid()

    def test_bloodied_speed_actual_priority_turn_loan(self):
        self.crystal('bloodied_speed','move/막치기')
        self.e.prepare_initiative_schedule(self.e.everyone,source='gm/z-schedule',
            bindings=[{'slot':a.entity_id,'actor_id':a.entity_id,'role':a.entity_id} for a in self.e.everyone],
            order_groups=[[a.entity_id] for a in self.e.everyone])
        self.e.start_round(self.e.everyone)
        self.e.gm.set_hp(self.p,(self.p.max_hp-1)//2,reason='actual bloodied Z recipient')
        with patch.object(Engine,'d20',return_value=18):receipt=self.e.bloodied_speed(self.p,self.foe,'move/막치기')
        self.assertEqual(receipt['source'],Z.CRYSTAL)
        window=self.e._initiative_interrupts['windows'][receipt['window_id']]
        request=next(r for r in window['requests'] if r['id']==receipt['request_id'])
        self.assertEqual(request['source'],Z.CRYSTAL)
        self.assertEqual(self.e._initiative_interrupts['loans'][receipt['window_id']+':'+receipt['request_id']]['source'],Z.CRYSTAL)
        self.assertIs(self.e._active_turn_actor,self.p);self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(len(self.p.spec[Z.HISTORY]),1);self.restore();self.valid()

    def test_motivation_and_double_curse_native_status_consumers(self):
        self.crystal('burst_of_motivation','move/울음소리')
        self.e.gm.set_stage(self.p,'atk',value=-1,reason='actual Z user negative stage')
        row=self.attack('move/울음소리');self.e.burst_of_motivation(self.p,row['id'],{'atk':1})
        self.assertEqual(self.p.stages['atk'],0);self.assertEqual(self.foe.stages['atk'],-1)
        self.restore();self.valid();self.setup()
        self.crystal('double_curse','move/이상한빛');self.q.side='enemy'
        row=self.attack('move/이상한빛',targets=[self.foe,self.q])
        self.assertEqual(len(row['targets']),2);self.assertTrue(all('혼란' in p.conditions for p in (self.foe,self.q)))
        self.assertEqual(self.p.move_uses['move/이상한빛'],1);self.restore();self.valid()

    def test_supreme_concentration_real_turn_conditions(self):
        for condition in ('난동','마비','풀죽음'):
            self.setup();self.crystal('supreme_concentration','move/울음소리');self.begin(self.foe)
            self.e.apply_status(self.p,condition);self.close()
            with patch.object(Engine,'d20',return_value=1):self.e.start_of_turn(self.p,initiative_count=50)
            with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.p,self.foe,'move/울음소리',[self.foe])
            self.assertEqual(self.p.budget['standard'],0);self.assertIn(condition,self.p.conditions)
            self.assertEqual(self.foe.stages['atk'],-1);self.restore();self.valid()

    def test_permanent_signature_and_crystal_compose_without_fake_investment(self):
        self.teach('alternative_energy','move/불꽃세례');investment=deepcopy(self.p.spec[A.KEY]);tp=self.p.spec['tutor_points']
        self.crystal('double_down','move/불꽃세례');row=self.attack('move/불꽃세례')
        self.assertEqual(row['move']['class'],'물리');self.assertIn(A.MARKER,row['move']);self.assertIn(Z.MARKER,row['move'])
        self.assertEqual(self.p.spec[A.KEY],investment);self.assertEqual(self.p.spec['tutor_points'],tp)
        self.assertEqual(len(self.p.spec['multi_strike_history'][-1]['rolls']),2);self.restore();self.valid()

    def test_same_modifier_coalesces_once_and_different_contracts_require_explicit_source(self):
        for mod,mid in (('alternative_energy','move/불꽃세례'),('double_down','move/불꽃세례')):
            self.setup();self.teach(mod,mid);investment=deepcopy(self.p.spec[A.KEY]);tp=self.p.spec['tutor_points']
            self.crystal(mod,mid);row=self.attack(mid)
            self.assertIn(A.MARKER,row['move']);self.assertIn(Z.MARKER,row['move'])
            if mod=='alternative_energy':self.assertEqual(row['move']['class'],'물리')
            else:self.assertEqual(len(self.p.spec['multi_strike_history'][-1]['rolls']),2)
            self.assertEqual(self.p.spec[A.KEY],investment);self.assertEqual(self.p.spec['tutor_points'],tp)
            self.restore();self.valid()
        for selected,count in (('signature',2),('crystal',3)):
            self.setup();self.teach('scattershot','move/파도타기',contract='dataninja_class_errata')
            self.crystal('scattershot','move/파도타기',contract='core_1.05',same_modifier_source=selected)
            self.reject(lambda:self.arm('move/파도타기',request='unselected-contract'),'explicit same_modifier_source')
            projected=A.prepare(self.e,self.p,self.rules.move('move/파도타기'))
            self.assertEqual(projected['range'],'4m, 대상'+str(count))
            self.assertEqual(projected[A.MARKER]['source_contract'],'dataninja_class_errata')
            self.assertEqual(projected[Z.MARKER]['source_contract'],'core_1.05')
            row=self.attack('move/파도타기',targets=[self.foe,self.q,self.ps[2]][:count])
            self.assertEqual(len(row['targets']),count);self.restore();self.valid()

    def test_actual_gm_approved_ring_fusion_and_atomic_denials(self):
        self.own(self.t,Z.RING,'z-component');self.own(self.t,'item/메가링','mega-component')
        args=dict(zring_id='z-component',mega_ring_id='mega-component',result_id='actual-power-ring',reason='actual GM-approved ring fusion')
        self.reject(lambda:self.e.combine_z_rings(self.t,**args,gm_decision={'allowed':False,'reason':'not approved'}),'GM approval')
        seconds=self.e.elapsed_seconds
        result=self.e.combine_z_rings(self.t,**args,gm_decision={'allowed':True,'reason':'GM approved the printed extension'})
        self.assertEqual(result['item_rule_id'],Z.POWER_RING);self.assertEqual(self.t._action_history[-1],'extended')
        self.assertEqual(self.e.elapsed_seconds,seconds)  # HB prints Extended, not an invented duration.
        for uid in ('z-component','mega-component'):
            self.assertIn('consumed',self.e._physical_objects[uid]);self.assertNotIn('carrier_id',self.e._physical_objects[uid])
        I.register_item(self.e,self.t,Z.POWER_RING,source_instance_id='actual-power-ring')
        self.pose();self.own(self.p,Z.CRYSTAL,'actual-crystal',equip=True)
        self.e.observe_z_crystal('actual-crystal',modification='alternative_energy',reason='actual combined ring crystal')
        self.e.gm.set_move(self.p,'move/막치기',reason='actual combined ring Move')
        self.arm('move/막치기',ring='actual-power-ring');self.attack('move/막치기');self.restore();self.valid()

    def test_z_power_ring_preserves_real_mega_function(self):
        self.fused_mega()

    def fused_mega(self):
        import test_category2_mega_forms as MEGA
        helper=MEGA.MegaFormTests();helper.r=self.rules;helper.setUp()
        self.e,self.t,self.p=helper.e,helper.t,helper.p
        I.unregister_item(self.e,self.t,'메가링')
        self.t.spec['movement']['power']=4;self.t.spec['power_basis']='current'
        self.e._physical_objects['ring']['weight_kg']=0.1
        CAP.set_carried(self.e,self.t,[{'id':'ring','weight_kg':0.1}],'actual Mega component possession')
        self.own(self.t,Z.RING,'z-component')
        self.e.combine_z_rings(self.t,zring_id='z-component',mega_ring_id='ring',result_id='power-ring',
            gm_decision={'allowed':True,'reason':'GM approved the actual printed fusion'},reason='observed native fusion')
        I.register_item(self.e,self.t,Z.POWER_RING,source_instance_id='power-ring')
        helper.turn(self.t);before=deepcopy(self.p.stats)
        receipt=self.e.mega_evolve(self.t,self.p,'mega/리자몽-x',ring='power-ring',stone='stone')
        self.assertEqual(receipt['ring_instance'],'power-ring');self.assertEqual(self.t.budget['swift'],0)
        self.assertEqual(self.p.stats['atk'],before['atk']+5);self.assertEqual(self.p.types,['불꽃','드래곤'])
        self.assertTrue(self.e.validate_state()['valid']);self.e.end_scene()
        self.assertEqual(self.p.stats,before);self.assertEqual(self.e._physical_objects['power-ring']['item_rule_id'],Z.POWER_RING)
