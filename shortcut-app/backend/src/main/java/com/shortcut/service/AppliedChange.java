package com.shortcut.service;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonPropertyOrder;

/**
 * 검사를 마친 변경 한 건이다. 이벤트의 changes 컬럼과 중복 키에 JSON으로 그대로 남고, Agent와 변동 이력이 읽는다.
 * 종류마다 쓰는 필드만 채우고 나머지는 JSON에서 뺀다. 필드 순서가 곧 JSON 키 순서다.
 *
 * @param kind 변경 종류(EQUIPMENT_UNAVAILABLE 등). 자원 패널에서 되돌리기는 CLEAR
 * @param targetId 장비, 배우, 장소 id
 * @param overrideId CLEAR일 때 되돌린 상태 기록 id
 * @param region 재난 문자 지역
 * @param alertKind 재난 문자 종류
 * @param from 배우 가용 시작 또는 재난 문자 시작(HH:mm)
 * @param to 배우 가용 끝 또는 재난 문자 끝(HH:mm)
 * @param reasonKind 배우 다른 일정(ACTOR_BUSY)의 사유 종류. 개인 사정의 내용은 남기지 않는다
 * @param fromHour 비 시작 시각
 * @param toHour 비 끝 시각(포함)
 * @param mm 시간당 강수량
 * @param summary Agent와 변동 이력에 보이는 한 줄 요약
 * @param status 장비 상태(REPAIR). 자원 패널에서만
 * @param untilDate 적용 끝 날짜(yyyy-MM-dd). 자원 패널에서만
 * @param memo 메모. 자원 패널에서만
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
@JsonPropertyOrder({"kind", "targetId", "overrideId", "region", "alertKind", "from", "to", "reasonKind", "fromHour", "toHour",
        "mm", "summary", "status", "untilDate", "memo"})
public record AppliedChange(
        String kind,
        Long targetId,
        Long overrideId,
        String region,
        String alertKind,
        String from,
        String to,
        String reasonKind,
        Integer fromHour,
        Integer toHour,
        Double mm,
        String summary,
        String status,
        String untilDate,
        String memo) {

    public static final String CLEAR = "CLEAR";

    static AppliedChange target(String kind, long targetId, String summary) {
        return new AppliedChange(kind, targetId, null, null, null, null, null, null, null, null, null, summary, null, null,
                null);
    }

    static AppliedChange window(String kind, long targetId, String from, String to, String summary) {
        return new AppliedChange(kind, targetId, null, null, null, from, to, null, null, null, null, summary, null, null,
                null);
    }

    static AppliedChange busy(long targetId, String from, String to, String reasonKind, String summary) {
        return new AppliedChange("ACTOR_BUSY", targetId, null, null, null, from, to, reasonKind, null, null, null, summary,
                null, null, null);
    }

    static AppliedChange rain(long targetId, int fromHour, int toHour, double mm, String summary) {
        return new AppliedChange("RAIN_FORECAST", targetId, null, null, null, null, null, null, fromHour, toHour, mm,
                summary, null, null, null);
    }

    static AppliedChange alert(String region, String alertKind, String from, String to, String summary) {
        return new AppliedChange("DISASTER_ALERT", null, null, region, alertKind, from, to, null, null, null, null,
                summary, null, null, null);
    }

    static AppliedChange clear(long overrideId, String summary) {
        return new AppliedChange(CLEAR, null, overrideId, null, null, null, null, null, null, null, null, summary, null,
                null, null);
    }

    boolean isClear() {
        return CLEAR.equals(kind);
    }

    AppliedChange withSummary(String value) {
        return new AppliedChange(kind, targetId, overrideId, region, alertKind, from, to, reasonKind, fromHour, toHour, mm,
                value, status, untilDate, memo);
    }

    AppliedChange withStatus(String value) {
        return new AppliedChange(kind, targetId, overrideId, region, alertKind, from, to, reasonKind, fromHour, toHour, mm,
                summary, value, untilDate, memo);
    }

    AppliedChange withUntilDate(String value) {
        return new AppliedChange(kind, targetId, overrideId, region, alertKind, from, to, reasonKind, fromHour, toHour, mm,
                summary, status, value, memo);
    }

    AppliedChange withMemo(String value) {
        return new AppliedChange(kind, targetId, overrideId, region, alertKind, from, to, reasonKind, fromHour, toHour, mm,
                summary, status, untilDate, value);
    }
}
