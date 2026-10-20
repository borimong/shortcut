package com.shortcut.web.internal;

import com.shortcut.dto.ProposalDtos.CommitRequest;
import com.shortcut.dto.ProposalDtos.CommitResult;
import com.shortcut.dto.ProposalDtos.CreateProposalRequest;
import com.shortcut.dto.ProposalDtos.ProposalCreated;
import com.shortcut.dto.ProposalDtos.ProposalView;
import com.shortcut.service.ProposalService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/proposals")
public class InternalProposalController {

    private final ProposalService proposals;

    public InternalProposalController(ProposalService proposals) {
        this.proposals = proposals;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProposalCreated create(@Valid @RequestBody CreateProposalRequest request) {
        return proposals.create(request);
    }

    @GetMapping("/{id}")
    public ProposalView get(@PathVariable long id) {
        return proposals.view(id);
    }

    @PostMapping("/{id}/commit")
    public CommitResult commit(@PathVariable long id, @Valid @RequestBody CommitRequest request) {
        return proposals.commit(id, request.dataVersion());
    }
}
