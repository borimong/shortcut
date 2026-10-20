package com.shortcut.domain;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.engine.PlanSnapshot;
import java.time.OffsetDateTime;

public record Proposal(
        long id,
        long taskId,
        Long eventId,
        long shootDayId,
        int loopNo,
        int versionNo,
        String status,
        int dataVersion,
        PlanSnapshot original,
        PlanSnapshot proposed,
        JsonNode source,
        double score,
        JsonNode scoreBreakdown,
        JsonNode weights,
        String explanation,
        JsonNode checklist,
        JsonNode evidence,
        JsonNode unresolved,
        JsonNode review,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {

    public String versionLabel() {
        return "v" + versionNo;
    }
}
