package com.shortcut.domain;

public record OutboxMessage(long id, String routingKey, String payloadJson) {
}
