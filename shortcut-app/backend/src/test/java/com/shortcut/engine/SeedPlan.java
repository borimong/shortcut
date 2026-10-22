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

    /**
     * 대본 분해와 배우 날짜별 일정을 더한 입력이다. 1회차 오후 씬 S12(배우 A, B, 90분), S13(배우 A, 30분)은 낮 야외 장면이고
     * 카메라 패키지(1)가 필수, 드론(2)과 반사판(3)이 선호다. 오전 블록은 07:00~11:30에 배우 B, C가 나온다.
     */
    static PlanInput withScript(PlanInput base, List<ScenePlan> scenes, Map<Long, ActorDay> actorDays,
                                List<BlockSlot> otherBlocks, LocalTime sunset) {
        return new PlanInput(base.callTime(), base.morningEnd(), base.budgetCap(), base.crewWeeklyHoursUsed(),
                base.current(), base.blockActorIds(), base.actorOtherBlockMinutes(), base.actors(), base.locations(),
                base.equipment(), base.options(), base.precipByLocation(), base.alerts(), base.alternativeLocationIds(),
                base.rainBlockMm(), base.rainWarnMm(), scenes, actorDays, otherBlocks, t("06:50"), sunset);
    }

    static PlanInput withScript(PlanInput base) {
        return withScript(base, seedScenes(), Map.of(), seedMorning(), t("17:40"));
    }

    static List<ScenePlan> seedScenes() {
        return List.of(
                new ScenePlan("S12", 90, true, false, false, null, List.of(), List.of(1L), List.of(2L, 3L), List.of(1L, 2L)),
                new ScenePlan("S13", 30, true, false, false, null, List.of(), List.of(1L), List.of(), List.of(1L)));
    }

    /**
     * 시드 2회차 오후 블록이다. 확정안은 성수 스튜디오 14:00~16:00에 S18(배우 B, C, 90분) 다음 S19(배우 B, 30분)이고,
     * 두 씬은 작업실 세트가 성수에만 있어 다른 장소에서 찍을 수 없다. 오전 블록(08:00~10:00)에는 배우 B, C가 나오고
     * 비는 오지 않는다. 배우 C는 콜시트 확정 뒤 10:30~14:30 타 작품 일정이 들어왔다(data-schedule.sql [시연]).
     *
     * @param sceneActors 씬마다 출연 배우를 넣을지. 빼면 1단계 엔진처럼 배우가 블록 내내 현장에 있다고 본다
     */
    static PlanInput day2(boolean sceneActors) {
        PlanInput day1 = input(List.of());
        List<PlanOption> options = List.of(
                new PlanOption(1, 2, List.of(1L, 5L), 1.00, t("14:00"), t("16:00")),
                new PlanOption(2, 3, List.of(1L, 5L), 0.80, t("13:00"), t("15:00")),
                new PlanOption(3, 1, List.of(1L, 3L), 0.60, t("13:00"), t("15:00")));
        Map<Long, Map<Integer, Double>> dry = new HashMap<>();
        for (long locationId = 1; locationId <= 4; locationId++) {
            Map<Integer, Double> hourly = new HashMap<>();
            for (int hour = 6; hour <= 18; hour++) {
                hourly.put(hour, 0.0);
            }
            dry.put(locationId, hourly);
        }
        List<ScenePlan> scenes = List.of(
                new ScenePlan("S18", 90, false, false, true, 2L, List.of(), List.of(1L), List.of(5L),
                        sceneActors ? List.of(2L, 3L) : List.of()),
                new ScenePlan("S19", 30, false, false, true, 2L, List.of(), List.of(1L), List.of(),
                        sceneActors ? List.of(2L) : List.of()));
        Map<Long, ActorDay> days = Map.of(
                1L, new ActorDay(1, false, null, List.of(new ActorDay.Window(t("09:00"), t("16:00"))),
                        List.of(new ActorDay.Busy(t("06:00"), t("13:30"), "PROMOTION"))),
                3L, new ActorDay(3, false, null, List.of(new ActorDay.Window(t("06:30"), t("20:00"))),
                        List.of(new ActorDay.Busy(t("10:30"), t("14:30"), "OTHER_PRODUCTION"))));
        PlanSnapshot current = new PlanSnapshot(2, List.of(1L, 5L), t("14:00"), t("16:00"), 450000);
        return new PlanInput(t("07:30"), t("10:00"), 1_000_000, 40, current, List.of(2L, 3L),
                Map.of(2L, 120, 3L, 120), day1.actors(), day1.locations(), day1.equipment(), options, dry, List.of(),
                List.of(), PlanEngine.DEFAULT_RAIN_BLOCK_MM, PlanEngine.DEFAULT_RAIN_WARN_MM, scenes, days,
                List.of(new BlockSlot("AM", t("08:00"), t("10:00"), List.of(2L, 3L))), t("06:50"), t("17:40"));
    }

    static List<BlockSlot> seedMorning() {
        return List.of(new BlockSlot("AM", t("07:00"), t("11:30"), List.of(2L, 3L)));
    }

    static LocalTime t(String value) {
        return LocalTime.parse(value);
    }
}
