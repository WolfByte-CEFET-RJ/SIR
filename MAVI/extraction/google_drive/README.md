# Módulo de Extração - Google Drive (MAVI)

Módulo responsável por autenticar, mapear pastas recursivamente e extrair conteúdo de arquivos armazenados no Google Drive.

---

## Pré-requisitos & Autenticação

1. Obtenha o arquivo `credentials.json` seguindo o [Guia oficial do Google Drive API](https://developers.google.com/workspace/drive/api/quickstart/python#authorize_credentials_for_a_desktop_application).
2. Salve o arquivo `credentials.json` dentro deste diretório (`MAVI/extraction/google_drive/`).
3. Na primeira execução, uma janela do navegador será aberta para autorizar o acesso. As credenciais de sessão serão salvas automaticamente em `token.json`.

---

## Estrutura de Arquivos

* `auth.py`: Gerencia a autenticação OAuth2 e retorna o cliente do Google Drive.
* `crawler.py`: Percorre recursivamente as pastas do Drive a partir de um ID raiz e constrói a árvore de diretórios/metadados.
* `extractor.py`: Converte e extrai o conteúdo dos arquivos mapeados na árvore (suporta Google Docs com exportação em Markdown).
* `main.py`: Orquestrador que executa o pipeline completo (crawler + extração).

---

## Como Usar

### 1. Executar o Pipeline Completo

Gera a extração de todo o conteúdo em formato `.jsonl`:

```bash
# Execução padrão (salva parsed_<root_folder_id>.jsonl em output/)
uv run MAVI/extraction/google_drive/main.py <root_folder_id>

# Salvar também a árvore de diretórios (tree_<root_folder_id>.json)
uv run MAVI/extraction/google_drive/main.py <root_folder_id> --save-tree

# Especificar pasta de saída customizada
uv run MAVI/extraction/google_drive/main.py <root_folder_id> --output-dir caminho/para/saida --save-tree
```

---

### 2. Executar Etapas Isoladamente

#### Apenas Mapear a Árvore de Diretórios (`crawler.py`)
Salva a estrutura de pastas e metadados em formato JSON:
```bash
uv run MAVI/extraction/google_drive/crawler.py <root_folder_id>
```

#### Apenas Extrair Conteúdo a partir de uma Árvore já Salva (`extractor.py`)
Lê uma árvore `.json` existente e gera o `.jsonl` correspondente:
```bash
uv run MAVI/extraction/google_drive/extractor.py MAVI/extraction/google_drive/output/tree_<root_folder_id>.json
```

---

## Formato dos Dados de Saída

### Arquivo `.jsonl` (`parsed_<root_folder_id>.jsonl`)
Cada linha representa um arquivo com seus metadados e conteúdo extraído:

```json
{
  "id": "1P0FgiApXzZjQwGjDj-dtvcBpgCDSQkqJcvtgPaz2_KU",
  "name": "Documento Exemplo",
  "mimeType": "application/vnd.google-apps.document",
  "createdTime": "2024-01-15T10:00:00.000Z",
  "modifiedTime": "2024-02-10T14:30:00.000Z",
  "version": "12",
  "path": "Pesquisa/Subpasta",
  "content": "# Título do Documento\n\nConteúdo extraído em markdown..."
}
```