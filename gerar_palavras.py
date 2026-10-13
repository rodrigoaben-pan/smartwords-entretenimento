
import json
import re
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL_ENTRETENIMENTO = "https://jovempan.com.br/entretenimento/"
MAX_MATERIAS = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Palavras irrelevantes para o ranking
STOPWORDS = set("""
a ao aos as o os um uma uns umas de da das do dos e em
no na nos nas num numa para por pelo pela pelos pelas
com sem que quem qual quais quando onde como porque
porém mas ou se sua suas seu seus meu minha meus minhas
isso isto esse essa esses essas este esta estes estas
aquele aquela é são foi foram ser sendo sido era eram
estar está estão estava estavam tem têm tinha tinham
ter há houve haver pode podem poderia poderiam vai vão
ir vem vêm veio fazer feito fez faz dizer diz disse
disseram segundo sobre entre após antes durante desde
até ainda também já mais menos muito muita muitos muitas
pouco pouca poucos poucas todo toda todos todas outro
outra outros outras mesmo mesma mesmos mesmas cada algo
alguém algum alguma alguns algumas tanto tanta tão
apenas quase então assim agora hoje ontem amanhã ano
anos mês meses dia dias vez vezes parte forma momento
primeiro primeira segundo segunda novo nova novos novas
maior menor através além cerca diante enquanto depois
neste nesta nesse nessa naquele aqui ali lá ele ela
eles elas lhe lhes nós vocês você eu tu gente

jovem pan entretenimento noticia notícias notícia
matéria matérias foto fotos reprodução imagens imagem
instagram facebook twitter vídeo vídeos news classicpan
afiliadas rádio leia veja saiba confira site publicação
publicado publicada redação conteúdo relacionados
publicidade anúncio
""".split())


def normalizar(palavra):
    return "".join(
        letra
        for letra in unicodedata.normalize("NFD", palavra)
        if unicodedata.category(letra) != "Mn"
    )


STOPWORDS_NORMALIZADAS = {
    normalizar(p) for p in STOPWORDS
}


def obter_links_materias(sessao):
    resposta = sessao.get(
        URL_ENTRETENIMENTO,
        timeout=20
    )
    resposta.raise_for_status()

    soup = BeautifulSoup(
        resposta.content, "html.parser"
    )

    links = []
    vistos = set()

    for a in soup.select("a[href]"):
        url = urljoin(
            URL_ENTRETENIMENTO, a["href"]
        )

        parsed = urlparse(url)
        partes = parsed.path.strip("/").split("/")

        if parsed.netloc not in {
            "jovempan.com.br",
            "www.jovempan.com.br"
        }:
            continue

        # Filtra links de matérias da editoria
        if len(partes) < 3:
            continue

        if partes[0] != "entretenimento":
            continue

        if partes[1] in {
            "pagina", "page", "tag", "feed"
        }:
            continue

        url = (
            "https://jovempan.com.br"
            + parsed.path.rstrip("/")
            + "/"
        )

        if url not in vistos:
            vistos.add(url)
            links.append(url)

        if len(links) == MAX_MATERIAS:
            break

    return links


def extrair_texto_materia(html):
    soup = BeautifulSoup(html, "html.parser")

    # Uma matéria precisa ter título principal
    if not soup.find("h1"):
        return ""

    # Procura o corpo editorial, não a página inteira
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

    for seletor in seletores:
        for bloco in soup.select(seletor):
            corpo = BeautifulSoup(
                str(bloco), "html.parser"
            )

            # Remove componentes não editoriais
            for descartavel in corpo.select(
                "script, style, nav, aside, footer, "
                "header, form, figcaption, button, "
                "[class*='related'], "
                "[class*='share'], "
                "[class*='sidebar'], "
                "[class*='recommend'], "
                "[class*='ads-'], "
                "[class*='mais-lidas']"
            ):
                descartavel.decompose()

            paragrafos = [
                p.get_text(" ", strip=True)
                for p in corpo.select("p")
                if len(
                    p.get_text(" ", strip=True)
                ) >= 35
            ]

            texto = " ".join(paragrafos)

            if len(texto) >= 200:
                return texto

    return ""


def analisar_palavras(sessao, urls):
    contador = Counter()
    grafias = defaultdict(Counter)
    lidas = 0

    for url in urls:
        try:
            resposta = sessao.get(
                url, timeout=20
            )
            resposta.raise_for_status()

            texto = extrair_texto_materia(
                resposta.content
            )

            if not texto:
                print(
                    "IGNORADA (corpo não identificado):",
                    url
                )
                continue

            lidas += 1

            print(
                f"OK ({len(texto)} caracteres): {url}"
            )

            # Captura somente palavras com letras
            # Ignora números e caracteres especiais
            palavras = re.findall(
                r"[^\W\d_]{4,}",
                texto.casefold()
            )

            for palavra in palavras:
                chave = normalizar(palavra)

                if chave in STOPWORDS_NORMALIZADAS:
                    continue

                contador[chave] += 1
                grafias[chave][palavra] += 1

        except requests.RequestException as erro:
            print(f"ERRO lendo {url}: {erro}")

    # Protege o JSON de resultados inválidos
    if lidas < 5:
        raise RuntimeError(
            f"Apenas {lidas} matérias válidas. "
            "JSON anterior preservado."
        )

    palavras = [
        grafias[chave].most_common(1)[0][0]
        for chave, _ in contador.most_common(8)
    ]

    if len(palavras) < 8:
        raise RuntimeError(
            "Menos de 8 palavras encontradas. "
            "JSON anterior preservado."
        )

    print("Matérias analisadas:", lidas)
    print("Palavras selecionadas:", palavras)

    return palavras


if __name__ == "__main__":
    with requests.Session() as sessao:
        sessao.headers.update(HEADERS)

        links = obter_links_materias(sessao)

        if not links:
            raise RuntimeError(
                "Nenhum link de matéria identificado."
            )

        print("Links encontrados:", len(links))

        palavras = analisar_palavras(
            sessao, links
        )

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

    print("JSON atualizado com sucesso!")
