package com.shortcut.service;

import com.shortcut.domain.Notification;
import com.shortcut.dto.NotificationDtos.NotificationView;
import com.shortcut.repository.NotificationRepository;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * DB에 새로 쌓인 알림을 접속 중인 사용자에게 SSE로 보낸다.
 * worker는 다른 프로세스라 SSE 연결을 모르므로, 알림은 모두 DB에 쓰고 api가 2초마다 읽어 전달하는 한 가지 경로로 통일했다.
 * 브로커 팬아웃을 따로 두는 것보다 단순하고, 2초 지연은 알림 용도에 충분하다.
 */
@Component
@Profile("api")
public class NotificationRelay {

    // 한 주기에 너무 많이 밀리면 다음 주기로 넘겨 스케줄러 스레드를 오래 잡지 않는다.
    private static final int BATCH_SIZE = 500;

    private final NotificationRepository notifications;
    private final SseHub hub;
    private long lastId = -1;

    public NotificationRelay(NotificationRepository notifications, SseHub hub) {
        this.notifications = notifications;
        this.hub = hub;
    }

    /**
     * 기동 전 알림은 목록 API로 보면 되므로 첫 주기에는 현재 최대 id만 기억하고 보내지 않는다.
     * id 순서와 커밋 순서가 드물게 어긋나 실시간 전달을 놓친 알림도 목록에는 남는다.
     */
    @Scheduled(fixedDelay = 2_000)
    public void relay() {
        if (lastId < 0) {
            lastId = notifications.maxId();
            return;
        }
        for (Notification n : notifications.findAfter(lastId, BATCH_SIZE)) {
            hub.sendToUser(n.username(), "NOTIFICATION", String.valueOf(n.id()), NotificationView.of(n));
            lastId = n.id();
        }
    }
}
