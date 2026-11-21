<script>
import { checkAuthExpiry, initAuth } from './auth.js'
import { initThemeBridge } from './theme/theme.js'
import { restoreInstalledThemes } from './themes/installed.js'
import { activateBuiltinPlugins } from './plugins/index.js'
import { bootstrapSelfDiscipline, onSelfDisciplineForeground } from './selfdiscipline/bootstrap.js'
import { onAppBackground, onAppForeground } from './selfdiscipline/guard.js'
import { currentFocusSession } from './selfdiscipline/focus.js'

export default {
  onLaunch: function () {
    console.log('App Launch')
    // 必须先于首屏渲染，避免深色模式闪白
    initThemeBridge()
    // 运行时安装的主题：读取本地注册表并把当前主题重新应用一遍
    restoreInstalledThemes()
    // 注册内置功能插件（静态模块，不使用动态执行）
    activateBuiltinPlugins()
    // 恢复本地令牌并用 /api/auth/me 校验；失败不会阻塞页面。
    initAuth().catch(() => {})
    // 自律模块：初始化本地存储、恢复专注、对账提醒与守护。
    bootstrapSelfDiscipline().catch(() => {})
  },
  onShow: function () {
    // 回到前台时检查本地过期时间；真正失效仍以服务端 401 为准。
    checkAuthExpiry()
    // 专注守护：回到前台立即隐藏悬浮窗，并轻量对账提醒。
    onAppForeground()
    onSelfDisciplineForeground().catch(() => {})
    console.log('App Show')
  },
  onHide: function () {
    // 专注进行中才触发守护；currentFocusSession 读内存，避免异步查库。
    if (currentFocusSession()) onAppBackground()
    console.log('App Hide')
  },
}
</script>

<style>
/* 全局默认 token：作为首帧兜底，实际值由页面根节点 :style="themeVars" 覆盖 */
page {
  --ik-bg: #f5f6f8;
  --ik-card: #ffffff;
  --ik-t1: #1f2937;
  --ik-t2: #4b5563;
  --ik-t3: #8a8f99;
  --ik-line: #e5e7eb;
  --ik-primary: #2b6cb0;
  --ik-primary-weak: #e8f0fb;
  --ik-on-primary: #ffffff;
  --ik-block: #1f2937;
  --ik-on-block: #ffffff;
  --ik-soft: #f0f2f5;
  --ik-input-bg: #ffffff;
  --ik-danger: #e53e3e;
  --ik-success: #2f9e68;
  --ik-radius: 24rpx;
  background: var(--ik-bg);
}

/* 把 wot-ui 的变量映射到本项目的 token（放在带 token 的根节点上） */
.theme-root {
  --wot-color-theme: var(--ik-primary);
  --wot-color-title: var(--ik-t1);
  --wot-color-content: var(--ik-t2);
  --wot-color-secondary: var(--ik-t3);
  --wot-color-border: var(--ik-line);
  --wot-color-bg: var(--ik-card);
  --wot-tabbar-bg: var(--ik-card);
  --wot-toast-bg: var(--ik-card);
  --wot-toast-color: var(--ik-t1);
  --wot-dialog-bg: var(--ik-card);
  --wot-dialog-title-color: var(--ik-t1);
  --wot-dialog-content-color: var(--ik-t2);
  --wot-dialog-content-input-bg: var(--ik-input-bg);
  --wot-dialog-primary-color: var(--ik-primary);
  --wot-dialog-success-color: var(--ik-success);
  --wot-dialog-error-color: var(--ik-danger);
  --wot-popup-bg: var(--ik-card);
  --wot-action-sheet-bg: var(--ik-card);
  --wot-action-sheet-action-color: var(--ik-t1);
  --wot-action-sheet-cancel-bg: var(--ik-card);
  --wot-action-sheet-cancel-color: var(--ik-t2);
}

/* ===== 主题插件背景图（手机/平板双图）=====
 * 每个主题页面根节点放一个 <ThemeBackground />（全局注册），
 * 它以 fixed + z-index:-1 铺在根节点背景之上、内容之下。
 * isolation 建立层叠上下文，保证负层级子元素不会掉到 page 背景后面。 */
.theme-root {
  position: relative;
  z-index: 0;
  isolation: isolate;
}
/* 这些容器默认铺满 var(--ik-bg)，改成透明后露出背景图（无背景图时视觉不变） */
.theme-root .page,
.theme-root .sd-page {
  background-color: transparent !important;
}

/* H5：原生 tabBar 已移除，这里仅作兜底 */
/* #ifdef H5 */
uni-tabbar {
  display: none !important;
}
/* #endif */
</style>
