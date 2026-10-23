"""Authored relation conditions consume actual ownership/control and native transfers."""
from copy import copy, deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules, Engine, Combatant
import pokemon_party as PARTY
import world_entities as WORLD


class PolicyRelationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT, ruleset='core')
 def setUp(self):
  self.engine=Engine(self.rules,seed=713)
  def actor(uid,kind='trainer'):
   return Combatant(self.rules,{'id':uid,'name':uid,'kind':kind,'level':5,
    'stats':{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},
    'moves':[],'abilities':[],'skills':{},'movement':{'land':5}})
  self.owner=actor('trainer/owner');self.other=actor('trainer/other')
  self.pokemon=actor('pokemon/owned','pokemon')
  self.pokemon.spec['trainer_id']=self.owner.entity_id
  self.engine.everyone=self.engine.gm.everyone=[self.owner,self.other,self.pokemon]
  source=self.rules.selection.units['combat/struggle']['source']['file']
  self.row={'rule_id':'combat/struggle',
    'source':{'file':'input/'+source,'sha256':sha256((ROOT/'input'/source).read_bytes()).hexdigest()},
    'inputs':{},'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}
  self.document={'schema':1,'id':'authored/relation-witness','variants':[self.row]}
 def bind(self,key,subject,field):
  self.row['inputs'][key]={'type':'string','authority':'state',
    'question':'Actual '+field,'binding':{'subject':subject,'field':field}}
 def owner_condition(self):
  self.bind('caller','actor','entity_id');self.bind('owner','target','owner_id')
  self.bind('kind','target','kind')
  self.row['when']={'all':[{'op':'eq','left':{'$input':'caller'},'right':{'$input':'owner'}},
                          {'op':'eq','left':{'$input':'kind'},'right':'pokemon'}]}
 def execute(self,actor=None):
  return self.engine.execute_source_policy_effects(actor or self.owner,self.pokemon,self.document)
 def test_world_clock_condition_reads_committed_time_and_distinct_boundaries(self):
  import source_policy_state as STATE
  for field,kind in STATE.WORLD_FIELDS.items():
   if field not in ('elapsed_seconds','round_no','encounter_active'):continue
   self.bind(field,'world',field);self.row['inputs'][field]['type']=kind
  self.row['when']={'op':'ge','left':{'$input':'elapsed_seconds'},'right':17}
  self.assertEqual(self.execute()['status'],'PolicyNotApplicable')
  self.assertEqual(self.owner.stages['atk'],0)
  self.engine.advance_time(17)
  result=self.execute()
  self.assertEqual(self.owner.stages['atk'],1)
  self.assertEqual(result['input_values']['elapsed_seconds'],17)
  self.assertEqual(result['input_values']['round_no'],0)
  self.assertFalse(result['input_values']['encounter_active'])
  self.engine.start_round(self.engine.everyone)
  facts=STATE.read(self.engine,self.owner,self.pokemon,self.row['inputs'])
  self.assertEqual((facts['elapsed_seconds'],facts['round_no'],facts['encounter_active']),(17,1,True))

 def test_world_clock_binding_rejects_actor_alias_or_arbitrary_path(self):
  import source_policy_state as STATE
  for subject,field,kind in [('actor','elapsed_seconds','integer'),('world','level','integer'),('world','__dict__','string')]:
   with self.assertRaises(ValueError):
    STATE.validate({'type':kind,'binding':{'subject':subject,'field':field}})

 def test_native_identity_query_and_external_binding_share_actual_relations(self):
  self.owner_condition()
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'actor','id':self.other.entity_id},reason='temporary controller')
  self.bind('controller','target','controller_id')
  self.bind('controller_kind','target','controller_kind')
  before=(deepcopy(self.pokemon.spec),self.engine.rng.getstate())
  facts=self.engine.actor_identity(self.pokemon.entity_id)
  self.assertEqual(facts,{'entity_id':self.pokemon.entity_id,'kind':'pokemon',
      'owner_id':self.owner.entity_id,'controller_kind':'actor','controller_id':self.other.entity_id})
  self.assertEqual(before,(self.pokemon.spec,self.engine.rng.getstate()))
  result=self.execute()
  for key,field in [('owner','owner_id'),('kind','kind'),('controller','controller_id'),('controller_kind','controller_kind')]:
   self.assertEqual(result['input_values'][key],facts[field])
  facts['owner_id']='caller-edited'
  self.assertEqual(self.engine.actor_identity(self.pokemon.entity_id)['owner_id'],self.owner.entity_id)

 def test_noncombat_gm_pokemon_and_player_trainer_control_feed_actual_external_policy(self):
  source='input/ch06-gameplay.md:157'
  self.assertFalse(self.engine.encounter_active)
  original=(self.pokemon.spec['trainer_id'],self.pokemon.side,self.pokemon.on_field,
            self.owner.side,self.engine.rng.getstate())
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'gm'},reason='table adopts ordinary noncombat Pokemon control',source=source)
  WORLD.set_controller(self.engine,self.owner,{'kind':'player','id':'player/owner'},reason='player controls their trainer',source=source)
  self.bind('pokemon_control','target','controller_kind')
  self.bind('trainer_control','actor','controller_kind');self.bind('player','actor','controller_id')
  self.row['when']={'all':[
    {'op':'eq','left':{'$input':'pokemon_control'},'right':'gm'},
    {'op':'eq','left':{'$input':'trainer_control'},'right':'player'},
    {'op':'eq','left':{'$input':'player'},'right':'player/owner'}]}
  result=self.execute()
  self.assertEqual(result['input_values'],{'pokemon_control':'gm','trainer_control':'player','player':'player/owner'})
  self.assertEqual(self.owner.stages['atk'],1)
  self.assertEqual(self.engine.actor_identity(self.pokemon.entity_id)['controller_kind'],'gm')
  self.assertIsNone(self.engine.actor_identity(self.pokemon.entity_id)['controller_id'])
  self.assertEqual(original,(self.pokemon.spec['trainer_id'],self.pokemon.side,self.pokemon.on_field,
                             self.owner.side,self.engine.rng.getstate()))
  self.assertFalse(hasattr(self.owner,'budget'));self.assertFalse(hasattr(self.pokemon,'budget'))
  # An explicit table exception changes control, not ownership or the trainer.
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'player','id':'player/owner'},reason='table allows direct noncombat Pokemon play',source=source)
  result=self.execute();self.assertEqual(result['status'],'PolicyNotApplicable')
  self.assertEqual(self.owner.stages['atk'],1)
  self.assertEqual(self.engine.actor_identity(self.pokemon.entity_id)['owner_id'],self.owner.entity_id)
  self.assertEqual(self.engine.actor_identity(self.owner.entity_id)['controller_kind'],'player')

 def test_noncombat_controller_state_and_native_policy_survive_both_restore_paths(self):
  import json
  import state_codec as CODEC
  for actor,control in [(self.owner,{'kind':'player','id':'player/owner'}),(self.pokemon,{'kind':'gm'})]:
   WORLD.set_controller(self.engine,actor,control,reason='ordinary table control',source='input/ch06-gameplay.md:157')
  self.bind('control','target','controller_kind')
  self.row['when']={'op':'eq','left':{'$input':'control'},'right':'gm'}
  snapshot=self.engine.gm.snapshot('noncombat-control')
  restored=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.engine),ensure_ascii=False)))
  index=WORLD.actor_index(restored);owner=index[self.owner.entity_id];pokemon=index[self.pokemon.entity_id]
  self.assertIsNone(restored.actor_identity(pokemon.entity_id)['controller_id'])
  result=restored.execute_source_policy_effects(owner,pokemon,self.document)
  self.assertEqual(result['input_values']['control'],'gm');self.assertEqual(owner.stages['atk'],1)
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'actor','id':self.other.entity_id},reason='temporary explicit control')
  self.assertEqual(self.execute()['status'],'PolicyNotApplicable')
  self.engine.gm.restore(snapshot)
  result=self.execute();self.assertEqual(result['input_values']['control'],'gm')
  self.assertEqual(self.owner.stages['atk'],1)
  self.assertEqual(self.engine.actor_identity(self.owner.entity_id)['controller_id'],'player/owner')
  self.assertTrue(WORLD.validate_world(self.engine)['valid']);self.assertTrue(WORLD.validate_world(restored)['valid'])

 def test_identity_query_rejects_fake_or_duplicate_ids_and_keeps_aliases(self):
  with self.assertRaisesRegex(ValueError,'unknown actor identity'):
   self.engine.actor_identity('pokemon/not-registered')
  self.engine.everyone.append(self.pokemon)
  self.assertEqual(self.engine.actor_identity(self.pokemon.entity_id)['entity_id'],self.pokemon.entity_id)
  duplicate=Combatant(self.rules,deepcopy(self.pokemon.spec))
  self.engine.everyone.append(duplicate)
  with self.assertRaisesRegex(ValueError,'distinct actors share identity'):
   self.engine.actor_identity(self.pokemon.entity_id)

 def test_physical_identity_is_detached_and_kind_checked(self):
  WORLD.register_object(self.engine,'object/tool',location={'kind':'unknown'},reason='observed tool',owner_id=self.owner.entity_id)
  actual=self.engine._physical_objects['object/tool']
  facts=self.engine.entity_identity('object/tool',kind='physical_object')
  self.assertEqual(facts['owner_id'],self.owner.entity_id)
  self.assertIsNone(facts['controller_id'])
  facts['component_ids'].append('fake')
  self.assertNotIn('components',actual)
  with self.assertRaisesRegex(ValueError,'kind does not match'):
   self.engine.entity_identity('object/tool',kind='pokemon')
  actual['owner_id']='absent'
  with self.assertRaisesRegex(ValueError,'actual actor'):
   self.engine.entity_identity('object/tool')

 def test_partial_body_and_parts_resolve_without_fabricating_stats(self):
  import partial_entities as PART
  body=PART.observe(self.engine,name='body',actor_kind='pokemon',entity_id='partial/body',reason='observed body')
  part=PART.observe(self.engine,name='seal',actor_kind='object',entity_id='partial/seal',parent_id=body['entity_id'],known={'hp':3},reason='observed part')
  self.assertEqual(self.engine.entity_identity(body['entity_id'])['weak_part_ids'],[part['entity_id']])
  facts=self.engine.entity_identity(part['entity_id'],kind='weak_part')
  self.assertEqual(facts['parent_id'],body['entity_id'])
  self.assertIsNone(facts['owner_id'])
  self.assertNotIn('stats',self.engine._partial_entities[body['entity_id']]['known'])
  restored=Engine.import_state(self.rules,self.engine.export_state())
  self.assertEqual(restored.entity_identity(part['entity_id']),facts)
  self.engine._partial_entities[part['entity_id']]['parent_id']='absent'
  with self.assertRaisesRegex(ValueError,'actual body'):
   self.engine.entity_identity(part['entity_id'])

 def test_common_index_rejects_cross_store_collisions_and_missing_components(self):
  WORLD.register_object(self.engine,'object/component',location={'kind':'unknown'},reason='observed component')
  WORLD.register_object(self.engine,'object/body',location={'kind':'unknown'},reason='observed body')
  row=self.engine._physical_objects['object/body']
  row['components']=[{'instance_id':'object/component'}]
  self.assertEqual(self.engine.entity_identity('object/body')['component_ids'],['object/component'])
  row['components']=[{'instance_id':'missing'}]
  with self.assertRaisesRegex(ValueError,'distinct actual entity'):
   self.engine.entity_identity('object/body')
  row['components']=[{'instance_id':'object/component'}]
  self.engine._physical_objects['object/component']['section_ids']=['object/body']
  with self.assertRaisesRegex(ValueError,'cycle'):
   self.engine.entity_identity('object/body')
  self.engine._physical_objects['object/component'].pop('section_ids')
  row['components']=[]
  row['installations']=[{'instance_id':'object/component'}]
  self.assertEqual(self.engine.entity_identity('object/body')['component_ids'],['object/component'])
  self.engine._physical_objects[self.owner.entity_id]={'id':self.owner.entity_id,'kind':'physical_object'}
  with self.assertRaisesRegex(ValueError,'collides'):
   self.engine.entity_identity(self.owner.entity_id)

 def test_external_definition_binds_actual_object_before_effect_execution(self):
  WORLD.register_object(self.engine,'object/key',location={'kind':'unknown'},reason='observed key',owner_id=self.owner.entity_id)
  self.bind('caller','actor','entity_id')
  self.row['inputs']['object_owner']={'type':'string','authority':'state','question':'Actual object owner',
      'binding':{'subject':'entity','entity_id':'object/key','field':'owner_id'}}
  self.row['when']={'op':'eq','left':{'$input':'caller'},'right':{'$input':'object_owner'}}
  self.assertEqual(self.execute()['status'],'PolicyEffectsCompleted')
  self.assertEqual(self.execute(self.other)['status'],'PolicyNotApplicable')
  before=(deepcopy(self.owner.spec),deepcopy(self.owner.stages),self.engine.rng.getstate())
  self.row['inputs']['object_owner']['binding']['entity_id']='missing'
  with self.assertRaisesRegex(ValueError,'unknown entity'):
   self.execute()
  self.assertEqual(before,(self.owner.spec,self.owner.stages,self.engine.rng.getstate()))

 def test_external_lifecycle_inputs_distinguish_terminal_and_temporary_states(self):
  WORLD.register_object(self.engine,'object/lifecycle',location={'kind':'unknown'},reason='observed')
  obj=self.engine._physical_objects['object/lifecycle'];obj.update(disabled=True,suppressed=True,destroyed=False)
  for field in ('consumed','destroyed','disabled','suppressed'):
   self.row['inputs'][field]={'type':'boolean','authority':'state','question':'Actual '+field,
       'binding':{'subject':'entity','entity_id':'object/lifecycle','field':field}}
  self.row['when']={'not':{'$input':'destroyed'}}
  result=self.execute()
  self.assertEqual(result['input_values'],{'consumed':False,'destroyed':False,'disabled':True,'suppressed':True})
  WORLD.finish_physical_use(self.engine,obj,'destroyed',{'source':'explicit destruction','former_holder_id':self.owner.entity_id})
  before=self.owner.stages['atk']
  self.assertEqual(self.execute()['status'],'PolicyNotApplicable')
  self.assertEqual(self.owner.stages['atk'],before)
  for spec in self.row['inputs'].values():spec['binding']['entity_id']=self.owner.entity_id
  result=self.execute()
  self.assertEqual(result['status'],'PolicyInputsRequired')
  self.assertEqual(len(result['obligations']),4)

 def test_owner_condition_follows_native_transfer_not_controller(self):
  self.owner_condition()
  PARTY.configure(self.engine,self.owner,mode='standard',reason='native owner roster',
    roster=[self.pokemon],storage={'kind':'center','id':'center/one'})
  PARTY.configure(self.engine,self.other,mode='standard',reason='recipient roster',
    roster=[],storage={'kind':'center','id':'center/two'})
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'actor','id':self.other.entity_id},reason='temporary control')
  self.assertEqual(self.execute(self.other)['status'],'PolicyNotApplicable')
  before=self.owner.stages['atk']
  result=self.execute()
  self.assertEqual(self.owner.stages['atk'],before+1)
  record=self.engine.source_policy_execution(result['execution_id'])
  self.assertEqual(record['input_values']['owner'],self.owner.entity_id)
  PARTY.transfer(self.engine,self.owner,target=self.pokemon,new_owner=self.other,
    reason='actual trade',request_id='relations/trade')
  self.assertEqual(self.execute()['status'],'PolicyNotApplicable')
  self.assertEqual(self.execute(self.other)['status'],'PolicyEffectsCompleted')
  self.assertEqual(self.engine.source_policy_execution(result['execution_id']),record)
  self.assertEqual(self.pokemon.spec['controller']['id'],self.other.entity_id)
 def test_controller_namespace_is_explicit_and_does_not_change_ownership(self):
  self.bind('caller','actor','entity_id');self.bind('controller','target','controller_id')
  self.bind('controller_kind','target','controller_kind')
  self.row['when']={'all':[{'op':'eq','left':{'$input':'controller_kind'},'right':'actor'},
                          {'op':'eq','left':{'$input':'controller'},'right':{'$input':'caller'}}]}
  self.other.budget={'standard':1,'shift':1,'swift':1}
  before=(self.pokemon.spec['trainer_id'],self.pokemon.side,deepcopy(self.other.budget))
  for kind,expected in [('player','PolicyNotApplicable'),('actor','PolicyEffectsCompleted'),('pending','PolicyNotApplicable')]:
   WORLD.set_controller(self.engine,self.pokemon,{'kind':kind,'id':self.other.entity_id},reason='explicit namespace')
   result=self.execute(self.other)
   self.assertEqual(result['status'],expected)
   if kind=='pending':self.assertNotIn('controller',result['input_values'])
   self.assertEqual((self.pokemon.spec['trainer_id'],self.pokemon.side,self.other.budget),before)
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'gm'},reason='GM-controlled')
  self.assertEqual(self.execute()['input_values']['controller_kind'],'gm')
 def test_unknown_and_invalid_relations_never_supply_authority_or_spend(self):
  self.owner_condition()
  self.engine.encounter_active=True;self.engine.round_start_seconds=0
  self.engine._active_turn_actor=self.owner
  self.owner.budget={'standard':1,'shift':1,'swift':1};self.owner._turn_start_decisions_pending=False
  self.row['values'].update(action='standard',ap={'amount':1,'mode':'spend'})
  def execute():return self.engine.execute_source_policy_action(self.owner,self.pokemon,self.document)
  def snapshot():return (deepcopy(self.owner.__dict__,{id(self.rules):self.rules}),self.engine.rng.getstate(),list(self.engine.log_lines))
  self.pokemon.spec.pop('trainer_id');before=snapshot()
  missing=execute()
  self.assertEqual(missing['status'],'PolicyInputsRequired')
  self.assertEqual(missing['obligations'][0]['input'],'owner')
  self.assertEqual(snapshot(),before)
  for uid in ['missing',self.pokemon.entity_id,[],True,'']:
   self.pokemon.spec['trainer_id']=uid
   with self.subTest(owner=uid),self.assertRaises(ValueError):execute()
   self.assertEqual(snapshot(),before)
  self.pokemon.spec['trainer_id']=self.owner.entity_id
  self.bind('control','target','controller_id')
  for relation in [{'kind':'actor','id':'missing'},{'kind':'player'},'actor',{'kind':'other','id':'x'}]:
   self.pokemon.spec['controller']=relation
   with self.subTest(controller=relation),self.assertRaises(ValueError):execute()
   self.assertEqual(snapshot(),before)
  self.pokemon.spec['controller']={'kind':'pending','id':self.owner.entity_id}
  self.assertEqual(execute()['status'],'PolicyInputsRequired')
  self.assertEqual(snapshot(),before)
  self.assertFalse(getattr(self.engine,'_source_policy_executions',{}))
 def test_relations_survive_restore_and_are_rechecked_against_actual_world(self):
  from state_codec import dump_engine,load_engine
  self.owner_condition()
  WORLD.set_controller(self.engine,self.pokemon,{'kind':'actor','id':self.other.entity_id},reason='observed control')
  self.bind('control','target','controller_id')
  saved=dump_engine(self.engine)
  restored=load_engine(self.rules,saved);index=WORLD.actor_index(restored)
  owner=index[self.owner.entity_id];pokemon=index[self.pokemon.entity_id]
  result=restored.execute_source_policy_effects(owner,pokemon,self.document)
  self.assertEqual(result['status'],'PolicyEffectsCompleted')
  self.assertEqual(result['input_values']['owner'],owner.entity_id)
  self.assertEqual(result['input_values']['control'],self.other.entity_id)
  # An actual owner reference with a foreign Rules binding cannot authorize execution.
  owner.r=copy(owner.r)
  with self.assertRaisesRegex(ValueError,'actual trainer'):
   restored.execute_source_policy_effects(index[self.other.entity_id],pokemon,self.document)

if __name__=='__main__':unittest.main()
