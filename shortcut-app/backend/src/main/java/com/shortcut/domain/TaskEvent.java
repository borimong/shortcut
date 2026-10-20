package com.shortcut.domain;

import java.time.OffsetDateTime;

public record TaskEvent(long id, long taskId, String type, String payloadJson, OffsetDateTime createdAt) {
}
