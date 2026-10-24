"""Actual attack completion, coin ownership and derived physical Hazard consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE/'engine'), str(ROOT/'engine')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import move_coins as COINS
import move_completion as COMPLETE
import hazard_state as HAZARDS
import effects_ext as EXT
import frequency as FREQ
import area_targets as AREA
import field_effects as FIELD


class MoveCoinsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset='core')

    def world(self, *, winner_trainer=False):
        e = Engine(self.r, seed=1211); e.grid = Grid(24, 24)
        a = Combatant(self.r, build_pokemon(self.r, '피카츄', 40,
            moves=['move/고양이돈받기','move/골드러시'], abilities=['정전기']))
        a.pos = (4,4)
        targets = [Combatant(self.r, build_pokemon(self.r, '꼬부기', 80,
            name='target'+str(n), moves=['move/몸통박치기'], abilities=['급류'], side='wild')) for n in range(2)]
        for n, target in enumerate(targets): target.pos = (5+n,4)
        actors = [a, *targets]
        winner = targets[0]
        if winner_trainer:
            winner = Combatant(self.r, build_trainer(self.r, 'winning-trainer', 20,
                dict(hp=30,atk=10,**{'def':10},spa=10,spd=10,spe=10), moves=[], extra={'money':100}))
            winner.pos = (18,18); actors.append(winner)
        for actor in actors: e.gm.add_combatant(actor)
        e.start_round(actors); e.start_of_turn(a, initiative_count=20)
        return e,a,targets,winner

    def attack(self,e,a,targets,mid,*,miss=False):
        with patch.object(e,'d20',return_value=1 if miss else 17):
            return e.use_move_on(a,targets[0],mid,e.everyone,aim=(5,4))

    def close(self,e,a):
        e.end_of_turn(a); e.end_encounter()

    def outcome(self,e,winner,*,trainer=False,identity='battle'):
        return e.gm.observe_encounter_outcome(encounter_id=identity, participants=e.everyone,
            winner=winner,trainer_battle=trainer,reason='observed actual winner')

    def restore(self,e):
        return Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))

    def test_both_coins_once_after_all_targets_and_gold_stage_once(self):
        for mid in COINS.MOVES:
            with self.subTest(move=mid):
                e,a,targets,_ = self.world(); seen=[]; original=e.roll_damage
                def capture(*args,**kwargs):
                    seen.append((a.stages['spa'],len(COINS.records(a))))
                    return original(*args,**kwargs)
                with patch.object(e,'roll_damage',side_effect=capture): self.attack(e,a,targets,mid)
                self.assertEqual(seen,[(0,0),(0,0)])
                row=COINS.records(a)[0]
                self.assertEqual(len(COINS.records(a)),1)
                self.assertEqual(row['amount'],40*row['face'])
                self.assertEqual(a.stages['spa'],-1 if mid=='move/골드러시' else 0)
                self.assertEqual(a.budget['standard'],0)
                rng=e.rng.getstate(); COMPLETE.refresh(e)
                self.assertEqual(rng,e.rng.getstate()); self.assertEqual(len(COINS.records(a)),1)
                self.assertTrue(self.restore(e).validate_state()['valid'])

    def test_actual_miss_scatter_and_daily_limit_survives_scene_and_save(self):
        e,a,targets,_=self.world(); self.attack(e,a,targets,'move/골드러시',miss=True)
        self.assertEqual(a.stages['spa'],-1); self.assertGreater(COINS.records(a)[0]['amount'],0)
        e.end_of_turn(a); e.end_scene(); e=self.restore(e)
        a=next(x for x in e.everyone if x.entity_id==a.entity_id)
        targets=[next(x for x in e.everyone if x.entity_id==t.entity_id) for t in targets]
        e.start_round(e.everyone); e.start_of_turn(a,initiative_count=20)
        self.attack(e,a,targets,'move/골드러시',miss=True)
        self.assertEqual(COINS.records(a)[1]['amount'],0); self.assertIsNone(COINS.records(a)[1]['face'])
        self.assertEqual(a.stages['spa'],-1)
        e.end_of_turn(a);e.end_scene();FREQ.new_day(a)
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        self.attack(e,a,targets,'move/골드러시',miss=True)
        self.assertGreater(COINS.records(a)[2]['amount'],0)
        self.assertEqual(COINS.records(a)[2]['day'],1)

    def test_trainer_winner_collects_both_sources_once_and_restore_retains_payment(self):
        e,a,targets,winner=self.world(winner_trainer=True)
        self.attack(e,a,targets,'move/고양이돈받기')
        e.end_of_turn(a);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        self.attack(e,a,targets,'move/골드러시')
        total=sum(row['amount'] for row in COINS.records(a))
        self.close(e,a);self.outcome(e,winner,trainer=True)
        receipt=e.gm.collect_move_coins(encounter_id='battle')
        self.assertEqual(receipt['amount'],total);self.assertEqual(winner.spec['money'],100+total)
        restored=self.restore(e)
        with self.assertRaises(ValueError):restored.gm.collect_move_coins(encounter_id='battle')
        with self.assertRaises(ValueError):self.outcome(e,winner,trainer=True,identity='renamed-same-battle')

    def test_non_trainer_winner_only_receives_pay_day_and_cannot_relabel_battle(self):
        e,a,targets,winner=self.world()
        self.attack(e,a,targets,'move/고양이돈받기')
        e.end_of_turn(a);e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        self.attack(e,a,targets,'move/골드러시')
        self.close(e,a); self.outcome(e,winner)
        receipt=e.gm.collect_move_coins(encounter_id='battle')
        self.assertEqual(receipt['amount'],COINS.records(a)[0]['amount'])
        self.assertIsNone(COINS.records(a)[1]['payment'])
        with self.assertRaises(ValueError):e.gm.collect_move_coins(encounter_id='battle')
        self.assertTrue(self.restore(e).validate_state()['valid'])

    def test_unobserved_or_other_encounter_cannot_claim_and_invalid_payment_is_atomic(self):
        e,a,targets,winner=self.world(winner_trainer=True)
        self.attack(e,a,targets,'move/고양이돈받기');self.close(e,a)
        with self.assertRaises(ValueError):e.gm.collect_move_coins(encounter_id='missing')
        self.outcome(e,winner,trainer=True)
        winner.spec['money']='invalid'; before=deepcopy(COINS.records(a))
        with self.assertRaises(ValueError):e.gm.collect_move_coins(encounter_id='battle')
        self.assertEqual(before,COINS.records(a));winner.spec['money']=100
        e.start_round(e.everyone);e.end_encounter();self.outcome(e,winner,trainer=True,identity='later')
        with self.assertRaises(ValueError):e.gm.collect_move_coins(encounter_id='later')
        e.gm.collect_move_coins(encounter_id='battle')
        self.assertTrue(self.restore(e).validate_state()['valid'])

    def test_source_change_and_fabricated_completion_fail_before_cost_or_randomness(self):
        e,a,targets,_=self.world();mid='move/고양이돈받기'
        before=deepcopy((a.budget,a.move_uses,e.rng.getstate()))
        with patch.dict(self.r.moves[mid],effect='changed source'):
            with self.assertRaises(ValueError):self.attack(e,a,targets,mid)
        self.assertEqual(before,(a.budget,a.move_uses,e.rng.getstate()))
        with self.assertRaises(ValueError):COINS.observe_completion(e,{'id':'invented','move_id':mid})
        self.assertFalse(COINS.records(a))

    def test_saved_coin_value_and_consumed_outcome_tampering_are_rejected(self):
        e,a,targets,winner=self.world(winner_trainer=True)
        self.attack(e,a,targets,'move/고양이돈받기');self.close(e,a);self.outcome(e,winner,trainer=True)
        row=COINS.records(a)[0];row['amount']+=1
        self.assertFalse(e.validate_state()['valid'])
        with self.assertRaises(ValueError):e.export_state()
        row['amount']-=1;e.gm.collect_move_coins(encounter_id='battle')
        row=COINS.records(a)[0];row['payment']['winner_id']=a.entity_id
        self.assertFalse(e.validate_state()['valid'])


class DerivedHazardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r=Rules(str(ROOT),ruleset='all')

    def world(self,mid):
        e=Engine(self.r,seed=1212);e.grid=Grid(24,24)
        species,base=('갈가부기','move/물대포') if mid=='move/거다이암진' else ('대왕끼리동','move/아이언헤드')
        a=Combatant(self.r,build_pokemon(self.r,species,50,moves=[base],abilities=[]))
        target=Combatant(self.r,build_pokemon(self.r,'꼬부기',80,moves=['move/몸통박치기'],abilities=['급류'],side='wild'))
        a.pos,target.pos=(4,4),(9,4)
        e.gm.add_combatant(a);e.gm.add_combatant(target)
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        e.enter_gigantamax(a,source_id='test/actual-gmax',reason='actual form')
        return e,a,target,base

    def use(self,e,a,t,base,mid,*,miss=False):
        with patch.object(e,'d20',return_value=1 if miss else 17):
            return e.use_gmax_move_on(a,t,base,mid,e.everyone,aim=(9,4))

    def test_both_native_areas_create_distinct_source_owned_traps_and_cleanup(self):
        for mid in HAZARDS.DERIVED_MOVES:
            with self.subTest(move=mid):
                e,a,t,base=self.world(mid);self.use(e,a,t,base,mid)
                completion=next(iter(e._move_completions.values()))
                area=AREA.cells(e,a,completion['move'])
                self.assertEqual(set(e.hazards),area)
                rows=[r for env in e.hazards.values() for r in env['instances']]
                self.assertEqual(len(rows),len(area));self.assertEqual({r['source_id'] for r in rows},{mid})
                self.assertEqual({r['region_id'] for r in rows},{completion['hazard_region_id']})
                self.assertEqual({r['owner_actor_id'] for r in rows},{a.entity_id})
                with self.assertRaises(ValueError):HAZARDS.install_from_completion(e,a,mid,completion['id'])
                restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
                self.assertEqual(set(restored.hazards),area)
                e.end_of_turn(a);e.end_encounter();self.assertFalse(e.hazards)

    def test_proximity_consumes_one_typed_trap_and_recall_restores_eligibility(self):
        for mid,kind,attack_type in [('move/거다이암진','stealth_rock','바위'),('move/거다이강철진','steelsurge','강철')]:
            with self.subTest(move=mid):
                e,a,t,base=self.world(mid);self.use(e,a,t,base,mid)
                count=len(e.hazards);hp=t.hp
                expected=int(e.tick(t)*e.type_multiplier(attack_type,t)[0])
                EXT.on_enter_cell(e,t,(9,4))
                self.assertEqual(hp-t.hp,expected);self.assertEqual(len(e.hazards),count-1)
                self.assertIn(kind,t.spec[HAZARDS.REENTRY])
                EXT.on_enter_cell(e,t,(9,5));self.assertEqual(len(e.hazards),count-1)
                HAZARDS.on_recall(t);EXT.on_enter_cell(e,t,(9,5));self.assertEqual(len(e.hazards),count-2)
                EXT.on_enter_cell(e,a,(9,5));self.assertEqual(len(e.hazards),count-2)

    def test_miss_has_no_trap_and_missing_map_or_aim_refuses_atomically(self):
        # Legacy test ID retained for evidence continuity; Spirit Surge does install the miss trap.
        for mid in HAZARDS.DERIVED_MOVES:
            with self.subTest(move=mid):
                e,a,t,base=self.world(mid)
                before=deepcopy((a.budget,a.move_uses,t.hp,e.rng.getstate()))
                with self.assertRaises(ValueError):e.use_gmax_move_on(a,t,base,mid,e.everyone)
                self.assertEqual(before,(a.budget,a.move_uses,t.hp,e.rng.getstate()))
                grid=e.grid;e.grid=None
                with self.assertRaises(ValueError):self.use(e,a,t,base,mid)
                self.assertEqual(before,(a.budget,a.move_uses,t.hp,e.rng.getstate()));e.grid=grid
                hp=t.hp
                self.use(e,a,t,base,mid,miss=True)
                completion=next(iter(e._move_completions.values()))
                self.assertFalse(any(row['hit'] for row in completion['results'].values()))
                self.assertLess(t.hp,hp)
                self.assertEqual(set(e.hazards),AREA.cells(e,a,completion['move']))
                self.assertEqual(len(e._gmax_payload_receipts),1)
                self.assertEqual(a.budget['standard'],0)
                self.assertTrue(e.validate_state()['valid'])

    def test_rock_and_steel_immunity_are_independent_and_court_change_keeps_identity(self):
        e,a,t,base=self.world('move/거다이암진');self.use(e,a,t,base,'move/거다이암진')
        copper=Combatant(self.r,build_pokemon(self.r,'대왕끼리동',50,moves=['move/아이언헤드'],abilities=[]))
        copper.pos=(4,5);e.gm.add_combatant(copper)
        e.end_of_turn(a);e.start_of_turn(copper,initiative_count=10)
        e.enter_gigantamax(copper,source_id='test/actual-gmax',reason='second actual form')
        self.use(e,copper,t,'move/아이언헤드','move/거다이강철진')
        rows=lambda:[row for env in e.hazards.values() for row in env['instances']]
        before=len(rows());EXT.on_enter_cell(e,t,(9,4))
        self.assertEqual(len(rows()),before-2)
        self.assertEqual(set(t.spec[HAZARDS.REENTRY]),{'stealth_rock','steelsurge'})
        identities={row['id']:(row['region_id'],row['owner_actor_id'],row['cell']) for row in rows()}
        HAZARDS.swap_sides(e,a)
        self.assertEqual(identities,{row['id']:(row['region_id'],row['owner_actor_id'],row['cell']) for row in rows()})
        self.assertTrue(all(row['owner_side']=='wild' for row in rows()))
        e.gm.snapshot('traps');HAZARDS.clear(e);e.gm.restore('traps')
        self.assertEqual(len(rows()),before-2)

    def test_gmax_gravity_reuses_field_consumers_with_enemy_only_move_ban(self):
        e=Engine(self.r,seed=1213);e.grid=Grid(30,30)
        a=Combatant(self.r,build_pokemon(self.r,'이올브',50,moves=['move/염동력'],abilities=[]))
        t=Combatant(self.r,build_pokemon(self.r,'구구',80,moves=['move/공중날기'],abilities=[],side='wild'))
        ally=Combatant(self.r,build_pokemon(self.r,'구구',80,moves=['move/공중날기'],abilities=[]))
        a.pos,t.pos,ally.pos=(4,4),(9,4),(20,20)
        for c in (a,t,ally):e.gm.add_combatant(c)
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        self.assertEqual(e.type_multiplier('땅',t)[0],0)
        e.enter_gigantamax(a,source_id='test/actual-gmax',reason='actual field producer')
        with patch.object(e,'d20',return_value=17):
            e.use_gmax_move_on(a,t,'move/염동력','move/거다이천도',e.everyone,aim=(9,4))
        self.assertEqual(FIELD.active(e,'왜곡')['source_id'],'move/거다이천도');self.assertEqual(FIELD.active(e,'왜곡')['rounds'],5)
        self.assertEqual(FIELD.accuracy_modifier(e,t),0)
        self.assertIsNone(FIELD.native_move_block_reason(e,'move/공중날기',ally))
        self.assertEqual(FIELD.native_move_block_reason(e,'move/공중날기',t),'move/거다이천도')
        self.assertGreater(e.type_multiplier('땅',t)[0],0)
        self.assertGreater(e.type_multiplier('땅',ally)[0],0)
        e.end_of_turn(a);e.start_of_turn(t,initiative_count=10)
        before=deepcopy((t.budget,t.move_uses,e.rng.getstate()))
        self.assertEqual(e.use_setup_move_on(t,a,'move/공중날기',e.everyone),0)
        self.assertEqual(before,(t.budget,t.move_uses,e.rng.getstate()))
        t.spec['_movement_altitude']=2
        with self.assertRaises(ValueError):e.end_of_turn(t)
        t.spec['_movement_altitude']=1;e.end_of_turn(t)
        e=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        for remaining in (4,3,2,1):
            e.start_round(e.everyone);self.assertEqual(FIELD.active(e,'왜곡')['rounds'],remaining)
        e.start_round(e.everyone);self.assertIsNone(FIELD.active(e,'왜곡'))
        rt=next(c for c in e.everyone if c.entity_id==t.entity_id)
        self.assertEqual(e.type_multiplier('땅',rt)[0],0)


if __name__=='__main__': unittest.main()
