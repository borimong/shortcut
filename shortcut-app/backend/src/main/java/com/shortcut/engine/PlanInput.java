package com.shortcut.engine;

import com.shortcut.domain.Actor;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.PlanOption;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;

/**
 * 엔진이 판단에 쓰는 촬영일 데이터 전부다.
 * DB를 모르는 상태로 테스트하려고 필요한 값을 미리 모아서 넘긴다.
 *
 * @param actorOtherBlockMinutes 변경 대상 블록 밖에서 그 배우가 이미 촬영하는 분
 * @param precipByLocation 장소 id별 시각(0~23)별 시간당 강수량(mm)
 * @param alternativeLocationIds 1/2/3안이 모두 막혔을 때 Agent가 등록한 4안 대체 장소 id
 * @param rainBlockMm 이 강수량 이상이면 야외 촬영을 막는다(관리자 설정)
 * @param rainWarnMm 이 강수량 이상이면 우천 대비 경고를 남긴다(관리자 설정)
 */
public record PlanInput(
        LocalTime callTime,
        LocalTime morningEnd,
        long budgetCap,
        double crewWeeklyHoursUsed,
        PlanSnapshot current,
        List<Long> blockActorIds,
        Map<Long, Integer> actorOtherBlockMinutes,
        Map<Long, Actor> actors,
        Map<Long, Location> locations,
        Map<Long, Equipment> equipment,
        List<PlanOption> options,
        Map<Long, Map<Integer, Double>> precipByLocation,
        List<DisasterAlert> alerts,
        List<Long> alternativeLocationIds,
        double rainBlockMm,
        double rainWarnMm) {
}
