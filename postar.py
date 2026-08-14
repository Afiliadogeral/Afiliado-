"""
postar.py — Publicação multi-plataforma
========================================
Posta em Telegram, Instagram e WhatsApp automaticamente.
  - Telegram:  100% oficial, sem risco
  - Instagram: via instagrapi + proxy residencial (Bright Data)
  - WhatsApp:  via Evolution API no Railway

Credenciais ausentes → canal ignorado silenciosamente.
Sessão do Instagram é salva/carregada para evitar login diário.
"""

import json
import os
import tempfile
import time
import random
import requests
from dotenv import load_dotenv
from utils import (
    salvar_sessao_instagram, carregar_sessao_instagram,
    espera_humana, periodo_atual, mascarar_log
)

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.getenv("TELEGRAM_CHAT_ID",   "")

# ── Instagram ─────────────────────────────────────────────────────────────────
IG_USER    = os.getenv("INSTAGRAM_USERNAME", "")
IG_PASS    = os.getenv("INSTAGRAM_PASSWORD", "")
PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_PORT = os.getenv("PROXY_PORT", "")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

# ── WhatsApp (Evolution API) ──────────────────────────────────────────────────
EVO_URL      = os.getenv("EVOLUTION_API_URL",    "")
EVO_KEY      = os.getenv("EVOLUTION_API_KEY",    "")
EVO_INSTANCE = os.getenv("EVOLUTION_INSTANCE",   "")
WPP_CHANNEL  = os.getenv("WHATSAPP_CHANNEL_JID", "")

# ── Hashtags por período ──────────────────────────────────────────────────────
HASHTAGS = {
    "manha": "#academia #suplementos #wheyprotein #fitness #treino #promocao #achadinhos #ofertas",
    "tarde":  "#pet #cachorro #gato #animais #ofertas #achadinhos #promocao #petlovers",
    "noite":  "#moda #tenis #streetwear #estilo #fone #smartwatch #ofertas #achadinhos",
}


def montar_legenda(oferta, markdown=True):
    periodo = periodo_atual()
    tags    = HASHTAGS.get(periodo, "#ofertas #achadinhos #promocao")

    if markdown:  # Telegram suporta Markdown
        return (
            f"🔥 *{oferta['titulo']}*\n\n"
            f"~~De: R$ {oferta['preco_original']:.2f}~~\n"
            f"💰 *Por: R$ {oferta['preco_atual']:.2f}*  \\({oferta['desconto']}% OFF\\)\n\n"
            f"🔗 {oferta['link_afiliado']}\n\n"
            f"{tags}"
        )
    else:  # Instagram/WhatsApp sem markdown
        return (
            f"🔥 {oferta['titulo']}\n\n"
            f"De: R$ {oferta['preco_original']:.2f}\n"
            f"💰 Por: R$ {oferta['preco_atual']:.2f}  ({oferta['desconto']}% OFF)\n\n"
            f"🔗 {oferta['link_afiliado']}\n\n"
            f"{tags}"
        )


# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def postar_telegram(oferta):
    if not TG_TOKEN or not TG_CHAT:
        return False, "não configurado"
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
            data={
                "chat_id":    TG_CHAT,
                "caption":    montar_legenda(oferta, markdown=False),
                "photo":      oferta["imagem"],
            },
            timeout=25,
        )
        if resp.status_code == 200:
            return True, "ok"
        return False, resp.json().get("description", str(resp.status_code))
    except Exception as e:
        return False, str(e)[:60]


