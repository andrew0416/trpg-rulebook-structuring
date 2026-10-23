"""C11-049/050: original final chart -> ordinary native type/damage consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer,allocation_base
from state_codec import StateCodecError
import example_species as X,type_state as T,homebrew_state as H
import state_grants as G,downtime as D,combat_damage as DAMAGE
import pokemon_party as PARTY

ONIX='pokemon/example/crystal-onix'
# Independently transcribed from the two visibly separate printed467 columns.
MONO={'immune':{'물'},'resist':{'노말','얼음','독'},
      'weak':{'불꽃','격투','땅','바위','강철'}}
DUAL={'immune':{'물','전기'},'resist':{'노말','비행'},'double':{'독'},
      'weak':{'불꽃','풀','격투','땅','강철'}}


class CrystalOnixTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):self.e=Engine(self.r,4950)
 def add(self,spec):
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def pokemon(self,species=ONIX,level=10,**kw):
  kw.setdefault('abilities',[])
  return self.add(build_pokemon(self.r,species,level,**kw))
 def trainer(self):
  return self.add(build_trainer(self.r,'chart attacker',10,
      dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),abilities=[]))
 def expected(self,chart,attack):
  return 0 if attack in chart['immune'] else .25 if attack in chart.get('double',()) else .5 if attack in chart['resist'] else 1.5 if attack in chart['weak'] else 1

 def test_source_template_preserves_stock_and_independent_actual_instances(self):
  stock=deepcopy(self.r.species['pokemon/롱스톤']);a=self.pokemon();b=self.pokemon()
  self.assertEqual(a.spec['species'],ONIX);self.assertEqual(a.types,['유리','땅'])
  self.assertEqual(a.spec['example_definition'],self.r.species[ONIX]['example_definition'])
  for key in ('base_stats','movement','size','weight_class','capabilities'):
   self.assertEqual(self.r.species[ONIX][key],stock[key])
  original=self.r.learnsets['롱스톤'];derived=self.r.learnsets['크리스탈롱스톤']
  for key in ('level_up','tm','tutor','egg','abilities'):self.assertEqual(derived[key],original[key])
  self.e.gm.set_types(a,['유리'],reason='GM observes a monotype individual')
  self.assertEqual(b.types,['유리','땅']);self.assertEqual(self.r.species['pokemon/롱스톤'],stock)

 def test_all_eighteen_mono_and_exact_final_joint_matchups(self):
  p=self.pokemon()
  for types,chart in [(['유리'],MONO),(['유리','땅'],DUAL),(['땅','유리'],DUAL)]:
   self.e.gm.set_types(p,types,reason='source table form')
   for attack in T.CORE_TYPES:
    with self.subTest(types=types,attack=attack):
     self.assertEqual(self.e.type_multiplier(attack,p)[0],self.expected(chart,attack))
  self.assertEqual(T.matchup(self.r,'비행','유리'),1)
  self.assertEqual(T.matchup(self.r,'비행','땅'),1)
  self.assertEqual(self.e.type_multiplier('비행',p)[0],.5)

 def test_native_damage_uses_resistance_double_resistance_weakness_and_immunity(self):
  a=self.trainer()
  for mid,factor in [('move/몸통박치기',.5),('move/날개치기',.5),
                     ('move/독침',.25),('move/불꽃세례',1.5),
                     ('move/물대포',0),('move/전기쇼크',0),('move/돌떨구기',1)]:
   p=self.pokemon();move=self.r.move(mid);receipt={};hp=p.hp
   with patch.object(DAMAGE,'scale',wraps=DAMAGE.scale) as scale:
    dealt=self.e.resolve_attack_damage(a,p,move,set_damage=True,_damage_observation=receipt)
   # The first scale is the committed formula; the second is the optional
   # resistance-reaction preview, whose multiplier is one further step lower.
   actual=scale.call_args_list[0].kwargs
   self.assertEqual(set(actual),{'after_defense','type_multiplier','other_multiplier','adjustment'})
   self.assertEqual(actual['type_multiplier'],factor)
   self.assertEqual(dealt,DAMAGE.scale(**actual))
   self.assertEqual(receipt['requested'],dealt);self.assertEqual(p.hp,hp-receipt['net_hp_loss'])
   self.assertEqual(receipt['damage_class'],move['class'])
   if factor==0:self.assertEqual(dealt,0);self.assertEqual(p.hp,hp)

 def test_native_rock_attack_has_one_stab_bonus_and_ground_stab_is_retained(self):
  owner=self.trainer()
  p=self.pokemon(moves=['move/돌떨구기'],extra={'trainer_id':owner.entity_id})
  target=self.trainer();target.pos=(1,0);target.side='wild';move=self.r.move('move/돌떨구기')
  PARTY.configure(self.e,owner,mode='standard',roster=[p],storage={'kind':'center','id':'test-native-roster'},reason='actual established native attack owner')
  self.assertNotIn('바위',p.types);self.assertIn('바위',H.stab_types(p))
  self.assertEqual(self.e.damage_base(p,move),move['damage_base']+2)
  ground=self.r.move('move/구멍파기')
  self.assertEqual(self.e.damage_base(p,ground),ground['damage_base']+2)
  self.assertEqual(self.e.damage_base(p,self.r.move('move/몸통박치기')),self.r.move('move/몸통박치기')['damage_base'])
  self.e.gm.observe_loyalty(p,6,reason='actual native attack participant')
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(p,initiative_count=20)
  hp=target.hp
  with patch.object(self.e,'accuracy_check',return_value=(True,15,False)),patch.object(self.e,'damage_base',wraps=self.e.damage_base) as db:
   self.e.use_move(p,target,move['id'],set_damage=True)
  self.assertGreater(db.call_count,0);self.assertLess(target.hp,hp)
  self.assertEqual(p.move_uses[move['id']],1);self.assertEqual(p.budget['standard'],0)

 def test_glass_stab_applies_to_actual_pokemon_type_and_ends_when_type_is_removed(self):
  p=self.pokemon('이상해씨');trainer=self.trainer();move=self.r.move('move/돌떨구기')
  self.e.gm.set_types(p,['유리'],reason='adopt source Glass typing')
  self.assertEqual(self.e.damage_base(p,move),move['damage_base']+2)
  self.e.gm.set_types(p,['땅'],reason='Glass typing no longer present')
  self.assertEqual(self.e.damage_base(p,move),move['damage_base'])
  self.e.gm.set_types(trainer,['유리'],reason='type observation does not make a Pokemon')
  self.assertEqual(self.e.damage_base(trainer,move),move['damage_base'])

 def test_native_source_grant_removal_snapshot_and_fresh_restore_keep_identity(self):
  p=self.pokemon();G.type_operation(p,'set',['유리'],'test/source-glass')
  self.e.gm.snapshot('mono');G.remove_owned(self.e,p,'test/source-glass')
  self.assertEqual(p.types,['유리','땅']);self.assertEqual(self.e.type_multiplier('비행',p)[0],.5)
  self.e.gm.restore('mono');self.assertEqual(p.types,['유리']);self.assertEqual(self.e.type_multiplier('비행',p)[0],1)
  fresh=Rules(ROOT,ruleset='core');n=Engine.import_state(fresh,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  c=next(x for x in n.everyone if x.entity_id==p.entity_id)
  self.assertEqual(c.spec['species'],ONIX);self.assertEqual(c.spec['example_definition'],p.spec['example_definition'])
  self.assertEqual(n.type_multiplier('물',c)[0],0);G.remove_owned(n,c,'test/source-glass')
  self.assertEqual(c.types,['유리','땅']);self.assertEqual(n.type_multiplier('독',c)[0],.25)
  D.gain_exp_combatant(n,c,'to next level');self.assertEqual(c.level,11)
  self.assertEqual(allocation_base(fresh,c.spec),fresh.species['pokemon/롱스톤']['base_stats'])

 def test_unwritten_glass_attacks_optional_matchups_and_mixtures_are_explicit(self):
  p=self.pokemon();a=self.trainer();move=dict(self.r.move('move/몸통박치기'),type='유리')
  for types in [[],['노말'],['유리']]:
   self.e.gm.set_types(p,types,reason='attack validation target')
   before=self.e.rng.getstate()
   with self.assertRaisesRegex(ValueError,'not Glass attacks'):self.e.roll_damage(a,p,move)
   self.assertEqual(self.e.rng.getstate(),before)
  for types in [['유리','불꽃'],['유리','땅','노말']]:
   self.e.gm.set_types(p,types,reason='unwritten source combination')
   with self.assertRaisesRegex(ValueError,'no reviewed source whole-chart'):self.e.type_multiplier('비행',p)
  self.e.gm.set_types(p,['유리'],reason='source monotype')
  poly=Rules(ROOT,ruleset='polygon');e=Engine(poly,50)
  c=Combatant(poly,build_pokemon(poly,ONIX,10,abilities=[]));e.gm.add_combatant(c)
  with self.assertRaisesRegex(ValueError,'no reviewed source matchup'):e.type_multiplier('에러',c)

 def test_selected_source_provenance_and_defender_policy_are_enforced_on_save(self):
  p=self.pokemon();saved=self.e.export_state();fresh=Rules(ROOT,ruleset='core')
  fresh.example_defender_types['유리']['defense_steps']['물']=0
  with self.assertRaises(StateCodecError):Engine.import_state(fresh,saved)
  p.spec['example_definition']['definition_id']='pokemon/롱스톤'
  with self.assertRaises(StateCodecError):self.e.export_state()
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda source:X.SOURCE+'/disabled' if source==X.SOURCE else original(source)):
   with self.assertRaises(ValueError):T.validate_types(self.r,['유리'])
   with self.assertRaises(ValueError):build_pokemon(self.r,ONIX,10,abilities=[])

 def test_source_type_cannot_be_overwritten_by_an_unrelated_custom_extension(self):
  r=deepcopy(self.r);matrix=dict.fromkeys(T.CORE_TYPES+('유리',),1)
  r.ruleset.profile['type_extensions']={'유리':{'source_id':X.SOURCE,'reason':'conflicting identity',
      'attack_vs':dict(matrix),'defense_vs':dict(matrix)}}
  with self.assertRaisesRegex(ValueError,'replace a selected source type'):T.allowed_types(r)

 def test_actual_tera_form_keeps_original_glass_rock_stab_and_ends_to_final_chart(self):
  r=Rules(ROOT,ruleset='homebrew');e=Engine(r,50)
  p=Combatant(r,build_pokemon(r,ONIX,10,abilities=[]));e.gm.add_combatant(p)
  H.observe_type(e,p,'물',reason='established permanent Tera choice')
  H.observe_active(e,p,True,reason='observed active transformation')
  self.assertEqual(p.types,['물']);self.assertIn('바위',H.stab_types(p))
  self.assertEqual(e.type_multiplier('비행',p)[0],1)
  self.assertEqual(e.damage_base(p,r.move('move/돌떨구기')),r.move('move/돌떨구기')['damage_base']+2)
  e.end_encounter();self.assertEqual(p.types,['유리','땅'])
  self.assertEqual(e.type_multiplier('비행',p)[0],.5)


if __name__=='__main__':unittest.main()
