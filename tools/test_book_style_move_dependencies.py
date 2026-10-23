"""Native effects and consumption boundaries of Style Expert's Move dependencies."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_style_expert_full as fixture
from engine import Engine,Combatant
from native_scenario_fixture import prepare_body
import action_points as AP,common_checks as C,world_entities as WORLD
import style_expert as S,bide as B,spite as P,double_team as D,roar as R


class StyleMoveDependencyTests(unittest.TestCase):
 # Reuse preparation without inheriting/discovering the parent's test methods.
 setUpClass=classmethod(fixture.StyleExpertTests.setUpClass.__func__)
 setUp=fixture.StyleExpertTests.setUp
 setup=fixture.StyleExpertTests.setup
 acquire=fixture.StyleExpertTests.acquire
 family=fixture.StyleExpertTests.family
 combat=fixture.StyleExpertTests.combat
 use=fixture.StyleExpertTests.use
 rejected=fixture.StyleExpertTests.rejected
 restored=fixture.StyleExpertTests.restored

 def actor(self,name,pos,*,side='wild',kind='pokemon',trainer=None,movement=None,moves=None):
  spec=dict(name=name,kind=kind,level=25,size='중형',
   stats={'hp':100,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
   moves=moves or ['move/몸통박치기'],abilities=[],types=['노말'],
   movement=movement or {'land':6,'swim':4,'sky':4,'power':4},weight_kg=30,
   skills={'육상':4,'곡예':4,'집중':4},gender='암컷')
  if trainer is not None:spec['trainer_id']=trainer.entity_id
  elif kind=='pokemon':spec['wild']=True
  actor=Combatant(self.rules,spec)
  self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native Move recipient')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual body')
  return actor

 def attack(self,actor,target,move='move/몸통박치기',*,roll=19):
  with patch.object(Engine,'d20',return_value=roll):
   return self.e.use_move_on(actor,target,move,self.e.everyone,set_damage=True)

 def next_round(self,actor):
  self.e.end_round();self.e.start_round(self.e.everyone)
  self.e.start_of_turn(actor,initiative_count=30)

 def hit_event(self):
  return next(key for key,row in reversed(list(self.e._passive_events.items()))
              if row.get('phase')=='producer_return_boundary')

 def test_double_team_shared_accuracy_then_capped_and_ignored_evasion_spends_three(self):
  self.setup('근사함');self.family(rank=2)
  second=self.actor('second adjacent foe',(6,6));second_id=second.entity_id
  self.q.pos=(5,6)
  self.e.gm.set_move(self.p,'move/작아지기',reason='actual learned native Evasion Move')
  self.e.gm.set_move(self.b,'move/파동탄',reason='actual learned native automatic-hit Move')
  self.combat();self.attack(self.p,self.p,'move/작아지기')
  import effect_lifetimes as LIFE
  self.assertEqual(LIFE.numeric(self.p,'evasion_modifier'),4)
  self.assertEqual(self.p.evasion('물리',attacker=self.b,engine=self.e),9)
  self.e.end_of_turn(self.p);self.next_round(self.p)
  self.use(D.SOURCE,self.p,ranked=S.RANKED[self.stat])
  self.e.end_of_turn(self.p);self.next_round(self.p)
  D.choose(self.e,self.p,'accuracy',reason='actual one shared Burst attack')
  log_start=len(self.e.log_lines)
  self.use('move/부르짖기',ranked=S.RANKED[self.stat])
  self.assertEqual([row['kind'] for row in D.records(self.p)[0]['applications']],['accuracy'])
  self.assertEqual(sum('Double Team accuracy +2' in line for line in self.e.log_lines[log_start:]),1)
  for target in (self.b,second):self.assertEqual((target.stages['atk'],target.stages['spa']),(-1,-1))
  self.assertEqual((self.q.stages['atk'],self.q.stages['spa']),(0,0))
  accuracy=[line for line in self.e.log_lines[log_start:] if '명중 d20=' in line]
  self.assertEqual(len(accuracy),2);self.assertTrue(all('d20=19+2=21' in line for line in accuracy))
  self.e.end_of_turn(self.p);self.restored()
  self.assertEqual(len(D.records(self.p)[0]['applications']),1)
  self.assertIn(second_id,WORLD.actor_index(self.e))
  self.e.start_of_turn(self.b,initiative_count=29)
  D.choose(self.e,self.p,'evasion',reason='actual capped incoming attack')
  before=self.p.hp;log_start=len(self.e.log_lines)
  self.attack(self.b,self.p,roll=11)
  self.assertLess(self.p.hp,before)
  self.assertTrue(any('회피 9=' in line for line in self.e.log_lines[log_start:]))
  self.assertEqual(len(D.records(self.p)[0]['applications']),2)
  self.e.end_of_turn(self.b);self.next_round(self.b)
  D.choose(self.e,self.p,'evasion',reason='actual incoming native Evasion waiver')
  before=self.p.hp;log_start=len(self.e.log_lines)
  self.attack(self.b,self.p,'move/파동탄',roll=1)
  self.assertLess(self.p.hp,before)
  self.assertTrue(any('never_miss' in line for line in self.e.log_lines[log_start:]))
  self.assertFalse(D.records(self.p))
  self.assertNotIn('double_team_choice',self.p.spec)
  self.assertEqual(self.p.move_uses[D.SOURCE],1)
  self.restored();self.assertFalse(D.records(self.p));self.assertTrue(self.e.validate_state()['valid'])

 def test_spite_pending_standard_rejection_and_immediate_printed_free_disables_trigger_move(self):
  import condition_instances as CONDITIONS
  self.setup('강인함');self.family();self.combat(self.p)
  self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=29)
  self.attack(self.b,self.p);event=self.hit_event()
  before=self.e.export_state()
  self.assertIsInstance(P.use(self.e,self.a,self.p,event),C.PendingDecision)
  self.assertEqual(self.e.export_state(),before)
  self.rejected(lambda:P.use(self.e,self.a,self.p,event,policy='standard_override'),'current owner turn')
  budget=deepcopy(self.p.budget);ap=AP.available(self.a)
  with patch.object(Engine,'d20',return_value=19):P.use(self.e,self.a,self.p,event,policy='printed_free')
  self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(self.p.budget,budget)
  locks=CONDITIONS.records(self.b,'사슬묶기')
  self.assertEqual([row['effect']['move_id'] for row in locks],['move/몸통박치기'])
  self.assertFalse(CONDITIONS.move_allowed(self.e,self.b,self.rules.move('move/몸통박치기'))[0])
  with patch.object(Engine,'d20',return_value=1):self.e.end_of_turn(self.b)
  self.next_round(self.b)
  self.rejected(lambda:P.use(self.e,self.a,self.p,event,policy='printed_free'),'actual move occurrence|completed native hit')
  before=(self.p.hp,deepcopy(self.b.budget),deepcopy(self.b.move_uses),self.e.rng.getstate())
  self.assertEqual(self.attack(self.b,self.p),0)
  self.assertEqual((self.p.hp,self.b.budget,self.b.move_uses,self.e.rng.getstate()),before)
  self.setup('강인함');self.family();self.e.gm.faint(self.a,reason='actual unavailable Style owner')
  self.combat(self.b);before=self.p.hp
  self.attack(self.b,self.p)
  self.assertLess(self.p.hp,before)

 def test_bide_reaction_payments_shift_and_release_count_only_later_damage(self):
  for payment in ('current','next'):
   with self.subTest(payment=payment):
    self.setup('강인함');self.family(rank=2)
    second=self.actor('second Bide foe',(6,4));second_id=second.entity_id
    self.r.pos=(4,5)
    self.e.gm.set_move(self.r,'move/분노의앞니',reason='actual learned direct HP-loss Move')
    if payment=='current':
     self.combat(self.p);self.e.end_of_turn(self.p)
     self.e.start_of_turn(self.b,initiative_count=29)
    else:self.combat(self.b)
    self.attack(self.b,self.p);event=self.hit_event();initial_hp=self.p.hp;ap=AP.available(self.a)
    B.reaction(self.e,self.p,event,trainer=self.a,ranked=S.RANKED[self.stat],payment=payment)
    self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(self.p.hp,initial_hp)
    if payment=='current':self.assertEqual(self.p.budget['standard'],0)
    self.assertEqual(self.p.move_uses[B.SOURCE],1)
    self.e.end_of_turn(self.b);self.q.pos=(5,6)
    self.e.start_of_turn(self.q,initiative_count=28)
    before=self.p.hp;self.attack(self.q,self.p);damage=before-self.p.hp
    self.assertGreater(damage,0)
    self.e.lose_hp(self.p,7,source='독 passive HP loss')
    self.e.end_of_turn(self.q)
    self.e.start_of_turn(self.r,initiative_count=27)
    before=self.p.hp;self.attack(self.r,self.p,'move/분노의앞니')
    self.assertLess(self.p.hp,before);self.e.end_of_turn(self.r)
    if payment=='current':
     self.e.end_round();self.e.start_round(self.e.everyone)
    self.restored();self.e.start_of_turn(self.p,initiative_count=26)
    self.assertEqual(self.p.budget['standard'],1 if payment=='current' else 0)
    self.e.disengage(self.p,(5,4),movement_mode='land')
    self.assertEqual(self.p.pos,(5,4));self.assertEqual(self.p.budget['shift'],0)
    second=WORLD.actor_index(self.e)[second_id]
    before=[actor.hp for actor in (self.b,second,self.q)]
    B.release(self.e,self.p,self.b)
    self.assertEqual([old-actor.hp for old,actor in zip(before,(self.b,second,self.q))],[damage,damage,0])
    self.assertIsNone(B.pending(self.p));self.assertEqual(self.p.move_uses[B.SOURCE],1)
    self.assertEqual(AP.available(self.a),ap-1)
    self.e.end_of_turn(self.p);self.next_round(self.b)
    self.attack(self.b,self.p);event=self.hit_event()
    self.rejected(lambda:B.reaction(self.e,self.p,event,trainer=self.a,ranked=S.RANKED[self.stat],payment='next'),'activation refused|소진')

 def test_bide_encounter_clears_pending_but_scene_frequency_resets_only_at_scene_end(self):
  self.setup('강인함');self.family(rank=2);self.combat(self.b)
  self.attack(self.b,self.p)
  B.reaction(self.e,self.p,self.hit_event(),trainer=self.a,ranked=S.RANKED[self.stat],payment='next')
  self.e.end_of_turn(self.b);self.e.end_encounter(self.e.everyone)
  self.assertIsNone(B.pending(self.p))
  self.restored();self.combat(self.b);self.attack(self.b,self.p)
  event=self.hit_event()
  self.rejected(lambda:B.reaction(self.e,self.p,event,trainer=self.a,ranked=S.RANKED[self.stat],payment='next'),'activation refused|소진')
  self.e.end_of_turn(self.b);self.e.end_scene(self.e.everyone)
  self.combat(self.b);self.attack(self.b,self.p)
  B.reaction(self.e,self.p,self.hit_event(),trainer=self.a,ranked=S.RANKED[self.stat],payment='next')
  self.assertIsNotNone(B.pending(self.p));self.assertEqual(self.p.move_uses[B.SOURCE],1)

 def test_bide_style_effects_wait_for_actual_release_and_are_not_paid_twice(self):
  import combat_timing as TIME
  self.setup('강인함');self.family(rank=2,effect=True,flourish=True);self.combat(self.b)
  self.attack(self.b,self.p);event=self.hit_event();origin=self.b.pos;ap=AP.available(self.a)
  B.reaction(self.e,self.p,event,trainer=self.a,ranked=S.RANKED[self.stat],payment='next',
             effect=S.IMPROVE[self.stat],flourish=True)
  self.assertEqual(AP.available(self.a),ap-2)
  self.assertEqual(self.b.pos,origin);self.assertEqual(self.p.stages['def'],0)
  self.assertFalse(any(row.get('style_flourish') for row in TIME.records(self.p)))
  self.e.end_of_turn(self.b);self.q.pos=(5,6);self.e.start_of_turn(self.q,initiative_count=29)
  self.attack(self.q,self.p);self.e.end_of_turn(self.q);self.restored()
  self.e.start_of_turn(self.p,initiative_count=28)
  B.release(self.e,self.p,self.b)
  self.assertEqual(self.b.pos,(origin[0]+3,origin[1]))
  self.assertEqual(self.p.stages['def'],1)
  self.assertTrue(any(row.get('style_flourish') for row in TIME.records(self.p)))
  self.assertEqual(AP.available(self.a),ap-2);self.assertEqual(self.p.move_uses[B.SOURCE],1)
  self.assertNotIn('_style_move_scope',vars(self.e))

 def test_roar_end_round_shift_highest_retreat_ball_distance_and_replacement_turn(self):
  import party_actions as PARTY
  from native_scenario_fixture import prepare_object
  for ball_distance in (6,7):
   with self.subTest(ball_distance=ball_distance):
    self.setup('근사함');self.family(rank=2)
    owner=self.actor('actual opposing Trainer',(14,6),side='opponent',kind='trainer')
    target=self.actor('actual owned Roar target',(6,6),side='opponent',trainer=owner,
                      movement={'land':3,'sky':8,'swim':0,'power':4})
    reserve=self.actor('actual replacement',(15,6),side='opponent',trainer=owner)
    self.e.gm.observe_loyalty(reserve,6,reason='actual willing replacement Pokemon')
    reserve.on_field=False
    PARTY.configure(self.e,owner,battle_mode='league',reason='actual League replacement boundary')
    prepare_object(self.e,'actual-home-ball',location={'kind':'grid','cell':(12+ball_distance,6)},
     kind='item_instance',item_rule_id='item/슈퍼볼',owner_id=owner.entity_id,
     reason='actual target Poke Ball at observed distance')
    R.bind_ball(self.e,target,'actual-home-ball',reason='actual target belongs to this Poke Ball')
    self.e.gm.set_movement_capabilities(self.p,{'land':0,'sky':6,'swim':0},basis='current',
                                      reason='actual flying user has no usable Land movement')
    survivor=self.actor('actual surviving Burst target',(5,7))
    survivor_id=survivor.entity_id
    self.combat();origin=self.p.pos;target_id=target.entity_id;owner_id=owner.entity_id;reserve_id=reserve.entity_id
    R.choose(self.e,self.p,shift=[{'position':(5,6),'altitude':0}],shift_mode='sky',
     retreats={survivor_id:{'path':[(x,7) for x in range(6,12)],'mode':'land'},
               target.entity_id:{'path':[{'position':(x,6),'altitude':0} for x in range(7,13)],
                                 'mode':'sky','ball_id':'actual-home-ball'}},
     reason='actual end-round Shift and highest usable retreats towards the Trainer')
    self.use(R.SOURCE,ranked=S.RANKED[self.stat])
    self.assertEqual(self.p.pos,origin);self.assertEqual(target.pos,(6,6));self.assertTrue(target.on_field)
    self.assertEqual(self.p.budget['shift'],0)
    # The declaration placeholder does not own the later self-centred Burst.
    anchor=self.b
    if ball_distance==6:self.e.gm.faint(anchor,reason='declaration anchor fainted before Roar release')
    else:__import__('combat_state_lifecycle').recall(self.e,anchor)
    self.e.end_of_turn(self.p);self.restored()
    with patch.object(Engine,'d20',return_value=19):self.e.end_round()
    index=WORLD.actor_index(self.e);target=index[target_id];owner=index[owner_id];reserve=index[reserve_id]
    self.assertEqual(self.p.pos,(5,6));self.assertEqual(index[survivor_id].pos,(11,7))
    self.assertEqual(self.b.pos,(6,5));self.assertTrue(self.b.fainted if ball_distance==6 else not self.b.on_field)
    self.assertEqual(target.pos,(12,6));self.assertEqual(target.on_field,ball_distance>6)
    self.assertEqual(self.p.move_uses[R.SOURCE],1)
    if ball_distance==6:
     self.e.start_round(self.e.everyone);self.e.start_of_turn(owner,initiative_count=30)
     result=PARTY.act(self.e,owner,send=[(reserve,(13,6))],request_id='Roar replacement',
                      reason='actual replacement after forced Roar recall')
     self.assertFalse(result['counts_as_switch']);self.assertFalse(result['blocked_command_ids'])
     self.assertIsNone(PARTY.switch_lock(self.e,reserve))
     self.e.end_of_turn(owner);self.e.start_of_turn(reserve,initiative_count=29)
     self.assertEqual(reserve.budget['standard'],1)
     before=self.p.hp
     self.e.gm.set_move(reserve,'move/파동탄',reason='actual learned replacement attack')
     result=self.attack(reserve,self.p,'move/파동탄')
     self.assertNotIsInstance(result,C.PendingDecision)
     self.assertLess(self.p.hp,before)
