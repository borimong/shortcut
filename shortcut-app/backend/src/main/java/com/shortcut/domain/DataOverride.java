package com.shortcut.domain;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.LocalDate;
import java.time.OffsetDateTime;

/**
 * 변경 입력이나 자원 현황 패널이 남긴 촬영일 데이터 덮어쓰기 한 건이다.
 * kind는 EQUIPMENT_UNAVAILABLE, ACTOR_WINDOW, LOCATION_UNAVAILABLE, RAIN_FORECAST 중 하나다.
 * untilDate가 있으면 startsOn부터 그날까지 모든 촬영일에, 없으면 shootDayId 촬영일에만 적용된다.
 */
public record DataOverride(long id, long shootDayId, Long eventId, String kind, Long targetId, JsonNode payload,
                           LocalDate startsOn, LocalDate untilDate, String memo, String createdBy,
                           OffsetDateTime createdAt) {
}
