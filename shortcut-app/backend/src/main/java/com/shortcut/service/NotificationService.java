package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.UserAccount;
import com.shortcut.dto.NotificationDtos.NotificationList;
import com.shortcut.dto.NotificationDtos.NotificationView;
import com.shortcut.repository.NotificationRepository;
import com.shortcut.repository.UserRepository;
import java.util.Collection;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 알림은 DB에만 쓰고 SSE 전달은 NotificationRelay가 맡는다.
 * worker도 같은 방식으로 알림을 남기므로 전달 경로가 하나로 모인다.
 */
@Service
public class NotificationService {

    public static final String CHANGE_NOTICE = "CHANGE_NOTICE";
    public static final String APPROVAL_REQUEST = "APPROVAL_REQUEST";
    public static final String DECISION = "DECISION";
    public static final String CALLSHEET = "CALLSHEET";
    // 종 아이콘 드롭다운에 보여 줄 만큼만 내려 응답을 가볍게 한다.
    private static final int LIST_LIMIT = 50;

    private final NotificationRepository notifications;
    private final UserRepository users;

    public NotificationService(NotificationRepository notifications, UserRepository users) {
        this.notifications = notifications;
        this.users = users;
    }

    public void notifyRoles(List<String> roles, String kind, String title, String body, String link) {
        notifications.insertForUsers(users.findByRoles(roles).stream().map(UserAccount::id).toList(),
                kind, title, body, link);
    }

    public void notifyUsernames(Collection<String> usernames, String kind, String title, String body, String link) {
        List<Long> ids = users.findAll().stream()
                .filter(user -> usernames.contains(user.username()))
                .map(UserAccount::id)
                .toList();
        notifications.insertForUsers(ids, kind, title, body, link);
    }

    public void notifyAll(String kind, String title, String body, String link) {
        notifications.insertForAll(kind, title, body, link);
    }

    @Transactional(readOnly = true)
    public NotificationList list(String username) {
        List<NotificationView> items = notifications.findForUser(username, LIST_LIMIT).stream()
                .map(NotificationView::of)
                .toList();
        return new NotificationList(notifications.countUnread(username), items);
    }

    @Transactional
    public void markRead(long id, String username) {
        if (notifications.markRead(id, username) == 0) {
            throw ApiException.notFound("NOTIFICATION_NOT_FOUND", "알림이 없습니다: " + id);
        }
    }

    @Transactional
    public void markAllRead(String username) {
        notifications.markAllRead(username);
    }
}
