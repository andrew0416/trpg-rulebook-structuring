"""C03-129's explicit GM inputs reach real native command and lifetime owners.

Classification and control rulings here are labeled GM examples, not invented
official species metadata or item rules. Static acquisition is reused from C128.
"""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'input').is_dir():ROOT = Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0] = [str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine, Rules, Combatant
from builder import build_pokemon, build_trainer
import test_book_heir as HEIR
import test_core_pack_mon as PACK_FIXTURE
import common_checks as C
import legendary_commands as LEGENDARY
import pokemon_activities as ACTIVITIES
import pokemon_party as PARTY
import trainer_feature_acquisition as FEATURES
import world_entities as WORLD
import items as ITEMS
import effect_lifetime_policy as LIFETIMES


class BookLegendaryTrainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r = Rules(ROOT,ruleset='core')

    add = HEIR.BookHeirTests.add
    equip = HEIR.BookHeirTests.equip
    turn = HEIR.BookHeirTests.turn
    activate = HEIR.BookHeirTests.activate
    setUp = HEIR.BookHeirTests.setUp
    command = HEIR.BookHeirTests.command
    force = HEIR.BookHeirTests.force
    cost_state = HEIR.BookHeirTests.cost_state
    acquire = HEIR.BookHeirTests.acquire
    trainer = HEIR.BookHeirTests.trainer
    active = HEIR.BookHeirTests.active

    def classify(self,kind='worldly_legendary',pokemon=None):
        return self.e.gm.observe_legendary_classification(pokemon or self.p,kind,
            source='gm/example-classification',reason='GM example for this actual individual and species; not stock species data')

    def battle(self):
        self.e.begin_encounter([self.t,self.p,self.q]);self.turn(self.p)

    def qualify(self):return self.e.gm.legendary_qualification(self.p)

    def acquire_legendary(self,trainer=None,request='legendary/acquire'):
        return self.acquire(LEGENDARY.FEATURE,trainer=trainer,request=request)

    def recognize(self,trainer=None):
        return self.e.gm.observe_legendary_recognition(self.p,trainer or self.t,True,
            source='gm/example-recognition',reason='GM observed this individual recognizing exactly this trainer')

    def tool(self,uid='control-object'):
        WORLD.register_object(self.e,uid,owner_id=self.t.entity_id,weight_kg=1,
            location={'kind':'unknown'},reason='GM example physical prop; no official control effect claimed')
        self.e.gm.set_carried_objects(self.t,[{'id':uid,'weight_kg':1}],reason='actual GM example user carries the prop')
        return uid

    def ruling(self,**changes):
        row = {'authority':'gm_ruling','source':'gm/example-control-effect',
            'reason':'Explicit GM example: waive only C129 penalty for one declared obedience decision; no other rule bypass',
            'effect':'waive_c129_penalty','use':'carried_by_user','cost':'none','lifetime':{'commands':1}}
        row.update(changes);return row

    def apply_tool(self,identity='control/application',uid='control-object',ruling=True,**changes):
        options = dict(user=self.t,instance_id=uid,application_id=identity,target=self.q,move_id='struggle',
            applied=True,source='gm/example-application',reason='GM observed the actual prop applied to this exact Pokemon and command',
            ruling=self.ruling() if ruling is True else ruling)
        options.update(changes)
        return self.e.gm.observe_legendary_control(self.p,**options)

    def controls(self):return self.p.spec[LEGENDARY.KEY]['controls']

    def test_explicit_scope_unknown_blocks_all_trainer_entries_without_cost_and_ordinary_is_not_applicable(self):
        self.assertEqual(self.qualify(),{'status':'not_evaluated'})
        self.classify('unknown');self.battle();before=self.cost_state()
        calls = (lambda:self.e.pokemon_activity(self.t,'command_loyalty',target=self.p),
            lambda:self.command(),lambda:self.e.use_move(self.p,self.q,'struggle',set_damage=True),
            lambda:self.e.use_move_on(self.p,self.q,'struggle',[self.t,self.p,self.q],set_damage=True))
        for call in calls:
            self.assertIsInstance(call(),C.PendingDecision);self.assertEqual(self.cost_state(),before)
        self.classify('ordinary');self.assertEqual(self.qualify(),{'status':'not_applicable'})
        self.assertTrue(self.e.pokemon_activity(self.t,'command_loyalty',target=self.p)['obeys'])
        self.assertEqual(self.command()['status'],'submitted')

    def test_worldly_legendary_missing_feat_uses_dc20_and_real_failure_then_gm_action(self):
        self.classify();self.battle();before=self.cost_state()
        self.e.use_move(self.p,self.q,'struggle',set_damage=True)
        self.e.use_move_on(self.p,self.q,'struggle',[self.t,self.p,self.q],set_damage=True)
        self.assertEqual(self.cost_state(),before)
        result=self.command(obedience_options={'fixed':[1]*4})
        self.assertEqual((result['status'],result['obedience']['check'].dc),('disobedient',20))
        self.assertEqual(self.cost_state(),before)
        self.e.rng.seed(5);hp=self.q.hp
        self.assertEqual(self.force(decision='action',target=self.q,move_id='struggle',set_damage=True)['status'],'submitted')
        self.assertLess(self.q.hp,hp);self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
        self.assertEqual(self.p.spec['loyalty'],5)

    def test_dc20_success_needs_no_invented_absolute_tool_gate_and_receipt_is_single_use(self):
        self.classify();self.battle();self.e.rng.seed(5);hp=self.q.hp
        out=self.command(obedience_options={'fixed':[5]*4})
        self.assertEqual(out['obedience']['check'].dc,20);self.assertLess(self.q.hp,hp)
        self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
        self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[])
        self.turn(self.p);before=self.cost_state();self.e.use_move(self.p,self.q,'struggle',set_damage=True)
        self.assertEqual(self.cost_state(),before);self.assertEqual(self.p.spec['loyalty'],5)

    def test_feature_qualifies_without_automatic_recognition_or_loyalty_and_current_loss_changes_next_command(self):
        self.classify();self.assertFalse(self.qualify()['qualified']);self.acquire_legendary()
        self.e.gm.set_level(self.t,19,reason='later GM level observation is not a new acquisition event')
        self.assertTrue(self.qualify()['qualified']);self.assertIsNone(self.qualify()['recognized'])
        self.e.gm.observe_loyalty(self.p,1,reason='GM retains the independent actual relationship')
        self.battle();out=self.command(obedience_options={'fixed':[1]*4})
        self.assertEqual(out['obedience']['check'].dc,8);self.force(decision='idle')
        self.e.retrain_trainer_source(self.t,LEGENDARY.FEATURE,request_id='legendary/remove',
            reason='actual retraining removes current qualification',gm_decision={'allowed':True,'reason':'GM reviewed'},retained_dependencies={})
        self.assertFalse(self.qualify()['qualified']);out=self.command(obedience_options={'fixed':[1]*4})
        self.assertEqual(out['obedience']['check'].dc,20);self.assertEqual(self.p.spec['loyalty'],1)

    def test_recognition_scope_and_other_legendary_do_not_create_ownership_or_override_missing_inputs(self):
        owner=self.p.spec['trainer_id'];before=deepcopy(self.p.spec.get('loyalty_relations'))
        self.recognize();self.assertIsInstance(self.qualify(),C.PendingDecision)
        self.assertEqual(self.p.spec['trainer_id'],owner);self.assertEqual(self.p.spec['loyalty_relations'],before)
        self.classify('other_legendary');self.acquire_legendary();self.battle();cost=self.cost_state()
        self.assertIsInstance(self.command(),C.PendingDecision);self.assertEqual(self.cost_state(),cost)
        self.classify();self.assertTrue(self.qualify()['recognized']);self.assertFalse(self.qualify()['grants_ownership'])
        other=self.trainer(30);self.assertIsNone(self.e.gm.legendary_qualification(self.p,other)['recognized'])

    def test_current_owner_transfer_recomputes_feature_and_does_not_transfer_recognition_or_tool(self):
        self.classify();self.acquire_legendary();self.recognize();other=self.trainer(30)
        PARTY.configure(self.e,self.t,mode='unlimited',reason='actual starting roster',roster=[self.p])
        PARTY.configure(self.e,other,mode='unlimited',reason='actual recipient roster',roster=[])
        self.tool();self.apply_tool()
        PARTY.transfer(self.e,self.t,target=self.p,new_owner=other,reason='actual ownership transfer',request_id='legendary/transfer')
        self.assertFalse(self.qualify()['qualified']);self.assertIsNone(self.qualify()['recognized'])
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e,self.p),0)
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        with self.assertRaises(ValueError):LEGENDARY.control_permission(self.e,other,self.p,self.q,'struggle','control/application')
        self.acquire_legendary(trainer=other,request='legendary/recipient')
        self.assertTrue(self.qualify()['qualified']);self.assertIsNone(ACTIVITIES.command_loyalty_value(self.e,self.p))

    def test_c129_has_no_pre_failure_gm_force_but_failed_command_survives_trainer_fainting(self):
        self.classify();self.battle();before=self.cost_state()
        with self.assertRaisesRegex(ValueError,'unresolved failed command'):self.force(decision='action',target=self.q,move_id='struggle')
        self.assertEqual(self.cost_state(),before)
        self.command(obedience_options={'fixed':[1]*4})
        self.e.gm.set_hp(self.t,value=0,reason='trainer fainted after command failure')
        with self.assertRaisesRegex(ValueError,'conscious trainer'):self.command()
        self.e.rng.seed(5);hp=self.q.hp
        self.assertEqual(self.force(decision='action',target=self.q,move_id='struggle',set_damage=True)['status'],'submitted')
        self.assertLess(self.q.hp,hp);self.assertEqual(self.p.budget['standard'],0)

    def test_c128_and_c129_penalties_remain_independent_and_scene_only_ends_mega(self):
        self.classify();self.acquire_legendary();self.active()
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e,self.p),0)
        self.acquire(request='heir/current');self.assertEqual(ACTIVITIES.command_loyalty_value(self.e,self.p),5)
        self.e.retrain_trainer_source(self.t,LEGENDARY.FEATURE,request_id='legendary/remove',
            reason='remove only legendary qualification',gm_decision={'allowed':True,'reason':'GM reviewed'},
            retained_dependencies={HEIR.RETRAINING.owned_source(self.e,self.t,HEIR.MEGA.HEIR):[]})
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e,self.p),0)
        self.recognize();self.e.end_scene()
        self.assertEqual(LEGENDARY.classification(self.e,self.p),'worldly_legendary')
        self.assertTrue(self.qualify()['recognized']);self.assertEqual(ACTIVITIES.command_loyalty_value(self.e,self.p),0)

    def test_explicit_gm_outcome_and_c128_authority_are_not_new_trainer_commands(self):
        self.classify();self.battle();self.command(obedience_options={'fixed':[1]*4})
        self.classify('unknown');self.e.rng.seed(5);hp=self.q.hp
        self.assertEqual(self.force(decision='action',target=self.q,move_id='struggle',set_damage=True)['status'],'submitted')
        self.assertLess(self.q.hp,hp);self.assertNotIn('pending_disobedience',self.p.spec)
        self.setUp();self.classify('unknown');self.active();self.e.rng.seed(5);hp=self.q.hp
        self.assertEqual(self.force(decision='action',target=self.q,move_id='struggle',set_damage=True)['status'],'submitted')
        self.assertLess(self.q.hp,hp);self.assertEqual(self.p.budget['standard'],0)

    def test_gm_native_refusal_keeps_pending_but_a_real_miss_finishes_the_failed_command(self):
        self.classify();self.battle();self.command(obedience_options={'fixed':[1]*4})
        import turn as TURN
        self.assertTrue(TURN.spend(self.e,self.p,'standard','actual prior native action'))
        before=self.cost_state()
        self.assertEqual(self.force(decision='action',target=self.q,move_id='struggle',set_damage=True)['status'],'refused')
        self.assertIn('pending_disobedience',self.p.spec);self.assertEqual(self.cost_state(),before)
        self.turn(self.p);self.e.rng.seed(1);hp=self.q.hp
        out=self.force(decision='action',target=self.q,move_id='struggle',situational=-100,set_damage=True)
        self.assertEqual((out['status'],out['move_result']),('submitted',0));self.assertEqual(self.q.hp,hp)
        self.assertNotIn('pending_disobedience',self.p.spec)
        self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))

    def test_gm_real_move_continuation_resumes_its_existing_completion_without_another_attack(self):
        self.p=self.add(build_pokemon(self.r,'리자몽',40,name='actual strength user',
            moves=['몸통박치기','괴력'],abilities=[],extra={'trainer_id':self.t.entity_id},pos=(2,1)))
        self.q=self.add(build_pokemon(self.r,'파오리',100,name='actual durable continuation target',
            moves=[],abilities=[],wild=True,side='wild',pos=(3,1)))
        self.e.gm.observe_loyalty(self.p,5,reason='actual relationship for this Pokemon')
        self.classify();self.battle();self.command(obedience_options={'fixed':[1]*4});self.e.rng.seed(1)
        options=dict(decision='action',target=self.q,move_id='move/괴력',situational=100,set_damage=True)
        out=self.force(**options);self.assertIsInstance(out,C.PendingDecision)
        pending=deepcopy(self.p.spec['pending_disobedience']['gm_resolution'])
        self.assertEqual(len(pending['completion_ids']),1)
        self.assertEqual((self.p.move_uses['move/괴력'],self.p.budget['standard']),(1,0))
        identifiers=[a.entity_id for a in (self.t,self.p,self.q)]
        self.e.gm.restore(self.e.gm.snapshot())
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        self.t,self.p,self.q=(WORLD.actor_index(self.e)[uid] for uid in identifiers)
        options['target']=self.q
        before=self.cost_state();self.assertIsInstance(self.force(**options),C.PendingDecision)
        self.assertEqual(self.cost_state(),before)
        import maneuver_grants as MANEUVERS
        receipt=next(row for row in self.e._effect_dispatch_receipts.values() if row.get('status')=='awaiting_input')
        MANEUVERS.resolve(self.e,self.p,receipt['result'].grant_id,accept=False)
        self.assertEqual(self.e._move_completions[pending['completion_ids'][0]]['phase'],'complete')
        self.e.gm.set_move(self.p,'move/괴력',add=False,reason='GM observed later forgetting after this native action completed')
        self.assertNotIn('move/괴력',{self.e.r.move_id(mid) for mid in self.p.moves})
        self.assertEqual(self.force(**options)['status'],'submitted')
        self.assertNotIn('pending_disobedience',self.p.spec);self.assertEqual(self.cost_state(),before)

    def test_gm_continuation_rejects_empty_duplicate_and_older_native_completion_through_restore_validators(self):
        self.p=self.add(build_pokemon(self.r,'리자몽',40,name='actual repeated strength user',
            moves=['몸통박치기','괴력'],abilities=[],extra={'trainer_id':self.t.entity_id},pos=(2,1)))
        self.q=self.add(build_pokemon(self.r,'파오리',100,name='actual durable reference target',
            moves=[],abilities=[],wild=True,side='wild',pos=(3,1)))
        self.e.gm.observe_loyalty(self.p,5,reason='actual repeated user relationship')
        self.battle();self.e.rng.seed(1)
        self.e.use_move(self.p,self.q,'move/괴력',situational=100,set_damage=True)
        import maneuver_grants as MANEUVERS
        import resolution_transaction as TX
        receipt=next(row for row in self.e._effect_dispatch_receipts.values() if row.get('status')=='awaiting_input')
        MANEUVERS.resolve(self.e,self.p,receipt['result'].grant_id,accept=False)
        old=next(iter(self.e._move_completions));self.assertEqual(self.e._move_completions[old]['phase'],'complete')
        self.turn(self.p)
        import frequency as FREQ
        self.assertFalse(FREQ.move_allowed(self.e,self.p,'move/괴력',outside_combat=False)[0])
        self.turn(self.p)  # The actual intervening turn satisfies Strength's every-other-turn source.
        self.assertTrue(FREQ.move_allowed(self.e,self.p,'move/괴력',outside_combat=False)[0])
        self.classify();self.command(obedience_options={'fixed':[1]*4});self.e.rng.seed(1)
        self.assertIsInstance(self.force(decision='action',target=self.q,move_id='move/괴력',situational=100,set_damage=True),C.PendingDecision)
        resolution=self.p.spec['pending_disobedience']['gm_resolution'];actual=resolution['completion_ids'][0]
        original=deepcopy(self.e.export_state())
        for changed,pattern in (([],'nonempty distinct'),([actual,actual],'nonempty distinct'),([old],'own actual producer')):
            with self.subTest(completions=changed):
                before=deepcopy(self.e.export_state())
                value=deepcopy(resolution);value['completion_ids']=changed
                value['sha256']=TX.request_fingerprint({k:v for k,v in value.items() if k!='sha256'})
                if changed==[actual,actual]:
                    with self.assertRaisesRegex(ValueError,pattern):ACTIVITIES._validate_gm_resolution(self.p,value)
                elif not changed:
                    name=self.e.gm.snapshot('invalid-gm-continuation')
                    saved=self.e.gm.snapshots[name]['combatants'][id(self.p)]['spec']['pending_disobedience']['gm_resolution']
                    saved['completion_ids'][:]=changed;saved['sha256']=value['sha256']
                    before=deepcopy(self.e.export_state())  # Keep the native snapshot log; only a rejected restore must be inert.
                    with self.assertRaisesRegex(ValueError,pattern):self.e.gm.restore(name)
                else:
                    invalid=deepcopy(original)
                    node=next(n for n in invalid['nodes'].values() if n['kind']=='dict' and ['id',resolution['id']] in n['items'])
                    ref=next(v for k,v in node['items'] if k=='completion_ids')
                    invalid['nodes'][ref['$ref']]['items']=list(changed)
                    next(pair for pair in node['items'] if pair[0]=='sha256')[1]=value['sha256']
                    seen=[];validate=ACTIVITIES.validate_disobedience_world
                    def observe_actual_rejection(engine,actors):
                        try:return validate(engine,actors)
                        except ValueError as exc:
                            seen.append(str(exc));raise
                    with patch.object(ACTIVITIES,'validate_disobedience_world',side_effect=observe_actual_rejection):
                        with self.assertRaisesRegex(ValueError,'world reference integrity: pokemon_entity_state'):
                            Engine.import_state(Rules(ROOT,ruleset='core'),invalid)
                    self.assertEqual(seen,['GM resolution requires its own actual producer completion'])
                self.assertEqual(self.e.export_state(),before)

    def test_gm_native_interruption_is_terminal_and_never_replays_or_claims_completion(self):
        self.classify();self.battle();self.command(obedience_options={'fixed':[1]*4});self.e.rng.seed(1)
        import post_resolution_stage_effects as POST_STAGE
        with patch.object(POST_STAGE,'apply_completion',side_effect=ValueError('actual late native completion failure')):
            with self.assertRaisesRegex(ValueError,'late native completion'):
                self.force(decision='action',target=self.q,move_id='struggle',situational=100,set_damage=True)
        resolution=self.p.spec['pending_disobedience']['gm_resolution'];uid=resolution['completion_ids'][0]
        self.assertEqual(self.e._move_completions[uid]['phase'],'interrupted')
        self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
        before=self.cost_state()
        out=self.force(decision='action',target=self.q,move_id='struggle',situational=100,set_damage=True)
        self.assertEqual(out['status'],'interrupted');self.assertEqual(self.e._move_completions[uid]['phase'],'interrupted')
        self.assertNotIn('pending_disobedience',self.p.spec);self.assertEqual(self.cost_state(),before)

    def test_actual_species_source_and_actor_binding_prevent_stale_observation_reuse(self):
        self.classify();self.recognize();self.battle()
        self.p.spec['species']=self.q.spec['species']
        self.assertIsInstance(self.command(),C.PendingDecision)
        self.classify();self.assertIsNone(self.qualify()['recognized'])
        with self.assertRaisesRegex(ValueError,'^distinct actors share identity:'):
            self.e.gm.observe_legendary_classification(copy(self.p),'ordinary',source='gm/example',reason='clone is not actual')
        original=self.e.r._selected_rule
        with patch.object(self.e.r,'_selected_rule',side_effect=lambda uid,**kw:'feat/other' if uid==LEGENDARY.FEATURE else original(uid,**kw)):
            with self.assertRaisesRegex(ValueError,'selected static Feature'):self.command()
        with patch.dict(FEATURES.STATIC_SOURCE,sha256='0'*64):
            with self.assertRaisesRegex(ValueError,'source changed'):self.command()

    def test_missing_tool_effect_application_and_unsupported_policy_stay_pending_without_native_cost(self):
        self.classify();self.tool()
        for identity,ruling,applied in (('missing',None,True),('unapplied',self.ruling(),False),
                ('unknown-effect',self.ruling(effect='obey_everything'),True),
                ('unknown-lifetime',self.ruling(lifetime={'invented':True}),True)):
            self.apply_tool(identity,ruling=ruling,applied=applied)
        self.battle();before=self.cost_state()
        for identity in self.controls():
            self.assertIsInstance(self.command(control_application=identity),C.PendingDecision)
            self.assertEqual(self.cost_state(),before)
        self.assertEqual(ACTIVITIES.command_loyalty_value(self.e,self.p),0)
        with self.assertRaises(ValueError):self.apply_tool('absent',uid='not-real')
        other=self.trainer(30)
        with self.assertRaisesRegex(ValueError,'actual current trainer'):self.apply_tool('foreign-user',user=other)
        self.e.gm.set_carried_objects(self.t,[],reason='actual prop released before another user picks it up')
        self.e.gm.set_carried_objects(other,[{'id':'control-object','weight_kg':1}],reason='a different actual trainer now carries the prop')
        with self.assertRaisesRegex(ValueError,'not carried'):self.apply_tool('foreign-carrier')
        self.assertEqual(self.cost_state(),before)

    def test_explicit_gm_tool_application_executes_exact_native_command_once_and_preserves_all_native_costs(self):
        self.classify();self.tool();self.e.begin_encounter([self.t,self.p,self.q]);self.turn(self.t)
        row=self.apply_tool(ruling=self.ruling(cost='swift'))
        self.assertEqual(self.t.budget['swift'],0);self.assertEqual(row['ruling']['authority'],'gm_ruling')
        self.assertEqual(self.apply_tool(ruling=self.ruling(cost='swift')),row)
        self.turn(self.p);self.e.rng.seed(5);hp=self.q.hp
        out=self.command(control_application='control/application')
        self.assertIsNone(out['obedience']['check']);self.assertLess(self.q.hp,hp)
        self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.assertEqual(self.p.spec['loyalty'],5);self.assertFalse(self.qualify()['qualified'])
        self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[])
        self.turn(self.p);before=self.cost_state()
        with self.assertRaisesRegex(ValueError,'ended or consumed'):self.command(control_application='control/application')
        self.assertEqual(self.cost_state(),before)
        self.e.use_move(self.p,self.q,'struggle',set_damage=True);self.assertEqual(self.cost_state(),before)

    def test_tool_does_not_waive_actual_loyalty_or_c128_and_exact_target_is_required(self):
        self.classify();self.tool();self.apply_tool();self.battle();before=self.cost_state()
        with self.assertRaisesRegex(ValueError,'different user or exact command'):
            self.e.pokemon_activity(self.t,'command_move',pokemon=self.p,target=self.t,move_id='struggle',control_application='control/application')
        self.assertEqual(self.cost_state(),before)
        self.e.gm.observe_loyalty(self.p,1,reason='actual independent relationship')
        out=self.command(control_application='control/application',obedience_options={'fixed':[1]*4})
        self.assertEqual(out['obedience']['check'].dc,8);self.assertEqual(out['status'],'disobedient')
        self.assertEqual(self.controls()['control/application']['uses'],1)
        self.setUp();self.classify();self.tool();self.apply_tool();self.active()
        out=self.command(control_application='control/application',obedience_options={'fixed':[1]*4})
        self.assertEqual(out['obedience']['check'].dc,20);self.assertEqual(out['status'],'disobedient')

    def test_controlled_command_keeps_native_intercept_wait_and_resumes_once_after_both_restores(self):
        import move_defense_reactions as DEFENSE
        import passive_events as PASSIVE
        from grid import Grid
        for index,use in enumerate((True,False)):
            with self.subTest(intercept=use):
                if index:self.setUp()
                self.classify();self.tool();self.e.grid=Grid(12,12)
                interceptor=self.add(build_trainer(self.r,'controlled command interceptor',30,
                    dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
                    skills={'육상':'달인'},extra={'pos':(3,4),'side':'wild',
                    'movement':{'land':8},'movement_basis':'current','abilities':[]}))
                self.e.begin_encounter([self.t,self.p,self.q,interceptor]);self.turn(self.t)
                self.apply_tool(ruling=self.ruling(cost='swift'))
                self.assertEqual(self.t.budget['swift'],0);self.turn(self.p)
                self.e.watch_move_defense(self.q,[{'actor_id':interceptor.entity_id,
                    'source':DEFENSE.MELEE}],reason='actual controlled command target defense')
                hp=(self.q.hp,interceptor.hp);before=set(getattr(self.e,'_move_completions',{}))
                with patch.object(type(self.e),'d20',new=lambda e:20):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        self.command(control_application='control/application')
                event=self.e._passive_pending;self.assertIsNotNone(event)
                self.assertEqual((self.q.hp,interceptor.hp),hp)
                self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
                self.assertEqual(self.controls()['control/application']['uses'],1)
                self.assertEqual(self.controls()['control/application']['status'],'closed')
                self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[])
                identities=[a.entity_id for a in (self.t,self.p,self.q,interceptor)]
                self.e.gm.restore(self.e.gm.snapshot())
                self.assertEqual(self.e._passive_pending,event)
                self.e=Engine.import_state(Rules(ROOT,ruleset='core'),
                    json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
                self.t,self.p,self.q,interceptor=(WORLD.actor_index(self.e)[uid] for uid in identities)
                self.assertEqual(self.e._passive_pending,event)
                options={'path':[(3,4),(3,3),(3,2),(3,1)],'skill':'육상','mode':'land',
                    'shove_destination':[4,1],'roll_options':{'fixed':[6]*6}} if use else None
                self.e.choose_move_defense(event,interceptor,use=use,options=options,
                    reason='actual waiting controlled command defense choice')
                self.assertIsNone(self.e._passive_pending)
                received=interceptor if use else self.q
                untouched=self.q if use else interceptor
                self.assertLess(received.hp,hp[1 if use else 0])
                self.assertEqual(untouched.hp,hp[0 if use else 1])
                completion=[row for key,row in self.e._move_completions.items() if key not in before]
                self.assertEqual(len(completion),1);self.assertEqual(completion[0]['phase'],'complete')
                self.assertEqual(set(completion[0]['received']),{received.entity_id})
                self.assertEqual(self.controls()['control/application']['uses'],1)
                self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
                self.assertEqual((self.p.spec['loyalty'],self.qualify()['qualified']),(5,False))
                paid=deepcopy((self.e.rng.getstate(),self.p.move_uses,self.p.budget,
                    self.q.hp,interceptor.hp,self.controls()))
                with self.assertRaises(ValueError):
                    self.e.choose_move_defense(event,interceptor,use=use,options=options,
                        reason='same completed defense cannot replay')
                PASSIVE.deliver(self.e,event)
                self.assertEqual((self.e.rng.getstate(),self.p.move_uses,self.p.budget,
                    self.q.hp,interceptor.hp,self.controls()),paid)
                self.assertEqual(set(self.e._move_completions)-before,{completion[0]['id']})

    def test_controlled_command_rejects_non_native_wait_and_rolls_back_consumed_prefix(self):
        import passive_events as PASSIVE
        import heavy_injury_adapter as HEAVY
        self.classify();self.tool();self.apply_tool();self.battle()
        before=deepcopy(self.e.export_state())
        for error in (ValueError('actual command failure'),
                      PASSIVE.PassiveEventPending('absent-event'),HEAVY.HeavyPending('absent-event')):
            with self.subTest(error=type(error).__name__):
                with patch.object(type(self.e),'use_move',side_effect=error):
                    with self.assertRaises(type(error)):
                        self.command(control_application='control/application')
                self.assertEqual(self.e.export_state(),before)
        self.assertEqual(self.controls()['control/application']['uses'],0)

    def test_tool_lifetime_reuses_scene_duration_and_explicit_end_without_changing_classification(self):
        for lifetime,ending in (({'commands':None,'until':'scene_end'},'scene'),
                ({'commands':None,'duration':{'seconds':2}},'duration'),({'commands':3},'explicit')):
            with self.subTest(lifetime=lifetime):
                self.setUp();self.classify();self.recognize();self.tool();self.apply_tool(ruling=self.ruling(lifetime=lifetime))
                if ending=='scene':self.e.end_scene()
                elif ending=='duration':
                    started=self.e.elapsed_seconds;self.e.advance_time(10,[self.t,self.p,self.q])
                    self.assertEqual(self.controls()['control/application']['ended_at'],started+2)
                else:self.e.gm.end_legendary_control(self.p,'control/application',reason='GM observed the selected effect end')
                self.assertEqual(self.controls()['control/application']['status'],'closed')
                self.assertEqual(LEGENDARY.classification(self.e,self.p),'worldly_legendary');self.assertTrue(self.qualify()['recognized'])
        self.setUp();self.classify();self.tool();self.apply_tool(ruling=self.ruling(lifetime={'commands':2,'until':'scene_end'}));self.battle()
        self.command(control_application='control/application');self.assertEqual(self.controls()['control/application']['status'],'live')
        self.turn(self.p);self.command(control_application='control/application');self.assertEqual(self.controls()['control/application']['status'],'closed')

    def test_actual_pokemon_equipped_tool_binds_its_own_physical_owner_and_native_command(self):
        self.classify()
        row=self.apply_tool(uid='stone',ruling=self.ruling(use='equipped_by_pokemon'))
        self.assertEqual(row['object_owner_id'],self.p.entity_id)
        self.battle();self.e.rng.seed(5);hp=self.q.hp
        out=self.command(control_application='control/application')
        self.assertIsNone(out['obedience']['check']);self.assertLess(self.q.hp,hp)
        self.assertEqual((self.p.move_uses['struggle'],self.p.budget['standard']),(1,0))
        self.assertEqual(self.controls()['control/application']['status'],'closed')

    def test_tool_physical_loss_equipment_suppression_and_environment_end_actual_effect(self):
        self.classify();self.tool();self.apply_tool()
        self.e.gm.set_carried_objects(self.t,[],reason='actual control prop released')
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.e.gm.set_carried_objects(self.t,[{'id':'control-object','weight_kg':1}],reason='same trainer recovered the real prop')
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.setUp();self.classify();self.apply_tool(uid='ring',ruling=self.ruling(use='equipped_by_user'))
        self.e.gm.observe_environmental_item(self.t,'ring',event_id='control/frozen',condition='frozen',
            source='gm/example-exposure',reason='actual example tool frozen',exposed=True)
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.setUp();self.classify();self.apply_tool(uid='ring',ruling=self.ruling(use='equipped_by_user'))
        ITEMS.unregister_item(self.e,self.t,'메가링')
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.battle();before=self.cost_state()
        with self.assertRaisesRegex(ValueError,'ended or consumed'):self.command(control_application='control/application')
        self.assertEqual(self.cost_state(),before)
        self.setUp();self.classify();self.apply_tool(uid='ring',ruling=self.ruling(use='equipped_by_user'))
        self.e.start_round([self.t,self.p,self.q])
        import field_effects as FIELD
        FIELD.install(self.e,self.q,self.r.move_mech('move/매직룸')[0]['effects_exec'][0],'move/매직룸')
        LIFETIMES.boundary(self.e,'reconcile')
        self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.assertEqual(self.e._physical_objects['ring']['equipped_by'],self.t.entity_id)

    def test_observations_and_actual_tool_references_survive_both_restores_with_lifetime_and_command_still_live(self):
        self.classify();self.recognize();self.tool();self.apply_tool(ruling=self.ruling(lifetime={'commands':2,'until':'scene_end'}))
        identifiers=[a.entity_id for a in (self.t,self.p,self.q)];expected=deepcopy(self.p.spec[LEGENDARY.KEY])
        self.e.gm.restore(self.e.gm.snapshot())
        self.t,self.p,self.q=(WORLD.actor_index(self.e)[uid] for uid in identifiers)
        self.assertEqual(self.p.spec[LEGENDARY.KEY],expected)
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        self.t,self.p,self.q=(WORLD.actor_index(self.e)[uid] for uid in identifiers)
        self.assertEqual(self.p.spec[LEGENDARY.KEY],expected);self.battle();self.e.rng.seed(5)
        self.assertEqual(self.command(control_application='control/application')['status'],'submitted')
        self.assertEqual(self.controls()['control/application']['uses'],1)
        self.e.end_scene();self.assertEqual(self.controls()['control/application']['status'],'closed')
        self.assertTrue(self.qualify()['recognized']);self.assertTrue(self.e.validate_state()['valid'])

    def test_pack_mon_and_unowned_autonomous_move_retain_their_separate_actual_authority(self):
        case=PACK_FIXTURE.CorePackMonTests();case.r=case.rules=self.r;case.world()
        case.e.gm.observe_legendary_classification(case.p,'unknown',source='gm/example-scope',reason='unknown classification does not repeal Pack Mon authority')
        out=case.command();self.assertEqual(out['status'],'submitted')
        self.assertEqual(out['obedience']['source'],'capability/우두머리')
        self.assertEqual(case.p.budget['standard'],0)
        self.classify('unknown',pokemon=self.q);self.e.begin_encounter([self.t,self.p,self.q]);self.turn(self.q)
        hp=self.p.hp;self.e.rng.seed(5);self.e.use_move(self.q,self.p,'struggle',set_damage=True)
        self.assertLess(self.p.hp,hp);self.assertIsNone(self.q.spec.get('trainer_id'))


if __name__=='__main__':unittest.main()
