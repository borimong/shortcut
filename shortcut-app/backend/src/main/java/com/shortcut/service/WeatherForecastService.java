package com.shortcut.service;

import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.Location;
import com.shortcut.dto.AdminDtos.WeatherRefreshResult;
import com.shortcut.engine.PlanEngine;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.WeatherRepository;
import com.shortcut.repository.WeatherRepository.Key;
import com.shortcut.repository.WeatherRepository.Target;
import com.shortcut.service.OpenMeteoClient.Point;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 장소 위경도로 날씨 API(Open-Meteo)의 시간별 강수량을 받아 weather_forecasts에 LIVE 행으로 넣는다.
 * 시드 예보(SEED 행)는 그대로 두고, 엔진과 화면이 어느 쪽을 읽을지는 관리자 설정 weather_source가 정한다.
 * API가 실패하면 행을 건드리지 않아 마지막으로 받은 예보를 계속 쓰고, 화면은 갱신 시각으로 오래된 예보임을 알린다.
 */
@Service
public class WeatherForecastService {

    private static final Logger log = LoggerFactory.getLogger(WeatherForecastService.class);
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    static final Duration REFRESH_EVERY = Duration.ofHours(1);
    static final Duration RETRY_AFTER = Duration.ofMinutes(5);
    /** 마지막 갱신이 이보다 오래되면 화면에 최근 갱신이 실패했다고 보인다. 정기 갱신을 한 번 놓친 것까지는 봐준다. */
    public static final Duration STALE_AFTER = Duration.ofMinutes(90);
    // Open-Meteo는 오늘부터 16일 치 예보를 준다. 범위 밖 날짜를 물으면 요청 전체가 거절된다.
    private static final int FORECAST_DAYS = 16;
    // 콜타임(6시대)부터 야간 촬영 제한(22시) 전까지만 저장한다. 시드 예보도 이 범위 안에 있다.
    static final int FIRST_HOUR = 6;
    static final int LAST_HOUR = 21;

    private final WeatherRepository weather;
    private final OpenMeteoClient client;
    private final PlanDataService planData;
    private final PlanRepository plans;
    private final SupersedeService supersede;
    private final SettingsRepository settings;
    private final TransactionTemplate transaction;
    private final boolean enabled;

    private final AtomicBoolean requested = new AtomicBoolean();
    private volatile Instant nextRefresh;
    private volatile boolean lastFailed;

    public WeatherForecastService(WeatherRepository weather, OpenMeteoClient client, PlanDataService planData,
                                  PlanRepository plans, SupersedeService supersede, SettingsRepository settings,
                                  TransactionTemplate transaction, ShortcutProperties properties) {
        this.weather = weather;
        this.client = client;
        this.planData = planData;
        this.plans = plans;
        this.supersede = supersede;
        this.settings = settings;
        this.transaction = transaction;
        this.enabled = properties.weather().fetchEnabled();
    }

    /**
     * 1분마다 확인해서 정기 갱신 시각이 되었거나, 갱신 요청이 있었거나, 아직 예보가 없는 촬영일과 장소가 있으면 받는다.
     * 예보가 없는 곳(4안 등록, 초기화로 촬영일 날짜가 바뀜)은 1시간을 기다리지 않고 바로 채운다.
     * 직전 갱신이 실패했으면 1분마다 다시 부르지 않고 몇 분 뒤 정기 시각까지 기다린다.
     */
    @Scheduled(initialDelay = 10_000, fixedDelay = 60_000)
    public void scheduledRefresh() {
        if (!enabled) {
            return;
        }
        ZonedDateTime now = ZonedDateTime.now(SEOUL);
        boolean due = requested.getAndSet(false) || nextRefresh == null || !now.toInstant().isBefore(nextRefresh)
                || (!lastFailed && hasMissing(now.toLocalDate()));
        if (due) {
            refresh(now, null);
        }
    }

    /** 다음 정기 확인(1분 간격)을 기다리지 않고 지금 예보를 받는다. */
    public WeatherRefreshResult refreshNow() {
        return refresh(ZonedDateTime.now(SEOUL), null);
    }

    /**
     * 4안 장소를 등록한 직후 그 장소 예보를 받는다. 엔진이 시드에서 복사한 보수적인 강수량 대신 그 지점 예보로 판정하게 하려는 것이다.
     * 시드 예보를 쓰는 중이면 등록 응답을 늦추지 않고 다음 정기 확인에 맡긴다.
     */
    public void refreshRegistered(Collection<Long> locationIds) {
        if (!enabled || locationIds.isEmpty()) {
            return;
        }
        if (!settings.settings().liveWeather()) {
            requested.set(true);
            return;
        }
        refresh(ZonedDateTime.now(SEOUL), Set.copyOf(locationIds));
    }

