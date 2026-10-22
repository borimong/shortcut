package com.shortcut.domain;

/** 씬에 등장하는 배역이다. actorId가 비어 있으면 아직 캐스팅 전이다. */
public record SceneCharacter(long id, String name, Long actorId) {
}
