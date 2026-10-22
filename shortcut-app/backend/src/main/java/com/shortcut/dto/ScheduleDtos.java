package com.shortcut.dto;

import com.shortcut.engine.Finding;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;

/** 배우 날짜별 일정과 대본 씬 배정 가능성 응답이다. */
public final class ScheduleDtos {

    private ScheduleDtos() {
    }

    /** 일정이 없는 날은 빠진다. 그런 날은 계약 기본 시간(contractFrom~contractTo)에 촬영할 수 있다. */
    public record ActorScheduleResponse(LocalDate from, LocalDate to, List<ActorScheduleView> actors) {
    }

    public record ActorScheduleView(long id, String name, LocalTime contractFrom, LocalTime contractTo, boolean noNight,
                                    List<ActorDayView> days) {
    }

    /**
     * shoots는 우리 촬영에 배정된 블록이다. 촬영일에는 변경 입력(불참, 가용 시간, 다른 일정)까지 얹은 값을 보여 준다.
     */
    public record ActorDayView(LocalDate date, boolean off, String offReason, String offMemo, List<WindowView> windows,
                               List<BusyView> busy, List<ShootView> shoots) {
    }

    public record WindowView(LocalTime from, LocalTime to) {
    }

    /** memo는 사람 화면에만 채운다. Agent가 받는 내부 응답에서는 개인 사정을 옮기지 않으려고 비운다. */
    public record BusyView(LocalTime from, LocalTime to, String reasonKind, String memo) {
    }

    public record ShootView(long shootDayId, String blockCode, LocalTime start, LocalTime end, String scenes) {
    }

    /** 오후 블록(재계획 대상) 현재 확정안을 엔진으로 다시 검사한 결과다. 촬영판 점검 배지에 쓴다. */
    public record PlanCheckResponse(long shootDayId, int dataVersion, List<Finding> violations, List<Finding> warnings) {
    }

    public record PlaceabilityResponse(LocalDate from, LocalDate to, List<PlaceabilityView> scenes) {
    }

    public record PlaceabilityView(String code, String heading, List<Long> actorIds, int minutes, boolean placeable,
                                   LocalDate firstDate, String reason) {
    }
}
