# spawnverse/apis/registry.py
from ..display import _log

# Injected once per agent, before any API function — provides sqlite-backed
# cache so parallel agents don't each hammer the same endpoint and get 429d.
_CACHE_CODE = """\
def _api_cache_get(key, max_age=120):
    try:
        c=_c(); row=c.execute("SELECT value,stored_at FROM memory WHERE namespace='_cache_' AND key=?",(key,)).fetchone(); c.close()
        if row:
            age=(datetime.now()-datetime.fromisoformat(row[1])).total_seconds()
            if age<max_age: return json.loads(row[0])
    except: pass
    return None
def _api_cache_set(key,value):
    try:
        c=_c(); c.execute("INSERT OR REPLACE INTO memory VALUES (?,?,?,?)",('_cache_',key,json.dumps(value),datetime.now().isoformat())); c.commit(); c.close()
    except: pass"""

_API_REGISTRY: dict = {
    "weather": {
        "keywords": ["weather", "temperature", "climate", "forecast", "rain", "snow", "sunny"],
        "hint": "get_weather('Mumbai') → {'temp_c':'31','feels_like':'35','humidity':'80','wind_kmph':'14','desc':'Sunny'} — city name only, no extra args",
        "code": """
def get_weather(city, **_):
    import urllib.request as _r, urllib.parse as _p, json as _j
    cached = _api_cache_get(f'weather_{city}')
    if cached is not None: return cached
    try:
        url = f'https://wttr.in/{_p.quote(str(city))}?format=j1'
        with _r.urlopen(_r.Request(url, headers={'User-Agent':'sv/1'}), timeout=8) as r:
            d = _j.loads(r.read())
        c = d.get('current_condition',[{}])[0]
        result = {'temp_c':c.get('temp_C'),'feels_like':c.get('FeelsLikeC'),
                'humidity':c.get('humidity'),'wind_kmph':c.get('windspeedKmph'),
                'desc':c.get('weatherDesc',[{}])[0].get('value')}
        _api_cache_set(f'weather_{city}', result)
        return result
    except Exception as e: vlog('API_WEATHER_FAIL',str(e)); return None
""",
    },
    "forex": {
        "keywords": ["exchange rate", "forex", "currency", "convert", "inr", "usd", "eur", "jpy", "aed"],
        "hint": "get_rate('USD','INR') → ~84.5  OR  get_rate('INR','USD') → ~0.012  — returns TARGET units per 1 BASE unit. Use get_rate('USD','INR') to get INR per dollar.",
        "code": """
def get_rate(base, target):
    import urllib.request as _r, json as _j
    cache_key = f'rate_{base}_{target}'
    cached = _api_cache_get(cache_key)
    if cached is not None: return cached
    try:
        url = f'https://open.er-api.com/v6/latest/{base}'
        with _r.urlopen(_r.Request(url, headers={'User-Agent':'sv/1'}), timeout=8) as r:
            d = _j.loads(r.read())
        rate = d.get('rates',{}).get(target)
        result = round(float(rate), 6) if rate else None
        if result is not None: _api_cache_set(cache_key, result)
        return result
    except Exception as e: vlog('API_FOREX_FAIL',str(e)); return None
""",
    },
    "country": {
        "keywords": ["country", "nation", "capital", "population", "language", "region"],
        "hint": "get_country(name) → {name, capital, population, region, languages}  WARNING: use 'America' for USA (not 'United States' — returns Virgin Islands). Use exact names: 'Japan', 'UAE', 'Germany'.",
        "code": """
def get_country(name):
    import urllib.request as _r, urllib.parse as _p, json as _j
    cached = _api_cache_get(f'country_{name}')
    if cached is not None: return cached
    try:
        url = f'https://restcountries.com/v3.1/name/{_p.quote(str(name))}'
        with _r.urlopen(_r.Request(url, headers={'User-Agent':'sv/1'}), timeout=8) as r:
            d = _j.loads(r.read())
        c = d[0] if isinstance(d,list) else d
        result = {'name':c.get('name',{}).get('common'),'capital':c.get('capital',[''])[0],
                'population':c.get('population'),'region':c.get('region'),
                'languages':list(c.get('languages',{}).values())[:4]}
        _api_cache_set(f'country_{name}', result)
        return result
    except Exception as e: vlog('API_COUNTRY_FAIL',str(e)); return None
""",
    },
    "crypto": {
        "keywords": ["bitcoin", "ethereum", "crypto", "btc", "eth", "blockchain", "token", "coin"],
        "hint": "get_crypto('BTC') → {'usd': 95000.0, 'inr': 7900000.0} — access via result['usd'] or result['inr'], NOT result['price']",
        "code": """
def get_crypto(symbol='BTC'):
    import urllib.request as _r, json as _j, time as _t
    COINS = {'BTC':'bitcoin','ETH':'ethereum','SOL':'solana','BNB':'binancecoin'}
    coin_id = COINS.get(symbol.upper(), symbol.lower())
    cached = _api_cache_get(f'crypto_{symbol.upper()}')
    if cached is not None: return cached
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd,inr'
    for _attempt in range(5):
        try:
            with _r.urlopen(_r.Request(url, headers={'User-Agent':'sv/1'}), timeout=8) as r:
                d = _j.loads(r.read())
            result = d.get(coin_id)
            if result: _api_cache_set(f'crypto_{symbol.upper()}', result)
            return result
        except Exception as e:
            err = str(e)
            if '429' in err or 'Too Many' in err:
                wait = 2 ** _attempt
                vlog('API_CRYPTO_FAIL', f'{err} — retry in {wait}s')
                _t.sleep(wait)
                cached = _api_cache_get(f'crypto_{symbol.upper()}')
                if cached is not None: return cached
                continue
            vlog('API_CRYPTO_FAIL', err); return None
    vlog('API_CRYPTO_FAIL', 'max retries exceeded'); return None
""",
    },
    "news": {
        "keywords": ["news", "latest", "headlines", "article", "breaking"],
        "hint": "get_news() → [{title, url, score}, ...]",
        "code": """
def get_news(topic=None):
    import urllib.request as _r, json as _j
    try:
        url = 'https://hacker-news.firebaseio.com/v0/topstories.json'
        with _r.urlopen(url, timeout=8) as r:
            ids = _j.loads(r.read())[:8]
        stories = []
        for sid in ids[:5]:
            with _r.urlopen(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=5) as r:
                item = _j.loads(r.read())
            stories.append({'title':item.get('title'),'url':item.get('url'),'score':item.get('score')})
        return stories
    except Exception as e: vlog('API_NEWS_FAIL',str(e)); return []
""",
    },
}


