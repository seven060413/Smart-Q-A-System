/**
 * LaTeX 文本工具。
 *
 * 这个模块不依赖 DOM，逻辑层（页面/语音）和 renderjs 视图层都能引用。
 * 目标不是完整实现 TeX，而是覆盖中小学数学里常见的写法：
 *   $\frac{2}{5}$、$x^2$、$\sqrt{3}$、$\angle ABC$、$\times$、$\div$ 等。
 */

const SUP_DIGITS = {
  0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴',
  5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹',
  '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
  n: 'ⁿ', i: 'ⁱ',
}

const SUB_DIGITS = {
  0: '₀', 1: '₁', 2: '₂', 3: '₃', 4: '₄',
  5: '₅', 6: '₆', 7: '₇', 8: '₈', 9: '₉',
  '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
  n: 'ₙ', i: 'ᵢ',
}

const GREEK = {
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε',
  varepsilon: 'ε', zeta: 'ζ', eta: 'η', theta: 'θ', vartheta: 'ϑ',
  iota: 'ι', kappa: 'κ', lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ',
  pi: 'π', varpi: 'ϖ', rho: 'ρ', varrho: 'ϱ', sigma: 'σ',
  varsigma: 'ς', tau: 'τ', upsilon: 'υ', phi: 'φ', varphi: 'ϕ',
  chi: 'χ', psi: 'ψ', omega: 'ω',
  Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ',
  Pi: 'Π', Sigma: 'Σ', Upsilon: 'Υ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω',
}

const SYMBOLS = {
  times: '×', div: '÷', cdot: '·', pm: '±', mp: '∓',
  le: '≤', leq: '≤', ge: '≥', geq: '≥', ne: '≠', neq: '≠',
  approx: '≈', equiv: '≡', sim: '∼', propto: '∝',
  infty: '∞', angle: '∠', triangle: '△', circ: '°', degree: '°',
  because: '∵', therefore: '∴', in: '∈', notin: '∉',
  subset: '⊂', subseteq: '⊆', supset: '⊃', supseteq: '⊇',
  cup: '∪', cap: '∩', forall: '∀', exists: '∃',
  sum: '∑', prod: '∏', int: '∫', partial: '∂', nabla: '∇',
  perp: '⊥', parallel: '∥', cong: '≅', mid: '|',
  to: '→', rightarrow: '→', leftarrow: '←', leftrightarrow: '↔',
  Rightarrow: '⇒', Leftarrow: '⇐', Leftrightarrow: '⇔',
  cdots: '⋯', ldots: '…', dots: '…', prime: '′',
  lbrace: '{', rbrace: '}', langle: '⟨', rangle: '⟩',
  vert: '|', Vert: '‖', backslash: '\\',
}

const SPEECH_GREEK = {
  alpha: '阿尔法', beta: '贝塔', gamma: '伽马', delta: '德尔塔',
  epsilon: '艾普西龙', varepsilon: '艾普西龙', zeta: '泽塔', eta: '伊塔',
  theta: '西塔', vartheta: '西塔', iota: '约塔', kappa: '卡帕',
  lambda: '兰姆达', mu: '缪', nu: '纽', xi: '克西', pi: '派',
  rho: '柔', sigma: '西格玛', tau: '陶', upsilon: '宇普西龙',
  phi: '斐', varphi: '斐', chi: '卡伊', psi: '普西', omega: '欧米伽',
  Gamma: '伽马', Delta: '德尔塔', Theta: '西塔', Lambda: '兰姆达',
  Xi: '克西', Pi: '派', Sigma: '西格玛', Upsilon: '宇普西龙',
  Phi: '斐', Psi: '普西', Omega: '欧米伽',
}

function isEscaped(text, index) {
  let count = 0
  for (let i = index - 1; i >= 0 && text[i] === '\\'; i -= 1) count += 1
  return count % 2 === 1
}

/**
 * 把文本拆成普通文本和公式段。
 * 支持 $...$、$$...$$、\(...\)、\[...\]。
 */
