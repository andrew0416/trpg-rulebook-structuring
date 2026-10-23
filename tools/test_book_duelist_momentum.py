"""Six Book Duelist clauses through their actual native producers and consumers."""
from copy import copy,deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_class_passive_combat_bulk as FIXTURE
from engine import Rules,Combatant
from builder import build_pokemon
import duelist as D,trainer_feature_acquisition as TFA,training_features as TRAIN
import state_fields as F,state_grants as G,state_codec as CODEC,frequency as FREQ
import combat_timing as TIME,condition_recovery as RECOVERY,ability_transitions as AB
import move_completion as COMPLETE,weapon_actions as WEAPONS,effects_ext as EXT
import class_passive_combat as CLASS,directive_features as DIRECT,combat_precision_features as PRECISION


class DuelistMomentumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')
    def setup(self,*,directed=False,ability='착취',pokemon_types=None,enemy_types=None):
        self.rules.rulings.answers=[row for row in self.rules.rulings.answers if row['key'] not in ('duelist_eleven','type_methodology')]
        helper=FIXTURE.ClassPassiveCombatBulkTests();helper.rules=self.rules
        self.e,self.a,self.p,self.t=helper.fixture(feats=[TRAIN.FOCUSED,D.METHODS],
            pokemon_moves=['몸통박치기','화염방사','불태우기','메가혼','파괴광선','잠자기'],
            pokemon_types=pokemon_types,enemy_types=enemy_types)
        F.base_patch(self.a,{'skills':{'집중':6,'명령':6,'매력':4,'통찰':5,'육상':4,'협박':4,'생존':4}},reason='actual Book Duelist prerequisites')
        for uid in (D.CLASS,D.EXPEND,D.TYPE,D.MANUAL,D.SEIZE,*((D.DIRECTED,) if directed else ())):
            TFA.acquire_static(self.e,self.a,uid,acquisition_request_id='duelist/'+uid)
        self.e.gm.observe_loyalty(self.p,6,reason='actual willing owned partner')
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual Order delivery')
        if ability:self.e.gm.set_ability(self.p,ability,reason='actual method ability')
        self.e.train_pokemon(self.a,[(self.p,[TRAIN.FOCUSED])],minutes=30,reason='actual Focused Training',request_id='focused-training',safe=True)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20)
        self.e.manual_feat(self.a,D.CLASS,self.t)
        self.e.end_of_turn(self.a)
        return self.e,self.a,self.p,self.t
    def answer(self,kind,value):
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!=kind]
        self.e.rulings.add_answer(kind,value,reason='actual player decision',scope='permanent')
    def rounds(self,count,*,closed=False):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        for n in range(count):
            self.e.end_round()
            if n+1<count or not closed:self.e.start_round(self.e.everyone)
    def start(self,actor):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        if self.e.round_start_seconds is None:self.e.start_round(self.e.everyone)
        if self.e._ordinary_turn_rounds.get(actor)==self.e.round_no:self.rounds(1)
        self.e.start_of_turn(actor,initiative_count=20)
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def snapshot(self):return CODEC.dump_engine(self.e)
    def reject(self,fn):
        before=self.snapshot()
        with self.assertRaises(ValueError):fn()
        self.assertEqual(self.snapshot(),before)
    def attack(self,*,natural=10,move='move/몸통박치기',actor=None,target=None,area=False):
        actor=actor or self.p;target=target or self.t
        with patch.object(type(self.e),'d20',new=lambda e:natural):
            return self.e.use_move_on(actor,target,move,self.e.everyone,set_damage=True) if area else self.e.use_move(actor,target,move,set_damage=True)
    def expend(self,amount,move=None):
        self.start(self.a)
        return self.e.manual_feat(self.a,D.EXPEND,self.p,adjustment={'amount':amount,'move':move})
    def manual(self,mode,**options):
        self.start(self.a)
        return self.e.manual_feat(self.a,D.MANUAL,self.p,adjustment={'mode':mode,**options})
    def extra_partner(self):
        p=Combatant(self.rules,build_pokemon(self.rules,'이브이',20,name='second actual partner',moves=['몸통박치기'],abilities=[],
            extra={'trainer_id':self.a.entity_id,'trainer':self.a.name}))
        self.e.gm.add_combatant(p,pos=(1,1),side='party',reason='actual distinct owned Pokemon')
        return p

    def test_exact_six_sources_and_acquisition_excludes_already_completed_effective_methods(self):
        self.setup()
        self.assertEqual(set(D.FEATURES),{D.CLASS,D.EXPEND,D.DIRECTED,D.TYPE,D.MANUAL,D.SEIZE})
        self.assertNotIn(D.METHODS,D.FEATURES)
        self.assertEqual(hashlib.sha256((ROOT/'input/ch04-trainer-classes.md').read_bytes()).hexdigest(),'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4')
        for uid,span in D.FEATURES.items():
            self.assertEqual(TFA.STATIC_FEATURES[uid]['span'],list(span))
        self.assertTrue(D.acquired(self.a));self.assertEqual(D.momentum(self.p),0);self.valid()

    def test_tagged_foe_accuracy_evasion_only_suppresses_focused_accuracy_elsewhere(self):
        self.setup();self.rounds(3)
        other=self.extra_partner();other.side='other-foe'
        move=self.rules.move('move/몸통박치기')
        self.assertEqual(D.accuracy(self.e,self.p,self.t),2)
        self.assertEqual(D.evasion(self.e,self.p,self.t),2)
        self.assertEqual(D.accuracy(self.e,self.p,other),-1)
        self.assertEqual(TRAIN.bonus(self.p,'skill'),2)
        with_tag=self.e.accuracy_check(self.p,self.t,move,fixed_roll=5)
        without_tag=self.e.accuracy_check(self.p,other,move,fixed_roll=5)
        self.assertTrue(with_tag[0]);self.assertEqual(TRAIN.bonus(self.p,'accuracy'),1)
        self.assertEqual(self.p.evasion('물리',attacker=self.t,engine=self.e)-self.p.evasion('물리',attacker=other,engine=self.e),2)
        self.start(self.a);self.e.manual_feat(self.a,D.CLASS,other)
        self.assertFalse(D.tagged(self.e,self.p,self.t));self.assertTrue(D.tagged(self.e,self.p,other));self.valid()

    def test_actual_hit_round_end_cap_and_recall_faint_combat_end_clear(self):
        self.setup();self.start(self.p);self.attack();self.assertEqual(D.momentum(self.p),1)
        row=next(iter(self.e._move_completions.values()));COMPLETE.refresh(self.e)
        self.assertEqual(D.momentum(self.p),1)
        self.rounds(7);self.assertEqual(D.momentum(self.p),6)
        self.e.end_encounter(self.e.everyone);self.assertEqual(D.momentum(self.p),0)
        self.assertIsNone(self.a.spec[D.KEY]['tag'])
        self.e.start_round(self.e.everyone);self.rounds(2)
        self.e.take_damage(self.p,self.p.hp+100)
        self.assertEqual(D.momentum(self.p),0);self.valid()
        self.setup();self.rounds(2)
        self.e.end_scene(self.e.everyone);self.assertEqual(D.momentum(self.p),0)
        self.setup();self.rounds(2)
        __import__('combat_state_lifecycle').recall(self.e,self.p)
        self.assertEqual(D.momentum(self.p),0);self.valid()

    def test_expend_restores_only_selected_eot_or_scene_move_and_scene_quota_is_per_pokemon(self):
        for amount,move in ((1,'move/화염방사'),(3,'move/메가혼')):
            with self.subTest(amount=amount):
                self.setup();self.rounds(6);self.start(self.p);self.attack(natural=1,move=move)
                before=dict(self.p.move_uses)
                self.expend(amount,move)
                self.assertEqual(self.p.move_uses[move],before[move]-1)
                for uid,count in before.items():
                    if uid!=move:self.assertEqual(self.p.move_uses[uid],count)
                if amount==3:
                    self.start(self.p);self.attack(natural=1,move=move);self.start(self.a)
                    self.reject(lambda:self.e.manual_feat(self.a,D.EXPEND,self.p,adjustment={'amount':3,'move':move}))
                self.valid()

    def test_expend_chosen_eleven_reaches_accuracy_and_saving_once_during_next_own_turn(self):
        for saving in (False,True):
            with self.subTest(saving=saving):
                self.setup();self.rounds(3);self.expend(2);self.answer('duelist_eleven',True)
                self.assertTrue(any(r.get('duelist_eleven') for r in TIME.records(self.p)))
                self.start(self.p)
                if saving:
                    out=RECOVERY.saving_check(self.e,self.p,'마비',11,fixed=1);self.assertEqual(out['natural'],11)
                    self.assertEqual(RECOVERY.saving_check(self.e,self.p,'마비',11,fixed=2)['natural'],2)
                else:
                    self.assertEqual(self.e.accuracy_check(self.p,self.t,self.rules.move('move/몸통박치기'),fixed_roll=1)[1],11)
                    self.assertEqual(self.e.accuracy_check(self.p,self.t,self.rules.move('move/몸통박치기'),fixed_roll=2)[1],2)
                self.assertFalse(any(r.get('duelist_eleven') for r in TIME.records(self.p)));self.valid()
        self.setup();self.rounds(3);self.expend(2);self.start(self.p)
        self.answer('duelist_eleven',False);requests=[];decide=type(self.e.rulings).decide
        def observe(ruling,request,*args,**kwargs):
            if request.get('type')=='duelist_eleven':requests.append(deepcopy(request))
            return decide(ruling,request,*args,**kwargs)
        with patch.object(type(self.e.rulings),'decide',new=observe),patch.object(type(self.e),'d20',new=lambda e:7):
            self.assertEqual(self.e.accuracy_check(self.p,self.t,self.rules.move('move/몸통박치기'))[1],7)
        self.assertEqual(len(requests),1)
        self.answer('duelist_eleven',1)
        self.reject(lambda:self.e.accuracy_check(self.p,self.t,self.rules.move('move/몸통박치기'),fixed_roll=7))
        self.answer('duelist_eleven',True);requests.clear()
        with patch.object(type(self.e.rulings),'decide',new=observe):self.attack(move='move/불태우기',area=True,natural=1)
        self.assertEqual(len(requests),1)
        self.assertFalse(any(r.get('duelist_eleven') for r in TIME.records(self.p)));self.valid()

    def test_directed_training_and_all_native_order_routes_award_once_after_success(self):
        for route in ('training','stratagem','director','pinpoint'):
            with self.subTest(route=route):
                self.setup(directed=True)
                if route=='training':self.rounds(1)
                else:self.start(self.a)
                before=D.momentum(self.p)
                if route=='training':
                    self.e.manual_feat(self.a,TRAIN.FOCUSED,self.p)
                else:
                    if route=='stratagem':
                        uid=next(iter(CLASS.STRATAGEMS));self.a.spec['feats'].append(uid)
                        self.e.activate_class_passive(self.a,self.p,uid)
                    elif route=='director':
                        self.a.spec.setdefault('classes',[]).append(DIRECT.CLASS);self.a.spec['feats'].append(DIRECT.FEATURE)
                        self.e.use_decisive_director(self.a,self.p,adjustment='increase')
                    else:
                        self.a.spec['feats'].extend([PRECISION.PRECISION,PRECISION.PINPOINT]);PRECISION.activate(self.e,self.a,self.p)
                self.assertEqual(D.momentum(self.p),before+1);self.valid()
        self._directed_native_manual_order_batch()

    def test_directed_super_effective_actual_damage_and_whole_area_completion_deduplicate(self):
        self.setup(directed=True,enemy_types=['풀']);self.start(self.p)
        self.attack(move='move/불태우기',area=True)
        row=list(self.e._move_completions.values())[-1]
        self.assertEqual(row['phase'],'complete')
        self.assertEqual(D.momentum(self.p),2)
        self.assertEqual(len([r for r in self.p.spec[D.KEY]['gains'] if r['origin']['kind']=='super_effective']),1)
        COMPLETE.refresh(self.e);COMPLETE.refresh(self.e)
        self.assertEqual(D.momentum(self.p),2);self.valid()

    def test_native_non_move_ability_attack_hit_awards_tag_momentum(self):
        self.setup(ability='현혹');self.start(self.p)
        from ruleset import bind_rule_identity
        uid=self.rules.selection.resolve_name('현혹',('ability/',))
        effect=bind_rule_identity(self.rules.ability_effects['현혹'],uid)[0]
        with patch.object(type(self.e),'d20',new=lambda e:20):
            result=self.e.apply_effect(self.p,self.t,effect,None,True,0,uid)
        self.assertFalse(result.pending)
        self.assertEqual(D.momentum(self.p),1);self.assertIn('잠듦',self.t.conditions);self.valid()

    def _directed_native_manual_order_batch(self):
        # A declared application-authored Order exercises the existing generic
        # producer without assigning new effects to an unrelated Book feature.
        self.rules=copy(self.rules);self.rules.selection=copy(self.rules.selection)
        self.setup(directed=True);self.start(self.a)
        uid='authored/duelist/native-order';name='Declared Directed Focus diagnostic'
        reference={'file':'input/ch04-trainer-classes.md','sha256':hashlib.sha256((ROOT/'input/ch04-trainer-classes.md').read_bytes()).hexdigest()}
        self.rules.register_source_policy_definitions([{'id':uid,'title':name,'source':reference,'locator':{'lines':[1,1]},'tags':['지시'],
            'rationale':'Application-authored diagnostic of native Orders completion, not a Book feature interpretation'}])
        freq={'kind':'at_will','action':'standard'}
        row={'type':'feat_manual','name':name,'usage_key':uid,'frequency':freq,'activation_header':{'id':uid,'frequency':freq},'effects':[
            {'type':'stage_change','stat':'atk','delta':1,'target':'target'},
            {'type':'stage_change','stat':'def','delta':1,'target':'target','if':'target was asleep'},
            {'type':'stage_change','stat':'spe','delta':1,'target':'target'}]}
        self.a.active_effects.register_definition_row(self.e,'external-row:'+uid,'registry',row)
        before=D.momentum(self.p);self.e.manual_feat(self.a,name,self.p)
        self.assertEqual(D.momentum(self.p),before)
        token=next(t for t,r in self.e._effect_dispatch_receipts.items() if r['status']=='condition_unknown')
        self.e.resolve_effect_condition(self.a,token,target_was_asleep=True,reason='actual diagnostic condition observation')
        self.assertEqual(D.momentum(self.p),before+1)
        import cheerleader as CHEER
        CHEER.refresh_batches(self.e);self.assertEqual(D.momentum(self.p),before+1);self.valid()

    def test_type_methodology_uses_actual_resisted_outgoing_and_super_effective_incoming(self):
        for incoming in (False,True):
            for decision in (False,True,1):
                with self.subTest(incoming=incoming,decision=decision):
                    self.setup(ability='강내성' if incoming else '착취',pokemon_types=['풀'] if incoming else ['노말'],enemy_types=['물'])
                    self.rounds(3);self.answer('type_methodology',decision)
                    self.start(self.t if incoming else self.p)
                    actor,target=(self.t,self.p) if incoming else (self.p,self.t)
                    if type(decision) is not bool:
                        self.reject(lambda:self.attack(actor=actor,target=target,move='move/화염방사'))
                        continue
                    events=[];roll=type(self.e).roll_damage
                    def observed(e,*args,**kwargs):
                        result=roll(e,*args,**kwargs)
                        if kwargs.get('_reaction_event') is not None:events.append(deepcopy(kwargs['_reaction_event']['damage_formula']))
                        return result
                    before=D.momentum(self.p)
                    with patch.object(type(self.e),'roll_damage',new=observed):self.attack(actor=actor,target=target,move='move/화염방사')
                    self.assertEqual(events[-1]['multiplier'],1.0 if decision else 1.5 if incoming else 0.5)
                    self.assertEqual(D.momentum(self.p),before-(2 if decision else 0)+(0 if incoming else 1))
                    self.assertEqual(FREQ.state(self.a)['activations'].get(D.TYPE,{}).get('used',0),int(decision));self.valid()

    def test_method_ability_passives_and_manual_double_exchange_expire_on_pokemon_turn(self):
        self.setup(ability='강내성',pokemon_types=['물']);self.rounds(2)
        fire=self.rules.move('move/화염방사');event={}
        self.e.roll_damage(self.t,self.p,fire,set_damage=True,_reaction_event=event)
        self.assertEqual(event['damage_formula']['multiplier'],0.25)
        self.manual(1);event={};self.e.roll_damage(self.t,self.p,fire,set_damage=True,_reaction_event=event)
        self.assertEqual(event['damage_formula']['multiplier'],0.125)
        before=D.momentum(self.p);self.assertGreaterEqual(before,1)
        self.start(self.p);self.e.end_of_turn(self.p)
        self.assertEqual(D.method_multiplier(self.p),1)
        self.manual(1,ability=D.EXPLOIT);self.assertTrue(AB.active(self.p,D.EXPLOIT));self.assertFalse(AB.active(self.p,D.TOLERANCE))
        self.start(self.p);self.e.end_of_turn(self.p)
        self.assertTrue(AB.active(self.p,D.TOLERANCE));self.assertFalse(AB.active(self.p,D.EXPLOIT));self.valid()

    def test_manual_next_attack_range_and_actual_hit_vulnerable_and_victim_initiative_lifetime(self):
        self.setup();self.rounds(3);self.manual(2);before=D.momentum(self.p)
        rng=WEAPONS.range_spec(self.e,self.rules.move('move/불태우기'),self.p)
        self.assertNotIn('shape',rng);self.assertEqual(rng['targets'],1)
        self.assertEqual(D.momentum(self.p),before)
        self.start(self.p);self.attack(move='move/불태우기',area=True)
        self.assertIn('취약',self.t.conditions)
        self.assertTrue(any(r.get('initiative_zero') for r in TIME.records(self.t)))
        self.e.end_of_turn(self.p)
        self.assertTrue(any(r.get('initiative_zero') for r in TIME.records(self.t)))
        self.start(self.t);self.e.end_of_turn(self.t)
        self.assertFalse(any(r.get('initiative_zero') for r in TIME.records(self.t)));self.valid()

    def test_manual_next_turn_ignores_only_four_conditions_for_tagged_attack_without_curing(self):
        self.setup();self.rounds(3);self.manual(3)
        self.e.apply_status(self.p,'혼란',source='move/혼란',applied_by=self.t)
        self.e.apply_status(self.p,'억압',source='move/사슬묶기',applied_by=self.t)
        self.e.apply_status(self.p,'헤롱헤롱',source='move/헤롱헤롱',applied_by=self.t)
        self.e.apply_status(self.p,'난동',source='move/분노',applied_by=self.t)
        self.start(self.p)
        other=self.extra_partner();other.side='other-foe'
        before=(deepcopy(self.p.budget),deepcopy(self.p.move_uses),other.hp,D.momentum(self.p))
        self.assertEqual(self.attack(move='move/잠자기',target=other),0)
        self.assertEqual((self.p.budget,self.p.move_uses,other.hp,D.momentum(self.p)),before)
        self.attack(move='move/화염방사')
        self.assertIn('혼란',self.p.conditions);self.assertIn('억압',self.p.conditions)
        self.assertEqual(__import__('combat_maneuvers').infatuation_damage(self.p,self.t,self.rules.move('move/화염방사'),self.p,40),(20,0))
        self.e.end_of_turn(self.p)
        self.assertFalse(any(r.get('duelist_mode')==3 for r in TIME.records(self.p)))
        self.start(self.a)
        self.reject(lambda:self.e.manual_feat(self.a,D.MANUAL,self.p,adjustment={'mode':3}));self.valid()

    def test_seize_round_end_actual_overflow_miss_smite_and_no_future_turn_debt(self):
        for move in ('move/몸통박치기','move/파괴광선'):
            with self.subTest(move=move):
                self.setup();self.rounds(7,closed=True)
                pending=self.e.pending_duelist_interrupts(self.a);self.assertEqual(len(pending),1)
                before=self.t.hp;budget=deepcopy(getattr(self.p,'budget',None))
                expected=self.e.roll_damage(self.p,self.t,self.rules.move(move),set_damage=True)//2
                applications=[];take=type(self.e).take_damage
                def observed(e,actor,amount):
                    if actor.entity_id==self.t.entity_id:applications.append(amount)
                    return take(e,actor,amount)
                with patch.object(type(self.e),'d20',new=lambda e:1),patch.object(type(self.e),'take_damage',new=observed):
                    self.e.seize_the_moment(self.a,self.p,event_id=pending[0]['id'],move=move,target=self.t,set_damage=True)
                self.assertEqual(applications,[expected]);self.assertEqual(self.t.hp,before-expected)
                self.assertEqual(D.momentum(self.p),1);self.assertEqual(getattr(self.p,'budget',None),budget);self.assertIsNone(self.e._active_turn_actor)
                import initiative_interrupts as INTERRUPTS,exhaust_moves as EXHAUST
                self.assertFalse(getattr(self.e,INTERRUPTS.KEY)['loans'])
                if EXHAUST.applies(self.rules.move(move)):
                    self.assertEqual(self.p.pending_action_loss,EXHAUST.DEBT)
                    self.assertEqual(EXHAUST.record(self.p)['move_id'],move)
                else:self.assertFalse(getattr(self.p,'pending_action_loss',{}))
                self.assertFalse(self.e.pending_duelist_interrupts(self.a));self.valid()

    def test_seize_hit_auto_critical_original_critical_heals_half_max_and_pokemon_quota(self):
        import life
        self.setup();self.rounds(7,closed=True)
        self.e.lose_hp(self.p,self.p.base_max_hp//4,source=D.SEIZE)
        before=self.p.hp;pending=self.e.pending_duelist_interrupts(self.a)[0]
        self.e.enable_execution_trace()
        with patch.object(type(self.e),'d20',new=lambda e:10),patch.object(life,'heal',wraps=life.heal) as healing:
            self.e.seize_the_moment(self.a,self.p,event_id=pending['id'],move='move/몸통박치기',target=self.t,set_damage=True)
        event=next(event for event in self.e.execution_traces() if event['producer']=='resolve_attack_damage')
        self.assertEqual(event['state'],'returned');self.assertTrue(event['inputs']['crit'])
        completion=next(row for row in self.e._move_completions.values() if row['actor'] is self.p)
        self.assertEqual(completion['phase'],'complete');self.assertTrue(completion['results'][self.t.entity_id]['hit'])
        self.assertEqual(self.p.hp,before);healing.assert_not_called()
        row=next(row for row in self.p.spec[D.KEY]['gains'] if row['id']==pending['id'])
        self.assertFalse(row.get('heal_applied',False));self.assertEqual(row.get('healed',0),0);self.valid()
        self.setup();self.rounds(7,closed=True)
        self.e.lose_hp(self.p,self.p.base_max_hp//2,source=D.SEIZE)
        before=self.p.hp;pending=self.e.pending_duelist_interrupts(self.a)[0]
        import life
        requested=[];heal=life.heal
        def observed(e,actor,amount,source_kind='unspecified'):
            if actor.entity_id==self.p.entity_id:requested.append(amount)
            return heal(e,actor,amount,source_kind=source_kind)
        with patch.object(type(self.e),'d20',new=lambda e:20),patch.object(life,'heal',new=observed):
            self.e.seize_the_moment(self.a,self.p,event_id=pending['id'],move='move/몸통박치기',target=self.t,set_damage=True)
        self.assertEqual(requested,[self.p.base_max_hp//2])
        self.assertEqual(self.p.hp,min(self.p.max_hp,before+self.p.base_max_hp//2))
        row=next(row for row in self.p.spec[D.KEY]['gains'] if row['id']==pending['id'])
        self.assertEqual(row['healed'],self.p.hp-before);self.assertTrue(row['heal_applied'])
        self.assertEqual(D.momentum(self.p),2)
        self.reject(lambda:self.e.seize_the_moment(self.a,self.p,event_id=pending['id'],move='move/몸통박치기',target=self.t,set_damage=True))
        self.e.start_round(self.e.everyone);self.rounds(6,closed=True)
        self.assertFalse(self.e.pending_duelist_interrupts(self.a));self.valid()

    def test_codec_rejects_changed_source_receipt_and_counter_bounds(self):
        self.setup();self.rounds(3);self.expend(2)
        state=self.snapshot();restored=CODEC.load_engine(self.rules,state)
        self.assertTrue(restored.validate_state()['valid'])
        bad=deepcopy(state)
        # Mutate the live receipt through the same public validation boundary.
        self.a.spec[D.USES][0]['momentum']=6
        self.assertFalse(self.e.validate_state()['valid'])
        self.a.spec[D.USES][0]['momentum']=3
        self.p.counters[D.COUNTER]=7
        self.assertFalse(self.e.validate_state()['valid'])

    def test_global_suppression_removes_only_actual_ability_resistance_and_snapshot_restores(self):
        self.setup(ability='강내성',pokemon_types=['물']);fire=self.rules.move('move/화염방사')
        before={};self.e.roll_damage(self.t,self.p,fire,set_damage=True,_reaction_event=before)
        self.e.gm.snapshot('before-ability-suppression')
        self.e.apply_effect(self.t,self.p,{'type':'suppress_ability'},None,True,0,'audit/actual-ability-suppression')
        after={};self.e.roll_damage(self.t,self.p,fire,set_damage=True,_reaction_event=after)
        self.assertEqual((before['damage_formula']['multiplier'],after['damage_formula']['multiplier']),(0.25,0.5))
        self.e.gm.restore('before-ability-suppression',reason='restore actual active Ability state')
        restored={};self.e.roll_damage(self.t,self.p,fire,set_damage=True,_reaction_event=restored)
        self.assertEqual(restored['damage_formula']['multiplier'],0.25)
        self.valid()


if __name__=='__main__':unittest.main()
