"""Native state contracts for Sticky Hold and Leek Mastery, including consent."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
import items as I,world_entities as W,state_grants as G,equipment_actions as E,equipment_protection as P
import common_checks as C,frequency as FREQ,effects as FX,turn as TURN

class ProtectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def fixture(self,move='도둑질',held=(None,'대파'),abilities=((),('대파의달인',))):
  e=Engine(self.r,0);mid=self.r.move_id(move);actors=[]
  for i,item in enumerate(held):
   c=Combatant(self.r,build_pokemon(self.r,'파오리',30,name='P'+str(i),moves=[mid],abilities=[],wild=True,pos=(i,0)))
   actors.append(c)
  e.everyone=e.gm.everyone=actors;e.grid=Grid(10,10)
  for i,c in enumerate(actors):e.gm.add_combatant(c,side='party' if i==0 else 'foe',reason='observed sides of actual equipment attack participants')
  for i,(c,item) in enumerate(zip(actors,held)):
   if item:
    c.item=item;c.spec['item']=item;uid='object/'+str(i)
    W.register_object(e,uid,location={'kind':'unknown'},reason='actual observed held instance',kind='item_instance',item_rule_id='item/'+item,owner_id=c.entity_id)
    I.register_item(e,c,item,source_instance_id=uid,as_held=True)
   G.replace_baseline(e,c,'abilities',list(abilities[i]))
  return e,*actors,mid
 def valid(self,e):self.assertTrue(e.validate_state()['valid'],e.validate_state()['issues'])
 def roundtrip(self,e):return Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
 def test_sticky_blocks_actual_drop_steal_covet_pluck_switcheroo_and_bestow(self):
  for move in ('탁쳐서떨구기','도둑질','탐내기','쪼아대기','바꿔치기','기프트패스'):
   with self.subTest(move=move):
    own=move=='기프트패스';held=('선제공격손톱',None) if own else (None,'선제공격손톱');abilities=(('점착',),()) if own else ((),('점착',))
    e,a,b,mid=self.fixture(move,held,abilities);before=deepcopy(e._physical_objects);e.use_move(a,b,mid)
    self.assertEqual((a.item,b.item),held[::-1] if own else held)
    if not own:self.assertEqual(e._physical_objects,before)
    self.assertFalse(E.pending(e));self.valid(e)
 def test_sticky_exchange_two_actual_targets_after_hits_and_reactions_cost_nothing(self):
  e,a,b,c,mid=self.fixture('트릭',held=(None,'선제공격손톱',None),abilities=((),('점착',),()))
  result=e.use_move_on(a,b,mid,e.everyone,equipment_options={'targets':[b,c]})
  self.assertTrue(all(result['hits'].values()));self.assertFalse(result['result']['changed']);self.assertEqual(b.item,'선제공격손톱');self.assertIsNone(c.item)
  for ability in ('매지션','나쁜손버릇'):
   e,a,b,mid=self.fixture('몸통박치기',held=(None,'선제공격손톱') if ability=='매지션' else ('선제공격손톱',None),abilities=((ability,),('점착',)) if ability=='매지션' else (('점착',),(ability,)))
   holder=a if ability=='매지션' else b;before=deepcopy(holder.spec.get('frequency_state',{}));e.use_move(a,b,mid)
   self.assertFalse(E.pending(e));self.assertEqual(holder.spec.get('frequency_state',{}).get('activations',{}),before.get('activations',{}));self.assertIsNone(holder.item);self.valid(e)
 def test_sticky_direct_removal_and_disarm_reject_before_cost_rng_or_instance_change(self):
  e,a,b,mid=self.fixture(held=(None,'선제공격손톱'),abilities=((),('점착',)));before=deepcopy(e._physical_objects);rng=e.rng.getstate()
  for action in (lambda:I.transfer_equipment(e,b,a,'object/1'),lambda:I.exchange_items(e,a,b),lambda:I.drop_item(e,b),lambda:I.destroy_equipment(e,b,'object/1',reason='observed destruction'),lambda:I.drop_item(e,b,consent_by=(b,))):
   with self.assertRaises(P.ProtectedEquipment):action()
  self.assertFalse(e.disarm(a,b,attacker_skill='전투',defender_skill='은신'))
  self.assertEqual(e.rng.getstate(),rng);self.assertEqual(e._physical_objects,before);self.assertFalse(getattr(a,'_action_history',[]));self.valid(e)
 def test_sticky_incinerate_cannot_choose_drop_but_hp_alternative_is_once(self):
  e,a,b,mid=self.fixture('불태우기',held=(None,'선제공격손톱'),abilities=((),('점착',)));e.use_move(a,b,mid);row=E.pending(e)[0];hp=b.hp
  with self.assertRaises(P.ProtectedEquipment):E.resolve(e,b,row['id'],choice='drop')
  self.assertEqual(b.hp,hp);self.assertEqual(b.item,'선제공격손톱');E.resolve(e,b,row['id'],choice='hp_loss');self.assertEqual(hp-b.hp,e.tick(b));self.valid(e)
 def test_leek_actual_hit_asks_holder_wrong_actor_rejected_and_refusal_has_no_transfer(self):
  for move in ('도둑질','탁쳐서떨구기','쪼아대기','탐내기','바꿔치기'):
   e,a,b,mid=self.fixture(move);obj=e._physical_objects['object/1'];e.use_move(a,b,mid);row=E.pending(e)[0]
   self.assertIs(row['chooser'],b);self.assertEqual(row['phase'],'removal_consent');self.assertEqual(b.item,'대파');self.assertIs(obj,e._physical_objects['object/1'])
   with self.assertRaises(ValueError):E.resolve(e,a,row['id'],consent=True)
   E.resolve(e,b,row['id'],consent=False);self.assertEqual(b.item,'대파');self.assertIsNone(a.item);self.assertFalse(E.pending(e));self.valid(e)
 def test_leek_actual_consent_transfers_or_drops_preserving_identity_and_owner(self):
  for move in ('도둑질','탁쳐서떨구기','쪼아대기','탐내기','바꿔치기','기프트패스'):
   own=move=='기프트패스';e,a,b,mid=self.fixture(move,held=('대파',None) if own else (None,'대파'),abilities=(('대파의달인',),()) if own else ((),('대파의달인',)))
   holder=a if own else b;uid='object/0' if own else 'object/1';obj=e._physical_objects[uid];e.use_move(a,b,mid);row=E.pending(e)[0];result=E.resolve(e,holder,row['id'],consent=True)
   self.assertEqual(E.resolve(e,holder,row['id'],consent=True),result);self.assertIs(e._physical_objects[uid],obj);self.assertEqual(obj['owner_id'],holder.entity_id);self.assertIsNone(holder.item)
   if move=='탁쳐서떨구기':self.assertNotIn('equipped_by',obj)
   else:self.assertEqual((b if own else a).item,'대파')
   self.valid(e)
 def test_leek_reaction_holder_consent_precedes_free_and_frequency_and_refusal_preserves_both(self):
  for allow in (False,True):
   e,a,b,mid=self.fixture('몸통박치기',abilities=(('매지션',),('대파의달인',)));e.use_move(a,b,mid);row=E.pending(e)[0]
   before=deepcopy(a.spec.get('frequency_state',{}));actions=deepcopy(a._action_history)
   note=E.resolve(e,a,row['id'],accept=True);self.assertIsInstance(note,C.PendingDecision);self.assertIs(row['chooser'],b)
   self.assertEqual(a.spec.get('frequency_state',{}),before);self.assertEqual(a._action_history,actions)
   E.resolve(e,b,row['id'],consent=allow);self.assertEqual(a.item,'대파' if allow else None)
   self.assertEqual(FREQ.activation_allowed(a,'ability/매지션',e.r.ability_freq['매지션'],engine=e),not allow)
   if not allow:self.assertEqual(a._action_history,actions)
   self.valid(e)
 def test_leek_trick_two_holders_require_both_and_hit_consent_is_not_removal_consent(self):
  e,a,b,c,mid=self.fixture('트릭',held=(None,'대파','대파'),abilities=((),('대파의달인',),('대파의달인',)))
  a.side=b.side=c.side='party';before=e.rng.getstate();result=e.use_move_on(a,b,mid,e.everyone,equipment_options={'targets':[b,c],'consenting':[b,c]})
  self.assertEqual(e.rng.getstate(),before);row=E.pending(e)[0];self.assertIs(row['chooser'],b);E.resolve(e,b,row['id'],consent=True);self.assertIs(E.pending(e)[0]['chooser'],c)
  self.assertEqual(b._item_reg['대파']['instance_id'],'object/1');E.resolve(e,c,row['id'],consent=True)
  self.assertEqual(b._item_reg['대파']['instance_id'],'object/2');self.assertEqual(c._item_reg['대파']['instance_id'],'object/1');self.assertEqual(a.move_uses[mid],1);self.valid(e)
 def test_pending_holder_gm_and_codec_preserve_actual_references_then_resume_once(self):
  for move in ('도둑질','바꿔치기','트릭'):
   e,a,b,mid=self.fixture(move)
   if move=='트릭':e.use_move_on(a,b,mid,e.everyone,equipment_options={'targets':[a,b]})
   else:e.use_move(a,b,mid)
   row=E.pending(e)[0];e.gm.snapshot('holder-choice');E.resolve(e,b,row['id'],consent=True);e.gm.restore('holder-choice',reason='review actual holder decision')
   loaded=self.roundtrip(e);index=W.actor_index(loaded);saved=E.pending(loaded)[0];self.assertIs(saved['chooser'],index[b.entity_id]);self.assertIs(saved['permission_holders'][0],index[b.entity_id])
   E.resolve(loaded,index[b.entity_id],saved['id'],consent=True);self.assertEqual(index[a.entity_id].item,'대파');self.valid(loaded)
 def test_leek_disarm_is_prohibited_before_cost_even_though_other_removal_allows_consent(self):
  e,a,b,mid=self.fixture();rng=e.rng.getstate();result=e.disarm(a,b,attacker_skill='전투',defender_skill='은신')
  self.assertFalse(result);self.assertEqual(e.rng.getstate(),rng);self.assertFalse(getattr(a,'_action_history',[]));self.assertEqual(b.item,'대파')
  with self.assertRaises(P.ProtectedEquipment):P.require(e,b,I.equipment_options(b,('held',))[0],'disarm',(b,))
  self.valid(e)
 def test_suppression_removes_protection_and_nonleek_has_no_leek_exception(self):
  for name,item in (('대파의달인','대파'),('점착','선제공격손톱')):
   e,a,b,mid=self.fixture(held=(None,item),abilities=((),(name,)));b.abilities_suppressed=True;e.use_move(a,b,mid);self.assertEqual(a.item,item);self.assertFalse(E.pending(e));self.valid(e)
  e,a,b,mid=self.fixture(held=(None,'선제공격손톱'));e.use_move(a,b,mid);self.assertEqual(a.item,'선제공격손톱');self.assertFalse(E.pending(e))
 def test_acrobatics_leek_exception_uses_actual_move_only_and_native_damage(self):
  for item,ability,expected in (('대파','대파의달인',13),('대파',None,8),('선제공격손톱','대파의달인',8),(None,None,13)):
   e,a,b,mid=self.fixture('애크러뱃',held=(item,None),abilities=((ability,) if ability else (),()))
   self.assertEqual(e.damage_base(a,e.r.move(mid)),expected)
   self.assertEqual(FX.cond_ok(e,{'if':'user holds nothing'},{'attacker':a,'move':e.r.move('move/도둑질')})[0],item is None)
   hp=b.hp;damage=e.use_move(a,b,mid);self.assertGreater(damage,0);self.assertEqual(hp-b.hp,damage)
   if ability and item=='대파':a.abilities_suppressed=True;self.assertEqual(e.damage_base(a,e.r.move(mid)),8)
 def test_native_skill_observation_identity_survives_failed_and_successful_equipment_transition(self):
  import skill_feature_actions as SF
  from dataclasses import replace
  e,a,b,mid=self.fixture(held=(None,'선제공격손톱'),abilities=((),()))
  first=e.skill_roll(a,'전투',roll_id='native-roll')
  final=C.AdjustedSkillRoll(first.rank,first.faces,first.modifier,first.helper_rank,first.penalties,first.helper_bonus,dice_count=len(first.faces))
  e._ap_rolls['native-roll']['skill_event']=replace(SF.event(e,a,'native-roll'),final=final)
  observed_values=(first.faces,final.faces)
  for fail in (True,False):
   def apply(staged,c):
    self.assertIs(staged._ap_rolls['native-roll']['skill_event'].first,first)
    self.assertIs(staged._ap_rolls['native-roll']['skill_event'].final,final)
    self.assertIsNot(staged._ap_rolls['native-roll']['skill_event'].actor,a)
    c.spec['transition_marker']=True
    if fail:raise ValueError('observed failure after staging')
   if fail:
    with self.assertRaises(ValueError):G.transition(e,a,apply)
    self.assertNotIn('transition_marker',a.spec)
   else:G.transition(e,a,apply)
   self.assertIs(SF.event(e,a,'native-roll').first,first);self.assertIs(SF.event(e,a,'native-roll').final,final)
   self.assertEqual((first.faces,final.faces),observed_values)
 def test_protection_restore_and_actual_source_revocation_have_no_stale_lock(self):
  for name,item in (('점착','선제공격손톱'),('대파의달인','대파')):
   e,a,b,mid=self.fixture(held=(None,item),abilities=((),(name,)));e.gm.snapshot('protected');e.gm.restore('protected',reason='restore selected source protection')
   loaded=self.roundtrip(e);who=W.actor_index(loaded)[b.entity_id]
   with self.assertRaises((P.ProtectedEquipment,P.EquipmentConsentRequired)):I.drop_item(loaded,who)
   G.replace_baseline(loaded,who,'abilities',[]);I.drop_item(loaded,who);self.assertIsNone(who.item);self.valid(loaded)
 def test_destroyed_instance_is_preserved_but_unusable_and_leek_requires_consent(self):
  e,a,b,mid=self.fixture();obj=e._physical_objects['object/1']
  with self.assertRaises(P.EquipmentConsentRequired):I.destroy_equipment(e,b,'object/1',reason='actual resolved destruction')
  I.destroy_equipment(e,b,'object/1',reason='actual resolved destruction',consent_by=(b,));self.assertIs(obj,e._physical_objects['object/1']);self.assertIsNone(b.item);self.assertTrue(obj['destroyed']);self.valid(e)
  with self.assertRaises(ValueError):I.register_item(e,b,'대파',source_instance_id='object/1',as_held=True)
  loaded=self.roundtrip(e);self.assertEqual(loaded._physical_objects['object/1']['destroyed'],obj['destroyed'])
  loaded._physical_objects['object/1']['equipped_by']=b.entity_id
  self.assertIn('destroyed_equipment_registered',{x['code'] for x in loaded.validate_state()['issues']})

if __name__=='__main__':unittest.main(verbosity=2)
