"""Sourced contest effects; partial DOMAIN-038/045, not a completion certificate."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from contest import Contestant,ContestRules,ContestEngine
class Sequence:
    def __init__(self,faces):self.faces=list(faces)
    def randint(self,a,b):return self.faces.pop(0)
class Ones:
    def randint(self,a,b):return 1
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=ContestRules(ROOT)
        cls.moves={}
        for uid in cls.r._moves:
            try:stat,eff=cls.r.move_contest(uid)
            except Exception:continue
            cls.moves.setdefault(eff,(uid,stat))
        assert len(cls.moves)==22
    def setUp(self):self.e=ContestEngine(self.r)
    def actor(self,name='A'):
        return Contestant(name,{},[x[0] for x in self.moves.values()],'매력',1,'귀여움')
    def use(self,c,eff,neighbors,n,*,faces=None,center=False,match=False,spend=0):
        uid,stat=self.moves[eff];ring=self.r.mech('contest/type-match')['ring'];topic=stat if match else ring[(ring.index(stat)+1)%5]
        self.e.perform(c,uid,topic,neighbors,center,spend_stat_dice=spend,fixed_rolls=faces if faces is not None else [2]*n)
    def test_attention_grabber_transfers_only_actual_loss(self):
        a,b,c=self.actor(),self.actor('B'),self.actor('C');a.excitement,b.excitement,c.excitement=1,1,3
        self.use(a,'주목 끌기',[b,c],2)
        self.assertEqual([x.excitement for x in [a,b,c]],[4,0,1])
    def test_big_show_three_voltage_clamped(self):
        a=self.actor();a.excitement=4;self.use(a,'빅 쇼',[],5);self.assertEqual((a.appeal,a.excitement),(5,5))
    def test_catching_up_strictly_all_neighbors_and_conditional_gain(self):
        for neighbor,expected,after in [(2,6,2),(1,3,1)]:
            a,b=self.actor(),self.actor('B');a.excitement=1;b.excitement=neighbor
            self.use(a,'따라잡기',[b],expected);self.assertEqual((a.appeal,a.excitement),(expected,after))
    def test_desperation_extra_faces_stack_with_center(self):
        for center,expected in [(False,(7,2)),(True,(8,4))]:
            a=self.actor();self.use(a,'필사',[],5,faces=[1,6,2,1,6],center=center);self.assertEqual((a.appeal,a.fumble),expected)
    def test_double_time_signed_component_is_not_clamped_before_turn_voltage(self):
        a,b=self.actor(),self.actor('B');a.excitement=5;b.excitement=0
        self.use(a,'더블 타임',[b],2);self.assertEqual((a.appeal,a.excitement),(2,3))
        a,b=self.actor(),self.actor('B');a.excitement=2;b.excitement=4
        self.use(a,'더블 타임',[b],6);self.assertEqual((a.appeal,a.excitement),(6,0))
    def test_excitement_gains_two_after_turn_start_snapshot(self):
        a=self.actor();a.excitement=4;self.use(a,'고조',[],7);self.assertEqual((a.appeal,a.excitement),(7,5))
    def test_exhausting_act_threshold_and_loss(self):
        for start,n in [(1,5),(2,8)]:
            a=self.actor();a.excitement=start;self.use(a,'기진맥진 행동',[],n);self.assertEqual((a.appeal,a.excitement),(n,0))
    def test_gamble_sixes_gain_voltage_and_cap(self):
        a=self.actor();a.excitement=4;self.use(a,'도박',[],6,faces=[6]*6);self.assertEqual((a.appeal,a.excitement),(12,5))
    def test_get_ready_doubles_next_effect_dice_once_not_stat_or_voltage(self):
        a=self.actor();a.excitement=3;self.use(a,'준비하기',[],4);self.assertTrue(a.double_next)
        stat=self.moves['빅 쇼'][1];a.stat_dice[stat]=2
        self.use(a,'빅 쇼',[],5,spend=2);self.assertEqual(a.appeal,9);self.assertFalse(a.double_next)
        self.use(a,'고조',[],7);self.assertEqual(a.appeal,16)
    def test_good_show_requires_all_neighbors_strictly_lower(self):
        for other,n,after in [(2,8,4),(3,5,3)]:
            a,b=self.actor(),self.actor('B');a.excitement=3;b.excitement=other;self.use(a,'굿 쇼',[b],n);self.assertEqual((a.appeal,a.excitement),(n,after))
    def test_incentives_only_matches_contest_type(self):
        for match,n,after,other in [(True,6,3,2),(False,5,2,3)]:
            a,b=self.actor(),self.actor('B');a.excitement=2;b.excitement=3;self.use(a,'장려',[b],n,match=match);self.assertEqual((a.appeal,a.excitement,b.excitement),(n,after,other))
    def test_inverse_and_reflective_appeal_use_current_voltage(self):
        for eff,n in [('반전 어필',5),('반영 어필',8)]:
            a=self.actor();a.excitement=4;self.use(a,eff,[],n);self.assertEqual((a.appeal,a.excitement),(n,4))
    def test_reliable_repetition_exception_still_needs_identical_move(self):
        a=self.actor();self.use(a,'신뢰',[],3);self.use(a,'신뢰',[],4);self.assertEqual((a.appeal,a.excitement),(7,1))
    def test_sabotage_assigns_roll_points_only_to_adjacent_targets(self):
        a,b,c=self.actor(),self.actor('B'),self.actor('C');c.immune_fumble=True
        self.use(a,'방해',[b,c],3,faces=[6,3,1]);self.assertEqual((a.appeal,b.fumble,c.fumble),(0,3,0))
    def test_safe_option_center_one_no_fumble_six_one_appeal(self):
        a=self.actor();self.use(a,'안전한 선택',[],4,faces=[1,6,5,2],center=True);self.assertEqual((a.appeal,a.fumble),(3,0))
    def test_saving_grace_lost_threshold_immunity_not_self_fumbles(self):
        for points,after in [(2,4),(5,3)]:
            a=self.actor();a.excitement=3;a.fumble=points
            self.use(a,'은총',[],4,faces=[1,2,2,2],center=True)
            self.assertEqual(a.excitement,after);self.assertEqual(a.fumble,max(points-3,0)+1);self.assertTrue(a.immune_fumble)
    def test_seen_nothing_yet_loses_voltage_but_keeps_turn_start_dice(self):
        a=self.actor();a.excitement=3;self.use(a,'이제부터',[],9);self.assertEqual((a.appeal,a.excitement),(9,0))
    def test_special_attention_affects_only_supplied_neighbors(self):
        a,b,c=self.actor(),self.actor('B'),self.actor('C');b.excitement=5
        self.use(a,'특별한 관심',[b],5);self.assertEqual((a.appeal,b.excitement,c.excitement),(5,5,0))
    def test_steady_performance_gain_one(self):
        a=self.actor();self.use(a,'안정된 공연',[],5);self.assertEqual((a.appeal,a.excitement),(5,1))
    def test_tease_face_override_and_neighbor_fumble(self):
        a,b=self.actor(),self.actor('B');self.use(a,'놀리기',[b],4,faces=[5,6,6,3],center=True);self.assertEqual((a.appeal,b.fumble),(4,2))
    def test_unsettling_self_two_adjacent_one_and_floor(self):
        a,b=self.actor(),self.actor('B');a.excitement=1;b.excitement=1
        self.use(a,'동요',[b],6);self.assertEqual((a.appeal,a.excitement,b.excitement),(6,0,0))
    def test_supercontest_rerolls_six_and_maps_each_face(self):
        self.e.rng=Sequence([6,6,1,2,3,4,5]);self.assertEqual([self.e.random_contest_type() for _ in range(5)],['근사함','강인함','아름다움','슬기로움','귀여움'])
    def test_supercontest_actual_run_uses_round_topic_without_intro_bonus(self):
        topics=iter(['근사함','강인함','아름다움']);self.e.random_contest_type=lambda:next(topics);self.e.rng=Ones()
        cs=[self.actor(str(i)) for i in range(3)];move=self.moves['신뢰'][0]
        for c in cs:c.moves=[move]
        self.e.run(cs,None,lambda *a:(move,0),variant='super')
        self.assertEqual(len([x for x in self.e.log_lines if '라운드 유형:' in x]),3)
        self.assertFalse(any('시작 어필' in x for x in self.e.log_lines))
    def test_festival_unresolved_reset_does_not_silently_choose(self):
        from ruleset import UnresolvedRuleSelection
        with self.assertRaises(UnresolvedRuleSelection):self.e.run([self.actor(str(i)) for i in range(3)],'근사함',lambda *a:None,variant='festival',contest_id='unresolved-festival-reset')
        self.assertEqual(self.e.log_lines,[])
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    paths=['tools/test_category3_contest_effects.py','engine/contest.py','engine/common_checks.py','engine/resolution_transaction.py','engine/ruleset.py','data/rulesets.json','data/contest-rules.json','output/entities/moves.json','output/ruleunits.jsonl','input/ch08-contests.md']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':'Partial DOMAIN-038/045; all 22 effects exercised, unresolved combinations and festival resets not certified.','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    (ROOT/'output/category3-contest-effects-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())

