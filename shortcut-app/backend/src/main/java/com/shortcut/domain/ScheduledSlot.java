package com.shortcut.domain;

import java.time.LocalDate;
import java.time.LocalTime;

/** 우리 촬영에 배정된 배우 한 명의 블록 하나다. 배우 일정 조회에서 다른 작품 일정과 나란히 보여 준다. */
public record ScheduledSlot(long actorId, LocalDate date, long shootDayId, String blockCode, LocalTime start,
                            LocalTime end, String sceneCodes) {
}
