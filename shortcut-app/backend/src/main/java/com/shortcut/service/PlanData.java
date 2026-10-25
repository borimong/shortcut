package com.shortcut.service;

import com.shortcut.domain.Actor;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.Block;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.ForecastInfo;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import com.shortcut.domain.Scene;
import com.shortcut.domain.SceneCharacter;
import com.shortcut.domain.SceneRequirement;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.engine.ActorDay;
import com.shortcut.engine.BlockSlot;
import com.shortcut.engine.PlanEngine;
import com.shortcut.engine.PlanInput;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.engine.ScenePlan;
import com.shortcut.engine.SceneSlot;
import java.util.ArrayList;
import java.time.LocalTime;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * 한 촬영일의 계획 데이터를 한 번에 읽어 둔 묶음이다.
 * 엔진 입력, 촬영판, 내부 조회가 같은 스냅숏을 보도록 여기서 변환한다.
 */
public record PlanData(
        ShootDay shootDay,
        List<Block> blocks,
        List<Scene> scenes,
        Map<Long, Actor> actors,
        Map<Long, Location> locations,
        Map<Long, Equipment> equipment,
        List<PlanOption> options,
        List<WeatherHour> weather,
        ForecastInfo forecast,
        List<DisasterAlert> alerts,
        List<Long> alternativeLocationIds,
        AppSettings settings,
        Map<Long, ActorDay> actorDays) {

    public static final String CHANGING_BLOCK = "PM";

    /** 날짜별 배우 일정 없이 만든 묶음이다. 배우는 계약 기본 시간으로 본다. */
    public PlanData(ShootDay shootDay, List<Block> blocks, List<Scene> scenes, Map<Long, Actor> actors,
                    Map<Long, Location> locations, Map<Long, Equipment> equipment, List<PlanOption> options,
                    List<WeatherHour> weather, ForecastInfo forecast, List<DisasterAlert> alerts,
                    List<Long> alternativeLocationIds, AppSettings settings) {
        this(shootDay, blocks, scenes, actors, locations, equipment, options, weather, forecast, alerts,
                alternativeLocationIds, settings, Map.of());
    }

    /** 배우의 그날 일정이다. 날짜별 일정이 없으면 계약 기본 시간(변경 입력 반영) 하나로 본다. */
    public ActorDay actorDay(long actorId) {
        ActorDay day = actorDays.get(actorId);
        return day != null ? day : ActorDay.of(actors.get(actorId));
    }

    public Block changingBlock() {
        return blocks.stream()
                .filter(block -> CHANGING_BLOCK.equals(block.code()))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("오후 블록이 없습니다."));
    }

    /** 오후 블록 확정안이다. 씬 시각표는 지금 씬 순서(scenes.sort)로 블록 시작부터 쌓는다. */
    public PlanSnapshot current() {
        Block pm = changingBlock();
        List<ScenePlan> scenes = scenesOf(CHANGING_BLOCK).stream().map(PlanData::scenePlan).toList();
        return snapshot(pm.locationId(), pm.equipmentIds(), pm.start(), pm.end(),
                PlanEngine.timetable(scenes, pm.start()));
    }

    public PlanSnapshot snapshot(long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end,
                                 List<SceneSlot> scenes) {
        long cost = locations.get(locationId).cost()
                + equipmentIds.stream().mapToLong(id -> equipment.get(id).cost()).sum();
        return new PlanSnapshot(locationId, equipmentIds, start, end, cost, scenes);
    }

    public List<Scene> scenesOf(String blockCode) {
        return scenes.stream().filter(scene -> blockCode.equals(scene.blockCode())).toList();
    }

    public List<Long> actorIdsOf(String blockCode) {
        Set<Long> ids = new LinkedHashSet<>();
        scenesOf(blockCode).forEach(scene -> ids.addAll(scene.actorIds()));
        return List.copyOf(ids);
    }

    /** 장소의 시각별 시간당 강수량(mm)이다. */
    public Map<Integer, Double> hourly(long locationId) {
        Map<Integer, Double> hourly = new TreeMap<>();
        weather.stream()
                .filter(w -> w.locationId() == locationId)
                .forEach(w -> hourly.put(w.hour(), w.precipMm()));
        return hourly;
    }

    public PlanInput toInput() {
        Map<Long, Integer> otherMinutes = new HashMap<>();
        for (Block block : blocks) {
            if (CHANGING_BLOCK.equals(block.code())) {
                continue;
            }
            for (long actorId : actorIdsOf(block.code())) {
                otherMinutes.merge(actorId, block.minutes(), Integer::sum);
            }
        }
        Map<Long, Map<Integer, Double>> precip = new HashMap<>();
        locations.keySet().forEach(id -> precip.put(id, hourly(id)));
        LocalTime morningEnd = blocks.stream()
                .filter(block -> !CHANGING_BLOCK.equals(block.code()) && block.end().isBefore(changingBlock().end()))
                .map(Block::end)
                .max(LocalTime::compareTo)
                .orElse(shootDay.callTime());
        List<BlockSlot> otherBlocks = new ArrayList<>();
        for (Block block : blocks) {
            if (!CHANGING_BLOCK.equals(block.code())) {
                otherBlocks.add(new BlockSlot(block.code(), block.start(), block.end(), actorIdsOf(block.code())));
            }
        }
        List<ScenePlan> blockScenes = scenesOf(CHANGING_BLOCK).stream().map(PlanData::scenePlan).toList();
        return new PlanInput(shootDay.callTime(), morningEnd, shootDay.blockBudgetCap(),
                shootDay.crewWeeklyHoursUsed(), current(), actorIdsOf(CHANGING_BLOCK), otherMinutes,
                actors, locations, equipment, options, precip, alerts, alternativeLocationIds,
                settings.rainBlockMm(), settings.rainWarnMm(), blockScenes, actorDays, List.copyOf(otherBlocks),
                shootDay.sunrise(), shootDay.sunset());
    }

    private static ScenePlan scenePlan(Scene scene) {
        List<String> uncast = scene.characters().stream().filter(c -> c.actorId() == null)
                .map(SceneCharacter::name).toList();
        List<Long> must = scene.requirements().stream()
                .filter(r -> r.equipmentId() != null && r.must()).map(SceneRequirement::equipmentId).toList();
        List<Long> want = scene.requirements().stream()
                .filter(r -> r.equipmentId() != null && !r.must()).map(SceneRequirement::equipmentId).toList();
        return new ScenePlan(scene.code(), scene.durationMin(), scene.exterior(), scene.night(), scene.settingLocked(),
                scene.locationId(), uncast, must, want, scene.actorIds());
    }
}
