# 底部导航 Wot UI 改造过程

> 记录本次“原生 tabBar → Wot UI 悬浮胶囊导航”的调研、实现、踩坑与验证过程。
> 目标不是只留下结果，而是说明每一步为什么这样做、遇到问题怎么定位。
>
> 相关文件：[AppTabBar.vue](../../app/src/components/AppTabBar.vue)、
> [tabbar.js](../../app/src/tabbar.js)、[pages.json](../../app/src/pages.json)、
> [index.vue](../../app/src/pages/index/index.vue)、[my.vue](../../app/src/pages/my/my.vue)。

---

## 1. 改造前的状态

- `pages.json` 里已经有一个**原生 tabBar**，只有“学习”和“我的”两项，且没有图标（纯文字）。
- 首页输入栏的顺序是“语音按钮 → 输入框 → 发送按钮”。
- 语音图标用的是“标准 Wi-Fi 旋转 90°”的 SVG。
- “我的”页面已经存在，只是普通页面，没有底部导航。
- 项目没有引入任何第三方 UI 组件库。

本次目标：

1. 使用 Wot UI 的 `wd-tabbar` / `wd-tabbar-item` 做一个**悬浮胶囊**导航；
2. 保留原生 tabBar 配置，让 `uni.switchTab` 继续可用，但**隐藏原生显示**；
3. 导航只出现在“学习”和“我的”两个页面；
4. 输入栏顺序保持“输入框 → 语音 → 发送”，导航不能遮挡输入栏；
5. 语音图标改为旋转 90°；
6. 不动后端、ASR、录音、上传和问答逻辑。

---

## 2. 先调研，再动手

### 2.1 是否已有可复用的组件库

先看 [app/package.json](../../app/package.json)：依赖只有 uni-app、Vue、vue-i18n，没有 UI 组件库。因此可以引入 Wot UI，且只为导航使用，不迁移其他页面。

### 2.2 确认 Wot UI 的接入方式

查官方文档后确认：

- npm 包名：`@wot-ui/ui`
- 需要 Sass，版本要求 **> 1.78**，官方推荐 `^1.98.0`
- 组件通过 EasyCom 自动引入，不需要在 `main.js` 注册
- EasyCom 配置：

```json
"easycom": {
  "autoscan": true,
  "custom": {
    "^wd-(.*)": "@wot-ui/ui/components/wd-$1/wd-$1.vue"
  }
}
```

`pages.json` 里原来没有 `easycom` 字段，所以直接新增，**没有重复创建配置项**。

### 2.3 确认 tabbar 组件能力

`wd-tabbar` 文档确认可用的关键属性：

| 属性 | 作用 |
| --- | --- |
| `v-model` / `model-value` | 选中项，按 `name` 或索引 |
| `fixed` | 固定底部 |
| `placeholder` | 固定时生成等高占位 |
| `safe-area-inset-bottom` | 处理底部安全区 |
| `shape="round"` | 圆形/悬浮外观 |
| `active-color` / `inactive-color` | 选中/未选中颜色 |
| `custom-style` | 自定义宽度、圆角、阴影等 |

`wd-tabbar-item` 支持 `name`、`title`、`icon`。

### 2.4 确认图标名称，不靠猜

没有直接照抄文档里的示例图标，而是安装后在组件包的
`node_modules/@wot-ui/ui/components/wd-icon/iconfont.scss` 里核对：

```text
book
user
```

所以最终使用：

- 学习：`icon="book"`
- 我的：`icon="user"`

### 2.5 隐藏原生 tabBar 的官方方式

查 `uni.hideTabBar` 文档：

- App、H5 都支持；
- 需要在原生 tabBar 渲染后调用；
- `animation` 参数只在小程序生效；
- `pages.json` 的 `"custom": true` 只支持微信/抖音小程序，**不能用于 App/H5**。

因此方案确定为：

