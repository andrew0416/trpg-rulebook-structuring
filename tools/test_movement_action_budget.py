"""Source-bound action downgrade checks; not whole movement conformance."""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from grid import Grid
import turn as TURN

class MovementActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def pair(self,kind='trainer'):
        def actor(name,k,pos):
            return Combatant(self.rules,dict(name=name,kind=k,level=1,stats={s:10 for s in ('hp','atk','def','spa','spd','spe')},types=[],moves=[],abilities=[],pos=pos,size='Medium',movement={'land':2}))
        e=Engine(self.rules);c=actor('mover',kind,(0,0));t=actor('target','pokemon',(12,0))
        e.grid=Grid(20,1);e.everyone=[c,t];e.gm.everyone=[c,t]
        TURN.reset_budget(e,c);return e,c,t
    def test_trainer_second_movement_is_not_standard_downgrade(self):
        e,c,t=self.pair();e.approach(c,t);self.assertEqual(c.pos,(2,0))
        before=copy.deepcopy(c.budget);e.approach(c,t)
        self.assertEqual(c.pos,(2,0));self.assertEqual(c.budget,before)
    def test_pokemon_second_movement_is_not_standard_downgrade(self):
        e,c,t=self.pair('pokemon');e.approach(c,t);before=copy.deepcopy(c.budget)
        e.approach(c,t);self.assertEqual(c.pos,(2,0));self.assertEqual(c.budget,before)
    def test_trainer_can_move_after_shift_was_nonmovement(self):
        e,c,t=self.pair();self.assertTrue(TURN.spend(e,c,'shift','nonmovement fixture'))
        e.approach(c,t);self.assertEqual(c.pos,(2,0));self.assertEqual(c.budget,dict(standard=0,shift=0,swift=1))
    def test_pokemon_cannot_downgrade_for_movement_even_after_nonmovement(self):
        e,c,t=self.pair('pokemon');self.assertTrue(TURN.spend(e,c,'shift','nonmovement fixture'));before=copy.deepcopy(c.budget)
        e.approach(c,t);self.assertEqual(c.pos,(0,0));self.assertEqual(c.budget,before)
    def test_trainer_movement_does_not_block_nonmovement_downgrade(self):
        e,c,t=self.pair();e.approach(c,t)
        self.assertTrue(TURN.spend(e,c,'shift','nonmovement fixture'));self.assertEqual(c.budget['standard'],0)
    def test_pokemon_movement_does_not_block_nonmovement_downgrade(self):
        e,c,t=self.pair('pokemon');e.approach(c,t)
        self.assertTrue(TURN.spend(e,c,'shift','nonmovement fixture'));self.assertEqual(c.budget['standard'],0)
    def test_regular_shift_still_moves_after_standard_action(self):
        for kind in ('trainer','pokemon'):
            with self.subTest(kind=kind):
                e,c,t=self.pair(kind);self.assertTrue(TURN.spend(e,c,'standard','fixture'));e.approach(c,t)
                self.assertEqual(c.pos,(2,0));self.assertEqual(c.budget['shift'],0)
    def test_failed_repeat_retains_standard_for_other_action(self):
        e,c,t=self.pair();e.approach(c,t);e.approach(c,t)
        self.assertTrue(TURN.spend(e,c,'standard','fixture'));self.assertEqual(c.pos,(2,0))
    def test_no_standard_budget_cannot_pay_for_extra_shift(self):
        e,c,t=self.pair();TURN.spend(e,c,'shift');TURN.spend(e,c,'standard');e.approach(c,t)
        self.assertEqual(c.pos,(0,0));self.assertEqual(c.budget['swift'],1)
    def test_new_turn_resets_movement_history(self):
        e,c,t=self.pair();e.approach(c,t);TURN.reset_budget(e,c);e.approach(c,t)
        self.assertEqual(c.pos,(4,0));self.assertEqual(c.budget['standard'],1)
    def test_snapshot_after_movement_restores_its_restriction(self):
        e,c,t=self.pair();e.approach(c,t);e.gm.snapshot('spent')
        TURN.reset_budget(e,c);e.gm.restore('spent');e.approach(c,t)
        self.assertEqual(c.pos,(2,0));self.assertEqual(c.budget['standard'],1)
    def test_snapshot_before_movement_restores_fresh_shift(self):
        e,c,t=self.pair();e.gm.snapshot('fresh');e.approach(c,t);e.gm.restore('fresh');e.approach(c,t)
        self.assertEqual(c.pos,(2,0));self.assertEqual(c.budget['standard'],1)
    def test_reachable_ordinary_budget_states_match_source_relation(self):
        # Independent finite source model: default one Standard/Shift/Swift,
        # conscious actor, no grants/borrowed turns/extra movement exceptions.
        from collections import deque
        actions=('standard','swift','shift_effect','shift_move','full','free')
        def oracle(kind,state,action):
            std,shift,swift,moved=state
            if action=='free':return True,state
            if action=='full':return (True,(std-1,shift-1,swift,moved)) if std and shift else (False,state)
            if action=='standard':return (True,(std-1,shift,swift,moved)) if std else (False,state)
            if action=='swift':
                if swift:return True,(std,shift,swift-1,moved)
                return (True,(std-1,shift,swift,moved)) if std else (False,state)
            movement=action=='shift_move'
            if shift:return True,(std,shift-1,swift,moved or movement)
            permitted=std and (not movement or (kind=='trainer' and not moved))
            return (True,(std-1,shift,swift,moved)) if permitted else (False,state)
        self.abstract_counts={}
        for kind in ('trainer','pokemon'):
            queue=deque([(1,1,1,False)]);seen=set(queue);branches=0
            e,c,t=self.pair(kind)
            while queue:
                state=queue.popleft()
                for action in actions:
                    with self.subTest(kind=kind,state=state,action=action):
                        allowed,expected=oracle(kind,state,action)
                        c.budget=dict(zip(('standard','shift','swift'),state[:3]));c._regular_shift_movement_used=state[3]
                        cost='shift' if action.startswith('shift_') else action
                        actual=TURN.spend(e,c,cost,'finite source oracle',movement=action=='shift_move')
                        resulting=(c.budget['standard'],c.budget['shift'],c.budget['swift'],c._regular_shift_movement_used)
                        self.assertEqual((actual,resulting),(allowed,expected));branches+=1
                        if expected not in seen:seen.add(expected);queue.append(expected)
            self.abstract_counts[kind]=dict(reachable_states=len(seen),branches=branches)
        self.assertEqual(set(self.abstract_counts),{'trainer','pokemon'})
    def test_source_anchors_links_and_false_closure(self):
        from audit_action_cost_semantics import validate
        spec=json.loads((ROOT/'data/verification/action-cost-semantics.json').read_text(encoding='utf-8'))
        self.assertEqual(validate(spec,ROOT),[])
        mutations=[('whole_rule_certified',True),('semantic_completeness_proved',True)]
        for field,value in mutations:
            bad=copy.deepcopy(spec);bad[field]=value;self.assertIn('unsupported_action_closure',validate(bad,ROOT))
        bad=copy.deepcopy(spec);bad['source_anchors']['PDF-POKEMON']['excerpt']='invented';self.assertIn('stale_action_anchor:PDF-POKEMON',validate(bad,ROOT))
        bad=copy.deepcopy(spec);bad['source_anchors']['MD-DEFAULT']['end']=39;self.assertIn('stale_action_anchor:MD-DEFAULT',validate(bad,ROOT))
        bad=copy.deepcopy(spec);bad['clauses'][0]['tests']=['missing_test'];self.assertIn('invalid_action_test_links:ACTION-COST-01',validate(bad,ROOT))
        bad=copy.deepcopy(spec);bad['unresolved_source_conflicts']=[];self.assertIn('lost_action_drop_conflict',validate(bad,ROOT))
    def test_invalid_movement_request_cannot_mutate_budget(self):
        e,c,t=self.pair();before=copy.deepcopy(c.budget)
        for kind,movement in [('standard',True),('shift','true'),('shift',1)]:
            with self.assertRaises(ValueError):TURN.spend(e,c,kind,movement=movement)
            self.assertEqual(c.budget,before)
    def test_already_in_range_does_not_spend_shift(self):
        e,c,t=self.pair();t.pos=(1,0);before=copy.deepcopy(c.budget);e.approach(c,t)
        self.assertEqual(c.budget,before);self.assertEqual(c.pos,(0,0))
    def test_no_grid_does_not_spend_shift(self):
        e,c,t=self.pair();e.grid=None;before=copy.deepcopy(c.budget);e.approach(c,t);self.assertEqual(c.budget,before)
    def test_fainted_actor_cannot_consume_or_move(self):
        e,c,t=self.pair();c.hp=0;before=copy.deepcopy(c.budget);e.approach(c,t)
        self.assertEqual(c.pos,(0,0));self.assertEqual(c.budget,before)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[];self.abstract_counts={}
        def addSuccess(self,t):
            super().addSuccess(t);self.rows.append(dict(id='MOVE-BUDGET-'+t._testMethodName,status='pass'));self.abstract_counts.update(getattr(t,'abstract_counts',{}))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='MOVE-BUDGET-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='MOVE-BUDGET-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(MovementActionTests))
    paths=['tools/test_movement_action_budget.py','engine/turn.py','engine/engine.py','engine/gm_state.py','input/ch07-combat.md']
    paths+=['tools/audit_action_cost_semantics.py','data/verification/action-cost-semantics.json','input/ch09-equipment.md','output/source-audit/2026-10-10/ptu-core-1.05.pdf']
    report=dict(abstract_model_counts=result.abstract_counts,scope='Ordinary budgeted action downgrade and movement-purpose tracking only',whole_rule_certified=False,results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    out=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'output/movement-action-budget-tests.json'
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
