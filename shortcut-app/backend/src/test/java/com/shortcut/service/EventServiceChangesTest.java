package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.common.JsonColumns;
import com.shortcut.domain.Actor;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Block;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.ResourceDtos.ResourceChange;
import com.shortcut.dto.ResourceDtos.ResourceChangeRequest;
import com.shortcut.dto.TaskDtos.ChangeItem;
import com.shortcut.dto.TaskDtos.EventRequest;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.TaskRepository;
import com.shortcut.security.CurrentUser;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/**
 * 변경 입력이 이벤트 changes 컬럼과 중복 키에 남기는 JSON 모양, 덮어쓰기에 저장하는 값을 고정한다.
 * Agent와 변동 이력이 이 JSON을 읽으므로 키 이름과 순서가 바뀌면 안 된다.
 */
class EventServiceChangesTest {

    private static final LocalDate SHOOT_DATE = LocalDate.of(2026, 10, 22);
    private static final CurrentUser PD = new CurrentUser("pd", "PRODUCER", "한서윤", "PRODUCTION");

    private final PlanRepository plans = mock(PlanRepository.class);
    private final TaskRepository tasks = mock(TaskRepository.class);
    private final OverrideRepository overrides = mock(OverrideRepository.class);
    private final PlanDataService planData = mock(PlanDataService.class);
    private EventService events;

    @BeforeEach
    void setUp() {
        events = new EventService(plans, tasks, mock(OutboxService.class), overrides, planData, mock(SupersedeService.class),
                new JsonColumns(new ObjectMapper()));
        given(plans.findShootDay(1L)).willReturn(Optional.of(shootDay()));
        given(planData.load(1L)).willReturn(data());
        given(tasks.insertEventIfAbsent(anyLong(), anyString(), anyString(), any(), anyInt(), anyString(), anyString()))
                .willReturn(Optional.of(30L));
        given(tasks.insertTask(anyString(), any(), anyLong(), any(), anyLong(), anyString(), anyString(), anyString()))
                .willReturn(40L);
        given(tasks.findTask(40L)).willReturn(Optional.of(mock(AiTask.class)));
        given(plans.bumpDataVersion(1L)).willReturn(6);
    }

    @Test
    void 변경_종류마다_저장하는_JSON과_중복_키가_같다() {
        List<ChangeItem> changes = List.of(
                new ChangeItem("EQUIPMENT_UNAVAILABLE", 2L, null, null, null, null, null, null, null),
                new ChangeItem("ACTOR_ABSENT", 1L, null, null, null, null, null, null, null),
                new ChangeItem("ACTOR_WINDOW", 1L, LocalTime.of(9, 0), LocalTime.of(15, 0), null, null, null, null, null),
                new ChangeItem("LOCATION_UNAVAILABLE", 2L, null, null, null, null, null, null, null),
                new ChangeItem("RAIN_FORECAST", 2L, null, null, 13, 15, 7.5, null, null),
                new ChangeItem("DISASTER_ALERT", null, LocalTime.of(13, 0), LocalTime.of(18, 0), null, null, null,
                        " 서울 성동구 ", " 호우 경보 "));

        events.create(PD, new EventRequest("OTHER", " 여러 변경 ", null, 1L, changes));

        String expected = "["
                + "{\"kind\":\"EQUIPMENT_UNAVAILABLE\",\"targetId\":2,\"summary\":\"드론 사용 불가(고장)\"},"
                + "{\"kind\":\"ACTOR_ABSENT\",\"targetId\":1,\"summary\":\"배우 A 오늘 촬영 불참\"},"
                + "{\"kind\":\"ACTOR_WINDOW\",\"targetId\":1,\"from\":\"09:00\",\"to\":\"15:00\","
                + "\"summary\":\"배우 A 가용 시간 09:00~15:00로 변경\"},"
                + "{\"kind\":\"LOCATION_UNAVAILABLE\",\"targetId\":2,\"summary\":\"성수 스튜디오 사용 불가(취소)\"},"
                + "{\"kind\":\"RAIN_FORECAST\",\"targetId\":2,\"fromHour\":13,\"toHour\":15,\"mm\":7.5,"
                + "\"summary\":\"성수 스튜디오 13~15시 시간당 7.5mm 비\"},"
                + "{\"kind\":\"DISASTER_ALERT\",\"region\":\"서울 성동구\",\"alertKind\":\"호우 경보\",\"from\":\"13:00\","
                + "\"to\":\"18:00\",\"summary\":\"서울 성동구 호우 경보 13:00~18:00\"}"
                + "]";
        verify(tasks).updateEventChanges(30L, expected);
        verify(tasks).insertEventIfAbsent(1L, "OTHER", "여러 변경", null, 5, "1|OTHER|여러 변경|" + expected + "|5", "pd");

        verify(overrides).insert(1L, 30L, "EQUIPMENT_UNAVAILABLE", 2L, Map.of(), null, null, "pd");
        verify(overrides).insert(1L, 30L, "ACTOR_WINDOW", 1L, Map.of("from", "00:00", "to", "00:00"), null, null, "pd");
        verify(overrides).insert(1L, 30L, "ACTOR_WINDOW", 1L, Map.of("from", "09:00", "to", "15:00"), null, null, "pd");
        verify(overrides).insert(1L, 30L, "LOCATION_UNAVAILABLE", 2L, Map.of(), null, null, "pd");
        verify(overrides).insert(1L, 30L, "RAIN_FORECAST", 2L, Map.of("fromHour", 13, "toHour", 15, "mm", 7.5), null, null, "pd");
        verify(plans).insertAlert(SHOOT_DATE, "서울 성동구", "호우 경보", LocalTime.of(13, 0), LocalTime.of(18, 0),
                "서울 성동구 호우 경보");
    }

