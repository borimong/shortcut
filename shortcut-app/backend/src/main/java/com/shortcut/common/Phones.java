package com.shortcut.common;

/**
 * 촬영판은 크루 전원이 보는 화면이라 연락처 가운데 자리를 가린다.
 */
public final class Phones {

    private Phones() {
    }

    public static String mask(String phone) {
        if (phone == null) {
            return null;
        }
        String[] parts = phone.split("-");
        if (parts.length != 3) {
            return "***";
        }
        return parts[0] + "-" + "*".repeat(parts[1].length()) + "-" + parts[2];
    }
}
