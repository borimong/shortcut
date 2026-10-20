<script setup>
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { STATUS } from '../labels.js'

const props = defineProps({ status: { type: String, default: '' } })

// labels.js의 상태 톤을 shadcn Badge 변형으로 옮긴다
const VARIANT = { ok: 'success', wait: 'secondary', bad: 'destructive', stale: 'warning', run: 'info' }
const entry = computed(() => STATUS[props.status] ?? [props.status, 'wait'])
</script>

<template>
  <Badge :variant="VARIANT[entry[1]] ?? 'secondary'">{{ entry[0] }}</Badge>
</template>