1. **保留** `pages.json` 的原生 tabBar 配置（保证 `switchTab` 可用）；
2. 在运行时用 `uni.hideTabBar()` 隐藏原生显示；
3. 显示层完全换成 Wot UI 组件。

---

## 3. 安装依赖

```powershell
cd D:\IKGR-system-eands\app
npm install @wot-ui/ui@2.4.0
npm install -D sass@^1.98.0
```

实际结果：

| 包 | 版本 |
| --- | --- |
| `@wot-ui/ui` | 2.4.0 |
| `sass` | 1.107.1（满足 > 1.78） |

构建时会出现 Sass `legacy-js-api` 的弃用警告，这是 Wot UI/构建链使用旧 API 导致，不影响构建结果。

---

## 4. 代码结构

### 4.1 集中管理导航配置：[tabbar.js](../../app/src/tabbar.js)

把页面路径、标题、图标集中到一个数组，后续增加第 3、4 项时只改这里：

```js
export const TAB_INDEX = 'pages/index/index'
export const TAB_MY = 'pages/my/my'

export const TAB_ITEMS = [
  { path: TAB_INDEX, title: '学习', icon: 'book' },
  { path: TAB_MY, title: '我的', icon: 'user' },
]
```

同时提供：

- `switchTab(path)`：统一调用 `uni.switchTab`；
- `hideNativeTabBar()`：统一调用 `uni.hideTabBar`，失败时静默忽略。

### 4.2 导航组件：[AppTabBar.vue](../../app/src/components/AppTabBar.vue)

结构：

```vue
<view class="app-tabbar-wrap">
  <wd-tabbar
    :model-value="active"
    fixed
    placeholder
    safe-area-inset-bottom
    shape="round"
    :z-index="100"
    active-color="#2b6cb0"
    inactive-color="#8a8f99"
    custom-style="..."
    @change="handleChange"
  >
    <wd-tabbar-item
      v-for="item in TAB_ITEMS"
      :key="item.path"
      :name="item.path"
      :title="item.title"
      :icon="item.icon"
    />
  </wd-tabbar>
</view>
```

每个页面传入自己的路径：

- 首页：`<AppTabBar :active="TAB_INDEX" />`
- 我的：`<AppTabBar :active="TAB_MY" />`

这样**高亮项永远等于当前页面路由**。

### 4.3 原生 tabBar 隐藏位置

| 位置 | 调用 |
| --- | --- |
| [App.vue](../../app/src/App.vue) | `onLaunch`、`onShow` 调用 `hideNativeTabBar()` |
| [index.vue](../../app/src/pages/index/index.vue) | `onLoad`、`onShow` 调用 |
| [my.vue](../../app/src/pages/my/my.vue) | `onLoad`、`onShow` 调用 |
| App.vue 的 H5 样式 | `uni-tabbar { display: none !important; }` |

H5 端额外用 CSS 立即隐藏，避免页面首帧先出现原生 tabBar；App 端原生 tabBar 不是 DOM，只能依赖 `uni.hideTabBar`。

---

## 5. 悬浮胶囊的样式实现

`custom-style` 控制外观，**没有覆盖组件内部的大段样式**：

```text
left: 50%;
right: auto;
bottom: calc(8px + env(safe-area-inset-bottom));
transform: translateX(-50%);
width: calc(100% - 48px);
max-width: 420px;
margin-left: 0;
margin-right: 0;
border-radius: 28px;
background: #ffffff;
box-shadow: 0 6px 20px rgba(43, 108, 176, 0.14);
--wot-tabbar-height: 56px;
--wot-tabbar-item-icon-size: 26px;
--wot-tabbar-item-title-font-size: 11px;
```

设计说明：

