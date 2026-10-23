"""Realized Potential evolution keeps working through the shared capability projection.

Sources: input/ch05-pokemon.md:315 (C05-069), CSV input/db/poke-edges.csv R27 and homebrew R69, core 1.05 p.204.
Evolution is an allowed event for both definitions: an evolved species base total of 45 or more removes the
bonus and refunds the Tutor Points (R27/C05-069); below 45 the bonus is recalculated from the new species;
the homebrew row recalculates from the evolved species and refunds when the Underdog capability is lost (R69).
The evolved-sheet projection in underdog_edges.evolution_points must reach state_grants' capability owner,
including the Survivalist capability projection, as an actual Pokemon subject (repair of audit S-pedge-3).
"""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category2_underdog_edges as _fixture_test_category2_underdog_edges
from builder import build_pokemon,species_lookup
import downtime as D,growth_stats as GS,underdog_edges as U
import state_grants as G,survivalist_class as SURVIVAL

R27='C2CSV/input/db/poke-edges.csv:R27:main'
R69='C2CSV/input/db/poke-edges.csv:R69:main'


class RealizedPotentialEvolutionRegressionTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_underdog_edges.RealizedPotentialTests.setUpClass.__func__)
 add=_fixture_test_category2_underdog_edges.RealizedPotentialTests.add
 snap=_fixture_test_category2_underdog_edges.RealizedPotentialTests.snap
 restored=_fixture_test_category2_underdog_edges.RealizedPotentialTests.restored
 setUp=_fixture_test_category2_underdog_edges.RealizedPotentialTests.setUp
 pokemon=_fixture_test_category2_underdog_edges.RealizedPotentialTests.pokemon
 choice=_fixture_test_category2_underdog_edges.RealizedPotentialTests.choice
 def teach(self,edge,source):
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=edge,growth=self.choice(source),safe=True)
 def child(self,engine):return next(a for a in engine.gm.everyone if a.entity_id==self.p.entity_id)
 def test_book_and_csv_r27_evolution_to_45_or_more_succeeds_refunds_once_and_survives_json_restore(self):
  for edge in (U.POTENTIAL,R27):
   with self.subTest(edge=edge):
    self.setUp();out=self.teach(edge,U.POTENTIAL)
    self.assertEqual((out['bonus_points'],out['definition_origin']['record'],self.p.spec['tutor_points']),(24,27,6))
    self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
    self.assertEqual((self.p.spec['species'],self.p.spec['tutor_points'],U.records(self.p.spec)[0]['status']),(species_lookup(self.r,'갸라도스')['id'],8,'refunded'))
    self.assertEqual(U.records(self.p.spec)[0]['refund']['points'],2)
    self.assertNotIn('bonus_points',GS.project(self.r,self.p.spec)['contributions'])
    loaded=self.restored();child=self.child(loaded)
    self.assertEqual((child.spec['tutor_points'],U.records(child.spec)[0]['status']),(8,'refunded'))
    loaded.growth_stat_projection(child)
 def test_book_and_csv_r27_evolution_below_45_recomputes_bonus_from_new_species(self):
  for edge in (U.POTENTIAL,R27):
   with self.subTest(edge=edge):
    self.setUp();self.p=self.pokemon(species='이상해씨')
    self.assertEqual(self.teach(edge,U.POTENTIAL)['bonus_points'],11)
    self.assertTrue(D.evolve_combatant(self.e,self.p,'이상해풀')['evolved'])
    row=U.records(self.p.spec)[0];now=GS.project(self.r,self.p.spec)
    self.assertEqual((row['status'],row['species_points'],self.p.spec['tutor_points']),('active',5,6))
    self.assertEqual(sum(now['contributions']['bonus_points'].values()),5)
    self.assertEqual(row['evolution_history'][-1]['previous']['species_points'],11)
 def test_homebrew_r69_evolution_refunds_when_actual_underdog_capability_is_lost(self):
  self.p=self.pokemon(20);self.teach(R69,U.HOMEBREW)
  self.assertEqual((U.records(self.p.spec)[0]['source'],self.p.spec['tutor_points']),(U.HOMEBREW,6))
  self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  self.assertFalse(U.owned(self.p))
  row=U.records(self.p.spec)[0]
  self.assertEqual((self.p.spec['tutor_points'],row['status'],row['refund']['reason']),(8,'refunded','actual Underdog capability lost at evolution'))
  child=self.child(self.restored());self.assertEqual((child.spec['tutor_points'],U.records(child.spec)[0]['status']),(8,'refunded'))
 def test_evolved_sheet_projection_reaches_shared_capability_owner_as_actual_pokemon_subject(self):
  self.teach(U.POTENTIAL,U.POTENTIAL);seen=[];native=SURVIVAL.capability_contributions;projection=U.evolution_points
  def observe(actor):
   seen.append((actor.kind,actor.spec.get('species'),actor.custom_conditions=={}));return native(actor)
  def evolution_points(*args,**kwargs):
   with patch.object(SURVIVAL,'capability_contributions',side_effect=observe):return projection(*args,**kwargs)
  with patch.object(U,'evolution_points',side_effect=evolution_points):
   self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  self.assertEqual(seen,[('pokemon',species_lookup(self.r,'갸라도스')['id'],True)])
 def test_pure_evolution_budget_projection_never_mutates_the_live_sheet(self):
  self.p=self.pokemon(species='이상해씨');self.teach(U.POTENTIAL,U.POTENTIAL);before=deepcopy(self.p.spec)
  out=U.evolution_points(self.r,self.p.spec,species_lookup(self.r,'이상해풀'))
  self.assertEqual((out['budgets'],out['ending']),([{'source':U.POTENTIAL,'points':5}],[]))
  self.assertEqual(self.p.spec,before)
  out=U.evolution_points(self.r,self.p.spec,species_lookup(self.r,'이상해꽃'))
  self.assertEqual(out['ending'],[{'source':U.POTENTIAL,'reason':'actual Underdog capability lost at evolution'}])
  self.assertEqual(self.p.spec,before)
  G.grant(self.p,'capabilities','약골','observed-underdog','gm_observation',rule_id='capability/약골');before=deepcopy(self.p.spec)
  out=U.evolution_points(self.r,self.p.spec,species_lookup(self.r,'이상해꽃'))
  self.assertEqual(out['ending'],[{'source':U.POTENTIAL,'reason':'evolved species base total reached source refund threshold'}])
  self.assertEqual(self.p.spec,before)
 def test_gm_restore_returns_the_unevolved_receipt_and_the_refund_happens_exactly_once(self):
  self.teach(U.POTENTIAL,U.POTENTIAL);saved=self.e.gm.snapshot()
  self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  self.e.gm.restore(saved,reason='actual GM rewind before evolution');self.p=self.child(self.e)
  self.assertEqual((self.p.spec['species'],self.p.spec['tutor_points'],U.records(self.p.spec)[0]['status']),(species_lookup(self.r,'잉어킹')['id'],6,'active'))
  self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  row=U.records(self.p.spec)[0]
  self.assertEqual((self.p.spec['tutor_points'],row['status'],len(row['evolution_history'])),(8,'refunded',1))
 def test_refused_evolution_leaves_receipt_tp_and_stats_unchanged(self):
  self.teach(U.HOMEBREW,U.HOMEBREW);before=self.snap()
  with self.assertRaises(ValueError):D.evolve_combatant(self.e,self.p,'갸라도스',underdog_decision={'value':'signed_points','reason':'no actual pending negative interpretation','scope':{}})
  self.assertEqual(self.snap(),before)
 def test_evolution_without_realized_potential_is_unchanged(self):
  self.assertEqual(U.evolution_points(self.r,self.p.spec,species_lookup(self.r,'갸라도스'))['budgets'],[])
  self.assertTrue(D.evolve_combatant(self.e,self.p,'갸라도스')['evolved'])
  self.assertEqual((self.p.spec['tutor_points'],U.records(self.p.spec)),(8,[]))


if __name__=='__main__':
 unittest.main()
