package com.shortcut.service;

import com.shortcut.dto.BoardDtos.EquipmentView;
import com.shortcut.dto.PlanDtos.CandidateEquipment;
import com.shortcut.dto.PlanDtos.CandidateLocation;
import com.shortcut.dto.PlanDtos.CandidateTime;
import com.shortcut.dto.PlanDtos.CandidateView;
import com.shortcut.dto.PlanDtos.EvaluateRequest;
import com.shortcut.dto.PlanDtos.EvaluateResponse;
import com.shortcut.dto.PlanDtos.ValidateRequest;
import com.shortcut.dto.PlanDtos.ValidateResponse;
import com.shortcut.engine.CandidateResult;
import com.shortcut.engine.CheckResult;
import com.shortcut.engine.EvaluationResult;
import com.shortcut.engine.ExtraConstraint;
import com.shortcut.engine.PlanEngine;
import java.time.LocalTime;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;

/**
 * DB에서 읽은 촬영일 데이터를 엔진에 넘기고 결과를 계약 모양으로 바꾼다.
 * 판정 로직은 두지 않고 엔진 호출과 변환만 한다.
 */
@Service
public class PlanService {

    // Agent가 한 번에 비교하기에 충분하고 프롬프트를 과하게 키우지 않는 개수다.
    private static final int TOP_CANDIDATES = 10;

    private final PlanDataService planData;
    private final PlanEngine engine;

    public PlanService(PlanDataService planData, PlanEngine engine) {
        this.planData = planData;
        this.engine = engine;
    }

    public EvaluateResponse evaluate(EvaluateRequest request) {
        PlanData data = planData.load(request.shootDayId());
        EvaluationResult result = engine.evaluate(data.toInput(), request.weights(), request.extraConstraints());
        Set<String> excluded = request.excludeHashes() == null ? Set.of() : Set.copyOf(request.excludeHashes());
        List<CandidateResult> remaining = result.candidates().stream()
                .filter(candidate -> !excluded.contains(candidate.hash()))
                .toList();
        long feasibleCount = remaining.stream().filter(CandidateResult::feasible).count();
        List<CandidateView> top = remaining.stream().limit(TOP_CANDIDATES).map(PlanService::view).toList();
        return new EvaluateResponse(data.shootDay().dataVersion(), result.weights(), feasibleCount, top,
                PlanEngine.locationProofBlockers(remaining));
    }

    public ValidateResponse validate(ValidateRequest request) {
        PlanData data = planData.load(request.shootDayId());
        CheckResult check = check(data, request.candidate().locationId(), request.candidate().equipmentIds(),
                request.candidate().start(), request.candidate().end(), request.extraConstraints(),
                request.candidate().sceneOrder());
        int current = data.shootDay().dataVersion();
        boolean stale = request.dataVersion() != current;
        // 데이터가 바뀐 뒤의 판정은 근거가 낡았으므로 위반이 없어도 유효하지 않다고 본다.
        return new ValidateResponse(check.feasible() && !stale, stale, current, check.violations(), check.warnings(),
                check.sceneOrder(), check.sceneOrderChanged());
    }

    /** sceneOrder(씬 코드)를 비우면 엔진이 막히지 않는 씬 순서를 고른다. */
    public CheckResult check(PlanData data, long locationId, List<Long> equipmentIds, LocalTime start, LocalTime end,
                             List<ExtraConstraint> extras, List<String> sceneOrder) {
        return engine.check(data.toInput(), locationId, equipmentIds, start, end, extras, sceneOrder);
    }

    private static CandidateView view(CandidateResult c) {
        List<EquipmentView> items = c.equipment().stream().map(e -> new EquipmentView(e.id(), e.name(), e.available())).toList();
        return new CandidateView(c.hash(),
                new CandidateLocation(c.locationOptionNo(), c.location().id(), c.location().name(), c.location().indoor()),
                new CandidateEquipment(c.equipmentOptionNo(), items),
                new CandidateTime(c.timeOptionNo(), c.start(), c.end()),
                c.feasible(), c.violations(), c.warnings(), c.softScores(), c.totalScore(), c.cost(), c.extraCost(),
                c.distanceKm(), c.sceneOrder(), c.sceneOrderChanged());
    }
}
