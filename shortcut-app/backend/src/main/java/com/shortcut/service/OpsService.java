package com.shortcut.service;

import com.shortcut.common.ApiException;
import com.shortcut.domain.Actor;
import com.shortcut.domain.Block;
import com.shortcut.domain.Equipment;
import com.shortcut.domain.Location;
import com.shortcut.domain.UserAccount;
import com.shortcut.dto.OpsDtos.Budget;
import com.shortcut.dto.OpsDtos.BudgetStatus;
import com.shortcut.dto.OpsDtos.Contact;
import com.shortcut.dto.OpsDtos.ContactList;
import com.shortcut.dto.OpsDtos.LedgerEntryRequest;
import com.shortcut.dto.OpsDtos.LedgerEntryView;
import com.shortcut.dto.OpsDtos.LedgerRequest;
import com.shortcut.dto.OpsDtos.LedgerResult;
import com.shortcut.dto.OpsDtos.MessageSummary;
import com.shortcut.dto.OpsDtos.OpsSummary;
import com.shortcut.dto.OpsDtos.OutgoingMessage;
import com.shortcut.dto.OpsDtos.PermitApplyRequest;
import com.shortcut.dto.OpsDtos.PermitBrief;
import com.shortcut.dto.OpsDtos.PermitRequirement;
import com.shortcut.dto.OpsDtos.PermitResult;
import com.shortcut.dto.OpsDtos.PermitView;
import com.shortcut.dto.OpsDtos.PermitWindow;
import com.shortcut.dto.OpsDtos.Question;
import com.shortcut.dto.OpsDtos.RentalBookRequest;
import com.shortcut.dto.OpsDtos.RentalBookResult;
import com.shortcut.dto.OpsDtos.RentalBookingView;
import com.shortcut.dto.OpsDtos.RentalCancelResult;
import com.shortcut.dto.OpsDtos.RentalItem;
import com.shortcut.dto.OpsDtos.RentalQuote;
import com.shortcut.dto.OpsDtos.RentalQuoteRequest;
import com.shortcut.dto.OpsDtos.RentalView;
import com.shortcut.dto.OpsDtos.Replies;
import com.shortcut.dto.OpsDtos.ReservationView;
import com.shortcut.dto.OpsDtos.SendRequest;
import com.shortcut.dto.OpsDtos.SendResult;
import com.shortcut.dto.OpsDtos.SentMessage;
import com.shortcut.dto.OpsDtos.TransportBookRequest;
import com.shortcut.dto.OpsDtos.TransportBookResult;
import com.shortcut.dto.OpsDtos.TransportBrief;
import com.shortcut.dto.OpsDtos.TransportCancelResult;
import com.shortcut.dto.OpsDtos.TransportQuote;
import com.shortcut.dto.OpsDtos.TransportQuoteRequest;
import com.shortcut.dto.OpsDtos.TransportView;
import com.shortcut.dto.OpsDtos.VehicleOption;
import com.shortcut.dto.OpsDtos.VenueAvailability;
import com.shortcut.dto.OpsDtos.VenueCancelResult;
import com.shortcut.dto.OpsDtos.VenueHoldRequest;
import com.shortcut.dto.OpsDtos.VenueHoldResult;
import com.shortcut.repository.OpsRepository;
import com.shortcut.repository.OpsRepository.LedgerRow;
import com.shortcut.repository.OpsRepository.MessageRow;
import com.shortcut.repository.OpsRepository.PermitRow;
import com.shortcut.repository.OpsRepository.RentalRow;
import com.shortcut.repository.OpsRepository.ReservationRow;
import com.shortcut.repository.OpsRepository.TransportRow;
import com.shortcut.repository.UserRepository;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 실행팀 Agent가 ops-mcp를 거쳐 부르는 가상 외부 서비스다.
 * 가상 아워플레이스, 렌탈사, 허가 기관, 차량 업체, 메시지 발송, 제작비 장부를 결정론적으로 흉내 낸다.
 * 같은 입력에는 같은 결과를 돌려주고, 같은 요청을 다시 보내면 기존 행을 그대로 돌려준다(재시도와 재실행에 안전).
 * 실제 외부 연동은 하지 않지만 상태를 DB에 남겨 콜시트 화면과 평가에서 확인할 수 있게 한다.
 */
@Service
public class OpsService {

