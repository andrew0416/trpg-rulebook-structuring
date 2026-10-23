"""Book cheers through actual acquisition, Orders, condition and action owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon
import test_book_moment_of_action as FIXTURE
import go_fight_win as GO,cheerleader as CH,moment_of_action as M
import trainer_feature_acquisition as TFA,trainer_retraining as RETRAIN
import state_codec as CODEC,state_fields as F,action_points as AP
import effect_instances as E,priority_limited as P,combat_timing as CLOCK


class GoFightWinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='core')
        cls.errata=Rules(str(ROOT),ruleset='core+errata')
    def setup(self,*,acquire=True,combat=True,rules=None):
        base=FIXTURE.MomentOfActionTests();base.rules=rules or self.rules;base.setup(combat=False)
        self.base=base;self.e,self.a,self.b,self.c=base.e,base.a,base.b,base.c
        F.base_patch(self.a,{'skills':{'매력':5,'명령':2}},reason='actual Expert Charm prerequisite')
        if acquire:self.acquire()
        self.answer(False)
        if combat:self.open()
    def acquire(self):return TFA.acquire_static(self.e,self.a,GO.FEATURE,acquisition_request_id='acquire/'+GO.FEATURE)
    def answer(self,value):
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='cheerleader']
        self.e.rulings.add_answer('cheerleader',value,reason='explicit independent class choice',scope='permanent')
    def open(self):self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
    def use(self,cheer='defense',**kwargs):
        if cheer=='defense':kwargs.setdefault('stat','def')
        return self.e.go_fight_win(self.a,cheer=cheer,**kwargs)
    def state(self):return CODEC.dump_engine(self.e)
    def unchanged(self,fn):
        before=self.state()
        with self.assertRaises(ValueError):fn()
        self.assertEqual(self.state(),before)
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def next_round(self):
        self.e.start_of_turn(self.a,initiative_count=20);self.e.end_of_turn(self.a)
        self.e.end_round();self.open()
    def pokemon(self,name,*,side='party'):
        target=Combatant(self.e.r,build_pokemon(self.e.r,'이브이',20,name=name,moves=[],abilities=[]))
        self.e.gm.add_combatant(target,pos=(1,0),side=side,reason='actual battlefield participant')
        self.e.gm.observe_sensory_environment(self.a,target,paths={'auditory':True},present=True,reason='actual delivered cheer path')
        return target

    def test_acquisition_requires_actual_moment_and_expert_charm_then_retains_historical_rank(self):
        self.setup(acquire=False,combat=False)
        F.base_patch(self.a,{'skills':{'매력':4,'명령':2}},reason='only Adept Charm')
        self.unchanged(self.acquire)
        F.base_patch(self.a,{'skills':{'매력':5,'명령':2}},reason='Expert Charm')
        acquired=self.acquire();before=self.state()
        self.assertEqual(acquired['snapshot']['charm'],5)
        self.assertEqual(acquired['snapshot']['parent_request'],CH.acquired(self.a,M.FEATURE)['request_id'])
        self.assertEqual(self.acquire(),acquired);self.assertEqual(self.state(),before)
        self.unchanged(lambda:TFA.acquire_static(self.e,self.a,GO.FEATURE,acquisition_request_id='duplicate/'+GO.FEATURE))
        sources=RETRAIN._owned(self.a)
        self.assertEqual(RETRAIN._native_dependencies(self.e,self.a,sources)[GO.FEATURE],[M.FEATURE])
        F.base_patch(self.a,{'skills':{'매력':2,'명령':2}},reason='later rank decline after legal acquisition')
        self.open();row=self.use('temp_hp')
        self.assertEqual(row['charm'],2);self.assertEqual(self.b.temp_hp,2);self.valid()
        self.setup(acquire=False,combat=False)
        decisions=self.base.decisions(M.FEATURE);self.e.retrain_trainer_source(self.a,M.FEATURE,**decisions)
        self.a.spec['feats'].append(M.FEATURE)
        self.unchanged(self.acquire)

    def test_virtuoso_charm_restores_effective_eight_without_changing_six_dice(self):
        import skill_modifiers as SKILLS,state_grants as G
        self.setup(combat=False)
        F.base_patch(self.a,{'skills':{'매력':6,'명령':2}},reason='actual Master Charm before Virtuoso acquisition')
        G.transition(self.e,self.a,lambda e,a:a.spec.update(
            edges=[*a.spec.get('edges',[]),'edge/거장'],edge_choices={'edge/거장':['매력']}))
        self.assertEqual(SKILLS.effective_rank(self.e.r,self.a,'매력'),8)
        ids=[a.entity_id for a in (self.a,self.b,self.c)]
        self.e=CODEC.load_engine(Rules(str(self.e.r.root),ruleset='core'),json.loads(json.dumps(self.state())))
        index={a.entity_id:a for a in self.e.everyone};self.a,self.b,self.c=[index[uid] for uid in ids]
        self.assertEqual(SKILLS.rank(self.e.r,self.a,'매력')[2],6)
        self.assertEqual(len(self.e.skill_roll(self.a,'매력',fixed=[1]*6).faces),6)
        self.open();row=self.use('temp_hp')
        self.assertEqual((row['charm'],self.b.temp_hp,self.c.temp_hp),(8,8,8))
        self.valid();self.state()

    def test_three_real_outcomes_grant_fixed_book_conditions_without_intrinsic_ap_or_class_choice(self):
        for cheer in GO.CONDITIONS:
            self.setup();before=AP.available(self.a);evasion=self.b.evasion('물리')
            row=self.use(cheer)
            self.assertEqual(set(row['targets']),{self.b.entity_id,self.c.entity_id})
            self.assertEqual(AP.available(self.a),before);self.assertFalse(CH._uses(self.a))
            for target in (self.b,self.c):
                fixed=CH.live(target);self.assertEqual(len(fixed),1)
                self.assertEqual((fixed[0]['source'],fixed[0]['effect']['condition']),(GO.FEATURE,GO.CONDITIONS[cheer]))
                if cheer=='defense':self.assertEqual(target.stages['def'],1)
                elif cheer=='temp_hp':self.assertEqual(target.temp_hp,5)
                else:self.assertEqual(target.evasion('물리'),evasion+2)
            self.assertFalse(CH.live(self.a));self.valid()

    def test_complete_actual_battlefield_allies_include_other_trainers_and_pokemon_only(self):
        self.setup(combat=False)
        partner=self.pokemon('present ally');enemy=self.pokemon('actual foe',side='enemy')
        reserve=self.pokemon('recalled ally');self.e.gm.recall(reserve,reason='actual reserve off field')
        self.open();row=self.use('temp_hp')
        self.assertEqual(set(row['targets']),{self.b.entity_id,self.c.entity_id,partner.entity_id})
        self.assertEqual(partner.temp_hp,5);self.assertFalse(CH.live(enemy));self.assertFalse(CH.live(reserve));self.valid()

    def test_all_ally_communication_is_required_before_any_cost_or_fixed_grant(self):
        self.setup();self.base.audible(self.c,False)
        self.unchanged(lambda:self.use('temp_hp'))
        self.assertFalse(GO._uses(self.a));self.assertFalse(CH.live(self.b))
        self.base.audible(self.c,True);self.use('temp_hp');self.valid()

    def test_compound_priority_reserves_and_settles_both_costs_and_forbids_ordinary_timing(self):
        self.setup();self.e.start_of_turn(self.c,initiative_count=20);self.unchanged(self.use);self.e.end_of_turn(self.c)
        self.a.conditions.add('넘어짐');self.unchanged(self.use);self.a.conditions.remove('넘어짐')
        row=self.use();self.assertEqual(self.a.pending_action_loss,{'standard':1,'swift':1})
        receipt=P.records(self.a)[0];self.assertEqual(receipt['payment']['declared'],['standard','swift'])
        self.unchanged(lambda:self.use('temp_hp'))
        self.e.start_of_turn(self.a,initiative_count=20)
        self.assertEqual(self.a.budget,{'standard':0,'shift':1,'swift':0})
        self.assertEqual(P.records(self.a)[0]['payment']['phase'],'paid');self.e.end_of_turn(self.a)
        self.unchanged(lambda:self.use('temp_hp'));self.valid()

    def test_each_scene_cheer_has_one_quota_and_defense_choice_cannot_bypass_it(self):
        self.setup();self.use(stat='spd');self.assertEqual(self.b.stages['spd'],1)
        self.next_round();self.unchanged(lambda:self.use(stat='def'))
        self.use('temp_hp');self.next_round();self.use('evasion')
        self.e.start_of_turn(self.a,initiative_count=20);self.e.end_of_turn(self.a)
        self.e.end_round();self.e.end_scene();self.open();self.use(stat='def')
        self.assertEqual(len(GO._uses(self.a)),4);self.assertEqual(self.b.stages['def'],1);self.valid()

    def test_independent_class_free_choice_pays_zero_or_one_ap_in_addition_to_fixed_condition(self):
        for count,choice in ((1,'Cheered'),(2,'Excited')):
            self.setup()
            if count==1:self.c.side='enemy'
            self.answer(choice);before=AP.available(self.a);self.use()
            self.assertEqual(AP.available(self.a),before-int(count==2))
            self.assertEqual(len(CH._uses(self.a)),1);self.assertEqual(self.a._action_history.count('free'),1)
            self.assertEqual({r['source'] for r in CH.live(self.b)},{GO.FEATURE,CH.CLASS})
            self.assertEqual({r['effect']['condition'] for r in CH.live(self.b)},{'Motivated',choice});self.valid()

    def test_second_target_and_independent_class_failures_roll_back_all_new_producer_state(self):
        self.setup();original=E.create
        def fail_second(engine,actor,**kwargs):
            if kwargs.get('source')==GO.FEATURE and actor.entity_id==self.c.entity_id:
                engine.rng.random();engine.rulings.answers.clear();raise ValueError('actual second fixed cheer grant failed')
            return original(engine,actor,**kwargs)
        with patch.object(E,'create',side_effect=fail_second):self.unchanged(lambda:self.use('temp_hp'))
        self.answer(['Cheered','Excited']);self.unchanged(self.use)
        self.answer(False);self.use('temp_hp');self.assertEqual(self.b.temp_hp,5);self.valid()

    def test_new_book_producer_and_fixed_condition_restore_and_consume_through_existing_owner(self):
        self.setup();self.use();ids=[a.entity_id for a in (self.a,self.b,self.c)]
        saved=self.state();self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(saved,ensure_ascii=False)))
        index={a.entity_id:a for a in self.e.everyone};self.a,self.b,self.c=[index[uid] for uid in ids]
        self.e.change_stage(self.b,'atk',-2);self.e.start_of_turn(self.b,initiative_count=20)
        effect=CH.live(self.b,'Motivated')[0]
        self.e.use_motivated(self.b,effect['id'],'atk')
        self.assertEqual(self.b.stages['atk'],-1);self.assertEqual(len(CH.history(self.b)),1);self.valid()
        GO._uses(self.a)[0]['cheer']='evasion'
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(CODEC.StateCodecError):self.state()
        self.setup();self.use('evasion');saved=self.state();holder_id=self.b.entity_id
        for variant in ('bonus','deadline','recipient'):
            loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(saved,ensure_ascii=False)))
            holder=next(a for a in loaded.everyone if a.entity_id==holder_id)
            effect=CLOCK.records(holder)[0]
            if variant=='bonus':effect['evasion_modifier']=3
            elif variant=='deadline':effect['count_deadline']=(loaded.round_no+2,20)
            else:effect['go_fight_win_target']=self.a.entity_id
            self.assertFalse(loaded.validate_state()['valid'])
            with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(loaded)

    def test_book_source_does_not_adopt_the_errata_standard_two_ap_contract(self):
        self.setup(acquire=False,combat=False,rules=self.errata)
        import optional_state_effect_contracts as OPTIONAL
        row=OPTIONAL.clause(self.errata,'ERRATA-056')
        self.assertEqual((row['action'],row['ap']),('standard',2))
        self.assertNotEqual(row['rule_id'],GO.FEATURE)
        self.a.spec['feats'].append(row['rule_id']);self.unchanged(self.use)
        self.acquire();self.open();before=AP.available(self.a);issued=self.use()
        self.assertEqual(issued['source']['clause_id'],GO.CLAUSE)
        self.assertEqual(AP.available(self.a),before);self.assertEqual(self.a.pending_action_loss,{'standard':1,'swift':1})
        self.assertEqual(CH.live(self.b)[0]['source'],GO.FEATURE);self.valid()


if __name__=='__main__':unittest.main()
