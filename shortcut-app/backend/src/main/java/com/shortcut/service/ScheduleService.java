package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.Actor;
import com.shortcut.domain.AvailabilityEntry;
import com.shortcut.domain.ScheduledSlot;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.ScheduleDtos.ActorDayView;
import com.shortcut.dto.ScheduleDtos.ActorScheduleResponse;
import com.shortcut.dto.ScheduleDtos.ActorScheduleView;
import com.shortcut.dto.ScheduleDtos.BusyView;
import com.shortcut.dto.ScheduleDtos.PlaceabilityResponse;
import com.shortcut.dto.ScheduleDtos.PlanCheckResponse;
import com.shortcut.dto.ScheduleDtos.PlaceabilityView;
import com.shortcut.dto.ScheduleDtos.ShootView;
import com.shortcut.dto.ScheduleDtos.WindowView;
import com.shortcut.engine.ActorDay;
import com.shortcut.engine.CheckResult;
import com.shortcut.engine.Placeability;
import com.shortcut.engine.PlanEngine;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ScheduleRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 배우 날짜별 일정(기본 일정 + 우리 촬영 배정 + 촬영일 변경 입력)과 대본 씬 배정 가능성을 만든다.
 * 촬영일의 배우 하루는 PlanDataService.load()와 같은 값을 쓰므로 엔진, 촬영판, Agent가 같은 일정을 본다.
 */
@Service
public class ScheduleService {

    // 배우 일정 조회 한 번에 볼 수 있는 최대 날 수다. Agent 도구 결과 길이 한도를 넘지 않게 한다.
    public static final int MAX_DAYS = 31;
    // 배정 가능성은 1회차부터 91일(약 3개월) 안에서 찾는다. 목데이터 일정이 1회차 뒤 91일까지 있다.
    static final int PLACEABILITY_DAYS = 91;
    // 일출·일몰을 모르는 촬영일에 쓰는 서울 10월 하순 근사값이다.
    private static final LocalTime DEFAULT_SUNRISE = LocalTime.of(6, 50);
    private static final LocalTime DEFAULT_SUNSET = LocalTime.of(17, 40);

    private final ScheduleRepository schedules;
    private final PlanRepository plans;
    private final PlanDataService planData;
    private final PlanEngine engine;

    public ScheduleService(ScheduleRepository schedules, PlanRepository plans, PlanDataService planData,
                           PlanEngine engine) {
        this.schedules = schedules;
        this.plans = plans;
        this.planData = planData;
        this.engine = engine;
    }

    /**
     * 오후 블록 현재 확정안을 최신 데이터(배우 날짜별 일정, 대본 요구 포함)로 다시 검사한다.
     * 변경 입력이 없어도 확정 뒤 들어온 배우 일정 충돌 같은 문제를 촬영판에서 먼저 보이려는 것이다.
     */
    @Transactional(readOnly = true)
    public PlanCheckResponse planCheck(Long shootDayId) {
        PlanData data = planData.load(shootDayId == null ? planData.boardShootDayId() : shootDayId);
        PlanSnapshot current = data.current();
        CheckResult result = engine.check(data.toInput(), current.locationId(), current.equipmentIds(), current.start(),
                current.end(), List.of());
        return new PlanCheckResponse(data.shootDay().id(), data.shootDay().dataVersion(), result.violations(),
                result.warnings());
    }

    /**
     * 배우들의 날짜별 일정이다. 촬영일 날짜는 그 촬영일의 변경 입력까지 얹는다.
     *
     * @param withMemo 사람 화면이면 true. Agent가 받는 내부 응답은 사유 종류만 남긴다
     */
    @Transactional(readOnly = true)
    public ActorScheduleResponse actorSchedule(Long shootDayId, List<Long> actorIds, LocalDate from, int days,
                                               boolean withMemo) {
        if (days < 1 || days > MAX_DAYS) {
            throw ApiException.badRequest("INVALID_DAYS", "조회 기간은 1~" + MAX_DAYS + "일입니다.");
        }
        ShootDay anchor = shootDay(shootDayId);
        LocalDate start = from == null ? anchor.shootDate() : from;
        LocalDate end = start.plusDays(days - 1L);
        Map<Long, Actor> actors = new LinkedHashMap<>();
        plans.findActors().stream().filter(a -> actorIds == null || actorIds.isEmpty() || actorIds.contains(a.id()))
                .forEach(a -> actors.put(a.id(), a));
        Map<LocalDate, Map<Long, List<AvailabilityEntry>>> entries = byDate(schedules.findAvailability(start, end));
        Map<LocalDate, Map<Long, List<ScheduledSlot>>> slots = schedules.findScheduledSlots(anchor.projectId(), start, end)
                .stream().collect(Collectors.groupingBy(ScheduledSlot::date,
                        Collectors.groupingBy(ScheduledSlot::actorId)));
        Map<LocalDate, PlanData> shootDays = shootDaysBetween(slots);

        List<ActorScheduleView> views = new ArrayList<>();
        for (Actor actor : actors.values()) {
            List<ActorDayView> dayViews = new ArrayList<>();
            for (LocalDate date = start; !date.isAfter(end); date = date.plusDays(1)) {
                List<AvailabilityEntry> mine = entries.getOrDefault(date, Map.of()).getOrDefault(actor.id(), List.of());
                List<ScheduledSlot> shoots = slots.getOrDefault(date, Map.of()).getOrDefault(actor.id(), List.of());
                PlanData data = shootDays.get(date);
                if (mine.isEmpty() && shoots.isEmpty() && data == null) {
                    continue;
                }
                // 촬영일이면 변경 입력까지 얹은 하루를 쓴다. 엔진이 판정한 값과 같아야 한다.
                ActorDay day = data != null ? data.actorDay(actor.id()) : ActorDay.of(actor, mine);
                dayViews.add(dayView(date, day, mine, shoots, withMemo));
            }
            views.add(new ActorScheduleView(actor.id(), actor.name(), actor.availableFrom(), actor.availableTo(),
                    actor.noNight(), dayViews));
        }
        return new ActorScheduleResponse(start, end, views);
    }

