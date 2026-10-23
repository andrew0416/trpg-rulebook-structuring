"""C11-002/109: adopted gym participants use native turns, Moves and switches."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from grid import Grid
import test_category2_training_state as training_fixture
import test_foundation_initiative_schedule as schedule_fixture
import party_actions as PARTY_ACTIONS,pokemon_party as PARTY,nicolette_gym as NICOLETTE
import state_codec as CODEC,turn as TURN


class GymCommandProfileTests(unittest.TestCase):
    setUpClass=classmethod(training_fixture.TrainingStateTests.setUpClass.__func__)

    def setUp(self):
        training_fixture.TrainingStateTests.setUp(self)
        self.e.grid=Grid(24,16)
        self.pc=self.enemy
        def actor(name,kind,owner=None,pos=(0,0)):
            spec=deepcopy(self.ps[0].spec)
            spec.update(id=kind+'/'+name,name=name,kind=kind,pos=pos,feats=[],abilities=[],edges=[])
            if owner:spec.update(trainer_id=owner.entity_id,trainer=owner.name)
            else:
                spec.pop('trainer_id',None);spec.pop('trainer',None)
            return Combatant(self.r,spec)
        self.pcps=[actor('pc'+str(i),'pokemon',self.pc,(i+1,4)) for i in range(8)]
        self.helper=actor('gym-helper','trainer',pos=(16,10))
        self.helperp=actor('helper-pokemon','pokemon',self.helper,(5,0))
        self.outsider=actor('unadmitted','pokemon',self.t,(8,0))
        self.e.everyone.extend([*self.pcps,self.helper,self.helperp,self.outsider])
        self.e.gm.everyone=self.e.everyone
        for a in self.e.everyone:
            a.spec['skills']={}
            a.spec['size']='중형'
            self.e.gm.set_footprint(a,[(0,0)],reason='observed actual single-cell fixture body')
            a.side='party' if a is self.pc or a in self.pcps else 'gym'
        self.t.pos=(18,10);self.pc.pos=(18,12)
        for trainer,pool in ((self.t,[*self.ps,self.outsider]),(self.pc,self.pcps),(self.helper,[self.helperp])):
            PARTY.configure(self.e,trainer,mode='unlimited',reason='actual complete owned pool',roster=pool)
            self.e.configure_party_combat(trainer,battle_mode='league',reason='GM selected League group challenge')

    def adopt(self,limit=2,helpers=False):
        return self.e.configure_gym_challenge(self.t,pc_trainers=[self.pc],
            gym_trainers=[self.helper] if helpers else [],
            pokemon=[*self.ps,*self.pcps,*([self.helperp] if helpers else [])],
            leader_turn_limit=limit,gm_id='gm/actual-session-gm',reason='GM explicitly chooses this group challenge')

    def sample(self):
        return NICOLETTE.configure_commands(self.e,self.t,pc_trainers=[self.pc],
            pokemon=[*self.ps,*self.pcps],gm_id='gm/actual-session-gm',reason='GM adopts Nicolette group sample')

    def participants(self,helpers=False):
        return [self.pc,*self.ps,*self.pcps,*([self.helper,self.helperp] if helpers else [])]

    def start(self,helpers=False):self.e.start_round(self.participants(helpers))

    def attack(self,actor,target=None):
        target=self.pcps[0] if target is None else target
        self.e.start_of_turn(actor,initiative_count=20)
        before=target.hp
        with patch.object(self.e,'d20',return_value=12):
            damage=self.e.use_move(actor,target,'move/불꽃세례',set_damage=True)
        self.assertGreater(damage,0);self.assertLess(target.hp,before)
        self.assertEqual(actor.budget['standard'],0)
        self.e.end_of_turn(actor)

    def snapshot(self):return deepcopy(CODEC.dump_engine(self.e))

    def test_gm_limit_and_additional_trainer_consume_actual_turns_and_moves(self):
        row=self.adopt(helpers=True);self.assertEqual(row['gym_trainer_ids'],[self.helper.entity_id])
        self.start(helpers=True)
        self.attack(self.ps[0]);self.attack(self.ps[1])
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'already used the Pokemon'):self.e.start_of_turn(self.ps[2])
        self.assertEqual(before,self.snapshot())
        self.e.start_of_turn(self.helper,initiative_count=20)
        self.assertTrue(TURN.spend(self.e,self.helper,'swift','actual helper trainer action'))
        self.e.end_of_turn(self.helper);self.attack(self.helperp)
        used=self.t.spec['party_command_turns']
        self.assertEqual([r['pokemon_id'] for r in used],[p.entity_id for p in self.ps[:2]])
        self.assertEqual(self.helper.spec['party_command_turns'][-1]['pokemon_id'],self.helperp.entity_id)

    def test_nicolette_whole_team_and_pc_ordinary_owner_preserve_distinct_pools(self):
        row=self.sample();self.assertEqual(row['leader_turn_limit'],4)
        self.assertEqual(row['pool_guidance'],{'pc_pokemon':8,'gym_pokemon':4,'recommended_pc_total':6.0,'enforced_cap':False})
        self.start()
        for pokemon in self.ps:self.attack(pokemon)
        self.assertTrue(all(p.on_field for p in self.pcps))
        self.attack(self.pcps[0],self.ps[0])
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'already used the Pokemon'):self.e.start_of_turn(self.pcps[1])
        self.assertEqual(before,self.snapshot())
        self.assertEqual(len(self.t.spec['party_command_turns']),4)

    def test_pc_single_active_turn_and_round_reset_do_not_grant_extra_actions(self):
        self.sample();self.start();self.e.start_of_turn(self.pcps[0])
        before=self.snapshot()
        with self.assertRaises(ValueError):self.e.start_of_turn(self.ps[0])
        self.assertEqual(before,self.snapshot())
        self.e.end_of_turn(self.pcps[0]);self.e.start_round(self.participants())
        self.attack(self.pcps[1],self.ps[0])
        for pokemon in self.ps:self.attack(pokemon)

    def test_profile_survives_codec_and_gm_restore_then_expires_at_encounter_end(self):
        self.sample();self.start();self.attack(self.ps[0]);self.e.gm.snapshot('gym-used-once')
        self.attack(self.ps[1]);self.e.gm.restore('gym-used-once')
        self.assertEqual(len(self.t.spec['party_command_turns']),1)
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index={a.entity_id:a for a in loaded.everyone};self.e=loaded
        self.t=index[self.t.entity_id];self.ps=[index[p.entity_id] for p in self.ps]
        self.pc=index[self.pc.entity_id];self.pcps=[index[p.entity_id] for p in self.pcps]
        for pokemon in self.ps[1:]:self.attack(pokemon)
        self.e.end_encounter(round_elapsed_seconds=10)
        self.assertNotIn(PARTY_ACTIONS.GYM,self.t.spec)
        self.start();self.attack(self.ps[0])
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'already used the Pokemon'):self.e.start_of_turn(self.ps[1])
        self.assertEqual(before,self.snapshot())

    def test_profile_rejects_unadmitted_native_join_turn_and_move_before_payment(self):
        self.adopt();before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'not an admitted'):self.e.begin_encounter([self.outsider])
        self.assertEqual(before,self.snapshot());self.start();before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'not an admitted'):self.e.start_of_turn(self.outsider)
        self.assertEqual(before,self.snapshot())
        with self.assertRaisesRegex(ValueError,'not an admitted'):self.e.use_move(self.outsider,self.pcps[0],'move/불꽃세례')
        self.assertEqual(before,self.snapshot())
        self.outsider.on_field=False;self.e.start_of_turn(self.t)
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'not an admitted'):
            self.e.act_on_party(self.t,send=[(self.outsider,(8,0))],request_id='unadmitted-send',reason='outside the adopted pool')
        self.assertEqual(before,self.snapshot());self.e.end_of_turn(self.t)

        # A completed paid request stays a receipt when the next pool changes.
        self.setUp();self.adopt();self.ps[0].on_field=False;self.start()
        self.e.start_of_turn(self.t)
        intent=dict(send=[(self.ps[0],(1,0))],reason='actual admitted paid send')
        receipt=self.e.act_on_party(self.t,request_id='admitted-replay',**intent)
        self.assertEqual(receipt['payment']['kind'],'shift')
        self.assertEqual(receipt['payment']['funded'],{'shift':1})
        self.e.end_of_turn(self.t);self.e.end_round();self.e.end_encounter()
        self.e.configure_gym_challenge(self.t,pc_trainers=[self.pc],gym_trainers=[],
            pokemon=[*self.ps[1:],*self.pcps],leader_turn_limit=2,
            gm_id='gm/actual-session-gm',reason='GM chooses a different actual next pool')
        self.e.start_round([self.pc,*self.ps[1:],*self.pcps]);self.e.start_of_turn(self.t)
        before=self.snapshot()
        self.assertEqual(self.e.act_on_party(self.t,request_id='admitted-replay',**intent),receipt)
        self.assertEqual(before,self.snapshot())
        with self.assertRaisesRegex(ValueError,'not an admitted'):
            self.e.act_on_party(self.t,request_id='fresh-unadmitted-send',**intent)
        self.assertEqual(before,self.snapshot());self.e.end_of_turn(self.t)

    def test_explicit_identity_limits_ownership_and_scope_are_required_atomically(self):
        options=dict(pc_trainers=[self.pc],gym_trainers=[],pokemon=[*self.ps,*self.pcps],
            leader_turn_limit=2,gm_id='gm/session',reason='explicit GM choice')
        for change in ({'gm_id':''},{'reason':''},{'leader_turn_limit':True},{'leader_turn_limit':0},
                       {'pc_trainers':[self.t]},{'pokemon':[self.pcps[0]]},{'gym_trainers':[self.outsider]}):
            with self.subTest(change=change):
                before=self.snapshot()
                with self.assertRaises(ValueError):self.e.configure_gym_challenge(self.t,**dict(options,**change))
                self.assertEqual(before,self.snapshot())
        self.adopt();before=self.snapshot()
        with self.assertRaises(ValueError):self.adopt()
        self.assertEqual(before,self.snapshot());self.start();before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'closed encounter'):self.adopt()
        self.assertEqual(before,self.snapshot())
        self.ps[0].spec['trainer_id']=self.pc.entity_id
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)

    def test_native_league_switch_lock_and_fainted_replacement_keep_their_owner(self):
        self.sample();self.pcps[1].on_field=False;self.start()
        self.e.start_of_turn(self.pc)
        self.e.act_on_party(self.pc,recall=[self.pcps[0]],send=[(self.pcps[1],(1,4))],request_id='voluntary',reason='actual voluntary League switch')
        self.e.end_of_turn(self.pc);before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'voluntary League'):self.e.start_of_turn(self.pcps[1])
        self.assertEqual(before,self.snapshot())
        # A fainted replacement keeps an unused ordinary turn, without adding one.
        self.setUp();self.sample();self.pcps[0].hp=0;self.pcps[1].on_field=False;self.start()
        self.e.start_of_turn(self.pc)
        result=self.e.act_on_party(self.pc,recall=[self.pcps[0]],send=[(self.pcps[1],(1,4))],request_id='fainted',reason='actual fainted replacement')
        self.assertEqual(result['blocked_command_ids'],[]);self.e.end_of_turn(self.pc)
        self.attack(self.pcps[1],self.ps[0])

    def test_current_source_is_checked_at_adoption_and_native_consumption(self):
        original=Path.read_bytes
        def changed(path):
            return b'changed actual ch11 source' if path.name=='ch11-running-the-game.md' else original(path)
        before=self.snapshot()
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'source changed'):self.sample()
        self.assertEqual(before,self.snapshot());self.sample();self.start();before=self.snapshot()
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'source changed'):self.e.start_of_turn(self.ps[0])
        self.assertEqual(before,self.snapshot())

    def test_profile_preserves_actual_borrowed_turn_and_future_slot_settlement(self):
        self.sample()
        participants=[self.pc,self.ps[0],self.pcps[0]]
        roles=['caller','gym','pc']
        self.e.prepare_initiative_schedule(participants,source='gm/observed-gym-order',
            bindings=[{'slot':a.entity_id,'actor_id':a.entity_id,'role':r} for a,r in zip(participants,roles)],
            order_groups=[[role] for role in roles])
        self.e.start_round(participants);self.e.start_of_turn(self.pc)
        request=schedule_fixture.InitiativeScheduleTests.borrow(self,self.pcps[0])
        queued=self.e.queue_initiative_reactions([request],trigger=schedule_fixture.InitiativeScheduleTests.trigger(self))
        self.e.begin_initiative_reaction(queued['window_id'],'borrow')
        with patch.object(self.e,'d20',return_value=12):
            self.assertGreater(self.e.use_move(self.pcps[0],self.ps[0],'move/불꽃세례',set_damage=True),0)
        self.e.finish_initiative_reaction();self.e.end_of_turn(self.pc)
        self.assertFalse(self.pc.spec.get('party_command_turns'))
        self.e.start_of_turn(self.ps[0]);self.e.end_of_turn(self.ps[0])
        before=self.snapshot()
        with self.assertRaises(ValueError):self.e.start_of_turn(self.pcps[0])
        self.assertEqual(before,self.snapshot());self.e.settle_borrowed_turn()
        self.assertEqual(self.e.initiative_reaction_status()['owed_turns'],[])
        self.e.end_round();CODEC.dump_engine(self.e)

if __name__=='__main__':unittest.main()
