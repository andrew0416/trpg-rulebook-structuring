"""Mettle source acceptance: PTU 1.05 p171, damage ordering pp236-237 and injuries p250.
Intercept cases enter an already-resolved interception; movement/skill checks are separate obligations.
"""
import copy,hashlib,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import test_frequencies as _fixture_test_frequencies
from engine import Combatant,Engine
from synthetic_rule_fixture import register_synthetic
import frequency as FREQ
import world_entities as WORLD
class MettleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_frequencies.FrequencyTests.setUpClass();cls.rules=_fixture_test_frequencies.FrequencyTests.rules
        # Synthetic damage input isolates Mettle response from individual move semantics.
        register_synthetic(cls.rules,'audit/mettle-source',name='깡다구 원문 검사 공격')
        source=json.loads((ROOT/'data/mettle-source-review.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((ROOT/source['file']).read_bytes()).hexdigest()==source['sha256']
        assert hashlib.sha256((ROOT/source['excerpt_file']).read_bytes()).hexdigest()==source['excerpt_sha256']
    def fixture(self,attack=70,category='물리',answer=True,feat=True):
        r=self.rules;mid='audit/mettle-source'
        r.moves[mid]=dict(id=mid,name='깡다구 원문 검사 공격',type='노말',frequency='임의',range='근접, 1 목표',ac=2,damage_base=6,**{'class':category},effect='',mech_auto={})
        r.moves_mech[mid]=dict(name='검사 공격',coverage='full',header=dict(db=6,frequency=dict(kind='at_will')),effects=[])
        e=Engine(r,seed=1);e.rulings=copy.deepcopy(e.rulings);e.rulings.answers=[]
        a=Combatant(r,dict(name='foe',kind='pokemon',level=10,stats=dict(hp=30,atk=attack,spa=attack,**{'def':20,'spd':20,'spe':1}),types=[],abilities=[],moves=[mid]))
        b=Combatant(r,dict(name='defender',kind='trainer',level=10,stats=dict(hp=20,atk=20,spa=20,**{'def':20,'spd':20,'spe':1}),types=[],abilities=[],moves=[],feats=['깡다구'] if feat else []))
        e.everyone=e.gm.everyone=[a,b];e.register_abilities(a);e.register_abilities(b)
        e.d20=lambda:10
        if answer is not None:e.rulings.add_answer('mettle',answer)
        return e,a,b,mid
    def attack(self,e,a,b,mid):return e.use_move(a,b,mid,set_damage=True,free_action=True)
    def test_physical_damage_and_stage(self):
        e,a,b,m=self.fixture();hp=b.hp
        self.assertEqual(self.attack(e,a,b,m),32) # floor((15+70-20)/2)
        self.assertEqual(b.hp,hp-32);self.assertEqual(a.stages['atk'],-2);self.assertEqual(a.stages['spa'],0)
        self.assertEqual(b.injuries,0)
    def test_special_damage_and_stage(self):
        e,a,b,m=self.fixture(category='특수');self.assertEqual(self.attack(e,a,b,m),32)
        self.assertEqual((a.stages['atk'],a.stages['spa']),(0,-2))
    def test_threshold_equal(self):
        e,a,b,m=self.fixture(attack=50);self.assertEqual(b.base_max_hp,90)
        self.assertEqual(self.attack(e,a,b,m),22);self.assertEqual(a.stages['atk'],-2)
    def test_threshold_below(self):
        e,a,b,m=self.fixture(attack=49);self.assertEqual(self.attack(e,a,b,m),44)
        self.assertEqual(a.stages['atk'],0)
    def test_decline(self):
        e,a,b,m=self.fixture(answer=False);self.assertEqual(self.attack(e,a,b,m),65)
        self.assertEqual(a.stages['atk'],0);self.assertEqual(FREQ.state(b)['activations'],{})
    def test_no_answer_is_not_consent(self):
        e,a,b,m=self.fixture(answer=None);self.assertEqual(self.attack(e,a,b,m),65)
        self.assertEqual(a.stages['atk'],0);self.assertEqual(FREQ.state(b)['activations'],{})
    def test_no_feature(self):
        e,a,b,m=self.fixture(feat=False);self.assertEqual(self.attack(e,a,b,m),65)
        self.assertEqual(a.stages['atk'],0)
    def test_miss_does_not_activate(self):
        e,a,b,m=self.fixture();e.d20=lambda:1;hp=b.hp
        self.assertEqual(self.attack(e,a,b,m),0);self.assertEqual(b.hp,hp);self.assertEqual(a.stages['atk'],0)
    def test_damage_precedes_stat_loss(self):
        e,a,b,m=self.fixture();observed=[];original=type(e).take_damage;attacker_id=a.entity_id
        def take(actual_engine,c,amount):
            actual_attacker=WORLD.actor_index(actual_engine)[attacker_id]
            observed.append((amount,actual_attacker.stages['atk']))
            return original(actual_engine,c,amount)
        with patch.object(type(e),'take_damage',take):self.attack(e,a,b,m)
        self.assertEqual(observed,[(32,0)]);self.assertEqual(a.stages['atk'],-2)
    def test_free_action_and_no_ap(self):
        e,a,b,m=self.fixture();b.budget={'standard':0,'shift':0,'swift':0}
        self.attack(e,a,b,m);self.assertEqual(a.stages['atk'],-2)
        self.assertEqual(b.budget,{'standard':0,'shift':0,'swift':0});self.assertEqual(b.spec.get('ap_spent',0),0)
    def test_stage_floor(self):
        e,a,b,m=self.fixture();a.stages['atk']=-5
        e.resolve_attack_damage(a,b,e.r.move(m),set_damage=True,intercepted=True)
        self.assertEqual(a.stages['atk'],-6)
    def test_stage_immunity_keeps_resistance(self):
        e,a,b,m=self.fixture();a.stage_loss_immune={'atk'}
        self.assertEqual(self.attack(e,a,b,m),32);self.assertEqual(a.stages['atk'],0)
    def test_stat_override(self):
        e,a,b,m=self.fixture(category='특수')
        e.r.moves_mech[m]['effects']=[dict(type='damage_formula_override',attack_stat='atk')]
        self.assertEqual(self.attack(e,a,b,m),32);self.assertEqual((a.stages['atk'],a.stages['spa']),(-2,0))
    def test_scene_reset(self):
        e,a,b,m=self.fixture()
        FREQ.consume_activation(b,'feat/깡다구','장면x2');FREQ.consume_activation(b,'feat/깡다구','장면x2')
        e.end_scene([a,b]);e.rulings.add_answer('mettle',True)
        self.assertEqual(self.attack(e,a,b,m),32)
    def test_saved_usage_rejects_third(self):
        e,a,b,m=self.fixture()
        FREQ.consume_activation(b,'feat/깡다구','장면x2');FREQ.consume_activation(b,'feat/깡다구','장면x2')
        z=Combatant(e.r,json.loads(json.dumps(b.spec)))
        e=Engine(e.r,seed=1);e.everyone=e.gm.everyone=[a,z]
        e.register_abilities(a);e.register_abilities(z);e.d20=lambda:10
        self.assertEqual(self.attack(e,a,z,m),65);self.assertEqual(a.stages['atk'],0)
    def test_rewind_restores_damage_stage_and_use(self):
        e,a,b,m=self.fixture();e.gm.snapshot();self.attack(e,a,b,m);e.gm.restore()
        self.assertEqual((b.hp,a.stages['atk']),(90,0))
        self.assertTrue(FREQ.activation_allowed(b,'feat/깡다구','장면x2'))
        self.assertEqual(self.attack(e,a,b,m),32)
    def test_calculator_does_not_activate_or_consume(self):
        e,a,b,m=self.fixture();self.assertEqual(e.roll_damage(a,b,e.r.move(m),set_damage=True),65)
        self.assertEqual(a.stages['atk'],0);self.assertEqual(FREQ.state(b)['activations'],{})
    def test_multiple_hits_only_two_activations(self):
        e,a,b,m=self.fixture();damages=[]
        for i in range(3):
            b.hp=90;b.injuries=0;b.conditions.clear();a.stages['atk']=0
            damages.append(self.attack(e,a,b,m))
        self.assertEqual(damages,[32,32,65])
        self.assertEqual(FREQ.state(b)['activations']['feat/깡다구']['used'],2)
    def test_immunity_has_no_massive_trigger(self):
        e,a,b,m=self.fixture();e.type_multiplier=lambda *args:(0,'test immunity')
        self.assertEqual(self.attack(e,a,b,m),0);self.assertEqual(a.stages['atk'],0)
    def test_damage_uses_original_max_hp_despite_injuries(self):
        e,a,b,m=self.fixture(attack=49);b.injuries=3
        self.assertEqual(self.attack(e,a,b,m),44);self.assertEqual(a.stages['atk'],0)
    def test_declined_answer_string_is_not_true(self):
        e,a,b,m=self.fixture(answer='false');self.assertEqual(self.attack(e,a,b,m),65)
        self.assertEqual(a.stages['atk'],0)
    def test_feature_id_alias(self):
        e,a,b,m=self.fixture();b.spec['feats']=['feat/깡다구']
        self.assertEqual(self.attack(e,a,b,m),32)
    def test_critical_damage_is_not_rerolled(self):
        e,a,b,m=self.fixture();e.d20=lambda:20
        self.assertEqual(self.attack(e,a,b,m),40);self.assertEqual(a.stages['atk'],-2)
    def test_actual_damage_dice_are_rolled_once(self):
        e,a,b,m=self.fixture();rolls=[]
        def roll(expr,times=1):rolls.append((expr,times));return 15,[3,4]
        e.roll_expr=roll
        self.assertEqual(e.use_move(a,b,m,free_action=True),32);self.assertEqual(len(rolls),1)
    def test_response_can_prevent_fainting(self):
        e,a,b,m=self.fixture();b.hp=40
        self.assertEqual(self.attack(e,a,b,m),32);self.assertEqual(b.hp,8);self.assertFalse(b.fainted)
    def test_stat_loss_occurs_even_if_defender_faints(self):
        e,a,b,m=self.fixture();b.hp=20
        self.assertEqual(self.attack(e,a,b,m),32);self.assertTrue(b.fainted);self.assertEqual(a.stages['atk'],-2)
    def test_temp_hp_preserved_until_selected_damage_applied(self):
        e,a,b,m=self.fixture();__import__('temporary_hp').grant(e,b,10)
        self.assertEqual(self.attack(e,a,b,m),32);self.assertEqual(b.hp,68);self.assertEqual(b.temp_hp,0)
    def test_status_and_hp_loss_do_not_create_damage_response(self):
        e,a,b,m=self.fixture();e.lose_hp(b,50)
        self.assertEqual(a.stages['atk'],0);self.assertEqual(FREQ.state(b)['activations'],{})
    def test_gm_before_damage_hook_runs_once_after_response(self):
        e,a,b,m=self.fixture();seen=[]
        def hook(value,context):seen.append(value);return value+3
        e.rulings.add_hook('before_damage',hook)
        self.assertEqual(self.attack(e,a,b,m),35);self.assertEqual(seen,[32])
    def test_unrelated_actor_unchanged(self):
        e,a,b,m=self.fixture();c=Combatant(e.r,dict(b.spec,name='bystander'));before=dict(c.stages)
        self.attack(e,a,b,m);self.assertEqual(c.hp,90);self.assertEqual(c.stages,before)

def case(massive,intercepted,uses):
    def test(self):
        e,a,b,m=self.fixture(attack=70 if massive else 30)
        for _ in range(uses):FREQ.consume_activation(b,'feat/깡다구','장면x2')
        result=e.resolve_attack_damage(a,b,e.r.move(m),set_damage=True,intercepted=intercepted)
        active=(massive or intercepted) and uses<2
        self.assertEqual(result,(32 if massive else 12) if active else (65 if massive else 25))
        self.assertEqual(a.stages['atk'],-2 if active else 0)
        self.assertEqual(FREQ.state(b)['activations'].get('feat/깡다구',{}).get('used',0),uses+int(active))
    return test
for massive in [False,True]:
    for intercepted in [False,True]:
        for uses in [0,1,2]:
            setattr(MettleTests,f'test_truth_{int(massive)}_{int(intercepted)}_{uses}',case(massive,intercepted,uses))
def resistance(mult,expected):
    def test(self):
        e,a,b,m=self.fixture();e.type_multiplier=lambda *args:(mult,'test type matchup')
        result=e.resolve_attack_damage(a,b,e.r.move(m),set_damage=True,intercepted=True)
        self.assertEqual(result,expected)
    return test
for i,(mult,expected) in enumerate([(3,130),(2,97),(1.5,65),(1,32),(0.5,16),(0.25,8)]):
    setattr(MettleTests,f'test_resistance_step_{i}',resistance(mult,expected))
if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='METTLE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='METTLE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='METTLE-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(MettleTests))
    paths=[p for folder,pattern in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pattern)]
    paths += [ROOT/'tools/synthetic_rule_fixture.py',Path(__file__),ROOT/'tools/test_frequencies.py',ROOT/'input/ch04-trainer-classes.md',ROOT/'input/ch07-combat.md']
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Mettle attack damage response, explicit choice, actual attack stat, scene frequency and lifecycle. Interception maneuver eligibility/movement and acquisition prerequisites remain separate.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    result['logical_witnesses']={
        f'METTLE-test_truth_{int(m)}_{int(i)}_{u}':dict(model_id='mettle-activation-boolean',inputs={'M':m,'I':i,'L':u<2},concrete_usage=u)
        for m in [False,True] for i in [False,True] for u in [0,1,2]}
    (ROOT/'output/mettle-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
