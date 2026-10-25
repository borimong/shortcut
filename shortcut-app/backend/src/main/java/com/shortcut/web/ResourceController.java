package com.shortcut.web;

import com.shortcut.dto.ResourceDtos.ResourceBoard;
import com.shortcut.dto.ResourceDtos.ResourceChangeRequest;
import com.shortcut.dto.ResourceDtos.ResourceChangeResult;
import com.shortcut.dto.ScheduleDtos.ActorScheduleResponse;
import com.shortcut.dto.ScheduleDtos.PlaceabilityResponse;
import com.shortcut.dto.ScheduleDtos.PlanCheckResponse;
import com.shortcut.security.CurrentUser;
import com.shortcut.service.EventService;
import com.shortcut.service.ResourceService;
import com.shortcut.service.ScheduleService;
import jakarta.validation.Valid;
import java.time.LocalDate;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 자원 현황 패널이 쓰는 API다. 장비 고장, 장소 취소, 배우 가용 시간을 보고 바로 고친다.
 */
@RestController
@RequestMapping("/api/resources")
public class ResourceController {

    private final ResourceService resources;
    private final EventService events;
    private final ScheduleService schedules;

    public ResourceController(ResourceService resources, EventService events, ScheduleService schedules) {
        this.resources = resources;
        this.events = events;
        this.schedules = schedules;
    }

    /** 배우 날짜별 일정이다. 사람 화면이라 소속사 메모까지 준다. */
    @GetMapping("/actor-schedule")
    public ActorScheduleResponse actorSchedule(@RequestParam(required = false) Long shootDayId,
                                               @RequestParam(required = false) List<Long> actorIds,
                                               @RequestParam(required = false) LocalDate from,
                                               @RequestParam(defaultValue = "14") int days) {
        return schedules.actorSchedule(shootDayId, actorIds, from, days, true);
    }

    /** 오후 블록 현재 확정안을 최신 배우 일정과 대본 요구로 다시 검사한 결과다. */
    @GetMapping("/plan-check")
    public PlanCheckResponse planCheck(@RequestParam(required = false) Long shootDayId) {
        return schedules.planCheck(shootDayId);
    }

    /** 아직 배정하지 않은 대본 씬을 배우 일정 안에서 찍을 수 있는지다. */
    @GetMapping("/placeability")
    public PlaceabilityResponse placeability(@RequestParam(required = false) Long shootDayId) {
        return schedules.placeability(shootDayId);
    }

    @GetMapping
    public ResourceBoard board(@AuthenticationPrincipal Jwt jwt, @RequestParam(required = false) Long shootDayId) {
        return resources.board(CurrentUser.from(jwt), shootDayId);
    }

    /**
     * 재계획을 함께 요청하면 큐 뒤에서 비동기로 도므로 202, 상태만 바꿨으면 200을 준다.
     */
    @PostMapping("/changes")
    public ResponseEntity<ResourceChangeResult> change(@AuthenticationPrincipal Jwt jwt,
                                                       @Valid @RequestBody ResourceChangeRequest request) {
        ResourceChangeResult result = events.applyResources(CurrentUser.from(jwt), request);
        return ResponseEntity.status(result.taskId() == null ? HttpStatus.OK : HttpStatus.ACCEPTED).body(result);
    }
}
