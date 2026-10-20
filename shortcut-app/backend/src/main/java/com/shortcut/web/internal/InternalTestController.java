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
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 평가 시나리오 전용 경로라 api 프로필에서만 열고 내부 토큰 체인 뒤에 둔다.
 */
@RestController
@Profile("api")
@RequestMapping("/internal/test")
public class InternalTestController {

    // 시연 데이터는 촬영일 1 하나뿐이라 되돌릴 대상을 고정한다.
    private static final long SEED_SHOOT_DAY = 1L;

    private final TestSupportService testSupport;

    public InternalTestController(TestSupportService testSupport) {
        this.testSupport = testSupport;
    }

    @PostMapping("/disaster-alerts")
    @ResponseStatus(HttpStatus.CREATED)
    public DisasterAlert addAlert(@Valid @RequestBody AlertRequest request) {
        return testSupport.addAlert(request);
    }

    @DeleteMapping("/disaster-alerts")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clearAlerts() {
        testSupport.clearAlerts();
    }

    @PostMapping("/reset")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void reset() {
        testSupport.reset(SEED_SHOOT_DAY);
    }
}
