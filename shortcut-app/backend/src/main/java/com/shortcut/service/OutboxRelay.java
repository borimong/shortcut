package com.shortcut.service;

import com.shortcut.config.RabbitTopology;
import com.shortcut.domain.OutboxMessage;
import com.shortcut.repository.OutboxRepository;
import java.nio.charset.StandardCharsets;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("api")
public class OutboxRelay {

    private static final Logger log = LoggerFactory.getLogger(OutboxRelay.class);
    // 한 주기에 50건이면 시연 트래픽을 넉넉히 비우면서 행 잠금 시간을 짧게 유지한다.
    private static final int BATCH_SIZE = 50;
    // 브로커 확인이 5초 안에 없으면 실패로 보고 다음 주기에 다시 보낸다.
    private static final long CONFIRM_TIMEOUT_MS = 5_000;

    private final OutboxRepository outbox;
    private final RabbitTemplate rabbit;
    private final TransactionTemplate transaction;

    public OutboxRelay(OutboxRepository outbox, RabbitTemplate rabbit, TransactionTemplate transaction) {
        this.outbox = outbox;
        this.rabbit = rabbit;
        this.transaction = transaction;
    }

    @Scheduled(fixedDelay = 1_000)
    public void relay() {
        transaction.executeWithoutResult(status -> {
            for (OutboxMessage message : outbox.lockNewBatch(BATCH_SIZE)) {
                try {
                    publish(message);
                    outbox.markSent(message.id());
                } catch (AmqpException e) {
                    outbox.markFailed(message.id(), e.getMessage());
                    log.warn("outbox {} 발행 실패, 다음 주기에 다시 보냅니다: {}", message.id(), e.getMessage());
                    // 브로커 장애면 나머지도 실패하고 순서만 뒤섞이므로 이번 주기는 멈춘다.
                    break;
                }
            }
        });
    }

    /**
     * 발행 확인을 기다린 뒤에만 SENT로 바꿔 브로커가 받지 못한 메시지를 보낸 것으로 착각하지 않는다.
     * 확인 직후 DB 갱신이 실패하면 같은 메시지가 다시 나갈 수 있어 소비자는 중복 수신을 견뎌야 한다.
     */
    private void publish(OutboxMessage message) {
        Message amqp = MessageBuilder.withBody(message.payloadJson().getBytes(StandardCharsets.UTF_8))
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding(StandardCharsets.UTF_8.name())
                .setMessageId("outbox-" + message.id())
                .setDeliveryMode(MessageDeliveryMode.PERSISTENT)
                .setHeader(RabbitTopology.ATTEMPT_HEADER, 1)
                .build();
        rabbit.invoke(operations -> {
            operations.send(RabbitTopology.EXCHANGE, message.routingKey(), amqp);
            operations.waitForConfirmsOrDie(CONFIRM_TIMEOUT_MS);
            return null;
        });
    }
}
