<template>
  <div ref="containerRef" class="click-spark-wrapper" @click="onClick">
    <canvas ref="canvasRef" class="click-spark-canvas"></canvas>
    <slot />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  sparkColor: { type: String, default: '#4F46E5' },
  sparkSize: { type: Number, default: 10 },
  sparkRadius: { type: Number, default: 25 },
  sparkCount: { type: Number, default: 8 },
  duration: { type: Number, default: 400 }
})

const containerRef = ref(null)
const canvasRef = ref(null)
const sparks = []
let animationId = null

function resizeCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  canvas.width = window.innerWidth
  canvas.height = window.innerHeight
}

function easeOut(t) {
  return t * (2 - t)
}

function draw(timestamp) {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  for (let i = sparks.length - 1; i >= 0; i--) {
    const spark = sparks[i]
    const elapsed = timestamp - spark.startTime
    if (elapsed >= props.duration) {
      sparks.splice(i, 1)
      continue
    }

    const progress = elapsed / props.duration
    const eased = easeOut(progress)
    const distance = eased * props.sparkRadius
    const lineLen = props.sparkSize * (1 - eased)

    const x1 = spark.x + distance * Math.cos(spark.angle)
    const y1 = spark.y + distance * Math.sin(spark.angle)
    const x2 = spark.x + (distance + lineLen) * Math.cos(spark.angle)
    const y2 = spark.y + (distance + lineLen) * Math.sin(spark.angle)

    ctx.strokeStyle = props.sparkColor
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.globalAlpha = 1 - eased
    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)
    ctx.stroke()
  }
  ctx.globalAlpha = 1

  if (sparks.length > 0) animationId = requestAnimationFrame(draw)
  else animationId = null
}

function onClick(e) {
  const x = e.clientX
  const y = e.clientY
  const now = performance.now()

  for (let i = 0; i < props.sparkCount; i++) {
    sparks.push({
      x, y,
      angle: (2 * Math.PI * i) / props.sparkCount,
      startTime: now
    })
  }

  if (!animationId) animationId = requestAnimationFrame(draw)
}

onMounted(() => {
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', resizeCanvas)
})
</script>

<style scoped>
.click-spark-wrapper {
  width: 100%;
  min-height: 100%;
}

.click-spark-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: 9999;
}
</style>
