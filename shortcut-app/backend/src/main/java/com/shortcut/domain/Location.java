package com.shortcut.domain;

import java.time.LocalTime;

public record Location(
        long id,
        String name,
        String address,
        boolean indoor,
        String region,
        LocalTime openFrom,
        LocalTime openTo,
        LocalTime permitFrom,
        LocalTime permitTo,
        long cost,
        boolean noFlyZone,
        double fit,
        double distanceKm,
        String note) {
}
