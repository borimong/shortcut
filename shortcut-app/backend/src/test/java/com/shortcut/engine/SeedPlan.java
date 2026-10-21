package com.shortcut.engine;

import com.shortcut.domain.Actor;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import java.time.LocalTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * data.sql 시드와 같은 값으로 엔진 입력을 만든다.
 * DB 없이 기대 결과를 고정하려고 테스트 쪽에 한 번 더 적어 둔다.
 */
final class SeedPlan {

    private SeedPlan() {
    }

    static PlanInput input(List<DisasterAlert> alerts) {
        Map<Long, Actor> actors = Map.of(
                1L, new Actor(1, "배우 A", t("09:00"), t("16:00"), 44, "contract-actor-a-v3", true, 10.0, "010-2481-7731"),
                2L, new Actor(2, "배우 B", t("07:00"), t("22:00"), 38, "contract-actor-b-v1", false, null, "010-3920-1184"),
                3L, new Actor(3, "배우 C", t("06:30"), t("20:00"), 30, "contract-actor-c-v2", false, null, "010-5512-0093"));
        Map<Long, Location> locations = Map.of(
                1L, new Location(1, "한강 공원", "", false, "서울 영등포구", t("06:00"), t("22:00"), t("09:00"), t("17:00"),
                        300000, false, 0.95, 6, null, true),
                2L, new Location(2, "성수 스튜디오", "", true, "서울 성동구", t("14:00"), t("18:00"), null, null,
                        450000, false, 0.80, 14, "평일 오후 인근 공사 소음 가능", true),
                3L, new Location(3, "파주 세트장", "", true, "경기 파주시", t("08:00"), t("20:00"), null, null,
                        600000, true, 0.70, 41, null, true),
                4L, new Location(4, "목동 오피스 세트", "", true, "서울 양천구", t("06:00"), t("13:00"), null, null,
                        0, false, 1.00, 0, null, true));
        Map<Long, Equipment> equipment = Map.of(
                1L, new Equipment(1, "카메라 패키지 A", true, false, 0),
                2L, new Equipment(2, "드론", true, true, 0),
                3L, new Equipment(3, "반사판", true, false, 0),
                4L, new Equipment(4, "추가 조명 패키지", true, false, 250000),
                5L, new Equipment(5, "짐벌 세트", true, false, 0));
        List<PlanOption> options = List.of(
                new PlanOption(1, 1, List.of(1L, 2L, 3L), 1.00, t("13:00"), t("15:00")),
                new PlanOption(2, 2, List.of(1L, 4L), 0.75, t("14:00"), t("16:00")),
                new PlanOption(3, 3, List.of(1L, 5L), 0.60, t("12:30"), t("14:30")));
        // data.sql과 같이 한강 공원은 13시부터 시간당 8mm, 12시에 0.5mm 비가 온다.
        Map<Long, Map<Integer, Double>> precip = new HashMap<>();
        for (long locationId = 1; locationId <= 4; locationId++) {
            Map<Integer, Double> hourly = new HashMap<>();
            for (int hour = 6; hour <= 18; hour++) {
                hourly.put(hour, locationId == 1 && hour >= 13 ? 8.0 : locationId == 1 && hour == 12 ? 0.5 : 0.0);
            }
            precip.put(locationId, hourly);
        }
        PlanSnapshot current = new PlanSnapshot(1, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), 300000);
        return new PlanInput(t("06:30"), t("11:30"), 1_000_000, 40, current,
                List.of(1L, 2L), Map.of(2L, 270), actors, locations, equipment, options, precip, alerts, List.of(),
                PlanEngine.DEFAULT_RAIN_BLOCK_MM, PlanEngine.DEFAULT_RAIN_WARN_MM);
    }

    /**
     * 아워플레이스 카탈로그의 일산 실내 스튜디오를 4안 장소(id 101)로 등록한 입력이다.
     */
    static PlanInput withAlternative(PlanInput base) {
        Map<Long, Location> locations = new HashMap<>(base.locations());
        locations.put(101L, new Location(101, "일산 실내 스튜디오", "경기 고양시", true, "경기 고양시", t("08:00"), t("22:00"),
                null, null, 380000, false, 0.8, 25, null, true));
        return new PlanInput(base.callTime(), base.morningEnd(), base.budgetCap(), base.crewWeeklyHoursUsed(),
                base.current(), base.blockActorIds(), base.actorOtherBlockMinutes(), base.actors(), locations,
                base.equipment(), base.options(), base.precipByLocation(), base.alerts(), List.of(101L),
                base.rainBlockMm(), base.rainWarnMm());
    }

    /** 장소 하나를 변경 입력에서 취소한 입력이다. */
    static PlanInput withCancelledLocation(PlanInput base, long locationId) {
        Map<Long, Location> locations = new HashMap<>(base.locations());
        locations.computeIfPresent(locationId, (id, l) -> l.unavailable());
        return new PlanInput(base.callTime(), base.morningEnd(), base.budgetCap(), base.crewWeeklyHoursUsed(),
                base.current(), base.blockActorIds(), base.actorOtherBlockMinutes(), base.actors(), locations,
                base.equipment(), base.options(), base.precipByLocation(), base.alerts(), base.alternativeLocationIds(),
                base.rainBlockMm(), base.rainWarnMm());
    }

    /** 배우 하나를 불참(가용 시작과 끝이 같음)으로 바꾼 입력이다. */
    static PlanInput withAbsentActor(PlanInput base, long actorId) {
        Map<Long, Actor> actors = new HashMap<>(base.actors());
        actors.computeIfPresent(actorId, (id, a) -> new Actor(a.id(), a.name(), LocalTime.MIDNIGHT, LocalTime.MIDNIGHT,
                a.weeklyHoursUsed(), a.contractDocId(), a.noNight(), a.maxDailyHours(), a.managerPhone()));
        return new PlanInput(base.callTime(), base.morningEnd(), base.budgetCap(), base.crewWeeklyHoursUsed(),
                base.current(), base.blockActorIds(), base.actorOtherBlockMinutes(), actors, base.locations(),
                base.equipment(), base.options(), base.precipByLocation(), base.alerts(), base.alternativeLocationIds(),
                base.rainBlockMm(), base.rainWarnMm());
    }

    /** 강수 기준만 바꾼 입력이다. 관리자 설정 변경을 흉내 낸다. */
    static PlanInput withRainRule(PlanInput base, double blockMm, double warnMm) {
        return new PlanInput(base.callTime(), base.morningEnd(), base.budgetCap(), base.crewWeeklyHoursUsed(),
                base.current(), base.blockActorIds(), base.actorOtherBlockMinutes(), base.actors(), base.locations(),
                base.equipment(), base.options(), base.precipByLocation(), base.alerts(), base.alternativeLocationIds(),
                blockMm, warnMm);
    }

    static LocalTime t(String value) {
        return LocalTime.parse(value);
    }
}
