"""Conqueror's March uses the paid mounted Pass producer for all five families."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import test_book_ride_as_one as BASE
import conquerors_march as CM
import trainer_feature_acquisition as A
import control_mount as M,world_entities as W,state_codec as CODEC
import state_grants as G,state_fields as FIELDS,turn as TURN
import combat_timing as TIME,priority_limited as PRIORITY
import movement_actions as MOVE,physical_object_attacks as OBJECTS
from native_scenario_fixture import prepare_body, assert_rejected_unchanged

FAMILY_MOVES={'대시':'move/시저크로스','파열':'move/세차게휘두르기',
              '폭발':'move/일렉트릭네트','원뿔':'move/매지컬샤인','직선':'move/드래곤해머',
              '파열(변화)':'move/꼬리흔들기'}


class ConquerorsMarchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')

    def setup(self,*,acquire=True,run_up=True,mounted=True,moves=None):
        helper=BASE.RideAsOneTests();helper.rules=self.rules;helper.setup(acquire=False)
        self.e,self.a,self.p,self.enemy=helper.e,helper.a,helper.p,helper.enemy
        self.e.grid=Grid(16,10)
        FIELDS.base_patch(self.a,{'skills':{'곡예':4,'육상':3,'명령':3,'매력':3}},reason='actual Adept Conqueror qualification')
        self.p.spec['moves']=list((FAMILY_MOVES['대시'],FAMILY_MOVES['파열'],FAMILY_MOVES['원뿔'],'move/몸통박치기') if moves is None else moves)
        self.p.moves=list(self.p.spec['moves'])
        if run_up:
            G.grant(self.p,'abilities','도움닫기','gm/native-run-up','native_observation',
                    owner_id=None,lifetime=None,rule_id=CM.RUN_UP)
            G.ensure_ability(self.e,self.p,'도움닫기')
            self.assertTrue(any(row.get('_rule_id')==CM.RUN_UP for row in self.p.modifiers))
        self.enemy.pos=(1,0)
        self.other=Combatant(self.rules,dict(deepcopy(self.enemy.spec),id='conqueror/second-foe',name='second actual foe'))
        self.e.gm.add_combatant(self.other,pos=(3,0),side='foe',reason='second real traversed creature')
        self.map_bodies()
        if acquire:
            self.acquire(M.RIDER);self.acquire(CM.RAMMING);self.acquire(CM.FEATURE)
        if mounted:self.board()

    def acquire(self,feature,request=None):
        return A.acquire_static(self.e,self.a,feature,acquisition_request_id=request or 'march/acquire/'+feature)

    def board(self):
        result=self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True)
        self.assertTrue(result['passed']);return result

    def map_bodies(self):
        for actor, size in ((self.a, '중형'), (self.p, '중형'),
                            (self.enemy, '중형'), (self.other, '중형')):
            prepare_body(self.e, actor, size=size, offsets=[(0, 0)],
                reason='GM observes these four named Medium bodies in the mounted Pass scene')

    def snap(self):return CODEC.dump_engine(self.e)

    def reject(self,fn):
        before=self.snap();rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):fn()
        self.assertEqual(self.snap(),before);self.assertEqual(self.e.rng.getstate(),rng)

    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def restore(self):
        ids=[c.entity_id for c in (self.a,self.p,self.enemy,self.other)]
        saved=json.loads(json.dumps(self.snap(),ensure_ascii=False))
        self.rules=Rules(ROOT,ruleset='all')
        self.e=CODEC.load_engine(self.rules,saved)
        index=W.actor_index(self.e);self.a,self.p,self.enemy,self.other=[index[uid] for uid in ids]

    def start(self):
        self.e.start_round(self.e.everyone)
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual delivered mounted Order')

    def order(self,event='march/order'):
        return self.e.conquerors_march(self.a,self.p,event_id=event)

    def pass_move(self,mid,event='march/pass',objects=None,destination=(4,0)):
        return self.e.use_pass_move(self.p,mid,destination,event_id=event,range_source=CM.FEATURE,
            object_adjudications=objects or {},source='gm/march-object-hits',reason='actual observed Pass object hits and pre-DR damage')

    def close(self,actor):self.e.start_of_turn(actor);self.e.end_of_turn(actor)

    def test_existing_actor_body_preparation_preserves_native_identity_and_facts(self):
        self.setup()
        actor=self.p
        before=deepcopy({k:v for k,v in actor.spec.items() if k!='footprint'})
        moves=list(actor.moves);owner=actor.spec['trainer_id'];riders=list(M.mounted_pairs(actor))
        self.assertIs(prepare_body(self.e,actor,size='중형',offsets=[(0,0)],
            reason='GM confirms this same mounted Medium body'),actor)
        self.assertIs(W.actor_index(self.e)[actor.entity_id],actor)
        self.assertEqual({k:v for k,v in actor.spec.items() if k!='footprint'},before)
        self.assertEqual((actor.moves,actor.spec['trainer_id'],list(M.mounted_pairs(actor))),
                         (moves,owner,riders))
        for values in ({'size':'소형'},{'size':''},{'offsets':[]},{'reason':''}):
            facts=dict(size='중형',offsets=[(0,0)],reason='actual body observation')
            facts.update(values)
            self.reject(lambda:prepare_body(self.e,actor,**facts))

    def test_native_creature_pass_keeps_reactive_abilities_and_condition_owners(self):
        self.setup()
        self.e.gm.set_ability(self.p,'변환자재',reason='actual observed secondary Ability')
        self.e.gm.set_ability(self.enemy,'변색',reason='actual observed reactive target Ability')
        self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        self.e.choose_reactive_ability(self.p,'ability/변환자재',reason='actual owner chooses next native use')
        self.e.choose_reactive_ability(self.enemy,'ability/변색',reason='actual target chooses next native hit')
        self.e.apply_status(self.p,'독',source='move/독가루',applied_by=self.enemy)
        target_base=deepcopy(self.enemy.spec.get('types'));hp=[self.enemy.hp,self.other.hp]
        import reactive_ability_events as REACTIVE
        native_preflight=REACTIVE.preflight_move;checked=[]
        def observe_prepaid(e,actor,target,move,mm,**options):
            if target.entity_id==self.enemy.entity_id:
                import body_state as BODY
                self.assertEqual(BODY.flanking(e,target)['pending'],[])
                activation=e._move_activation_scopes[-1]['activation']
                payload={'actual':activation,'lookalike':dict(activation),'snapshot':{'values':[]}}
                copied=G._stage_transition_payload(e,e,payload)
                self.assertIs(copied['actual'],activation)
                self.assertIsNot(copied['lookalike'],activation)
                self.assertIsNot(copied['snapshot']['values'],payload['snapshot']['values'])
                before=deepcopy((actor.budget,actor.spec[REACTIVE.CHOICES]))
                self.assertEqual((actor.budget['standard'],actor.budget['swift']),(0,1))
                other=e.r.move('move/몸통박치기');other_mm=e.r.move_mech(other['id'])[0]
                with self.assertRaisesRegex(ValueError,'move and Swift action costs'):
                    native_preflight(e,actor,target,other,other_mm,**options)
                self.assertEqual((actor.budget,actor.spec[REACTIVE.CHOICES]),before)
                checked.append(move['id'])
            return native_preflight(e,actor,target,move,mm,**options)
        with patch.object(REACTIVE,'preflight_move',observe_prepaid),patch.object(Engine,'d20',lambda e:20):
            row=self.pass_move(FAMILY_MOVES['대시'])
        self.assertEqual(checked,[FAMILY_MOVES['대시']])
        move_type=self.rules.move(FAMILY_MOVES['대시'])['type']
        self.assertEqual((self.p.types,self.enemy.types),([move_type],[move_type]))
        self.assertEqual(self.enemy.spec.get('types'),target_base)
        self.assertTrue(all(c.hp<old for c,old in zip((self.enemy,self.other),hp)))
        self.assertEqual((self.p.budget['standard'],self.p.budget['shift'],self.p.budget['swift']),(0,0,0))
        completion=self.e._move_completions[row['completion_id']]
        self.assertEqual(completion['started'],[self.enemy.entity_id,self.other.entity_id])
        sources=[r['source'] for r in completion['reactive_ability']['applications']]
        self.assertEqual(sources.count('ability/변환자재'),1)
        self.assertEqual(sources.count('ability/변색'),1)
        hp=self.p.hp;self.e.end_of_turn(self.p)
        self.assertLess(self.p.hp,hp);self.assertIn('독',self.p.conditions)
        self.restore();self.valid()

    def test_actual_mount_overlap_never_supplies_two_flanking_contributors(self):
        import body_state as BODY
        self.setup()
        state=BODY.flanking(self.e,self.enemy)
        self.assertEqual(state['pending'],[])
        self.assertFalse(state['flanked']);self.assertEqual(state['contributors'],[])
        ally=Combatant(self.rules,dict(deepcopy(self.other.spec),
            id='conqueror/independent-ally',name='observed independent flanking ally'))
        self.e.gm.add_combatant(ally,pos=(2,0),side='party',reason='actual independent ally on the opposite side')
        prepare_body(self.e,ally,size='중형',offsets=[(0,0)],reason='observed independent Medium ally')
        state=BODY.flanking(self.e,self.enemy)
        self.assertTrue(state['flanked']);self.assertEqual(state['pending'],[])
        self.assertIn(ally.entity_id,state['contributors'])
        self.assertEqual(len(set(state['contributors']) & {self.a.entity_id,self.p.entity_id}),1)
        self.e.gm.set_position(ally,(1,0),reason='explicit unrelated overlapping-body negative scene')
        state=BODY.flanking(self.e,self.enemy)
        self.assertIsNone(state['flanked'])
        self.assertTrue(any(ally.entity_id in issue for issue in state['pending']))
        self.assertFalse(hasattr(self.e,'_pass_move_scope'))
        with self.assertRaisesRegex(ValueError,'overlapping bodies'):
            self.e.spatial_evasion_penalty(self.enemy)

    def test_native_status_pass_keeps_ability_protection_and_physical_limits(self):
        mid=FAMILY_MOVES['파열(변화)'];self.setup(moves=[mid])
        self.e.gm.set_ability(self.enemy,'클리어바디',reason='actual observed stage protection Ability')
        self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        with patch.object(Engine,'d20',lambda e:20):row=self.pass_move(mid)
        self.assertEqual((self.enemy.stages['def'],self.other.stages['def']),(0,-1))
        self.assertEqual(self.e._move_completions[row['completion_id']]['started'],
                         [self.enemy.entity_id,self.other.entity_id])
        self.valid()
        self.setup()
        self.e.gm.set_ability(self.enemy,'변색',reason='actual reactive Ability in a physical-target scene')
        self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        W.register_object(self.e,'march/object',location={'kind':'grid','cell':(2,0)},reason='actual traversed object')
        self.e.configure_object_durability(self.a,'march/object',max_hp=30,reduction=5,minimum_damage=0,
            source='gm/observed-durability',reason='actual ordinary object')
        self.reject(lambda:self.pass_move(FAMILY_MOVES['대시'],
            objects={'march/object':{'hit':True,'damage_before_dr':12}}))
        self.valid()
        self.setup();self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        self.e.apply_status(self.p,'얼음',source='move/냉동빔',applied_by=self.enemy)
        self.reject(lambda:self.pass_move(FAMILY_MOVES['대시']))
        self.valid()

    def test_interactive_pass_preserves_hit_and_resumes_actual_return(self):
        from hashlib import sha256
        self.setup();self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        source='input/'+self.rules.selection.units['combat/struggle']['source']['file']
        doc={'schema':1,'id':'event/pass-completion-choice','variants':[{
            'rule_id':'combat/struggle','source':{'file':source,'sha256':sha256((ROOT/source).read_bytes()).hexdigest()},
            'inputs':{'hit':{'authority':'context','type':'boolean','question':'Native hit'},
                      'choice':{'authority':'gm','type':'boolean','question':'Actual reaction choice'}},
            'when':{'op':'eq','left':{'$input':'hit'},'right':True},
            'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}]}
        listener=self.e.subscribe_source_policy(self.p,'pass-choice',doc,event='move_resolved',inputs={'hit':'hit'})
        import passive_events as EVENTS
        before=self.enemy.hp
        with patch.object(Engine,'d20',lambda e:20),self.assertRaises(EVENTS.PassiveEventPending):
            self.pass_move(FAMILY_MOVES['대시'])
        event=self.e._passive_pending;hp=self.enemy.hp
        self.assertLess(hp,before);self.valid();self.restore()
        other_hp=self.other.hp
        with patch.object(Engine,'d20',return_value=16),self.assertRaises(EVENTS.PassiveEventPending):
            self.e.choose_passive_event(event,self.p,listener,
                {'decisions':{'choice':{'value':True,'reason':'first actual source policy choice'}}})
        later=self.e._passive_pending;self.assertNotEqual(event,later)
        self.assertEqual(self.enemy.hp,hp);self.assertLess(self.other.hp,other_hp)
        self.assertEqual(self.p.stages['atk'],1);self.valid();self.restore()
        hp=(self.enemy.hp,self.other.hp);rng=self.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('already applied hits cannot reroll')):
            row=self.e.choose_passive_event(later,self.p,listener,
                {'decisions':{'choice':{'value':True,'reason':'second actual source policy choice'}}})
        self.assertEqual(row['phase'],'complete')
        self.assertEqual(((self.enemy.hp,self.other.hp),self.e.rng.getstate()),(hp,rng))
        self.assertEqual(self.p.stages['atk'],2)
        self.assertEqual(self.p.move_uses[FAMILY_MOVES['대시']],1)
        self.assertIsNone(self.e._passive_pending)
        self.assertFalse(hasattr(self.e,'_pass_move_scope'))
        self.assertFalse(hasattr(self.e,'_reactive_move_transaction'))
        self.valid()

    def test_actual_parent_acquisition_skill_alternatives_speed_and_historical_replay(self):
        self.setup(acquire=False,mounted=False)
        self.reject(lambda:self.acquire(CM.RAMMING));self.reject(lambda:self.acquire(CM.FEATURE))
        before=self.a.stats['spe'];self.acquire(M.RIDER)
        parent=self.acquire(CM.RAMMING)
        FIELDS.base_patch(self.a,{'skills':{'곡예':3,'육상':3}},reason='actual ranks below Adept')
        self.reject(lambda:self.acquire(CM.FEATURE))
        FIELDS.base_patch(self.a,{'skills':{'곡예':3,'육상':4}},reason='actual Athletics alternative')
        child=self.acquire(CM.FEATURE)
        self.assertEqual(child['snapshot']['parent_request'],parent['request_id'])
        self.assertEqual(child['source']['span'],[913,918]);self.assertEqual(self.a.stats['spe'],before+3)
        FIELDS.base_patch(self.a,{'skills':{'곡예':1,'육상':1}},reason='later skill loss preserves original acquisition facts')
        self.assertEqual(self.acquire(CM.FEATURE),child);self.restore()
        self.assertEqual(self.acquire(CM.FEATURE),child);self.valid()
        self.setup(acquire=False,mounted=False);self.a.spec['classes']=[M.RIDER]
        self.reject(lambda:self.acquire(CM.RAMMING))

    def test_order_requires_actual_owned_active_run_up_and_pays_one_standard(self):
        import passive_events as PASSIVE,heavy_injury_adapter as HEAVY
        self.setup(mounted=False);self.start()
        for module,error in ((PASSIVE,PASSIVE.PassiveEventPending('native-passive-boundary')),
                             (HEAVY,HEAVY.HeavyPending('native-heavy-boundary'))):
            before=self.snap();rng=self.e.rng.getstate()
            with patch.object(module,'ensure_clear',side_effect=error) as guard:
                with self.assertRaises(type(error)):self.order()
                guard.assert_called_once_with(self.e)
            self.assertEqual(self.snap(),before);self.assertEqual(self.e.rng.getstate(),rng)
        self.e.start_of_turn(self.a)
        for failure in ('owner','ability','standard','communication'):
            with self.subTest(failure=failure):
                before=self.snap()
                if failure=='owner':self.p.spec['trainer_id']=self.enemy.entity_id
                if failure=='ability':G.revoke(self.p,'gm/native-run-up',engine=self.e)
                if failure=='standard':self.a.budget['standard']=0
                if failure=='communication':
                    self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':False},present=True,reason='actual blocked Order')
                self.reject(self.order)
                self.e=CODEC.load_engine(self.rules,before)
                index=W.actor_index(self.e)
                self.a,self.p,self.enemy,self.other=[index[uid] for uid in (self.a.entity_id,self.p.entity_id,self.enemy.entity_id,self.other.entity_id)]
        row=self.order();self.assertEqual(row['payment']['kind'],'standard')
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(len(CM.live(self.p)),1)
        self.assertIsNone(CM.current(self.e,self.p))
        snap=self.snap();self.assertEqual(self.order(),row);self.assertEqual(self.snap(),snap)
        # Mounting spends its own actual Standard; this paid issuer has none left.
        # Other methods start from native pre-combat boarding and test actual use.
        self.e.end_of_turn(self.a);self.valid()

    def test_priority_order_reserves_native_standard_and_survives_both_restores(self):
        self.setup();self.start();row=self.order()
        reserved=PRIORITY.records(self.a)[0]
        self.assertEqual((row['payment']['kind'],reserved['payment']['funded']),('priority_limited',{'standard':1}))
        self.e.gm.snapshot('march/order');self.e.start_of_turn(self.a)
        self.assertEqual(self.a.budget['standard'],0);self.e.end_of_turn(self.a)
        self.e.gm.restore('march/order',reason='actual native Order restore');self.restore()
        self.assertEqual(self.order(),row);self.assertIsNotNone(CM.current(self.e,self.p))
        self.e.start_of_turn(self.a);self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(PRIORITY.records(self.a)[0]['payment']['phase'],'paid');self.valid()

    def test_actual_order_triggers_existing_cheerleader_once_and_late_failure_is_atomic(self):
        import cheerleader as CHEER,moment_of_action as MOMENT
        self.setup()
        self.a.spec['feats'].remove(MOMENT.TRAINING)
        self.acquire(MOMENT.TRAINING);self.acquire(MOMENT.CLASS)
        self.e.rulings.add_answer('cheerleader','Cheered',reason='actual player trigger choice',scope='permanent')
        self.start();self.e.start_of_turn(self.a)
        original=CHEER.issue
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise ValueError('late native Cheerleader consumer failure')
        with patch.object(CHEER,'issue',fail):self.reject(self.order)
        row=self.order()
        self.assertEqual(len(CHEER.live(self.p,'Cheered')),1)
        self.assertEqual(CHEER._uses(self.a)[0]['origin'],{'kind':'conquerors_march','source':CM.FEATURE,'use_id':row['id']})
        self.assertEqual(self.order(),row);self.assertEqual(len(CHEER.live(self.p,'Cheered')),1)
        self.restore();self.valid()

    def test_every_printed_range_family_uses_native_hits_actual_objects_and_shared_mount_movement(self):
        for family,mid in FAMILY_MOVES.items():
            with self.subTest(family=family):
                self.setup(moves=[mid]);self.start();self.order();self.close(self.a)
                W.register_object(self.e,'march/object',location={'kind':'grid','cell':(2,0)},reason='actual traversed object')
                self.e.configure_object_durability(self.a,'march/object',max_hp=30,reduction=5,minimum_damage=0,
                    source='gm/observed-durability',reason='actual ordinary object')
                hp=[self.enemy.hp,self.other.hp];original=deepcopy(self.rules.move(mid))
                status=original['class']=='변화'
                self.e.start_of_turn(self.p)
                with patch.object(TURN,'trigger_aoo',wraps=TURN.trigger_aoo) as aoo,patch.object(Engine,'d20',lambda e:20):
                    row=self.pass_move(mid,objects={'march/object':{'hit':True,'damage_before_dr':0 if status else 12}})
                    aoo.assert_not_called()
                self.assertEqual(self.rules.move(mid),original)
                self.assertEqual((self.p.pos,self.a.pos),((4,0),(4,0)))
                self.assertEqual(row['targets'],[['creature',self.enemy.entity_id],['object','march/object'],['creature',self.other.entity_id]])
                if status:
                    self.assertEqual([self.enemy.hp,self.other.hp],hp)
                    self.assertEqual((self.enemy.stages['def'],self.other.stages['def']),(-1,-1))
                else:self.assertTrue(all(c.hp<old for c,old in zip((self.enemy,self.other),hp)))
                self.assertEqual(self.e._physical_objects['march/object'][OBJECTS.FIELD]['hp'],30 if status else 23)
                self.assertEqual((self.p.budget['standard'],self.p.budget['shift'],self.p.move_uses[mid]),(0,0,1))
                self.assertEqual(M.shared_movement(self.e,self.p)[2]['used'],4)
                completion=self.e._move_completions[row['completion_id']]
                self.assertEqual(completion['phase'],'complete')
                self.assertEqual(completion['started'],[self.enemy.entity_id,self.other.entity_id])
                if family=='폭발':
                    self.assertEqual((self.enemy.stages['spe'],self.other.stages['spe']),(-1,-1))
                self.assertEqual(row['conversion']['order_id'],'march/order')
                self.assertIsNotNone(CM.current(self.e,self.p))
                if family=='폭발':
                    self.e.gm.snapshot('march/paid-pass')
                    self.e.gm.restore('march/paid-pass',reason='actual converted Pass historical restore')
                    self.restore()
                self.valid()

    def test_conversion_is_optional_and_ineligible_or_forged_public_paths_do_not_gain_it(self):
        self.setup();self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        mid='move/물대포'
        self.e.gm.set_move(self.p,mid,True,reason='GM observes this permanently learned Water Gun in the accepted scene')
        selected=self.rules.move(mid)
        self.assertEqual(selected['range'],'4, 대상 1')
        self.assertEqual((selected['_source']['file'],selected['_source']['record_span']),('db/moves.csv',[823,823]))
        self.assertIn(mid,self.p.spec['moves']);self.assertIn(mid,self.p.moves)
        self.e.gm.snapshot('march/valid-negative-control')
        with patch.object(Engine,'d20',lambda e:20):control=self.pass_move(FAMILY_MOVES['대시'],event='valid/control')
        self.assertEqual(self.e._move_completions[control['completion_id']]['phase'],'complete')
        self.assertEqual((self.p.pos,self.p.budget['standard']),((4,0),0))
        self.e.gm.restore('march/valid-negative-control',reason='restore actual valid scene before the specific-rule rejection')
        self.assertEqual(self.p.budget['standard'],1)
        assert_rejected_unchanged(self.e,lambda:self.pass_move(mid),
            reason_pattern=r'^converted Pass lost its selected eligible Move$')
        self.reject(lambda:self.pass_move(FAMILY_MOVES['파열'],event='wrong/source',objects={},destination=(5,0)))
        self.reject(lambda:self.e.use_pass_move(self.p,FAMILY_MOVES['파열'],(4,0),event_id='forged-source',
            range_source='gm/fake-conqueror',object_adjudications={},source='gm/observed',reason='actual observations'))
        before=deepcopy(self.rules.move(FAMILY_MOVES['원뿔']))
        self.assertNotIn('통과',before['range'])
        self.reject(lambda:self.e.use_pass_move(self.p,FAMILY_MOVES['원뿔'],(4,0),event_id='no-source',
            object_adjudications={},source='gm/observed',reason='actual observations'))
        # Choosing ordinary range still enters the existing native area producer.
        self.other.pos=(8,0)
        import move_completion as COMPLETE
        prior_completions=set(getattr(self.e,COMPLETE.KEY,{}))
        ordinary_definition=deepcopy(self.rules.move(FAMILY_MOVES['파열']))
        hp=self.enemy.hp;uses=self.p.move_uses.get(FAMILY_MOVES['파열'],0)
        with patch.object(Engine,'d20',lambda e:20):
            dealt=self.e.use_move_on(self.p,self.enemy,FAMILY_MOVES['파열'],self.e.everyone)
        completed=[row for key,row in getattr(self.e,COMPLETE.KEY,{}).items() if key not in prior_completions]
        self.assertEqual(len(completed),1)
        row=completed[0]
        self.assertEqual((row['phase'],row['sealed'],row['move_id']),('complete',True,FAMILY_MOVES['파열']))
        self.assertIs(row['actor'],self.p)
        self.assertIn(self.enemy,COMPLETE.actual_recipients(row))
        recipient=COMPLETE.recipient_result(row,self.enemy)
        self.assertTrue(recipient['hit']);self.assertFalse(recipient['cancelled'])
        self.assertGreater(dealt,0);self.assertLess(self.enemy.hp,hp)
        self.assertEqual((self.p.budget['standard'],self.p.move_uses[FAMILY_MOVES['파열']]),(0,uses+1))
        self.assertEqual(self.rules.move(FAMILY_MOVES['파열']),ordinary_definition)
        self.assertEqual(self.p.pos,(0,0));self.assertEqual(self.rules.move(FAMILY_MOVES['원뿔']),before)
        self.assertEqual(len(CM.live(self.p)),1);self.valid()

    def test_named_rejection_helper_requires_reason_and_detects_wrong_boundary_or_mutation(self):
        self.setup(acquire=False,mounted=False)
        called=[]
        for pattern in ('','  ',None):
            with self.subTest(pattern=pattern),self.assertRaisesRegex(ValueError,'explicit nonempty'):
                assert_rejected_unchanged(self.e,lambda:called.append(True),reason_pattern=pattern)
        self.assertEqual(called,[])
        before=self.snap();rng=self.e.rng.getstate()
        def wrong_body():
            prepare_body(self.e,self.p,size='소형',offsets=[(0,0)],reason='deliberately conflicting observed size')
        assert_rejected_unchanged(self.e,wrong_body,
            reason_pattern=r'existing size and actual body\.size observation disagree$')
        with self.assertRaisesRegex(AssertionError,'rejection reason did not match'):
            assert_rejected_unchanged(self.e,wrong_body,reason_pattern=r'^different rule prerequisite$')
        with self.assertRaisesRegex(AssertionError,'expected ValueError'):
            assert_rejected_unchanged(self.e,lambda:None,reason_pattern=r'^actual rejection$')
        self.assertEqual(self.snap(),before);self.assertEqual(self.e.rng.getstate(),rng)
        for mutation in ('state','rng'):
            with self.subTest(mutation=mutation):
                self.setup(acquire=False,mounted=False)
                hp,rng=self.p.hp,self.e.rng.getstate()
                def mutate_then_reject():
                    if mutation=='state':self.p.hp-=1
                    else:self.e.rng.random()
                    raise ValueError('actual rejection')
                with self.assertRaisesRegex(AssertionError,'changed engine state or RNG'):
                    assert_rejected_unchanged(self.e,mutate_then_reject,reason_pattern=r'^actual rejection$')
                if mutation=='state':self.assertEqual(self.p.hp,hp-1)
                else:self.assertNotEqual(self.e.rng.getstate(),rng)

    def test_current_mount_and_native_remaining_allowance_are_checked_when_used(self):
        for failure in ('dismounted','foreign','run-up-lost','spent-pool','endpoint'):
            with self.subTest(failure=failure):
                self.setup();self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
                if failure=='dismounted':self.e.dismount(self.a,destination=(0,1),reason='actual dismount before use')
                if failure=='foreign':self.p.spec['trainer_id']=self.enemy.entity_id
                if failure=='run-up-lost':G.revoke(self.p,'gm/native-run-up',engine=self.e)
                if failure=='spent-pool':
                    mount,policy,context=M.shared_movement(self.e,self.p)
                    M.record_movement(self.e,mount,policy,distance=context['allowance']-1,diagonals=context['diagonals'])
                self.reject(lambda:self.pass_move(FAMILY_MOVES['대시'],destination=(3,0) if failure=='endpoint' else (4,0)))

    def test_unmounted_order_becomes_usable_when_an_actual_other_rider_mounts(self):
        self.setup(mounted=False)
        self.e.gm.set_position(self.a,(0,1),reason='actual issuer stands beside the unmounted target')
        rider=Combatant(self.rules,dict(deepcopy(self.enemy.spec),id='march/independent-rider',
            name='actual allied rider',edges=['edge/탑승-기량']))
        self.e.gm.add_combatant(rider,pos=(0,0),side='party',reason='actual independent rider boards after the Order')
        prepare_body(self.e,rider,size='중형',offsets=[(0,0)],reason='observed independent Medium rider')
        self.start();self.e.start_of_turn(self.a);order=self.order()
        self.assertEqual(self.a.budget['standard'],0)
        self.assertEqual(len(CM.live(self.p)),1);self.assertIsNone(CM.current(self.e,self.p))
        self.e.end_of_turn(self.a);self.e.start_of_turn(rider)
        boarded=self.e.pokemon_activity(rider,'mounting',target=self.p,phase='mount',
            skill='육상',gm_mountable=True)
        self.assertTrue(boarded['passed']);self.assertEqual(rider.budget['standard'],0)
        self.assertEqual(list(M.mounted_pairs(self.p)),[(rider,self.p)])
        self.e.end_of_turn(rider);self.e.start_of_turn(self.p)
        self.assertEqual(CM.current(self.e,self.p),order)
        hp=(self.enemy.hp,self.other.hp)
        with patch.object(Engine,'d20',lambda e:20):row=self.pass_move(FAMILY_MOVES['대시'])
        self.assertEqual(row['conversion']['mounted_riders'],[rider.entity_id])
        self.assertEqual((self.p.pos,rider.pos,self.a.pos),((4,0),(4,0),(0,1)))
        completion=self.e._move_completions[row['completion_id']]
        self.assertEqual(completion['phase'],'complete')
        self.assertEqual(completion['started'],[self.enemy.entity_id,self.other.entity_id])
        self.assertTrue(all(actor.hp<before for actor,before in zip((self.enemy,self.other),hp)))
        self.assertEqual((self.p.budget['standard'],self.p.budget['shift']),(0,0))
        # The round permission remains; another Move still owes its own native actions.
        again=CM.conversion(self.e,self.p,self.rules.move(FAMILY_MOVES['원뿔']))
        self.assertEqual(again['order_id'],order['id'])
        self.assertEqual(again['mounted_riders'],[rider.entity_id])
        self.valid()

    def test_native_pass_replay_conflict_round_expiration_and_source_only_withdrawal(self):
        self.setup();self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
        with patch.object(Engine,'d20',lambda e:20):row=self.pass_move(FAMILY_MOVES['대시'])
        before=self.snap();self.assertEqual(self.pass_move(FAMILY_MOVES['대시']),row);self.assertEqual(self.snap(),before)
        self.reject(lambda:self.pass_move(FAMILY_MOVES['원뿔']))
        self.e.end_of_turn(self.p);self.close(self.enemy);self.close(self.other);self.e.end_round()
        self.assertEqual(CM.live(self.p),[]);self.restore();self.valid()
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p)
        self.reject(lambda:self.pass_move(FAMILY_MOVES['원뿔'],event='next-round'))
        self.setup();self.start();self.order()
        TIME.install(self.e,self.p,{'source':'gm/independent','round_end_deadline':self.e.round_no,'damage_reduction':2})
        speed=self.a.stats['spe']
        helper=BASE.RideAsOneTests();helper.e,helper.a=self.e,self.a
        helper.retrain(CM.FEATURE)
        self.assertEqual(CM.live(self.p),[])
        self.assertEqual(self.a.stats['spe'],speed-1)
        self.assertTrue(any(r['source']=='gm/independent' for r in TIME.records(self.p)));self.valid()

    def test_late_native_hit_failure_rolls_back_movement_mount_pool_costs_object_damage_and_rng(self):
        for recipient in ('object','reactive-creature'):
            with self.subTest(recipient=recipient):
                self.setup()
                if recipient=='reactive-creature':
                    self.e.gm.set_ability(self.enemy,'변색',reason='actual late rollback recipient Ability')
                    self.e.choose_reactive_ability(self.enemy,'ability/변색',reason='actual first recipient reaction choice')
                self.start();self.order();self.close(self.a);self.e.start_of_turn(self.p)
                objects={}
                if recipient=='object':
                    W.register_object(self.e,'march/object',location={'kind':'grid','cell':(2,0)},reason='real object before late failure')
                    self.e.configure_object_durability(self.a,'march/object',max_hp=30,reduction=5,minimum_damage=0,
                        source='gm/observed-durability',reason='actual ordinary object')
                    objects={'march/object':{'hit':True,'damage_before_dr':12}}
                original=Engine._apply_move_recipient;hit_calls=[]
                def fail(e,actor,target,mid,*args,**kw):
                    hit_calls.append(target.entity_id)
                    precision=args[7]
                    if precision is not None:
                        copied=G._stage_transition_payload(e,e,{'actual':precision,'lookalike':dict(precision)})
                        self.assertIs(copied['actual'],precision)
                        self.assertIsNot(copied['lookalike'],precision)
                    result=original(e,actor,target,mid,*args,**kw)
                    if target.entity_id==self.other.entity_id:
                        if recipient=='reactive-creature':
                            self.assertEqual(W.actor_index(e)[self.enemy.entity_id].types,[e.r.move(mid)['type']])
                        raise ValueError('actual late native recipient failure')
                    return result
                with patch.object(Engine,'_apply_move_recipient',fail),patch.object(Engine,'d20',lambda e:20):
                    self.reject(lambda:self.pass_move(FAMILY_MOVES['대시'],objects=objects))
                self.assertEqual(hit_calls,[self.enemy.entity_id,self.other.entity_id])
                self.assertEqual((self.a.pos,self.p.pos),((0,0),(0,0)));self.valid()


if __name__=='__main__':unittest.main()
