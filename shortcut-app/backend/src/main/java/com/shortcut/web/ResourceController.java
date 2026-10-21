package com.shortcut.web;

import com.shortcut.dto.ResourceDtos.ResourceBoard;
import com.shortcut.dto.ResourceDtos.ResourceChangeRequest;
import com.shortcut.dto.ResourceDtos.ResourceChangeResult;
import com.shortcut.security.CurrentUser;
import com.shortcut.service.EventService;
import com.shortcut.service.ResourceService;
import jakarta.validation.Valid;
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

    public ResourceController(ResourceService resources, EventService events) {
        this.resources = resources;
        this.events = events;
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