_AUTO_SKIP = {
    # HackerNews returns generic tech stories — never domain-specific EV/finance news.
    # Enable explicitly via external_apis: ["news"] if you want it.
    "news",
}


def detect_needed_apis(task_desc: str, config: dict, client) -> list:
    setting = config.get("external_apis", False)
    if setting is False:
        return []
    if isinstance(setting, list):
        return [k for k in setting if k in _API_REGISTRY]
    if setting is True:
        task_lower = task_desc.lower()
        matched    = [name for name, info in _API_REGISTRY.items()
                      if name not in _AUTO_SKIP
                      and any(kw in task_lower for kw in info["keywords"])]
        if matched:
            _log("API", "AUTO", "DETECTED FROM KEYWORDS", str(matched), "C")
        return matched
    return []


def build_api_stdlib(api_names: list, api_keys: dict = None) -> str:
    if not api_names:
        return ""
    parts = [
        "\n# ── External API Helpers (auto-injected by SpawnVerse) ─────────",
        _CACHE_CODE,  # shared cache helpers — always first
    ]
    hints = []
    for name in api_names:
        if name in _API_REGISTRY:
            parts.append(_API_REGISTRY[name]["code"].strip())
            hints.append(_API_REGISTRY[name]["hint"])
    if hints:
        parts.append("\n# Available API functions:")
        for h in hints:
            parts.append(f"#   {h}")
    return "\n".join(parts)
