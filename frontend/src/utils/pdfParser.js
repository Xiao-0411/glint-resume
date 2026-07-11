/**
 * PDF 解析工具 —— 基于 pdfjs-dist
 * 注意：worker 通过 Vite 的 ?worker 方式打包，确保跨域安全
 */
import * as pdfjsLib from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'

// 初始化 worker（只设置一次）
if (!pdfjsLib.GlobalWorkerOptions.workerPort) {
  pdfjsLib.GlobalWorkerOptions.workerPort = new PdfWorker()
}

/**
 * 解析 PDF 文件
 * @param {File} file - 上传的 PDF 文件
 * @param {Function} onProgress - 进度回调 (0-1)
 * @returns {Promise<{text: string, numPages: number}>}
 */
export async function parsePdf(file, onProgress) {
  if (!file) throw new Error('未提供文件')
  if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    throw new Error('请上传 PDF 格式的文件')
  }

  const arrayBuffer = await file.arrayBuffer()
  const loadingTask = pdfjsLib.getDocument({
    data: arrayBuffer,
    // 内置中文字体支持（防止部分 PDF 文字缺失）
    cMapUrl: 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.0.379/cmaps/',
    cMapPacked: true
  })

  if (onProgress) {
    loadingTask.onProgress = ({ loaded, total }) => {
      const ratio = total > 0 ? loaded / total : 0.5
      onProgress(Math.min(0.5, ratio * 0.5))   // 0~50% 留给加载
    }
  }

  const pdf = await loadingTask.promise
  let fullText = ''
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i)
    const content = await page.getTextContent()

    // 按 y 坐标分行（top→bottom）
    const lines = {}
    content.items.forEach(item => {
      if (!item.str) return
      // transform[5] 是 y 坐标
      const y = Math.round(item.transform[5])
      if (!lines[y]) lines[y] = []
      lines[y].push({ x: item.transform[4], str: item.str })
    })
    const sortedYs = Object.keys(lines)
      .map(Number)
      .sort((a, b) => b - a) // y 从大到小（视觉上从上到下）

    const pageText = sortedYs
      .map(y => lines[y].sort((a, b) => a.x - b.x).map(t => t.str).join(' '))
      .join('\n')
    fullText += pageText + '\n\n'

    if (onProgress) {
      onProgress(0.5 + (i / pdf.numPages) * 0.5)
    }
  }

  return {
    text: fullText.trim(),
    numPages: pdf.numPages
  }
}

/**
 * 简单格式化文件大小
 */
export function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}
