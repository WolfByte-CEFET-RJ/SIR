"""
Operacao MAVI - mavi.py
=========================
Script unico para indexar planilhas no Postgres e buscar no acervo,
com busca hibrida (lexical + semantica + estruturada).

USO:

  Indexar um arquivo:
      python mavi.py indexar caminho/planilha.xlsx

  Indexar uma pasta inteira (todos os .xlsx/.csv dentro dela):
      python mavi.py indexar caminho/da/pasta --pasta

  Buscar um termo em TODO o acervo (sem precisar dizer a planilha):
      python mavi.py buscar "termo que voce procura"

  Buscar restringindo a uma planilha especifica (opcional):
      python mavi.py buscar "termo" --fonte minha_planilha.xlsx

Configuracao da conexao: variaveis de ambiente (ver README.md) ou
edite DB_CONFIG abaixo para testes rapidos.
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # le o arquivo .env, se existir, e preenche as variaveis de ambiente

import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values

from embeddings import gerar_embedding, treinar_modelo_local, PROVIDER

# ---------------------------------------------------------------------------
# LOG DE EXECUCAO
# ---------------------------------------------------------------------------

logging.basicConfig(
    filename="mavi.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Tambem mostra os logs no terminal, alem de gravar no arquivo
_console = logging.StreamHandler()
_console.setLevel(logging.WARNING)  # so mostra avisos/erros no terminal, pra nao poluir
logging.getLogger().addHandler(_console)

log = logging.getLogger("mavi")

# ---------------------------------------------------------------------------
# CONFIGURACAO DA CONEXAO COM O BANCO
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": os.environ.get("MAVI_DB_HOST", "localhost"),
    "port": os.environ.get("MAVI_DB_PORT", "5432"),
    "dbname": os.environ.get("MAVI_DB_NAME", "mavi_teste"),
    "user": os.environ.get("MAVI_DB_USER", "postgres"),
    "password": os.environ.get("MAVI_DB_PASSWORD", "postgres"),
}


# ---------------------------------------------------------------------------
# NARRATIVIZACAO: transforma uma linha da planilha em texto corrido
# ---------------------------------------------------------------------------

def narrativizar_linha(linha: pd.Series, fonte: str) -> str:
    partes = []
    for coluna, valor in linha.items():
        if pd.isna(valor):
            continue
        partes.append(f"{coluna}: {valor}")
    corpo = ". ".join(partes)
    return f"Registro da planilha '{fonte}'. {corpo}."


def limpar_metadados(linha: pd.Series) -> dict:
    dados = {}
    for coluna, valor in linha.items():
        if pd.isna(valor):
            dados[str(coluna)] = None
        elif hasattr(valor, "isoformat"):
            dados[str(coluna)] = valor.isoformat()
        elif hasattr(valor, "item"):
            dados[str(coluna)] = valor.item()
        else:
            dados[str(coluna)] = valor
    return dados


def checar_colunas_vazias(df: pd.DataFrame, fonte: str) -> None:
    """Avisa se alguma coluna veio inteiramente vazia (ex: formulas nao calculadas)."""
    for coluna in df.columns:
        if df[coluna].isna().all():
            print(f"  [AVISO] '{fonte}': a coluna '{coluna}' veio totalmente vazia. "
                  f"Se ela tem formula, abra e salve a planilha no Excel antes de indexar.")


def ler_planilha(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() == ".csv":
        return pd.read_csv(caminho)
    return pd.read_excel(caminho)


# ---------------------------------------------------------------------------
# INDEXACAO
# ---------------------------------------------------------------------------

def indexar_planilha(caminho_planilha: Path, conn) -> int:
    """Indexa uma unica planilha usando uma conexao ja aberta. Retorna quantas linhas foram gravadas."""
    df = ler_planilha(caminho_planilha)
    fonte = caminho_planilha.name

    checar_colunas_vazias(df, fonte)

    registros = []
    for i, linha in df.iterrows():
        texto = narrativizar_linha(linha, fonte)
        metadados = limpar_metadados(linha)
        embedding = gerar_embedding(texto)
        registros.append((fonte, "planilha", int(i), Json(metadados), texto, embedding))

    with conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO documentos
                    (fonte, tipo_origem, linha_origem, metadados, conteudo_texto, embedding)
                VALUES %s
                ON CONFLICT (fonte, linha_origem)
                DO UPDATE SET
                    metadados = EXCLUDED.metadados,
                    conteudo_texto = EXCLUDED.conteudo_texto,
                    embedding = EXCLUDED.embedding,
                    atualizado_em = now()
                """,
                registros,
                template="(%s, %s, %s, %s, %s, %s)",
            )

    print(f"  '{fonte}': {len(registros)} linhas indexadas.")
    log.info(f"Indexado '{fonte}': {len(registros)} linhas (provider={PROVIDER})")
    return len(registros)


