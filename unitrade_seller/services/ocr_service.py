# -*- coding: utf-8 -*-
"""
OCR Service for KTM (Student ID Card) verification.

Uses subprocess to call PaddleOCR via an external script (ocr_runner.py).
This solves the issue where PaddleOCR is installed in the user's
Python site-packages but not visible to the Odoo Windows Service process.
"""
import re
import logging
import base64
import requests

_logger = logging.getLogger(__name__)

# === Constants ===
NIM_REGEX = re.compile(r'\d{8,12}')
KTM_KEYWORDS = [
    'KARTU', 'MAHASISWA', 'UNISA', 'STUDENT', 'UNIVERSITAS',
    'NIM', 'FAKULTAS', 'PRODI', 'PROGRAM STUDI', 'TANDA',
    'AISYIYAH', 'YOGYAKARTA', 'TEKNOLOGI', 'INFORMASI',
]
NAME_PATTERN = re.compile(r'[A-Za-z]{2,}(?:\s+[A-Za-z]{2,})+')
GOOGLE_VISION_API_KEY_PARAM = 'unitrade.google_vision.api_key'


class KTMOCRService:
    """Service class for KTM image OCR processing."""

    # ─────────────── OCR via Subprocess ───────────────

    # ─────────────── Google Cloud Vision API ───────────────

    @staticmethod
    def call_google_vision_api(env, image_bytes):
        """
        Send image to Google Cloud Vision API for TEXT_DETECTION.
        Returns the full concatenated text.
        """
        api_key = env['ir.config_parameter'].sudo().get_param(
            GOOGLE_VISION_API_KEY_PARAM, ''
        )
        if not api_key or api_key == 'INSERT_YOUR_API_KEY_HERE':
            raise RuntimeError("Google Vision API Key is not configured.")

        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
        
        # Encode image to base64
        encoded_image = base64.b64encode(image_bytes).decode('utf-8')
        
        payload = {
            "requests": [
                {
                    "image": {
                        "content": encoded_image
                    },
                    "features": [
                        {
                            "type": "TEXT_DETECTION"
                        }
                    ]
                }
            ]
        }

        _logger.info('[OCR] Sending request to Google Cloud Vision API...')
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            responses = data.get('responses', [])
            if not responses:
                raise RuntimeError("Empty response from Google Vision API")
                
            vision_result = responses[0]
            
            # Check for API error inside response
            if 'error' in vision_result:
                err_msg = vision_result['error'].get('message', 'Unknown API Error')
                raise RuntimeError(f"Vision API Error: {err_msg}")
                
            text_annotations = vision_result.get('textAnnotations', [])
            if not text_annotations:
                _logger.info('[OCR] No text found in image.')
                return ""
                
            # The first annotation contains the full text block with line breaks
            full_text = text_annotations[0].get('description', '')
            
            # Google Vision often includes newline characters. 
            # Replace them with spaces for our pipeline consistency.
            full_text_inline = full_text.replace('\n', ' ').strip()
            
            _logger.info('[OCR] Google Vision Extracted Text (first 200 chars): "%s"', full_text_inline[:200])
            return full_text_inline

        except requests.exceptions.HTTPError as e:
            # Try to get the detailed error message from Google's JSON response
            error_details = str(e)
            try:
                err_json = e.response.json()
                if 'error' in err_json:
                    error_details = f"{e.response.status_code} - {err_json['error'].get('message', 'Unknown')}"
            except Exception:
                pass
            
            _logger.error('[OCR] Vision API HTTP Error: %s', error_details)
            raise RuntimeError(f"Vision API Error: {error_details}")
            
        except requests.exceptions.RequestException as e:
            _logger.error('[OCR] HTTP Request failed: %s', e)
            raise RuntimeError(f"HTTP Request failed: {str(e)}")
        except Exception as e:
            _logger.error('[OCR] Google Vision API processing failed: %s', e)
            raise RuntimeError(f"Google Vision processing failed: {str(e)}")

    # ─────────────── Text Normalization (for NIM only) ───────────────

    @staticmethod
    def normalize_for_nim(text):
        """
        Normalize OCR text specifically for NIM extraction.
        Only applies letter→digit substitution to characters
        adjacent to actual digits.
        """
        char_map = {
            'O': '0', 'o': '0',
            'I': '1', 'l': '1',
            'S': '5', 's': '5',
            'B': '8',
            'Z': '2', 'z': '2',
        }
        result = list(text)
        length = len(result)

        for i in range(length):
            ch = result[i]
            if ch in char_map:
                prev_is_digit = (i > 0 and result[i - 1].isdigit())
                next_is_digit = (i < length - 1 and result[i + 1].isdigit())
                if prev_is_digit or next_is_digit:
                    result[i] = char_map[ch]

        normalized = ''.join(result)
        _logger.info('[NORMALIZE] Result (first 200): "%s"', normalized[:200])
        return normalized

    # ─────────────── KTM Keyword Validation ───────────────

    @staticmethod
    def validate_ktm_keywords(ocr_text):
        """Check if OCR text contains KTM-related keywords."""
        try:
            text_upper = ocr_text.upper().strip()
            found = [kw for kw in KTM_KEYWORDS if kw in text_upper]
            _logger.info('[KEYWORD] Text: "%s"', text_upper[:200])
            _logger.info('[KEYWORD] Found: %s', found if found else 'NONE')
            return (bool(found), found)
        except Exception as e:
            _logger.exception('[KEYWORD] Validation failed: %s', e)
            return (False, [])

    # ─────────────── Name Detection ───────────────

    @staticmethod
    def detect_name(ocr_text):
        """Detect a human name in the OCR text."""
        try:
            non_name_words = {
                'UNIVERSITAS', 'AISYIYAH', 'YOGYAKARTA', 'TEKNOLOGI', 'INFORMASI',
                'FAKULTAS', 'PROGRAM', 'STUDI', 'KARTU', 'MAHASISWA', 'STUDENT',
                'TANDA', 'PENGENAL', 'PRODI', 'UNISA',
            }

            matches = NAME_PATTERN.findall(ocr_text)
            _logger.info('[NAME] All regex matches: %s', matches)

            name_candidates = []
            for m in matches:
                words = m.strip().split()
                meaningful = [w for w in words if w.upper() not in non_name_words]
                if len(meaningful) >= 2:
                    name_candidates.append(m.strip())

            _logger.info('[NAME] After filtering: %s', name_candidates)

            if name_candidates:
                name = max(name_candidates, key=len)
                _logger.info('[NAME] ✅ Detected: "%s"', name)
                return name

            # Fallback
            words = ocr_text.split()
            alpha_words = [w for w in words if w.isalpha() and len(w) >= 2
                           and w.upper() not in non_name_words]
            if len(alpha_words) >= 2:
                name = ' '.join(alpha_words[:5])
                _logger.info('[NAME] Fallback: "%s"', name)
                return name

            _logger.info('[NAME] ❌ No name detected.')
            return None
        except Exception as e:
            _logger.exception('[NAME] Detection failed: %s', e)
            return None

    # ─────────────── NIM Extraction ───────────────

    @staticmethod
    def extract_nim(raw_text, normalized_text):
        """Extract NIM (8-12 digits) from raw text first, then normalized."""
        try:
            matches_raw = NIM_REGEX.findall(raw_text)
            _logger.info('[NIM] Raw matches: %s', matches_raw)
            if matches_raw:
                nim = matches_raw[0].strip()
                _logger.info('[NIM] ✅ From raw: "%s"', nim)
                return nim

            matches_norm = NIM_REGEX.findall(normalized_text)
            _logger.info('[NIM] Normalized matches: %s', matches_norm)
            if matches_norm:
                nim = matches_norm[0].strip()
                _logger.info('[NIM] ✅ From normalized: "%s"', nim)
                return nim

            _logger.info('[NIM] ❌ Not found.')
            return None
        except Exception as e:
            _logger.exception('[NIM] Extraction failed: %s', e)
            return None

    # ─────────────── Database NIM Lookup ───────────────

    @staticmethod
    def check_nim_in_database(env, nim):
        """Check NIM in unisa.student with exact → ilike → manual fallback."""
        try:
            nim_clean = nim.strip()
            _logger.info('[DB] Searching NIM: "%s"', nim_clean)

            all_students = env['unisa.student'].sudo().search([])
            all_nims = [(s.nim, s.name) for s in all_students]
            _logger.info('[DB] Total records: %d — All NIM: %s', len(all_nims), all_nims)

            # Exact match
            student = env['unisa.student'].sudo().search(
                [('nim', '=', nim_clean)], limit=1
            )
            if student:
                _logger.info('[DB] ✅ EXACT: NIM=%s, Name=%s', student.nim, student.name)
                return {'found': True, 'student': student, 'method': 'exact'}

            # ilike match
            student = env['unisa.student'].sudo().search(
                [('nim', 'ilike', nim_clean)], limit=1
            )
            if student:
                _logger.info('[DB] ✅ ILIKE: NIM=%s, Name=%s', student.nim, student.name)
                return {'found': True, 'student': student, 'method': 'ilike'}

            # Manual strip match
            for s in all_students:
                if s.nim and s.nim.strip() == nim_clean:
                    _logger.info('[DB] ✅ MANUAL: NIM=%s, Name=%s', s.nim, s.name)
                    return {'found': True, 'student': s, 'method': 'manual'}

            # === PREFIX FALLBACK ===
            # OCR often loses leading digit(s). Try common prefixes.
            # UNISA NIMs typically start with '2' (e.g., 2411501021)
            if len(nim_clean) >= 8:
                prefixes_to_try = ['2', '24']
                for prefix in prefixes_to_try:
                    prefixed_nim = prefix + nim_clean
                    _logger.info('[DB] Trying prefix "%s": NIM=%s', prefix, prefixed_nim)
                    student = env['unisa.student'].sudo().search(
                        [('nim', '=', prefixed_nim)], limit=1
                    )
                    if student:
                        _logger.info('[DB] ✅ PREFIX "%s": NIM=%s, Name=%s', prefix, student.nim, student.name)
                        return {'found': True, 'student': student, 'method': f'prefix_{prefix}'}

            # === ENDSWITH FALLBACK ===
            # Check if any DB NIM ends with the OCR NIM
            for s in all_students:
                if s.nim and s.nim.strip().endswith(nim_clean):
                    _logger.info('[DB] ✅ ENDSWITH: NIM=%s, Name=%s', s.nim, s.name)
                    return {'found': True, 'student': s, 'method': 'endswith'}

            _logger.info('[DB] ❌ NIM "%s" NOT found (tried exact, ilike, manual, prefix, endswith).', nim_clean)
            return {'found': False, 'student': None, 'method': 'none'}
        except Exception as e:
            _logger.exception('[DB] Check failed: %s', e)
            return {'found': False, 'student': None, 'method': 'error'}

    # ─────────────── Name-based DB Lookup (Fallback) ───────────────

    @staticmethod
    def check_name_in_database(env, ocr_name):
        """Fallback: match OCR-detected name against student DB when NIM is unreadable."""
        try:
            if not ocr_name:
                return {'found': False, 'student': None, 'method': 'none'}

            # Clean OCR name: remove non-name words, keep only alpha words
            non_name_words = {
                'UNIVERSITAS', 'AISYIYAH', 'YOGYAKARTA', 'TEKNOLOGI', 'INFORMASI',
                'FAKULTAS', 'PROGRAM', 'STUDI', 'KARTU', 'MAHASISWA', 'STUDENT',
                'TANDA', 'PENGENAL', 'PRODI', 'UNISA', 'TEKNIK',
            }

            ocr_words = [w.upper() for w in ocr_name.split()
                         if w.isalpha() and len(w) >= 2 and w.upper() not in non_name_words]
            _logger.info('[DB-NAME] OCR name words: %s', ocr_words)

            if not ocr_words:
                return {'found': False, 'student': None, 'method': 'none'}

            all_students = env['unisa.student'].sudo().search([])

            best_match = None
            best_score = 0

            for student in all_students:
                if not student.name:
                    continue
                db_words = [w.upper() for w in student.name.split() if len(w) >= 2]
                db_name_upper = student.name.upper()

                match_count = 0
                for db_w in db_words:
                    matched = False
                    for ocr_w in ocr_words:
                        # 1. Exact match
                        if ocr_w == db_w:
                            matched = True
                            break
                        # 2. Compound word: OCR merged words (e.g., DWIREZKY contains DWI)
                        if len(ocr_w) > len(db_w) and db_w in ocr_w:
                            matched = True
                            break
                        # 3. Substring: DB word contains OCR word
                        if len(db_w) > len(ocr_w) and ocr_w in db_w:
                            matched = True
                            break
                        # 4. Fuzzy: >=50% chars match (handles MOIIAMAD vs MOHAMAD)
                        if len(ocr_w) >= 3 and len(db_w) >= 3:
                            common = sum(1 for a, b in zip(ocr_w, db_w) if a == b)
                            max_len = max(len(ocr_w), len(db_w))
                            if common / max_len >= 0.5:
                                matched = True
                                break
                    if matched:
                        match_count += 1

                _logger.info('[DB-NAME] Student "%s": %d/%d words matched', student.name, match_count, len(db_words))

                if match_count >= 2 and match_count > best_score:
                    best_score = match_count
                    best_match = student
                    _logger.info('[DB-NAME] Candidate: %s (score=%d/%d)', student.name, match_count, len(db_words))

            if best_match:
                _logger.info('[DB-NAME] ✅ MATCHED: %s (NIM=%s, score=%d)',
                             best_match.name, best_match.nim, best_score)
                return {'found': True, 'student': best_match, 'method': 'name_fuzzy'}

            _logger.info('[DB-NAME] ❌ No name match found.')
            return {'found': False, 'student': None, 'method': 'none'}
        except Exception as e:
            _logger.exception('[DB-NAME] Failed: %s', e)
            return {'found': False, 'student': None, 'method': 'error'}

    # ─────────────── Main Pipeline ───────────────

    @classmethod
    def process_ktm(cls, env, image_bytes):
        """
        Full KTM verification pipeline using subprocess for OCR.
        1. Run OCR via subprocess (ocr_runner.py)
        2. Validate KTM keywords
        3. Detect name
        4. Extract NIM
        5. Check NIM in database
        """
        result = {
            'ocr_text': '',
            'ocr_text_normalized': '',
            'is_ktm': False,
            'name_detected': None,
            'nim': None,
            'nim_registered': False,
            'student_name': None,
            'db_method': 'none',
            'verification_status': 'rejected',
            'reason': '',
        }

        try:
            _logger.info('=' * 60)
            _logger.info('[PIPELINE] Starting KTM verification (Google Vision API mode)...')
            _logger.info('=' * 60)

            # Step 1: Run OCR via Google Vision API
            try:
                raw_text = cls.call_google_vision_api(env, image_bytes)
            except Exception as e:
                _logger.exception('[PIPELINE] Google Vision API failed: %s', e)
                result['reason'] = f'vision_api_failed: {str(e)}'
                result['ocr_text'] = f'API Error: {str(e)}'
                return result

            result['ocr_text'] = raw_text

            if not raw_text.strip():
                result['verification_status'] = 'invalid_image'
                result['reason'] = 'ocr_empty'
                _logger.info('[PIPELINE] ❌ OCR returned empty text.')
                return result

            # Step 2: Validate KTM keywords
            is_ktm, keywords_found = cls.validate_ktm_keywords(raw_text)
            result['is_ktm'] = is_ktm

            if not is_ktm:
                result['verification_status'] = 'invalid_image'
                result['reason'] = 'no_ktm_keywords'
                _logger.info('[PIPELINE] ❌ No KTM keywords found.')
                return result

            # Step 3: Detect name
            name_detected = cls.detect_name(raw_text)
            result['name_detected'] = name_detected

            if not name_detected:
                result['verification_status'] = 'no_name'
                result['reason'] = 'name_not_detected'
                _logger.info('[PIPELINE] ❌ No name detected.')
                return result

            # Step 4: Normalize and extract NIM
            normalized_text = cls.normalize_for_nim(raw_text)
            result['ocr_text_normalized'] = normalized_text

            nim = cls.extract_nim(raw_text, normalized_text)
            result['nim'] = nim

            if not nim:
                _logger.info('[PIPELINE] NIM not found — trying name-based fallback...')
                # FALLBACK: Try matching by name instead
                name_result = cls.check_name_in_database(env, name_detected)
                if name_result['found'] and name_result['student']:
                    result['nim'] = name_result['student'].nim
                    result['nim_registered'] = True
                    result['student_name'] = name_result['student'].name
                    result['db_method'] = name_result['method']
                    result['verification_status'] = 'approved'
                    result['reason'] = 'name_matched_in_db'
                    _logger.info(
                        '[PIPELINE] ✅ APPROVED (via name) — Student=%s, NIM=%s',
                        name_result['student'].name, name_result['student'].nim,
                    )
                else:
                    result['verification_status'] = 'rejected'
                    result['reason'] = 'nim_not_extracted'
                    _logger.info('[PIPELINE] ❌ NIM not found and name match failed.')
                    return result

            # Step 5: Check NIM in database
            db_result = cls.check_nim_in_database(env, nim)
            result['nim_registered'] = db_result['found']
            result['db_method'] = db_result['method']

            if db_result['found'] and db_result['student']:
                result['student_name'] = db_result['student'].name
                result['verification_status'] = 'approved'
                result['reason'] = 'nim_found_in_db'
                _logger.info(
                    '[PIPELINE] ✅ APPROVED — NIM=%s, Student=%s, Method=%s',
                    nim, db_result['student'].name, db_result['method'],
                )
            else:
                # NIM found by OCR but not in DB — try name fallback
                _logger.info('[PIPELINE] NIM=%s not in DB — trying name fallback...', nim)
                name_result = cls.check_name_in_database(env, name_detected)
                if name_result['found'] and name_result['student']:
                    result['nim'] = name_result['student'].nim
                    result['nim_registered'] = True
                    result['student_name'] = name_result['student'].name
                    result['db_method'] = name_result['method']
                    result['verification_status'] = 'approved'
                    result['reason'] = 'name_matched_in_db'
                    _logger.info(
                        '[PIPELINE] ✅ APPROVED (via name fallback) — Student=%s, NIM=%s',
                        name_result['student'].name, name_result['student'].nim,
                    )
                else:
                    result['verification_status'] = 'rejected'
                    result['reason'] = 'nim_not_in_db'
                    _logger.info('[PIPELINE] ❌ REJECTED — NIM=%s not in DB, name match also failed.', nim)

            _logger.info('=' * 60)
            _logger.info('[PIPELINE] Final: %s', {
                k: v for k, v in result.items()
                if k not in ('ocr_text', 'ocr_text_normalized')
            })
            _logger.info('=' * 60)

        except Exception as e:
            _logger.exception('[PIPELINE] EXCEPTION: %s', e)
            result['ocr_text'] = f'Error: {str(e)}'
            result['reason'] = f'exception: {str(e)}'

        return result
