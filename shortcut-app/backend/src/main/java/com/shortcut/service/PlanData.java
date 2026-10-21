package com.shortcut.service;

import com.shortcut.domain.Actor;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.Block;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import com.shortcut.domain.Scene;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.engine.PlanInput;
import com.shortcut.engine.PlanSnapshot;
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
        List<DisasterAlert> alerts,
        List<Long> alternativeLocationIds,
        AppSettings settings) {

    public static final String CHANGING_BLOCK = "PM";

    public Block changingBlock() {
        return blocks.stream()
                .filter(block -> CHANGING_BLOCK.equals(block.code()))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("오후 블록이 없습니다."));
    }

    public PlanSnapshot current() {
        Block pm = changingBlock();
        return snapshot(pm.locationId(), pm.equipmentIds(), pm.start(), pm.end());
    }

    public PlanSnapshot snapshot(long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end) {
        long cost = locations.get(locationId).cost()
                + equipmentIds.stream().mapToLong(id -> equipment.get(id).cost()).sum();
        return new PlanSnapshot(locationId, equipmentIds, start, end, cost);
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
        return new PlanInput(shootDay.callTime(), morningEnd, shootDay.blockBudgetCap(),
                shootDay.crewWeeklyHoursUsed(), current(), actorIdsOf(CHANGING_BLOCK), otherMinutes,
                actors, locations, equipment, options, precip, alerts, alternativeLocationIds,
                settings.rainBlockMm(), settings.rainWarnMm());
    }
}