def indexar_pasta(caminho_pasta: Path, conn) -> None:
    """Varre a pasta e indexa todos os arquivos .xlsx e .csv encontrados."""
    extensoes = (".xlsx", ".csv")
    arquivos = sorted(
        f for f in caminho_pasta.iterdir()
        if f.suffix.lower() in extensoes and not f.name.startswith("~$")
    )

    if not arquivos:
        print(f"Nenhuma planilha (.xlsx/.csv) encontrada em: {caminho_pasta}")
        return

    print(f"Encontradas {len(arquivos)} planilha(s) em '{caminho_pasta}':\n")
    total = 0
    for arquivo in arquivos:
        try:
            total += indexar_planilha(arquivo, conn)
        except Exception as e:
            print(f"  [ERRO] Falha ao indexar '{arquivo.name}': {e}")
            log.error(f"Falha ao indexar '{arquivo.name}': {e}")

    print(f"\nConcluido: {total} linhas no total, de {len(arquivos)} arquivo(s).")
    log.info(f"Indexacao de pasta '{caminho_pasta}' concluida: {total} linhas, {len(arquivos)} arquivo(s)")


# ---------------------------------------------------------------------------
# REMOCAO DE UMA PLANILHA DO BANCO
# ---------------------------------------------------------------------------

def remover_planilha(fonte: str, conn) -> int:
    """Remove todos os registros de uma planilha (pelo nome do arquivo) do banco."""
    with conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documentos WHERE fonte = %s", (fonte,))
            linhas_removidas = cur.rowcount
    return linhas_removidas


def comando_remover(args) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        # Confirmacao de seguranca, para nao apagar por engano
        if not args.confirmar:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM documentos WHERE fonte = %s", (args.fonte,))
                quantidade = cur.fetchone()[0]
            if quantidade == 0:
                print(f"Nenhum registro encontrado para a fonte '{args.fonte}'. Nada a remover.")
                return
            resposta = input(
                f"Isso vai remover {quantidade} registro(s) da fonte '{args.fonte}'. "
                f"Confirma? (digite 'sim' para continuar): "
            )
            if resposta.strip().lower() != "sim":
                print("Operacao cancelada.")
                return

        removidos = remover_planilha(args.fonte, conn)
        print(f"{removidos} registro(s) removido(s) da fonte '{args.fonte}'.")
        log.info(f"Removidos {removidos} registro(s) da fonte '{args.fonte}'")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BUSCA
# ---------------------------------------------------------------------------

def buscar(termo: str, limite: int = 10, fonte: str | None = None):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if fonte:
                cur.execute(
                    """
                    SELECT id, fonte, linha_origem, conteudo_texto,
                           ts_rank(conteudo_tsv, plainto_tsquery('portuguese', %s)) AS relevancia
                    FROM documentos
                    WHERE conteudo_tsv @@ plainto_tsquery('portuguese', %s)
                      AND fonte = %s
                    ORDER BY relevancia DESC
                    LIMIT %s
                    """,
                    (termo, termo, fonte, limite),
                )
            else:
                cur.execute(
                    """
                    SELECT id, fonte, linha_origem, conteudo_texto,
                           ts_rank(conteudo_tsv, plainto_tsquery('portuguese', %s)) AS relevancia
                    FROM documentos
                    WHERE conteudo_tsv @@ plainto_tsquery('portuguese', %s)
                    ORDER BY relevancia DESC
                    LIMIT %s
                    """,
                    (termo, termo, limite),
                )
            return cur.fetchall()
    finally:
        conn.close()


def comando_buscar(args) -> None:
    resultados = buscar(args.termo, args.limite, args.fonte)

    if not resultados:
        print(f"Nenhum resultado encontrado para: '{args.termo}'")
        return

    print(f"{len(resultados)} resultado(s) para '{args.termo}':\n")
    log.info(f"Busca lexical por '{args.termo}': {len(resultados)} resultado(s)")
    for id_, fonte, linha_origem, texto, relevancia in resultados:
        print(f"[id={id_} | fonte={fonte} | linha={linha_origem} | relevancia={relevancia:.4f}]")
        print(texto)
        print()


def comando_indexar(args) -> None:
    caminho = Path(args.caminho)
    if not caminho.exists():
        print(f"ERRO: caminho nao encontrado: {caminho}")
        sys.exit(1)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        if args.pasta:
            if not caminho.is_dir():
                print(f"ERRO: --pasta foi usado, mas '{caminho}' nao e uma pasta.")
                sys.exit(1)
            indexar_pasta(caminho, conn)
        else:
            if caminho.is_dir():
                print("ERRO: voce passou uma pasta sem o parametro --pasta. "
                      "Use: python mavi.py indexar SUA_PASTA --pasta")
                sys.exit(1)
            indexar_planilha(caminho, conn)
    finally:
        conn.close()

    if args.buscar:
        print(f"\n--- Testando busca lexical por: '{args.buscar}' ---")
        comando_buscar(argparse.Namespace(termo=args.buscar, limite=10, fonte=None))


# ---------------------------------------------------------------------------
# TREINAMENTO DO MODELO LOCAL DE EMBEDDINGS
# ---------------------------------------------------------------------------

