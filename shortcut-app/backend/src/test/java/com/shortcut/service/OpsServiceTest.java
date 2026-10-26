package com.shortcut.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.shortcut.common.ApiException;
import com.shortcut.domain.AppSettings;
import com.shortcut.domain.Block;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.ForecastInfo;
import com.shortcut.domain.Location;
import com.shortcut.domain.ShootDay;
import com.shortcut.dto.OpsDtos.LedgerEntryRequest;
import com.shortcut.dto.OpsDtos.OutgoingMessage;
import com.shortcut.dto.OpsDtos.LedgerRequest;
import com.shortcut.dto.OpsDtos.LedgerResult;
import com.shortcut.dto.OpsDtos.PermitApplyRequest;
import com.shortcut.dto.OpsDtos.PermitResult;
import com.shortcut.dto.OpsDtos.Replies;
import com.shortcut.dto.OpsDtos.SendRequest;
import com.shortcut.dto.OpsDtos.SendResult;
import com.shortcut.dto.OpsDtos.TransportQuote;
import com.shortcut.dto.OpsDtos.TransportQuoteRequest;
import com.shortcut.dto.OpsDtos.VenueCancelResult;
import com.shortcut.dto.OpsDtos.VenueHoldRequest;
import com.shortcut.dto.OpsDtos.VenueHoldResult;
import com.shortcut.repository.OpsRepository;
import com.shortcut.repository.OpsRepository.LedgerRow;
import com.shortcut.repository.OpsRepository.MessageRow;
import com.shortcut.repository.OpsRepository.RentalRow;
import com.shortcut.repository.OpsRepository.ReservationRow;
import com.shortcut.repository.UserRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/**
 * 실행팀 가상 외부 서비스의 판단(가예약 충돌, 멱등, 취소 수수료, 장부 금액, 허가 반려, 자동 응답)을 고정한다.
 */
class OpsServiceTest {

    private static final long DAY = 1L;
    private static final LocalTime T14 = LocalTime.of(14, 0);
    private static final LocalTime T16 = LocalTime.of(16, 0);

    private final OpsRepository ops = mock(OpsRepository.class);
    private final PlanDataService planData = mock(PlanDataService.class);
    private OpsService service;

    @BeforeEach
    void setUp() {
        service = new OpsService(ops, planData, mock(UserRepository.class), mock(NotificationService.class));
        given(planData.load(DAY)).willReturn(data(false, false));
        given(ops.findReservations(DAY)).willReturn(List.of());
        given(ops.findLedger(DAY)).willReturn(List.of());
        given(ops.upsertLedger(any())).willAnswer(call -> {
            LedgerRow row = call.getArgument(0);
            return new LedgerRow(1, row.shootDayId(), row.taskId(), row.account(), row.memo(), row.amountKrw(),
                    row.refType(), row.refId());
        });
    }

    // ---------------------------------------------------------------- 장소

    @Test
    void 충돌_스위치가_켜지면_가예약이_409다() {
        given(planData.load(DAY)).willReturn(data(true, false));

        assertThatThrownBy(() -> service.holdVenue(new VenueHoldRequest(DAY, 7L, 2L, T14, T16)))
                .isInstanceOf(ApiException.class)
                .extracting("code").isEqualTo("VENUE_CONFLICT");
        verify(ops, never()).insertReservation(any());
    }

    @Test
    void 시간대를_덮는_기존_예약이_있으면_새로_만들지_않고_그_예약을_돌려준다() {
        given(ops.findReservations(DAY)).willReturn(List.of(
                new ReservationRow("R-2031", DAY, 2L, T14, LocalTime.of(18, 0), "HELD", "OURPLACE", null, 0, 0)));

        VenueHoldResult first = service.holdVenue(new VenueHoldRequest(DAY, 7L, 2L, T14, T16));
        VenueHoldResult second = service.holdVenue(new VenueHoldRequest(DAY, 7L, 2L, T14, T16));

        assertThat(first.reservationId()).isEqualTo("R-2031");
        assertThat(second.reservationId()).isEqualTo("R-2031");
        verify(ops, never()).insertReservation(any());
    }

