"""Native trainer-participant models; partial DOMAIN-048, optional interactions/feats remain open."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from contest import Contestant,ContestRules,ContestEngine
from engine import Engine,Rules,Combatant
class Ones:
    def randint(self,a,b):return 1
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.native_rules=Rules(ROOT);cls.contest_rules=ContestRules(ROOT)
    def setUp(self):
        self.native=Engine(self.native_rules);self.e=ContestEngine(self.contest_rules);self.e.rng=Ones()
        self.pokemon=[];self.trainers=[];self.cs=[];self.partners=[]
        for i in range(3):
            common={'level':20,'stats':dict.fromkeys(['hp','atk','def','spa','spd','spe'],10),'moves':['연속자르기','꼬리흔들기']}
            t=Combatant(self.native_rules,dict(common,id=f't{i}',name=f'T{i}',kind='trainer',skills={'매력':'초보'}))
            p=Combatant(self.native_rules,dict(common,id=f'p{i}',name=f'P{i}',kind='pokemon',trainer_id=f't{i}'))
            self.native.everyone.extend([t,p]);self.native.gm.everyone=self.native.everyone
            c=self.e.contestant_from_combatants(self.native,p,t,'매력',{'근사함':6})
            partner=self.e.trainer_participant(c)
            self.trainers.append(t);self.pokemon.append(p);self.cs.append(c);self.partners.append(partner)
    def test_simultaneous_actual_run_all_six_actors_and_shared_pool(self):
        turns=Counter();neighbors=[];centers=Counter()
        def choose(c,rnd,adj,center):
            turns[c.name]+=1;neighbors.append(len(adj));centers[c.name]+=int(center)
            return '연속자르기',1
        self.e.run(self.cs,'근사함',choose,trainer_model='simultaneous',trainer_order=lambda c,t,r:[t,c] if r==2 else [c,t])
        self.assertEqual(set(turns.values()),{3});self.assertEqual(len(turns),6)
        self.assertEqual(set(centers.values()),{1});self.assertEqual(set(neighbors),{2,4})
        for c,t in zip(self.cs,self.partners):
            self.assertIs(c.stat_dice,t.stat_dice);self.assertEqual(c.stat_dice['근사함'],0)
        expected=sorted([c.appeal+t.appeal-c.fumble-t.fumble for c,t in zip(self.cs,self.partners)],reverse=True)
        self.assertEqual([r['net'] for r in self.e.last_standings],expected)
    def test_simultaneous_partners_have_separate_voltage(self):
        observed=[]
        def choose(c,rnd,adj,center):
            if rnd==1 and c.name.startswith('T'):observed.append(c.excitement)
            return ('꼬리흔들기' if rnd==1 and c.name.startswith('P') else '연속자르기'),0
        self.assertEqual(self.contest_rules.move_contest('꼬리흔들기')[1],'고조')
        self.e.run(self.cs,'근사함',choose,trainer_model='simultaneous',trainer_order=lambda c,t,r:[c,t])
        self.assertEqual(observed,[0,0,0])
        self.assertTrue(all(c.excitement!=t.excitement for c,t in zip(self.cs,self.partners)))
    def test_alternating_one_action_per_pair_and_shared_voltage(self):
        turns=Counter();neighbors=[]
        def choose(c,rnd,adj,center):turns[c.name]+=1;neighbors.append(len(adj));return '연속자르기',2
        self.e.run(self.cs,'근사함',choose,trainer_model='alternating',trainer_order=lambda c,t,r:[c if r%2 else t])
        self.assertEqual([turns[c.name] for c in self.cs],[2]*3);self.assertEqual([turns[t.name] for t in self.partners],[1]*3)
        self.assertEqual(set(neighbors),{1,2})
        for c,t in zip(self.cs,self.partners):self.assertEqual(c.excitement,t.excitement);self.assertEqual(c.stat_dice['근사함'],0)
    def test_alternating_rejects_same_actor_next_round(self):
        turns=[]
        def choose(c,rnd,*a):turns.append(rnd);return '연속자르기',0
        with self.assertRaises(ValueError):self.e.run(self.cs,'근사함',choose,trainer_model='alternating',trainer_order=lambda c,t,r:[c])
        self.assertEqual(turns,[1,1,1])
    def test_unowned_pair_and_changed_trainer_moves_are_not_admitted(self):
        manual=Contestant('fake',{},['연속자르기'],'매력',3,'귀여움')
        with self.assertRaises(ValueError):self.e.trainer_participant(manual)
        self.trainers[0].moves=[]
        with self.assertRaises(ValueError):self.e.run(self.cs,'근사함',lambda *a:None,trainer_model='simultaneous',trainer_order=lambda c,t,r:[c,t])
        self.assertFalse(self.cs[0].intro_completed)
    def test_no_implicit_order_or_mixed_model(self):
        for model,order in [('simultaneous',None),('both-and-shared',lambda c,t,r:[c,t])]:
            with self.assertRaises(ValueError):self.e.run(self.cs,'근사함',lambda *a:None,trainer_model=model,trainer_order=order)
        self.assertFalse(self.cs[0].intro_completed)
    def coordinator(self, i=0):
        self.trainers[i].spec['feats']=['class/코디네이터']
        self.trainers[i].spec['edges']=['edge/우아함']
        old=self.cs[i]
        self.cs[i]=self.e.contestant_from_combatants(self.native,self.pokemon[i],self.trainers[i],'매력',old.stat_dice)
        self.partners[i]=self.e.trainer_participant(self.cs[i])
    def test_coordinator_requires_real_feature_grace_and_novice_skill(self):
        c=self.cs[0]
        for feats,edges,rank in [([],['edge/우아함'],'초보'),(['class/코디네이터'],[],'초보'),(['class/코디네이터'],['edge/우아함'],'미숙')]:
            t=self.trainers[0];t.spec.update(feats=feats,edges=edges,skills={'매력':rank})
            before=deepcopy(vars(c))
            with self.assertRaises(ValueError):self.e.perform(c,'연속자르기','근사함',[],False,reroll_decision=lambda first:True)
            self.assertEqual(vars(c),before);self.assertFalse(self.e._coordinator_used)
        self.trainers[0].spec['skills']={'명령':'초보'};self.coordinator();c=self.cs[0]
        self.e.perform(c,'연속자르기','근사함',[],False,reroll_decision=lambda first:True)
        self.assertEqual(len(self.e._coordinator_used),1)
    def test_coordinator_choice_sees_first_roll_and_declining_keeps_use(self):
        self.coordinator();c=self.cs[0];seen=[]
        self.e.perform(c,'연속자르기','근사함',[],False,fixed_rolls=[6]*4,
                       reroll_decision=lambda first:seen.append(first) or False)
        self.assertEqual(seen[0]['rolls'],(6,)*4);self.assertEqual(seen[0]['appeal'],8)
        self.assertEqual(c.appeal,8);self.assertFalse(self.e._coordinator_used)
        # Even a maximum roll can be rerolled by choice; the second result replaces it.
        self.e.perform(c,'연속자르기','근사함',[],False,fixed_rolls=[6]*5,reroll_decision=lambda first:True)
        self.assertEqual(c.appeal,8);self.assertEqual(len(self.e._coordinator_used),1)
    def test_coordinator_actual_run_and_trainer_share_one_use(self):
        self.coordinator();seen=[]
        def choose(c,rnd,*args):
            if c is self.partners[0] and rnd==1:
                return '연속자르기',0,lambda first:seen.append(first['rolls']) or True
            return '연속자르기',0
        self.e.run(self.cs,'근사함',choose,trainer_model='simultaneous',trainer_order=lambda c,t,r:[t,c])
        self.assertEqual(len(seen),1);self.assertEqual(len(self.e._coordinator_used),1)
        before=deepcopy(vars(self.cs[0]))
        with self.assertRaises(ValueError):self.e.perform(self.cs[0],'연속자르기','근사함',[],False,reroll_decision=lambda first:True)
        self.assertEqual(vars(self.cs[0]),before)
    def test_coordinator_invalid_decision_preserves_first_roll_and_resumes_same_cost(self):
        self.coordinator();c=self.cs[0];before=deepcopy(vars(c));seen=[]
        def invalid(first):seen.append(first);return 'yes'
        with self.assertRaises(ValueError):
            self.e.perform(c,'연속자르기','근사함',[],False,spend_stat_dice=2,reroll_decision=invalid)
        self.assertEqual(c.stat_dice['근사함'],before['stat_dice']['근사함']-2)
        self.assertEqual((c.appeal,c.fumble),(before['appeal'],before['fumble']))
        self.assertTrue(self.e.log_lines);self.assertFalse(self.e._coordinator_used)
        def resume(first):
            self.assertEqual(first,seen[0]);return True
        self.e.perform(c,'연속자르기','근사함',[],False,spend_stat_dice=2,reroll_decision=resume)
        self.assertEqual(c.stat_dice['근사함'],before['stat_dice']['근사함']-2)
        self.assertTrue(self.e._coordinator_used)
    def test_coordinator_only_final_faces_trigger_gamble_voltage(self):
        self.coordinator();c=self.cs[0]
        uid='move/엉겨붙기';stat,effect=self.contest_rules.move_contest(uid);self.assertEqual(effect,'도박')
        c.moves=[uid];self.pokemon[0].moves=[uid]
        ring=self.contest_rules.mech('contest/type-match')['ring'];topic=ring[(ring.index(stat)+1)%5]
        class Sixes:
            def randint(self,a,b):return 6
        self.e.rng=Sixes()
        self.e.perform(c,uid,topic,[],False,fixed_rolls=[1,1],reroll_decision=lambda first:True)
        self.assertEqual((c.appeal,c.fumble,c.excitement),(4,0,2))
    def test_coordinator_legacy_auto_flag_and_unbound_claim_are_rejected(self):
        self.coordinator();c=self.cs[0]
        with self.assertRaises(ValueError):self.e.perform(c,'연속자르기','근사함',[],False,reroll_ok=True)
        abstract=Contestant('fake',{},['연속자르기'],'매력',3,'귀여움',trainer_edges=['edge/우아함'])
        with self.assertRaises(ValueError):self.e.perform(abstract,'연속자르기','근사함',[],False,reroll_decision=lambda first:True)
        self.assertFalse(self.e.log_lines);self.assertFalse(self.e._coordinator_used)
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
        def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    paths=['tools/test_category3_contest_modes.py','engine/contest.py','engine/engine.py','engine/skill_modifiers.py','engine/common_checks.py','engine/resolution_transaction.py','engine/ruleset.py','data/skill-check-policy.json','data/lookup-tables.json','data/contest-rules.json','data/rulesets.json','output/entities/moves.json','output/ruleunits.jsonl','input/ch08-contests.md','input/ch04-trainer-classes.md','input/ch03-skills-edges-feats.md','output/source-audit/2026-10-10/ptu-core-1.05.pdf']
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':'Partial DOMAIN-046/048: native two participation models and Coordinator contest reroll; damage/scene reroll and optional interactions remain unresolved.','results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    (ROOT/'output/category3-contest-modes-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
