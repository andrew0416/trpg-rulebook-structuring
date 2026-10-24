"""S-p2c4-3: actual Shocking Speed applies only to its trainer's Pokemon."""
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Engine, Rules
import fast_combat as FAST
import frequency as FREQ
import native_scenario_fixture as NATIVE
import passive_events as PASSIVE
import pokemon_entities as ENTITIES
import priority_actions as PRIORITY
import state_codec as CODEC
import world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]
QUICK='move/전광석화'
THUNDER='move/전기쇼크'


class ShockingSpeedOwnedPokemonSourceRevisionTests(unittest.TestCase):
    def world(self, *, ownership='owner', pending=False):
        def trainer(key,pos,side,*,owner=False,ability=False):
            extra={'id':'shocking-'+key,'feats':[PRIORITY.SHOCKING,'feat/락다운'] if owner else [],
                'type_link_skills':{'전기':'집중'} if owner else {},
                'movement':{'land':6,'power':3},'movement_basis':'current','power_basis':'current'}
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':30,
                'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),
                'moves':['move/몸통박치기'],'abilities':['테라셸'] if ability else [],
                'skills':{'집중':5},'pos':pos,'side':side,'extra':extra},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual observed trainer body'}}
        extra={}
        if ownership in ('owner','other'):extra['trainer_id']='shocking-'+ownership
        pokemon={'key':'pokemon','kind':'pokemon','sheet':{'name':'electric user',
            'species':'피카츄','level':30,'moves':[QUICK,THUNDER],'abilities':[],
            'wild':ownership=='wild','side':'party','pos':(2,2),'extra':extra},
            'body':{'size':'소형','offsets':[(0,0)],'reason':'actual observed Electric Pokemon body'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='core',seed=1475,
            grid={'width':12,'height':8},actors=[
                trainer('owner',(1,1),'party',owner=True),
                trainer('other',(1,2),'party'),pokemon,
                trainer('target',(5,2),'enemy',ability=pending)])
        self.t,self.other,self.p,self.foe=[actors[key] for key in ('owner','other','pokemon','target')]
        if ownership in ('owner','other'):
            ENTITIES.observe_loyalty(self.e,self.p,3,reason='actual GM observation for the registered current trainer')
        self.e.prepare_initiative_schedule(self.e.everyone,source='gm/actual-shocking-speed-schedule')
        self.e.start_round(self.e.everyone)

    def shocking(self):
        return self.e.use_priority_move(self.p,self.foe,THUNDER,shocking_speed=self.t)

    def used(self):
        return FREQ.state(self.t)['activations'].get(PRIORITY.SHOCKING,{}).get('used',0)

    def restore(self):
        ids=[actor.entity_id for actor in (self.t,self.other,self.p,self.foe)]
        state=json.loads(json.dumps(CODEC.dump_engine(self.e)))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),state)
        index=WORLD.actor_index(self.e)
        self.t,self.other,self.p,self.foe=[index[uid] for uid in ids]

    def assert_one_paid_use(self):
        self.assertEqual(self.t._action_history,['free']);self.assertEqual(self.used(),1)
        self.assertEqual(self.p.move_uses[THUNDER],1)
        self.assertEqual(self.p.budget,{'standard':0,'shift':1,'swift':1})
        self.assertIs(self.e._active_turn_actor,self.p)
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'],1)

    def test_actual_owned_electric_pokemon_receives_advanced_priority_and_pays_once(self):
        self.world();hp=self.foe.hp
        with patch.object(FAST,'roll',return_value=15):result=self.shocking()
        self.assertEqual(result['source'],PRIORITY.SHOCKING)
        self.assertLess(self.foe.hp,hp);self.assert_one_paid_use()
        self.assertEqual(WORLD.identity_field(self.e,self.p,'owner_id'),self.t.entity_id)
        completions=[row for row in self.e._move_completions.values() if row['actor'] is self.p]
        self.assertEqual(len(completions),1);self.assertEqual(completions[0]['move_id'],THUNDER)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_other_trainers_same_side_electric_pokemon_is_rejected_before_payment_or_loan(self):
        self.world(ownership='other')
        self.assertEqual(WORLD.identity_field(self.e,self.p,'owner_id'),self.other.entity_id)
        NATIVE.assert_rejected_unchanged(self.e,self.shocking,reason_pattern='actual owned Pokemon')
        self.assertEqual(self.used(),0);self.assertEqual(self.t._action_history,[])
        self.assertIsNone(self.e._active_turn_actor)
        self.assertFalse(self.e.initiative_reaction_status()['owed_turns'])

    def test_wild_and_unknown_owner_pokemon_are_rejected_without_any_resource_or_rng_change(self):
        for ownership in ('wild','unknown'):
            with self.subTest(ownership=ownership):
                self.world(ownership=ownership)
                self.assertIsNone(WORLD.identity_field(self.e,self.p,'owner_id'))
                NATIVE.assert_rejected_unchanged(self.e,self.shocking,reason_pattern='actual owned Pokemon')
                self.assertEqual(self.used(),0);self.assertEqual(self.t._action_history,[])
                self.assertNotIn(THUNDER,self.p.move_uses)

    def test_actor_controller_shared_side_and_trainer_name_do_not_replace_actual_ownership(self):
        self.world(ownership='other')
        self.p.spec['controller']={'kind':'actor','id':self.t.entity_id}
        self.p.spec['trainer']=self.t.name
        self.assertEqual(WORLD.identity_field(self.e,self.p,'controller_id'),self.t.entity_id)
        self.assertEqual(self.p.side,self.t.side)
        NATIVE.assert_rejected_unchanged(self.e,self.shocking,reason_pattern='actual owned Pokemon')
        self.assertEqual(WORLD.identity_field(self.e,self.p,'owner_id'),self.other.entity_id)
        self.assertEqual(self.used(),0)

    def test_late_native_failure_rolls_back_real_owned_trainer_cost_turn_loan_frequency_and_rng(self):
        self.world()
        with patch.object(Engine,'_accuracy_check_native',side_effect=ValueError('actual native accuracy receiver failed')):
            NATIVE.assert_rejected_unchanged(self.e,self.shocking,reason_pattern='actual native accuracy receiver failed')
        self.assertEqual(self.used(),0);self.assertEqual(self.t._action_history,[])
        self.assertIsNone(self.e._active_turn_actor)

    def test_real_paid_defense_wait_gm_and_cold_restore_resume_without_second_payment(self):
        self.world(pending=True)
        self.e.watch_ability_interrupt(self.foe,'ability/테라셸',reason='actual defender may choose its defensive type')
        hp=self.foe.hp
        with patch.object(FAST,'roll',return_value=15):
            with self.assertRaises(PASSIVE.PassiveEventPending):self.shocking()
        event=self.e._passive_pending;self.assert_one_paid_use()
        self.assertEqual(self.foe.hp,hp);rng=self.e.rng.getstate()
        self.e.gm.snapshot('owned-shocking-paid');self.e.gm.restore('owned-shocking-paid');self.restore()
        self.assert_one_paid_use();self.assertEqual(self.e._passive_pending,event)
        self.assertEqual(self.e.rng.getstate(),rng)
        self.e.choose_ability_interrupt(event,self.foe,use=False,reason='actual defender declines after restored paid activation')
        self.assertIsNone(self.e._passive_pending);self.assertLess(self.foe.hp,hp)
        self.assert_one_paid_use()
        NATIVE.assert_rejected_unchanged(self.e,
            lambda:self.e.choose_ability_interrupt(event,self.foe,use=False,reason='resolved choice cannot be replayed'),
            reason_pattern='pending|completed|resolved|replay')
        self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_wild_plain_priority_remains_legal_without_shocking_speed_ownership(self):
        self.world(ownership='wild');hp=self.foe.hp
        with patch.object(FAST,'roll',return_value=15):
            result=self.e.use_priority_move(self.p,self.foe,QUICK)
        self.assertEqual(result['source'],QUICK);self.assertLess(self.foe.hp,hp)
        self.assertEqual(self.used(),0);self.assertEqual(self.t._action_history,[])
        self.assertEqual(self.p.move_uses[QUICK],1);self.assertIs(self.e._active_turn_actor,self.p)
        self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
