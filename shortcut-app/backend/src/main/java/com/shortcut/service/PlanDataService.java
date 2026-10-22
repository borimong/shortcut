package com.shortcut.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.common.ApiException;
import com.shortcut.domain.Actor;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.AvailabilityEntry;
import com.shortcut.domain.DataOverride;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.ForecastInfo;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.engine.ActorDay;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ScheduleRepository;
import com.shortcut.repository.SettingsRepository;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlanDataService {

    private final PlanRepository plans;
    private final OverrideRepository overrides;
    private final SettingsRepository settings;
    private final ScheduleRepository schedules;

    public PlanDataService(PlanRepository plans, OverrideRepository overrides, SettingsRepository settings,
                           ScheduleRepository schedules) {
        this.plans = plans;
        this.overrides = overrides;
        this.settings = settings;
        this.schedules = schedules;
    }

    /**
     * 시드 데이터에 변경 입력이 남긴 덮어쓰기를 얹어서 읽는다.
     * 엔진, 촬영판, Agent 조회가 모두 이 결과를 쓰므로 "반사판 고장"을 입력하면 세 곳 모두 고장으로 본다.
     * equipment.available 같은 원본 열에는 고장이 남지 않으므로, 배우, 장소, 장비 상태는 반드시 이 메서드로 읽는다.
     * 배우의 그날 일정은 날짜별 기본 일정(actor_availability)에 변경 입력의 가용 시간과 다른 일정을 얹은 값이다.
     */
    @Transactional(readOnly = true)
    public PlanData load(long shootDayId) {
        ShootDay shootDay = plans.findShootDay(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        Map<Long, Actor> actors = byId(plans.findActors(), Actor::id);
        Map<Long, Location> locations = byId(plans.findLocations(), Location::id);
        Map<Long, Equipment> equipment = byId(plans.findEquipment(), Equipment::id);
        Map<Long, List<AvailabilityEntry>> entries = schedules.findAvailability(shootDay.shootDate(), shootDay.shootDate())
                .stream().collect(Collectors.groupingBy(AvailabilityEntry::actorId));
        Map<Long, ActorDay> actorDays = new LinkedHashMap<>();
        actors.values().forEach(a -> actorDays.put(a.id(), ActorDay.of(a, entries.getOrDefault(a.id(), List.of()))));
        AppSettings appSettings = settings.settings();
        List<WeatherHour> weather = new ArrayList<>(plans.findWeather(shootDayId, appSettings.weatherSource()));
        Set<Long> manualWeather = new LinkedHashSet<>();
        for (DataOverride o : overrides.find(shootDayId)) {
            apply(o, actors, actorDays, locations, equipment, weather);
            if ("RAIN_FORECAST".equals(o.kind())) {
                manualWeather.add(o.targetId());
            }
        }
        Map<Long, OffsetDateTime> liveFetchedAt = appSettings.liveWeather()
                ? plans.findLiveForecastTimes(shootDayId) : Map.of();
        return new PlanData(shootDay,
                plans.findBlocks(shootDayId),
                plans.findScenes(shootDayId),
                actors,
                locations,
                equipment,
                plans.findPlanOptions(shootDayId, PlanData.CHANGING_BLOCK),
                weather,
                new ForecastInfo(liveFetchedAt, manualWeather),
                plans.findAlerts(shootDay.shootDate()),
                plans.findAlternativeLocationIds(shootDayId),
                appSettings,
                actorDays);
    }

    public long boardShootDayId() {
        return plans.findBoardShootDayId()
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다."));
    }

    private static void apply(DataOverride o, Map<Long, Actor> actors, Map<Long, ActorDay> actorDays,
                              Map<Long, Location> locations, Map<Long, Equipment> equipment, List<WeatherHour> weather) {
        JsonNode p = o.payload();
        switch (o.kind()) {
            case "EQUIPMENT_UNAVAILABLE" -> equipment.computeIfPresent(o.targetId(),
                    (id, e) -> new Equipment(e.id(), e.name(), false, e.drone(), e.cost()));
            case "LOCATION_UNAVAILABLE" -> locations.computeIfPresent(o.targetId(), (id, l) -> l.unavailable());
            case "ACTOR_WINDOW" -> {
                LocalTime from = LocalTime.parse(p.path("from").asText());
                LocalTime to = LocalTime.parse(p.path("to").asText());
                actors.computeIfPresent(o.targetId(), (id, a) -> new Actor(a.id(), a.name(), from, to,
                        a.weeklyHoursUsed(), a.contractDocId(), a.noNight(), a.maxDailyHours(), a.managerPhone()));
                actorDays.computeIfPresent(o.targetId(), (id, day) -> day.withWindow(from, to));
            }
            // 소속사가 알려 온 다른 일정이다. 그날 가능 시간에서 그 시간만 뺀다.
            case "ACTOR_BUSY" -> actorDays.computeIfPresent(o.targetId(), (id, day) -> day.withBusy(new ActorDay.Busy(
                    LocalTime.parse(p.path("from").asText()), LocalTime.parse(p.path("to").asText()),
                    p.path("reasonKind").asText("OTHER_PRODUCTION"))));
            case "RAIN_FORECAST" -> {
                // 입력한 시간대는 예보보다 비가 적게 오더라도 입력값을 쓴다. 현장 관측이 예보보다 정확하기 때문이다.
                // 시드 예보든 날씨 API 예보든 같다. API가 다시 갱신해도 덮어쓰기가 지워지지 않는 한 입력값이 이긴다.
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
