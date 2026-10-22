package com.shortcut.domain;

import java.util.Set;

/**
 * Agent 작업(ai_tasks.status)의 상태 값이다. DB에 이 문자열 그대로 저장한다.
 * SQL 안의 상태 값은 저장소 클래스에 그대로 적혀 있으므로, 값을 바꿀 때는 저장소도 함께 고친다.
 */
public final class TaskStatus {

    public static final String QUEUED = "QUEUED";
    public static final String RUNNING = "RUNNING";
    public static final String WAITING_APPROVAL = "WAITING_APPROVAL";
    public static final String DONE = "DONE";
    public static final String FAILED = "FAILED";
    public static final String NEEDS_HUMAN = "NEEDS_HUMAN";
    /** 승인을 기다리던 중 촬영 데이터가 바뀌어 다른 변경으로 대체된 작업이다(SupersedeService). */
    public static final String SUPERSEDED = "SUPERSEDED";

    public static final Set<String> TERMINAL = Set.of(DONE, FAILED, NEEDS_HUMAN, SUPERSEDED);

    private TaskStatus() {
    }
}
