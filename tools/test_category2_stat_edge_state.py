"""Attack Conflict uses exact selected-stat exemptions on real progression."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon
import builder as B,pokemon_stat_edges as E,downtime as D,pokemon_party as PARTY
import state_fields as F

class StatEdgeStateTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_progression_state.ProgressionStateTests.setUp
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def pokemon(self,level=35):return self.add(build_pokemon(self.r,'근육몬',level,moves=[],abilities=[],strategy='special',extra={'trainer_id':self.a.entity_id,'tutor_points':5}))
 def teach(self,c,stat,**kw):return self.e.pokemon_activity(self.a,'teach_edge',target=c,edge=E.ATTACK_CONFLICT,stat=stat,**kw,safe=True)
 def state_for_boundary(self,c,exempt):
  base=B.allocation_base(self.r,c.spec);stats={k:v*100 for k,v in base.items()}
  raised='hp' if exempt=='atk' else 'spa';stats[raised]=stats['atk' if exempt=='atk' else 'spd']-1
  F.base_patch(c,{'stats':stats},reason='GM observed current distributed points')
  return raised
 def test_choice_cost_hour_and_no_trainer_feature_or_level_prerequisite(self):
  for choice,expected in [('공격','atk'),('특수공격','spa')]:
   self.setUp();c=self.pokemon(1);out=self.teach(c,choice)
   self.assertEqual((out['stat'],c.spec['tutor_points'],self.e.elapsed_seconds),(expected,4,3600))
   self.assertEqual(E.exemptions(self.r,c.spec),{expected})
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(c,'spa' if expected=='atk' else 'atk')
   self.assertEqual(before,self.snap())
 def test_both_choices_remove_only_their_own_base_relation_pairs_in_native_levelup(self):
  for selected in ('atk','spa'):
   self.setUp();c=self.pokemon();raised=self.state_for_boundary(c,selected);before=self.snap()
   with self.assertRaisesRegex(ValueError,'base relations'):D.gain_exp_combatant(self.e,c,'to next level',stat_choices={36:raised})
   self.assertEqual(before,self.snap());self.teach(c,selected);old=deepcopy(c.spec['stats'])
   D.gain_exp_combatant(self.e,c,'to next level',stat_choices={36:raised})
   self.assertEqual(c.stats[raised],old[raised]+1);self.assertEqual(c.stats[selected],old[selected]+int(raised==selected))
   self.assertEqual(c.spec['stat_history'][-1]['choice'],raised);self.assertEqual(c.level,36)
 def test_other_stats_still_obey_base_relations_and_old_points_are_not_reassigned(self):
  c=self.pokemon();self.teach(c,'atk');stats={k:v*100 for k,v in B.allocation_base(self.r,c.spec).items()};stats['spd']=stats['def']-1
  F.base_patch(c,{'stats':stats},reason='GM current allocations');before=self.snap()
  with self.assertRaisesRegex(ValueError,'base relations'):D.gain_exp_combatant(self.e,c,'to next level',stat_choices={36:'spd'})
  self.assertEqual(before,self.snap())
  D.gain_exp_combatant(self.e,c,'to next level',stat_choices={36:'def'})
  self.assertEqual(c.stats,{**stats,'def':stats['def']+1})
 def test_actual_evolution_reallocation_preserves_selected_exception_and_payment(self):
  c=self.pokemon();self.teach(c,'spa');new=B.species_lookup(self.r,'괴력몬');points=c.level+10
  expected=B.allocate_stats(new['base_stats'],points,'special',None,self.r,relation_exempt={'spa'})
  ordinary=B.allocate_stats(new['base_stats'],points,'special',None,self.r)
  self.assertNotEqual(expected,ordinary)
  self.assertTrue(D.evolve_combatant(self.e,c,'괴력몬')['evolved'])
  self.assertEqual(c.stats,expected);self.assertEqual(E.exemptions(self.r,c.spec),{'spa'});self.assertEqual(c.spec['tutor_points'],4)
 def test_invalid_choice_or_missing_points_refuses_without_time_or_state_change(self):
  c=self.pokemon()
  for bad in ('hp','def',None,True):
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(c,bad)
   self.assertEqual(before,self.snap())
  c.spec['tutor_points']=0;before=self.snap()
  with self.assertRaises(ValueError):self.teach(c,'atk')
  self.assertEqual(before,self.snap())
 def test_actual_grooming_can_share_completed_hour_with_permanent_edge(self):
  c=self.pokemon();self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.e.pokemon_activity(self.a,'groom',targets=[c],safe=True);out=self.teach(c,'atk',from_grooming=True)
  self.assertEqual((self.e.elapsed_seconds,out['seconds'],c.spec['tutor_points']),(3600,0,4))
  self.assertIn(E.ATTACK_CONFLICT,c.spec['training_credit']['applications'])
 def test_transfer_and_both_restore_routes_keep_permanent_choice_without_refund(self):
  c=self.pokemon();self.teach(c,'atk');saved=self.e.gm.snapshot()
  c.spec['learned_poke_edges'][0]['stat']='spa';self.e.gm.restore(saved)
  current={a.entity_id:a for a in self.e.gm.everyone};c=current[c.entity_id];self.a=current[self.a.entity_id]
  self.assertEqual(E.exemptions(self.r,c.spec),{'atk'})
  from builder import build_trainer
  other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(F.STATS,10)))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='actual party',roster=[c]);PARTY.configure(self.e,other,mode='unlimited',reason='actual party',roster=[])
  PARTY.transfer(self.e,self.a,target=c,new_owner=other,reason='actual transfer',request_id='stat-edge-transfer')
  self.assertEqual((E.exemptions(self.r,c.spec),c.spec['tutor_points']),({'atk'},4))
  loaded=self.restored();child=next(x for x in loaded.gm.everyone if x.entity_id==c.entity_id)
  self.assertEqual((E.exemptions(self.r,child.spec),child.spec['tutor_points']),({'atk'},4))
  child.spec['learned_poke_edges'][0]['stat']='def';self.assertFalse(loaded.validate_state()['valid'])

if __name__=='__main__':unittest.main()
