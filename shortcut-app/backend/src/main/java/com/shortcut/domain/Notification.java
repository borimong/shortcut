package com.shortcut.domain;

import java.time.OffsetDateTime;

public record Notification(
        long id,
        String username,
        String kind,
        String title,
        String body,
        String link,
        boolean read,
        OffsetDateTime createdAt) {
}
