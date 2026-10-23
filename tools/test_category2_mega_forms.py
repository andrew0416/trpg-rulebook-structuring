"""Actual shared Mega form activation, equipment identities, lifetime and persistence."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import state_grants as G,mega_forms as M,world_entities as W,items as I,equipment_protection as P,equipment_actions as E

class MegaFormTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def add(self,spec):
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c,pos=tuple(spec.get('pos',(1,1))),side=spec.get('side','party'),reason='actual current roster member');return c
 def equip(self,c,uid,item):
  W.register_object(self.e,uid,kind='item_instance',item_rule_id=self.r.item_effects(item)[1]['id'],owner_id=c.entity_id,location={'kind':'unknown'},reason='actual inspected physical equipment')
  I.register_item(self.e,c,item,source_instance_id=uid)
 def setUp(self):
  self.e=Engine(self.r,seed=555)
  self.t=self.add(build_trainer(self.r,'Mega trainer',30,{'hp':20,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},moves=[],abilities=[]))
  self.p=self.add(build_pokemon(self.r,'리자몽',40,moves=['몸통박치기'],abilities=[],extra={'trainer_id':self.t.entity_id},pos=(2,1)))
  self.equip(self.t,'ring','메가링');self.equip(self.p,'stone','리자몽나이트X')
 def turn(self,c):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(c)
 def activate(self,**options):return self.e.mega_evolve(self.t,self.p,'mega/리자몽-x',ring='ring',stone='stone',**options)
 def state(self):return deepcopy(([(c.spec,c.stats,c.abilities,c.types,c.form,c.hp,c.stages,getattr(c,'budget',None),getattr(c,'_item_reg',{})) for c in self.e.gm.everyone],getattr(self.e,'_mega_state',None),self.e._physical_objects,self.e.rng.getstate()))
 def valid(self):self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state())
 def reload(self):
  self.e.gm.restore(self.e.gm.snapshot());ids=(self.t.entity_id,self.p.entity_id)
  self.e=Engine.import_state(Rules(str(ROOT),ruleset='core'),json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)));idx=W.actor_index(self.e);self.t,self.p=(idx[x] for x in ids);self.valid()
 def test_native_catalog_direct_form_adds_stats_types_and_ability_preserving_hp_stages_and_independent_grants(self):
  G._source(self.p,'other:stat','fixture');G.stat(self.p,'atk',3,'other:stat');self.p.stages['atk']=2
  before=deepcopy(self.p.stats);hp=self.p.hp;abilities=list(self.p.abilities);self.turn(self.t);budget=self.t.budget.copy();out=self.activate()
  self.assertEqual(self.p.stats,{k:v+{'atk':5,'def':3,'spa':2}.get(k,0) for k,v in before.items()});self.assertEqual(self.p.types,['불꽃','드래곤']);self.assertEqual(self.p.hp,hp);self.assertEqual(self.p.stages['atk'],2)
  self.assertEqual(self.p.abilities,abilities+['단단한발톱']);self.assertEqual(self.t.budget['swift'],budget['swift']-1);self.assertEqual(self.p.form,'mega/리자몽-x');self.assertEqual(out['actor_id'],self.t.entity_id);self.valid()
 def test_both_actual_turn_owners_pay_their_swift_and_missing_prerequisites_are_atomic(self):
  for who in ('trainer','pokemon'):
   with self.subTest(who=who):
    self.setUp();payer=self.t if who=='trainer' else self.p;other=self.p if who=='trainer' else self.t;self.turn(payer);before=self.state()
    with self.assertRaises(ValueError):self.activate(actor=other)
    self.assertEqual(self.state(),before);self.activate(actor=payer);self.assertEqual(payer.budget['swift'],0);self.valid()
  self.setUp();self.turn(self.t);I.unregister_item(self.e,self.t,'메가링');before=self.state()
  with self.assertRaises(ValueError):self.activate()
  self.assertEqual(self.state(),before)
 def test_duplicate_ability_requires_actual_natural_unowned_choice_and_grants_only_one(self):
  self.e.gm.set_ability(self.p,'단단한발톱',reason='actual original ability already acquired');self.turn(self.p);before=self.state()
  for replacement in (None,'복안','단단한발톱'):
   with self.assertRaises(ValueError):self.activate(replacement_ability=replacement)
   self.assertEqual(self.state(),before)
  self.activate(replacement_ability='맹화');self.assertEqual(self.p.abilities.count('단단한발톱'),1);self.assertIn('맹화',self.p.abilities);self.reload();self.e.end_scene();self.assertIn('단단한발톱',self.p.abilities);self.assertNotIn('맹화',self.p.abilities)
 def test_faint_recall_and_encounter_end_keep_form_then_scene_restores_independent_state(self):
  G._source(self.p,'other:stat','fixture');G.stat(self.p,'atk',3,'other:stat');before=deepcopy(self.p.stats);types=list(self.p.types)
  self.turn(self.t);self.activate();self.e.apply_status(self.p,'기절');self.e.gm.recall(self.p,reason='actual recalled fainted Pokemon');self.e.end_encounter();self.assertEqual(self.p.form,'mega/리자몽-x');self.assertIn('단단한발톱',self.p.abilities)
  self.reload();self.e.end_scene();self.assertEqual(self.p.stats,before);self.assertEqual(self.p.types,types);self.assertNotIn('단단한발톱',self.p.abilities);self.assertNotIn(M.KEY,self.p.spec);self.assertIn('other:stat',self.p.spec[G.KEY]['sources']);self.assertFalse(M.state(self.e)['uses']);self.valid()
 def test_second_sheet_preserves_hp_total_and_independent_modifier_with_different_stat_relations(self):
  base=deepcopy(self.p.spec['stats']);sheet={'hp':16,'atk':23,'def':21,'spa':23,'spd':15,'spe':16}
  G._source(self.p,'other:stat','fixture');G.stat(self.p,'def',2,'other:stat');self.turn(self.p)
  for wrong in (dict(sheet,hp=sheet['hp']+1),dict(sheet,atk=sheet['atk']+1),dict(sheet,**{'def':15,'spd':21}),dict(sheet,atk=12,spa=34)):
   before=self.state()
   with self.assertRaises(ValueError):self.activate(second_sheet=wrong)
   self.assertEqual(self.state(),before)
  self.assertLess(sheet['spd'],sheet['hp'])  # HP preservation is a permitted relation exception.
  self.activate(second_sheet=sheet);self.assertEqual(self.p.stats,dict(sheet,**{'def':sheet['def']+2}));snap=self.e.gm.snapshot();self.p.spec[M.KEY]['second_sheet'].update({'def':15,'spd':21})
  with self.assertRaisesRegex(ValueError,'mega_form_contract'):self.e.export_state()
  self.e.gm.restore(snap);self.reload();self.e.end_scene();self.assertEqual(self.p.stats,dict(base,**{'def':base['def']+2}));self.valid()
 def test_actual_locked_stone_refuses_every_removal_path_but_ring_removal_does_not_end_form(self):
  self.turn(self.t);self.activate();options=I.equipment_options(self.p,('held',));self.assertEqual(len(options),1)
  for operation in ('transfer','exchange','give','drop','disarm','destroy'):self.assertEqual(P.status(self.e,self.p,options[0],operation)['status'],'blocked')
  before=self.state()
  for remove in (lambda:I.unregister_item(self.e,self.p,'리자몽나이트X'),lambda:self.e.gm.set_item(self.p,None,selection='stone',reason='attempted active stone removal')):
   with self.assertRaises(ValueError):remove()
   self.assertEqual(self.state(),before)
  I.unregister_item(self.e,self.t,'메가링');self.assertIn(M.KEY,self.p.spec);self.reload();self.e.end_scene();I.unregister_item(self.e,self.p,'리자몽나이트X');self.assertIsNone(self.p.item)
 def test_trainer_scene_quota_survives_new_ring_and_another_encounter(self):
  second=self.add(build_pokemon(self.r,'리자몽',40,name='same Trainer second Pokemon',moves=[],abilities=[],extra={'trainer_id':self.t.entity_id},pos=(4,1)));self.equip(second,'second-stone','리자몽나이트X')
  self.turn(self.t);self.activate();self.e.end_encounter();I.unregister_item(self.e,self.t,'메가링');self.equip(self.t,'new-ring','메가링');self.turn(self.t);before=self.state()
  with self.assertRaisesRegex(ValueError,'Trainer already'):self.e.mega_evolve(self.t,second,'mega/리자몽-x',ring='new-ring',stone='second-stone')
  self.assertEqual(self.state(),before);second_id=second.entity_id;self.reload();self.e.end_scene();self.turn(self.t);self.e.mega_evolve(self.t,W.actor_index(self.e)[second_id],'mega/리자몽-x',ring='new-ring',stone='second-stone');self.valid()
 def test_custom_definition_generic_stone_binding_and_guidance_are_durable(self):
  for changes in ({'hp':10},{'atk':9}):
   with self.assertRaises(ValueError):self.e.gm.define_mega_form('mega/custom-invalid',base_species='리자몽',stat_changes=changes,ability='복안',reason='actual GM design')
  row=self.e.gm.define_mega_form('mega/custom-charizard',base_species='리자몽',stat_changes={'atk':10},ability='복안',types=['불꽃','페어리'],reason='GM chooses one-stat+10 design;3-4 stats is guidance')
  self.assertEqual(row['stat_changes'],{'atk':10});I.unregister_item(self.e,self.p,'리자몽나이트X');self.equip(self.p,'custom-stone','메가스톤');self.turn(self.t);before=self.state()
  with self.assertRaises(ValueError):self.e.mega_evolve(self.t,self.p,row['id'],ring='ring',stone='custom-stone')
  self.assertEqual(self.state(),before);self.e.gm.bind_mega_stone('custom-stone',row['id'],reason='GM inspected exact custom species and form affinity');self.reload()
  self.e.mega_evolve(self.t,self.p,row['id'],ring='ring',stone='custom-stone');self.assertEqual(self.p.accuracy_stage,3);self.assertEqual(self.p.types,['불꽃','페어리']);self.reload();self.e.end_scene();self.assertEqual(self.p.accuracy_stage,0);self.valid()
 def test_corrupt_source_lifetime_hp_and_ring_graph_reject_before_gm_restore(self):
  self.turn(self.t);self.activate();snap=self.e.gm.snapshot();before=self.state()
  for key,value in [('ends','encounter'),('ability','ability/복안'),('ring_instance','stone')]:
   self.p.spec[M.KEY][key]=value
   with self.assertRaises(ValueError):self.e.export_state()
   self.e.gm.restore(snap);self.assertEqual(self.state(),before)

 def test_native_knock_off_and_magician_cannot_remove_actual_active_stone(self):
  for move,ability in [('탁쳐서떨구기',[]),('몸통박치기',['매지션'])]:
   with self.subTest(move=move):
    self.setUp();enemy=self.add(build_pokemon(self.r,'파오리',30,name='enemy',moves=[move],abilities=ability,wild=True,side='wild',pos=(3,1)))
    self.turn(self.t);self.activate();self.e.end_of_turn(self.t);self.e.start_of_turn(enemy);self.e.rng.seed(0)
    hp_before=self.p.hp;self.e.use_move(enemy,self.p,self.r.move_id(move));self.assertLess(self.p.hp,hp_before);self.assertEqual(enemy.move_uses[self.r.move_id(move)],1);self.assertFalse(E.pending(self.e));self.assertEqual(self.p.item,'리자몽나이트X');self.assertEqual(self.e._physical_objects['stone']['equipped_by'],self.p.entity_id);self.valid()
 def test_one_physical_ring_cannot_support_another_trainers_form_in_same_scene(self):
  other=self.add(build_trainer(self.r,'second Trainer',30,{'hp':20,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},moves=[],abilities=[]))
  second=self.add(build_pokemon(self.r,'리자몽',40,name='second Pokemon',moves=[],abilities=[],extra={'trainer_id':other.entity_id},pos=(4,1)));self.equip(second,'second-stone','리자몽나이트X')
  self.turn(self.t);self.activate();I.transfer_equipment(self.e,self.t,other,I.equipment_options(self.t,('장신구',))[0]['key'],slots=('장신구',))
  I.unregister_item(self.e,other,'메가링');W.register_object(self.e,'ring',kind='item_instance',item_rule_id='item/메가링',owner_id=other.entity_id,location={'kind':'unknown'},reason='actual Ring ownership transferred before wearing');I.register_item(self.e,other,'메가링',source_instance_id='ring');self.turn(other);before=self.state()
  with self.assertRaisesRegex(ValueError,'Ring already'):self.e.mega_evolve(other,second,'mega/리자몽-x',ring='ring',stone='second-stone')
  self.assertEqual(self.state(),before);self.e.end_scene();self.turn(other);self.e.mega_evolve(other,second,'mega/리자몽-x',ring='ring',stone='second-stone');self.valid()
 def test_wrong_specific_stone_form_and_visible_state_corruption_do_not_pass(self):
  I.unregister_item(self.e,self.p,'리자몽나이트X');self.equip(self.p,'wrong-stone','리자몽나이트Y');self.turn(self.t);before=self.state()
  with self.assertRaisesRegex(ValueError,'binding'):self.e.mega_evolve(self.t,self.p,'mega/리자몽-x',ring='ring',stone='wrong-stone')
  self.assertEqual(self.state(),before)
  with self.assertRaises(ValueError):self.e.gm.bind_mega_stone('wrong-stone','mega/리자몽-x',reason='cannot relabel an actual Y stone as X')
  self.setUp();self.turn(self.t);self.activate();snapshot=self.e.gm.snapshot()
  for mutate in (lambda:setattr(self.p,'form','another form'),lambda:self.p.stats.__setitem__('atk',self.p.stats['atk']+1),lambda:self.p.abilities.append('복안')):
   mutate()
   with self.assertRaises(ValueError):self.e.export_state()
   self.e.gm.restore(snapshot)

if __name__=='__main__':unittest.main()
