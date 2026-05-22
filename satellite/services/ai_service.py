"""Groq LLM — fermer tushunadigan oddiy tilda agronomik tahlil."""
import json
import re

from groq import Groq
from django.conf import settings


# ── Raqamlarni oddiy o'zbek tiliga tarjima ────────────────────────────────────

def _ndvi_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 0.7:  return f"{v:.2f} — dala to'liq yashil, o'simliklar juda sog'lom"
    if v >= 0.5:  return f"{v:.2f} — dala yaxshi holda, o'simliklar normal o'sayapti"
    if v >= 0.3:  return f"{v:.2f} — o'simliklar o'rtacha holda, e'tibor kerak"
    if v >= 0.1:  return f"{v:.2f} — o'simliklar siyrak yoki zaif, muammo bor"
    return f"{v:.2f} — dala deyarli bo'sh yoki quruq tuproq"


def _ndwi_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 0.3:  return f"{v:.2f} — tuproqda suv yetarli, yaxshi namlangan"
    if v >= 0.0:  return f"{v:.2f} — tuproqda suv o'rtacha, kuzatib boring"
    return f"{v:.2f} — tuproq quruq, sug'orish kerak"


def _drought_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 1.5:  return f"{v:.1f} — tuproqda namlik ortiqcha, suv toshqini xavfi bor"
    if v >= 0.5:  return f"{v:.1f} — namlik yetarli, hozircha sug'orish shart emas"
    if v >= -0.5: return f"{v:.1f} — namlik o'rtacha chegarada, kuzatib boring"
    if v >= -1.5: return f"{v:.1f} — tuproq quruqlik tomonga ketmoqda, tez sug'oring"
    return f"{v:.1f} — jiddiy quruqlik, zudlik bilan sug'orish shart"


def _moisture_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 60:   return f"{v:.0f}% — tuproq juda nam, suv toshib ketishidan ehtiyot bo'ling"
    if v >= 40:   return f"{v:.0f}% — tuproq namligi ideal, sug'orish shart emas"
    if v >= 25:   return f"{v:.0f}% — tuproq biroz quruq, 2-3 kunda sug'oring"
    if v >= 10:   return f"{v:.0f}% — tuproq quruq, bugun sug'orish kerak"
    return f"{v:.0f}% — tuproq juda quruq, zudlik bilan ko'p sug'oring"


def _temp_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 38:   return f"{v:.0f}°C — juda issiq, ekinlar kuyib ketishi mumkin"
    if v >= 30:   return f"{v:.0f}°C — issiq, issiqlikka chidamli ekinlar ekish kerak"
    if v >= 20:   return f"{v:.0f}°C — harorat qulay, ko'p ekinlar uchun ideal"
    if v >= 10:   return f"{v:.0f}°C — salqin, issiqlikni yaxshi ko'rmaydigan ekinlarga mos"
    return f"{v:.0f}°C — sovuq, ekinlar muzlashi mumkin, ehtiyot bo'ling"


def _precip_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 700:  return f"{v:.0f} mm — yillik yomg'ir ko'p, sug'orishga kam ehtiyoj"
    if v >= 400:  return f"{v:.0f} mm — yillik yomg'ir o'rtacha, qo'shimcha sug'orish kerak"
    if v >= 200:  return f"{v:.0f} mm — yomg'ir kam, muntazam sug'orish shart"
    return f"{v:.0f} mm — juda quruq iqlim, intensiv sug'orish tizimi kerak"


def _ph_label(v):
    if v is None: return "aniqlanmadi"
    if v >= 8.5:  return f"{v:.1f} — tuproq haddan tashqari ishqoriy, ko'p ekin o'smaydi"
    if v >= 7.5:  return f"{v:.1f} — tuproq biroz ishqoriy, yerni isloh qilish tavsiya etiladi"
    if v >= 6.0:  return f"{v:.1f} — tuproq neytral, ko'pchilik ekinlar uchun ideal"
    if v >= 5.0:  return f"{v:.1f} — tuproq biroz kislotali, ohak solish kerak"
    return f"{v:.1f} — tuproq juda kislotali, ekinlar yaxshi o'smaydi"


def _nitrogen_label(v):
    if v is None: return "aniqlanmadi"
    # SoilGrids nitrogen: cg/kg → mg/kg uchun /10 bo'linadi
    mg = v / 10 if v > 50 else v
    if mg >= 200: return f"{v:.0f} — azot juda ko'p, qo'shimcha o'g'it shart emas"
    if mg >= 100: return f"{v:.0f} — azot yetarli, o'g'itlash o'rtacha"
    if mg >= 50:  return f"{v:.0f} — azot kam, azotli o'g'it (karbamid) solish kerak"
    return f"{v:.0f} — azot juda kam, tezkor azotli o'g'it bering"


