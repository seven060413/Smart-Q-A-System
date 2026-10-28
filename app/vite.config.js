import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    uni(),
  ],
  // 开发服务器默认只监听 IPv6 回环（::1），部分环境用 localhost 会连不上。
  // 固定监听所有网卡，本机可用 127.0.0.1，手机可用电脑局域网 IP 访问。
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
})
