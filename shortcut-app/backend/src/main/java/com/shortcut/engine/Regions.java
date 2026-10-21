package com.shortcut.engine;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 재난 문자 지역과 장소 지역을 비교한다.
 * 재난 문자는 "서울특별시 영등포구"처럼 정식 이름으로, 장소는 "서울 영등포구"처럼 줄여 적어서 글자가 그대로 같지 않다.
 * 시도 이름을 줄임말로 바꾸고 공백을 뺀 뒤, 재난 문자 지역이 장소 지역의 앞부분이면 같은 지역으로 본다.
 * 그래서 "서울" 재난 문자는 서울의 모든 구에 걸리고 "서울 성동구" 재난 문자는 영등포구 장소에 걸리지 않는다.
 */
public final class Regions {

    // 긴 이름을 먼저 바꿔야 "강원특별자치도"가 "강원도" 규칙에 먼저 걸리지 않는다.
    private static final Map<String, String> PROVINCES = new LinkedHashMap<>();

    static {
        PROVINCES.put("서울특별시", "서울");
        PROVINCES.put("서울시", "서울");
        PROVINCES.put("부산광역시", "부산");
        PROVINCES.put("대구광역시", "대구");
        PROVINCES.put("인천광역시", "인천");
        PROVINCES.put("광주광역시", "광주");
        PROVINCES.put("대전광역시", "대전");
        PROVINCES.put("울산광역시", "울산");
        PROVINCES.put("세종특별자치시", "세종");
        PROVINCES.put("경기도", "경기");
        PROVINCES.put("강원특별자치도", "강원");
        PROVINCES.put("강원도", "강원");
        PROVINCES.put("충청북도", "충북");
        PROVINCES.put("충청남도", "충남");
        PROVINCES.put("전북특별자치도", "전북");
        PROVINCES.put("전라북도", "전북");
        PROVINCES.put("전라남도", "전남");
        PROVINCES.put("경상북도", "경북");
        PROVINCES.put("경상남도", "경남");
        PROVINCES.put("제주특별자치도", "제주");
    }

    private Regions() {
    }

    /** 공백을 빼고 맨 앞 시도 이름을 줄임말로 바꾼다. "서울특별시 영등포구"와 "서울 영등포구"는 둘 다 "서울영등포구"가 된다. */
    public static String normalize(String region) {
        if (region == null) {
            return "";
        }
        String compact = region.replaceAll("\\s+", "");
        for (Map.Entry<String, String> e : PROVINCES.entrySet()) {
            if (compact.startsWith(e.getKey())) {
                return e.getValue() + compact.substring(e.getKey().length());
            }
        }
        return compact;
    }

    /** 재난 문자 지역이 장소 지역을 포함하면 true다. 지역이 비어 있으면 아무 곳에도 걸지 않는다. */
    public static boolean covers(String alertRegion, String locationRegion) {
        String alert = normalize(alertRegion);
        return !alert.isEmpty() && normalize(locationRegion).startsWith(alert);
    }
}