def _clay_label(v):
    if v is None: return "aniqlanmadi"
    # SoilGrids clay: g/kg → foizga o'tkazish
    pct = v / 10 if v > 10 else v
    if pct >= 40: return f"{pct:.0f}% — tuproq og'ir loysumon, suv yomon o'tadi, shudgor kerak"
    if pct >= 25: return f"{pct:.0f}% — tuproq o'rtacha loysimon, ko'p ekin uchun yaxshi"
    return f"{pct:.0f}% — tuproq yengil qumloq, suv tez o'tib ketadi, ko'p sug'orish kerak"


def _build_plain_context(ctx: dict) -> str:
    """Context raqamlarini oddiy o'zbek tiliga o'tkazadi."""
    soil = ctx.get("tuproq", {}) or {}
    kimyo = ctx.get("tuproq_kimyosi", {}) or {}
    loc = ctx.get("joylashuv", {}) or {}

    lines = []

    # Joylashuv
    if loc.get("maydon_ha"):
        lines.append(f"Dala maydoni: {loc['maydon_ha']} gektar ({loc['maydon_ha']*100:.0f} sotix)")

    # NDVI
    lines.append(f"O'simlik holati (NDVI): {_ndvi_label(ctx.get('joriy_ndvi'))}")
    if ctx.get("joriy_evi") is not None:
        evi = ctx["joriy_evi"]
        lines.append(f"Biomassa (EVI): {evi:.2f} — {'yaxshi' if evi >= 0.3 else 'past'} biomassa")
    lines.append(f"Suv indeksi (NDWI): {_ndwi_label(ctx.get('joriy_ndwi'))}")
    lines.append(f"Qurg'oqchilik darajasi: {_drought_label(ctx.get('qurgochlik_di'))}")

    ndvi_chg = ctx.get("ndvi_ozgarishi")
    if ndvi_chg is not None:
        yoq = "yaxshilangan" if ndvi_chg > 0.05 else ("yomonlashgan" if ndvi_chg < -0.05 else "o'zgarmagan")
        lines.append(f"Yil davomida o'simlik holati: {ndvi_chg:+.3f} — {yoq}")

    # Ob-havo
    lines.append(f"O'rtacha harorat: {_temp_label(ctx.get('ortacha_harorat'))}")
    lines.append(f"Yillik yomg'ir: {_precip_label(ctx.get('yillik_yogin_mm'))}")
    if ctx.get("ortacha_shamol") is not None:
        lines.append(f"Shamol tezligi: {ctx['ortacha_shamol']:.1f} m/s")
    if ctx.get("ortacha_namlik") is not None:
        lines.append(f"Havo namligi: {ctx['ortacha_namlik']:.0f}%")

    # Tuproq namligi
    if soil.get("moisture_0_1cm") is not None:
        lines.append(f"Yuza tuproq namligi (0-1 sm): {_moisture_label(soil['moisture_0_1cm'])}")
    if soil.get("moisture_3_9cm") is not None:
        lines.append(f"Chuqur tuproq namligi (3-9 sm): {_moisture_label(soil['moisture_3_9cm'])}")
    if soil.get("surface_temp") is not None:
        lines.append(f"Tuproq yuzasi harorati: {soil['surface_temp']:.0f}°C")

    # Tuproq kimyosi (yangi to'liq format + eski format qo'llab-quvvatlash)
    if kimyo:
        # pH
        if kimyo.get("ph_label"):
            lines.append(f"Tuproq kislotaligi (pH {kimyo.get('ph', '')}): {kimyo['ph_label']}")
        elif kimyo.get("ph_h2o") is not None:
            lines.append(f"Tuproq kislotaligi (pH): {_ph_label(kimyo['ph_h2o'])}")

        # Tarkib
        if kimyo.get("texture"):
            lines.append(f"Tuproq tarkibi: {kimyo['texture']}")
            if kimyo.get("clay_pct") is not None:
                lines.append(f"  Loy: {kimyo['clay_pct']}%, Qum: {kimyo.get('sand_pct',0)}%, Lyoss: {kimyo.get('silt_pct',0)}%")
        elif kimyo.get("clay") is not None:
            lines.append(f"Tuproq tarkibi (loy): {_clay_label(kimyo['clay'])}")

        # Azot
        if kimyo.get("nitrogen_label"):
            lines.append(f"Azot (N): {kimyo['nitrogen_label']}")
        elif kimyo.get("nitrogen") is not None:
            lines.append(f"Azot miqdori: {_nitrogen_label(kimyo['nitrogen'])}")

        # Organik uglerod
        if kimyo.get("soc_label"):
            lines.append(f"Organik uglerod ({kimyo.get('soc_g_kg','')} g/kg): {kimyo['soc_label']}")
        elif kimyo.get("soc") is not None:
            soc_v = kimyo["soc"]
            lines.append(f"Organik modda: {soc_v:.1f} g/kg — {'yaxshi' if soc_v >= 10 else 'kam, go\'ng solish kerak'}")

        # CEC — oziq ushlab turish
        if kimyo.get("cec_label"):
            lines.append(f"Oziq ushlab turish (CEC): {kimyo['cec_label']}")

        # NASA POWER namligi
        if kimyo.get("gwet_root_label") and kimyo.get("gwet_root") is not None:
            lines.append(f"Ko'p yillik o'rtacha ildiz namligi: {kimyo['gwet_root_label']}")

    # Suv manbalari
    water = ctx.get("suv_manbalari") or {}
    if water.get("total_found"):
        lines.append(
            f"Atrofdagi suv manbalari ({water['total_found']} ta topildi): "
            f"{water.get('plain_text', '')}"
        )
        irr = water.get("irrigation_source")
        if irr:
            lines.append(
                f"Sug'orish uchun eng qulay manba: {irr['name']} ({irr['type_uz']}) "
                f"— {irr['distance_text']} {irr['direction']} tomonda"
            )
    else:
        lines.append("Atrofda 10 km ichida suv manbai topilmadi")

    return "\n".join(f"• {l}" for l in lines)


