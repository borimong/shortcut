package com.shortcut.web;

import com.shortcut.dto.ProposalDtos.ProposalSummary;
import com.shortcut.dto.ProposalDtos.ProposalView;
import com.shortcut.service.ProposalService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/proposals")
public class ProposalController {

    private final ProposalService proposals;

    public ProposalController(ProposalService proposals) {
        this.proposals = proposals;
    }

    @GetMapping("/{id}")
    public ProposalView get(@PathVariable long id) {
        return proposals.view(id);
    }

    @GetMapping
    public List<ProposalSummary> list(@RequestParam(defaultValue = "1") long shootDayId) {
        return proposals.list(shootDayId);
    }
}
