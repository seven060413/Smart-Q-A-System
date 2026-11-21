/**
 * 四点透视裁切的核心数学。
 *
 * corners 顺序固定为：左上、右上、右下、左下（TL, TR, BR, BL）。
 * 输出一张矩形图片：目标矩形的四个角对应源图的四个角。
 */

function solveLinear(A, b) {
  const n = b.length
  for (let col = 0; col < n; col += 1) {
    let pivot = col
    for (let row = col + 1; row < n; row += 1) {
      if (Math.abs(A[row][col]) > Math.abs(A[pivot][col])) pivot = row
    }
    if (Math.abs(A[pivot][col]) < 1e-10) return null
    if (pivot !== col) {
      const tmpA = A[col]
      A[col] = A[pivot]
      A[pivot] = tmpA
      const tmpB = b[col]
      b[col] = b[pivot]
      b[pivot] = tmpB
    }

    const divisor = A[col][col]
    for (let c = col; c < n; c += 1) A[col][c] /= divisor
    b[col] /= divisor

    for (let row = 0; row < n; row += 1) {
      if (row === col) continue
      const factor = A[row][col]
      if (!factor) continue
      for (let c = col; c < n; c += 1) A[row][c] -= factor * A[col][c]
      b[row] -= factor * b[col]
    }
  }
  return b
}

/**
 * 求 dst -> src 的单应矩阵。
 * dst / src 都是 4 个 [x, y] 点。
 * 返回 [h11, h12, h13, h21, h22, h23, h31, h32]，h33 固定为 1。
 */
export function solveHomography(dst, src) {
  const A = []
  const b = []
  for (let i = 0; i < 4; i += 1) {
    const [u, v] = dst[i]
    const [x, y] = src[i]
    A.push([u, v, 1, 0, 0, 0, -x * u, -x * v])
    b.push(x)
    A.push([0, 0, 0, u, v, 1, -y * u, -y * v])
    b.push(y)
  }
  return solveLinear(A, b)
}

function sampleBilinear(data, width, height, x, y) {
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 || x > width - 1 || y > height - 1) {
    return [255, 255, 255, 255]
  }

  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const x1 = Math.min(x0 + 1, width - 1)
  const y1 = Math.min(y0 + 1, height - 1)
  const fx = x - x0
  const fy = y - y0

  const i00 = (y0 * width + x0) * 4
  const i10 = (y0 * width + x1) * 4
  const i01 = (y1 * width + x0) * 4
  const i11 = (y1 * width + x1) * 4

  const out = [0, 0, 0, 0]
  for (let c = 0; c < 4; c += 1) {
    const top = data[i00 + c] * (1 - fx) + data[i10 + c] * fx
    const bottom = data[i01 + c] * (1 - fx) + data[i11 + c] * fx
    out[c] = Math.round(top * (1 - fy) + bottom * fy)
  }
  return out
}

/**
 * 把源图按四角透视校正到 outW x outH 的矩形像素数组。
 * 返回 Uint8ClampedArray(RGBA)；四点退化时返回 null。
 */
export function warpRGBA(src, srcW, srcH, corners, outW, outH) {
  if (!src || srcW <= 0 || srcH <= 0 || outW <= 0 || outH <= 0) return null

  const dst = [
    [0, 0],
    [outW - 1, 0],
    [outW - 1, outH - 1],
    [0, outH - 1],
  ]
  const h = solveHomography(dst, corners)
  if (!h) return null

  const out = new Uint8ClampedArray(outW * outH * 4)
  let offset = 0

  for (let y = 0; y < outH; y += 1) {
    for (let x = 0; x < outW; x += 1) {
      const denominator = h[6] * x + h[7] * y + 1
      let r = 255
      let g = 255
      let b = 255
      let a = 255
      if (Math.abs(denominator) > 1e-10) {
        const sx = (h[0] * x + h[1] * y + h[2]) / denominator
        const sy = (h[3] * x + h[4] * y + h[5]) / denominator
        const pixel = sampleBilinear(src, srcW, srcH, sx, sy)
        r = pixel[0]
        g = pixel[1]
        b = pixel[2]
        a = pixel[3]
      }
      out[offset] = r
      out[offset + 1] = g
      out[offset + 2] = b
      out[offset + 3] = a
      offset += 4
    }
  }

  return out
}

export function quadSize(corners) {
  const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])
  const top = distance(corners[0], corners[1])
  const right = distance(corners[1], corners[2])
  const bottom = distance(corners[2], corners[3])
  const left = distance(corners[3], corners[0])
  return {
    width: Math.max(top, bottom),
    height: Math.max(left, right),
  }
}

export function quadArea(corners) {
  let area = 0
  for (let i = 0; i < corners.length; i += 1) {
    const [x1, y1] = corners[i]
    const [x2, y2] = corners[(i + 1) % corners.length]
    area += x1 * y2 - x2 * y1
  }
  return Math.abs(area) / 2
}
