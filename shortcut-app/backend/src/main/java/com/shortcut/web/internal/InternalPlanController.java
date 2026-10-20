package com.shortcut.web.internal;

import com.shortcut.dto.PlanDtos.EvaluateRequest;
import com.shortcut.dto.PlanDtos.EvaluateResponse;
import com.shortcut.dto.PlanDtos.ValidateRequest;
import com.shortcut.dto.PlanDtos.ValidateResponse;
import com.shortcut.service.PlanService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/plans")
public class InternalPlanController {

    private final PlanService plans;

    public InternalPlanController(PlanService plans) {
        this.plans = plans;
    }

    @PostMapping("/evaluate")
    public EvaluateResponse evaluate(@Valid @RequestBody EvaluateRequest request) {
        return plans.evaluate(request);
    }

    @PostMapping("/validate")
    public ValidateResponse validate(@Valid @RequestBody ValidateRequest request) {
        return plans.validate(request);
    }
}
