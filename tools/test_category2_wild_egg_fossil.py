"""Source-complete category2 wild relationships and egg/fossil lifetime projections.
Only the named tests below run; category3 procedures are not re-certified here.
"""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Combatant
import pokemon_entities as PE
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities
import test_category3_researcher_features as _fixture_test_category3_researcher_features

class Tests(_fixture_test_category3_pokemon_activities.PokemonActivityTests):
 def other(self,name='receiver'):
  t=self.actor(name,'trainer');self.e.gm.everyone.append(t);return t
 def test_six_dispositions_are_observed_per_audience_not_capture_consent(self):
  self.p.spec.pop('disposition');audience='trainer:'+self.a.entity_id
  self.assertFalse(PE.disposition_projection(self.p,audience)['known'])
  before=self.state()
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,fixed=[6]*4)
  self.assertEqual(self.state(),before)
  for category in PE.DISPOSITION_VALUES:
   with self.subTest(category=category):
    self.act('disposition_ruling',target=self.p,disposition=category,reason='GM observed this audience relationship')
    row=PE.disposition_projection(self.p,audience)
    self.assertEqual(row['value'],category);self.assertTrue(row['meaning']);self.assertFalse(row['capture_consent_inferred'])
    self.assertFalse(self.p.captured);self.assertNotIn('trainer_id',self.p.spec)
  self.assertEqual(len(self.p.spec['disposition_history']),6)
  other=self.other();self.assertFalse(PE.disposition_projection(self.p,'trainer:'+other.entity_id)['known'])
  self.e.advance_time(60)
  self.assertEqual(PE.disposition_projection(self.p,audience)['value'],'매우 우호적')
  snapshot=self.e.gm.snapshot();self.act('disposition_ruling',target=self.p,disposition='매우 적대적',reason='GM observed trainer hurting family')
  self.assertEqual(self.p.spec['disposition_history'][-1]['before'],'매우 우호적')
  self.e.gm.restore(snapshot)
  restored=next(c for c in self.e.gm.everyone if c.entity_id==self.p.entity_id)
  self.assertEqual(PE.disposition_projection(restored,audience)['value'],'매우 우호적')
 def test_relation_history_failure_lock_group_identity_and_gm_changed_circumstances(self):
  other=self.other();members=[self.a.entity_id,other.entity_id]
  self.act('disposition_ruling',target=self.p,group_id='party',group_members=members,disposition='중립',reason='GM observes explicit party')
  result=self.act('befriend',target=self.p,group_id='party',fixed=[1]*4)
  self.assertFalse(result['check'].passed);self.assertEqual(self.p.spec['disposition_history'][-1]['after'],'중립')
  for group in (None,'party'):
   before=self.state()
   with self.assertRaises(ValueError):self.act('befriend',target=self.p,group_id=group,fixed=[6]*4)
   self.assertEqual(self.state(),before)
  with self.assertRaises(ValueError):self.act('disposition_ruling',target=self.p,group_id='party',group_members=[self.a.entity_id],disposition='우호적',reason='membership changed')
  self.e.pokemon_activity(other,'befriend',target=self.p,group_id='party',fixed=[3]*4)
  self.assertEqual(PE.disposition_projection(self.p,'group:party')['value'],'우호적')
  self.assertEqual(PE.disposition_projection(self.p,'trainer:'+self.a.entity_id)['value'],'중립')
  self.act('disposition_ruling',target=self.p,disposition='우호적',reason='GM: food and help changed circumstances',allow_retry=True)
  self.assertEqual(self.p.spec['befriend_failures'],[])
  self.assertEqual(self.act('befriend',target=self.p,fixed=[4]*4)['disposition'],'매우 우호적')
  self.assertFalse(self.p.captured)
  self.act('disposition_ruling',target=self.p,disposition='매우 적대적',reason='GM: hurting family immediately worsened disposition')
  self.assertEqual(self.p.spec['disposition_history'][-1]['before'],'매우 우호적')
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
 def test_breeder_and_gm_intervention_produce_distinct_unhatched_egg_entities(self):
  before=self.state()
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='no-edge',phase='check',compatible=True,fixed=[3]*4)
  self.assertEqual(self.state(),before)
  self.test_breeding_checks_after_four_hours_then_egg_after_four_more()
  ordinary=self.a.spec['eggs'][0];self.assertIsNone(ordinary['species']);self.assertIsNone(ordinary['gm_hatch_details'])
  self.a.spec['edges'].remove('edge/브리더')
  gm=self.act('observe_egg',egg_id='divine',reason='GM established an egg in the shrine',parents=[self.p.entity_id,self.q.entity_id])
  self.assertNotEqual(gm['entity_id'],ordinary['entity_id']);self.assertEqual(gm['source'],'gm/egg_intervention')
  self.assertFalse(gm['hatched']);self.assertIsNone(gm['hatch_level'])
  self.assertEqual(gm['parents'],[self.p.entity_id,self.q.entity_id])
  before=self.state()
  for options in ({'egg_id':'divine','reason':'duplicate'}, {'egg_id':'new','reason':'unknown parents','parents':['missing']},{'egg_id':'new','reason':''}):
   with self.assertRaises(ValueError):self.act('observe_egg',**options)
   self.assertEqual(self.state(),before)
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
 def test_native_fossil_observation_supports_all_named_species_and_gm_other_species(self):
  for number,name in enumerate((*PE.STANDARD_FOSSIL_SPECIES,'이상해씨')):
   with self.subTest(species=name):
    result=self.act('fossil',phase='search',site={'name':'GM confirmed deposit','fossils_present':True},dc=15,minutes=1,discovery={'id':str(number),'species':'pokemon/'+name},fixed=[4]*4)
    row=result['fossil'];actual=self.a.spec['fossils'][str(number)]
    self.assertEqual(row['kind'],'fossil');self.assertEqual(row['material'],'calcified_pokemon_remains');self.assertTrue(row['contains_pokemon_dna']);self.assertEqual(row['origin_state'],'long_deceased_pokemon')
    self.assertEqual(row['species_basis'],'standard_fossil' if number<11 else 'GM_nonstandard_fossil')
    self.assertFalse(PE.fossil_projection(self.e,row['entity_id'])['combatant'])
    self.assertIs(PE.fossil_index(self.e)[row['entity_id']][1],actual)
  self.assertEqual(len(PE.fossil_index(self.e)),12)
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
 def test_restoration_tools_owner_transfer_stable_fossil_egg_child_lineage(self):
  for machine in ('복원기','휴대용 복원기'):
   with self.subTest(machine=machine):
    self.setUp();self.own('paleontologist');self.a.spec['items'][machine]=1
    self.a.spec['fossils']={'f1':{'species':'pokemon/암나이트','status':'fossil'}};remains=self.a.spec['fossils']['f1']
    self.act('fossil',phase='restore',fossil_id='f1');egg=self.a.spec['eggs'][0]
    self.assertIs(self.a.spec['fossils']['f1'],remains)
    receiver=self.other();self.e.gm.transfer_egg(self.a,receiver,egg['entity_id'],reason='gift before hatch',request_id=machine)
    self.assertIs(receiver.spec['eggs'][0],egg);self.assertIs(PE.egg_fossil(self.e,egg),remains)
    self.assertEqual(remains['restored_by'],self.a.entity_id)
    details=dict(gender='female',nature='고집',abilities=['깨어진갑옷'],moves=['move/물대포'],special_appearance=True,inheritance_moves=['move/거품'])
    child=self.e.pokemon_activity(receiver,'hatch_fossil',egg_id=egg['id'],name='actual offspring',ready=True,reason='GM confirmed readiness',details=details)['pokemon']
    self.assertEqual(child.level,10);self.assertEqual(child.spec['trainer_id'],receiver.entity_id)
    self.assertEqual(child.spec['fossil_entity_id'],remains['entity_id']);self.assertEqual(child.spec['fossil_egg_entity_id'],egg['entity_id'])
    self.assertEqual(child.spec['gender'],'female');self.assertEqual(child.spec['nature'],'고집');self.assertEqual(child.abilities,['깨어진갑옷'])
    self.assertEqual([m for m in child.spec['moves'] if m!='struggle'],['move/물대포']);self.assertEqual(list(child.moves),['move/물대포','struggle']);self.assertEqual(child.spec['inheritance_moves'],['move/거품']);self.assertTrue(child.spec['special_appearance'])
    self.assertEqual(remains['pokemon_id'],child.entity_id);self.assertEqual(remains['status'],'hatched')
    self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
    before=deepcopy((receiver.spec,self.a.spec))
    with self.assertRaises(ValueError):self.e.pokemon_activity(receiver,'hatch_fossil',egg_id=egg['id'],name='duplicate',ready=True,reason='again',details=details)
    self.assertEqual((receiver.spec,self.a.spec),before)
 def test_fossil_rejects_missing_prerequisite_tool_or_gm_fact_without_transition(self):
  details=self.fossil_egg();egg=self.a.spec['eggs'][0]
  for mutate in (lambda d:d.pop('gender'),lambda d:d.update(nature=None),lambda d:d.update(abilities=['not a sourced ability']),lambda d:d.update(moves=['unknown']),lambda d:d.update(special_appearance=None),lambda d:d.update(inheritance_moves=['unknown'])):
   invalid=deepcopy(details);mutate(invalid);before=self.state()
   with self.assertRaises(ValueError):self.act('hatch_fossil',egg_id=egg['id'],name='child',ready=True,reason='GM readiness',details=invalid)
   self.assertEqual(self.state(),before)
  self.setUp();self.a.spec['fossils']={'f1':{'species':'pokemon/암나이트','status':'fossil'}}
  before=self.state()
  with self.assertRaises(ValueError):self.act('fossil',phase='restore',fossil_id='f1')
  self.assertEqual(self.state(),before)
  self.own('paleontologist');before=self.state()
  with self.assertRaises(ValueError):self.act('fossil',phase='restore',fossil_id='f1')
  self.assertEqual(self.state(),before)
 def test_changed_fossil_lineage_or_hatch_level_is_rejected_by_world_validation(self):
  self.fossil_egg();egg=self.a.spec['eggs'][0];fossil=self.a.spec['fossils']['f1']
  for field,value in (('fossil_entity_id','absent'),('hatch_level',1),('restored_by','other')):
   old=egg[field];egg[field]=value
   self.assertFalse(self.e.validate_state()['valid'])
   egg[field]=old
  fossil['entity_id']=egg['entity_id']
  self.assertFalse(self.e.validate_state()['valid'])
 def test_native_hatch_placement_pending_storage_and_invalid_policy_atomicity(self):
  for mode in ('pending','storage','invalid'):
   with self.subTest(mode=mode):
    self.setUp();details=self.fossil_egg();egg=self.a.spec['eggs'][0]
    if mode!='pending':
     self.act('party_policy',mode='custom',limit=0,roster=[],storage={'kind':'center','id':'center-A'},reason='GM chosen zero carried')
    if mode=='invalid':
     self.a.spec['pokemon_party_policy']['storage']=None;before=self.state();roster=list(self.e.gm.everyone)
     with self.assertRaises(ValueError):self.act('hatch_fossil',egg_id=egg['id'],name='child',ready=True,reason='GM readiness',details=details)
     self.assertEqual(self.state(),before);self.assertEqual(self.e.gm.everyone,roster);continue
    child=self.act('hatch_fossil',egg_id=egg['id'],name='child',ready=True,reason='GM readiness',details=details)['pokemon']
    row=self.a.spec['pokemon_registry'][child.entity_id]
    self.assertEqual(row['location'],mode);self.assertEqual(child.spec['party_location'],dict(row,pokemon_id=child.entity_id))
    self.assertFalse(child.on_field);self.assertEqual(row['egg_entity_id'],egg['entity_id'])
    if mode=='storage':self.assertEqual(row['destination'],{'kind':'center','id':'center-A'})
    else:self.assertIn('not established',row['reason'])
    self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state()['issues'])
 def test_native_state_roundtrip_preserves_wild_history_and_transferred_fossil_lineage(self):
  details=self.fossil_egg();egg=self.a.spec['eggs'][0];receiver=self.other()
  self.e.gm.transfer_egg(self.a,receiver,egg['entity_id'],reason='gift',request_id='roundtrip-gift')
  self.act('disposition_ruling',target=self.p,disposition='적대적',reason='GM observed hostility')
  self.act('befriend',target=self.p,fixed=[1]*4)
  child=self.e.pokemon_activity(receiver,'hatch_fossil',egg_id=egg['id'],name='child',ready=True,reason='GM readiness',details=details)['pokemon']
  expected=PE.egg_projection(self.e,egg['entity_id']);fossil=PE.fossil_projection(self.e,egg['fossil_entity_id'])
  wild=PE.disposition_projection(self.p,'trainer:'+self.a.entity_id)
  loaded=Engine.import_state(self.e.r,self.e.export_state())
  self.assertEqual(PE.egg_projection(loaded,egg['entity_id']),expected)
  self.assertEqual(PE.fossil_projection(loaded,egg['fossil_entity_id']),fossil)
  import world_entities as W
  restored=W.actor_index(loaded)
  self.assertEqual(PE.disposition_projection(restored[self.p.entity_id],'trainer:'+self.a.entity_id),wild)
  self.assertEqual(restored[child.entity_id].spec['fossil_egg_entity_id'],egg['entity_id'])
  self.assertEqual(restored[self.p.entity_id].spec['befriend_failures'],['trainer:'+self.a.entity_id])
  self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state()['issues'])
 def test_relic_crown_requires_original_restorer_and_global_source_after_egg_transfer(self):
  f=_fixture_test_category3_researcher_features.Tests('test_actual_fossil_hatch_crown_production_equipment_and_native_start_end_saves');f.r=self.rules;f.setUp()
  f.t.spec['skills']['포켓몬학']=5
  import researcher_features as RF
  f.t.spec['edges'].append('edge/고생물학자');f.t.spec['items']['복원기']=1;f.t.spec['feats'].extend([RF.FOSSIL_RESTORATION,RF.PREHISTORIC_BOND])
  f.t.spec['fossils']={'f1':{'species':'pokemon/아마루스','status':'fossil'}}
  f.e.pokemon_activity(f.t,'fossil',phase='restore',fossil_id='f1');egg=f.t.spec['eggs'][0]
  spec=deepcopy(f.t.spec);spec.update(id='trainer/new',name='New');spec.pop('fossils');spec.pop('eggs');receiver=Combatant(f.r,spec);f.e.everyone.append(receiver)
  f.e.pokemon_activity(f.t,'party_policy',mode='unlimited',reason='GM carrying policy',roster=[f.p])
  f.e.pokemon_activity(receiver,'party_policy',mode='unlimited',reason='GM carrying policy',roster=[])
  f.e.gm.transfer_egg(f.t,receiver,egg['entity_id'],reason='egg gifted',request_id='gift')
  child=f.e.pokemon_activity(receiver,'hatch_fossil',egg_id=egg['id'],name='child',ready=True,reason='GM readiness',details=dict(gender='female',nature='노력',abilities=['아이스실드'],moves=[],special_appearance=False,inheritance_moves=[]))['pokemon']
  self.assertEqual(child.abilities,['아이스실드'])
  before=f.e.elapsed_seconds
  with self.assertRaisesRegex(ValueError,'this trainer restored'):f.e.craft_relic_crown(receiver,child,minutes=10)
  self.assertEqual(f.e.elapsed_seconds,before);self.assertNotIn('relic_items',receiver.spec)
  # Use the actual party producer to return the child to its original restorer.
  f.e.pokemon_activity(receiver,'party_transfer',target=child,new_owner=f.t,reason='child returned',request_id='return-child')
  record=f.e.craft_relic_crown(f.t,child,minutes=10)
  self.assertEqual(record['fossil_entity_id'],f.t.spec['fossils']['f1']['entity_id'])
  self.assertEqual(record['egg_entity_id'],egg['entity_id'])
  f.e.equip_relic_crown(f.t,child,record['id']);self.assertEqual(child.save_mod,2)
  self.assertTrue(f.e.validate_state()['valid'],f.e.validate_state()['issues'])

if __name__=='__main__':
 names=[name for name in Tests.__dict__ if name.startswith('test_')]
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
 sys.exit(not result.wasSuccessful())
