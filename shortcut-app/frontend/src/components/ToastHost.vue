<script setup>
import { useToastStore } from '../stores/toast.js'

const toast = useToastStore()
</script>

<template>
  <div class="toasts" aria-live="polite">
    <div v-for="t in toast.items" :key="t.id" class="toast" :class="t.kind" @click="toast.dismiss(t.id)">
      <span>{{ t.message }}</span>
      <span v-if="t.code" class="code mono">{{ t.code }}</span>
    </div>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 16px;
  bottom: 16px;
  left: 16px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  z-index: 100;
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  max-width: 380px;
  width: fit-content;
  background: var(--charcoal);
  color: #fff;
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: var(--shadow);
  font-size: 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  cursor: pointer;
}

.toast.info {
  border-left: 4px solid var(--mint);
}

.toast.error {
  border-left: 4px solid #f87171;
}

.code {
  color: #cbd5e1;
}
</style>
