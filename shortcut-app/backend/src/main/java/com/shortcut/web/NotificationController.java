package com.shortcut.web;

import com.shortcut.dto.NotificationDtos.NotificationList;
import com.shortcut.service.NotificationService;
import com.shortcut.service.SseHub;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationService notifications;
    private final SseHub hub;

    public NotificationController(NotificationService notifications, SseHub hub) {
        this.notifications = notifications;
        this.hub = hub;
    }

    @GetMapping
    public NotificationList list(@AuthenticationPrincipal Jwt jwt) {
        return notifications.list(jwt.getSubject());
    }

    @PostMapping("/{id}/read")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void read(@AuthenticationPrincipal Jwt jwt, @PathVariable long id) {
        notifications.markRead(id, jwt.getSubject());
    }

    @PostMapping("/read-all")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void readAll(@AuthenticationPrincipal Jwt jwt) {
        notifications.markAllRead(jwt.getSubject());
    }

    @GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(@AuthenticationPrincipal Jwt jwt) {
        return hub.openUser(jwt.getSubject());
    }
}
