package com.shortcut.service;

import com.shortcut.common.AfterCommit;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Approval;
import com.shortcut.domain.Proposal;
import com.shortcut.domain.TaskEvent;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.repository.UserRepository;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SupersedeService {

    public static final String SUPERSEDED = "SUPERSEDED";

    private final ProposalRepository proposals;
    private final TaskRepository tasks;
    private final UserRepository users;
    private final NotificationService notifications;
    private final SseHub hub;
    private final JsonColumns json;

    public SupersedeService(ProposalRepository proposals, TaskRepository tasks, UserRepository users,
                            NotificationService notifications, SseHub hub, JsonColumns json) {
        this.proposals = proposals;
        this.tasks = tasks;
        this.users = users;
        this.notifications = notifications;
        this.hub = hub;
        this.json = json;
    }

    /**
     * 촬영 데이터가 바뀌면 그 전 데이터로 만든 승인 대기 변경안은 확정할 수 없다.
     * 누가 승인을 누를 때까지 "승인 중"으로 남겨 두지 않고 바로 무효로 돌리고, 그 작업은 대체됨으로 닫는다.
     * Agent를 다시 깨우지 않는다. 같은 촬영일에 재계획이 두 개 동시에 돌지 않게, 새 재계획은 새 변경이 맡는다.
     *
     * @return 무효로 돌린 변경안 수
     */
    @Transactional
    public int supersedeOlder(long shootDayId, int dataVersion, String reason) {
        int count = 0;
        for (Proposal p : proposals.findByShootDay(shootDayId)) {
            if (!"PENDING".equals(p.status()) || p.dataVersion() >= dataVersion) {
                continue;
            }
            List<String> waitingRoles = proposals.findApprovals(p.id()).stream()
                    .filter(a -> "PENDING".equals(a.status()))
                    .map(Approval::role)
                    .toList();
            proposals.updateStatus(p.id(), "STALE");
            proposals.cancelPending(p.id());

            Set<String> related = new LinkedHashSet<>();
            tasks.findTask(p.taskId()).ifPresent(task -> {
                related.add(task.requestedBy());
                if ("WAITING_APPROVAL".equals(task.status())) {
                    tasks.markFinished(task.id(), SUPERSEDED, null, null, null, null);
                    TaskEvent event = tasks.insertTaskEvent(task.id(), SUPERSEDED,
                            json.write(Map.of("proposalId", p.id(), "reason", reason)));
                    AfterCommit.run(() -> hub.publishTask(event));
                }
            });
            users.findByRoles(waitingRoles).forEach(u -> related.add(u.username()));
            notifications.notifyUsernames(related, NotificationService.DECISION, "변경안 " + p.versionLabel() + " 무효",
                    "촬영 데이터가 바뀌어 더 이상 승인할 수 없습니다. 바뀐 내용: " + reason, "/proposals/" + p.id());
            count++;
        }
        return count;
    }
}
