package com.shortcut.engine;

import static com.shortcut.engine.SeedPlan.t;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * 배우 여럿의 시간이 함께 걸릴 때를 본다. 격리 스택에서 돌린 시나리오를 그대로 옮겼다.
 * 1/2/3안 시간대가 모두 막히면 배우들이 함께 되는 시간에 맞춘 조정 시간을 만들고, 그래도 막히면 배우마다 원인을 적고
 * 함께 되는 시간을 덧붙인다.
 */
class MultiActorScheduleTest {

    private final PlanEngine engine = new PlanEngine();

    @Test
    void 일_2_3안_시간대_밖에서만_배우들이_함께_되면_조정_시간을_만든다() {
        // 배우 A는 13:15부터, 배우 B는 14:45까지. S12(A·B 90분)를 13:15~14:45, S13(A 30분)을 14:45~15:15에 찍으면 되지만
        // 1/2/3안 시간대(13~15, 14~16, 12:30~14:30)에는 맞는 것이 없다. 비는 오지 않는다.
        Map<Long, ActorDay> days = Map.of(
                1L, new ActorDay(1, false, null, List.of(new ActorDay.Window(t("13:15"), t("16:00"))), List.of()),
                2L, new ActorDay(2, false, null, List.of(new ActorDay.Window(t("07:00"), t("22:00"))),
                        List.of(new ActorDay.Busy(t("14:45"), t("18:00"), "OTHER_PRODUCTION"))));
        PlanInput input = dry(SeedPlan.withScript(SeedPlan.input(List.of()), SeedPlan.seedScenes(), days,
                SeedPlan.seedMorning(), t("17:40")));

        EvaluationResult result = engine.evaluate(input, null, List.of());

        assertThat(result.candidates().stream().filter(c -> c.timeOptionNo() != PlanEngine.ADJUSTED_TIME_OPTION_NO))
                .hasSize(27).noneMatch(CandidateResult::feasible);
        CandidateResult best = result.candidates().getFirst();
        assertThat(best.feasible()).isTrue();
        assertThat(best.timeOptionNo()).isEqualTo(PlanEngine.ADJUSTED_TIME_OPTION_NO);
        assertThat(best.location().id()).isEqualTo(1L);
        assertThat(best.sceneOrder()).containsExactly(
                new SceneSlot("S12", t("13:15"), t("14:45")), new SceneSlot("S13", t("14:45"), t("15:15")));
        assertThat(best.warnings()).extracting(Finding::code).contains("TIME_ADJUSTED");
    }

    @Test
    void 일_2_3안으로_되는_후보가_있으면_조정_시간을_만들지_않는다() {
        EvaluationResult result = engine.evaluate(SeedPlan.withScript(SeedPlan.input(List.of())), null, List.of());

        assertThat(result.candidates()).hasSize(27)
                .noneMatch(c -> c.timeOptionNo() == PlanEngine.ADJUSTED_TIME_OPTION_NO);
    }

    @Test
    void 두_배우가_함께_막으면_배우마다_원인을_적고_함께_되는_시간을_덧붙인다() {
        // 2회차: 배우 C는 14:30까지 인터뷰(시드), 배우 B는 15:30부터 다른 일정. S18(B·C 90분)이 들어갈 자리가 없다.
        PlanInput seed = SeedPlan.day2(true);
        Map<Long, ActorDay> days = new HashMap<>(seed.actorDays());
        days.put(2L, new ActorDay(2, false, null, List.of(new ActorDay.Window(t("07:00"), t("22:00"))),
                List.of(new ActorDay.Busy(t("15:30"), t("18:00"), "OTHER_PRODUCTION"))));
        PlanInput input = withActorDays(seed, days);

        EvaluationResult result = engine.evaluate(input, null, List.of());
        List<String> blockers = PlanEngine.locationProofBlockers(input, result.candidates());

        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
        // 성수는 취소되지 않았으므로 "그곳을 쓸 수 없다"고 쓰지 않는다.
        assertThat(blockers.getFirst()).isEqualTo("S18, S19는 세트가 성수 스튜디오에만 있는데 성수 스튜디오에서 찍는 후보도 모두 막혔습니다.");
        assertThat(blockers).contains("배우 B 일정(15:30~18:00 타 작품)과 겹칩니다.", "배우 C 일정(10:30~14:30 타 작품)과 겹칩니다.");
        assertThat(blockers.getLast()).isEqualTo(
                "성수 스튜디오 이용 시간 안에서 배우 B, 배우 C가 함께 되는 시간: 14:30~15:30(60분). 블록 120분을 한 번에 찍기에는 짧습니다.");
    }

