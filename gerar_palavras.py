
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# CONFIGURACOES
URL_ENTRETENIMENTO = "https://jovempan.com.br/entretenimento/"
MAX_MATERIAS = 30
MAX_PAGINAS_BUSCA = 8
MIN_CANDIDATOS = MAX_MATERIAS + 20
FUSO_BRASIL = timezone(timedelta(hours=-3))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Palavras ignoradas na contagem
STOPWORDS = set("""
a ao aos as o os um uma uns umas de da das do dos e em
no na nos nas num numa para por pelo pela pelos pelas
com sem que quem qual quais quando onde como porque
porem mas ou se sua suas seu seus meu minha meus minhas
isso isto esse essa esses essas este esta estes estas
aquele aquela e sao foi foram ser sendo sido era eram
estar esta estao estava estavam tem tinha tinham
ter ha houve haver pode podem poderia poderiam vai vao
ir vem veio fazer feito fez faz dizer diz disse
disseram segundo sobre entre apos antes durante desde
ate ainda tambem ja mais menos muito muita muitos muitas
pouco pouca poucos poucas todo toda todos todas outro
outra outros outras mesmo mesma mesmos mesmas cada algo
alguem algum alguma alguns algumas tanto tanta tao
apenas quase entao assim agora hoje ontem amanha ano
anos mes meses dia dias vez vezes parte forma momento
primeiro primeira segundo segunda novo nova novos novas
maior menor atraves alem cerca diante enquanto depois
neste nesta nesse nessa naquele aqui ali la ele ela
eles elas lhe lhes nos voces voce eu tu gente lado
dois duas tres quatro pessoas
jovem pan entretenimento noticia noticias materia materias
foto fotos reproducao imagens imagem instagram facebook
twitter video videos news classicpan afiliadas radio
leia veja saiba confira site publicacao publicado publicada
redacao conteudo relacionados publicidade anuncio
""".split())


def normalizar(palavra):
    return "".join(
        c for c in unicodedata.normalize("NFD", palavra)
        if unicodedata.category(c) != "Mn"
    )


STOPWORDS = {normalizar(p) for p in STOPWORDS}


# IDENTIFICAR LINKS DE MATERIAS
def limpar_url_materia(href):
    url = urlparse(urljoin(URL_ENTRETENIMENTO, href))
    partes = url.path.strip("/").split("/")

    if url.netloc.lower() not in (
        "jovempan.com.br",
        "www.jovempan.com.br"
    ):
        return None

    if len(partes) < 3 or partes[0] != "entretenimento":
        return None

    if any(
        p in ("pagina", "page", "tag", "feed")
        for p in partes[1:]
    ):
        return None

    return (
        "https://jovempan.com.br/"
        + "/".join(partes)
        + "/"
    )


# BUSCAR MATERIAS NAS PAGINAS DA EDITORIA
def obter_links_materias(sessao):
    encontrados = []
    vistos = set()

    for pagina in range(1, MAX_PAGINAS_BUSCA + 1):
        url = (
            URL_ENTRETENIMENTO if pagina == 1
            else f"{URL_ENTRETENIMENTO}pagina/{pagina}/"
        )

        resposta = sessao.get(url, timeout=20)
        resposta.raise_for_status()

        soup = BeautifulSoup(
            resposta.content, "html.parser"
        )

        area = soup.find("main") or soup
        novos = 0

        for a in area.select("a[href]"):
            materia = limpar_url_materia(a["href"])

            if materia and materia not in vistos:
                vistos.add(materia)
                encontrados.append(materia)
                novos += 1

        print(
            f"Pagina {pagina}: {novos} links novos. "
            f"Total: {len(encontrados)}"
        )

        if len(encontrados) >= MIN_CANDIDATOS:
            break

        if pagina > 1 and novos == 0:
            break

    if len(encontrados) < MAX_MATERIAS:
        raise RuntimeError(
            f"Encontrei apenas {len(encontrados)} links. "
            "JSON anterior preservado."
        )

    return encontrados


# CONVERTER DATA DE PUBLICACAO
def converter_data(valor):
    if not valor:
        return None

    try:
        data = datetime.fromisoformat(
            valor.strip().replace("Z", "+00:00")
        )

        if data.tzinfo is None:
            data = data.replace(tzinfo=FUSO_BRASIL)

        return data.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