- `width: calc(100% - 48px)`：左右各留 24px，不贴屏幕边缘；
- `max-width: 420px`：宽屏/平板不会拉成一条长条；
- `left: 50% + translateX(-50%)`：水平居中；
- `bottom: 8px + env(safe-area-inset-bottom)`：胶囊悬浮在安全区上方；
- `border-radius: 28px` + 56px 高度：形成胶囊；
- 颜色使用项目蓝 `#2b6cb0`，未选中灰 `#8a8f99`；
- 图标 26px、文字 11px，满足“图标在上、短文字在下”。

### 5.1 占位与首帧跳动

`wd-tabbar` 的 `placeholder` 是在组件挂载后通过测量高度再设置的。
如果完全依赖它，第一帧高度可能是 0，随后再撑开，输入栏会向上跳一下。

解决办法：外层 `.app-tabbar-wrap` 固定预留：

```css
.app-tabbar-wrap {
  flex: 0 0 auto;
  height: calc(64px + env(safe-area-inset-bottom));
}
```

64px = 56px 胶囊高度 + 8px 悬浮间距，和组件设置保持一致。
这样首帧就预留了空间，同时仍保留 Wot UI 自带的 `placeholder`。

---

## 6. 输入栏与页面高度

### 6.1 输入栏顺序

首页输入栏顺序改为：

```text
输入框 → 语音按钮 → 发送按钮
```

CSS 关键点：

- `input`：`flex: 1; min-width: 0;`，自动占剩余宽度；
- 语音按钮：固定 `72rpx`，`flex-shrink: 0`；
- 发送按钮：固定 `140rpx`，`flex-shrink: 0`；
- 不换行、不设 `flex-wrap`。

录音/识别状态行放到输入栏上方的 `.record-row`，固定高度 44rpx。
这样状态出现/消失时，三个控件的水平和垂直位置都不会跳。

### 6.2 页面高度与 H5 固定导航

H5 的导航栏、tabBar 是固定定位，页面高度要扣除：

```css
/* #ifdef H5 */
.page {
  height: calc(100vh - var(--window-top, 0px) - var(--window-bottom, 0px));
}
/* #endif */
```

`--window-top` 是导航栏高度，`--window-bottom` 在原生 tabBar 显示时是 tabBar 高度；
原生 tabBar 隐藏后变为 0，此时由 `.app-tabbar-wrap` 预留自定义导航空间。

App 端保留 `height: 100vh`，原生 tabBar 隐藏后 webview 区域由系统处理。

---

## 7. 语音图标旋转 90°

保留原来的三层弧线、无中心点 SVG，只把 transform 改为：

```html
<g transform="rotate(90 12 12)" ...>
  <path d="M2 8.82a15 15 0 0 1 20 0" />
  <path d="M5 12.859a10 10 0 0 1 14 0" />
  <path d="M8.5 16.429a5 5 0 0 1 7 0" />
</g>
```

没有改成 emoji、没有换图标、没有去掉录音状态的同一图标。

无障碍名称：

- 按钮 `aria-label="语音输入"`；
- 内部再放一个视觉隐藏的 `<text class="sr-only">语音输入</text>`，兼容不同平台读屏。

---

## 8. 路由与高亮

`switchTab` 要求目标页面在 `pages.json` 的 `tabBar.list` 中，因此**原生 tabBar 配置必须保留**，只是隐藏显示。

历史页不能通过 URL 给 tabBar 页面传参，所以沿用上一轮的方案：

- 历史页设置 `store.pendingIndexAction`；
- `uni.switchTab` 回首页；
- 首页 `onShow` 读取并处理：
  - `open`：打开指定会话；
  - `new`：清空当前会话；
  - `home`：保持当前页面。

账号页的“返回问答”兜底也改为 `uni.switchTab`。

---

## 9. 遇到的问题与定位过程

### 9.1 切换 tab 后高亮错误（真实 bug）

第一版使用：

```html
<wd-tabbar v-model="model">
```

组件内部自己维护选中值。切到“我的”再切回“学习”后，隐藏页面里的 `model` 还停留在上一次点击的值，页面重新显示时高亮错误。

