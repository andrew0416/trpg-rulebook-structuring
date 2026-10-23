"""Independent checks for source binding and shared Type Link consumption."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_priority_actions as P
import class_passive_combat as CLASSES
import priority_actions as PRIORITY
from state_codec import dump_engine


class PriorityIndependentTests(unittest.TestCase):
    setUpClass=classmethod(P.PriorityActionTests.setUpClass.__func__)
    setUp=P.PriorityActionTests.setUp
    actor=P.PriorityActionTests.actor
    close=P.PriorityActionTests.close
    complete_round=P.PriorityActionTests.complete_round

    def test_actual_interrupt_return_is_numeric_and_consumed_once_across_restores(self):
        import passive_events as EVENTS
        import move_completion as COMPLETE
        for restore in ('live','snapshot','fresh_rules'):
            with self.subTest(restore=restore):
                self.setUp()
                self.foe.spec['abilities']=['테라셸']
                self.foe.abilities=['테라셸']
                self.e.register_abilities(self.foe)
                self.e.watch_ability_interrupt(self.foe,'ability/테라셸',reason='actual defensive choice')
                hp=self.foe.hp
                with self.assertRaises(EVENTS.PassiveEventPending):
                    self.e.use_priority_move(self.p,self.foe,P.QUICK)
                event=self.e._passive_pending
                self.assertEqual(self.foe.hp,hp)
                if restore=='snapshot':
                    self.e.gm.snapshot('native-return')
                    self.e.gm.restore('native-return')
                elif restore=='fresh_rules':
                    P.PriorityActionTests.fresh(self)
                result=self.e.choose_ability_interrupt(event,self.foe,use=True,
                    options={'chosen_type':'강철'},reason='native recipient chooses')
                self.assertIs(type(result),int)
                row=self.e._move_completions[self.e._passive_events[event]['completion_id']]
                self.assertEqual(row['phase'],'complete')
                self.assertEqual(row['results'][self.foe.entity_id]['dealt'],result)
                self.assertEqual(hp-self.foe.hp,result)
                self.assertNotIn('activation_continuation',row)
                COMPLETE.require_returned_event(self.e,event)
                self.assertEqual(self.p.move_uses[P.QUICK],1)
                self.assertEqual(self.p.budget,{'standard':0,'shift':1,'swift':1})
                self.assertEqual(len(self.e.initiative_reaction_status()['owed_turns']),1)
                before=dump_engine(self.e)
                EVENTS.deliver(self.e,event)
                self.assertEqual(before,dump_engine(self.e))
                with self.assertRaises(ValueError):
                    self.e.choose_ability_interrupt(event,self.foe,use=True,
                        options={'chosen_type':'강철'},reason='duplicate choice')
                self.assertEqual(before,dump_engine(self.e))
                self.complete_round()

    def test_both_printed_electric_type_link_choices_feed_actual_advanced_activation(self):
        for skill in ('집중','기술학'):
            with self.subTest(skill=skill):
                if skill!='집중':self.setUp()
                self.t.spec['skills']={skill:'전문'}
                self.t.spec['type_link_skills']={'전기':skill}
                self.assertEqual(CLASSES.type_link_rank(self.e,self.t,'전기'),5)
                hp=self.foe.hp
                self.e.use_priority_move(self.p,self.foe,P.THUNDER,shocking_speed=self.t)
                self.assertLess(self.foe.hp,hp)
                self.complete_round()
                self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])

    def test_real_encounter_loader_and_ai_choose_native_priority(self):
        import encounter,tempfile
        document={'name':'independent actual priority','rounds':1,'seed':871,
                  'party':[{'species':'피카츄','level':100,'moves':[P.QUICK],'pos':[1,1]}],
                  'wild':[{'species':'이브이','level':99,'moves':[P.QUICK],'pos':[2,1]}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'encounter.json'
            path.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
            e,party,wild=encounter.run_encounter(ROOT,str(path),ruleset='core',write=False)
        self.assertEqual(e.initiative_schedule_status()['status'],'completed')
        self.assertFalse(e.initiative_reaction_status()['owed_turns'])
        for actor in party+wild:
            self.assertEqual(actor.move_uses[P.QUICK],1)
            self.assertEqual(actor.custom_conditions['combat_turn_serial'],1)
        windows=list(e._initiative_interrupts['windows'].values())
        self.assertEqual(len(windows),2)
        self.assertTrue(all(window['requests'][0]['source']==P.QUICK for window in windows))
        dump_engine(e)

    def test_changed_printed_move_header_or_record_cannot_grant_a_priority_turn(self):
        original=deepcopy(self.r.moves[P.QUICK])
        before=dump_engine(self.e)
        changed=[]
        for field,value in (('range','근접, 대상 1, 우선(고급)'),('frequency','장면'),('type','전기')):
            row=deepcopy(original);row[field]=value;changed.append(row)
        row=deepcopy(original);row['_source']['record_span']=[1,1];changed.append(row)
        for row in changed:
            with self.subTest(changed=row):
                with patch.dict(self.r.moves,{P.QUICK:row}):
                    with self.assertRaises(ValueError):self.e.use_priority_move(self.p,self.foe,P.QUICK)
                self.assertEqual(before,dump_engine(self.e))

    def test_changed_general_or_feature_source_is_inert_before_any_free_cost(self):
        read_text=Path.read_text
        policy=PRIORITY.definition(self.r)
        before=dump_engine(self.e)
        for key in ('priority','shocking_speed','electric_type_link'):
            authority=policy['authority'][key]
            def changed(path,*args,**kwargs):
                text=read_text(path,*args,**kwargs)
                if path.as_posix().endswith(authority['file']):
                    text=text.replace(authority['excerpt'],authority['excerpt']+' source changed',1)
                return text
            with self.subTest(authority=key),patch.object(Path,'read_text',changed):
                with self.assertRaises(ValueError):
                    self.e.use_priority_move(self.p,self.foe,P.THUNDER,shocking_speed=self.t)
            self.assertEqual(before,dump_engine(self.e))


class UnavailableScheduleTests(unittest.TestCase):
    import test_foundation_initiative_schedule as F
    setUpClass=classmethod(F.InitiativeScheduleTests.setUpClass.__func__)
    setUp=F.InitiativeScheduleTests.setUp
    actor=F.InitiativeScheduleTests.actor
    prepare=F.InitiativeScheduleTests.prepare
    close=F.InitiativeScheduleTests.close

    def test_native_unavailable_step_has_no_owner_turn_and_restores(self):
        import initiative_schedule as S
        from state_codec import load_engine
        for reason in ('fainted','captured','off_field'):
            with self.subTest(reason=reason):
                self.setUp();self.prepare();self.e.start_round(self.e.everyone)
                before=dump_engine(self.e)
                with self.assertRaises(ValueError):S.skip_unavailable(self.e,self.a)
                self.assertEqual(before,dump_engine(self.e))
                if reason=='fainted':self.a.hp=0;self.a.conditions.add('기절')
                elif reason=='captured':self.a.captured=True
                else:self.a.on_field=False
                before=dump_engine(self.e)
                with self.assertRaises(ValueError):S.skip_unavailable(self.e,self.b)
                self.assertEqual(before,dump_engine(self.e))
                clocks=(self.e.elapsed_seconds,self.e.rng.getstate(),deepcopy(self.e._turn_closures),
                        deepcopy(self.a.custom_conditions),deepcopy(getattr(self.a,'budget',None)))
                S.skip_unavailable(self.e,self.a)
                self.assertEqual(clocks,(self.e.elapsed_seconds,self.e.rng.getstate(),self.e._turn_closures,
                                        self.a.custom_conditions,getattr(self.a,'budget',None)))
                self.e.gm.snapshot('skipped');self.e.gm.restore('skipped')
                e=load_engine(P.Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
                self.assertEqual(S.status(e)['completed_steps'],1)
                before=dump_engine(self.e)
                with self.assertRaises(ValueError):S.skip_unavailable(self.e,self.a)
                self.assertEqual(before,dump_engine(self.e))
                self.close(self.b);self.close(self.c);self.e.end_round()

    def test_skipped_declaration_does_not_create_intent_or_skip_later_turn(self):
        import initiative_schedule as S
        self.prepare(layout=[{'id':'declare','roles':['*'],'reverse':False,'declaration':True},
                             {'id':'resolve','roles':['*'],'reverse':False,'declaration':False}])
        self.e.start_round(self.e.everyone);self.a.on_field=False
        S.skip_unavailable(self.e,self.a)
        self.e.declare_scheduled_action(self.b,{'action':'wait'})
        self.e.declare_scheduled_action(self.c,{'action':'wait'})
        self.a.on_field=True
        self.close(self.a);self.close(self.b);self.close(self.c)
        self.assertNotIn(self.a.entity_id,self.e._initiative_schedule['declarations'])
        self.e.end_round();dump_engine(self.e)

    def test_actual_borrowed_slot_cannot_be_erased_by_unavailable_skip(self):
        import initiative_schedule as S
        # Reuse the actual native Priority producer rather than fabricating debt.
        fixture=PriorityIndependentTests();fixture.r=self.r;fixture.setUp()
        fixture.e.use_priority_move(fixture.p,fixture.foe,P.QUICK)
        fixture.e.finish_initiative_reaction();fixture.close(fixture.t)
        fixture.p.on_field=False
        before=dump_engine(fixture.e)
        with self.assertRaises(ValueError):S.skip_unavailable(fixture.e,fixture.p)
        self.assertEqual(before,dump_engine(fixture.e))
        fixture.e.settle_borrowed_turn()
        self.assertFalse(fixture.e.initiative_reaction_status()['owed_turns'])
        dump_engine(fixture.e)

    def test_saved_skip_requires_its_unavailable_observation_and_actual_actor(self):
        import initiative_schedule as S
        self.prepare();self.e.start_round(self.e.everyone);self.a.on_field=False
        S.skip_unavailable(self.e,self.a)
        record=self.e._initiative_schedule['records'][0]
        original=dict(record['unavailable'])
        record['unavailable']={'fainted':False,'captured':False,'on_field':True}
        with self.assertRaises(ValueError):dump_engine(self.e)
        record['unavailable']=original
        record['actor']=self.b
        with self.assertRaises(ValueError):dump_engine(self.e)
        record['actor']=self.a
        dump_engine(self.e)


if __name__=='__main__':unittest.main()
