package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.common.ApiException;
import com.shortcut.domain.Actor;
import com.shortcut.domain.DataOverride;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.SettingsRepository;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlanDataService {

    private final PlanRepository plans;
    private final OverrideRepository overrides;
    private final SettingsRepository settings;

    public PlanDataService(PlanRepository plans, OverrideRepository overrides, SettingsRepository settings) {
        this.plans = plans;
        this.overrides = overrides;
        this.settings = settings;
    }

    /**
     * 시드 데이터에 변경 입력이 남긴 덮어쓰기를 얹어서 읽는다.
     * 엔진, 촬영판, Agent 조회가 모두 이 결과를 쓰므로 "반사판 고장"을 입력하면 세 곳 모두 고장으로 본다.
     * equipment.available 같은 원본 열에는 고장이 남지 않으므로, 배우, 장소, 장비 상태는 반드시 이 메서드로 읽는다.
     */
    @Transactional(readOnly = true)
    public PlanData load(long shootDayId) {
        ShootDay shootDay = plans.findShootDay(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        Map<Long, Actor> actors = byId(plans.findActors(), Actor::id);
        Map<Long, Location> locations = byId(plans.findLocations(), Location::id);
        Map<Long, Equipment> equipment = byId(plans.findEquipment(), Equipment::id);
        List<WeatherHour> weather = new ArrayList<>(plans.findWeather(shootDayId));
        for (DataOverride o : overrides.find(shootDayId)) {
            apply(o, actors, locations, equipment, weather);
        }
        return new PlanData(shootDay,
                plans.findBlocks(shootDayId),
                plans.findScenes(shootDayId),
                actors,
                locations,
                equipment,
                plans.findPlanOptions(shootDayId, PlanData.CHANGING_BLOCK),
                weather,
                plans.findAlerts(shootDay.shootDate()),
                plans.findAlternativeLocationIds(shootDayId),
                settings.settings());
    }

    public long boardShootDayId() {
        return plans.findBoardShootDayId()
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다."));
    }

    private static void apply(DataOverride o, Map<Long, Actor> actors, Map<Long, Location> locations,
                              Map<Long, Equipment> equipment, List<WeatherHour> weather) {
        JsonNode p = o.payload();
        switch (o.kind()) {
            case "EQUIPMENT_UNAVAILABLE" -> equipment.computeIfPresent(o.targetId(),
                    (id, e) -> new Equipment(e.id(), e.name(), false, e.drone(), e.cost()));
            case "LOCATION_UNAVAILABLE" -> locations.computeIfPresent(o.targetId(), (id, l) -> l.unavailable());
            case "ACTOR_WINDOW" -> actors.computeIfPresent(o.targetId(), (id, a) -> new Actor(a.id(), a.name(),
                    LocalTime.parse(p.path("from").asText()), LocalTime.parse(p.path("to").asText()),
                    a.weeklyHoursUsed(), a.contractDocId(), a.noNight(), a.maxDailyHours(), a.managerPhone()));
            case "RAIN_FORECAST" -> {
                // 입력한 시간대는 예보보다 비가 적게 오더라도 입력값을 쓴다. 현장 관측이 예보보다 정확하기 때문이다.
                int from = p.path("fromHour").asInt();
                int to = p.path("toHour").asInt();
                double mm = p.path("mm").asDouble();
                weather.removeIf(w -> w.locationId() == o.targetId() && w.hour() >= from && w.hour() <= to);
                for (int hour = from; hour <= to; hour++) {
                    weather.add(new WeatherHour(o.targetId(), hour, mm));
                }
            }
            default -> {
                // 알 수 없는 종류는 무시한다. 새 종류를 추가하면서 옛 backend가 읽어도 깨지지 않게 하려는 것이다.
            }
        }
    }

    private static <T> Map<Long, T> byId(List<T> rows, Function<T, Long> id) {
        Map<Long, T> map = new LinkedHashMap<>();
        rows.forEach(row -> map.put(id.apply(row), row));
        return map;
    }
}
