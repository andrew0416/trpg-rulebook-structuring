"""Audit F41/F42/F43: native actors, timed activities and actual capture attempts."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from builder import build_pokemon
from engine import Engine, Combatant
import csv_item_capability_contracts as CAP
import species_classification as CLASSIFICATION
import world_entities as WORLD
import native_scenario_fixture as NATIVE
import test_category2_csv_remaining_item_contracts as fixtures


class AuditItemBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon = fixtures.RemainingCsvItemContractTests.pokemon
    trainer = fixtures.RemainingCsvItemContractTests.trainer
    fixture = fixtures.RemainingCsvItemContractTests.fixture

    def restore(self, e):
        restored = Engine.import_state(self.r, json.loads(json.dumps(e.export_state())))
        self.assertTrue(restored.validate_state()['valid'])
        return restored

    def test_csv_unown_rejects_actual_trainer_and_level19_before_any_cost(self):
        for kind in ('trainer','level19'):
            actor = (self.trainer('csv-trainer',capabilities=('안농모으기',)) if kind=='trainer'
                     else self.pokemon('csv-level19',level=19,capabilities=('안농모으기',)))
            u = self.pokemon('new-unown-'+kind,species='안농',level=15)
            e = self.fixture(actor)
            e.start_round([actor]); e.start_of_turn(actor,initiative_count=20)
            NATIVE.assert_rejected_unchanged(e,lambda:CAP.gather_unown(e,actor,u,occult_total=16),
                reason_pattern='level 20 user')
            self.assertNotIn(u,e.everyone)

    def test_csv_unown_level20_four_sessions_restored_and_new_native_turn(self):
        actor=self.pokemon('csv-level20',level=20,capabilities=('안농모으기',))
        u=self.pokemon('csv-first',species='안농',level=15)
        e=self.fixture(actor);e.session_frequency=True;e.defer_session_refresh=False;e.begin_session('csv:first',[actor])
        e.start_round([actor]);e.start_of_turn(actor,initiative_count=20)
        self.assertTrue(CAP.gather_unown(e,actor,u,occult_total=16)['summoned'])
        self.assertEqual(actor.budget['standard'],0)
        e.end_of_turn(actor);e.end_encounter(round_elapsed_seconds=0)
        e=self.restore(e);actor=WORLD.actor_index(e)[actor.entity_id]
        candidate=Combatant(e.r,build_pokemon(e.r,'안농',15,name='csv-second',abilities=[]))
        candidate.side='wild'
        for n in range(1,4):
            e.begin_session('csv:next:'+str(n),[actor])
            NATIVE.assert_rejected_unchanged(e,lambda:CAP.gather_unown(e,actor,candidate,occult_total=16),
                reason_pattern='four-session')
        e.begin_session('csv:fourth',[actor])
        e.start_round([actor]);e.start_of_turn(actor,initiative_count=20)
        self.assertTrue(CAP.gather_unown(e,actor,candidate,occult_total=15)['summoned'])
        self.assertEqual(actor.budget['standard'],0)
        self.assertNotEqual(candidate.side,actor.side)
        self.restore(e)

    def scavenger(self):
        actor=self.pokemon('scavenger',capabilities=('청소부',))
        return self.fixture(actor),actor

    def test_scavenger_both_combat_claims_and_unproved_noncombat_reject_unchanged(self):
        e,a=self.scavenger();e.start_round([a]);e.start_of_turn(a,initiative_count=20)
        # Native actions exhaust the budget; the encounter gate must still win.
        import turn as TURN
        for kind in ('standard','shift','swift'):self.assertTrue(TURN.spend(e,a,kind,'actual preceding action'))
        NATIVE.assert_rejections_unchanged(e,[lambda mode=mode:e.scavenge(a,during=mode,
            duration_minutes=240,duration_reason='cannot replace combat with a string',rest_id='rest' if mode=='extended_rest' else None)
            for mode in ('extended_action','extended_rest')],reason_pattern='noncombat')
        e.end_of_turn(a);e.end_encounter(round_elapsed_seconds=0)
        NATIVE.assert_rejections_unchanged(e,[
            lambda:e.scavenge(a),
            lambda:e.scavenge(a,duration_minutes=5,duration_reason=''),
            lambda:e.scavenge(a,during='extended_rest',duration_minutes=239,duration_reason='too short',rest_id='short')],
            reason_pattern=['activity minutes','duration reason','actual Extended Rest'])

    def test_scavenger_extended_job_time_reward_daily_and_both_restores(self):
        e,a=self.scavenger();start=e.elapsed_seconds
        out=e.scavenge(a,fixed_d20=20,duration_minutes=5,duration_reason='observed five-minute search')
        self.assertEqual(e.elapsed_seconds-start,300)
        self.assertEqual(a.spec['items']['item/이상한사탕'],1)
        import activity_jobs as JOBS
        status=JOBS.status(e,out['activity']['job_id'])
        self.assertEqual((status['status'],status['worked_seconds']),('complete',300))
        e=self.restore(e);a=WORLD.actor_index(e)[a.entity_id]
        NATIVE.assert_rejected_unchanged(e,lambda:e.scavenge(a,duration_minutes=5,
            duration_reason='duplicate search'),reason_pattern='daily use')
        snapshot=e.gm.snapshot();e.gm.restore(snapshot)
        self.assertEqual(a.spec['items']['item/이상한사탕'],1)
        import downtime as DT
        DT.new_day(a)
        e.scavenge(a,fixed_d20=1,duration_minutes=5,duration_reason='next observed day search')
        self.assertEqual(a.spec['items']['item/상처약'],1)
        a.spec['capabilities']=[]
        NATIVE.assert_rejected_unchanged(e,lambda:e.scavenge(a,duration_minutes=5,
            duration_reason='lost live capability'),reason_pattern='actual capability')

    def test_scavenger_real_extended_rest_retains_actual_activity_and_daily_limit(self):
        e,a=self.scavenger();start=e.elapsed_seconds
        out=e.scavenge(a,during='extended_rest',fixed_d20=1,duration_minutes=240,
            duration_reason='GM observed uninterrupted sleep and search',rest_id='overnight')
        self.assertEqual(e.elapsed_seconds-start,14400)
        self.assertEqual(a.spec['rest_interval']['total_minutes'],240)
        self.assertTrue(out['activity']['qualifies_as_rest'])
        self.assertEqual(a.spec['items']['item/상처약'],1)
        e=self.restore(e);a=WORLD.actor_index(e)[a.entity_id]
        NATIVE.assert_rejected_unchanged(e,lambda:e.scavenge(a,during='extended_rest',duration_minutes=240,
            duration_reason='same day repeated',rest_id='second'),reason_pattern='daily use')

    def test_scavenger_late_roll_failure_rolls_back_time_payment_reward_and_rng(self):
        for during in ('extended_action','extended_rest'):
            e,a=self.scavenger()
            with patch.object(CAP.POOLS,'die',side_effect=ValueError('observed late pickup failure')):
                NATIVE.assert_rejected_unchanged(e,lambda:e.scavenge(a,during=during,
                    duration_minutes=240 if during=='extended_rest' else 5,
                    duration_reason='actual activity before failed reward',rest_id='failed' if during=='extended_rest' else None),
                    reason_pattern='late pickup failure')
            self.assertNotIn(CAP.STATE,a.spec)
        import effects as FX
        for during in ('extended_action','extended_rest'):
            e,a=self.scavenger()
            effect={'type':'stage_change','stat':'atk','delta':1,'repeat':{'seconds':5,'times':1},
                    'if':'target was asleep'}
            self.assertEqual(FX.run_effects(e,a,a,[effect],{'hit':True,'target_was_asleep':True},
                'external/scavenger-clock'),(1,0))
            NATIVE.assert_rejected_unchanged(e,lambda:e.scavenge(a,during=during,
                duration_minutes=240 if during=='extended_rest' else 5,duration_reason='actual unresolved timer',
                rest_id='pending-rest' if during=='extended_rest' else None),reason_pattern='pending repeat requires a resumable clock invocation')

    def throw(self,species,*,ball='울트라볼',declare=None,marker=None,restore_before=False):
        t=self.trainer('capture-trainer',items={ball:1})
        target=Combatant(self.r,build_pokemon(self.r,species,30,moves=['move/몸통박치기'],abilities=[],wild=True))
        e=self.fixture(t,target)
        if marker is not None:target.spec['ultra_beast']=marker
        if declare is not None:CLASSIFICATION.declare(e,target,declare,source='GM homebrew species',reason='explicit observed taxonomy')
        if restore_before:
            e=self.restore(e);idx=WORLD.actor_index(e);t,target=idx[t.entity_id],idx[target.entity_id]
        e.start_round([t,target]);e.start_of_turn(t,initiative_count=20)
        e.throw_ball(t,target,ball,fixed_accuracy=20,fixed_capture=1)
        attempt=deepcopy(t.spec['capture_attempts']['capture-1'])
        e=self.restore(e);actual=WORLD.actor_index(e)[t.entity_id]
        self.assertEqual(actual.spec['capture_attempts']['capture-1'],attempt)
        return attempt['resolution']['modifiers']['ball']

    def test_ultra_ball_canonical_species_producer_multiple_ub_and_normal_controls(self):
        for species in ('텅비드','매시붕','베베놈','두파팡'):
            with self.subTest(species=species):
                self.assertTrue(build_pokemon(self.r,species,30,abilities=[])[CLASSIFICATION.KEY]['ultra_beast'])
                self.assertEqual(self.throw(species),0)
        self.assertEqual(self.throw('이상해씨',marker='truthy'),-4)
        self.assertEqual(self.throw('피카츄'),-4)

    def test_ultra_ball_explicit_gm_override_json_restore_and_other_ball(self):
        self.assertEqual(self.throw('이상해씨',declare=True,restore_before=True),0)
        self.assertEqual(self.throw('텅비드',declare=False,restore_before=True),-4)
        self.assertEqual(self.throw('텅비드',restore_before=True),0)
        self.assertEqual(self.throw('텅비드',ball='몬스터볼'),0)

    def test_species_classification_invalid_gm_claim_rejects_before_native_mutation(self):
        a=self.pokemon('taxonomy');e=self.fixture(a)
        NATIVE.assert_rejections_unchanged(e,[
            lambda:CLASSIFICATION.declare(e,a,'yes',source='GM',reason='not a bool'),
            lambda:CLASSIFICATION.declare(e,a,True,source='',reason='missing source'),
            lambda:CLASSIFICATION.declare(e,a,True,source='GM',reason='')],
            reason_pattern='explicit species-bound GM')
        CLASSIFICATION.declare(e,a,True,source='GM homebrew',reason='explicit species taxonomy')
        with self.assertRaisesRegex(ValueError,'species-bound'):
            CLASSIFICATION.classification(e.r,{**a.spec,'species':'pokemon/매시붕'})
        projected=build_pokemon(e.r,'피카츄',30,abilities=[])
        self.assertTrue(CLASSIFICATION.classification(e.r,{**projected,'species':'pokemon/매시붕'})['ultra_beast'])


if __name__=='__main__':unittest.main()