    public static final String HELD = "HELD";
    public static final String CONFIRMED = "CONFIRMED";
    public static final String CANCELLED = "CANCELLED";
    public static final String MANUAL_PENDING = "MANUAL_PENDING";
    public static final String BOOKED = "BOOKED";
    public static final String APPROVED = "APPROVED";
    public static final String DENIED = "DENIED";
    public static final String MOCK_PROVIDER = "OURPLACE_MOCK";

    // 확정 뒤 취소하면 금액의 10%를 수수료로 낸다고 가정한다. 가예약 취소는 무료다.
    private static final long CANCEL_FEE_PERCENT = 10;
    private static final long LOCATION_PERMIT_FEE = 50_000;
    private static final long DRONE_PERMIT_FEE = 30_000;
    private static final Map<String, Long> VEHICLE_PRICE = Map.of("VAN_12", 180_000L, "BUS_25", 350_000L, "TRUCK_1T", 120_000L);
    // 장비가 이만큼 이상이면 승합차에 다 싣지 못한다고 보고 1톤 트럭을 따로 제안한다.
    private static final int TRUCK_EQUIPMENT_THRESHOLD = 4;
    private static final Set<String> CANCELLABLE_REFS = Set.of("RESERVATION", "RENTAL", "TRANSPORT");
    private static final Map<String, String> ACCOUNT_REF = Map.of(
            "VENUE", "RESERVATION", "EQUIPMENT_RENTAL", "RENTAL", "TRANSPORT", "TRANSPORT", "PERMIT_FEE", "PERMIT");
    private static final Pattern HH_MM = Pattern.compile("\\b\\d{1,2}:\\d{2}\\b");
    static final String ACK_REPLY = "확인했습니다.";
    static final String QUESTION_REPLY = "몇 시에 어디로 가면 되나요?";

    private final OpsRepository ops;
    private final PlanDataService planData;
    private final UserRepository users;
    private final NotificationService notifications;

    public OpsService(OpsRepository ops, PlanDataService planData, UserRepository users,
                      NotificationService notifications) {
        this.ops = ops;
        this.planData = planData;
        this.users = users;
        this.notifications = notifications;
    }

    // ---------------------------------------------------------------- 장소 (가상 아워플레이스)

    @Transactional(readOnly = true)
    public VenueAvailability venueAvailability(long shootDayId, long locationId, LocalTime start, LocalTime end) {
        requireTimeRange(start, end);
        PlanData data = planData.load(shootDayId);
        Location location = location(data, locationId);
        String reason = null;
        if (data.settings().mockVenueConflict()) {
            reason = "같은 시간대에 다른 예약이 있습니다";
        } else if (!location.available()) {
            reason = "이 장소는 이번 촬영일에 쓸 수 없다고 등록되어 있습니다";
        } else if (start.isBefore(location.openFrom()) || end.isAfter(location.openTo())) {
            reason = "운영 시간(" + location.openFrom() + "~" + location.openTo() + ") 밖입니다";
        }
        return new VenueAvailability(location.id(), location.name(), location.indoor(), reason == null,
                reason == null ? "예약할 수 있습니다" : reason, location.cost(), reservationViews(data, shootDayId));
    }

    @Transactional
    public VenueHoldResult holdVenue(VenueHoldRequest request) {
        requireTimeRange(request.start(), request.end());
        PlanData data = planData.load(request.shootDayId());
        Location location = location(data, request.locationId());
        if (data.settings().mockVenueConflict()) {
            throw ApiException.conflict("VENUE_CONFLICT", "같은 시간대에 다른 예약이 있어 가예약할 수 없습니다");
        }
        Optional<ReservationRow> existing = covering(request.shootDayId(), location.id(), request.start(), request.end());
        if (existing.isPresent()) {
            ReservationRow row = existing.get();
            // 이미 확정된 예약은 그대로 두고, 확정 처리 대기나 가예약은 가예약으로 맞춘다.
            String status = CONFIRMED.equals(row.status()) ? CONFIRMED : HELD;
            ops.updateReservation(row.id(), status, request.taskId(), location.cost(), 0);
            return new VenueHoldResult(row.id(), status, location.cost());
        }
        String id = ops.nextReservationId();
        ops.insertReservation(new ReservationRow(id, request.shootDayId(), location.id(), request.start(), request.end(),
                HELD, MOCK_PROVIDER, request.taskId(), location.cost(), 0));
        return new VenueHoldResult(id, HELD, location.cost());
    }

