"""Mixed native reactions retain only their actual original Bug-hit authority.

Acceptance tests for disruption-window-proposal01, not an executed certification.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import action_points as AP
import action_resources as RESOURCES
import class_actor_state_reactions as REACTIONS
import combat_timing as TIME
import common_checks as CHECKS
import frequency as FREQUENCY
import jump_actions as JUMP
import move_completion as COMPLETE
import skill_maneuver_actions as MANEUVERS
import trainer_feature_acquisition as ACQUIRE
import trickster as TRICKSTER
import tumbler as TUMBLER
import turn as TURN
import type_ace as ACE
import test_book_type_ace_acquisition as ACQ_FIX
import test_book_type_ace_reactions as ACE_FIX


class DisruptionMixedReactionTests(unittest.TestCase):
    setup=ACQ_FIX.TypeAceAcquisitionTests.setup
    add=ACQ_FIX.TypeAceAcquisitionTests.add
    acquire=ACQ_FIX.TypeAceAcquisitionTests.acquire
    combat=ACQ_FIX.TypeAceAcquisitionTests.combat
    family=ACE_FIX.TypeAceReactionTests.family
    known=ACE_FIX.TypeAceReactionTests.known
    native=ACE_FIX.TypeAceReactionTests.native
    completed=ACE_FIX.TypeAceReactionTests.completed
    valid=ACQ_FIX.TypeAceAcquisitionTests.valid

    def setUp(self):
        self.rules=Rules(ROOT,ruleset='core')
        self.setup()

    def restore(self):
        ACQ_FIX.TypeAceAcquisitionTests.restore(self)
        self.assertIs(self.e.rulings,self.e.r.rulings)

    def grass_defender(self):
        self.family('벌레','Insectoid Utility','Disruption Order')
        skill=ACE.SKILLS['풀'][0]
        self.u=self.add('actual defending Grass Ace','trainer',(7,5),side='foe',
            classes=[],feats=[],exp_bank=100,type_link_skills={'풀':skill})
        self.e.gm.set_skill(self.u,skill,6,reason='actual Master Grass-linked skill')
        self.v=self.add('actual Grass defender','pokemon',(4,3),side='foe',
            trainer_id=self.u.entity_id,types=['풀'],tutor_points=8)
        self.w=self.add('actual second Grass partner','pokemon',(5,3),side='foe',
            trainer_id=self.u.entity_id,types=['풀'],tutor_points=8)
        for pokemon in (self.v,self.w):
            self.e.gm.observe_loyalty(pokemon,6,reason='actual willing Grass pair')
        self.acquire(branch='풀',actor=self.u)
        self.acquire('Foiling Foliage',branch='풀',actor=self.u)
        self.acquire('Enduring Bloom',branch='풀',actor=self.u)

    def bloom_offer(self):
        rows=[row for row in self.e.pending_class_actor_state_reactions(self.u)
              if row['source']==REACTIONS.ENDURING_BLOOM]
        self.assertEqual(len(rows),1)
        return rows[0]

    def assert_native_bloom_origin(self,offer,completion_id):
        self.assertEqual(offer['completion_id'],completion_id)
        event_id=offer['native_event_id']
        native=self.e._passive_events[event_id]
        self.assertEqual(offer['native_origin_version'],1)
        self.assertEqual(native['class_actor_reaction_offers'][offer['id']],
            {key:value for key,value in offer.items() if key not in ('status','result')})
        self.assertEqual(native['completion_id'],completion_id)
        self.assertIs(native['actor'],self.p);self.assertIs(native['target'],self.v)
        self.assertEqual(native['move_id'],'move/시그널빔')
        receipt=COMPLETE.require_hit_return(self.e,event_id,self.v)
        self.assertEqual(receipt['completion_id'],completion_id)
        self.assertEqual(receipt['attacker_id'],self.p.entity_id)
        self.assertEqual(receipt['recipient_id'],self.v.entity_id)
        self.assertEqual(offer['attacker_id'],self.p.entity_id)
        self.assertEqual(offer['subject_id'],self.v.entity_id)
        self.assertEqual(offer['target_id'],self.v.entity_id)
        self.assertEqual(offer['actual_type'],'벌레')
        self.assertGreater(offer['type_multiplier'],1)
        result=COMPLETE.recipient_result(self.e._move_completions[completion_id],self.v)
        self.assertTrue(result['hit']);self.assertGreater(result['dealt'],0)
        self.assertEqual(offer['damage_receipt']['net_hp_loss'],result['dealt'])

    def hit_grass(self):
        self.combat(self.p)
        self.native(self.p,self.v,'move/시그널빔',face=18)
        completion_id=self.completed(self.p,'move/시그널빔')['id']
        offer=self.bloom_offer();self.assert_native_bloom_origin(offer,completion_id)
        return completion_id,offer

    def use_disruption(self,completion_id,target):
        before=list(getattr(self.t,'_action_history',[]))
        self.assertTrue(ACE.react(self.e,self.t,self.p,ACE.uid('Disruption Order'),completion_id))
        rows=[row for row in TIME.records(target) if row.get('ace_disruption')]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['accuracy_modifier'],-3)
        self.assertEqual(self.t._action_history,before+['free'])
        state=self.e.export_state()
        with self.assertRaises(ValueError):
            ACE.react(self.e,self.t,self.p,ACE.uid('Disruption Order'),completion_id)
        self.assertEqual(self.e.export_state(),state)

    def test_bloom_accept_and_decline_preserve_original_disruption_through_cold_restore(self):
        for use in (False,True):
            for cold in (False,True):
                with self.subTest(use=use,cold=cold):
                    self.grass_defender();completion_id,offer=self.hit_grass()
                    if cold:
                        self.restore();offer=self.bloom_offer()
                        self.assert_native_bloom_origin(offer,completion_id)
                    history=list(getattr(self.u,'_action_history',[]))
                    result=self.e.resolve_class_actor_state_reaction(self.u,offer['id'],
                        use=use,**({'stats':('def',)} if use else {}))
                    self.assertEqual(result['used'],use)
                    self.assertEqual(list(getattr(self.u,'_action_history',[])),history+(['free'] if use else []))
                    self.assertEqual(self.v.temp_hp,12 if use else 0)
                    self.assertEqual(self.v.stages['def'],1 if use else 0)
                    self.use_disruption(completion_id,self.v)
                    self.assertEqual(self.p.move_uses['move/시그널빔'],1)
                    self.valid()

    def test_bloom_issued_sunny_and_nested_damage_facts_reject_mutation_before_cost(self):
        for changed in ('sunny','damage_receipt','sealed_sunny'):
            with self.subTest(changed=changed):
                self.grass_defender();completion_id,offer=self.hit_grass()
                self.assertFalse(offer['sunny'])
                stored=next(row for row in self.u.spec[REACTIONS.STATE]['events'] if row['id']==offer['id'])
                field='sunny' if changed=='sealed_sunny' else changed
                original=deepcopy(stored[field])
                native=self.e._passive_events[offer['native_event_id']]
                witness=deepcopy(native['class_actor_reaction_offers'][offer['id']])
                before=(self.v.hp,self.v.temp_hp,dict(self.v.stages),
                        list(getattr(self.u,'_action_history',[])),deepcopy(FREQUENCY.state(self.u)),
                        self.e.rng.getstate())
                if field=='sunny':stored['sunny']=True
                else:stored['damage_receipt']['requested']+=1
                if changed=='sealed_sunny':
                    # Editing both copies still cannot rewrite their original
                    # native event intent seal, including finite JSON floats.
                    native['class_actor_reaction_offers'][offer['id']]['sunny']=True
                    rejection='request identity reused with changed input'
                else:
                    self.assertEqual(native['class_actor_reaction_offers'][offer['id']],witness)
                    rejection='actual issued native occurrence'
                with self.assertRaisesRegex(ValueError,rejection):
                    self.e.resolve_class_actor_state_reaction(self.u,offer['id'],use=True,
                        stats=('def','spd') if field=='sunny' else ('def',))
                self.assertEqual((self.v.hp,self.v.temp_hp,dict(self.v.stages),
                    list(getattr(self.u,'_action_history',[])),FREQUENCY.state(self.u),self.e.rng.getstate()),before)
                stored[field]=original
                if changed=='sealed_sunny':native['class_actor_reaction_offers'][offer['id']]['sunny']=original
                self.assertTrue(self.e.resolve_class_actor_state_reaction(self.u,offer['id'],
                    use=True,stats=('def',))['used'])
                self.assertEqual((self.v.temp_hp,self.v.stages['def'],self.v.stages['spd']),(12,1,0))
                self.assertEqual(self.u._action_history,before[3]+['free'])
                self.use_disruption(completion_id,self.v)
                self.valid()

    def test_witnessed_bloom_cannot_downgrade_or_delete_its_pending_owner_record(self):
        self.grass_defender();completion_id,offer=self.hit_grass()
        events=self.u.spec[REACTIONS.STATE]['events']
        stored=next(row for row in events if row['id']==offer['id'])
        position=events.index(stored);original=deepcopy(stored)
        native=self.e._passive_events[offer['native_event_id']]
        witness=deepcopy(native['class_actor_reaction_offers'][offer['id']])
        before=(self.v.hp,self.v.temp_hp,dict(self.v.stages),
                list(getattr(self.u,'_action_history',[])),deepcopy(FREQUENCY.state(self.u)),self.e.rng.getstate(),
                list(getattr(self.p,'_action_history',[])),deepcopy(self.p.budget))
        for changed in ('version','origin','identity','row'):
            with self.subTest(changed=changed):
                stored['sunny']=True
                stored.pop('native_origin_version')
                if changed in ('origin','identity'):
                    stored.pop('native_event_id');stored.pop('completion_id')
                identity=offer['id']
                if changed=='identity':
                    identity+=':forged-legacy';stored['id']=identity
                if changed=='row':events.remove(stored)
                with self.assertRaisesRegex(ValueError,'actual issued native occurrence'):
                    REACTIONS.validate_world(self.e)
                with self.assertRaisesRegex(ValueError,'actual issued native occurrence'):
                    self.e.resolve_class_actor_state_reaction(self.u,identity,use=True,stats=('def','spd'))
                with self.assertRaisesRegex(ValueError,'actual issued native occurrence'):
                    TURN.spend(self.e,self.p,'free','deleting a pending row cannot release the ordinary-action guard')
                self.assertEqual((self.v.hp,self.v.temp_hp,dict(self.v.stages),
                    list(getattr(self.u,'_action_history',[])),FREQUENCY.state(self.u),self.e.rng.getstate(),
                    list(getattr(self.p,'_action_history',[])),self.p.budget),before)
                self.assertEqual(native['class_actor_reaction_offers'][offer['id']],witness)
                if changed=='row':events.insert(position,stored)
                stored.clear();stored.update(deepcopy(original))
        self.assertTrue(self.e.resolve_class_actor_state_reaction(self.u,offer['id'],use=True,stats=('def',))['used'])
        self.assertEqual((self.v.temp_hp,self.v.stages['def'],self.v.stages['spd']),(12,1,0))
        self.use_disruption(completion_id,self.v)
        self.valid()

    def test_unrelated_ordinary_free_after_bloom_closes_original_disruption(self):
        for use in (False,True):
            with self.subTest(use=use):
                self.grass_defender();completion_id,offer=self.hit_grass()
                self.e.resolve_class_actor_state_reaction(self.u,offer['id'],
                    use=use,**({'stats':('def',)} if use else {}))
                self.assertTrue(TURN.spend(self.e,self.p,'free','actual unrelated ordinary Free action'))
                before=self.e.export_state()
                with self.assertRaises(ValueError):
                    ACE.react(self.e,self.t,self.p,ACE.uid('Disruption Order'),completion_id)
                self.assertEqual(self.e.export_state(),before)
                self.assertFalse(any(row.get('ace_disruption') for row in TIME.records(self.v)))

    def test_bloom_rejects_another_real_hit_pair_even_with_equal_damage(self):
        self.grass_defender();old_completion,old_offer=self.hit_grass()
        self.e.resolve_class_actor_state_reaction(self.u,old_offer['id'],use=False)
        # One actual unused personal turn separates the EOT Signal Beam uses.
        self.e.end_of_turn(self.p);self.e.end_round();self.combat(self.p)
        self.e.end_of_turn(self.p);self.e.end_round();self.combat(self.p)
        self.e.gm.set_hp(self.v,value=old_offer['damage_receipt']['before']['hp'],
            reason='independent GM healing makes two genuine hits have identical before HP')
        self.native(self.p,self.v,'move/시그널빔',face=18)
        current_completion=self.completed(self.p,'move/시그널빔')['id']
        offer=self.bloom_offer();self.assert_native_bloom_origin(offer,current_completion)
        self.assertNotEqual(current_completion,old_completion)
        self.assertEqual(offer['damage_receipt']['net_hp_loss'],old_offer['damage_receipt']['net_hp_loss'])
        self.assertEqual(offer['damage_receipt']['before'],old_offer['damage_receipt']['before'])
        stored=next(row for row in self.u.spec[REACTIONS.STATE]['events'] if row['id']==offer['id'])
        original=(stored['native_event_id'],stored['completion_id'])
        stored['native_event_id']=old_offer['native_event_id'];stored['completion_id']=old_completion
        before=(self.v.hp,self.v.temp_hp,dict(self.v.stages),
                list(getattr(self.u,'_action_history',[])),deepcopy(FREQUENCY.state(self.u)))
        with self.assertRaisesRegex(ValueError,'actual issued native occurrence'):
            self.e.resolve_class_actor_state_reaction(self.u,offer['id'],use=True,stats=('def',))
        self.assertEqual((self.v.hp,self.v.temp_hp,dict(self.v.stages),
                          list(getattr(self.u,'_action_history',[])),FREQUENCY.state(self.u)),before)
        stored['native_event_id'],stored['completion_id']=original
        self.e.resolve_class_actor_state_reaction(self.u,offer['id'],use=False)
        self.use_disruption(current_completion,self.v)

    def test_trickster_splash_jump_child_cold_resume_retains_original_bug_hit(self):
        for cold in (False,True):
            with self.subTest(cold=cold):
                self.family('벌레','Insectoid Utility','Disruption Order')
                self.e.gm.set_skill(self.t,'교활',6,reason='actual Trickster prerequisite')
                ACQUIRE.acquire_static(self.e,self.t,TRICKSTER.CLASS,
                    selection={'source':'core'},acquisition_request_id='mixed08/trickster')
                self.e.gm.set_skill(self.p,'곡예','6d6',reason='actual Pokemon maneuver pool')
                self.u=self.add('actual defending Tumbler','trainer',(3,2),side='foe',
                    classes=[],feats=[],edges=[TUMBLER.ACROBAT],exp_bank=100,
                    skills={**self.common['skills'],'곡예':6},
                    movement={'land':6,'high_jump':1,'long_jump':2,'power':4},movement_basis='base')
                for feature in (TUMBLER.CLASS,TUMBLER.AERIAL,TUMBLER.FLIP):
                    ACQUIRE.acquire_static(self.e,self.u,feature,
                        acquisition_request_id='mixed08/'+feature)
                self.combat(self.p);self.native(self.p,self.u,'move/실뿜기',face=18,aim=(3,2))
                original=self.completed(self.p,'move/실뿜기')['id']
                self.assertEqual(self.e._move_completions[original]['move']['class'],'변화')
                self.assertTrue(COMPLETE.recipient_result(self.e._move_completions[original],self.u)['hit'])
                dealt=COMPLETE.recipient_result(self.e._move_completions[original],self.u)['dealt']
                self.e.watch_move_defense(self.u,[{'actor_id':self.u.entity_id,'source':TUMBLER.SPLASH}],
                    reason='actual acquired native Splash reaction to following maneuver')
                self.e.rulings.add_answer('native_attack_splash',
                    {'jump':{'destination':(3,3),'difficult':True,'difficulty_skill':'곡예',
                             'difficulty_dc':100,'difficulty_options':{'fixed':[1]*6},'clear_path':True}},
                    reason='actual difficult defensive Jump choice',scope='scene')
                ap=AP.available(self.t)
                trainer_history=list(getattr(self.t,'_action_history',[]))
                pokemon_history=list(getattr(self.p,'_action_history',[]))
                options={'challenger_options':{'fixed':[6]*6},'defender_options':{'fixed':[1]*6}}
                result=self.e.trickster_maneuver(self.t,self.p,self.u,original,'dirty_trick','low_blow',**options)
                self.assertIsInstance(result,CHECKS.PendingDecision)
                jump_id=self.u.spec['_jump_pending']
                active=self.p.custom_conditions[MANEUVERS.ACTIVE]
                self.assertEqual(self.p.custom_conditions[MANEUVERS.RECEIPTS][active]['stage'],'attack_boundary')
                self.assertEqual(AP.available(self.t),ap-1)
                self.assertEqual(self.t._action_history,trainer_history+['free'])
                self.assertEqual(self.p._action_history,pokemon_history+['free'])
                rng=self.e.rng.getstate()
                if cold:self.restore();self.assertEqual(self.e.rng.getstate(),rng)
                JUMP.resolve_failure(self.e,self.u,decision='land',reason_text='actual failed reaction Jump landing')
                self.e.resume_jump_move(self.u,event_id=jump_id)
                self.assertIs(self.e._active_turn_actor,self.p)
                after_jump_rng=self.e.rng.getstate()
                with patch.object(Engine,'accuracy_check',side_effect=AssertionError('paid child must not repeat accuracy')):
                    result=self.e.dirty_trick(self.p,self.u,'low_blow',**options)
                self.assertTrue(result)
                self.assertEqual(self.e.rng.getstate(),after_jump_rng)
                self.assertEqual(AP.available(self.t),ap-1)
                self.assertEqual(self.t._action_history,trainer_history+['free'])
                self.assertEqual(self.p._action_history,pokemon_history+['free'])
                self.assertEqual(self.p.move_uses['move/실뿜기'],1)
                self.assertEqual(self.u.move_uses[TUMBLER.SPLASH],1)
                self.assertEqual(RESOURCES.pending(self.u).get('shift'),1)
                self.assertEqual(COMPLETE.recipient_result(self.e._move_completions[original],self.u)['dealt'],dealt)
                self.assertEqual(len([row for row in self.e._move_completions.values()
                    if row['actor'] is self.p and row['move_id']=='move/실뿜기']),1)
                self.use_disruption(original,self.u)
                self.valid()