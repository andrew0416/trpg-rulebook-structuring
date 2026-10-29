"""Type Ace attack, terrain and shared-pool consumers on actual native events."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'),str(ROOT / 'tools')]
import test_book_type_ace_acquisition as FIX
from engine import Engine
import blessing_effects as BLESSINGS
import combat_timing as TIME
import frequency as FREQUENCY
import grapple_state as GRAPPLE
import hazard_state as HAZARDS
import held_equipment as HELD
import items as ITEMS
import movement_actions as MOVEMENT
import physics_maneuvers as MANEUVERS
import pokemon_move_edges as EDGES
import state_fields as FIELDS
import state_grants as GRANTS
import terrain_actions as TERRAIN
import turn as TURN
import type_ace as TA
import world_entities as WORLD


class TypeAceReactionTests(unittest.TestCase):
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

    def family(self, branch, *features):
        self.setup()
        skill = TA.SKILLS[branch][0]
        self.t.spec['type_link_skills'][branch] = skill
        self.e.gm.set_skill(self.t,skill,6,reason='actual Master Type-linked skill')
        for pokemon in (self.p,self.q):
            self.e.gm.set_types(pokemon,[branch],reason='actual matching owned Pokemon pair')
        self.acquire(branch=branch)
        for feature in features:self.acquire(feature,branch)

    def known(self, actor, *moves):
        for move in moves:
            if move not in actor.moves:
                self.e.gm.set_move(actor,move,reason='actual complete known Move list')

    def answer(self, key, value):
        self.e.rulings.answers[:] = [a for a in self.e.rulings.answers if a['key'] != key]
        self.e.rulings.add_answer(key,value,reason='actual selected native scene choice')

    def native(self, actor, target, move, *, face=10, aim=None):
        self.known(actor,move)
        with patch.object(Engine,'d20',return_value=face):
            return self.e.use_move_on(actor,target,move,self.e.everyone,aim=aim,set_damage=True)

    def selected(self, feature, move, *, target=None, face=10, **options):
        if move != 'struggle':self.known(self.p,move)
        with patch.object(Engine,'d20',return_value=face):
            return TA.use_move(self.e,self.t,self.p,target or self.b,move,
                feature=TA.uid(feature),set_damage=True,**options)

    def completed(self, actor=None, move=None):
        actor = self.p if actor is None else actor
        return next(row for row in reversed(list(self.e._move_completions.values()))
            if row['actor'] is actor and row['phase']=='complete'
            and (move is None or row['move_id']==move))

    def react(self, feature, row=None, **options):
        row = self.completed() if row is None else row
        return TA.react(self.e,self.t,self.p,TA.uid(feature),row['id'],**options)

    def sustain(self, feature):
        self.communication()
        self.combat(self.t)
        TA.activate(self.e,self.t,self.p,TA.uid(feature))
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p,initiative_count=30)

    def walk(self, actor, path):
        self.assertTrue(TURN.spend(self.e,actor,'shift','actual observed Shift',movement=True))
        return MOVEMENT.follow_paid_path(self.e,actor,path,mode='land',
            maximum_distance=MOVEMENT.distance_budget(self.e,actor,'land'))

    def hazards(self, kind):
        return [h for env in HAZARDS.ensure(self.e).values() for h in env['instances'] if h['kind']==kind]

    def test_area_move_adapters_use_actual_targets_types_shift_cost_and_source_geometry(self):
        rows = [
            ('격투',('Close Quarters Mastery','Brawler'),'Brawler','struggle',None,'burst','격투','standard'),
            ('불꽃',('Brightest Flame','Fan The Flames'),'Fan The Flames','move/불꽃펀치',None,'burst','불꽃','standard'),
            ('불꽃',('Brightest Flame','Fan The Flames'),'Fan The Flames','move/불꽃세례',None,'cone','불꽃','standard'),
            ('땅',('Mold the Earth','Earthroil'),'Earthroil','move/진흙뿌리기','line','line','땅','shift'),
            ('땅',('Mold the Earth','Earthroil'),'Earthroil','move/진흙뿌리기','burst','burst','땅','shift'),
            ('물',('Flood!',),'Flood!','move/물대포','line','line','물','shift'),
            ('물',('Flood!',),'Flood!','move/물대포','close_blast','close_blast','물','shift')]
        for branch,features,feature,move,choice,shape,kind,action in rows:
            with self.subTest(feature=feature,choice=choice,move=move):
                self.family(branch,*features)
                self.e.gm.set_position(self.b,(3,2),reason='actual first adjacent foe')
                second = self.add('second actual area foe','pokemon',(3,3),side='foe')
                self.combat(self.p)
                hp = self.q.hp
                self.selected(feature,move,choice=choice,aim=(3,2) if shape in ('line','cone','close_blast') else None)
                row = self.completed()
                self.assertEqual(row['move']['type'],kind)
                self.assertEqual(row['move']['_class_move_range']['shape'],shape)
                self.assertIn(self.b,row['targets'])
                if shape=='burst':self.assertIn(second,row['targets'])
                if feature=='Brawler':self.assertEqual(self.q.hp,hp)
                if feature=='Earthroil':self.assertIn('지면통과',row['move']['keywords'])
                self.assertEqual(self.p.budget[action],0)
                if action=='shift':self.assertEqual(self.p.budget['standard'],1)
                self.valid()

    def test_actual_mark_face_me_and_smite_opportunity_follow_disengaging_departure(self):
        import attack_damage_history as HISTORY
        self.family('격투','Close Quarters Mastery','Face Me Whelp','Smashing Punishment')
        self.e.gm.set_position(self.p,(3,2),reason='actual adjacent Fighting marker')
        self.sustain('Close Quarters Mastery')
        self.native(self.p,self.b,'move/태권당수')
        self.assertIs(TA.marked(self.e,self.b),self.p)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b,initiative_count=20)
        # A ranged attack beside the marker would already provoke this round's single
        # opportunity attack; the departure must be the actual trigger.
        self.e.gm.set_position(self.q,(5,3),reason='actual adjacent non-marker target')
        self.native(self.b,self.q,'move/몸통박치기')
        attack = self.completed(self.b)['move']
        self.assertEqual(TA.accuracy(self.e,self.b,self.q,attack,{}),-3)
        self.assertEqual(TA.damage_bonus(self.e,self.b,self.q,attack,1),-10)
        self.answer('type_ace_choice',True)
        hp = self.b.hp
        history_before = len(HISTORY.records(self.b))
        with patch.object(Engine,'d20',return_value=1):
            TA.disengage(self.e,self.b,[(5,2)])
        self.assertEqual(self.b.pos,(5,2))
        self.assertLess(self.b.hp,hp)
        rows = HISTORY.records(self.b)[history_before:]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['receipt']['source'], 'struggle')
        self.assertEqual(rows[0]['move_type'], '격투')
        self.assertEqual(HISTORY.amount(rows[0]), hp - self.b.hp)
        opportunity = self.completed(self.p,'struggle')
        self.assertEqual(opportunity['move']['type'],'격투')
        self.assertTrue(TA._completed_targets(opportunity))
        self.valid()

    def test_gneiss_aim_native_miss_records_one_attack_and_pays_feature_once(self):
        import attack_damage_history as HISTORY
        self.family('바위', 'Gravel Before Me', 'Gneiss Aim')
        self.known(self.p, 'move/돌떨구기')
        self.answer('type_ace_choice', False)
        self.combat(self.p)
        before = self.b.hp
        self.selected('Gneiss Aim', 'move/돌떨구기', face=1)
        completion = self.completed(self.p, 'move/돌떨구기')
        self.assertFalse(completion['results'][self.b.entity_id]['hit'])
        self.assertLess(self.b.hp, before)
        rows = HISTORY.records(self.b)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['receipt']['source'], 'move/돌떨구기')
        self.assertEqual(rows[0]['move_type'], '바위')
        self.assertEqual(rows[0]['attacker_id'], self.p.entity_id)
        self.assertEqual(HISTORY.amount(rows[0]), before - self.b.hp)
        self.assertEqual(self.p.move_uses['move/돌떨구기'], 1)
        self.assertEqual(FREQUENCY.state(self.t)['activations'][TA.uid('Gneiss Aim')]['used'], 1)
        self.assertEqual(self.p.budget['standard'], 0)
        self.valid()

    def test_additional_moves_devious_normal_social_cross_non_grass_and_force_distinct(self):
        rows = [
            ('악',('Clever Ruse','Devious'),'Devious','move/울음소리','move/거짓울음',False),
            ('풀',('Foiling Foliage','Cross-Pollinate'),'Cross-Pollinate','move/메가드레인','move/광합성',True),
            ('에스퍼',('Psionic Sponge','Force of Will'),'Force of Will','move/고속이동','move/빛의장막',False)]
        for branch,features,feature,trigger,extra,grass_required in rows:
            for eligible in ((False, True) if grass_required else (True,)):
                with self.subTest(feature=feature,eligible=eligible):
                    # Each positive has a fresh actual qualifying native hit;
                    # changing type after a rejected non-Grass hit is no trigger.
                    self.family(branch,*features)
                    if not eligible:
                        self.e.gm.set_types(self.p,['노말'],reason='actual non-Grass Cross-Pollinate rejection control')
                    self.e.gm.set_position(self.b,(3,2),reason='actual Social burst target')
                    self.known(self.p,trigger,extra)
                    self.combat(self.p)
                    self.native(self.p,self.p if feature=='Force of Will' else self.b,trigger)
                    actual = self.completed()
                    if not eligible:
                        self.assertEqual(actual['move']['type'],'풀')
                        self.assertNotEqual(actual['move']['class'],'변화')
                        self.rejected(lambda:self.react(feature,actual,move=extra,target=self.p),
                                      'actual Grass Pokemon required')
                        self.assertNotIn(extra,self.p.move_uses)
                        self.valid()
                        continue
                    if feature=='Force of Will':
                        self.rejected(lambda:self.react(feature,actual,move=trigger,target=self.p),'different')
                    self.react(feature,actual,move=extra,target=self.p if feature!='Devious' else self.b)
                    self.assertEqual(self.p.budget['standard'],0)
                    self.assertEqual(self.completed()['move_id'],extra)
                    self.assertEqual(self.p.move_uses[extra],1)
                    self.valid()

    def test_psychic_resonance_encore_uses_triggering_foe_and_native_prior_move(self):
        self.family('에스퍼','Psionic Sponge','Psychic Resonance')
        self.combat(self.b)
        self.native(self.b,self.p,'move/거짓울음')
        self.e.end_of_turn(self.b)
        self.e.start_of_turn(self.p,initiative_count=10)
        self.native(self.p,self.b,'move/최면술')
        row = self.completed()
        self.rejected(lambda:self.react('Psychic Resonance',row,target=self.q),'triggering|foe|hit')
        self.react('Psychic Resonance',row,target=self.b)
        encore = self.completed(move='move/앙코르')
        self.assertEqual(encore['targets'],[self.b])
        self.assertNotIn('move/앙코르',self.p.moves)
        self.assertEqual(self.p.budget['standard'],0)
        self.valid()

    def test_miasma_native_smoke_center_ignores_frequency_and_only_poison_is_exempt(self):
        self.family('독','Potent Venom','Miasma')
        self.combat(self.p)
        self.native(self.p,self.b,'move/독침',face=1)
        self.react('Miasma',move='move/연막',target=self.b)
        first = self.completed(move='move/연막')
        self.assertEqual(first['move']['_class_move_range']['size'],3)
        self.assertEqual(self.p.budget['standard'],0)
        self.assertNotIn('move/연막',self.p.moves)
        self.next_turn(self.p)
        # The printed deliberate Standard branch uses the same extra-Move path.
        TA.special(self.e,self.t,self.p,TA.uid('Miasma'),target=self.b,move='move/연막')
        self.assertEqual(len([r for r in self.e._move_completions.values() if r['actor'] is self.p and r['move_id']=='move/연막' and r['phase']=='complete']),2)
        self.assertNotIn('move/연막',self.p.move_uses)  # frequency ignored: the ledger records no ordinary use
        self.assertEqual(self.p.budget['standard'],0)
        self.valid()

    def test_chain_lightning_uses_three_actual_damage_rolls_and_stops_after_second_miss(self):
        for miss_second in (False,True):
            with self.subTest(miss_second=miss_second):
                self.family('전기','Lockdown','Chain Lightning')
                second = self.add('second chain recipient','pokemon',(7,2),side='foe')
                third = self.add('third chain recipient','pokemon',(10,2),side='foe')
                self.combat(self.p)
                self.native(self.p,self.b,'move/전기쇼크')
                actual = self.completed()
                before = second.hp,third.hp
                self.rejected(lambda:self.react('Chain Lightning',actual,targets=[second,self.b]),'third|geometry')
                with patch.object(Engine,'d20',side_effect=[1] if miss_second else [10,10]):
                    self.react('Chain Lightning',actual,targets=[second,third],set_damage=True)
                self.assertEqual(self.p.budget['standard'],0)
                if miss_second:self.assertEqual((second.hp,third.hp),before)
                else:
                    self.assertLess(second.hp,before[0])
                    self.assertLess(third.hp,before[1])
                    self.assertGreater(before[0]-second.hp,before[1]-third.hp)
                self.valid()

    def test_gale_strike_two_actual_accuracy_faces_only_free_when_lower_also_hits(self):
        for faces,choice,consumed in (((10,15),'first',False),((10,15),'second',True),((1,15),'second',True)):
            with self.subTest(faces=faces,choice=choice):
                self.family('비행','Celerity','Gale Strike')
                self.known(self.p,'move/바람일으키기')
                self.combat(self.p)
                self.answer('type_ace_gale_strike',choice)
                with patch.object(Engine,'d20',side_effect=faces) as dice:
                    TA.use_move(self.e,self.t,self.p,self.b,'move/바람일으키기',
                        feature=TA.uid('Gale Strike'),set_damage=True)
                self.assertEqual(dice.call_count,2)
                feature = TA.uid('Gale Strike')
                used = not FREQUENCY.activation_allowed(self.t,feature,{'kind':'scene','uses':1},engine=self.e)
                self.assertEqual(used,consumed)
                self.assertEqual(self.p.budget['standard'],0)
                self.valid()

    def test_shocking_speed_advanced_borrows_actual_scheduled_turn_for_at_will_electric_move(self):
        self.family('전기','Lockdown','Shocking Speed')
        self.known(self.p,'move/전기쇼크')
        for actor,speed in ((self.p,30),(self.t,25),(self.q,15),(self.b,10)):
            self.e.gm.set_stat(actor,'spe',value=speed,reason='actual distinct Speeds for a decidable schedule')
        self.e.prepare_initiative_schedule(self.e.everyone,source='gm/type-ace-native-schedule')
        self.e.start_round(self.e.everyone)
        hp = self.b.hp
        self.selected('Shocking Speed','move/전기쇼크')
        self.assertIs(self.e._active_turn_actor,self.p)
        self.assertEqual(self.p.budget['standard'],0)
        self.assertLess(self.b.hp,hp)
        self.assertEqual(self.p.move_uses['move/전기쇼크'],1)
        self.e.finish_initiative_reaction()
        self.valid()

    def test_disruption_followup_damaging_sixteen_flinches_recipient_and_status_does_not(self):
        for damaging,face in ((True,15),(True,16),(False,16)):
            with self.subTest(damaging=damaging,face=face):
                self.family('벌레','Insectoid Utility','Disruption Order')
                self.combat(self.p)
                self.native(self.p,self.b,'move/벌레의저항')
                self.react('Disruption Order')
                self.assertIn('둔화',self.b.conditions)
                self.e.end_of_turn(self.p)
                self.e.start_of_turn(self.q,initiative_count=20)
                self.native(self.q,self.b,'move/물대포' if damaging else 'move/거짓울음',face=face)
                self.assertEqual('풀죽음' in self.b.conditions,damaging and face>=16)
                self.assertNotIn('풀죽음',self.q.conditions)
                self.valid()

    def test_reaction_conditions_use_native_hit_recipients_and_printed_expiry(self):
        cases = [
            ('드래곤',('Tyrant’s Roar',),'Tyrant’s Roar','move/용의숨결'),
            ('페어리',('Fairy Lights','Arcane Favor'),'Arcane Favor','move/요정의바람'),
            ('고스트',('Ghost Step','Vampirism'),'Vampirism','move/핥기'),
            ('얼음',('Glacial Ice','Deep Cold'),'Deep Cold','move/얼음뭉치')]
        for branch,features,feature,move in cases:
            with self.subTest(feature=feature):
                self.family(branch,*features)
                self.e.gm.set_position(self.p,(3,2),reason='actual adjacent reaction user')
                self.e.gm.set_types(self.b,['물'],reason='actual nonimmune reaction foe')
                if feature=='Tyrant’s Roar':
                    self.e.change_stage(self.b,'atk',2)
                    self.e.change_stage(self.b,'spa',-1)
                self.combat(self.p)
                self.native(self.p,self.b,move)
                hp = self.b.hp
                if feature!='Deep Cold':self.react(feature,**({'stat':'def'} if feature=='Vampirism' else {}))
                if feature=='Tyrant’s Roar':
                    self.assertIn('둔화',self.b.conditions)
                    self.assertEqual((self.b.stages['atk'],self.b.stages['spa']),(1,-1))
                elif feature=='Arcane Favor':
                    self.assertTrue(all(TA.all_rolls(a)==1 for a in (self.t,self.p,self.q)))
                    self.assertEqual(TA.all_rolls(self.b),0)
                elif feature=='Vampirism':
                    self.assertEqual(hp-self.b.hp,self.e.tick(self.b))
                    self.assertEqual((self.b.stages['def'],self.p.stages['def']),(-1,1))
                    self.assertEqual(self.p.temp_hp,self.e.tick(self.p))
                else:
                    # Deep Cold (1701-1705) is owned by the existing pending-reaction owner.
                    import class_actor_state_reactions as REACTIONS
                    pending=self.e.pending_class_actor_state_reactions(self.t)
                    self.assertEqual([row['source'] for row in pending],[REACTIONS.DEEP_COLD])
                    self.rejected(lambda:self.react('Deep Cold'),'native incoming/action producer|accepted or declined')
                    self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True)
                    self.assertIn('얼음',self.b.conditions)
                    self.assertEqual([self.b.stages[s] for s in ('atk','spa','spe')],[-1,-1,-1])
                    self.next_turn(self.p)
                    self.assertNotIn('얼음',self.b.conditions)
                    self.native(self.p,self.b,move)
                    self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))
                self.valid()

    def test_enduring_bloom_uses_existing_pending_reaction_owner_with_rank_and_sunny(self):
        import class_actor_state_reactions as REACTIONS
        self.family('풀','Foiling Foliage','Enduring Bloom')
        self.e.gm.set_position(self.b,(3,2),reason='actual adjacent attacker')
        self.e.gm.set_types(self.b,['불꽃'],reason='actual Fire attacker')
        self.combat(self.b)
        self.native(self.b,self.p,'move/화염방사')
        pending=self.e.pending_class_actor_state_reactions(self.t)
        self.assertEqual([(row['source'],row['sunny']) for row in pending],[(REACTIONS.ENDURING_BLOOM,False)])
        self.rejected(lambda:self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True,stats=('def','spd')),
            'optional different Sunny')
        result=self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True,stats=('def',))
        self.assertEqual((result['type_link_rank'],result['temporary_hp_granted']),(6,12))
        self.assertEqual((self.p.stages['def'],self.p.temp_hp),(1,12))
        self.next_turn(self.b)
        self.native(self.b,self.p,'move/화염방사')
        self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))
        self.next_turn(self.b)
        self.e.gm.set_weather('sunny',reason='actual sourced field weather')
        self.native(self.b,self.q,'move/화염방사')
        pending=self.e.pending_class_actor_state_reactions(self.t)
        self.assertEqual([(row['source'],row['sunny']) for row in pending],[(REACTIONS.ENDURING_BLOOM,True)])
        # Sunny allows one optional different stat; the same stat twice is rejected atomically.
        self.rejected(lambda:self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True,stats=('def','def')),
            'distinct')
        self.e.resolve_class_actor_state_reaction(self.t,pending[0]['id'],use=True,stats=('def','spd'))
        self.assertEqual((self.q.stages['def'],self.q.stages['spd'],self.q.temp_hp),(1,1,12))
        self.valid()

    def test_errata_this_will_not_stand_suppresses_legacy_critical_offer_for_receipted_owner(self):
        self.family('드래곤','Tyrant’s Roar','This Will Not Stand')
        self.e.gm.set_position(self.b,(3,2),reason='actual adjacent attacker')
        self.combat(self.b)
        self.native(self.b,self.p,'move/몸통박치기',face=20)
        self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))
        self.assertEqual([self.p.stages[s] for s in ('atk','spa','spe')],[0,0,0])
        self.answer('type_ace_choice',True)
        self.next_turn(self.b)
        self.e.gm.set_hp(self.p,value=self.p.max_hp//2+1,reason='actual HP immediately above half')
        self.native(self.b,self.p,'move/몸통박치기',face=20)
        self.assertFalse(self.e.pending_class_actor_state_reactions(self.t))
        self.assertEqual([self.p.stages[s] for s in ('atk','spa','spe')],[1,1,1])
        self.assertIn('난동',self.p.conditions)
        self.valid()
