# -*- coding: utf-8 -*-
"""
Standalone OCR runner for PaddleOCR with multi-pass preprocessing.
Tries multiple image processing approaches to maximize text extraction.
"""
import sys
import json
import os

# Force-inject site-packages
_EXTRA_PATHS = [
    r'C:\Users\Lenovo\AppData\Roaming\Python\Python312\site-packages',
    r'C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\Lib\site-packages',
    r'C:\Program Files\Odoo 17.0.20260217\python\Lib\site-packages',
]
for p in _EXTRA_PATHS:
    if p not in sys.path:
        sys.path.insert(0, p)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': 'No image path', 'full_text': '', 'lines': []}))
        sys.exit(1)

    image_path = sys.argv[1]
    if not os.path.isfile(image_path):
        print(json.dumps({'success': False, 'error': f'File not found: {image_path}', 'full_text': '', 'lines': []}))
        sys.exit(1)

    # Redirect stdout to stderr BEFORE importing paddle
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    try:
        os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
        os.environ['FLAGS_call_stack_level'] = '0'
        os.environ['FLAGS_use_mkldnn'] = '0'
        os.environ['FLAGS_enable_pir_api'] = '0'
        os.environ['FLAGS_enable_pir_in_executor'] = '0'

        from paddleocr import PaddleOCR
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        import numpy as np

        # Create OCR instance
        try:
            ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
        except (TypeError, ValueError):
            try:
                ocr = PaddleOCR(use_textline_orientation=True, lang='en')
            except Exception:
                ocr = PaddleOCR(lang='en')

        def run_ocr_on_image(img_path):
            """Run OCR and return list of (text, confidence) tuples."""
            results = []
            try:
                result = ocr.ocr(img_path, cls=True)
                if result:
                    for page in result:
                        if isinstance(page, list):
                            for item in page:
                                if isinstance(item, (list, tuple)) and len(item) >= 2:
                                    text_info = item[1]
                                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                                        results.append((str(text_info[0]), float(text_info[1])))
            except Exception:
                pass
            return results

        def run_ocr_on_array(img_array):
            """Run OCR on numpy array and return list of (text, confidence) tuples."""
            results = []
            try:
                result = ocr.ocr(img_array, cls=True)
                if result:
                    for page in result:
                        if isinstance(page, list):
                            for item in page:
                                if isinstance(item, (list, tuple)) and len(item) >= 2:
                                    text_info = item[1]
                                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                                        results.append((str(text_info[0]), float(text_info[1])))
            except Exception:
                pass
            return results

        import tempfile
        all_lines = []
        temp_files = []

        # === PASS 1: Original image (color) ===
        pass1 = run_ocr_on_image(image_path)
        all_lines.extend(pass1)
        sys.stderr.write(f'[OCR] Pass 1 (original): {len(pass1)} lines\n')

        # Load image for preprocessing
        image = Image.open(image_path)

        # === PASS 2: High contrast grayscale ===
        try:
            img2 = image.convert('L')
            img2 = ImageOps.autocontrast(img2, cutoff=5)
            enhancer = ImageEnhance.Sharpness(img2)
            img2 = enhancer.enhance(2.0)
            # Save temp and OCR
            tmp2 = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            img2.save(tmp2.name)
            temp_files.append(tmp2.name)
            pass2 = run_ocr_on_image(tmp2.name)
            all_lines.extend(pass2)
            sys.stderr.write(f'[OCR] Pass 2 (grayscale+contrast): {len(pass2)} lines\n')
        except Exception as e:
            sys.stderr.write(f'[OCR] Pass 2 failed: {e}\n')

        # === PASS 3: Binary threshold (for digits near barcode) ===
        try:
            img3 = image.convert('L')
            # Adaptive-like: use a medium threshold
            img3 = img3.point(lambda x: 255 if x > 140 else 0, '1')
            img3 = img3.convert('L')
            tmp3 = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            img3.save(tmp3.name)
            temp_files.append(tmp3.name)
            pass3 = run_ocr_on_image(tmp3.name)
            all_lines.extend(pass3)
            sys.stderr.write(f'[OCR] Pass 3 (binary threshold): {len(pass3)} lines\n')
        except Exception as e:
            sys.stderr.write(f'[OCR] Pass 3 failed: {e}\n')

        # === PASS 4: Crop bottom 35% (where NIM usually is) + high contrast ===
        try:
            w, h = image.size
            bottom_crop = image.crop((0, int(h * 0.65), w, h))
            # Enhance bottom crop
            bottom_crop = bottom_crop.convert('L')
            bottom_crop = ImageOps.autocontrast(bottom_crop, cutoff=10)
            enhancer = ImageEnhance.Contrast(bottom_crop)
            bottom_crop = enhancer.enhance(2.0)
            enhancer = ImageEnhance.Sharpness(bottom_crop)
            bottom_crop = enhancer.enhance(2.0)
            # Scale up for better digit recognition
            new_w = int(bottom_crop.width * 2)
            new_h = int(bottom_crop.height * 2)
            bottom_crop = bottom_crop.resize((new_w, new_h), Image.LANCZOS)

            tmp4 = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            bottom_crop.save(tmp4.name)
            temp_files.append(tmp4.name)
            pass4 = run_ocr_on_image(tmp4.name)
            all_lines.extend(pass4)
            sys.stderr.write(f'[OCR] Pass 4 (bottom crop): {len(pass4)} lines\n')
        except Exception as e:
            sys.stderr.write(f'[OCR] Pass 4 failed: {e}\n')

        # === PASS 5: Bottom 35% with inverted colors + binary ===
        try:
            w, h = image.size
            bottom_crop = image.crop((0, int(h * 0.65), w, h))
            bottom_crop = bottom_crop.convert('L')
            bottom_crop = ImageOps.invert(bottom_crop)
            bottom_crop = bottom_crop.point(lambda x: 255 if x > 100 else 0, '1')
            bottom_crop = bottom_crop.convert('L')
            new_w = int(bottom_crop.width * 2)
            new_h = int(bottom_crop.height * 2)
            bottom_crop = bottom_crop.resize((new_w, new_h), Image.LANCZOS)

            tmp5 = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            bottom_crop.save(tmp5.name)
            temp_files.append(tmp5.name)
            pass5 = run_ocr_on_image(tmp5.name)
            all_lines.extend(pass5)
            sys.stderr.write(f'[OCR] Pass 5 (bottom inverted): {len(pass5)} lines\n')
        except Exception as e:
            sys.stderr.write(f'[OCR] Pass 5 failed: {e}\n')

        # Cleanup temp files
        for tf in temp_files:
            try:
                os.unlink(tf)
            except Exception:
                pass

        # Deduplicate lines (keep highest confidence for each text)
        seen = {}
        for text, conf in all_lines:
            key = text.strip()
            if key and (key not in seen or conf > seen[key]):
                seen[key] = conf

        lines = [{'text': k, 'confidence': v} for k, v in seen.items()]
        full_text = ' '.join([l['text'] for l in lines])

        output = {
            'success': True,
            'full_text': full_text,
            'lines': lines,
            'line_count': len(lines),
            'passes': 5,
        }

        sys.stdout = real_stdout
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)

    except Exception as e:
        import traceback
        sys.stdout = real_stdout
        print(json.dumps({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
            'full_text': '',
            'lines': [],
        }, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
