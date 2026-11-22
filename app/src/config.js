// ===== 后端服务地址 =====
// H5 开发默认本地；H5 构建和 App 打包默认生产 HTTPS。
// 真机局域网调试时用环境变量覆盖（app/.env.local）：
//   VITE_API_BASE_URL=http://192.168.1.31:18082
//
// 注意：
// - release 包不要用 http://。Android targetSdk >= 28 默认禁止明文 HTTP；
//   局域网调试只能用于 debug 包，并需要临时允许 cleartext。
// - 安全边界：前端只访问本后端；语音转写走 POST /api/transcribe，
//   由后端请求 ASR 服务，前端不保存任何 ASR 密钥。

const DEV_BASE_URL = 'http://127.0.0.1:18082'
const PROD_BASE_URL = 'https://seventeen17.com.cn'

// #ifdef H5
const DEFAULT_BASE_URL = import.meta.env.DEV ? DEV_BASE_URL : PROD_BASE_URL
// #endif
// #ifndef H5
// App / 小程序一律使用生产地址；调试用 VITE_API_BASE_URL 覆盖。
const DEFAULT_BASE_URL = PROD_BASE_URL
// #endif

const injectedBaseUrl = import.meta.env.VITE_API_BASE_URL || ''

export const BASE_URL = (injectedBaseUrl || DEFAULT_BASE_URL).replace(/\/+$/, '')