# ── INSTAGRAM ─────────────────────────────────────────────────────────────────
def conectar_instagram():
    if not IG_USER or not IG_PASS:
        return None

    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired, BadPassword

        cl = Client()

        # Proxy residencial
        if PROXY_HOST and PROXY_PORT and PROXY_USER and PROXY_PASS:
            proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
            cl.set_proxy(proxy_url)
            print(f"  [IG] Proxy ativado.")

        # Tenta reusar sessão salva
        if carregar_sessao_instagram(cl):
            try:
                cl.get_timeline_feed()   # testa se a sessão ainda é válida
                print("  [IG] Sessão anterior restaurada — sem login necessário.")
                return cl
            except LoginRequired:
                print("  [IG] Sessão expirada — fazendo login novamente.")

        # Login completo
        cl.login(IG_USER, IG_PASS)
        salvar_sessao_instagram(cl)
        print("  [IG] Login OK — sessão salva.")
        return cl

    except Exception as e:
        print(f"  [IG] Falha ao conectar: {mascarar_log(str(e))[:80]}")
        return None


def postar_instagram(oferta, cl):
    if not cl:
        return False, "sem cliente"
    try:
        img_bytes = requests.get(oferta["imagem"], timeout=15).content
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(img_bytes)
            caminho = tmp.name

        cl.photo_upload(caminho, montar_legenda(oferta, markdown=False))
        os.unlink(caminho)
        return True, "ok"
    except Exception as e:
        return False, str(e)[:60]


# ── WHATSAPP (Evolution API) ──────────────────────────────────────────────────
def postar_whatsapp(oferta):
    if not all([EVO_URL, EVO_KEY, EVO_INSTANCE, WPP_CHANNEL]):
        return False, "não configurado"
    try:
        resp = requests.post(
            f"{EVO_URL}/message/sendMedia/{EVO_INSTANCE}",
            headers={"apikey": EVO_KEY, "Content-Type": "application/json"},
            json={
                "number":    WPP_CHANNEL,
                "mediatype": "image",
                "mimetype":  "image/jpeg",
                "caption":   montar_legenda(oferta, markdown=False),
                "media":     oferta["imagem"],
            },
            timeout=25,
        )
        if resp.status_code in [200, 201]:
            return True, "ok"
        return False, str(resp.status_code)
    except Exception as e:
        return False, str(e)[:60]


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    with open("ofertas.json", "r", encoding="utf-8") as f:
        ofertas = json.load(f)

    ofertas = [o for o in ofertas if o.get("link_afiliado")]

    if not ofertas:
        print("Nenhuma oferta com link de afiliado para postar.")
        return

    periodo = periodo_atual()
    print(f"Postando {len(ofertas)} oferta(s) | Período: {periodo.upper()}\n")

    cl_ig = conectar_instagram()

    resumo = {"tg": 0, "ig": 0, "wpp": 0, "total": len(ofertas)}

    for i, oferta in enumerate(ofertas, 1):
        print(f"[{i}/{len(ofertas)}] {oferta['titulo'][:45]}...")

        ok_tg,  msg_tg  = postar_telegram(oferta)
        ok_ig,  msg_ig  = postar_instagram(oferta, cl_ig)
        ok_wpp, msg_wpp = postar_whatsapp(oferta)

        if ok_tg:  resumo["tg"]  += 1
        if ok_ig:  resumo["ig"]  += 1
        if ok_wpp: resumo["wpp"] += 1

        tg_s  = "✅" if ok_tg  else f"❌ {msg_tg}"
        ig_s  = "✅" if ok_ig  else f"❌ {msg_ig}"
        wpp_s = "✅" if ok_wpp else f"❌ {msg_wpp}"
        print(f"  TG: {tg_s}  |  IG: {ig_s}  |  WPP: {wpp_s}")

        # Delay aleatório entre posts (evita padrão detectável)
        if i < len(ofertas):
            pausa = random.uniform(12, 25)
            print(f"  Aguardando {pausa:.0f}s...")
            time.sleep(pausa)

    print(f"\n── Resumo ──────────────────────────────────")
    print(f"  Telegram:  {resumo['tg']}/{resumo['total']}")
    print(f"  Instagram: {resumo['ig']}/{resumo['total']}")
    print(f"  WhatsApp:  {resumo['wpp']}/{resumo['total']}")


if __name__ == "__main__":
    main()
