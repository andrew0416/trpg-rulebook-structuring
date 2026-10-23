"""Whole Roughneck through acquired Features, native Moves, actual reactions and common lifetimes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import test_book_dancer_acquisition as fixture
import roughneck as R,trainer_feature_acquisition as T,action_points as AP,combat_timing as CLOCK
import frequency as F,combat_modifiers as MOD,temporary_hp as HP,world_entities as W,state_codec as CODEC


class RoughneckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    def setUp(self):
        previous=self.rules.rulings;self.rules.rulings=deepcopy(previous)
        self.addCleanup(setattr,self.rules,'rulings',previous)
        self.e=Engine(self.rules,seed=23481);self.e.grid=Grid(16,14)
        self.t=self.add('Roughneck',(3,3),speed=30,edges=[R.PRESENCE])
    def add(self,name,pos,side='party',speed=20,power=20,skills=None,edges=None,**extra):
        spec=dict(deepcopy(fixture.COMMON),name=name,kind='trainer',feats=[],classes=[],edges=edges or [],moves=[],items={},exp_bank=50)
        spec['stats'].update(spe=speed,atk=power,spa=power)
        spec['skills'].update(협박=6,집중=6)
        if skills:spec['skills'].update(skills)
        spec.update(extra);actor=Combatant(self.rules,spec)
        self.e.gm.add_combatant(actor,pos=pos,side=side,reason='observed complete trainer sheet')
        prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete body')
        import items
        items.register_feats(self.e,actor)
        return actor
    def foe(self,**kw):return self.add('foe',(4,3),side='enemy',speed=15,**kw)
    def acquire(self,feature):return T.acquire_static(self.e,self.t,feature,acquisition_request_id='roughneck/'+feature)
    def roughneck(self,*features):
        self.acquire(R.CLASS)
        wanted=set(features)
        if R.DISPLAY in wanted:wanted.add(R.MALICE)
        if R.NAILS in wanted:wanted.update((R.MALICE,R.GAZE))
        for feature in R.FEATURES[1:]:
            if feature in wanted:self.acquire(feature)
    combat=fixture.DancerAcquisitionTests.combat
    next_turn=fixture.DancerAcquisitionTests.next_turn
    use=fixture.DancerAcquisitionTests.use
    restore=fixture.DancerAcquisitionTests.restore
    retrain=fixture.DancerAcquisitionTests.retrain
    valid=fixture.DancerAcquisitionTests.valid
    def rejected(self,operation,pattern):
        before=self.e.export_state()
        try:return assert_rejected_unchanged(self.e,operation,reason_pattern=pattern)
        except AssertionError as error:
            after=self.e.export_state();differences=[]
            def compare(a,b,path=''):
                if a==b:return
                if type(a) is dict and type(b) is dict:
                    for key in set(a)|set(b):compare(a.get(key),b.get(key),path+'/'+str(key))
                elif type(a) is list and type(b) is list and len(a)==len(b):
                    for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i))
                else:differences.append((path,str(a)[:80],str(b)[:80]))
            compare(before,after)
            raise AssertionError(str(error)+'; changed='+repr(differences[:12])) from error
    answer=fixture.DancerAcquisitionTests.answer
    def latest(self,actor=None,move=None):
        return next(r for r in reversed(list(self.e._move_completions.values())) if (actor is None or r['actor'] is actor) and (move is None or r['move_id']==move))
    def terrorize(self,target,face=20,won=True):
        return self.e.manipulate(self.t,target,'terrorize',defender_skill='집중',fixed_accuracy=face,
            challenger_options={'fixed':[6 if won else 1]*6},defender_options={'fixed':[1 if won else 6]*6})
    def display(self,value=True):self.answer('roughneck_display',value)

    def test_template_and_class_acquisition_do_not_grant_children(self):
        before=self.t.stats['def'];self.roughneck()
        self.assertEqual(len(R.FEATURES),7);self.assertEqual(self.t.spec['feats'],[R.CLASS])
        self.assertEqual(self.t.stats['def'],before+1);self.assertEqual(set(self.t.moves),{'move/째려보기'})
        self.assertEqual(T.STATIC_FEATURES[R.CLASS]['catalog_span'],[2649,2649]);self.valid()
    def test_class_requires_actual_presence_and_novice_athletics(self):
        for name,skills,edges,reason in [('no edge',{},[],'Presence'),('low athletics',{'육상':2},[R.PRESENCE],'Athletics')]:
            actor=self.add(name,(1,1),skills=skills,edges=edges)
            self.rejected(lambda:T.acquire_static(self.e,actor,R.CLASS,acquisition_request_id=name),reason)
    def test_each_rank_and_three_feature_requirement(self):
        self.roughneck();self.rejected(lambda:self.acquire(R.NAILS),'three acquired')
        for feature,rank in ((R.MALICE,3),(R.GAZE,4),(R.NAILS,5)):
            actor=self.add(feature,(1,2),skills={'협박':rank},edges=[R.PRESENCE])
            T.acquire_static(self.e,actor,R.CLASS,acquisition_request_id=feature+'/class')
            self.rejected(lambda:T.acquire_static(self.e,actor,feature,acquisition_request_id=feature),'skill rank')
    def test_all_children_fixed_moves_tags_replay_restore_and_withdrawal(self):
        before=self.t.stats['def'];self.roughneck(*R.FEATURES[1:])
        self.assertEqual(set(self.t.moves),set(R.MOVES));self.assertEqual(self.t.stats['def'],before+7)
        self.acquire(R.NAILS);self.assertEqual(self.t.stats['def'],before+7)
        self.restore('t');self.retrain(R.NAILS)
        self.assertNotIn('move/버티기',self.t.moves);self.assertIn('move/검은눈빛',self.t.moves)
        self.assertEqual(self.t.stats['def'],before+6);self.valid()
    def test_hit_selects_one_stat_and_spends_one_ap_one_swift(self):
        self.roughneck();foe=self.foe();self.combat(self.t);before=AP.available(self.t)
        self.answer('roughneck_hit','spd');self.use(self.t,foe,'move/몸통박치기')
        self.assertEqual(foe.stages['spd'],-1);self.assertEqual(AP.available(self.t),before-1)
        self.assertEqual(self.t.budget['swift'],0);self.valid()
    def test_miss_and_ally_hit_never_offer_class_reduction(self):
        self.roughneck();foe=self.foe();self.combat(self.t);before=AP.available(self.t)
        self.answer('roughneck_hit','atk');self.use(self.t,foe,'move/몸통박치기',face=1)
        self.assertEqual(foe.stages['atk'],0);self.assertEqual(AP.available(self.t),before)
        ally=self.add('ally',(3,4));self.next_turn(self.t);self.use(self.t,ally,'move/몸통박치기')
        self.assertEqual(ally.stages['atk'],0);self.assertEqual(AP.available(self.t),before)
    def test_invalid_stat_cannot_commit_move_or_resource(self):
        self.roughneck();foe=self.foe();self.combat(self.t);self.e.gm.set_move(self.t,'move/몸통박치기',reason='known attack')
        self.answer('roughneck_hit','hp')
        self.rejected(lambda:self.use(self.t,foe,'move/몸통박치기'),'Combat Stat')
    def test_menace_requires_actual_terrorize_success(self):
        self.roughneck(R.MENACE);foe=self.foe();self.combat(self.t);self.answer('roughneck_menace',True)
        self.assertFalse(self.terrorize(foe,face=1));self.assertIsNone(foe.initiative_override)
        other=self.add('opposed winner',(4,4),side='enemy');self.next_turn(self.t)
        self.assertFalse(self.terrorize(other,won=False));self.assertEqual(other.initiative_override,0)  # accuracy hit, opposed effect failed
    def test_menace_has_independent_next_turn_start_and_full_round_expiries(self):
        self.roughneck(R.MENACE);self.p=self.foe();self.combat(self.t);self.answer('roughneck_menace',True)
        self.assertTrue(self.terrorize(self.p));self.assertEqual(self.p.initiative_override,0)
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=0)
        self.assertIsNone(self.p.initiative_override);self.assertEqual(MOD.incoming_status_threshold(self.p,'풀죽음',15),11)
        self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.t,initiative_count=30)
        self.assertEqual(MOD.incoming_status_threshold(self.p,'풀죽음',15),15)
    def test_menace_native_new_flinch_17_and_existing_headbutt_plus_four(self):
        for move,face,flinched in [('move/몸통박치기',16,False),('move/몸통박치기',17,True),('move/박치기',11,True)]:
            with self.subTest(move=move,face=face):
                self.setUp();self.roughneck(R.MENACE);foe=self.foe();ally=self.add('striker',(4,4),speed=25)
                self.combat(self.t);self.answer('roughneck_menace',True);self.terrorize(foe)
                self.e.end_of_turn(self.t);self.e.start_of_turn(ally,initiative_count=25)
                self.use(ally,foe,move,face=face)
                self.assertEqual('풀죽음' in foe.conditions,flinched)
    def test_menace_timers_roundtrip_and_source_loss_preserve_already_applied_effect(self):
        self.roughneck(R.MENACE);self.p=self.foe();self.combat(self.t);self.answer('roughneck_menace',True);self.terrorize(self.p)
        self.restore('t','p');self.assertEqual(self.p.initiative_override,0)
        self.e.end_scene(self.e.everyone);self.retrain(R.MENACE)
        self.assertFalse(any(r['source']==R.MENACE for r in CLOCK.records(self.p)));self.valid()
    def test_fearsome_leer_only_actual_cone_foes_and_critical_consumer(self):
        self.roughneck(R.DISPLAY);foe=self.foe();far=self.add('outside',(8,3),side='enemy');ally=self.add('ally',(4,4))
        self.combat(self.t);self.display();ap=AP.available(self.t);self.use(self.t,foe,'move/째려보기',aim=(5,3))
        self.assertEqual(MOD.incoming_critical_bonus(foe),2);self.assertEqual(MOD.incoming_critical_bonus(far),0)
        self.assertEqual(MOD.incoming_critical_bonus(ally),0);self.assertEqual(AP.available(self.t),ap-2)
        self.e.end_of_turn(self.t);self.e.start_of_turn(ally,initiative_count=20)
        critical=[];original=Engine.roll_damage
        def observe(engine,attacker,target,move,crit=False,*args,**kwargs):
            if attacker.entity_id==ally.entity_id:critical.append(crit)
            return original(engine,attacker,target,move,crit,*args,**kwargs)
        with patch.object(Engine,'roll_damage',observe):self.use(ally,foe,'move/몸통박치기',face=18)
        self.assertIn(True,critical)
    def test_fearsome_chip_away_vulnerable_for_only_this_attack(self):
        self.roughneck(R.DISPLAY);foe=self.foe();self.combat(self.t);self.display()
        self.use(self.t,foe,'move/야금야금',face=2)
        self.assertTrue(self.latest(self.t)['results'][foe.entity_id]['hit']);self.assertNotIn('취약',foe.conditions)
        self.next_turn(self.t);self.display(False);self.use(self.t,foe,'move/몸통박치기',face=2)
        self.assertFalse(self.latest(self.t)['results'][foe.entity_id]['hit'])
    def test_fearsome_headbutt_zero_expires_at_end_not_start_of_next_turn(self):
        self.roughneck(R.DISPLAY,R.GAZE);foe=self.foe();self.combat(self.t);self.display();self.use(self.t,foe,'move/박치기')
        self.assertEqual(foe.initiative_override,0);self.e.end_of_turn(self.t)
        self.e.start_of_turn(foe,initiative_count=0);self.assertEqual(foe.initiative_override,0)
        self.e.end_of_turn(foe);self.assertIsNone(foe.initiative_override)
    def test_fearsome_glare_real_miss_lowers_speed_without_paralysis(self):
        self.roughneck(R.DISPLAY,R.GAZE);foe=self.foe();self.combat(self.t);self.display();self.use(self.t,foe,'move/뱀눈초리',face=1)
        self.assertEqual(foe.stages['spe'],-2);self.assertNotIn('마비',foe.conditions);self.valid()
    def test_fearsome_glare_hit_adds_speed_loss_and_actual_paralysis(self):
        self.roughneck(R.DISPLAY,R.GAZE);foe=self.foe();self.combat(self.t);self.display();self.use(self.t,foe,'move/뱀눈초리')
        self.assertEqual(foe.stages['spe'],-2);self.assertIn('마비',foe.conditions)
    def test_mean_look_reuses_trapped_slowed_and_adds_suppression(self):
        self.roughneck(R.DISPLAY);self.p=self.foe();self.combat(self.t);self.display();self.use(self.t,self.p,'move/검은눈빛')
        self.assertTrue({'수렁','둔화','억압'}<=self.p.conditions);self.restore('t','p')
        self.e.end_scene(self.e.everyone);self.assertFalse({'수렁','둔화','억압'}&self.p.conditions)
    def test_slack_off_heals_native_half_and_one_selected_affliction_only(self):
        self.roughneck(R.DISPLAY,R.NAILS);self.e.gm.set_hp(self.t,100,reason='observed current HP')
        self.e.apply_status(self.t,'화상');self.e.apply_status(self.t,'독');before=self.t.hp
        self.combat(self.t);self.display({'status':'독'});self.use(self.t,self.t,'move/게으름피우기')
        self.assertEqual(self.t.hp,min(self.t.max_hp,before+self.t.max_hp//2));self.assertNotIn('독',self.t.conditions);self.assertIn('화상',self.t.conditions)
    def test_display_bad_status_selection_rolls_back_cost_and_heal(self):
        self.roughneck(R.DISPLAY,R.NAILS);self.combat(self.t);self.display({'status':'임시 체력'})
        self.rejected(lambda:self.use(self.t,self.t,'move/게으름피우기'),'Status Affliction')
    def test_mettle_actual_massive_hit_resists_once_and_reduces_used_attack_stat(self):
        self.roughneck(R.METTLE);foe=self.foe(power=250);self.combat(foe,count=15);self.answer('mettle',True)
        hp=self.t.hp;self.use(foe,self.t,'move/물대포',set_damage=True)
        self.assertEqual(foe.stages['spa'],-2);self.assertEqual(foe.stages['atk'],0)
        self.assertLess(hp-self.t.hp,self.t.base_max_hp//2);self.assertEqual(F.state(self.t)['activations'][R.METTLE]['used'],1)
        self.assertEqual(self.t._action_history,['free']);self.valid()
    def test_mettle_does_not_trigger_on_status_hp_loss_or_small_hit(self):
        self.roughneck(R.METTLE);foe=self.foe();self.combat(foe,count=15);self.answer('mettle',True)
        self.e.lose_hp(self.t,1,source='condition/독');self.use(foe,self.t,'move/몸통박치기')
        self.assertEqual(foe.stages['atk'],0);self.assertNotIn(R.METTLE,F.state(self.t)['activations'])
    def test_endure_requires_actual_trigger_not_a_prepared_global_shield(self):
        self.roughneck(R.NAILS);self.combat(self.t)
        self.rejected(lambda:self.use(self.t,self.t,'move/버티기'),'actual hit trigger')
        self.assertFalse(self.t.shield)
    def test_endure_native_lethal_hit_uses_daily_free_and_preserves_requested_receipt(self):
        self.roughneck(R.NAILS);foe=self.foe(power=500);self.combat(foe,count=15);self.answer('endure',True)
        self.use(foe,self.t,'move/몸통박치기',set_damage=True)
        self.assertEqual(self.t.hp,1);self.assertEqual(self.t.move_uses['move/버티기'],1)
        self.assertEqual(self.t._action_history,['free']);self.assertFalse(self.t.shield)
        import attack_damage_history as H
        receipt=H.last_damage(self.t)['receipt'];self.assertGreater(receipt['requested'],receipt['net_hp_loss'])
        self.valid()
    def test_endure_no_leak_to_later_poison_or_second_move(self):
        self.roughneck(R.NAILS);foe=self.foe(power=500);self.combat(foe,count=15);self.answer('endure',True)
        self.use(foe,self.t,'move/몸통박치기',set_damage=True);self.e.lose_hp(self.t,1,source='condition/독')
        self.assertEqual(self.t.hp,0)
    def test_endure_miss_does_not_consume_or_create_reaction(self):
        self.roughneck(R.NAILS);foe=self.foe(power=500);self.combat(foe,count=15);self.answer('endure',True)
        self.use(foe,self.t,'move/몸통박치기',face=1)
        self.assertNotIn('move/버티기',self.t.move_uses);self.assertEqual(self.t.hp,self.t.max_hp)
    def test_endure_codec_preserves_actual_completion_and_daily_use(self):
        self.roughneck(R.NAILS);self.p=self.foe(power=500);self.combat(self.p,count=15);self.answer('endure',True)
        self.use(self.p,self.t,'move/몸통박치기',set_damage=True);self.restore('t','p')
        self.assertEqual(self.t.hp,1);self.assertEqual(self.t.move_uses['move/버티기'],1);self.valid()
    def test_fearsome_endure_during_own_turn_aoo_grants_two_ticks_temporary_hp(self):
        self.roughneck(R.DISPLAY,R.NAILS);foe=self.foe();self.combat(self.t);self.answer('endure',True);self.display()
        before=self.t.hp;ap=AP.available(self.t)
        import turn
        with patch.object(Engine,'d20',return_value=10):turn.trigger_aoo(self.e,self.t,'native test provoking movement')
        self.assertEqual(self.t.hp,before);self.assertGreater(self.t.temp_hp,0)
        self.assertLessEqual(self.t.temp_hp,2*self.e.tick(self.t));self.assertEqual(AP.available(self.t),ap-2)
        self.assertEqual(self.t.move_uses['move/버티기'],1);self.assertEqual(self.t.budget['swift'],0);self.valid()
    def test_offturn_fearsome_swift_is_refused_without_partial_move_commit(self):
        self.roughneck(R.DISPLAY,R.NAILS);foe=self.foe(power=500);self.e.gm.set_move(foe,'move/몸통박치기',reason='known attack')
        self.combat(foe,count=15);self.answer('endure',True);self.display()
        self.rejected(lambda:self.use(foe,self.t,'move/몸통박치기',set_damage=True),'Swift Action')

    def test_roughneck_native_intercept_reduces_actual_recipient_not_nominal_target(self):
        import passive_events as P
        self.roughneck();foe=self.foe();reactor=self.add('enemy interceptor',(4,5),side='enemy')
        self.e.watch_move_defense(foe,[{'actor_id':reactor.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual Intercept declaration')
        self.combat(self.t);self.answer('roughneck_hit','atk')
        with self.assertRaises(P.PassiveEventPending):self.use(self.t,foe,'move/몸통박치기')
        event=self.e._passive_pending
        self.e.choose_move_defense(event,reactor,use=True,options={'path':[(4,5),(4,4),(4,3)],'skill':'육상','mode':'land','shove_destination':[5,3],'roll_options':{'fixed':[6]*6}},reason='actual defense choice')
        self.assertEqual(foe.stages['atk'],0);self.assertEqual(reactor.stages['atk'],-1);self.valid()
    def test_mettle_small_intercept_hit_still_triggers_scene_free_response(self):
        import passive_events as P
        self.roughneck(R.METTLE);foe=self.foe();ally=self.add('protected ally',(4,4))
        self.e.watch_move_defense(ally,[{'actor_id':self.t.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual Intercept declaration')
        self.combat(foe,count=15);self.answer('mettle',True)
        with self.assertRaises(P.PassiveEventPending):self.use(foe,ally,'move/몸통박치기')
        self.e.choose_move_defense(self.e._passive_pending,self.t,use=True,options={'path':[(3,3),(3,4),(4,4)],'skill':'육상','mode':'land','shove_destination':[5,4],'roll_options':{'fixed':[6]*6}},reason='actual defense choice')
        self.assertEqual(foe.stages['atk'],-2);self.assertEqual(ally.hp,ally.max_hp);self.valid()
    def test_fearsome_glare_shield_prevention_is_not_an_ordinary_miss(self):
        import passive_events as P,move_completion as COMPLETE
        self.roughneck(R.DISPLAY,R.GAZE);foe=self.foe()
        self.e.gm.set_move(foe,'move/판별',reason='actual learned Detect Interrupt')
        self.combat(self.t);self.display()
        self.e.watch_move_defense(foe,[{'actor_id':foe.entity_id,'source':'move/판별'}],reason='actual Glare hit Detect')
        with self.assertRaises(P.PassiveEventPending):self.use(self.t,foe,'move/뱀눈초리')
        self.e.choose_move_defense(self.e._passive_pending,foe,use=True,reason='actual Detect on successful Glare')
        result=COMPLETE.recipient_result(self.latest(self.t,'move/뱀눈초리'),foe)
        self.assertTrue(result['hit_prevented']);self.assertIsNone(foe.shield)
        self.assertEqual(foe.move_uses['move/판별'],1)
        self.assertEqual(foe.stages['spe'],0);self.assertNotIn('마비',foe.conditions);self.valid()

    def test_homebrew_endure_is_explicitly_selected_and_minus_quarter_exception_remains(self):
        old=self.rules
        self.rules=Rules(ROOT,ruleset='homebrew');self.addCleanup(setattr,self,'rules',old)
        self.setUp();self.roughneck(R.NAILS);foe=self.foe(power=600)
        self.assertEqual(self.rules.move_id('버티기'),'move/버티기-홈브류')
        self.combat(foe,count=15);self.answer('endure',True)
        self.use(foe,self.t,'move/몸통박치기',set_damage=True)
        self.assertLessEqual(self.t.hp,-(self.t.base_max_hp//4));self.assertEqual(self.t.move_uses['move/버티기-홈브류'],1)
    def test_endure_receives_native_counter_hp_loss_but_mettle_does_not(self):
        import combat_move_reactions as REACT
        self.roughneck(R.METTLE,R.NAILS);foe=self.foe()
        self.e.gm.set_move(foe,REACT.COUNTER,reason='actually learned Counter')
        self.e.gm.set_hp(self.t,5,reason='observed wounded trainer before the attack')
        self.combat(self.t);REACT.arm(self.e,foe,REACT.COUNTER)
        self.answer('endure',True);self.answer('mettle',True)
        self.use(self.t,foe,'move/몸통박치기',set_damage=True)
        self.assertEqual(self.t.hp,1);self.assertEqual(self.t.move_uses['move/버티기'],1)
        self.assertEqual(foe.move_uses[REACT.COUNTER],1)
        self.assertNotIn(R.METTLE,F.state(self.t)['activations']);self.valid()

    def test_maneuver_accuracy_hit_grants_roughneck_even_when_opposed_effect_loses(self):
        self.roughneck();foe=self.foe();self.combat(self.t);self.answer('roughneck_hit','def')
        self.assertFalse(self.terrorize(foe,won=False));self.assertEqual(foe.stages['def'],-1)
        self.assertFalse(any(r.get('manipulation')=='terrorize' for r in CLOCK.records(foe)))
    def test_direct_manipulate_effect_helper_is_not_a_menace_attack(self):
        self.roughneck(R.MENACE);foe=self.foe();self.combat(self.t);self.answer('roughneck_menace',True)
        import combat_maneuvers as M
        M._manipulate_outcome(self.e,self.t,foe,'terrorize',None,30)
        self.assertIsNone(foe.initiative_override);self.assertEqual(self.t.budget['swift'],1)

    def test_maneuver_choice_retry_keeps_actual_standard_accuracy_and_opposed_result(self):
        self.roughneck();foe=self.foe();self.combat(self.t);self.answer('roughneck_hit','hp')
        with self.assertRaisesRegex(ValueError,'Combat Stat'):self.terrorize(foe)
        self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.t.budget['swift'],1)
        event=self.e._precision_events[-1];before_rng=self.e.rng.getstate();before_ap=AP.available(self.t)
        self.answer('roughneck_hit','atk');R.resolve_maneuver(self.e,self.t,event['id'])
        self.assertEqual(foe.stages['atk'],-1);self.assertEqual(AP.available(self.t),before_ap-1)
        R.resolve_maneuver(self.e,self.t,event['id'])
        self.assertEqual(foe.stages['atk'],-1);self.assertEqual(self.e.rng.getstate(),before_rng)
    def test_grapple_native_automatic_struggle_hit_reuses_completed_relation(self):
        self.roughneck();foe=self.foe();self.combat(self.t)
        self.e.grapple(self.t,foe,challenger_skill='육상',defender_skill='육상',fixed_accuracy=20,
            challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
        self.next_turn(self.t);self.answer('roughneck_hit','spa')
        result=self.e.grapple_action(self.t,'attack')
        self.assertGreater(result['damage'],0);self.assertEqual(foe.stages['spa'],-1)
        import grapple_state as GRAPPLE
        record=GRAPPLE._state(self.e)['relations'][result['relation_id']]
        self.assertEqual(record['history'][-1]['roughneck']['stat'],'spa')
        self.assertEqual(self.t.budget['swift'],0);self.valid()

    def test_actual_enchanting_gaze_terrorize_effect_is_not_a_roughneck_or_menace_hit(self):
        import provocateur as P
        self.roughneck(R.MENACE)
        for feature in (P.CLASS,P.QUICK,P.GAZE):
            T.acquire_static(self.e,self.t,feature,acquisition_request_id='gaze/'+feature)
        foe=self.foe();self.combat(self.t);self.answer('roughneck_hit','atk');self.answer('roughneck_menace',True)
        ap=AP.available(self.t);self.e.enchanting_gaze(self.t,'terrorize',aim=(5,3))
        self.assertEqual(foe.stages['atk'],0);self.assertIsNone(foe.initiative_override)
        self.assertEqual(self.t.budget['swift'],1);self.assertEqual(AP.available(self.t),ap-2);self.valid()

    def test_endure_preserves_massive_injury_despite_only_four_actual_hp_loss(self):
        self.roughneck(R.NAILS);foe=self.foe(power=500)
        self.e.gm.set_hp(self.t,5,reason='actual current wounded HP');injuries=self.t.injuries
        self.combat(foe,count=15);self.answer('endure',True);self.use(foe,self.t,'move/몸통박치기',set_damage=True)
        self.assertEqual(self.t.hp,1);self.assertEqual(self.t.injuries,injuries+1)
        import attack_damage_history as H
        receipt=H.last_damage(self.t)['receipt'];self.assertEqual(receipt['net_hp_loss'],4)
        self.assertGreaterEqual(receipt['requested'],self.t.base_max_hp//2);self.valid()
    def test_mettle_and_endure_keep_distinct_damage_and_final_hp_owners(self):
        self.roughneck(R.METTLE,R.NAILS);foe=self.foe(power=500)
        self.e.gm.set_hp(self.t,5,reason='actual current wounded HP');self.combat(foe,count=15)
        self.answer('endure',True);self.answer('mettle',True);self.use(foe,self.t,'move/몸통박치기',set_damage=True)
        self.assertEqual(self.t.hp,1);self.assertEqual(foe.stages['atk'],-2)
        self.assertEqual(F.state(self.t)['activations'][R.METTLE]['used'],1)
        self.assertEqual(self.t.move_uses['move/버티기'],1);self.valid()

    def test_tough_as_nails_withdrawal_uses_three_retained_features_not_every_historical_member(self):
        import trainer_retraining as RET
        self.roughneck(*R.FEATURES[1:])
        def withdraw(feature):
            owned=RET._owned(self.t);sources={uid:RET.owned_source(self.e,self.t,uid) for uid in owned}
            requirements=RET._native_dependencies(self.e,self.t,owned)
            retained={sources[uid]:[sources[parent] for parent in requirements.get(uid,[])] for uid in owned if uid!=feature}
            retained[sources[R.NAILS]]=[sources[uid] for uid in (R.CLASS,R.MALICE,R.DISPLAY) if uid in owned and uid!=feature]
            return self.e.retrain_trainer_source(self.t,feature,request_id='retained-count/'+feature,reason='actual retraining',
                gm_decision={'allowed':True,'reason':'GM reviewed actual remaining prerequisites'},retained_dependencies=retained)
        for feature in (R.MENACE,R.METTLE,R.GAZE):withdraw(feature)
        self.assertIn('move/버티기',self.t.moves)
        self.rejected(lambda:withdraw(R.DISPLAY),'three actual Roughneck Features');self.valid()

    def test_supplied_hit_shape_cannot_authorize_roughneck_without_native_receipt(self):
        self.roughneck();foe=self.foe();self.combat(self.t);self.answer('roughneck_hit','atk')
        self.rejected(lambda:R.attack_hit(self.e,self.t,foe,origin={'kind':'maneuver','event_id':-1,'source':'maneuver/술수','hit':True}),'actual Roughneck native maneuver hit')

    def test_actual_core_inner_focus_blocks_menace_and_fearsome_headbutt_without_cancelling_hit(self):
        self.roughneck(R.MENACE,R.DISPLAY,R.GAZE)
        foe=self.add('Inner Focus',(4,3),side='enemy',speed=15,edges=['edge/기본-무술'],skills={'전투':6})
        T.acquire_martial_artist(self.e,foe,acquisition_request_id='focus/class',selected_ability='정신력',lifecycle_policy=T.LIFECYCLE_WHILE_OWNED)
        self.combat(self.t);self.answer('roughneck_menace',True);self.assertTrue(self.terrorize(foe))
        self.assertIsNone(foe.initiative_override)
        self.next_turn(self.t);self.display();self.use(self.t,foe,'move/박치기',face=20)
        self.assertIsNone(foe.initiative_override);self.assertNotIn('풀죽음',foe.conditions)
        self.assertTrue(self.latest(self.t)['results'][foe.entity_id]['hit']);self.valid()


    def second_roughneck(self,*features):
        self.b=self.add('second Roughneck',(3,4),speed=25,edges=[R.PRESENCE])
        for feature in (R.CLASS,*features):
            T.acquire_static(self.e,self.b,feature,acquisition_request_id='second/'+feature)
        return self.b
    def expire_overlap(self,field,first_value):
        self.restore('t','b','p')
        self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.t,initiative_count=30)
        self.assertEqual(field(),first_value);self.valid()
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.b,initiative_count=25)
        self.assertEqual(field(),0);self.valid()
    def test_menace_overlap_requires_exact_gm_ruling_and_preserves_independent_occurrences(self):
        import common_checks as C
        self.roughneck(R.MENACE);self.second_roughneck(R.MENACE);self.p=self.foe()
        self.combat(self.t);self.answer('roughneck_menace',True);self.terrorize(self.p,won=False)
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.b,initiative_count=25)
        before_ap=AP.available(self.b)
        pending=self.e.manipulate(self.b,self.p,'terrorize',defender_skill='집중',fixed_accuracy=20,
            challenger_options={'fixed':[1]*6},defender_options={'fixed':[6]*6})
        self.assertIsInstance(pending,C.PendingDecision);binding=pending.basis['binding']
        self.assertEqual(binding['source'],R.MENACE);self.assertEqual(len(binding['overlap_occurrences']),1)
        self.assertEqual(self.b.budget['standard'],0);self.assertEqual(self.b.budget['swift'],1)
        self.assertEqual(MOD.incoming_status_threshold(self.p,'풀죽음',15),11)
        event=binding['new_origin']['event_id'];before=self.e.export_state()
        again=R.resolve_maneuver(self.e,self.b,event)
        self.assertIsInstance(again,C.PendingDecision);self.assertEqual(before,self.e.export_state())
        bad=deepcopy(binding);bad['target_id']=self.t.entity_id
        self.answer('roughneck_overlap',{'binding':bad,'operator':'add','reason':'explicit but other target'})
        before=self.e.export_state();self.assertIsInstance(R.resolve_maneuver(self.e,self.b,event),C.PendingDecision)
        self.assertEqual(before,self.e.export_state())
        self.answer('roughneck_overlap',{'binding':binding,'operator':'add','reason':'GM resolves this exact simultaneous Menace pair additively'})
        rng=self.e.rng.getstate();R.resolve_maneuver(self.e,self.b,event)
        self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(AP.available(self.b),before_ap)
        self.assertEqual(self.b.budget['standard'],0);self.assertEqual(self.b.budget['swift'],0)
        self.assertEqual(MOD.incoming_status_threshold(self.p,'풀죽음',15),7)
        rows=[r for r in CLOCK.records(self.p) if 'incoming_status_range' in r]
        self.assertEqual(len({r['effect_occurrence'] for r in rows}),2)
        R.resolve_maneuver(self.e,self.b,event);self.assertEqual(MOD.incoming_status_threshold(self.p,'풀죽음',15),7)
        self.expire_overlap(lambda:MOD.incoming_derivation(self.p,'incoming_status_range',status='풀죽음')['value'],4)
    def test_fearsome_overlap_holds_before_move_costs_then_gm_maximum_survives_restore_and_expiry(self):
        import common_checks as C
        self.roughneck(R.DISPLAY);self.second_roughneck(R.MALICE,R.DISPLAY);self.p=self.foe()
        self.combat(self.t);self.display();self.use(self.t,self.p,'move/째려보기',aim=(5,3))
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.b,initiative_count=25)
        before=self.e.export_state();pending=self.use(self.b,self.p,'move/째려보기',aim=(5,3))
        self.assertIsInstance(pending,C.PendingDecision);self.assertEqual(before,self.e.export_state())
        binding=pending.basis['binding'];self.assertEqual(binding['source'],R.DISPLAY)
        self.answer('roughneck_overlap',True)
        self.rejected(lambda:self.use(self.b,self.p,'move/째려보기',aim=(5,3)),'source-bound')
        self.answer('roughneck_overlap',{'binding':binding,'operator':'maximum','reason':'GM chooses maximum for these exact simultaneous Leer contributions'})
        ap=AP.available(self.b);self.use(self.b,self.p,'move/째려보기',aim=(5,3))
        self.assertEqual(AP.available(self.b),ap-2);self.assertEqual(self.b.budget['swift'],0)
        self.assertEqual(MOD.incoming_critical_bonus(self.p),2)
        rows=[r for r in CLOCK.records(self.p) if 'incoming_critical_bonus' in r]
        self.assertEqual(len({r['effect_occurrence'] for r in rows}),2)
        self.assertTrue(any(r['kind']=='source_composition' and r['before']==binding for r in self.e.rulings.log))
        self.expire_overlap(lambda:MOD.incoming_critical_bonus(self.p),2)


    def test_four_native_maneuver_producers_feed_one_real_roughneck_hit(self):
        import items
        for name,source in [('disarm','maneuver/무장해제'),('dirty_trick','maneuver/치사한-짓'),('push','maneuver/밀기'),('trip','maneuver/걸기')]:
            with self.subTest(producer=name):
                self.setUp()
                self.t=self.add('actual maneuver trainer',(3,5),speed=30,skills={'전투':6},edges=[R.PRESENCE])
                target=self.add('actual maneuver foe',(4,5),side='enemy',speed=15,skills={'전투':6})
                self.roughneck();self.combat(self.t);self.answer('roughneck_hit','spd')
                options=dict(fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
                ap=AP.available(self.t)
                if name=='disarm':
                    items.register_item(self.e,target,'소형 방패')
                    self.e.disarm(self.t,target,attacker_skill='전투',defender_skill='전투',item_name='소형 방패',**options)
                    self.assertEqual(self.e.ground_items[-1]['item'],'소형 방패')
                elif name=='dirty_trick':
                    self.e.dirty_trick(self.t,target,'hinder',**options);self.assertIn('둔화',target.conditions)
                elif name=='push':
                    self.e.push(self.t,target,challenger_skill='육상',defender_skill='육상',**options);self.assertEqual(tuple(target.pos),(5,5))
                else:
                    self.e.trip(self.t,target,challenger_skill='곡예',defender_skill='곡예',**options);self.assertIn('넘어짐',target.conditions)
                event=self.e._precision_events[-1]
                self.assertEqual((event['source'],event['producer'],event['result']),(source,'combat_maneuver','accuracy_hit'))
                self.assertEqual(target.stages['spd'],-1);self.assertEqual(AP.available(self.t),ap-1)
                self.assertEqual(self.t.budget['standard'],0);self.assertEqual(self.t.budget['swift'],0)
                R.resolve_maneuver(self.e,self.t,event['id'])
                self.assertEqual(target.stages['spd'],-1);self.assertEqual(AP.available(self.t),ap-1);self.valid()


    def test_dodge_printed_miss_keeps_jump_kick_crash_distinct_from_detect_cancellation(self):
        import passive_events as P,move_completion as COMPLETE
        self.roughneck();foe=self.foe(abilities=['회피'])
        self.combat(self.t);self.answer('roughneck_hit','atk')
        self.e.watch_move_defense(foe,[{'actor_id':foe.entity_id,'source':'ability/회피'}],reason='actual Dodge damaging hit')
        before=self.t.hp
        with self.assertRaises(P.PassiveEventPending):self.use(self.t,foe,'move/점프킥')
        self.e.choose_move_defense(self.e._passive_pending,foe,use=True,reason='Dodge makes the Move miss')
        result=COMPLETE.recipient_result(self.latest(self.t,'move/점프킥'),foe)
        self.assertFalse(result['hit']);self.assertFalse(result['hit_prevented'])
        self.assertLess(self.t.hp,before);self.assertEqual(foe.hp,foe.max_hp)
        self.assertEqual(foe.stages['atk'],0);self.assertEqual(self.t.budget['swift'],1);self.valid()

if __name__=='__main__':unittest.main()
