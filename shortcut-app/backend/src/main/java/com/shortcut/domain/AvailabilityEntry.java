package com.shortcut.domain;

import java.time.LocalDate;
import java.time.LocalTime;

/**
 * 배우의 날짜별 기본 일정 한 줄(actor_availability)이다.
 *
 * @param kind WINDOW(그날 가능한 시간), BUSY(빼야 하는 다른 일정), OFF(종일 불가)
 * @param reasonKind OTHER_PRODUCTION, PROMOTION, PERSONAL, TRAVEL 중 하나. Agent에는 이 값만 보낸다
 * @param memo 사람이 보는 설명이다. 개인 사정이 들어갈 수 있어 Agent 응답에는 넣지 않는다
 * @param source SEED(목데이터), MANAGER(소속사 회신), MANUAL(직접 입력)
 */
public record AvailabilityEntry(long actorId, LocalDate date, String kind, LocalTime start, LocalTime end,
                                String reasonKind, String memo, String source) {
}
