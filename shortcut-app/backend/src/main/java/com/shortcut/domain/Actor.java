package com.shortcut.domain;

import java.time.LocalTime;

public record Actor(
        long id,
        String name,
        LocalTime availableFrom,
        LocalTime availableTo,
        double weeklyHoursUsed,
        String contractDocId,
        boolean noNight,
        Double maxDailyHours,
        String managerPhone) {
}
