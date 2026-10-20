package com.shortcut.common;

import com.shortcut.engine.PlanRuleException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    ResponseEntity<Map<String, Object>> handleApi(ApiException e) {
        Map<String, Object> body = body(e.code(), e.getMessage());
        body.putAll(e.extra());
        return ResponseEntity.status(e.status()).body(body);
    }

    @ExceptionHandler(PlanRuleException.class)
    ResponseEntity<Map<String, Object>> handlePlanRule(PlanRuleException e) {
        return ResponseEntity.badRequest().body(body(e.code(), e.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> handleInvalid(MethodArgumentNotValidException e) {
        FieldError error = e.getBindingResult().getFieldError();
        String message = error == null ? "요청 값이 올바르지 않습니다." : error.getField() + ": " + error.getDefaultMessage();
        return ResponseEntity.badRequest().body(body("VALIDATION_FAILED", message));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    ResponseEntity<Map<String, Object>> handleMethodValidation(HandlerMethodValidationException e) {
        return ResponseEntity.badRequest().body(body("VALIDATION_FAILED", "요청 파라미터가 올바르지 않습니다."));
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MissingServletRequestParameterException.class,
            MethodArgumentTypeMismatchException.class, MissingRequestHeaderException.class})
    ResponseEntity<Map<String, Object>> handleBadRequest(Exception e) {
        return ResponseEntity.badRequest().body(body("BAD_REQUEST", "요청 형식이 올바르지 않습니다."));
    }

    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<Map<String, Object>> handleNoResource(NoResourceFoundException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body("NOT_FOUND", "없는 경로입니다."));
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    ResponseEntity<Map<String, Object>> handleMethod(HttpRequestMethodNotSupportedException e) {
        return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED).body(body("METHOD_NOT_ALLOWED", e.getMessage()));
    }

    // SSE 구독자가 창을 닫으면 생기는 예외라 응답을 쓸 수 없고 기록할 가치도 없다.
    @ExceptionHandler(AsyncRequestNotUsableException.class)
    void handleClosedStream() {
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<Map<String, Object>> handleUnexpected(Exception e) {
        log.error("처리하지 못한 오류", e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(body("INTERNAL_ERROR", "서버 오류가 발생했습니다."));
    }

    private static Map<String, Object> body(String code, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", code);
        body.put("message", message);
        return body;
    }
}
