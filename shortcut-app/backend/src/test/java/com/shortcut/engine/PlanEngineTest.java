package com.shortcut.engine;

import static com.shortcut.engine.SeedPlan.t;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.shortcut.domain.DisasterAlert;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.assertj.core.data.Offset;
import org.junit.jupiter.api.Test;

class PlanEngineTest {

    private final PlanEngine engine = new PlanEngine();

    private static final LocalDate TODAY = LocalDate.of(2026, 10, 21);

    private static final ExtraConstraint SEONGSU_AFTERNOON = new ExtraConstraint(
            "EXCLUDE_LOCATION_TIME", 2L, null, t("13:00"), t("18:00"), null, null, "공사 소음", "SOUND 거절");

    @Test
    void 기본_가중치면_성수_스튜디오_장비1안_시간2안이_1등이다() {
        EvaluationResult result = engine.evaluate(SeedPlan.input(List.of()), null, List.of());

        assertThat(result.candidates()).hasSize(27);
        CandidateResult best = result.candidates().getFirst();
        assertThat(best.feasible()).isTrue();
        assertThat(best.hash()).isEqualTo("L2-E1,2,3-T14001600");
        assertThat(best.locationOptionNo()).isEqualTo(2);
        assertThat(best.equipmentOptionNo()).isEqualTo(1);
        assertThat(best.timeOptionNo()).isEqualTo(2);
        assertThat(best.totalScore()).isCloseTo(0.79, Offset.offset(0.001));
        assertThat(best.extraCost()).isEqualTo(150000);

        List<CandidateResult> hangang = result.candidates().stream().filter(c -> c.location().id() == 1).toList();
        assertThat(hangang).hasSize(9).allSatisfy(c -> {
            assertThat(c.feasible()).isFalse();
            assertThat(codes(c)).contains("RAIN_HARD");
        });
        assertThat(result.weights()).containsEntry("location", 0.25).containsEntry("weather", 0.2);
    }

    @Test
    void 성수_오후를_제외하면_파주_장비3안_시간2안이_1등이고_파주_드론은_막힌다() {
        EvaluationResult result = engine.evaluate(SeedPlan.input(List.of()), null, List.of(SEONGSU_AFTERNOON));

        CandidateResult best = result.candidates().getFirst();
        assertThat(best.feasible()).isTrue();
        assertThat(best.hash()).isEqualTo("L3-E1,5-T14001600");
        assertThat(best.equipmentOptionNo()).isEqualTo(3);
        assertThat(best.timeOptionNo()).isEqualTo(2);

        CandidateResult pajuWithDrone = find(result, "L3-E1,2,3-T14001600");
        assertThat(codes(pajuWithDrone)).containsExactly("DRONE_NO_FLY");
        assertThat(codes(find(result, "L2-E1,2,3-T14001600"))).containsExactly("EXCLUDED_BY_CONSTRAINT");
        assertThat(find(result, "L2-E1,2,3-T14001600").violations().getFirst().ruleRef())
                .isEqualTo("EXTRA_EXCLUDE_LOCATION_TIME");
    }

    @Test
    void 서울_재난_문자가_더해져도_파주가_1등이다() {
        List<DisasterAlert> alerts = List.of(
                new DisasterAlert(1, TODAY, "서울 영등포구", "호우", t("13:00"), t("18:00"), "호우 경보"),
                new DisasterAlert(2, TODAY, "서울 성동구", "호우", t("13:00"), t("18:00"), "호우 경보"));
        EvaluationResult result = engine.evaluate(SeedPlan.input(alerts), null, List.of(SEONGSU_AFTERNOON));

        assertThat(result.candidates().getFirst().hash()).isEqualTo("L3-E1,5-T14001600");
        assertThat(codes(find(result, "L1-E1,2,3-T13001500"))).contains("DISASTER_ALERT", "RAIN_HARD");
        assertThat(codes(find(result, "L2-E1,4-T14001600"))).contains("DISASTER_ALERT");
    }

