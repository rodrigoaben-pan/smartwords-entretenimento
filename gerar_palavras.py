import json
import re
from collections import Counter
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Termos neutros e irrelevantes para filtrar
STOPWORDS = set(
    [
        "de",
        "a",
        "o",
        "que",
        "e",
        "do",
        "da",
        "em",
        "um",
        "para",
        "com",
        "nao",
        "uma",
        "os",
        "no",
        "se",
        "na",
        "por",
        "mais",
        "as",
        "dos",
        "como",
        "mas",
        "ao",
        "ele",
        "das",
        "aqui",
        "sobre",
        "foi",
        "sua",
        "seu",
        "tem",
        "tambem",
        "disse",
        "segundo",
        "nesta",
        "neste",
        "ser",
        "estava",
        "anos",
        "pode",
        "veja",
        "após",
        "entre",
        "está",
        "estão",
        "foram",
        "materia",
        "noticia",
        "jovem",
        "pan",
        "foto",
        "reprodução",
        "instagram",
    ]
)

URL_ENTRETENIMENTO = "https://jovempan.com.br/entretenimento/"


def obter_links_materias():
    links = set()
    try:
        res = requests.get(URL_ENTRETENIMENTO, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content, "html.parser")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            # Garante que pega apenas matérias dentro de /entretenimento/
            if "jovempan.com.br/entretenimento/" in href and href.strip(
                "/"
            ) != URL_ENTRETENIMENTO.strip("/"):
                clean_url = href.split("?")[0].split("#")[0]
                if len(urlparse(clean_url).path.strip("/").split("/")) > 1:
                    links.add(clean_url)
            if len(links) >= 15:
                break
    except Exception as e:
        print(f"Erro ao capturar links de entretenimento: {e}")
    return list(links)


def analisar_palavras(urls):
    texto = ""
    for url in urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.content, "html.parser")
            for p in soup.find_all("p"):
                texto += " " + p.get_text()
        except Exception as e:
            print(f"Erro ao ler {url}: {e}")

    texto_limpo = re.sub(r"[^\w\s]", "", texto.lower())
    palavras = [
        p
        for p in texto_limpo.split()
        if p not in STOPWORDS and len(p) > 3
    ]
    contador = Counter(palavras)
    return [item[0] for item in contador.most_common(8)]


if __name__ == "__main__":
    materias = obter_links_materias()
    palavras_chave = analisar_palavras(materias)

    with open("palavras.json", "w", encoding="utf-8") as f:
        json.dump(palavras_chave, f, ensure_ascii=False)

    print("Palavras atualizadas:", palavras_chave)
