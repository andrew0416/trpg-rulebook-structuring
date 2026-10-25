"""Keep Fighting uses actual acquired sources and each real native HP producer."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon,species_lookup
import test_book_moment_of_action as FIXTURE
import keep_fighting as K,cheerleader as CH,moment_of_action as M
import trainer_feature_acquisition as TFA,trainer_retraining as RETRAIN
import state_fields as F,state_codec as CODEC,state_grants as G
import temporary_hp as HP,frequency as FREQ,action_points as AP
import actor_templates as TEMPLATES,life as LIFE,move_completion as COMPLETE


class KeepFightingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='core')
        cls.errata=Rules(str(ROOT),ruleset='core+errata')
    def setup(self,*,acquire=True,parents=5,combat=True,rules=None):
        base=FIXTURE.MomentOfActionTests();base.rules=rules or self.rules;base.setup(combat=False)
        self.base=base;self.e,self.a,self.b,self.c=base.e,base.a,base.b,base.c
        F.base_patch(self.a,{'skills':{'매력':6,'명령':2}},reason='actual Master Charm prerequisite')
        for feature in (CH.BRIGADE,CH.SUPPORT,'feat/신나게-방해')[:parents-2]:self.acquire(feature)
        if acquire:self.acquire()
        self.answer(True)
        if combat:self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
    def acquire(self,feature=K.FEATURE,request=None):
        return TFA.acquire_static(self.e,self.a,feature,acquisition_request_id=request or 'acquire/'+feature)
    def answer(self,value):
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='keep_fighting']
        self.e.rulings.add_answer('keep_fighting',value,reason='explicit actual trigger decision',scope='permanent')
    def state(self):return CODEC.dump_engine(self.e)
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def unchanged(self,callback):
        before=self.state()
        with self.assertRaises(ValueError):callback()
        self.assertEqual(self.state(),before)
    def pokemon(self,name='owned partner',*,owner=True,species='이브이',moves=(),abilities=(),extra=None):
        values=dict(extra or {})
        if owner:values.update(trainer_id=self.a.entity_id,trainer=self.a.name)
        target=Combatant(self.e.r,build_pokemon(self.e.r,species,20,name=name,moves=list(moves),abilities=list(abilities),extra=values))
        self.e.gm.add_combatant(target,pos=(1,0),side='party',reason='actual registered Pokemon')
        return target
    def ready_hp(self,target,hp=1,temp=0):
        self.e.gm.set_temp_hp(target,temp,reason='observed temporary HP before actual crossing')
        self.e.gm.set_hp(target,value=hp,reason='observed initial positive HP')
    def assert_saved(self,target,*,charm=6,uses=1):
        self.assertEqual(target.hp,1);self.assertEqual(target.temp_hp,2*charm)
        self.assertFalse(target.fainted);self.assertNotIn('기절',target.conditions);self.assertFalse(target.dead)
        self.assertEqual(len(K._uses(self.a)),uses);self.valid()
    def retrain(self,feature,request):
        options=self.base.base.decisions(self.e,self.a,feature,request=request)
        owned=RETRAIN._owned(self.a);sources={uid:RETRAIN.owned_source(self.e,self.a,uid) for uid in owned}
        for child,parents in RETRAIN._native_dependencies(self.e,self.a,owned).items():
            if child!=feature:options['retained_dependencies'][sources[child]]=[sources[p] for p in parents]
        if K.FEATURE in owned and feature!=K.FEATURE:
            options['retained_dependencies'][sources[K.FEATURE]]=[sources[p] for p in K.FAMILY if p in owned and p!=feature]
        return self.e.retrain_trainer_source(self.a,feature,**options)

    def test_five_actual_cheerleader_features_master_charm_and_historical_replay(self):
        self.setup(acquire=False,parents=4,combat=False);self.unchanged(self.acquire)
        self.a.spec['feats'].append('feat/신나게-방해');self.unchanged(self.acquire)
        self.a.spec['feats'].remove('feat/신나게-방해');self.acquire('feat/신나게-방해')
        F.base_patch(self.a,{'skills':{'매력':5,'명령':2}},reason='only Expert Charm');self.unchanged(self.acquire)
        F.base_patch(self.a,{'skills':{'매력':6,'명령':2}},reason='Master Charm');receipt=self.acquire()
        self.assertEqual(len(receipt['snapshot']['features']),5);self.assertEqual(receipt['snapshot']['charm'],6)
        before=self.state();self.assertEqual(self.acquire(),receipt);self.assertEqual(self.state(),before)
        self.unchanged(lambda:self.acquire(request='distinct duplicate'))
        F.base_patch(self.a,{'skills':{'매력':2,'명령':2}},reason='later skill decline does not rewrite qualification')
        self.ready_hp(self.b);self.e.lose_hp(self.b,1,source='actual post-acquisition loss');self.assert_saved(self.b,charm=2)
        self.setup(combat=False)
        self.a.spec['edges'].append('edge/거장');self.a.spec['edge_choices']={'edge/거장':['매력']}
        self.ready_hp(self.b);self.e.lose_hp(self.b,1,source='actual Virtuoso Charm rescue');self.assert_saved(self.b,charm=8)
        self.assertEqual(CH.acquired(self.a,K.FEATURE)['snapshot']['charm'],6)

    def test_damage_replaces_hp_one_crossing_before_markers_faint_and_retains_massive_damage(self):
        for rules in (self.rules,self.errata):
            self.setup(rules=rules);self.ready_hp(self.b)
            self.b.conditions.add('독');before_ap=AP.available(self.a);calls=[];original=LIFE.faint
            def observe(engine,actor):calls.append(actor.entity_id);return original(engine,actor)
            amount=self.b.base_max_hp
            with patch.object(LIFE,'faint',side_effect=observe):injuries=self.e.take_damage(self.b,amount)
            self.assert_saved(self.b);self.assertEqual(injuries,1);self.assertEqual(self.b.injuries,1)
            self.assertNotIn(self.b.entity_id,calls);self.assertIn('독',self.b.conditions)
            self.assertEqual(AP.available(self.a),before_ap);self.assertEqual(self.a._action_history.count('free'),1)
            origin=K._uses(self.a)[0]['origin'];self.assertEqual((origin['before_hp'],origin['proposed_hp'],origin['amount']),(1,1-amount,amount))

    def test_loss_percentage_hp_setting_and_unpreventable_policies_use_post_temporary_hp(self):
        cases=[('loss',False,'temp_first',4,5),('percentage',False,'temp_first',4,5),
               ('hp_setting',False,'temp_first',4,1)]
        for kind,unpreventable,policy,temp,amount in cases:
            self.setup();self.ready_hp(self.b,temp=temp);self.e.gm.set_hp_loss_policy(policy,reason='actual adopted policy')
            self.e.lose_hp(self.b,amount,source='actual '+kind,loss_kind=kind,unpreventable=unpreventable)
            self.assertEqual(self.b.hp,1);self.assertFalse(self.b.fainted)
            self.assertEqual(self.b.temp_hp,max(temp if kind=='hp_setting' or unpreventable and policy=='bypass' else max(0,temp-amount),12))
            self.assertEqual(K._uses(self.a)[0]['origin']['proposed_hp'],0);self.valid()
        # Explicitly unpreventable loss is not a Keep Fighting trigger.
        # Retain each real temporary-HP policy without granting prevention.
        for policy,temp,amount,remaining in [('temp_first',4,5,0),('bypass',20,1,20)]:
            self.setup();self.ready_hp(self.b,temp=temp);self.e.gm.set_hp_loss_policy(policy,reason='actual adopted policy')
            self.e.lose_hp(self.b,amount,source='actual loss',loss_kind='loss',unpreventable=True)
            self.assertEqual(self.b.hp,0);self.assertTrue(self.b.fainted)
            self.assertEqual(self.b.temp_hp,remaining);self.assertFalse(K._uses(self.a));self.valid()
        self.setup();self.ready_hp(self.b,temp=5);self.e.take_damage(self.b,5)
        self.assertEqual((self.b.hp,self.b.temp_hp),(1,0));self.assertFalse(K._uses(self.a));self.valid()

    def test_only_owned_pokemon_and_other_allied_trainers_with_positive_to_nonpositive_hp(self):
        for target_kind in ('owned','other_pokemon','enemy_trainer','self','zero','positive_after'):
            self.setup(combat=False)
            if target_kind in ('owned','other_pokemon'):target=self.pokemon(owner=target_kind=='owned')
            else:target=self.a if target_kind=='self' else self.b
            if target_kind=='enemy_trainer':target.side='enemy'
            if target_kind=='zero':self.answer(False)
            self.ready_hp(target,hp=0 if target_kind=='zero' else 2 if target_kind=='positive_after' else 1)
            self.answer(True)
            self.e.lose_hp(target,1,source='actual target eligibility loss')
            self.assertEqual(bool(K._uses(self.a)),target_kind=='owned')
            self.assertEqual(target.hp,1 if target_kind in ('owned','positive_after') else -1 if target_kind=='zero' else 0)
            self.valid()

    def test_gm_value_delta_and_explicit_faint_replace_before_any_faint_side_effect(self):
        for operation in ('value','delta','faint'):
            self.setup();self.ready_hp(self.b);self.b.conditions.add('독')
            if operation=='value':self.e.gm.set_hp(self.b,value=-8,reason='actual forced HP change')
            elif operation=='delta':self.e.gm.set_hp(self.b,delta=-9,reason='actual relative HP change')
            else:self.e.gm.faint(self.b,reason='actual forced faint HP transition')
            self.assert_saved(self.b);self.assertIn('독',self.b.conditions)

    def test_decline_exhausted_daily_and_unavailable_free_action_do_not_prevent_faint(self):
        for unavailable in ('decline','exhausted','unconscious','body'):
            self.setup();self.ready_hp(self.b)
            if unavailable=='decline':self.answer(False)
            elif unavailable=='exhausted':
                for _ in range(2):FREQ.consume_activation(self.a,K.FEATURE,K.QUOTA,engine=self.e)
            elif unavailable=='unconscious':self.e.gm.set_hp(self.a,value=0,reason='actual unconscious user')
            context=patch('body_modes.permits',return_value=False) if unavailable=='body' else patch('body_modes.permits',wraps=__import__('body_modes').permits)
            with context:self.e.lose_hp(self.b,1,source='actual unavailable reaction loss')
            self.assertTrue(self.b.fainted);self.assertFalse(K._uses(self.a));self.assertEqual(self.b.temp_hp,0);self.valid()

    def test_invalid_choice_and_late_grant_failure_roll_back_every_native_hp_boundary(self):
        for operation in ('damage','loss','gm_set','gm_faint'):
            self.setup();self.ready_hp(self.b,temp=3)
            fn={'damage':lambda:self.e.take_damage(self.b,4),'loss':lambda:self.e.lose_hp(self.b,4,source='atomic real loss'),
                'gm_set':lambda:self.e.gm.set_hp(self.b,value=0,reason='atomic GM'),'gm_faint':lambda:self.e.gm.faint(self.b,reason='atomic GM')}[operation]
            self.answer(['invalid']);self.unchanged(fn);self.answer(True)
            original=HP.grant
            def fail(engine,target,*args,**kwargs):
                original(engine,target,*args,**kwargs);engine.rng.random();engine.rulings.answers.clear()
                raise ValueError('failure after actual temporary HP grant')
            with patch.object(HP,'grant',side_effect=fail):self.unchanged(fn)
            fn();self.assert_saved(self.b)

    def test_boss_and_swarm_prevent_bar_consumption_until_actual_declined_crossing(self):
        for kind in ('boss','swarm'):
            self.setup(combat=False);target=self.pokemon()
            if kind=='boss':self.e.gm.set_encounter_template(target,kind='boss',total_bars=None,action_slots=None,
                action_basis={'pokemon_turns':2,'combat_trainers':1,'focused_command_extra':0},base_initiative=20,reason='actual boss')
            else:self.e.gm.set_encounter_template(target,kind='swarm',total_bars=3,action_slots=[{'id':'native','initiative':20}],reason='actual swarm',member_count_or_band='25_to_40')
            self.ready_hp(target);self.e.lose_hp(target,1000,source='actual bar crossing',loss_kind='hp_setting')
            self.assert_saved(target);view=TEMPLATES.projection(target)
            self.assertEqual(view['remaining_bars'],3);self.assertFalse(view['bar_transition_receipts'])
            self.answer(False);self.e.lose_hp(target,1000,source='actual declined bar crossing',loss_kind='hp_setting')
            self.assertEqual(TEMPLATES.projection(target)['remaining_bars'],2);self.valid()

    def test_actual_enemy_move_and_later_failure_share_the_new_native_transaction(self):
        self.setup(combat=False);enemy=self.pokemon('enemy attacker',owner=False,moves=['메가톤펀치']);enemy.side='enemy'
        self.ready_hp(self.b);self.e.start_round(self.e.everyone);self.e.start_of_turn(enemy,initiative_count=20)
        original=COMPLETE.finish_target
        def late(*args,**kwargs):original(*args,**kwargs);raise ValueError('actual native completion failure after rescue')
        with patch.object(type(self.e),'d20',new=lambda e:18),patch.object(COMPLETE,'finish_target',side_effect=late):
            self.unchanged(lambda:self.e.use_move(enemy,self.b,'move/메가톤펀치',set_damage=True))
        with patch.object(type(self.e),'d20',new=lambda e:18):self.e.use_move(enemy,self.b,'move/메가톤펀치',set_damage=True)
        self.assert_saved(self.b);self.assertEqual(K._uses(self.a)[0]['origin']['loss_kind'],'damage')

    def test_restore_source_integrity_daily_quota_and_shared_temporary_hp_expiry(self):
        self.setup(combat=False)
        for _ in range(2):self.ready_hp(self.b);self.e.lose_hp(self.b,1,source='actual daily use')
        self.assertEqual(len(K._uses(self.a)),2);ids=[a.entity_id for a in (self.a,self.b,self.c)]
        saved=self.state();self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(saved,ensure_ascii=False)))
        index={a.entity_id:a for a in self.e.everyone};self.a,self.b,self.c=[index[uid] for uid in ids]
        self.ready_hp(self.b);self.e.lose_hp(self.b,1,source='actual exhausted after restore');self.assertTrue(self.b.fainted)
        self.e.gm.revive(self.b,hp=1,reason='actual GM revival');FREQ.new_day(self.a)
        self.e.lose_hp(self.b,1,source='actual next-day crossing');self.assert_saved(self.b,uses=3)
        self.e.advance_time(300,[self.a,self.b]);self.assertEqual(self.b.temp_hp,0);self.assertEqual(self.b.hp,1);self.valid()
        K._uses(self.a)[0]['origin']['before_hp']=0
        self.assertFalse(self.e.validate_state()['valid'])
        with self.assertRaises(CODEC.StateCodecError):self.state()

    def test_retraining_preserves_five_feature_threshold_and_historical_rescue(self):
        self.setup(combat=False);self.ready_hp(self.b);self.e.lose_hp(self.b,1,source='actual before source withdrawal')
        self.unchanged(lambda:self.retrain('feat/신나게-방해','retrain/too-few'))
        self.acquire('feat/응원-문구');self.retrain('feat/신나게-방해','retrain/six-to-five')
        self.assertEqual(len([uid for uid in K.FAMILY if uid in RETRAIN._owned(self.a)]),5);self.valid()
        self.retrain(K.FEATURE,'retrain/keep');self.ready_hp(self.b);self.e.lose_hp(self.b,1,source='actual withdrawn source loss')
        self.assertTrue(self.b.fainted);self.assertEqual(len(K._uses(self.a)),1);self.valid()
        self.setup(combat=False);self.acquire('feat/전설의-트레이너')
        self.retrain('feat/전설의-트레이너','retrain/unrelated');self.valid()

    def test_as_one_linked_faint_is_intercepted_for_its_actual_owned_partner(self):
        import csv_item_form_contracts as FORMS
        self.setup(combat=False)
        rider=self.pokemon('actual rider',owner=False,species='버드렉스',extra={'capabilities':['혼연일체']})
        mount=self.pokemon('owned mount',species='레이스포스',abilities=['흑의울음'],extra={'capabilities':['탑승 2']})
        FORMS.mount_as_one(self.e,rider,mount,ability='흑의울음')
        self.ready_hp(rider);self.ready_hp(mount)
        self.answer(['invalid']);self.unchanged(lambda:self.e.lose_hp(rider,1,source='actual rider faint'))
        self.answer(True);self.e.lose_hp(rider,1,source='actual rider faint')
        self.assertTrue(rider.fainted);self.assert_saved(mount)
        self.assertEqual(K._uses(self.a)[0]['origin']['loss_kind'],'as_one')

    def test_nature_and_evolution_positive_hp_floor_crossings_use_actual_producers(self):
        import growth_stats as GROW,nature_state as N,downtime as DOWN
        for hp_policy in ('preserve_fraction','preserve_damage'):
            self.setup(combat=False);target=self.pokemon();self.ready_hp(target)
            base=species_lookup(self.rules,target.spec['species'])['base_stats']
            proposals=[]
            for nature in self.rules.mech('pokemon/natures')['by_name']:
                allocation=GROW.allocate(base,30,nature=nature,rules=self.rules)
                proposals.append((allocation['stats']['hp'],nature,allocation['investment']))
            _,nature,investment=min(proposals,key=lambda p:p[0])
            # Start from an actual valid alternative allocation with higher HP.
            _,large,large_investment=max(proposals,key=lambda p:p[0])
            self.e.commit_growth_nature(self.a,target,large,investment=large_investment,source='combat/struggle',reason='actual large-HP nature',ap_cost=0,hp_policy='preserve_fraction',request_id='nature/large')
            self.ready_hp(target)
            options=dict(investment=investment,source='combat/struggle',reason='actual lower-HP nature',ap_cost=0,hp_policy=hp_policy,request_id='nature/lower')
            self.answer(['invalid']);self.unchanged(lambda:self.e.commit_growth_nature(self.a,target,nature,**options))
            self.answer(True);self.e.commit_growth_nature(self.a,target,nature,**options)
            self.assert_saved(target);self.assertEqual(K._uses(self.a)[0]['origin']['loss_kind'],'nature_change')
        self.setup(combat=False);target=self.pokemon('actual evolving Pokemon',species='토중몬',abilities=['복안']);self.ready_hp(target)
        self.assertIn('껍질몬',dict(DOWN.evolution_options(self.e.r,target.spec)))
        self.answer(['invalid']);self.unchanged(lambda:DOWN.evolve_combatant(self.e,target,'껍질몬'))
        self.answer(True);result=DOWN.evolve_combatant(self.e,target,'껍질몬')
        self.assertTrue(result['evolved']);self.assertEqual(target.spec['species'],'pokemon/껍질몬');self.assertEqual(target.hp,1);self.assertFalse(target.fainted)
        self.assertEqual(target.temp_hp,0);self.assertEqual(K._uses(self.a)[0]['temp_gained'],0);self.valid()
        self.assertEqual(K._uses(self.a)[0]['origin']['loss_kind'],'evolution')


if __name__=='__main__':unittest.main()
