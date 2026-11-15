# دليل الفريق — طريقة التشغيل

## 1) اللعبة (أسهل طريقة)
افتح الرابط من أي متصفح: https://sattam-al.github.io/marswalk-mission/
- "ابدأ المهمة الموجّهة": نقطتين علميتين والرجوع للقاعدة، وفيها حدث عائق مفاجئ.
- "خطّط مشيتك بنفسك": اضغط على الخريطة واختر حتى 4 نقاط.
- زر ⚠: بلّغ عن خطر في أي مكان وشوف المسار يتغيّر.
- زر ع / EN: تغيير اللغة.

## 2) Colab (التحليل على بيانات ناسا)
1. ارفع marswalk_router.py و curiosity_traverse.py على /content.
2. شغّل خلية جلب رابط الـ DEM (في colab_helper_cells.py).
3. شغّل colab_demo.py (المسار وإعادة التوجيه) و colab_curiosity.py (مسار Curiosity الحقيقي).

## 3) التشغيل المحلي (ويندوز)
افتح مجلد Python_Engine واضغط دبل كليك على start_game.bat (يحتاج Python). اللعبة تنفتح على http://localhost:8000

## 4) واجهة الـ API
POST /route — POST /reroute — POST /obstacle — GET /obstacles — GET /info — GET /layer/{slope|roughness|cost}.png
