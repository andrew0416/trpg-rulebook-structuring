"""Authored native Laser Focus scenarios for the two complete source definitions."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_event_effects as F
import event_effects as N,effect_instances as E


class LaserFocusSourceTests(unittest.TestCase):
 setUpClass=classmethod(F.EventEffectTests.setUpClass.__func__)
 setUp=F.EventEffectTests.setUp
 add=F.EventEffectTests.add
 held=F.EventEffectTests.held
 restored=F.EventEffectTests.restored
 row=F.EventEffectTests.row
 valid=F.EventEffectTests.valid
 known=F.EventEffectTests.known
 begin=F.EventEffectTests.begin
 next_turn=F.EventEffectTests.next_turn
 cast=F.EventEffectTests.cast
 snap=F.EventEffectTests.snap

 def decision(self,value):
  pending=N.laser_focus_source_choices(self.r)
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  self.assertEqual(pending['obligations'][0]['decision_kind'],'source_conflict')
  return {'value':value,'reason':'GM selects the complete '+value+' Laser Focus source','scope':pending['decision_scope']}

 def choose(self,actor,value,**kw):
  return N.choose_laser_focus_source(self.e,actor,self.decision(value),**kw)

 def fullsnap(self):return self.snap(),deepcopy(vars(self.e.rulings))

 def damage(self,actor,roll=10):
  native=self.e.resolve_attack_damage
  with patch.object(self.e,'d20',return_value=roll),patch.object(self.e,'resolve_attack_damage',wraps=native) as used:
   result=self.e.use_move(actor,self.other,'struggle',set_damage=True)
  return result,[call.args[3] for call in used.call_args_list]

 def test_korean_paid_first_attack_miss_consumes_for_both_actor_kinds(self):
  for kind in ('trainer','pokemon'):
   with self.subTest(kind=kind):
    self.setUp();actor=self.a if kind=='trainer' else self.p
    self.choose(actor,'korean_next_attack');self.known(actor,'예민해지기','울음소리')
    self.begin(actor);self.cast(actor,'예민해지기');record=N.live(actor)[0];uid=record['id']
    self.assertEqual(actor.move_uses[N.LASER],1);self.assertEqual(actor.budget['standard'],0)
    self.next_turn(actor)
    with patch.object(self.e,'d20',return_value=10):self.e.use_move(actor,self.other,'move/울음소리')
    self.assertEqual(N.live(actor)[0]['id'],uid)
    self.next_turn(actor);hp=self.other.hp;uses=actor.move_uses.get('struggle',0)
    _,criticals=self.damage(actor,1)
    self.assertFalse(criticals);self.assertEqual(self.other.hp,hp);self.assertFalse(N.live(actor))
    self.assertEqual((actor.budget['standard'],actor.move_uses['struggle']),(0,uses+1))
    closed=actor.spec[N.HISTORY][-1]
    self.assertEqual((closed['id'],closed[E.KEY]['state']),(uid,'consumed'))
    self.assertEqual(closed[E.KEY]['end_event'],{'kind':'damaging_move_use','move_id':'struggle','move_class':'물리','target_id':self.other.entity_id})
    self.next_turn(actor);_,criticals=self.damage(actor)
    self.assertEqual(criticals,[False]);self.valid()

 def test_english_paid_miss_preserves_then_actual_hit_consumes(self):
  self.choose(self.p,'english_next_successful_attack');self.known(self.p,'예민해지기','울음소리')
  self.begin(self.p);self.cast(self.p,'예민해지기');uid=N.live(self.p)[0]['id'];self.next_turn(self.p)
  with patch.object(self.e,'d20',return_value=10):self.e.use_move(self.p,self.other,'move/울음소리')
  self.assertEqual(N.live(self.p)[0]['id'],uid);self.next_turn(self.p)
  hp=self.other.hp;uses=self.p.move_uses.get('struggle',0);_,criticals=self.damage(self.p,1)
  self.assertFalse(criticals);self.assertEqual(self.other.hp,hp);self.assertEqual(N.live(self.p)[0]['id'],uid)
  self.assertEqual((self.p.budget['standard'],self.p.move_uses['struggle']),(0,uses+1))
  self.next_turn(self.p);_,criticals=self.damage(self.p)
  self.assertEqual(criticals,[True]);self.assertFalse(N.live(self.p))
  closed=self.p.spec[N.HISTORY][-1]
  self.assertEqual((closed['id'],closed[E.KEY]['end_event']['kind']),(uid,'successful_damaging_hit'));self.valid()

 def test_both_source_definitions_share_one_real_area_activation_only(self):
  from grid import Grid
  for source in ('korean_next_attack','english_next_successful_attack'):
   with self.subTest(source=source):
    self.setUp();self.choose(self.p,source);self.known(self.p,'예민해지기','스피드스타')
    self.begin(self.p);self.cast(self.p,'예민해지기');uid=N.live(self.p)[0]['id'];self.next_turn(self.p)
    from engine import Engine
    # Swift is Friendly: both intended recipients are opposing combatants.
    self.e.grid=Grid(8,8);self.a.pos=(2,0)
    self.a.side=self.other.side='opponent';self.e.begin_encounter([self.a])
    observed=[];native=Engine.resolve_attack_damage
    def observe(engine,actor,target,move,crit=False,*args,**kwargs):
     result=native(engine,actor,target,move,crit,*args,**kwargs)
     if actor.entity_id==self.p.entity_id and move['id']=='move/스피드스타':
      observed.append((target.entity_id,crit))
     return result
    with patch.object(Engine,'d20',return_value=10),patch.object(Engine,'resolve_attack_damage',observe):
     self.e.use_move_on(self.p,self.other,'move/스피드스타',[self.p,self.a,self.other])
    self.assertEqual({target for target,crit in observed},{self.a.entity_id,self.other.entity_id})
    self.assertEqual(len(observed),2)
    self.assertTrue(all(crit for target,crit in observed))
    self.assertEqual(self.p.move_uses['move/스피드스타'],1);self.assertEqual(self.p.budget['standard'],0)
    closed=self.p.spec[N.HISTORY][-1];self.assertEqual(closed['id'],uid)
    self.assertEqual(len(closed[E.KEY]['end_event']['activation_targets']),len(observed))
    self.assertEqual(closed[E.KEY]['end_event']['kind'],'damaging_move_use' if source=='korean_next_attack' else 'successful_damaging_hit')
    self.assertFalse(N.live(self.p));self.assertFalse(getattr(self.e,'_move_activation_scopes',[]))
    self.assertFalse(N.critical(self.e,self.p,self.other,self.r.move('struggle'),True))
    before=self.fullsnap()
    with self.assertRaises(ValueError):
     self.e.use_move(self.p,self.other,'move/스피드스타',_activation={'started':True},_shared_accuracy={'targets':(self.other,)},count_use=False)
    self.assertEqual(before,self.fullsnap());self.valid()

 def test_missing_scoped_choice_and_tampered_effect_refuse_before_payment(self):
  self.known(self.p,'예민해지기');self.p.spec.pop(N.LASER_CHOICE);self.begin(self.p);before=self.fullsnap()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,N.LASER)
  self.assertEqual(before,self.fullsnap());self.assertNotIn(N.LASER,self.p.move_uses)
  decision=self.decision('korean_next_attack');decision['scope']=dict(decision['scope'],profile_hash='not-the-actual-profile')
  with self.assertRaises(ValueError):N.choose_laser_focus_source(self.e,self.p,decision)
  self.assertEqual(before,self.fullsnap())
  self.choose(self.p,'english_next_successful_attack');self.cast(self.p,'예민해지기');self.next_turn(self.p)
  record=N.live(self.p)[0];record[N.LASER_CHOICE]['resolution']['values']['variant']='korean_next_attack';before=self.fullsnap()
  with self.assertRaises(ValueError):self.damage(self.p)
  self.assertEqual(before,self.fullsnap())

 def test_later_table_choice_preserves_each_active_and_historical_contract_across_restore(self):
  self.known(self.p,'예민해지기');self.begin(self.p);self.cast(self.p,'예민해지기');english=N.live(self.p)[0]['id']
  self.next_turn(self.p);self.next_turn(self.p);self.choose(self.p,'korean_next_attack');self.cast(self.p,'예민해지기');korean=N.live(self.p)[-1]['id']
  self.assertNotEqual(english,korean);self.next_turn(self.p)
  saved=self.e.gm.snapshot();loaded=self.restored();self.e.gm.restore(saved)
  for e in (self.e,loaded):
   p=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
   target=next(c for c in e.gm.everyone if c.entity_id==self.other.entity_id)
   with patch.object(e,'d20',return_value=1):e.use_move(p,target,'struggle',set_damage=True)
   self.assertEqual([r['id'] for r in N.live(p)],[english]);self.assertEqual(p.spec[N.HISTORY][-1]['id'],korean)
   e.end_of_turn(p);e.start_round([p,target]);e.start_of_turn(p,initiative_count=20)
   native=e.resolve_attack_damage
   with patch.object(e,'d20',return_value=10),patch.object(e,'resolve_attack_damage',wraps=native) as used:
    e.use_move(p,target,'struggle',set_damage=True)
   self.assertEqual([call.args[3] for call in used.call_args_list],[True]);self.assertFalse(N.live(p))
   self.assertEqual([r['id'] for r in p.spec[N.HISTORY]],[korean,english]);self.assertTrue(e.validate_state()['valid'])
  self.assertTrue(self.restored().validate_state()['valid'])

 def test_legacy_current_adoption_keeps_original_identity_and_past_history(self):
  self.known(self.p,'예민해지기','울음소리');self.begin(self.p);self.cast(self.p,'예민해지기');self.next_turn(self.p);self.damage(self.p)
  # Project actual records to the exact pre-repair schema, which has neither
  # source-choice field. This cold legacy fixture does not invent a past choice.
  self.p.spec[N.HISTORY][-1].pop(N.LASER_CHOICE);past=deepcopy(self.p.spec[N.HISTORY])
  self.next_turn(self.p);self.cast(self.p,'예민해지기');record=N.live(self.p)[0];record.pop(N.LASER_CHOICE)
  self.p.spec.pop(N.LASER_CHOICE);original=deepcopy(record);uid=record['id'];self.next_turn(self.p)
  saved=self.e.gm.snapshot();self.assertTrue(self.restored().validate_state()['valid']);self.e.gm.restore(saved)
  with patch.object(self.e,'d20',return_value=10):self.e.use_move(self.p,self.other,'move/울음소리')
  self.assertEqual(N.live(self.p)[0],original);self.assertEqual(self.p.spec[N.HISTORY],past);self.next_turn(self.p)
  before=self.fullsnap()
  with self.assertRaisesRegex(ValueError,'current source adoption'):self.damage(self.p)
  self.assertEqual(before,self.fullsnap());self.assertEqual(N.live(self.p)[0],original)
  decision=self.decision('korean_next_attack')
  N.choose_laser_focus_source(self.e,self.p,decision,legacy_effects=[uid])
  adopted=N.live(self.p)[0];actual=deepcopy(adopted);actual.pop(N.LASER_CHOICE);adoption=actual.pop('laser_focus_adoption')
  self.assertEqual(actual,original);self.assertEqual(adoption,{'kind':'gm_current_adoption','at':self.e.elapsed_seconds})
  self.assertEqual(self.p.spec[N.HISTORY],past);self.assertNotIn(N.LASER_CHOICE,past[0])
  before=self.fullsnap()
  with self.assertRaises(ValueError):N.choose_laser_focus_source(self.e,self.p,decision,legacy_effects=[uid])
  self.assertEqual(before,self.fullsnap());self.damage(self.p,1)
  self.assertFalse(N.live(self.p));self.assertEqual(self.p.spec[N.HISTORY][:-1],past)
  self.assertEqual(self.p.spec[N.HISTORY][-1][E.KEY]['end_event']['kind'],'damaging_move_use')
  self.valid();self.assertTrue(self.restored().validate_state()['valid'])

 def test_source_asset_is_fresh_and_invalid_choice_does_not_commit_gm_receipt(self):
  source=N.definition(self.r,N.LASER)['source_variants']['english_next_successful_attack']['source']
  from source_context import verified_source
  self.assertIn(b'The next successful damaging attack',verified_source(self.r,source,source_root='source-audit'))
  before=self.fullsnap();decision=self.decision('not-a-source-definition')
  with self.assertRaises(ValueError):N.choose_laser_focus_source(self.e,self.p,decision)
  self.assertEqual(before,self.fullsnap())
  # A bounded source-only root proves actual byte freshness without modifying
  # repository assets or constructing another gameplay engine/framework.
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);csv=root/'input/db/moves.csv';csv.parent.mkdir(parents=True)
   csv.write_bytes((Path(self.r.root)/'input/db/moves.csv').read_bytes())
   path=root/source['file'];path.parent.mkdir(parents=True);path.write_bytes(verified_source(self.r,source,source_root='source-audit')+b'changed')
   with patch.object(self.r,'root',str(root)):
    with self.assertRaisesRegex(ValueError,'source changed'):N.laser_focus_source_choices(self.r)
  self.assertEqual(before,self.fullsnap())

 def test_preview_direct_accuracy_and_actual_ability_keep_their_real_consumption_boundaries(self):
  for roll in (18,1):
   with self.subTest(direct_roll=roll):
    self.setUp();self.choose(self.p,'korean_next_attack');self.known(self.p,'예민해지기')
    self.begin(self.p);self.cast(self.p,'예민해지기');uid=N.live(self.p)[0]['id'];self.next_turn(self.p)
    move=self.r.move('struggle');before=self.fullsnap()
    preview=self.e.plan_accuracy_context(self.p,self.other,move)
    self.assertFalse(preview['consumed']);self.assertIsNone(preview['final_outcome']);self.assertEqual(before,self.fullsnap())
    self.e.accuracy_check(self.p,self.other,self.r.move('move/울음소리'),fixed_roll=18)
    self.assertEqual([r['id'] for r in N.live(self.p)],[uid])
    budget=deepcopy(self.p.budget);uses=deepcopy(self.p.move_uses);rng=self.e.rng.getstate()
    hit,nat,crit=self.e.accuracy_check(self.p,self.other,move,fixed_roll=roll)
    self.assertEqual((hit,nat,crit),(roll==18,roll,roll==18));self.assertFalse(N.live(self.p))
    self.assertEqual((self.p.budget,self.p.move_uses,self.e.rng.getstate()),(budget,uses,rng))
    closed=self.p.spec[N.HISTORY][-1];self.assertEqual(closed['id'],uid)
    self.assertEqual(closed[E.KEY]['end_event'],{'kind':'damaging_accuracy_attempt','move_id':'struggle','move_class':'물리','target_id':self.other.entity_id})
    self.assertEqual(self.e.accuracy_check(self.p,self.other,move,fixed_roll=18),(True,18,False))
    self.valid();self.assertTrue(self.restored().validate_state()['valid'])
  # The actual published ability uses the same native leaf with Status class.
  # Its hit must complete normally without spending the damaging-attack source.
  from ruleset import bind_rule_identity
  import effects_ext as EXT
  self.setUp();self.choose(self.p,'korean_next_attack');self.known(self.p,'예민해지기')
  self.e.gm.set_ability(self.p,'현혹',reason='observed acquired published ability')
  self.begin(self.p);self.cast(self.p,'예민해지기');uid=N.live(self.p)[0]['id'];self.next_turn(self.p)
  source=self.r.selection.resolve_name('현혹',('ability/',));effect=bind_rule_identity(self.r.ability_effects['현혹'],source)[0]
  with patch.object(self.e,'d20',return_value=18):EXT.h_attack(self.e,self.p,self.other,effect,{'attacker':self.p,'target':self.other})
  self.assertIn('잠듦',self.other.conditions);self.assertEqual([r['id'] for r in N.live(self.p)],[uid]);self.valid()
  # Two independently produced definitions both finish on this first real hit;
  # the already spent Korean activation must not hide a still-live English one.
  self.setUp();self.known(self.p,'예민해지기');self.begin(self.p);self.cast(self.p,'예민해지기')
  english=N.live(self.p)[0]['id'];self.next_turn(self.p);self.next_turn(self.p);self.choose(self.p,'korean_next_attack');self.cast(self.p,'예민해지기')
  korean=N.live(self.p)[-1]['id'];self.next_turn(self.p);_,criticals=self.damage(self.p,18)
  self.assertEqual(criticals,[True]);self.assertFalse(N.live(self.p))
  self.assertEqual([(r['id'],r[E.KEY]['end_event']['kind']) for r in self.p.spec[N.HISTORY]],[(korean,'damaging_move_use'),(english,'successful_damaging_hit')]);self.valid()

 def test_neither_source_invents_an_encounter_expiry(self):
  for source in ('korean_next_attack','english_next_successful_attack'):
   with self.subTest(source=source):
    self.setUp();self.choose(self.p,source);self.known(self.p,'예민해지기');self.begin(self.p);self.cast(self.p,'예민해지기')
    uid=N.live(self.p)[0]['id'];self.e.end_of_turn(self.p);self.e.end_encounter(round_elapsed_seconds=6)
    self.assertEqual(N.live(self.p)[0]['id'],uid);self.assertNotIn('encounter_end',N.live(self.p)[0])
    self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
    self.begin(self.p);_,criticals=self.damage(self.p)
    self.assertEqual(criticals,[True]);self.assertFalse(N.live(self.p));self.valid()


if __name__=='__main__':unittest.main()
