"""Common ordinary HP-loss allocation; compatibility branches are not source proofs."""
import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import effects as FX
import effects_ext as EXT

class HPLossResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self,hp=70,temp=0,injuries=0):
        e=Engine(self.rules);c=Combatant(self.rules,dict(name='Resource boundary',kind='pokemon',level=1,stats=dict(hp=23,atk=5,**{'def':5},spa=5,spd=5,spe=5),types=['노말'],moves=[]))
        c.hp=hp;c.temp_hp=temp;c.injuries=injuries;e.everyone=e.gm.everyone=[c]
        e.gm.set_temp_hp(c,temp,reason='observed fixture temporary pool',duration_seconds=300)
        self.assertEqual(c.base_max_hp,80)
        return e,c,dict(attacker=c,target=c,who=c,engine=e,hit=True)
    def test_temp_absorption_boundaries(self):
        # ch07:623: other effects consume temporary HP first, then actual HP.
        for temp,loss,hp_after,temp_after in [(5,3,70,2),(5,5,70,0),(5,8,67,0),(0,8,62,0),(5,0,70,5)]:
            with self.subTest(temp=temp,loss=loss):
                e,c,_=self.fixture(temp=temp);e.lose_hp(c,loss)
                self.assertEqual((c.hp,c.temp_hp),(hp_after,temp_after))
    def test_actual_marker_only_after_temporary_pool(self):
        for temp,hp,inj in [(2,40,1),(3,41,0)]:
            e,c,_=self.fixture(hp=41,temp=temp);e.lose_hp(c,3)
            self.assertEqual((c.hp,c.temp_hp,c.injuries),(hp,0,inj))
    def test_loss_has_no_massive_damage_injury(self):
        # ch07:688 exempts HP-loss, not its actual HP marker crossings.
        e,c,_=self.fixture(temp=20);e.lose_hp(c,60)
        self.assertEqual((c.hp,c.temp_hp,c.injuries),(30,0,1))
    def test_real_hp_faint_boundary(self):
        for loss,hp,fainted in [(4,1,False),(6,0,True)]:
            e,c,_=self.fixture(hp=1,temp=5);e.lose_hp(c,loss)
            self.assertEqual((c.hp,c.fainted),(hp,fainted))
    def test_tenth_marker_injury_can_kill_at_positive_hp(self):
        e,c,_=self.fixture(hp=41,temp=1,injuries=9);e.lose_hp(c,2)
        self.assertEqual((c.hp,c.injuries,c.dead),(40,10,True))
    def test_healing_remains_actual_hp_only(self):
        e,c,_=self.fixture(hp=30,temp=10);e.lose_hp(c,5);e.heal(c,3)
        self.assertEqual((c.hp,c.temp_hp),(33,5))
    def test_no_attack_damage_reaction_dispatch(self):
        e,c,_=self.fixture(temp=20)
        with patch.object(EXT,'after_damage',side_effect=AssertionError('HP loss is not damage')):
            e.lose_hp(c,10)
        self.assertEqual((c.hp,c.temp_hp),(70,10))
    def test_effect_handler_ordinary_loss(self):
        e,c,ctx=self.fixture(temp=5);FX.h_hp_loss(e,c,c,dict(value=8),ctx)
        self.assertEqual((c.hp,c.temp_hp),(67,0))
    def test_legacy_effect_ordinary_loss(self):
        e,c,_=self.fixture(temp=5);e.apply_effect(c,c,dict(type='hp_loss',value=8),None,True,0,'fixture')
        self.assertEqual((c.hp,c.temp_hp),(67,0))
    def test_status_tick_consumes_temp_first(self):
        e,c,_=self.fixture(temp=20);e.apply_status(c,'독');c.took_standard=True;e.end_of_turn(c)
        self.assertEqual(c.hp,70);self.assertLess(c.temp_hp,20)
    def test_zero_setting_is_distinct_from_loss(self):
        e,c,ctx=self.fixture(temp=100);FX.h_self_hp_set(e,c,c,dict(self_hp=0),ctx)
        self.assertEqual((c.hp,c.temp_hp,c.injuries),(0,100,2));self.assertTrue(c.fainted)
    def test_negative_half_setting_is_distinct_from_loss(self):
        e,c,ctx=self.fixture(temp=100);FX.h_self_hp_set(e,c,c,dict(self_hp='-50% max'),ctx)
        self.assertEqual((c.hp,c.temp_hp,c.injuries),(-40,100,3));self.assertTrue(c.fainted)
    def test_explicit_unpreventable_setting_preserves_existing_cap_bypass(self):
        e,c,ctx=self.fixture(temp=100);c.damage_cap=dict(value=1)
        FX.h_self_hp_set(e,c,c,dict(self_hp='-50% max',unpreventable=True),ctx)
        self.assertEqual((c.hp,c.temp_hp),(-40,100))
    def test_cap_before_allocation_is_compatibility_not_source_closure(self):
        e,c,_=self.fixture(temp=5);c.damage_cap=dict(value=3);e.lose_hp(c,8)
        self.assertEqual((c.hp,c.temp_hp),(70,2))
    def test_unpreventable_loss_defaults_to_temp_first_without_damage_cap(self):
        e,c,ctx=self.fixture(temp=20);c.damage_cap=dict(value=1)
        FX.h_hp_loss(e,c,c,dict(value=8,unpreventable=True),ctx)
        self.assertEqual((c.hp,c.temp_hp),(70,12))
    def test_execute_keeps_existing_direct_faint_model(self):
        # Source says faint; full HP/injury/cap semantics of this legacy adapter remain open.
        e,c,ctx=self.fixture(temp=100);EXT.h_execute(e,c,c,dict(threshold=101),ctx)
        self.assertEqual((c.hp,c.temp_hp),(0,100));self.assertTrue(c.fainted)
    def test_gm_direct_override_remains_distinct(self):
        e,c,_=self.fixture(temp=100);e.gm.set_hp(c,value=0,reason='explicit fixture intervention')
        self.assertEqual((c.hp,c.temp_hp,c.injuries),(0,100,0))
    def test_snapshot_restores_both_resources_and_marker_state(self):
        e,c,_=self.fixture(hp=41,temp=2);e.gm.snapshot('before');e.lose_hp(c,3)
        self.assertEqual((c.hp,c.temp_hp,c.injuries),(40,0,1))
        e.gm.restore('before');self.assertEqual((c.hp,c.temp_hp,c.injuries),(41,2,0))
        e.lose_hp(c,3);self.assertEqual((c.hp,c.temp_hp,c.injuries),(40,0,1))
    def test_unknown_loss_kind_rejects_before_mutation(self):
        e,c,_=self.fixture(temp=5)
        with self.assertRaises(ValueError):e.lose_hp(c,8,loss_kind='damage')
        self.assertEqual((c.hp,c.temp_hp,c.injuries),(70,5,0))

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='HP-RESOURCE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='HP-RESOURCE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='HP-RESOURCE-'+t._testMethodName,status='error'))
        def addSubTest(self,t,st,e):
            super().addSubTest(t,st,e)
            if e:self.rows.append(dict(id='HP-RESOURCE-'+t._testMethodName+str(st),status='fail'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(HPLossResources))
    paths=['tools/test_hp_loss_resources.py','engine/engine.py','engine/effects.py','engine/effects_ext.py','engine/life.py','engine/gm_state.py','input/ch07-combat.md','input/db/moves.csv','data/core-rules.json']
    report=dict(scope='Ordinary HP-loss resource allocation and compatibility boundaries; no full effect or semantic proof.',semantic_closure=False,results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/hp-loss-resource-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
