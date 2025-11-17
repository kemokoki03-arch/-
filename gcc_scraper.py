# -*- coding: utf-8 -*-
import re, time, threading, json, os, random
from typing import List, Dict, Tuple, Optional
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

# ================== CONFIG / CONSTANTS ==================
GCC: Dict[str, dict] = {
    "UAE": {"label":"الإمارات","hl":"ar","gl":"AE","host":"www.google.ae",
            "bounds":{"min_lat":22.8,"max_lat":26.2,"min_lng":51.45,"max_lng":56.50}},
    "KSA": {"label":"السعودية","hl":"ar","gl":"SA","host":"www.google.com.sa",
            "bounds":{"min_lat":15.5,"max_lat":32.3,"min_lng":34.5,"max_lng":55.8}},
    "QAT": {"label":"قطر","hl":"ar","gl":"QA","host":"www.google.com.qa",
            "bounds":{"min_lat":24.3,"max_lat":26.3,"min_lng":50.5,"max_lng":52.0}},
    "BHR": {"label":"البحرين","hl":"ar","gl":"BH","host":"www.google.com.bh",
            "bounds":{"min_lat":25.4,"max_lat":26.5,"min_lng":50.2,"max_lng":50.85}},
    "KWT": {"label":"الكويت","hl":"ar","gl":"KW","host":"www.google.com.kw",
            "bounds":{"min_lat":28.4,"max_lat":30.2,"min_lng":46.5,"max_lng":49.0}},
    "OMN": {"label":"عُمان","hl":"ar","gl":"OM","host":"www.google.com.om",
            "bounds":{"min_lat":16.5,"max_lat":26.0,"min_lng":52.0,"max_lng":60.0}},
}

# مهلات/مراقبة
MAX_QUERY_TIME   = int(os.getenv("MAX_QUERY_TIME", "45"))     # ثانية لكل Query
FREEZE_MAX_SEC   = int(os.getenv("FREEZE_MAX_SEC", "12"))     # ثانية اعتبار الصفحة مجمّدة
REFRESH_EVERY_QS = int(os.getenv("REFRESH_EVERY_QS", "30"))   # إعادة تهيئة خفيفة
STALL_RESETS     = int(os.getenv("STALL_RESETS", "5"))        # مرات ركود قبل إعادة تشغيل السيلينيوم

DEFAULT_KEYWORDS: List[str] = []
UPLOADED_KEYWORDS: List[str] = []

# ================== ALL SERVICES (شامل) ==================
ALL_MAP_SERVICES: List[str] = [
    # (اختصار القائمة هنا لأسباب المساحة — نفس القائمة الشاملة اللي أرسلتها لك قبل كده)
    "مطعم","Restaurant","كافيه","Cafe","Coffee shop","سوبر ماركت","Supermarket","Grocery",
    "Electronics store","Mobile shop","Clothing store","Shoes store","Jewelry","Optical",
    "Pharmacy","صيدلية","Hospital","Clinic","Dental clinic","Laboratory","Radiology","Vet",
    "School","مدرسة","University","Training center","Driving school",
    "Park","حديقة","Gym","Salon","Barbershop","Cinema","Museum","Art gallery",
    "Hotel","فندق","Car rental","Taxi","Bus station","Airport","Gas station","Charging station",
    "Car wash","Oil change","Tire shop","Car repair",
    "Bank","بنك","ATM","Exchange","Insurance","Police","Fire station","Embassy",
    "Municipality","Government office","Post office","Courier",
    "Real estate office","Construction company","Logistics","Warehouse","Factory",
    "Printer","Printing","Telecom","Internet service provider",
    "Plumber","Electrician","A/C service","Pest control",
    "Laundry","Dry clean","Tailor","Mosque","Church","Temple",
    "Service center","Showroom","Head office","فرع"
]