    @Transactional
    public VenueHoldResult confirmVenue(String reservationId) {
        ReservationRow row = reservation(reservationId);
        if (CANCELLED.equals(row.status())) {
            throw ApiException.conflict("INVALID_STATE", "취소된 예약은 확정할 수 없습니다. venue_hold로 다시 가예약하세요");
        }
        long price = locationCost(row);
        ops.updateReservation(row.id(), CONFIRMED, null, price, 0);
        return new VenueHoldResult(row.id(), CONFIRMED, price);
    }

    @Transactional
    public VenueCancelResult cancelVenue(String reservationId) {
        ReservationRow row = reservation(reservationId);
        if (CANCELLED.equals(row.status())) {
            return new VenueCancelResult(row.id(), CANCELLED, row.cancelFeeKrw());
        }
        long price = locationCost(row);
        long fee = CONFIRMED.equals(row.status()) ? price * CANCEL_FEE_PERCENT / 100 : 0;
        ops.updateReservation(row.id(), CANCELLED, null, price, fee);
        return new VenueCancelResult(row.id(), CANCELLED, fee);
    }

    // ---------------------------------------------------------------- 장비 (가상 렌탈사)

    @Transactional(readOnly = true)
    public RentalQuote quoteRental(RentalQuoteRequest request) {
        requireTimeRange(request.start(), request.end());
        PlanData data = planData.load(request.shootDayId());
        List<RentalItem> items = rentalItems(data, request.equipmentIds());
        long total = items.stream().mapToLong(RentalItem::priceKrw).sum();
        List<RentalBookingView> bookings = ops.findRentals(request.shootDayId()).stream()
                .map(r -> new RentalBookingView(r.id(), r.equipmentIds(), r.status(), r.totalKrw()))
                .toList();
        return new RentalQuote(items, total, request.start().minusMinutes(60), "가상 렌탈사", bookings);
    }

    @Transactional
    public RentalBookResult bookRental(RentalBookRequest request) {
        requireTimeRange(request.start(), request.end());
        PlanData data = planData.load(request.shootDayId());
        List<RentalItem> items = rentalItems(data, request.equipmentIds());
        List<String> broken = items.stream().filter(item -> !item.available()).map(RentalItem::name).toList();
        if (!broken.isEmpty()) {
            throw ApiException.conflict("INVALID_STATE", "고장이나 사용 불가로 등록된 장비는 빌릴 수 없습니다: " + String.join(", ", broken));
        }
        List<Long> ids = request.equipmentIds().stream().distinct().sorted().toList();
        for (RentalRow row : ops.findRentals(request.shootDayId())) {
            if (BOOKED.equals(row.status()) && ids.equals(row.equipmentIds().stream().sorted().toList())
                    && row.start().equals(request.start()) && row.end().equals(request.end())) {
                return new RentalBookResult(row.id(), BOOKED, row.totalKrw(), row.deliveryAt());
            }
        }
        long total = items.stream().mapToLong(RentalItem::priceKrw).sum();
        LocalTime deliveryAt = request.start().minusMinutes(60);
        String id = ops.nextRentalId();
        ops.insertRental(new RentalRow(id, request.shootDayId(), request.taskId(), ids, request.start(), request.end(),
                BOOKED, total, deliveryAt, 0));
        return new RentalBookResult(id, BOOKED, total, deliveryAt);
    }

    @Transactional
    public RentalCancelResult cancelRental(String bookingId) {
        RentalRow row = ops.findRental(bookingId)
                .orElseThrow(() -> ApiException.notFound("BOOKING_NOT_FOUND", "렌탈 예약이 없습니다: " + bookingId));
        if (CANCELLED.equals(row.status())) {
            return new RentalCancelResult(row.id(), CANCELLED, row.cancelFeeKrw());
        }
        long fee = row.totalKrw() * CANCEL_FEE_PERCENT / 100;
        ops.updateRentalStatus(row.id(), CANCELLED, fee);
        return new RentalCancelResult(row.id(), CANCELLED, fee);
    }

    // ---------------------------------------------------------------- 촬영 허가 (가상 허가 기관)

