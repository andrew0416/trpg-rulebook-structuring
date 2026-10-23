"""Original foundation 33 over real Engine turns, budgets, clocks and codec."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from itertools import permutations
import json,sys,unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from rulings import Rulings
from state_codec import dump_engine,load_engine,StateCodecError
import initiative_schedule as S
import initiative_interrupts as I
import combat_timing as TIME
import turn


class InitiativeScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e = Engine(self.r,871)
        self.r.rulings = self.e.rulings = Rulings()
        self.a,self.b,self.c = self.actor('first',30),self.actor('second',20),self.actor('third',10)
        self.e.everyone = self.e.gm.everyone = [self.a,self.b,self.c]

    def actor(self,name,speed,kind='trainer',abilities=None):
        stats = dict.fromkeys(('hp','atk','def','spa','spd','spe'),30);stats['spe']=speed
        return Combatant(self.r,dict(name=name,kind=kind,level=10,stats=stats,types=[],
                                    moves=['struggle'],abilities=abilities or [],movement={'land':4}))

    def prepare(self,actors=None,**declaration):
        actors = actors or [self.a,self.b,self.c]
        return self.e.prepare_initiative_schedule(actors,source='gm/test-schedule',**declaration)

    def start(self,**declaration):
        self.prepare(**declaration)
        self.e.start_round([self.a,self.b,self.c])
        self.e.start_of_turn(self.a)

    def trigger(self):
        owner = self.e._active_turn_actor
        current = I.frame(self.e)
        if current:
            return dict(kind='reaction',window_id=current['window_id'],request_id=current['request_id'])
        return dict(kind='turn',actor_id=owner.entity_id,serial=owner.custom_conditions.get('combat_turn_serial',0),round=self.e.round_no)

    def reaction(self,actor,uid='react',priority=10,**fields):
        return dict(id=uid,actor_id=actor.entity_id,source='homebrew/declared-reaction',priority=priority,
                    mode='reaction',payment='next',budget={'standard':1},clock='none',**fields)

    def borrow(self,actor,uid='borrow',settlement='none'):
        return dict(id=uid,actor_id=actor.entity_id,source='homebrew/whole-turn',priority=10,
                    mode='borrow_turn',payment='future_turn',budget=None,clock='owner_turn',settlement_clock=settlement)

    def queue(self,*requests,**fields):
        return self.e.queue_initiative_reactions(list(requests),trigger=self.trigger(),**fields)

    def close(self,actor):
        self.e.start_of_turn(actor);self.e.end_of_turn(actor)

    def clone(self):
        e = load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        return e,{c.entity_id:c for c in e.everyone}

    def test_real_order_denies_wrong_owner_without_clock_or_budget_progress(self):
        self.prepare();self.e.start_round([self.a,self.b,self.c])
        before=(self.e.rng.getstate(),self.e.elapsed_seconds,deepcopy(self.b.spec),getattr(self.b,'budget',None))
        with self.assertRaises(ValueError):self.e.start_of_turn(self.b)
        self.assertEqual(before,(self.e.rng.getstate(),self.e.elapsed_seconds,self.b.spec,getattr(self.b,'budget',None)))
        for actor in (self.a,self.b,self.c):self.close(actor)
        self.e.end_round()
        self.assertEqual(self.e.initiative_schedule_status()['status'],'completed')
        self.assertEqual(self.e.elapsed_seconds,10)

    def test_tie_remains_pending_without_rng_round_or_schedule(self):
        self.b.stats['spe']=30
        before=self.e.rng.getstate()
        self.assertEqual(self.prepare()['status'],'pending')
        self.assertEqual(self.e.rng.getstate(),before)
        self.assertEqual(self.e.round_no,0)
        self.assertEqual(self.e.initiative_schedule_status()['status'],'not_attached')

    def test_declared_roles_reverse_declaration_then_forward_resolution(self):
        bindings=[dict(slot='first-slot',actor_id=self.a.entity_id,role='caller'),
                  dict(slot='second-slot',actor_id=self.b.entity_id,role='caller'),
                  dict(slot='third-slot',actor_id=self.c.entity_id,role='creature')]
        layout=[dict(id='say',roles=['caller'],reverse=True,declaration=True),
                dict(id='resolve',roles=['caller'],reverse=False,declaration=False),
                dict(id='creature',roles=['creature'],reverse=False,declaration=False)]
        self.prepare(bindings=bindings,layout=layout,order_groups=[['caller'],['creature']])
        self.e.start_round([self.a,self.b,self.c]);before=self.b.custom_conditions.get('combat_turn_serial',0)
        with self.assertRaises(ValueError):self.e.start_of_turn(self.b)
        intent={'kind':'homebrew-data','values':{'amount':7}}
        self.e.declare_scheduled_action(self.b,intent);intent['values']['amount']=99
        self.assertEqual(self.e._initiative_schedule['declarations']['second-slot']['values']['amount'],7)
        self.assertEqual(self.b.custom_conditions.get('combat_turn_serial',0),before)
        self.e.declare_scheduled_action(self.a,{'kind':'other'})
        for actor in (self.a,self.b,self.c):self.close(actor)
        self.e.end_round()

    def test_invalid_layout_fails_before_random_or_round(self):
        before=(self.e.rng.getstate(),self.e.round_no)
        with self.assertRaises(ValueError):
            self.prepare(layout=[dict(id='bad',roles=['absent'],reverse=False,declaration=False)])
        self.assertEqual((self.e.rng.getstate(),self.e.round_no),before)

    def test_replacement_before_turn_keeps_slot_and_prior_initiative_position(self):
        self.prepare();self.e.start_round([self.a,self.b,self.c]);self.close(self.a)
        replacement=self.actor('replacement',99);self.e.everyone.append(replacement)
        self.e.replace_scheduled_participant(self.b.entity_id,replacement,source='gm/switch',reason='explicit switch')
        self.assertEqual(self.e.initiative_schedule_status()['next']['actor_id'],replacement.entity_id)
        with self.assertRaises(ValueError):self.e.start_of_turn(self.b)
        self.close(replacement);self.close(self.c);self.e.end_round()
        self.assertEqual(replacement.custom_conditions.get('combat_turn_serial',0),1)

    def test_replacement_after_consumption_never_creates_second_turn(self):
        self.prepare();self.e.start_round([self.a,self.b,self.c]);self.close(self.a)
        replacement=self.actor('replacement',99);self.e.everyone.append(replacement)
        self.e.replace_scheduled_participant(self.a.entity_id,replacement,source='gm/switch',reason='explicit switch')
        with self.assertRaises(ValueError):self.e.start_of_turn(replacement)
        self.assertEqual(replacement.custom_conditions.get('combat_turn_serial',0),0)
        self.close(self.b);self.close(self.c);self.e.end_round()
        dump_engine(self.e)

    def test_schedule_roundtrip_and_gm_restore_keep_actual_continuation(self):
        self.start();self.assertTrue(turn.spend(self.e,self.a,'swift'))
        self.e.gm.snapshot('open');self.e.end_of_turn(self.a);self.e.gm.restore('open')
        self.assertIs(self.e._initiative_schedule['slots'][self.a.entity_id]['actor'],self.a)
        self.assertIs(self.e._active_turn_actor,self.a)
        e,index=self.clone();a=index[self.a.entity_id];b=index[self.b.entity_id]
        self.assertIs(e._active_turn_actor,a);self.assertEqual(a.budget['swift'],0)
        e.end_of_turn(a);e.start_of_turn(b);e.end_of_turn(b)
        self.assertEqual(e.initiative_schedule_status()['completed_steps'],2)

    def test_forged_completed_slot_or_missing_native_closure_cannot_save(self):
        self.start();self.e.end_of_turn(self.a)
        self.e._initiative_schedule['slots'][self.b.entity_id]['turn']='closed'
        with self.assertRaises(StateCodecError):dump_engine(self.e)
        self.e._initiative_schedule['slots'][self.b.entity_id]['turn']='ready'
        self.e._initiative_schedule['records'][0]['closure_sequence']=999
        with self.assertRaises(StateCodecError):dump_engine(self.e)

    def test_unknown_reaction_precedence_is_pending_without_payment_or_rng(self):
        self.start();before=(deepcopy(self.b.spec),self.e.rng.getstate(),getattr(self.b,'budget',None))
        out=self.queue(self.reaction(self.b,priority=None))
        self.assertEqual(out['status'],'pending');self.assertEqual(self.e.initiative_reaction_status()['status'],'clear')
        self.assertEqual(before,(self.b.spec,self.e.rng.getstate(),getattr(self.b,'budget',None)))
        out=self.queue(self.reaction(self.b,'b',10),self.reaction(self.c,'c',10))
        self.assertEqual(out['status'],'pending')

    def test_priority_and_simultaneous_decision_own_actual_execution(self):
        self.start()
        q=self.queue(self.reaction(self.b,'b',10),self.reaction(self.c,'c',10),order=['c','b'])
        with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'b')
        for uid,actor in (('c',self.c),('b',self.b)):
            self.e.begin_initiative_reaction(q['window_id'],uid)
            self.assertIs(self.e._active_turn_actor,actor)
            self.assertTrue(turn.spend(self.e,actor,'standard'))
            self.e.finish_initiative_reaction()
            self.assertIs(self.e._active_turn_actor,self.a)
        self.assertEqual(self.e.initiative_reaction_status()['status'],'clear')
        self.assertEqual((self.b.custom_conditions.get('combat_turn_serial',0),self.c.custom_conditions.get('combat_turn_serial',0)),(0,0))
        with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'c')

    def test_reaction_resumes_paid_parent_and_next_loss_settles_once(self):
        self.start();self.assertTrue(turn.spend(self.e,self.a,'swift'));parent=deepcopy(self.a.budget)
        q=self.queue(self.reaction(self.b))
        self.e.begin_initiative_reaction(q['window_id'],'react')
        self.assertFalse(turn.spend(self.e,self.a,'standard'))
        self.assertTrue(turn.spend(self.e,self.b,'standard'))
        self.assertFalse(turn.spend(self.e,self.b,'standard'))
        with self.assertRaises(ValueError):self.e.end_of_turn(self.b)
        self.e.finish_initiative_reaction()
        self.assertEqual(self.a.budget,parent)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b)
        self.assertEqual(self.b.budget['standard'],0)
        self.e.end_of_turn(self.b);self.close(self.c);self.e.end_round()
        self.prepare();self.e.start_round([self.a,self.b,self.c]);self.close(self.a);self.e.start_of_turn(self.b)
        self.assertEqual(self.b.budget['standard'],1)

    def test_current_cost_uses_actual_prior_budget_and_cannot_pay_twice(self):
        self.start();self.b.budget={'standard':1,'shift':1,'swift':1}
        request=self.reaction(self.b);request['payment']='current'
        q=self.queue(request);self.e.begin_initiative_reaction(q['window_id'],'react')
        self.assertTrue(turn.spend(self.e,self.b,'standard'));self.e.finish_initiative_reaction()
        self.assertEqual(self.b.budget,{'standard':0,'shift':1,'swift':1})
        self.assertIsNone(getattr(self.b,'pending_action_loss',None))

    def test_nested_reactions_restore_each_actual_parent_without_refresh(self):
        self.start();q=self.queue(self.reaction(self.b));self.e.begin_initiative_reaction(q['window_id'],'react')
        self.assertTrue(turn.spend(self.e,self.b,'standard'))
        inner=self.queue(self.reaction(self.c,'inner'))
        self.e.begin_initiative_reaction(inner['window_id'],'inner')
        self.assertTrue(turn.spend(self.e,self.c,'standard'));self.e.finish_initiative_reaction()
        self.assertIs(self.e._active_turn_actor,self.b);self.assertEqual(self.b.budget['standard'],0)
        self.e.finish_initiative_reaction();self.assertIs(self.e._active_turn_actor,self.a)

    def test_open_reaction_json_and_gm_restore_do_not_repeat_payment(self):
        self.start();q=self.queue(self.reaction(self.b));self.e.begin_initiative_reaction(q['window_id'],'react')
        self.assertTrue(turn.spend(self.e,self.b,'standard'));self.e.gm.snapshot('reaction')
        self.e.finish_initiative_reaction();self.e.gm.restore('reaction')
        self.assertIs(I.frame(self.e)['actor'],self.b)
        e,index=self.clone();a=index[self.a.entity_id];b=index[self.b.entity_id]
        self.assertEqual(b.budget['standard'],0)
        self.assertEqual(b.pending_action_loss,{'standard':1})
        e.finish_initiative_reaction();self.assertIs(e._active_turn_actor,a)
        with self.assertRaises(ValueError):e.begin_initiative_reaction(q['window_id'],'react')

    def test_borrowed_unstarted_turn_uses_native_clock_and_future_slot_once(self):
        self.start();q=self.queue(self.borrow(self.b));self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertEqual(self.b.custom_conditions.get('combat_turn_serial',0),1)
        self.assertTrue(turn.spend(self.e,self.b,'standard'));self.e.finish_initiative_reaction()
        self.e.end_of_turn(self.a)
        with self.assertRaises(ValueError):self.e.start_of_turn(self.b)
        self.e.settle_borrowed_turn()
        self.assertEqual(self.b.custom_conditions.get('combat_turn_serial',0),1)
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'],[])
        self.close(self.c);self.e.end_round()
        dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.settle_borrowed_turn()

    def test_future_loan_remains_with_replaced_slot_in_same_round(self):
        self.start();q=self.queue(self.borrow(self.b));self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.e.finish_initiative_reaction();self.e.end_of_turn(self.a)
        replacement=self.actor('replacement',99);self.e.everyone.append(replacement)
        self.e.replace_scheduled_participant(self.b.entity_id,replacement,source='gm/switch',reason='same slot')
        with self.assertRaises(ValueError):self.e.start_of_turn(replacement)
        self.e.settle_borrowed_turn()
        self.assertEqual(replacement.custom_conditions.get('combat_turn_serial',0),0)
        self.close(self.c);self.e.end_round();dump_engine(self.e)

    def test_owner_clock_settlement_permits_only_zero_actions(self):
        self.start();q=self.queue(self.borrow(self.b,settlement='owner_turn'))
        self.e.begin_initiative_reaction(q['window_id'],'borrow');self.e.finish_initiative_reaction()
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b)
        self.assertEqual(self.b.custom_conditions.get('combat_turn_serial',0),2)
        self.assertEqual(self.b.budget,dict.fromkeys(('standard','shift','swift'),0))
        self.assertFalse(turn.spend(self.e,self.b,'standard'))
        self.e.end_of_turn(self.b);self.close(self.c);self.e.end_round();dump_engine(self.e)

    def test_already_closed_borrower_owes_next_round_and_cannot_drop_slot(self):
        self.start();self.e.end_of_turn(self.a);self.e.start_of_turn(self.b)
        q=self.queue(self.borrow(self.a));self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertEqual(self.a.custom_conditions.get('combat_turn_serial',0),2)
        self.e.finish_initiative_reaction();self.e.end_of_turn(self.b);self.close(self.c);self.e.end_round()
        e,index=self.clone();a=index[self.a.entity_id];b=index[self.b.entity_id];c=index[self.c.entity_id]
        with self.assertRaises(ValueError):e.prepare_initiative_schedule([b,c],source='gm/test-schedule')
        e.prepare_initiative_schedule([a,b,c],source='gm/test-schedule');e.start_round([a,b,c])
        e.settle_borrowed_turn();self.assertEqual(a.custom_conditions.get('combat_turn_serial',0),2)
        e.start_of_turn(b);e.end_of_turn(b);e.start_of_turn(c);e.end_of_turn(c);e.end_round();dump_engine(e)

    def test_unknown_loan_clock_and_forged_trigger_are_inert(self):
        self.start();request=self.borrow(self.b);request['settlement_clock']=None
        before=(self.e.rng.getstate(),deepcopy(self.b.spec))
        self.assertEqual(self.queue(request)['status'],'pending')
        bad=self.trigger();bad['actor_id']=self.b.entity_id
        with self.assertRaises(ValueError):self.e.queue_initiative_reactions([self.reaction(self.b)],trigger=bad)
        self.assertEqual(before,(self.e.rng.getstate(),self.b.spec))

    def test_late_borrow_start_failure_rolls_back_owner_budget_and_future_debt(self):
        self.start();q=self.queue(self.borrow(self.b));before=dump_engine(self.e)
        with patch('turn.reset_budget',side_effect=ValueError('late reset')):
            with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertEqual(dump_engine(self.e),before)
        self.assertIs(self.e._active_turn_actor,self.a)

    def test_changed_reaction_policy_or_forged_future_receipt_cannot_save(self):
        self.start();q=self.queue(self.reaction(self.b))
        self.e._initiative_interrupts['windows'][q['window_id']]['requests'][0]['budget']['standard']=99
        with self.assertRaises(StateCodecError):dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'react')

    def test_explicit_tie_policy_controls_native_order_without_automatic_randomness(self):
        self.b.stats['spe']=30
        self.e.rule_answer('initiative_tie_order',dict(policy='highest_d20',same_face='reroll',max_rounds=5,
                                                     reason='caller declares this exact d20 tie policy'),scope='scene')
        before=self.e.rng.getstate()
        self.assertEqual(self.prepare()['status'],'prepared')
        self.assertNotEqual(self.e.rng.getstate(),before)
        resolved=self.e._initiative_schedule['order']
        self.assertEqual(set(resolved[:2]),{self.a.entity_id,self.b.entity_id})
        self.e.start_round([self.a,self.b,self.c])
        index={a.entity_id:a for a in self.e.everyone}
        for key in resolved:self.close(index[key])
        self.e.end_round()

    def test_owner_and_target_deadlines_survive_reordered_turns_and_reaction(self):
        self.start()
        self.e.apply_effect(self.a,self.b,dict(type='type_change',add_type='물',target='target',
            until={'event':'turn_start','owner':'user','after':1}),None,True,0,'gm/owner-deadline')
        self.e.apply_effect(self.a,self.c,dict(type='type_change',add_type='불꽃',target='target',
            until={'event':'turn_end','owner':'target','after':1}),None,True,0,'gm/target-deadline')
        q=self.queue(self.reaction(self.c));self.e.begin_initiative_reaction(q['window_id'],'react')
        self.e.finish_initiative_reaction()
        self.assertIn('불꽃',self.c.types);self.assertIn('물',self.b.types)
        self.e.end_of_turn(self.a);self.close(self.b);self.close(self.c)
        self.assertNotIn('불꽃',self.c.types);self.assertIn('물',self.b.types)
        self.e.end_round();self.b.stats['spe']=40;self.prepare();self.e.start_round([self.a,self.b,self.c])
        self.close(self.b);self.assertIn('물',self.b.types)
        self.e.start_of_turn(self.a);self.assertNotIn('물',self.b.types)

    def test_core_full_contact_keeps_trainers_in_mixed_order_and_as_attack_targets(self):
        pokemon = self.actor('contact pokemon', 40, 'pokemon')
        actors = [self.a, self.b, pokemon]
        self.e.everyone = self.e.gm.everyone = actors
        self.assertEqual(self.prepare(actors)['status'], 'prepared')
        self.e.start_round(actors)
        self.assertEqual(self.e.initiative_schedule_status()['next']['actor_id'], pokemon.entity_id)
        self.close(pokemon)
        self.e.start_of_turn(self.a)
        before = self.b.hp
        self.e.rng.seed(0)
        self.e.use_move(self.a, self.b, 'struggle', set_damage=True)
        self.assertLess(self.b.hp, before)
        self.assertEqual(self.a.budget['standard'], 0)
        self.assertIsNone(self.e._league_runtime)
        self.e.end_of_turn(self.a)
        self.close(self.b)
        self.e.end_round()
        restored, actual = self.clone()
        self.assertEqual(actual[self.b.entity_id].hp, self.b.hp)
        self.assertEqual(restored.initiative_schedule_status()['status'], 'completed')

    def test_core_incapacitated_partner_does_not_remove_other_role_turn(self):
        for disabled_kind in ('trainer', 'pokemon'):
            for condition in ('fainted', 'sleep'):
                with self.subTest(disabled_kind=disabled_kind, condition=condition):
                    self.setUp()
                    trainer = self.a
                    pokemon = self.actor('paired pokemon', 20, 'pokemon')
                    actors = [trainer, pokemon]
                    self.e.everyone = self.e.gm.everyone = actors
                    disabled = trainer if disabled_kind == 'trainer' else pokemon
                    if condition == 'fainted':
                        self.e.lose_hp(disabled, disabled.hp)
                        self.assertEqual(disabled.hp, 0)
                        self.assertTrue(disabled.fainted)
                    else:
                        self.e.apply_status(disabled, '잠듦')
                    bindings = [dict(slot='player:'+c.kind, actor_id=c.entity_id, role=c.kind) for c in actors]
                    self.prepare(actors, bindings=bindings)
                    self.e.start_round(actors)
                    for actor in actors:
                        self.e.start_of_turn(actor)
                        budget = deepcopy(actor.budget)
                        if actor is disabled:
                            self.assertFalse(turn.spend(self.e, actor, 'standard', 'disabled partner'))
                            self.assertEqual(actor.budget, budget)
                        else:
                            self.assertTrue(turn.spend(self.e, actor, 'standard', 'independent partner'))
                            self.assertEqual(actor.budget['standard'], 0)
                        self.e.end_of_turn(actor)
                    self.assertEqual([row['actor'] for row in self.e._turn_closures], actors)
                    self.e.end_round()
                    restored, actual = self.clone()
                    self.assertEqual(restored.initiative_schedule_status()['completed_steps'], 2)
                    self.assertEqual(actual[trainer.entity_id].custom_conditions['combat_turn_serial'], 1)
                    self.assertEqual(actual[pokemon.entity_id].custom_conditions['combat_turn_serial'], 1)

    def test_core_action_order_free_repetition_and_spent_budget_survive_codec(self):
        for kind in ('trainer', 'pokemon'):
            for order in permutations(('standard', 'shift', 'swift')):
                with self.subTest(kind=kind, order=order):
                    self.setUp()
                    actor = self.actor('ordered actions', 30, kind)
                    self.e.everyone = self.e.gm.everyone = [actor]
                    self.prepare([actor])
                    self.e.start_round([actor])
                    self.e.start_of_turn(actor)
                    for action in order:
                        for _ in range(2):
                            self.assertTrue(turn.spend(self.e, actor, 'free', 'repeatable free action'))
                        self.assertTrue(turn.spend(self.e, actor, action, 'arbitrary ordinary order'))
                    self.assertEqual(actor.budget, dict(standard=0, shift=0, swift=0))
                    restored, actual = self.clone()
                    current = actual[actor.entity_id]
                    before = (deepcopy(current.budget), list(current._action_history), restored.rng.getstate())
                    for action in ('standard', 'shift', 'swift', 'full'):
                        self.assertFalse(turn.spend(restored, current, action, 'already spent'))
                    self.assertEqual((current.budget, current._action_history, restored.rng.getstate()), before)
                    self.assertTrue(turn.spend(restored, current, 'free', 'still repeatable'))
                    self.assertEqual(current.budget, dict(standard=0, shift=0, swift=0))

    def test_count_deadline_keeps_its_count_when_next_order_changes(self):
        self.prepare();self.e.start_round([self.a,self.b,self.c]);self.e.start_of_turn(self.a,initiative_count=30)
        self.e.apply_effect(self.a,self.b,dict(type='type_change',add_type='물',target='target',duration='1 round'),
                            None,True,0,'gm/count-deadline')
        self.e.end_of_turn(self.a)
        for actor,count in ((self.b,20),(self.c,10)):
            self.e.start_of_turn(actor,initiative_count=count);self.e.end_of_turn(actor)
        self.e.end_round()
        self.e, actual = self.clone()
        self.a, self.b, self.c = (actual[c.entity_id] for c in (self.a, self.b, self.c))
        self.assertIn('물', self.b.types)
        self.b.stats['spe']=40;self.prepare();self.e.start_round([self.a,self.b,self.c])
        self.e.start_of_turn(self.b,initiative_count=40);self.assertIn('물',self.b.types);self.e.end_of_turn(self.b)
        self.e.start_of_turn(self.a,initiative_count=30);self.assertNotIn('물',self.b.types)

    def test_real_move_event_reaction_and_resume_preserve_single_native_payment(self):
        self.a=self.actor('native first',30,'pokemon',abilities=['자기과신']);self.a.side='party';self.b.side='wild';self.c.side='party'
        self.e.everyone=self.e.gm.everyone=[self.a,self.b,self.c];self.e.register_abilities(self.a)
        self.start();self.e.use_move(self.a,self.b,'struggle',set_damage=True)
        event=list(self.e._passive_events.values())[-1]
        self.assertIn(event['status'],('applied','inapplicable'))
        parent=deepcopy(self.a.budget);uses=self.a.move_uses['struggle'];target_before=self.c.hp
        q=self.e.queue_initiative_reactions([self.reaction(self.b)],trigger={'kind':'move','event_id':event['id']})
        self.e.begin_initiative_reaction(q['window_id'],'react')
        self.e.use_move(self.b,self.c,'struggle',set_damage=True)
        self.assertEqual(self.b.move_uses['struggle'],1)
        self.assertLess(self.c.hp,target_before)
        self.e.finish_initiative_reaction()
        self.assertEqual(self.a.budget,parent);self.assertEqual(self.a.move_uses['struggle'],uses)
        dump_engine(self.e)

    def test_borrowed_turn_uses_actual_target_deadline_and_rolls_back_late_end_failure(self):
        self.start();self.e.at_initiative_count(30)
        self.e.apply_effect(self.a,self.b,dict(type='type_change',add_type='물',target='target',
            until={'event':'turn_end','owner':'target','after':1}),None,True,0,'gm/borrow-deadline')
        q=self.queue(self.borrow(self.b));self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.assertIn('물',self.b.types)
        before=dump_engine(self.e)
        with patch('combat_timing.end_turn',side_effect=ValueError('late owner end')):
            with self.assertRaises(ValueError):self.e.finish_initiative_reaction()
        self.assertEqual(dump_engine(self.e),before)
        self.e.finish_initiative_reaction();self.assertNotIn('물',self.b.types)
        self.assertIs(self.e._active_turn_actor,self.a)

    def test_native_encounter_end_closes_future_slot_domain_without_extra_turn(self):
        self.start();self.e.end_of_turn(self.a);self.e.start_of_turn(self.b)
        q=self.queue(self.borrow(self.a));self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.e.finish_initiative_reaction();self.e.end_of_turn(self.b)
        before=self.a.custom_conditions.get('combat_turn_serial',0)
        self.e.end_encounter()
        self.assertEqual(self.a.custom_conditions.get('combat_turn_serial',0),before)
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'],[])
        self.assertEqual(self.e.initiative_schedule_status()['status'],'not_attached')
        dump_engine(self.e)
        self.e.start_round([self.a,self.b,self.c]);self.e.start_of_turn(self.a)

    def test_existing_league_driver_uses_common_reverse_declaration_and_forward_steps(self):
        a=self.actor('league-a',10);b=self.actor('league-b',20)
        p=self.actor('league-p',40,'pokemon');q=self.actor('league-q',30,'pokemon')
        self.e.everyone=self.e.gm.everyone=[a,b,p,q]
        out=self.e.start_league([('a',a,p),('b',b,q)],mode='league')
        self.assertEqual(out['status'],'ready')
        self.assertEqual(self.e.initiative_schedule_status()['next']['slot'],'a:trainer')
        self.e.league_declare('a:trainer',{'kind':'no_action'})
        self.e.league_declare('b:trainer',{'kind':'no_action'})
        self.assertEqual(self.e.initiative_schedule_status()['next']['slot'],'b:trainer')
        self.e.league_step();self.e.league_step()
        self.e.league_step(pokemon_intent={'kind':'no_action'});self.e.league_step(pokemon_intent={'kind':'no_action'})
        self.e.league_complete_round()
        self.assertEqual(self.e.initiative_schedule_status()['status'],'completed')
        e,_=self.clone();e.end_league();self.assertEqual(e.initiative_schedule_status()['status'],'not_attached')

    def test_league_explicit_ties_reuse_common_decision_without_cross_role_tie(self):
        a=self.actor('league-a',30);b=self.actor('league-b',30)
        p=self.actor('league-p',30,'pokemon');q=self.actor('league-q',20,'pokemon')
        self.e.everyone=self.e.gm.everyone=[a,b,p,q]
        self.e.rule_answer('initiative_tie_order',dict(policy='highest_d20',same_face='reroll',max_rounds=5,
                                                     reason='explicit trainer tie policy'),scope='scene')
        self.assertEqual(self.e.start_league([('a',a,p),('b',b,q)],mode='league')['status'],'ready')
        schedule=self.e._initiative_schedule
        for n in range(2):
            key=self.e.initiative_schedule_status()['next']['slot']
            self.e.league_declare(key,{'kind':'no_action'})
        for n in range(2):self.e.league_step()
        self.assertEqual(self.e.initiative_schedule_status()['next']['slot'],'a:pokemon')

    def test_distinct_future_action_costs_do_not_silently_coalesce_and_may_decline(self):
        self.start();q=self.queue(self.reaction(self.b,'one',10),self.reaction(self.b,'two',5))
        self.e.begin_initiative_reaction(q['window_id'],'one');self.e.finish_initiative_reaction()
        before=dump_engine(self.e)
        with self.assertRaises(ValueError):self.e.begin_initiative_reaction(q['window_id'],'two')
        self.assertEqual(dump_engine(self.e),before)
        self.e.decline_initiative_reaction(q['window_id'],'two',source='homebrew/declared-reaction',reason='explicit pass')
        self.assertEqual(self.b.pending_action_loss,{'standard':1})
        self.assertEqual(self.e.initiative_reaction_status()['status'],'clear')
        dump_engine(self.e)

    def test_explicit_future_cost_conjunction_and_window_replay_are_idempotent(self):
        self.start();one=self.reaction(self.b,'one',10);two=self.reaction(self.b,'two',5)
        two['debt_policy']='coalesce';trigger=self.trigger()
        q=self.e.queue_initiative_reactions([one,two],trigger=trigger)
        for uid in ('one','two'):
            self.e.begin_initiative_reaction(q['window_id'],uid);self.e.finish_initiative_reaction()
        before=dump_engine(self.e)
        self.assertEqual(self.e.queue_initiative_reactions([one,two],trigger=trigger)['status'],'already_queued')
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(self.b.pending_action_loss,{'standard':1})

    def test_forged_future_closure_and_settlement_are_rejected(self):
        self.start();q=self.queue(self.borrow(self.b));self.e.begin_initiative_reaction(q['window_id'],'borrow')
        self.e.finish_initiative_reaction()
        loan=next(iter(self.e._initiative_interrupts['loans'].values()));closure=loan['borrow_closure']
        loan['borrow_closure']=999
        with self.assertRaises(StateCodecError):dump_engine(self.e)
        loan['borrow_closure']=closure;self.e.end_of_turn(self.a);self.e.settle_borrowed_turn()
        loan['settlement']['actor']=self.c
        with self.assertRaises(StateCodecError):dump_engine(self.e)

    def test_actual_scheduled_turn_boundaries_are_atomic_after_late_failure(self):
        self.prepare();self.e.start_round([self.a,self.b,self.c]);before=dump_engine(self.e)
        with patch('turn.reset_budget',side_effect=ValueError('late ordinary reset')):
            with self.assertRaises(ValueError):self.e.start_of_turn(self.a)
        self.assertEqual(dump_engine(self.e),before)
        self.e.start_of_turn(self.a);before=dump_engine(self.e)
        with patch('combat_timing.end_turn',side_effect=ValueError('late ordinary end')):
            with self.assertRaises(ValueError):self.e.end_of_turn(self.a)
        self.assertEqual(dump_engine(self.e),before)
        self.e.end_of_turn(self.a)

    def test_malformed_schedule_or_reaction_is_a_codec_error(self):
        self.start();del self.e._initiative_schedule['initial_bindings']
        with self.assertRaises(StateCodecError):dump_engine(self.e)


if __name__=='__main__':
    unittest.main()
