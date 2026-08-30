import os
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource

# https://developers.google.com/workspace/drive/api/quickstart/python

# Escopos padrão necessários para acessar a API do Google Drive (apenas leitura por padrão)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_google_drive_service(scopes: list[str] = SCOPES) -> Resource:
    """
    Requer credentials.json para acessar a API do Google Drive 
    Autentica o usuário e retorna um cliente de serviço para a API do Google Drive.
    
    Verifica se o arquivo 'token.json' existe e se as credenciais são válidas. Se expiradas,
    tenta atualizá-las. Se inválidas ou inexistentes, inicia o fluxo de autorização via navegador
    usando o arquivo 'credentials.json' e salva um novo 'token.json'.

    Args:
        scopes (list[str]): Lista de escopos de acesso solicitados para a API.

    Returns:
        Resource: Um objeto de serviço para interagir com a API do Google Drive (v3).
    """
    creds = None

    # Caminhos relativos ao próprio módulo (MAVI\extraction\g_drive\credentials.json)
    base_dir = os.path.dirname(__file__)
    cred_path = os.path.join(base_dir, 'credentials.json')
    token_path = os.path.join(base_dir, 'token.json')

    # Verifica se já temos um arquivo de token armazenado localmente
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)
    
    # Se não temos credenciais ou se as credenciais atuais são inválidas
    if not creds or not creds.valid:
        print("Nenhuma credencial válida encontrada. Verificando opções...")
        
        # Tenta atualizar as credenciais se elas estiverem expiradas e houver um token de atualização (refresh token)
        if creds and creds.expired and creds.refresh_token:
            print("Tentando atualizar credenciais expiradas...")
            try:
                creds.refresh(Request())
            except RefreshError:
                print("O token de atualização é inválido ou foi revogado. Forçando re-autenticação...")
                creds = None  # Reseta as credenciais para que o bloco seguinte seja acionado
                if os.path.exists(token_path):
                    os.remove(token_path)  # Remove o arquivo corrompido/expirado

        # Se a atualização falhou ou não tínhamos credenciais, inicia o fluxo no navegador
        if not creds:
            print("Iniciando fluxo de autorização...")
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, scopes)
            creds = flow.run_local_server(port=0)

            # Salva as novas credenciais válidas para execuções futuras
            with open(token_path, 'w') as token:
                print(f"Salvando credenciais em {token_path}")
                token.write(creds.to_json())

        service = build('drive', 'v3', credentials=creds)

        try:
            about = service.about().get(fields="user(displayName, emailAddress)").execute()
            print(f"Autenticado como: {about['user']['displayName']} ({about['user']['emailAddress']})")
        except Exception as e:
            print(f"Erro na autenticação: {e}")

    return service