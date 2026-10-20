package com.shortcut.domain;

import com.shortcut.engine.PlanSnapshot;
import java.time.OffsetDateTime;

public record Callsheet(
        long id,
        long shootDayId,
        int versionNo,
        Long proposalId,
        PlanSnapshot pm,
        OffsetDateTime createdAt) {
}
