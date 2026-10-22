package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
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
import com.shortcut.domain.Approval;
import com.shortcut.domain.Callsheet;
import com.shortcut.domain.Location;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.TaskEvent;
import com.shortcut.engine.CheckResult;
import com.shortcut.engine.Finding;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.repository.UserRepository;
import com.shortcut.security.CurrentUser;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 재계획 중단(변경안 철회)과 확정 콜시트 되돌리기를 DB 없이 확인한다. */
class CancelAndRestoreTest {

    private static final CurrentUser PD = new CurrentUser("pd", "PRODUCER", "한서윤", "제작부");
    private static final CurrentUser SOUND = new CurrentUser("sound", "SOUND", "서도현", "동시녹음팀");

    private final TaskRepository tasks = mock(TaskRepository.class);
    private final ProposalRepository proposals = mock(ProposalRepository.class);
    private final UserRepository users = mock(UserRepository.class);
    private final NotificationService notifications = mock(NotificationService.class);
    private final CancelService cancels = new CancelService(tasks, proposals, users, notifications, mock(SseHub.class),
            new JsonColumns(new ObjectMapper()));

    @Test
    void 승인_대기_중에_중단하면_변경안을_철회하고_작업을_닫는다() {
        given(tasks.findTask(7L)).willReturn(Optional.of(task("WAITING_APPROVAL", 40L)));
        given(proposals.find(40L)).willReturn(Optional.of(proposal(40L, "PENDING")));
        given(proposals.findApprovals(40L)).willReturn(List.of(new Approval(1, 40, 1, "SOUND", "PENDING", null, null,
                null, List.of(), null)));
        given(tasks.insertTaskEvent(anyLong(), anyString(), anyString()))
                .willReturn(new TaskEvent(1, 7, "CANCELLED", null, OffsetDateTime.now()));

        var result = cancels.cancel(PD, 7, "배우 일정이 다시 바뀌어 직접 정리함");

        assertThat(result.proposalId()).isEqualTo(40L);
        verify(proposals).updateStatus(40L, "WITHDRAWN");
        verify(proposals).cancelPending(40L);
        verify(tasks).markFinished(eq(7L), eq("CANCELLED"), eq("한서윤 중단: 배우 일정이 다시 바뀌어 직접 정리함"), any(), any(), any());
        verify(tasks).insertTaskEvent(eq(7L), eq("CANCELLED"), anyString());
    }

    @Test
    void 끝난_작업이나_권한_없는_사람은_중단할_수_없다() {
        given(tasks.findTask(7L)).willReturn(Optional.of(task("DONE", null)));
        assertThatThrownBy(() -> cancels.cancel(PD, 7, null))
                .isInstanceOf(ApiException.class).hasMessageContaining("이미 끝난 작업");

        given(tasks.findTask(8L)).willReturn(Optional.of(task("RUNNING", null)));
        assertThatThrownBy(() -> cancels.cancel(SOUND, 8, null))
                .isInstanceOf(ApiException.class).hasMessageContaining("제작 PD, 연출감독, 요청한 사람");
        verify(tasks, never()).markFinished(eq(8L), anyString(), any(), any(), any(), any());
    }

    // ---------------------------------------------------------------- 콜시트 되돌리기

    private final PlanRepository plans = mock(PlanRepository.class);
    private final CallsheetRepository callsheets = mock(CallsheetRepository.class);
    private final PlanDataService planData = mock(PlanDataService.class);
    private final PlanService planService = mock(PlanService.class);
    private final SupersedeService supersede = mock(SupersedeService.class);
    private final OutboxService outbox = mock(OutboxService.class);
    private final CallsheetService restores = new CallsheetService(plans, callsheets, proposals, planData, planService,
            supersede, outbox, notifications);

    private static final PlanSnapshot HANGANG = new PlanSnapshot(1, List.of(1L, 2L, 3L), t("13:00"), t("15:00"), 300000);
    private static final PlanSnapshot SEONGSU = new PlanSnapshot(2, List.of(1L, 2L, 3L), t("14:00"), t("16:00"), 450000);

