"""R04 partial lifetime adapter tests; synthetic pre-existing bindings, real Engine API.
Not source feature activation/whole Bound AP conformance evidence.
"""
import copy, hashlib, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules, Engine, Combatant
import action_points as AP
import effects as FX

class BoundAPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rules=Rules(str(ROOT),ruleset='all')
    def fixture(self, *, ending='none_specified', adopted=True, turn=True):
        e=Engine(self.rules,seed=12)
        def actor(name):
            return Combatant(self.rules,dict(name=name,kind='trainer',level=10,
                stats={s:30 for s in ('hp','atk','def','spa','spd','spe')},moves=[],abilities=[]))
        a,b=actor('actor'),actor('other');e.everyone=e.gm.everyone=[a,b]
        # Explicit import state: this test does NOT claim a source feat produced it.
        a.spec.update(ap_bound={'effect-A':2,'effect-B':1},ap_spent=1,ap_removed=1)
        m={'type':'damage_roll_mod','value':3};other={'type':'damage_roll_mod','value':3}
        a.modifiers=[m,other]
        if adopted:
            result=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method=ending,
                source_ref='test_fixture/preexisting-single-modifier; no source feature activation')
            self.assertEqual(result.status,'adopted')
        if turn:e.start_round([a,b]);e.start_of_turn(a)
        return e,a,b,m,other
    def projection(self,e,a):
        return copy.deepcopy((a.spec,a.modifiers,a.hp,a.temp_hp,a.injuries,getattr(a,'budget',None),a.took_standard,
            getattr(a,'_action_history',None),a.move_uses,e.rng.getstate(),e.elapsed_seconds,e.log_lines,
            [(k,v['state'],v['end_event'])for k,v in getattr(a,'_ap_bound_effects',{}).items()]))
    def release(self,e,a):return e.release_bound_ap(a,'effect-A',event_id='release-A')
    def test_adoption_does_not_create_or_double_reserve_AP(self):
        e,a,b,m,o=self.fixture(adopted=False);before=self.projection(e,a);avail=AP.available(a)
        z=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method='none_specified',source_ref='test_fixture')
        self.assertEqual(z.status,'adopted');self.assertEqual(before,self.projection(e,a)[:-1]+([],))
        self.assertEqual(AP.available(a),avail)
    def test_release_exact_instance_effect_and_AP(self):
        e,a,b,m,o=self.fixture();before=AP.available(a);rng=e.rng.getstate();budget=dict(a.budget)
        move={'type':'노말','class':'물리'}
        self.assertEqual(FX.passive_damage_mods(e,a,b,move,{'attacker':a,'target':b})[1],6)
        z=self.release(e,a);self.assertEqual(z.status,'released');self.assertEqual(z.released_ap,2)
        self.assertTrue(z.performed_free_action);self.assertEqual(AP.available(a),before+2)
        self.assertEqual(a.spec['ap_bound'],{'effect-B':1});self.assertIs(a.modifiers[0],o)
        self.assertEqual(FX.passive_damage_mods(e,a,b,move,{'attacker':a,'target':b})[1],3)
        self.assertEqual(a.spec['ap_spent'],1);self.assertEqual(a.spec['ap_removed'],1)
        self.assertEqual(a.budget,budget);self.assertEqual(e.rng.getstate(),rng)
        self.assertEqual(a._action_history,['free']);self.assertFalse(a.took_standard)
    def test_no_standard_heavy_injury_consequence(self):
        e,a,b,m,o=self.fixture();a.injuries=5;hp=a.hp
        self.assertEqual(self.release(e,a).status,'released');self.assertEqual(a.hp,hp);self.assertFalse(a.took_standard)
    def test_zero_standard_shift_swift_budget_still_free(self):
        e,a,b,m,o=self.fixture();a.budget=dict(standard=0,shift=0,swift=0)
        self.assertEqual(self.release(e,a).status,'released');self.assertEqual(sum(a.budget.values()),0)
    def test_duplicate_release_cannot_refund_or_record_action_again(self):
        e,a,b,m,o=self.fixture();self.release(e,a);before=self.projection(e,a)
        self.assertEqual(self.release(e,a).status,'rejected');self.assertEqual(self.projection(e,a),before)
    def test_duplicate_adoption_no_effect_or_AP_change(self):
        e,a,b,m,o=self.fixture();before=self.projection(e,a)
        z=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method='none_specified',source_ref='test_fixture')
        self.assertEqual(z.status,'rejected');self.assertEqual(self.projection(e,a),before)
    def test_overlapping_equal_modifiers_are_not_removed_by_value(self):
        e,a,b,m,o=self.fixture();self.release(e,a);self.assertEqual(len(a.modifiers),1);self.assertIs(a.modifiers[0],o)
    def test_same_modifier_cannot_belong_to_two_bindings(self):
        e,a,b,m,o=self.fixture();before=self.projection(e,a)
        z=e.adopt_bound_ap_modifier(a,'effect-B',modifier=m,ending_method='none_specified',source_ref='test_fixture')
        self.assertEqual(z.status,'rejected');self.assertEqual(self.projection(e,a),before)
    def test_snapshot_restores_identity_and_replay(self):
        e,a,b,m,o=self.fixture();before=AP.available(a);e.gm.snapshot('bound');self.release(e,a)
        e.gm.restore('bound');self.assertEqual(AP.available(a),before)
        rec=a._ap_bound_effects['effect-A'];self.assertIs(rec['owner'],a);self.assertIs(rec['modifier'],a.modifiers[0])
        self.assertEqual(self.release(e,a).status,'released');self.assertEqual(AP.available(a),before+2)
    def test_scene_boundary_does_not_end_binding(self):
        e,a,b,m,o=self.fixture();e.end_of_turn(a);e.end_scene([a,b],round_elapsed_seconds=1)
        self.assertEqual(a.spec['ap_bound']['effect-A'],2);self.assertEqual(a._ap_bound_effects['effect-A']['state'],'active')
        self.assertTrue(any(v is m for v in a.modifiers));self.assertEqual(a.spec['ap_removed'],1)
    def test_reused_event_id_cannot_end_second_instance(self):
        e,a,b,m,o=self.fixture();e.adopt_bound_ap_modifier(a,'effect-B',modifier=o,ending_method='none_specified',source_ref='test_fixture')
        self.release(e,a);before=self.projection(e,a)
        z=e.release_bound_ap(a,'effect-B',event_id='release-A');self.assertEqual(z.status,'rejected');self.assertEqual(self.projection(e,a),before)
    def test_different_event_can_end_second_instance(self):
        e,a,b,m,o=self.fixture();e.adopt_bound_ap_modifier(a,'effect-B',modifier=o,ending_method='none_specified',source_ref='test_fixture')
        self.release(e,a);z=e.release_bound_ap(a,'effect-B',event_id='release-B');self.assertEqual(z.released_ap,1)
        self.assertEqual(a.spec['ap_bound'],{});self.assertEqual(a.modifiers,[])
    def test_legacy_scalar_adoption_is_pending(self):
        e,a,b,m,o=self.fixture(adopted=False);a.spec['ap_bound']=3;before=self.projection(e,a)
        z=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method='none_specified',source_ref='test_fixture')
        self.assertEqual(z.status,'pending');self.assertEqual(self.projection(e,a),before)
    def test_no_binding_identity_can_be_inferred_from_modifier_value(self):
        e,a,b,m,o=self.fixture(adopted=False);before=self.projection(e,a)
        self.assertEqual(self.release(e,a).status,'pending');self.assertEqual(self.projection(e,a),before)
    def test_unsourced_adoption_metadata_is_pending(self):
        e,a,b,m,o=self.fixture(adopted=False);before=self.projection(e,a)
        z=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method=None,source_ref='')
        self.assertEqual(z.status,'pending');self.assertEqual(self.projection(e,a),before)
    def test_unsupported_modifier_is_not_adopted(self):
        e,a,b,m,o=self.fixture(adopted=False);m['type']='stat_mod';before=self.projection(e,a)
        z=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method='none_specified',source_ref='test_fixture')
        self.assertEqual(z.status,'pending');self.assertEqual(self.projection(e,a),before)
    def test_shared_modifier_ownership_is_pending(self):
        e,a,b,m,o=self.fixture(adopted=False);b.modifiers.append(m);before=self.projection(e,a)
        z=e.adopt_bound_ap_modifier(a,'effect-A',modifier=m,ending_method='none_specified',source_ref='test_fixture')
        self.assertEqual(z.status,'pending');self.assertEqual(self.projection(e,a),before)


