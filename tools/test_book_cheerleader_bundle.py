"""Cheerleader's actual native triggers, independent instances and consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon,build_trainer
import test_book_moment_of_action as MOA_FIXTURE
import test_category2_class_passive_combat_bulk as STRATAGEM_FIXTURE
import cheerleader as CH,moment_of_action as M,training_features as TRAINING
import trainer_feature_acquisition as TFA,trainer_retraining as RETRAIN
import state_codec as CODEC,state_fields as F,state_grants as G,action_points as AP
import effect_instances as E,condition_recovery as RECOVERY,combat_stage_sources as CS
import combat_precision_features as PRECISION,class_passive_combat as CLASS_PASSIVE
import directive_features as DIRECTIVES,items,move_completion as COMPLETE


class CheerleaderBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setup(self,*,support=False,combat=True,moves=(),abilities=(),rules=None):
        base=MOA_FIXTURE.MomentOfActionTests();base.rules=rules or self.rules;base.setup(combat=False)
        self.base=base;self.e,self.a,self.b,self.c=base.e,base.a,base.b,base.c
        F.base_patch(self.a,{'skills':{'매력':4,'명령':5,'통찰':5,'육상':4,'협박':4}},reason='actual acquisition prerequisites')
        if support:
            for uid in (CH.BRIGADE,CH.SUPPORT):TFA.acquire_static(self.e,self.a,uid,acquisition_request_id='acquire/'+uid)
        self.p=Combatant(self.e.r,build_pokemon(self.e.r,'이브이',20,name='actual cheer partner',
            moves=list(moves),abilities=list(abilities),extra={'trainer_id':self.a.entity_id,'trainer':self.a.name}))
        self.e.gm.add_combatant(self.p,pos=(1,0),side='party',reason='actual owned partner')
        self.e.gm.observe_loyalty(self.p,6,reason='actual willing partner')
        self.a.pos=(0,0);self.b.pos=(2,0);self.c.pos=(3,0)
        for target in (self.b,self.c):base.audible(target)
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual order delivery')
        self.e.register_abilities(self.p)
        if combat:self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
        self.answer('cheerleader','Cheered')
    def answer(self,kind,value):
        self.e.rulings.answers=[row for row in self.e.rulings.answers if row['key']!=kind]
        self.e.rulings.add_answer(kind,value,reason='explicit player choice',scope='permanent')
    def moment(self,targets=None):return self.base.use([self.b] if targets is None else targets)
    def save(self,actor=None,first=3,second=17):
        with patch.object(type(self.e),'d20',new=lambda e:second):
            return RECOVERY.saving_check(self.e,actor or self.b,'마비',11,fixed=first)
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def state(self):return CODEC.dump_engine(self.e)
    def unchanged(self,callback,error=ValueError):
        before=self.state()
        with self.assertRaises(error):callback()
        self.assertEqual(self.state(),before)
    def start(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        if getattr(actor,'budget',None) is not None:self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=20)
    def coach(self,fixture,pokemon):
        self.e=fixture.e
        self.a=Combatant(self.e.r,build_trainer(self.e.r,'actual Support owner',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),skills={'매력':4,'명령':2},abilities=[]))
        self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual Trainer of the ability holder')
        pokemon.spec['trainer_id']=self.a.entity_id;pokemon.spec['trainer']=self.a.name
        G.replace_baseline(self.e,pokemon,'abilities',list(pokemon.spec['abilities'])+['프렌드가드'])
        for uid in (M.TRAINING,M.CLASS,CH.BRIGADE,CH.SUPPORT):
            TFA.acquire_static(self.e,self.a,uid,acquisition_request_id='support-owner/'+uid)
        self.answer('cheerleader','Cheered')

    def test_moment_zero_one_two_real_allies_one_condition_and_triggered_free_cost(self):
        for count in (0,1,2):
            self.setup();before=AP.available(self.a);self.moment([self.b,self.c][:count])
            self.assertEqual(len(CH.live(self.b)),int(count>0));self.assertEqual(len(CH.live(self.c)),int(count>1))
            self.assertEqual(AP.available(self.a),before-int(count==2))
            self.assertEqual(getattr(self.a,'_action_history',[]).count('free'),int(count>0))
            self.assertFalse(CH.live(self.a));self.valid()

    def test_all_four_training_orders_use_same_actual_ally_producer_self_is_excluded(self):
        for uid in TRAINING.RULES:
            self.setup()
            if uid!=TRAINING.INSPIRED:self.a.spec['feats'].append(uid)
            result=self.e.manual_feat(self.a,uid,self.p)
            self.assertEqual(result['status'],'applied');self.assertEqual(len(CH.live(self.p)),1)
            self.assertEqual(CH._uses(self.a)[0]['origin']['source'],uid);self.valid()
        self.setup();self.e.manual_feat(self.a,TRAINING.INSPIRED,self.a)
        self.assertFalse(CH._uses(self.a));self.assertFalse(CH.live(self.a))
        self.setup();self.p.side='enemy'
        result=self.e.manual_feat(self.a,TRAINING.INSPIRED,self.p)
        self.assertEqual(result['status'],'applied');self.assertFalse(CH.live(self.p));self.valid()

    def test_five_stratagems_pinpoint_and_director_reach_actual_successful_completion(self):
        for uid in sorted(CLASS_PASSIVE.STRATAGEMS):
            helper=STRATAGEM_FIXTURE.ClassPassiveCombatBulkTests();helper.rules=self.rules
            self.e,self.a,self.p,_=helper.fixture(feats=[uid])
            F.base_patch(self.a,{'skills':{'매력':4,'명령':5,'집중':4,'생존':4,'육상':4,'협박':4}},reason='actual prerequisite skills')
            for feature in (M.TRAINING,M.CLASS):TFA.acquire_static(self.e,self.a,feature,acquisition_request_id='acquire/'+feature)
            self.answer('cheerleader','Motivated');self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
            before=AP.available(self.a);self.assertEqual(self.e.activate_class_passive(self.a,self.p,uid),(1,0))
            self.assertEqual(len(CH.live(self.p,'Motivated')),1);self.assertEqual(AP.available(self.a),before-2);self.valid()
        self.setup();self.a.spec['feats'].extend([PRECISION.PRECISION,PRECISION.PINPOINT]);self.start(self.a)
        self.assertEqual(PRECISION.activate(self.e,self.a,self.p),(1,0));self.assertEqual(len(CH.live(self.p)),1);self.valid()
        self.setup();self.a.spec.setdefault('classes',[]).append(DIRECTIVES.CLASS);self.a.spec['feats'].append(DIRECTIVES.FEATURE);self.start(self.a)
        self.e.use_decisive_director(self.a,self.p,adjustment='increase');self.assertEqual(len(CH.live(self.p)),1);self.valid()

    def test_cheered_stacks_but_one_actual_save_rolls_exactly_twice_and_uses_best(self):
        self.setup(combat=False);self.moment();self.moment();self.answer('cheerleader_cheered',True)
        self.assertEqual(len(CH.live(self.b,'Cheered')),2)
        result=self.save(first=18,second=2)
        self.assertTrue(result['passed']);self.assertEqual(result['natural'],18)
        self.assertEqual(result['cheered']['rolls'],[18,2]);self.assertEqual(len(CH.live(self.b)),1)
        result=self.save(first=2,second=17);self.assertEqual(result['natural'],17)
        self.assertFalse(CH.live(self.b));self.assertEqual(len(CH.history(self.b)),2);self.valid()

    def test_cheered_decline_and_invalid_multiple_selection_preserve_instances(self):
        self.setup(combat=False);self.moment();self.answer('cheerleader_cheered',False)
        self.assertEqual(self.save(first=2)['natural'],2);self.assertEqual(len(CH.live(self.b)),1)
        self.answer('cheerleader_cheered',[CH.live(self.b)[0]['id']])
        self.unchanged(lambda:self.save());self.valid()

    def test_excited_only_actual_damaging_hit_adds_five_dr_once_and_miss_preserves(self):
        self.setup(combat=False,moves=['메가톤펀치']);self.answer('cheerleader','Excited');self.moment();self.moment()
        self.answer('cheerleader_excited',True);self.b.side='enemy';self.e.start_round(self.e.everyone);self.start(self.p)
        move=self.rules.move('move/메가톤펀치')
        baseline=self.e.roll_damage(self.p,self.b,move,set_damage=True)
        self.assertEqual(len(CH.live(self.b)),2)
        with patch.object(type(self.e),'d20',new=lambda e:1):self.e.use_move(self.p,self.b,move['id'],set_damage=True)
        self.assertEqual(len(CH.live(self.b)),2);self.start(self.p);hp=self.b.hp
        with patch.object(type(self.e),'d20',new=lambda e:18):self.e.use_move(self.p,self.b,move['id'],set_damage=True)
        self.assertEqual(hp-self.b.hp,max(1,baseline-5));self.assertEqual(len(CH.live(self.b)),1)
        self.assertEqual(CH.history(self.b)[0][E.KEY]['end_event']['reduction'],5);self.valid()

    def test_motivated_restores_toward_real_ace_base_and_requires_own_free_action(self):
        for simple in (False,True):
            self.setup(combat=False,abilities=['단순'] if simple else []);self.a.spec.setdefault('classes',[]).append(TRAINING.ACE)
            self.e.train_pokemon(self.a,[(self.p,[])],minutes=30,reason='actual Ace training',request_id='ace-base',
                safe=True,trained_stats={self.p.entity_id:'atk'},source_clause_id='C04-009')
            self.assertEqual(self.p.stages['atk'],1)
            self.answer('cheerleader','Motivated');self.e.start_round(self.e.everyone);self.e.manual_feat(self.a,TRAINING.INSPIRED,self.p)
            instance=CH.live(self.p)[0]['id'];self.e.change_stage(self.p,'atk',-1)
            self.unchanged(lambda:self.e.use_motivated(self.p,instance,'atk'))
            self.start(self.p);result=self.e.use_motivated(self.p,instance,'atk')
            self.assertEqual((result['baseline'],result['before'],result['after']),(1,-1 if simple else 0,1))
            self.assertFalse(CH.live(self.p));self.assertEqual(self.p._action_history[-1],'free');self.valid()

    def test_lifetime_survives_round_scene_faint_and_original_source_withdrawal(self):
        self.setup(combat=False);self.moment();uid=CH.live(self.b)[0]['id']
        self.e.start_round(self.e.everyone);self.e.end_round();self.e.end_encounter();self.e.end_scene()
        self.e.lose_hp(self.b,self.b.hp,source='actual faint boundary')
        self.assertTrue(self.b.fainted);self.assertEqual(CH.live(self.b)[0]['id'],uid)
        self.assertTrue(self.e.revive(self.b,10));self.assertFalse(self.b.fainted)
        for feature in (M.FEATURE,M.CLASS):
            decisions=self.base.decisions(feature)
            self.e.retrain_trainer_source(self.a,feature,**decisions)
        self.assertEqual(CH.live(self.b)[0]['id'],uid)
        self.answer('cheerleader_cheered',True);self.assertEqual(self.save()['natural'],17);self.valid()

    def test_invalid_choice_and_second_grant_failure_roll_back_native_order_and_decision(self):
        self.setup();self.answer('cheerleader',['Cheered','Excited']);self.unchanged(lambda:self.moment([self.b,self.c]))
        self.answer('cheerleader','Cheered');original=E.create
        def fail_second(engine,actor,**kwargs):
            if kwargs.get('kind')==CH.KIND and actor.entity_id==self.c.entity_id:
                engine.rulings.answers.clear();engine.rng.random();raise ValueError('second actual cheer grant failed')
            return original(engine,actor,**kwargs)
        with patch.object(E,'create',side_effect=fail_second):self.unchanged(lambda:self.moment([self.b,self.c]))
        self.valid()

    def test_support_actual_parent_acquisition_is_historical_and_friend_guard_owner_is_current(self):
        self.setup(support=True,combat=False,moves=['도우미'],abilities=['프렌드가드'])
        F.base_patch(self.a,{'skills':{'매력':1,'명령':1}},reason='later skill rank decline')
        self.e.start_round(self.e.everyone);self.start(self.p);self.e.use_move(self.p,self.b,'move/도우미')
        self.assertEqual(len(CH.live(self.b)),1);self.assertEqual(CH._uses(self.a)[0]['origin']['kind'],'inspirational_support');self.valid()
        for invalid in ('unowned','suppressed','enemy'):
            self.setup(support=True,combat=False,moves=['도우미'],abilities=['프렌드가드'])
            if invalid=='unowned':self.p.spec['trainer_id']=self.b.entity_id;self.p.spec['trainer']=self.b.name
            if invalid=='suppressed':self.p.abilities_suppressed=True
            if invalid=='enemy':self.b.side='enemy'
            self.e.start_round(self.e.everyone);self.start(self.p);self.e.use_move(self.p,self.b,'move/도우미')
            self.assertFalse(CH._uses(self.a));self.valid()

    def test_support_self_coat_and_team_blessing_apply_to_actual_trainer_allies_once(self):
        for move in ('아쿠아링','빛의장막'):
            self.setup(support=True,combat=False,moves=[move],abilities=['프렌드가드'])
            self.e.start_round(self.e.everyone);self.start(self.p);before=AP.available(self.a)
            self.e.use_move(self.p,self.p,'move/'+move)
            self.assertEqual(len(CH._uses(self.a)),1);self.assertEqual(len(CH.live(self.p)),1);self.assertFalse(CH.live(self.a))
            self.assertEqual(AP.available(self.a),before-int(move=='빛의장막'))
            if move=='빛의장막':self.assertEqual([len(CH.live(t)) for t in (self.b,self.c)],[1,1])
            COMPLETE.refresh(self.e);self.assertEqual(len(CH._uses(self.a)),1);self.valid()

    def test_support_battery_manual_ability_and_enemy_or_missing_friend_guard_controls(self):
        self.setup(support=True,combat=False,abilities=['프렌드가드','배터리']);self.b.pos=(2,0)
        self.e.start_round(self.e.everyone);self.start(self.p)
        result=self.e.activate_ability(self.p,'배터리',self.b)
        self.assertEqual(len(CH.live(self.b)),1);self.assertTrue(result['effect_id'])
        self.assertEqual(CH._uses(self.a)[0]['origin']['activation']['kind'],'manual_ability');self.valid()
        self.setup(support=True,combat=False,abilities=['배터리']);self.e.start_round(self.e.everyone);self.start(self.p)
        self.e.activate_ability(self.p,'배터리',self.b);self.assertFalse(CH._uses(self.a));self.valid()

    def test_support_mixed_actual_area_targets_disqualify_whole_activation(self):
        from grid import Grid
        self.setup(support=True,combat=False,moves=['흔들흔들댄스'],abilities=['프렌드가드'])
        self.e.grid=Grid(8,8);self.p.pos=(2,2);self.b.pos=(2,3);self.c.pos=(3,2);self.c.side='enemy';self.a.pos=(0,0)
        self.e.start_round(self.e.everyone);self.start(self.p)
        with patch.object(type(self.e),'d20',new=lambda e:18):
            self.e.use_move_on(self.p,self.b,'move/흔들흔들댄스',self.e.everyone)
        self.assertIn('혼란',self.b.conditions);self.assertIn('혼란',self.c.conditions)
        self.assertFalse(CH._uses(self.a));self.valid()

    def test_excited_enemy_attack_preserves_actual_passive_pending_prefix_and_consumption(self):
        import passive_events as PASSIVE
        self.setup(combat=False,moves=['메가톤펀치'],abilities=['자기과신'])
        self.answer('cheerleader','Excited');self.moment();self.answer('cheerleader_excited',True)
        self.b.side=None;self.b.hp=1;self.e.start_round(self.e.everyone);self.start(self.p)
        with patch.object(type(self.e),'d20',new=lambda e:18):
            with self.assertRaises(PASSIVE.PassiveEventPending) as error:
                self.e.use_move(self.p,self.b,'move/메가톤펀치',set_damage=True)
        self.assertEqual(self.e._passive_pending,error.exception.event_id)
        self.assertIn(error.exception.event_id,self.e._passive_events)
        self.assertLessEqual(self.b.hp,0);self.assertEqual(self.p.move_uses['move/메가톤펀치'],1)
        self.assertFalse(CH.live(self.b));self.assertEqual(len(CH.history(self.b)),1)
        self.b.side='enemy';self.e.deliver_passive_event(error.exception.event_id);self.valid()

    def test_support_child_acquisition_requires_actual_parent_and_adept_charm(self):
        self.setup(combat=False)
        self.unchanged(lambda:TFA.acquire_static(self.e,self.a,CH.SUPPORT,acquisition_request_id='missing-parent'))
        TFA.acquire_static(self.e,self.a,CH.BRIGADE,acquisition_request_id='brigade')
        F.base_patch(self.a,{'skills':{'매력':3,'명령':2}},reason='actual below Adept acquisition rank')
        self.unchanged(lambda:TFA.acquire_static(self.e,self.a,CH.SUPPORT,acquisition_request_id='low-rank'))
        F.base_patch(self.a,{'skills':{'매력':4,'명령':2}},reason='actual Adept acquisition rank')
        TFA.acquire_static(self.e,self.a,CH.SUPPORT,acquisition_request_id='support')
        decisions=self.base.base.decisions(self.e,self.a,CH.BRIGADE,request='withdraw-parent')
        self.unchanged(lambda:self.e.retrain_trainer_source(self.a,CH.BRIGADE,**decisions));self.valid()

    def test_authored_triggered_ability_held_suffix_only_cheers_after_actual_completion_once(self):
        import test_historical_effect_source_closure as AUTHORED
        import effects as FX
        fixture=AUTHORED.AcceptedTriggerSources();fixture.base=self.rules;fixture.setUp()
        self.setup(support=True,combat=False,abilities=['프렌드가드'],rules=fixture.r)
        fixture.e=self.e;fixture.a=self.p
        fixture.register(is_feat=False,effects=[
            {'type':'stage_change','stat':'atk','delta':1,'target':'self','if':'target was asleep'},
            {'type':'stage_change','stat':'def','delta':1,'target':'self'}])
        self.e.start_round(self.e.everyone);self.start(self.p)
        returned=self.e.end_of_turn(self.p)
        self.assertEqual(returned['status'],'awaiting_input');self.assertFalse(CH.live(self.p))
        token=next(t for t,row in self.e._effect_dispatch_receipts.items() if row['status']=='condition_unknown')
        self.e.resolve_effect_condition(self.p,token,target_was_asleep=True,reason='actual historical observation for authored Ability')
        self.assertEqual((self.p.stages['atk'],self.p.stages['def']),(1,1))
        self.assertEqual(len(CH.live(self.p)),1);CH.refresh_batches(self.e);self.assertEqual(len(CH._uses(self.a)),1)
        self.assertEqual(CH._uses(self.a)[0]['origin']['activation']['kind'],'effect_batch');self.valid()

    def test_native_reactive_ability_grant_uses_its_actual_recipient(self):
        import reactive_ability_events as REACTIVE
        self.setup(support=True,combat=False,moves=['물대포'],abilities=['프렌드가드','변환자재'])
        self.c.side='enemy';self.e.start_round(self.e.everyone);self.start(self.p)
        self.e.choose_reactive_ability(self.p,REACTIVE.PROTEAN,reason='actual next native type-change choice')
        with patch.object(type(self.e),'d20',new=lambda e:18):self.e.use_move(self.p,self.c,'move/물대포',set_damage=True)
        self.assertEqual(self.p.types,['물']);self.assertEqual(len(CH.live(self.p)),1)
        self.assertFalse(CH.live(self.c));self.assertFalse(CH.live(self.a))
        origin=CH._uses(self.a)[0]['origin']['activation'];self.assertEqual(origin['kind'],'reactive_ability')
        completion=self.e._move_completions[origin['completion_id']]
        grant=completion[REACTIVE.TAG]['applications'][0]['grants'][0]
        self.assertIs(grant['recipient'],self.p);self.valid()

    def test_tera_shell_actual_interrupt_self_activation_triggers_support_once(self):
        import test_category2_ability_interrupt_choices as INTERRUPT_FIXTURE
        fixture=INTERRUPT_FIXTURE.AbilityInterruptChoiceTests();fixture.rules=self.rules;fixture.setUp()
        self.coach(fixture,fixture.t)
        event=fixture.waiting();fixture.choose(event)
        self.assertEqual(fixture.t.types,['물']);self.assertEqual(len(CH.live(fixture.t)),1)
        self.assertFalse(CH.live(self.a));self.assertEqual(len(CH._uses(self.a)),1)
        self.assertEqual(CH._uses(self.a)[0]['origin']['activation']['event_id'],event);self.valid()

    def test_perish_body_actual_pair_rejects_enemy_mix_and_cheers_allied_attack_pair(self):
        import test_category2_perish_body as REACTION_FIXTURE
        for allied in (False,True):
            fixture=REACTION_FIXTURE.PerishBodyTests();fixture.r=self.rules;fixture.setUp()
            self.coach(fixture,fixture.t)
            if allied:fixture.a.side='party'
            before=AP.available(self.a);event=fixture.offer();fixture.choose(event)
            self.assertEqual([len(CH.live(actor)) for actor in (fixture.a,fixture.t)],[int(allied)]*2)
            self.assertEqual(AP.available(self.a),before-int(allied));self.assertFalse(CH.live(self.a))
            self.assertEqual(len(CH._uses(self.a)),int(allied));self.valid()

    def test_codec_preserves_independent_instances_and_rejects_changed_producer_or_consumption(self):
        self.setup(combat=False);self.moment();self.moment();self.answer('cheerleader_cheered',True);self.save()
        saved=self.state();loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(saved,ensure_ascii=False)))
        holder=next(a for a in loaded.everyone if a.entity_id==self.b.entity_id)
        self.assertEqual(len(CH.live(holder)),1);self.assertEqual(len(CH.history(holder)),1);self.assertTrue(loaded.validate_state()['valid'])
        CH.live(self.b)[0]['effect']['condition']='Excited';self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)


if __name__=='__main__':unittest.main()
