package com.shortcut.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.shortcut.config.RabbitTopology;
import com.shortcut.repository.JobLogRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * jobs.callsheet 소비자다.
 * 실패하면 원본을 nack하지 않고 attempt를 올려 retry 큐로 다시 발행한 뒤 원본은 ack한다.
 * 브로커의 requeue에 맡기면 횟수를 셀 수 없고 즉시 재전달되어 같은 오류를 반복하기 때문이다.
 */
@Component
@Profile("worker")
public class CallsheetJobListener {

    private static final Logger log = LoggerFactory.getLogger(CallsheetJobListener.class);

    private final CallsheetDistributor distributor;
    private final JobLogRepository jobLogs;
    private final RabbitTemplate rabbit;
    private final ObjectMapper mapper;

    public CallsheetJobListener(CallsheetDistributor distributor, JobLogRepository jobLogs, RabbitTemplate rabbit,
                                ObjectMapper mapper) {
        this.distributor = distributor;
        this.jobLogs = jobLogs;
        this.rabbit = rabbit;
        this.mapper = mapper;
    }

    @RabbitListener(queues = RabbitTopology.JOBS_CALLSHEET)
    public void onMessage(Message message) {
        int attempt = attemptOf(message);
        String messageId = message.getMessageProperties().getMessageId();
        try {
            distributor.distribute(mapper.readTree(message.getBody()), messageId, attempt);
        } catch (Exception e) {
            int next = attempt + 1;
            boolean exhausted = next > RabbitTopology.MAX_ATTEMPTS;
            String target = RabbitTopology.JOBS_CALLSHEET + (exhausted ? RabbitTopology.DLQ_SUFFIX : RabbitTopology.RETRY_SUFFIX);
            // 재발행이 실패하면 예외가 컨테이너로 올라가 원본이 requeue되므로 메시지는 잃지 않는다.
            rabbit.send(RabbitTopology.EXCHANGE, target, MessageBuilder.fromClonedMessage(message)
                    .setHeader(RabbitTopology.ATTEMPT_HEADER, next)
                    .build());
            jobLogs.insert(RabbitTopology.JOBS_CALLSHEET, messageId, attempt, exhausted ? "DLQ" : "RETRY", e.getMessage());
            log.warn("콜시트 배포 실패 attempt={} -> {}: {}", attempt, target, e.getMessage());
        }
    }

    private static int attemptOf(Message message) {
        Object header = message.getMessageProperties().getHeaders().get(RabbitTopology.ATTEMPT_HEADER);
        // 헤더 없이 들어온 메시지는 첫 시도로 본다.
        return header instanceof Number number ? number.intValue() : 1;
    }
}
