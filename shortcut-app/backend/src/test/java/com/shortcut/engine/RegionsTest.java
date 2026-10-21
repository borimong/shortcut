package com.shortcut.engine;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class RegionsTest {

    @Test
    void 정식_이름과_공백_차이는_같은_지역으로_본다() {
        assertThat(Regions.normalize("서울특별시 영등포구")).isEqualTo("서울영등포구");
        assertThat(Regions.normalize(" 서울  영등포구 ")).isEqualTo("서울영등포구");
        assertThat(Regions.normalize("강원특별자치도 춘천시")).isEqualTo("강원춘천시");
        assertThat(Regions.covers("서울특별시 영등포구", "서울 영등포구")).isTrue();
        assertThat(Regions.covers("서울영등포구", "서울 영등포구")).isTrue();
    }

    @Test
    void 시도_단위_재난_문자는_그_안의_모든_장소에_걸린다() {
        assertThat(Regions.covers("서울", "서울 영등포구")).isTrue();
        assertThat(Regions.covers("경기도", "경기 파주시")).isTrue();
        assertThat(Regions.covers("서울 성동구", "서울 영등포구")).isFalse();
        assertThat(Regions.covers("광주광역시", "경기 광주시")).isFalse();
        assertThat(Regions.covers(" ", "서울 영등포구")).isFalse();
    }
}
