package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.shortcut.common.ApiException;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Actor;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Block;
import com.shortcut.domain.DataOverride;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.ResourceDtos.ResourceChange;
import com.shortcut.dto.ResourceDtos.ResourceChangeRequest;
import com.shortcut.dto.ResourceDtos.ResourceChangeResult;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class EventServiceResourceTest {

    private static final LocalDate SHOOT_DATE = LocalDate.of(2026, 10, 22);
    private static final CurrentUser PD = new CurrentUser("pd", "PRODUCER", "한서윤", "PRODUCTION");
    private static final ResourceChange DRONE_REPAIR =
            new ResourceChange("EQUIPMENT_UNAVAILABLE", 2L, "REPAIR", null, null, LocalDate.of(2026, 10, 25), "배터리 불량");

    private final PlanRepository plans = mock(PlanRepository.class);
    private final TaskRepository tasks = mock(TaskRepository.class);
    private final OutboxService outbox = mock(OutboxService.class);
    private final OverrideRepository overrides = mock(OverrideRepository.class);
    private final PlanDataService planData = mock(PlanDataService.class);
    private final SupersedeService supersede = mock(SupersedeService.class);
    private EventService events;

    @BeforeEach
    void setUp() {
        events = new EventService(plans, tasks, outbox, overrides, planData, supersede, new JsonColumns(new ObjectMapper()));
        given(plans.findShootDay(1L)).willReturn(Optional.of(
                new ShootDay(1, 1, "드라마", SHOOT_DATE, LocalTime.of(6, 30), 5, null, "[]", 1_000_000, 0)));
        given(planData.load(1L)).willReturn(data());
        given(tasks.insertEventIfAbsent(anyLong(), anyString(), anyString(), any(), anyInt(), anyString(), anyString()))
                .willReturn(Optional.of(30L));
        given(plans.bumpDataVersion(1L)).willReturn(6);
    }

    @Test
    void 패널을_연_뒤_데이터가_바뀌었으면_409다() {
        ResourceChangeRequest request = new ResourceChangeRequest(1L, 4, false, List.of(DRONE_REPAIR), null);

        assertThatThrownBy(() -> events.applyResources(PD, request))
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).code()).isEqualTo("DATA_VERSION_CONFLICT");
        verify(overrides, never()).insert(anyLong(), anyLong(), anyString(), any(), any(), any(), any(), any());
    }

    @Test
    void 변경_권한이_없는_역할은_막는다() {
        CurrentUser dop = new CurrentUser("dop", "DOP", "문태오", "CAMERA");

        assertThatThrownBy(() -> events.applyResources(dop, new ResourceChangeRequest(1L, 5, false, List.of(DRONE_REPAIR), null)))
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).code()).isEqualTo("FORBIDDEN");
    }

    @Test
    void 적용_끝_날짜가_촬영일보다_빠르면_400이다() {
        ResourceChange past = new ResourceChange("EQUIPMENT_UNAVAILABLE", 2L, "BROKEN", null, null, SHOOT_DATE.minusDays(1), null);

        assertThatThrownBy(() -> events.applyResources(PD, new ResourceChangeRequest(1L, 5, false, List.of(past), null)))
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).code()).isEqualTo("INVALID_UNTIL");
    }

    @Test
    void 같은_장비의_이전_기록을_되돌리고_기간과_수리_여부를_저장한다() {
        DataOverride broken = override(12, "EQUIPMENT_UNAVAILABLE", 2L);
        given(overrides.find(1L)).willReturn(List.of(broken));

        ResourceChangeResult result = events.applyResources(PD, new ResourceChangeRequest(1L, 5, false, List.of(DRONE_REPAIR), null));

        InOrder order = inOrder(overrides, plans, supersede);
        order.verify(overrides).clear(12L, "pd");
        order.verify(overrides).insert(eq(1L), eq(30L), eq("EQUIPMENT_UNAVAILABLE"), eq(2L), eq(Map.of("status", "REPAIR")),
                eq(LocalDate.of(2026, 10, 25)), eq("배터리 불량"), eq("pd"));
        order.verify(plans).bumpDataVersion(1L);
        order.verify(supersede).supersedeOlder(eq(1L), eq(6), eq("드론 사용 불가(수리 중), 2026-10-25까지"));
        assertThat(result.taskId()).isNull();
        assertThat(result.dataVersion()).isEqualTo(6);
        verify(tasks, never()).insertTask(anyString(), any(), any(), any(), anyLong(), anyString(), anyString(), anyString());
    }

    @Test
    void 되돌리기만_하고_재계획을_요청하면_작업을_만든다() {
        given(overrides.find(1L)).willReturn(List.of(override(12, "EQUIPMENT_UNAVAILABLE", 2L)));
        given(tasks.insertTask(anyString(), isNull(), eq(30L), isNull(), eq(1L), eq("pd"), anyString(), anyString())).willReturn(40L);
        AiTask task = mock(AiTask.class);
        given(tasks.findTask(40L)).willReturn(Optional.of(task));

        ResourceChangeResult result = events.applyResources(PD, new ResourceChangeRequest(1L, 5, true, null, List.of(12L)));

        assertThat(result.taskId()).isEqualTo(40L);
        verify(overrides).clear(12L, "pd");
        verify(tasks).insertEventIfAbsent(eq(1L), eq("OTHER"), eq("드론 정상으로 되돌림"), isNull(), eq(5), eq("1|RESOURCE|5"), eq("pd"));
        verify(outbox).agentStart(task);
    }

    @Test
    void 이미_되돌린_기록은_되돌릴_수_없다() {
        given(overrides.find(1L)).willReturn(List.of());

        assertThatThrownBy(() -> events.applyResources(PD, new ResourceChangeRequest(1L, 5, false, null, List.of(99L))))
                .isInstanceOf(ApiException.class)
                .extracting(e -> ((ApiException) e).code()).isEqualTo("UNKNOWN_OVERRIDE");
    }

    private static DataOverride override(long id, String kind, long target) {
        return new DataOverride(id, 1, 24L, kind, target, JsonNodeFactory.instance.objectNode(), SHOOT_DATE, null, null, "pd",
                OffsetDateTime.now());
    }

    private static PlanData data() {
        Location seongsu = new Location(2, "성수 스튜디오", "서울 성동구", true, "서울 성동구", LocalTime.of(9, 0), LocalTime.of(22, 0),
                null, null, 300_000, false, 0.8, 14, null, true);
        return new PlanData(
                new ShootDay(1, 1, "드라마", SHOOT_DATE, LocalTime.of(6, 30), 5, null, "[]", 1_000_000, 0),
                List.of(new Block("PM", LocalTime.of(14, 0), LocalTime.of(16, 0), 120, 2L, List.of(1L))),
                List.of(),
                Map.of(1L, new Actor(1, "배우 A", LocalTime.of(9, 0), LocalTime.of(18, 0), 30, "contract-a", false, null, null)),
                Map.of(2L, seongsu),
                Map.of(1L, new Equipment(1, "카메라 패키지 A", true, false, 150_000), 2L, new Equipment(2, "드론", true, true, 100_000)),
                List.of(), List.of(), List.of(), List.of(), null);
    }
}