    @Test
    void 재난_문자_지역은_정식_이름과_시도_단위로도_맞춘다() {
        List<DisasterAlert> alerts = List.of(
                new DisasterAlert(1, TODAY, "서울특별시  성동구", "호우", t("13:00"), t("18:00"), "호우 경보"),
                new DisasterAlert(2, TODAY, "경기도", "호우", t("13:00"), t("18:00"), "호우 경보"));
        EvaluationResult result = engine.evaluate(SeedPlan.input(alerts), null, List.of());

        assertThat(codes(find(result, "L2-E1,4-T14001600"))).contains("DISASTER_ALERT");
        assertThat(codes(find(result, "L3-E1,5-T14001600"))).contains("DISASTER_ALERT");
        assertThat(codes(find(result, "L1-E1,2,3-T13001500"))).doesNotContain("DISASTER_ALERT");
    }

    @Test
    void 모든_장소를_제외하면_가능한_후보가_없다() {
        List<ExtraConstraint> excludeAll = List.of(1L, 2L, 3L).stream()
                .map(id -> new ExtraConstraint("EXCLUDE_LOCATION", id, null, null, null, null, null, "제외", "test"))
                .toList();
        EvaluationResult result = engine.evaluate(SeedPlan.input(List.of()), null, excludeAll);

        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
    }

    @Test
    void 파주_이른_시간대는_이동_시간_때문에_막힌다() {
        EvaluationResult result = engine.evaluate(SeedPlan.input(List.of()), null, List.of());

        assertThat(codes(find(result, "L3-E1,5-T12301430"))).containsExactly("TRAVEL_TOO_LONG");
        assertThat(codes(find(result, "L2-E1,4-T13001500"))).containsExactly("LOCATION_CLOSED");
    }

    @Test
    void 추가_비용_상한은_예산_위반으로_분류된다() {
        ExtraConstraint maxExtra = new ExtraConstraint("MAX_EXTRA_COST", null, null, null, null, 100000L, null, "예산", "PRODUCER 거절");
        CheckResult check = engine.check(SeedPlan.input(List.of()), 2, List.of(1L, 2L, 3L), t("14:00"), t("16:00"), List.of(maxExtra));

        assertThat(check.violations()).extracting(Finding::code).containsExactly("BUDGET_EXCEEDED");
        assertThat(check.violations().getFirst().ruleRef()).isEqualTo("EXTRA_MAX_EXTRA_COST");
    }

    @Test
    void 요청_가중치는_합이_1이_되도록_정규화한다() {
        Map<String, Double> weights = PlanEngine.normalizeWeights(Map.of("budget", 0.65));

        assertThat(weights.values().stream().mapToDouble(Double::doubleValue).sum()).isCloseTo(1.0, Offset.offset(1e-9));
        assertThat(weights.get("budget")).isCloseTo(0.65 / 1.5, Offset.offset(1e-9));
    }

    @Test
    void 알_수_없는_추가_제약은_거부한다() {
        ExtraConstraint unknown = new ExtraConstraint("NO_RAIN_DANCE", null, null, null, null, null, null, null, null);

        assertThatThrownBy(() -> engine.evaluate(SeedPlan.input(List.of()), null, List.of(unknown)))
                .isInstanceOf(PlanRuleException.class)
                .satisfies(e -> assertThat(((PlanRuleException) e).code()).isEqualTo("UNKNOWN_CONSTRAINT"));
    }

    private static CandidateResult find(EvaluationResult result, String hash) {
        return result.candidates().stream().filter(c -> c.hash().equals(hash)).findFirst().orElseThrow();
    }

