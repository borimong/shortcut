package com.shortcut.engine;

import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;

/**
 * @param sceneOrder 이 후보로 찍을 블록 씬 시각표. 배우 일정이나 해 때문에 지금 순서로 막히면 엔진이 순서를 바꾼다
 * @param sceneOrderChanged 지금 확정 순서와 씬 순서가 다르다
 */
public record CandidateResult(
        String hash,
        int locationOptionNo,
        Location location,
        int equipmentOptionNo,
        List<Equipment> equipment,
        int timeOptionNo,
        LocalTime start,
        LocalTime end,
        boolean feasible,
        List<Finding> violations,
        List<Finding> warnings,
        Map<String, Double> softScores,
        double totalScore,
        long cost,
        long extraCost,
        double distanceKm,
        List<SceneSlot> sceneOrder,
        boolean sceneOrderChanged) {
}
