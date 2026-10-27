"""Poke Edge receipts keep actual teaching history; Advanced Mobility needs an existing mode.

input/ch05-pokemon.md:274 (core 1.05 p.204 "After an hour of training, Pokemon may spend
Tutor Points"): a learned Edge exists only after an actual teacher's completed training hour
and a Tutor Point payment. Active and refunded native receipts therefore keep trainer_id,
completed_at and training_source (and acquired_level where the producer records it); the
current balance never proves a past payment. Book receipts without a CSV definition_origin
keep their native identity but not an exemption from this history.

input/ch05-pokemon.md:352-355 (core 1.05 p.205 "Increase one Movement Capability by 2"):
Advanced Mobility never creates a Movement Capability. A mode lost after acquisition (for
example by evolution or a corrected base observation) leaves the investment dormant, not
refunded; Capability Training (Power/Jump) still applies to an existing 0 value.
"""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_progression_state as _fixture
import test_category2_advanced_connection as _connection
from builder import build_pokemon
import poke_edge_variants as V,pokemon_skill_edges as SKILL,pokemon_stat_edges as STAT
import pokemon_move_edges as MOVE,pokemon_capability_edges as CAP,ranged_struggle as RANGED
import tk_mastery as TK,invisibility_edge as INVIS,advanced_connection as CONNECTION
import ability_mastery as ABILITY,skill_modifiers as SK,movement_actions as M,jump_actions as J
import downtime as D

RAW={'land':4,'sky':3,'swim':2,'levitate':2,'burrow':2,'teleport':2,'power':3,'high_jump':1,'long_jump':2}
REJECT='trainer|training|acquisition|historical'
ORDINARY,TRAINING,GROOMING='input/ch05-pokemon.md:274','input/ch05-pokemon.md:229','edge/미용사'


def origin(row):return {k:row[k] for k in ('clause_id','rule_id','record')}


