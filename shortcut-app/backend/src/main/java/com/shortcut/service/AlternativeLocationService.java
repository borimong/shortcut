package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.ExternalLocation;
import com.shortcut.dto.PlanDtos.AlternativeLocationView;
import com.shortcut.repository.PlanRepository;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 1/2/3안을 모두 써도 실행 가능한 안이 없을 때 Agent가 고른 대체 장소를 4안 후보로 등록한다.
 * 등록만 하고 판정은 하지 않는다. 판정은 등록된 장소를 포함해 엔진이 다시 한다.
 */
@Service
public class AlternativeLocationService {

    // 1/2/3안 장소(적합도 0.7~0.95)보다 낮게 시작해, 키워드가 다 맞아도 제작사가 고른 장소를 앞서지 않게 한다.
    private static final double BASE_FIT = 0.5;
    private static final double KEYWORD_FIT_RANGE = 0.3;

    private final PlanRepository plans;

    public AlternativeLocationService(PlanRepository plans) {
        this.plans = plans;
    }

    @Transactional
    public List<AlternativeLocationView> register(long shootDayId, List<Long> externalIds, List<String> keywords) {
        plans.findShootDay(shootDayId).orElseThrow(() -> PlanDataService.shootDayNotFound(shootDayId));
        Map<Long, ExternalLocation> catalog = plans.findExternalLocations().stream()
                .collect(Collectors.toMap(ExternalLocation::id, Function.identity()));
        List<String> wanted = keywords == null ? List.of() : keywords.stream().map(String::strip).filter(k -> !k.isEmpty()).toList();
        return externalIds.stream().distinct().map(id -> {
            ExternalLocation external = catalog.get(id);
            if (external == null) {
                throw ApiException.notFound("EXTERNAL_LOCATION_NOT_FOUND", "카탈로그에 없는 장소입니다: " + id);
            }
            List<String> matched = wanted.stream().filter(external.keywords()::contains).toList();
            // 4안 장소의 적합도는 1/2/3안에서 뽑은 키워드와 얼마나 겹치는지로 정한다.
            double ratio = wanted.isEmpty() ? 0.0 : (double) matched.size() / wanted.size();
            double fit = Math.round((BASE_FIT + KEYWORD_FIT_RANGE * ratio) * 100.0) / 100.0;
            long locationId = PlanRepository.ALTERNATIVE_LOCATION_ID_BASE + external.id();
            plans.registerAlternative(shootDayId, locationId, external, fit, wanted);
            return new AlternativeLocationView(locationId, external.id(), external.name(), external.indoor(),
                    external.region(), external.distanceKm(), external.cost(), fit, matched);
        }).toList();
    }
}
