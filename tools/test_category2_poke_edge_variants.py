"""Native coverage of 29 reviewed CSV specializations sharing investment policies."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon
from ruleset import RuleFilter
import poke_edge_variants as V,pokemon_skill_edges as S,pokemon_capability_edges as C
import movement_actions as M,skill_modifiers as SK

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_progression_state.ProgressionStateTests.setUpClass.__func__)
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self)
  self.e.pokemon_activity(self.a,'configure_intelligence',
      portrayal='Pokemon may learn the selected social and education specializations',discussed_with=['edge training participants'],
      social=True,education=True,reason='explicit campaign permission for assigned and taught skill pools')
  self.p=self.add(build_pokemon(self.r,'근육몬',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':20}))
  self.raw=dict(land=4,sky=3,swim=2,levitate=2,burrow=2,teleport=2,power=3,high_jump=1,long_jump=2)
  self.e.gm.set_movement_capabilities(self.p,self.raw,basis='base',reason='observed base capabilities')
 def teach(self,row,**kw):
  if row['choice'] is None:kw.setdefault(row['field'],'육상' if row['field']=='skill' else 'power' if row['record']==32 else 'land')
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=row['clause_id'],**kw,safe=True)
 def test_all_29_definitions_change_actual_readers_and_preserve_origin(self):
  rows=[r for r in V.catalog(self.r) if r['field'] in ('skill','capability') and r['policy'] in ('poke_edge/스킬-향상',C.TRAINING,C.MOBILITY)];self.assertEqual(len(rows),29)
  for row in rows:
   with self.subTest(record=row['record']):
    self.setUp();value=V.choice_value(self.r,row,row['choice'] or ('육상' if row['field']=='skill' else 'power' if row['record']==32 else 'land'))
    before=S.skill_pool(self.r,self.p.spec,value) if row['field']=='skill' else M.capabilities(self.e,self.p)[value]
    out=self.teach(row)
    self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(19,3600))
    receipt=self.p.spec['learned_poke_edges'][-1]
    self.assertEqual(receipt['definition_origin']['clause_id'],row['clause_id'])
    self.assertEqual(out['definition_origin'],receipt['definition_origin'])
    if row['field']=='skill':
     now=S.skill_pool(self.r,self.p.spec,value);self.assertEqual(now,(before[0]+1,before[1]))
     self.assertEqual(self.e.skill_roll(self.p,value,fixed=[1]*now[0]).total,now[0]+now[1])
    else:
     self.assertEqual(M.capabilities(self.e,self.p)[value],before+C.RULES[row['policy']]['amount'])
     self.assertEqual(self.p.spec['movement'],self.raw)
    state=self.snap()
    with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=row['policy'],**{row['field']:value},safe=True)
    self.assertEqual(self.snap(),state)
 def test_cached_source_and_definition_changes_reject_before_teaching(self):
  row=next(x for x in V.catalog(self.r) if x['record']==3)
  original=Path.read_bytes
  for filename in ('poke-edges.csv','poke-edge-variants.json'):
   before=self.snap()
   def changed(path):
    raw=original(path)
    return raw+b'changed' if path.name==filename else raw
   with patch.object(Path,'read_bytes',changed):
    with self.assertRaisesRegex(ValueError,'changed'):self.teach(row)
   self.assertEqual(before,self.snap())
 def test_returned_catalog_cannot_change_future_selected_policy(self):
  rows=V.catalog(self.r);expected=deepcopy(rows[0]);rows[0]['policy']='invented'
  self.assertEqual(V.catalog(self.r)[0],expected)
 def test_fixed_choice_mismatch_rejected_before_any_cost(self):
  for record,bad in [(3,{'skill':'육상'}),(33,{'capability':'high_jump'}),(37,{'capability':'sky'})]:
   row=next(x for x in V.catalog(self.r) if x['record']==record);before=self.snap()
   with self.assertRaises(ValueError):self.teach(row,**bad)
   self.assertEqual(self.snap(),before)
 def test_origin_survives_native_codec_and_snapshot_for_all_three_policies(self):
  for record in (3,33,37):
   row=next(x for x in V.catalog(self.r) if x['record']==record);self.teach(row)
  receipts=deepcopy(self.p.spec['learned_poke_edges']);self.e.gm.snapshot('investments')
  self.e.gm.set_level(self.p,19,reason='lost capability prerequisites')
  self.assertEqual(self.p.spec['tutor_points'],19)
  self.e.gm.restore('investments',reason='restore source-owned choices')
  self.assertEqual(self.p.spec['learned_poke_edges'],receipts)
  n=self.restored();p=next(x for x in n.gm.everyone if x.entity_id==self.p.entity_id)
  self.assertEqual(p.spec['learned_poke_edges'],receipts)
  self.assertEqual(M.capabilities(n,p)['land'],6)
  self.assertEqual(n.skill_roll(p,'곡예',fixed=[1]*3).total,5)
 def test_native_point_receipts_follow_prerequisite_refund_after_restore(self):
  from state_codec import dump_engine,load_engine
  selected=[next(row for row in V.catalog(self.r) if row['record']==record) for record in (33,37)]
  choices=[V.choice_value(self.r,row,row['choice'] or ('power' if row['record']==32 else 'land')) for row in selected]
  baseline={choice:M.capabilities(self.e,self.p)[choice] for choice in choices}
  for row in selected:self.teach(row)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(18,7200))
  before=self.snap();paid=self.e.acquisition_receipts(self.p);self.assertEqual(before,self.snap())
  self.assertEqual(len(paid),2)
  for receipt,row in zip(paid,selected):
   self.assertEqual(receipt['basis'],'native_learned_edge')
   self.assertEqual(receipt['source_id'],row['policy'])
   self.assertEqual(receipt['provider_id'],self.a.entity_id)
   self.assertEqual(receipt['recipient_id'],self.p.entity_id)
   self.assertEqual(receipt['debit'],{'payer_id':self.p.entity_id,'resource':'tutor_points','amount':1})
   self.assertEqual(receipt['state'],'active')
   self.assertEqual(receipt['native_record']['definition_origin']['clause_id'],row['clause_id'])
  saved=self.e.gm.snapshot();self.e.gm.set_level(self.p,19,reason='actual level prerequisite was lost')
  refunded=self.e.acquisition_receipts(self.p);self.assertEqual(self.p.spec['tutor_points'],20)
  self.assertEqual({choice:M.capabilities(self.e,self.p)[choice] for choice in choices},baseline)
  for receipt in refunded:
   self.assertEqual(receipt['state'],'refunded')
   self.assertEqual(receipt['debit']['amount'],1)
   self.assertEqual(receipt['native_record']['refund']['points'],1)
   self.assertEqual(receipt['native_record']['refund']['source'],'input/ch05-pokemon.md:274')
  loaded=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False)))
  actual=next(actor for actor in loaded.gm.everyone if actor.entity_id==self.p.entity_id)
  self.assertEqual(loaded.acquisition_receipts(actual),refunded)
  loaded.gm.set_level(actual,18,reason='further permanent level correction')
  self.assertEqual(actual.spec['tutor_points'],20);self.assertEqual(loaded.acquisition_receipts(actual),refunded)
  self.e.gm.restore(saved);self.assertEqual(self.e.acquisition_receipts(self.p),paid)
  self.assertEqual(self.p.spec['tutor_points'],18)
  self.e.gm.set_level(self.p,19,reason='actual level prerequisite was lost')
  self.assertEqual(self.p.spec['tutor_points'],20);self.assertEqual(self.e.acquisition_receipts(self.p),refunded)
  self.assertTrue(self.e.validate_state()['valid']);self.assertTrue(loaded.validate_state()['valid'])
 def test_shared_refund_failure_preserves_actual_level_points_and_investments(self):
  import acquisition_withdrawal as WITHDRAWAL
  for record in (33,37):self.teach(next(row for row in V.catalog(self.r) if row['record']==record))
  before=self.snap();native=WITHDRAWAL.refund_native_investments
  def fail(spec,records,**context):
   if records:raise ValueError('shared native refund failure')
   return native(spec,records,**context)
  with patch.object(WITHDRAWAL,'refund_native_investments',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'shared native refund failure'):
    self.e.gm.set_level(self.p,19,reason='actual level prerequisite was lost')
  self.assertEqual(self.snap(),before)
  self.e.gm.set_level(self.p,19,reason='actual level prerequisite was lost')
  self.assertEqual(self.p.spec['tutor_points'],20)
  self.assertTrue(all(row['state']=='refunded' for row in self.e.acquisition_receipts(self.p)))
 def test_skill_refund_and_capability_refund_keep_csv_identity_once(self):
  for record in (3,33,37):self.teach(next(x for x in V.catalog(self.r) if x['record']==record))
  self.e.gm.set_skill(self.p,'곡예','7d6+2',reason='permanent improvement')
  self.assertEqual(self.p.spec['tutor_points'],18)
  self.e.gm.set_level(self.p,19,reason='lost level prerequisite')
  self.assertEqual(self.p.spec['tutor_points'],20)
  self.assertEqual({x['definition_origin']['record'] for x in self.p.spec['learned_poke_edges']},{3,33,37})
  self.assertTrue(all(x['status']=='refunded' for x in self.p.spec['learned_poke_edges']))
  self.e.gm.set_level(self.p,18,reason='further correction');self.assertEqual(self.p.spec['tutor_points'],20)
 def test_tampered_fixed_choice_or_source_is_rejected_by_native_validation(self):
  row=next(x for x in V.catalog(self.r) if x['record']==37);self.teach(row)
  state=deepcopy(self.p.spec)
  self.p.spec['learned_poke_edges'][0]['choice']='sky'
  with self.assertRaises(ValueError):M.capabilities(self.e,self.p)
  self.p.spec=deepcopy(state);self.p.spec['learned_poke_edges'][0]['definition_origin']['record']=38
  with self.assertRaises(ValueError):M.capabilities(self.e,self.p)
 def test_selected_source_exclusion_prevents_acquisition_and_consumption(self):
  row=next(x for x in V.catalog(self.r) if x['record']==37);self.teach(row)
  old=self.r.ruleset
  self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[row['rule_id']]});self.r._apply_ruleset()
  try:
   with self.assertRaises(ValueError):M.capabilities(self.e,self.p)
   with self.assertRaises(ValueError):V.resolve(self.r,row['clause_id'])
  finally:self.r.ruleset=old;self.r._apply_ruleset()

if __name__=='__main__':unittest.main()
