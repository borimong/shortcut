package com.shortcut.common;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** 괄호 조사 대신 앞말 받침에 맞는 조사를 붙이는지 본다. 한글은 받침, 숫자와 영문은 읽는 소리로 가른다. */
class JosaTest {

    @Test
    void 한글은_마지막_글자의_받침으로_고른다() {
        assertThat(Josa.eunNeun("성수 스튜디오")).isEqualTo("성수 스튜디오는");
        assertThat(Josa.eunNeun("파주 세트장")).isEqualTo("파주 세트장은");
        assertThat(Josa.eulReul("반사판")).isEqualTo("반사판을");
        assertThat(Josa.eulReul("드론")).isEqualTo("드론을");
        assertThat(Josa.eulReul("짐벌 세트")).isEqualTo("짐벌 세트를");
        assertThat(Josa.iGa("한강 공원")).isEqualTo("한강 공원이");
        assertThat(Josa.gwaWa("배우 B 일정")).isEqualTo("배우 B 일정과");
        assertThat(Josa.euroRo("성수 스튜디오")).isEqualTo("성수 스튜디오로");
        assertThat(Josa.euroRo("파주 세트장")).isEqualTo("파주 세트장으로");
        assertThat(Josa.euroRo("합정 루프탑 야외 테이블")).isEqualTo("합정 루프탑 야외 테이블로");
        assertThat(Josa.euroRo("서울")).isEqualTo("서울로");
    }

    @Test
    void 숫자와_영문은_읽는_소리로_고른다() {
        assertThat(Josa.eunNeun("S18, S19")).isEqualTo("S18, S19는");
        assertThat(Josa.eunNeun("S12, S13")).isEqualTo("S12, S13은");
        assertThat(Josa.eunNeun("S18")).isEqualTo("S18은");
        assertThat(Josa.euroRo("콜시트 v1")).isEqualTo("콜시트 v1로");
        assertThat(Josa.euroRo("콜시트 v3")).isEqualTo("콜시트 v3으로");
        assertThat(Josa.iGa("확정 콜시트 v2")).isEqualTo("확정 콜시트 v2가");
        assertThat(Josa.iGa("확정 콜시트 v10")).isEqualTo("확정 콜시트 v10이");
        assertThat(Josa.eunNeun("배우 A")).isEqualTo("배우 A는");
        assertThat(Josa.iGa("배우 C")).isEqualTo("배우 C가");
        assertThat(Josa.eunNeun("카메라 패키지 L")).isEqualTo("카메라 패키지 L은");
        assertThat(Josa.euroRo("구역 L")).isEqualTo("구역 L로");
        assertThat(Josa.eunNeun("12mm")).isEqualTo("12mm는");
        assertThat(Josa.eunNeun("150,000")).isEqualTo("150,000은");
    }

    @Test
    void 끝이_괄호면_괄호_앞말로_고른다() {
        assertThat(Josa.gwaWa("배우 B 일정(18:30~21:00 광고와 행사)")).isEqualTo("배우 B 일정(18:30~21:00 광고와 행사)과");
        assertThat(Josa.eunNeun("「봄밤」")).isEqualTo("「봄밤」은");
    }
}
