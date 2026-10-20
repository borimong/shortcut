<script setup>
import { computed } from 'vue'
import { STATUS } from '../labels.js'

const props = defineProps({ status: { type: String, default: '' } })
const entry = computed(() => STATUS[props.status] ?? [props.status, 'wait'])
</script>

<template>
  <span class="badge" :class="`tone-${entry[1]}`">{{ entry[0] }}</span>
</template>
