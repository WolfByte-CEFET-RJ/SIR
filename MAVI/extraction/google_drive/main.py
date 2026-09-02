import argparse
import json
from pathlib import Path

from auth import get_google_drive_service
from crawler import get_google_drive_tree
from extractor import get_content_from_tree

def run_pipeline(root_folder_id: str, output_dir: Path, save_tree: bool=False):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    service = get_google_drive_service()
    tree = get_google_drive_tree(service, root_folder_id)

    if save_tree:
        tree_save_path = output_dir / f"tree_{root_folder_id}.json"
        with open(tree_save_path, "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=4, ensure_ascii=False)
    
    content_save_path = output_dir / f"parsed_{root_folder_id}.jsonl"
    
    count = 0
    with open(content_save_path, "w", encoding="utf-8") as f:
        for file_meta in get_content_from_tree(service, tree):
            f.write(json.dumps(file_meta, ensure_ascii=False) + "\n")
            count += 1

    print(f"{count} arquivos processados e salvos em {content_save_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestra o mapeamento e extração de conteúdo do Google Drive.")
    parser.add_argument("root_folder_id", type=str, help="ID da pasta raiz do Google Drive")
    parser.add_argument("--output-dir", type=str, default="output", help="Diretório para salvar os resultados")
    parser.add_argument("--save-tree", action="store_true", help="Salva a árvore de diretórios em formato JSON")

    args = parser.parse_args()
    
    base_dir = Path(__file__).parent
    out_path = base_dir / args.output_dir
    save_tree = args.save_tree
    
    run_pipeline(args.root_folder_id, out_path, save_tree)
