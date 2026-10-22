package com.shortcut.engine;

import java.time.LocalTime;
import java.util.List;

/** 같은 촬영일의 다른 블록이다. 같은 배우가 시간이 겹치는 두 블록에 나오는지 볼 때 쓴다. */
public record BlockSlot(String code, LocalTime start, LocalTime end, List<Long> actorIds) {
}