    @Transactional(readOnly = true)
    public PermitRequirement permitRequirement(long shootDayId, long locationId, LocalTime start, LocalTime end,
                                               boolean drone) {
        requireTimeRange(start, end);
        PlanData data = planData.load(shootDayId);
        Location location = location(data, locationId);
        List<String> kinds = new ArrayList<>();
        List<String> authorities = new ArrayList<>();
        long fee = 0;
        if (!location.indoor()) {
            kinds.add("LOCATION");
            authorities.add("가상 " + location.region() + " 영상 촬영 허가 창구");
            fee += LOCATION_PERMIT_FEE;
        }
        if (drone) {
            kinds.add("DRONE");
            authorities.add("가상 지방항공청");
            fee += DRONE_PERMIT_FEE;
        }
        PermitWindow window = location.permitFrom() == null || location.permitTo() == null
                ? null : new PermitWindow(location.permitFrom(), location.permitTo());
        boolean within = window == null || (!start.isBefore(window.from()) && !end.isAfter(window.to()));
        String reason;
        if (kinds.isEmpty()) {
            reason = "실내 장소이고 드론을 쓰지 않아 장소 예약만으로 촬영할 수 있습니다";
        } else {
            List<String> parts = new ArrayList<>();
            if (kinds.contains("LOCATION")) {
                parts.add("야외 공공장소라 관할 기관의 촬영 허가가 필요합니다"
                        + (within ? "" : ". 요청 시간이 허가 시간대(" + window.from() + "~" + window.to() + ") 밖이라 반려됩니다"));
            }
            if (kinds.contains("DRONE")) {
                parts.add(location.noFlyZone() ? "드론 촬영 승인이 필요하지만 비행 금지 구역이라 반려됩니다"
                        : "드론 장비가 있어 드론 촬영 승인이 필요합니다");
            }
            reason = String.join(". ", parts);
        }
        List<PermitBrief> permits = ops.findPermits(shootDayId).stream()
                .map(p -> new PermitBrief(p.id(), p.kind(), p.status()))
                .toList();
        return new PermitRequirement(!kinds.isEmpty(), kinds, authorities.isEmpty() ? null : String.join(", ", authorities),
                fee, window, within, location.noFlyZone(), reason, permits);
    }

    @Transactional
    public PermitResult applyPermit(PermitApplyRequest request) {
        requireTimeRange(request.start(), request.end());
        PlanData data = planData.load(request.shootDayId());
        Location location = location(data, request.locationId());
        for (PermitRow row : ops.findPermits(request.shootDayId())) {
            if (row.locationId() == location.id() && row.kind().equals(request.kind())
                    && row.start().equals(request.start()) && row.end().equals(request.end())) {
                return permitResult(row);
            }
        }
        String denial = null;
        if (data.settings().mockPermitDenied()) {
            denial = "가상 허가 기관이 같은 시간대의 다른 행사와 겹쳐 반려했습니다";
        } else if ("LOCATION".equals(request.kind()) && location.permitFrom() != null && location.permitTo() != null
                && (request.start().isBefore(location.permitFrom()) || request.end().isAfter(location.permitTo()))) {
            denial = "허가 시간대(" + location.permitFrom() + "~" + location.permitTo() + ") 밖입니다";
        } else if ("DRONE".equals(request.kind()) && location.noFlyZone()) {
            denial = "비행 금지 구역이라 드론 촬영을 승인할 수 없습니다";
        }
        List<String> conditions = new ArrayList<>();
        long fee = 0;
        if (denial == null) {
            if ("LOCATION".equals(request.kind())) {
                if (location.indoor()) {
                    conditions.add("실내 장소라 별도 허가 없이 장소 예약으로 사용합니다");
                } else {
                    fee = LOCATION_PERMIT_FEE;
                    conditions.add("촬영 가능 시간 " + request.start() + "~" + request.end());
                    conditions.add("통행로 확보 요원 1명 배치");
                    conditions.add("현장에 허가증 사본 비치");
                }
            } else {
                fee = DRONE_PERMIT_FEE;
                conditions.add("고도 30m 이하 비행");
                conditions.add("이착륙 지점에 안전 요원 배치");
            }
        }
        PermitRow row = new PermitRow(ops.nextPermitId(), request.shootDayId(), request.taskId(), location.id(),
                request.start(), request.end(), request.kind(), denial == null ? APPROVED : DENIED, fee, conditions, denial);
        ops.insertPermit(row);
        return permitResult(row);
    }

    @Transactional(readOnly = true)
    public PermitResult permitStatus(String permitId) {
        return permitResult(ops.findPermit(permitId)
                .orElseThrow(() -> ApiException.notFound("PERMIT_NOT_FOUND", "허가 신청이 없습니다: " + permitId)));
    }

    // ---------------------------------------------------------------- 이동 수단 (가상 차량 업체)

