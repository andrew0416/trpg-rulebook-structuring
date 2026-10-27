"""Whole CSV shiny-creation Language and Mount Training native contracts."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv,io,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as fixture
from engine import Rules,Engine
from builder import build_pokemon
import pokemon_capability_edges as CAP,poke_edge_variants as V,move_state as MOVES,state_grants as G
import csv_item_capability_contracts as LANGUAGE,world_entities as WORLD
from native_scenario_fixture import assert_rejected_unchanged


class CsvPokemonTrainingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT))
 add=fixture.ProgressionStateTests.add
 snap=fixture.ProgressionStateTests.snap
 restored=fixture.ProgressionStateTests.restored
 def setUp(self):fixture.ProgressionStateTests.setUp(self)
 def pokemon(self,*,language=False,moves=None,**extra):
  return self.add(build_pokemon(self.r,'근육몬',20,moves=moves or [],abilities=[],
   extra={'trainer_id':self.a.entity_id,'tutor_points':5,**extra},
   creation_poke_edges=[CAP.LANGUAGE] if language else None))
 def teach(self,p):return self.e.pokemon_activity(self.a,'teach_edge',target=p,edge=CAP.MOUNT,safe=True)
 def row(self,record):return next(row for row in V.catalog(self.r) if row['record']==record)

 def test_named_definition_adapter_preserves_existing_rows_and_rejects_conflicts(self):
  data=json.loads((ROOT/'data/poke-edge-variants.json').read_text(encoding='utf-8'))
  content=(ROOT/'input/db/poke-edges.csv').read_bytes()
  original=[row for row in data['entries'] if row['record'] not in (67,68)]
  legacy=deepcopy(data);legacy['entries']=deepcopy(original)
  restored=V._named_capability_catalog(legacy,content)
  self.assertEqual(restored[:len(original)],original)
  self.assertEqual({row['record'] for row in restored[len(original):]},{67,68})
  self.assertEqual([(row['record'],row['point_cost'],row['native_kind']) for row in restored[len(original):]],
                   [(67,2,'named_capability'),(68,1,'named_capability')])
  complete=deepcopy(data);complete['entries']=deepcopy(restored)
  self.assertEqual(V._named_capability_catalog(complete,content),restored)
  for change in ('wrong_cost','wrong_identity','extra_key','duplicate'):
   with self.subTest(change=change):
    altered=deepcopy(complete);row=next(x for x in altered['entries'] if x['record']==68)
    if change=='wrong_cost':row['point_cost']=True
    elif change=='wrong_identity':row['rule_id']='poke_edge/언어-학습'
    elif change=='extra_key':row['unreviewed']=True
    else:altered['entries'].append(deepcopy(row))
    with self.assertRaisesRegex(ValueError,'conflicts'):
     V._named_capability_catalog(altered,content)
  self.assertEqual(legacy['entries'],original)

 def test_exact_homebrew_rows_and_shiny_creation_language_are_live_not_a_fake_move(self):
  rows=list(csv.reader(io.StringIO((ROOT/'input/db/poke-edges.csv').read_text(encoding='utf-8-sig'))))
  for number in (67,68):
   row=self.row(number);self.assertEqual(row['source_cells'],rows[number-1]);V.selected(self.r,row)
  p=self.pokemon(language=True,shiny=True)
  self.assertEqual(p.spec['tutor_points'],3)
  self.assertEqual(p.spec['moves'],['struggle']);self.assertNotIn('언어',p.spec['capabilities'])
  self.assertEqual(LANGUAGE.language(p)['speaks_human'],True)
  self.assertEqual(MOVES.describe(self.r,p.spec)['slot_count'],1)
  receipt=self.e.acquisition_receipts(p)[-1]
  self.assertEqual(receipt['debit']['amount'],2)
  self.assertEqual(receipt['native_record']['definition_origin']['clause_id'],self.row(67)['clause_id'])
  self.assertEqual(receipt['native_record']['training_source'],'pokemon/creation')
  self.assertEqual(self.e.elapsed_seconds,0)
  self.e.pokemon_activity(self.a,'understanding_profile',target=p,habitat='observed home',organization='actual household',domains={},reason='individual scoped understanding')
  self.e.pokemon_activity(self.a,'request_help',target=p,request_id='spoken',intent='retrieve the familiar basket',understanding={'domains':['human_language'],'context':'this actual spoken request'})
  self.e.pokemon_activity(self.a,'assess_pokemon_request',target=p,request_id='spoken',decisions={'human_language':True},language_exception='언어',reason='actual acquired speech capability supports this spoken request')
  out=self.e.pokemon_activity(self.a,'resolve_help',target=p,request_id='spoken',decision='accept',explanation='GM accepts this understood request')
  self.assertEqual(out['status'],'completed');self.assertNotIn('education',p.spec['pokemon_understanding']['domains'])

 def test_language_creation_only_cost_and_five_slot_boundary_reject_before_mutation(self):
  for extra,pattern in [({'shiny':False},'shiny Pokemon creation'),({'shiny':True,'tutor_points':1},'two actual Tutor Points')]:
   with self.subTest(extra=extra):
    before=self.snap()
    with self.assertRaisesRegex(ValueError,pattern):self.pokemon(language=True,**extra)
    self.assertEqual(before,self.snap())
  mids=list(MOVES.current_natural_evidence(self.r,{'species':'근육몬','level':100}))[:6]
  self.assertEqual(len(mids),6)
  spec=build_pokemon(self.r,'근육몬',100,moves=mids[:5],abilities=[],extra={'shiny':True},creation_poke_edges=[CAP.LANGUAGE])
  self.assertEqual(MOVES.describe(self.r,spec)['slot_count'],6)
  with self.assertRaisesRegex(ValueError,'move slots|Move slots|known moves|capacity|slot limit'):
   build_pokemon(self.r,'근육몬',100,moves=mids,abilities=[],extra={'shiny':True},creation_poke_edges=[CAP.LANGUAGE])
  p=self.pokemon(shiny=True)
  assert_rejected_unchanged(self.e,lambda:self.e.pokemon_activity(self.a,'teach_edge',target=p,edge=CAP.LANGUAGE,safe=True),reason_pattern='actual shiny Pokemon creation')
  assert_rejected_unchanged(self.e,lambda:self.e.pokemon_activity(self.a,'teach_edge',target=p,edge=CAP.LANGUAGE,capability='언어',safe=True),reason_pattern='unexpected choice')

 def test_language_reservation_and_capability_survive_both_native_restores(self):
  p=self.pokemon(language=True,shiny=True)
  paid=self.e.acquisition_receipts(p);saved=self.e.gm.snapshot()
  self.e.gm.set_level(p,19,reason='later level correction is not a lost birth prerequisite')
  self.assertEqual(p.spec['tutor_points'],3);self.assertIsNotNone(LANGUAGE.language(p))
  self.e.gm.restore(saved);self.assertEqual(self.e.acquisition_receipts(p),paid)
  loaded=self.restored();actual=next(c for c in loaded.gm.everyone if c.entity_id==p.entity_id)
  self.assertEqual(loaded.acquisition_receipts(actual),paid)
  self.assertEqual(MOVES.describe(loaded.r,actual.spec)['slot_count'],1)
  self.assertIsNotNone(LANGUAGE.language(actual));self.assertTrue(loaded.validate_state()['valid'])

 def test_mount_all_printed_size_power_shiny_branches_and_rejections(self):
  cases=[('중형',8,True,True),('중형',7,True,False),('중형',8,False,False),
   ('대형',1,True,True),('대형',8,False,True),('대형',7,False,False),
   ('거대형',1,True,True),('거대형',6,False,True),('거대형',5,False,False),
   ('초거대형',1,False,True),('소형',10,True,False)]
  for size,power,shiny,allowed in cases:
   with self.subTest(size=size,power=power,shiny=shiny):
    p=self.pokemon(size=size,shiny=shiny,movement={'land':4,'power':power},capabilities=[])
    before_time=self.e.elapsed_seconds
    if not allowed:
     assert_rejected_unchanged(self.e,lambda:self.teach(p),reason_pattern='size/Power/shiny prerequisites')
     continue
    self.teach(p)
    self.assertEqual((p.spec['tutor_points'],self.e.elapsed_seconds-before_time),(4,3600))
    self.assertIn('탑승 1',G.effective_capabilities(p));self.assertEqual(p.spec['capabilities'],[])
    assert_rejected_unchanged(self.e,lambda:self.teach(p),reason_pattern='already acquired')
  empty=self.pokemon(size='대형',shiny=True,tutor_points=0)
  assert_rejected_unchanged(self.e,lambda:self.teach(empty),reason_pattern='one actual Tutor Point')

 def test_mount_existing_numeric_capability_reaches_actual_boarding_and_action_owner(self):
  p=self.pokemon(size='대형',shiny=True,movement={'land':6,'power':3},capabilities=['탑승 1'])
  self.teach(p);self.assertEqual(G.effective_capabilities(p),['탑승 2'])
  self.a.spec['skills']['곡예']=3;self.a.spec['weight_kg']=60
  self.a.pos=(1,2);p.pos=(2,2)
  policy=json.loads((ROOT/'data/examples/control-mount.json').read_text(encoding='utf8'))[1]
  policy['boarding'].update(action='standard',automatic=None)
  self.e.start_round([self.a,p]);self.e.start_of_turn(self.a,initiative_count=20)
  out=self.e.board_mount(self.a,p,policy,gm_mountable=True,roll_options={'fixed':[6]*3})
  self.assertTrue(out['passed']);self.assertEqual(self.a.budget['standard'],0)
  self.assertIs(WORLD.mount_relation(WORLD.actor_index(self.e),self.a),p)
  self.assertEqual(p.spec['capabilities'],['탑승 1'])
  self.assertTrue(self.e.validate_state()['valid'])

 def test_mount_prerequisite_loss_refunds_once_and_both_restores_preserve_receipt(self):
  p=self.pokemon(size='대형',movement={'land':4,'power':8},capabilities=['탑승 2'])
  self.teach(p);paid=self.e.acquisition_receipts(p);saved=self.e.gm.snapshot()
  learned=deepcopy(p.spec['learned_poke_edges'])
  for field in ('trainer_id','completed_at','training_source'):
   with self.subTest(history=field):
    try:
     del p.spec['learned_poke_edges'][-1][field]
     with self.assertRaises(ValueError):CAP.validate_named(self.r,p.spec)
    finally:p.spec['learned_poke_edges']=deepcopy(learned)
  self.assertIn('탑승 3',G.effective_capabilities(p))
  self.e.gm.set_movement_capabilities(p,{'land':4,'power':7},basis='base',reason='permanent Power prerequisite lost')
  self.assertEqual(p.spec['tutor_points'],5);self.assertEqual(G.effective_capabilities(p),['탑승 2'])
  refunded=self.e.acquisition_receipts(p)
  self.assertEqual(refunded[-1]['state'],'refunded');self.assertEqual(refunded[-1]['native_record']['refund']['points'],1)
  self.e.gm.set_level(p,19,reason='later correction cannot refund twice');self.assertEqual(p.spec['tutor_points'],5)
  loaded=self.restored();actual=next(c for c in loaded.gm.everyone if c.entity_id==p.entity_id)
  self.assertEqual(loaded.acquisition_receipts(actual),refunded)
  self.e.gm.restore(saved);self.assertEqual(self.e.acquisition_receipts(p),paid)
  self.assertEqual((p.spec['tutor_points'],G.effective_capabilities(p)),(4,['탑승 3']))
  import state_fields as F
  F.base_patch(p,{'size':'중형'},reason='permanent normal Medium prerequisite lost')
  self.assertEqual((p.spec['tutor_points'],G.effective_capabilities(p)),(5,['탑승 2']))

 def test_shared_native_refund_failure_and_changed_selected_source_are_atomic(self):
  p=self.pokemon(size='대형',movement={'land':4,'power':8},capabilities=[]);self.teach(p)
  import acquisition_withdrawal as WITHDRAWAL
  with patch.object(WITHDRAWAL,'refund_native_investments',side_effect=ValueError('injected shared refund failure')):
   assert_rejected_unchanged(self.e,lambda:self.e.gm.set_movement_capabilities(p,{'land':4,'power':7},basis='base',reason='actual Power loss'),reason_pattern='injected shared refund failure')
  original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'changed' if path.name=='poke-edges.csv' else raw
  before=self.snap()
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'changed'):G.effective_capabilities(p)
  self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
