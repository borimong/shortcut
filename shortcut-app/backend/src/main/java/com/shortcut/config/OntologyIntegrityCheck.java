package com.shortcut.config;

import com.shortcut.repository.OntologyRepository;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * 온톨로지 노드는 업무 행을 외래키 없이 ID 글자로 가리키므로, 업무 행이 지워지거나 ID 규칙이 바뀌면 그래프만 낡는다.
 * 기동할 때 한 번 맞춰 보고 어긋난 노드를 경고로 남긴다. data.sql을 실행하는 api 프로세스에서만 돈다.
 */
@Component
@Profile("api")
public class OntologyIntegrityCheck implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(OntologyIntegrityCheck.class);

    private final OntologyRepository ontology;

    public OntologyIntegrityCheck(OntologyRepository ontology) {
        this.ontology = ontology;
    }

    @Override
    public void run(String... args) {
        List<String> orphans = ontology.findOrphanNodeIds();
        if (orphans.isEmpty()) {
            log.info("온톨로지 정합성 검사: 모든 노드가 업무 행과 맞습니다.");
        } else {
            log.warn("온톨로지 정합성 검사: 업무 행과 맞지 않는 노드 {}개 {}", orphans.size(), orphans);
        }
    }
}
