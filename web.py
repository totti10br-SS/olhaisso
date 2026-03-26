"""
OlhaissoTech — Painel de Publicação Manual
Interface web para postar produtos manualmente no Telegram
"""

import os
import re
import hashlib
import requests
from flask import Flask, request, jsonify, session, redirect, render_template_string
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")

# Configurações
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "8258862380:AAGCr--OpycbKXp6KeqJCU1_piyu4kRl4bk")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@olhaissotech")
WEB_PASSWORD     = os.getenv("WEB_PASSWORD", "olhaissoadmin")
AMAZON_TAG       = os.getenv("AMAZON_TAG", "olhaissotech-20")

# ============================================================
# HTML DO APP
# ============================================================

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>👀 OlhaissoTech — Painel</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #111; color: #fff; font-family: -apple-system, sans-serif; min-height: 100vh; }

  .header { background: #FF6B1A; padding: 16px 20px; display: flex; align-items: center; gap: 10px; }
  .header h1 { font-size: 20px; font-weight: 800; }
  .header span { font-size: 28px; }

  .container { max-width: 600px; margin: 0 auto; padding: 20px; }

  .card { background: #1a1a1a; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
  .card h2 { font-size: 16px; color: #FF6B1A; margin-bottom: 14px; font-weight: 700; }

  input, textarea, select {
    width: 100%; background: #2a2a2a; border: 1px solid #333; border-radius: 10px;
    color: #fff; padding: 12px; font-size: 15px; margin-bottom: 10px; outline: none;
  }
  input:focus, textarea:focus { border-color: #FF6B1A; }
  textarea { min-height: 120px; resize: vertical; }

  .btn { width: 100%; padding: 14px; border-radius: 12px; border: none; font-size: 16px;
         font-weight: 700; cursor: pointer; margin-bottom: 10px; transition: opacity 0.2s; }
  .btn:active { opacity: 0.8; }
  .btn-orange { background: #FF6B1A; color: #fff; }
  .btn-green  { background: #00BB44; color: #fff; }
  .btn-gray   { background: #333; color: #aaa; }

  .preview { background: #0d0d0d; border: 1px solid #333; border-radius: 12px;
             padding: 16px; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
  .preview img { width: 100%; border-radius: 10px; margin-bottom: 12px; }

  .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px;
           font-weight: 700; margin-bottom: 8px; }
  .badge-orange { background: #FF6B1A; }
  .badge-green  { background: #00BB44; }

  .msg { padding: 12px 16px; border-radius: 10px; margin-bottom: 12px; font-size: 14px; }
  .msg-ok  { background: #003d1a; color: #00ee66; border: 1px solid #00BB44; }
  .msg-err { background: #3d0000; color: #ff6666; border: 1px solid #ff4444; }

  .sep { border: none; border-top: 1px solid #2a2a2a; margin: 16px 0; }

  /* Login */
  .login-wrap { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .login-box { background: #1a1a1a; border-radius: 20px; padding: 36px 28px; width: 340px; text-align: center; }
  .login-box .logo { font-size: 52px; margin-bottom: 8px; }
  .login-box h2 { color: #FF6B1A; font-size: 22px; margin-bottom: 4px; }
  .login-box p { color: #888; font-size: 13px; margin-bottom: 24px; }

  .loader { display: none; text-align: center; padding: 10px; color: #FF6B1A; }
</style>
</head>
<body>

{% if not logged_in %}
<div class="login-wrap">
  <div class="login-box">
    <div class="logo">👀</div>
    <h2>OlhaissoTech</h2>
    <p>Painel de Publicação</p>
    {% if error %}<div class="msg msg-err">{{ error }}</div>{% endif %}
    <form method="POST" action="/login">
      <input type="password" name="password" placeholder="Senha de acesso" autofocus>
      <button type="submit" class="btn btn-orange">Entrar</button>
    </form>
  </div>
</div>

{% else %}

<div class="header">
  <span>👀</span>
  <h1>OlhaissoTech — Painel</h1>
</div>

<div class="container">

  {% if msg %}
  <div class="msg {{ 'msg-ok' if msg_type == 'ok' else 'msg-err' }}">{{ msg }}</div>
  {% endif %}

  <!-- STEP 1: Cole o link -->
  <div class="card" id="step1">
    <h2>📎 Cole o link do produto</h2>
    <input type="url" id="url_input" placeholder="https://aliexpress.com/item/... ou shopee.com.br/...">
    <button class="btn btn-orange" onclick="buscarProduto()">🔍 Buscar produto</button>
    <div class="loader" id="loader">⏳ Buscando informações...</div>
  </div>

  <!-- STEP 2: Editar e preview -->
  <div class="card" id="step2" style="display:none">
    <h2>✏️ Edite e revise antes de publicar</h2>

    <label style="color:#aaa;font-size:13px;">Nome do produto</label>
    <input type="text" id="nome">

    <label style="color:#aaa;font-size:13px;">Preço atual (R$)</label>
    <input type="number" id="preco" step="0.01" oninput="atualizarPreview()">

    <label style="color:#aaa;font-size:13px;">Preço original (R$)</label>
    <input type="number" id="preco_orig" step="0.01" oninput="atualizarPreview()">

    <label style="color:#aaa;font-size:13px;">Loja</label>
    <select id="loja" onchange="atualizarPreview()">
      <option value="ALIEXPRESS">AliExpress</option>
      <option value="SHOPEE">Shopee</option>
      <option value="AMAZON">Amazon</option>
      <option value="OUTRO">Outro</option>
    </select>

    <label style="color:#aaa;font-size:13px;">Link de afiliado</label>
    <input type="url" id="link_afiliado">

    <label style="color:#aaa;font-size:13px;">URL da imagem</label>
    <input type="url" id="imagem_url" oninput="atualizarPreview()">

    <hr class="sep">
    <h2>👁️ Preview do post</h2>
    <div class="preview" id="preview_img"></div>
    <div class="preview" id="preview_txt" style="margin-top:10px;"></div>

    <hr class="sep">
    <button class="btn btn-green" onclick="publicar()">📢 Publicar no grupo agora</button>
    <button class="btn btn-gray" onclick="resetar()">↩️ Buscar outro produto</button>
  </div>

</div>

<script>
let produtoAtual = {};

async function buscarProduto() {
  const url = document.getElementById('url_input').value.trim();
  if (!url) return alert('Cole um link válido!');

  document.getElementById('loader').style.display = 'block';
  document.querySelector('#step1 .btn').disabled = true;

  try {
    const resp = await fetch('/buscar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await resp.json();

    if (data.erro) {
      alert('Erro: ' + data.erro);
      return;
    }

    produtoAtual = data;
    document.getElementById('nome').value = data.nome || '';
    document.getElementById('preco').value = data.preco || '';
    document.getElementById('preco_orig').value = data.preco_orig || '';
    document.getElementById('loja').value = data.loja || 'ALIEXPRESS';
    document.getElementById('link_afiliado').value = data.link || url;
    document.getElementById('imagem_url').value = data.imagem || '';

    atualizarPreview();
    document.getElementById('step1').style.display = 'none';
    document.getElementById('step2').style.display = 'block';

  } catch(e) {
    alert('Erro ao buscar: ' + e.message);
  } finally {
    document.getElementById('loader').style.display = 'none';
    document.querySelector('#step1 .btn').disabled = false;
  }
}

function atualizarPreview() {
  const nome = document.getElementById('nome').value;
  const preco = parseFloat(document.getElementById('preco').value) || 0;
  const orig = parseFloat(document.getElementById('preco_orig').value) || 0;
  const loja = document.getElementById('loja').value;
  const imagem = document.getElementById('imagem_url').value;

  const desc = orig > preco ? Math.round((1 - preco/orig) * 100) : 0;
  const eco = orig > preco ? (orig - preco).toFixed(2).replace('.', ',') : null;

  const fmtPreco = v => 'R$ ' + v.toFixed(2).replace('.', ',').replace(/\\B(?=(\\d{3})+(?!\\d))/g, '.');
  const lojaLabel = {ALIEXPRESS:'🛍️ AliExpress', SHOPEE:'🧡 Shopee', AMAZON:'📦 Amazon', OUTRO:'🏪 Outro'}[loja] || loja;

  // Preview imagem
  if (imagem) {
    document.getElementById('preview_img').innerHTML = `<img src="${imagem}" onerror="this.style.display='none'">`;
  }

  // Preview texto
  let badge = desc >= 40 ? '🔥 VIRAL AGORA' : desc >= 25 ? '📈 TENDÊNCIA' : '💰 OFERTA DO DIA';
  let txt = `👀 OlhaissO — ${badge}\\n`;
  txt += `━━━━━━━━━━━━━━━━━━━━\\n\\n`;
  txt += `${nome}\\n\\n`;
  if (desc > 0) {
    txt += `🏷️ ${desc}% OFF`;
    if (eco) txt += `  |  Economia de R$ ${eco}`;
    txt += '\\n';
  }
  if (orig > 0) txt += `\\n💵 De ${fmtPreco(orig)} por apenas\\n`;
  txt += `💰 ${fmtPreco(preco)}\\n\\n`;
  txt += `${lojaLabel}\\n`;
  txt += `\\n🛒 COMPRAR AGORA — CLIQUE AQUI\\n`;
  txt += `\\n━━━━━━━━━━━━━━━━━━━━\\n`;
  txt += `👀 OlhaissoTech | Gadgets com o melhor preço`;

  document.getElementById('preview_txt').textContent = txt;
}

async function publicar() {
  const payload = {
    nome: document.getElementById('nome').value,
    preco: parseFloat(document.getElementById('preco').value) || 0,
    preco_orig: parseFloat(document.getElementById('preco_orig').value) || 0,
    loja: document.getElementById('loja').value,
    link: document.getElementById('link_afiliado').value,
    imagem: document.getElementById('imagem_url').value,
  };

  if (!payload.nome || !payload.preco || !payload.link) {
    return alert('Preencha nome, preço e link!');
  }

  const btn = document.querySelector('.btn-green');
  btn.textContent = '⏳ Publicando...';
  btn.disabled = true;

  try {
    const resp = await fetch('/publicar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await resp.json();

    if (data.ok) {
      alert('✅ Publicado com sucesso no grupo!');
      resetar();
    } else {
      alert('❌ Erro: ' + data.erro);
    }
  } catch(e) {
    alert('Erro: ' + e.message);
  } finally {
    btn.textContent = '📢 Publicar no grupo agora';
    btn.disabled = false;
  }
}

function resetar() {
  document.getElementById('url_input').value = '';
  document.getElementById('step1').style.display = 'block';
  document.getElementById('step2').style.display = 'none';
}
</script>
{% endif %}
</body>
</html>"""

# ============================================================
# ROTAS
# ============================================================

@app.route("/")
def index():
    logged_in = session.get("logged_in", False)
    return render_template_string(HTML, logged_in=logged_in, msg=None, msg_type=None, error=None)


@app.route("/login", methods=["POST"])
def login():
    senha = request.form.get("password", "")
    if senha == WEB_PASSWORD:
        session["logged_in"] = True
        return redirect("/")
    return render_template_string(HTML, logged_in=False, msg=None, msg_type=None, error="Senha incorreta!")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


def buscar_shopee(url):
    """Extrai shop_id e item_id da URL Shopee e consulta API oficial."""
    m = re.search(r'i\.(\d+)\.(\d+)', url)
    if not m:
        return None
    shop_id = m.group(1)
    item_id = m.group(2)

    api_url = "https://shopee.com.br/api/v4/item/get"
    params  = {"itemid": item_id, "shopid": shop_id}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://shopee.com.br/",
        "X-API-SOURCE": "pc",
    }
    try:
        r = requests.get(api_url, params=params, headers=headers, timeout=15)
        data = r.json()
        item = data.get("data", {}) or {}
        if not item:
            return None

        nome   = item.get("name", "")[:200]
        preco  = (item.get("price") or item.get("price_min") or 0) / 100000
        orig   = (item.get("price_before_discount") or item.get("price_max") or 0) / 100000
        if orig <= preco:
            orig = round(preco * 1.3, 2)

        imgs   = item.get("images") or []
        imagem = f"https://cf.shopee.com.br/file/{imgs[0]}" if imgs else ""

        return {"nome": nome, "preco": round(preco, 2), "preco_orig": round(orig, 2), "imagem": imagem}
    except Exception:
        return None


def extrair_nome_da_url(url):
    """Extrai nome do produto diretamente da URL (slug)."""
    try:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(url)
        slug = parsed.path.strip("/").split("/")[0]
        slug = re.sub(r'-i\.\d+\.\d+$', '', slug)
        nome = unquote(slug).replace("-", " ").title()
        nome = re.sub(r'\s+', ' ', nome).strip()
        return nome[:200] if len(nome) > 5 else ""
    except Exception:
        return ""


def buscar_og(url):
    """Fallback: Open Graph scraping generico."""
    nome = ""
    imagem = ""
    preco = 0.0
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=12)
        html = r.text

        og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html)
        if og_title:
            nome = og_title.group(1)[:200]

        og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']', html)
        if og_img:
            imagem = og_img.group(1)

        preco_match = re.search(r'R\$\s*([\d.,]+)', html)
        if preco_match:
            preco_str = preco_match.group(1).replace(".", "").replace(",", ".")
            try:
                preco = float(preco_str)
            except:
                pass
    except Exception:
        pass

    if not nome:
        nome = extrair_nome_da_url(url)

    return {"nome": nome, "preco": preco, "preco_orig": round(preco * 1.3, 2) if preco > 0 else 0, "imagem": imagem}


@app.route("/buscar", methods=["POST"])
def buscar():
    if not session.get("logged_in"):
        return jsonify({"erro": "Não autorizado"}), 401

    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"erro": "URL inválida"})

    # Detecta loja
    loja = "OUTRO"
    if "aliexpress.com" in url:
        loja = "ALIEXPRESS"
    elif "shopee.com.br" in url:
        loja = "SHOPEE"
    elif "amazon.com.br" in url or "amzn.to" in url:
        loja = "AMAZON"

    # Adiciona tag Amazon se necessário
    link = url
    if loja == "AMAZON" and AMAZON_TAG not in url:
        sep = "&" if "?" in url else "?"
        link = f"{url}{sep}tag={AMAZON_TAG}"

    # Busca dados do produto
    dados = None
    if loja == "SHOPEE":
        dados = buscar_shopee(url)
    if not dados:
        dados = buscar_og(url)

    return jsonify({
        "nome":       dados.get("nome", ""),
        "preco":      dados.get("preco", 0),
        "preco_orig": dados.get("preco_orig", 0),
        "loja":       loja,
        "link":       link,
        "imagem":     dados.get("imagem", ""),
    })


@app.route("/publicar", methods=["POST"])
def publicar():
    if not session.get("logged_in"):
        return jsonify({"ok": False, "erro": "Não autorizado"}), 401

    data = request.json
    nome      = data.get("nome", "")
    preco     = float(data.get("preco", 0))
    preco_orig= float(data.get("preco_orig", 0))
    loja      = data.get("loja", "")
    link      = data.get("link", "")
    imagem    = data.get("imagem", "")

    if not nome or not preco or not link:
        return jsonify({"ok": False, "erro": "Dados incompletos"})

    # Monta caption
    desc = int((1 - preco / preco_orig) * 100) if preco_orig > preco else 0
    eco  = round(preco_orig - preco, 2) if preco_orig > preco else 0

    def fmt(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    loja_label = {"ALIEXPRESS": "🛍️ AliExpress", "SHOPEE": "🧡 Shopee", "AMAZON": "📦 Amazon"}.get(loja, "🏪 " + loja)
    badge = "🔥 <b>VIRAL AGORA</b>" if desc >= 40 else "📈 <b>TENDÊNCIA</b>" if desc >= 25 else "💰 <b>OFERTA DO DIA</b>"

    nome_html = nome.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    caption  = f"👀 <b>OlhaissO</b> — {badge}\n"
    caption += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    caption += f"<b>{nome_html}</b>\n\n"
    if desc > 0:
        caption += f"🏷️ <b>{desc}% OFF</b>"
        if eco > 0:
            caption += f"  |  Economia de <b>{fmt(eco)}</b>"
        caption += "\n"
    if preco_orig > 0:
        caption += f"\n💵 De <s>{fmt(preco_orig)}</s> por apenas\n"
    caption += f"💰 <b>{fmt(preco)}</b>\n\n"
    caption += f"{loja_label}\n"
    caption += f"\n🛒 <a href=\"{link}\"><b>COMPRAR AGORA — CLIQUE AQUI</b></a>\n"
    caption += f"\n━━━━━━━━━━━━━━━━━━━━\n"
    caption += f"<i>👀 OlhaissoTech | Gadgets com o melhor preço</i>"

    # Posta no Telegram
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    try:
        if imagem:
            r = requests.post(tg_url, data={
                "chat_id": TELEGRAM_CHANNEL,
                "photo": imagem,
                "caption": caption,
                "parse_mode": "HTML",
            }, timeout=30)
        else:
            r = requests.post(tg_url, data={
                "chat_id": TELEGRAM_CHANNEL,
                "caption": caption,
                "parse_mode": "HTML",
            }, timeout=30)

        if r.status_code == 200:
            return jsonify({"ok": True})
        else:
            return jsonify({"ok": False, "erro": r.text[:200]})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
