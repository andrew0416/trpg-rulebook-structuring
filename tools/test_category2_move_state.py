"""Whole-clause state proofs for ability/move cardinality and natural history."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import state_codec as CODEC
import state_grants as G
import state_fields as F
import move_state as M
import pokemon_teaching as T
import downtime as D
from encounter import usable_moves

class MoveStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):self.e=Engine(self.r,seed=535)
 def add(self,spec):
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c,pos=(1,1),side='party',reason='actual observed actor enters roster');return c
 def restore(self):
  return CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
 def trainer(self,name='trainer',**kw):
  return build_trainer(self.r,name,20,{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},**kw)
 def test_no_total_ability_cap_for_trainer_or_pokemon_with_native_passives(self):
  names=['복안','마이페이스','유연','클리어바디','하얀연기']
  for kind in ('trainer','pokemon'):
   spec=self.trainer(kind,abilities=names[:3]) if kind=='trainer' else build_pokemon(self.r,'이상해씨',30,name=kind,abilities=names[:3])
   c=self.add(spec)
   for name in names[3:]:self.e.gm.set_ability(c,name,reason='observed independent acquired ability')
   self.assertEqual(c.abilities,names);self.assertEqual(c.accuracy_stage,3)
   self.assertIn('all',c.stage_loss_immune)  # Cardinality clause; individual ability effects have separate source obligations.
   self.assertEqual(len(G.state(c)['ability_receipts']),5)
  e=self.restore()
  for c in e.everyone:
   self.assertEqual(c.abilities,names);self.assertEqual(c.accuracy_stage,3);self.assertEqual(len(G.state(c)['ability_receipts']),5)
 def test_level_slot_adds_to_extra_abilities_without_total_three_cap(self):
  names=['복안','마이페이스','유연','클리어바디','하얀연기']
  c=self.add(build_pokemon(self.r,'이상해씨',19,abilities=names,moves=['move/몸통박치기']))
  D.gain_exp_combatant(self.e,c,'to next level')
  self.assertEqual(c.level,20);self.assertEqual(c.abilities,names)
  choices=c.spec['growth_milestone_choices']['ability:20']['offered']['options']
  self.e.choose_growth_ability(c,20,choices[-1],reason='explicit additional ability')
  self.assertEqual(len(c.abilities),6)
  self.assertTrue(set(names).issubset(c.abilities))
  self.assertEqual(len(set(c.abilities)-set(names)),1)
  e=self.restore();self.assertEqual(e.everyone[0].abilities,c.abilities)

 def test_unlimited_ability_sources_gm_snapshot_and_last_source_removal(self):
  c=self.add(build_pokemon(self.r,'이상해씨',30,abilities=['복안','마이페이스','유연','클리어바디','하얀연기']))
  for source in ('item:one','feature:two'):G.grant(c,'abilities','복안',source,'fixture')
  G.reconcile(self.e,c);self.e.gm.set_ability(c,'복안',add=False,reason='permanent source ended')
  self.assertEqual((len(c.abilities),c.abilities.count('복안'),c.accuracy_stage),(5,1,3))
  self.e.gm.snapshot('independent-ability-sources');G.revoke(c,'item:one',engine=self.e);G.revoke(c,'feature:two',engine=self.e)
  self.assertEqual((len(c.abilities),c.accuracy_stage),(4,0))
  self.e.gm.restore('independent-ability-sources');self.assertEqual(c.accuracy_stage,3)
  e=self.restore();c=e.everyone[0];G.revoke(c,'item:one',engine=e)
  self.assertEqual((len(c.abilities),c.accuracy_stage),(5,3));G.revoke(c,'feature:two',engine=e)
  self.assertEqual((len(c.abilities),c.accuracy_stage),(4,0));self.assertIn('all',c.stage_loss_immune)
 def test_trainer_more_than_six_native_moves_preserves_source_overlap_and_storage(self):
  names=['몸통박치기','울음소리','덩굴채찍','씨뿌리기','잎날가르기','성장','수면가루','독가루']
  mids=[self.r.move_id(n) for n in names];self.assertNotIn(None,mids)
  c=self.add(self.trainer(moves=mids[:7],abilities=[]));self.e.gm.set_move(c,mids[7],reason='eighth acquired trainer move')
  for source in ('item:move-one','feature:move-two'):G.grant(c,'moves',mids[7],source,'fixture')
  self.assertEqual(set(usable_moves(self.e,c)),set(mids+['struggle']))
  self.assertEqual(len([m for m in c.moves if m!='struggle']),8)
  self.e.gm.snapshot('unlimited-moves');self.e.gm.set_move(c,mids[7],add=False,reason='permanent source ends')
  self.assertIn(mids[7],usable_moves(self.e,c));self.e.gm.restore('unlimited-moves')
  e=self.restore();c=e.everyone[0]
  for source in ('item:move-one','feature:move-two'):G.revoke(c,source,engine=e)
  self.assertIn(mids[7],usable_moves(e,c));e.gm.set_move(c,mids[7],add=False,reason='only remaining permanent source ends')
  self.assertEqual(len([m for m in usable_moves(e,c) if m!='struggle']),7)
 def test_actual_level_opportunity_retained_through_evolution_and_durable_state(self):
  c=self.add(build_pokemon(self.r,'브케인',39,abilities=[],moves=['move/화염방사'],extra={'tutor_points':3,'move_learning':{'move/화염방사':{'method':'tm','source':T.MACHINES,'learned_at_level':30,'natural':False}}}))
  self.assertEqual(T.classifications(self.r,c.spec)['move/화염방사'],'taught')
  D.gain_exp_combatant(self.e,c,'to next level')
  events=deepcopy(c.spec[M.HISTORY]['move/화염방사'])
  self.assertEqual((c.level,T.classifications(self.r,c.spec)['move/화염방사']),(40,'natural'))
  self.assertTrue(any(x['species_id']=='pokemon/브케인' and x['required_level']==40 and x['at_level']==40 for x in events))
  self.assertTrue(D.evolve(self.r,c.spec,'마그케인'))
  self.assertNotIn('move/화염방사',M.current_natural_evidence(self.r,c.spec))
  self.assertEqual(T.classifications(self.r,c.spec)['move/화염방사'],'natural')
  self.assertEqual(c.spec[M.HISTORY]['move/화염방사'],events)
  spec=deepcopy(c.spec);self.e=Engine(self.r,seed=536);c=self.add(spec)
  e=self.restore();loaded=e.everyone[0]
  self.assertEqual(T.classifications(self.r,loaded.spec)['move/화염방사'],'natural')
  self.assertEqual(loaded.spec['move_learning']['move/화염방사']['method'],'tm')
 def test_initial_natural_evidence_keeps_egg_and_n_tutor_distinct_without_learning_anything(self):
  sample=None
  for sp in self.r.species.values():
   if sp.get('name')=='알':continue
   evidence=M.current_natural_evidence(self.r,{'species':sp['id'],'level':1})
   egg=next((m for m,rows in evidence.items() if any(x['kind']=='egg' for x in rows)),None)
   nt=next((m for m,rows in evidence.items() if any(x['kind']=='n_tutor' for x in rows)),None)
   if egg and nt and egg!=nt:sample=(sp['name'],egg,nt);break
  self.assertIsNotNone(sample);species,egg,nt=sample
  spec=build_pokemon(self.r,species,1,moves=[egg,nt],abilities=[])
  before=deepcopy(spec['moves']);M.record_natural_opportunities(self.r,spec,reason='same observed known moves')
  self.assertEqual(spec['moves'],before);self.assertEqual(T.classifications(self.r,spec),{egg:'natural',nt:'natural'})
  self.assertTrue(any(x['kind']=='egg' for x in spec[M.HISTORY][egg]))
  self.assertTrue(any(x['kind']=='n_tutor' for x in spec[M.HISTORY][nt]))
 def test_natural_record_preflights_all_learning_rows_and_retry_is_idempotent(self):
  spec=build_pokemon(self.r,'브케인',39,moves=['move/화염방사'],abilities=[])
  spec['level']=40;spec['move_learning']={'move/화염방사':{'method':'tm','source':T.MACHINES,'natural':False},'move/연막':'malformed'}
  before=deepcopy(spec)
  with self.assertRaisesRegex(ValueError,'must be a record'):M.record_natural_opportunities(self.r,spec,reason='observed actual learning opportunity')
  self.assertEqual(spec,before)
  spec['move_learning']['move/연막']={'method':'tm','source':T.MACHINES,'natural':False}
  record=spec['move_learning']['move/화염방사']
  added=M.record_natural_opportunities(self.r,spec,reason='observed actual learning opportunity')
  self.assertEqual(len(added),1);self.assertIs(spec['move_learning']['move/화염방사'],record);self.assertTrue(record['natural'])
  self.assertEqual(M.record_natural_opportunities(self.r,spec,reason='same actual observation'),[])
  self.assertEqual(len(spec[M.HISTORY]['move/화염방사']),1)

 def test_forged_natural_event_rejects_before_level_mutation(self):
  spec=build_pokemon(self.r,'브케인',39,moves=['move/화염방사'],abilities=[])
  spec[M.HISTORY]={'move/화염방사':[{'source':M.SOURCE,'species_id':'pokemon/브케인','kind':'level_up','required_level':40,'at_level':39,'reason':'invalid claimed past opportunity'}]}
  before=deepcopy(spec)
  with self.assertRaisesRegex(ValueError,'historical species and level'):D.level_up(self.r,spec)
  self.assertEqual(spec,before)

if __name__=='__main__':unittest.main()
