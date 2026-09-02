import io
from googleapiclient.http import MediaIoBaseDownload
from collections.abc import Iterator

def get_text_from_google_doc(service, file_id, output_type='text/markdown') -> str:
    """
    Extrai o conteúdo de um Google Doc e retorna como uma string.
    output_type: O tipo MIME do formato de saída. Ver https://developers.google.com/workspace/drive/api/guides/ref-export-formats
    """
    request = service.files().export_media(fileId=file_id, mimeType=output_type)

    file_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(file_stream, request)
    done = False

    while not done:
        status, done = downloader.next_chunk()

    # Convert the downloaded bytes into a Python string
    text = file_stream.getvalue().decode('utf-8')
    return text


def get_content_from_google(service, file_id, mime_type) -> str | None:
    """
    Router para funções de extração de conteúdo do Google Drive com base no tipo MIME do arquivo.
    """
    match mime_type:
        case 'application/vnd.google-apps.document':
            print(f"Extraindo conteúdo do Google Doc (ID: {file_id})")
            return get_text_from_google_doc(service, file_id)
        case 'application/pdf':
            # TODO pdf extraction
            pass
        case 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            # TODO docx extraction
            pass
    return None

def get_content_from_tree(service, tree: dict, current_path="") -> Iterator[dict[str, str]]:
    """
    Percorre a árvore de pastas gerada pelo crawler recursivamente e baixa o conteúdo de cada arquivo, retornando um dicionário com metadados e conteúdo.
    Caminhos relativos são construídos com base na estrutura da árvore.
    """
    for folder_id, folder_data in tree.items():
        # Constrói o caminho até a pasta atual
        new_path = f"{current_path}/{folder_data['name']}" if current_path else folder_data['name']

        # 1. Processa os arquivos da pasta atual
        files = folder_data.get("files", {})
        for file_id, file_meta in files.items():
            file_meta["id"] = file_id            
            file_meta["path"] = new_path
            mime_type = file_meta.get("mimeType", "")
            content = get_content_from_google(service, file_id, mime_type)
            if content is not None:
                file_meta["content"] = content 
            yield file_meta

        # 2. Chama a função recursivamente para as subpastas
        subfolders = folder_data.get("folders", {})
        if subfolders:
            yield from get_content_from_tree(service, subfolders, new_path)


if __name__ == "__main__":
    import argparse
    import json
    import os
    from pathlib import Path
    from auth import get_google_drive_service

    parser = argparse.ArgumentParser(description="Extrai o conteúdo de arquivos do Google Drive a partir de uma árvore de diretórios.")
    parser.add_argument("tree_file", type=str, help="O caminho para o arquivo JSON contendo a árvore de diretórios do Google Drive.")
    args = parser.parse_args()

    tree_file = Path(args.tree_file)

    with open(tree_file, "r", encoding="utf-8") as f:
        tree = json.load(f)

    save_path = tree_file.parent / f"parsed_{tree_file.stem}.jsonl"
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    service = get_google_drive_service()
    with open(save_path, "w", encoding="utf-8") as f:
        for file_meta in get_content_from_tree(service, tree):
            f.write(json.dumps(file_meta, ensure_ascii=False) + "\n")

    print(f"Conteúdo extraído e salvo em {save_path}")
