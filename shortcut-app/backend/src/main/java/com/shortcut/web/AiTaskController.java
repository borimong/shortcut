package com.shortcut.web;

import com.shortcut.dto.ProposalDtos.ApprovalRequest;
import com.shortcut.dto.ProposalDtos.ApprovalResult;
import com.shortcut.dto.TaskDtos.AskRequest;
import com.shortcut.dto.TaskDtos.TaskCreated;
import com.shortcut.dto.TaskDtos.TaskView;
import com.shortcut.security.CurrentUser;
import com.shortcut.service.ProposalService;
import com.shortcut.service.TaskService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/ai/tasks")
public class AiTaskController {

    private final TaskService tasks;
    private final ProposalService proposals;

    public AiTaskController(TaskService tasks, ProposalService proposals) {
        this.tasks = tasks;
        this.proposals = proposals;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    public TaskCreated ask(@AuthenticationPrincipal Jwt jwt, @Valid @RequestBody AskRequest request) {
        return tasks.ask(CurrentUser.from(jwt), request);
    }

    @GetMapping
    public List<TaskView> list(@AuthenticationPrincipal Jwt jwt, @RequestParam(defaultValue = "true") boolean mine) {
        return tasks.list(CurrentUser.from(jwt), mine);
    }

    @GetMapping("/{id}")
    public TaskView get(@PathVariable long id) {
        return tasks.get(id);
    }

    @GetMapping(value = "/{id}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(@PathVariable long id,
                             @RequestHeader(value = "Last-Event-ID", required = false) Long lastEventId) {
        return tasks.stream(id, lastEventId);
    }

    /**
     * 승인 결과에 따라 Agent가 큐에서 이어 받아 처리하므로 202를 준다.
     */
    @PostMapping("/{id}/approval")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public ApprovalResult approval(@AuthenticationPrincipal Jwt jwt, @PathVariable long id,
                                   @Valid @RequestBody ApprovalRequest request) {
        return proposals.decide(CurrentUser.from(jwt), id, request);
    }
}
