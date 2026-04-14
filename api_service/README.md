---
title: Auto Clipper
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
app_port: 7860
---

# ✂️ Auto-Clip API

> **ارفع فيديو طويل — واستلم كليبس فيرال جاهزة أوتوماتيك بـ AI**
> Upload a long video — get viral-ready clips automatically with AI

[![HuggingFace Space](https://img.shields.io/badge/🤗%20HuggingFace-auto__cliper-FFD21E)](https://huggingface.co/spaces/alisaadeng/auto_cliper)
[![API Docs](https://img.shields.io/badge/Swagger-API%20Docs-85EA2D?logo=swagger)](https://huggingface.co/spaces/alisaadeng/auto_cliper)
[![Duplicate Space](https://img.shields.io/badge/🤗-Duplicate%20Space-blue)](https://huggingface.co/spaces/alisaadeng/auto_cliper?duplicate=true)

---

## 🧠 إيه هو Auto-Clip؟ / What is Auto-Clip?

**Auto-Clip** هو API بيعمل واحدة بس:

```
فيديو طويل → AI → كليبس فيرال جاهزة للنشر
```

من غير ما تعمل أي حاجة يدوي — بدون مونتاج، بدون سكريبت، بدون تعب.  
بس ارفع الفيديو، حدد الستايل، وخد الكليبس.

**Auto-Clip** does one thing:

```
Long video → AI → Viral-ready clips for posting
```

No manual editing. No scripting. No hassle.  
Just upload, pick a style, get your clips.

---

## 🚀 ابدأ في 3 خطوات / Start in 3 Steps

### الخطوة 1 — ارفع الفيديو

```bash
curl -X POST https://huggingface.co/spaces/alisaadeng/auto_cliper/auto-clip \
  -F "video=@your_video.mp4" \
  -F "style=vertical_full" \
  -F "caption_mode=word" \
  -F "caption_style=tiktok_bold"
```

### الخطوة 2 — تابع التقدم

```bash
curl https://huggingface.co/spaces/alisaadeng/auto_cliper/status/{task_id}
```

```
1–99 = شغال ⏳  |  100 = خلص ✅  |  -1 = فشل ❌
```

### الخطوة 3 — نزّل الكليبات

```bash
curl https://huggingface.co/spaces/alisaadeng/auto_cliper/download/{filename}
```

---

## 📡 الـ Endpoints / Endpoints

| Method | Endpoint | الوظيفة |
|--------|----------|---------|
| `POST` | `/auto-clip` | ارفع فيديو وابدأ المعالجة |
| `GET` | `/status/{task_id}` | تابع تقدم التاسك |
| `GET` | `/download/{filename}` | نزّل كليب معين |
| `GET` | `/files` | شوف كل الكليبس الموجودة |

---

## 🎬 الستايلات المتاحة / Available Styles

| Style | المعنى | مناسب لـ |
|-------|--------|----------|
| `cinematic` | سينمائي كلاسيك | YouTube / LinkedIn |
| `cinematic_blur` | خلفية مبلورة | YouTube Shorts |
| `vertical_full` | فيرتيكال كامل | TikTok / Reels |
| `split_vertical` | شاشتين جنب بعض | Reaction / Commentary |
| `split_horizontal` | شاشتين فوق بعض | Tutorial / Compare |

---

## 💬 الكابشن / Captions

### Mode — طريقة ظهور الكلام

| Mode | الشرح |
|------|-------|
| `sentence` | جملة كاملة في وقت واحد |
| `word` | كلمة كلمة |
| `highlight_word` | كلمة كلمة مع تمييز |
| `none` | بدون كابشن |

### Style — شكل الكابشن

| Style | المظهر |
|-------|--------|
| `classic` | كلاسيك سادة |
| `modern_glow` | توهج عصري |
| `tiktok_bold` | تيك توك عريض |
| `tiktok_neon` | نيون تيك توك |
| `youtube_clean` | يوتيوب نظيف |
| `youtube_box` | يوتيوب بوكس |

---

## ⚡ Async vs Sync — إيه الفرق؟

```
بعتّ webhook_url ✅
  └── بيشتغل في الخلفية
  └── لما يخلص بيبعتلك النتيجة على الـ webhook
  └── مناسب للفيديوهات الطويلة

ما بعتّش webhook_url ✅
  └── بيستنى ويرجعلك النتيجة في نفس الريكوست
  └── مناسب للفيديوهات القصيرة
```

---

## 🔁 Clone & Self-Host — اعمل نسختك الخاصة

> تقدر تعمل Clone للـ Space ده على HuggingFace وتشغّله على نفسك مجاناً

[![Duplicate this Space](https://huggingface.co/datasets/huggingface/badges/resolve/main/duplicate-this-space-md.svg)](https://huggingface.co/spaces/alisaadeng/auto_cliper?duplicate=true)

**الخطوات:**
1. اضغط "Duplicate this Space" فوق
2. اختار اسم للـ Space الجديد
3. اضغط Duplicate — وخلاص ✅

---

## 🔗 روابط مهمة / Links

| | |
|--|--|
| 🤗 **Live API** | [huggingface.co/spaces/ex510/auto_cliper](https://huggingface.co/spaces/alisaadeng/auto_cliper) |
| 📖 **Swagger Docs** | نفس الرابط — `/docs` |
| 💬 **Discord Community** | [discord.gg/ZsqyhvAq](https://discord.gg/ZsqyhvAq) |
| 🐙 **GitHub** | [github.com/expher510](https://github.com/expher510) |

---

*من مجتمع **alisaadeng** — بنبني مع بعض 🚀*