package com.shortcut.domain;

/**
 * 장소와 시각별 시간당 강수량(mm)이다.
 */
public record WeatherHour(long locationId, int hour, double precipMm) {
}
