package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.common.ApiException;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Approval;
import com.shortcut.domain.Callsheet;
import com.shortcut.domain.Location;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.ProposalDtos.ApprovalRequest;
import com.shortcut.dto.ProposalDtos.ApprovalResult;
import com.shortcut.dto.ProposalDtos.CommitResult;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.repository.UserRepository;
import com.shortcut.security.CurrentUser;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 승인, 거절, 무효(STALE), 확정 흐름의 현재 동작을 고정한다.
 * 판정 순서(존재, 상태, 역할, 사유, 데이터 최신성)와 부수 효과(상태 변경, Agent 재개)를 본다.
 */
class ProposalServiceTest {

    private static final long TASK_ID = 7L;
    private static final long PROPOSAL_ID = 11L;
    private static final int DATA_VERSION = 5;
    private static final PlanSnapshot ORIGINAL = new PlanSnapshot(1, List.of(1L, 2L, 3L), LocalTime.of(13, 0), LocalTime.of(15, 0), 300_000);
    private static final PlanSnapshot PROPOSED = new PlanSnapshot(2, List.of(1L, 2L, 3L), LocalTime.of(14, 0), LocalTime.of(16, 0), 450_000);
    private static final CurrentUser SOUND = new CurrentUser("sound", "SOUND", "배수아", "TECH");
    private static final CurrentUser DIRECTOR = new CurrentUser("director", "DIRECTOR", "강민재", "DIRECTING");
    private static final CurrentUser CREW = new CurrentUser("crew", "CREW", "임채원", "DIRECTING");

    private final ProposalRepository proposals = mock(ProposalRepository.class);
    private final TaskRepository tasks = mock(TaskRepository.class);
    private final PlanRepository plans = mock(PlanRepository.class);
    private final CallsheetRepository callsheets = mock(CallsheetRepository.class);
    private final UserRepository users = mock(UserRepository.class);
    private final PlanDataService planData = mock(PlanDataService.class);
    private final OutboxService outbox = mock(OutboxService.class);
    private final AiTask task = mock(AiTask.class);
    private ProposalService service;

    @BeforeEach
    void setUp() {
        service = new ProposalService(proposals, tasks, plans, callsheets, users, planData, mock(PlanService.class),
                mock(NotificationService.class), outbox, mock(SseHub.class), new ObjectMapper(), mock(SettingsRepository.class));
        given(tasks.findTask(TASK_ID)).willReturn(Optional.of(task));
        given(task.requestedBy()).willReturn("manager");
        given(users.findByRoles(anyList())).willReturn(List.of());
        given(plans.findShootDay(1L)).willReturn(Optional.of(shootDay(DATA_VERSION)));
        given(planData.load(1L)).willReturn(data());
    }

    // ---------------------------------------------------------------- 승인·거절

