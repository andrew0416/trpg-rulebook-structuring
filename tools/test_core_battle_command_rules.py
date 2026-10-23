"""C07-003/023/026 actual consumers; root must authorize the complete run."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import test_core_gym_command_profile as gym_fixture
import party_actions as PARTY_ACTIONS
import state_codec as CODEC
import turn as TURN
import action_lifecycle as ACTION
import pokemon_party as PARTY
import pokemon_entities as ENTITIES
import state_grants as GRANTS
import initiative_interrupts as INTERRUPTS
import initiative_schedule as SCHEDULE
import move_defense_reactions as DEFENSE
import passive_events as PASSIVE
import priority_actions as PRIORITY


class BattleCommandRulesTests(unittest.TestCase):
    setUpClass=classmethod(gym_fixture.GymCommandProfileTests.setUpClass.__func__)
    setUp=gym_fixture.GymCommandProfileTests.setUp
    attack=gym_fixture.GymCommandProfileTests.attack
    snapshot=gym_fixture.GymCommandProfileTests.snapshot

    def adopt(self,limit,mode='league',trainer=None):
        return self.e.configure_party_combat(trainer or self.pc,battle_mode=mode,
            command_limit=limit,gm_id='gm/actual-command-adoption',
            reason='GM adopts this actual double/triple/NPC combat allowance')

    def start(self):self.e.start_round(self.e.everyone)

    def unchanged(self,callback,pattern=None):
        before=self.snapshot()
        if pattern is None:
            with self.assertRaises(ValueError):callback()
        else:
            with self.assertRaisesRegex(ValueError,pattern):callback()
        self.assertEqual(before,self.snapshot())

    def fresh(self):
        ids=[a.entity_id for a in [self.pc,self.t,*self.pcps,*self.ps]]
        state=json.loads(json.dumps(self.snapshot()))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),state)
        index={a.entity_id:a for a in self.e.everyone}
        actual=[index[uid] for uid in ids]
        self.pc,self.t=actual[:2];self.pcps=actual[2:10];self.ps=actual[10:]

    def test_double_triple_and_npc_allowances_consume_actual_distinct_turns_and_moves(self):
        for limit in (2,3,5):
            with self.subTest(limit=limit):
                self.setUp();row=self.adopt(limit);self.start()
                self.assertEqual(row['command_limit'],limit)
                for pokemon in self.pcps[:limit]:self.attack(pokemon,self.ps[0])
                self.assertEqual([r['pokemon_id'] for r in self.pc.spec['party_command_turns']],
                    [p.entity_id for p in self.pcps[:limit]])
                self.unchanged(lambda:self.e.start_of_turn(self.pcps[limit]),'already used the Pokemon')

    def test_extra_commands_cannot_repeat_one_pokemon_or_refresh_its_action_budget(self):
        self.adopt(3);self.start();self.attack(self.pcps[0],self.ps[0])
        self.unchanged(lambda:self.e.start_of_turn(self.pcps[0]),'already taken')
        self.assertEqual(self.pcps[0].budget['standard'],0)
        self.attack(self.pcps[1],self.ps[0]);self.attack(self.pcps[2],self.ps[0])
        self.assertEqual(len(self.pc.spec['party_command_turns']),3)

    def test_command_adoption_survives_gm_and_fresh_rules_restore_and_resets_by_round(self):
        self.adopt(2);self.start();self.attack(self.pcps[0],self.ps[0])
        self.e.gm.snapshot('one-command-used');self.attack(self.pcps[1],self.ps[0])
        self.e.gm.restore('one-command-used');self.fresh()
        self.assertEqual(self.pc.spec[PARTY_ACTIONS.POLICY]['command_limit'],2)
        self.attack(self.pcps[1],self.ps[0])
        self.unchanged(lambda:self.e.start_of_turn(self.pcps[2]),'already used the Pokemon')
        self.e.start_round(self.e.everyone);self.attack(self.pcps[2],self.ps[0])
        self.attack(self.pcps[3],self.ps[0])

    def test_default_pc_and_existing_gym_cap_have_their_original_owners(self):
        self.adopt(3,trainer=self.t)
        self.e.configure_gym_challenge(self.t,pc_trainers=[self.pc],gym_trainers=[],
            pokemon=[*self.ps,*self.pcps],leader_turn_limit=2,
            gm_id='gm/actual-gym-owner',reason='group gym has its own source-specific cap')
        self.e.start_round([self.t,self.pc,*self.ps,*self.pcps])
        self.attack(self.ps[0]);self.attack(self.ps[1])
        self.unchanged(lambda:self.e.start_of_turn(self.ps[2]),'already used the Pokemon')
        self.attack(self.pcps[0],self.ps[0])
        self.unchanged(lambda:self.e.start_of_turn(self.pcps[1]),'already used the Pokemon')

    def test_outside_combat_multiple_actual_pokemon_do_not_consume_combat_command_history(self):
        self.adopt(2)
        positions=[pokemon.pos for pokemon in self.pcps[:3]]
        for pokemon in self.pcps[:3]:
            self.e.start_of_turn(pokemon)
            before=pokemon.pos
            self.e.approach(pokemon,self.t,reach=1)
            self.assertNotEqual(pokemon.pos,before)
            self.e.end_of_turn(pokemon)
        self.assertFalse(self.e.encounter_active)
        self.assertNotIn('party_command_turns',self.pc.spec)
        self.assertTrue(all(p.on_field for p in self.pcps))
        for pokemon,pos in zip(self.pcps[:3],positions):
            self.e.gm.set_position(pokemon,pos,reason='GM places the walking partners for the actual combat')
        self.start();self.attack(self.pcps[0],self.ps[0]);self.attack(self.pcps[1],self.ps[0])

    def test_adoption_identity_limit_mode_source_and_midcombat_changes_reject_atomically(self):
        for options in ({'command_limit':2},{'command_limit':True,'gm_id':'gm/test'},
                {'command_limit':0,'gm_id':'gm/test'},{'command_limit':2,'gm_id':' '},
                {'command_limit':2,'gm_id':123}):
            self.unchanged(lambda options=options:self.e.configure_party_combat(self.pc,
                battle_mode='league',reason='actual GM adoption',**options))
        self.unchanged(lambda:self.adopt(2,mode='unreviewed-format'))
        original=Path.read_bytes
        def changed(path):
            return b'changed actual combat source' if path.name=='ch07-combat.md' else original(path)
        before=self.snapshot()
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'source changed'):self.adopt(2)
        self.assertEqual(before,self.snapshot())
        self.adopt(2);self.start();self.unchanged(lambda:self.adopt(3))
        before=self.snapshot()
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'source changed'):self.e.start_of_turn(self.pcps[0])
        self.assertEqual(before,self.snapshot())

    def test_restored_command_adoption_requires_its_actual_gm_and_source(self):
        self.adopt(3)
        for key,value in (('command_limit',0),('gm_id',''),('command_source','caller/forged')):
            # Mutation is made on the real actor before dumping so the native
            # codec representation remains the current shared owner's format.
            original=deepcopy(self.pc.spec[PARTY_ACTIONS.POLICY])
            self.pc.spec[PARTY_ACTIONS.POLICY][key]=value
            with self.assertRaises((ValueError,CODEC.StateCodecError)):
                CODEC.load_engine(self.r,json.loads(json.dumps(self.snapshot())))
            self.pc.spec[PARTY_ACTIONS.POLICY]=original


class NativeBattleFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def world(self,mode='league',limit=1):
        self.e=Engine(self.r,703);self.e.grid=Grid(9,7)
        def actor(name,kind,speed,pos,owner=None):
            stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),30);stats['spe']=speed
            spec=dict(id=kind+'/'+name,name=name,kind=kind,size='중형',level=20,
                stats=stats,types=['노말'],skills={},movement={'land':4},movement_basis='current',
                moves=['move/막치기','move/할퀴기','move/판별','move/전광석화','move/울음소리'],abilities=[],feats=[],edges=[],
                pos=pos,side='pc' if owner is self.t or name=='command-owner' else 'foe')
            if owner is not None:spec.update(trainer_id=owner.entity_id,trainer=owner.name)
            return Combatant(self.r,spec)
        self.t=None
        self.t=actor('command-owner','trainer',40,(0,0))
        self.foe_t=actor('opponent-owner','trainer',30,(7,0))
        self.old=actor('old-field','pokemon',10,(2,1),self.t)
        self.new=actor('released','pokemon',10,(1,1),self.t);self.new.on_field=False
        self.foe=actor('opponent','pokemon',20,(3,1),self.foe_t)
        self.foreign=actor('other-opponent','pokemon',7,(6,4),self.foe_t)
        self.others=[actor('other-'+str(i),'pokemon',9-i,(i+1,4),self.t) for i in range(3)]
        self.e.everyone=self.e.gm.everyone=[self.t,self.foe_t,self.old,self.new,self.foe,self.foreign,*self.others]
        for a in self.e.everyone:self.e.gm.set_footprint(a,[(0,0)],reason='actual single-cell battle body')
        for a in self.e.everyone:
            if a.kind=='pokemon':ENTITIES.observe_loyalty(self.e,a,3,reason='GM observes this actual willing partner relationship')
        PARTY.configure(self.e,self.t,mode='unlimited',reason='actual owned party',roster=[self.old,self.new,*self.others])
        PARTY.configure(self.e,self.foe_t,mode='unlimited',reason='actual opponent party',roster=[self.foe,self.foreign])
        for t in (self.t,self.foe_t):
            self.e.configure_party_combat(t,battle_mode=mode,reason='actual declared battle format',
                command_limit=limit if t is self.t else 1,gm_id='gm/actual-battle-adoption')

    def snapshot(self):return deepcopy(CODEC.dump_engine(self.e))

    def unchanged(self,call,pattern=None):
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,pattern or '.*'):call()
        self.assertEqual(before,self.snapshot())

    def prepare(self,actors=None,mode='league'):
        actors=actors or [self.t,self.foe_t,self.old,self.foe]
        self.e.prepare_battle_initiative(actors,battle_mode=mode,bindings=[
            {'slot':'pc-pokemon' if a in (self.old,self.new) else a.entity_id,
             'actor_id':a.entity_id,'role':a.kind} for a in actors])
        self.e.start_round(actors)

    def declarations(self):
        before=(self.e.elapsed_seconds,len(self.e._turn_closures))
        for t in (self.foe_t,self.t):self.e.declare_scheduled_action(t,{'kind':'actual trainer intent','actor_id':t.entity_id})
        self.assertEqual(before,(self.e.elapsed_seconds,len(self.e._turn_closures)))

    def close(self,a):self.e.start_of_turn(a);self.e.end_of_turn(a)

    def attack(self,a,target):
        self.e.start_of_turn(a)
        self.e.approach(a,target,reach=1)
        before=target.hp
        with patch.object(self.e,'d20',return_value=18):self.e.use_move_on(a,target,'move/막치기',self.e.everyone)
        self.assertLess(target.hp,before)
        self.assertEqual(a.budget['standard'],0)
        self.e.end_of_turn(a)

    def switched(self,limit=1,fainted=False,mode='league',placement=False):
        self.world(mode,limit);self.prepare(mode=mode)
        if mode=='league':self.declarations()
        self.e.start_of_turn(self.t)
        if fainted:self.old.hp=0
        if placement:
            self.e.gm.recall(self.old,reason='GM adjudicates a source-specific forced removal')
            self.e.gm.send_out(self.new,(2,1),reason='GM chooses the actual forced replacement')
        else:
            self.e.act_on_party(self.t,recall=[self.old],send=[(self.new,(2,1))],
                request_id='actual-switch',reason='actual fainted replacement' if fainted else 'actual voluntary switch')
        self.e.replace_scheduled_participant('pc-pokemon',self.new,source='gm/actual-switch-binding',reason='actual replacement retains the turn slot')
        self.e.end_of_turn(self.t);self.close(self.foe_t)

    def waiting(self,move='move/막치기',roll=18):
        DEFENSE.watch(self.e,self.new,[{'actor_id':self.new.entity_id,'source':DEFENSE.DETECT}],reason='optional actual-hit Detect')
        self.e.start_of_turn(self.foe)
        with patch.object(self.e,'d20',return_value=roll):
            with self.assertRaises(PASSIVE.PassiveEventPending) as pending:
                self.e.use_move_on(self.foe,self.new,move,self.e.everyone)
        return pending.exception.event_id

    def choose(self,event):return DEFENSE.choose(self.e,event,self.new,use=True,reason='use actual selected Detect for this hit')

    def loan(self):
        loans=getattr(self.e,INTERRUPTS.KEY)['loans']
        self.assertEqual(len(loans),1)
        return next(iter(loans.values()))

    def fresh(self):
        names=('t','foe_t','old','new','foe','foreign');ids={name:getattr(self,name).entity_id for name in names}
        other_ids=[a.entity_id for a in self.others]
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.snapshot())))
        index={a.entity_id:a for a in self.e.everyone}
        for name,uid in ids.items():setattr(self,name,index[uid])
        self.others=[index[uid] for uid in other_ids]

    def next_round(self,extra=()):
        self.e.end_of_turn(self.foe)
        closures=len(self.e._turn_closures)
        self.e.skip_switch_locked_turn(self.new)
        record=self.e._initiative_schedule['records'][-1]
        self.assertEqual(record['outcome'],'switch_locked')
        self.assertNotIn('unavailable',record);self.assertNotIn('closure_sequence',record)
        self.assertEqual(len(self.e._turn_closures),closures)
        self.e.end_round()
        self.prepare([self.t,self.foe_t,self.new,self.foe,*extra]);self.declarations()
        self.close(self.t);self.close(self.foe_t);self.close(self.foe)


class BattleFormatTests(NativeBattleFixture):
    def test_declared_league_and_full_contact_use_native_order_actions_and_distinct_turns(self):
        for mode in ('league','full_contact'):
            self.world(mode)
            # Pokemon is faster than both trainers, exposing the format difference.
            self.old.stats['spe']=50
            self.prepare(mode=mode)
            if mode=='league':
                self.unchanged(lambda:self.e.start_of_turn(self.t))
                self.declarations();order=[self.t,self.foe_t,self.old,self.foe]
            else:order=[self.old,self.t,self.foe_t,self.foe]
            for actor in order:
                if actor.kind=='pokemon':self.attack(actor,self.foe if actor is self.old else self.old)
                else:
                    self.e.start_of_turn(actor)
                    self.assertTrue(TURN.spend(self.e,actor,'swift','actual trainer action'))
                    self.e.end_of_turn(actor)
            self.e.end_round()
            self.assertEqual([row['actor'].entity_id for row in self.e._turn_closures],[a.entity_id for a in order])

    def test_format_mode_role_mismatch_is_atomic_and_restore_keeps_declarations(self):
        self.world()
        self.unchanged(lambda:self.e.prepare_battle_initiative([self.t,self.old],battle_mode='full_contact'))
        self.unchanged(lambda:self.e.prepare_battle_initiative([self.t,self.old],battle_mode='league',bindings=[
            {'slot':'t','actor_id':self.t.entity_id,'role':'pokemon'},
            {'slot':'p','actor_id':self.old.entity_id,'role':'trainer'}]))
        self.prepare();self.e.declare_scheduled_action(self.foe_t,{'kind':'actual first declaration'})
        self.fresh();self.e.gm.snapshot('format-declared')
        state=self.e._initiative_schedule
        self.assertEqual(state['source'],PARTY_ACTIONS.FORMAT_PREFIX+'league')
        self.assertEqual(state['declarations'][self.foe_t.entity_id],{'kind':'actual first declaration'})
        self.unchanged(lambda:self.e.start_of_turn(self.t))
        self.e.declare_scheduled_action(self.t,{'kind':'actual second declaration'})
        self.close(self.t);self.e.gm.restore('format-declared')
        self.assertEqual(self.e._initiative_schedule['cursor'],1)


class SwitchInterruptTests(NativeBattleFixture):
    def test_actual_voluntary_switch_detect_blocks_hit_and_borrows_exact_next_round_command_unit(self):
        self.switched();self.unchanged(lambda:self.e.start_of_turn(self.new),'voluntary League')
        before=(self.new.hp,len(self.e._turn_closures),self.new.custom_conditions.get('combat_turn_serial',0))
        event=self.waiting();parent=deepcopy(self.foe.budget);self.choose(event)
        self.assertEqual((self.new.hp,len(self.e._turn_closures),self.new.custom_conditions.get('combat_turn_serial',0)),before)
        self.assertIsNone(self.new.shield);self.assertIs(self.e._active_turn_actor,self.foe)
        self.assertEqual(self.foe.budget,parent)
        self.assertEqual(self.new.move_uses[DEFENSE.DETECT],1)
        loan=self.loan();self.assertEqual((loan['mode'],loan['due_round'],loan['borrow_round']),('switch_interrupt',2,1))
        self.assertNotIn('borrow_closure',loan)
        self.assertEqual(self.e._move_completions[loan['move_completion']]['phase'],'complete')
        self.next_round();clock=self.e.elapsed_seconds;closures=len(self.e._turn_closures)
        self.unchanged(lambda:self.e.start_of_turn(self.others[0]),'already used the Pokemon')
        self.e.settle_borrowed_turn()
        self.assertEqual((self.e.elapsed_seconds,len(self.e._turn_closures)),(clock,closures))
        self.assertEqual(self.e._initiative_schedule['records'][-1]['outcome'],'switch_interrupt_settled')
        self.assertEqual(INTERRUPTS.command_debts(self.e,self.t),1)
        self.unchanged(lambda:self.e.settle_borrowed_turn())
        self.unchanged(lambda:self.e.start_of_turn(self.others[0]),'already used the Pokemon')
        self.e.end_round()

    def test_gm_three_commands_lose_one_unit_and_same_owner_replacement_cannot_escape_debt(self):
        self.switched(limit=3);event=self.waiting();self.choose(event)
        self.unchanged(lambda:self.e.replace_scheduled_participant('pc-pokemon',self.foreign,
            source='gm/foreign-owner',reason='attempted cross-owner debt transfer'))
        self.next_round(extra=self.others[1:])
        self.e.replace_scheduled_participant('pc-pokemon',self.others[0],
            source='gm/same-owner',reason='normal replacement preserves the trainer debt')
        self.e.settle_borrowed_turn()
        for p in self.others[1:]:self.attack(p,self.foe)
        self.assertEqual(INTERRUPTS.command_debts(self.e,self.t),1)
        self.assertEqual(len([r for r in self.t.spec['party_command_turns'] if r['scope']==[1,2]]),2)
        self.unchanged(lambda:self.e.start_of_turn(self.new),'already used the Pokemon')
        self.e.end_round()

    def test_next_round_preserves_owed_owner_slot_but_allows_a_normal_same_owner_binding(self):
        self.switched();event=self.waiting();self.choose(event)
        self.e.end_of_turn(self.foe);self.e.skip_switch_locked_turn(self.new);self.e.end_round()
        self.unchanged(lambda:self.e.prepare_battle_initiative([self.t,self.foe_t,self.others[0],self.foe],
            battle_mode='league'),'preserve.*slot')
        actors=[self.t,self.foe_t,self.foreign,self.foe]
        bindings=[dict(slot='pc-pokemon' if a is self.foreign else a.entity_id,actor_id=a.entity_id,role=a.kind) for a in actors]
        self.unchanged(lambda:self.e.prepare_battle_initiative(actors,battle_mode='league',bindings=bindings),'trainer command pool')
        actors=[self.t,self.foe_t,self.others[0],self.foe]
        bindings=[dict(slot='pc-pokemon' if a is self.others[0] else a.entity_id,actor_id=a.entity_id,role=a.kind) for a in actors]
        self.e.prepare_battle_initiative(actors,battle_mode='league',bindings=bindings)
        self.e.start_round(actors);self.declarations();self.close(self.t);self.close(self.foe_t);self.close(self.foe)
        self.e.settle_borrowed_turn()
        self.assertIs(self.loan()['settlement']['actor'],self.others[0])
        self.unchanged(lambda:self.e.start_of_turn(self.new),'already used the Pokemon')
        self.e.end_round()

    def test_only_selected_native_detect_action_is_allowed_and_original_borrow_cannot_bypass_lock(self):
        self.switched()
        self.unchanged(lambda:self.e.use_priority_move(self.new,self.foe,'move/전광석화'),'voluntary League')
        self.unchanged(lambda:self.e.use_move_on(self.new,self.foe,'move/할퀴기',self.e.everyone),'voluntary League')
        event=self.waiting();original=Engine.use_move_on
        def guarded(engine,attacker,primary,move_id,everyone,**options):
            if move_id==DEFENSE.DETECT:
                for kind in ('free','shift','swift','standard'):
                    with self.assertRaisesRegex(ValueError,'Interrupt'):TURN.spend(engine,attacker,kind,'unentitled extra action')
                with self.assertRaisesRegex(ValueError,'Interrupt'):
                    TURN.spend_compound(engine,attacker,TURN.ActionCost(('standard','shift')),'unentitled compound action')
                for kind in ('free','shift','swift','standard'):
                    with self.assertRaisesRegex(ValueError,'Interrupt'):ACTION.record_action(engine,attacker,kind)
                with self.assertRaisesRegex(ValueError,'Interrupt'):ACTION.triggered_free_action(engine,attacker,DEFENSE.DETECT)
                target=next(a for a in everyone if a.entity_id==self.foe.entity_id)
                with self.assertRaisesRegex(ValueError,'selected Move'):engine.use_move(attacker,target,'move/막치기')
                with self.assertRaises(ValueError):INTERRUPTS.finish(engine)
            return original(engine,attacker,primary,move_id,everyone,**options)
        with patch.object(Engine,'use_move_on',guarded):self.choose(event)
        self.assertEqual(self.new._action_history,['standard'])
        self.unchanged(lambda:self.choose(event))
        self.assertEqual(self.new.move_uses[DEFENSE.DETECT],1)

    def test_pending_after_native_completion_cold_restore_resumes_once_and_late_failure_is_atomic(self):
        self.switched();event=self.waiting();before=self.snapshot()
        with patch.object(Engine,'use_move_on',return_value=0):
            with self.assertRaisesRegex(ValueError,'did not activate'):self.choose(event)
        self.assertEqual(before,self.snapshot())
        with patch.object(DEFENSE,'consume_shield',side_effect=ValueError('actual late native failure')):
            with self.assertRaisesRegex(ValueError,'late native failure'):self.choose(event)
        self.assertEqual(before,self.snapshot())
        original=Engine.use_move_on
        def pause(engine,attacker,primary,move_id,everyone,**options):
            result=original(engine,attacker,primary,move_id,everyone,**options)
            if move_id==DEFENSE.DETECT:PASSIVE._pending(engine,engine._passive_events[event],'test wait after actual completed selected Move')
            return result
        with patch.object(Engine,'use_move_on',pause):
            with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(event)
        self.assertEqual(self.new.move_uses[DEFENSE.DETECT],1)
        self.fresh();self.e.gm.snapshot('completed-detect-wait')
        self.unchanged(lambda:self.e.use_move(self.new,self.foe,'move/막치기'),'selected Move')
        self.choose(event);self.assertEqual(self.new.move_uses[DEFENSE.DETECT],1)
        self.assertEqual(self.loan()['status'],'owed')
        self.e.gm.restore('completed-detect-wait');self.choose(event)
        self.assertEqual(self.new.move_uses[DEFENSE.DETECT],1)

    def test_source_frequency_trigger_and_restore_ownership_cannot_manufacture_an_interrupt(self):
        self.switched()
        learned=list(self.new.spec['moves'])
        GRANTS.replace_baseline(self.e,self.new,'moves',['move/할퀴기'])
        self.unchanged(lambda:DEFENSE.watch(self.e,self.new,[{'actor_id':self.new.entity_id,'source':DEFENSE.DETECT}],
            reason='unlearned Detect cannot be offered'),'learned')
        GRANTS.replace_baseline(self.e,self.new,'moves',learned)
        original=Path.read_bytes
        def changed(path):return b'changed printed CSV' if path.name=='moves.csv' else original(path)
        before=self.snapshot()
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'selected source changed: move/판별'):
                DEFENSE.watch(self.e,self.new,[{'actor_id':self.new.entity_id,'source':DEFENSE.DETECT}],
                    reason='changed source cannot be offered')
        self.assertEqual(before,self.snapshot())
        before=self.snapshot()
        raw=dict(id='invented-detect',actor_id=self.new.entity_id,source=DEFENSE.DETECT,priority=0,
            mode='switch_interrupt',payment='future_turn',budget={'standard':1},clock='none',move_id=DEFENSE.DETECT)
        self.unchanged(lambda:self.e.queue_initiative_reactions([raw],trigger={'kind':'accuracy','event_id':'invented'}))
        self.assertEqual(before,self.snapshot())
        event=self.waiting();self.choose(event);loan=self.loan()
        for key,value in (('trainer_id',self.foe_t.entity_id),('encounter_epoch',2),('due_round',3),('move_completion','invented')):
            old=loan[key];loan[key]=value
            with self.assertRaises((ValueError,CODEC.StateCodecError)):self.snapshot()
            loan[key]=old
        self.fresh();self.assertEqual(self.loan()['due_round'],2)
        with self.assertRaisesRegex(ValueError,'frequency'):DEFENSE.watch(self.e,self.new,[
            {'actor_id':self.new.entity_id,'source':DEFENSE.DETECT}],reason='same scene cannot reuse Detect')

    def test_full_contact_fainted_and_gm_forced_placement_do_not_create_voluntary_switch_debt(self):
        for options in ({'mode':'full_contact'},{'fainted':True},{'placement':True}):
            with self.subTest(options=options):
                self.switched(**options)
                self.assertIsNone(PARTY_ACTIONS.switch_lock(self.e,self.new))
                stages=dict(self.new.stages)
                event=self.waiting(move='move/울음소리' if options.get('fainted') else 'move/막치기');self.choose(event)
                self.assertEqual(self.new.stages,stages)
                self.assertFalse(getattr(self.e,INTERRUPTS.KEY)['loans'])
                self.e.end_of_turn(self.foe)
                self.e.start_of_turn(self.new)
                self.assertEqual(self.new.budget['standard'],0)
                self.assertTrue(TURN.spend(self.e,self.new,'shift','actual remaining ordinary movement action'))
                self.e.end_of_turn(self.new);self.e.end_round()


if __name__=='__main__':unittest.main()
