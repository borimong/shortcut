package com.shortcut.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.time.LocalTime;
import java.util.List;

/**
 * 실행팀 가상 외부 서비스(/internal/ops/**)의 요청과 응답이다. ops-mcp가 이 필드 이름(camelCase)을 그대로 쓴다.
 */
public final class OpsDtos {

    private OpsDtos() {
    }

    // ---------------------------------------------------------------- 장소

    public record ReservationView(String reservationId, long locationId, String locationName, LocalTime start,
                                  LocalTime end, String status) {
    }

    public record VenueAvailability(long locationId, String locationName, boolean indoor, boolean available,
                                    String reason, long priceKrw, List<ReservationView> reservations) {
    }

    public record VenueHoldRequest(@NotNull Long shootDayId, Long taskId, @NotNull Long locationId,
                                   @NotNull LocalTime start, @NotNull LocalTime end) {
    }

    public record VenueHoldResult(String reservationId, String status, long priceKrw) {
    }

    public record CancelRequest(@Size(max = 200) String reason) {
    }

    public record VenueCancelResult(String reservationId, String status, long cancelFeeKrw) {
    }

    // ---------------------------------------------------------------- 장비

    public record RentalQuoteRequest(@NotNull Long shootDayId, @NotEmpty @Size(max = 10) List<Long> equipmentIds,
                                     @NotNull LocalTime start, @NotNull LocalTime end) {
    }

    public record RentalItem(long equipmentId, String name, long priceKrw, boolean owned, boolean available) {
    }

    public record RentalBookingView(String bookingId, List<Long> equipmentIds, String status, long totalKrw) {
    }

    public record RentalQuote(List<RentalItem> items, long totalKrw, LocalTime deliveryAt, String vendor,
                              List<RentalBookingView> bookings) {
    }

    public record RentalBookRequest(@NotNull Long shootDayId, Long taskId, @NotEmpty @Size(max = 10) List<Long> equipmentIds,
                                    @NotNull LocalTime start, @NotNull LocalTime end) {
    }

    public record RentalBookResult(String bookingId, String status, long totalKrw, LocalTime deliveryAt) {
    }

    public record RentalCancelResult(String bookingId, String status, long cancelFeeKrw) {
    }

    // ---------------------------------------------------------------- 허가

    public record PermitWindow(LocalTime from, LocalTime to) {
    }

    public record PermitBrief(String permitId, String kind, String status) {
    }

    public record PermitRequirement(boolean required, List<String> kinds, String authority, long feeKrw,
                                    @JsonInclude(JsonInclude.Include.ALWAYS) PermitWindow permitWindow,
                                    boolean withinWindow, boolean noFlyZone, String reason, List<PermitBrief> permits) {
    }

    public record PermitApplyRequest(@NotNull Long shootDayId, Long taskId, @NotNull Long locationId,
                                     @NotNull LocalTime start, @NotNull LocalTime end,
                                     @NotNull @Pattern(regexp = "LOCATION|DRONE") String kind) {
    }

    public record PermitResult(String permitId, String kind, String status, long feeKrw, List<String> conditions,
                               @JsonInclude(JsonInclude.Include.ALWAYS) String denialReason) {
    }

    // ---------------------------------------------------------------- 이동

    public record TransportQuoteRequest(@NotNull Long shootDayId, @NotNull Long destLocationId, @NotNull LocalTime start,
                                        @NotNull @Min(1) @Max(200) Integer headcount, @Size(max = 20) List<Long> equipmentIds) {
    }

    public record VehicleOption(String vehicle, int count, long priceKrw) {
    }

    public record TransportBrief(String bookingId, String status, long destLocationId) {
    }

    public record TransportQuote(String pickup, String destination, double distanceKm, int travelMinutes,
                                 LocalTime departAt, List<VehicleOption> options, VehicleOption recommended,
                                 List<TransportBrief> bookings) {
    }

