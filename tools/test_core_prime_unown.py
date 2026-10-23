"""Letter Press's existing state owner through actual native consumers."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
from unittest.mock import patch
STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine')]
from engine import Engine,Rules,Combatant
from builder import build_pokemon,build_trainer
from grid import Grid
import special_entities as S
import state_grants as G
import growth_stats as GROWTH
import world_entities as W
import pokemon_party as PARTY
import party_actions as COMMAND
import turn as TURN
import frequency as FREQ
import move_state as MOVES
import state_codec as CODEC


class CorePrimeUnownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def fixture(self,n=4,*,generic=False,owned=False):
        e=Engine(self.r,seed=68070);e.grid=Grid(24,16)
        a=Combatant(self.r,build_trainer(self.r,'trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),items={'몬스터볼':3},pos=(0,0)))
        actors=[]
        for number in range(n+1):
            moves=['move/잠재파워' if generic else 'move/잠재파워-불꽃']
            if number==0:moves+=['move/몸통박치기']
            spec=build_pokemon(self.r,'안농',20,name='unown-'+str(number),moves=moves,wild=not owned,pos=(2+number,2))
            if owned:spec['trainer_id']=a.entity_id
            c=Combatant(self.r,spec);c.side='party';c.on_field=number==0;actors.append(c)
        target=Combatant(self.r,build_pokemon(self.r,'파오리',50,name='target',moves=['move/몸통박치기'],wild=True,pos=(3,2)))
        target.side='wild'
        e.everyone=e.gm.everyone=[a,*actors,target]
        row=dict(id='prime-state',kind='prime_unown',location={'kind':'unknown'},creator_id=actors[0].entity_id,
            actor_id=actors[0].entity_id,joined=[])
        for k,c in enumerate(actors[1:]):
            part={'member_id':c.entity_id,'boosted_stat':('hp','atk','spa','spe')[k],
                'hidden_power_id':c.moves[0],'damage_class':'physical' if k%2==0 else 'special'}
            if generic:part['hidden_power_type']=('물','풀','얼음','전기')[k]
            row['joined'].append(part)
        return e,a,actors[0],actors[1:],target,row

    def observe(self,e,row):return S.observe(e,row,reason='observed actual permanent Letter Press combination')

    def begin(self,e,c):
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
        if not e.encounter_active:e.start_round([x for x in e.everyone if x.on_field])
        e.start_of_turn(c,initiative_count=20)

    def valid(self,e):
        out=e.validate_state();self.assertTrue(out['valid'],out['issues'])

    def test_all_four_additions_use_sourced_base_and_preserve_actual_investment_hp_and_identity(self):
        e,a,h,m,t,row=self.fixture()
        before=GROWTH.project_actor(e,h);identity=id(h);oldhp=h.hp
        first=deepcopy(row);first['joined']=first['joined'][:1]
        out=self.observe(e,first)
        self.assertEqual(out['state_view']['base_stat_bonuses']['hp'],5)
        self.assertEqual(h.stats['hp'],before['effective_stats']['hp']+5)
        self.assertEqual(h.hp,oldhp)
        self.observe(e,row)
        after=GROWTH.project_actor(e,h)
        self.assertEqual(after['permanent']['investment'],before['permanent']['investment'])
        self.assertEqual({s:after['effective_stats'][s]-before['effective_stats'][s] for s in h.stats},dict(hp=5,atk=5,**{'def':0},spa=5,spd=0,spe=5))
        self.assertEqual(sum(after['permanent']['investment'].values()),sum(before['permanent']['investment'].values()))
        self.assertIs(W.actor_index(e)[h.entity_id],h);self.assertEqual(id(h),identity)
        self.assertEqual(len(h.spec['allocation_migrations']),2)
        self.assertEqual(after['permanent']['species_base'],before['permanent']['species_base'])
        count=len(h.spec['allocation_migrations']);self.observe(e,row)
        self.assertEqual(len(h.spec['allocation_migrations']),count)
        self.valid(e)

    def test_same_base_hidden_powers_are_distinct_native_physical_special_type_and_frequency(self):
        e,a,h,m,t,row=self.fixture(2,generic=True)
        host_before=list(h.moves);member_before=deepcopy([(x.spec,x.move_uses) for x in m])
        catalog=deepcopy((e.r.moves,e.r.moves_mech))
        self.observe(e,row);ids=S.prime_moves(e.r,h.spec[S.PRIME_KEY])
        self.assertEqual(len(set(ids)),2);self.assertTrue(set(host_before)<=set(h.moves))
        self.assertEqual([e.r.move(x)['class'] for x in ids],['물리','특수'])
        self.assertEqual([e.r.move(x)['type'] for x in ids],['물','풀'])
        self.assertEqual(e.r.move_mech(ids[0]),e.r.move_mech('move/잠재파워'))
        self.assertEqual(MOVES.describe(e.r,h.spec,moves=h.moves)['slot_count'],2)
        for member,(oldspec,uses) in zip(m,member_before):
            self.assertEqual(member.spec,{**oldspec,S.PRIME_MEMBER:{'record_id':row['id'],'host_id':h.entity_id}})
            self.assertEqual(member.move_uses,uses)
        self.begin(e,h)
        before=t.hp;budget=deepcopy(h.budget)
        e.use_move(h,t,ids[0],situational=100,set_damage=True)
        self.assertLess(t.hp,before);self.assertEqual(h.budget['standard'],budget['standard']-1)
        self.assertEqual(h.move_uses[ids[0]],1);self.assertNotIn(ids[1],h.move_uses)
        self.assertFalse(FREQ.move_allowed(e,h,ids[0])[0]);self.assertTrue(FREQ.move_allowed(e,h,ids[1])[0])
        self.assertNotIn('move/잠재파워',h.move_uses)
        for member,(oldspec,uses) in zip(m,member_before):
            for key in ('moves','move_learning','move_natural_history','state_grants','learned_poke_edges','stats','level','initial_allocation','hidden_power_type','frequency_state'):
                self.assertEqual(member.spec.get(key),oldspec.get(key))
            self.assertEqual(member.move_uses,uses)
        # The actual damage consumer reads the chosen class and type from each
        # instance, including the Attack/Defense versus SpAtk/SpDef difference.
        seen=[]
        import event_trace as TRACE
        original=TRACE.calculation
        def capture(engine,**data):seen.append(data);return original(engine,**data)
        with patch.object(TRACE,'calculation',capture):
            e.roll_damage(h,t,e.r.move(ids[0]),False,set_damage=True)
            e.roll_damage(h,t,e.r.move(ids[1]),False,set_damage=True)
        records=[x for x in seen if 'attack_stat' in x and 'defense_stat' in x]
        self.assertEqual([(x['attack_stat'],x['defense_stat'],x['damage_type']) for x in records],[('atk','def','물'),('spa','spd','풀')])
        self.assertEqual((e.r.moves,e.r.moves_mech),catalog)
        self.valid(e)

    def test_multiple_prior_hidden_powers_and_full_original_host_list_survive_outside_slots(self):
        e,a,h,m,t,row=self.fixture(1)
        originals=['move/잠재파워-불꽃','move/몸통박치기','move/전광석화','move/할퀴기','move/물대포','move/울음소리']
        G.set_baseline(h,'moves',originals)
        G.set_baseline(m[0],'moves',['move/잠재파워-불꽃','move/잠재파워-물'])
        row['joined'][0]['hidden_powers']=[{'move_id':'move/잠재파워-불꽃','type':'불꽃','damage_class':'physical'},
            {'move_id':'move/잠재파워-물','type':'물','damage_class':'special'}]
        self.observe(e,row)
        ids=S.prime_moves(e.r,h.spec[S.PRIME_KEY])
        self.assertEqual(len(h.moves),8);self.assertTrue(set(originals)<=set(h.moves))
        self.assertEqual(MOVES.describe(e.r,h.spec,moves=h.moves)['slot_count'],6)
        self.assertEqual([e.r.move(mid)['type'] for mid in ids],['불꽃','물'])
        self.valid(e)

    def test_generic_prior_type_must_be_observed_and_does_not_become_normal_by_default(self):
        e,a,h,m,t,row=self.fixture(1,generic=True)
        row['joined'][0].pop('hidden_power_type')
        out=self.observe(e,row)
        self.assertTrue(out['state_view']['unresolved']);self.assertEqual(S.prime_moves(e.r,h.spec[S.PRIME_KEY]),[])
        forged=S.prime_instance_id(row,row['joined'][0],{'move_id':'move/잠재파워','type':'노말','damage_class':'physical'})
        with self.assertRaisesRegex(ValueError,'owned|ownership'):e.use_move(h,t,forged)
        self.assertNotIn(forged,h.moves)
        enriched=deepcopy(row);enriched['joined'][0]['hidden_power_type']='물'
        self.observe(e,enriched)
        ids=S.prime_moves(e.r,h.spec[S.PRIME_KEY]);self.assertEqual(len(ids),1)
        self.assertEqual(e.r.move(ids[0])['type'],'물')
        rewritten=deepcopy(enriched);rewritten['joined'][0]['hidden_power_type']='풀'
        with self.assertRaisesRegex(ValueError,'permanent'):self.observe(e,rewritten)
        self.valid(e)

    def test_fifth_join_rewrite_split_duplicate_recombination_and_glyph_conflicts_are_atomic(self):
        e,a,h,m,t,row=self.fixture();self.observe(e,row)
        before=deepcopy((e._physical_objects,h.spec,h.stats,h.moves,h.hp))
        bads=[]
        changed=deepcopy(row);changed['joined'][0]['damage_class']='special';bads.append(changed)
        split=deepcopy(row);split['joined']=split['joined'][:2];bads.append(split)
        fifth=Combatant(e.r,build_pokemon(e.r,'안농',20,name='fifth',moves=['move/잠재파워-물'],wild=True));fifth.on_field=False;e.everyone.append(fifth)
        full=deepcopy(row);full['joined'].append({'member_id':fifth.entity_id,'boosted_stat':'def','hidden_power_id':'move/잠재파워-물','damage_class':'special'});bads.append(full)
        other=deepcopy(row);other['id']='second-prime';other['actor_id']=fifth.entity_id;other['joined']=other['joined'][:1];bads.append(other)
        for bad in bads:
            with self.subTest(joined=bad['joined']):
                with self.assertRaises(ValueError):self.observe(e,bad)
                self.assertEqual((e._physical_objects,h.spec,h.stats,h.moves,h.hp),before)
        # Existing glyph validator rejects absorbed identities before any
        # unrelated Fantasy source creation can be certified.
        fantasy=Rules(ROOT,ruleset='fantasy');e.r=fantasy
        wall={'id':'wall','kind':'object','location':{'kind':'unknown'}}
        W.register_object(e,'wall',location={'kind':'unknown'},reason='surface')
        glyph=dict(id='glyph',kind='glyph',location={'kind':'unknown'},creator_id=a.entity_id,unown_id=m[0].entity_id,
            creation_level=a.level,level=a.level,hp=a.level,max_hp=a.level,status='active',visible=False,channeling=False,flat_surface_id='wall')
        with self.assertRaisesRegex(ValueError,'Prime Unown'):S.observe(e,glyph,reason='cannot reuse absorbed member')

    def test_absorbed_actual_identity_is_blocked_on_turn_move_command_movement_ball_and_party_actions(self):
        e,a,h,m,t,row=self.fixture(1);self.observe(e,row);member=m[0]
        before=deepcopy((member.spec,member.hp,member.move_uses,a.spec))
        attempts=[lambda:e.start_of_turn(member),lambda:e.use_move(member,t,member.moves[0]),
            lambda:e.use_move(t,member,'move/몸통박치기'),lambda:COMMAND.require_command(e,member),
            lambda:TURN.can_act(e,member),lambda:e.throw_ball(a,member),lambda:PARTY.require_participation(e,member)]
        for attempt in attempts:
            with self.assertRaisesRegex(ValueError,'Prime Unown'):attempt()
        self.assertEqual((member.spec,member.hp,member.move_uses,a.spec),before)
        self.assertIs(W.actor_index(e)[member.entity_id],member)
        self.valid(e)

    def test_managed_party_counts_combined_members_once_and_cannot_send_or_place_them(self):
        e,a,h,m,t,row=self.fixture(1,owned=True)
        PARTY.configure(e,a,mode='custom',limit=1,storage={'kind':'center','id':'center'},reason='one travelling Pokemon',roster=[h,*m])
        self.observe(e,row)
        self.assertEqual(PARTY._carried(a),1)
        PARTY.configure(e,a,mode='custom',limit=1,storage={'kind':'center','id':'center'},reason='same source party',roster=[h,*m])
        self.assertEqual(PARTY._carried(a),1)
        self.assertEqual(a.spec['pokemon_registry'][m[0].entity_id]['combined_into'],h.entity_id)
        for where in ('storage','carried'):
            PARTY.place(e,a,target=h,location=where)
            self.assertEqual(m[0].spec['party_location']['location'],h.spec['party_location']['location'])
            self.assertEqual(m[0].spec['party_location']['destination'],h.spec['party_location']['destination'])
        h.on_field=True
        with self.assertRaisesRegex(ValueError,'Prime Unown'):PARTY.place(e,a,target=m[0],location='carried')
        COMMAND.configure(e,a,battle_mode='league',reason='actual League party')
        self.begin(e,a)
        with self.assertRaisesRegex(ValueError,'Prime Unown'):COMMAND.act(e,a,send=[(m[0],(5,5))],request_id='send-absorbed',reason='invalid split')
        COMMAND.act(e,a,recall=[h],request_id='recall-host',reason='one actual Prime body')
        self.assertFalse(h.on_field);self.assertFalse(m[0].on_field)
        e.end_of_turn(a);e.start_round([a,t]);e.start_of_turn(a,initiative_count=20)
        COMMAND.act(e,a,send=[(h,(5,5))],request_id='send-host',reason='same actual Prime body')
        self.assertTrue(h.on_field);self.assertFalse(m[0].on_field);self.assertEqual(PARTY._carried(a),1)
        e.end_of_turn(a);e.end_encounter()
        other=Combatant(e.r,build_trainer(e.r,'other-owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),pos=(0,1)))
        e.everyone.append(other)
        PARTY.configure(e,other,mode='custom',limit=0,storage={'kind':'center','id':'new-center'},reason='actual new owner storage',roster=[])
        PARTY.transfer(e,a,target=h,new_owner=other,reason='observed whole Prime ownership transfer',request_id='transfer-host')
        self.assertEqual(h.spec['party_location']['destination'],{'kind':'center','id':'new-center'})
        self.assertEqual(m[0].spec['party_location']['destination'],h.spec['party_location']['destination'])
        self.assertEqual(m[0].spec['trainer_id'],a.entity_id)
        with self.assertRaisesRegex(ValueError,'Prime Unown'):
            PARTY.transfer(e,a,target=m[0],new_owner=other,reason='cannot transfer an absorbed identity separately',request_id='transfer-member')
        # The existing successful-capture placement producer also changes the
        # actual host's placement.  It receives an observed success, and no
        # new capture procedure or ownership rule is certified here.
        e2,a2,h2,m2,t2,row2=self.fixture(1)
        m2[0].spec['trainer_id']=a2.entity_id
        PARTY.configure(e2,a2,mode='custom',limit=0,storage={'kind':'center','id':'capture-center'},reason='actual capture overflow',roster=m2)
        self.observe(e2,row2)
        plan=PARTY.preflight_capture(e2,a2,h2);h2.captured=True
        PARTY.finish_capture(e2,a2,h2,plan)
        self.assertEqual(m2[0].spec['party_location']['location'],'storage')
        self.assertEqual(m2[0].spec['party_location']['destination'],h2.spec['party_location']['destination'])
        self.valid(e2)
        self.valid(e)

    def test_underdog_loss_is_consumed_and_preserves_independent_capabilities_and_member_sources(self):
        e,a,h,m,t,row=self.fixture(1,owned=True)
        h.spec['capabilities']=['약골','Underdog','capability/약골','활자','독립능력']
        import underdog_edges as UNDERDOG
        self.assertTrue(UNDERDOG.owned(h))
        h.spec['tutor_points']=8
        e.pokemon_activity(a,'teach_edge',target=h,edge=UNDERDOG.STRENGTH,safe=True)
        member=deepcopy(m[0].spec)
        self.assertEqual(h.spec['tutor_points'],7)
        before=GROWTH.source_permanent(h);stats=deepcopy(h.stats)
        self.observe(e,row)
        self.assertFalse(UNDERDOG.owned(h))
        self.assertEqual(G.effective_capabilities(h),['활자','독립능력'])
        self.assertEqual(m[0].spec,{**member,S.PRIME_MEMBER:{'record_id':row['id'],'host_id':h.entity_id}})
        self.assertIn('약골',h.spec['capabilities'])
        receipt=UNDERDOG.records(h.spec)[0]
        self.assertEqual(receipt['status'],'refunded');self.assertEqual(receipt['refund']['points'],1)
        self.assertEqual(h.spec['tutor_points'],8)
        after=GROWTH.source_permanent(h)
        self.assertEqual(after['investment'],before['investment'])
        self.assertFalse(UNDERDOG.base_sources(e.r,h.spec))
        self.assertEqual(h.stats,{st:value-1+(5 if st=='hp' else 0) for st,value in stats.items()})
        self.valid(e)

    def test_gm_snapshot_json_restore_and_forged_instance_projection_are_validated(self):
        e,a,h,m,t,row=self.fixture(2,generic=True);self.observe(e,row)
        ids=S.prime_moves(e.r,h.spec[S.PRIME_KEY]);e.gm.snapshot('combined')
        e.gm.set_hp(h,h.hp-3,reason='actual damage');e.gm.restore('combined',reason='restore actual same combination')
        self.assertIs(W.actor_index(e)[h.entity_id],h)
        payload=CODEC.dump_engine(e);loaded=CODEC.load_engine(e.r,json.loads(json.dumps(payload)))
        actual=W.actor_index(loaded)[h.entity_id]
        self.assertEqual(S.prime_moves(loaded.r,actual.spec[S.PRIME_KEY]),ids)
        self.assertIs(W.actor_index(loaded)[m[0].entity_id],loaded.everyone[2])
        self.valid(loaded)
        with self.assertRaisesRegex(ValueError,'owned|ownership'):G.set_baseline(t,'moves',[ids[0]])
        forged=deepcopy(actual.spec[S.PRIME_KEY]);forged['joined'][0]['hidden_power_type']='전기'
        actual.spec[S.PRIME_KEY]=forged
        self.assertFalse(loaded.validate_state()['valid'])
        with self.assertRaises(ValueError):CODEC.dump_engine(loaded)


if __name__=='__main__':unittest.main()
