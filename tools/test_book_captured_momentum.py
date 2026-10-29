"""Captured Momentum's actual native trigger, choices, rolls and AP funding."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
import captured_momentum as CM,temporary_ap as TEMP,trainer_feature_acquisition as TFA
import capture_techniques as CT,action_points as AP,ap_roll_bonus as AP_ROLL
import bound_ap as BOUND,state_codec as CODEC,effect_instances as E,state_fields as FIELDS
import test_book_capture_specialist as BASE

FUNDING={'priority':'temporary_first','binding_expiry':'end_effect','reason':'GM explicitly selects temporary funding first and ends funded effects at expiry'}

class CapturedMomentumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='core+errata')
        cls.core=Rules(str(ROOT),ruleset='core')
    def setUp(self):self.setup()
    def setup(self,*,rules=None,acquire=True):
        self.base=BASE.BookCaptureSpecialistTests();self.base.rules=self.rules if rules is None else rules
        self.e,self.a=self.base.fixture()
        for rank,pair in enumerate((('작업 도구','커브볼'),('빠른 투구','약화 투척'),('덫','캐치 콤보'))):
            self.base.acquire(self.e,self.a,[BASE.choice(name) for name in pair],rank)
        if acquire:TFA.acquire_static(self.e,self.a,CM.FEATURE,acquisition_request_id='momentum/acquire')
        def pokemon(name,owned=False):
            spec={'id':'pokemon/'+name,'name':name,'kind':'pokemon','level':20,'pos':(1,0),
                'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),5),'items':{},'edges':[],'feats':[],
                'species':'잉어킹','evolutions_remaining':0,'wild':not owned,'moves':[]}
            if owned:spec['trainer_id']=self.a.entity_id
            c=Combatant(self.e.r,spec);c.side='party' if owned else 'wild';return c
        self.p,self.q,self.pet=pokemon('first'),pokemon('second'),pokemon('owned',True)
        self.e.everyone=self.e.gm.everyone=[self.a,self.p,self.q,self.pet]
        self.a.spec['items']['몬스터볼']=5
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
    def capture(self,target=None,*,face=20,accuracy=20,**options):
        return self.e.throw_ball(self.a,target or self.p,fixed_accuracy=accuracy,fixed_capture=face,**options)
    def choose(self,choice,**kw):return self.e.choose_captured_momentum(self.a,attempt_id='capture-1',choice=choice,**kw)
    def grant(self,choice,**kw):self.assertTrue(self.capture());return self.choose(choice,**kw)
    def next_turn(self):
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
    def expire(self):
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
    def snap(self):return deepcopy((self.a.spec,self.a.stats,self.p.spec,self.q.spec,self.pet.spec,self.e.rng.getstate(),self.a.budget,self.e.elapsed_seconds))
    def test_acquisition_rank_two_actual_source_speed_replay_and_historical_prerequisite(self):
        self.assertEqual(self.a.stats['spe'],14)
        row=TFA.acquire_static(self.e,self.a,CM.FEATURE,acquisition_request_id='momentum/acquire')
        self.assertEqual(row['source']['clause_id'],CM.CLAUSE);self.assertEqual(self.a.stats['spe'],14)
        before=self.snap()
        with self.assertRaises(ValueError):TFA.acquire_static(self.e,self.a,CM.FEATURE,acquisition_request_id='different')
        self.assertEqual(self.snap(),before)
        self.a.spec['skills']=dict.fromkeys(CT.SKILLS,1)
        TFA.validate_actor(self.a)
        e,a=self.base.fixture();self.base.acquire(e,a,[BASE.choice('작업 도구'),BASE.choice('커브볼')])
        self.base.acquire(e,a,[BASE.choice('빠른 투구'),BASE.choice('약화 투척')],1)
        with self.assertRaisesRegex(ValueError,'rank 2'):TFA.acquire_static(e,a,CM.FEATURE,acquisition_request_id='invalid')
    def test_real_capture_failure_miss_and_imported_feature_do_not_create_success_right(self):
        self.assertFalse(self.capture(face=1));self.assertNotIn('momentum',self.a.spec['capture_attempts']['capture-1'])
        with self.assertRaises(ValueError):self.choose('accuracy')
        self.setup();self.assertFalse(self.capture(accuracy=1));self.assertNotIn('momentum',self.a.spec['capture_attempts']['capture-1'])
        self.setup(acquire=False);self.a.spec['feats'].append(CM.FEATURE);before=self.snap()
        with self.assertRaisesRegex(ValueError,'actual acquisition'):self.capture()
        self.assertEqual(self.snap(),before)
    def test_success_waits_for_explicit_choice_without_repeating_ball_capture_or_rng(self):
        self.assertTrue(self.capture());before=self.snap();attempt=deepcopy(self.a.spec['capture_attempts']['capture-1'])
        with self.assertRaisesRegex(ValueError,'pending'):self.e.end_of_turn(self.a)
        with self.assertRaisesRegex(ValueError,'pending'):self.e.accuracy_check(self.a,self.q,self.e.r.move('move/울음소리'),fixed_roll=10)
        self.assertEqual(self.snap(),before)
        result=self.choose('decline');self.assertEqual(result['status'],'declined')
        self.assertEqual(self.a.spec['items']['몬스터볼'],4);self.assertTrue(self.p.captured)
        self.assertEqual(self.a.spec['capture_attempts']['capture-1']['resolution'],attempt['resolution'])
        with self.assertRaisesRegex(ValueError,'already resolved'):self.choose('accuracy')
    def test_accuracy_owner_explicit_choice_invalid_input_and_free_action_failure_are_atomic(self):
        self.assertTrue(self.capture());before=self.snap()
        for options in ({'choice':'both'},{'choice':'accuracy','target':self.q},{'choice':'temporary_ap'},{'choice':'capture','target':self.pet}):
            with self.assertRaises(ValueError):self.e.choose_captured_momentum(self.a,attempt_id='capture-1',**options)
            self.assertEqual(self.snap(),before)
        self.a.hp=0
        with self.assertRaises(ValueError):self.choose('accuracy')
        self.assertEqual(self.a.spec['capture_attempts']['capture-1']['momentum']['state'],'pending')
    def test_next_accuracy_changes_result_once_for_self_and_owned_pokemon_and_miss_consumes(self):
        for beneficiary in ('self','pokemon'):
            self.setup();holder=self.a if beneficiary=='self' else self.pet;move=self.e.r.move('move/울음소리')
            threshold=next(n for n in range(2,20) if self.e.accuracy_check(holder,self.q,move,fixed_roll=n)[0])
            self.grant('accuracy',target=holder)
            self.assertTrue(self.e.accuracy_check(holder,self.q,move,fixed_roll=threshold-1)[0])
            self.assertFalse(self.e.accuracy_check(holder,self.q,move,fixed_roll=threshold-1)[0]);self.assertFalse(CM.live(holder))
            self.assertEqual(len(CM.history(holder)[-1]['applications']),1)
        self.setup();self.grant('accuracy');self.e.accuracy_check(self.a,self.q,move,fixed_roll=1)
        self.assertFalse(CM.live(self.a));self.assertEqual(CM.history(self.a)[-1]['applications'][0]['natural'],1)
    def test_no_roll_and_forged_shared_roll_preserve_accuracy_until_actual_roll(self):
        self.grant('accuracy');effect=CM.live(self.a)[0];before=self.snap()
        with self.assertRaisesRegex(ValueError,'authority'):self.e.accuracy_check(self.a,self.q,self.e.r.move('move/울음소리'),shared_roll={})
        self.assertEqual(self.snap(),before)
        self.e.accuracy_check(self.a,self.a,self.e.r.move('move/각지기'))
        self.assertEqual(CM.live(self.a)[0]['id'],effect['id']);self.assertEqual(effect['applications'],[])
    def test_transferred_pokemon_is_not_eligible_and_encounter_end_expires_unused_accuracy(self):
        self.grant('accuracy',target=self.pet);self.pet.spec['trainer_id']='other-owner'
        self.e.accuracy_check(self.pet,self.q,self.e.r.move('move/울음소리'),fixed_roll=10)
        self.assertTrue(CM.live(self.pet));self.pet.spec['trainer_id']=self.a.entity_id
        self.e.end_of_turn(self.a);self.e.end_encounter()
        self.assertFalse(CM.live(self.pet));self.assertEqual(CM.history(self.pet)[-1][E.KEY]['state'],'expired')
        for choice in ('capture','temporary_ap'):
            self.setup();self.grant(choice,**({'ap_policy':FUNDING} if choice=='temporary_ap' else {}))
            self.e.end_of_turn(self.a);self.e.end_encounter()
            self.assertFalse(CM.live(self.a));self.assertFalse(TEMP.live(self.a));self.assertTrue(self.e.validate_state()['valid'])
    def test_selected_errata_conversion_uses_current_six_skill_ranks_and_one_real_capture_roll(self):
        self.grant('capture');self.next_turn()
        FIELDS.base_patch(self.a,{'skills':dict.fromkeys(CT.SKILLS,4)},reason='actual later skill ranks')
        self.assertFalse(self.capture(self.q,face=7));attempt=self.a.spec['capture_attempts']['capture-2']
        plan=next(iter(attempt['momentum_effects'].values()))
        self.assertEqual((plan['book_modifier'],plan['modifier']),(-4,0));self.assertEqual(attempt['resolution']['modifiers']['captured_momentum'],0)
        self.assertFalse(CM.live(self.a));self.assertEqual(CM.history(self.a)[-1]['applications'][0]['capture_plan'],plan)
        self.setup();self.grant('capture');self.next_turn()
        self.assertTrue(self.capture(self.q,face=8));attempt=self.a.spec['capture_attempts']['capture-2']
        self.assertEqual(attempt['resolution']['modifiers']['captured_momentum'],1);self.e.choose_captured_momentum(self.a,attempt_id='capture-2',choice='decline')
    def test_capture_miss_no_roll_keeps_benefit_and_core_needs_explicit_separate_conversion(self):
        self.grant('capture');self.next_turn();self.assertFalse(self.capture(self.q,accuracy=1));self.assertTrue(CM.live(self.a))
        self.setup(rules=self.core)
        snare_conversion={'modifier':2,'reason':'GM explicitly converts this Book Snare attempt on the native d20 procedure','scope':'this_capture_roll'}
        self.assertTrue(self.capture(snare_conversion=snare_conversion));before=self.snap()
        proof=self.a.spec['capture_attempts']['capture-1']['snare_conversion']
        self.assertEqual(proof['request'],snare_conversion);self.assertEqual((proof['authority'],proof['applied_modifier']),('gm_ruling',0))
        with self.assertRaisesRegex(ValueError,'conversion'):self.choose('capture')
        self.assertEqual(self.snap(),before)
        self.choose('capture',conversion={'modifier':3,'scope':'next_capture_roll','reason':'GM explicitly converts Book modifier for this next d20 capture'})
        self.assertEqual(CM.live(self.a)[0]['effect']['capture_plan']['basis']['kind'],'gm_ruling')
    def test_temporary_ap_ordinary_spend_pays_actual_pre_roll_action_without_regular_debit(self):
        self.grant('temporary_ap',ap_policy=FUNDING);maximum=AP.maximum(self.a);self.assertEqual(AP.available(self.a),maximum+1)
        AP_ROLL.prepare(self.e,self.a,self.a,roll_id='temp-roll',kind='accuracy')
        self.assertEqual(self.a.spec.get('ap_spent',0),0);self.assertEqual(TEMP.available(self.a),0)
        self.e.accuracy_check(self.a,self.q,self.e.r.move('move/울음소리'),fixed_roll=10,roll_id='temp-roll')
        self.assertEqual(self.e._ap_rolls['temp-roll']['state'],'resolved');self.expire();self.assertEqual(AP.available(self.a),maximum)
    def test_temporary_ap_drain_and_expiry_do_not_restore_spent_points_or_debit_regular_pool(self):
        self.grant('temporary_ap',ap_policy=FUNDING);maximum=AP.maximum(self.a)
        AP.charge(self.a,1,mode='drain');self.assertEqual(self.a.spec.get('ap_removed',0),0);self.assertEqual(TEMP.available(self.a),0)
        self.expire();self.assertEqual(AP.available(self.a),maximum)
        AP.end_scene(self.a);AP.extended_rest(self.a);self.assertEqual(AP.available(self.a),maximum)
        self.assertEqual(TEMP.all_records(self.a)[-1]['payments'][0]['state'],'spent')
    def test_unused_temporary_ap_expires_at_same_count_next_round_not_current_round_end(self):
        self.grant('temporary_ap',ap_policy=FUNDING);maximum=AP.maximum(self.a)
        self.e.end_of_turn(self.a);self.e.end_round();self.assertEqual(AP.available(self.a),maximum+1)
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(21);self.assertEqual(AP.available(self.a),maximum+1)
        self.e.at_initiative_count(20);self.assertEqual(AP.available(self.a),maximum);self.assertFalse(TEMP.live(self.a))
    def test_explicit_ordinary_first_priority_and_missing_binding_policy_hold_before_payment(self):
        self.grant('temporary_ap',ap_policy=dict(FUNDING,priority='ordinary_first'));AP.spend(self.a,1)
        self.assertEqual((self.a.spec['ap_spent'],TEMP.available(self.a)),(1,1))
        self.setup();self.grant('temporary_ap',ap_policy=dict(FUNDING,binding_expiry='require_decision'));before=self.snap()
        with self.assertRaisesRegex(ValueError,'funding-loss'):BOUND.activate_modifier(self.e,self.a,'temporary-binding',amount=1,modifier={'type':'damage_roll_mod','value':3},ending_method='none_specified',source_ref='gameplay/action-points')
        self.assertEqual(self.snap(),before)
    def test_temporary_bound_modifier_ends_through_native_owner_at_funding_expiry(self):
        self.grant('temporary_ap',ap_policy=FUNDING);maximum=AP.maximum(self.a)
        BOUND.activate_modifier(self.e,self.a,'temporary-binding',amount=1,modifier={'type':'damage_roll_mod','value':3},ending_method='none_specified',source_ref='gameplay/action-points')
        self.assertEqual(self.a.spec['ap_bound'],{'temporary-binding':1});self.assertEqual(AP.available(self.a),maximum)
        self.expire();self.assertEqual(self.a.spec['ap_bound'],{});self.assertEqual(AP.available(self.a),maximum)
        self.assertEqual(self.a._ap_bound_effects['temporary-binding']['state'],'ended');self.assertFalse(any(m.get('value')==3 and m.get('type')=='damage_roll_mod' for m in self.a.modifiers))
    def test_live_temporary_binding_release_returns_only_unexpired_point(self):
        self.grant('temporary_ap',ap_policy=FUNDING)
        BOUND.activate_modifier(self.e,self.a,'temporary-binding',amount=1,modifier={'type':'damage_roll_mod','value':3},ending_method='none_specified',source_ref='gameplay/action-points')
        result=self.e.release_bound_ap(self.a,'temporary-binding',event_id='explicit-release')
        self.assertEqual(result.status,'released');self.assertEqual(TEMP.available(self.a),1)
        self.expire();self.assertEqual(TEMP.available(self.a),0)
    def test_pending_and_issued_effects_survive_gm_json_restore_and_tampering_is_rejected(self):
        self.assertTrue(self.capture());self.e.gm.snapshot('pending')
        fresh=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        owner=next(a for a in fresh.gm.everyone if a.entity_id==self.a.entity_id)
        fresh.choose_captured_momentum(owner,attempt_id='capture-1',choice='temporary_ap',ap_policy=FUNDING)
        self.assertEqual(TEMP.available(owner),1);self.assertTrue(fresh.validate_state()['valid'])
        self.choose('accuracy',target=self.pet);self.e.gm.snapshot('issued')
        loaded=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        pet=next(a for a in loaded.gm.everyone if a.entity_id==self.pet.entity_id);self.assertEqual(len(CM.live(pet)),1)
        self.e.gm.restore('pending',reason='restore pending actual capture');self.assertEqual(len(CM.pending(self.e)),1)
        row=TEMP.live(owner)[0];row['effect']['amount']=2
        report=fresh.validate_state();self.assertFalse(report['valid']);self.assertTrue(any(issue['code']=='effect_instance' for issue in report['issues']))
        with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(fresh)
    def test_retraining_removes_speed_and_feature_source_without_reusing_old_capture_events(self):
        self.e.end_of_turn(self.a);self.e.end_encounter()
        opts=self.base.decisions(self.e,self.a,CM.FEATURE)
        self.e.retrain_trainer_source(self.a,CM.FEATURE,**opts)
        self.assertEqual(self.a.stats['spe'],13);self.assertIsNone(CM.acquired(self.a))
        TFA.acquire_static(self.e,self.a,CM.FEATURE,acquisition_request_id='momentum/reacquire')
        self.assertEqual(self.a.stats['spe'],14);self.assertTrue(self.e.validate_state()['valid'])

    def test_temporary_mixed_funding_ends_both_existing_stratagem_owners_and_refunds_regular_part(self):
        import class_passive_combat as CP,combat_precision_features as PRECISION
        for mode in ('class','precision'):
            self.setup();self.grant('temporary_ap',ap_policy=FUNDING)
            # Isolate each existing native bind consumer with its ordinary action
            # budget supplied by this fixture; the AP came from real ball capture.
            self.a.budget['standard']=1
            self.e.gm.observe_sensory_environment(self.a,self.pet,paths={'auditory':True},present=True,
                reason='actual allied recipient hears the current native Stratagem Order')
            if mode=='class':
                self.a.spec['feats'].append(CP.TRICK_SHOT)
                self.assertEqual(CP.activate(self.e,self.a,self.pet,CP.TRICK_SHOT),(1,0))
                instance=CP._active(self.e,self.pet,CP.TRICK_SHOT)[1]['instance']
            else:
                self.a.spec['feats'].append(PRECISION.PRECISION)
                self.assertEqual(PRECISION.activate(self.e,self.a,self.pet),(1,0))
                instance=PRECISION.binding(self.e,self.pet)['instance']
            maximum=AP.maximum(self.a)
            self.assertEqual(self.a.spec['ap_bound'][instance],2)
            self.assertEqual((TEMP.bound_amount(self.a),AP.available(self.a)),(1,maximum-1))
            self.expire()
            self.assertNotIn(instance,self.a.spec['ap_bound']);self.assertEqual(AP.available(self.a),maximum)
            if mode=='class':self.assertIsNone(CP._active(self.e,self.pet,CP.TRICK_SHOT))
            else:self.assertIsNone(PRECISION.binding(self.e,self.pet))
            self.assertEqual(self.a.spec.get('ap_spent',0),0)
    def test_unknown_script_binding_owner_fails_before_funding_and_ordinary_funding_still_works(self):
        self.grant('temporary_ap',ap_policy=FUNDING);before=self.snap()
        with self.assertRaisesRegex(ValueError,'supported actual bound-effect owner'):
            AP.charge(self.a,1,mode='bind',instance_id='unknown-script')
        self.assertEqual(self.snap(),before)
        self.setup();self.grant('temporary_ap',ap_policy=dict(FUNDING,priority='ordinary_first'))
        AP.charge(self.a,1,mode='bind',instance_id='ordinary-only')
        self.assertEqual(TEMP.available(self.a),1)

    def test_outside_battle_capture_grants_temporary_ap_for_ten_actual_seconds(self):
        self.e.end_of_turn(self.a);self.e.end_encounter();self.assertFalse(self.e.encounter_active)
        self.assertTrue(self.capture());self.choose('temporary_ap',ap_policy=FUNDING)
        maximum=AP.maximum(self.a);self.assertEqual(AP.available(self.a),maximum+1)
        self.e.advance_time(9);self.assertEqual(AP.available(self.a),maximum+1)
        loaded=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        owner=next(a for a in loaded.gm.everyone if a.entity_id==self.a.entity_id)
        loaded.advance_time(1);self.assertEqual(AP.available(owner),maximum)
        self.e.advance_time(1);self.assertEqual(AP.available(self.a),maximum)

    def test_virtuoso_effective_rank_eight_is_preserved_in_actual_capture_modifier_evidence(self):
        FIELDS.base_patch(self.a,{'skills':dict(self.a.spec['skills'],육상=6)},reason='actual Master Athletics')
        self.a.spec['edges'].append('edge/거장');self.a.spec['edge_choices']={'edge/거장':['육상']}
        self.grant('capture');plan=CM.live(self.a)[0]['effect']['capture_plan']
        self.assertEqual((plan['ordinary_skills']['육상'],plan['skills']['육상'],plan['book_modifier'],plan['modifier']),(6,8,-8,1))
    def test_live_roll_with_already_consumed_application_is_rejected_on_save(self):
        self.grant('accuracy');row=CM.live(self.a)[0]
        row['applications'].append({'kind':'accuracy_roll','move_id':'move/울음소리','target_id':self.q.entity_id,'natural':10})
        report=self.e.validate_state();self.assertFalse(report['valid']);self.assertTrue(any(issue['code']=='effect_instance' for issue in report['issues']))
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
    def test_native_bound_bundle_default_ending_accepts_only_actual_funding_loss(self):
        self.grant('temporary_ap',ap_policy=FUNDING)
        result=BOUND.activate_effects(self.e,self.a,self.pet,'mixed-bundle',amount=2,
            effects=[{'type':'damage_roll_mod','value':3,'target':'self'},{'type':'accuracy_mod','value':2,'target':'target'}],
            ending_method='none_specified',source_ref='gameplay/action-points')
        self.assertEqual(result.status,'adopted');self.assertEqual(TEMP.bound_amount(self.a),1)
        binding=self.a._ap_bound_effects['mixed-bundle'];part=binding['components'][0]
        with self.assertRaises(ValueError):BOUND.preflight_expire(self.e,part['holder'],part['record'],event={'kind':'temporary_ap_expired','grant_id':TEMP.live(self.a)[0]['id'],'source':CM.FEATURE})
        maximum=AP.maximum(self.a);self.expire()
        self.assertEqual(self.a.spec['ap_bound'],{});self.assertEqual(AP.available(self.a),maximum)
        self.assertEqual(self.a._ap_bound_effects['mixed-bundle']['state'],'ended')

    def test_temporary_payment_owner_tamper_is_rejected_before_restore_or_expiry(self):
        self.grant('temporary_ap',ap_policy=FUNDING)
        BOUND.activate_modifier(self.e,self.a,'bound-owner',amount=1,modifier={'type':'damage_roll_mod','value':3},ending_method='none_specified',source_ref='gameplay/action-points')
        payment=TEMP.live(self.a)[0]['payments'][0];payment['binding_owner']='class_passive_combat'
        report=self.e.validate_state();self.assertFalse(report['valid']);self.assertTrue(any(issue['code']=='effect_instance' for issue in report['issues']))
        with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)

    def test_snare_gm_conversion_requires_actual_technique_and_actual_bait_condition(self):
        import wild_equipment as WILD
        self.setup(rules=self.core)
        conversion={'modifier':3,'reason':'GM explicitly chooses this capture attempt conversion','scope':'this_capture_roll'}
        # An arbitrary modifier alone never establishes a real Snare condition.
        self.assertEqual(WILD.snare_bonus(self.e,self.a,self.p,conversion=conversion),0)
        self.a.spec['items']['미끼']=1;self.p.spec['skills']={'집중':4}
        self.e.pokemon_activity(self.a,'distract_bait',target=self.p,fixed=[1]*4)
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.assertTrue(self.capture(face=7,snare_conversion=conversion))
        receipt=self.a.spec['capture_attempts']['capture-1'];self.assertEqual(receipt['snare_bonus'],3)
        self.assertEqual(receipt['snare_conversion']['attempt_id'],receipt['id'])
        self.choose('decline')
        e,unowned=self.base.fixture()
        with self.assertRaisesRegex(ValueError,'actual acquired Snare'):WILD.snare_bonus(e,unowned,self.p,conversion=conversion)
