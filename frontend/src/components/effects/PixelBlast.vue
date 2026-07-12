<template>
  <div
    ref="containerRef"
    class="pixel-blast"
    :class="{ 'pixel-blast--fixed': fixed }"
    aria-hidden="true"
  ></div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { Effect, EffectComposer, EffectPass, RenderPass } from 'postprocessing'
import * as THREE from 'three'

const props = defineProps({
  variant: { type: String, default: 'square' },
  pixelSize: { type: Number, default: 4 },
  color: { type: String, default: '#7C3AED' },
  patternScale: { type: Number, default: 2 },
  patternDensity: { type: Number, default: 1 },
  pixelSizeJitter: { type: Number, default: 0 },
  enableRipples: { type: Boolean, default: true },
  rippleIntensity: { type: Number, default: 1 },
  rippleThickness: { type: Number, default: 0.1 },
  rippleSpeed: { type: Number, default: 0.3 },
  liquid: { type: Boolean, default: false },
  liquidStrength: { type: Number, default: 0.025 },
  liquidRadius: { type: Number, default: 1 },
  liquidWobbleSpeed: { type: Number, default: 4.5 },
  speed: { type: Number, default: 0.5 },
  edgeFade: { type: Number, default: 0.5 },
  fixed: { type: Boolean, default: false },
  frameRate: { type: Number, default: 30 },
  resolutionScale: { type: Number, default: 0.7 },
  mobileResolutionScale: { type: Number, default: 0.58 }
})

const SHAPE_MAP = { square: 0, circle: 1, triangle: 2, diamond: 3 }
const MAX_CLICKS = 10
const containerRef = ref(null)
let state = null

const VERTEX_SHADER = `
void main() {
  gl_Position = vec4(position, 1.0);
}
`

