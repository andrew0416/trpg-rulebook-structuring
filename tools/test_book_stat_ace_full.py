"""Book Stat Ace: acquired branches reach actual native resources and consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,random,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from rulings import Rulings
from builder import build_pokemon
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import stat_ace as S,trainer_feature_acquisition as A,acquired_features as ACQUIRED
import state_grants as G,state_fields as SF,state_codec as CODEC,world_entities as WORLD
import action_points as AP,frequency as F,turn as TURN,weapon_actions as WEAPONS
import combat_stage_sources as CS,combat_timing as TIME,combat_precision_features as CPF


class StatAceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    def setUp(self):
        old=self.rules.rulings;self.rules.rulings=deepcopy(old)
        self.addCleanup(setattr,self.rules,'rulings',old)
        self.setup()
    def setup(self,prerequisite=None,recipient_kind='pokemon'):
        self.e=Engine(self.rules,seed=779);self.e.grid=Grid(14,12)
        common=dict(level=20,size='중형',stats={'hp':100,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},
            moves=['move/몸통박치기','move/물대포','move/전광석화','move/화염방사','move/회오리','move/불꽃세례'],
            abilities=[],types=['노말'],movement={'land':6,'swim':0,'sky':0,'power':4},weight_kg=30,
            skills={'명령':6,'집중':6,'전투':4,'육상':4,'곡예':4,'은신':4})
        self.a=Combatant(self.rules,dict(deepcopy(common),name='actual stat owner',kind='trainer',
            classes=[] if prerequisite is None else [prerequisite[0]],feats=[],exp_bank=50,
            feature_choices={} if prerequisite is None or prerequisite[1] is None else {prerequisite[0]:[prerequisite[1]]}))
        self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual trainer')
        owned=[]
        for n,pos in enumerate(((4,4),(1,0),(1,1))):
            p=Combatant(self.rules,dict(deepcopy(common),name='owned stat partner '+str(n),kind='pokemon',trainer_id=self.a.entity_id))
            self.e.gm.add_combatant(p,pos=pos,side='party',reason='actual distinct owned Pokemon');owned.append(p)
        self.p,self.q,self.r=owned
        self.foes=[]
        for n,pos in enumerate(((5,4),(4,5),(3,4))):
            p=Combatant(self.rules,dict(deepcopy(common),name='actual recipient '+str(n),kind=recipient_kind))
            self.e.gm.add_combatant(p,pos=pos,side='foe',reason='actual distinct native recipient');self.foes.append(p)
        self.b=self.foes[0]
        for c in self.e.everyone:
            prepare_body(self.e,c,size='중형',offsets=[(0,0)],reason='observed complete body')
        for p in owned:self.e.gm.observe_loyalty(p,6,reason='actual willing partner')
    def acquire(self,feature=S.CLASS,branch='atk'):
        return A.acquire_static(self.e,self.a,feature,branch=branch,acquisition_request_id='stat/'+feature+'/'+branch)
    def family(self,branch,*,link=False,training=False,maneuver=False,mastery=False,stratagem=False,embodiment=False):
        self.acquire(branch=branch)
        for feature,wanted in ((S.LINK,link or stratagem or embodiment),(S.TRAINING,training or stratagem or embodiment),
            (S.MANEUVER,maneuver or mastery or embodiment),(S.MASTERY,mastery),(S.STRATAGEM,stratagem),(S.EMBODIMENT,embodiment)):
            if wanted:self.acquire(feature,branch)
    def answer(self,key,value):
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!=key]
        self.e.rulings.add_answer(key,value,reason='explicit actual player choice',scope='permanent')
    def combat(self,c):self.e.start_round(self.e.everyone);self.e.start_of_turn(c,initiative_count=30)
    def attack(self,c=None,t=None,mid='move/몸통박치기',face=10):
        with patch.object(Engine,'d20',return_value=face):return self.e.use_move_on(c or self.p,t or self.b,mid,self.e.everyone,set_damage=True)
    def rejected(self,fn,pattern=None):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
    def restore(self):
        ids=[c.entity_id for c in (self.a,self.p,self.q,self.r,*self.foes)]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        actors=WORLD.actor_index(self.e);self.a,self.p,self.q,self.r,*self.foes=[actors[uid] for uid in ids];self.b=self.foes[0]
    def activate(self,branch):
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual Order communication')
        self.combat(self.a);return S.activate(self.e,self.a,self.p,branch)

    def test_actual_acquisition_template_prerequisites_branch_slots_and_historical_observation(self):
        self.assertEqual(set(S.DEFINITIONS),set(S.FEATURES));self.assertEqual(S.DEFINITIONS[S.CLASS]['choices'],S.STATS)
        self.rejected(lambda:self.acquire(S.MASTERY),'prerequisite')
        SF.base_patch(self.a,{'skills':{'명령':2,'집중':2}},reason='actual below Novice skill')
        self.rejected(self.acquire,'rank');SF.base_patch(self.a,{'skills':{'명령':6,'집중':6}},reason='actual qualified Master')
        base=dict(self.p.spec['stats']);receipt=self.acquire();self.assertEqual(receipt['source']['span'],[1097,1099])
        self.assertEqual(self.p.stats['atk'],base['atk']+3);self.assertEqual(self.p.stats['def'],base['def'])
        self.assertFalse(S.has(self.e,self.p,S.MASTERY,'atk'));self.assertEqual(self.acquire(),receipt)
        for branch in ('def','spa','spd'):self.acquire(branch=branch)
        self.assertEqual(len(ACQUIRED.class_instances(self.a)),4)
        self.rejected(lambda:self.acquire(branch='spe'),'four|4|class')
        SF.base_patch(self.a,{'skills':{'명령':2,'집중':2}},reason='later rank preserves actual historical qualification')
        self.restore();self.valid()

    def test_class_qualification_counts_distinct_owned_pokemon_and_rejects_wrong_branch(self):
        for p in (self.q,self.r):SF.base_patch(p,{'stats':dict(p.spec['stats'],atk=19)},reason='actual lower Attack')
        self.rejected(self.acquire,'three stat20')
        self.rejected(lambda:self.acquire(branch='hp'),'branch')
        self.rejected(lambda:self.acquire(S.LINK,'def'),'prerequisite')

    def test_alternative_ace_or_matching_style_initial_source_and_one_actual_fifteen_pokemon(self):
        for prerequisite,branch in ((('class/에이스-트레이너',None),'atk'),(('class/스타일-전문가','아름다움'),'spa')):
            self.setup(prerequisite)
            for p in (self.p,self.q,self.r):
                stats=dict(p.spec['stats']);stats.update({st:15 if p is self.p else 10 for st in S.STATS})
                SF.base_patch(p,{'stats':stats},reason='actual prerequisite route current observed Stats')
            if branch=='spa':self.rejected(lambda:self.acquire(branch='atk'),'three stat20')
            self.acquire(branch=branch);self.assertEqual(len(ACQUIRED.class_instances(self.a)),2)
            self.assertEqual(self.p.stats[branch],18);self.assertFalse(S.records(self.a,S.LINK,True));self.valid()

    def test_all_five_class_modifiers_follow_actual_level_without_duplicate_projection(self):
        for branch in S.STATS:
            with self.subTest(branch=branch):
                if branch!='atk':self.setup()
                self.family(branch);base=self.p.spec['stats'][branch]
                self.e.register_abilities(self.a);self.e.register_abilities(self.a)
                self.assertEqual(self.p.stats[branch],base+3)
                self.e.gm.set_level(self.p,30,reason='actual level observation')
                self.assertEqual(self.p.stats[branch],base+4);self.valid()

    def test_link_actual_end_turn_optional_ap_and_real_nonzero_base_combat_stage(self):
        self.family('atk',link=True);self.answer('stat_link',True)
        self.p.spec['items']={'힘의가루':3}
        self.e.use_item(self.p,'힘의가루');self.e.use_item(self.p,'힘의가루')
        for seed in range(1000):
            if random.Random(seed).randint(1,6)==1:self.e.rng.seed(seed);break
        self.e.use_item(self.p,'힘의가루');self.assertEqual(CS.total(CS.validate(self.p),'atk'),-1)
        self.combat(self.p);before=AP.available(self.a);self.e.end_of_turn(self.p)
        self.assertEqual(self.p.stages['atk'],0);self.assertEqual(AP.available(self.a),before-1)
        self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=30);self.e.end_of_turn(self.p)
        self.assertEqual(self.p.stages['atk'],0);self.assertEqual(AP.available(self.a),before-1)
        self.restore();self.valid()

    def test_link_invalid_choice_rolls_back_native_turn_and_cost(self):
        self.family('atk',link=True);self.answer('stat_link','invalid');self.combat(self.p)
        self.rejected(lambda:self.e.end_of_turn(self.p),'boolean')
        self.answer('stat_link',False);before=AP.available(self.a);self.e.end_of_turn(self.p)
        self.assertEqual(AP.available(self.a),before);self.assertEqual(self.p.stages['atk'],0)

    def teaching_target(self):
        p=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':2}))
        self.e.gm.add_combatant(p,pos=(8,8),side='party',reason='actual species and current Tutor Point balance')
        prepare_body(self.e,p,size=p.spec['size'],offsets=[(0,0)],reason='observed actual learner body')
        self.e.gm.observe_loyalty(p,6,reason='actual willing learner');return p
    def test_training_all_five_branches_two_moves_tp_actual_activity_and_existing_learning_ledger(self):
        import move_state as M,trainer_retraining as RETRAIN
        for branch in S.STATS:
            with self.subTest(branch=branch):
                if branch!='atk':self.setup()
                self.family(branch,training=True);p=self.teaching_target();before=self.e.elapsed_seconds
                for mid in S.MOVES[branch]:
                    row=S.teach(self.e,self.a,p,branch,mid,seconds=60,reason='actual completed chosen Stat Training')
                    self.assertEqual(row['point_cost'],1);self.assertIn(mid,M.known(self.rules,p.spec))
                self.assertEqual(p.spec['tutor_points'],0);self.assertEqual(self.e.elapsed_seconds,before+120)
                M.validate_spec(self.rules,p.spec,require_routes=True)
                sid=RETRAIN.owned_source(self.e,self.a,S.TRAINING)
                self.assertTrue(G.state(self.a)['sources'][sid]['irreversible_uses']);self.valid()
                self.rejected(lambda:S.teach(self.e,self.a,p,branch,S.MOVES[branch][0],seconds=60,reason='no remaining TP'),'Tutor Point')

    def test_training_wrong_owner_wrong_move_and_late_native_failure_are_atomic(self):
        self.family('atk',training=True);p=self.teaching_target()
        self.rejected(lambda:S.teach(self.e,self.a,self.b,'atk',S.MOVES['atk'][0],seconds=60,reason='foreign'),'own|trainer')
        self.rejected(lambda:S.teach(self.e,self.a,p,'atk',S.MOVES['spe'][0],seconds=60,reason='wrong Move'),'outside')
        import activity_jobs as JOBS
        with patch.object(JOBS,'run_fixed',side_effect=ValueError('late actual activity failure')):
            self.rejected(lambda:S.teach(self.e,self.a,p,'atk',S.MOVES['atk'][0],seconds=60,reason='actual attempt'),'late actual')

    def test_maneuver_attack_three_actual_recipients_pay_one_move_and_one_branch_frequency(self):
        self.family('atk',maneuver=True);self.combat(self.p);before=[p.hp for p in self.foes]
        with patch.object(Engine,'d20',return_value=20):
            S.maneuver(self.e,self.a,self.p,self.b,'move/몸통박치기',branch='atk',option='three',targets=self.foes,set_damage=True)
        self.assertTrue(all(p.hp<hp for p,hp in zip(self.foes,before)))
        self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(len(self.a.spec['stat_maneuver_uses']),1)
        self.rejected(lambda:S.maneuver(self.e,self.a,self.q,self.b,'move/몸통박치기',branch='atk',option='three',targets=[self.b]),'frequency')
        self.restore();self.valid()

    def test_maneuver_attack_invalid_selection_and_late_move_error_leave_no_paid_receipt(self):
        self.family('atk',maneuver=True);self.combat(self.p)
        self.rejected(lambda:S.maneuver(self.e,self.a,self.p,self.b,'move/몸통박치기',branch='atk',option='three',targets=[self.b,self.b]),'distinct')
        with patch.object(Engine,'use_move_on',side_effect=ValueError('late actual Move failure')):
            self.rejected(lambda:S.maneuver(self.e,self.a,self.p,self.b,'move/몸통박치기',branch='atk',option='three',targets=[self.b]),'late actual')
        self.assertFalse(self.a.spec.get('stat_maneuver_uses'))

    def test_maneuver_attack_pass_actual_movement_target_and_native_receipt_restore(self):
        self.family('atk',maneuver=True);self.b.pos=(5,4);self.foes[1].pos=(10,10);self.foes[2].pos=(11,10)
        self.combat(self.p);hp=self.b.hp
        with patch.object(Engine,'d20',return_value=20):
            result=S.maneuver(self.e,self.a,self.p,self.b,'move/몸통박치기',branch='atk',option='pass',destination=(7,4),event_id='stat/pass')
        self.assertEqual(self.p.pos,(7,4));self.assertLess(self.b.hp,hp)
        self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(self.p.budget['shift'],0)
        self.assertEqual(result['distance'],3);self.restore();self.valid()

    def test_maneuver_three_targets_actual_passive_wait_restore_keeps_paid_geometry_and_remaining_recipients(self):
        import passive_events as PASSIVE
        self.family('atk',maneuver=True)
        G.set_baseline(self.b,'abilities',['테라셸'])
        self.e.register_abilities(self.b);self.e.watch_ability_interrupt(self.b,'ability/테라셸',reason='actual target choice')
        self.combat(self.p);before=[p.hp for p in self.foes]
        with patch.object(Engine,'d20',return_value=20):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                S.maneuver(self.e,self.a,self.p,self.b,'move/몸통박치기',branch='atk',option='three',targets=self.foes,set_damage=True)
        event=self.e._passive_pending;self.assertEqual(self.p.move_uses['move/몸통박치기'],1)
        self.assertEqual(len(self.a.spec['stat_maneuver_uses']),1);self.restore()
        with patch.object(Engine,'d20',return_value=20):
            self.e.choose_ability_interrupt(event,self.b,use=True,options={'chosen_type':'강철'},reason='actual native target choice')
        self.assertIsNone(self.e._passive_pending);self.assertTrue(all(p.hp<hp for p,hp in zip(self.foes,before)))
        self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(len(self.a.spec['stat_maneuver_uses']),1);self.valid()

    def test_maneuver_special_attack_all_four_real_geometries_and_no_persistent_range_mutation(self):
        for option,aim in (('burst',(4,4)),('cone',(5,4)),('close_blast',(5,4)),('line',(5,4))):
            with self.subTest(option=option):
                if option!='burst':self.setup()
                self.family('spa',maneuver=True);self.combat(self.p);hp=self.b.hp
                original=WEAPONS.range_spec(self.e,self.rules.move('move/회오리'),self.p)
                with patch.object(Engine,'d20',return_value=20):
                    S.maneuver(self.e,self.a,self.p,self.b,'move/회오리',branch='spa',option=option,aim=aim,set_damage=True)
                self.assertLess(self.b.hp,hp);self.assertEqual(self.p.move_uses['move/회오리'],1)
                self.assertEqual(WEAPONS.range_spec(self.e,self.rules.move('move/회오리'),self.p),original)
                self.assertFalse(hasattr(self.e,'_stat_maneuver_scope'));self.valid()

    def test_defensive_maneuvers_actual_hits_only_use_six_stages_once_and_preserve_current_stages(self):
        for branch,mid in (('def','move/몸통박치기'),('spd','move/물대포')):
            with self.subTest(branch=branch):
                if branch!='def':self.setup()
                self.family(branch,maneuver=True);self.answer('stat_maneuver_defense',True)
                self.e.change_stage(self.p,branch,-2);self.e.change_stage(self.q,branch,-2)
                self.combat(self.b);move=self.rules.move(mid);preview=self.e.roll_damage(self.b,self.p,move,set_damage=True)
                self.assertFalse(self.a.spec.get('stat_maneuver_uses'))
                damage=self.attack(self.b,self.p,mid);self.assertLess(damage,preview)
                self.assertEqual(self.p.stages[branch],-2);self.assertEqual(len(self.a.spec['stat_maneuver_uses']),1)
                self.valid()

    def test_speed_maneuver_native_priority_and_advanced_priority_whole_turn_payment(self):
        import priority_actions as P
        for mid in ('move/물대포','move/전광석화'):
            with self.subTest(mid=mid):
                if mid!='move/물대포':self.setup()
                self.family('spe',maneuver=True)
                for actor,speed in zip(self.e.everyone,(70,60,50,40,30,20,10)):
                    SF.base_patch(actor,{'stats':dict(actor.spec['stats'],spe=speed)},reason='actual observed distinct initiative speeds')
                self.e.prepare_initiative_schedule(self.e.everyone,source='gm/actual-stat-schedule')
                self.e.start_round(self.e.everyone)
                with patch.object(Engine,'d20',return_value=20):
                    result=S.maneuver(self.e,self.a,self.p,self.b,mid,branch='spe',option='priority')
                self.assertEqual(result['source'],S.MANEUVER);self.assertIs(self.e._active_turn_actor,self.p)
                self.assertEqual(self.p.move_uses[mid],1);self.assertEqual(self.p.budget,{'standard':0,'shift':1,'swift':1})
                self.assertTrue(TURN.spend(self.e,self.p,'swift'));self.e.finish_initiative_reaction()
                self.restore();self.valid()

    def test_attack_mastery_successful_push_real_tick_and_failed_opposed_no_tick(self):
        for won in (True,False):
            if not won:self.setup()
            self.family('atk',mastery=True);self.foes[1].pos=(10,10);self.foes[2].pos=(11,10);self.combat(self.p);hp=self.b.hp
            result=self.e.push(self.p,self.b,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
                challenger_options={'fixed':[6 if won else 1]*4},defender_options={'fixed':[2]*4})
            self.assertEqual(self.b.hp,hp-(self.e.tick(self.b) if won else 0));self.assertEqual(bool(result),won);self.valid()

    def test_attack_mastery_native_disarm_and_dirty_trick_each_lose_one_tick(self):
        for kind in ('disarm','dirty'):
            self.setup(recipient_kind='trainer')
            self.family('atk',mastery=True);self.foes[1].pos=(10,10);self.foes[2].pos=(11,10)
            TURN.equip_weapon(self.e,self.b,{'name':'검','kind':'소형 근접무기','grade':'조잡'})
            self.combat(self.p);before=self.b.hp
            options={'fixed_accuracy':20,'challenger_options':{'fixed':[6]*4},'defender_options':{'fixed':[1]*4}}
            result=(self.e.disarm(self.p,self.b,attacker_skill='전투',defender_skill='은신',**options) if kind=='disarm'
                else self.e.dirty_trick(self.p,self.b,'blind',**options))
            self.assertTrue(result);self.assertEqual(self.b.hp,before-self.e.tick(self.b));self.valid()

    def test_defense_mastery_native_shift_decision_dr_and_full_round_initiative_expiry(self):
        self.family('def',mastery=True);self.combat(self.p)
        move=self.rules.move('move/물대포');control=self.e.roll_damage(self.b,self.p,move,set_damage=True)
        bypass={mid:self.e.roll_damage(self.b,self.p,self.rules.move(mid),set_damage=True) for mid in ('move/풀베기','move/dd래리어트')}
        self.e.end_of_turn(self.p);self.assertEqual(self.e.roll_damage(self.b,self.p,move,set_damage=True),max(1,control-5))
        for mid,baseline in bypass.items():self.assertEqual(self.e.roll_damage(self.b,self.p,self.rules.move(mid),set_damage=True),baseline)
        SF.base_patch(self.p,{'weight_class':3},reason='actual observed Weight Class for typeless Physical fall')
        hp=self.p.hp
        fall=self.e.falling_damage(self.p,action_id='actual-stat-def-fall',meters=3,intentional=False,
            reason='actual observed rough cliff fall',fixed_damage=[3,3],surface_dice='3d6',fixed_surface=[6,6,6],
            surface_reason='observed sharp landing surface',natural_sky=False,natural_sky_reason='actual species baseline has no Sky')
        self.assertEqual(fall['damage_reduction'],5);self.assertEqual(self.p.hp,hp-fall['damage'])
        self.assertEqual(fall['damage'],max(1,fall['raw_damage']-fall['defense']-5))
        self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(31)
        self.assertEqual(S.damage_reduction(self.e,self.p),5)
        self.e.at_initiative_count(30);self.assertEqual(S.damage_reduction(self.e,self.p),0)
        self.e.start_of_turn(self.p,initiative_count=30);self.assertTrue(self.e.disengage(self.p,(4,3)))
        self.e.end_of_turn(self.p);self.assertEqual(S.damage_reduction(self.e,self.p),0);self.valid()
        # Withdrawal of the actual acquisition disables an otherwise live marker.
        import trainer_retraining as RETRAIN
        self.setup();self.family('def',mastery=True);self.combat(self.p);self.e.end_of_turn(self.p)
        sources={uid:RETRAIN.owned_source(self.e,self.a,uid) for uid in (S.CLASS,S.MANEUVER,S.MASTERY)}
        RETRAIN.retrain(self.e,self.a,S.MASTERY,request_id='actual-def-mastery-withdrawal',reason='actual consultation',
            gm_decision={'allowed':True,'reason':'approved retraining'},
            retained_dependencies={sources[S.CLASS]:[],sources[S.MANEUVER]:[sources[S.CLASS]]})
        self.assertEqual(S.damage_reduction(self.e,self.p),0);self.restore();self.valid()

    def test_special_attack_mastery_native_origin_bonus_once_keeps_area_size(self):
        self.family('spa',mastery=True)
        for mid in ('move/물대포','move/화염방사','move/회오리'):
            base=WEAPONS.range_spec(self.e,self.rules.move(mid),self.b)
            actual=WEAPONS.range_spec(self.e,self.rules.move(mid),self.p)
            self.assertEqual(actual['size'] if 'size' in actual else None,base.get('size'))
            if type(base['origin']) is int:self.assertEqual(actual['origin'],base['origin']+2)
        self.restore();self.valid()

    def test_special_defense_mastery_explicit_one_two_ticks_minimum_percent_and_healing_distinction(self):
        import confusion_attacks as CONF,status_sets as STATUS,condition_recovery as REC
        self.family('spd',mastery=True);unit=max(1,self.e.tick(self.p)-5)
        self.assertEqual(self.e.tick_loss(self.p,2),unit*2)
        self.assertEqual(CONF.amount(self.e,self.p,'변화'),unit*2)
        little=self.teaching_target();hp=little.hp;self.assertLessEqual(self.e.tick(little),6)
        self.e.lose_tick_hp(little,source='condition/저주');self.assertEqual(little.hp,hp-1)
        before=self.p.hp;self.e.lose_tick_hp(self.p,2,source='condition/저주');self.assertEqual(self.p.hp,before-unit*2)
        before=self.p.hp;self.e.lose_hp(self.p,self.e.tick(self.p),source='actual fixed percentage');self.assertEqual(self.p.hp,before-self.e.tick(self.p))
        self.e.apply_status(self.p,'잠듦');self.e.apply_status(self.p,'악몽');before=self.p.hp
        REC.saving_check(self.e,self.p,'잠듦',16,fixed=1);self.assertEqual(self.p.hp,before-unit*2)
        healed=self.e.heal(self.p,self.e.tick(self.p),source_kind='feature');self.assertEqual(healed,self.e.tick(self.p))
        self.valid()

    def test_speed_mastery_actual_swift_disengage_preserves_shift_and_avoids_aoo(self):
        self.family('spe',mastery=True);self.combat(self.p)
        with patch.object(TURN,'trigger_aoo',wraps=TURN.trigger_aoo) as aoo:self.assertTrue(self.e.disengage(self.p,(4,3)))
        aoo.assert_not_called();self.assertEqual(self.p.budget,{'standard':1,'shift':1,'swift':0});self.valid()

    def test_embodiment_acquired_four_features_two_branches_existing_scene_owner_ap_and_restore(self):
        import scene_feature_ability_grants as SCENE
        self.family('atk',embodiment=True);self.family('def',embodiment=True)
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual feature communication')
        self.e.start_round(self.e.everyone);before=AP.available(self.a)
        self.e.activate_scene_feature_ability(self.a,self.p,S.EMBODIMENT,'atk','오기')
        self.assertEqual(AP.available(self.a),before-1);self.assertEqual(len(SCENE.records(self.p)),1)
        self.restore();self.valid();self.e.start_of_turn(self.a,initiative_count=30);self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
        self.assertEqual(len(SCENE.records(self.p)),1);self.e.end_scene();self.assertEqual(SCENE.records(self.p),())

    def test_stratagem_attack_actual_order_bound_ap_current_critical_cap_and_release(self):
        import class_passive_combat as CP
        self.family('atk',stratagem=True);before=AP.available(self.a);self.assertEqual(self.activate('atk'),(1,0))
        self.assertEqual(AP.available(self.a),before-2);self.assertEqual(self.a.budget['standard'],0)
        melee=self.rules.move('move/몸통박치기');ranged=self.rules.move('move/물대포')
        for stage in (-2,0,1,2,3,6):
            self.e.change_stage(self.p,'atk',stage-self.p.stages['atk'])
            self.assertEqual(self.e.accuracy_check(self.p,self.b,melee,fixed_roll=17)[2],stage>=3)
            self.assertFalse(self.e.accuracy_check(self.p,self.b,ranged,fixed_roll=17)[2])
        self.restore();self.valid();self.e.release_class_passive(self.a,self.p,S.STRATAGEM)
        self.assertFalse(CP._state(self.p)['sustains']);self.assertEqual(AP.available(self.a),before)

    def test_stratagem_special_attack_effect_range_dynamic_distinct_from_natural_or_range(self):
        self.family('spa',stratagem=True);self.activate('spa');move=self.rules.move('move/물대포')
        for stage in (-2,0,1,2,3,6):
            self.e.change_stage(self.p,'spa',stage-self.p.stages['spa'])
            self.assertEqual(CPF.effect_natural(self.e,self.p,move,10),10+max(0,min(stage,3)))
        self.assertFalse(self.e.accuracy_check(self.p,self.b,move,fixed_roll=17)[2]);self.restore();self.valid()

    def test_stratagem_both_defensive_save_families_reach_actual_saving_check(self):
        import condition_recovery as REC
        for branch,conditions in (('def',('마비','잠듦','얼음')),('spd',('혼란','난동','헤롱헤롱'))):
            if branch!='def':self.setup()
            self.family(branch,stratagem=True);self.activate(branch)
            for stage in (-2,0,1,2,3,6):
                self.e.change_stage(self.p,branch,stage-self.p.stages[branch])
                for condition in conditions:
                    result=REC.saving_check(self.e,self.p,condition,16,fixed=10)
                    self.assertEqual(result['dc'],16-2*max(0,min(stage,3)))
            self.assertEqual(REC.saving_check(self.e,self.p,'독',16,fixed=10)['dc'],16);self.valid()

    def test_stratagem_speed_existing_positive_modes_only_and_encounter_lifetime(self):
        import movement_actions as MOVE,class_passive_combat as CP
        self.family('spe',stratagem=True);self.activate('spe')
        base=MOVE.capabilities(self.e,self.p,environment=False)['land']
        self.e.change_stage(self.p,'spe',3);actual=MOVE.capabilities(self.e,self.p,environment=False)
        # Combat Stage movement is already native; this is its additional Stratagem contribution.
        self.assertEqual(S.stratagem_bonus(self.e,self.p,'movement'),3);self.assertEqual(actual['swim'],0)
        self.e.release_class_passive(self.a,self.p,S.STRATAGEM)
        self.assertEqual(MOVE.capabilities(self.e,self.p,environment=False)['land'],actual['land']-3)
        self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=30)
        S.activate(self.e,self.a,self.p,'spe');self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone)
        self.assertFalse(CP._state(self.p)['sustains']);self.assertFalse(self.a.spec['ap_bound']);self.valid()

    def test_stratagem_single_occupancy_late_failure_and_branch_provenance_tamper(self):
        import class_passive_combat as CP
        self.family('atk',stratagem=True);self.family('def',stratagem=True);self.activate('atk')
        self.rejected(lambda:S.activate(self.e,self.a,self.p,'def'),'Stratagem|stratagem')
        self.restore();row=CP._state(self.p)['sustains'][S.STRATAGEM];row['acquisition_source']='forged'
        self.assertFalse(self.e.validate_state()['valid'])

    def test_single_branch_retraining_releases_live_binding_and_retires_real_branch_receipt(self):
        import trainer_retraining as R
        self.family('atk',stratagem=True);self.activate('atk')
        sources={uid:R.owned_source(self.e,self.a,uid) for uid in (S.CLASS,S.LINK,S.TRAINING,S.STRATAGEM)}
        dependencies={sources[S.CLASS]:[],sources[S.LINK]:[sources[S.CLASS]],sources[S.TRAINING]:[sources[S.CLASS]]}
        result=R.retrain(self.e,self.a,S.STRATAGEM,request_id='actual-stat-retrain',reason='actual consultation',
            gm_decision={'allowed':True,'reason':'approved story retraining'},retained_dependencies=dependencies)
        self.assertEqual(result['source_id'],sources[S.STRATAGEM]);self.assertIsNone(S.acquired(self.a,S.STRATAGEM,'atk'))
        self.assertFalse(self.a.spec['ap_bound']);self.restore();self.valid()

    def test_chosen_investment_native_levelup_forms_and_retained_nature_without_permanent_waiver(self):
        import growth_stats as GS,downtime as D
        for forms in (False,True):
            if forms:self.setup()
            self.family('atk');p=Combatant(self.rules,build_pokemon(self.rules,'잉어킹',5,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
            base=deepcopy(p.spec['initial_allocation']['species_base']);hi=min((k for k in base if base[k]>base['atk']),key=base.get)
            investment=dict.fromkeys(base,0);investment['atk']=base[hi]-base['atk']-1;investment[max(base,key=base.get)]+=15-investment['atk']
            plan=GS.compose(base,investment,points=15,rules=self.rules);spec=deepcopy(p.spec);spec.update(stats=plan['stats'],initial_allocation=plan)
            p=Combatant(self.rules,spec);self.e.gm.add_combatant(p,pos=(9,8),side='party',reason='actual explicitly allocated learner')
            if forms:
                declaration={'species_base':base,'investment':investment}
                self.e.configure_growth_forms(p,{'normal':declaration,'alternate':deepcopy(declaration)},active='normal',source='combat/struggle')
            D.gain_exp_combatant(self.e,p,'to next level',stat_choices={6:'atk'})
            self.assertEqual(p.level,6);self.assertNotIn('stat_relation_exempt',p.spec)
            before=GS.project_actor(self.e,p)['permanent']['investment']
            proposal=self.e.plan_growth_nature(p,p.spec.get('nature'))
            self.assertEqual(proposal['allocation']['investment'],before);self.valid()


if __name__=='__main__':unittest.main()