def comando_treinar_embeddings(args) -> None:
    """
    Le TODOS os textos ja indexados no banco, treina o modelo local de
    embeddings sobre eles, e depois recalcula o vetor de cada registro.
    So faz sentido quando MAVI_EMBEDDING_PROVIDER=local.
    """
    if PROVIDER != "local":
        print(f"Provider atual e '{PROVIDER}', nao 'local'. Esse comando so serve para o provider local.")
        print("Para os providers 'openai'/'voyage', basta rodar 'python mavi.py indexar ...' de novo -")
        print("cada linha ja gera o embedding no momento da indexacao, via API.")
        return

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, conteudo_texto FROM documentos ORDER BY id")
            linhas = cur.fetchall()

        if not linhas:
            print("Nenhum registro no banco ainda. Indexe alguma planilha antes de treinar.")
            return

        textos = [linha[1] for linha in linhas]
        treinar_modelo_local(textos)

        print("Recalculando embeddings de todos os registros com o modelo treinado...")
        atualizados = 0
        with conn:
            with conn.cursor() as cur:
                for id_, texto in linhas:
                    vetor = gerar_embedding(texto)
                    cur.execute(
                        "UPDATE documentos SET embedding = %s WHERE id = %s",
                        (vetor, id_),
                    )
                    atualizados += 1
        print(f"{atualizados} registros atualizados com embedding.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# BUSCA SEMANTICA
# ---------------------------------------------------------------------------

def buscar_semantico(termo: str, limite: int = 10, fonte: str | None = None):
    vetor_consulta = gerar_embedding(termo)
    if vetor_consulta is None:
        print("Nao ha modelo de embedding disponivel. Rode 'python mavi.py treinar-embeddings' "
              "(provider local) ou configure MAVI_EMBEDDING_PROVIDER=openai/voyage com a chave de API.")
        return []

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            if fonte:
                cur.execute(
                    """
                    SELECT id, fonte, linha_origem, conteudo_texto,
                           1 - (embedding <=> %s::vector) AS similaridade
                    FROM documentos
                    WHERE embedding IS NOT NULL AND fonte = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vetor_consulta, fonte, vetor_consulta, limite),
                )
            else:
                cur.execute(
                    """
                    SELECT id, fonte, linha_origem, conteudo_texto,
                           1 - (embedding <=> %s::vector) AS similaridade
                    FROM documentos
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vetor_consulta, vetor_consulta, limite),
                )
            return cur.fetchall()
    finally:
        conn.close()


def comando_buscar_semantico(args) -> None:
    resultados = buscar_semantico(args.termo, args.limite, args.fonte)

    if not resultados:
        return

    print(f"{len(resultados)} resultado(s) semanticamente proximos de '{args.termo}':\n")
    for id_, fonte, linha_origem, texto, similaridade in resultados:
        print(f"[id={id_} | fonte={fonte} | linha={linha_origem} | similaridade={similaridade:.4f}]")
        print(texto)
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Operacao MAVI - indexa planilhas e busca no acervo (Postgres, busca hibrida)."
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_indexar = subparsers.add_parser("indexar", help="Indexa uma planilha ou uma pasta de planilhas")
    p_indexar.add_argument("caminho", type=str, help="Caminho para o arquivo .xlsx/.csv OU para uma pasta")
    p_indexar.add_argument("--pasta", action="store_true",
                            help="Trata o caminho como uma pasta e indexa todas as planilhas dentro dela")
    p_indexar.add_argument("--buscar", type=str, default=None,
                            help="Apos indexar, ja testa uma busca lexical com esse termo")
    p_indexar.set_defaults(func=comando_indexar)

    p_buscar = subparsers.add_parser("buscar", help="Busca um termo em todo o acervo ja indexado")
    p_buscar.add_argument("termo", type=str, help="Termo ou frase a buscar")
    p_buscar.add_argument("--limite", type=int, default=10, help="Quantidade maxima de resultados")
    p_buscar.add_argument("--fonte", type=str, default=None,
                           help="(Opcional) restringe a busca a uma planilha especifica")
    p_buscar.set_defaults(func=comando_buscar)

    p_treinar = subparsers.add_parser("treinar-embeddings",
                                       help="Treina o modelo local de embeddings sobre o acervo (provider local)")
    p_treinar.set_defaults(func=comando_treinar_embeddings)

    p_buscar_sem = subparsers.add_parser("buscar-semantico",
                                          help="Busca por similaridade de significado (embeddings)")
    p_buscar_sem.add_argument("termo", type=str, help="Termo ou frase a buscar")
    p_buscar_sem.add_argument("--limite", type=int, default=10, help="Quantidade maxima de resultados")
    p_buscar_sem.add_argument("--fonte", type=str, default=None,
                               help="(Opcional) restringe a busca a uma planilha especifica")
    p_buscar_sem.set_defaults(func=comando_buscar_semantico)

    p_remover = subparsers.add_parser("remover", help="Remove todos os registros de uma planilha do banco")
    p_remover.add_argument("fonte", type=str, help="Nome do arquivo (fonte) a remover, ex: minha_planilha.xlsx")
    p_remover.add_argument("--confirmar", action="store_true",
                            help="Remove sem pedir confirmacao (use com cuidado)")
    p_remover.set_defaults(func=comando_remover)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
