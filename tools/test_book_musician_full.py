"""Native Musician acquisition, all Song paths, Voice Lessons, Power Chord and source-specific Drown Out."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'tools'))
import test_book_dancer_acquisition as fixture
from engine import Rules, Engine, Combatant
from grid import Grid
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
from contest import ContestRules, ContestEngine
import musician as M
import trainer_feature_acquisition as TFA
import action_points as AP
import effect_lifetimes as LIFE
import combat_timing as TIME
import state_codec as CODEC
import world_entities as W
import frequency as F
import effects_ext as EXT


class MusicianTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')
        cls.contest_rules = ContestRules(ROOT, ruleset='core')

    def setUp(self):
        old = self.rules.rulings
        self.rules.rulings = deepcopy(old)
        self.addCleanup(setattr, self.rules, 'rulings', old)
        self.e = Engine(self.rules, seed=2345)
        self.e.grid = Grid(18, 12)
        self.t = self.add('Musician', 'trainer', (3, 3), speed=30, classes=[], feats=[], edges=[], moves=[], items={}, exp_bank=50)

    def add(self, name, kind, pos, speed=20, side='party', **extra):
        spec = dict(deepcopy(fixture.COMMON), name=name, kind=kind)
        spec['skills'] = dict(spec['skills'], 집중=6)
        spec['stats']['spe'] = speed
        spec.update(extra)
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=side, reason='actual Musician scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        if kind == 'pokemon' and extra.get('trainer_id'):
            self.e.gm.observe_loyalty(actor, 6, reason='actual willing Pokemon')
        return actor

    def acquire(self, feature, branch=None, actor=None):
        actor = actor or self.t
        return TFA.acquire_static(self.e, actor, feature, acquisition_request_id=actor.entity_id+'/'+feature, branch=branch)

    def musician(self, top=M.CLASS, ability=None):
        self.acquire(M.CLASS)
        if ability:
            self.acquire(M.ABILITY, ability)
        if top != M.CLASS:
            for feature in (M.BLUES, M.CACOPHONY, M.NOISE):
                self.acquire(feature)
                if feature == top:
                    return
            if top not in (M.NOISE, M.BLUES, M.CACOPHONY):
                self.acquire(top)

    combat = fixture.DancerAcquisitionTests.combat
    next_turn = fixture.DancerAcquisitionTests.next_turn
    use = fixture.DancerAcquisitionTests.use
    restore = fixture.DancerAcquisitionTests.restore
    retrain = fixture.DancerAcquisitionTests.retrain
    valid = fixture.DancerAcquisitionTests.valid
    rejected = fixture.DancerAcquisitionTests.rejected

    def pokemon(self, name='Singer', pos=(4, 3), owner=None, side='party', **extra):
        return self.add(name, 'pokemon', pos, trainer_id=(owner or self.t).entity_id, side=side,
                        abilities=[], moves=['move/하이퍼보이스', 'move/소란피기', 'move/멸망의노래', 'move/몸통박치기'], **extra)

    def foe(self, pos=(5, 3), **extra):
        return self.add('Foe', 'trainer', pos, side='enemy', speed=15, **extra)

    def test_complete_template_acquires_only_the_selected_class_and_stat_tag(self):
        self.assertEqual(len(M.DEFINITIONS), 7)
        before = self.t.stats['spa']
        self.musician()
        self.assertEqual(self.t.stats['spa'], before+1)
        self.assertEqual(self.t.spec['feats'], [M.CLASS])
        self.assertEqual(self.t.moves, [])
        self.valid()

    def test_class_requires_both_novice_skills_without_receipts_or_cost(self):
        self.t.spec['skills']['집중'] = 2
        self.rejected(lambda: self.acquire(M.CLASS), 'skill rank')

    def test_prerequisite_chain_and_each_printed_rank_are_enforced(self):
        self.rejected(lambda: self.acquire(M.NOISE), 'acquired')
        self.musician(M.BLUES)
        self.t.spec['skills'].update(매력=3, 집중=3)
        self.rejected(lambda: self.acquire(M.CACOPHONY), 'skill rank')

    def test_existing_three_move_grants_and_stat_tags_are_not_duplicated(self):
        before = self.t.stats['spa']
        self.musician(M.NOISE)
        self.assertEqual(set(self.t.moves), {self.rules.move_id(n) for n in ('노래하기','초음파','싫은소리','금속음','소란피기','하이퍼보이스')})
        self.assertEqual(self.t.stats['spa'], before+4)
        import items
        items.register_feats(self.e, self.t)
        self.assertEqual(self.t.stats['spa'], before+4)
        self.valid()

    def test_musical_ability_is_one_choice_and_soundproof_is_effective(self):
        self.musician(ability='방음')
        self.assertIn('방음', self.t.abilities)
        foe=self.foe();self.combat(foe,count=15)
        self.use(foe,self.t,'move/초음파',face=20)
        self.assertNotIn('혼란',self.t.conditions)
        self.rejected(lambda: TFA.acquire_static(self.e,self.t,M.ABILITY,branch='소리묻히기',acquisition_request_id='other'), 'already acquired')

    def test_core_drown_out_is_distinct_from_the_excluded_playtest(self):
        self.musician(ability='소리묻히기')
        self.assertIn('소리묻히기', self.t.abilities)
        self.assertEqual(self.rules._selected_rule(M.DROWN), M.DROWN)
        with self.assertRaises(ValueError):
            self.rules._selected_rule(M.DROWN_PLAYTEST)
        self.assertEqual(self.rules.core_abilities[M.DROWN]['native_contract']['dc'], 'actual_accuracy_roll')
        self.restore('t')
        self.assertIn('소리묻히기', self.t.abilities)

    def test_standard_courage_affects_self_and_only_allies_in_burst_four(self):
        self.musician(); ally=self.pokemon(); foe=self.foe(); far=self.pokemon('far',(9,3))
        self.combat(self.t); before=AP.available(self.t)
        result=M.play(self.e,self.t,['courage'])
        self.assertEqual(set(result[0]['targets']),{self.t.entity_id,ally.entity_id})
        self.assertEqual(AP.available(self.t),before-1)
        self.assertEqual(self.e.skill_roll(ally,'매력',fixed=[1]*6).total,8)
        self.assertEqual(LIFE.numeric(ally,'save_modifier'),2)
        self.assertEqual(LIFE.numeric(foe,'save_modifier'),0)
        self.assertEqual(LIFE.numeric(far,'save_modifier'),0)
        self.valid()

    def test_full_action_plays_two_songs_and_pays_each_one_ap(self):
        self.musician();self.combat(self.t);before=AP.available(self.t)
        rows=M.play(self.e,self.t,['might','life'],mode='full')
        self.assertEqual(len(rows),2);self.assertEqual(AP.available(self.t),before-2)
        self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.t.budget['shift'],0)
        self.assertEqual(LIFE.numeric(self.t,'damage_reduction'),5)
        self.assertTrue(any(x.get('type')=='damage_roll_mod' and x.get('value')==5 for x in self.t.modifiers))

    def test_courage_last_until_end_of_users_next_turn_and_survive_codec(self):
        self.musician();self.p=self.pokemon();self.combat(self.t)
        M.play(self.e,self.t,['courage']);self.e.end_of_turn(self.t)
        self.assertEqual(LIFE.numeric(self.p,'save_modifier'),2)
        self.restore('t','p');self.combat(self.t)
        self.assertEqual(LIFE.numeric(self.p,'save_modifier'),2)
        self.e.end_of_turn(self.t)
        self.assertEqual(LIFE.numeric(self.p,'save_modifier'),0)
        self.assertEqual(self.e.skill_roll(self.p,'매력',fixed=[1]*6).total,6)

    def test_song_of_might_and_life_are_consumed_by_native_damage_formula(self):
        self.musician();foe=self.foe();self.combat(self.t)
        move=self.rules.move('move/하이퍼보이스');base=self.e.roll_damage(self.t,foe,move,set_damage=True)
        M.play(self.e,self.t,['might','life'],mode='full')
        self.assertEqual(self.e.roll_damage(self.t,foe,move,set_damage=True),base+5)
        outgoing=self.e.roll_damage(foe,self.t,move,set_damage=True)
        self.assertGreater(outgoing,0)
        self.assertEqual(EXT.defense_hook(self.e,foe,self.t,move,{'effects_exec':[]},'spd')[1],5)

    def test_sound_swift_uses_actual_move_geometry_and_always_includes_user(self):
        self.musician(M.NOISE);ally=self.pokemon(pos=(4,3));outside=self.pokemon('outside',(3,5));foe=self.foe()
        self.combat(self.t);self.use(self.t,foe,'move/하이퍼보이스',aim=(5,3))
        row=M.play(self.e,self.t,['life'],mode='sound')[0]
        self.assertIn(self.t.entity_id,row['targets']);self.assertIn(ally.entity_id,row['targets'])
        self.assertNotIn(outside.entity_id,row['targets']);self.assertEqual(self.t.budget['swift'],0)
        self.rejected(lambda:M.play(self.e,self.t,['life'],mode='sound'),'unused same-turn')

    def test_dance_shift_song_uses_burst_two_and_native_dance_trigger(self):
        self.musician();ally=self.pokemon(pos=(5,3));far=self.pokemon('far',(6,3))
        self.combat(self.t);self.use(self.t,self.t,'move/칼춤')
        row=M.play(self.e,self.t,['courage'],mode='dance')[0]
        self.assertIn(ally.entity_id,row['targets']);self.assertNotIn(far.entity_id,row['targets'])
        self.assertEqual(self.t.budget['shift'],0)

    def test_invalid_or_missing_move_trigger_is_atomic(self):
        self.musician();self.combat(self.t)
        self.rejected(lambda:M.play(self.e,self.t,['might'],mode='sound'),'unused same-turn')
        self.rejected(lambda:M.play(self.e,self.t,['might'],mode='full'),'exactly two')

    def test_song_rejects_before_real_turn_and_insufficient_ap_atomically(self):
        self.musician()
        self.rejected(lambda:M.play(self.e,self.t,['life']),'encounter')
        self.combat(self.t);AP.spend(self.t,AP.available(self.t))
        self.rejected(lambda:M.play(self.e,self.t,['life']),'one AP')

    def test_voice_lessons_projects_only_current_owner_sound_moves_except_perish(self):
        self.musician(M.VOICE);own=self.pokemon();other=self.add('Other','trainer',(10,3),feats=[],classes=[])
        foreign=self.pokemon('Foreign',(10,4),owner=other)
        for actor in (self.t,own):
            self.assertIn('친화',M.project_move(self.e,actor,self.rules.move('move/하이퍼보이스'))['keywords'])
            self.assertNotIn('친화',M.project_move(self.e,actor,self.rules.move('move/멸망의노래'))['keywords'])
            self.assertNotIn('친화',M.project_move(self.e,actor,self.rules.move('move/몸통박치기'))['keywords'])
        self.assertNotIn('친화',M.project_move(self.e,foreign,self.rules.move('move/하이퍼보이스'))['keywords'])

    def test_voice_lessons_combat_does_not_hit_allies_and_still_hits_foes(self):
        self.musician(M.VOICE);ally=self.pokemon(pos=(4,3));foe=self.foe();hp=ally.hp
        self.combat(self.t);self.use(self.t,foe,'move/하이퍼보이스',aim=(5,3))
        self.assertEqual(ally.hp,hp);self.assertLess(foe.hp,foe.max_hp)
        self.assertEqual(ally.pos,(4,3))

    def test_voice_lessons_ownership_transfer_removes_bonus_without_cached_keyword(self):
        self.musician(M.VOICE);p=self.pokemon();other=self.add('New Owner','trainer',(9,3),classes=[],feats=[])
        import pokemon_party as PARTY
        PARTY.configure(self.e,self.t,mode='standard',reason='actual roster',roster=[p],storage={'kind':'center','id':'a'})
        PARTY.configure(self.e,other,mode='standard',reason='actual new roster',roster=[],storage={'kind':'center','id':'b'})
        W.transfer_owner(self.e,p,self.t,other,reason='actual trade',request_id='transfer')
        self.assertIsNone(M.voice_owner(self.e,p))
        self.assertNotIn('친화',M.project_move(self.e,p,self.rules.move('move/하이퍼보이스'))['keywords'])

    def test_contest_sound_bonus_is_in_the_actual_native_pool(self):
        self.musician(M.VOICE);p=self.pokemon();ce=ContestEngine(self.contest_rules,seed=99)
        c=ce.contestant_from_combatants(self.e,p,self.t,'매력',stat_dice={'근사함':2})
        frames=[];finish=ContestEngine._finish_performance
        def observe(native,actor,adjacent,frame,reroll_kind=None):
            frames.append(deepcopy(frame))
            return finish(native,actor,adjacent,frame,reroll_kind)
        with patch.object(ContestEngine,'_finish_performance',new=observe), patch.object(ce,'d6',side_effect=lambda n:[6]*n) as roll:
            ce.perform(c,'하이퍼보이스','근사함',[],False)
        frame=frames[-1]
        self.assertEqual(frame['pool_components']['voice_lessons'],1)
        self.assertEqual(roll.call_args.args[0],sum(v for k,v in frame['pool_components'].items() if k!='voice_lessons')+1)
        self.assertEqual(c.appeal,2*frame['total'])

    def test_contest_optional_voice_lesson_die_can_be_declined(self):
        self.musician(M.VOICE);p=self.pokemon();ce=ContestEngine(self.contest_rules,seed=99)
        c=ce.contestant_from_combatants(self.e,p,self.t,'매력',stat_dice={'근사함':2})
        frames=[];finish=ContestEngine._finish_performance
        def observe(native,actor,adjacent,frame,reroll_kind=None):
            frames.append(deepcopy(frame));return finish(native,actor,adjacent,frame,reroll_kind)
        with patch.object(ContestEngine,'_finish_performance',new=observe):
            ce.perform(c,'하이퍼보이스','근사함',[],False,voice_lessons=False)
        self.assertNotIn('voice_lessons',frames[-1]['pool_components'])
        self.assertEqual(frames[-1]['total'],sum(frames[-1]['pool_components'].values()))

    def test_contest_bonus_excludes_trainer_foreign_pokemon_and_perish(self):
        self.musician(M.VOICE);p=self.pokemon();move=self.rules.move('move/하이퍼보이스')
        self.assertEqual(M.contest_bonus(self.e,self.t,self.t,move),0)
        self.assertEqual(M.contest_bonus(self.e,p,self.t,self.rules.move('move/몸통박치기')),0)
        self.assertEqual(M.contest_bonus(self.e,p,self.t,self.rules.move('move/멸망의노래')),0)

    def test_power_chord_uses_one_native_skill_check_special_defense_and_normal_type(self):
        self.musician(M.CHORD);foe=self.foe();ghost=self.add('Ghost','trainer',(5,4),side='enemy',types=['고스트'])
        ally=self.pokemon();hp=ally.hp;self.combat(self.t)
        row=M.play(self.e,self.t,['life'],power_chord='매력')[0]['power_chord']
        self.assertEqual(row['total'],row['check']+self.t.staged('spa'))
        self.assertGreater(row['damage'][foe.entity_id]['requested'],0)
        self.assertEqual(row['damage'][ghost.entity_id]['requested'],0)
        self.assertEqual(ally.hp,hp)

    def test_full_two_songs_can_choose_power_chord_once_with_one_scene_use_left(self):
        self.musician(M.CHORD);self.foe();self.combat(self.t)
        M.play(self.e,self.t,['life'],power_chord='집중');self.next_turn(self.t)
        rows=M.play(self.e,self.t,['might','life'],mode='full',power_chord=['매력',None])
        self.assertIn('power_chord',rows[0]);self.assertNotIn('power_chord',rows[1])
        self.assertFalse(F.activation_allowed(self.t,M.CHORD,'장면x2',engine=self.e))
        self.next_turn(self.t)
        self.rejected(lambda:M.play(self.e,self.t,['life'],power_chord='매력'),'scene uses exhausted')

    def test_core_drown_out_cancels_the_entire_actual_area_once(self):
        self.musician(ability='소리묻히기');foe=self.foe();ally=self.pokemon(pos=(3,4));hp=(self.t.hp,ally.hp)
        self.combat(foe,count=15)
        with patch.object(self.e,'decide',return_value=True):
            self.use(foe,self.t,'move/하이퍼보이스',face=2,aim=(3,3))
        self.assertEqual((self.t.hp,ally.hp),hp)
        self.assertFalse(F.activation_allowed(self.t,M.DROWN,'장면',engine=self.e))

    def test_failed_core_drown_out_pays_scene_use_and_does_not_cancel(self):
        self.t.spec['skills']['집중']=3;self.musician(ability='소리묻히기');foe=self.foe();self.combat(foe,count=15)
        with patch.object(self.e,'decide',return_value=True):
            self.use(foe,self.t,'move/하이퍼보이스',face=20,aim=(3,3))
        self.assertLess(self.t.hp,self.t.max_hp)
        self.assertFalse(F.activation_allowed(self.t,M.DROWN,'장면',engine=self.e))

    def test_class_and_voice_receipts_restore_without_auto_granting_power_chord(self):
        self.musician(M.VOICE);self.p=self.pokemon();self.restore('t','p')
        self.assertIs(M.voice_owner(self.e,self.p),self.t)
        self.assertNotIn(M.CHORD,self.t.spec['feats'])
        self.assertEqual(len([r for r in TFA._static_records(self.t) if r[2]]),5)

    def test_no_accuracy_core_drown_out_is_pending_before_any_game_action(self):
        import common_checks as C
        self.musician(ability='소리묻히기');foe=self.foe();self.combat(foe,count=15)
        self.e.gm.set_move(foe,'move/멸망의노래',reason='actual known Sonic Move')
        M.request_drown_out(self.e,self.t,reason='player wishes to counter this Sonic Move')
        before=self.e.export_state();rng=self.e.rng.getstate()
        result=self.e.use_move_on(foe,self.t,'move/멸망의노래',self.e.everyone,aim=foe.pos)
        self.assertIsInstance(result,C.PendingDecision)
        self.assertEqual(before,self.e.export_state());self.assertEqual(rng,self.e.rng.getstate())

    def test_playtest_drown_out_cancels_no_accuracy_move_without_a_focus_check(self):
        self.rules=Rules(ROOT,ruleset='all');self.setUp()
        self.musician(ability='소리묻히기 [Playtest]');foe=self.foe();self.combat(foe,count=15)
        M.request_drown_out(self.e,self.t,source=M.DROWN_PLAYTEST,reason='player selects the actual Playtest reaction')
        with patch.object(Engine,'skill_roll',side_effect=AssertionError('Playtest has no Focus Check')):
            self.use(foe,self.t,'move/멸망의노래',aim=foe.pos)
        self.assertNotIn('perish',str(self.t.custom_conditions).lower())
        self.assertTrue(F.activation_allowed(self.t,M.DROWN_PLAYTEST,'장면x2',engine=self.e))
        self.valid()

    def test_retraining_voice_withdraws_keyword_and_contest_bonus_but_retains_learned_pairs(self):
        self.musician(M.VOICE);p=self.pokemon();before=list(self.t.moves)
        self.retrain(M.VOICE)
        self.assertIsNone(M.voice_owner(self.e,p))
        self.assertEqual(M.contest_bonus(self.e,p,self.t,self.rules.move('move/하이퍼보이스')),0)
        self.assertEqual(self.t.moves,before)
        self.valid()

    def test_no_accuracy_core_drown_out_resumes_only_with_an_explicit_scoped_gm_dc(self):
        self.musician(ability='소리묻히기');foe=self.foe();self.combat(foe,count=15)
        M.request_drown_out(self.e,self.t,reason='actual core reaction choice')
        self.e.rulings.add_answer('drown_out_no_accuracy',{'source':M.DROWN,'move_id':'move/멸망의노래','dc':1,'reason':'explicit table ruling for this otherwise undefined DC'},reason='user-provided table rule',scope='scene')
        self.use(foe,self.t,'move/멸망의노래',aim=foe.pos)
        self.assertFalse(F.activation_allowed(self.t,M.DROWN,'장면',engine=self.e))
        self.assertNotIn('perish',str(self.t.custom_conditions).lower())
        self.valid()

    def test_all_four_learned_status_moves_execute_their_actual_effects(self):
        self.musician(M.NOISE);foe=self.foe();self.combat(self.t)
        self.use(self.t,foe,'move/노래하기',face=20);self.assertIn('잠듦',foe.conditions)
        self.next_turn(self.t);self.use(self.t,foe,'move/초음파',face=20);self.assertIn('혼란',foe.conditions)
        self.next_turn(self.t);self.use(self.t,foe,'move/싫은소리',face=20);self.assertEqual(foe.stages['def'],-2)
        self.next_turn(self.t);self.use(self.t,foe,'move/금속음',face=20);self.assertEqual(foe.stages['spd'],-2)

    def test_uproar_damages_and_wakes_all_sleepers_in_its_five_meter_effect(self):
        self.musician(M.NOISE);foe=self.foe(pos=(4,3));ally=self.pokemon(pos=(7,3));far=self.pokemon('far',(10,3))
        self.e.apply_status(ally,'잠듦');self.e.apply_status(far,'잠듦');self.combat(self.t)
        self.use(self.t,foe,'move/소란피기',face=20,aim=self.t.pos)
        self.assertLess(foe.hp,foe.max_hp);self.assertNotIn('잠듦',ally.conditions);self.assertIn('잠듦',far.conditions)

    def test_supersonic_miss_accuracy_penalty_expires_at_the_next_round_count(self):
        self.musician(M.BLUES);foe=self.foe();self.combat(self.t)
        self.use(self.t,foe,'move/초음파',face=1)
        self.assertEqual(LIFE.numeric(foe,'accuracy_modifier'),-2)
        self.next_turn(self.t)
        self.assertEqual(LIFE.numeric(foe,'accuracy_modifier'),0)

    def test_sing_miss_slows_and_penalizes_evasion_until_users_next_turn_end(self):
        self.musician(M.BLUES);foe=self.foe();self.combat(self.t)
        self.use(self.t,foe,'move/노래하기',face=1)
        self.assertIn('둔화',foe.conditions);self.assertEqual(LIFE.numeric(foe,'evasion_modifier'),-2)
        self.next_turn(self.t);self.e.end_of_turn(self.t)
        self.assertEqual(LIFE.numeric(foe,'evasion_modifier'),0)

    def test_voice_and_no_accuracy_source_loss_do_not_survive_parent_retraining(self):
        self.musician(M.VOICE)
        self.rejected(lambda:self.retrain(M.NOISE),'depend|retained|prerequisite')

    def test_uproar_without_attack_targets_still_cures_within_five_meters(self):
        self.musician(M.NOISE);ally=self.pokemon(pos=(7,3));self.e.apply_status(ally,'잠듦');self.combat(self.t)
        self.use(self.t,self.t,'move/소란피기',aim=self.t.pos)
        self.assertNotIn('잠듦',ally.conditions)
        row=M.play(self.e,self.t,['life'],mode='sound')[0]
        self.assertEqual(row['targets'],[self.t.entity_id])

    def test_song_trigger_requires_a_real_completed_move_not_a_fabricated_spec(self):
        self.musician();self.combat(self.t)
        self.t.spec[M.KEY]={'move_trigger':{'move_id':'move/초음파','sonic':True,'dance':False,'cells':[[3,3]],'stamp':M._stamp(self.e,self.t),'used':False}}
        report=self.e.validate_state();self.assertFalse(report['valid'])
        before=(AP.available(self.t),deepcopy(self.t.budget),self.e.rng.getstate())
        with self.assertRaisesRegex(ValueError,'completion identity'):
            M.play(self.e,self.t,['life'],mode='sound')
        self.assertEqual(before,(AP.available(self.t),self.t.budget,self.e.rng.getstate()))
        self.t.spec[M.KEY]['move_trigger']='move-complete:missing'
        with self.assertRaisesRegex(ValueError,'completion owner'):
            M.play(self.e,self.t,['life'],mode='sound')
        self.assertEqual(before,(AP.available(self.t),self.t.budget,self.e.rng.getstate()))

    def test_real_song_activation_restores_with_native_origin_and_rejects_another_owner_or_move(self):
        self.musician(M.NOISE);self.f=self.foe();self.combat(self.t)
        self.use(self.t,self.f,'move/초음파',face=20)
        origin=self.t.spec[M.KEY]['move_trigger'];self.assertIsInstance(origin,str)
        self.assertEqual(M._song_origin(self.e,self.t)['cells'],[[5,3]])
        self.restore('t','f');self.assertEqual(self.t.spec[M.KEY]['move_trigger'],origin)
        self.assertEqual(M._song_origin(self.e,self.t)['cells'],[[5,3]])
        M.play(self.e,self.t,['life'],mode='sound')
        self.next_turn(self.t)
        self.rejected(lambda:M.play(self.e,self.t,['life'],mode='sound'),'same-turn')
        self.use(self.t,self.f,'move/몸통박치기',face=20)
        wrong=next(reversed(self.e._move_completions))
        self.t.spec[M.KEY]['move_trigger']=wrong
        with self.assertRaisesRegex(ValueError,'activation evidence|Sonic or Dance'):
            M._song_origin(self.e,self.t,for_use=True)
        self.t.spec[M.KEY]['move_trigger']=origin
        self.f.spec[M.KEY]={'move_trigger':origin}
        with self.assertRaisesRegex(ValueError,'completion owner'):
            M._song_origin(self.e,self.f,for_use=True)
        self.f.spec.pop(M.KEY);self.t.spec[M.KEY].pop('move_trigger')
        self.valid()

    def test_cancelled_sonic_move_does_not_authorize_a_song(self):
        self.musician(M.NOISE);foe=self.foe()
        self.acquire(M.CLASS,actor=foe);self.acquire(M.ABILITY,branch='소리묻히기',actor=foe)
        M.request_drown_out(self.e,foe,reason='actual counter before Song')
        self.combat(self.t);self.use(self.t,foe,'move/하이퍼보이스',face=2,aim=foe.pos)
        self.assertNotIn('move_trigger',self.t.spec.get(M.KEY,{}))
        self.rejected(lambda:M.play(self.e,self.t,['life'],mode='sound'),'unused same-turn')

    def test_uproar_field_respects_soundproof_but_not_friendly_or_damage_only_immunity(self):
        self.musician(M.VOICE)
        protected=self.add('Protected Singer','trainer',(7,3),classes=[],feats=[],abilities=[])
        self.acquire(M.CLASS,actor=protected);self.acquire(M.ABILITY,branch='방음',actor=protected)
        ally=self.pokemon('Ordinary Sleeper',pos=(6,3))
        guard=self.add('Wonder Guard Sleeper','pokemon',(7,4),trainer_id=self.t.entity_id,abilities=['불가사의부적'],moves=[],types=['벌레','고스트'])
        self.e.register_abilities(guard)
        for target in (protected,ally,guard):self.e.apply_status(target,'잠듦')
        move=M.project_move(self.e,self.t,self.rules.move('move/소란피기'))
        self.assertIn('친화',move['keywords'])
        self.assertIsNotNone(EXT.blocks_hit(self.e,self.t,guard,move,self.rules.move_mech(move['id'])[0]))
        self.combat(self.t);self.use(self.t,self.t,'move/소란피기',aim=self.t.pos)
        self.assertIn('잠듦',protected.conditions)
        self.assertNotIn('잠듦',ally.conditions)
        self.assertNotIn('잠듦',guard.conditions)
        self.valid()

    def test_auxiliary_core_source_uses_the_explicit_audit_boundary_and_current_sha(self):
        from hashlib import sha256
        import source_context as SOURCE
        self.assertFalse((ROOT/'input'/'core-drown-out.txt').exists())
        path=ROOT/'source-audit'/'core-drown-out.txt';body=path.read_bytes()
        reference={'file':'source-audit/core-drown-out.txt','sha256':sha256(body).hexdigest()}
        self.assertEqual(SOURCE.verified_source(self.rules,reference,source_root='source-audit'),body)
        with self.assertRaisesRegex(ValueError,'inside input'):
            SOURCE.verified_source(self.rules,reference)
        with self.assertRaisesRegex(ValueError,'inside source-audit'):
            SOURCE.verified_source(self.rules,{'file':'input/ch04-trainer-classes.md','sha256':M.SOURCE_SHA256},source_root='source-audit')
        with self.assertRaisesRegex(ValueError,'source changed'):
            SOURCE.verified_source(self.rules,dict(reference,sha256='0'*64),source_root='source-audit')
        selected=self.rules.select_source_definition(M.DROWN)
        self.assertEqual(selected['source']['additional_snapshots'],{reference['file']:reference['sha256']})
        with self.assertRaisesRegex(ValueError,'inside source-audit'):
            SOURCE.verified_source(self.rules,{'file':'source-audit/../input/ch04-trainer-classes.md','sha256':M.SOURCE_SHA256},source_root='source-audit')
        origin=self.rules.selection.units[M.DROWN]['source'];saved=origin['additional_snapshots']
        try:
            origin['additional_snapshots']=dict(saved,**{'source-audit/unregistered.txt':reference['sha256']})
            with self.assertRaisesRegex(ValueError,'unregistered source-audit'):
                self.rules.select_source_definition(M.DROWN)
        finally:origin['additional_snapshots']=saved
        self.assertEqual(SOURCE.verified_source(self.rules,{'file':'input/ch04-trainer-classes.md','sha256':M.SOURCE_SHA256}),(ROOT/'input/ch04-trainer-classes.md').read_bytes())

if __name__ == '__main__':
    unittest.main()
