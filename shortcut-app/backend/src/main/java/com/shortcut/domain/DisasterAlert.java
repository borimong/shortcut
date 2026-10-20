package com.shortcut.domain;

import java.time.LocalTime;

public record DisasterAlert(
        long id,
        String region,
        String kind,
        LocalTime startsAt,
        LocalTime endsAt,
        String message) {
}
