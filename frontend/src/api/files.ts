import { postForm } from '../lib/api'

export interface UploadedFile {
  filename: string
  size: number
  sha256: string
}

export interface UploadResult {
  upload_id: string
  dir: string
  files: UploadedFile[]
}

export const filesApi = {
  // 多文件一次性上传，后端返回一个 upload_id（一个目录）。
  // run 接口把 upload_id 作为 type=files 参数值，build_argv 解析成 --input-dir。
  upload: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return postForm<UploadResult>('/api/upload', form)
  },
}
