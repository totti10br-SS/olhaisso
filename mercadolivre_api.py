"""
Mercado Livre — via Playwright (primário) + ScrapingAnt (fallback)
Publisher ID: ot20260326074822
"""

import os
import re
import sys
import json
import random
import hashlib
import time
import requests

ML_PUBLISHER_ID = os.getenv("ML_PUBLISHER_ID", "ot20260326074822")
SCRAPINGANT_KEY  = os.getenv("SCRAPINGANT_KEY", "")
ZENROWS_KEY      = os.getenv("ZENROWS_KEY", "")       # fallback
BRIGHTDATA_KEY   = os.getenv("BRIGHTDATA_API_KEY", "") # Web Unlocker — resolve CAPTCHA

# ScraperAPI — suporta múltiplas keys: SCRAPERAPI_KEY, SCRAPERAPI_KEY2, SCRAPERAPI_KEY3...
# Se a key 1 estiver esgotada (402/403), tenta automaticamente a próxima.
def _get_scraperapi_keys():
    keys = []
    for i in range(1, 6):
        k = os.getenv(f"SCRAPERAPI_KEY{i}", "") if i > 1 else os.getenv("SCRAPERAPI_KEY", "")
        if k:
            keys.append(k)
    return keys

SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY", "")   # mantido para compatibilidade
PRECO_MINIMO    = float(os.getenv("PRECO_MINIMO", "50.00"))
PRECO_MAXIMO    = float(os.getenv("PRECO_MAXIMO", "3000.00"))
DESCONTO_MINIMO = int(os.getenv("DESCONTO_MINIMO", "20"))

URLS_BUSCA = [
    ("https://lista.mercadolivre.com.br/notebooks-acessorios", "Notebooks"),
    ("https://lista.mercadolivre.com.br/celulares-smartphones", "Smartphones"),
    ("https://lista.mercadolivre.com.br/televisores", "TVs"),
    ("https://lista.mercadolivre.com.br/video-games-controles", "Controles"),
    ("https://lista.mercadolivre.com.br/video-games-consoles", "Consoles"),
    ("https://lista.mercadolivre.com.br/video-games-jogos", "Jogos"),
    ("https://lista.mercadolivre.com.br/fones-ouvido-headsets", "Fones"),
    ("https://lista.mercadolivre.com.br/monitores-telas", "Monitores"),
]

PALAVRAS_BLOQUEADAS = [
    # Ferramentas e equipamentos industriais
    "guincho", "girafa", "talha", "macaco hidraulico", "compressor",
    "furadeira", "parafusadeira", "martelo", "serra", "esmerilhadeira",
    "retifica", "lixadeira", "soldador", "solda", "torno",
    "andaime", "escada", "carrinho de mao", "empilhadeira",
    # Iluminação não-tech / cenografia
    "lente de projecao", "lente spot", "filtro efeito", "gobo",
    "refletor par", "moving head", "beam", "follow spot",
    "canhao de luz", "strobo", "maquina de fumaca",
    # Automotivo
    "pneu", "rodas", "amortecedor", "escapamento", "farol",
    "retrovisor", "para-choque", "capota", "banco de carro",
    # Casa e jardim
    "cortador de grama", "vaso de planta", "mangueira",
    "churrasqueira", "fogueira", "fogao", "geladeira", "lava-roupa",
    "maquina de lavar", "secadora", "lava-loucas",
    "sofa", "colchao", "cama", "guarda-roupa", "estante",
    "tapete", "cortina", "persiana", "luminaria de teto",
    # Vestuário e moda
    "roupa", "roupas", "vestido", "camisa", "camiseta", "blusa",
    "calca", "bermuda", "short", "saia", "jaqueta", "casaco",
    "sapato", "tenis", "sandalia", "chinelo", "bota",
    "bolsa", "mochila", "mala", "carteira", "cinto",
    # Brinquedos e esportes
    "bola de futebol", "bola gigante", "brinquedo", "brinquedos",
    "boneca", "carrinho de brinquedo", "lego",
    "bicicleta", "patins", "skate", "patinete infantil",
    # Saúde e beleza
    "suplemento", "creatina", "whey protein", "vitamina",
    "remedio", "medicamento", "termometro clinico",
    "perfume", "fragrancia", "eau de parfum", "colonia",
    "shampoo", "condicionador", "creme", "hidratante",
    "maquiagem", "batom", "base", "sombra", "rimel",
    # Optica / astronomia não-tech
    "telescopio", "telescópio", "luneta", "microscopio",
    # Animais
    "racao", "casinha de cachorro", "aquario", "gaiola",
    # Livros e papelaria
    "livro", "album de figurinha", "figurinha",
    "caderno", "agenda", "caneta", "lapis",
]


def log(msg):
    print(msg, flush=True)
    sys.stdout.flush()


# Palavras que DEVEM aparecer em produtos tech (se não tiver nenhuma, bloqueia)
PALAVRAS_TECH = [
    "notebook", "laptop", "pc", "computador", "desktop",
    "celular", "smartphone", "iphone", "samsung", "xiaomi", "motorola",
    "tv", "smart tv", "televisao", "televisão",
    "monitor", "tela", "display",
    "tablet", "ipad",
    "fone", "headset", "headphone", "earphone", "auricular", "caixa de som",
    "soundbar", "speaker",
    "teclado", "mouse", "mousepad",
    "ssd", "hd externo", "pendrive", "memoria ram", "processador",
    "placa de video", "placa mae", "gabinete", "fonte atx",
    "roteador", "repetidor wifi", "modem", "switch",
    "camera", "webcam", "impressora",
    "carregador", "cabo usb", "hub usb", "adaptador",
    "controle", "joystick", "videogame", "playstation", "xbox", "nintendo",
    "ps5", "ps4", "dualsense", "dual sense", "switch 2", "switch2",
    "jogo ps5", "jogo xbox", "jogo nintendo", "game ps5", "game xbox",
    "headset gamer", "fone gamer", "console gamer",
    "smartwatch", "relogio inteligente",
    "drone", "gopro", "action cam",
    "power bank", "nobreak", "estabilizador",
    "ar condicionado", "ventilador tower", "purificador de ar",
    "fritadeira air fryer", "cafeteira", "liquidificador",
]

