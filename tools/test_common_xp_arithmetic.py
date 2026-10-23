"""Exact positive XP arithmetic from ch11:1251-1267 and default floor ch06:7.
Contest XP numerator conflicts in ch08 are outside this common encounter path.
"""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules
import downtime as DT

class CommonXPArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def test_decimal_integer_boundary_is_not_lost(self):
        for base,rate,expected in [(90,1.4,126),(50,2.3,115),(100,1.4,140)]:
            with self.subTest(base=base,rate=rate):
                per,detail=DT.award_exp(self.rules,[base],1,significance=rate,challenge=1)
                self.assertEqual(per,expected);self.assertEqual(detail['total'],expected)
    def test_party_division_preserves_exact_integer_boundary(self):
        per,detail=DT.award_exp(self.rules,[90],3,significance=1.4,challenge=1)
        self.assertEqual(per,42);self.assertEqual(detail['players'],3)
    def test_source_example_floors_fractional_xp(self):
        per,_=DT.award_exp(self.rules,[39],2,significance=1,challenge=1)
        self.assertEqual(per,19)
    def test_final_fraction_is_floored_without_redistributing_remainder(self):
        per,detail=DT.award_exp(self.rules,[10],3,significance=1.4,challenge=1)
        self.assertEqual(per,4);self.assertEqual(detail['total'],14)
        self.assertEqual(per*3,12)
    def test_participating_trainer_counts_twice(self):
        per,detail=DT.award_exp(self.rules,[20],1,significance=1.4,challenge=1,trainers_fought=[10])
        self.assertEqual(detail['base'],40);self.assertEqual(per,56)
    def test_partitioning_defeated_roster_does_not_change_xp(self):
        a,_=DT.award_exp(self.rules,[90],3,significance=1.4,challenge=1)
        b,_=DT.award_exp(self.rules,[40,50],3,significance=1.4,challenge=1)
        self.assertEqual((a,b),(42,42))
    def test_existing_half_and_integer_rates_are_preserved(self):
        for rate,expected in [(1,90),(1.5,135),(2,180),(3,270),(4,360),(5,450)]:
            with self.subTest(rate=rate):
                self.assertEqual(DT.award_exp(self.rules,[90],1,significance=rate,challenge=1)[0],expected)
    def test_challenge_decimal_integer_boundary_is_exact(self):
        # x0.5..x1.5 challenge adjustment is an independently named factor.
        self.assertEqual(DT.award_exp(self.rules,[90],1,significance=1,challenge=0.7)[0],63)
        self.assertEqual(DT.award_exp(self.rules,[90],3,significance=1,challenge=0.7)[0],21)
    def test_source_explicitly_allows_importance_above_five(self):
        for rate,expected in [(5,150),(6,180),(9,270)]:
            per,detail=DT.award_exp(self.rules,[90],3,significance=rate)
            self.assertEqual(per,expected)
            self.assertEqual(detail['significance'],rate)
    def test_values_outside_reader_domain_are_not_silently_clamped(self):
        for significance,challenge in [(0,1),(-1,1),(1,0.49),(1,1.51)]:
            with self.subTest(significance=significance,challenge=challenge):
                with self.assertRaises(ValueError):DT.award_exp(self.rules,[10],1,significance=significance,challenge=challenge)
    def test_invalid_factors_are_rejected(self):
        for value in [True,False,'2',float('nan'),float('inf'),-float('inf'),complex(2,1)]:
            for field in ['significance','challenge']:
                with self.subTest(value=value,field=field):
                    with self.assertRaises(ValueError):DT.award_exp(self.rules,[10],1,**{field:value})
    def test_player_count_cannot_be_invented_or_fractional(self):
        for players in [0,-1,1.5,True,'2']:
            with self.subTest(players=players):
                with self.assertRaises(ValueError):DT.award_exp(self.rules,[10],players)
    def test_combatant_levels_cannot_be_truncated_or_invented(self):
        for value in [0,-1,1.5,True,'2']:
            for field in ['defeated','trainers_fought']:
                with self.subTest(value=value,field=field):
                    args=dict(defeated=[10],players=1);args[field]=[value]
                    with self.assertRaises(ValueError):DT.award_exp(self.rules,**args)
    def test_empty_defeated_roster_yields_zero(self):
        self.assertEqual(DT.award_exp(self.rules,[],1,significance=6)[0],0)
    def test_positive_decimal_sweep_uses_integer_source_oracle(self):
        # 3600 bounded cases, rates1.0..1.5 and player counts1..6.
        # Expected values use integer tenths directly, not production helpers.
        for base in range(1,101):
            for numerator in range(10,16):
                for players in range(1,7):
                    expected=base*numerator//(10*players)
                    actual,_=DT.award_exp(self.rules,[base],players,significance=numerator/10,challenge=1)
                    self.assertEqual(actual,expected,(base,numerator,players))
    def test_finite_large_rate_does_not_overflow_display_metadata(self):
        # Representation boundary only: no claim that this value is game-authorized.
        per,detail=DT.award_exp(self.rules,[10],3,significance=1e308,challenge=1)
        self.assertEqual(per,10**309//3)
        self.assertIs(type(detail['significance']),float)
        self.assertEqual(detail['significance'],1e308)
        self.assertEqual(detail['total'],str(10**309))
        restored=json.loads(json.dumps({'per':per,'detail':detail},allow_nan=False))
        self.assertEqual(restored['per'],10**309//3)
        self.assertEqual(restored['detail']['total'],str(10**309))
    def test_overflowing_rational_metadata_preserves_fraction(self):
        from fractions import Fraction
        numerator=10**310+1
        per,detail=DT.award_exp(self.rules,[1],1,significance=Fraction(numerator,3),challenge=1)
        self.assertEqual(per,numerator//3)
        self.assertEqual(detail['significance'],str(numerator)+'/3')
        self.assertEqual(detail['total'],str(numerator)+'/3')
        self.assertEqual(json.loads(json.dumps(detail,allow_nan=False)),detail)
    def test_zero_roster_with_large_rate_preserves_zero_total_float(self):
        per,detail=DT.award_exp(self.rules,[],1,significance=10**310,challenge=1)
        self.assertEqual(per,0)
        self.assertIs(type(detail['total']),float)
        self.assertEqual(detail['total'],0.0)
        self.assertEqual(detail['significance'],str(10**310))
        json.dumps(detail,allow_nan=False)
    def test_metadata_remains_json_serializable(self):
        per,detail=DT.award_exp(self.rules,[90],3,significance=1.4,challenge=1)
        for field in ['significance','challenge','total']:
            self.assertIs(type(detail[field]),float)
        self.assertEqual(json.loads(json.dumps({'per':per,'detail':detail},allow_nan=False))['detail']['total'],126)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'COMMON-XP-'+t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'COMMON-XP-'+t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'COMMON-XP-'+t._testMethodName,'status':'error'})
        def addSubTest(self,t,st,e):
            super().addSubTest(t,st,e)
            if e:self.rows.append({'id':'COMMON-XP-'+t._testMethodName+str(st),'status':'fail'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommonXPArithmeticTests))
    paths=['tools/test_common_xp_arithmetic.py','engine/downtime.py','engine/engine.py','input/ch06-gameplay.md','input/ch11-running-the-game.md','input/ch07-combat.md','data/pokemon-rules.json']
    paths=[p for p in paths if (ROOT/p).exists()]
    # Include the actual file containing the configured XP formula and rate limits.
    for p in (ROOT/'data').glob('*.json'):
        if 'pokemon/experience-award' in p.read_text(encoding='utf-8'):
            rel=p.relative_to(ROOT).as_posix()
            if rel not in paths:paths.append(rel)
    anchors=[]
    for file,start,end in [('input/ch06-gameplay.md',7,12),('input/ch11-running-the-game.md',1251,1267),('input/ch07-combat.md',903,905)]:
        ls=(ROOT/file).read_text(encoding='utf-8').splitlines();excerpt='\n'.join(ls[start-1:end])
        anchors.append({'file':file,'start':start,'end':end,'excerpt':excerpt,'excerpt_sha256':hashlib.sha256(excerpt.encode()).hexdigest()})
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'scope':'Positive encounter XP exact decimal arithmetic, party division and strict-JSON display representation boundaries. Large-number tests establish input representation behavior, not game-rule authorization; independent of ch08 contest numerator conflict.','whole_rule_certified':False,'finite_boundary_case_count':3600,'source_anchors':anchors,'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    (ROOT/'output/common-xp-arithmetic-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
