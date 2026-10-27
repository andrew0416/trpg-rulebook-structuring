"""Actual selected Move completion, local Terrain consumers, and saved lifetime."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body
import test_hp_setting_source_boundaries as HP
import field_effects as FIELD
import misty_explosion as MISTY
import move_completion as COMPLETE
import world_entities as WORLD
import state_codec as CODEC


class MistyExplosionLocalFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HP.HPSettingSourceTests.setUpClass()

    def world(self,*,owned=False,loyalty=None):
        helper = HP.HPSettingSourceTests('runTest')
        e,a,t,owner = helper.world('core',owned=owned)
        e.grid = Grid(12,12)
        e.gm.set_position(a,(5,5),reason='actual centered local blast origin')
        e.gm.set_position(t,(6,5),reason='actual first burst recipient')
        if owner is not None:
            e.gm.set_position(owner,(11,11),reason='actual trainer outside the empty Burst')
            if loyalty is not None:
                e.gm.observe_loyalty(a,loyalty,reason='actual GM observation of this trainer relationship')
        def add(uid,pos):
            spec = dict(id=uid,name=uid,kind='pokemon',level=1,
                stats=dict(hp=197,atk=10,**{'def':10},spa=10,spd=10,spe=10),types=['노말'],
                skills={'육상':6,'명령':6,'집중':6},moves=[],abilities=[],movement={'land':6},items={},wild=True)
            c = Combatant(e.r,spec)
            e.gm.add_combatant(c,pos=pos,side='enemy',reason='actual local Mist observer')
            prepare_body(e,c,size='소형',offsets=[(0,0)],reason='observed local Mist one-cell body')
            return c
        second = add('misty/second',(5,6))
        outside = add('misty/outside',(9,5))
        helper.temp(e,a,100)
        e.gm.set_move(a,MISTY.SOURCE,True,reason='actual selected public Misty Explosion')
        e.start_round(e.everyone)
        e.start_of_turn(a,initiative_count=e.initiative_value(a).value)
        return e,a,t,second,outside

    def emit(self,e,a,t,second,*,hit=True):
        with patch.object(Engine,'d20',return_value=10 if hit else 1):
            e.use_move_on(a,t,MISTY.SOURCE,e.everyone,set_damage=True)

    def restored(self,e):
        return Engine.import_state(HP.HPSettingSourceTests.make_rules('core'),
            json.loads(json.dumps(e.export_state(),ensure_ascii=False)))

    def test_actual_hit_and_miss_install_one_centered_blast_after_faint_and_restore(self):
        for hit in (True,False):
            with self.subTest(hit=hit):
                e,a,t,second,outside = self.world()
                self.emit(e,a,t,second,hit=hit)
                self.assertEqual((a.hp,a.temp_hp,a.injuries),(-42,100,3))
                self.assertTrue(a.fainted)
                self.assertEqual(a.move_uses[MISTY.SOURCE],1)
                rows = [r for r in FIELD.validate_local(e) if r['source_id']==MISTY.SOURCE]
                self.assertEqual(len(rows),1)
                row = rows[0]
                self.assertEqual(row['geometry']['shape'],'blast')
                self.assertEqual(row['geometry']['size'],7)
                self.assertEqual(row['cells'],[list(p) for p in sorted(e.grid.ranged_blast((5,5),7))])
                self.assertEqual(len(row['cells']),49)
                self.assertIn([5,5],row['cells'])
                self.assertNotIn([9,5],row['cells'])
                self.assertIsNone(e.field)
                completion = getattr(e,COMPLETE.KEY)[row['completion_id']]
                self.assertEqual(completion['phase'],'complete')
                self.assertEqual(len(completion['results']),2)
                self.assertTrue(all(r['hit'] is hit and not r['cancelled'] for r in completion['results'].values()))
                receipts = [r for r in e._effect_dispatch_receipts.values()
                            if r['source_id']==MISTY.SOURCE and r['effect'].get('type')=='field_effect']
                self.assertEqual(len(receipts),1)
                self.assertEqual(receipts[0]['status'],'completed')
                before = deepcopy(getattr(e,FIELD.LOCAL_KEY))
                COMPLETE.refresh(e,row['completion_id'])
                self.assertEqual(getattr(e,FIELD.LOCAL_KEY),before)
                e = self.restored(e)
                a,t,outside = [WORLD.actor_index(e)[c.entity_id] for c in (a,t,outside)]
                self.assertTrue(a.fainted)
                self.assertEqual(FIELD.terrain_for(e,t)['name'],'미스트')
                self.assertIsNone(FIELD.terrain_for(e,outside))
                self.assertEqual(FIELD.validate_local(e),rows)
                self.assertTrue(e.validate_state()['valid'])

    def test_actual_local_status_damage_and_field_exclusion_expire_after_five_rounds(self):
        e,a,t,second,outside = self.world()
        grass = e.r.move_mech('move/그래스필드')[0]['effects_exec'][0]
        FIELD.install(e,a,grass,'move/그래스필드')
        self.emit(e,a,t,second,hit=False)
        self.assertEqual(e.field['source_id'],'move/그래스필드')
        self.assertIsNone(FIELD.terrain_for(e,t,'그래스'))
        self.assertEqual(FIELD.terrain_for(e,outside)['name'],'그래스')
        self.assertFalse(e.apply_status(t,'화상',source='test/misty-inside',applied_by=outside))
        self.assertTrue(e.apply_status(outside,'화상',source='test/misty-outside',applied_by=t))
        e.cure_status(outside,'화상')
        dragon = e.r.move('move/용의분노')
        self.assertEqual(FIELD.damage_roll_modifier(e,outside,t,dragon,'드래곤'),-10)
        self.assertEqual(FIELD.damage_roll_modifier(e,outside,outside,dragon,'드래곤'),0)
        move = e.r.move(MISTY.SOURCE)
        self.assertEqual(e.damage_base(t,move,target=outside),15)
        self.assertEqual(e.damage_base(outside,move,target=t),10)
        e.gm.set_position(t,(8,5),reason='inside far edge of original seven-square blast')
        self.assertFalse(e.apply_status(t,'화상',source='test/misty-edge',applied_by=outside))
        e.gm.set_position(t,(9,6),reason='actual movement outside original fixed field')
        self.assertTrue(e.apply_status(t,'화상',source='test/misty-exit',applied_by=outside))
        e.cure_status(t,'화상')
        e.gm.set_position(t,(6,5),reason='actual return to original fixed field')
        e.end_of_turn(a)
        created = e.round_no
        for elapsed in range(1,6):
            e.end_round()
            e.start_round(e.everyone)
            if elapsed < 5:
                self.assertFalse(e.apply_status(t,'화상',source='test/misty-finite',applied_by=outside))
                e = self.restored(e)
                a,t,outside = [WORLD.actor_index(e)[c.entity_id] for c in (a,t,outside)]
            else:
                self.assertEqual(e.round_no,created+5)
                self.assertFalse(FIELD.validate_local(e))
                self.assertTrue(e.apply_status(t,'화상',source='test/misty-expired',applied_by=outside))
        self.restored(e)

    def test_native_volatile_delay_survives_restore_and_original_geometry_tamper_is_rejected(self):
        e,a,t,second,outside = self.world()
        self.emit(e,a,t,second,hit=False)
        self.assertTrue(e.apply_status(t,'혼란',source='test/local-misty-delay',applied_by=outside))
        self.assertNotIn('혼란',t.conditions)
        self.assertEqual(t.custom_conditions[FIELD.DEFERRED][0]['terrain_source_id'],MISTY.SOURCE)
        e = self.restored(e)
        a,t = [WORLD.actor_index(e)[c.entity_id] for c in (a,t)]
        e.end_of_turn(a)
        e.start_of_turn(t,initiative_count=e.initiative_value(t).value)
        self.assertNotIn('혼란',t.conditions)
        e.end_of_turn(t)
        self.assertIn('혼란',t.conditions)
        state = getattr(e,FIELD.LOCAL_KEY)
        key = next(iter(state['receipts']))
        original = deepcopy(state['receipts'][key])
        for field,value in (('cells',[]),('expires_round',original['round']+6),
                            ('completion_id','fabricated'),('source_row_sha256','changed')):
            row = deepcopy(original)
            row[field] = value
            row['seal'] = FIELD._local_seal(row)
            state['receipts'][key] = row
            with self.assertRaises(CODEC.StateCodecError):
                e.export_state()
            state['receipts'][key] = deepcopy(original)
        self.restored(e)

    def test_actual_empty_burst_pays_one_cost_and_installs_one_field_without_hit_or_rng(self):
        for owned in (False,True):
            with self.subTest(owned=owned):
                e,a,t,second,outside = self.world(owned=owned,loyalty=3 if owned else None)
                e.gm.set_position(t,(9,6),reason='no creature in the native damage Burst')
                e.gm.set_position(second,(10,5),reason='no second recipient in the native damage Burst')
                before_budget = deepcopy(a.budget)
                before_rng = e.rng.getstate()
                loyalty = (a.spec.get('loyalty'),a.spec.get('loyalty_revision'))
                with patch.object(Engine,'d20',side_effect=AssertionError('empty Burst must not roll accuracy')):
                    e.use_move_on(a,t,MISTY.SOURCE,e.everyone,set_damage=True)
                self.assertEqual((a.hp,a.temp_hp,a.injuries),(-42,100,3))
                self.assertEqual(a.budget['standard'],before_budget['standard']-1)
                self.assertEqual(a.budget['shift'],before_budget['shift'])
                self.assertEqual(a.move_uses[MISTY.SOURCE],1)
                self.assertEqual(e.rng.getstate(),before_rng)
                self.assertEqual((a.spec.get('loyalty'),a.spec.get('loyalty_revision')),loyalty)
                rows = FIELD.validate_local(e)
                self.assertEqual(len(rows),1)
                completion = getattr(e,COMPLETE.KEY)[rows[0]['completion_id']]
                self.assertEqual(completion['activation'],'empty_area_field')
                self.assertEqual(completion['targets'],[])
                self.assertEqual(completion['results'],{})
                self.assertEqual(completion['started'],[])
                self.assertEqual(completion['phase'],'complete')
                self.assertEqual([r['effect']['type'] for r in e._effect_dispatch_receipts.values()
                                  if r['source_id']==MISTY.SOURCE],['self_hp_set','field_effect'])
                e = self.restored(e)
                a = WORLD.actor_index(e)[a.entity_id]
                self.assertTrue(a.fainted)
                self.assertEqual(a.move_uses[MISTY.SOURCE],1)
                self.assertEqual(len(FIELD.validate_local(e)),1)

    def test_owned_empty_burst_preserves_unresolved_or_disobedient_permission_without_cost(self):
        for loyalty in (None,0):
            with self.subTest(loyalty=loyalty):
                e,a,t,second,outside = self.world(owned=True,loyalty=loyalty)
                e.gm.set_position(t,(9,6),reason='empty original native Burst')
                e.gm.set_position(second,(10,5),reason='empty original native Burst')
                before = (a.hp,a.temp_hp,a.injuries,deepcopy(a.budget),e.rng.getstate())
                with patch.object(Engine,'d20',side_effect=AssertionError('permission refusal must not roll')):
                    e.use_move_on(a,t,MISTY.SOURCE,e.everyone,set_damage=True)
                self.assertEqual((a.hp,a.temp_hp,a.injuries,a.budget,e.rng.getstate()),before)
                self.assertEqual(a.move_uses.get(MISTY.SOURCE,0),0)
                self.assertFalse(FIELD.validate_local(e))
                self.assertFalse([r for r in getattr(e,'_effect_dispatch_receipts',{}).values() if r['source_id']==MISTY.SOURCE])
                self.restored(e)

    def test_airborne_global_mist_is_not_affected_but_local_mist_treats_every_occupant_as_affected(self):
        e,a,t,second,outside = self.world()
        mist = e.r.move_mech('move/미스트필드')[0]['effects_exec'][0]
        FIELD.install(e,a,mist,'move/미스트필드')
        self.emit(e,a,t,second,hit=False)
        # These are observed existing airborne-state fields, not flight grants.
        t.airborne = True
        outside.airborne = True
        move = e.r.move(MISTY.SOURCE)
        self.assertFalse(FIELD.touches_ground(t))
        self.assertFalse(FIELD.touches_ground(outside))
        self.assertEqual(FIELD.terrain_for(e,t)['source_id'],MISTY.SOURCE)
        self.assertEqual(FIELD.terrain_for(e,outside)['source_id'],'move/미스트필드')
        self.assertTrue(MISTY.affected(e,t))
        self.assertFalse(MISTY.affected(e,outside))
        self.assertEqual(e.damage_base(t,move,target=outside),15)
        self.assertEqual(e.damage_base(outside,move,target=t),10)
        e = self.restored(e)
        t,outside = [WORLD.actor_index(e)[c.entity_id] for c in (t,outside)]
        self.assertTrue(MISTY.affected(e,t))
        self.assertFalse(MISTY.affected(e,outside))
        outside.airborne = False
        self.assertTrue(MISTY.affected(e,outside))
        self.assertEqual(e.damage_base(outside,e.r.move(MISTY.SOURCE),target=t),15)


if __name__ == '__main__':
    unittest.main()
