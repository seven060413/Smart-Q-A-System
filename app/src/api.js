import { BASE_URL } from './config.js'

// 调用后端 POST /api/ask，返回后端响应 JSON
export function askQuestion(question) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: `${BASE_URL}/api/ask`,
      method: 'POST',
      data: { question },
      header: { 'Content-Type': 'application/json' },
      timeout: 60000,
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data)
        } else {
          reject(new Error('HTTP ' + res.statusCode))
        }
      },
      fail: (err) => reject(err),
    })
  })
}
