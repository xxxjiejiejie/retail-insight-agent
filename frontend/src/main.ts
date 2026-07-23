import { createApp } from "vue"
import {
  ElAlert,
  ElButton,
  ElIcon,
  ElInput,
  ElTable,
  ElTableColumn,
} from "element-plus"
import "element-plus/es/components/base/style/css"
import "element-plus/es/components/alert/style/css"
import "element-plus/es/components/button/style/css"
import "element-plus/es/components/icon/style/css"
import "element-plus/es/components/input/style/css"
import "element-plus/es/components/table/style/css"

import App from "./App.vue"
import "./style.css"

const app = createApp(App)

for (const component of [ElAlert, ElButton, ElIcon, ElInput, ElTable, ElTableColumn]) {
  app.use(component)
}

app.mount("#app")
