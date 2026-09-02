
from googleapiclient.discovery import Resource

FILES_METADATA = "createdTime, modifiedTime, version"

def get_google_drive_tree(service: Resource, root_folder_id: str, files_metadata: str = FILES_METADATA) -> dict[str, dict]:
    """
    Retorna uma árvore de diretórios aninhada para uma pasta do Google Drive, incluindo arquivos e subpastas.
    A função percorre recursivamente a pasta raiz e suas subpastas, coletando informações sobre arquivos e pastas,
    incluindo metadados especificados.
    """
    # A busca não retorna o nome da pasta raiz, então precisamos acecá-lo separadamente
    root_name = service.files().get(
        fileId=root_folder_id, 
        fields="name"
    ).execute().get("name", "Root Folder")
    print(f"Construindo árvore para a pasta raiz: {root_name} (ID: {root_folder_id})")
    
    def _build_subtree(folder_id: str) -> tuple[list[dict], list[dict]]:
        """Recursive helper to fetch files and subfolders with full pagination support."""
        files = {}
        folders = {}
        page_token = None

        while True:
            # Retorna os arquivos e pastas
            results = service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=f"nextPageToken, files(id, name, mimeType, {files_metadata})",
                pageSize=1000, # Quantidade de itens por página (máximo de 1000)
                pageToken=page_token # Se houverem mais items que o máximo, page_token é usado para buscar os próximos resultados
            ).execute()

            items = results.get('files', [])

            for item in items:
                if item.get('mimeType') == 'application/vnd.google-apps.folder':
                    sub_id = item.get('id')
                    sub_name = item.get('name')
                    
                    # Explora as sub-pastas por recursão
                    sub_files, sub_folders = _build_subtree(sub_id)
                    
                    folders[sub_id] = {
                        "name": sub_name,
                        "files": sub_files,
                        "folders": sub_folders
                    }
                else:
                    file_id = item.pop('id')
                    files[file_id] = item

            page_token = results.get('nextPageToken')
            if not page_token:
                break

        return files, folders

    root_files, root_folders = _build_subtree(root_folder_id)

    tree = {
        root_folder_id: {
            "name": root_name,
            "files": root_files,
            "folders": root_folders
        }
    }
    return tree

if __name__ == "__main__":
    import argparse
    import os
    import json
    from auth import get_google_drive_service

    parser = argparse.ArgumentParser(description="Constrói uma árvore de diretórios aninhada para uma pasta do Google Drive.")
    parser.add_argument("root_folder_id", type=str, help="O ID da pasta raiz no Google Drive para construir a árvore.")
    args = parser.parse_args()

    service = get_google_drive_service()

    root_folder_id = args.root_folder_id
    tree = get_google_drive_tree(service, root_folder_id)
    
    base_dir = os.path.dirname(__file__)
    save_path = os.path.join(base_dir, "output", f"tree_{root_folder_id}.json")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=4)

    print(f"Árvore de diretórios salva em {save_path}")
