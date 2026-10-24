"""Entire Rogue class: actual ownership, physical weapon, native hit/cost/timing boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from rogue_fixture import RogueScene,Rules,Engine,Combatant
import rogue as R,weapon_actions as WA,turn as TURN,combat_timing as TIME
import frequency as F,move_completion as MC,trainer_feature_acquisition as T
import skill_feature_actions as SF,skill_maneuver_actions as SM,state_fields as FIELDS

class RogueTests(RogueScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT)
 def test_seven_independent_acquisitions_and_attack_tags(self):
  before=self.a.stats['atk'];self.acquire(R.CLASS)
  self.assertEqual(self.a.stats['atk'],before+1);self.assertEqual(self.a.spec['feats'],[R.CLASS])
  self.assertTrue(set(R.MOVES[:2])<=set(self.a.moves));self.assertFalse(set(R.MOVES[2:])&set(self.a.moves))
  for uid in list(R.FEATURES)[1:]:self.acquire(uid,ability=R.CRUELTY)
  self.assertEqual(self.a.stats['atk'],before+7);self.assertTrue(set(R.MOVES)<=set(self.a.moves))
  self.assertTrue(__import__('ability_transitions').active(self.a,R.CRUELTY));self.assertEqual(len(T._static_records(self.a)),7)
  T.validate_actor(self.a);self.restore();self.valid()
 def test_class_rank_count_and_parent_selection_rejections_are_atomic(self):
  self.reject(lambda:self.acquire(R.CUT),'prerequisite')
  FIELDS.base_patch(self.a,{'skills':{'곡예':3,'육상':2,'은신':2}},reason='actual insufficient ranks')
  self.reject(lambda:self.acquire(R.CLASS),'rank')
  FIELDS.base_patch(self.a,{'skills':{'곡예':5,'육상':3,'은신':2}},reason='actual two novice ranks')
  self.acquire(R.CLASS)
  self.reject(lambda:self.acquire(R.UNEXPECTED),'rank')
  self.reject(lambda:self.acquire(R.UNDERHAND,ability='ambush'),'choose')
  self.acquire(R.UNDERHAND,ability=R.CRUELTY)
  self.reject(lambda:self.acquire(R.UNDERHAND,ability=R.AMBUSH,request='again'),'one Ability')
 def test_cutthroat_short_weapon_range_and_original_move_are_independent(self):
  self.family(R.CUT);key=self.weapon('근거리 사격무기');move=self.rules.move(R.MOVES[0])
  self.assertNotIn('_weapon_attack',WA.prepare(self.e,self.a,move))
  actual=WA.prepare(self.e,self.a,move,key)
  self.assertEqual(WA.range_spec(self.e,actual,self.a)['origin'],4)
  self.assertEqual((actual['id'],actual['frequency'],actual['ac']),(move['id'],move['frequency'],move['ac']))
  self.e.gm.set_position(self.t,(6,2),reason='four metre actual target');self.begin()
  row=self.use(self.a,self.t,R.MOVES[0],face=1,weapon_id=key)
  self.assertTrue(MC.recipient_result(row,self.t)['hit']);self.assertEqual(row['move']['_weapon_attack']['key'],key)
  self.assertLess(self.t.hp,self.t.max_hp)
 def test_cutthroat_small_weapon_bonus_and_explicit_selection(self):
  self.family(R.CUT);first=self.weapon();second=self.weapon('근거리 사격무기',name='sling',slot='반대손')
  small=WA.prepare(self.e,self.a,self.rules.move(R.MOVES[0]),first)
  ranged=WA.prepare(self.e,self.a,self.rules.move(R.MOVES[0]),second)
  self.assertEqual(WA.damage_bonus(small),1);self.assertEqual(WA.damage_bonus(ranged),0)
  self.assertEqual(WA.accuracy_bonus(ranged),-2)
  self.assertEqual(WA.range_spec(self.e,small,self.a)['origin'],'melee')
  self.assertEqual(WA.range_spec(self.e,ranged,self.a)['origin'],4)
  self.reject(lambda:WA.prepare(self.e,self.a,small,second),'cannot be changed')
 def test_cutthroat_rejects_noneligible_weapon_and_no_long_range_leak(self):
  self.family(R.CUT);key=self.weapon('장거리 사격무기')
  self.reject(lambda:WA.prepare(self.e,self.a,self.rules.move(R.MOVES[0]),key),'Small Melee')
  import optional_weapon_framework as FW
  weapon=self.a.custom_conditions['equipped_weapons'][key]['weapon']
  self.assertEqual(FW.skill_rank(self.e,self.a,weapon),2)
 def test_cutthroat_real_weapon_move_qualification_uses_highest_rogue_skill(self):
  self.family(R.CUT)
  key=self.weapon(moves=['move/비열한-습격'],grade='간단')
  self.begin();row=self.use(self.a,self.t,'move/비열한-습격',weapon_id=key)
  self.assertTrue(MC.recipient_result(row,self.t)['hit'])
  self.assertEqual(self.a.spec['skills']['전투'],2)
 def test_cutthroat_disarmed_prepared_weapon_cannot_be_reused(self):
  self.family(R.CUT);key=self.weapon();move=WA.prepare(self.e,self.a,self.rules.move(R.MOVES[0]),key)
  TURN.unequip_weapon(self.e,self.a,key)
  self.reject(lambda:WA.prepare(self.e,self.a,move),'equipped')
 def test_cutthroat_resists_real_disarm_with_athletics_without_offensive_substitution(self):
  self.family(R.CUT);self.weapon();self.begin(self.t)
  options={'fixed_accuracy':20,'challenger_options':{'fixed':[1]*2},'defender_options':{'fixed':[6]*5}}
  self.assertFalse(self.e.disarm(self.t,self.a,attacker_skill='전투',defender_skill='육상',**options))
  self.assertTrue(self.a.custom_conditions['equipped_weapons'])
  self.next_round();self.weapon(actor=self.b,name='other')
  self.reject(lambda:self.e.disarm(self.a,self.b,attacker_skill='육상',defender_skill='전투',fixed_accuracy=20),'Combat or Stealth')
 def dirty_ready(self):
  self.family(R.DIRTY);self.family(R.CUT);key=self.weapon();self.begin();token=self.hit(weapon_id=key)
  return token
 def test_dirty_fighting_real_weapon_hit_pays_swift_ap_and_skips_only_accuracy(self):
  token=self.dirty_ready();ap=self.a.spec.get('ap_spent',0)
  with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as check:
   self.assertTrue(self.e.dirty_fighting(self.a,self.t,token,'blind',fixed_accuracy=1,challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*5}))
  self.assertEqual(check.call_count,1) # only adjacent third-party opportunity attack
  self.assertEqual(self.a.spec['ap_spent'],ap+1);self.assertEqual(self.a.budget['swift'],0)
  self.assertIn('실명',self.t.conditions);self.assertEqual(self.a._action_history.count('standard'),1)
 def test_dirty_fighting_lost_opposed_check_keeps_payment_and_no_effect(self):
  token=self.dirty_ready()
  self.assertFalse(self.e.dirty_fighting(self.a,self.t,token,'low_blow',challenger_options={'fixed':[1]*5},defender_options={'fixed':[6]*5}))
  self.assertNotIn('취약',self.t.conditions);self.assertEqual(self.a.spec['ap_spent'],1)
 def test_dirty_fighting_plain_move_and_changed_range_reject_before_cost(self):
  self.family(R.DIRTY);self.begin();token=self.hit()
  self.reject(lambda:self.e.dirty_fighting(self.a,self.t,token,'blind'),'Weapon Attack')
  self.setup();token=self.dirty_ready();self.e.gm.set_position(self.t,(7,2),reason='actual target moved away')
  self.reject(lambda:self.e.dirty_fighting(self.a,self.t,token,'blind'),'adjacent')
 def test_dirty_fighting_observed_opposed_retry_preserves_ap_swift_and_first_faces(self):
  self.setup(extra_feats=[SF.MONKEY],target_kind='trainer');self.family(R.DIRTY);self.family(R.CUT)
  key=self.weapon();self.begin();token=self.hit(weapon_id=key)
  def opts(identity,bad=False):return {'roll_id':identity,'fixed':[1]*5,'feature':SF.MONKEY,'feature_options':{'decision':(lambda first:'bad') if bad else (lambda first:True),'reroll_faces':[6]*5}}
  args={'challenger_options':opts('rogue-a'),'defender_options':opts('rogue-b',True)}
  with self.assertRaises(ValueError):self.e.dirty_fighting(self.a,self.t,token,'blind',**args)
  before=(deepcopy(self.a.budget),self.a.spec['ap_spent'],self.e.rng.getstate(),self.a.hp)
  first=SF.event(self.e,self.a,'rogue-a').first;args['defender_options']=opts('rogue-b')
  self.e.dirty_fighting(self.a,self.t,token,'blind',**args)
  self.assertEqual((self.a.budget,self.a.spec['ap_spent'],self.e.rng.getstate(),self.a.hp),before)
  self.assertIs(SF.event(self.e,self.a,'rogue-a').first,first);self.assertNotIn(SM.ACTIVE,self.a.custom_conditions)
 def test_scoundrel_hp_loss_uses_highest_rank_and_temp_hp_policy(self):
  import temporary_hp as TEMP,rogue_fixture as FIXTURE,skill_modifiers as SK
  for ordinary,effective,dice,virtuoso in ((6,6,6,False),(6,8,6,True),(10,10,7,False)):
   self.rules.rulings=deepcopy(self.rules.rulings)
   if ordinary==10:
    self.rules.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.신화',{'rank':10,'dice':'7d6','eng':'Mythic'},reason='Explicit campaign rank ordinal, independent of its seven dice',scope='campaign',rules=self.rules)
   actual=FIXTURE.Combatant
   def actor(rules,spec):
    if spec['name']=='rogue' and virtuoso:
     spec['edges'].append('edge/거장');spec['edge_choices']={'edge/거장':['육상']}
    return actual(rules,spec)
   with patch.object(FIXTURE,'Combatant',side_effect=actor):self.setup(skills={'곡예':5,'육상':ordinary,'은신':5,'전투':2,'집중':3})
   self.family(R.STRIKE);self.assertEqual(R.acquired(self.a,R.CLASS)['snapshot']['ranks']['육상'],ordinary)
   self.assertEqual(SK.rank(self.rules,self.a,'육상')[2],ordinary);self.assertEqual(SK.effective_rank(self.rules,self.a,'육상'),effective)
   roll=self.e.skill_roll(self.a,'육상',fixed=[2]*dice);self.assertEqual((roll.rank,len(roll.faces)),(ordinary,dice))
   self.begin();token=self.hit();before=self.t.hp
   TEMP.grant(self.e,self.t,6,provenance={'test':'actual temporary HP grant'})
   result=self.e.scoundrel_strike(self.a,self.t,token)
   self.assertEqual(result['loss'],2*effective);self.assertEqual(before-self.t.hp,2*effective-6);self.assertEqual(self.t.temp_hp,0)
   self.assertIn('둔화',self.t.conditions);self.assertFalse(TURN.can_aoo(self.e,self.t));self.assertEqual(self.e.move_profile(self.t,'land')[0],3)
   self.restore();self.valid()
 def test_scoundrel_rejects_miss_wrong_move_wrong_actual_recipient(self):
  self.family(R.STRIKE);self.begin();row=self.use(self.a,self.t,'move/도둑질',face=1)
  self.reject(lambda:self.e.scoundrel_strike(self.a,self.t,row['id']),'recipient')
  self.next_round();token=self.use(self.a,self.t,'move/몸통박치기')['id']
  self.reject(lambda:self.e.scoundrel_strike(self.a,self.t,token),'Rogue Move|immediate current attack completion')
  self.next_round();token=self.hit()
  self.reject(lambda:self.e.scoundrel_strike(self.a,self.u,token),'recipient')
 def test_scoundrel_target_scene_quota_and_daily_three_are_separate(self):
  self.family(R.STRIKE)
  targets=[self.t,self.u,self.add('third','pokemon',(1,2),side='foes',species='피카츄'),self.add('fourth','pokemon',(1,3),side='foes',species='피카츄')]
  for i,target in enumerate(targets[:3]):
   self.begin() if i==0 else self.next_round()
   token=self.hit(mid='move/도둑질',target=target);self.e.scoundrel_strike(self.a,target,token)
  self.assertEqual(F.state(self.a)['activations'][R.STRIKE]['used'],3)
  self.next_round();token=self.hit(mid='move/도둑질',target=targets[3])
  self.reject(lambda:self.e.scoundrel_strike(self.a,targets[3],token),'frequency')
 def test_scoundrel_same_target_second_scene_use_rejected_even_new_attack(self):
  self.family(R.STRIKE);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.next_round();token=self.hit(mid='move/도둑질')
  self.reject(lambda:self.e.scoundrel_strike(self.a,self.t,token),'frequency')
 def test_scoundrel_ambush_penalty_reaches_real_skill_accuracy_damage_and_save(self):
  self.family(R.STRIKE);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.assertEqual(self.e.skill_roll(self.t,'집중',fixed=[3]*3).modifier,-2)
  move=self.rules.move('move/몸통박치기')
  with patch.object(Engine,'d20',return_value=6):
   before=self.e.accuracy_check(self.t,self.a,move)[0]
   records=list(TIME.records(self.t));self.t.custom_conditions[TIME.KEY]=[]
   after=self.e.accuracy_check(self.t,self.a,move)[0]
  self.assertFalse(before);self.assertTrue(after)
  self.t.custom_conditions[TIME.KEY]=records
  with patch.object(self.e.rng,'randint',return_value=3):penalized=self.e.roll_damage(self.t,self.a,move,False,False)
  self.t.custom_conditions[TIME.KEY]=[]
  with patch.object(self.e.rng,'randint',return_value=3):ordinary=self.e.roll_damage(self.t,self.a,move,False,False)
  self.assertEqual(ordinary-penalized,2);self.t.custom_conditions[TIME.KEY]=records
  import condition_recovery as REC
  self.e.apply_status(self.t,'마비')
  with patch.object(Engine,'d20',return_value=15):receipt=REC.saving_check(self.e,self.t,'마비',11)
  self.assertEqual(receipt['all_roll_modifier'],-2)
 def test_scoundrel_one_full_round_survives_turn_and_round_end_then_same_count_expires(self):
  self.family(R.STRIKE);self.begin(count=30);self.e.scoundrel_strike(self.a,self.t,self.hit());self.restore()
  self.e.end_of_turn(self.a);self.e.end_round();self.assertIn('둔화',self.t.conditions)
  self.e.start_round(self.e.everyone);self.e.at_initiative_count(31);self.assertIn('둔화',self.t.conditions)
  self.e.at_initiative_count(30);self.assertNotIn('둔화',self.t.conditions);self.assertEqual(TIME.all_roll_modifier(self.t),0);self.valid()
 def test_scoundrel_cruelty_after_each_later_damaging_hit_other_actor_not_initial(self):
  self.family(R.STRIKE,R.CRUELTY);self.begin();token=self.hit();before=self.t.hp
  self.e.scoundrel_strike(self.a,self.t,token);self.assertEqual(before-self.t.hp,10)
  self.turn(self.b,count=20);before=self.t.hp;row=self.use(self.b,self.t,'move/몸통박치기')
  self.assertEqual(before-self.t.hp,MC.recipient_result(row,self.t)['dealt']+5)
 def test_scoundrel_cruelty_miss_and_status_do_not_trigger(self):
  self.family(R.STRIKE,R.CRUELTY);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.turn(self.b,count=20);before=self.t.hp;self.use(self.b,self.t,'move/몸통박치기',face=1);self.assertEqual(self.t.hp,before)
  self.next_round(self.b);before=self.t.hp;self.use(self.b,self.t,'move/째려보기');self.assertEqual(self.t.hp,before)
 def test_underhand_cruelty_uses_existing_real_ability_without_taskmaster(self):
  self.family(R.UNDERHAND,R.CRUELTY);self.begin()
  old=self.e.rulings.provider
  self.e.rulings.provider=lambda prompt:{'desperate':False,'normal_trigger':True,'hp_loss':1,'slowed':False,'healing_block':False} if prompt.get('type')=='cruelty' else None
  self.addCleanup(setattr,self.e.rulings,'provider',old)
  before=self.t.injuries;row=self.use(self.a,self.t,'move/속여때리기')
  self.assertEqual(self.t.injuries,before+1);self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(F.state(self.a)['activations'][R.CRUELTY]['used'],1);self.assertFalse(R.owns(self.a,'class/감독관'))
 def ambush_setup(self,ability):
  self.family(R.UNDERHAND,ability);self.e.prepare_initiative_schedule(self.e.everyone,source='gm/rogue-priority-test');self.e.start_round(self.e.everyone);self.e.at_initiative_count(50)
 def test_core_ambush_real_priority_turn_and_hit_flinch(self):
  self.ambush_setup(R.AMBUSH)
  with patch.object(Engine,'d20',return_value=15):result=self.e.use_ambush(self.a,self.t,'move/속여때리기',ability=R.AMBUSH)
  self.assertEqual(result['source'],R.AMBUSH);self.assertIn('풀죽음',self.t.conditions)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(F.state(self.a)['activations'][R.AMBUSH]['used'],1)
  self.assertFalse(any(r.get('accuracy_modifier') for r in TIME.records(self.t)))
 def test_core_ambush_rejects_ranged_and_printed_db_above_six(self):
  self.ambush_setup(R.AMBUSH)
  self.reject(lambda:self.e.use_ambush(self.a,self.t,'move/전기쇼크',ability=R.AMBUSH),'Melee')
  self.e.gm.set_move(self.a,'move/기습',reason='actual additional learned Move')
  self.reject(lambda:self.e.use_ambush(self.a,self.t,'move/기습',ability=R.AMBUSH),'Damage Base')
 def test_playtest_ambush_allows_ranged_and_adds_exact_accuracy_penalty(self):
  self.ambush_setup(R.PLAYTEST);self.e.gm.set_position(self.t,(6,2),reason='actual ranged target')
  with patch.object(Engine,'d20',return_value=15):self.e.use_ambush(self.a,self.t,'move/전기쇼크',ability=R.PLAYTEST)
  self.assertIn('풀죽음',self.t.conditions)
  self.assertEqual(sum(r.get('accuracy_modifier',0) for r in TIME.records(self.t)),-2)
  self.assertEqual(F.state(self.a)['activations'][R.PLAYTEST]['used'],1)
  move=self.rules.move('move/몸통박치기')
  with patch.object(Engine,'d20',return_value=6):penalized=self.e.accuracy_check(self.t,self.a,move)[0]
  for record in list(TIME.records(self.t)):
   if record.get('source')==R.PLAYTEST:TIME.expire(self.e,self.t,record)
  with patch.object(Engine,'d20',return_value=6):ordinary=self.e.accuracy_check(self.t,self.a,move)[0]
  self.assertFalse(penalized);self.assertTrue(ordinary)
 def test_ambush_wrong_selected_edition_is_not_implicit_alias(self):
  self.ambush_setup(R.AMBUSH)
  self.reject(lambda:self.e.use_ambush(self.a,self.t,'move/속여때리기',ability=R.PLAYTEST),'explicit active')
 def test_reference_sucker_punch_interrupts_real_adjacent_damaging_declaration(self):
  import combat_move_reactions as CMR,action_resources as RES
  self.family(R.UNEXPECTED);self.begin(self.t);CMR.arm(self.e,self.a,'move/기습')
  before=self.t.hp;self.use(self.t,self.a,'move/몸통박치기')
  self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses['move/기습'],1)
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIs(self.e._active_turn_actor,self.t)
  self.restore();self.valid()
 def test_reference_sucker_punch_status_other_target_and_nonadjacent_do_not_trigger(self):
  import combat_move_reactions as CMR
  self.family(R.UNEXPECTED);self.begin(self.t);CMR.arm(self.e,self.a,'move/기습')
  self.use(self.t,self.a,'move/째려보기');self.assertNotIn('move/기습',self.a.move_uses)
  self.next_round(self.t);self.use(self.t,self.b,'move/몸통박치기');self.assertNotIn('move/기습',self.a.move_uses)
  self.next_round(self.t);self.e.gm.set_position(self.t,(6,2),reason='actual distant foe')
  self.use(self.t,self.a,'move/전기쇼크');self.assertNotIn('move/기습',self.a.move_uses)

 def test_sucker_punch_requires_observed_enemy_without_spending_unknown_reaction(self):
  import combat_move_reactions as CMR,action_resources as RES
  for sides in (('absent','absent'),(None,None),(None,'foes'),('party',None),('party','party'),('party','foes')):
   with self.subTest(sides=sides):
    self.setup();self.family(R.UNEXPECTED);self.begin(self.t);CMR.arm(self.e,self.a,CMR.SUCKER)
    for actor,side in zip((self.a,self.t),sides):
     actor.spec.pop('side',None)
     if side=='absent':vars(actor).pop('side',None)
     else:actor.side=side
    self.restore();before=self.t.hp;choice=deepcopy(self.a.spec[CMR.CHOICES][CMR.SUCKER])
    self.use(self.t,self.a,'move/몸통박치기')
    if sides==('party','foes'):
     self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses[CMR.SUCKER],1)
     self.assertEqual(RES.pending(self.a),{'standard':1});self.assertNotIn(CMR.SUCKER,self.a.spec[CMR.CHOICES])
    else:
     self.assertEqual(self.t.hp,before);self.assertNotIn(CMR.SUCKER,self.a.move_uses)
     self.assertEqual(RES.pending(self.a),{});self.assertEqual(self.a.spec[CMR.CHOICES][CMR.SUCKER],choice)
    self.restore();self.valid()
 def test_reference_sucker_punch_cutthroat_keeps_actual_weapon_and_trigger(self):
  import combat_move_reactions as CMR
  self.family(R.UNEXPECTED);self.family(R.CUT);key=self.weapon();self.begin(self.t)
  CMR.arm(self.e,self.a,'move/기습',weapon_id=key);self.use(self.t,self.a,'move/몸통박치기')
  row=next(row for row in self.e._move_completions.values() if row['move_id']=='move/기습')
  self.assertEqual(row['move']['_weapon_attack']['key'],key)
  self.assertEqual(row['move']['id'],'move/기습')
 def test_reference_pursuit_ordinary_db4_has_no_reaction_bonus(self):
  self.family(R.UNEXPECTED);self.begin();row=self.use(self.a,self.t,'move/따라가때리기')
  self.assertEqual(row['move']['damage_base'],4);self.assertEqual(self.e.move_profile(self.a,'land')[0],6)
  self.assertNotIn('방해',row['move'].get('range',''));self.assertNotIn('방해',row['move'].get('keywords',[]))
 def test_reference_pursuit_actual_recall_hits_before_offfield_and_pays_next_standard(self):
  import pokemon_party as PARTY,combat_move_reactions as CMR,action_resources as RES
  self.family(R.UNEXPECTED)
  owner=self.add('foe trainer','trainer',(6,2),side='foes',feats=[],classes=[],edges=[])
  self.t.spec['trainer_id']=owner.entity_id
  PARTY.configure(self.e,owner,mode='standard',reason='actual opponent roster',roster=[self.t],storage={'kind':'center','id':'foe-center'})
  self.e.configure_party_combat(owner,battle_mode='full_contact',reason='actual full contact encounter')
  self.begin(owner);CMR.arm(self.e,self.a,'move/따라가때리기');before=self.t.hp;profiles=[]
  original=Engine.roll_damage
  def damage(engine,attacker,target,move,*args,**kwargs):
   if move['id']=='move/따라가때리기':
    self.assertIn('방해',move['range']);profiles.append((target.on_field,engine.move_profile(attacker,'land')[0],move['damage_base']))
   return original(engine,attacker,target,move,*args,**kwargs)
  with patch.object(Engine,'d20',return_value=15),patch.object(Engine,'roll_damage',new=damage):
   self.e.act_on_party(owner,recall=[self.t],request_id='rogue-recall',reason='actual voluntary recall')
  self.assertLess(self.t.hp,before);self.assertFalse(self.t.on_field)
  self.assertEqual(profiles,[(True,11,8)]);self.assertEqual(RES.pending(self.a),{'standard':1})
  self.assertEqual(self.e.move_profile(self.a,'land')[0],6)
 def test_reference_thief_acquired_move_uses_existing_actual_equipment_transfer(self):
  import items as ITEMS
  self.acquire(R.CLASS);ITEMS.register_item(self.e,self.t,'선제공격손톱')
  self.begin();row=self.use(self.a,self.t,'move/도둑질')
  self.assertTrue(MC.recipient_result(row,self.t)['hit'])
  self.assertTrue(any(r.get('item_id')=='item/선제공격손톱' for r in getattr(self.a,'_item_reg',{}).values()))
  self.assertFalse(getattr(self.t,'_item_reg',{}));self.restore();self.valid()
 def test_reference_assurance_native_damage_and_per_target_scene_limit(self):
  self.family(R.STREET);self.begin(self.b);self.use(self.b,self.t,'move/몸통박치기');self.turn(self.a,count=20)
  seen=[];original=Engine.roll_damage
  def damage(engine,attacker,target,move,*args,**kwargs):
   result=original(engine,attacker,target,move,*args,**kwargs);seen.append(result);return result
  with patch.object(Engine,'roll_damage',new=damage):self.use(self.a,self.t,'move/승부굳히기')
  first=seen[-1];self.next_round(self.b);self.use(self.b,self.t,'move/몸통박치기');self.turn(self.a,count=20)
  with patch.object(Engine,'roll_damage',new=damage):self.use(self.a,self.t,'move/승부굳히기')
  self.assertGreater(first,seen[-1]);self.assertIn('lim:conditional-db:move/승부굳히기:'+self.t.entity_id,self.a.counters)
 def test_scoundrel_followup_after_another_action_is_not_immediate(self):
  self.family(R.STRIKE);self.begin();token=self.hit();TURN.spend(self.e,self.a,'free','actual intervening action')
  self.reject(lambda:self.e.scoundrel_strike(self.a,self.t,token),'immediate')
 def test_underhand_withdrawal_removes_only_granted_ability_and_attack_tag(self):
  import trainer_retraining as RETRAIN,state_grants as G
  self.family(R.UNDERHAND,R.CRUELTY);before=self.a.stats['atk']
  source=RETRAIN.owned_source(self.e,self.a,R.CLASS)
  RETRAIN.retrain(self.e,self.a,R.UNDERHAND,request_id='remove-underhand',reason='actual feature retraining',
   gm_decision={'allowed':True,'reason':'GM approved source-specific removal'},retained_dependencies={source:[]})
  self.assertEqual(self.a.stats['atk'],before-1);self.assertFalse(__import__('ability_transitions').active(self.a,R.CRUELTY))
  self.assertTrue(set(R.MOVES[:2])<=set(self.a.moves));self.restore();self.valid()
 def test_actual_intercept_recipient_drives_scoundrel_not_declared_target(self):
  import passive_events as P,move_defense_reactions as D
  self.family(R.STRIKE);self.e.gm.set_position(self.u,(8,8),reason='actual fixture defender replaces Pokemon');self.u=self.add('actual strike defender','trainer',(3,3),side='foes',feats=[],classes=[],edges=[],speed=40);self.begin()
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':D.MELEE}],reason='actual Rogue recipient test')
  with patch.object(Engine,'d20',return_value=15):
   with self.assertRaises(P.PassiveEventPending):self.e.use_move(self.a,self.t,'move/도둑질',set_damage=True)
  event=self.e._passive_pending
  with patch.object(Engine,'d20',return_value=15):
   self.e.choose_move_defense(event,self.u,use=True,options={'path':[(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6]*5}},reason='actual native interception')
  row=list(self.e._move_completions.values())[-1]
  self.assertIsNone(MC.recipient_result(row,self.t));self.assertTrue(MC.recipient_result(row,self.u)['hit'])
  self.reject(lambda:self.e.scoundrel_strike(self.a,self.t,row['id']),'recipient')
  before=self.u.hp;self.e.scoundrel_strike(self.a,self.u,row['id']);self.assertEqual(before-self.u.hp,10)
 def test_actual_intercept_recipient_keeps_prepared_cutthroat_weapon_for_dirty_fighting(self):
  import passive_events as P,move_defense_reactions as D
  self.family(R.DIRTY);self.family(R.CUT);key=self.weapon();self.e.gm.set_position(self.u,(8,8),reason='actual fixture defender replaces Pokemon');self.u=self.add('actual weapon defender','trainer',(3,3),side='foes',feats=[],classes=[],edges=[],speed=40);self.begin()
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':D.MELEE}],reason='actual Rogue weapon recipient')
  with patch.object(Engine,'d20',return_value=15):
   with self.assertRaises(P.PassiveEventPending):self.e.use_move(self.a,self.t,'move/속여때리기',set_damage=True,weapon_id=key)
  forbidden=self.e._passive_pending
  self.reject(lambda:self.e.choose_move_defense(forbidden,self.u,use=True,options={'path':[(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6]*5}},reason='attempted Intercept forbidden by the actual Feint'),'prohibits Intercept')
  self.e.choose_move_defense(forbidden,self.u,use=False,reason='decline the prohibited Intercept');self.next_round()
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':D.MELEE}],reason='new actual Thief attack after resolved Feint defense')
  with patch.object(Engine,'d20',return_value=15):
   with self.assertRaises(P.PassiveEventPending):self.e.use_move(self.a,self.t,'move/도둑질',set_damage=True,weapon_id=key)
  event=self.e._passive_pending
  with patch.object(Engine,'d20',return_value=15):self.e.choose_move_defense(event,self.u,use=True,options={'path':[(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[4,2],'roll_options':{'fixed':[6]*5}},reason='actual paid interception')
  row=list(self.e._move_completions.values())[-1]
  self.reject(lambda:self.e.dirty_fighting(self.a,self.t,row['id'],'blind'),'recipient')
  self.assertTrue(self.e.dirty_fighting(self.a,self.u,row['id'],'blind',challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*5}))
  self.assertIn('실명',self.u.conditions);self.assertNotIn('실명',self.t.conditions)
 def test_scoundrel_cruelty_actual_zero_damage_hit_still_loses_five(self):
  for type_immunity in (False,True):
   self.setup();self.family(R.STRIKE,R.CRUELTY);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
   self.turn(self.b,count=20);before=self.t.hp
   if type_immunity:
    self.e.gm.set_types(self.t,['고스트'],reason='actual ordinary Normal damage immunity, not cannot-hit');row=self.use(self.b,self.t,'move/몸통박치기')
   else:
    with patch.object(Engine,'roll_damage',return_value=0):row=self.use(self.b,self.t,'move/몸통박치기')
   self.assertTrue(MC.recipient_result(row,self.t)['hit']);self.assertEqual(MC.recipient_result(row,self.t)['dealt'],0);self.assertEqual(before-self.t.hp,5)
 def test_scoundrel_cruelty_two_strike_native_combination_is_one_damaging_attack(self):
  self.family(R.STRIKE,R.CRUELTY);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.turn(self.b,count=20);before=self.t.hp;row=self.use(self.b,self.t,'move/더블어택')
  self.assertEqual(before-self.t.hp,MC.recipient_result(row,self.t)['dealt']+5)
 def test_reference_pursuit_actual_flee_interrupt_precedes_native_shift(self):
  import combat_move_reactions as CMR,movement_actions as M
  self.family(R.UNEXPECTED);self.e.gm.set_level(self.t,5,reason='actual low-level wild target')
  M.set_capabilities(self.e,self.t,{'land':4,'swim':0},basis='current',reason_text='actual observed land movement')
  self.e.use_item(self.a,'item/벌레회피스프레이',aim={'reason':'actual wearer spray'})
  self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='actual close approach to sprayed wearer')
  self.e.observe_relative_directions(self.t,directions={'away':(1,0)},quickly_trip_placement='before_entry',reason='actual understood away direction')
  self.e.observe_repel_flee(self.t,movement={'direction':'away','distance':4,'pace':'quickly','movement_id':'rogue-flee'},reason='actual fastest feasible retreat')
  self.begin(self.t);CMR.arm(self.e,self.a,'move/따라가때리기');before=self.t.hp
  with patch.object(Engine,'d20',return_value=15):result=self.e.resolve_repel_flee(self.t)
  self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses['move/따라가때리기'],1)
  self.assertEqual(self.t.pos,(7,2));self.assertEqual(self.t.budget['shift'],0)
  self.assertEqual(result['status'],'attempted');self.restore();self.valid()

 def test_pursuit_requires_observed_enemy_for_actual_recall_and_flee(self):
  import pokemon_party as PARTY,combat_move_reactions as CMR,action_resources as RES,movement_actions as M
  for kind in ('recall','flee'):
   for sides in (('absent','absent'),(None,None),(None,'foes'),('party',None),('party','party'),('party','foes')):
    with self.subTest(kind=kind,sides=sides):
     self.setup();self.family(R.UNEXPECTED)
     self.e.gm.set_position(self.b,(12,10),reason='uninvolved observer outside the actual flee path')
     self.e.gm.set_position(self.u,(12,11),reason='uninvolved observer outside the actual flee path')
     if kind=='recall':
      owner=self.add('actual recalling owner','trainer',(6,2),side='foes',feats=[],classes=[],edges=[])
      self.t.spec['trainer_id']=owner.entity_id
      PARTY.configure(self.e,owner,mode='standard',reason='actual recall roster',roster=[self.t],storage={'kind':'center','id':'recall-center'})
      self.e.configure_party_combat(owner,battle_mode='full_contact',reason='actual full contact encounter')
      owner_id=owner.entity_id;self.begin(owner)
     else:
      self.e.gm.set_level(self.t,5,reason='actual low-level wild target')
      M.set_capabilities(self.e,self.t,{'land':4,'swim':0},basis='current',reason_text='actual observed land movement')
      self.e.use_item(self.a,'item/벌레회피스프레이',aim={'reason':'actual wearer spray'})
      self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='actual close approach')
      self.e.observe_relative_directions(self.t,directions={'away':(1,0)},quickly_trip_placement='before_entry',reason='actual understood away direction')
      self.e.observe_repel_flee(self.t,movement={'direction':'away','distance':4,'pace':'quickly','movement_id':'side-boundary-flee'},reason='actual fastest feasible retreat')
      self.begin(self.t)
     CMR.arm(self.e,self.a,CMR.PURSUIT)
     for actor,side in zip((self.a,self.t),sides):
      actor.spec.pop('side',None)
      if side=='absent':vars(actor).pop('side',None)
      else:actor.side=side
     self.restore();before=self.t.hp;choice=deepcopy(self.a.spec[CMR.CHOICES][CMR.PURSUIT])
     self.assertEqual(self.a in TURN.adjacent_enemies(self.e,self.t),sides==('party','foes'))
     with patch.object(Engine,'d20',return_value=15):
      if kind=='recall':
       owner=__import__('world_entities').actor_index(self.e)[owner_id]
       self.e.act_on_party(owner,recall=[self.t],request_id='side-boundary-recall',reason='actual voluntary recall')
      else:self.e.resolve_repel_flee(self.t)
     if sides==('party','foes'):
      self.assertLess(self.t.hp,before);self.assertEqual(self.a.move_uses[CMR.PURSUIT],1)
      self.assertEqual(RES.pending(self.a),{'standard':1});self.assertNotIn(CMR.PURSUIT,self.a.spec[CMR.CHOICES])
     else:
      self.assertEqual(self.t.hp,before);self.assertNotIn(CMR.PURSUIT,self.a.move_uses)
      self.assertEqual(RES.pending(self.a),{});self.assertEqual(self.a.spec[CMR.CHOICES][CMR.PURSUIT],choice)
     if kind=='recall':self.assertFalse(self.t.on_field)
     else:self.assertEqual(self.t.pos,(7,2));self.assertEqual(self.t.budget['shift'],0)
     self.restore();self.valid()
 def test_scoundrel_branch_uses_possessed_ability_but_ambush_activation_requires_active(self):
  self.family(R.STRIKE);self.a.abilities_suppressed=True;self.begin();token=self.hit()
  self.e.scoundrel_strike(self.a,self.t,token)
  self.assertIn('둔화',self.t.conditions);self.assertEqual(TIME.all_roll_modifier(self.t),-2)

  self.setup();self.ambush_setup(R.AMBUSH);self.a.abilities_suppressed=True
  self.reject(lambda:self.e.use_ambush(self.a,self.t,'move/속여때리기',ability=R.AMBUSH),'explicit active')

 def test_scoundrel_scene_reset_restores_target_use_but_keeps_daily_count(self):
  self.family(R.STRIKE);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.e.end_of_turn(self.a);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
  self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.assertEqual(F.state(self.a)['activations'][R.STRIKE]['used'],2)
  self.assertEqual(F.state(self.a)['activations'][R.STRIKE+':'+self.t.entity_id]['used'],1)
 def test_ambush_possession_never_applies_flinch_or_db_without_activation(self):
  for ability in (R.AMBUSH,R.PLAYTEST):
   self.setup();self.family(R.UNDERHAND,ability);self.begin();self.hit()
   self.assertNotIn('풀죽음',self.t.conditions)
   self.assertEqual(F.state(self.a)['activations'].get(ability,{}).get('used',0),0)
 def test_reference_sucker_punch_can_answer_real_opportunity_attack_during_own_turn(self):
  import combat_move_reactions as CMR,action_resources as RES
  self.family(R.UNEXPECTED);self.family(R.CUT);key=self.weapon('단거리 사격무기')
  self.e.gm.set_position(self.t,(6,2),reason='actual distant target for ranged Weapon Move')
  self.begin();CMR.arm(self.e,self.a,'move/기습')
  self.use(self.a,self.t,'move/속여때리기',weapon_id=key)
  self.assertEqual(self.a.move_uses['move/기습'],1)
  self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIs(self.e._active_turn_actor,self.a)
  self.assertEqual(self.a.budget['standard'],0);self.restore();self.valid()
 def test_retraining_cannot_remove_actual_rogue_parent_and_keep_dependent_feature(self):
  import trainer_retraining as RETRAIN
  self.family(R.CUT);source=RETRAIN.owned_source(self.e,self.a,R.CUT)
  self.reject(lambda:RETRAIN.retrain(self.e,self.a,R.CLASS,request_id='invalid-parent-removal',reason='attempted source removal',gm_decision={'allowed':True,'reason':'actual GM consultation'},retained_dependencies={source:[]}),'prerequisite')
 def test_scoundrel_cruelty_includes_actual_counter_hp_loss_attack(self):
  import combat_move_reactions as CMR
  self.family(R.STRIKE,R.CRUELTY);self.e.gm.set_move(self.b,'move/카운터',reason='actually learned native Counter')
  self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.turn(self.t,count=20);CMR.arm(self.e,self.b,'move/카운터')
  before_target=self.t.hp;before_counter=self.b.hp
  self.use(self.t,self.b,'move/몸통박치기')
  actual_loss=before_counter-self.b.hp
  self.assertGreater(actual_loss,0);self.assertEqual(before_target-self.t.hp,2*actual_loss+5)
  self.assertEqual(self.b.move_uses['move/카운터'],1);self.restore();self.valid()
 def payback_use(self,expected):
  import conditional_damage_base as DB
  original=DB.override_base;seen=[]
  def observe(engine,attacker,target,move,base):
   value=original(engine,attacker,target,move,base)
   if move['id']=='move/보복':seen.append(value)
   return value
  before=self.t.hp
  with patch.object(DB,'override_base',new=observe):row=self.use(self.a,self.t,'move/보복')
  self.assertTrue(seen);self.assertEqual(set(seen),{expected});self.assertLess(self.t.hp,before)
  self.assertEqual(self.a.move_uses['move/보복'],1);return row
 def test_payback_previous_actual_turn_zero_damage_hit_survives_restore(self):
  for type_immunity in (False,True):
   self.setup();self.family(R.STREET);self.begin(self.t)
   if type_immunity:
    self.e.gm.set_types(self.a,['고스트'],reason='actual ordinary Normal damage immunity, not cannot-hit');hit=self.use(self.t,self.a,'move/몸통박치기')
   else:
    with patch.object(Engine,'roll_damage',return_value=0):hit=self.use(self.t,self.a,'move/몸통박치기')
   self.assertTrue(MC.recipient_result(hit,self.a)['hit']);self.assertEqual(MC.recipient_result(hit,self.a)['dealt'],0)
   self.turn(self.a,count=20);self.restore();self.payback_use(10);self.valid()
 def test_payback_intervening_full_turn_removes_bonus_not_targets_latest_turn(self):
  self.family(R.STREET);self.begin(self.t);self.use(self.t,self.a,'move/몸통박치기')
  self.turn(self.b,count=20);TURN.spend(self.e,self.b,'free','actual intervening action')
  self.turn(self.a,count=10);self.payback_use(5)
 def test_payback_miss_and_status_are_not_damaging_hits(self):
  for mid,face in [('move/몸통박치기',1),('move/째려보기',15)]:
   self.setup();self.family(R.STREET);self.begin(self.t);self.use(self.t,self.a,mid,face=face)
   self.turn(self.a,count=20);self.payback_use(5)
 def test_payback_intercept_uses_actual_hit_recipient_not_declared_target(self):
  import passive_events as P,move_defense_reactions as D
  self.family(R.STREET);self.begin(self.t)
  self.e.gm.set_stat(self.b,'spe',40,reason='actual qualified native interceptor')
  self.e.watch_move_defense(self.a,[{'actor_id':self.b.entity_id,'source':D.MELEE}],reason='actual Payback recipient evidence')
  with patch.object(Engine,'d20',return_value=15):
   with self.assertRaises(P.PassiveEventPending):self.e.use_move(self.t,self.a,'move/몸통박치기',set_damage=True)
  event=self.e._passive_pending
  with patch.object(Engine,'d20',return_value=15):self.e.choose_move_defense(event,self.b,use=True,options={'path':[(2,3),(2,2)],'skill':'육상','mode':'land','shove_destination':[2,1],'roll_options':{'fixed':[6]*5}},reason='native actual Intercept')
  row=list(self.e._move_completions.values())[-1];self.assertIsNone(MC.recipient_result(row,self.a))
  self.turn(self.a,count=20);self.payback_use(5)
 def test_payback_interrupt_hit_uses_suspended_full_turn_not_temporary_actor(self):
  import combat_move_reactions as CMR,conditional_damage_base as DB
  self.family(R.STREET);self.e.gm.set_move(self.t,'move/기습',reason='actual known Sucker Punch')
  self.begin();CMR.arm(self.e,self.t,'move/기습');self.use(self.a,self.t,'move/몸통박치기')
  reply=next(row for row in self.e._move_completions.values() if row['move_id']=='move/기습')
  self.assertIs(reply['full_turn']['actor'],self.a);self.assertIs(reply['actor'],self.t)
  self.assertEqual(len(self.e._turn_closures),0);self.assertFalse(DB.hit_previous_turn(self.e,self.t,self.a))
  self.next_round();self.assertEqual(len(self.e._turn_closures),1)
  self.payback_use(10)
 def test_payback_genuine_priority_full_turn_intervenes_in_global_sequence(self):
  self.family(R.STREET);self.e.gm.set_move(self.b,'move/전광석화',reason='actual learned Priority Move')
  FIELDS.base_patch(self.t,{'stats':dict(self.t.spec['stats'],spe=40)},reason='actual first initiative participant')
  self.e.prepare_initiative_schedule(self.e.everyone,source='gm/payback-actual-turns')
  self.begin(self.t,count=40);self.use(self.t,self.a,'move/몸통박치기');self.e.end_of_turn(self.t)
  with patch.object(Engine,'d20',return_value=15):self.e.use_priority_move(self.b,self.u,'move/전광석화')
  self.e.finish_initiative_reaction();self.assertIs(self.e._turn_closures[-1]['actor'],self.b)
  self.e.start_of_turn(self.a,initiative_count=20);self.payback_use(5)
 def test_sucker_punch_pending_response_restores_and_resumes_paid_incoming_move_once(self):
  import combat_move_reactions as CMR,passive_events as P,initiative_interrupts as I,action_resources as RES
  for intercept in (False,True):
   self.setup();self.family(R.UNEXPECTED);self.e.gm.set_position(self.u,(8,8),reason='fixture native defender replaced by Trainer');self.u=self.add('actual defense trainer','trainer',(3,3),side='foes',feats=[],classes=[],edges=[],speed=40);self.begin(self.t)
   self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual defense of Sucker Punch response')
   CMR.arm(self.e,self.a,'move/기습');hp=(self.a.hp,self.t.hp,self.u.hp)
   with patch.object(Engine,'d20',return_value=15),self.assertRaises(P.PassiveEventPending):self.e.use_move(self.t,self.a,'move/몸통박치기',set_damage=True)
   event=self.e._passive_pending;self.restore()
   options={'path':[(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[3,1],'roll_options':{'fixed':[6]*5}} if intercept else None
   self.e.choose_move_defense(event,self.u,use=intercept,options=options,reason='actual optional response defense')
   self.assertLess(self.a.hp,hp[0]);self.assertLess(self.u.hp if intercept else self.t.hp,hp[2] if intercept else hp[1])
   self.assertEqual(self.a.move_uses['move/기습'],1);self.assertEqual(self.t.move_uses['move/몸통박치기'],1)
   self.assertEqual(self.t.budget['standard'],0);self.assertEqual(RES.pending(self.a),{'standard':1})
   self.assertIsNone(I.frame(self.e));self.assertIs(self.e._active_turn_actor,self.t);self.restore();self.valid()
 def test_pursuit_pending_response_restores_and_completes_original_paid_recall_once(self):
  import pokemon_party as PARTY,party_actions as PA,combat_move_reactions as CMR,passive_events as P,initiative_interrupts as I,action_resources as RES
  for intercept,speed in ((False,40),(True,40),(False,10)):
   self.setup();self.family(R.UNEXPECTED);self.e.gm.set_position(self.u,(8,8),reason='fixture native defender replaced by Trainer');self.u=self.add('actual Pursuit defender','trainer',(3,3),side='foes',feats=[],classes=[],edges=[],speed=speed)
   owner=self.add('recall owner','trainer',(6,2),side='foes',feats=[],classes=[],edges=[]);owner_id=owner.entity_id
   self.t.spec['trainer_id']=owner_id;self.t.spec['wild']=False
   PARTY.configure(self.e,owner,mode='standard',reason='actual opponent roster',roster=[self.t],storage={'kind':'center','id':'foe-center'})
   self.e.configure_party_combat(owner,battle_mode='full_contact',reason='actual encounter');self.begin(owner)
   self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual Pursuit defense')
   CMR.arm(self.e,self.a,'move/따라가때리기')
   with patch.object(Engine,'d20',return_value=15),self.assertRaises(P.PassiveEventPending):self.e.act_on_party(owner,recall=[self.t],request_id='pending-recall',reason='actual voluntary recall')
   event=self.e._passive_pending;self.assertTrue(self.t.on_field);self.assertEqual(owner.budget['shift'],0)
   self.assertIn('pending',owner.spec[PA.KEY]['pending-recall']);self.restore();owner=__import__('world_entities').actor_index(self.e)[owner_id]
   options={'path':[(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[3,1],'roll_options':{'fixed':[6]*5}} if intercept else None
   if speed==10:
    self.reject(lambda:self.e.choose_move_defense(event,self.u,use=True,options={'path':[(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[3,1],'roll_options':{'fixed':[6]*5}},reason='actual too-slow Intercept of the conditional Pursuit Interrupt'),'greater Speed')
   self.e.choose_move_defense(event,self.u,use=intercept,options=options,reason='actual native Pursuit reply')
   self.assertFalse(self.t.on_field);self.assertNotIn('pending',owner.spec[PA.KEY]['pending-recall'])
   self.assertEqual(owner.budget['shift'],0);self.assertEqual(owner._action_history.count('shift'),1)
   self.assertEqual(self.a.move_uses['move/따라가때리기'],1);self.assertEqual(RES.pending(self.a),{'standard':1});self.assertIsNone(I.frame(self.e))
   replay=self.e.act_on_party(owner,recall=[self.t],request_id='pending-recall',reason='actual voluntary recall')
   self.assertEqual(replay['recalled'],[self.t.entity_id]);self.restore();self.valid()
 def test_pursuit_pending_flee_response_resumes_native_shift_once(self):
  import combat_move_reactions as CMR,movement_actions as M,passive_events as P,initiative_interrupts as I
  self.family(R.UNEXPECTED);self.e.gm.set_level(self.t,5,reason='actual low-level wild foe');self.e.gm.set_stat(self.u,'spe',40,reason='actual defense observer')
  M.set_capabilities(self.e,self.t,{'land':4,'swim':0},basis='current',reason_text='actual observed movement')
  self.e.use_item(self.a,'item/벌레회피스프레이',aim={'reason':'actual wearer spray'})
  self.e.observe_repel_approach(self.a,self.t,nearby=True,reason='actual approach')
  self.e.observe_relative_directions(self.t,directions={'away':(1,0)},quickly_trip_placement='before_entry',reason='actual away direction')
  self.e.observe_repel_flee(self.t,movement={'direction':'away','distance':4,'pace':'quickly','movement_id':'pending-flee'},reason='actual fastest feasible retreat')
  self.begin(self.t);self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual optional Pursuit defense');CMR.arm(self.e,self.a,'move/따라가때리기')
  with patch.object(Engine,'d20',return_value=15),self.assertRaises(P.PassiveEventPending):self.e.resolve_repel_flee(self.t)
  event=self.e._passive_pending;self.assertEqual(self.t.budget['shift'],1);self.restore()
  self.e.choose_move_defense(event,self.u,use=False,reason='actual declined defense')
  self.assertEqual(self.t.pos,(7,2));self.assertEqual(self.t.budget['shift'],0);self.assertEqual(self.t._action_history.count('shift'),1)
  self.assertEqual(self.a.move_uses['move/따라가때리기'],1);self.assertIsNone(I.frame(self.e));self.restore();self.valid()
 def test_playtest_ambush_native_pending_keeps_priority_and_actual_hit_effects(self):
  import passive_events as P,initiative_interrupts as I
  self.e.gm.set_stat(self.u,'spe',40,reason='actual defense observer');self.ambush_setup(R.PLAYTEST)
  self.e.watch_move_defense(self.t,[{'actor_id':self.u.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual Ambush recipient choice')
  with patch.object(Engine,'d20',return_value=15),self.assertRaises(P.PassiveEventPending):self.e.use_ambush(self.a,self.t,'move/도둑질',ability=R.PLAYTEST)
  event=self.e._passive_pending;self.restore();self.e.choose_move_defense(event,self.u,use=False,reason='actual declined defense')
  self.assertIn('풀죽음',self.t.conditions);self.assertEqual(TIME.accuracy_modifier(self.t),-2)
  self.assertEqual(F.state(self.a)['activations'][R.PLAYTEST]['used'],1);self.assertEqual(self.a.move_uses['move/도둑질'],1)
  self.assertIsNotNone(I.frame(self.e));self.e.finish_initiative_reaction();self.restore();self.valid()
 def test_payback_includes_genuine_priority_full_turn_hit(self):
  self.family(R.STREET);self.e.gm.set_move(self.t,'move/전광석화',reason='actual learned Priority attack')
  self.e.prepare_initiative_schedule(self.e.everyone,source='gm/payback-borrowed-turn');self.e.start_round(self.e.everyone);self.e.at_initiative_count(30)
  with patch.object(Engine,'d20',return_value=15):self.e.use_priority_move(self.t,self.a,'move/전광석화')
  self.e.finish_initiative_reaction();self.assertEqual(self.e._turn_closures[-1]['kind'],'borrowed')
  self.assertEqual(self.e._turn_closures[-1]['turn_serial'],1)
  self.e.start_of_turn(self.a,initiative_count=20);self.payback_use(10)
 def test_payback_excludes_basic_and_enhanced_struggle_attacks(self):
  for weapon in (False,True):
   self.setup(target_kind='trainer');self.family(R.STREET)
   mid=self.weapon(actor=self.t,name='foe knife') if weapon else 'struggle'
   self.begin(self.t);self.use(self.t,self.a,mid)
   self.turn(self.a,count=20);self.payback_use(5)
 def test_payback_prevented_immunity_is_not_a_zero_damage_hit(self):
  self.family(R.STREET);self.e.gm.set_ability(self.a,'불가사의부적',reason='actual native cannot-hit prevention');self.begin(self.t)
  row=self.use(self.t,self.a,'move/몸통박치기');self.assertFalse(MC.recipient_result(row,self.a)['hit'])
  self.turn(self.a,count=20);self.payback_use(5)
 def test_scoundrel_cruelty_never_triggers_from_prevented_immune_attack(self):
  self.family(R.STRIKE,R.CRUELTY);self.begin();self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.e.gm.set_ability(self.t,'불가사의부적',reason='actual native cannot-hit prevention after the source hit');self.turn(self.b,count=20);before=self.t.hp
  row=self.use(self.b,self.t,'move/몸통박치기');self.assertFalse(MC.recipient_result(row,self.t)['hit']);self.assertEqual(self.t.hp,before)

 def grapple_strike_ready(self):
  self.family(R.STRIKE,R.CRUELTY);self.begin(self.b,count=40)
  self.e.grapple(self.b,self.t,challenger_skill='육상',defender_skill='육상',fixed_accuracy=20,
   challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*5})
  self.turn(self.a,count=30);self.e.scoundrel_strike(self.a,self.t,self.hit())
  self.next_round(self.b,count=40)
 def test_scoundrel_cruelty_native_grapple_struggle_hit_and_replay_apply_once(self):
  for zero in (False,True,'type_immunity'):
   self.setup();self.grapple_strike_ready();before=self.t.hp
   if zero=='type_immunity':
    self.e.gm.set_types(self.t,['고스트'],reason='actual ordinary damage immunity remains an Attack hit');result=self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-hit')
   elif zero:
    with patch.object(Engine,'roll_damage',return_value=0):result=self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-hit')
   else:result=self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-hit')
   self.assertEqual(before-self.t.hp,result['damage']+5)
   if zero:self.assertEqual(result['damage'],0)
   after=self.t.hp;self.restore()
   self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-hit')
   self.assertEqual(self.t.hp,after);self.valid()
 def test_scoundrel_cruelty_native_grapple_prevented_immunity_does_not_trigger(self):
  self.grapple_strike_ready();self.e.gm.set_ability(self.t,'불가사의부적',reason='actual native cannot-hit prevention for grappling Struggle')
  before=self.t.hp;result=self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-immune')
  self.assertEqual(result['damage'],0);self.assertEqual(self.t.hp,before)
  self.restore();self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-immune');self.assertEqual(self.t.hp,before);self.valid()

 def test_payback_actual_burst_extra_turn_uses_its_own_full_turn_hit_history(self):
  import tumbler as TB,initiative_schedule as SCHEDULE,action_lifecycle as ACTION
  for hit_in_extra in (False,True):
   self.setup(target_kind='trainer',target_edges=[TB.ACROBAT],skills={'곡예':6,'육상':5,'은신':5,'집중':3,'전투':2});self.family(R.STREET)
   __import__('movement_actions').set_capabilities(self.e,self.t,{**self.t.spec['movement'],'high_jump':1,'long_jump':3},basis='current',reason_text='GM observes actual current jumping totals before source-owned Tumbler Move learning')
   for uid in (TB.CLASS,TB.AERIAL,TB.FLIP,TB.DEATH,TB.REFLEX,TB.BURST):
    T.acquire_static(self.e,self.t,uid,acquisition_request_id='actual-extra-turn/'+uid)
   self.e.gm.set_stat(self.a,'spe',5,reason='actual Payback user acts after the scheduled extra turn')
   self.e.prepare_initiative_schedule(self.e.everyone,source='combat/initiative')
   initiative=self.e.initiative_value(self.t).value;self.begin(self.t,count=initiative)
   self.rules.rulings.add_answer('burst_of_speed',10,reason='actual source-owned extra full turn at half Initiative or less',scope='scene')
   if not hit_in_extra:self.use(self.t,self.a,'move/몸통박치기')
   self.turn(self.b,count=18);self.turn(self.u,count=14);self.turn(self.t,count=10)
   self.assertEqual(self.t.custom_conditions['combat_turn_serial'],2)
   self.assertIs(ACTION.current_full_turn(self.e)['actor'],self.t)
   if hit_in_extra:
    row=self.use(self.t,self.a,'move/몸통박치기');self.assertEqual(row['full_turn']['turn_serial'],2)
   self.turn(self.a,count=5)
   self.assertEqual(getattr(self.e,SCHEDULE.EXTRA)[0]['status'],'closed')
   self.assertIs(self.e._turn_closures[-1]['actor'],self.t);self.assertEqual(self.e._turn_closures[-1]['turn_serial'],2)
   self.restore();self.payback_use(10 if hit_in_extra else 5);self.valid()

 def test_scoundrel_cruelty_actual_grapple_dodge_preserves_hp_and_signed_once_receipt(self):
  import grapple_state as GRAPPLE
  self.setup(target_kind='trainer');self.grapple_strike_ready()
  self.e.gm.set_ability(self.t,'회피',reason='actual owned source-identified Dodge Ability')
  self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'ability/회피'}],reason='actual native grappling Attack response')
  self.rules.rulings.add_answer('native_attack_dodge',True,reason='actual chosen native Dodge response',scope='scene')
  before=self.t.hp;result=self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-dodge')
  relation=GRAPPLE.relation(self.e,self.b);index=len(relation['history'])-1;event=GRAPPLE.completed_attack_event(self.e,relation['id'],index)
  self.assertEqual(event['result'],'hit_prevented');self.assertEqual(result['damage'],0);self.assertEqual(self.t.hp,before)
  self.assertEqual(relation['history'][index]['attack_followups']['rogue_cruelty']['hp_loss'],0)
  self.assertFalse(F.activation_allowed(self.t,'ability/회피',{'kind':'daily','uses':1},engine=self.e))
  self.restore();self.e.grapple_action(self.b,'attack',request_id='rogue-grapple-dodge');self.assertEqual(self.t.hp,before);self.valid()
