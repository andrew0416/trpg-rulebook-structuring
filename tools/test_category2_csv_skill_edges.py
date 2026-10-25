"""Explicit CSV skill-edge IDs share native arithmetic without losing source identity."""
from pathlib import Path
import sys,unittest
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import skill_modifiers as S
import trainer_capabilities as T
from ruleset import ExcludedRuleSelection,RuleSelection
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def actor(self,rows,choices,skills=None):
  ids=[f'C2CSV/input/db/edges.csv:R{n}:main' for n in rows]
  c=Combatant(self.rules,dict(id='trainer/csv-skills',name='tester',kind='trainer',level=20,
    stats=dict(hp=10,atk=5,**{'def':5},spa=5,spd=5,spe=5),
    skills=skills or {'육상':6,'곡예':6,'일반지식':5},edges=ids,
    edge_choices={f'C2CSV/input/db/edges.csv:R{n}:main':v for n,v in choices.items()}))
  engine=Engine(self.rules,73)
  engine.gm.add_combatant(c,reason='actual CSV skill-edge roll actor')
  return engine,c
 def test_category_pairs_and_scholar_use_real_roll_once_per_skill(self):
  e,c=self.actor([8,9,9,64],{8:'신체',9:[['육상','곡예'],['육상','생존']]})
  for skill in self.rules.skill_policy['skills']:
   with self.subTest(skill=skill):
    n=S.rank(self.rules,c,skill)[2]
    group=self.rules.skill_policy['skills'][skill]['category']
    expected=int(skill in ('acrobatics','athletics','combat','intimidate','stealth','survival'))+2*int(skill in ('athletics','acrobatics','survival'))+int(skill in self.rules.skill_policy['edges']['edge/학자']['skills'])
    out=e.skill_roll(c,skill,fixed=[1]*n)
    self.assertEqual(out.modifier,expected)
  self.assertEqual(c.spec['edges'][0],'C2CSV/input/db/edges.csv:R8:main')
 def test_virtuoso_changes_capability_rank_but_not_dice_and_rejects_repeated_choice(self):
  e,c=self.actor([10,10],{10:['육상','곡예']})
  self.assertEqual(S.effective_rank(self.rules,c,'육상'),8)
  self.assertEqual(len(e.skill_roll(c,'육상',fixed=[1]*6).faces),6)
  self.assertEqual(T.values(c)['land'],11)
  c.spec['edge_choices']['C2CSV/input/db/edges.csv:R10:main']=['육상','Athletics']
  with self.assertRaises(ValueError):S.effective_rank(self.rules,c,'육상')
 def test_native_skill_roll_reuses_common_composition_without_changing_rank(self):
  e,c=self.actor([8,9],{8:'신체',9:[['육상','곡예']]})
  before=deepcopy(c.spec)
  with patch.object(S.COMPOSITION,'derive',wraps=S.COMPOSITION.derive) as derive:
   result=e.skill_roll(c,'육상',mods=-3,fixed=[1]*6)
   self.assertTrue(derive.called)
  self.assertEqual((result.modifier,result.total,len(result.faces)),(0,6,6))
  projection=S.modifiers(self.rules,c,'육상',-3)['composition']
  self.assertEqual((projection['base'],projection['value']),(-3,0))
  self.assertEqual(len(projection['contributions']),2)
  self.assertFalse(projection['consumed'])
  self.assertEqual(c.spec,before)
 def test_common_composition_failure_rejects_before_rng_or_state_changes(self):
  e,c=self.actor([9],{9:[['육상','곡예']]})
  before=(deepcopy(c.spec),e.rng.getstate())
  with patch.object(S.COMPOSITION,'derive',side_effect=ValueError('common skill composition failed')):
   with self.assertRaisesRegex(ValueError,'common skill composition failed'):e.skill_roll(c,'육상')
  self.assertEqual((c.spec,e.rng.getstate()),before)
 def test_missing_prerequisites_and_pokemon_cannot_borrow_trainer_rule(self):
  for rows,choices in [([64],{}),([10],{10:['육상']}),([9],{9:[['육상','곡예']]})]:
   e,c=self.actor(rows,choices)
   if rows==[64]:c.spec['skills']['일반지식']=4
   elif rows==[10]:c.level=19
   else:c.kind='pokemon'
   before=(deepcopy(c.spec),e.rng.getstate())
   with self.assertRaises(ValueError):
    if rows==[10]:S.effective_rank(self.rules,c,'육상')
    else:e.skill_roll(c,'육상')
   self.assertEqual((c.spec,e.rng.getstate()),before)
 def test_csv_exclusion_is_checked_even_after_source_cache_warmed(self):
  e,c=self.actor([9],{9:[['육상','곡예']]});e.skill_roll(c,'육상',fixed=[1]*6)
  cid=c.spec['edges'][0];self.rules.ruleset.exclude_units.add(cid)
  original=self.rules.selection
  self.rules.selection=RuleSelection(self.rules.ruleset,list(original.units.values()))
  try:
   with self.assertRaises(ExcludedRuleSelection):e.skill_roll(c,'육상',fixed=[1]*6)
  finally:
   self.rules.ruleset.exclude_units.remove(cid)
   self.rules.selection=original
  self.assertEqual(e.skill_roll(c,'육상',fixed=[1]*6).modifier,2)
if __name__=='__main__':unittest.main()
