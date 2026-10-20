package com.shortcut.engine;

import java.time.LocalTime;
import java.util.Set;

/**
 * 거절 사유에서 Agent가 만든 추가 제약이다.
 * 요청 JSON을 그대로 받으려고 모든 유형의 필드를 한 레코드에 둔다.
 */
public record ExtraConstraint(
        String type,
        Long locationId,
        Long equipmentId,
        LocalTime from,
        LocalTime to,
        Long amount,
        LocalTime time,
        String reason,
        String source) {

    public static final Set<String> TYPES = Set.of(
            "EXCLUDE_LOCATION", "EXCLUDE_LOCATION_TIME", "EXCLUDE_EQUIPMENT",
            "MAX_EXTRA_COST", "REQUIRE_INDOOR", "LATEST_END", "EXCLUDE_TIME");

    void validate() {
        if (type == null || !TYPES.contains(type)) {
            throw new PlanRuleException("UNKNOWN_CONSTRAINT", "알 수 없는 추가 제약 유형입니다: " + type);
        }
        boolean complete = switch (type) {
            case "EXCLUDE_LOCATION" -> locationId != null;
            case "EXCLUDE_LOCATION_TIME" -> locationId != null && from != null && to != null && from.isBefore(to);
            case "EXCLUDE_EQUIPMENT" -> equipmentId != null;
            case "MAX_EXTRA_COST" -> amount != null && amount >= 0;
            case "LATEST_END" -> time != null;
            case "EXCLUDE_TIME" -> from != null && to != null && from.isBefore(to);
            default -> true;
        };
        if (!complete) {
            throw new PlanRuleException("INVALID_CONSTRAINT", type + " 제약에 필요한 값이 없거나 잘못되었습니다.");
        }
    }

    String describe() {
        return reason == null || reason.isBlank() ? type : reason;
    }
}