    /**
     * @param only null이면 전체 대상을 받고 기준 변화를 확인한다. 값이 있으면 그 장소만 받고 data_version은 그대로 둔다
     */
    synchronized WeatherRefreshResult refresh(ZonedDateTime now, Set<Long> only) {
        LocalDate today = now.toLocalDate();
        List<Target> targets = weather.targets(today, today.plusDays(FORECAST_DAYS - 1)).stream()
                .filter(t -> only == null || only.contains(t.locationId()))
                .toList();
        if (targets.isEmpty()) {
            markRefreshed(now, only, true);
            return new WeatherRefreshResult(0, List.of(), 0);
        }
        // 장소 하나에 촬영일이 여러 날이면 한 지점으로 묻고, 모든 지점을 요청 한 번에 묻는다.
        Map<Long, List<Target>> byLocation = targets.stream()
                .collect(Collectors.groupingBy(Target::locationId, LinkedHashMap::new, Collectors.toList()));
        List<Target> points = byLocation.values().stream().map(list -> list.get(0)).toList();
        LocalDate from = targets.stream().map(Target::shootDate).min(Comparator.naturalOrder()).orElseThrow();
        LocalDate to = targets.stream().map(Target::shootDate).max(Comparator.naturalOrder()).orElseThrow();
        List<Map<LocalDate, Map<Integer, Double>>> fetched;
        try {
            fetched = client.hourlyPrecip(points.stream().map(t -> new Point(t.latitude(), t.longitude())).toList(),
                    from, to);
        } catch (RuntimeException e) {
            List<String> failed = points.stream().map(Target::locationName).toList();
            log.warn("날씨 API 예보를 받지 못해 마지막 예보를 그대로 씁니다 ({}곳): {}", failed.size(), e.getMessage());
            markRefreshed(now, only, false);
            return new WeatherRefreshResult(0, failed, 0);
        }

        Map<Long, Map<Long, Map<Integer, Double>>> byShootDay = new TreeMap<>();
        List<String> failed = new ArrayList<>();
        for (int i = 0; i < points.size(); i++) {
            Map<LocalDate, Map<Integer, Double>> byDate = fetched.get(i);
            for (Target t : byLocation.get(points.get(i).locationId())) {
                Map<Integer, Double> hourly = new TreeMap<>(byDate.getOrDefault(t.shootDate(), Map.of()));
                hourly.keySet().removeIf(hour -> hour < FIRST_HOUR || hour > LAST_HOUR);
                if (hourly.isEmpty()) {
                    failed.add(t.locationName());
                    continue;
                }
                byShootDay.computeIfAbsent(t.shootDayId(), id -> new LinkedHashMap<>()).put(t.locationId(), hourly);
            }
        }
        OffsetDateTime fetchedAt = now.toOffsetDateTime();
        int updated = 0;
        int bumped = 0;
        for (var entry : byShootDay.entrySet()) {
            Boolean changed = transaction.execute(status -> save(entry.getKey(), entry.getValue(), fetchedAt, only == null));
            updated += entry.getValue().size();
            bumped += Boolean.TRUE.equals(changed) ? 1 : 0;
        }
        markRefreshed(now, only, failed.isEmpty());
        return new WeatherRefreshResult(updated, failed.stream().distinct().toList(), bumped);
    }

    /**
     * 예보를 저장하고, 실시간 예보를 쓰는 중에 촬영 불가 기준을 넘나드는 시각이 생기면 data_version을 올린다.
     * 변경 입력과 같이 그 전 데이터로 만든 승인 대기 변경안을 무효로 돌려, 바뀐 비 예보를 모른 채 확정되지 않게 한다.
     * 이번에 처음 받은 장소는 비교하지 않는다. 그 장소를 실시간 예보로 판정한 변경안이 아직 없기 때문이다.
     *
     * @return data_version을 올렸는지
     */
    private boolean save(long shootDayId, Map<Long, Map<Integer, Double>> byLocation, OffsetDateTime fetchedAt,
                         boolean detectChanges) {
        PlanData before = detectChanges ? planData.load(shootDayId) : null;
        byLocation.forEach((locationId, hourly) -> weather.saveLive(shootDayId, locationId, hourly, fetchedAt));
        if (before == null || !before.settings().liveWeather()) {
            return false;
        }
        Set<Long> compared = before.forecast().liveFetchedAt().keySet();
        PlanData after = planData.load(shootDayId);
        List<String> changed = compared.stream()
                .filter(id -> !rainyHours(before, id).equals(rainyHours(after, id)))
                .map(id -> after.locations().get(id).name())
                .toList();
        if (changed.isEmpty()) {
            return false;
        }
        int version = plans.bumpDataVersion(shootDayId);
        String reason = String.join(", ", changed) + " 비 예보 변경(시간당 "
                + PlanEngine.mm(after.settings().rainBlockMm()) + "mm 기준)";
        supersede.supersedeOlder(shootDayId, version, reason);
        log.info("촬영일 {} 날씨 예보가 촬영 불가 기준을 넘나들어 data_version을 {}로 올렸습니다: {}", shootDayId, version, reason);
        return true;
    }

    /** 야외 장소에서 시간당 강수량이 촬영 불가 기준 이상인 시각이다. 실내는 비의 영향을 받지 않으므로 비어 있다. */
    private static Set<Integer> rainyHours(PlanData data, long locationId) {
        Location location = data.locations().get(locationId);
        if (location == null || location.indoor()) {
            return Set.of();
        }
        return data.hourly(locationId).entrySet().stream()
                .filter(e -> e.getValue() >= data.settings().rainBlockMm())
                .map(Map.Entry::getKey)
                .collect(Collectors.toCollection(TreeSet::new));
    }

    private boolean hasMissing(LocalDate today) {
        Set<Key> live = weather.liveKeys();
        return weather.targets(today, today.plusDays(FORECAST_DAYS - 1)).stream()
                .anyMatch(t -> !live.contains(new Key(t.shootDayId(), t.locationId())));
    }

    /** 전체 갱신만 다음 정기 시각을 정한다. 실패하면 1시간이 아니라 몇 분 뒤에 다시 받는다. */
    private void markRefreshed(ZonedDateTime now, Set<Long> only, boolean ok) {
        if (only == null) {
            nextRefresh = now.toInstant().plus(ok ? REFRESH_EVERY : RETRY_AFTER);
            lastFailed = !ok;
        }
    }
}
