"""
Mahsulot kasalliklari tahlili — TensorFlow modeli va Groq LLaMA yordamida
"""
import json
import numpy as np
import os
from pathlib import Path

try:
    import tensorflow as tf
    from tensorflow.keras.preprocessing import image
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Django settings'ni o'rnatish
import django
from django.conf import settings

if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

# TensorFlow modeli va class names'larni yuklash
BASE_DIR = Path(settings.BASE_DIR)
MODEL_PATH = BASE_DIR / "kasaliklar" / "agrovision_plant_disease_model.keras"
CLASS_PATH = BASE_DIR / "kasaliklar" / "class_names.json"

_model = None
_class_names = None


# 38 ta kasallik klassi uchun batafsil o'zbekcha zaxira ma'lumotlar bazasi
FALLBACK_DISEASE_INFO = {
    "Apple___Apple_scab": {
        "symptoms": "Barglarda va mevalarda zaytun-yashil, keyinchalik qorayadigan baxmalsimon dog'lar paydo bo'ladi. Barglar muddatidan oldin to'kiladi, mevalar yorilib, shakli buziladi.",
        "treatment": "Kasallangan barglar va shoxlarni kesib yo'q qilish. Fungitsidlar (masalan, mis xloroksidi, Skor, Xorus) bilan kurtak yozishdan oldin va gullashdan keyin purkash.",
        "prevention": "Kuzda to'kilgan barglarni to'plash va yoqish yoki chuqur ko'mish. Daraxt tojini siyraklashtirish orqali havo aylanishini yaxshilash, kasallikka chidamli navlarni ekish.",
        "recommendations": [
            "Kuzgi va bahorgi profilaktik ishlov berish",
            "Daraxt ostini toza saqlash",
            "Tarkibida mis bo'lgan dori vositalaridan foydalanish"
        ]
    },
    "Apple___Black_rot": {
        "symptoms": "Barglarda 'qurbaqa ko'zi' kabi konsentrik dog'lar, shoxlarda qora saraton yaralari va mevalarda qora rangli konsentrik chirish dog'lari hosil bo'ladi.",
        "treatment": "Kasallangan shoxlarni kesish va kesilgan joylarni 1% li mis kuporosi bilan dezinfeksiya qilish, bog' malhami surtish. Gullashdan keyin tizimli fungitsidlar purkash.",
        "prevention": "Daraxtni mexanik shikastlanishlardan himoya qilish, zararkunandalarga qarshi kurashish, quritilgan meva va shoxlarni bog'dan chiqarish.",
        "recommendations": [
            "Daraxt po'stlog'idagi yaralarni davolash",
            "Kuzgi sanitariya kesimi",
            "Tizimli fungitsidlarni qo'llash"
        ]
    },
    "Apple___Cedar_apple_rust": {
        "symptoms": "Barglarning ustki qismida yorqin to'q sariq-sariq dog'lar, ostida esa so'galsimon o'smalar paydo bo'ladi. Kuchli zararlanganda barglar muddatidan oldin to'kiladi.",
        "treatment": "Kasallikning birinchi belgilari ko'ringanda tizimli fungitsidlar (Skor, Topaz, Bayleton) bilan ishlov berish.",
        "prevention": "Olma bog'lari yaqinida zang tarqatuvchi archa va archasimon butalarni ekmaslik. Archa butalariga erta bahorda mis preparatlari bilan ishlov berish.",
        "recommendations": [
            "Yaqin atrofdagi archalarni nazorat qilish",
            "Bahorda tizimli fungitsidlar sepish",
            "Profilaktik purkash ishlarini olib borish"
        ]
    },
    "Apple___healthy": {
        "symptoms": "Barglar toza, yashil va shikastlanishlarsiz. Mevalar sog'lom va to'g'ri rivojlanmoqda.",
        "treatment": "Sog'lom daraxt, davolash talab etilmaydi.",
        "prevention": "Muntazam ravishda sug'orish, mineral va organik o'g'itlar bilan oziqlantirish, bog' gigiyenasiga rioya qilish.",
        "recommendations": [
            "Muntazam sug'orish va oziqlantirish",
            "Zararkunandalarga qarshi profilaktika",
            "Daraxt tojini shakllantirish"
        ]
    },
    "Blueberry___healthy": {
        "symptoms": "Barglar yashil, sog'lom va o'sish dinamikasi yaxshi. Hech qanday dog' yoki zararkunanda belgilari yo'q.",
        "treatment": "Sog'lom o'simlik, davolash shart emas.",
        "prevention": "Tuproq kislotaligini (pH 4.5-5.2) saqlash, to'g'ri sug'orish tizimini yo'lga qo'yish va mulchalash.",
        "recommendations": [
            "Tuproq namligini bir xil saqlash",
            "Nordon tuproq muhitini ta'minlash",
            "Bahorgi oziqlantirish"
        ]
    },
    "Cherry_(including_sour)___Powdery_mildew": {
        "symptoms": "Barglar, yosh novdalar va mevalar yuzasida oq mog'orsimon unli g'ubor paydo bo'ladi. Barglar bujmayib qurib qoladi.",
        "treatment": "Oltingugurtli preparatlar (masalan, kolloid oltingugurt) yoki tizimli fungitsidlar (Topaz, Tiovit Djet, Skor) bilan ishlov berish.",
        "prevention": "Daraxt barglarini siyraklashtirish, azotli o'g'itlarni me'yoridan oshirmaslik, kaliyli o'g'itlar qo'llash.",
        "recommendations": [
            "Oltingugurt asosidagi fungitsid sepish",
            "Sug'orishni to'g'ri tashkil etish",
            "Zararlangan qismlarni kesish"
        ]
    },
    "Cherry_(including_sour)___healthy": {
        "symptoms": "Barglar yaltiroq yashil rangda, novdalar sog'lom, mevalar normal rivojlanmoqda.",
        "treatment": "Sog'lom daraxt, davolash kerak emas.",
        "prevention": "Bahorda profilaktik mis preparatlari sepish, zararkunandalardan himoya qilish, to'g'ri sug'orish.",
        "recommendations": [
            "Vaqtida sug'orish",
            "O'g'itlash rejasiga rioya qilish",
            "Kuzgi sanitariya ishlari"
        ]
    },
    "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot": {
        "symptoms": "Barglarda tomirlar bo'ylab cho'zilgan, to'g'ri burchakli kulrang-qo'ng'ir dog'lar paydo bo'ladi. Kuchli zararlanganda barglar butunlay quriydi va hosil keskin kamayadi.",
        "treatment": "Kasallik boshlanganda tizimli fungitsidlar (masalan, karbendazim, triazollar) bilan ishlov berish.",
        "prevention": "Almashlab ekishga rioya qilish, o'simlik qoldiqlarini chuqur haydash orqali yo'q qilish, chidamli duragaylarni tanlash.",
        "recommendations": [
            "Almashlab ekishni yo'lga qo'yish",
            "Kuzgi chuqur shudgorlash",
            "Fungitsidlar bilan profilaktik ishlov berish"
        ]
    },
    "Corn_(maize)___Common_rust_": {
        "symptoms": "Barglarning ikkala tomonida to'q sariq yoki qo'ng'ir rangli changlanuvchi pustulalar (zang dog'lari) hosil bo'ladi.",
        "treatment": "Kasallik keng tarqalganda mis yoki triazol guruhiga mansub fungitsidlar (masalan, Kvadris, Titul) purkash.",
        "prevention": "O'simlik qoldiqlarini daladan yo'q qilish, chidamli navlar ekish, o'z vaqtida kaliy-fosforli o'g'itlar bilan oziqlantirish.",
        "recommendations": [
            "Kaliy va fosfor o'g'itlarini ko'paytirish",
            "Chidamli navlarni tanlash",
            "Dastlabki zang dog'larida fungitsid sepish"
        ]
    },
    "Corn_(maize)___Northern_Leaf_Blight": {
        "symptoms": "Barglarda yirik, qayiqsimon yoki cho'zilgan kulrang-jigarrang dog'lar hosil bo'ladi. Dog'lar birlashib, barglarni butunlay quritib yuboradi.",
        "treatment": "Dastlabki simptomlar ko'ringanda tizimli fungitsidlar (Kvadris, Folicur) sepish.",
        "prevention": "Ekin qoldiqlarini yo'q qilish, tuproqni chuqur yumshatish, almashlab ekish qoidalariga rioya qilish.",
        "recommendations": [
            "Almashlab ekish (kamida 2 yil)",
            "Kasallikka chidamli duragaylar ekish",
            "Urug'larni ekishdan oldin dorilash"
        ]
    },
    "Corn_(maize)___healthy": {
        "symptoms": "Poyasi baquvvat, barglari quyuq yashil, so'limagan va dog'larsiz.",
        "treatment": "Sog'lom ekin, davolash shart emas.",
        "prevention": "Optimal ekish muddatlariga rioya qilish, azot, fosfor va kaliy balansini saqlash, begona o'tlarga qarshi kurashish.",
        "recommendations": [
            "Optimal sug'orish rejimi",
            "Begona o'tlarni tozalash",
            "Mineral oziqlantirish"
        ]
    },
    "Grape___Black_rot": {
        "symptoms": "Barglarda jigarrang dumaloq dog'lar, mevalarda esa avval och jigarrang, keyin butunlay quriydigan va qorayib mumiya bo'lib qoladigan mog'or dog'lari paydo bo'ladi.",
        "treatment": "Mis saqlovchi preparatlar (Bordo suyuqligi) yoki tizimli fungitsidlar (Ridomil Gold, Topaz, Skor) bilan ishlov berish.",
        "prevention": "Tok shoxlarini to'g'ri kesish va ko'tarish, havo aylanishini ta'minlash, to'kilgan rezavorlarni yig'ib yo'q qilish.",
        "recommendations": [
            "Bahorda Bordo aralashmasi bilan purkash",
            "Tok tojlari havo aylanishini yaxshilash",
            "Zararlangan mevalarni tozalash"
        ]
    },
    "Grape___Esca_(Black_Measles)": {
        "symptoms": "Barg tomirlari oralig'ida 'yo'lbars chiziqlari' kabi sarg'ish-jigarrang dog'lar hosil bo'ladi. Rezavorlarda mayda qora dog'lar paydo bo'lib, ular yoriladi.",
        "treatment": "Kasallangan shoxlarni sog'lom qismigacha kesish va kesilgan joylarni dezinfeksiya qilish. Hozirda to'liq kimyoviy davosi yo'q, agrotexnik choralar qo'llaniladi.",
        "prevention": "Tok kesish asboblarini muntazam ravishda dezinfeksiya qilish, eski kesilgan joylarni maxsus bog' pastalari bilan yopish.",
        "recommendations": [
            "Asboblarni muntazam dezinfeksiya qilish",
            "Kasallangan shoxlarni kesib yoqish",
            "O'simlik immunitetini oshirish"
        ]
    },
    "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)": {
        "symptoms": "Barglarning ostki qismida zaytun rangli, keyinchalik qo'ng'ir tus oladigan qora dog'lar hosil bo'ladi. Barglar muddatidan oldin qurib to'kiladi.",
        "treatment": "Mis xloroksidi, Kuproksat yoki tizimli fungitsidlar (masalan, Kvadris) sepish.",
        "prevention": "Sug'orishda barglarga suv sachratmaslik, kuzda to'kilgan barglarni yig'ib yo'q qilish va yoqish.",
        "recommendations": [
            "Kuzda to'kilgan barglarni yoqish",
            "Sug'orish rejimini nazorat qilish",
            "Bahorgi fungitsid sepish"
        ]
    },
    "Grape___healthy": {
        "symptoms": "Barglar yashil, sog'lom, novdalar baquvvat, shingillar toza va yaxshi rivojlanmoqda.",
        "treatment": "Sog'lom tok, davolash talab qilinmaydi.",
        "prevention": "Mikroug'itlar bilan oziqlantirish, muntazam ravishda tokni bog'lash va ortiqcha novdalarni yulib tashlash (xomtok qilish).",
        "recommendations": [
            "Vaqtida xomtok qilish",
            "Muntazam profilaktika",
            "Mikroelementlar bilan oziqlantirish"
        ]
    },
    "Orange___Haunglongbing_(Citrus_greening)": {
        "symptoms": "Barglarda simmetrik bo'lmagan sarg'ish dog'lar ('marmar barg'), mevalar mayda, shakli buzilgan, nordon bo'lib, pastki qismi yashil qoladi.",
        "treatment": "Ushbu xavfli bakterial kasallikning to'g'ridan-to'g'ri davosi yo'q. Zararlangan daraxtlar darhol ildizi bilan sug'urib yoqib yuboriladi.",
        "prevention": "Kasallik tarqatuvchi psillid zararkunandasiga qarshi insektitsidlar qo'llash, faqat sertifikatlangan sog'lom ko'chatlarni ekish.",
        "recommendations": [
            "Zararkunandalarga (psillid) qarshi kurashish",
            "Kasallangan daraxtlarni darhol yo'q qilish",
            "Sertifikatlangan ko'chat ekish"
        ]
    },
    "Peach___Bacterial_spot": {
        "symptoms": "Barglarda mayda, suvli, keyinroq qo'ng'ir rangga kirib to'kiladigan dog'lar hosil bo'ladi ('g'alvirsimon barg'). Mevalarda chuqur qora yoriqlar hosil bo'ladi.",
        "treatment": "Gullashdan oldin va keyin mis saqlovchi vositalar (Bordo aralashmasi, Kuproksat) bilan ishlov berish.",
        "prevention": "Kasallikka chidamli navlar ekish, o'simliklarni to'g'ri oziqlantirish, azotli o'g'itlarni me'yorida berish.",
        "recommendations": [
            "Tarkibida mis bo'lgan fungitsidlar sepish",
            "Kuzgi va bahorgi profilaktik purkash",
            "Chidamli navlarni tanlash"
        ]
    },
    "Peach___healthy": {
        "symptoms": "Barglari yashil, keng yoyilgan, silliq. Mevaleri tekis, chiroyli rangda va sog'lom.",
        "treatment": "Sog'lom daraxt, davolash shart emas.",
        "prevention": "Bog'ni vaqtida sug'orish, bahorda va kuzda profilaktika maqsadida 1% li Bordo suyuqligi bilan purkash.",
        "recommendations": [
            "Kuzgi va bahorgi profilaktika",
            "To'g'ri sug'orish va oziqlantirish",
            "Zararkunandalardan himoya"
        ]
    },
    "Pepper,_bell___Bacterial_spot": {
        "symptoms": "Barglarda, poyalarda va mevalarda mayda, suvli, chetlari qora jigarrang dog'lar paydo bo'ladi. Barglar sarg'ayib to'kiladi.",
        "treatment": "Mis asosidagi preparatlar (mis xloroksidi, Abiga-Pik, Kurzat) bilan o'simliklarga 10-14 kun oralig'ida ishlov berish.",
        "prevention": "Urug'larni ekishdan oldin dorilash, issiqxonalarda havo namligini kamaytirish va almashlab ekishga rioya qilish.",
        "recommendations": [
            "Urug'larni dorilash",
            "Namlikni kamaytirish va havoni shamollatish",
            "Mis preparatlari bilan purkash"
        ]
    },
    "Pepper,_bell___healthy": {
        "symptoms": "Barglari silliq, quyuq yashil, gullari va mevalari normal shaklda va sog'lom.",
        "treatment": "Sog'lom o'simlik, davolash talab qilinmaydi.",
        "prevention": "Optimal sug'orish va kaliy-fosforli o'g'itlar bilan vaqtida oziqlantirish, harorat rejimiga rioya qilish.",
        "recommendations": [
            "Balanslashgan oziqlantirish",
            "Muntazam sug'orish",
            "Begona o'tlardan tozalash"
        ]
    },
    "Potato___Early_blight": {
        "symptoms": "Barglarda aniq konsentrik (aylanasimon) halqali quyuq jigarrang-qora dog'lar hosil bo'ladi. Barglar quriydi va to'kiladi.",
        "treatment": "Tizimli va kontakt fungitsidlar (Ridomil Gold, Konsento, Skor, Signum) bilan ishlov berish.",
        "prevention": "Almashlab ekish, o'simlik qoldiqlarini yo'q qilish, kaliyli o'g'itlarni yetarli darajada qo'llash.",
        "recommendations": [
            "Tizimli fungitsidlarni qo'llash",
            "Kaliy o'g'itlari miqdorini oshirish",
            "Almashlab ekish qoidasiga rioya qilish"
        ]
    },
    "Potato___Late_blight": {
        "symptoms": "Barg chetlarida yirik, suvli, tez kengayadigan to'q jigarrang dog'lar hosil bo'ladi. Bargning ostki qismida oqish mog'or g'ubori paydo bo'ladi, tugunaklar chiriy boshlaydi.",
        "treatment": "Kasallik belgilari ko'rinishi bilan kuchli fungitsidlar (Ridomil Gold, Revus, Konsento, Profit Gold) sepiladi. Ishlov berishni 7-10 kunda takrorlash lozim.",
        "prevention": "Faqat sog'lom urug'lik tugunlarni ekish, tuproqni tepalash (okuchka qilish), ekinlarni dori sepib profilaktika qilish.",
        "recommendations": [
            "Kasallik boshlanishidan oldin profilaktik dori sepish",
            "Sog'lom urug'likdan foydalanish",
            "Zararlangan poyalarni kesish va yo'q qilish"
        ]
    },
    "Potato___healthy": {
        "symptoms": "Barglari baquvvat, sershox, yashil. Hech qanday dog' yoki sarg'ayish belgilari yo'q.",
        "treatment": "Sog'lom ekin, davolash shart emas.",
        "prevention": "Vaqtida sug'orish (ayniqsa gullash davrida), tuproqni yumshatish, chidamli navlarni ekish.",
        "recommendations": [
            "Tuproqni yumshatish va tepalash",
            "Optimal namlikni saqlash",
            "Zararkunandalarni nazorat qilish"
        ]
    },
    "Raspberry___healthy": {
        "symptoms": "Poyalari tekis, barglari chiroyli yashil rangda, gullari va rezavorlari toza va mo'l.",
        "treatment": "Sog'lom o'simlik, davolash shart emas.",
        "prevention": "Eski poyalarni kuzda kesish, malinazorni qalinlashib ketishiga yo'l qo'ymaslik, muntazam ravishda mineral oziqlantirish.",
        "recommendations": [
            "Eski va quruq novdalarni kesish",
            "Muntazam sug'orish",
            "Organik o'g'itlar bilan oziqlantirish"
        ]
    },
    "Soybean___healthy": {
        "symptoms": "Barglari toza, sarg'ayishlarsiz va dog'larsiz yashil rangda. Dukkaklari sog'lom rivojlanmoqda.",
        "treatment": "Sog'lom ekin, davolash talab etilmaydi.",
        "prevention": "Almashlab ekish, tugun bakteriyalari bilan urug'larni dorilash, optimal ekish sxemasiga rioya qilish.",
        "recommendations": [
            "Almashlab ekish",
            "Begona o'tlarga qarshi kurash",
            "Fosforli o'g'itlar bilan oziqlantirish"
        ]
    },
    "Squash___Powdery_mildew": {
        "symptoms": "Barglarning ustki va ostki tomonida oqish, unsimon g'ubor paydo bo'ladi. Barglar sarg'ayadi, quriydi va mo'rt bo'lib qoladi.",
        "treatment": "Tizimli fungitsidlar (Topaz, Kvadris, Skor) yoki kolloid oltingugurt bilan ishlov berish.",
        "prevention": "Sug'orishda barglarga suv sachratmaslik (tomchilatib sug'orish), azotli o'g'itlarni kamaytirish va havo almashinuvini yaxshilash.",
        "recommendations": [
            "Oltingugurtli preparatlar sepish",
            "Tomchilatib sug'orish tizimini qo'llash",
            "Zararlangan barglarni olib tashlash"
        ]
    },
    "Strawberry___Leaf_scorch": {
        "symptoms": "Barglarda qizg'ish-binafsha dog'lar hosil bo'ladi, keyinchalik ular kengayib, barg qurib qoladi va kuygan ko'rinishga keladi.",
        "treatment": "Gullashdan oldin va hosil yig'ilgandan keyin Bordo suyuqligi yoki mis saqlovchi fungitsidlar (masalan, Kuproksat) bilan purkash.",
        "prevention": "Qulupnayzorni qalinlashtirmaslik, eski kasallangan barglarni tozalash va yoqish, mo'ylovlarni vaqtida qirqish.",
        "recommendations": [
            "Eski barglarni bahorda va kuzda kesish",
            "Misli fungitsidlar bilan ishlov berish",
            "Ekin maydonini siyraklashtirish"
        ]
    },
    "Strawberry___healthy": {
        "symptoms": "Barglari to'q yashil, yaltiroq, mevalari sog'lom va qizil rangda, dog'larsiz.",
        "treatment": "Sog'lom o'simlik, davolash shart emas.",
        "prevention": "Sug'orish rejimini saqlash, tuproqni mulchalash (somon yoki qora plyonka bilan), kaliyli o'g'itlar berish.",
        "recommendations": [
            "Tuproqni mulchalash",
            "Mevalarni nam tuproqqa tegishidan saqlash",
            "Kaliy bilan oziqlantirish"
        ]
    },
    "Tomato___Bacterial_spot": {
        "symptoms": "Barglarda, poyada mayda, suvli, chetlari qora jigarrang dog'lar hosil bo'ladi. Mevalarda qora, qo'pol so'galsimon dog'lar paydo bo'ladi.",
        "treatment": "Kasallikning boshida mis saqlovchi fungitsidlar (Kozayd, Abiga-Pik, Bordo aralashmasi) sepish.",
        "prevention": "Issiqxonalarda namlikni kamaytirish va havoni yaxshi aylantirish, urug'larni ekishdan oldin dorilash.",
        "recommendations": [
            "Tarkibida mis bo'lgan dori sepish",
            "Issiqxonani muntazam shamollatish",
            "Urug'larni dorilash"
        ]
    },
    "Tomato___Early_blight": {
        "symptoms": "Pastki barglardan boshlab halqasimon konsentrik jigarrang-qora dog'lar paydo bo'ladi. Poyalarda va meva bandida quyuq botiq dog'lar hosil bo'ladi.",
        "treatment": "Tizimli fungitsidlar (Kvadris, Skor, Ridomil Gold, Signum) bilan o'simliklarni purkash.",
        "prevention": "Pastki sarg'aygan va kasal barglarni kesish, o'simliklarni tomchilatib sug'orish va almashlab ekish.",
        "recommendations": [
            "Pastki barglarni erta kesib tashlash",
            "Tizimli fungitsidlar qo'llash",
            "Barg yuzasini quruq saqlash"
        ]
    },
    "Tomato___Late_blight": {
        "symptoms": "Barglar va mevalarda to'q jigarrang, yirik, hoshiyasiz dog'lar paydo bo'ladi. Nam havoda barg ostida oqish g'ubor ko'rinadi. Mevalar ichkaridan qo'ng'ir tus olib chiriydi.",
        "treatment": "Zudlik bilan kuchli tizimli fungitsidlar (Ridomil Gold, Revus, Konsento) sepish lozim. Ishlov berishni 7-10 kunda qayta bajarish kerak.",
        "prevention": "Pomidorni kartoshkadan uzoqroqqa ekish, o'simlik ostini mulchalash, profilaktik maqsadida mis preparatlari sepib turish.",
        "recommendations": [
            "Kartoshka yaqiniga ekmaslik",
            "Zudlik bilan kuchli fungitsidlar sepish",
            "Profilaktik purkash (nam ob-havoda)"
        ]
    },
    "Tomato___Leaf_Mold": {
        "symptoms": "Barglarning ustki qismida sarg'ish-yashil dog'lar, ostki qismida esa qo'ng'ir-binafsha rangli baxmalsimon mog'or g'ubori hosil bo'ladi.",
        "treatment": "Issiqxonani muntazam shamollatish va namlikni pasaytirish. Kvadris, Xorus kabi fungitsidlar sepish.",
        "prevention": "Issiqxonada havo namligini 70-80% dan oshirmaslik, chidamli navlarni tanlash, o'simliklarni juda zich ekmaslik.",
        "recommendations": [
            "Havo namligini keskin kamaytirish",
            "Fungitsidlar bilan purkash",
            "Zichlikni kamaytirish uchun barglarni siyraklash"
        ]
    },
    "Tomato___Septoria_leaf_spot": {
        "symptoms": "Barglarda to'q jigarrang hoshiyali, markazi kulrang-oq rangli mayda dumaloq dog'lar hosil bo'ladi. Kuchli zararlanganda barglar butunlay sarg'ayadi va quriydi.",
        "treatment": "Mis xloroksidi, Abiga-Pik yoki tizimli fungitsidlar (masalan, Kvadris) bilan ishlov berish.",
        "prevention": "Sug'orishda barglarga suv sachratmaslik, kuzda o'simlik qoldiqlarini yo'q qilish, tuproqni chuqur shudgorlash.",
        "recommendations": [
            "Barg ostidan sug'orish (tomchilatib)",
            "Kasallangan barglarni yig'ib yoqish",
            "Mis preparatlarini qo'llash"
        ]
    },
    "Tomato___Spider_mites Two-spotted_spider_mite": {
        "symptoms": "Barglarning ostida mayda sarg'ish nuqtalar paydo bo'ladi, keyinchalik ular sarg'ayib quriydi. Barglar orqasida mayda to'r va mayda harakatlanuvchi kanalar ko'rinadi.",
        "treatment": "Maxsus oqadilar va kanalarga qarshi vositalar — akaritsidlar (Vermitek, Fitoverm, Aktara, Neoron) qo'llash.",
        "prevention": "Havoni haddan tashqari quruq bo'lishiga yo'l qo'ymaslik, begona o'tlarni tozalash, zararkunanda tarqalishidan oldin profilaktik suv purkash.",
        "recommendations": [
            "Akaritsidlar (Vermitek, Fitoverm) qo'llash",
            "Barg orqasini yaxshilab dorilash",
            "Namlikni me'yorda saqlash"
        ]
    },
    "Tomato___Target_Spot": {
        "symptoms": "Barglarda markazi oqargan va aylanma chiziqlari bo'lgan jigarrang halqasimon nishonga o'xshash dog'lar paydo bo'ladi. Meva va poyalarni ham zararlaydi.",
        "treatment": "Kvadris, Ridomil Gold yoki boshqa tizimli triazol fungitsidlar sepish.",
        "prevention": "Almashlab ekish, o'simliklar orasida havo aylanishini ta'minlash, namlik darajasini nazorat qilish.",
        "recommendations": [
            "Daraxt/buta ostini toza saqlash",
            "Tizimli fungitsid purkash",
            "Havo aylanishini yaxshilash"
        ]
    },
    "Tomato___Tomato_Yellow_Leaf_Curl_Virus": {
        "symptoms": "Barglar maydalashadi, chetlari yuqoriga qarab bujmayadi va sarg'ayadi. O'simlik o'sishdan to'xtaydi, gullari to'kilib ketadi va hosil bermaydi.",
        "treatment": "Virusli kasalliklarning davosi yo'q. Kasallangan butalar darhol ildizi bilan yulib yoqiladi.",
        "prevention": "Virus tarqatuvchi oqqanot (belokrilka) zararkunandasiga qarshi tizimli insektitsidlar (Aktara, Konfidor) sepish, issiqxonalarga hasharotlarga qarshi to'rlar o'rnatish.",
        "recommendations": [
            "Oqqanot zararkunandasini yo'q qilish",
            "Kasallangan butalarni zudlik bilan yo'q qilish",
            "Hasharotlardan himoya qiluvchi to'rlar o'rnatish"
        ]
    },
    "Tomato___Tomato_mosaic_virus": {
        "symptoms": "Barglarda to'q va och yashil rangli mozaik dog'lar, barg shaklining o'zgarishi va ipsimon bo'lib qolishi kuzatiladi. Hosildorlik keskin kamayadi.",
        "treatment": "Davosi yo'q. Kasal o'simliklar yo'q qilinadi va qo'llar hamda asboblar dezinfeksiya qilinadi.",
        "prevention": "Urug'larni ekishdan oldin kaliy permanganat (margansovka) eritmasida dezinfeksiya qilish, chidamli duragaylarni ekish.",
        "recommendations": [
            "Urug'larni ekishdan oldin dezinfeksiya qilish",
            "Kasal o'simliklarni darhol yo'q qilish",
            "Asboblarni ishlovdan keyin dezinfeksiya qilish"
        ]
    },
    "Tomato___healthy": {
        "symptoms": "Barglari quyuq yashil, silliq, poyasi baquvvat va toza. Gullash va meva tugish jarayoni sog'lom.",
        "treatment": "Sog'lom o'simlik, davolash talab qilinmaydi.",
        "prevention": "Muntazam ravishda sug'orish, mineral va organik o'g'itlar bilan oziqlantirish, begona o'tlar va zararkunandalardan himoya qilish.",
        "recommendations": [
            "Vaqtida sug'orish va oziqlantirish",
            "Pastki barglarni havo aylanishi uchun tozalash",
            "Profilaktik nazorat"
        ]
    }
}


