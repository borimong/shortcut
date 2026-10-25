package com.shortcut.repository;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.core.io.ClassPathResource;

/** 시드 SQL 파일의 INSERT ... VALUES 행을 DB 없이 읽는다. 시드끼리 맞춰 보는 테스트가 함께 쓴다. */
final class SeedRows {

    private SeedRows() {
    }

    /**
     * INSERT INTO table (열, ...) VALUES (...), (...) 형식의 시드 행을 열 이름 → 값으로 읽는다. 따옴표 값은 벗긴다.
     */
    static List<Map<String, String>> rows(String seed, String table) {
        List<Map<String, String>> rows = new ArrayList<>();
        Matcher insert = Pattern.compile("INSERT INTO " + table + " \\(([^)]*)\\)\\s*VALUES").matcher(seed);
        while (insert.find()) {
            String[] columns = insert.group(1).split(",");
            for (List<String> tuple : tuples(seed, insert.end())) {
                Map<String, String> row = new HashMap<>();
                for (int i = 0; i < columns.length; i++) {
                    row.put(columns[i].strip(), tuple.get(i));
                }
                rows.add(row);
            }
        }
        return rows;
    }

    /**
     * UPDATE table ... FROM (VALUES (...), (...)) AS v (열, ...) 형식으로 덮어쓰는 값을 열 이름 → 값으로 읽는다.
     * 대본 시드가 만든 행에 제작부 값을 얹을 때 이 형식을 쓴다. 같은 표의 UPDATE가 여럿이면 모두 읽으므로 열 이름으로 고른다.
     */
    static List<Map<String, String>> updateRows(String seed, String table) {
        List<Map<String, String>> rows = new ArrayList<>();
        Matcher update = Pattern.compile("UPDATE " + table + "\\b[^;]*?FROM \\(VALUES").matcher(seed);
        Matcher alias = Pattern.compile("\\)\\s*AS v \\(([^)]*)\\)").matcher(seed);
        while (update.find()) {
            if (!alias.find(update.end())) {
                continue;
            }
            String[] columns = alias.group(1).split(",");
            for (List<String> tuple : tuples(seed, update.end())) {
                Map<String, String> row = new HashMap<>();
                for (int i = 0; i < columns.length; i++) {
                    row.put(columns[i].strip(), tuple.get(i));
                }
                rows.add(row);
            }
        }
        return rows;
    }

    /**
     * VALUES 뒤의 괄호 묶음을 값 목록으로 나눈다. 따옴표 안의 쉼표와 괄호는 값의 일부이고, 주석은 건너뛴다.
     * 괄호 밖에서 쉼표와 공백이 아닌 글자(ON CONFLICT, 세미콜론)나 FROM (VALUES ...)를 닫는 괄호가 나오면 VALUES가 끝난 것이다.
     */
    private static List<List<String>> tuples(String seed, int from) {
        List<List<String>> tuples = new ArrayList<>();
        List<String> values = new ArrayList<>();
        StringBuilder value = new StringBuilder();
        boolean quoted = false;
        int depth = 0;
        for (int i = from; i < seed.length(); i++) {
            char c = seed.charAt(i);
            if (c == '\'') {
                quoted = !quoted;
                value.append(c);
            } else if (quoted) {
                value.append(c);
            } else if (c == '-' && seed.startsWith("--", i)) {
                int lineEnd = seed.indexOf('\n', i);
                i = lineEnd < 0 ? seed.length() : lineEnd;
            } else if (c == '(') {
                if (depth++ > 0) {
                    value.append(c);
                }
            } else if (c == ')') {
                if (depth == 0) {
                    break;
                }
                if (--depth > 0) {
                    value.append(c);
                } else {
                    values.add(literal(value));
                    tuples.add(values);
                    values = new ArrayList<>();
                }
            } else if (depth == 1 && c == ',') {
                values.add(literal(value));
            } else if (depth > 0) {
                value.append(c);
            } else if (c != ',' && !Character.isWhitespace(c)) {
                break;
            }
        }
        return tuples;
    }

    private static String literal(StringBuilder raw) {
        String value = raw.toString().strip();
        raw.setLength(0);
        return value.startsWith("'") && value.endsWith("'")
                ? value.substring(1, value.length() - 1).replace("''", "'")
                : value;
    }

    /** 시드 파일을 서버가 넣는 순서대로 이어 붙여 읽는다. */
    static String read(String... paths) {
        StringBuilder text = new StringBuilder();
        for (String path : paths) {
            try {
                text.append(new ClassPathResource(path).getContentAsString(StandardCharsets.UTF_8)).append('\n');
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        }
        return text.toString();
    }
}