const FRAGMENT_SHADER = `
precision highp float;

uniform vec3 uColor;
uniform vec2 uResolution;
uniform float uTime;
uniform float uPixelSize;
uniform float uScale;
uniform float uDensity;
uniform float uPixelJitter;
uniform int uEnableRipples;
uniform float uRippleSpeed;
uniform float uRippleThickness;
uniform float uRippleIntensity;
uniform float uEdgeFade;
uniform int uShapeType;

const int SHAPE_CIRCLE = 1;
const int SHAPE_TRIANGLE = 2;
const int SHAPE_DIAMOND = 3;
const int MAX_CLICKS = 10;

uniform vec2 uClickPos[MAX_CLICKS];
uniform float uClickTimes[MAX_CLICKS];
out vec4 fragColor;

float Bayer2(vec2 a) {
  a = floor(a);
  return fract(a.x / 2.0 + a.y * a.y * 0.75);
}
#define Bayer4(a) (Bayer2(0.5 * (a)) * 0.25 + Bayer2(a))
#define Bayer8(a) (Bayer4(0.5 * (a)) * 0.25 + Bayer2(a))

float hash11(float n) { return fract(sin(n) * 43758.5453); }

float vnoise(vec3 p) {
  vec3 ip = floor(p);
  vec3 fp = fract(p);
  float n000 = hash11(dot(ip + vec3(0,0,0), vec3(1,57,113)));
  float n100 = hash11(dot(ip + vec3(1,0,0), vec3(1,57,113)));
  float n010 = hash11(dot(ip + vec3(0,1,0), vec3(1,57,113)));
  float n110 = hash11(dot(ip + vec3(1,1,0), vec3(1,57,113)));
  float n001 = hash11(dot(ip + vec3(0,0,1), vec3(1,57,113)));
  float n101 = hash11(dot(ip + vec3(1,0,1), vec3(1,57,113)));
  float n011 = hash11(dot(ip + vec3(0,1,1), vec3(1,57,113)));
  float n111 = hash11(dot(ip + vec3(1,1,1), vec3(1,57,113)));
  vec3 w = fp * fp * fp * (fp * (fp * 6.0 - 15.0) + 10.0);
  float x00 = mix(n000, n100, w.x);
  float x10 = mix(n010, n110, w.x);
  float x01 = mix(n001, n101, w.x);
  float x11 = mix(n011, n111, w.x);
  return mix(mix(x00, x10, w.y), mix(x01, x11, w.y), w.z) * 2.0 - 1.0;
}

float fbm(vec2 uv, float t) {
  vec3 p = vec3(uv * uScale, t);
  float sum = 1.0;
  float amp = 1.0;
  float freq = 1.0;
  for (int i = 0; i < 5; i++) {
    sum += amp * vnoise(p * freq);
    freq *= 1.25;
  }
  return sum * 0.5 + 0.5;
}

float circleMask(vec2 p, float coverage) {
  float radius = sqrt(coverage) * 0.25;
  float distanceToEdge = length(p - 0.5) - radius;
  float aa = 0.5 * fwidth(distanceToEdge);
  return coverage * (1.0 - smoothstep(-aa, aa, distanceToEdge * 2.0));
}

float triangleMask(vec2 p, vec2 id, float coverage) {
  if (mod(id.x + id.y, 2.0) > 0.5) p.x = 1.0 - p.x;
  float distanceToEdge = p.y - sqrt(coverage) * (1.0 - p.x);
  return coverage * clamp(0.5 - distanceToEdge / fwidth(distanceToEdge), 0.0, 1.0);
}

float diamondMask(vec2 p, float coverage) {
  float radius = sqrt(coverage) * 0.564;
  return step(abs(p.x - 0.49) + abs(p.y - 0.49), radius);
}

void main() {
  vec2 fragCoord = gl_FragCoord.xy - uResolution * 0.5;
  float aspect = uResolution.x / uResolution.y;
  vec2 pixelId = floor(fragCoord / uPixelSize);
  vec2 pixelUV = fract(fragCoord / uPixelSize);
  float cellSize = 8.0 * uPixelSize;
  vec2 cellCoord = floor(fragCoord / cellSize) * cellSize;
  vec2 uv = cellCoord / uResolution * vec2(aspect, 1.0);

  float base = fbm(uv, uTime * 0.05) * 0.5 - 0.65;
  float feed = base + (uDensity - 0.5) * 0.3;

  if (uEnableRipples == 1) {
    for (int i = 0; i < MAX_CLICKS; i++) {
      vec2 pos = uClickPos[i];
      if (pos.x < 0.0) continue;
      vec2 clickUV = ((pos - uResolution * 0.5 - cellSize * 0.5) / uResolution) * vec2(aspect, 1.0);
      float elapsed = max(uTime - uClickTimes[i], 0.0);
      float radius = distance(uv, clickUV);
      float ring = exp(-pow((radius - uRippleSpeed * elapsed) / uRippleThickness, 2.0));
      float attenuation = exp(-elapsed) * exp(-10.0 * radius);
      feed = max(feed, ring * attenuation * uRippleIntensity);
    }
  }

  float coverage = step(0.5, feed + Bayer8(fragCoord / uPixelSize) - 0.5);
  float jitter = fract(sin(dot(pixelId, vec2(127.1, 311.7))) * 43758.5453);
  coverage *= 1.0 + (jitter - 0.5) * uPixelJitter;

  float mask;
  if (uShapeType == SHAPE_CIRCLE) mask = circleMask(pixelUV, coverage);
  else if (uShapeType == SHAPE_TRIANGLE) mask = triangleMask(pixelUV, pixelId, coverage);
  else if (uShapeType == SHAPE_DIAMOND) mask = diamondMask(pixelUV, coverage);
  else mask = coverage;

  if (uEdgeFade > 0.0) {
    vec2 normalized = gl_FragCoord.xy / uResolution;
    float edge = min(min(normalized.x, normalized.y), min(1.0 - normalized.x, 1.0 - normalized.y));
    mask *= smoothstep(0.0, uEdgeFade, edge);
  }

  vec3 srgb = mix(
    uColor * 12.92,
    1.055 * pow(uColor, vec3(1.0 / 2.4)) - 0.055,
    step(0.0031308, uColor)
  );
  fragColor = vec4(srgb, mask);
}
`

