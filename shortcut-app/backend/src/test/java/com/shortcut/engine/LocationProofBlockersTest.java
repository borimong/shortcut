package com.shortcut.engine;

import static com.shortcut.engine.SeedPlan.t;
import static org.assertj.core.api.Assertions.assertThat;

import com.shortcut.domain.Actor;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * 실행 가능한 후보가 없을 때 새 장소(4안)로 풀 수 있는지 가른다. 미리보기에서 대체 장소를 잘못 제안한 두 이벤트를 그대로 옮겼다.
 */
class LocationProofBlockersTest {

    private final PlanEngine engine = new PlanEngine();

    @Test
    void 이회차_성수_취소에_배우_C_일정과_세트_고정이_겹치면_장소로_풀_수_없다() {
        // 이벤트: LOCATION_CANCEL 성수 스튜디오. 시드의 배우 C 10:30~14:30 타 작품 일정이 모든 시간대와 겹친다.
        Map<Long, Location> locations = new HashMap<>(SeedPlan.input(List.of()).locations());
        locations.computeIfPresent(2L, (id, l) -> l.unavailable());
        PlanInput input = day2(locations);

        EvaluationResult result = engine.evaluate(input, null, List.of());
        List<String> blockers = PlanEngine.locationProofBlockers(result.candidates());

        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
        assertThat(blockers.getFirst()).isEqualTo("배우 C 일정(10:30~14:30 타 작품)과 겹칩니다.");
        assertThat(blockers).anySatisfy(m -> assertThat(m).contains("S18, S19", "성수 스튜디오에만"));
    }

    @Test
    void 삼회차_반사판_고장에_배우_B_일정이_겹치면_장소로_풀_수_없다() {
        // 이벤트: 반사판 고장(EQUIPMENT_UNAVAILABLE 3)과 배우 B 18:30~21:00 광고·행사 일정(ACTOR_BUSY).
        Map<Long, Location> locations = new HashMap<>(SeedPlan.input(List.of()).locations());
        locations.put(5L, new Location(5, "합정 루프탑", "", false, "서울 마포구", t("16:00"), t("23:00"), t("18:00"),
                t("23:00"), 280000, false, 0.90, 10, null, true));
        Map<Long, Equipment> equipment = new HashMap<>(SeedPlan.input(List.of()).equipment());
        equipment.put(3L, new Equipment(3, "반사판", false, false, 0));
        Map<Long, Actor> actors = new HashMap<>(SeedPlan.input(List.of()).actors());
        actors.put(4L, new Actor(4, "배우 D", t("10:00"), t("23:00"), 12, "contract-actor-d-v1", false, null, null));
        List<PlanOption> options = List.of(
                new PlanOption(1, 5, List.of(1L, 3L), 1.00, t("19:00"), t("21:00")),
                new PlanOption(2, 1, List.of(1L, 4L), 0.70, t("18:00"), t("20:00")),
                new PlanOption(3, 3, List.of(1L, 4L), 0.60, t("18:00"), t("20:00")));
        List<ScenePlan> night = List.of(
                new ScenePlan("S21", 90, true, true, false, 5L, List.of(), List.of(1L), List.of(3L)),
                new ScenePlan("S22", 30, true, true, false, 5L, List.of(), List.of(1L), List.of()));
        ActorDay promotion = new ActorDay(2, false, null, List.of(new ActorDay.Window(t("07:00"), t("22:00"))),
                List.of(new ActorDay.Busy(t("18:30"), t("21:00"), "PROMOTION")));
        PlanInput input = new PlanInput(t("12:30"), t("16:00"), 1_000_000, 40,
                new PlanSnapshot(5, List.of(1L, 3L), t("19:00"), t("21:00"), 280000), List.of(2L, 4L),
                Map.of(2L, 120), actors, locations, equipment, options, Map.of(), List.of(), List.of(),
                PlanEngine.DEFAULT_RAIN_BLOCK_MM, PlanEngine.DEFAULT_RAIN_WARN_MM, night, Map.of(2L, promotion),
                List.of(new BlockSlot("AM", t("14:00"), t("16:00"), List.of(2L, 5L))), t("06:50"), t("17:40"));

        EvaluationResult result = engine.evaluate(input, null, List.of());

        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
        assertThat(PlanEngine.locationProofBlockers(result.candidates()).getFirst())
                .isEqualTo("배우 B 일정(18:30~21:00 광고와 행사)과 겹칩니다.");
    }

    @Test
    void 장소만_문제인_후보가_있으면_4안을_찾아볼_수_있다() {
        // 1/2/3안 장소를 모두 빼면 막히지만 장소 제약뿐이라 새 장소로 풀 수 있다.
        List<ExtraConstraint> allPlaces = List.of(
                new ExtraConstraint("EXCLUDE_LOCATION", 1L, null, null, null, null, null, "", ""),
                new ExtraConstraint("EXCLUDE_LOCATION", 2L, null, null, null, null, null, "", ""),
                new ExtraConstraint("EXCLUDE_LOCATION", 3L, null, null, null, null, null, "", ""));
        EvaluationResult result = engine.evaluate(SeedPlan.input(List.of()), null, allPlaces);

        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
        assertThat(PlanEngine.locationProofBlockers(result.candidates())).isEmpty();
    }

    /** 2회차 오후 블록: S18, S19는 성수 세트 고정, 배우 B·C, 오전 08:00~10:00 목동(배우 B, C). 비는 오지 않는다. */
    private static PlanInput day2(Map<Long, Location> locations) {
        PlanInput seed = SeedPlan.input(List.of());
        List<PlanOption> options = List.of(
                new PlanOption(1, 2, List.of(1L, 5L), 1.00, t("14:00"), t("16:00")),
                new PlanOption(2, 3, List.of(1L, 5L), 0.80, t("13:00"), t("15:00")),
                new PlanOption(3, 1, List.of(1L, 3L), 0.60, t("13:00"), t("15:00")));
        List<ScenePlan> workshop = List.of(
                new ScenePlan("S18", 90, false, false, true, 2L, List.of(), List.of(1L), List.of(5L)),
                new ScenePlan("S19", 30, false, false, true, 2L, List.of(), List.of(1L), List.of()));
        ActorDay interview = new ActorDay(3, false, null, List.of(new ActorDay.Window(t("06:30"), t("20:00"))),
                List.of(new ActorDay.Busy(t("10:30"), t("14:30"), "OTHER_PRODUCTION")));
        return new PlanInput(t("07:30"), t("10:00"), 1_000_000, 40,
                new PlanSnapshot(2, List.of(1L, 5L), t("14:00"), t("16:00"), 450000), List.of(2L, 3L),
                Map.of(2L, 120, 3L, 120), seed.actors(), locations, seed.equipment(), options, Map.of(), List.of(),
                List.of(), PlanEngine.DEFAULT_RAIN_BLOCK_MM, PlanEngine.DEFAULT_RAIN_WARN_MM, workshop,
                Map.of(3L, interview), List.of(new BlockSlot("AM", t("08:00"), t("10:00"), List.of(2L, 3L))),
                t("06:50"), t("17:40"));
    }
}