export function splitMathSegments(input) {
  const text = String(input == null ? '' : input)
  const out = []
  let textStart = 0
  let i = 0

  const pushText = (end) => {
    if (end > textStart) {
      // 普通文本里的 \$ 是字面美元符号，不应显示反斜杠
      out.push({ type: 'text', value: text.slice(textStart, end).replace(/\\\$/g, '$') })
    }
  }

  while (i < text.length) {
    const ch = text[i]

    // \[...\] 与 \(...\)
    if (ch === '\\' && !isEscaped(text, i) && (text[i + 1] === '[' || text[i + 1] === '(')) {
      const display = text[i + 1] === '['
      const close = display ? '\\]' : '\\)'
      const end = text.indexOf(close, i + 2)
      if (end !== -1) {
        pushText(i)
        out.push({
          type: 'math',
          value: text.slice(i + 2, end),
          display,
          raw: text.slice(i, end + 2),
        })
        i = end + 2
        textStart = i
        continue
      }
    }

    if (ch === '$' && !isEscaped(text, i)) {
      // $$...$$ 块级公式
      if (text[i + 1] === '$') {
        const end = text.indexOf('$$', i + 2)
        if (end !== -1) {
          pushText(i)
          out.push({
            type: 'math',
            value: text.slice(i + 2, end),
            display: true,
            raw: text.slice(i, end + 2),
          })
          i = end + 2
          textStart = i
          continue
        }
      } else {
        // $...$ 行内公式，不跨行
        let end = i + 1
        while (end < text.length) {
          if (text[end] === '\n') { end = -1; break }
          if (text[end] === '$' && !isEscaped(text, end)) break
          end += 1
        }
        if (end !== -1 && end < text.length) {
          pushText(i)
          out.push({
            type: 'math',
            value: text.slice(i + 1, end),
            display: false,
            raw: text.slice(i, end + 1),
          })
          i = end + 1
          textStart = i
          continue
        }
      }
    }

    i += 1
  }

  pushText(text.length)
  return out
}

/**
 * 常见 LaTeX 命令归一化。
 * 例如 \frac12 -> \frac{1}{2}，\le -> \leq。
 */
export function normalizeLatex(input) {
  let s = String(input == null ? '' : input).trim()
  s = s.replace(/\\dfrac(?![a-zA-Z])/g, '\\frac')
  s = s.replace(/\\tfrac(?![a-zA-Z])/g, '\\frac')
  s = s.replace(/\\le(?![a-zA-Z])/g, '\\leq')
  s = s.replace(/\\ge(?![a-zA-Z])/g, '\\geq')
  s = s.replace(/\\ne(?![a-zA-Z])/g, '\\neq')
  s = s.replace(/\\frac\s*([0-9A-Za-z])\s*([0-9A-Za-z])/g, '\\frac{$1}{$2}')
  return s
}

function readGroup(text, start) {
  // start 指向 '{'
  let depth = 0
  for (let i = start; i < text.length; i += 1) {
    if (text[i] === '\\') { i += 1; continue }
    if (text[i] === '{') depth += 1
    else if (text[i] === '}') {
      depth -= 1
      if (depth === 0) {
        return { content: text.slice(start + 1, i), end: i + 1 }
      }
    }
  }
  return { content: text.slice(start + 1), end: text.length }
}

function skipSpace(text, index) {
  let i = index
  while (i < text.length && /\s/.test(text[i])) i += 1
  return i
}

function replaceFractions(text, replacer) {
  let out = ''
  let i = 0
  while (i < text.length) {
    const index = text.indexOf('\\frac', i)
    if (index === -1) {
      out += text.slice(i)
      break
    }
    out += text.slice(i, index)
    let cursor = skipSpace(text, index + 5)
    if (text[cursor] !== '{') {
      out += text.slice(index, cursor)
      i = cursor
      continue
    }
    const numerator = readGroup(text, cursor)
    cursor = skipSpace(text, numerator.end)
    if (text[cursor] !== '{') {
      out += text.slice(index, cursor)
      i = cursor
      continue
    }
    const denominator = readGroup(text, cursor)
    out += replacer(numerator.content, denominator.content)
    i = denominator.end
  }
  return out
}

