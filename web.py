"""
OlhaissoTech — Painel de Publicação Manual
Fluxo: Cola link → preenche Preço + Imagem → Publica direto
"""

import os
import re
import requests
from urllib.parse import urlparse, unquote
from flask import Flask, request, jsonify, session, redirect, render_template_string

from bot import (
    gerar_imagem,
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

  .container { max-width: 580px; margin: 0 auto; padding: 20px; }

  .card { background: #1a1a1a; border-radius: 16px; padding: 22px; margin-bottom: 16px; }
  .card h2 { font-size: 15px; color: #FF6B1A; margin-bottom: 16px; font-weight: 700; }

  label { display: block; color: #aaa; font-size: 13px; margin-bottom: 5px; }
  input, select {
    width: 100%; background: #2a2a2a; border: 1px solid #333; border-radius: 10px;
    color: #fff; padding: 12px; font-size: 15px; margin-bottom: 14px; outline: none;
  }
  input:focus { border-color: #FF6B1A; }

  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

  .btn { width: 100%; padding: 15px; border-radius: 12px; border: none; font-size: 16px;
         font-weight: 700; cursor: pointer; margin-bottom: 10px; transition: opacity 0.2s; }
  .btn:active { opacity: 0.8; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-orange { background: #FF6B1A; color: #fff; }
  .btn-green  { background: #00BB44; color: #fff; }

  .msg { padding: 13px 16px; border-radius: 10px; margin-bottom: 14px; font-size: 14px; }
  .msg-ok  { background: #003d1a; color: #00ee66; border: 1px solid #00BB44; }
  .msg-err { background: #3d0000; color: #ff6666; border: 1px solid #ff4444; }

  .info { background: #1e2a1e; border: 1px solid #2a4a2a; border-radius: 10px;
          padding: 10px 14px; font-size: 13px; color: #88cc88; margin-bottom: 14px; }

  .loader { text-align: center; padding: 14px; color: #FF6B1A; font-size: 14px; display: none; }

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

  <div class="card">
    <h2>🚀 Publicar produto direto no grupo</h2>

    <label>📎 Link do produto</label>
    <div style="display:flex; gap:10px; margin-bottom:14px;">
      <input type="url" id="url_input" placeholder="https://shopee.com.br/... ou aliexpress.com/..." style="margin-bottom:0; flex:1;">
      <button onclick="abrirLink()" style="background:#2a2a2a; border:1px solid #444; border-radius:10px; color:#FF6B1A; font-size:22px; padding:0 16px; cursor:pointer;" title="Abrir produto em nova aba">🔗</button>
    </div>

    <div class="row2">
      <div>
        <label>💰 Preço atual (R$) *</label>
        <input type="number" id="preco" step="0.01" placeholder="Ex: 89.90">
      </div>
      <div>
        <label>💵 Preço original (R$)</label>
        <input type="number" id="preco_orig" step="0.01" placeholder="Ex: 149.90">
      </div>
    </div>

    <label>🖼️ URL da imagem do produto *</label>
    <input type="url" id="imagem_url" placeholder="Cole a URL da imagem do produto">

    <div class="info">
      💡 Nome e loja são detectados automaticamente pelo link. Preço e imagem você preenche.
    </div>

    <button class="btn btn-green" id="btn_pub" onclick="publicar()">
      📢 Publicar no grupo agora
    </button>
    <div class="loader" id="loader">⏳ Gerando imagem e publicando no grupo...</div>
  </div>
</div>

<script>
function abrirLink() {
  const url = document.getElementById('url_input').value.trim();
  if (!url) return alert('Cole o link do produto primeiro!');
  window.open(url, '_blank');
}

function detectarLoja(url) {
  if (url.includes('aliexpress.com')) return 'ALIEXPRESS';
  if (url.includes('shopee.com.br'))  return 'SHOPEE';
  if (url.includes('amazon.com.br') || url.includes('amzn.to')) return 'AMAZON';
  return 'OUTRO';
}

function extrairNomeDaUrl(url) {
  try {
    const path = new URL(url).pathname;
    let slug = path.split('/').filter(Boolean)[0] || '';
    slug = slug.replace(/-i\.\d+\.\d+$/, '');
    slug = decodeURIComponent(slug).replace(/-/g, ' ');
    return slug.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ').trim();
  } catch(e) { return ''; }
}

async function publicar() {
  const url    = document.getElementById('url_input').value.trim();
  const preco  = parseFloat(document.getElementById('preco').value) || 0;
  const preco_orig = parseFloat(document.getElementById('preco_orig').value) || 0;
  const imagem = document.getElementById('imagem_url').value.trim();

  if (!url)   return alert('Cole o link do produto!');
  if (!preco) return alert('Preencha o preço atual!');
  if (!imagem) return alert('Cole a URL da imagem do produto!');

  const btn = document.getElementById('btn_pub');
  btn.disabled = true;
  document.getElementById('loader').style.display = 'block';

  const loja = detectarLoja(url);
  const nome = extrairNomeDaUrl(url) || 'Produto em Oferta';

  let link = url;
  if (loja === 'AMAZON' && !url.includes('tag=')) {
    link = url + (url.includes('?') ? '&' : '?') + 'tag={{ amazon_tag }}';
  }

  try {
    const resp = await fetch('/publicar', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ nome, preco, preco_orig, loja, link, imagem })
    });
    const data = await resp.json();
    const area = document.getElementById('msg_area');

    if (data.ok) {
      area.innerHTML = '<div class="msg msg-ok">✅ Publicado com sucesso no grupo!</div>';
      document.getElementById('url_input').value = '';
      document.getElementById('preco').value = '';
      document.getElementById('preco_orig').value = '';
      document.getElementById('imagem_url').value = '';
      setTimeout(() => area.innerHTML = '', 5000);
    } else {
      area.innerHTML = `<div class="msg msg-err">❌ Erro: ${data.erro}</div>`;
    }
  } catch(e) {
    document.getElementById('msg_area').innerHTML = `<div class="msg msg-err">❌ Erro: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    document.getElementById('loader').style.display = 'none';
  }
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
    return render_template_string(
        HTML,
        logged_in=session.get("logged_in", False),
        error=None,
        amazon_tag=AMAZON_TAG,
    )


@app.route("/login", methods=["POST"])
def login():
    if request.form.get("password", "") == WEB_PASSWORD:
        session["logged_in"] = True
        return redirect("/")
    return render_template_string(HTML, logged_in=False, error="Senha incorreta!", amazon_tag=AMAZON_TAG)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


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
        imagem_path = gerar_imagem(produto)
        ok = postar_telegram(produto, imagem_path)
        return jsonify({"ok": ok, "erro": "" if ok else "Falha ao enviar pro Telegram"})
    except Exception as e:
        return jsonify({"ok": False, "erro": str(e)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
