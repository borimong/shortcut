package com.shortcut.web;

import com.shortcut.dto.TaskDtos.EventOptions;
import com.shortcut.dto.TaskDtos.EventRequest;
import com.shortcut.dto.TaskDtos.EventResponse;
import com.shortcut.security.CurrentUser;
import com.shortcut.service.EventService;
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

@RestController
@RequestMapping("/api/events")
public class EventController {

    private final EventService events;

    public EventController(EventService events) {
        this.events = events;
    }

    /**
     * 재계획은 큐 뒤에서 비동기로 도므로 접수만 하고 202를 준다.
     * 같은 변동을 다시 보내면 새 작업을 만들지 않았다는 뜻으로 200을 준다.
     */
    /** 변경 입력 화면이 고를 장소, 장비, 배우, 재난 문자 지역 목록이다. 변경 입력 결과가 이미 반영된 상태다. */
    @GetMapping("/options")
    public EventOptions options(@RequestParam(required = false) Long shootDayId) {
        return events.options(shootDayId);
    }

    @PostMapping
    public ResponseEntity<EventResponse> create(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody EventRequest request) {
        EventResponse response = events.create(CurrentUser.from(jwt), request);
        HttpStatus status = Boolean.TRUE.equals(response.duplicate()) ? HttpStatus.OK : HttpStatus.ACCEPTED;
        return ResponseEntity.status(status).body(response);
    }
}