# ================== ADMIN جاهز ==================
ADMIN: Dict[str, Dict[str, List[str]]] = {
    "BHR": {
        "L1": ["العاصمة","المحرق","الشمالية","الجنوبية","Capital","Muharraq","Northern","Southern"],
        "L2": ["المنامة","المحرق","سترة","الرفاع","مدينة عيسى","مدينة حمد","البسيتين","الحد",
               "Budaiya","Jidhafs","A'ali","Sitra","Riffa","Isa Town","Hamad Town","Barbar","Saar"],
        "L3": []
    },
    "KWT": {
        "L1": ["العاصمة","حولي","الفروانية","الأحمدي","الجهراء","مبارك الكبير",
               "Capital","Hawalli","Farwaniya","Ahmadi","Jahra","Mubarak Al-Kabeer"],
        "L2": ["مدينة الكويت","السالمية","حولي","الفحيحيل","الأحمدي","الجهرا","الأندلس","الفروانية",
               "القرين","المنقف","المهبولة","ضاحية صباح السالم","صباح الأحمد","الخيران"],
        "L3": []
    },
    "QAT": {
        "L1": ["الدوحة","الريان","الوكرة","الخور والذخيرة","الشمال","الشحانية","أم صلال","الظعاين",
               "Doha","Al Rayyan","Al Wakrah","Al Khor and Al Thakhira","Al Shamal","Al Shahaniya","Umm Salal","Al Daayen"],
        "L2": ["الدوحة","مشيرب","السد","الهتمي","نجمة","المنصورة","المطار القديم","أبو هامور","الوعب",
               "الوكرة","الوكير","مسيعيد","الخور","الغرافة","المعيذر","الريان","الوجبة","السيلية"],
        "L3": []
    },
    "UAE": {
        "L1": ["أبوظبي","دبي","الشارقة","عجمان","أم القيوين","رأس الخيمة","الفجيرة",
               "Abu Dhabi","Dubai","Sharjah","Ajman","Umm Al Quwain","Ras Al Khaimah","Fujairah"],
        "L2": ["مدينة أبوظبي","العين","الظفرة","دبي","الشارقة","خورفكان","كلباء","عجمان",
               "رأس الخيمة","الفجيرة","أم القيوين","جبل علي","الذيد","الخمير"],
        "L3": ["ليوا","غياثي","دلما","الرويس","مصفح","البراكة","دبا","حتا"]
    },
    "KSA": {
        "L1": ["الرياض","مكة المكرمة","المدينة المنورة","الشرقية","عسير","تبوك","حائل",
               "الحدود الشمالية","جازان","نجران","الباحة","الجوف","القصيم",
               "Riyadh","Makkah","Madinah","Eastern Province","Asir","Tabuk","Hail",
               "Northern Borders","Jazan","Najran","Al Baha","Al Jouf","Qassim"],
        "L2": ["الرياض","الدرعية","الخرج","المجمعة","الدوادمي","القويعية","وادي الدواسر","شقراء",
               "مكة","جدة","الطائف","رابغ","المدينة","ينبع","الدمام","الخبر","الظهران","الجبيل","الأحساء",
               "أبها","خميس مشيط","جازان","صبيا","صامطة","نجران","تبوك","حائل","عرعر","سكاكا","القريات","الباحة","بيشة"],
        "L3": ["قرية","قرى","نجع","عزبة","كفر","حي","ضاحية","حارة","شارع","مركز","بلدة","هجرة"]
    },
    "OMN": {
        "L1": ["مسقط","ظفار","مسندم","البريمي","الداخلية","الظاهرة","شمال الباطنة","جنوب الباطنة",
               "شمال الشرقية","جنوب الشرقية","الوسطى",
               "Muscat","Dhofar","Musandam","Al Buraimi","Ad Dakhiliyah","Ad Dhahirah",
               "North Al Batinah","South Al Batinah","North Ash Sharqiyah","South Ash Sharqiyah","Al Wusta"],
        "L2": ["السيب","بوشر","مطرح","قريات","صلالة","خصب","مدحاء","البريمي","عبري","نزوى","بدبد","بهلاء",
               "صحم","صحار","الرستاق","بركاء","صور","إبراء","الدقم","هيما"],
        "L3": ["ولاية","قرية","نيابة","بلدة","حي","حلة"]
    }
}

L1_SUFFIXES_AR = [" إمارة"," محافظة"," ولاية"," منطقة"," بلدية"," جهة"," إقليم"]
L1_SUFFIXES_EN = [" emirate"," governorate"," wilayat"," region"," municipality"," province"," county"]
L2_SUFFIXES_AR = [" مدينة"," مركز"," بلدية"," قسم"," ناحية"," قضاء"]
L2_SUFFIXES_EN = [" city"," center"," municipality"," district"," county"," borough"," township"]
L3_SUFFIXES_AR = [" قرية"," نجع"," عزبة"," كفر"," حي"," ضاحية"," حارة"," شارع"," بلدة"," هجرة"]
L3_SUFFIXES_EN = [" village"," hamlet"," neighborhood"," suburb"," alley"," street"," block"," town"]

JOBS: Dict[str, dict] = {}
LOCK = threading.Lock()

# ================== GEO / GRID & ZONES ==================
def in_bounds(lat: float, lng: float, country: str) -> bool:
    b = GCC[country]["bounds"]
    return (b["min_lat"] <= lat <= b["max_lat"]) and (b["min_lng"] <= lng <= b["max_lng"])

def frange(start: float, stop: float, step: float):
    v = start
    while v <= stop + 1e-9:
        yield round(v, 6); v += step

def gen_offsets(aggressive: bool):
    base = [(0,0),(0.5,0),(0,0.5),(-0.5,0),(0,-0.5)]
    if not aggressive: return base
    extra = [(0.33,0.33),(-0.33,0.33),(0.33,-0.33),(-0.33,-0.33),
             (0.25,0.25),(-0.25,0.25),(0.25,-0.25),(-0.25,-0.25)]
    return base + extra

