"""Exact source-owned static trainer modifiers through their native consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]

from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import effects as FX
import items as ITEMS
import movement_actions as MOVEMENT
import state_codec as CODEC
import state_fields as FIELDS
import state_grants as GRANTS
import static_trainer_modifiers as STATIC
import survivalist_features as SURVIVALIST
import weapon_actions as WEAPONS
import world_entities as WORLD


STAT_ROWS={
 'hp':('C2CSV/input/db/feats.csv:R125:main',STATIC.ENDURING,None),
 'atk':('C2CSV/input/db/feats.csv:R162:main',STATIC.STAT_ACE,'atk'),
 'def':('C2CSV/input/db/feats.csv:R163:main',STATIC.STAT_ACE,'def'),
 'spa':('C2CSV/input/db/feats.csv:R164:main',STATIC.STAT_ACE,'spa'),
 'spd':('C2CSV/input/db/feats.csv:R165:main',STATIC.STAT_ACE,'spd'),
 'spe':('C2CSV/input/db/feats.csv:R166:main',STATIC.STAT_ACE,'spe'),
}
ALL_ROWS=set(row[0] for row in STAT_ROWS.values())|{
 'C2CSV/input/db/feats.csv:R194:main','C2CSV/input/db/feats.csv:R293:main',
 'C2CSV/input/db/feats.csv:R672:main','C2CSV/input/db/class-data.csv:R25:technique'}
ALL_ROWS.add('C2CSV/input/db/class-data.csv:R30:technique')


class StaticTrainerModifierTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')

 def encounter(self,*,classes=(),feats=(),choices=None,level=20,moves=()):
  e=Engine(self.r,seed=1710)
  t=Combatant(self.r,build_trainer(self.r,'Owner',30,
   {'hp':40,'atk':12,'def':12,'spa':12,'spd':12,'spe':12},moves=[],abilities=[],
   extra={'classes':list(classes),'feats':list(feats),'edges':[],
          'feature_choices':deepcopy(choices or {}),'skills':{'명령':6,'통찰':3}}))
  p=Combatant(self.r,build_pokemon(self.r,'이상해씨',level,moves=list(moves),abilities=[],
   extra={'trainer_id':t.entity_id}))
  q=Combatant(self.r,build_pokemon(self.r,'이상해씨',level,moves=list(moves),abilities=[]))
  for actor,pos in ((t,(0,0)),(p,(1,0)),(q,(2,0))):
   e.gm.add_combatant(actor,pos=pos,side='party',reason='actual static modifier fixture')
  return e,t,p,q

 def test_exact_policy_pins_all_ten_reviewed_source_clauses(self):
  policy=STATIC._policy(self.r)
  self.assertEqual(set(policy['clauses']),ALL_ROWS)
  self.assertEqual(policy['stat_ace_branches'],{
   'atk':'C2CSV/input/db/feats.csv:R162:main','def':'C2CSV/input/db/feats.csv:R163:main',
   'spa':'C2CSV/input/db/feats.csv:R164:main','spd':'C2CSV/input/db/feats.csv:R165:main',
   'spe':'C2CSV/input/db/feats.csv:R166:main'})
  self.assertTrue(all(len(row['cell_sha256'])==64 for row in policy['clauses'].values()))

 def test_enduring_and_each_stat_ace_branch_follow_level_formula_once(self):
  for field,(clause,source,branch) in STAT_ROWS.items():
   with self.subTest(field=field):
    choices={} if branch is None else {source:[branch]}
    e,t,p,q=self.encounter(classes=[source],choices=choices,level=20)
    baseline=p.spec['stats'][field]
    e.register_abilities(t);e.register_abilities(t)
    self.assertEqual(p.stats[field],baseline+3)
    self.assertEqual(q.stats[field],q.spec['stats'][field])
    rows=p.spec[GRANTS.KEY]['sources']
    owned=[row for row in rows.values() if row.get('clause_id')==clause]
    self.assertEqual(len(owned),1)
    self.assertEqual(owned[0]['owner_id'],t.entity_id)
    self.assertEqual(owned[0]['lifetime'],'your_pokemon')
    e.gm.set_level(p,30,reason='actual permanent level growth')
    self.assertEqual(p.stats[field],baseline+4)
    new=dict(p.spec['stats']);new[field]+=2
    FIELDS.base_patch(p,{'stats':new},reason='actual permanent base-stat growth')
    self.assertEqual(p.stats[field],baseline+6)
    self.assertTrue(e.validate_state()['valid'])

 def test_stat_sources_stack_restore_and_retract_by_actual_owner(self):
  e,t,p,q=self.encounter(classes=[STATIC.ENDURING,STATIC.STAT_ACE],
   choices={STATIC.STAT_ACE:['atk']},level=20)
  e.register_abilities(t)
  expected=(p.spec['stats']['hp']+3,p.spec['stats']['atk']+3)
  self.assertEqual((p.stats['hp'],p.stats['atk']),expected)
  snap=e.gm.snapshot();e.gm.set_level(p,30,reason='temporary observed growth');e.gm.restore(snap)
  self.assertEqual((p.stats['hp'],p.stats['atk']),expected)
  payload=json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False))
  loaded=CODEC.load_engine(self.r,payload);index=WORLD.actor_index(loaded)
  lp=index[p.entity_id];lt=index[t.entity_id]
  self.assertEqual((lp.stats['hp'],lp.stats['atk']),expected)
  GRANTS.revoke_owner(loaded,lp,lt.entity_id,'actual ownership ended')
  self.assertEqual((lp.stats['hp'],lp.stats['atk']),
                   (lp.spec['stats']['hp'],lp.spec['stats']['atk']))
  self.assertTrue(loaded.validate_state()['valid'])

 def test_special_attack_mastery_changes_only_physical_origin_not_area_size(self):
  e,t,p,q=self.encounter(classes=[STATIC.STAT_ACE],feats=[STATIC.STAT_MASTERY],
   choices={STATIC.STAT_ACE:['spa'],STATIC.STAT_MASTERY:['spa']},
   moves=['화염방사','회오리','아이언헤드'])
  e.register_abilities(t)
  flame=self.r.move('move/화염방사');blast=self.r.move('move/회오리');melee=self.r.move('move/아이언헤드')
  self.assertEqual((WEAPONS.range_spec(e,flame,p)['origin'],WEAPONS.range_spec(e,flame,q)['origin']),(6,4))
  self.assertEqual((WEAPONS.range_spec(e,blast,p)['origin'],WEAPONS.range_spec(e,blast,p)['size']),(8,3))
  self.assertEqual(WEAPONS.range_spec(e,melee,p)['origin'],'melee')
  GRANTS.apply_owned(e,p,'fixture:unreviewed-range',lambda:p.modifiers.append({
   'type':'move_range_mod','value':20,'move_class':'특수','non_melee':True,'area_size_delta':0,
   '_clause_id':'unreviewed'}))
  self.assertEqual(WEAPONS.range_spec(e,flame,p)['origin'],6)
  GRANTS.revoke_owner(e,p,t.entity_id,'actual ownership ended')
  self.assertEqual(WEAPONS.range_spec(e,flame,p)['origin'],4)
  self.assertIn('fixture:unreviewed-range',GRANTS.state(p)['effects'])

 def test_special_attack_mastery_rejects_forged_visible_receipt(self):
  e,t,p,q=self.encounter(classes=[STATIC.STAT_ACE],feats=[STATIC.STAT_MASTERY],
   choices={STATIC.STAT_ACE:['spa'],STATIC.STAT_MASTERY:['spa']},moves=['화염방사'])
  e.register_abilities(t);effect=next(x for x in p.modifiers if x.get('type')=='move_range_mod')
  effect['value']=3
  with self.assertRaisesRegex(ValueError,'visibility changed'):FIELDS.validate_actor(p)

 def test_corrupt_blood_uses_status_and_damage_consumers_and_retracts(self):
  e,t,p,q=self.encounter(feats=['feat/부패한-피'],moves=['오물폭탄','화염방사'])
  attacker=q;target=t
  poison=self.r.move('move/오물폭탄');fire=self.r.move('move/화염방사')
  e.register_abilities(t)
  self.assertFalse(e.apply_status(t,'독',source='actual Poison source',applied_by=attacker))
  self.assertFalse(e.apply_status(t,'맹독',source='actual Bad Poison source',applied_by=attacker))
  reduced_poison=e.roll_damage(attacker,target,poison,set_damage=True)
  reduced_fire=e.roll_damage(attacker,target,fire,set_damage=True)
  source='feature:'+t.entity_id+':feat/부패한-피'
  t.spec['feats'].remove('feat/부패한-피');GRANTS.revoke(t,source,engine=e)
  self.assertNotIn('독',t.status_immune)
  self.assertGreater(e.roll_damage(attacker,target,poison,set_damage=True),reduced_poison)
  self.assertEqual(e.roll_damage(attacker,target,fire,set_damage=True),reduced_fire)
  self.assertTrue(e.validate_state()['valid'])

 def test_plains_runner_uses_actual_talent_for_skill_and_land_movement(self):
  e=Engine(self.r,seed=1711)
  a=Combatant(self.r,{'id':'trainer/plains','name':'Plains','kind':'trainer','size':'중형','level':20,
   'stats':{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},
   'skills':{'생존':6,'육상':4,'곡예':4,'은신':3,'통찰':3},
   'classes':[SURVIVALIST.SURVIVALIST],'feats':['feat/내추럴-파이터'],
   'edges':[],'movement':{'land':6},'weight_kg':70,'weight_class':4})
  e.everyone=[a]
  for terrain in ('grassland','mountain'):
   for n in range(3):
    SURVIVALIST.observe_environment(e,a,terrains=[terrain],light='normal',reason='GM actual terrain')
    SURVIVALIST.begin_night(e,a,night_id=terrain+str(n),terrain_name=terrain,reason='GM night')
    e.advance_time(60,[a]);SURVIVALIST.finish_night(e,a,night_id=terrain+str(n),reason='GM full night')
   SURVIVALIST.select_terrain(e,a,terrain_name=terrain,minutes=1,reason='GM Extended selection')
  a.spec['feats'].append(SURVIVALIST.TALENT);a.spec['feat_ranks']={SURVIVALIST.TALENT:1}
  SURVIVALIST.choose_talents(e,a,terrains=['grassland','mountain'])
  SURVIVALIST.observe_environment(e,a,terrains=['urban'],light='normal',reason='GM current terrain')
  self.assertEqual(MOVEMENT.capabilities(e,a,environment=False)['land'],8)
  self.assertEqual(e.move_profile(a,movement_mode='land'),(8,'육상'))
  context={'purpose':'distant_object','reason':'GM actual distant object'}
  self.assertEqual(e.skill_roll(a,'통찰',fixed=[1,1,1],skill_context=context).total,5)
  snapshot=e.gm.snapshot();a.spec['feats'].remove(SURVIVALIST.TALENT);a.spec.pop('_survivalist_talents');a.spec['feat_ranks'].pop(SURVIVALIST.TALENT)
  self.assertEqual(MOVEMENT.capabilities(e,a,environment=False)['land'],6)
  e.gm.restore(snapshot);self.assertEqual(MOVEMENT.capabilities(e,a,environment=False)['land'],8)
  fall=e.falling_damage(a,action_id='mountain-fall',meters=5,intentional=False,
   reason='GM actual five metre fall')
  self.assertEqual((fall['damage_distance'],fall['terrain_distance_reduction'],
                    fall['height_injuries'],fall['terrain_injury_reduction']),(4,1,1,1))


if __name__=='__main__':unittest.main(verbosity=2)
