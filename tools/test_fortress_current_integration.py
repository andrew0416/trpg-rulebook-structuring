"""Fortress restoration against current CQM/recipient/swarm owners. NOT RUN locally."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine
from fortress_fixture import FortressFixture
import fortress as F,combat_timing as TIME,trainer_feature_acquisition as ACQUIRE
import type_ace as TA,turn,frequency as FREQUENCY,state_codec as CODEC,world_entities as WORLD
import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
import test_close_quarters_marking_sources_native as CQM
import test_category2_swarm_transitions as SWARM_FIXTURE


class FortressCurrentIntegrationTests(FortressFixture,unittest.TestCase):
 def cqm(self):
  self.rules.rulings=deepcopy(self.base_rulings)
  f=CQM.CloseQuartersMarkingSourceTests();f.rules=self.rules;f.pair();f.both()
  self.e=f.e;self.edition='supplement'
  self.a=self.actor('actual mixed Fortress',(4,1));self.b=f.b
  return f

 def cold(self,*actors):
  ids=[a.entity_id for a in actors]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=WORLD.actor_index(self.e)
  return [index[uid] for uid in ids]

 def test_korean_cqm_two_markers_survive_fortress_world_and_replace_both_directions(self):
  f=self.cqm();self.acquire(F.CLASS)
  self.assertEqual({r['ace_marker'] for r in F.markers(self.e,self.b)},{f.p,f.v})
  self.assertEqual(F.accuracy(self.e,self.b,self.a),0);self.valid()
  with self.assertRaisesRegex(ValueError,'multiple native Mark'):F.marker(self.e,self.b)
  f.start(self.a,26);self.mark()
  self.assertEqual([r['ace_marker'] for r in F.markers(self.e,self.b)],[self.a])
  self.valid()
  f.next_round(f.p,29);f.native(f.p,f.b,'move/태권당수')
  self.assertEqual(TA.markers(self.e,self.b),[f.p])
  self.assertFalse(any(r.get('fortress_mark') for r in TIME.records(self.b)))
  self.a,self.b,p=self.cold(self.a,self.b,f.p)
  self.assertEqual(TA.markers(self.e,self.b),[p]);self.valid()

 def test_korean_cqm_outgoing_cap_does_not_consume_another_foes_fortress_mark(self):
  f=self.cqm();self.acquire(F.CLASS)
  other=f.add('distinct actual Fortress marked foe','pokemon',(3,3),side='foe')
  self.e.gm.set_position(self.a,(2,3),reason='actual adjacent Fortress targeting position')
  f.start(self.a,26);self.attack(target=other)
  self.e.end_of_turn(self.a,fortress_mark=self.completion)
  f.next_round(f.p,29);f.native(f.p,other,'move/태권당수')
  self.assertEqual(TA.markers(self.e,f.b),[f.p,f.v])
  self.assertIs(F.marker(self.e,other)['ace_marker'],self.a)
  self.assertTrue(F.marker(self.e,other)['fortress_mark'])
  self.assertEqual(f.p.budget['standard'],0);self.valid()
  self.a,other=self.cold(self.a,other);self.valid()
  self.assertIs(F.marker(self.e,other)['ace_marker'],self.a)

 def test_english_guardian_accepts_all_actual_korean_cqm_markers_without_scalar_choice(self):
  f=self.cqm();self.acquire(F.GUARDIAN,mark_scope='original_english_any_mark')
  key=self.weapon();f.start(self.a,26)
  self.assertTrue(F.guardian_mark(self.e,self.a,self.b))
  self.attack(weapon=key,guardian=True)
  self.assertEqual(F.outgoing_penalty(self.b),-5)
  self.assertEqual(set(TA.markers(self.e,self.b)),{f.p,f.v})
  self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(FREQUENCY.state(self.a)['activations'][F.GUARDIAN]['used'],1)
  self.valid();self.a,self.b=self.cold(self.a,self.b);self.valid()
  self.assertEqual(len(F.markers(self.e,self.b)),2)

 def guardian_intercept(self,*,marked=True):
  self.scene(features=(F.GUARDIAN,));key=self.weapon();self.combat()
  if marked:
   self.e.gm.set_position(self.other,(3,1),reason='actual second native volley target')
   volley=turn.equip_weapon(self.e,self.a,{'name':'actual Guardian preparation volley','kind':'단거리 사격무기','grade':'간단','slot':'반대손','moves':['move/일제사격']})
   with patch.object(Engine,'d20',return_value=1):
    self.e.use_move_on(self.a,self.b,'move/일제사격',self.e.everyone,weapon_id=volley,aim=(2,1))
   row=next(reversed(list(self.e._move_completions.values())))
   self.assertIn(self.other,row['targets'])
   self.e.end_of_turn(self.a,fortress_mark=row['id'])
  else:self.mark(weapon=key)
  self.next_turn()
  self.e.gm.set_position(self.other,(2,4),reason='actual ally interceptor approaching the marked foe')
  self.e.watch_move_defense(self.b,[{'actor_id':self.other.entity_id,'source':'maneuver/근접-가로채기'}],
   reason='actual marked foe requests native interception')
  mid=self.a.custom_conditions['equipped_weapons'][key]['struggle_id']
  with patch.object(Engine,'d20',return_value=10):
   with self.assertRaises(PASSIVE.PassiveEventPending):
    self.e.guardian_weapon_attack(self.a,self.b,mid,weapon_id=key,skill='집중')
  event=self.e._passive_pending
  self.guardian_native_use_count=self.a.move_uses[mid]
  self.assertEqual(self.a.budget['swift'],1)
  self.assertFalse(self.a.custom_conditions['fortress_guardian_attack']['paid'])
  self.valid();self.restore();self.valid()
  return key,mid,event

 def intercept(self,event):
  return self.e.choose_move_defense(event,self.other,use=True,
   options={'path':[(2,4),(2,3),(2,2),(2,1)],'skill':'육상','mode':'land',
    'shove_destination':[3,1],'roll_options':{'fixed':[6,6,6,6,6]}},
   reason='actual complete marked recipient interception')

 def test_guardian_cold_defense_resume_uses_actual_marked_recipient_and_pays_once(self):
  key,mid,event=self.guardian_intercept();hp=(self.b.hp,self.other.hp)
  observed=[];original=F.guardian_damage
  def damage(e,a,t,move,packet):
   value=original(e,a,t,move,packet);observed.append((t.entity_id,value));return value
  with patch.object(Engine,'d20',side_effect=AssertionError('resolved accuracy must not reroll')):
   with patch.object(F,'guardian_damage',side_effect=damage):self.intercept(event)
  row=next(reversed(list(self.e._move_completions.values())))
  self.assertEqual(row['targets'],[self.b])
  self.assertIs(row['received'][self.other.entity_id]['actor'],self.other)
  self.assertEqual(self.b.hp,hp[0]);self.assertLess(self.other.hp,hp[1])
  self.assertEqual(F.outgoing_penalty(self.b),0);self.assertEqual(F.outgoing_penalty(self.other),-5)
  self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(self.a._action_history,['standard','swift'])
  self.assertEqual(self.a.move_uses[mid],self.guardian_native_use_count)
  self.assertEqual(FREQUENCY.state(self.a)['activations'][F.GUARDIAN]['used'],1)
  self.assertIn((self.other.entity_id,self.a.staged('def')),observed)
  self.assertNotIn((self.b.entity_id,self.a.staged('def')),observed)
  self.assertNotIn('fortress_guardian_attack',self.a.custom_conditions)
  self.valid();self.restore();self.valid()
  self.rejected(lambda:self.intercept(event))

 def test_guardian_redirect_to_unmarked_actual_recipient_has_no_feature_cost_or_bonus(self):
  key,mid,event=self.guardian_intercept(marked=False);hp=self.b.hp
  self.intercept(event)
  self.assertEqual(self.b.hp,hp);self.assertEqual(F.outgoing_penalty(self.other),0)
  self.assertEqual(self.a.budget['swift'],1)
  self.assertNotIn(F.GUARDIAN,FREQUENCY.state(self.a)['activations'])
  self.assertEqual(self.a.move_uses[mid],self.guardian_native_use_count);self.valid();self.restore();self.valid()

 def test_guardian_routed_heavy_prefix_restore_rejects_forged_recipient_without_repayment(self):
  key,mid,event=self.guardian_intercept()
  self.e.gm.set_injuries(self.other,value=5,reason='actual heavily injured interceptor')
  with self.assertRaises(HEAVY.HeavyPending):self.intercept(event)
  pending=self.e._heavy_pending;scope=self.a.custom_conditions['fortress_guardian_attack']
  self.assertIs(scope['target'],self.b);self.assertIs(scope['recipient'],self.other)
  self.assertIs(self.e._heavy_events[pending]['target'],self.other)
  self.assertEqual(self.a.budget['swift'],0)
  self.assertEqual(FREQUENCY.state(self.a)['activations'][F.GUARDIAN]['used'],1)
  self.valid();self.restore();self.valid()
  scope=self.a.custom_conditions['fortress_guardian_attack'];actual=scope['recipient']
  scope['recipient']=self.b;self.assertFalse(self.e.validate_state()['valid'])
  scope['recipient']=actual;self.valid()
  self.assertEqual(self.e._heavy_pending,pending)
  self.assertEqual(FREQUENCY.state(self.a)['activations'][F.GUARDIAN]['used'],1)
  self.assertEqual(self.a._action_history,['standard','swift'])
  self.assertEqual(self.a.move_uses[mid],self.guardian_native_use_count)
  self.rejected(lambda:self.e.guardian_weapon_attack(self.a,self.b,mid,weapon_id=key,skill='집중'))

 def test_guardian_parent_accuracy_cannot_masquerade_as_actual_defense_recipient(self):
  key,mid,event=self.guardian_intercept()
  scope=self.a.custom_conditions['fortress_guardian_attack']
  row=self.e._move_completions[scope['completion_id']]
  move=row.get('target_moves',{}).get(self.b.entity_id,row['move'])
  self.rejected(lambda:F.guardian_hit(self.e,self.a,self.b,move,row['id'],passive_event=event),
   'recipient producer')
  self.assertEqual(self.a.budget['swift'],1)
  self.intercept(event);self.valid()


class FortressSwarmBoundaryTests(unittest.TestCase):
 setUpClass=classmethod(SWARM_FIXTURE.SwarmTransitionTests.setUpClass.__func__)
 setUp=SWARM_FIXTURE.SwarmTransitionTests.setUp
 configure=SWARM_FIXTURE.SwarmTransitionTests.configure
 open_turn=SWARM_FIXTURE.SwarmTransitionTests.open_turn

 def test_swarm_continuation_never_runs_fortress_end_turn_or_retains_a_mark_request(self):
  import swarm_transitions as SWARM
  self.open_turn(3)
  self.assertTrue(turn.spend(self.e,self.p,'standard','actual first swarm window'))
  before=self.e.export_state()
  with self.assertRaisesRegex(ValueError,'real turn end'):
   self.e.end_of_turn(self.p,fortress_mark='not-a-native-Fortress-completion')
  self.assertEqual(self.e.export_state(),before)
  with patch.object(F,'end_turn',wraps=F.end_turn) as ending:
   result=self.e.end_of_turn(self.p)
  self.assertEqual(result['status'],'swarm_action_pending');ending.assert_not_called()
  self.assertNotIn('fortress_end_turn_mark',self.p.custom_conditions)
  self.e.start_of_turn(self.p,initiative_count=result['initiative'])
  with patch.object(F,'end_turn',wraps=F.end_turn) as ending:
   self.e.end_of_turn(self.p,swarm_continue=False)
  ending.assert_called_once()
  self.assertEqual(SWARM.state(self.p)['swarm_turn']['lifecycle'],'closed')
  self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
