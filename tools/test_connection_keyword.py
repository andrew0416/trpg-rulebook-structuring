"""C10-168 audit repair: the Connection Ability keyword (official PTU 1.05 Core p.310).

The Korean ch10:178 keeps only the static relation. The official text: upon gaining the
Ability the user learns the Move, forgetting another Move if necessary; the Move cannot be
forgotten through any means; with 1 Tutor Point the user may immediately take Advanced
Connection and avoid forgetting. Actual Ability gain (GM edit, natural milestone, source-owned or temporary) reaches advanced_connection.reconcile through the common state transition.
"""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from native_scenario_fixture import assert_rejected_unchanged
from builder import build_pokemon,build_trainer
from engine import Combatant,Engine,Rules
import advanced_connection as C,ability_transitions as A,move_state as M,state_codec as CODEC
import state_grants as G,world_entities as W

FULL=['튀어오르기','몸통박치기','바둥바둥','돌진','전광석화','방어']


class ConnectionKeywordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        previous=self.rules.rulings;self.rules.rulings=deepcopy(previous)
        self.addCleanup(setattr,self.rules,'rulings',previous)

    def pokemon(self,moves,tutor_points=4,abilities=(),species='잉어킹',level=20):
        self.e=Engine(self.rules,seed=902)
        # Rules-level GM answers are shared by every Engine of this class.
        self.e.rulings.answers=[row for row in self.e.rulings.answers if row['key']!=C.PROMPT]
        self.p=Combatant(self.rules,build_pokemon(self.rules,species,level,abilities=None if abilities is None else list(abilities),moves=moves,
                                                  extra={'tutor_points':tutor_points}))
        self.e.gm.add_combatant(self.p,pos=(0,0),side='party',reason='audit fixture')
        self.honey=A.ability_id(self.rules,'꿀도둑');self.bite=self.rules.move_id('벌레먹기')
        return self.p

    def known(self):return set(M.known(self.rules,self.p.spec))
    def gain(self):return self.e.gm.set_ability(self.p,'꿀도둑',reason='gained core Connection Ability')
    def answer(self,**option):
        self.e.rulings.add_answer(C.PROMPT,dict(actor_id=self.p.entity_id,ability=self.honey,**option),
                                  reason='explicit player Connection choice',scope='permanent')
    def snap(self):return CODEC.dump_engine(self.e)

    def test_gaining_connection_learns_linked_move(self):
        self.pokemon(['튀어오르기']);self.gain()
        self.assertIn(self.bite,self.known())
        record=self.p.spec['move_learning'][self.bite]
        self.assertEqual((record['method'],record['source'],record['paid_tp'],record['connection_ability']),
                         ('feature',C.KEYWORD,0,self.honey))
        self.assertEqual(M.describe(self.rules,self.p.spec)['classifications'][self.bite],'granted')
        self.assertEqual(self.p.spec['tutor_points'],4);self.assertFalse(C.records(self.p.spec))

    def test_common_permanent_ability_list_gain_learns_too(self):
        self.pokemon(['튀어오르기'])
        G.transition(self.e,self.p,lambda e,c:G.set_baseline(c,'abilities',[*c.spec['abilities'],'꿀도둑']))
        self.assertIn(self.bite,self.known())

    def test_connected_move_cannot_be_forgotten_by_any_permanent_list_path(self):
        self.pokemon(['벌레먹기','튀어오르기']);before=list(self.p.spec['moves']);self.gain()
        self.assertEqual(self.p.spec['moves'],before);self.assertNotIn(self.bite,self.p.spec.get('move_learning',{}))
        snap=self.snap()
        with self.assertRaisesRegex(ValueError,'cannot be forgotten'):
            self.e.gm.set_move(self.p,'벌레먹기',add=False,reason='attempt to forget bound move')
        with self.assertRaisesRegex(ValueError,'cannot be forgotten'):
            G.transition(self.e,self.p,lambda e,c:G.set_baseline(c,'moves',['튀어오르기']))
        self.assertEqual(self.snap(),snap)
        self.e.gm.set_move(self.p,'튀어오르기',add=False,reason='other moves stay forgettable')
        self.assertEqual(self.known(),{self.bite})

    def test_full_list_without_explicit_choice_rejects_atomically(self):
        self.pokemon(FULL);snap=self.snap()
        with self.assertRaisesRegex(ValueError,'explicit forgotten Move or immediate Advanced Connection'):self.gain()
        self.assertEqual(self.snap(),snap)

    def test_full_list_forget_choice_replaces_only_the_named_move(self):
        self.pokemon(FULL);self.answer(forget='튀어오르기');self.gain()
        known=self.known()
        self.assertIn(self.bite,known);self.assertNotIn(self.rules.move_id('튀어오르기'),known)
        self.assertEqual(len(known),6);self.assertEqual(self.p.spec['tutor_points'],4)
        self.assertEqual(self.p.spec['move_learning_log'][-1]['replaced'],self.rules.move_id('튀어오르기'))

    def test_tutor_point_takes_immediate_advanced_connection_and_restores(self):
        self.pokemon(FULL);start=self.e.elapsed_seconds;self.answer(advanced_connection=True);self.gain()
        state=M.describe(self.rules,self.p.spec)
        self.assertEqual((len(state['known']),state['slot_count']),(7,6))
        self.assertEqual(set(state['exempt']),{self.bite})
        row=C.records(self.p.spec)[0]
        self.assertEqual((row['status'],row['ability'],row['point_cost'],row['training_source']),
                         ('active',self.honey,1,C.KEYWORD))
        self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(3,start))
        loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        target=W.actor_index(loaded)[self.p.entity_id]
        self.assertEqual(M.describe(self.rules,target.spec)['exempt'],state['exempt'])
        with self.assertRaisesRegex(ValueError,'cannot be forgotten'):
            loaded.gm.set_move(target,'벌레먹기',add=False,reason='restored bound move')

    def test_invalid_choices_reject_atomically(self):
        helper=[*FULL[:5],'도우미']
        cases=(('unknown',dict(forget='하이드로펌프'),FULL,4,()),('linked',dict(forget='벌레먹기'),FULL,4,()),
               ('other_connection_move',dict(forget='도우미'),helper,4,('헬퍼',)),
               ('unneeded',dict(forget='튀어오르기'),['튀어오르기','몸통박치기'],4,()),
               ('no_points',dict(advanced_connection=True),FULL,0,()),('bad_flag',dict(advanced_connection=1),FULL,4,()))
        for case,option,moves,points,abilities in cases:
            with self.subTest(case=case):
                self.pokemon(moves,points,abilities);self.answer(**option);snap=self.snap()
                with self.assertRaises(ValueError):self.gain()
                self.assertEqual(self.snap(),snap)
        self.pokemon(FULL)
        self.e.rulings.add_answer(C.PROMPT,{'actor_id':'someone else','ability':self.honey,'forget':'방어'},
                                  reason='stale answer for another actor',scope='permanent')
        snap=self.snap()
        with self.assertRaisesRegex(ValueError,'name this actor'):self.gain()
        self.assertEqual(self.snap(),snap)

    def test_already_owned_or_non_connection_gain_learns_nothing(self):
        self.pokemon(['튀어오르기']);self.gain();moves=list(self.p.spec['moves'])
        self.e.gm.set_ability(self.p,'꿀도둑',reason='same Ability again')
        self.e.gm.set_ability(self.p,'단순',reason='non-Connection Ability')
        self.assertEqual(self.p.spec['moves'],moves)

    def test_imported_ability_missing_move_registration_and_restores_are_not_new_gain(self):
        self.pokemon(['튀어오르기'],abilities=['꿀도둑'])
        self.e.register_abilities(self.p);self.e.gm.set_ability(self.p,'꿀도둑',reason='same imported ownership')
        self.assertNotIn(self.bite,self.known());self.assertNotIn(C.PROTECTION,self.p.spec)
        self.e.gm.snapshot('imported');self.e.gm.restore('imported')
        loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        self.assertNotIn(self.bite,W.actor_index(loaded)[self.p.entity_id].spec['moves'])

    def test_actual_growth_milestone_learns_and_replay_does_not_reacquire(self):
        self.pokemon([],species='치라미',level=5,abilities=None)
        out=self.e.choose_growth_ability(self.p,'creation','헬퍼',reason='actual creation selection')
        helper=self.rules.move_id('도우미');self.assertIn(helper,self.known());self.assertFalse(out['replayed'])
        before=self.snap()
        self.assertTrue(self.e.choose_growth_ability(self.p,'creation','헬퍼',reason='actual creation selection')['replayed'])
        self.assertEqual(self.snap(),before)

    def mastery(self,moves=(),points=4):
        self.pokemon(list(moves),points,species='나메일',level=60)
        teacher=Combatant(self.rules,build_trainer(self.rules,'actual teacher',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':4,'포켓몬학':4}))
        self.e.gm.add_combatant(teacher,pos=(0,0),side='party',reason='actual teacher')
        self.p.spec['trainer_id']=teacher.entity_id
        return teacher

    def teach_mastery(self,teacher):
        return self.e.pokemon_activity(teacher,'teach_edge',target=self.p,edge='poke_edge/특성-숙달',ability='꿀도둑',safe=True)

    def test_native_ability_mastery_missing_move_cost_owner_and_loss_reacquisition(self):
        teacher=self.mastery();self.teach_mastery(teacher)
        self.assertEqual(self.p.spec['abilities'],[]);self.assertIn(self.bite,self.known())
        self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(1,3600))
        self.e.gm.set_level(self.p,59,reason='actual prerequisite loss')
        self.assertNotIn('꿀도둑',self.p.abilities);self.assertIn(self.bite,self.known())
        assert_rejected_unchanged(self.e,lambda:self.e.gm.set_move(self.p,self.bite,add=False),reason_pattern='cannot be forgotten')
        self.e.gm.set_level(self.p,60,reason='qualification restored');self.teach_mastery(teacher)
        self.assertEqual(self.p.spec['moves'].count(self.bite),1)
        self.assertEqual(len([r for r in self.p.spec['move_learning_log'] if r['move_id']==self.bite]),1)

    def test_native_ability_mastery_full_list_choice_cost_and_atomic_rejection(self):
        teacher=self.mastery(FULL,4)
        assert_rejected_unchanged(self.e,lambda:self.teach_mastery(teacher),reason_pattern='explicit forgotten Move or immediate Advanced Connection')
        self.answer(advanced_connection=True);self.teach_mastery(teacher)
        self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(0,3600))
        self.assertEqual(M.describe(self.rules,self.p.spec)['slot_count'],6)
        self.assertEqual(C.records(self.p.spec)[0]['trainer_id'],teacher.entity_id)

    def test_actual_trainer_gain_learns_without_pokemon_slot_limit(self):
        self.e=Engine(self.rules,seed=930)
        self.p=Combatant(self.rules,build_trainer(self.rules,'actual Trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'moves':FULL,'abilities':[]}))
        self.e.gm.add_combatant(self.p,pos=(0,0),side='party',reason='actual Trainer')
        self.honey=A.ability_id(self.rules,'꿀도둑');self.bite=self.rules.move_id('벌레먹기');self.gain()
        self.assertIn(self.bite,self.known());self.assertEqual(len(self.known()),7)
        self.e.gm.set_ability(self.p,'꿀도둑',add=False,reason='actual later loss')
        assert_rejected_unchanged(self.e,lambda:self.e.gm.set_move(self.p,self.bite,add=False),reason_pattern='cannot be forgotten')

    def test_source_owned_known_move_becomes_independent_connection_learning(self):
        self.pokemon(['튀어오르기'])
        G.grant_moves(self.p,['벌레먹기'],'actual-other-grant','feature',rule_id='keyword/연결',lifetime='while_owned')
        self.gain();G.revoke(self.p,'actual-other-grant',engine=self.e)
        self.assertIn(self.bite,self.p.moves);self.assertIn(self.bite,self.p.spec['moves'])
        self.assertEqual(self.p.spec['move_learning'][self.bite]['source'],C.KEYWORD)

    def test_current_source_owned_connection_move_cannot_be_revoked_as_forgetting(self):
        self.pokemon([],abilities=['꿀도둑'])
        G.grant_moves(self.p,['벌레먹기'],'actual-known-source','feature',rule_id=C.KEYWORD,lifetime='while_owned')
        assert_rejected_unchanged(self.e,lambda:G.revoke(self.p,'actual-known-source',engine=self.e),reason_pattern='cannot be forgotten')

    def test_loss_and_both_restores_retain_protection_without_inventing_import_learning(self):
        self.pokemon(['벌레먹기','튀어오르기']);self.gain()
        self.assertNotIn(self.bite,self.p.spec.get('move_learning',{}))
        self.e.gm.set_ability(self.p,'꿀도둑',add=False,reason='real loss')
        self.e.gm.snapshot('lost');self.e.gm.restore('lost')
        loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        for e in (self.e,loaded):
            c=W.actor_index(e)[self.p.entity_id]
            assert_rejected_unchanged(e,lambda:e.gm.set_move(c,self.bite,add=False),reason_pattern='cannot be forgotten')

    def test_late_learning_failure_rolls_back_ability_moves_points_clock_and_rng(self):
        import learning_grant as L
        self.pokemon(FULL);self.answer(advanced_connection=True);native=L.learn_moves
        def fail(*args,**kwargs):
            native(*args,**kwargs);raise ValueError('late Connection learning failure')
        with patch.object(L,'learn_moves',side_effect=fail):
            assert_rejected_unchanged(self.e,self.gain,reason_pattern='late Connection learning')

    def temporary(self,move,*,pokemon=False):
        from grid import Grid
        self.e=Engine(self.rules,seed=940);self.e.grid=Grid(20,20)
        spec=(build_pokemon(self.rules,'잉어킹',20,moves=FULL,abilities=['트레이스'],extra={'tutor_points':1}) if pokemon else
              build_trainer(self.rules,'actual copy user',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'moves':[move],'abilities':['인분'] if move=='스킬스왑' else []}))
        self.p=Combatant(self.rules,spec)
        self.donor=Combatant(self.rules,build_pokemon(self.rules,'나메일',20,moves=['몸통박치기'],abilities=['꿀도둑']))
        self.e.gm.add_combatant(self.p,pos=(1,1),side='party',reason='actual ability recipient')
        self.e.gm.add_combatant(self.donor,pos=(2,1),side='opponent',reason='imported donor with missing linked Move')
        self.honey=A.ability_id(self.rules,'꿀도둑');self.bite=self.rules.move_id('벌레먹기')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)

    def test_role_play_and_skill_swap_learn_and_keep_move_after_actual_recall(self):
        for move in ('역할','스킬스왑'):
            with self.subTest(move=move):
                self.temporary(move)
                if move=='스킬스왑':self.e.gm.choose_ability_transition(self.p,self.donor,'move/'+move,ability='인분',reason='actual swapped Ability')
                self.e.use_move(self.p,self.donor,self.rules.move_id(move))
                self.assertIn(self.bite,self.known());self.assertIn('꿀도둑',self.p.abilities)
                self.e.gm.recall(self.p,reason='actual temporary source end')
                self.assertNotIn('꿀도둑',self.p.abilities);self.assertIn(self.bite,self.known())
                assert_rejected_unchanged(self.e,lambda:self.e.gm.set_move(self.p,self.bite,add=False),reason_pattern='cannot be forgotten')

    def test_trace_immediate_edge_full_slots_native_restore_and_expiry_refund(self):
        self.temporary('트레이스',pokemon=True);self.answer(advanced_connection=True)
        self.e.gm.choose_ability_transition(self.p,self.donor,'ability/트레이스',ability='꿀도둑',reason='actual Trace choice')
        self.e.activate_ability(self.p,'트레이스',self.donor)
        self.assertIn(self.bite,self.known());self.assertEqual(self.p.spec['tutor_points'],0)
        saved=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        target=W.actor_index(saved)[self.p.entity_id]
        self.assertEqual(set(M.describe(self.rules,target.spec)['exempt']),{self.bite})
        saved.gm.set_move(target,'튀어오르기',add=False,reason='explicit slot before temporary Ability ends')
        saved.end_encounter(saved.everyone)
        self.assertEqual(target.spec['tutor_points'],1);self.assertIn(self.bite,target.spec['moves'])
        self.assertEqual(C.records(target.spec)[0]['status'],'refunded')
        protection=deepcopy(target.spec[C.PROTECTION]);receipts=deepcopy(C.records(target.spec))
        saved.end_encounter(saved.everyone)
        self.assertEqual(target.spec[C.PROTECTION],protection);self.assertEqual(C.records(target.spec),receipts)
        self.assertEqual(target.spec['tutor_points'],1)
        assert_rejected_unchanged(saved,lambda:saved.gm.set_move(target,self.bite,add=False),reason_pattern='cannot be forgotten')

    def test_transform_learns_in_form_then_restores_exact_previous_list(self):
        self.temporary('변신');before=list(self.p.spec['moves'])
        self.assertIsNone(self.p.weight_class);self.assertNotIn('weight_class',self.p.spec)
        self.e.use_move(self.p,self.donor,self.rules.move_id('변신'))
        self.assertIn(self.bite,self.p.moves);self.assertEqual(self.p.spec['moves'],before)
        self.assertEqual(self.p.weight_class,self.donor.weight_class)
        saved=self.e.gm.snapshot('actual-transform');self.e.gm.restore(saved)
        self.assertIn(self.bite,self.p.moves);self.assertEqual(self.p.weight_class,self.donor.weight_class)
        self.assertNotIn(self.bite,self.p.spec.get('move_learning',{}))
        loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        target=W.actor_index(loaded)[self.p.entity_id]
        self.assertIn(self.bite,target.moves)
        loaded.gm.recall(target,reason='Transform explicit previous Move List restoration')
        self.assertIsNone(target.weight_class);self.assertNotIn('weight_class',target.spec)
        self.assertEqual(target.spec['moves'],before)
        self.assertEqual(set(M.known(self.rules,{'moves':target.moves})),set(M.known(self.rules,{'moves':before})))
        self.assertNotIn(self.bite,target.moves)

    def test_transform_lifetime_requires_the_exact_selected_source_contract(self):
        import effect_lifetimes as LIFE
        self.temporary('변신')
        effect=next(e for e in self.rules.move_mech('move/변신')[0]['effects_exec'] if e['type']=='transform')
        self.assertTrue(LIFE.prepare(self.e,self.p,self.donor,effect,'move/변신')['transform_owned'])
        for source,payload in [('move/몸통박치기',effect),('move/변신',dict(effect,until='scene_end'))]:
            with self.assertRaisesRegex(LIFE.TimingUnsupported,'exact selected source-owned lifetime'):
                LIFE.prepare(self.e,self.p,self.donor,payload,source)

    def test_transform_native_faint_and_encounter_end_restore_only_form_moves(self):
        for event in ('faint','encounter'):
            with self.subTest(event=event):
                self.temporary('변신');before=list(self.p.spec['moves'])
                self.e.use_move(self.p,self.donor,self.rules.move_id('변신'));self.assertIn(self.bite,self.p.moves)
                if event=='faint':self.e.gm.faint(self.p,reason='native Transform KO')
                else:self.e.end_encounter(self.e.everyone)
                self.assertEqual(self.p.spec['moves'],before);self.assertNotIn(self.bite,self.p.moves)
                self.assertNotIn('transformed',self.p.custom_conditions)
                G.transition(self.e,self.p,lambda e,c:None)
                self.assertEqual(self.p.spec['moves'],before)

    def test_transform_cleanup_keeps_connection_learned_from_another_temporary_source(self):
        for event in ('recall','faint','encounter'):
            with self.subTest(event=event):
                self.temporary('역할');self.e.gm.set_move(self.p,'변신',reason='known native Transform')
                self.e.use_move(self.p,self.donor,self.rules.move_id('역할'));self.assertIn(self.bite,self.known())
                protection=deepcopy(self.p.spec[C.PROTECTION]);baseline=list(self.p.spec['moves'])
                self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)
                self.e.use_move(self.p,self.donor,self.rules.move_id('변신'))
                if event=='recall':self.e.gm.recall(self.p,reason='end both temporary sources')
                elif event=='faint':self.e.gm.faint(self.p,reason='end both temporary sources')
                else:self.e.end_encounter(self.e.everyone)
                self.assertEqual(self.p.spec[C.PROTECTION],protection);self.assertIn(self.bite,self.p.moves)
                self.assertEqual(self.p.spec['moves'],baseline)
                self.assertNotIn('transformed',self.p.custom_conditions)
                assert_rejected_unchanged(self.e,lambda:self.e.gm.set_move(self.p,self.bite,add=False),reason_pattern='cannot be forgotten')


    def test_imported_fixed_trainer_feature_projection_does_not_fabricate_acquisition(self):
        import items
        rules=Rules(ROOT,ruleset='all');e=Engine(rules,seed=950)
        spec=build_trainer(rules,'imported Farcast holder',30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[])
        spec.update(feats=['feat/파캐스트'],classes=[],edges=[],abilities=[])
        actor=Combatant(rules,spec);e.everyone=e.gm.everyone=[actor]
        items.register_feats(e,actor)
        self.assertIn('ability/트랜스포터-playtest',A.known(actor))
        self.assertNotIn(rules.move_id('순간이동'),actor.spec['moves']);self.assertNotIn(C.PROTECTION,actor.spec)

    def test_tampered_connection_protection_cannot_save(self):
        self.pokemon(['튀어오르기']);self.gain()
        self.p.spec[C.PROTECTION][self.bite]['ability']='ability/단순'
        with self.assertRaises(ValueError):CODEC.dump_engine(self.e)


if __name__=='__main__':unittest.main()
