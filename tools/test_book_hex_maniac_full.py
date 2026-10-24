"""Actual Hex Maniac acquisition, complete native activations and both Confusions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import hex_maniac as H,trainer_feature_acquisition as A,acquired_features as AC
import action_points as AP,frequency as F,state_grants as G,state_codec as CODEC,world_entities as WORLD
import confusion_attacks as CONFUSION,turn as TURN,condition_instances as CONDITIONS


class HexManiacTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(ROOT,ruleset='core-confusion-feb2016')
  cls.core=Rules(ROOT,ruleset='core-confusion-1.05')
  cls.feb=Rules(ROOT,ruleset='core-confusion-feb2016')
 def setUp(self):
  self.original=self.rules.rulings;self.rules.rulings=deepcopy(self.original)
  self.addCleanup(setattr,self.rules,'rulings',self.original)
  self.setup()
 def setup(self,rules=None,skill=6):
  self.r=rules or self.rules;self.e=Engine(self.r,seed=29312936);self.e.grid=Grid(20,12)
  common=dict(level=30,size='중형',stats={'hp':100,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
   moves=['move/몸통박치기','move/염동력'],abilities=[],types=['노말'],movement={'land':6,'swim':4,'sky':4,'power':4},
   skills={'오컬트학':skill,'전투':3,'육상':4,'곡예':4,'집중':4},gender='수컷',weight_class=3,weight_kg=30)
  self.a=Combatant(self.r,dict(deepcopy(common),name='actual Hex Maniac',kind='trainer',classes=[],feats=[],exp_bank=50))
  self.b=Combatant(self.r,dict(deepcopy(common),name='actual enemy',kind='trainer',classes=[],feats=[]))
  self.c=Combatant(self.r,dict(deepcopy(common),name='additional enemy',kind='trainer',classes=[],feats=[]))
  self.d=Combatant(self.r,dict(deepcopy(common),name='actual ally',kind='trainer',classes=[],feats=[]))
  for actor,pos,side in ((self.a,(2,2),'party'),(self.b,(3,2),'enemy'),(self.c,(3,3),'enemy'),(self.d,(2,3),'party')):
   self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native participant')
   prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual body')
 def acquire(self,feature=H.CLASS,*,ability=H.OMEN,rank=None,moves=None):
  selection={'ability':ability} if feature==H.CLASS else {'moves':moves} if feature==H.STUDIES else None
  return A.acquire_static(self.e,self.a,feature,rank=rank,selection=selection,acquisition_request_id='Hex/'+feature+'/'+str(rank))
 def family(self,rank=3,ability=H.OMEN,extras=True):
  self.acquire(ability=ability)
  pairs=[['이상한빛','저주'],['최면술','원한'],['도깨비불','병상첨병']]
  for number in range(1,rank+1):self.acquire(H.STUDIES,rank=number,moves=pairs[number-1])
  if extras:
   for feature in (H.DIFFUSE,H.MALEDICTION):self.acquire(feature)
   if rank==3:self.acquire(H.GRAND)
 def combat(self,actor=None):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=30)
 def next(self,actor=None):
  owner=self.e._active_turn_actor
  if owner is not None:self.e.end_of_turn(owner)
  self.e.end_round();self.combat(actor)
 def use(self,mid,target=None,**kw):
  with patch.object(Engine,'d20',return_value=19):return self.e.use_hex_maniac_move(self.a,target or self.b,mid,set_damage=True,**kw)
 def event(self,mid=None,recipient=None):
  rows=[event for event in self.e._passive_events.values() if event['producer'] in ('Engine.use_move','Engine.use_move/defense-recipient') and (mid is None or event['move_id']==mid) and (recipient is None or event['target'] is recipient)]
  return rows[-1]['id']
 def rejected(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
 def restored(self):
  ids=[a.entity_id for a in (self.a,self.b,self.c,self.d)]
  self.e=CODEC.load_engine(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.b,self.c,self.d=[WORLD.actor_index(self.e)[uid] for uid in ids]
 def status_then_hex(self,mid='move/이상한빛',*,target=None,boost=False):
  target=target or self.b;self.use(mid,target);self.next();self.use(H.HEX,target,boost=boost)
  return self.event(H.HEX,target)
 def enemy_attack(self,*,hit=False,targets=None):
  if not self.e.encounter_active:self.combat(self.b)
  else:self.next(self.b)
  targets=targets or [self.a]
  import move_activation as ACTIVATION,action_lifecycle as ACTION
  with patch.object(Engine,'d20',return_value=19 if hit else 1):
   with ACTIVATION.open_scope(self.e,self.b,'move/몸통박치기',targets,shared=False,primary=targets[0]) as (activation,accuracy):
    for index,target in enumerate(targets):
     if not index:self.e.use_move(self.b,target,'move/몸통박치기',_activation=activation,set_damage=True)
     else:
      with ACTION.move_grant(self.e,self.b,target,'move/몸통박치기',source='same_move_activation') as grant:self.e.use_move(self.b,target,'move/몸통박치기',count_use=False,_activation=activation,_action_grant=grant,set_damage=True)
  return self.event('move/몸통박치기',targets[-1])

 def test_five_members_independent_actual_acquisition_hp_and_all_six_move_sources(self):
  hp=self.a.stats['hp'];self.family()
  self.assertEqual(len(H.DEFINITIONS),5);self.assertEqual(len(AC.class_instances(self.a)),1)
  self.assertEqual(self.a.stats['hp'],hp+7)
  self.assertEqual(len(H.records(self.a,active=True)),7)
  self.assertEqual(H.studies_moves(self.a),set(H.STATUS_MOVES)|{H.HEX})
  self.assertIn('징조',self.a.abilities);self.assertNotIn('저주받은바디',self.a.abilities)
  self.restored();self.assertTrue(self.e.validate_state()['valid'])

 def test_base_class_exact_ability_choice_and_no_children_automatically_awarded(self):
  self.acquire(ability=H.BODY)
  self.assertIn('저주받은바디',self.a.abilities);self.assertFalse(H.acquired(self.a,H.STUDIES))
  self.assertEqual(H.studies_moves(self.a),set())
  self.rejected(lambda:self.acquire(ability=H.OMEN),'replay|already')
  self.rejected(lambda:self.e.use_hex_maniac_move(self.a,self.b,'move/이상한빛'),'Studies')

 def test_novice_and_parent_rank_prerequisites_use_actual_receipts(self):
  self.setup(skill=2);self.rejected(self.acquire,'Occult|prerequisite')
  self.setup();self.rejected(lambda:self.acquire(H.STUDIES,rank=1,moves=['이상한빛','저주']),'parent')
  self.acquire();self.rejected(lambda:self.acquire(H.GRAND),'Studies|parent')

 def test_studies_rank_domains_distinct_choices_and_expert_third_rank(self):
  self.acquire();self.rejected(lambda:self.acquire(H.STUDIES,rank=2,moves=['원한','최면술']),'next actual rank')
  self.rejected(lambda:self.acquire(H.STUDIES,rank=1,moves=['병상첨병','저주']),'rank|domain')
  self.acquire(H.STUDIES,rank=1,moves=['이상한빛','저주'])
  self.rejected(lambda:self.acquire(H.STUDIES,rank=2,moves=['저주','원한']),'distinct')
  self.acquire(H.STUDIES,rank=2,moves=['최면술','원한'])
  self.a.spec['skills']['오컬트학']=4
  self.rejected(lambda:self.acquire(H.STUDIES,rank=3,moves=['도깨비불','병상첨병']),'Occult|prerequisite')

 def test_diffuse_same_native_activation_two_targets_one_ap_payment_and_frequency(self):
  self.family();self.combat();ap=AP.available(self.a)
  self.use('move/이상한빛',diffuse_target=self.c)
  self.assertTrue(all('혼란' in target.conditions for target in (self.b,self.c)))
  self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.a.move_uses['move/이상한빛'],1)
  rows=[row for row in self.e._move_completions.values() if row['move_id']=='move/이상한빛']
  self.assertEqual(len(rows),1);self.assertEqual(set(rows[0]['results']),{self.b.entity_id,self.c.entity_id})

 def test_diffuse_ghost_curse_pays_native_self_hp_cost_once(self):
  self.family();self.combat();hp=self.a.hp
  self.use(H.CURSE,diffuse_target=self.c)
  self.assertTrue(all('저주' in t.conditions for t in (self.b,self.c)))
  self.assertEqual(self.a.hp,hp-self.a.max_hp//3)
  self.assertEqual(self.a.move_uses[H.CURSE],1);self.assertNotIn('고스트',self.a.types)

 def test_diffuse_wrong_source_damaging_move_duplicate_and_range_reject_atomically(self):
  self.family();self.combat()
  self.rejected(lambda:self.use(H.HEX,diffuse_target=self.c),'Status')
  self.rejected(lambda:self.use('move/이상한빛',diffuse_target=self.b),'distinct')
  self.c.pos=(10,2);self.rejected(lambda:self.use('move/최면술',diffuse_target=self.c),'range')
  self.rejected(lambda:self.use('move/염동력',diffuse_target=self.c),'Studies')

 def test_diffuse_native_spite_keeps_real_user_hit_and_same_disabled_move_for_extra(self):
  self.family();self.combat();self.d.pos=(0,2);self.c.pos=(6,3)
  with patch.object(Engine,'d20',return_value=19):self.e.approach(self.a,self.d,reach=1)
  event=self.event('struggle',self.a);ap=AP.available(self.a)
  self.use(H.SPITE,spite_event=event,diffuse_target=self.c)
  for target in (self.b,self.c):self.assertEqual(CONDITIONS.records(target,'사슬묶기')[0]['effect']['move_id'],'struggle')
  self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.a.move_uses[H.SPITE],1)
  self.restored();self.assertTrue(self.e.validate_state()['valid'])

 def test_spite_cannot_use_allmiss_as_user_hit_or_arbitrary_trigger(self):
  self.family();event=self.enemy_attack(hit=False)
  self.rejected(lambda:self.use(H.SPITE,spite_event=event),'hit recipient')
  self.rejected(lambda:self.use(H.SPITE,spite_event='invented'),'trigger|event')
  event=self.enemy_attack(hit=True)
  self.rejected(lambda:self.use(H.SPITE,spite_event=event,diffuse_target=self.c),'Swift')

 def test_malediction_actual_allmiss_free_action_scene_two_and_event_replay(self):
  self.family();self.combat();event=self.enemy_attack(hit=False);before=self.a.budget.copy()
  self.use('move/이상한빛',malediction_event=event)
  self.assertIn('혼란',self.b.conditions);self.assertEqual(self.a.budget,before)
  self.rejected(lambda:self.use('move/최면술',malediction_event=event),'consumed')
  event=self.enemy_attack(hit=False);self.use('move/최면술',malediction_event=event)
  self.assertIn('잠듦',self.b.conditions)
  self.e.cure_status(self.b,'잠듦')
  event=self.enemy_attack(hit=False);self.rejected(lambda:self.use('move/도깨비불',malediction_event=event),'Scene frequency')

 def test_malediction_any_hit_ally_beyond5_and_native_move_range_are_atomic(self):
  self.family();event=self.enemy_attack(hit=True)
  self.rejected(lambda:self.use('move/이상한빛',malediction_event=event),'miss every')
  event=self.enemy_attack(hit=False);self.b.pos=(8,2)
  self.rejected(lambda:self.use('move/이상한빛',malediction_event=event),'five metres')
  self.b.pos=(7,2);self.rejected(lambda:self.use('move/최면술',malediction_event=event),'range')
  self.b.pos=(3,2);self.b.side='party';self.rejected(lambda:self.use('move/이상한빛',malediction_event=event),'enemy')

 def test_malediction_whole_attack_with_one_hit_or_unfinished_target_is_rejected(self):
  self.family();self.combat(self.b)
  import move_activation as ACTIVATION,action_lifecycle as ACTION
  with ACTIVATION.open_scope(self.e,self.b,'move/몸통박치기',[self.a,self.d],shared=False,primary=self.a) as (activation,accuracy):
   with patch.object(Engine,'d20',return_value=1):self.e.use_move(self.b,self.a,'move/몸통박치기',_activation=activation,set_damage=True)
   event=self.event('move/몸통박치기',self.a)
   with self.assertRaisesRegex(ValueError,'whole Move'):H.malediction_trigger(self.e,self.a,event)
   with ACTION.move_grant(self.e,self.b,self.d,'move/몸통박치기',source='same_move_activation') as grant:
    with patch.object(Engine,'d20',return_value=19):self.e.use_move(self.b,self.d,'move/몸통박치기',count_use=False,_activation=activation,_action_grant=grant,set_damage=True)
  self.rejected(lambda:self.use('move/이상한빛',malediction_event=event),'miss every')

 def test_malediction_spite_never_fabricates_a_triggering_hit(self):
  self.family();event=self.enemy_attack(hit=False)
  self.rejected(lambda:self.use(H.SPITE,malediction_event=event,spite_event=event),'hit recipient')

 def test_grand_hex_recovers_actual_scene_use_without_additional_cast(self):
  self.family();self.combat();event=self.status_then_hex();before=len(self.e._move_completions);ap=AP.available(self.a)
  result=self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛')
  self.assertEqual(self.a.move_uses['move/이상한빛'],0);self.assertEqual(len(self.e._move_completions),before)
  self.assertEqual(AP.available(self.a),ap-1);self.assertFalse(result['hex_frequency_refunded'])
  self.assertEqual(self.a.move_uses[H.HEX],1)
  self.restored();self.assertTrue(self.e.validate_state()['valid'])

 def test_grand_boost_selected_this_hit_refunds_only_hex_frequency_not_boost_scene(self):
  self.family();self.combat();event=self.status_then_hex(boost=True)
  self.assertIn(self.b.entity_id,self.e._move_completions[self.e._passive_events[event]['completion_id']]['hex_boosted_recipients'])
  result=self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛')
  self.assertTrue(result['hex_frequency_refunded']);self.assertNotIn(H.HEX,self.a.move_uses)
  self.assertTrue(self.a.counters['lim:conditional-db:'+H.HEX+':scene'])
  self.assertEqual(self.e.damage_base(self.a,self.r.move(H.HEX),target=self.b),7)

 def test_old_scene_boost_does_not_refund_a_later_unboosted_hex_hit(self):
  self.family();self.combat();self.status_then_hex(boost=True);self.next();self.use('move/이상한빛',self.c)
  self.next();self.use(H.HEX,self.c,boost=False);event=self.event(H.HEX,self.c)
  result=self.e.activate_grand_hex(self.a,self.c,event,'move/이상한빛')
  self.assertFalse(result['hex_frequency_refunded']);self.assertEqual(self.a.move_uses[H.HEX],2)

 def test_hex_optional_boost_decline_default_and_miss_do_not_spend_scene_increase(self):
  self.family();self.combat();self.use('move/이상한빛');self.next()
  self.assertEqual(self.e.damage_base(self.a,self.r.move(H.HEX),target=self.b),7)
  with patch.object(Engine,'d20',return_value=1):self.e.use_hex_maniac_move(self.a,self.b,H.HEX,boost=True,set_damage=True)
  self.assertFalse(self.a.counters.get('lim:conditional-db:'+H.HEX+':scene'))

 def test_grand_wrong_current_status_unused_move_and_nonstudies_source_reject(self):
  self.family();self.combat();event=self.status_then_hex()
  self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/최면술'),'current')
  self.e.apply_status(self.b,'화상',source='native test status',applied_by=self.c)
  self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/도깨비불'),'expended')
  self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/염동력'),'Studies')

 def test_grand_eot_restore_and_already_restored_occurrence_are_distinct(self):
  self.family();self.combat();event=self.status_then_hex('move/도깨비불')
  self.e.activate_grand_hex(self.a,self.b,event,'move/도깨비불')
  self.assertNotIn('move/도깨비불',F.state(self.a)['moves'])
  self.next();self.next();self.use(H.HEX,self.c);event=self.event(H.HEX,self.c)
  self.e.apply_status(self.c,'화상',source='native status',applied_by=self.b)
  self.rejected(lambda:self.e.activate_grand_hex(self.a,self.c,event,'move/도깨비불'),'expended')

 def test_grand_current_status_choices_curse_sleep_disabled_and_burn(self):
  for mid,status in ((H.CURSE,'저주'),('move/최면술','잠듦'),(H.SPITE,'사슬묶기'),('move/도깨비불','화상')):
   with self.subTest(move=mid):
    self.setup();self.family()
    if mid==H.SPITE:
     event=self.enemy_attack(hit=True);self.use(H.SPITE,spite_event=event);self.next()
    else:self.combat();self.use(mid);self.next()
    self.assertIn(status,self.b.conditions);self.use(H.HEX);event=self.event(H.HEX,self.b)
    self.e.activate_grand_hex(self.a,self.b,event,mid)
    if F.move_frequency(self.e,mid,self.a)[0]=='scene':self.assertEqual(self.a.move_uses[mid],0)
    else:self.assertNotIn(mid,F.state(self.a)['moves'])

 def test_grand_target_scene_cap_different_targets_and_next_scene(self):
  self.family();self.combat();event=self.status_then_hex();self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛')
  self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛'),'already')
  self.next();self.use('move/이상한빛',self.c);self.next();self.use(H.HEX,self.c);event=self.event(H.HEX,self.c)
  self.e.activate_grand_hex(self.a,self.c,event,'move/이상한빛')
  self.e.end_of_turn(self.a);self.e.end_scene(self.e.everyone);self.combat()
  event=self.status_then_hex();self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛')

 def test_grand_miss_nonhex_missing_ap_and_swift_failure_are_atomic(self):
  self.family();self.combat();event=self.status_then_hex()
  AP.spend(self.a,AP.available(self.a));self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛'),'AP')
  self.setup();self.family();self.combat();event=self.status_then_hex()
  TURN.spend(self.e,self.a,'swift','actual consumed Swift');self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛'),'Swift')
  self.setup();self.family();self.combat();self.use('move/이상한빛');self.next()
  with patch.object(Engine,'d20',return_value=1):self.e.use_hex_maniac_move(self.a,self.b,H.HEX,set_damage=True)
  event=self.event(H.HEX,self.b);self.rejected(lambda:self.e.activate_grand_hex(self.a,self.b,event,'move/이상한빛'),'successful')

 def test_cursed_body_actual_damaging_hit_disables_exact_move_scene_once(self):
  self.family(ability=H.BODY);event=self.enemy_attack(hit=True)
  receipt=self.e.activate_ability(self.a,H.BODY,self.b,trigger_event_id=event)
  self.assertEqual(receipt['move_id'],'move/몸통박치기')
  self.assertEqual(CONDITIONS.records(self.b,'사슬묶기')[0]['effect']['move_id'],'move/몸통박치기')
  self.rejected(lambda:self.e.activate_ability(self.a,H.BODY,self.b,trigger_event_id=event),'Scene')
  self.restored();self.assertTrue(self.e.validate_state()['valid'])

 def test_cursed_body_miss_other_recipient_and_wrong_attacker_reject_atomically(self):
  self.family(ability=H.BODY);event=self.enemy_attack(hit=False)
  self.rejected(lambda:self.e.activate_ability(self.a,H.BODY,self.b,trigger_event_id=event),'successful')
  event=self.enemy_attack(hit=True,targets=[self.d])
  self.rejected(lambda:self.e.activate_ability(self.a,H.BODY,self.b,trigger_event_id=event),'successful')
  event=self.enemy_attack(hit=True);self.rejected(lambda:self.e.activate_ability(self.a,H.BODY,self.c,trigger_event_id=event),'attacker')

 def test_omen_selected_5m_scene_swift_and_actual_accuracy_penalty(self):
  self.family();self.combat();self.b.pos=(7,2)
  baseline=[self.e.accuracy_check(self.b,self.a,self.r.move('move/몸통박치기'),fixed_roll=face)[0] for face in range(2,20)]
  self.e.activate_ability(self.a,H.OMEN,self.b)
  penalized=[self.e.accuracy_check(self.b,self.a,self.r.move('move/몸통박치기'),fixed_roll=face)[0] for face in range(2,20)]
  self.assertEqual(sum(baseline)-sum(penalized),2)
  self.assertEqual(__import__('combat_timing').accuracy_modifier(self.b),-2)
  self.rejected(lambda:self.e.activate_ability(self.a,H.OMEN,self.c),'Scene')
  self.restored();self.assertEqual(__import__('combat_timing').accuracy_modifier(self.b),-2)
  self.e.end_of_turn(self.a);self.e.end_scene(self.e.everyone)
  self.assertEqual(__import__('combat_timing').accuracy_modifier(self.b),0)

 def test_omen_outside5_unowned_and_suppressed_are_atomic(self):
  self.family();self.combat();self.b.pos=(8,2)
  self.rejected(lambda:self.e.activate_ability(self.a,H.OMEN,self.b),'five metres')
  self.b.pos=(3,2);self.rejected(lambda:self.e.activate_ability(self.a,H.BODY,self.b),'acquired')
  self.a.abilities_suppressed=True;self.rejected(lambda:self.e.activate_ability(self.a,H.OMEN,self.b),'acquired')

 def test_core_confusion_actual_start_save_three_bands_and_typeless_resisted_self_hit(self):
  for face in (1,8,9,15,16,20):
   with self.subTest(save=face):
    self.setup(self.core);self.e.apply_status(self.a,'혼란',source='move/이상한빛',applied_by=self.b)
    hp=self.a.hp
    with patch.object(Engine,'d20',return_value=face):self.combat()
    result=self.a.custom_conditions['core_confusion_turns'][-1]
    self.assertEqual(result['outcome'],'self_hit' if face<=8 else 'normal' if face<=15 else 'cured')
    if face<=8:
     self.assertLess(self.a.hp,hp);self.assertEqual(result['type'],'None');self.assertEqual(result['resistance_steps'],1)
     row=self.e._move_completions[result['completion_id']];self.assertEqual(row['phase'],'complete');self.assertTrue(row['results'][self.a.entity_id]['hit'])
     self.assertFalse(TURN.spend(self.e,self.a,'free','no other action'))
    else:self.assertEqual(self.a.hp,hp)
    self.assertEqual('혼란' in self.a.conditions,face<16)
    self.assertEqual(TURN.can_aoo(self.e,self.a),9<=face<=15 or face>=16)
    self.e.end_of_turn(self.a);self.assertTrue(TURN.can_aoo(self.e,self.a))
    self.assertTrue(__import__('action_lifecycle').status_permission(self.e,self.a,'free'))

 def test_core_default_selects_printed_version_all_preserves_feb_and_frozen_turn_starts(self):
  rules=Rules(ROOT,ruleset='core');self.setup(rules);self.assertTrue(CONFUSION.core(self.e))
  self.assertFalse(CONFUSION.core(Engine(Rules(ROOT,ruleset='all'))))
  self.e.apply_status(self.a,'얼음',source='native Frozen',applied_by=self.b)
  self.e.apply_status(self.a,'혼란',source='move/이상한빛',applied_by=self.b);hp=self.a.hp
  with patch.object(Engine,'d20',return_value=1):self.combat()
  self.assertIs(self.e._active_turn_actor,self.a);self.assertEqual(self.a.hp,hp)
  self.assertEqual(self.a.custom_conditions['core_confusion_turns'][-1]['outcome'],'self_attack_forbidden')

 def test_core_confusion_no_postattack_die_or_end_save_and_sleep_exception(self):
  self.setup(self.core);self.family();self.e.apply_status(self.a,'혼란',source='move/이상한빛',applied_by=self.b)
  with patch.object(Engine,'d20',return_value=9):self.combat()
  hp=self.a.hp;self.use('move/이상한빛')
  row=list(self.e._move_completions.values())[-1];self.assertNotIn('confusion',row);self.assertEqual(self.a.hp,hp)
  with patch.object(Engine,'d20',return_value=20):self.e.end_of_turn(self.a)
  self.assertIn('혼란',self.a.conditions)
  self.e.apply_status(self.a,'잠듦',source='move/최면술',applied_by=self.b)
  with patch.object(Engine,'d20',return_value=1):self.e.end_round();self.combat()
  self.assertEqual(self.a.hp,hp)

 def test_feb2016_confusion_actual_postattack_d2_and_turn_end_cure(self):
  self.setup(self.feb);self.family();self.combat();self.e.apply_status(self.a,'혼란',source='move/이상한빛',applied_by=self.b)
  hp=self.a.hp
  with patch.object(CONFUSION.POOLS,'die',return_value=1):self.use('move/이상한빛')
  self.assertEqual(self.a.hp,hp-self.e.tick_loss(self.a,2));self.assertIn('혼란',self.b.conditions)
  self.assertFalse(TURN.can_aoo(self.e,self.a))
  with patch.object(Engine,'d20',return_value=16):self.e.end_of_turn(self.a)
  self.assertNotIn('혼란',self.a.conditions);self.restored();self.assertTrue(self.e.validate_state()['valid'])


from provocateur_fixture import ProvocateurScene
class HexCoreProvocateurTests(ProvocateurScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_actual_core_self_attack_preserves_fiddle_adjacent_enemy_opportunities_once(self):
  import provocateur as P
  self.whole();self.e.gm.set_position(self.a,(3,2),reason='actual adjacent foe');self.e.gm.set_position(self.b,(4,1),reason='actual second adjacent foe')
  self.begin();self.fiddle(P.MOVES[3])
  with patch.object(Engine,'d20',return_value=1):self.turn(self.t)
  self.assertTrue(self.a.aoo_used);self.assertTrue(self.b.aoo_used)
  row=[r for r in self.e._move_completions.values() if r['actor'] is self.t and r['move_id']=='struggle'][-1]
  self.assertTrue(row['results'][self.t.entity_id]['hit']);self.valid()

from channeler_fixture import ChannelerScene
class HexCoreChannelerTests(ChannelerScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_actual_core_self_attack_uses_pain_dampening_damage_replacement(self):
  import channeler as CHANNEL
  self.ready_pain();before=self.q.hp
  self.e.apply_status(self.p,'혼란',source='move/이상한빛',applied_by=self.b)
  with patch.object(Engine,'d20',return_value=1):self.turn(self.p)
  row=self.latest();self.assertEqual(row['actor'],self.p);self.assertEqual(row['move']['type'],'None')
  self.assertTrue(row['results'][self.p.entity_id]['hit']);self.assertLess(self.q.hp,before)
  self.assertEqual(F.state(self.a)['activations'][CHANNEL.PAIN]['used'],1);self.valid()

if __name__=='__main__':unittest.main()
