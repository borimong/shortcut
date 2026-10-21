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
        String note,
        boolean available) {

    /** 변경 입력의 장소 취소를 반영해 이용할 수 없는 장소로 바꾼다. */
    public Location unavailable() {
        return new Location(id, name, address, indoor, region, openFrom, openTo, permitFrom, permitTo, cost, noFlyZone,
                fit, distanceKm, note, false);
    }
}
