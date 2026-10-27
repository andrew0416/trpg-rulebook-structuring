"""Independent exact native-type certification boundaries, not a Python tamper sandbox.
Only this test file is authored here. Runtime modules are read-only inputs.
"""
import copy,hashlib,json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import heavy_injury_adapter as H

class NativeTypeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(str(ROOT),ruleset='core');cls.other_rules=Rules(str(ROOT),ruleset='core')
 def pair(self,engine_type=Engine,attacker_type=Combatant,target_type=Combatant,rules=None):
  rules=rules or self.rules;e=engine_type(rules);e.rulings=copy.deepcopy(e.rulings)
  def actor(cls,name):return cls(rules,dict(name=name,kind='trainer',level=10,stats={x:30 for x in ('hp','atk','def','spa','spd','spe')},types=[],abilities=[],moves=['struggle']))
  a=actor(attacker_type,'attacker');b=actor(target_type,'target');a.hp=b.hp=50;b.injuries=5
  e.everyone=e.gm.everyone=[a,b];e.d20=lambda:10;e.start_round([a,b]);e.start_of_turn(a)
  return e,a,b
 def diagnostic(self,e,a,b):return H.certify_native_context(e,a,b,self.rules.move('struggle'),{},ordinary_single=True)
 def held(self,e,a,b):
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  packet=e._heavy_events[e._heavy_pending]
  self.assertEqual(packet['status'],'pending');self.assertEqual(packet['context'],'unknown')
  self.assertNotIn('heavy_consequence',packet);self.assertEqual(b.hp,39)
  return packet
 def test_exact_native_types_still_apply_local_result(self):
  e,a,b=self.pair();self.assertEqual(e._heavy_native_types,(Engine,Rules,Combatant))
  self.assertFalse(self.diagnostic(e,a,b).failures);e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(b.hp,34);self.assertIsNone(e._heavy_pending)
 def test_same_name_engine_subclass_reaction_counterexample_held(self):
  class SameName(Engine):
   def take_damage(self,c,amount):
    result=super().take_damage(c,amount)
    if c.hp>35:self.extra_reactions+=1
    return result
  SameName.__name__='Engine';e,a,b=self.pair(engine_type=SameName);e.extra_reactions=0
  self.assertIn('engine_subclass_not_reviewed',self.diagnostic(e,a,b).failures)
  self.held(e,a,b);self.assertEqual(e.extra_reactions,1)
  # Original subclass damage remains supported; unproved additional loss does not run.
 def test_actor_hp_property_counterexample_held(self):
  class ThresholdActor(Combatant):
   @property
   def hp(self):return self.__dict__['hp']
   @hp.setter
   def hp(self,value):self.__dict__['hp']=0 if 0<value<35 else value
  e,a,b=self.pair(target_type=ThresholdActor)
  self.assertIn('target:actor_subclass_not_reviewed',self.diagnostic(e,a,b).failures)
  self.held(e,a,b);self.assertNotIn('기절',b.conditions)
 def test_same_name_combatant_subclass_is_not_canonical(self):
  Alias=type('Combatant',(Combatant,),{})
  for kwargs,reason in [(dict(attacker_type=Alias),'attacker:actor_subclass_not_reviewed'),(dict(target_type=Alias),'target:actor_subclass_not_reviewed')]:
   with self.subTest(reason=reason):
    e,a,b=self.pair(**kwargs);self.assertIn(reason,self.diagnostic(e,a,b).failures);self.held(e,a,b)
 def test_same_name_rules_subclass_is_unknown(self):
  Alias=type('Rules',(Rules,),{'move_mech':lambda self,*args,**kwargs:Rules.move_mech(self,*args,**kwargs)})
  rules=Alias(str(ROOT),ruleset='core');e,a,b=self.pair(rules=rules)
  self.assertIn('rules_subclass_not_reviewed',self.diagnostic(e,a,b).failures);self.held(e,a,b)
 def test_separate_equal_rules_instance_is_not_same_context(self):
  for who in ('attacker','target'):
   with self.subTest(who=who):
    e,a,b=self.pair();actor=a if who=='attacker' else b;actor.r=self.other_rules
    self.assertIn(who+':different_rules_context',self.diagnostic(e,a,b).failures)
    # Unlike an uncertified subclass in a valid world, this is not an admitted actor.
    def observed():
     return copy.deepcopy((a.hp,b.hp,a.temp_hp,b.temp_hp,a.budget,a.spec,b.spec,
         a.conditions,b.conditions,a.custom_conditions,b.custom_conditions,a.move_uses,b.move_uses,
         e.rng.getstate(),e.elapsed_seconds,e.round_no,a._action_history,
         e._heavy_events,e._heavy_pending,e._heavy_native_receipts,
         getattr(e,'_move_completions',{}),getattr(e,'_effect_dispatch_receipts',{})))
    before=observed()
    with self.assertRaisesRegex(ValueError,'actual registered actor'):
     e.use_move(a,b,'struggle',set_damage=True)
    self.assertEqual(observed(),before)
    self.assertEqual((a.hp,b.hp),(50,50));self.assertIsNone(e._heavy_pending)
 def test_instance_formula_and_log_wrappers_are_not_certified(self):
  for name in ('formula','log'):
   with self.subTest(method=name):
    e,a,b=self.pair();original=getattr(e,name);setattr(e,name,lambda *args,_fn=original,**kwargs:_fn(*args,**kwargs))
    self.assertIn('overridden_engine_method:'+name,self.diagnostic(e,a,b).failures);self.held(e,a,b)
 def test_instance_take_damage_wrapper_remains_unknown(self):
  e,a,b=self.pair();original=e.take_damage;e.take_damage=lambda *args:original(*args)
  self.assertIn('overridden_engine_method:take_damage',self.diagnostic(e,a,b).failures);self.held(e,a,b)
 def test_rules_instance_method_override_remains_unknown(self):
  rules=Rules(str(ROOT),ruleset='core');original=rules.move_mech;rules.move_mech=lambda *args:original(*args)
  e,a,b=self.pair(rules=rules);self.assertIn('overridden_rules_method:move_mech',self.diagnostic(e,a,b).failures);self.held(e,a,b)
 def test_missing_binding_does_not_guess_from_names(self):
  e,a,b=self.pair();del e._heavy_native_types
  self.assertIn('native_type_binding_missing',self.diagnostic(e,a,b).failures);self.held(e,a,b)
 def test_main_module_lexical_classes_keep_native_identity(self):
  # Load unchanged declarations as __main__, omitting only CLI file-writing branch.
  # This checks module identity, not the scenario CLI control flow or its output.
  script="""import ast,pathlib
root=pathlib.Path(ROOT_LITERAL)
p=root/'engine/engine.py';tree=ast.parse(p.read_text(encoding='utf-8'))
tree.body=[n for n in tree.body if not (isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='__name__')]
ns={'__name__':'__main__','__file__':str(p)};exec(compile(tree,str(p),'exec'),ns)
E,R,C=ns['Engine'],ns['Rules'],ns['Combatant'];r=R(str(root),ruleset='core');e=E(r)
def actor(name):return C(r,dict(name=name,kind='trainer',level=10,stats={x:30 for x in ('hp','atk','def','spa','spd','spe')},types=[],abilities=[],moves=['struggle']))
a,b=actor('a'),actor('b');a.hp=b.hp=50;b.injuries=5;e.everyone=e.gm.everyone=[a,b];e.d20=lambda:10;e.start_round([a,b]);e.start_of_turn(a)
assert E.__module__=='__main__';assert e._heavy_native_types==(E,R,C)
assert not ns['HEAVY'].certify_native_context(e,a,b,r.move('struggle'),{},ordinary_single=True).failures
e.use_move(a,b,'struggle',set_damage=True);assert b.hp==34
""".replace('ROOT_LITERAL',repr(str(ROOT)))
  p=subprocess.run([sys.executable,'-B','-I','-X','utf8','-c',script],capture_output=True,text=True,encoding='utf-8')
  self.assertEqual(p.returncode,0,p.stderr)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id=t.id(),status='pass'))
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id=t.id(),status='fail'))
  def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id=t.id(),status='error'))
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeTypeTests))
 paths=['tests/test_heavy_native_types.py','engine/engine.py','engine/heavy_injury_adapter.py','engine/heavy_injury_kernel.py','engine/effects.py','engine/effects_ext.py','engine/gm_state.py']
 report=dict(scope='Exact native-class certification boundaries only; no arbitrary Python tamper proof.',semantic_closure=False,tests_run=result.testsRun,results=result.rows,input_hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in paths})
 (ROOT/'output/heavy-native-type-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
