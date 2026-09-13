"""
Operacao MAVI - Geracao de Embeddings (busca semantica)
==========================================================

Este arquivo concentra as opcoes de geracao de embedding. Escolha UMA
das opcoes abaixo e configure a variavel MAVI_EMBEDDING_PROVIDER.

Opcoes disponiveis:

  "local"   -> Nao usa API nem internet. Usa uma tecnica estatistica
               (TF-IDF + SVD) sobre o proprio acervo. Boa para TESTAR
               a arquitetura sem custo e sem chave de API, mas NAO e
               um modelo de linguagem de verdade - a qualidade da
               busca semantica e limitada (capta textos com vocabulario
               parecido, nao "significado" no sentido pleno).
               Precisa ser TREINADA com o comando:
                   python mavi.py treinar-embeddings

  "openai"  -> Usa a API da OpenAI (modelo text-embedding-3-small,
               1536 dimensoes). Requer OPENAI_API_KEY configurada e
               ajustar a dimensao da coluna 'embedding' no schema.sql
               para 1536 (e rodar novamente treinar-embeddings apos
               trocar o provider).

  "voyage"  -> Usa a API da Voyage AI (parceira recomendada pela
               Anthropic para embeddings, modelo voyage-3, 1024
               dimensoes). Requer VOYAGE_API_KEY configurada e ajustar
               a dimensao da coluna 'embedding' para 1024.

  "gemini"  -> Usa a API do Google Gemini (GRATUITA, sem cartao de
               credito - via Google AI Studio). Modelo
               gemini-embedding-001, 3072 dimensoes por padrao (pode
               ser reduzido via output_dimensionality, ver funcao
               abaixo). Requer GEMINI_API_KEY configurada e ajustar
               a dimensao da coluna 'embedding' para bater com o
               valor escolhido.

IMPORTANTE: a dimensao do vetor gerado precisa bater com a dimensao
da coluna 'embedding' no banco (VECTOR(N) no schema.sql). Se trocar de
provider, ajuste o schema e reindexe os embeddings.
"""

import os
import pickle
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import numpy as np

PROVIDER = os.environ.get("MAVI_EMBEDDING_PROVIDER", "local")

# Onde o "modelo" local treinado fica salvo (arquivo pequeno, gerado localmente)
CAMINHO_MODELO_LOCAL = Path(os.environ.get("MAVI_LOCAL_MODEL_PATH", "embeddings_local.pkl"))

DIMENSAO_LOCAL = 256  # precisa bater com VECTOR(256) no schema.sql


# ---------------------------------------------------------------------------
# OPCAO 1: LOCAL (sem internet, sem API) - TF-IDF + SVD
# ---------------------------------------------------------------------------

def treinar_modelo_local(textos: list[str]) -> None:
    """
    Treina o modelo local a partir de TODOS os textos ja indexados no
    acervo, e salva num arquivo local (.pkl). Precisa ser rodado de novo
    sempre que o acervo crescer bastante, para o vocabulario acompanhar.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD

    vectorizer = TfidfVectorizer(max_features=5000)
    matriz_tfidf = vectorizer.fit_transform(textos)

    n_componentes = min(DIMENSAO_LOCAL, matriz_tfidf.shape[1] - 1, matriz_tfidf.shape[0] - 1)
    n_componentes = max(n_componentes, 2)  # SVD precisa de pelo menos 2 componentes

    svd = TruncatedSVD(n_components=n_componentes, random_state=42)
    svd.fit(matriz_tfidf)

    with open(CAMINHO_MODELO_LOCAL, "wb") as f:
        pickle.dump({"vectorizer": vectorizer, "svd": svd, "n_componentes": n_componentes}, f)

    print(f"Modelo local treinado com {len(textos)} textos e salvo em '{CAMINHO_MODELO_LOCAL}'.")


def _carregar_modelo_local():
    if not CAMINHO_MODELO_LOCAL.exists():
        return None
    with open(CAMINHO_MODELO_LOCAL, "rb") as f:
        return pickle.load(f)


def gerar_embedding_local(texto: str):
    """Gera o vetor usando o modelo local treinado. Retorna None se o modelo ainda nao existir."""
    modelo = _carregar_modelo_local()
    if modelo is None:
        return None

    vetor_tfidf = modelo["vectorizer"].transform([texto])
    vetor_reduzido = modelo["svd"].transform(vetor_tfidf)[0]

    # Preenche com zeros ate a dimensao fixa da coluna do banco, se necessario
    vetor_completo = np.zeros(DIMENSAO_LOCAL, dtype=float)
    vetor_completo[: len(vetor_reduzido)] = vetor_reduzido
    return vetor_completo.tolist()


# ---------------------------------------------------------------------------
# OPCAO 2: OpenAI (pronto para usar, requer chave de API e internet)
# ---------------------------------------------------------------------------

def gerar_embedding_openai(texto: str):
    """
    Requer: pip install openai
    Requer: variavel de ambiente OPENAI_API_KEY configurada
    Dimensao do resultado: 1536 (ajustar VECTOR(1536) no schema.sql)
    """
    from openai import OpenAI

    client = OpenAI()  # le a chave automaticamente de OPENAI_API_KEY
    resposta = client.embeddings.create(
        model="text-embedding-3-small",
        input=texto,
    )
    return resposta.data[0].embedding


# ---------------------------------------------------------------------------
# OPCAO 3: Voyage AI (pronto para usar, requer chave de API e internet)
# ---------------------------------------------------------------------------

def gerar_embedding_voyage(texto: str):
    """
    Requer: pip install voyageai
    Requer: variavel de ambiente VOYAGE_API_KEY configurada
    Dimensao do resultado: 1024 (ajustar VECTOR(1024) no schema.sql)
    """
    import voyageai

    client = voyageai.Client()  # le a chave automaticamente de VOYAGE_API_KEY
    resposta = client.embed([texto], model="voyage-3", input_type="document")
    return resposta.embeddings[0]


# ---------------------------------------------------------------------------
# OPCAO 4: Google Gemini (gratuito, sem cartao de credito - via Google AI Studio)
# ---------------------------------------------------------------------------

def gerar_embedding_gemini(texto: str):
    """
    Requer: pip install google-genai
    Requer: variavel de ambiente GEMINI_API_KEY configurada

    Como conseguir a chave (gratis, sem cartao de credito):
      1. Acesse https://aistudio.google.com
      2. Faca login com uma conta Google
      3. Clique em "Get API key"
      4. Copie a chave gerada

    Dimensao: o modelo gemini-embedding-001 retorna 3072 numeros por
    padrao. Aqui pedimos 768 explicitamente (output_dimensionality),
    que e menor, mais rapido de buscar, e continua com boa qualidade -
    mas o valor DEVE bater com a coluna VECTOR(N) do schema.sql.
    """
    from google import genai
    from google.genai import types

    client = genai.Client()  # le a chave automaticamente de GEMINI_API_KEY
    resposta = client.models.embed_content(
        model="gemini-embedding-001",
        contents=texto,
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    return resposta.embeddings[0].values


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL: escolhe o provider conforme a variavel de ambiente
# ---------------------------------------------------------------------------

def gerar_embedding(texto: str):
    if PROVIDER == "local":
        return gerar_embedding_local(texto)
    elif PROVIDER == "openai":
        return gerar_embedding_openai(texto)
    elif PROVIDER == "voyage":
        return gerar_embedding_voyage(texto)
    elif PROVIDER == "gemini":
        return gerar_embedding_gemini(texto)
    elif PROVIDER == "none":
        return None
    else:
        raise ValueError(f"Provider de embedding desconhecido: '{PROVIDER}'")