class _Edges(unittest.TestCase):
 setUpClass=classmethod(_fixture.ProgressionStateTests.setUpClass.__func__)
 add=_fixture.ProgressionStateTests.add
 snap=_fixture.ProgressionStateTests.snap
 restored=_fixture.ProgressionStateTests.restored
 def setUp(self):
  _fixture.ProgressionStateTests.setUp(self)
  self.p=self.pokemon('근육몬',20,moves=['메가톤펀치'])
 def pokemon(self,species,level,moves=(),tp=8):
  return self.add(build_pokemon(self.r,species,level,moves=list(moves),abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':tp}))
 def teach(self,edge,target=None,**kw):
  return self.e.pokemon_activity(self.a,'teach_edge',target=target or self.p,edge=edge,safe=True,**kw)
 def row(self,record):return next(x for x in V.catalog(self.r) if x['record']==record)
 def loaded(self,engine,actor=None):return next(x for x in engine.gm.everyone if x.entity_id==(actor or self.p).entity_id)
 def base(self,values=RAW,actor=None):
  self.e.gm.set_movement_capabilities(actor or self.p,dict(values),basis='base',reason='GM observed actual pre-bonus capabilities')
 def assert_rejected(self,receipt,pattern=REJECT):
  """A receipt without actual teaching history is refused by native validation and restore."""
  rows=self.p.spec.setdefault('learned_poke_edges',[]);rows.append(receipt)
  try:
   self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(8,0))
   self.assertFalse(self.e.validate_state()['valid'])
   with self.assertRaisesRegex(ValueError,pattern):self.restored()
  finally:rows.remove(receipt)


class PokeEdgeReceiptHistoryTests(_Edges):
 def test_book_receipts_without_teaching_history_reject_restore_and_effects(self):
  # C05-064/066/072/074/075/076/079/083: same forged shapes as the audit probe.
  cases=(('skill',None,lambda:{'source':SKILL.SOURCE,'status':'active','point_cost':1,'rank_before':2,'skill':SK.skill_id(self.r.skill_policy,'육상')},lambda p:SKILL.validate(self.r,p.spec)),
         ('stat',None,lambda:{'source':STAT.ATTACK_CONFLICT,'status':'active','point_cost':1,'stat':'atk'},lambda p:STAT.exemptions(self.r,p.spec)),
         ('accuracy',None,lambda:{'source':MOVE.ACCURACY,'status':'active','point_cost':1,'move_id':'move/메가톤펀치','effect_storage':'derived'},lambda p:MOVE.prepare(self.e,p,self.r.move('move/메가톤펀치'))),
         ('training',None,lambda:{'source':CAP.TRAINING,'status':'active','point_cost':1,'choice':'power','effect_storage':'derived'},lambda p:CAP.bonus(p,'power')),
         ('mobility',None,lambda:{'source':CAP.MOBILITY,'status':'active','point_cost':1,'choice':'land','effect_storage':'derived'},lambda p:M.capabilities(self.e,p)),
         ('ranged','불쏘시개',lambda:{'source':RANGED.SOURCE,'status':'active','point_cost':1,'choice':'불쏘시개','effect_storage':'derived'},lambda p:RANGED.range_for(p,'불쏘시개')),
         ('invisibility','투명',lambda:{'source':INVIS.SOURCE,'status':'active','point_cost':1},INVIS.duration),
         ('tk','염력',lambda:{'source':TK.SOURCE,'status':'active','point_cost':1},TK.bonus))
  for name,capability,receipt,consumer in cases:
   with self.subTest(policy=name):
    self.setUp()
    if capability:self.p.spec['capabilities']=[capability]
    row=receipt();self.p.spec.setdefault('learned_poke_edges',[]).append(row)
    before=self.snap()
    with self.assertRaisesRegex(ValueError,REJECT):consumer(self.p)
    self.assertEqual(before,self.snap())
    self.p.spec['learned_poke_edges'].remove(row)
    self.assert_rejected(row)
 def test_csv_receipts_with_definition_origin_but_no_teaching_history_reject_restore(self):
  # S-pedge-1: CSV poke-edges R2-R22, R30, R32-R46, R48, R49, R52, R56 (R29 below).
  families=[(record,None,lambda row:{'skill':SK.skill_id(self.r.skill_policy,row['choice'] or '육상'),'rank_before':SKILL.skill_pool(self.r,self.p.spec,SK.skill_id(self.r.skill_policy,row['choice'] or '육상'))[0]}) for record in range(2,20)]
  families+=[(record,None,lambda row,stat=stat:{'stat':stat}) for record,stat in ((20,'atk'),(21,'atk'),(22,'spa'))]
  families+=[(30,None,lambda row:{'move_id':'move/메가톤펀치','effect_storage':'derived'})]
  families+=[(record,None,lambda row,choice=choice:{'choice':choice,'effect_storage':'derived'}) for record,choice in
             ((32,'power'),(33,'power'),(34,'high_jump'),(35,'long_jump'),(36,'land'),(37,'land'),(38,'sky'),(39,'swim'),(40,'levitate'),(41,'burrow'),(42,'teleport'))]
  families+=[(record,cap,lambda row,cap=cap:{'choice':cap,'effect_storage':'derived'}) for record,cap in
             ((43,'불쏘시개'),(44,'불쏘시개'),(45,'물줄기'),(46,'냉동고'),(48,'구체화'),(49,'재퍼'))]
  families+=[(56,'염력',lambda row:{})]
  self.base()
  for record,capability,choice in families:
   with self.subTest(record=record):
    self.p.spec['capabilities']=[capability] if capability else []
    row=self.row(record)
    receipt={'source':row['policy'],'status':'active','point_cost':row.get('point_cost',row.get('tutor_cost',1)),'definition_origin':origin(row),**choice(row)}
    V.validate_receipt(self.r,receipt)
    self.assert_rejected(receipt)
  with self.subTest(record=52):
   # R52 has no CSV catalog row; its receipt is the book SOURCE (alias clause).
   self.p.spec['capabilities']=['투명']
   self.assert_rejected({'source':INVIS.SOURCE,'status':'active','point_cost':1})
   # Extended Invisibility now passes the common receipt owner: a foreign CSV origin is refused too.
   self.assert_rejected({'source':INVIS.SOURCE,'status':'active','point_cost':1,'trainer_id':self.a.entity_id,'acquired_level':20,
                         'completed_at':3600,'training_source':ORDINARY,'definition_origin':origin(self.row(41))},'CSV source receipt mismatch')
 def test_each_history_field_is_required_on_actual_receipts_without_mutation(self):
  self.base();self.p.spec['capabilities']=['투명']
  self.teach(self.row(41)['clause_id']);self.teach(STAT.ATTACK_CONFLICT,stat='atk');self.teach(INVIS.SOURCE)
  receipts=self.p.spec['learned_poke_edges']
  self.assertEqual([r['training_source'] for r in receipts],[ORDINARY]*3)
  self.assertNotIn('acquired_level',receipts[1])  # Attack Conflict's producer records no level.
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
  bad=(('trainer_id',None),('trainer_id',''),('trainer_id',7),('completed_at',None),('completed_at',-1),('completed_at',True),
       ('completed_at',1.5),('training_source',None),('training_source','completed training'),('acquired_level',None),
       ('acquired_level',19),('acquired_level',True),('acquired_level',101))
  for index,receipt in enumerate(receipts):
   for field,value in bad:
    if field=='acquired_level' and index==1:continue
    with self.subTest(source=receipt['source'],field=field,value=value):
     original=deepcopy(receipt)
     if value is None:receipt.pop(field)
     else:receipt[field]=value
     before=self.snap()
     self.assertFalse(self.e.validate_state()['valid'])
     self.assertEqual(before,self.snap())
     if value is None:  # native JSON restore boundary for each missing field
      with self.assertRaisesRegex(ValueError,REJECT):self.restored()
     receipt.clear();receipt.update(original)
  loaded=self.restored();self.assertEqual(self.loaded(loaded).spec['learned_poke_edges'],receipts)
 def test_refunded_receipts_keep_actual_history_and_refund_once(self):
  self.base();self.teach(self.row(33)['clause_id']);self.teach(MOVE.ACCURACY,move_id='메가톤펀치')
  self.e.gm.set_level(self.p,19,reason='actual permanent level correction')
  receipts=self.p.spec['learned_poke_edges']
  self.assertEqual(([r['status'] for r in receipts],self.p.spec['tutor_points']),(['refunded','refunded'],8))
  self.assertTrue(all(r['trainer_id']==self.a.entity_id and r['training_source']==ORDINARY and r['acquired_level']==20 for r in receipts))
  loaded=self.restored();self.assertEqual(self.loaded(loaded).spec['learned_poke_edges'],receipts)
  for receipt in receipts:
   with self.subTest(source=receipt['source']):
    original=deepcopy(receipt);receipt.pop('completed_at')
    self.assertFalse(self.e.validate_state()['valid'])
    with self.assertRaisesRegex(ValueError,REJECT):self.restored()
    receipt.clear();receipt.update(original)
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
 def test_ordinary_grooming_and_training_session_sources_are_accepted_and_restored(self):
  self.base();self.p.spec['capabilities']=['투명','염력','불쏘시개']
  self.teach(self.row(41)['clause_id'])
  self.a.spec['edges']=['edge/미용사'];self.a.spec['items']['미용사 킷']=1
  self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True)
  self.teach(INVIS.SOURCE,from_grooming=True);self.teach(STAT.ATTACK_CONFLICT,stat='atk',from_grooming=True)
  self.teach(RANGED.SOURCE,capability='불쏘시개',from_grooming=True)
  other=self.pokemon('근육몬',20,moves=['메가톤펀치'])
  self.e.complete_training_hour(self.a,[other],safe=True,reason='observed safe training ground',request_id='receipt-hour')
  self.teach(MOVE.ACCURACY,target=other,move_id='메가톤펀치',from_training=True)
  self.teach(SKILL.SOURCE,target=other,skill='육상',from_training=True)
  self.teach(TK.SOURCE,target=self.p)
  observed=[(r['source'],r['training_source']) for c in (self.p,other) for r in c.spec['learned_poke_edges']]
  self.assertEqual(observed,[(CAP.MOBILITY,ORDINARY),(INVIS.SOURCE,GROOMING),(STAT.ATTACK_CONFLICT,GROOMING),(RANGED.SOURCE,GROOMING),
                             (TK.SOURCE,ORDINARY),(MOVE.ACCURACY,TRAINING),(SKILL.SOURCE,TRAINING)])
  self.assertEqual(set(V.TRAINING_SOURCES),{ORDINARY,TRAINING,GROOMING})
  self.assertTrue(all(r['trainer_id']==self.a.entity_id and type(r['completed_at']) is int for c in (self.p,other) for r in c.spec['learned_poke_edges']))
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
  loaded=self.restored()
  for actor in (self.p,other):self.assertEqual(self.loaded(loaded,actor).spec['learned_poke_edges'],actor.spec['learned_poke_edges'])
  self.assertEqual((INVIS.duration(self.loaded(loaded)),TK.bonus(self.loaded(loaded)),RANGED.range_for(self.loaded(loaded),'불쏘시개')),(480,2,6))


