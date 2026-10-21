package com.shortcut.domain;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * 변경 입력이 남긴 촬영일 데이터 덮어쓰기 한 건이다.
 * kind는 EQUIPMENT_UNAVAILABLE, ACTOR_WINDOW, LOCATION_UNAVAILABLE, RAIN_FORECAST 중 하나다.
 */
public record DataOverride(long id, long shootDayId, Long eventId, String kind, Long targetId, JsonNode payload) {
}
