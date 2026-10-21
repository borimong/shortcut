package com.shortcut.domain;

import java.time.LocalDate;
import java.time.LocalTime;

public record DisasterAlert(
        long id,
        LocalDate date,
        String region,
        String kind,
        LocalTime startsAt,
        LocalTime endsAt,
        String message) {
}
