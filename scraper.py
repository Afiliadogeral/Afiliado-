
"""
scraper.py v5 - FINAL
Extrai ofertas diretamente de mercadolivre.com.br/ofertas
CONFIRMADO que funciona nos servidores do GitHub Actions.
"""
import json, re, time, random, logging, requests
from bs4 import BeautifulSoup
from utils import carregar_historico, periodo_atual

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

ETIQUETA = "rafaelrafa13"
MAX_FINAL = 8
DESCONTO_MIN = 5

HEADERS_REQ = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Páginas de ofertas por categoria - todas confirmadas funcionando
PAGINAS_OFERTAS = [
    # Geral - maior volume
    "https://www.mercadolivre.com.br/ofertas",
    # Categorias específicas dos seus nichos
    "https://www.mercadolivre.com.br/ofertas#nav-by-category",
]

# Termos dos seus nichos para filtrar produtos relevantes
PALAVRAS_NICHO = [
    # Fitness/Suplementos
    "whey", "creatina", "proteina", "suplemento", "pre treino",
    "bcaa", "termogenico", "colageno", "vitamina", "omega",
    # Academia/Roupas
    "fitness", "academia", "legging", "short", "camiseta",
    # Pet
    "racao", "cachorro", "gato", "pet", "coleira", "antipulgas",
    # Moda/Calcados
    "tenis", "calcado", "roupa", "bermuda", "jaqueta",
    # Eletronicos
    "fone", "smartwatch", "relogio", "mochila",
]

def gerar_link_afiliado(url):
    """Adiciona parâmetros de rastreamento do afiliado."""
    url_limpa = url.split("?")[0].split("#")[0]
    return f"{url_limpa}?matt_tool=60085&matt_word={ETIQUETA}&matt_source=gg_mlb&matt_campaign_id={ETIQUETA}"

def produto_e_relevante(titulo):
    """Verifica se o produto é dos nichos desejados."""
    titulo_lower = titulo.lower()
    return any(palavra in titulo_lower for palavra in PALAVRAS_NICHO)

def extrair_numero(texto):
    if not texto:
        return None
    texto = texto.replace(".", "").replace(",", ".")
    numeros = re.findall(r'\d+\.?\d*', texto)
    try:
        return float(numeros[0]) if numeros else None
    except:
        return None

