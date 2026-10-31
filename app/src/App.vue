<script>
import { checkAuthExpiry, initAuth } from './auth.js'
import { hideNativeTabBar } from './tabbar.js'

export default {
  onLaunch: function () {
    console.log('App Launch')
    // 使用 Wot UI 自定义悬浮导航，尽早隐藏原生 tabBar。
    hideNativeTabBar()
    // 恢复本地令牌并用 /api/auth/me 校验；失败不会阻塞页面。
    initAuth().catch(() => {})
  },
  onShow: function () {
    // 回到前台时检查本地过期时间；真正失效仍以服务端 401 为准。
    hideNativeTabBar()
    checkAuthExpiry()
    console.log('App Show')
  },
  onHide: function () {
    console.log('App Hide')
  },
}
</script>

<style>
/*每个页面公共css */

/* H5：原生 tabBar 只保留路由能力，显示层完全由 Wot UI 导航负责。
   这里先隐藏 DOM，避免页面刚渲染时闪出原生 tabBar。 */
/* #ifdef H5 */
uni-tabbar {
  display: none !important;
}
/* #endif */
</style>
