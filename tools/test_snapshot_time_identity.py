"""Snapshot state isolation, identity graph and round-boundary regressions."""
import copy,hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import frequency as FREQ

class SnapshotIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self):
        e=Engine(self.rules,seed=301)
        a=Combatant(self.rules,copy.deepcopy(self.rules.creatures['pokemon/archie']))
        b=Combatant(self.rules,dict(copy.deepcopy(a.spec),id='pokemon/archie-second',name='second'))
        e.everyone=e.gm.everyone=[a,b]
        return e,a,b
    def delayed(self,e,a,b):
        e.delayed=[dict(kind='heal',who=b,attacker=a,turns=1,effect={'fraction_of_max':[1,2]},src='test',healing_source_kind='move')]

    def test_round_number_and_actor_frequency_round_markers_restore_together(self):
        e,a,b=self.fixture();e.round_no=7;a._round_marker=7;a.aoo_used=True;FREQ.state(a)['turn']=4
        e.gm.snapshot('before')
        e.round_no=8;a._round_marker=8;a.aoo_used=False;FREQ.state(a)['turn']=5
        e.gm.restore('before')
        self.assertEqual((e.round_no,a._round_marker,a.aoo_used,FREQ.state(a)['turn']),(7,7,True,4))

    def test_delayed_target_and_attacker_are_original_actors(self):
        e,a,b=self.fixture();self.delayed(e,a,b);e.gm.snapshot();e.gm.restore()
        self.assertIs(e.delayed[0]['who'],b);self.assertIs(e.delayed[0]['attacker'],a)

    def test_delayed_healing_executes_after_restore(self):
        e,a,b=self.fixture();b.hp=1;self.delayed(e,a,b);e.gm.snapshot()
        e.delayed.clear();b.hp=5;e.gm.restore();e.end_of_turn(b)
        self.assertEqual(b.hp,1+b.max_hp//2);self.assertEqual(e.delayed,[])

    def test_same_snapshot_can_replay_delayed_healing_repeatedly(self):
        e,a,b=self.fixture();b.hp=1;self.delayed(e,a,b);e.gm.snapshot()
        for _ in range(3):
            e.gm.restore();self.assertEqual(b.hp,1);self.assertIs(e.delayed[0]['who'],b)
            e.end_of_turn(b);self.assertEqual(b.hp,1+b.max_hp//2);self.assertEqual(e.delayed,[])

    def test_nested_engine_references_to_actors_keep_identity(self):
        from grid import Grid
        e,a,b=self.fixture();e.grid=Grid(3,3)
        e.field={'owners':(a,b),'nested':[{'target':b}]};e.hazards={(1,1):{'owner':a}}
        e.gm.snapshot();e.gm.restore()
        self.assertIs(e.field['owners'][0],a);self.assertIs(e.field['nested'][0]['target'],b)
        self.assertIs(e.hazards[(1,1)]['owner'],a)

    def test_actor_referenced_outside_roster_is_not_cloned(self):
        e,a,b=self.fixture();e.everyone=e.gm.everyone=[b];self.delayed(e,a,b)
        a.hp=17;e.gm.snapshot();a.hp=2;e.gm.restore()
        self.assertIs(e.delayed[0]['attacker'],a);self.assertEqual(a.hp,17)

    def test_cross_actor_references_are_preserved(self):
        e,a,b=self.fixture()
        e.gm.set_custom(a,'snapshot_graph',{'linked_target':b},reason='snapshot graph fixture')
        e.gm.set_custom(b,'snapshot_graph',{'linked_target':a},reason='snapshot graph fixture')
        e.gm.snapshot();a.custom_conditions.pop('snapshot_graph');b.custom_conditions.pop('snapshot_graph');e.gm.restore()
        self.assertIs(a.custom_conditions['snapshot_graph']['linked_target'],b);self.assertIs(b.custom_conditions['snapshot_graph']['linked_target'],a)

    def test_mutable_alias_across_engine_and_actor_is_preserved(self):
        e,a,b=self.fixture();shared={'counter':2}
        e.gm.set_custom(a,'snapshot_graph',shared,reason='snapshot alias fixture');e.field={'shared':shared}
        e.gm.snapshot();shared['counter']=9;e.gm.restore()
        self.assertEqual(e.field['shared']['counter'],2)
        self.assertIs(e.field['shared'],a.custom_conditions['snapshot_graph'])
        e.field['shared']['counter']=13;e.gm.restore()
        self.assertEqual(a.custom_conditions['snapshot_graph']['counter'],2)

    def test_source_state_mutation_does_not_change_snapshot(self):
        e,a,b=self.fixture();self.delayed(e,a,b)
        e.gm.set_custom(a,'snapshot_graph',{'nested':[2]},reason='snapshot isolation fixture');e.gm.snapshot()
        e.delayed[0]['turns']=90;a.custom_conditions['snapshot_graph']['nested'].append(3);e.gm.restore()
        self.assertEqual(e.delayed[0]['turns'],1);self.assertEqual(a.custom_conditions['snapshot_graph']['nested'],[2])

    def test_item_modifier_alias_within_actor_stays_live(self):
        import items as ITEMS
        import world_entities as WORLD
        e,a,b=self.fixture()
        WORLD.register_object(e,'snapshot-alias-item',location={'kind':'unknown'},
            reason='snapshot modifier alias fixture',kind='item_instance',
            item_rule_id='item/예리한손톱',owner_id=a.entity_id)
        ITEMS.register_item(e,a,'예리한손톱',source_instance_id='snapshot-alias-item')
        # Retain a legacy graph alias on a real native item registration.
        a._item_reg['예리한손톱']['mods']=[a.modifiers[-1]]
        e.gm.snapshot();e.gm.restore()
        self.assertIs(a._item_reg['예리한손톱']['mods'][0],a.modifiers[-1])

    def test_clock_offset_and_recovery_timer_rewind_together(self):
        e,a,b=self.fixture();b.hp=0;e.heal(b,1,source_kind='ordinary_item')
        e.start_round([a]);e.at_round_offset(4);e.gm.snapshot()
        e.end_round();self.assertEqual((e.elapsed_seconds,b.faint_recovery_seconds),(10,590))
        for _ in range(2):
            e.gm.restore()
            self.assertEqual((e.elapsed_seconds,e.round_start_seconds,b.faint_recovery_seconds),(4,0,596))
            e.end_round();self.assertEqual((e.elapsed_seconds,b.faint_recovery_seconds),(10,590))

    def test_clock_only_off_roster_actor_identity_and_state_restore(self):
        e,a,b=self.fixture();e.everyone=e.gm.everyone=[a];b.on_field=False
        e.time_actors([b]);b.hp=17;e.gm.snapshot();b.hp=3;e._time_actors=[];e.gm.restore()
        self.assertTrue(any(c is b for c in e._time_actors));self.assertEqual(b.hp,17)
        self.assertFalse(b.on_field)

    def test_unresolved_time_intervals_are_isolated_and_actor_references_live(self):
        e,a,b=self.fixture();e.unresolved_time_intervals=[{'kind':'partial_round','actors':[b],'observed':4}]
        e.gm.snapshot();e.unresolved_time_intervals[0]['observed']=9;e.gm.restore()
        self.assertEqual(e.unresolved_time_intervals[0]['observed'],4)
        self.assertIs(e.unresolved_time_intervals[0]['actors'][0],b)

    def test_absent_actor_fields_are_removed_on_restore(self):
        e,a,b=self.fixture()
        if hasattr(a,'pending_action_loss'):delattr(a,'pending_action_loss')
        e.gm.snapshot();a.pending_action_loss={'standard':1};e.gm.restore()
        self.assertFalse(hasattr(a,'pending_action_loss'))

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='SNAPSHOT-TIME-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='SNAPSHOT-TIME-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='SNAPSHOT-TIME-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(SnapshotIdentityTests))
    paths=['engine/gm_state.py','engine/engine.py','engine/life.py','engine/effects_ext.py','engine/frequency.py','tools/test_snapshot_time_identity.py']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='In-memory snapshot graph identity, state isolation, delayed replay and round-marker coherence; not full session serialization.',
        results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},whole_rule_certified=False)
    (ROOT/'output/snapshot-time-identity-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)

