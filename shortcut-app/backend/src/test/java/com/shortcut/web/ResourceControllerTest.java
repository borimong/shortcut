package com.shortcut.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.shortcut.config.SecurityConfig;
import com.shortcut.config.ShortcutProperties;
import com.shortcut.domain.UserAccount;
import com.shortcut.dto.ResourceDtos.ResourceChangeResult;
import com.shortcut.security.JwtService;
import com.shortcut.service.EventService;
import com.shortcut.service.ResourceService;
import com.shortcut.service.ScheduleService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ResourceController.class)
@Import(SecurityConfig.class)
@EnableConfigurationProperties(ShortcutProperties.class)
class ResourceControllerTest {

    private static final String BODY = """
            {"dataVersion": 5, "replan": false,
             "changes": [{"kind": "EQUIPMENT_UNAVAILABLE", "targetId": 2, "status": "REPAIR", "untilDate": "2026-10-25"}]}
            """;

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ShortcutProperties properties;

    @MockitoBean
    private ResourceService resources;

    @MockitoBean
    private EventService events;

    @MockitoBean
    private ScheduleService schedules;

    @Test
    void 토큰이_없으면_401이다() throws Exception {
        mvc.perform(get("/api/resources"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void 상태만_바꾸면_200이다() throws Exception {
        given(events.applyResources(any(), any())).willReturn(new ResourceChangeResult(30, null, 6, 1));

        mvc.perform(post("/api/resources/changes").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.dataVersion").value(6))
                .andExpect(jsonPath("$.superseded").value(1));
    }

    @Test
    void 재계획을_함께_요청하면_202다() throws Exception {
        given(events.applyResources(any(), any())).willReturn(new ResourceChangeResult(30, 40L, 6, 0));

        mvc.perform(post("/api/resources/changes").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.taskId").value(40));
    }

    @Test
    void 정해지지_않은_상태는_400이다() throws Exception {
        String body = """
                {"dataVersion": 5, "changes": [{"kind": "EQUIPMENT_UNAVAILABLE", "targetId": 2, "status": "LOST"}]}
                """;
        mvc.perform(post("/api/resources/changes").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    }

    @Test
    void 데이터_버전이_없으면_400이다() throws Exception {
        mvc.perform(post("/api/resources/changes").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"changes\": []}"))
                .andExpect(status().isBadRequest());
    }

    private String bearer() {
        UserAccount pd = new UserAccount(1, "pd", "hash", "한서윤", "PRODUCER", "PRODUCTION", "제작 PD", null, true, true);
        return "Bearer " + new JwtService(properties).issue(pd);
    }
}
