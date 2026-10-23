"""Paid Pass resumes its actual ordered cells through native reaction choices."""
from copy import deepcopy
from pathlib import Path
import json,unittest
from unittest.mock import patch
from engine import Engine,Rules,Combatant
import test_pass_moves as BASE
import test_book_conquerors_march as BOOK
import passive_events as EVENTS,world_entities as WORLD,control_mount as MOUNT
import physical_object_attacks as OBJECTS,pass_moves as PASS
from native_scenario_fixture import prepare_body,assert_rejected_unchanged,assert_rejections_unchanged

ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')

class PassPathContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.Tests.setUpClass();cls.base=BASE.Tests()
        cls.book_rules=Rules(ROOT,ruleset='all')

    def scene(self,*,objects=True,watch=True):
        self.e,self.a,self.b,self.mid,self.objects=self.base.fixture(ropes=False)
        self.b.pos=(1,0)
        self.c=Combatant(self.e.r,dict(deepcopy(self.b.spec),id='path/third',name='third real recipient'))
        self.r=Combatant(self.e.r,dict(deepcopy(self.b.spec),id='path/reactor',name='real defense owner'))
        self.e.gm.add_combatant(self.c,pos=(3,0),side='foe',reason='later actual recipient')
        self.e.gm.add_combatant(self.r,pos=(1,3),side='foe',reason='actual allied defense owner')
        for actor in (self.a,self.b,self.c,self.r):
            prepare_body(self.e,actor,size=actor.spec.get('size','중형'),offsets=[(0,0)],reason='actual one-cell body')
        if objects:
            WORLD.observe_location(self.e,self.e._physical_objects['door'],{'kind':'grid','cell':(2,0)},reason='later actual object')
            self.objects={'door':{'hit':True,'damage_before_dr':12}}
        if watch:
            for actor in (self.b,self.c):
                self.e.watch_move_defense(actor,[{'actor_id':self.r.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual ordered reaction offer')
        return self.e

    def use(self):return self.base.execute(self.e,self.a,self.mid,self.objects)
    def choose(self,event,actor=None,use=False):
        return self.e.choose_move_defense(event,actor or self.r,use=use,reason='actual defense decision')
    def valid(self):
        state=self.e.validate_state();self.assertTrue(state['valid'],state['issues'])
    def restore(self):
        ids=[c.entity_id for c in (self.a,self.b,self.c,self.r)]
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.e=Engine.import_state(Rules(ROOT,ruleset=self.e.r.ruleset.name),saved)
        self.a,self.b,self.c,self.r=[WORLD.actor_index(self.e)[uid] for uid in ids]
    def pending(self):
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.use()
        self.valid();return self.e._passive_pending

    def test_ordered_mixed_path_repeated_native_wait_restore_and_exactly_once(self):
        self.scene();hp=(self.b.hp,self.c.hp);event=self.pending()
        row=self.e._pass_moves['pass/1'];self.assertEqual(row['phase'],'pending')
        self.assertEqual((self.a.pos,row['travelled'],row['results']),((1,0),1,[]))
        self.assertEqual((self.b.hp,self.c.hp),hp)
        before=self.e.export_state()
        with self.assertRaises(EVENTS.PassiveEventPending):self.use()
        self.assertEqual(self.e.export_state(),before)
        self.restore()
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):self.choose(event)
        later=self.e._passive_pending;self.assertNotEqual(event,later)
        row=self.e._pass_moves['pass/1'];self.assertEqual(self.a.pos,(3,0))
        self.assertEqual([[r['kind'],r['id']] for r in row['results']],[['creature',self.b.entity_id],['object','door']])
        self.assertLess(self.b.hp,hp[0]);self.assertEqual(self.c.hp,hp[1]);self.valid()
        doorhp=self.e._physical_objects['door'][OBJECTS.FIELD]['hp'];firsthp=self.b.hp
        self.restore()
        with patch.object(Engine,'d20',side_effect=AssertionError('saved accuracy cannot reroll')):row=self.choose(later)
        self.assertEqual(row['phase'],'complete');self.assertEqual(self.a.pos,(4,0))
        self.assertEqual((self.b.hp,self.e._physical_objects['door'][OBJECTS.FIELD]['hp']),(firsthp,doorhp))
        self.assertLess(self.c.hp,hp[1]);self.assertEqual(self.a.move_uses[self.mid],1)
        self.assertEqual(self.a._action_history,['standard','shift'])
        completion=self.e._move_completions[row['completion_id']]
        self.assertEqual(completion['phase'],'complete');self.assertEqual(completion['started'],[self.b.entity_id,self.c.entity_id])
        before=self.e.export_state();self.assertEqual(self.use(),row);self.assertEqual(self.e.export_state(),before)
        assert_rejected_unchanged(self.e,lambda:self.choose(later),reason_pattern='actual waiting accuracy defense required')
        self.valid();self.restore();self.valid()

    def test_native_detect_choice_keeps_its_own_cost_and_pass_finishes(self):
        self.scene(objects=False,watch=False)
        self.e.gm.set_move(self.b,'move/판별',reason='actual learned defensive Move')
        self.e.watch_move_defense(self.b,[{'actor_id':self.b.entity_id,'source':'move/판별'}],reason='actual Detect reaction')
        hp=(self.b.hp,self.c.hp);event=self.pending()
        with patch.object(Engine,'d20',return_value=16):row=self.choose(event,self.b,True)
        self.assertEqual(row['phase'],'complete');self.assertEqual(self.b.hp,hp[0]);self.assertLess(self.c.hp,hp[1])
        self.assertEqual((self.a.move_uses[self.mid],self.b.move_uses['move/판별']),(1,1))
        self.assertEqual(self.a.pos,(4,0));self.valid()

    def test_wrong_owner_tamper_and_resumed_blockage_reject_without_losing_prefix(self):
        self.scene();event=self.pending()
        assert_rejections_unchanged(self.e,[
            lambda:self.choose(event,self.b),
            lambda:self.e.choose_move_defense(event,self.r,use=True,
                options={'path':[(1,3),(1,2),(1,1),(1,0)],'skill':'육상','shove_destination':[2,0]},
                reason='actual Intercept cannot occupy the paid Pass body'),
            lambda:self.e.use_pass_move(self.a,self.mid,(4,0),event_id='pass/1',
                object_adjudications=self.objects,source='wrong/source',reason='actual Pass object hits and pre-DR damage'),
        ],reason_pattern=['next actual defense owner','Intercept route is blocked or occupied','identity conflicts'])
        saved=self.e.export_state();bad=deepcopy(saved)
        # Change a serialized native definition through fresh Rules, preserving the actual save.
        wrong=Rules(ROOT,ruleset=self.e.r.ruleset.name)
        wrong.ruleset.profile='wrong-source-profile'
        with self.assertRaisesRegex(ValueError,'fingerprint|profile'):Engine.import_state(wrong,bad)
        self.e.grid.blocking.add((2,0));self.valid()
        with patch.object(Engine,'d20',return_value=16):
            assert_rejected_unchanged(self.e,lambda:self.choose(event),reason_pattern='Pass movement interrupted')
        self.e.grid.blocking.remove((2,0))
        self.assertEqual(self.a.pos,(1,0));self.assertEqual(self.e._pass_moves['pass/1']['results'],[])
        continuation=self.e._move_completions[self.e._pass_moves['pass/1']['completion_id']]['activation_continuation']
        continuation['scope']['prepaid_pass']['target_index']=1
        with self.assertRaisesRegex(ValueError,'authenticated actual path continuation'):PASS.validate_world(self.e)
        with self.assertRaisesRegex(ValueError,'world reference integrity: physical_object_attack'):self.e.export_state()

    def test_native_cancellation_commits_interrupted_prefix_without_remaining_hits(self):
        self.scene(objects=False)
        self.e.apply_status(self.a,'혼란',source='move/이상한빛',applied_by=self.b)
        hp=(self.b.hp,self.c.hp);event=self.pending()
        self.e.gm.faint(self.a,reason='actual attacker faints during the defense wait')
        row=self.e.deliver_passive_event(event)
        self.assertEqual(row['phase'],'interrupted');self.assertEqual(self.a.pos,(1,0))
        self.assertEqual((self.b.hp,self.c.hp),hp);self.assertTrue(self.a.fainted)
        self.assertEqual(row['confusion']['result']['reason'],'cancelled')
        self.assertEqual(row['results'],[{'kind':'creature','id':self.b.entity_id,'dealt':0,'cancelled':True}])
        completion=self.e._move_completions[row['completion_id']]
        self.assertEqual(completion['phase'],'interrupted');self.assertEqual(completion['started'],[self.b.entity_id])
        self.assertEqual(self.a.move_uses[self.mid],1);self.assertIsNone(self.e._passive_pending)
        self.valid();self.restore();self.valid()

    def test_heavy_uncertainty_initial_and_resumed_boundaries_remain_explicit(self):
        self.scene(objects=False,watch=False)
        self.e.gm.set_injuries(self.b,value=5,reason='actual existing heavy injuries')
        with patch.object(Engine,'d20',return_value=16):
            assert_rejected_unchanged(self.e,self.use,reason_pattern='Pass Heavy continuation is not executable')
        self.scene(objects=False);event=self.pending()
        self.e.gm.set_injuries(self.b,value=5,reason='actual injuries before resuming this hit')
        with patch.object(Engine,'d20',return_value=16):
            assert_rejected_unchanged(self.e,lambda:self.choose(event),reason_pattern='Pass Heavy continuation is not executable')
        self.assertEqual(self.a.pos,(1,0));self.assertEqual(self.e._pass_moves['pass/1']['phase'],'pending');self.valid()

    def test_mounted_diagonal_pool_is_committed_per_cell_and_restored(self):
        f=BOOK.ConquerorsMarchTests();f.rules=self.book_rules;f.setup(moves=[BOOK.FAMILY_MOVES['대시']])
        f.enemy.pos=(1,1);f.other.pos=(12,8)
        f.e.watch_move_defense(f.enemy,[{'actor_id':f.other.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual mounted diagonal reaction')
        f.start();f.order();f.close(f.a);f.e.start_of_turn(f.p)
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):
            f.pass_move(BOOK.FAMILY_MOVES['대시'],destination=(3,3))
        event=f.e._passive_pending
        self.assertEqual((f.p.pos,f.a.pos),((1,1),(1,1)))
        self.assertEqual((MOUNT.shared_movement(f.e,f.p)[2]['used'],MOUNT.shared_movement(f.e,f.p)[2]['diagonals']),(1,1))
        f.valid();f.restore()
        with patch.object(Engine,'d20',side_effect=AssertionError('saved hit must not reroll')):
            row=f.e.choose_move_defense(event,f.other,use=False,reason='actual mounted decline')
        self.assertEqual(row['phase'],'complete');self.assertEqual((f.p.pos,f.a.pos),((3,3),(3,3)))
        self.assertEqual((MOUNT.shared_movement(f.e,f.p)[2]['used'],MOUNT.shared_movement(f.e,f.p)[2]['diagonals']),(4,3))
        self.assertEqual(f.p.move_uses[BOOK.FAMILY_MOVES['대시']],1);f.valid();f.restore();f.valid()


    def test_direct_and_routed_post_hit_waits_resume_actual_native_tail_once(self):
        from hashlib import sha256
        for routed in (False,True):
            with self.subTest(routed=routed):
                self.scene(objects=False,watch=False)
                self.e.gm.set_position(self.c,(9,7),reason='only one actual creature on this path')
                if routed:
                    self.e.watch_move_defense(self.b,[{'actor_id':self.r.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual routed native hit')
                else:
                    import tera_shell as TS
                    self.e.gm.set_ability(self.b,'테라셸',reason='actual native pre-hit choice without routing')
                    self.e.watch_ability_interrupt(self.b,TS.SOURCE,reason='actual direct native choice')
                source='input/'+self.e.r.selection.units['combat/struggle']['source']['file']
                document={'schema':1,'id':'event/pass-resumed-choice','variants':[{
                    'rule_id':'combat/struggle','source':{'file':source,'sha256':sha256((ROOT/source).read_bytes()).hexdigest()},
                    'inputs':{'hit':{'authority':'context','type':'boolean','question':'Native hit'},
                              'choice':{'authority':'gm','type':'boolean','question':'Actual application choice'}},
                    'when':{'op':'eq','left':{'$input':'hit'},'right':True},
                    'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}]}
                listener=self.e.subscribe_source_policy(self.a,'resumed-choice',document,event='move_resolved',inputs={'hit':'hit'})
                event=self.pending()
                with patch.object(Engine,'d20',return_value=16):
                    with self.assertRaises(EVENTS.PassiveEventPending):
                        if routed:self.choose(event)
                        else:self.e.choose_ability_interrupt(event,self.b,use=False,reason='actual direct decline')
                    child=self.e._passive_pending
                    if routed:
                        self.assertNotEqual(child,event)
                        self.assertEqual(self.e._passive_events[child]['defense_parent'],event)
                    else:self.assertEqual(child,event)
                    hp=self.b.hp;rng=self.e.rng.getstate();self.valid();self.restore()
                    row=self.e.choose_passive_event(child,self.a,listener,{'decisions':{'choice':{'value':True,'reason':'actual accepted application reaction'}}})
                    self.assertEqual(row['phase'],'complete');self.assertEqual(self.a.pos,(4,0))
                    self.assertEqual((self.b.hp,self.e.rng.getstate()),(hp,rng))
                    self.assertEqual(self.a.stages['atk'],1);self.assertEqual(self.a.move_uses[self.mid],1)
                self.valid()

    def test_real_rough_skin_incapacitation_keeps_hit_and_stops_initial_or_resumed_path(self):
        for waiting in (False,True):
            with self.subTest(resumed=waiting):
                self.scene(objects=False,watch=waiting)
                self.e.gm.set_ability(self.b,'까칠한피부/철가시',reason='actual native Rough Skin Ability')
                self.e.gm.set_temp_hp(self.b,100,reason='actual temporary HP keeps reacting defender conscious')
                self.e.gm.set_hp(self.a,value=1,reason='actual attacker HP before contact')
                hp=self.c.hp;expected_hp=self.a.hp-self.e.tick(self.a)
                with patch.object(Engine,'d20',return_value=16):
                    if waiting:
                        event=self.pending();row=self.choose(event)
                    else:row=self.use()
                self.assertTrue(self.a.fainted);self.assertEqual(self.a.hp,expected_hp)
                self.assertEqual(row['phase'],'interrupted');self.assertEqual(self.a.pos,(1,0))
                self.assertEqual(self.c.hp,hp);self.assertEqual(len(row['results']),1)
                self.assertGreater(row['results'][0]['dealt'],0);self.assertFalse(row['results'][0].get('cancelled',False))
                self.assertEqual(self.a.move_uses[self.mid],1);self.valid();self.restore();self.valid()

    def test_separate_recipient_ability_interrupts_keep_their_native_prepared_move(self):
        self.scene(objects=False,watch=False)
        import tera_shell as TS
        for actor in (self.b,self.c):
            self.e.gm.set_ability(actor,'테라셸',reason='actual native recipient Type choice Ability')
            self.e.watch_ability_interrupt(actor,TS.SOURCE,reason='actual chosen native type defense')
        first=self.pending()
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):
            self.e.choose_ability_interrupt(first,self.b,use=True,options={'chosen_type':'강철'},reason='first actual recipient choice')
        second=self.e._passive_pending;self.valid();self.restore()
        with patch.object(Engine,'d20',side_effect=AssertionError('saved hit must not reroll')):
            row=self.e.choose_ability_interrupt(second,self.c,use=False,reason='second actual recipient decline')
        self.assertEqual(row['phase'],'complete');self.assertEqual(self.b.types,['강철']);self.valid()
        import move_completion as COMPLETE
        completed=self.e._move_completions[row['completion_id']]
        self.assertEqual(list(completed['target_moves']),[self.b.entity_id,self.c.entity_id])
        event=self.e._passive_events[second]
        self.assertEqual(COMPLETE.event_move(self.e,event)['_actual_targets'],(self.c,))


    def test_legacy_saved_group_resumes_without_inventing_prepared_target_history(self):
        import test_category2_move_defense_reactions as DEFENSE
        import move_completion as COMPLETE
        self.scene(objects=False,watch=False)
        f=DEFENSE.MoveDefenseReactionsTests();f.rules=self.e.r;f.setUp();f.r.pos=(3,4);f.watch()
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):
            f.e.use_move_on(f.a,f.t,'move/지진',f.e.everyone,set_damage=True)
        event=f.e._passive_pending;row=f.completion();before=f.e.export_state()
        original_items=list(row.items());prepared=row.pop('target_moves')
        legacy=json.loads(json.dumps(f.e.export_state(),ensure_ascii=False))
        row.clear();row.update(original_items)
        self.assertEqual(f.e.export_state(),before)
        first=next(iter(prepared));missing=prepared.pop(first)
        with self.assertRaisesRegex(ValueError,'prepared target Moves require their actual native starts'):
            COMPLETE.validate_world(f.e,WORLD.actor_index(f.e))
        with self.assertRaisesRegex(ValueError,'actual prepared target Move missing'):
            COMPLETE.event_move(f.e,f.e._passive_events[event])
        prepared[first]=missing
        ids=[actor.entity_id for actor in (f.a,f.t,f.r)]
        f.e=Engine.import_state(Rules(ROOT,ruleset='core'),legacy)
        f.a,f.t,f.r=[WORLD.actor_index(f.e)[uid] for uid in ids]
        hp=(f.t.hp,f.r.hp);rng=f.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('legacy saved accuracy cannot reroll')):
            f.choose(event,use=False)
        self.assertEqual(f.completion()['phase'],'complete');self.assertNotIn('target_moves',f.completion())
        self.assertTrue(f.t.hp<hp[0] and f.r.hp<hp[1]);self.assertEqual(f.e.rng.getstate(),rng)
        self.assertEqual((f.a.move_uses['move/지진'],f.a._action_history),(1,['standard']))
        f.fresh();self.assertTrue(f.e.validate_state()['valid'])
