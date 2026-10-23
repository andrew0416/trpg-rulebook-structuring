"""Source-derived common check boundaries and independent finite comparisons."""
import hashlib,itertools,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
import common_checks as C
from engine import Engine,Rules,Combatant
from builder import build_trainer

class CommonCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def engine(self,rank='초보'):
        engine=Engine(self.rules,seed=137)
        engine.everyone=engine.gm.everyone=[]
        return engine,self.actor(engine,'검사자',rank)
    def actor(self,engine,name,rank):
        actor=Combatant(self.rules,build_trainer(self.rules,name,10,
            {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
        actor.spec['skills']={'Athletics':rank}
        engine.everyone.append(actor)
        return actor
    def test_source_anchor_integrity(self):
        spec=json.loads((ROOT/'data/verification/common-check-semantics.json').read_text(encoding='utf-8'))
        for c in spec['clauses']:
            s=c['source'];lines=(ROOT/s['file']).read_text(encoding='utf-8').splitlines();text='\n'.join(lines[s['start']-1:s['end']])
            self.assertEqual(text,s['excerpt'],c['id']);self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),s['excerpt_sha256'])
            self.assertTrue(c['tests'])
    def test_contract_integrity_and_missing_evidence_rejected(self):
        import copy
        from audit_common_checks import validate
        spec=json.loads((ROOT/'data/verification/common-check-semantics.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(spec,ROOT),[])
        for mutate,expected in [(lambda s:s['clauses'][0].update(tests=[]),'missing_test:CHECK-01'),(lambda s:s['clauses'][0]['source'].update(excerpt='invented'),'stale_source:CHECK-01'),(lambda s:s.update(whole_rule_certified=True),'unsupported_completion_claim')]:
            bad=copy.deepcopy(spec);mutate(bad);self.assertIn(expected,validate(bad,ROOT))
    def test_engine_fixed_faces_invalid_before_rng(self):
        e,c=self.engine();state=e.rng.getstate()
        for faces in [[6],[6,6,6,6],[6,6,7]]:
            with self.assertRaises(ValueError):e.skill_check(c,'Athletics',10,fixed=faces)
            self.assertEqual(e.rng.getstate(),state)
    def test_dc_equality_and_neighbours(self):
        roll=C.SkillRoll(3,(2,3,4))
        for dc,passed,margin in [(8,True,1),(9,True,0),(10,False,-1)]:
            r=C.against_dc(roll,dc);self.assertEqual((r.passed,r.margin),(passed,margin))
    def test_small_rank_all_rolls_against_independent_threshold_sets(self):
        for rank in range(1,4):
            for faces in itertools.product(range(1,7),repeat=rank):
                total=sum(faces)
                for dc in range(1,20):
                    expected=dc in range(1,total+1)
                    self.assertEqual(C.against_dc(C.SkillRoll(rank,faces),dc).passed,expected)
    def test_ordinary_rank_limits_and_bool_rejected(self):
        for rank in [0,7,True,2.0]:
            with self.assertRaises(ValueError):C.SkillRoll(rank,(1,))
    def test_fixed_roll_must_have_exact_faces(self):
        for faces in [(1,2),(1,2,3,4),(1,2,0),(1,2,7),(1,2,True),(1,2,3.0)]:
            with self.assertRaises(ValueError):C.SkillRoll(3,faces)
    def test_helper_minimum_rejected_before_rng_and_log(self):
        e,c=self.engine();state=e.rng.getstate()
        for rank in [1,2]:
            with self.assertRaises(ValueError):e.skill_check(c,'Athletics',10,helper_rank=rank)
            self.assertEqual(e.rng.getstate(),state)
    def test_assist_uses_floor_for_each_base_rank(self):
        for rank,bonus in [(0,0),(3,1),(4,2),(5,2),(6,3)]:
            self.assertEqual(C.SkillRoll(1,(1,),helper_rank=rank).total,1+bonus)
    def test_penalty_dice_are_subtracted_not_removed(self):
        r=C.SkillRoll(1,(6,),penalties=(1,1))
        self.assertEqual(r.total,4);self.assertTrue(C.against_dc(r,4).passed)
    def test_negative_totals_not_clamped(self):
        self.assertEqual(C.SkillRoll(1,(1,),modifier=-2,penalties=(6,)).total,-7)
    def test_engine_penalty_rolls_consume_separate_rng_draws(self):
        import random
        e,c=self.engine('不明')
        c.spec['skills']['Athletics']='미숙';oracle=random.Random(137)
        faces=tuple(oracle.randint(1,6) for _ in range(2));penalties=tuple(oracle.randint(1,6) for _ in range(3))
        r=e.skill_roll(c,'Athletics',penalty_count=3)
        self.assertEqual((r.faces,r.penalties),(faces,penalties));self.assertEqual(e.rng.getstate(),oracle.getstate())
    def test_invalid_penalties_do_not_consume_skill_rng(self):
        e,c=self.engine();state=e.rng.getstate()
        for options in [dict(penalty_count=1,fixed_penalties=[]),dict(penalty_count=1,fixed_penalties=[7]),dict(penalty_count=-1),dict(fixed=[1])]:
            with self.assertRaises(ValueError):e.skill_check(c,'Athletics',10,**options)
            self.assertEqual(e.rng.getstate(),state)
    def test_invalid_dc_does_not_consume_rng(self):
        e,c=self.engine();state=e.rng.getstate()
        with self.assertRaises(ValueError):e.skill_check(c,'Athletics',True)
        self.assertEqual(e.rng.getstate(),state)
    def test_opposed_ties_favor_status_quo(self):
        for a,b,winner in [(8,9,'defender'),(9,9,'defender'),(10,9,'challenger')]:
            self.assertEqual(C.opposed(C.SkillRoll(1,(1,),modifier=a-1),C.SkillRoll(1,(1,),modifier=b-1)),winner)
    def test_engine_opposed_uses_defender_on_tie(self):
        e,a=self.engine('불능');b=self.actor(e,'수비','불능')
        e.rng=SimpleNamespace(randint=lambda a,b:3)
        self.assertFalse(e.opposed_check(a,'Athletics',b,'Athletics'))
    def test_team_dc_uses_required_people_not_participants(self):
        rolls=[C.SkillRoll(1,(6,))]*3
        self.assertEqual(C.team(rolls,6,2),C.CheckResult(18,12,6,True))
        self.assertEqual(C.team(rolls,6,4),C.CheckResult(18,24,-6,False))
    def test_extra_team_participant_does_not_raise_dc(self):
        roll=C.SkillRoll(1,(6,));a=C.team([roll],5,2);b=C.team([roll,roll],5,2)
        self.assertEqual(a.dc,b.dc);self.assertFalse(a.passed);self.assertTrue(b.passed)
    def test_empty_team_and_invalid_required_count_rejected(self):
        with self.assertRaises(ValueError):C.team([],10,2)
        for count in [0,-1,True,1.5]:
            with self.assertRaises(ValueError):C.team([C.SkillRoll(1,(1,))],10,count)
    def test_extended_limited_final_attempt_can_complete(self):
        rolls=[C.SkillRoll(5,(1,1,1,1,1))]*2
        result=C.extended(rolls,5,2,5,True)
        self.assertEqual((result.status,result.attempt_limit,result.attempts_used),('complete',2,2))
    def test_extended_limited_exhaustion_and_zero_allowance(self):
        self.assertEqual(C.extended([C.SkillRoll(3,(1,1,1))],5,2,3,True).status,'exhausted')
        self.assertEqual(C.extended([],5,2,1,True).status,'exhausted')
    def test_extended_unlimited_progress_and_completion(self):
        r=C.SkillRoll(1,(1,))
        self.assertEqual(C.extended([r]*9,5,2,1,False).status,'in_progress')
        self.assertEqual(C.extended([r]*10,5,2,1,False).status,'complete')
    def test_extended_rejects_post_completion_and_post_limit(self):
        with self.assertRaises(ValueError):C.extended([C.SkillRoll(1,(6,))]*2,1,2,1,False)
        with self.assertRaises(ValueError):C.extended([C.SkillRoll(3,(1,1,1))]*2,100,2,3,True)
    def test_extended_requires_complexity_and_limit_decision(self):
        for complexity in [1,6,True]:
            with self.assertRaises(ValueError):C.extended([],5,complexity,3,False)
        with self.assertRaises(ValueError):C.extended([],5,2,3,None)
    def test_no_roll_branch_consumes_no_randomness(self):
        e,c=self.engine();state=e.rng.getstate()
        result=e.common_action(c,mode='no_roll',outcome='success',description='나무에 오른다')
        self.assertIsInstance(result,C.ActionOutcome);self.assertIsNone(result.check);self.assertEqual(e.rng.getstate(),state)
    def test_missing_action_branch_is_pending_not_failure(self):
        e,c=self.engine();state=e.rng.getstate();r=e.common_action(c)
        self.assertIsInstance(r,C.PendingDecision);self.assertEqual(e.rng.getstate(),state)
    def test_failed_check_can_be_adjudicated_success_with_cost(self):
        e,c=self.engine();r=e.common_action(c,'Athletics',10,mode='skill',fixed=[3,3,3],outcome='success_with_cost',description='건넜으나 물건을 떨어뜨림',cost='물건 손실',failure_margin_accepted=True)
        self.assertFalse(r.check.passed);self.assertEqual(r.outcome,'success_with_cost')
    def test_high_margin_does_not_invent_benefit(self):
        e,c=self.engine();r=e.common_action(c,'Athletics',1,mode='skill',fixed=[6,6,6])
        self.assertIsInstance(r,C.PendingDecision);self.assertEqual(r.check.margin,17)
    def test_invalid_defender_request_does_not_roll_challenger(self):
        e,c=self.engine();state=e.rng.getstate();bad=self.actor(e,'bad','bad-rank')
        with self.assertRaises(ValueError):e.opposed_check(c,'Athletics',bad,'Athletics')
        self.assertEqual(e.rng.getstate(),state)
    def test_opposed_accepts_separate_explicit_modifiers(self):
        e,c=self.engine();b=self.actor(e,'수비','초보')
        self.assertTrue(e.opposed_check(c,'Athletics',b,'Athletics',challenger_options={'fixed':[1,1,1],'mods':1},defender_options={'fixed':[1,1,1]}))
        self.assertFalse(e.opposed_check(c,'Athletics',b,'Athletics',challenger_options={'fixed':[1,1,1],'mods':1},defender_options={'fixed':[1,1,1],'mods':1}))
    def test_invalid_adjudication_rejected_before_rng(self):
        e,c=self.engine();state=e.rng.getstate()
        for options in [dict(outcome='typo',description='x'),dict(outcome='success',description=''),dict(outcome='success_with_cost',description='x',cost=3)]:
            with self.assertRaises(ValueError):e.common_action(c,'Athletics',10,mode='skill',**options)
            self.assertEqual(e.rng.getstate(),state)
    def test_failed_check_cannot_be_plain_success(self):
        r=C.against_dc(C.SkillRoll(3,(1,1,1)),100)
        self.assertIsInstance(C.adjudicate(r,outcome='success',description='no cost'),C.PendingDecision)
    def test_cost_and_margin_decision_are_required_for_failure_conversion(self):
        r=C.against_dc(C.SkillRoll(3,(3,3,3)),10)
        for opts in [dict(cost=None,failure_margin_accepted=True),dict(cost='item lost',failure_margin_accepted=False)]:
            self.assertIsInstance(C.adjudicate(r,outcome='success_with_cost',description='crossed',**opts),C.PendingDecision)
        result=C.adjudicate(r,outcome='success_with_cost',description='crossed',cost='item lost',failure_margin_accepted=True)
        self.assertEqual(result.cost,'item lost');self.assertFalse(result.check.passed)
    def test_specialized_action_remains_pending(self):
        e,c=self.engine();state=e.rng.getstate();r=e.common_action(c,mode='capture')
        self.assertIsInstance(r,C.PendingDecision);self.assertEqual(e.rng.getstate(),state)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='CHECK-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='CHECK-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='CHECK-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommonCheckTests))
    paths=[ROOT/'tools/audit_common_checks.py',ROOT/'data/verification/root-semantics.json',Path(__file__),ROOT/'engine/common_checks.py',ROOT/'engine/engine.py',ROOT/'data/core-rules.json',ROOT/'data/verification/common-check-semantics.json',ROOT/'input/ch06-gameplay.md',ROOT/'input/ch03-skills-edges-feats.md',ROOT/'input/ch11-running-the-game.md']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Ordinary common check components; not whole action semantics or extension conformance.',results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/common-check-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
