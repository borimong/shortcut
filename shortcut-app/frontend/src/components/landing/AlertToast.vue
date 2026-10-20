<script setup>
import { CloudLightning } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { weatherAlert } from '@/data/demo.js'
</script>

<template>
  <Alert class="border-warning/40 bg-warning/10">
    <CloudLightning class="text-warning-foreground" />
    <AlertTitle class="flex justify-between gap-3">
      {{ weatherAlert.kind }}
      <span class="mono text-xs font-normal text-muted-foreground">22:02</span>
    </AlertTitle>
    <AlertDescription>
      <p>{{ weatherAlert.area }}, {{ weatherAlert.effective }}</p>
      <p class="font-semibold text-warning-foreground">{{ weatherAlert.location }} 촬영에 영향</p>
    </AlertDescription>
  </Alert>
</template>
