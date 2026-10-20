package com.shortcut.engine;

import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;

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
        double distanceKm) {
}
