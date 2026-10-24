"""Native connections for the fourteen remaining Type Ace audit findings."""
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import test_book_type_ace_acquisition as FIX
import test_book_type_ace_reactions as RX
import body_state as BODY
import class_actor_state_reactions as REACTIONS
import combat_timing as TIME
import frequency as FREQUENCY
import state_fields as FIELDS
import type_ace as TA
import trainer_feature_acquisition as ACQUIRE


class TypeAceRemainingTests(unittest.TestCase):
    setUpClass = classmethod(FIX.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = FIX.TypeAceAcquisitionTests.setUp
    setup = FIX.TypeAceAcquisitionTests.setup
    add = FIX.TypeAceAcquisitionTests.add
    acquire = FIX.TypeAceAcquisitionTests.acquire
    combat = FIX.TypeAceAcquisitionTests.combat
    next_turn = FIX.TypeAceAcquisitionTests.next_turn
    communication = FIX.TypeAceAcquisitionTests.communication
    rejected = FIX.TypeAceAcquisitionTests.rejected
    valid = FIX.TypeAceAcquisitionTests.valid
    restore = FIX.TypeAceAcquisitionTests.restore
    family = RX.TypeAceReactionTests.family
    known = RX.TypeAceReactionTests.known
    answer = RX.TypeAceReactionTests.answer
    native = RX.TypeAceReactionTests.native
    selected = RX.TypeAceReactionTests.selected
    completed = RX.TypeAceReactionTests.completed
    react = RX.TypeAceReactionTests.react
    sustain = RX.TypeAceReactionTests.sustain
    hazards = RX.TypeAceReactionTests.hazards
    walk = RX.TypeAceReactionTests.walk

    def capability(self, actor, name):
        FIELDS.base_patch(actor, {'capabilities': list(actor.spec.get('capabilities', [])) + [name]},
                          reason='observed actual Pokemon capability')

    def test_wallclimber_blocks_actual_move_push_without_blocking_damage(self):
        self.family('벌레', 'Insectoid Utility')
        self.capability(self.p, '벽타기')
        self.e.gm.set_position(self.p, (3, 2), reason='actual adjacent push recipient')
        self.combat(self.b)
        hp = self.p.hp
        self.native(self.b, self.p, 'move/메가톤킥', face=15)
        self.assertTrue(TA._completed_targets(self.completed(self.b)))
        self.assertLess(self.p.hp, hp)
        self.assertEqual(self.p.pos, (3, 2))
        self.valid()

    def test_sneak_attack_reads_native_flanking_before_surprise_question(self):
        self.family('악', 'Clever Ruse', 'Sneak Attack')
        self.e.gm.set_position(self.p, (3, 2), reason='actual western flanker')
        self.e.gm.set_position(self.q, (5, 2), reason='actual eastern flanker')
        self.sustain('Sneak Attack')
        self.assertIs(BODY.flanking(self.e, self.b)['flanked'], True)
        move = self.e.r.move('move/물기')
        self.assertEqual(TA.accuracy(self.e, self.p, self.b, move, {}), 2)
        self.assertEqual(TA.damage_bonus(self.e, self.p, self.b, move, 1), 6)
        self.native(self.p, self.b, 'move/물기')
        self.assertTrue(self.completed()['results'][self.b.entity_id]['hit'])
        self.valid()

    def test_wallclimber_blocks_tough_style_push_after_actual_hit(self):
        import style_expert as STYLE
        self.family('벌레', 'Insectoid Utility')
        self.capability(self.p, '벽타기')
        students = [self.add('actual Tough student '+str(i), 'pokemon', pos,
                            trainer_id=self.t.entity_id, poffins=['강인함']*3)
                    for i,pos in enumerate(((3,2),(7,5),(8,5)))]
        ACQUIRE.acquire_static(self.e,self.t,STYLE.CLASS,branch='강인함',acquisition_request_id='typeace/style/class')
        ACQUIRE.acquire_static(self.e,self.t,STYLE.RANKED['강인함'],rank=1,acquisition_request_id='typeace/style/rank')
        ACQUIRE.acquire_static(self.e,self.t,STYLE.IMPROVE['강인함'],acquisition_request_id='typeace/style/improvement')
        self.combat(students[0])
        with patch.object(Engine,'d20',return_value=15):
            self.e.style_move(self.t,students[0],self.p,'move/겁나는얼굴',
                              ranked=STYLE.RANKED['강인함'],effect=STYLE.IMPROVE['강인함'],set_damage=True)
        self.assertEqual(self.p.stages['spe'],-2)
        self.assertEqual(self.p.pos,(2,2))
        self.valid()

    def test_wallclimber_blocks_bigger_and_boulder_push_after_actual_rock_hit(self):
        self.family('벌레', 'Insectoid Utility')
        self.capability(self.p, '벽타기')
        skill = TA.SKILLS['바위'][0]
        self.t.spec['type_link_skills']['바위'] = skill
        self.e.gm.set_skill(self.t,skill,6,reason='actual second Master Type-linked skill')
        for pokemon in (self.p,self.q):
            self.e.gm.set_types(pokemon,['벌레','바위'],reason='actual dual matching owned pair')
        self.acquire(branch='바위')
        self.acquire('Gravel Before Me','바위')
        self.acquire('Bigger and Boulder','바위')
        self.combat(self.q)
        hp = self.p.hp
        self.native(self.q,self.p,'move/돌떨구기',face=15)
        row = self.completed(self.q)
        TA.react(self.e,self.t,self.q,TA.uid('Bigger and Boulder'),row['id'],
                 pushes={self.p.entity_id:{'direction':[-1,0],'distance':3}},rocks={})
        self.assertLess(self.p.hp,hp)
        self.assertEqual(self.p.pos,(2,2))
        self.assertIn('취약',self.p.conditions)
        self.valid()

    def test_wallclimber_rejects_melee_intercept_before_payment_and_keeps_pending_hit(self):
        import passive_events as PASSIVE
        self.family('벌레', 'Insectoid Utility')
        self.capability(self.p, '벽타기')
        self.e.gm.set_position(self.b,(3,2),reason='actual adjacent incoming attacker')
        self.combat(self.b)
        self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/근접-가로채기'}],
                                 reason='actual ally attempts to intercept')
        with patch.object(Engine,'d20',return_value=15),self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.b,self.p,'move/몸통박치기',set_damage=True)
        event = self.e._passive_pending
        options = {'path':[(2,3),(2,2)],'skill':'육상','shove_destination':[1,2],
                   'roll_options':{'fixed':(6,6,6,6,6,6)}}
        self.rejected(lambda:self.e.choose_move_defense(event,self.q,use=True,options=options,
                                                      reason='actual rejected Push against immunity'), 'Push immunity')
        self.assertEqual(self.e._passive_pending,event)
        self.e.choose_move_defense(event,self.q,use=False,reason='actual decline after immune ally')
        self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.p.pos,(2,2))
        self.valid()

    def test_cross_pollinate_actual_grass_user_gets_additional_status_move(self):
        self.family('풀', 'Foiling Foliage', 'Cross-Pollinate')
        self.known(self.p, 'move/메가드레인', 'move/광합성')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/메가드레인')
        self.react('Cross-Pollinate', move='move/광합성', target=self.p)
        self.assertEqual(self.completed()['move_id'], 'move/광합성')
        self.assertEqual(self.p.move_uses['move/광합성'], 1)
        self.assertEqual(self.p.budget['standard'], 0)
        self.valid()

    def test_mindbreak_disabled_adds_effect_range_and_actual_damage(self):
        self.family('에스퍼', 'Psionic Sponge', 'Mindbreak')
        self.sustain('Mindbreak')
        move = self.e.r.move('move/염동력')
        hp = self.b.hp
        self.native(self.p, self.b, 'move/염동력')
        ordinary = hp - self.b.hp
        self.next_turn(self.p)
        self.e.apply_status(self.p, '사슬묶기', source='move/사슬묶기',
                            parameters={'move_id':'move/몸통박치기'}, applied_by=self.b)
        self.assertIn('사슬묶기', self.p.conditions)
        self.assertEqual(TA.effect_range(self.e, self.p, move), 1)
        hp = self.b.hp
        self.native(self.p, self.b, 'move/염동력')
        self.assertEqual(hp - self.b.hp, ordinary + 3)
        self.valid()

    def test_trail_fire_has_native_hazard_effects_without_slow_terrain(self):
        self.family('불꽃', 'Brightest Flame', 'Trail Blazer')
        self.e.gm.set_position(self.b, (3, 5), reason='actual fire crossing recipient')
        self.combat(self.p)
        TA.trail(self.e, self.t, self.p, [(3,2),(4,2),(5,2)], mode='land')
        cells = {tuple(h['cell']) for h in self.hazards('fire')}
        self.assertEqual(cells, {(3,2),(4,2),(5,2)})
        self.assertFalse(cells.intersection(self.e.grid.slow))
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        hp = self.b.hp
        self.walk(self.b, [(3,4),(3,3),(3,2)])
        self.assertEqual(hp - self.b.hp, self.e.tick(self.b))
        self.e.end_of_turn(self.b)
        self.assertIn('화상', self.b.conditions)
        self.valid()

    def test_aqua_vortex_penalty_ends_with_its_occurrence_across_restore(self):
        self.family('물', 'Flood!', 'Aqua Vortex')
        self.combat(self.p)
        self.native(self.p, self.b, 'move/물대포')
        self.react('Aqua Vortex')
        move = self.e.r.move('move/몸통박치기')
        self.assertEqual(TA.damage_bonus(self.e, self.b, self.p, move, 1), -6)
        self.restore()
        self.assertEqual(TA.damage_bonus(self.e, self.b, self.p, move, 1), -6)
        self.e.cure_status(self.b, '조이기')
        self.assertFalse(any(r.get('ace_vortex') for r in TIME.records(self.b)))
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.q, initiative_count=20)
        self.native(self.q, self.b, 'move/바다회오리')
        self.assertIn('조이기', self.b.conditions)
        self.assertEqual(TA.damage_bonus(self.e, self.b, self.p, move, 1), 0)
        self.valid()

    def test_mold_requires_actual_capability_and_preserves_normal_range(self):
        for capable in (False, True):
            with self.subTest(capable=capable):
                self.family('땅', 'Mold the Earth')
                if capable:self.capability(self.p, '지형변화')
                self.combat(self.p)
                self.native(self.p, self.b, 'move/진흙뿌리기')
                changes = [{'cell':[1,2], 'terrain':'rough'}]
                operation = lambda:self.react('Mold the Earth', changes=changes,
                                              geometry='normal', reason='actual ordinary Groundshaper footprint')
                if not capable:
                    self.rejected(operation, 'Groundshaper capability')
                    continue
                operation()
                self.assertIn((1,2), self.e.grid.rough)
                self.assertEqual({tuple(h['cell']) for h in self.hazards('spikes')}, {(1,2)})
                self.assertEqual(self.p.budget['standard'], 0)
                self.valid()

    def test_upheaval_consumes_actual_capability_receipt_and_rejects_unrelated_move(self):
        self.family('땅', 'Mold the Earth', 'Upheaval')
        self.capability(self.p, '지형변화')
        self.e.gm.set_position(self.b, (3,2), reason='actual changed-square recipient')
        self.combat(self.p)
        self.e.shape_ground(self.p, [{'cell':[3,2], 'terrain':'rough'}], reason='actual Standard Groundshaper')
        self.rejected(lambda:TA.up_execution(self.e,self.t,self.p,None,[self.q]), 'Trip recipients')
        with patch.object(Engine, 'd20', return_value=20):
            TA.up_execution(self.e,self.t,self.p,None,[self.b],
                options={self.b.entity_id:{'challenger_skill':'전투','defender_skill':'전투',
                                           'challenger_options':{'fixed':(6,6,6,6,6,6)},
                                           'defender_options':{'fixed':(1,1,1,1,1,1)}}})
        self.assertIn('넘어짐', self.b.conditions)
        self.assertEqual(self.p.budget['standard'], 0)
        self.rejected(lambda:TA.up_execution(self.e,self.t,self.p,None,[self.b]), 'already consumed')
        self.next_turn(self.p)
        self.native(self.p, self.b, 'move/진흙뿌리기')
        row = self.completed()
        self.rejected(lambda:TA.up_execution(self.e,self.t,self.p,row['id'],[self.b]), 'Groundsource')
        self.valid()

    def test_upheaval_observed_trip_retains_payment_and_resumes_only_its_actual_event(self):
        import skill_feature_actions as SKILL
        import skill_maneuver_actions as MANEUVER
        self.family('땅', 'Mold the Earth', 'Upheaval')
        self.capability(self.p, '지형변화')
        self.e.gm.set_position(self.b,(3,2),reason='actual changed-cell and Groundsource recipient')
        self.combat(self.p)
        self.native(self.p,self.b,'move/대지의힘')
        move_event = self.completed()['id']
        self.react('Mold the Earth',changes=[{'cell':[3,2],'terrain':'rough'}],
                   geometry='normal',reason='actual free Groundshaper after Groundsource')
        options = {self.b.entity_id:{'fixed_accuracy':20,'challenger_skill':'전투','defender_skill':'전투',
                    'challenger_options':{'fixed':(6,6,6,6,6,6)},
                    'defender_options':{'fixed':(1,1,1,1,1,1)}}}
        bad = {self.b.entity_id:dict(options[self.b.entity_id],defender_options={'fixed':(7,)*6})}
        self.rejected(lambda:TA.up_execution(self.e,self.t,self.p,None,[self.b],options=bad),'d6 face')
        native_roll = self.e.skill_roll
        def interrupt_defender(actor,skill,**kwargs):
            if actor is self.b:raise RuntimeError('native interruption after observed challenger')
            return native_roll(actor,skill,**kwargs)
        with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as accuracy:
            with patch.object(self.e,'skill_roll',side_effect=interrupt_defender):
                with self.assertRaisesRegex(RuntimeError,'native interruption'):
                    TA.up_execution(self.e,self.t,self.p,None,[self.b],options=options)
            record = self.p.custom_conditions[MANEUVER.RECEIPTS][self.p.custom_conditions[MANEUVER.ACTIVE]]
            self.assertEqual(record['stage'],'skill')
            self.assertEqual(record['basis']['upheaval_event'],{'groundshaper_sequence':1})
            roll_id = record['requests'][0][-1]
            observed = SKILL.event(self.e,self.p,roll_id).first
            rng = self.e.rng.getstate()
            actions = (list(self.t._action_history),list(self.p._action_history))
            paid = len([r for r in self.p.spec[TA.KEY] if r['source']==TA.uid('Upheaval')])
            self.assertEqual(paid,1)
            self.assertNotIn('넘어짐',self.b.conditions)
            # This actual Groundsource has the same target and Feature, but is
            # a different event from the interrupted Groundshaper activation.
            self.rejected(lambda:TA.up_execution(self.e,self.t,self.p,move_event,[self.b],options=options),
                          'finish the actually observed maneuver')
            self.assertEqual(TA.up_execution(self.e,self.t,self.p,None,[self.b],options=options),[True])
            self.assertEqual(accuracy.call_count,1)
            self.assertEqual(self.e.rng.getstate(),rng)
            self.assertIs(SKILL.event(self.e,self.p,roll_id).first,observed)
            self.assertEqual((self.t._action_history,self.p._action_history),actions)
            self.assertEqual(len([r for r in self.p.spec[TA.KEY] if r['source']==TA.uid('Upheaval')]),paid)
        self.assertIn('넘어짐',self.b.conditions)
        self.assertNotIn(MANEUVER.ACTIVE,self.p.custom_conditions)
        self.rejected(lambda:TA.up_execution(self.e,self.t,self.p,None,[self.b],options=options),'already consumed')
        self.valid()

    def test_new_normal_maximum_survives_formula_and_retains_ordinary_stab(self):
        for move, expected in (('move/은혜갚기',11), ('move/쥐어짜기',14), ('move/원수갚기',16)):
            with self.subTest(move=move):
                self.family('노말', 'Extra Ordinary', 'New Normal')
                self.e.gm.observe_loyalty(self.p, 2, reason='actual conditional Return loyalty')
                self.e.gm.set_position(self.b, (3,2), reason='actual adjacent conditional attack target')
                self.e.gm.set_hp(self.b, value=self.b.base_max_hp//2, reason='actual reduced Wring Out target HP')
                self.combat(self.p)
                hp = self.b.hp
                self.selected('New Normal', move)
                row = self.completed()
                self.assertTrue(row['results'][self.b.entity_id]['hit'])
                self.assertLess(self.b.hp, hp)
                self.assertEqual(self.e.damage_base(self.p, row['move'], target=self.b), expected)
                self.assertEqual(FREQUENCY.state(self.p)['activations'][TA.uid('New Normal')]['used'], 1)
                self.valid()

    def test_gravel_uses_one_faint_producer_and_keeps_independent_injury(self):
        self.family('바위', 'Gravel Before Me')
        self.answer('type_ace_choice', True)
        self.answer('type_ace_stealth_rock_cell', [3,1])
        self.e.gm.set_position(self.b, (3,3), reason='actual adjacent attacker')
        self.combat(self.b)
        self.e.gm.set_hp(self.p, value=3, reason='actual nearly fainted recipient')
        injuries = self.p.injuries
        self.native(self.b, self.p, 'move/몸통박치기', face=10)
        self.assertTrue(self.p.fainted)
        self.assertEqual(self.p.injuries - injuries, 1)
        self.assertEqual(len(self.hazards('stealth_rock')), 2)
        self.valid()

    def test_blight_refreshes_one_condition_for_two_actual_issuers(self):
        self.family('독', 'Potent Venom', 'Corrosive Blight')
        self.e.gm.set_position(self.b, (3,2), reason='actual adjacent Blight recipient')
        self.e.gm.set_position(self.q, (3,3), reason='actual second Poison issuer')
        self.combat(self.q)
        hp = self.b.hp
        self.native(self.q, self.b, 'move/몸통박치기')
        ordinary = hp - self.b.hp
        self.next_turn(self.p)
        self.native(self.p, self.b, 'move/독침')
        self.react('Corrosive Blight')
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.q, initiative_count=20)
        self.native(self.q, self.b, 'move/독침')
        TA.react(self.e,self.t,self.q,TA.uid('Corrosive Blight'),self.completed(self.q)['id'])
        self.assertEqual(len([r for r in TIME.records(self.b) if r.get('ace_blight')]), 1)
        self.next_turn(self.p)
        hp = self.b.hp
        self.native(self.p, self.b, 'move/몸통박치기')
        self.assertEqual(hp - self.b.hp, ordinary + self.e.tick(self.b))
        self.valid()

    def test_enduring_bloom_excludes_virtual_sun_for_book_and_csv_acquisition(self):
        self.family('풀', 'Foiling Foliage', 'Sunlight Within', 'Enduring Bloom')
        self.e.gm.set_position(self.b, (3,2), reason='actual adjacent Fire attacker')
        self.e.gm.set_types(self.b, ['불꽃'], reason='actual Fire attacker')
        self.sustain('Sunlight Within')
        self.assertIsNone(self.e.weather)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.native(self.b, self.p, 'move/화염방사')
        pending = self.e.pending_class_actor_state_reactions(self.t)
        self.assertEqual([(row['source'],row['sunny']) for row in pending], [(REACTIONS.ENDURING_BLOOM,False)])
        self.assertEqual(pending[0]['clause_id'], 'C2CSV/input/db/feats.csv:R267:main')
        self.rejected(lambda:self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True,stats=('def','spd')),
                      'optional different Sunny')
        self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True,stats=('def',))
        self.assertEqual((self.p.stages['def'],self.p.temp_hp), (1,12))
        self.valid()

    def test_face_me_whole_area_targets_marker_even_when_other_recipient_is_first(self):
        losses = []
        for enabled in (False, True):
            features = ('Close Quarters Mastery','Face Me Whelp') if enabled else ('Close Quarters Mastery',)
            self.family('격투', *features)
            self.e.gm.set_position(self.p, (3,2), reason='actual adjacent Fighting marker')
            self.e.gm.set_position(self.q, (4,3), reason='actual first area recipient')
            self.sustain('Close Quarters Mastery')
            self.native(self.p, self.b, 'move/태권당수')
            self.assertIs(TA.marked(self.e,self.b), self.p)
            self.e.end_of_turn(self.p)
            self.e.start_of_turn(self.b, initiative_count=20)
            hp = self.q.hp
            self.native(self.b, self.q, 'move/땅고르기', face=15)
            row = self.completed(self.b)
            self.assertIn(self.p, row['targets'])
            self.assertIn(self.q, row['targets'])
            losses.append(hp - self.q.hp)
            self.valid()
        self.assertEqual(losses[0], losses[1])
