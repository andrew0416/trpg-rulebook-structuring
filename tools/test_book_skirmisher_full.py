"""Skirmisher's whole source contract through actual acquisition and native play."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import skirmisher as S,trainer_feature_acquisition as T,acquired_features as AC
import optional_weapon_framework as OW,weapon_actions as WA,turn
import state_grants as G,world_entities as W,frequency as F,action_points as AP
import combat_timing as TIME,initiative as INIT


class SkirmisherFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='fantasy');cls.base_rulings=deepcopy(cls.rules.rulings)
        import setup_move_state,stellar_tera_blast
        setup_move_state._policy(cls.rules);stellar_tera_blast._policy(cls.rules)

    def scene(self,*,features=(),combat=6,acrobatics=6,edition='supplement',ability=S.FLUTTER,counter='english_free',finesse='korean_damaging',positions=((3,4),(4,4),(8,4))):
        self.rules.rulings=deepcopy(self.base_rulings);self.e=Engine(self.rules,seed=102670)
        self.e.grid=Grid(20,16);self.edition=edition;self.ability=ability;self.counter=counter;self.finesse=finesse
        self.people=[]
        for n,pos in enumerate(positions):
            actor=Combatant(self.rules,build_trainer(self.rules,'Skirmisher actual '+str(n),40,
                {'hp':300,'atk':20,'def':10,'spa':20,'spd':10,'spe':30-n*5},moves=['move/몸통박치기'],abilities=[],
                pos=pos,side='party' if n==0 else 'foe',skills={'전투':combat,'곡예':acrobatics,'육상':5,'집중':5,'직감':5},
                extra={'movement':{'land':6},'movement_basis':'current','weight_kg':40}))
            self.e.gm.add_combatant(actor);prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual complete Skirmisher body')
            self.people.append(actor)
        self.a,self.b,self.c=self.people;self.initial_spe=self.a.stats['spe']
        for u in features:self.acquire(u)

    def acquire(self,u,*,request=None,**overrides):
        parents={S.NIMBLE:S.CLASS,S.COUNTER:S.CLASS,S.HARRIER:S.CLASS,S.FINESSE:S.COUNTER,S.OUT:S.HARRIER,S.SWIFT:S.CLASS}
        if u in parents and S.acquired(self.a,parents[u])is None:self.acquire(parents[u])
        selection={'edition':self.edition}
        if u==S.CLASS:selection['ability']=self.ability
        if u==S.COUNTER:selection['counter_cost']=self.counter
        if u==S.FINESSE:selection['trigger_scope']=self.finesse
        selection.update(overrides)
        return T.acquire_static(self.e,self.a,u,acquisition_request_id=request or 'skirmisher/'+u,selection=selection)

    def combat(self,actor=None):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=20)

    def weapon(self,actor=None,*,uid='skirmisher/actual-sword',moves=(),kind='소형 근접무기'):
        actor=actor or self.a
        W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual owned melee weapon',owner_id=actor.entity_id,weight_kg=1,kind='physical_object')
        OW.observe_weapon(self.e,actor,uid,name=uid,kind=kind,grade='좋음',arcane=False,metal=False,moves=list(moves),reason='observed physical weapon')
        key=OW.equip(self.e,actor,uid);mid=actor.custom_conditions['equipped_weapons'][key]['struggle_id']
        return key,mid

    def attack(self,actor=None,target=None,*,natural=18,mid='move/몸통박치기',key=None):
        actor=actor or self.a;target=target or self.b
        with patch.object(Engine,'d20',return_value=natural):self.e.use_move(actor,target,mid,weapon_id=key,set_damage=True)
        return next(reversed(self.e._move_completions))

    def rejected(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)

    def rejected_state(self,actor,mutation):
        # G's optional completion boundary invokes the unchanged native world
        # validator; G does not itself promise every gameplay-domain check.
        def validate(staged,*subjects):
            import gameplay_validation as GAMEPLAY
            GAMEPLAY.validate(staged,list(W.actor_index(staged).values()))
        return self.rejected(lambda:G.transition(self.e,actor,mutation,completion=validate),'initiative_schedule_contract')

    def restore(self):
        ids=[a.entity_id for a in self.people]
        self.e=Engine.import_state(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        self.rules=self.e.r
        self.people=[W.actor_index(self.e)[u] for u in ids];self.a,self.b,self.c=self.people

    def withdraw(self,u):
        sid=next(s for s,r in G.state(self.a)['sources'].items() if r.get('static_acquisition',{}).get('feature_id')==u)
        def apply(e,a):G.revoke(a,sid,engine=e);a.spec['feats'].remove(u)
        return G.transition(self.e,self.a,apply)

    def test_all_seven_acquisitions_both_editions_choices_stat_tags_slots_replay_codec(self):
        for edition in ('supplement','local_csv'):
            for ability in (S.FLUTTER,S.VANGUARD):
                self.scene(edition=edition,ability=ability);self.acquire(S.CLASS)
                self.assertEqual(set(self.a.spec['feats']),{S.CLASS});self.assertEqual(len(AC.class_instances(self.a)),1)
                self.assertEqual(self.a.abilities,['파닥파닥' if ability==S.FLUTTER else '선봉'])
                for u in S.FEATURES:
                    if u!=S.CLASS:self.acquire(u)
                    self.assertEqual(S.acquired(self.a,u)['snapshot']['source']['edition'],edition)
                    if edition=='local_csv':self.assertEqual(S.acquired(self.a,u)['snapshot']['source']['row'],S.CSV_ROWS[u])
                self.assertEqual(self.a.stats['spe'],self.initial_spe+7)
                self.assertEqual(self.acquire(S.OUT),self.acquire(S.OUT))
                self.rejected(lambda:self.acquire(S.OUT,request='duplicate/out'),'already|duplicate|repeat|acquired')
                self.restore();self.assertEqual(len(S.records(self.a,active=True)),7)
                self.assertEqual(len(AC.class_instances(self.a)),1)

    def test_prerequisites_no_automatic_children_and_forged_ownership_no_authority(self):
        for combat,acrobatics in ((2,6),(6,2)):
            self.scene(combat=combat,acrobatics=acrobatics)
            self.rejected(lambda:self.acquire(S.CLASS),'skill ranks')
        self.scene(combat=3,acrobatics=3);self.acquire(S.COUNTER)
        self.rejected(lambda:self.acquire(S.FINESSE),'skill ranks')
        self.scene();self.acquire(S.CLASS)
        self.rejected(lambda:self.acquire(S.SWIFT),'four actual')
        self.scene();self.a.spec['classes']=['class/운동선수','class/멘토','class/지휘관','class/코디네이터']
        self.rejected(lambda:self.acquire(S.CLASS),'four slots')
        self.scene();self.a.spec['feats']=[S.CLASS,S.OUT]
        self.rejected(lambda:S.arm_attack(self.e,self.a,'move/몸통박치기',outmaneuver=True),'actual acquired')

    def test_flutter_actual_shift_evasion_unflanked_replacement_and_next_owner_turn_end(self):
        self.scene(features=(S.CLASS,),positions=((3,4),(2,4),(4,4)));self.combat()
        self.assertEqual(self.a.evasion_mod,0)
        baseline=self.a.evasion('물리',engine=self.e);self.assertEqual(self.e.spatial_evasion_penalty(self.a),-2)
        self.e.activate_ability(self.a,'파닥파닥',self.a)
        self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a.evasion('물리',engine=self.e),baseline+3)
        self.assertEqual(self.e.spatial_evasion_penalty(self.a),0)
        self.rejected_state(self.a,lambda se,a:next(r for r in TIME.records(a) if r.get('source')==S.FLUTTER).update(evasion_modifier=99))
        self.e.activate_ability(self.a,S.FLUTTER,self.a)
        self.assertEqual(len([r for r in TIME.records(self.a) if r['source']==S.FLUTTER]),1)
        self.restore();self.assertEqual(self.e.spatial_evasion_penalty(self.a),0)
        self.combat();self.assertEqual(self.a.evasion('물리',engine=self.e),baseline+3)
        self.e.end_of_turn(self.a);self.assertEqual(self.a.evasion('물리',engine=self.e),baseline)
        self.assertEqual(self.e.spatial_evasion_penalty(self.a),-2)

    def test_nimble_native_disengage_swift_keeps_shift_and_standard_source_loss(self):
        self.scene(features=(S.NIMBLE,));self.combat()
        self.e.disengage(self.a,(3,5));self.assertEqual(self.a.pos,(3,5))
        self.assertEqual(self.a.budget,{'standard':1,'shift':1,'swift':0})
        S.disengage(self.e,self.a,(3,6),as_swift=False)
        self.assertEqual(self.a.budget,{'standard':1,'shift':0,'swift':0})
        self.withdraw(S.NIMBLE);self.combat();self.e.disengage(self.a,(3,7))
        self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a.budget['swift'],1)

    def test_vanguard_native_damage_only_faster_and_target_not_ordinary_acted_this_round(self):
        self.scene();self.combat();before=self.b.hp;self.attack();plain=before-self.b.hp
        self.scene(features=(S.CLASS,),ability=S.VANGUARD);self.combat();before=self.b.hp;self.attack()
        self.assertEqual(before-self.b.hp,plain+5)
        self.scene(features=(S.CLASS,),ability=S.VANGUARD);self.combat(self.b);self.e.end_of_turn(self.b)
        self.e.start_of_turn(self.a,initiative_count=20);before=self.b.hp;self.attack()
        self.assertEqual(before-self.b.hp,plain)

    def test_harrier_native_hit_flanked_slow_priority_interrupt_per_foe_scene_and_restore(self):
        self.scene(features=(S.HARRIER,));self.combat();completion=self.attack()
        S.harrier(self.e,self.a,self.b,completion)
        self.assertIn('둔화',self.b.conditions);self.assertEqual(self.e.spatial_evasion_penalty(self.b),-2)
        self.rejected_state(self.b,lambda se,a:next(r for r in TIME.records(a) if r.get('source')==S.HARRIER).update(skirmisher_forbidden=[]))
        self.rejected_state(self.b,lambda se,a:next(r for r in TIME.records(a) if r.get('source')==S.HARRIER).update(origin_completion='fabricated/completion'))
        self.restore();self.assertEqual(self.e.spatial_evasion_penalty(self.b),-2)
        owner=self.e._active_turn_actor
        trigger={'kind':'turn','actor_id':owner.entity_id,'serial':owner.custom_conditions['combat_turn_serial'],'round':self.e.round_no}
        declaration={'id':'blocked/harrier','actor_id':self.b.entity_id,'source':'move/몸통박치기','priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
        self.rejected(lambda:self.e.queue_initiative_reactions([declaration],trigger=trigger),'Harrier')
        self.rejected(lambda:S.harrier(self.e,self.a,self.b,completion),'cannot follow another action|once per foe')
        self.combat();self.assertIn('둔화',self.b.conditions)
        next_hit=self.attack();self.rejected(lambda:S.harrier(self.e,self.a,self.b,next_hit),'once per foe')
        self.e.end_of_turn(self.a);self.assertNotIn('둔화',self.b.conditions)
        self.assertEqual(self.e.spatial_evasion_penalty(self.b),0)
        from passive_events import PassiveEventPending
        for ability in ('회피','테라셸'):
            self.scene(features=(S.HARRIER,));self.combat();completion=self.attack()
            S.harrier(self.e,self.a,self.b,completion)
            G.replace_baseline(self.e,self.b,'abilities',[ability]);self.combat(self.b)
            self.e.gm.set_move(self.b,'move/전광석화',reason='actual independent Priority Move')
            self.rejected(lambda:self.attack(self.b,self.a,mid='move/전광석화'),'Harrier')
            self.e.end_of_turn(self.b);self.e.start_of_turn(self.a,initiative_count=20)
            if ability=='회피':
                self.e.watch_move_defense(self.b,[{'actor_id':self.b.entity_id,'source':'ability/회피'}],reason='actual Harrier forbids Dodge Interrupt')
            else:self.e.watch_ability_interrupt(self.b,'ability/테라셸',reason='actual Harrier forbids recipient Interrupt')
            hp=self.b.hp
            with self.assertRaises(PassiveEventPending):self.attack()
            event=self.e._passive_pending;self.restore()
            if ability=='회피':
                self.rejected(lambda:self.e.choose_move_defense(event,self.b,use=True,options={},reason='actual forbidden Dodge'),'Harrier')
                self.e.choose_move_defense(event,self.b,use=False,reason='actual Dodge decline still legal')
            else:
                self.rejected(lambda:self.e.choose_ability_interrupt(event,self.b,use=True,options={'chosen_type':'바위'},reason='actual forbidden Tera Shell'),'Harrier')
                self.e.choose_ability_interrupt(event,self.b,use=False,reason='actual Tera Shell decline still legal')
            self.assertIsNone(self.e._passive_pending);self.assertLess(self.b.hp,hp)
            self.assertIn('둔화',self.b.conditions);self.assertEqual(getattr(self.b,'_action_history',[]),[])
            self.withdraw(S.HARRIER);self.assertIn('둔화',self.b.conditions)
            self.e.end_of_turn(self.a);self.assertNotIn('둔화',self.b.conditions)
        # Gale Wings supplies Priority through actual registered source effects.
        self.scene(features=(S.HARRIER,));mid='move/바람일으키기'
        self.e.gm.set_ability(self.b,'ability/질풍날개',reason='actual observed core Gale Wings ability')
        self.e.gm.set_move(self.b,mid,reason='actual observed learned Flying Move')
        self.assertEqual(self.rules._selected_rule('ability/질풍날개'),'ability/질풍날개')
        move=self.rules.move(mid)
        raw=set(move.get('keywords') or ())|set(self.rules.moves_mech.get(mid,{}).get('header',{}).get('keywords') or ())
        self.assertNotIn('우선',raw);self.assertNotIn('우선',move.get('range',''))
        self.assertTrue(any(effect.get('_rule_id')=='ability/질풍날개' and effect.get('type')=='gain_keyword'
            and effect.get('keyword')=='우선' and effect.get('moves')=='비행' for effect in self.b.registry))
        self.assertTrue(turn.has_priority(self.e,self.b,move))
        self.combat();completion=self.attack();S.harrier(self.e,self.a,self.b,completion)
        self.combat(self.b)
        self.rejected(lambda:self.attack(self.b,self.a,mid=mid),'Harrier')
        self.restore()
        self.rejected(lambda:self.attack(self.b,self.a,mid=mid),'Harrier')
        self.combat();self.e.end_of_turn(self.a);self.assertNotIn('둔화',self.b.conditions)
        self.combat(self.b);hp=self.a.hp;self.attack(self.b,self.a,mid=mid)
        self.assertLess(self.a.hp,hp);self.assertEqual(self.b.budget['standard'],0)

    def test_harrier_miss_ally_stale_and_withdrawal_do_not_fabricate_trigger(self):
        self.scene(features=(S.HARRIER,));self.combat();completion=self.attack(natural=1)
        self.rejected(lambda:S.harrier(self.e,self.a,self.b,completion),'nonprevented hit')
        self.combat();completion=self.attack();self.e.disengage(self.a,(3,5))
        self.rejected(lambda:S.harrier(self.e,self.a,self.b,completion),'cannot follow another action')
        self.withdraw(S.HARRIER)
        self.rejected(lambda:S.harrier(self.e,self.a,self.b,completion),'actual acquired')

    def test_outmaneuver_native_accuracy_initiative_not_speed_scene_quota_and_codec(self):
        self.scene(features=(S.OUT,));self.combat();base_spe=self.b.stats['spe'];base=INIT.value(self.rules,self.b,engine=self.e).value
        ev=self.a.evasion('물리',engine=self.e)
        S.arm_attack(self.e,self.a,'move/몸통박치기',outmaneuver=True,evasion_class='물리')
        completion=self.attack(natural=18);row=self.e._move_completions[completion]
        self.assertEqual(row['skirmisher_attack']['evasion'],ev)
        self.assertEqual(INIT.value(self.rules,self.b,engine=self.e).value,base-ev)
        self.assertEqual(self.b.stats['spe'],base_spe);self.assertEqual(self.b.stages['spe'],0)
        self.restore();self.assertEqual(INIT.value(self.rules,self.b,engine=self.e).value,base-ev)
        for _ in range(2):
            self.combat();S.arm_attack(self.e,self.a,'move/몸통박치기',outmaneuver=True);self.attack(natural=1)
        self.combat();S.arm_attack(self.e,self.a,'move/몸통박치기',outmaneuver=True)
        self.rejected(lambda:self.attack(),'frequency exhausted')

    def test_outmaneuver_native_accuracy_bonus_changes_hit_and_miss_has_no_initiative_effect(self):
        self.scene(features=(S.OUT,));self.combat();ev=self.a.evasion('물리',engine=self.e)
        # AC2 + target Physical Evasion6: 6 misses, but the genuine bonus3 hits.
        with patch.object(Engine,'d20',return_value=6):plain=self.e.accuracy_check(self.a,self.b,self.rules.move('move/몸통박치기'))[0]
        self.assertFalse(plain)
        S.arm_attack(self.e,self.a,'move/몸통박치기',outmaneuver=True)
        completion=self.attack(natural=6);self.assertTrue(self.e._move_completions[completion]['results'][self.b.entity_id]['hit'])
        self.assertEqual(self.e._move_completions[completion]['skirmisher_attack']['evasion'],ev)

    def test_counter_stance_actual_adjacent_miss_free_or_full_current_and_future_cost(self):
        for cost in ('english_free','korean_full'):
            self.scene(features=(S.COUNTER,),counter=cost);self.combat(self.b);completion=self.attack(self.b,self.a,natural=1)
            before=self.b.hp
            with patch.object(Engine,'d20',return_value=18):S.counter_stance(self.e,self.a,self.b,completion,request_id='counter/'+cost)
            self.assertLess(self.b.hp,before);self.assertTrue(self.a.aoo_used)
            self.assertIs(self.e._active_turn_actor,self.b)
            self.rejected(lambda:S.counter_stance(self.e,self.a,self.b,completion,request_id='repeat'),'eligible|already')
            self.e.end_of_turn(self.b);self.e.start_of_turn(self.a,initiative_count=20)
            self.assertEqual(self.a.budget['standard'],0 if cost=='korean_full' else 1)
            self.assertEqual(self.a.budget['shift'],0 if cost=='korean_full' else 1)
            self.restore()
        from passive_events import PassiveEventPending
        self.scene(features=(S.COUNTER,),counter='korean_full')
        G.replace_baseline(self.e,self.b,'abilities',['테라셸'])
        self.e.watch_ability_interrupt(self.b,'ability/테라셸',reason='actual Counter AoO recipient Interrupt')
        self.combat(self.b);completion=self.attack(self.b,self.a,natural=1);hp=self.b.hp
        with self.assertRaises(PassiveEventPending),patch.object(Engine,'d20',return_value=18):
            S.counter_stance(self.e,self.a,self.b,completion,request_id='counter/native-pending')
        self.assertTrue(self.a.aoo_used);self.restore()
        self.rejected_state(self.a,lambda se,a:a.spec[S.COUNTER_STATE].update(completion_id='fabricated/completion'))
        self.rejected(lambda:self.withdraw(S.COUNTER),'paid Counter Stance continuation')
        self.e.choose_ability_interrupt(self.e._passive_pending,self.b,use=False,reason='actual Counter recipient declines Tera Shell')
        self.assertTrue(S.counter_stance(self.e,self.a,self.b,completion,request_id='counter/native-pending'))
        self.assertLess(self.b.hp,hp);self.assertNotIn(S.COUNTER_STATE,self.a.spec);self.assertIs(self.e._active_turn_actor,self.b)
        self.assertEqual(len([r for r in self.e._move_completions.values() if r['actor']is self.a]),1)
        self.e.end_of_turn(self.b);self.e.start_of_turn(self.a,initiative_count=20)
        self.assertEqual(self.a.budget,{'standard':0,'shift':0,'swift':1});self.restore()

    def test_weapon_finesse_three_native_maneuvers_auto_hit_actual_opposed_cost_and_source_policy(self):
        options={'challenger_skill':'전투','defender_skill':'전투','fixed_accuracy':1,'challenger_options':{'fixed':[6]*6},'defender_options':{'fixed':[1]*6}}
        for maneuver in ('trip','push','disarm'):
            self.scene(features=(S.FINESSE,));self.combat();key,mid=self.weapon()
            if maneuver=='disarm':self.weapon(self.b,uid='enemy/actual-sword')
            completion=self.attack(mid=mid,key=key);before=AP.available(self.a)
            actual=deepcopy(options)
            if maneuver=='disarm':actual['attacker_skill']=actual.pop('challenger_skill')
            result=S.weapon_finesse(self.e,self.a,self.b,completion,maneuver,**actual)
            self.assertTrue(result);self.assertEqual(AP.available(self.a),before-2)
            self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['standard'],0)
            if maneuver=='trip':self.assertIn('넘어짐',self.b.conditions)
            if maneuver=='push':self.assertEqual(self.b.pos,(5,4))
            if maneuver=='disarm':self.assertFalse(self.b.custom_conditions.get('equipped_weapons'))
            self.rejected(lambda:S.weapon_finesse(self.e,self.a,self.b,completion,maneuver,**actual),'already used')
        self.scene(features=(S.FINESSE,),finesse='english_weapon');self.combat();completion=self.attack()
        self.rejected(lambda:S.weapon_finesse(self.e,self.a,self.b,completion,'trip',**options),'requires a Weapon Attack')

    def test_swift_strikes_actual_weapon_priority_upgrade_one_standard_one_ap_and_withdrawal(self):
        self.scene(features=(S.NIMBLE,S.COUNTER,S.HARRIER,S.SWIFT));key,mid=self.weapon();self.combat()
        before=AP.available(self.a);S.arm_attack(self.e,self.a,mid,weapon_id=key,swift=True)
        prepared=S.prepare_move(self.e,self.a,WA.prepare(self.e,self.a,self.rules.move(mid),key))
        self.assertIn('우선',prepared['keywords'])
        self.attack(mid=mid,key=key);self.assertEqual(AP.available(self.a),before-1)
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['shift'],1)
        self.combat();S.arm_attack(self.e,self.a,mid,weapon_id=key,swift=True)
        raw=WA.prepare(self.e,self.a,self.rules.move(mid),key);raw['keywords']=['우선']
        self.assertIn('우선(고급)',S.prepare_move(self.e,self.a,raw)['keywords'])
        self.withdraw(S.SWIFT)
        self.assertNotIn(S.ARM,self.a.spec)
        self.rejected(lambda:S.arm_attack(self.e,self.a,mid,weapon_id=key,swift=True),'actual acquired')

    def test_source_withdrawal_preserves_independent_ability_and_removes_only_owned_speed(self):
        self.scene(features=(S.CLASS,));self.a.spec.setdefault('abilities',[]).append('파닥파닥')
        self.withdraw(S.CLASS);self.assertIn('파닥파닥',self.a.abilities)
        self.assertEqual(self.a.stats['spe'],self.initial_spe);self.assertEqual(len(AC.class_instances(self.a)),0)

    def test_outmaneuver_native_area_uses_one_cost_and_every_actual_hit_enemy(self):
        self.scene(features=(S.OUT,),positions=((0,1),(5,1),(6,2)));self.combat()
        key,_=self.weapon(moves=('move/일제사격',),kind='장거리 사격무기');mid='move/일제사격'
        before=[INIT.value(self.rules,t,engine=self.e).value for t in (self.b,self.c)];ev=self.a.evasion('물리',engine=self.e)
        S.arm_attack(self.e,self.a,mid,weapon_id=key,outmaneuver=True)
        with patch.object(Engine,'d20',return_value=18):self.e.use_move_on(self.a,self.b,mid,self.e.everyone,weapon_id=key,aim=(5,1),set_damage=True)
        row=next(reversed(self.e._move_completions.values()))
        self.assertEqual(set(row['results']),{self.b.entity_id,self.c.entity_id})
        self.assertEqual([INIT.value(self.rules,t,engine=self.e).value for t in (self.b,self.c)],[v-ev for v in before])
        self.assertEqual(F.state(self.a)['activations'][S.OUT]['used'],1);self.assertEqual(self.a.budget['standard'],0)

    def test_outmaneuver_actual_intercept_pending_restore_harrier_only_received_foe(self):
        from passive_events import PassiveEventPending
        import move_completion as MC
        self.scene(features=(S.OUT,),positions=((2,4),(8,4),(6,7)));key,mid=self.weapon(kind='장거리 사격무기');self.combat()
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual Skirmisher ranged Intercept')
        base=[INIT.value(self.rules,t,engine=self.e).value for t in (self.b,self.c)];ev=self.a.evasion('물리',engine=self.e)
        S.arm_attack(self.e,self.a,mid,weapon_id=key,outmaneuver=True)
        with self.assertRaises(PassiveEventPending):self.attack(mid=mid,key=key)
        self.assertEqual(F.state(self.a)['activations'][S.OUT]['used'],1);self.assertEqual(self.a.budget['standard'],0)
        self.restore()
        self.e.choose_move_defense(self.e._passive_pending,self.c,use=True,options={'path':[(6,7),(6,6),(6,5),(6,4)],'skill':'육상','mode':'land','roll_options':{'fixed':[6]*5}},reason='actual successful Intercept')
        row=next(r for r in self.e._move_completions.values() if r['actor']is self.a)
        self.assertIsNone(MC.recipient_result(row,self.b));self.assertTrue(MC.recipient_result(row,self.c)['hit'])
        self.assertEqual(INIT.value(self.rules,self.b,engine=self.e).value,base[0]);self.assertEqual(INIT.value(self.rules,self.c,engine=self.e).value,base[1]-ev)
        self.rejected(lambda:S.harrier(self.e,self.a,self.b,row['id']),'nonprevented hit')
        S.harrier(self.e,self.a,self.c,row['id']);self.assertNotIn('둔화',self.b.conditions);self.assertIn('둔화',self.c.conditions)
        self.assertEqual(F.state(self.a)['activations'][S.OUT]['used'],1);self.restore()

    def test_finesse_native_trip_splash_pending_restore_same_cost_and_opposed_once(self):
        from common_checks import PendingDecision
        from tumbler_fixture import TumblerScene
        import tumbler as TUMBLER,jump_actions as JUMP
        self.scene(features=(S.FINESSE,));key,mid=self.weapon();self.combat();completion=self.attack(mid=mid,key=key)
        self.b.spec.setdefault('edges',[]).append(TUMBLER.ACROBAT);self.b.spec['movement'].update(high_jump=1,long_jump=2,power=4);self.b.spec['weight_kg']=30
        fixture=TumblerScene();fixture.e=self.e;fixture.rules=self.rules;fixture.a=self.b;fixture.family(TUMBLER.FLIP)
        self.e.watch_move_defense(self.b,[{'actor_id':self.b.entity_id,'source':TUMBLER.SPLASH}],reason='actual Finesse Trip native Splash')
        self.e.rulings.add_answer('native_attack_splash',{'jump':{'destination':(4,5),'difficult':True,'difficulty_skill':'곡예','difficulty_dc':100,'difficulty_options':{'fixed':[1]*6},'clear_path':True}})
        options={'challenger_skill':'전투','defender_skill':'곡예','fixed_accuracy':1,'challenger_options':{'fixed':[6]*6},'defender_options':{'fixed':[1]*6}}
        before=AP.available(self.a)
        result=S.weapon_finesse(self.e,self.a,self.b,completion,'trip',**options);self.assertIsInstance(result,PendingDecision)
        self.assertIn('_jump_pending',self.b.spec);self.assertEqual(AP.available(self.a),before-2)
        self.rejected_state(self.a,lambda se,a:a.spec[S.FINESSE_STATE].update(completion_id='fabricated/completion'))
        self.restore();self.rejected(lambda:S.weapon_finesse(self.e,self.a,self.b,completion,'push',**options),'same actual')
        jump_id=self.b.spec['_jump_pending'];JUMP.resolve_failure(self.e,self.b,decision='land',reason_text='actual Finesse reaction Jump lands');self.e.resume_jump_move(self.b,event_id=jump_id)
        with patch.object(Engine,'accuracy_check',side_effect=AssertionError('automatic Finesse Trip cannot reroll accuracy')):
            self.assertTrue(S.weapon_finesse(self.e,self.a,self.b,completion,'trip',**options))
        self.assertIn('넘어짐',self.b.conditions);self.assertEqual(AP.available(self.a),before-2);self.assertNotIn(S.FINESSE_STATE,self.a.spec);self.restore()

    def test_swift_strikes_actual_priority_reaction_pays_one_future_standard_and_one_ap(self):
        import initiative_interrupts as I
        self.scene(features=(S.NIMBLE,S.COUNTER,S.HARRIER,S.SWIFT));key,mid=self.weapon();self.combat(self.b)
        S.arm_attack(self.e,self.a,mid,weapon_id=key,swift=True);before=AP.available(self.a)
        declaration={'id':'actual/swift-priority','actor_id':self.a.entity_id,'source':S.SWIFT,'move_id':mid,'priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
        trigger={'kind':'turn','actor_id':self.b.entity_id,'serial':self.b.custom_conditions['combat_turn_serial'],'round':self.e.round_no}
        window=I.queue(self.e,[declaration],trigger=trigger)['window_id'];I.begin(self.e,window,declaration['id'])
        self.attack(mid=mid,key=key);I.finish(self.e)
        self.assertEqual(AP.available(self.a),before-1);self.assertIs(self.e._active_turn_actor,self.b)
        self.e.end_of_turn(self.b);self.e.start_of_turn(self.a,initiative_count=20)
        self.assertEqual(self.a.budget,{'standard':0,'shift':1,'swift':1});self.restore()


if __name__=='__main__':unittest.main()
