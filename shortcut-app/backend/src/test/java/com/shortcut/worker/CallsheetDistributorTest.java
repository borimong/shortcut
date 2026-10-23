package com.shortcut.worker;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.config.RabbitTopology;
import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.UserAccount;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.JobLogRepository;
import com.shortcut.repository.NotificationRepository;
import com.shortcut.repository.UserRepository;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * 콜시트 배포 작업이 지워진 콜시트 버전을 재시도하지 않고 건너뛰는지 본다.
 * 평가와 시연은 확정 직후 초기화하므로, 재시도로 늦게 도는 배포가 지워진 버전을 만나 외래키에 걸리던 문제다.
 */
class CallsheetDistributorTest {

    private static final JsonNode JOB = job(42, 3);

    private final UserRepository users = mock(UserRepository.class);
    private final CallsheetRepository callsheets = mock(CallsheetRepository.class);
    private final NotificationRepository notifications = mock(NotificationRepository.class);
    private final JobLogRepository jobLogs = mock(JobLogRepository.class);

    @Test
    void 콜시트_버전이_지워졌으면_배포하지_않고_건너뛴다() {
        when(callsheets.lockForDistribution(42)).thenReturn(false);

        distributor(true).distribute(JOB, "outbox-1", 1);

        verify(callsheets, never()).insertDistribution(anyLong(), anyLong());
        verify(notifications, never()).insertForUsers(anyList(), anyString(), anyString(), anyString(), anyString());
        verify(jobLogs).insert(eq(RabbitTopology.JOBS_CALLSHEET), eq("outbox-1"), eq(1), eq("SKIPPED"), anyString());
    }

    @Test
    void 콜시트_버전이_있으면_수신자마다_배포하고_성공으로_남긴다() {
        when(callsheets.lockForDistribution(42)).thenReturn(true);
        when(users.findAll()).thenReturn(List.of(user(1), user(2)));
        when(callsheets.insertDistribution(eq(42L), anyLong())).thenReturn(1);

        distributor(false).distribute(JOB, "outbox-1", 1);

        verify(callsheets).insertDistribution(42, 1);
        verify(callsheets).insertDistribution(42, 2);
        verify(notifications).insertForUsers(eq(List.of(1L, 2L)), anyString(), anyString(), anyString(), anyString());
        verify(jobLogs).insert(RabbitTopology.JOBS_CALLSHEET, "outbox-1", 1, "SUCCESS", null);
    }

    @Test
    void 재시도_시연은_콜시트_버전이_있을_때만_첫_시도를_실패시킨다() {
        when(callsheets.lockForDistribution(42)).thenReturn(true);

        assertThatThrownBy(() -> distributor(true).distribute(JOB, "outbox-1", 1))
                .isInstanceOf(IllegalStateException.class);
        verify(jobLogs, never()).insert(anyString(), anyString(), anyInt(), anyString(), isNull());
    }

    private CallsheetDistributor distributor(boolean failFirstAttempt) {
        ShortcutProperties properties = new ShortcutProperties(null, null,
                new ShortcutProperties.Worker(failFirstAttempt), null);
        return new CallsheetDistributor(users, callsheets, notifications, jobLogs, properties);
    }

    private static UserAccount user(long id) {
        return new UserAccount(id, "u" + id, "", "사용자" + id, "CREW", "연출부", "부원", null, false, true);
    }

    private static JsonNode job(long callsheetVersionId, int versionNo) {
        return new ObjectMapper().createObjectNode()
                .put("callsheetVersionId", callsheetVersionId)
                .put("versionNo", versionNo);
    }
}