    @Test
    void 일이삼안이_모두_막히면_등록한_4안_장소가_1등이_된다() {
        List<ExtraConstraint> rejected = List.of(SEONGSU_AFTERNOON,
                new ExtraConstraint("EXCLUDE_LOCATION", 3L, null, null, null, null, null, "장면 의도와 맞지 않음", "DIRECTOR 거절"));
        assertThat(engine.evaluate(SeedPlan.input(List.of()), null, rejected).candidates())
                .noneMatch(CandidateResult::feasible);

        EvaluationResult result = engine.evaluate(SeedPlan.withAlternative(SeedPlan.input(List.of())), null, rejected);

        assertThat(result.candidates()).hasSize(36);
        CandidateResult best = result.candidates().getFirst();
        assertThat(best.feasible()).isTrue();
        assertThat(best.locationOptionNo()).isEqualTo(PlanEngine.ALTERNATIVE_OPTION_NO);
        assertThat(best.hash()).isEqualTo("L101-E1,2,3-T13001500");
        // 오전 종료 11:30에서 25km 이동과 세팅을 마치면 12:50이라 12:30 시작안은 막힌다.
        assertThat(codes(find(result, "L101-E1,5-T12301430"))).contains("TRAVEL_TOO_LONG");
    }

    @Test
    void 시간대_제외_제약은_겹치는_후보만_막는다() {
        ExtraConstraint noEarlyAfternoon = new ExtraConstraint("EXCLUDE_TIME", null, null, t("13:00"), t("15:00"), null, null,
                "13~15시는 다른 촬영과 겹침", "AD1 거절");
        EvaluationResult result = engine.evaluate(SeedPlan.input(List.of()), null, List.of(noEarlyAfternoon));

        assertThat(codes(find(result, "L2-E1,2,3-T14001600"))).contains("EXCLUDED_BY_CONSTRAINT");
        assertThat(result.candidates().getFirst().feasible()).isFalse();
    }

    @Test
    void 강수량이_관리자_기준보다_적으면_야외안도_경고만_남는다() {
        // 한강 공원은 13시부터 시간당 8mm라 기본 기준(5mm)에서는 막히지만, 기준을 10mm로 올리면 경고만 남는다.
        CheckResult strict = engine.check(SeedPlan.input(List.of()), 1, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), List.of());
        assertThat(strict.violations()).extracting(Finding::code).contains("RAIN_HARD");

