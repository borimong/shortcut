package com.shortcut.config;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarable;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * agent와 같은 인자로 큐를 선언한다.
 * 인자가 하나라도 다르면 RabbitMQ가 선언을 거부하므로 값은 명세 그대로 둔다.
 */
@Configuration
public class RabbitTopology {

    public static final String EXCHANGE = "shortcut";
    public static final String AGENT_TASKS = "agent.tasks";
    public static final String JOBS_CALLSHEET = "jobs.callsheet";
    public static final String RETRY_SUFFIX = ".retry";
    public static final String DLQ_SUFFIX = ".dlq";
    public static final String ATTEMPT_HEADER = "x-attempt";
    public static final int MAX_ATTEMPTS = 3;
    // 재시도 대기 5초는 일시 장애가 풀릴 여유를 주면서 시연 중 기다림이 길지 않은 값이다.
    private static final int RETRY_DELAY_MS = 5000;

    @Bean
    DirectExchange shortcutExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Declarables shortcutQueues(DirectExchange shortcutExchange) {
        List<Declarable> declarables = new ArrayList<>();
        for (String name : List.of(AGENT_TASKS, JOBS_CALLSHEET)) {
            Queue main = QueueBuilder.durable(name).build();
            // retry 큐에는 소비자가 없고 TTL이 지나면 dead letter로 원래 큐에 돌아간다.
            Queue retry = QueueBuilder.durable(name + RETRY_SUFFIX)
                    .withArguments(Map.of(
                            "x-message-ttl", RETRY_DELAY_MS,
                            "x-dead-letter-exchange", EXCHANGE,
                            "x-dead-letter-routing-key", name))
                    .build();
            Queue dlq = QueueBuilder.durable(name + DLQ_SUFFIX).build();
            for (Queue queue : List.of(main, retry, dlq)) {
                declarables.add(queue);
                declarables.add(bind(queue, shortcutExchange));
            }
        }
        return new Declarables(declarables);
    }

    private static Binding bind(Queue queue, DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(queue.getName());
    }
}
