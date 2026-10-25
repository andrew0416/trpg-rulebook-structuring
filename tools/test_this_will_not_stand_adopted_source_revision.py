"""S-p2c4-4: one adopted HP-crossing owner for native and imported Type Ace feats."""
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Engine, Rules
import class_actor_state_reactions as REACTIONS
import frequency as FREQ
import heavy_injury_adapter as HEAVY
import native_scenario_fixture as NATIVE
import pokemon_entities as ENTITIES
import state_codec as CODEC
import state_grants as GRANTS
import trainer_feature_acquisition as ACQUIRE
import type_ace as TA
import world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]
FEATURE='feat/이건-버티지-못할걸'
PARENT='feat/폭군의-울부짖기'
STATS=('atk','spa','spe')
TACKLE='move/몸통박치기'


class ThisWillNotStandAdoptedSourceRevisionTests(unittest.TestCase):
    def world(self, *, receipted=False, attack=1):
        def trainer(key,pos,side,*,owner=False):
            stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),30)
            if not owner:stats['atk']=attack
            extra={'id':'adopted-'+key,'feats':[] if receipted or not owner else [PARENT,FEATURE],
                'classes':[] if receipted or not owner else [TA.CLASS],
                'feature_choices':{TA.CLASS:['드래곤']} if owner and not receipted else {},
                'exp_bank':100,'type_link_skills':{'드래곤':'협박'} if owner else {},
                'movement':{'land':6,'power':3},'movement_basis':'current','power_basis':'current'}
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':30,'stats':stats,
                'moves':[TACKLE],'abilities':[],'skills':{'협박':6,'명령':6},
                'pos':pos,'side':side,'extra':extra},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual observed trainer body'}}
        pokemon=[]
        for key,pos in (('p',(2,2)),('q',(2,3)),('r',(2,4))):
            pokemon.append({'key':key,'kind':'pokemon','sheet':{'species':'미뇽','name':key,
                'level':30,'moves':[TACKLE],'abilities':[],'pos':pos,'side':'party',
                'extra':{'trainer_id':'adopted-owner'}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual observed owned Dragon body'}})
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='core',seed=1454,
            grid={'width':12,'height':8},actors=[trainer('owner',(1,1),'party',owner=True),*pokemon,
                trainer('attacker',(3,2),'foe')])
        self.t,self.p,self.q,self.r,self.foe=[actors[key] for key in ('owner','p','q','r','attacker')]
        for actor in (self.p,self.q,self.r):
            ENTITIES.observe_loyalty(self.e,actor,3,reason='actual GM observation of the current owner relationship')
        if receipted:
            for feature in (TA.CLASS,PARENT,FEATURE):
                options={'branch':'드래곤'} if feature==TA.CLASS else {}
                ACQUIRE.acquire_static(self.e,self.t,feature,
                    acquisition_request_id='actual-adopted-'+feature,**options)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.foe,initiative_count=20)
        self.answer(True)

    def answer(self,value):
        self.e.rulings.answers[:]=[row for row in self.e.rulings.answers if row['key']!='type_ace_choice']
        self.e.rulings.add_answer('type_ace_choice',value,reason='actual owner chooses adopted HP-crossing feature')

    def above_half(self,actor=None):
        actor=self.p if actor is None else actor
        self.e.gm.set_hp(actor,value=actor.base_max_hp//2+1,reason='actual HP immediately above half')

    def used(self,actor=None):
        actor=self.t if actor is None else actor
        return FREQ.state(actor)['activations'].get(FEATURE,{}).get('used',0)

    def assert_effect(self,actor=None):
        actor=self.p if actor is None else actor
        self.assertEqual(tuple(actor.stages[stat] for stat in STATS),(1,1,1))
        self.assertIn('난동',actor.conditions)
        self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))

    def attack(self,face=15):
        with patch.object(Engine,'d20',return_value=face):
            return self.e.use_move(self.foe,self.p,TACKLE,set_damage=True)

    def restore(self):
        ids=[actor.entity_id for actor in (self.t,self.p,self.q,self.r,self.foe)]
        state=json.loads(json.dumps(CODEC.dump_engine(self.e)))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),state)
        index=WORLD.actor_index(self.e)
        self.t,self.p,self.q,self.r,self.foe=[index[uid] for uid in ids]

    def test_actual_noncritical_native_attack_crossing_uses_same_imported_and_receipted_effect(self):
        for receipted in (False,True):
            with self.subTest(receipted=receipted):
                self.world(receipted=receipted);self.above_half()
                self.attack()
                self.assert_effect();self.assertEqual(self.used(),1);self.assertEqual(self.used(self.p),1)
                self.assertEqual(self.t._action_history,['free'])
                self.assertEqual(self.foe.move_uses[TACKLE],1)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_critical_above_half_and_massive_below_half_never_restore_old_trigger(self):
        for receipted in (False,True):
            with self.subTest(receipted=receipted):
                self.world(receipted=receipted)
                self.attack(face=20)
                self.assertGreater(self.p.hp*2,self.p.base_max_hp)
                self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))
                self.assertEqual(self.used(),0);self.assertNotIn('난동',self.p.conditions)
                self.world(receipted=receipted,attack=1000)
                self.e.gm.set_hp(self.p,value=self.p.base_max_hp//2,reason='already at or below half before actual massive hit')
                before=self.p.hp
                with self.assertRaises(HEAVY.HeavyPending) as pending:self.attack()
                event_id=self.e._heavy_pending;event=self.e._heavy_events[event_id]
                self.assertEqual(pending.exception.event_id,event_id)
                self.assertEqual((event['kind'],event['status']),('attack_damage','pending'))
                self.assertIs(event['attacker'],self.foe);self.assertIs(event['target'],self.p)
                self.assertEqual(event['move']['id'],TACKLE)
                self.assertEqual((event['before']['hp'],event['observed_after']['hp']),(before,self.p.hp))
                self.assertGreater(event['amount'],0);self.assertLess(self.p.hp,before)
                self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))
                self.assertEqual(self.used(),0);self.assertEqual(getattr(self.t,'_action_history',[]),[])

    def test_actual_loss_endpoint_crossing_applies_enraged_and_three_stages_without_an_attack(self):
        for receipted in (False,True):
            with self.subTest(receipted=receipted):
                self.world(receipted=receipted);self.above_half()
                self.e.lose_hp(self.p,1,unpreventable=True,source='actual unpreventable native HP loss')
                self.assert_effect();self.assertEqual(self.used(),1)
                self.assertFalse(getattr(self.e,'_move_completions',{}))
                self.assertTrue(self.e.validate_state()['valid'])

    def test_scene_two_owner_uses_and_once_per_pokemon_share_existing_frequency_ledgers(self):
        for receipted in (False,True):
            with self.subTest(receipted=receipted):
                self.world(receipted=receipted)
                for actor in (self.p,self.p,self.q,self.r):
                    self.above_half(actor);self.e.lose_hp(actor,1,unpreventable=True)
                self.assert_effect(self.p);self.assert_effect(self.q)
                self.assertEqual(self.used(),2);self.assertEqual(self.t._action_history,['free','free'])
                self.assertEqual(self.used(self.p),1);self.assertEqual(self.used(self.q),1);self.assertEqual(self.used(self.r),0)
                self.assertNotIn('난동',self.r.conditions)
                self.assertEqual(tuple(self.r.stages[stat] for stat in STATS),(0,0,0))
                self.assertTrue(self.e.validate_state()['valid'])

    def test_imported_feature_removal_and_actual_static_withdrawal_cannot_revive_an_owner(self):
        self.world();self.t.spec['feats'].remove(FEATURE);self.above_half()
        self.e.lose_hp(self.p,1,unpreventable=True)
        self.assertEqual(self.used(),0);self.assertNotIn('난동',self.p.conditions)
        self.world(receipted=True)
        source=next(sid for sid,row,active in ACQUIRE._static_records(self.t)
            if active and row['static_acquisition']['feature_id']==FEATURE)
        GRANTS.revoke(self.t,source,engine=self.e)
        self.t.spec['feats'].append(FEATURE)
        self.assertFalse(TA.hp_interested(self.e,self.p))
        self.t.spec['feats'].remove(FEATURE)
        self.above_half();self.e.lose_hp(self.p,1,unpreventable=True)
        self.assertEqual(self.used(),0);self.assertNotIn('난동',self.p.conditions)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_declined_crossing_and_gm_cold_restore_preserve_unspent_then_spent_quotas(self):
        for receipted in (False,True):
            with self.subTest(receipted=receipted):
                self.world(receipted=receipted);self.answer(False);self.above_half()
                self.e.lose_hp(self.p,1,unpreventable=True)
                self.assertEqual(self.used(),0);self.assertNotIn('난동',self.p.conditions)
                self.answer(True);self.above_half()
                self.e.gm.snapshot('adopted-before-crossing');self.e.gm.restore('adopted-before-crossing');self.restore()
                self.e.lose_hp(self.p,1,unpreventable=True);self.assert_effect();self.assertEqual(self.used(),1)
                self.e.gm.snapshot('adopted-paid-crossing');self.e.gm.restore('adopted-paid-crossing');self.restore()
                self.assert_effect();self.assertEqual(self.used(),1);self.assertEqual(self.used(self.p),1)
                self.above_half();self.e.lose_hp(self.p,1,unpreventable=True)
                self.assert_effect();self.assertEqual(self.used(),1);self.assertEqual(self.t._action_history,['free'])
                self.assertTrue(self.e.validate_state()['valid'])

    def test_common_transaction_rolls_back_hp_free_action_quota_enraged_and_stages_on_failure(self):
        for receipted in (False,True):
            with self.subTest(receipted=receipted):
                self.world(receipted=receipted);self.above_half()
                def apply(e,p,t):return e.lose_hp(p,1,unpreventable=True)
                with patch.object(Engine,'change_stage',side_effect=ValueError('actual adopted stage receiver failed')):
                    NATIVE.assert_rejected_unchanged(self.e,
                        lambda:GRANTS.transition(self.e,self.p,apply,participants=(self.t,),include_grid=True),
                        reason_pattern='actual adopted stage receiver failed')
                self.assertEqual(self.used(),0);self.assertNotIn('난동',self.p.conditions)


if __name__=='__main__':unittest.main()
