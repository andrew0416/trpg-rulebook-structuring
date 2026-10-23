"""Native Taskmaster training, current injury consumers and optional reactions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from builder import build_pokemon
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import taskmaster as T,training_features as F,trainer_feature_acquisition as A
import state_codec as CODEC,world_entities as W,action_points as AP
import combat_precision_features as CPF,injury_recovery as INJURY,turn as TURN
import state_fields as SF,frequency as FREQUENCY,state_grants as G


class TaskmasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setup(self,*,acquire=True,press=False,pain=False):
        self.e=Engine(self.rules,seed=61231);self.e.grid=Grid(8,8)
        common=dict(level=20,stats={'hp':60,'atk':10,'def':5,'spa':10,'spd':5,'spe':10},
            moves=['move/독침','move/물대포','move/대폭발','move/버티기','move/아픔나누기','move/자폭'],
            abilities=[],movement={'land':6,'swim':0,'sky':0},size='중형')
        self.a=Combatant(self.rules,dict(deepcopy(common),name='actual taskmaster',kind='trainer',
            skills={'협박':6,'명령':6,'육상':3},feats=[F.BRUTAL],classes=[],exp_bank=30))
        self.e.gm.add_combatant(self.a,pos=(0,1),side='party',reason='actual trainer')
        self.p=Combatant(self.rules,dict(deepcopy(common),name='trained partner',kind='pokemon',
            trainer_id=self.a.entity_id,trainer=self.a.name,skills={'육상':'2d6'}))
        self.q=Combatant(self.rules,dict(deepcopy(common),name='unhardened partner',kind='pokemon',
            trainer_id=self.a.entity_id,trainer=self.a.name,skills={'육상':'2d6'}))
        self.b=Combatant(self.rules,dict(deepcopy(common),name='actual opponent',kind='trainer',skills={'육상':3}))
        for actor,pos,side in ((self.p,(1,1),'party'),(self.q,(1,2),'party'),(self.b,(2,1),'foe')):
            self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native participant')
        for actor in (self.a,self.p,self.q,self.b):
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete medium body')
        for actor in (self.p,self.q):self.e.gm.observe_loyalty(actor,6,reason='actual willing partner')
        if acquire:self.acquire()
        if press:self.acquire(T.PRESS)
        if pain:self.acquire(T.PAIN)

    def acquire(self,feature=T.CLASS):
        return A.acquire_static(self.e,self.a,feature,acquisition_request_id='taskmaster/acquire/'+feature)
    def answer(self,key,value):
        if any(r['key']==key and type(r['answer']) is type(value) and r['answer']==value for r in self.e.rulings.answers):return
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!=key]
        self.e.rulings.add_answer(key,value,reason='explicit native player choice',scope='permanent')
    def train(self,target=None,count=3,request='training'):
        target=self.p if target is None else target;self.answer('taskmaster',count)
        return self.e.train_pokemon(self.a,[(target,[F.BRUTAL])],minutes=30,
            reason='actual completed Brutal Training',request_id=request,safe=True)
    def injury(self,target,count):self.e.gm.set_injuries(target,value=count,reason='observed actual current injury count')
    def hp(self,target,hp):self.e.gm.set_hp(target,value=hp,reason='observed current HP')
    def combat(self,actor):
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor,initiative_count=20)
    def restore(self):
        ids=[c.entity_id for c in (self.a,self.p,self.q,self.b)]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index=W.actor_index(self.e);self.a,self.p,self.q,self.b=[index[uid] for uid in ids]
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def rejected(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
    def attack(self,actor,target,move='move/물대포'):
        with patch.object(Engine,'d20',return_value=10):
            return self.e.use_move_on(actor,target,move,self.e.everyone,set_damage=True)

    def test_real_acquisition_prerequisites_historical_rank_and_imported_names(self):
        self.setup(acquire=False)
        self.rejected(lambda:self.acquire(T.PRESS),'actual acquired Taskmaster')
        self.a.spec['feats']=[];self.rejected(self.acquire,'actual Brutal Training');self.a.spec['feats']=[F.BRUTAL]
        SF.base_patch(self.a,{'skills':{'협박':2,'명령':6}},reason='below Novice Intimidate')
        self.rejected(self.acquire,'training feature prerequisite')
        SF.base_patch(self.a,{'skills':{'협박':3,'명령':6}},reason='Novice actual qualification')
        receipt=self.acquire();self.assertEqual(receipt['source']['span'],[961,963])
        self.rejected(lambda:self.acquire(T.PAIN),'printed Intimidate')
        SF.base_patch(self.a,{'skills':{'협박':6,'명령':6}},reason='actual Master Intimidate')
        self.acquire(T.PAIN);self.acquire(T.PRESS)
        SF.base_patch(self.a,{'skills':{'협박':2,'명령':6}},reason='later rank does not rewrite acquisition')
        self.assertEqual(self.acquire(),receipt);self.restore();self.valid()
        self.setup(acquire=False);self.a.spec['classes']=[T.CLASS]
        self.answer('taskmaster',3)
        self.rejected(lambda:self.train(),'source-specific Taskmaster')

    def test_actual_training_optional_zero_three_replay_and_orders_do_not_harden(self):
        self.setup();self.train(count=False,request='declined')
        self.assertEqual(self.p.injuries,0);self.assertIsNone(T.active(self.p))
        self.train(count=0,request='zero-healthy');self.assertIsNone(T.active(self.p))
        self.injury(self.p,1);result=self.train(count=0,request='zero-injured')
        self.assertEqual(self.p.injuries,1);self.assertIsNotNone(T.active(self.p))
        before=self.e.export_state();self.assertEqual(self.train(count=0,request='zero-injured'),result)
        self.assertEqual(self.e.export_state(),before)
        self.answer('taskmaster',4)
        self.rejected(lambda:self.train(count=4,request='invalid-count'),'Taskmaster injury grant')
        self.train(count=3,request='three');self.assertEqual(self.p.injuries,4)
        self.assertEqual(len(T.records(self.p)),1);self.valid();self.restore();self.valid()
        self.e.start_round(self.e.everyone)
        self.e.gm.observe_sensory_environment(self.a,self.q,paths={'auditory':True},present=True,reason='actual Order delivery')
        F.orders(self.e,self.a,F.BRUTAL,self.q)
        self.assertEqual(self.q.injuries,0);self.assertIsNone(T.active(self.q))

    def test_current_thresholds_reach_native_critical_effect_evasion_initiative_damage_and_recovery(self):
        self.setup();self.train();move=self.rules.move('move/물대포')
        original_max=self.p.base_max_hp
        for count in range(10):
            self.injury(self.p,count)
            self.assertEqual(self.p.max_hp,int(original_max*(1-min(count,5)/10)))
            self.assertEqual(self.e.initiative_value(self.p).value,10+(5 if count>=3 else 0))
            self.assertEqual(self.p.evasion('특수'),self.q.evasion('특수')+(1 if count>=3 else 0))
            self.assertEqual(CPF.effect_natural(self.e,self.p,move,10),11+(1 if count else 0))
            self.assertEqual(self.e.accuracy_check(self.p,self.b,move,fixed_roll=18)[2],count>=1)
            damage=self.e.roll_damage(self.b,self.p,move,set_damage=True)
            control=self.e.roll_damage(self.b,self.q,move,set_damage=True)
            if count<5:self.assertEqual(damage,control)
            elif count<9:self.assertEqual(damage,control-5)
            else:self.assertEqual(damage,(control-5)//2)
        self.injury(self.p,6);self.hp(self.p,1);self.e.heal(self.p,999,source_kind='feature')
        self.assertEqual(self.p.hp,self.p.max_hp);self.assertEqual(self.p.base_max_hp,original_max)
        self.assertEqual(INJURY.heal(self.e,self.p,3,source='natural_rest'),3)
        self.assertEqual(self.p.injuries,3);self.assertEqual(T.bonus(self.p,'dr'),0)
        self.assertEqual(self.p.max_hp,int(original_max*0.7));self.valid()

    def test_native_standard_and_incoming_attack_distinguish_acting_exemption_from_seven_injury_immunity(self):
        self.setup();self.train();self.injury(self.p,5);self.combat(self.p)
        before=self.p.hp;damage=self.attack(self.p,self.b)
        self.assertGreater(damage,0);self.assertEqual(self.p.hp,before)
        self.assertEqual(self.p.budget['standard'],0);self.assertIsNone(self.e._heavy_pending)
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=10)
        before=self.p.hp;damage=self.attack(self.b,self.p)
        self.assertGreater(damage,0);self.assertEqual(self.p.hp,before-damage-5)
        self.assertIsNone(self.e._heavy_pending)
        self.e.end_of_turn(self.b);self.e.end_round();self.injury(self.p,7)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
        before=self.p.hp;damage=self.attack(self.b,self.p)
        self.assertEqual(self.p.hp,before-damage);self.assertIsNone(self.e._heavy_pending)
        for unpreventable in (False,True):
            for kind in ('loss','percentage'):
                before=self.p.hp;self.e.lose_hp(self.p,17,source='actual nonattack effect',loss_kind=kind,unpreventable=unpreventable)
                self.assertEqual(self.p.hp,before)
        self.e.lose_hp(self.p,1,source='actual setting effect',loss_kind='hp_setting')
        self.assertEqual(self.p.hp,before-1);self.valid()
        self.setup();self.train();self.injury(self.p,5);self.combat(self.b)
        before=self.p.hp
        with patch.object(Engine,'roll_damage',return_value=0):self.attack(self.b,self.p)
        self.assertEqual(self.p.hp,before);self.assertIsNone(self.e._heavy_pending)

    def test_press_on_actual_faint_choice_threshold_continuation_and_all_six_master_bonuses(self):
        self.setup(press=True);self.train();self.injury(self.p,8);self.hp(self.p,1);self.answer('press_on',True)
        self.combat(self.p);before=AP.available(self.a)
        # HP-setting keeps the explicit distinction from the seven-injury loss immunity.
        self.e.lose_hp(self.p,self.p.hp+1,source='actual setting crossing',loss_kind='hp_setting')
        self.assertEqual(self.p.hp,-1);self.assertFalse(self.p.fainted)
        self.assertEqual(AP.available(self.a),before-1);self.assertNotIn('기절',self.p.conditions)
        self.assertEqual(self.e.initiative_value(self.p).value,20)
        self.assertEqual(self.p.evasion('특수'),self.q.evasion('특수')+2)
        move=self.rules.move('move/물대포')
        self.assertTrue(self.e.accuracy_check(self.p,self.b,move,fixed_roll=17)[2])
        self.assertEqual(CPF.effect_natural(self.e,self.p,move,10),13)
        control=self.e.roll_damage(self.b,self.q,move,set_damage=True)
        self.assertEqual(self.e.roll_damage(self.b,self.p,move,set_damage=True),(control-10)//4)
        self.restore();self.assertFalse(self.p.fainted);self.assertTrue(TURN.can_act(self.e,self.p))
        self.assertGreater(self.attack(self.p,self.b),0);self.assertEqual(self.p.budget['standard'],0)
        self.assertEqual(AP.available(self.a),before-1)
        # At exactly -30% real maximum, no second purchase postpones fainting.
        threshold=-(self.p.base_max_hp*3//10)
        self.e.lose_hp(self.p,self.p.hp-threshold,source='actual threshold setting',loss_kind='hp_setting')
        self.assertTrue(self.p.fainted);self.assertIn('기절',self.p.conditions)
        self.assertEqual(AP.available(self.a),before-1);self.valid()

    def test_press_on_decline_expert_only_move_bans_and_soulless(self):
        self.setup(press=True);self.train();self.answer('press_on',False)
        self.hp(self.p,0);self.assertTrue(self.p.fainted)
        self.setup(press=True);self.train();SF.base_patch(self.a,{'skills':{'협박':5,'명령':6}},reason='current Expert tier')
        self.answer('press_on',True);self.hp(self.p,-1);self.assertFalse(self.p.fainted)
        self.assertEqual(self.e.initiative_value(self.p).value,15);self.assertEqual(self.p.evasion('특수'),self.q.evasion('특수')+1)
        self.combat(self.p)
        for move in ('move/대폭발','move/버티기','move/아픔나누기','move/자폭'):
            self.rejected(lambda move=move:self.e.use_move_on(self.p,self.b,move,self.e.everyone),'cannot be used at nonpositive HP')
        self.assertGreater(self.attack(self.p,self.b),0)
        self.setup(press=True)
        shed=Combatant(self.rules,build_pokemon(self.rules,'Shedinja',20,name='actual Soulless',moves=['move/물대포'],
            abilities=['불가사의부적'],extra={'trainer_id':self.a.entity_id,'trainer':self.a.name}))
        self.e.gm.add_combatant(shed,pos=(3,3),side='party',reason='actual Soulless participant')
        prepare_body(self.e,shed,size=shed.spec['size'],offsets=[(0,0)],reason='observed complete Soulless body')
        self.e.gm.observe_loyalty(shed,6,reason='actual willing partner')
        self.train(shed,count=3,request='soulless');self.assertEqual(shed.injuries,0);self.assertIsNone(T.active(shed))
        self.answer('press_on',True);before=AP.available(self.a);self.hp(shed,0)
        self.assertTrue(shed.fainted);self.assertEqual(AP.available(self.a),before);self.valid()

    def test_pain_resistance_is_optional_one_ap_per_scene_per_pokemon_without_hardened_requirement(self):
        self.setup(pain=True);self.injury(self.p,1);self.injury(self.q,1)
        self.assertIsNone(T.active(self.p));self.assertIsNone(T.active(self.q))
        self.answer('pain_resistance',True);self.combat(self.b)
        before=AP.available(self.a);damage=self.attack(self.b,self.p)
        self.assertEqual(AP.available(self.a),before-1);self.assertGreater(damage,0)
        self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
        second=self.attack(self.b,self.p);self.assertGreater(second,damage);self.assertEqual(AP.available(self.a),before-1)
        self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
        third=self.attack(self.b,self.q);self.assertEqual(third,damage);self.assertEqual(AP.available(self.a),before-2)
        self.e.end_of_turn(self.b);self.e.end_scene(round_elapsed_seconds=10)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
        self.assertEqual(self.attack(self.b,self.p),damage);self.valid();self.restore();self.valid()
        self.setup(pain=True);self.injury(self.p,1);self.answer('pain_resistance',False);self.combat(self.b)
        before=AP.available(self.a);self.attack(self.b,self.p);self.assertEqual(AP.available(self.a),before)

    def test_source_lifecycle_rest_does_not_end_class_result_and_transfer_removes_only_owned_hardened(self):
        self.setup();self.train();self.injury(self.p,7)
        F.extended_rest(self.e,self.a)
        self.assertEqual(F.active(self.p),[]);self.assertIsNotNone(T.active(self.p));self.assertEqual(T.bonus(self.p,'effect'),1)
        self.restore();self.valid()
        before=self.p.injuries
        import pokemon_party as PARTY
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual party roster',roster=[self.p,self.q])
        PARTY.configure(self.e,self.b,mode='unlimited',reason='actual receiving empty roster',roster=[])
        PARTY.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='actual ownership transfer',request_id='taskmaster-transfer')
        self.assertEqual(self.p.injuries,before);self.assertIsNone(T.active(self.p));self.assertEqual(self.p.max_hp,int(self.p.base_max_hp*0.3))
        self.assertEqual(self.p.spec['trainer_id'],self.b.entity_id);self.valid()

    def test_invalid_reaction_choices_and_late_damage_failures_are_atomic(self):
        self.setup(press=True,pain=True);self.train();self.answer('press_on','invalid')
        self.rejected(lambda:self.e.lose_hp(self.p,self.p.hp,source='actual crossing'),'explicit Press On')
        self.answer('press_on',True);self.hp(self.p,1)
        self.answer('pain_resistance','invalid');self.combat(self.b)
        self.rejected(lambda:self.attack(self.b,self.p),'explicit Pain Resistance')
        self.answer('pain_resistance',True);before=self.e.export_state()
        original=Engine._take_damage
        def fail(e,c,amount):
            original(e,c,amount)
            raise ValueError('late actual native damage failure')
        with patch.object(Engine,'_take_damage',fail):
            self.rejected(lambda:self.attack(self.b,self.p),'late actual native damage failure')
        self.assertEqual(self.e.export_state(),before);self.valid()

    def all_features(self):
        self.a.spec.setdefault('feats',[]).append(T.PRESS_ACTION)
        for feature in (T.QUICK,T.SAVAGE,T.WHIP,T.PAIN,T.PRESS,T.DESPERATE,T.GAMBIT):self.acquire(feature)

    def gambit_features(self):
        self.all_features()
        self.answer('cruelty',False)
        G.set_baseline(self.b,'moves',list(self.b.spec['moves'])[:5]+['move/몸통박치기'])

    def test_class_template_defines_eight_independent_acquisitions_and_exact_dependency_count(self):
        self.setup();self.assertEqual(len(T.DEFINITIONS),8)
        self.assertTrue(all(T.acquired(self.a,f) is None for f in T.FEATURES if f!=T.CLASS))
        self.rejected(lambda:self.acquire(T.DESPERATE),'printed Taskmaster prerequisites')
        self.rejected(lambda:self.acquire(T.WHIP),'printed Taskmaster prerequisites')
        self.rejected(lambda:self.acquire(T.GAMBIT),'five actual')
        self.all_features();self.assertTrue(all(T.acquired(self.a,f) is not None for f in T.FEATURES))
        self.restore();self.valid()

    def test_quick_healing_actual_extended_job_shared_natural_limit_and_current_hardened_thresholds(self):
        self.setup();self.acquire(T.QUICK)
        self.rejected(lambda:self.e.taskmaster_extended(self.a,self.p,T.QUICK,seconds=60,reason='actual rest',request_id='no-hard',injuries=3),'Hardened')
        self.train();self.injury(self.p,6);self.hp(self.p,1)
        at=self.e.elapsed_seconds
        first=self.e.taskmaster_extended(self.a,self.p,T.QUICK,seconds=60,reason='GM establishes one minute',request_id='quick1',injuries=2)
        self.assertEqual(first['injuries_removed'],2);self.assertEqual(self.p.injuries,4)
        self.assertEqual(self.e.elapsed_seconds,at+60);self.assertEqual(self.p.hp,1+4*self.e.tick(self.p))
        self.assertEqual(INJURY.healed_today(self.p),2);self.assertEqual(T.bonus(self.p,'dr'),0)
        second=self.e.taskmaster_extended(self.a,self.p,T.QUICK,seconds=60,reason='second actual rest',request_id='quick2',injuries=3)
        self.assertEqual(second['injuries_removed'],1);self.assertEqual(INJURY.healed_today(self.p),3)
        third=self.e.taskmaster_extended(self.a,self.p,T.QUICK,seconds=60,reason='daily limit consumed',request_id='quick3',injuries=3)
        self.assertEqual(third['injuries_removed'],0)
        self.rejected(lambda:self.e.taskmaster_extended(self.a,self.p,T.QUICK,seconds=0,reason='invalid duration',request_id='bad',injuries=1),'Extended duration')
        self.restore();self.valid()

    def test_savage_strike_real_tp_job_repeat_without_invented_cap_and_transfer_refund(self):
        self.setup();self.acquire(T.SAVAGE)
        self.p.spec['tutor_points']=4
        import ability_transitions as AB,pokemon_party as PARTY
        for i in range(2):
            result=self.e.taskmaster_extended(self.a,self.p,T.SAVAGE,seconds=60,reason='actual Cruelty lesson',request_id='savage'+str(i))
            self.assertEqual(result['ability'],T.CRUELTY);self.assertEqual(self.p.spec['tutor_points'],2*(1-i))
            self.assertTrue(AB.active(self.p,T.CRUELTY))
        self.rejected(lambda:self.e.taskmaster_extended(self.a,self.p,T.SAVAGE,seconds=60,reason='no points left',request_id='no-tp'),'Tutor Points')
        self.restore();self.valid()
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual roster',roster=[self.p,self.q])
        PARTY.configure(self.e,self.b,mode='unlimited',reason='actual new trainer roster',roster=[])
        PARTY.transfer(self.e,self.a,target=self.p,new_owner=self.b,reason='actual transfer',request_id='savage-transfer')
        self.assertFalse(AB.active(self.p,T.CRUELTY));self.assertEqual(self.p.spec['tutor_points'],4);self.valid()

    def test_press_and_whip_selected_effects_pay_actual_standard_swift_ap_and_free_training_order(self):
        self.setup();self.all_features();self.train();self.combat(self.a)
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual audible Order')
        self.e.apply_status(self.p,'잠듦');self.e.apply_status(self.p,'혼란')
        before_hp=self.p.hp;before_ap=AP.available(self.a);before_injury=self.p.injuries
        result=self.e.manual_feat(self.a,T.PRESS_ACTION,self.p,adjustment={'stats':['atk','spe'],'obedience':True,
            'whip':{'injury':True,'cure':True,'order':F.BRUTAL}})
        self.assertEqual(result['source'],T.PRESS_ACTION)
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['swift'],0)
        self.assertEqual(self.p.hp,before_hp-self.p.base_max_hp//6)
        self.assertEqual(self.p.injuries,before_injury+1);self.assertEqual(self.p.temp_hp,self.e.tick(self.p))
        self.assertNotIn('잠듦',self.p.conditions);self.assertNotIn('혼란',self.p.conditions)
        self.assertEqual(AP.available(self.a),before_ap-1)
        self.assertEqual(self.p.stages['atk'],1);self.assertEqual(self.p.stages['spe'],1)
        self.assertIn('free',self.a._action_history)
        self.assertEqual(T.obedience_bonus(self.e,self.a,{'purpose':'pokemon_obedience'},self.p),3)
        self.assertEqual(T.obedience_bonus(self.e,self.a,{'purpose':'pokemon_obedience'},self.q),0)
        self.assertEqual(T.obedience_bonus(self.e,self.a,{'purpose':'other'},self.p),0)
        self.restore();self.valid();self.e.end_of_turn(self.a);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
        self.assertEqual(T.obedience_bonus(self.e,self.a,{'purpose':'pokemon_obedience'},self.p),0)

    def test_whip_is_optional_and_rejects_unknown_orders_wrong_choices_without_costs(self):
        self.setup();self.all_features();self.combat(self.a)
        self.rejected(lambda:self.e.manual_feat(self.a,T.PRESS_ACTION,self.p,adjustment={'stats':['atk','atk']}),'two distinct')
        self.rejected(lambda:self.e.manual_feat(self.a,T.PRESS_ACTION,self.p,adjustment={'stats':['atk','spe'],'whip':{'order':T.PAIN}}),'targeted')
        self.e.manual_feat(self.a,T.PRESS_ACTION,self.p,adjustment={'stats':['atk','spe']})
        self.assertEqual(self.a.budget['swift'],1);self.assertEqual(self.p.injuries,0);self.assertEqual(self.p.temp_hp,0)

    def cruelty_choice(self,**options):
        choice={'desperate':False,'normal_trigger':True,'hp_loss':0,'slowed':False,'healing_block':False}
        choice.update(options);self.answer('cruelty',choice)

    def test_cruelty_real_damaging_hit_discloses_budget_applies_purchases_and_shared_gain_block_boundaries(self):
        self.setup();self.acquire(T.SAVAGE);self.p.spec['tutor_points']=2
        self.e.taskmaster_extended(self.a,self.p,T.SAVAGE,seconds=60,reason='actual lesson',request_id='cruelty')
        self.injury(self.b,4);self.hp(self.b,self.b.base_max_hp//3);self.combat(self.p)
        self.cruelty_choice(hp_loss=2,slowed=True,healing_block=True)
        before=self.b.hp;damage=self.attack(self.p,self.b)
        self.assertEqual(self.b.injuries,5);self.assertEqual(self.b.hp,before-damage-4)
        self.assertIn('둔화',self.b.conditions);self.assertEqual(self.p.budget['swift'],0)
        self.assertTrue(any('current injuries 5' in line for line in self.e.log_lines))
        self.assertEqual(self.e.heal(self.b,20,source_kind='feature'),0)
        import temporary_hp as TEMP,healing_blocks as BLOCK
        TEMP.grant(self.e,self.b,10,provenance={'source':'actual gain'});self.assertEqual(self.b.temp_hp,0)
        self.restore();self.valid()
        BLOCK.boundary(self.e,[self.b],'breather');self.assertGreater(self.e.heal(self.b,20,source_kind='feature'),0)
        for boundary in ('replacement','encounter_end'):
            import custom_condition_effects as CUSTOM
            CUSTOM.grant(self.e,self.p,self.b,T.cruelty_definition(self.rules)['raw'],T.CRUELTY)
            BLOCK.boundary(self.e,[self.b],boundary);self.assertFalse(BLOCK.blocked(self.b))

    def test_cruelty_decline_invalid_budget_and_miss_do_not_apply_or_charge(self):
        self.setup();self.acquire(T.SAVAGE);self.p.spec['tutor_points']=2
        self.e.taskmaster_extended(self.a,self.p,T.SAVAGE,seconds=60,reason='actual lesson',request_id='cruelty')
        self.combat(self.p);self.cruelty_choice(hp_loss=999)
        self.rejected(lambda:self.attack(self.p,self.b),'purchase.*budget')
        self.answer('cruelty',False);self.attack(self.p,self.b)
        self.assertEqual(self.b.injuries,0);self.assertEqual(self.p.budget['swift'],1)
        self.e.end_of_turn(self.p);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
        self.combat(self.p);self.cruelty_choice()
        before=self.b.hp
        with patch.object(Engine,'d20',return_value=1):self.e.use_move_on(self.p,self.b,'move/독침',self.e.everyone,set_damage=True)
        self.assertEqual(self.b.hp,before);self.assertEqual(self.b.injuries,0);self.assertEqual(self.p.budget['swift'],1)
        self.e.end_of_turn(self.p);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
        self.combat(self.p)
        # The real accuracy/hit path still completes when defense reduces damage to zero.
        with patch.object(Engine,'roll_damage',return_value=0):self.attack(self.p,self.b)
        self.assertEqual(self.b.hp,before);self.assertEqual(self.b.injuries,1);self.assertEqual(self.p.budget['swift'],0)

    def test_desperate_critical_trigger_without_ability_and_normal_trigger_retains_swift_and_scene_quotas(self):
        self.setup();self.acquire(T.SAVAGE);self.acquire(T.DESPERATE);self.injury(self.p,3)
        self.combat(self.p);self.cruelty_choice(desperate=True,normal_trigger=False,hp_loss=4)
        before=self.b.hp
        with patch.object(Engine,'d20',return_value=20):damage=self.e.use_move_on(self.p,self.b,'move/독침',self.e.everyone,set_damage=True)
        self.assertEqual(self.b.hp,before-damage-8);self.assertEqual(self.b.injuries,1)
        self.assertEqual(self.p.budget['swift'],1)
        self.assertFalse(FREQUENCY.activation_allowed(self.p,T.DESPERATE,{'kind':'scene','uses':1},engine=self.e))
        self.e.end_of_turn(self.p);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
        self.p.spec['tutor_points']=2
        self.e.taskmaster_extended(self.a,self.p,T.SAVAGE,seconds=60,reason='actual later lesson',request_id='cruelty-after-critical')
        self.combat(self.p);self.cruelty_choice(desperate=True,normal_trigger=True,hp_loss=1)
        self.attack(self.p,self.b);self.assertEqual(self.p.budget['swift'],0)
        self.assertTrue(FREQUENCY.activation_allowed(self.p,T.CRUELTY,{'kind':'scene','uses':1},engine=self.e))

    def test_press_on_native_healing_positive_ends_paid_exception_and_gm_invalid_choice_is_atomic(self):
        self.setup(press=True);self.train();self.answer('press_on',True)
        self.e.lose_hp(self.p,self.p.hp,source='first real faint crossing')
        paid=AP.available(self.a);self.assertFalse(self.p.fainted)
        self.e.heal(self.p,10,source_kind='feature');self.assertGreater(self.p.hp,0)
        self.assertFalse(T.active(self.p)['press_on'])
        self.e.lose_hp(self.p,self.p.hp,source='second real faint crossing');self.assertEqual(AP.available(self.a),paid-1)
        self.e.heal(self.p,10,source_kind='feature');self.answer('press_on','bad')
        self.rejected(lambda:self.e.gm.set_hp(self.p,value=0,reason='actual GM correction'),'explicit Press On')

    def test_deadly_gambit_real_melee_counter_frequency_simultaneous_hp_and_double_ko(self):
        self.setup();self.gambit_features();self.e.death_enabled=False
        self.hp(self.p,10);self.hp(self.b,10);self.combat(self.b)
        self.answer('deadly_gambit',{'move':'move/독침','roll_effects':False,'options':{'set_damage':True}})
        before_uses=self.p.move_uses.get('move/독침',0)
        applied=[];original=Engine._take_damage
        def observe(e,c,amount):
            applied.append((c.entity_id,c.hp,e._taskmaster_gambit is not None))
            return original(e,c,amount)
        with patch.object(Engine,'_take_damage',observe):damage=self.attack(self.b,self.p,'move/몸통박치기')
        self.assertGreater(damage,0);self.assertLessEqual(self.p.hp,0);self.assertLessEqual(self.b.hp,0)
        self.assertTrue(self.p.fainted);self.assertTrue(self.b.fainted)
        self.assertEqual(self.p.move_uses.get('move/독침',0),before_uses+1)
        self.assertEqual(len(applied),2);self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None))
        self.assertFalse(FREQUENCY.activation_allowed(self.a,T.GAMBIT,{'kind':'scene','uses':1},engine=self.e))
        self.restore();self.valid()
        # A draining counter heals only after both immediate damage receipts.
        self.setup();self.gambit_features();self.e.death_enabled=False
        G.set_baseline(self.p,'moves',list(self.p.spec['moves'])[:5]+['move/흡수'])
        self.hp(self.p,120);self.combat(self.b)
        self.answer('deadly_gambit',{'move':'move/흡수','roll_effects':False,'options':{'set_damage':True}})
        import combat_damage as DAMAGE
        receipts=[];native_application=DAMAGE.application
        def receipt(**fields):
            result=native_application(**fields);receipts.append(result);return result
        with patch.object(DAMAGE,'application',side_effect=receipt):damage=self.attack(self.b,self.p,'move/몸통박치기')
        incoming=next(row for row in receipts if row['source']=='move/몸통박치기')
        self.assertEqual(incoming['net_hp_loss'],damage)
        self.assertGreater(self.p.hp,incoming['after']['hp'])
        self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None));self.valid()

    def test_deadly_gambit_optional_counter_decline_effect_roll_and_critical_immunity_asymmetry(self):
        import ability_transitions as AB
        self.setup();self.gambit_features();self.e.death_enabled=False
        G.set_baseline(self.p,'abilities',['조가비갑옷/전투무장'])
        self.combat(self.b);self.answer('deadly_gambit',{'move':None,'roll_effects':True})
        move=self.rules.move('move/몸통박치기');expected=self.e.roll_damage(self.b,self.q,move,crit=True,set_damage=True)
        with patch.object(Engine,'d20',return_value=1):damage=self.e.use_move_on(self.b,self.p,'move/몸통박치기',self.e.everyone,set_damage=True)
        self.assertEqual(damage,expected);self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None))
        self.e.end_of_turn(self.b);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
        self.combat(self.b);self.answer('deadly_gambit',False)
        self.assertEqual(self.attack(self.b,self.p,'move/몸통박치기'),self.e.roll_damage(self.b,self.p,move,crit=False,set_damage=True))
        self.e.end_of_turn(self.b);self.e.end_scene(self.e.everyone,round_elapsed_seconds=10)
        G.set_baseline(self.b,'abilities',['조가비갑옷/전투무장'])
        self.assertTrue(AB.active(self.b,'ability/조가비갑옷-전투무장'))
        self.combat(self.b);self.answer('deadly_gambit',{'move':'move/독침','roll_effects':False,'options':{'set_damage':True}})
        expected_counter=self.e.roll_damage(self.p,self.b,self.rules.move('move/독침'),crit=False,set_damage=True)
        before=self.b.hp;self.attack(self.b,self.p,'move/몸통박치기')
        self.assertEqual(self.b.hp,before-expected_counter)
        self.setup();self.gambit_features()
        G.set_baseline(self.p,'moves',list(self.p.spec['moves'])[:5]+['move/방어'])
        self.combat(self.p);self.e.use_move(self.p,self.p,'move/방어')
        self.assertIsNotNone(self.p.shield)
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=10)
        self.answer('deadly_gambit',{'move':None,'roll_effects':False})
        before=self.p.hp;self.e.use_move(self.b,self.p,'move/몸통박치기',set_damage=True)
        self.assertEqual(self.p.hp,before);self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None))

    def test_deadly_gambit_bad_counter_and_late_second_damage_failure_roll_back_whole_attack(self):
        self.setup();self.gambit_features();self.combat(self.b)
        self.answer('deadly_gambit',{'move':'move/모르는-기술','roll_effects':False})
        self.rejected(lambda:self.attack(self.b,self.p,'move/몸통박치기'),'known Deadly')
        self.answer('deadly_gambit',{'move':'move/독침','roll_effects':False,'options':{'set_damage':True}})
        original=Engine._take_damage;calls=[]
        def fail(e,c,amount):
            calls.append(c.entity_id);result=original(e,c,amount)
            if len(calls)==2:raise ValueError('second paired native damage failure')
            return result
        with patch.object(Engine,'_take_damage',fail):self.rejected(lambda:self.attack(self.b,self.p,'move/몸통박치기'),'second paired native damage failure')
        self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None));self.valid()

    def test_whip_non_training_native_order_keeps_actual_ap_binding_and_receipt_source(self):
        self.setup();self.all_features()
        self.a.spec.setdefault('feats',[]).extend((CPF.PRECISION,CPF.PINPOINT))
        self.combat(self.a)
        before=AP.available(self.a)
        self.e.manual_feat(self.a,T.PRESS_ACTION,self.p,adjustment={'stats':['atk','spe'],'whip':{'order':CPF.PINPOINT}})
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['swift'],0)
        self.assertEqual(AP.available(self.a),before-2)
        self.assertIsNotNone(CPF.binding(self.e,self.p));self.assertIn('free',self.a._action_history)
        self.restore();self.valid()

    def test_deadly_gambit_accepts_native_basic_struggle_without_learned_move_entry(self):
        self.setup();self.gambit_features();self.combat(self.b)
        self.answer('deadly_gambit',{'move':'struggle','roll_effects':False})
        before=self.b.hp;self.attack(self.b,self.p,'move/몸통박치기')
        self.assertLess(self.b.hp,before);self.assertEqual(self.p.last_move,'struggle')
        self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None));self.valid()

    def test_whip_native_directive_records_real_free_payment_and_preserves_target_lifetime(self):
        import directive_features as D
        self.setup();self.all_features()
        self.a.spec.setdefault('classes',[]).append(D.CLASS)
        self.a.spec.setdefault('feats',[]).append(D.FEATURE)
        SF.base_patch(self.a,{'skills':{'협박':6,'명령':6,'매력':3}},reason='actual native Coordinator directive skills')
        self.combat(self.a);before=self.e.initiative_value(self.p).value
        self.e.manual_feat(self.a,T.PRESS_ACTION,self.p,adjustment={'stats':['atk','spe'],
            'whip':{'order':{'feature':D.FEATURE,'options':{'adjustment':'increase'}}}})
        row=next(row for row in self.e._effect_dispatch_receipts.values() if row.get('source_id')==D.SOURCE)
        plan=row[D.KEY]['plan'];self.assertEqual(plan['action'],'free')
        self.assertEqual(plan['free_order_payment']['source'],T.WHIP)
        self.assertGreater(self.e.initiative_value(self.p).value,before)
        self.restore();self.valid()
