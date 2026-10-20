package com.shortcut.domain;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.OffsetDateTime;
import java.util.Set;

public record AiTask(
        long id,
        String kind,
        String status,
        String question,
        String answer,
        JsonNode sources,
        Long eventId,
        Long proposalId,
        String traceUrl,
        String threadId,
        String traceId,
        long shootDayId,
        String requestedBy,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {

    public static final Set<String> TERMINAL = Set.of("DONE", "FAILED", "NEEDS_HUMAN");

    public boolean finished() {
        return TERMINAL.contains(status);
    }
}
