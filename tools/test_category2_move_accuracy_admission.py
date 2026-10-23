"""Native absent-AC admission, numerical checks, exceptions and roll resources.

Conditional override fixtures exercise the contract, not new source clauses.
"""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest,csv,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_team_blessings as _fixture_test_category2_team_blessings
import blessing_effects as B,move_accuracy as A,ap_roll_bonus as AP,items as I
import combat_precision_features as CPF

# Blessing creation gates and if_weather conditions read the sourced weather registry
# (effects.weather_matches -> weather_state.effective_weathers with the actor), so fixtures
# place hail through engine.gm.set_weather(..., rounds=None) instead of engine.weather.
class MoveAccuracyAdmissionTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_team_blessings.TeamBlessingTests.setUpClass.__func__)
 setUp=_fixture_test_category2_team_blessings.TeamBlessingTests.setUp
 known=_fixture_test_category2_team_blessings.TeamBlessingTests.known
 begin=_fixture_test_category2_team_blessings.TeamBlessingTests.begin
 snap=_fixture_test_category2_team_blessings.TeamBlessingTests.snap
 valid=_fixture_test_category2_team_blessings.TeamBlessingTests.valid
 restored=_fixture_test_category2_team_blessings.TeamBlessingTests.restored
 add=_fixture_test_category2_team_blessings.TeamBlessingTests.add
 def test_all_three_blessings_create_for_both_actor_kinds_without_a_natural_roll(self):
  for name in ['빛의장막','리플렉터','오로라베일']:
   for role in ['a','p']:
    with self.subTest(name=name,role=role):
     self.setUp();actor=getattr(self,role);self.known(actor,name);self.e.gm.set_weather('hail',rounds=None,reason='actual sourced hail for the Aurora Veil creation gate');self.begin(actor)
     rng=self.e.rng.getstate()
     with patch.object(self.e,'d20',side_effect=AssertionError('no accuracy die exists')):self.e.use_move(actor,actor,'move/'+name)
     self.assertEqual(len(B.live(actor)),1);self.assertEqual(actor.move_uses['move/'+name],1);self.assertEqual(actor.budget['standard'],0)
     self.assertEqual(self.e.rng.getstate(),rng);self.valid()
 def test_facade_distinguishes_none_numeric_zero_and_source_dependent_ac(self):
  move=self.r.move('move/빛의장막');before=self.e.rng.getstate()
  for incidental in [None,1,20]:
   with patch.object(self.e,'d20',side_effect=AssertionError('no accuracy roll')):
    self.assertEqual(self.e.accuracy_check(self.a,self.a,move,fixed_roll=incidental),(True,None,False))
  self.assertEqual(self.e.rng.getstate(),before)
  # Mirror Move's Damage Base says see effect; its separate AC cell is --.
  with patch.object(self.e,'d20',side_effect=AssertionError('Mirror Move has no initial check')):
   self.assertEqual(self.e.accuracy_check(self.a,self.p,self.r.move('move/따라하기')),(True,None,False))
  numerical=dict(move,ac=0)
  self.assertEqual(self.e.accuracy_check(self.a,self.a,numerical,fixed_roll=1),(False,1,False))
  self.assertEqual(self.e.accuracy_check(self.a,self.a,numerical,fixed_roll=20),(True,20,False))
  for name in ['자연의힘']:
   unknown=self.r.move('move/'+name);self.assertIsNone(unknown['ac'])
   self.assertFalse(A.no_status_check(self.e,self.a,self.a,unknown,self.r.move_mech(unknown['id'])[0]))
 def test_blur_reintroduces_native_check_and_never_miss_damage_still_has_crit_roll(self):
  self.a.spec['feats']=[CPF.BLUR];self.a.spec['skills'].update({'곡예':'전문','은신':'전문'})
  self.a.spec['feature_stat_imports']={CPF.BLUR:{'mode':'apply','base_stat':self.a.stats['spe']}}
  I.register_feats(self.e,self.a);self.known(self.a,'빛의장막');self.begin(self.a)
  with patch.object(self.e,'d20',return_value=1) as die:self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertEqual(die.call_count,1);self.assertFalse(B.live(self.a));self.assertEqual(self.a.move_uses['move/빛의장막'],1)
  move=self.r.move('move/스피드스타')
  self.assertEqual(self.e.accuracy_check(self.other,self.p,move,fixed_roll=1),(True,1,False))
  self.assertEqual(self.e.accuracy_check(self.other,self.p,move,fixed_roll=20),(True,20,True))
 def test_no_check_cannot_consume_named_ap_bonus_or_start_reliable_reroll(self):
  self.known(self.a,'빛의장막');self.begin(self.a);AP.prepare(self.e,self.a,self.a,roll_id='future-real-roll',kind='accuracy')
  before=self.snap();ap=deepcopy(self.e._ap_rolls,{id(self.a):self.a})
  with self.assertRaisesRegex(ValueError,'no accuracy roll'):self.e.use_move(self.a,self.a,'move/빛의장막',roll_id='future-real-roll')
  self.assertEqual(self.snap(),before);self.assertEqual(self.e._ap_rolls,ap);self.assertFalse(B.live(self.a))
  with self.assertRaisesRegex(ValueError,'no accuracy roll'):self.e.use_move(self.a,self.a,'move/빛의장막',reliable_trainer=self.a)
  self.assertEqual(self.snap(),before)
 def test_conditional_numeric_replacement_is_applied_only_when_its_condition_is_true(self):
  self.known(self.a,'빛의장막');self.begin(self.a)
  self.a.registry.append({'type':'accuracy_override','ac':2,'if_weather':'hail'})
  self.e.weather=None
  with patch.object(self.e,'d20',side_effect=AssertionError('inactive override')):self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertEqual(len(B.live(self.a)),1)
  self.setUp();self.known(self.a,'빛의장막');self.begin(self.a);self.e.gm.set_weather('hail',rounds=None,reason='actual sourced hail for the conditional accuracy override')
  self.a.registry.append({'type':'accuracy_override','ac':2,'if_weather':'hail'})
  with patch.object(self.e,'d20',return_value=1) as die:self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertEqual(die.call_count,1);self.assertFalse(B.live(self.a))
 def test_unresolved_replacement_and_invented_natural_predicate_hold_before_cost(self):
  self.known(self.a,'빛의장막');self.begin(self.a)
  self.a.registry.append({'type':'accuracy_override','ac':2,'if':'an unobserved narrative prerequisite'})
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'conditional AC replacement'):self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertEqual(self.snap(),before)
  self.a.registry.clear();base=self.r.move_mech;mm,confidence=base('move/빛의장막');mm=deepcopy(mm)
  mm['effects_exec'].append({'type':'accuracy_mod','value':1,'on_natural_roll_min':19,'target':'self'})
  before=self.snap()
  with patch.object(self.r,'move_mech',side_effect=lambda mid:(mm,confidence) if mid=='move/빛의장막' else base(mid)):
   with self.assertRaisesRegex(ValueError,'natural-roll'):self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertEqual(self.snap(),before)
  mm=deepcopy(base('move/빛의장막')[0]);mm['on_natural_roll']={'min':19,'effects':[]}
  with patch.object(self.r,'move_mech',side_effect=lambda mid:(mm,confidence) if mid=='move/빛의장막' else base(mid)):
   with self.assertRaisesRegex(ValueError,'natural-roll'):self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertEqual(self.snap(),before)
 def test_policy_classification_matches_exact_original_ac_cells(self):
  policy=A.policy(self.r)
  with (ROOT/'input/db/moves.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
  for group in ['sources','unresolved']:
   for source,entry in policy[group].items():
    with self.subTest(source=source):
     row=rows[entry['source_record']-1]
     self.assertEqual(row[5],entry['source_ac_cell']);self.assertEqual(row[9],entry['class'])
     self.assertEqual(hashlib.sha256(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),entry['source_row_sha256'])
     self.assertEqual(row[5]=='--',group=='sources')
     self.assertEqual(self.r.moves[source]['_source']['columns']['ac'],6)
 def test_keyword_immunity_remains_effective_without_an_accuracy_roll(self):
  self.known(self.a,'빛의장막');self.begin(self.a);self.a.keyword_immune={'축복'}
  with patch.object(self.e,'d20',side_effect=AssertionError('no accuracy die')):self.e.use_move(self.a,self.a,'move/빛의장막')
  self.assertFalse(B.live(self.a));self.assertEqual(self.a.move_uses['move/빛의장막'],1)

if __name__=='__main__':unittest.main()
