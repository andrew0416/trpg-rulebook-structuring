"""Independent weather/source regressions; no runtime-generated expected values."""
import hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import test_frequencies as _fixture_test_frequencies
import effects as FX
import effects_ext as EXT
import turn as TURN
from ruleset import UnresolvedRuleSelection

WEATHERS=[None,'sunny','rain','sandstorm','hail']
class WeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_frequencies.FrequencyTests.setUpClass()
        cls.review=json.loads((ROOT/'data/weather-source-review.json').read_text(encoding='utf-8'))
        book=_fixture_test_frequencies.FrequencyTests.source
        for row in cls.review['sources']:
            value=book[row['sheet']]['cells'][row['cell']]
            assert hashlib.sha256(value.encode()).hexdigest()==row['sha256'],row
    def fixture(self,weather=None):
        e,a,b,_=_fixture_test_frequencies.FrequencyTests().fixture()
        e.gm.set_weather(weather,rounds=None,reason='actual observed source-regression weather')
        return e,a,b
    def electro_fixture(self,weather=None):
        from grid import Grid
        e,a,b=self.fixture(weather);e.grid=Grid(12,8)
        a.pos=(1,2);b.pos=(4,2);a.side='party';b.side='wild'
        for actor in (a,b):e.gm.set_footprint(actor,[(0,0)],reason='observed Electro Shot regression body')
        e.gm.set_move(a,'move/일렉트로빔',True,reason='actual learned source Move')
        e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        return e,a,b
    def test_weather_or_does_not_accept_substring(self):
        e,a,b=self.fixture()
        with self.assertRaises(ValueError):
            e.gm.set_weather('not-rain',reason='invalid weather cannot become rain by substring')
        self.assertFalse(FX.cond_ok(e,{'if_weather':'rain|hail'},{'hit':True})[0])
    def test_replacement_does_not_suppress_unrelated_target_heal(self):
        e,a,b=self.fixture('sunny');a.hp=b.hp=1
        effects=[{'type':'heal','target':'self','fraction_of_max':[1,2]},
                 {'type':'heal','target':'target','fraction_of_max':[1,2]},
                 {'type':'heal','target':'self','fraction_of_max':[2,3],'if_weather':'sunny','replaces':True}]
        FX.run_effects(e,a,b,effects,{'attacker':a,'target':b,'hit':True},'audit')
        self.assertEqual(a.hp,1+a.max_hp*2//3)
        self.assertEqual(b.hp,1+b.max_hp//2)
    def test_full_action_rejects_atomically_when_shift_unavailable(self):
        e,a,b=self.electro_fixture();a.budget={'standard':1,'shift':0,'swift':1}
        before=dict(a.budget);e.use_move_on(a,b,'move/일렉트로빔',e.everyone)
        self.assertEqual(a.budget,before)
        self.assertNotIn('move/일렉트로빔',a.move_uses)
    def test_sunny_veil_weather_component_tracks_changes_without_reregistering(self):
        e,a,b=self.fixture()
        # C462 and C529 both explicitly state this component. Register the component
        # directly: name-keyed ability registration cannot establish either identity.
        for cell in ('C462','C529'):
            self.assertIn('쾌청한 동안 피해감소 5',_fixture_test_frequencies.FrequencyTests.source['특성 데이터']['cells'][cell])
        FX.apply_passives(e,b,[{'type':'damage_reduction','value':5,'if_weather':'sunny'}])
        m=e.r.move('move/하이드로스팀')
        for w,dr in [(None,0),('sunny',5),('rain',0),('sunny',5),(None,0)]:
            e.gm.set_weather(w,rounds=None,reason='actual changed weather for retained passive')
            self.assertEqual(EXT.defense_hook(e,a,b,m,{},'spd')[1],dr)
    def test_sunny_veil_ambiguous_registration_stays_unresolved(self):
        e,a,b=self.fixture()
        self.assertEqual(set(e.r.selection.names['햇살베일']),{'ability/햇살베일','ability/햇살베일-2'})
        before=(list(b.modifiers),b.evasion_mod,b.damage_reduction,list(b.ability_triggers))
        with self.assertRaises(UnresolvedRuleSelection):
            e.gm.set_ability(b,'햇살베일',True,reason='actual ambiguous Ability acquisition request')
        self.assertEqual((b.modifiers,b.evasion_mod,b.damage_reduction,b.ability_triggers),before)

    def test_solar_beam_weather_override_preserves_stab(self):
        e,a,b=self.fixture('hail');a.types=['풀']
        self.assertEqual(e.damage_base(a,e.r.move('move/솔라빔')),8)

def add(name,fn):setattr(WeatherTests,'test_'+name,fn)
for name,row in [('달빛',171),('광합성',375),('아침햇살',531),('모래모으기',404)]:
    for wi,w in enumerate(WEATHERS):
        favored='sandstorm' if name=='모래모으기' else 'sunny'
        num,den=(1,2) if w is None else ((2,3) if w==favored else (1,4))
        def case(self,name=name,w=w,num=num,den=den):
            e,a,b=self.fixture(w);a.hp=1
            e.use_move(a,a,'move/'+name,free_action=True)
            self.assertEqual(a.hp,1+a.max_hp*num//den)
        add('healing_'+str(row)+'_'+str(wi),case)
for wi,w in enumerate(WEATHERS):
    def blizzard(self,w=w):
        e,a,b=self.fixture(w);e.d20=lambda:2
        self.assertEqual(e.accuracy_check(a,b,e.r.move('move/눈보라'))[0],w=='hail')
    add('blizzard_'+str(wi),blizzard)
    def solar_db(self,w=w):
        e,a,b=self.fixture(w)
        self.assertEqual(e.damage_base(a,e.r.move('move/솔라빔')),6 if w in ('rain','sandstorm','hail') else 12)
    add('solar_db_'+str(wi),solar_db)
    def blade(self,w=w):
        e,a,b=self.fixture(w);m=e.r.move('move/솔라블레이드')
        result=EXT.multiplier_hook(e,a,m,e.r.move_mech(m['id'])[0],{'attacker':a,'target':b,'hit':True})
        self.assertEqual(result,0.5 if w in ('rain','sandstorm','hail') else 1)
    add('blade_multiplier_'+str(wi),blade)
    def hydro(self,w=w):
        e,a,b=self.fixture(w);m=e.r.move('move/하이드로스팀')
        e.gm.set_weather(None,reason='clear actual weather for baseline');base=e.roll_damage(a,b,m,set_damage=True)
        e.gm.set_weather(w,rounds=None,reason='actual comparison weather');actual=e.roll_damage(a,b,m,set_damage=True)
        self.assertEqual(actual,base+(10 if w=='sunny' else 5 if w=='rain' else 0))
    add('hydro_damage_'+str(wi),hydro)
    def electro(self,w=w):
        e,a,b=self.electro_fixture(w);a.budget={'standard':1,'shift':1,'swift':1};e.d20=lambda:1
        e.use_move_on(a,b,'move/일렉트로빔',e.everyone)
        self.assertEqual(a.budget,{'standard':0,'shift':1 if w=='rain' else 0,'swift':1})
    add('electro_action_'+str(wi),electro)
    def desert(self,w=w):
        e,a,b=self.fixture(w);e.gm.set_ability(b,'사막날씨 [Playtest]',True,reason='actual selected weather Ability')
        m=dict(e.r.move('move/하이드로스팀'),type='불꽃')
        ctx={'attacker':a,'target':b,'hit':True,'move':m}
        self.assertEqual(FX.passive_damage_mods(e,a,b,m,ctx)[2],1 if w=='sunny' else 0)
    add('desert_fire_resistance_'+str(wi),desert)
for name in ['솔라빔','솔라블레이드']:
    def sunny_setup(self,name=name):
        e,a,b=self.fixture('sunny');e.d20=lambda:20
        e.use_move(a,b,'move/'+name,free_action=True)
        self.assertIsNone(a.setup_move);self.assertEqual(a.move_uses.get('move/'+name),1)
        self.assertEqual(a.stages['atk'],0)
    add('sunny_skip_'+name,sunny_setup)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='WEATHER-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='WEATHER-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='WEATHER-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(WeatherTests))
    paths=[p for folder,pat in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pat)]
    paths += [Path(__file__),ROOT/'tools/test_frequencies.py',ROOT/'tools/synthetic_rule_fixture.py',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Weather-dependent healing, accuracy, damage, setup and action costs; specified ability components only.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/weather-source-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