    @Test
    void 다른_작업의_변경안이면_404다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));

        assertCode(() -> service.decide(SOUND, 999L, approve()), "PROPOSAL_NOT_FOUND");
    }

    @Test
    void 이미_처리된_변경안이면_409다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("REJECTED", DATA_VERSION)));

        assertCode(() -> service.decide(SOUND, TASK_ID, approve()), "PROPOSAL_NOT_PENDING");
    }

    @Test
    void 승인_대기_역할이_아니면_막고_데이터가_바뀌었어도_무효로_만들지_않는다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(plans.findShootDay(1L)).willReturn(Optional.of(shootDay(DATA_VERSION + 1)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(List.of(approval("SOUND", "PENDING")));

        assertCode(() -> service.decide(CREW, TASK_ID, approve()), "FORBIDDEN");
        assertNoSideEffects();
    }

    @Test
    void 이미_결정한_역할은_다시_결정할_수_없다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(List.of(approval("SOUND", "APPROVED")));

        assertCode(() -> service.decide(SOUND, TASK_ID, approve()), "FORBIDDEN");
    }

    @Test
    void 거절_입력이_부족하면_400이고_상태를_바꾸지_않는다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(List.of(approval("SOUND", "PENDING")));

        assertCode(() -> service.decide(SOUND, TASK_ID, reject(" ", List.of("LOCATION"))), "REASON_REQUIRED");
        assertCode(() -> service.decide(SOUND, TASK_ID, reject("소음", List.of("LOCATION"))), "REASON_TOO_SHORT");
        assertCode(() -> service.decide(SOUND, TASK_ID, reject("오후 공사 소음이 심합니다", List.of())), "ISSUES_REQUIRED");
        assertCode(() -> service.decide(SOUND, TASK_ID, reject("오후 공사 소음이 심합니다", null)), "ISSUES_REQUIRED");
        assertNoSideEffects();
    }

    @Test
    void 대기_중_데이터_버전이_바뀌었으면_무효로_바꾸고_Agent를_다시_계획하게_한다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(plans.findShootDay(1L)).willReturn(Optional.of(shootDay(DATA_VERSION + 1)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(List.of(approval("SOUND", "PENDING")));

        ApprovalResult result = service.decide(SOUND, TASK_ID, approve());

        assertThat(result.status()).isEqualTo("STALE");
        verify(proposals).updateStatus(PROPOSAL_ID, "STALE");
        verify(proposals).cancelPending(PROPOSAL_ID);
        verify(outbox).agentResume(task, PROPOSAL_ID, new OutboxService.Resume("STALE", null, null, List.of()));
        verify(proposals, never()).decide(anyLong(), anyString(), anyString(), anyString(), anyString(), any(), anyList());
    }

    @Test
    void 거절하면_사유와_문제_요소를_중복_없이_Agent에_넘긴다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(List.of(approval("DIRECTOR", "APPROVED"), approval("SOUND", "PENDING")));
        String reason = "  성수 스튜디오 오후 공사 소음, 동시녹음 불가  ";

        ApprovalResult result = service.decide(SOUND, TASK_ID, reject(reason, List.of("LOCATION", "TIME", "LOCATION")));

        assertThat(result.status()).isEqualTo("REJECTED");
        List<String> issues = List.of("LOCATION", "TIME");
        verify(proposals).decide(PROPOSAL_ID, "SOUND", "REJECTED", "sound", "배수아", reason.strip(), issues);
        verify(proposals).updateStatus(PROPOSAL_ID, "REJECTED");
        verify(proposals).cancelPending(PROPOSAL_ID);
        verify(outbox).agentResume(task, PROPOSAL_ID, new OutboxService.Resume("REJECTED", "SOUND", reason.strip(), issues));
    }

    @Test
    void 일부만_승인되면_대기를_유지하고_Agent를_깨우지_않는다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(
                List.of(approval("DIRECTOR", "PENDING"), approval("SOUND", "PENDING")),
                List.of(approval("DIRECTOR", "APPROVED"), approval("SOUND", "PENDING")));

        ApprovalResult result = service.decide(DIRECTOR, TASK_ID, approve());

        assertThat(result.status()).isEqualTo("PENDING");
        verify(proposals).decide(PROPOSAL_ID, "DIRECTOR", "APPROVED", "director", "강민재", null, List.of());
        verify(proposals, never()).updateStatus(anyLong(), anyString());
        verify(outbox, never()).agentResume(any(), anyLong(), any());
    }

    @Test
    void 마지막_필수_승인자가_승인하면_전원_승인으로_Agent를_재개한다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));
        given(proposals.findApprovals(PROPOSAL_ID)).willReturn(
                List.of(approval("DIRECTOR", "APPROVED"), approval("SOUND", "PENDING")),
                List.of(approval("DIRECTOR", "APPROVED"), approval("SOUND", "APPROVED")));

        ApprovalResult result = service.decide(SOUND, TASK_ID, approve());

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(proposals).updateStatus(PROPOSAL_ID, "APPROVED");
        verify(outbox).agentResume(task, PROPOSAL_ID, new OutboxService.Resume("APPROVED", null, null, List.of()));
    }

    // ---------------------------------------------------------------- 확정

    @Test
    void 전원_승인되지_않은_변경안은_확정할_수_없다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("PENDING", DATA_VERSION)));

        assertCode(() -> service.commit(PROPOSAL_ID, DATA_VERSION), "NOT_APPROVED");
    }

    @Test
    void 확정_직전_데이터_버전이_다르면_409이고_촬영판을_바꾸지_않는다() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("APPROVED", DATA_VERSION)));
        given(plans.lockDataVersion(1L)).willReturn(Optional.of(DATA_VERSION + 1));

        assertCode(() -> service.commit(PROPOSAL_ID, DATA_VERSION), "VERSION_CONFLICT");
        verify(plans, never()).updateBlock(anyLong(), anyString(), any());
        verify(plans, never()).bumpDataVersion(anyLong());
    }

    @Test
    void 가예약이_있는_장소로_확정하면_예약을_그대로_쓰고_변경안_번호로_콜시트를_만든다() {
        givenApprovedForCommit();
        given(callsheets.hasHeldReservation(1L, 2L)).willReturn(true);

        CommitResult result = service.commit(PROPOSAL_ID, DATA_VERSION);

        assertThat(result.callsheetVersionNo()).isEqualTo(4);
        assertThat(result.reservationStatus()).isEqualTo("HELD");
        verify(plans).updateBlock(1L, PlanData.CHANGING_BLOCK, PROPOSED);
        verify(plans).bumpDataVersion(1L);
        verify(proposals).updateStatus(PROPOSAL_ID, "COMMITTED");
        verify(callsheets, never()).insertManualReservation(anyString(), anyLong(), anyLong(), any(), any());
        verify(outbox).callsheetJob(31L, 1L, 4, "trace-1");
    }

    @Test
    void 가예약이_없는_장소로_확정하면_담당자_처리_대기_예약을_만든다() {
        givenApprovedForCommit();
        given(callsheets.hasHeldReservation(1L, 2L)).willReturn(false);

        CommitResult result = service.commit(PROPOSAL_ID, DATA_VERSION);

        assertThat(result.reservationStatus()).isEqualTo("MANUAL_PENDING");
        verify(callsheets).insertManualReservation("M-" + PROPOSAL_ID, 1L, 2L, LocalTime.of(14, 0), LocalTime.of(16, 0));
    }

    // ---------------------------------------------------------------- 도우미

    private void givenApprovedForCommit() {
        given(proposals.findForUpdate(PROPOSAL_ID)).willReturn(Optional.of(proposal("APPROVED", DATA_VERSION)));
        given(plans.lockDataVersion(1L)).willReturn(Optional.of(DATA_VERSION));
        given(callsheets.insert(1L, 4, PROPOSAL_ID, PROPOSED)).willReturn(new Callsheet(31L, 1L, 4, PROPOSAL_ID, PROPOSED, null));
        given(task.traceId()).willReturn("trace-1");
    }

    private void assertNoSideEffects() {
        verify(proposals, never()).updateStatus(anyLong(), anyString());
        verify(proposals, never()).cancelPending(anyLong());
        verify(proposals, never()).decide(anyLong(), anyString(), anyString(), anyString(), anyString(), any(), anyList());
        verify(outbox, never()).agentResume(any(), anyLong(), any());
    }

    private static void assertCode(Runnable call, String code) {
        assertThatThrownBy(call::run)
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).code()).isEqualTo(code);
    }

    private static ApprovalRequest approve() {
        return new ApprovalRequest(PROPOSAL_ID, "APPROVE", null, null);
    }

    private static ApprovalRequest reject(String reason, List<String> issues) {
        return new ApprovalRequest(PROPOSAL_ID, "REJECT", reason, issues);
    }

    private static Proposal proposal(String status, int dataVersion) {
        return new Proposal(PROPOSAL_ID, TASK_ID, 3L, 1L, 1, 4, status, dataVersion, ORIGINAL, PROPOSED, null, 0.8,
                null, null, null, null, null, null, null, null, null);
    }

    private static Approval approval(String role, String status) {
        return new Approval(1L, PROPOSAL_ID, 1, role, status, null, null, null, List.of(), null);
    }

    private static ShootDay shootDay(int dataVersion) {
        return new ShootDay(1, 1, "드라마", LocalDate.of(2026, 10, 22), LocalTime.of(6, 30), dataVersion, null, "[]",
                1_000_000, 0);
    }

    private static PlanData data() {
        Location seongsu = new Location(2, "성수 스튜디오", "서울 성동구", true, "서울 성동구", LocalTime.of(9, 0),
                LocalTime.of(22, 0), null, null, 450_000, false, 0.8, 14, null, true);
        return new PlanData(shootDay(DATA_VERSION), List.of(), List.of(), Map.of(), Map.of(2L, seongsu), Map.of(),
                List.of(), List.of(), List.of(), List.of(), null);
    }
}
