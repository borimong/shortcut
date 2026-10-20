package com.shortcut.domain;

import java.time.LocalDate;
import java.time.LocalTime;

public record ShootDay(
        long id,
        long projectId,
        String projectName,
        LocalDate shootDate,
        LocalTime callTime,
        int dataVersion,
        String notice,
        String crewCallsJson,
        long blockBudgetCap,
        double crewWeeklyHoursUsed) {
}
