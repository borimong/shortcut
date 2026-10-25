package com.shortcut.engine;

import static com.shortcut.engine.SeedPlan.t;
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ApproverRuleTest {

    private static final PlanSnapshot CURRENT = new PlanSnapshot(1, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), 300000);

    @Test
    void 관리자가_바꾼_규칙을_따른다() {
        // 장소가 바뀌면 제작실장도 승인하고, 항상 승인자는 제작 PD로 바꾼 규칙이다.
        Map<String, List<String>> rules = Map.of(
                "ALWAYS", List.of("PRODUCER"),
                "LOCATION", List.of("SOUND", "PRODUCTION_MANAGER"),
                "EQUIPMENT", List.of(), "TIME", List.of(), "COST", List.of());
        PlanSnapshot paju = new PlanSnapshot(3, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), 600000);

        assertThat(ApproverRule.requiredApprovers(CURRENT, paju, rules))
                .containsExactly("PRODUCER", "PRODUCTION_MANAGER", "SOUND");
    }

    @Test
    void 규칙이_모두_비어도_연출감독_한_명은_승인한다() {
        Map<String, List<String>> empty = Map.of("ALWAYS", List.of());
        assertThat(ApproverRule.requiredApprovers(CURRENT, CURRENT, empty)).containsExactly("DIRECTOR");
    }

    @Test
    void 아무것도_안_바뀌면_감독만_승인한다() {
        assertThat(ApproverRule.requiredApprovers(CURRENT, CURRENT)).containsExactly("DIRECTOR");
    }

    @Test
    void 씬_순서만_바뀌면_조감독_둘이_함께_승인한다() {
        PlanSnapshot committed = new PlanSnapshot(2, List.of(1L, 5L), t("14:00"), t("16:00"), 450000,
                List.of(new SceneSlot("S18", t("14:00"), t("15:30")), new SceneSlot("S19", t("15:30"), t("16:00"))));
        PlanSnapshot swapped = new PlanSnapshot(2, List.of(1L, 5L), t("14:00"), t("16:00"), 450000,
                List.of(new SceneSlot("S19", t("14:00"), t("14:30")), new SceneSlot("S18", t("14:30"), t("16:00"))));

        assertThat(ApproverRule.requiredApprovers(committed, swapped)).containsExactly("DIRECTOR", "AD1", "AD2");
        // 씬 순서를 남기기 전에 만든 기록과는 순서를 비교하지 않는다.
        PlanSnapshot legacy = new PlanSnapshot(2, List.of(1L, 5L), t("14:00"), t("16:00"), 450000);
        assertThat(ApproverRule.requiredApprovers(legacy, swapped)).containsExactly("DIRECTOR");
    }

    @Test
    void 성수_스튜디오안은_장소_시간_비용이_바뀌어_다섯_명이다() {
        PlanSnapshot seongsu = new PlanSnapshot(2, List.of(3L, 2L, 1L), t("14:00"), t("16:00"), 450000);

        assertThat(ApproverRule.requiredApprovers(CURRENT, seongsu))
                .containsExactly("DIRECTOR", "AD1", "SOUND", "AD2", "PRODUCER");
    }

    @Test
    void 장비만_바뀌고_비용이_같으면_촬영감독이_더해진다() {
        PlanSnapshot gimbal = new PlanSnapshot(1, List.of(1L, 5L), t("13:00"), t("15:00"), 300000);

        assertThat(ApproverRule.requiredApprovers(CURRENT, gimbal)).containsExactly("DIRECTOR", "DOP");
    }

    @Test
    void 장소와_시간이_함께_바뀌어도_1조감독은_한_번만_들어간다() {
        PlanSnapshot paju = new PlanSnapshot(3, List.of(1L, 5L), t("14:00"), t("16:00"), 600000);

        assertThat(ApproverRule.requiredApprovers(CURRENT, paju))
                .containsExactly("DIRECTOR", "AD1", "SOUND", "DOP", "AD2", "PRODUCER");
    }

    @Test
    void 비용이_줄면_제작_PD는_빠진다() {
        PlanSnapshot cheaper = new PlanSnapshot(4, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), 0);

        assertThat(ApproverRule.requiredApprovers(CURRENT, cheaper)).containsExactly("DIRECTOR", "AD1", "SOUND");
    }

    @Test
    void 제작_PD_범위에는_추가_비용을_적는다() {
        assertThat(ApproverRule.scope("PRODUCER", 150000)).isEqualTo("추가 비용 150,000원");
        assertThat(ApproverRule.scope("SOUND", 0)).isEqualTo("장소 소음");
    }
}