function createTouchTexture() {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')
  const texture = new THREE.CanvasTexture(canvas)
  texture.minFilter = THREE.LinearFilter
  texture.magFilter = THREE.LinearFilter
  texture.generateMipmaps = false
  const trail = []
  let last = null
  const maxAge = 64

  function addTouch(point) {
    let force = 0
    let vx = 0
    let vy = 0
    if (last) {
      const dx = point.x - last.x
      const dy = point.y - last.y
      const distance = Math.hypot(dx, dy)
      if (!distance) return
      vx = dx / distance
      vy = dy / distance
      force = Math.min((dx * dx + dy * dy) * 10000, 1)
    }
    last = point
    trail.push({ ...point, vx, vy, force, age: 0 })
  }

  function update() {
    context.fillStyle = '#000'
    context.fillRect(0, 0, size, size)
    for (let i = trail.length - 1; i >= 0; i--) {
      const point = trail[i]
      const remaining = 1 - point.age / maxAge
      point.x += point.vx * point.force * remaining / maxAge
      point.y += point.vy * point.force * remaining / maxAge
      point.age++
      if (point.age > maxAge) {
        trail.splice(i, 1)
        continue
      }
      const intensity = Math.sin(Math.min(point.age / (maxAge * 0.3), 1) * Math.PI / 2) * remaining * point.force
      const radius = size * 0.1 * props.liquidRadius
      const gradient = context.createRadialGradient(point.x * size, (1 - point.y) * size, 0, point.x * size, (1 - point.y) * size, radius)
      gradient.addColorStop(0, `rgba(${(point.vx + 1) * 127.5}, ${(point.vy + 1) * 127.5}, ${intensity * 255}, ${intensity})`)
      gradient.addColorStop(1, 'rgba(0,0,0,0)')
      context.fillStyle = gradient
      context.fillRect(0, 0, size, size)
    }
    texture.needsUpdate = true
  }

  return { texture, addTouch, update }
}

function createLiquidEffect(texture) {
  return new Effect('LiquidEffect', `
    uniform sampler2D uTexture;
    uniform float uStrength;
    uniform float uTime;
    uniform float uFreq;
    void mainUv(inout vec2 uv) {
      vec4 touch = texture2D(uTexture, uv);
      float wave = 0.5 + 0.5 * sin(uTime * uFreq + touch.b * 6.2831853);
      uv += (touch.rg * 2.0 - 1.0) * uStrength * touch.b * wave;
    }
  `, {
    uniforms: new Map([
      ['uTexture', new THREE.Uniform(texture)],
      ['uStrength', new THREE.Uniform(props.liquidStrength)],
      ['uTime', new THREE.Uniform(0)],
      ['uFreq', new THREE.Uniform(props.liquidWobbleSpeed)]
    ])
  })
}

function dispose() {
  if (!state) return
  cancelAnimationFrame(state.raf)
  state.resizeObserver.disconnect()
  state.intersectionObserver.disconnect()
  window.removeEventListener('pointerdown', state.onPointerDown)
  window.removeEventListener('pointermove', state.onPointerMove)
  document.removeEventListener('visibilitychange', state.onVisibilityChange)
  state.geometry.dispose()
  state.material.dispose()
  state.touch?.texture.dispose()
  state.composer?.dispose()
  state.renderer.dispose()
  state.renderer.forceContextLoss()
  state.renderer.domElement.remove()
  state = null
}

