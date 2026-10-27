"""Actual ordinary close ends only its sourced CSV Paralysis action loss."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_paralysis_failed_action_source_revision as MODERN
import condition_instances as CI
import combat_timing as CLOCK
import frequency as F
import action_resources as RESOURCES
import passive_events as PASSIVE
import state_codec as CODEC
import swarm_transitions as SWARM
import turn as TURN
import world_entities as WORLD


class CsvParalysisTurnLifetimeTests(unittest.TestCase):
    scene=MODERN.ParalysisFailedActionSourceRevisionTests.scene
    begin=MODERN.ParalysisFailedActionSourceRevisionTests.begin

    def setUp(self):
        self.r=Rules(ROOT,ruleset='core-csv-status-1.05')

    def restored(self,e,*actors):
        saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
        restored=CODEC.load_engine(Rules(ROOT,ruleset=e.r.ruleset.name),saved)
        index=WORLD.actor_index(restored)
        return (restored,*(index[actor.entity_id] for actor in actors))

    def test_real_failed_turn_close_then_detect_next_payment_survives_both_restores(self):
        for restoration in ('gm','json'):
            with self.subTest(restoration=restoration):
                e,a,b=self.scene()
                e.gm.set_move(a,'move/판별',True,reason='actual learned native Detect')
                self.begin(e,a,face=4)
                self.assertIn('forbidden',a._turn_action_limit)
                self.assertFalse(TURN.spend(e,a,'standard'))
                self.assertEqual(RESOURCES.pending(a),{})
                if restoration=='gm':
                    snapshot=e.gm.snapshot('open-csv-paralysis');e.gm.restore(snapshot)
                    index=WORLD.actor_index(e);a,b=(index[c.entity_id] for c in (a,b))
                else:e,a,b=self.restored(e,a,b)
                self.assertIn('forbidden',a._turn_action_limit)
                self.assertFalse(TURN.spend(e,a,'standard'))
                e.end_of_turn(a)
                self.assertIsNone(a._turn_action_limit)
                self.assertIn('마비',a.conditions)
                if restoration=='gm':
                    snapshot=e.gm.snapshot('closed-csv-paralysis');e.gm.restore(snapshot)
                    index=WORLD.actor_index(e);a,b=(index[c.entity_id] for c in (a,b))
                else:e,a,b=self.restored(e,a,b)
                self.assertIsNone(a._turn_action_limit)
                e.start_of_turn(b,initiative_count=10)
                e.watch_move_defense(a,[{'actor_id':a.entity_id,'source':'move/판별'}],
                    reason='actual hit offers native next-Standard Detect after the closed turn')
                hp=a.hp
                with patch.object(Engine,'d20',return_value=18),self.assertRaises(PASSIVE.PassiveEventPending):
                    e.use_move(b,a,'move/몸통박치기',set_damage=True)
                event=e._passive_pending
                e,a,b=self.restored(e,a,b)
                with patch.object(Engine,'d20',side_effect=AssertionError('restore cannot reroll the existing hit')):
                    e.choose_move_defense(event,a,use=True,reason='actual native Detect after CSV turn close')
                self.assertEqual((a.hp,a.move_uses['move/판별'],b.move_uses['move/몸통박치기']),(hp,1,1))
                self.assertEqual(RESOURCES.pending(a),{'standard':1})
                self.assertIs(e._active_turn_actor,b)
                self.assertIsNone(e._passive_pending)
                self.assertIsNone(a._turn_action_limit)
                self.assertTrue(e.validate_state()['valid'])
                e,a,b=self.restored(e,a,b)
                self.assertEqual(RESOURCES.pending(a),{'standard':1})
                e.end_of_turn(b);e.end_round();e.start_round(e.everyone)
                with patch.object(Engine,'d20',return_value=5):e.start_of_turn(a,initiative_count=20)
                self.assertEqual(RESOURCES.pending(a),{})
                self.assertEqual(a.budget['standard'],0)
                self.assertIsNone(a._turn_action_limit)
                self.assertTrue(TURN.spend(e,a,'shift'))

    def configure_swarm(self,e,a):
        e.gm.set_encounter_template(a,kind='swarm',total_bars=3,
            action_slots=[{'id':'native','initiative':20}],member_count_or_band='25_to_40',
            reason='actual selected Chapter11 swarm')

    def test_swarm_failed_csv_save_final_close_releases_only_the_actual_csv_limit(self):
        e,a,b=self.scene('pokemon');self.configure_swarm(e,a)
        self.begin(e,a,face=4)
        self.assertIn('forbidden',a._turn_action_limit)
        self.assertFalse(TURN.spend(e,a,'standard'))
        self.assertFalse(SWARM.state(a)['swarm_turn']['window_used'])
        self.assertIsNone(e.end_of_turn(a,swarm_continue=False))
        self.assertEqual(SWARM.state(a)['swarm_turn']['lifecycle'],'closed')
        self.assertIsNone(a._turn_action_limit)
        e,a,b=self.restored(e,a,b)
        self.assertIsNone(a._turn_action_limit)
        self.assertEqual(sum(row['actor'] is a for row in e._turn_closures),1)
        self.assertTrue(e.validate_state()['valid'])

    def test_actual_swarm_continuation_retains_start_save_until_final_ordinary_close(self):
        e,a,b=self.scene('pokemon');self.configure_swarm(e,a)
        e.apply_status(a,'헤롱헤롱',applied_by=b)
        e.start_round(e.everyone)
        with patch.object(Engine,'d20',return_value=1):e.start_of_turn(a,initiative_count=20)
        serial=a.custom_conditions['combat_turn_serial'];turn=F.state(a)['turn']
        self.assertFalse(CI.records(a,'헤롱헤롱')[0]['csv_start_save']['closed'])
        self.assertTrue(TURN.spend(e,a,'standard','actual first swarm window Standard'))
        self.assertEqual(e.end_of_turn(a)['status'],'swarm_action_pending')
        self.assertFalse(CI.records(a,'헤롱헤롱')[0]['csv_start_save']['closed'])
        self.assertEqual(e._turn_closures,[])
        e,a,b=self.restored(e,a,b)
        with patch.object(Engine,'d20',side_effect=AssertionError('same swarm turn cannot reroll its start save')):
            e.start_of_turn(a,initiative_count=15)
        self.assertEqual((a.custom_conditions['combat_turn_serial'],F.state(a)['turn']),(serial,turn))
        self.assertFalse(CI.records(a,'헤롱헤롱')[0]['csv_start_save']['closed'])
        with self.assertRaisesRegex(ValueError,'CSV Infatuation'):CI.require_target(a,b)
        self.assertTrue(TURN.spend(e,a,'standard','actual continued swarm window Standard'))
        e.end_of_turn(a,swarm_continue=False)
        self.assertTrue(CI.records(a,'헤롱헤롱')[0]['csv_start_save']['closed'])
        self.assertEqual(SWARM.state(a)['swarm_turn']['lifecycle'],'closed')
        self.assertEqual(sum(row['actor'] is a for row in e._turn_closures),1)
        CI.require_target(a,b)
        self.assertTrue(e.validate_state()['valid'])

    def test_native_modern_dc11_limit_and_independent_children_are_not_cleared_by_csv_owner(self):
        self.r=Rules(ROOT,ruleset='core')
        e,a,_=self.scene();self.begin(e,a,face=10)
        limit=deepcopy(a._turn_action_limit)
        child=deepcopy(next(row for row in CLOCK.records(a) if 'paralysis_failed_save' in row))
        e.end_of_turn(a)
        self.assertEqual(a._turn_action_limit,limit)
        self.assertEqual(next(row for row in CLOCK.records(a) if 'paralysis_failed_save' in row),child)
        self.assertIn('취약',a.conditions)


if __name__=='__main__':unittest.main()
