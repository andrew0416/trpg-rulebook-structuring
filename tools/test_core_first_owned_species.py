"""C11-027: actual capture, birth and evolution consume one ownership history."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from contextlib import nullcontext
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import downtime as D,pokemon_party as PARTY,state_grants as G,world_entities as W
import state_codec as CODEC,trainer_entitlements as RIGHTS
import test_foundation_egg_creation as EGG_FIXTURE


class FirstOwnedSpeciesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,27)
        self.a=self.add(build_trainer(self.r,'species owner',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            skills={'명령':4},abilities=[],extra={'items':{'몬스터볼':10}}))

    def add(self,spec):
        actor=Combatant(self.r,spec)
        self.e.gm.add_combatant(actor,pos=(0,0),side='party',reason='actual species acquisition fixture')
        return actor

    def pokemon(self,species='잉어킹',level=20,owner=None):
        extra={'wild':owner is None}
        if owner is not None:extra['trainer_id']=owner.entity_id
        actor=self.add(build_pokemon(self.r,species,level,moves=[],abilities=[],extra=extra))
        if owner is None:actor.side='wild';actor.spec['side']='wild'
        return actor

    def catch(self,pokemon,trainer=None,**options):
        return self.e.throw_ball(trainer or self.a,pokemon,**dict(fixed_accuracy=20,fixed_capture=20,**options))

    def snap(self):return deepcopy(CODEC.dump_engine(self.e))

    def gift_egg(self):
        fixture=EGG_FIXTURE.EggTests();fixture.setUpClass();fixture.setUp()
        row=fixture.create()
        recipient=fixture.add(build_trainer(fixture.r,'actual egg recipient',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[]))
        fixture.e.gm.transfer_egg(fixture.a,recipient,row['entity_id'],reason='actual egg gift',request_id='species-gift')
        return fixture,recipient,row

    def hatch(self,fixture,recipient,row,**options):
        return fixture.e.hatch_declared_egg(recipient,row['entity_id'],**dict(
            name='actual newborn',ready=True,reason='observed actual birth',choices=fixture.choices(),**options))

    def test_preparation_is_read_only_and_preserves_the_actual_progression_owner_output(self):
        self.a.spec['exp_bank']=9;target=self.pokemon()
        PARTY.preflight_capture(self.e,self.a,target)  # Admit the selected sources before measuring read-only preparation.
        before=self.snap();plan=PARTY.preflight_capture(self.e,self.a,target)['first_species']
        self.assertEqual(self.snap(),before)
        staged=deepcopy(self.e,{id(self.r):self.r});actor=W.actor_index(staged)[self.a.entity_id]
        result=staged.award_trainer_progression(actor,kind='experience',amount=1,
            request_id='trainer/new-species/pokemon/잉어킹',reason='처음 소유한 종 pokemon/잉어킹')
        self.assertEqual(plan['result'],result)
        self.assertEqual(plan['progression_after'],{key:deepcopy(actor.spec[key]) for key in D._PROGRESSION_FIELDS if key in actor.spec})
        self.assertEqual((result['level_after'],result['bank_after'],result['attained_levels']),(6,0,[6]))

    def test_actual_capture_grants_one_xp_and_consumes_ten_bank_immediately_once(self):
        self.a.spec['exp_bank']=9;target=self.pokemon()
        self.assertTrue(self.catch(target));self.assertTrue(target.captured)
        self.assertEqual((self.a.level,self.a.spec['exp_bank']),(6,0))
        self.assertEqual(self.a.spec['caught_species'],['pokemon/잉어킹'])
        event=self.a.spec['trainer_progression_events']['trainer/new-species/pokemon/잉어킹']['result']
        self.assertEqual(event['entitlement_ids'],['ordinary/level/6'])
        self.assertEqual(event['skill_reward_levels'],[6]);self.assertEqual(event['stat_reward_levels'],[6])
        self.assertTrue(self.catch(self.pokemon()))
        self.assertEqual((self.a.level,self.a.spec['exp_bank'],len(self.a.spec['trainer_progression_events'])),(6,0,1))

    def test_existing_current_historical_and_reserve_species_normalize_aliases_without_retroactive_xp(self):
        for origin in ('live','history','reserve'):
            with self.subTest(origin=origin):
                self.setUp()
                if origin=='live':self.pokemon(owner=self.a)
                elif origin=='history':self.a.spec['caught_species']=['잉어킹','Magikarp','pokemon/잉어킹']
                else:
                    PARTY.configure(self.e,self.a,mode='standard',reason='established initial party',roster=[],storage={'kind':'center','id':'reserve-center'})
                    PARTY.register_reserve(self.e,self.a,pokemon_id='reserve/fish',species='Magikarp',location='storage',reason='established prior ownership')
                target=self.pokemon();target.spec['species']='Magikarp'
                self.assertTrue(self.catch(target));self.assertEqual(target.spec['species'],'pokemon/잉어킹')
                self.assertEqual((self.a.level,self.a.spec.get('exp_bank',0)),(5,0))
                self.assertEqual(self.a.spec['caught_species'],['pokemon/잉어킹'])
                self.assertFalse(self.a.spec.get('trainer_progression_events'))

    def test_actual_hatch_grants_only_the_recipient_first_species_and_retry_cannot_repeat(self):
        fixture,recipient,row=self.gift_egg();recipient.spec['exp_bank']=9
        child=self.hatch(fixture,recipient,row)['pokemon']
        self.assertEqual(child.spec['trainer_id'],recipient.entity_id)
        self.assertEqual((recipient.level,recipient.spec['exp_bank']),(6,0))
        self.assertEqual(recipient.spec['caught_species'],['pokemon/이상해씨'])
        self.assertEqual(fixture.a.spec.get('exp_bank',0),0)
        before=CODEC.dump_engine(fixture.e)
        with self.assertRaises(ValueError):self.hatch(fixture,recipient,row)
        self.assertEqual(CODEC.dump_engine(fixture.e),before)

    def test_actual_hatch_of_an_initial_owned_species_only_records_history(self):
        fixture=EGG_FIXTURE.EggTests();fixture.setUpClass();fixture.setUp();row=fixture.create()
        fixture.hatch(row)
        self.assertEqual(fixture.a.spec['caught_species'],['pokemon/이상해씨'])
        self.assertEqual(fixture.a.spec.get('exp_bank',0),0)
        self.assertFalse(fixture.a.spec.get('trainer_progression_events'))

    def test_actual_evolution_remembers_both_forms_and_trainers_are_independent(self):
        fish=self.pokemon(owner=self.a);self.a.spec['exp_bank']=9
        self.assertTrue(D.evolve_combatant(self.e,fish,'갸라도스')['evolved'])
        self.assertEqual((self.a.level,self.a.spec['exp_bank']),(6,0))
        self.assertEqual(set(self.a.spec['caught_species']),{'pokemon/잉어킹','pokemon/갸라도스'})
        before=self.snap();self.assertFalse(D.evolve_combatant(self.e,fish,'갸라도스')['evolved']);self.assertEqual(self.snap(),before)
        other=self.add(build_trainer(self.r,'independent trainer',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[]))
        second=self.pokemon(owner=other)
        self.assertTrue(D.evolve_combatant(self.e,second,'갸라도스')['evolved'])
        self.assertEqual(other.spec['exp_bank'],1)
        self.assertTrue(D.evolve_combatant(self.e,self.pokemon(owner=self.a),'갸라도스')['evolved'])
        self.assertEqual(self.a.spec['exp_bank'],0)

    def test_failure_miss_and_non_evolution_do_not_claim_species_or_experience(self):
        for options in ({'fixed_accuracy':1},{'fixed_capture':1}):
            with self.subTest(options=options):
                self.setUp();target=self.pokemon()
                self.assertFalse(self.e.throw_ball(self.a,target,**dict({'fixed_accuracy':20,'fixed_capture':20},**options)))
                self.assertFalse(self.a.spec.get('caught_species'));self.assertFalse(self.a.spec.get('trainer_progression_events'))
                self.assertFalse(target.captured);self.assertEqual(self.a.spec.get('exp_bank',0),0)
        self.setUp();fish=self.pokemon(level=1,owner=self.a);before=self.snap()
        self.assertFalse(D.evolve_combatant(self.e,fish,'갸라도스')['evolved']);self.assertEqual(self.snap(),before)
        fixture,recipient,row=self.gift_egg();before=CODEC.dump_engine(fixture.e)
        with self.assertRaises(ValueError):fixture.e.hatch_declared_egg(recipient,row['entity_id'],name='not ready',ready=False,reason='not ready',choices=fixture.choices())
        self.assertEqual(CODEC.dump_engine(fixture.e),before)
        self.hatch(fixture,recipient,row);self.assertEqual(recipient.spec['exp_bank'],1)

    def test_new_progression_failures_reject_capture_before_cost_and_retry_keeps_first_award(self):
        target=self.pokemon();PARTY.preflight_capture(self.e,self.a,target)
        before=self.snap()
        with patch.object(RIGHTS,'issue',side_effect=ValueError('late progression rejection')):
            with self.assertRaisesRegex(ValueError,'late progression rejection'):self.catch(target)
        self.assertEqual(self.snap(),before)
        self.assertTrue(self.catch(target));self.assertEqual(self.a.spec['exp_bank'],1)

    def test_late_growth_failure_in_hatch_and_evolution_preserves_actual_producer_state(self):
        fish=self.pokemon(owner=self.a);before=self.snap()
        with patch.object(RIGHTS,'issue',side_effect=ValueError('late growth')):
            with self.assertRaisesRegex(ValueError,'late growth'):D.evolve_combatant(self.e,fish,'갸라도스')
        self.assertEqual(self.snap(),before)
        self.assertTrue(D.evolve_combatant(self.e,fish,'갸라도스')['evolved']);self.assertEqual(self.a.spec['exp_bank'],1)
        fixture,recipient,row=self.gift_egg();before=CODEC.dump_engine(fixture.e)
        with patch.object(RIGHTS,'issue',side_effect=ValueError('late growth')):
            with self.assertRaisesRegex(ValueError,'late growth'):self.hatch(fixture,recipient,row)
        self.assertEqual(CODEC.dump_engine(fixture.e),before)
        self.hatch(fixture,recipient,row);self.assertEqual(recipient.spec['exp_bank'],1)

    def test_invalid_bank_history_reward_and_selected_policy_reject_without_new_capture_effects(self):
        for corruption in ('bank','history','reward','policy','source'):
            with self.subTest(corruption=corruption):
                self.setUp();target=self.pokemon();PARTY.preflight_capture(self.e,self.a,target)
                if corruption=='bank':self.a.spec['exp_bank']=-1
                elif corruption=='history':self.a.spec['caught_species']=['missing species']
                elif corruption=='reward':self.a.spec['trainer_milestone_rewards']={}
                # Invalid imported state cannot be exported; compare actual native fields directly.
                before=deepcopy((self.a.spec,target.spec,target.captured,self.e.rng.getstate(),self.e.log_lines))
                original=self.r.mech
                def mech(key):
                    value=original(key)
                    return dict(value,new_species_exp=2) if key=='trainer/experience' else value
                context=patch.object(self.r,'mech',side_effect=mech) if corruption=='policy' else nullcontext()
                if corruption=='source':
                    import source_context
                    verified=source_context.verified_source
                    def source(rules,reference,**kwargs):
                        if reference==D._FIRST_SPECIES_SOURCE:raise ValueError('changed species source')
                        return verified(rules,reference,**kwargs)
                    context=patch.object(source_context,'verified_source',side_effect=source)
                with context,self.assertRaises((ValueError,KeyError)):self.catch(target)
                self.assertEqual(deepcopy((self.a.spec,target.spec,target.captured,self.e.rng.getstate(),self.e.log_lines)),before)

    def test_transfer_and_reacquisition_preserve_history_without_trade_experience(self):
        fish=self.pokemon(owner=self.a)
        other=self.add(build_trainer(self.r,'new actual owner',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[],extra={'items':{'몬스터볼':1}}))
        for trainer,roster in ((self.a,[fish]),(other,[])):
            PARTY.configure(self.e,trainer,mode='standard',reason='established initial roster',roster=roster,storage={'kind':'center','id':'actual-center'})
        PARTY.transfer(self.e,self.a,target=fish,new_owner=other,reason='actual transfer',request_id='first-species-transfer')
        for trainer in (self.a,other):
            self.assertEqual(trainer.spec['caught_species'],['pokemon/잉어킹'])
            self.assertFalse(trainer.spec.get('trainer_progression_events'))
        self.assertTrue(self.catch(self.pokemon()));self.assertEqual(self.a.spec.get('exp_bank',0),0)
        self.assertTrue(self.catch(self.pokemon(),trainer=other));self.assertEqual(other.spec.get('exp_bank',0),0)

    def test_snapshot_json_and_history_restore_preserve_one_capture_award(self):
        self.a.spec['exp_bank']=9;self.assertTrue(self.catch(self.pokemon()))
        snapshot=self.e.gm.snapshot()
        self.assertTrue(self.catch(self.pokemon()));self.assertEqual((self.a.level,self.a.spec['exp_bank']),(6,0))
        self.e.gm.restore(snapshot)
        self.a=W.actor_index(self.e)[self.a.entity_id]
        self.assertEqual((self.a.level,self.a.spec['exp_bank']),(6,0))
        restored=CODEC.load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        self.e=restored;self.r=restored.r;self.a=W.actor_index(restored)[self.a.entity_id]
        self.assertTrue(self.catch(self.pokemon()));self.assertEqual(self.a.spec['exp_bank'],0)

    def test_stale_prepared_growth_rejects_before_history_or_placement_commit(self):
        target=self.pokemon();plan=PARTY.preflight_capture(self.e,self.a,target)
        self.a.spec['exp_bank']=2;target.captured=True;target.spec['trainer_id']=self.a.entity_id
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'progression changed'):PARTY.finish_capture(self.e,self.a,target,plan)
        self.assertEqual(self.snap(),before);self.assertFalse(self.a.spec.get('caught_species'))


if __name__=='__main__':unittest.main()