    @Test
    void 기존_예약이_없으면_가상_아워플레이스_가예약을_새로_만든다() {
        given(ops.nextReservationId()).willReturn("R-3001");

        VenueHoldResult result = service.holdVenue(new VenueHoldRequest(DAY, 7L, 2L, T14, T16));

        ArgumentCaptor<ReservationRow> saved = ArgumentCaptor.forClass(ReservationRow.class);
        verify(ops).insertReservation(saved.capture());
        assertThat(result).isEqualTo(new VenueHoldResult("R-3001", "HELD", 450_000));
        assertThat(saved.getValue().provider()).isEqualTo(OpsService.MOCK_PROVIDER);
        assertThat(saved.getValue().costKrw()).isEqualTo(450_000);
    }

    @Test
    void 확정은_취소된_예약에_409다() {
        given(ops.findReservation("R-1")).willReturn(Optional.of(reservation("R-1", "CANCELLED", 450_000)));

        assertThatThrownBy(() -> service.confirmVenue("R-1"))
                .isInstanceOf(ApiException.class)
                .extracting("code").isEqualTo("INVALID_STATE");
    }

    @Test
    void 가예약을_확정한다() {
        given(ops.findReservation("R-1")).willReturn(Optional.of(reservation("R-1", "HELD", 0)));

        VenueHoldResult result = service.confirmVenue("R-1");

        assertThat(result).isEqualTo(new VenueHoldResult("R-1", "CONFIRMED", 450_000));
        verify(ops).updateReservation("R-1", "CONFIRMED", null, 450_000, 0);
    }

    @Test
    void 취소_수수료는_확정된_예약에만_장소비의_10퍼센트다() {
        given(ops.findReservation("R-1")).willReturn(Optional.of(reservation("R-1", "CONFIRMED", 450_000)));
        given(ops.findReservation("R-2")).willReturn(Optional.of(reservation("R-2", "HELD", 450_000)));

        VenueCancelResult confirmed = service.cancelVenue("R-1");
        VenueCancelResult held = service.cancelVenue("R-2");

        assertThat(confirmed.cancelFeeKrw()).isEqualTo(45_000);
        assertThat(held.cancelFeeKrw()).isZero();
    }

    // ---------------------------------------------------------------- 장부

    @Test
    void 장부_금액은_요청이_아니라_예약_행에서_읽는다() {
        given(ops.findReservation("R-1")).willReturn(Optional.of(reservation("R-1", "CONFIRMED", 450_000)));

        LedgerResult result = service.recordLedger(new LedgerRequest(DAY, 7L,
                List.of(new LedgerEntryRequest("VENUE", "우천으로 옮긴 성수 스튜디오 대관료", "RESERVATION", "R-1"))));

        assertThat(result.entries().get(0).amountKrw()).isEqualTo(450_000);
        assertThat(result.totalKrw()).isEqualTo(450_000);
        assertThat(result.budget().capKrw()).isEqualTo(1_000_000);
    }

    @Test
    void 계정과_대상_종류가_맞지_않으면_400이다() {
        assertThatThrownBy(() -> service.recordLedger(new LedgerRequest(DAY, 7L,
                List.of(new LedgerEntryRequest("VENUE", "장비", "RENTAL", "RB-1001")))))
                .isInstanceOf(ApiException.class)
                .extracting("code").isEqualTo("VALIDATION_FAILED");
        verify(ops, never()).upsertLedger(any());
    }

    @Test
    void 취소되지_않은_예약에는_취소_수수료를_기록할_수_없다() {
        given(ops.findReservation("R-1")).willReturn(Optional.of(reservation("R-1", "CONFIRMED", 450_000)));

        assertThatThrownBy(() -> service.recordLedger(new LedgerRequest(DAY, 7L,
                List.of(new LedgerEntryRequest("CANCEL_FEE", "취소", "RESERVATION", "R-1")))))
                .isInstanceOf(ApiException.class)
                .extracting("code").isEqualTo("INVALID_STATE");
    }