    @Transactional(readOnly = true)
    public TransportQuote quoteTransport(TransportQuoteRequest request) {
        PlanData data = planData.load(request.shootDayId());
        Location dest = location(data, request.destLocationId());
        int travel = (int) Math.round(dest.distanceKm() * 2 + 10);
        LocalTime departAt = request.start().minusMinutes(travel + 30L);
        int headcount = request.headcount();
        // 승합차는 12인승, 버스는 25인승이다.
        VehicleOption van = vehicle("VAN_12", (headcount + 11) / 12);
        VehicleOption bus = vehicle("BUS_25", (headcount + 24) / 25);
        List<VehicleOption> options = new ArrayList<>(List.of(van, bus));
        int equipmentCount = request.equipmentIds() == null ? 0 : request.equipmentIds().size();
        if (equipmentCount >= TRUCK_EQUIPMENT_THRESHOLD) {
            options.add(vehicle("TRUCK_1T", 1));
        }
        VehicleOption recommended = van.priceKrw() <= bus.priceKrw() ? van : bus;
        List<TransportBrief> bookings = ops.findTransports(request.shootDayId()).stream()
                .map(t -> new TransportBrief(t.id(), t.status(), t.destLocationId()))
                .toList();
        return new TransportQuote(pickupName(data), dest.name(), dest.distanceKm(), travel, departAt, options,
                recommended, bookings);
    }

    @Transactional
    public TransportBookResult bookTransport(TransportBookRequest request) {
        PlanData data = planData.load(request.shootDayId());
        Location dest = location(data, request.destLocationId());
        for (TransportRow row : ops.findTransports(request.shootDayId())) {
            if (BOOKED.equals(row.status()) && row.destLocationId() == dest.id() && row.vehicle().equals(request.vehicle())
                    && row.departAt().equals(request.departAt())) {
                return new TransportBookResult(row.id(), BOOKED, row.costKrw(), row.departAt(), row.pickup());
            }
        }
        long cost = VEHICLE_PRICE.get(request.vehicle()) * request.count();
        String id = ops.nextTransportId();
        ops.insertTransport(new TransportRow(id, request.shootDayId(), request.taskId(), dest.id(), request.vehicle(),
                request.count(), request.headcount() == null ? 0 : request.headcount(), request.departAt(),
                request.pickup(), BOOKED, cost, 0));
        return new TransportBookResult(id, BOOKED, cost, request.departAt(), request.pickup());
    }

    @Transactional
    public TransportCancelResult cancelTransport(String bookingId) {
        TransportRow row = ops.findTransport(bookingId)
                .orElseThrow(() -> ApiException.notFound("BOOKING_NOT_FOUND", "차량 예약이 없습니다: " + bookingId));
        if (CANCELLED.equals(row.status())) {
            return new TransportCancelResult(row.id(), CANCELLED, row.cancelFeeKrw());
        }
        long fee = row.costKrw() * CANCEL_FEE_PERCENT / 100;
        ops.updateTransportStatus(row.id(), CANCELLED, fee);
        return new TransportCancelResult(row.id(), CANCELLED, fee);
    }

    // ---------------------------------------------------------------- 연락 (가상 메시지 발송)

    @Transactional(readOnly = true)
    public ContactList contacts(long shootDayId, List<String> changed) {
        return new ContactList(List.copyOf(contactMap(shootDayId, changed).values()));
    }

    @Transactional
    public SendResult send(SendRequest request) {
        Map<String, Contact> known = contactMap(request.shootDayId(), List.of());
        List<SentMessage> sent = new ArrayList<>();
        for (OutgoingMessage message : request.messages()) {
            Contact contact = known.get(message.recipientId());
            if (contact == null) {
                throw ApiException.badRequest("VALIDATION_FAILED",
                        "연락 대상이 아닙니다: " + message.recipientId() + ". contacts_for_change 결과의 recipientId를 쓰세요");
            }
            Optional<MessageRow> existing = ops.findMessage(request.taskId(), message.recipientId(), message.text());
            if (existing.isPresent()) {
                sent.add(new SentMessage(existing.get().id(), message.recipientId(), existing.get().status()));
                continue;
            }
            long id = ops.insertMessage(new MessageRow(0, request.shootDayId(), request.taskId(), contact.recipientId(),
                    contact.name(), contact.role(), contact.channel(), message.text(), "SENT", null));
            if (message.recipientId().startsWith("USER:")) {
                notifications.notifyUsernames(List.of(message.recipientId().substring("USER:".length())),
                        NotificationService.CHANGE_NOTICE, "촬영 변경 안내", message.text(), "/");
            }
            sent.add(new SentMessage(id, message.recipientId(), "SENT"));
        }
        return new SendResult(sent);
    }

