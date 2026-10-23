"""Training-mode native state. Orders remains explicitly incomplete."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from engine import Rules, Engine, Combatant
import training_features as T
import items as ITEMS
import initiative as INIT
import effects_ext as EXT
import downtime as DT
import state_codec as CODEC
import state_grants as GRANTS
import pokemon_entities as ENTITIES
import pokemon_party as PARTY

class TrainingStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset='core')
    def setUp(self):
        self.e = Engine(self.r, seed=104)
        common = dict(level=20, stats={'hp':60,'atk':20,'def':15,'spa':20,'spd':15,'spe':10}, movement={'land':6,'swim':3,'sky':0}, pos=(0,0))
        self.t = Combatant(self.r, dict(common, name='trainer', kind='trainer', feats=list(T.RULES), skills={'육상':3,'명령':3,'협박':3,'매력':3}, moves=[]))
        self.ps = [Combatant(self.r, dict(common, name='p'+str(i), kind='pokemon', trainer_id=self.t.entity_id, trainer=self.t.name, skills={'육상':'2d6+1'}, moves=['move/불꽃세례','move/할퀴기'], pos=(i+1,0))) for i in range(4)]
        self.enemy = Combatant(self.r, dict(common, name='enemy', kind='trainer', moves=[],pos=(1,1)))
        self.e.everyone = self.e.gm.everyone = [self.t,*self.ps,self.enemy]
        self.e.time_actors(self.e.everyone)
        self.t.side='party';self.enemy.side='enemy'
        for p in self.ps:
            p.side='party';ENTITIES.observe_loyalty(self.e,p,3,reason='GM observed willing training partner')
        ITEMS.register_feats(self.e,self.t)
    def train(self, choices=None, request='training-1', **kwargs):
        return self.e.train_pokemon(self.t, choices or [(p,[uid]) for p,uid in zip(self.ps,T.RULES)], minutes=kwargs.pop('minutes',30),reason='observed actual Pokemon training',request_id=request,**kwargs,safe=True)
    def load(self):
        e=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        return e,{a.entity_id:a for a in e.everyone}
    def test_registration_does_not_activate_and_actual_session_is_atomic_idempotent(self):
        self.assertTrue(all(not T.records(p) for p in self.ps));before=deepcopy(self.t.spec)
        receipt=self.train();self.assertEqual(self.e.elapsed_seconds,1800);self.assertEqual(self.t._action_history,['extended'])
        self.assertEqual(len(receipt['sources']),4);self.assertFalse(self.t.spec.get('ap_spent',0));self.assertFalse(self.t.spec.get('experience_training'))
        self.assertEqual(self.train(),receipt);self.assertEqual(self.e.elapsed_seconds,1800)
        with self.assertRaises(ValueError):self.train(minutes=31)
        self.assertEqual(self.e.elapsed_seconds,1800)
    def test_completed_request_replays_after_rest_and_lost_qualification_after_restore(self):
        receipt=self.train();DT.extended_rest(self.e,self.t,4)
        self.t.spec['skills']['육상']=1
        e,actors=self.load();owner=actors[self.t.entity_id]
        choices=[(actors[p.entity_id],[uid]) for p,uid in zip(self.ps,T.RULES)]
        before=e.elapsed_seconds,e.rng.getstate(),deepcopy(owner.spec)
        result=e.train_pokemon(owner,choices,minutes=30,reason='observed actual Pokemon training',request_id='training-1',safe=True)
        self.assertEqual(result,receipt)
        self.assertEqual(before,(e.elapsed_seconds,e.rng.getstate(),owner.spec))
        self.assertTrue(all(not T.records(p) for p,_ in choices))
        result['sources'].clear()
        self.assertTrue(owner.custom_conditions['_training_sessions']['training-1']['sources'])
        for request,minutes in [('training-1',31),('new-training',30)]:
            with self.assertRaises(ValueError):e.train_pokemon(owner,choices,minutes=minutes,reason='observed actual Pokemon training',request_id=request,safe=True)
        self.assertEqual(before,(e.elapsed_seconds,e.rng.getstate(),owner.spec))

    def test_all_four_actual_consumer_paths_and_natural_face_separation(self):
        self.train();agile,brutal,focused,inspired=self.ps
        self.assertEqual(self.e.move_profile(agile,'land')[0],7)
        self.assertEqual(self.e.move_profile(agile,'swim')[0],4)
        self.assertEqual(INIT.value(self.r,agile).value,14)
        import movement_actions as MOVE
        self.assertEqual(MOVE.capabilities(self.e,agile)['sky'],0)
        move=self.r.move('move/불꽃세례')
        self.assertFalse(self.e.accuracy_check(agile,self.enemy,move,fixed_roll=4)[0])
        self.assertTrue(self.e.accuracy_check(focused,self.enemy,move,fixed_roll=4)[0])
        self.assertFalse(self.e.accuracy_check(focused,self.enemy,move,fixed_roll=1)[0])
        self.assertTrue(self.e.accuracy_check(brutal,self.enemy,move,fixed_roll=19)[2])
        self.assertFalse(self.e.accuracy_check(agile,self.enemy,move,fixed_roll=19)[2])
        self.assertEqual(self.e.skill_roll(focused,'육상',fixed=[1,1]).total,5)
        self.assertEqual(inspired.evasion('물리'),4);self.assertEqual(EXT.save_dc(self.e,inspired,'마비',11),9)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(brutal)
        with patch.object(self.e,'d20',return_value=17):self.e.use_move(brutal,self.enemy,'move/불꽃세례',set_damage=True)
        self.assertIn('화상',self.enemy.conditions);self.assertEqual(brutal.budget['standard'],0)
    def test_target_rest_and_scene_do_not_expire_trainer_rest_does(self):
        self.train();DT.extended_rest(self.e,self.ps[0],4)
        self.assertEqual(self.e.move_profile(self.ps[0],'land')[0],7)
        self.e.end_scene();self.assertTrue(all(T.records(p) for p in self.ps))
        DT.extended_rest(self.e,self.t,4)
        self.assertTrue(all(not T.records(p) for p in self.ps));self.assertEqual(self.e.move_profile(self.ps[0],'land')[0],6)
    def test_replacement_and_explicit_revocation_preserve_independent_values(self):
        self.ps[0].initiative_bonus=3;self.train()
        self.train([(self.ps[0],[T.FOCUSED])],request='replacement')
        self.assertEqual(len(T.records(self.ps[0])),1);self.assertEqual(INIT.value(self.r,self.ps[0]).value,13)
        self.assertEqual(self.e.move_profile(self.ps[0],'land')[0],6)
        self.assertEqual(self.e.skill_roll(self.ps[0],'육상',fixed=[1,1]).total,5)
        source=T.records(self.ps[0])[0][GRANTS.TAG];GRANTS.revoke(self.ps[0],source,engine=self.e)
        self.assertEqual(self.e.skill_roll(self.ps[0],'육상',fixed=[1,1]).total,3)
        self.assertEqual(self.ps[0].initiative_bonus,3)
    def test_codec_and_gm_restore_keep_actual_owner_and_expiry(self):
        self.train();self.e.gm.snapshot('trained')
        DT.extended_rest(self.e,self.t,4);self.e.gm.restore('trained')
        self.assertIs(T.records(self.ps[0])[0]['owner'],self.t)
        e,actors=self.load();owner=actors[self.t.entity_id];pokemon=actors[self.ps[0].entity_id]
        self.assertIs(T.records(pokemon)[0]['owner'],owner);self.assertEqual(e.move_profile(pokemon,'land')[0],7)
        DT.extended_rest(e,owner,4);self.assertEqual(e.move_profile(pokemon,'land')[0],6)
    def test_actual_owner_transfer_cleans_only_tracked_training(self):
        self.train();receiver=self.enemy
        PARTY.configure(self.e,self.t,mode='unlimited',reason='actual roster',roster=self.ps)
        PARTY.configure(self.e,receiver,mode='unlimited',reason='actual empty roster',roster=[])
        self.ps[0].initiative_bonus=2
        PARTY.transfer(self.e,self.t,target=self.ps[0],new_owner=receiver,reason='observed transfer',request_id='transfer-training')
        self.assertFalse(T.records(self.ps[0]));self.assertEqual(INIT.value(self.r,self.ps[0]).value,12)
        self.assertTrue(T.records(self.ps[1]))
    def test_exact_eligibility_atomic_rejection_and_orders_hold(self):
        before=(self.e.elapsed_seconds,deepcopy(self.t.spec),[deepcopy(p.spec) for p in self.ps])
        for choices,minutes in [([(self.ps[0],[T.AGILITY])],29), ([(self.ps[0],[T.AGILITY,T.FOCUSED])],30), ([(self.ps[0],[T.AGILITY]),(self.ps[0],[T.BRUTAL])],30), ([(self.enemy,[T.AGILITY])],30)]:
            with self.assertRaises(ValueError):self.train(choices,minutes=minutes)
        self.assertEqual(before,(self.e.elapsed_seconds,self.t.spec,[p.spec for p in self.ps]))
        order_before=deepcopy((self.t.spec,self.ps[0].spec,getattr(self.t,'pending_action_loss',None)))
        with self.assertRaisesRegex(ValueError,'open combat round'):
            self.e.manual_feat(self.t,T.FOCUSED,self.ps[0])
        self.assertEqual(order_before,(self.t.spec,self.ps[0].spec,getattr(self.t,'pending_action_loss',None)))
        self.assertFalse(T.records(self.ps[0]))
        self.t.spec['skills']['육상']=2
        with self.assertRaises(ValueError):self.train([(self.ps[0],[T.AGILITY])])
    def test_imported_elite_exception_allows_two_distinct_regimes_and_one_gift_waiver(self):
        self.t.spec['classes']=['class/에이스-트레이너'];self.t.spec['feats'].append(T.ELITE)
        self.t.spec['skills']['육상']=1;self.t.spec['elite_training_choice']=T.AGILITY
        self.train([(self.ps[0],[T.AGILITY,T.FOCUSED])])
        self.assertEqual(len(T.records(self.ps[0])),2);self.assertEqual(self.e.move_profile(self.ps[0],'land')[0],7)
        self.assertEqual(self.e.skill_roll(self.ps[0],'육상',fixed=[1,1]).total,5)
        with self.assertRaises(ValueError):self.train([(self.ps[0],[T.AGILITY,T.AGILITY])],request='double')
        with self.assertRaises(ValueError):self.train([(self.ps[0],[T.AGILITY,T.BRUTAL,T.FOCUSED])],request='triple')

if __name__=='__main__': unittest.main()
