package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.ForecastInfo;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.dto.AdminDtos.WeatherRefreshResult;
import com.shortcut.dto.BoardDtos.ForecastView;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.SettingsRepository;
import com.shortcut.repository.WeatherRepository;
import com.shortcut.repository.WeatherRepository.Target;
import com.shortcut.service.OpenMeteoClient.Point;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.client.ResourceAccessException;

class WeatherForecastServiceTest {

    private static final ZonedDateTime NOW = ZonedDateTime.of(2026, 10, 22, 9, 0, 0, 0, ZoneId.of("Asia/Seoul"));
    private static final LocalDate DAY1 = NOW.toLocalDate();
    private static final LocalDate DAY2 = DAY1.plusDays(1);
    private static final AppSettings SEED = new AppSettings(5, 5.0, 1.0, 3, AppSettings.SEED, null, null);
    private static final AppSettings LIVE = AppSettings.DEFAULT;
    private static final Location HANGANG = new Location(1, "한강 공원", "서울 영등포구 여의도 한강공원", false, "서울 영등포구",
            LocalTime.of(6, 0), LocalTime.of(22, 0), LocalTime.of(9, 0), LocalTime.of(17, 0), 300_000, false, 0.95, 6,
            null, true);
    private static final Target HANGANG_DAY1 = new Target(1, DAY1, 1, "한강 공원", 37.5283, 126.9326);
    private static final Target HANGANG_DAY2 = new Target(2, DAY2, 1, "한강 공원", 37.5283, 126.9326);

    private final WeatherRepository weather = mock(WeatherRepository.class);
    private final OpenMeteoClient client = mock(OpenMeteoClient.class);
    private final PlanDataService planData = mock(PlanDataService.class);
    private final PlanRepository plans = mock(PlanRepository.class);
    private final SupersedeService supersede = mock(SupersedeService.class);
    private final SettingsRepository settings = mock(SettingsRepository.class);
    private WeatherForecastService service;

    @BeforeEach
    void setUp() {
        service = new WeatherForecastService(weather, client, planData, plans, supersede, settings,
                new TransactionTemplate(mock(PlatformTransactionManager.class)),
                new ShortcutProperties(null, null, null, new ShortcutProperties.Weather("http://open-meteo.test", "", true)));
        given(weather.targets(DAY1, DAY1.plusDays(15))).willReturn(List.of(HANGANG_DAY1, HANGANG_DAY2));
    }

    @Test
    void 촬영일마다_6시부터_21시까지_LIVE_예보로_저장한다() {
        given(client.hourlyPrecip(List.of(new Point(37.5283, 126.9326)), DAY1, DAY2))
                .willReturn(List.of(Map.of(DAY1, allDay(0.0), DAY2, allDay(1.5))));
        given(planData.load(anyLong())).willReturn(data(SEED, Map.of(), Map.of()));

        WeatherRefreshResult result = service.refresh(NOW, null);

        verify(weather).saveLive(eq(1L), eq(1L), argThat(h -> h.size() == 16 && h.containsKey(6) && h.containsKey(21)
                && !h.containsKey(22)), eq(NOW.toOffsetDateTime()));
        verify(weather).saveLive(eq(2L), eq(1L), argThat(h -> h.get(13) == 1.5), eq(NOW.toOffsetDateTime()));
        assertThat(result.updated()).isEqualTo(2);
        assertThat(result.failed()).isEmpty();
        verify(plans, never()).bumpDataVersion(anyLong());
    }

    @Test
    void API가_실패하면_마지막_예보를_건드리지_않는다() {
        given(client.hourlyPrecip(any(), any(), any())).willThrow(new ResourceAccessException("connect timed out"));

        WeatherRefreshResult result = service.refresh(NOW, null);

        verify(weather, never()).saveLive(anyLong(), anyLong(), any(), any());
        assertThat(result.failed()).containsExactly("한강 공원");
    }

    @Test
    void 실시간_예보가_촬영_불가_기준을_넘으면_data_version을_올리고_대기_변경안을_무효로_돌린다() {
        given(weather.targets(DAY1, DAY1.plusDays(15))).willReturn(List.of(HANGANG_DAY1));
        given(client.hourlyPrecip(any(), any(), any())).willReturn(List.of(Map.of(DAY1, allDay(8.0))));
        OffsetDateTime earlier = NOW.minusHours(1).toOffsetDateTime();
        given(planData.load(1L)).willReturn(
                data(LIVE, Map.of(13, 0.0), Map.of(1L, earlier)),
                data(LIVE, Map.of(13, 8.0), Map.of(1L, NOW.toOffsetDateTime())));
        given(plans.bumpDataVersion(1L)).willReturn(7);

        WeatherRefreshResult result = service.refresh(NOW, null);

        verify(supersede).supersedeOlder(eq(1L), eq(7), contains("한강 공원"));
        assertThat(result.dataVersionBumped()).isEqualTo(1);
    }

