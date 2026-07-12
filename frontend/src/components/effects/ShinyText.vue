<template>
  <span class="shiny-text" :style="{ '--dur': duration + 's', '--c1': color, '--c2': shineColor }">
    <slot />
  </span>
</template>

<script setup>
defineProps({
  color: { type: String, default: '#4F46E5' },
  shineColor: { type: String, default: '#A78BFA' },
  duration: { type: Number, default: 3 }
})
</script>

<style scoped>
.shiny-text {
  display: inline;
  color: var(--c1, #4F46E5);
  background: linear-gradient(
    110deg,
    var(--c1, #4F46E5) 0%,
    var(--c1, #4F46E5) 35%,
    var(--c2, #A78BFA) 50%,
    var(--c1, #4F46E5) 65%,
    var(--c1, #4F46E5) 100%
  );
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shinyMove var(--dur, 3s) linear infinite;
}

@keyframes shinyMove {
  0% { background-position: 200% center; }
  100% { background-position: -200% center; }
}
</style>