function replaceBraced(text, command, replacer) {
  let out = ''
  let i = 0
  while (i < text.length) {
    const index = text.indexOf(command, i)
    if (index === -1) {
      out += text.slice(i)
      break
    }
    out += text.slice(i, index)
    let cursor = skipSpace(text, index + command.length)
    if (text[cursor] !== '{') {
      out += text.slice(index, cursor)
      i = cursor
      continue
    }
    const group = readGroup(text, cursor)
    out += replacer(group.content)
    i = group.end
  }
  return out
}

function toSuperscript(value) {
  const text = String(value == null ? '' : value)
  if (!text) return ''
  const mapped = Array.from(text).map((ch) => SUP_DIGITS[ch] || '').join('')
  return mapped && mapped.length === text.length ? mapped : `^(${text})`
}

function toSubscript(value) {
  const text = String(value == null ? '' : value)
  if (!text) return ''
  const mapped = Array.from(text).map((ch) => SUB_DIGITS[ch] || '').join('')
  return mapped && mapped.length === text.length ? mapped : `_(${text})`
}

function replaceScripts(text) {
  let s = text
  // ^{...} / _{...}
  s = s.replace(/\^\{([^{}]*)\}/g, (_, value) => toSuperscript(value))
  s = s.replace(/_\{([^{}]*)\}/g, (_, value) => toSubscript(value))
  // ^2 / _1 这类单字符
  s = s.replace(/\^([0-9A-Za-z+\-])/g, (_, value) => toSuperscript(value))
  s = s.replace(/_([0-9A-Za-z+\-])/g, (_, value) => toSubscript(value))
  return s
}

function speechPower(value) {
  const text = String(value == null ? '' : value)
  if (text === '2') return '的平方'
  if (text === '3') return '的立方'
  return `的${text}次方`
}

function replaceScriptsSpeech(text) {
  let s = text
  s = s.replace(/\^\{([^{}]*)\}/g, (_, value) => speechPower(value))
  s = s.replace(/_\{([^{}]*)\}/g, (_, value) => `下标${value}`)
  s = s.replace(/\^([0-9A-Za-z+\-])/g, (_, value) => speechPower(value))
  s = s.replace(/_([0-9A-Za-z+\-])/g, (_, value) => `下标${value}`)
  return s
}

function replaceLatexCommands(text, speech = false) {
  let s = text
  const greek = speech ? SPEECH_GREEK : GREEK

  // 字体/文本/修饰命令：保留括号里的内容
  for (const command of [
    '\\text', '\\textrm', '\\textbf', '\\textit', '\\mathrm', '\\mathbf',
    '\\mathit', '\\mathbb', '\\mathcal', '\\operatorname', '\\overline',
    '\\underline', '\\hat', '\\bar', '\\widehat', '\\widetilde',
  ]) {
    s = replaceBraced(s, command, (value) => value)
  }

  // 向量
  s = replaceBraced(s, '\\overrightarrow', (value) => (speech ? `向量${value}` : `→${value}`))
  s = replaceBraced(s, '\\vec', (value) => (speech ? `向量${value}` : `→${value}`))

  // 根号
  s = replaceBraced(s, '\\sqrt', (value) => (speech ? `根号${value}` : `√(${value})`))

  // 度数
  s = s.replace(/\^\{?\\circ\}?/g, speech ? '度' : '°')
  s = s.replace(/\\circ/g, speech ? '度' : '°')

  // 希腊字母
  s = s.replace(/\\([A-Za-z]+)/g, (match, name) => {
    if (greek[name]) return greek[name]
    return match
  })

  // 常见符号
  s = s.replace(/\\([A-Za-z]+)/g, (match, name) => {
    if (SYMBOLS[name] != null) return SYMBOLS[name]
    return match
  })

  // 间距和排版命令
  s = s.replace(/\\left|\\right|\\displaystyle|\\textstyle|\\limits|\\nolimits/g, '')
  s = s.replace(/\\[,;!]/g, ' ')
  s = s.replace(/\\quad|\\qquad/g, ' ')
  s = s.replace(/\\(?:%|&|#|_|\$)/g, (match) => match.slice(1))
  s = s.replace(/\\begin\{[^}]*\}|\\end\{[^}]*\}/g, ' ')
  s = s.replace(/\\\\/g, ' ')

  // 未识别的命令去掉反斜杠，至少不让学生看到 TeX 源码
  s = s.replace(/\\([A-Za-z]+)/g, '$1')
  s = s.replace(/[{}]/g, '')
  s = s.replace(/\\/g, '')
  return s
}

