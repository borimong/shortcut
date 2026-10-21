package com.shortcut.service;

import com.shortcut.domain.Block;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.ExternalLocation;
import com.shortcut.domain.Location;
import com.shortcut.dto.BoardDtos.EquipmentView;
import com.shortcut.dto.BoardDtos.HourlyView;
import com.shortcut.dto.PlanDtos.ActorAvailability;
import com.shortcut.dto.PlanDtos.AvailabilityResponse;
import com.shortcut.dto.PlanDtos.ExternalLocationView;
import com.shortcut.dto.PlanDtos.LocationAvailability;
import com.shortcut.dto.PlanDtos.LocationWeather;
import com.shortcut.dto.PlanDtos.PlanBlock;
import com.shortcut.dto.PlanDtos.PlanCurrent;
import com.shortcut.dto.PlanDtos.PlanLocation;
import com.shortcut.dto.PlanDtos.PlanOptionView;
import com.shortcut.dto.PlanDtos.PlanScene;
import com.shortcut.dto.PlanDtos.PlanSetResponse;
import com.shortcut.dto.PlanDtos.WeatherResponse;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.PlanRepository;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ShootDayQueryService {

    private static final String OURPLACE_SOURCE = "OURPLACE_MOCK";

    private final PlanDataService planData;
    private final PlanRepository plans;

    public ShootDayQueryService(PlanDataService planData, PlanRepository plans) {
        this.planData = planData;
        this.plans = plans;
    }

    public PlanSetResponse planSet(long shootDayId) {
        PlanData data = planData.load(shootDayId);
        Block pm = data.changingBlock();
        List<PlanScene> scenes = data.scenesOf(pm.code()).stream()
                .map(s -> new PlanScene(s.code(), s.title(), s.durationMin(), s.actorIds(), s.outdoorIntent()))
                .toList();
        PlanSnapshot current = data.current();
        List<PlanOptionView> options = data.options().stream()
                .map(o -> new PlanOptionView(o.optionNo(), planLocation(data.locations().get(o.locationId())),
                        equipment(data, o.equipmentIds()), o.equipmentFit(), o.start(), o.end()))
                .toList();
        return new PlanSetResponse(shootDayId, data.shootDay().dataVersion(),
                new PlanBlock(pm.code(), pm.durationMin(), scenes, data.actorIdsOf(pm.code())),
                new PlanCurrent(planLocation(data.locations().get(current.locationId())),
                        equipment(data, current.equipmentIds()), current.start(), current.end(), current.cost()),
                options);
    }

    public AvailabilityResponse availability(long shootDayId) {
        PlanData data = planData.load(shootDayId);
        List<ActorAvailability> actors = data.actors().values().stream()
                .map(a -> new ActorAvailability(a.id(), a.name(), a.availableFrom(), a.availableTo(),
                        a.weeklyHoursUsed(), a.contractDocId(), a.noNight(), a.maxDailyHours()))
                .toList();
        List<LocationAvailability> locations = data.locations().values().stream()
                .map(l -> new LocationAvailability(l.id(), l.name(), l.indoor(), l.region(), l.openFrom(), l.openTo(),
                        l.permitFrom(), l.permitTo(), l.noFlyZone(), l.note(), l.available()))
                .toList();
        return new AvailabilityResponse(actors, locations, List.copyOf(data.equipment().values()),
                data.shootDay().crewWeeklyHoursUsed());
    }

    public WeatherResponse weather(long shootDayId) {
        PlanData data = planData.load(shootDayId);
        List<LocationWeather> locations = data.locations().values().stream()
                .map(l -> new LocationWeather(l.id(), l.name(), l.indoor(), hourly(data, l.id())))
                .toList();
        return new WeatherResponse(data.shootDay().shootDate(), locations, data.settings().rainBlockMm(),
                data.settings().rainWarnMm());
    }

    public List<DisasterAlert> disasterAlerts(long shootDayId) {
        planData.load(shootDayId);
        return plans.findAlerts();
    }

    /**
     * 키워드는 하나라도 맞으면 후보로 넣고 많이 맞은 순, 가까운 순으로 정렬한다.
     * 모두 맞아야 하면 mock 카탈로그 5건에서 거의 항상 빈 결과가 나와 Agent가 대안을 못 찾는다.
     */
    public List<ExternalLocationView> searchExternal(String keywords, Double maxDistanceKm) {
        List<String> wanted = keywords == null ? List.of() : Arrays.stream(keywords.split(","))
                .map(String::strip)
                .filter(k -> !k.isEmpty())
                .toList();
        return plans.findExternalLocations().stream()
                .filter(l -> maxDistanceKm == null || l.distanceKm() <= maxDistanceKm)
                .filter(l -> wanted.isEmpty() || matches(l, wanted) > 0)
                .sorted(Comparator.comparingLong((ExternalLocation l) -> -matches(l, wanted))
                        .thenComparingDouble(ExternalLocation::distanceKm))
                .map(l -> new ExternalLocationView(l.id(), l.name(), l.indoor(), l.region(), l.distanceKm(), l.cost(),
                        l.keywords(), OURPLACE_SOURCE))
                .toList();
    }

    private static long matches(ExternalLocation location, List<String> wanted) {
        return wanted.stream().filter(location.keywords()::contains).count();
    }

    static List<HourlyView> hourly(PlanData data, long locationId) {
        return data.hourly(locationId).entrySet().stream()
                .map(e -> new HourlyView(e.getKey(), e.getValue()))
                .toList();
    }

    static List<EquipmentView> equipment(PlanData data, List<Long> ids) {
        return ids.stream().map(id -> {
            var item = data.equipment().get(id);
            return new EquipmentView(id, item.name(), item.available());
        }).toList();
    }

    private static PlanLocation planLocation(Location l) {
        return new PlanLocation(l.id(), l.name(), l.indoor(), l.region(), l.cost(), l.distanceKm(), l.fit());
    }
}