def build_grid(country: str, step_deg: float = 0.25, aggressive: bool = False) -> List[Tuple[float,float]]:
    b = GCC[country]["bounds"]
    pts = []
    for dx, dy in gen_offsets(aggressive):
        lats = list(frange(b["min_lat"]+dy*step_deg, b["max_lat"], step_deg))
        lngs = list(frange(b["min_lng"]+dx*step_deg, b["max_lng"], step_deg))
        pts.extend([(la, lo) for la in lats for lo in lngs])
    seen, uniq = set(), []
    for la, lo in pts:
        k = (round(la,5), round(lo,5))
        if k in seen: continue
        if in_bounds(la, lo, country):
            seen.add(k); uniq.append((la,lo))
    random.shuffle(uniq)
    return uniq

def build_zones(country: str, rows: int = 4, cols: int = 4) -> List[dict]:
    b = GCC[country]["bounds"]
    lat_step = (b["max_lat"] - b["min_lat"]) / rows
    lng_step = (b["max_lng"] - b["min_lng"]) / cols
    zones, zidx = [], 1
    for r in range(rows):
        for c in range(cols):
            min_lat = b["min_lat"] + r*lat_step
            max_lat = min_lat + lat_step
            min_lng = b["min_lng"] + c*lng_step
            max_lng = min_lng + lng_step
            zones.append({
                "id": f"{country}-Z{zidx}",
                "name": f"{GCC[country]['label']} Zone {zidx}",
                "bbox": (min_lat, max_lat, min_lng, max_lng),
                "center": ((min_lat+max_lat)/2.0, (min_lng+max_lng)/2.0)
            })
            zidx += 1
    return zones

def zone_contains_point(zone_bbox: Tuple[float,float,float,float], lat: float, lng: float) -> bool:
    min_la, max_la, min_lo, max_lo = zone_bbox
    return (min_la <= lat <= max_la) and (min_lo <= lng <= max_lo)

def filter_grid_by_zones(grid: List[Tuple[float,float]], zones: List[dict], selected_ids: List[str]) -> List[int]:
    sel = set([z.strip().lower() for z in selected_ids])
    pick = [z for z in zones if (z["id"].lower() in sel) or (z["name"].lower() in sel)]
    if not pick:
        return list(range(len(grid)))
    idxs = []
    for i,(la,lo) in enumerate(grid):
        for z in pick:
            if zone_contains_point(z["bbox"], la, lo):
                idxs.append(i); break
    return idxs

def export_zones_geojson(country: str, rows: int = 4, cols: int = 4, out_path: Optional[str] = None) -> str:
    zones = build_zones(country, rows, cols)
    feat = []
    for z in zones:
        min_la, max_la, min_lo, max_lo = z["bbox"]
        coords = [[min_lo, min_la], [min_lo, max_la], [max_lo, max_la], [max_lo, min_la], [min_lo, min_la]]
        feat.append({"type":"Feature","properties":{"id": z["id"], "name": z["name"]},
                     "geometry":{"type":"Polygon","coordinates":[coords]}})
    fc = {"type":"FeatureCollection","features":feat}
    if not out_path:
        out_path = os.path.join(os.getcwd(), f"zones_{country}.geojson")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False)
    return out_path

# ================== PARSERS ==================
def parse_lat_lng_from_text(text: str):
    m2 = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", text)
    if m2: return float(m2.group(1)), float(m2.group(2))
    m = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", text)
    if m: return float(m.group(1)), float(m.group(2))
    m3 = re.search(r"(-?\d+\.\d+),\s*(-?\d+\.\d+)", text)
    if m3:
        la = float(m3.group(1)); lo = float(m3.group(2))
        if -90<=la<=90 and -180<=lo<=180: return la, lo
    return None, None

def extract_place_id_from_url(url: str):
    if not url: return None
    m = re.search(r"(?:[?&]q=)?place_id:([^&/#]+)", url)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"!1s([^!/&?#]+)", url)
    if m2 and len(m2.group(1)) > 10 and "http" not in m2.group(1):
        return m2.group(1).strip()
    return None

def qplus(q: str): return "+".join([x for x in q.split(",")[0].split() if x])

# ================== PAGE HELPERS + WATCHDOG ==================
def accept_consent(driver):
    try:
        btns = driver.find_elements(By.XPATH, "//button[contains(., 'أوافق') or contains(., 'I agree') or contains(., 'Accept all')]")
        if btns:
            btns[0].click(); time.sleep(0.4)
    except Exception: pass

def ensure_single_tab(driver):
    try:
        handles = driver.window_handles
        current = driver.current_window_handle
        for h in handles:
            if h != current:
                driver.switch_to.window(h)
                try: driver.close()
                except Exception: pass
        driver.switch_to.window(current)
    except Exception:
        pass

