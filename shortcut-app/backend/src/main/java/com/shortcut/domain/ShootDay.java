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
        double crewWeeklyHoursUsed,
        LocalTime sunrise,
        LocalTime sunset) {

    /** 일출·일몰을 모르는 촬영일이다. 낮/밤 대본 규칙을 건너뛴다. */
    public ShootDay(long id, long projectId, String projectName, LocalDate shootDate, LocalTime callTime, int dataVersion,
                    String notice, String crewCallsJson, long blockBudgetCap, double crewWeeklyHoursUsed) {
        this(id, projectId, projectName, shootDate, callTime, dataVersion, notice, crewCallsJson, blockBudgetCap,
                crewWeeklyHoursUsed, null, null);
    }
}
