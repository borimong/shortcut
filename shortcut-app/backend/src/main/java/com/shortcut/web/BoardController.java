package com.shortcut.web;

import com.shortcut.dto.BoardDtos.BoardResponse;
import com.shortcut.dto.BoardDtos.CallsheetContent;
import com.shortcut.dto.BoardDtos.CallsheetSummary;
import com.shortcut.dto.BoardDtos.HistoryItem;
import com.shortcut.service.BoardService;
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

    public BoardController(BoardService board) {
        this.board = board;
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

    @GetMapping("/history")
    public List<HistoryItem> history(@RequestParam(defaultValue = "1") long shootDayId) {
        return board.history(shootDayId);
    }
}