    @Test
    void 자원_패널은_상태_기간_메모를_요약_뒤에_붙인다() {
        ResourceChange drone = new ResourceChange("EQUIPMENT_UNAVAILABLE", 2L, "REPAIR", null, null,
                LocalDate.of(2026, 10, 25), " 배터리 불량 ");
        ResourceChange actor = new ResourceChange("ACTOR_WINDOW", 1L, null, LocalTime.of(10, 0), LocalTime.of(14, 0), null, null);

        events.applyResources(PD, new ResourceChangeRequest(1L, 5, false, List.of(drone, actor), null));

        ArgumentCaptor<String> json = ArgumentCaptor.forClass(String.class);
        verify(tasks).updateEventChanges(eq(30L), json.capture());
        assertThat(json.getValue()).isEqualTo("["
                + "{\"kind\":\"EQUIPMENT_UNAVAILABLE\",\"targetId\":2,\"summary\":\"드론 사용 불가(수리 중), 2026-10-25까지\","
                + "\"status\":\"REPAIR\",\"untilDate\":\"2026-10-25\",\"memo\":\"배터리 불량\"},"
                + "{\"kind\":\"ACTOR_WINDOW\",\"targetId\":1,\"from\":\"10:00\",\"to\":\"14:00\","
                + "\"summary\":\"배우 A 가용 시간 10:00~14:00로 변경\"}"
                + "]");
        verify(overrides).insert(1L, 30L, "EQUIPMENT_UNAVAILABLE", 2L, Map.of("status", "REPAIR"),
                LocalDate.of(2026, 10, 25), "배터리 불량", "pd");
        verify(overrides).insert(1L, 30L, "ACTOR_WINDOW", 1L, Map.of("from", "10:00", "to", "14:00"), null, null, "pd");
    }

    private static ShootDay shootDay() {
        return new ShootDay(1, 1, "드라마", SHOOT_DATE, LocalTime.of(6, 30), 5, null, "[]", 1_000_000, 0);
    }

    private static PlanData data() {
        Location seongsu = new Location(2, "성수 스튜디오", "서울 성동구", true, "서울 성동구", LocalTime.of(9, 0),
                LocalTime.of(22, 0), null, null, 300_000, false, 0.8, 14, null, true);
        return new PlanData(shootDay(),
                List.of(new Block("PM", LocalTime.of(14, 0), LocalTime.of(16, 0), 120, 2L, List.of(1L))),
                List.of(),
                Map.of(1L, new Actor(1, "배우 A", LocalTime.of(9, 0), LocalTime.of(18, 0), 30, "contract-a", false, null, null)),
                Map.of(2L, seongsu),
                Map.of(2L, new Equipment(2, "드론", true, true, 100_000)),
                List.of(), List.of(), List.of(), List.of(), null);
    }
}