function cleanup(text) {
  return String(text == null ? '' : text)
    .replace(/\s+/g, ' ')
    .replace(/\s*([，。；：、])\s*/g, '$1')
    .trim()
}

/**
 * LaTeX -> 纯文本。用于不支持公式渲染的平台，或渲染失败时的兜底。
 */
export function latexToPlain(input) {
  let s = normalizeLatex(input)
  s = replaceFractions(s, (a, b) => `(${latexToPlain(a)})/(${latexToPlain(b)})`)
  s = replaceLatexCommands(s, false)
  s = replaceScripts(s)
  return cleanup(s)
}

/**
 * LaTeX -> 朗读文本。分数按中文习惯读成“b分之a”。
 */
export function latexToSpeech(input) {
  let s = normalizeLatex(input)
  // 带分数：1\frac{1}{2} 读作“1又2分之1”
  s = s.replace(
    /(^|[^0-9A-Za-z])([0-9]+)\s*\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g,
    (_, prefix, whole, numerator, denominator) =>
      `${prefix}${whole}又${latexToSpeech(denominator)}分之${latexToSpeech(numerator)}`
  )
  s = replaceFractions(s, (a, b) => `${latexToSpeech(b)}分之${latexToSpeech(a)}`)
  s = replaceLatexCommands(s, true)
  s = replaceScriptsSpeech(s)
  s = s.replace(/\+/g, '加')
  s = s.replace(/=(?!=)/g, '等于')
  s = s.replace(/[×·]/g, '乘')
  s = s.replace(/÷/g, '除以')
  s = s.replace(/±/g, '正负')
  s = s.replace(/≤/g, '小于等于')
  s = s.replace(/≥/g, '大于等于')
  s = s.replace(/≠/g, '不等于')
  s = s.replace(/≈/g, '约等于')
  s = s.replace(/°/g, '度')
  s = s.replace(/√/g, '根号')
  s = s.replace(/∞/g, '无穷大')
  s = s.replace(/∠/g, '角')
  s = s.replace(/△/g, '三角形')
  s = s.replace(/π/g, '派')
  return cleanup(s)
}

/**
 * 按换行切分文本，但不切开 $...$ / $$...$$ / \(...\) / \[...\] 里的内容。
 * 用于把模型回答拆成“步骤”时保护行间公式。
 */
export function splitLinesOutsideMath(input) {
  const lines = []
  let current = ''

  for (const segment of splitMathSegments(input)) {
    if (segment.type === 'math') {
      current += segment.raw
      continue
    }
    const parts = segment.value.split('\n')
    parts.forEach((part, index) => {
      if (index > 0) {
        lines.push(current)
        current = ''
      }
      current += part
    })
  }
  lines.push(current)
  return lines.map((line) => line.trim()).filter(Boolean)
}

/**
 * 整段文本的纯文本化：公式段走 latexToPlain，普通文本保持不变。
 */
export function textToPlain(input) {
  return splitMathSegments(input)
    .map((segment) => (segment.type === 'text' ? segment.value : latexToPlain(segment.value)))
    .join('')
}

/**
 * 整段文本的朗读文本：公式段走 latexToSpeech，普通文本保持不变。
 */
export function textToSpeech(input) {
  return splitMathSegments(input)
    .map((segment) => (segment.type === 'text' ? segment.value : latexToSpeech(segment.value)))
    .join('')
}
