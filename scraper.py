
import json, time, random, logging, requests, re
from datetime import datetime
from bs4 import BeautifulSoup
from utils import carregar_historico, periodo_atual

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

TERMOS = [
    "whey protein","creatina","pre treino","bcaa","colageno",
    "termogenico","vitamina","omega 3","legging fitness",
    "camiseta dry fit","short academia","racao golden",
    "racao royal canin","antipulgas","cama pet","coleira cachorro",
    "tenis nike","tenis adidas","tenis masculino","tenis feminino",
    "camiseta masculina","bermuda masculina","fone bluetooth",
    "smartwatch","mochila","garrafa termica",
]

ETIQUETA = "rafaelrafa13"
MAX_FINAL = 8
DESCONTO_MIN = 5

HEADERS_REQ = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def gerar_link_afiliado(url):
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}matt_tool=60085&matt_word={ETIQUETA}&matt_source=gg_mlb&matt_campaign_id={ETIQUETA}"

def buscar_termo(termo):
    url = f"https://lista.mercadolivre.com.br/{termo.replace(' ','-')}_PriceDiscount_5-100"
    try:
        r = requests.get(url, headers=HEADERS_REQ, timeout=20)
        if r.status_code != 200:
            log.warning(f"  HTTP {r.status_code} para '{termo}'")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("li.ui-search-layout__item")
        log.info(f"  {len(items)} cards HTML encontrados")
        resultados = []
        for item in items[:10]:
            try:
                titulo_el = item.select_one("h2.ui-search-item__title, .poly-component__title")
                titulo = titulo_el.text.strip() if titulo_el else ""
                if not titulo: continue

                # Preço atual
                preco_el = item.select_one(".ui-search-price__part:not(.ui-search-price__original-value) .andes-money-amount__fraction")
                if not preco_el: continue
                preco_txt = preco_el.text.strip().replace(".", "").replace(",", ".")
                preco_atual = float(preco_txt) if preco_txt else 0
                if preco_atual <= 0: continue

                # Preço original
                orig_el = item.select_one(".ui-search-price__original-value .andes-money-amount__fraction")
                if orig_el:
                    orig_txt = orig_el.text.strip().replace(".", "").replace(",", ".")
                    preco_orig = float(orig_txt) if orig_txt else preco_atual
                else:
                    preco_orig = preco_atual

                # Desconto
                badge_el = item.select_one(".andes-badge--discount, [class*='discount']")
                if badge_el:
                    nums = re.findall(r'\d+', badge_el.text)
                    desconto = int(nums[0]) if nums else 0
                elif preco_orig > preco_atual:
                    desconto = round((1 - preco_atual/preco_orig)*100)
                else:
                    desconto = 0

                if desconto < DESCONTO_MIN: continue

                # Link
                link_el = item.select_one("a.ui-search-link, a.poly-component__title, a[href*='produto.mercadolivre']")
                if not link_el: continue
                url_prod = link_el.get("href","").split("#")[0].split("?")[0]
                if not url_prod or "mercadolivre" not in url_prod: continue

                # Imagem
                img_el = item.select_one("img.ui-search-result-image__element, img[src*='mlstatic'], img[data-src*='mlstatic']")
                imagem = ""
                if img_el:
                    imagem = img_el.get("src") or img_el.get("data-src") or ""
                    imagem = imagem.replace("http://","https://")
                if not imagem:
                    imagem = "https://via.placeholder.com/500x500?text=Oferta+ML"

                resultados.append({
                    "titulo": titulo,
                    "preco_original": round(preco_orig, 2),
                    "preco_atual": round(preco_atual, 2),
                    "desconto": desconto,
                    "url": url_prod,
                    "imagem": imagem,
                    "link_afiliado": gerar_link_afiliado(url_prod),
                })
            except Exception as e:
                log.debug(f"  item erro: {e}")
        return resultados
    except Exception as e:
        log.error(f"  Erro geral '{termo}': {e}")
        return []

def main():
    periodo = periodo_atual()
    log.info("="*60)
    log.info(f"SCRAPER v4 BeautifulSoup | {len(TERMOS)} termos | min {DESCONTO_MIN}% OFF")
    log.info("="*60)

    historico = carregar_historico()
    ja_postadas = set(historico.keys())
    log.info(f"Histórico: {len(ja_postadas)} já postadas")

    termos = TERMOS.copy()
    random.shuffle(termos)

    vistos, ofertas = set(), []

    for i, termo in enumerate(termos, 1):
        log.info(f"[{i}/{len(termos)}] '{termo}'")
        for o in buscar_termo(termo):
            if o["url"] not in vistos and o["url"] not in ja_postadas:
                vistos.add(o["url"])
                ofertas.append(o)
        log.info(f"  Total acumulado: {len(ofertas)} oferta(s)")
        if len(ofertas) >= MAX_FINAL * 2:
            log.info("  Encontrei suficiente, parando busca.")
            break
        time.sleep(random.uniform(1, 3))

    ofertas.sort(key=lambda o: o["desconto"], reverse=True)
    selecionadas = ofertas[:MAX_FINAL]

    with open("ofertas.json","w",encoding="utf-8") as f:
        json.dump(selecionadas, f, ensure_ascii=False, indent=2)

    log.info(f"\nRESULTADO: {len(selecionadas)} oferta(s) prontas")
    for o in selecionadas:
        log.info(f"  {o['desconto']:3d}% OFF | R${o['preco_atual']:.2f} | {o['titulo'][:50]}")

if __name__ == "__main__":
    main()
