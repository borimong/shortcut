package com.shortcut.service;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.Callsheet;
import com.shortcut.dto.TaskDtos.AskRequest;
import com.shortcut.repository.*;
import com.shortcut.security.CurrentUser;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class TaskQuestionContextTest {
    @Test void implicitQuestionUsesCommittedProposalFromSameShootDay() {
        var tasks=mock(TaskRepository.class);
        var plans=mock(PlanDataService.class);
        var callsheets=mock(CallsheetRepository.class);
        when(plans.boardShootDayId()).thenReturn(1L);
        when(callsheets.findLatest(1L)).thenReturn(Optional.of(new Callsheet(1,1,2,42L,null,null)));
        when(tasks.insertTask(eq("ASK"),anyString(),isNull(),eq(42L),eq(1L),anyString(),anyString(),eq("ask-"))).thenReturn(8L);
        when(tasks.findTask(8L)).thenReturn(Optional.of(mock(AiTask.class)));
        var service=new TaskService(tasks,mock(ProposalRepository.class),plans,mock(OutboxService.class),mock(SseHub.class),mock(com.shortcut.common.JsonColumns.class),callsheets);
        service.ask(new CurrentUser("manager","PRODUCTION_MANAGER","test","test"),new AskRequest("이번 확정의 근거",null));
        verify(tasks).insertTask(eq("ASK"),eq("이번 확정의 근거"),isNull(),eq(42L),eq(1L),eq("manager"),anyString(),eq("ask-"));
    }
    @Test void baselineQuestionDoesNotInventAProposal() {
        var tasks=mock(TaskRepository.class);
        var plans=mock(PlanDataService.class);
        var callsheets=mock(CallsheetRepository.class);
        when(plans.boardShootDayId()).thenReturn(1L);
        when(callsheets.findLatest(1L)).thenReturn(Optional.of(new Callsheet(1,1,1,null,null,null)));
        when(tasks.insertTask(eq("ASK"),anyString(),isNull(),isNull(),eq(1L),anyString(),anyString(),eq("ask-"))).thenReturn(8L);
        when(tasks.findTask(8L)).thenReturn(Optional.of(mock(AiTask.class)));
        var service=new TaskService(tasks,mock(ProposalRepository.class),plans,mock(OutboxService.class),mock(SseHub.class),mock(com.shortcut.common.JsonColumns.class),callsheets);
        service.ask(new CurrentUser("manager","PRODUCTION_MANAGER","test","test"),new AskRequest("근거",null));
        verify(tasks).insertTask(eq("ASK"),eq("근거"),isNull(),isNull(),eq(1L),eq("manager"),anyString(),eq("ask-"));
    }
}
