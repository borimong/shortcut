<script setup>
import { watch } from 'vue'
import { toast as sonner } from 'vue-sonner'
import { Toaster } from '@/components/ui/sonner'
import 'vue-sonner/style.css'
import { useToastStore } from '../stores/toast.js'

// 화면들은 기존처럼 toast 스토어에 넣고, 실제 표시는 shadcn의 Sonner가 맡는다.
const store = useToastStore()
const shown = new Set()

watch(
  () => store.items.map((t) => t.id),
  () => {
    for (const t of store.items) {
      if (shown.has(t.id)) continue
      shown.add(t.id)
      if (t.kind === 'error') sonner.error(t.message, { description: t.code })
      else sonner(t.message)
    }
  }
)
</script>

<template>
  <Toaster position="bottom-right" rich-colors />
</template>
