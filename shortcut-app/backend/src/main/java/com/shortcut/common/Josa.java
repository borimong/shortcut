package com.shortcut.common;

/**
 * 앞말의 받침에 맞는 조사를 붙인다. 화면 문구에 "은(는)"처럼 괄호 조사를 쓰지 않으려고 둔다.
 * 한글은 마지막 글자의 받침으로, 숫자와 영문은 읽는 소리로 가른다. "S18"은 "에스 십팔"이라 받침 ㄹ, "카메라 패키지 A"는 "에이"라 받침이 없다.
 * 끝이 괄호면 괄호 앞말을 본다. "배우 B 일정(18:30~21:00 광고)"는 "일정"으로 가른다.
 */
public final class Josa {

    // 받침 없음, ㄹ 받침, 그 밖의 받침이다. 으로/로는 ㄹ 받침을 받침 없음과 같이 다룬다.
    private enum Ending { NONE, RIEUL, OTHER }

    private Josa() {
    }

    /** 은/는 */
    public static String eunNeun(String word) {
        return word + (ending(word) == Ending.NONE ? "는" : "은");
    }

    /** 이/가 */
    public static String iGa(String word) {
        return word + (ending(word) == Ending.NONE ? "가" : "이");
    }

    /** 을/를 */
    public static String eulReul(String word) {
        return word + (ending(word) == Ending.NONE ? "를" : "을");
    }

    /** 과/와 */
    public static String gwaWa(String word) {
        return word + (ending(word) == Ending.NONE ? "와" : "과");
    }

    /** 으로/로 */
    public static String euroRo(String word) {
        return word + (ending(word) == Ending.OTHER ? "으로" : "로");
    }

    private static Ending ending(String word) {
        String text = stripTrailingGroup(word.strip());
        if (text.isEmpty()) {
            return Ending.NONE;
        }
        char last = text.charAt(text.length() - 1);
        if (last >= '가' && last <= '힣') {
            int jong = (last - '가') % 28;
            return jong == 0 ? Ending.NONE : jong == 8 ? Ending.RIEUL : Ending.OTHER;
        }
        if (Character.isDigit(last)) {
            return number(text);
        }
        if (isLatin(last)) {
            return latin(text);
        }
        return Ending.NONE;
    }

    /** 끝에 붙은 괄호 묶음과 따옴표를 떼어 그 앞말을 남긴다. */
    private static String stripTrailingGroup(String text) {
        String rest = text;
        while (!rest.isEmpty()) {
            char last = rest.charAt(rest.length() - 1);
            if (last == '"' || last == '\'' || last == '」' || last == '』') {
                rest = rest.substring(0, rest.length() - 1).strip();
            } else if (last == ')') {
                int depth = 0;
                int open = -1;
                for (int i = rest.length() - 1; i >= 0; i--) {
                    char c = rest.charAt(i);
                    depth += c == ')' ? 1 : c == '(' ? -1 : 0;
                    if (depth == 0) {
                        open = i;
                        break;
                    }
                }
                if (open <= 0) {
                    return rest;
                }
                rest = rest.substring(0, open).strip();
            } else {
                return rest;
            }
        }
        return rest;
    }

    /** 끝 숫자를 읽는 소리로 가른다. 1 일, 3 삼, 6 육, 7 칠, 8 팔은 받침이 있고 10 십, 100 백, 1000 천, 10000 만도 받침이 있다. */
    private static Ending number(String text) {
        int end = text.length();
        int start = end;
        while (start > 0 && (Character.isDigit(text.charAt(start - 1)) || text.charAt(start - 1) == ',')) {
            start--;
        }
        String digits = text.substring(start, end).replace(",", "");
        int zeros = 0;
        while (zeros < digits.length() && digits.charAt(digits.length() - 1 - zeros) == '0') {
            zeros++;
        }
        if (zeros == digits.length()) {
            return Ending.OTHER; // 영
        }
        if (zeros == 0) {
            return switch (digits.charAt(digits.length() - 1)) {
                case '1', '7', '8' -> Ending.RIEUL; // 일, 칠, 팔
                case '3', '6' -> Ending.OTHER; // 삼, 육
                default -> Ending.NONE; // 이, 사, 오, 구
            };
        }
        return Ending.OTHER; // 십, 백, 천, 만, 억은 모두 받침이 있다
    }

    private static boolean isLatin(char c) {
        return c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z';
    }

    /** 단위(km, mm 등)는 우리말로 읽고, 그 밖의 영문은 마지막 글자 이름으로 읽는다. L 엘, R 알은 ㄹ, M 엠, N 엔은 받침이 있다. */
    private static Ending latin(String text) {
        String lower = text.toLowerCase();
        for (String unit : new String[] {"km", "mm", "cm", "kg", "mg", "ml"}) {
            if (lower.endsWith(unit)) {
                return Ending.NONE; // 킬로미터, 밀리미터, 센티미터, 킬로그램, 밀리그램, 밀리리터
            }
        }
        return switch (Character.toUpperCase(text.charAt(text.length() - 1))) {
            case 'L', 'R' -> Ending.RIEUL;
            case 'M', 'N' -> Ending.OTHER;
            default -> Ending.NONE;
        };
    }
}
