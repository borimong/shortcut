package com.shortcut.domain;

/**
 * 변경안(proposals.status)과 승인(approvals.status)의 상태 값이다. DB에 이 문자열 그대로 저장한다.
 * SQL 안의 상태 값은 저장소 클래스에 그대로 적혀 있으므로, 값을 바꿀 때는 저장소도 함께 고친다.
 */
public final class ProposalStatus {

    public static final String PENDING = "PENDING";
    public static final String APPROVED = "APPROVED";
    public static final String REJECTED = "REJECTED";
    /** 승인 대기 중 촬영 데이터가 바뀌어 무효가 된 변경안이다. */
    public static final String STALE = "STALE";
    public static final String COMMITTED = "COMMITTED";
    /** 재계획을 중단하면서 함께 거둔 변경안이다(CancelService). */
    public static final String WITHDRAWN = "WITHDRAWN";
    /** 다른 승인자의 거절이나 무효로 더 받을 필요가 없어진 승인이다. */
    public static final String CANCELLED = "CANCELLED";

    private ProposalStatus() {
    }
}
