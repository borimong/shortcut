package com.shortcut.domain;

import java.time.OffsetDateTime;

public record ChangeEvent(
        long id,
        long shootDayId,
        String type,
        String detail,
        String instruction,
        int dataVersion,
        String requestedBy,
        OffsetDateTime createdAt) {
}
