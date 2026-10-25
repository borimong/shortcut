package com.shortcut.common;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.engine.SceneSlot;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * jsonb 컬럼과 자바 값을 오간다.
 * 웹 응답과 같은 ObjectMapper를 써서 시간 형식이 DB 저장본과 API에서 어긋나지 않게 한다.
 */
@Component
public class JsonColumns {

    private static final TypeReference<List<Long>> LONG_LIST = new TypeReference<>() {
    };
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() {
    };
    private static final TypeReference<List<SceneSlot>> SCENE_SLOTS = new TypeReference<>() {
    };

    private final ObjectMapper mapper;

    public JsonColumns(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public String write(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("JSON으로 바꿀 수 없는 값입니다.", e);
        }
    }

    public JsonNode tree(String json) {
        if (json == null) {
            return null;
        }
        try {
            return mapper.readTree(json);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("저장된 JSON이 깨졌습니다.", e);
        }
    }

    public List<Long> longs(String json) {
        return read(json, LONG_LIST);
    }

    public List<String> strings(String json) {
        return read(json, STRING_LIST);
    }

    /** 씬 시각표다. 씬 순서를 남기기 전에 만든 행은 비어 있어 빈 목록으로 읽는다. */
    public List<SceneSlot> sceneSlots(String json) {
        return json == null ? List.of() : read(json, SCENE_SLOTS);
    }

    private <T> T read(String json, TypeReference<T> type) {
        try {
            return mapper.readValue(json, type);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("저장된 JSON이 깨졌습니다.", e);
        }
    }
}