**定位方式**：用 Chrome DevTools Protocol 在虚拟页面里查询：

```js
[...document.querySelectorAll('uni-page')]
  .map(pg => pg.querySelectorAll('.wd-tabbar-item'))
```

发现当前可见的“我的”页面里，高亮的是“学习”。

**修复**：不再使用内部 `v-model`，改成受控写法：

```html
<wd-tabbar :model-value="active" @change="handleChange">
```

`active` 由页面传入（`TAB_INDEX` / `TAB_MY`），永远等于当前页面路由。
点击另一项只调用 `switchTab`，高亮由目标页面自己负责。

### 9.2 首帧占位高度变化

`placeholder` 是挂载后测量，首帧可能为 0。
用固定高度的 `.app-tabbar-wrap` 预留“56px + 8px + 安全区”，消除跳动。

### 9.3 原生 tabBar 闪烁

- H5：`uni-tabbar { display: none !important; }` 先隐藏 DOM；
- App：`onLaunch`、`onShow`、页面 `onLoad/onShow` 多入口调用 `uni.hideTabBar`；
- 没有使用只支持小程序的 `custom: true`，也没有用只支持 H5 的纯 CSS 方案代替 App 导航。

### 9.4 截图看起来“右侧被裁掉”

第一次无头截图窗口是 390px，但 Chrome 的实际 CSS 视口是 512px，截图缩放后看起来发按钮/导航被裁。
用 CDP `Emulation.setDeviceMetricsOverride` 强制 390×844、320×568 重新测量，确认：

- `document.documentElement.scrollWidth === innerWidth`，没有横向溢出；
- 输入框、语音、发送都在视口内；
- 输入栏底部与导航占位边界精确衔接。

### 9.5 Sass 警告

构建有 `legacy-js-api` 弃用警告，属于 Sass 新版本提示，构建仍然成功。

---

## 10. 验证结果

### 10.1 构建

```powershell
cd D:\IKGR-system-eands\app
npm run build:h5
```

结果：`DONE Build complete.`（仅有 Sass 弃用警告）。

### 10.2 布局测量（H5 390px）

| 元素 | 位置/宽度 |
| --- | --- |
| 输入框 | x=12，宽 242 |
| 语音按钮 | x=261，宽 37 |
| 发送按钮 | x=305，宽 73，右边界 378 |
| 输入栏底部 | 780px |
| 导航占位 | 780px 开始，高 64px |
| 胶囊导航 | 24px 起，宽 342px，底部留 8px |

### 10.3 布局测量（H5 320px）

输入框 10–209，语音 214–245，发送 250–310，`scrollWidth = 320`，无溢出。

### 10.4 导航行为

用 CDP 实际点击验证：

- 学习 ↔ 我的：路由、标题、高亮都正确；
- 再次往返后仍正确（覆盖了 9.1 的 bug）；
- 原生 `uni-tabbar` 始终 `display: none`；
- 账号、历史页面不出现自定义导航；
- 历史页“返回问答”能回到首页并高亮“学习”。

未运行单元测试。

---

## 11. 需要手工验收的项

### Android App

- [ ] 启动和切换页面时不会闪出原生 tabBar。
- [ ] 只显示 Wot UI 悬浮胶囊，左右边距、最大宽度、圆角、阴影正常。
- [ ] “学习 / 我的”图标与文字正确，选中蓝、未选中灰。
- [ ] 输入栏在导航上方，语音/发送不被遮挡；底部安全区正常。
- [ ] 窄屏下三个控件不换行、不重叠。
- [ ] 历史、学习路径、账号页没有底部导航，返回后导航恢复。
- [ ] 语音图标为 90° 的三层弧线、无中心点，录音时保持同一图标。

### H5

- [ ] 首帧和 tab 切换时都不出现原生 tabBar。
- [ ] 320px / 390px 宽度下输入栏和导航布局正常。
- [ ] 安全区（刘海屏/手势条）下方留白正确。
- [ ] 学习/我的切换、账号/历史跳转与返回正常。
- [ ] 麦克风仍只在 localhost 或 HTTPS 下工作。

