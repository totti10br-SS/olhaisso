"""
OlhaissoTech — Painel de Publicação Manual
Cola o link → gera imagem + caption igual ao bot → publica direto no grupo
"""

import os
import re
import requests
from urllib.parse import urlparse, unquote
from flask import Flask, request, jsonify, session, redirect, render_template_string

# Importa funções do bot (mesma imagem, mesmo caption, mesmo postar)
from bot import (
    gerar_imagem,
    montar_caption,
    postar_telegram,
    TELEGRAM_TOKEN,
    TELEGRAM_CHANNEL,
    AMAZON_TAG,
)

app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET_KEY", "olhaissotech2026")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "olhaissoadmin")

# ============================================================
# HTML
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

  .container { max-width: 620px; margin: 0 auto; padding: 20px; }

  .card { background: #1a1a1a; border-radius: 16px; padding: 20px; margin-bottom: 16px; }
  .card h2 { font-size: 16px; color: #FF6B1A; margin-bottom: 14px; font-weight: 700; }

  label { display: block; color: #aaa; font-size: 13px; margin-bottom: 4px; }
  input, select {
    width: 100%; background: #2a2a2a; border: 1px solid #333; border-radius: 10px;
    color: #fff; padding: 12px; font-size: 15px; margin-bottom: 12px; outline: none;
  }
  input:focus, select:focus { border-color: #FF6B1A; }

  .btn { width: 100%; padding: 14px; border-radius: 12px; border: none; font-size: 16px;
         font-weight: 700; cursor: pointer; margin-bottom: 10px; transition: opacity 0.2s; }
  .btn:active { opacity: 0.8; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-orange { background: #FF6B1A; color: #fff; }
  .btn-green  { background: #00BB44; color: #fff; }
  .btn-gray   { background: #333; color: #aaa; }

  .msg { padding: 12px 16px; border-radius: 10px; margin-bottom: 12px; font-size: 14px; }
  .msg-ok  { background: #003d1a; color: #00ee66; border: 1px solid #00BB44; }
  .msg-err { background: #3d0000; color: #ff6666; border: 1px solid #ff4444; }

  .sep { border: none; border-top: 1px solid #2a2a2a; margin: 16px 0; }
  .loader { text-align: center; padding: 16px; color: #FF6B1A; font-size: 15px; display: none; }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

  /* Login */
  .login-wrap { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .login-box { background: #1a1a1a; border-radius: 20px; padding: 36px 28px; width: 340px; text-align: center; }
  .login-box .logo { font-size: 52px; margin-bottom: 8px; }
  .login-box h2 { color: #FF6B1A; font-size: 22px; margin-bottom: 4px; }
  .login-box p { color: #888; font-size: 13px; margin-bottom: 24px; }
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
  <h1>OlhaissoTech — Publicação Manual</h1>
</div>

<div class="container">

  <div id="msg_area"></div>

  <!-- STEP 1 -->
  <div class="card" id="step1">
    <h2>📎 Cole o link do produto</h2>
    <label>Link do produto (AliExpress, Shopee ou Amazon)</label>
    <input type="url" id="url_input" placeholder="https://shopee.com.br/... ou aliexpress.com/...">
    <button class="btn btn-orange" id="btn_buscar" onclick="buscarProduto()">🔍 Buscar e pré-preencher</button>
    <div class="loader" id="loader">⏳ Buscando dados do produto...</div>
  </div>

  <!-- STEP 2 -->
  <div class="card" id="step2" style="display:none">
    <h2>✏️ Revise os dados antes de publicar</h2>

    <label>Nome do produto</label>
    <input type="text" id="nome">

    <div class="row2">
      <div>
        <label>Preço atual (R$)</label>
        <input type="number" id="preco" step="0.01" placeholder="Ex: 89.90">
      </div>
      <div>
        <label>Preço original (R$)</label>
        <input type="number" id="preco_orig" step="0.01" placeholder="Ex: 149.90">
      </div>
    </div>

    <label>Loja</label>
    <select id="loja">
      <option value="SHOPEE">Shopee</option>
      <option value="ALIEXPRESS">AliExpress</option>
      <option value="AMAZON">Amazon</option>
      <option value="OUTRO">Outro</option>
    </select>

    <label>Link de afiliado</label>
    <input type="url" id="link_afiliado">

    <label>URL da imagem do produto (opcional)</label>
    <input type="url" id="imagem_url" placeholder="Cole a URL da imagem">

    <hr class="sep">
    <button class="btn btn-green" onclick="publicar()" id="btn_pub">
      📢 Publicar no grupo agora
    </button>
    <button class="btn btn-gray" onclick="resetar()">↩️ Buscar outro produto</button>
  </div>

</div>

<script>
async function buscarProduto() {
  const url = document.getElementById('url_input').value.trim();
  if (!url) return alert('Cole um link válido!');

  document.getElementById('loader').style.display = 'block';
  document.getElementById('btn_buscar').disabled = true;

  try {
    const resp = await fetch('/buscar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await resp.json();
    if (data.erro) { alert('Erro: ' + data.erro); return; }

    document.getElementById('nome').value         = data.nome || '';
    document.getElementById('preco').value        = data.preco || '';
    document.getElementById('preco_orig').value   = data.preco_orig || '';
    document.getElementById('loja').value         = data.loja || 'SHOPEE';
    document.getElementById('link_afiliado').value = data.link || url;
    document.getElementById('imagem_url').value   = data.imagem || '';

    document.getElementById('step1').style.display = 'none';
    document.getElementById('step2').style.display = 'block';
  } catch(e) {
    alert('Erro ao buscar: ' + e.message);
  } finally {
    document.getElementById('loader').style.display = 'none';
    document.getElementById('btn_buscar').disabled = false;
  }
}

async function publicar() {
  const nome  = document.getElementById('nome').value.trim();
  const preco = parseFloat(document.getElementById('preco').value) || 0;
  const link  = document.getElementById('link_afiliado').value.trim();

  if (!nome)  return alert('Preencha o nome do produto!');
  if (!preco) return alert('Preencha o preço atual!');
  if (!link)  return alert('Preencha o link de afiliado!');

  const btn = document.getElementById('btn_pub');
  btn.textContent = '⏳ Gerando imagem e publicando...';
  btn.disabled = true;

  try {
    const resp = await fetch('/publicar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        nome,
        preco,
        preco_orig: parseFloat(document.getElementById('preco_orig').value) || 0,
        loja: document.getElementById('loja').value,
        link,
        imagem: document.getElementById('imagem_url').value.trim(),
      })
    });
    const data = await resp.json();
    const area = document.getElementById('msg_area');

    if (data.ok) {
      area.innerHTML = '<div class="msg msg-ok">✅ Publicado com sucesso no grupo!</div>';
      resetar();
      setTimeout(() => area.innerHTML = '', 5000);
    } else {
      area.innerHTML = `<div class="msg msg-err">❌ Erro: ${data.erro}</div>`;
    }
  } catch(e) {
    document.getElementById('msg_area').innerHTML = `<div class="msg msg-err">❌ Erro: ${e.message}</div>`;
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
# HELPERS
# ============================================================

def extrair_nome_da_url(url):
    try:
        slug = urlparse(url).path.strip("/").split("/")[0]
        slug = re.sub(r'-i\.\d+\.\d+$', '', slug)
        nome = unquote(slug).replace("-", " ").title()
        return re.sub(r'\s+', ' ', nome).strip()[:200]
    except Exception:
        return ""


def buscar_shopee_api(url):
    m = re.search(r'i\.(\d+)\.(\d+)', url)
    if not m:
        return None
    try:
        r = requests.get(
            "https://shopee.com.br/api/v4/item/get",
            params={"itemid": m.group(2), "shopid": m.group(1)},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://shopee.com.br/", "X-API-SOURCE": "pc"},
            timeout=10
        )
        item = r.json().get("data") or {}
        if not item:
            return None
        preco = (item.get("price") or item.get("price_min") or 0) / 100000
        orig  = (item.get("price_before_discount") or item.get("price_max") or 0) / 100000
        if orig <= preco:
            orig = round(preco * 1.3, 2)
        imgs = item.get("images") or []
        return {
            "nome":      item.get("name", "")[:200],
            "preco":     round(preco, 2),
            "preco_orig": round(orig, 2),
            "imagem":    f"https://cf.shopee.com.br/file/{imgs[0]}" if imgs else "",
        }
    except Exception:
        return None


def buscar_og(url):
    nome = imagem = ""
    preco = 0.0
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        html = r.text
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html)
        if m: nome = m.group(1)[:200]
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']', html)
        if m: imagem = m.group(1)
        m = re.search(r'R\$\s*([\d.,]+)', html)
        if m:
            try: preco = float(m.group(1).replace(".", "").replace(",", "."))
            except: pass
    except Exception:
        pass
    if not nome:
        nome = extrair_nome_da_url(url)
    return {"nome": nome, "preco": preco, "preco_orig": round(preco * 1.3, 2) if preco > 0 else 0, "imagem": imagem}


# ============================================================
# ROTAS
# ============================================================

@app.route("/")
def index():
    return render_template_string(HTML, logged_in=session.get("logged_in", False), error=None)


@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password", "") == WEB_PASSWORD:
        session["logged_in"] = True
        return redirect("/")
    return render_template_string(HTML, logged_in=False, error="Senha incorreta!")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/buscar", methods=["POST"])
def buscar():
    if not session.get("logged_in"):
        return jsonify({"erro": "Não autorizado"}), 401

    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"erro": "URL inválida"})

    loja = "OUTRO"
    if "aliexpress.com" in url:       loja = "ALIEXPRESS"
    elif "shopee.com.br" in url:      loja = "SHOPEE"
    elif "amazon.com.br" in url or "amzn.to" in url: loja = "AMAZON"

    link = url
    if loja == "AMAZON" and AMAZON_TAG not in url:
        link = f"{url}{'&' if '?' in url else '?'}tag={AMAZON_TAG}"

    dados = None
    if loja == "SHOPEE":
        dados = buscar_shopee_api(url)
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

    data       = request.json
    nome       = data.get("nome", "").strip()
    preco      = float(data.get("preco", 0))
    preco_orig = float(data.get("preco_orig", 0))
    loja       = data.get("loja", "OUTRO")
    link       = data.get("link", "")
    imagem     = data.get("imagem", "")

    if not nome or not preco or not link:
        return jsonify({"ok": False, "erro": "Dados incompletos"})

    desc = int((1 - preco / preco_orig) * 100) if preco_orig > preco else 0

    # Monta produto no mesmo formato do bot automático
    produto = {
        "nome":           nome,
        "preco":          preco,
        "preco_original": preco_orig,
        "desconto":       desc,
        "loja":           loja,
        "frete":          "✅ Frete grátis" if loja in ("SHOPEE", "ALIEXPRESS") else "",
        "link_afiliado":  link,
        "imagem_url":     imagem,
        "score":          1,
        "fontes":         [],
    }

    try:
        imagem_path = gerar_imagem(produto)   # mesma função do bot
        ok = postar_telegram(produto, imagem_path)  # mesmo postar do bot
        return jsonify({"ok": ok, "erro": "" if ok else "Falha ao enviar pro Telegram"})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
