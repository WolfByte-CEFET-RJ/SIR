import io
import json
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path

from docx import Document
from googleapiclient.discovery import Resource
from googleapiclient.http import MediaIoBaseDownload
from markitdown import MarkItDown
from pypdf import PdfReader
import pypandoc


def get_file_stream(request) -> io.BytesIO:
    """
    Baixa um arquivo do Google Drive e retorna um objeto BytesIO referente ao arquivo.
    """
    file_stream = io.BytesIO()
    downloader = MediaIoBaseDownload(file_stream, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return file_stream


class GoogleDriveExtractor:
    """
    Classe responsável por baixar e extrair o conteúdo de arquivos do Google Drive
    (Google Docs, DOCX, PDF), convertendo-os para Markdown quando aplicável.
    """

    def __init__(self, service: Resource):
        self.service = service

    def get_file_stream(self, request) -> io.BytesIO:
        """Baixa o arquivo binário do Google Drive para a memória."""
        return get_file_stream(request)

    def get_text_from_google_doc(self, file_id: str, output_type: str = 'text/markdown') -> str:
        """
        Extrai o conteúdo de um Google Doc nativo via export_media do Drive.
        """
        request = self.service.files().export_media(fileId=file_id, mimeType=output_type)
        file_stream = self.get_file_stream(request)
        return file_stream.getvalue().decode('utf-8')

    def get_text_from_pdf(self, file_id: str) -> str:
        """
        Extrai o conteúdo de um arquivo PDF usando pypdf.
        """
        request = self.service.files().get_media(fileId=file_id)
        file_stream = self.get_file_stream(request)
        reader = PdfReader(file_stream)
        return "".join([page.extract_text() or "" for page in reader.pages])

    def get_text_from_docx(self, file_id: str) -> str:
        """
        Extrai texto simples de um arquivo DOCX via python-docx.
        """
        request = self.service.files().get_media(fileId=file_id)
        file_stream = self.get_file_stream(request)
        doc = Document(file_stream)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])

    def get_md_from_docx_pandoc(self, file_id: str) -> str | None:
        """
        Transforma DOCX em Markdown utilizando o Pandoc (via pypandoc).
        """
        request = self.service.files().get_media(fileId=file_id)
        file_stream = self.get_file_stream(request)
        if not file_stream or file_stream.getbuffer().nbytes == 0:
            return None

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
            temp_file.write(file_stream.getvalue())
            caminho = temp_file.name

        try:
            conteudo = pypandoc.convert_file(caminho, to='gfm', extra_args=['--wrap=none'])
            conteudo = re.sub(r'\[\]\{#.*?\}', '', conteudo)
            return conteudo
        except Exception as e:
            print(f"Erro ao converter DOCX com Pandoc (ID: {file_id}): {e}")
            return None
        finally:
            if os.path.exists(caminho):
                os.remove(caminho)

    def get_md_from_docx_markitdown(self, file_id: str) -> str | None:
        """
        Transforma DOCX em Markdown utilizando a biblioteca MarkItDown.
        """
        md = MarkItDown()
        request = self.service.files().get_media(fileId=file_id)
        file_stream = self.get_file_stream(request)
        if not file_stream or file_stream.getbuffer().nbytes == 0:
            return None

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
            temp_file.write(file_stream.getvalue())
            caminho = temp_file.name

        try:
            result = md.convert(caminho)
            conteudo = result.text_content
            conteudo = re.sub(r'\[\]\{#.*?\}', '', conteudo)
            return conteudo
        except Exception as e:
            print(f"Erro ao converter DOCX com MarkItDown (ID: {file_id}): {e}")
            return None
        finally:
            if os.path.exists(caminho):
                os.remove(caminho)

    def get_content_from_google(self, file_id: str, mime_type: str) -> str | None:
        """
        Router para funções de extração de conteúdo do Google Drive com base no tipo MIME do arquivo.
        """
        match mime_type:
            case 'application/vnd.google-apps.document':
                print(f"Extraindo conteúdo do Google Doc (ID: {file_id})")
                return self.get_text_from_google_doc(file_id)

            case 'application/pdf':
                print(f"Extraindo conteúdo do PDF (ID: {file_id})")
                return self.get_text_from_pdf(file_id)

            case 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                print(f"Extraindo conteúdo do DOCX (ID: {file_id})")
                return self.get_md_from_docx(file_id)

        return None

    def get_content_from_tree(self, tree: dict, current_path: str = "") -> Iterator[dict[str, str]]:
        """
        Percorre a árvore de pastas gerada pelo crawler recursivamente e baixa o conteúdo de cada arquivo.
        """
        for folder_id, folder_data in tree.items():
            new_path = f"{current_path}/{folder_data['name']}" if current_path else folder_data['name']

            files = folder_data.get("files", {})
            for file_id, file_meta in files.items():
                file_meta["id"] = file_id
                file_meta["path"] = new_path
                mime_type = file_meta.get("mimeType", "")
                content = self.get_content_from_google(file_id, mime_type)
                if content is not None:
                    file_meta["content"] = content
                yield file_meta

            subfolders = folder_data.get("folders", {})
            if subfolders:
                yield from self.get_content_from_tree(subfolders, new_path)


# Funções de compatibilidade no nível do módulo (mantendo exatamente os mesmos nomes originais)
def get_text_from_google_doc(service: Resource, file_id: str, output_type: str = 'text/markdown') -> str:
    return GoogleDriveExtractor(service).get_text_from_google_doc(file_id, output_type)


def get_text_from_pdf(service: Resource, file_id: str) -> str:
    return GoogleDriveExtractor(service).get_text_from_pdf(file_id)


def get_text_from_docx(service: Resource, file_id: str) -> str:
    return GoogleDriveExtractor(service).get_text_from_docx(file_id)


def get_md_from_docx_pandoc(service: Resource, file_id: str) -> str | None:
    return GoogleDriveExtractor(service).get_md_from_docx_pandoc(file_id)


def get_md_from_docx_markitdown(service: Resource, file_id: str) -> str | None:
    return GoogleDriveExtractor(service).get_md_from_docx_markitdown(file_id)


def get_content_from_google(service: Resource, file_id: str, mime_type: str) -> str | None:
    return GoogleDriveExtractor(service).get_content_from_google(file_id, mime_type)


def get_content_from_tree(service: Resource, tree: dict, current_path: str = "") -> Iterator[dict[str, str]]:
    return GoogleDriveExtractor(service).get_content_from_tree(tree, current_path)


if __name__ == "__main__":
    import argparse
    from auth import get_google_drive_service

    parser = argparse.ArgumentParser(description="Extrai o conteúdo de arquivos do Google Drive a partir de uma árvore de diretórios.")
    parser.add_argument("tree_file", type=str, help="O caminho para o arquivo JSON contendo a árvore de diretórios do Google Drive.")
    args = parser.parse_args()

    tree_file = Path(args.tree_file)

    with open(tree_file, "r", encoding="utf-8") as f:
        tree = json.load(f)

    save_path = tree_file.parent / f"parsed_{tree_file.stem}.jsonl"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    service = get_google_drive_service()
    extractor = GoogleDriveExtractor(service)

    with open(save_path, "w", encoding="utf-8") as f:
        for file_meta in extractor.get_content_from_tree(tree):
            f.write(json.dumps(file_meta, ensure_ascii=False) + "\n")

    print(f"Conteúdo extraído e salvo em {save_path}")
