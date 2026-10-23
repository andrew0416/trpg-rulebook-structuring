"""Actual zone movement and selected native area recipients, costs and history."""
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import test_mapless_space as BASE
import effects as FX
import state_codec
import turn as TURN
from native_scenario_fixture import prepare_scene

class Tests(BASE.MaplessFixture):
    def meaningful(self):
        return (deepcopy(self.a.budget),[c.hp for c in self.e.everyone],
                self.e.rng.getstate(),deepcopy(self.e._mapless_space))

    def test_electroweb_uses_the_same_native_recipient_boundary_once_per_hit(self):
        self.a.moves.append('move/일렉트릭네트');self.area(move_id='move/일렉트릭네트')
        self.e.rng.seed(6)
        self.e.use_move_on(self.a,self.b,'move/일렉트릭네트',self.e.everyone)
        self.assertEqual([c.stages['spe'] for c in self.e.everyone],[0,-1,-1,0])
        self.assertEqual(self.a.move_uses['move/일렉트릭네트'],1)
        self.assertEqual(self.e.effect_stats['held'],0)

    def test_shared_low_natural_and_electric_immunity_keep_their_native_conditions(self):
        self.area(move_id='move/방전');self.e.rng.seed(2)
        before=[c.hp for c in self.e.everyone]
        self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertTrue(all('마비' not in c.conditions for c in self.e.everyone))
        self.assertEqual([c.hp for c in self.e.everyone],before)
        self.setUp();self.area(move_id='move/방전');self.e.rng.seed(6)
        self.b.types=['전기']
        self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertNotIn('마비',self.b.conditions);self.assertIn('마비',self.c.conditions)

    def test_direct_activation_omitted_target_and_forged_hit_do_not_apply_group_effects(self):
        self.area(move_id='move/방전');before=self.meaningful()
        with self.assertRaisesRegex(ValueError,'complete native target activation'):
            self.e.use_move(self.a,self.b,'move/방전')
        self.assertEqual(before,self.meaningful())
        with self.assertRaisesRegex(ValueError,'omitted'):
            self.e.use_move_on(self.a,self.b,'move/방전',[self.a,self.b])
        self.assertEqual(before,self.meaningful())
        effect=self.r.move_mech('move/방전')[0]['effects_exec'][0]
        result=FX.run_effects(self.e,self.a,self.b,[effect],
            dict(hit=True,nat=19,move=self.r.move('move/방전'),engine=self.e), 'move/방전')
        self.assertEqual(result[1],1)
        self.assertNotIn('마비',self.b.conditions);self.assertNotIn('마비',self.c.conditions)

    def test_actual_zone_shift_contact_and_new_landmark_ruling_feed_discharge(self):
        self.area(move_id='move/방전');self.movement(4,contacts=[[self.a.entity_id,self.b.entity_id]])
        self.e.move_abstract(self.a,event_id='walk')
        self.assertTrue(self.e.adjacent(self.a,self.b));self.assertEqual(self.a.budget['shift'],0)
        before=self.meaningful()
        with self.assertRaisesRegex(ValueError,'stale'):
            self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertEqual(before,self.meaningful())
        self.area('after-actual-approach',move_id='move/방전');self.e.rng.seed(6)
        self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertTrue(all('마비' in c.conditions for c in (self.b,self.c)))
        self.assertEqual(self.a.budget['standard'],0)

    def test_restored_landmark_and_completed_hits_preserve_selected_source_and_usage(self):
        self.area(move_id='move/방전');saved=self.e.gm.snapshot()
        loaded=state_codec.load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        actual={c.entity_id:c for c in loaded.everyone};a=actual[self.a.entity_id]
        loaded.rng.seed(6);loaded.use_move_on(a,actual[self.b.entity_id],'move/방전',loaded.everyone)
        restored=state_codec.load_engine(self.r,json.loads(json.dumps(loaded.export_state(),ensure_ascii=False)))
        again={c.entity_id:c for c in restored.everyone}
        self.assertEqual(again[a.entity_id].move_uses['move/방전'],1)
        self.assertTrue(all('마비' in again[c.entity_id].conditions for c in (self.b,self.c)))
        self.e.gm.restore(saved);self.e.rng.seed(6)
        self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertTrue(all('마비' in c.conditions for c in (self.b,self.c)))

    def test_changed_selected_effect_is_not_authorized_by_the_shared_selector(self):
        self.area(move_id='move/방전');before=self.meaningful()
        original=self.r.move_mech
        def changed(mid):
            value,confidence=original(mid)
            value=deepcopy(value)
            if mid=='move/방전':value['effects_exec'][0]['on_natural_roll_min']=1
            return value,confidence
        with patch.object(self.r,'move_mech',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'unchanged reviewed selected source'):
                self.e.use_move_on(self.a,self.b,'move/방전',self.e.everyone)
        self.assertEqual(before,self.meaningful())

    def test_existing_numeric_grid_area_keeps_its_native_geometry_and_stage_effect(self):
        mid='move/일렉트릭네트'
        rows=[dict(key=key,kind='trainer',
            sheet=dict(name=key,level=10,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
                       moves=[mid],abilities=[],pos=(i,0),side=side),
            body=dict(size='중형',offsets=[(0,0)],reason='actual mapped native area participant'))
            for i,(key,side) in enumerate((('attacker','party'),('target','foe')))]
        e,actors=prepare_scene(BASE.ROOT,ruleset='core',seed=6,
            grid={'width':10,'height':10},actors=rows)
        a,b=actors['attacker'],actors['target']
        e.start_round(e.everyone);e.start_of_turn(a)
        e.use_move_on(a,b,mid,e.everyone)
        self.assertEqual(b.stages['spe'],-1)
        self.assertEqual(a.move_uses[mid],1)
        self.assertEqual(a.budget['standard'],0)
        self.assertEqual(e.effect_stats['held'],0)

if __name__=='__main__':unittest.main()
