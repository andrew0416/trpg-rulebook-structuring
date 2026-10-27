"""Native regressions for the original procedural caller routes; Actions only."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Rules
import body_state as BODY
import combat_timing as TIME
import encounter
import initiative as INIT
import initiative_interrupts as INTERRUPTS
from native_scenario_fixture import prepare_scene,assert_rejected_unchanged
import test_foundation_initiative_schedule as FIXTURE


class ProceduralInitiativeTests(unittest.TestCase):
    setUpClass=classmethod(FIXTURE.InitiativeScheduleTests.setUpClass.__func__)
    setUp=FIXTURE.InitiativeScheduleTests.setUp
    actor=FIXTURE.InitiativeScheduleTests.actor

    def test_adjudicated_value_and_exact_tie_order_survive_schedule_and_codec(self):
        a,b,c=self.a,self.b,self.c
        self.e.apply_status(a,'마비',source='gm/observed-paralysis')
        self.e.gm.set_initiative(a,30,reason='actual fixed value requires explicit composition')
        b.stats['spe']=17
        prompts=[]
        def decide(prompt):
            prompts.append(prompt['type'])
            if prompt['type']=='initiative_value':
                return {'value':17,'reason':'explicit composition chosen once'}
            return {'order':['actor:1','actor:0'],'request_id':prompt['request_id'],
                    'reason':'explicit tied actors, second first'}
        self.e.rulings.provider=decide
        before=self.e.rng.getstate()
        prepared=self.e.prepare_initiative_schedule([a,b,c],source='gm/test-schedule')
        self.assertEqual(prepared['status'],'prepared')
        state=self.e._initiative_schedule
        self.assertEqual([state['slots'][key]['actor'] for key in state['order']],[b,a,c])
        self.assertEqual(state['initiative_values'],{a.entity_id:17,b.entity_id:17,c.entity_id:10})
        self.assertEqual(prompts,['initiative_value','initiative_tie_order'])
        self.assertEqual(self.e.rng.getstate(),before)
        self.e.rulings.provider=None
        cold=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.e.export_state())))
        self.assertEqual(cold._initiative_schedule['initiative_values'],state['initiative_values'])
        self.e.start_round([a,b,c])
        for actor in (b,a,c):
            count=state['initiative_values'][actor.entity_id]
            self.e.start_of_turn(actor,initiative_count=count)
            self.assertEqual(TIME.current(self.e),count)
            self.e.end_of_turn(actor)
        self.e.end_round()

    def test_pending_order_does_not_write_resolved_value_sink(self):
        self.b.stats['spe']=self.a.stats['spe']
        sink={'prior':11};before=self.e.rng.getstate()
        self.assertIsNone(INIT.order(self.e,[self.a,self.b],resolved_values=sink))
        self.assertEqual(sink,{'prior':11})
        self.assertEqual(self.e.rng.getstate(),before)
        self.assertEqual(self.e.round_no,0)

    def test_original_builder_and_turn_encounter_routes_pass_actual_counts(self):
        observed=[]
        original=Engine.start_of_turn
        def start(host,actor,*args,**kwargs):
            ordinary=not INTERRUPTS.is_borrow_start(host,actor)
            expected=None
            if ordinary:
                slot=host.initiative_schedule_status()['next']['slot']
                expected=host._initiative_schedule['initiative_values'][slot]
                if kwargs.get('initiative_count')!=expected:
                    raise AssertionError('driver discarded the chosen initiative count')
            result=original(host,actor,*args,**kwargs)
            if ordinary:
                observed.append((host.round_no,actor.entity_id,TIME.current(host),expected))
            return result
        with patch.object(Engine,'start_of_turn',new=start):
            lakeside,_,_=encounter.run_encounter(str(ROOT),'data/encounters/lakeside.json',seed=5,write=False)
            cave,_,_=encounter.run_encounter(str(ROOT),'data/encounters/cave.json',write=False)
        self.assertTrue(observed)
        self.assertTrue(all(count==expected for _,_,count,expected in observed))
        self.assertGreaterEqual(lakeside.round_no,1)
        self.assertIsNotNone(cave._heavy_pending)
        self.assertEqual((cave.round_no,cave.elapsed_seconds),(3,20))
        self.assertTrue(cave.encounter_active)
        self.assertFalse(any(line.startswith('결과:') for line in cave.log_lines))


class ProceduralTargetAndAreaTests(unittest.TestCase):
    def scene(self,move='move/흡수',ruleset='core'):
        rows=[dict(key=key,kind='trainer',
            sheet=dict(name=key,level=30,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
                       moves=[move],abilities=[],pos=pos,side=side),
            body=dict(size='중형',offsets=[(0,0)],reason='actual mapped procedural regression actor'))
            for key,pos,side in (('a',(1,2),'party'),('b',(3,2),'foe'),('c',(4,2),'foe'))]
        e,actors=prepare_scene(ROOT,ruleset=ruleset,seed=6,grid={'width':12,'height':8},actors=rows)
        return e,actors['a'],actors['b'],actors['c']

    def test_recalled_target_query_rejects_before_missing_body_geometry(self):
        e,a,b,c=self.scene()
        e.gm.recall(b,reason='actual recall removes its concrete location')
        before=e.export_state()
        self.assertFalse(b.on_field)
        self.assertEqual(e.targets_in_range(a,e.r.move('move/흡수'),[a,b,c],b),[])
        self.assertEqual(e.export_state(),before)
        with self.assertRaisesRegex(ValueError,'concrete location'):
            BODY.cells(b,require_complete=True)

    def test_eligible_target_still_requires_real_geometry(self):
        e,a,b,c=self.scene()
        b.spec.pop('footprint')
        with self.assertRaisesRegex(ValueError,'concrete location'):
            e.targets_in_range(a,e.r.move('move/흡수'),[a,b,c],b)

    def test_homebrew_blizzard_retains_shared_hit_threshold_and_one_cost(self):
        for natural in (16,17):
            with self.subTest(natural=natural):
                e,a,b,c=self.scene('move/눈보라-홈브류','homebrew')
                self.assertEqual(e.r.move('move/눈보라')['id'],'move/눈보라-홈브류')
                e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
                e.d20=lambda:natural
                e.use_move_on(a,b,'move/눈보라',e.everyone)
                self.assertEqual(['얼음' in target.conditions for target in (b,c)],[natural>=17]*2)
                self.assertEqual(a.move_uses['move/눈보라-홈브류'],1)
                self.assertEqual(a.budget['standard'],0)
                self.assertEqual(e.effect_stats['held'],0)

    def test_homebrew_blizzard_does_not_allow_direct_or_omitted_area_activation(self):
        e,a,b,c=self.scene('move/눈보라-홈브류','homebrew')
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        assert_rejected_unchanged(e,lambda:e.use_move(a,b,'move/눈보라'),
                                 reason_pattern='complete native target activation')
        assert_rejected_unchanged(e,lambda:e.use_move_on(a,b,'move/눈보라',[a,b]),
                                 reason_pattern='omitted')


if __name__=='__main__':unittest.main()
