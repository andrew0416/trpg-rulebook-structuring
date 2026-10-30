"""NEW4: real move/faint/position/recall producers, never invented hit receipts."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from grid import Grid
import ability_transitions as A
import ability_exchange_contracts as X
import state_grants as G
import combat_timing as TIME
from native_scenario_fixture import assert_rejected_unchanged

MOVES=['move/몸통박치기','move/물대포',X.ENTRAIN,'move/독가스','move/스모그','move/클리어스모그','move/원더스팀']


class AbilityExchangeContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')

    def setUp(self):
        self.e=Engine(self.r,530);self.e.grid=Grid(30,30)
        self.a=self.actor('attacker',[],(2,2),'party')
        self.t=self.actor('target',[],(3,2),'opponent')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def actor(self,name,abilities,pos,side,*,pokemon=False):
        moves=MOVES[:1] if pokemon else MOVES
        extra={'abilities':abilities,'size':'중형','pos':pos,'side':side,'moves':moves}
        spec=(build_pokemon(self.r,'이상해씨',10,name=name,moves=moves,extra=extra) if pokemon else
              build_trainer(self.r,name,10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra=extra))
        c=Combatant(self.r,spec);self.e.gm.add_combatant(c)
        c.damage_cap={'value':1}
        return c

    def give(self,c,abilities):G.replace_baseline(self.e,c,'abilities',abilities)

    def choose(self,c,target,uid,ability=None,allies=(),**options):
        return self.e.gm.choose_ability_transition(c,target,uid,ability=ability,allies=allies,
                                                  reason='actual owner choice before the native producer',**options)

    def hit(self,a=None,t=None,move='move/몸통박치기'):
        return self.e.use_move(a or self.a,t or self.t,move,set_damage=True)

    def live(self,c):return [r for r in TIME.records(c) if X.TAG in r]

    def next_round(self,c,count=20):
        active=getattr(self.e,'_active_turn_actor',None)
        if active is not None:self.e.end_of_turn(active)
        self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(c,initiative_count=count)

    def core_mummy(self,c):
        self.e.end_encounter(self.e.everyone)
        self.choose(c,c,X.MUMMY,edition='core')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        return self.choose(c,c,X.MUMMY)

    def fresh(self):
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        e=Engine.import_state(Rules(ROOT,ruleset='all'),saved)
        return e,{c.entity_id:c for c in e.everyone}

    def shield(self,c):
        import items as ITEMS
        import world_entities as WORLD
        uid='ability-exchange/shield/'+c.entity_id
        WORLD.register_object(self.e,uid,kind='item_instance',item_rule_id='item/특성가드',
                              owner_id=c.entity_id,location={'kind':'unknown'},reason='actual owned Ability Shield fixture')
        ITEMS.register_item(self.e,c,'item/특성가드',source_instance_id=uid,as_held=False)

    def test_registration_uses_source_owned_passives_not_csv_poison_guess(self):
        for name in ['리시버','미라 [Playtest]','화학변화가스','화학변화가스-2']:
            with self.subTest(name=name):
                c=self.actor(name,[name],(10,10),'party')
                self.assertTrue(A.active(c,X.source(self.r,name)))
                self.assertNotIn('독',c.conditions)
                self.assertTrue(c.spec[G.KEY]['ability_receipts'])
        self.assertEqual(A.ability_id(self.r,'화학변화가스-2'),X.GAS)

    def test_mummy_playtest_suppresses_one_user_ability_not_attackers(self):
        self.give(self.t,['미라 [Playtest]','불요의검','불굴의방패']);self.give(self.a,['단순'])
        self.choose(self.t,self.t,X.MUMMY,'불요의검');baseline=deepcopy(self.t.spec['abilities'])
        self.hit()
        self.assertEqual(self.a.abilities,['단순'])
        self.assertNotIn('불요의검',self.t.abilities);self.assertIn('불굴의방패',self.t.abilities)
        self.assertEqual(self.t.spec['abilities'],baseline);self.assertEqual(self.live(self.t)[0]['ends'],['scene_end','recall'])
        self.assertEqual(self.t._action_history,['free'])

    def test_mummy_playtest_can_disable_itself_then_recall_restores_only_own_source(self):
        self.give(self.t,['미라 [Playtest]','단순']);self.choose(self.t,self.t,X.MUMMY,X.MUMMY)
        self.hit();self.assertFalse(A.active(self.t,X.MUMMY));self.assertIn('단순',self.t.abilities)
        self.e.gm.recall(self.t,reason='actual switch ends PT Mummy')
        self.assertTrue(A.active(self.t,X.MUMMY));self.assertEqual(self.live(self.t),[])

    def test_mummy_no_melee_hit_or_real_miss_has_no_reaction_cost(self):
        for move,seed in [('move/물대포',530),('move/몸통박치기',31)]:
            with self.subTest(move=move):
                self.setUp();self.give(self.t,['미라 [Playtest]','단순'])
                self.choose(self.t,self.t,X.MUMMY,'단순');self.e.rng.seed(seed)
                self.hit(move=move)
                self.assertIn('단순',self.t.abilities);self.assertEqual(self.live(self.t),[])
                self.assertEqual(getattr(self.t,'_action_history',[]),[])

    def test_mummy_core_replaces_all_actual_attacker_abilities_but_preserves_multitype(self):
        self.give(self.t,['미라 [Playtest]','불요의검']);self.give(self.a,['단순','멀티타입','불굴의방패'])
        self.core_mummy(self.t);self.hit()
        self.assertEqual(set(self.a.abilities),{'미라 [Playtest]','멀티타입'})
        self.assertIn('불요의검',self.t.abilities)
        self.assertEqual(self.live(self.a)[0]['ends'],['encounter'])
        self.e.end_encounter(self.e.everyone)
        self.assertEqual(set(self.a.abilities),{'단순','멀티타입','불굴의방패'})

    def test_mummy_core_propagated_identity_keeps_core_default_edition(self):
        self.give(self.t,['미라 [Playtest]']);self.give(self.a,['단순'])
        self.core_mummy(self.t);self.hit()
        self.assertEqual(X._edition(self.a),'core')
        request=self.choose(self.a,self.a,X.MUMMY)
        self.assertEqual(request['edition'],'core')
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        self.hit(self.t,self.a)
        app=list(self.e._move_completions.values())[-1][X.TAG][-1]
        self.assertEqual(app['edition'],'core');self.assertEqual(app['recipient'].entity_id,self.t.entity_id)

    def test_direct_trigger_activation_and_wrong_edition_are_rejected_without_mutation(self):
        self.give(self.t,['미라 [Playtest]'])
        assert_rejected_unchanged(self.e,lambda:self.e.activate_ability(self.t,X.MUMMY,self.a),reason_pattern='native trigger')
        assert_rejected_unchanged(self.e,lambda:self.choose(self.t,self.t,X.MUMMY,edition='unknown'),reason_pattern='edition')

    def test_mummy_edition_is_preencounter_only_and_daily_quota_cannot_be_laundered(self):
        self.give(self.t,['미라 [Playtest]'])
        assert_rejected_unchanged(self.e,lambda:self.choose(self.t,self.t,X.MUMMY,edition='core'),reason_pattern='before encounter')
        self.core_mummy(self.t);self.hit();self.e.end_encounter(self.e.everyone)
        self.choose(self.t,self.t,X.MUMMY,edition='playtest')
        self.give(self.t,[]);self.give(self.t,['미라 [Playtest]'])
        self.choose(self.t,self.t,X.MUMMY,edition='core')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        assert_rejected_unchanged(self.e,lambda:self.choose(self.t,self.t,X.MUMMY),reason_pattern='frequency exhausted')

    def test_entrainment_missing_or_stale_choice_rejects_before_move_cost_rng(self):
        self.give(self.a,['단순'])
        assert_rejected_unchanged(self.e,lambda:self.hit(move=X.ENTRAIN),reason_pattern='active donor ability choice')
        self.choose(self.a,self.t,X.ENTRAIN,'단순');self.give(self.a,['불면'])
        assert_rejected_unchanged(self.e,lambda:self.hit(move=X.ENTRAIN),reason_pattern='active donor ability choice')

    def test_entrainment_adds_one_ability_for_three_actual_recipient_turns(self):
        self.give(self.a,['단순']);self.give(self.t,['불면'])
        self.choose(self.a,self.t,X.ENTRAIN,'단순');before=deepcopy(self.t.spec['abilities'])
        self.hit(move=X.ENTRAIN)
        self.assertEqual(set(self.t.abilities),{'단순','불면'});self.assertEqual(self.a.abilities,['단순'])
        self.assertEqual(self.t.spec['abilities'],before)
        for serial in (1,2,3):
            self.next_round(self.t);self.assertIn('단순',self.t.abilities)
            self.e.end_of_turn(self.t)
            self.assertEqual('단순' in self.t.abilities,serial<3)

    def test_entrainment_miss_does_not_grant_and_protected_ability_remains_uncopied(self):
        for ability,seed in [('단순',31),('멀티타입',530)]:
            with self.subTest(ability=ability):
                self.setUp();self.give(self.a,[ability]);self.choose(self.a,self.t,X.ENTRAIN,ability)
                self.e.rng.seed(seed);self.hit(move=X.ENTRAIN)
                self.assertEqual(self.t.abilities,[]);self.assertEqual(self.live(self.t),[])

    def test_suppressed_donor_cannot_be_selected_even_when_known(self):
        self.give(self.a,['단순']);self.t.moves.append('move/위액')
        self.e.gm.choose_ability_transition(self.t,self.a,'move/위액',ability='단순',reason='actual selected suppression')
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        self.e.use_move(self.t,self.a,'move/위액')
        self.assertIn('ability/단순',A.known(self.a))
        assert_rejected_unchanged(self.e,lambda:self.choose(self.a,self.t,X.ENTRAIN,'단순'),reason_pattern='active eligible ability')

    def test_receiver_ally_faint_uses_true_boundary_and_encounter_lifetime(self):
        self.give(self.a,['리시버']);donor=self.actor('ally',['불요의검','단순'],(6,2),'party')
        self.choose(self.a,donor,X.RECEIVER,'단순');self.e.gm.faint(donor,reason='actual allied faint')
        self.assertIn('단순',self.a.abilities);self.assertTrue(donor.fainted)
        self.assertEqual(len(self.live(self.a)),1);self.e.check_fainted(donor)
        self.assertEqual(len(self.live(self.a)),1)
        self.e.end_encounter(self.e.everyone);self.assertEqual(self.a.abilities,['리시버'])

    def test_receiver_self_faint_grants_owned_basic_to_one_live_on_field_ally(self):
        receiver=self.actor('receiver',['리시버','엽록소'],(5,5),'party',pokemon=True)
        recipient=self.actor('recipient',[],(6,5),'party')
        self.choose(receiver,receiver,X.RECEIVER,'엽록소',allies=(recipient,))
        self.e.gm.faint(receiver,reason='actual Receiver self faint')
        self.assertTrue(receiver.fainted);self.assertIn('엽록소',recipient.abilities)
        self.assertEqual(receiver._action_history,['free']);self.assertEqual(len(self.live(recipient)),1)

    def test_receiver_nonbasic_enemy_and_recalled_recipient_choices_are_rejected(self):
        receiver=self.actor('receiver',['리시버','단순','엽록소'],(5,5),'party',pokemon=True)
        for target,ability,allies in [(receiver,'단순',(self.a,)),(self.t,'단순',())]:
            with self.subTest(ability=ability):
                assert_rejected_unchanged(self.e,lambda:self.choose(receiver,target,X.RECEIVER,ability,allies=allies),reason_pattern='eligible ability|actual ally')
        self.e.gm.recall(self.a,reason='recipient no longer on field')
        assert_rejected_unchanged(self.e,lambda:self.choose(receiver,receiver,X.RECEIVER,'엽록소',allies=(self.a,)),reason_pattern='on-field')

    def test_receiver_two_branches_have_independent_once_per_scene_usage(self):
        receiver=self.actor('receiver',['리시버','엽록소'],(5,5),'party',pokemon=True)
        donor=self.actor('donor',['단순'],(6,5),'party');recipient=self.actor('recipient',[],(7,5),'party')
        self.choose(receiver,donor,X.RECEIVER,'단순');self.e.gm.faint(donor,reason='receive branch')
        self.choose(receiver,receiver,X.RECEIVER,'엽록소',allies=(recipient,));self.e.gm.faint(receiver,reason='bequeath branch')
        self.assertIn('단순',receiver.abilities);self.assertIn('엽록소',recipient.abilities)
        uses=receiver.spec['frequency_state']['activations']
        self.assertEqual(uses[X.RECEIVER+':receive']['used'],1)
        self.assertEqual(uses[X.RECEIVER+':bequeath']['used'],1)

    def test_receiver_actual_melee_knockout_preserves_pre_cleanup_ability_snapshot(self):
        self.give(self.t,['단순']);receiver=self.actor('receiver',['리시버'],(6,5),'opponent')
        self.choose(receiver,self.t,X.RECEIVER,'단순')
        self.e.gm.set_hp(self.t,value=1,reason='actual one HP before hit');self.hit()
        self.assertTrue(self.t.fainted);self.assertIn('단순',receiver.abilities)
        self.assertEqual(self.t.spec[X.FAINTS][-1]['snapshot']['active'],['ability/단순'])

    def test_gas_aura_self_exclusion_defensive_only_and_actual_enter_leave(self):
        self.give(self.a,['화학변화가스','불면']);self.give(self.t,['불면','불요의검'])
        self.assertTrue(A.active(self.a,'ability/불면'));self.assertFalse(A.active(self.t,'ability/불면'))
        self.assertTrue(A.active(self.t,'ability/불요의검'));self.assertFalse(self.t.abilities_suppressed)
        self.assertTrue(self.e.apply_status(self.t,'잠듦'))
        self.e.cure_status(self.t,'잠듦')
        self.e.gm.set_position(self.t,(8,2),reason='actual exit from burst one')
        self.assertTrue(A.active(self.t,'ability/불면'));self.assertFalse(self.e.apply_status(self.t,'잠듦'))
        self.e.gm.set_position(self.t,(3,2),reason='actual reentry');self.assertFalse(A.active(self.t,'ability/불면'))

    def test_gas_overlapping_sources_restore_only_after_last_aura_is_gone(self):
        self.give(self.t,['불면'])
        self.give(self.a,['화학변화가스']);other=self.actor('second gas',['화학변화가스'],(4,2),'party')
        self.assertEqual(len(X._gas_sources(self.t)),2)
        self.give(self.a,[]);self.assertFalse(A.active(self.t,'ability/불면'))
        self.e.gm.recall(other,reason='last independent aura leaves');self.assertTrue(A.active(self.t,'ability/불면'))

    def test_gas_classifier_uses_declared_keyword_not_mentions_or_static_offense(self):
        self.assertIn('ability/불면',self.r.trickster_defensive)
        for uid in (X.GAS,'ability/화학변화가스-2','ability/틀깨기','ability/터보블레이즈-playtest','ability/테라볼티지-playtest'):
            self.assertNotIn(uid,self.r.trickster_defensive)
        self.assertIn('ability/복슬복슬',self.r.trickster_defensive)
        self.assertIn('ability/수포',self.r.trickster_defensive)

    def test_receiver_used_scene_branch_is_not_refunded_by_source_loss(self):
        self.give(self.a,['리시버']);donor=self.actor('donor',['단순'],(5,5),'party')
        self.choose(self.a,donor,X.RECEIVER,'단순');self.e.gm.faint(donor,reason='first actual Scene trigger')
        self.give(self.a,[]);self.give(self.a,['리시버'])
        other=self.actor('second donor',['단순'],(6,5),'party')
        assert_rejected_unchanged(self.e,lambda:self.choose(self.a,other,X.RECEIVER,'단순'),reason_pattern='frequency exhausted')

    def test_mummy_core_recall_does_not_silently_apply_playtest_switch_expiry(self):
        self.give(self.t,['미라 [Playtest]']);self.give(self.a,['단순'])
        self.core_mummy(self.t);self.hit()
        self.e.gm.recall(self.a,reason='Core replaced attacker switches out')
        self.assertEqual(self.a.abilities,['미라 [Playtest]']);self.assertEqual(len(self.live(self.a)),1)
        self.e.end_encounter(self.e.everyone);self.assertEqual(self.a.abilities,['단순'])

    def test_cold_restore_gas_keeps_full_round_deadline_and_source_identity(self):
        self.e.gm.set_position(self.t,(5,2),reason='outside aura');self.give(self.a,['화학변화가스']);self.give(self.t,['불면'])
        self.hit(move='move/클리어스모그');self.give(self.a,[])
        e,index=self.fresh();target=index[self.t.entity_id];source=index[self.a.entity_id]
        self.assertFalse(A.active(target,'ability/불면'));self.assertEqual(self.live(target)[0]['count_deadline'],[2,20])
        e.end_of_turn(source);e.end_round();e.start_round(e.everyone);e.start_of_turn(source,initiative_count=21)
        self.assertFalse(A.active(target,'ability/불면'));e.end_of_turn(source);e.start_of_turn(target,initiative_count=20)
        self.assertTrue(A.active(target,'ability/불면'))

    def test_gas_four_real_moves_apply_full_round_effect_independent_of_aura(self):
        for move in self.r.ability_exchange_policy['gas_moves']:
            with self.subTest(move=move):
                self.setUp();self.e.gm.set_position(self.t,(5,2),reason='outside aura but inside move range')
                self.give(self.a,['화학변화가스']);self.give(self.t,['불면'])
                self.hit(move=move);self.assertFalse(A.active(self.t,'ability/불면'))
                record=self.live(self.t)[0];self.assertEqual(record['count_deadline'],[2,20])
                self.give(self.a,[]);self.assertFalse(A.active(self.t,'ability/불면'))
                self.next_round(self.a,21);self.assertFalse(A.active(self.t,'ability/불면'))
                self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=20)
                self.assertTrue(A.active(self.t,'ability/불면'))

    def test_gas_real_miss_has_no_timed_suppression(self):
        self.e.gm.set_position(self.t,(5,2),reason='outside aura');self.give(self.a,['화학변화가스']);self.give(self.t,['불면'])
        self.e.rng.seed(31);self.hit(move='move/스모그')
        self.assertTrue(A.active(self.t,'ability/불면'));self.assertEqual(self.live(self.t),[])

    def test_gas_blocks_triggered_mummy_before_cost_but_not_static_offensive(self):
        gas=self.actor('gas',['화학변화가스'],(3,3),'party')
        self.give(self.t,['미라 [Playtest]','단순','불요의검']);self.choose(self.t,self.t,X.MUMMY,'단순')
        self.hit();self.assertIn('단순',self.t.abilities);self.assertTrue(A.active(self.t,'ability/불요의검'))
        self.assertEqual(getattr(self.t,'_action_history',[]),[]);self.assertEqual(self.live(self.t),[])
        self.e.gm.recall(gas,reason='real gas source exits')
        self.next_round(self.a);self.hit();self.assertNotIn('단순',self.t.abilities)

    def test_mummy_suppressed_gas_aura_ends_and_recall_restores_source(self):
        self.give(self.t,['미라 [Playtest]','화학변화가스']);self.give(self.a,['불면'])
        self.choose(self.t,self.t,X.MUMMY,X.GAS);self.hit()
        self.assertFalse(A.active(self.t,X.GAS));self.assertTrue(A.active(self.a,'ability/불면'))
        self.e.gm.recall(self.t,reason='Mummy PT suppression ends');self.assertTrue(A.active(self.t,X.GAS))

    def test_newly_copied_defensive_ability_is_suppressed_until_gas_source_leaves(self):
        self.give(self.a,['화학변화가스','불면']);self.choose(self.a,self.t,X.ENTRAIN,'불면')
        self.hit(move=X.ENTRAIN)
        self.assertIn('ability/불면',A.known(self.t));self.assertFalse(A.active(self.t,'ability/불면'))
        self.give(self.a,['불면']);self.assertTrue(A.active(self.t,'ability/불면'))

    def test_timed_gas_suppresses_later_copy_through_cold_restore_until_actual_count_expiry(self):
        from unittest.mock import patch
        self.e.gm.set_position(self.t,(5,2),reason='outside aura before actual timed Gas hit')
        self.give(self.a,['화학변화가스'])
        with patch.object(type(self.e),'d20',new=lambda actual:20):self.hit(move='move/클리어스모그')
        self.give(self.a,['불면']);self.next_round(self.a,21)
        self.choose(self.a,self.t,X.ENTRAIN,'불면')
        with patch.object(type(self.e),'d20',new=lambda actual:20):self.hit(move=X.ENTRAIN)
        gas_sources=tuple(X._gas_sources(self.t))
        self.assertEqual(len(gas_sources),1);self.assertEqual(len(self.live(self.t)),2)
        self.assertNotIn('불면',self.t.spec['abilities']);self.assertNotIn('불면',self.t.abilities)
        self.assertIn('ability/불면',A.project_components(self.t,include_suppressed=True))
        self.assertIn('ability/불면',A.project_components(self.t,ignored_sources=gas_sources))
        self.assertFalse(A.active(self.t,'ability/불면'))
        e,index=self.fresh();target=index[self.t.entity_id];source=index[self.a.entity_id]
        self.assertFalse(A.active(target,'ability/불면'));self.assertEqual(len(X._gas_sources(target)),1)
        e.end_of_turn(source);e.start_of_turn(target,initiative_count=20)
        self.assertTrue(A.active(target,'ability/불면'));self.assertEqual(X._gas_sources(target),{})
        e.end_encounter(e.everyone);self.assertEqual(target.abilities,[])

    def test_later_copy_keeps_native_mummy_suppression_source_order_without_gas(self):
        from unittest.mock import patch
        self.give(self.a,['단순']);self.give(self.t,['미라 [Playtest]','단순'])
        self.choose(self.t,self.t,X.MUMMY,'단순')
        with patch.object(type(self.e),'d20',new=lambda actual:20):self.hit()
        self.assertFalse(A.active(self.t,'ability/단순'));self.assertEqual(len(self.live(self.t)),1)
        self.next_round(self.a);self.choose(self.a,self.t,X.ENTRAIN,'단순')
        with patch.object(type(self.e),'d20',new=lambda actual:20):self.hit(move=X.ENTRAIN)
        self.assertTrue(A.active(self.t,'ability/단순'));self.assertEqual(len(self.live(self.t)),2)
        self.assertEqual(self.live(self.t)[0]['source'],X.MUMMY)
        self.e.gm.recall(self.t,reason='actual recall removes only earlier Mummy suppression')
        self.assertTrue(A.active(self.t,'ability/단순'));self.assertEqual(len(self.live(self.t)),1)

    def test_actual_public_selection_rejects_forged_event_fields(self):
        self.give(self.t,['미라 [Playtest]','단순'])
        before=self.e.export_state()
        with self.assertRaisesRegex(TypeError,'unexpected keyword'):
            self.e.gm.choose_ability_transition(self.t,self.t,X.MUMMY,ability='단순',reason='forged producer',completion_id='fake')
        self.assertEqual(self.e.export_state(),before)

    def test_gas_keeps_nontriggered_arena_and_tail_native_activation_and_psychic_struggle(self):
        import ability_control_contracts as CONTROL
        self.give(self.a,['개미지옥 [Playtest]','테일아머']);self.give(self.t,['화학변화가스'])
        self.e.activate_ability(self.a,CONTROL.ARENA,self.a)
        self.e.activate_ability(self.a,CONTROL.TAIL,(self.a,{'aim':[5,2]}))
        self.assertTrue(CONTROL._live(self.a,'arena'));self.assertTrue(CONTROL._live(self.a,'tail'))
        self.assertTrue(A.active(self.a,CONTROL.ARENA));self.assertTrue(A.active(self.a,CONTROL.TAIL))
        self.e.use_move(self.a,self.t,'struggle',struggle_choice={'ability':CONTROL.TAIL,'type':'에스퍼'},set_damage=True)
        completion=list(self.e._move_completions.values())[-1]
        self.assertEqual(completion['move']['type'],'에스퍼')

    def test_mummy_actual_source_suppression_reuses_control_aura_cleanup(self):
        import ability_control_contracts as CONTROL
        self.give(self.a,['미라 [Playtest]','개미지옥 [Playtest]'])
        self.e.activate_ability(self.a,CONTROL.ARENA,self.a)
        self.assertIn('수렁',self.t.conditions)
        self.choose(self.a,self.a,X.MUMMY,CONTROL.ARENA)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        self.hit(self.t,self.a)
        self.assertFalse(A.active(self.a,CONTROL.ARENA));self.assertFalse(CONTROL._live(self.a,'arena'))
        self.assertNotIn('수렁',self.t.conditions)
        self.e.gm.recall(self.a,reason='PT source suppression expires')
        self.assertTrue(A.active(self.a,CONTROL.ARENA));self.assertFalse(CONTROL._live(self.a,'arena'))

    def test_real_interrupt_offer_use_is_blocked_after_gas_enters_but_decline_is_free(self):
        import passive_events as PASSIVE
        import tera_shell as TS
        for use in (False,True):
            with self.subTest(use_after_rejection=use):
                self.setUp()
                self.give(self.t,['테라셸']);gas=self.actor('gas',['화학변화가스'],(10,10),'party')
                self.e.watch_ability_interrupt(self.t,TS.SOURCE,reason='watch actual native recipient')
                with self.assertRaises(PASSIVE.PassiveEventPending):self.hit(move='move/물대포')
                event=self.e._passive_pending;types_before=list(self.t.types)
                self.e.gm.set_position(gas,(3,3),reason='actual gas enters while the native choice waits')
                assert_rejected_unchanged(self.e,lambda:self.e.choose_ability_interrupt(event,self.t,use=True,options={'chosen_type':'물'},reason='attempt actual trigger'),reason_pattern='^Neutralizing Gas prohibits this triggered ability Interrupt$')
                self.assertEqual(getattr(self.t,'_action_history',[]),[])
                if use:
                    # The same pending choice succeeds when only the Gas source leaves.
                    self.e.gm.set_position(gas,(10,10),reason='only Gas leaves the waiting recipient')
                    self.e.choose_ability_interrupt(event,self.t,use=True,options={'chosen_type':'물'},reason='attempt actual trigger')
                    self.assertEqual(self.t.types,['물'])
                else:
                    # Decline remains legal with Gas still present.
                    self.e.choose_ability_interrupt(event,self.t,use=False,reason='actual decline remains permitted')
                    self.assertEqual(self.t.types,types_before)
                    self.assertNotIn(TS.KEY,self.t.spec)
                self.assertIsNone(self.e._passive_pending)
                self.assertEqual(getattr(self.t,'_action_history',[]),['free'] if use else [])
                attempt=self.e._passive_events[event]['ability_interrupts']['attempts'][0]
                self.assertEqual(attempt['paid'],use)
                self.assertEqual(attempt['outcome'],'activated' if use else 'declined')

    def test_exact_registry_four_parents_and_two_lossless_copies_are_not_extra_credit(self):
        ledger=json.loads((ROOT/'data/verification/category2-csv-abilities-moves-status.json').read_text(encoding='utf-8'))
        rows=ledger['rows'];by_id={r['row_id']:r for r in rows}
        parents=['C2CSV-ABILITY-R0112','C2CSV-ABILITY-R0157','C2CSV-ABILITY-R0473','C2CSV-MOVE-R0479']
        for uid in parents:
            self.assertTrue(by_id[uid]['category2_included']);self.assertEqual(by_id[uid]['denominator_contribution'],1)
            self.assertEqual(by_id[uid]['exact_copy_of'],[])
        for copy,parent in [('C2CSV-ABILITY-R0571',parents[0]),('C2CSV-ABILITY-R0600',parents[2])]:
            self.assertEqual(by_id[copy]['denominator_contribution'],0)
            self.assertEqual(by_id[copy]['source_cells'],by_id[parent]['source_cells'])
            self.assertEqual(by_id[copy]['source_row_sha256'],by_id[parent]['source_row_sha256'])

    def test_cold_restore_retains_native_mummy_and_entrainment_refs_and_real_expiry(self):
        self.give(self.a,['단순']);self.give(self.t,['미라 [Playtest]','불면'])
        self.choose(self.a,self.t,X.ENTRAIN,'단순');self.hit(move=X.ENTRAIN)
        self.next_round(self.a);self.choose(self.t,self.t,X.MUMMY,'불면');self.hit()
        e,index=self.fresh();target=index[self.t.entity_id]
        self.assertIn('단순',target.abilities);self.assertNotIn('불면',target.abilities)
        e.gm.recall(target,reason='actual recall after cold restore');self.assertIn('불면',target.abilities)
        self.assertIn('단순',target.abilities)
        e.end_encounter(e.everyone);self.assertNotIn('단순',target.abilities)

    def test_cold_restore_receiver_faint_evidence_retains_true_actor_identity(self):
        self.give(self.a,['리시버']);donor=self.actor('donor',['단순'],(5,5),'party')
        self.choose(self.a,donor,X.RECEIVER,'단순');self.e.gm.faint(donor,reason='actual faint before save')
        e,index=self.fresh();event=index[donor.entity_id].spec[X.FAINTS][-1]
        self.assertIs(event['actor'],index[donor.entity_id]);self.assertIs(event[X.TAG][0]['owner'],index[self.a.entity_id])
        e.end_encounter(e.everyone);self.assertEqual(index[self.a.entity_id].abilities,['리시버'])

    def test_entrainment_respects_actual_ability_shield_without_creating_exchange_grant(self):
        self.give(self.a,['단순']);self.give(self.t,['불면']);self.shield(self.t)
        self.choose(self.a,self.t,X.ENTRAIN,'단순');self.hit(move=X.ENTRAIN)
        self.assertEqual(self.t.abilities,['불면']);self.assertEqual(self.live(self.t),[])
        self.assertEqual(list(self.e._move_completions.values())[-1].get(X.TAG,[]),[])
        self.assertNotIn(A.key(X.ENTRAIN,self.t),self.a.spec.get(A.CHOICES,{}))

    def test_mummy_core_respects_attackers_actual_ability_shield(self):
        self.give(self.t,['미라 [Playtest]']);self.give(self.a,['단순','불굴의방패']);self.shield(self.a)
        self.core_mummy(self.t);self.hit()
        self.assertEqual(set(self.a.abilities),{'단순','불굴의방패'});self.assertEqual(self.live(self.a),[])
        self.assertEqual(list(self.e._move_completions.values())[-1].get(X.TAG,[]),[])
        self.assertEqual(self.t._action_history,['free'])

    def test_mummy_playtest_self_suppression_is_not_blocked_by_own_ability_shield(self):
        self.give(self.t,['미라 [Playtest]','단순']);self.shield(self.t)
        self.choose(self.t,self.t,X.MUMMY,'단순');self.hit()
        self.assertNotIn('단순',self.t.abilities);self.assertTrue(A.active(self.t,X.MUMMY))
        self.assertEqual(len(self.live(self.t)),1)
        self.e.gm.recall(self.t,reason='actual PT switch restores shield wearer own suppression')
        self.assertIn('단순',self.t.abilities);self.assertEqual(self.live(self.t),[])

    def test_uninterested_faint_is_evidence_neutral_and_gas_faint_still_refreshes(self):
        for producer in ('faint','set_hp'):
            for gas in (False,True):
                with self.subTest(producer=producer,gas=gas):
                    self.setUp()
                    if gas:
                        self.give(self.a,['화학변화가스']);self.give(self.t,['불면'])
                        self.assertFalse(A.active(self.t,'ability/불면'))
                    if producer=='faint':self.e.gm.faint(self.a,reason='actual faint without Receiver candidates')
                    else:self.e.gm.set_hp(self.a,value=0,reason='actual zero HP without Receiver candidates')
                    self.assertTrue(self.a.fainted);self.assertNotIn(X.FAINTS,self.a.spec)
                    self.e.check_fainted(self.a);self.assertNotIn(X.FAINTS,self.a.spec)
                    if gas:
                        self.assertTrue(A.active(self.t,'ability/불면'));self.assertEqual(X._gas_sources(self.t),{})

    def test_entrainment_projects_only_its_exact_legacy_effect_and_emits_one_native_grant(self):
        import reactive_ability_events as REACTIVE
        self.give(self.a,['단순']);self.choose(self.a,self.t,X.ENTRAIN,'단순')
        mm,_=self.r.move_mech(X.ENTRAIN)
        raw={'type':'grant_ability','grant_ability':"one of user's abilities",'on':'target','turns':3}
        other={'type':'grant_ability','grant_ability':'불면','on':'target','turns':2}
        self.assertEqual(mm.get('effects_exec',[]).count(raw),1)
        mm=deepcopy(mm);mm['effects_exec'].append(other);original=deepcopy(mm)
        projected=REACTIVE.preflight_move(self.e,self.a,self.t,self.r.moves[X.ENTRAIN],mm)
        expected=deepcopy(original);expected['effects_exec'].remove(raw)
        self.assertEqual(projected,expected);self.assertEqual(mm,original)
        self.assertIn(other,projected['effects_exec'])
        self.hit(move=X.ENTRAIN)
        apps=list(self.e._move_completions.values())[-1].get(X.TAG,[])
        self.assertEqual(len(apps),1);self.assertEqual(apps[0]['source'],X.ENTRAIN)
        self.assertEqual(len(self.live(self.t)),1);self.assertEqual(self.t.abilities,['단순'])

    def test_entrainment_legacy_grant_mismatch_rejects_before_cost_rng(self):
        original=deepcopy(self.r.moves_llm['동료만들기']['effects'])
        raw={'type':'grant_ability','grant_ability':"one of user's abilities",'on':'target','turns':3}
        variants=[[],[{**raw,'turns':2}],[{**raw,'on':'self'}],
                  [{**raw,'grant_ability':'불면'}],[raw,deepcopy(raw)]]
        try:
            for effects in variants:
                with self.subTest(effects=effects):
                    self.r.moves_llm['동료만들기']['effects']=deepcopy(original);self.setUp()
                    self.give(self.a,['단순']);self.choose(self.a,self.t,X.ENTRAIN,'단순')
                    self.r.moves_llm['동료만들기']['effects']=deepcopy(effects)
                    assert_rejected_unchanged(self.e,lambda:self.hit(move=X.ENTRAIN),
                                              reason_pattern='Entrainment requires its exact reviewed legacy grant declaration')
        finally:self.r.moves_llm['동료만들기']['effects']=original

    def test_receiver_bequeath_respects_allys_actual_ability_shield(self):
        receiver=self.actor('shielded bequeath source',['리시버','엽록소'],(5,5),'party',pokemon=True)
        self.shield(self.a);self.choose(receiver,receiver,X.RECEIVER,'엽록소',allies=(self.a,))
        self.e.gm.faint(receiver,reason='actual external Receiver bequeath to shield wearer')
        self.assertTrue(receiver.fainted);self.assertNotIn('엽록소',self.a.abilities)
        self.assertEqual(self.live(self.a),[]);self.assertEqual(receiver.spec[X.FAINTS][-1].get(X.TAG,[]),[])
        self.assertEqual(receiver._action_history,['free'])

    def test_receiver_self_receive_is_not_blocked_by_own_ability_shield(self):
        self.give(self.a,['리시버']);self.shield(self.a)
        donor=self.actor('self receive donor',['단순'],(6,2),'party')
        self.choose(self.a,donor,X.RECEIVER,'단순');self.e.gm.faint(donor,reason='actual Receiver self receive')
        self.assertIn('단순',self.a.abilities);self.assertEqual(len(self.live(self.a)),1)
        app=donor.spec[X.FAINTS][-1][X.TAG][0]
        self.assertIs(app['owner'],self.a);self.assertIs(app['recipient'],self.a)

    def test_gas_native_hits_respect_actual_ability_shield_without_trigger_block_sources(self):
        for move in self.r.ability_exchange_policy['gas_moves']:
            for abilities in (['불면','미라 [Playtest]'],['단순','미라 [Playtest]']):
                with self.subTest(move=move,abilities=abilities):
                    self.setUp();self.e.gm.set_position(self.t,(5,2),reason='actual target outside Gas aura')
                    self.give(self.t,abilities);self.shield(self.t);self.give(self.a,['화학변화가스'])
                    self.hit(move=move)
                    self.assertEqual(set(self.t.abilities),set(abilities));self.assertEqual(self.live(self.t),[])
                    self.assertEqual(X._gas_sources(self.t),{});self.assertTrue(X.admit_trigger(self.e,self.t,X.MUMMY))
                    self.assertEqual(list(self.e._move_completions.values())[-1].get(X.TAG,[]),[])

    def test_gas_aura_rechecks_actual_shield_at_continuous_boundaries_and_keeps_self_reactions(self):
        import items as ITEMS
        self.give(self.t,['불면','미라 [Playtest]','단순']);self.give(self.a,['화학변화가스'])
        self.assertFalse(A.active(self.t,'ability/불면'));self.assertFalse(X.admit_trigger(self.e,self.t,X.MUMMY))
        self.shield(self.t)
        self.e.gm.set_position(self.t,(2,3),reason='actual continuous aura boundary observes shield registration')
        self.assertTrue(A.active(self.t,'ability/불면'));self.assertEqual(X._gas_sources(self.t),{})
        self.assertTrue(X.admit_trigger(self.e,self.t,X.MUMMY))
        self.choose(self.t,self.t,X.MUMMY,'단순');self.hit()
        self.assertNotIn('단순',self.t.abilities);self.assertEqual(self.t._action_history,['free'])
        ITEMS.unregister_item(self.e,self.t,'item/특성가드')
        self.e.gm.set_position(self.t,(3,2),reason='actual continuous aura boundary observes no active shield')
        self.assertFalse(A.active(self.t,'ability/불면'));self.assertEqual(len(X._gas_sources(self.t)),1)
        self.assertFalse(X.admit_trigger(self.e,self.t,X.MUMMY));self.assertEqual(len(self.live(self.t)),1)
        self.e.gm.set_position(self.t,(8,2),reason='actual aura exit does not rewrite prior self application')
        self.assertTrue(A.active(self.t,'ability/불면'));self.assertEqual(X._gas_sources(self.t),{})
        self.assertNotIn('단순',self.t.abilities);self.assertEqual(len(self.live(self.t)),1)

    def test_gas_native_paid_disengage_refreshes_aura_before_actual_cell_entry(self):
        from unittest.mock import patch
        import effects_ext as EXT
        self.give(self.t,['불면']);self.give(self.a,['화학변화가스'])
        self.assertFalse(A.active(self.t,'ability/불면'))
        before=deepcopy(self.a.budget);observed=[];on_enter=EXT.on_enter_cell

        def observe(engine,actor,position,**options):
            observed.append((position,A.active(self.t,'ability/불면'),len(X._gas_sources(self.t))))
            return on_enter(engine,actor,position,**options)

        with patch.object(EXT,'on_enter_cell',side_effect=observe):
            self.assertTrue(self.e.disengage(self.a,(1,2)))
        self.assertEqual(self.a.pos,(1,2));self.assertEqual(self.t.pos,(3,2))
        self.assertEqual(self.a.budget,{**before,'shift':before['shift']-1})
        self.assertEqual(self.a._action_history,['shift'])
        self.assertEqual(observed,[((1,2),True,0)])
        self.assertTrue(A.active(self.t,'ability/불면'));self.assertEqual(self.live(self.t),[])

    def test_gas_paid_approach_refreshes_aura_before_each_actual_cell_entry(self):
        from unittest.mock import patch
        import effects_ext as EXT
        for crossing in ('enter','leave'):
            with self.subTest(crossing=crossing):
                self.setUp()
                self.e.gm.set_position(self.t,(20,20),reason='isolate actual movement from unrelated hostile opportunity attacks')
                watcher=self.actor('stationary ally',['불면'],(4,1) if crossing=='enter' else (2,1),'party')
                goal=self.actor('actual approach goal',[],(5,2),'party')
                self.give(self.a,['화학변화가스'])
                self.assertEqual(A.active(watcher,'ability/불면'),crossing=='enter')
                before=deepcopy(self.a.budget);observed=[];on_enter=EXT.on_enter_cell

                def observe(engine,actor,position,**options):
                    if actor is self.a:
                        observed.append((tuple(position),A.active(watcher,'ability/불면'),len(X._gas_sources(watcher))))
                    return on_enter(engine,actor,position,**options)

                with patch.object(EXT,'on_enter_cell',side_effect=observe):
                    result=self.e.approach(self.a,goal,reach=1,movement_mode='land')
                self.assertGreater(result['distance'],1);self.assertGreaterEqual(len(observed),2)
                self.assertEqual(observed[-1][0],self.a.pos)
                for position,active,sources in observed:
                    inside=max(abs(position[0]-watcher.pos[0]),abs(position[1]-watcher.pos[1]))<=1
                    self.assertEqual((active,sources),(not inside,int(inside)))
                self.assertEqual(A.active(watcher,'ability/불면'),crossing=='leave')
                self.assertEqual(self.a.budget,{**before,'shift':before['shift']-1})
                self.assertEqual(self.a._action_history,['shift']);self.assertEqual(self.live(watcher),[])

    def test_receiver_gm_zero_hp_preserves_both_actual_faint_branches_without_retrigger(self):
        for branch in ('receive','bequeath'):
            with self.subTest(branch=branch):
                self.setUp()
                if branch=='receive':
                    owner=self.a;self.give(owner,['리시버'])
                    donor=self.actor('zero HP ally',['단순'],(6,5),'party')
                    recipient=owner;chosen='단순'
                    self.choose(owner,donor,X.RECEIVER,chosen)
                else:
                    owner=self.actor('zero HP Receiver',['리시버','엽록소'],(6,5),'party',pokemon=True)
                    donor=owner;recipient=self.a;chosen='엽록소'
                    self.choose(owner,donor,X.RECEIVER,chosen,allies=(recipient,))
                self.e.gm.set_hp(donor,value=0,reason='actual GM zero HP Receiver boundary')
                self.assertTrue(donor.fainted);self.assertEqual(donor.hp,0)
                self.assertIn(chosen,recipient.abilities);self.assertEqual(len(self.live(recipient)),1)
                event=donor.spec[X.FAINTS][0];app=event[X.TAG][0]
                self.assertIs(event['actor'],donor);self.assertIs(app['owner'],owner)
                self.assertIs(app['recipient'],recipient);self.assertEqual(app['branch'],branch)
                self.e.check_fainted(donor)
                self.e.gm.set_hp(donor,value=0,reason='already fainted does not retrigger Receiver')
                self.assertEqual(len(donor.spec[X.FAINTS]),1);self.assertEqual(len(self.live(recipient)),1)
                self.assertEqual(owner._action_history,['free'])
                self.assertEqual(owner.spec['frequency_state']['activations'][X.RECEIVER+':'+branch]['used'],1)

    def test_mummy_native_recipient_respects_actual_noncontact_glove_and_restores(self):
        from unittest.mock import patch
        from test_actual_contact_reactions_f27 import ActualContactReactionTests
        import world_entities as WORLD
        for glove in (False,True):
            with self.subTest(glove=glove):
                fixture=ActualContactReactionTests();fixture.r=self.r
                e,attacker,spare=fixture.fixture(glove)
                target=fixture.target(e,'actual-mummy-contact',aroma=False)
                G.replace_baseline(e,target,'abilities',['미라 [Playtest]','단순'])
                e.start_round([attacker,spare,target]);e.start_of_turn(attacker,initiative_count=20)
                e.gm.choose_ability_transition(target,target,X.MUMMY,ability='단순',
                                              reason='actual recipient owns its native Mummy choice')
                with patch.object(type(e),'d20',new=lambda actual:20):
                    e.use_move(attacker,target,'move/몸통박치기',set_damage=True)
                row=list(e._move_completions.values())[-1]
                self.assertEqual(row['phase'],'complete')
                self.assertTrue(row['results'][target.entity_id]['hit'])
                self.assertEqual(len(row.get(X.TAG,[])),0 if glove else 1)
                self.assertEqual('단순' in target.abilities,glove)
                self.assertEqual(getattr(target,'_action_history',[]),[] if glove else ['free'])
                restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
                self.assertEqual(WORLD.actor_index(restored)[target.entity_id].abilities,target.abilities)
                self.assertTrue(restored.validate_state()['valid'])

    def test_tampered_grant_deadline_and_aura_source_are_rejected_not_refreshed_into_truth(self):
        for kind in ('operation','deadline','producer'):
            with self.subTest(kind=kind):
                self.setUp();self.give(self.a,['단순']);self.choose(self.a,self.t,X.ENTRAIN,'단순');self.hit(move=X.ENTRAIN)
                record=self.live(self.t)[0];owner=self.t.spec[G.KEY]['sources'][record['grant_source']]
                if kind=='operation':owner['ability_operation']['add']=['ability/불면']
                elif kind=='deadline':record['turn_deadline']+=1
                else:owner['owner_id']=self.t.entity_id
                with self.assertRaises(ValueError):X.validate_world(self.e,{c.entity_id:c for c in self.e.everyone})
                before=deepcopy((self.a.spec,self.t.spec,self.e.rng.getstate()))
                with self.assertRaisesRegex(ValueError,'receipt'):X.refresh(self.e)
                self.assertEqual((self.a.spec,self.t.spec,self.e.rng.getstate()),before)
                with self.assertRaises(Exception):self.e.export_state()


if __name__=='__main__':unittest.main()