def produto_valido(nome):
    nome_lower = nome.lower()
    # Verifica palavras bloqueadas
    for p in PALAVRAS_BLOQUEADAS:
        if p in nome_lower:
            log(f"  🚫 Bloqueado ({p}): {nome[:50]}")
            return False
    return True

def produto_e_tech(nome):
    """Verifica se o produto tem ao menos uma palavra-chave tech."""
    nome_lower = nome.lower()
    for p in PALAVRAS_TECH:
        if p in nome_lower:
            return True
    return False


def gerar_link_afiliado(url):
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}matt_tool={ML_PUBLISHER_ID}"


TINYURL_API_TOKEN = os.getenv("TINYURL_API_TOKEN", "5E6O0b6FW8c5FDRCSjjo1TBl4VO0JtmUwgDgtVr7opF1vCMzdu5NCD1f7T5k")

def encurtar_link(url_longa):
    # Tenta TinyURL com token (API autenticada)
    if TINYURL_API_TOKEN:
        try:
            r = requests.post(
                "https://api.tinyurl.com/create",
                headers={
                    "Authorization": f"Bearer {TINYURL_API_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"url": url_longa, "domain": "tinyurl.com"},
                timeout=8,
            )
            if r.status_code == 200:
                short = r.json().get("data", {}).get("tiny_url", "")
                if short.startswith("http"):
                    log(f"  🔗 TinyURL OK: {short}")
                    return short
            else:
                log(f"  ⚠️ TinyURL status {r.status_code}")
        except Exception as e:
            log(f"  ⚠️ TinyURL erro: {e}")
    # Fallback: TinyURL sem autenticação (endpoint legado)
    try:
        r2 = requests.get(
            f"https://tinyurl.com/api-create.php?url={requests.utils.quote(url_longa, safe='')}",
            timeout=8,
        )
        if r2.status_code == 200 and r2.text.startswith("http"):
            log(f"  🔗 TinyURL (legado) OK: {r2.text.strip()}")
            return r2.text.strip()
    except Exception as e:
        log(f"  ⚠️ TinyURL legado erro: {e}")
    return url_longa


def _is_captcha_html(html):
    """Detecta se o HTML retornado é página de CAPTCHA do ML."""
    if not html:
        return True

    # HTML grande (>200KB) quase certamente é página real — CAPTCHA é sempre pequeno
    # Evita falso positivo: "robot" / "Reintentar" aparecem no HTML normal do ML
    if len(html) > 200_000:
        # Ainda verifica sinais específicos de CAPTCHA que não ocorrem em página normal
        if "distil_r_captcha" in html or "cf-challenge" in html:
            return True
        return False

    # Para HTMLs pequenos: verifica sinais de CAPTCHA
    captcha_signs = ["REINTENTAR", "Reintentar", "captcha", "distil_r_captcha", "cf-challenge"]
    lower = html.lower()
    for sign in captcha_signs:
        if sign.lower() in lower:
            return True

    # HTML pequeno sem nenhuma chave de produto = página de erro/bloqueio
    if len(html) < 60000:
        tem_produto = any(f'"{k}"' in html for k in ["results", "items", "elements", "offers", "products", "deals", "card", "title", "ui-search"])
        if not tem_produto:
            return True

    return False


def _scrapingant_get(url, browser, proxy_country, timeout=90):
    """Faz uma requisição ao ScrapingAnt e retorna (status_code, html) ou (None, None) em erro."""
    params = {
        "url":       url,
        "x-api-key": SCRAPINGANT_KEY,
        "browser":   browser,
    }
    if proxy_country:
        params["proxy_country"] = proxy_country
    try:
        r = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        log(f"  ScrapingAnt erro: {e}")
        return None, None


def _url_sem_filtros(url):
    """Retorna versão da URL sem os filtros _NoIndex_ e _Discount_ (menos suspeita para o ML)."""
    # Remove tudo a partir de _OrderId_ ou _Discount_ ou _NoIndex_
    import re as _re
    url_limpa = _re.sub(r'/_Order[^"]*', '', url)
    url_limpa = _re.sub(r'/_Discount[^"]*', '', url_limpa)
    url_limpa = _re.sub(r'/_NoIndex[^"]*', '', url_limpa)
    return url_limpa.rstrip('/')


def _playwright_fetch(url, timeout_ms=45000):
    """
    Busca URL usando Playwright + Chromium headless real.
    Railway tem Chromium pré-instalado em /opt/pw-browsers/chromium
    Retorna HTML ou None se falhar.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        log("  Playwright: não instalado — pulando")
        return None

    chromium_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", os.path.expanduser("~/.cache/ms-playwright"))
    # Playwright procura o executável dentro da pasta; tenta localizar o binário
    exec_path = None
    for candidate in [
        os.path.expanduser("~/.cache/ms-playwright/chromium-headless-shell/chrome-linux/headless_shell"),
        "/opt/ms-playwright/chromium/chrome",
        "/opt/ms-playwright/chromium-headless-shell/headless_shell",
        "/opt/pw-browsers/chromium",
        "/opt/pw-browsers/chromium-headless-shell",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
    ]:
        if os.path.isfile(candidate):
            exec_path = candidate
            break
    # Se não achou caminho direto, faz glob recursivo nas pastas conhecidas
    if not exec_path:
        import glob
        search_paths = [os.path.expanduser("~/.cache/ms-playwright"), chromium_path,
                        "/opt/ms-playwright", "/opt/pw-browsers"]
        for base in search_paths:
            matches = (glob.glob(f"{base}/**/headless_shell", recursive=True) +
                       glob.glob(f"{base}/**/chrome", recursive=True) +
                       glob.glob(f"{base}/**/chromium", recursive=True) +
                       glob.glob(f"{base}/**/chromium-headless-shell", recursive=True))
            if matches:
                exec_path = matches[0]
                break

    log(f"  Playwright: executável → {exec_path or 'auto'}")

    try:
        with sync_playwright() as pw:
            launch_opts = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1920,1080",
                    "--lang=pt-BR",
                ],
            }
            if exec_path:
                launch_opts["executable_path"] = exec_path

            browser = pw.chromium.launch(**launch_opts)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                },
            )
            # Remove webdriver flag — evita detecção por JS
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            page = context.new_page()
            try:
                # Bloqueia imagens/fontes para carregar mais rápido
                page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}", lambda r: r.abort())

                log(f"  Playwright: abrindo {url[:70]}")
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                # Aguarda conteúdo principal aparecer (busca lista de produtos)
                try:
                    page.wait_for_selector(
                        ".ui-search-layout__item, .ui-search-results, #root-app",
                        timeout=15000,
                    )
                except PlaywrightTimeout:
                    log("  Playwright: seletor não encontrado — usando HTML parcial")

                html = page.content()
                log(f"  Playwright: HTML {len(html)} chars")

                if _is_captcha_html(html):
                    log("  Playwright: CAPTCHA detectado — tentando scroll")
                    # Scroll suave para simular humano
                    page.evaluate("window.scrollBy(0, 300)")
                    time.sleep(2)
                    page.evaluate("window.scrollBy(0, 600)")
                    time.sleep(2)
                    html = page.content()
                    if _is_captcha_html(html):
                        log("  Playwright: CAPTCHA persistente — falhou")
                        return None

                return html if len(html) > 10000 else None

            finally:
                try:
                    page.close()
                    context.close()
                    browser.close()
                except Exception:
                    pass

    except Exception as e:
        log(f"  Playwright erro: {e}")
        return None


def scraper_fetch(url):
    # Playwright desabilitado para ML — Railway IP blacklistado, sempre retorna CAPTCHA
    # Indo direto para Bright Data Web Unlocker
    log("  → Bright Data Web Unlocker...")

    # NOTA: ScrapingAnt e ZenRows desabilitados para ML (todos retornam CAPTCHA com IPs de datacenter)
    # Chain atual: Playwright → Bright Data Web Unlocker → ScraperAPI (rotação de keys)

    # Bright Data Web Unlocker — resolve CAPTCHA automaticamente
    if BRIGHTDATA_KEY:
        try:
            payload = {
                "zone":   "web_unlocker1",
                "url":    url,
                "format": "raw",
            }
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {BRIGHTDATA_KEY}",
            }
            r = requests.post("https://api.brightdata.com/request", json=payload, headers=headers, timeout=60)
            log(f"  BrightData WebUnlocker {r.status_code} → {url[:60]}")
            if r.status_code == 200:
                if not _is_captcha_html(r.text):
                    log(f"  BrightData ✅ {len(r.text)} chars")
                    return r.text
                log(f"  BrightData: CAPTCHA ainda presente ({len(r.text)} chars)")
            else:
                log(f"  BrightData erro: {r.text[:300]}")
        except Exception as e:
            log(f"  BrightData erro: {e}")

    # Fallback ScraperAPI — tenta múltiplas keys em sequência (SCRAPERAPI_KEY, SCRAPERAPI_KEY2, ...)
    scraperapi_keys = _get_scraperapi_keys()
    for idx, skey in enumerate(scraperapi_keys, 1):
        try:
            payload = {
                "api_key":      skey,
                "url":          url,
                "country_code": "br",
                "render":       "false",
            }
            r = requests.get("https://api.scraperapi.com", params=payload, timeout=60)
            log(f"  ScraperAPI key{idx} {r.status_code} → {url[:60]}")
            if r.status_code == 200:
                return r.text
            if r.status_code in (402, 403):
                log(f"  ScraperAPI key{idx} quota esgotada — tentando próxima key...")
                continue  # tenta próxima key
            log(f"  ScraperAPI key{idx} erro: {r.text[:100]}")
        except Exception as e:
            log(f"  ScraperAPI key{idx} erro: {e}")

    return None


def _extrair_lista_json(html, chave):
    """Tenta extrair lista JSON pela chave dentro do HTML."""
    idx = html.find(f'"{chave}":[{{')
    if idx == -1:
        idx = html.find(f'"{chave}": [{{')
    if idx == -1:
        return []
    start = html.find('[', idx)
    if start == -1:
        return []
    depth = 0
    end = start
    for i, c in enumerate(html[start:], start):
        if c == '[': depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        if i - start > 500000:
            break
    try:
        data = json.loads(html[start:end])
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    return []


def _extrair_next_data_produtos(html):
    """Extrai produtos do JSON __NEXT_DATA__ embutido no HTML (Next.js/React do ML)."""
    # Tenta <script id="__NEXT_DATA__"> primeiro
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
    if not m:
        # Fallback: window.__PRELOADED_STATE__
        m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});\s*(?:</script>|window\.)', html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []

    # Navega pela árvore JSON procurando arrays com produtos
    # ML estrutura: props.pageProps.initialState.results OU initialData.results
    def _busca_resultados(obj, depth=0):
        if depth > 8 or not isinstance(obj, (dict, list)):
            return None
        if isinstance(obj, list) and len(obj) >= 3:
            # Verifica se parece lista de produtos
            sample = obj[0] if obj else {}
            if isinstance(sample, dict):
                keys = set(sample.keys())
                if keys & {"title", "permalink", "price", "id"} and "price" in keys:
                    return obj
                if "card" in keys and isinstance(sample.get("card"), dict):
                    return obj
        if isinstance(obj, dict):
            # Chaves que geralmente contêm produtos no ML
            for key in ["results", "items", "elements", "listings", "searchResults", "products"]:
                if key in obj:
                    r = _busca_resultados(obj[key], depth + 1)
                    if r:
                        return r
            for v in obj.values():
                r = _busca_resultados(v, depth + 1)
                if r:
                    return r
        return None

    produtos = _busca_resultados(data)
    if produtos:
        log(f"  -> __NEXT_DATA__: {len(produtos)} produtos encontrados")
    return produtos or []


def extrair_produtos_html_lista(html):
    """Parser HTML direto para lista.mercadolivre.com.br — extrai produtos das tags HTML."""
    if not html or len(html) < 5000:
        return []
    produtos = []
    try:
        import html as htmllib

        # Tenta primeiro extrair do JSON __NEXT_DATA__ (ML usa Next.js)
        next_data = _extrair_next_data_produtos(html)
        if next_data and len(next_data) >= 3:
            return next_data

        # Divide o HTML em blocos por item de resultado (cada card de produto)
        # ML usa classes como ui-search-layout__item ou ui-search-result
        blocos = re.split(r'(?=<li[^>]+class="[^"]*ui-search-layout__item)', html, flags=re.IGNORECASE)
        if len(blocos) < 2:
            # Tenta split alternativo
            blocos = re.split(r'(?=<div[^>]+class="[^"]*ui-search-result[^"]*")', html, flags=re.IGNORECASE)

        if len(blocos) < 2:
            return []

        log(f"  -> HTML lista: {len(blocos)-1} blocos de produto encontrados")

        # DIAGNÓSTICO: mostra primeiro bloco real para identificar classes CSS
        if len(blocos) > 1:
            b0 = blocos[1][:600]
            log(f"  -> DIAG bloco[0]: {repr(b0)}")

        # Regex para nome — múltiplas estratégias de fallback
        nome_res = [
            re.compile(r'class="[^"]*ui-search-item__title[^"]*"[^>]*>([^<]+)<', re.IGNORECASE),
            re.compile(r'class="[^"]*poly-component__title[^"]*"[^>]*>([^<]+)<', re.IGNORECASE),
            re.compile(r'class="[^"]*item__title[^"]*"[^>]*>([^<]+)<', re.IGNORECASE),
            re.compile(r'<h2[^>]*>([^<]{10,150})</h2>', re.IGNORECASE),
            re.compile(r'<h3[^>]*>([^<]{10,150})</h3>', re.IGNORECASE),
            re.compile(r'aria-label="([^"]{10,150})"', re.IGNORECASE),
        ]
        preco_re   = re.compile(r'class="[^"]*andes-money-amount__fraction[^"]*"[^>]*>([0-9.,]+)<', re.IGNORECASE)
        centavos_re = re.compile(r'class="[^"]*andes-money-amount__cents[^"]*"[^>]*>([0-9]+)<', re.IGNORECASE)
        # Preço fallback — qualquer número grande formatado como preço BR
        preco_fallback_re = re.compile(r'R\$\s*([0-9]{2,}(?:\.[0-9]{3})*(?:,[0-9]{2})?)', re.IGNORECASE)
        desc_re    = re.compile(r'(\d+)%\s*OFF', re.IGNORECASE)
        link_re    = re.compile(r'href="(https://(?:www\.)?mercadolivre\.com\.br/[^"]+)"', re.IGNORECASE)
        img_re     = re.compile(r'(?:data-src|src)="(https://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', re.IGNORECASE)

        for bloco in blocos[1:]:  # pula primeiro bloco (cabeçalho)
            try:
                # Nome — tenta cada regex em ordem
                nome = ""
                for nre in nome_res:
                    m = nre.search(bloco)
                    if m:
                        nome = htmllib.unescape(m.group(1)).strip()
                        if nome and len(nome) >= 10:
                            break
                        nome = ""
                if not nome:
                    continue

                # Preço (pode ter parte inteira + centavos)
                precos_bloco = preco_re.findall(bloco)
                if not precos_bloco:
                    # Fallback: tenta R$ XX.XXX,XX no texto do bloco
                    precos_bloco = preco_fallback_re.findall(bloco)
                if not precos_bloco:
                    continue
                # Primeiro preço é o atual (com desconto), segundo pode ser original
                preco_txt = precos_bloco[0].replace(".", "").replace(",", ".")
                try:
                    preco = float(preco_txt)
                except Exception:
                    continue
                if preco <= 0:
                    continue

                # Centavos
                m_cents = centavos_re.search(bloco)
                if m_cents:
                    try:
                        cents = int(m_cents.group(1))
                        preco = preco + cents / 100
                    except Exception:
                        pass

                # Preço original (busca preço riscado "previous" no bloco)
                preco_orig = 0.0
                # Tenta capturar preço riscado (andes-money-amount--previous)
                m_prev = re.search(
                    r'andes-money-amount--previous[^>]*>.*?'
                    r'andes-money-amount__fraction[^>]*>([0-9][0-9.]*)',
                    bloco, re.S
                )
                if m_prev:
                    try:
                        preco_orig = float(m_prev.group(1).replace(".", "").replace(",", "."))
                    except Exception:
                        pass

                # Fallback: segundo preço na lista (se for maior que o atual)
                if preco_orig == 0.0 and len(precos_bloco) >= 2:
                    try:
                        cand = float(precos_bloco[1].replace(".", "").replace(",", "."))
                        if cand > preco:
                            preco_orig = cand
                    except Exception:
                        pass

                # Desconto
                m_desc = desc_re.search(bloco)
                desconto = int(m_desc.group(1)) if m_desc else 0
                if desconto == 0 and preco_orig > preco > 0:
                    desconto = round((1 - preco / preco_orig) * 100)

                # Se ainda sem preço original mas temos desconto, calcula de trás pra frente
                if preco_orig == 0.0 and desconto > 0:
                    try:
                        preco_orig = round(preco / (1 - desconto / 100), 2)
                    except Exception:
                        pass

                # URL
                m_link = link_re.search(bloco)
                url_prod = m_link.group(1) if m_link else ""

                # Imagem
                m_img = img_re.search(bloco)
                imagem = m_img.group(1) if m_img else ""

                produtos.append({
                    "_raw_html": True,
                    "nome": nome,
                    "preco": preco,
                    "preco_original": preco_orig if preco_orig > preco else 0,
                    "desconto": desconto,
                    "url_prod": url_prod,
                    "imagem": imagem,
                })
            except Exception:
                continue

    except Exception as e:
        log(f"  HTML lista parse erro: {e}")
    return produtos


def _itens_sao_produtos(items):
    """Verifica se a lista de itens parece conter produtos ML reais (não banners/UI)."""
    if not items:
        return False
    # Chaves que indicam produto real
    campos_produto = {"card", "title", "price", "prices", "permalink", "preco", "nome", "sale_price"}
    # Chaves que indicam elemento de UI (não produto)
    campos_ui = {"subtitle", "blog_id", "tag"}
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        chaves = set(item.keys())
        if chaves & campos_produto:
            return True
        if chaves & campos_ui and not (chaves & campos_produto):
            return False
    return False


def extrair_produtos_html(html):
    if not html:
        return []
    log(f"  -> HTML: {len(html)} chars")

    # Tenta parser HTML direto PRIMEIRO — mais confiável para lista.mercadolivre.com.br
    itens_html = extrair_produtos_html_lista(html)
    if itens_html:
        log(f"  -> {len(itens_html)} itens extraídos (parser HTML direto)")
        return itens_html

    # Tenta múltiplas chaves candidatas JSON — ML muda o formato com frequência
    CHAVES_CANDIDATAS = [
        "results", "items", "elements", "offers", "products",
        "searchResults", "itemsList", "deals", "promotions",
    ]
    for chave in CHAVES_CANDIDATAS:
        data = _extrair_lista_json(html, chave)
        if data and _itens_sao_produtos(data):
            log(f"  -> {len(data)} itens extraídos (chave JSON: '{chave}')")
            return data
        elif data:
            log(f"  -> chave '{chave}' retornou {len(data)} itens mas não são produtos (keys: {list(data[0].keys())[:5]})")

    # Fallback: procura qualquer lista grande de objetos com campo "card" ou "title"
    for kw in ['"card":{', '"card": {', '"title":{', '"title": {']:
        idx = html.find(kw)
        if idx > 0:
            # Acha o array pai
            start = html.rfind('[', 0, idx)
            if start > 0:
                depth = 0
                end = start
                for i, c in enumerate(html[start:], start):
                    if c == '[': depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                    if i - start > 500000:
                        break
                try:
                    data = json.loads(html[start:end])
                    if isinstance(data, list) and len(data) > 0 and _itens_sao_produtos(data):
                        log(f"  -> {len(data)} itens extraídos (fallback kw: '{kw}')")
                        return data
                except Exception:
                    pass

    # Debug: mostra quais chaves JSON existem no HTML para diagnóstico
    chaves_encontradas = set(re.findall(r'"(\w+)":\s*\[', html))
    log(f"  -> Nenhum produto encontrado. Chaves JSON disponíveis: {sorted(chaves_encontradas)[:30]}")
    return []


def _processar_item_next_data(item):
    """Processa item no formato direto do __NEXT_DATA__ (title/price/permalink)."""
    try:
        nome = item.get("title", "")
        if not nome:
            return None
        if not produto_valido(nome):
            return None
        if not produto_e_tech(nome):
            return None

        # Preço pode estar em price (número) ou prices.amount
        preco = 0.0
        p = item.get("price")
        if isinstance(p, (int, float)):
            preco = float(p)
        elif isinstance(p, dict):
            preco = float(p.get("amount", 0) or p.get("value", 0) or 0)
        if not preco:
            prices = item.get("prices", {}) or {}
            preco = float(prices.get("price", {}).get("amount", 0) or 0)
        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        # Preço original
        preco_orig = 0.0
        orig = item.get("original_price") or item.get("originalPrice")
        if isinstance(orig, (int, float)):
            preco_orig = float(orig)

        # Desconto
        desconto = item.get("discount_percentage") or item.get("discountPercentage") or 0
        if not desconto and preco_orig > preco > 0:
            desconto = round((1 - preco / preco_orig) * 100)
        if desconto < DESCONTO_MINIMO:
            return None

        url_prod = item.get("permalink", "") or item.get("url", "") or item.get("link", "")
        if not url_prod:
            return None
        if not url_prod.startswith("http"):
            url_prod = "https://www.mercadolivre.com.br" + url_prod

        # Imagem
        imagem = ""
        thumb = item.get("thumbnail") or item.get("picture") or ""
        if isinstance(thumb, str):
            imagem = thumb
        elif isinstance(thumb, dict):
            imagem = thumb.get("url", "")

        item_id = item.get("id", "")
        try:
            from mercadolivre_link import gerar_link_afiliado_ml
            link_curto = gerar_link_afiliado_ml(url_prod, item_id) or encurtar_link(gerar_link_afiliado(url_prod))
        except Exception:
            link_curto = encurtar_link(gerar_link_afiliado(url_prod))

        log(f"  ✅ [next_data] {nome[:45]} | R${preco} | {desconto}%")
        return {
            "nome":           nome,
            "preco":          round(preco, 2),
            "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
            "desconto":       desconto,
            "loja":           "MERCADOLIVRE",
            "frete":          "🚚 Frete a calcular",
            "link_afiliado":  link_curto,
            "imagem_url":     imagem,
            "score":          1,
            "fontes":         ["mercadolivre"],
        }
    except Exception as e:
        log(f"  ML next_data item erro: {e}")
        return None


def processar_item(item):
    try:
        if not isinstance(item, dict):
            return None

        # Formato direto (title/price/permalink) — vem do __NEXT_DATA__
        if "title" in item and ("price" in item or "prices" in item) and "card" not in item:
            return _processar_item_next_data(item)

        card = item.get("card", {})
        if not card:
            return None

        metadata   = card.get("metadata", {}) or {}
        components = card.get("components", []) or []
        pictures   = card.get("pictures", []) or []

        # Debug primeiro item
        if not getattr(processar_item, '_logged', False):
            processar_item._logged = True
            log(f"  -> metadata: {list(metadata.keys())}")
            log(f"  -> {len(components)} components")
            for c in components:
                ctype = c.get("type","")
                cdata = c.get(ctype, c)
                log(f"     [{ctype}] → {str(cdata)[:150]}")

        # ID do item (para link de afiliado oficial)
        item_id = metadata.get("id", "")

        # URL do produto
        url_prod = metadata.get("url", "")
        if url_prod and not url_prod.startswith("http"):
            url_prod = "https://" + url_prod
        if not url_prod:
            return None

        # Extrai dados dos components
        nome       = ""
        preco      = 0.0
        preco_orig = 0.0
        desconto   = 0
        imagem     = ""
        mais_vendido = False
        frete_ok   = False

        for comp in components:
            if not isinstance(comp, dict):
                continue
            ctype = comp.get("type", "").lower()
            cdata = comp.get(ctype, {})
            if not isinstance(cdata, dict):
                cdata = {}

            if ctype == "title":
                nome = cdata.get("text", "") or nome

            elif ctype == "price":
                curr = cdata.get("current_price", {}) or {}
                prev = cdata.get("previous_price", {}) or {}
                preco      = float(curr.get("value", 0) or 0)
                preco_orig = float(prev.get("value", 0) or 0)

                # Novo formato ML: preco original em price_labels -> values -> price -> value
                if preco_orig == 0:
                    for lbl in cdata.get("price_labels", []):
                        if "previous_price" in lbl.get("text", ""):
                            for v in lbl.get("values", []):
                                if v.get("key") == "previous_price":
                                    try:
                                        preco_orig = float(v.get("price", {}).get("value", 0) or 0)
                                    except:
                                        pass
                                    break
                            break

                # Fallback: discount_polylabel tem o percentual de desconto
                if preco_orig == 0 and preco > 0:
                    import re as _re
                    dpoly = cdata.get("discount_polylabel", {}) or {}
                    disc_txt = str(dpoly.get("text", "") or "")
                    m_disc = _re.search(r"(\d+)", disc_txt)
                    if m_disc:
                        disc_pct = int(m_disc.group(1))
                        if 5 <= disc_pct <= 90:
                            preco_orig = round(preco / (1 - disc_pct / 100), 2)

                log(f"  -> PRICE: curr={preco} orig={preco_orig}")

            elif ctype == "shipping":
                frete_txt_comp = cdata.get("text", "")
                if "grátis" in frete_txt_comp.lower() or "gratis" in frete_txt_comp.lower():
                    frete_ok = True

            elif ctype in ("image", "picture", "gallery"):
                imagem = cdata.get("url", "") or cdata.get("src", "") or imagem

            elif ctype == "highlight":
                txt = cdata.get("text", "").lower()
                if "mais vendido" in txt or "best seller" in txt:
                    mais_vendido = True

        # Imagem: vem em card["pictures"]["pictures"][0]["id"]
        if not imagem and isinstance(pictures, dict):
            try:
                pics_list = pictures.get("pictures", [])
                if pics_list and isinstance(pics_list[0], dict):
                    pic_id = pics_list[0].get("id", "")
                    if pic_id:
                        imagem = f"https://http2.mlstatic.com/D_NQ_NP_{pic_id}-F.jpg"
            except Exception:
                imagem = ""

        # Fallback nome
        if not nome:
            nome = metadata.get("title", "")

        nome = nome.strip()
        if not nome:
            return None
        if not produto_valido(nome):
            return None
        if not produto_e_tech(nome):
            log(f"  🚫 Não-tech: {nome[:50]}")
            return None

        if preco <= 0 or preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None

        if preco_orig > preco and desconto == 0:
            desconto = int((1 - preco / preco_orig) * 100)

        if desconto < DESCONTO_MINIMO:
            return None

        frete_txt = "✅ Frete grátis" if frete_ok else "🚚 Frete a calcular"
        # Gera link meli.la via endpoint oficial; fallback para tinyurl se falhar
        try:
            from mercadolivre_link import gerar_link_afiliado_ml
            link_curto = gerar_link_afiliado_ml(url_prod, item_id) or encurtar_link(gerar_link_afiliado(url_prod))
        except Exception:
            link_curto = encurtar_link(gerar_link_afiliado(url_prod))

        log(f"  ✅ {nome[:45]} | R${preco} | {desconto}% {'⭐' if mais_vendido else ''}")

        return {
            "nome":           nome,
            "preco":          round(preco, 2),
            "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
            "desconto":       desconto,
            "loja":           "MERCADOLIVRE",
            "frete":          frete_txt,
            "link_afiliado":  link_curto,
            "imagem_url":     imagem,
            "score":          3 if mais_vendido else 1,
            "fontes":         ["mercadolivre"],
        }
    except Exception as e:
        import traceback
        log(f"  ML item erro: {e} | {traceback.format_exc()[-300:]}")
        return None


def _processar_item_html(item_raw):
    """Processa produto já extraído do HTML de lista.mercadolivre.com.br."""
    try:
        nome = item_raw.get("nome", "").strip()
        if not nome:
            return None
        if not produto_valido(nome):
            return None
        if not produto_e_tech(nome):
            log(f"  🚫 Não-tech (lista): {nome[:50]}")
            return None
        preco = item_raw.get("preco", 0)
        if preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
            return None
        desconto = item_raw.get("desconto", 0)
        if desconto < DESCONTO_MINIMO:
            return None
        preco_orig = item_raw.get("preco_original", 0)
        url_prod = item_raw.get("url_prod", "")
        imagem = item_raw.get("imagem", "")
        if not url_prod:
            return None
        # Tenta link oficial meli.la primeiro (curto + afiliado), depois TinyURL, depois URL longa com matt_tool
        try:
            from mercadolivre_link import gerar_link_afiliado_ml
            link_curto = gerar_link_afiliado_ml(url_prod) or encurtar_link(gerar_link_afiliado(url_prod))
        except Exception:
            link_curto = encurtar_link(gerar_link_afiliado(url_prod))
        log(f"  ✅ {nome[:45]} | R${preco} | {desconto}% | 🔗 {link_curto[:60]}")
        return {
            "nome":           nome,
            "preco":          round(preco, 2),
            "preco_original": round(preco_orig, 2) if preco_orig > preco else 0,
            "desconto":       desconto,
            "loja":           "MERCADOLIVRE",
            "frete":          "🚚 Frete a calcular",
            "link_afiliado":  link_curto,
            "imagem_url":     imagem,
            "score":          1,
            "fontes":         ["mercadolivre"],
        }
    except Exception as e:
        log(f"  ML HTML item erro: {e}")
        return None


# Mapeamento categoria MLB → URLs de busca
_ML_API_CATEGORIAS = [
    ("MLB1648", "Notebooks"),
    ("MLB1051", "Smartphones"),
    ("MLB1066", "TVs"),
    ("MLB1039", "Controles"),
    ("MLB1144", "Consoles"),
    ("MLB1367", "Jogos"),
    ("MLB1000", "Fones"),
    ("MLB1648", "Monitores"),
]

def _buscar_ml_api_categoria(category_id, nome_cat, desconto_min=None, limit=50):
    """Busca via API JSON do ML diretamente (sem scraping)."""
    desc_min = desconto_min if desconto_min is not None else DESCONTO_MINIMO
    api_url = (
        f"https://api.mercadolibre.com/sites/MLB/search"
        f"?category={category_id}&sort=price_desc&limit={limit}"
    )
    raw_json = None

    # Tenta direto com headers completos de browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.mercadolivre.com.br/",
        "Origin": "https://www.mercadolivre.com.br",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Connection": "keep-alive",
    }
    try:
        r = requests.get(api_url, headers=headers, timeout=20)
        log(f"  ML API {nome_cat} direto: {r.status_code}")
        if r.status_code == 200 and r.text.strip().startswith("{"):
            raw_json = r.text
    except Exception as e:
        log(f"  ML API {nome_cat} direto erro: {e}")

    if raw_json is None:
        return []

    try:
        data = json.loads(raw_json)
    except Exception as e:
        log(f"  ML API {nome_cat}: JSON parse erro {e}")
        return []

    results = data.get("results", [])
    produtos = []
    for item in results:
        try:
            nome = item.get("title", "").strip()
            preco = float(item.get("price") or 0)
            preco_orig = float(item.get("original_price") or 0)
            url_prod = item.get("permalink", "")
            imagem = item.get("thumbnail", "").replace("I.jpg", "O.jpg")
            if not nome or not url_prod or preco <= 0:
                continue
            if not produto_valido(nome):
                continue
            if not produto_e_tech(nome):
                continue
            if preco < PRECO_MINIMO or preco > PRECO_MAXIMO:
                continue
            if preco_orig <= 0 or preco_orig <= preco:
                continue
            desconto = int(round((1 - preco / preco_orig) * 100))
            if desconto < desc_min:
                continue
            link_curto = encurtar_link(gerar_link_afiliado(url_prod))
            log(f"  ✅ [API] {nome[:45]} | R${preco} | {desconto}%")
            produtos.append({
                "nome":           nome,
                "preco":          round(preco, 2),
                "preco_original": round(preco_orig, 2),
                "desconto":       desconto,
                "loja":           "MERCADOLIVRE",
                "frete":          "🚚 Frete a calcular",
                "link_afiliado":  link_curto,
                "imagem_url":     imagem,
                "score":          1,
                "fontes":         ["mercadolivre"],
            })
        except Exception:
            continue
    log(f"  ML API {nome_cat}: {len(produtos)} produtos com desconto ≥{desc_min}%")
    return produtos


def buscar_todos_produtos():
    if not SCRAPINGANT_KEY and not ZENROWS_KEY and not SCRAPERAPI_KEY and not BRIGHTDATA_KEY:
        log("ML: nenhuma chave de scraping configurada")
        return []

    log("ML ScrapingAnt: iniciando busca...")
    todos   = []
    vistos  = set()
    total_bruto = 0

    # Garante que Games sempre entram — resto sorteia
    url_games  = [(u, n) for u, n in URLS_BUSCA if any(g in n.lower() for g in ["games", "consoles", "jogos", "controles"])]
    url_outros = [(u, n) for u, n in URLS_BUSCA if (u, n) not in url_games]
    urls = url_games + random.sample(url_outros, min(3, len(url_outros)))

    ml_bloqueado = False  # flag: se CAPTCHA em todas configs na 1ª URL, para tudo

    for url, nome in urls:
        if ml_bloqueado:
            log(f"ML pulando {nome} (bloqueado por CAPTCHA)")
            continue
        try:
            log(f"ML buscando: {nome}")
            html  = scraper_fetch(url)
            if html is None:
                log(f"ML: {nome} falhou (sem HTML) — continuando próxima categoria")
                continue
            items = extrair_produtos_html(html)
            total_bruto += len(items)
            log(f"  -> {len(items)} itens brutos extraídos para {nome}")

            validos_cat = 0
            for item in items:
                if item.get("_raw_html"):
                    p = _processar_item_html(item)
                else:
                    p = processar_item(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)
                        validos_cat += 1
            if items:
                # Diagnóstico: mostra estrutura do primeiro item bruto
                amostra = items[0]
                chaves = list(amostra.keys())[:20]
                log(f"  -> {validos_cat} válidos | chaves item: {chaves}")
                # Mostra valores de campos de preço conhecidos
                for campo in ["price","prices","sale_price","preco","original_price","preco_original","discount","desconto","discount_percentage"]:
                    v = amostra.get(campo)
                    if v is not None:
                        log(f"     {campo}={str(v)[:80]}")

            # Se JSON não funcionou, tenta parser HTML direto
            if not items:
                items_html = extrair_produtos_html_lista(html)
                if items_html:
                    log(f"  -> Fallback HTML lista: {len(items_html)} itens")
                    total_bruto += len(items_html)
                    for item in items_html:
                        p = _processar_item_html(item)
                        if p:
                            chave = hashlib.md5(p["nome"].encode()).hexdigest()
                            if chave not in vistos:
                                vistos.add(chave)
                                todos.append(p)

            time.sleep(2)
        except Exception as e:
            log(f"ML erro {nome}: {e}")
            continue

    log(f"Mercado Livre (ScrapingAnt): {total_bruto} brutos → {len(todos)} válidos")
    return todos


# URLs extras para busca profunda ML
URLS_BUSCA_EXTRA = [
    ("https://lista.mercadolivre.com.br/notebooks-acessorios", "Notebooks"),
    ("https://lista.mercadolivre.com.br/monitores-gamer", "Monitores Gamer"),
    ("https://lista.mercadolivre.com.br/ssd-nvme", "SSDs"),
    ("https://lista.mercadolivre.com.br/placas-de-video", "Placas de Vídeo"),
    ("https://lista.mercadolivre.com.br/samsung-celulares", "Samsung"),
    ("https://lista.mercadolivre.com.br/motorola-celulares", "Motorola"),
    ("https://lista.mercadolivre.com.br/xiaomi-celulares", "Xiaomi"),
    ("https://lista.mercadolivre.com.br/smartwatch", "Smartwatch"),
    ("https://lista.mercadolivre.com.br/fone-bluetooth", "Fones BT"),
    ("https://lista.mercadolivre.com.br/caixa-de-som-bluetooth", "Caixas de Som"),
    ("https://lista.mercadolivre.com.br/smart-tv-55", "Smart TV 55"),
    ("https://lista.mercadolivre.com.br/smart-tv-65", "Smart TV 65"),
    ("https://lista.mercadolivre.com.br/controle-gamer", "Controles Gamer"),
    ("https://lista.mercadolivre.com.br/soundbar", "Soundbar"),
]


def buscar_profundo():
    """Busca profunda ML via ScrapingAnt."""
    log("ML BUSCA PROFUNDA iniciada...")

    if not SCRAPINGANT_KEY and not ZENROWS_KEY and not SCRAPERAPI_KEY and not BRIGHTDATA_KEY:
        log("ML profundo: nenhuma chave de scraping configurada")
        return []
    todos = []
    vistos = set()
    total_bruto = 0

    # Usa TODAS as URLs (normais + extras) em vez de amostra de 4
    todas_urls = URLS_BUSCA + URLS_BUSCA_EXTRA

    for url, nome in todas_urls:
        try:
            log(f"ML profundo buscando: {nome}")
            html = scraper_fetch(url)
            items = extrair_produtos_html(html)
            total_bruto += len(items)
            for item in items:
                p = processar_item(item)
                if p:
                    chave = hashlib.md5(p["nome"].encode()).hexdigest()
                    if chave not in vistos:
                        vistos.add(chave)
                        todos.append(p)
            time.sleep(1)
        except Exception as e:
            log(f"ML profundo erro {nome}: {e}")
            continue

    log(f"ML BUSCA PROFUNDA: {total_bruto} brutos → {len(todos)} válidos")
    return todos
