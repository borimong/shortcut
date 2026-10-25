package com.shortcut.web.internal;

import com.shortcut.dto.OpsDtos.BudgetStatus;
import com.shortcut.dto.OpsDtos.CancelRequest;
import com.shortcut.dto.OpsDtos.ContactList;
import com.shortcut.dto.OpsDtos.LedgerRequest;
import com.shortcut.dto.OpsDtos.LedgerResult;
import com.shortcut.dto.OpsDtos.PermitApplyRequest;
import com.shortcut.dto.OpsDtos.PermitRequirement;
import com.shortcut.dto.OpsDtos.PermitResult;
import com.shortcut.dto.OpsDtos.RentalBookRequest;
import com.shortcut.dto.OpsDtos.RentalBookResult;
import com.shortcut.dto.OpsDtos.RentalCancelResult;
import com.shortcut.dto.OpsDtos.RentalQuote;
import com.shortcut.dto.OpsDtos.RentalQuoteRequest;
import com.shortcut.dto.OpsDtos.Replies;
import com.shortcut.dto.OpsDtos.SendRequest;
import com.shortcut.dto.OpsDtos.SendResult;
import com.shortcut.dto.OpsDtos.TransportBookRequest;
import com.shortcut.dto.OpsDtos.TransportBookResult;
import com.shortcut.dto.OpsDtos.TransportCancelResult;
import com.shortcut.dto.OpsDtos.TransportQuote;
import com.shortcut.dto.OpsDtos.TransportQuoteRequest;
import com.shortcut.dto.OpsDtos.VenueAvailability;
import com.shortcut.dto.OpsDtos.VenueCancelResult;
import com.shortcut.dto.OpsDtos.VenueHoldRequest;
import com.shortcut.dto.OpsDtos.VenueHoldResult;
import com.shortcut.service.OpsService;
import jakarta.validation.Valid;
import java.time.LocalTime;
import java.util.List;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 실행팀 Agent가 ops-mcp를 거쳐 부르는 가상 외부 서비스 API다. 경로와 필드 이름은 ops-mcp와 계약으로 고정한다.
 */
@RestController
@RequestMapping("/internal/ops")
public class InternalOpsController {

    private final OpsService ops;

    public InternalOpsController(OpsService ops) {
        this.ops = ops;
    }

    // ---------------- 장소

    @GetMapping("/venues/{locationId}/availability")
    public VenueAvailability venueAvailability(@PathVariable long locationId, @RequestParam long shootDayId,
                                               @RequestParam @DateTimeFormat(pattern = "HH:mm") LocalTime start,
                                               @RequestParam @DateTimeFormat(pattern = "HH:mm") LocalTime end) {
        return ops.venueAvailability(shootDayId, locationId, start, end);
    }

    @PostMapping("/venues/holds")
    public VenueHoldResult holdVenue(@Valid @RequestBody VenueHoldRequest request) {
        return ops.holdVenue(request);
    }

    @PostMapping("/venues/reservations/{id}/confirm")
    public VenueHoldResult confirmVenue(@PathVariable String id) {
        return ops.confirmVenue(id);
    }

    @PostMapping("/venues/reservations/{id}/cancel")
    public VenueCancelResult cancelVenue(@PathVariable String id, @Valid @RequestBody(required = false) CancelRequest request) {
        return ops.cancelVenue(id);
    }

    // ---------------- 장비

    @PostMapping("/rentals/quote")
    public RentalQuote quoteRental(@Valid @RequestBody RentalQuoteRequest request) {
        return ops.quoteRental(request);
    }

    @PostMapping("/rentals/bookings")
    public RentalBookResult bookRental(@Valid @RequestBody RentalBookRequest request) {
        return ops.bookRental(request);
    }

    @PostMapping("/rentals/bookings/{id}/cancel")
    public RentalCancelResult cancelRental(@PathVariable String id) {
        return ops.cancelRental(id);
    }

    // ---------------- 촬영 허가

    @GetMapping("/permits/requirement")
    public PermitRequirement permitRequirement(@RequestParam long shootDayId, @RequestParam long locationId,
                                               @RequestParam @DateTimeFormat(pattern = "HH:mm") LocalTime start,
                                               @RequestParam @DateTimeFormat(pattern = "HH:mm") LocalTime end,
                                               @RequestParam(defaultValue = "false") boolean drone) {
        return ops.permitRequirement(shootDayId, locationId, start, end, drone);
    }

    @PostMapping("/permits")
    public PermitResult applyPermit(@Valid @RequestBody PermitApplyRequest request) {
        return ops.applyPermit(request);
    }

    @GetMapping("/permits/{id}")
    public PermitResult permitStatus(@PathVariable String id) {
        return ops.permitStatus(id);
    }

    // ---------------- 이동 수단

    @PostMapping("/transport/quote")
    public TransportQuote quoteTransport(@Valid @RequestBody TransportQuoteRequest request) {
        return ops.quoteTransport(request);
    }

    @PostMapping("/transport/bookings")
    public TransportBookResult bookTransport(@Valid @RequestBody TransportBookRequest request) {
        return ops.bookTransport(request);
    }

    @PostMapping("/transport/bookings/{id}/cancel")
    public TransportCancelResult cancelTransport(@PathVariable String id) {
        return ops.cancelTransport(id);
    }

    // ---------------- 연락

    @GetMapping("/contacts")
    public ContactList contacts(@RequestParam long shootDayId, @RequestParam(required = false) List<String> changed) {
        return ops.contacts(shootDayId, changed);
    }

    @PostMapping("/messages")
    public SendResult send(@Valid @RequestBody SendRequest request) {
        return ops.send(request);
    }

    @GetMapping("/messages/replies")
    public Replies replies(@RequestParam long taskId) {
        return ops.replies(taskId);
    }

    // ---------------- 장부

    @PostMapping("/ledger")
    public LedgerResult recordLedger(@Valid @RequestBody LedgerRequest request) {
        return ops.recordLedger(request);
    }

    @GetMapping("/ledger/budget")
    public BudgetStatus budget(@RequestParam long shootDayId) {
        return ops.budgetStatus(shootDayId);
    }
}