    /**
     * 가상 수신자는 조회할 때 답한다. 시각(HH:mm)과 장소 이름(또는 집결)이 모두 적힌 안내는 확인으로,
     * 하나라도 빠진 안내는 질문으로 답한다. 한 번 정한 답은 저장해 다시 조회해도 같다.
     */
    @Transactional
    public Replies replies(long taskId) {
        List<MessageRow> messages = ops.findMessagesByTask(taskId);
        Map<Long, List<String>> placeNames = new LinkedHashMap<>();
        int acked = 0;
        List<Question> questions = new ArrayList<>();
        for (MessageRow m : messages) {
            String status = m.status();
            String reply = m.reply();
            if ("SENT".equals(status)) {
                List<String> places = placeNames.computeIfAbsent(m.shootDayId(),
                        id -> planData.load(id).locations().values().stream().map(Location::name).toList());
                boolean hasTime = HH_MM.matcher(m.text()).find();
                boolean hasPlace = m.text().contains("집결") || places.stream().anyMatch(m.text()::contains);
                status = hasTime && hasPlace ? "ACKED" : "QUESTION";
                reply = hasTime && hasPlace ? ACK_REPLY : QUESTION_REPLY;
                ops.updateMessageReply(m.id(), status, reply);
            }
            if ("ACKED".equals(status)) {
                acked++;
            } else if ("QUESTION".equals(status)) {
                questions.add(new Question(m.recipientId(), m.recipientName(), reply));
            }
        }
        return new Replies(messages.size(), acked, questions, messages.size() - acked - questions.size());
    }

    // ---------------------------------------------------------------- 제작비 장부

    /**
     * 금액은 Agent가 적지 않고 ref 행에서 직접 읽는다. 돈 계산이 틀리면 안 되므로 LLM은 계정 분류와 적요만 맡는다.
     */
    @Transactional
    public LedgerResult recordLedger(LedgerRequest request) {
        List<LedgerEntryView> entries = new ArrayList<>();
        for (LedgerEntryRequest entry : request.entries()) {
            long amount = amountOf(request.shootDayId(), entry);
            LedgerRow saved = ops.upsertLedger(new LedgerRow(0, request.shootDayId(), request.taskId(), entry.account(),
                    entry.memo(), amount, entry.refType(), entry.refId()));
            entries.add(view(saved));
        }
        long total = entries.stream().mapToLong(LedgerEntryView::amountKrw).sum();
        return new LedgerResult(entries, total, budget(request.shootDayId()));
    }

    @Transactional(readOnly = true)
    public BudgetStatus budgetStatus(long shootDayId) {
        Budget budget = budget(shootDayId);
        return new BudgetStatus(budget.capKrw(), budget.spentKrw(), budget.remainingKrw(), budget.over(),
                ops.findLedger(shootDayId).stream().map(OpsService::view).toList());
    }

    // ---------------------------------------------------------------- 화면용 묶음 조회

    @Transactional(readOnly = true)
    public OpsSummary summary(long shootDayId) {
        PlanData data = planData.load(shootDayId);
        List<RentalView> rentals = ops.findRentals(shootDayId).stream()
                .map(r -> new RentalView(r.id(), r.equipmentIds(), r.start(), r.end(), r.status(), r.totalKrw(), r.deliveryAt()))
                .toList();
        List<PermitView> permits = ops.findPermits(shootDayId).stream()
                .map(p -> new PermitView(p.id(), p.locationId(), p.kind(), p.status(), p.feeKrw(), p.conditions(), p.denialReason()))
                .toList();
        List<TransportView> transports = ops.findTransports(shootDayId).stream()
                .map(t -> new TransportView(t.id(), t.destLocationId(), t.vehicle(), t.count(), t.departAt(), t.pickup(),
                        t.status(), t.costKrw()))
                .toList();
        List<MessageRow> messages = ops.findMessagesByShootDay(shootDayId);
        MessageSummary messageSummary = new MessageSummary(messages.size(),
                (int) messages.stream().filter(m -> "ACKED".equals(m.status())).count(),
                (int) messages.stream().filter(m -> "QUESTION".equals(m.status())).count());
        return new OpsSummary(reservationViews(data, shootDayId), rentals, permits, transports, messageSummary,
                budget(shootDayId));
    }

    // ---------------------------------------------------------------- 내부