    public record TransportBookRequest(@NotNull Long shootDayId, Long taskId, @NotNull Long destLocationId,
                                       @NotNull @Pattern(regexp = "VAN_12|BUS_25|TRUCK_1T") String vehicle,
                                       @NotNull @Min(1) @Max(10) Integer count, @NotNull LocalTime departAt,
                                       @NotBlank @Size(max = 60) String pickup,
                                       @Min(0) @Max(200) Integer headcount) {
    }

    public record TransportBookResult(String bookingId, String status, long costKrw, LocalTime departAt, String pickup) {
    }

    public record TransportCancelResult(String bookingId, String status, long cancelFeeKrw) {
    }

    // ---------------------------------------------------------------- 연락

    public record Contact(String recipientId, String name, String role, String channel, String reason) {
    }

    public record ContactList(List<Contact> contacts) {
    }

    public record OutgoingMessage(
            @NotNull @Pattern(regexp = "^(ACTOR|USER|VENDOR):[A-Za-z0-9_\\-]+$") String recipientId,
            @NotBlank @Size(max = 1000) String text) {
    }

    /**
     * @param round 실행팀 라운드. 주면 같은 작업, 같은 라운드에서 이미 보낸 사람에게는 다시 보내지 않는다(재시도 대비).
     *              다음 라운드(수정 요청 뒤)의 정정 안내는 새로 보낸다
     */
    public record SendRequest(@NotNull Long shootDayId, Long taskId,
                              @NotEmpty @Size(max = 40) List<@Valid OutgoingMessage> messages,
                              @Positive Integer round) {

        public SendRequest(Long shootDayId, Long taskId, List<OutgoingMessage> messages) {
            this(shootDayId, taskId, messages, null);
        }
    }

    public record SentMessage(long messageId, String recipientId, String status) {
    }

    public record SendResult(List<SentMessage> sent) {
    }

    public record Question(String recipientId, String name, String reply) {
    }

    public record Replies(int sent, int acked, List<Question> questions, int pending) {
    }

    // ---------------------------------------------------------------- 장부

    public record LedgerEntryRequest(
            @NotNull @Pattern(regexp = "VENUE|EQUIPMENT_RENTAL|TRANSPORT|PERMIT_FEE|CANCEL_FEE") String account,
            @NotBlank @Size(max = 200) String memo,
            @NotNull @Pattern(regexp = "RESERVATION|RENTAL|TRANSPORT|PERMIT") String refType,
            @NotBlank @Size(max = 20) String refId) {
    }

    public record LedgerRequest(@NotNull Long shootDayId, Long taskId,
                                @NotEmpty @Size(max = 20) List<@Valid LedgerEntryRequest> entries) {
    }

    public record LedgerEntryView(long entryId, String account, String memo, long amountKrw, String refType,
                                  String refId) {
    }

    public record Budget(long capKrw, long spentKrw, long remainingKrw, boolean over) {
    }

    public record LedgerResult(List<LedgerEntryView> entries, long totalKrw, Budget budget) {
    }

    public record BudgetStatus(long capKrw, long spentKrw, long remainingKrw, boolean over,
                               List<LedgerEntryView> entries) {
    }

    // ---------------------------------------------------------------- 화면용 묶음 조회

    public record RentalView(String bookingId, List<Long> equipmentIds, LocalTime start, LocalTime end, String status,
                             long totalKrw, LocalTime deliveryAt) {
    }

    public record PermitView(String permitId, long locationId, String kind, String status, long feeKrw,
                             List<String> conditions, String denialReason) {
    }

    public record TransportView(String bookingId, long destLocationId, String vehicle, int count, LocalTime departAt,
                                String pickup, String status, long costKrw) {
    }

    public record MessageSummary(int sent, int acked, int questions) {
    }

    public record OpsSummary(List<ReservationView> reservations, List<RentalView> rentals, List<PermitView> permits,
                             List<TransportView> transports, MessageSummary messages, Budget budget) {
    }
}
