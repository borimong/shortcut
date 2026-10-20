package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.TaskDtos.EventRequest;
import com.shortcut.dto.TaskDtos.EventResponse;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventService {

    private static final Set<String> CHANGE_ROLES = Set.of("PRODUCTION_MANAGER", "AD1", "DIRECTOR");
    // 화면이 shootDayId를 보내지 않는 단일 촬영일 시연을 위해 기본값을 둔다.
    private static final long DEFAULT_SHOOT_DAY = 1L;

    private final PlanRepository plans;
    private final TaskRepository tasks;
    private final OutboxService outbox;

    public EventService(PlanRepository plans, TaskRepository tasks, OutboxService outbox) {
        this.plans = plans;
        this.tasks = tasks;
        this.outbox = outbox;
    }

    /**
     * 이벤트, 작업, outbox 메시지를 한 트랜잭션에 쓴다.
     * 셋 중 하나만 남으면 화면에는 작업이 있는데 Agent는 모르는 상태가 되기 때문이다.
     */
    @Transactional
    public EventResponse create(CurrentUser user, EventRequest request) {
        if (!CHANGE_ROLES.contains(user.role())) {
            throw ApiException.forbidden("변경 입력 권한이 없습니다.");
        }
        long shootDayId = request.shootDayId() == null ? DEFAULT_SHOOT_DAY : request.shootDayId();
        ShootDay shootDay = plans.findShootDay(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        String detail = request.detail().strip();
        String dedupKey = shootDayId + "|" + request.type() + "|" + detail + "|" + shootDay.dataVersion();

        Optional<Long> inserted = tasks.insertEventIfAbsent(shootDayId, request.type(), detail,
                blankToNull(request.instruction()), shootDay.dataVersion(), dedupKey, user.username());
        if (inserted.isEmpty()) {
            long eventId = tasks.findEventByDedupKey(dedupKey).orElseThrow().id();
            AiTask existing = tasks.findTaskByEvent(eventId).orElseThrow();
            return new EventResponse(eventId, existing.id(), true);
        }
        long eventId = inserted.get();
        long taskId = tasks.insertTask("REPLAN", null, eventId, null, shootDayId, user.username(),
                UUID.randomUUID().toString(), "event-");
        outbox.agentStart(tasks.findTask(taskId).orElseThrow());
        return new EventResponse(eventId, taskId, null);
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.strip();
    }
}
