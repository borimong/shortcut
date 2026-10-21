import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api.js'

// 촬영판은 서버가 고른 촬영일(오늘 이후 가장 가까운 날)을 보여 준다. 변경 입력, 이력, 변경안, 자원 현황도 같은 촬영일을 보도록 한곳에 둔다.
export const useShootDayStore = defineStore('shootDay', () => {
  const id = ref(null)
  let pending = null

  // 촬영판을 읽을 때마다 서버가 고른 촬영일로 맞춘다.
  function setFromBoard(board) {
    if (board?.shootDay?.id != null) id.value = board.shootDay.id
  }

  // 아직 모르면 촬영판을 한 번 읽어 정한다. 여러 화면이 동시에 불러도 요청은 하나만 보낸다.
  async function ensure() {
    if (id.value != null) return id.value
    pending ??= api('/board/today')
      .then(setFromBoard)
      .finally(() => (pending = null))
    await pending
    return id.value
  }

  return { id, setFromBoard, ensure }
})
