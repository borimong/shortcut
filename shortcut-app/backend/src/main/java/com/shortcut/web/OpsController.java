package com.shortcut.web;

import com.shortcut.dto.OpsDtos.OpsSummary;
import com.shortcut.service.OpsService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 콜시트 화면에 실행팀 결과(예약, 렌탈, 허가, 차량, 연락, 장부)를 한 줄씩 보여 주려고 묶어 조회한다.
 */
@RestController
@RequestMapping("/api/shoot-days")
public class OpsController {

    private final OpsService ops;

    public OpsController(OpsService ops) {
        this.ops = ops;
    }

    @GetMapping("/{id}/ops")
    public OpsSummary summary(@PathVariable long id) {
        return ops.summary(id);
    }
}
