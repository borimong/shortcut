package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Actor;
import com.shortcut.domain.DataOverride;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.Role;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.TaskDtos.ChangeItem;
import com.shortcut.dto.TaskDtos.EventOptions;
import com.shortcut.dto.TaskDtos.OptionActor;
import com.shortcut.dto.TaskDtos.OptionEquipment;
import com.shortcut.dto.TaskDtos.OptionLocation;
import com.shortcut.dto.TaskDtos.EventRequest;
import com.shortcut.dto.TaskDtos.EventResponse;
import com.shortcut.dto.ResourceDtos.ResourceChange;
import com.shortcut.dto.ResourceDtos.ResourceChangeRequest;
import com.shortcut.dto.ResourceDtos.ResourceChangeResult;
import com.shortcut.engine.PlanEngine;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EventService {

    // 불참 배우는 가용 시작과 끝을 같은 시각으로 저장한다. 엔진은 이 값을 "오늘 참여 불가"로 읽는다.
    private static final LocalTime ABSENT = LocalTime.MIDNIGHT;

    private final PlanRepository plans;
    private final TaskRepository tasks;
    private final OutboxService outbox;
    private final OverrideRepository overrides;
    private final PlanDataService planData;
    private final SupersedeService supersede;
    private final JsonColumns json;

    public EventService(PlanRepository plans, TaskRepository tasks, OutboxService outbox, OverrideRepository overrides,
                        PlanDataService planData, SupersedeService supersede, JsonColumns json) {
        this.plans = plans;
        this.tasks = tasks;
        this.outbox = outbox;
        this.overrides = overrides;
        this.planData = planData;
        this.supersede = supersede;
        this.json = json;
    }

    /**
     * 이벤트, 구조화된 변경 반영, 작업, outbox 메시지를 한 트랜잭션에 쓴다.
     * 셋 중 하나만 남으면 화면에는 작업이 있는데 Agent는 모르는 상태가 되기 때문이다.
     * 구조화된 변경(장비 고장, 배우 불참 등)이 있으면 촬영 데이터 버전을 올려서, 승인 중인 이전 변경안이 무효가 되게 한다.
     */
    @Transactional
    public EventResponse create(CurrentUser user, EventRequest request) {
        requireChangeRole(user, "변경 입력은 제작 PD와 연출 PD만 할 수 있습니다.");
        long shootDayId = PlanDataService.orDefault(request.shootDayId());
        ShootDay shootDay = shootDay(shootDayId);
        List<ChangeItem> changes = request.changes() == null ? List.of() : request.changes();
        PlanData data = planData.load(shootDayId);
        List<AppliedChange> applied = new ArrayList<>();
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
            for (AppliedChange change : applied) {
                apply(shootDay, eventId, change, user.username());
            }
            tasks.updateEventChanges(eventId, json.write(applied));
            int version = plans.bumpDataVersion(shootDayId);
            supersede.supersedeOlder(shootDayId, version, summaries(applied));
        }
        long taskId = startReplan(shootDayId, eventId, user.username());
        return new EventResponse(eventId, taskId, null);
    }

    /**
     * 자원 현황 패널에서 고친 상태를 저장한다. 변동 이력에 남도록 변경 이벤트를 하나 만들고,
     * 재계획은 요청한 경우에만 시작한다. 같은 자원에 이미 걸린 상태는 새 상태로 갈아 끼운다.
     */
    @Transactional
    public ResourceChangeResult applyResources(CurrentUser user, ResourceChangeRequest request) {
        requireChangeRole(user, "자원 상태는 제작 PD와 연출 PD만 바꿀 수 있습니다.");
        long shootDayId = PlanDataService.orDefault(request.shootDayId());
        ShootDay shootDay = shootDay(shootDayId);
        // 패널을 연 뒤 다른 사람이 먼저 바꿨으면 그 변경을 덮어쓰지 않도록 다시 불러오게 한다.
        if (request.dataVersion() != shootDay.dataVersion()) {
            throw versionConflict();
        }
        List<ResourceChange> changes = request.changes() == null ? List.of() : request.changes();
        Set<Long> clears = request.clears() == null ? Set.of() : new LinkedHashSet<>(request.clears());
        if (changes.isEmpty() && clears.isEmpty()) {
            throw ApiException.badRequest("NO_CHANGES", "바꿀 내용이 없습니다.");
        }

        PlanData data = planData.load(shootDayId);
        Map<Long, DataOverride> active = overrides.find(shootDayId).stream()
                .collect(Collectors.toMap(DataOverride::id, Function.identity()));
        List<AppliedChange> applied = new ArrayList<>();
        for (Long id : clears) {
            DataOverride o = active.get(id);
            if (o == null) {
                throw ApiException.badRequest("UNKNOWN_OVERRIDE", "이미 되돌렸거나 없는 상태 기록입니다: " + id);
            }
            applied.add(AppliedChange.clear(id, targetName(o, data) + " 정상으로 되돌림"));
        }
        for (ResourceChange c : changes) {
            applied.add(validateResource(c, data, shootDay.shootDate()));
        }

        // 한 데이터 버전에는 패널 저장을 한 번만 받는다. 동시에 두 번 눌러도 둘 다 반영되지 않게 하려는 키다.
        String dedupKey = shootDayId + "|RESOURCE|" + shootDay.dataVersion();
        String detail = summaries(applied);
        long eventId = tasks.insertEventIfAbsent(shootDayId, eventType(changes), detail, null, shootDay.dataVersion(),
                        dedupKey, user.username())
                .orElseThrow(EventService::versionConflict);

        for (Long id : clears) {
            overrides.clear(id, user.username());
        }
        for (AppliedChange change : applied) {
            if (change.isClear()) {
                continue;
            }
            String family = family(change.kind());
            long target = change.targetId();
            // 같은 자원에 기록이 겹치면 어느 쪽을 되돌려야 하는지 헷갈리므로 이전 기록을 먼저 되돌린다.
            active.values().stream()
                    .filter(o -> family.equals(o.kind()) && o.targetId() != null && o.targetId() == target)
                    .forEach(o -> overrides.clear(o.id(), user.username()));
            apply(shootDay, eventId, change, user.username());
        }
        tasks.updateEventChanges(eventId, json.write(applied));
        int version = plans.bumpDataVersion(shootDayId);
        int superseded = supersede.supersedeOlder(shootDayId, version, detail);

        Long taskId = request.replan() ? startReplan(shootDayId, eventId, user.username()) : null;
        return new ResourceChangeResult(eventId, taskId, version, superseded);
    }

    @Transactional(readOnly = true)
    public EventOptions options(Long shootDayId) {
        PlanData data = planData.load(PlanDataService.orDefault(shootDayId));
        List<OptionLocation> locations = data.locations().values().stream()
                .filter(l -> l.id() < PlanRepository.ALTERNATIVE_LOCATION_ID_BASE)
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
    private AppliedChange validate(ChangeItem c, PlanData data) {
        return switch (c.kind()) {
            case "EQUIPMENT_UNAVAILABLE" -> {
                Equipment item = require(data.equipment(), c.targetId(), "장비");
                yield AppliedChange.target(c.kind(), item.id(), item.name() + " 사용 불가(고장)");
            }
            case "ACTOR_ABSENT" -> {
                Actor actor = require(data.actors(), c.targetId(), "배우");
                yield AppliedChange.target(c.kind(), actor.id(), actor.name() + " 오늘 촬영 불참");
            }
            case "ACTOR_WINDOW" -> {
                Actor actor = require(data.actors(), c.targetId(), "배우");
                if (c.from() == null || c.to() == null || !c.from().isBefore(c.to())) {
                    throw ApiException.badRequest("INVALID_TIME", "배우 가용 시작 시각은 끝 시각보다 빨라야 합니다.");
                }
                yield AppliedChange.window(c.kind(), actor.id(), c.from().toString(), c.to().toString(),
                        actor.name() + " 가용 시간 " + c.from() + "~" + c.to() + "로 변경");
            }
            case "LOCATION_UNAVAILABLE" -> {
                Location location = require(data.locations(), c.targetId(), "장소");
                yield AppliedChange.target(c.kind(), location.id(), location.name() + " 사용 불가(취소)");
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
                yield AppliedChange.rain(location.id(), c.fromHour(), c.toHour(), c.mm(), location.name() + " "
                        + c.fromHour() + "~" + c.toHour() + "시 시간당 " + PlanEngine.mm(c.mm()) + "mm 비");
            }
            case "DISASTER_ALERT" -> {
                if (isBlank(c.region()) || isBlank(c.alertKind())) {
                    throw ApiException.badRequest("ALERT_REQUIRED", "재난 문자 지역과 종류를 입력합니다.");
                }
                if (c.from() == null || c.to() == null || !c.from().isBefore(c.to())) {
                    throw ApiException.badRequest("INVALID_TIME", "재난 문자 시작 시각은 끝 시각보다 빨라야 합니다.");
                }
                String region = c.region().strip();
                String alertKind = c.alertKind().strip();
                yield AppliedChange.alert(region, alertKind, c.from().toString(), c.to().toString(),
                        region + " " + alertKind + " " + c.from() + "~" + c.to());
            }
            default -> throw ApiException.badRequest("UNKNOWN_CHANGE", "알 수 없는 변경 종류입니다: " + c.kind());
        };
    }

    /**
     * 패널에서 온 변경 한 건을 검사한다. 변경 입력과 같은 검사(validate)에 수리 여부, 적용 기간, 메모를 더한다.
     */
    private AppliedChange validateResource(ResourceChange c, PlanData data, LocalDate shootDate) {
        AppliedChange out = validate(new ChangeItem(c.kind(), c.targetId(), c.from(), c.to(),
                null, null, null, null, null), data);
        boolean equipment = "EQUIPMENT_UNAVAILABLE".equals(c.kind());
        if (equipment && "REPAIR".equals(c.status())) {
            out = out.withStatus("REPAIR").withSummary(out.summary().replace("(고장)", "(수리 중)"));
        }
        if (c.untilDate() != null) {
            if (!equipment && !"LOCATION_UNAVAILABLE".equals(c.kind())) {
                throw ApiException.badRequest("UNTIL_NOT_ALLOWED", "적용 기간은 장비와 장소에만 정할 수 있습니다.");
            }
            if (c.untilDate().isBefore(shootDate)) {
                throw ApiException.badRequest("INVALID_UNTIL", "적용 끝 날짜는 이 촬영일보다 빠를 수 없습니다.");
            }
            out = out.withUntilDate(c.untilDate().toString()).withSummary(out.summary() + ", " + c.untilDate() + "까지");
        }
        if (!isBlank(c.memo())) {
            out = out.withMemo(c.memo().strip());
        }
        return out;
    }

    private void apply(ShootDay shootDay, long eventId, AppliedChange c, String username) {
        long shootDayId = shootDay.id();
        String kind = c.kind();
        Long target = c.targetId();
        LocalDate until = c.untilDate() == null ? null : LocalDate.parse(c.untilDate());
        String memo = c.memo();
        switch (kind) {
            case "EQUIPMENT_UNAVAILABLE" -> overrides.insert(shootDayId, eventId, kind, target,
                    c.status() == null ? Map.of() : Map.of("status", c.status()), until, memo, username);
            case "LOCATION_UNAVAILABLE" -> overrides.insert(shootDayId, eventId, kind, target, Map.of(), until, memo, username);
            case "ACTOR_ABSENT" -> overrides.insert(shootDayId, eventId, "ACTOR_WINDOW", target,
                    Map.of("from", ABSENT.toString(), "to", ABSENT.toString()), null, memo, username);
            case "ACTOR_WINDOW" -> overrides.insert(shootDayId, eventId, kind, target,
                    Map.of("from", c.from(), "to", c.to()), null, memo, username);
            case "RAIN_FORECAST" -> overrides.insert(shootDayId, eventId, kind, target,
                    Map.of("fromHour", c.fromHour(), "toHour", c.toHour(), "mm", c.mm()), null, memo, username);
            // 재난 문자는 이 촬영일 날짜에만 적용한다. 다른 날 촬영일의 판정에는 섞이지 않는다.
            case "DISASTER_ALERT" -> plans.insertAlert(shootDay.shootDate(), c.region(), c.alertKind(),
                    LocalTime.parse(c.from()), LocalTime.parse(c.to()), c.region() + " " + c.alertKind());
            default -> throw new IllegalStateException(kind);
        }
    }

    private static void requireChangeRole(CurrentUser user, String message) {
        if (!Role.CHANGERS.contains(user.role())) {
            throw ApiException.forbidden(message);
        }
    }

    private ShootDay shootDay(long shootDayId) {
        return plans.findShootDay(shootDayId).orElseThrow(() -> PlanDataService.shootDayNotFound(shootDayId));
    }

    /** 재계획 작업을 만들고, 같은 트랜잭션의 outbox로 Agent 시작 메시지를 남긴다. */
    private long startReplan(long shootDayId, long eventId, String username) {
        long taskId = tasks.insertTask("REPLAN", null, eventId, null, shootDayId, username,
                UUID.randomUUID().toString(), "event-");
        outbox.agentStart(tasks.findTask(taskId).orElseThrow());
        return taskId;
    }

    private static ApiException versionConflict() {
        return ApiException.conflict("DATA_VERSION_CONFLICT", "다른 변경이 먼저 저장되었습니다. 새로 불러온 뒤 다시 저장하세요.");
    }

    private static String summaries(List<AppliedChange> applied) {
        return applied.stream().map(AppliedChange::summary).collect(Collectors.joining(", "));
    }

    /** 변동 이력에 보일 변경 유형이다. 여러 종류가 섞이면 처음 것을 쓴다. */
    private static String eventType(List<ResourceChange> changes) {
        if (changes.isEmpty()) {
            return "OTHER";
        }
        return switch (changes.get(0).kind()) {
            case "EQUIPMENT_UNAVAILABLE" -> "EQUIPMENT_FAILURE";
            case "LOCATION_UNAVAILABLE" -> "LOCATION_CANCEL";
            default -> "ACTOR_SCHEDULE";
        };
    }

    /** 배우 불참도 가용 시간 덮어쓰기(ACTOR_WINDOW)로 저장하므로 같은 묶음으로 본다. */
    private static String family(String kind) {
        return "ACTOR_ABSENT".equals(kind) ? "ACTOR_WINDOW" : kind;
    }

    private static String targetName(DataOverride o, PlanData data) {
        Long id = o.targetId();
        String name = switch (o.kind()) {
            case "EQUIPMENT_UNAVAILABLE" -> id == null || !data.equipment().containsKey(id) ? null : data.equipment().get(id).name();
            case "LOCATION_UNAVAILABLE", "RAIN_FORECAST" ->
                    id == null || !data.locations().containsKey(id) ? null : data.locations().get(id).name();
            default -> id == null || !data.actors().containsKey(id) ? null : data.actors().get(id).name();
        };
        return name == null ? "대상 " + id : name;
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
