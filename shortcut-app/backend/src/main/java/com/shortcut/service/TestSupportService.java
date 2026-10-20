package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.DisasterAlert;
import com.shortcut.dto.TestDtos.AlertRequest;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ResetRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 평가 시나리오를 반복하려고 재난 문자 주입과 시드 복원을 제공한다.
 */
@Service
public class TestSupportService {

    private final PlanRepository plans;
    private final ResetRepository reset;

    public TestSupportService(PlanRepository plans, ResetRepository reset) {
        this.plans = plans;
        this.reset = reset;
    }

    @Transactional
    public DisasterAlert addAlert(AlertRequest request) {
        if (!request.startsAt().isBefore(request.endsAt())) {
            throw ApiException.badRequest("INVALID_TIME", "시작 시각은 종료 시각보다 빨라야 합니다.");
        }
        String message = request.message() == null ? request.region() + " " + request.kind() : request.message();
        return plans.insertAlert(request.region(), request.kind(), request.startsAt(), request.endsAt(), message);
    }

    @Transactional
    public void clearAlerts() {
        plans.deleteAlerts();
    }

    @Transactional
    public void reset(long shootDayId) {
        reset.reset(shootDayId);
    }
}