    @Test
    void 배우_불참이_원인이면_세트_장소를_쓸_수_없다고_쓰지_않고_순서로_풀리는_배우는_뺀다() {
        // 2회차 배우 B 불참. 배우 C 일정은 S19를 먼저 찍으면 풀리므로 원인이 아니다.
        PlanInput seed = SeedPlan.day2(true);
        Map<Long, ActorDay> days = new HashMap<>(seed.actorDays());
        days.put(2L, new ActorDay(2, true, null, List.of(), List.of()));
        PlanInput input = withActorDays(seed, days);

        EvaluationResult result = engine.evaluate(input, null, List.of());

        assertThat(PlanEngine.locationProofBlockers(input, result.candidates())).containsExactly(
                "S18, S19는 세트가 성수 스튜디오에만 있는데 성수 스튜디오에서 찍는 후보도 모두 막혔습니다.",
                "배우 B는 오늘 촬영에 참여할 수 없습니다.");
    }

    @Test
    void 되는_후보가_없으면_세트_장소에서_위반이_가장_적은_후보가_가장_가깝다() {
        // 2회차 성수 취소와 배우 C 불참. 점수 1등인 한강안은 S18, S19가 성수 세트에만 있어 어떤 조율로도 성립하지 않는다.
        PlanInput seed = SeedPlan.day2(true);
        Map<Long, ActorDay> days = new HashMap<>(seed.actorDays());
        days.put(3L, new ActorDay(3, true, null, List.of(), List.of()));
        Map<Long, com.shortcut.domain.Location> locations = new HashMap<>(seed.locations());
        locations.computeIfPresent(2L, (id, l) -> l.unavailable());
        PlanInput withDays = withActorDays(seed, days);
        PlanInput input = new PlanInput(withDays.callTime(), withDays.morningEnd(), withDays.budgetCap(),
                withDays.crewWeeklyHoursUsed(), withDays.current(), withDays.blockActorIds(),
                withDays.actorOtherBlockMinutes(), withDays.actors(), locations, withDays.equipment(), withDays.options(),
                withDays.precipByLocation(), withDays.alerts(), withDays.alternativeLocationIds(), withDays.rainBlockMm(),
                withDays.rainWarnMm(), withDays.blockScenes(), withDays.actorDays(), withDays.otherBlocks(),
                withDays.sunrise(), withDays.sunset());

        EvaluationResult result = engine.evaluate(input, null, List.of());
        CandidateResult closest = PlanEngine.closestFirst(result.candidates()).getFirst();

        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
        assertThat(result.candidates().getFirst().violations()).extracting(Finding::code).contains("SCRIPT_SETTING_LOCKED");
        assertThat(closest.location().id()).isEqualTo(2L);
        assertThat(closest.start()).isEqualTo(t("14:00"));
        assertThat(closest.violations()).extracting(Finding::code)
                .containsExactlyInAnyOrder("LOCATION_CANCELLED", "ACTOR_UNAVAILABLE");
    }

    /** 비가 오지 않는 입력이다. 시드 입력은 한강 공원에 13시부터 비가 와서 배우 일정만 따로 보기 어렵다. */
    private static PlanInput dry(PlanInput in) {
        Map<Long, Map<Integer, Double>> precip = new HashMap<>();
        in.precipByLocation().forEach((id, hourly) -> {
            Map<Integer, Double> zero = new HashMap<>();
            hourly.keySet().forEach(hour -> zero.put(hour, 0.0));
            precip.put(id, zero);
        });
        return new PlanInput(in.callTime(), in.morningEnd(), in.budgetCap(), in.crewWeeklyHoursUsed(), in.current(),
                in.blockActorIds(), in.actorOtherBlockMinutes(), in.actors(), in.locations(), in.equipment(), in.options(),
                precip, in.alerts(), in.alternativeLocationIds(), in.rainBlockMm(), in.rainWarnMm(),
                in.blockScenes(), in.actorDays(), in.otherBlocks(), in.sunrise(), in.sunset());
    }

    private static PlanInput withActorDays(PlanInput in, Map<Long, ActorDay> days) {
        return new PlanInput(in.callTime(), in.morningEnd(), in.budgetCap(), in.crewWeeklyHoursUsed(), in.current(),
                in.blockActorIds(), in.actorOtherBlockMinutes(), in.actors(), in.locations(), in.equipment(), in.options(),
                in.precipByLocation(), in.alerts(), in.alternativeLocationIds(), in.rainBlockMm(), in.rainWarnMm(),
                in.blockScenes(), Map.copyOf(days), in.otherBlocks(), in.sunrise(), in.sunset());
    }
}
