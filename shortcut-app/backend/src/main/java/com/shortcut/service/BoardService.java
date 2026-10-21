package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Actor;
import com.shortcut.domain.Approval;
import com.shortcut.domain.Callsheet;
import com.shortcut.domain.ChangeEvent;
import com.shortcut.domain.Location;
import com.shortcut.domain.Proposal;
import com.shortcut.dto.BoardDtos.BlockView;
import com.shortcut.dto.BoardDtos.BlockWeatherView;
import com.shortcut.dto.BoardDtos.BoardResponse;
import com.shortcut.dto.BoardDtos.CallsheetContent;
import com.shortcut.dto.BoardDtos.CallsheetRef;
import com.shortcut.dto.BoardDtos.CallsheetSummary;
import com.shortcut.dto.BoardDtos.ContactView;
import com.shortcut.dto.BoardDtos.HistoryItem;
import com.shortcut.dto.BoardDtos.LocationView;
import com.shortcut.dto.BoardDtos.PendingProposalView;
import com.shortcut.dto.BoardDtos.ProjectView;
import com.shortcut.dto.BoardDtos.RainRuleView;
import com.shortcut.dto.BoardDtos.SceneView;
import com.shortcut.dto.BoardDtos.ShootDayView;
import com.shortcut.dto.BoardDtos.WeatherView;
import com.shortcut.engine.PlanEngine;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.repository.ProposalRepository.DecidedApproval;
import com.shortcut.repository.TaskRepository;
import com.shortcut.repository.UserRepository;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BoardService {

    // 촬영판 연락처에는 현장에서 바로 연락할 제작부와 연출부 책임자만 보인다.
    private static final Set<String> CONTACT_ROLES = Set.of("PRODUCER", "PRODUCTION_MANAGER", "DIRECTOR", "AD1", "AD2");
    private static final Map<String, String> EVENT_LABELS = Map.of(
            "RAIN", "우천", "ACTOR_SCHEDULE", "배우 일정", "LOCATION_CANCEL", "장소 취소",
            "EQUIPMENT_FAILURE", "장비 고장", "DISASTER", "천재지변", "OTHER", "기타");

    private final PlanDataService planData;
    private final CallsheetRepository callsheets;
    private final ProposalRepository proposals;
    private final TaskRepository tasks;
    private final UserRepository users;
    private final JsonColumns json;

    public BoardService(PlanDataService planData, CallsheetRepository callsheets, ProposalRepository proposals,
                        TaskRepository tasks, UserRepository users, JsonColumns json) {
        this.planData = planData;
        this.callsheets = callsheets;
        this.proposals = proposals;
        this.tasks = tasks;
        this.users = users;
        this.json = json;
    }

    @Transactional(readOnly = true)
    public BoardResponse today() {
        long shootDayId = planData.boardShootDayId();
        PlanData data = planData.load(shootDayId);
        Callsheet latest = callsheets.findLatest(shootDayId).orElseThrow();
        PlanSnapshot current = data.current();
        Location pmLocation = data.locations().get(current.locationId());

        List<ContactView> contacts = new ArrayList<>();
        users.findAll().stream()
                .filter(u -> u.active() && CONTACT_ROLES.contains(u.role()) && u.phone() != null)
                .forEach(u -> contacts.add(new ContactView(u.title(), u.name(), u.phone())));
        for (Actor actor : data.actors().values()) {
            if (actor.managerPhone() != null) {
                contacts.add(new ContactView("매니저", actor.name() + " 매니저", actor.managerPhone()));
            }
        }
        PendingProposalView pending = proposals.findOpen(shootDayId)
                .map(p -> new PendingProposalView(p.id(), p.versionLabel(), p.status()))
                .orElse(null);

        return new BoardResponse(
                new ProjectView(data.shootDay().projectId(), data.shootDay().projectName()),
                new ShootDayView(shootDayId, data.shootDay().shootDate(), data.shootDay().callTime(),
                        data.shootDay().dataVersion(), data.shootDay().notice()),
                new CallsheetRef(latest.versionNo(), latest.createdAt()),
                blockViews(data, current),
                json.tree(data.shootDay().crewCallsJson()),
                new WeatherView(pmLocation.name(), ShootDayQueryService.hourly(data, pmLocation.id()),
                        weatherSummary(data, pmLocation, current.start(), current.end())),
                contacts,
                pending,
                blockWeather(data, current),
                new RainRuleView(data.settings().rainBlockMm(), data.settings().rainWarnMm()));
    }

    @Transactional(readOnly = true)
    public List<CallsheetSummary> callsheets(long shootDayId) {
        planData.load(shootDayId);
        return callsheets.findAll(shootDayId).stream()
                .map(c -> new CallsheetSummary(c.versionNo(), c.createdAt(), c.proposalId()))
                .toList();
    }

    @Transactional(readOnly = true)
    public CallsheetContent callsheet(long shootDayId, int versionNo) {
        PlanData data = planData.load(shootDayId);
        Callsheet c = callsheets.find(shootDayId, versionNo)
                .orElseThrow(() -> ApiException.notFound("CALLSHEET_NOT_FOUND", "콜시트 버전이 없습니다: v" + versionNo));
        return new CallsheetContent(shootDayId, c.versionNo(), c.proposalId(), c.createdAt(),
                data.shootDay().shootDate(), data.shootDay().callTime(), blockViews(data, c.pm()));
    }

    /**
     * 여러 테이블에 흩어진 사건을 시간순 한 줄 이력으로 모은다.
     * 별도 이력 테이블을 두면 원본과 어긋날 수 있어 조회할 때마다 원본에서 만든다.
     */
    @Transactional(readOnly = true)
    public List<HistoryItem> history(long shootDayId) {
        PlanData data = planData.load(shootDayId);
        List<HistoryItem> items = new ArrayList<>();
        for (ChangeEvent event : tasks.findEvents(shootDayId)) {
            String link = tasks.findTaskByEvent(event.id()).map(t -> "/tasks/" + t.id()).orElse(null);
            items.add(new HistoryItem(event.createdAt(), "EVENT",
                    EVENT_LABELS.getOrDefault(event.type(), event.type()) + " 변동 접수: " + event.detail(), link));
        }
        for (Proposal p : proposals.findByShootDay(shootDayId)) {
            String link = "/proposals/" + p.id();
            if (p.loopNo() > 1) {
                items.add(new HistoryItem(p.createdAt(), "REPLAN_LOOP", "재계획 루프 " + p.loopNo(), "/tasks/" + p.taskId()));
            }
            Location location = data.locations().get(p.proposed().locationId());
            items.add(new HistoryItem(p.createdAt(), "PROPOSAL",
                    "변경안 " + p.versionLabel() + " 생성: " + location.name(), link));
            List<String> roles = proposals.findApprovals(p.id()).stream().map(Approval::role).toList();
            items.add(new HistoryItem(p.createdAt(), "APPROVAL_REQUEST",
                    "승인 요청: " + String.join(", ", roles), link));
            if ("STALE".equals(p.status())) {
                items.add(new HistoryItem(p.updatedAt(), "STALE",
                        "변경안 " + p.versionLabel() + " 무효: 촬영 데이터 변경", link));
            }
        }
        for (DecidedApproval decided : proposals.findDecided(shootDayId)) {
            boolean approved = "APPROVED".equals(decided.approval().status());
            String text = "v" + decided.versionNo() + " " + decided.approval().role() + " "
                    + nullToEmpty(decided.approval().userName())
                    + (approved ? " 승인" : " 거절: " + nullToEmpty(decided.approval().reason()));
            items.add(new HistoryItem(decided.approval().decidedAt(), approved ? "APPROVED" : "REJECTED", text,
                    "/proposals/" + decided.approval().proposalId()));
        }
        for (Callsheet c : callsheets.findAll(shootDayId)) {
            if (c.proposalId() != null) {
                items.add(new HistoryItem(c.createdAt(), "COMMITTED", "확정 콜시트 v" + c.versionNo(), "/"));
            }
        }
        callsheets.findDistributions(shootDayId).forEach(d -> items.add(new HistoryItem(d.at(), "DISTRIBUTED",
                "콜시트 v" + d.versionNo() + " 배포 완료 (" + d.recipients() + "명)", "/")));
        items.sort(Comparator.comparing(HistoryItem::at, Comparator.nullsLast(OffsetDateTime::compareTo)));
        return items;
    }

    private static List<BlockView> blockViews(PlanData data, PlanSnapshot pm) {
        return data.blocks().stream().map(block -> {
            boolean changing = PlanData.CHANGING_BLOCK.equals(block.code());
            long locationId = changing ? pm.locationId() : block.locationId();
            List<Long> equipmentIds = changing ? pm.equipmentIds() : block.equipmentIds();
            Location l = data.locations().get(locationId);
            List<SceneView> scenes = data.scenesOf(block.code()).stream()
                    .map(s -> new SceneView(s.code(), s.title(), s.durationMin(),
                            s.actorIds().stream().map(id -> data.actors().get(id).name()).toList()))
                    .toList();
            return new BlockView(block.code(), changing ? pm.start() : block.start(), changing ? pm.end() : block.end(),
                    new LocationView(l.id(), l.name(), l.address(), l.indoor(), l.region()),
                    ShootDayQueryService.equipment(data, equipmentIds), scenes);
        }).toList();
    }

    /** 블록마다 실제 촬영지(오후는 확정 콜시트 기준)의 날씨를 만든다. */
    private static List<BlockWeatherView> blockWeather(PlanData data, PlanSnapshot current) {
        return data.blocks().stream().map(block -> {
            boolean changing = PlanData.CHANGING_BLOCK.equals(block.code());
            Location l = data.locations().get(changing ? current.locationId() : block.locationId());
            var start = changing ? current.start() : block.start();
            var end = changing ? current.end() : block.end();
            return new BlockWeatherView(block.code(), l.id(), l.name(), l.indoor(), ShootDayQueryService.hourly(data, l.id()),
                    weatherSummary(data, l, start, end));
        }).toList();
    }

    private static String weatherSummary(PlanData data, Location location, java.time.LocalTime start,
                                         java.time.LocalTime end) {
        if (location.indoor()) {
            return location.name() + "은(는) 실내라 강수 영향이 없습니다.";
        }
        double blockMm = data.settings().rainBlockMm();
        double warnMm = data.settings().rainWarnMm();
        Map<Integer, Double> hourly = data.hourly(location.id());
        int lastHour = (end.toSecondOfDay() / 60 - 1) / 60;
        double max = 0;
        Integer firstRainy = null;
        for (int hour = start.getHour(); hour <= lastHour; hour++) {
            double precip = hourly.getOrDefault(hour, 0.0);
            max = Math.max(max, precip);
            if (firstRainy == null && precip >= warnMm) {
                firstRainy = hour;
            }
        }
        if (max >= blockMm) {
            return firstRainy + "시부터 시간당 " + PlanEngine.mm(max) + "mm 비로 야외 촬영이 어렵습니다(기준 "
                    + PlanEngine.mm(blockMm) + "mm).";
        }
        if (max >= warnMm) {
            return firstRainy + "시부터 시간당 " + PlanEngine.mm(max) + "mm 비로 우천 대비가 필요합니다.";
        }
        return "촬영 시간대 강수량이 시간당 " + PlanEngine.mm(max) + "mm로 영향이 적습니다.";
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
