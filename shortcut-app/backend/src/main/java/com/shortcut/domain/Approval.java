package com.shortcut.domain;

import java.time.OffsetDateTime;
import java.util.List;

public record Approval(
        long id,
        long proposalId,
        int seq,
        String role,
        String status,
        String userName,
        String reason,
        List<String> issues,
        OffsetDateTime decidedAt) {
}