class AdvancedConnectionReceiptHistoryTests(unittest.TestCase):
 setUpClass=classmethod(_connection.AdvancedConnectionTests.setUpClass.__func__)
 setUp=_connection.AdvancedConnectionTests.setUp
 add=_connection.AdvancedConnectionTests.add
 snap=_connection.AdvancedConnectionTests.snap
 teach=_connection.AdvancedConnectionTests.teach
 restored=_fixture.ProgressionStateTests.restored
 def test_forged_book_and_csv_connection_receipts_reject_and_actual_receipt_restores(self):
  # C05-071 and CSV R29: a Connection slot exemption needs an actual paid teaching hour.
  row=next(x for x in V.catalog(self.r) if x['record']==29);ability=ABILITY.choice(self.r,'기부자')
  for name,receipt in (('book',{'source':CONNECTION.SOURCE,'status':'active','point_cost':1,'ability':ability}),
                       ('csv',{'source':CONNECTION.SOURCE,'status':'active','point_cost':1,'ability':ability,'definition_origin':origin(row)})):
   with self.subTest(receipt=name):
    self.setUp();self.p.spec.setdefault('learned_poke_edges',[]).append(receipt)
    self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(4,0))
    self.assertFalse(self.e.validate_state()['valid'])
    with self.assertRaisesRegex(ValueError,REJECT):self.restored()
  self.setUp();self.teach()
  receipt=self.p.spec['learned_poke_edges'][0]
  self.assertEqual((receipt['trainer_id'],receipt['training_source'],receipt['acquired_level'],receipt['definition_origin']['record']),(self.a.entity_id,ORDINARY,20,29))
  loaded=self.restored();self.assertEqual(next(x for x in loaded.gm.everyone if x.entity_id==self.p.entity_id).spec['learned_poke_edges'],[receipt])
  for field,value in (('training_source','edge/unknown'),('acquired_level',0),('trainer_id',' ')):
   with self.subTest(field=field):
    original=deepcopy(receipt);receipt[field]=value;before=self.snap()
    self.assertFalse(self.e.validate_state()['valid']);self.assertEqual(before,self.snap())
    with self.assertRaisesRegex(ValueError,REJECT):self.restored()
    receipt.clear();receipt.update(original)


