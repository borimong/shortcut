package com.shortcut.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.shortcut.common.Josa;
import com.shortcut.config.RabbitTopology;
import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.UserAccount;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.JobLogRepository;
import com.shortcut.repository.NotificationRepository;
import com.shortcut.repository.UserRepository;
import com.shortcut.service.NotificationService;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@Profile("worker")
public class CallsheetDistributor {

    private static final Logger log = LoggerFactory.getLogger(CallsheetDistributor.class);

    private final UserRepository users;
    private final CallsheetRepository callsheets;
    private final NotificationRepository notifications;
    private final JobLogRepository jobLogs;
    private final boolean failFirstAttempt;

    public CallsheetDistributor(UserRepository users, CallsheetRepository callsheets,
                                NotificationRepository notifications, JobLogRepository jobLogs,
                                ShortcutProperties properties) {
        this.users = users;
        this.callsheets = callsheets;
        this.notifications = notifications;
        this.jobLogs = jobLogs;
        this.failFirstAttempt = properties.worker().failFirstAttempt();
    }

    /**
     * 배포 기록, 알림, 성공 로그를 한 트랜잭션으로 남겨 실패 시 반쯤 배포된 상태가 남지 않게 한다.
     * 이미 배포된 메시지가 다시 오면 새 기록이 0건이라 알림을 또 만들지 않는다.
     * 콜시트 버전이 그사이 초기화로 지워졌으면 다시 해도 성공할 수 없으므로 재시도하지 않고 건너뛴다.
     */
    @Transactional
    public void distribute(JsonNode job, String messageId, int attempt) {
        long callsheetVersionId = job.path("callsheetVersionId").asLong();
        int versionNo = job.path("versionNo").asInt();
        if (callsheetVersionId <= 0 || versionNo <= 0) {
            throw new IllegalArgumentException("배포 메시지에 콜시트 버전이 없습니다.");
        }
        if (!callsheets.lockForDistribution(callsheetVersionId)) {
            log.warn("배포할 콜시트 버전 {}(v{})이 없어 건너뜁니다. 초기화로 지워졌을 수 있습니다.", callsheetVersionId, versionNo);
            jobLogs.insert(RabbitTopology.JOBS_CALLSHEET, messageId, attempt, "SKIPPED",
                    "콜시트 버전 " + callsheetVersionId + "이 없습니다.");
            return;
        }
        if (failFirstAttempt && attempt == 1) {
            throw new IllegalStateException("재시도 시연을 위해 첫 시도를 실패시킵니다.");
        }
        List<Long> newlySent = new ArrayList<>();
        for (UserAccount user : users.findAll()) {
            if (callsheets.insertDistribution(callsheetVersionId, user.id()) > 0) {
                newlySent.add(user.id());
            }
        }
        notifications.insertForUsers(newlySent, NotificationService.CALLSHEET,
                Josa.iGa("확정 콜시트 v" + versionNo) + " 배포되었습니다", "변경된 오후 블록을 확인해 주세요.", "/");
        jobLogs.insert(RabbitTopology.JOBS_CALLSHEET, messageId, attempt, "SUCCESS", null);
    }
}
