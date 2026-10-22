package com.shortcut.web.internal;

import com.shortcut.domain.DisasterAlert;
import com.shortcut.dto.TestDtos.AlertRequest;
import com.shortcut.service.TestSupportService;
import jakarta.validation.Valid;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 평가 시나리오 전용 경로라 api 프로필에서만 열고 내부 토큰 체인 뒤에 둔다.
 */
@RestController
@Profile("api")
@RequestMapping("/internal/test")
public class InternalTestController {

    // 재난 알림을 넣는 곳과 초기화의 기본값은 시연 촬영일(1회차)이다.
    private static final long SEED_SHOOT_DAY = 1L;

    private final TestSupportService testSupport;

    public InternalTestController(TestSupportService testSupport) {
        this.testSupport = testSupport;
    }

    @PostMapping("/disaster-alerts")
    @ResponseStatus(HttpStatus.CREATED)
    public DisasterAlert addAlert(@Valid @RequestBody AlertRequest request) {
        return testSupport.addAlert(SEED_SHOOT_DAY, request);
    }

    @DeleteMapping("/disaster-alerts")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clearAlerts() {
        testSupport.clearAlerts();
    }

    /** 이 촬영일이 속한 작품의 모든 촬영일을 시드 상태로 되돌린다. 비우면 시연 촬영일(1회차)의 작품이다. */
    @PostMapping("/reset")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void reset(@RequestParam(required = false) Long shootDayId) {
        testSupport.reset(shootDayId == null ? SEED_SHOOT_DAY : shootDayId);
    }
}
