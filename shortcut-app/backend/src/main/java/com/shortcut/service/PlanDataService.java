package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.Actor;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.repository.PlanRepository;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlanDataService {

    private final PlanRepository plans;

    public PlanDataService(PlanRepository plans) {
        this.plans = plans;
    }

    @Transactional(readOnly = true)
    public PlanData load(long shootDayId) {
        ShootDay shootDay = plans.findShootDay(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        return new PlanData(shootDay,
                plans.findBlocks(shootDayId),
                plans.findScenes(shootDayId),
                byId(plans.findActors(), Actor::id),
                byId(plans.findLocations(), Location::id),
                byId(plans.findEquipment(), Equipment::id),
                plans.findPlanOptions(shootDayId, PlanData.CHANGING_BLOCK),
                plans.findWeather(shootDayId),
                plans.findAlerts(),
                plans.findAlternativeLocationIds(shootDayId));
    }

    public long boardShootDayId() {
        return plans.findBoardShootDayId()
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다."));
    }

    private static <T> Map<Long, T> byId(List<T> rows, Function<T, Long> id) {
        Map<Long, T> map = new LinkedHashMap<>();
        rows.forEach(row -> map.put(id.apply(row), row));
        return map;
    }
}
