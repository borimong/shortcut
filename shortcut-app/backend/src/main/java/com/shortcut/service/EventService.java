package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Actor;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.TaskDtos.ChangeItem;
import com.shortcut.dto.TaskDtos.EventOptions;
import com.shortcut.dto.TaskDtos.OptionActor;
import com.shortcut.dto.TaskDtos.OptionEquipment;
import com.shortcut.dto.TaskDtos.OptionLocation;
import com.shortcut.dto.TaskDtos.EventRequest;
import com.shortcut.dto.TaskDtos.EventResponse;
import com.shortcut.engine.PlanEngine;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventService {

    // 콜시트를 바꿀 수 있는 사람은 제작 PD와 연출 PD(연출감독)다. 제작 조직에서 제작 PD가 제작실장보다 위다.
    public static final Set<String> CHANGE_ROLES = Set.of("PRODUCER", "DIRECTOR");
    // 화면이 shootDayId를 보내지 않는 단일 촬영일 시연을 위해 기본값을 둔다.
    private static final long DEFAULT_SHOOT_DAY = 1L;
    // 불참 배우는 가용 시작과 끝을 같은 시각으로 저장한다. 엔진은 이 값을 "오늘 참여 불가"로 읽는다.
    private static final LocalTime ABSENT = LocalTime.MIDNIGHT;

    private final PlanRepository plans;
    private final TaskRepository tasks;
    private final OutboxService outbox;
    private final OverrideRepository overrides;
    private final PlanDataService planData;
    private final JsonColumns json;

    public EventService(PlanRepository plans, TaskRepository tasks, OutboxService outbox, OverrideRepository overrides,
                        PlanDataService planData, JsonColumns json) {
        this.plans = plans;
        this.tasks = tasks;
        this.outbox = outbox;
        this.overrides = overrides;
        this.planData = planData;
        this.json = json;
    }

    /**
     * 이벤트, 구조화된 변경 반영, 작업, outbox 메시지를 한 트랜잭션에 쓴다.
     * 셋 중 하나만 남으면 화면에는 작업이 있는데 Agent는 모르는 상태가 되기 때문이다.
     * 구조화된 변경(장비 고장, 배우 불참 등)이 있으면 촬영 데이터 버전을 올려서, 승인 중인 이전 변경안이 무효가 되게 한다.
     */
    @Transactional
    public EventResponse create(CurrentUser user, EventRequest request) {
        if (!CHANGE_ROLES.contains(user.role())) {
            throw ApiException.forbidden("변경 입력은 제작 PD와 연출 PD만 할 수 있습니다.");
        }
        long shootDayId = request.shootDayId() == null ? DEFAULT_SHOOT_DAY : request.shootDayId();
        ShootDay shootDay = plans.findShootDay(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        List<ChangeItem> changes = request.changes() == null ? List.of() : request.changes();
        PlanData data = planData.load(shootDayId);
        List<Map<String, Object>> applied = new ArrayList<>();
        for (ChangeItem change : changes) {
            applied.add(validate(change, data));
        }

        String detail = request.detail().strip();
        String dedupKey = shootDayId + "|" + request.type() + "|" + detail + "|" + json.write(applied) + "|"
                + shootDay.dataVersion();
        Optional<Long> inserted = tasks.insertEventIfAbsent(shootDayId, request.type(), detail,
                blankToNull(request.instruction()), shootDay.dataVersion(), dedupKey, user.username());
        if (inserted.isEmpty()) {
            long eventId = tasks.findEventByDedupKey(dedupKey).orElseThrow().id();
            AiTask existing = tasks.findTaskByEvent(eventId).orElseThrow();
            return new EventResponse(eventId, existing.id(), true);
        }
        long eventId = inserted.get();
        if (!applied.isEmpty()) {
            for (Map<String, Object> change : applied) {
                apply(shootDayId, eventId, change);
            }
            tasks.updateEventChanges(eventId, json.write(applied));
            plans.bumpDataVersion(shootDayId);
        }
        long taskId = tasks.insertTask("REPLAN", null, eventId, null, shootDayId, user.username(),
                UUID.randomUUID().toString(), "event-");
        outbox.agentStart(tasks.findTask(taskId).orElseThrow());
        return new EventResponse(eventId, taskId, null);
    }

    @Transactional(readOnly = true)
    public EventOptions options(Long shootDayId) {
        PlanData data = planData.load(shootDayId == null ? DEFAULT_SHOOT_DAY : shootDayId);
        List<OptionLocation> locations = data.locations().values().stream()
                .filter(l -> l.id() < 100)
                .map(l -> new OptionLocation(l.id(), l.name(), l.region(), l.indoor(), l.available()))
                .toList();
        return new EventOptions(data.current().locationId(), locations,
                data.equipment().values().stream().map(e -> new OptionEquipment(e.id(), e.name(), e.available())).toList(),
                data.actors().values().stream()
                        .map(a -> new OptionActor(a.id(), a.name(), a.availableFrom(), a.availableTo())).toList(),
                locations.stream().map(OptionLocation::region).distinct().toList());
    }

    /**
     * 변경 한 건을 검사하고, 저장할 값과 Agent에게 보낼 한 줄 요약을 만든다.
     */
    private Map<String, Object> validate(ChangeItem c, PlanData data) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("kind", c.kind());
        switch (c.kind()) {
            case "EQUIPMENT_UNAVAILABLE" -> {
                Equipment item = require(data.equipment(), c.targetId(), "장비");
                out.put("targetId", item.id());
                out.put("summary", item.name() + " 사용 불가(고장)");
            }
            case "ACTOR_ABSENT" -> {
                Actor actor = require(data.actors(), c.targetId(), "배우");
                out.put("targetId", actor.id());
                out.put("summary", actor.name() + " 오늘 촬영 불참");
            }
            case "ACTOR_WINDOW" -> {
                Actor actor = require(data.actors(), c.targetId(), "배우");
                if (c.from() == null || c.to() == null || !c.from().isBefore(c.to())) {
                    throw ApiException.badRequest("INVALID_TIME", "배우 가용 시작 시각은 끝 시각보다 빨라야 합니다.");
                }
                out.put("targetId", actor.id());
                out.put("from", c.from().toString());
                out.put("to", c.to().toString());
                out.put("summary", actor.name() + " 가용 시간 " + c.from() + "~" + c.to() + "로 변경");
            }
            case "LOCATION_UNAVAILABLE" -> {
                Location location = require(data.locations(), c.targetId(), "장소");
                out.put("targetId", location.id());
                out.put("summary", location.name() + " 사용 불가(취소)");
            }
            case "RAIN_FORECAST" -> {
                Location location = require(data.locations(), c.targetId(), "장소");
                if (c.fromHour() == null || c.toHour() == null || c.fromHour() < 0 || c.toHour() > 23
                        || c.fromHour() > c.toHour()) {
                    throw ApiException.badRequest("INVALID_TIME", "비 시작과 끝 시각은 0~23시 사이에서 시작이 끝보다 늦을 수 없습니다.");
                }
                if (c.mm() == null || c.mm() < 0 || c.mm() > 300) {
                    throw ApiException.badRequest("INVALID_PRECIP", "시간당 강수량은 0~300mm 사이로 입력합니다.");
                }
                out.put("targetId", location.id());
                out.put("fromHour", c.fromHour());
                out.put("toHour", c.toHour());
                out.put("mm", c.mm());
                out.put("summary", location.name() + " " + c.fromHour() + "~" + c.toHour() + "시 시간당 "
                        + PlanEngine.mm(c.mm()) + "mm 비");
            }
            case "DISASTER_ALERT" -> {
                if (isBlank(c.region()) || isBlank(c.alertKind())) {
                    throw ApiException.badRequest("ALERT_REQUIRED", "재난 문자 지역과 종류를 입력합니다.");
                }
                if (c.from() == null || c.to() == null || !c.from().isBefore(c.to())) {
                    throw ApiException.badRequest("INVALID_TIME", "재난 문자 시작 시각은 끝 시각보다 빨라야 합니다.");
                }
                out.put("region", c.region().strip());
                out.put("alertKind", c.alertKind().strip());
                out.put("from", c.from().toString());
                out.put("to", c.to().toString());
                out.put("summary", c.region().strip() + " " + c.alertKind().strip() + " " + c.from() + "~" + c.to());
            }
            default -> throw ApiException.badRequest("UNKNOWN_CHANGE", "알 수 없는 변경 종류입니다: " + c.kind());
        }
        return out;
    }

    private void apply(long shootDayId, long eventId, Map<String, Object> c) {
        String kind = (String) c.get("kind");
        Long target = c.get("targetId") == null ? null : ((Number) c.get("targetId")).longValue();
        switch (kind) {
            case "EQUIPMENT_UNAVAILABLE", "LOCATION_UNAVAILABLE" -> overrides.insert(shootDayId, eventId, kind, target, Map.of());
            case "ACTOR_ABSENT" -> overrides.insert(shootDayId, eventId, "ACTOR_WINDOW", target,
                    Map.of("from", ABSENT.toString(), "to", ABSENT.toString()));
            case "ACTOR_WINDOW" -> overrides.insert(shootDayId, eventId, kind, target,
                    Map.of("from", c.get("from"), "to", c.get("to")));
            case "RAIN_FORECAST" -> overrides.insert(shootDayId, eventId, kind, target,
                    Map.of("fromHour", c.get("fromHour"), "toHour", c.get("toHour"), "mm", c.get("mm")));
            case "DISASTER_ALERT" -> plans.insertAlert((String) c.get("region"), (String) c.get("alertKind"),
                    LocalTime.parse((String) c.get("from")), LocalTime.parse((String) c.get("to")),
                    c.get("region") + " " + c.get("alertKind"));
            default -> throw new IllegalStateException(kind);
        }
    }

    private static <T> T require(Map<Long, T> rows, Long id, String label) {
        T row = id == null ? null : rows.get(id);
        if (row == null) {
            throw ApiException.badRequest("UNKNOWN_TARGET", "없는 " + label + "입니다: " + id);
        }
        return row;
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.strip();
    }
}
