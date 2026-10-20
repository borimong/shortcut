package com.shortcut.domain;

import java.util.List;

public record ExternalLocation(
        long id,
        String name,
        boolean indoor,
        String region,
        double distanceKm,
        long cost,
        List<String> keywords) {
}