def open_maps_home(driver, host, hl, gl):
    driver.get(f"https://{host}/maps?hl={hl}&gl={gl}")
    accept_consent(driver)
    ensure_single_tab(driver)

def open_search(driver, host, query, lat, lng, hl, gl, zoom):
    url = f"https://{host}/maps/search/{qplus(query)}/@{lat},{lng},{zoom}z?hl={hl}&gl={gl}"
    driver.get(url); accept_consent(driver); ensure_single_tab(driver)

def wait_results_panel(driver: webdriver.Chrome, timeout: int = 12):
    WebDriverWait(driver, timeout).until(
        EC.any_of(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]')),
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[aria-label]'))
        )
    )

def force_type_query(driver, text):
    try:
        cands = driver.find_elements(By.CSS_SELECTOR, "input[aria-label*='البحث'], input[aria-label*='Search']")
        if cands:
            inp = cands[0]; inp.clear(); inp.send_keys(text); time.sleep(0.2); inp.send_keys(Keys.ENTER); return True
    except Exception: pass
    return False

def get_results_count(driver) -> int:
    try:
        return len(driver.find_elements(By.CSS_SELECTOR, "div[role='article'], div[jsaction*='mouseover:pane']"))
    except Exception:
        return 0

def get_perf_count(driver) -> int:
    try:
        return int(driver.execute_script("return performance.getEntriesByType('resource').length || 0;"))
    except Exception:
        return 0

def is_page_frozen(start_ts: float, last_dom: int, cur_dom: int, last_perf: int, cur_perf: int) -> bool:
    if (time.time() - start_ts) < 3:  # ادّيها فرصة في الأول
        return False
    # لا DOM ولا Resources بتتغير + عدى FREEZE_MAX_SEC
    frozen = (cur_dom == last_dom) and (cur_perf == last_perf) and ((time.time() - start_ts) >= FREEZE_MAX_SEC)
    return frozen

def hard_recover(driver, host, hl, gl):
    # وقف التحميل + تفريغ + رجوع
    try:
        driver.execute_cdp_cmd("Page.stopLoading", {})
    except Exception:
        try: driver.execute_script("window.stop();")
        except Exception: pass
    try:
        driver.get("about:blank"); time.sleep(0.5)
    except Exception: pass
    try:
        open_maps_home(driver, host, hl, gl)
    except Exception:
        pass

