package com.shortcut.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.domain.AiTask;
import com.shortcut.domain.TaskEvent;
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.BooleanSupplier;
import java.util.function.LongFunction;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 작업별, 사용자별 SSE 연결을 메모리에 들고 있다.
 * api 인스턴스가 하나라는 전제의 단순한 구조이고, 끊긴 클라이언트는 Last-Event-ID로 DB에서 이어 받는다.
 */
@Component
public class SseHub {

    // nginx proxy_read_timeout 3600s와 맞춘다.
    // 끊기면 EventSource가 스스로 다시 붙으므로 더 길게 잡을 이유가 없다.
    private static final long TIMEOUT_MS = Duration.ofHours(1).toMillis();

    private final Map<Long, Set<TaskStream>> taskStreams = new ConcurrentHashMap<>();
    private final Map<String, Set<UserStream>> userStreams = new ConcurrentHashMap<>();
    private final ObjectMapper mapper;

    public SseHub(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    /**
     * 등록, 저장분 재전송, 실시간 전달 사이에 이벤트가 빠지거나 순서가 뒤집히지 않도록
     * 스트림 잠금을 쥔 채로 등록하고 재전송한다.
     * 그 사이 도착한 실시간 이벤트는 잠금을 기다렸다가 이미 보낸 id면 건너뛴다.
     */
    public SseEmitter openTask(long taskId, long afterId, LongFunction<List<TaskEvent>> backlog,
                               BooleanSupplier finished) {
        SseEmitter emitter = new SseEmitter(TIMEOUT_MS);
        TaskStream stream = new TaskStream(taskId, emitter, afterId);
        synchronized (stream) {
            taskStreams.computeIfAbsent(taskId, id -> ConcurrentHashMap.newKeySet()).add(stream);
            emitter.onCompletion(stream::detach);
            emitter.onTimeout(stream::detach);
            emitter.onError(error -> stream.detach());
            backlog.apply(afterId).forEach(stream::deliver);
            if (!stream.closed && finished.getAsBoolean()) {
                stream.close();
            }
        }
        return emitter;
    }

    public void publishTask(TaskEvent event) {
        taskStreams.getOrDefault(event.taskId(), Set.of()).forEach(stream -> stream.deliver(event));
    }

    public SseEmitter openUser(String username) {
        SseEmitter emitter = new SseEmitter(TIMEOUT_MS);
        UserStream stream = new UserStream(username, emitter);
        userStreams.computeIfAbsent(username, name -> ConcurrentHashMap.newKeySet()).add(stream);
        emitter.onCompletion(stream::detach);
        emitter.onTimeout(stream::detach);
        emitter.onError(error -> stream.detach());
        return emitter;
    }

    public void sendToUser(String username, String eventName, String id, Object data) {
        String json = toJson(data);
        userStreams.getOrDefault(username, Set.of()).forEach(stream -> stream.send(eventName, id, json));
    }

    public void broadcast(String eventName, Object data) {
        String json = toJson(data);
        userStreams.values().forEach(streams -> streams.forEach(stream -> stream.send(eventName, null, json)));
    }

    // 프록시와 브라우저가 유휴 연결을 끊지 않도록 15초마다 주석 한 줄을 보낸다.
    @Scheduled(fixedRate = 15_000)
    public void heartbeat() {
        taskStreams.values().forEach(streams -> streams.forEach(TaskStream::ping));
        userStreams.values().forEach(streams -> streams.forEach(UserStream::ping));
    }

    private String toJson(Object data) {
        try {
            return mapper.writeValueAsString(data);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("SSE 데이터를 JSON으로 바꿀 수 없습니다.", e);
        }
    }

    private final class TaskStream {

        private final long taskId;
        private final SseEmitter emitter;
        private long lastSentId;
        private boolean closed;

        private TaskStream(long taskId, SseEmitter emitter, long lastSentId) {
            this.taskId = taskId;
            this.emitter = emitter;
            this.lastSentId = lastSentId;
        }

        synchronized void deliver(TaskEvent event) {
            if (closed || event.id() <= lastSentId) {
                return;
            }
            try {
                emitter.send(SseEmitter.event()
                        .id(String.valueOf(event.id()))
                        .name(event.type())
                        .data(event.payloadJson(), MediaType.APPLICATION_JSON));
                lastSentId = event.id();
            } catch (IOException | IllegalStateException e) {
                detach();
                return;
            }
            if (AiTask.TERMINAL.contains(event.type())) {
                close();
            }
        }

        synchronized void ping() {
            if (closed) {
                return;
            }
            try {
                emitter.send(SseEmitter.event().comment("heartbeat"));
            } catch (IOException | IllegalStateException e) {
                detach();
            }
        }

        synchronized void close() {
            closed = true;
            emitter.complete();
            detach();
        }

        void detach() {
            closed = true;
            Set<TaskStream> streams = taskStreams.get(taskId);
            if (streams != null) {
                streams.remove(this);
            }
        }
    }

    private final class UserStream {

        private final String username;
        private final SseEmitter emitter;

        private UserStream(String username, SseEmitter emitter) {
            this.username = username;
            this.emitter = emitter;
        }

        synchronized void send(String eventName, String id, String json) {
            try {
                SseEmitter.SseEventBuilder event = SseEmitter.event().name(eventName).data(json, MediaType.APPLICATION_JSON);
                emitter.send(id == null ? event : event.id(id));
            } catch (IOException | IllegalStateException e) {
                detach();
            }
        }

        synchronized void ping() {
            try {
                emitter.send(SseEmitter.event().comment("heartbeat"));
            } catch (IOException | IllegalStateException e) {
                detach();
            }
        }

        void detach() {
            Set<UserStream> streams = userStreams.get(username);
            if (streams != null) {
                streams.remove(this);
            }
        }
    }
}
