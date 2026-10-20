package com.shortcut.domain;

import java.time.LocalTime;
import java.util.List;

public record PlanOption(
        int optionNo,
        long locationId,
        List<Long> equipmentIds,
        double equipmentFit,
        LocalTime start,
        LocalTime end) {
}