    @Test
    void 취소된_예약은_취소_수수료를_그_행에서_읽는다() {
        ReservationRow cancelled = new ReservationRow("R-1", DAY, 2L, T14, T16, "CANCELLED", "OURPLACE_MOCK", 7L, 450_000, 45_000);
        given(ops.findReservation("R-1")).willReturn(Optional.of(cancelled));

        LedgerResult result = service.recordLedger(new LedgerRequest(DAY, 7L,
                List.of(new LedgerEntryRequest("CANCEL_FEE", "장소 변경으로 낸 취소 수수료", "RESERVATION", "R-1"))));

        assertThat(result.entries().get(0).amountKrw()).isEqualTo(45_000);
    }

    // ---------------------------------------------------------------- 허가

    @Test
    void 반려_스위치가_켜지면_허가가_반려된다() {
        given(planData.load(DAY)).willReturn(data(false, true));
        given(ops.findPermits(DAY)).willReturn(List.of());
        given(ops.nextPermitId()).willReturn("PM-1001");

        PermitResult result = service.applyPermit(new PermitApplyRequest(DAY, 7L, 1L, T14, T16, "LOCATION"));

        assertThat(result.status()).isEqualTo("DENIED");
        assertThat(result.feeKrw()).isZero();
        assertThat(result.denialReason()).isNotBlank();
    }

    @Test
    void 허가_시간대_밖이면_반려되고_안이면_승인된다() {
        given(ops.findPermits(DAY)).willReturn(List.of());
        given(ops.nextPermitId()).willReturn("PM-1001", "PM-1002");

        PermitResult late = service.applyPermit(new PermitApplyRequest(DAY, 7L, 1L, LocalTime.of(16, 0), LocalTime.of(18, 0), "LOCATION"));
        PermitResult ok = service.applyPermit(new PermitApplyRequest(DAY, 7L, 1L, T14, T16, "LOCATION"));

        assertThat(late.status()).isEqualTo("DENIED");
        assertThat(ok.status()).isEqualTo("APPROVED");
        assertThat(ok.feeKrw()).isEqualTo(50_000);
    }

    // ---------------------------------------------------------------- 이동, 연락

    @Test
    void 차량_견적은_오전_장소에서_출발하고_이동_시간만큼_앞당겨_출발한다() {
        given(ops.findTransports(DAY)).willReturn(List.of());

        TransportQuote quote = service.quoteTransport(new TransportQuoteRequest(DAY, 2L, T14, 20, List.of(1L, 2L, 3L, 4L)));

        assertThat(quote.pickup()).isEqualTo("목동 오피스 세트");
        assertThat(quote.travelMinutes()).isEqualTo(38);
        assertThat(quote.departAt()).isEqualTo(LocalTime.of(12, 52));
        assertThat(quote.options()).extracting("vehicle").contains("TRUCK_1T");
        assertThat(quote.recommended().vehicle()).isEqualTo("BUS_25");
    }

    @Test
    void 시각과_장소가_적힌_안내는_확인으로_빠진_안내는_질문으로_답한다() {
        given(ops.findMessagesByTask(7L)).willReturn(List.of(
                new MessageRow(1, DAY, 7L, "USER:ad1", "윤하린", "1조감독", "APP",
                        "13:30 목동 오피스 세트 집결 후 성수 스튜디오로 이동합니다", "SENT", null),
                new MessageRow(2, DAY, 7L, "ACTOR:1", "배우 A", "배우", "SMS", "장소가 바뀌었습니다", "SENT", null)));

        Replies replies = service.replies(7L);

        assertThat(replies.sent()).isEqualTo(2);
        assertThat(replies.acked()).isEqualTo(1);
        assertThat(replies.questions()).extracting("recipientId").containsExactly("ACTOR:1");
        verify(ops).updateMessageReply(eq(1L), eq("ACKED"), anyString());
        verify(ops).updateMessageReply(eq(2L), eq("QUESTION"), eq(OpsService.QUESTION_REPLY));
    }

