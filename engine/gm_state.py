"""
GM 상태 개입. 재정(rulings)이 '처리 규칙'을 바꾼다면, 이 층은 '지금의 상태'를 GM 이 명시적으로 바꾼다 — 체력·임시 체력·부상·전투단계·상태이상(면역 무시 가능)·
위치·도구·버프·기술·특성·타입·스탯·레벨·카운터·고유 상태·날씨·필드·함정·이니셔티브·소생/기절/복귀/퇴장·참가자 추가/제거.
모든 개입은 전/후 값과 이유를 `[GM 상태]` 로그와 rulings.log(kind="state") 에 남기고, 스냅샷/되돌리기(rewind)를 지원한다.
문자열 명령도 받는다: engine.gm.command("아치 hp 30 -- 낙석에 맞음"), "뚜벅초 A +독", "마야 atk +2", "전원 상태 -둔화", "날씨 비", "되돌리기 before-trap" …
"""
import arithmetic_policy as M
import state_fields as STATE_FIELDS
import copy
import dataclasses
import re
import temporary_hp as TEMP_HP
import bandages as BANDAGES

COMBATANT_FIELDS = ["airborne","weapon", "_ap_bound_effects", "last_target", "_turn_start_decisions_pending", "_standard_action_round", "_action_history", "_turn_action_limit", "_restricted_action_taken", "faint_recovery_birth_round", "dead", "faint_recovery_seconds", "faint_recovery_pending", "faint_recovery_interrupted", "life_elapsed_seconds", "spec", "hp", "temp_hp", "injuries", "stages", "accuracy_stage", "evasion_mod", "conditions", "pos", "item", "buffs", "moves", "abilities", "types", "stats",
                    "level", "counters", "custom_conditions", "coats", "blessings", "registry", "modifiers", "captured", "on_field", "form", "damage_reduction",
                    "grounded", "shield", "next_attack", "took_standard", "last_move", "move_uses", "locked_move", "save_mod", "stage_loss_immune", "abilities_suppressed",
                    "initiative_override", "initiative_bonus", "setup_move", "reflect", "damage_cap", "passed", "turns_taken", "ability_triggers",
                    "_diagonal_steps", "_regular_shift_movement_used", "_item_reg", "_passive_acc", "_passive_eva", "movement", "budget", "pending_action_loss", "aoo_used", "_round_marker",
                    "status_immune", "weather_immune", "keyword_immune", "move_immune"]
ENGINE_FIELDS = ["_roll_policy_requests", "_roll_context_requests", "_execution_trace_enabled", "_execution_trace_sequence", "_execution_traces", "_source_policy_requests", "_source_policy_executions", "_source_policy_sequence", "_weather_templates","_weather_state","_mega_state","_encounter_actors", "_partial_entities", "_world_facts", "_world_relation_receipts", "_campaign_reward_policy","_campaign_reward_events","_league_outcomes","_pokemon_setting_policy","_pokemon_intelligence_policy","_effect_dispatch_receipts","_effect_dispatch_sequence","_skill_sequences","_precision_events","_precision_sequence","_initiative_cursor","_burrow_tunnels","ground_items", "_physical_objects", "_ap_rolls", "_extended_checks", "_root_common_receipts", "_passive_driver_result", "_passive_sequence", "_passive_listeners", "_passive_events", "_passive_receipts", "_passive_pending", "_league_runtime", "_turn_closures", "everyone", "_heavy_native_receipts", "_heavy_activation_sequence", "_heavy_driver_result", "_heavy_standard_receipts", "_heavy_standard_sequence", "_heavy_sequence", "_heavy_events", "_heavy_pending", "_heavy_resolution_history", "_active_turn_actor", "_ordinary_turn_rounds", "_action_grants", "session_frequency", "defer_session_refresh", "session_id", "pending_session_id", "session_ids_seen", "session_epoch", "encounter_active", "round_no", "elapsed_seconds", "round_start_seconds", "unresolved_time_intervals", "_time_actors", "death_enabled", "friendly_battle", "weather", "weather_rounds", "field", "hazards", "hazards_nogrid", "zone_cells", "zones", "taunt", "delayed", "zone_rules", "condition_params"]
ENGINE_FIELDS.extend(("_initiative_schedule", "_initiative_interrupts", "_initiative_extra_turns"))
ENGINE_FIELDS.append("_campaign_injury_policy")
ENGINE_FIELDS.append('_ground_flight_option')
ENGINE_FIELDS.append('_hp_loss_policy')
ENGINE_FIELDS.append('_session_move_policy')
ENGINE_FIELDS.extend(('_clock_invocations','_active_clock_invocation'))
ENGINE_FIELDS.extend(('_native_action_stack','_native_action_resolutions','_native_action_sequence'))
ENGINE_FIELDS.append('_breather_attempts')
ENGINE_FIELDS.extend(('_hazard_sequence','_hazard_region_sequence'))
ENGINE_FIELDS.append('_move_completions')
ENGINE_FIELDS.extend(('_gmax_activation_scopes','_gmax_effect_sequence','_gmax_coin_rewards','_gmax_payload_receipts'))
ENGINE_FIELDS.append('_party_encounter_epoch')
ENGINE_FIELDS.append("_activity_jobs")
ENGINE_FIELDS.append("_sensory_environments")
ENGINE_FIELDS.append("_communication_state")
ENGINE_FIELDS.append("_machine_operations")
ENGINE_FIELDS.append("_remote_control")
ENGINE_FIELDS.append("_network_connections")
ENGINE_FIELDS.append("_digital_integrity")
ENGINE_FIELDS.append("_object_repairs")
ENGINE_FIELDS.append("_vehicle_breaches")
ENGINE_FIELDS.append("_environment_derive")
ENGINE_FIELDS.append("_scene_lighting")
ENGINE_FIELDS.append("_mapless_space")
ENGINE_FIELDS.append("_enemy_accuracy_sheet")
ENGINE_FIELDS.append("_local_grass_occurrences")
ENGINE_FIELDS.append("_independent_field_effects")
ENGINE_FIELDS.append("_environment_changes")
ENGINE_FIELDS.append("_grapple_state")
ENGINE_FIELDS.append("_pass_moves")
ENGINE_FIELDS.append('_taskmaster_gambit')
ENGINE_FIELDS.append('_free_order_scope')
ENGINE_FIELDS.append('_commander_order_scope')
ENGINE_FIELDS.extend(('_smoke_regions','_smoke_region_sequence'))
COMBATANT_FIELDS.extend(("_mounted_riders","_mount_movement"))
COMBATANT_FIELDS.append('_equipment_transport_body')
STAT_KO = {"공격": "atk", "방어": "def", "특공": "spa", "특수공격": "spa", "특방": "spd", "특수방어": "spd", "스피드": "spe", "명중": "acc", "회피": "eva",
           "atk": "atk", "def": "def", "spa": "spa", "spd": "spd", "spe": "spe", "acc": "acc", "eva": "eva"}
WEATHER_KO = {"비": "rain", "비바라기": "rain", "쾌청": "sunny", "모래바람": "sandstorm", "싸라기눈": "hail", "눈": "snow", "없음": None, "맑음": None, "rain": "rain", "sunny": "sunny", "sandstorm": "sandstorm", "hail": "hail", "snow": "snow", "none": None}