    @Test
    void 앞_버전으로_되돌리면_오후_블록을_복구하고_새_버전으로_배포한다() {
        given(plans.lockDataVersion(1L)).willReturn(Optional.of(5));
        given(callsheets.find(1L, 1)).willReturn(Optional.of(callsheet(1, 1, HANGANG)));
        given(callsheets.findLatest(1L)).willReturn(Optional.of(callsheet(2, 4, SEONGSU)));
        PlanData data = mock(PlanData.class);
        given(planData.load(1L)).willReturn(data);
        given(data.snapshot(1L, HANGANG.equipmentIds(), HANGANG.start(), HANGANG.end(), List.of())).willReturn(HANGANG);
        given(data.locations()).willReturn(Map.of(1L, new Location(1, "한강 공원", "", false, "서울 영등포구",
                t("06:00"), t("22:00"), t("09:00"), t("17:00"), 300000, false, 0.95, 6, null, true)));
        given(planService.check(eq(data), eq(1L), any(), any(), any(), any(), any()))
                .willReturn(new CheckResult(List.of(), List.of(), List.of(), false));
        given(plans.bumpDataVersion(1L)).willReturn(6);
        given(proposals.nextVersionNo(1L)).willReturn(5);
        given(callsheets.insertRestored(1L, 5, HANGANG, 1, "비가 그쳐 원래 안으로", "pd"))
                .willReturn(callsheet(30, 5, HANGANG));
        given(callsheets.hasHeldReservation(1L, 1L)).willReturn(false);

        var result = restores.restore(PD, 1, 1, "비가 그쳐 원래 안으로");

        assertThat(result.versionNo()).isEqualTo(5);
        assertThat(result.reservationStatus()).isEqualTo("MANUAL_PENDING");
        verify(plans).updateBlock(1L, "PM", HANGANG);
        verify(supersede).supersedeOlder(1L, 6, "콜시트 v1으로 되돌림");
        verify(outbox).callsheetJob(eq(30L), eq(1L), eq(5), anyString());
    }

    @Test
    void 지금_콜시트이거나_지금_데이터로_위반이면_되돌리지_않는다() {
        given(plans.lockDataVersion(1L)).willReturn(Optional.of(5));
        given(callsheets.find(1L, 4)).willReturn(Optional.of(callsheet(2, 4, SEONGSU)));
        given(callsheets.findLatest(1L)).willReturn(Optional.of(callsheet(2, 4, SEONGSU)));
        assertThatThrownBy(() -> restores.restore(PD, 1, 4, null)).hasMessageContaining("지금 콜시트가 v4");

        given(callsheets.find(1L, 1)).willReturn(Optional.of(callsheet(1, 1, HANGANG)));
        PlanData data = mock(PlanData.class);
        given(planData.load(1L)).willReturn(data);
        given(planService.check(eq(data), eq(1L), any(), any(), any(), any(), any())).willReturn(new CheckResult(
                List.of(new Finding("RAIN_HARD", "WEATHER", "한강 공원 시간대 최대 강수량 시간당 8mm", "WEATHER_RAIN")), List.of(),
                List.of(), false));
        assertThatThrownBy(() -> restores.restore(PD, 1, 1, null)).hasMessageContaining("8mm");
        verify(plans, never()).updateBlock(anyLong(), anyString(), any());

        assertThatThrownBy(() -> restores.restore(SOUND, 1, 1, null)).hasMessageContaining("제작 PD와 연출감독");
        verify(callsheets, never()).insertRestored(anyLong(), anyInt(), any(), anyInt(), any(), any());
    }

    private static AiTask task(String status, Long proposalId) {
        return new AiTask(7, "REPLAN", status, null, null, null, 3L, proposalId, null, "event-3", "trace", 1, "pd",
                OffsetDateTime.now(), OffsetDateTime.now());
    }

    private static Proposal proposal(long id, String status) {
        return new Proposal(id, 7, 3L, 1, 1, 4, status, 5, HANGANG, SEONGSU, null, 0.79, null, null, null, null, null,
                null, null, OffsetDateTime.now(), OffsetDateTime.now());
    }

    private static Callsheet callsheet(long id, int versionNo, PlanSnapshot pm) {
        return new Callsheet(id, 1, versionNo, null, pm, OffsetDateTime.now(), null, null, null);
    }

    private static LocalTime t(String value) {
        return LocalTime.parse(value);
    }
}
