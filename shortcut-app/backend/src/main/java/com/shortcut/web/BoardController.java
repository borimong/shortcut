package com.shortcut.web;

import com.shortcut.dto.BoardDtos.BoardResponse;
import com.shortcut.dto.BoardDtos.CallsheetContent;
import com.shortcut.dto.BoardDtos.CallsheetSummary;
import com.shortcut.dto.BoardDtos.HistoryItem;
import com.shortcut.dto.PlanDtos.WeatherResponse;
import com.shortcut.service.BoardService;
import com.shortcut.service.ShootDayQueryService;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class BoardController {

    private final BoardService board;
    private final ShootDayQueryService shootDays;

    public BoardController(BoardService board, ShootDayQueryService shootDays) {
        this.board = board;
        this.shootDays = shootDays;
    }

    @GetMapping("/board/today")
    public BoardResponse today() {
        return board.today();
    }

    @GetMapping("/callsheets")
    public List<CallsheetSummary> callsheets(@RequestParam(defaultValue = "1") long shootDayId) {
        return board.callsheets(shootDayId);
    }

    @GetMapping("/callsheets/{shootDayId}/{versionNo}")
    public CallsheetContent callsheet(@PathVariable long shootDayId, @PathVariable int versionNo) {
        return board.callsheet(shootDayId, versionNo);
    }

    /** 촬영일의 장소별 시간당 강수량과 예보 출처다. 변경 입력의 우천 칸이 고른 장소의 예보로 채워질 때 쓴다. */
    @GetMapping("/weather")
    public WeatherResponse weather(@RequestParam(defaultValue = "1") long shootDayId) {
        return shootDays.weather(shootDayId);
    }

    @GetMapping("/history")
    public List<HistoryItem> history(@RequestParam(defaultValue = "1") long shootDayId) {
        return board.history(shootDayId);
    }
}
