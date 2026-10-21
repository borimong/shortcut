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
import com.shortcut.dto.TaskDtos.EventResponse;
import com.shortcut.security.JwtService;
import com.shortcut.service.EventService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(EventController.class)
@Import(SecurityConfig.class)
@EnableConfigurationProperties(ShortcutProperties.class)
class EventControllerTest {

    private static final String BODY = """
            {"type": "RAIN", "detail": "13시 이후 한강 시간당 8mm 비", "instruction": "웃돈을 줘도 좋은 데로"}
            """;

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ShortcutProperties properties;

    @MockitoBean
    private EventService events;

    @Test
    void 토큰이_없으면_401이다() throws Exception {
        mvc.perform(post("/api/events").contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void 새_변동은_202와_작업_id를_준다() throws Exception {
        given(events.create(any(), any())).willReturn(new EventResponse(7, 11, null));

        mvc.perform(post("/api/events").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.eventId").value(7))
                .andExpect(jsonPath("$.taskId").value(11))
                .andExpect(jsonPath("$.duplicate").doesNotExist());
    }

    @Test
    void 같은_변동을_다시_보내면_200과_duplicate를_준다() throws Exception {
        given(events.create(any(), any())).willReturn(new EventResponse(7, 11, true));

        mvc.perform(post("/api/events").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.duplicate").value(true));
    }

    @Test
    void 정해지지_않은_변동_유형은_400이다() throws Exception {
        mvc.perform(post("/api/events").header("Authorization", bearer())
                        .contentType(MediaType.APPLICATION_JSON).content("{\"type\": \"ALIENS\", \"detail\": \"x\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    }

    @Test
    void 쿼리_토큰은_SSE_경로가_아니면_받지_않는다() throws Exception {
        mvc.perform(post("/api/events").param("access_token", token())
                        .contentType(MediaType.APPLICATION_JSON).content(BODY))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void 내부_경로는_JWT가_있어도_내부_토큰이_없으면_401이다() throws Exception {
        mvc.perform(get("/internal/shoot-days/1/plan-set").header("Authorization", bearer()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("INVALID_INTERNAL_TOKEN"));
    }

    private String bearer() {
        return "Bearer " + token();
    }

    private String token() {
        UserAccount ad1 = new UserAccount(3, "director", "hash", "강민재", "DIRECTOR", "DIRECTING", "연출 PD (연출감독)", null, true, true);
        return new JwtService(properties).issue(ad1);
    }
}
