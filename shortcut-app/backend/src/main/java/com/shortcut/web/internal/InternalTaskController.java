package com.shortcut.web.internal;

import com.shortcut.dto.TaskDtos.InternalTaskView;
import com.shortcut.dto.TaskDtos.TaskEventRequest;
import com.shortcut.service.TaskService;
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
@RequestMapping("/internal/ai/tasks")
public class InternalTaskController {

    private final TaskService tasks;

    public InternalTaskController(TaskService tasks) {
        this.tasks = tasks;
    }

    @PostMapping("/{id}/events")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void appendEvent(@PathVariable long id, @Valid @RequestBody TaskEventRequest request) {
        tasks.appendEvent(id, request);
    }

    @GetMapping("/{id}")
    public InternalTaskView get(@PathVariable long id) {
        return tasks.internalGet(id);
    }
}