    private long amountOf(long shootDayId, LedgerEntryRequest entry) {
        boolean cancelFee = "CANCEL_FEE".equals(entry.account());
        if (cancelFee ? !CANCELLABLE_REFS.contains(entry.refType()) : !entry.refType().equals(ACCOUNT_REF.get(entry.account()))) {
            throw ApiException.badRequest("VALIDATION_FAILED", "계정 " + entry.account() + "에는 refType " + entry.refType()
                    + "을 쓸 수 없습니다. VENUE는 RESERVATION, EQUIPMENT_RENTAL은 RENTAL, TRANSPORT는 TRANSPORT, "
                    + "PERMIT_FEE는 PERMIT, CANCEL_FEE는 RESERVATION, RENTAL, TRANSPORT입니다");
        }
        String status;
        long amount;
        long fee;
        switch (entry.refType()) {
            case "RESERVATION" -> {
                ReservationRow r = reservation(entry.refId());
                requireSameDay(shootDayId, r.shootDayId(), entry.refId());
                status = r.status();
                amount = locationCost(r);
                fee = r.cancelFeeKrw();
            }
            case "RENTAL" -> {
                RentalRow r = ops.findRental(entry.refId())
                        .orElseThrow(() -> ApiException.notFound("BOOKING_NOT_FOUND", "렌탈 예약이 없습니다: " + entry.refId()));
                requireSameDay(shootDayId, r.shootDayId(), entry.refId());
                status = r.status();
                amount = r.totalKrw();
                fee = r.cancelFeeKrw();
            }
            case "TRANSPORT" -> {
                TransportRow r = ops.findTransport(entry.refId())
                        .orElseThrow(() -> ApiException.notFound("BOOKING_NOT_FOUND", "차량 예약이 없습니다: " + entry.refId()));
                requireSameDay(shootDayId, r.shootDayId(), entry.refId());
                status = r.status();
                amount = r.costKrw();
                fee = r.cancelFeeKrw();
            }
            default -> {
                PermitRow r = ops.findPermit(entry.refId())
                        .orElseThrow(() -> ApiException.notFound("PERMIT_NOT_FOUND", "허가 신청이 없습니다: " + entry.refId()));
                requireSameDay(shootDayId, r.shootDayId(), entry.refId());
                if (DENIED.equals(r.status())) {
                    throw ApiException.conflict("INVALID_STATE", "반려된 허가에는 수수료가 없습니다: " + entry.refId());
                }
                return r.feeKrw();
            }
        }
        if (cancelFee) {
            if (!CANCELLED.equals(status)) {
                throw ApiException.conflict("INVALID_STATE", "취소되지 않은 예약에는 취소 수수료가 없습니다: " + entry.refId());
            }
            return fee;
        }
        if (CANCELLED.equals(status)) {
            throw ApiException.conflict("INVALID_STATE",
                    "취소된 예약의 비용은 기록하지 않습니다. 취소 수수료는 CANCEL_FEE로 기록하세요: " + entry.refId());
        }
        return amount;
    }

    private Budget budget(long shootDayId) {
        long cap = planData.load(shootDayId).shootDay().blockBudgetCap();
        long spent = ops.findLedger(shootDayId).stream().mapToLong(LedgerRow::amountKrw).sum();
        return new Budget(cap, spent, cap - spent, spent > cap);
    }

    private Map<String, Contact> contactMap(long shootDayId, List<String> changed) {
        PlanData data = planData.load(shootDayId);
        String what = changed == null || changed.isEmpty() ? "촬영 변경" : String.join(", ", changed) + " 변경";
        Map<String, Contact> contacts = new LinkedHashMap<>();
        for (long actorId : data.actorIdsOf(PlanData.CHANGING_BLOCK)) {
            Actor actor = data.actors().get(actorId);
            if (actor != null) {
                contacts.put("ACTOR:" + actor.id(), new Contact("ACTOR:" + actor.id(), actor.name(), "배우", "SMS",
                        "오후 블록 출연자, " + what + " 안내(소속사 매니저 경유)"));
            }
        }
        for (UserAccount user : users.findAll()) {
            if (user.active()) {
                contacts.put("USER:" + user.username(), new Contact("USER:" + user.username(), user.name(), user.title(),
                        "APP", "스태프, " + what + " 안내"));
            }
        }
        if (ops.findReservations(shootDayId).stream().anyMatch(r -> HELD.equals(r.status()) || CONFIRMED.equals(r.status()))) {
            contacts.put("VENDOR:venue", new Contact("VENDOR:venue", "가상 아워플레이스", "장소 업체", "EMAIL", "장소 예약 업체"));
        }
        if (ops.findRentals(shootDayId).stream().anyMatch(r -> BOOKED.equals(r.status()))) {
            contacts.put("VENDOR:rental", new Contact("VENDOR:rental", "가상 렌탈사", "장비 업체", "EMAIL", "장비 렌탈 업체"));
        }
        if (ops.findTransports(shootDayId).stream().anyMatch(t -> BOOKED.equals(t.status()))) {
            contacts.put("VENDOR:transport", new Contact("VENDOR:transport", "가상 차량 업체", "차량 업체", "EMAIL", "차량 예약 업체"));
        }
        return contacts;
    }

