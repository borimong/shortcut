package com.shortcut.web.internal;

import com.shortcut.domain.DisasterAlert;
import com.shortcut.dto.PlanDtos.AvailabilityResponse;
import com.shortcut.dto.PlanDtos.ExternalLocationView;
import com.shortcut.dto.PlanDtos.PlanSetResponse;
import com.shortcut.dto.PlanDtos.WeatherResponse;
import com.shortcut.dto.PlanDtos.AlternativeLocationView;
import com.shortcut.dto.PlanDtos.RegisterAlternativesRequest;
import com.shortcut.service.AlternativeLocationService;
import com.shortcut.service.ShootDayQueryService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class InternalShootDayController {

    private final ShootDayQueryService shootDays;
    private final AlternativeLocationService alternatives;

    public InternalShootDayController(ShootDayQueryService shootDays, AlternativeLocationService alternatives) {
        this.shootDays = shootDays;
        this.alternatives = alternatives;
    }

    @GetMapping("/shoot-days/{id}/plan-set")
    public PlanSetResponse planSet(@PathVariable long id) {
        return shootDays.planSet(id);
    }

    @GetMapping("/shoot-days/{id}/availability")
    public AvailabilityResponse availability(@PathVariable long id) {
        return shootDays.availability(id);
    }

    @GetMapping("/shoot-days/{id}/weather")
    public WeatherResponse weather(@PathVariable long id) {
        return shootDays.weather(id);
    }

    @GetMapping("/shoot-days/{id}/disaster-alerts")
    public List<DisasterAlert> disasterAlerts(@PathVariable long id) {
        return shootDays.disasterAlerts(id);
    }

    @PostMapping("/shoot-days/{id}/alternative-locations")
    @ResponseStatus(HttpStatus.CREATED)
    public List<AlternativeLocationView> registerAlternatives(@PathVariable long id,
                                                              @Valid @RequestBody RegisterAlternativesRequest request) {
        return alternatives.register(id, request.externalLocationIds(), request.keywords());
    }

    @GetMapping("/locations/search")
    public List<ExternalLocationView> searchLocations(@RequestParam(required = false) String keywords,
                                                      @RequestParam(required = false) Double maxDistanceKm) {
        return shootDays.searchExternal(keywords, maxDistanceKm);
    }
}
