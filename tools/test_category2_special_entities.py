"""Selected supplemental state invariants; unresolved mechanics stay explicit."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from builder import build_pokemon
import special_entities as S
import world_entities as W

class SpecialTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.poly=Rules(str(ROOT),ruleset='polygon');cls.fantasy=Rules(str(ROOT),ruleset='fantasy');cls.core=Rules(str(ROOT),ruleset='core');cls.allrules=Rules(str(ROOT),ruleset='all')
 def trainer(self,r,uid='trainer'):
  return Combatant(r,{'id':uid,'name':uid,'kind':'trainer','level':5,'stats':dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),'skills':{'오컬트학':4},'moves':['move/잠재파워'],'pos':(1,1)})
 def setUp(self):
  self.e=Engine(self.poly,18);self.a=self.trainer(self.poly);self.e.everyone=self.e.gm.everyone=[self.a]
 def object(self,uid):W.register_object(self.e,uid,location={'kind':'unknown'},reason='GM observed physical object')
 def bot(self,uid='bot'):
  return dict(id=uid,kind='pokebot',location={'kind':'unknown'},size='small',base_stats=dict(hp=6,atk=6,**{'def':5},spa=5,spd=5,spe=5),stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),level=5,hp=40,max_hp=40,injuries=0,types=[],gender=None,owner_id=self.a.entity_id,controller_id=None,complexity=0,components=[],base_body=dict(land=6,power=1,high_jump=0,long_jump=0,weight_class=1),home_gravity=2,gravity_tolerance=3,destroyed=False,skills=dict(athletics=2,combat=2,acrobatics=3,stealth=3,perception=0,focus=0))
 def vehicle(self,uid='vehicle'):
  return dict(id=uid,kind='vehicle',location={'kind':'unknown'},stats={'hp':10,'def':8,'spd':6},hp=60,max_hp=60,breaches=3,patched_breaches=1,breach_security=3,breach_capacity=4,owner_id=self.a.entity_id,driver_id=self.a.entity_id,passenger_ids=[self.a.entity_id],weapon_ids=[],destroyed=False,overland=7,breach_resistance_armor=False)
 def augment(self):
  self.object('implant/1')
  return dict(id='augmentation/1',kind='augmentation_set',location={'kind':'unknown'},actor_id=self.a.entity_id,body_slots=['eyes','limbs','body','skin'],installations=[{'instance_id':'implant/1','augmentation_id':'smart_vision'}],allow_added_parts=False,essence_enabled=False)
 def fantasy_world(self):
  self.e=Engine(self.fantasy,18);self.a=self.trainer(self.fantasy)
  self.u=Combatant(self.fantasy,build_pokemon(self.fantasy,'안농',5,name='source-unown'));self.u.on_field=False
  self.e.everyone=self.e.gm.everyone=[self.a,self.u];self.object('wall')
 def glyph(self):
  return dict(id='glyph',kind='glyph',location={'kind':'abstract','place_id':'wall/north'},creator_id=self.a.entity_id,unown_id=self.u.entity_id,creation_level=5,level=5,hp=5,max_hp=5,status='active',visible=False,channeling=False,flat_surface_id='wall')
 def digital(self,uid='avatar',actor=None):
  actor=actor or self.a;actor.spec['skills']['기술학']=4
  if 'network' not in self.e._physical_objects:self.object('network')
  maximum=actor.level*(2 if actor.kind=='trainer' else 1)+actor.stats['hp']*2+10
  return dict(id=uid,kind='digital_avatar',location={'kind':'abstract','place_id':'network/root'},actor_id=actor.entity_id,network_id='network',integrity=maximum,max_integrity=maximum,temp_integrity=0,status='connected',anchor_id=None,entry_basis='technology',optional_trainer_stats=False,program_ids=[])
 def golem(self):
  self.e=Engine(self.allrules,18);self.a=self.trainer(self.allrules);self.e.everyone=self.e.gm.everyone=[self.a];self.object('scrap')
  return dict(id='golem',kind='animated_golem',location={'kind':'unknown'},creator_id=self.a.entity_id,creation_level=5,stats=dict(hp=1,atk=1,**{'def':1},spa=1,spd=1,spe=0),type='강철',material_id='scrap',hp=13,max_hp=13,created_at=0,destroyed=False)
 def test_digital_integrity_is_separate_from_real_hp_and_location(self):
  row=self.digital();self.a.hp=0;real=self.a.location.copy();out=S.observe(self.e,row,reason='connected state')['state_view']
  self.assertFalse(out['real_hp_zero_ejects']);self.assertEqual(self.a.location,real);self.assertEqual(self.a.hp,0)
  row['integrity']=0
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='cannot retain zero integrity connection')
  row['status']='ejected';S.observe(self.e,row,reason='record ejection');self.assertEqual(self.a.hp,0)
 def test_digital_anchor_capacity_and_disconnected_parent_are_atomic(self):
  parent=self.digital();S.observe(self.e,parent,reason='anchor');child=self.trainer(self.poly,'child');self.e.everyone.append(child)
  row=self.digital('child-avatar',child);row.update(entry_basis='anchor',anchor_id='avatar');S.observe(self.e,row,reason='dependent')
  before=deepcopy(self.e._physical_objects);parent['status']='ejected'
  with self.assertRaises(ValueError):S.observe(self.e,parent,reason='cannot strand connected dependent')
  self.assertEqual(self.e._physical_objects,before)
  row['status']='ejected';S.observe_batch(self.e,[parent,row],reason='linked ejection facts');self.assertTrue(W.validate_world(self.e)['valid'])
 def test_virtuoso_technology_focus_drive_actual_maximum_formula_and_optional_stats(self):
  import skill_modifiers as SKILL,state_grants as GRANTS
  row=self.digital()
  self.e.gm.set_level(self.a,30,reason='actual level30 trainer before Virtuoso acquisitions')
  self.e.gm.set_skill(self.a,'기술학',6,reason='actual Master Technology')
  self.e.gm.set_skill(self.a,'집중',6,reason='actual Master Focus')
  GRANTS.transition(self.e,self.a,lambda e,a:a.spec.update(
   edges=[*a.spec.get('edges',[]),'edge/거장','edge/거장'],
   edge_choices={'edge/거장':['기술학','집중']}))
  for skill in ('기술학','집중'):
   self.assertEqual((SKILL.rank(self.e.r,self.a,skill)[2],SKILL.effective_rank(self.e.r,self.a,skill)),(6,8))
  row.update(integrity=110,max_integrity=110,optional_trainer_stats=True)
  out=S.observe(self.e,row,reason='actual Virtuoso digital maximum and chosen stat option')
  view=out['state_view']
  self.assertEqual(out['entity']['max_integrity'],110)
  self.assertEqual(view['integrity_formula']['hp_multiplier'],[8,2])
  self.assertEqual({key:view['digital_stats'][key] for key in ('atk','spa','def','spd')},
   dict.fromkeys(('atk','spa','def','spd'),24))
  wrong=deepcopy(row);wrong.update(integrity=100,max_integrity=100)
  before=deepcopy(self.e._physical_objects)
  with self.assertRaisesRegex(ValueError,'maximum integrity uses Technology rank'):
   S.observe(self.e,wrong,reason='ordinary rank maximum cannot replace the effective maximum')
  self.assertEqual(self.e._physical_objects,before)
 def test_digital_formula_and_optional_stats_are_sourced(self):
  row=self.digital();row['optional_trainer_stats']=True;out=S.observe(self.e,row,reason='chosen stat option')['state_view'];self.assertEqual(out['digital_stats']['atk'],12)
  row['max_integrity']+=1
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='mistaken HP maximum')
 def test_digital_defense_node_has_own_identity_and_anchor(self):
  self.object('network')
  core=dict(id='core',kind='digital_node',location={'kind':'abstract','place_id':'network'},node_type='server_core',network_id='network',integrity=90,max_integrity=90,status='connected',anchor_id=None,controller_id=self.a.entity_id,defense=8,evasion=2,data_state='intact',bot_id=None)
  wall=dict(core,id='wall',node_type='wall_of_thorns',integrity=25,max_integrity=25,anchor_id='core',data_state='not_applicable')
  S.observe_batch(self.e,[core,wall],reason='actual server defenses');self.assertTrue(S.view(self.e,'wall')['state_view']['only_technology_targetable'])
  core['status']='disabled'
  with self.assertRaises(ValueError):S.observe(self.e,core,reason='linked defense still active')
  wall['status']='disabled';S.observe_batch(self.e,[core,wall],reason='deactivated core defenses')
 def test_golem_has_independent_allocation_and_cannot_heal_or_recreate(self):
  row=self.golem();out=S.observe(self.e,row,reason='existing summoned construct')['state_view'];self.assertFalse(out['healing_allowed']);self.assertEqual(out['struggle_type'],'강철')
  row['hp']=5;S.observe(self.e,row,reason='observed damage');row['hp']=6
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='forbidden healing')
  row['hp']=5;row['created_at']=1;self.e.elapsed_seconds=2
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='cannot reset lifetime')
 def test_native_clock_expires_golem_at_one_day_not_encounter_end(self):
  row=self.golem();S.observe(self.e,row,reason='observed creation');self.e.end_encounter();self.assertFalse(self.e._physical_objects['golem']['destroyed'])
  self.e.advance_time(86399);self.assertFalse(self.e._physical_objects['golem']['destroyed']);self.e.advance_time(1);self.assertTrue(self.e._physical_objects['golem']['destroyed'])
 def test_paired_forms_preserve_two_hp_pools_and_one_active_identity(self):
  self.e=Engine(self.allrules,18);self.a=self.trainer(self.allrules);pokemon=Combatant(self.allrules,build_pokemon(self.allrules,'뮤',1));pokemon.on_field=False;self.e.everyone=self.e.gm.everyone=[self.a,pokemon]
  row=dict(id='being',kind='paired_forms',location={'kind':'unknown'},human_id=self.a.entity_id,pokemon_id=pokemon.entity_id,active_id=self.a.entity_id,sharing_rank=2)
  out=S.observe(self.e,row,reason='actual linked forms')['state_view'];self.assertTrue(out['avatar_has_legendary_types']);self.assertFalse(out['avatar_has_legendary_moves']);self.assertEqual(len(out['hp_by_form']),2)
  pokemon.on_field=True
  with self.assertRaises(ValueError):S.view(self.e,'being')
  pokemon.on_field=False;self.a.hp=0
  with self.assertRaises(ValueError):S.view(self.e,'being')
 def test_native_paired_damage_and_inactive_access_reject_before_mutation(self):
  self.e=Engine(self.allrules,18);self.a=self.trainer(self.allrules);pokemon=Combatant(self.allrules,build_pokemon(self.allrules,'뮤',1));pokemon.on_field=False;self.e.everyone=self.e.gm.everyone=[self.a,pokemon]
  row=dict(id='being',kind='paired_forms',location={'kind':'unknown'},human_id=self.a.entity_id,pokemon_id=pokemon.entity_id,active_id=self.a.entity_id,sharing_rank=0);S.observe(self.e,row,reason='actual linked forms')
  before=(self.a.hp,pokemon.hp,self.a.injuries,pokemon.injuries,self.e.rng.getstate())
  for fn,args in [(self.e.take_damage,(self.a,12)),(self.e.lose_hp,(self.a,12)),(self.e.heal,(pokemon,5)),(self.e.start_of_turn,(pokemon,))]:
   with self.assertRaises(ValueError):fn(*args)
   self.assertEqual((self.a.hp,pokemon.hp,self.a.injuries,pokemon.injuries,self.e.rng.getstate()),before)
 def test_native_golem_heal_is_rejected_before_ordinary_actor_access(self):
  row=self.golem();S.observe(self.e,row,reason='existing golem');actual=self.e._physical_objects['golem'];before=deepcopy(actual)
  with self.assertRaisesRegex(ValueError,'cannot recover HP'):self.e.heal(actual,5)
  self.assertEqual(actual,before)
 def test_core_rejects_polygon_state_without_mutation(self):
  self.e=Engine(self.core,18);self.a=self.trainer(self.core);self.e.everyone=self.e.gm.everyone=[self.a]
  with self.assertRaises(ValueError):S.observe(self.e,self.bot(),reason='not-selected')
  self.assertFalse(self.e._physical_objects)
 def test_bot_is_untyped_despite_magnetic_steel_reference(self):
  out=S.observe(self.e,self.bot(),reason='observed bot')
  self.assertFalse(out['state_view']['stab']);self.assertIn('마비',out['state_view']['condition_immunity']['all_except']);self.assertNotIn('독',out['state_view']['condition_immunity']['all_except'])
  row=self.bot();row['types']=['강철']
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='mistaken type')
  self.assertEqual(self.e._physical_objects['bot']['types'],[])
 def test_bot_base_and_complexity_source_limits_are_distinct(self):
  row=self.bot();row['base_stats']['hp']=7;row['base_stats']['atk']=5
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='exceeds individual cap')
  row=self.bot();self.object('component');row['components']=[{'instance_id':'component','complexity':2,'source':'observed/component-rule'}];row['complexity']=1
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='cost ledger mismatch')
  row['complexity']=2;S.observe(self.e,row,reason='actual component state')
 def test_bot_unranked_skill_and_gravity_range_do_not_use_ordinary_defaults(self):
  out=S.observe(self.e,self.bot(),reason='baseline skill state')
  self.assertEqual(out['state_view']['gravity_range'],[1,3]);self.assertFalse(out['state_view']['ordinary_skill_fallback_allowed'])
  row=self.bot();row['skills']['focus']=1
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='unranked is not default rank one')
  row=self.bot();row['skills']['combat']=3
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='skill pool mismatch')
 def test_bot_engineer_cap_grant_requires_actual_sourced_creator(self):
  self.object('component');row=self.bot();row['components']=[{'instance_id':'component','complexity':8,'source':'observed/component-rule'}];row['complexity']=8
  row['complexity_grant']={'creator_id':self.a.entity_id,'source_id':'feat/실험용-ai'}
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='creator lacks experimental AI')
  self.a.spec['feats']=['feat/실험용-ai'];out=S.observe(self.e,row,reason='actual sourced builder grant')
  self.assertEqual(out['state_view']['complexity_limit'],8)
 def test_ship_corrected_example_uses_46_and_destroyed_side_adds_12(self):
  rows=[]
  for n in range(8):
   row=self.vehicle('section/'+str(n));row.update(breaches=0,patched_breaches=0,breach_capacity=4 if n==7 else 6)
   if n in (0,1,7):row['breach_capacity']+=2;row['breach_resistance_armor']=True
   rows.append(row)
  S.observe_batch(self.e,rows,reason='eight actual sections')
  ship=dict(id='ship',kind='vehicle_sections',location={'kind':'unknown'},section_ids=[x['id'] for x in rows],owner_id=self.a.entity_id)
  out=S.observe(self.e,ship,reason='composite');self.assertEqual(out['state_view']['combined_breach_capacity'],46)
  for n in (0,1,2):rows[n]['breaches']=rows[n]['breach_capacity']
  S.observe_batch(self.e,rows,reason='three disabled sections');self.assertEqual(S.view(self.e,'ship')['state_view']['combined_breaches'],22)
  rows[2]['destroyed']=True;S.observe(self.e,rows[2],reason='side section destroyed')
  view=S.view(self.e,'ship')['state_view'];self.assertEqual(view['combined_breaches'],34);self.assertFalse(view['inoperable'])
 def module(self,uid,module,complexity,choice):
  self.object(uid);return {'instance_id':uid,'module_id':module,'complexity':complexity,'source':'feat/엔지니어','choice':choice}
 def test_bot_material_does_not_forge_intrinsic_type_or_stab(self):
  row=self.bot();row['material']='psionic_alloy';out=S.observe(self.e,row,reason='observed chosen material')['state_view']
  self.assertEqual(out['component_projection']['defense_matchup']['weak'],['악']);self.assertNotIn('mindlock',out['component_projection']['capabilities']);self.assertFalse(out['stab'])
 def test_bot_two_skill_modules_can_grant_formerly_unranked_focus(self):
  row=self.bot();row['components']=[self.module('part/1','advanced_utility',2,{'kind':'skills','ranks':{'perception':3}}),self.module('part/2','advanced_utility',2,{'kind':'skills','ranks':{'focus':2,'perception':1}})];row['complexity']=4
  out=S.observe(self.e,row,reason='actual two utility skill modules')['state_view']['component_projection']
  self.assertEqual(out['skills']['focus'],2);self.assertEqual(out['skills']['perception'],4);self.assertEqual(row['skills']['focus'],0)
  row['components'].append(self.module('part/3','advanced_utility',2,{'kind':'skills','ranks':{'focus':3}}));row['complexity']=6
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='third skill option invalid')
 def test_bot_utility_corrected_options_and_duplicate_choices(self):
  row=self.bot();row['components']=[self.module('part/1','basic_utility',1,'levitate_sky2'),self.module('part/2','basic_utility',1,'stealth_and_silent')];row['complexity']=2
  out=S.observe(self.e,row,reason='sourced missing utility option')['state_view']['component_projection']
  self.assertEqual(out['movement']['sky'],2);self.assertIn('부유',out['abilities']);self.assertIn('stealth',out['capabilities']);self.assertIn('dead_silent',out['capabilities'])
  row['components'].append(self.module('part/3','basic_utility',1,'levitate_sky2'));row['complexity']=3
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='same option twice')
 def test_bot_relative_speed_composition_is_explicit_pending(self):
  row=self.bot();row['components']=[self.module('part/1','basic_utility',1,'movement_plus4'),self.module('part/2','basic_utility',1,'swim_half_land')];row['complexity']=2
  out=S.observe(self.e,row,reason='two relative modifiers')['state_view']['component_projection']
  self.assertEqual(out['movement']['land'],10);self.assertIsNone(out['movement']['swim']);self.assertTrue(out['unresolved'])
 def test_bot_drive_type_and_healing_projection_are_instance_sourced(self):
  row=self.bot();row['components']=[self.module('part/1','sympathetic_drive',2,{'item':'metal_coat','mode':'trait'}),self.module('part/2','sympathetic_drive',2,{'item':'dubious_disc','mode':'trait'})];row['complexity']=4
  out=S.observe(self.e,row,reason='observed source-specific drives')['state_view']['component_projection']
  self.assertEqual(out['effective_types'],['강철']);self.assertTrue(out['organic_healing_allowed']);self.assertEqual(row['types'],[])
  self.assertEqual(out['source_grants'][0]['source_instance_id'],'part/1')
 def test_bot_magnetic_and_repair_module_provenance_survive_independent_removal(self):
  row=self.bot();row['components']=[self.module('part/magnetic','advanced_utility',2,{'kind':'magnetic'}),self.module('part/repair','repair_nanites',2,None)];row['complexity']=4
  out=S.observe(self.e,row,reason='distinct permanent components')['state_view']['component_projection']
  self.assertEqual(out['special_immunities'],['scramble','emp']);self.assertEqual(out['food_buff_access']['uses_per_day'],1);self.assertIn('재생력',out['abilities'])
  row['components']=row['components'][1:];row['complexity']=2;out=S.observe(self.e,row,reason='magnetic component removed')['state_view']['component_projection']
  self.assertNotIn('special_immunities',out);self.assertIn('재생력',out['abilities']);self.assertEqual(out['source_grants'][0]['source_instance_id'],'part/repair')
 def test_bot_destruction_not_organic_death(self):
  row=self.bot();row['hp']=-80
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='threshold')
  row['destroyed']=True;S.observe(self.e,row,reason='destroyed')
  row['destroyed']=False;row['hp']=40
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='ordinary repair cannot undo destroyed identity')
 def test_vehicle_breach_and_patch_views_preserve_maximum_hp(self):
  out=S.observe(self.e,self.vehicle(),reason='observed vehicle')
  view=out['state_view'];self.assertEqual(view['max_hp'],60);self.assertEqual(view['breaches_for_capacity'],3);self.assertEqual(view['breaches_for_protection'],2);self.assertTrue(view['occupants_protected']);self.assertTrue(view['operable'])
  row=self.vehicle();row['breaches']=4
  out=S.observe(self.e,row,reason='one additional observed breach')
  self.assertFalse(out['state_view']['operable']);self.assertEqual(out['state_view']['max_hp'],60)
 def test_vehicle_rejects_fabricated_organic_injuries_or_six_stats(self):
  for extra in ({'injuries':3},{'stats':dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10)}):
   row=self.vehicle();row.update(extra)
   with self.assertRaises(ValueError):S.observe(self.e,row,reason='wrong state kind')
 def test_vehicle_dangling_passenger_and_weapon_reject(self):
  row=self.vehicle();row['passenger_ids']=['missing']
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='unknown passenger')
  row=self.vehicle();row['weapon_ids']=['missing']
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='unknown installed weapon')
 def test_composite_ship_uses_case_corrected_formula_without_combined_hp(self):
  S.observe(self.e,self.vehicle('one'),reason='section one');S.observe(self.e,self.vehicle('two'),reason='section two')
  out=S.observe(self.e,dict(id='ship',kind='vehicle_sections',location={'kind':'unknown'},section_ids=['one','two'],owner_id=self.a.entity_id),reason='linked sections')
  self.assertEqual(out['state_view']['combined_breach_capacity'],5);self.assertIsNone(out['state_view']['combined_max_hp'])
  self.assertEqual(out['state_view']['unresolved'],[])
 def test_augmentation_duplicate_slot_and_missing_part_reject(self):
  row=self.augment();self.object('implant/2');row['installations'].append({'instance_id':'implant/2','augmentation_id':'enhanced_sight'})
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='same slot')
  row=self.augment();row['body_slots'].remove('eyes')
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='body has no eyes')
 def test_selected_added_part_doubles_capacity(self):
  row=self.augment();row['body_slots'].remove('eyes');row['allow_added_parts']=True;row['installations'][0]['added_body_part']=True
  out=S.observe(self.e,row,reason='selected added-body-part option, actual surgery already established')
  self.assertEqual(out['state_view']['used_capacity'],4)
 def test_essence_is_optional_and_cumulative_without_changing_current_hp(self):
  row=self.augment();self.object('implant/2');row['installations'].append({'instance_id':'implant/2','augmentation_id':'wired_reflexes'});before=self.a.hp
  plain=S.observe(self.e,row,reason='no optional essence');self.assertIsNone(plain['state_view']['essence'])
  row['essence_enabled']=True;out=S.observe(self.e,row,reason='explicit optional essence state')
  self.assertEqual(out['state_view']['essence'],5);self.assertEqual(out['state_view']['base_hp_modifier'],-1);self.assertEqual(self.a.hp,before)
  self.assertFalse(out['state_view']['effect_consumers_integrated'])
 def test_efficient_installation_preserves_owner_bound_slot_and_capacity_exception(self):
  row=self.augment();self.object('implant/2');row['installations'].append({'instance_id':'implant/2','augmentation_id':'enhanced_sight'})
  row['capacity_grant']={'owner_id':self.a.entity_id,'source_id':'feat/효율-설치'}
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='feature missing')
  self.a.spec['feats']=['feat/효율-설치'];out=S.observe(self.e,row,reason='actual owner feature')
  self.assertEqual(out['state_view']['capacity_limit'],12);self.assertEqual(out['state_view']['shock_used_capacity'],1)
  self.a.spec['feats']=[];out=S.view(self.e,row['id'])
  self.assertEqual(len(out['entity']['installations']),2);self.assertFalse(out['state_view']['source_owner_available'])
  self.assertIn('C2SPECIAL-CONFLICT-lost-installation-owner',out['state_view']['unresolved'])
 def test_negative_essence_preserves_unresolved_threshold(self):
  row=self.augment();row['essence_enabled']=True
  for n,name in enumerate(('embedded_weaponry','wired_reflexes','thermal_optical_camouflage'),2):
   uid='implant/'+str(n);self.object(uid);row['installations'].append({'instance_id':uid,'augmentation_id':name})
  out=S.observe(self.e,row,reason='optional essence replaces ordinary capacity ceiling')
  self.assertEqual(out['state_view']['essence'],-2);self.assertIsNone(out['state_view']['base_hp_modifier'])
  self.assertIn('C2SPECIAL-CONFLICT-negative-essence',out['state_view']['unresolved'])
 def test_one_physical_augmentation_cannot_be_installed_twice(self):
  row=self.augment();S.observe(self.e,row,reason='installed on first actor')
  other=self.trainer(self.poly,'second');self.e.everyone.append(other);row['id']='augmentation/2';row['actor_id']=other.entity_id
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='duplicate physical instance')
 def test_glyph_has_hp_only_and_visibility_contract(self):
  self.fantasy_world();row=self.glyph();out=S.observe(self.e,row,reason='established glyph')
  self.assertIsNone(out['state_view']['stats'])
  row['channeling']=True
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='invisible channel')
  row['visible']=True;S.observe(self.e,row,reason='visible channel')
  row['stats']={'hp':5}
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='glyph has no ordinary stats')
 def test_glyph_does_not_duplicate_original_unown_participation(self):
  self.fantasy_world();self.u.on_field=True
  with self.assertRaises(ValueError):S.observe(self.e,self.glyph(),reason='source Unown still active')
 def prime(self):
  self.fantasy_world();base=Combatant(self.fantasy,build_pokemon(self.fantasy,'안농',5,name='prime'));self.e.everyone.append(base)
  self.u.moves=['move/잠재파워']
  return dict(id='prime-state',kind='prime_unown',location={'kind':'unknown'},creator_id=self.a.entity_id,actor_id=base.entity_id,joined=[{'member_id':self.u.entity_id,'boosted_stat':'atk','hidden_power_id':'move/잠재파워','damage_class':'physical'}])
 def test_prime_unown_members_are_permanent_and_cannot_become_glyph(self):
  row=self.prime();out=S.observe(self.e,row,reason='actual permanent combination')
  self.assertEqual(out['state_view']['counts_as_pokemon'],1);self.assertEqual(out['state_view']['base_stat_bonuses']['atk'],5)
  with self.assertRaises(ValueError):S.observe(self.e,self.glyph(),reason='joined member cannot become glyph')
  row['joined'][0]['damage_class']='special'
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='permanent move choice cannot be rewritten')
  row['joined']=[]
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='cannot disassemble')
 def test_destroyed_glyph_identity_cannot_reactivate(self):
  self.fantasy_world();row=self.glyph();row['status']='destroyed';S.observe(self.e,row,reason='destroyed')
  row['status']='active'
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='same consumed identity cannot revive')
 def test_glyph_creator_growth_is_explicit_unresolved_not_auto_heal(self):
  # Preserve the historical test ID; U-009 has resolved its former question.
  self.fantasy_world();row=self.glyph();row['hp']=3
  S.observe(self.e,row,reason='established Glyph with observed prior damage')
  self.e.gm.set_level(self.a,6,reason='actual creator growth after Glyph creation')
  out=S.view(self.e,'glyph')
  self.assertEqual(tuple(out['entity'][key] for key in ('creation_level','level','max_hp','hp')),(5,5,5,3))
  self.assertEqual(out['state_view']['unresolved'],[])
 def setup_sentry(self):
  self.fantasy_world();glyph=self.glyph();glyph['status']='sentry'
  actor=Combatant(self.fantasy,build_pokemon(self.fantasy,'안농',5,name='sentry'));actor.moves=['move/잠재파워'];self.e.everyone.append(actor)
  row=dict(id='sentry',kind='sentry',location={'kind':'unknown'},creator_id=self.a.entity_id,actor_id=actor.entity_id,glyph_id='glyph',creation_level=5,hidden_power_id='move/잠재파워',created_at=0,created_in_encounter=False,status='active')
  S.observe_batch(self.e,[glyph,row],reason='actual resolved linked glyph and sentry state');return actor
 def test_incomplete_linked_glyph_observation_is_atomic(self):
  self.fantasy_world();row=self.glyph();row['status']='sentry';before=deepcopy(self.e._physical_objects)
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='missing summoned actor record')
  self.assertEqual(self.e._physical_objects,before)
 def test_sentry_known_time_boundary_ends_linked_actor_and_glyph_once(self):
  actor=self.setup_sentry();self.e.advance_time(299);self.assertEqual(self.e._physical_objects['sentry']['status'],'active')
  self.e.advance_time(1);self.assertEqual(self.e._physical_objects['sentry']['status'],'ended');self.assertFalse(actor.on_field);self.assertEqual(self.e._physical_objects['glyph']['status'],'destroyed')
  self.assertEqual(S.expire_sentries(self.e),[])
 def test_sentry_preflight_is_read_only_and_commit_accepts_saved_plan(self):
  actor=self.setup_sentry();before=deepcopy(self.e._physical_objects);plan=S.preflight_sentries(self.e)
  self.assertEqual(self.e._physical_objects,before);self.assertIs(plan[0][1],actor)
  self.e.elapsed_seconds=300
  self.assertEqual(S.expire_sentries(self.e,prepared=plan),['sentry'])
  self.assertEqual(S.expire_sentries(self.e,prepared=plan),[])
 def test_sentry_invalid_link_preflight_preserves_clock_and_entities(self):
  self.setup_sentry();self.e._physical_objects['glyph']['visible']='bad';before=deepcopy(self.e._physical_objects)
  with self.assertRaises(ValueError):self.e.advance_time(300)
  self.assertEqual(self.e.elapsed_seconds,0);self.assertEqual(self.e._physical_objects,before)
  with self.assertRaises(ValueError):self.e.end_encounter()
  self.assertEqual(self.e._physical_objects,before)
 def test_malformed_observation_batch_rejects_without_mutation(self):
  with self.assertRaises(ValueError):S.observe_batch(self.e,[None],reason='malformed')
  self.assertFalse(self.e._physical_objects)
 def test_sentry_encounter_end_and_one_active_per_creator(self):
  actor=self.setup_sentry();row=deepcopy(self.e._physical_objects['sentry']);row['id']='second-sentry'
  with self.assertRaises(ValueError):S.observe(self.e,row,reason='another simultaneous activation')
  self.e.end_encounter();self.assertEqual(self.e._physical_objects['sentry']['status'],'ended');self.assertFalse(actor.on_field)
 def test_existing_special_entity_identity_and_snapshot_survive(self):
  S.observe(self.e,self.vehicle(),reason='initial');instance=self.e._physical_objects['vehicle'];self.a.custom_conditions['vehicle_ref']=instance
  row=self.vehicle();row['hp']=40;S.observe(self.e,row,reason='updated observation')
  self.assertIs(self.a.custom_conditions['vehicle_ref'],instance);self.assertEqual(instance['hp'],40)
  self.e.gm.snapshot('special');instance['hp']=1;self.e.gm.restore('special')
  self.assertIs(self.a.custom_conditions['vehicle_ref'],self.e._physical_objects['vehicle']);self.assertEqual(S.view(self.e,'vehicle')['entity']['hp'],40)
 def test_world_validator_checks_special_contract(self):
  S.observe(self.e,self.vehicle(),reason='valid');self.e._physical_objects['vehicle']['patched_breaches']=99
  self.assertIn('special_entity_state',{x['code'] for x in W.validate_world(self.e)['issues']})

if __name__=='__main__':unittest.main()
