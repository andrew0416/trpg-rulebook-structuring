"""Actual shared mapless positions drive paid movement and native area attacks."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'engine') not in sys.path:sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import state_fields as F
import world_entities as W
import mapless_space as SPACE
import turn as TURN
from state_codec import load_engine


class MaplessFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,15);self.e.everyone=self.e.gm.everyone=[]
        self.a=self.actor('user','party');self.b=self.actor('same name');self.c=self.actor('same name');self.d=self.actor('distant')
        self.places={'stairs':'계단','fountain':'로비의 분수','corridor':'복도'}
        self.placements={self.a.entity_id:'stairs',self.b.entity_id:'fountain',
                         self.c.entity_id:'fountain',self.d.entity_id:'corridor'}
        self.configure()
        TURN.reset_budget(self.e,self.a)

    def actor(self,name,side='foes'):
        c=Combatant(self.r,dict(name=name,kind='pokemon',level=20,stats={s:30 for s in F.STATS},
            types=['노말'],moves=['move/방전','move/스피드스타','move/몸통박치기','move/물대포'],abilities=[],movement={'land':4}))
        c.side=side;self.e.everyone.append(c);return c

    def configure(self,contacts=None):
        return self.e.gm.observe_mapless_scene(scene_id='lobby',places=self.places,
            placements=self.placements,contacts=contacts or [],reason='GM observed lobby, fountain and actual contact')

    def area(self,event='area',move_id='move/스피드스타'):
        return self.e.gm.observe_mapless_targets(self.a,event_id=event,move_id=move_id,
            landmark_id='fountain',target_ids=[self.b.entity_id,self.c.entity_id],
            reason='GM judges these two near the fountain inside the actual burst')

    def movement(self,cost=4,event='walk',contacts=None):
        return self.e.gm.observe_mapless_movement(self.a,event_id=event,destination='fountain',
            movement_cost=cost,contacts_after=contacts or [],reason='GM observed the required travel allowance')

    def snap(self):return self.e.export_state()

class MaplessTests(MaplessFixture):
    def test_native_shift_and_sprint_pay_once_and_invalidate_old_area(self):
        self.area();self.movement(6)
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'allowance'):self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(before,self.snap())
        self.assertTrue(self.e.sprint(self.a,source_policy='ch06_once'))
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(W.location_of(self.a),{'kind':'abstract','place_id':'fountain'})
        self.assertEqual((self.a.budget['standard'],self.a.budget['shift']),(0,0))
        self.assertNotIn('질주',self.a.custom_conditions)
        before=self.snap();self.assertEqual(result,self.e.move_abstract(self.a,event_id='walk'))
        self.assertEqual(before,self.snap())
        with self.assertRaisesRegex(ValueError,'stale'):
            self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),self.e.everyone,self.b)
        # Replaying the old observation is not permission to refresh it.
        self.area()
        with self.assertRaisesRegex(ValueError,'stale'):
            self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),self.e.everyone,self.b)
        self.area('new-area')
        self.assertEqual(self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),self.e.everyone,self.b),[self.b,self.c])

    def test_actual_area_attack_hits_only_observed_instances_and_pays_one_standard(self):
        self.area(move_id='move/스피드스타');before=[c.hp for c in (self.a,self.b,self.c,self.d)]
        self.e.use_move_on(self.a,self.b,'move/스피드스타',self.e.everyone)
        self.assertEqual(self.a.hp,before[0]);self.assertLess(self.b.hp,before[1]);self.assertLess(self.c.hp,before[2]);self.assertEqual(self.d.hp,before[3])
        self.assertEqual(self.a.budget['standard'],0)
        self.assertNotEqual(self.b.entity_id,self.c.entity_id)

    def test_contact_melee_is_explicit_and_direct_use_cannot_bypass_area_relation(self):
        self.configure([[self.a.entity_id,self.b.entity_id]])
        self.assertTrue(self.e.adjacent(self.a,self.b));self.assertFalse(self.e.adjacent(self.b,self.c))
        melee=self.r.move('move/몸통박치기')
        self.assertEqual(self.e.targets_in_range(self.a,melee,self.e.everyone,self.b),[self.b])
        self.assertEqual(self.e.targets_in_range(self.a,melee,self.e.everyone,self.c),[])
        self.area();before=self.snap()
        with self.assertRaisesRegex(ValueError,'outside'):
            self.e.use_move(self.a,self.d,'move/스피드스타')
        self.assertEqual(self.snap(),before)
        self.movement();before_hp=self.a.hp;self.e.rng.seed(6)
        result=self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(result['phase'],'complete')
        self.assertTrue(self.b.aoo_used);self.assertLess(self.a.hp,before_hp)
        self.assertEqual(W.location_of(self.a)['place_id'],'fountain')

    def test_both_restorations_and_scene_boundary_preserve_or_end_observed_relations(self):
        self.area();self.movement();saved=self.e.gm.snapshot()
        loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        actors={c.entity_id:c for c in loaded.everyone};a=actors[self.a.entity_id]
        self.assertEqual([x.entity_id for x in loaded.targets_in_range(a,self.r.move('move/스피드스타'),loaded.everyone,actors[self.b.entity_id])],[self.b.entity_id,self.c.entity_id])
        loaded.move_abstract(a,event_id='walk')
        self.e.move_abstract(self.a,event_id='walk');self.e.gm.restore(saved)
        self.assertEqual(W.location_of(self.a)['place_id'],'stairs')
        self.assertEqual(self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),self.e.everyone,self.b),[self.b,self.c])
        self.e.end_encounter();self.assertTrue(SPACE.active(self.e))
        self.e.end_scene();self.assertFalse(SPACE.active(self.e))

    def test_invalid_and_late_failed_movement_preserve_budget_locations_and_relations(self):
        self.area();self.movement();before=self.snap()
        original=W.observe_location
        def fail_after_move(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('late move failure')
        with patch.object(W,'observe_location',side_effect=fail_after_move):
            with self.assertRaisesRegex(ValueError,'late move failure'):
                self.e.move_abstract(self.a,event_id='walk')
        self.assertEqual(self.snap(),before)
        self.a.conditions.add('넘어짐')
        self.assertFalse(self.e.move_abstract(self.a,event_id='walk'))
        self.assertEqual(W.location_of(self.a)['place_id'],'stairs')

    def test_external_position_change_and_tampered_observation_are_not_trusted(self):
        self.area();self.b.location={'kind':'abstract','place_id':'corridor'}
        with self.assertRaisesRegex(ValueError,'stale'):
            self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),self.e.everyone,self.b)
        self.configure();self.area('current')
        saved=self.e.gm.snapshot();before=self.snap()
        self.e.gm.snapshots[saved]['engine']['_mapless_space']['observations']['current']['declaration']['target_ids'].append(self.d.entity_id)
        with self.assertRaises(ValueError):self.e.gm.restore(saved)
        self.assertEqual(self.snap(),before)

    def test_discharge_hits_the_complete_observed_area_with_shared_natural_effect(self):
        self.area(move_id='move/방전')
        self.e.rng.seed(6);before=[c.hp for c in self.e.everyone]
        self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertEqual([self.a.hp,self.d.hp],[before[0],before[3]])
        for c,hp in zip((self.b,self.c),before[1:3]):
            self.assertLess(c.hp,hp);self.assertIn('마비',c.conditions)
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(self.a.move_uses['move/방전'],1)
        self.assertEqual(self.e.effect_stats['held'],0)

    def test_single_target_stays_single_and_duplicate_candidates_do_not_repeat_area_hits(self):
        self.area(move_id='move/물대포')
        targets=self.e.targets_in_range(self.a,self.r.move('move/물대포'),self.e.everyone,self.b)
        self.assertEqual(targets,[self.b])
        before=self.c.hp
        self.e.use_move_on(self.a,self.b,'move/물대포',self.e.everyone)
        self.assertEqual(self.c.hp,before)
        self.area('swift-area')
        self.assertEqual(self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),
            [self.b,self.b,self.c],self.b),[self.b,self.c])
        foreign=deepcopy(self.b)
        with self.assertRaises(ValueError):
            self.e.targets_in_range(self.a,self.r.move('move/스피드스타'),[foreign],foreign)
        self.e.end_scene()
        self.assertEqual(self.e.targets_in_range(self.a,self.r.move('move/물대포'),self.e.everyone,self.b),[self.b])


if __name__=='__main__':unittest.main()