# EXTRAIR DATA DA MATERIA
def extrair_data(soup):
    seletores = (
        'meta[property="article:published_time"]',
        'meta[property="datePublished"]',
        'meta[itemprop="datePublished"]',
        'meta[name="datePublished"]',
        'time[datetime]',
    )

    for seletor in seletores:
        tag = soup.select_one(seletor)

        if tag:
            data = converter_data(
                tag.get("content") or tag.get("datetime")
            )

            if data:
                return data

    # Alternativa: data escrita na pagina
    texto = soup.get_text(" ", strip=True)

    padrao = (
        r"(\d{2})/(\d{2})/(\d{4})\s+"
        r"[àa]s\s+(\d{1,2})[h:](\d{2})"
    )

    encontrado = re.search(
        padrao, texto, flags=re.IGNORECASE
    )

    if encontrado:
        dia, mes, ano, hora, minuto = map(
            int, encontrado.groups()
        )

        try:
            return datetime(
                ano, mes, dia, hora, minuto,
                tzinfo=FUSO_BRASIL
            ).astimezone(timezone.utc)

        except ValueError:
            pass

    return None


# EXTRAIR APENAS O TEXTO EDITORIAL
def extrair_texto_materia(soup):
    seletores = (
        '[itemprop="articleBody"]',
        ".entry-content",
        ".post-content",
        ".article-content",
        ".article-body",
        ".single-post-content",
        ".content-article",
        '[class*="article__body"]',
        '[class*="post__content"]',
        "article",
        "main",
    )

    lixo = (
        "script, style, nav, aside, footer, header, form, "
        "figcaption, button, [class*='related'], "
        "[class*='share'], [class*='sidebar'], "
        "[class*='recommend'], [class*='ads-'], "
        "[class*='mais-lidas']"
    )

    for seletor in seletores:
        for bloco in soup.select(seletor):
            copia = BeautifulSoup(
                str(bloco), "html.parser"
            )

            for tag in copia.select(lixo):
                tag.decompose()

            paragrafos = [
                p.get_text(" ", strip=True)
                for p in copia.select("p")
                if len(
                    p.get_text(" ", strip=True)
                ) >= 35
            ]

            texto = " ".join(paragrafos)

            if len(texto) >= 200:
                return texto

    return ""


# ABRIR E VALIDAR CADA MATERIA
def carregar_materia(sessao, url):
    try:
        resposta = sessao.get(url, timeout=20)
        resposta.raise_for_status()

        soup = BeautifulSoup(
            resposta.content, "html.parser"
        )

        h1 = soup.find("h1")

        if not h1:
            return None

        texto = extrair_texto_materia(soup)

        if not texto:
            return None

        return {
            "url": url,
            "titulo": h1.get_text(" ", strip=True),
            "data": extrair_data(soup),
            "texto": texto,
        }

    except requests.RequestException as erro:
        print(f"ERRO em {url}: {erro}")
        return None


# CONTAR TODAS AS PALAVRAS VALIDAS
def analisar_palavras(materias):
    frequencias = Counter()
    grafias = defaultdict(Counter)

    for materia in materias:
        palavras = re.findall(
            r"[^\W\d_]{4,}",
            materia["texto"].casefold()
        )

        for palavra in palavras:
            chave = normalizar(palavra)

            if chave not in STOPWORDS:
                frequencias[chave] += 1
                grafias[chave][palavra] += 1

    # Todas as palavras, sem limite
    return [
        grafias[chave].most_common(1)[0][0]
        for chave, _ in frequencias.most_common()
    ]


# EXECUCAO PRINCIPAL
def main():
    with requests.Session() as sessao:
        sessao.headers.update(HEADERS)

        links = obter_links_materias(sessao)

        materias = []

        for indice, url in enumerate(links, 1):
            materia = carregar_materia(sessao, url)

            if materia:
                materias.append(materia)

            print(
                f"Lidas {indice}/{len(links)} | "
                f"Validas: {len(materias)}"
            )

    if len(materias) < MAX_MATERIAS:
        raise RuntimeError(
            f"Apenas {len(materias)} materias validas. "
            "JSON anterior preservado."
        )

    # Ordena por data de publicacao
    data_minima = datetime.min.replace(
        tzinfo=timezone.utc
    )

    materias.sort(
        key=lambda m: m["data"] or data_minima,
        reverse=True
    )

    # Escolhe as 30 mais recentes
    selecionadas = materias[:MAX_MATERIAS]

    print("30 materias selecionadas:")

    for numero, materia in enumerate(
        selecionadas, 1
    ):
        print(
            f"{numero:02d}. "
            f"{materia['data']} | "
            f"{materia['titulo']}"
        )

    palavras = analisar_palavras(selecionadas)

    if not palavras:
        raise RuntimeError(
            "Nenhuma palavra valida. "
            "JSON anterior preservado."
        )

    # ATUALIZAR JSON
    with open(
        "palavras.json", "w", encoding="utf-8"
    ) as arquivo:
        json.dump(
            palavras,
            arquivo,
            ensure_ascii=False,
            indent=2
        )
        arquivo.write("\n")

    print(
        f"Sucesso: {len(selecionadas)} materias, "
        f"{len(palavras)} palavras distintas."
    )


if __name__ == "__main__":
    main()