    /** 아직 배정하지 않은 대본 씬마다 배우 일정 안에서 찍을 수 있는 첫 날, 또는 못 찍는 이유다. */
    @Transactional(readOnly = true)
    public PlaceabilityResponse placeability(Long shootDayId) {
        ShootDay anchor = shootDay(shootDayId);
        LocalDate start = schedules.findFirstShootDate(anchor.projectId()).orElse(anchor.shootDate());
        LocalDate end = start.plusDays(PLACEABILITY_DAYS);
        Map<Long, Actor> actors = new LinkedHashMap<>();
        plans.findActors().forEach(a -> actors.put(a.id(), a));
        Map<LocalDate, Map<Long, List<AvailabilityEntry>>> entries = byDate(schedules.findAvailability(start, end));
        Map<LocalDate, Map<Long, List<ScheduledSlot>>> slots = schedules.findScheduledSlots(anchor.projectId(), start, end)
                .stream().collect(Collectors.groupingBy(ScheduledSlot::date,
                        Collectors.groupingBy(ScheduledSlot::actorId)));
        TreeMap<LocalDate, Map<Long, ActorDay>> days = new TreeMap<>();
        for (LocalDate date = start; !date.isAfter(end); date = date.plusDays(1)) {
            Map<Long, ActorDay> byActor = new HashMap<>();
            for (Actor actor : actors.values()) {
                ActorDay day = ActorDay.of(actor, entries.getOrDefault(date, Map.of()).getOrDefault(actor.id(), List.of()));
                // 우리 촬영에 이미 배정된 시간은 비어 있지 않다.
                for (ScheduledSlot slot : slots.getOrDefault(date, Map.of()).getOrDefault(actor.id(), List.of())) {
                    day = day.withBusy(new ActorDay.Busy(slot.start(), slot.end(), "OUR_SHOOT"));
                }
                byActor.put(actor.id(), day);
            }
            days.put(date, byActor);
        }
        LocalTime sunrise = anchor.sunrise() == null ? DEFAULT_SUNRISE : anchor.sunrise();
        LocalTime sunset = anchor.sunset() == null ? DEFAULT_SUNSET : anchor.sunset();
        List<PlaceabilityView> views = Placeability.check(schedules.findScriptScenes(anchor.projectId()), actors, days,
                        sunrise, sunset).stream()
                .map(r -> new PlaceabilityView(r.code(), r.heading(), r.actorIds(), r.minutes(), r.placeable(),
                        r.firstDate(), r.reason()))
                .toList();
        return new PlaceabilityResponse(start, end, views);
    }

    /** 촬영일을 고르지 않았으면 촬영판의 촬영일을 쓴다. 같은 작품과 기준 날짜를 정하는 데만 쓴다. */
    private ShootDay shootDay(Long shootDayId) {
        long id = shootDayId == null ? planData.boardShootDayId() : shootDayId;
        return plans.findShootDay(id)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + id));
    }

    private Map<LocalDate, PlanData> shootDaysBetween(Map<LocalDate, Map<Long, List<ScheduledSlot>>> slots) {
        Map<LocalDate, PlanData> loaded = new HashMap<>();
        slots.values().stream().flatMap(m -> m.values().stream()).flatMap(List::stream)
                .map(ScheduledSlot::shootDayId).distinct()
                .forEach(id -> {
                    PlanData data = planData.load(id);
                    loaded.put(data.shootDay().shootDate(), data);
                });
        return loaded;
    }

    private static ActorDayView dayView(LocalDate date, ActorDay day, List<AvailabilityEntry> entries,
                                        List<ScheduledSlot> shoots, boolean withMemo) {
        String offMemo = !withMemo ? null : entries.stream().filter(e -> "OFF".equals(e.kind()))
                .map(AvailabilityEntry::memo).findFirst().orElse(null);
        List<BusyView> busy = day.busy().stream()
                .map(b -> new BusyView(b.from(), b.to(), b.reasonKind(), !withMemo ? null : entries.stream()
                        .filter(e -> "BUSY".equals(e.kind()) && b.from().equals(e.start()))
                        .map(AvailabilityEntry::memo).findFirst().orElse(null)))
                .toList();
        return new ActorDayView(date, day.off(), day.offReason(), offMemo,
                day.windows().stream().map(w -> new WindowView(w.from(), w.to())).toList(), busy,
                shoots.stream().map(s -> new ShootView(s.shootDayId(), s.blockCode(), s.start(), s.end(), s.sceneCodes()))
                        .toList());
    }

    private static Map<LocalDate, Map<Long, List<AvailabilityEntry>>> byDate(List<AvailabilityEntry> entries) {
        return entries.stream().collect(Collectors.groupingBy(AvailabilityEntry::date,
                Collectors.groupingBy(AvailabilityEntry::actorId)));
    }
}
