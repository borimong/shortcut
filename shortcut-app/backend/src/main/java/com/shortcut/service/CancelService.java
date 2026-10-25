package com.shortcut.service;

import com.shortcut.common.AfterCommit;
import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Approval;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.ProposalStatus;
import com.shortcut.domain.Role;
import com.shortcut.domain.TaskEvent;
import com.shortcut.domain.TaskStatus;
import com.shortcut.dto.TaskDtos.CancelResult;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.repository.UserRepository;
import com.shortcut.security.CurrentUser;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 진행 중인 재계획을 사람이 멈춘다. 승인을 기다리던 변경안은 철회로 닫고 남은 승인 요청은 취소한다.
 * Agent는 다음 진행 이벤트를 보낼 때 409(TASK_CANCELLED)를 받고 그래프를 멈추며, 중단한 작업으로는 변경안을 올릴 수 없다.
 * 변경 입력으로 넣은 촬영 데이터(장비 고장, 배우 불참 등)는 그대로 둔다. 되돌리려면 자원 현황에서 되돌린다.
 */
@Service
public class CancelService {

    public static final String CANCELLED = TaskStatus.CANCELLED;
    public static final String WITHDRAWN = ProposalStatus.WITHDRAWN;

    private final TaskRepository tasks;
    private final ProposalRepository proposals;
    private final UserRepository users;
    private final NotificationService notifications;
    private final SseHub hub;
    private final JsonColumns json;

    public CancelService(TaskRepository tasks, ProposalRepository proposals, UserRepository users,
                         NotificationService notifications, SseHub hub, JsonColumns json) {
        this.tasks = tasks;
        this.proposals = proposals;
        this.users = users;
        this.notifications = notifications;
        this.hub = hub;
        this.json = json;
    }

    /**
     * 제작 PD, 연출감독, 재계획을 요청한 사람만 멈출 수 있다. 이미 끝난 작업이나 질문 작업은 멈출 것이 없다.
     */
    @Transactional
    public CancelResult cancel(CurrentUser user, long taskId, String reason) {
        AiTask task = tasks.findTask(taskId)
                .orElseThrow(() -> ApiException.notFound("TASK_NOT_FOUND", "작업이 없습니다: " + taskId));
        if (!Role.CHANGERS.contains(user.role()) && !user.username().equals(task.requestedBy())) {
            throw ApiException.forbidden("재계획 중단은 제작 PD, 연출감독, 요청한 사람만 할 수 있습니다.");
        }
        if (!"REPLAN".equals(task.kind())) {
            throw ApiException.badRequest("NOT_REPLAN", "재계획 작업만 중단할 수 있습니다.");
        }
        if (task.finished()) {
            throw ApiException.conflict("TASK_FINISHED", "이미 끝난 작업입니다: " + task.status());
        }
        String why = reason == null || reason.isBlank() ? "사유 없음" : reason.strip();

        Set<String> related = new LinkedHashSet<>();
        related.add(task.requestedBy());
        Proposal withdrawn = null;
        if (task.proposalId() != null) {
            Proposal p = proposals.find(task.proposalId()).orElse(null);
            // 전원 승인됐어도 확정 전이면 철회할 수 있다. 확정은 승인 완료 상태만 받으므로 철회한 안은 확정되지 않는다.
            if (p != null && ("PENDING".equals(p.status()) || "APPROVED".equals(p.status()))) {
                List<String> roles = proposals.findApprovals(p.id()).stream().map(Approval::role).toList();
                proposals.updateStatus(p.id(), WITHDRAWN);
                proposals.cancelPending(p.id());
                users.findByRoles(roles).forEach(u -> related.add(u.username()));
                withdrawn = p;
            }
        }
        tasks.markFinished(taskId, CANCELLED, user.name() + " 중단: " + why, null, null, null);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("reason", why);
        payload.put("by", user.name());
        if (withdrawn != null) {
            payload.put("proposalId", withdrawn.id());
        }
        TaskEvent event = tasks.insertTaskEvent(taskId, CANCELLED, json.write(payload));
        AfterCommit.run(() -> hub.publishTask(event));

        String title = withdrawn == null ? "재계획 중단" : "변경안 " + withdrawn.versionLabel() + " 철회";
        notifications.notifyUsernames(related, NotificationService.DECISION, title, user.name() + ": " + why,
                withdrawn == null ? "/tasks/" + taskId : "/proposals/" + withdrawn.id());
        return new CancelResult(taskId, withdrawn == null ? null : withdrawn.id(), CANCELLED);
    }
}
