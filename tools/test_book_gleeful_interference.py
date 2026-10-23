"""Book Gleeful: actual hit recipients, owned Ability snapshot and native penalty."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon
from grid import Grid
import test_book_cheerleader_bundle as FIXTURE
import test_category2_move_defense_reactions as DEFENSE_FIXTURE
import test_category2_reactive_ability_events as REACTIVE_FIXTURE
import test_category2_type_state as TYPE_FIXTURE
import gleeful_interference as GI,cheerleader as CH,moment_of_action as M
import trainer_feature_acquisition as TFA,trainer_retraining as RETRAIN
import state_fields as F,state_grants as G,state_codec as CODEC,action_points as AP
import combat_timing as CLOCK,combat_modifiers as MOD,move_completion as COMPLETE
import ability_transitions as ABILITIES,grapple_state as GRAPPLE
import passive_events as PASSIVE


class GleefulInterferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    def setup(self,*,acquire=True,abilities=('프렌드가드',),moves=('메가톤펀치',)):
        helper=FIXTURE.CheerleaderBundleTests();helper.rules=self.rules
        helper.setup(combat=False,abilities=abilities,moves=moves)
        self.helper=helper;self.e,self.a,self.p,self.b,self.c=helper.e,helper.a,helper.p,helper.b,helper.c
        self.b.side=self.c.side='enemy'
        if acquire:
            for uid in (CH.BRIGADE,GI.FEATURE):TFA.acquire_static(self.e,self.a,uid,acquisition_request_id='gleeful/'+uid)
        self.answer(True)
    def answer(self,value):self.helper.answer(GI.KEY,value)
    def start(self):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)
    def hit(self,move='move/메가톤펀치',target=None,natural=18,area=False):
        with patch.object(type(self.e),'d20',new=lambda e:natural):
            if area:return self.e.use_move_on(self.p,target or self.b,move,self.e.everyone,set_damage=True)
            return self.e.use_move(self.p,target or self.b,move,set_damage=True)
    def effects(self,target=None):return [r for r in CLOCK.records(target or self.b) if r['source']==GI.FEATURE]
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def state(self):return CODEC.dump_engine(self.e)
    def unchanged(self,callback):
        before=self.state()
        with self.assertRaises(ValueError):callback()
        self.assertEqual(self.state(),before)
    def refresh(self):
        COMPLETE.refresh(self.e)
        for row in self.e._move_completions.values():GI.after_move(self.e,row)
    def retire(self,feature):
        decisions=self.helper.base.base.decisions(self.e,self.a,feature,request='gleeful/remove/'+feature)
        owned=RETRAIN._owned(self.a)
        for child,parent in ((M.CLASS,M.TRAINING),(M.FEATURE,M.CLASS),(CH.BRIGADE,M.CLASS),(GI.FEATURE,CH.BRIGADE)):
            if child!=feature and child in owned:
                decisions['retained_dependencies'][RETRAIN.owned_source(self.e,self.a,child)]=[RETRAIN.owned_source(self.e,self.a,parent)]
        return self.e.retrain_trainer_source(self.a,feature,**decisions)
    def restore(self):
        ids=[a.entity_id for a in (self.a,self.p,self.b,self.c)]
        self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(self.state(),ensure_ascii=False)))
        index={a.entity_id:a for a in self.e.everyone};self.a,self.p,self.b,self.c=[index[i] for i in ids]
        self.helper.e=self.e

    def test_acquisition_requires_real_brigade_and_adept_charm_then_retains_historical_rank(self):
        self.setup(acquire=False)
        self.unchanged(lambda:TFA.acquire_static(self.e,self.a,GI.FEATURE,acquisition_request_id='missing-parent'))
        TFA.acquire_static(self.e,self.a,CH.BRIGADE,acquisition_request_id='brigade')
        F.base_patch(self.a,{'skills':{'매력':3,'명령':5}},reason='actual below Adept observation')
        self.unchanged(lambda:TFA.acquire_static(self.e,self.a,GI.FEATURE,acquisition_request_id='low-rank'))
        F.base_patch(self.a,{'skills':{'매력':4,'명령':5}},reason='actual Adept observation')
        receipt=TFA.acquire_static(self.e,self.a,GI.FEATURE,acquisition_request_id='qualified')
        self.assertEqual(receipt['source']['clause_id'],'input/ch04-trainer-classes.md:684-688')
        F.base_patch(self.a,{'skills':{'매력':1,'명령':5}},reason='later skill decline')
        self.start();self.hit();self.assertEqual(len(self.effects()),1);self.valid()

    def test_native_damaging_hit_spends_one_ap_off_turn_free_and_changes_actual_accuracy(self):
        self.setup();self.start();ap=AP.available(self.a);hp=self.b.hp
        attack=self.rules.move('move/메가톤펀치')
        threshold=attack['ac']+self.p.evasion(attack['class'])
        before=self.e.accuracy_check(self.b,self.p,attack,fixed_roll=threshold)[0]
        self.hit();self.assertLess(self.b.hp,hp)
        self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(self.a._action_history,['free'])
        self.assertEqual(MOD.accuracy_stage(self.b),-2);self.assertFalse(self.effects(self.c))
        self.assertTrue(before);self.assertFalse(self.e.accuracy_check(self.b,self.p,attack,fixed_roll=threshold)[0])
        self.assertEqual(self.effects()[0]['count_deadline'],(self.e.round_no+1,20))
        self.refresh()
        event=self.effects()[0]['gleeful_origin']['event_id'];PASSIVE.deliver(self.e,event)
        self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(len(self.effects()),1);self.valid()

    def test_miss_status_ally_unowned_suppressed_and_missing_ability_never_trigger(self):
        for invalid in ('miss','status','ally','unowned','suppressed','missing'):
            with self.subTest(invalid=invalid):
                self.setup(abilities=() if invalid=='missing' else ('프렌드가드',),moves=('메가톤펀치','꼬리흔들기'))
                if invalid=='ally':self.b.side=self.p.side
                if invalid=='unowned':self.p.spec['trainer_id']=self.b.entity_id;self.p.spec['trainer']=self.b.name
                if invalid=='suppressed':self.p.abilities_suppressed=True
                self.start();ap=AP.available(self.a)
                self.hit(move='move/꼬리흔들기' if invalid=='status' else 'move/메가톤펀치',natural=1 if invalid=='miss' else 18)
                self.assertEqual(AP.available(self.a),ap);self.assertFalse(self.effects());self.valid()
        self.setup();self.start();ap=AP.available(self.a)
        self.e.lose_hp(self.b,1,source='non-attack loss')
        self.e.resolve_attack_damage(self.p,self.b,self.rules.move('move/메가톤펀치'),set_damage=True)
        self.assertFalse(self.effects());self.assertEqual(AP.available(self.a),ap);self.valid()

    def test_decline_invalid_choice_and_failed_payment_preserve_native_transaction(self):
        self.setup();self.start();self.answer(False);ap=AP.available(self.a);hp=self.b.hp
        self.hit();self.assertLess(self.b.hp,hp);self.assertEqual(AP.available(self.a),ap);self.assertFalse(self.effects())
        for invalid in ('choice','ap','install'):
            self.setup();self.start()
            if invalid=='choice':self.answer('yes')
            if invalid=='ap':self.a.ap_account.charge(AP.available(self.a),mode='spend')
            if invalid=='install':
                original=CLOCK.install
                def fail(e,c,row):
                    if row.get('source')==GI.FEATURE:raise ValueError('actual timed install failure')
                    return original(e,c,row)
                with patch.object(CLOCK,'install',side_effect=fail):self.unchanged(self.hit)
            else:self.unchanged(self.hit)
            self.valid()

    def test_absorbed_zero_damage_hit_triggers_but_cannot_hit_does_not(self):
        for ability,expected in (('저수',1),('불가사의부적',0)):
            self.setup(moves=('물대포',))
            self.e.gm.set_types(self.b,['노말'],reason='actual typed target with a Fighting weakness')
            G.replace_baseline(self.e,self.b,'abilities',[ability]);self.e.register_abilities(self.b)
            self.start();hp=self.b.hp;ap=AP.available(self.a)
            self.hit('move/물대포');self.assertEqual(self.b.hp,hp)
            self.assertEqual(len(self.effects()),expected);self.assertEqual(AP.available(self.a),ap-expected);self.valid()

    def test_area_targets_and_distinct_attacks_apply_once_per_actual_foe_hit(self):
        self.setup(moves=('방전',))
        self.e.gm.observe_mapless_scene(scene_id='gleeful-area',places={'source':'source','foes':'nearby foes','owner':'distant owner'},
            placements={self.p.entity_id:'source',self.b.entity_id:'foes',self.c.entity_id:'foes',self.a.entity_id:'owner'},
            contacts=[],reason='actual complete combat placements')
        self.e.gm.observe_mapless_targets(self.p,event_id='actual-gleeful-area',move_id='move/방전',
            landmark_id='foes',target_ids=[self.b.entity_id,self.c.entity_id],reason='actual selected source area includes both foes')
        self.start();ap=AP.available(self.a);self.hit('move/방전',area=True)
        self.assertEqual([len(self.effects(t)) for t in (self.a,self.p,self.b,self.c)],[0,0,1,1])
        self.assertEqual(AP.available(self.a),ap-2);self.refresh();self.assertEqual(AP.available(self.a),ap-2);self.valid()
        self.setup();self.start();self.hit();self.e.end_of_turn(self.p)
        other=Combatant(self.rules,build_pokemon(self.rules,'이브이',20,name='second owned partner',moves=['메가톤펀치'],
            abilities=['프렌드가드'],extra={'trainer_id':self.a.entity_id,'trainer':self.a.name}))
        self.e.gm.add_combatant(other,pos=(2,1),side='party',reason='another actual owned partner')
        self.e.gm.observe_loyalty(other,6,reason='willing partner');self.e.register_abilities(other)
        self.e.start_of_turn(other,initiative_count=19)
        with patch.object(type(self.e),'d20',new=lambda e:18):self.e.use_move(other,self.b,'move/메가톤펀치',set_damage=True)
        self.assertEqual(MOD.accuracy_stage(self.b),-4);self.assertEqual(len(self.effects()),2);self.valid()

    def test_ability_swap_after_hit_preserves_friend_guard_snapshot_and_ownership_is_not_side(self):
        fixture=REACTIVE_FIXTURE.ReactiveAbilityEventsTests();fixture.r=self.rules;fixture.setUp()
        helper=FIXTURE.CheerleaderBundleTests();helper.rules=self.rules;helper.coach(fixture,fixture.a)
        self.helper=helper;self.e,self.a,self.p,self.b=helper.e,helper.a,fixture.a,fixture.t
        self.c=self.b
        TFA.acquire_static(self.e,self.a,GI.FEATURE,acquisition_request_id='swap-gleeful')
        self.e.gm.observe_loyalty(self.p,6,reason='actual willing newly owned attacker')
        fixture.give(self.b,['떠도는영혼']);self.e.register_abilities(self.p);self.e.register_abilities(self.b)
        self.b.damage_cap={'value':1}
        self.assertNotEqual(self.p.side,self.b.side)
        fixture.choose(self.b,'ability/떠도는영혼')
        self.answer(True)
        with patch.object(type(self.e),'d20',new=lambda e:18):self.e.use_move(self.p,self.b,'move/몸통박치기',set_damage=True)
        self.assertFalse(ABILITIES.active(self.p,'ability/프렌드가드'));self.assertTrue(ABILITIES.active(self.b,'ability/프렌드가드'))
        self.assertEqual(len(self.effects()),1);self.valid()
        self.setup();self.p.side='third-party';self.b.side='party';self.start();self.hit()
        self.assertEqual(len(self.effects()),1);self.valid()

    def test_actual_interceptor_receives_penalty_original_target_does_not(self):
        fixture=DEFENSE_FIXTURE.MoveDefenseReactionsTests();fixture.rules=self.rules;fixture.setUp()
        helper=FIXTURE.CheerleaderBundleTests();helper.rules=self.rules;helper.coach(fixture,fixture.a)
        self.helper=helper;self.e,self.a,self.p,self.b,self.c=helper.e,helper.a,fixture.a,fixture.t,fixture.r
        TFA.acquire_static(self.e,self.a,GI.FEATURE,acquisition_request_id='intercept-gleeful');self.answer(True)
        self.e.gm.observe_loyalty(self.p,6,reason='actual willing newly owned attacker')
        self.e.register_abilities(self.p);fixture.watch()
        with patch.object(type(self.e),'d20',new=lambda e:18):
            event=fixture.waiting();fixture.choose(event,options=fixture.melee())
        self.assertFalse(self.effects(self.b));self.assertEqual(len(self.effects(self.c)),1)
        self.assertEqual(self.effects(self.c)[0]['gleeful_origin']['event_id'],fixture.completion()['received'][self.c.entity_id]['child_event']);self.valid()

    def test_full_round_survives_source_withdrawal_restore_and_expires_at_original_count(self):
        self.setup();self.start();self.hit();origin=deepcopy(self.effects()[0]['gleeful_origin'])
        self.retire(GI.FEATURE);self.retire(CH.BRIGADE)
        self.assertEqual(self.effects()[0]['gleeful_origin'],origin);self.restore();self.valid()
        self.e.end_of_turn(self.p);self.e.end_round();self.assertEqual(MOD.accuracy_stage(self.b),-2)
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(21);self.assertEqual(MOD.accuracy_stage(self.b),-2)
        self.e.at_initiative_count(20);self.assertEqual(MOD.accuracy_stage(self.b),0);self.valid()

    def test_grapple_actual_automatic_struggle_uses_same_penalty_and_request_replay_is_inert(self):
        self.setup();self.e.grid=Grid(8,8)
        F.base_patch(self.p,{'skills':{'전투':4,'육상':4}},reason='actual grappler')
        F.base_patch(self.b,{'skills':{'전투':4,'육상':4}},reason='actual defender');self.start()
        relation=self.e.grapple(self.p,self.b,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4})
        self.assertEqual(relation['dominant'],self.p.entity_id)
        self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20)
        ap=AP.available(self.a);hp=self.b.hp
        result=self.e.grapple_action(self.p,'attack',request_id='actual-grapple-hit')
        self.assertLess(self.b.hp,hp);self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(len(self.effects()),1)
        self.assertEqual(self.e.grapple_action(self.p,'attack',request_id='actual-grapple-hit'),result)
        self.assertEqual(AP.available(self.a),ap-1);self.assertEqual(len(self.effects()),1);self.valid()

    def test_restore_rejects_changed_actual_recipient_and_penalty(self):
        self.setup();self.start();self.hit();self.restore();self.valid()
        event=self.effects()[0]['gleeful_origin']['event_id'];ap=AP.available(self.a)
        PASSIVE.deliver(self.e,event);self.assertEqual(AP.available(self.a),ap);self.assertEqual(len(self.effects()),1)
        self.effects()[0]['accuracy_modifier']=-3
        with self.assertRaises(ValueError):GI.validate_world(self.e,{a.entity_id:a for a in self.e.everyone})

    def test_wonder_guard_selected_attack_universe_keeps_custom_weakness_and_defense_only_types_separate(self):
        import type_state as TYPES
        helper=TYPE_FIXTURE.Tests();helper.core=self.rules
        e,attacker,target=helper.engine();e.gm.set_ability(target,'불가사의부적',reason='actual Wonder Guard owner')
        e.gm.set_types(target,[],reason='actual absence of natural weaknesses')
        self.assertNotIn('에러',TYPES.attack_types(e.r));self.assertNotIn('유리',TYPES.attack_types(e.r))
        self.assertTrue(e.accuracy_check(attacker,target,e.r.move('move/물대포'),fixed_roll=20)[0])
        for bad in ('에러','유리','unknown-type'):
            with self.assertRaises(ValueError):e.roll_damage(attacker,target,dict(e.r.move('move/물대포'),type=bad),set_damage=True)
        custom=deepcopy(self.rules);matrix=dict.fromkeys(TYPES.CORE_TYPES+('수정',),1);matrix['수정']=2
        custom.ruleset.profile['type_extensions']={'수정':{'source_id':TYPES.EXAMPLE_SOURCE,
            'reason':'GM adopts a complete custom attack and defense matrix from the selected example source',
            'attack_vs':dict(matrix),'defense_vs':dict(matrix)}}
        e,attacker,target=helper.engine(custom)
        e.gm.set_ability(target,'불가사의부적',reason='actual selected custom-type holder')
        e.gm.set_types(target,['수정'],reason='only the selected custom attack type is a weakness')
        self.assertTrue(all(e.type_multiplier(kind,target)[0]==1 for kind in TYPES.CORE_TYPES))
        self.assertGreater(e.type_multiplier('수정',target)[0],1)
        self.assertFalse(e.accuracy_check(attacker,target,e.r.move('move/물대포'),fixed_roll=20)[0])


if __name__=='__main__':unittest.main()
