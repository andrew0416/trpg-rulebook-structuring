"""Q16/Q17 complete source alternatives through existing native producers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from state_codec import dump_engine,load_engine
import exhaust_moves as EXHAUST,vortex_state as VORTEX,turn as TURN
import test_category2_exhaust_action_debt as EX
import test_category2_vortex_parameters as VX
import test_book_duelist_momentum as DUELIST_FIXTURE
import combat_timing as TIME

KR_EX='korean_standard_swift';EN_EX='english_standard_shift'
KR_VX='korean_mandatory_strict';EN_VX='english_optional_inclusive'


def select(owner,engine,actor,variant):
    choice={'value':variant,'reason':'actual table source decision',
            'scope':owner.source_choices(actor)['decision_scope']}
    owner.select_source(engine,actor,choice)
    return choice


def answer(engine,value):
    engine.rulings.answers=[row for row in engine.rulings.answers if row['key']!='vortex_escape_attempt']
    engine.rulings.add_answer('vortex_escape_attempt',value,reason='actual optional escape decision',scope='permanent')


class ExhaustSourceVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
    fixture=EX.ExhaustActionDebtTests.fixture
    next_user_turn=staticmethod(EX.ExhaustActionDebtTests.next_user_turn)

    def test_both_complete_pairs_actual_miss_due_budget_and_command_lock(self):
        for variant,debt,budget in ((KR_EX,{'standard':1,'swift':1},{'standard':0,'shift':1,'swift':0}),
                                    (EN_EX,{'standard':1,'shift':1},{'standard':0,'shift':0,'swift':1})):
            with self.subTest(variant=variant):
                e,t,p,target=self.fixture()
                choice=select(EXHAUST,e,p,variant)
                with patch.object(e,'d20',return_value=1):e.use_move(p,target,'move/파괴광선')
                self.assertEqual(p.pending_action_loss,debt)
                self.assertEqual((p.spec[EXHAUST.KEY]['policy_variant'],p.spec[EXHAUST.KEY]['source_choice']),(variant,choice))
                self.assertEqual(p.move_uses['move/파괴광선'],1)
                self.next_user_turn(e,e.everyone,p)
                self.assertEqual(p.budget,budget);self.assertEqual(p._action_history,[])
                with self.assertRaisesRegex(ValueError,'Exhaust prevents'):
                    e.pokemon_activity(t,'command_move',pokemon=p,target=target,move_id='struggle')
                e.end_of_turn(p);self.assertNotIn(EXHAUST.KEY,p.spec)
                e.end_round();e.start_round(e.everyone);e.start_of_turn(p)
                self.assertEqual(e.pokemon_activity(t,'command_move',pokemon=p,target=target,move_id='struggle')['status'],'submitted')

    def test_current_activation_eligibility_uses_the_same_selected_pair_atomically(self):
        for variant,prior,blocked in ((KR_EX,'swift',True),(KR_EX,'shift',False),
                                      (EN_EX,'swift',False),(EN_EX,'shift',True),
                                      (EN_EX,'standard',True)):
            with self.subTest(variant=variant,prior=prior):
                e,_,p,target=self.fixture();select(EXHAUST,e,p,variant)
                self.assertTrue(TURN.spend(e,p,prior,'actual prior action'))
                before=deepcopy((p.budget,p.move_uses,e.rng.getstate(),target.hp))
                with patch.object(e,'d20',return_value=1) as roll:
                    out=e.use_move(p,target,'move/파괴광선')
                if blocked:
                    self.assertEqual(out,0);roll.assert_not_called()
                    self.assertEqual((p.budget,p.move_uses,e.rng.getstate(),target.hp),before)
                    self.assertNotIn(EXHAUST.KEY,p.spec)
                else:
                    self.assertTrue(roll.called);self.assertEqual(p.move_uses['move/파괴광선'],1)
                    self.assertEqual(p.spec[EXHAUST.KEY]['policy_variant'],variant)

    def test_pending_and_active_keep_producing_english_across_future_choice_gm_and_fresh_rules_json(self):
        for restoration in ('gm','json'):
            with self.subTest(restoration=restoration):
                e,_,p,target=self.fixture();select(EXHAUST,e,p,EN_EX)
                with patch.object(e,'d20',return_value=1):e.use_move(p,target,'move/파괴광선')
                producing=deepcopy(p.spec[EXHAUST.KEY])
                select(EXHAUST,e,p,KR_EX)
                if restoration=='gm':
                    e.gm.snapshot('pending-english-exhaust')
                    e.end_encounter(e.everyone);e.gm.restore('pending-english-exhaust')
                else:e=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(e),ensure_ascii=False)))
                p=next(c for c in e.everyone if c.entity_id==p.entity_id)
                self.assertEqual(p.spec[EXHAUST.KEY],producing)
                self.next_user_turn(e,e.everyone,p)
                self.assertEqual(p.budget,{'standard':0,'shift':0,'swift':1})
                active=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(e),ensure_ascii=False)))
                p=next(c for c in active.everyone if c.entity_id==p.entity_id)
                self.assertEqual(p.spec[EXHAUST.KEY]['policy_variant'],EN_EX)
                self.assertEqual(p.spec['exhaust_source_choice']['value'],KR_EX)
                active.end_of_turn(p);self.assertNotIn(EXHAUST.KEY,p.spec)
                self.assertTrue(active.validate_state()['valid'])

    def test_actual_actor_current_source_and_scoped_decision_rejection_are_atomic(self):
        e,_,p,_=self.fixture()
        good={'value':EN_EX,'reason':'actual source choice','scope':EXHAUST.source_choices(p)['decision_scope']}
        for bad in (EN_EX,{'value':EN_EX,'reason':'not scoped'},dict(good,scope=dict(good['scope'],profile_hash='changed'))):
            before=dump_engine(e)
            with self.assertRaises(ValueError):EXHAUST.select_source(e,p,bad)
            self.assertEqual(dump_engine(e),before)
        clone=Combatant(e.r,deepcopy(p.spec))
        before=dump_engine(e)
        with self.assertRaises(ValueError):EXHAUST.select_source(e,clone,good)
        self.assertEqual(dump_engine(e),before)
        with patch.object(e.r.ruleset,'exclude_units',e.r.ruleset.exclude_units|{'keyword/탈진'}):
            with self.assertRaises(ValueError):EXHAUST.select_source(e,p,good)
        self.assertEqual(dump_engine(e),before)


class VortexSourceVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
    setUp=VX.VortexParameterTests.setUp
    actor=VX.VortexParameterTests.actor
    begin=VX.VortexParameterTests.begin
    hit=VX.VortexParameterTests.hit
    end_target=VX.VortexParameterTests.end_target

    def produce(self,variant,*,trap=False):
        select(VORTEX,self.e,self.t,variant)
        self.begin();self.assertGreater(self.hit(mid=VX.TRAP if trap else VX.VORTEX),0)
        self.e.end_of_turn(self.a)
        if variant==EN_VX:answer(self.e,True)

    def test_equal_20_14_8_2_on_successive_actual_turns_distinguishes_both_definitions(self):
        for variant in (KR_VX,EN_VX):
            for nth,threshold in enumerate((20,14,8,2),1):
                with self.subTest(variant=variant,turn=nth):
                    self.setUp();self.produce(variant)
                    for _ in range(nth-1):
                        self.end_target(1)
                        self.assertIn('조이기',self.t.conditions)
                        self.e.start_round(self.e.everyone)
                    self.end_target(threshold)
                    self.assertEqual('조이기' in self.t.conditions,variant==KR_VX)
                    if variant==KR_VX:self.assertEqual(self.t.custom_conditions['vortex']['ends'],nth)
                    else:self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)

    def test_optional_decline_advances_real_ends_missing_invalid_are_atomic_and_fifth_never_prompts(self):
        self.produce(EN_VX)
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='vortex_escape_attempt']
        self.e.start_of_turn(self.t,initiative_count=20)
        for bad in (None,1):
            if bad is not None:answer(self.e,bad)
            before=dump_engine(self.e)
            with patch.object(self.e,'d20',side_effect=AssertionError('no roll before a valid attempt decision')):
                with self.assertRaisesRegex(ValueError,'choose whether'):self.e.end_of_turn(self.t)
            self.assertEqual(dump_engine(self.e),before)
        answer(self.e,False)
        with patch.object(self.e,'d20',side_effect=AssertionError('declined escape must not roll')):
            self.e.end_of_turn(self.t)
        self.assertEqual(self.t.custom_conditions['vortex']['ends'],1)
        for nth in (2,3,4):
            self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=20)
            with patch.object(self.e,'d20',side_effect=AssertionError('declined escape must not roll')):
                self.e.end_of_turn(self.t)
            self.assertEqual(self.t.custom_conditions['vortex']['ends'],nth)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t,initiative_count=20)
        real=type(self.e.rulings).decide
        def refuse_fifth(rulings,request,*args,**kwargs):
            if request.get('type') in ('vortex_escape_attempt','duelist_eleven'):
                raise AssertionError('fifth automatic end has no attempt or automatic11 choice')
            return real(rulings,request,*args,**kwargs)
        with patch.object(type(self.e.rulings),'decide',new=refuse_fifth),patch.object(self.e,'d20',side_effect=AssertionError('fifth auto')):
            self.e.end_of_turn(self.t)
        self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)

    def test_real_duelist_eleven_is_never_requested_on_decline_and_is_consumed_on_attempt(self):
        for attempt in (False,True):
            with self.subTest(attempt=attempt):
                helper=DUELIST_FIXTURE.DuelistMomentumTests();helper.rules=Rules(ROOT,ruleset='all')
                e,_,p,_=helper.setup();helper.rounds(3)
                select(VORTEX,e,p,EN_VX);e.apply_status(p,'조이기')
                answer(e,True)
                for _ in range(2):
                    helper.start(p)
                    with patch.object(type(e),'d20',new=lambda engine:1):e.end_of_turn(p)
                helper.expend(2);helper.start(p)
                self.assertTrue(any(row.get('duelist_eleven') for row in TIME.records(p)))
                helper.answer('duelist_eleven',True);answer(e,attempt)
                requests=[];real=type(e.rulings).decide
                def observe(rulings,request,*args,**kwargs):
                    requests.append(deepcopy(request))
                    return real(rulings,request,*args,**kwargs)
                with patch.object(type(e.rulings),'decide',new=observe),patch.object(type(e),'d20',new=lambda engine: (_ for _ in ()).throw(AssertionError('no random d20 on decline or selected automatic11'))):
                    e.end_of_turn(p)
                self.assertEqual(any(row.get('type')=='duelist_eleven' for row in requests),attempt)
                self.assertEqual('조이기' in p.conditions,not attempt)
                if not attempt:self.assertEqual(p.custom_conditions['vortex']['ends'],3)
                self.assertTrue(e.validate_state()['valid'])

    def test_bonus_producing_definition_duplicate_and_fresh_restore_keep_real_progress(self):
        for restoration in ('gm','json'):
            with self.subTest(restoration=restoration):
                self.setUp();self.produce(EN_VX,trap=True)
                self.end_target(1);producing=deepcopy(self.t.custom_conditions['vortex'])
                select(VORTEX,self.e,self.t,KR_VX)
                self.e.apply_status(self.t,'조이기')
                self.assertEqual(self.t.custom_conditions['vortex'],producing)
                if restoration=='gm':
                    self.e.gm.snapshot('english-vortex')
                    self.e.cure_status(self.t,'조이기');self.e.gm.restore('english-vortex')
                else:self.e=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
                actors={c.name:c for c in self.e.everyone};self.a=actors['source'];self.t=actors['target']
                self.assertEqual(self.t.custom_conditions['vortex'],producing)
                self.e.start_round(self.e.everyone);answer(self.e,True);self.end_target(17)
                self.assertFalse({'조이기','둔화','수렁'}&self.t.conditions)
                self.e.apply_status(self.t,'조이기')
                self.assertEqual(self.t.custom_conditions['vortex']['policy_variant'],KR_VX)
                self.e.start_round(self.e.everyone);self.end_target(20)
                self.assertIn('조이기',self.t.conditions)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_current_source_scope_and_registered_actor_are_required_before_future_selection(self):
        good={'value':EN_VX,'reason':'actual source choice','scope':VORTEX.source_choices(self.t)['decision_scope']}
        before=dump_engine(self.e)
        for bad in (EN_VX,dict(good,scope=dict(good['scope'],definition_hash='changed'))):
            with self.assertRaises(ValueError):VORTEX.select_source(self.e,self.t,bad)
            self.assertEqual(dump_engine(self.e),before)
        clone=Combatant(self.r,deepcopy(self.t.spec))
        with self.assertRaises(ValueError):VORTEX.select_source(self.e,clone,good)
        with patch.object(self.r.ruleset,'exclude_units',self.r.ruleset.exclude_units|{VORTEX.SOURCE}):
            with self.assertRaises(ValueError):VORTEX.select_source(self.e,self.t,good)
        self.assertEqual(dump_engine(self.e),before)


if __name__=='__main__':unittest.main(verbosity=2)
