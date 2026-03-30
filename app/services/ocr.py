import asyncio
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream


class WindowsOcrService:
    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 5) -> str:
        return asyncio.run(self._extract_text_from_pdf_async(pdf_path, max_pages=max_pages))

    async def _extract_text_from_pdf_async(self, pdf_path: str, max_pages: int = 5) -> str:
        document = pdfium.PdfDocument(str(Path(pdf_path)))
        engine = OcrEngine.try_create_from_user_profile_languages()
        page_text_blocks = []

        page_count = min(len(document), max_pages)
        for page_index in range(page_count):
            page = document[page_index]
            rendered = page.render(scale=2.2)
            pil_image = rendered.to_pil()
            image_buffer = BytesIO()
            pil_image.save(image_buffer, format="PNG")

            stream = InMemoryRandomAccessStream()
            writer = DataWriter(stream)
            writer.write_bytes(image_buffer.getvalue())
            await writer.store_async()
            writer.detach_stream()
            stream.seek(0)

            decoder = await BitmapDecoder.create_async(stream)
            software_bitmap = await decoder.get_software_bitmap_async()
            result = await engine.recognize_async(software_bitmap)

            line_text = [line.text.strip() for line in result.lines if line.text.strip()]
            if line_text:
                page_text_blocks.append("\n".join(line_text))

        return "\n\n".join(page_text_blocks)