    private Optional<ReservationRow> covering(long shootDayId, long locationId, LocalTime start, LocalTime end) {
        return ops.findReservations(shootDayId).stream()
                .filter(r -> r.locationId() == locationId && !CANCELLED.equals(r.status()))
                .filter(r -> !r.start().isAfter(start) && !r.end().isBefore(end))
                .findFirst();
    }

    private List<ReservationView> reservationViews(PlanData data, long shootDayId) {
        return ops.findReservations(shootDayId).stream()
                .map(r -> new ReservationView(r.id(), r.locationId(),
                        Optional.ofNullable(data.locations().get(r.locationId())).map(Location::name).orElse(""),
                        r.start(), r.end(), r.status()))
                .toList();
    }

    private List<RentalItem> rentalItems(PlanData data, List<Long> equipmentIds) {
        List<RentalItem> items = new ArrayList<>();
        for (Long id : equipmentIds.stream().distinct().sorted().toList()) {
            Equipment equipment = data.equipment().get(id);
            if (equipment == null) {
                throw ApiException.badRequest("UNKNOWN_EQUIPMENT", "장비 ID가 없습니다: " + id);
            }
            items.add(new RentalItem(equipment.id(), equipment.name(), equipment.cost(), equipment.cost() == 0,
                    equipment.available()));
        }
        return items;
    }

    private String pickupName(PlanData data) {
        LocalTime pmStart = data.changingBlock().start();
        return data.blocks().stream()
                .filter(b -> !PlanData.CHANGING_BLOCK.equals(b.code()) && b.locationId() != null && !b.start().isAfter(pmStart))
                .reduce((first, second) -> second)
                .map(Block::locationId)
                .map(id -> data.locations().get(id))
                .filter(Objects::nonNull)
                .map(Location::name)
                .orElse("목동 오피스 세트");
    }

    private ReservationRow reservation(String id) {
        return ops.findReservation(id)
                .orElseThrow(() -> ApiException.notFound("RESERVATION_NOT_FOUND", "예약이 없습니다: " + id));
    }

    /** 시드 예약이나 확정 대기 예약은 금액이 비어 있으므로 장소비로 채운다. */
    private long locationCost(ReservationRow row) {
        if (row.costKrw() > 0) {
            return row.costKrw();
        }
        Location location = planData.load(row.shootDayId()).locations().get(row.locationId());
        return location == null ? 0 : location.cost();
    }

    private static Location location(PlanData data, long locationId) {
        Location location = data.locations().get(locationId);
        if (location == null) {
            throw ApiException.badRequest("UNKNOWN_LOCATION", "장소 ID가 없습니다: " + locationId);
        }
        return location;
    }

    private static VehicleOption vehicle(String vehicle, int count) {
        return new VehicleOption(vehicle, count, VEHICLE_PRICE.get(vehicle) * count);
    }

    private static PermitResult permitResult(PermitRow row) {
        return new PermitResult(row.id(), row.kind(), row.status(), row.feeKrw(), row.conditions(), row.denialReason());
    }

    private static LedgerEntryView view(LedgerRow row) {
        return new LedgerEntryView(row.id(), row.account(), row.memo(), row.amountKrw(), row.refType(), row.refId());
    }

    private static void requireSameDay(long shootDayId, long rowShootDayId, String refId) {
        if (shootDayId != rowShootDayId) {
            throw ApiException.badRequest("VALIDATION_FAILED", "다른 촬영일의 예약입니다: " + refId);
        }
    }

    private static void requireTimeRange(LocalTime start, LocalTime end) {
        if (start == null || end == null || !start.isBefore(end)) {
            throw ApiException.badRequest("INVALID_TIME", "시작 시각이 종료 시각보다 빨라야 합니다(HH:mm)");
        }
    }
}
