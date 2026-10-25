package com.shortcut.domain;

import java.time.OffsetDateTime;

/**
 * 관리자가 바꾸는 운영 설정이다.
 *
 * @param maxLoops 변경 안건 하나에 재계획 루프를 최대 몇 번 돌지
 * @param rainBlockMm 야외 촬영을 막는 시간당 강수량(mm). 엔진 하드 제약과 우천 알림이 같은 값을 쓴다
 * @param rainWarnMm 우천 대비 경고를 남기는 시간당 강수량(mm)
 * @param rainAlertLeadHours 비 때문에 촬영이 어려운 시각보다 몇 시간 전에 알릴지
 * @param mockVenueConflict 켜면 가상 아워플레이스의 가예약이 실패한다(실행팀 실패 대응 시연용)
 * @param mockPermitDenied 켜면 가상 허가 기관이 촬영 허가를 반려한다(실행팀 실패 대응 시연용)
 */
public record AppSettings(int maxLoops, double rainBlockMm, double rainWarnMm, int rainAlertLeadHours,
                          boolean mockVenueConflict, boolean mockPermitDenied,
                          String updatedBy, OffsetDateTime updatedAt) {

    public static final AppSettings DEFAULT = new AppSettings(5, 5.0, 1.0, 3, false, false, null, null);
}
