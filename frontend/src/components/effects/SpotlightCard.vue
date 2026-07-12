<template>
  <div
    ref="cardRef"
    class="spotlight-card"
    @mousemove="onMouseMove"
    @mouseleave="onMouseLeave"
  >
    <slot />
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  spotlightColor: { type: String, default: 'rgba(79, 70, 229, 0.12)' },
  borderColor: { type: String, default: '' }
})

const cardRef = ref(null)
const isHovered = ref(false)

function onMouseMove(e) {
  if (!cardRef.value) return
  const rect = cardRef.value.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  cardRef.value.style.setProperty('--mx', `${x}px`)
  cardRef.value.style.setProperty('--my', `${y}px`)
  cardRef.value.style.setProperty('--sc', props.spotlightColor)
  isHovered.value = true
}

function onMouseLeave() {
  isHovered.value = false
}
</script>

<style scoped>
.spotlight-card {
  position: relative;
  overflow: hidden;
  --mx: 50%;
  --my: 50%;
  --sc: rgba(79, 70, 229, 0.12);
}

.spotlight-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle 400px at var(--mx) var(--my), var(--sc), transparent 80%);
  opacity: 0;
  transition: opacity 0.4s ease;
  pointer-events: none;
  z-index: 0;
}

.spotlight-card:hover::before {
  opacity: 1;
}
</style>