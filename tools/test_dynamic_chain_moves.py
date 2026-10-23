"""Actual source choices, movement, native waits and one whole Move return."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
from engine import Engine,Rules
import test_native_set_damage as BASE
import test_native_return_continuation as RETURN
import dynamic_chain_moves as CHAIN
import passive_events as EVENTS,move_completion as COMPLETE,world_entities as WORLD
import declarative_move_contracts as DMC
from native_scenario_fixture import prepare_body,assert_rejected_unchanged,assert_rejections_unchanged


class DynamicChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.NativeSetDamageTests.setUpClass();cls.rules=BASE.NativeSetDamageTests.r

    def world(self,name='트리플다이브',positions=((3,2),(4,3),(5,4))):
        f=BASE.NativeSetDamageTests();f.r=self.rules
        self.e,self.a,self.targets,self.mid=f.world(name,positions)
        for actor in self.e.everyone:
            prepare_body(self.e,actor,size=actor.spec.get('size','중형'),offsets=[(0,0)],reason='actual chain scene body')

    def step(self,i,*,path=(),forgo=False):return dict(target=self.targets[i],path=list(path),forgo_remaining=forgo)
    def use(self,steps):return self.e.use_move_on(self.a,self.targets[0],self.mid,self.e.everyone,chain_steps=steps,set_damage=True)
    def row(self):return next(row for row in self.e._move_completions.values() if row['actor'] is self.a and row['move_id']==self.mid)
    def valid(self):
        state=self.e.validate_state();self.assertTrue(state['valid'],state['issues'])
    def fresh(self):
        ids=[actor.entity_id for actor in (self.a,*self.targets)]
        self.e=Engine.import_state(Rules(self.e.r.root,ruleset=self.e.r.ruleset.name),json.loads(json.dumps(self.e.export_state())))
        self.a,*self.targets=[WORLD.actor_index(self.e)[uid] for uid in ids]
    def policy(self,key):return RETURN.NativeReturnContinuationTests.policy(self,key)
    def choose(self,event,key):return RETURN.NativeReturnContinuationTests.choose(self,event,key)

    def test_explicit_separated_recipients_paths_independent_miss_and_one_cost(self):
        self.world();hp=[t.hp for t in self.targets];budget=deepcopy(self.a.budget)
        choices=[self.step(0),self.step(1,path=[(2,3),(3,3)]),self.step(2,path=[(3,4),(4,4)])]
        with patch.object(Engine,'d20',side_effect=[16,1,16]) as rolls:
            total=self.use(choices)
        row=self.row();self.assertEqual(rolls.call_count,3)
        self.assertEqual([row['results'][t.entity_id]['hit'] for t in self.targets],[True,False,True])
        self.assertLess(self.targets[0].hp,hp[0]);self.assertEqual(self.targets[1].hp,hp[1]);self.assertLess(self.targets[2].hp,hp[2])
        self.assertEqual(total,sum(r['dealt'] for r in row['results'].values()))
        self.assertEqual((self.a.pos,self.a.move_uses[self.mid],self.a._action_history),((4,4),1,['standard']))
        self.assertEqual(self.a.budget['shift'],budget['shift']);self.assertEqual(row['phase'],'complete')
        self.assertEqual(len(row['started']),3);self.fresh();self.valid()

    def test_all_sources_before_roll_forfeit_bonuses_at_each_stop_point(self):
        for name,accuracy,db,flat in [('트리플다이브',0,0,5),('트리플악셀',1,1,0),('수류연타',0,3,0),('3연화살',1,1,0)]:
            for count in (1,2,3):
                with self.subTest(source=name,attacks=count):
                    self.world(name,((3,2),(2,3),(1,2)))
                    raw=self.e.r.move(self.mid)
                    baseline=self.e.damage_base(self.a,raw,target=self.targets[0]);seen=[]
                    original=Engine.roll_damage
                    def observe(e,a,t,move,crit=False,set_damage=False,*args,**kwargs):
                        actual=original(e,a,t,move,crit,set_damage,*args,**kwargs)
                        seen.append((e.damage_base(a,move,target=t),crit,actual))
                        return actual
                    choices=[self.step(i,forgo=i==count-1 and count<3) for i in range(count)]
                    with patch.object(Engine,'d20',return_value=16),patch.object(Engine,'roll_damage',observe):total=self.use(choices)
                    row=self.row();forgone=3-count
                    self.assertEqual([v[0] for v in seen],[baseline]*(count-1)+[baseline+forgone*db])
                    self.assertEqual([v[1] for v in seen],[name=='수류연타']*count)
                    self.assertEqual(total,sum(v[2] for v in seen));self.assertEqual(len(row['results']),count)
                    self.assertEqual(row['phase'],'complete');self.assertEqual(self.a.move_uses[self.mid],1)
                    # Accuracy modifiers are real native observations, while Dive's flat
                    # damage must preserve its DB rather than turning +5 into DB+5.
                    target_move=row['target_moves'][self.targets[count-1].entity_id]
                    unbonused=dict(target_move);unbonused.pop('_chain_bonus')
                    import combat_hit as HIT
                    actual_mods=[];resolve=HIT.resolve
                    def observe_accuracy(**facts):
                        actual_mods.append(facts['modifier']);return resolve(**facts)
                    with patch.object(Engine,'d20',return_value=4),patch.object(HIT,'resolve',side_effect=observe_accuracy):
                        self.e.accuracy_check(self.a,self.targets[count-1],unbonused)
                        self.e.accuracy_check(self.a,self.targets[count-1],target_move)
                    self.assertEqual(actual_mods[1]-actual_mods[0],accuracy*forgone)
                    if flat:
                        plain=self.e.roll_damage(self.a,self.targets[count-1],unbonused,False,True)
                        # The fixture has neutral Water damage; native result is integer damage.
                        self.assertEqual(seen[-1][2]-plain,forgone*flat)
                    if name=='3연화살':
                        self.assertEqual([(t.stages['def'],t.stages['spd']) for t in self.targets[:count]],[(-1,-1)]*count)
                        self.assertEqual(len(DMC.live(self.a,'focus_until_switch')),1)
                    self.valid()

        self.world('3연화살',((3,2),))
        with patch.object(Engine,'d20',return_value=1):self.use([self.step(0,forgo=True)])
        self.assertFalse(self.row()['results'][self.targets[0].entity_id]['hit'])
        self.assertEqual(len(DMC.live(self.a,'focus_until_switch')),1)
        self.assertEqual(self.targets[0].stages['def'],0);self.valid()

    def test_choice_after_results_restore_stop_and_after_all_pumped_once(self):
        self.world('3연화살',((3,2),(6,2),(7,2)))
        with patch.object(Engine,'d20',return_value=16):pending=self.use([self.step(0)])
        self.assertEqual(pending['status'],'awaiting_chain_choice');token=pending['completion_id']
        self.assertFalse(self.row()['sealed']);self.assertFalse(DMC.live(self.a,'focus_until_switch'))
        before=self.e.export_state();adapter=DMC.policy(self.e.r)['moves'][self.mid]
        original=deepcopy(adapter['frequency'])
        for malformed in ('daily x1',None,{'kind':'daily','uses':True},{'kind':'daily','uses':2}):
            adapter['frequency']=malformed
            try:
                with self.assertRaisesRegex(ValueError,'daily-once'):
                    self.e.continue_chain_move(token,stop=True)
            finally:adapter['frequency']=deepcopy(original)
        self.assertEqual(self.e.export_state(),before)

        for operation in (lambda:self.e.use_move(self.a,self.targets[0],'struggle'),
                          lambda:self.e.end_of_turn(self.a),lambda:self.e.preflight_advance_time(1)):
            assert_rejected_unchanged(self.e,operation,reason_pattern='unfinished chain')
        self.fresh();first_hp=self.targets[0].hp
        with patch.object(Engine,'d20',return_value=16):
            total=self.e.continue_chain_move(token,chain_steps=[self.step(1,path=[(3,3)],forgo=True)])
        self.assertEqual(self.targets[0].hp,first_hp);self.assertEqual(self.row()['phase'],'complete')
        self.assertEqual(total,sum(v['dealt'] for v in self.row()['results'].values()))
        self.assertEqual(len(DMC.live(self.a,'focus_until_switch')),1)
        self.assertEqual(DMC.live(self.a)[0]['source'],self.mid)
        self.assertEqual(DMC.critical_threshold(self.a,20),18)
        import frequency as FREQ
        self.assertFalse(FREQ.activation_allowed(self.a,self.mid+'/pumped',{'kind':'daily','uses':1},engine=self.e))
        self.assertEqual(FREQ.state(self.a)['activations'][self.mid+'/pumped']['used'],1)
        DMC.recall(self.e,self.a);self.assertFalse(DMC.live(self.a,'focus_until_switch'))
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        # Every-other-turn source frequency needs one further actual turn.
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        with patch.object(Engine,'d20',return_value=1):pending=self.use([self.step(0)])
        self.assertIsInstance(pending,dict)
        self.e.continue_chain_move(pending['completion_id'],stop=True)
        self.assertFalse(DMC.live(self.a,'focus_until_switch'))
        self.fresh();self.valid()

    def test_source_movement_exempts_only_previous_surging_target(self):
        for name,bystander in [('트리플다이브',False),('수류연타',True)]:
            with self.subTest(source=name):
                self.world(name,((3,2),(3,4),(1,2)))
                first,last=self.targets[0],self.targets[2]
                first.aoo_used=last.aoo_used=False
                with patch.object(Engine,'d20',return_value=16):
                    self.use([self.step(0),self.step(1,path=[(2,3),(2,4)],forgo=True)])
                self.assertFalse(first.aoo_used);self.assertEqual(last.aoo_used,bystander)
                self.assertEqual(self.a.pos,(2,4));self.valid()

    def test_existing_aerial_path_and_technician_owners_receive_actual_chain(self):
        self.world('트리플악셀',((3,2),(3,3),(1,2)))
        self.e.gm.set_ability(self.a,'테크니션',reason='actual Technician owner')
        self.e.gm.set_movement_capabilities(self.a,{'land':4,'sky':4},basis='current',reason='actual flight capability')
        before=self.e.damage_base(self.a,self.e.r.move(self.mid),target=self.targets[1]);actual=[]
        original=Engine.damage_base
        def observe(e,a,move,**kwargs):
            result=original(e,a,move,**kwargs)
            if a.entity_id==self.a.entity_id:actual.append(result)
            return result
        second=self.step(1,path=[{'position':(2,3),'altitude':1,'gm_distance':2}],forgo=True)
        second['movement_mode']='sky'
        with patch.object(Engine,'d20',return_value=16),patch.object(Engine,'damage_base',observe):
            self.use([self.step(0),second])
        self.assertEqual(actual,[before+2,before+3])
        self.assertEqual((self.a.pos,self.a.spec['_movement_altitude']),((2,3),1))
        self.assertTrue(self.a.airborne);self.assertEqual(self.a._action_history,['standard']);self.fresh();self.valid()

    def test_native_accuracy_then_hit_waits_and_late_resumed_failure_keep_prefix(self):
        self.world();import tera_shell as TS
        self.e.gm.set_ability(self.targets[0],'테라셸',reason='actual earlier accuracy Interrupt')
        self.e.watch_ability_interrupt(self.targets[0],TS.SOURCE,reason='actual chain accuracy wait')
        key=self.policy('chain');hp=[t.hp for t in self.targets]
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.use([self.step(0)])
        event=self.e._passive_pending;self.assertEqual([t.hp for t in self.targets],hp)
        with self.assertRaises(EVENTS.PassiveEventPending):
            self.e.choose_ability_interrupt(event,self.targets[0],use=False,reason='decline actual shell reaction')
        self.assertEqual(self.e._passive_pending,event);first_hp=self.targets[0].hp;self.fresh()
        with patch.object(Engine,'d20',side_effect=AssertionError('first recipient cannot reroll')):
            pending=self.choose(event,key)
        token=pending['completion_id'];self.assertEqual(self.targets[0].hp,first_hp)
        self.e.grid.blocking.add((3,3));self.fresh()
        assert_rejected_unchanged(self.e,lambda:self.e.continue_chain_move(token,chain_steps=[self.step(1,path=[(2,3),(3,3)],forgo=True)]),reason_pattern='chain movement interrupted')
        self.e.grid.blocking.remove((3,3))
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):
            self.e.continue_chain_move(token,chain_steps=[self.step(1,path=[(2,3),(3,3)],forgo=True)])
        later=self.e._passive_pending;self.assertNotEqual(event,later);self.assertEqual(self.targets[0].hp,first_hp)
        self.fresh();hp=[t.hp for t in self.targets];rng=self.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('completed accuracy cannot reroll')):total=self.choose(later,key)
        self.assertEqual([t.hp for t in self.targets],hp);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(total,sum(v['dealt'] for v in self.row()['results'].values()))
        self.assertEqual(self.e.deliver_passive_event(event),'already_delivered')
        self.assertEqual(self.e.deliver_passive_event(later),'already_delivered')
        self.assertEqual((self.a.move_uses[self.mid],self.a._action_history),(1,['standard']))
        self.fresh();self.valid()

    def test_real_rough_skin_incapacitation_stops_remaining_chain(self):
        for waiting in (False,True):
            with self.subTest(native_accuracy_wait=waiting):
                self.world();self.e.gm.set_ability(self.targets[0],'까칠한피부/철가시',reason='actual Rough Skin recipient')
                self.e.lose_hp(self.a,self.a.hp-1,source='actual preexisting injury damage')
                hp=self.targets[1].hp
                if waiting:
                    self.e.watch_move_defense(self.targets[0],[{'actor_id':self.targets[1].entity_id,'source':'maneuver/근접-가로채기'}],reason='actual pre-hit defense choice')
                    with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.use([self.step(0)])
                    event=self.e._passive_pending;self.fresh()
                    self.e.choose_move_defense(event,self.targets[1],use=False,reason='decline actual defense; Rough Skin returns natively')
                else:
                    with patch.object(Engine,'d20',return_value=16):self.use([self.step(0),self.step(1,path=[(2,3),(3,3)],forgo=True)])
                self.assertTrue(self.a.fainted);self.assertEqual(self.targets[1].hp,hp)
                self.assertEqual(self.a.pos,(2,2));self.assertEqual(self.row()['phase'],'interrupted')
                self.assertEqual(self.a.move_uses[self.mid],1);self.fresh();self.valid()

    def test_same_stamina_action_defers_across_native_wait_and_later_choice(self):
        self.world('수류연타',((3,2),(2,3),(1,2)))
        import state_grants as G,stamina as STAMINA
        for target in self.targets:
            G.transition(self.e,target,lambda e,c:c.spec.update(skills={'육상':5,'전투':5},edges=[STAMINA.SOURCE]))
        key=self.policy('stamina-chain')
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.use([self.step(0)])
        event=self.e._passive_pending;action_id=next(iter(self.e._native_action_resolutions));self.fresh()
        pending=self.choose(event,key);token=pending['completion_id']
        self.assertEqual(self.targets[0].temp_hp,0);self.assertEqual(self.e._native_action_resolutions[action_id]['phase'],'interrupted')
        self.fresh()
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):
            self.e.continue_chain_move(token,chain_steps=[self.step(1,forgo=True)])
        self.assertEqual(set(self.e._native_action_resolutions),{action_id});self.assertEqual([t.temp_hp for t in self.targets],[0,0,0])
        self.choose(self.e._passive_pending,key)
        self.assertEqual([t.temp_hp for t in self.targets],[5,5,0]);self.assertEqual(set(self.e._native_action_resolutions),{action_id})
        self.assertEqual(self.e._native_action_resolutions[action_id]['phase'],'producer_returned');self.fresh();self.valid()

    def test_routed_actual_recipient_cannot_be_selected_again(self):
        self.world('트리플다이브',((3,2),(3,4),(6,4)))
        self.e.watch_move_defense(self.targets[0],[{'actor_id':self.targets[1].entity_id,
            'source':'maneuver/근접-가로채기'}],reason='actual ally Intercept choice')
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.use([self.step(0)])
        event=self.e._passive_pending
        pending=self.e.choose_move_defense(event,self.targets[1],use=True,
            options={'path':[(3,4),(3,3),(3,2)],'skill':'육상','mode':'land',
                     'shove_destination':[4,2],'roll_options':{'fixed':[6,6]}},reason='actual adjacent ally interception')
        self.assertEqual(set(self.row()['received']),{self.targets[1].entity_id})
        self.assertEqual(pending['status'],'awaiting_chain_choice');self.fresh()
        assert_rejected_unchanged(self.e,lambda:self.e.continue_chain_move(pending['completion_id'],chain_steps=[self.step(1,forgo=True)]),reason_pattern='already targeted.*routed')
        self.e.continue_chain_move(pending['completion_id'],stop=True);self.fresh();self.valid()

    def test_actual_managed_mount_cannot_bypass_held_shared_movement_composition(self):
        import test_book_conquerors_march as MOUNT_FIX,control_mount as MOUNT
        f=MOUNT_FIX.ConquerorsMarchTests();f.rules=Rules(self.rules.root,ruleset='all')
        f.setup(run_up=False,moves=['move/트리플다이브'])
        self.e,self.a,self.targets,self.mid=f.e,f.p,[f.enemy,f.other],'move/트리플다이브'
        self.assertTrue(MOUNT.manages(self.e,self.a));self.assertTrue(MOUNT.manages(self.e,f.a))
        self.assertIsNone(self.a.spec.get('mount_id'))
        f.start();self.e.start_of_turn(self.a)
        with patch.object(Engine,'d20',return_value=16):pending=self.use([self.step(0)])
        self.assertEqual(pending['status'],'awaiting_chain_choice')
        prefix=self.targets[0].hp
        assert_rejected_unchanged(self.e,lambda:self.e.continue_chain_move(pending['completion_id'],
            chain_steps=[self.step(1,path=[(1,1),(2,1)],forgo=True)]),reason_pattern='special movement composition')
        self.assertEqual(self.targets[0].hp,prefix);self.e.continue_chain_move(pending['completion_id'],stop=True)
        self.assertEqual((self.a.pos,f.a.pos),((0,0),(0,0)));self.fresh();self.valid()

    def test_selected_body_origin_survives_chain_path_and_cannot_borrow_other_cells(self):
        self.world('3연화살',((6,1),(10,1),(8,1)))
        self.e.gm.set_footprint(self.a,[(x,0) for x in range(5)],reason='actual five-cell non-square body')
        self.e.gm.observe_body_part(self.a,'tail',(2,2),reason='actual selected tail origin')
        with patch.object(Engine,'d20',return_value=16):
            pending=self.e.use_move_on(self.a,self.targets[0],self.mid,self.e.everyone,
                origin_part='tail',set_damage=True,chain_steps=[self.step(0)])
        token=pending['completion_id'];self.fresh();prefix=self.targets[0].hp
        # After two metres the tail is at (4,2), while other body cells reach
        # (8,2). A target at (10,1) is outside the selected tail's printed four.
        assert_rejected_unchanged(self.e,lambda:self.e.continue_chain_move(token,
            chain_steps=[self.step(1,path=[(3,2),(4,2)],forgo=True)]),reason_pattern='outside actual source reach')
        before=self.targets[2].hp
        with patch.object(Engine,'d20',return_value=16):
            total=self.e.continue_chain_move(token,chain_steps=[self.step(2,path=[(3,2),(4,2)],forgo=True)])
        self.assertEqual(self.targets[0].hp,prefix);self.assertLess(self.targets[2].hp,before)
        self.assertEqual(self.a.pos,(4,2));self.assertEqual(self.row()['targets'],[self.targets[0],self.targets[2]])
        self.assertEqual(total,sum(value['dealt'] for value in self.row()['results'].values()))
        self.assertEqual(self.a.move_uses[self.mid],1);self.fresh();self.valid()

    def test_late_native_entry_refusal_stops_without_replaying_movement_or_inventing_return(self):
        self.world();import field_effects as FIELD
        native=FIELD.native_move_block_reason;denials=[];hp=[t.hp for t in self.targets]
        def refuse_after_actual_prefix(e,mid,actor=None):
            prefix=any(row['move_id']==self.mid and row['actor'] is actor and row['started']
                       for row in getattr(e,'_move_completions',{}).values())
            if prefix:
                denials.append(actor.pos)
                if len(denials)>1:raise AssertionError('unchanged native cursor retried a refused attack')
                return 'injected native field-entry refusal after the actual first hit'
            return native(e,mid,actor)
        with patch.object(Engine,'d20',return_value=16),patch.object(FIELD,'native_move_block_reason',side_effect=refuse_after_actual_prefix):
            total=self.use([self.step(0),self.step(1,path=[(2,3),(3,3)])])
        row=self.row();self.assertEqual(denials,[(3,3)]);self.assertEqual(self.a.pos,(3,3))
        self.assertEqual(row['phase'],'interrupted');self.assertEqual(row['started'],[self.targets[0].entity_id])
        self.assertEqual(set(row['results']),{self.targets[0].entity_id})
        self.assertLess(self.targets[0].hp,hp[0]);self.assertEqual([t.hp for t in self.targets[1:]],hp[1:])
        self.assertEqual(total,row['results'][self.targets[0].entity_id]['dealt'])
        self.assertEqual((self.a.move_uses[self.mid],self.a._action_history),(1,['standard']))
        self.fresh();self.valid()

    def test_duplicate_forged_grant_changed_source_and_saved_intent_reject(self):
        self.world();import action_lifecycle as ACTION
        invalid=[([], 'explicit chain'),([self.step(0),self.step(0)],'distinct actual'),
                 ([self.step(0,forgo=True),self.step(1)],'forgone'),
                 ([self.step(0),self.step(1,path=[(3,3),(4,3),(5,3)])],'two-metre')]
        def forged_grant():
            with ACTION.move_grant(self.e,self.a,self.targets[0],self.mid,source='same_move_activation') as grant:
                return self.e.use_move(self.a,self.targets[0],self.mid,count_use=False,_action_grant=grant)
        assert_rejections_unchanged(self.e,[lambda bad=bad:self.use(bad) for bad,_ in invalid]+[forged_grant],
                                   reason_pattern=[reason for _,reason in invalid]+['actual use_move_on producer'])
        with patch.object(Engine,'d20',return_value=16):pending=self.use([self.step(0)])
        import state_grants as G
        registered=self.e._precision_events[-1];lookalike=dict(registered)
        def actual_observation(staged,actor):
            actual,copied=G._stage_transition_payload(self.e,staged,(registered,lookalike))
            self.assertTrue(any(actual is row for row in staged._precision_events))
            self.assertFalse(any(copied is row for row in staged._precision_events))
            self.assertIsNot(actual,copied)
        G.transition(self.e,self.a,actual_observation)
        token=pending['completion_id'];before=self.e.export_state()
        saved=self.row()['activation_continuation'];saved['scope']['total']+=1
        with self.assertRaisesRegex(ValueError,'authenticated completed prefix'):self.e.continue_chain_move(token,stop=True)
        saved['scope']['total']-=1;self.assertEqual(self.e.export_state(),before)
        self.fresh();wrong=Rules(self.e.r.root,ruleset=self.e.r.ruleset.name);wrong.ruleset.profile='unselected'
        with self.assertRaisesRegex(ValueError,'profile|fingerprint'):Engine.import_state(wrong,self.e.export_state())
        original=deepcopy(self.e.r.moves[self.mid]);self.e.r.moves[self.mid]['effect']='changed source'
        with self.assertRaisesRegex(ValueError,'definition or mechanics changed'):self.e.continue_chain_move(token,stop=True)
        self.e.r.moves[self.mid]=original
        self.e.continue_chain_move(token,stop=True)
        assert_rejected_unchanged(self.e,lambda:self.e.continue_chain_move(token,chain_steps=[self.step(1)]),reason_pattern='actual pending chain choice')
        self.fresh();self.valid()


if __name__=='__main__':unittest.main()