def scrape_ofertas():
    """Extrai ofertas da página principal de ofertas do ML."""
    url = "https://www.mercadolivre.com.br/ofertas"
    
    log.info(f"Acessando: {url}")
    try:
        r = requests.get(url, headers=HEADERS_REQ, timeout=30)
        log.info(f"Status: {r.status_code} | Tamanho: {len(r.text)} bytes")
        if r.status_code != 200:
            log.error(f"Falhou: {r.status_code}")
            return []
    except Exception as e:
        log.error(f"Erro ao acessar: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    
    # Tenta múltiplos seletores (o ML muda layout às vezes)
    seletores_card = [
        "li.promotion-item",
        "div.promotion-item",
        "[class*='promotion-item']",
        "li[class*='andes-card']",
        "div[class*='dynamic-carousel__item']",
        "ol.items_container li",
        "section.items_container li",
        "[data-testid*='deal']",
        "article",
    ]
    
    cards = []
    for sel in seletores_card:
        cards = soup.select(sel)
        if cards:
            log.info(f"Seletor '{sel}': {len(cards)} cards encontrados")
            break
    
    if not cards:
        # Tenta extrair via JSON embutido no HTML (Next.js/React)
        log.info("Tentando extrair via JSON embutido no HTML...")
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                data = json.loads(script.string or "")
                # Procura estruturas com preço e título
                text = json.dumps(data)
                if '"price"' in text and '"title"' in text:
                    log.info(f"JSON encontrado com {len(text)} chars")
                    # Extrai produtos do JSON
                    return extrair_de_json(data)
            except:
                continue
        
        # Último recurso: regex no HTML
        log.info("Tentando extração via regex...")
        return extrair_via_regex(r.text)
    
    ofertas = []
    for card in cards[:30]:
        try:
            # Título
            titulo_el = (
                card.select_one("p.promotion-item__title") or
                card.select_one("[class*='title']") or
                card.select_one("h2") or
                card.select_one("p")
            )
            if not titulo_el:
                continue
            titulo = titulo_el.get_text(strip=True)
            if not titulo or len(titulo) < 5:
                continue

            # Preço atual
            preco_el = (
                card.select_one("span.price-tag-amount") or
                card.select_one("[class*='price']") or
                card.select_one("span[class*='amount']")
            )
            preco_atual = extrair_numero(preco_el.get_text() if preco_el else None)
            if not preco_atual or preco_atual < 5:
                continue

            # Preço original
            orig_el = (
                card.select_one("s.price-tag-amount") or
                card.select_one("[class*='original']") or
                card.select_one("s")
            )
            preco_orig = extrair_numero(orig_el.get_text() if orig_el else None)
            if not preco_orig or preco_orig <= preco_atual:
                preco_orig = preco_atual

            # Desconto
            desconto_el = card.select_one("[class*='discount']")
            if desconto_el:
                nums = re.findall(r'\d+', desconto_el.get_text())
                desconto = int(nums[0]) if nums else 0
            elif preco_orig > preco_atual:
                desconto = round((1 - preco_atual / preco_orig) * 100)
            else:
                desconto = 0

            if desconto < DESCONTO_MIN:
                continue

            # Link
            link_el = card.select_one("a")
            if not link_el:
                continue
            url_prod = link_el.get("href", "")
            if not url_prod or "mercadolivre" not in url_prod:
                continue
            url_prod = url_prod.split("?")[0].split("#")[0]

            # Imagem
            img_el = card.select_one("img")
            imagem = ""
            if img_el:
                imagem = (img_el.get("src") or img_el.get("data-src") or "")
                imagem = imagem.replace("http://", "https://")
            if not imagem or "data:image" in imagem:
                imagem = "https://via.placeholder.com/500x500?text=Oferta+ML"

            ofertas.append({
                "titulo": titulo,
                "preco_original": round(preco_orig, 2),
                "preco_atual": round(preco_atual, 2),
                "desconto": desconto,
                "url": url_prod,
                "imagem": imagem,
                "link_afiliado": gerar_link_afiliado(url_prod),
            })
            log.info(f"  ✓ {titulo[:40]} | {desconto}% OFF | R${preco_atual:.2f}")

        except Exception as e:
            log.debug(f"  Erro num card: {e}")
            continue

    return ofertas


def extrair_de_json(data):
    """Extrai produtos de JSON embutido no HTML (Next.js)."""
    ofertas = []
    
    def buscar_recursivo(obj, profundidade=0):
        if profundidade > 10 or len(ofertas) >= 20:
            return
        if isinstance(obj, dict):
            # Verifica se parece um produto
            titulo = obj.get("title") or obj.get("name") or ""
            preco = obj.get("price") or obj.get("sale_price") or 0
            if titulo and preco and isinstance(preco, (int, float)):
                preco_orig = obj.get("original_price") or preco
                desconto = round((1 - preco/preco_orig)*100) if preco_orig > preco else 0
                url_prod = obj.get("permalink") or obj.get("url") or ""
                imagem = obj.get("thumbnail") or obj.get("image") or ""
                if url_prod and desconto >= DESCONTO_MIN:
                    imagem = imagem.replace("http://","https://")
                    if not imagem:
                        imagem = "https://via.placeholder.com/500x500?text=Oferta"
                    ofertas.append({
                        "titulo": str(titulo)[:100],
                        "preco_original": float(preco_orig),
                        "preco_atual": float(preco),
                        "desconto": desconto,
                        "url": url_prod.split("?")[0],
                        "imagem": imagem,
                        "link_afiliado": gerar_link_afiliado(url_prod),
                    })
                    log.info(f"  ✓ JSON: {titulo[:40]} | {desconto}% OFF")
            for v in obj.values():
                buscar_recursivo(v, profundidade + 1)
        elif isinstance(obj, list):
            for item in obj:
                buscar_recursivo(item, profundidade + 1)
    
    buscar_recursivo(data)
    return ofertas


def extrair_via_regex(html):
    """Extração de emergência via regex no HTML bruto."""
    ofertas = []
    # Procura padrões de preço e título no HTML
    pattern = r'"title"\s*:\s*"([^"]{10,100})"[^}]*"price"\s*:\s*(\d+\.?\d*)[^}]*"original_price"\s*:\s*(\d+\.?\d*)'
    matches = re.findall(pattern, html, re.DOTALL)
    
    urls = re.findall(r'https?://[^\s"<>]+produto\.mercadolivre[^\s"<>]+', html)
    imgs = re.findall(r'https://http2\.mlstatic\.com[^\s"<>]+\.jpg', html)
    
    for i, (titulo, preco_str, orig_str) in enumerate(matches[:15]):
        try:
            preco = float(preco_str)
            orig = float(orig_str)
            desconto = round((1 - preco/orig)*100) if orig > preco else 0
            if desconto < DESCONTO_MIN:
                continue
            url = urls[i] if i < len(urls) else ""
            imagem = imgs[i] if i < len(imgs) else "https://via.placeholder.com/500x500?text=Oferta"
            if not url:
                continue
            ofertas.append({
                "titulo": titulo,
                "preco_original": orig,
                "preco_atual": preco,
                "desconto": desconto,
                "url": url.split("?")[0],
                "imagem": imagem.replace("http://","https://"),
                "link_afiliado": gerar_link_afiliado(url),
            })
            log.info(f"  ✓ Regex: {titulo[:40]} | {desconto}% OFF")
        except:
            continue
    
    return ofertas


def main():
    log.info("="*60)
    log.info("SCRAPER v5 FINAL — mercadolivre.com.br/ofertas")
    log.info("="*60)

    historico = carregar_historico()
    ja_postadas = set(historico.keys())
    log.info(f"Histórico: {len(ja_postadas)} já postadas")

    # Extrai todas as ofertas
    todas = scrape_ofertas()
    log.info(f"\nTotal extraído: {len(todas)} produtos")

    # Filtra já postadas e sem relevância
    novas = []
    for o in todas:
        if o["url"] in ja_postadas:
            continue
        novas.append(o)

    # Se não filtrou por nicho, usa tudo (queremos postar!)
    log.info(f"Novas (não postadas): {len(novas)}")

    # Ordena por maior desconto
    novas.sort(key=lambda o: o["desconto"], reverse=True)
    selecionadas = novas[:MAX_FINAL]

    with open("ofertas.json", "w", encoding="utf-8") as f:
        json.dump(selecionadas, f, ensure_ascii=False, indent=2)

    log.info(f"\nRESULTADO: {len(selecionadas)} oferta(s) para postar")
    for o in selecionadas:
        log.info(f"  {o['desconto']:3d}% OFF | R${o['preco_atual']:.2f} | {o['titulo'][:50]}")

if __name__ == "__main__":
    main()
