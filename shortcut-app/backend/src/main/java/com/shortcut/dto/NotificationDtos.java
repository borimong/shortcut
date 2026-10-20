package com.shortcut.dto;

import com.shortcut.domain.Notification;
import java.time.OffsetDateTime;
import java.util.List;

public final class NotificationDtos {

    private NotificationDtos() {
    }

    public record NotificationList(long unreadCount, List<NotificationView> items) {
    }

    public record NotificationView(long id, String kind, String title, String body, String link, boolean read,
                                   OffsetDateTime createdAt) {

        public static NotificationView of(Notification n) {
            return new NotificationView(n.id(), n.kind(), n.title(), n.body(), n.link(), n.read(), n.createdAt());
        }
    }

    public record ApprovalUpdated(long proposalId, int approvedCount, int requiredCount, String status) {
    }
}
