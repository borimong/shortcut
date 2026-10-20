package com.shortcut.domain;

import java.util.List;

public record Scene(
        String code,
        String blockCode,
        String title,
        int durationMin,
        boolean outdoorIntent,
        List<Long> actorIds) {
}