class AdvancedMobilityExistingModeTests(_Edges):
 def evolve(self,species,record,target,mode,capability=None):
  self.setUp();self.p=self.pokemon(species,{'데구리':35,'나목령':25}.get(species,20),tp=6)
  before=M.capabilities(self.e,self.p).get(mode,0);self.assertGreater(before,0)
  self.teach(self.row(record)['clause_id'],**({'capability':capability} if capability else {}))
  self.assertEqual(M.capabilities(self.e,self.p)[mode],before+2)
  self.assertTrue(D.evolve_combatant(self.e,self.p,target)['evolved'])
  self.assertEqual(self.p.spec['movement'].get(mode,0),0)
 def test_mode_lost_by_evolution_keeps_dormant_unrefunded_investment(self):
  for species,record,target,mode,capability in (('데구리',41,'딱구리','burrow',None),('나목령',40,'대로트','levitate',None),
                                                ('메리프',36,'보송송','swim','swim'),('메리프',39,'보송송','swim',None),('쪼마리',38,'어지리더','sky',None)):
   with self.subTest(species=species,record=record):
    self.evolve(species,record,target,mode,capability)
    self.assertEqual(M.capabilities(self.e,self.p).get(mode,0),0)
    with self.assertRaisesRegex(ValueError,'not possessed'):self.e.move_profile(self.p,movement_mode=mode)
    receipt=CAP.records(self.p.spec)[0]
    self.assertEqual((receipt['status'],receipt['choice'],self.p.spec['tutor_points']),('active',mode,5))
    self.assertEqual(CAP.amounts(self.r,self.p.spec),{mode:2})
    self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
    if record==41:  # native JSON restore keeps the dormant receipt and the absent mode
     loaded=self.restored();restored=self.loaded(loaded)
     self.assertEqual((M.capabilities(loaded,restored).get(mode,0),restored.spec['learned_poke_edges']),(0,self.p.spec['learned_poke_edges']))
 def test_base_observation_without_mode_is_dormant_and_resumes_when_mode_returns(self):
  raw={**RAW,'sky':0,'levitate':0,'burrow':0}
  self.base(raw);self.teach(self.row(42)['clause_id']);self.assertEqual(M.capabilities(self.e,self.p)['teleport'],4)
  self.base({**raw,'teleport':0})
  self.assertEqual((M.capabilities(self.e,self.p).get('teleport',0),CAP.records(self.p.spec)[0]['status'],self.p.spec['tutor_points']),(0,'active',7))
  evidence=CAP.projection(self.r,self.p.spec,{**raw,'teleport':0});self.assertNotIn('teleport',evidence)
  self.base({**raw,'teleport':3});self.assertEqual(M.capabilities(self.e,self.p)['teleport'],5)
 def test_retained_mode_and_zero_capability_training_still_receive_their_bonus(self):
  self.setUp();self.p=self.pokemon('데구리',35,tp=6);self.teach(self.row(37)['clause_id'])
  self.assertTrue(D.evolve_combatant(self.e,self.p,'딱구리')['evolved'])
  self.assertEqual(M.capabilities(self.e,self.p)['land'],self.p.movement+2)
  self.setUp();self.base({**RAW,'high_jump':0});self.teach(self.row(34)['clause_id'])
  self.assertEqual(J.limits(self.p)['high_jump'],1)
 def test_current_observation_of_dormant_mode_is_accepted_and_contradiction_rejected_atomically(self):
  self.evolve('데구리',41,'딱구리','burrow')
  observed=M.capabilities(self.e,self.p,environment=False)
  self.assertEqual(observed.get('burrow',0),0)
  self.e.gm.set_movement_capabilities(self.p,observed,basis='current',reason='GM copied actual current totals')
  self.assertEqual(M.capabilities(self.e,self.p).get('burrow',0),0)
  for value in (1,2):
   with self.subTest(burrow=value):
    before=self.snap()
    with self.assertRaises(ValueError):
     self.e.gm.set_movement_capabilities(self.p,{**observed,'burrow':value},basis='current',reason='contradictory current total')
    self.assertEqual(before,self.snap())
  self.e.gm.set_movement_capabilities(self.p,{**observed,'burrow':5},basis='current',reason='GM observed restored burrowing')
  self.assertEqual((self.p.spec['movement']['burrow'],M.capabilities(self.e,self.p)['burrow']),(3,5))
 def test_acquisition_without_existing_mode_refuses_before_cost(self):
  self.setUp();self.p=self.pokemon('딱구리',35,tp=6)
  before=self.snap()
  with self.assertRaises(ValueError):self.teach(self.row(41)['clause_id'])
  self.assertEqual(before,self.snap())


if __name__=='__main__':unittest.main()