---

## 12. 以后扩展到 3–4 项

以新增一个“练习”页为例，需要改四处：

### 12.1 新建页面文件

`pages.json` 里的路由 `pages/practice/practice` 对应磁盘文件：

```text
app/src/pages/practice/practice.vue
```

页面里放导航组件，并传入自己的路径常量：

```vue
<template>
  <view class="page">
    <!-- 页面内容 -->
    <AppTabBar :active="TAB_PRACTICE" />
  </view>
</template>

<script setup>
import AppTabBar from '../../components/AppTabBar.vue'
import { TAB_PRACTICE } from '../../tabbar.js'
</script>
```

### 12.2 在 pages.json 注册页面

```json
{
  "path": "pages/practice/practice",
  "style": {
    "navigationBarTitleText": "练习"
  }
}
```

### 12.3 加入原生 tabBar.list

`switchTab` 只接受 `tabBar.list` 中的页面，所以必须同时加入：

```json
"tabBar": {
  "list": [
    { "pagePath": "pages/index/index", "text": "学习" },
    { "pagePath": "pages/practice/practice", "text": "练习" },
    { "pagePath": "pages/my/my", "text": "我的" }
  ]
}
```

原生 tabBar 仍会被隐藏，这里只是为了保留 `switchTab` 的路由能力。

### 12.4 在 tabbar.js 增加配置

```js
export const TAB_PRACTICE = 'pages/practice/practice'

export const TAB_ITEMS = [
  { path: TAB_INDEX, title: '学习', icon: 'book' },
  { path: TAB_PRACTICE, title: '练习', icon: 'edit' },
  { path: TAB_MY, title: '我的', icon: 'user' },
]
```

`wd-tabbar-item` 本身是 `flex: 1`，增加第三、第四项后会自动均分宽度，不需要改导航布局。

> 注意：历史、学习路径、登录/账号页是普通页面，不要加入 `TAB_ITEMS` 或 `tabBar.list`。

### 12.5 path 与 icon 的区别

| 配置 | 是什么 | 去哪里查 |
| --- | --- | --- |
| `path` | uni-app 页面路由，不是磁盘路径 | [pages.json](../../app/src/pages.json) 的 `pages[].path` / `tabBar.list[].pagePath`；对应 `app/src/pages/...` 下的文件 |
| `icon` | Wot UI 图标名 | `app/node_modules/@wot-ui/ui/components/wd-icon/iconfont.scss` |

- 三处路径必须一致：`pages.json` 的 `pages[].path`、`tabBar.list[].pagePath`、`tabbar.js` 的常量；
- 配置里不带开头的 `/`，`switchTab` 内部会拼成 `/${path}`；
- 图标名区分大小写，必须在上面的 `iconfont.scss` 清单里。

列出全部图标名：

```powershell
cd D:\IKGR-system-eands\app
Select-String -Path node_modules\@wot-ui\ui\components\wd-icon\iconfont.scss -Pattern '\.wd-icon-([a-z0-9-]+)' -AllMatches |
  ForEach-Object { $_.Matches } |
  ForEach-Object { $_.Groups[1].Value } |
  Sort-Object -Unique
```

一句话：

- **`path`**：页面路由，查 `pages.json` 和 `src/pages/`；
- **`icon`**：Wot UI 图标名，查 `node_modules/@wot-ui/ui/components/wd-icon/iconfont.scss`。

---

## 13. 参考

- Wot UI 仓库：<https://github.com/wot-ui/wot-ui>
- Wot UI 安装：<https://wot-ui.cn/guide/quick-use.html>
- Wot UI Tabbar：<https://wot-ui.cn/component/tabbar.html>
- uni.hideTabBar：<https://uniapp.dcloud.net.cn/api/ui/tabbar.html>