<script>
import { checkAuthExpiry, initAuth } from './auth.js'

export default {
  onLaunch: function () {
    console.log('App Launch')
    // 恢复本地令牌并用 /api/auth/me 校验；失败不会阻塞页面。
    initAuth().catch(() => {})
  },
  onShow: function () {
    // 回到前台时检查本地过期时间；真正失效仍以服务端 401 为准。
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
</style>