class GMState:
    def __init__(self, engine):
        self.e = engine
        self.snapshots = {}
        self.everyone = []          # 참가자 목록 (scenario / 콘솔이 넣어 준다)

    def set_hp_loss_policy(self, mode, *, reason):
        """Persist temp_first (default) or bypass for unpreventable HP loss."""
        before = TEMP_HP.loss_policy(self.e)
        after = TEMP_HP.configure_loss_policy(self.e, mode, reason=reason)
        self._rec('방지 불가 HP 손실 정책', before, after, reason)
        return TEMP_HP.loss_policy(self.e)

    def observe_coup_de_grace_target(self, actor, *, properly_bound, completely_helpless, source, reason):
        import coup_de_grace as COUP
        return COUP.observe(self.e,actor,properly_bound=properly_bound,
            completely_helpless=completely_helpless,source=source,reason=reason)

    def observe_activity(self, actors, minutes, *, qualifies_as_rest, reason, rest_id=None):
        import downtime as DOWNTIME
        return DOWNTIME.observe_activity(self.e,actors,minutes,qualifies_as_rest=qualifies_as_rest,reason=reason,rest_id=rest_id)

    def observe_encounter_outcome(self, **observation):
        import encounter_settlement as SETTLEMENT
        return SETTLEMENT.observe_outcome(self.e, **observation)

    def collect_move_coins(self, *, encounter_id):
        import move_coins as COINS
        return COINS.settle(self.e, encounter_id=encounter_id)

    def activate_stellar_blast(self, actor, opportunity_id, radiated_type, *, reason):
        import stellar_tera_blast as STELLAR_TERA
        return STELLAR_TERA.activate(self.e,actor,opportunity_id,radiated_type,reason=reason)

    # ---------- 기록 ----------
    def observe_saddle_fit(self, mount, instance_id, **observation):
        import equipped_transport_saddle as EQUIPMENT
        return EQUIPMENT.fit_saddle(self.e,mount,instance_id,**observation)

    def observe_equipment_transport(self, controller, body_id, **observation):
        import equipped_transport_saddle as EQUIPMENT
        return EQUIPMENT.assemble(self.e,controller,body_id,**observation)

    def observe_missed_ball_ground(self, actor, **observation):
        import missed_ball_body as BALL_BODY
        return BALL_BODY.observe_ground(self.e,actor,**observation)

    def _rec(self, what, before, after, reason, who=None):
        self.e.rulings.record("state", f"{who.name + ' ' if who else ''}{what}", before, after, reason, "once")
        self.e.log(f"    [GM 상태] {who.name + ' ' if who else ''}{what}: {before} → {after}" + (f" ({reason})" if reason else ""), "gm/state")

    def find(self, name):
        """이름(부분 일치 허용)으로 전투원 찾기. '전원'/'아군'/'적' 은 목록."""
        if name in ("전원", "all", "*"):
            return [c for c in self.everyone if not c.captured]
        if name in ("아군", "party"):
            return [c for c in self.everyone if getattr(c, "side", "party") == "party"]
        if name in ("적", "enemies", "wild"):
            return [c for c in self.everyone if getattr(c, "side", "party") != "party"]
        exact = [c for c in self.everyone if c.name == name]
        if exact:
            return exact
        part = [c for c in self.everyone if name in c.name]
        if not part:
            raise KeyError(f"전투원 없음: {name} (있는 것: {', '.join(c.name for c in self.everyone)})")
        return part

    # ---------- 전투원 상태 ----------
    def resolve_jump_failure(self, c, *, decision, reason):
        import jump_actions as JUMP
        return JUMP.resolve_failure(self.e,c,decision=decision,reason_text=reason)

    def confirm_awareness(self, trainer, defenders, *, reason):
        import enduring_awareness as AWARENESS
        return AWARENESS.confirm(self.e,trainer,defenders,reason=reason)

    def observe_maturation_start(self, c, **observation):
        import item_maturation as MATURATION
        return MATURATION.observe_holding(self.e,c,**observation)

    def observe_magic_flute(self, instance_id, **observation):
        """Observe an existing instrument's manufacture choice and daily charge."""
        import magic_flute as FLUTE
        return FLUTE.observe(self.e, instance_id, **observation)

    def observe_smoke_ball_use(self, actor, center, **observation):
        """Observe actual deployment; the source specifies no action or range."""
        import smoke_balls as SMOKE
        return SMOKE.observe_use(self.e, actor, center, **observation)

    def observe_smoke_region(self, cells, *, reason):
        """Observe actual surviving legacy smoke membership, without old history."""
        import smoke_regions as SMOKE
        return SMOKE.observe_region(self.e,cells,reason=reason)

    def observe_cleanse_burn(self, c, instance_id, **options):
        return self.e.burn_cleanse_tag(c, instance_id, **options)

    def observe_cleanse_loss_elapsed(self, c, source_id, seconds, *, reason):
        import cleanse_tag_burn as CLEANSE_BURN
        return CLEANSE_BURN.observe_loss_elapsed(self.e, c, source_id, seconds, reason=reason)

    def observe_cleanse_barrier(self, instance_id, **observation):
        """Observe attachment/removal of the same manufactured tag on a real surface."""
        import cleanse_tags as TAG
        return TAG.observe_barrier(self.e, instance_id, **observation)

    def observe_cleanse_retry_elapsed(self, instance_id, actor, seconds, **observation):
        import cleanse_tags as TAG
        return TAG.observe_retry_elapsed(self.e, instance_id, actor, seconds, **observation)

    def observe_lifetime_consumption(self, c, **observation):
        import lifetime_consumables as LIFETIME
        return LIFETIME.observe(self.e,c,**observation)

    def observe_collected_keystone(self, collector, stone_id, **options):
        import keystone_state as K
        return K.observe(self.e,collector,stone_id,**options)

    def observe_surface_thought(self, c, thought, *, reason):
        import aura_pulse as PULSE
        return PULSE.observe_thought(self.e,c,thought,reason=reason)

    def observe_sensory_environment(self, observer, target, **facts):
        import perception_observe as OBSERVE
        return OBSERVE.observe_environment(self.e,observer,target,**facts)

    def observe_communication_relationship(self, sender, recipient, name, source, allowed, *, reason):
        import perception_communicate as COMM
        return COMM.observe_relation(self.e,sender,recipient,name,source,allowed,reason=reason)

    def observe_control_device(self, device_id, host_id, source, installed, *, reason):
        import control_remote as REMOTE
        return REMOTE.observe_device(self.e,device_id,host_id,source,installed,reason=reason)

    def observe_dream(self, c, content, *, reason):
        import dream_state as DREAM
        return DREAM.observe(self.e,c,content,reason=reason)

    def observe_aura(self, c, **observation):
        import aura_state as AURA
        return AURA.observe(self.e,c,**observation)

    def observe_plant(self, c, **observation):
        import cultivation_state as CULTIVATION
        return CULTIVATION.observe(self.e,c,**observation)

    def choose_learned_capability_policy(self, c, source, choice, *, reason):
        import move_capabilities as CAPABILITIES
        return CAPABILITIES.choose(self.e,c,source,choice,reason=reason)

    def set_movement_capabilities(self, c, values, *, basis, reason):
        import movement_actions as MOVEMENT
        return MOVEMENT.set_capabilities(self.e,c,values,basis=basis,reason_text=reason)

    def observe_partial_entity(self, **options):
        import partial_entities as PARTIAL
        return PARTIAL.observe(self.e, **options)

    def describe_partial_entity(self, entity_id):
        import partial_entities as PARTIAL
        return PARTIAL.project(self.e, entity_id)

    def update_partial_entity(self, entity_id, **options):
        import partial_entities as PARTIAL
        return PARTIAL.update(self.e, entity_id, **options)

    def set_footprint(self, c, offsets, *, reason):
        import body_state as BODY
        return BODY.observe(self.e, c, offsets, reason=reason)

    def observe_body_part(self, c, part_id, cell, *, reason):
        import body_state as BODY
        return BODY.observe_part(self.e, c, part_id, cell, reason=reason)

    def observe_body_passage(self, object_id, edge, **observation):
        import body_state as BODY
        return BODY.observe_passage(self.e, object_id, edge, **observation)

    def observe_melee_reach(self, c, value, **options):
        import body_state as BODY
        return BODY.observe_melee_reach(self.e, c, value, **options)

    def observe_melee_reach_source(self, c, choice=None):
        import body_state as BODY
        return BODY.observe_melee_reach_source(self.e, c, choice)

    def observe_elemental_connection_source(self, c, choice):
        import elemental_connection as ELEMENTAL
        return ELEMENTAL.observe_source(self.e, c, choice)

    def observe_trainer_weight(self, c, value, **options):
        import body_state as BODY
        return BODY.observe_trainer_weight(self.e, c, value, **options)

    def observe_foiling_foliage(self, owner, target, move_id, *, reason):
        """Record an explicit resolved choice; this does not pay or execute the action."""
        import move_state as MOVE_STATE
        return MOVE_STATE.select_foiling(self.e, owner, target, move_id, reason=reason)

    def define_mega_form(self, form_id, **options):
        import mega_forms as MEGA
        return MEGA.define(self.e,form_id,**options)

    def bind_mega_stone(self, instance_id, form_id, **options):
        import mega_forms as MEGA
        return MEGA.bind_stone(self.e,instance_id,form_id,**options)

    def choose_ability_transition(self, actor, target, source, **options):
        """Record an explicit ability/ally choice before native activation."""
        import ability_transitions as ABILITY_TRANSITIONS
        return ABILITY_TRANSITIONS.select(self.e,actor,target,source,**options)

    def choose_food_transfer(self, actor, target, buff_id, *, reason):
        """Select one actual live or consumed target food effect for Bug Bite."""
        import food_effects as FOOD
        return FOOD.choose_transfer(self.e,actor,target,buff_id,reason=reason)

    def choose_move_type(self, actor, move_id, chosen_type, *, known_move=None, reason):
        """Choose a source-authorized monotype before paying for the Move."""
        import move_type_choices as TYPES
        return TYPES.choose(self.e,actor,move_id,chosen_type,known_move=known_move,reason=reason)

    def choose_alternate_move_type(self, actor, move_id, alternate_type, *, reason):
        """Record the optional scene-limited type before the actual Move use."""
        import alternate_move_modes as ALTERNATE
        return ALTERNATE.choose(self.e,actor,move_id,alternate_type,reason=reason)

    def choose_optional_move_effect(self, actor, move_id, *, reason):
        """Select a reviewed optional effect for the next actual Move use."""
        import optional_move_modes as OPTIONAL
        return OPTIONAL.choose(self.e,actor,move_id,reason=reason)

    def choose_post_resolution_stage_effect(self, actor, move_id, *, reason):
        """Select a reviewed scene-limited stage-history effect before use."""
        import post_resolution_stage_effects as POST_STAGE
        return POST_STAGE.choose(self.e,actor,move_id,reason=reason)

    def choose_declarative_move(self, actor, target, move_id, **choice):
        """Record a reviewed Move's required stat or type choice before use."""
        import declarative_move_contracts as DECLARATIVE_MOVES
        return DECLARATIVE_MOVES.choose(self.e,actor,target,move_id,**choice)

    def choose_pokemon_skill_template(self, c, template, **options):
        import pokemon_skill_profiles as SKILLS
        return SKILLS.choose_template(self.e, c, template, **options)

    def adjust_pokemon_skill_template(self, c, skills, **options):
        import pokemon_skill_profiles as SKILLS
        return SKILLS.adjust(self.e, c, skills, **options)

    def evolve_pokemon_skill_template(self, c, **options):
        import pokemon_skill_profiles as SKILLS
        return SKILLS.evolve_template(self.e, c, **options)

    def set_pokemon_skill_background(self, c, name, **options):
        import pokemon_skill_profiles as SKILLS
        return SKILLS.background(self.e, c, name, **options)

    def describe_actor(self, c, *, viewer="player"):
        import pokemon_entities as ENTITIES
        return ENTITIES.actor_projection(c, viewer=viewer)

    def observe_loyalty(self, c, value, **options):
        import pokemon_entities as ENTITIES
        return ENTITIES.observe_loyalty(self.e, c, value, **options)

    def observe_legendary_classification(self, c, kind, **observation):
        import legendary_commands as LEGENDARY
        return LEGENDARY.observe_classification(self.e,c,kind,**observation)

    def legendary_qualification(self, c, trainer=None):
        import legendary_commands as LEGENDARY
        return LEGENDARY.qualification(self.e,c,trainer)

    def observe_legendary_recognition(self, c, trainer, recognized, **observation):
        import legendary_commands as LEGENDARY
        return LEGENDARY.observe_recognition(self.e,c,trainer,recognized,**observation)

    def observe_legendary_control(self, c, **observation):
        import legendary_commands as LEGENDARY
        return LEGENDARY.observe_control(self.e,c,**observation)

    def end_legendary_control(self, c, application_id, *, reason):
        import legendary_commands as LEGENDARY
        return LEGENDARY.end_control(self.e,c,application_id,reason=reason)

    def set_actor_description(self, c, changes, *, reason, request_id=None, expected_revision=None):
        """Record narrative facts without changing mechanical Nature or identity."""
        if not isinstance(changes, dict) or not changes or not set(changes) <= set(STATE_FIELDS.DESCRIPTION_FIELDS):
            raise ValueError("explicit narrative description fields required")
        return STATE_FIELDS.base_patch(c, changes, reason=reason,
            source="gm/actor-description", request_id=request_id, expected_revision=expected_revision)

    def observe_actor_measurements(self, c, changes, *, reason, request_id=None, expected_revision=None):
        """Individual observations remain independent of species averages."""
        if not isinstance(changes, dict) or not changes or not set(changes) <= set(STATE_FIELDS.MEASUREMENT_FIELDS):
            raise ValueError("explicit individual measurement fields required")
        return STATE_FIELDS.base_patch(c, changes, reason=reason,
            source="gm/individual-measurements", request_id=request_id, expected_revision=expected_revision)

    def transfer_egg(self, old_owner, new_owner, egg_entity_id, **options):
        import pokemon_entities as ENTITIES
        return ENTITIES.transfer_egg(self.e, old_owner, new_owner, egg_entity_id, **options)

    def set_encounter_template(self, c, **options):
        import actor_templates as TEMPLATES
        return TEMPLATES.configure(self.e, c, **options)

    def record_encounter_template(self, c, **options):
        import actor_templates as TEMPLATES
        return TEMPLATES.record(self.e, c, **options)

    def set_multipart_entity(self, **options):
        import actor_templates as TEMPLATES
        return TEMPLATES.multipart(self.e, **options)

    def relocate_multipart_entity(self, **options):
        import actor_templates as TEMPLATES
        return TEMPLATES.relocate_multipart(self.e, **options)

    def set_physical_object(self, object_id, **options):
        import capability_actions as CAPABILITIES
        return CAPABILITIES.set_object(self.e,object_id,**options)

    def grant_starting_pokedex(self, actor, instance_id, **observation):
        import pokedex_device as POKEDEX
        return POKEDEX.starting(self.e, actor, instance_id, **observation)

    def set_carried_objects(self, c, objects, reason, **options):
        import capability_actions as CAPABILITIES
        return CAPABILITIES.set_carried(self.e,c,objects,reason,**options)

    def observe_mapless_scene(self, **observation):
        import mapless_space as MAPLESS
        return MAPLESS.configure(self.e, **observation)

    def adopt_enemy_accuracy_sheet(self, **observation):
        import fast_combat as FAST_COMBAT
        return FAST_COMBAT.adopt(self.e, **observation)

    def observe_mapless_targets(self, actor, **observation):
        import mapless_space as MAPLESS
        return MAPLESS.observe_targets(self.e, actor, **observation)

    def observe_mapless_movement(self, actor, **observation):
        import mapless_space as MAPLESS
        return MAPLESS.observe_movement(self.e, actor, **observation)

    def observe_environmental_item(self, c, instance_id, **options):
        import environmental_item_state as ENVIRONMENTAL_ITEMS
        return ENVIRONMENTAL_ITEMS.observe(self.e, c, instance_id, **options)

    def observe_environmental_attack(self, c, instance_id, **options):
        import environmental_attacks as ENVIRONMENTAL_ATTACKS
        return ENVIRONMENTAL_ATTACKS.observe(self.e, c, instance_id, **options)

    def recover_environmental_item(self, c, instance_id, **options):
        import environmental_item_state as ENVIRONMENTAL_ITEMS
        return ENVIRONMENTAL_ITEMS.recover(self.e, c, instance_id, **options)

    def resolve_carry_failure(self,c,*,outcome,reason):
        import capability_actions as CAPABILITIES
        return CAPABILITIES.resolve_carry_failure(self.e,c,outcome=outcome,reason=reason)

    def set_hp(self, c, value=None, delta=None, reason="", unpreventable=True):
        import keep_fighting as KEEP,state_grants as GRANTS
        nonpositive=(M.floor(value) if value is not None else c.hp+M.floor(delta))<=0
        if KEEP.interested(self.e,c) or nonpositive:
            return GRANTS.transition(self.e,c,lambda e,actor:e.gm._set_hp(actor,value=value,delta=delta,reason=reason,unpreventable=unpreventable),include_rulings=True,include_grid=self.e.grid is not None)
        return self._set_hp(c,value=value,delta=delta,reason=reason,unpreventable=unpreventable)

    def _set_hp(self, c, value=None, delta=None, reason="", unpreventable=True):
        before = c.hp
        proposed = min(M.floor(value) if value is not None else c.hp + M.floor(delta),c.base_max_hp)
        import keep_fighting as KEEP
        c.hp = KEEP.replace_hp(self.e,c,before,proposed,source='gm/state',loss_kind='gm_set',amount=max(0,before-proposed),unpreventable=unpreventable)
        BANDAGES.on_hp_change(self.e,c,before,c.hp)
        self._rec("체력", before, c.hp, reason, c)
        import taskmaster as TASK
        press=TASK.faint_boundary(self.e,c)
        if c.hp <= 0 and not press:
            import life as LIFE,core_weather_abilities as WEATHER_ABILITIES
            # A GM-observed knockout owns the same source endings as native HP loss.
            # The existing Press decision above still owns remaining conscious.
            newly_fainted=LIFE.faint(self.e,c)
            WEATHER_ABILITIES.refresh(c)
            if newly_fainted:self.e.log(f"    {c.name} 기절 (GM 조정)", "gm/state")
        elif c.hp > 0 and "기절" in c.conditions:
            c.conditions.discard("기절")
            import life
            life.clear_recovery(c)
            self.e.log(f"    {c.name} 기절 해제 (GM 조정)", "gm/state")
        return c.hp

    def set_temp_hp(self, c, value, reason="", *, duration_seconds=None, round_offset_seconds=None):
        before = c.temp_hp
        TEMP_HP.gm_set(self.e,c,value,duration_seconds=duration_seconds,round_offset_seconds=round_offset_seconds)
        self._rec("임시 체력 GM 개변", before, c.temp_hp, reason, c)

    def set_injuries(self, c, value=None, delta=None, reason=""):
        before = c.injuries
        hp_before=c.hp
        proposed = max(0, M.floor(value) if value is not None else c.injuries + M.floor(delta))
        import actor_templates as TEMPLATES
        if proposed and TEMPLATES.injuries_immune(c):
            raise ValueError("Injury immunity requires a rule override before assigning injuries")
        import environmental_effects as ENVIRONMENT
        if proposed<ENVIRONMENT.protected_injuries(c):raise ValueError("protected injuries require their actual recovery source")
        c.injuries = proposed
        import precise_actions as PRECISE
        PRECISE.injury(self.e,c,c.injuries-before,"gm/injury")
        self.e.check_fainted(c)
        self._rec("부상", before, f"{c.injuries} (최대 체력 {c.max_hp})", reason, c)

    def set_stage(self, c, stat, value=None, delta=None, reason=""):
        import state_grants as GRANTS
        stat = STAT_KO.get(stat, stat)
        lo, hi = self.e.r.mech("combat/combat-stages")["range"]
        if stat == "acc":
            before = c.accuracy_stage
            wanted = max(lo, min(hi, M.floor(value) if value is not None else c.accuracy_stage + M.floor(delta)))
            if not GRANTS.assign_numeric(c, "accuracy_stage", wanted):
                c.accuracy_stage = wanted
            self._rec("명중 단계", before, c.accuracy_stage, reason, c)
        elif stat == "eva":
            before = c.evasion_mod
            wanted = max(lo, min(hi, M.floor(value) if value is not None else c.evasion_mod + M.floor(delta)))
            if not GRANTS.assign_numeric(c, "evasion_mod", wanted):
                c.evasion_mod = wanted
            self._rec("회피 보정", before, c.evasion_mod, reason, c)
        else:
            import combat_stage_sources as STAGES
            if stat not in STAGES.STATS:raise ValueError("only five non-HP combat stages can be assigned")
            before = c.stages[stat]
            wanted = max(lo, min(hi, M.floor(value) if value is not None else before + M.floor(delta)))
            STAGES.assign_combat(c, {stat: wanted})
            self._rec(f"{stat} 전투단계", f"{before:+d}", f"{c.stages[stat]:+d}", reason, c)

    def add_condition(self, c, cond, reason="", force=True, *, parameters=None, applied_by=None):
        """force=True 면 타입 면역·중복 검사를 건너뛰고 GM 권한으로 부여한다."""
        before = sorted(c.conditions)
        if cond=='맹독':
            result=self.e.apply_status(c,cond,source='gm/condition/맹독',applied_by=applied_by,force=force)
            self._rec('상태',before,sorted(c.conditions),reason,c)
            return result
        import condition_instances as CONDITIONS
        if cond in CONDITIONS.SUPPORTED:
            result=CONDITIONS.grant(self.e,c,cond,source='gm/condition/'+cond,parameters=parameters,applied_by=applied_by,force=force)
            self._rec('상태',before,sorted(c.conditions),reason,c)
            return result
        if f"condition/{cond}" in self.e.r.units:
            import status_sets as STATUS_SETS
            if not STATUS_SETS.can_apply(self.e,c,cond):return
        if force:
            if cond in c.conditions:
                self.e.log(f"    {c.name}은(는) 이미 {cond}", "gm/state")
                return
            import condition_recovery as RECOVERY
            RECOVERY.invalidate(c,cond)
            c.conditions.add(cond)
            if cond=='잠듦':
                import dream_state as DREAM
                DREAM.applied(c,'gm/state')
            for ef in self.e.r.condition_effects(cond) if f"condition/{cond}" in self.e.r.units else []:
                if ef["type"] == "combat_stage" and ef.get("while") == "afflicted":
                    import combat_state_lifecycle as COMBAT_STATE
                    COMBAT_STATE.apply_condition_stage(self.e,c,cond,ef)
        else:
            self.e.apply_status(c, cond)
        self._rec("상태", before, sorted(c.conditions), reason, c)

    def remove_condition(self, c, cond, reason=""):
        before = sorted(c.conditions)
        if cond == "전부":
            for x in list(c.conditions):
                self.e.cure_status(c, x)
            c.conditions.clear()
        else:
            self.e.cure_status(c, cond)
            c.conditions.discard(cond)
        import condition_recovery as RECOVERY
        RECOVERY.invalidate(c,None if cond == "전부" else cond)
        self._rec("상태", before, sorted(c.conditions), reason, c)

    def set_custom(self, c, name, value=True, reason=""):
        before = c.custom_conditions.get(name)
        if value is None or value is False:
            c.custom_conditions.pop(name, None)
        else:
            c.custom_conditions[name] = value if isinstance(value, dict) else {"gm": True, "note": value}
        self._rec(f"고유 상태 {name}", before, c.custom_conditions.get(name), reason, c)

    def set_position(self, c, pos, reason=""):
        import actor_templates as TEMPLATES
        if not TEMPLATES.multipart_can_place(self.e,c,tuple(pos)):
            raise ValueError("multipart position exceeds its starting-position region; whole reposition required")
        before = copy.deepcopy(c.location)
        c.pos = tuple(pos)
        import survivalist_features as SURVIVAL
        SURVIVAL.position_changed(self.e,c,event='GM set_position')
        import body_modes as BODY_MODES
        BODY_MODES.sync_shadows(self.e)
        import effect_lifetime_policy as LIFETIMES
        LIFETIMES.reconcile(self.e)
        self._rec("위치", before, copy.deepcopy(c.location), reason, c)

    def set_item(self, c, item, reason="", *, selection=None, source_instance_id=None):
        import items as ITEMS
        import held_equipment as HELD
        before = copy.deepcopy(HELD.entries(c))
        ITEMS.replace_item(self.e,c,item or None,selection=selection,source_instance_id=source_instance_id)
        self._rec("도구",before,copy.deepcopy(HELD.entries(c)),reason,c)

    def add_buff(self, c, buff, reason=""):
        import effect_instances as INSTANCES
        if isinstance(buff,dict) and INSTANCES.KEY in buff:
            import state_grants as G,world_entities as W
            def apply(e,actor):
                before=copy.deepcopy(actor.buffs)
                actor.buffs.append(copy.deepcopy(buff))
                INSTANCES.validate_world(e,W.actor_index(e))
                e.gm._rec('버프',before,actor.buffs,reason,actor)
            return G.transition(self.e,c,apply)
        before = list(c.buffs)
        c.buffs.append(buff)
        self._rec("버프", before, list(c.buffs), reason, c)

    def set_move(self, c, move_id, add=True, reason=""):
        import state_grants as GRANTS
        before = list(c.moves)
        baseline = list(c.spec.get("moves", []))
        canonical = self.e.r.move_id(move_id)
        if canonical is None:raise ValueError("known canonical move or alias required")
        matches = [value for value in baseline if self.e.r.move_id(value) == canonical]
        if add and not matches:
            baseline.append(canonical)
        elif not add:
            baseline = [value for value in baseline if value not in matches]
        GRANTS.replace_baseline(self.e, c, "moves", baseline)
        self._rec("영구 기술", before, list(c.moves), reason, c)

    def set_ability(self, c, name, add=True, reason=""):
        import state_grants as GRANTS
        before = list(c.abilities)
        baseline = list(c.spec.get("abilities", []))
        if add and name not in baseline:
            baseline.append(name)
        elif not add and name in baseline:
            baseline.remove(name)
        GRANTS.replace_baseline(self.e, c, "abilities", baseline)
        self._rec("영구 특성", before, list(c.abilities), reason, c)

    def observe_pledge_rainbow(self, c, **observation):
        """Record an already activated Rainbow without executing Pledge turns."""
        import pledge_state as PLEDGE
        return PLEDGE.observe(self.e,c,**observation)

    def observe_type_sync(self, c, **options):
        import type_sync as TYPE_SYNC
        return TYPE_SYNC.observe(self.e,c,**options)

    def observe_move_type_sync(self, c, **options):
        import move_type_sync as MOVE_TYPE_SYNC
        return MOVE_TYPE_SYNC.observe(self.e,c,**options)

    def set_types(self, c, types, reason=""):
        before = list(c.types)
        STATE_FIELDS.base_patch(c, {"types": list(types)}, reason=reason or "explicit GM base-type edit")
        import csv_item_capability_contracts as CSV_CAP
        CSV_CAP.sync_essence(self.e,c)
        self._rec("타입", before, c.types, reason, c)

    def set_stat(self, c, stat, value=None, delta=None, reason=""):
        stat = STAT_KO.get(stat, stat)
        before = c.stats[stat]
        base = c.spec["stats"][stat]
        proposed = dict(c.spec["stats"])
        proposed[stat] = M.floor(value) if value is not None else base + M.floor(delta)
        import mixed_sweeper as MIXED
        if MIXED.records(c.spec):
            import state_grants as G
            G.transition(self.e,c,lambda se,st:STATE_FIELDS.base_patch(st,{"stats":proposed},reason=reason or 'explicit GM base-stat edit'))
        else:
            STATE_FIELDS.base_patch(c, {"stats": proposed}, reason=reason or "explicit GM base-stat edit")
        self._rec(f"기본 스탯 {stat}", before, c.stats[stat], reason, c)

    def set_skill(self,c,skill,value,*,reason,request_id=None):
        """Observe a permanent skill pool, including source-required refunds."""
        import skill_modifiers as SKILL
        sid=SKILL.skill_id(self.e.r.skill_policy,skill,required=True)
        skills={k:v for k,v in c.spec.get('skills',{}).items() if SKILL.skill_id(self.e.r.skill_policy,k)!=sid}
        skills[sid]=value
        receipt=STATE_FIELDS.base_patch(c,{'skills':skills},reason=reason,source='gm/permanent-skill',request_id=request_id)
        return receipt

    def set_level(self, c, value, reason=""):
        before = c.level
        import state_grants as G
        # Every level edit includes formula refresh and native prerequisite-loss
        # reconciliation, even when no previously selected edge family is owned.
        def complete(e,actor):
            e.gm._rec("레벨", before, f"{actor.level} (최대 체력 {actor.max_hp})", reason, actor)
        G.transition(self.e,c,lambda se,st:STATE_FIELDS.base_patch(st,{'level':M.floor(value)},
            reason=reason or 'explicit GM level edit'),include_rulings=True,completion=complete)

    def set_counter(self, c, name, value, reason=""):
        before = c.counters.get(name, 0)
        c.counters[name] = M.floor(value)
        self._rec(f"카운터 {name}", before, c.counters[name], reason, c)

    def set_initiative(self, c, value, reason=""):
        before = c.initiative_override
        import combat_timing as TIMING
        TIMING.on_initiative_override(c)
        c.initiative_override = M.floor(value)
        self._rec("이니셔티브 고정", before, c.initiative_override, reason, c)

    def revive(self, c, hp=None, reason=""):
        import life
        before = dict(hp=c.hp,dead=c.dead)
        c.dead=False
        life.clear_recovery(c)
        c.conditions.discard("기절")
        c.hp = M.floor(hp) if hp is not None else max(1, M.ratio(c.max_hp,4))
        BANDAGES.on_hp_change(self.e,c,before["hp"],c.hp)
        self._rec("소생", before, c.hp, reason, c)

    def faint(self, c, reason=""):
        import keep_fighting as KEEP,state_grants as GRANTS
        if KEEP.interested(self.e,c):
            return GRANTS.transition(self.e,c,lambda e,actor:e.gm._faint(actor,reason=reason),include_rulings=True,include_grid=self.e.grid is not None)
        return self._faint(c,reason=reason)

    def _faint(self, c, reason=""):
        before = c.hp
        import keep_fighting as KEEP
        c.hp = KEEP.replace_hp(self.e,c,before,0,source='gm/state',loss_kind='gm_faint',amount=max(0,before),unpreventable=True)
        BANDAGES.on_hp_change(self.e,c,before,c.hp)
        import life as LIFE
        if c.hp<=0:LIFE.sync(self.e,c)
        self._rec("기절 처리", before, c.hp, reason, c)

    def recall(self, c, reason=""):
        before = c.on_field
        import combat_state_lifecycle as COMBAT_STATE,state_grants as GRANTS
        GRANTS.transition(self.e,c,lambda staged,actual:COMBAT_STATE.recall(staged,actual,ignore_trapped=True))
        self._rec("퇴장(볼 복귀)", before, False, reason, c)

    def send_out(self, c, pos=None, reason=""):
        import combat_state_lifecycle as COMBAT_STATE,state_grants as GRANTS
        before=c.on_field
        GRANTS.transition(self.e,c,lambda staged,actual:COMBAT_STATE.send_out(staged,actual,pos=pos,source_id='gm/send-out'),include_grid=self.e.grid is not None)
        self._rec("등장",before,True,reason,c)

    def add_combatant(self, c, pos=None, side=None, reason=""):
        import world_entities as WORLD
        import state_grants as GRANTS
        WORLD.actor_index(self.e, (c,))
        STATE_FIELDS.validate_base(c.spec)
        if side is not None and (not isinstance(side, str) or not side.strip()):
            raise ValueError("side requires explicit nonempty text")
        def apply(staged_engine, staged_c):
            if pos is not None:
                staged_c.pos = tuple(pos)
            if side is not None:
                staged_c.side = side
            for roster in (staged_engine.gm.everyone, staged_engine.everyone):
                if staged_c not in roster:
                    roster.append(staged_c)
            staged_engine.register_abilities(staged_c)
            # A newly imported sheet gets its while-owned projections here.
            STATE_FIELDS.validate_actor(staged_c)
        GRANTS.transition(self.e, c, apply)
        for roster in (self.everyone, self.e.everyone):
            if c not in roster:
                roster.append(c)
        if self.e.encounter_active and c.on_field:
            import combat_state_lifecycle as COMBAT_STATE
            COMBAT_STATE.join(self.e,[c])
        self._rec("참가자 추가", None, f"{c.name} @{c.location} ({c.side})", reason)
        return c

    def remove_combatant(self, c, reason=""):
        for roster in (self.everyone, self.e.everyone):
            if c in roster:
                roster.remove(c)
        c.on_field = False
        self._rec("참가자 제거", c.name, None, reason)

    # ---------- 전장 상태 ----------
    def set_weather(self, weather, rounds=5, reason=""):
        import weather_state as WEATHER
        before = self.e.weather
        result=WEATHER.set_weather(self.e,WEATHER_KO.get(weather,weather),rounds=rounds,source_id='gm/weather',origin='gm',reason=reason)
        self._rec("날씨", before, self.e.weather, reason)
        return result

    def observe_natural_weather(self, description, *, treat_as=None, reason=""):
        import weather_state as WEATHER
        result=WEATHER.observe_natural(self.e,description,treat_as=WEATHER_KO.get(treat_as,treat_as),reason=reason)
        self._rec("자연 날씨 관찰",None,result,reason)
        return result

    def set_field(self, name, rounds=5, reason=""):
        before = (self.e.field or {}).get("name")
        import field_effects as FIELD
        if name:
            FIELD.validate(self.e)
            FIELD._store(self.e, {"name": name, "rounds": rounds, "effect": "GM"})
            import items as ITEMS
            ITEMS.synchronize_field_suppression(self.e)
        else:
            FIELD.clear(self.e)
        self._rec("필드", before, name, reason)

    def place_hazard(self, cell, name, effects=None, reason=""):
        before = (self.e.hazards.get(tuple(cell)) or {}).get("name")
        import hazard_state as HAZARDS
        HAZARDS.place_legacy(self.e,cell,name,effects,owner="GM")
        self._rec(f"함정 {tuple(cell)}", before, name, reason)

    def clear_hazards(self, reason=""):
        before = len(self.e.hazards)
        import hazard_state as HAZARDS
        HAZARDS.clear(self.e)
        self._rec("함정 전부 제거", before, 0, reason)

    def set_terrain(self, cell, kind, on=True, reason=""):
        if self.e.grid is None:
            return
        store = {"slow": self.e.grid.slow, "rough": self.e.grid.rough, "blocking": self.e.grid.blocking, "둔화": self.e.grid.slow, "험한": self.e.grid.rough, "차단": self.e.grid.blocking}[kind]
        before = tuple(cell) in store
        (store.add if on else store.discard)(tuple(cell))
        self._rec(f"지형 {kind} {tuple(cell)}", before, on, reason)

    # ---------- 스냅샷 / 되돌리기 ----------
    def _snapshot_actors(self, engine_state):
        """Find participant references in the supported state graph.

        The participant protocol avoids importing Engine while it is running as
        __main__. It also includes off-field actors referenced only by a delayed
        effect or the clock, rather than treating the current turn roster as all
        actors. Actor objects are identity anchors; their field values are copied.
        """
        actors = {}
        seen = set()

        def visit(value):
            identity = id(value)
            if identity in seen:
                return
            seen.add(identity)
            if all(hasattr(value, field) for field in ("spec", "hp", "conditions", "stages")):
                actors[identity] = value
                for field, child in vars(value).items():
                    if field != "r":
                        visit(child)
            elif isinstance(value, dict):
                for key, child in value.items():
                    visit(key)
                    visit(child)
            elif isinstance(value, (list, tuple, set, frozenset)):
                for child in value:
                    visit(child)
            elif dataclasses.is_dataclass(value) and not isinstance(value, type):
                for field in dataclasses.fields(value):
                    visit(getattr(value, field.name))

        visit(self.everyone)
        visit(getattr(self.e, "everyone", []))
        visit(engine_state)
        return actors

    def observe_empty_container(self, actor, **options):
        import item_containers as CONTAINERS
        return CONTAINERS.observe_empty(self.e,actor,**options)

    def snapshot(self, name="snap"):
        TEMP_HP.loss_policy(self.e)
        engine_state = {k: getattr(self.e, k) for k in ENGINE_FIELDS if hasattr(self.e, k)}
        actors = self._snapshot_actors(engine_state)
        import gameplay_validation as GAMEPLAY
        GAMEPLAY.validate(self.e, actors.values())
        engine_state = {k: getattr(self.e, k) for k in ENGINE_FIELDS if hasattr(self.e, k)}
        state = {"snapshot_version": 2,
                 "combatants": {identity: vars(c) for identity, c in actors.items()},
                 "engine": engine_state,
                 "gm_everyone": self.everyone,
                 "grid": vars(self.e.grid) if self.e.grid is not None else None,
                 "rng_state": self.e.rng.getstate(),
                 "log_len": len(self.e.log_lines)}
        # One graph copy preserves mutable aliases across actor and engine state;
        # memoized actor identities prevent queued targets from becoming clones.
        snap = copy.deepcopy(state, {**actors,id(self.e):self.e,id(self.e.r):self.e.r})
        snap["actor_refs"] = dict(actors)
        snap["grid_ref"] = self.e.grid
        self.snapshots[name] = snap
        self.e.log(f"    [GM 상태] 스냅샷 '{name}' ({len(actors)}명)", "gm/snapshot")
        return name

    def restore(self, name="snap", reason=""):
        snap = self.snapshots[name]
        actors = snap.get("actor_refs")
        if actors is None:  # Older in-memory snapshots only tracked the GM roster.
            actors = {id(c): c for c in self.everyone}
        # Copy the complete value graph once per replay. The snapshot remains
        # isolated from later mutations, while actor references stay live.
        restored = copy.deepcopy({k: v for k, v in snap.items() if k not in ("actor_refs", "grid_ref")}, {**actors,id(self.e):self.e,id(self.e.r):self.e.r})
        # Check new permanent-use receipts before replacing any live actor.
        # Older snapshots without this optional ledger keep their unknown history.
        if restored.get("snapshot_version", 1) >= 2:
            # Validate a complete candidate graph: its actor references must
            # point to candidate actors, not the still-live objects that will
            # receive the restored dictionaries only after validation succeeds.
            staged={identity:copy.copy(c) for identity,c in actors.items() if identity in restored["combatants"]}
            candidate_engine=copy.copy(self.e)
            # Native transient attribution (for example _inflictor) can also
            # refer to actors. Validate it against the candidate actor graph.
            transient={key:value for key,value in vars(self.e).items() if key not in ENGINE_FIELDS and key not in ('r','gm','rulings','rng')}
            candidate_engine.__dict__.update(copy.deepcopy(transient,{**staged,id(self.e):candidate_engine,id(self.e.r):self.e.r,id(self):self}))
            checked=copy.deepcopy(restored,{**staged,id(self.e):candidate_engine,id(self.e.r):self.e.r})
            candidate_engine.rng=copy.deepcopy(self.e.rng)
            candidate_engine.rng.setstate(checked['rng_state'])
            candidate_engine.gm=copy.copy(self)
            candidate_engine.gm.e=candidate_engine
            candidate_engine.gm.everyone=checked['gm_everyone']
            candidates={}
            for identity,candidate in staged.items():
                candidate.__dict__=checked["combatants"][identity];candidate.r=self.e.r
                candidates[candidate.entity_id]=candidate
            for field in ENGINE_FIELDS:
                if field in checked['engine']:setattr(candidate_engine,field,checked['engine'][field])
                elif hasattr(candidate_engine,field):delattr(candidate_engine,field)
            # Validate the saved map, never the current live Grid. Its value
            # graph was copied with the candidate actors, preserving aliases.
            if checked['grid'] is None:
                candidate_engine.grid = None
            else:
                from grid import Grid
                candidate_engine.grid = Grid.__new__(Grid)
                candidate_engine.grid.__dict__ = checked['grid']
            import equipment_suppression as EQUIPMENT_SUPPRESSION
            EQUIPMENT_SUPPRESSION.upgrade_legacy(candidate_engine, candidates)
            import equipment_variant_contracts as EQUIPMENT_VARIANTS
            EQUIPMENT_VARIANTS.upgrade_legacy_slipstream(candidate_engine)
            import gameplay_validation as GAMEPLAY
            GAMEPLAY.validate(candidate_engine, candidates.values())
            # Transfer only the authenticated legacy-marker upgrade from the
            # candidate graph after every candidate validation has succeeded.
            for identity,candidate in staged.items():
                for key,row in getattr(candidate,'_item_reg',{}).items():
                    original=restored['combatants'][identity].get('_item_reg',{}).get(key)
                    if original is not None and EQUIPMENT_SUPPRESSION.KEY in row:
                        original[EQUIPMENT_SUPPRESSION.KEY]=copy.deepcopy(row[EQUIPMENT_SUPPRESSION.KEY])
            for uid,obj in getattr(candidate_engine,'_physical_objects',{}).items():
                state=obj.get(EQUIPMENT_VARIANTS.OBJECT_STATE)
                if isinstance(state,dict) and state.get('kind') in EQUIPMENT_VARIANTS.SLIPSTREAM_KINDS:
                    original=restored['engine']['_physical_objects'][uid][EQUIPMENT_VARIANTS.OBJECT_STATE]
                    for key in ('encounter_scope_version','legacy_encounter_scope'):
                        if key in state and key not in original:original[key]=copy.deepcopy(state[key])
        for identity, c in actors.items():
            st = restored["combatants"].get(identity)
            if st is None:
                continue
            if restored.get("snapshot_version", 1) >= 2:
                c.__dict__ = st
                c.r = self.e.r
            else:
                for k in COMBATANT_FIELDS:
                    if k in st:
                        setattr(c, k, st[k])
                    elif hasattr(c, k):
                        delattr(c, k)
        for field in ENGINE_FIELDS:
            if field in restored["engine"]:
                setattr(self.e, field, restored["engine"][field])
            elif hasattr(self.e, field):
                delattr(self.e, field)
        if "gm_everyone" in restored:
            self.everyone = restored["gm_everyone"]
        if restored.get("snapshot_version", 1) >= 2:
            self.e.grid = snap["grid_ref"]
            if self.e.grid is not None:
                self.e.grid.__dict__ = restored["grid"]
            self.e.rng.setstate(restored["rng_state"])
        elif restored["grid"] is not None and self.e.grid is not None:
            self.e.grid.slow, self.e.grid.rough, self.e.grid.blocking, self.e.grid.walls = restored["grid"]
        # Pending root sessions are not durable snapshots. Even restoring an
        # identical gameplay graph invalidates all old authenticated inputs.
        self.e._root_common_epoch = getattr(self.e, "_root_common_epoch", 0) + 1
        self.e.rulings.record("state", f"되돌리기 '{name}'", None, None, reason, "once")
        self.e.log(f"    [GM 상태] 스냅샷 '{name}' 으로 되돌림" + (f" ({reason})" if reason else ""), "gm/restore")

    # ---------- 문자열 명령 ----------
    def command(self, line):
        """'<대상> <필드> [값] [-- 이유]'. 예: '아치 hp 30', '아치 hp -10', '뚜벅초 A +독', '뚜벅초 A -독', '마야 atk +2', '마야 명중 +1',
        '아치 부상 2', '아치 위치 5,5', '아치 도구 오랭열매', '아치 소생', '아치 기절', '아치 퇴장', '아치 등장 3,3', '전원 상태 -둔화', '날씨 비', '필드 그래스',
        '함정 4,4 압정', '지형 둔화 5,5', '스냅샷 이름', '되돌리기 이름', '아치 기술 +move/불꽃세례', '아치 특성 +맹화', '아치 타입 불꽃,비행', '아치 레벨 25', '아치 카운터 stockpile 2'."""
        reason = ""
        if "--" in line:
            line, reason = [x.strip() for x in line.split("--", 1)]
        toks = line.split()
        if not toks:
            return "빈 명령"
        head = toks[0]
        if head in ("날씨", "weather"):
            self.set_weather(toks[1] if len(toks) > 1 else None, reason=reason); return "ok"
        if head in ("필드", "field"):
            self.set_field(toks[1] if len(toks) > 1 and toks[1] != "없음" else None, reason=reason); return "ok"
        if head in ("함정", "hazard"):
            self.place_hazard(_xy(toks[1]), toks[2] if len(toks) > 2 else "함정", reason=reason); return "ok"
        if head in ("지형", "terrain"):
            self.set_terrain(_xy(toks[2]), toks[1], on=not (len(toks) > 3 and toks[3] in ("off", "해제")), reason=reason); return "ok"
        if head in ("스냅샷", "snapshot"):
            return self.snapshot(toks[1] if len(toks) > 1 else "snap")
        if head in ("되돌리기", "restore", "rewind"):
            self.restore(toks[1] if len(toks) > 1 else "snap", reason); return "ok"
        # 대상 이름은 공백을 포함할 수 있다('뚜벅초 A'): 필드 키워드가 나올 때까지 합친다
        fields = {"hp", "체력", "temp", "임시", "부상", "injuries", "상태", "cond", "위치", "pos", "도구", "item", "버프", "buff", "기술", "move", "특성", "ability", "타입", "types",
                  "레벨", "level", "카운터", "counter", "소생", "revive", "기절", "faint", "퇴장", "recall", "등장", "sendout", "스탯", "stat", "이니셔티브", "init", "고유", "custom"} | set(STAT_KO)
        i = 1
        while i < len(toks) and toks[i] not in fields and not toks[i].startswith(("+", "-")):
            i += 1
        name = " ".join(toks[:i])
        rest = toks[i:]
        if not rest:
            return "필드 없음"
        targets = self.find(name)
        f = rest[0]
        arg = rest[1] if len(rest) > 1 else None
        for c in targets:
            if f.startswith(("+", "-")) and f[1:] and not f[1:].isdigit():          # '+독' / '-독'
                (self.add_condition if f[0] == "+" else self.remove_condition)(c, f[1:], reason)
            elif f in ("hp", "체력"):
                self._num(self.set_hp, c, arg, reason)
            elif f in ("temp", "임시"):
                self.set_temp_hp(c, int(arg), reason)
            elif f in ("부상", "injuries"):
                self._num(self.set_injuries, c, arg, reason)
            elif f in ("상태", "cond"):
                if arg and arg[0] in "+-":
                    (self.add_condition if arg[0] == "+" else self.remove_condition)(c, arg[1:], reason)
                else:
                    self.remove_condition(c, "전부", reason) if arg in (None, "없음", "clear") else self.add_condition(c, arg, reason)
            elif f in STAT_KO:
                if STAT_KO[f] in ("acc", "eva") or f in ("명중", "회피"):
                    self._num(lambda cc, **kw: self.set_stage(cc, f, **kw), c, arg, reason)
                else:
                    self._num(lambda cc, **kw: self.set_stage(cc, f, **kw), c, arg, reason)
            elif f in ("스탯", "stat"):
                self._num(lambda cc, **kw: self.set_stat(cc, rest[1], **kw), c, rest[2] if len(rest) > 2 else None, reason)
            elif f in ("위치", "pos"):
                self.set_position(c, _xy(arg), reason)
            elif f in ("도구", "item"):
                self.set_item(c, None if arg in (None, "없음") else arg, reason)
            elif f in ("버프", "buff"):
                self.add_buff(c, arg, reason)
            elif f in ("기술", "move"):
                self.set_move(c, arg.lstrip("+-"), add=not arg.startswith("-"), reason=reason)
            elif f in ("특성", "ability"):
                self.set_ability(c, arg.lstrip("+-"), add=not arg.startswith("-"), reason=reason)
            elif f in ("타입", "types"):
                self.set_types(c, arg.split(","), reason)
            elif f in ("레벨", "level"):
                self.set_level(c, int(arg), reason)
            elif f in ("카운터", "counter"):
                self.set_counter(c, rest[1], rest[2], reason)
            elif f in ("고유", "custom"):
                self.set_custom(c, rest[1], rest[2] if len(rest) > 2 else True, reason)
            elif f in ("소생", "revive"):
                self.revive(c, int(arg) if arg else None, reason)
            elif f in ("기절", "faint"):
                self.faint(c, reason)
            elif f in ("퇴장", "recall"):
                self.recall(c, reason)
            elif f in ("등장", "sendout"):
                self.send_out(c, _xy(arg) if arg else None, reason)
            elif f in ("이니셔티브", "init"):
                self.set_initiative(c, int(arg), reason)
            else:
                return f"모르는 필드: {f}"
        return "ok"

    def _num(self, fn, c, arg, reason):
        if arg is None:
            raise ValueError("값 없음")
        if arg[0] in "+-":
            fn(c, delta=int(arg), reason=reason)
        else:
            fn(c, value=int(arg), reason=reason)

    def show(self):
        return "; ".join(repr(c) + ("" if c.on_field else "(퇴장)") for c in self.everyone) + f" | 날씨 {self.e.weather} 필드 {(self.e.field or {}).get('name')} 함정 {len(self.e.hazards)}"


def _xy(s):
    a, b = str(s).replace("(", "").replace(")", "").split(",")
    return (int(a), int(b))

