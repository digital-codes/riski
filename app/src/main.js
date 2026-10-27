import { createApp } from 'vue'
import App from './App.vue'
import { initInstance } from './instanceStore.js'

const app = createApp(App)
app.mount('#app')

// deployment-instance branding/map settings (falls back to Karlsruhe
// defaults when the API is unreachable)
initInstance()