    @Test
    void 같은_라운드에서_이미_보낸_사람에게는_문장이_달라도_다시_보내지_않는다() {
        given(ops.findRentals(DAY)).willReturn(List.of(bookedRental()));
        MessageRow sent = new MessageRow(5, DAY, 7L, "VENDOR:rental", "가상 렌탈사", "장비 업체", "EMAIL",
                "14:00까지 성수 스튜디오로 장비를 보내 주세요", "SENT", null);
        // 재시도에서 LLM이 같은 내용을 다른 문장으로 다시 썼다.
        String rewritten = "성수 스튜디오에 14시 전까지 장비 도착 부탁드립니다";
        given(ops.findMessage(7L, "VENDOR:rental", 1, rewritten)).willReturn(Optional.of(sent));

        SendResult result = service.send(new SendRequest(DAY, 7L, List.of(new OutgoingMessage("VENDOR:rental", rewritten)), 1));

        assertThat(result.sent()).extracting("messageId").containsExactly(5L);
        verify(ops, never()).insertMessage(any(), any());
    }

    @Test
    void 다음_라운드의_정정_안내는_새로_보내고_라운드를_남긴다() {
        given(ops.findRentals(DAY)).willReturn(List.of(bookedRental()));
        given(ops.insertMessage(any(), eq(2))).willReturn(9L);

        SendResult result = service.send(new SendRequest(DAY, 7L,
                List.of(new OutgoingMessage("VENDOR:rental", "도착 시각이 13:30으로 바뀌었습니다")), 2));

        assertThat(result.sent()).extracting("messageId").containsExactly(9L);
        verify(ops).findMessage(7L, "VENDOR:rental", 2, "도착 시각이 13:30으로 바뀌었습니다");
        verify(ops).insertMessage(any(), eq(2));
    }

    // ---------------------------------------------------------------- 시드

    private static RentalRow bookedRental() {
        return new RentalRow("RT-1", DAY, 7L, List.of(1L), T14, T16, "BOOKED", 0, LocalTime.of(13, 0), 0);
    }

    private static ReservationRow reservation(String id, String status, long cost) {
        return new ReservationRow(id, DAY, 2L, T14, T16, status, "OURPLACE_MOCK", 7L, cost, 0);
    }

    private static PlanData data(boolean venueConflict, boolean permitDenied) {
        ShootDay day = new ShootDay(DAY, 1, "드라마", LocalDate.of(2026, 10, 22), LocalTime.of(6, 30), 1, null, "[]",
                1_000_000, 40);
        Location hangang = new Location(1, "한강 공원", "서울 영등포구", false, "서울 영등포구", LocalTime.of(6, 0),
                LocalTime.of(22, 0), LocalTime.of(9, 0), LocalTime.of(17, 0), 300_000, false, 0.95, 6, null, true);
        Location seongsu = new Location(2, "성수 스튜디오", "서울 성동구", true, "서울 성동구", LocalTime.of(14, 0),
                LocalTime.of(18, 0), null, null, 450_000, false, 0.8, 14, null, true);
        Location mokdong = new Location(4, "목동 오피스 세트", "서울 양천구", true, "서울 양천구", LocalTime.of(6, 0),
                LocalTime.of(13, 0), null, null, 0, false, 1.0, 0, null, true);
        List<Block> blocks = List.of(
                new Block("AM", LocalTime.of(7, 0), LocalTime.of(11, 30), 270, 4L, List.of(1L)),
                new Block("PM", LocalTime.of(13, 0), LocalTime.of(15, 0), 120, 1L, List.of(1L, 2L, 3L)));
        Map<Long, Equipment> equipment = Map.of(
                1L, new Equipment(1, "카메라 패키지 A", true, false, 0),
                4L, new Equipment(4, "추가 조명 패키지", true, false, 250_000));
        AppSettings settings = new AppSettings(5, 5.0, 1.0, 3, AppSettings.LIVE, venueConflict, permitDenied, null, null);
        return new PlanData(day, blocks, List.of(), Map.of(), Map.of(1L, hangang, 2L, seongsu, 4L, mokdong), equipment,
                List.of(), List.of(), ForecastInfo.NONE, List.of(), List.of(), settings);
    }
}
