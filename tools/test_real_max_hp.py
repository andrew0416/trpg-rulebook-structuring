"""Source ch07:700: actual max HP is the fraction base; injuries only cap healing."""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import effects as FX
import effects_ext as EXT

class RealMaxHPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def fixture(self,injuries=3,hp=10,hp_stat=23):
        e=Engine(self.rules);c=Combatant(self.rules,dict(name='HP basis',kind='pokemon',level=1,stats={'hp':hp_stat,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[],evolutions_remaining=0))
        c.injuries=injuries;c.hp=hp;e.everyone=e.gm.everyone=[c]
        return e,c,dict(attacker=c,target=c,who=c,engine=e,hit=True,healing_source_kind='move')
    def test_fractional_healing_uses_real_max_then_injury_cap(self):
        for hp_stat,real in [(23,80),(24,83)]:
            for injuries in [0,1,3,7]:
                for num,den in [(1,2),(1,3),(1,4),(2,3)]:
                    with self.subTest(real=real,injuries=injuries,fraction=(num,den)):
                        e,c,ctx=self.fixture(injuries=injuries,hp=1,hp_stat=hp_stat)
                        self.assertEqual(c.base_max_hp,real)
                        cap=c.max_hp
                        FX.h_heal(e,c,c,{'fraction_of_max':[num,den]},ctx)
                        self.assertEqual(c.hp,min(cap,1+real*num//den))
    def test_healing_at_or_above_recovery_ceiling_never_erases_hp(self):
        for hp in [54,56,65]:
            e,c,ctx=self.fixture(hp=hp);FX.h_heal(e,c,c,{'fraction_of_max':[1,2]},ctx)
            self.assertEqual(c.hp,max(hp,56))
    def test_expression_fractions_and_lost_percent_ignore_injury_ceiling(self):
        e,c,ctx=self.fixture(hp=35)
        for expr,value in [('max_hp/2',40),('max_hp/3',26),('max_hp/4',20),('max_hp*3/4',60),('lost_hp_percent',56)]:
            with self.subTest(expr=expr):self.assertEqual(FX._amount(expr,c,e,ctx),value)
    def test_current_hp_expression_remains_based_on_current_hp(self):
        e,c,ctx=self.fixture(hp=35);self.assertEqual(FX._amount('current_hp/2',c,e,ctx),17)
    def test_conditional_thresholds_use_actual_hp_without_temporary_hp(self):
        for hp,above,below in [(39,False,True),(40,False,True),(41,True,False)]:
            e,c,ctx=self.fixture(hp=hp);e.gm.set_temp_hp(c,100,reason="observed temporary HP",duration_seconds=300)
            self.assertEqual(FX.KNOWN_IF['hp > half'](ctx),above)
            self.assertEqual(FX.KNOWN_IF['hp <= half'](ctx),below)
        e,c,ctx=self.fixture(hp=25);self.assertTrue(FX.KNOWN_IF['hp <= 1/3'](ctx))
    def test_extended_conditions_share_actual_half_boundary(self):
        e,c,ctx=self.fixture(hp=35)
        self.assertTrue(EXT._eval_cond(e,c,c,'user current HP <= half',ctx))
        self.assertFalse(EXT._eval_cond(e,c,c,'target HP above 50%',ctx))
        self.assertTrue(EXT._eval_cond(e,c,c,'target HP below half',ctx))
    def test_delayed_healing_uses_actual_max_when_it_resolves(self):
        e,c,ctx=self.fixture();e.delayed=[dict(who=c,kind='heal',turns=1,effect={'fraction_of_max':[1,2]},src='test',healing_source_kind='move')]
        EXT.end_of_turn(e,c);self.assertEqual(c.hp,50);self.assertEqual(e.delayed,[])
    def test_legacy_heal_path_uses_actual_max(self):
        e,c,ctx=self.fixture();e.apply_effect(c,c,dict(type='heal',fraction_of_max=[1,2]),None,True,0,'test')
        self.assertEqual(c.hp,50)
    def test_generic_hp_loss_uses_actual_maximum(self):
        e,c,ctx=self.fixture(hp=70);FX.h_hp_loss(e,c,c,dict(value='max_hp/4'),ctx)
        self.assertEqual(c.hp,50)
    def test_legacy_hp_loss_uses_actual_maximum(self):
        e,c,ctx=self.fixture(hp=70);e.apply_effect(c,c,dict(type='hp_loss',value='max_hp/4'),None,True,0,'test')
        self.assertEqual(c.hp,50)
    def test_capture_hp_boxes_do_not_shift_with_less_than_five_injuries(self):
        for hp,expected_boxes in [(20,2),(21,1),(40,1),(41,0)]:
            for injuries in [0,1,3,4]:
                e,c,ctx=self.fixture(injuries=injuries,hp=hp)
                self.assertEqual(e.capture_rate(c),(10-2*expected_boxes,expected_boxes))
    def test_damage_cap_ceil_uses_real_max_and_preserves_rounding_override(self):
        e,c,ctx=self.fixture(hp_stat=24);c.damage_cap={'value':'max_hp/2','round':'up'}
        self.assertEqual(c.base_max_hp,83)
        self.assertEqual(EXT.cap_damage(e,c,100),42)
        self.assertEqual(EXT.cap_damage(e,c,20),20)
    def test_generic_half_hp_form_trigger_ignores_injury_ceiling(self):
        e,c,ctx=self.fixture(hp=35);c.form='before';c.form_rule={'trigger':'hp < half','forms':['before','after']}
        EXT.after_damage(e,c);self.assertEqual(c.form,'after')
    def test_self_negative_half_hp_uses_real_max_for_even_base(self):
        e,c,ctx=self.fixture(injuries=0,hp=20)
        c.injuries=2;FX.h_self_hp_set(e,c,c,{'self_hp':'-50% max'},ctx)
        self.assertEqual(c.hp,-40)
    def test_passive_third_hp_threshold_uses_real_max(self):
        e,c,ctx=self.fixture(hp=25);c.modifiers=[{'type':'damage_roll_mod','value':2,'if_hp_below_third':5}]
        self.assertEqual(FX.passive_damage_mods(e,c,c,{'type':'노말','class':'물리'},ctx)[1],5)

    def test_capture_five_injury_boxes_remain_separate(self):
        e,c,ctx=self.fixture(injuries=5,hp=35);self.assertEqual(e.capture_rate(c),(4,3))


    def test_unpreventable_self_setting_bypasses_cap_but_keeps_life_transitions(self):
        # Saved moves.csv Explosion/Self-Destruct explicitly prohibit prevention.
        e,c,ctx=self.fixture(injuries=2,hp=20)
        c.damage_cap={'value':'max_hp/2','round':'up'};e.gm.set_temp_hp(c,100,reason="observed temporary HP",duration_seconds=300)
        FX.h_self_hp_set(e,c,c,{'self_hp':'-50% max','unpreventable':True},ctx)
        self.assertEqual(c.hp,-40)
        self.assertEqual(c.injuries,4)  # Crosses0 and-40; no Massive Damage injury.
        self.assertTrue(c.fainted);self.assertFalse(c.dead)
        self.assertEqual(c.temp_hp,100)
    def test_ordinary_hp_loss_still_obeys_cap(self):
        e,c,ctx=self.fixture(injuries=2,hp=20);c.damage_cap={'value':'max_hp/2','round':'up'}
        e.lose_hp(c,60)
        self.assertEqual(c.hp,-20)
    def test_self_setting_without_explicit_true_does_not_bypass_cap(self):
        for flag in [None,False,'true',1]:
            with self.subTest(flag=flag):
                e,c,ctx=self.fixture(injuries=2,hp=20);c.damage_cap={'value':'max_hp/2','round':'up'}
                effect={'self_hp':'-50% max'}
                if flag is not None:effect['unpreventable']=flag
                FX.h_self_hp_set(e,c,c,effect,ctx)
                self.assertEqual(c.hp,-20)
    def test_unpreventable_zero_setting_uses_same_transition(self):
        e,c,ctx=self.fixture(injuries=0,hp=70);c.damage_cap={'value':'max_hp/2','round':'up'}
        FX.h_self_hp_set(e,c,c,{'self_hp':0,'unpreventable':True},ctx)
        self.assertEqual(c.hp,0);self.assertTrue(c.fainted)
        self.assertEqual(c.injuries,2)
    def test_actual_revival_herb_uses_real_half_then_healing_ceiling(self):
        for hp_stat,injuries,expected in [(23,3,40),(24,3,41),(24,7,24)]:
            with self.subTest(hp_stat=hp_stat,injuries=injuries):
                e,c,ctx=self.fixture(injuries=injuries,hp=-1,hp_stat=hp_stat)
                user=Combatant(e.r,dict(name='Medic',kind='trainer',level=1,stats={'hp':5,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[],items={'부활초':1}))
                e.everyone=e.gm.everyone=[user,c];e.check_fainted(c)
                e.use_item(user,'부활초',c)
                self.assertEqual(c.hp,expected);self.assertFalse(c.fainted)
                self.assertEqual(user.spec['items']['부활초'],0)
    def test_actual_fixed_revive_remains_twenty_hp(self):
        e,c,ctx=self.fixture(hp=-1,hp_stat=24)
        user=Combatant(e.r,dict(name='Medic',kind='trainer',level=1,stats={'hp':5,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[],items={'기력의조각':1}))
        e.everyone=e.gm.everyone=[user,c];e.check_fainted(c)
        e.use_item(user,'기력의조각',c)
        self.assertEqual(c.hp,20);self.assertFalse(c.fainted)
        self.assertEqual(user.spec['items']['기력의조각'],0)
    def test_actual_revival_herb_does_not_resurrect_dead_target(self):
        e,c,ctx=self.fixture(hp=-200)
        user=Combatant(e.r,dict(name='Medic',kind='trainer',level=1,stats={'hp':5,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},types=['노말'],moves=[],items={'부활초':1}))
        e.everyone=e.gm.everyone=[user,c];e.check_fainted(c)
        e.use_item(user,'부활초',c)
        self.assertEqual(c.hp,-200);self.assertTrue(c.dead);self.assertTrue(c.fainted)

    def test_generic_unpreventable_loss_bypasses_cap(self):
        # moves.csv Curse explicitly forbids prevention of its one-third HP cost.
        e,c,ctx=self.fixture(injuries=0,hp=70)
        c.damage_cap={'value':'max_hp/4'}
        FX.h_hp_loss(e,c,c,{'value':'max_hp/3','target':'self','unpreventable':True},ctx)
        self.assertEqual(c.hp,44)
    def test_generic_ordinary_loss_preserves_cap(self):
        e,c,ctx=self.fixture(injuries=0,hp=70)
        c.damage_cap={'value':'max_hp/4'}
        FX.h_hp_loss(e,c,c,{'value':'max_hp/3','target':'self'},ctx)
        self.assertEqual(c.hp,50)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='REAL-MAX-HP-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='REAL-MAX-HP-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='REAL-MAX-HP-'+t._testMethodName,status='error'))
        def addSubTest(self,t,st,e):
            super().addSubTest(t,st,e)
            if e:self.rows.append(dict(id='REAL-MAX-HP-'+t._testMethodName+str(st),status='fail'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(RealMaxHPTests))
    paths=['tools/test_real_max_hp.py','engine/engine.py','engine/effects.py','engine/effects_ext.py','engine/life.py','engine/items.py','input/ch07-combat.md','input/ch09-equipment.md','input/db/moves.csv','data/items-mech.json','data/items-llm.json','data/core-rules.json']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Common real-max denominator, injury healing cap and selected entry points only.',whole_rule_certified=False,results=result.rows,input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/real-max-hp-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
