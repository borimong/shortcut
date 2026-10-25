package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.DataOverride;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.domain.WeatherHour;
import com.shortcut.repository.OverrideRepository;
import com.shortcut.repository.PlanRepository;
import com.shortcut.repository.ScheduleRepository;
import com.shortcut.repository.SettingsRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PlanDataServiceWeatherTest {

    private static final AppSettings LIVE = AppSettings.DEFAULT;
    private static final AppSettings SEED = new AppSettings(5, 5.0, 1.0, 3, AppSettings.SEED, false, false, null, null);
    private static final OffsetDateTime FETCHED = OffsetDateTime.parse("2026-10-22T09:00:00+09:00");

    private final PlanRepository plans = mock(PlanRepository.class);
    private final OverrideRepository overrides = mock(OverrideRepository.class);
    private final SettingsRepository settings = mock(SettingsRepository.class);
    private final ScheduleRepository schedules = mock(ScheduleRepository.class);
    private final PlanDataService service = new PlanDataService(plans, overrides, settings, schedules);

    @BeforeEach
    void setUp() {
        given(plans.findShootDay(1L)).willReturn(Optional.of(
                new ShootDay(1, 1, "드라마", LocalDate.of(2026, 10, 22), LocalTime.of(6, 30), 5, null, "[]", 1_000_000, 0)));
        given(plans.findLocations()).willReturn(List.of(new Location(1, "한강 공원", "서울 영등포구", false, "서울 영등포구",
                LocalTime.of(6, 0), LocalTime.of(22, 0), null, null, 300_000, false, 0.95, 6, null, true)));
        given(plans.findWeather(1L, AppSettings.LIVE)).willReturn(List.of(
                new WeatherHour(1, 12, 0.0), new WeatherHour(1, 13, 0.0), new WeatherHour(1, 14, 0.0)));
        given(plans.findLiveForecastTimes(1L)).willReturn(Map.of(1L, FETCHED));
    }

    @Test
    void 사람이_입력한_강수량이_날씨_API_예보보다_우선한다() throws Exception {
        given(settings.settings()).willReturn(LIVE);
        given(overrides.find(1L)).willReturn(List.of(new DataOverride(9, 1, 30L, "RAIN_FORECAST", 1L,
                new ObjectMapper().readTree("{\"fromHour\": 13, \"toHour\": 14, \"mm\": 8.0}"),
                null, null, null, "pd", FETCHED)));

        PlanData data = service.load(1L);

        assertThat(data.hourly(1)).containsExactly(Map.entry(12, 0.0), Map.entry(13, 8.0), Map.entry(14, 8.0));
        assertThat(data.forecast().manualLocations()).containsExactly(1L);
        assertThat(data.forecast().liveFetchedAt()).containsEntry(1L, FETCHED);
    }

    @Test
    void 시드_예보를_고르면_시드_행만_읽고_갱신_시각을_보지_않는다() {
        given(settings.settings()).willReturn(SEED);
        given(plans.findWeather(1L, AppSettings.SEED)).willReturn(List.of(new WeatherHour(1, 13, 8.0)));
        given(overrides.find(1L)).willReturn(List.of());

        PlanData data = service.load(1L);

        assertThat(data.hourly(1)).containsExactly(Map.entry(13, 8.0));
        assertThat(data.forecast().liveFetchedAt()).isEmpty();
        verify(plans, never()).findLiveForecastTimes(anyLong());
        verify(plans, never()).findWeather(1L, AppSettings.LIVE);
    }
}
