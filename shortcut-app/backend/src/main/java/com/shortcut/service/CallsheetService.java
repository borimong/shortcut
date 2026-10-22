package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.Callsheet;
import com.shortcut.dto.BoardDtos.RestoreResult;
import com.shortcut.engine.CheckResult;
import com.shortcut.engine.Finding;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.CallsheetRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ProposalRepository;
import com.shortcut.security.CurrentUser;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 확정한 콜시트를 앞 버전으로 되돌린다. 버전 기록은 지우지 않고, 앞 버전의 오후 블록으로 촬영판을 복구한 뒤
 * 새 버전 번호로 다시 배포한다. 그래서 배포 기록과 이력이 그대로 남고 받은 사람은 "되돌린 새 콜시트"를 받는다.
 */
@Service
public class CallsheetService {

    private static final DateTimeFormatter HH_MM = DateTimeFormatter.ofPattern("HH:mm");

    private final PlanRepository plans;
    private final CallsheetRepository callsheets;
    private final ProposalRepository proposals;
    private final PlanDataService planData;
    private final PlanService planService;
    private final SupersedeService supersede;
    private final OutboxService outbox;
    private final NotificationService notifications;

    public CallsheetService(PlanRepository plans, CallsheetRepository callsheets, ProposalRepository proposals,
                            PlanDataService planData, PlanService planService, SupersedeService supersede,
                            OutboxService outbox, NotificationService notifications) {
        this.plans = plans;
        this.callsheets = callsheets;
        this.proposals = proposals;
        this.planData = planData;
        this.planService = planService;
        this.supersede = supersede;
        this.outbox = outbox;
        this.notifications = notifications;
    }

    /**
     * 제작 PD와 연출감독만 되돌릴 수 있다. 되돌릴 안도 지금 촬영 데이터(날씨, 배우 일정, 고장 등)로 다시 검사해
     * 하드 제약을 어기면 되돌리지 않는다. 승인을 기다리던 변경안은 데이터가 바뀌었으므로 무효가 된다.
     */
    @Transactional
    public RestoreResult restore(CurrentUser user, long shootDayId, int versionNo, String reason) {
        if (!EventService.CHANGE_ROLES.contains(user.role())) {
            throw ApiException.forbidden("콜시트 되돌리기는 제작 PD와 연출감독만 할 수 있습니다.");
        }
        plans.lockDataVersion(shootDayId)
                .orElseThrow(() -> ApiException.notFound("SHOOT_DAY_NOT_FOUND", "촬영일이 없습니다: " + shootDayId));
        Callsheet target = callsheets.find(shootDayId, versionNo)
                .orElseThrow(() -> ApiException.notFound("CALLSHEET_NOT_FOUND", "콜시트 버전이 없습니다: v" + versionNo));
        Callsheet latest = callsheets.findLatest(shootDayId).orElseThrow();
        if (latest.versionNo() == versionNo) {
            throw ApiException.conflict("ALREADY_LATEST", "지금 콜시트가 v" + versionNo + "입니다.");
        }
        PlanData data = planData.load(shootDayId);
        PlanSnapshot pm = target.pm();
        CheckResult check = planService.check(data, pm.locationId(), pm.equipmentIds(), pm.start(), pm.end(), List.of());
        if (!check.feasible()) {
            String why = check.violations().stream().map(Finding::message).collect(Collectors.joining(" "));
            throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "RESTORE_INVALID",
                    "v" + versionNo + "은(는) 지금 촬영 데이터로는 하드 제약을 어겨 되돌릴 수 없습니다. " + why,
                    Map.of("violations", check.violations()));
        }
        // 비용은 지금 장소와 장비 값으로 다시 계산한다.
        PlanSnapshot restored = data.snapshot(pm.locationId(), pm.equipmentIds(), pm.start(), pm.end());
        String note = reason == null || reason.isBlank() ? null : reason.strip();

        plans.updateBlock(shootDayId, PlanData.CHANGING_BLOCK, restored);
        int dataVersion = plans.bumpDataVersion(shootDayId);
        // 변경안과 콜시트 번호가 겹치지 않게 변경안 번호 규칙(둘 중 큰 번호 + 1)을 함께 쓴다.
        int newVersion = proposals.nextVersionNo(shootDayId);
        Callsheet created = callsheets.insertRestored(shootDayId, newVersion, restored, versionNo, note, user.username());

        String reservationStatus;
        if (callsheets.hasHeldReservation(shootDayId, restored.locationId())) {
            reservationStatus = "HELD";
        } else {
            // 확정과 같이 외부 예약 연동이 없는 장소는 제작부 담당자가 직접 잡도록 처리 대기로 남긴다.
            callsheets.insertManualReservation("M-R" + created.id(), shootDayId, restored.locationId(),
                    restored.start(), restored.end());
            reservationStatus = "MANUAL_PENDING";
        }
        supersede.supersedeOlder(shootDayId, dataVersion, "콜시트 v" + versionNo + "으로 되돌림");
        outbox.callsheetJob(created.id(), shootDayId, newVersion, UUID.randomUUID().toString());
        String place = data.locations().get(restored.locationId()).name();
        notifications.notifyAll(NotificationService.CHANGE_NOTICE, "콜시트 v" + newVersion + " 배포(v" + versionNo + "으로 되돌림)",
                "오후 블록: " + place + " " + restored.start().format(HH_MM) + "~" + restored.end().format(HH_MM)
                        + (note == null ? "" : ". 사유: " + note), "/callsheet");
        return new RestoreResult(newVersion, versionNo, reservationStatus);
    }
}
