package com.shortcut.domain;

import java.time.LocalTime;
import java.util.List;

public record Block(
        String code,
        LocalTime start,
        LocalTime end,
        int durationMin,
        Long locationId,
        List<Long> equipmentIds) {

    public int minutes() {
        return (end.toSecondOfDay() - start.toSecondOfDay()) / 60;
    }
}
