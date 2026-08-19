"""
scraper.py v3 — Busca via API do ML + requests simples
Sem Playwright, sem filtro de desconto mínimo agressivo.
Posta qualquer produto com desconto real.
"""
import json, os, time, random, requests, logging
from datetime import datetime
from utils import carregar_historico, periodo_atual

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Headers que imitam browser real
HEADERS_ML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.mercadolivre.com.br/",
    "Origin": "https://www.mercadolivre.com.br",
}

# TODOS os nichos combinados — sem separação por período
# Busca tudo de uma vez, pega os com maior desconto
TERMOS = [
    # Fitness / Suplementos
    "whey protein", "creatina", "pre treino", "bcaa", "colageno",
    "termogenico", "glutamina", "vitamina c", "omega 3",
    # Roupas fitness
    "legging fitness", "camiseta dry fit", "short academia",
    # Pet
    "racao golden", "racao royal canin", "antipulgas nexgard",
    "comedouro automatico", "cama pet", "coleira cachorro",
    # Moda
    "tenis nike", "tenis adidas", "tenis masculino", "tenis feminino",
    "camiseta masculina", "bermuda masculina",
    # Eletronicos / Acessorios
    "fone bluetooth", "smartwatch", "carregador rapido",
    "mochila escolar", "garrafa termica stanley",
]

MAX_POR_TERMO = 5
MAX_FINAL = 8
DESCONTO_MINIMO = 5  # aceitamos qualquer desconto acima de 5%


def buscar_api_ml(termo):
    """Usa a API pública do ML para buscar produtos com desconto."""
    url = "https://api.mercadolibre.com/sites/MLB/search"
    params = {
        "q": termo,
        "limit": 10,
        "sort": "price_asc",
        "tag": "on_sale",  # apenas produtos em oferta
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS_ML, timeout=15)
        if r.status_code != 200:
            logger.warning(f"  API retornou {r.status_code} para '{termo}'")
            return []
        dados = r.json()
        return dados.get("results", [])
    except Exception as e:
        logger.error(f"  Erro na API para '{termo}': {e}")
        return []


def processar_item(item):
    """Extrai dados relevantes de um item da API do ML."""
    try:
        titulo = item.get("title", "")
        if not titulo or len(titulo) < 5:
            return None

        preco_atual = float(item.get("price", 0))
        preco_orig = float(item.get("original_price") or preco_atual)

        if preco_atual <= 0:
            return None

        # Calcula desconto
        if preco_orig > preco_atual:
            desconto = round((1 - preco_atual / preco_orig) * 100)
        else:
            desconto = 0

        if desconto < DESCONTO_MINIMO:
            return None

        url = item.get("permalink", "")
        if not url:
            return None

        # Imagem
        imagem = ""
        thumb = item.get("thumbnail", "")
        if thumb:
            # Pega imagem em maior resolução
            imagem = thumb.replace("-I.jpg", "-O.jpg").replace("http://", "https://")

        if not imagem:
            imagem = "https://via.placeholder.com/500x500?text=Oferta"

        return {
            "titulo": titulo,
            "preco_original": round(preco_orig, 2),
            "preco_atual": round(preco_atual, 2),
            "desconto": desconto,
            "url": url,
            "imagem": imagem,
            "link_afiliado": "",
        }
    except Exception as e:
        logger.debug(f"Erro processando item: {e}")
        return None


def main():
    periodo = periodo_atual()
    logger.info("=" * 60)
    logger.info(f"SCRAPER v3 | Período: {periodo.upper()} | {len(TERMOS)} termos")
    logger.info(f"Desconto mínimo: {DESCONTO_MINIMO}%")
    logger.info("=" * 60)

    historico = carregar_historico()
    ja_postadas = set(historico.keys())
    logger.info(f"Histórico: {len(ja_postadas)} URLs já postadas (ignoradas)")

    vistos = set()
    ofertas = []

    # Embaralha termos para variar o conteúdo a cada rodada
    termos_shuffled = TERMOS.copy()
    random.shuffle(termos_shuffled)

    for i, termo in enumerate(termos_shuffled, 1):
        logger.info(f"[{i}/{len(termos_shuffled)}] Buscando: '{termo}'")
        itens = buscar_api_ml(termo)
        novos = 0
        for item in itens[:MAX_POR_TERMO]:
            oferta = processar_item(item)
            if not oferta:
                continue
            if oferta["url"] in vistos or oferta["url"] in ja_postadas:
                continue
            vistos.add(oferta["url"])
            ofertas.append(oferta)
            novos += 1

        logger.info(f"  → {novos} oferta(s) nova(s) com >= {DESCONTO_MINIMO}% OFF")
        time.sleep(random.uniform(0.5, 1.5))  # pausa leve entre requests

    # Ordena por maior desconto
    ofertas.sort(key=lambda o: o["desconto"], reverse=True)
    selecionadas = ofertas[:MAX_FINAL]

    with open("ofertas.json", "w", encoding="utf-8") as f:
        json.dump(selecionadas, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'='*60}")
    logger.info(f"RESULTADO: {len(selecionadas)} oferta(s) prontas para postar")
    logger.info(f"{'='*60}")
    for o in selecionadas:
        logger.info(f"  {o['desconto']:3d}% OFF | R${o['preco_atual']:.2f} | {o['titulo'][:50]}")


if __name__ == "__main__":
    main()
