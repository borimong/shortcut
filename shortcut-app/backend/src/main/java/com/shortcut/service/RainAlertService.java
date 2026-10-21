package com.shortcut.service;

import com.shortcut.domain.AppSettings;
import com.shortcut.domain.Location;
import com.shortcut.dto.AdminDtos.RainCheckResult;
import com.shortcut.engine.PlanEngine;
import com.shortcut.engine.PlanSnapshot;
import com.shortcut.repository.OverrideRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 야외 촬영지에 촬영 불가 기준 이상의 비가 예보되면, 관리자가 정한 시간만큼 미리 전원에게 알린다.
 * 기준 강수량은 엔진의 하드 제약과 같은 관리자 설정을 써서 "알림은 왔는데 엔진은 통과" 같은 어긋남이 없게 한다.
 */
@Service
@Profile("api")
public class RainAlertService {

    // 촬영 현장 시각 기준으로 판단한다. 컨테이너 기본 시간대(UTC)를 쓰면 알림이 9시간 어긋난다.
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final Map<String, String> BLOCK_LABELS = Map.of("AM", "오전", "PM", "오후");

    private final PlanDataService planData;
    private final OverrideRepository overrides;
    private final NotificationService notifications;

    public RainAlertService(PlanDataService planData, OverrideRepository overrides, NotificationService notifications) {
        this.planData = planData;
        this.overrides = overrides;
        this.notifications = notifications;
    }

    @Scheduled(initialDelay = 30_000, fixedDelay = 60_000)
    public void scheduledCheck() {
        check(ZonedDateTime.now(SEOUL));
    }

    @Transactional
    public RainCheckResult check(ZonedDateTime now) {
        long shootDayId = planData.boardShootDayId();
        PlanData data = planData.load(shootDayId);
        AppSettings settings = data.settings();
        LocalDate date = data.shootDay().shootDate();
        PlanSnapshot pm = data.current();
        List<String> sent = new ArrayList<>();
        for (var block : data.blocks()) {
            boolean changing = PlanData.CHANGING_BLOCK.equals(block.code());
            Location location = data.locations().get(changing ? pm.locationId() : block.locationId());
            LocalTime start = changing ? pm.start() : block.start();
            LocalTime end = changing ? pm.end() : block.end();
            if (location.indoor()) {
                continue;
            }
            Map<Integer, Double> hourly = data.hourly(location.id());
            int lastHour = (end.toSecondOfDay() / 60 - 1) / 60;
            for (int hour = start.getHour(); hour <= lastHour; hour++) {
                double mm = hourly.getOrDefault(hour, 0.0);
                if (mm < settings.rainBlockMm()) {
                    continue;
                }
                LocalTime rainFrom = LocalTime.of(hour, 0).isBefore(start) ? start : LocalTime.of(hour, 0);
                ZonedDateTime alertAt = date.atTime(rainFrom).atZone(SEOUL).minusHours(settings.rainAlertLeadHours());
                ZonedDateTime blockEnd = date.atTime(end).atZone(SEOUL);
                if (now.isBefore(alertAt) || !now.isBefore(blockEnd)) {
                    break;
                }
                if (overrides.markRainAlertSent(shootDayId, location.id(), hour)) {
                    String title = "비로 촬영 불가 예상: " + location.name() + " " + hour + "시";
                    String body = date + " " + hour + "시부터 시간당 " + PlanEngine.mm(mm) + "mm 비가 예보되어 기준 "
                            + PlanEngine.mm(settings.rainBlockMm()) + "mm 이상입니다. "
                            + BLOCK_LABELS.getOrDefault(block.code(), block.code()) + " 블록(" + start + "~" + end
                            + ") 야외 촬영을 다시 계획하세요.";
                    notifications.notifyAll("WEATHER", title, body, "/changes/new");
                    sent.add(title);
                }
                break;
            }
        }
        return new RainCheckResult(sent.size(), sent);
    }

    public RainCheckResult checkNow() {
        return check(ZonedDateTime.now(SEOUL));
    }
}