onMounted(() => {
  const container = containerRef.value
  if (!container) return

  let renderer
  try {
    renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: 'low-power' })
  } catch {
    // WebGL 不可用时保留现有页面背景，不影响首页主要功能。
    return
  }
  renderer.setPixelRatio(1)
  renderer.setClearAlpha(0)
  renderer.domElement.className = 'pixel-blast-canvas'
  container.appendChild(renderer.domElement)

  const uniforms = {
    uResolution: { value: new THREE.Vector2(1, 1) },
    uTime: { value: Math.random() * 1000 },
    uColor: { value: new THREE.Color(props.color) },
    uPixelSize: { value: props.pixelSize },
    uScale: { value: props.patternScale },
    uDensity: { value: props.patternDensity },
    uPixelJitter: { value: props.pixelSizeJitter },
    uEnableRipples: { value: props.enableRipples ? 1 : 0 },
    uRippleSpeed: { value: props.rippleSpeed },
    uRippleThickness: { value: props.rippleThickness },
    uRippleIntensity: { value: props.rippleIntensity },
    uEdgeFade: { value: props.edgeFade },
    uShapeType: { value: SHAPE_MAP[props.variant] ?? 0 },
    uClickPos: { value: Array.from({ length: MAX_CLICKS }, () => new THREE.Vector2(-1, -1)) },
    uClickTimes: { value: new Float32Array(MAX_CLICKS) }
  }

  const scene = new THREE.Scene()
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
  const geometry = new THREE.PlaneGeometry(2, 2)
  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    glslVersion: THREE.GLSL3
  })
  scene.add(new THREE.Mesh(geometry, material))

  let composer = null
  let touch = null
  let liquidEffect = null
  if (props.liquid) {
    touch = createTouchTexture()
    liquidEffect = createLiquidEffect(touch.texture)
    composer = new EffectComposer(renderer)
    composer.addPass(new RenderPass(scene, camera))
    composer.addPass(new EffectPass(camera, liquidEffect))
  }

  const resize = () => {
    const width = Math.max(container.clientWidth, 1)
    const height = Math.max(container.clientHeight, 1)
    const renderScale = width < 768 ? props.mobileResolutionScale : props.resolutionScale
    const renderWidth = Math.ceil(width * renderScale)
    const renderHeight = Math.ceil(height * renderScale)
    renderer.setSize(renderWidth, renderHeight, false)
    uniforms.uResolution.value.set(renderer.domElement.width, renderer.domElement.height)
    uniforms.uPixelSize.value = Math.max(props.pixelSize * renderScale, 1.5)
    composer?.setSize(renderWidth, renderHeight)
  }

  const mapPointer = (event) => {
    const rect = renderer.domElement.getBoundingClientRect()
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) return null
    return {
      x: (event.clientX - rect.left) / rect.width,
      y: 1 - (event.clientY - rect.top) / rect.height,
      px: (event.clientX - rect.left) * renderer.domElement.width / rect.width,
      py: (rect.bottom - event.clientY) * renderer.domElement.height / rect.height
    }
  }

  let clickIndex = 0
  const onPointerDown = (event) => {
    const point = mapPointer(event)
    if (!point || !props.enableRipples) return
    uniforms.uClickPos.value[clickIndex].set(point.px, point.py)
    uniforms.uClickTimes.value[clickIndex] = uniforms.uTime.value
    clickIndex = (clickIndex + 1) % MAX_CLICKS
  }
  const onPointerMove = (event) => {
    const point = mapPointer(event)
    if (point && touch) touch.addTouch(point)
  }

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  let visible = true
  let documentVisible = !document.hidden
  let lastFrameTime = 0
  const frameInterval = 1000 / Math.max(props.frameRate, 1)

  const drawFrame = (deltaSeconds) => {
    if (visible && documentVisible) {
      uniforms.uTime.value += deltaSeconds * props.speed
      touch?.update()
      if (liquidEffect) liquidEffect.uniforms.get('uTime').value = uniforms.uTime.value
      if (composer) composer.render()
      else renderer.render(scene, camera)
    }
  }

  const animate = (timestamp) => {
    const elapsed = timestamp - lastFrameTime
    if (elapsed >= frameInterval) {
      drawFrame(Math.min(elapsed / 1000, 0.1))
      lastFrameTime = timestamp - (elapsed % frameInterval)
    }
    state.raf = requestAnimationFrame(animate)
  }

  const resizeObserver = new ResizeObserver(resize)
  const intersectionObserver = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting }, { rootMargin: '120px' })
  const onVisibilityChange = () => { documentVisible = !document.hidden }

  state = {
    renderer,
    material,
    geometry,
    composer,
    touch,
    resizeObserver,
    intersectionObserver,
    onPointerDown,
    onPointerMove,
    onVisibilityChange,
    raf: 0
  }

  resizeObserver.observe(container)
  intersectionObserver.observe(container)
  window.addEventListener('pointerdown', onPointerDown, { passive: true })
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  document.addEventListener('visibilitychange', onVisibilityChange)
  resize()
  if (prefersReducedMotion) drawFrame(0)
  else state.raf = requestAnimationFrame(animate)
})

onUnmounted(dispose)
</script>

<style scoped>
.pixel-blast {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.pixel-blast--fixed {
  position: fixed;
  inset: 0;
}

:deep(.pixel-blast-canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