# ================== CHROME / DRIVER ==================
def make_driver(headless: bool = True, lang: str = "ar") -> webdriver.Chrome:
    chrome_options = Options()
    if headless: chrome_options.add_argument("--headless=new")
    chrome_options.page_load_strategy = "eager"
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1440,1100")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-default-browser-check")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--lang=" + lang)
    chrome_options.add_argument("--disable-features=InfiniteSessionRestore,TranslateUI")
    chrome_options.add_argument("--disable-notifications")
    show_tiles = JOBS.get('CURRENT_SHOW_TILES', False)
    if not show_tiles:
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    prefs = {
        "intl.accept_languages": lang,
        "profile.default_content_setting_values.geolocation": 1,
        "profile.managed_default_content_settings.images": 1 if show_tiles else 2,
        "profile.managed_default_content_settings.plugins": 2,
        "profile.managed_default_content_settings.notifications": 2,
        "profile.managed_default_content_settings.media_stream": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    service = ChromeService()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(25)
    return driver

def set_cdp_geolocation(driver: webdriver.Chrome, lat: float, lng: float, accuracy: float = 50):
    params = {"latitude": lat, "longitude": lng, "accuracy": accuracy}
    try: driver.execute_cdp_cmd("Emulation.setGeolocationOverride", params)
    except Exception: driver.execute("Emulation.setGeolocationOverride", params)

# ================== INPUTS (AREAS + KEYWORDS) ==================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "admin")

def _load_list(csv_name: str) -> List[str]:
    p = os.path.join(DATA_DIR, csv_name)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            v = line.strip().strip(",")
            if v: out.append(v)
    return out

def _expand_with_suffixes(base_names: List[str], suffixes: List[str]) -> List[str]:
    out = []
    for n in base_names:
        for s in suffixes:
            out.append(f"{n}{s}")
    return out

def build_admin_chain(country: str) -> List[str]:
    areas: List[str] = []
    label = GCC[country]["label"]
    areas.append(label)
    preset = ADMIN.get(country, {"L1":[], "L2":[], "L3":[]})
    L1 = preset.get("L1", [])[:]
    L2 = preset.get("L2", [])[:]
    L3 = preset.get("L3", [])[:]
    L1 += _load_list(f"{country}_L1.csv")
    L2 += _load_list(f"{country}_L2.csv")
    L3 += _load_list(f"{country}_L3.csv")
    areas.extend(L1); areas.extend(L2); areas.extend(L3)
    areas.extend(_expand_with_suffixes(L1, L1_SUFFIXES_AR + L1_SUFFIXES_EN))
    areas.extend(_expand_with_suffixes(L2, L2_SUFFIXES_AR + L2_SUFFIXES_EN))
    if L3:
        areas.extend(_expand_with_suffixes(L3, L3_SUFFIXES_AR + L3_SUFFIXES_EN))
    def _combo(base_list: List[str], suffixes: List[str]):
        for n in base_list:
            for s in suffixes:
                areas.append(f"{n}{s}")
    _combo(L1, [" مدينة"," حي"," قرية"," نجع"," مركز"," بلدية"," city"," district"," village"," neighborhood"])
    _combo(L2, [" حي"," قرية"," نجع"," بلدية"," neighborhood"," village"])
    if L3:
        _combo(L3, [" حي"," قرية"," نجع"," حارة"," شارع"," neighborhood"," street"," alley"])
    seen, uniq = set(), []
    for a in areas:
        k = a.strip().lower()
        if not k: continue
        if k not in seen:
            uniq.append(a.strip()); seen.add(k)
    return uniq

def build_areas_list(areas_csv: str, areas_text: str) -> List[str]:
    lst = []
    if areas_csv:
        for line in areas_csv.splitlines():
            v = line.strip().strip(",")
            if v: lst.append(v)
    for raw in (areas_text or "").split(","):
        v = raw.strip()
        if v: lst.append(v)
    seen, uniq = set(), []
    for x in lst:
        key = x.lower()
        if key not in seen:
            uniq.append(x); seen.add(key)
    return uniq

def _keywords_from_inputs(keywords_inline: List[str]) -> List[str]:
    base = []
    if UPLOADED_KEYWORDS:
        base.extend([k for k in UPLOADED_KEYWORDS if k.strip()])
    if keywords_inline:
        base.extend([k for k in keywords_inline if k.strip()])
    if not base:
        base = ALL_MAP_SERVICES[:]
    seen, uniq = set(), []
    for k in base:
        kk = k.strip()
        if not kk: continue
        low = kk.lower()
        if low in seen: continue
        uniq.append(kk); seen.add(low)
    return uniq

# ================== STATE / DEDUP ==================
def _safe_quit(driver):
    try: driver.quit()
    except Exception: pass

def _recycle_driver(headless=True, lang='ar'):
    try: return make_driver(headless=headless, lang=lang)
    except Exception:
        time.sleep(1.0)
        return make_driver(headless=headless, lang=lang)

def state_path(job_id: str) -> str: return os.path.join(os.getcwd(), f"state_{job_id}.json")

def save_state(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
        if not job: return
        to_dump = {}
        for k,v in job.items():
            if k in ("drivers",): continue
            if isinstance(v, set): to_dump[k] = list(v)
            else: to_dump[k] = v
        with open(state_path(job_id), "w", encoding="utf-8") as f:
            json.dump(to_dump, f, ensure_ascii=False)

def load_state(job_id: str):
    p = state_path(job_id)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "done_points" in d and isinstance(d["done_points"], list):
                d["done_points"] = set(d["done_points"])
            if "seen_place_ids" in d and isinstance(d["seen_place_ids"], list):
                d["seen_place_ids"] = set(d["seen_place_ids"])
            if "seen_coords" in d and isinstance(d["seen_coords"], list):
                d["seen_coords"] = set(d["seen_coords"])
            return d
    return None

def _to_float(v):
    try:
        return float(str(v).strip().replace(" ", "").replace(",", "."))
    except Exception:
        return None

def _coord_key(lat, lng, precision=6):
    if lat is None or lng is None: return None
    try:
        return f"{round(float(lat), precision):.{precision}f}|{round(float(lng), precision):.{precision}f}"
    except Exception:
        return None

def _seed_seen_sets(job_id: str):
    job = JOBS.get(job_id) or {}
    data = job.get("data") or []
    seen_pid = job.setdefault("seen_place_ids", set())
    seen_xy = job.setdefault("seen_coords", set())
    if isinstance(seen_pid, list): seen_pid = set(seen_pid)
    if isinstance(seen_xy, list):  seen_xy  = set(seen_xy)
    for r in data:
        pid = r.get("place_id") or extract_place_id_from_url(r.get("place_url","") or r.get("url",""))
        if pid: seen_pid.add(str(pid).strip())
        la = _to_float(r.get("lat") or r.get("latitude") or r.get("y"))
        ln = _to_float(r.get("lng") or r.get("lon") or r.get("longitude") or r.get("x") or r.get("long"))
        ck = _coord_key(la, ln)
        if ck: seen_xy.add(ck)
    JOBS[job_id]["seen_place_ids"] = seen_pid
    JOBS[job_id]["seen_coords"] = seen_xy

def _already_seen(job_id: str, pid: str, lat, lng) -> bool:
    job = JOBS.get(job_id) or {}
    seen_pid = job.get("seen_place_ids") or set()
    seen_xy = job.get("seen_coords") or set()
    if pid and (pid in seen_pid): return True
    ck = _coord_key(lat, lng)
    if ck and (ck in seen_xy): return True
    return False

def _mark_seen(job_id: str, pid: str, lat, lng):
    job = JOBS.get(job_id) or {}
    sp = job.setdefault("seen_place_ids", set())
    sx = job.setdefault("seen_coords", set())
    if pid: sp.add(pid)
    ck = _coord_key(lat, lng)
    if ck: sx.add(ck)
    JOBS[job_id] = job

# ================== CPU THROTTLE ==================
def _cpu_sleep_hint() -> float:
    try:
        tgt = int(os.getenv("CPU_TARGET", str(JOBS.get("_cpu_target_", 75))))
    except Exception:
        tgt = 75
    return max(0.0, (90 - max(30, min(90, tgt))) * 0.002)

# ================== WORKER ==================
def worker_run(job_id: str, slice_indexes: list, grid: list, country: str,
               keywords_inline: list, areas: list, headless: bool, host: str,
               hl: str, gl: str, aggressive: bool, zoom: int):
    JOBS['CURRENT_SHOW_TILES'] = JOBS.get(job_id, {}).get('show_tiles', False)

    net_fail_streak = 0
    retries_left = 2
    driver = make_driver(headless=headless, lang="ar")
    try:
        while True:
            try:
                for origin in [f"https://{host}", "http://localhost:5000", "http://127.0.0.1:5000"]:
                    try: driver.execute_cdp_cmd("Browser.grantPermissions", {"origin":origin, "permissions":["geolocation"]})
                    except Exception: pass
                open_maps_home(driver, host, hl, gl)
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                break
            except Exception:
                retries_left -= 1
                if retries_left < 0:
                    _safe_quit(driver)
                    driver = _recycle_driver(headless=headless, lang="ar")
                else:
                    time.sleep(1.0)

        time.sleep(0.2)
        stall_count = 0
        last_rows_seen = JOBS.get(job_id, {}).get('rows', 0)
        queries_since_refresh = 0

        admin_auto = JOBS.get(job_id, {}).get('admin_sweep', True)
        admin_areas = build_admin_chain(country) if admin_auto else []
        user_areas = (areas if areas else [""])
        area_list = (admin_areas + user_areas) or [""]

        with LOCK:
            _seed_seen_sets(job_id)

        for gi in slice_indexes:
            with LOCK:
                cmd = JOBS[job_id].get("command")
                if cmd == "pause":
                    JOBS[job_id]["status"] = "paused"; save_state(job_id); return
                if gi in JOBS[job_id]["done_points"]:
                    continue
                cap = int(JOBS[job_id].get("max_rows", 0) or 0)
                if cap and JOBS[job_id].get("rows", 0) >= cap:
                    JOBS[job_id]["status"] = "done_cap"; save_state(job_id); return

            lat, lng = grid[gi]
            set_cdp_geolocation(driver, lat, lng)
            kws = _keywords_from_inputs(keywords_inline)

            for area in area_list:
                queries_since_refresh += 1
                for kw in kws:
                    time.sleep(_cpu_sleep_hint())

                    with LOCK:
                        cap = int(JOBS[job_id].get("max_rows", 0) or 0)
                        if cap and JOBS[job_id].get("rows", 0) >= cap:
                            JOBS[job_id]["status"] = "done_cap"; save_state(job_id); return

                    query = (area + " " + kw).strip()

                    # ====== تنفيذ الاستعلام مع مراقبة تجمّد ======
                    start_ts = time.time()
                    last_dom = get_results_count(driver)
                    last_perf = get_perf_count(driver)
                    try_count = 0

                    while True:
                        try:
                            open_search(driver, host, query, lat, lng, hl, gl, zoom)
                            try:
                                wait_results_panel(driver, 10)
                            except Exception:
                                force_type_query(driver, query)
                                wait_results_panel(driver, 12)

                            # Scroll + مراقبة
                            container = None
                            cands = driver.find_elements(By.CSS_SELECTOR, 'div[role="feed"]')
                            if cands: container = cands[0]
                            stable_hits, last_count = 0, -1

                            while True:
                                # خروج بالمراقبة الزمنية
                                cur_dom = get_results_count(driver)
                                cur_perf = get_perf_count(driver)

                                if is_page_frozen(start_ts, last_dom, cur_dom, last_perf, cur_perf):
                                    raise TimeoutException("page_frozen")

                                if (time.time() - start_ts) > MAX_QUERY_TIME:
                                    raise TimeoutException("query_timeout")

                                # Scroll خطوة
                                try:
                                    more = driver.find_elements(By.XPATH, "//button//span[contains(., 'المزيد') or contains(., 'More')]")
                                    if more: more[0].click(); time.sleep(0.25)
                                except Exception: pass
                                try:
                                    if container: driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", container)
                                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                except Exception:
                                    try: driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
                                    except Exception: pass

                                time.sleep(0.14 if aggressive else 0.18)
                                cards2 = get_results_count(driver)
                                cur2 = cards2
                                if cur2 <= last_count: stable_hits += 1
                                else: stable_hits, last_count = 0, cur2
                                if stable_hits >= 2:  # وصلنا للنهاية الظاهرة
                                    break

                                last_dom, last_perf = cur_dom, cur_perf

                            # جلب البطاقات
                            cards = driver.find_elements(By.CSS_SELECTOR, "div[role='article'], div[jsaction*='mouseover:pane']")
                            net_fail_streak = 0
                            break  # نجحنا نطلع Cards

                        except (WebDriverException, TimeoutException) as e:
                            try_count += 1
                            net_fail_streak += 1

                            if isinstance(e, TimeoutException) and str(e).startswith("page_frozen"):
                                # إنقاذ قاسي ثم إعادة المحاولة لنفس الكويري
                                hard_recover(driver, host, hl, gl)
                                if try_count <= 2:
                                    start_ts = time.time()
                                    last_dom = get_results_count(driver)
                                    last_perf = get_perf_count(driver)
                                    continue

                            if net_fail_streak >= 3 or try_count >= 2:
                                # إعادة إنشاء المتصفح بالكامل
                                _safe_quit(driver)
                                driver = _recycle_driver(headless=headless, lang='ar')
                                try:
                                    for origin in [f"https://{host}", "http://localhost:5000", "http://127.0.0.1:5000"]:
                                        try: driver.execute_cdp_cmd("Browser.grantPermissions", {"origin":origin, "permissions":["geolocation"]})
                                        except Exception: pass
                                    open_maps_home(driver, host, hl, gl)
                                except Exception:
                                    pass
                                # محاولة أخيرة للكويري نفسه
                                if try_count < 3:
                                    start_ts = time.time()
                                    last_dom = get_results_count(driver)
                                    last_perf = get_perf_count(driver)
                                    continue
                                else:
                                    cards = []  # سيبها فاضية ونكمل للكويري التالي
                                    break
                            else:
                                # إنقاذ خفيف
                                hard_recover(driver, host, hl, gl)
                                start_ts = time.time()
                                last_dom = get_results_count(driver)
                                last_perf = get_perf_count(driver)
                                continue

                    # ====== دمج النتائج ======
                    with LOCK:
                        data = JOBS[job_id].setdefault("data", [])
                        for card in cards:
                            try:
                                a = card.find_element(By.CSS_SELECTOR, "a[aria-label]")
                                name = a.get_attribute("aria-label").strip()
                                link = a.get_attribute("href") or ""
                            except Exception:
                                continue
                            if not name: 
                                continue
                            la, lo = parse_lat_lng_from_text(link)
                            if la is None or lo is None: 
                                continue
                            if not in_bounds(la, lo, country): 
                                continue
                            pid = extract_place_id_from_url(link)
                            if _already_seen(job_id, pid, la, lo): 
                                continue
                            rec = {"country": GCC[country]["label"], "service": kw, "name": name, "lat": la, "lng": lo}
                            if pid: rec["place_id"] = pid
                            if link: rec["place_url"] = link
                            data.append(rec)
                            _mark_seen(job_id, pid, la, lo)
                            if (len(data) % 100) == 0:
                                try: pd.DataFrame(data).to_csv(JOBS[job_id]["csv"], index=False, encoding="utf-8-sig")
                                except Exception: pass
                        JOBS[job_id]["rows"] = len(data)

                    # إدارة الركود/التحديث الدوري
                    cur_rows = JOBS.get(job_id, {}).get('rows', 0)
                    if cur_rows <= last_rows_seen: stall_count += 1
                    else: stall_count = 0; last_rows_seen = cur_rows
                    if stall_count >= STALL_RESETS or queries_since_refresh >= REFRESH_EVERY_QS:
                        _safe_quit(driver); driver = _recycle_driver(headless=headless, lang='ar')
                        try:
                            for origin in [f"https://{host}", "http://localhost:5000", "http://127.0.0.1:5000"]:
                                try: driver.execute_cdp_cmd("Browser.grantPermissions", {"origin":origin, "permissions":["geolocation"]})
                                except Exception: pass
                            open_maps_home(driver, host, hl, gl)
                        except Exception: pass
                        stall_count = 0; queries_since_refresh = 0

            with LOCK:
                JOBS[job_id]["done_points"].add(gi)
                exp_tot = int(JOBS[job_id].get("expected_total", 0) or 0)
                JOBS[job_id]["total"] = exp_tot if exp_tot > 0 else len(grid)
                JOBS[job_id]["progress"] = len(JOBS[job_id]["done_points"])
                JOBS[job_id]["status"] = "running"; save_state(job_id)

    except Exception as e:
        with LOCK:
            JOBS[job_id]["status"] = "paused_err"
            JOBS[job_id]["last_error"] = f"worker_crashed: {type(e).__name__}: {e}"
            save_state(job_id)
    finally:
        _safe_quit(driver)

# ================== RUN JOB (يدعم الزونات) ==================
def run_job(job_id: str, country: str, keywords_inline: list, step_deg: float,
            headless: bool, out_csv: str, areas_csv_text: str = "", areas_text: str = "",
            aggressive: bool = False, workers: int = 1, zoom: int = 15,
            zones_grid: Tuple[int,int] = (4,4), zones_select: Optional[List[str]] = None,
            zones_geojson_out: Optional[str] = None):
    meta = GCC[country]
    full_grid = build_grid(country, step_deg=step_deg, aggressive=aggressive)
    total_points = len(full_grid)

    rows, cols = zones_grid
    zones = build_zones(country, rows, cols)
    if zones_geojson_out:
        try: export_zones_geojson(country, rows, cols, zones_geojson_out)
        except Exception: pass

    if zones_select:
        slice_indices = filter_grid_by_zones(full_grid, zones, zones_select)
    else:
        slice_indices = list(range(total_points))

    areas = build_areas_list(areas_csv_text, areas_text)
    prev = load_state(job_id)
    total = len(slice_indices)

    if prev:
        JOBS[job_id] = prev
        JOBS[job_id]["csv"] = out_csv or JOBS[job_id].get("csv") or os.path.join(os.getcwd(), f"results_{country}_{job_id}.csv")
        JOBS[job_id].setdefault("data", [])
        JOBS[job_id].setdefault("done_points", set())
        _seed_seen_sets(job_id)
        if not JOBS[job_id]["done_points"] and JOBS[job_id].get("progress",0) > 0:
            p = min(JOBS[job_id]["progress"], total)
            JOBS[job_id]["done_points"] = set(slice_indices[:p])
        JOBS[job_id]["total"] = int(JOBS[job_id].get("expected_total", 0) or total)
        JOBS[job_id]["country"] = country
        JOBS[job_id]["keywords"] = keywords_inline
        JOBS[job_id]["step"] = step_deg
        JOBS[job_id]["aggressive"] = aggressive
        JOBS[job_id]["workers"] = workers
        JOBS[job_id]["zoom"] = zoom
        JOBS[job_id]["areas"] = ",".join(areas)
    else:
        JOBS[job_id] = {
            "status":"running","progress":0,"total":int(JOBS.get(job_id,{}).get("expected_total",0) or total),
            "rows":0,"csv":out_csv,
            "data":[], "country":country, "keywords":keywords_inline, "step":step_deg,
            "command":"", "aggressive":aggressive, "workers":workers, "zoom":zoom,
            "done_points": set(), "areas": ",".join(areas), "admin_sweep": True
        }
        _seed_seen_sets(job_id)

    JOBS['CURRENT_SHOW_TILES'] = JOBS[job_id].get('show_tiles', False)
    JOBS[job_id]["max_rows"] = int(JOBS[job_id].get("max_rows", 0) or 0)
    JOBS[job_id]["expected_total"] = int(JOBS[job_id].get("expected_total", 0) or 0)

    indices = slice_indices
    workers = max(1, int(workers))
    slices = [indices[i::workers] for i in range(workers)]

    def _launch_round():
        threads = []
        for wi in range(workers):
            t = threading.Thread(
                target=worker_run,
                args=(job_id, slices[wi], full_grid, country, keywords_inline, areas, headless,
                      meta["host"], meta["hl"], meta["gl"], aggressive, zoom),
                daemon=True
            )
            threads.append(t); t.start()
        for t in threads: t.join()

    while True:
        _launch_round()
        status = JOBS[job_id].get("status")
        if status == "paused_net":
            time.sleep(5); continue
        if status == "done_cap": break
        if status in ("paused","paused_err"): break
        break

    if JOBS[job_id].get("status") not in ("paused","paused_net","paused_err"):
        df = pd.DataFrame(JOBS[job_id]["data"])
        if not df.empty:
            if "place_id" in df.columns and df["place_id"].notna().any():
                df.sort_values(by=["place_id","name"], inplace=True)
                df.drop_duplicates(subset=["place_id"], inplace=True)
            else:
                df.drop_duplicates(subset=["name","lat","lng"], inplace=True)
            try: df.to_csv(JOBS[job_id]["csv"], index=False, encoding="utf-8-sig")
            except Exception: pass
            try:
                xlsx_path = JOBS[job_id]["csv"].replace(".csv",".xlsx")
                with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
                    df.to_excel(xw, index=False)
            except Exception: pass
        else:
            try: open(JOBS[job_id]["csv"], "w", encoding="utf-8").write("")
            except Exception: pass
        JOBS[job_id]["status"] = "done"; save_state(job_id)
    else:
        save_state(job_id)
