"""C10-105 native holder, qualifier, one space and identified pending plants."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import test_category3_pokemon_activities as fixture
import common_checks as C
import cultivation_state as P,cultivation_growth as G,cultivation_harvest as H
import planter_capability as PLANTER,state_grants as GRANTS,state_codec as CODEC

ROOT=Path(__file__).resolve().parents[1]


class CorePlanterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    actor=fixture.PokemonActivityTests.actor

    def setUp(self):self.world()

    def pokemon(self,uid,species):
        return Combatant(self.rules,build_pokemon(self.rules,species,30,moves=['struggle'],abilities=[],
            wild=True,side='independent',extra={'id':'pokemon/'+uid}))

    def world(self,species='토대부기',sessions=False):
        self.e=Engine(self.rules,seed=63,**({'session_frequency':True,'defer_session_refresh':True} if sessions else {}))
        self.p=self.pokemon('planter',species);self.q=self.pokemon('other','꼬부기')
        self.owner=self.actor('observer','trainer')
        self.e.gm.everyone=[self.p,self.q,self.owner]
        if sessions:self.e.begin_session('start',[self.owner])
        self.p.spec.setdefault('items',{}).update({'버치열매':5,'향기버섯':5,'멘탈허브':5})

    def native(self,species='버치열매',pid='plant:first',**kw):
        return self.e.pokemon_activity(self.p,'plant_berry',berry=species,plant_id=pid,planter_policy=kw.pop('planter_policy','book-literal'),**kw)

    def snapshot(self):return CODEC.dump_engine(self.e)

    def assert_atomic(self,call):
        before=self.snapshot()
        with self.assertRaises(ValueError):call()
        self.assertEqual(before,self.snapshot())

    def test_native_unrestricted_holder_pays_real_seed_and_harvests_without_trainer_or_item(self):
        out=self.native('향기버섯')
        plant=self.p.spec['plants']['plant:first']
        self.assertEqual(self.p.spec['items']['향기버섯'],4)
        self.assertNotIn('나무열매플랜터',self.p.spec['items'])
        self.assertFalse(self.p.spec.get('edges'));self.assertFalse(self.p.spec.get('feats'))
        self.assertIs(plant,self.e._physical_objects['plant:first'])
        self.assertEqual(plant['growth']['owner_id'],self.p.entity_id)
        self.assertEqual(plant['growth']['site_id'],PLANTER.site_id(self.p))
        self.assertEqual(out['plant']['crop'],P.crop(self.rules,'향기버섯'))
        self.e.advance_time(172799,[self.p]);self.assertEqual(self.e.growth_status(self.p,'plant:first')['remaining'],1)
        self.assert_atomic(lambda:self.e.pokemon_activity(self.p,'harvest_berry',plant_id='plant:first',fixed=4))
        self.e.advance_time(1,[self.p])
        out=self.e.pokemon_activity(self.p,'harvest_berry',plant_id='plant:first',fixed=4,environment_allows_growth=False,soil_quality=-99)
        self.assertEqual((out['amount'],out['protected'],out['receipt']['soil_base'],out['receipt']['site_bonus']),(2,True,0,1))
        self.assertEqual(self.p.spec['items']['향기버섯'],6)

    def test_actual_qualified_capabilities_and_narrow_dispatch_reject_before_payment(self):
        for species,allowed,denied in [('트로피우스','버치열매','멘탈허브'),('파라섹트','멘탈허브','버치열매')]:
            with self.subTest(species=species):
                self.world(species)
                self.assert_atomic(lambda:self.native(denied))
                self.native(allowed)
        self.world('꼬부기')
        self.assert_atomic(lambda:self.native())
        GRANTS.grant(self.p,'capabilities','Planter(Berries)','fixture:planter','fixture')
        self.assert_atomic(lambda:self.native('멘탈허브'))
        self.native()
        self.assert_atomic(lambda:self.e.pokemon_activity(self.p,'breed',pair=[self.p,self.q],task_id='forged',phase='check',compatible=True))
        self.assert_atomic(lambda:self.e.pokemon_activity(self.q,'harvest_berry',plant_id='plant:first',fixed=3))
        self.assert_atomic(lambda:self.e.pokemon_activity(deepcopy(self.p,{id(self.rules):self.rules}),'plant_berry',berry='버치열매',plant_id='forged',planter_policy='book-literal'))
        self.owner.spec['capabilities']=['Planter'];self.owner.spec['items']['버치열매']=1
        self.assert_atomic(lambda:self.e.pokemon_activity(self.owner,'plant_berry',berry='버치열매',plant_id='forged',planter_policy='book-literal'))

    def test_global_single_space_and_fixed_source_policy_cannot_be_bypassed_by_declarations(self):
        self.native();plant=self.p.spec['plants']['plant:first'];value=deepcopy(plant['growth']['definition'])
        self.assert_atomic(lambda:self.native(pid='plant:second'))
        self.assert_atomic(lambda:self.e.plant_growth(self.p,value,plant_id='plant:second',site_id='different:site',reason='changed ID'))
        value['site']['capacity']=4
        self.assert_atomic(lambda:self.e.plant_growth(self.p,value,plant_id='plant:second',site_id=PLANTER.site_id(self.p),reason='CSV capacity cannot enlarge capability'))
        self.assert_atomic(lambda:self.e.observe_cultivation_site(self.p,PLANTER.site_id(self.p),capacity=4,soil_quality=9,soft_soil=True,allows_growth=True,reason='replace innate site'))
        self.world();self.p.spec['items']['버치열매']=0
        self.assert_atomic(lambda:self.native())
        self.assertNotIn(PLANTER.site_id(self.p),getattr(self.e,'_physical_objects',{}))
        self.p.spec['items']['버치열매']=1
        self.assert_atomic(lambda:self.native(planter_slot=0))
        self.assert_atomic(lambda:self.native(soft_soil=True))

    def test_retained_plant_survives_capability_loss_and_gm_and_fresh_rules_restore(self):
        self.native();self.p.spec['capabilities']=[v for v in self.p.spec['capabilities'] if PLANTER.restriction(v) is False]
        self.assertFalse(any(PLANTER.restriction(v) is not False for v in GRANTS.effective_capabilities(self.p)))
        self.e.advance_time(17,[self.p]);self.e.gm.snapshot('planted')
        saved=json.loads(json.dumps(self.snapshot(),ensure_ascii=False))
        fresh=Rules(ROOT,ruleset='core');restored=CODEC.load_engine(fresh,saved)
        self.e.advance_time(1,[self.p]);self.e.gm.restore('planted')
        for e in (self.e,restored):
            p=next(a for a in e.gm.everyone if a.entity_id==self.p.entity_id)
            self.assertIs(p.spec['plants']['plant:first'],e._physical_objects['plant:first'])
            self.assertEqual(e.growth_status(p,'plant:first')['remaining'],172783)
            e.advance_time(172783,[p])
            self.assertEqual(e.pokemon_activity(p,'harvest_berry',plant_id='plant:first',fixed=3)['amount'],3)
            with self.assertRaises(ValueError):e.pokemon_activity(p,'plant_berry',berry='버치열매',plant_id='second',planter_policy='book-literal')

    def test_saved_holder_qualifier_and_source_integrity_remain_authoritative(self):
        self.world('트로피우스');self.native();plant=self.p.spec['plants']['plant:first'];original=deepcopy(plant)
        for change in ('restriction','holder','seed','alias'):
            with self.subTest(change=change):
                plant.clear();plant.update(deepcopy(original));self.p.spec['plants']['plant:first']=plant
                definition=plant['growth']['definition']
                if change=='restriction':definition['site']['capability']['restriction']=None;plant['growth']['definition_sha256']=G._digest(definition)
                elif change=='holder':definition['site']['capability']['holder_id']=self.q.entity_id;plant['growth']['definition_sha256']=G._digest(definition)
                elif change=='seed':plant['growth']['seed_payment']['count']=2
                else:self.p.spec['plants']['plant:first']=deepcopy(plant)
                with self.assertRaises(ValueError):self.snapshot()
        plant.clear();plant.update(deepcopy(original));self.p.spec['plants']['plant:first']=plant
        before=self.snapshot()
        with patch.object(PLANTER,'REFERENCE',dict(PLANTER.REFERENCE,sha256='0'*64)):
            with self.assertRaises(ValueError):self.e.growth_status(self.p,'plant:first')
        self.assertEqual(before,self.snapshot())

    def test_sheet_clock_does_not_import_four_slots_or_world_seconds(self):
        self.world(sessions=True);self.native(planter_policy='sheet-current')
        self.assertEqual(self.p.spec['plants']['plant:first']['growth']['definition']['site']['capacity'],1)
        self.assert_atomic(lambda:self.native(pid='second',planter_policy='sheet-current'))
        self.e.advance_time(172800,[self.p]);self.assertEqual(self.e.growth_status(self.p,'plant:first')['remaining'],3)
        for n in (1,2,3):
            self.e.begin_session('next:'+str(n),[self.owner])
            self.e.begin_session('next:'+str(n),[self.owner])
            self.assertEqual(self.e.growth_status(self.p,'plant:first')['remaining'],3-n)
        self.assertEqual(self.e.pokemon_activity(self.p,'harvest_berry',plant_id='plant:first',fixed=3)['amount'],3)

    def test_unrestricted_identified_species_plants_with_pending_policy_and_no_fabricated_harvest(self):
        # The GM identifies a real counted seed. This fact is not a yield table.
        identity={'species':'민들레','kind':'flower','seed_source':P.SOURCE,'reason':'GM identified actual dandelion seeds in inventory'}
        self.p.spec['items']['민들레']=2
        value=PLANTER.definition(self.rules,self.p,'민들레','민들레','플랜터','book-literal',identity)
        self.e.plant_growth(self.p,value,plant_id='plant:flower',site_id=PLANTER.site_id(self.p),reason='actual unrestricted plant seed')
        self.assertEqual(self.p.spec['items']['민들레'],1)
        plant=self.p.spec['plants']['plant:flower']
        self.assertIs(plant,self.e._physical_objects['plant:flower'])
        self.assertEqual(plant['crop'],{'kind':'flower','harvest_policy':'pending'})
        self.assertEqual(plant['growth']['definition']['maturity'],{'clock':'pending','amount':None})
        before=self.snapshot()
        result=self.e.pokemon_activity(self.p,'harvest_berry',plant_id='plant:flower',fixed=999)
        self.assertIsInstance(result,C.PendingDecision);self.assertIn('민들레',result.required)
        self.assertEqual(before,self.snapshot())
        self.assertEqual(self.e.growth_status(self.p,'plant:flower')['clock'],'pending')
        loaded=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(self.snapshot(),ensure_ascii=False)))
        p=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
        self.assertIs(p.spec['plants']['plant:flower'],loaded._physical_objects['plant:flower'])
        self.assertIsInstance(loaded.pokemon_activity(p,'harvest_berry',plant_id='plant:flower'),C.PendingDecision)
        self.world()
        forged={'species':'버치열매','kind':'flower','seed_source':'item/버치열매','reason':'cannot relabel reviewed Berry'}
        with self.assertRaisesRegex(ValueError,'reviewed plant classification'):PLANTER.definition(self.rules,self.p,'버치열매','버치열매','플랜터','book-literal',forged)
        self.world('트로피우스');self.p.spec['items']['민들레']=1
        value=PLANTER.definition(self.rules,self.p,'민들레','민들레','플랜터 (열매)','book-literal',identity)
        self.assert_atomic(lambda:self.e.plant_growth(self.p,value,plant_id='flower',site_id=PLANTER.site_id(self.p),reason='Berry-only holder cannot plant flower'))


if __name__=='__main__':unittest.main()
