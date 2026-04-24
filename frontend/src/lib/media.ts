function replaceExtension(fileName: string, nextExtension: string) {
  const lastDot = fileName.lastIndexOf(".")
  if (lastDot === -1) {
    return `${fileName}${nextExtension}`
  }
  return `${fileName.slice(0, lastDot)}${nextExtension}`
}

async function canvasToBlob(
  canvas: HTMLCanvasElement,
  mimeType: string,
  quality: number
) {
  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob((blob) => resolve(blob), mimeType, quality)
  })
}

export async function optimizeUploadFile(file: File): Promise<File> {
  if (!file.type.startsWith("image/") || file.type === "image/gif") {
    return file
  }

  const imageBitmap = await createImageBitmap(file)
  const maxSide = 1600
  const largestSide = Math.max(imageBitmap.width, imageBitmap.height)
  const scale = largestSide > maxSide ? maxSide / largestSide : 1

  const canvas = document.createElement("canvas")
  canvas.width = Math.max(1, Math.round(imageBitmap.width * scale))
  canvas.height = Math.max(1, Math.round(imageBitmap.height * scale))

  const context = canvas.getContext("2d")
  if (!context) {
    return file
  }

  context.drawImage(imageBitmap, 0, 0, canvas.width, canvas.height)

  const preferredType = "image/webp"
  const compressedBlob = await canvasToBlob(canvas, preferredType, 0.82)
  imageBitmap.close()

  if (!compressedBlob || compressedBlob.size >= file.size) {
    return file
  }

  return new File(
    [compressedBlob],
    replaceExtension(file.name, ".webp"),
    { type: preferredType }
  )
}
