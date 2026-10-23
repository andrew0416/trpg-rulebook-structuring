"""Unown sample connections to actual native actions, hits and completions.

The general source/frequency/transaction/arithmetic owners retain their existing
guarantees. These cases exercise only this sample and its changed Shield seam.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
import test_category2_progression_state as _fixture_progression
import unown_imbuement as U
import world_entities as W
import passive_events as P
import move_defense_reactions as D
import move_completion as C
import frequency as F
import state_codec as CODEC


class UnownImbuementTests(unittest.TestCase):
    setUpClass=classmethod(_fixture_progression.ProgressionStateTests.setUpClass.__func__)
    add=_fixture_progression.ProgressionStateTests.add

    def setUp(self):
        _fixture_progression.ProgressionStateTests.setUp(self)
        self.e.grid=Grid(8,8)
        self.a.pos=(2,2)
        for name in ('막치기','물대포','울음소리','방어'):
            self.e.gm.set_move(self.a,'move/'+name,reason='observed known Move before native use')
        self.t=self.add(build_trainer(self.r,'actual-target',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
            moves=['move/막치기','move/울음소리','move/치유파동'],skills={'집중':3},extra={'items':{}}))
        self.t.pos=(3,2);self.t.side='opponent'
        self.other=self.add(build_trainer(self.r,'actual-second-target',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],skills={'집중':3},extra={'items':{}}))
        self.other.pos=(2,3);self.other.side='opponent'

    def adopt(self,actor=None,clusters=5):
        return U.adopt(self.e,actor or self.a,clusters,gm_id='actual GM',reason='explicit observed implantation')

    def begin(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.gm.everyone)
        self.e.start_of_turn(actor,initiative_count=20)

    def hp(self,actor=None,*,ty='불꽃',cls='물리',request='sample-hp',roll=18):
        actor=actor or self.a
        with patch.object(self.e,'d20',return_value=roll):
            return U.use_hidden_power(self.e,actor,self.t,self.e.gm.everyone,
                chosen_type=ty,damage_class=cls,request_id=request,reason='actual chosen sample attack')

    def boost(self,*,request='sample-accuracy',move='move/막치기',roll=2):
        with patch.object(self.e,'d20',return_value=roll):
            return U.boost_attack(self.e,self.a,self.t,move,self.e.gm.everyone,
                request_id=request,reason='actual selected attack')

    def waiting(self,*,move='move/막치기',roll=18):
        with patch.object(self.e,'d20',return_value=roll):
            with self.assertRaises(P.PassiveEventPending):
                self.e.use_move(self.t,self.a,move,set_damage=True)
        event=self.e._passive_pending
        self.assertIsNotNone(event)
        return event

    def choose(self,event,*,use=True):
        return D.choose(self.e,event,self.a,use=use,reason='actual native hit response')

    def valid(self):
        result=self.e.validate_state()
        self.assertTrue(result['valid'],result['issues'])

    def snap(self):
        actors=self.e.gm.everyone
        return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),
            [vars(actor) for actor in actors],self.e.log_lines),
            {id(self.r):self.r,**{id(actor):actor for actor in actors}})

    def burn(self,actor=None):
        return U.state(actor or self.a)['burns'][-1]

    def source_completion(self,actor=None):
        return self.e._move_completions[self.burn(actor)['completion_ids'][0]]

    def test_explicit_trainer_and_pokemon_adoption_boundaries(self):
        self.assertEqual(U.active_count(self.a),0)
        self.assertNotIn(U.KEY,self.a.spec)
        p=self.add(build_pokemon(self.r,'이브이',20,moves=[],abilities=[],
            extra={'trainer_id':self.a.entity_id,'items':{}}))
        self.e.gm.observe_loyalty(p,6,reason='observed actual trainer relationship')
        self.assertEqual(p.spec['species'],'pokemon/이브이')
        self.assertEqual(p.spec['trainer_id'],self.a.entity_id)
        self.adopt(p,1);self.adopt(self.a,5)
        self.assertEqual((U.active_count(p),U.active_count(self.a)),(1,5))
        for value in (0,6,True,1.5):
            before=self.snap()
            with self.assertRaises(ValueError):self.adopt(self.t,value)
            self.assertEqual(before,self.snap())
        with self.assertRaises(ValueError):self.adopt(self.a,5)
        with self.assertRaises(ValueError):self.adopt(Combatant(self.r,deepcopy(p.spec)),1)
        self.valid()

    def test_passive_contributions_reach_native_accuracy_and_evasion(self):
        base={kind:self.a.evasion(kind) for kind in ('물리','특수','변화')}
        self.assertFalse(self.e.accuracy_check(self.a,self.t,self.r.move('move/할퀴기'),fixed_roll=2)[0])
        self.adopt()
        self.assertTrue(self.e.accuracy_check(self.a,self.t,self.r.move('move/할퀴기'),fixed_roll=2)[0])
        for kind in base:self.assertEqual(self.a.evasion(kind),min(9,base[kind]+5))
        self.assertFalse(U.state(self.a)['burns'])
        U.set_active(self.e,self.a,False,reason='sample temporarily disabled')
        for kind in base:self.assertEqual(self.a.evasion(kind),base[kind])
        U.set_active(self.e,self.a,True,reason='same implantation reenabled')
        self.assertEqual(U.active_count(self.a),5)
        self.valid()

    def test_hidden_power_uses_actual_burst_class_type_and_swift_once(self):
        self.adopt();self.begin(self.a)
        original=deepcopy(self.r.move(U.HP));known=list(self.a.moves)
        captured=[];native=Engine.roll_damage
        def observe(engine,actor,target,move,*args,**options):
            if move['id']==U.HP:captured.append((target.entity_id,move['type'],move['class']))
            return native(engine,actor,target,move,*args,**options)
        before=(self.t.hp,self.other.hp);budget=dict(self.a.budget)
        with patch.object(Engine,'roll_damage',observe):dealt=self.hp()
        row=self.source_completion()
        self.assertEqual(set(row['results']),{self.t.entity_id,self.other.entity_id})
        self.assertEqual(set(captured),{(self.t.entity_id,'불꽃','물리'),(self.other.entity_id,'불꽃','물리')})
        self.assertGreater(dealt,0)
        self.assertEqual(dealt,before[0]-self.t.hp+before[1]-self.other.hp)
        self.assertEqual(self.a.move_uses[U.HP],1)
        self.assertEqual((self.a.budget['swift'],self.a.budget['standard']),
            (budget['swift']-1,budget['standard']))
        self.assertEqual(self.a._action_history,['swift'])
        self.assertEqual(U.active_count(self.a),4)
        self.assertEqual(self.burn()['completion_ids'],[row['id']])
        self.assertEqual(self.a.moves,known);self.assertEqual(self.r.move(U.HP),original)
        self.assertEqual(row['move']['damage_base'],6)
        self.valid()

    def test_hidden_power_per_use_choices_preserve_native_frequency_and_permanent_type(self):
        p=self.add(build_pokemon(self.r,'이브이',20,moves=[U.HP],abilities=[],
            extra={'trainer_id':self.a.entity_id,'items':{}}))
        p.pos=(3,3);self.e.gm.observe_loyalty(p,6,reason='actual commanded Pokemon')
        # Preserve the existing sheet observation used by the separate Prime
        # Unown member owner. This sample never rewrites that baseline.
        p.spec['hidden_power_type']='물'
        self.adopt(p,5);self.begin(p)
        self.hp(p,ty='노말',cls='특수',request='pokemon-first')
        row=self.source_completion(p)
        self.assertEqual((row['move']['type'],row['move']['class']),('노말','특수'))
        self.assertEqual(p.spec['hidden_power_type'],'물')
        self.begin(p);before=self.snap()
        with self.assertRaises(ValueError):self.hp(p,ty='전기',request='pokemon-too-soon')
        self.assertEqual(self.snap(),before)
        self.assertEqual(U.active_count(p),4)
        self.begin(p);self.hp(p,ty='전기',cls='물리',request='pokemon-third-turn')
        row=self.source_completion(p)
        self.assertEqual((row['move']['type'],row['move']['class']),('전기','물리'))
        self.assertEqual((U.active_count(p),p.move_uses[U.HP]),(3,2))
        self.assertEqual(p.spec['hidden_power_type'],'물')
        self.valid()

    def test_hidden_power_miss_consumes_before_accuracy_and_request_replay_once(self):
        self.adopt();self.begin(self.a)
        self.assertEqual(self.hp(roll=1),0)
        self.assertEqual(U.active_count(self.a),4)
        row=self.source_completion()
        self.assertFalse(any(result['hit'] for result in row['results'].values()))
        self.assertTrue(any('d20=1+4=' in str(line) for line in self.e.log_lines))
        before=self.snap();count=len(self.e._move_completions)
        self.assertEqual(self.hp(roll=18),0)
        self.assertEqual(self.snap(),before);self.assertEqual(len(self.e._move_completions),count)
        with self.assertRaises(ValueError):self.hp(ty='물')
        self.assertEqual(self.snap(),before)
        self.valid()

    def test_two_cluster_boost_binds_one_native_accuracy_group_and_no_later_attack(self):
        self.t.evasion_mod=3
        self.assertEqual((self.r.move('move/막치기')['ac'],self.t.evasion('물리')),(2,5))
        self.adopt();self.begin(self.a)
        self.assertGreater(self.boost(),0)
        row=self.source_completion()
        self.assertTrue(row['results'][self.t.entity_id]['hit'])
        self.assertTrue(any('d20=2+8=' in str(line) for line in self.e.log_lines))
        self.assertEqual((U.active_count(self.a),self.a._action_history),(3,['swift','standard']))
        before=self.snap();result=self.burn()['result']
        self.assertEqual(self.boost(roll=18),result);self.assertEqual(before,self.snap())
        self.begin(self.a)
        with patch.object(self.e,'d20',return_value=2):
            self.assertEqual(self.e.use_move(self.a,self.t,'move/막치기',set_damage=True),0)
        self.assertEqual(U.active_count(self.a),3)
        self.assertTrue(any('d20=2+3=' in str(line) for line in self.e.log_lines))
        # A new source use owns another native activation and Swift cost.
        self.begin(self.a);self.boost(request='second-actual-attack')
        self.assertEqual(U.active_count(self.a),1)
        with self.assertRaises(ValueError):self.boost(request='overdraw')
        self.valid()

    def test_action_denial_and_late_native_failure_roll_back_whole_combined_use(self):
        self.adopt();self.begin(self.a)
        self.e.use_move(self.a,self.t,'move/막치기',set_damage=True)
        before=self.snap()
        with self.assertRaises(ValueError):self.boost(request='no-native-standard')
        self.assertEqual(self.snap(),before)
        self.begin(self.a);before=self.snap();native=C.finish_target
        def fail_after_native(engine,*args,**options):
            native(engine,*args,**options)
            raise ValueError('injected after actual native completion')
        with patch.object(C,'finish_target',side_effect=fail_after_native):
            with self.assertRaisesRegex(ValueError,'after actual native'):self.hp()
        self.assertEqual(self.snap(),before)
        self.assertEqual(U.active_count(self.a),5)
        self.valid()

    def test_scene_only_refresh_keeps_burn_history_and_disabled_source_cannot_refund(self):
        self.adopt();self.begin(self.a);self.boost()
        self.e.end_of_turn(self.a);self.e.end_encounter()
        scene=F.state(self.a)['scene'];burns=deepcopy(U.state(self.a)['burns'])
        self.e.advance_time(24*3600)
        self.assertEqual(U.active_count(self.a),3)
        U.set_active(self.e,self.a,False,reason='explicit suppression')
        U.set_active(self.e,self.a,True,reason='same reservoir returns')
        self.assertEqual(U.active_count(self.a),3)
        self.e.end_scene()
        self.assertEqual(F.state(self.a)['scene'],scene+1)
        self.assertEqual(U.active_count(self.a),5)
        self.assertEqual(U.state(self.a)['burns'],burns)
        self.valid()

    def test_actual_hit_detect_spends_free_native_move_and_prevents_damage_and_effects(self):
        self.adopt();self.begin(self.a);self.begin(self.t)
        U.watch_detect(self.e,self.a,reason='optional actual-hit response')
        hp=self.a.hp;stages=dict(self.a.stages);budget=dict(self.a.budget)
        event=self.waiting(move='move/울음소리')
        self.assertEqual((U.active_count(self.a),self.a.hp,self.a.stages),(5,hp,stages))
        self.choose(event)
        self.assertEqual((self.a.hp,self.a.stages,self.a.budget),(hp,stages,budget))
        self.assertEqual((U.active_count(self.a),self.a.move_uses[U.DETECT]),(2,1))
        self.assertEqual(self.a._action_history,['free']);self.assertIsNone(self.a.shield)
        row=self.source_completion();self.assertEqual(row['phase'],'complete')
        self.assertEqual((row['move_id'],row['targets']),(U.DETECT,[self.a]))
        original=self.e._move_completions[self.e._passive_events[event]['completion_id']]
        self.assertFalse(original['results'][self.a.entity_id]['hit'])
        self.assertEqual(original['results'][self.a.entity_id]['dealt'],0)
        attempt=original['defense'][self.a.entity_id]['attempts'][0]
        self.assertTrue(U.validate_detect_attempt(self.e,self.e._passive_events[event],self.a,attempt))
        self.assertEqual(self.e._effect_dispatch_receipts[attempt['unown']['effect_receipt']]['status'],'completed')
        self.assertFalse(F.move_allowed(self.e,self.a,U.DETECT,outside_combat=False)[0])
        self.valid()

    def test_detect_does_not_spend_on_miss_natural_one_or_immunity(self):
        for roll,immune in ((1,False),(2,False),(18,True)):
            with self.subTest(roll=roll,immune=immune):
                self.setUp();self.adopt();self.begin(self.t)
                if immune:self.a.move_immune={'move/막치기'}
                U.watch_detect(self.e,self.a,reason='watch does not assert a hit')
                with patch.object(self.e,'d20',return_value=roll):
                    self.e.use_move(self.t,self.a,'move/막치기',set_damage=True)
                self.assertIsNone(self.e._passive_pending)
                self.assertEqual(U.active_count(self.a),5)
                self.assertFalse(U.state(self.a)['burns']);self.assertEqual(self.a.move_uses.get(U.DETECT,0),0)
                self.assertIn(D.WATCH,self.a.spec)
                self.valid()

    def test_detect_suppression_frequency_and_bypass_policy_do_not_invent_use(self):
        self.adopt();self.begin(self.t)
        U.watch_detect(self.e,self.a,reason='actual source watch')
        event=self.waiting();self.a.abilities_suppressed=True
        before=self.snap()
        with self.assertRaises(ValueError):self.choose(event)
        self.assertEqual(self.snap(),before);self.assertEqual(U.active_count(self.a),5)
        self.a.abilities_suppressed=False
        self.a.custom_conditions['move_lock']={'keyword':'방패'}
        before=self.snap()
        with self.assertRaisesRegex(ValueError,'native Detect Move entry unavailable'):self.choose(event)
        self.assertEqual(self.snap(),before);self.assertEqual(U.active_count(self.a),5)
        self.assertEqual(self.a.move_uses.get(U.DETECT,0),0)
        del self.a.custom_conditions['move_lock']
        self.choose(event,use=False)
        self.assertFalse(U.state(self.a)['burns'])
        # These source rows still have a separately unresolved disappearance
        # action. Reuse their reviewed bypass policy without executing it.
        for mid in ('move/고스트다이브','move/섀도다이브'):
            self.assertTrue(D._prohibited(self.e,self.r.move(mid),'shield'))
        self.begin(self.a)
        self.e.use_move(self.a,self.a,U.DETECT)
        self.assertEqual(self.a.move_uses[U.DETECT],1)
        with self.assertRaises(ValueError):U.watch_detect(self.e,self.a,reason='native Scene quota unchanged')
        self.assertEqual(U.active_count(self.a),5)
        self.valid()

    def test_detect_cold_pending_restore_and_redelivery_keep_actual_owner(self):
        self.adopt();self.begin(self.t);U.watch_detect(self.e,self.a,reason='cold actual native hit')
        event=self.waiting();hp=self.a.hp
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
        index=W.actor_index(self.e);self.a,self.t,self.other=(index[a.entity_id] for a in (self.a,self.t,self.other))
        self.assertEqual(self.e._passive_pending,event)
        self.e.gm.snapshot('unown-pending');self.choose(event)
        self.assertEqual(U.active_count(self.a),2)
        self.assertEqual(self.a.hp,hp)
        before=self.e.export_state()
        P.deliver(self.e,event)
        self.assertEqual(self.e.export_state(),before)
        self.e.gm.restore('unown-pending')
        index=W.actor_index(self.e);self.a,self.t,self.other=(index[a.entity_id] for a in (self.a,self.t,self.other))
        self.assertEqual(U.active_count(self.a),5);self.choose(event)
        self.assertEqual(U.active_count(self.a),2)
        self.valid()

        # The same native target-group continuation can itself be a sampled
        # Hidden Power. Restore resumes later Burst recipients with the same
        # chosen Type/class and one burn, without another learn prompt/cost.
        self.setUp();self.adopt();self.adopt(self.t,3);self.begin(self.a)
        U.watch_detect(self.e,self.t,reason='first actual Burst recipient')
        with self.assertRaises(P.PassiveEventPending):self.hp()
        event=self.e._passive_pending;other_hp=self.other.hp;target_hp=self.t.hp
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
        index=W.actor_index(self.e);self.a,self.t,self.other=(index[a.entity_id] for a in (self.a,self.t,self.other))
        D.choose(self.e,event,self.t,use=True,reason='actual first recipient Detect')
        self.assertEqual(self.t.hp,target_hp);self.assertLess(self.other.hp,other_hp)
        self.assertEqual((U.active_count(self.a),U.active_count(self.t)),(4,0))
        row=self.source_completion()
        self.assertEqual((row['phase'],row['move']['type'],row['move']['class']),('complete','불꽃','물리'))
        self.assertEqual(self.a.move_uses[U.HP],1)
        self.assertGreater(self.hp(),0)
        self.assertEqual(len(U.state(self.a)['burns']),1)
        self.valid()

    def test_detect_status_source_and_legacy_shield_changed_boundary(self):
        for incoming in ('move/울음소리','move/치유파동'):
            for source,expected in ((U.DETECT,False),('move/방어',True),(None,True)):
                with self.subTest(source=source,incoming=incoming):
                    self.setUp();self.begin(self.a)
                    if source:self.e.use_move(self.a,self.a,source)
                    else:D.hold_shield(self.e,self.a,deepcopy(U.SHIELD),{'engine':self.e})
                    if source==U.DETECT:
                        self.assertFalse(D.shield_allowed(self.e,self.t,self.a,self.r.move('move/고스트다이브')))
                    self.begin(self.t)
                    self.e.lose_hp(self.a,10,source='observed setup injury')
                    stages=dict(self.a.stages);hp=self.a.hp
                    with patch.object(self.e,'d20',return_value=18):
                        self.e.use_move(self.t,self.a,incoming)
                    changed=self.a.stages!=stages if incoming=='move/울음소리' else self.a.hp>hp
                    self.assertEqual(changed,expected)
                    self.assertEqual(self.a.shield is not None,expected)
                    self.valid()
        self.setUp();self.adopt();self.begin(self.t)
        self.e.lose_hp(self.a,10,source='observed setup injury')
        hp=self.a.hp
        U.watch_detect(self.e,self.a,reason='actual no-AC Move hit')
        event=self.waiting(move='move/치유파동');self.choose(event)
        self.assertEqual((self.a.hp,U.active_count(self.a)),(hp,2))
        self.valid()

    def test_source_actor_and_receipt_tamper_rejected_by_world_codec(self):
        self.adopt();self.begin(self.a);self.hp()
        original=deepcopy(U.state(self.a))
        for change in ('actor','source','amount','completion'):
            with self.subTest(change=change):
                self.a.spec[U.KEY]=deepcopy(original)
                row=self.a.spec[U.KEY]
                if change=='actor':row['adoption']['actor_id']=self.t.entity_id
                elif change=='source':row['adoption']['source_file']['sha256']='0'*64
                elif change=='amount':row['burns'][0]['intent']['amount']=2
                else:row['burns'][0]['completion_ids']=['move-complete:invented']
                self.assertFalse(self.e.validate_state()['valid'])
                with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
        self.a.spec[U.KEY]=original
        cold=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        actor=W.actor_index(cold)[self.a.entity_id]
        self.assertEqual(U.active_count(actor),4)
        self.assertEqual(U.state(actor),original)
        self.valid()

    def test_external_json_programs_bind_actual_sample_owners_through_existing_registry(self):
        # Use a fresh ordinary core profile; the package points at the actual
        # selected native sample and contains data only.
        self.r=Rules(ROOT,ruleset='core');self.setUp();self.begin(self.a)
        owner={'$actor':'actor'};target={'$actor':'target'}
        group=[owner,target,{'$actor':self.other.entity_id}]
        def step(identity,operation,**arguments):
            return {'id':identity,'operation':operation,'arguments':arguments}
        def run(identity,steps,actual_target=None):
            document={'schema':1,'id':'external/unown-'+identity,'variants':[{
                'rule_id':U.SOURCE,'source':deepcopy(U.SOURCE_FILE),'inputs':{},'values':{'operations':steps}}]}
            self.r.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[document]},ensure_ascii=False))
            loaded=self.r.source_policy_document(document['id'])
            with patch.object(self.e,'d20',return_value=18):
                result=self.e.execute_source_policy_operations(self.a,actual_target or self.t,loaded,
                    request_id='external/'+identity)
            self.assertEqual(result['status'],'PolicyOperationsCompleted')
            self.assertEqual(result['selected_id'],U.SOURCE)
            return loaded,result
        document,result=run('hp',[
            step('adopt','unown.adopt',actor=owner,clusters=5,gm_id='actual GM',reason='data-authored adoption'),
            step('hp','unown.hidden_power',actor=owner,target=target,targets=group,
                chosen_type='불꽃',damage_class='물리',request_id='external/native-hp',reason='data-authored native attack')])
        self.assertEqual(U.active_count(self.a),4)
        self.assertGreater(result['operation_results'][1]['result'],0)
        before=self.e.export_state()
        replay=self.e.execute_source_policy_operations(self.a,self.t,document,request_id='external/hp')
        self.assertTrue(replay['replayed']);self.assertEqual(self.e.export_state(),before)
        self.begin(self.a)
        run('accuracy',[step('boost','unown.accuracy',actor=owner,target=target,targets=group,
            move_id='move/막치기',request_id='external/native-accuracy',reason='data-authored selected attack')])
        self.assertEqual(U.active_count(self.a),2)
        run('watch',[
            step('adopt-target','unown.adopt',actor=target,clusters=5,gm_id='actual GM',reason='second actual implant'),
            step('watch','unown.detect_watch',actor=target,reason='data-authored actual-hit watch')],self.other)
        self.begin(self.t)
        hp=self.other.hp
        with patch.object(self.e,'d20',return_value=18):
            with self.assertRaises(P.PassiveEventPending):
                self.e.use_move(self.t,self.other,'move/막치기',set_damage=True)
        D.choose(self.e,self.e._passive_pending,self.other,use=True,reason='actual native hit after external watch')
        self.assertEqual((U.active_count(self.other),self.other.hp),(2,hp))
        self.valid()


if __name__=='__main__':unittest.main()
