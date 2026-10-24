from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_container_contents as _fixture_test_category2_container_contents
import event_effects as N,effect_instances as E,state_codec as CODEC,turn as TURN,weapon_actions as WEAPONS

class EventEffectTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_container_contents.ContainerContentsTests.setUpClass.__func__)
 add=_fixture_test_category2_container_contents.ContainerContentsTests.add
 held=_fixture_test_category2_container_contents.ContainerContentsTests.held
 restored=_fixture_test_category2_container_contents.ContainerContentsTests.restored
 row=_fixture_test_category2_container_contents.ContainerContentsTests.row
 def snap(self):
  actors=self.e.gm.everyone
  return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in actors],getattr(self.e,'_physical_objects',{}),self.e.log_lines),{id(self.r):self.r,**{id(x):x for x in actors}})
 valid=_fixture_test_category2_container_contents.ContainerContentsTests.valid
 def setUp(self):
  _fixture_test_category2_container_contents.ContainerContentsTests.setUp(self)
  self.e.gm.observe_loyalty(self.p,6,reason='observed native Move obedience')
  self.other.pos=(1,0)
  pending=N.laser_focus_source_choices(self.r)
  for actor in (self.a,self.p):
   N.choose_laser_focus_source(self.e,actor,{'value':'english_next_successful_attack','reason':'explicit English Laser Focus contract for these retained successful-hit scenarios','scope':pending['decision_scope']})
 def known(self,actor,*moves):
  for name in moves:self.e.gm.set_move(actor,'move/'+name,reason='observed known Move before native use')
 def begin(self,actor):self.e.start_round([actor,self.other]);self.e.start_of_turn(actor,initiative_count=20)
 def next_turn(self,actor):self.e.end_of_turn(actor);self.e.start_round([actor,self.other]);self.e.start_of_turn(actor,initiative_count=20)
 def cast(self,actor,name):
  self.e.use_move(actor,actor,'move/'+name)
  self.assertTrue(any(r['source']=='move/'+name for r in N.live(actor)),self.e.log_lines[-4:])
 def test_native_critical_preserves_misses_status_and_other_effect_then_consumes_actual_hit(self):
  self.known(self.p,'예민해지기');self.begin(self.p);self.cast(self.p,'예민해지기');uid=N.live(self.p)[0]['id']
  raw=self.r.move_mech('move/도우미')[0]['effects_exec'][0]
  self.e.apply_effect(self.other,self.p,raw,20,True,0,'move/도우미')
  self.assertEqual(N.live(self.p)[0]['id'],uid);self.assertIn('damage',__import__('roll_effects').remaining(__import__('roll_effects').live(self.p)[0]))
  self.assertFalse(self.e.accuracy_check(self.p,self.other,self.r.move('struggle'),fixed_roll=1)[0]);self.assertEqual(len(N.live(self.p)),1)
  self.e.accuracy_check(self.p,self.other,self.r.move('move/울음소리'),fixed_roll=20);self.assertEqual(len(N.live(self.p)),1)
  self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
  hit,nat,crit=self.e.accuracy_check(self.p,self.other,self.r.move('struggle'),fixed_roll=18)
  self.assertTrue(hit and crit);self.assertFalse(N.live(self.p));self.assertIn('damage',__import__('roll_effects').remaining(__import__('roll_effects').live(self.p)[0]))
  closed=self.p.spec[N.HISTORY][-1];self.assertEqual((closed['id'],closed[E.KEY]['state']),(uid,'consumed'))
  self.valid();self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
 def test_native_laser_focus_damage_and_usage_for_both_actor_kinds(self):
  for actor_kind in ('trainer','pokemon'):
   with self.subTest(actor_kind=actor_kind):
    self.setUp();actor=self.a if actor_kind=='trainer' else self.p;self.known(actor,'예민해지기');self.begin(actor);self.cast(actor,'예민해지기')
    self.assertEqual(actor.move_uses['move/예민해지기'],1);self.assertEqual(actor.budget['standard'],0)
    self.next_turn(actor)
    with patch.object(self.e,'d20',return_value=18):self.e.use_move(actor,self.other,'struggle',set_damage=True)
    self.assertFalse(N.live(actor));self.assertEqual(actor.spec[N.HISTORY][-1][E.KEY]['end_event']['kind'],'successful_damaging_hit');self.valid()
 def test_charge_and_victory_windows_keep_immediate_stages_and_expire_on_exact_owner_turn(self):
  for source,attack,stat in [('충전','전기쇼크','spd'),('승리의춤','태권당수','def')]:
   with self.subTest(source=source):
    self.setUp();self.known(self.p,source,attack);self.begin(self.p);self.cast(self.p,source);row=N.live(self.p)[0];self.assertEqual(self.p.stages[stat],1)
    move=self.r.move('move/'+attack);self.assertFalse(N.extra_rolls(self.e,self.p,move,move['type']))
    self.e.gm.restore(self.e.gm.snapshot());self.next_turn(self.p);self.assertEqual(len(N.extra_rolls(self.e,self.p,move,move['type'])),1)
    with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'move/'+attack,set_damage=True)
    self.assertEqual(len(N.live(self.p)[0]['applications']),1);self.assertEqual(len(N.live(self.p)),1)
    self.e.gm.restore(self.e.gm.snapshot());loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
    self.assertIs(N.live(p)[0]['turn_owner'],p);loaded.end_of_turn(p);self.assertFalse(N.live(p));self.assertTrue(loaded.validate_state()['valid'])
    self.e.end_of_turn(self.p);self.assertFalse(N.live(self.p));self.assertEqual(self.p.spec[N.HISTORY][-1][E.KEY]['state'],'expired');self.valid()
 def test_extra_damage_roll_uses_actual_type_and_critical_adds_third_roll(self):
  self.known(self.p,'충전');self.begin(self.p);self.cast(self.p,'충전');self.next_turn(self.p);move=self.r.move('move/전기쇼크')
  db=self.e.damage_base(self.p,move);entry=self.r.mech('combat/damage-chart')['by_damage_base'][str(db)];delta=entry['set']['mid']
  base=self.e.roll_damage(self.p,self.other,move,crit=False,set_damage=True)
  crit=self.e.roll_damage(self.p,self.other,move,crit=True,set_damage=True);self.assertEqual(crit-base,delta)
  self.assertEqual(len(N.live(self.p)[0]['applications']),2)
  wrong=self.r.move('move/화염방사');self.assertFalse(N.extra_rolls(self.e,self.p,wrong,'불꽃'))
  self.p.type_override_next='전기';before=self.p.type_override_next;actual=__import__('effects_ext').effective_type(self.e,self.p,self.other,wrong,self.r.move_mech(wrong['id'])[0],consume=False)
  self.assertEqual(self.p.type_override_next,before);self.assertEqual(len(N.extra_rolls(self.e,self.p,wrong,actual)),1)
  self.e.roll_damage(self.p,self.other,wrong,set_damage=True);self.assertIsNone(self.p.type_override_next);self.assertEqual(len(N.live(self.p)[0]['applications']),3)
 def test_zeroing_in_requires_actual_weapon_move_not_weapon_struggle_or_plain_move(self):
  actor=self.a;actor.spec['skills']['전투']='숙련';self.known(actor,'정조준')
  key=TURN.equip_weapon(self.e,actor,{'name':'observed aiming sword','kind':'소형 근접무기','grade':'간단','moves':['정조준']})
  TURN.equip_weapon(self.e,actor,{'name':'observed strike sword','kind':'소형 근접무기','grade':'간단','slot':'반대손','moves':['강타']})
  self.begin(actor);self.cast(actor,'정조준');self.assertEqual(actor.accuracy_stage,1);self.next_turn(actor)
  plain=self.r.move('move/전기쇼크');self.assertFalse(N.extra_rolls(self.e,actor,plain,plain['type']))
  weapon_struggle=WEAPONS.prepare(self.e,actor,self.r.move(key));self.assertFalse(N.extra_rolls(self.e,actor,weapon_struggle,weapon_struggle['type']))
  actual=WEAPONS.prepare(self.e,actor,self.r.move('move/강타'));self.assertEqual(len(N.extra_rolls(self.e,actor,actual,actual['type'])),1)
  self.e.gm.restore(self.e.gm.snapshot());loaded=self.restored();restored_actor=next(c for c in loaded.gm.everyone if c.entity_id==actor.entity_id);restored_target=next(c for c in loaded.gm.everyone if c.entity_id==self.other.entity_id)
  with patch.object(loaded,'d20',return_value=18):loaded.use_move(restored_actor,restored_target,'move/강타',set_damage=True)
  self.assertEqual(len(N.live(restored_actor)[0]['applications']),1);self.assertTrue(loaded.validate_state()['valid'])
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(actor,self.other,'move/강타',set_damage=True)
  self.assertEqual(N.live(actor)[0]['applications'][0]['move_id'],'move/강타');self.valid()
 def test_invalid_payload_lifetime_and_foreign_timing_owner_reject_before_live_restore(self):
  self.known(self.p,'충전');self.begin(self.p);self.cast(self.p,'충전');row=N.live(self.p)[0];good=deepcopy(row,{id(self.p):self.p});uid=row['id']
  for field,value in [('effect',{'kind':'extra_damage_roll','amount':9}),('turn_owner',self.other),('turn_deadline',True)]:
   row.clear();row.update(deepcopy(good,{id(self.p):self.p}));row[field]=value
   with self.assertRaises(ValueError):self.e.gm.snapshot()
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with patch.object(E,'validate_actor',return_value=True),patch.object(E,'validate_world',return_value=True):
   bad=self.e.gm.snapshot('bad-future');payload=json.loads(json.dumps(CODEC.dump_engine(self.e)))
  row.clear();row.update(good);before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.restore(bad)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  self.assertEqual(before,self.snap());self.assertEqual(N.live(self.p)[0]['id'],uid)
  with self.assertRaises(ValueError):self.e.gm.add_buff(self.p,deepcopy(row,{id(self.p):self.p}),reason='wrong native family container')
  self.assertEqual(before,self.snap())
  row['effect']['amount']=True;before=self.snap()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.other,'struggle',set_damage=True)
  self.assertEqual(before,self.snap())
 def test_next_turn_admission_and_wrong_dice_do_not_spend_or_consume_pending_effect(self):
  self.known(self.p,'충전');before=self.snap()
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.p,'move/충전')
  self.assertEqual(before,self.snap());self.begin(self.p);self.cast(self.p,'충전');self.next_turn(self.p);before=self.snap()
  with self.assertRaises(ValueError):self.e.roll_damage(self.p,self.other,self.r.move('move/전기쇼크'),fixed_dice=[True])
  self.assertEqual(before,self.snap());self.assertFalse(N.live(self.p)[0]['applications'])
 def test_one_native_multi_target_activation_retains_critical_for_all_hits_and_cannot_replay(self):
  self.known(self.p,'예민해지기','스피드스타');self.begin(self.p);self.cast(self.p,'예민해지기');uid=N.live(self.p)[0]['id'];self.next_turn(self.p)
  from grid import Grid
  from engine import Engine
  self.e.grid=Grid(8,8);self.a.pos=(2,0);self.a.side=self.other.side='opponent';self.e.begin_encounter([self.a])
  real=Engine.resolve_attack_damage;calls=[]
  def observe(engine,actor,target,move,crit=False,*args,**kwargs):
   result=real(engine,actor,target,move,crit,*args,**kwargs)
   if actor.entity_id==self.p.entity_id and move['id']=='move/스피드스타':calls.append((target.entity_id,crit))
   return result
  with patch.object(Engine,'d20',return_value=10),patch.object(Engine,'resolve_attack_damage',observe):
   self.e.use_move_on(self.p,self.other,'move/스피드스타',[self.p,self.a,self.other])
  self.assertEqual({target for target,crit in calls},{self.a.entity_id,self.other.entity_id});self.assertEqual(len(calls),2);self.assertTrue(all(crit for target,crit in calls))
  history=self.p.spec[N.HISTORY];self.assertEqual(len(history),1);self.assertEqual(history[0]['id'],uid);self.assertEqual(len(history[0][E.KEY]['end_event']['activation_targets']),len(calls))
  self.assertFalse(N.live(self.p));self.assertFalse(N.critical(self.e,self.p,self.other,self.r.move('struggle'),True));self.assertFalse(getattr(self.e,'_move_activation_scopes',[]));self.valid();self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
 def test_expired_empty_window_and_native_ids_are_not_reused_after_restore(self):
  self.known(self.p,'충전');self.begin(self.p);self.cast(self.p,'충전');old=N.live(self.p)[0]['id'];self.next_turn(self.p);self.e.end_of_turn(self.p)
  self.assertFalse(N.live(self.p));self.assertFalse(self.p.spec[N.HISTORY][-1]['applications']);self.e.gm.restore(self.e.gm.snapshot());self.assertTrue(self.restored().validate_state()['valid'])
  self.e.start_round([self.p,self.other]);self.e.start_of_turn(self.p);self.cast(self.p,'충전');self.assertNotEqual(N.live(self.p)[0]['id'],old)

if __name__=='__main__':unittest.main()
