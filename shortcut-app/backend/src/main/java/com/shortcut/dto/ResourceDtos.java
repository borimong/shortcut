package com.shortcut.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;

public final class ResourceDtos {

    private ResourceDtos() {
    }

    /**
     * 자원 현황 패널 한 화면 분량이다. 변경 입력과 덮어쓰기가 이미 반영된 상태다.
     */
    public record ResourceBoard(long shootDayId, LocalDate shootDate, int dataVersion, boolean canEdit,
                                List<ResourceItem> equipment, List<ResourceItem> locations, List<ResourceItem> actors) {
    }

    /**
     * @param status 장비는 OK, BROKEN, REPAIR, 장소는 OK, CANCELLED, 배우는 OK, ABSENT, LIMITED
     * @param usage 확정된 오후 블록에서 쓰이는 곳(예: 오후 블록 사용 중). 쓰이지 않으면 null
     * @param override 지금 걸려 있는 상태 기록. 정상이면 null
     */
    public record ResourceItem(long id, String name, String status, String usage,
                               LocalTime availableFrom, LocalTime availableTo, ActiveOverride override) {
    }

    /**
     * @param fromOtherDay 다른 촬영일에 등록한 기록이 기간 덕분에 이 촬영일에도 적용되고 있는지
     */
    public record ActiveOverride(long id, LocalDate untilDate, String memo, String createdBy, OffsetDateTime createdAt,
                                 Long eventId, boolean fromOtherDay) {
    }

    /**
     * @param dataVersion 패널을 불러올 때 받은 버전. 그사이 누가 바꿨으면 409로 막는다
     * @param replan 저장한 뒤 재계획을 시작할지
     * @param clears 정상으로 되돌릴 상태 기록(override) id
     */
    public record ResourceChangeRequest(Long shootDayId, @NotNull Integer dataVersion, boolean replan,
                                        @Valid @Size(max = 20) List<ResourceChange> changes,
                                        @Size(max = 20) List<Long> clears) {
    }

    /**
     * @param status 장비만 쓴다. BROKEN(고장) 또는 REPAIR(수리 중)
     * @param untilDate 장비와 장소만 쓴다. 있으면 그날까지 모든 촬영일에 적용한다
     */
    public record ResourceChange(
            @NotNull @Pattern(regexp = "EQUIPMENT_UNAVAILABLE|LOCATION_UNAVAILABLE|ACTOR_ABSENT|ACTOR_WINDOW") String kind,
            @NotNull Long targetId,
            @Pattern(regexp = "BROKEN|REPAIR") String status,
            LocalTime from,
            LocalTime to,
            LocalDate untilDate,
            @Size(max = 200) String memo) {
    }

    /**
     * @param taskId 재계획을 요청하지 않았으면 null
     * @param superseded 이번 변경으로 무효가 된 승인 대기 변경안 수
     */
    public record ResourceChangeResult(long eventId, Long taskId, int dataVersion, int superseded) {
    }
}
