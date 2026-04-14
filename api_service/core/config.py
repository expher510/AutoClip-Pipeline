"""
Config — Viral Shorts Engine Configuration

Font choices based on analysis of 2M+ short-form videos (2024-2025):

SUPPORTED LANGUAGES (26 languages):
────────────────────────────────────
Arabic Script:  ar (Arabic), fa (Persian/Farsi), ur (Urdu)
CJK:            zh (Simplified), zh-tw (Traditional), ja (Japanese), ko (Korean)
Devanagari:     hi (Hindi), mr (Marathi), ne (Nepali)
Latin:          en, fr, es, de, pt, it, tr, nl, pl, id, vi, sv, ro
Cyrillic:       ru, uk (Ukrainian)
Hebrew:         he
Thai:           th

FONT DOWNLOAD FIX:
  Google Fonts returns woff2 for modern browsers — Pillow cannot load woff2.
  Solution: use an old IE User-Agent to force Google Fonts to return TTF URLs.
    Modern UA  → fonts.gstatic.com/s/cairo/xxx.woff2   ← Pillow FAILS
    Old IE UA  → fonts.gstatic.com/s/cairo/xxx.ttf     ← Pillow works ✅
"""
import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()


class Config:
    BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TEMP_DIR    = os.path.join(BASE_DIR, "temp")
    UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
    OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
    LOGS_DIR    = os.path.join(BASE_DIR, "logs")

    # ─────────────────────────────────────────────────────────────────────────
    # Font Registry — Google Fonts CSS2 API URLs
    # ─────────────────────────────────────────────────────────────────────────
    FONTS = {

        # ── Latin / Universal ──────────────────────────────────────────────────
        "Montserrat-Bold.ttf":        "https://fonts.googleapis.com/css2?family=Montserrat:wght@700&display=swap",
        "Rubik-Bold.ttf":             "https://fonts.googleapis.com/css2?family=Rubik:wght@700&display=swap",
        "Oswald-Bold.ttf":            "https://fonts.googleapis.com/css2?family=Oswald:wght@700&display=swap",
        "Roboto-Bold.ttf":            "https://fonts.googleapis.com/css2?family=Roboto:wght@700&display=swap",

        # ── Arabic Script ──────────────────────────────────────────────────────
        "Tajawal-Bold.ttf":           "https://fonts.googleapis.com/css2?family=Tajawal:wght@700&display=swap",
        "Cairo-Bold.ttf":             "https://fonts.googleapis.com/css2?family=Cairo:wght@700&display=swap",
        "Almarai-Bold.ttf":           "https://fonts.googleapis.com/css2?family=Almarai:wght@800&display=swap",
        "NotoSansArabic-Bold.ttf":    "https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@700&display=swap",

        # ── Persian ────────────────────────────────────────────────────────────
        "Vazirmatn-Bold.ttf":         "https://fonts.googleapis.com/css2?family=Vazirmatn:wght@700&display=swap",

        # ── Urdu ───────────────────────────────────────────────────────────────
        "NotoSansArabicUrdu-Bold.ttf": "https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@700&display=swap",

        # ── Hebrew ─────────────────────────────────────────────────────────────
        "FrankRuhlLibre-Bold.ttf":    "https://fonts.googleapis.com/css2?family=Frank+Ruhl+Libre:wght@700&display=swap",
        "Heebo-Bold.ttf":             "https://fonts.googleapis.com/css2?family=Heebo:wght@700&display=swap",

        # ── CJK ───────────────────────────────────────────────────────────────
        "NotoSansSC-Bold.ttf":        "https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@700&display=swap",
        "NotoSansTC-Bold.ttf":        "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@700&display=swap",
        "NotoSansJP-Bold.ttf":        "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@700&display=swap",
        "NotoSansKR-Bold.ttf":        "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@700&display=swap",

        # ── Devanagari ────────────────────────────────────────────────────────
        "NotoSansDevanagari-Bold.ttf": "https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@700&display=swap",
        "Poppins-Bold.ttf":           "https://fonts.googleapis.com/css2?family=Poppins:wght@700&display=swap",

        # ── Thai ──────────────────────────────────────────────────────────────
        "Sarabun-Bold.ttf":           "https://fonts.googleapis.com/css2?family=Sarabun:wght@700&display=swap",
        "NotoSansThai-Bold.ttf":      "https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@700&display=swap",

        # ── Universal fallback ─────────────────────────────────────────────────
        "NotoSans-Bold.ttf":          "https://fonts.googleapis.com/css2?family=Noto+Sans:wght@700&display=swap",
    }

    # ─────────────────────────────────────────────────────────────────────────
    # Language → Font
    # ─────────────────────────────────────────────────────────────────────────
    LANGUAGE_FONT_MAP = {
        "ar": "Tajawal-Bold.ttf",
        "fa": "Vazirmatn-Bold.ttf",
        "ur": "NotoSansArabic-Bold.ttf",
        "he": "Heebo-Bold.ttf",
        "zh":    "NotoSansSC-Bold.ttf",
        "zh-tw": "NotoSansTC-Bold.ttf",
        "ja":    "NotoSansJP-Bold.ttf",
        "ko":    "NotoSansKR-Bold.ttf",
        "hi": "NotoSansDevanagari-Bold.ttf",
        "mr": "NotoSansDevanagari-Bold.ttf",
        "ne": "NotoSansDevanagari-Bold.ttf",
        "th": "Sarabun-Bold.ttf",
        "ru": "Montserrat-Bold.ttf",
        "uk": "Montserrat-Bold.ttf",
        "en": "Montserrat-Bold.ttf",
        "fr": "Montserrat-Bold.ttf",
        "es": "Montserrat-Bold.ttf",
        "de": "Montserrat-Bold.ttf",
        "pt": "Montserrat-Bold.ttf",
        "it": "Montserrat-Bold.ttf",
        "tr": "Montserrat-Bold.ttf",
        "nl": "Montserrat-Bold.ttf",
        "pl": "Montserrat-Bold.ttf",
        "id": "Montserrat-Bold.ttf",
        "vi": "Roboto-Bold.ttf",
        "sv": "Montserrat-Bold.ttf",
        "ro": "Montserrat-Bold.ttf",
        "default": "NotoSans-Bold.ttf",
    }

    STYLE_FONT_MAP = {
        "classic":       "Montserrat-Bold.ttf",
        "modern_glow":   "Rubik-Bold.ttf",
        "tiktok_bold":   "Montserrat-Bold.ttf",
        "tiktok_neon":   "Montserrat-Bold.ttf",
        "youtube_clean": "Rubik-Bold.ttf",
        "youtube_box":   "Montserrat-Bold.ttf",
    }

    UNICODE_SCRIPT_RANGES = [
        ("\u0600", "\u06FF", "ar"),
        ("\u0750", "\u077F", "ar"),
        ("\u08A0", "\u08FF", "ar"),
        ("\u0590", "\u05FF", "he"),
        ("\uAC00", "\uD7AF", "ko"),
        ("\u1100", "\u11FF", "ko"),
        ("\u4E00", "\u9FFF", "zh"),
        ("\u3400", "\u4DBF", "zh"),
        ("\u3040", "\u309F", "ja"),
        ("\u30A0", "\u30FF", "ja"),
        ("\u0900", "\u097F", "hi"),
        ("\u0E00", "\u0E7F", "th"),
        ("\u0400", "\u04FF", "ru"),
        ("\u0500", "\u052F", "ru"),
    ]

    RTL_LANGUAGES = {"ar", "fa", "ur", "he"}

    DEFAULT_SIZE         = (1080, 1920)
    CHUNK_SIZE_SECONDS   = 600
    OVERLAP_SECONDS      = 60

    STYLES = [
        "cinematic",
        "cinematic_blur",
        "vertical_full",
        "split_vertical",
        "split_horizontal",
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # Directory setup
    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def setup_dirs(cls):
        for d in [cls.TEMP_DIR, cls.UPLOADS_DIR, cls.OUTPUTS_DIR, cls.LOGS_DIR]:
            os.makedirs(d, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Language detection
    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def detect_language_from_text(cls, text: str) -> str | None:
        if not text:
            return None
        for start, end, lang in cls.UNICODE_SCRIPT_RANGES:
            if any(start <= c <= end for c in text):
                return lang
        return None

    @classmethod
    def is_rtl(cls, language: str) -> bool:
        return language in cls.RTL_LANGUAGES

    @classmethod
    def get_font_for_language(cls, language: str, style_name: str = None) -> str:
        NON_LATIN = {
            "ar", "fa", "ur", "he",
            "zh", "zh-tw", "ja", "ko",
            "hi", "mr", "ne", "th",
        }
        if language in NON_LATIN:
            return cls.LANGUAGE_FONT_MAP.get(language, cls.LANGUAGE_FONT_MAP["default"])
        if style_name and style_name in cls.STYLE_FONT_MAP:
            return cls.STYLE_FONT_MAP[style_name]
        if language in cls.LANGUAGE_FONT_MAP:
            return cls.LANGUAGE_FONT_MAP[language]
        return cls.LANGUAGE_FONT_MAP["default"]

    # ─────────────────────────────────────────────────────────────────────────
    # Font URL extraction
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_urls(css_content: str, prefer_latin: bool = True) -> list:
        """
        Extracts font file URLs from a Google Fonts CSS response.
        Prefers TTF over woff2 because Pillow cannot load woff2.
        """
        # Extract all (subset_comment, url) pairs
        pattern = re.compile(
            r'/\*\s*\[?\d*\]?\s*([\w\-]+)\s*\*/[^}]*?url\(([^)]+)\)',
            re.DOTALL,
        )
        pairs = pattern.findall(css_content)

        if pairs:
            subset_map = {s.lower(): u.strip().strip("'\"") for s, u in pairs}
            if prefer_latin:
                for key in ("latin", "latin-ext"):
                    if key in subset_map:
                        return [subset_map[key]]
                return [list(subset_map.values())[-1]]
            else:
                return [list(subset_map.values())[0]]

        # Fallback: grab all raw URLs
        all_urls = re.findall(r'url\(([^)]+)\)', css_content)
        all_urls = [u.strip().strip("'\"") for u in all_urls]

        # Prefer TTF, then woff (not woff2 — Pillow can't open woff2)
        ttf   = [u for u in all_urls if u.endswith(".ttf")]
        woff  = [u for u in all_urls if u.endswith(".woff") and not u.endswith(".woff2")]
        return ttf or woff or all_urls

    # ─────────────────────────────────────────────────────────────────────────
    # Font CSS download  ← FIXED: uses TTF-forcing User-Agent
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def download_font_from_css(css_url: str, output_path: str) -> bool:
        """
        Downloads the correct font file for a given Google Fonts CSS URL.

        KEY FIX: Uses an old IE 6 User-Agent to force Google Fonts to return
        TTF URLs instead of woff2. Pillow/FreeType cannot open woff2 files.

          Modern Chrome UA → Google returns .woff2  → Pillow FAILS ❌
          Old IE 6 UA      → Google returns .ttf    → Pillow works ✅

        Two-pass strategy:
          Pass 1: Old IE UA → gets TTF (ideal for Pillow)
          Pass 2: Modern UA → gets woff2 as last resort (may fail in Pillow)
        """
        # ── User-Agent constants ──────────────────────────────────────────────
        # IE 6 on Windows XP — forces Google Fonts to return legacy TTF format
        UA_TTF = (
            "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; "
            "SV1; .NET CLR 1.1.4322)"
        )
        # Modern Chrome — returns woff2 (not ideal for Pillow, last resort)
        UA_MODERN = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        NON_LATIN_KEYWORDS = (
            "arabic", "noto", "devanagari", "sc", "jp", "kr", "tc",
            "thai", "sarabun", "heebo", "frank", "vazir", "tajawal",
            "cairo", "almarai",
        )
        filename     = os.path.basename(output_path).lower()
        is_non_latin = any(kw in filename for kw in NON_LATIN_KEYWORDS)
        prefer_latin = not is_non_latin

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        for pass_num, ua in enumerate([UA_TTF, UA_MODERN], start=1):
            ua_label = "TTF-forcing (IE6)" if pass_num == 1 else "Modern (woff2 fallback)"
            try:
                # ── Fetch CSS ─────────────────────────────────────────────────
                resp = requests.get(
                    css_url,
                    headers={"User-Agent": ua},
                    timeout=15
                )
                resp.raise_for_status()

                urls = Config.get_urls(resp.text, prefer_latin=prefer_latin)
                if not urls:
                    print(f"⚠️  Pass {pass_num} ({ua_label}): no font URLs in CSS")
                    continue

                font_url = urls[0]
                ext = os.path.splitext(font_url.split("?")[0])[-1].lower()
                print(f"⬇️  Pass {pass_num} ({ua_label}): {ext} → {font_url[:70]}…")

                # ── Download font file ────────────────────────────────────────
                font_resp = requests.get(
                    font_url,
                    headers={"User-Agent": UA_MODERN},
                    timeout=30
                )
                font_resp.raise_for_status()
                data = font_resp.content

                # ── Validate: check magic bytes ───────────────────────────────
                if len(data) < 10_000:
                    print(f"⚠️  File too small ({len(data)} B) — likely error page, skipping")
                    continue

                magic = data[:4]
                is_ttf_magic = magic in (
                    b"\x00\x01\x00\x00",   # TrueType
                    b"OTTO",               # OpenType CFF
                    b"true",               # TrueType variant
                    b"wOFF",               # WOFF (Pillow ≥ 9.2 can open)
                    b"wOF2",               # WOFF2 (Pillow may fail)
                )

                if not is_ttf_magic:
                    print(
                        f"⚠️  Pass {pass_num}: unexpected magic bytes {magic.hex()} "
                        f"(probably HTML error page) — skipping"
                    )
                    continue

                if magic == b"wOF2":
                    print(
                        f"⚠️  Pass {pass_num}: received WOFF2 — "
                        f"Pillow may not be able to open this. "
                        f"Consider installing: sudo apt-get install fonts-noto-core"
                    )

                with open(output_path, "wb") as f:
                    f.write(data)

                print(f"✅ Font saved ({len(data):,} B, {ext}): {output_path}")
                return True

            except requests.RequestException as e:
                print(f"❌ Pass {pass_num} network error: {e}")
            except Exception as e:
                print(f"❌ Pass {pass_num} unexpected error: {e}")

        # ── Both passes failed ────────────────────────────────────────────────
        print(
            f"❌ All download attempts failed for {os.path.basename(output_path)}.\n"
            f"   Fix on Ubuntu/Debian:\n"
            f"     sudo apt-get install -y fonts-noto-core fonts-arabeyes\n"
            f"   Or copy a TTF manually to: {output_path}"
        )
        return False