# ── Asosiy tahlil funksiyasi ───────────────────────────────────────────────────

def analyze(context: dict) -> dict:
    plain = _build_plain_context(context)
    area_ha = (context.get("joylashuv") or {}).get("maydon_ha") or 1.0

    prompt = f"""Sen O'zbekistondagi tajribali agronom va fermer maslahatchisan.
Quyidagi dala haqidagi barcha ma'lumotlarni tahlil qilib, fermerga batafsil va eng mos bo'lgan 3 ta ekinni tavsiya qil.

MUHIM QOIDALAR:
1. Ilmiy atamasiz — oddiy fermer tushunadigan tilda yoz
2. Har bir raqamni tushuntir: "0.62 NDVI" emas — "dala yaxshi yashil" de
3. Aniq son ayt: "ko'p hosil" emas — "1 gektardan 40-50 tonna" de
4. O'zbekiston bozori real narxlaridan foydalan (2024-2025 yil narxlari)
5. Faqat ushbu yer uchun mos ekinlarni tavsiya qil — hamma joyga bir xil javob berma! 
   - Agar hududda suv juda kam bo'lsa va iqlim quruq bo'lsa, suvsizlikka chidamli ekinlarni (Arpaboya, Beda, Maxsar, No'xat va b.) tavsiya qil.
   - Agar suv yetarli, iqlim qulay va tuproq unumdor bo'lsa, sabzavotlar (Pomidor, Bodring, Piyoz, Kartoshka) yoki G'o'za va G'allani tavsiya qil.
   - Agar tuproq kislotali yoki sho'rroq bo'lsa, sho'rga va kislotaga chidamli ekinlarni tanla.
6. Suv manbai bo'lsa — sug'orish rejasini unga mos tuzib ber.
7. Shunchaki namuna sifatida berilgan ekin nomlarini ko'chirmasdan, ushbu dalaning haqiqiy tuproq kimyosi, azot, loy va ob-havo parametrlariga eng mos keladigan eng yaxshi mahsulotlarni tanla!
8. ENG MUHIMI: Tavsiyalaringda sun'iy og'ish (bias) bo'lmasin. Faqatgina "Pomidor" yoki sabzavotlarni tanlashdan qoch! Dalaning haqiqiy tuproq kimyosi (pH, azot, loy foizi) va suv darajasini juda qattiq inobatga olgan holda, unga mos va foydali bo'lgan boshqa ekinlarni ham tanla.
   - Agar suv kam yoki yo'q bo'lsa, sabzavotlarni (pomidor, bodring) aslo tavsiya qilma, o'rniga Beda, Arpa, Maxsar kabi qurg'oqchilikka chidamlilarni tavsiya qil.
   - Agar azot miqdori juda kam bo'lsa, tuproqni qayta tiklovchi dukkaklilar (Beda, Mosh, No'xat)ni birinchi o'ringa qo'yib tavsiya qil.
   - Agar tuproq kislotali bo'lsa (pH < 6.0), kartoshkani afzal bil.
   - Agar tuproq og'ir loy bo'lsa, ildizmevalilardan qochib, G'o'za yoki Bug'doy kabi ekinlarni tavsiya qil.

Dala tahlil ma'lumotlari:
{plain}

Dala maydoni: {area_ha} gektar

Faqat JSON qaytaring (boshqa hech narsa yozma, izoh ham yozma):
{{
  "yer_tahlili": {{
    "umumiy_baho": "Bu yer haqida 3-4 jumlada to'liq baho. Nima yaxshi, nima muammo, asosiy xususiyat.",
    "tuproq_sifati": "Tuproq qanday — qulay yoki muammo bor? Nima qilish kerak?",
    "suv_holati": "Tuproq namligi va atrofdagi suv manbalari. Sug'orish qanday yo'l bilan qilinadi?",
    "iqlim_sharoit": "Harorat, yomg'ir, shamol — ekinlar uchun qulaymi yoki qiyinmi?",
    "osimlik_holati": "Yaxshi | O'rtacha | Yomon"
  }},

  "ekin_tavsiyalari": [
    {{
      "ekin": "Birinchi mos ekin nomi (Dalaga agronomik nuqtai nazardan eng mos keladigan, kutilayotgan sof foydasi yuqori bo'lgan mahsulot turi)",
      "nima_uchun_mos": "Nima uchun ushbu ekin bu yerning tuprog'i, namligi va iqlimiga aynan mos kelishi tushuntirilishi",
      "hosil_tonnada": "Kutilayotgan o'rtacha hosildorlik tonnada (masalan: 3-4 tonna/gektar, 40-50 tonna/gektar)",
      "narx_som": "Bozordagi o'rtacha ulgurji narxi (so'm/kg)",
      "daromad_taxmin": "Taxminiy umumiy daromad so'mda",
      "xarajat_taxmin": "Xarajatlar tafsiloti (urug'lik, dori, o'g'it, texnika uchun taxminiy xarajat)",
      "sof_foyda": "Sof foyda so'mda",
      "ekish_vaqti": "Ekish muddatlari (masalan: mart-aprel)",
      "yig'im_vaqti": "Hosil yig'ish oylari (masalan: avgust-sentyabr)",
      "asosiy_xavf": "Ushbu ekindagi eng katta xavf va unga qarshi ko'riladigan chora (aniq dori yoki agrotexnik usul)"
    }},
    {{
      "ekin": "Ikkinchi mos ekin nomi (Muqobil va foydali boshqa ekin turi)",
      "nima_uchun_mos": "...",
      "hosil_tonnada": "...",
      "narx_som": "...",
      "daromad_taxmin": "...",
      "xarajat_taxmin": "...",
      "sof_foyda": "...",
      "ekish_vaqti": "...",
      "yig'im_vaqti": "...",
      "asosiy_xavf": "..."
    }},
    {{
      "ekin": "Uchinchi mos ekin nomi (Yana bir muqobil yoki tuproq unumdorligini oshiruvchi ekin turi)",
      "nima_uchun_mos": "...",
      "hosil_tonnada": "...",
      "narx_som": "...",
      "daromad_taxmin": "...",
      "xarajat_taxmin": "...",
      "sof_foyda": "...",
      "ekish_vaqti": "...",
      "yig'im_vaqti": "...",
      "asosiy_xavf": "..."
    }}
  ],

  "eng_foydali_ekin": "Tavsiya qilingan uchta ekin ichidan qaysi biri ushbu dalaga eng ko'p foyda va yuqori daromad keltiradi? 2 jumlada agronomik sababi bilan tushuntiring.",

  "sugorish_rejasi": {{
    "manba": "Suv qayerdan olinadi (quduq, kanal, ariq, nasos)",
    "chastota": "Necha kunda bir sug'orish kerak va necha soat",
    "usul": "Sug'orish usuli (ariqdan oqizish, tomchilatib sug'orish, yomg'irlatish)"
  }},

  "ogit_rejasi": [
    "1. [O'g'it nomi], [qachon], [qancha] — [nima uchun]",
    "2. ...",
    "3. ..."
  ],

  "bugun_nima_qilish": [
    "Birinchi — [aniq harakat va sababi]",
    "Ikkinchi — [aniq harakat va sababi]",
    "Uchinchi — [aniq harakat va sababi]"
  ],

  "xavflar": [
    "Xavf: [nima bo'lishi mumkin] — Chora: [qanday chora ko'rish kerak]",
    "Xavf: [...]  — Chora: [...]"
  ],

  "yillik_reja": {{
    "yanvar_fevral": "Ushbu oylardagi agrotexnik ishlar",
    "mart_aprel": "Ushbu oylardagi agrotexnik ishlar",
    "may_iyun": "Ushbu oylardagi agrotexnik ishlar",
    "iyul_avgust": "Ushbu oylardagi agrotexnik ishlar",
    "sentabr_oktabr": "Ushbu oylardagi agrotexnik ishlar",
    "noyabr_dekabr": "Ushbu oylardagi agrotexnik ishlar"
  }},

  "xulosa": "Fermer uchun 4-5 jumlada yakuniy va amaliy tavsiyalar."
}}"""

    try:
        api_key = getattr(settings, "GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY topilmadi")
            
        client = Groq(api_key=api_key)
        
        # Groq orqali tahlilni olish
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=4000,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = completion.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|```", "", raw).strip()
        
        result = json.loads(raw)
        
    except Exception as exc:
        print(f"Groq analyze xatosi, zaxira ishlatiladi: {exc}")
        # Groq ishlamasa, dalaning haqiqiy ko'rsatkichlariga ko'ra aniq qoidalarga asoslangan zaxira tahlil yaratiladi
        result = _get_fallback_analysis(context)

    # Orqaga moslik — eski frontend maydonlarini saqlaymiz
    if "yer_tahlili" in result:
        t = result["yer_tahlili"]
        result.setdefault("umumiy_holat", t.get("umumiy_baho", ""))
        result.setdefault("osimlik_holati", t.get("osimlik_holati", ""))
        result.setdefault("tuproq_izoh",   t.get("tuproq_sifati", ""))
        result.setdefault("suv_izoh",      t.get("suv_holati", ""))
        result.setdefault("ob_havo_izoh",  t.get("iqlim_sharoit", ""))
    if "ekin_tavsiyalari" in result:
        result.setdefault(
            "tavsiya_ekinlar",
            [f"{e['ekin']} — {e.get('nima_uchun_mos','')}" for e in result["ekin_tavsiyalari"]]
        )
    if "bugun_nima_qilish" in result:
        result.setdefault("ustuvor_harakatlar", result["bugun_nima_qilish"])
    if "xavflar" in result:
        result.setdefault("ehtiyot_bolish", result["xavflar"])

    return result


def _get_fallback_analysis(context: dict) -> dict:
    """Tizim oflayn bo'lganda dalaning haqiqiy ma'lumotlariga qarab tahlil va ekin tavsiya etuvchi qoidali mexanizm"""
    soil_props = context.get("tuproq_kimyosi", {}) or {}
    soil = context.get("tuproq", {}) or {}
    
    ph = soil_props.get("ph_h2o", 7.0)
    nitrogen = soil_props.get("nitrogen", 100)
    clay = soil_props.get("clay", 250)
    temp = context.get("ortacha_harorat", 22.0)
    precip = context.get("yillik_yogin_mm", 300)
    ndwi = context.get("joriy_ndwi", 0.0)
    area_ha = (context.get("joylashuv") or {}).get("maydon_ha") or 1.0
    
    water = context.get("suv_manbalari", {}) or {}
    has_water = water.get("total_found", 0) > 0 or precip > 400 or (ndwi is not None and ndwi >= 0.0)

    # Loy foizini aniqlash (g/kg yoki foiz)
    clay_pct = clay / 10.0 if clay > 100 else clay
    
    # Ekinlar agronomik ma'lumotlar bazasi
    crops_db = {
        "Pomidor": {
            "name_uz": "Pomidor (Tomato)",
            "requires_water": True,
            "pref_temp_range": (20, 32),
            "pref_ph_range": (6.0, 7.2),
            "max_clay": 35,
            "min_nitrogen": 70,
            "nima_uchun_mos": "Suv yetarli, iqlim issiq va tuproq kimyoviy jihatdan pomidor uchun juda qulay.",
            "yield_per_ha": 45.0,
            "price_per_kg": 3500,
            "cost_per_ha": 35000000,
            "ekish_vaqti": "Aprel-may",
            "yig'im_vaqti": "Iyul-sentyabr",
            "risk": "Fitoftora kasalligi",
            "risk_chora": "Rido-mil Gold yoki mis preparatlari bilan 10-12 kunda ishlov berish"
        },
        "Kartoshka": {
            "name_uz": "Kartoshka (Potato)",
            "requires_water": True,
            "pref_temp_range": (14, 23),
            "pref_ph_range": (5.2, 6.8),
            "max_clay": 25,
            "min_nitrogen": 60,
            "nima_uchun_mos": "Salqin harorat va biroz kislotali tuproq kartoshka tugunlari yaxshi rivojlanishi uchun mos.",
            "yield_per_ha": 35.0,
            "price_per_kg": 4000,
            "cost_per_ha": 28000000,
            "ekish_vaqti": "Mart-aprel (bahorgi) yoki iyul (kechki)",
            "yig'im_vaqti": "Iyul-avgust yoki oktyabr",
            "risk": "Kolorado qo'ng'izi",
            "risk_chora": "Imidakloprid asosidagi insektitsidlardan foydalanish"
        },
        "Piyoz": {
            "name_uz": "Piyoz (Onion)",
            "requires_water": True,
            "pref_temp_range": (15, 26),
            "pref_ph_range": (6.0, 7.5),
            "max_clay": 30,
            "min_nitrogen": 50,
            "nima_uchun_mos": "Tuproq tarkibi yengil va pH darajasi neytralligi piyoz yetishtirish uchun qulay sharoit yaratadi.",
            "yield_per_ha": 50.0,
            "price_per_kg": 2500,
            "cost_per_ha": 22000000,
            "ekish_vaqti": "Avgust-sentyabr (to'qsonbosti) yoki mart",
            "yig'im_vaqti": "Iyun-avgust",
            "risk": "Piyoz pashshasi",
            "risk_chora": "Karbofos sepish va tuproq namligini me'yorda saqlash"
        },
        "Bodring": {
            "name_uz": "Bodring (Cucumber)",
            "requires_water": True,
            "pref_temp_range": (22, 32),
            "pref_ph_range": (6.0, 7.0),
            "max_clay": 25,
            "min_nitrogen": 80,
            "nima_uchun_mos": "Suv yetarli, harorat issiq va tuproq yumshoq bo'lgani sababli bodring tez va sifatli pishadi.",
            "yield_per_ha": 30.0,
            "price_per_kg": 3000,
            "cost_per_ha": 20000000,
            "ekish_vaqti": "Aprel-may",
            "yig'im_vaqti": "Iyun-avgust",
            "risk": "Un-shudring (bakterial kasallik)",
            "risk_chora": "Fitosporin yoki mis kuporosi bilan profilaktika"
        },
        "G'o'za": {
            "name_uz": "G'o'za (Cotton)",
            "requires_water": True,
            "pref_temp_range": (23, 36),
            "pref_ph_range": (6.5, 8.0),
            "max_clay": 50,
            "min_nitrogen": 80,
            "nima_uchun_mos": "Issiq iqlim, chuqur loyli/qumoq tuproq va sug'orish manbai paxta yetishtirish uchun juda mos.",
            "yield_per_ha": 3.8,
            "price_per_kg": 9000,
            "cost_per_ha": 12000000,
            "ekish_vaqti": "Aprel",
            "yig'im_vaqti": "Sentyabr-oktyabr",
            "risk": "Ko'sak qurti va shira",
            "risk_chora": "Trixogramma yuborish yoki Xlorantraniliprol sepish"
        },
        "Kuzgi Bug'doy": {
            "name_uz": "Kuzgi Bug'doy (Winter Wheat)",
            "requires_water": True,
            "pref_temp_range": (5, 22),
            "pref_ph_range": (6.0, 7.8),
            "max_clay": 45,
            "min_nitrogen": 50,
            "nima_uchun_mos": "Salqin sharoit va og'ir tuproq g'alla o'sishi va mo'l hosil yetilishi uchun ajoyib imkoniyatdir.",
            "yield_per_ha": 6.0,
            "price_per_kg": 2800,
            "cost_per_ha": 7000000,
            "ekish_vaqti": "Sentyabr-oktyabr",
            "yig'im_vaqti": "Iyun-iyul",
            "risk": "Sariq zang kasalligi",
            "risk_chora": "Gullashdan oldin tebukonazol fungitsidini qo'llash"
        },
        "Beda": {
            "name_uz": "Beda (Alfalfa)",
            "requires_water": False,
            "pref_temp_range": (10, 35),
            "pref_ph_range": (6.5, 8.2),
            "max_clay": 40,
            "min_nitrogen": 0,
            "nima_uchun_mos": "Suvsizlikka juda chidamli va tuproqda tabiiy azot miqdorini oshirib unumdorlikni oshiradi.",
            "yield_per_ha": 11.0,
            "price_per_kg": 1800,
            "cost_per_ha": 4000000,
            "ekish_vaqti": "Mart yoki avgust-sentyabr",
            "yig'im_vaqti": "May-oktyabr (yiliga 4-5 o'rim)",
            "risk": "Beda bargxo'ri (fitonomus)",
            "risk_chora": "Erta bahorda Detsis yoki boshqa tegishli insektitsid purkash"
        },
        "Arpaboya": {
            "name_uz": "Arpaboya (Barley)",
            "requires_water": False,
            "pref_temp_range": (8, 25),
            "pref_ph_range": (6.0, 8.5),
            "max_clay": 40,
            "min_nitrogen": 40,
            "nima_uchun_mos": "Qurg'oqchilik, sho'rlanish va kislotali bo'lmagan qattiq yerlarda ham kam suv bilan yaxshi hosil beradi.",
            "yield_per_ha": 3.0,
            "price_per_kg": 2600,
            "cost_per_ha": 4500000,
            "ekish_vaqti": "Oktyabr-noyabr yoki fevral-mart",
            "yig'im_vaqti": "May-iyun",
            "risk": "Qorakuya kasalligi",
            "risk_chora": "Ekishdan oldin urug'larni tizimli dorilar bilan tozalash"
        },
        "No'xat": {
            "name_uz": "No'xat (Chickpea)",
            "requires_water": False,
            "pref_temp_range": (16, 28),
            "pref_ph_range": (6.0, 8.0),
            "max_clay": 30,
            "min_nitrogen": 0,
            "nima_uchun_mos": "Kam suv talab qiladi va o'z ildizida tuganak bakteriyalari yordamida azot hosil qilib yerni boyitadi.",
            "yield_per_ha": 1.8,
            "price_per_kg": 8000,
            "cost_per_ha": 5500000,
            "ekish_vaqti": "Fevral-mart",
            "yig'im_vaqti": "Iyun-iyul",
            "risk": "Askozitoz zamburug'i",
            "risk_chora": "Mis preparatlari bilan ishlov berish va navlarni navbatlash"
        },
        "Mosh": {
            "name_uz": "Mosh (Mung bean)",
            "requires_water": False,
            "pref_temp_range": (22, 34),
            "pref_ph_range": (6.0, 7.8),
            "max_clay": 30,
            "min_nitrogen": 0,
            "nima_uchun_mos": "Issiq iqlim, kam suv sharoitida qisqa vaqtda yetiladi va azot darajasi kam tuproqni tiklaydi.",
            "yield_per_ha": 1.7,
            "price_per_kg": 9000,
            "cost_per_ha": 5000000,
            "ekish_vaqti": "Iyun-iyul (g'alladan keyin)",
            "yig'im_vaqti": "Sentyabr",
            "risk": "O'rgimchakkana va shira",
            "risk_chora": "Akkaritsid yoki insektitsidlar qo'llash"
        }
    }

    # Agronomik moslik ballini hisoblash algoritmi
    scores = {}
    for crop_name, c in crops_db.items():
        score = 100
        
        # 1. Suv yetarliligi
        if c["requires_water"] and not has_water:
            score -= 150
            
        # 2. Harorat optimal diapazoni
        min_t, max_t = c["pref_temp_range"]
        if temp < min_t:
            score -= abs(min_t - temp) * 10
        elif temp > max_t:
            score -= abs(temp - max_t) * 10
        else:
            score += 20
            
        # 3. Tuproq kislotaligi (pH)
        min_ph, max_ph = c["pref_ph_range"]
        if ph < min_ph:
            score -= abs(min_ph - ph) * 30
        elif ph > max_ph:
            score -= abs(ph - max_ph) * 30
        else:
            score += 20
            
        # 4. Loy miqdori (og'irligi)
        if clay_pct > c["max_clay"]:
            score -= (clay_pct - c["max_clay"]) * 5
            
        # 5. Azot miqdori va dukkakli ekinlar bonusi
        if nitrogen < 50:
            if c["min_nitrogen"] == 0:
                score += 40
            else:
                score -= 20
        elif nitrogen > 150 and c["min_nitrogen"] == 0:
            score -= 10
            
        scores[crop_name] = score

    # Ballar bo'yicha saralash
    sorted_crops = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_3 = sorted_crops[:3]

    # Javob massivini shakllantirish
    recommendations = []
    for crop_name, score in top_3:
        c = crops_db[crop_name]
        y = c["yield_per_ha"]
        p = c["price_per_kg"]
        cost = c["cost_per_ha"]
        
        tot_yield = round(y * area_ha, 1)
        revenue = int(tot_yield * 1000 * p)
        total_cost = int(cost * area_ha)
        net_profit = revenue - total_cost
        
        narx_str = f"{p:,}".replace(",", " ")
        daromad_str = f"{revenue:,}".replace(",", " ")
        xarajat_str = f"Urug'lik, o'g'it, dori, texnika va ish kuchi uchun taxminiy xarajat: {total_cost:,} so'm".replace(",", " ")
        foyda_str = f"{net_profit:,}".replace(",", " ")
        
        rec = {
            "ekin": c["name_uz"],
            "nima_uchun_mos": c["nima_uchun_mos"] + f" (Agronomik tahlil moslik reytingi: {score:.0f}/100)",
            "hosil_tonnada": f"{tot_yield} tonna ({y} tn/ga)",
            "narx_som": f"{narx_str} so'm/kg",
            "daromad_taxmin": f"{daromad_str} so'm",
            "xarajat_taxmin": xarajat_str,
            "sof_foyda": f"{foyda_str} so'm",
            "ekish_vaqti": c["ekish_vaqti"],
            "yig'im_vaqti": c["yig'im_vaqti"],
            "asosiy_xavf": f"{c['risk']} — Chora: {c['risk_chora']}"
        }
        recommendations.append(rec)

    best_crop_name = top_3[0][0]
    best_c = crops_db[best_crop_name]
    best_crop = f"{best_c['name_uz']}, chunki ushbu hududning hozirgi agrotexnik holatiga (pH, azot, loy miqdori va suv manbalari) eng yuqori darajada mos keladi va yuqori daromad salohiyatiga ega."

    # Dinamik sug'orish rejasi
    if not has_water:
        sugorish = {
            "manba": "Atrofda yaqin suv manbai topilmadi. Yomg'ir suvi yoki chuqur artezian qudug'i talab etiladi.",
            "chastota": "Suvsizlikka chidamli ekin bo'lgani sababli, ekin vegetatsiya davrida 2-3 marta sug'orish yetarli.",
            "usul": "Arteziandan tomchilatib sug'orish yoki subartikal oqizish."
        }
    else:
        sugorish = {
            "manba": water.get("plain_text", "Yaqin atrofda joylashgan suv manbasi (ariq, kanal yoki daryo)."),
            "chastota": "Ekin turiga va havo haroratiga qarab har 7-10 kunda bir marta, 4-6 soat davomida.",
            "usul": "Zamonamiy tomchilatib sug'orish tizimi yoki egatlardan oqizish."
        }

    # Dinamik o'g'it rejasi
    ogit_rejasi = []
    if nitrogen < 50:
        ogit_rejasi.append("1. Karbamid (azotli o'g'it), erta bahorda va ekin bo'yi ko'tarilganda, 150-200 kg/ga — Tuproqdagi azot yetishmovchiligini qoplash va vegetativ o'sishni jadallashtirish uchun.")
    else:
        ogit_rejasi.append("1. Chirigan go'ng va organik o'g'itlar, kuzgi shudgorda, 20-30 tonna/ga — Tuproq unumdorligini va mikroflorasini doimiy saqlab turish uchun.")
        
    if ph < 6.0:
        ogit_rejasi.append("2. Ohak yoki bo'r (kislota pasaytiruvchilar), shudgorlash vaqtida, 300-500 kg/ga — Tuproqning yuqori kislotaliligini neytrallash va ekin ildizlarini himoya qilish uchun.")
    elif ph > 7.8:
        ogit_rejasi.append("2. Gips yoki nordon o'g'itlar (sulfatlar), kuzda yoki erta bahorda, 200-300 kg/ga — Sho'rlanish va ishqoriylikni kamaytirish, tuproq strukturasini yaxshilash uchun.")
    else:
        ogit_rejasi.append("2. Superfosfat (fosforli o'g'it), ekish oldidan yer tayyorlashda, 150-250 kg/ga — Ildiz tizimining mustahkam rivojlanishi va gullash jarayonini yaxshilash uchun.")
        
    ogit_rejasi.append("3. Kaliy sulfat (kaliyli o'g'it), hosil tugish va pishish arafasida, 100-150 kg/ga — Mevalarning yirikligi, mazasi, sifati va saqlanish muddatini oshirish uchun.")

    # Dinamik bugungi ustuvor vazifalar
    bugun_nima_qilish = []
    if nitrogen < 50:
        bugun_nima_qilish.append("Birinchi — Tuproqdagi keskin azot tanqisligini to'ldirish uchun organik o'g'it (go'ng) yoki karbamid sotib olishni rejalashtiring.")
    else:
        bugun_nima_qilish.append("Birinchi — Mavjud yer maydonini begona o'tlardan tozalab, shudgorlash va tekislash ishlarini boshlang.")
        
    if not has_water:
        bugun_nima_qilish.append("Ikkinchi — Dala atrofida suv yetishmovchiligi sababli chuqur quduq (artezian) qazish imkoniyatlarini o'rganing yoki suvsiz ekinlarni rejalashtiring.")
    else:
        bugun_nima_qilish.append("Ikkinchi — Atrofdagi suv manbalaridan samarali foydalanish uchun egatlar yoki tomchilatib sug'orish shlanglarini torting.")
        
    bugun_nima_qilish.append("Uchinchi — Tanlangan ekinlar uchun sifatli sertifikatlangan urug' yoki ko'chat yetkazib beruvchilari bilan shartnoma tuzing.")

    xavflar = [
        "Xavf: Kasallik va zararkunandalar ko'payishi — Chora: Ekishdan oldin urug'larni fungitsidlar bilan dorilash va nazorat qilib borish.",
        "Xavf: Tuproq namligi va kislotaligi og'ishi — Chora: Har oyda tuproq namligini datchiklar yoki laboratoriya orqali tahlil qilib, sug'orish me'yorini saqlash."
    ]

    suv_izoh = "Dala suv manbalariga yaqin, sug'orish rejasi to'liq shakllantirildi." if has_water else "Dala atrofida suv topilmadi, faqat suvsizlikka chidamli ekinlar yetishtirilishi shart."
    tuproq_izoh = f"Tuproq pH darajasi {ph:.1f} ({'kislotali' if ph < 6.0 else 'ishqoriy' if ph > 7.8 else 'neytral'}). Loy miqdori {clay_pct:.1f}%."
    if nitrogen < 50:
        tuproq_izoh += " Azot miqdori juda kam, zudlik bilan o'g'itlash talab etiladi."
    else:
        tuproq_izoh += " Azot miqdori yetarli va muvozanatlashgan."

    return {
        "yer_tahlili": {
            "umumiy_baho": f"Dala maydoni {area_ha} gektar. Tuproq kislotaligi pH {ph:.1f} va loy tarkibi {clay_pct:.1f}%. Hudud uchun eng yuqori agronomik moslik reytingiga ega ekinlar tanlandi.",
            "tuproq_sifati": tuproq_izoh,
            "suv_holati": suv_izoh,
            "iqlim_sharoit": f"O'rtacha harorat {temp:.1f}°C, yillik yomg'ir {precip:.1f} mm. Iqlim sharoitlari ekinlarga mos keladi.",
            "osimlik_holati": "O'rtacha"
        },
        "ekin_tavsiyalari": recommendations,
        "eng_foydali_ekin": best_crop,
        "sugorish_rejasi": sugorish,
        "ogit_rejasi": ogit_rejasi,
        "bugun_nima_qilish": bugun_nima_qilish,
        "xavflar": xavflar,
        "yillik_reja": {
            "yanvar_fevral": "Urug' va o'g'itlarni sotib olish, issiqlik sharoitiga ko'ra tayyorgarlik ko'rish",
            "mart_aprel": "Ekish va birinchi oziqlantirish ishlarini olib borish",
            "may_iyun": "Begona o'tlarga qarshi kurash va ekinlarni sug'orish",
            "iyul_avgust": "Kasalliklar va zararkunandalar nazorati, erta ekinlarni yig'ish",
            "sentabr_oktabr": "Asosiy hosil yig'im-terimi va erni shudgorlash ishlari",
            "noyabr_dekabr": "Dala maydonini qishki tinchlik davriga tayyorlash va tozalash"
        },
        "xulosa": f"Ushbu {area_ha} gektar maydon uchun barcha agronomik ko'rsatkichlar tahlil qilindi va eng foydali ekinlar tavsiya etildi. Qoidalarga va sug'orish rejasiga rioya qilinganda optimal rentabellik kafolatlanadi."
    }
