from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import composition_derive as C
import effect_lifetimes as L
import combat_timing as T

def row(i,value,**kw):return dict(id=i,source='source/'+i,value=value,**kw)
def step(law,*ids):return {'law':law,'contributors':list(ids)}

class CompositionTests(unittest.TestCase):
 def test_additive_percent_default_and_explicit_product_differ(self):
  rows=[row('a',{'numerator':1,'denominator':5}),row('b',{'numerator':3,'denominator':10})]
  self.assertEqual(C.derive(11,rows,[step('percent_add','a','b')])['value'],16)
  self.assertEqual(C.derive(100,rows,[step('percent_product','a','b')])['value'],156)
 def test_ordered_replacement_is_not_addition(self):
  rows=[row('a',5),row('b',20,priority=1)]
  first=C.derive(10,rows,[step('add','a'),step('replace','b')])
  second=C.derive(10,rows,[step('replace','b'),step('add','a')])
  self.assertEqual((first['value'],second['value']),(20,25));self.assertEqual(second['base'],10)
 def test_nonstacking_priority_and_conflict(self):
  rows=[row('a',3,priority=1),row('b',5,priority=2)]
  self.assertEqual(C.derive(10,rows,[step('nonstacking','a','b')])['value'],15)
  rows[0]['priority']=2
  with self.assertRaises(C.CompositionPending):C.derive(10,rows,[step('nonstacking','a','b')])
 def test_conditions_and_exact_rounding(self):
  rows=[row('a',100,active=False),row('b',{'numerator':-3,'denominator':2})]
  self.assertEqual(C.derive(0,rows,[step('add','a','b')])['value'],-2)
  self.assertEqual(C.derive(0,rows,[step('add','a','b')],rounding='trunc')['value'],-1)
  rows[0]['active']=None
  with self.assertRaises(C.CompositionPending):C.derive(0,rows,[step('add','a','b')])
 def test_bad_or_repeated_contributions_reject(self):
  for rows,steps in [([row('a',True)],[step('add','a')]),([row('a',1)],[step('add','a'),step('add','a')]),([row('a',1)],[])]:
   with self.assertRaises(ValueError):C.derive(0,rows,steps)
 def test_maximum_minimum_and_detached_preview(self):
  rows=[row('a',20),row('b',7)];steps=[step('maximum','a'),step('minimum','b')];before=deepcopy(rows)
  out=C.derive(10,rows,steps);self.assertEqual(out['value'],7);self.assertFalse(out['consumed'])
  out['contributions'][0]['value']=100;self.assertEqual(rows,before)
 def test_native_timed_consumer_preserves_sources_without_consumption(self):
  actor=SimpleNamespace(r=SimpleNamespace(_selected_rule=lambda x:x,selection=SimpleNamespace(units={'rule/a':{},'rule/b':{}})),custom_conditions={T.KEY:[
   {'effect_contract':True,'source':'rule/a','accuracy_modifier':2},
   {'effect_contract':True,'source':'rule/b','accuracy_modifier':-1}]})
  before=deepcopy(actor.custom_conditions);out=L.numeric_derivation(actor,'accuracy_modifier')
  self.assertEqual(L.numeric(actor,'accuracy_modifier'),1)
  self.assertEqual([r['source'] for r in out['contributions']],['rule/a','rule/b'])
  self.assertEqual(actor.custom_conditions,before)
  actor.r._selected_rule=lambda x:'changed'
  with self.assertRaises(ValueError):L.numeric(actor,'accuracy_modifier')
if __name__=='__main__':unittest.main()
