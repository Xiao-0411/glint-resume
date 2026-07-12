<template>
  <div class="animated-bg" aria-hidden="true">
    <div class="mesh mesh-1"></div>
    <div class="mesh mesh-2"></div>
    <div class="mesh mesh-3"></div>
    <div class="mesh mesh-4"></div>
    <div class="dots"></div>
    <div class="grain"></div>
  </div>
</template>

<style scoped>
.animated-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

/* 渐变网格 */
.mesh {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
  animation-duration: 25s;
  animation-iteration-count: infinite;
  animation-timing-function: ease-in-out;
}

.mesh-1 {
  width: 800px; height: 800px;
  background: radial-gradient(circle, rgba(79, 70, 229, 0.25) 0%, rgba(139, 92, 246, 0.1) 40%, transparent 70%);
  top: -300px; left: -200px;
  animation-name: meshFloat1;
}

.mesh-2 {
  width: 600px; height: 600px;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.2) 0%, rgba(79, 70, 229, 0.08) 40%, transparent 70%);
  top: 50%; right: -200px;
  animation-name: meshFloat2;
}

.mesh-3 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(249, 115, 22, 0.08) 0%, rgba(79, 70, 229, 0.05) 40%, transparent 70%);
  bottom: -200px; left: 30%;
  animation-name: meshFloat3;
}

.mesh-4 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.06) 0%, transparent 70%);
  top: 20%; right: 30%;
  animation-name: meshFloat2;
  animation-direction: reverse;
}

@keyframes meshFloat1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(40px, -30px) scale(1.05); }
  66% { transform: translate(-20px, 20px) scale(0.95); }
}

@keyframes meshFloat2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-30px, 20px) scale(1.08); }
  66% { transform: translate(25px, -15px) scale(0.92); }
}

@keyframes meshFloat3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(20px, 25px) scale(1.06); }
}

/* 圆点网格 */
.dots {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(79, 70, 229, 0.12) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: radial-gradient(ellipse 80% 60% at 50% 40%, black 20%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse 80% 60% at 50% 40%, black 20%, transparent 70%);
}

/* 噪点纹理 */
.grain {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-repeat: repeat;
  background-size: 256px 256px;
}
</style>