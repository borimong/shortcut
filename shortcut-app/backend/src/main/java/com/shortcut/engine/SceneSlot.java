package com.shortcut.engine;

import java.time.LocalTime;
import java.util.List;

/** 블록 안 씬 하나의 촬영 시각이다. 블록 시작부터 씬 길이를 차례로 쌓아 만든다. */
public record SceneSlot(String code, LocalTime start, LocalTime end) {

    public static List<String> codes(List<SceneSlot> slots) {
        return slots.stream().map(SceneSlot::code).toList();
    }
}
