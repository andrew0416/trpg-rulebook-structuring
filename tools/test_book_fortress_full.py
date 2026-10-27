"""Every Fortress source obligation; prepared together before first game run."""
from pathlib import Path
import sys,unittest,json
from copy import deepcopy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine
from fortress_fixture import FortressFixture
import fortress as F,trainer_feature_acquisition as T,acquired_features as AC
import state_grants as G,state_fields as SF,combat_timing as TIME,action_points as AP
import acquired_feature_projections as PROJ,items,turn,frequency as Q,weapon_actions as WA


class FortressFullTests(FortressFixture,unittest.TestCase):
 def test_all_seven_actual_acquisitions_one_class_seven_tags_and_codec(self):
  for edition in ('supplement','local_csv'):
   self.scene(features=tuple(F.FEATURES),edition=edition)
   self.assertEqual(len(F.records(self.a)),7);self.assertEqual(len(AC.class_instances(self.a)),1)
   self.assertEqual(self.a.stats['def'],self.initial_def+7)
   self.assertIn(PROJ._ability(self.rules,'애널라이즈')[1],self.a.abilities)
   self.assertIn('절제력',self.a.abilities)
   for name in ('철벽','방어'):self.assertIn(self.rules.move_id(name),self.a.moves)
   for feature in F.FEATURES:
    row=F.acquired(self.a,feature);self.assertEqual(row['snapshot']['source'],F.source(self.rules,feature,edition))
    before=self.e.export_state();self.acquire(feature);self.assertEqual(self.e.export_state(),before)
   self.assertEqual(F.acquired(self.a,F.GUARDIAN)['snapshot']['selection']['mark_scope'],'korean_own_mark')
   self.valid();self.restore();self.valid()
   self.scene(features=(F.CLASS,),edition=edition)
   default=lambda:T.acquire_static(self.e,self.a,F.GUARDIAN,acquisition_request_id='guardian/default-scope',selection={'edition':edition})
   default();before=self.e.export_state();default();self.assertEqual(self.e.export_state(),before)
   self.assertEqual(F.acquired(self.a,F.GUARDIAN)['snapshot']['selection']['mark_scope'],'korean_own_mark')

 def test_class_is_not_automatic_features_and_raw_names_have_no_authority(self):
  self.scene(features=(F.CLASS,));self.assertEqual([r['feature_id'] for r in F.records(self.a)],[F.CLASS])
  self.assertFalse(F.acquired(self.a,F.BASTION));self.assertNotIn(self.rules.move_id('철벽'),self.a.moves)
  self.rejected(lambda:self.e.sustain_fortress(self.a,request_id='missing',skill='집중'),'actual')
  self.scene();self.a.spec['feats']=list(F.FEATURES)
  self.assertIsNone(F.acquired(self.a))
  # Deliberately corrupt imported names cannot be exported as a valid fixture.
  before=deepcopy(self.a.spec)
  with self.assertRaisesRegex(ValueError,'actual'):self.e.sustain_fortress(self.a,request_id='raw',skill='집중')
  self.assertEqual(self.a.spec,before)

 def test_prerequisites_and_four_class_limit_use_native_acquisition(self):
  self.scene(combat=2);self.rejected(lambda:self.acquire(),'prerequisite|rank')
  SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],전투=3,집중=3)},reason='actual Novice prerequisites')
  self.acquire();self.rejected(lambda:self.acquire(F.IRON),'rank')
  SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],전투=4)},reason='actual Adept Combat')
  self.acquire(F.IRON);self.rejected(lambda:self.acquire(F.GUARDIAN),'rank')
  for feature,selection in (('class/닌자',None),('class/오컬트마니아',{'ability':'ability/징조'}),('class/멘토',{'source':'local_translation','skills':['직감','협박'],'tutoring_policy':'kr_errata'})):
   SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],협박=5)},reason='actual additional acquired prerequisite')
   T.acquire_static(self.e,self.a,feature,acquisition_request_id='four/'+feature,selection=selection)
  self.assertEqual(len(AC.class_instances(self.a)),4)
  self.rejected(lambda:T.acquire_static(self.e,self.a,'class/기록자',acquisition_request_id='fifth'),'four slots')

 def test_ability_aliases_exact_consumers_and_independent_source_withdrawal(self):
  for value in ('전투무장','배틀무장','Battle Armor','ability/조가비갑옷-전투무장'):
   self.scene();self.acquire(F.SLOW,ability=value)
   self.assertEqual(F.acquired(self.a,F.SLOW)['snapshot']['selection']['ability'],'전투무장')
   title=PROJ._ability(self.rules,'전투무장')[1];self.assertIn(title,self.a.abilities)
   self.acquire(F.WILL);self.withdraw(F.WILL);self.assertNotIn('절제력',self.a.abilities)
   G.grant(self.a,'abilities',title,'gm/independent-battle-armor','gm',rule_id='gm/actual',owner_id=self.a.entity_id)
   self.withdraw(F.SLOW);self.assertIn(title,self.a.abilities)
   self.valid();self.restore();self.valid()

 def test_mark_actual_missed_struggle_end_turn_not_hit_and_owner_expiry(self):
  for edition in ('supplement','local_csv'):
   self.scene(features=(F.CLASS,),edition=edition);self.combat();self.mark(roll=1)
   self.assertIs(F.marker(self.e,self.b)['ace_marker'],self.a)
   self.assertEqual(F.accuracy(self.e,self.b,self.a),0)
   self.assertEqual(F.accuracy(self.e,self.b,self.ally),-5)
   self.restore();self.valid();self.next_turn();self.assertIsNotNone(F.marker(self.e,self.b))
   self.e.end_of_turn(self.a);self.assertIsNone(F.marker(self.e,self.b))

 def test_mark_actual_weapon_and_accuracy_consumer_not_damage(self):
  self.scene(features=(F.CLASS,));key=self.weapon();self.combat();self.mark(weapon=key)
  move=self.rules.move('move/물대포')
  import combat_hit as HIT
  with patch.object(HIT,'resolve',wraps=HIT.resolve) as native:
   observed=self.e.accuracy_check(self.b,self.ally,move,fixed_roll=10)
   actual_modifier=native.call_args.kwargs['modifier']
  with patch.object(F,'accuracy',return_value=0),patch.object(HIT,'resolve',wraps=HIT.resolve) as native:
   baseline=self.e.accuracy_check(self.b,self.ally,move,fixed_roll=10)
   plain_modifier=native.call_args.kwargs['modifier']
  self.assertEqual(actual_modifier-plain_modifier,-5);self.assertEqual(observed[1],baseline[1])
  self.assertEqual(F.outgoing_penalty(self.b),0)

 def test_mark_requires_current_complete_attack_and_adjacency_atomic(self):
  self.scene(features=(F.CLASS,));self.combat()
  self.rejected(lambda:self.e.end_of_turn(self.a,fortress_mark='fabricated'),'actual complete')
  self.attack();token=self.completion
  self.e.gm.set_position(self.a,(10,10),reason='actual moved away after attack')
  self.rejected(lambda:self.e.end_of_turn(self.a,fortress_mark=token),'adjacent')
  self.e.gm.set_position(self.a,(1,1),reason='actual returns adjacent')
  self.e.end_of_turn(self.a);self.next_turn()
  self.rejected(lambda:self.e.end_of_turn(self.a,fortress_mark=token),'owner turn')

 def test_shared_mark_relation_replacement_both_directions_and_restore(self):
  self.scene(features=(F.CLASS,));self.combat();self.mark()
  T.acquire_static(self.e,self.ally,F.CLASS,acquisition_request_id='actual-second-fortress',selection={'edition':'supplement'})
  self.e.start_of_turn(self.ally,initiative_count=10)
  self.attack(actor=self.ally,target=self.b)
  self.e.end_of_turn(self.ally,fortress_mark=self.completion)
  self.assertEqual(len([r for r in TIME.records(self.b) if r.get('ace_marker')]),1)
  self.assertIs(F.marker(self.e,self.b)['ace_marker'],self.ally)
  self.next_turn();self.mark();self.assertIs(F.marker(self.e,self.b)['ace_marker'],self.a)
  self.restore();self.valid()
  rows=TIME.records(self.b);rows.append(dict(rows[0]))
  self.assertFalse(self.e.validate_state()['valid']);rows.pop();self.valid()

 def test_actual_fighting_ace_and_fortress_overwrite_one_shared_mark(self):
  import test_book_type_ace_reactions as FIX,type_ace as TA
  for mark_scope in F.GUARDIAN_SCOPES:
   f=FIX.TypeAceReactionTests();f.rules=self.rules;f.family('격투','Close Quarters Mastery')
   defender=f.add('actual Fortress replacement','trainer',(3,1),classes=[],feats=[],exp_bank=100)
   T.acquire_static(f.e,defender,F.CLASS,acquisition_request_id='cross/f',selection={'edition':'supplement'})
   T.acquire_static(f.e,defender,F.GUARDIAN,acquisition_request_id='cross/g',selection={'edition':'supplement','mark_scope':mark_scope})
   key=turn.equip_weapon(f.e,defender,{'name':'actual cross-source blade','kind':'소형 근접무기','grade':'간단','moves':[]})
   mid=defender.custom_conditions['equipped_weapons'][key]['struggle_id']
   f.e.gm.set_position(f.p,(3,2),reason='actual adjacent Fighting marker')
   f.sustain('Close Quarters Mastery');f.native(f.p,f.b,'move/태권당수')
   self.assertIs(TA.marked(f.e,f.b),f.p);f.e.end_of_turn(f.p)
   f.e.start_of_turn(defender,initiative_count=20)
   foreign=lambda:f.e.guardian_weapon_attack(defender,f.b,mid,weapon_id=key,skill='집중')
   if mark_scope=='korean_own_mark':
    f.rejected(foreign,'acquired Guardian source scope');f.native(defender,f.b,mid)
   else:
    with patch.object(Engine,'d20',return_value=10):foreign()
    self.assertEqual(F.outgoing_penalty(f.b),-6)
   row=f.completed(defender);f.e.end_of_turn(defender,fortress_mark=row['id'])
   self.assertIs(TA.marked(f.e,f.b),defender)
   f.e.end_round();f.combat(f.p);f.native(f.p,f.b,'move/태권당수')
   self.assertIs(TA.marked(f.e,f.b),f.p)
   self.assertEqual(len([r for r in TIME.records(f.b) if r.get('ace_marker')]),1);f.valid()

 def test_all_actual_weapon_aoe_targets_are_marked_not_only_adjacent_primary(self):
  self.scene(features=(F.CLASS,));self.e.gm.set_position(self.other,(3,1),reason='actual second blast recipient')
  key=turn.equip_weapon(self.e,self.a,{'name':'actual Fortress volley weapon','kind':'단거리 사격무기','grade':'간단','moves':['move/일제사격']})
  self.combat()
  with patch.object(Engine,'d20',return_value=1):
   self.e.use_move_on(self.a,self.b,'move/일제사격',self.e.everyone,weapon_id=key,aim=(2,1))
  row=next(reversed(list(self.e._move_completions.values())))
  self.assertIn(self.b,row['targets']);self.assertIn(self.other,row['targets'])
  self.e.end_of_turn(self.a,fortress_mark=row['id'])
  for target in row['targets']:self.assertIs(F.marker(self.e,target)['ace_marker'],self.a)

 def test_bastion_bind_two_ap_standard_cardinal_only_current_rank_consumer(self):
  self.scene(features=(F.BASTION,));self.combat();before=AP.available(self.a)
  out=self.e.sustain_fortress(self.a,request_id='native-aura',skill='전투')
  self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(self.a.spec['ap_bound'][out['instance_id']],2)
  self.assertEqual(F.damage_reduction(self.e,self.a),5);self.assertEqual(F.damage_reduction(self.e,self.ally),5)
  self.assertEqual(F.damage_reduction(self.e,self.b),0)
  self.e.gm.set_position(self.ally,(2,2),reason='actual diagonal not cardinal')
  self.assertEqual(F.damage_reduction(self.e,self.ally),0)
  SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],전투=4)},reason='actual current rank changes aura')
  self.assertEqual(F.damage_reduction(self.e,self.a),4)
  move=self.rules.move('move/물대포');actual=self.e.roll_damage(self.b,self.a,move,set_damage=True)
  with patch.object(F,'damage_reduction',return_value=0):plain=self.e.roll_damage(self.b,self.a,move,set_damage=True)
  self.assertEqual(plain-actual,4);self.valid()
  # Two actual sustained owners do not imply an unprinted stacking law.
  for uid in (F.CLASS,F.BASTION):T.acquire_static(self.e,self.ally,uid,acquisition_request_id='overlap/'+uid,selection={'edition':'supplement'})
  self.e.gm.set_position(self.ally,(1,2),reason='actual overlapping cardinal Bastion')
  self.next_turn(self.ally)
  overlap=self.e.sustain_fortress(self.ally,request_id='unruled-overlap',skill='집중')
  from composition_derive import CompositionPending
  with self.assertRaisesRegex(CompositionPending,'explicit GM composition law'):self.e.roll_damage(self.b,self.a,move,set_damage=True)
  self.e.end_fortress(self.ally,overlap['instance_id'])
  for law,value in (('add',9),('maximum',5),('minimum',4)):
   self.next_turn(self.ally)
   overlap=self.e.sustain_fortress(self.ally,request_id='ruled-overlap/'+law,skill='집중',stacking=law)
   self.assertEqual(F.damage_reduction(self.e,self.a),value)
   actual=self.e.roll_damage(self.b,self.a,move,set_damage=True)
   with patch.object(F,'damage_reduction',return_value=0):plain=self.e.roll_damage(self.b,self.a,move,set_damage=True)
   self.assertEqual(plain-actual,value);self.restore();self.valid()
   self.e.end_fortress(self.ally,overlap['instance_id'])

 def test_bastion_binding_codec_free_end_scene_and_exact_source_loss(self):
  self.scene(features=(F.BASTION,));self.combat();before=AP.available(self.a)
  out=self.e.sustain_fortress(self.a,request_id='persist',skill='집중')
  self.restore();self.valid();self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0)
  self.assertEqual(F.damage_reduction(self.e,self.a),5)
  self.combat();self.e.end_fortress(self.a,out['instance_id'])
  self.assertEqual(AP.available(self.a),before);self.assertEqual(F.damage_reduction(self.e,self.a),0)
  self.next_turn();out=self.e.sustain_fortress(self.a,request_id='withdraw',skill='집중')
  self.withdraw(F.BASTION);self.assertNotIn(out['instance_id'],self.a.spec['ap_bound']);self.valid()

 def test_binding_failures_do_not_spend_actions_or_ap(self):
  self.scene(features=(F.BASTION,));self.combat()
  self.rejected(lambda:self.e.sustain_fortress(self.a,request_id='bad-rank',skill='은신'),'Combat|Focus')
  self.e.sustain_fortress(self.a,request_id='first',skill='집중')
  self.rejected(lambda:self.e.sustain_fortress(self.a,request_id='second',skill='집중'),'one actual')
  self.next_turn();self.e.end_fortress(self.a,'fortress:'+self.a.entity_id+':first')
  turn.spend(self.e,self.a,'standard','actual used Standard')
  self.rejected(lambda:self.e.sustain_fortress(self.a,request_id='no-action',skill='집중'),'standard')

 def test_temporary_funding_expiry_uses_same_binding_owner_and_only_funded_effect(self):
  import moment_of_action as M,temporary_ap as TEMP
  self.scene(features=(F.BASTION,))
  issuer=self.ally
  for skill in ('매력','명령'):self.e.gm.set_skill(issuer,skill,3,reason='actual Cheerleader prerequisites')
  for uid in (M.TRAINING,M.CLASS,M.FEATURE):T.acquire_static(self.e,issuer,uid,acquisition_request_id='actual-cheer/'+uid)
  self.e.gm.observe_sensory_environment(issuer,self.a,paths={'auditory':True},present=True,reason='actual audible allied instruction')
  funding={'priority':'temporary_first','binding_expiry':'end_effect','reason':'GM chooses end same effect on actual funding loss'}
  self.e.moment_of_action(issuer,[self.a],funding={self.a.entity_id:funding},allies={self.a.entity_id:{'allied':True,'reason':'actual ally'}})
  self.assertEqual(TEMP.available(self.a),1);self.combat()
  out=self.e.sustain_fortress(self.a,request_id='temporarily-funded',skill='집중')
  self.restore();self.valid();self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=10)
  self.assertNotIn(out['instance_id'],self.a.spec['ap_bound'])
  self.assertEqual(F.damage_reduction(self.e,self.a),0);self.valid()

 def test_insufficient_ap_and_no_shield_swift_fail_atomically(self):
  self.scene(features=(F.SHIELD,));uid=self.shield();self.combat()
  self.a.ap_account.charge(AP.available(self.a))
  self.rejected(lambda:self.e.sustain_fortress(self.a,request_id='no-ap',skill='집중'),'AP|insufficient')
  self.rejected(lambda:self.e.ready_fortress_shield(self.a,uid,request_id='no-ap'),'AP|insufficient')

 def test_source_exact_light_heavy_shields_not_legacy_name_equivalence(self):
  self.scene(features=(F.SHIELD,))
  for uid,ready,dr in (('item/경방패',4,10),('item/중방패',6,15)):
   effects,header=self.rules.item_effects(uid)
   self.assertEqual(header['id'],uid);self.assertEqual(header['trainer_slot'],'반대손')
   self.assertEqual(F.SHIELDS[uid],(2,ready,dr));self.assertFalse(any(e['type']=='damage_reduction' for e in effects))
   self.assertEqual(self.rules.selection.dependencies[uid],(F.SHIELD_PARENT,))
   self.assertEqual(self.rules.selection.units[uid]['source']['sha256'],F.EQUIPMENT_SHA)
   self.assertEqual(self.rules.items_mech[uid]['effects'],effects)
   with patch.object(F,'shield_definition',side_effect=AssertionError('ordinary item reads must use the catalog')):
    self.assertEqual(self.rules.item_effects(uid)[0],effects)
  before=deepcopy(self.rules.items_mech['item/소형-방패'])
  F.install_shields(self.rules);self.assertEqual(self.rules.items_mech['item/소형-방패'],before)
  self.assertNotIn('item/소형-방패',F.SHIELDS)
  self.rejected(lambda:self.e.ready_fortress_shield(self.a,'not-physical',request_id='missing'),'physical')

 def test_shield_book_binding_csv_spend_swift_no_new_slowed_and_next_end(self):
  for edition in ('supplement','local_csv'):
   for heavy in (False,True):
    self.scene(features=(F.SHIELD,),edition=edition);uid=self.shield(heavy);self.combat();before=AP.available(self.a)
    out=self.e.ready_fortress_shield(self.a,uid,request_id='actual-ready')
    self.assertEqual(self.a.budget['swift'],0);self.assertNotIn('둔화',self.a.conditions)
    self.assertEqual(AP.available(self.a),before-1);self.assertEqual(out['bound'],edition=='supplement')
    self.assertEqual(F.shield_bonus(self.e,self.a),(6,15) if heavy else (4,10));self.assertEqual(F.ordinary_shield(self.e,self.a),0)
    self.restore();self.valid();self.next_turn();self.assertNotEqual(F.shield_bonus(self.e,self.a),(0,0))
    self.e.end_of_turn(self.a);self.assertEqual(F.shield_bonus(self.e,self.a),(0,0))
    self.assertEqual(F.ordinary_shield(self.e,self.a),2)
    self.assertEqual(AP.available(self.a),before if edition=='supplement' else before-1)

 def test_shield_donation_instead_of_self_dynamic_adjacency_and_existing_slowed(self):
  self.scene(features=(F.SHIELD,));uid=self.shield();self.e.apply_status(self.a,'둔화');self.combat()
  self.e.ready_fortress_shield(self.a,uid,ally=self.ally,request_id='donate')
  self.assertIn('둔화',self.a.conditions);self.assertEqual(F.shield_bonus(self.e,self.a),(0,0))
  self.assertEqual(F.shield_bonus(self.e,self.ally),(4,10));self.assertEqual(F.ordinary_shield(self.e,self.a),0)
  self.e.gm.set_position(self.ally,(8,8),reason='actual ally left adjacency')
  self.assertEqual(F.shield_bonus(self.e,self.ally),(0,0))
  self.e.gm.set_position(self.ally,(1,2),reason='actual ally returned adjacent')
  self.assertEqual(F.shield_bonus(self.e,self.ally),(4,10));self.valid()

 def test_shield_native_evasion_damage_consumers_and_unequip(self):
  self.scene(features=(F.SHIELD,));uid=self.shield();self.combat()
  self.e.ready_fortress_shield(self.a,uid,ally=self.ally,request_id='consumer')
  actual=self.ally.evasion('물리',attacker=self.b,engine=self.e)
  with patch.object(F,'shield_bonus',return_value=(0,0)):plain=self.ally.evasion('물리',attacker=self.b,engine=self.e)
  self.assertEqual(actual-plain,4)
  move=self.rules.move('move/물대포');actual=self.e.roll_damage(self.b,self.ally,move,set_damage=True)
  with patch.object(F,'shield_bonus',return_value=(0,0)):plain=self.e.roll_damage(self.b,self.ally,move,set_damage=True)
  self.assertEqual(plain-actual,10)
  items._unregister_selected(self.e,self.a,items.selected_equipment(self.a,uid,('반대손',)))
  self.assertEqual(F.shield_bonus(self.e,self.ally),(0,0));self.valid()

 def test_shield_follow_actual_paid_shift_native_interrupt_cap_and_codec(self):
  self.scene(features=(F.SHIELD,));uid=self.shield();self.combat()
  self.e.ready_fortress_shield(self.a,uid,ally=self.ally,request_id='follow-ready');self.e.end_of_turn(self.a)
  self.e.start_of_turn(self.ally,initiative_count=10)
  out=self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='native-follow',payment='next')
  self.assertGreater(out['ally']['distance'],0);self.assertEqual(self.ally.budget['shift'],0)
  self.assertIs(self.e._active_turn_actor,self.ally)
  self.assertLessEqual(out['follow']['distance'],6)
  self.assertTrue(self.e.adjacent(self.a,self.ally));self.assertEqual(F.shield_bonus(self.e,self.ally),(4,10))
  self.restore();self.valid();self.next_turn();self.assertEqual(self.a.budget['shift'],0)

 def test_shield_follow_rejects_nonprotected_wrong_turn_and_fabricated_movement(self):
  self.scene(features=(F.SHIELD,));uid=self.shield();self.combat()
  self.e.ready_fortress_shield(self.a,uid,ally=self.ally,request_id='follow-ready')
  self.rejected(lambda:self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='wrong-turn'),'own-turn')
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.ally,initiative_count=10)
  self.rejected(lambda:self.e.follow_fortress_ally(self.a,self.b,self.other,request_id='wrong-ally'),'protected')
  turn.spend(self.e,self.ally,'shift','actual spent ally Shift',movement=True)
  before=self.a.pos;out=self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='no-shift')
  self.assertIsNone(out['follow']);self.assertEqual(self.a.pos,before)

 def test_shield_follow_independent_native_ally_modes_and_own_land(self):
  for mode in ('sky','levitate','teleport','burrow'):
   self.follow_scene(ally_mode=mode,normal=2)
   options={'destination':(5,2),'reason_text':'actual protected ally native Shift destination'}
   if mode in ('sky','levitate'):options.update(altitude=1,gm_distance=4)
   elif mode=='teleport':options.update(surface_contact=True)
   else:options={'path':[(1,2),(2,2),(3,2),(4,2),(5,2)],'diggable':True,'surface':True,'reason_text':'surveyed actual ally tunnel and surface exit'}
   out=self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='different-mode/'+mode,
    movement_mode='land',ally_movement_mode=mode,ally_options=options)
   self.assertEqual(self.ally.pos,(5,2));self.assertEqual(self.ally.budget['shift'],0)
   self.assertIs(self.e._active_turn_actor,self.ally);self.assertGreater(out['follow']['distance'],0)
   self.assertLessEqual(out['follow']['distance'],2);self.assertFalse(self.e.adjacent(self.a,self.ally))
   if mode in ('sky','levitate'):self.assertEqual(self.ally.spec['_movement_altitude'],1)
   elif mode=='teleport':self.assertEqual(self.ally.spec['_teleport']['used_round'],self.e.round_no)
   else:self.assertTrue(self.e._burrow_tunnels);self.assertFalse(self.ally.spec['_burrow']['underground'])
   self.restore();self.valid();self.next_turn();self.assertEqual(self.a.budget['shift'],0)

 def test_shield_follow_native_own_nonland_paths_limits_interrupt_and_codec(self):
  for mode in ('sky','levitate','teleport','burrow'):
   self.follow_scene(mode=mode,normal=4)
   options={'destination':(3,3),'reason_text':'actual Fortress native follow destination'}
   if mode in ('sky','levitate'):options.update(altitude=1,gm_distance=3.5)
   elif mode=='teleport':options.update(surface_contact=True)
   else:options={'path':[(1,1),(1,2),(2,2),(3,3)],'diggable':True,'surface':True,'reason_text':'surveyed actual Fortress tunnel and surface exit'}
   out=self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='own-native/'+mode,
    movement_mode=mode,ally_movement_mode='land',follow_options=options)
   self.assertEqual(self.a.pos,(3,3));self.assertEqual(self.ally.budget['shift'],0)
   self.assertIs(self.e._active_turn_actor,self.ally);self.assertLessEqual(out['follow']['distance'],4)
   if mode in ('sky','levitate'):self.assertEqual(self.a.spec['_movement_altitude'],1);self.assertEqual(out['follow']['distance'],3.5)
   elif mode=='teleport':self.assertEqual(self.a.spec['_teleport']['used_round'],self.e.round_no)
   else:self.assertTrue(self.e._burrow_tunnels);self.assertFalse(self.a.spec['_burrow']['underground'])
   self.restore();self.valid();self.next_turn();self.assertEqual(self.a.budget['shift'],0)

 def test_shield_follow_nonland_observations_normal_cap_and_raw_budget_atomic(self):
  self.follow_scene(mode='teleport',normal=4)
  self.rejected(lambda:self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='too-far',
   movement_mode='teleport',ally_movement_mode='land',follow_options={'destination':(6,3),'surface_contact':True,'reason_text':'actual unoccupied destination exceeds own normal movement'}),'capability|movement')
  self.rejected(lambda:self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='fake-budget',
   movement_mode='teleport',ally_movement_mode='land',follow_options={'destination':(3,3),'surface_contact':True,'reason_text':'not authority','maximum_distance':999}),'observations')
  self.follow_scene(mode='burrow',normal=4)
  self.rejected(lambda:self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='unsurveyed',
   movement_mode='burrow',ally_movement_mode='land',follow_options={'path':[(1,1),(1,2),(2,2)],'diggable':False,'surface':True,'reason_text':'diggable ground has not been established'}),'awaits|burrowed')
  self.follow_scene(mode='levitate',normal=2)
  self.rejected(lambda:self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='too-high',
   movement_mode='levitate',ally_movement_mode='land',follow_options={'destination':(3,3),'altitude':2,'gm_distance':3,'reason_text':'actual height exceeds native Levitate limit'}),'altitude|height')
  self.follow_scene(ally_mode='teleport');self.e.gm.set_move(self.ally,'move/순간이동',add=False,reason='actual Teleport source withdrawn')
  before=(self.a.pos,self.ally.pos,deepcopy(self.a.budget),deepcopy(self.ally.budget))
  out=self.e.follow_fortress_ally(self.a,self.ally,self.other,request_id='no-learned-source',
   movement_mode='land',ally_movement_mode='teleport',ally_options={'destination':(5,2),'surface_contact':True,'reason_text':'observed destination does not grant Teleport'})
  self.assertIsInstance(out['ally'],__import__('common_checks').PendingDecision);self.assertIsNone(out['follow'])
  self.assertEqual((self.a.pos,self.ally.pos,self.a.budget,self.ally.budget),before);self.valid()

 def test_guardian_actual_marked_weapon_hit_defense_damage_only_and_full_round(self):
  self.scene(features=(F.GUARDIAN,));key=self.weapon();self.combat();self.mark(weapon=key);self.next_turn()
  observed=[];original=F.guardian_damage
  def observe(e,a,t,m,event):
   value=original(e,a,t,m,event);observed.append(value);return value
  with patch.object(F,'guardian_damage',side_effect=observe):self.attack(weapon=key,guardian=True)
  self.assertIn(self.a.staged('def'),observed);self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(F.outgoing_penalty(self.b),-5)
  before=F.accuracy(self.e,self.b,self.ally);self.assertEqual(before,-5)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
  self.assertEqual(F.outgoing_penalty(self.b),-5)
  self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone)
  self.e.start_of_turn(self.a,initiative_count=20);self.assertEqual(F.outgoing_penalty(self.b),0)
  self.valid()
  # A real H wait commits the hit prefix; saving/retrying cannot pay it twice.
  import heavy_injury_adapter as H
  self.scene(features=(F.GUARDIAN,));key=self.weapon();self.combat();self.mark(weapon=key);self.next_turn()
  self.e.gm.set_injuries(self.b,value=5,reason='observed actual heavily injured Guardian recipient')
  hp=self.b.hp
  with self.assertRaises(H.HeavyPending) as wait:self.attack(weapon=key,guardian=True)
  event_id=wait.exception.event_id;packet=self.e._heavy_events[event_id]
  self.assertEqual(self.e._heavy_pending,event_id);self.assertIs(packet['target'],self.b)
  self.assertLess(self.b.hp,hp);self.assertEqual(packet['observed_after']['hp'],self.b.hp)
  self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a._action_history,['standard','swift'])
  self.assertTrue(Q.activation_allowed(self.a,F.GUARDIAN,{'kind':'scene','uses':2},engine=self.e))
  self.assertEqual(Q.state(self.a)['activations'][F.GUARDIAN]['used'],1)
  self.assertEqual(F.outgoing_penalty(self.b),-5)
  scope=self.a.custom_conditions['fortress_guardian_attack'];row=self.e._move_completions[scope['completion_id']]
  self.assertTrue(scope['paid']);self.assertIs(scope['target'],self.b);self.assertIs(row['actor'],self.a)
  self.assertIn(self.b.entity_id,row['started']);self.assertNotIn(self.b.entity_id,row['results'])
  self.assertEqual(scope['hit_occurrence'],row['id']+':'+self.b.entity_id)
  self.valid();self.restore();self.valid()
  self.assertEqual(self.e._heavy_pending,event_id);self.assertIs(self.e._heavy_events[event_id]['target'],self.b)
  self.assertEqual(Q.state(self.a)['activations'][F.GUARDIAN]['used'],1);self.assertEqual(self.a.budget['swift'],0)
  scope=self.a.custom_conditions['fortress_guardian_attack']
  self.assertTrue(scope['paid']);self.assertIs(scope['target'],self.b)
  occurrence=scope['hit_occurrence'];scope['hit_occurrence']=occurrence+':forged-recipient'
  self.assertFalse(self.e.validate_state()['valid'])
  scope['hit_occurrence']=occurrence;self.valid()
  before=self.e.export_state()
  with self.assertRaisesRegex(ValueError,'one actual Guardian'):self.attack(weapon=key,guardian=True)
  self.assertEqual(self.e.export_state(),before)
  mid=self.a.custom_conditions['equipped_weapons'][key]['struggle_id']
  with self.assertRaises(H.HeavyPending):self.e.use_move_on(self.a,self.b,mid,self.e.everyone,weapon_id=key)
  self.assertEqual(self.e.export_state(),before)

 def test_guardian_miss_no_trigger_unmarked_nonweapon_and_set_damage_atomic(self):
  self.scene(features=(F.GUARDIAN,));key=self.weapon();self.combat()
  mid=self.a.custom_conditions['equipped_weapons'][key]['struggle_id']
  self.rejected(lambda:self.e.guardian_weapon_attack(self.a,self.b,mid,weapon_id=key,skill='집중'),'Marked')
  self.mark(weapon=key);self.next_turn();self.attack(weapon=key,guardian=True,roll=1)
  self.assertEqual(self.a.budget['swift'],1);self.assertEqual(F.outgoing_penalty(self.b),0)
  self.next_turn();self.mark(weapon=key);self.next_turn()
  self.rejected(lambda:self.e.guardian_weapon_attack(self.a,self.b,'move/물대포',skill='집중'),'Weapon')
  self.rejected(lambda:self.e.guardian_weapon_attack(self.a,self.b,mid,weapon_id=key,skill='집중',set_damage=True),'Set Damage')
  # A foreign Fortress Mark is a real native relation, not a test-installed flag.
  for edition in ('supplement','local_csv'):
   for mark_scope in F.GUARDIAN_SCOPES:
    self.scene(edition=edition);self.acquire(F.GUARDIAN,mark_scope=mark_scope);key=self.weapon()
    T.acquire_static(self.e,self.ally,F.CLASS,acquisition_request_id='foreign/class',selection={'edition':edition})
    self.combat(self.ally);self.attack(actor=self.ally,target=self.b)
    self.e.end_of_turn(self.ally,fortress_mark=self.completion);self.e.start_of_turn(self.a,initiative_count=10)
    self.restore();self.valid()
    self.assertEqual(F.acquired(self.a,F.GUARDIAN)['snapshot']['selection']['mark_scope'],mark_scope)
    if mark_scope=='korean_own_mark':self.rejected(lambda:self.attack(weapon=key,guardian=True),'acquired Guardian source scope')
    else:
     self.attack(weapon=key,guardian=True);self.assertEqual(F.outgoing_penalty(self.b),-5)
     self.assertIs(F.marker(self.e,self.b)['ace_marker'],self.ally)

 def test_guardian_damage_penalty_hits_native_roll_not_accuracy_or_fixed_loss(self):
  self.scene(features=(F.GUARDIAN,));key=self.weapon();self.combat();self.mark(weapon=key);self.next_turn()
  self.attack(weapon=key,guardian=True);move=self.rules.move('move/물대포')
  actual=self.e.roll_damage(self.b,self.ally,move,set_damage=True)
  with patch.object(F,'outgoing_penalty',return_value=0):plain=self.e.roll_damage(self.b,self.ally,move,set_damage=True)
  self.assertEqual(plain-actual,5)
  hp=self.ally.hp;self.e.lose_hp(self.ally,10,source='actual nonattack fixed loss');self.assertEqual(hp-self.ally.hp,10)
  self.restore();self.valid();self.assertEqual(F.outgoing_penalty(self.b),-5)

 def test_guardian_scene_two_uses_no_bypass_and_source_loss(self):
  self.scene(features=(F.GUARDIAN,));key=self.weapon();self.combat()
  for n in range(2):
   self.mark(weapon=key);self.next_turn();self.attack(weapon=key,guardian=True)
   self.assertEqual(Q.activation_allowed(self.a,F.GUARDIAN,{'kind':'scene','uses':2},engine=self.e),n==0)
   self.next_turn()
  self.mark(weapon=key);self.next_turn()
  self.rejected(lambda:self.attack(weapon=key,guardian=True),'frequency')
  self.withdraw(F.GUARDIAN);self.assertEqual(F.outgoing_penalty(self.b),0);self.valid()

 def test_source_pin_immutable_choices_and_corrupt_binding_validation(self):
  self.scene(features=(F.SLOW,F.BASTION));self.combat()
  self.rejected(lambda:self.acquire(F.SLOW,ability='전투무장'),'choice|selection|already|request')
  self.e.sustain_fortress(self.a,request_id='pin',skill='집중');identity='fortress:'+self.a.entity_id+':pin'
  self.a.spec['ap_bound'][identity]=1
  self.assertFalse(self.e.validate_state()['valid'])
  self.a.spec['ap_bound'][identity]=2
  self.valid()
  self.rejected(lambda:self.acquire(F.GUARDIAN,mark_scope='guess-all'),'S001 Guardian Mark scope')
  self.acquire(F.GUARDIAN,mark_scope='original_english_any_mark')
  sid=next(s for s,r in G.state(self.a)['sources'].items() if r.get('static_acquisition',{}).get('feature_id')==F.GUARDIAN)
  choice=G.state(self.a)['sources'][sid]['static_acquisition']['snapshot']['selection']
  choice['mark_scope']='korean_own_mark';self.assertFalse(self.e.validate_state()['valid'])
  choice['mark_scope']='original_english_any_mark';self.valid();self.restore();self.valid()
  self.rejected(lambda:self.acquire(F.GUARDIAN,mark_scope='korean_own_mark'),'selection|request|already')
  self.scene();key=self.weapon();self.combat();self.a.spec['feats']=list(F.FEATURES)
  before=deepcopy(self.a.spec)
  with self.assertRaisesRegex(ValueError,'actual Fortress acquisition'):self.attack(weapon=key,guardian=True)
  self.assertEqual(self.a.spec,before)

 def test_complete_inventory_scope_preserves_dedupe_other_category_and_no_credit(self):
  rows=json.loads((ROOT/'data/verification/category2-class-csv-clause-status.json').read_text(encoding='utf-8-sig'))['rows']
  rows={r['csv_record']:r for r in rows if r['file']=='input/db/feats.csv' and 566<=r['csv_record']<=572}
  self.assertEqual(set(rows),set(range(566,573)))
  for n in (566,569):self.assertTrue(rows[n]['include_category2']);self.assertIsNone(rows[n]['dedupe_target'])
  for n in (568,570,571):self.assertIsNotNone(rows[n]['dedupe_target'])
  for n in (567,572):self.assertFalse(rows[n]['include_category2']);self.assertEqual(rows[n]['status'],'other-category')


if __name__=='__main__':unittest.main()
