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

    // SUPERSEDED: 승인을 기다리던 중 촬영 데이터가 바뀌어 다른 변경으로 대체된 작업이다(SupersedeService).
    public static final Set<String> TERMINAL = Set.of("DONE", "FAILED", "NEEDS_HUMAN", "SUPERSEDED");

    public boolean finished() {
        return TERMINAL.contains(status);
    }
}
