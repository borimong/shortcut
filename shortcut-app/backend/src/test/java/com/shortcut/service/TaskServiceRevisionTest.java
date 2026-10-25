package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.TaskEvent;
import com.shortcut.dto.TaskDtos.RevisionAccepted;
import com.shortcut.dto.TaskDtos.RevisionRequest;
import com.shortcut.dto.TaskDtos.TaskEventRequest;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/**
 * 생각 기록 수정 요청의 상태 조건(계획은 승인 대기, 실행은 완료 뒤)과 부수 효과, 새 이벤트 종류를 고정한다.
 */
class TaskServiceRevisionTest {

    private static final long TASK_ID = 7L;
    private static final long PROPOSAL_ID = 11L;
    private static final CurrentUser DIRECTOR = new CurrentUser("director", "DIRECTOR", "강민재", "DIRECTING");
    private static final String PLAN_THOUGHT =
            "{\"step\":12,\"node\":\"compose_plan\",\"agent\":\"planner\",\"phase\":\"plan\",\"revisable\":true}";
    private static final String EXEC_THOUGHT =
            "{\"step\":30,\"node\":\"venue_agent\",\"agent\":\"venue\",\"phase\":\"exec\",\"revisable\":true}";

    private final TaskRepository tasks = mock(TaskRepository.class);
    private final ProposalRepository proposals = mock(ProposalRepository.class);
    private final OutboxService outbox = mock(OutboxService.class);
    private final ObjectMapper mapper = new ObjectMapper();
    private TaskService service;

    @BeforeEach
    void setUp() {
        service = new TaskService(tasks, proposals, mock(PlanDataService.class), outbox, mock(SseHub.class),
                new JsonColumns(mapper), mock(SettingsRepository.class));
        given(tasks.insertTaskEvent(anyLong(), anyString(), anyString()))
                .willAnswer(call -> new TaskEvent(99, TASK_ID, call.getArgument(1), call.getArgument(2), null));
    }

    @Test
    void 승인_대기_중_계획_생각은_받고_대기_변경안을_닫는다() {
        task("WAITING_APPROVAL");
        thought(5L, "THOUGHT", PLAN_THOUGHT);
        Proposal pending = mock(Proposal.class);
        given(pending.id()).willReturn(PROPOSAL_ID);
        given(pending.status()).willReturn("PENDING");
        given(proposals.find(PROPOSAL_ID)).willReturn(Optional.of(pending));

        RevisionAccepted accepted = service.revise(DIRECTOR, TASK_ID, new RevisionRequest(5L, "실내 장소만 고려해 주세요"));

        assertThat(accepted).isEqualTo(new RevisionAccepted(TASK_ID, "plan"));
        verify(proposals).updateStatus(PROPOSAL_ID, "CANCELLED");
        verify(proposals).cancelPending(PROPOSAL_ID);
        verify(tasks).markRevising(TASK_ID);
        ArgumentCaptor<OutboxService.Revise> revise = ArgumentCaptor.forClass(OutboxService.Revise.class);
        verify(outbox).agentRevise(any(), revise.capture());
        assertThat(revise.getValue()).isEqualTo(
                new OutboxService.Revise(5L, 12, "compose_plan", "planner", "plan", "실내 장소만 고려해 주세요"));
        verify(tasks).insertTaskEvent(eq(TASK_ID), eq("REVISION"), anyString());
    }

    @Test
    void 실행_중에는_계획_생각을_고칠_수_없다() {
        task("RUNNING");
        thought(5L, "THOUGHT", PLAN_THOUGHT);

        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(5L, "다시")), "REVISION_NOT_ALLOWED");
        verify(outbox, never()).agentRevise(any(), any());
        verify(proposals, never()).updateStatus(anyLong(), anyString());
    }

    @Test
    void 끝난_작업의_계획_생각은_409다() {
        task("DONE");
        thought(5L, "THOUGHT", PLAN_THOUGHT);

        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(5L, "다시")), "REVISION_NOT_ALLOWED");
    }

    @Test
    void 실행_생각은_완료나_사람_확인_뒤에만_받는다() {
        thought(6L, "THOUGHT", EXEC_THOUGHT);

        task("DONE");
        assertThat(service.revise(DIRECTOR, TASK_ID, new RevisionRequest(6L, "취소 수수료 없는 시간으로")).phase()).isEqualTo("exec");
        task("NEEDS_HUMAN");
        assertThatCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(6L, "다시 예약"))).doesNotThrowAnyException();
        task("WAITING_APPROVAL");
        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(6L, "다시")), "REVISION_NOT_ALLOWED");
        task("RUNNING");
        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(6L, "다시")), "REVISION_NOT_ALLOWED");
        verify(proposals, never()).updateStatus(anyLong(), anyString());
    }

    @Test
    void 생각_기록이_아니거나_수정_불가면_400이다() {
        task("WAITING_APPROVAL");
        thought(7L, "NODE", "{\"node\":\"compose_plan\"}");
        thought(8L, "THOUGHT", "{\"step\":3,\"node\":\"self_review\",\"agent\":\"planner\",\"phase\":\"plan\",\"revisable\":false}");

        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(7L, "다시")), "REVISION_TARGET_INVALID");
        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(8L, "다시")), "REVISION_TARGET_INVALID");
        assertCode(() -> service.revise(DIRECTOR, TASK_ID, new RevisionRequest(404L, "다시")), "REVISION_TARGET_INVALID");
    }

    @Test
    void 새_이벤트_종류를_받는다() throws Exception {
        task("RUNNING");
        for (String type : new String[] {"AGENT", "THOUGHT", "REVISION"}) {
            service.appendEvent(TASK_ID, new TaskEventRequest(type, mapper.readTree("{\"agent\":\"venue\"}")));
        }
        verify(tasks).insertTaskEvent(eq(TASK_ID), eq("AGENT"), anyString());
        verify(tasks).insertTaskEvent(eq(TASK_ID), eq("THOUGHT"), anyString());
        assertCode(() -> service.appendEvent(TASK_ID, new TaskEventRequest("SOMETHING", null)), "UNKNOWN_EVENT_TYPE");
    }

    private void task(String status) {
        AiTask task = new AiTask(TASK_ID, "REPLAN", status, null, null, null, 3L, PROPOSAL_ID, null, "thread-3",
                "trace", 1L, "manager", null, null);
        given(tasks.findTask(TASK_ID)).willReturn(Optional.of(task));
    }

    private void thought(long eventId, String type, String payload) {
        given(tasks.findTaskEvent(TASK_ID, eventId)).willReturn(Optional.of(new TaskEvent(eventId, TASK_ID, type, payload, null)));
    }

    private static void assertCode(org.assertj.core.api.ThrowableAssert.ThrowingCallable call, String code) {
        assertThatThrownBy(call).isInstanceOf(ApiException.class).extracting("code").isEqualTo(code);
    }
}
