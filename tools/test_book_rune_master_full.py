"""Rune-specific acquired sources and real native producers/consumers."""
from copy import deepcopy
from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from rune_master_fixture import RuneFixture
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import rune_master as R,trainer_feature_acquisition as T,acquired_features as A
import state_grants as G,world_entities as W,action_points as AP,csv_item_capability_contracts as CAP
import special_entities as SPECIAL,temporary_ap as TEMP
import state_codec as CODEC,resolution_transaction as TX


class RuneMasterFullTests(RuneFixture,unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='fantasy')
    def setUp(self):self.scene()

    def test_exact_class_alias_and_actual_acquisition_not_imported_feat_authority(self):
        self.assertEqual([r['source_id'] for r in A.class_instances(self.a)],[R.CLASS])
        self.assertEqual(A.owned_rule_count(self.a,R.CLASS),1)
        self.assertNotIn(R.CLASS,[r['source_id'] for r in A.feature_instances(self.a)])
        self.assertNotIn(R.CLASS,A._names(self.a,'supp-fantasy/'))
        self.assertEqual(G.effective(self.a,'capabilities').count(R.GATHER),1)
        for u in self.unown:self.assertIn(R.PRESS,G.effective(u,'capabilities'))
        self.assertEqual(self.acquire(R.CLASS),self.acquire(R.CLASS))
        self.rejected(lambda:self.acquire(R.CLASS,request='duplicate/class'))
        later=Combatant(self.rules,build_pokemon(self.rules,'안농',20,moves=[],abilities=[],
            extra={'id':'pokemon/later-owned','trainer_id':self.a.entity_id}))
        self.e.gm.add_combatant(later,pos=(9,2),side='party',reason='actual later registered owned Unown')
        sid=next(sid for sid,row in G.state(later)['sources'].items() if R.PRESS in row.get('grants',{}).get('capabilities',[]) and row.get('rule_id')==R.CLASS)
        self.restore();later=W.actor_index(self.e)['pokemon/later-owned']
        self.assertEqual(G.state(later)['sources'][sid]['owner_id'],self.a.entity_id)
        self.e.pokemon_activity(self.a,'party_policy',mode='unlimited',roster=[*self.unown,later],reason='actual complete old owned roster')
        self.e.pokemon_activity(self.b,'party_policy',mode='unlimited',roster=[],reason='actual receiving Trainer roster')
        self.e.pokemon_activity(self.a,'party_transfer',target=later,new_owner=self.b,reason='actual ownership transfer away from Rune Master',request_id='rune/actual-transfer')
        self.assertNotIn(sid,later.spec.get(G.KEY,{}).get('sources',{}))
        self.scene(acquire=False);self.acquire(R.CLASS)
        sid=next(sid for sid,row in G.state(self.a)['sources'].items() if row.get('static_acquisition',{}).get('feature_id')==R.CLASS)
        def withdraw(e,a):
            G.revoke(a,sid,engine=e);a.spec['feats'].remove(R.CLASS)
        G.transition(self.e,self.a,withdraw)
        for u in self.unown:self.assertNotIn(sid,u.spec.get(G.KEY,{}).get('sources',{}))
        self.scene(acquire=False);self.a.spec['feats']=[R.CLASS,R.POWER]
        self.rejected(lambda:R.use_power(self.e,self.a,self.b,[self.b],damage_class='물리'))

    def test_prerequisites_four_slots_and_selected_csv_sentry_parent(self):
        self.scene(acquire=False,occult=2);self.rejected(lambda:self.acquire(R.CLASS))
        self.a.spec['skills']['오컬트학']=5
        for u in self.unown[1:]:u.spec.pop('trainer_id')
        self.rejected(lambda:self.acquire(R.CLASS))
        self.scene(acquire=False);self.a.spec['classes']=['class/운동선수','class/멘토','class/지휘관','class/코디네이터']
        self.rejected(lambda:self.acquire(R.CLASS))
        self.scene(edition='local_csv',acquire=False)
        for uid in (R.CLASS,R.POWER,R.GLYPH):self.acquire(uid)
        self.rejected(lambda:self.acquire(R.SENTRY))
        self.acquire(R.EXPLOSIVE);out=self.acquire(R.SENTRY)
        self.assertEqual(out['snapshot']['source']['row'],558)
        self.assertEqual({r['feature_id'] for r in R.records(self.a) if r['request_id'] in out['snapshot']['parents']},{R.EXPLOSIVE,R.POWER})
        for uid in R.FEATURES:self.assertNotEqual(R.source(self.rules,uid,'supplement'),R.source(self.rules,uid,'local_csv'))
        self.acquire(R.REWRITE);rewritten=R.rewrite(self.e,self.a,self.a,move_id=R.HP,fixed_d20=[20,19])
        self.assertEqual(rewritten['types'],{R.HP:'에러'})

    def test_class_gather_real_week_native_standard_unowned_sheet_and_restore(self):
        self.combat();out=CAP.summon_unown(self.e,self.a,entity_id='pokemon/summoned',
            selection={'species_id':'pokemon/안농','form':'Z','reason':'GM observes random form Z'},
            location={'kind':'grid','cell':[1,3]},side='independent',side_reason='GM sees independent allegiance',fixed_d8=[8,8])
        u=out['pokemon'];self.assertEqual(u.level,16);self.assertTrue(u.spec['wild']);self.assertNotIn('trainer_id',u.spec)
        self.assertIs(W.actor_index(self.e)[u.entity_id],u);self.assertEqual(self.a.budget['standard'],0)
        self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0);self.restore()
        self.rejected(lambda:CAP.summon_unown(self.e,self.a,entity_id='pokemon/too-soon',
            selection={'species_id':'pokemon/안농','form':'A','reason':'GM observes form A'},
            location={'kind':'grid','cell':[1,3]},side='independent',side_reason='actual independent side',fixed_d8=[1,1]))
        u=W.actor_index(self.e)['pokemon/summoned']
        self.e.gm.set_position(self.a,(20,6),reason='actual Rune Master physically at pressing surface')
        self.e.gm.set_position(u,(21,7),reason='actual independently summoned Unown pressed against surface')
        R.create_glyph(self.e,self.a,u,glyph_id='glyph/wild-summoned',surface_id='surface/wall',visible=False,
            seconds=3,flat_surface=True,contact=True,gm_id='gm/actual',reason='GM observes actual non-Prime wild summoned Unown pressed to wall')
        self.assertFalse(u.on_field);self.assertTrue(u.spec['wild']);self.assertNotIn('trainer_id',u.spec)

    def test_low_level_class_gather_uses_twenty_level_cap_in_both_editions_and_preserves_receipts(self):
        for edition in ('supplement','local_csv'):
            with self.subTest(edition=edition):
                self.scene(edition=edition,acquire=False,trainer_level=12)
                self.acquire(R.CLASS)
                self.assertEqual(self.a.level,12)
                self.assertEqual([row['feature_id'] for row in R.records(self.a)],[R.CLASS])
                self.assertEqual(R.acquired(self.a)['snapshot']['source'],R.source(self.rules,R.CLASS,edition))
                self.assertTrue(R.gather_authorized(self.e,self.a))
                self.combat();self.assertEqual(self.a.budget['standard'],1)
                out=CAP.summon_unown(self.e,self.a,entity_id='pokemon/low-level-summoned',
                    selection={'species_id':'pokemon/안농','form':'Z','reason':'GM observes actual random form Z'},
                    location={'kind':'grid','cell':[1,3]},side='independent',side_reason='GM observes independent allegiance',fixed_d8=[8,8])
                u=out['pokemon'];self.assertTrue(out['summoned']);self.assertEqual(u.level,16)
                self.assertIs(W.actor_index(self.e)[u.entity_id],u);self.assertEqual(self.a.budget['standard'],0)
                self.assertTrue(u.spec['wild']);self.assertFalse(u.captured);self.assertNotIn('trainer_id',u.spec)
                self.assertEqual(u.side,'independent');self.assertNotIn(u.entity_id,self.a.spec.get('pokemon_registry',{}))
                self.assertEqual((out['receipt']['d8'],out['receipt']['level']),([8,8],16))
                self.assertEqual(u.spec['gather_unown_origin']['summoner_id'],self.a.entity_id)
                self.assertEqual(u.spec['gather_unown_origin']['selection'],out['receipt']['selection'])
                self.assertEqual(CAP._unown_receipts(self.a),[out['receipt']])
                self.assertTrue(CAP.validate_world(self.e,W.actor_index(self.e)))
                self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0);self.restore()
                u=W.actor_index(self.e)['pokemon/low-level-summoned']
                self.assertEqual((self.a.level,u.level),(12,16));self.assertNotIn('trainer_id',u.spec)
                self.assertTrue(u.spec['wild']);self.assertFalse(u.captured);self.assertEqual(u.side,'independent')
                self.assertEqual(CAP._unown_receipts(self.a),[out['receipt']])
                baseline=self.e.export_state();rng=self.e.rng.getstate();damaged=deepcopy(baseline)
                receipt=deepcopy(out['receipt']);receipt['level']=self.a.level
                receipt['sha256']=TX.request_fingerprint({key:value for key,value in receipt.items() if key!='sha256'})
                encoded,=[node['items'] for node in damaged['nodes'].values()
                    if node['kind']=='dict' and ['kind',CAP.UNOWN_SUMMON] in node['items']]
                for pair in encoded:
                    if pair[0] in ('level','sha256'):pair[1]=receipt[pair[0]]
                unchanged=deepcopy(damaged)
                with self.assertRaisesRegex(CODEC.StateCodecError,'summoned level must match the actual 2d8 roll'):
                    CODEC.load_engine(self.rules,damaged)
                self.assertEqual(damaged,unchanged);self.assertEqual(self.e.export_state(),baseline)
                self.assertEqual(self.e.rng.getstate(),rng);self.assertIs(W.actor_index(self.e)[self.a.entity_id],self.a)
                self.e.advance_time(604799,[])
                assert_rejected_unchanged(self.e,lambda:CAP.summon_unown(self.e,self.a,entity_id='pokemon/low-level-too-soon',
                    selection={'species_id':'pokemon/안농','form':'A','reason':'GM observes actual random form A'},
                    location={'kind':'grid','cell':[1,3]},side='independent',side_reason='actual independent allegiance',fixed_d8=[8,8]),
                    reason_pattern='actual week is spent')
                self.e.advance_time(1,[]);self.combat();self.assertEqual(self.a.budget['standard'],1)
                second=CAP.summon_unown(self.e,self.a,entity_id='pokemon/low-level-next-week',
                    selection={'species_id':'pokemon/안농','form':'A','reason':'GM observes actual random form A'},
                    location={'kind':'grid','cell':[1,4]},side='independent',side_reason='actual independent allegiance',fixed_d8=[8,8])
                self.assertTrue(second['summoned']);self.assertEqual(second['pokemon'].level,16)
                self.assertEqual(self.a.budget['standard'],0);self.assertNotIn('trainer_id',second['pokemon'].spec)
                self.assertEqual(second['receipt']['at']-out['receipt']['at'],604800)
                self.assertEqual(CAP._unown_receipts(self.a),[out['receipt'],second['receipt']])

    def test_hidden_power_native_physical_special_damage_and_shapes_stab(self):
        self.e.gm.set_position(self.b,(2,1),reason='actual adjacent target');self.combat()
        with patch.object(Engine,'d20',return_value=15):physical=R.use_power(self.e,self.a,self.b,[self.b],damage_class='물리')
        self.assertGreater(physical,0);self.assertEqual(self.a.move_uses[R.HP],1)
        self.assertTrue(R.grants_stab(self.e,self.a,self.rules.move(R.HP)))
        self.next_round()
        self.assertFalse(__import__('frequency').move_allowed(self.e,self.a,R.HP)[0])
        self.next_round()
        with patch.object(Engine,'d20',return_value=15):special=R.use_power(self.e,self.a,self.b,[self.b],damage_class='특수',shape='ranged')
        self.assertGreater(special,0)
        for shape,expected in (('melee','근접'),('ranged','6'),('cone','원뿔'),('burst','파열')):
            with R._using(self.e,self.a,R.HP,'물리',shape):self.assertIn(expected,R.prepare(self.e,self.a,self.rules.move(R.HP))['range'])

    def test_words_owned_pokemon_native_command_and_nonprime_has_no_extra_stab(self):
        p=self.unown[0];self.e.gm.set_move(p,R.HP,reason='actual own Pokemon learned Hidden Power')
        p.spec['hidden_power_type']='물'  # Actual prior generic HP type observation.
        self.e.gm.set_position(p,(17,8),reason='actual ranged own Pokemon');self.combat(p)
        with patch.object(Engine,'d20',return_value=15):out=R.use_power(self.e,p,self.b,[self.b],damage_class='특수',shape='ranged',trainer=self.a)
        self.assertEqual(out['status'],'submitted');self.assertGreater(out['move_result'],0)
        self.assertFalse(R.grants_stab(self.e,p,self.rules.move(R.HP)));self.assertEqual(p.budget['standard'],0)

    def test_rewrite_actual_daily_instance_type_and_unown_letter_restore(self):
        p=self.unown[0];self.e.gm.set_move(p,R.HP,reason='actual Rewrite target learned Hidden Power')
        out=R.rewrite(self.e,self.a,p,move_id=R.HP,letter='Z',fixed_d20=[20,18])
        self.assertEqual(out['types'],{R.HP:'물'});self.assertEqual(p.spec['unown_letter'],'Z')
        self.rejected(lambda:R.rewrite(self.e,self.a,self.a,fixed_d20=[7]))
        self.restore();self.assertEqual(R._power_type(self.unown[0],R.HP),'물');self.assertEqual(self.unown[0].spec['unown_letter'],'Z')

    def test_glyph_extended_surface_channel_perception_voice_and_permanent_loss(self):
        self.glyph();row=self.e._physical_objects['glyph/0'];self.assertEqual(row['max_hp'],self.a.level)
        self.assertEqual(row['hp'],self.a.level);self.assertNotIn('stats',row);self.assertFalse(row['visible'])
        self.assertEqual(self.e.elapsed_seconds,3);self.assertFalse(self.unown[0].on_field)
        self.combat();R.channel(self.e,self.a,'glyph/0');self.assertTrue(row['visible'])
        fact=R.observe_glyph(self.e,self.a,'glyph/0',sights=['actual distant book'],sounds=['actual footsteps'],gm_id='gm/actual',reason='GM observes wall viewpoint')
        self.assertEqual(fact['location'],row['location']);self.assertEqual(R.speak(self.e,self.a,'glyph/0','actual projected words')['origin'],row['location'])
        self.rejected(lambda:self.e.start_of_turn(self.unown[0]))
        R.end_glyph(self.e,self.a,'glyph/0',deactivate=True);self.assertEqual(row['status'],'deactivated')
        self.rejected(lambda:SPECIAL.require_prime_independent(self.e,self.unown[0]));self.restore()
        self.rejected(lambda:SPECIAL.require_prime_independent(self.e,self.unown[0]))

    def test_glyph_creator_growth_preserves_damaged_creation_state_through_native_restore(self):
        self.glyph();created=deepcopy(self.e._physical_objects['glyph/0'])
        self.assertEqual((created['creation_level'],created['level'],created['max_hp'],created['hp']),(40,40,40,40))
        R.end_glyph(self.e,self.a,'glyph/0',damage=7)
        damaged=deepcopy(self.e._physical_objects['glyph/0'])
        self.assertEqual(damaged,dict(created,hp=33))
        self.e.gm.set_level(self.a,41,reason='actual creator growth after a damaged Glyph was placed')
        self.assertEqual(self.a.level,41)
        self.assertEqual(self.e._physical_objects['glyph/0'],damaged)
        self.assertEqual(SPECIAL.view(self.e,'glyph/0')['state_view']['unresolved'],[])
        self.e.gm.snapshot('glyph-growth')
        R.end_glyph(self.e,self.a,'glyph/0',damage=2)
        self.e.gm.set_level(self.a,42,reason='later actual creator growth before restoring the snapshot')
        self.assertEqual(self.e._physical_objects['glyph/0'],dict(damaged,hp=31))
        self.e.gm.restore('glyph-growth',reason='restore actual damaged Glyph and creator growth together')
        self.assertEqual(self.a.level,41)
        self.assertEqual(self.e._physical_objects['glyph/0'],damaged)
        self.restore()
        self.assertEqual(self.a.level,41)
        self.assertEqual(self.e._physical_objects['glyph/0'],damaged)
        self.assertEqual(SPECIAL.view(self.e,'glyph/0')['state_view']['unresolved'],[])
        self.assertFalse(self.unown[0].on_field)
        self.rejected(lambda:SPECIAL.require_prime_independent(self.e,self.unown[0]))
        changed=deepcopy(damaged)
        changed.update(creation_level=41,level=41,max_hp=41)
        self.rejected(lambda:SPECIAL.observe(self.e,changed,reason='creator growth cannot rewrite a Glyph creation snapshot'))
        # U-009 prevents growth healing, not a separately observed current-HP change.
        healed=dict(damaged,hp=34)
        SPECIAL.observe(self.e,healed,reason='GM observes separate recovery of one point of actual Glyph damage')
        self.assertEqual(SPECIAL.view(self.e,'glyph/0')['entity']['hp'],34)
        self.assertEqual(tuple(self.e._physical_objects['glyph/0'][key] for key in ('creation_level','level','max_hp')),(40,40,40))
        self.glyph(1)
        self.assertEqual(tuple(self.e._physical_objects['glyph/1'][key] for key in ('creation_level','level','max_hp','hp')),(41,41,41,41))
        # The separate printed Sentry activation uses the creator's current level.
        self.combat()
        out=R.sentry(self.e,self.a,'glyph/0',entity_id='pokemon/growth-sentry',investment=self.investment())
        sentry=W.actor_index(self.e)[out['actor_id']]
        prepare_body(self.e,sentry,size=sentry.spec['size'],offsets=[(0,0)],reason='actual post-growth Sentry body')
        self.assertEqual((sentry.level,self.e._physical_objects['glyph/0']['level']),(41,40))
        self.assertEqual(self.e._physical_objects['glyph/0']['hp'],34)
        self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0)
        self.assertFalse(sentry.on_field)
        self.assertEqual(self.e._physical_objects['glyph/0']['status'],'destroyed')
        self.restore()
        self.rejected(lambda:SPECIAL.require_prime_independent(self.e,self.unown[0]))

    def test_glyph_cap_remote_explosive_exact_ap_standard_damage_and_minute_glow(self):
        self.glyph()
        second=Combatant(self.rules,build_trainer(self.rules,'actual second remote target',40,
            {'hp':100,'atk':10,'def':5,'spa':10,'spd':5,'spe':10},moves=[],abilities=[],
            extra={'id':'trainer/second-rune-target','movement':{'land':6},'size':'중형'}))
        self.e.gm.add_combatant(second,pos=(19,7),side='foe',reason='actual second Glyph-burst recipient')
        prepare_body(self.e,second,size='중형',offsets=[(0,0)],reason='GM observed complete second target body')
        self.combat();before=(self.b.hp,second.hp);available=AP.available(self.a)
        with patch.object(Engine,'d20',return_value=15) as accuracy:
            dealt=R.explosive(self.e,self.a,'glyph/0',self.b,[self.b,second])
        self.assertGreater(dealt,0);self.assertLess(self.b.hp,before[0]);self.assertLess(second.hp,before[1])
        self.assertEqual(accuracy.call_count,1);self.assertEqual(AP.available(self.a),available-1)
        self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.move_uses[R.HP],1)
        self.assertTrue(R.glyph_view(self.e,self.a,'glyph/0')['glowing']);self.assertTrue(self.e._physical_objects['glyph/0']['visible'])
        self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0);self.e.advance_time(60)
        self.assertFalse(R.glyph_view(self.e,self.a,'glyph/0')['glowing'])
        for n in range(1,5):self.glyph(n)
        self.e.gm.set_position(self.a,(20,6),reason='actual creator at wall for attempted sixth Glyph')
        self.e.gm.set_position(self.unown[5],(21,7),reason='actual sixth Unown at wall')
        self.rejected(lambda:R.create_glyph(self.e,self.a,self.unown[5],glyph_id='glyph/5',surface_id='surface/wall',
            visible=False,seconds=3,flat_surface=True,contact=True,gm_id='gm/actual',reason='actual attempted sixth pressing at full Occult capacity'))

    def test_sentry_real_single_copied_power_commandless_five_minute_expiry(self):
        self.glyph();self.combat();out=R.sentry(self.e,self.a,'glyph/0',entity_id='pokemon/sentry',investment=self.investment())
        p=W.actor_index(self.e)[out['actor_id']];prepare_body(self.e,p,size=p.spec['size'],offsets=[(0,0)],reason='actual sentry Unown body')
        self.assertEqual(p.moves,[R.HP]);self.assertNotIn('trainer_id',p.spec);self.assertEqual(p.level,self.a.level)
        self.assertEqual(R._power_type(p,R.HP),R._power_type(self.a,R.HP))
        self.e.end_of_turn(self.a);self.e.start_of_turn(p,initiative_count=10)
        with patch.object(Engine,'d20',return_value=15):self.assertGreater(R.sentry_attack(self.e,p,self.b,[self.b]),0)
        self.e.end_of_turn(p);self.e.end_round();self.assertTrue(self.e.encounter_active)
        remaining=self.e._physical_objects[out['sentry_id']]['created_at']+300-self.e.elapsed_seconds
        self.assertGreater(remaining,0)
        self.e.advance_time(remaining-1);self.assertTrue(p.on_field)
        self.e.advance_time(1);self.assertFalse(p.on_field);self.assertEqual(self.e._physical_objects['glyph/0']['status'],'destroyed')

    def test_alarm_gm_truth_distance_warnings_one_auto_explosive_per_round(self):
        self.glyph();self.glyph(1);self.combat();options={'target_id':self.b.entity_id,'target_ids':[self.b.entity_id]}
        R.alarm(self.e,self.a,'glyph/0',trigger='arbitrary actual GM trigger',automatic='explosive',options=options)
        self.next_round();R.alarm(self.e,self.a,'glyph/1',trigger='second arbitrary trigger',automatic='explosive',options=options)
        ap=AP.available(self.a);spent=self.a.spec.get('ap_spent',0)
        self.assertFalse(R.observe_alarm(self.e,self.a,'glyph/0',fulfilled=True,distance_m=31,gm_id='gm/actual',reason='observed outside radius')['triggered'])
        with patch.object(Engine,'d20',return_value=15):first=R.observe_alarm(self.e,self.a,'glyph/0',fulfilled=True,distance_m=30,gm_id='gm/actual',reason='observed actual trigger')
        self.assertTrue(first['audible_warning']);self.assertEqual(first['mental_warning_to'],self.a.entity_id);self.assertGreater(first['automatic'],0)
        second=R.observe_alarm(self.e,self.a,'glyph/1',fulfilled=True,distance_m=1,gm_id='gm/actual',reason='observed same-round trigger')
        self.assertEqual(second['waiting'],'one_explosive_glyph_per_round');self.assertEqual(AP.available(self.a),ap);self.assertEqual(self.a.spec.get('ap_spent',0),spent)

    def test_alarm_sentry_queue_recheck_encounter_end_exact_binding_release(self):
        self.glyph();self.glyph(1);self.combat()
        for n in (0,1):
            if n:self.next_round()
            R.alarm(self.e,self.a,'glyph/'+str(n),trigger='explicit trigger',automatic='sentry',options={'entity_id':'pokemon/sentry/'+str(n),'investment':self.investment()})
        R.observe_alarm(self.e,self.a,'glyph/0',fulfilled=True,distance_m=0,gm_id='gm/actual',reason='GM sees first trigger')
        waiting=R.observe_alarm(self.e,self.a,'glyph/1',fulfilled=True,distance_m=0,gm_id='gm/actual',reason='GM sees simultaneous trigger')
        self.assertEqual(waiting['waiting'],'one_active_sentry')
        self.e.end_of_turn(self.a);self.e.end_encounter(round_elapsed_seconds=0)
        self.assertNotIn('glyph/0',R.alarms(self.a));self.assertIn('glyph/1',R.alarms(self.a))
        self.assertFalse(R.observe_alarm(self.e,self.a,'glyph/1',fulfilled=False,distance_m=0,gm_id='gm/actual',reason='GM rechecks and trigger no longer true')['triggered'])
        result=R.observe_alarm(self.e,self.a,'glyph/1',fulfilled=True,distance_m=0,gm_id='gm/actual',reason='GM observes trigger newly true again')
        self.assertIn('sentry_id',result['automatic'])

    def test_temporary_funding_expiry_ends_same_alarm_only_manual_end_idempotent(self):
        import moment_of_action as M
        self.glyph();self.glyph(1)
        issuer=Combatant(self.rules,build_trainer(self.rules,'actual allied Cheerleader',40,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],abilities=[],
            extra={'id':'trainer/cheer','skills':{'매력':3,'명령':3},'classes':[],'feats':[],'movement':{'land':6},'size':'중형'}))
        self.e.gm.add_combatant(issuer,pos=(2,1),side='party',reason='actual allied temporary AP producer')
        prepare_body(self.e,issuer,size='중형',offsets=[(0,0)],reason='actual Cheerleader body')
        for uid in (M.TRAINING,M.CLASS,M.FEATURE):T.acquire_static(self.e,issuer,uid,acquisition_request_id='cheer/'+uid)
        self.e.gm.observe_sensory_environment(issuer,self.a,paths={'auditory':True},present=True,reason='actual audible allied instruction')
        funding={'priority':'temporary_first','binding_expiry':'end_effect','reason':'GM explicitly chooses end alarm on funding loss'}
        self.e.moment_of_action(issuer,[self.a],funding={self.a.entity_id:funding},allies={self.a.entity_id:{'allied':True,'reason':'actual allied relationship'}})
        self.assertEqual(TEMP.available(self.a),1)
        first=R.alarm(self.e,self.a,'glyph/0',trigger='temporary funded alarm');second=R.alarm(self.e,self.a,'glyph/1',trigger='other ordinary funded alarm')
        self.restore();self.e.advance_time(10)
        self.assertNotIn(first['id'],self.a.spec['ap_bound']);self.assertEqual(self.a.spec['ap_bound'][second['id']],1)
        self.assertNotIn('glyph/0',R.alarms(self.a));self.assertIn('glyph/1',R.alarms(self.a))
        self.assertFalse(R.stop_alarm(self.e,self.a,'glyph/0'))
        self.assertTrue(R.stop_alarm(self.e,self.a,'glyph/1'));self.assertFalse(R.stop_alarm(self.e,self.a,'glyph/1'))
        self.assertFalse(self.a.spec['ap_bound'])

    def test_source_revoke_and_terminal_gm_glyph_observation_end_exact_alarm(self):
        self.glyph();first=R.alarm(self.e,self.a,'glyph/0',trigger='actual alarm before terminal observation')
        row=dict(self.e._physical_objects['glyph/0'],status='deactivated',channeling=False)
        SPECIAL.observe(self.e,row,reason='GM observes the actual Glyph intentionally deactivated')
        self.assertNotIn(first['id'],self.a.spec['ap_bound'])
        self.glyph(1);second=R.alarm(self.e,self.a,'glyph/1',trigger='actual alarm before source withdrawal')
        sid=next(sid for sid,row in G.state(self.a)['sources'].items() if row.get('static_acquisition',{}).get('feature_id')==R.ALARM)
        def withdraw(e,a):
            G.revoke(a,sid,engine=e);a.spec['feats'].remove(R.ALARM)
        G.transition(self.e,self.a,withdraw)
        self.assertNotIn(second['id'],self.a.spec['ap_bound']);self.assertNotIn(sid,G.state(self.a)['sources'])

    def test_nonrune_native_base_stats_moves_and_typeace_empty_path_are_unchanged(self):
        import pokemon_move_edges as P,type_ace as TA,environ_moves as ENV
        move=self.rules.move('move/물대포');stats=dict(self.b.stats);base=dict(self.b.spec['stats'])
        self.assertEqual(R.prepare(self.e,self.b,move),move)
        self.assertIs(R.range_actor(self.e,self.b,move),self.b)
        self.assertFalse(R.grants_stab(self.e,self.b,move));self.assertIsNone(TA.scope(self.e,self.b,move))
        self.assertEqual(P.prepare(self.e,self.b,move),move)
        mm,_=self.rules.move_mech(move['id']);self.assertEqual(R.mechanics(self.e,self.b,move,mm),mm)
        self.e.gm.set_move(self.b,move['id'],reason='actual non-Rune learned basic Move')
        self.e.gm.set_position(self.b,(3,1),reason='actual non-Rune within native basic Move range')
        self.combat(self.b)
        with patch.object(Engine,'d20',return_value=15):self.assertGreater(self.e.use_move_on(self.b,self.a,move['id'],[self.a]),0)
        self.assertEqual(self.b.stats,stats);self.assertEqual(self.b.spec['stats'],base)


if __name__=='__main__':unittest.main()
