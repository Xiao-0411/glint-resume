import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import './assets/styles/global.css'

// 兼容旧的 hash 路由链接（如 https://sgjl.cloud/#/chat），改写为 history 路径
if (window.location.hash.startsWith('#/')) {
  window.history.replaceState(null, '', window.location.hash.slice(1))
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
