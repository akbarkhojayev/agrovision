"""Groq LLM yordamida agronomi tahlili."""
import json
import re

from groq import Groq
from django.conf import settings


def analyze(context: dict) -> dict:
    client = Groq(api_key=settings.GROQ_API_KEY)

    prompt = f"""Sen professional agronomi va yer tahlilchisissan.
Quyidagi HAQIQIY ma'lumotlarni o'zbek tilida tahlil qil:
- NDVI/EVI/NDWI: Sentinel-2 sun'iy yo'ldoshidan (AgroMonitoring)
- Ob-havo: ERA5 reanaliz (Open-Meteo)
- Tuproq kimyosi: SoilGrids ISRIC (haqiqiy o'lchov)

Ma'lumotlar:
{json.dumps(context, ensure_ascii=False, indent=2)}

Ko'rsatkichlar:
NDVI: -1..+1. 0.6+= sich o'simlik, 0.3-0.6= o'rtacha, 0.1-0.3= siyrak, <0.1= tuproq/beton.
EVI: yuqori biomassa uchun NDVI dan aniqroq.
NDWI (suv indeksi): 0.3+= yaxshi namlangan, 0..0.3= o'rtacha, <0= quruq.
Qurg'oqchilik (DI): -3..+3. Manfiy= quruqlik, musbat= namlik.
pH: 6.0-7.5= ko'pchilik ekinlar uchun ideal.

Faqat JSON qaytaring (boshqa matn yo'q):
{{
  "ndvi_baho": "NDVI, EVI, NDWI qiymatlari va ularning ma'nosi (2-3 jumla)",
  "osimlik_holati": "Juda yaxshi | Yaxshi | O'rtacha | Yomon | Juda yomon",
  "tuproq_tahlili": "Tuproq namligi, harorat VA kimyosi (pH, loy, qum, azot) tahlili (3-4 jumla)",
  "qurgochlik": "Qurg'oqchilik xatari: past | o'rta | yuqori — NDWI va DI asosida sababi bilan",
  "tavsiya_ekinlar": ["ekin 1", "ekin 2", "ekin 3", "ekin 4"],
  "dehqonchilik_maslahati": ["maslahati 1", "maslahati 2", "maslahati 3", "maslahati 4"],
  "xavflar": ["xavf 1", "xavf 2", "xavf 3"],
  "ustuvor_harakatlar": ["harakat 1", "harakat 2", "harakat 3"],
  "bashorat": "Keyingi oyda o'simlik va iqlim holati qanday bo'lishi kutilmoqda (2 jumla)",
  "xulosa": "Umumiy xulosa va asosiy tavsiya (3-4 jumla)"
}}"""

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = completion.choices[0].message.content.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"xulosa": raw}