def _load_model():
    """TensorFlow modelini yuklash (bir marta)"""
    global _model, _class_names
    
    if _model is not None:
        return _model, _class_names
    
    if not TF_AVAILABLE:
        print("TensorFlow o'rnatilmagan")
        return None, None
    
    try:
        print(f"Model path: {MODEL_PATH}")
        print(f"Model mavjud: {MODEL_PATH.exists()}")
        print(f"Class path: {CLASS_PATH}")
        print(f"Class mavjud: {CLASS_PATH.exists()}")
        
        if MODEL_PATH.exists():
            print("Model yuklash boshlandi...")
            _model = tf.keras.models.load_model(str(MODEL_PATH))
            print("Model muvaffaqiyatli yuklandi")
        else:
            print(f"Model fayli topilmadi: {MODEL_PATH}")
        
        if CLASS_PATH.exists():
            print("Class names yuklash boshlandi...")
            with open(CLASS_PATH, "r", encoding="utf-8") as f:
                _class_names = json.load(f)
            print(f"Class names yuklandi: {len(_class_names)} ta class")
        else:
            print(f"Class names fayli topilmadi: {CLASS_PATH}")
        
        return _model, _class_names
    except Exception as e:
        print(f"Model yuklash xatosi: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def predict_plant_disease(img_path: str) -> dict:
    """
    TensorFlow modeli yordamida rasmdagi kasallikni aniqlab qo'yadi.
    
    Returns:
        {
            "status": "success" | "uncertain" | "error",
            "disease": "Kasallik nomi",
            "confidence": 0-100,
            "message": "Tavsif",
        }
    """
    
    model, class_names = _load_model()
    
    if model is None or class_names is None:
        return {
            "status": "error",
            "disease": "Noma'lum",
            "confidence": 0.0,
            "message": "Model yuklash xatosi",
        }
    
    try:
        # Rasmni yuklash va tayyorlash
        img = image.load_img(img_path, target_size=(224, 224))
        img_array = image.img_to_array(img)
        img_array = np.expand_dims(img_array, axis=0)
        
        # Bashorat qilish
        prediction = model.predict(img_array, verbose=0)[0]
        
        predicted_index = int(np.argmax(prediction))
        predicted_class = class_names[predicted_index]
        confidence = float(np.max(prediction) * 100)
        
        # Ishonch darajasi bo'yicha status
        if confidence < 60:
            status = "uncertain"
            message = "Aniq tashxis qo'yib bo'lmadi. Bargni tiniqroq va yaqinroq suratga olib qayta yuklang."
        else:
            status = "success"
            message = "Kasallik aniqlandi."
        
        return {
            "status": status,
            "disease": predicted_class,
            "confidence": round(confidence, 2),
            "message": message,
        }
    
    except Exception as e:
        return {
            "status": "error",
            "disease": "Noma'lum",
            "confidence": 0.0,
            "message": f"Tahlil xatosi: {str(e)}",
        }


def analyze_crop_image(image_path: str, crop_name: str = "") -> dict:
    """
    Rasmdagi mahsulotni tahlil qiladi:
    1. TensorFlow modeli bilan kasallik aniqlanadi
    2. Groq AI yoki zaxira lug'at bilan batafsil tahlil yaratiladi
    
    Returns:
        {
            "health_status": "healthy" | "moderate" | "poor" | "critical",
            "diseases": [{"name": "...", "symptoms": "...", ...}],
            "analysis": "Batafsil tahlil",
            "confidence": 0.0-1.0,
        }
    """
    
    # 1. TensorFlow modeli bilan kasallik aniqlanadi
    tf_result = predict_plant_disease(image_path)
    
    if tf_result["status"] == "error":
        return {
            "health_status": "unknown",
            "diseases": [],
            "analysis": {
                "symptoms": "Tahlil xatosi",
                "treatment": tf_result["message"],
                "prevention": "Qayta yuklash",
                "recommendations": ["Rasm sifatini tekshiring"]
            },
            "confidence": 0.0,
        }
    
    disease_name = tf_result["disease"]
    confidence = tf_result["confidence"] / 100.0  # 0-1 ga o'tkazish
    
    # Sog'lig'i holati aniqlanadi
    if confidence < 0.6:
        health_status = "unknown"
    elif disease_name.lower() in ["healthy", "sog'lig'i yaxshi", "normal"] or "healthy" in disease_name.lower():
        health_status = "healthy"
    elif confidence > 0.85:
        health_status = "critical"
    elif confidence > 0.7:
        health_status = "poor"
    else:
        health_status = "moderate"
    
    # 2. Groq AI bilan batafsil tahlil (yoki zaxira lug'at)
    ai_analysis = _get_ai_analysis(disease_name, crop_name, confidence)
    
    return {
        "health_status": health_status,
        "diseases": [
            {
                "name": disease_name,
                "confidence": confidence,
                "severity": _get_severity(health_status),
                "symptoms": ai_analysis.get("symptoms", ""),
                "treatment": ai_analysis.get("treatment", ""),
            }
        ],
        "analysis": ai_analysis,
        "confidence": confidence,
    }


def _get_severity(health_status: str) -> str:
    """Sog'lig'i holatiga ko'ra darajani qaytaradi"""
    severity_map = {
        "healthy": "Yo'q (Sog'lom)",
        "moderate": "O'rtacha",
        "poor": "Og'ir (Juda yomon)",
        "critical": "Kritik (Juda xavfli)",
        "unknown": "Noma'lum",
    }
    return severity_map.get(health_status, "Noma'lum")


def _get_ai_analysis(disease_name: str, crop_name: str, confidence: float) -> dict:
    """Groq AI yordamida batafsil o'zbekcha tahlil yaratadi, muvaffaqiyatsizlikda zaxiraga murojaat qiladi"""
    
    # Mos keladigan zaxira ma'lumotlarini olish
    fallback_data = FALLBACK_DISEASE_INFO.get(
        disease_name, 
        {
            "symptoms": f"Aniqlangan kasallik: {disease_name}.",
            "treatment": "Davolash usullarini aniqlash uchun agronom mutaxassis bilan maslahatlashing.",
            "prevention": "Ekin maydonida sanitariya va to'g'ri sug'orish choralarini ko'ring.",
            "recommendations": ["Zararlangan barglarni kesish va yo'q qilish", "Kasallik tarqalishining oldini olish"]
        }
    )
    
    if not GROQ_AVAILABLE:
        print("Groq SDK o'rnatilmagan. Zaxira ma'lumotlaridan foydalaniladi.")
        return fallback_data
    
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        print("GROQ_API_KEY topilmadi. Zaxira ma'lumotlaridan foydalaniladi.")
        return fallback_data
    
    # Ishlatiladigan modellar ketma-ketligi (zaxira bilan)
    models_to_try = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-8b-8192"
    ]
    
    prompt = f"""Siz agronomik mutaxassissiz. Quyidagi kasallik haqida to'liq va mukammal ma'lumot bering. Javobni faqat o'zbek tilida yozing.
Barcha agrotexnik va kimyoviy davolash choralarini, dori vositalarini batafsil tushuntiring.

Kasallik nomi (klassifikator bo'yicha): {disease_name}
Ekin turi: {crop_name or "Ekin"}
Model ishonch darajasi: {confidence * 100:.1f}%

Quyidagi JSON formatida javob bering, hech qanday qo'shimcha so'z yoki matn yozmang. Faqat va faqat to'g'ri JSON qaytaring:
{{
    "symptoms": "Kasallik simptomlari va belgilari haqida to'liq o'zbekcha ma'lumot (2-3 qator)",
    "treatment": "Kasallikni davolash, ishlatiladigan preparatlar, agronomik choralar va kimyoviy dori vositalari haqida batafsil ma'lumot",
    "prevention": "Kasallikning oldini olish choralari va agrotexnik qoidalar (batafsil)",
    "recommendations": [
        "Tavsiya 1: Aniq va amaliy tavsiya",
        "Tavsiya 2: Yana bir amaliy tavsiya",
        "Tavsiya 3: Muhim profilaktik tavsiya"
    ]
}}"""
    
    for model in models_to_try:
        try:
            print(f"Groq API orqali so'rov yuborilmoqda, model: {model}...")
            client = Groq(api_key=api_key)
            
            chat_completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            
            response_text = chat_completion.choices[0].message.content.strip()
            
            # JSON ni topish va parse qilish
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                
                # Barcha zaruriy kalitlar mavjudligini ta'minlash
                required_keys = ["symptoms", "treatment", "prevention", "recommendations"]
                if all(k in result for k in required_keys):
                    print(f"Groq tahlili ({model}) muvaffaqiyatli qabul qilindi.")
                    return result
                else:
                    # Agar ba'zi kalitlar bo'lmasa, zaxira bilan to'ldiramiz
                    for k in required_keys:
                        if k not in result or not result[k]:
                            result[k] = fallback_data[k]
                    return result
            
        except Exception as e:
            print(f"Groq model ({model}) xatosi: {e}")
            continue
            
    # Agar barcha modellar xatolikka uchrasa, zaxira lug'atini qaytaramiz
    print("Barcha Groq modellari xatolikka uchradi. Zaxira ma'lumotlaridan foydalaniladi.")
    return fallback_data


def get_disease_recommendations(disease_name: str, crop_name: str = "") -> dict:
    """Kasallik bo'yicha zaxira tavsiyalari"""
    
    fallback = FALLBACK_DISEASE_INFO.get(disease_name, {
        "symptoms": "",
        "treatment": "Agronomga murojaat qiling",
        "prevention": "Havo almashinuvi, sanitariya",
        "recommendations": ["Zararli barglarni kesish", "Fungitsidlar ishlatish"]
    })
    
    return {
        "immediate_actions": fallback["recommendations"],
        "preventive_measures": [fallback["prevention"]],
        "treatment_options": [
            {
                "disease": disease_name,
                "severity": "O'rtacha",
                "treatment": fallback["treatment"],
            }
        ],
    }
