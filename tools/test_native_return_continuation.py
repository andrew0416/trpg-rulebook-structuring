"""Actual native producer returns survive source-policy waits without replaying hits."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json,unittest
from unittest.mock import patch
from engine import Engine,Rules
import test_native_set_damage as BASE
import test_pass_path_continuation as PATH
import passive_events as EVENTS,move_completion as COMPLETE,world_entities as WORLD
from native_scenario_fixture import prepare_body,assert_rejected_unchanged

class NativeReturnContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.NativeSetDamageTests.setUpClass();cls.rules=BASE.NativeSetDamageTests.r
        PATH.PassPathContinuationTests.setUpClass()

    def world(self,name='막치기',positions=((3,2),)):
        f=BASE.NativeSetDamageTests();f.r=self.rules
        self.e,self.a,self.targets,self.mid=f.world(name,positions)
        for actor in self.e.everyone:
            prepare_body(self.e,actor,size=actor.spec.get('size','중형'),offsets=[(0,0)],reason='native scene body')

    def policy(self,key,stat='atk',event='move_resolved'):
        source='input/'+self.e.r.selection.units['combat/struggle']['source']['file']
        document={'schema':1,'id':'event/return-'+key,'variants':[{
            'rule_id':'combat/struggle','source':{'file':source,'sha256':sha256((Path(self.e.r.root)/source).read_bytes()).hexdigest()},
            'inputs':{'hit':{'authority':'context','type':'boolean','question':'Actual native accuracy'},
                      'choice':{'authority':'gm','type':'boolean','question':'Actual application decision'}},
            'when':{'op':'eq','left':{'$input':'hit'},'right':True},
            'values':{'effects':[{'type':'stage_change','stat':stat,'delta':1,'target':'self'}]}}]}
        return self.e.subscribe_source_policy(self.a,key,document,event=event,inputs={'hit':'hit'})

    def choose(self,event,key):
        return self.e.choose_passive_event(event,self.a,key,
            {'decisions':{'choice':{'value':True,'reason':'actual selected application policy'}}})

    def valid(self):
        state=self.e.validate_state();self.assertTrue(state['valid'],state['issues'])

    def fresh(self):
        ids=[actor.entity_id for actor in (self.a,*self.targets)]
        self.e=Engine.import_state(Rules(self.e.r.root,ruleset=self.e.r.ruleset.name),json.loads(json.dumps(self.e.export_state())))
        self.a,*self.targets=[WORLD.actor_index(self.e)[uid] for uid in ids]

    def start(self,*,group=False,natural=16):
        with patch.object(Engine,'d20',return_value=natural),self.assertRaises(EVENTS.PassiveEventPending):
            if group:self.e.use_move_on(self.a,self.targets[0],self.mid,self.e.everyone,set_damage=True)
            else:self.e.use_move(self.a,self.targets[0],self.mid,set_damage=True)
        self.valid();return self.e._passive_pending

    def test_direct_multiple_listeners_and_reactive_tail_restore_late_failure_once(self):
        self.world();target=self.targets[0]
        self.e.gm.set_ability(target,'변색',reason='actual Color Change owner')
        self.e.choose_reactive_ability(target,'ability/변색',reason='owner selects native hit reaction')
        first=self.policy('first');second=self.policy('second','def')
        hp=target.hp;types=target.types[:];event=self.start()
        self.assertLess(target.hp,hp);self.assertEqual(target.types,types)
        with self.assertRaises(EVENTS.PassiveEventPending):self.choose(event,first)
        self.assertEqual((self.a.stages['atk'],self.a.stages['def']),(1,0))
        self.fresh();target=self.targets[0];hp=target.hp;rng=self.e.rng.getstate()
        original=COMPLETE.record_return
        def late_failure(*args,**kwargs):
            original(*args,**kwargs)
            args[0].rng.random()
            raise ValueError('injected late producer return failure')
        with patch.object(COMPLETE,'record_return',side_effect=late_failure):
            assert_rejected_unchanged(self.e,lambda:self.choose(event,second),reason_pattern='late producer return failure')
        self.assertEqual((self.a.stages['atk'],self.a.stages['def']),(1,0))
        with patch.object(Engine,'d20',side_effect=AssertionError('saved hit cannot reroll')):
            self.assertEqual(self.choose(event,second),'applied')
        self.assertEqual((target.hp,self.e.rng.getstate()),(hp,rng))
        self.assertEqual(target.types,[self.e.r.move(self.mid)['type']])
        self.assertEqual((self.a.stages['atk'],self.a.stages['def']),(1,1))
        self.assertEqual((self.a.move_uses[self.mid],self.a._action_history),(1,['standard']))
        self.assertEqual(COMPLETE.require_hit_return(self.e,event,target)['result']['hit'],True)
        before=self.e.export_state();self.assertEqual(self.e.deliver_passive_event(event),'already_delivered')
        self.assertEqual(self.e.export_state(),before)
        assert_rejected_unchanged(self.e,lambda:self.choose(event,second),reason_pattern='listener already delivered')
        self.fresh();self.valid()

    def test_group_shared_accuracy_preserves_recipient_effects_and_returns(self):
        self.world('바크아웃',((3,2),(4,2)));key=self.policy('shared')
        hp=[t.hp for t in self.targets];event=self.start(group=True)
        self.assertLess(self.targets[0].hp,hp[0]);self.assertEqual(self.targets[1].hp,hp[1])
        self.assertEqual([t.stages['spa'] for t in self.targets],[-1,0])
        self.fresh();firsthp=self.targets[0].hp;rng=self.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('shared accuracy cannot reroll')),self.assertRaises(EVENTS.PassiveEventPending):
            self.choose(event,key)
        later=self.e._passive_pending;self.assertNotEqual(later,event)
        self.assertEqual(self.targets[0].hp,firsthp);self.assertLess(self.targets[1].hp,hp[1])
        self.assertEqual([t.stages['spa'] for t in self.targets],[-1,-1])
        self.fresh();actualhp=[t.hp for t in self.targets]
        with patch.object(Engine,'d20',side_effect=AssertionError('saved accuracy cannot reroll')):total=self.choose(later,key)
        row=next(iter(self.e._move_completions.values()))
        self.assertEqual(total,sum(r['dealt'] for r in row['results'].values()))
        self.assertEqual(row['phase'],'complete');self.assertEqual(len(row['native_returns']),2)
        self.assertEqual([t.hp for t in self.targets],actualhp);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual((self.a.stages['atk'],self.a.move_uses[self.mid]),(2,1))
        for native in (event,later):COMPLETE.require_returned_event(self.e,native)
        self.fresh();self.valid()

    def test_independent_pass_accuracy_then_post_hit_wait_keeps_prefix_on_late_path_failure(self):
        f=PATH.PassPathContinuationTests();f.base=PATH.PassPathContinuationTests.base
        f.scene(objects=False,watch=False)
        self.e,self.a,self.targets,self.mid=f.e,f.a,[f.b,f.c],f.mid
        import tera_shell as TS
        self.e.gm.set_ability(self.targets[0],'테라셸',reason='actual pre-hit Interrupt owner')
        self.e.watch_ability_interrupt(self.targets[0],TS.SOURCE,reason='actual earlier accuracy wait')
        key=self.policy('path');hp=[t.hp for t in self.targets]
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):f.use()
        event=self.e._passive_pending;self.assertEqual([t.hp for t in self.targets],hp)
        with self.assertRaises(EVENTS.PassiveEventPending):
            self.e.choose_ability_interrupt(event,self.targets[0],use=False,reason='actual declined type change')
        self.assertEqual(self.e._passive_pending,event);self.assertLess(self.targets[0].hp,hp[0])
        self.fresh();firsthp=self.targets[0].hp;self.e.grid.blocking.add((2,0))
        assert_rejected_unchanged(self.e,lambda:self.choose(event,key),reason_pattern='Pass movement interrupted')
        self.assertEqual(self.targets[0].hp,firsthp);self.assertEqual(self.a.stages['atk'],0)
        self.e.grid.blocking.remove((2,0))
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.choose(event,key)
        later=self.e._passive_pending;self.assertNotEqual(event,later)
        self.assertEqual(self.targets[0].hp,firsthp);self.assertLess(self.targets[1].hp,hp[1])
        self.assertEqual(self.a.pos,(3,0));self.fresh();hp=[t.hp for t in self.targets];rng=self.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('post-hit cannot reroll')):row=self.choose(later,key)
        self.assertEqual((row['phase'],self.a.pos),('complete',(4,0)))
        self.assertEqual([t.hp for t in self.targets],hp);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual((self.a.stages['atk'],self.a.move_uses[self.mid],self.a._action_history),(2,1,['standard','shift']))
        self.assertEqual(len(row['results']),2);self.fresh();self.valid()

    def test_post_hit_tamper_unknown_source_and_forged_numeric_return_reject(self):
        self.world();key=self.policy('tamper');event=self.start(group=True)
        ev=self.e._passive_events[event];row=self.e._move_completions[ev['completion_id']]
        import move_activation as ACTIVATION
        assert_rejected_unchanged(self.e,lambda:ACTIVATION.resume_after_event(self.e,ev,999),reason_pattern='native target return required')
        assert_rejected_unchanged(self.e,lambda:self.e.choose_passive_event(event,self.targets[0],key,{'decisions':{}}),reason_pattern='actual owned source event')
        assert_rejected_unchanged(self.e,lambda:self.e.choose_passive_event(event,self.a,key,{'decisions':{'choice':True}}),reason_pattern='decision|reason|GM')
        assert_rejected_unchanged(self.e,lambda:self.e.deliver_passive_event('unknown/event'),reason_pattern='no actual source event')
        saved=self.e.export_state();wrong=Rules(self.e.r.root,ruleset=self.e.r.ruleset.name);wrong.ruleset.profile='wrong-profile'
        with self.assertRaisesRegex(ValueError,'fingerprint|profile'):Engine.import_state(wrong,saved)
        frame=ev['continuation'];dealt=frame['result']['dealt'];frame['result']['dealt']=dealt+1
        hp=self.targets[0].hp
        with self.assertRaisesRegex(ValueError,'authenticated continuation'):self.choose(event,key)
        with self.assertRaisesRegex(ValueError,'authenticated continuation'):COMPLETE.validate_world(self.e,WORLD.actor_index(self.e))
        self.assertEqual(self.targets[0].hp,hp);frame['result']['dealt']=dealt
        del ev['continuation']
        with self.assertRaisesRegex(ValueError,'authenticated continuation'):COMPLETE.validate_world(self.e,WORLD.actor_index(self.e))
        ev['continuation']=frame
        profile=self.e._passive_listeners[self.a][key];document=deepcopy(profile['document'])
        profile['document']['variants'][0]['source']['sha256']='0'*64
        with self.assertRaises(EVENTS.PassiveEventPending):self.choose(event,key)
        self.assertEqual(self.e._passive_events[event]['reason'],'subscription_definition_changed')
        self.assertEqual(self.targets[0].hp,hp)
        self.e._passive_listeners[self.a][key]['document']=document
        self.choose(event,key);self.valid()

    def test_incapacitation_during_post_hit_wait_retains_completed_hit_and_stops_group(self):
        for pass_path in (False,True):
            with self.subTest(pass_path=pass_path):
                if pass_path:
                    f=PATH.PassPathContinuationTests();f.base=PATH.PassPathContinuationTests.base;f.scene(objects=False,watch=False)
                    self.e,self.a,self.targets,self.mid=f.e,f.a,[f.b,f.c],f.mid
                else:self.world('바크아웃',((3,2),(4,2)))
                key=self.policy('stop');hp=[t.hp for t in self.targets]
                if pass_path:
                    with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):f.use()
                    event=self.e._passive_pending
                else:event=self.start(group=True)
                actualhp=self.targets[0].hp;self.assertLess(actualhp,hp[0])
                self.e.gm.faint(self.a,reason='actual attacker incapacitated after completed hit')
                result=self.e.deliver_passive_event(event)
                row=self.e._move_completions[self.e._passive_events[event]['completion_id']]
                self.assertEqual(row['phase'],'interrupted');self.assertEqual(len(row['results']),1)
                self.assertEqual([t.hp for t in self.targets],[actualhp,hp[1]])
                self.assertFalse(row['results'][self.targets[0].entity_id]['cancelled'])
                self.assertEqual(self.a.move_uses[self.mid],1);self.assertEqual(self.a.stages['atk'],0)
                if pass_path:self.assertEqual((result['phase'],self.a.pos),('interrupted',(1,0)))
                self.fresh();self.valid()

    def test_actual_stamina_wait_reopens_same_action_and_finishes_after_whole_group(self):
        import state_grants as G,stamina as STAMINA
        for grouped in (False,True):
            with self.subTest(grouped=grouped):
                self.world('바크아웃' if grouped else '막치기',((3,2),(4,2)) if grouped else ((3,2),))
                for target in self.targets:
                    G.transition(self.e,target,lambda e,c:c.spec.update(skills={'육상':5,'전투':5},edges=[STAMINA.SOURCE]))
                key=self.policy('stamina');event=self.start(group=grouped,natural=20)
                rows=self.e._native_action_resolutions;self.assertEqual(len(rows),1)
                action_id=next(iter(rows));self.assertEqual(rows[action_id]['phase'],'interrupted')
                self.assertEqual([t.temp_hp for t in self.targets],[0]*len(self.targets))
                self.fresh()
                if grouped:
                    with patch.object(Engine,'d20',side_effect=AssertionError('critical shared accuracy cannot reroll')),self.assertRaises(EVENTS.PassiveEventPending):self.choose(event,key)
                    event=self.e._passive_pending
                    self.assertEqual(set(self.e._native_action_resolutions),{action_id})
                    self.assertEqual([t.temp_hp for t in self.targets],[0,0]);self.fresh()
                hp=[t.hp for t in self.targets];self.choose(event,key)
                self.assertEqual(set(self.e._native_action_resolutions),{action_id})
                row=self.e._native_action_resolutions[action_id]
                self.assertEqual(row['phase'],'producer_returned')
                self.assertEqual(len(row['triggers']),len(self.targets))
                self.assertTrue(all(t['status']=='completed' for t in row['triggers']))
                self.assertEqual([t.temp_hp for t in self.targets],[5]*len(self.targets))
                self.assertEqual([t.hp for t in self.targets],hp)
                self.assertEqual(self.a.move_uses[self.mid],1)
                self.assertEqual(self.e.deliver_passive_event(event),'already_delivered')
                self.fresh();self.valid()

    def test_single_return_rejects_unknown_tail_and_completed_stray_frame_before_delivery(self):
        self.world();key=self.policy('single-admission');event=self.start()
        ev=self.e._passive_events[event];frame=ev['continuation'];before=self.e.export_state()
        frame['kind']='unknown_producer'
        with self.assertRaisesRegex(ValueError,'authenticated continuation'):self.choose(event,key)
        frame['kind']='recipient_return'
        self.assertEqual(self.e.export_state(),before)
        self.assertEqual(self.a.stages['atk'],0);self.assertFalse(self.e._passive_receipts)
        self.assertEqual(self.choose(event,key),'applied');self.assertEqual(self.a.stages['atk'],1)
        ev=self.e._passive_events[event];before=self.e.export_state();ev['continuation']=frame
        with self.assertRaisesRegex(ValueError,'returned recipient retains executable continuation'):
            self.e.deliver_passive_event(event)
        ev.pop('continuation');self.assertEqual(self.e.export_state(),before)
        self.assertEqual(self.e.deliver_passive_event(event),'already_delivered');self.valid()
