"""Q44/C10-121: actual source choice, observed rest work and native revival."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon
from engine import Combatant,Engine,Rules
import actor_templates as T
import downtime as D
from native_scenario_fixture import assert_rejected_unchanged


class SoullessRestSourceRevisionTests(unittest.TestCase):
    def world(self,*,ruleset='core'):
        r=Rules(str(ROOT),ruleset=ruleset);e=Engine(r,seed=44121)
        c=Combatant(r,build_pokemon(r,'껍질몬',30,moves=[],wild=True))
        e.gm.add_combatant(c,reason='actual catalog Soulless rest subject')
        e.take_damage(c,100)
        self.assertLess(c.hp,0)
        self.assertEqual((c.max_hp,c.injuries,c.temp_hp,c.dead),(1,0,0,False))
        return e,c

    def choice(self,c,variant):
        pending=T.soulless_rest_choices(c)
        self.assertEqual(pending['status'],'PolicyInputsRequired')
        self.assertEqual(pending['obligations'][0]['decision_kind'],'source_conflict')
        return {'value':variant,'reason':'GM explicitly adopts this complete Soulless timing definition',
                'scope':pending['decision_scope']}

    def choose_english(self,e,c):
        choice=self.choice(c,'english_extended_rest')
        T.select_soulless_rest(e,c,choice)
        return choice

    def task(self,e,c,identity,minutes=3):
        return T.observe_soulless_rest_task(e,c,rest_id=identity,minutes=minutes,
            reason='GM establishes this current multi-minute Extended Action spent resting')

    def test_korean_default_requires_actual_observed_task_completion_and_cannot_replay_it(self):
        e,c=self.world();hp=c.hp
        self.assertNotIn(T.SOULLESS_REST_CHOICE,c.spec)
        D.rest(e,c,0)
        D.rest(e,c,3,rest_id='unobserved-three-minutes')
        self.assertEqual(c.hp,hp)
        self.assertTrue(c.fainted)
        row=self.task(e,c,'actual-three-minute-task')
        self.assertEqual((row['start'],row['minutes'],row['status']),(180,3,'pending'))
        D.rest(e,c,2,rest_id=row['rest_id'])
        self.assertEqual((c.hp,e.elapsed_seconds),(hp,300))
        D.rest(e,c,1,rest_id=row['rest_id'])
        self.assertEqual((c.hp,c.fainted,e.elapsed_seconds),(1,False,360))
        completed=deepcopy(c.spec[T.SOULLESS_REST_TASKS][row['rest_id']])
        self.assertEqual((completed['status'],completed['finished_at']),('complete',360))
        e.take_damage(c,100);hp=c.hp
        D.rest(e,c,3,rest_id='different-future-rest')
        self.assertEqual(c.hp,hp)
        self.assertEqual(c.spec[T.SOULLESS_REST_TASKS][row['rest_id']],completed)
        assert_rejected_unchanged(e,lambda:self.task(e,c,row['rest_id']),reason_pattern='already used')
        other=self.task(e,c,'actual-seven-minute-task',7)
        D.rest(e,c,6,rest_id=other['rest_id']);self.assertEqual(c.hp,hp)
        D.rest(e,c,1,rest_id=other['rest_id']);self.assertEqual(c.hp,1)
        self.assertEqual(c.spec[T.SOULLESS_REST_TASKS][other['rest_id']]['minutes'],7)

    def test_english_uses_real_239_plus_one_continuous_group_rest_and_not_interrupted_bouts(self):
        e,c=self.world();self.choose_english(e,c);hp=c.hp
        ordinary=Combatant(e.r,build_pokemon(e.r,'꼬렛',30,moves=[],wild=True))
        e.gm.add_combatant(ordinary,reason='ordinary resting control')
        e.take_damage(ordinary,10);ordinary_hp=ordinary.hp
        e.gm.observe_activity([c,ordinary],239,qualifies_as_rest=True,
            reason='actual uninterrupted resting activity',rest_id='english-four-hour-bout')
        self.assertEqual((c.hp,c.fainted),(hp,True))
        self.assertGreater(ordinary.hp,ordinary_hp)
        e.gm.observe_activity([c,ordinary],1,qualifies_as_rest=True,
            reason='actual final continuous minute',rest_id='english-four-hour-bout')
        self.assertEqual((c.hp,c.fainted,e.elapsed_seconds),(1,False,14400))
        e.take_damage(c,100);hp=c.hp
        D.rest(e,c,239,rest_id='interrupted-bout')
        e.gm.observe_activity([c],1,qualifies_as_rest=False,
            reason='actual physical activity breaks rest continuity')
        D.rest(e,c,1,rest_id='interrupted-bout')
        self.assertEqual((c.hp,c.fainted),(hp,True))
        D.rest(e,c,239,rest_id='separate-bout')
        self.assertEqual(c.hp,hp)
        D.extended_rest(e,c,4,rest_id='actual-new-four-hour-rest')
        self.assertEqual((c.hp,c.fainted),(1,False))
        self.assertNotIn(T.SOULLESS_REST_TASKS,c.spec)

    def test_current_scope_registered_actor_and_actual_task_observation_are_required_atomically(self):
        e,c=self.world()
        assert_rejected_unchanged(e,lambda:T.select_soulless_rest(e,c,'english_extended_rest'),
            reason_pattern='actual scoped source decision required')
        stale=self.choice(c,'english_extended_rest');stale['scope']='not-the-current-source-scope'
        assert_rejected_unchanged(e,lambda:T.select_soulless_rest(e,c,stale),reason_pattern='scope changed')
        unknown=self.choice(c,'english_extended_rest');unknown['value']='imaginary_timing'
        assert_rejected_unchanged(e,lambda:T.select_soulless_rest(e,c,unknown),reason_pattern='invalid policy input')
        unregistered=Combatant(e.r,build_pokemon(e.r,'껍질몬',30,moves=[],wild=True))
        assert_rejected_unchanged(e,lambda:self.task(e,unregistered,'unregistered-task'),reason_pattern='registered Soulless')
        assert_rejected_unchanged(e,lambda:self.task(e,c,'not-multi-minute',1),reason_pattern='multi-minute rest task')
        row=self.task(e,c,'current-task');D.rest(e,c,1,rest_id=row['rest_id'])
        e.advance_time(60,[c])
        assert_rejected_unchanged(e,lambda:D.rest(e,c,2,rest_id=row['rest_id']),reason_pattern='adjacent time')
        D.rest(e,c,2,rest_id='new-independent-rest')
        self.assertEqual(c.spec[T.SOULLESS_REST_TASKS][row['rest_id']]['status'],'interrupted')
        self.assertTrue(c.fainted)
        e.start_round(e.everyone)
        assert_rejected_unchanged(e,lambda:self.task(e,c,'task-in-combat'),reason_pattern='active encounter')
        e.end_encounter(round_elapsed_seconds=0)
        before=e.export_state();original=deepcopy(e.r.ruleset.variant_choices)
        try:
            e.r.ruleset.variant_choices[T.SOULLESS]='capability/unreviewed-soulless'
            with self.assertRaises(ValueError):self.task(e,c,'replaced-source-task')
        finally:e.r.ruleset.variant_choices=original
        self.assertEqual(e.export_state(),before)

    def test_pending_actual_task_and_english_boundary_survive_gm_and_fresh_rules_json(self):
        for variant,minutes in (('korean_extended_action',2),('english_extended_rest',239)):
            with self.subTest(variant=variant):
                e,c=self.world();hp=c.hp
                if variant=='english_extended_rest':self.choose_english(e,c)
                else:self.task(e,c,'saved-native-bout')
                D.rest(e,c,minutes,rest_id='saved-native-bout')
                self.assertEqual(c.hp,hp)
                record=deepcopy(c.spec['rest_interval'])
                task=deepcopy(c.spec.get(T.SOULLESS_REST_TASKS))
                choice=deepcopy(c.spec.get(T.SOULLESS_REST_CHOICE))
                e.gm.snapshot('before-source-boundary')
                payload=json.loads(json.dumps(e.export_state()))
                loaded=Engine.import_state(Rules(str(ROOT),ruleset='core'),payload)
                q=next(a for a in loaded.everyone if a.entity_id==c.entity_id)
                self.assertEqual((q.spec['rest_interval'],q.spec.get(T.SOULLESS_REST_TASKS),
                    q.spec.get(T.SOULLESS_REST_CHOICE)),(record,task,choice))
                D.rest(loaded,q,1,rest_id='saved-native-bout')
                self.assertEqual((q.hp,q.fainted,q.injuries,q.temp_hp,q.dead),(1,False,0,0,False))
                D.rest(e,c,1,rest_id='saved-native-bout');self.assertEqual(c.hp,1)
                e.gm.restore('before-source-boundary')
                self.assertEqual((c.hp,c.spec['rest_interval']),(hp,record))
                D.rest(e,c,1,rest_id='saved-native-bout')
                self.assertEqual((c.hp,c.fainted),(1,False))

    def test_actual_kaladanda_damage_producer_blocks_both_source_timing_recoveries(self):
        from test_category2_optional_catalog_nine import OptionalCatalogNineTests
        import optional_physical_equipment as OPTIONAL
        import weapon_actions as WEAPONS
        fixture=OptionalCatalogNineTests('runTest');fixture.r=Rules(str(ROOT),ruleset='all')
        e,a,_,_=fixture.fixture()
        c=Combatant(e.r,build_pokemon(e.r,'껍질몬',30,moves=[],wild=True))
        e.gm.add_combatant(c,pos=(3,3),reason='actual Soulless target of equipped Kaladanda')
        uid=fixture.equip(e,a,'crafted_item/카라단다','soulless-native-kaladanda')
        move=WEAPONS.prepare(e,a,e.r.move('move/섀도클로'),uid)
        observed={};e.resolve_attack_damage(a,c,move,_damage_observation=observed)
        self.assertGreater(observed['net_hp_loss'],0)
        self.assertTrue(c.fainted)
        self.assertEqual(c.custom_conditions[OPTIONAL.NO_AWAKENING]['move_id'],'move/섀도클로')
        hp=c.hp;self.task(e,c,'blocked-korean-task')
        D.rest(e,c,3,rest_id='blocked-korean-task')
        self.assertEqual((c.hp,c.fainted),(hp,True))
        self.assertEqual(c.spec[T.SOULLESS_REST_TASKS]['blocked-korean-task']['status'],'complete')
        self.choose_english(e,c)
        D.extended_rest(e,c,4,rest_id='blocked-english-bout')
        self.assertEqual((c.hp,c.fainted,c.injuries,c.temp_hp,c.dead),(hp,True,0,0,False))
        loaded=Engine.import_state(Rules(str(ROOT),ruleset='all'),json.loads(json.dumps(e.export_state())))
        q=next(actor for actor in loaded.everyone if actor.entity_id==c.entity_id)
        self.assertTrue(OPTIONAL.awakening_blocked(loaded,q))
        self.assertFalse(loaded.revive(q,1))
        self.assertEqual((q.hp,q.fainted),(hp,True))


if __name__=='__main__':unittest.main()