        PlanInput lenient = SeedPlan.withRainRule(SeedPlan.input(List.of()), 10.0, 1.0);
        CheckResult relaxed = engine.check(lenient, 1, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), List.of());
        assertThat(relaxed.violations()).extracting(Finding::code).doesNotContain("RAIN_HARD");
        assertThat(relaxed.warnings()).extracting(Finding::code).contains("RAIN_SOFT");
    }

    @Test
    void 변경_입력에서_취소한_장소는_후보에서_막힌다() {
        PlanInput input = SeedPlan.withCancelledLocation(SeedPlan.input(List.of()), 2);
        EvaluationResult result = engine.evaluate(input, null, List.of());

        assertThat(codes(find(result, "L2-E1,2,3-T14001600"))).contains("LOCATION_CANCELLED");
        assertThat(result.candidates().getFirst().location().id()).isNotEqualTo(2);
    }

    @Test
    void 불참_배우가_나오는_블록은_모든_후보가_막힌다() {
        PlanInput input = SeedPlan.withAbsentActor(SeedPlan.input(List.of()), 1);
        EvaluationResult result = engine.evaluate(input, null, List.of());

        assertThat(result.candidates()).allSatisfy(c -> assertThat(c.violations())
                .anySatisfy(f -> assertThat(f.message()).contains("배우 A은(는) 오늘 촬영에 참여할 수 없습니다")));
    }

    @Test
    void 대본을_넣어도_우천_1등은_성수이고_야외_장면_경고만_붙는다() {
        EvaluationResult result = engine.evaluate(SeedPlan.withScript(SeedPlan.input(List.of())), null, List.of());

        CandidateResult best = result.candidates().getFirst();
        assertThat(best.hash()).isEqualTo("L2-E1,2,3-T14001600");
        assertThat(best.feasible()).isTrue();
        assertThat(best.warnings()).extracting(Finding::code).containsExactly("SCRIPT_EXT_INDOOR");
        assertThat(best.warnings().getFirst().message()).contains("S12, S13", "성수 스튜디오", "연출 확인");
        // 드론과 반사판이 없는 장비 묶음은 선호 장비 경고만 받는다.
        assertThat(find(result, "L2-E1,4-T14001600").warnings()).extracting(Finding::code)
                .contains("SCRIPT_EQUIPMENT_WANTED");
        assertThat(find(result, "L2-E1,4-T14001600").feasible()).isTrue();
    }

    @Test
    void 해가_지면_낮_야외_장면을_찍을_수_없다() {
        PlanInput rainless = SeedPlan.withRainRule(SeedPlan.input(List.of()), 100, 100);
        PlanInput input = SeedPlan.withScript(rainless, SeedPlan.seedScenes(), Map.of(), SeedPlan.seedMorning(), t("14:00"));

        CheckResult hangang = engine.check(input, 1, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), List.of());
        assertThat(hangang.violations()).extracting(Finding::code).containsExactly("SCRIPT_DAYLIGHT");
        // 실내 스튜디오는 조명으로 낮을 만들 수 있어 막지 않는다.
        CheckResult studio = engine.check(input, 2, List.of(1L, 2L, 3L), t("14:00"), t("16:00"), List.of());
        assertThat(studio.violations()).isEmpty();
    }

    @Test
    void 밤_야외_장면은_일몰_전에_시작할_수_없다() {
        List<ScenePlan> night = List.of(new ScenePlan("S21", 120, true, true, false, null, List.of(), List.of(), List.of()));
        PlanInput input = SeedPlan.withScript(SeedPlan.withRainRule(SeedPlan.input(List.of()), 100, 100), night,
                Map.of(), SeedPlan.seedMorning(), t("17:40"));

        CheckResult check = engine.check(input, 1, List.of(1L), t("13:00"), t("15:00"), List.of());
        assertThat(check.violations()).extracting(Finding::code).contains("SCRIPT_DAYLIGHT");
        assertThat(check.violations()).anySatisfy(f -> assertThat(f.message()).contains("S21", "일몰(17:40)"));
    }

    @Test
    void 필수_장비가_없거나_배역이_캐스팅_전이면_막힌다() {
        List<ScenePlan> scenes = List.of(
                new ScenePlan("S12", 90, true, false, false, null, List.of("문태"), List.of(1L, 2L), List.of()),
                new ScenePlan("S13", 30, true, false, false, null, List.of(), List.of(1L), List.of()));
        PlanInput input = SeedPlan.withScript(SeedPlan.input(List.of()), scenes, Map.of(), SeedPlan.seedMorning(),
                t("17:40"));

        CheckResult check = engine.check(input, 2, List.of(1L, 4L), t("14:00"), t("16:00"), List.of());
        assertThat(check.violations()).extracting(Finding::code)
                .containsExactlyInAnyOrder("SCRIPT_EQUIPMENT_MISSING", "CHARACTER_UNCAST");
        assertThat(check.violations()).anySatisfy(f -> assertThat(f.message()).contains("드론"));
    }

    @Test
    void 세트가_고정된_씬은_다른_장소에서_찍을_수_없다() {
        List<ScenePlan> workshop = List.of(
                new ScenePlan("S18", 90, false, false, true, 2L, List.of(), List.of(1L), List.of()),
                new ScenePlan("S19", 30, false, false, true, 2L, List.of(), List.of(1L), List.of()));
        PlanInput input = SeedPlan.withScript(SeedPlan.input(List.of()), workshop, Map.of(), SeedPlan.seedMorning(),
                t("17:40"));

        EvaluationResult result = engine.evaluate(input, null, List.of());
        assertThat(codes(find(result, "L3-E1,5-T14001600"))).contains("SCRIPT_SETTING_LOCKED");
        assertThat(codes(find(result, "L2-E1,5-T14001600"))).doesNotContain("SCRIPT_SETTING_LOCKED");
    }

    @Test
    void 씬_길이_합이_후보_시간보다_길면_막힌다() {
        List<ScenePlan> longer = List.of(new ScenePlan("S12", 150, true, false, false, null, List.of(), List.of(), List.of()));
        PlanInput input = SeedPlan.withScript(SeedPlan.input(List.of()), longer, Map.of(), SeedPlan.seedMorning(),
                t("17:40"));

        CheckResult check = engine.check(input, 2, List.of(1L, 2L, 3L), t("14:00"), t("16:00"), List.of());
        assertThat(check.violations()).extracting(Finding::code).containsExactly("BLOCK_OVERFLOW");
    }

    @Test
    void 배우의_그날_다른_일정과_겹치는_시간대만_막힌다() {
        // 1회차 목데이터처럼 배우 A가 12:00~13:00에 병원 진료가 있다.
        ActorDay clinic = new ActorDay(1, false, null, List.of(new ActorDay.Window(t("09:00"), t("16:00"))),
                List.of(new ActorDay.Busy(t("12:00"), t("13:00"), "PERSONAL")));
        PlanInput input = SeedPlan.withScript(SeedPlan.input(List.of()), SeedPlan.seedScenes(), Map.of(1L, clinic),
                SeedPlan.seedMorning(), t("17:40"));

        EvaluationResult result = engine.evaluate(input, null, List.of());
        CandidateResult early = find(result, "L2-E1,2,3-T12301430");
        assertThat(codes(early)).contains("ACTOR_BUSY");
        assertThat(early.violations()).anySatisfy(f -> assertThat(f.message()).contains("배우 A", "12:00~13:00 개인 일정"));
        assertThat(codes(find(result, "L1-E1,2,3-T13001500"))).doesNotContain("ACTOR_BUSY");
        assertThat(result.candidates().getFirst().hash()).isEqualTo("L2-E1,2,3-T14001600");
    }

    @Test
    void 종일_불가는_사유_종류와_함께_막는다() {
        ActorDay film = new ActorDay(1, true, "OTHER_PRODUCTION", List.of(), List.of());
        PlanInput input = SeedPlan.withScript(SeedPlan.input(List.of()), SeedPlan.seedScenes(), Map.of(1L, film),
                SeedPlan.seedMorning(), t("17:40"));

        assertThat(engine.evaluate(input, null, List.of()).candidates()).allSatisfy(c -> assertThat(c.violations())
                .anySatisfy(f -> assertThat(f.message()).isEqualTo("배우 A은(는) 오늘 촬영에 참여할 수 없습니다(타 작품).")));
    }

    @Test
    void 같은_배우가_시간이_겹치는_다른_블록에_나오면_막힌다() {
        List<BlockSlot> lateMorning = List.of(new BlockSlot("AM", t("07:00"), t("13:30"), List.of(2L, 3L)));
        PlanInput input = SeedPlan.withScript(SeedPlan.input(List.of()), SeedPlan.seedScenes(), Map.of(), lateMorning,
                t("17:40"));

        CheckResult check = engine.check(input, 2, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), List.of());
        assertThat(check.violations()).extracting(Finding::code).contains("ACTOR_OVERLAP");
        assertThat(check.violations()).anySatisfy(f -> assertThat(f.message()).contains("배우 B", "AM 블록"));
    }

    @Test
    void 대본_실내외_맞춤_제약이면_실내로_옮기는_후보가_막힌다() {
        ExtraConstraint keepOutdoor = new ExtraConstraint("REQUIRE_SETTING_MATCH", null, null, null, null, null, null,
                "야외 장면은 야외에서", "DIRECTOR 거절");
        EvaluationResult result = engine.evaluate(SeedPlan.withScript(SeedPlan.input(List.of())), null,
                List.of(keepOutdoor));

        assertThat(codes(find(result, "L2-E1,2,3-T14001600"))).contains("EXCLUDED_BY_CONSTRAINT");
        assertThat(result.candidates()).noneMatch(CandidateResult::feasible);
    }

    private static List<String> codes(CandidateResult candidate) {
        return candidate.violations().stream().map(Finding::code).toList();
    }
}