def add_case(name,setup,expected='rejected',ending='none_specified',turn=True):
    def test(self):
        e,a,b,m,o=self.fixture(ending=ending,turn=turn);setup(e,a,b,m,o);before=self.projection(e,a)
        self.assertEqual(self.release(e,a).status,expected);self.assertEqual(self.projection(e,a),before)
    setattr(BoundAPTests,'test_'+name,test)
add_case('specified_end_method_blocks_default',lambda *a:None,ending='specified')
add_case('unknown_end_method_is_not_absence',lambda *a:None,'pending',ending='unknown')
add_case('outside_encounter_has_no_own_turn_proof',lambda *a:None,'pending',turn=False)
add_case('other_actor_turn_rejected',lambda e,a,b,m,o:setattr(e,'_active_turn_actor',b))
add_case('closed_turn_rejected',lambda e,a,b,m,o:e.end_of_turn(a))
add_case('fainted_actor_rejected',lambda e,a,b,m,o:a.conditions.add('기절'))
add_case('zero_HP_rejected',lambda e,a,b,m,o:setattr(a,'hp',0))
add_case('sleep_blocks_this_noncuring_free_action',lambda e,a,b,m,o:a.conditions.add('잠듦'))
add_case('frozen_actor_rejected',lambda e,a,b,m,o:a.conditions.add('얼음'))
add_case('paralysis_free_combination_pending',lambda e,a,b,m,o:setattr(a,'_turn_action_limit',{'choose_one_of':['standard','shift']}),'pending')
add_case('turn_start_decision_pending',lambda e,a,b,m,o:setattr(a,'_turn_start_decisions_pending',True),'pending')
add_case('binding_amount_mismatch_pending',lambda e,a,b,m,o:a.spec['ap_bound'].__setitem__('effect-A',1),'pending')
add_case('changed_modifier_pending',lambda e,a,b,m,o:m.__setitem__('value',4),'pending')
add_case('equal_but_replaced_modifier_pending',lambda e,a,b,m,o:a.modifiers.__setitem__(0,dict(m)),'pending')
add_case('captured_actor_rejected',lambda e,a,b,m,o:setattr(a,'captured',True))
add_case('withdrawn_actor_rejected',lambda e,a,b,m,o:setattr(a,'on_field',False))
add_case('overallocated_AP_pending',lambda e,a,b,m,o:a.spec.__setitem__('ap_spent',7),'pending')
add_case('League_integration_remains_pending',lambda e,a,b,m,o:setattr(e,'_league_runtime',{'active':True}),'pending')

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='BOUND-AP-'+getattr(t,'_testMethodName',str(t)),status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='BOUND-AP-'+getattr(t,'_testMethodName',str(t)),status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='BOUND-AP-'+getattr(t,'_testMethodName',str(t)),status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(BoundAPTests))
    files=sorted(set([p for folder in ('engine','data','output/entities') for p in (ROOT/folder).rglob('*') if p.suffix in ('.py','.json')] + [Path(__file__),ROOT/'input/ch06-gameplay.md',ROOT/'input/ch07-combat.md']))
    report=dict(scope='Explicit imported single-modifier bindings only; no source feat activation producer; not complete R04.',results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in files},whole_semantic_closure=False)
    (ROOT/'output/bound-ap-release-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    sys.exit(0 if result.wasSuccessful() else 1)