    @Test
    void 처음_받은_장소는_비교하지_않고_data_version을_그대로_둔다() {
        given(weather.targets(DAY1, DAY1.plusDays(15))).willReturn(List.of(HANGANG_DAY1));
        given(client.hourlyPrecip(any(), any(), any())).willReturn(List.of(Map.of(DAY1, allDay(8.0))));
        given(planData.load(1L)).willReturn(
                data(LIVE, Map.of(13, 0.0), Map.of()),
                data(LIVE, Map.of(13, 8.0), Map.of(1L, NOW.toOffsetDateTime())));

        service.refresh(NOW, null);

        verify(plans, never()).bumpDataVersion(anyLong());
    }

    @Test
    void 기준_아래에서만_바뀌면_data_version을_그대로_둔다() {
        given(weather.targets(DAY1, DAY1.plusDays(15))).willReturn(List.of(HANGANG_DAY1));
        given(client.hourlyPrecip(any(), any(), any())).willReturn(List.of(Map.of(DAY1, allDay(2.0))));
        OffsetDateTime earlier = NOW.minusHours(1).toOffsetDateTime();
        given(planData.load(1L)).willReturn(
                data(LIVE, Map.of(13, 0.5), Map.of(1L, earlier)),
                data(LIVE, Map.of(13, 2.0), Map.of(1L, NOW.toOffsetDateTime())));

        service.refresh(NOW, null);

        verify(plans, never()).bumpDataVersion(anyLong());
    }

    @Test
    void 대체_장소를_등록한_직후에는_그_장소만_받고_data_version을_그대로_둔다() {
        given(settings.settings()).willReturn(LIVE);
        Target rooftop = new Target(1, DAY1, 105, "망원 루프탑", 37.556, 126.905);
        given(weather.targets(any(), any())).willReturn(List.of(HANGANG_DAY1, rooftop));
        given(client.hourlyPrecip(eq(List.of(new Point(37.556, 126.905))), any(), any()))
                .willReturn(List.of(Map.of(DAY1, allDay(0.2))));

        service.refreshRegistered(List.of(105L));

        verify(weather).saveLive(eq(1L), eq(105L), any(), any());
        verify(weather, never()).saveLive(anyLong(), eq(1L), any(), any());
        verify(planData, never()).load(anyLong());
    }

    @Test
    void 시드_예보를_쓰는_중에_대체_장소를_등록하면_API를_기다리지_않는다() {
        given(settings.settings()).willReturn(SEED);

        service.refreshRegistered(List.of(105L));

        verify(client, never()).hourlyPrecip(any(), any(), any());
    }

    @Test
    void 화면은_시드_실시간_예보_없음_오래된_예보와_현장_입력을_구분한다() {
        OffsetDateTime now = NOW.toOffsetDateTime();

        ForecastView seed = ShootDayQueryService.forecast(data(SEED, Map.of(), Map.of(1L, now)), 1, now);
        ForecastView none = ShootDayQueryService.forecast(data(LIVE, Map.of(), Map.of()), 1, now);
        ForecastView live = ShootDayQueryService.forecast(data(LIVE, Map.of(), Map.of(1L, now.minusMinutes(30))), 1, now);
        ForecastView stale = ShootDayQueryService.forecast(data(LIVE, Map.of(), Map.of(1L, now.minusHours(2))), 1, now);
        PlanData typed = new PlanData(data(LIVE, Map.of(), Map.of()).shootDay(), List.of(), List.of(), Map.of(),
                Map.of(1L, HANGANG), Map.of(), List.of(), List.of(), new ForecastInfo(Map.of(), Set.of(1L)), List.of(),
                List.of(), LIVE);

        assertThat(seed).isEqualTo(new ForecastView("SEED", null, false, false));
        assertThat(none).isEqualTo(new ForecastView("NONE", null, false, false));
        assertThat(live).isEqualTo(new ForecastView("LIVE", now.minusMinutes(30), false, false));
        assertThat(stale.stale()).isTrue();
        assertThat(ShootDayQueryService.forecast(typed, 1, now).manual()).isTrue();
    }

    private static Map<Integer, Double> allDay(double mm) {
        Map<Integer, Double> hourly = new TreeMap<>();
        for (int hour = 0; hour < 24; hour++) {
            hourly.put(hour, mm);
        }
        return hourly;
    }

    private static PlanData data(AppSettings settings, Map<Integer, Double> hourly, Map<Long, OffsetDateTime> fetchedAt) {
        List<WeatherHour> rows = hourly.entrySet().stream().map(e -> new WeatherHour(1, e.getKey(), e.getValue())).toList();
        return new PlanData(new ShootDay(1, 1, "드라마", DAY1, LocalTime.of(6, 30), 5, null, "[]", 1_000_000, 0),
                List.of(), List.of(), Map.of(), Map.of(1L, HANGANG), Map.of(), List.of(), rows,
                new ForecastInfo(fetchedAt, Set.of()), List.of(), List.of(), settings);
    }
}
